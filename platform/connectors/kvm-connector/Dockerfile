# Base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install build dependencies for libvirt-python and libvirt client
# libvirt-dev provides headers, pkg-config helps find them
# libvirt-clients provides virsh for potential debugging inside container (optional)
RUN apt-get update && apt-get install -y \
    pkg-config \
    libvirt-dev \
    libvirt-clients \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt requirements.txt

# Install Python dependencies
# Ensure C_INCLUDE_PATH is set if headers are not in default locations,
# though libvirt-dev should handle this for standard installs.
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Command to run the KVM connector
CMD ["python", "main.py"]
