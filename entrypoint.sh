#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Run database migrations
echo "Running database migrations..."
flask db upgrade

# Seed the database with default users and business.
# The seeder script has a check to prevent duplicate entries.
echo "Seeding the database..."
flask seed-db

# Start Gunicorn server
echo "Starting Gunicorn server..."
exec gunicorn --bind 0.0.0.0:2942 --workers 4 "app:create_app()"

