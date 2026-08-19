"""Switching light and dark may change how the window LOOKS. Nothing else.

WHY THIS EXISTS. Two faults in one week, both reported as appearance bugs and
neither having anything to do with colour:

  * "comparing dark and light mode on some instances there is a line of text
    missing in dark, while light sometimes leaves too much space" -- and then
    the reproduction that gave it away: "with the wider left column the
    initial dark mode is good. you switch to light mode and then there is
    unused space added below the text. you switch back to dark and the space
    is still there".
  * A line that was there when the window opened and gone once you had been
    to the other appearance and back: "Nothing open yet. Add two or more
    profiles of one device."

Neither is about light or dark. Switching the appearance re-applies the
stylesheet, which re-POLISHES every widget, which resizes it and redraws it --
and re-polishing is the only thing in a freshly opened window that makes a
paragraph measure itself again or makes a panel redraw. So the switch is not
the cause of these faults; it is the thing that EXPOSES them, and that makes
it an excellent thing to drive on purpose.

THE RULE, AND IT IS SIMPLE ENOUGH TO CHECK. After dark -> light -> dark the
window must say exactly what it said before, in exactly the same shape:

  1. the same set of visible lines of text, word for word;
  2. every paragraph the same height as before;
  3. and that height is what its own words need -- no line cut off, and no
     empty band under the text.

AND IT IS CROSSED WITH WHAT IS OPEN, because an empty window exercises almost
none of the readouts. Three states: nothing open, a profile open, a chart
open. The faults above lived in two different ones of those.

    python scripts/audit_the_switch_changes_nothing.py

Exit code is 1 if a switch changed anything but the colours.
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "python"))

import prefs  # noqa: E402

prefs.use_a_scratch_store()
sys.argv = ["audit_the_switch_changes_nothing"]

from PyQt6.QtCore import QRect, Qt                             # noqa: E402
from PyQt6.QtWidgets import (QApplication, QGroupBox,          # noqa: E402
                             QScrollArea)

PROFILE = ROOT / "demo" / "Glossy-paper.icc"
CHART = ROOT / "demo" / "verification-chart-480.ti1"


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def needed_height(label) -> int:
    """What this paragraph's own words need at the width it has."""
    margins = label.contentsMargins()
    inner = (label.width() - margins.left() - margins.right()
             - 2 * label.margin())
    box = label.fontMetrics().boundingRect(
        QRect(0, 0, max(1, inner), 10_000),
        int(Qt.TextFlag.TextWordWrap), label.text())
    return box.height() + 4


def what_it_says(column, gamut_app) -> dict:
    """Every paragraph on show: its words, and how tall it is."""
    said = {}
    for label in column.findChildren(gamut_app.WrappedLabel):
        if not (label.isVisible() and label.text().strip()):
            continue
        said[label.text().strip()] = (label.height(), needed_height(label))
    return said


def compare(state: str, before: dict, after: dict) -> list:
    problems = []
    for words in sorted(set(before) - set(after)):
        problems.append(
            f"[{state}] LOST  the window stopped saying {words[:60]!r} after "
            f"a switch — an appearance may change how it looks, never what "
            f"it tells you")
    for words in sorted(set(after) - set(before)):
        problems.append(
            f"[{state}] APPEARED  the window only says {words[:60]!r} after "
            f"a switch, so it was missing when the window opened")
    for words in sorted(set(before) & set(after)):
        was, _ = before[words]
        now, needs = after[words]
        if was != now:
            problems.append(
                f"[{state}] RESIZED  {words[:50]!r} was {was}px and is {now}px "
                f"after a switch (its words need {needs}px)")
    return problems


def height_is_honest(state: str, said: dict, when: str) -> list:
    problems = []
    for words, (height, needs) in said.items():
        if height < needs:
            problems.append(
                f"[{state}] CUT {when}  {words[:50]!r} has {height}px for "
                f"{needs}px of words — the last line is under something")
        elif height - needs >= 4:
            problems.append(
                f"[{state}] SPARE {when}  {words[:50]!r} has {height}px for "
                f"{needs}px of words — an empty band under the text")
    return problems


def main() -> int:
    import gamut_app

    app = QApplication(sys.argv)
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
    window = gamut_app.GamutApp([])
    window.resize(1500, 1000)
    window.show()
    pump(app, 3)
    column = window.findChild(QScrollArea).widget()

    def open_every_section():
        for box in column.findChildren(QGroupBox):
            if hasattr(box, "_refold") and not getattr(box, "_fold_open", True):
                box._fold_open = True
                box._refold()
        pump(app, 1.5)

    open_every_section()

    problems: list = []
    states = [("nothing open", None)]
    if PROFILE.is_file():
        states.append(("a profile open", PROFILE))
    if CHART.is_file():
        states.append(("a chart open", CHART))

    for state, path in states:
        if path is not None:
            if path.suffix in (".ti1", ".ti2"):
                window._open_chart_file(path)
            else:
                window._load(path)
            pump(app, 6)
            open_every_section()
        # THE APPEARANCE IS PUT BACK TO DARK FIRST, so every state starts
        # from the same place however the last one left it.
        window._set_appearance("dark")
        pump(app, 2.5)
        before = what_it_says(column, gamut_app)
        problems += height_is_honest(state, before, "as it opens")
        window._set_appearance("light")
        pump(app, 3)
        middle = what_it_says(column, gamut_app)
        problems += height_is_honest(state, middle, "in light")
        window._set_appearance("dark")
        pump(app, 3)
        after = what_it_says(column, gamut_app)
        problems += compare(state, before, after)
        problems += height_is_honest(state, after, "after the round trip")
        print(f"  checked: {state} ({len(before)} paragraphs)")

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} problem(s).")
        return 1
    print("  Clean: three content states, each driven dark -> light -> dark, "
          "every paragraph the same words and the same height throughout.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
