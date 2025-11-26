#!/bin/bash
#
# wrapper script for mastodon-archiver.py
# this script sources the .env file and runs the archiver using uv
# suitable for cron execution
#

set -euo pipefail

# ensure uv is in path (typically installed in ~/.local/bin)
export PATH="${HOME}/.local/bin:${PATH}"

# get the directory where this script resides
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# source the .env file from the script directory
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: .env file not found at ${ENV_FILE}" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

# change to the script directory to ensure uv uses the correct pyproject.toml
cd "${SCRIPT_DIR}"

# execute the archiver (uv will be invoked via shebang)
exec "${SCRIPT_DIR}/mastodon-archiver.py"
