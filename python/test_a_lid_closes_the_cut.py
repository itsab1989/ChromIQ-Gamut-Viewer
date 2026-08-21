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
    assert len(loops) == 1, f"the piece's rim is {len(loops)} chains, not one"
    rim = sorted({int(i) for i in loops[0]})
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
    both = np.vstack([capped["skin"], capped["lid"]])
    v = capped["corners"]
    a, b, c = (v[both[:, 0]] - _MIDDLE, v[both[:, 1]] - _MIDDLE,
               v[both[:, 2]] - _MIDDLE)
    s = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    # A shell: the piece's own skin faces out, the lid faces back in.
    assert (s[:len(capped["skin"])] > 0).all(), "the piece's skin faces inward"
    assert (s[len(capped["skin"]):] < 0).all(), (
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
