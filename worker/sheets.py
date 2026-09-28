"""Google Sheets access.

Status writes are batched into contiguous ranges so one run costs a handful
of API calls rather than one per row.
"""

import os

from worker.config import (
    DEFAULT_MAPPING, PROVISION_HEADERS, col_to_index, index_to_col,
)

CONFIG_TAB = "_config"


def spreadsheet_id() -> str:
    """The target spreadsheet. Never hardcoded — the repo is public."""
    return os.environ["SPREADSHEET_ID"]


def _sheet_id(service, tab: str) -> int:
    """Numeric sheetId, needed for grid operations (title is not accepted)."""
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id(), fields="sheets.properties(sheetId,title)",
    ).execute()
    for entry in meta.get("sheets", []):
        props = entry.get("properties", {})
        if props.get("title") == tab:
            return props["sheetId"]
    raise ValueError(f"tab not found: {tab}")


def read_rows(service, tab: str) -> list[list[str]]:
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id(), range=f"'{tab}'!A:ZZ",
    ).execute()
    return result.get("values", [])


def read_config(service) -> list[list[str]]:
    """Read the _config tab. Returns [] when the tab does not exist yet."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id(), range=f"'{CONFIG_TAB}'!A:B",
        ).execute()
        return result.get("values", [])
    except Exception:
        return []


def read_header(service, tab: str) -> list[str]:
    """The data tab's header row, or [] when the tab is empty."""
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id(), range=f"'{tab}'!1:1",
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
        spreadsheetId=spreadsheet_id(), range=f"'{CONFIG_TAB}'!A1:B{len(rows)}",
        valueInputOption="RAW", body={"values": rows},
    ).execute()


def ensure_columns(service, tab: str, header: list[str], mapping: dict) -> None:
    """Add any missing mapped columns AND write their headers.

    A column with no header is not a valid outcome, so the header is written
    in the same task as the widening. Idempotent: a column that already
    exists is left alone.
    """
    width = len(header or [])
    sheet_id = None
    header_updates = []
    for key, header_text in PROVISION_HEADERS.items():
        idx = col_to_index(mapping.get(key, ""))
        if idx < 0 or idx < width:
            continue  # absent from the mapping, or already present
        if sheet_id is None:
            sheet_id = _sheet_id(service, tab)
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id(),
            body={"requests": [{"appendDimension": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "length": idx + 1 - width,
            }}]},
        ).execute()
        width = idx + 1
        header_updates.append({
            "range": f"'{tab}'!{index_to_col(idx)}1",
            "values": [[header_text]],
        })
    if header_updates:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id(),
            body={"valueInputOption": "RAW", "data": header_updates},
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
    first = f"'{tab}'!{letter}{start}"
    last = f"{letter}{start + len(run) - 1}"
    span = first if len(run) == 1 else f"{first}:{last}"
    return {"range": span, "values": [[value] for value in run]}


def write_statuses(service, tab: str, status_col_index: int, updates: dict) -> None:
    payload = batch_status_payload(tab, status_col_index, updates)
    if not payload:
        return
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id(),
        body={"valueInputOption": "RAW", "data": payload},
    ).execute()
