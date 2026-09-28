import pytest

from worker.config import DEFAULT_MAPPING
from worker.sheets import batch_status_payload, ensure_columns, write_statuses


def test_batch_payload_collapses_contiguous_rows():
    payload = batch_status_payload("Sheet1", 5, {2: "DONE", 3: "DONE", 7: "NO_MEDIA"})
    assert [p["range"] for p in payload] == ["'Sheet1'!F2:F3", "'Sheet1'!F7"]
    assert payload[0]["values"] == [["DONE"], ["DONE"]]


def test_batch_payload_single_row():
    payload = batch_status_payload("Sheet1", 5, {4: "DONE"})
    assert payload[0]["range"] == "'Sheet1'!F4"


def test_batch_payload_empty_when_no_updates():
    assert batch_status_payload("Sheet1", 5, {}) == []


class _FakeRequest:
    def __init__(self, result=None):
        self._result = result if result is not None else {}

    def execute(self):
        return self._result


class _FakeValues:
    def __init__(self, log):
        self._log = log

    def batchUpdate(self, **kwargs):
        self._log.append(("values.batchUpdate", kwargs))
        return _FakeRequest()

    def update(self, **kwargs):
        self._log.append(("values.update", kwargs))
        return _FakeRequest()


class _FakeSpreadsheets:
    def __init__(self, log):
        self._log = log

    def get(self, **kwargs):
        return _FakeRequest({"sheets": [{"properties": {"sheetId": 7, "title": "Sheet1"}}]})

    def batchUpdate(self, **kwargs):
        self._log.append(("spreadsheets.batchUpdate", kwargs))
        return _FakeRequest()

    def values(self):
        return _FakeValues(self._log)


class _FakeService:
    def __init__(self):
        self.log = []

    def spreadsheets(self):
        return _FakeSpreadsheets(self.log)


@pytest.fixture(autouse=True)
def _spreadsheet_id(monkeypatch):
    monkeypatch.setenv("SPREADSHEET_ID", "fake-id")


def test_write_statuses_issues_a_single_batch_call():
    service = _FakeService()
    write_statuses(service, "Sheet1", 5, {2: "DONE", 3: "DONE", 7: "NO_MEDIA"})
    calls = [c for c in service.log if c[0] == "values.batchUpdate"]
    assert len(calls) == 1, "one run must cost one call, not one call per row"
    ranges = [d["range"] for d in calls[0][1]["body"]["data"]]
    assert ranges == ["'Sheet1'!F2:F3", "'Sheet1'!F7"]


def test_ensure_columns_widens_the_grid_and_writes_each_header():
    # the operator's rule: a new column must never exist without its header
    service = _FakeService()
    header = ["username", "image_path", "video_path"]  # width 3, so D/E/F are absent
    ensure_columns(service, "Sheet1", header, dict(DEFAULT_MAPPING))
    assert [c for c in service.log if c[0] == "spreadsheets.batchUpdate"], \
        "the grid must be widened for the missing columns"
    written = [c for c in service.log if c[0] == "values.batchUpdate"][-1]
    assert [d["range"] for d in written[1]["body"]["data"]] == \
        ["'Sheet1'!D1", "'Sheet1'!E1", "'Sheet1'!F1"]
    assert [d["values"][0][0] for d in written[1]["body"]["data"]] == \
        ["image_folder", "video_folder", "status"]


def test_ensure_columns_is_a_no_op_when_the_headers_already_exist():
    service = _FakeService()
    header = ["username", "image_path", "video_path", "image_folder", "video_folder", "status"]
    ensure_columns(service, "Sheet1", header, dict(DEFAULT_MAPPING))
    assert service.log == [], "existing columns must be left alone"

def test_ensure_columns_writes_a_header_for_every_column_it_creates():
    # the operator's rule: a column must never exist without its header.
    # A mapping whose columns are NOT in ascending order used to create a bare
    # column, because a header was only written when the index was still beyond
    # the running grid width.
    service = _FakeService()
    header = ["username", "image_path", "video_path"]  # width 3
    mapping = dict(DEFAULT_MAPPING)
    mapping.update(image_folder_col="E", video_folder_col="D", status_col="H")

    ensure_columns(service, "Sheet1", header, mapping)

    written = [c for c in service.log if c[0] == "values.batchUpdate"][-1]
    ranges = {d["range"]: d["values"][0][0] for d in written[1]["body"]["data"]}
    assert ranges == {
        "'Sheet1'!E1": "image_folder",
        "'Sheet1'!D1": "video_folder",
        "'Sheet1'!H1": "status",
    }, "every mapped column must get its header, whatever the mapping order"


def test_a1_tab_escapes_an_apostrophe_in_the_tab_name():
    # "Bob's Data" is a legal tab name; interpolated raw it produces the
    # malformed range 'Bob's Data'!A1 and the whole run fails
    from worker.sheets import _a1_tab
    assert _a1_tab("Bob's Data") == "'Bob''s Data'"
    assert _a1_tab("Sheet1") == "'Sheet1'"


def test_write_statuses_escapes_an_apostrophe_in_the_tab_name():
    service = _FakeService()
    write_statuses(service, "Bob's Data", 5, {2: "DONE"})
    call = [c for c in service.log if c[0] == "values.batchUpdate"][0]
    assert call[1]["body"]["data"][0]["range"] == "'Bob''s Data'!F2"
