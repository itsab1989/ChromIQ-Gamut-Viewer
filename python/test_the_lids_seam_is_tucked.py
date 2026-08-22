"""The lid's drawn rim is tucked a hair under the one it is sewn to.

THE TIE THAT COULD NOT BE MOVED. The lid and the piece meet at a fold along
the seam, and they meet BY BEING THE SAME CORNERS — which is what makes the
lid close the hole and what leaves the two surfaces at exactly the same depth
all along that line. Seen near edge-on the picture has nothing to choose
between them and chooses in bites: a beaded thread along the seam, and where
the two shapes converge a herringbone of teeth on a smooth slope. Every
number said the lid was in the right place, and it was: no corner above the
skin, 0.01% of the area through it by 0.072 Lab. Only the pictures showed it.

MEASURED WITH TWO NUMBERS, because the obvious one is minimised by drawing no
lid at all — OUTSIDE, what the lid changes at his camera where it ought to be
invisible, and INSIDE, what it closes when you look into the opening:

    tucked by       OUTSIDE     INSIDE
    nothing           2,847     77,467
    diag/800          1,161     75,756
    DIAG/400            349     74,475
    diag/200            114     73,582

⚠ AND ITS PREDECESSOR SCORED WELL AND WAS WORSE. A rule that withheld lid
triangles hugging the skin took 97.1% of one lid on sRGB against Display P3 —
two reference spaces, the default space, the default Detail — and left a
picture indistinguishable from having no lid. `test_no_pair_has_its_lid_taken
_away` is here so that cannot come back quietly.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"
_MIDDLE = np.array([50.0, 0.0, 0.0])


def _a_share_of_the_shape(piece):
    return float(np.linalg.norm(
        np.asarray(piece.vertices, float).max(axis=0)
        - np.asarray(piece.vertices, float).min(axis=0))) / 400.0


def _a_twentieth_of_the_lid(corners, faces):
    """The tuck that opens a slit of a twentieth of the lid's own area."""
    v, f = np.asarray(corners, float), np.asarray(faces, int)
    seen: dict = {}
    for tri in f:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            k = (min(int(a), int(b)), max(int(a), int(b)))
            seen[k] = seen.get(k, 0) + 1
    rim = [k for k, n in seen.items() if n == 1]
    perimeter = sum(float(np.linalg.norm(v[a] - v[b])) for a, b in rim)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area = float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())
    return 0.05 * area / max(1e-9, perimeter)


def _seam_of(faces):
    seen: dict = {}
    for tri in np.asarray(faces, int):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            k = (min(int(a), int(b)), max(int(a), int(b)))
            seen[k] = seen.get(k, 0) + 1
    return sorted({i for k, n in seen.items() if n == 1 for i in k})


@pytest.fixture(scope="module")
def built_and_drawn():
    """The lid `close_the_cut` builds, and the copy that goes to the picture.

    The two share a numbering — `cap_over_the_cut` copies the array — so they
    can be compared corner for corner rather than by position, which is what
    makes "only the seam moved" a statement about every other corner too.
    """
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
                       np.asarray(drawn[0], float), np.asarray(drawn[1], int),
                       np.asarray(drawn[2], float), piece)
    return made


@pytest.mark.parametrize("which", (0, 1))
def test_every_seam_corner_is_tucked_and_by_how_much(built_and_drawn, which):
    built_at, built, drawn_at, _drawn, _colours, piece = built_and_drawn[which]
    # ⚠ AND CAPPED BY THE LID'S OWN SIZE. The tuck opens a slit around the
    # whole rim -- perimeter times tuck -- and half a Lab of the SHAPE is the
    # wrong size for a lid that is a sliver of it: measured on sRGB against
    # Display P3, a slit of 204.1 Lab² around a lid of 25.8, which is 790% of
    # the thing it was meant to help.
    want = min(_a_share_of_the_shape(piece), _a_twentieth_of_the_lid(built_at,
                                                                     built))
    seam = _seam_of(built)
    assert len(seam) > 100, "no seam to speak of, so this measures nothing"
    was = np.linalg.norm(built_at[seam] - _MIDDLE, axis=1)
    now = np.linalg.norm(drawn_at[seam] - _MIDDLE, axis=1)
    moved = was - now
    assert np.allclose(moved, want, atol=1e-9), (
        f"the seam moved by {moved.min():.6f}..{moved.max():.6f} Lab where "
        f"{want:.6f} was asked for")
    # AND STRAIGHT DOWN ITS OWN RAY, not sideways: the lid must still be the
    # same set of directions as the hole, or it is a different surface.
    #
    # ⚠ ASKED OF THE MOVE, NOT OF THE COSINE. A hostile review pointed out
    # that the cosine between the two POSITIONS only notices a slide that
    # also changes the radius -- and the magnitude check above catches those
    # already, so the cosine could never be the thing that fired. What has to
    # be zero is the part of the MOVE that is across the ray.
    ray = built_at[seam] - _MIDDLE
    unit = ray / np.linalg.norm(ray, axis=1)[:, None]
    move = drawn_at[seam] - built_at[seam]
    across = move - unit * np.einsum("ij,ij->i", move, unit)[:, None]
    assert np.abs(across).max() < 1e-9, (
        f"a seam corner slid across its ray by {np.abs(across).max():.3e} Lab")


@pytest.mark.parametrize("which", (0, 1))
def test_nothing_but_the_seam_moved(built_and_drawn, which):
    """A LID THAT MOVED EVERYWHERE IS A DIFFERENT LID. Only the rim is in two
    places; every other corner the picture draws is the one that was built."""
    built_at, built, drawn_at, _drawn, _colours, _piece = built_and_drawn[which]
    seam = set(_seam_of(built))
    inside = np.asarray([i for i in range(len(built_at)) if i not in seam], int)
    assert len(inside) > 100, "no inside corners, so this measures nothing"
    assert np.allclose(built_at[inside], drawn_at[inside], atol=0.0), (
        "a corner that is not on the seam was moved for the picture")


@pytest.mark.parametrize("which", (0, 1))
def test_what_is_built_keeps_the_pieces_own_corners(built_and_drawn, which):
    """THE TUCK IS FOR THE PICTURE AND NOTHING ELSE. `close_the_cut` still
    returns the piece's corners unmoved — every closure check in
    `test_a_lid_closes_the_cut.py` rests on that, and so would any volume."""
    built_at, built, _drawn_at, _drawn, _colours, piece = built_and_drawn[which]
    at = {}
    for n, p in enumerate(np.round(np.asarray(piece.vertices, float), 7)):
        at.setdefault((float(p[0]), float(p[1]), float(p[2])), n)
    seam = _seam_of(built)
    found = 0
    for v in seam:
        p = np.round(built_at[v], 7)
        if at.get((float(p[0]), float(p[1]), float(p[2]))) is not None:
            found += 1
    assert found == len(seam), (
        f"{len(seam) - found} of {len(seam)} built seam corners are not the "
        f"piece's own corners any more")


@pytest.mark.parametrize("which", (0, 1))
def test_the_seam_is_painted_the_pieces_own_colour(built_and_drawn, which):
    """ONE POINT, ONE COLOUR — in true colours, which is the one mode the lid
    has ever known. See the note in `cap_over_the_cut`: `_paint_vertices` can
    put the shape in one flat colour or an accent family, and neither the lid
    nor this sewing knows, so the sewn seam is 197.5 of 255 out there. That
    is older than the sewing and is the queue's next job.

    ⚠ MATCHED ON THE WELDED NUMBERS. `weld_by_position` returns
    `np.unique(np.round(v, 7))`, so a rim corner is the piece's corner
    ROUNDED. Matched on the raw numbers, 0 of 299 were found and the picture
    came back byte-identical.
    """
    built_at, built, _drawn_at, _drawn, colours, piece = built_and_drawn[which]
    at = {}
    for n, p in enumerate(np.round(np.asarray(piece.vertices, float), 7)):
        at.setdefault((float(p[0]), float(p[1]), float(p[2])), n)
    own = np.asarray(piece.colors, float)
    sewn = 0
    for v in _seam_of(built):
        p = np.round(built_at[v], 7)
        n = at.get((float(p[0]), float(p[1]), float(p[2])))
        assert n is not None, f"seam corner {v} is not one of the piece's"
        sewn += 1
        assert np.allclose(colours[v], own[n], atol=1e-9), (
            f"the lid paints corner {v} {colours[v]} where the piece it is "
            f"sewn to paints it {own[n]}")
    assert sewn > 100, "nothing was sewn, and that looks like nothing to sew"


def test_no_pair_has_its_lid_taken_away():
    """WHAT IS DRAWN IS WHAT WAS BUILT.

    The rule this replaced withheld triangles that hugged the skin. On sRGB
    against Display P3 — the default space, the default Detail — it withheld
    97.1% of one lid and the picture became indistinguishable from having no
    lid at all; 103 configurations were flagged, the worst at 98.06%. Nothing
    may quietly take a lid away again.
    """
    import ti3gamut
    from gamutview import close_the_cut
    from references import reference_gamut
    pairs = [("sRGB", "Display P3"), ("sRGB", "Adobe RGB (1998)"),
             ("Display P3", "Rec.2020")]
    looked = 0
    for a_name, b_name in pairs:
        a = reference_gamut(a_name, steps=20)
        b = reference_gamut(b_name, steps=20)
        gamuts = [(a_name, a), (b_name, b)]
        ti3gamut._LAST_CUT = None
        ti3gamut._LAST_CAP = None
        out, _f, stands, _l = ti3gamut.recut_where_they_part(gamuts)
        cut = [(a_name, out[0][1]), (b_name, out[1][1])]
        for which in (0, 1):
            piece = cut[which][1]
            other = cut[1 - which][1]
            faces = np.asarray(piece.faces, int)
            keep = np.asarray(stands[which], bool)[faces].all(axis=1)
            if keep.sum() < 4:
                continue
            try:
                _c, _s, built = close_the_cut(
                    piece.vertices, faces[keep], other.vertices, other.faces,
                    _MIDDLE, under=(piece.vertices, piece.faces))
            except ValueError:
                continue
            got = ti3gamut.cap_over_the_cut(cut, stands, which)
            if got is None or not len(built):
                continue
            looked += 1
            assert len(got[1]) == len(built), (
                f"{a_name} vs {b_name}, {cut[which][0]}'s lid: "
                f"{len(built) - len(got[1])} of {len(built)} triangles "
                f"({100 * (1 - len(got[1]) / len(built)):.1f}%) are built and "
                f"not drawn")
    assert looked >= 4, f"only {looked} lids were looked at, which proves little"


def test_the_lid_is_lit_the_way_the_shape_it_copies_is():
    """ASKED OF THE FIGURE, NOT OF THE SOURCE.

    The check this replaced asserted on a substring of `ti3gamut`'s own text,
    and the substring stopped before the comparison: inverting the rule to
    `!= "hull"` — the lid lit the exact opposite way from the shape it copies,
    the one thing the check is named for — left it passing. An assertion on
    source text cannot test behaviour, and that one demonstrably did not.

    A hull-built shape is lit facet by facet and a device-built one smoothly
    (`_mesh`), and the lid IS the OTHER shape's skin, so it must follow that
    shape and not its own.
    """
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut
    paper_file = _DEMO / "Glossy-paper.ti3"
    if not paper_file.is_file():
        pytest.skip("no demo paper to cut")
    paper = build_gamut(ti3gamut.read_measurement(paper_file).lab,
                        input_space="lab")
    import dataclasses
    seen = {}
    # A GAMUT IS FROZEN, so the two modes are two objects. `device-cube` is
    # what a reference space really carries; the rule asks only whether it is
    # "hull", so any other name stands for the smooth-lit case.
    for their_mode in ("device-cube", "hull"):
        srgb = dataclasses.replace(reference_gamut("sRGB", steps=24),
                                   mode=their_mode)
        ti3gamut._LAST_CUT = None
        ti3gamut._LAST_CAP = None
        fig = ti3gamut.build_figure(
            [("Glossy-paper", paper), ("sRGB", srgb)], "lit",
            agree=0.45, split=True, cap=True,
            styles=["solid", "solid"], camera={"eye": dict(x=1, y=1, z=1)})
        lids = [t for t in fig.data
                if "where it is cut" in str(getattr(t, "name", ""))]
        assert lids, f"no lid was drawn at all with the other shape {their_mode}"
        # THE PAPER'S OWN LID is the one cut from sRGB, so it is the one that
        # must follow sRGB's rule.
        theirs = [t for t in lids if str(t.name).startswith("Glossy-paper")]
        assert theirs, "the paper's lid is missing"
        seen[their_mode] = bool(theirs[0].flatshading)
    assert seen == {"device-cube": False, "hull": True}, (
        f"the lid lights itself by the wrong shape's rule: {seen}")


def test_the_tuck_never_takes_more_than_a_twentieth_of_the_lid():
    """A THRESHOLD THAT IS A SHARE OF THE SHAPE, APPLIED TO A SLIVER OF IT.

    The tuck opens a slit around the whole rim — perimeter times tuck. Half a
    Lab of the SHAPE is the right size for a lid that is a fair part of it and
    the wrong size for a lid that is not: measured on sRGB against Display P3,
    a slit of 204.1 Lab² around a lid whose whole area is 25.8 — 790% of the
    thing it was meant to help. Exactly the mistake reverted in a1c6111, in a
    different place, which is why it is pinned here across pairs rather than
    on the one pair the rest of this file uses.
    """
    import ti3gamut
    from gamutview import close_the_cut
    from references import reference_gamut
    pairs = [("sRGB", "Display P3"), ("sRGB", "Adobe RGB (1998)"),
             ("Display P3", "Rec.2020")]
    looked = capped = 0
    for a_name, b_name in pairs:
        gamuts = [(a_name, reference_gamut(a_name, steps=20)),
                  (b_name, reference_gamut(b_name, steps=20))]
        ti3gamut._LAST_CUT = None
        ti3gamut._LAST_CAP = None
        out, _f, stands, _l = ti3gamut.recut_where_they_part(gamuts)
        cut = [(a_name, out[0][1]), (b_name, out[1][1])]
        for which in (0, 1):
            piece = cut[which][1]
            other = cut[1 - which][1]
            faces = np.asarray(piece.faces, int)
            keep = np.asarray(stands[which], bool)[faces].all(axis=1)
            if keep.sum() < 4:
                continue
            try:
                built_at, _skin, built = close_the_cut(
                    piece.vertices, faces[keep], other.vertices, other.faces,
                    _MIDDLE, under=(piece.vertices, piece.faces))
            except ValueError:
                continue
            got = ti3gamut.cap_over_the_cut(cut, stands, which)
            if got is None or not len(built):
                continue
            built_at = np.asarray(built_at, float)
            drawn_at = np.asarray(got[0], float)
            seam = _seam_of(built)
            moved = float(np.median(np.linalg.norm(
                built_at[seam] - drawn_at[seam], axis=1)))
            v, f = built_at, np.asarray(built, int)
            seen: dict = {}
            for tri in f:
                for a, b in ((tri[0], tri[1]), (tri[1], tri[2]),
                             (tri[2], tri[0])):
                    k = (min(int(a), int(b)), max(int(a), int(b)))
                    seen[k] = seen.get(k, 0) + 1
            rim = [k for k, n in seen.items() if n == 1]
            perimeter = sum(float(np.linalg.norm(v[a] - v[b])) for a, b in rim)
            p0, p1, p2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
            area = float(0.5 * np.linalg.norm(
                np.cross(p1 - p0, p2 - p0), axis=1).sum())
            share = perimeter * moved / max(1e-9, area)
            looked += 1
            if moved < _a_share_of_the_shape(piece) - 1e-9:
                capped += 1
            assert share <= 0.05 + 1e-6, (
                f"{a_name} vs {b_name}, {cut[which][0]}'s lid: the tuck opens "
                f"a slit of {100 * share:.1f}% of the lid's own area")
    assert looked >= 4, f"only {looked} lids were looked at, which proves little"
    assert capped >= 2, (
        f"only {capped} of {looked} lids were held back by the cap at all — "
        f"a cap that never fires cannot be seen to work")
