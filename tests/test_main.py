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


def test_done_row_still_anchors_the_folder_fill_down():
    # On a resume run the first data row is often already DONE. Its folder cell
    # must still seed the fill-down: skipping before reading it leaves every
    # continuation row with an empty folder, which fails in a way that
    # retrying cannot clear (the row above stays DONE forever).
    rows = [
        ["username", "image_path", "video_path", "image_folder", "video_folder", "status"],
        ["done-row", "http://i/1.jpg", "https://player.vimeo.com/video/1", "F1", "F1", "DONE"],
        ["next-row", "http://i/2.jpg", "https://player.vimeo.com/video/2", "", "", ""],
    ]
    plan = row_plan(rows, dict(DEFAULT_MAPPING))
    assert [r["username"] for r in plan] == ["next-row"], "the DONE row is not processed"
    assert plan[0]["image_folder"] == "F1"
    assert plan[0]["video_folder"] == "F1"


def test_a_done_row_without_a_folder_does_not_break_the_fill_down():
    # the DONE row carries no folder of its own; the row above it still wins
    rows = [
        ["username", "image_path", "video_path", "image_folder", "video_folder", "status"],
        ["anchor", "http://i/1.jpg", "https://player.vimeo.com/video/1", "TOP", "TOP", ""],
        ["done-row", "", "", "", "", "DONE"],
        ["next-row", "http://i/2.jpg", "https://player.vimeo.com/video/2", "", "", ""],
    ]
    plan = row_plan(rows, dict(DEFAULT_MAPPING))
    assert plan[0]["video_folder"] == "TOP"
