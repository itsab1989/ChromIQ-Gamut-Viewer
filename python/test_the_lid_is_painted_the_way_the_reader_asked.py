"""The lid follows the reader's painting, like everything else on the picture.

`cap_over_the_cut` read `theirs.colors` from the day it was written and knew
nothing of `_paint_vertices`, so in four of the five paintings the lid was a
patch of TRUE COLOUR inside a shape painted some other way. Photographed at
his settings — his profile against sRGB, agree 45, Detail 20, both drawn as
surfaces — counting the pixels the lid changes against the same picture with
no lid at all, and how far out they are:

                        before                 after
    True colours          349 px, median  23     349, median 23
    One colour each     2,652        median  79   2,595   median 79
    By lightness        1,471        median  44     271   median 24
    By chroma           1,471        median 157     267   median 21
    In the accents      1,162        median  20     436   median 22

⚠ AND "ONE COLOUR EACH" BARELY MOVED BECAUSE WHAT IS LEFT THERE IS NOT THE
LID. On the ridge where the two gamuts converge the picture has 8,504 pink
pixels with NO LID AT ALL: the two SHAPES are a hair apart there and the
depth buffer picks between them. What the lid was adding is the alien
colour — 559 white-ish pixels with the old lid, 0 with this one.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"
_MIDDLE = np.array([50.0, 0.0, 0.0])


def _seam_of(faces):
    seen: dict = {}
    for tri in np.asarray(faces, int):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            k = (min(int(a), int(b)), max(int(a), int(b)))
            seen[k] = seen.get(k, 0) + 1
    return sorted({i for k, n in seen.items() if n == 1 for i in k})


@pytest.fixture(scope="module")
def pair():
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut
    paper_file = _DEMO / "Glossy-paper.ti3"
    if not paper_file.is_file():
        pytest.skip("no demo paper to cut")
    paper = build_gamut(ti3gamut.read_measurement(paper_file).lab,
                        input_space="lab")
    srgb = reference_gamut("sRGB", steps=24)
    gamuts = [("Glossy-paper", paper), ("sRGB", srgb)]
    ti3gamut._LAST_CUT = None
    ti3gamut._LAST_CAP = None
    out, _f, stands, _l = ti3gamut.recut_where_they_part(gamuts)
    return [("Glossy-paper", out[0][1]), ("sRGB", out[1][1])], stands


@pytest.mark.parametrize("painting", ("true", "solid", "lightness",
                                      "chroma", "accent"))
def test_the_lid_is_painted_from_the_other_shapes_painted_skin(pair, painting):
    """Every colour on the lid is one the OTHER shape's painted skin has.

    The lid IS that shape's surface, sampled where each ray leaves it, so its
    colours must come from that shape painted the way the reader asked — and
    from nowhere else. Checked as containment rather than by re-deriving the
    interpolation, so it cannot pass by repeating this module's own arithmetic.
    """
    import ti3gamut
    cut, stands = pair
    for which in (0, 1):
        ti3gamut._LAST_CAP = None
        got = ti3gamut.cap_over_the_cut(cut, stands, which, paint=painting)
        assert got is not None, f"no lid for shape {which}"
        corners, faces, colours = got
        used = sorted({int(i) for f in np.asarray(faces, int) for i in f})
        seam = set(_seam_of(faces))
        theirs = ti3gamut._painted_floats(cut[1 - which][1], painting,
                                          1 - which)
        lo, hi = theirs.min(axis=0), theirs.max(axis=0)
        body = np.asarray([colours[v] for v in used if v not in seam], float)
        assert len(body) > 100, "hardly any lid to look at"
        # A colour sampled ACROSS a triangle of the other shape's skin lies
        # inside the box its own corners span; one from anywhere else need not.
        assert (body >= lo - 1e-9).all() and (body <= hi + 1e-9).all(), (
            f"shape {which}'s lid paints colours the other shape's "
            f"{painting} skin never has")


@pytest.mark.parametrize("painting", ("solid", "chroma", "accent"))
def test_the_seam_takes_the_pieces_own_painted_colour(pair, painting):
    import ti3gamut
    cut, stands = pair
    for which in (0, 1):
        ti3gamut._LAST_CAP = None
        corners, faces, colours = ti3gamut.cap_over_the_cut(
            cut, stands, which, paint=painting)
        piece = cut[which][1]
        own = ti3gamut._painted_floats(piece, painting, which)
        # ⚠ MATCHED THROUGH THE UNTUCKED CORNERS, NOT BY NEAREST NEIGHBOUR.
        # The rim was tucked for the picture, so its drawn position is no
        # longer the piece's; asking which corner is CLOSEST picks a
        # neighbour instead, and the two disagree by 1 of 255 -- a failure
        # that reads as a colour fault and is a matching fault.
        from gamutview import close_the_cut
        other = cut[1 - which][1]
        pf = np.asarray(piece.faces, int)
        keep = np.asarray(stands[which], bool)[pf].all(axis=1)
        built_at, _skin, _built = close_the_cut(
            piece.vertices, pf[keep], other.vertices, other.faces, _MIDDLE,
            under=(piece.vertices, piece.faces))
        built_at = np.asarray(built_at, float)
        at = {}
        for n, p in enumerate(np.round(np.asarray(piece.vertices, float), 7)):
            at.setdefault((float(p[0]), float(p[1]), float(p[2])), n)
        sewn = 0
        for v in _seam_of(faces):
            q = np.round(built_at[v], 7)
            n = at.get((float(q[0]), float(q[1]), float(q[2])))
            if n is None:
                continue
            sewn += 1
            assert np.allclose(colours[v], own[n], atol=1e-9), (
                f"seam corner {v} is {colours[v]} where the piece painted "
                f"{painting} is {own[n]}")
        assert sewn > 100, "nothing was sewn, which looks like nothing to sew"


def test_asking_for_a_different_painting_does_not_hand_back_the_last_one(pair):
    """THE PAINTING IS PART OF THE QUESTION.

    The lid's colours are worked out inside `cap_over_the_cut`, so a store
    that remembers only the middle answers the next ask with the last ask's
    colours — and a fade is a redraw, so it would come back wrong on the very
    next drag.
    """
    import ti3gamut
    cut, stands = pair
    ti3gamut._LAST_CAP = None
    first = np.asarray(ti3gamut.cap_over_the_cut(cut, stands, 0,
                                                 paint="true")[2], float)
    second = np.asarray(ti3gamut.cap_over_the_cut(cut, stands, 0,
                                                  paint="solid")[2], float)
    again = np.asarray(ti3gamut.cap_over_the_cut(cut, stands, 0,
                                                 paint="true")[2], float)
    assert not np.allclose(first, second), (
        "asking for one flat colour handed back the true-coloured lid")
    assert np.allclose(first, again), (
        "asking twice for the same painting gave two different lids")


def test_a_colour_it_cannot_read_is_refused_not_guessed():
    """There is no shade of grey between reading a colour and not. A lid
    painted black by a silent failure looks like a painting fault."""
    import ti3gamut
    from references import reference_gamut
    srgb = reference_gamut("sRGB", steps=8)
    real = ti3gamut._paint_vertices
    ti3gamut._paint_vertices = lambda *a, **k: ["not a colour"] * len(srgb.vertices)
    try:
        with pytest.raises(ValueError, match="cannot read the colour"):
            ti3gamut._painted_floats(srgb, "solid", 0)
    finally:
        ti3gamut._paint_vertices = real
