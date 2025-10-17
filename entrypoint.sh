#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Wait for the database to be ready
echo "Waiting for database..."
while ! pg_isready -h "$POSTGRES_HOSTNAME" -p "5432" -q -U "$POSTGRES_USER"; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done
>&2 echo "Postgres is up - executing command"

# Ensure the upload folder exists
echo "Ensuring upload directory exists..."
mkdir -p /app/app/static/uploads

# Run database migrations
echo "Running database migrations..."
flask db upgrade

# Start Gunicorn server for production
echo "Starting Gunicorn server..."
exec gunicorn --bind 0.0.0.0:2942 "app:create_app()"