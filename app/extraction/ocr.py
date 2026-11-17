"""OCR through Tesseract (Apache-2.0), driven by pytesseract."""

import io
from functools import lru_cache

import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import ExtractionError

# UI language -> Tesseract traineddata name. Add entries to support more.
SUPPORTED_LANGUAGES = {"eng": "English", "fra": "French", "ara": "Arabic"}
DEFAULT_LANGUAGES = ("eng",)


class OcrEngine:
    """Thin wrapper so the rest of the code never imports pytesseract directly."""

    def available_languages(self) -> list[str]:
        """Supported languages whose traineddata is installed (empty if no Tesseract)."""
        try:
            installed = set(pytesseract.get_languages(config=""))
        except pytesseract.TesseractNotFoundError:
            return []
        return [code for code in SUPPORTED_LANGUAGES if code in installed]

    def validate_languages(self, languages: list[str] | None) -> list[str]:
        requested = list(languages or DEFAULT_LANGUAGES)
        unknown = [code for code in requested if code not in SUPPORTED_LANGUAGES]
        if unknown:
            raise ValueError(f"Unsupported OCR language(s): {', '.join(unknown)}")
        return requested

    def image_to_text(self, image: Image.Image, languages: list[str]) -> str:
        try:
            return pytesseract.image_to_string(image, lang="+".join(languages)).strip()
        except pytesseract.TesseractNotFoundError as exc:
            raise ExtractionError(
                "OCR engine (Tesseract) is not installed on the server."
            ) from exc
        except pytesseract.TesseractError as exc:
            raise ExtractionError(
                f"OCR failed. Is the language data for {', '.join(languages)} installed?"
            ) from exc

    def bytes_to_text(self, data: bytes, languages: list[str]) -> str:
        try:
            with Image.open(io.BytesIO(data)) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ExtractionError("The file is not a readable image.") from exc
        return self.image_to_text(image, languages)


@lru_cache
def default_engine() -> OcrEngine:
    return OcrEngine()
