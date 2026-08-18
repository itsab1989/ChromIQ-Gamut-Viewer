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

# ON SCREEN, AND THAT IS NOT A PREFERENCE. Run offscreen, this audit called
# every movement slider dead: with no compositor the browser throttles
# requestAnimationFrame away, so the page reports itself as moving
# (cqSpin.moving() === true) and the camera never advances. Measured, same
# tree, same minute:
#
#     offscreen   camera 1.500,1.500 -> 1.500,1.500   "nothing happened"
#     on screen   camera 0.550,2.049 -> 1.108,1.809   turning
#
# A real measurement of the wrong thing reads as coverage, which is how four
# correct controls were nearly "fixed".
OFFSCREEN = os.environ.get("QT_QPA_PLATFORM") == "offscreen"
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
  if (!d) return "no picture";
  // _fullData, NOT data. The arrays travel packed, and only the library's own
  // copy is unpacked -- asked of `data`, every length comes back undefined,
  // so a shape rebuilt at a different fineness looked identical to one that
  // had not changed at all. That is how "detail" came to be called dead.
  var data = d._fullData || d.data || [];
  var seen = [];
  for (var i = 0; i < data.length; i++) {
    var t = data[i], m = t.marker || {};
    seen.push([t.type, (t.x || []).length, (t.i || []).length, t.opacity,
               // MARKER OPACITY WAS MISSING FROM THIS LIST, and three chart
               // sliders that change nothing else were therefore reported
               // dead -- by a check that had simply not been told to look.
               m.opacity === undefined ? null : m.opacity,
               JSON.stringify(m.size || null),
               JSON.stringify(m.color || null).slice(0, 60),
               JSON.stringify(t.lighting || null), t.name,
               t.visible === undefined ? true : t.visible]);
  }
  var l = d.layout || {}, s = l.scene || {}, cam = null;
  // TWO ANSWERS, NOT ONE. See the note on THE RIGHT PAIR in the module
  // docstring: with "turn it by itself" ticked the camera moves every frame,
  // so a fingerprint that included it reported every slider in the window as
  // live -- including five that plainly rebuild the page.
  // THE CAMERA THAT IS ACTUALLY IN USE. layout.scene.camera is only brought
  // up to date when the library relayouts, so a picture asked while it is
  // turning answers with where it USED to be -- and every movement slider
  // read as dead.
  try {
    var sc = d._fullLayout && d._fullLayout.scene && d._fullLayout.scene._scene;
    if (sc && sc.getCamera) cam = sc.getCamera();
  } catch (e) {}
  if (!cam) cam = s.camera || null;
  seen.push(["layout", JSON.stringify((s.xaxis || {}).visible)]);
  return JSON.stringify({picture: seen, camera: JSON.stringify(cam)});
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
    # sliders have no chart.
    #
    # AND ONE PICTURE CANNOT EXERCISE THEM ALL. While a run owns the view,
    # the chart is not in the picture at all and neither are the two shapes
    # the agreement sliders fade -- so the first version of this called five
    # correct controls dead. Every slider is therefore judged in BOTH scenes
    # and reported at its best: a slider is only at fault if it does nothing
    # in the one place it belongs.
    demo = HERE.parent / "demo"
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
    def by_widget_name(widget):
        return named.get(widget, "an unnamed slider")

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

    skipped = set()

    def sweep(scene_name):
        found = []
        for slider in column.findChildren(QSlider):
            # NOT SHOWN IS NOT THE SAME AS HIDDEN. A slider inside a section
            # the window has closed answers isHidden() == False while being
            # nowhere on screen -- and one judged there is judged with its
            # prerequisite missing. "Detail" governs the shape you COMPARE
            # against and is not shown until there is one; asked anyway, it
            # answered "nothing happened", which is true and says nothing.
            if not slider.isVisibleTo(win):
                skipped.add((slider, scene_name))
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

            # A MOVEMENT SLIDER IS JUDGED ON THE CAMERA and everything else
            # on the picture, which is the only way to ask each of them the
            # question it is about.
            moves_the_view = name.startswith(("turn_", "tilt_"))
            part = "camera" if moves_the_view else "picture"
            before, during, after = (json.loads(x)[part] if x.startswith("{")
                                     else x for x in (before, during, after))
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
            found.append((where, name, lo, hi, verdict, why))
            slider.setValue(was)
            slider.sliderReleased.emit()
            pump(2.0)
        return found

    # SCENE ONE: the run owns the picture -- its cloud, its two shells.
    rows = sweep("a run of profiles")

    # SCENE TWO: two measurements of one paper, months apart. This is where
    # "Has anything changed?" has something to say, and its threshold slider
    # has a range wider than a single step.
    win._timeline._clear_btn.click()          # "Remove them all"
    pump(6)
    # TWO PROFILES, NOT TWO MEASUREMENTS. "Has anything changed?" compares
    # what two PROFILES do with the same colours -- see _drift_for_figure,
    # which asks for a profile pair -- so with two .ti3 files open its
    # threshold slider has no pair, no fitted range (0..1) and nothing to
    # hide. Judged there, a working control reads as dead.
    for profile in profiles[:2]:
        win._load(profile)
        pump(6)
    if hasattr(win, "_drift_draw"):
        win._drift_draw.setChecked(True)
        pump(7)
    rows += sweep("two profiles of one printer")

    # SCENE THREE: a profile and a chart to be printed. A CHART IS PLACED BY
    # A PROFILE -- with only measurements open it is not in the picture at
    # all, which is why its five sliders read as dead in an earlier version
    # of this and were nearly "fixed".
    win._on_clear()
    pump(5)
    win._load(profiles[0])
    pump(6)
    if (demo / "verification-chart-480.ti1").exists():
        win._open_chart_file(demo / "verification-chart-480.ti1")
        pump(7)
    # AND SOMETHING TO COMPARE AGAINST, because "Detail" is about the shape
    # you compare WITH -- "how finely the shape you compare against is built"
    # -- and is not even shown until there is one.
    for i in range(win._compare.count()):
        if win._compare.itemText(i).startswith("sRGB"):
            win._compare.setCurrentIndex(i)
            win._compare.activated.emit(i)
            win._on_compare_changed()
            break
    pump(8)
    # A SKIN OVER THE PATCHES, or "how solid the skin is" has nothing to be
    # solid: the chart opens with no skin, so that slider was being asked
    # about a thing that was not in the picture.
    at = win._chart_skin.findData("mesh")
    if at < 0:
        at = 1 if win._chart_skin.count() > 1 else 0
    win._chart_skin.setCurrentIndex(at)
    win._chart_skin.activated.emit(at)
    pump(6)
    rows += sweep("a profile and a chart")

    # SCENE FOUR: the cross-section, which is the only place the height
    # slider means anything -- and a flat cut is a different picture, not a
    # different setting, so it gets a scene of its own.
    win._slice_on.setChecked(True)
    pump(6)
    rows += sweep("a cross-section")
    win._slice_on.setChecked(False)
    pump(4)

    # THE BEST ANSWER EACH SLIDER GAVE, in the scene where it belongs.
    best, order = {}, []
    rank = {"live": 0, "live, then rebuilds": 1, "rebuilds": 2,
            "only on release": 3, "nothing happened": 4}
    for row in rows:
        key = (row[0], row[1])
        if key not in best or rank[row[4]] < rank[best[key][4]]:
            best[key] = row
        if key not in order:
            order.append(key)
    rows = [best[key] for key in order]

    # A SLIDER NO SCENE EVER SHOWED is not "fine", it is unexamined, and
    # saying so is the difference between a report and a clean bill.
    judged = {name for _w, name, *_rest in rows}
    never = sorted({by_widget_name(s) for s, _scene in skipped
                    if by_widget_name(s) not in judged})

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
        if OFFSCREEN and name.startswith(("turn_", "tilt_")):
            print("           ^ not answerable without a screen: the "
                  "browser throttles its animation loop away")
            continue
        faults.append(f"{name} in “{where}”: {verdict}")

    if never:
        print("\n  NOT SHOWN IN ANY SCENE, so not judged: "
              + ", ".join(never))
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
