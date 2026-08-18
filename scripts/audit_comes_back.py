"""Does the window come back tomorrow the way you left it — picture and all?

TWO THINGS HAVE TO SURVIVE A RESTART, and only one of them is obvious. The
CONTROLS have to come back where they were, which is what the settings are
for. And the PICTURE has to come back matching them, which is a different
claim: several settings are kept twice over -- once as the slider's own value
and once inside the per-shape record the renderer reads -- and a restart is
exactly where two copies of one number get to disagree.

IT HAS HAPPENED HERE. "Show the greys" turned the shape down on screen and
never in the record, so the next rebuild put it back to solid: a value that
reached the picture and not the store. This asks the opposite question, and
the answer is known in advance -- everything comes back, and the picture
agrees with the controls.

THE AWKWARD CASE IS DRAGGED-BUT-NOT-LET-GO. A slider writes its own value on
every step; the per-shape record is written when the handle is released. Quit
in between -- or leave it, since a crash is exactly the case the settings are
written eagerly for -- and the two copies part company. What must NOT happen
is a window that opens showing 37% beside a shape drawn solid.

    python scripts/audit_comes_back.py

Exit code 1 if a setting is lost, or if the picture disagrees with the
controls it is drawn from.
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
sys.argv = ["audit_comes_back"]

import prefs                                                   # noqa: E402

#: ONE STORE FOR BOTH WINDOWS, which is the whole point: the second window
#: has to find what the first one wrote.
STORE = prefs.use_a_scratch_store()

#: What is set in the first window, and what each one must come back as.
#: Distinctive values, so a control that was never written cannot pass by
#: sitting on a default that happens to match.
SETTINGS = {
    "opacity": 37,
    "depth": 81,
    "chart_dot": 74,
    "chart_out_opacity": 21,
    "rings": 9,
    "turn_sweep": 123,
}

ASK = """
(function () {
  var d = document.getElementsByClassName('plotly-graph-div')[0];
  if (!d) return "{}";
  var data = d._fullData || d.data || [], out = {surfaces: [], box: null};
  for (var i = 0; i < data.length; i++) {
    if (data[i].type === "mesh3d") out.surfaces.push(data[i].opacity);
  }
  var scene = (d._fullLayout || {}).scene || {};
  out.box = !!((scene.xaxis || {}).visible);
  return JSON.stringify(out);
})()
"""


def main() -> int:
    from PyQt6.QtWidgets import QApplication

    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    def a_window():
        win = gamut_app.GamutApp([])
        win.resize(1400, 900)
        win.show()
        pump(3)
        return win

    def picture(win):
        got = []
        page = win._view.page()
        if page is None:
            return {}
        page.runJavaScript(ASK, got.append)
        end = time.time() + 6
        while not got and time.time() < end:
            app.processEvents()
            time.sleep(0.005)
        try:
            return json.loads(got[0]) if got else {}
        except (TypeError, ValueError):
            return {}

    profiles = sorted(pathlib.Path(tempfile.gettempdir())
                      .glob("showme-*/printer-*.icc"))
    if not profiles:
        print("  no demo profiles to drive the window with")
        return 1

    first = a_window()
    first._load(profiles[0])
    pump(6)
    for name, value in SETTINGS.items():
        slider = getattr(first, "_" + name)
        slider.setValue(value)
        slider.sliderReleased.emit()
        pump(0.6)
    first._grid_on.setChecked(False)
    first._rings_on.setChecked(True)
    pump(5)
    was_drawn = picture(first)
    print(f"  the first window drew: {was_drawn}")
    first.close()
    pump(1.5)

    second = a_window()
    second._load(profiles[0])
    pump(7)
    now_drawn = picture(second)
    print(f"  the second window drew: {now_drawn}\n")

    problems = []
    for name, value in SETTINGS.items():
        came_back = getattr(second, "_" + name).value()
        ok = came_back == value
        print(f"      {name:22s} left at {value:4d}   came back {came_back:4d}"
              f"   {'ok' if ok else 'LOST'}")
        if not ok:
            problems.append(f"[restart] {name}: left at {value} and came back "
                            f"at {came_back}")
    for name, want in (("the box and its grid", False),
                       ("show rings inside", True)):
        widget = second._grid_on if "box" in name else second._rings_on
        ok = widget.isChecked() == want
        print(f"      {name:22s} left {want!r:>6}   came back "
              f"{widget.isChecked()!r:>6}   {'ok' if ok else 'LOST'}")
        if not ok:
            problems.append(f"[restart] {name} did not come back")

    # AND THE PICTURE AGREES WITH THE CONTROLS. Reading the slider rather than
    # the record the renderer uses, because those are the two things that can
    # part company -- asking the record would be asking the picture to agree
    # with itself.
    want = round(second._opacity.value() / 100.0, 3)
    drawn = [round(o, 3) for o in now_drawn.get("surfaces", [])]
    print(f"\n      the shapes are drawn at {drawn}, and the slider says "
          f"{want}")
    if drawn and any(o != want for o in drawn):
        problems.append(
            f"[restart] the window opens showing {want} on the slider and "
            f"{drawn} in the picture")
    if now_drawn.get("box") is not False:
        problems.append(
            "[restart] the box was switched off and the picture came back "
            "with it")

    # ---- AND THE AWKWARD CASE: DRAGGED, NEVER LET GO --------------------
    # A slider writes its own value on every step of a drag; the record the
    # renderer reads is written when the handle is released. Quit in between
    # -- which is the very case the settings are written eagerly FOR -- and
    # the two copies of one number part company. The failure looks exactly
    # like the one reported on screen last week: a number beside a slider
    # that the picture does not agree with.
    print("\n  AND AFTER A DRAG THAT WAS NEVER LET GO\n")
    second._opacity.setValue(64)          # valueChanged only, no release
    pump(3)
    second.close()
    pump(1.5)

    third = a_window()
    third._load(profiles[0])
    pump(7)
    after = picture(third)
    says = round(third._opacity.value() / 100.0, 3)
    drawn_now = [round(o, 3) for o in after.get("surfaces", [])]
    print(f"      the slider says {says}, the picture is drawn at "
          f"{drawn_now}")
    if drawn_now and any(o != says for o in drawn_now):
        problems.append(
            f"[restart] after a drag that was never let go, the window opens "
            f"saying {says} beside a picture drawn at {drawn_now}")
    third.close()
    pump(0.5)
    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} thing(s) did not survive a restart.")
        return 1
    print("  Clean: everything came back, and the picture matches the "
          "controls it is drawn from.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
