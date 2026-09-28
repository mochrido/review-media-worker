import pytest
from worker.config import (
    DEFAULT_MAPPING, ConfigError, col_to_index, index_to_col, parse_mapping,
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


def test_parse_mapping_rejects_a_word_where_a_column_letter_is_expected():
    # "Status" is all letters, so col_to_index() happily returns 234917324 and
    # the run would try to widen the sheet to that many columns.
    rows = [["key", "value"], ["status_col", "Status"]]
    with pytest.raises(ConfigError) as caught:
        parse_mapping(rows)
    assert "status_col" in str(caught.value)
    assert "Status" in str(caught.value)


def test_parse_mapping_rejects_a_digit_value():
    # "1" yields -1, and the run would process every row then write nothing
    with pytest.raises(ConfigError):
        parse_mapping([["key", "value"], ["username_col", "1"]])


def test_parse_mapping_accepts_letters_and_leaves_data_tab_alone():
    rows = [["key", "value"], ["data_tab", "my data tab"], ["username_col", "AA"]]
    mapping = parse_mapping(rows)
    assert mapping["username_col"] == "AA"
    assert mapping["data_tab"] == "my data tab"  # free text, not a column
