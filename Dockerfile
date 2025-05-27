FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages (ensure job-queue support)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Optional: Copy .env if it exists (for local builds only)
# In production, use Docker secrets or --env-file
# COPY .env . || echo ".env not found, continuing..."

# Create temp directory
RUN mkdir -p /tmp/telegram_bot

# Define default command
CMD ["python", "main.py"]
