import pytest
from worker.images import BROWSER_UA, DEFAULT_MIME, ImageError, fetch_image


class FakeResponse:
    def __init__(self, status=200, content=b"abc", ctype="image/jpeg"):
        self.status_code = status
        self.content = content
        self.headers = {"Content-Type": ctype}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, resp, record=None):
        self._resp = resp
        self._record = record if record is not None else {}

    def get(self, url, timeout=None, headers=None):
        self._record["headers"] = headers
        return self._resp


def test_fetch_image_returns_bytes_and_mime():
    data, mime = fetch_image("https://x.test/a.jpg", FakeSession(FakeResponse()))
    assert data == b"abc"
    assert mime == "image/jpeg"


def test_fetch_image_sends_a_user_agent():
    # the review CDN 403s requests with no User-Agent; this is the module's
    # whole reason for existing, so the header must be pinned
    record = {}
    fetch_image("https://x.test/a.jpg", FakeSession(FakeResponse(), record))
    assert record["headers"]["User-Agent"] == BROWSER_UA


def test_fetch_image_rejects_empty_body():
    with pytest.raises(ImageError):
        fetch_image("https://x.test/a.jpg", FakeSession(FakeResponse(content=b"")))


def test_fetch_image_wraps_http_errors():
    with pytest.raises(ImageError):
        fetch_image("https://x.test/a.jpg", FakeSession(FakeResponse(status=404)))


def test_fetch_image_wraps_network_errors():
    class Broken:
        def get(self, url, timeout=None, headers=None):
            raise ConnectionError("dns failure")

    with pytest.raises(ImageError):
        fetch_image("https://x.test/a.jpg", Broken())


def test_fetch_image_falls_back_to_default_mime():
    data, mime = fetch_image("https://x.test/a.jpg", FakeSession(FakeResponse(ctype="")))
    assert mime == DEFAULT_MIME
