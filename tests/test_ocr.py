import shutil

import pytest

from app.extraction import ExtractionError, OcrEngine

from app.extraction.pdf import extract_pdf

from .helpers import make_scanned_pdf, make_text_image

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract missing")


def test_validate_languages_defaults_and_rejects_unknown():
    engine = OcrEngine()
    assert engine.validate_languages(None) == ["eng"]
    assert engine.validate_languages(["eng", "fra"]) == ["eng", "fra"]
    with pytest.raises(ValueError, match="klingon"):
        engine.validate_languages(["klingon"])


def test_corrupt_image_raises_extraction_error():
    with pytest.raises(ExtractionError, match="not a readable image"):
        OcrEngine().bytes_to_text(b"definitely not an image", ["eng"])


@needs_tesseract
@pytest.mark.parametrize("fmt", ["PNG", "JPEG"])
def test_reads_text_from_image(fmt):
    text = OcrEngine().bytes_to_text(make_text_image("INVOICE 2026", fmt), ["eng"])
    assert "INVOICE" in text.upper()


@needs_tesseract
def test_available_languages_lists_only_supported_codes():
    available = OcrEngine().available_languages()
    assert "eng" in available
    assert set(available) <= {"eng", "fra", "ara"}


@needs_tesseract
def test_scanned_pdf_is_read_through_real_ocr():
    engine = OcrEngine()
    result = extract_pdf(
        make_scanned_pdf("SCANNED CONTRACT"),
        ocr=lambda image: engine.image_to_text(image, ["eng"]),
    )
    assert result.method == "ocr"
    assert "CONTRACT" in result.text.upper()
