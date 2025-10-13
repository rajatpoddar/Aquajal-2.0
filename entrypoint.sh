#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Ensure the upload folder exists
echo "Ensuring upload directory exists..."
mkdir -p /app/app/static/uploads

# Run database migrations
echo "Running database migrations..."
flask db upgrade

# Seed the database with default users and business.
# The seeder script has a check to prevent duplicate entries.
echo "Seeding the database..."
flask seed-db

# Start Gunicorn server for production
echo "Starting Gunicorn server..."
exec gunicorn --bind 0.0.0.0:2942 --workers 4 "app:create_app()"