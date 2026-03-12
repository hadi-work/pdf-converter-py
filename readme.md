Absolutely! Here’s an **updated and fully detailed README.md** that includes **LibreOffice installation, dependencies, and system setup steps** for Mac and Linux, alongside all the existing instructions.

---

# Ultra-Fast PDF Converter

**Description:**
This service converts `TXT`, `DOCX`, `DOC`, and `PDF` files into PDF format, with **full Arabic support**. It preserves formatting for Office files using **LibreOffice headless** and supports right-to-left Arabic orientation for text files.

It provides two endpoints:

1. `/convert-buffer` – returns PDF as a buffer (inline).
2. `/download-pdf` – returns PDF as a downloadable file.

---

## Folder Structure

```text
├─ main.py
├─ requirements.txt
├─ Dockerfile
├─ docker-compose.yml
├─ fonts/
│   └─ DejaVuSans.ttf
├─ .gitignore
```

---

## 1️⃣ Prerequisites

### System Requirements

* **MacOS or Linux**
* **Docker & Docker Compose** (optional, recommended)
* **Python 3.14** (if running locally outside Docker)

### Required Packages

For Linux:

```bash
sudo apt update
sudo apt install -y libreoffice libgl1 libglib2.0-0 ttf-dejavu fontconfig
```

For MacOS using Homebrew:

```bash
brew install libreoffice
brew tap homebrew/cask-fonts
brew install --cask font-dejavu
```

These packages ensure that:

* LibreOffice can run headless for DOC/DOCX/DOC → PDF conversions
* DejaVuSans font is available for Arabic/Unicode text rendering
* OpenGL & font libraries are available for PDF generation

---

## 2️⃣ Installing Fonts

Place the **DejaVuSans.ttf** font (supports Arabic) in the `fonts/` folder:

```text
fonts/DejaVuSans.ttf
```

This font is required for right-to-left Arabic rendering in TXT files.

---

## 3️⃣ Installing Python Dependencies

**requirements.txt:**

```text
fastapi
uvicorn
python-multipart
filetype
arabic-reshaper
bidi
reportlab
```

Install locally:

```bash
pip install -r requirements.txt
```

---

## 4️⃣ Running Locally with Docker

### Step 1: Build Docker Image

```bash
docker-compose build
```

or without Docker Compose:

```bash
docker build -t pdf-converter:latest .
```

### Step 2: Run the Container

With Docker Compose:

```bash
docker-compose up
```

Without Docker Compose:

```bash
docker run -d -p 8000:8000 --name pdf-service pdf-converter:latest
```

### Step 3: Access FastAPI Docs

Open your browser:

```text
http://localhost:8000/docs
```

---

## 5️⃣ Using the API

### Endpoint 1: Convert Buffer

* **URL:** `/convert-buffer`
* **Method:** `POST`
* **Request:** Upload `TXT`, `DOCX`, `DOC`, or `PDF` file as form-data
* **Response:** PDF content returned in response body

**Example using `curl`:**

```bash
curl -X POST "http://localhost:8000/convert-buffer" \
  -F "file=@/path/to/file.docx" \
  -o output.pdf
```

---

### Endpoint 2: Download PDF

* **URL:** `/download-pdf`
* **Method:** `POST`
* **Request:** Upload `TXT`, `DOCX`, `DOC`, or `PDF` file as form-data
* **Response:** PDF is returned as a downloadable file, preserving original filename and supporting Unicode characters

**Example using `curl`:**

```bash
curl -X POST "http://localhost:8000/download-pdf" \
  -F "file=@/path/to/file.docx" \
  -O
```

> The `-O` flag saves the file with the original name returned by the API.

---

## 6️⃣ Docker Notes

* LibreOffice is installed in the container for DOC/DOCX/DOC → PDF conversion
* DejaVuSans.ttf is used for Arabic support in TXT files
* The container exposes port `8000`

---

## 7️⃣ Kubernetes Deployment

Create a `k8s-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pdf-converter
spec:
  replicas: 1
  selector:
    matchLabels:
      app: pdf-converter
  template:
    metadata:
      labels:
        app: pdf-converter
    spec:
      containers:
        - name: pdf-converter
          image: pdf-converter:latest
          ports:
            - containerPort: 8000
          resources:
            limits:
              memory: "512Mi"
              cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: pdf-converter-service
spec:
  selector:
    app: pdf-converter
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
  type: LoadBalancer
```

Deploy:

```bash
kubectl apply -f k8s-deployment.yaml
```

Access service using external IP or port forwarding:

```bash
kubectl port-forward svc/pdf-converter-service 8000:80
```

---

## 8️⃣ Notes & Troubleshooting

* Ensure **LibreOffice** is installed and available in PATH inside the container
* Ensure `fonts/DejaVuSans.ttf` exists for Arabic text
* Arabic text in TXT files is reshaped and rendered **right-to-left**
* DOC/DOCX/DOC conversion preserves formatting as in original Office file
* For large DOC files, the conversion may take a few seconds

---

## 9️⃣ Optional: `.gitignore`

```gitignore
__pycache__/
*.pyc
*.pyo
*.pyd
venv/
env/
pdf_env/
.env
*.log
build/
dist/
*.egg-info/
docker-compose.override.yml
.vscode/
.idea/
*.DS_Store
```