

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from app.drive import DriveClient, DriveError, DriveFile
from app.extraction import ExtractionError, Extractor

log = logging.getLogger(__name__)

MAX_JOBS_KEPT = 50


class FileStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class JobStatus(str, Enum):
    running = "running"
    completed = "completed"


class FileResult(BaseModel):
    id: str
    name: str
    mime_type: str
    kind: str
    size: int | None = None
    status: FileStatus = FileStatus.pending
    method: str | None = None
    pages: int | None = None
    text: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    duration_ms: int | None = None


class Job(BaseModel):
    id: str
    folder_id: str
    languages: list[str]
    status: JobStatus = JobStatus.running
    created_at: str
    files: list[FileResult]

    @property
    def finished_count(self) -> int:
        return sum(f.status in (FileStatus.done, FileStatus.failed) for f in self.files)


class JobManager:
    def __init__(self, drive: DriveClient, extractor: Extractor, concurrency: int):
        self._drive = drive
        self._extractor = extractor
        self._concurrency = max(1, concurrency)
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()  # keep references so tasks are not GC'd

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def submit(self, folder_id: str, files: list[DriveFile], languages: list[str]) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            folder_id=folder_id,
            languages=languages,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            files=[
                FileResult(
                    id=f.id, name=f.name, mime_type=f.mime_type, kind=f.kind, size=f.size
                )
                for f in files
            ],
        )
        self._jobs[job.id] = job
        while len(self._jobs) > MAX_JOBS_KEPT:
            self._jobs.pop(next(iter(self._jobs)))

        task = asyncio.create_task(self._run(job, files))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run(self, job: Job, files: list[DriveFile]) -> None:
        semaphore = asyncio.Semaphore(self._concurrency)
        await asyncio.gather(
            *(
                self._process(semaphore, job, drive_file, result)
                for drive_file, result in zip(files, job.files)
            )
        )
        job.status = JobStatus.completed

    async def _process(
        self, semaphore: asyncio.Semaphore, job: Job, drive_file: DriveFile, result: FileResult
    ) -> None:
        async with semaphore:
            result.status = FileStatus.processing
            started = time.perf_counter()
            try:
                data = await self._drive.download(drive_file)
                extraction = await asyncio.to_thread(
                    self._extractor.extract, drive_file.kind, data, job.languages
                )
                result.text = extraction.text
                result.method = extraction.method
                result.pages = extraction.pages
                result.warnings = extraction.warnings
                result.status = FileStatus.done
            except (DriveError, ExtractionError) as exc:
                result.error = str(exc)
                result.status = FileStatus.failed
            except Exception as exc:  # last resort: never let one file kill the batch
                log.exception("Unexpected failure on %s", drive_file.name)
                result.error = f"Unexpected error ({type(exc).__name__})."
                result.status = FileStatus.failed
            finally:
                result.duration_ms = round((time.perf_counter() - started) * 1000)
