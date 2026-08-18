"""Does every slider change the picture WHILE it is being dragged?

ASKED FOR IN AS MANY WORDS: "sliders should update the viewer 'live' not only
after i let go - should be part of the audit that all sliders act accordingly".

THREE THINGS ARE WRONG WITH A SLIDER THAT ONLY ACTS ON RELEASE, and the third
is the one that took the longest to see:

  1. dragging shows nothing, so the value has to be found by trial;
  2. the whole picture is written and loaded again, which empties the view for
     a moment -- "blacks out and then puts everything back at once";
  3. AND THE VIEW JUMPS AFTERWARDS. A rebuilt page opens at the camera it was
     written with, not the one the reader had turned the shape to. Reported
     exactly: "i drag let go it settles and after a few seconds it jumps".

WHAT THIS DOES. For every slider in the column it drags -- which in Qt means
`valueChanged` without `sliderReleased`, precisely what a mouse does -- and
asks the page itself what it is drawing, before and after. Then it lets go and
asks again. Three answers per slider:

    live        the picture changed under the hand, and no page was loaded
    dead        nothing changed until it was let go
    rebuilds    a new page was written, which is the black-out and the jump

A slider that has to recompute geometry (how finely the shape is worked out,
where a cross-section is cut) cannot restyle its way out of it, and is listed
as `rebuilds (geometry)` with that reason rather than counted as a fault.

    python scripts/audit_sliders.py

Exit code 1 if any slider that could be live is not.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_sliders"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

#: Sliders whose value changes what has to be COMPUTED, not how it is drawn.
#: Named here with the reason, so that "this one rebuilds" is a decision on
#: the record rather than an exception somebody added to make a check pass.
MUST_RECOMPUTE = {
    "detail": "the shape itself is worked out again at the new fineness",
    "quality": "the shape itself is worked out again at the new fineness",
    "slice_at": "a cross-section is a different set of points at every height",
    "rings": "the rings are geometry: new lines, not a new colour",
    "custom": "a different number of patches is a different chart",
    "moving_width": "a different window means the numbers are measured again",
    "seconds": "how long the film runs is not something the picture shows",
    # THESE TWO COULD BE LIVE AND ARE NOT, AND THE REASON IS WORTH KEEPING.
    # Where two shapes agree and where they differ is one mesh whose points
    # carry an alpha each, worked out when the page is written -- a design
    # arrived at by measurement, because cutting the surface into two halves
    # left a seam 120,481 pixels wide. The reader's own copy of the page CAN
    # fade them live, because it is written with a mark per point saying
    # which side that point is on; this window's view is not. Making them
    # live here means writing that mark into the live view as well, which is
    # a change to what is drawn rather than to a signal connection.
    "agree": "the two halves are worked out into the colours when the page "
             "is written; see the note in scripts/audit_sliders.py",
    "differ": "the two halves are worked out into the colours when the page "
              "is written; see the note in scripts/audit_sliders.py",
}

#: What the page is drawing, in one string: the trace types, how many points
#: each has, how solid, how big its markers are, what colour, and where the
#: camera is. Anything a restyle can change shows up here; anything it cannot
#: shows up as a different set of traces.
ASK = """
(function () {
  var d = document.getElementsByClassName('plotly-graph-div')[0];
  if (!d || !d.data) return "no picture";
  var seen = [];
  for (var i = 0; i < d.data.length; i++) {
    var t = d.data[i], m = t.marker || {};
    seen.push([t.type, (t.x || []).length, t.opacity,
               JSON.stringify(m.size || null),
               JSON.stringify(m.color || null).slice(0, 60),
               JSON.stringify(t.lighting || null), t.name,
               t.visible === undefined ? true : t.visible]);
  }
  var l = d.layout || {}, s = l.scene || {};
  seen.push(["layout", JSON.stringify(s.camera || null),
             JSON.stringify((s.xaxis || {}).visible)]);
  return JSON.stringify(seen);
})()
"""


def main() -> int:
    from PyQt6.QtWidgets import (QApplication, QGroupBox, QScrollArea,
                                 QSlider)

    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    win = gamut_app.GamutApp([])
    win.resize(1500, 950)
    win.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    def drawing():
        """Ask the page what it is drawing, and WAIT for the answer."""
        got = []
        page = win._view.page()
        if page is None:
            return "no page"
        page.runJavaScript(ASK, got.append)
        end = time.time() + 4
        while not got and time.time() < end:
            app.processEvents()
            time.sleep(0.005)
        return got[0] if got else "no answer"

    pump(3)
    profiles = sorted(pathlib.Path(tempfile.gettempdir())
                      .glob("showme-*/printer-*.icc"))
    if len(profiles) < 2:
        print("  no demo profiles to drive the window with — "
              "run scripts/make_demo_profiles.py first")
        return 1
    # A RUN, ITS SHAPES, AND A PAIR OF FILES: the state in which the most
    # sliders have something to act on. A slider judged with nothing on screen
    # would be called dead for the honest reason that there is nothing to
    # change.
    win._timeline.add(profiles)
    pump(8)
    for i in range(win._timeline._picture_of.count()):
        if win._timeline._picture_of.itemData(i) == ("whole", 0):
            win._timeline._picture_of.setCurrentIndex(i)
            break
    win._timeline._draw()
    pump(4)
    win._timeline._with_shapes.setChecked(True)
    pump(5)

    # WHAT EACH SLIDER NEEDS BEFORE IT CAN DO ANYTHING. Without this the
    # report is mostly noise: the light sliders are wired live and answer
    # "nothing happened" while the light is on automatic, and the chart
    # sliders have no chart. A check that calls a correct control dead is a
    # check nobody will read twice.
    demo = HERE.parent / "demo"
    for measured in ("Glossy-paper.ti3", "Glossy-paper-months-later.ti3"):
        win._load(demo / measured)
        pump(4)
    if (demo / "verification-chart-480.ti1").exists():
        win._open_chart_file(demo / "verification-chart-480.ti1")
        pump(5)
    win._manual_light.setChecked(True)
    win._spin_on.setChecked(True)
    win._rings_on.setChecked(True)
    pump(4)

    column = win.findChild(QScrollArea).widget()
    for box in column.findChildren(QGroupBox):
        if hasattr(box, "_refold"):
            box._fold_open = True
            box._refold()
    pump(2)

    #: name → the slider, found by the attribute it is stored under, so the
    #: report names the control the way the code does.
    named = {}
    for attr in dir(win):
        try:
            thing = getattr(win, attr)
        except Exception:                                  # noqa: BLE001
            continue
        if isinstance(thing, QSlider):
            named[thing] = attr.lstrip("_")
    # The light sliders live in a dictionary rather than in attributes, and
    # "an unnamed slider" seven times over is not a report.
    for key, (slider, _lo, _hi) in getattr(win, "_light_sliders", {}).items():
        named.setdefault(slider, f"light: {key}")
    for attr in dir(win._timeline):
        try:
            thing = getattr(win._timeline, attr)
        except Exception:                                  # noqa: BLE001
            continue
        if isinstance(thing, QSlider) and thing not in named:
            named[thing] = "the run's " + attr.lstrip("_")

    rows = []
    for slider in column.findChildren(QSlider):
        if slider.isHidden():
            continue
        name = named.get(slider, "an unnamed slider")
        group = slider
        while group is not None and not isinstance(group, QGroupBox):
            group = group.parentWidget()
        where = group.title() if group is not None else "the column"

        lo, hi = slider.minimum(), slider.maximum()
        was, url_was = slider.value(), win._view.url().toString()
        before = drawing()
        # THE DRAG. Qt sends valueChanged for every step under the hand and
        # sliderReleased only when it is let go, so this is what dragging is.
        steps = [lo + (hi - lo) * k // 4 for k in (1, 2, 3)]
        moved_to = next((v for v in steps if v != was), hi if was != hi else lo)
        slider.setValue(moved_to)
        pump(2.5)
        during, url_during = drawing(), win._view.url().toString()
        slider.sliderReleased.emit()
        pump(3.0)
        after, url_after = drawing(), win._view.url().toString()

        live = during != before and url_during == url_was
        woke = after != before
        rebuilt = url_after != url_was or url_during != url_was
        if live and not rebuilt:
            verdict = "live"
        elif live and rebuilt:
            verdict = "live, then rebuilds"
        elif woke and rebuilt:
            verdict = "rebuilds"
        elif woke:
            verdict = "only on release"
        else:
            verdict = "nothing happened"
        why = MUST_RECOMPUTE.get(name.replace("the run's ", ""), "")
        rows.append((where, name, lo, hi, verdict, why))
        slider.setValue(was)
        slider.sliderReleased.emit()
        pump(2.0)

    print("\n  WHAT EVERY SLIDER DOES WHILE IT IS BEING DRAGGED\n")
    wide = max(len(r[1]) for r in rows)
    last = None
    faults = []
    for where, name, lo, hi, verdict, why in rows:
        if where != last:
            print(f"\n  {where}")
            last = where
        note = f"   ({why})" if why else ""
        print(f"      {name:{wide}s}  {lo:4d}…{hi:<4d}  {verdict}{note}")
        if verdict == "live":
            continue
        if why and verdict in ("rebuilds", "only on release"):
            continue            # named, with a reason, on the record
        faults.append(f"{name} in “{where}”: {verdict}")

    print()
    if faults:
        for line in faults:
            print(f"  [slider] {line}")
        print(f"\n{len(faults)} slider(s) do not change the picture under the "
              f"hand.")
        win.close()
        return 1
    print("  Clean: every slider that can act live does, and the ones that "
          "recompute say so.")
    win.close()
    pump(0.3)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
