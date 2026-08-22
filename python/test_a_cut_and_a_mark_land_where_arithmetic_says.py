"""Two more things the window shows, checked against a shape with an exact answer.

The volume and the coverage are checked elsewhere the same way. These are the
two that are DRAWN rather than printed, and a drawing is where a mistake hides
best:

  * **Slice it at one lightness.** A cut through an ellipsoid is an exact
    ellipse, so every point of the outline can be asked how far it is from
    where it belongs.
  * **Show what it cannot print.** Whether a colour is inside a shape is a
    yes or no with no tolerance in it, so patches placed at 0.99 and 1.01 of
    the surface have a known answer and a 1% margin to find it in.

Neither found a fault, which is worth writing down as plainly as a fault
would be: the cut lands within 0.05% of the true ellipse, and the marking is
exact at one per cent.
"""
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_MIDDLE = np.array([50.0, 0.0, 0.0])
_AXES = np.array([40.0, 45.0, 45.0])


def _ball(n=20000, scale=1.0, seed=1):
    from gamutview import build_gamut
    rng = np.random.default_rng(seed)
    u = rng.normal(size=(n, 3))
    u /= np.linalg.norm(u, axis=1)[:, None]
    return build_gamut(_MIDDLE + u * (_AXES * scale), input_space="lab")


def test_a_cut_lands_on_the_ellipse_it_should_be():
    from gamutview import slice_at
    shape = _ball()
    checked = 0
    for light in (50.0, 60.0, 70.0, 80.0):
        k = 1.0 - ((light - 50.0) / _AXES[0]) ** 2
        want = _AXES[1:] * np.sqrt(k)
        ring = np.asarray(slice_at(shape, light))
        assert ring.size, f"L* {light}: the cut came back empty"
        pts = ring[:, 1:] if ring.shape[1] >= 3 else ring
        off = np.abs(np.hypot(pts[:, 0] / want[0], pts[:, 1] / want[1]) - 1.0)
        assert off.max() < 0.01, (
            f"L* {light}: the outline is {100*off.max():.2f}% off the ellipse "
            f"a cut through this shape actually makes")
        checked += len(pts)
    assert checked > 400, f"only {checked} points of outline were checked"


def test_what_cannot_be_printed_is_exact_at_one_per_cent():
    from gamutview import outside_of
    paper = _ball()
    for scale, expected in ((0.90, False), (0.99, False),
                            (1.01, True), (1.10, True)):
        chart = _ball(4000, scale, seed=5)
        lost = np.asarray(outside_of(chart, paper), bool)
        assert lost.mean() == (1.0 if expected else 0.0), (
            f"patches at {scale:.2f} of the surface: "
            f"{100*lost.mean():.1f}% called out of reach")


def test_the_margin_is_narrow_enough_to_mean_something():
    """A test that only tried 0.5 and 2.0 would pass on a very blunt rule."""
    assert abs(1.01 - 0.99) < 0.05
