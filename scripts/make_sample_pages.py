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
page -- "saved with the movement running", "222 inside, 18 on the edge", "80 kB
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
PROFILE = DEMO / "Glossy-paper.icc"
CHART = DEMO / "verification-chart-480.ti1"

failures: list[str] = []

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
                numbers: bool = False) -> None:
        from PyQt6.QtWidgets import QDialog

        class Options:
            def __init__(self, *a, **k):
                pass

            def exec(self):
                return QDialog.DialogCode.Accepted.value

            def choices(self):
                return {"carry_viewer": carry, "numbers": numbers}

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
        """Back to nothing open, so one scene cannot leak into the next."""
        w._on_clear()
        pump(0.4)

    made: list[tuple[str, pathlib.Path]] = []

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
    print("\n04 — a glossy paper inside a matte one's outline")
    fresh()
    w._load(GLOSSY)
    pump(2.0)
    w._load(MATTE)
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
          "100.0% of Matte-paper fits inside Glossy-paper" in said,
          "the matte is the one that fits inside")
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

    # ------------------------------------------------------------ all of them
    print("\nevery page")
    for name, path in made:
        body = path.read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", body)
        check(name, "has a name in the tab that is not just a file name",
              bool(title and title.group(1).strip()
                   and title.group(1) != " — ChromIQ Gamut Viewer"),
              title.group(1) if title else "none")
        check(name, "paints its controls rather than inheriting a colour",
              '"ink":' in body and '"paper":' in body)
        check(name, "offers the reader a way back to the opening view",
              'data-cq="home"' in body)

    print("\n" + "=" * 68)
    if failures:
        print(f"{len(failures)} claim(s) not met:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"{len(made)} pages written to {out_dir}, every claim met.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
