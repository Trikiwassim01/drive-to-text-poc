
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel

FileKind = Literal["pdf", "image"]

_MIME_TO_KIND: dict[str, FileKind] = {
    "application/pdf": "pdf",
    "image/png": "image",
    "image/jpeg": "image",
}
_EXT_TO_KIND: dict[str, FileKind] = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
}


def classify(name: str, mime_type: str | None) -> FileKind | None:
    """Return 'pdf' / 'image' for supported files, None for everything else.

    The MIME type wins; the extension is a fallback because Drive sometimes
    reports application/octet-stream for uploaded files.
    """
    if mime_type in _MIME_TO_KIND:
        return _MIME_TO_KIND[mime_type]
    if mime_type in (None, "", "application/octet-stream"):
        return _EXT_TO_KIND.get(PurePosixPath(name).suffix.lower())
    return None


class DriveFile(BaseModel):
    id: str
    name: str
    mime_type: str
    size: int | None = None  # None when Drive does not tell us (keyless mode)
    kind: FileKind
