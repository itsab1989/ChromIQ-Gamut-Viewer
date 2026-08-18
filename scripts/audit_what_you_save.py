"""Is the page you save the picture you were looking at?

WHY THIS IS NEW WORK RATHER THAN AN OLD CHECK. Until this week almost every
control rebuilt the whole page, so the screen and the file could hardly
disagree: both were written from the same recorded values, one after the
other. Seven controls now change the picture WITHOUT writing a page — the
solidity, the shading depth, the chart's four dot settings, its skin, the box
and its grid, and both threshold sliders.

That is a new way to be wrong, and it is the quiet kind: the screen is right,
the reader's copy is not, and nobody finds out until somebody else opens the
file. The live change has to be recorded as well as pushed, and "as well as"
is exactly the sort of thing that gets left out. It has happened here before
-- Show the greys turned the shape down on screen and never in the settings,
so the next rebuild closed it up again.

WHAT THIS DOES. It sets a state a person could set, entirely through the live
paths, and then saves a page the way the button does. Then it reads the file
and compares what is in it against what is on screen. Each value is
distinctive, so a page written from defaults fails loudly rather than
accidentally matching.

    python scripts/audit_what_you_save.py

Exit code 1 if the file disagrees with the screen.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_what_you_save"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

from PyQt6.QtWidgets import QApplication                       # noqa: E402


def how_many(value) -> int:
    """How many points an array in a written page holds.

    THE ARRAYS TRAVEL PACKED, and this audit believed the wrong number before
    it was told: a packed array arrives as {"dtype": …, "bdata": …}, so asking
    Python for its length answers TWO -- the number of keys -- and the run's
    saved page was reported as drawing 2 colours where the screen showed 149.
    The page was right; the check was counting a dictionary.

    Third time this family of mistake has been made in a week, twice in this
    audit's own siblings: what a check cannot read, it reports as a fault.
    """
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict) and "bdata" in value:
        import base64

        import numpy as np

        raw = base64.b64decode(value["bdata"])
        return len(raw) // np.dtype(value.get("dtype", "f8")).itemsize
    return 0


def _json_at(text: str, at: int):
    """Read one JSON value out of *text* starting at *at*, by matching brackets.

    A PATTERN WOULD NOT DO, and the first version of this audit proved it. A
    saved page carries the drawing library's own TEMPLATE inside the layout,
    and the template has a full set of axes -- so a pattern hunting for "the
    scene's x axis" found the template's, which is always visible, and this
    audit reported the box switch as lost on the way into the file. It is not
    lost: written with the box off, the file says "visible":false three times,
    once per axis. Reading the layout as one value and then looking INSIDE it
    cannot make that mistake, because the template sits under its own key.
    """
    opener = text[at]
    closer = {"[": "]", "{": "}"}[opener]
    depth, i, in_string, escaped = 0, at, False, False
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(text[at:i + 1]), i + 1
        i += 1
    raise ValueError("unbalanced JSON in the page")


def figures_in(page: pathlib.Path):
    """The traces and the layout the written page draws with."""
    text = page.read_text(encoding="utf-8", errors="ignore")
    call = text.index("Plotly.newPlot(")
    at = text.index("[", call)
    traces, after = _json_at(text, at)
    layout, _ = _json_at(text, text.index("{", after))
    return traces, layout


def main() -> int:
    from PyQt6.QtWidgets import QApplication

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

    pump(3)
    demo = HERE.parent / "demo"
    profiles = sorted(pathlib.Path(tempfile.gettempdir())
                      .glob("showme-*/printer-*.icc"))
    if not profiles:
        print("  no demo profiles to drive the window with")
        return 1
    win._load(profiles[0])
    pump(6)
    win._open_chart_file(demo / "verification-chart-480.ti1")
    pump(7)

    # A STATE NOBODY WOULD REACH BY ACCIDENT, set only through the controls
    # that no longer write a page. Distinctive values, so a file written from
    # the defaults cannot pass by coincidence.
    win._opacity.setValue(37)
    win._opacity.sliderReleased.emit()
    win._depth.setValue(81)
    win._depth.sliderReleased.emit()
    win._chart_dot.setValue(74)               # 7.4 across
    win._chart_dot_opacity.setValue(43)
    win._chart_out_dot.setValue(96)           # 9.6 across
    win._chart_out_opacity.setValue(21)
    win._grid_on.setChecked(False)
    pump(6)

    folder = pathlib.Path(tempfile.mkdtemp(prefix="what-you-save-"))
    out = folder / "saved.html"
    # THE SAVE ROUTE ITSELF, not a hand-rolled call: _write_scene is what the
    # button reaches, and the argument list is the thing being checked.
    win._write_scene(*win._scene_contents()[:2], win._scene_contents()[2],
                     win._scene_contents()[3], out, controls=True,
                     carry_viewer=False)
    pump(2)
    traces, layout = figures_in(out)
    surfaces = [t for t in traces if t.get("type") == "mesh3d"]

    def cloud(kind):
        return [(t.get("marker") or {}) for t in traces
                if str(t.get("legendgroup", "")).endswith("-" + kind)
                and t.get("hoverinfo") != "skip"]

    printed, outside = cloud("printed"), cloud("outside")
    # THE FIGURE'S OWN AXES, reached through the layout rather than found in
    # it -- layout["template"] holds another set, and that is what the first
    # version of this audit was reading.
    axis = ((layout.get("scene") or {}).get("xaxis") or {})

    def one(what, on_screen, in_the_file):
        print(f"      {what:38s} screen {on_screen!r:>10}   "
              f"file {in_the_file!r:>10}   "
              f"{'ok' if on_screen == in_the_file else 'DIFFER'}")
        return None if on_screen == in_the_file else (
            f"[saved] {what}: the screen says {on_screen!r} and the page "
            f"says {in_the_file!r}")

    print("\n  WHAT THE SCREEN SAYS, AND WHAT THE FILE SAYS\n")
    problems = [p for p in (
        one("how solid the shapes look",
            round(win._opacity.value() / 100.0, 3),
            round(surfaces[0].get("opacity", -1), 3) if surfaces else None),
        one("how big the chart's dots are",
            win._chart_dot.value() / 10.0,
            printed[0].get("size") if printed else None),
        one("how solid the chart's dots are",
            round(win._chart_dot_opacity.value() / 100.0, 3),
            round(printed[0].get("opacity", -1), 3) if printed else None),
        one("how big the out-of-reach dots are",
            win._chart_out_dot.value() / 10.0,
            outside[0].get("size") if outside else None),
        one("how solid the out-of-reach dots are",
            round(win._chart_out_opacity.value() / 100.0, 3),
            round(outside[0].get("opacity", -1), 3) if outside else None),
        one("the box and its grid",
            win._grid_on.isChecked(), bool(axis.get("visible", True))),
    ) if p]

    # AND THE SHADING, which is a set of five numbers rather than one, so it
    # is compared as the picture would show it: the surface's own lighting.
    if surfaces:
        want = 81 / 100.0
        lit = surfaces[0].get("lighting", {}) or {}
        expected = round(0.10 + 0.75 * want, 4)
        got = round(float(lit.get("diffuse", -1)), 4)
        problems += [p for p in (one("how deep the shading is (diffuse)",
                                     expected, got),) if p]

    # ---- AND THE RUN'S OWN PAGE, which is a second writing route ---------
    # The same risk, one route further along: the run's threshold hides dots
    # live and its two shells fade live, so both have to reach the file as
    # well as the screen. A check that covered only the window's own scene
    # would have said "clean" about half the application.
    print("\n  AND THE RUN'S OWN PAGE\n")
    panel = win._timeline
    panel.add(profiles)
    pump(8)
    for i in range(panel._picture_of.count()):
        if panel._picture_of.itemData(i) == ("whole", 0):
            panel._picture_of.setCurrentIndex(i)
            break
    panel._draw()
    pump(4)
    panel._with_shapes.setChecked(True)
    pump(5)
    # Half way up the threshold, and the shells at a distinctive strength.
    panel._cut.setValue((panel._cut.minimum() + panel._cut.maximum()) // 2)
    pump(3)
    win._opacity.setValue(52)
    win._opacity.sliderReleased.emit()
    pump(4)

    run_page = folder / "run.html"
    panel.write_page(run_page, carry_viewer=False, controls=True,
                     numbers=True)
    pump(2)
    run_traces, run_layout = figures_in(run_page)
    run_surfaces = [t for t in run_traces if t.get("type") == "mesh3d"]
    dots = [t for t in run_traces
            if t.get("type") == "scatter3d" and t.get("mode") == "markers"
            and t.get("hoverinfo") != "skip"]
    drawn_dots = sum(how_many(t.get("x")) for t in dots)

    import numpy as _np
    from ti3gamut import compare_profiles

    pair = panel._chosen_pair()
    d = compare_profiles(pair[0], pair[1], steps=panel.GRID)
    cut = panel._cut_off()
    should_draw = int(_np.sum(_np.asarray(d.deltas) >= cut)) if cut \
        else len(d.deltas)

    problems += [p for p in (
        one("how solid the run's shells look",
            round(win._opacity.value() / 100.0, 3),
            round(run_surfaces[0].get("opacity", -1), 3)
            if run_surfaces else None),
        one("how many colours survive the threshold",
            should_draw, drawn_dots),
    ) if p]

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} value(s) reached the screen and not the "
              f"file.")
        shutil.rmtree(folder, ignore_errors=True)
        win.close()
        return 1
    print("  Clean: both pages carry the picture that was on screen.")
    shutil.rmtree(folder, ignore_errors=True)
    win.close()
    pump(0.3)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
