"""Two thirds of a cut mesh's "rim" is cracks, and reading it cost a day.

`split_at_crossing` makes each crossing point FOUR times — twice for the odd
corner's side of a straddling triangle and twice for the pair's — and welds
none of them. The picture is right either way, because coincident corners draw
identically. The MESH is full of cracks, and a crack looks exactly like a
boundary.

Measured on a real paper cut against sRGB, the standing piece:

    as the cut leaves it   354 boundary edges over 290 corners, with corners
                           where 4, 6, 8, 10, 12 and even SIXTEEN edges meet
    welded by position     118 edges over 118 corners, every one with exactly
                           two: ONE closed loop

Everything I measured on the unwelded boundary — 18 chains, 236 corners "made
by the cut", rims a median 0.88 Lab apart — was about the cracks.

AND THE PROPERTY THAT MAKES CLOSING THE CUT POSSIBLE. Every gamut this
application draws is a height field seen from a neutral point: one distance
per direction, the whole view covered exactly once. That is what lets two
shapes be cut along their shared rays with nothing to match. It is measured,
not assumed, and `covers_the_sphere_once` is the guard.
"""
import math
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


@pytest.fixture(scope="module")
def standing_piece():
    import ti3gamut
    from gamutview import build_gamut
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
    return paper, cut, faces[keep]


def _edges_used_once(faces):
    seen = {}
    for tri in np.asarray(faces, int):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            k = (min(int(a), int(b)), max(int(a), int(b)))
            seen[k] = seen.get(k, 0) + 1
    return [k for k, n in seen.items() if n == 1]


def test_the_cut_really_does_leave_copies(standing_piece):
    # THE FAULT ITSELF, so this file cannot pass on a mesh that never had it.
    _paper, cut, _kept = standing_piece
    v = np.round(np.asarray(cut.vertices, float), 7)
    _places, counts = np.unique(v, axis=0, return_counts=True)
    assert int((counts == 4).sum()) > 50, (
        f"only {int((counts == 4).sum())} places hold four corners — the cut "
        f"no longer leaves copies, so nothing below is being tested")


def test_welding_turns_the_cracks_back_into_a_rim(standing_piece):
    from gamutview import boundary_loops, weld_by_position
    _paper, cut, kept = standing_piece
    raw = _edges_used_once(kept)
    v2, f2, _where = weld_by_position(cut.vertices, kept)
    welded = _edges_used_once(f2)
    assert len(welded) < len(raw) / 2, (
        f"welding took {len(raw)} boundary edges to {len(welded)}; the cracks "
        f"are still being counted as boundary")
    loops = boundary_loops(f2)
    # A FEW CLOSED LOOPS, NOT EIGHTEEN CHAINS. It was one loop until the cut
    # learned to look inside a facet (`sharpen_where_they_part`); where the
    # other shape bulges through the middle of one, the standing piece has an
    # ISLAND in it, and that is the truth about the shapes rather than a
    # fault. What welding fixes is the eighteen open chains the cracks made.
    assert len(loops) <= 4, (
        f"the welded rim walks into {len(loops)} chains — the cracks are "
        f"still being counted as boundary")
    for i, loop in enumerate(loops):
        assert loop[0] == loop[-1], f"welded rim {i} does not close"


def test_every_corner_of_a_welded_rim_has_exactly_two_edges(standing_piece):
    from gamutview import weld_by_position
    _paper, cut, kept = standing_piece
    _v2, f2, _where = weld_by_position(cut.vertices, kept)
    degree: dict = {}
    for a, b in _edges_used_once(f2):
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    odd = {v: d for v, d in degree.items() if d != 2}
    assert not odd, (
        f"{len(odd)} corner(s) of the welded rim have a number of edges other "
        f"than two: {sorted(set(odd.values()))}. Before welding this mesh had "
        f"corners where sixteen met.")


def test_the_shapes_are_height_fields_seen_from_the_middle(standing_piece):
    from gamutview import covers_the_sphere_once
    from references import reference_gamut
    paper, _cut, _kept = standing_piece
    for name, shape, centre in (("the paper", paper, (50.0, 0.0, 0.0)),
                                ("sRGB", reference_gamut("sRGB", steps=16),
                                 (50.0, 0.0, 0.0))):
        covered = covers_the_sphere_once(shape.vertices, shape.faces, centre)
        assert abs(covered - 4 * math.pi) < 1e-3, (
            f"{name} covers {covered:.6f} of the view from the middle, not "
            f"{4 * math.pi:.6f} — it is not a height field from there, and "
            f"cutting two shapes along their rays would fold")
