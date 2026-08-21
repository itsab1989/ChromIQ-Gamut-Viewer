"""Half of every shape this app draws was wound backwards, and nobody asked.

A triangle's front is decided by the order of its three corners, and that
order is what a renderer turns into the normal it lights the facet by.
Nothing upstream promises neighbours agree: a convex hull hands its triangles
back however each one fell out. MEASURED on the app's own shapes:

    the paper (414 triangles)   207 one way, 207 the other
    sRGB     (6348 triangles)  3174 one way, 3174 the other

An exact half-and-half — the signature of nobody ever having asked.

WHAT IT COSTS. A closed shape's volume is a sum of signed pieces, so half of
them subtract and the total collapses: the paper's came out at 35,662 against
a true 765,392, twenty-one times too small. Every measurement built on that
number would have been wrong, and the cap over a cut is built on exactly that
number. `face_the_same_way` is the fix, and this file is the guard.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"
_MIDDLE = np.array([50.0, 0.0, 0.0])


def _signed(faces, vertices, centre=_MIDDLE):
    v = np.asarray(vertices, float)
    f = np.asarray(faces, int)
    a, b, c = v[f[:, 0]] - centre, v[f[:, 1]] - centre, v[f[:, 2]] - centre
    return np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0


@pytest.fixture(scope="module")
def shapes():
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut
    paper_file = _DEMO / "Glossy-paper.ti3"
    if not paper_file.is_file():
        pytest.skip("no demo paper to measure")
    paper = build_gamut(ti3gamut.read_measurement(paper_file).lab,
                        input_space="lab")
    return {"the paper": paper, "sRGB": reference_gamut("sRGB", steps=16)}


def test_the_shapes_really_do_come_back_mixed(shapes):
    # THE FAULT ITSELF, so this file cannot pass on shapes that never had it.
    mixed = 0
    for name, shape in shapes.items():
        s = _signed(shape.faces, shape.vertices)
        if (s > 0).any() and (s < 0).any():
            mixed += 1
    assert mixed == len(shapes), (
        f"only {mixed} of {len(shapes)} shapes come back wound both ways — "
        f"something upstream now orients them, and the rest of this file is "
        f"testing nothing")


def test_facing_them_the_same_way_leaves_no_triangle_backwards(shapes):
    from gamutview import face_the_same_way
    for name, shape in shapes.items():
        faced = face_the_same_way(shape.faces, shape.vertices, _MIDDLE)
        s = _signed(faced, shape.vertices)
        assert (s > 0).all(), (
            f"{name}: {int((s <= 0).sum())} of {len(s)} triangles still face "
            f"the wrong way after being faced the same way")


def test_facing_them_keeps_every_triangle_and_its_corners(shapes):
    from gamutview import face_the_same_way
    for name, shape in shapes.items():
        before = np.asarray(shape.faces, int)
        faced = face_the_same_way(before, shape.vertices, _MIDDLE)
        assert faced.shape == before.shape, f"{name}: triangles appeared or went"
        was = sorted(tuple(sorted(map(int, t))) for t in before)
        now = sorted(tuple(sorted(map(int, t))) for t in faced)
        assert was == now, (
            f"{name}: facing the mesh changed which corners a triangle joins, "
            f"not just the order it walks them in")


def test_a_faced_shape_holds_the_volume_it_looks_like(shapes):
    from gamutview import _where_the_ray_leaves, face_the_same_way
    # 20,000 directions: at 4,000 the dice count itself wobbles by 3%, which
    # is wider than some of the faults this is meant to catch. Measured noise
    # here is under half a per cent for both shapes.
    rng = np.random.default_rng(7)
    u = rng.normal(size=(20000, 3))
    u /= np.linalg.norm(u, axis=1)[:, None]
    for name, shape in shapes.items():
        reach = _where_the_ray_leaves(shape.vertices, shape.faces, _MIDDLE, u)
        alive = np.isfinite(reach)
        dice = (4 * np.pi / alive.sum()) * (reach[alive] ** 3 / 3).sum()
        raw = _signed(shape.faces, shape.vertices).sum()
        faced = _signed(face_the_same_way(shape.faces, shape.vertices,
                                          _MIDDLE), shape.vertices).sum()
        assert abs(faced - dice) < 0.03 * dice, (
            f"{name}: faced, the mesh holds {faced:,.0f} where casting rays "
            f"through it says {dice:,.0f}")
        assert raw < 0.5 * dice, (
            f"{name}: the mesh as built already holds {raw:,.0f} against a "
            f"true {dice:,.0f} — it was not mixed, so this proves nothing")
