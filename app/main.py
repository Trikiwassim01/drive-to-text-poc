"""FastAPI application: JSON API plus the static single-page UI."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.drive import (
    DriveClient,
    DriveError,
    FolderNotAccessibleError,
    InvalidDriveLinkError,
    parse_folder_id,
)
from app.drive.models import DriveFile
from app.extraction import Extractor, OcrEngine
from app.jobs import Job, JobManager

STATIC_DIR = Path(__file__).parent / "static"


class ListRequest(BaseModel):
    url: str


class ListResponse(BaseModel):
    folder_id: str
    files: list[DriveFile]


class JobRequest(BaseModel):
    url: str
    file_ids: list[str] = Field(min_length=1)
    languages: list[str] | None = None


class JobCreated(BaseModel):
    job_id: str


def create_app(
    settings: Settings | None = None,
    http_client: httpx.AsyncClient | None = None,
    ocr: OcrEngine | None = None,
) -> FastAPI:
    """Application factory. Arguments exist so tests can inject fakes."""
    settings = settings or get_settings()
    ocr = ocr or OcrEngine()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = http_client or httpx.AsyncClient(
            timeout=settings.http_timeout_s, follow_redirects=True
        )
        drive = DriveClient(client, settings.google_api_key, settings.max_file_bytes)
        app.state.drive = drive
        app.state.jobs = JobManager(
            drive, Extractor(settings, ocr), settings.batch_concurrency
        )
        yield
        if http_client is None:
            await client.aclose()

    app = FastAPI(title="Drive-to-Text", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(InvalidDriveLinkError)
    async def _bad_link(_: Request, exc: InvalidDriveLinkError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(FolderNotAccessibleError)
    async def _not_accessible(_: Request, exc: FolderNotAccessibleError):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(DriveError)
    async def _drive_error(_: Request, exc: DriveError):
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/config")
    async def public_config():
        return {
            "ocr_languages": ocr.available_languages(),
            "max_file_size_mb": settings.max_file_size_mb,
            "max_files_per_batch": settings.max_files_per_batch,
            "drive_mode": "api" if settings.google_api_key else "keyless",
        }

    @app.post("/api/folders/list", response_model=ListResponse)
    async def list_folder(body: ListRequest, request: Request):
        folder_id = parse_folder_id(body.url)
        files = await request.app.state.drive.list_folder(folder_id)
        return ListResponse(folder_id=folder_id, files=files)

    @app.post("/api/jobs", response_model=JobCreated, status_code=202)
    async def create_job(body: JobRequest, request: Request):
        if len(body.file_ids) > settings.max_files_per_batch:
            raise HTTPException(
                422, f"Select at most {settings.max_files_per_batch} files per batch."
            )
        try:
            languages = ocr.validate_languages(body.languages)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        folder_id = parse_folder_id(body.url)
        # Re-list the folder so only files that really live in it can be processed.
        available = {f.id: f for f in await request.app.state.drive.list_folder(folder_id)}
        missing = [fid for fid in body.file_ids if fid not in available]
        if missing:
            raise HTTPException(422, "Some selected files are not in this folder anymore.")
        selected = [available[fid] for fid in dict.fromkeys(body.file_ids)]

        job = request.app.state.jobs.submit(folder_id, selected, languages)
        return JobCreated(job_id=job.id)

    def _job_or_404(request: Request, job_id: str) -> Job:
        job = request.app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown job.")
        return job

    @app.get("/api/jobs/{job_id}", response_model=Job)
    async def job_status(job_id: str, request: Request):
        return _job_or_404(request, job_id)

    @app.get("/api/jobs/{job_id}/export")
    async def export_job(job_id: str, request: Request):
        job = _job_or_404(request, job_id)
        return JSONResponse(
            job.model_dump(mode="json"),
            headers={
                "Content-Disposition": f'attachment; filename="extraction-{job.id[:8]}.json"'
            },
        )

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
