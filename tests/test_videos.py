import pytest
from worker.videos import (
    build_command, classify_failure, is_vimeo_url, vimeo_id,
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


def test_classify_failure_reports_missing_audio_separately():
    out = classify_failure("MUX_RESULT: no audio stream")
    assert out.startswith("ERROR: ")
