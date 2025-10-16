#!/bin/bash

# --- CONFIGURATION ---
APP_DIR="/volume1/docker/Projects/Aquajal2.0"
UPLOAD_DIR="$APP_DIR/app/static/upload"
ENV_FILE="$APP_DIR/.env"
ENV_TEMPLATE="$APP_DIR/.env.template"

# --- SCRIPT LOGIC ---
echo "Starting deployment script at $(date)"

# Navigate to the app directory
cd "$APP_DIR" || { echo "Error: Could not navigate to $APP_DIR. Aborting."; exit 1; }

# Pull the latest code from GitHub
echo "Pulling latest code from GitHub..."
git pull origin main

# --- Ensure required files and folders exist ---

# 1. Create the upload directory if it doesn't exist
if [ ! -d "$UPLOAD_DIR" ]; then
  echo "Upload directory not found. Creating it..."
  mkdir -p "$UPLOAD_DIR"
fi

# 2. Create the .env file from the template if it doesn't exist
if [ ! -f "$ENV_FILE" ]; then
  echo ".env file not found. Creating from template..."
  cp "$ENV_TEMPLATE" "$ENV_FILE"
  echo "IMPORTANT: You MUST manually edit the new .env file with your secrets!"
fi

# --- Rebuild and restart Docker containers ---
echo "Rebuilding and restarting Docker containers..."
sudo docker-compose down
sudo docker-compose up -d --build

# Optional: Clean up old, unused Docker images to save space
sudo docker image prune -f

echo "Deployment finished successfully at $(date)."
echo "----------------------------------------------------"