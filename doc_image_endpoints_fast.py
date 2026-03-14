import os
import io
import uuid
import base64
import orjson
import fitz

from PIL import Image
from fastapi import UploadFile, File, Request
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.concurrency import run_in_threadpool


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
from utils import office_to_pdf_bytes, txt_to_pdf_bytes


# ---------------------------------------------------------
# Multipart Streaming Builder
# ---------------------------------------------------------

def multipart_stream(parts):

    boundary = f"boundary-{uuid.uuid4().hex}"

    async def stream():

        for name, data in parts:

            yield f"--{boundary}\r\n".encode()
            yield f'Content-Disposition: form-data; name="{name}"\r\n'.encode()
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

            parts = []

            for i, page in enumerate(doc):

                pix = page.get_pixmap(dpi=125)

                img_bytes = pix.tobytes(format)

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

            metadata = orjson.loads(form["metadata"])

            file_bytes = await upload.read()

            if not file_bytes:
                raise RuntimeError("Empty file")

            ext = os.path.splitext(upload.filename or "")[1].lower()

            pdf_bytes, ext = await ensure_pdf(file_bytes, ext)

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            scale = 1.6

            for item in metadata["items"]:

                image_data = item["image"]

                b64 = image_data.split(",")[1]

                img_bytes = base64.b64decode(b64)

                image = Image.open(io.BytesIO(img_bytes))

                for place in item["places"]:

                    page_number = place["page"]

                    page = doc.load_page(page_number)

                    width = int(place["width"] * scale)
                    height = int(place["height"] * scale)

                    x = int(place["x"] * scale)
                    y = int(place["y"] * scale)

                    image_resized = image.resize((width, height))

                    img_buf = io.BytesIO()

                    image_resized.save(img_buf, "PNG")

                    rect = fitz.Rect(x, y, x + width, y + height)

                    page.insert_image(rect, stream=img_buf.getvalue())

            output = io.BytesIO()

            doc.save(output)

            output.seek(0)

            return multipart_stream([
                ("file", output.read())
            ])

        except Exception as e:

            return JSONResponse(
                status_code=500,
                content={"message": str(e)}
            )