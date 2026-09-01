"""What "Close them all" really closes.

WHY A STAND-IN RATHER THAN THE WINDOW. Constructing ``GamutApp`` inside pytest
brings up a QWebEngineView and aborts the run -- the same reason
``test_chart_panel`` works this way. So the method is called exactly as a
click reaches it, against an object holding the parts of the window it reads.

WHAT WENT WRONG, and it is the reason this file exists. The button said it
closed everything and left the comparison behind. Measured in the real
application, two papers open and Adobe RGB chosen, straight after the press:

    files open              []
    shapes actually drawn   ['Adobe RGB (1998)']
    the readout said        "90.7% of the colour Glossy-paper can print also
                             fits inside Adobe RGB (1998)"

A shape with nothing left to compare against, and figures still describing a
file that had just been closed. The second is the worse one: a saved picture
takes its caption straight from those labels, so a wrong sentence does not
stay on the screen where somebody might notice it.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class Label:
    """Just enough of a text label to be set, read and asked if it is empty."""

    def __init__(self, text=""):
        self._text = text

    def setText(self, text):        # noqa: N802  (Qt's name)
        self._text = text

    def text(self):
        return self._text

    def isVisible(self):            # noqa: N802  (Qt's name)
        return True


class Combo:
    """A stand-in for Compare with, remembering what it was set to."""

    def __init__(self, index=2):
        self.index = index
        self.handled = 0

    def setCurrentIndex(self, i):   # noqa: N802  (Qt's name)
        self.index = i

    def currentData(self):          # noqa: N802  (Qt's name)
        return None if self.index == 0 else ("space", "Adobe RGB (1998)")


@pytest.fixture
def window():
    """A window with two papers, a chart, a comparison and a full readout."""
    import gamut_app                                       # noqa: F401
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    # EVERY READOUT THE WINDOW HAS, taken from the window's own list rather
    # than a copy of it here. A copy is what let two of them be forgotten:
    # the colour-family lines survived "Close them all" and were missing from
    # every saved page, because three separate lists had to be kept in step.
    import gamut_app as _app
    figures = {name: Label(f"a sentence about {name}")
               for name in _app.GamutApp.READOUTS}
    w = SimpleNamespace(
        READOUTS=_app.GamutApp.READOUTS,
        _slots=[("a", 1, None), ("b", 2, None)],
        _chart=("chart", None),
        _chart_placed=object(),
        _compare=Combo(index=2),
        _reference=("Adobe RGB (1998)", object()),
        _reference_path=None,
        _volume=Label("702,327"),
        _volume_hint=Label(""),
        _clear_btn=SimpleNamespace(setVisible=lambda v: None),
        _save=SimpleNamespace(setEnabled=lambda v: None),
        _refresh_slot_labels=lambda: None,
        _refresh_chart_panel=lambda: None,
        _fill_chart_profiles=lambda: None,
        _show_placeholder=lambda: None,
        _volume_units=lambda: "cubic Lab units",
        _image_facts={},
        **figures)
    # ⚠ THE REAL HELPERS, BOUND. "Close them all" now also gives back the
    # colours of every photograph it closes — about 9.6 MB each — and this
    # fixture is what proves the gesture still does everything else. A stub
    # that shrugged would let the freeing quietly stop happening.
    for helper in ("_facts_key", "_forget_unused_facts"):
        setattr(w, helper,
                getattr(_app.GamutApp, helper).__get__(w, _app.GamutApp))

    def compare_changed():
        # The real handler, reduced to the one thing this test is about.
        w._reference = None if w._compare.currentData() is None else w._reference
        w._compare.handled += 1

    w._on_compare_changed = compare_changed
    return w


def close_them_all(w):
    import gamut_app
    gamut_app.GamutApp._on_clear(w)


def test_closing_them_all_closes_the_comparison_too(window):
    close_them_all(window)
    assert window._compare.index == 0, (
        "Compare with was left showing a comparison that is no longer loaded")
    assert window._reference is None, (
        "the comparison shape survived, so it is still drawn with nothing "
        "left to compare it against")


def test_it_goes_through_the_combo_box_rather_than_behind_it(window):
    """Assigning to _reference would leave the box naming a shape that is gone.

    The handler is also what clears the note underneath, so reaching past it
    would leave that behind too.
    """
    close_them_all(window)
    assert window._compare.handled == 1, (
        "the comparison was cleared without telling the control that shows it")


def test_the_figures_go_with_the_files_they_described(window):
    """⚠ FROM THE WINDOW'S OWN LIST, NOT A COPY OF IT.

    This test held a fourth hand-written copy of the readout names — the
    exact fault `READOUTS` exists to prevent, and its comment describes:
    "a list that must be kept in step by hand will not be". The copy still
    named `_pair`, which is not a widget on the window at all and never was,
    and it was missing `_range` and `_shared_lbl`, which are.

    A list that omits a readout cannot notice that readout going stale.
    """
    import gamut_app
    close_them_all(window)
    left = {name: getattr(window, name).text()
            for name in gamut_app.GamutApp.READOUTS
            if getattr(window, name, None) is not None
            and getattr(window, name).text()}
    assert not left, (
        f"these still describe files that were just closed: {sorted(left)}")


def test_the_readout_a_saved_picture_would_carry_is_empty_afterwards(window):
    """The caption of an exported picture is read straight out of the labels.

    So this is not only about what is on screen: a stale figure here becomes a
    stale figure printed under a picture somebody sends to a forum.
    """
    import gamut_app
    close_them_all(window)
    said = gamut_app.GamutApp._readout_text(window)
    assert said.strip() == "", f"a picture saved now would be captioned {said!r}"


def test_the_files_and_the_chart_still_go(window):
    """The behaviour that was already right, kept right."""
    close_them_all(window)
    assert window._slots == []
    assert window._chart is None
    assert window._chart_placed is None
    assert window._volume.text() == "—"


def test_the_pictures_colours_are_handed_back_too(window):
    """⚠ "CLOSE THEM ALL" GAVE BACK EVERYTHING BUT THE MEMORY.

    It emptied the slots, the chart, the comparison and every readout in the
    window's own list — and left each photograph's colours behind. An entry
    is the picture's colours themselves, up to 300,000 of them in two float64
    arrays: about 9.6 MB a photograph, held for the life of the window.
    Twenty photographs in a sitting is roughly 190 MB that the start-again
    gesture could never give back.

    This belongs beside the other four things the gesture closes, and in the
    same fixture, because the fault was that a list of things to release had
    to be kept in step by hand — which is how the colour-family lines came to
    survive it once already.
    """
    window._image_facts = {("/a/holiday.png", 111): {"colours": 9},
                           ("/b/sunset.png", 222): {"colours": 9}}
    close_them_all(window)
    assert window._image_facts == {}, (
        "the photographs' colours survived Close them all — about 9.6 MB "
        "each, for the life of the window")


def test_every_name_in_the_readout_list_is_a_readout_that_exists():
    """⚠ `_pair` SAT IN THAT LIST AND WAS NOT A WIDGET AT ALL.

    Both consumers skip a missing name with `getattr(..., None)`, so it did
    nothing, quietly, for as long as it was there: not cleared, not copied
    into a saved page, not noticed. A list whose entries are silently
    optional is a list that cannot be wrong out loud.

    The other half of the same fault: `_range` and `_shared_lbl` ARE
    readouts and were missing from it, so every saved page went out without
    the range panel and without "Both can print …% of everything either one
    can". Driven before fixing, both absent from `_readout_text()`.
    """
    import inspect
    import gamut_app

    src = inspect.getsource(gamut_app.GamutApp)
    for name in gamut_app.GamutApp.READOUTS:
        assert f"self.{name} = " in src, (
            f"{name} is in READOUTS and is never assigned on the window — "
            f"both consumers skip it in silence, so it does nothing at all")
    # AND THE READOUTS THAT EXIST ARE IN IT. These four are the sentences a
    # saved page carries; leaving one out loses it from every export.
    for name in ("_coverage", "_picture_loss", "_range", "_shared_lbl"):
        assert name in gamut_app.GamutApp.READOUTS, (
            f"{name} is a readout and is not in the list, so it is neither "
            f"cleared with the files nor carried into a saved page")
