"""6,912 combinations is a claim about whatever the table happens to hold.

WHY THIS EXISTS. `scripts/drive_all_combinations.py` crosses every chart
option against every other and asks the invariants of each — "no look setting
may move a dot", "no count may depend on how anything is drawn". It is the
widest check in the project and it prints its own width: `6,912
combinations`, `65,836 checks, 0 broken`.

But the width is a claim about the tuples at the top of that script, and
those are hand-written. Add a fourth skin colour or a fifth drawing space to
the window and the run goes on saying 6,912 while quietly no longer covering
the thing that was added — and a combination nobody crosses is exactly where
this project keeps finding faults. The same shape has now cost three separate
findings in three days: "every slider follows its handle" was seven of
nineteen; "the strip is inside the window" measured only the sides; the page
checks between them size 8 of 23 pages. A CLAIM IS ONLY AS WIDE AS THE
POPULATION SOMEBODY MEASURED.

WHY IT READS SOURCE. Constructing `GamutApp` inside pytest brings up a
QWebEngineView and aborts the run — see the note at the top of
`test_chart_panel.py`. Both the window's `addItem` calls and the script's
tuples are literals, so they can be read without running either.
"""
import ast
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_WINDOW = (_ROOT / "python" / "gamut_app.py").read_text(encoding="utf-8")
_SCRIPT = (_ROOT / "scripts" / "drive_all_combinations.py").read_text(
    encoding="utf-8")

#: The window's chooser, and the tuple in the script that must cross it.
PAIRS = [("_chart_skin", "SKINS"),
         ("_chart_skin_colour", "SKIN_COLOURS"),
         ("_space", "SPACES")]


def _offered(widget: str) -> list:
    """Every value the window puts in one chooser, in order."""
    calls = re.findall(rf"self\.{widget}\.addItem\((.*?)\)", _WINDOW, re.S)
    values = []
    for args in calls:
        found = re.findall(r'"([^"]*)"', args)
        if len(found) >= 2:          # the label, then the value behind it
            values.append(found[-1])
    # A SCRAPE THAT FOUND NOTHING LOOKS EXACTLY LIKE A CHOOSER WITH NOTHING
    # IN IT. Every one of these has at least three items, so anything less
    # means the calls have been rewritten and this rule can no longer see
    # them — which must fail loudly rather than pass quietly.
    assert len(values) >= 3, (
        f"only {len(values)} item(s) found for {widget} — this rule can no "
        f"longer read the window's choosers and is not checking anything")
    return values


def _crossed(name: str) -> tuple:
    tree = ast.parse(_SCRIPT)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == name for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError(f"{name} is gone from drive_all_combinations.py")


@pytest.mark.parametrize("widget,table", PAIRS)
def test_every_choice_the_window_offers_is_crossed(widget, table):
    offered, crossed = set(_offered(widget)), set(_crossed(table))
    missing = sorted(offered - crossed)
    assert not missing, (
        f"{widget} offers {sorted(offered)} and drive_all_combinations.py "
        f"crosses only {sorted(crossed)} — {missing} is in the window and in "
        f"no combination, so the run's '6,912 combinations' is a claim about "
        f"less than it says. Add it to {table}.")


@pytest.mark.parametrize("widget,table", PAIRS)
def test_the_table_invents_nothing(widget, table):
    # THE OTHER DIRECTION, and it is not symmetrical: a value crossed that
    # the window cannot produce wastes a sixth of the run proving something
    # about a setting nobody can reach, and reads as coverage.
    extra = sorted(set(_crossed(table)) - set(_offered(widget)))
    assert not extra, (
        f"drive_all_combinations.py crosses {extra} for {table}, which "
        f"{widget} does not offer — either the window lost a choice or the "
        f"table is describing one that never existed")
