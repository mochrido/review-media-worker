"""Output filenames.

A row has at most one image and one video, and the two extensions differ,
so a bare username cannot collide with itself. The name is sanitised
because real data contains '@' and a stray path separator would escape the
target folder.
"""

import os
import re

_ALLOWED = re.compile(r"[^A-Za-z0-9._-]")
_IMAGE_EXT = re.compile(r"\.([A-Za-z0-9]{2,5})$")
_MAX_STEM = 200  # Drive and ext4 cap names at 255; leave room for ".mp4"


def safe_username(raw: str) -> str:
    """Strip anything that is not safe in a filename.

    '@megasyana' -> 'megasyana'; '../../etc/passwd' -> 'etcpasswd'.
    Leading/trailing dots and dashes are removed because a name like
    '..' or 'name.' is either a traversal or illegal on Windows.
    Never returns an empty string for non-empty input.
    """
    if not raw:
        return "user"
    cleaned = _ALLOWED.sub("", str(raw).strip()).strip(".-")
    if not cleaned:
        return "user"
    return cleaned[:_MAX_STEM]


def image_filename(username: str, url: str) -> str:
    """<username>.<ext>, extension taken from the URL's path (query stripped)."""
    stem = safe_username(username)
    path = str(url).split("?")[0].split("#")[0]
    match = _IMAGE_EXT.search(os.path.basename(path))
    ext = match.group(1).lower() if match else "jpg"
    return f"{stem}.{ext}"


def video_filename(username: str) -> str:
    """<username>.mp4 — always mp4, since we mux into an mp4 container."""
    return f"{safe_username(username)}.mp4"
