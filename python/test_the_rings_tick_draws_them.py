"""Ticking "Show rings inside" must actually draw them.

WHAT HAPPENED. v2.43.1 stopped a slider you pressed and let go without moving
from throwing the whole picture away — "a second of black for a change nobody
made". The guard it added lives in `_after_shape_setting` and asks: is this
control's value already the one the picture was drawn with? Then do nothing.

The TICK reaches that guard by the same key, and ticking it changes the rings
COUNT not at all. So the answer was "nothing to do" and the rings were never
drawn. Measured in a fresh window with one paper, and the page asked what it
was holding rather than only photographed:

    tick off → on   traces: 'Glossy-paper | Glossy-paper'      0 px changed
    then the slider  traces gain 'Glossy-paper (rings inside)' 15,816 px

So the tick did nothing at all until some other control was touched — and
because the picture it left behind had no rings in it, the count slider then
"failed to come back" as well: 324,109 px away and 324,721 px back.

After: the tick draws them (7,491 px, two traces gained) and the slider comes
back to 0 px.

THE FAILURE DIRECTION, and it is the whole reason the guard exists: an
unmoved slider must still not rebuild. Measured with the window's own
`_render_count`, which counts pages written:

    rings / detail / agree let go without moving   0 rebuilds each
    ticking Show rings inside                      1
    unticking it                                   1
"""
import pathlib

_APP = (pathlib.Path(__file__).resolve().parent / "gamut_app.py").read_text(
    encoding="utf-8")


def test_the_picture_remembers_whether_the_rings_were_on():
    assert '"rings_on": self._rings_on.isChecked()' in _APP, (
        "the record of what the picture was drawn with no longer holds "
        "whether the rings were showing — so ticking them on looks like a "
        "setting that has not changed, and nothing is redrawn")


def test_the_guard_asks_about_the_switch_and_not_only_the_count():
    where = _APP[_APP.index("def _after_shape_setting"):]
    where = where[:where.index("\n    def ", 10)]
    assert "same_switch" in where, (
        "the release guard is back to comparing only the slider's value, so "
        "the rings tick is answered with 'nothing to do'")
    assert 'self._drawn_with.get("rings_on")' in where
    # AND IT STILL GUARDS THE THING IT WAS WRITTEN FOR.
    assert "control.value() == self._drawn_with[key]" in where, (
        "an unmoved slider will rebuild the whole picture again — the blink "
        "v2.43.1 removed")


def test_both_halves_are_in_the_same_condition():
    # A guard that checks the switch OR the value would let each fault
    # through in turn; it has to be both.
    where = _APP[_APP.index("def _after_shape_setting"):]
    where = where[:where.index("\n    def ", 10)]
    # Written across two lines in the source, so the condition is read as
    # one string rather than line by line — a line-by-line look reported it
    # missing while it was plainly there, which is the same stops-short
    # mistake as a fixed-size window.
    condition = where[where.index("if (control is not None"):]
    condition = condition[:condition.index("return")]
    line = ["same_switch" in condition and "and" in condition]
    assert all(line), condition
    assert line, ("the two halves of the guard are no longer joined by and — "
                  "either an unmoved slider rebuilds, or a tick does nothing")
