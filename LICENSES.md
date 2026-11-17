# Third-party licences

Every dependency was checked against the licence declared in its installed
package metadata (Python packages) or its Debian copyright file (system
packages). Question asked for each one: **can it be used in a closed-source
commercial product?**

This project itself is released under the [MIT licence](LICENSE).

**Result: no GPL / AGPL / LGPL dependency.** Nothing here requires the
application's source code to be published.

## Direct dependencies (runtime)

| Dependency | Version tested | Licence | Commercial use | Note |
|---|---|---|---|---|
| fastapi | 0.163 | MIT | Yes | |
| uvicorn | 0.54 | BSD-3-Clause | Yes | Keep copyright notice when redistributing. |
| httpx | 0.28 | BSD-3-Clause | Yes | |
| pydantic-settings | 2.16 | MIT | Yes | |
| pypdf | 7.1 | BSD-3-Clause | Yes | **Chosen over PyMuPDF (AGPL-3.0 / commercial), which would require publishing this app's source or buying a licence.** |
| pypdfium2 | 5.15 | BSD-3-Clause / Apache-2.0 | Yes | Bundles Google's PDFium (BSD-3 / Apache-2.0) and its permissive third-party libraries. Used only to rasterise scanned pages. Keep the bundled licence files. |
| pytesseract | 0.3.13 | Apache-2.0 | Yes | Python wrapper only; calls the Tesseract binary as a subprocess. |
| Pillow | 13.0 | MIT-CMU (HPND-style) | Yes | |

## System packages (installed in Docker image / on the host)

| Dependency | Version tested | Licence | Commercial use | Note |
|---|---|---|---|---|
| Tesseract OCR | 5.3.4 | Apache-2.0 | Yes | Keep NOTICE/licence text when redistributing. |
| tessdata (eng, fra, ara) | Debian `tesseract-ocr-*` | Apache-2.0 | Yes | Language models, same licence as the engine. |

## Notable transitive dependencies

| Dependency | Licence | Commercial use | Note |
|---|---|---|---|
| starlette | BSD-3-Clause | Yes | |
| pydantic / pydantic-core | MIT | Yes | |
| anyio, h11, httptools, watchfiles, PyYAML | MIT | Yes | |
| httpcore, click, idna, websockets, python-dotenv | BSD-3-Clause | Yes | |
| uvloop | MIT / Apache-2.0 | Yes | |
| certifi | MPL-2.0 | Yes | File-level copyleft: only changes to certifi's own files must be shared. We use it unmodified. |
| typing-extensions | PSF-2.0 | Yes | |

## Development only (not shipped)

| Dependency | Licence | Commercial use |
|---|---|---|
| pytest | MIT | Yes |
| pytest-asyncio | Apache-2.0 | Yes |

## Other things worth knowing

- **Google Drive API / Terms of Service:** the Drive API is a service, not a
  library. Using it with your own API key is subject to Google's API Terms of
  Service. The keyless fallback scrapes a public HTML view and is not a
  supported API; do not rely on it in production.
- **Docker base image** `python:3.12-slim` (PSF licence for Python, Debian
  packages under their own licences). Debian packages installed here are the
  Tesseract ones listed above.
- Licences were read from package metadata on 2026-11-17. Re-check with
  `pip-licenses` (MIT) before any release.
