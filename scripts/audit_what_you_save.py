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

# OFFSCREEN FOR MOST OF IT, AND NOT FOR ALL OF IT. Saving a picture asks the
# drawing library to render one itself, and without a compositor it answers
# "error creating static canvas/context for image server" -- so that section
# says it cannot be judged rather than reporting a fault that is the
# platform's. Run this on screen (QT_QPA_PLATFORM= python scripts/...) to
# have it checked.
OFFSCREEN = os.environ.get("QT_QPA_PLATFORM", "offscreen") == "offscreen"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
#: TAKEN BEFORE QT IS GIVEN A TIDY sys.argv. Overwriting it below is what the
#: window needs; reading a flag out of it afterwards finds nothing, silently —
#: a `--prove` written that way ran the ORDINARY pass and reported Clean.
ASKED = list(sys.argv[1:])
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
    # A SECOND SHAPE, so the two fades have something to act on. They are the
    # newest of the controls that change the picture without writing a page,
    # and they are the ones with most to go wrong: what they push is a colour
    # per corner and a triangle list, worked out here in Python.
    for i in range(win._compare.count()):
        data = win._compare.itemData(i)
        if data and data[0] == "space" and data[1] == "sRGB":
            win._compare.setCurrentIndex(i)
            win._on_compare_changed()
            break
    pump(6)

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
    # THE FADE, THROUGH THE LIVE PATH ONLY. `valueChanged` is what a drag
    # emits; `sliderReleased` is what the window uses to decide whether it
    # must rebuild. Setting the value without the release is exactly the
    # state a reader is in mid-drag, and it is the state in which the screen
    # and the file are free to disagree.
    win._agree.setValue(62)
    pump(6)

    if "--prove" in ASKED:
        # THE MUTATION: leave the screen faded and write the page as though it
        # were not. That is this check's whole subject in one line — the
        # screen is right, the reader's copy is not, and nobody finds out
        # until somebody else opens the file.
        real_options = win._render_options

        def as_if_nothing_were_faded(*a, **k):
            got = dict(real_options(*a, **k))
            got["agree"] = 1.0
            return got

        landed = as_if_nothing_were_faded().get("agree") != \
            real_options().get("agree")
        if not landed:
            print("  THE MUTATION DID NOT LAND — the fade was already at the "
                  "top, so writing\n  the page as though nothing were faded "
                  "changes nothing and this run tested\n  nothing.")
            return 2
        win._render_options = as_if_nothing_were_faded
        print("  --prove: the screen stays faded and the page is written as "
              "though it were not.\n  The check must notice.\n")

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

    def _fade_in(meshes):
        """The alpha the saved surfaces carry, or None if none is faded."""
        for mesh in meshes:
            colours = mesh.get("vertexcolor")
            if not isinstance(colours, list):
                continue
            for colour in colours:
                text = str(colour)
                if text.startswith("rgba("):
                    return text[:-1].rsplit(",", 1)[-1].strip()
        return None

    def one(what, on_screen, in_the_file):
        print(f"      {what:38s} screen {on_screen!r:>10}   "
              f"file {in_the_file!r:>10}   "
              f"{'ok' if on_screen == in_the_file else 'DIFFER'}")
        return None if on_screen == in_the_file else (
            f"[saved] {what}: the screen says {on_screen!r} and the page "
            f"says {in_the_file!r}")

    print("\n  WHAT THE SCREEN SAYS, AND WHAT THE FILE SAYS\n")
    problems = [p for p in (
        # THE FADE HAS TO BE IN THE FILE, and it shows as an alpha on every
        # corner of the surface it acts on. Read off the colours rather than
        # off a setting, because a setting recorded and never drawn would
        # pass a check of settings and hand the reader a different picture.
        one("how much of the agreement is left",
            f"{win._agree.value() / 100.0:.3f}",
            _fade_in(surfaces)),
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

    # ---- AND THE PICTURE, which is the third way out of this window -------
    # A still is re-rendered by the viewer at the size asked for, and its
    # height comes from the PANE's aspect -- so a narrow window saves a tall
    # picture. That is the shape the fitting exists for, and a picture framed
    # like the cropped view would carry the fault out of the window and into
    # somebody's document.
    print("\n  AND THE PICTURE IT SAVES\n")
    if OFFSCREEN:
        print("      not judged: the drawing library cannot render a picture "
              "without a screen. Run this with QT_QPA_PLATFORM= to include "
              "it.")
    from PIL import Image

    def edges_of(png, band=8):
        im = Image.open(png).convert("RGB")
        wide, tall = im.size
        px = im.load()

        def lit(x, y):
            r, g, b = px[x, y]
            return max(abs(r - 17), abs(g - 17), abs(b - 17)) > 12

        left = sum(1 for x in range(band) for y in range(tall) if lit(x, y))
        right = sum(1 for x in range(wide - band, wide)
                    for y in range(tall) if lit(x, y))
        drawn = sum(1 for x in range(0, wide, 4) for y in range(0, tall, 4)
                    if lit(x, y))
        return wide, tall, left, right, drawn

    win._timeline._clear_btn.click()
    pump(5)
    for label, size in (() if OFFSCREEN else (("a wide window", (1600, 1000)),
                                              ("a narrow one", (1000, 700)))):
        win.resize(*size)
        pump(6)
        shot = folder / f"still-{label.replace(' ', '-')}.png"
        try:
            win._save_still(shot, {"width": 1200, "format": "png",
                                   "background": "as-shown", "walls": "same"})
        except Exception as exc:                               # noqa: BLE001
            problems.append(f"[picture] {label}: it could not be saved: {exc}")
            continue
        wide, tall, left, right, drawn = edges_of(shot)
        print(f"      {label:14s} picture {wide}x{tall}   edges "
              f"{left}/{right}   drawn {drawn}")
        if not drawn:
            problems.append(f"[picture] {label}: the picture is empty")
        elif left or right:
            problems.append(
                f"[picture] {label}: the shape runs off the edge of the saved "
                f"picture ({left} left, {right} right)")

    print()
    # THE MUTATION'S OWN VERDICT COMES FIRST. Put after the report below, that
    # report's `return 1` wins and --prove exits as a failure while having
    # done exactly what it was asked to do.
    if "--prove" in ASKED:
        shutil.rmtree(folder, ignore_errors=True)
        win.close()
        if any("agreement" in line for line in problems):
            print("  With the page written as though nothing were faded, the "
                  "check said so.\n  It can see.")
            return 0
        print("  THE PAGE WAS WRITTEN UNFADED AND THE CHECK SAID NOTHING. "
              "It is blind.")
        return 1
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} value(s) reached the screen and not the "
              f"file.")
        shutil.rmtree(folder, ignore_errors=True)
        win.close()
        return 1
    # THE VERDICT SAYS WHAT WAS ACTUALLY JUDGED. Offscreen, the picture is
    # skipped a hundred lines above and this used to close with "both pages
    # carry the picture that was on screen" regardless -- a sentence that is
    # false in exactly the run where it is printed, and the default run at
    # that. A summary that reads the same whether or not the hardest third of
    # the check happened is how a measurement of the wrong thing comes to read
    # as coverage.
    if OFFSCREEN:
        print("  Clean AS FAR AS IT WAS LOOKED AT: both pages carry what was "
              "on screen.\n  The picture was NOT judged -- there is no screen "
              "to draw it on. Run this\n  with QT_QPA_PLATFORM= to include "
              "it.")
    else:
        print("  Clean: both pages and the saved picture carry what was on "
              "screen.")
    shutil.rmtree(folder, ignore_errors=True)
    win.close()
    pump(0.3)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
