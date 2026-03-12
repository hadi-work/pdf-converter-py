# Use official Python 3.14 slim image
FROM python:3.14-slim

# Set working directory
WORKDIR /app

# --- 1. Install system dependencies ---
RUN apt-get update && apt-get install -y \
    software-properties-common \
    wget \
    curl \
    build-essential \
    libglib2.0-0 \
    libgl1 \
    ttf-dejavu \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

# --- 2. Copy requirements and install Python packages ---
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- 3. Copy the application code ---
COPY . .

# --- 4. Expose port ---
EXPOSE 8000

# --- 5. Run the FastAPI app with multiple workers ---
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]