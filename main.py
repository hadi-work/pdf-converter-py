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
import shutil

# Arabic PDF support for TXT
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = FastAPI(title="Ultra-Fast PDF Converter Full Office Support with Swagger")

# --- Font path for Arabic/Unicode TXT ---
ARABIC_FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf")
if not os.path.exists(ARABIC_FONT_PATH):
    raise RuntimeError(f"Arabic font not found at {ARABIC_FONT_PATH}")
pdfmetrics.registerFont(TTFont("DejaVu", ARABIC_FONT_PATH))

# --- Auto-detect LibreOffice executable ---
LIBREOFFICE_PATH = shutil.which("libreoffice") or shutil.which("soffice")
if not LIBREOFFICE_PATH:
    raise RuntimeError("LibreOffice executable not found. Install it and ensure it's in PATH.")

# --- TXT → PDF ---
def txt_to_pdf_bytes(file_bytes: bytes) -> bytes:
    text = file_bytes.decode("utf-8")
    pdf_buffer = BytesIO()
    c = canvas.Canvas(pdf_buffer)
    c.setFont("DejaVu", 14)
    page_width = 595
    right_margin = page_width - 50
    y = 800
    for line in text.split("\n"):
        reshaped_text = arabic_reshaper.reshape(line)
        bidi_text = get_display(reshaped_text)
        c.drawRightString(right_margin, y, bidi_text)
        y -= 20
    c.save()
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()

# --- DOC/DOCX/DOC → PDF via LibreOffice ---
def office_to_pdf_bytes(file_bytes: bytes, ext: str) -> bytes:
    suffix = f".{ext}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
        tmp_file.write(file_bytes)
        tmp_file_path = tmp_file.name

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            subprocess.run([
                LIBREOFFICE_PATH,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", tmp_dir,
                tmp_file_path
            ], check=True)

            pdf_file = next((f for f in os.listdir(tmp_dir) if f.endswith(".pdf")), None)
            if not pdf_file:
                raise HTTPException(status_code=500, detail="LibreOffice conversion failed")
            pdf_path = os.path.join(tmp_dir, pdf_file)
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
        return pdf_bytes
    finally:
        os.unlink(tmp_file_path)

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