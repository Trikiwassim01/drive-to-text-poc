# Drive-to-Text

A small web app that takes a **public Google Drive folder link**, lists the PDFs
and images (PNG, JPG, JPEG) it contains, and extracts their text through the
right pipeline: a **PDF parser** for native PDFs, **OCR** for images (and for
scanned PDF pages).

Built as a proof of concept for technical assessment TA-2026-01.

```
drive_link → list files → user selection → batch
   ├─ *.pdf      → pypdf (text layer) ─ page has no text? → Tesseract OCR
   └─ *.png|jpg  → Tesseract OCR
results → per-file text + status + method → UI / JSON export
```

## Features

- Paste a public Drive folder URL; invalid or private links show a clear error.
- Lists only PDFs and images, with name, type and size.
- Select files one by one or with "Select all"; the selection count stays visible.
- One batch per validation. Each file has its own status: `pending`, `processing`, `done`, `failed`. **A failing file never stops the batch.**
- Results per file with the method used (`pdf parser`, `ocr`, `pdf parser+ocr`), copy button, and **JSON export** of the whole batch.
- Bonus items done: scanned-PDF detection with automatic OCR fallback, asynchronous processing with live progress (polling), Docker/compose, automated tests, OCR language choice (English, French, Arabic).

## Quick start

### Docker (one command)

```bash
cp .env.example .env      # optional, see "Google API key" below
docker compose up --build
```

Open <http://localhost:8000>.

### Local

Requirements: Python 3.11+ and the Tesseract binary with the language packs you need.

```bash
# Debian/Ubuntu
sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra tesseract-ocr-ara
# macOS: brew install tesseract tesseract-lang

python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open <http://localhost:8000>. Run the tests with `pytest`.

### Google API key (recommended, optional)

Public folders can be read **without any user login**, but Google only offers a
proper listing endpoint with an API key (a key, not OAuth):

1. Google Cloud Console → create a project → enable **Google Drive API**.
2. Credentials → create an **API key**, restrict it to the Drive API.
3. Put it in `.env` as `GOOGLE_API_KEY=...` (the file is git-ignored).

| | With key | Without key (fallback) |
|---|---|---|
| Source | Drive API v3 | Public embedded folder view (HTML) |
| File sizes | Exact | Unknown (shown as "—") |
| Reliability | Supported API | Best effort: Google can change the markup |
| Over-size check | Before download | While downloading |

## Architecture

```
app/
  main.py            FastAPI app factory + routes (thin)
  config.py          Settings from env / .env (pydantic-settings)
  jobs.py            In-memory batch jobs, per-file status, concurrency limit
  drive/
    url.py           Folder id parsing and link validation
    client.py        Listing + download (API mode and keyless mode)
    models.py        DriveFile and file-type classification
  extraction/
    router.py        Routing: pdf -> parser, image -> OCR
    pdf.py           pypdf text layer + per-page OCR fallback
    ocr.py           Tesseract wrapper, language validation
  static/            Single page UI (HTML + CSS + vanilla JS, no build step)
tests/               pytest suite (mocked Drive, real Tesseract when installed)
scripts/             Sample output generator
```

How a batch runs:

1. `POST /api/folders/list` parses the link, lists the folder, returns supported files.
2. `POST /api/jobs` re-lists the folder (so only files that really live in it can be processed), then starts a background task and returns a job id immediately.
3. Files run concurrently up to `BATCH_CONCURRENCY`. Downloads are async; CPU-bound extraction runs in worker threads so the server stays responsive.
4. The UI polls `GET /api/jobs/{id}` every ~0.8 s for live status, and `GET /api/jobs/{id}/export` returns the JSON file.

Scanned-PDF detection is **per page**: a page with fewer than
`PDF_MIN_CHARS_PER_PAGE` characters of text layer is rendered (pypdfium2) and
OCR'd. OCR output replaces the parsed text only if it is longer, so mixed
documents work and short real pages are not degraded.

## Why this stack

- **Python + FastAPI**: the best ecosystem for PDF/OCR work, async I/O for downloads, and automatic request validation. Small surface, easy to test with an injected HTTP transport.
- **Vanilla HTML/JS frontend**: the flow is one page. No build step or `node_modules` means one process, one command, less to review.
- **pypdf (BSD-3)** instead of PyMuPDF: PyMuPDF is AGPL-3.0 and would block closed-source commercial use. See [LICENSES.md](LICENSES.md).
- **Tesseract (Apache-2.0)**: open source, self-hostable, no per-page cost, supports French and Arabic. No paid cloud API is used.
- **pypdfium2** only to rasterise scanned pages (BSD/Apache). It avoids requiring the poppler system package.
- **Polling instead of WebSockets/SSE**: simplest thing that gives live progress; easy to replace later.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness |
| GET | `/api/config` | Installed OCR languages, limits, Drive mode |
| POST | `/api/folders/list` | `{url}` → `{folder_id, files[]}` |
| POST | `/api/jobs` | `{url, file_ids[], languages[]}` → `202 {job_id}` |
| GET | `/api/jobs/{id}` | Job + per-file status/results |
| GET | `/api/jobs/{id}/export` | Same data as a downloadable JSON file |

Interactive docs at `/docs`.

## Sample output

[`samples/sample_output.json`](samples/sample_output.json) shows the export format.

> **Transparency note:** it was generated by `python -m scripts.generate_sample`
> from a **local fixture folder** (a fake Drive serving generated files, with the
> real PDF parser and real Tesseract). To produce one from a real Drive folder:
>
> ```bash
> JOB=$(curl -s localhost:8000/api/jobs -H 'content-type: application/json' \
>   -d '{"url":"<folder-url>","file_ids":["<id1>","<id2>"]}' | jq -r .job_id)
> curl -s localhost:8000/api/jobs/$JOB/export -o samples/sample_output.json
> ```
> (File ids come from `POST /api/folders/list`.)

## Known limits

- **Not tested against live Google Drive** during development (no network access to Google in the build environment). The Drive layer is covered by tests with mocked HTTP responses matching the documented API shape; the keyless HTML parser is based on the current embedded-view markup and may break.
- Only files **directly inside** the folder are listed (no sub-folders).
- Large files: limited to `MAX_FILE_SIZE_MB` (25 by default). Files that trigger Google's virus-scan confirmation page fail with a clear message in keyless mode.
- Jobs live **in memory** (last 50 kept): a restart loses them, and it does not scale past one process.
- OCR quality depends on the image; no preprocessing (deskew, binarisation) yet. Handwriting is not supported.
- Password-protected PDFs are reported as failed.
- No authentication or rate limiting on this API: do not expose it publicly as-is.

## Next steps

- Persist jobs (SQLite/Redis) and move extraction to a worker queue.
- Recurse into sub-folders; support Google Docs export.
- Image preprocessing and per-page confidence scores.
- Server-sent events instead of polling.
- CI (GitHub Actions) running `pytest` and a licence scan.

## Licence

[MIT](LICENSE). Third-party licences and commercial-use review: [LICENSES.md](LICENSES.md).
