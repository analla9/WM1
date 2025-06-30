# Base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies that might be needed by some Python packages
# (e.g., build-essential for C extensions, though sentence-transformers might not need it explicitly on slim)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (if a FastAPI health check or control API is implemented)
# EXPOSE 8000
# For now, this service is primarily a background worker.

# Command to run the knowledge ingester
CMD ["python", "main.py"]
