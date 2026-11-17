"""Produce samples/sample_output.json from a *local fixture folder*.

A fake Drive serves generated files; the real PDF parser and real Tesseract
do the extraction. Use it when you have no Drive access. For the real thing,
see "Sample output" in the README.

    python -m scripts.generate_sample
"""

import asyncio
import json
import time
from pathlib import Path

import httpx

from app.config import Settings
from app.drive import DriveClient
from app.extraction import Extractor, OcrEngine
from app.jobs import JobManager
from tests.helpers import make_scanned_pdf, make_text_image, make_text_pdf

FOLDER_ID = "LOCAL_FIXTURE_FOLDER"
FILES = {
    "invoice-native.pdf": ("application/pdf", make_text_pdf("Invoice 2026-0042 Total 120.00 EUR")),
    "contract-scan.pdf": ("application/pdf", make_scanned_pdf("SCANNED CONTRACT 2026")),  # image only
    "receipt.png": ("image/png", make_text_image("RECEIPT 2026")),
    "photo.jpg": ("image/jpeg", make_text_image("HELLO DRIVE", "JPEG")),
    "broken.pdf": ("application/pdf", b"this is not a pdf"),
}


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/drive/v3/files":
        return httpx.Response(200, json={"files": [
            {"id": name, "name": name, "mimeType": mime, "size": str(len(data))}
            for name, (mime, data) in FILES.items()
        ]})
    return httpx.Response(200, content=FILES[request.url.path.rsplit("/", 1)[-1]][1])


async def main() -> None:
    settings = Settings(google_api_key="local-fixture")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    drive = DriveClient(http, settings.google_api_key, settings.max_file_bytes)

    ocr = OcrEngine()
    jobs = JobManager(drive, Extractor(settings, ocr), concurrency=2)
    job = jobs.submit(FOLDER_ID, await drive.list_folder(FOLDER_ID), ["eng"])
    while job.status.value != "completed":
        await asyncio.sleep(0.1)

    out = Path("samples/sample_output.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(job.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
