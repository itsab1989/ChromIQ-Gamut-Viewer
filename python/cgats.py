"""Read a CGATS file properly — including the ones that hold several tables.

WHY THIS EXISTS, AND WHAT IT FIXED
----------------------------------
Every colour file in this family — ``.ti1``, ``.ti2``, ``.ti3``, an i1Profiler
``.txt`` — is CGATS: a few keywords, a list of column names between
``BEGIN_DATA_FORMAT`` and ``END_DATA_FORMAT``, and rows between ``BEGIN_DATA``
and ``END_DATA``. It looks like a format you can read with two ``split`` calls,
and for a ``.ti3`` you can.

**A ``.ti1`` is three tables in one file**, and that is not a corner case: it is
what ``targen`` writes every single time. The first table is the chart; the
second lists the eight density extremes; the third lists the nine device
combinations. Reading from the first ``BEGIN_DATA`` to the *last* ``END_DATA``
swallows all three, headers and all, and the first thing the number parser then
meets is the word ``chart`` out of the second table's ``DESCRIPTOR`` line.
Measured on a real ChromIQ chart before this module existed:

    ValueError: could not convert string to float: 'chart'

So a file that is perfectly well-formed produced an error naming a word from a
comment. That is the sort of message that sends somebody looking for a fault in
their own file, and it is why the reader is here rather than inlined.

WHAT IT DOES NOT DO
-------------------
It does not interpret anything. It hands back the identifier, the keywords, the
column names and the rows, as text. Deciding that ``RGB_R`` means a device
value and that a number over 100 means the file counts to 255 is a judgement
about *charts*, and it lives in ``chart.py`` where it can be argued with.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

#: One data field: a bare run of non-space, or anything inside double quotes.
#: A ``.ti2`` carries sheet positions as ``"E11"``, so splitting on whitespace
#: alone would keep the quotation marks and turn a position into ``'"E11"'``.
_FIELD = re.compile(r'"[^"]*"|\S+')

#: ``NAME value`` or ``NAME "value"`` — the keyword lines above each table.
_KEYWORD = re.compile(r'^([A-Za-z_][A-Za-z0-9_.]*)\s+(.*)$')


class CgatsProblem(ValueError):
    """This file is not CGATS, or is CGATS that cannot be made sense of."""


def _unquote(word: str) -> str:
    return word[1:-1] if len(word) >= 2 and word[0] == word[-1] == '"' else word


@dataclass(frozen=True)
class Table:
    """One table out of a CGATS file: its keywords, columns and rows."""

    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    keywords: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.rows)

    def has(self, *names: str) -> bool:
        """True when every one of *names* is a column of this table."""
        return set(names) <= set(self.columns)

    def text(self, name: str) -> list:
        """One column, as it is written in the file."""
        try:
            at = self.columns.index(name)
        except ValueError:
            raise CgatsProblem(f"there is no column called {name}") from None
        return [r[at] for r in self.rows]

    def numbers(self, *names: str) -> np.ndarray:
        """Several columns side by side, as an (N, len(names)) array.

        A row whose value is not a number is not silently dropped: a chart with
        one unreadable patch is a chart somebody should look at, not one to
        quietly shorten.
        """
        out = np.empty((len(self.rows), len(names)), dtype=float)
        for column, name in enumerate(names):
            values = self.text(name)
            for row, word in enumerate(values):
                try:
                    out[row, column] = float(word)
                except ValueError:
                    raise CgatsProblem(
                        f"row {row + 1} of this file has {word!r} in the "
                        f"{name} column, which is not a number") from None
        return out


def identifier(text: str) -> str:
    """What the file calls itself on its first line.

    ``CTI1`` for a chart to be printed, ``CTI2`` once it has been laid out on a
    sheet, ``CTI3`` once it has been measured — and ``CGATS.5`` or ``CGATS.17``
    for the wider family that i1Profiler and vendor charts use. This is the one
    piece of the file that says what kind of thing it is, and it is far more
    trustworthy than the extension somebody happened to save it under.
    """
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line.split()[0] if line.split() else ""
    return ""


def read_tables(source) -> list:
    """Every table in a CGATS file, in the order they appear.

    *source* may be a path or the text itself, so a caller that already has the
    bytes does not have to write them to disk to read them back.
    """
    text = (source if isinstance(source, str) and "\n" in source
            else Path(source).read_text(errors="replace"))
    if "BEGIN_DATA_FORMAT" not in text or "BEGIN_DATA" not in text:
        raise CgatsProblem(
            "this file has no BEGIN_DATA_FORMAT section, so it is not a CGATS "
            "file (a .ti1, .ti2, .ti3 or a chart exported as text)")

    tables: list = []
    pending: dict = {}          # keywords seen since the last table ended
    columns: list = []
    rows: list = []
    where = "outside"           # outside | format | data

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("BEGIN_DATA_FORMAT"):
            where, columns = "format", []
            continue
        if line.startswith("END_DATA_FORMAT"):
            where = "outside"
            continue
        # ORDER MATTERS: "BEGIN_DATA_FORMAT" also starts with "BEGIN_DATA",
        # so this test has to come after the one above, not before it.
        if line.startswith("BEGIN_DATA"):
            where, rows = "data", []
            continue
        if line.startswith("END_DATA"):
            tables.append(Table(columns=tuple(columns), rows=tuple(rows),
                                keywords=dict(pending)))
            where, pending, columns, rows = "outside", {}, [], []
            continue

        if where == "format":
            columns.extend(_unquote(w) for w in _FIELD.findall(line))
        elif where == "data":
            values = [_unquote(w) for w in _FIELD.findall(line)]
            if len(values) >= len(columns) and columns:
                rows.append(tuple(values[:len(columns)]))
        else:
            # A keyword line. KEYWORD "X" only announces that X is a
            # user-defined name; the interesting line is X's own.
            match = _KEYWORD.match(line)
            if match and match.group(1) != "KEYWORD":
                pending[match.group(1)] = _unquote(match.group(2).strip())

    if not tables:
        raise CgatsProblem("this file has a header but no data rows")
    return tables


def keyword(tables, name: str, default: str = "") -> str:
    """A keyword from whichever table carries it.

    Keywords sit above the table they belong to, but the ones worth reading —
    what colour space the file is in, what created it, whether its predicted
    values came from a real profile — are properties of the file as a whole and
    are written above the first table only.
    """
    for table in tables:
        if name in table.keywords:
            return table.keywords[name]
    return default
