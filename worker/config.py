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
# A real column letter: at most three letters, which covers every column a
# real sheet uses (XFD is the last). "Status" is not a column letter.
_COLUMN_LETTER = re.compile(r"^[A-Za-z]{1,3}$")


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


def parse_mapping(rows: list[list[str]]) -> dict:
    """Read the _config tab: a `key`/`value` header plus one row per key.

    Unknown keys are ignored; absent keys fall back to DEFAULT_MAPPING, so a
    partially-filled _config still yields a complete mapping.

    Every `*_col` value is validated as a column letter. A typo would otherwise
    become a six-figure index ('Status' -> 234917324) or an unusable -1, and
    both fail in ways the operator cannot read: the run widens the sheet to an
    absurd width, or processes every row and then writes nothing at all.
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
    validate_mapping(mapping)
    return mapping


class ConfigError(Exception):
    """The _config tab holds a value that cannot work."""


def validate_mapping(mapping: dict) -> None:
    """Raise ConfigError naming the key and value that are wrong.

    `data_tab` is free text; every other key must be a column letter. The check
    is a shape check, not `col_to_index(...) >= 0`: that function happily reads
    any run of letters, so "Status" would pass as column 234917324 and the run
    would try to widen the sheet to that width. Real sheets stop at three
    letters (ZZZ), so anything longer is a typo.
    """
    for key, value in mapping.items():
        if key == "data_tab":
            continue
        if not _COLUMN_LETTER.match(str(value).strip()):
            raise ConfigError(
                f"{key} is {value!r}, which is not a column letter "
                "(expected something like A, B or AA)"
            )
