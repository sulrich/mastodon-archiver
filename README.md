# mastodon personal archiver

a containerized python script that archives your mastodon favorites and
bookmarks locally, preserving them even if the original posts or media become
unavailable due to server retention policies.

## features

- archives both favorites and bookmarks incrementally
- downloads and stores media attachments locally
- uses sqlite to track what's already been archived
- durable against extended periods without new favorites/bookmarks
- preserves archived content even if you un-favorite/unbookmark items
- runs in docker for easy deployment and scheduling

## setup

### 1. get mastodon API credentials

1. log into your mastodon instance
2. go to settings -> development -> new application
3. create an application with these scopes:
   - `read:favourites`
   - `read:bookmarks`
4. note down your access token

### 2. configure environment

```bash
cp .env.example .env
# edit .env with your mastodon instance URL and access token
```

### 3. create archive directory

```bash
mkdir -p archive
```

## usage

### one-time run

```bash
docker compose up mastodon-archiver
```

### scheduled execution (every hour)

```bash
docker compose --profile cron up -d mastodon-archiver-cron
```

### manual build and run

```bash
docker build -t mastodon-archiver .
docker run --rm \
  -e MASTODON_BASE_URL="https://your-instance.com" \
  -e MASTODON_ACCESS_TOKEN="your_token" \
  -v $(pwd)/archive:/archive \
  mastodon-archiver
```

## archive structure

```
archive/
├── archiver.db          # sqlite database tracking archived posts
├── archiver.log         # application logs
├── posts/               # json files for each archived post
│   ├── 12345678.json
│   └── 87654321.json
└── media/               # downloaded media files
    ├── 12345678_a1b2c3d4.jpg
    └── 87654321_e5f6g7h8.mp4
```

### post json structure

each archived post is saved as a json file containing:

- original post metadata (id, url, timestamps, account info)
- post content and any content warnings
- engagement metrics (replies, boosts, favorites counts)
- media attachment metadata
- local file paths for downloaded media
- reblog information if applicable

## operational notes

### incremental archiving

the script only archives new posts since the last successful run, making it
efficient for regular execution.

### media handling

- media files are downloaded and stored with safe filenames
- original URLs are preserved as fallbacks
- if media download fails, the original URL is kept in the archive
- duplicate media (same URL) is only downloaded once

### database durability

- uses sqlite to track what's been archived
- posts remain archived even if you un-favorite/unbookmark them
- handles gaps in favorites/bookmarks gracefully

### rate limiting

the script includes small delays between API calls to be respectful to your
mastodon instance.

### error handling

- comprehensive logging to both file and console
- continues processing other posts if individual posts fail
- graceful handling of network errors and missing media

## troubleshooting

### check logs

```bash
docker compose logs mastodon-archiver-cron
# or
tail -f archive/archiver.log
```

### verify API access

test your credentials:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://your-instance.com/api/v1/accounts/verify_credentials
```

### inspect database

```bash
sqlite3 archive/archiver.db
.tables
SELECT COUNT(*) FROM archived_posts;
SELECT post_type, COUNT(*) FROM archived_posts GROUP BY post_type;
```

### manual media download test

if media downloads are failing, check if the URLs are accessible:

```bash
curl -I "https://media-url-from-post"
```

## security considerations

- the access token has read-only permissions
- script runs as non-root user in container
- archive directory should have appropriate filesystem permissions
- consider backing up the archive directory regularly

## api reference

this script uses the following mastodon API endpoints:

- `/api/v1/favourites` - fetch favorited posts
- `/api/v1/bookmarks` - fetch bookmarked posts

both endpoints support pagination via `max_id` and `limit` parameters.
