from fastapi import HTTPException
from io import BytesIO
import subprocess
import tempfile
import os
import shutil


# Arabic PDF support for TXT
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfgen import canvas

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