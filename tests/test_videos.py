import subprocess
from pathlib import Path

import pytest

from worker.videos import (
    VideoError, build_command, classify_failure, download_video, has_audio,
    is_vimeo_url, vimeo_id,
)


@pytest.mark.parametrize("url,ok", [
    ("https://player.vimeo.com/video/1178320400", True),
    ("https://vimeo.com/1178320400", True),
    ("https://www.example.com/uploads/videos/abc.mov", False),
    ("", False),
])
def test_is_vimeo_url(url, ok):
    assert is_vimeo_url(url) is ok


def test_vimeo_id_extracts_digits():
    assert vimeo_id("https://player.vimeo.com/video/1178320400") == "1178320400"
    assert vimeo_id("https://vimeo.com/1178320400") == "1178320400"
    assert vimeo_id("https://example.com/x") is None


def test_build_command_prefers_muxed_mp4_and_forces_mp4_container():
    cmd = build_command("https://player.vimeo.com/video/1", "/tmp/out.mp4")
    assert cmd[0] == "yt-dlp"
    assert "--merge-output-format" in cmd
    assert cmd[cmd.index("--merge-output-format") + 1] == "mp4"
    assert cmd[-1] == "https://player.vimeo.com/video/1"
    assert "-o" in cmd


def test_classify_failure_detects_unauthorized_as_restricted():
    assert classify_failure("ERROR: Unable to download webpage: HTTP Error 401") == "RESTRICTED"


def test_classify_failure_other_errors_are_errors():
    out = classify_failure("ERROR: [vimeo] something else broke")
    assert out.startswith("ERROR: ")
    assert "ERROR: ERROR:" not in out  # yt-dlp's own prefix must not be doubled


def test_classify_failure_does_not_stop_at_a_warning():
    # yt-dlp prints warnings before the real error; the status must carry the ERROR line
    out = classify_failure("WARNING: falling back\nERROR: the actual problem")
    assert "the actual problem" in out


def test_classify_failure_reports_missing_audio_separately():
    out = classify_failure("MUX_RESULT: no audio stream")
    assert out.startswith("ERROR: ")


def test_non_vimeo_url_raises_an_in_vocabulary_status():
    # an old non-Vimeo upload URL value must not produce a bare string
    with pytest.raises(VideoError) as caught:
        download_video("https://www.example.com/uploads/videos/abc.mov", "/tmp")
    assert caught.value.status.startswith("ERROR: ")


# has_audio is the only guard that keeps a broken file out of Drive, and it
# shells out to ffprobe. The files are generated with ffmpeg (which the CI
# runner installs) rather than committed, so the repo carries no binaries.
_FIXTURES = Path(__file__).parent / "_media_fixtures"


@pytest.fixture(scope="module")
def media_fixtures():
    _FIXTURES.mkdir(exist_ok=True)
    both, silent, audio_only = (_FIXTURES / n for n in
                                ("both.mp4", "silent.mp4", "audio_only.m4a"))
    if not (both.exists() and silent.exists() and audio_only.exists()):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=black:s=16x16:d=0.2",
                        "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-shortest",
                        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
                        str(both)], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=black:s=16x16:d=0.2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                        str(silent)], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", "0.2",
                        "-c:a", "aac", str(audio_only)], check=True)
    return {"both": both, "silent": silent, "audio_only": audio_only}


def test_has_audio_accepts_a_file_with_both_streams(media_fixtures):
    assert has_audio(str(media_fixtures["both"])) is True


def test_has_audio_rejects_a_video_only_file(media_fixtures):
    # a silent file must never be DONE: audio is required alongside the video
    assert has_audio(str(media_fixtures["silent"])) is False


def test_has_audio_rejects_an_audio_only_file(media_fixtures):
    # the reverse case: a file that muxed into audio-only is just as broken
    assert has_audio(str(media_fixtures["audio_only"])) is False


def test_has_audio_rejects_a_missing_file():
    assert has_audio("/nonexistent/path.mp4") is False


def test_is_vimeo_url_rejects_a_lookalike_host():
    # the ID regex is anchored to the vimeo host, so a host that merely has
    # "vimeo.com" in its path is not a Vimeo URL
    assert is_vimeo_url("https://evil.test/vimeo.com/12345") is False
    assert vimeo_id("https://evil.test/vimeo.com/12345") is None
