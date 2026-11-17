import pytest

from app.extraction import ExtractionError
from app.extraction.pdf import extract_pdf

from .helpers import make_blank_pdf, make_text_pdf


def test_native_pdf_uses_parser_only():
    calls = []
    result = extract_pdf(
        make_text_pdf("Hello native text layer"),
        ocr=lambda image: calls.append(image) or "should not be used",
    )
    assert "Hello native text layer" in result.text
    assert result.method == "pdf_parser"
    assert result.pages == 1
    assert calls == []  # OCR never ran on a page that has text


def test_scanned_pdf_falls_back_to_ocr():
    result = extract_pdf(make_blank_pdf(2), ocr=lambda image: "text from the scan")
    assert result.method == "ocr"
    assert result.pages == 2
    assert result.text.count("text from the scan") == 2


def test_scanned_pdf_without_ocr_warns_instead_of_failing():
    result = extract_pdf(make_blank_pdf(), ocr=None)
    assert result.text == ""
    assert result.method == "pdf_parser"
    assert any("No text found" in w for w in result.warnings)


def test_short_native_page_is_kept_when_ocr_finds_nothing_better():
    result = extract_pdf(make_text_pdf("Hi"), ocr=lambda image: "")
    assert result.text == "Hi"
    assert result.method == "pdf_parser"


def test_ocr_failure_on_a_page_becomes_a_warning():
    def broken(image):
        raise RuntimeError("boom")

    result = extract_pdf(make_blank_pdf(), ocr=broken)
    assert any("OCR fallback failed" in w for w in result.warnings)


def test_ocr_engine_error_propagates_with_its_message():
    def missing_engine(image):
        raise ExtractionError("OCR engine (Tesseract) is not installed on the server.")

    with pytest.raises(ExtractionError, match="Tesseract"):
        extract_pdf(make_blank_pdf(), ocr=missing_engine)


@pytest.mark.parametrize("data", [b"", b"not a pdf at all", b"%PDF-1.4\ngarbage"])
def test_invalid_pdf_raises_extraction_error(data):
    with pytest.raises(ExtractionError, match="not a valid PDF"):
        extract_pdf(data, ocr=None)
