"""A live push and a rebuild must draw the same rings.

WHAT HAPPENED. A shape's rings are TWO traces with the SAME NAME: the rings
themselves, and a one-point proxy that exists only so the legend key can be
drawn at full weight while the rings stay light (`ti3gamut._legend_line`).
The live push matched traces by name — as it must, since matching by position
once faded the wrong shape — and so filled the legend proxy with the whole
ring set as well. A rebuild does not.

Measured on two papers against sRGB, rings at 6:

    rebuilt   each shape holds 552 points and 1
    pushed    each shape holds 552 points and 552
    the two pictures differ by 13,538 px

That is the one asymmetry this project keeps having to fix: the live view and
a page you save drawing the same setting differently. After: 552 and 1 by
both routes, and 0 px between them.

THE TRAP INSIDE THE FIX. The obvious test — "does this trace have more than
one point" — must be asked of `_fullData`. A page packs any sizeable array
binary, so `el.data[i].x.length` is `undefined`, and a test written against
that would skip every trace, quietly turning every push into a rebuild: the
second of black the live push exists to remove, with nothing to say it had
happened.
"""
import pathlib

_APP = (pathlib.Path(__file__).resolve().parent / "gamut_app.py").read_text(
    encoding="utf-8")
_PUSH = _APP[_APP.index("def _push_rings"):]
_PUSH = _PUSH[:_PUSH.index("\n    def ", 10)]


def test_the_push_skips_a_trace_with_one_point():
    assert "have>1" in _PUSH.replace(" ", ""), (
        "the rings push no longer skips the one-point legend key, so it "
        "fills it with the whole ring set and the live picture drifts from "
        "what a rebuild — and any page you save — would draw")


def test_the_length_comes_from_fullData():
    assert "_fullData" in _PUSH, (
        "the push reads the trace's length from `data`, where a packed array "
        "reports `undefined` — so no trace would ever be pushed and every "
        "release would fall through to a rebuild")


def test_it_still_matches_by_name():
    # The failure direction: matching by POSITION faded the wrong shape once,
    # which is why the push is keyed on the trace's own name.
    assert "hasOwnProperty.call(want,n)" in _PUSH.replace(" ", ""), (
        "the push no longer matches traces by name")


def test_the_legend_key_is_still_one_point():
    # If the key ever gained points of its own, the rule above would start
    # pushing into it again — silently.
    text = (pathlib.Path(__file__).resolve().parent
            / "ti3gamut.py").read_text(encoding="utf-8")
    where = text[text.index("def _legend_line"):]
    where = where[:where.index("\ndef ", 10)]
    assert "x=[None], y=[None], z=[None]" in where, (
        "the legend key is no longer a single point, so the rings push can "
        "no longer tell it from the rings themselves")
