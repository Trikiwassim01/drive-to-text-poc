"""End-to-end through the HTTP API with a fake Google Drive and a fake OCR engine."""

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from .helpers import make_blank_pdf, make_text_pdf

FOLDER = "1AbCdEfGhIjKlMnOpQrStUv"
URL = f"https://drive.google.com/drive/folders/{FOLDER}"

CONTENT = {
    "pdf1": make_text_pdf("Native PDF with a text layer"),
    "scan1": make_blank_pdf(),
    "img1": b"image-bytes",
    "bad1": b"this is not a pdf",
}
LISTING = [
    {"id": "pdf1", "name": "native.pdf", "mimeType": "application/pdf", "size": "1000"},
    {"id": "scan1", "name": "scan.pdf", "mimeType": "application/pdf", "size": "1000"},
    {"id": "img1", "name": "photo.png", "mimeType": "image/png", "size": "11"},
    {"id": "bad1", "name": "broken.pdf", "mimeType": "application/pdf", "size": "17"},
    {"id": "txt1", "name": "notes.txt", "mimeType": "text/plain", "size": "3"},
]


class FakeOcr:
    def available_languages(self):
        return ["eng", "fra"]

    def validate_languages(self, languages):
        return list(languages or ["eng"])

    def image_to_text(self, image, languages):
        return "scanned text"

    def bytes_to_text(self, data, languages):
        return "image text"


def fake_drive(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/drive/v3/files":
        return httpx.Response(200, json={"files": LISTING})
    file_id = path.rsplit("/", 1)[-1]
    if file_id in CONTENT:
        return httpx.Response(200, content=CONTENT[file_id])
    return httpx.Response(404)


@pytest.fixture
def client():
    app = create_app(
        Settings(google_api_key="k", max_files_per_batch=10),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(fake_drive)),
        ocr=FakeOcr(),
    )
    with TestClient(app) as test_client:
        yield test_client


def wait_for(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] == "completed":
            return job
        time.sleep(0.05)
    raise AssertionError("job did not complete")


def test_listing_keeps_only_pdfs_and_images(client):
    body = client.post("/api/folders/list", json={"url": URL}).json()
    assert body["folder_id"] == FOLDER
    assert [f["name"] for f in body["files"]] == ["broken.pdf", "native.pdf", "photo.png", "scan.pdf"]


def test_invalid_link_returns_clear_error(client):
    response = client.post("/api/folders/list", json={"url": "https://example.com/x"})
    assert response.status_code == 400
    assert "drive.google.com" in response.json()["detail"]


def test_private_folder_returns_404_message():
    app = create_app(
        Settings(google_api_key="k"),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))),
        ocr=FakeOcr(),
    )
    with TestClient(app) as client:
        response = client.post("/api/folders/list", json={"url": URL})
    assert response.status_code == 404
    assert "not public" in response.json()["detail"]


def test_batch_continues_after_a_failing_file_and_routes_each_file(client):
    job_id = client.post(
        "/api/jobs",
        json={"url": URL, "file_ids": ["pdf1", "scan1", "img1", "bad1"], "languages": ["eng"]},
    ).json()["job_id"]
    job = wait_for(client, job_id)
    by_name = {f["name"]: f for f in job["files"]}

    assert by_name["native.pdf"]["status"] == "done"
    assert by_name["native.pdf"]["method"] == "pdf_parser"
    assert "Native PDF" in by_name["native.pdf"]["text"]
    assert by_name["scan.pdf"]["method"] == "ocr"
    assert by_name["photo.png"]["method"] == "ocr"
    assert by_name["broken.pdf"]["status"] == "failed"
    assert "not a valid PDF" in by_name["broken.pdf"]["error"]


def test_export_is_downloadable_json(client):
    job_id = client.post("/api/jobs", json={"url": URL, "file_ids": ["img1"]}).json()["job_id"]
    wait_for(client, job_id)
    response = client.get(f"/api/jobs/{job_id}/export")
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.json()["files"][0]["text"] == "image text"


def test_rejects_files_outside_the_folder(client):
    response = client.post("/api/jobs", json={"url": URL, "file_ids": ["someone-elses-file"]})
    assert response.status_code == 422


def test_rejects_empty_selection_and_oversized_batch(client):
    assert client.post("/api/jobs", json={"url": URL, "file_ids": []}).status_code == 422
    too_many = [f"id{i}" for i in range(11)]
    assert client.post("/api/jobs", json={"url": URL, "file_ids": too_many}).status_code == 422


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_config_reports_languages_and_mode(client):
    body = client.get("/api/config").json()
    assert body["ocr_languages"] == ["eng", "fra"]
    assert body["drive_mode"] == "api"
