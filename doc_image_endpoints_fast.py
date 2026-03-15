import os
import io
import uuid
import base64
import orjson
import fitz

from PIL import Image
from fastapi import UploadFile, File, Request, Form
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
# -----------------------------------------------------
# pip install pymupdf pillow httpx orjson
# -----------------------------------------------------
# -----------------------------------------------------
# Add below lines in main.py if you want to load this file
# from doc_image_endpoints_fast import (
#     register_convert_endpoint,
#     register_joinmetadata_endpoint
# )
#
# register_convert_endpoint(app)
# register_joinmetadata_endpoint(app)
# -----------------------------------------------------


# ---------------------------------------------------------
# Supported extensions that don't require PDF conversion
# ---------------------------------------------------------

SUPPORTED_IMAGE_EXT = [".pdf", ".jpg", ".jpeg", ".jfif", ".jng", ".png"]


# ---------------------------------------------------------
# Import existing conversion logic from your project
# ---------------------------------------------------------

# ⚠️ Change "main" to your actual file name if different
from utils import office_to_pdf_bytes, txt_to_pdf_bytes, is_base64


# ---------------------------------------------------------
# Multipart Streaming Builder
# ---------------------------------------------------------

def multipart_stream(parts):

    boundary = f"boundary-{uuid.uuid4().hex}"

    async def stream():

        for name, data in parts:

            yield f"--{boundary}\r\n".encode()
            # yield f'Content-Disposition: form-data; name="{name}"\r\n'.encode()
            yield f'Content-Disposition: form-data; name="{name}"; filename="{name}"\r\n'.encode()
            yield b"Content-Type: application/octet-stream\r\n\r\n"

            yield data
            yield b"\r\n"

        yield f"--{boundary}--\r\n".encode()

    return StreamingResponse(
        stream(),
        media_type=f"multipart/form-data; boundary={boundary}"
    )


# ---------------------------------------------------------
# Ensure file is PDF if required
# ---------------------------------------------------------

async def ensure_pdf(file_bytes: bytes, ext: str):

    if ext in SUPPORTED_IMAGE_EXT:
        return file_bytes, ext

    ext_clean = ext.lstrip(".").lower()

    if ext_clean in ["doc", "docx"]:
        pdf_bytes = await run_in_threadpool(
            office_to_pdf_bytes,
            file_bytes,
            ext_clean
        )
        return pdf_bytes, ".pdf"

    if ext_clean in ["txt", "text"]:
        pdf_bytes = await run_in_threadpool(
            txt_to_pdf_bytes,
            file_bytes
        )
        return pdf_bytes, ".pdf"

    raise RuntimeError(f"Unsupported file type: {ext}")


# ---------------------------------------------------------
# Convert image bytes
# ---------------------------------------------------------

def convert_image_bytes(image_bytes, fmt):

    img = Image.open(io.BytesIO(image_bytes))

    if fmt.lower() in ["jpg", "jpeg"] and img.mode in ("RGBA", "LA"):
        img = img.convert("RGB")

    buf = io.BytesIO()

    img.save(buf, fmt.upper())

    return buf.getvalue()

# ---------------------------------------------------------
# Register /convert endpoint
# ---------------------------------------------------------

def register_convert_endpoint(app):

    @app.post("/convert")
    async def convert_endpoint(file: UploadFile = File(...), format: str = "png"):

        try:

            body = await file.read()

            if not body:
                raise RuntimeError("Empty file")

            if len(body) > MAX_FILE_SIZE:
                raise RuntimeError("File too large")

            ALLOWED_FORMATS = {"png", "jpg", "jpeg"}

            if format.lower() not in ALLOWED_FORMATS:
                raise RuntimeError("Unsupported output format")

            ext = os.path.splitext(file.filename or "")[1].lower()

            file_bytes, ext = await ensure_pdf(body, ext)

            # ---------- IMAGE INPUT ----------

            if ext != ".pdf":

                img_bytes = convert_image_bytes(file_bytes, format)

                return multipart_stream([
                    (f"0.{format}", img_bytes)
                ])

            # ---------- PDF INPUT ----------

            doc = fitz.open(stream=file_bytes, filetype="pdf")
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                parts = []

                for i, page in enumerate(doc):

                    pix = page.get_pixmap(dpi=125)

                    # img_bytes = pix.tobytes(format)
                    img_bytes = pix.tobytes(output=format)

                    parts.append((f"{i}.{format}", img_bytes))

                return multipart_stream(parts)

        except Exception as e:

            return JSONResponse(
                status_code=500,
                content={"message": str(e)}
            )


# ---------------------------------------------------------
# Register /joinmetadata endpoint
# ---------------------------------------------------------

def register_joinmetadata_endpoint(app):

    @app.post("/joinmetadata")
    async def joinmetadata(request: Request):
        try:
            form = await request.form()
            upload = form["file"]
            metadata_str = form["metadata"]

            # Parse metadata safely
            if not metadata_str or not metadata_str.strip():
                return JSONResponse(status_code=400, content={"message": "Empty metadata field"})
            try:
                metadata = orjson.loads(metadata_str.strip())
            except Exception as e:
                return JSONResponse(status_code=400, content={"message": f"Invalid JSON in metadata: {str(e)}"})

            # Read file bytes
            file_bytes = await upload.read()
            if not file_bytes:
                raise RuntimeError("Empty file")

            ext = os.path.splitext(upload.filename or "")[1].lower()
            pdf_bytes, ext = await ensure_pdf(file_bytes, ext)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = doc.page_count
            if total_pages == 0:
                return JSONResponse(status_code=400, content={"message": "Converted PDF has no pages"})

            # scale = 1.6
            scale = 72 / 125  # scale factor from 125->200 dpi

            # Insert images
            for item in metadata.get("items", []):
                image_data = item.get("image", "")
                if is_base64(image_data):
                    b64 = image_data
                elif "," in image_data:
                    b64 = image_data.split(",")[1]
                elif ";" in image_data:
                    b64 = image_data.split(";")[1]
                else:
                    return JSONResponse(status_code=400, content={"message": "Invalid image data (missing base64)"})
                if not b64.strip():
                    return JSONResponse(status_code=400, content={"message": "Empty base64 image data"})

                img_bytes = base64.b64decode(b64)
                image = Image.open(io.BytesIO(img_bytes))

                # Force RGB to remove transparency
                if image.mode != "RGB":
                    image = image.convert("RGB")

                for place in item.get("places", []):
                    page_number = place.get("page") + 1
                    if not isinstance(page_number, int):
                        return JSONResponse(status_code=400, content={"message": "Invalid page number type"})
                    if page_number < 1 or page_number > total_pages:
                        return JSONResponse(
                            status_code=400,
                            content={"message": f"Invalid page number {page_number}, PDF has {total_pages} pages"}
                        )

                    page = doc.load_page(page_number - 1)

                    x = float(place.get("x", 0)) * scale
                    y = float(place.get("y", 0)) * scale
                    width = float(place.get("width", 0)) * scale
                    height = float(place.get("height", 0)) * scale

                    if width < 2 or height < 2:
                        continue

                    rect = fitz.Rect(x, y, x + width, y + height)

                    page.insert_image(
                        rect,
                        stream=img_bytes
                    )

            # Save PDF to memory
            output = io.BytesIO()
            doc.save(output)
            output.seek(0)

            # Return in existing multipart/form-data format
            return multipart_stream([
                ("file", output.read())
            ])

        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"message": str(e)}
            )

import zipfile
from fastapi.responses import StreamingResponse


# ---------------------------------------------------------
# Helper: Convert PDF bytes to PNG pages
# ---------------------------------------------------------

def pdf_to_png_zip(pdf_bytes: bytes):

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

        for i, page in enumerate(doc):

            pix = page.get_pixmap(dpi=125)

            img_bytes = pix.tobytes("png")

            zipf.writestr(f"{i}.png", img_bytes)

    zip_buffer.seek(0)

    return zip_buffer


# ---------------------------------------------------------
# Register /convert-download
# ---------------------------------------------------------

def register_convert_download_endpoint(app):

    @app.post("/convert-download")
    async def convert_download(file: UploadFile = File(...), format: str = "png"):

        try:

            body = await file.read()

            if not body:
                raise RuntimeError("Empty file")

            ext = os.path.splitext(file.filename or "")[1].lower()

            file_bytes, ext = await ensure_pdf(body, ext)

            # ---------- IMAGE INPUT ----------

            if ext != ".pdf":

                img_bytes = convert_image_bytes(file_bytes, "png")

                zip_buffer = io.BytesIO()

                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                    zipf.writestr("0.png", img_bytes)

                zip_buffer.seek(0)

                return StreamingResponse(
                    zip_buffer,
                    media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=images.zip"}
                )

            # ---------- PDF INPUT ----------

            zip_buffer = pdf_to_png_zip(file_bytes)

            return StreamingResponse(
                zip_buffer,
                media_type="application/zip",
                headers={"Content-Disposition": "attachment; filename=images.zip"}
            )

        except Exception as e:

            return JSONResponse(
                status_code=500,
                content={"message": str(e)}
            )


# ---------------------------------------------------------
# Register /joinmetadata-download
# ---------------------------------------------------------

def register_joinmetadata_download_endpoint(app):

    @app.post("/joinmetadata-download")
    async def joinmetadata_download(
        file: UploadFile = File(...),
        metadata: str = Form(...)
    ):
        try:
            # Read uploaded file
            file_bytes = await file.read()
            if not file_bytes:
                return JSONResponse(status_code=400, content={"message": "Empty file"})

            # Parse metadata safely
            if not metadata or not metadata.strip():
                return JSONResponse(status_code=400, content={"message": "Empty metadata field"})
            try:
                metadata_json = orjson.loads(metadata.strip())
            except Exception as e:
                return JSONResponse(status_code=400, content={"message": f"Invalid JSON in metadata: {str(e)}"})

            # Ensure PDF using your existing function
            ext = os.path.splitext(file.filename or "")[1].lower()
            pdf_bytes, ext = await ensure_pdf(file_bytes, ext)  # must return PDF bytes

            # Open PDF with PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = doc.page_count
            if total_pages == 0:
                return JSONResponse(status_code=400, content={"message": "Converted PDF has no pages"})

            scale = 72 / 125  # scale factor from 125->200 dpi

            # Insert images
            for item in metadata_json.get("items", []):
                image_data = item.get("image", "")

                if is_base64(image_data):
                    b64 = image_data
                elif "," in image_data:
                    b64 = image_data.split(",")[1]
                elif ";" in image_data:
                    b64 = image_data.split(";")[1]
                else:
                    return JSONResponse(status_code=400, content={"message": "Invalid image data (missing base64)"})
                if not b64.strip():
                    return JSONResponse(status_code=400, content={"message": "Empty base64 image data"})
                img_bytes = base64.b64decode(b64)

                image = Image.open(io.BytesIO(img_bytes))

                # Force RGB to remove transparency
                if image.mode != "RGB":
                    image = image.convert("RGB")

                for place in item.get("places", []):

                    page_number = place.get("page") + 1

                    if page_number < 1 or page_number > total_pages:
                        continue

                    page = doc.load_page(page_number - 1)

                    x = float(place.get("x", 0)) * scale
                    y = float(place.get("y", 0)) * scale
                    width = float(place.get("width", 0)) * scale
                    height = float(place.get("height", 0)) * scale

                    if width < 2 or height < 2:
                        continue

                    rect = fitz.Rect(x, y, x + width, y + height)

                    page.insert_image(
                        rect,
                        stream=img_bytes
                    )

            # Save PDF to memory
            output_pdf = io.BytesIO()
            # doc.save(output_pdf)
            doc.save(
                output_pdf,
                garbage=4,
                deflate=True
            )
            doc.close()

            output_pdf.seek(0)

            # Convert PDF pages to PNG ZIP
            zip_buffer = io.BytesIO()
            pdf_for_png = fitz.open(stream=output_pdf.read(), filetype="pdf")
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for i, page in enumerate(pdf_for_png):
                    pix = page.get_pixmap(dpi=125)
                    img_bytes = pix.tobytes("png")
                    zipf.writestr(f"{i}.png", img_bytes)

            zip_buffer.seek(0)

            # Return ZIP download
            return StreamingResponse(
                zip_buffer,
                media_type="application/zip",
                headers={"Content-Disposition": "attachment; filename=pages.zip"}
            )

        except Exception as e:
            return JSONResponse(status_code=500, content={"message": str(e)})