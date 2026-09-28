from worker.config import DEFAULT_MAPPING
from worker.main import row_plan


def _rows():
    return [
        ["username", "image_path", "video_path", "image_folder", "video_folder", "status"],
        ["alice", "http://i/1.jpg", "https://player.vimeo.com/video/1", "F1", "F1", ""],
        ["bob", "http://i/2.jpg", "", "F1", "", ""],
        ["carol", "", "", "", "", ""],
        ["dave", "http://i/3.jpg", "https://player.vimeo.com/video/3", "", "", "DONE"],
    ]


def test_row_plan_skips_done_rows():
    plan = row_plan(_rows(), dict(DEFAULT_MAPPING))
    usernames = [r["username"] for r in plan]
    assert "dave" not in usernames


def test_row_plan_includes_image_only_row():
    plan = row_plan(_rows(), dict(DEFAULT_MAPPING))
    bob = next(r for r in plan if r["username"] == "bob")
    assert bob["has_image"] is True
    assert bob["has_video"] is False


def test_row_plan_marks_row_with_no_media():
    plan = row_plan(_rows(), dict(DEFAULT_MAPPING))
    carol = next(r for r in plan if r["username"] == "carol")
    assert carol["has_image"] is False and carol["has_video"] is False


def test_row_plan_fills_folder_down():
    rows = _rows()
    rows[2][4] = ""  # bob's video folder blank
    plan = row_plan(rows, dict(DEFAULT_MAPPING))
    bob = next(r for r in plan if r["username"] == "bob")
    assert bob["video_folder"] == "F1"  # inherited from the row above
