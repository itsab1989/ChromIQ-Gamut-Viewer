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


def _edges_walked_the_same_way(faces):
    """Interior edges whose two triangles walk them in the SAME direction.

    THE ONLY HONEST TEST OF CONSISTENT WINDING, and not "do all the cone
    volumes from the middle come out positive". A closed shape that is DENTED
    — which a printer's gamut is, and which is the whole reason `mesh_volume`
    measures the drawn surface rather than a hull around it — genuinely has
    triangles whose cone from a point inside runs the other way. Measured: 3
    of the device-cube paper's 978. Judging those backwards would call a
    correctly wound mesh broken; two of us did exactly that.
    """
    import numpy as np
    seen: dict = {}
    for tri in np.asarray(faces, int):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (min(int(a), int(b)), max(int(a), int(b)))
            seen.setdefault(key, []).append((int(a), int(b)))
    return [k for k, walks in seen.items()
            if len(walks) == 2 and walks[0] == walks[1]]


@pytest.fixture(scope="module")
def shapes():
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut
    paper_file = _DEMO / "Glossy-paper.ti3"
    if not paper_file.is_file():
        pytest.skip("no demo paper to measure")
    reading = ti3gamut.read_measurement(paper_file)
    paper = build_gamut(reading.lab, input_space="lab")
    # THE DENTED ONE TOO. A convex hull cannot dent, so a fixture of hulls
    # alone never meets the case that made the old criterion wrong.
    cube = build_gamut(reading.lab, input_space="lab",
                       drive_values=reading.device)
    return {"the paper": paper, "the paper as a device cube": cube,
            "sRGB": reference_gamut("sRGB", steps=16)}


def test_the_raw_triangles_really_do_disagree(shapes):
    # THE FAULT ITSELF, so this file cannot pass on shapes that never had it.
    # Taken from the UNFACED source, since the shapes now arrive faced.
    import ti3gamut
    from scipy.spatial import ConvexHull
    reading = ti3gamut.read_measurement(_DEMO / "Glossy-paper.ti3")
    raw = ConvexHull(np.asarray(reading.lab, float)).simplices
    clash = _edges_walked_the_same_way(raw)
    assert len(clash) > 100, (
        f"only {len(clash)} of the hull's edges are walked the same way by "
        f"both their triangles — scipy now orients them, and this file is "
        f"guarding a fault that no longer exists")


def test_every_shape_the_app_builds_is_wound_one_way(shapes):
    # NOT "faced on the way past" — the shapes must arrive already wound, or
    # the page's far-wall sort reads a mesh that disagrees with itself.
    for name, shape in shapes.items():
        clash = _edges_walked_the_same_way(shape.faces)
        assert not clash, (
            f"{name}: {len(clash)} edge(s) are walked the same way round by "
            f"both of their triangles, so the two disagree about which side "
            f"is out")


def test_facing_them_the_same_way_settles_every_neighbour(shapes):
    from gamutview import face_the_same_way
    for name, shape in shapes.items():
        faced = face_the_same_way(shape.faces, shape.vertices, _MIDDLE)
        assert not _edges_walked_the_same_way(faced), (
            f"{name}: neighbours still disagree after being faced")
        assert _signed(faced, shape.vertices).sum() > 0, (
            f"{name}: faced, the shape encloses a negative volume — it is "
            f"consistent but turned inside out")


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
    """Only the star-shaped ones: a ray count cannot measure a dented shape.

    Casting one ray per direction assumes the surface is met exactly once
    that way. The device-cube paper is not star-shaped from the middle — 1 in
    4,000 rays crosses it three times — so it is left out here and covered by
    the winding tests above instead.
    """
    from gamutview import _where_the_ray_leaves, face_the_same_way
    # 20,000 directions: at 4,000 the dice count itself wobbles by 3%, which
    # is wider than some of the faults this is meant to catch. Measured noise
    # here is under half a per cent for both shapes.
    rng = np.random.default_rng(7)
    u = rng.normal(size=(20000, 3))
    u /= np.linalg.norm(u, axis=1)[:, None]
    for name, shape in shapes.items():
        if shape.mode != "hull":
            continue
        reach = _where_the_ray_leaves(shape.vertices, shape.faces, _MIDDLE, u)
        alive = np.isfinite(reach)
        dice = (4 * np.pi / alive.sum()) * (reach[alive] ** 3 / 3).sum()
        faced = _signed(shape.faces, shape.vertices).sum()
        assert abs(faced - dice) < 0.03 * dice, (
            f"{name}: the mesh holds {faced:,.0f} where casting rays through "
            f"it says {dice:,.0f}")
        # AND THE SAME TRIANGLES LEFT UNFACED MUST NOT, or the number above
        # is not evidence of anything. Shuffling each triangle's own corners
        # cannot move a single point of the surface; it can only take away
        # the agreement between neighbours.
        rng2 = np.random.default_rng(11)
        f = np.asarray(shape.faces, int).copy()
        flip = rng2.random(len(f)) < 0.5
        f[flip] = f[flip][:, ::-1]
        muddled = _signed(f, shape.vertices).sum()
        assert abs(muddled) < 0.5 * dice, (
            f"{name}: with half the triangles turned round the mesh still "
            f"holds {muddled:,.0f} of {dice:,.0f} — this measurement cannot "
            f"see winding at all")
