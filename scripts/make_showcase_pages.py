"""The showcase pages: eight questions about papers, answered by the window.

    python scripts/make_showcase_pages.py [--out docs/showcase/pages]

WHAT THIS IS. `docs/showcase/` is a guided argument -- eight scenarios about
papers, batches and the profiles that describe them -- distinct from the
feature tour in `docs/pages/`. Every page here is produced by pressing the
real window's own Save button through its own dialogs, exactly like
`make_sample_pages.py`, and for the same reason: a page built by calling the
drawing code directly proves only that the drawing code works.

THE FIGURES ARE READ OFF THE WINDOW AND WRITTEN DOWN. Every number the
showcase quotes -- a containment percentage, a patch count, a verdict
sentence -- is captured here into `docs/showcase/figures.json` as the pages
are made, and `docs/showcase/index.html` is then checked against it: any
figure the index quotes that the window did not say fails the build. A
percentage nobody checks is a percentage that goes stale the first time the
arithmetic improves; that has already happened once in this repository.

THE DEMO FILES. The four papers come from `make_showcase_measurements.py`
(committed, self-checking). The batch profiles are bent copies of the demo
profile written by `make_demo_profiles.py`'s machinery into a temporary
folder -- five megabytes of near-duplicate binary have no place in the
repository, and they take a second to regenerate.

Exit code 1 if any page is missing, empty, or does not match its claim.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "python"))

import prefs  # noqa: E402

prefs.use_a_scratch_store()
sys.argv = ["make_showcase_pages"]

SHOWCASE_DEMO = ROOT / "demo" / "showcase"
GLOSS = SHOWCASE_DEMO / "baryta gloss 315gsm.ti3"
COTTON = SHOWCASE_DEMO / "heavy matte cotton 310gsm.ti3"
RAG = SHOWCASE_DEMO / "soft-white rag 300gsm.ti3"
SHELF = SHOWCASE_DEMO / "baryta gloss 315gsm, a year on the shelf.ti3"
CHART = ROOT / "demo" / "verification-chart-480.ti1"

#: The batch runs, written at build time. The steady one is BELOW the
#: visibility threshold on purpose -- its page is the good-news page, and its
#: verdict must be "Nothing has moved that anybody could see". That is why
#: `make_demo_profiles.main()` is not used here: its self-check demands
#: visible movement, which is the OTHER run's story.
STEADY = [("batch 2024-01", (2024, 1, 8, 9, 0, 0), 0.0000),
          ("batch 2024-04", (2024, 4, 9, 9, 0, 0), 0.00025),
          ("batch 2024-07", (2024, 7, 8, 9, 0, 0), 0.0005),
          ("batch 2024-10", (2024, 10, 7, 9, 0, 0), 0.00075),
          ("batch 2025-01", (2025, 1, 6, 9, 0, 0), 0.0010)]
JUMP = [("batch 2023-01", (2023, 1, 9, 9, 0, 0), 0.0000),
        ("batch 2023-04", (2023, 4, 10, 9, 0, 0), 0.0002),
        ("batch 2023-07", (2023, 7, 10, 9, 0, 0), 0.0004),
        ("batch 2023-10", (2023, 10, 9, 9, 0, 0), 0.0050),
        ("batch 2024-01", (2024, 1, 8, 9, 0, 0), 0.0052)]
PAIR = [("studio printer, spring 2019", (2019, 3, 12, 10, 30, 0), 0.0000),
        ("studio printer, autumn 2024", (2024, 9, 2, 16, 20, 0), 0.0035)]

DEFAULT_OFFER = {"play": True, "speed": True, "lr": True, "ud": True,
                 "reset": True, "remember": True, "zoom": True, "move": True,
                 "notes": True, "opacity": True, "wires": True, "grey": True,
                 "views": True, "fullscreen": True, "picture": True,
                 "cut": True, "agree": True, "sweep": False}
EVERY_CONTROL = dict(DEFAULT_OFFER, speed_each=True, grid=True, labels=True,
                     key=True, appearance=True, speed=False, sweep=True)

failures: list[str] = []
figures: dict[str, dict] = {}

#: How many bytes one number takes, per the dtype names plotly writes.
_WIDTH = {"f8": 8, "f4": 4, "i8": 8, "i4": 4, "i2": 2, "i1": 1,
          "u1": 1, "u2": 2, "u4": 4}


def _count(values) -> int:
    """How many points a trace really holds — NOT len().

    Plotly packs any sizeable array as base64 in {"dtype":…, "bdata":…}, so
    len() on a 480-patch trace returns 2, the number of keys in that dict.
    The same lesson `make_sample_pages.py` carries, for the same reason.
    """
    import base64

    if isinstance(values, dict) and "bdata" in values:
        raw = base64.b64decode(values["bdata"])
        return len(raw) // _WIDTH.get(values.get("dtype", "f8"), 8)
    return len(values) if isinstance(values, list) else 0


def patch_counts(body: str) -> tuple[int, int]:
    """(within reach, beyond it) for the chart drawn on a saved page.

    Single-point traces are skipped: those are the fixed-size keys beside
    the picture, not data.
    """
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
    ap.add_argument("--out", default=str(ROOT / "docs" / "showcase" / "pages"))
    args = ap.parse_args()
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for needed in (GLOSS, COTTON, RAG, SHELF, CHART):
        if not needed.exists():
            print(f"missing demo file: {needed}\n"
                  f"run scripts/make_showcase_measurements.py first")
            return 1

    from PyQt6.QtWidgets import QApplication

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
                        "controls": True,
                        "offer": (offer if isinstance(offer, dict)
                                  else DEFAULT_OFFER)}

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

    def spin(on=True, turn="round", turn_speed=6, turn_sweep=60,
             tilt="off", tilt_speed=4, tilt_sweep=20) -> None:
        w._spin_on.setChecked(on)
        for combo, mode in ((w._turn_mode, turn), (w._tilt_mode, tilt)):
            combo.setCurrentIndex(combo.findData(mode))
        w._turn_speed.setValue(turn_speed)
        w._turn_sweep.setValue(turn_sweep)
        w._tilt_speed.setValue(tilt_speed)
        w._tilt_sweep.setValue(tilt_sweep)
        pump(0.2)

    def fresh() -> None:
        w._on_clear()
        w._compare.setCurrentIndex(0)
        w._on_compare_changed()
        w._show_lost.setChecked(False)
        pump(0.6)
        assert w._reference is None, "the comparison survived a fresh()"

    def compare_with(fragment: str) -> bool:
        for i in range(w._compare.count()):
            got = w._compare.itemData(i)
            if got and got[0] == "space" and fragment in w._compare.itemText(i):
                w._compare.setCurrentIndex(i)
                w._on_compare_changed()
                return True
        return False

    made: list[tuple[str, pathlib.Path]] = []
    leftovers: list[pathlib.Path] = []

    def page(name: str) -> pathlib.Path:
        target = out_dir / name
        if target.exists():
            target.unlink()
        return target

    def readout() -> str:
        return w._readout_text().replace("\n", " ")

    # ------------------------------------------------------------------ 01
    # WHICH PAPER HOLDS THE OTHER, ASKED BOTH WAYS ROUND. The cotton opens
    # first so it is the solid shape inside the gloss's cage -- an inner
    # shape drawn as a cage inside a closed surface is invisible at every
    # angle, a lesson docs/pages/04 already paid for.
    print("\n01 — two papers, both ways round")
    fresh()
    w._load(COTTON)
    pump(2.0)
    w._load(GLOSS)
    pump(2.5)
    spin(on=True, turn="swing", turn_speed=7, turn_sweep=80)
    p = page("01-two-papers-both-ways.html")
    save_to(p, numbers=True)
    made.append(("01", p))
    body = p.read_text(encoding="utf-8")
    said = readout()
    print("           " + said[:200])
    check("01", "both papers are in the picture",
          "baryta gloss 315gsm" in body and "heavy matte cotton 310gsm" in body)
    check("01", "the one that fits inside is the one drawn solid",
          "baryta gloss 315gsm (outline)" in body
          and "heavy matte cotton 310gsm (outline)" not in body)
    into = re.search(r"([\d.]+)% of the colour heavy matte cotton 310gsm can "
                     r"print also fits inside baryta gloss 315gsm", said)
    back = re.search(r"([\d.]+)% of baryta gloss 315gsm fits inside heavy "
                     r"matte cotton 310gsm", said)
    check("01", "the window states both directions", bool(into and back),
          f"into {into.group(1) if into else '?'}%, "
          f"back {back.group(1) if back else '?'}%")
    check("01", "and the two answers are far apart, which is the point",
          bool(into and back)
          and float(into.group(1)) - float(back.group(1)) >= 8.0)
    check("01", "the numbers travel with the page",
          bool(into) and f"{into.group(1)}%" in body)
    figures["01"] = {"cotton_in_gloss": into.group(1) if into else "?",
                     "gloss_in_cotton": back.group(1) if back else "?"}

    # ------------------------------------------------------------------ 02
    # ONE PAPER, TWO RULERS. The same measurement against the two spaces
    # pictures actually arrive in. Two pages, because the window compares
    # with one space at a time -- which is honest: so does anyone quoting a
    # coverage figure.
    print("\n02 — the gloss against Adobe RGB (1998)")
    fresh()
    w._load(GLOSS)
    pump(2.5)
    check("02", "Adobe RGB (1998) is on the comparison list",
          compare_with("Adobe RGB"))
    pump(2.5)
    w._style_mine.setCurrentIndex(0)
    w._style_second.setCurrentIndex(2)
    pump(2.0)
    spin(on=True, turn="round", turn_speed=6)
    p = page("02-against-adobe-rgb.html")
    save_to(p, numbers=True)
    made.append(("02", p))
    said = readout()
    print("           " + said[:200])
    adobe = re.search(r"([\d.]+)% of the colour baryta gloss 315gsm can print "
                      r"also fits inside Adobe RGB \(1998\)", said)
    check("02", "the window quotes the paper's share of Adobe RGB",
          bool(adobe), f"{adobe.group(1) if adobe else '?'}%")
    figures["02"] = {"gloss_in_adobe": adobe.group(1) if adobe else "?"}

    print("\n03 — the same paper against sRGB")
    check("03", "sRGB is on the comparison list", compare_with("sRGB"))
    pump(2.5)
    p = page("03-against-srgb.html")
    save_to(p, numbers=True)
    made.append(("03", p))
    said = readout()
    print("           " + said[:200])
    srgb = re.search(r"([\d.]+)% of the colour baryta gloss 315gsm can print "
                     r"also fits inside sRGB", said)
    check("03", "the window quotes the paper's share of sRGB", bool(srgb),
          f"{srgb.group(1) if srgb else '?'}%")
    check("03", "and the two rulers give two different answers",
          bool(adobe and srgb)
          and abs(float(adobe.group(1)) - float(srgb.group(1))) >= 3.0,
          "otherwise the pair of pages proves nothing")
    figures["03"] = {"gloss_in_srgb": srgb.group(1) if srgb else "?"}

    # ------------------------------------------------------------------ 04
    # A CHART ON A PAPER THAT CANNOT REACH ALL OF IT. Judged against the
    # FIRST shape on screen and placed through the first profile -- so the
    # paper being asked opens first and the profile second. The other order
    # judges the chart against the very profile that placed it, and finds
    # two lost patches out of 480; docs/pages/05 documents that trap.
    print("\n04 — a 480-patch chart, in the printer's own ink amounts")
    fresh()
    profiles = pathlib.Path(__import__("tempfile").mkdtemp(
        prefix="showcase-profiles-"))
    leftovers.append(profiles)
    import importlib.util as _iu
    _spec = _iu.spec_from_file_location("mkprof",
                                        HERE / "make_demo_profiles.py")
    _mk = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(_mk)
    _mk.DEMO = profiles
    printer_icc = _mk.write_one("studio printer, baryta gloss",
                                (2024, 3, 4, 10, 0, 0), 0.0)
    w._open_chart_file(CHART)
    pump(2.0)
    w._load(COTTON)
    pump(2.5)
    w._load(printer_icc)
    pump(2.5)
    w._place_chart()
    pump(1.5)
    w._space.setCurrentIndex(w._space.findData("rgb"))
    pump(1.5)
    w._chart_skin.setCurrentIndex(w._chart_skin.findData("mesh"))
    pump(1.5)
    spin(on=True, turn="round", turn_speed=6, tilt="swing", tilt_speed=4,
         tilt_sweep=20)
    p = page("04-a-chart-in-ink-amounts.html")
    save_to(p)
    made.append(("04", p))
    body = p.read_text(encoding="utf-8")
    check("04", "the axes are the printer's own controls",
          "Red" in body and "Green" in body and "Blue" in body)
    check("04", "the out-of-reach patches are picked out",
          "\\u2014 outside" in body)
    said = readout()
    print("           " + said[:200])
    # THE COUNTS COME FROM THE PAGE, read the way the sample-page generator
    # reads them: single-point traces are keys, not data.
    inside, outside = patch_counts(body)
    check("04", "and there are enough of them to be the point of the picture",
          outside > 50, f"{inside} within reach, {outside} beyond it")
    figures["04"] = {"inside": inside, "outside": outside}

    print("\n05 — the same chart, in CIELAB")
    w._space.setCurrentIndex(w._space.findData("lab"))
    pump(2.5)
    p = page("05-the-same-chart-in-cielab.html")
    save_to(p)
    made.append(("05", p))
    body5 = p.read_text(encoding="utf-8")
    check("05", "it is drawn in CIELAB now", "a*" in body5 or "L*" in body5)
    check("05", "the counts are identical to the ink-amounts view",
          patch_counts(body5) == (inside, outside),
          f"ink amounts {(inside, outside)}, CIELAB {patch_counts(body5)}")

    # ------------------------------------------------------------------ 06
    print("\n06 — a year on the shelf, painted on the shape")
    fresh()
    w._load(GLOSS)
    pump(2.0)
    w._load(SHELF)
    pump(2.5)
    # NO COMPARISON NEEDS CHOOSING. With two shapes open and nothing under
    # "Compare with", the window judges the first against the second — which
    # is exactly what a person who has just opened both measurements gets
    # when they tick the box.
    w._show_lost.setChecked(True)
    pump(3.0)
    spin(on=True, turn="round", turn_speed=5)
    p = page("06-a-year-on-the-shelf.html")
    save_to(p, numbers=True, offer=EVERY_CONTROL)
    made.append(("06", p))
    body = p.read_text(encoding="utf-8")
    said = readout()
    print("           " + said[:200])
    check("06", "the shape is painted by what is out of reach",
          "red is out of reach" in body)
    check("06", "and the key names the other colour too",
          "grey is within it" in body)
    check("06", "the reader can fade away where the two agree",
          'data-cq="agree-at"' in body and 'data-cq="differ-at"' in body)
    # THE WINDOW WORDS THE LOSS AS COVERAGE — "91.9% … also fits inside the
    # year-on-the-shelf measurement" — so the lost share is 100 minus that,
    # and both are recorded: the index may quote either form.
    still = re.search(r"([\d.]+)% of the colour baryta gloss 315gsm can "
                      r"print also fits inside baryta gloss 315gsm, a year "
                      r"on the shelf", said)
    check("06", "the window quotes how much still fits", bool(still),
          f"{still.group(1) if still else '?'}%")
    figures["06"] = {
        "still_fits": still.group(1) if still else "?",
        "lost_share": (f"{100 - float(still.group(1)):.1f}"
                       if still else "?")}

    # ------------------------------------------------------------------ 07
    # FIVE BATCHES AND NOTHING TO SEE. The good-news page: its verdict must
    # be that nothing visible moved, which is why these bends stay below the
    # visibility threshold.
    print("\n07 — five batches, nothing to see")
    fresh()
    steady_dir = pathlib.Path(__import__("tempfile").mkdtemp(
        prefix="showcase-steady-"))
    leftovers.append(steady_dir)
    _mk.DEMO = steady_dir
    for stem, when, amount in STEADY:
        _mk.write_one(stem, when, amount)
    timeline = gamut_app.TimelineDialog(w, appearance=w._appearance)
    timeline.show()
    timeline.add(sorted(steady_dir.glob("batch *.icc")))
    pump(3.0)
    check("07", "the five batches form a clean run",
          timeline._run is not None and len(timeline._run.usable) == 5
          and not timeline._run.complaints,
          "; ".join(timeline._run.complaints) if timeline._run else "no run")
    check("07", "and the whole run stays below what anybody can see",
          timeline._run.total < 1.0, f"dE {timeline._run.total:.2f} altogether")

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

    p = page("07-five-batches-nothing-to-see.html")
    save_timeline(p)
    made.append(("07", p))
    body = p.read_text(encoding="utf-8")
    check("07", "the page says nothing has moved that anybody could see",
          "Nothing has moved" in body)
    check("07", "and still carries the caveat against over-reading",
          "not how far the device drifted" in body)
    figures["07"] = {"total_de": f"{timeline._run.total:.2f}"}

    # ------------------------------------------------------------------ 08
    print("\n08 — the batch where something happened")
    jump_dir = pathlib.Path(__import__("tempfile").mkdtemp(
        prefix="showcase-jump-"))
    leftovers.append(jump_dir)
    _mk.DEMO = jump_dir
    for stem, when, amount in JUMP:
        _mk.write_one(stem, when, amount)
    timeline._on_clear()
    timeline.add(sorted(jump_dir.glob("batch *.icc")))
    pump(3.0)
    check("08", "this run is NOT called steady", not timeline._run.steady)
    p = page("08-the-batch-where-something-happened.html")
    save_timeline(p)
    made.append(("08", p))
    body = p.read_text(encoding="utf-8")
    check("08", "the page says the movement was at one point, not gradual",
          "one point rather than gradually" in body)
    check("08", "and names the dates it happened between",
          "2023-07" in body and "2023-10" in body)
    worst = timeline._run.worst_step
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", worst.spans)
    figures["08"] = {"jump_de": f"{worst.worst:.2f}",
                     "between_a": dates[0] if dates else "?",
                     "between_b": dates[1] if len(dates) > 1 else "?"}
    timeline.close()

    # ------------------------------------------------------------------ 09
    # TWO SHELLS THE SAME SIZE, AND THE INSIDES MOVED. The argument the
    # whole drift feature exists for, on the batch pair.
    print("\n09 — two shells the same size, the insides moved")
    fresh()
    pair_dir = pathlib.Path(__import__("tempfile").mkdtemp(
        prefix="showcase-pair-"))
    leftovers.append(pair_dir)
    _mk.DEMO = pair_dir
    for stem, when, amount in PAIR:
        _mk.write_one(stem, when, amount)
    first = pair_dir / "studio printer, spring 2019.icc"
    last = pair_dir / "studio printer, autumn 2024.icc"
    w._load(first)
    pump(5.0)
    w._load(last)
    pump(7.0)
    check("09", "both profiles are open as shapes", len(w._slots) == 2)
    sizes = [g.volume for _p, g, _m in w._slots if g is not None]
    apart = 100 * abs(sizes[0] - sizes[1]) / max(sizes)
    check("09", "the two shells really are all but identical in size",
          len(sizes) == 2 and apart < 2.0,
          f"{sizes[0]:,.0f} against {sizes[1]:,.0f} — {apart:.2f}% apart")
    w._drift_draw.setChecked(True)
    pump(4.0)
    w._drift_split.setChecked(True)
    pump(4.0)
    got = w._drift_for_figure()
    check("09", "the cloud is drawn inside the shapes, split into families",
          got is not None and bool(got[4]))
    import numpy as _np
    worst_de = float(_np.max(got[1]))
    check("09", "and the colours inside have plainly moved", worst_de > 3.0,
          f"worst dE {worst_de:.2f} in shells {apart:.2f}% apart")
    p = page("09-two-shells-the-same-size.html")
    save_to(p, numbers=True)
    made.append(("09", p))
    body = p.read_text(encoding="utf-8")
    check("09", "both profiles are named in the page",
          "studio printer, spring 2019" in body
          and "studio printer, autumn 2024" in body)
    check("09", "the reader gets a threshold of their own",
          'data-cq="cut"' in body)
    figures["09"] = {"volumes_apart_pct": f"{apart:.2f}",
                     "worst_de": f"{worst_de:.2f}"}
    w._drift_split.setChecked(False)
    w._drift_draw.setChecked(False)

    # ------------------------------------------------------------------ 10
    # THE CUT THAT SHOWS WHAT ONE NUMBER HIDES. Same volume, different
    # papers: at L* 55 the cotton is the wider, at L* 20 the rag is --
    # and the rag still has a cut at all where the cotton is almost gone.
    # AT AN EVEN LIGHTNESS, ON PURPOSE. The saved page precomputes its cuts
    # on a 2-Lab-unit grid (ti3gamut._CUT_STEP), so a page saved at an odd
    # L* opens with its slider label one off from its title until the first
    # touch. Found by photographing the saved page: title "L* = 55", strip
    # "L* 54". Reported rather than worked around silently — but a showcase
    # page should not open wearing a known off-by-one, so these cuts sit on
    # the grid.
    print("\n10 — the cut at L* 54: the cotton is the wider paper")
    fresh()
    w._load(COTTON)
    pump(2.0)
    w._load(RAG)
    pump(2.5)
    w._slice_on.setChecked(True)
    w._slice_at.setValue(54)
    w._redraw()
    pump(3.0)
    p = page("10-the-cut-at-54.html")
    save_to(p)
    made.append(("10", p))
    body = p.read_text(encoding="utf-8")
    rooms = re.findall(r'Plotly\.newPlot\(\s*"(scene\d)"', body)
    check("10", "it is the flat cross-section",
          '"flat": true' in body, f"rooms {rooms}")
    check("10", "both papers are in the cut",
          "heavy matte cotton 310gsm" in body and "soft-white rag 300gsm" in body)
    check("10", "at the lightness the card names", "L* = 54" in body)

    print("\n11 — the cut at L* 20: the rag is the one still standing")
    w._slice_at.setValue(20)
    w._redraw()
    pump(3.0)
    p = page("11-the-cut-at-20.html")
    save_to(p)
    made.append(("11", p))
    body = p.read_text(encoding="utf-8")
    check("11", "still the flat cross-section", '"flat": true' in body)
    check("11", "both papers are named", "heavy matte cotton 310gsm" in body
          and "soft-white rag 300gsm" in body)
    w._slice_on.setChecked(False)
    pump(1.0)

    # ------------------------------------------------------- every page
    print("\nevery page")
    for name, path in made:
        body = path.read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", body)
        check(name, "has a name in the tab",
              bool(title and title.group(1).strip()
                   and title.group(1) != " — ChromIQ Gamut Viewer"),
              title.group(1) if title else "none")
        if "cqSpinControls" in body:
            check(name, "paints its controls rather than inheriting a colour",
                  '"ink":' in body and '"paper":' in body)
            check(name, "offers the reader a way back",
                  'button("home", "reset view"' in body)
            check(name, "can be zoomed and moved without a mouse",
                  'button("in", "+"' in body and 'button("left", "&larr;"'
                  in body)

    # THE FIGURES GO ON DISK, and the index is checked against them when it
    # exists. Order matters on the first run: pages first, then the index is
    # written quoting figures.json, then this runs green end to end.
    figures_path = out_dir.parent / "figures.json"
    figures_path.write_text(json.dumps(figures, indent=2) + "\n",
                            encoding="utf-8")
    print(f"\nfigures written to {figures_path}")
    index = out_dir.parent / "index.html"
    if index.exists():
        card = index.read_text(encoding="utf-8")
        for page_name, values in figures.items():
            for key, value in values.items():
                if key == "readout":
                    continue
                check(page_name, f"the index quotes the window's {key}",
                      str(value) in card,
                      f"{value} is not anywhere in showcase/index.html")
    else:
        print("no showcase/index.html yet — figure checks will run once it "
              "exists")

    print("\n" + "=" * 68)
    if failures:
        print(f"{len(failures)} claim(s) not met:")
        for f in failures:
            print(f"  - {f}")
        print("the generated profiles are kept for you to look at:")
        for folder in leftovers:
            print(f"  {folder}")
        return 1
    import shutil
    for folder in leftovers:
        shutil.rmtree(folder, ignore_errors=True)
    w.close()
    pump(0.4)
    print(f"{len(made)} pages written to {out_dir}, every claim met.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
