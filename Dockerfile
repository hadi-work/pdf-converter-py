# Use official Python 3.14 slim image
FROM python:3.14-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies for LibreOffice + fonts
RUN apt-get update && apt-get install -y \
    libreoffice \
    fonts-dejavu \
    ttf-dejavu \
    libgl1 \
    libglib2.0-0 \
    wget \
    unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY . .

# Ensure fonts folder exists
RUN mkdir -p /app/fonts

# Expose FastAPI port
EXPOSE 8000

# Command to start FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]