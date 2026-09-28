import pytest

from worker.config import DEFAULT_MAPPING
from worker.sheets import (
    batch_status_payload, ensure_columns, read_config, write_statuses,
)


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

    def execute(self, **kwargs):
        # the real client accepts num_retries; the fake must too, or it would
        # hide a call the implementation actually makes
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


def _http_error(status):
    """A real googleapiclient HttpError — it needs an httplib2.Response."""
    import httplib2
    from googleapiclient.errors import HttpError

    response = httplib2.Response({"status": str(status)})
    response.status = status
    return HttpError(response, b"{}")


def test_read_config_returns_empty_only_for_a_missing_tab():
    # 400 "Unable to parse range" is how a missing tab shows up
    class Missing:
        def spreadsheets(self):
            return self

        def values(self):
            return self

        def get(self, **kwargs):
            return self

        def execute(self):
            raise _http_error(400)

    assert read_config(Missing()) == []


def test_read_config_propagates_a_server_error():
    # a 5xx must NOT look like "no _config", or the caller tries to create a
    # tab that already exists
    from googleapiclient.errors import HttpError

    class Flaky:
        def spreadsheets(self):
            return self

        def values(self):
            return self

        def get(self, **kwargs):
            return self

        def execute(self):
            raise _http_error(503)

    with pytest.raises(HttpError):
        read_config(Flaky())


def test_write_statuses_asks_the_client_to_retry():
    # the final status write is the only record of a run that already did all
    # its work, so it must be issued with retries. num_retries is an execute()
    # argument, so the fake request captures it there.
    seen = {}

    class CapturingRequest(_FakeRequest):
        def execute(self, **kwargs):
            seen.update(kwargs)
            return {}

    class Svc(_FakeService):
        def spreadsheets(self):
            outer = self

            class S(_FakeSpreadsheets):
                def values(self_inner):
                    class V(_FakeValues):
                        def batchUpdate(self_v, **kwargs):
                            return CapturingRequest()
                    return V(outer.log)
            return S(outer.log)

    write_statuses(Svc(), "Sheet1", 5, {2: "DONE"})
    assert seen.get("num_retries") == 3


class _GridFake:
    """A service whose data tab has a real grid width, as the API reports it.

    The values API omits trailing empty cells, so a 5-column grid whose header
    row holds 3 entries reports a header of length 3. The grid width is a
    separate number and is what the widening must be sized from.
    """

    def __init__(self, grid_width):
        self._grid_width = grid_width
        self.written = []
        self.appended = []

    def spreadsheets(self):
        outer = self

        class _S:
            def get(self_inner, **kwargs):
                return _Req({"sheets": [{"properties": {
                    "sheetId": 7, "title": "Sheet1",
                    "gridProperties": {"columnCount": outer._grid_width},
                }}]})

            def batchUpdate(self_inner, **kwargs):
                reqs = kwargs["body"]["requests"]
                for r in reqs:
                    if "appendDimension" in r:
                        outer.appended.append(r["appendDimension"]["length"])
                return _Req({})

            def values(self_inner):
                class _V:
                    def batchUpdate(self_v, **kwargs):
                        for d in kwargs["body"]["data"]:
                            outer.written.append((d["range"], d["values"]))
                        return _Req({})
                return _V()

        return _S()

    def appended_lengths(self):
        return self.appended


class _Req:
    def __init__(self, result=None):
        self._result = result or {}

    def execute(self, **kwargs):
        return self._result


def test_ensure_columns_does_not_create_bare_columns_when_the_grid_is_wider_than_the_header():
    # Real case: the sheet's grid was 5 columns wide but its header row had only
    # 3 entries (the values API omits trailing empties). Sizing the widening from
    # the header length appended 3 columns instead of 1, leaving G1 and H1 with
    # no header — the one outcome that is never acceptable.
    forged = _GridFake(grid_width=5)
    ensure_columns(forged, "Sheet1", ["username", "image_path", "video_path"], dict(DEFAULT_MAPPING))

    assert forged.appended_lengths() == [1], \
        f"expected exactly one column added, added {forged.appended_lengths()}"

    headed = {r.split("!")[-1] for r, _ in forged.written}
    assert headed == {"D1", "E1", "F1"}, headed
    assert "G1" not in headed and "H1" not in headed, "no column may be left bare"


def test_ensure_columns_heads_a_mapping_inside_a_wide_grid_without_widening_it():
    # A 6-column grid whose header row has 3 entries: D/E/F exist as empty
    # columns but have no headers. They must be headed, and because the grid is
    # already wide enough, nothing may be appended (an append of length 0 is
    # rejected by the API).
    forged = _GridFake(grid_width=6)
    ensure_columns(forged, "Sheet1", ["username", "image_path", "video_path"], dict(DEFAULT_MAPPING))

    assert forged.appended_lengths() == [], "the grid is wide enough; nothing to append"
    headed = {r.split("!")[-1] for r, _ in forged.written}
    assert headed == {"D1", "E1", "F1"}, headed


def test_ensure_columns_is_a_true_no_op_when_every_mapped_column_is_headed():
    forged = _GridFake(grid_width=6)
    ensure_columns(forged, "Sheet1",
                   ["username", "image_path", "video_path",
                    "image_folder", "video_folder", "status"], dict(DEFAULT_MAPPING))
    assert forged.appended_lengths() == []
    assert forged.written == [], "nothing to do when every header is present"
