FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim
# install system dependencies

RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /uvx /bin/

# set working directory
WORKDIR /app

# copy project files
COPY mastodon-archiver.py .
COPY pyproject.toml .
COPY uv.lock . 

RUN uv sync --locked

RUN chmod +x mastodon-archiver.py

# run the archiver
CMD ["uv", "run", "mastodon-archiver.py"]
