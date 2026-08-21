"""Is any control on screen with nothing in it?

    python scripts/audit_nothing_around_nothing.py

Exit code 1 if a visible control is empty.

WHY THIS EXISTS. Reported from the window: "one device over time shows an
empty frame over the add button" -- the run's file list, holding its least
height with no rows in it, drawn as a framed 52 px of nothing on top of the
button that fills it. Driving that fix found the SAME FAULT TWICE MORE in the
same section and neither had been reported: an empty "Show me" dropdown, and
a "coloured by" offering five ways to paint a picture that did not exist.

Three in one section says this is a class and not an incident, so every state
the window can be in is walked and every control asked whether it has
anything in it. A control drawn around nothing invites a click and answers
with silence, which is worse than one that is not there.

WHAT COUNTS AS EMPTY: a chooser with no entries, a list with no rows, a
group box with nothing visible inside it. A LABEL is not judged -- the
window has a `hide_when_empty` label of its own that is meant to be blank
sometimes -- and neither is a control that is deliberately disabled, which
says its own piece by being greyed.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_nothing_around_nothing"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

from PyQt6.QtWidgets import (QApplication, QComboBox,           # noqa: E402
                             QGroupBox, QListWidget, QScrollArea)

import gamut_app                                                # noqa: E402


def empties(win):
    """Every visible control in the column that has nothing in it."""
    area = win.findChild(QScrollArea)
    inner = area.widget() if area else win
    found = []
    for box in inner.findChildren(QComboBox):
        if box.isVisibleTo(inner) and box.count() == 0:
            found.append(("a chooser with no entries", name_of(box, inner)))
    for lst in inner.findChildren(QListWidget):
        if lst.isVisibleTo(inner) and lst.count() == 0:
            found.append(("a list with no rows", name_of(lst, inner)))
    for group in inner.findChildren(QGroupBox):
        if not group.isVisibleTo(inner):
            continue
        # A GROUP THAT IS FOLDED IS NOT EMPTY, it is folded, and the reader
        # did that themselves.
        if getattr(group, "_fold_open", True) is False:
            continue
        alive = [w for w in group.findChildren(object)
                 if hasattr(w, "isVisibleTo") and w.isVisibleTo(group)
                 and w is not group]
        if not alive:
            found.append(("a group with nothing in it", group.title()))
    return found


def name_of(widget, inner):
    """Whatever a reader would call it: its own words, or its neighbour's."""
    for attr in ("text", "title", "toolTip"):
        got = getattr(widget, attr, None)
        if callable(got):
            said = (got() or "").strip()
            if said:
                return said.splitlines()[0][:44]
    return widget.objectName() or widget.__class__.__name__


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
    win = gamut_app.GamutApp([])
    win.resize(1500, 950)
    win.show()

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(3)
    import demo_profiles
    profiles = demo_profiles.the_run_of_profiles()
    demo = HERE.parent / "demo"
    chart = demo / "verification-chart-480.ti1"

    #: EVERY STATE THE WINDOW CAN BE IN, because a control that is empty in
    #: one of them is full in another -- that is the whole shape of this
    #: fault. Crossed rather than driven one at a time.
    states = [("nothing open at all", lambda: None)]
    if profiles:
        states += [
            ("one profile", lambda: win._load(profiles[0])),
            ("two profiles", lambda: win._load(profiles[-1])),
            ("a run of four", lambda: win._timeline.add(list(profiles))),
        ]
    if chart.exists():
        states.append(("and a chart as well",
                       lambda: win._open_chart_file(chart)))

    problems = []
    for label, act in states:
        act()
        pump(9 if "run" in label else 6)
        found = empties(win)
        print(f"\n  {label}")
        if not found:
            print("      nothing drawn around nothing")
        for kind, who in found:
            print(f"      {kind}: {who}")
            problems.append(f"[{label}] {kind} — {who}")

    print()
    for line in problems:
        print("  " + line)
    if problems:
        print(f"\n{len(problems)} control(s) drawn around nothing.")
    else:
        print("  Clean: no control is on screen with nothing in it.")
    win.close()
    pump(0.4)
    sys.stdout.flush()
    return 1 if problems else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
