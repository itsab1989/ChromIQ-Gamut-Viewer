"""The README's window pictures, made by driving the real window.

    python scripts/make_screenshots.py            # all of them
    python scripts/make_screenshots.py 02 08 19   # just these

WHY THIS EXISTS. Twenty-odd pictures in the README were made by throwaway
scripts that lived outside the repository. That is the same failure the four in
`make_doc_shots.py` were rescued from, only twenty times over: remaking one
depended on somebody still having a file that was never committed, and once
that file was gone the picture could not be reproduced by anybody -- not from
a clean checkout, not at all.

It showed. Correcting the containment test moved figures that appear in these
pictures, and the answer to "which of them are now wrong?" was "we cannot
remake them to find out". Five percentages and four patch counts in the prose
around them turned out to have been stale for two releases.

WHAT IT DOES NOT COVER. The moving pictures (the g, c and n sets) are made by
their own scripts, and the four in `make_doc_shots.py` stay there. This is the
still window shots, which are the ones with no home at all.

HOW A PICTURE IS DESCRIBED. One function per shot, registered in SHOTS by the
file name it writes. Each is handed a fresh window with nothing loaded, sets it
up through the same widgets a person would use, and returns nothing -- the
grab is taken for it. Adding a picture is adding a function and a line.

EVERY SHOT IS CHECKED BEFORE IT IS WRITTEN. A picture of an empty scene, or of
a control that did not take, looks fine at a glance in a terminal and wrong on
the front page for a year. Each one says what must be true of it -- that a
shape is drawn, that the readout mentions the comparison, that some patches
came out red -- and a shot that cannot say so is reported and not saved.
"""
from __future__ import annotations

import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
_ASKED = [a for a in sys.argv[1:] if not a.startswith("-")]
sys.argv = ["make_screenshots"]

OUT = HERE.parent / "docs" / "screenshots"
DEMO = HERE.parent / "demo"
GLOSSY = DEMO / "Glossy-paper.ti3"
MATTE = DEMO / "Matte-paper.ti3"
LATER = DEMO / "Glossy-paper-months-later.ti3"
PROFILE = DEMO / "Glossy-paper.icc"
CHART = DEMO / "verification-chart-480.ti1"

#: The window size every one of these is taken at. It is the size the existing
#: pictures were made at, and keeping it means a remade picture drops into the
#: README at the same width instead of resizing every layout around it.
WIDE, TALL = 1500, 950

#: The ink-amount pictures are a little wider and shorter, as they were.
INK = (1560, 940)

failures: list[str] = []
_app = None


def pump(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        _app.processEvents()
        time.sleep(0.005)


def compare_with(window, kind: str, name=None) -> None:
    """Set Compare with, the way the combo box actually stores its entries.

    Its data is a (kind, name) pair -- ("space", "sRGB"), ("icc", None) -- and
    setting the index is not enough on its own: the handler that rebuilds the
    comparison only runs on a real activation, so it is called here. Getting
    that wrong once published a picture whose caption named sRGB and whose
    scene had no comparison in it at all.
    """
    for i in range(window._compare.count()):
        got = window._compare.itemData(i)
        if got and got[0] == kind and (name is None or got[1] == name):
            window._compare.setCurrentIndex(i)
            window._on_compare_changed()
            pump(3.0)
            return
    raise SystemExit(f"no Compare-with entry for {kind} {name!r}")


def pick(combo, data) -> None:
    at = combo.findData(data)
    if at < 0:
        raise SystemExit(f"no {data!r} in {combo.objectName() or combo}")
    combo.setCurrentIndex(at)


def readout(window) -> str:
    return window._readout_text().replace("\n", " ")


def drawn(window) -> int:
    """How many shapes are on screen, as the window itself counts them."""
    return len(window._slots) + (1 if window._reference is not None else 0)


# --------------------------------------------------------------- the pictures

def one_chart(w):
    """01 — a single measured chart, which is where everybody starts."""
    w._load(GLOSSY)
    pump(3.5)
    assert drawn(w) == 1, "the chart did not load"
    assert "cubic Lab units" in readout(w), "no volume was reported"


def vs_srgb(w):
    """02 — the same paper against sRGB, with coverage both ways round."""
    w._load(GLOSSY)
    pump(3.5)
    compare_with(w, "space", "sRGB")
    said = readout(w)
    assert "sRGB" in said, "the readout does not mention the comparison"
    assert "fits inside" in said, "no coverage figure was reported"


def where_lost(w):
    """03 — and where that colour is lost, rather than how much of it."""
    w._load(GLOSSY)
    pump(3.5)
    compare_with(w, "space", "sRGB")
    w._show_lost.setChecked(True)
    pump(3.0)
    assert w._show_lost.isChecked(), "the switch did not take"


def drift(w):
    """05 — the same paper measured again months later."""
    if not LATER.exists():
        raise SystemExit(f"{LATER} is missing")
    w._load(GLOSSY)
    pump(3.0)
    w._load(LATER)
    pump(3.5)
    assert drawn(w) == 2, "the second measurement did not load"
    assert "E" in readout(w), "no drift figure was reported"


def profile_vs_measured(w):
    """06 — the measurement against the profile built from it."""
    w._load(GLOSSY)
    pump(3.5)
    compare_with(w, "icc", None)
    assert w._reference is not None, (
        "no profile comparison -- this picture needs ArgyllCMS to read the ICC")


def greys(w):
    """07 — the neutral axis, which is where a paper shows its cast."""
    w._load(GLOSSY)
    pump(3.5)
    w._neutral.setChecked(True)
    pump(3.0)
    assert w._neutral.isChecked()


def slice_through(w):
    """08 — a flat cut through two papers at one lightness.

    THE PICTURE THIS RELEASE MOVED MOST. The outline used to be taken through
    the convex hull of the surface, which stood outside the real shape by as
    much as 10 Lab units.
    """
    w._load(GLOSSY)
    pump(3.0)
    w._load(MATTE)
    pump(3.5)
    w._slice_on.setChecked(True)
    pump(3.5)
    assert w._slice_on.isChecked(), "the cut did not switch on"


def light_mode(w):
    """09 — the same window for somebody who works on a white desktop."""
    w._load(GLOSSY)
    pump(3.5)
    w._set_appearance("light")
    pump(3.0)
    assert w._appearance == "light"


def side_by_side(w):
    """14 — two papers a room each, rather than one over the other."""
    w._load(GLOSSY)
    pump(3.0)
    w._load(MATTE)
    pump(3.5)
    w._side_by_side.setChecked(True)
    pump(4.0)
    assert w._side_by_side.isChecked()


def in_space(name: str):
    """12 — the same measurement on each set of axes it can be read against."""
    def shot(w):
        w._load(GLOSSY)
        pump(3.5)
        pick(w._space, name)
        pump(3.5)
        assert w._space.currentData() == name
    shot.__doc__ = f"12 — the same paper drawn in {name}."
    return shot


def ink_amounts(w):
    """18 — a chart in the printer's own controls, which needs no profile."""
    w._open_chart_file(CHART)
    pump(3.0)
    w._load(GLOSSY)
    pump(3.0)
    pick(w._space, "rgb")
    pump(3.5)
    assert w._space.currentData() == "rgb"


def ink_amounts_outside(w):
    """19 — and which of those patches the paper cannot reach."""
    ink_amounts(w)
    w._chart_show_outside.setChecked(True)
    pump(3.0)
    assert w._chart_show_outside.isChecked()


def a_skin_over_the_patches(w):
    """20 — a surface stretched over the patches a chart asks for."""
    ink_amounts(w)
    pick(w._chart_skin, "mesh")
    pump(3.5)
    assert w._chart_skin.currentData() == "mesh"


#: file name → (how to set it up, how big the window is for it)
SHOTS = {
    "01-one-chart.webp": (one_chart, (WIDE, TALL)),
    "02-vs-srgb.webp": (vs_srgb, (WIDE, TALL)),
    "03-where-lost.webp": (where_lost, (WIDE, TALL)),
    "05-drift.webp": (drift, (WIDE, TALL)),
    "06-profile-vs-measured.webp": (profile_vs_measured, (WIDE, TALL)),
    "07-greys.webp": (greys, (WIDE, TALL)),
    "08-slice.webp": (slice_through, (WIDE, TALL)),
    "09-light.webp": (light_mode, (WIDE, TALL)),
    "12-space-cielab.webp": (in_space("lab"), (WIDE, TALL)),
    "12-space-cieluv.webp": (in_space("luv"), (WIDE, TALL)),
    "12-space-ciexyz.webp": (in_space("xyz"), (WIDE, TALL)),
    "14-side-by-side.webp": (side_by_side, (WIDE, TALL)),
    "18-ink-amounts.webp": (ink_amounts, INK),
    "19-ink-amounts-outside.webp": (ink_amounts_outside, INK),
    "20-a-skin-over-the-patches.webp": (a_skin_over_the_patches, INK),
}


def main() -> int:
    global _app
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    for needed in (GLOSSY, MATTE, CHART):
        if not needed.exists():
            print(f"missing demo file: {needed}")
            return 1

    wanted = [n for n in SHOTS
              if not _ASKED or any(a in n for a in _ASKED)]
    if not wanted:
        print(f"nothing matches {' '.join(_ASKED)}; known:")
        for n in SHOTS:
            print(f"  {n}")
        return 1

    # BEFORE THE APPLICATION EXISTS. Importing gamut_app pulls in
    # QtWebEngineWidgets, and Qt refuses to load that once a QCoreApplication
    # has been created unless AA_ShareOpenGLContexts was set first -- so the
    # order of these two lines is not a matter of taste.
    import gamut_app
    _app = QApplication.instance() or QApplication(sys.argv)
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.ask = staticmethod(lambda *a, **k: True)

    for name in wanted:
        setup, (wide, tall) = SHOTS[name]
        # A FRESH WINDOW EACH TIME, and its settings cleared with it. These
        # controls are remembered between runs on purpose, so a shot set up
        # after another one would inherit whatever that one switched on -- and
        # the picture would be right on a clean machine and wrong on the
        # machine that makes them.
        QSettings("MeasuredGamutViewer", "MeasuredGamutViewer").clear()
        window = gamut_app.GamutApp([])
        window.resize(wide, tall)
        window.show()
        pump(2.0)
        try:
            setup(window)
        except AssertionError as why:
            print(f"  [ FAIL ] {name}: {why}")
            failures.append(f"{name}: {why}")
            window.close()
            continue
        except SystemExit as why:
            print(f"  [ SKIP ] {name}: {why}")
            window.close()
            continue
        image = window.grab()
        ok = image.save(str(OUT / name), "WEBP", 88)
        print(f"  [{'  ok  ' if ok else ' FAIL '}] {name}"
              f"  {image.width()}x{image.height()}")
        if not ok:
            failures.append(f"{name}: could not be written")
        window.close()
        pump(0.5)

    print()
    if failures:
        print(f"{len(failures)} picture(s) not made:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"{len(wanted)} picture(s) written to "
          f"{OUT.relative_to(HERE.parent)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
