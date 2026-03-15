from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from fastapi.openapi.utils import get_openapi
from io import BytesIO
import filetype
from starlette.concurrency import run_in_threadpool
import subprocess
import tempfile
import os
from urllib.parse import quote

# Arabic PDF support for TXT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# Document read
from fastapi.responses import JSONResponse
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET
from pypdf import PdfReader

from utils import office_to_pdf_bytes, txt_to_pdf_bytes

app = FastAPI(title="Ultra-Fast PDF Converter Full Office Support with Swagger")

# Document convert to png

from doc_image_endpoints_fast import (
    register_convert_endpoint,
    register_joinmetadata_endpoint,
    register_convert_download_endpoint,
    register_joinmetadata_download_endpoint
)

register_convert_endpoint(app)
register_joinmetadata_endpoint(app)
register_convert_download_endpoint(app)
register_joinmetadata_download_endpoint(app)


# --- Font path for Arabic/Unicode TXT ---
ARABIC_FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf")
if not os.path.exists(ARABIC_FONT_PATH):
    raise RuntimeError(f"Arabic font not found at {ARABIC_FONT_PATH}")
pdfmetrics.registerFont(TTFont("DejaVu", ARABIC_FONT_PATH))

# --- /convert-buffer endpoint ---
@app.post("/convert-buffer", response_description="PDF file buffer")
async def convert_buffer(file: UploadFile = File(...)):
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty file")

    kind = filetype.guess(body)
    file_type = kind.extension.lower() if kind else "txt"

    if file_type == "pdf":
        return Response(content=body, media_type="application/pdf")

    try:
        if file_type in ["docx", "doc"]:
            pdf_bytes = await run_in_threadpool(office_to_pdf_bytes, body, file_type)
        elif file_type in ["txt", "text"]:
            pdf_bytes = await run_in_threadpool(txt_to_pdf_bytes, body)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"LibreOffice conversion error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")

    return Response(content=pdf_bytes, media_type="application/pdf")

# --- /download-pdf endpoint ---
@app.post("/download-pdf", response_description="PDF file download")
async def download_pdf(file: UploadFile = File(...)):
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty file")

    kind = filetype.guess(body)
    file_type = kind.extension.lower() if kind else "txt"
    original_name = os.path.splitext(file.filename)[0] if file.filename else "file"
    download_filename = f"{original_name}.pdf"

    if file_type == "pdf":
        pdf_bytes = body
    else:
        try:
            if file_type in ["docx", "doc"]:
                pdf_bytes = await run_in_threadpool(office_to_pdf_bytes, body, file_type)
            elif file_type in ["txt", "text"]:
                pdf_bytes = await run_in_threadpool(txt_to_pdf_bytes, body)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"LibreOffice conversion error: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")

    quoted_filename = quote(download_filename)
    content_disposition = f"attachment; filename*=UTF-8''{quoted_filename}"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition}
    )

##########################################################################################################

# Document read to Plain text

# --- TXT → plain text ---
def txt_to_text(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="ignore")

# --- DOCX → plain text ---
def docx_to_text(file_bytes: bytes) -> str:
    def extract_paragraphs(xml_bytes: bytes) -> list[str]:
        root = ET.fromstring(xml_bytes)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []

        for paragraph in root.findall(".//w:p", ns):
            texts = [node.text for node in paragraph.findall(".//w:t", ns) if node.text]
            if texts:
                paragraphs.append("".join(texts))

        return paragraphs

    collected = []

    with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
        xml_names = [
            name for name in zf.namelist()
            if name == "word/document.xml"
            or name.startswith("word/header")
            or name.startswith("word/footer")
        ]

        for xml_name in xml_names:
            with zf.open(xml_name) as xml_file:
                collected.extend(extract_paragraphs(xml_file.read()))

    return "\n".join(collected)

# --- DOC/DOCX → plain text via LibreOffice ---
def office_to_text(file_bytes: bytes, ext: str) -> str:
    suffix = f".{ext}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
        tmp_file.write(file_bytes)
        tmp_file_path = tmp_file.name

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            subprocess.run([
                LIBREOFFICE_PATH,
                "--headless",
                "--convert-to", "txt:Text",
                "--outdir", tmp_dir,
                tmp_file_path
            ], check=True)

            txt_file = next((f for f in os.listdir(tmp_dir) if f.endswith(".txt")), None)
            if not txt_file:
                raise HTTPException(status_code=500, detail="LibreOffice text extraction failed")

            txt_path = os.path.join(tmp_dir, txt_file)
            with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    finally:
        os.unlink(tmp_file_path)

# --- PDF → plain text ---
def pdf_to_text(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages_text = []

    for page in reader.pages:
        pages_text.append(page.extract_text() or "")

    return "\n".join(pages_text).strip()


# --- /extract-text endpoint ---
@app.post("/extract-text", response_description="Extract plain text from uploaded document")
async def extract_text(file: UploadFile = File(...)):
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty file")

    kind = filetype.guess(body)
    detected_type = kind.extension.lower() if kind else None
    file_ext = Path(file.filename).suffix.lower().lstrip(".") if file.filename else ""
    file_type = detected_type or file_ext or "txt"

    try:
        if file_type == "pdf":
            text = await run_in_threadpool(pdf_to_text, body)
        elif file_type == "docx":
            try:
                text = await run_in_threadpool(docx_to_text, body)
            except Exception:
                text = await run_in_threadpool(office_to_text, body, file_type)
        elif file_type == "doc":
            text = await run_in_threadpool(office_to_text, body, file_type)
        elif file_type in ["txt", "text"]:
            text = await run_in_threadpool(txt_to_text, body)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"LibreOffice extraction error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text extraction error: {str(e)}")

    return JSONResponse(
        content={
            "filename": file.filename,
            "file_type": file_type,
            "text": text,
            "length": len(text),
            "supports_arabic": True
        }
    )




# --- Custom Swagger/OpenAPI ---
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Ultra-Fast PDF Converter API",
        version="1.0.0",
        description="DOC/DOCX preserve formatting via LibreOffice. TXT uses ReportLab with Arabic support.",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi