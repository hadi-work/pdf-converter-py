#!/bin/bash
# macOS PDF Converter Setup - fully checked

echo "✅ Starting macOS PDF converter setup..."

# --- 1. Check pyenv ---
if ! command -v pyenv &> /dev/null; then
    echo "Installing pyenv..."
    brew install pyenv
else
    echo "pyenv already installed, skipping."
fi

# --- 2. Check Python 3.14 ---
if ! pyenv versions | grep -q "3.14"; then
    echo "Installing Python 3.14 via pyenv..."
    pyenv install 3.14.0
else
    echo "Python 3.14 already installed, skipping."
fi
pyenv local 3.14.0
echo "Using Python $(python --version)"

# --- 3. Check pip ---
if ! python -m pip --version &> /dev/null; then
    echo "Installing/upgrading pip..."
    python -m ensurepip --upgrade
else
    echo "pip already installed, skipping."
fi

# --- 4. Check GLib ---
if ! brew list glib &> /dev/null; then
    echo "Installing GLib..."
    brew install glib
else
    echo "GLib already installed, skipping."
fi

# --- 5. Check DejaVu fonts ---
if ! brew list --cask | grep -q font-dejavu; then
    echo "Installing DejaVu fonts..."
    brew tap homebrew/cask-fonts
    brew install --cask font-dejavu
else
    echo "DejaVu fonts already installed, skipping."
fi

# --- 6. Check LibreOffice ---
if ! command -v libreoffice &> /dev/null && ! command -v soffice &> /dev/null; then
    echo "LibreOffice not found. Please install LibreOffice manually."
else
    echo "LibreOffice found, skipping."
fi

# --- 7. Create virtual environment ---
if [ ! -d "pdf_env" ]; then
    echo "Creating Python virtual environment..."
    python -m venv pdf_env
else
    echo "Virtual environment already exists, skipping."
fi
source pdf_env/bin/activate

# --- 8. Upgrade pip inside venv ---
python -m pip install --upgrade pip

# --- 9. Install Python packages ---
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

# --- 10. Run FastAPI service ---
echo "Running FastAPI PDF converter on http://localhost:8000 ..."
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload