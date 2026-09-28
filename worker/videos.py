"""Vimeo video download and mux.

yt-dlp fetches the player page (which embeds the signed stream URLs in
window.playerConfig) and drives ffmpeg to mux the separate video and audio
renditions into one mp4. Apps Script cannot do this — it has no ffmpeg.

Verified during design: a plain GET on the player page needs no cookies and
no browser, and yt-dlp produces an mp4 containing both h264 video and aac
audio.
"""

import os
import re
import subprocess

from worker.status import RESTRICTED, error_status

_VIMEO_HOST = re.compile(r"^https?://(?:www\.|player\.)?vimeo\.com/", re.I)
_VIMEO_ID = re.compile(r"^https?://(?:www\.|player\.)?vimeo\.com/(?:video/)?(\d+)", re.I)

# Prefer a muxed mp4; fall back to best video+audio merged into mp4.
FORMAT_SELECTOR = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b"
TIMEOUT_SECONDS = 600


def is_vimeo_url(url: str) -> bool:
    return bool(url) and bool(_VIMEO_HOST.match(str(url).strip()))


def vimeo_id(url: str):
    match = _VIMEO_ID.search(str(url or ""))
    return match.group(1) if match else None


def build_command(url: str, out_path: str):
    """The exact yt-dlp invocation. Kept pure so it is unit-testable."""
    return [
        "yt-dlp",
        "--no-warnings",
        "--no-playlist",
        "--force-ipv4",
        "-f", FORMAT_SELECTOR,
        "--merge-output-format", "mp4",
        "-o", out_path,
        url,
    ]


def classify_failure(stderr: str) -> str:
    """Map yt-dlp's stderr to a status.

    A 401 from the player page means the video is gated on the account and
    will never succeed by retrying, so it is RESTRICTED rather than an error.
    """
    text = str(stderr or "")
    if "HTTP Error 401" in text or "401 Unauthorized" in text:
        return RESTRICTED
    # yt-dlp's own message already begins "ERROR:"; take that line rather than
    # the first non-blank one, which is often just a WARNING.
    line = next((l.strip() for l in text.splitlines() if l.strip().startswith("ERROR:")), None)
    if line is None:
        line = next((l.strip() for l in text.splitlines() if l.strip()), "download failed")
    line = line[len("ERROR:"):].strip() if line.startswith("ERROR:") else line
    line = re.sub(r"https?://\S+", "<url>", line)
    return error_status(line)


def download_video(url: str, workdir: str) -> str:
    """Download and mux. Returns the path to the mp4. Raises VideoError."""
    if not is_vimeo_url(url):
        raise VideoError(error_status("not a Vimeo URL"))
    out_path = os.path.join(workdir, "video.%(ext)s")
    command = build_command(url, out_path)
    result = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise VideoError(classify_failure(result.stderr))

    produced = os.path.join(workdir, "video.mp4")
    if not os.path.exists(produced):
        raise VideoError(error_status("yt-dlp produced no mp4"))
    return produced


def has_audio(path: str) -> bool:
    """True when the file carries BOTH a video and an audio stream.

    The spec's rule is "every video must report both a video and an audio
    stream before upload; a silent file is never DONE" — so checking audio
    alone is not enough. A file that muxed into audio-only is just as broken
    as one that came out silent.
    """
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=120,
    )
    kinds = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return result.returncode == 0 and "video" in kinds and "audio" in kinds


class VideoError(Exception):
    """A per-row video failure. The message IS the status to record."""

    def __init__(self, status: str):
        super().__init__(status)
        self.status = status
