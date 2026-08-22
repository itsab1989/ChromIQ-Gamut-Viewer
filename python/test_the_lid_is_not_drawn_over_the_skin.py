"""A lid is not drawn where the skin it closes is already there.

`TOO_CLOSE_TO_CLOSE` asks this of two shapes AS A WHOLE: a lid between
surfaces half a Lab apart cannot be told from the skin, so it is refused and
the tick dims. The same thing happens in PATCHES on shapes that are far apart
everywhere else — near the white point two gamuts converge — and there the
lid is laid a hair under a surface the picture is already drawing. The depth
buffer then picks between them facet by facet.

Measured on his own profile against sRGB at his own settings, counting the
pixels the lid changes against the same picture with no lid at all: a
herringbone of grey teeth, 1,875 pixels of it on one smooth pale slope, and
2,636 more along the seam. Nothing in any number could see it — the lid's
corners were ALL correctly under the skin, and only 0.01% of its area was
outside — because a surface half a Lab under another one is in the right
place and still unpaintable.

What is dropped is dropped from what is DRAWN, never from what
`close_the_cut` builds: the volume is read off that lid and a lid with holes
in it encloses nothing.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"
_MIDDLE = np.array([50.0, 0.0, 0.0])


def _edges_used(faces):
    seen: dict = {}
    for tri in np.asarray(faces, int):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            k = (min(int(a), int(b)), max(int(a), int(b)))
            seen[k] = seen.get(k, 0) + 1
    return seen


def _seam_of(faces):
    return {k for k, n in _edges_used(faces).items() if n == 1}


@pytest.fixture(scope="module")
def built_and_drawn():
    """The lid `close_the_cut` builds, and the part of it that is drawn."""
    import ti3gamut
    from gamutview import build_gamut, close_the_cut
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
    cut = [("Glossy-paper", out[0][1]), ("sRGB", out[1][1])]
    made = {}
    for which in (0, 1):
        piece = cut[which][1]
        other = cut[1 - which][1]
        faces = np.asarray(piece.faces, int)
        keep = np.asarray(stands[which], bool)[faces].all(axis=1)
        corners, _skin, built = close_the_cut(
            piece.vertices, faces[keep], other.vertices, other.faces,
            _MIDDLE, under=(piece.vertices, piece.faces))
        drawn = ti3gamut.cap_over_the_cut(cut, stands, which)
        assert drawn is not None, f"shape {which} got no lid at all"
        made[which] = (np.asarray(corners, float), np.asarray(built, int),
                       np.asarray(drawn[1], int), piece,
                       np.asarray(drawn[2], float))
    return made


@pytest.mark.parametrize("which", (0, 1))
def test_the_part_that_hugs_the_skin_is_not_drawn(built_and_drawn, which):
    """AND THERE HAS TO BE SOME OF IT. A rule that fires on nothing reads
    exactly like a rule that found nothing to fire on."""
    _corners, built, drawn, _piece, _paint = built_and_drawn[which]
    assert len(drawn) < len(built), (
        "nothing was held back at all, so this measures nothing")
    share = 1.0 - len(drawn) / len(built)
    assert share > 0.05, (
        f"only {100 * share:.2f}% of the lid held back — too little to be "
        f"the patches that were measured (21.0% and 13.3% on this pair)")
    assert share < 0.60, (
        f"{100 * share:.1f}% of the lid held back — that is not a patch, "
        f"that is the lid")


@pytest.mark.parametrize("which", (0, 1))
def test_everything_held_back_really_was_against_the_skin(built_and_drawn,
                                                          which):
    from gamutview import _rays_onto
    corners, built, drawn, piece, _paint = built_and_drawn[which]
    shy = float(np.linalg.norm(
        np.asarray(piece.vertices, float).max(axis=0)
        - np.asarray(piece.vertices, float).min(axis=0))) / 100.0
    kept = {tuple(sorted(map(int, t))) for t in drawn}
    gone = np.asarray([t for t in built
                       if tuple(sorted(map(int, t))) not in kept], int)
    assert len(gone), "nothing was held back"
    ray = corners - _MIDDLE
    reach = np.linalg.norm(ray, axis=1)
    skin = _rays_onto(piece.vertices, piece.faces, _MIDDLE)(ray)
    room = np.where(np.isfinite(skin), skin - reach, np.inf)
    worst = room[gone].max(axis=1)
    assert worst.max() < shy, (
        f"a triangle with {worst.max():.4f} Lab of room was held back, and "
        f"the rule only covers what is inside {shy:.4f}")


@pytest.mark.parametrize("which", (0, 1))
def test_the_seam_is_still_covered(built_and_drawn, which):
    """THE ONE THING THAT MAY NEVER BE DROPPED.

    The seam's corners sit ON the skin — room zero, by the construction that
    makes the lid meet the hole — so a rule about room takes the whole rim
    ring with it unless it is told not to. Measured without the guard: 413 of
    the printer's 1,134 seam edges and 291 of sRGB's 877 stopped being
    covered at all, leaving an opening up to 2.98 Lab deep along the very
    edge the lid exists to close.
    """
    _corners, built, drawn, _piece, _paint = built_and_drawn[which]
    was = _seam_of(built)
    assert len(was) > 100, "no seam to speak of, so this measures nothing"
    still = set(_edges_used(drawn))
    missing = was - still
    assert not missing, (
        f"{len(missing)} of the lid's {len(was)} seam edges are no longer "
        f"covered — the lid has come away from the hole's own edge")


@pytest.mark.parametrize("which", (0, 1))
def test_the_seam_is_painted_the_pieces_own_colour(built_and_drawn, which):
    """ONE POINT, ONE COLOUR.

    A rim corner IS the piece's corner, so the lid and the skin paint the same
    place. They did not agree about it — a median 5.3 of 255 apart on his
    profile and up to 41.3, and up to 53.3 on sRGB's own lid — and the seam is
    the one place the two surfaces must touch, so the depth buffer's tie there
    cannot be moved. Taking the disagreement away is what is left.

    ⚠ AND THE MATCH IS ON THE WELDED NUMBERS. `weld_by_position` hands back
    `np.unique(np.round(v, 7))`, so a rim corner is the piece's corner
    ROUNDED — as much as 8.4e-08 Lab from it. Matched on the raw numbers, 0
    of 299 corners were found and the rule painted nothing at all, which read
    exactly like a rule with nothing to paint.
    """
    corners, _built, drawn, piece, colours = built_and_drawn[which]
    where = {}
    for n, p in enumerate(np.round(np.asarray(piece.vertices, float), 7)):
        where.setdefault((float(p[0]), float(p[1]), float(p[2])), n)
    paint = np.asarray(piece.colors, float)
    seam = _seam_of(drawn)
    sewn = 0
    for v in sorted({i for e in seam for i in e}):
        p = np.round(corners[v], 7)
        n = where.get((float(p[0]), float(p[1]), float(p[2])))
        if n is None:                       # an edge the shy rule opened
            continue
        sewn += 1
        assert np.allclose(colours[v], paint[n], atol=1e-9), (
            f"the lid paints corner {v} {colours[v]} where the piece it is "
            f"sewn to paints it {paint[n]}")
    assert sewn > 100, (
        f"only {sewn} rim corners were found in the piece at all — the match "
        f"is not landing, and a rule that paints nothing looks like a rule "
        f"with nothing to paint")


def test_the_lid_is_lit_the_way_the_shape_it_copies_is():
    """The lid IS the other shape's skin. `_mesh` lights a skin facet by facet
    only when it was built as a hull, and the lid was flat either way: at his
    settings the herringbone counts 668 pixels flat against 257 smooth."""
    import inspect
    import ti3gamut
    src = inspect.getsource(ti3gamut)
    at = src.index("name=f\"{name} — where it is cut\"")
    before = src[:at]
    cut = before.rindex("go.Mesh3d(")
    assert 'flatshading=(getattr(gamuts[1 - i][1], "mode", "")' in before[cut:], (
        "the lid no longer takes its lighting from the shape it is cut from")
