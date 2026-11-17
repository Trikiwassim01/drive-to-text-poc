from dataclasses import dataclass, field
from typing import Literal

# How the text was obtained.
Method = Literal["pdf_parser", "ocr", "pdf_parser+ocr"]


@dataclass
class ExtractionResult:
    text: str
    method: Method
    pages: int | None = None  # None for single images
    warnings: list[str] = field(default_factory=list)
