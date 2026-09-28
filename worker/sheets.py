"""Google Sheets access.

Status writes are batched into contiguous ranges so one run costs a handful
of API calls rather than one per row.
"""

import os

from googleapiclient.errors import HttpError

from worker.config import (
    DEFAULT_MAPPING, PROVISION_HEADERS, col_to_index, index_to_col,
)

CONFIG_TAB = "_config"


def spreadsheet_id() -> str:
    """The target spreadsheet. Never hardcoded — the repo is public."""
    return os.environ["SPREADSHEET_ID"]


def _sheet_props(service, tab: str) -> dict:
    """The tab's properties, including its grid width."""
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id(),
        fields="sheets.properties(sheetId,title,gridProperties)",
    ).execute()
    for entry in meta.get("sheets", []):
        props = entry.get("properties", {})
        if props.get("title") == tab:
            return props
    raise ValueError(f"tab not found: {tab}")


def _sheet_id(service, tab: str) -> int:
    """Numeric sheetId, needed for grid operations (title is not accepted)."""
    return _sheet_props(service, tab)["sheetId"]


def _grid_width(service, tab: str) -> int:
    """How many columns the tab physically has.

    This is NOT len(header): the values API omits trailing empty cells, so a
    6-column sheet whose header row has 3 entries reports a header of length 3.
    Sizing the widening from the header length appends columns nobody asked
    for, and those extra columns cannot have headers — the one outcome the
    operator's rule forbids.
    """
    return int(_sheet_props(service, tab).get("gridProperties", {}).get("columnCount", 0))


def read_rows(service, tab: str) -> list[list[str]]:
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id(), range=f"{_a1_tab(tab)}!A:ZZ",
    ).execute()
    return result.get("values", [])


def read_config(service) -> list[list[str]]:
    """Read the _config tab. Returns [] ONLY when the tab does not exist yet.

    Every other failure is re-raised: swallowing a 5xx or a permissions error
    here would be misread as "no _config", and the caller would then try to
    create a tab that already exists.
    """
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id(), range=f"{_a1_tab(CONFIG_TAB)}!A:B",
        ).execute()
        return result.get("values", [])
    except HttpError as exc:
        status = getattr(getattr(exc, "resp", None), "status", None)
        if status == 400:
            return []  # "Unable to parse range" == the tab is not there
        raise


def read_header(service, tab: str) -> list[str]:
    """The data tab's header row, or [] when the tab is empty."""
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id(), range=f"{_a1_tab(tab)}!1:1",
    ).execute()
    rows = result.get("values", [])
    return rows[0] if rows else []


def create_config_tab(service, tab: str, mapping: dict) -> None:
    """Create the _config tab and write the mapping with its headers.

    Written from the defaults so the operator has something concrete to
    correct, rather than an empty sheet to guess at. `tab` names the data
    tab the mapping will point at; it is not the tab being created.
    """
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id(),
        body={"requests": [{"addSheet": {"properties": {"title": CONFIG_TAB}}}]},
    ).execute()
    rows = [["key", "value"]] + [[key, mapping[key]] for key in DEFAULT_MAPPING]
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id(), range=f"{_a1_tab(CONFIG_TAB)}!A1:B{len(rows)}",
        valueInputOption="RAW", body={"values": rows},
    ).execute()


def _a1_tab(tab: str) -> str:
    """Quote a tab name for A1 notation.

    A tab whose name contains an apostrophe must have it doubled, e.g.
    "Bob's Data" -> 'Bob''s Data'. Unescaped, the range is malformed and the
    call fails for the whole run.
    """
    return "'" + str(tab).replace("'", "''") + "'"


def ensure_columns(service, tab: str, header: list[str], mapping: dict) -> None:
    """Add any missing mapped columns AND write their headers.

    A column with no header is not a valid outcome, so every mapped column
    that lacks a header gets one in the same run. The grid is widened ONCE to
    the highest missing index, then a header is written for every mapped
    column that is missing one — writing headers only for columns above the
    running width would silently leave a bare column whenever the mapping is
    not in ascending order.

    "Missing" is judged against the header row, not the grid width: a mapped
    column can sit inside a wide grid and still be empty (D and E were exactly
    that in production). But the WIDENING is sized from the tab's grid, not
    from len(header): the values API omits trailing empty cells, so a
    6-column sheet with a 3-entry header row would otherwise be widened by
    three columns, two of them bare.
    """
    header = header or []
    present = {i for i, text in enumerate(header) if str(text).strip()}
    width = max(_grid_width(service, tab), len(header))
    targets = []
    for key, header_text in PROVISION_HEADERS.items():
        idx = col_to_index(mapping.get(key, ""))
        if idx >= 0:
            targets.append((idx, header_text))
    missing = sorted((idx, text) for idx, text in targets if idx not in present)
    if not missing:
        return  # every mapped column already has its header

    sheet_id = _sheet_id(service, tab)
    grow = missing[-1][0] + 1 - width
    if grow > 0:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id(),
            body={"requests": [{"appendDimension": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "length": grow,
            }}]},
        ).execute()

    quoted = _a1_tab(tab)
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id(),
        body={"valueInputOption": "RAW", "data": [
            {"range": f"{quoted}!{index_to_col(idx)}1", "values": [[text]]}
            for idx, text in missing
        ]},
    ).execute()


def batch_status_payload(tab: str, status_col_index: int, updates: dict) -> list[dict]:
    """Collapse {row_index: status} into contiguous A1 ranges.

    `row_index` is 1-based (row 1 is the header). A run of adjacent rows
    becomes one range, so a full sheet costs a few calls, not one per row.
    """
    if not updates:
        return []
    letter = index_to_col(status_col_index)
    rows = sorted(updates)
    payload = []
    start = rows[0]
    run = [updates[start]]
    for row in rows[1:]:
        if row == start + len(run):
            run.append(updates[row])
        else:
            payload.append(_range(tab, letter, start, run))
            start = row
            run = [updates[row]]
    payload.append(_range(tab, letter, start, run))
    return payload


def _range(tab: str, letter: str, start: int, run: list) -> dict:
    first = f"{_a1_tab(tab)}!{letter}{start}"
    last = f"{letter}{start + len(run) - 1}"
    span = first if len(run) == 1 else f"{first}:{last}"
    return {"range": span, "values": [[value] for value in run]}


def write_statuses(service, tab: str, status_col_index: int, updates: dict) -> None:
    payload = batch_status_payload(tab, status_col_index, updates)
    if not payload:
        return
    # num_retries: this is the single end-of-run write, and a transient 5xx
    # here would discard the record of a run that already did all its work
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id(),
        body={"valueInputOption": "RAW", "data": payload},
    ).execute(num_retries=3)
