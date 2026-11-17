"""Fixtures built in code so the repo carries no binary test files."""

import io

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter


def make_text_pdf(text: str) -> bytes:
    """A one-page PDF with a real text layer (hand-written, no extra dependency)."""
    stream = f"BT /F1 18 Tf 72 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def make_blank_pdf(pages: int = 1) -> bytes:
    """A PDF with no text layer, like a scan."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_text_image(text: str, fmt: str = "PNG") -> bytes:
    """A white image with large black text, easy for Tesseract."""
    image = Image.new("RGB", (900, 200), "white")
    ImageDraw.Draw(image).text((30, 60), text, fill="black", font=ImageFont.load_default(size=64))
    buffer = io.BytesIO()
    image.save(buffer, fmt)
    return buffer.getvalue()


def make_scanned_pdf(text: str) -> bytes:
    """A PDF that holds only a picture of text (no text layer), like a real scan."""
    image = Image.new("RGB", (1240, 400), "white")
    ImageDraw.Draw(image).text((60, 150), text, fill="black", font=ImageFont.load_default(size=72))
    buffer = io.BytesIO()
    image.save(buffer, "PDF", resolution=150)
    return buffer.getvalue()
