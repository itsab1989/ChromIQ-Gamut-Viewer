"""What counts as inside a gamut — the question the whole comparison rests on.

WHAT WENT WRONG. Containment was ``Delaunay(points).find_simplex(p) < 0``,
and a Delaunay triangulation tessellates exactly the CONVEX HULL of its
points. So the question actually asked was "is this inside the convex hull",
which is a different question for any gamut that is not convex — and none of
them is. Measured on Adobe RGB: 89.2% of its own surface points lie strictly
inside its own convex hull, by up to 3.9 Lab units, and the hull holds 6.1%
more volume than the space does.

Every feature that asks "does this colour fit" was affected the same way, and
always in the same direction — claiming more agreement than there is. Of the
demo paper's 675 boundary vertices, the hull called 191 outside Adobe RGB and
the surface calls 239: 48 disagreements, every one of them a colour the paper
reaches and Adobe RGB does not, reported as agreeing.

It was found by somebody looking at a published page on a phone and saying
that a part of it plainly did not agree and yet refused to stand out.
"""
import numpy as np
import pytest

from gamutview import _Enclosure, build_gamut, coverage, mesh_volume, outside_of
from references import reference_gamut


def _cube(side=2.0):
    s = side / 2
    v = np.array([[x, y, z] for x in (-s, s) for y in (-s, s)
                  for z in (-s, s)], float)
    f = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
                  [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                  [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    return v, f


def _l_shape():
    """A solid with a bite out of it: 3 square units by 1 deep.

    The whole point of it is that its convex hull is 4 units and includes the
    bite, so a hull test and a surface test must disagree about the bite.
    """
    v = np.array([
        [0, 0, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0], [1, 2, 0], [0, 2, 0],
        [0, 0, 1], [2, 0, 1], [2, 1, 1], [1, 1, 1], [1, 2, 1], [0, 2, 1]],
        float)
    faces = [[0, 2, 1], [0, 3, 2], [0, 4, 3], [0, 5, 4],
             [6, 7, 8], [6, 8, 9], [6, 9, 10], [6, 10, 11]]
    ring = [0, 1, 2, 3, 4, 5]
    for i in range(6):
        a, b = ring[i], ring[(i + 1) % 6]
        faces += [[a, b, b + 6], [a, b + 6, a + 6]]
    return v, np.array(faces)


def test_a_cube_holds_what_a_cube_holds():
    e = _Enclosure(*_cube())
    got = e.contains(np.array([[0, 0, 0], [0.9, 0.9, 0.9], [-0.99, 0, 0],
                               [1.1, 0, 0], [5, 5, 5]]))
    assert got.tolist() == [True, True, True, False, False]


def test_a_colour_on_the_boundary_is_in_the_gamut():
    """A gamut is a closed set: the surface belongs to it.

    Not a nicety. Placing a chart through a profile and asking whether it
    lands inside that same profile puts 98 of 125 patches exactly on the
    boundary, because a five-point grid falls on sample points of a 17-, 33-
    and 65-step build alike. Judged by ray parity alone — which cannot answer
    for a point on the surface — 61 of those 98 came out "outside", which is
    the coin-toss it is.
    """
    e = _Enclosure(*_cube())
    on = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.5, 0.5],
                   [1.0, 1.0, 1.0]])
    assert e.contains(on).all(), "a point on the surface must count as inside"


def test_the_bite_out_of_a_shape_is_outside_it():
    """The one thing a convex hull can never get right."""
    e = _Enclosure(*_l_shape())
    probes = np.array([[0.5, 0.5, 0.5],    # in the foot
                       [1.5, 0.5, 0.5],    # in the arm
                       [1.5, 1.5, 0.5]])   # in the BITE
    assert e.contains(probes).tolist() == [True, True, False]


def test_the_volume_of_a_shape_with_a_bite_is_not_its_hull():
    v, f = _l_shape()
    assert mesh_volume(v, f) == pytest.approx(3.0, abs=1e-9)


def test_a_working_space_is_not_convex():
    """The fact the whole change rests on, measured rather than asserted."""
    from scipy.spatial import ConvexHull
    v = np.asarray(reference_gamut("Adobe RGB (1998)", steps=40).vertices,
                   float)
    hull = ConvexHull(v)
    depth = -(hull.equations[:, :3] @ v.T + hull.equations[:, 3][:, None]
              ).max(axis=0)
    strictly_inside = (depth > 1e-6).mean()
    assert strictly_inside > 0.5, (
        f"only {strictly_inside:.1%} of Adobe RGB's surface is inside its own "
        f"hull — if this ever falls, the hull test was not the problem")
    assert depth.max() > 1.0, "the hull should bulge well clear of the surface"


def test_containment_is_measured_against_the_surface_not_the_hull():
    """A point in a hollow of the outer gamut is OUTSIDE it.

    Built to order rather than taken from a measurement, so the answer does
    not depend on which demo file is in the repository.
    """
    outer_v, outer_f = _l_shape()
    outer = type("G", (), {"vertices": outer_v, "faces": outer_f})()
    in_the_bite = np.array([[1.5, 1.5, 0.5]])
    assert outside_of(in_the_bite, outer).tolist() == [True]

    # And with the faces thrown away there is no surface to ask about, so the
    # hull is all that is left — which is the old answer, and is wrong here.
    cloud = type("G", (), {"vertices": outer_v, "faces": np.empty((0, 3), int)})()
    assert outside_of(in_the_bite, cloud).tolist() == [False], (
        "a bare point cloud can only be judged by its hull; that is why the "
        "callers hand over the gamut and not its vertices")


def test_a_gamut_covers_itself_completely():
    v, f = _l_shape()
    g = type("G", (), {"vertices": v, "faces": f})()
    got, _err = coverage(g, g, samples=4000)
    assert got == pytest.approx(1.0, abs=1e-9)


def test_coverage_counts_the_bite_as_lost():
    """The hull would say the L fits inside its own hull completely."""
    v, f = _l_shape()
    l_shape = type("G", (), {"vertices": v, "faces": f})()
    box_v, box_f = _cube(2.0)
    box_v = box_v + 1.0          # a 2x2x2 cube covering the L entirely
    box = type("G", (), {"vertices": box_v, "faces": box_f})()
    whole, _ = coverage(l_shape, box, samples=6000)
    assert whole == pytest.approx(1.0, abs=1e-9), "the L is inside the box"
    part, _ = coverage(box, l_shape, samples=6000)
    # The box holds 8; the L holds 3 of it, but only the part within the box's
    # own bounds -- the L sits at 0..2 in x and y, 0..1 in z, all inside.
    assert 0.3 < part < 0.45, (
        f"the box is only partly covered by the L, and got {part:.3f}")


def test_the_sampler_only_ever_lands_inside():
    """`coverage` draws its points from the solid rather than rejecting from a
    box, so every one it draws has to be inside."""
    e = _Enclosure(*_l_shape())
    pts = e.sample(5000, np.random.default_rng(3))
    assert e.contains(pts).all()


def test_the_sampler_fills_the_shape_evenly():
    """An even draw reproduces the volume; a biased one does not."""
    e = _Enclosure(*_l_shape())
    pts = e.sample(20000, np.random.default_rng(5))
    # The arm (x>1) is one third of the L's three square units.
    in_arm = (pts[:, 0] > 1.0).mean()
    assert in_arm == pytest.approx(1 / 3, abs=0.02), (
        f"{in_arm:.3f} of the points landed in the arm, which is a third of "
        f"the shape")
