
import logging
from html.parser import HTMLParser

import httpx

from .models import DriveFile, classify

log = logging.getLogger(__name__)

API_FILES = "https://www.googleapis.com/drive/v3/files"
EMBED_VIEW = "https://drive.google.com/embeddedfolderview"
LEGACY_DOWNLOAD = "https://drive.google.com/uc"


class DriveError(Exception):
    """Generic Drive failure, safe to show to the user."""


class FolderNotAccessibleError(DriveError):
    """The folder does not exist or is not shared publicly."""


class FileTooLargeError(DriveError):
    """The file exceeds the configured size limit."""


class _EmbeddedFolderParser(HTMLParser):
    """Collects (id, name) pairs from Drive's embedded folder view."""

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[tuple[str, str]] = []
        self._current_id: str | None = None
        self._in_title = False
        self._title: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        entry_id = attributes.get("id") or ""
        if tag == "div" and "flip-entry" in classes and entry_id.startswith("entry-"):
            self._current_id = entry_id.removeprefix("entry-")
        elif tag == "div" and "flip-entry-title" in classes and self._current_id:
            self._in_title = True
            self._title = []

    def handle_data(self, data):
        if self._in_title:
            self._title.append(data)

    def handle_endtag(self, tag):
        if tag == "div" and self._in_title:
            self._in_title = False
            name = "".join(self._title).strip()
            if self._current_id and name:
                self.entries.append((self._current_id, name))
            self._current_id = None


class DriveClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str | None, max_bytes: int):
        self._http = http
        self._api_key = api_key
        self._max_bytes = max_bytes

    # ---- listing -----------------------------------------------------

    async def list_folder(self, folder_id: str) -> list[DriveFile]:
        """List the PDFs and images (PNG/JPG/JPEG) directly inside a folder."""
        if self._api_key:
            files = await self._list_with_api(folder_id)
        else:
            files = await self._list_keyless(folder_id)
        return sorted(files, key=lambda f: f.name.lower())

    async def _list_with_api(self, folder_id: str) -> list[DriveFile]:
        files: list[DriveFile] = []
        page_token: str | None = None
        while True:
            params = {
                "q": f"'{folder_id}' in parents and trashed = false",
                "fields": "nextPageToken, files(id, name, mimeType, size)",
                "pageSize": "1000",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
                "key": self._api_key,
            }
            if page_token:
                params["pageToken"] = page_token
            response = await self._get(API_FILES, params=params)
            self._raise_for_listing(response)
            payload = response.json()
            for item in payload.get("files", []):
                kind = classify(item["name"], item.get("mimeType"))
                if kind:
                    files.append(
                        DriveFile(
                            id=item["id"],
                            name=item["name"],
                            mime_type=item.get("mimeType", ""),
                            size=int(item["size"]) if item.get("size") else None,
                            kind=kind,
                        )
                    )
            page_token = payload.get("nextPageToken")
            if not page_token:
                return files

    async def _list_keyless(self, folder_id: str) -> list[DriveFile]:
        response = await self._get(EMBED_VIEW, params={"id": folder_id})
        self._raise_for_listing(response)
        parser = _EmbeddedFolderParser()
        parser.feed(response.text)
        if not parser.entries and "flip-entry" not in response.text:
            # Private folders redirect to a sign-in page that has no entries.
            raise FolderNotAccessibleError(
                "The folder is private, empty or could not be read. "
                "Check that sharing is set to 'Anyone with the link'."
            )
        files = []
        for file_id, name in parser.entries:
            kind = classify(name, None)
            if kind:
                mime = {"pdf": "application/pdf"}.get(kind, _guess_image_mime(name))
                files.append(DriveFile(id=file_id, name=name, mime_type=mime, kind=kind))
        return files

    @staticmethod
    def _raise_for_listing(response: httpx.Response) -> None:
        if response.status_code == 200:
            return
        if response.status_code in (401, 403, 404):
            raise FolderNotAccessibleError(
                "Folder not found or not public. "
                "Share it with 'Anyone with the link' and try again."
            )
        if response.status_code == 400:
            raise DriveError("Google rejected the request. Is the folder link valid?")
        if response.status_code == 429:
            raise DriveError("Google Drive is rate-limiting requests. Try again shortly.")
        raise DriveError(f"Google Drive returned an unexpected error ({response.status_code}).")

    # ---- download ----------------------------------------------------

    async def download(self, file: DriveFile) -> bytes:
        """Download a file, refusing anything over the size limit."""
        if file.size is not None and file.size > self._max_bytes:
            raise FileTooLargeError(_too_large_message(self._max_bytes))

        if self._api_key:
            url, params = f"{API_FILES}/{file.id}", {"alt": "media", "key": self._api_key}
        else:
            url, params = LEGACY_DOWNLOAD, {"export": "download", "id": file.id}

        try:
            async with self._http.stream("GET", url, params=params) as response:
                if response.status_code in (401, 403, 404):
                    raise DriveError("The file is not publicly downloadable.")
                if response.status_code != 200:
                    raise DriveError(f"Download failed ({response.status_code}).")
                if "text/html" in response.headers.get("content-type", ""):
                    raise DriveError(
                        "Google returned a web page instead of the file "
                        "(download quota or confirmation page)."
                    )
                chunks, total = [], 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self._max_bytes:
                        raise FileTooLargeError(_too_large_message(self._max_bytes))
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.HTTPError as exc:
            raise DriveError(f"Network error while downloading: {type(exc).__name__}.") from exc

    async def _get(self, url: str, params: dict) -> httpx.Response:
        try:
            return await self._http.get(url, params=params)
        except httpx.HTTPError as exc:
            raise DriveError(f"Could not reach Google Drive: {type(exc).__name__}.") from exc


def _guess_image_mime(name: str) -> str:
    return "image/png" if name.lower().endswith(".png") else "image/jpeg"


def _too_large_message(limit: int) -> str:
    return f"File is larger than the {limit // (1024 * 1024)} MB limit."
