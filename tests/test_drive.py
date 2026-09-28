import pytest
from worker.drive import folder_id_from_url


@pytest.mark.parametrize("url,expected", [
    ("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"),
    ("https://drive.google.com/drive/u/0/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"),
    ("https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"),
])
def test_folder_id_from_url(url, expected):
    assert folder_id_from_url(url) == expected


@pytest.mark.parametrize("bad", [
    "",
    "not a url",
    "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view",
])
def test_folder_id_from_url_rejects_non_folders(bad):
    with pytest.raises(ValueError):
        folder_id_from_url(bad)
