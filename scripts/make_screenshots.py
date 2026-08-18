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

# THE SETTINGS GO SOMEWHERE THROWAWAY, and this must happen before the
# window is built. A driver that uses the real store both destroys what
# the person using this application has chosen and leaves its own last
# state behind as their new preference -- which is how "the walls behind
# the shape are missing" was reported as a bug in the viewer. See
# python/prefs.py.
import prefs  # noqa: E402

prefs.use_a_scratch_store()
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

#: Temporary folders a shot made, removed when the run finishes.
_MADE: list = []
#: Every picture written this run, by what it looks like. See the check in
#: main(): two shots that come out identical are a fault in one of them.
seen: dict[bytes, str] = {}
_app = None


def pump(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        _app.processEvents()
        time.sleep(0.005)


class ChoosesForYou:
    """Stands in for the "choose a file" dialog, and answers with *path*.

    WHY THIS IS HERE AND NOT A LONGER PAUSE. Comparing against a profile is
    the one entry in Compare with that has to ASK which file, so
    `_on_compare_changed` opens a file dialog and calls `.exec()` on it. Run
    with no display that returns immediately and the shot is simply skipped;
    run on a REAL display -- which is the only way these pictures can be taken
    at all, because an offscreen platform cannot capture the web view -- it is
    a modal window sitting on the desktop waiting for somebody to click it.
    The generator stopped dead there for eight minutes at 2.8% of one core,
    with a file picker open over whatever else was on screen.

    The same trap CLAUDE.md warns about for the test suite, arriving by the
    one route the suite never takes.
    """

    def __init__(self, path) -> None:
        self._path = str(path)

    def exec(self):
        return 1                      # as if the user pressed Open

    def selectedFiles(self):
        return [self._path]


def answer_file_dialogs_with(window, path) -> None:
    """Every file dialog this window opens from now on picks *path*."""
    window._file_dialog = lambda *a, **k: ChoosesForYou(path)


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


def whole_window(window):
    """The window WITH the picture in it, which one grab does not give you.

    THE FAULT THIS EXISTS FOR. `window.grab()` walks the widget tree and paints
    each child — and the web view that draws the gamut is not painted by Qt at
    all. It has its own render path, so it comes back as a blank rectangle, and
    every picture this script wrote had the controls down the left and an empty
    grey box where the shape belongs: 27 kB files against the 126-202 kB of the
    ones already committed.

    It went unnoticed because nothing looked wrong in a terminal. What gave it
    away was two shots coming out BYTE-FOR-BYTE IDENTICAL — 02 and 03 differ
    only inside the picture, so identical files meant the picture was not in
    them.

    Grabbing the view ON ITS OWN does work, which is what `make_doc_shots.py`
    has always done. So both are taken and the second is painted into the
    first, at the place the view actually sits.
    """
    from PyQt6.QtGui import QPainter
    shot = window.grab()
    view = getattr(window, "_view", None)
    if view is not None and view.width() > 1 and view.height() > 1:
        picture = view.grab()
        where = view.mapTo(window, view.rect().topLeft())
        painter = QPainter(shot)
        painter.drawPixmap(where, picture)
        painter.end()
    return shot


def until_it_changes(window, before, seconds: float = 25.0) -> bool:
    """Wait for the picture to actually change, rather than for a while.

    WHY A FIXED PAUSE IS NOT ENOUGH. A redraw here writes a fresh
    self-contained page of about 6 MB and hands it to the web view to load, so
    "3 seconds" is a guess about somebody else's machine. Guessing short does
    not fail loudly -- it grabs the frame that is still on screen, which is the
    PREVIOUS shot, and writes it out under the new name. That is exactly how 03
    came to be byte-for-byte identical to 02.

    Waiting for the pixels to move instead is both faster on a quick machine
    and correct on a slow one.
    """
    end = time.time() + seconds
    while time.time() < end:
        pump(0.25)
        if whole_window(window).toImage() != before:
            pump(0.6)                  # let the rest of the frame settle
            return True
    return False


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
    """03 — and where that colour is lost, rather than how much of it.

    THE SWITCH BEING ON IS NOT THE PICTURE BEING DIFFERENT. This asked
    `_show_lost.isChecked()`, which is true the instant it is set and says
    nothing about what was drawn -- and the picture it published was
    **byte-for-byte identical to 02**, the shot before it. A page explaining
    where a paper falls short of sRGB, illustrated with a picture that does
    not show it, for as long as nobody compared two files.

    So it is asked of the shape instead: the marks are drawn from the vertices
    the containment test says are outside, and if there are none of those
    there is nothing to photograph and the caption is a lie.
    """
    w._load(GLOSSY)
    pump(3.5)
    compare_with(w, "space", "sRGB")
    before = whole_window(w).toImage()
    w._show_lost.setChecked(True)
    assert w._show_lost.isChecked(), "the switch did not take"
    assert until_it_changes(w, before), (
        "the switch is on and the picture never changed -- either nothing is "
        "marked as lost, or the redraw never reached the screen, and either "
        "way this shot shows the same thing as 02")


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
    if not PROFILE.exists():
        raise SystemExit(f"{PROFILE} is missing")
    # THE ONE SHOT THAT IS ASKED A QUESTION. See ChoosesForYou: this entry
    # opens a file dialog, and on a real display nobody is there to answer it.
    answer_file_dialogs_with(w, PROFILE)
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
    """19 — and which of those patches the paper cannot reach.

    THE SECOND ONE THE DUPLICATE CHECK CAUGHT, and the fault was here rather
    than in the window. Written like 03 was -- set the switch, wait three
    seconds, assert the switch is set -- it published a picture identical to
    18, and the obvious reading was that the marking is simply not drawn in
    ink amounts.

    MEASURED, and that reading was wrong. In the state 18 leaves behind there
    is no profile placing the chart, so there is no colour to judge and the
    marking is never worked out at all -- and the window is right about that:
    it HIDES the out-of-reach row, and the panel says "Choose a profile under
    Placed through and they can be counted against whatever else you have
    open." This function then reached past the hidden row and ticked its box
    anyway, which changes nothing and cannot: a switch the reader could not
    have found was never the thing under test.

    Choose the profile, as the window asks and as the README describes, and
    the marking works here exactly as it does in CIELAB: 151 of the 480
    patches come out beyond what that paper can reach.
    """
    ink_amounts(w)
    w._chart_profile = PROFILE
    w._fill_chart_profiles()
    w._place_chart()
    pump(3.0)
    assert w._chart_placed is not None, "the chart was not placed by the profile"
    assert w._chart_outside_row.isVisible(), (
        "the out-of-reach row is still hidden, so its switch is not something "
        "a reader could reach in this state -- setting it by hand would prove "
        "nothing")

    marked = w._chart_cloud()[2]
    assert marked is not None and marked.any(), (
        "nothing came out beyond this paper, so this shot would show the same "
        "thing as 18 however long we waited")

    # THE CLAIM THE README MAKES ABOUT THIS PICTURE, checked rather than
    # trusted: "the losses are the whole outer shell of the ink range, while
    # the interior survives". A shape thrown round the survivors must be
    # clearly smaller than one round the whole chart, and a shape thrown round
    # the lost ones must be nearly the whole thing -- because they wrap it.
    import numpy as _np
    from scipy.spatial import ConvexHull
    import chart as _chart_mod

    def _volume(points):
        points = _np.unique(_np.asarray(points).round(6), axis=0)
        return float(ConvexHull(points).volume)

    ink = _chart_mod.device_positions(w._chart[1])
    whole = _volume(ink)
    survivors = _volume(ink[~marked])
    lost = _volume(ink[marked])
    assert survivors < whole * 0.95, (
        f"the survivors fill {survivors / whole:.0%} of the chart's range, so "
        f"the losses are not the outer shell the README says they are")
    assert lost > whole * 0.75, (
        f"a shape round the lost patches is only {lost / whole:.0%} of the "
        f"whole chart, so they do not wrap the interior")

    # THE SWITCH OFF FIRST, because it starts on: capturing "before" with the
    # marking already drawn would compare the picture against itself.
    w._chart_show_outside.setChecked(False)
    pump(2.5)
    before = whole_window(w).toImage()
    w._chart_show_outside.setChecked(True)
    assert w._chart_show_outside.isChecked(), "the switch did not take"
    assert until_it_changes(w, before), (
        "the switch is on and the picture never changed -- no patch came out "
        "marked as unreachable, so this shows the same thing as 18")


def a_skin_over_the_patches(w):
    """20 — a surface stretched over the patches a chart asks for."""
    ink_amounts(w)
    pick(w._chart_skin, "mesh")
    pump(3.5)
    assert w._chart_skin.currentData() == "mesh"


def _a_run_of_profiles(w):
    """Four profiles of one printer, five years apart, in a timeline window.

    GENERATED RATHER THAN COMMITTED, like the example pages do it: each is a
    1257 kB copy of a 1257 kB profile differing in about six thousand bytes,
    so four of them would be five megabytes of near-duplicate binary for
    something that takes a second to make.
    """
    import importlib.util
    import tempfile

    import gamut_app

    spec = importlib.util.spec_from_file_location(
        "mkprof", HERE / "make_demo_profiles.py")
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    folder = pathlib.Path(tempfile.mkdtemp(prefix="shot-profiles-"))
    _MADE.append(folder)
    if mk.main(folder) != 0:
        raise AssertionError("the demo profiles would not build")
    dialog = gamut_app.TimelineDialog(w, appearance=w._appearance)
    dialog.resize(1000, 760)
    dialog.show()
    dialog.add(sorted(folder.glob("printer-*.icc")))
    pump(4.0)
    assert dialog._run and len(dialog._run.usable) == 4, "the run did not build"
    return dialog


def over_time(w):
    """24 — one device followed through four profiles: the graph."""
    dialog = _a_run_of_profiles(w)
    pump(3.0)
    assert dialog._chosen_pair() is None, "it should open on the graph"
    assert "drifted" in dialog._verdict.text() or \
           "moved" in dialog._verdict.text(), dialog._verdict.text()
    return dialog


def one_step_of_a_run(w):
    """25 — and the same run with one step chosen, drawn as the heat-map."""
    dialog = _a_run_of_profiles(w)
    before = whole_window(dialog).toImage()
    # ONE STEP, NOT THE WHOLE RUN, and the difference matters for what this
    # picture is meant to show. Against the whole run the sentence underneath
    # says much the same thing either way, so a shot of it cannot show that
    # the words follow the picture -- which is the fault this feature had.
    # A single step is the discriminating case, and it is also the one a
    # reader reaches for: the graph jumped here, so where did it go?
    #
    # Chosen by DATA rather than by index, so adding an entry later cannot
    # silently change which picture this is.
    for i in range(dialog._picture_of.count()):
        if dialog._picture_of.itemData(i) == ("step", 0):
            dialog._picture_of.setCurrentIndex(i)
            break
    else:
        raise AssertionError("no step is on offer")
    dialog._draw()
    pair = dialog._chosen_pair()
    assert pair is not None, "choosing a step did not give a pair"
    assert until_it_changes(dialog, before), (
        "the picture never changed, so this shows the same thing as 24")
    # THE SENTENCE UNDERNEATH MUST BE ABOUT THIS PAIR, not about the run. It
    # was not, and a published screenshot is how that was noticed.
    said = dialog._verdict.text()
    assert pair[2].split(" → ")[0] in said and pair[2].split(" → ")[1] in said, (
        f"the words under the picture are not about it: {said}")
    return dialog


def which_way_it_moved(w):
    """26 — the same pair, coloured by WHICH WAY rather than how far."""
    import gamut_app

    dialog = _a_run_of_profiles(w)
    for i in range(dialog._picture_of.count()):
        if dialog._picture_of.itemData(i) == ("whole", 0):
            dialog._picture_of.setCurrentIndex(i)
            break
    dialog._draw()
    pump(3.0)
    before = whole_window(dialog).toImage()
    for i in range(dialog._coloured_by.count()):
        if dialog._coloured_by.itemData(i) == "b":     # warmer or cooler
            dialog._coloured_by.setCurrentIndex(i)
            break
    else:
        raise AssertionError("the direction views are not on offer")
    dialog._draw()
    figure = dialog._cloud_figure()
    assert figure is not None, "no picture was built"
    # THE THING THAT MAKES IT A DIRECTION: a scale with no change in the
    # middle and opposite ends, rather than one running up from zero.
    assert figure.data[0].marker.cmin < 0 < figure.data[0].marker.cmax, (
        f"this is not a two-way scale: {figure.data[0].marker.cmin} to "
        f"{figure.data[0].marker.cmax}")
    assert until_it_changes(dialog, before), (
        "the picture never changed, so this shows the same thing as 25")
    return dialog


def split_into_families(w):
    """27 — the same pair split into the colour families the report names.

    THE PICTURE AND THE WORDS IN ONE FRAME, which is the whole point of the
    feature: the sentences underneath say the blues went toward the magentas,
    and the key above turns every other family off so you can go and look at
    them. A shot of either half alone would not show that they are one answer.
    """
    dialog = _a_run_of_profiles(w)
    for i in range(dialog._picture_of.count()):
        if dialog._picture_of.itemData(i) == ("whole", 0):
            dialog._picture_of.setCurrentIndex(i)
            break
    else:
        raise AssertionError("the whole-run comparison is not on offer")
    dialog._draw()
    pump(3.0)
    before = whole_window(dialog).toImage()

    assert dialog._by_family.isVisible(), (
        "the split box must be offered while a cloud is showing")
    dialog._by_family.setChecked(True)
    dialog._draw()
    pump(3.0)

    figure = dialog._cloud_figure()
    assert figure is not None, "no picture was built"
    # SEVEN GROUPS, EACH NAMED WITH ITS COUNT -- the thing the shot exists to
    # show, checked rather than hoped for.
    assert len(figure.data) >= 6, f"only {len(figure.data)} groups"
    assert all(" — " in t.name for t in figure.data), (
        [t.name for t in figure.data])
    # ONE KEY, AND NO GROUP OWNS IT. Asking "which trace carries the bar"
    # is the question that passed while the fault was live: the bar was on
    # the FIRST group, so switching the reds off took the whole scale off
    # the page. Owned by the scene, no group can take it away.
    assert not any(t.marker.showscale for t in figure.data), (
        "a family owns the colour key and can switch it off")
    assert all(t.marker.coloraxis == "coloraxis" for t in figure.data)
    assert figure.layout.coloraxis.colorbar.title.text == "ΔE2000"
    # THE BOX MUST BE PINNED, or switching a family off moves the picture.
    assert figure.layout.scene.xaxis.autorange is False
    # and the words underneath have to be there too
    assert "which colour families moved" in dialog._families.text()
    assert until_it_changes(dialog, before), (
        "the picture never changed, so this shows the same thing as 26")
    return dialog


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
    "24-one-device-over-time.webp": (over_time, (WIDE, TALL)),
    "25-one-step-of-a-run.webp": (one_step_of_a_run, (WIDE, TALL)),
    "26-which-way-it-moved.webp": (which_way_it_moved, (WIDE, TALL)),
    "27-split-into-families.webp": (split_into_families, (WIDE, TALL)),
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
        window = gamut_app.GamutApp([])
        window.resize(wide, tall)
        window.show()
        pump(2.0)
        subject = window
        try:
            # A SETUP MAY HAND BACK SOMETHING ELSE TO PHOTOGRAPH. Most shots
            # are of the main window, so returning nothing keeps meaning that.
            # But two of this application's features live in windows of their
            # own -- following a device over time is one -- and until this
            # existed neither could be pictured at all, which is why the whole
            # timeline feature shipped with no screenshot anywhere.
            #
            # `whole_window` needs no change to cope: it looks for a `_view`
            # attribute and paints it in, and the dialog has one for the same
            # reason the main window does.
            subject = setup(window) or window
        except AssertionError as why:
            print(f"  [ FAIL ] {name}: {why}")
            failures.append(f"{name}: {why}")
            window.close()
            continue
        except SystemExit as why:
            print(f"  [ SKIP ] {name}: {why}")
            window.close()
            continue
        image = whole_window(subject)
        # NO TWO OF THESE MAY BE THE SAME PICTURE.
        #
        # Every shot says what must be true of it, and those claims are only
        # as good as somebody having thought of the right one: 03 asked
        # whether its switch was ticked, which it was, and published a file
        # identical to 02. This is the claim that needs no foresight -- two
        # README pictures illustrating two different things cannot be the same
        # image, whatever went wrong to make them so.
        fingerprint = bytes(image.toImage().constBits().asarray(
            image.toImage().sizeInBytes()))
        clash = seen.get(fingerprint)
        if clash:
            print(f"  [ FAIL ] {name}: identical to {clash}")
            failures.append(f"{name}: the same picture as {clash}")
            window.close()
            continue
        seen[fingerprint] = name
        ok = image.save(str(OUT / name), "WEBP", 88)
        print(f"  [{'  ok  ' if ok else ' FAIL '}] {name}"
              f"  {image.width()}x{image.height()}")
        if not ok:
            failures.append(f"{name}: could not be written")
        window.close()
        pump(0.5)

    # THE GENERATED PROFILES GO AGAIN. Twelve megabytes a run otherwise, and
    # this project has already had one 27 GB version of exactly that fault.
    import shutil
    for folder in _MADE:
        shutil.rmtree(folder, ignore_errors=True)

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
