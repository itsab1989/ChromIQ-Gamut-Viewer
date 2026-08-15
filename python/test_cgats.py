"""Reading CGATS — and in particular the files that hold more than one table."""
from __future__ import annotations

import pytest

import cgats

# A .ti1 exactly as ArgyllCMS targen writes one: THREE tables. The second and
# third are reference values about the chart, not patches to print, and the
# DESCRIPTOR line inside the second is the word a naive reader trips over.
A_REAL_TI1 = """CTI1

DESCRIPTOR "Argyll Calibration Target chart information 1"
ORIGINATOR "Argyll targen"
CREATED "Thu Aug 13 20:55:41 2026"
APPROX_WHITE_POINT "95.106486 100.000000 108.844025"
COLOR_REP "iRGB"
WHITE_COLOR_PATCHES "2"

NUMBER_OF_FIELDS 7
BEGIN_DATA_FORMAT
SAMPLE_ID RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z
END_DATA_FORMAT

NUMBER_OF_SETS 3
BEGIN_DATA
1 100.0000 100.0000 100.0000 95.10649 100.0000 108.8440
2 0.00000 0.00000 0.00000 1.000000 1.000000 1.000000
3 50.00000 50.00000 50.00000 21.14266 22.19007 24.08306
END_DATA
CTI1

DESCRIPTOR "Argyll Calibration Target chart information 1"
ORIGINATOR "Argyll targen"
DENSITY_EXTREME_VALUES "2"

NUMBER_OF_FIELDS 7
BEGIN_DATA_FORMAT
INDEX RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z
END_DATA_FORMAT

NUMBER_OF_SETS 2
BEGIN_DATA
0 100.0000 100.0000 100.0000 95.10649 100.0000 108.8440
1 0.00000 0.00000 0.00000 1.000000 1.000000 1.000000
END_DATA
"""

#: A .ti2 — one table, and sheet positions in quotes.
A_REAL_TI2 = """CTI2

DESCRIPTOR "Argyll Calibration Target chart information 2"
ORIGINATOR "ChromIQ layout engine"
TARGET_INSTRUMENT "X-Rite ColorMunki"
COLOR_REP "iRGB"

NUMBER_OF_FIELDS 8
BEGIN_DATA_FORMAT
SAMPLE_ID SAMPLE_LOC RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z
END_DATA_FORMAT

NUMBER_OF_SETS 2
BEGIN_DATA
1 "E11" 100.00000 100.00000 100.00000 95.10649 100.00000 108.84400
2 "A1" 0.00000 0.00000 0.00000 1.00000 1.00000 1.00000
END_DATA
"""


def test_a_ti1_is_three_tables_and_only_the_first_holds_the_chart():
    """THE BUG THIS MODULE EXISTS FOR. Reading from the first BEGIN_DATA to the
    last END_DATA swallows every table and the headers between them; the first
    thing a number parser then meets is a word out of a DESCRIPTOR line, and it
    reports `could not convert string to float: 'chart'` on a file that is
    perfectly well formed."""
    tables = cgats.read_tables(A_REAL_TI1)
    assert len(tables) == 2
    assert len(tables[0]) == 3
    assert len(tables[1]) == 2
    assert tables[0].columns[:4] == ("SAMPLE_ID", "RGB_R", "RGB_G", "RGB_B")


def test_no_row_carries_a_word_from_a_header():
    for table in cgats.read_tables(A_REAL_TI1):
        for row in table.rows:
            assert "chart" not in row
            assert not any(word.startswith("DESCRIPTOR") for word in row)


def test_the_identifier_says_what_kind_of_file_it_is():
    assert cgats.identifier(A_REAL_TI1) == "CTI1"
    assert cgats.identifier(A_REAL_TI2) == "CTI2"
    assert cgats.identifier("CGATS.5\n\nBEGIN_DATA_FORMAT") == "CGATS.5"


def test_a_quoted_sheet_position_keeps_neither_quote():
    """A .ti2 records where each patch sits as "E11". Splitting on whitespace
    alone keeps the quotation marks and turns a position into '"E11"', which
    then matches nothing anybody looks for."""
    table = cgats.read_tables(A_REAL_TI2)[0]
    assert table.text("SAMPLE_LOC") == ["E11", "A1"]


def test_a_quoted_position_does_not_shift_the_columns_after_it():
    table = cgats.read_tables(A_REAL_TI2)[0]
    assert table.numbers("RGB_R", "RGB_G", "RGB_B").tolist() == [
        [100.0, 100.0, 100.0], [0.0, 0.0, 0.0]]


def test_keywords_are_read_from_whichever_table_carries_them():
    tables = cgats.read_tables(A_REAL_TI1)
    assert cgats.keyword(tables, "COLOR_REP") == "iRGB"
    assert cgats.keyword(tables, "ORIGINATOR") == "Argyll targen"
    assert cgats.keyword(tables, "DENSITY_EXTREME_VALUES") == "2"
    assert cgats.keyword(tables, "NOT_THERE", "fallback") == "fallback"


def test_a_keyword_line_announcing_a_name_is_not_itself_a_keyword():
    """CGATS writes KEYWORD "X" to declare X, and then X's own line. Reading
    the first as a keyword gives a keyword called KEYWORD."""
    tables = cgats.read_tables(
        'CTI3\n\nKEYWORD "MINE"\nMINE "yes"\n\n'
        "NUMBER_OF_FIELDS 1\nBEGIN_DATA_FORMAT\nA\nEND_DATA_FORMAT\n"
        "BEGIN_DATA\n1\nEND_DATA\n")
    assert cgats.keyword(tables, "MINE") == "yes"
    assert "KEYWORD" not in tables[0].keywords


def test_a_file_that_is_not_cgats_says_so_in_words():
    with pytest.raises(cgats.CgatsProblem, match="BEGIN_DATA_FORMAT"):
        cgats.read_tables("this is a shopping list\nmilk\nbread\n")


def test_a_header_with_no_rows_says_so():
    with pytest.raises(cgats.CgatsProblem, match="no data rows"):
        cgats.read_tables("CTI1\nBEGIN_DATA_FORMAT\nA B\nEND_DATA_FORMAT\n"
                          "BEGIN_DATA\n")


def test_a_column_that_is_not_there_names_itself():
    table = cgats.read_tables(A_REAL_TI2)[0]
    with pytest.raises(cgats.CgatsProblem, match="LAB_L"):
        table.text("LAB_L")


def test_a_row_with_something_that_is_not_a_number_says_which_row():
    """Quietly dropping it would shorten somebody's chart without telling them."""
    tables = cgats.read_tables(
        "CTI1\nBEGIN_DATA_FORMAT\nSAMPLE_ID RGB_R\nEND_DATA_FORMAT\n"
        "BEGIN_DATA\n1 50.0\n2 oops\nEND_DATA\n")
    with pytest.raises(cgats.CgatsProblem, match="row 2"):
        tables[0].numbers("RGB_R")


def test_reading_from_a_path_and_from_text_agree(tmp_path):
    where = tmp_path / "chart.ti1"
    where.write_text(A_REAL_TI1)
    assert [len(t) for t in cgats.read_tables(where)] == \
           [len(t) for t in cgats.read_tables(A_REAL_TI1)]


def test_a_comment_line_is_not_a_patch():
    tables = cgats.read_tables(
        "CTI1\nBEGIN_DATA_FORMAT\nSAMPLE_ID RGB_R\nEND_DATA_FORMAT\n"
        "BEGIN_DATA\n1 50.0\n# a note somebody left\n2 60.0\nEND_DATA\n")
    assert len(tables[0]) == 2
