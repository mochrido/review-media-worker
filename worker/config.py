"""Column mapping.

The worker does not hardcode columns. The operator declares them in a
_config tab; anything absent is provisioned with a header, never guessed.
"""

import re

DEFAULT_MAPPING = {
    "data_tab": "Sheet1",
    "username_col": "A",
    "image_url_col": "B",
    "image_folder_col": "D",
    "video_url_col": "C",
    "video_folder_col": "E",
    "status_col": "F",
}

# header text written when the worker provisions a column
PROVISION_HEADERS = {
    "image_folder_col": "image_folder",
    "video_folder_col": "video_folder",
    "status_col": "status",
}

_LETTERS = re.compile(r"^[A-Z]+$")


def col_to_index(letter: str) -> int:
    """'A' -> 0, 'AA' -> 26. Returns -1 for anything invalid."""
    if not letter:
        return -1
    clean = str(letter).strip().upper()
    if not _LETTERS.match(clean):
        return -1
    total = 0
    for ch in clean:
        total = total * 26 + (ord(ch) - 64)
    return total - 1


def index_to_col(index: int) -> str:
    """0 -> 'A', 26 -> 'AA'."""
    if index < 0:
        raise ValueError("column index must be >= 0")
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def parse_mapping(rows) -> dict:
    """Read the _config tab: a `key`/`value` header plus one row per key.

    Unknown keys are ignored; absent keys fall back to DEFAULT_MAPPING, so a
    partially-filled _config still yields a complete mapping.
    """
    mapping = dict(DEFAULT_MAPPING)
    for row in rows or []:
        if len(row) < 2:
            continue
        key = str(row[0]).strip()
        value = str(row[1]).strip()
        if not key or not value or key == "key":
            continue
        if key in DEFAULT_MAPPING:
            mapping[key] = value
    return mapping


def missing_columns(mapping: dict, header) -> dict:
    """Return {mapping_key: header_text} for mapped columns that are absent.

    Presence is judged by the column letter against the header row length.
    """
    missing = {}
    width = len(header or [])
    for key, header_text in PROVISION_HEADERS.items():
        idx = col_to_index(mapping.get(key, ""))
        if idx < 0:
            continue
        if idx >= width:
            missing[key] = header_text
    return missing
