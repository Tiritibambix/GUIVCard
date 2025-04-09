# Use Python slim image
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        libssl-dev \
        curl \
        build-essential \
        python3-pip \
        python3-setuptools \
        python3-wheel && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and templates first for better caching
COPY requirements.txt .
COPY templates ./templates/

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy remaining application code
COPY app.py .

# Set environment variables
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "-u", "app.py"]