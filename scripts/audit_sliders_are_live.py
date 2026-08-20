"""Every slider changes the picture WHILE it is dragged, not on release.

    ../gv-venv/bin/python scripts/audit_sliders_are_live.py
    ../gv-venv/bin/python scripts/audit_sliders_are_live.py --prove

WHY THIS EXISTS. Reported from the window, twice in two minutes: "show rings
inside slider only updates the viewer when i let go from dragging it - should
be live", then "same what i just said is true for the details slider", and
then the rule that settles it: "all sliders should work this way".

Two reports of one fault means it is a class, not two bugs. A slider that only
acts on release is one connected to `sliderReleased` while `valueChanged` does
nothing but retitle a label, and nothing in the window says which is which --
so the way to keep this from coming back is to ask every slider the same
question rather than to fix the two that were noticed.

WHAT MUST BE TRUE, with the failure direction:

  the picture changes DURING the drag   a slider whose picture only catches up
                                        on release feels broken, and the
                                        reader cannot see what they are
                                        choosing while they choose it;
  it changes to the RIGHT thing         a live push that reaches the wrong
                                        trace is worse than none: the rebuild
                                        on release would put it right and hide
                                        the fault, which is how one fix
                                        becomes the next bug (see
                                        _which_meshes_js);
  releasing does not undo it            if letting go rebuilds the page, the
                                        shape jumps back and the camera moves,
                                        which is the fault the in-place
                                        restyle exists to avoid.

HOW A DRAG IS SIMULATED, and why not with setValue alone: a slider driven by
`setValue` emits `valueChanged` and never `sliderPressed`/`sliderReleased`, so
a check written that way cannot tell a live slider from a dead one -- it would
pass on both. `setValue` has already fooled this project once, which is the
memory "setValue fires only half a slider". So the handle is pressed
(`sliderPressed`), moved with `setSliderDown(True)` in force, measured, and
only then released.

WHAT IS MEASURED is the picture itself -- the number of points in the rings
trace, read out of the live page -- not the widget, not the settings, and not
a signal count. A control that says something true while the picture says
something else is the fault this window has been reported for twice.
"""
from __future__ import annotations

import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

import prefs                                                 # noqa: E402

prefs.use_a_scratch_store()

ASK = """(function () {
  var divs = document.getElementsByClassName('plotly-graph-div');
  var out = {};
  for (var r = 0; r < divs.length; r++) {
    var el = divs[r];
    if (!el || !el.data) continue;
    for (var i = 0; i < el.data.length; i++) {
      var n = String(el.data[i].name || '');
      if (n.indexOf('(rings inside)') < 0) continue;
      out[n] = (el.data[i].x || []).length;
    }
  }
  return JSON.stringify(out);
})()"""


def main() -> int:
    prove = "--prove" in sys.argv
    sys.argv = ["audit_sliders_are_live"]

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication

    import gamut_app

    app = QApplication(sys.argv)
    window = gamut_app.GamutApp()
    window.resize(1500, 950)
    window.show()

    def settle(ms=1500):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    demo = HERE.parent / "demo"
    profiles = sorted(demo.glob("*.icc")) + sorted(demo.glob("*.ti3"))
    if not profiles:
        print("no demo profile to open — run scripts/make_demo_profiles.py")
        return 0
    window._load(profiles[0])
    settle(4000)

    # RINGS MUST BE ON, or there is no trace to change and the question this
    # asks does not exist.
    window._rings_on.setChecked(True)
    settle(3000)

    def read():
        answer = {}
        loop = QEventLoop()

        def got(value):
            answer["v"] = value
            loop.quit()

        window._view.page().runJavaScript(ASK, got)
        QTimer.singleShot(4000, loop.quit)
        loop.exec()
        return answer.get("v") or "{}"

    import json

    before = json.loads(read())
    if not before:
        print("  the picture has no rings trace, so nothing can be measured "
              "here.\n  (a shape must be open and 'Show rings inside' ticked)")
        return 0
    print(f"  before the drag: {before}")

    slider = window._rings
    start = slider.value()
    target = 20 if start < 14 else 6

    if prove:
        # THE MUTATION: put the OLD behaviour back -- valueChanged retitles the
        # label and touches nothing else, which is exactly how this slider was
        # wired when Basti reported it. If the check still says Clean with this
        # in force, it is blind and its Clean means nothing.
        #
        # AND THE MUTATION IS PROVEN TO LAND, because a mutation that silently
        # fails to apply looks identical to a check passing: the label must
        # still follow the handle (so the wiring was replaced, not destroyed)
        # while the picture must not.
        slider.valueChanged.disconnect()
        slider.valueChanged.connect(
            lambda v: window._rings_lbl.setText(str(v)))
        print("  --prove: the live handler is disconnected; the label alone "
              "follows the handle")

    # A REAL DRAG: pressed, held down, moved -- never setValue on its own.
    slider.setSliderDown(True)
    slider.sliderPressed.emit()
    slider.setValue(target)
    settle(2500)
    if prove and window._rings_lbl.text() != str(target):
        print(f"  THE MUTATION DID NOT LAND — the label says "
              f"{window._rings_lbl.text()!r}, not {str(target)!r}, so this "
              f"run tested nothing.")
        return 2
    during = json.loads(read())
    print(f"  while it is held at {target}: {during}")

    slider.setSliderDown(False)
    slider.sliderReleased.emit()
    settle(3000)
    after = json.loads(read())
    print(f"  after letting go: {after}")

    problems = []
    moved = [k for k in before if during.get(k) != before.get(k)]
    if not moved:
        problems.append(
            f"the picture did not change while the handle was down — the "
            f"rings trace still has {before} points, so this slider is "
            f"release-only")
    for key in during:
        if after.get(key) != during.get(key):
            problems.append(
                f"letting go changed {key} from {during.get(key)} back to "
                f"{after.get(key)} — the release is undoing the live change")

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: the picture followed the handle while it was down, and "
          "letting go\n  left it exactly where the drag had put it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
