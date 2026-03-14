import os
import re
import uuid
import json
import base64
import asyncio
import tempfile
import subprocess
import httpx

from fastapi import UploadFile, File, Request
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

SUPPORTED_IMAGE_EXT = [".pdf", ".jpg", ".jpeg", ".jfif", ".jng", ".png"]

PORT = int(os.getenv("PORT", 3003))
MAX_REQUEST_SIZE = int(os.getenv("MAX_REQUEST_SIZE", 100 * 1024 * 1024))
MAX_RESPONSE_SIZE = int(os.getenv("MAX_RESPONSE_SIZE", 100 * 1024 * 1024))
DOCUMENT_PDF_CONVERTER = os.getenv("DOCUMENT_PDF_CONVERTER", "http://localhost:3333/convert")

PAGE_REGEX = re.compile(r"\d+")

# ---------------------------------------------------------
# This will require to install
# mutool
# ImageMagick
#
# UBUNTU: apt install mupdf-tools imagemagick
# ---------------------------------------------------------

# ---------------------------------------------------------
# Add below lines in main.py if you want to load this file
# from doc_image_endpoints import register_convert_endpoint, register_joinmetadata_endpoint
#
# register_convert_endpoint(app)
# register_joinmetadata_endpoint(app)
# ---------------------------------------------------------

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

async def convert_to_pdf_if_needed(file_bytes: bytes, ext: str):
    if ext in SUPPORTED_IMAGE_EXT:
        return file_bytes, ext

    async with httpx.AsyncClient(timeout=None) as client:
        files = {"file": ("file", file_bytes)}
        r = await client.post(DOCUMENT_PDF_CONVERTER, files=files)

        if r.status_code != 200:
            raise RuntimeError("PDF conversion service failed")

        return r.content, ".pdf"


async def get_pdf_pages(pdf_path: str):
    proc = await asyncio.create_subprocess_exec(
        "mutool", "pages", pdf_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    out, _ = await proc.communicate()
    txt = out.decode()

    match = re.search(r'pagenum="(\d+)"', txt)
    if not match:
        raise RuntimeError("Cannot detect page count")

    return int(match.group(1))


async def render_page(pdf_path, page, fmt, outdir):
    out_file = os.path.join(outdir, f"page-{page}.{fmt}")

    proc = await asyncio.create_subprocess_exec(
        "mutool",
        "draw",
        "-o", out_file,
        "-r", "125",
        pdf_path,
        str(page + 1),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    await proc.communicate()
    return out_file


async def imagemagick_convert(input_path, output_path):
    proc = await asyncio.create_subprocess_exec(
        "convert",
        "-limit", "memory", "64MiB",
        "-limit", "map", "128MiB",
        "-depth", "8",
        "-density", "125",
        input_path,
        output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    await proc.communicate()


def build_multipart(parts):
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
# /convert endpoint
# ---------------------------------------------------------

def register_convert_endpoint(app):

    @app.post("/convert")
    async def convert_endpoint(file: UploadFile = File(...), format: str = "png"):
        try:
            body = await file.read()

            ext = os.path.splitext(file.filename or "")[1].lower()

            pdf_bytes, ext = await convert_to_pdf_if_needed(body, ext)

            with tempfile.TemporaryDirectory() as tmp:

                if ext == ".pdf":

                    pdf_path = os.path.join(tmp, "input.pdf")

                    with open(pdf_path, "wb") as f:
                        f.write(pdf_bytes)

                    pages = await get_pdf_pages(pdf_path)

                    tasks = [
                        render_page(pdf_path, i, format, tmp)
                        for i in range(pages)
                    ]

                    results = await asyncio.gather(*tasks)

                    parts = []

                    for path in results:
                        name = os.path.basename(path)
                        page = PAGE_REGEX.search(name).group(0)

                        with open(path, "rb") as f:
                            parts.append((f"{page}.{format}", f.read()))

                    return build_multipart(parts)

                else:
                    input_path = os.path.join(tmp, "img")
                    output_path = os.path.join(tmp, f"page-0.{format}")

                    with open(input_path, "wb") as f:
                        f.write(body)

                    await imagemagick_convert(input_path, output_path)

                    with open(output_path, "rb") as f:
                        parts = [(f"0.{format}", f.read())]

                    return build_multipart(parts)

        except Exception as e:
            return JSONResponse(status_code=500, content={"message": str(e)})


# ---------------------------------------------------------
# /joinmetadata endpoint
# ---------------------------------------------------------

def register_joinmetadata_endpoint(app):

    @app.post("/joinmetadata")
    async def joinmetadata(request: Request):

        try:
            form = await request.form()

            upload = form["file"]
            metadata = json.loads(form["metadata"])

            file_bytes = await upload.read()

            ext = os.path.splitext(upload.filename or "")[1].lower()

            pdf_bytes, ext = await convert_to_pdf_if_needed(file_bytes, ext)

            with tempfile.TemporaryDirectory() as tmp:

                pdf_path = os.path.join(tmp, "input.pdf")

                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)

                images = []

                for item in metadata["items"]:

                    data = item["image"]
                    data = data.split(",")[1]

                    img_bytes = base64.b64decode(data)

                    img_path = os.path.join(tmp, f"{uuid.uuid4().hex}.png")

                    with open(img_path, "wb") as f:
                        f.write(img_bytes)

                    images.append((img_path, item["places"]))

                modified_pages = {}

                scale = 1.6

                for img_path, places in images:
                    for p in places:

                        page = p["page"]

                        width = int(p["width"] * scale)
                        height = int(p["height"] * scale)
                        x = int(p["x"] * scale)
                        y = int(p["y"] * scale)

                        out = os.path.join(tmp, f"page-{page}.pdf")

                        cmd = [
                            "convert",
                            "-limit", "memory", "64MiB",
                            "-limit", "map", "128MiB",
                            "-depth", "8",
                            "-density", "200",
                            f"{pdf_path}[{page}]",
                            img_path,
                            "-geometry", f"{width}x{height}+{x}+{y}",
                            "-composite",
                            out
                        ]

                        await asyncio.create_subprocess_exec(*cmd)

                        modified_pages[page] = out

                output = os.path.join(tmp, "output.pdf")

                pages = await get_pdf_pages(pdf_path)

                merge_cmd = ["mutool", "merge", "-o", output]

                for i in range(pages):

                    if i in modified_pages:
                        merge_cmd.append(modified_pages[i])
                    else:
                        merge_cmd.append(f"{pdf_path} {i+1}")

                proc = await asyncio.create_subprocess_exec(*merge_cmd)
                await proc.communicate()

                with open(output, "rb") as f:
                    parts = [("file", f.read())]

                return build_multipart(parts)

        except Exception as e:
            return JSONResponse(status_code=500, content={"message": str(e)})