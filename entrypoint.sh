#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Run database migrations
flask db upgrade

# Start Gunicorn server
exec gunicorn --bind 0.0.0.0:2942 --workers 4 "app:create_app()"
