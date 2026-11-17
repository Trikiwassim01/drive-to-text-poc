"""Text extraction from PDFs: native text layer first, OCR for pages without one."""

import io
from collections.abc import Callable

import pypdf
import pypdfium2 as pdfium
from PIL import Image

from .errors import ExtractionError
from .types import ExtractionResult, Method

# Takes a rendered page image, returns its text.
PageOcr = Callable[[Image.Image], str]


def extract_pdf(
    data: bytes,
    *,
    ocr: PageOcr | None,
    min_chars_per_page: int = 20,
    dpi: int = 200,
) -> ExtractionResult:
    """Extract text page by page.

    A page whose text layer is shorter than `min_chars_per_page` is treated as
    scanned and sent to `ocr` (if provided). OCR output is only kept when it is
    longer than what the parser found, so a page that legitimately holds a few
    words is not degraded.
    """
    reader = _open(data)
    page_count = len(reader.pages)
    if page_count == 0:
        raise ExtractionError("The PDF has no pages.")

    texts: list[str] = []
    ocr_pages: set[int] = set()
    warnings: list[str] = []
    renderer: pdfium.PdfDocument | None = None

    for index, page in enumerate(reader.pages):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:  # pypdf raises many types on malformed pages
            text = ""
            warnings.append(f"Page {index + 1}: text layer could not be read.")

        if len(text) < min_chars_per_page and ocr is not None:
            try:
                renderer = renderer or pdfium.PdfDocument(data)
                image = renderer[index].render(scale=dpi / 72).to_pil().convert("RGB")
                ocr_text = ocr(image)
            except ExtractionError:
                raise
            except Exception:
                ocr_text = ""
                warnings.append(f"Page {index + 1}: OCR fallback failed.")
            if len(ocr_text) > len(text):
                text = ocr_text
                ocr_pages.add(index)
        texts.append(text)

    method: Method
    if not ocr_pages:
        method = "pdf_parser"
    elif len(ocr_pages) == page_count:
        method = "ocr"
    else:
        method = "pdf_parser+ocr"

    full_text = "\n\n".join(texts).strip()
    if not full_text:
        warnings.append("No text found. The PDF may be empty or contain only graphics.")
    return ExtractionResult(text=full_text, method=method, pages=page_count, warnings=warnings)


def _open(data: bytes) -> pypdf.PdfReader:
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("The PDF is password-protected.")
        len(reader.pages)  # force parsing so structural errors surface here
        return reader
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("The file is not a valid PDF.") from exc
