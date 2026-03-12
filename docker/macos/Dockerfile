# Use Python 3.14 slim base image
FROM python:3.14-slim

# Set working directory
WORKDIR /app

# --- 1. Install system dependencies ---
# Note: macOS containers are usually Linux-based, so we install Debian/Ubuntu packages
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libgl1 \
    ttf-dejavu \
    libreoffice \
    wget \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# --- 2. Copy requirements and install Python packages ---
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- 3. Copy application code ---
COPY . .

# --- 4. Expose port ---
EXPOSE 8000

# --- 5. Run FastAPI app with multiple workers ---
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]