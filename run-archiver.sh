#!/bin/bash
#
# Wrapper script for mastodon-archiver.py
# This script sources the .env file and runs the archiver using uv
# Suitable for cron execution
#

set -euo pipefail

# Get the directory where this script resides
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the .env file from the script directory
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: .env file not found at ${ENV_FILE}" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

# Export required environment variables
export MASTODON_BASE_URL
export MASTODON_ACCESS_TOKEN
export ARCHIVE_DIR

# Change to the script directory to ensure uv uses the correct pyproject.toml
cd "${SCRIPT_DIR}"

# Run the archiver using uv
exec uv run "${SCRIPT_DIR}/mastodon-archiver.py"
