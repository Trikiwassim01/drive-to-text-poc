
import re
from urllib.parse import parse_qs, urlparse

_ID = r"[A-Za-z0-9_-]{10,}"
_FOLDER_PATH = re.compile(rf"/folders/({_ID})")
_ALLOWED_HOSTS = {"drive.google.com", "www.drive.google.com"}


class InvalidDriveLinkError(ValueError):
    """The text is not a usable Google Drive folder link."""


def parse_folder_id(link: str) -> str:
    """Return the folder id from a Drive folder URL.

    Accepted shapes:
      https://drive.google.com/drive/folders/<id>?usp=sharing
      https://drive.google.com/drive/u/0/folders/<id>
      https://drive.google.com/embeddedfolderview?id=<id>
      https://drive.google.com/open?id=<id>
    """
    link = (link or "").strip()
    if not link:
        raise InvalidDriveLinkError("Paste a Google Drive folder link.")

    parsed = urlparse(link if "://" in link else f"https://{link}")
    if parsed.hostname not in _ALLOWED_HOSTS:
        raise InvalidDriveLinkError("This is not a drive.google.com link.")

    match = _FOLDER_PATH.search(parsed.path)
    if match:
        return match.group(1)

    ids = parse_qs(parsed.query).get("id", [])
    if ids and re.fullmatch(_ID, ids[0]):
        return ids[0]

    if "/file/" in parsed.path:
        raise InvalidDriveLinkError(
            "This link points to a single file. Paste a folder link instead."
        )
    raise InvalidDriveLinkError("Could not find a folder id in this link.")
