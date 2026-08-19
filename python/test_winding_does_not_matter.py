"""Flipping which way a triangle faces changes no answer this code gives.

WHY THIS EXISTS. Nearly half the faces of a device-cube mesh are wound
inside-out — 492 of 978, measured — because the six faces of the cube are
triangulated independently and their windings disagree. That was found while
investigating a report of "rough triangles" on a saved page, and the decision
was to leave it alone: an in-page A/B of the corrected indices changed 0.1% to
0.5% of pixels and left the picture identical, because the drawing library
lights both sides of a triangle.

"Leave it alone" is only safe while every OTHER consumer is indifferent too,
and that was an argument rather than a guarantee. These tests make it a
guarantee, so nobody has to re-derive it and nobody can quietly introduce a
consumer that cares.

THE THREE CONSUMERS, and why each is indifferent:

  the volume        `mesh_volume` orients every triangle outward from the
                    centroid before summing, and says so in its docstring —
                    getting that wrong once produced a figure three times too
                    small;
  the containment   `contains` counts how many times a ray crosses the surface
                    and asks whether that is odd (gamutview.py:1000). A
                    crossing is a crossing whichever way the triangle faces;
  the drawing       measured in a real browser, not here.

The failure direction is worth stating: if one of these ever starts using face
normals — for lighting, for a signed distance, for an exported mesh format
where winding decides inside from outside — these tests fail, and that is the
moment to fix the winding rather than the moment to discover it in a picture.

WHAT IS PROVEN AND WHAT IS A TRIPWIRE, because the two are not the same.
The volume test is mutation-proven: drop the outward orientation from
`mesh_volume` (`np.abs(signed).sum()` → `signed.sum()`) and it fails, naming
the two numbers. The containment test CANNOT be made to fail by any winding
change, because counting crossings is indifferent to orientation by
construction — which is exactly what it asserts. It is there to catch the day
someone replaces that parity count with something that reads a normal, and it
would say so immediately. A check that cannot fail today is worth keeping only
when it is honest about why.
"""
from __future__ import annotations

import numpy as np
import pytest

from gamutview import build_gamut, mesh_volume


def _a_shape(seed: int = 5):
    """A closed, non-convex-ish blob big enough to have opinions."""
    rng = np.random.default_rng(seed)
    p = rng.normal(size=(900, 3))
    p /= np.linalg.norm(p, axis=1)[:, None]
    p *= rng.uniform(0.5, 1.0, size=(900, 1)) ** (1 / 3)
    lab = p * np.array([38, 52, 50])
    lab[:, 0] = np.clip(lab[:, 0] * 0.6 + 50, 4, 96)
    return build_gamut(lab)


def _flipped(faces, share: float = 0.5, seed: int = 11):
    """The same faces with a share of them wound the other way round."""
    f = np.asarray(faces).copy()
    rng = np.random.default_rng(seed)
    pick = rng.random(len(f)) < share
    f[pick] = f[pick][:, [0, 2, 1]]
    return f, int(pick.sum())


def test_the_volume_is_the_same_whichever_way_the_faces_are_wound():
    g = _a_shape()
    faces = np.asarray(g.faces)
    flipped, how_many = _flipped(faces)
    assert 0 < how_many < len(faces), "the flip has to actually flip something"

    straight = mesh_volume(g.vertices, faces)
    reversed_ = mesh_volume(g.vertices, flipped)
    assert straight > 0
    # Same number, not merely the same magnitude: a sign error would show as a
    # negative volume and an orientation error as a partly cancelled one.
    assert reversed_ == pytest.approx(straight, rel=1e-12), (
        f"flipping {how_many} of {len(faces)} faces changed the volume: "
        f"{straight} → {reversed_}")


def test_what_is_inside_is_the_same_whichever_way_the_faces_are_wound():
    from gamutview import enclosure

    g = _a_shape()
    faces = np.asarray(g.faces)
    flipped, how_many = _flipped(faces)

    # ASKED OF POINTS THAT STRADDLE THE SURFACE, half plainly within it and
    # half plainly beyond, because a question every point answers the same way
    # cannot notice anything. Built from the shape's own corners rather than a
    # box around it: uniform sampling of a box put almost everything outside,
    # and the guard below caught that.
    v = np.asarray(g.vertices, dtype=float)
    middle = v.mean(axis=0)
    rng = np.random.default_rng(3)
    pick = rng.integers(0, len(v), 400)
    reach = rng.uniform(0.35, 1.25, size=(400, 1))
    ask = middle + (v[pick] - middle) * reach

    class _Same:
        """The same gamut, its faces wound differently."""
        vertices = g.vertices
        faces = flipped
        colors = getattr(g, "colors", None)

    before = enclosure(g).contains(ask)
    after = enclosure(_Same()).contains(ask)
    assert before.sum() > 20, "the question has to be worth asking"
    assert np.array_equal(before, after), (
        f"flipping {how_many} of {len(faces)} faces moved "
        f"{int((before != after).sum())} of {len(ask)} points across the "
        f"boundary")
