"""A cap over a cut must be a lid, not a second skin lying on the first.

Fade "where they agree" to nothing and what is left of a shape has a hole in
it; turned round, you look into the hole and the far wall is lit like an
outside, so it reads as torn. `close_the_cut` closes it with the piece of the
other shape that lies inside. Three things had to be true, and each one was
wrong first:

    THE SEAM IS SHARED, NOT MATCHED. The lid is the hole's own triangles slid
    down their own rays, so the rim corners do not move at all — measured, the
    furthest moves 0.000000000 Lab.

    ONLY THE SEAM IS SHARED. Sharing the inside corners too left every inside
    edge used FOUR times: 0 edges open, 496 used more than twice. Not a solid.

    AND THE LID MUST NOT SAG. A flat triangle strung between three corners on
    a curved floor hangs below it, so the lid encloses too much: 206,048 Lab³
    against a true 189,090, nine per cent fat, until sagging edges were split.

The number to beat is not this code's own: an independent construction,
written to a different design to argue with this one, measured 187,545.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"
_MIDDLE = np.array([50.0, 0.0, 0.0])


def _how_often_each_edge_is_used(faces):
    seen: dict = {}
    for tri in np.asarray(faces, int):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            k = (min(int(a), int(b)), max(int(a), int(b)))
            seen[k] = seen.get(k, 0) + 1
    return seen


@pytest.fixture(scope="module")
def capped():
    import ti3gamut
    from gamutview import build_gamut, close_the_cut, weld_by_position
    from references import reference_gamut
    paper_file = _DEMO / "Glossy-paper.ti3"
    if not paper_file.is_file():
        pytest.skip("no demo paper to cut")
    paper = build_gamut(ti3gamut.read_measurement(paper_file).lab,
                        input_space="lab")
    srgb = reference_gamut("sRGB", steps=24)
    out, _f, stands, _l = ti3gamut.recut_where_they_part(
        [("Glossy-paper", paper), ("sRGB", srgb)])
    cut = out[0][1]
    faces = np.asarray(cut.faces, int)
    keep = np.asarray(stands[0], bool)[faces].all(axis=1)
    kept, welded, _w = weld_by_position(cut.vertices, faces[keep])
    corners, skin, lid = close_the_cut(cut.vertices, faces[keep],
                                       srgb.vertices, srgb.faces, _MIDDLE,
                                       under=(paper.vertices, paper.faces))
    return dict(paper=paper, srgb=srgb, corners=corners, skin=skin, lid=lid,
                rim_before=kept, welded=welded)


def test_the_piece_really_does_arrive_with_a_hole(capped):
    # THE FAULT ITSELF: if the cut piece were already closed there would be
    # nothing to cap, and everything below would pass on an empty promise.
    open_edges = [k for k, n in
                  _how_often_each_edge_is_used(capped["welded"]).items() if n == 1]
    assert len(open_edges) > 50, (
        f"the standing piece arrives with only {len(open_edges)} open edges — "
        f"it is not a piece with a hole in it, so capping it tests nothing")


def test_the_lid_shuts_the_piece(capped):
    both = np.vstack([capped["skin"], capped["lid"]])
    used = _how_often_each_edge_is_used(both)
    once = [k for k, n in used.items() if n == 1]
    crowded = [k for k, n in used.items() if n > 2]
    assert not once, (
        f"{len(once)} edge(s) of the capped shape are used by one triangle "
        f"only: the lid leaves it open")
    assert not crowded, (
        f"{len(crowded)} edge(s) are used by more than two triangles: the lid "
        f"is lying on the piece rather than closing it")


def test_the_seam_is_the_pieces_own_corners_unmoved(capped):
    from gamutview import boundary_loops
    loops = boundary_loops(capped["welded"])
    assert loops, "the piece has no rim at all"
    for i, loop in enumerate(loops):
        assert loop[0] == loop[-1], f"the piece's rim {i} does not close"
    rim = sorted({int(i) for loop in loops for i in loop})
    moved = np.linalg.norm(capped["corners"][rim] - capped["rim_before"][rim],
                           axis=1)
    assert moved.max() == 0.0, (
        f"a seam corner moved {moved.max():.9f} Lab. The seam holds because "
        f"both pieces use the SAME corners; move one and it opens.")
    # and both pieces really do use them
    in_skin = set(np.asarray(capped["skin"], int).ravel().tolist())
    in_lid = set(np.asarray(capped["lid"], int).ravel().tolist())
    assert set(rim) <= in_skin & in_lid, (
        "some seam corners belong to only one of the two pieces")


def test_the_capped_shape_is_wound_one_way(capped):
    """Neighbours must agree — NOT "every cone from the middle points out".

    That was the first criterion here and it is wrong, for the same reason it
    was wrong about a dented shape: the standing piece is not star-shaped from
    the middle once it has an island in it, so a handful of its triangles
    genuinely have their cone the other way. Two of the lid's 32,948 do.
    Consistency is about neighbours, and the total is what says which way out
    is.
    """
    both = np.vstack([capped["skin"], capped["lid"]])
    v = capped["corners"]
    seen: dict = {}
    for tri in both:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            seen.setdefault((min(int(a), int(b)), max(int(a), int(b))),
                            []).append((int(a), int(b)))
    clash = [k for k, walks in seen.items()
             if len(walks) == 2 and walks[0] == walks[1]]
    assert not clash, (
        f"{len(clash)} edge(s) of the capped shape are walked the same way "
        f"round by both their triangles")
    a, b, c = (v[both[:, 0]] - _MIDDLE, v[both[:, 1]] - _MIDDLE,
               v[both[:, 2]] - _MIDDLE)
    s = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    assert s[:len(capped["skin"])].sum() > 0, "the piece's skin faces inward"
    assert s[len(capped["skin"]):].sum() < 0, (
        "the lid does not face back into the shell, so the two double rather "
        "than close")


def test_the_capped_shape_holds_the_gap_it_should(capped):
    from gamutview import _where_the_ray_leaves
    rng = np.random.default_rng(7)
    u = rng.normal(size=(20000, 3))
    u /= np.linalg.norm(u, axis=1)[:, None]
    paper, srgb = capped["paper"], capped["srgb"]
    rp = _where_the_ray_leaves(paper.vertices, paper.faces, _MIDDLE, u)
    rs = _where_the_ray_leaves(srgb.vertices, srgb.faces, _MIDDLE, u)
    alive = np.isfinite(rp) & np.isfinite(rs)
    rp, rs = rp[alive], rs[alive]
    stands = rp > rs
    dice = ((4 * np.pi / alive.sum())
            * ((rp[stands] ** 3 - rs[stands] ** 3) / 3).sum())
    both = np.vstack([capped["skin"], capped["lid"]])
    v = capped["corners"]
    a, b, c = (v[both[:, 0]] - _MIDDLE, v[both[:, 1]] - _MIDDLE,
               v[both[:, 2]] - _MIDDLE)
    held = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
    assert abs(held - dice) < 0.03 * dice, (
        f"the capped shape holds {held:,.0f} Lab³ where casting rays through "
        f"both shapes says the paper stands out by {dice:,.0f}. Unsplit, the "
        f"sagging lid held 206,048 against 189,090.")


def test_the_lid_stays_under_the_skin_it_closes(capped):
    from gamutview import _where_the_ray_leaves
    v = capped["corners"]
    lid_only = np.setdiff1d(np.unique(np.asarray(capped["lid"], int)),
                            np.unique(np.asarray(capped["skin"], int)))
    assert len(lid_only) > 100, "the lid has almost no corners of its own"
    rays = v[lid_only] - _MIDDLE
    mine = np.linalg.norm(rays, axis=1)
    paper = capped["paper"]
    roof = _where_the_ray_leaves(paper.vertices, paper.faces, _MIDDLE, rays)
    out = np.isfinite(roof) & (mine > roof + 1e-6)
    assert not out.any(), (
        f"{int(out.sum())} lid corner(s) poke out through the skin they are "
        f"meant to close, the worst by {float((mine - roof)[out].max()):.2f} Lab")


# ---------------------------------------------------------------------------
# What a hostile reading of this code broke on 2026-08-21. Every one of these
# passed every test above while being wrong by hundreds of per cent.
# ---------------------------------------------------------------------------


def _held(corners, *pieces):
    both = np.vstack([p for p in pieces if len(p)])
    a, b, c = (corners[both[:, 0]] - _MIDDLE, corners[both[:, 1]] - _MIDDLE,
               corners[both[:, 2]] - _MIDDLE)
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def _stands_out_by(a, b, seed=5, rays=60000):
    """What the first shape reaches past the second, by casting rays."""
    from gamutview import _where_the_ray_leaves
    rng = np.random.default_rng(seed)
    u = rng.normal(size=(rays, 3))
    u /= np.linalg.norm(u, axis=1)[:, None]
    ra = _where_the_ray_leaves(a.vertices, a.faces, _MIDDLE, u)
    rb = _where_the_ray_leaves(b.vertices, b.faces, _MIDDLE, u)
    ok = np.isfinite(ra) & np.isfinite(rb)
    ra, rb = ra[ok], rb[ok]
    out = ra > rb
    return (4 * np.pi / ok.sum()) * ((ra[out] ** 3 - rb[out] ** 3) / 3).sum()


def _cap(a, b, which):
    import ti3gamut
    from gamutview import close_the_cut
    out, _f, stands, _l = ti3gamut.recut_where_they_part([("a", a), ("b", b)])
    cut = out[which][1]
    faces = np.asarray(cut.faces, int)
    keep = np.asarray(stands[which], bool)[faces].all(axis=1)
    other = b if which == 0 else a
    under = (a.vertices, a.faces) if which == 0 else (b.vertices, b.faces)
    return close_the_cut(cut.vertices, faces[keep], other.vertices,
                         other.faces, _MIDDLE, under=under)


@pytest.fixture(scope="module")
def papers():
    import ti3gamut
    from gamutview import build_gamut
    made = {}
    for stem in ("Glossy-paper", "Matte-paper", "Glossy-paper-months-later"):
        f = _DEMO / f"{stem}.ti3"
        if not f.is_file():
            pytest.skip(f"no {stem} to measure")
        made[stem] = build_gamut(ti3gamut.read_measurement(f).lab,
                                 input_space="lab")
    return made


def test_a_shape_with_nothing_cut_away_gets_no_lid(papers):
    """Matte-paper lies wholly inside Glossy-paper, so there is no hole.

    Capping it anyway built a SECOND closed shell inside the first. Neither
    shares an edge with the other, so every structural check above passed —
    no edge open, none used more than twice, each wound outward on its own —
    and the volume came out as skin PLUS lid: 1,341,108 against a true
    180,432. Six hundred and forty-three per cent.
    """
    glossy, matte = papers["Glossy-paper"], papers["Matte-paper"]
    from gamutview import _where_the_ray_leaves
    rays = np.asarray(matte.vertices, float) - _MIDDLE
    inside = _where_the_ray_leaves(glossy.vertices, glossy.faces, _MIDDLE, rays)
    outside = int((np.linalg.norm(rays, axis=1) > inside + 1e-9).sum())
    assert outside == 0, (
        f"{outside} of Matte-paper's corners now lie outside Glossy-paper — "
        f"the two are no longer nested, so this proves nothing")
    corners, skin, lid = _cap(glossy, matte, 0)
    assert len(lid) == 0, (
        f"a piece with no rim was given a lid of {len(lid)} triangles")
    held = _held(corners, skin, lid)
    assert abs(held - glossy.volume) < 0.02 * glossy.volume, (
        f"with nothing cut away the answer should be the shape itself, "
        f"{glossy.volume:,.0f}; it is {held:,.0f}")


def test_two_measurements_of_one_paper_are_not_wildly_over(papers):
    """The application's headline comparison, and the one it was worst on.

    The sag tolerance used to be a flat 0.25 Lab. That is a fine tolerance
    between two shapes about 20 Lab apart and a useless one between two that
    are 2 Lab apart, so the lid's flat triangles hung across most of the gap:
    46.9% and 97.8% too much, with no structural symptom whatever.
    """
    a, b = papers["Glossy-paper"], papers["Glossy-paper-months-later"]
    for which, first, second in ((0, a, b), (1, b, a)):
        corners, skin, lid = _cap(a, b, which)
        assert len(lid) > 0, "nothing was capped, so nothing is being tested"
        held = _held(corners, skin, lid)
        truth = _stands_out_by(first, second)
        assert truth > 1000, (
            f"the two measurements differ by only {truth:,.0f} — too little "
            f"to tell a good lid from a bad one")
        assert abs(held - truth) < 0.05 * truth, (
            f"piece {which}: the capped shape holds {held:,.0f} where casting "
            f"rays says {truth:,.0f} ({100 * (held - truth) / truth:+.1f}%)")


def test_it_refuses_a_middle_the_other_shape_does_not_surround():
    """A gamut of only light patches does not contain (50, 0, 0).

    Asked to cap against it, this used to return 126 + 3,232 triangles with
    13 of the piece's own facing inward and still call itself closed.
    """
    import ti3gamut
    from gamutview import build_gamut, covers_the_sphere_once
    f = _DEMO / "Glossy-paper.ti3"
    if not f.is_file():
        pytest.skip("no demo paper")
    lab = np.asarray(ti3gamut.read_measurement(f).lab, float)
    whole = build_gamut(lab, input_space="lab")
    light = build_gamut(lab[lab[:, 0] > 55.0], input_space="lab")
    covered = covers_the_sphere_once(light.vertices, light.faces, _MIDDLE)
    assert abs(covered - 4 * np.pi) > 1e-2, (
        f"the light-only shape covers {covered:.4f} of the view, which is a "
        f"full one — it does surround the middle after all, so there is "
        f"nothing here to refuse")
    with pytest.raises(ValueError, match="covers"):
        _cap(whole, light, 0)


def test_the_quick_caster_answers_exactly_as_the_slow_one_does(papers):
    """The index may only ever offer too MANY candidates, never too few.

    A bounding box drawn round a triangle's three corners is too small — the
    arc between two corners bulges further from the equator than either end —
    and with one the paper's own facets answered 4,000 rays differently.
    """
    from gamutview import _rays_onto, _where_the_ray_leaves
    from references import reference_gamut
    rng = np.random.default_rng(1)
    u = rng.normal(size=(4000, 3))
    u /= np.linalg.norm(u, axis=1)[:, None]
    shapes = dict(papers)
    shapes["sRGB"] = reference_gamut("sRGB", steps=24)
    for name, g in shapes.items():
        slow = _where_the_ray_leaves(g.vertices, g.faces, _MIDDLE, u)
        quick = _rays_onto(g.vertices, g.faces, _MIDDLE)(u)
        assert np.isfinite(slow).sum() > len(u) // 2, (
            f"{name}: the slow caster only answered "
            f"{int(np.isfinite(slow).sum())} of {len(u)} rays")
        wrong = int((~np.isclose(slow, quick, equal_nan=True)).sum())
        assert wrong == 0, (
            f"{name}: the index answers {wrong} of {len(u)} rays differently")


def test_the_lid_cannot_run_away(papers):
    """It is a thing to LOOK at, and it has to be carried in a saved page.

    The tolerance is a share of how far the lid falls, and two measurements of
    one paper lie about a tenth of a Lab apart over most of their shared
    surface — so any share of that is microscopic and the splitting runs away:
    48,666 lid triangles at a hundredth of the drop, 11,840 at a tenth, for a
    volume nobody reads off the lid. The numbers beside the picture come from
    the SHAPES and never from here.

    A ceiling checked once a round is not a ceiling: splitting an edge adds up
    to two triangles to every face using it, so a round begun at 7,999 ended
    at 32,000. The worst-sagging edges are taken first, up to what fits.
    """
    from references import reference_gamut
    biggest = 0
    for name, other in (("sRGB", reference_gamut("sRGB", steps=24)),
                        ("Adobe RGB (1998)",
                         reference_gamut("Adobe RGB (1998)", steps=24)),
                        ("months later", papers["Glossy-paper-months-later"])):
        corners, skin, lid = _cap(papers["Glossy-paper"], other, 0)
        assert len(lid) > len(skin), (
            f"against {name} the lid is no finer than the piece it caps, so "
            f"the refinement is not running at all and this proves nothing")
        # ⚠ WHAT IS BOUNDED IS WHAT IS ADDED. The lid begins as a copy of
        # the piece it caps — they share a rim corner for corner — so it can
        # never be smaller than that piece. At the highest Detail the other
        # shape's piece is already 15,886 triangles and its lid is a copy with
        # nothing added at all. "No lid passes 8,000" was claimed and is false.
        assert len(lid) - len(skin) <= 8000, (
            f"against {name} the lid adds {len(lid) - len(skin):,} triangles "
            f"to a piece of {len(skin):,}; the budget is 8,000 and a page has "
            f"to carry every one of them")
        biggest = max(biggest, len(lid))
    assert biggest >= 4000, (
        f"the biggest lid is only {biggest:,} triangles — nothing came near "
        f"the ceiling, so this is not testing that it holds")
    # ⚠ AND THE ORDINARY CASE *DOES* LIVE AT THE CEILING NOW, which an
    # earlier version of this test forbade. That rule was mine and its premise
    # went when the lid was set clear of the other shape's surface: the floor
    # it follows is no longer that shape exactly, so it takes more splitting
    # to follow. Keeping the rule would have meant coarsening the tolerance,
    # and the NARROW pairs cannot afford that — two measurements of one paper
    # go from +0.96% of a ray count to +26.76% as the tolerance is loosened.
    # What matters is that it is BOUNDED and lands in the right place, and
    # both of those are checked here and in the volume test above.
    _c, _s, lid = _cap(papers["Glossy-paper"],
                       reference_gamut("sRGB", steps=24), 0)
    assert 0 < len(lid) <= 8000, (
        f"the paper against sRGB needs {len(lid):,} lid triangles")


# ---------------------------------------------------------------------------
# What a hostile reading found on 2026-08-22, from the shapes in
# scripts/make_awkward_shapes.py. The guard above asks the coverage question of
# the shape being capped AGAINST and stopped there; capping a shape the middle
# is OUTSIDE went unrefused and produced a lid in the wrong place.
# ---------------------------------------------------------------------------


def _awkward(tmp_path_factory, name):
    import sys as _sys
    import numpy as _np
    import ti3gamut as _t
    from gamutview import build_gamut as _b
    _sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                            / "scripts"))
    import make_awkward_shapes as _m
    folder = tmp_path_factory.mktemp("awkward")
    _m.make(folder)
    return _b(_np.asarray(_t.read_measurement(folder / f"{name}.ti3").lab,
                          float), input_space="lab")


@pytest.fixture(scope="module")
def off_to_one_side(tmp_path_factory):
    """A ball, and a small shape beside it that the middle is outside of."""
    return (_awkward(tmp_path_factory, "ball"),
            _awkward(tmp_path_factory, "ball-just-poking"))


def test_a_shape_the_middle_is_outside_is_refused(off_to_one_side):
    """It is not capped, and not capped WRONGLY, which is what happened.

    Unrefused, this returned 7,999 triangles that looked like a lid and were a
    duplicate of the piece's own front skin: 0.000 Lab from its own surface,
    5.918 Lab from the shape it was supposedly cut from, painted with colours
    sampled over there. A picture nobody could tell was wrong.
    """
    import ti3gamut
    from gamutview import covers_the_sphere_once
    ball, sliver = off_to_one_side
    covered = covers_the_sphere_once(sliver.vertices, sliver.faces, _MIDDLE)
    assert covered < 4 * np.pi - 1e-2, (
        "this shape is meant to be one the middle is outside; if it now wraps "
        "the middle the case has evaporated and this test proves nothing")
    gamuts = [("ball", ball), ("sliver", sliver)]
    out, _f, stands, _l = ti3gamut.recut_where_they_part(gamuts)
    cut = [("ball", out[0][1]), ("sliver", out[1][1])]
    assert ti3gamut.cap_over_the_cut(cut, stands, 1) is None, (
        "a shape the middle is outside was capped anyway")


def test_the_ordinary_pairs_still_get_their_lids(tmp_path_factory):
    """The other half of the rule: it must refuse ONLY the broken case.

    Dimming or refusing too widely is how the drift marker's tick was broken;
    these are the pairs that must keep working.
    """
    import ti3gamut
    # ⚠ NOT ball-with-a-dent + ball. Those two lie on top of each other
    # everywhere but the dent -- 0.000 Lab apart at the median -- so a lid
    # between them is refused now, and rightly: every corner of it landed
    # within 0.05 Lab of the skin, which the picture shows as hatching. See
    # test_two_shapes_that_all_but_coincide_are_refused below.
    for one, two in (("two-lobes", "ball"), ("pancake", "column")):
        a = _awkward(tmp_path_factory, one)
        b = _awkward(tmp_path_factory, two)
        gamuts = [(one, a), (two, b)]
        out, _f, stands, _l = ti3gamut.recut_where_they_part(gamuts)
        cut = [(one, out[0][1]), (two, out[1][1])]
        made = [ti3gamut.cap_over_the_cut(cut, stands, i) for i in (0, 1)]
        assert any(m is not None for m in made), (
            f"{one} + {two}: neither shape got a lid, and both should")


def test_two_shapes_that_all_but_coincide_are_refused(tmp_path_factory):
    """A lid you cannot tell from the skin is a lid that only speckles.

    DRIVEN AND PHOTOGRAPHED. Two readings of one paper are 0.535 Lab apart,
    and the picture came back hatched with diagonal stripes wherever the lid
    lay on the surface -- 32,308 pixels of a 1600x1050 window changed when the
    tick went on, none of them for a reason a reader would want. Holding the
    lid 0.05 Lab clear thinned the stripes to 17,803 and left them there;
    there is no room to push harder, because a flat step was measured at
    +61.7% on what the lid encloses.

    A dented ball against a plain one is the extreme of the same thing: they
    are 0.000 Lab apart at the median.
    """
    import ti3gamut
    a = _awkward(tmp_path_factory, "ball-with-a-dent")
    b = _awkward(tmp_path_factory, "ball")
    assert ti3gamut.how_far_apart(a, b, _MIDDLE) < ti3gamut.TOO_CLOSE_TO_CLOSE
    gamuts = [("dent", a), ("ball", b)]
    out, _f, stands, _l = ti3gamut.recut_where_they_part(gamuts)
    cut = [("dent", out[0][1]), ("ball", out[1][1])]
    assert all(ti3gamut.cap_over_the_cut(cut, stands, i) is None for i in (0, 1))
    assert ti3gamut.which_shapes_could_be_capped(gamuts) == [False, False], (
        "the tick would promise a lid the drawing refuses to make")
