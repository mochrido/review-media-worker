import typing

import pytest
from worker.config import (
    DEFAULT_MAPPING, col_to_index, index_to_col, missing_columns, parse_mapping,
)


@pytest.mark.parametrize("letter,idx", [("A", 0), ("B", 1), ("Z", 25), ("AA", 26), ("AB", 27)])
def test_col_to_index(letter, idx):
    assert col_to_index(letter) == idx


@pytest.mark.parametrize("idx,letter", [(0, "A"), (25, "Z"), (26, "AA"), (27, "AB")])
def test_index_to_col(idx, letter):
    assert index_to_col(idx) == letter


def test_col_to_index_rejects_junk():
    assert col_to_index("1") == -1
    assert col_to_index("") == -1
    assert col_to_index("A1") == -1


def test_parse_mapping_reads_key_value_rows():
    rows = [["key", "value"], ["data_tab", "Sheet1"], ["username_col", "A"]]
    mapping = parse_mapping(rows)
    assert mapping["data_tab"] == "Sheet1"
    assert mapping["username_col"] == "A"
    # unlisted keys fall back to defaults
    assert mapping["status_col"] == DEFAULT_MAPPING["status_col"]


def test_parse_mapping_ignores_blank_rows():
    rows = [["key", "value"], ["", ""], ["username_col", "A"]]
    assert parse_mapping(rows)["username_col"] == "A"


def test_missing_columns_reports_absent_headers():
    mapping = dict(DEFAULT_MAPPING)
    header = ["username", "image_path", "video_path"]
    missing = missing_columns(mapping, header)
    # image_folder / video_folder / status are not in the header yet
    assert set(missing) == {"image_folder_col", "video_folder_col", "status_col"}


def test_missing_columns_empty_when_all_present():
    mapping = dict(DEFAULT_MAPPING)
    header = ["username", "image_path", "video_path",
              "image_folder", "video_folder", "status"]
    assert missing_columns(mapping, header) == {}


def test_interfaces_signatures_carry_their_annotations():
    # the Interfaces section names these types; an unannotated signature is a
    # silent drift from the published contract
    assert typing.get_type_hints(parse_mapping) == {"rows": list[list[str]], "return": dict}
    assert typing.get_type_hints(missing_columns) == {
        "mapping": dict, "header": list[str], "return": dict}
