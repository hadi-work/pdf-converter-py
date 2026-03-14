#!/bin/bash
# Linux PDF Converter Setup - fully checked (Ubuntu/Debian)

echo "✅ Starting Linux PDF converter setup..."

# --- 1. Update system ---
sudo apt-get update -y

# --- 2. Check and install system dependencies ---
for pkg in software-properties-common wget curl build-essential libglib2.0-0 libgl1 ttf-dejavu libreoffice; do
    if ! dpkg -s $pkg &> /dev/null; then
        echo "Installing $pkg..."
        sudo apt-get install -y $pkg
    else
        echo "$pkg already installed, skipping."
    fi
done

# --- 3. Check Python 3.14 ---
if ! python3.14 --version &> /dev/null; then
    echo "Installing Python 3.14 via deadsnakes PPA..."
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt-get update -y
    sudo apt-get install -y python3.14 python3.14-venv python3.14-dev python3.14-distutils
else
    echo "Python 3.14 already installed, skipping."
fi

# --- 4. Create virtual environment ---
if [ ! -d "pdf_env" ]; then
    python3.14 -m venv pdf_env
    echo "Virtual environment created at pdf_env"
else
    echo "Virtual environment already exists, skipping."
fi
source pdf_env/bin/activate

# --- 5. Upgrade pip inside venv ---
python -m pip install --upgrade pip

# --- 6. Install Python dependencies ---
cat <<EOF > requirements.txt
fastapi
uvicorn[standard]
python-multipart
python-docx
filetype
reportlab
arabic-reshaper
python-bidi
pypdf
EOF

echo "Installing Python packages..."
python -m pip install --no-cache-dir -r requirements.txt

# --- 7. Check LibreOffice path ---
if ! command -v libreoffice &> /dev/null && ! command -v soffice &> /dev/null; then
    echo "LibreOffice not found. Please install LibreOffice manually."
else
    echo "LibreOffice found, skipping."
fi

# --- 8. Run FastAPI service ---
echo "Running FastAPI PDF converter on http://localhost:8000 ..."
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload