import sys

import pytest

from worker import main as main_mod
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


# --------------------------------------------------------------------------
# main() end-to-end. row_plan-only tests are what let C1 through: they were
# green while the whole run was broken, because nothing exercised the wire-up
# between reading the mapping, planning, processing and writing back.
# --------------------------------------------------------------------------

class _FakeSheets:
    """Stands in for the Sheets service, recording the status write."""

    def __init__(self, rows, config_rows):
        self._rows = rows
        self._config_rows = config_rows
        self.written = None
        self.widened = None

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, **kwargs):
        outer = self
        rng = kwargs.get("range", "")

        class _Req:
            def execute(self_inner, **kw):
                if "_config" in rng:
                    return {"values": outer._config_rows}
                return {"values": outer._rows}

        return _Req()

    def batchUpdate(self, **kwargs):
        outer = self
        if "body" in kwargs and "data" in kwargs["body"]:
            outer.written = kwargs["body"]["data"]

        class _Req:
            def execute(self_inner, **kw):
                return {}

        return _Req()

    def spreadsheets_batch(self):
        return self

    def appendDimension(self, **kwargs):
        return self

    def batchUpdateSpreadsheet(self, **kwargs):
        return self


def _run_main(monkeypatch, sheets, drive, argv=()):
    monkeypatch.setattr(sys, "argv", ["main", *argv])
    monkeypatch.setattr(main_mod, "_service", lambda: (sheets, drive))
    monkeypatch.setattr(main_mod.sheets, "read_config", lambda service: service._config_rows)
    monkeypatch.setattr(main_mod.sheets, "read_rows", lambda service, tab: service._rows)
    monkeypatch.setattr(main_mod, "bootstrap", lambda *a, **k: False)
    monkeypatch.setattr(main_mod.sheets, "write_statuses",
                        lambda service, tab, col, updates: setattr(service, "updates", updates))
    return main_mod.main()


def _patch_drive(monkeypatch, uploaded, folders_ok=True):
    """process_row calls the drive MODULE's functions, not the service object,
    so those are what must be patched."""
    def folder_id_from_url(url):
        if not url:
            raise ValueError("could not read a folder ID from this URL")
        return url.replace("FOLDER-", "")

    def find_existing(service, folder, name):
        return None

    def upload(service, folder, name, data, mime):
        uploaded.append(folder)
        return {"id": "x"}

    monkeypatch.setattr(main_mod.drive, "folder_id_from_url", folder_id_from_url)
    monkeypatch.setattr(main_mod.drive, "find_existing", find_existing)
    monkeypatch.setattr(main_mod.drive, "upload", upload)


def test_main_resumes_a_run_whose_first_row_is_already_done(monkeypatch):
    # THE C1 CASE, end to end. Row 2 is already DONE and holds the folder; rows
    # 3-4 have blank folder cells and must inherit it. When row_plan skipped the
    # DONE row before reading its folders, every continuation row got an empty
    # folder and failed with an error retrying could never clear — and no test
    # noticed, because only row_plan was ever exercised.
    rows = [
        ["username", "image_path", "video_path", "image_folder", "video_folder", "status"],
        ["done-row", "", "", "FOLDER-F1", "FOLDER-F1", "DONE"],
        ["alice", "http://i/1.jpg", "", "", "", ""],
        ["carol", "", "", "", "", ""],
    ]
    sheets = _FakeSheets(rows, [["key", "value"]])
    uploaded = []
    _patch_drive(monkeypatch, uploaded)

    import worker.images as images_mod
    monkeypatch.setattr(images_mod, "fetch_image", lambda url, session: (b"JPEG", "image/jpeg"))

    assert _run_main(monkeypatch, sheets, object()) == 0
    assert sheets.updates == {3: "DONE", 4: "NO_MEDIA"}, sheets.updates
    assert uploaded == ["F1"], f"expected the inherited folder, got {uploaded}"


def test_main_reports_every_row_and_writes_its_status(monkeypatch):
    rows = [
        ["username", "image_path", "video_path", "image_folder", "video_folder", "status"],
        ["alice", "http://i/1.jpg", "", "FOLDER-A", "", ""],
        ["carol", "", "", "", "", ""],
    ]
    sheets = _FakeSheets(rows, [["key", "value"]])
    uploaded = []
    _patch_drive(monkeypatch, uploaded)

    import worker.images as images_mod
    monkeypatch.setattr(images_mod, "fetch_image", lambda url, session: (b"JPEG", "image/jpeg"))

    assert _run_main(monkeypatch, sheets, object()) == 0
    assert sheets.updates == {2: "DONE", 3: "NO_MEDIA"}


def test_main_reports_a_failed_download_as_its_error_not_done(monkeypatch):
    # a row whose download fails must never be DONE
    rows = [
        ["username", "image_path", "video_path", "image_folder", "video_folder", "status"],
        ["alice", "http://i/1.jpg", "", "FOLDER-A", "", ""],
    ]
    sheets = _FakeSheets(rows, [["key", "value"]])
    _patch_drive(monkeypatch, [])

    import worker.images as images_mod

    def boom(url, session):
        raise images_mod.ImageError("ERROR: boom")

    monkeypatch.setattr(images_mod, "fetch_image", boom)

    assert _run_main(monkeypatch, sheets, object()) == 0
    assert sheets.updates[2].startswith("ERROR:"), sheets.updates
    assert sheets.updates[2] != "DONE"


def test_main_returns_2_on_a_bad_config_value(monkeypatch, capsys):
    rows = [["username", "image_path", "video_path", "image_folder", "video_folder", "status"]]
    sheets = _FakeSheets(rows, [["key", "value"], ["status_col", "Status"]])

    assert _run_main(monkeypatch, sheets, object()) == 2
    out = capsys.readouterr().out
    assert "status_col" in out and "Status" in out  # names the offending key
    assert "Traceback" not in out                    # not a stack trace


def test_main_dry_run_writes_nothing(monkeypatch):
    rows = [
        ["username", "image_path", "video_path", "image_folder", "video_folder", "status"],
        ["alice", "http://i/1.jpg", "", "F1", "", ""],
    ]
    sheets = _FakeSheets(rows, [["key", "value"]])
    monkeypatch.setattr(main_mod.images, "fetch_image",
                        lambda *a, **k: pytest.fail("dry run must not download"))

    assert _run_main(monkeypatch, sheets, object(), argv=("--dry-run",)) == 0
    assert not hasattr(sheets, "updates")
