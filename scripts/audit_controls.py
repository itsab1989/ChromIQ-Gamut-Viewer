"""Which controls redraw the whole picture, and which change it in place?

ASKED FOR IN AS MANY WORDS: "audit for which options this is true so i don't
have to check every single one myself". The "this" is a control that empties
the view and loads a new page for a change the picture could have made in
place -- the whole thing blinks, and while a slider is being DRAGGED it blinks
on every step.

WHY IT MATTERS MORE THAN IT SOUNDS. A rebuild is right when what is DRAWN
changes: adding two shapes to a scene is not a restyle. It is wrong when only
an appearance changes -- how solid a surface is, which dots are hidden -- and
those are exactly the controls somebody drags rather than clicks, so the fault
lands where it is most visible.

WHAT THIS DOES. It drives the real window with a run and a pair of files open,
touches every control in the column in turn, and watches the address the view
is showing. A new address means the page was written and loaded again; the
same address means the picture was changed where it stood.

It also reports, for every slider, the range it offers -- because "i can't
turn how solid it looks completely down to 0" is the same kind of question
and the same kind of answer: a number, not an opinion.

    python scripts/audit_controls.py

This one PRINTS rather than fails: which controls deserve a live path is a
judgement, and a table is what that judgement needs.

WHERE THAT JUDGEMENT HAS GOT TO, measured 2026-08-18: **80 controls touched,
34 rebuild** -- down from 41. The seven that changed are the ones a person
drags: how solid, how deep the shading, the chart's four dot settings and its
skin, plus the box and its grid, which the reader's own copy of the page had
always been able to switch without a rebuild while this window wrote a new
page for it.

THE 34 THAT REMAIN ARE NOT A BACKLOG. Every one of them changes WHAT is
drawn rather than how it looks: splitting into colour families, adding the two
shapes, the rings, the greys, the neutral line, every measured patch, two
rooms, a cross-section, a different white point, a different space, a
different pair to compare. Five sliders are in there for the same reason and
are named in scripts/audit_sliders.py with the reason each: the cut height,
the rings, the fineness, and the two agreement sliders.

ONE IS AN OPEN QUESTION rather than settled: Light/Dark/Amber. A saved page
can change its own palette without a reload, because the palettes travel in
the file -- this window's live view is written without them, so switching
means writing the page again. Carrying them into the live view would cure it,
at the cost of putting three palettes into every page this window writes.
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

# THE SETTINGS GO SOMEWHERE THROWAWAY, and this must happen before the
# window is built. A driver that uses the real store both destroys what
# the person using this application has chosen and leaves its own last
# state behind as their new preference -- which is how "the walls behind
# the shape are missing" was reported as a bug in the viewer. See
# python/prefs.py.
import prefs  # noqa: E402

prefs.use_a_scratch_store()
sys.argv = ["audit_controls"]

#: Controls that must NOT be touched by a sweep like this: they open a window
#: that waits for a person, or they throw away what is loaded.
LEAVE_ALONE = {
    "Open something to look at…", "Open a chart to be printed…",
    "Add profiles…", "Remove them all", "Remove the selected one",
    "Close them all", "Save this view as a picture…",
    "Save this view as a web page…", "Save the numbers as a table…",
    "Save the run's numbers as a table…", "What do these words mean?",
    "Where ArgyllCMS is…", "Where ffmpeg is…", "Check for a newer version…",
    "Start again with standard settings", "♥  Support ChromIQ",
    "ChromIQ website", "×", "+", "−", "…", "Choose a colour…",
}


def main() -> int:
    from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox,
                                 QGroupBox, QLabel, QPushButton,
                                 QRadioButton, QScrollArea, QSlider)
    from PyQt6.QtCore import QSettings

    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    win = gamut_app.GamutApp([])
    win.resize(1500, 950)
    win.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(3)
    import demo_profiles
    profiles = demo_profiles.the_run_of_profiles()
    if len(profiles) < 2:
        print("  no demo profiles to drive the window with — "
              "run scripts/make_demo_profiles.py first")
        return 1
    # A RUN AND A PAIR AT ONCE, so every control in the column has something
    # to act on: the run owns the picture and the pair's own readouts exist.
    win._timeline.add(profiles)
    pump(7)
    for i in range(win._timeline._picture_of.count()):
        if win._timeline._picture_of.itemData(i) == ("whole", 0):
            win._timeline._picture_of.setCurrentIndex(i)
            break
    win._timeline._draw()
    pump(3)
    win._timeline._with_shapes.setChecked(True)
    pump(4)

    column = win.findChild(QScrollArea).widget()
    for box in column.findChildren(QGroupBox):
        if hasattr(box, "_refold"):
            box._fold_open = True
            box._refold()
    pump(2)

    def showing() -> str:
        return win._view.url().toString()

    #: AND WHERE THE READER IS LOOKING FROM. Asked for from the window: "i
    #: would like them to simply appear / disappear without the viewer
    #: flashing / reloading and the camera resetting". Those are two
    #: questions, and only the first was ever measured here. A rebuild that
    #: carries the angle over is a blink; a rebuild that loses it puts the
    #: reader back at the beginning, which is the one that really costs.
    def angle():
        got = []
        page = win._view.page()
        if page is None:
            return None
        page.runJavaScript(
            "(function(){var d=document.getElementsByClassName("
            "'plotly-graph-div')[0];var s=d&&d._fullLayout&&d._fullLayout.scene;"
            "var c=s&&((s._scene&&s._scene.getCamera())||s.camera);"
            "return c&&c.eye?[Math.round(c.eye.x*100)/100,"
            "Math.round(c.eye.y*100)/100,Math.round(c.eye.z*100)/100].join():"
            "'';})()", got.append)
        end = time.time() + 6
        while not got and time.time() < end:
            app.processEvents()
            time.sleep(0.005)
        return got[0] if got else None

    # THE READER'S OWN ANGLE, turned away from the default so that losing it
    # shows as a difference rather than as a coincidence.
    win._view.page().runJavaScript(
        "(function(){var d=document.getElementsByClassName("
        "'plotly-graph-div')[0];return Plotly.relayout(d,"
        "{'scene.camera.eye':{x:2.1,y:0.4,z:0.8}})&&'ok';})()")
    pump(3)

    # WHAT THE WINDOW KEEPS EACH CONTROL UNDER, so a slider can be named.
    #
    # A QSlider has no text, so every one of them came out as the placeholder
    # "a slider" in one list and as "NoScrollSlider" in the other. The report
    # then said "82 controls touched, 33 rebuild the whole picture" without
    # saying WHICH — and this file exists because Basti asked for exactly that:
    # "audit for which options this is true so i don't have to check every
    # single one myself". Twenty-five anonymous rows are not an answer to that.
    attribute = {id(v): k for k, v in vars(win).items()}

    def _named(control):
        """The words beside a slider, or failing that what the code calls it."""
        row = control.parentWidget()
        spot = row.layout() if row is not None else None
        if spot is not None:
            for i in range(spot.count()):
                item = spot.itemAt(i)
                widget = item.widget() if item is not None else None
                if isinstance(widget, QLabel) and widget.text().strip():
                    return widget.text().strip()
        return attribute.get(id(control), "") or "a slider"

    rows, sliders = [], []
    for kind in (QCheckBox, QRadioButton, QComboBox, QSlider):
        for control in column.findChildren(kind):
            if isinstance(control, gamut_app.Hint) or control.isHidden():
                continue
            name = (control.text() if hasattr(control, "text") else "") or ""
            if isinstance(control, QSlider) and not name:
                name = _named(control)
            if isinstance(control, QComboBox):
                name = "▾ " + (control.currentText()[:26] or "a chooser")
            if name.strip() in LEAVE_ALONE:
                continue
            group = control
            while group is not None and not isinstance(group, QGroupBox):
                group = group.parentWidget()
            where = group.title() if group is not None else "the column"

            was = showing()
            turned = angle()
            before = None
            try:
                if isinstance(control, QSlider):
                    before = control.value()
                    lo, hi = control.minimum(), control.maximum()
                    sliders.append((where, name, lo, hi, control.value()))
                    step = max(1, (hi - lo) // 4)
                    control.setValue(min(hi, before + step))
                    control.sliderReleased.emit()
                elif isinstance(control, QComboBox):
                    before = control.currentIndex()
                    if control.count() < 2:
                        continue
                    control.setCurrentIndex((before + 1) % control.count())
                    control.activated.emit(control.currentIndex())
                else:
                    before = control.isChecked()
                    control.setChecked(not before)
            except Exception as exc:                      # noqa: BLE001
                rows.append((where, name, f"could not be touched: {exc}"))
                continue
            pump(2.5)
            now = showing()
            still = angle()
            kept = (turned is None or still is None or still == turned)
            rows.append((where, name or type(control).__name__,
                         ("REBUILDS" if now != was else "in place")
                         + ("" if kept else "  AND LOSES THE ANGLE")))
            # PUT IT BACK, so the next control is judged from the same state.
            try:
                if isinstance(control, QSlider):
                    control.setValue(before)
                    control.sliderReleased.emit()
                elif isinstance(control, QComboBox):
                    control.setCurrentIndex(before)
                    control.activated.emit(before)
                else:
                    control.setChecked(before)
            except Exception:                             # noqa: BLE001
                pass
            pump(1.5)

    print("\n  WHAT EACH CONTROL DOES TO THE PICTURE\n")
    width = max((len(r[1]) for r in rows), default=10)
    last = None
    for where, name, what in rows:
        if where != last:
            print(f"\n  {where}")
            last = where
        print(f"      {name[:width]:{width}s}   {what}")

    print("\n  WHAT EACH SLIDER OFFERS\n")
    for where, name, lo, hi, at in sliders:
        print(f"      {where[:26]:28s} {name[:22]:24s} {lo:4d} … {hi:4d}"
              f"   (now {at})")

    rebuilds = [r for r in rows if r[2] == "REBUILDS"]
    print(f"\n  {len(rows)} controls touched, {len(rebuilds)} rebuild the "
          f"whole picture.")
    win.close()
    pump(0.5)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
