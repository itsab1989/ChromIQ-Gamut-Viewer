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

    figures = {name: Label(f"a sentence about {name}")
               for name in ("_coverage", "_picture_loss", "_pair", "_drift",
                            "_drift_worst", "_chart_headline", "_chart_rows",
                            "_chart_spread")}
    w = SimpleNamespace(
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
        **figures)

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
    close_them_all(window)
    left = {name: getattr(window, name).text()
            for name in ("_coverage", "_picture_loss", "_pair", "_drift",
                         "_drift_worst", "_chart_headline", "_chart_rows",
                         "_chart_spread")
            if getattr(window, name).text()}
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
