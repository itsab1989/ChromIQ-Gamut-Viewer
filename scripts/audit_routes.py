"""Every route that writes a picture carries what the others learned.

WHY THIS EXISTS, AND IT IS THE MOST EXPENSIVE LESSON IN THIS PROJECT. There is
more than one way a picture gets written here -- the window's live view, its
Save, the two-room and cross-section arrangements, the run panel's live view,
the run's Save -- and every time a new one appeared it silently skipped
something the others had. Four faults in one evening, all the same shape:

  * THE RUN'S LIVE PICTURE went around _write_dark_html, so it never got the
    script that puts see-through surfaces in draw order. The shells came apart
    into missing triangles the moment they were made fainter: "this is no
    transparency but missing triangles and stuff again which we should have
    fixed for good already". It HAD been fixed for good -- in the writer that
    one call was avoiding.
  * THE RUN'S SAVE passed no movement settings, so its page built the ΔE
    threshold and none of the reader's strip.
  * TWO ROOMS, A CROSS-SECTION AND TWO CROSS-SECTIONS carried the styling for
    a block of numbers and no numbers, from a button whose dialog had just
    asked whether the numbers should travel.
  * And the run's page had no title, no page colour and no streak cure until
    it went through the same writer.

None of these is visible in the file that is written. Each was found by a
person looking at a picture, and each cost a report.

SO THIS ASKS EVERY ROUTE THE SAME QUESTIONS. It writes a page by each route
this application has, and looks for the features every page is supposed to
carry. A route that answers "no" to something its siblings answer "yes" to is
reported, whether or not anybody has noticed on screen yet.

    python scripts/audit_routes.py

Exit code 1 if any route is missing something the others have.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile

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
sys.argv = ["audit_routes"]

import numpy as np                                            # noqa: E402

#: What a written picture is supposed to carry, and how to see it in the file.
#: Each of these was learned the hard way and lives in one writer; a route
#: that does not go through that writer loses it in silence.
FEATURES = {
    "a name for the tab": (
        "<title>",
        "a page sent to somebody arrives showing its file name without it"),
    "the page's own colours": (
        "paper_bgcolor",
        "or the picture is drawn on the library's default white"),
    "a caption that fits its pane": (
        "cqCaption",
        "one line written for a wide pane runs off a narrow one, and this "
        "audit said Clean while six pages had no such script at all -- it was "
        "added to the writer most pages go through and not to the one that "
        "builds two rooms"),
    "a title that shrinks with the window": (
        "max-width:820px",
        "the caption is one line of SVG text that cannot wrap and is the same "
        "width whatever the screen, so on a narrow one its end simply falls "
        "off -- and nothing warns the reader, because the SVG clips rather "
        "than scrolling. Measured on a graph page that had no such rule: 463px "
        "of title in a 390px page, the last dozen characters gone. THIS IS "
        "THE THIRD THING TO GO MISSING FROM page_html, after the caption "
        "script and the page's colours, because it is written by hand rather "
        "than by ti3gamut's writer"),
}

#: WHY THE 480px RULE IS NOT ASKED FOR, only the 820px one. The pages that
#: ti3gamut writes carry both; the two-room and cross-section template carries
#: only the wider one, and that was measured rather than assumed before this
#: audit was allowed to have an opinion: a two-room page has no Plotly title
#: at all (its captions are HTML), and a cross-section's title is "lightness
#: L* = 50" -- 17 characters, 113px wide, sitting 269px INSIDE a 390px page.
#: Demanding the tighter rule there would report a fault that does not exist,
#: which is the other way an audit wastes a day.
#:
#: Features that only apply where they can. A drift cloud has a ΔE per point
#: and a picture of two papers has not, so asking every route for the reader's
#: threshold would report a fault that is not one.
WHERE_IT_APPLIES = {
    "the reader's own ΔE threshold": ('data-cq="cut"', "clouds"),
    "the numbers, when they were asked for": ("cq-notes", "notes"),
    # THE STREAK CURE IS FOR A 3D SCENE AND NOTHING ELSE, and this audit
    # reported its absence from the cross-section on its first run. Checked
    # rather than assumed: a flat cut's axes carry no spike lines at all
    # (showspikes is None, the library's 2D default of off), so there are no
    # pointing lines to leave streaks and nothing for the cure to do. A rule
    # that demanded it everywhere would have had somebody "fixing" a page
    # that was already right -- which is the other way an audit wastes a day.
    "the hover-streak cure": ("spikethickness", "3d"),
    # A LINE GRAPH HAS NO SURFACES TO ORDER AND NO CAMERA TO SEND HOME, and
    # both of these sat in the unconditional list only because every route
    # this audit knew about was a 3D one. Adding the run's graph made that
    # assumption visible: it was reported as missing two features it cannot
    # have. Checked against a real graph page before moving them -- cqOrder
    # is absent (nothing see-through to sort) and the page carries its words
    # under `class="words"` rather than `cq-notes`.
    "the see-through draw order": ("cqOrder", "3d"),
    # A RESET BELONGS TO A CAMERA, and a line graph has neither. Measured
    # before moving it: a cloud page saved the SMALL way (14 kB, library
    # fetched) still carries this, because the page's own control strip names
    # it -- so for a 3D route the check is real. A graph page carries no
    # strip at all and no camera to send home.
    "one reset, the one that goes home": ("resetCameraDefault3d", "3d"),
}


def blob(seed, scale=1.0):
    from gamutview import build_gamut

    rng = np.random.default_rng(seed)
    points = rng.normal(size=(80, 3)) * np.array([12.0, 20.0, 20.0]) * scale
    points[:, 0] += 50.0
    return build_gamut(points, input_space="lab", space="lab")


def a_cloud(n=300):
    rng = np.random.default_rng(5)
    lab = np.column_stack([rng.uniform(20, 92, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    return lab, rng.uniform(0.4, 4.0, n)


NOTES = "Matte-paper holds 812,144 units of colour."
SPIN = {"on": True, "mode": "turn", "speed": 6, "sweep": 60,
        "tilt_mode": "swing", "tilt_speed": 4, "tilt_sweep": 30, "glide": True}


def routes(folder):
    """(name, the file it wrote, what it holds) for every writing route."""
    import ti3gamut

    one = [("paper-1", blob(1))]
    two = one + [("paper-2", blob(2, 0.75))]
    lab, de = a_cloud()
    made = []

    out = folder / "one-scene.html"
    ti3gamut.write_html(one, out, "one shape", carry_viewer=False,
                        controls=True, spin=SPIN, notes=NOTES)
    made.append(("the window's single scene", out, {"notes", "3d"}))

    out = folder / "two-rooms.html"
    figures = [(name, ti3gamut.build_figure([(name, g)], name))
               for name, g in two]
    ti3gamut.write_side_by_side_html(figures, out, spin=SPIN, controls=True,
                                     notes=NOTES)
    made.append(("the window's two rooms", out, {"notes", "3d"}))

    out = folder / "cross-section.html"
    ti3gamut.write_slice_html(two, out, 50.0, "a cut", controls=True,
                              notes=NOTES, carry_viewer=False)
    made.append(("the window's cross-section", out, {"notes"}))

    out = folder / "two-cuts.html"
    flat = [(name, ti3gamut.build_slice_figure([(name, g)], 50.0, name))
            for name, g in two]
    ti3gamut.write_side_by_side_html(flat, out, controls=True, notes=NOTES)
    made.append(("the window's two cross-sections", out, {"notes"}))

    out = folder / "drift-cloud.html"
    ti3gamut.write_html([], out, "a drift cloud", carry_viewer=False,
                        controls=True, spin=SPIN, notes=NOTES,
                        drift=(lab, de, "2019 → 2024", None, True))
    made.append(("a drift cloud", out, {"notes", "clouds", "3d"}))
    return made


def through_the_window(folder):
    """The two routes that only exist inside the running application.

    THE RUN'S LIVE VIEW IS A ROUTE, and it is the one that had been going
    around the writer. It cannot be reached from the module alone: it is what
    the window does when a run owns the picture.
    """
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    win = gamut_app.GamutApp([])
    win.resize(1400, 900)
    win.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

    def pump(seconds):
        import time
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(2.5)
    profiles = sorted(pathlib.Path(tempfile.gettempdir())
                      .glob("showme-*/printer-*.icc"))
    if len(profiles) < 2:
        demo = HERE.parent / "demo"
        win.close()
        return [], f"no demo profiles to drive the window with (looked beside {demo})"
    panel = win._timeline
    panel.add(profiles)
    pump(7)
    for i in range(panel._picture_of.count()):
        if panel._picture_of.itemData(i) == ("whole", 0):
            panel._picture_of.setCurrentIndex(i)
            break
    panel._draw()
    pump(3)
    panel._with_shapes.setChecked(True)
    pump(3)

    made = []
    live = sorted(win._tmp.glob("run-*.html"))
    if live:
        out = folder / "run-live.html"
        shutil.copy(live[-1], out)
        made.append(("the run's live view", out, {"clouds", "3d"}))
    out = folder / "run-saved.html"
    panel.write_page(out, carry_viewer=False, controls=True, numbers=True)
    made.append(("the run's saved page", out, {"clouds", "notes", "3d"}))

    # AND THE RUN'S GRAPH, WHICH IS A DIFFERENT WRITER AND WAS NEVER ASKED.
    #
    # Everything above chose a PAIR, so every page this audit had ever looked
    # at went through ti3gamut's writer. With no pair chosen the panel draws
    # the whole run as a line graph and writes it with `page_html`, a second
    # writer built by hand -- and that is the route that has now quietly lost
    # two of the features in this very table: the caption script once, and the
    # rule that shrinks a title on a phone after that. Both were found from
    # outside, by somebody looking at a page, while this said "Clean".
    #
    # A graph has no 3D scene and no cloud, so it is asked only for what a
    # flat picture can have.
    for i in range(panel._picture_of.count()):
        if panel._picture_of.itemData(i) is None:
            panel._picture_of.setCurrentIndex(i)
            break
    panel._draw()
    pump(3)
    out = folder / "run-graph.html"
    panel.write_page(out, carry_viewer=False, controls=True, numbers=True)
    made.append(("the run's graph, saved", out, set()))

    scenes = sorted(win._tmp.glob("scene-*.html"))
    if scenes:
        out = folder / "window-live.html"
        shutil.copy(scenes[-1], out)
        made.append(("the window's live view", out, {"3d"}))
    win.close()
    pump(0.5)
    return made, ""


def main() -> int:
    folder = pathlib.Path(tempfile.mkdtemp(prefix="routes-"))
    print(f"  pages written to {folder}")
    problems = []
    try:
        made = routes(folder)
        driven, why = through_the_window(folder)
        made += driven
        if why:
            problems.append(f"[skipped] {why}")

        width = max(len(name) for name, _p, _h in made)
        head = "   " + " ".join(f"{n[:14]:>15s}" for n in FEATURES)
        print(f"\n{'':{width}}{head}")
        for name, page, holds in made:
            text = page.read_text(encoding="utf-8", errors="ignore")
            marks = []
            for what, (mark, why_it_matters) in FEATURES.items():
                there = mark in text
                marks.append(f"{'yes' if there else 'NO':>15s}")
                if not there:
                    problems.append(
                        f"[route] {name} has no {what} — {why_it_matters}")
            for what, (mark, needs) in WHERE_IT_APPLIES.items():
                if needs in holds and mark not in text:
                    problems.append(
                        f"[route] {name} was asked for {what} and does not "
                        f"carry it")
            print(f"{name:{width}}   " + " ".join(marks))
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} problem(s).")
        return 1
    print("  Clean: every route carries what the others learned.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
