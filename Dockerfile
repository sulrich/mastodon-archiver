FROM python:3.11-slim

# install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# set working directory
WORKDIR /app

# copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy the archiver script
COPY mastodon-archiver.py .
RUN chmod +x mastodon-archiver.py

# create non-root user for security
RUN groupadd -r archiver && useradd -r -g archiver archiver
RUN mkdir -p /archive && chown -R archiver:archiver /archive /app
USER archiver

# run the archiver
CMD ["python", "mastodon-archiver.py"]
