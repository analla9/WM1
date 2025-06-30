# Base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies (if any are strictly needed by Python packages)
# RUN apt-get update && apt-get install -y ... && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port for the FastAPI service
EXPOSE 8000

# Command to run the remediation service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
