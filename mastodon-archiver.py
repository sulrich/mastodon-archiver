#!/usr/bin/env python3
"""
mastodon personal archiver - archives favorites and bookmarks locally
"""

import hashlib
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


class MastodonArchiver:
    def __init__(self, base_url, access_token, archive_dir="/archive"):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.archive_dir = Path(archive_dir)
        self.db_path = self.archive_dir / "archiver.db"

        # create archive directory structure
        self.archive_dir.mkdir(exist_ok=True, parents=True)
        (self.archive_dir / "media").mkdir(exist_ok=True)
        (self.archive_dir / "posts").mkdir(exist_ok=True)

        # setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(self.archive_dir / "archiver.log"),
                logging.StreamHandler(),
            ],
        )
        self.logger = logging.getLogger(__name__)

        # initialize database
        self.init_db()

        # setup session for requests
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "mastodon-personal-archiver/1.0",
            }
        )

    def init_db(self):
        """initialize sqlite database for tracking processed posts"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS archived_posts (
                    post_id TEXT PRIMARY KEY,
                    post_type TEXT NOT NULL,  -- 'favorite' or 'bookmark'
                    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    post_url TEXT,
                    account_username TEXT,
                    created_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_post_type 
                ON archived_posts(post_type)
            """)
            conn.commit()

    def is_post_archived(self, post_id, post_type):
        """check if a post has already been archived"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM archived_posts WHERE post_id = ? AND post_type = ?",
                (post_id, post_type),
            )
            return cursor.fetchone() is not None

    def mark_post_archived(
        self, post_id, post_type, post_url, account_username, created_at
    ):
        """mark a post as archived in the database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO archived_posts 
                (post_id, post_type, post_url, account_username, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (post_id, post_type, post_url, account_username, created_at),
            )
            conn.commit()

    def get_api_data(self, endpoint, params=None):
        """make authenticated API request to mastodon"""
        url = urljoin(self.base_url, endpoint)
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"API request failed for {url}: {e}")
            return None

    def download_media(self, media_url, filename):
        """download media file and save locally"""
        media_path = self.archive_dir / "media" / filename

        # skip if already exists
        if media_path.exists():
            return str(media_path.relative_to(self.archive_dir))

        try:
            response = requests.get(media_url, stream=True, timeout=30)
            response.raise_for_status()

            with open(media_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            self.logger.info(f"downloaded media: {filename}")
            return str(media_path.relative_to(self.archive_dir))

        except Exception as e:
            self.logger.warning(f"failed to download media {media_url}: {e}")
            return media_url  # return original url as fallback

    def generate_filename(self, url, post_id, index=0):
        """generate safe filename for media"""
        parsed = urlparse(url)
        original_name = Path(parsed.path).name

        # extract file extension
        ext = Path(original_name).suffix
        if not ext:
            ext = ".jpg"  # default fallback

        # create safe filename using post_id and hash
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        if index > 0:
            return f"{post_id}_{url_hash}_{index}{ext}"
        else:
            return f"{post_id}_{url_hash}{ext}"

    def archive_post(self, post, post_type):
        """archive a single post with all its media"""
        post_id = post["id"]

        # skip if already archived
        if self.is_post_archived(post_id, post_type):
            return False

        self.logger.info(f"archiving {post_type} post {post_id}")

        # create post archive structure
        post_data = {
            "id": post_id,
            "type": post_type,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "url": post.get("url", ""),
            "uri": post.get("uri", ""),
            "created_at": post.get("created_at", ""),
            "account": {
                "id": post["account"]["id"],
                "username": post["account"]["username"],
                "acct": post["account"]["acct"],
                "display_name": post["account"]["display_name"],
                "url": post["account"]["url"],
            },
            "content": post.get("content", ""),
            "spoiler_text": post.get("spoiler_text", ""),
            "visibility": post.get("visibility", "public"),
            "language": post.get("language"),
            "replies_count": post.get("replies_count", 0),
            "reblogs_count": post.get("reblogs_count", 0),
            "favourites_count": post.get("favourites_count", 0),
            "media_attachments": [],
            "media_files": [],  # local file paths
        }

        # handle reblog (boost)
        if post.get("reblog"):
            post_data["reblog"] = {
                "id": post["reblog"]["id"],
                "url": post["reblog"].get("url", ""),
                "account": post["reblog"]["account"],
                "content": post["reblog"].get("content", ""),
                "created_at": post["reblog"].get("created_at", ""),
            }
            # use reblogged post's media
            media_source = post["reblog"]
        else:
            media_source = post

        # download and archive media attachments
        for i, attachment in enumerate(media_source.get("media_attachments", [])):
            media_url = attachment.get("url")
            if not media_url:
                continue

            filename = self.generate_filename(media_url, post_id, i)
            local_path = self.download_media(media_url, filename)

            # store both original attachment info and local path
            post_data["media_attachments"].append(attachment)
            post_data["media_files"].append(
                {
                    "original_url": media_url,
                    "local_path": local_path,
                    "type": attachment.get("type", "unknown"),
                    "description": attachment.get("description", ""),
                }
            )

        # save post data as json
        post_filename = f"{post_id}.json"
        post_path = self.archive_dir / "posts" / post_filename

        try:
            with open(post_path, "w", encoding="utf-8") as f:
                json.dump(post_data, f, indent=2, ensure_ascii=False)

            # mark as archived in database
            self.mark_post_archived(
                post_id,
                post_type,
                post.get("url", ""),
                post["account"]["acct"],
                post.get("created_at", ""),
            )

            self.logger.info(f"successfully archived {post_type} post {post_id}")
            return True

        except Exception as e:
            self.logger.error(f"failed to save post {post_id}: {e}")
            return False

    def get_posts_since_last_run(self, endpoint, post_type):
        """get new posts since last successful run"""
        posts = []
        max_id = None
        pages_processed = 0
        max_pages = 100  # safety limit to prevent infinite pagination

        # get the most recent archived post for this type to establish baseline
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                      SELECT post_id FROM archived_posts 
                      WHERE post_type = ? 
                      ORDER BY archived_at DESC 
                      LIMIT 1
                  """,
                (post_type,),
            )
            result = cursor.fetchone()
            last_archived_id = result[0] if result else None

        self.logger.info(
            f"Starting pagination for {post_type}, last archived ID: {last_archived_id}"
        )

        # fetch posts in pages
        while pages_processed < max_pages:
            params = {"limit": 40}  # max allowed by mastodon api
            if max_id:
                params["max_id"] = max_id

            page_posts = self.get_api_data(endpoint, params)
            if not page_posts:
                self.logger.info(
                    f"No more posts returned from API, stopping pagination"
                )
                break

            pages_processed += 1
            self.logger.debug(
                f"Processing page {pages_processed} with {len(page_posts)} posts"
            )

            # track if we've reached our stopping condition
            reached_archived_boundary = False

            for post in page_posts:
                post_id = post["id"]

                # if we've reached previously archived content, stop
                if last_archived_id and post_id == last_archived_id:
                    self.logger.info(
                        f"Reached previously archived {post_type} {post_id}, stopping"
                    )
                    reached_archived_boundary = True
                    break

                # add unarchived posts to our list
                if not self.is_post_archived(post_id, post_type):
                    posts.append(post)

            # stop if we reached the boundary or got less than a full page
            if reached_archived_boundary:
                break

            if len(page_posts) < 40:  # less than full page means we're done
                self.logger.info(
                    f"Received partial page ({len(page_posts)} posts), reached end of available posts"
                )
                break

            # prepare for next page
            max_id = page_posts[-1]["id"]

            # rate limiting - be nice to the server
            time.sleep(0.5)

        if pages_processed >= max_pages:
            self.logger.warning(
                f"Reached maximum pagination limit ({max_pages} pages) for {post_type}"
            )

        self.logger.info(
            f"Pagination complete: processed {pages_processed} pages, found {len(posts)} new posts"
        )

        # reverse the list so posts are processed chronologically (oldest first)
        posts.reverse()
        return posts

    def archive_favorites(self):
        """archive new favorites"""
        self.logger.info("checking for new favorites...")
        new_posts = self.get_posts_since_last_run("/api/v1/favourites", "favorite")

        archived_count = 0
        for post in new_posts:
            if self.archive_post(post, "favorite"):
                archived_count += 1

        self.logger.info(f"archived {archived_count} new favorites")
        return archived_count

    def archive_bookmarks(self):
        """archive new bookmarks"""
        self.logger.info("checking for new bookmarks...")
        new_posts = self.get_posts_since_last_run("/api/v1/bookmarks", "bookmark")

        archived_count = 0
        for post in new_posts:
            if self.archive_post(post, "bookmark"):
                archived_count += 1

        self.logger.info(f"archived {archived_count} new bookmarks")
        return archived_count

    def run(self):
        """main archival process"""
        self.logger.info("starting mastodon archival process")

        try:
            self.logger.info(f"archiving favourites")
            favorites_count = self.archive_favorites()
            bookmarks_count = self.archive_bookmarks()

            total_count = favorites_count + bookmarks_count
            if total_count > 0:
                self.logger.info(f"archive complete: {total_count} new posts archived")
            else:
                self.logger.info("no new posts to archive")

        except Exception as e:
            self.logger.error(f"archival process failed: {e}")
            sys.exit(1)


def main():
    # get configuration from environment variables
    base_url = os.environ.get("MASTODON_BASE_URL")
    access_token = os.environ.get("MASTODON_ACCESS_TOKEN")
    archive_dir = os.environ.get("ARCHIVE_DIR", "/archive")

    if not base_url or not access_token:
        print(
            "ERROR: MASTODON_BASE_URL and MASTODON_ACCESS_TOKEN environment variables required"
        )
        sys.exit(1)

    archiver = MastodonArchiver(base_url, access_token, archive_dir)
    archiver.run()


if __name__ == "__main__":
    main()
