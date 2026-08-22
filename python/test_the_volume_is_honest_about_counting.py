"""A shape sits inside the surface it was measured from, and by how much.

WHY THIS MATTERS TO A READER. The volume is for comparing two papers, and a
mesh through measured points is always a little SMALLER than the real
surface -- more so the fewer points there are. Measured on an ellipsoid, whose
volume is exact arithmetic:

    400 patches   -3.0%        3,000 patches   -0.4%
    800           -1.5%       20,000           -0.06%
    1,600         -0.8%

So two charts of ONE paper, 400 patches against 1,600, differ by 2.3% -- and
always in the direction that makes the bigger chart look like the bigger
gamut. The README says so in numbers now; this keeps the numbers true.
"""
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_MIDDLE = np.array([50.0, 0.0, 0.0])
_AXES = np.array([40.0, 45.0, 45.0])
_TRUTH = 4.0 / 3.0 * np.pi * float(_AXES.prod())


def _ball(n, seed=1):
    from gamutview import build_gamut
    rng = np.random.default_rng(seed)
    u = rng.normal(size=(n, 3))
    u /= np.linalg.norm(u, axis=1)[:, None]
    return build_gamut(_MIDDLE + u * _AXES, input_space="lab")


def test_a_measured_shape_never_exceeds_the_surface_it_came_from():
    """Inside, not outside: every corner is ON the surface, so the solid they
    enclose cannot be larger. A volume above the truth would mean the shape is
    inventing reach the measurements do not support."""
    for n in (400, 1600, 6000):
        got = _ball(n).volume
        assert got <= _TRUTH * 1.0005, (
            f"{n} patches gave {got:,.0f} against a true {_TRUTH:,.0f}")


def test_it_closes_on_the_truth_as_the_patches_grow():
    small, large = _ball(400).volume, _ball(6000).volume
    assert small < large < _TRUTH, "more patches must mean a closer answer"
    off = 100 * (_TRUTH - large) / _TRUTH
    assert off < 0.5, f"6,000 patches should be within half a per cent, was {off:.2f}%"


def test_the_gap_the_readme_quotes_is_still_the_gap():
    """The README tells a reader that 400 patches against 1,600 is 2.3% for
    ONE paper. If that ever stops being true the sentence is wrong, and a
    reader comparing two charts would be misled about which paper is bigger."""
    small, big = _ball(400).volume, _ball(1600).volume
    gap = 100 * (big - small) / small
    assert 1.5 < gap < 3.2, (
        f"the README says about 2.3%; this build gives {gap:.2f}%")
