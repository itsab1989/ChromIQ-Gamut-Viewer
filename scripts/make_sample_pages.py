"""The showcase pages, written by the real window, and checked against what
the showcase says about them.

    python scripts/make_sample_pages.py [--out docs/pages]

WHY THE REAL WINDOW. These pages are the advertisement for a feature, and an
advertisement built by a script that calls the drawing code directly proves
only that the drawing code works. It cannot catch a control that no longer
reaches the export, a setting the window quietly overrides, or a scene that
comes out empty -- and those are exactly the faults a visitor would meet
first. Every page below is produced by pressing the window's own Save button,
through its own dialogs.

WHY EACH ONE IS THEN READ BACK. `docs/index.html` makes a claim about every
page -- "saved with the movement running", "202 inside, 23 on the edge", "80 kB
instead of 5 MB". A claim nobody checks is a claim that goes stale the first
time a default changes. Each scene therefore carries the assertions that make
its own card on the index page true, and this exits 1 if any of them is not.

Exit code is 1 if any page is missing, empty, or does not match its claim.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["make_sample_pages"]

DEMO = pathlib.Path(os.environ.get("GAMUTVIEW_DEMO", str(HERE.parent / "demo")))

GLOSSY = DEMO / "Glossy-paper.ti3"
MATTE = DEMO / "Matte-paper.ti3"
LATER = DEMO / "Glossy-paper-months-later.ti3"
PROFILE = DEMO / "Glossy-paper.icc"
CHART = DEMO / "verification-chart-480.ti1"

failures: list[str] = []

#: What the save dialog ticks for a new export: the controls that were always
#: there. Anything added since is opt-in, so nobody's exports change shape
#: without them asking.
DEFAULT_OFFER = {"play": True, "speed": True, "lr": True, "ud": True,
                 "reset": True, "remember": True, "zoom": True, "move": True,
                 "notes": True,
                 # Added with the per-shape controls. On by default in the
                 # save dialog too, so these pages show what a person gets
                 # when they save one without opening that section at all --
                 # which is the only honest thing for a showcase to show.
                 "opacity": True, "wires": True, "grey": True,
                 "views": True, "fullscreen": True, "picture": True,
                 "cut": True, "agree": True,
                 # Off by default, like the per-direction speeds it sits
                 # beside: a finer control for something the single speed
                 # already covers for most people.
                 "sweep": False}

#: Everything the page can carry, for the one sample that shows it off.
EVERY_CONTROL = dict(DEFAULT_OFFER, speed_each=True, grid=True, labels=True,
                     key=True, appearance=True, speed=False, sweep=True)

#: How many bytes one number takes, per the dtype names plotly writes.
_WIDTH = {"f8": 8, "f4": 4, "i8": 8, "i4": 4, "i2": 2, "i1": 1,
          "u1": 1, "u2": 2, "u4": 4}


def _count(values) -> int:
    """How many points a trace really holds.

    NOT len(). Plotly packs any sizeable array as base64 in
    {"dtype": ..., "bdata": ...}, so len() on a 480-patch trace returns 2 --
    the number of keys in that dict. Reading those twos as patch counts is
    how a first pass at this concluded a chart had two patches in it.
    """
    import base64

    if isinstance(values, dict) and "bdata" in values:
        raw = base64.b64decode(values["bdata"])
        return len(raw) // _WIDTH.get(values.get("dtype", "f8"), 8)
    return len(values) if isinstance(values, list) else 0


def scenes(body: str) -> dict:
    """{scene id: [trace types]} for every plot drawn on the page.

    How many rooms the page has, and whether they are 3D or flat, is the one
    thing that says which of the window's four arrangements was written -- and
    three of the four used to come out as a different one.
    """
    import json

    out = {}
    for m in re.finditer(r'Plotly\.newPlot\(\s*"(scene\d)",\s*(\[.*?\]),'
                         r'\s*\{"template"', body, re.S):
        out[m.group(1)] = sorted({t.get("type", "?")
                                  for t in json.loads(m.group(2))})
    return out


def traces_drawn(body: str) -> int:
    """How many separate things the browser is asked to draw, in total.

    NOT the file size, which is dominated by the bundled viewer and barely
    moves. This is what a phone feels: every trace is its own WebGL object
    with its own draw call. Counted across every room, because the
    side-by-side arrangements write more than one.
    """
    import json

    total = 0
    for m in re.finditer(r'Plotly\.newPlot\(\s*"(scene\d)",\s*(\[.*?\]),'
                         r'\s*\{"template"', body, re.S):
        total += len(json.loads(m.group(2)))
    return total


def drawn_names(body: str) -> set:
    """The names of everything actually drawn, across every room.

    The page's own text is not evidence of what is in the picture: the
    bundled viewer's source comments name colour spaces, so grepping the file
    reports shapes that are not there.
    """
    import json

    out = set()
    for m in re.finditer(r'Plotly\.newPlot\(\s*"(scene\d)",\s*(\[.*?\]),'
                         r'\s*\{"template"', body, re.S):
        for trace in json.loads(m.group(2)):
            name = trace.get("name")
            if name:
                out.add(re.sub(r" \((outline|rings inside)\)$", "", name))
    return out


def cage_colours(body: str) -> set:
    """Every colour the outlines on this page are drawn in.

    A cage is one trace whose ``line.color`` is a list, one entry per point.
    A plain grey cage is one trace whose ``line.color`` is a single string.
    Both are read here, so the question "is it drawn in its own colours"
    survives a change in how the cage is put together.
    """
    import json

    out = set()
    for m in re.finditer(r'Plotly\.newPlot\(\s*"(scene\d)",\s*(\[.*?\]),'
                         r'\s*\{"template"', body, re.S):
        for trace in json.loads(m.group(2)):
            if trace.get("mode") != "lines":
                continue
            colour = (trace.get("line") or {}).get("color")
            if isinstance(colour, list):
                out.update(colour)
            elif colour:
                out.add(colour)
    return out


def patch_counts(body: str) -> tuple[int, int]:
    """(within reach, beyond it) for the chart drawn on this page.

    The single-point traces are skipped: those are the fixed-size keys drawn
    beside the picture, not data. Counting them as patches is a mistake this
    project has already made once, in a harness that then reported 34,560
    broken checks against an application that was behaving correctly.
    """
    import json

    m = re.search(r'Plotly\.newPlot\(\s*"scene0",\s*(\[.*?\]),\s*\{"template"',
                  body, re.S)
    if not m:
        return (0, 0)
    inside = outside = 0
    for trace in json.loads(m.group(1)):
        n = _count(trace.get("x"))
        if n <= 1:
            continue
        name = str(trace.get("name", ""))
        if name.endswith("to be printed"):
            inside += n
        elif name.endswith("outside"):
            outside += n
    return (inside, outside)


def check(page: str, claim: str, ok: bool, detail: str = "") -> None:
    mark = "  ok  " if ok else " FAIL "
    print(f"  [{mark}] {claim}")
    if detail:
        print(f"           {detail}")
    if not ok:
        failures.append(f"{page}: {claim}" + (f" ({detail})" if detail else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE.parent / "docs" / "pages"))
    args = ap.parse_args()
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for needed in (GLOSSY, MATTE, PROFILE, CHART):
        if not needed.exists():
            print(f"missing demo file: {needed}")
            return 1

    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    QSettings("MeasuredGamutViewer", "MeasuredGamutViewer").clear()
    import gamut_app

    app = QApplication(sys.argv)
    w = gamut_app.GamutApp([])
    w.resize(1280, 860)
    w.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    # BOTH DIALOGS, NOT ONE. Save opens an options dialog first and a file
    # dialog second; stubbing only the file dialog leaves the first one on
    # screen waiting for a click that never comes, which is how an earlier
    # run of this appeared to hang.
    def save_to(target: pathlib.Path, carry: bool = True,
                numbers: bool = False, offer=None) -> None:
        from PyQt6.QtWidgets import QDialog

        class Options:
            def __init__(self, *a, **k):
                pass

            def exec(self):
                return QDialog.DialogCode.Accepted.value

            def choices(self):
                return {"carry_viewer": carry, "numbers": numbers,
                        "controls": offer is not False,
                        "offer": (offer if isinstance(offer, dict) else
                                  DEFAULT_OFFER)}

        class Files:
            def __init__(self, *a, **k):
                pass

            def setAcceptMode(self, *a):
                pass

            def setDefaultSuffix(self, *a):
                pass

            def exec(self):
                return 1

            def selectedFiles(self):
                return [str(target)]

        old_dialog, old_options = w._file_dialog, gamut_app.WebPageDialog
        w._file_dialog = lambda *a, **k: Files()
        gamut_app.WebPageDialog = Options
        try:
            w._on_save()
            pump(1.0)
        finally:
            w._file_dialog = old_dialog
            gamut_app.WebPageDialog = old_options

    def spin(on=True, turn="round", turn_speed=7, turn_sweep=60,
             tilt="off", tilt_speed=5, tilt_sweep=20) -> None:
        w._spin_on.setChecked(on)
        for combo, mode in ((w._turn_mode, turn), (w._tilt_mode, tilt)):
            combo.setCurrentIndex(combo.findData(mode))
        w._turn_speed.setValue(turn_speed)
        w._turn_sweep.setValue(turn_sweep)
        w._tilt_speed.setValue(tilt_speed)
        w._tilt_sweep.setValue(tilt_sweep)
        pump(0.2)

    def fresh() -> None:
        """Back to nothing open, so one scene cannot leak into the next.

        THE COMPARISON HAS TO BE PUT BACK BY HAND, and finding that out cost a
        published page. `GamutApp._on_clear` says it "closes everything on
        screen" and clears the measurements, the chart and its placement -- but
        not the shape chosen under "Compare with". So Adobe RGB (1998), picked
        for page 14, was still selected when page 18 was written several pages
        later, and went into it: 365 of that page's 642 traces were a colour
        space that has nothing to do with two profiles of one printer.

        Whether Clear SHOULD forget the comparison is a real question and not
        obviously a bug -- somebody working through one paper after another
        against sRGB would not thank us for dropping it every time. That is
        Basti's call. What is not in question is that a generator writing
        eighteen unrelated scenes must not rely on the answer, so it is set
        back explicitly here.
        """
        w._on_clear()
        w._compare.setCurrentIndex(0)          # "Nothing — this one on its own"
        w._on_compare_changed()
        pump(0.6)
        assert w._reference is None, (
            "the comparison shape survived a fresh(); every page after this "
            "one would carry it")

    made: list[tuple[str, pathlib.Path]] = []
    #: Temporary folders this run makes, cleared at the end when it passes.
    leftovers: list[pathlib.Path] = []

    def page(name: str) -> pathlib.Path:
        target = out_dir / name
        if target.exists():
            target.unlink()
        return target

    # ---------------------------------------------------------------- 01
    print("\n01 — one paper, standing still")
    fresh()
    w._load(GLOSSY)
    pump(2.0)
    spin(on=False, turn="round", turn_speed=8)
    p = page("01-one-paper-still.html")
    save_to(p)
    made.append(("01", p))
    body = p.read_text(encoding="utf-8") if p.exists() else ""
    check("01", "the page was written", p.exists() and len(body) > 100_000,
          f"{len(body):,} characters")
    check("01", "it opens standing still, as the card says",
          '"on": false' in body)
    check("01", "the paper is named in the tab",
          "<title>Glossy-paper" in body)
    check("01", "the reader still gets the controls",
          "cq-spin-bar" in body)

    # ---------------------------------------------------------------- 02
    print("\n02 — the same paper, turning by itself")
    spin(on=True, turn="round", turn_speed=7)
    p = page("02-one-paper-turning.html")
    save_to(p)
    made.append(("02", p))
    body = p.read_text(encoding="utf-8")
    check("02", "it opens with the movement running", '"on": true' in body)
    check("02", "turning all the way round, as the card says",
          '"turn": {"mode": "round"' in body)

    # ---------------------------------------------------------------- 03
    print("\n03 — turning and tipping, with the numbers underneath")
    spin(on=True, turn="round", turn_speed=6, tilt="swing",
         tilt_speed=5, tilt_sweep=28)
    p = page("03-turning-and-tipping.html")
    save_to(p, numbers=True)
    made.append(("03", p))
    body = p.read_text(encoding="utf-8")
    check("03", "both directions are moving, as the card says",
          '"turn": {"mode": "round"' in body and '"tilt": {"mode": "swing"' in body)
    check("03", "the figures really are written under the picture",
          "cubic Lab units" in body)
    check("03", "and a reader can scroll down to them",
          "overflow:auto" in body)
    turn_speed = re.search(r'"turn": \{"mode": "round", "speed": ([\d.]+)', body)
    tilt_speed = re.search(r'"tilt": \{"mode": "swing", "speed": ([\d.]+)', body)
    check("03", "the two directions kept their own speeds",
          bool(turn_speed and tilt_speed
               and float(turn_speed.group(1)) != float(tilt_speed.group(1))),
          f"turn {turn_speed.group(1) if turn_speed else '?'}, "
          f"tilt {tilt_speed.group(1) if tilt_speed else '?'}")

    # ---------------------------------------------------------------- 04
    # THE SMALLER PAPER SOLID, THE BIGGER ONE AS THE CAGE, and that order is
    # forced by the measurement rather than chosen for looks. The matte fits
    # 100.0% inside the glossy -- entirely, with nothing sticking out -- so
    # drawn the other way round the glossy surface is a closed lid over the
    # matte cage and the matte is not visible at all, at any angle. The page
    # was published that way, under a card promising you could "see exactly
    # where the glossy one pushes out through the matte one's cage", which
    # cannot happen when one contains the other.
    #
    # The window gives the FIRST paper opened the solid style and the second
    # the outline, so which is opened first is the whole of the fix.
    print("\n04 — a matte paper solid inside a glossy one's outline")
    fresh()
    w._load(MATTE)
    pump(2.0)
    w._load(GLOSSY)
    pump(2.5)
    spin(on=True, turn="swing", turn_speed=8, turn_sweep=90)
    p = page("04-two-papers.html")
    save_to(p)
    made.append(("04", p))
    body = p.read_text(encoding="utf-8")
    check("04", "both papers are in the picture",
          "Glossy-paper" in body and "Matte-paper" in body)
    # WHICH IS INSIDE WHICH IS THE WHOLE CARD, and it is not something to
    # assume from the names -- glossy is not always the bigger one, and on
    # these two files it is. Read it off the window rather than guess.
    said = w._readout_text().replace("\n", " ")
    print("           " + said[:190])
    # THE CARD NAMES A DIRECTION, so pin the direction. It was published the
    # wrong way round -- "a glossy paper inside a matte one's outline" when
    # the matte is the smaller of the two and fits entirely inside the
    # glossy. Names do not say which paper holds more; the window does.
    check("04", "the card has the two papers the right way round",
          # The window words this from whichever paper is named first, so the
          # sentence changed when the two were swapped. The FACT it pins --
          # which of them fits inside the other -- did not.
          "100.0% of the colour Matte-paper can print also fits inside "
          "Glossy-paper" in said,
          "the matte is the one that fits inside")
    # AND THE ONE THAT FITS INSIDE IS THE SOLID ONE. A shape drawn as a cage
    # inside a closed surface is a shape nobody can see, whatever the card
    # says about it.
    check("04", "the shape that fits inside is the one drawn solid",
          "Matte-paper" in body
          and "Glossy-paper (outline)" in body
          and "Matte-paper (outline)" not in body,
          "otherwise the inner shape is hidden by the outer one at every angle")
    # AND THE NUMBER ON THE CARD IS THE NUMBER THE WINDOW WORKED OUT.
    #
    # This was checked for the direction and not for the figure, so when
    # containment was corrected to measure against the real dented surface
    # instead of the convex hull around it, the card went on saying **76.4%**
    # while the window said 77.4% -- and the generator that exists to catch
    # exactly this reported every claim met. A percentage nobody checks is a
    # percentage that goes stale the first time the arithmetic improves.
    # The window words the two directions differently -- the first as "N% of
    # the colour X can print also fits inside Y", the second as the shorter
    # "N% of X fits inside Y". It is the second one the card quotes.
    said_share = re.search(r"([\d.]+)% of Glossy-paper fits inside Matte-paper",
                           said)
    card = pathlib.Path(HERE.parent / "docs" / "index.html").read_text(
        errors="replace")
    on_card = re.search(r"but only ([\d.]+)% of\s+the glossy fits inside the "
                        r"matte", card)
    check("04", "the figure on the index card is the one the window quotes",
          bool(said_share) and bool(on_card)
          and said_share.group(1) == on_card.group(1),
          f"page says {said_share.group(1) if said_share else '?'}%, "
          f"docs/index.html says {on_card.group(1) if on_card else '?'}%")
    check("04", "how one is drawn stays out of the tab",
          "(outline)" not in (re.search(r"<title>(.*?)</title>", body)
                              or re.match("", "")).group(1)
          if re.search(r"<title>(.*?)</title>", body) else False,
          (re.search(r"<title>(.*?)</title>", body) or ["", "?"])[1]
          if re.search(r"<title>(.*?)</title>", body) else "no title")

    # ---------------------------------------------------------------- 05
    print("\n05 — a chart in ink amounts, with a skin over what survives")
    fresh()
    w._open_chart_file(CHART)
    pump(2.0)
    # THE ORDER OF THESE TWO IS THE WHOLE PICTURE, and getting it wrong is
    # not visible until the patches are counted. A chart is judged against the
    # FIRST shape on screen (_chart_cloud), and it is PLACED through the first
    # ICC profile on screen (_profiles_on_screen). So the paper being asked
    # the question has to be opened first and the profile second: opened the
    # other way round the chart is judged against the very profile it was
    # placed through, everything lands inside it, and the picture that is
    # meant to show what a second paper cannot reach shows two lost patches
    # out of 480. That is exactly what the first run of this produced.
    w._load(MATTE)
    pump(2.5)
    w._load(PROFILE)
    pump(2.5)
    w._place_chart()
    pump(1.5)
    w._space.setCurrentIndex(w._space.findData("rgb"))
    pump(1.5)
    w._chart_skin.setCurrentIndex(w._chart_skin.findData("mesh"))
    pump(1.5)
    spin(on=True, turn="round", turn_speed=7, tilt="swing",
         tilt_speed=5, tilt_sweep=20)
    p = page("05-a-chart-in-ink-amounts.html")
    save_to(p)
    made.append(("05", p))
    body = p.read_text(encoding="utf-8")
    check("05", "the axes really are the printer's own controls",
          "Red" in body and "Green" in body and "Blue" in body)
    check("05", "the out-of-reach patches are picked out",
          "\\u2014 outside" in body)
    inside, outside = patch_counts(body)
    check("05", "and there are enough of them to be the point of the picture",
          outside > 50, f"{inside} within reach, {outside} beyond it")

    # ---------------------------------------------------------------- 06
    print("\n06 — the same chart and paper, in CIELAB")
    w._space.setCurrentIndex(w._space.findData("lab"))
    pump(2.5)
    p = page("06-the-same-chart-in-cielab.html")
    save_to(p)
    made.append(("06", p))
    body6 = p.read_text(encoding="utf-8")
    check("06", "it is drawn in CIELAB now", "a*" in body6 or "L*" in body6)
    # THE CLAIM THE PAIR EXISTS TO MAKE. The two pages are the same measurement
    # drawn two ways, so the counts must be identical -- the space is how a
    # thing is drawn, never what it is judged by. If these ever differ, the
    # judging has picked up the drawn space and the pair is a lie.
    check("06", "the counts are identical to the ink-amount view",
          patch_counts(body6) == (inside, outside),
          f"ink amounts {(inside, outside)}, CIELAB {patch_counts(body6)}")

    # THE CARD CLAIMS THE COUNTS ARE IDENTICAL IN BOTH VIEWS. That is the whole
    # point of the pair, so it is the one thing worth proving rather than
    # repeating: the space is how a thing is drawn, never what it is judged by.
    print(f"           what the window reads out: "
          f"{w._readout_text()[:120]!r}")

    # ---------------------------------------------------------------- 07
    print("\n07 — the same scene on a light page")
    w._set_appearance("light")
    pump(2.0)
    p = page("07-light-mode.html")
    save_to(p)
    made.append(("07", p))
    body = p.read_text(encoding="utf-8")
    light = "#efebe6" in body.lower()
    check("07", "the page really is on light paper", light)
    check("07", "and the controls are painted for light paper",
          '"paper": "#efebe6"' in body.lower())

    # ---------------------------------------------------------------- 08
    print("\n08 — the small one, without the viewer inside")
    # BACK TO DARK FIRST. The light page above leaves the window on light
    # paper, and this one is meant to be the plain dark scene again -- a run
    # that forgot it published a "same scene" card over a different-looking
    # page, which the contrast probe noticed before anybody else could.
    w._set_appearance("dark")
    pump(1.0)
    fresh()
    w._load(GLOSSY)
    pump(2.0)
    spin(on=True, turn="round", turn_speed=7)
    p = page("08-without-the-viewer.html")
    save_to(p, carry=False)
    made.append(("08", p))
    size = p.stat().st_size if p.exists() else 0
    biggest = max(pp.stat().st_size for _n, pp in made[:-1])
    check("08", "it is far smaller than the ones that carry the viewer",
          0 < size < 400_000,
          f"{size / 1024:.0f} kB against {biggest / 1024 / 1024:.1f} MB — "
          f"{biggest / size:.0f} times smaller")
    check("08", "and it is on dark paper again, as its card says",
          '"paper": "#111111"' in p.read_text(encoding="utf-8"))
    check("08", "because it fetches the viewer instead",
          "cdn.plot.ly" in p.read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- 09
    print("\n09 — two papers, a room each")
    fresh()
    w._load(GLOSSY)
    pump(2.0)
    w._load(MATTE)
    pump(2.5)
    w._side_by_side.setChecked(True)
    pump(3.0)
    spin(on=True, turn="swing", turn_speed=6, turn_sweep=70)
    p = page("09-a-room-each.html")
    save_to(p)
    made.append(("09", p))
    body = p.read_text(encoding="utf-8")
    rooms = scenes(body)
    check("09", "it really is two rooms and not one overlaid scene",
          len(rooms) == 2, f"{len(rooms)} scene(s): {list(rooms)}")
    check("09", "both are drawn in three dimensions",
          all("mesh3d" in k or "scatter3d" in k for k in rooms.values()),
          str(rooms))

    # ---------------------------------------------------------------- 10
    print("\n10 — one slice through both, at the same lightness")
    w._side_by_side.setChecked(False)
    pump(1.0)
    w._slice_on.setChecked(True)
    pump(3.0)
    p = page("10-a-slice-through-both.html")
    save_to(p)
    made.append(("10", p))
    body = p.read_text(encoding="utf-8")
    rooms = scenes(body)
    check("10", "it really is the flat cross-section, not the 3D shape",
          bool(rooms) and all(k == ["scatter"] for k in rooms.values()),
          str(rooms))
    # A FLAT CUT HAS NO CAMERA, so nothing about movement is built -- but it
    # does get the strip, because zoom, move and "put it back" mean exactly as
    # much here as on a shape. It used to get nothing, which left a reader on
    # a phone able to zoom in and never out: the library's own toolbar is the
    # only other way back, and that is hidden on a narrow screen.
    check("10", "is marked as having no camera, so no movement is built",
          '"flat": true' in body)
    check("10", "but can still be zoomed, moved and put back",
          "cqSpinControls" in body and '"zoom": true' in body
          and '"move": true' in body
          and 'button("home", "reset view"' in body)
    # ---------------------------------------------------------------- 12
    # THE FOURTH ARRANGEMENT, which no sample page made until now. The window
    # can show one scene, two rooms, one cut and TWO cuts, and the last was
    # the only one a visitor could not see. It is also the one with the most
    # to go wrong: the two panes are tied together, so a zoom that is applied
    # to them one after the other zooms the second one twice -- it is changed
    # once by the link and once again by the code, which by then is reading
    # the already-zoomed range. Two panes that disagree about scale are
    # exactly the lie a side-by-side comparison exists to prevent.
    print("\n12 — the same cut, a pane each")
    w._side_by_side.setChecked(True)
    pump(3.0)
    p = page("12-a-cut-each.html")
    save_to(p)
    made.append(("12", p))
    body = p.read_text(encoding="utf-8")
    rooms = scenes(body)
    check("12", "it really is two flat panes, not one",
          len(rooms) == 2 and all(k == ["scatter"] for k in rooms.values()),
          f"{len(rooms)}: {rooms}")
    check("12", "and they are tied together, so both always show the same "
          "patch of colour space", "cqLinkAxes" in body)
    check("12", "with the strip a flat page gets",
          "cqSpinControls" in body and '"flat": true' in body)
    w._side_by_side.setChecked(False)
    pump(1.0)
    w._slice_on.setChecked(False)
    pump(1.5)

    # ---------------------------------------------------------------- 11
    print("\n11 — a page that hands over everything")
    fresh()
    w._load(GLOSSY)
    pump(2.0)
    w._load(MATTE)
    pump(2.5)
    spin(on=True, turn="round", turn_speed=7, tilt="swing",
         tilt_speed=4, tilt_sweep=22)
    p = page("11-everything-handed-over.html")
    save_to(p, numbers=True, offer=EVERY_CONTROL)
    made.append(("11", p))
    body = p.read_text(encoding="utf-8")
    for wanted in ("speed_each", "grid", "labels", "key", "appearance",
                   "sweep", "agree"):
        check("11", f"the page was given the {wanted} control",
              f'"{wanted}": true' in body)
    check("11", "and it carries both sets of page colours, to switch between",
          '"palettes"' in body and "#efebe6" in body and "#111111" in body)

    # ---------------------------------------------------------------- 13
    # THE ONE VIEW THE SHOWCASE NEVER HAD, and the one that most needs
    # showing: not "here are two shapes" but "here is the part of this paper
    # the other one cannot reproduce", painted onto the shape itself.
    #
    # It is also the page that proves the rule about colour. This mesh is red
    # where a colour is out of reach and grey where it is not, so the colour
    # IS the measurement -- and the reader is deliberately NOT offered the
    # switch that would drain it to grey, because a greyed one would still
    # carry a name promising two things while showing one.
    # WHICH TWO PAPERS, and it is not a free choice. Painted against the
    # matte paper, 91.3% of the glossy one's surface comes out red -- a solid
    # red blob that demonstrates the two colours by showing almost none of
    # one of them, and reads as "something is broken" rather than as an
    # answer. The other way round it is 0.0%, because the matte fits entirely
    # inside the glossy, and the picture is a plain grey shape.
    #
    # The same paper measured again months later loses 54.1% -- roughly half
    # and half, which is the picture that actually shows what the two colours
    # mean. It is also the more useful question of the two: a paper drifts,
    # and "what can this batch no longer reproduce" is something a printer
    # asks about their own stock rather than about somebody else's.
    print("\n13 — what a paper can no longer reproduce, months later")
    fresh()
    w._load(GLOSSY)
    pump(2.0)
    w._load(LATER)
    pump(2.5)
    for i in range(w._compare.count()):
        got = w._compare.itemData(i)
        if got and got[0] == "space" and "months-later" in w._compare.itemText(i):
            w._compare.setCurrentIndex(i)
            w._on_compare_changed()
            break
    pump(2.0)
    w._show_lost.setChecked(True)
    pump(3.0)
    spin(on=True, turn="round", turn_speed=5)
    p = page("13-what-a-paper-can-no-longer-reach.html")
    save_to(p, numbers=True, offer=EVERY_CONTROL)
    made.append(("13", p))
    body = p.read_text(encoding="utf-8")
    check("13", "the shape really is painted by what is out of reach",
          "red is out of reach" in body)
    check("13", "and the key says what the OTHER colour means too",
          "grey is within it" in body,
          "naming one colour of a two-coloured shape invites the reader to "
          "take the other for background")
    # THE MARK THAT REFUSES THE GREY SWITCH. Written into the trace by the
    # Python and read by the page when it decides which controls to build.
    # Written compactly by the drawing library -- no spaces after the colons.
    # Looked for on its own rather than as a whole meta block: the same block
    # now also carries which points stand outside the other shape, so pinning
    # the exact object was pinning two unrelated things together.
    check("13", "it is marked as a shape whose colour is the answer",
          '"cq":"colour"' in body)
    check("13", "so the page still offers the other two shape controls",
          '"opacity": true' in body and '"wires": true' in body)
    # THE TWO FADES, AND THE MASK THEY NEED. One character per measured
    # point, saying which side of the question that point falls on -- the
    # page cannot work this out for itself, because it has no idea where one
    # gamut stops and another starts.
    check("13", "the reader can fade away where the two agree",
          'data-cq="agree-at"' in body)
    check("13", "and, the other way round, where they differ",
          'data-cq="differ-at"' in body)
    marks = re.findall(r'"stand":"([01]+)"', body)
    check("13", "and it carries what it needs to do it", bool(marks),
          f"{len(marks)} masks, {[len(m) for m in marks]} points")
    # THE MASK MUST BE THE SAME LENGTH AS THE COLOURS IT INDEXES, or the fade
    # lands on the wrong points and reads as a fault in the measurement.
    lens = [c.count("rgb") for c in re.findall(r'"vertexcolor":\[(.*?)\]', body)]
    check("13", "and it lines up with the colours it acts on",
          bool(marks) and all(len(m) in lens for m in marks),
          f"masks {[len(m) for m in marks]} against colours {lens[:3]}")
    # AND IT IS ACTUALLY A TWO-COLOURED PICTURE. The whole point of this page
    # is that a reader can tell the two apart, and a shape that is 91% one of
    # them demonstrates nothing. Read off the window rather than assumed.
    said = w._readout_text().replace("\n", " ")
    print("           " + said[:190])

    # ---------------------------------------------------------------- 14
    # A PAPER AGAINST A STANDARD SPACE, WITH EVERY CONTROL THE PAGE CAN CARRY.
    #
    # Every other showcase page compares two measurements. This one asks the
    # question most people actually arrive with -- "will the pictures people
    # send me survive on this paper?" -- against Adobe RGB (1998), which is
    # what a photographer editing for print is most likely to be working in.
    #
    # It is also the page that has to prove the shape controls really work,
    # and that is why it is saved with the OUTLINE IN ITS OWN COLOURS rather
    # than the plain grey every other page uses. Two things were reported on
    # page 11 and both are about exactly this: a surface could not be turned
    # to wires at all, and a cage saved grey has no colours for the colour
    # button to bring back. A page where the cage is coloured demonstrates
    # both controls doing something visible.
    print("\n14 — a paper against Adobe RGB, with every control")
    fresh()
    # `fresh()` closes what is open. It does NOT put the look controls back,
    # and the page before this one leaves "Show what the comparison cannot
    # print" switched on -- so this page came out drawing the red-and-grey
    # comparison painting instead of the paper, and the shape refused the
    # grey button because for that painting the colour IS the answer. Found
    # by reading the name of the surface the finished page actually holds.
    w._show_lost.setChecked(False)
    pump(0.5)
    w._load(GLOSSY)
    pump(2.5)
    picked = False
    for i in range(w._compare.count()):
        got = w._compare.itemData(i)
        if got and got[0] == "space" and w._compare.itemText(i).startswith(
                "Adobe RGB"):
            w._compare.setCurrentIndex(i)
            w._on_compare_changed()
            picked = True
            break
    check("14", "Adobe RGB (1998) is one of the built-in comparisons", picked)
    pump(2.5)
    # The paper solid and the space around it as a cage, which is the only way
    # to look at a printer sitting inside a larger space and still see it.
    w._style_mine.setCurrentIndex(0)
    w._style_second.setCurrentIndex(2)
    pump(1.0)
    at = w._outline_paint.findData("true")
    check("14", "the outline can be given the shapes' own colours", at >= 0)
    w._outline_paint.setCurrentIndex(at)
    pump(3.0)
    spin(on=True, turn="round", turn_speed=6, tilt="swing", tilt_speed=4,
         tilt_sweep=20)
    p = page("14-a-paper-against-adobe-rgb.html")
    save_to(p, numbers=True, offer=EVERY_CONTROL)
    made.append(("14", p))
    body = p.read_text(encoding="utf-8")
    for wanted in ("speed_each", "grid", "labels", "key", "appearance",
                   "sweep", "agree", "opacity", "wires", "grey"):
        check("14", f"the page was given the {wanted} control",
              f'"{wanted}": true' in body)
    # A COLOURED CAGE CARRIES MANY COLOURS. It used to be many TRACES, one
    # per band of colour, on the belief that a line takes one colour for the
    # whole of it -- and this check counted the traces. It is one trace now,
    # carrying a colour per point, which is the same picture drawn 296 times
    # more cheaply; counting traces would call that a regression. So the
    # question is asked of the colours, which is what the claim is about.
    colours = cage_colours(body)
    check("14", "the cage really is drawn in its own colours",
          len(colours) > 20,
          f"{len(colours)} colours along the cage; a plain grey one has 1")
    check("14", "and it is named once in the key",
          body.count("(outline)") >= 1)
    # AND IT REALLY IS THE PAPER, not the red-and-grey comparison painting
    # that the page before this one leaves switched on. Without this the leak
    # is invisible: the page builds, every other claim passes, and the shape
    # quietly refuses the grey button because its colour is the answer.
    check("14", "it draws the paper itself, not the comparison painting",
          "red is out of reach" not in body)
    said = w._readout_text().replace("\n", " ")
    print("           " + said[:190])

    # ---------------------------------------------------------- 15, 16, 17
    #
    # ONE DEVICE THROUGH TIME, which is the other question this application
    # answers and the one no gamut can. The profiles are generated rather than
    # committed: each is a 1257 kB copy of a 1257 kB profile differing in about
    # six thousand bytes, so four of them would be five megabytes of
    # near-duplicate binary for something that takes a second to make.
    print("\n15-17 — one printer, four profiles, five years")
    import tempfile as _tempfile
    profiles_dir = pathlib.Path(_tempfile.mkdtemp(prefix="timeline-demo-"))
    leftovers.append(profiles_dir)
    sys.path.insert(0, str(HERE))
    import importlib.util as _iu
    _spec = _iu.spec_from_file_location("mkprof", HERE / "make_demo_profiles.py")
    _mk = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(_mk)
    made_ok = _mk.main(profiles_dir) == 0
    check("15", "the demo run still makes its own point", made_ok,
          "the generator checks it is small by volume and large inside")
    run_files = sorted(profiles_dir.glob("printer-*.icc"))
    check("15", "four profiles were written", len(run_files) == 4)

    fresh()
    timeline = gamut_app.TimelineDialog(w, appearance=w._appearance)
    timeline.show()
    timeline.add(run_files)
    pump(3.0)

    import drift_series as _ds
    the_run = timeline._run
    check("15", "they were put in date order by themselves",
          the_run.ordered_by == "date", the_run.ordered_by)
    check("15", "and the run is clean enough to show somebody",
          not the_run.complaints, "; ".join(the_run.complaints) or "no complaints")
    # THE POINT, AS A NUMBER. A shape that barely changes and an inside that
    # plainly does is the whole reason this feature exists, so it is asserted
    # rather than left to the reader of the page.
    import icc_read as _icc
    sizes = [_icc.profile_gamut(p).volume for p in run_files]
    spread = (max(sizes) - min(sizes)) / max(sizes)
    check("15", "the gamut hardly changes across the whole run",
          spread < 0.03, f"{100 * spread:.2f}% by volume")
    check("15", "while the colours inside move plainly",
          the_run.total > 1.0, f"dE {the_run.total:.2f} altogether")

    def save_timeline(target: pathlib.Path) -> None:
        class Files:
            def __init__(self, *a, **k):
                pass

            def setAcceptMode(self, *a):
                pass

            def setDefaultSuffix(self, *a):
                pass

            def exec(self):
                return 1

            def selectedFiles(self):
                return [str(target)]

        was = w._file_dialog
        w._file_dialog = lambda *a, **k: Files()
        try:
            timeline._on_save()
            pump(1.0)
        finally:
            w._file_dialog = was

    p = page("15-one-printer-over-five-years.html")
    save_timeline(p)
    made.append(("15", p))
    body = p.read_text(encoding="utf-8")
    check("15", "both lines are in the page",
          "how far altogether" in body and "how far each time" in body)
    check("15", "the axis is spaced by real dates",
          '"type":"date"' in body or '"type": "date"' in body)
    # THE WORDS TRAVEL WITH THE PICTURE. A graph outlives the window that
    # explained it, and somebody opening this next year must not read a rising
    # line as proof their printer is failing.
    check("15", "the verdict is saved with the graph",
          "drifted steadily" in body or "Nothing has moved" in body)
    check("15", "and so is the caveat that stops it being over-read",
          "not how far the device drifted" in body)
    check("15", "the key explains what the numbers mean",
          "nobody can see" in body and "anybody can see" in body)
    # WHICH COLOURS MOVED, IN THE SAVED FILE. The page is what gets sent to a
    # colleague or a paper supplier, and the sentences are what they will
    # quote. Asked for by a paper manufacturer; the objection raised with it
    # -- that somebody has to draw an arbitrary line around "what is a red" --
    # is answered on the page rather than in a docstring, so these check for
    # the caveat as hard as for the report.
    check("15", "the family report is saved with the graph",
          'class="families"' in body)
    check("15", "every family line says how many colours it stands on",
          body.count("patches)") >= 5,
          f"{body.count('patches)')} lines carry a count")
    check("15", "and the greys are reported as greys, never given a hue",
          "greys:" in body)
    check("15", "the arbitrary line is admitted on the page itself",
          "not one that exists in nature" in body)
    check("15", "and the page says how many colours sat on that line",
          "could honestly have been counted either side" in body)

    # ---------------------------------------------------------------- 20
    # THE SAME RUN, SAID IN SENTENCES. Pages 15 and 18 draw a line and a
    # cloud; both need a reader to interpret them. This is the form somebody
    # can paste into an email, which is what a paper manufacturer asked for
    # -- and it is the only page that exercises the timeline's OWN cloud
    # save, notes and all, rather than the main window's.
    print("\n20 — which colours moved, in sentences")
    for i in range(timeline._picture_of.count()):
        if timeline._picture_of.itemData(i) == ("whole", 0):
            timeline._picture_of.setCurrentIndex(i)
            break
    else:
        raise AssertionError("the whole-run comparison is not on offer")
    timeline._draw()
    pump(3.0)
    pair = timeline._chosen_pair()
    check("20", "a pair is chosen, so this saves the cloud and not the graph",
          pair is not None)
    # SPLIT INTO FAMILIES, so the saved page carries the filter as well as the
    # sentences. The legend becomes seven switches: hide everything but the
    # blues and the page shows where in the blues the printer moved. It is the
    # drawing library's own behaviour, so it works offline, on a phone, with
    # nothing installed.
    timeline._by_family.setChecked(True)
    timeline._draw()
    pump(3.0)
    figure = timeline._cloud_figure()
    check("20", "the cloud really is split into its colour families",
          figure is not None and len(figure.data) >= 6,
          f"{0 if figure is None else len(figure.data)} groups")
    check("20", "and every group is named with the number of colours in it",
          all(" — " in t.name for t in figure.data),
          ", ".join(t.name for t in figure.data))
    p = page("20-which-colours-moved.html")
    save_timeline(p)
    made.append(("20", p))
    body = p.read_text(encoding="utf-8")
    check("20", "the report travels with the picture",
          "which colour families moved" in body)
    # ONE LINE PER FAMILY, EACH CARRYING ITS COUNT. A family of eleven and a
    # family of a hundred and thirty-seven read alike without that number,
    # and this page is the one people will quote from.
    counted = body.count("patches)") + body.count("patch)")
    check("20", "every family line carries the number it stands on",
          counted >= 6, f"{counted} lines carry a count")
    check("20", "the greys are reported as greys and given no hue",
          "greys:" in body)
    check("20", "the arbitrary line is admitted on the page itself",
          "not one that exists in nature" in body)
    check("20", "and it says how many colours sat close enough to go either way",
          "could honestly have been counted either side" in body)
    # WHAT IT DOES NOT CLAIM, which matters more here than on the other pages:
    # sentences are quoted, and a quoted sentence loses its caveat unless the
    # caveat is in the file with it.
    check("20", "the caveat that stops it being over-read is saved too",
          "not how far the device drifted" in body)

    check("20", "the families are switchable in the saved page too",
          '"name":"reds' in body or '"name": "reds' in body)

    timeline._by_family.setChecked(False)
    # PUT THE WINDOW BACK, and this is not tidiness. The pages after this one
    # share this timeline, and they save WHATEVER IS SHOWING -- deliberately,
    # so a saved file can never disagree with the screen it came from. Leaving
    # the chooser on a cloud made 16, 17 and 19 quietly save clouds too, and
    # five of their claims failed at once. The page that changes shared state
    # is the page that has to hand it back.
    for i in range(timeline._picture_of.count()):
        if timeline._picture_of.itemData(i) is None:
            timeline._picture_of.setCurrentIndex(i)
            break
    else:
        raise AssertionError("the graph is no longer on offer")
    timeline._draw()
    pump(2.0)
    check("20", "and the window is handed back showing the graph",
          timeline._chosen_pair() is None)

    print("\n16 — the same run with one profile taken out")
    timeline._list.setCurrentRow(2)
    timeline._on_remove()
    pump(2.0)
    check("16", "the run shrank to three", len(timeline._run.usable) == 3)
    p = page("16-the-same-run-with-a-gap.html")
    save_timeline(p)
    made.append(("16", p))
    body = p.read_text(encoding="utf-8")
    check("16", "it still draws both lines",
          "how far altogether" in body and "how far each time" in body)
    check("16", "and still carries the caveat",
          "not how far the device drifted" in body)

    print("\n17 — a run that moved all at once rather than steadily")
    jumpy = pathlib.Path(_tempfile.mkdtemp(prefix="timeline-jump-"))
    leftovers.append(jumpy)
    _mk.RUN = [("step-2019", (2019, 1, 5, 9, 0, 0), 0.0000),
               ("step-2020", (2020, 1, 5, 9, 0, 0), 0.0002),
               ("step-2021", (2021, 1, 5, 9, 0, 0), 0.0004),
               ("step-2022", (2022, 1, 5, 9, 0, 0), 0.0060),
               ("step-2023", (2023, 1, 5, 9, 0, 0), 0.0062)]
    _mk.main(jumpy)
    timeline._on_clear()
    timeline.add(sorted(jumpy.glob("step-*.icc")))
    pump(3.0)
    check("17", "this one is NOT called steady", not timeline._run.steady)
    p = page("17-a-printer-that-moved-all-at-once.html")
    save_timeline(p)
    made.append(("17", p))
    body = p.read_text(encoding="utf-8")
    # THE DIFFERENCE THAT MATTERS. Even steps mean it will keep creeping; one
    # big step means something HAPPENED, on a date somebody can go and look up.
    check("17", "the page says the movement was at one point, not gradual",
          "one point rather than gradually" in body)
    check("17", "and names the dates it happened between",
          "2021-01-05" in body and "2022-01-05" in body)

    print("\n19 — a printer that wandered off and came back")
    # BASTI'S QUESTION, AND THE CASE THIS FEATURE WAS MOST LIKELY TO LIE
    # ABOUT: "what if a profile drifts in one direction for two years and then
    # back to the other, matching the initial one again -- would this be
    # visible?" The picture always showed it; the words did not, and read only
    # the two ends. This page is the case itself, so the answer is something
    # somebody can look at rather than take on trust.
    wandered = pathlib.Path(_tempfile.mkdtemp(prefix="timeline-back-"))
    leftovers.append(wandered)
    _mk.RUN = [("year-2019", (2019, 3, 1, 9, 0, 0), 0.0000),
               ("year-2020", (2020, 3, 1, 9, 0, 0), 0.0030),
               ("year-2021", (2021, 3, 1, 9, 0, 0), 0.0060),
               ("year-2022", (2022, 3, 1, 9, 0, 0), 0.0030),
               ("year-2023", (2023, 3, 1, 9, 0, 0), 0.0006)]
    _mk.main(wandered)
    timeline._on_clear()
    timeline.add(sorted(wandered.glob("year-*.icc")))
    pump(3.0)
    back = timeline._run
    check("19", "the run is recognised as one that came back", back.came_back)
    # THE TWO NUMBERS THAT MAKE THE POINT, asserted rather than described: it
    # ended near where it began, and it was a long way from there in between.
    check("19", "it ends near where it started",
          back.total < 1.0, f"dE {back.total:.2f} first to last")
    check("19", "having been plainly visible distance away in between",
          back.furthest.worst > 3.0,
          f"dE {back.furthest.worst:.2f} at its furthest")
    p = page("19-it-wandered-off-and-came-back.html")
    save_timeline(p)
    made.append(("19", p))
    body = p.read_text(encoding="utf-8")
    # THE FAULT THIS PAGE EXISTS TO PROVE IS FIXED. Reading only the ends, the
    # verdict used to call this "Nothing has moved that anybody could see".
    check("19", "the verdict does NOT say nothing has moved",
          "Nothing has moved" not in body)
    check("19", "it says it went away and came back",
          "went away and came back" in body)
    check("19", "and names the year it was furthest",
          "2021" in body)
    check("19", "the picture marks the furthest point too",
          "furthest from the first" in body)
    timeline.close()

    # ---------------------------------------------------------------- 21
    # THE ONE THAT GETS SENT TO SOMEBODY, and the argument for the whole
    # feature. Two profiles of one printer five years apart enclose almost
    # exactly the same amount of colour -- 0.4% by volume, which is to say the
    # same size by any measure anybody would use. Judged on volume alone, and
    # that is how most tools judge, this printer has not changed.
    #
    # Inside those two identical shells the colours have plainly moved. That
    # is the whole point, and the page has to land it before a reader has
    # scrolled: the SHAPE says almost nothing and the INSIDE says plenty.
    print("\n21 — the shape says nothing, the inside says plenty")
    fresh()
    first_profile = profiles_dir / "printer-2019.icc"
    last_profile = profiles_dir / "printer-2024.icc"
    check("21", "both profiles of the run are there",
          first_profile.is_file() and last_profile.is_file())
    w._load(first_profile)
    pump(5.0)
    w._load(last_profile)
    pump(7.0)
    check("21", "both are open as shapes", len(w._slots) == 2,
          f"{len(w._slots)} open")

    # THE CLAIM THE PAGE IS BUILT ON, checked rather than asserted: the two
    # shells really are the same size. If a future demo generator changed that
    # this page would be making an argument its own data does not support.
    sizes = [g.volume for _p, g, _m in w._slots if g is not None]
    check("21", "the two shapes really are all but identical in size",
          len(sizes) == 2 and abs(sizes[0] - sizes[1]) / max(sizes) < 0.02,
          f"{sizes[0]:,.0f} against {sizes[1]:,.0f} — "
          f"{100 * abs(sizes[0] - sizes[1]) / max(sizes):.2f}% apart")

    w._drift_draw.setChecked(True)
    pump(4.0)
    w._drift_split.setChecked(True)
    pump(4.0)
    got = w._drift_for_figure()
    check("21", "the cloud is drawn inside the shapes", got is not None)
    check("21", "and it is split into its colour families", bool(got[4]))
    # AND THE INSIDE REALLY HAS MOVED, which is the other half of the claim.
    import numpy as _np
    worst = float(_np.max(got[1]))
    check("21", "the colours inside have plainly moved", worst > 3.0,
          f"worst ΔE {worst:.2f} — plainly visible, in shapes the same size")

    p = page("21-the-shape-says-nothing.html")
    # WITH THE NUMBERS, which is not the default. The picture alone makes half
    # the argument; the sentences under it are the half somebody can quote.
    save_to(p, numbers=True)
    made.append(("21", p))
    body = p.read_text(encoding="utf-8")
    check("21", "the two shapes are in the saved page",
          "printer-2019" in body and "printer-2024" in body)
    check("21", "so are the seven colour families",
          all(f'"{name} \\u2014 ' in body or f'"{name} — ' in body
              for name in ("reds", "yellows", "greens", "cyans", "blues",
                           "magentas")))
    check("21", "the families sit under a heading of their own, "
                "not mixed in with the shapes",
          "by colour family" in body)
    check("21", "the reader gets a threshold of their own",
          'data-cq="cut"' in body)
    check("21", "the sentences travel with the picture",
          "which colour families moved" in body)
    check("21", "including the arbitrary line they rest on",
          "not one that exists in nature" in body)
    check("21", "and what the numbers do NOT mean",
          "not how far the printer moved" in body
          or "not how far the device drifted" in body)
    w._drift_split.setChecked(False)
    w._drift_draw.setChecked(False)

    # ---------------------------------------------------------------- 18
    # THE OTHER PICTURE OF THE SAME FACT, and the reason it needs a page of
    # its own. Pages 15-17 answer WHEN a device moved and how fast. They
    # cannot answer WHERE in colour it moved, and those want opposite
    # actions: a device that has drifted evenly is a calibration job, one
    # that has moved only in the deep blues is a different problem. The two
    # profiles here are the first and last of the run on page 15, so a reader
    # can hold the line and the cloud against each other and see that they
    # are two views of one thing rather than two results.
    print("\n18 — the same drift, drawn where it happens")
    fresh()
    first_profile = profiles_dir / "printer-2019.icc"
    last_profile = profiles_dir / "printer-2024.icc"
    check("18", "the run's first and last profiles are both there",
          first_profile.is_file() and last_profile.is_file())
    w._load(first_profile)
    pump(4.0)
    w._load(last_profile)
    pump(6.0)
    check("18", "both profiles are open as shapes", len(w._slots) == 2,
          f"{len(w._slots)} open")
    check("18", "the window offers the drift readout for a pair of profiles",
          w._drift_box.isVisible())
    w._drift_draw.setChecked(True)
    pump(4.0)
    drift = w._drift_for_figure()
    check("18", "and the cloud is really built rather than skipped",
          drift is not None and len(drift[1]) > 0,
          "none" if drift is None else f"{len(drift[1])} colours")
    # THE POINT OF THE PAIRING, as a number: the same 0.42%-by-volume run that
    # page 15 draws as a rising line is drawn here as a cloud that is hot
    # somewhere and cold elsewhere. If the drift were even, this page would be
    # making a claim it could not support.
    import numpy as _np
    spread = float(_np.max(drift[1]) - _np.min(drift[1])) if drift else 0.0
    check("18", "the movement is not the same everywhere in colour",
          spread > 1.0, f"dE {_np.min(drift[1]):.2f} to {_np.max(drift[1]):.2f} "
                        f"across the cube")
    p = page("18-where-the-drift-happened.html")
    save_to(p)
    made.append(("18", p))
    body = p.read_text(encoding="utf-8")
    check("18", "the cloud reached the saved page",
          "how far it moved" in body)
    # LOOKED FOR AS THE PAGE REALLY SPELLS IT. The key's text goes through
    # JSON, which writes an em-dash as —, so searching the page for the
    # dash itself finds nothing and reports a missing key on a page that has
    # one. That mistake has now been made twice in this project; hence the
    # escaped form here and the note beside it.
    check("18", "with the key that says what the colours mean",
          "1 \\u2014 invisible" in body and "5+ \\u2014 obvious" in body)
    # A FIXED CEILING IS WHAT MAKES TWO OF THESE COMPARABLE. A scale stretched
    # to whatever is in front of it would make a nearly identical pair look as
    # alarming as a badly drifted one, because the reddest point is always red.
    check("18", "the colour scale is clamped rather than stretched to fit",
          '"cmax": 5' in body or '"cmax":5' in body)

    # ASKED OF THE SCENE, NOT OF THE PAGE TEXT. Searching the whole file for
    # "Adobe RGB" reports a leak on a clean page: the bundled viewer's own
    # source comments mention it twice, and they travel with every export.
    drawn_here = drawn_names(body)
    check("18", "and nothing else crept into the picture",
          all("printer-" in n or "how far" in n for n in drawn_here),
          ", ".join(sorted(drawn_here)))

    # ------------------------------------------------------------ all of them
    print("\nevery page")
    for name, path in made:
        body = path.read_text(encoding="utf-8")
        # HOW MANY SEPARATE THINGS THE BROWSER IS ASKED TO DRAW, which is what
        # a phone feels rather than the file size. A cage used to be cut into
        # one trace per band of colour, so page 14 shipped with 357 of them
        # and page 18 with 642; a colour per point does the same picture in
        # one. This ceiling is here so that never quietly comes back: no
        # arrangement in this application needs more than a handful.
        drawn = traces_drawn(body)
        # SIXTEEN, NOT TWELVE, and the reason is not that a page grew. The
        # ceiling exists to catch a cage being cut into one trace per band of
        # colour -- 357 and 642 traces on two pages once. Splitting a drift
        # cloud into its seven colour families is a deliberate seven, and a
        # page that also holds two shapes and their outlines lands at
        # thirteen. Raising a guard to admit a real feature is right;
        # raising it to admit a regression would not be, so the number stays
        # far below anything that could hide one.
        check(name, "the browser is not handed hundreds of separate traces",
              drawn <= 16, f"{drawn} traces across every room on the page")
    for name, path in made:
        body = path.read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", body)
        check(name, "has a name in the tab that is not just a file name",
              bool(title and title.group(1).strip()
                   and title.group(1) != " — ChromIQ Gamut Viewer"),
              title.group(1) if title else "none")
        if "cqSpinControls" not in body:
            continue          # the strip was deliberately left off this one
        check(name, "paints its controls rather than inheriting a colour",
              '"ink":' in body and '"paper":' in body)
        check(name, "offers the reader a way back to the opening view",
              '"reset"' in body and 'button("home", "reset view"' in body)
        check(name, "was given the controls that were chosen for it",
              '"show":' in body)
        # THE POINT OF THIS ROUND. A finger can only turn a 3D shape -- the
        # viewer's camera reads one touch and reports it as a left-button
        # drag, and left-button IS turn. Zooming needs the middle button and
        # moving needs the right one, neither of which a phone has. So every
        # page that can be turned must also carry a way to zoom and to move,
        # or it is a page that cannot be read on a phone.
        # Looking for the SOURCE of the buttons, not for rendered markup:
        # the strip is built by script when the page opens, so the file holds
        # the code that makes the buttons and never the buttons themselves.
        check(name, "can be zoomed without a mouse wheel",
              '"zoom": true' in body and 'button("in", "+"' in body)
        check(name, "can be moved without a right-hand mouse button",
              '"move": true' in body and 'button("left", "&larr;"' in body
              and 'button("down", "&darr;"' in body)
        check(name, "and understands a pinch, which is what a phone tries",
              "gd._cqGestures" in body and "touchAction" in body)
        # THE CONTROLS ARE GROUPED. Twenty of them in one flat list is not a
        # panel, it is an inventory -- and this is the check that the panel
        # is still built in named groups rather than having quietly
        # collapsed back into a column.
        check(name, "sorts its controls into named groups",
              all(f'section("{g}"' in body for g in
                  ("how it moves", "where you look from", "each shape",
                   "what is drawn", "the page itself")))
        # AND EACH SHAPE CAN BE DRESSED ON ITS OWN. The reason this matters
        # on every page rather than only the crowded ones: the person who
        # opens it did not choose which shapes are on it and cannot know in
        # advance which one they will want out of the way.
        check(name, "lets the reader fade any one shape on its own",
              '"opacity": true' in body
              and 'button("shape-fainter-" + n' in body)
        check(name, "and take the colour out of it",
              '"grey": true' in body and 'button("shape-grey-" + n' in body)
        # THE NUMBER BETWEEN A MINUS AND A PLUS MUST NOT MOVE THEM. "100%" is
        # wider than "50%", and without both of these the plus walks out
        # from under the finger pressing it. Reported from a real page.
        check(name, "and the reading between the two buttons cannot move "
              "them", ".cq-num{display:inline-block;min-width:40px;" in body
              and "font-variant-numeric:tabular-nums" in body)
        # A CLOSED PANEL IS CLOSED. This is the rule whose absence put 259px
        # of controls over 78px of picture on every page for two releases,
        # and it has to outrank every other rule that sets the panel's own
        # display -- so the check is that nothing after it sets one.
        check(name, "and its panel is really hidden when it is closed",
              ".cq-spin-panel[hidden]{display:none}" in body
              and ".cq-spin-panel{display" not in
              body[body.index(".cq-spin-panel[hidden]{display:none}"):])

    # THE DEMO PROFILES GO AWAY AGAIN, and this is not tidiness for its own
    # sake. Each run made three folders of generated profiles -- about 12 MB
    # -- and left every one of them behind; four runs in an afternoon had put
    # 88 MB in the temporary folder, on top of the scenes the window itself
    # writes. This project has already had one 27 GB version of that fault
    # (#100), and the lesson from it was that a thing which writes megabytes
    # per run has to remove them itself rather than hope somebody notices.
    #
    # Removed here rather than in a finally, deliberately: when the run FAILS
    # the profiles are the evidence, and deleting them takes away the only
    # copy of what the failing page was built from.
    import shutil as _shutil

    print("\n" + "=" * 68)
    if failures:
        print(f"{len(failures)} claim(s) not met:")
        for f in failures:
            print(f"  - {f}")
        print(f"\nthe generated profiles are kept for you to look at:")
        for folder in leftovers:
            print(f"  {folder}")
        return 1
    for folder in leftovers:
        _shutil.rmtree(folder, ignore_errors=True)
    # AND THE WINDOW IS CLOSED PROPERLY, so it clears its own scene folder.
    # The window removes its ``gamutview-*`` folder in closeEvent (#100);
    # walking out of main() never fires that, so each run of this script left
    # one behind. They are swept by the next run of the real application, but
    # a generator anybody may run twenty times before a release should not
    # rely on that.
    w.close()
    pump(0.4)
    print(f"{len(made)} pages written to {out_dir}, every claim met.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
