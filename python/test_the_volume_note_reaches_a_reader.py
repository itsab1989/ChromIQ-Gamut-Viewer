"""The sentence that goes with the volume number lands where it can be read.

⚠ FIVE SENTENCES WERE COMPUTED FOR NOBODY. `_update_volume` worked out what
the figure means -- with two papers open, "Glossy-paper holds 29.2% more
colour than the other one" -- and wrote it to `_volume_hint`. That is the ⓘ
beside the number: a `Hint`, which is a QToolButton fixed at 22x22 and set to
`ToolButtonIconOnly`. Its text is never painted. Driven against the real
window, the button held those 56 characters and its own `grab()` showed the
glyph and nothing else; the words were not in its hover either, nor behind
its click. Five writes, no reader, and NO TEST -- which is why it lasted.

So there are two rules here. One says the sentence is still computed. The
other says it goes somewhere a reader meets it, and that one is written as a
rule about the METHOD rather than about the one widget that was wrong,
because the next person to add a readout will reach for the nearest
attribute exactly as this code did.
"""
import ast
import inspect
import os
import pathlib
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    """⚠ THE APPLICATION HAS TO BE HELD, not merely created.

    Written first as `QApplication.instance() or QApplication(["test"])`,
    whose result nothing kept. The new application was collected on the spot
    and the next QToolButton hit qFatal inside QWidgetPrivate -- which is not
    a failed test, it is SIGABRT taking the whole pytest process with it, one
    crash that would have ended the gate rather than reported a fault.
    """
    from PyQt6.QtWidgets import QApplication
    import gamut_app                                  # noqa: F401
    yield QApplication.instance() or QApplication(["test"])


class Label:
    """A stand-in that only remembers what it was told, like a QLabel."""

    def __init__(self, text=""):
        self._text = text

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text


def _window(slots, reference=None, space="lab"):
    """A window carrying REAL methods, so nothing answers on its own authority.

    ⚠ `_fmt_volume` AND `_volume_units` ARE BOUND, NOT FAKED. A stand-in that
    returns its own idea of a formatted volume would let this test pass over
    a `_update_volume` that had stopped formatting anything -- the exact
    shape of the fault that shipped B7-1 green, where a test fabricated the
    value whose construction was the defect.
    """
    import gamut_app
    win = NS(_slots=slots, _reference=reference,
             _volume=Label("—"), _volume_note=Label(""),
             _volume_hint=Label(""),
             _space=NS(currentData=lambda: space),
             _update_range=lambda: None)
    win._fmt_volume = gamut_app.GamutApp._fmt_volume
    win._volume_units = gamut_app.GamutApp._volume_units.__get__(win)
    return win


def _shape(volume):
    return NS(volume=volume, space="lab")


def test_two_papers_are_compared_in_words_the_reader_can_see():
    import gamut_app
    win = _window([(pathlib.Path("/x/Glossy-paper.ti3"), _shape(702327.0), None),
                   (pathlib.Path("/x/Matte-paper.ti3"), _shape(543689.0), None)])
    gamut_app.GamutApp._update_volume(win)

    assert win._volume.text() == "702,327  ·  543,689", win._volume.text()
    said = win._volume_note.text()
    # 702327 / 543689 - 1 = 29.18%
    assert said == ("Glossy-paper holds 29.2% more colour than the other one."), said
    # AND NOT ON THE ICON, which is where it used to go.
    assert win._volume_hint.text() == "", (
        "the comparison went back to the ⓘ, which paints only its glyph")


def test_the_second_paper_is_not_named():
    """⚠ "THE OTHER ONE" IS DELIBERATE. Two files can share a stem, and this
    window still prints "96.7% of Glossy-paper fits inside Glossy-paper"
    elsewhere for exactly that reason. Naming only the larger of the two
    cannot collide with itself."""
    import gamut_app
    win = _window([(pathlib.Path("/jan/Glossy-paper.ti3"), _shape(700000.0), None),
                   (pathlib.Path("/jun/Glossy-paper.ti3"), _shape(500000.0), None)])
    gamut_app.GamutApp._update_volume(win)
    said = win._volume_note.text()
    assert said.count("Glossy-paper") == 1, (
        f"both papers are named and they have the same name: {said!r}")


def test_one_paper_is_told_what_to_do_with_a_single_figure():
    import gamut_app
    win = _window([(pathlib.Path("/x/Glossy-paper.ti3"), _shape(702327.0), None)])
    gamut_app.GamutApp._update_volume(win)
    assert win._volume.text() == "702,327"
    assert "open a second paper" in win._volume_note.text().lower(), \
        win._volume_note.text()


def test_a_comparison_on_its_own_says_which_shape_the_figure_is():
    import gamut_app
    win = _window([], reference=("Adobe RGB (1998)", _shape(1234567.0)))
    gamut_app.GamutApp._update_volume(win)
    assert win._volume.text() == "1,234,567"
    assert "Adobe RGB (1998)" in win._volume_note.text(), win._volume_note.text()


def test_nothing_open_says_nothing():
    import gamut_app
    win = _window([])
    gamut_app.GamutApp._update_volume(win)
    assert win._volume.text() == "—"
    assert win._volume_note.text() == "", win._volume_note.text()


def test_every_sentence_the_volume_works_out_goes_to_a_readout():
    """⚠ THE RULE, NOT THE ONE WIDGET THAT WAS WRONG.

    Everything `_update_volume` writes must go to `_volume` (the number
    itself) or to a name in `READOUTS` -- the table that gets cleared when
    the last file closes and that `_readout_text` copies into a saved page's
    caption. A sentence written anywhere else is one that survives the file
    it describes, never reaches a saved page, and -- as `_volume_hint`
    proved for five of them -- may never be painted at all.
    """
    import gamut_app
    allowed = {"_volume"} | set(gamut_app.GamutApp.READOUTS)
    src = inspect.getsource(gamut_app.GamutApp._update_volume)
    written = set()
    for node in ast.walk(ast.parse(src.strip())):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setText"
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "self"):
            written.add(node.func.value.attr)
    assert written, (
        "_update_volume writes nothing at all — either it stopped saying "
        "anything or this test has stopped being able to see it")
    stray = written - allowed
    assert not stray, (
        f"_update_volume writes to {sorted(stray)}, which is neither the "
        "number nor a registered readout, so it is never cleared, never "
        "reaches a saved page, and may not be painted at all")


def test_the_hint_beside_the_number_cannot_show_a_sentence(app):
    """The reason the rule above exists, stated as a fact about the widget.

    If `Hint` ever gains a readable text this test should fail and the rule
    can be relaxed on purpose rather than by accident.
    """
    from PyQt6.QtCore import Qt
    import gamut_app
    icon = gamut_app.Hint("A sentence.\n\nAnd the long form.")
    sentence = "Glossy-paper holds 29.2% more colour than the other one."

    # ⚠ THE PROOF IS PIXELS, NOT A SIZE HINT. Written first as
    # `sizeHint().width() > maximumSize().width()` -- 28 > 22 on its own, and
    # a fair-looking stand-in for "the text does not fit". It failed in the
    # full gate: once any earlier test builds a real window, that window's
    # application-wide stylesheet takes the ⓘ's hint down to 21x21, and 21 is
    # not greater than 22. The assertion was measuring the stylesheet, which
    # is no part of the claim. What the claim actually says is that the text
    # CHANGES NOTHING A READER SEES, so the widget is photographed with the
    # sentence and without it and the two images are compared.
    icon.setText("")
    blank = icon.grab().toImage()
    icon.setText(sentence)
    with_text = icon.grab().toImage()
    assert blank == with_text, (
        "setting text on the ⓘ changed what it paints, so a sentence put "
        "there would reach a reader after all")

    assert icon.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert icon.maximumSize().width() <= gamut_app.Hint.ICON + 4
    assert icon.text() not in icon.toolTip(), (
        "the hover now carries the text, so a sentence set on the icon would "
        "reach a reader after all")


def test_the_hover_is_true_while_something_is_open():
    # No window needed: the opening sentence is read out of the source.
    """⚠ THE FIRST SENTENCE IS THE HOVER. `Hint.in_a_sentence` hands over the
    opening sentence and nothing else, and this one opened "Open a chart to
    see how much colour it holds" -- which stayed the hover with two charts
    open and 702,327 · 543,689 printed under it."""
    import gamut_app
    text = inspect.getsource(gamut_app.GamutApp._build_panel) \
        if hasattr(gamut_app.GamutApp, "_build_panel") else \
        inspect.getsource(gamut_app.GamutApp)
    start = text.index("self._volume_hint = Hint(")
    opening = text[start:start + 400]
    assert "Open a chart to see" not in opening, (
        "the volume ⓘ opens with an empty-window instruction again, and that "
        "sentence is what a hover shows whatever is on screen")
