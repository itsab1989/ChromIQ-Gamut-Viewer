"""The lid over the cut: drawn where there is an opening, and nowhere else.

Fading the agreement away leaves an OPEN shell, and turned round you look
into it: the far wall is lit exactly like an outside, because there is no
separate inside to shade. Reported from the window as "this one looks
scattered". The lid is the piece of the OTHER shape that lies inside this one.

WHAT THIS GUARDS is not the geometry — `test_a_lid_closes_the_cut` does that —
but the OFFER: that it appears exactly where it can act and refuses where it
cannot, because this window's own rule, paid for four times, is that a control
offered where it cannot act is worse than one that is not there.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


def _lids(figure):
    return [d for d in figure.data
            if "where it is cut" in (getattr(d, "name", "") or "")]


@pytest.fixture(scope="module")
def shapes():
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut
    paper_file = _DEMO / "Glossy-paper.ti3"
    if not paper_file.is_file():
        pytest.skip("no demo paper")
    paper = build_gamut(ti3gamut.read_measurement(paper_file).lab,
                        input_space="lab")
    return (paper, reference_gamut("sRGB", steps=24),
            reference_gamut("Display P3", steps=24))


def _fresh():
    """The kept answers cleared, so one case cannot serve another's lid."""
    import ti3gamut
    ti3gamut._LAST_CUT = None
    ti3gamut._LAST_CAP = None


def test_a_pair_with_an_opening_gets_a_lid(shapes):
    import ti3gamut
    paper, srgb, _p3 = shapes
    _fresh()
    fig = ti3gamut.build_figure([("Glossy-paper", paper), ("sRGB", srgb)],
                                "t", agree=0.0, cap=True)
    lids = _lids(fig)
    assert lids, "no lid was drawn for a pair with the agreement faded away"
    for lid in lids:
        assert len(np.asarray(lid.i)) > 100, (
            f"the lid has only {len(np.asarray(lid.i))} triangles")
        assert lid.vertexcolor is not None, "the lid was not painted"


def test_no_lid_where_nothing_has_been_cut_away(shapes):
    """At full strength the shape is whole: a lid would be a second skin.

    ⚠ WITH `split=True`, WHICH IS WHAT THE WINDOW SENDS. A saved page has to
    be able to move the slider itself, so the window asks for the masks even
    at full strength — and only then are they there to build a lid from.
    Asked WITHOUT it the masks are never worked out at all, so no lid appears
    whatever the guard says, and a mutation removing the guard passed.
    """
    import ti3gamut
    paper, srgb, _p3 = shapes
    _fresh()
    plain = ti3gamut.build_figure([("Glossy-paper", paper), ("sRGB", srgb)],
                                  "t", agree=0.0, split=True, cap=True)
    assert _lids(plain), (
        "no lid even with the agreement faded away — the case below cannot "
        "tell a working guard from a lid that never appears")
    _fresh()
    fig = ti3gamut.build_figure([("Glossy-paper", paper), ("sRGB", srgb)],
                                "t", agree=1.0, split=True, cap=True)
    assert not _lids(fig), (
        "a lid was drawn over a shape with no opening in it")


def test_no_lid_when_it_is_not_asked_for(shapes):
    import ti3gamut
    paper, srgb, _p3 = shapes
    _fresh()
    fig = ti3gamut.build_figure([("Glossy-paper", paper), ("sRGB", srgb)],
                                "t", agree=0.0, cap=False)
    assert not _lids(fig), "a lid was drawn without being asked for"


def test_three_shapes_are_refused_rather_than_guessed_at(shapes):
    """With three, the hole ends at whichever of the others comes first.

    That is a different construction from this one, and capping against one
    arbitrary neighbour would be quietly wrong — so it declines, and the
    window dims the tick with the reason.
    """
    import ti3gamut
    paper, srgb, p3 = shapes
    _fresh()
    three = [("Glossy-paper", paper), ("sRGB", srgb), ("Display P3", p3)]
    fig = ti3gamut.build_figure(three, "t", agree=0.0, cap=True)
    assert not _lids(fig), (
        "a lid was drawn for three shapes, where 'the other shape' is not one "
        "shape at all")
    # and the pair it is built from DOES get one, so this is not passing
    # because nothing anywhere gets a lid
    _fresh()
    pair = ti3gamut.build_figure(three[:2], "t", agree=0.0, cap=True)
    assert _lids(pair), (
        "the same shapes as a pair get no lid either — this test is not "
        "measuring the refusal, it is measuring a lid that never appears")


def test_the_lid_wears_the_other_shape_s_colours(shapes):
    """It IS that shape's surface, so it is painted in its colours."""
    import ti3gamut
    paper, srgb, _p3 = shapes
    _fresh()
    out, _f, stands, _l = ti3gamut.recut_where_they_part(
        [("Glossy-paper", paper), ("sRGB", srgb)])
    got = ti3gamut.cap_over_the_cut(out, stands, 0)
    assert got is not None, "nothing to check"
    corners, faces, colours = got
    assert len(colours) == len(corners), "a colour is missing from a corner"
    assert (colours >= 0).all() and (colours <= 1).all(), (
        "the lid's colours are outside 0..1")
    # sRGB's own surface is vivid; the grey the paint falls back to when a ray
    # misses would be a flat 0.5 everywhere
    spread = float(np.ptp(colours, axis=0).mean())
    assert spread > 0.3, (
        f"the lid's colours vary by only {spread:.3f} — it is not wearing the "
        f"other shape's colours, it is a flat fill")


def test_the_hover_is_short_enough_to_read_going_past():
    """Hovers stay under 200 characters; the long version is behind the ⓘ.

    Asked for in as many words, and this is the third control to be held to
    it.
    """
    text = pathlib.Path(__file__).resolve().parent / "gamut_app.py"
    body = text.read_text(encoding="utf-8")
    start = body.index('self._close_cut.setToolTip(')
    chunk = body[start:body.index(')', body.index('"', start) + 1) + 1]
    words = "".join(part for part in chunk.split('"')[1::2])
    assert 0 < len(words) <= 200, (
        f"the lid's hover is {len(words)} characters; a hover is read on the "
        f"way past and the long version belongs behind the ⓘ")
    assert "Needs" in words, (
        "the hover does not say what the control needs before it can act")
