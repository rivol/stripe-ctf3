#!/bin/sh

set -e

# Add or modify any build steps you need here
cd "$(dirname "$0")"

pip install -r flask_server/requirements.txt
