"""Closing one thing must not empty a window that still holds another.

WHY A STAND-IN RATHER THAN THE WINDOW: constructing ``GamutApp`` inside
pytest brings up a QWebEngineView and aborts the run -- the same reason
``test_closing`` and ``test_chart_panel`` work this way. Each method is
called exactly as a click reaches it, against an object holding the parts of
the window it reads.

WHAT WENT WRONG, measured on screen in v2.53.1 with Knut's own files
(a 1168-patch .ti2 chart and the .ti3 measured from it, in the ink-amounts
view he had chosen):

    close the chart          ->  the .ti3 stayed loaded and LISTED, and the
                                 big view showed an empty axes grid captioned
                                 "Measured gamut" -- his "all empty screen"
    close the .ti3 with its  ->  the whole window emptied: the still-open
    own x ("Close this one")     chart was discarded and the comparison reset,
                                 because _close_one asked only about slots and
                                 placed charts before reaching for _on_clear
    the same x with a run    ->  the empty-window text was painted over the
    drawn                        run's graph, with the run still loaded and
                                 its analysis still filled in beside it
    Compare with = Nothing,  ->  the sRGB shell STAYED drawn, its volume still
    nothing else open            printed: a picture and a figure about a shape
                                 that had just been closed

One invariant covers all four, and it is this file's name: whatever closes,
the view is told what is (or is not) left -- it never keeps yesterday's
picture and it never goes silently blank while something is still open.
"""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app():
    import gamut_app
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    return gamut_app


class Recorder:
    """Remembers that it was called, and with what."""

    def __init__(self):
        self.calls = []

    def __call__(self, *a, **k):
        self.calls.append((a, k))
        return None

    def __bool__(self):
        return bool(self.calls)


# ---------------------------------------------------------------- _close_one

def closing_window(*, chart, placed, reference=None, slots=None,
                   run_drawn=False):
    w = SimpleNamespace(
        _slots=list(slots or []),
        _chart=chart,
        _chart_placed=placed,
        _reference=reference,
        _run_drawn=run_drawn,
        _refresh_slot_labels=Recorder(),
        _fill_chart_profiles=Recorder(),
        _redraw=Recorder(),
        _on_clear=Recorder(),
        _image_facts={},
        _reference_path=None,
    )
    # ⚠ THE REAL HELPERS, BOUND — not stubs that shrug. Closing one file with
    # its × now also gives that photograph's colours back (about 9.6 MB), and
    # a stand-in that answered for that method would let the freeing quietly
    # stop happening while this file went on passing. Fourth time today a
    # hand-built stand-in has gone stale as the window grew a helper.
    import gamut_app as _app
    for helper in ("_facts_key", "_forget_unused_facts", "_lays_down_ink"):
        setattr(w, helper, getattr(_app.GamutApp, helper).__get__(w,
                                                                 _app.GamutApp))
    return w


def test_the_x_keeps_an_open_but_unplaced_chart():
    """Knut's chart was open in ink amounts, where placing is optional.

    v2.53.1 asked "is a chart PLACED?" and, hearing no, closed everything --
    the chart he still had open included. An open chart is something on
    screen whichever question placing would answer.
    """
    gamut_app = _app()
    w = closing_window(chart=("chart", object()), placed=None,
                       slots=[(Path("a.ti3"), object(), object())])
    gamut_app.GamutApp._close_one(w, 0)
    assert not w._on_clear, (
        "closing the last measurement with its own x -- tooltip 'Close this "
        "one' -- reached _on_clear, the start-again gesture, while a chart "
        "was still open")
    assert w._redraw, "and nothing redrew what was left"


def test_the_x_keeps_the_comparison():
    """'Close the paper, open the next, and your sRGB stays where it was.'

    That is _on_clear's own docstring describing this x. v2.53.1 reset the
    comparison the moment the last paper closed.
    """
    gamut_app = _app()
    w = closing_window(chart=None, placed=None,
                       reference=("sRGB", object()),
                       slots=[(Path("a.ti3"), object(), object())])
    gamut_app.GamutApp._close_one(w, 0)
    assert not w._on_clear, (
        "closing the last paper reset the comparison it was being judged "
        "against -- the exact workflow the x exists to serve")


def test_the_x_keeps_the_run():
    gamut_app = _app()
    w = closing_window(chart=None, placed=None, run_drawn=True,
                       slots=[(Path("a.ti3"), object(), object())])
    gamut_app.GamutApp._close_one(w, 0)
    assert not w._on_clear, (
        "closing the last file painted the empty-window text over a run "
        "that is still loaded")
    assert w._redraw, "the run's picture was not redrawn"


def test_the_x_still_starts_again_when_nothing_is_left():
    """The behaviour that was right, kept right."""
    gamut_app = _app()
    w = closing_window(chart=None, placed=None,
                       slots=[(Path("a.ti3"), object(), object())])
    gamut_app.GamutApp._close_one(w, 0)
    assert w._on_clear, (
        "with truly nothing left, closing the last file should be the "
        "start-again gesture")


# -------------------------------------------------------------- _close_chart

def test_closing_the_chart_always_repaints():
    """v2.53.1 skipped the redraw with nothing else open.

    Measured: the closed chart's dot cloud stayed in the view, its name in
    the title and '-- to be printed' in the legend, over a panel that said
    nothing was open.
    """
    gamut_app = _app()
    w = SimpleNamespace(
        _chart=("chart", object()),
        _chart_placed=object(),
        _slots=[],
        _reference=None,
        _refresh_chart_panel=Recorder(),
        _redraw=Recorder(),
    )
    gamut_app.GamutApp._close_chart(w)
    assert w._chart is None and w._chart_placed is None
    assert w._redraw, (
        "the chart was closed and the view was never repainted: the closed "
        "chart's picture stays on screen")


# ------------------------------------------------------------------- _redraw

def redraw_window(**over):
    """Just the parts of the window _redraw reads, on both its early paths."""
    w = SimpleNamespace(
        # The view exists: these tests are about a BUILT window. (While the
        # column is still being constructed _redraw stands aside, and the
        # placeholder is set once the view is there.)
        _view=object(),
        _slots=[],
        _reference=None,
        _chart_drawable=lambda: False,
        _show_placeholder=Recorder(),
        _show_open_but_not_drawn=Recorder(),
        _update_volume=Recorder(),
        _update_coverage=Recorder(),
        _update_drift=Recorder(),
        _let_the_exports_follow_the_picture=Recorder(),
        _refresh_style_controls=Recorder(),
        _apply_side_by_side_availability=Recorder(),
        _apply_closing_availability=Recorder(),
        _apply_detail_availability=Recorder(),
        _update_chart_numbers=Recorder(),
        _scene_contents=lambda: ([], [], [], None),
        _chart_cloud=lambda: None,
        _drawing_in_ink=lambda: True,
        _write_scene=Recorder(),
        _show_page=Recorder(),
        _drop_the_scene_before_last=Recorder(),
        _render_count=0,
        _tmp=Path("."),
    )
    for name, value in over.items():
        setattr(w, name, value)
    return w


def test_an_empty_window_shows_its_words_not_yesterdays_picture():
    """Nothing open, redraw asked: the view must be told it is empty.

    v2.53.1 returned without touching the view, which is how a closed
    comparison stayed on screen as an sRGB shell -- volume still printed --
    beside a combo reading "Nothing, this one on its own".
    """
    gamut_app = _app()
    w = redraw_window()
    gamut_app.GamutApp._redraw(w)
    assert w._show_placeholder, (
        "with nothing open, _redraw left the view exactly as it was -- "
        "whatever was drawn before it closed is still on screen")
    assert w._update_volume and w._update_coverage, (
        "and the figures were never re-asked, so they still describe what "
        "was just closed")


def test_ink_amounts_with_no_chart_says_so_instead_of_an_empty_scene():
    """Knut's empty screen itself.

    A .ti3 open, ink amounts chosen, no chart (any more): the scene contents
    are empty by design -- ink amounts draw a chart and nothing else -- and
    v2.53.1 wrote that empty scene to a page and showed it. The view must
    say what is open and what would bring it back instead.
    """
    gamut_app = _app()
    meas = object()
    w = redraw_window(
        _slots=[(Path("printer.ti3"), object(), meas)],
        _scene_contents=lambda: ([], [None], [None], None),
    )
    gamut_app.GamutApp._redraw(w)
    assert not w._write_scene and not w._show_page, (
        "an entirely empty scene was written and shown: Knut's 'all empty "
        "screen', a blank page over a window that still lists an open file")
    assert w._show_open_but_not_drawn or w._show_placeholder, (
        "and the view was never given any words about why it shows nothing")
