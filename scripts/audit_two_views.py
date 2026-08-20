"""A page holding both views offers each one only what it can honour.

    ../gv-venv/bin/python scripts/audit_two_views.py

WHY THIS EXISTS. Asked for from the window: a switch in the saved page between
the shells and the sliced view, and — the half that matters — "the other
controls would then have to update accordingly so the user can manipulate each
view in a way that makes sense for it".

"Which controls make sense here" is exactly where an inconsistency hides. A
control offered where it cannot act is a control that lies, and this project
has already fixed that fault twice in the window itself: the split tick that
stayed lit while the destination colouring was in charge, and four colourings
that could be chosen while the split made them do nothing.

WHAT MUST BE TRUE, each with its failure direction:

  the shells offer the turning controls   they are what a camera is for; a
                                          page that withholds them has lost
                                          something the reader had;
  the cut offers none of them             a cross-section has no camera at
                                          all, so play, speed, faster and
                                          slower cannot act — offering them
                                          is the lie;
  both offer what belongs to both         zoom, "back to the start" and the
                                          panel are about the picture, not
                                          about which kind it is;
  switching back restores                 a switch that only works once is a
                                          trap, and the reader is left in the
                                          view they did not choose;
  there is exactly one strip              rebuilding without removing leaves
                                          two, and the second is stale.

MEASURED IN BOTH ENGINES, because the strip is rebuilt by script and the two
engines have disagreed before about when a layout is readable.

THE PAGE IS BUILT HERE, in a temporary directory, from a blob of measurements
rather than a file on disk: the two-view writer is not yet reachable from the
export dialog, so there is no saved page to point at. When it is, this should
be pointed at a real one.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

#: What only a camera can honour. A flat cut has none.
TURNING = {"play", "speed", "faster", "slower", "lr", "ud", "sweep"}
#: What belongs to any picture at all.
EITHER = {"home", "in", "out", "more"}

#: Where the cut says it is sitting, and where the page was saved at.
WHERE = """(function () {
  var s = window.cqSettings || {}, c = s.cuts || null;
  var says = document.querySelector('[data-cq="cut-at"]');
  return JSON.stringify({
    saved: c ? Math.round(c.levels[c.at || 0]) : null,
    says: says ? says.textContent.replace(/[^0-9-]/g, "") : null});
})()"""

STRIP = """(function () {
  var out = [];
  document.querySelectorAll('.cq-spin-bar [data-cq], .cq-spin-panel [data-cq]')
    .forEach(function (b) {
      if (b.getBoundingClientRect().width > 0)
        out.push(b.getAttribute('data-cq'));
    });
  return {controls: out, bars: document.querySelectorAll('.cq-spin-bar').length,
          views: document.querySelectorAll('.cq-view').length,
          shown: [].slice.call(document.querySelectorAll('.cq-view'))
                   .map(function (v) { return v.hidden ? 0 : 1; })};
})()"""


def a_shape():
    """The shape these pages are drawn from."""
    import numpy as np
    import ti3gamut
    from gamutview import build_gamut

    # THE REAL MEASUREMENT WHERE THERE IS ONE. A made-up ball gave this page
    # a lightness range so narrow that the height it was saved at and the
    # bottom of the range rounded to the same number -- so the check could not
    # tell them apart, and a mutation that genuinely broke the saved height
    # (proved on the demo paper: L* 50 became L* 8) slipped past it.
    demo = HERE.parent / "demo" / "Glossy-paper.ti3"
    if demo.is_file():
        measured = ti3gamut.read_measurement(demo)
        return build_gamut(measured.lab, input_space="lab")

    rng = np.random.default_rng(9)
    q = rng.normal(size=(700, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    q *= rng.uniform(0.5, 1, size=(700, 1)) ** (1 / 3)
    lab = q * np.array([38, 52, 50])
    lab[:, 0] = np.clip(lab[:, 0] * 0.6 + 50, 4, 96)
    # SAYING WHAT THE NUMBERS ARE. `build_gamut` reads its input as XYZ unless
    # told otherwise, so handing it Lab silently builds a shape in the wrong
    # space -- corners at L* -71,327, no rings, and `slice_levels` returning
    # None, which is what made this page's cut unslidable and looked like a
    # fault in the writer.
    return build_gamut(lab, input_space="lab")


def a_page(where: pathlib.Path):
    """One page carrying the shells and a cut, written by the real writer."""
    import ti3gamut

    shape = a_shape()

    scene = ti3gamut.build_figure([("a paper", shape)], "Measured gamut")

    # THE CUT IS GIVEN SOMETHING TO SLIDE THROUGH, which was the gap this
    # page was written with and which docs/DESIGN-two-views-in-one-page.md
    # recorded: a reader could switch to the cross-section and then not move
    # it. The recipe is the one the two-pane cut page already uses -- the
    # levels worked out once, the figure built `slidable` over their shared
    # extent, and the levels carried into the page's settings, where the
    # control strip looks for `settings.cuts`.
    at = 50.0
    cuts = ti3gamut.slice_levels([("a paper", shape)], include=at)
    if cuts is not None:
        cuts["title"] = ""
        cuts["at"] = min(range(len(cuts["levels"])),
                         key=lambda i: abs(cuts["levels"][i] - at))
    cut = ti3gamut.build_slice_figure(
        [("a paper", shape)], at, "A cut at L* 50",
        extent=(cuts["extent"] if cuts else None),
        slidable=cuts is not None)
    out = where / "both.html"
    ti3gamut.write_two_views_html(
        [("The shells", scene), ("A cut through it", cut)], out,
        spin={"on": False, "cuts": cuts}, controls=True,
        offer={"appearance": True, "camera": True})
    return out


def save_through_the_window(target: str, ticked: bool) -> int:
    """Build the window, tick the box, press Save. Run as its OWN process.

    A QtWebEngine window and playwright in one process do not survive each
    other: with this inlined, the whole check died before it printed a single
    line and still exited 0, which is the worst possible way for a check to
    fail. The same pairing crashed the unit-test gate outright. So the window
    half is a subprocess and the browser half never meets it.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication, QDialog

    import gamut_app
    import prefs

    prefs.use_a_scratch_store()
    # THE WINDOW TELLS YOU IT SAVED, and that sentence is a modal box. Two
    # drivers hung for ten minutes each on it before this line was written.
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

    app = QApplication.instance() or QApplication(["audit_two_views"])
    window = gamut_app.GamutApp()
    window.resize(1400, 900)
    window.show()

    def settle(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    demo = sorted((HERE.parent / "demo").glob("*.ti3"))
    if not demo:
        return 2
    window._load(demo[0])
    settle(4000)
    # TWO SHAPES, because a cross-section of one shape is a different picture
    # and the switch is about comparing.
    for i in range(window._compare.count()):
        data = window._compare.itemData(i)
        if data and data[0] == "space" and data[1] == "sRGB":
            window._compare.setCurrentIndex(i)
            window._on_compare_changed()
            break
    settle(5000)

    # THE REAL TICK, read through the real dialog, so what is measured is the
    # control rather than a dictionary somebody typed.
    dialog = gamut_app.WebPageDialog(window)
    tick = getattr(dialog, "_both_views", None)
    if tick is None:
        return 3
    tick.setChecked(ticked)
    chosen = dialog.choices()
    dialog.deleteLater()

    class Options:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted.value

        def choices(self):
            return chosen

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
            return [target]

    window._file_dialog = lambda *a, **k: Files()
    gamut_app.WebPageDialog = Options
    window._on_save()
    settle(4000)
    window.close()
    app.processEvents()
    return 0 if pathlib.Path(target).exists() else 4


def from_the_window(where: pathlib.Path, ticked: bool) -> "pathlib.Path | None":
    """Save a page by pressing the window's own button, with the tick set.

    WHY THIS EXISTS BESIDE `a_page`. Everything else here hands the writer its
    arguments directly, which proves the writer works and NOTHING about
    whether a reader can ask for it. Measured the day this was added: the word
    `both_views` did not occur anywhere in `scripts/` or in any test — the
    tick in the export dialog was built, plumbed and never once driven. That
    is exactly the fault `make_sample_pages` warns about in its own first
    paragraph, "a control that no longer reaches the export", and it had grown
    around this one while nobody was looking.

    Returns None when the window cannot be driven here, so a machine without
    a display skips rather than fails.
    """
    import subprocess

    out = where / f"from-the-window-{'ticked' if ticked else 'plain'}.html"
    done = subprocess.run(
        [sys.executable, str(pathlib.Path(__file__).resolve()),
         "--save-through-the-window", str(out), "1" if ticked else "0"],
        capture_output=True, timeout=600)
    if done.returncode != 0 or not out.exists():
        return None
    return out


def main() -> int:
    prove = "--prove" in sys.argv
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed, so this check is skipped.\n"
              "  pip install playwright && python -m playwright install "
              "webkit chromium")
        return 0

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        # FIRST, THE PATH A READER TAKES: the tick in the export dialog, and
        # the file that comes out of pressing Save. Everything after this
        # hands the writer its arguments and cannot see whether the control
        # reaches it at all.
        print("  pressing Save through the real export dialog…")
        # THE MUTATION: ask for the tick ON and set it OFF in the window, so
        # the control is made not to decide the file. Everything downstream is
        # untouched, which is the point — this is the fault "a control that no
        # longer reaches the export" wears.
        ticked = from_the_window(pathlib.Path(tmp), not prove)
        plain = from_the_window(pathlib.Path(tmp), False)
        if prove and ticked is not None and plain is not None:
            if ticked.read_bytes() != plain.read_bytes():
                print("  THE MUTATION DID NOT LAND — asking for the tick off "
                      "produced a different\n  file from asking for it off, "
                      "so this run tested nothing.")
                return 2
        if ticked is None or plain is None:
            print("  the window could not be driven here, so the reader's own "
                  "path is skipped.")
        else:
            with_it = ticked.read_text(encoding="utf-8").count('data-cq="view"')
            without = plain.read_text(encoding="utf-8").count('data-cq="view"')
            print(f"  tick on:  {ticked.stat().st_size // 1024} kB, "
                  f"{with_it} view-switch button(s)")
            print(f"  tick off: {plain.stat().st_size // 1024} kB, "
                  f"{without} view-switch button(s)")
            if not with_it:
                problems.append(
                    "the export dialog's “Carry a cross-section too” was "
                    "ticked and the saved page has no switch on it — the "
                    "control does not reach the export")
            # AND THE OTHER DIRECTION, which is what makes the first mean
            # anything: untick it and the switch must be gone. A page that
            # always carries both views would satisfy the rule above while
            # the tick did nothing whatever.
            if without:
                problems.append(
                    f"the tick was OFF and the saved page still carries "
                    f"{without} view-switch button(s) — the control is not "
                    f"what decides it")

        page = a_page(pathlib.Path(tmp))
        print(f"  a page with both views: {page.stat().st_size // 1024} kB")

        with sync_playwright() as play:
            try:
                engines = {n: getattr(play, n).launch()
                           for n in ("chromium", "webkit")}
            except Exception as why:                     # noqa: BLE001
                print(f"  no browser, so this check is skipped: {why}")
                return 0

            for name, browser in engines.items():
                tab = browser.new_page(viewport={"width": 1100, "height": 900})
                tab.goto(page.resolve().as_uri())
                tab.wait_for_timeout(7000)

                seen = {}
                for step, label in ((0, "the shells"), (1, "the cut"),
                                    (0, "the shells again")):
                    tab.locator('button[data-cq="view"]').nth(step).click()
                    tab.wait_for_timeout(2500)
                    got = tab.evaluate(STRIP)
                    seen[label] = got
                    offered = set(got["controls"])
                    print(f"  {name:9s} {label:18s} "
                          f"{' '.join(sorted(offered)) or '(nothing)'}")
                    if got["bars"] != 1:
                        problems.append(
                            f"{name}, {label}: {got['bars']} strips on screen "
                            f"— a rebuilt strip must replace the old one")
                    if got["views"] != 2:
                        problems.append(f"{name}: {got['views']} views, wanted 2")
                    missing = EITHER - offered
                    if missing:
                        problems.append(
                            f"{name}, {label}: does not offer "
                            f"{' '.join(sorted(missing))}, which any picture "
                            f"can honour")

                shells = set(seen["the shells"]["controls"])
                cut = set(seen["the cut"]["controls"])
                again = set(seen["the shells again"]["controls"])

                if not (TURNING & shells):
                    problems.append(
                        f"{name}: the shells offer none of the turning "
                        f"controls, which is what a camera is for")
                # WHERE THE CUT OPENS IS CHECKED ELSEWHERE, and it had to
                # be. A rule for it here could not be made to fail even with
                # the fault deliberately restored: this page's invented shape
                # has a lightness range narrow enough that the saved height
                # and the bottom of the range round to the same number. It
                # lives in audit_the_cut_opens_where_it_was_saved.py, on the
                # demo paper, where the two are eight and fifty.

                # AND THE CUT MUST OFFER THE ONE CONTROL THAT IS ITS OWN.
                # Switching to a cross-section that cannot be moved is the
                # half of "manipulate each view in a way that makes sense for
                # it" that this page was asked for.
                if not ({"cut", "cut-at", "cut-up", "cut-down"} & cut):
                    problems.append(
                        f"{name}: the cut offers nothing to move it with — a "
                        f"reader can switch to the cross-section and is then "
                        f"stuck at whichever lightness it was saved at")
                # AND THE MIRROR OF IT, which this audit did not ask and
                # should have. Giving the cut its levels put the lightness
                # controls in the strip for BOTH views -- the shells offered
                # cut, cut-at, cut-up and cut-down, none of which a
                # three-dimensional scene can honour. That is the same lie
                # the turning controls would be on a flat cut, in the other
                # direction, and it was introduced by the very change that
                # cured the cut's missing slider.
                loose = {"cut", "cut-at", "cut-up", "cut-down"} & shells
                if loose:
                    problems.append(
                        f"{name}: the shells offer {' '.join(sorted(loose))} "
                        f"— a scene has no cross-section to move, so these "
                        f"cannot act there")
                stranded = TURNING & cut
                if stranded:
                    problems.append(
                        f"{name}: the cut offers {' '.join(sorted(stranded))} "
                        f"— a cross-section has no camera, so they cannot act")
                if shells != again:
                    problems.append(
                        f"{name}: switching back did not restore the controls "
                        f"({' '.join(sorted(shells ^ again))} differ)")
                if seen["the cut"]["shown"] != [0, 1]:
                    problems.append(
                        f"{name}: pressing the second button did not show the "
                        f"second view ({seen['the cut']['shown']})")
                tab.close()
            for browser in engines.values():
                browser.close()

    print()
    if prove:
        if any("does not reach the export" in p for p in problems):
            print("  With the tick made not to decide the file, the audit "
                  "said so.\n  The check can see.")
            return 0
        print("  THE TICK WAS MADE NOT TO DECIDE THE FILE and the audit "
              "still said nothing.\n  This check is blind.")
        return 1
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: each view offers what it can honour and nothing it cannot, "
          "the switch\n  goes both ways, and there is one strip throughout.")
    return 0


if __name__ == "__main__":
    # THE WINDOW HALF, RUN AS ITS OWN PROCESS. See save_through_the_window:
    # a QtWebEngine window and playwright do not survive each other, and
    # inlining it killed the whole check before it printed a line while still
    # exiting 0.
    if len(sys.argv) > 3 and sys.argv[1] == "--save-through-the-window":
        raise SystemExit(save_through_the_window(sys.argv[2],
                                                 sys.argv[3] == "1"))
    raise SystemExit(main())
