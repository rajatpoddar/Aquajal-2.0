# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container
COPY . .

# Make the entrypoint script executable
RUN chmod +x ./entrypoint.sh

# Expose the port the app runs on
EXPOSE 2942

# Define the command to run the application
ENTRYPOINT ["./entrypoint.sh"]
