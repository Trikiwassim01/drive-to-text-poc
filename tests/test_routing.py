import pytest

from app.config import Settings
from app.extraction import ExtractionError, Extractor

from .helpers import make_blank_pdf, make_text_pdf


class FakeOcr:
    def __init__(self):
        self.image_calls = 0
        self.bytes_calls = 0

    def image_to_text(self, image, languages):
        self.image_calls += 1
        return f"ocr[{'+'.join(languages)}]"

    def bytes_to_text(self, data, languages):
        self.bytes_calls += 1
        return "image text"


@pytest.fixture
def ocr():
    return FakeOcr()


@pytest.fixture
def extractor(ocr):
    return Extractor(Settings(google_api_key=None), ocr)


def test_native_pdf_goes_to_parser_not_ocr(extractor, ocr):
    result = extractor.extract("pdf", make_text_pdf("A real text layer here"), ["eng"])
    assert result.method == "pdf_parser"
    assert ocr.image_calls == ocr.bytes_calls == 0


def test_image_goes_to_ocr(extractor, ocr):
    result = extractor.extract("image", b"bytes", ["eng"])
    assert (result.method, result.text) == ("ocr", "image text")
    assert ocr.bytes_calls == 1


def test_scanned_pdf_is_detected_and_sent_to_ocr_with_languages(extractor, ocr):
    result = extractor.extract("pdf", make_blank_pdf(), ["fra", "eng"])
    assert result.method == "ocr"
    assert result.text == "ocr[fra+eng]"


def test_empty_ocr_result_adds_a_warning(extractor, ocr):
    ocr.bytes_to_text = lambda data, languages: ""
    result = extractor.extract("image", b"bytes", ["eng"])
    assert result.warnings


def test_unknown_kind_is_rejected(extractor):
    with pytest.raises(ExtractionError):
        extractor.extract("video", b"", ["eng"])  # type: ignore[arg-type]
