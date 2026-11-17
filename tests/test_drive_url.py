import pytest

from app.drive import InvalidDriveLinkError, parse_folder_id

FOLDER_ID = "1AbCdEfGhIjKlMnOpQrStUv"


@pytest.mark.parametrize(
    "link",
    [
        f"https://drive.google.com/drive/folders/{FOLDER_ID}",
        f"https://drive.google.com/drive/folders/{FOLDER_ID}?usp=sharing",
        f"https://drive.google.com/drive/u/0/folders/{FOLDER_ID}",
        f"https://drive.google.com/embeddedfolderview?id={FOLDER_ID}",
        f"https://drive.google.com/open?id={FOLDER_ID}",
        f"  drive.google.com/drive/folders/{FOLDER_ID}  ",
    ],
)
def test_extracts_folder_id(link):
    assert parse_folder_id(link) == FOLDER_ID


@pytest.mark.parametrize(
    "link",
    ["", "   ", "not a url", "https://example.com/drive/folders/" + FOLDER_ID,
     "https://drive.google.com/drive/my-drive", "https://drive.google.com/drive/folders/"],
)
def test_rejects_invalid_links(link):
    with pytest.raises(InvalidDriveLinkError):
        parse_folder_id(link)


def test_single_file_link_gets_a_specific_message():
    with pytest.raises(InvalidDriveLinkError, match="single file"):
        parse_folder_id(f"https://drive.google.com/file/d/{FOLDER_ID}/view")
