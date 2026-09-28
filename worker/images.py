"""Image download.

The review CDN 403s requests with no User-Agent, so one is always sent.
"""

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
DEFAULT_MIME = "image/jpeg"


class ImageError(Exception):
    """A recoverable per-row image failure."""


def fetch_image(url: str, session):
    """Fetch an image. Returns (data, mime). Raises ImageError on failure."""
    if not url:
        raise ImageError("empty image URL")
    try:
        response = session.get(url, timeout=60, headers={"User-Agent": BROWSER_UA})
        response.raise_for_status()
    except Exception as exc:  # network, DNS, TLS, HTTP status
        raise ImageError(f"image fetch failed: {exc}") from exc

    data = response.content
    if not data:
        raise ImageError("image response was empty")
    mime = response.headers.get("Content-Type", DEFAULT_MIME).split(";")[0].strip()
    return data, (mime or DEFAULT_MIME)
