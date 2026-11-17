import httpx
import pytest

from app.drive import DriveClient, DriveError, FileTooLargeError, FolderNotAccessibleError
from app.drive.models import DriveFile, classify

MAX = 1024


def make_client(handler, api_key="test-key"):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return DriveClient(http, api_key, MAX)


def test_classify_prefers_mime_then_extension():
    assert classify("a.bin", "application/pdf") == "pdf"
    assert classify("scan.PNG", "application/octet-stream") == "image"
    assert classify("photo.jpeg", None) == "image"
    assert classify("notes.txt", "text/plain") is None
    assert classify("report.pdf", "text/plain") is None  # explicit MIME wins


async def test_api_listing_filters_and_paginates():
    pages = {
        None: {
            "files": [
                {"id": "1", "name": "b.pdf", "mimeType": "application/pdf", "size": "100"},
                {"id": "2", "name": "doc.docx", "mimeType": "application/msword"},
            ],
            "nextPageToken": "next",
        },
        "next": {"files": [{"id": "3", "name": "A.png", "mimeType": "image/png", "size": "5"}]},
    }

    def handler(request):
        assert request.url.params["key"] == "test-key"
        return httpx.Response(200, json=pages[request.url.params.get("pageToken")])

    files = await make_client(handler).list_folder("folder")
    assert [f.name for f in files] == ["A.png", "b.pdf"]  # sorted, docx dropped
    assert files[1].size == 100


@pytest.mark.parametrize("status", [403, 404])
async def test_private_or_missing_folder(status):
    client = make_client(lambda r: httpx.Response(status, json={}))
    with pytest.raises(FolderNotAccessibleError):
        await client.list_folder("folder")


async def test_server_error_is_a_drive_error():
    client = make_client(lambda r: httpx.Response(500))
    with pytest.raises(DriveError):
        await client.list_folder("folder")


EMBED_HTML = """
<div class="flip-entries">
  <div class="flip-entry" id="entry-AAA111"><div class="flip-entry-info">
    <div class="flip-entry-title">contract.pdf</div></div></div>
  <div class="flip-entry" id="entry-BBB222"><div class="flip-entry-info">
    <div class="flip-entry-title">scan.jpg</div></div></div>
  <div class="flip-entry" id="entry-CCC333"><div class="flip-entry-info">
    <div class="flip-entry-title">sheet.xlsx</div></div></div>
</div>"""


async def test_keyless_listing_parses_embedded_view():
    client = make_client(lambda r: httpx.Response(200, text=EMBED_HTML), api_key=None)
    files = await client.list_folder("folder")
    assert [(f.id, f.kind, f.size) for f in files] == [
        ("AAA111", "pdf", None),
        ("BBB222", "image", None),
    ]


async def test_keyless_listing_of_private_folder():
    client = make_client(lambda r: httpx.Response(200, text="<html>Sign in</html>"), api_key=None)
    with pytest.raises(FolderNotAccessibleError):
        await client.list_folder("folder")


def drive_file(size=None):
    return DriveFile(id="f1", name="x.pdf", mime_type="application/pdf", size=size, kind="pdf")


async def test_download_returns_bytes():
    client = make_client(lambda r: httpx.Response(200, content=b"%PDF data"))
    assert await client.download(drive_file()) == b"%PDF data"


async def test_download_refuses_declared_oversize_without_requesting():
    def handler(request):
        raise AssertionError("must not hit the network")

    with pytest.raises(FileTooLargeError):
        await make_client(handler).download(drive_file(size=MAX + 1))


async def test_download_stops_when_stream_exceeds_limit():
    client = make_client(lambda r: httpx.Response(200, content=b"x" * (MAX + 1)))
    with pytest.raises(FileTooLargeError):
        await client.download(drive_file(size=None))


async def test_download_rejects_html_confirmation_page():
    client = make_client(
        lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
    )
    with pytest.raises(DriveError, match="web page"):
        await client.download(drive_file())
