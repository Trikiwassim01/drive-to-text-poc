
from app.config import Settings
from app.drive.models import FileKind

from .errors import ExtractionError
from .ocr import OcrEngine
from .pdf import extract_pdf
from .types import ExtractionResult


class Extractor:
    """Synchronous and CPU-bound: call it from a worker thread."""

    def __init__(self, settings: Settings, ocr: OcrEngine):
        self._settings = settings
        self._ocr = ocr

    def extract(self, kind: FileKind, data: bytes, languages: list[str]) -> ExtractionResult:
        if kind == "pdf":
            return extract_pdf(
                data,
                ocr=lambda image: self._ocr.image_to_text(image, languages),
                min_chars_per_page=self._settings.pdf_min_chars_per_page,
                dpi=self._settings.ocr_dpi,
            )
        if kind == "image":
            text = self._ocr.bytes_to_text(data, languages)
            warnings = [] if text else ["OCR found no text in this image."]
            return ExtractionResult(text=text, method="ocr", warnings=warnings)
        raise ExtractionError(f"Unsupported file kind: {kind}")
