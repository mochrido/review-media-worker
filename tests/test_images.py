import pytest
from worker.images import ImageError, fetch_image


class FakeResponse:
    def __init__(self, status=200, content=b"abc", ctype="image/jpeg"):
        self.status_code = status
        self.content = content
        self.headers = {"Content-Type": ctype}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, resp):
        self._resp = resp

    def get(self, url, timeout=None, headers=None):
        return self._resp


def test_fetch_image_returns_bytes_and_mime():
    data, mime = fetch_image("https://x.test/a.jpg", FakeSession(FakeResponse()))
    assert data == b"abc"
    assert mime == "image/jpeg"


def test_fetch_image_rejects_empty_body():
    with pytest.raises(ImageError):
        fetch_image("https://x.test/a.jpg", FakeSession(FakeResponse(content=b"")))


def test_fetch_image_wraps_http_errors():
    with pytest.raises(ImageError):
        fetch_image("https://x.test/a.jpg", FakeSession(FakeResponse(status=404)))
