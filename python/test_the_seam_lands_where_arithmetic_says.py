"""The seam, and the tuck under it, against a curve nobody's code chose.

`ball` and `ball-shifted` are the SAME ellipsoid — semi-axes (40, 45, 45) —
about (50, 0, 0) and (50, 18, 0). Two equal shapes offset along a* cross in
the perpendicular bisector, a* = 9, exactly; and at a* = 9 the ellipsoid
equation leaves

    (L - 50)² / (40·√0.96)²  +  b² / (45·√0.96)²  =  1

so the crossing is an exact ellipse, semi-axes 39.1918 and 44.0908. That is
arithmetic this application had no hand in, which is the whole point of
`scripts/make_awkward_shapes.py`: anything the seam does that the ellipse does
not is the drawing's, and there is nothing to argue about.

TWO THINGS ARE ASKED OF IT.

    THE SEAM AS BUILT IS THAT ELLIPSE. Measured: the residual of the ellipse
    equation has a median of 0.0045 and a worst of 0.0145 over 316 corners,
    and the corners sit a median 0.17 Lab off the plane — which is the
    tessellation of a 1,600-patch ball, not the seam.

    AND THE TUCK IS EXACTLY RADIAL AND EXACTLY ITS OWN SIZE. The drawn rim is
    pulled down each corner's own ray; put that one number back along the ray
    and the ellipse must come back. It does, to five decimals: 0.00450 median
    both ways, 0.01446 worst both ways. A tuck that slid sideways, or varied
    corner to corner, could not do that.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_MIDDLE = np.array([50.0, 0.0, 0.0])
_A_AT = 9.0
_SEMI_L = 40.0 * np.sqrt(0.96)
_SEMI_B = 45.0 * np.sqrt(0.96)


def _off_the_ellipse(points):
    p = np.asarray(points, float)
    return np.abs(((p[:, 0] - 50.0) / _SEMI_L) ** 2
                  + (p[:, 2] / _SEMI_B) ** 2 - 1.0)


def _seam_of(faces):
    seen: dict = {}
    for tri in np.asarray(faces, int):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            k = (min(int(a), int(b)), max(int(a), int(b)))
            seen[k] = seen.get(k, 0) + 1
    return sorted({i for k, n in seen.items() if n == 1 for i in k})


@pytest.fixture(scope="module")
def two_equal_balls(tmp_path_factory):
    import ti3gamut
    from gamutview import build_gamut
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                           / "scripts"))
    import make_awkward_shapes
    folder = tmp_path_factory.mktemp("awkward")
    make_awkward_shapes.make(folder)

    def load(stem):
        return build_gamut(np.asarray(
            ti3gamut.read_measurement(folder / f"{stem}.ti3").lab, float),
            input_space="lab")

    gamuts = [("ball", load("ball")), ("ball-shifted", load("ball-shifted"))]
    ti3gamut._LAST_CUT = None
    ti3gamut._LAST_CAP = None
    out, _f, stands, _l = ti3gamut.recut_where_they_part(gamuts)
    return [("ball", out[0][1]), ("ball-shifted", out[1][1])], stands


@pytest.mark.parametrize("which", (0, 1))
def test_the_seam_as_built_is_the_exact_ellipse(two_equal_balls, which):
    import ti3gamut
    from gamutview import close_the_cut
    cut, stands = two_equal_balls
    piece, other = cut[which][1], cut[1 - which][1]
    faces = np.asarray(piece.faces, int)
    keep = np.asarray(stands[which], bool)[faces].all(axis=1)
    built_at, _skin, built = close_the_cut(
        piece.vertices, faces[keep], other.vertices, other.faces, _MIDDLE,
        under=(piece.vertices, piece.faces))
    built_at = np.asarray(built_at, float)
    seam = _seam_of(built)
    assert len(seam) > 100, (
        f"only {len(seam)} seam corners, which proves nothing")
    off = _off_the_ellipse(built_at[seam])
    assert np.median(off) < 0.02, (
        f"the seam sits a median {np.median(off):.5f} off the exact ellipse")
    assert off.max() < 0.08, (
        f"a seam corner sits {off.max():.5f} off the exact ellipse")
    plane = np.abs(built_at[seam][:, 1] - _A_AT)
    assert plane.max() < 1.5, (
        f"a seam corner is {plane.max():.4f} Lab off the plane a* = {_A_AT}, "
        f"which two equal shapes offset along a* cross in exactly")


@pytest.mark.parametrize("which", (0, 1))
def test_putting_the_tuck_back_brings_the_ellipse_back(two_equal_balls, which):
    """THE TUCK IS ONE NUMBER, STRAIGHT DOWN EACH RAY, OR THIS CANNOT HOLD.

    ⚠ AND THE DRAWN SEAM MUST BE MEASURABLY OFF IT FIRST. Without that, a
    tuck of zero passes this test perfectly: nothing moved, so putting
    nothing back changes nothing.
    """
    import ti3gamut
    from gamutview import close_the_cut
    cut, stands = two_equal_balls
    piece, other = cut[which][1], cut[1 - which][1]
    faces = np.asarray(piece.faces, int)
    keep = np.asarray(stands[which], bool)[faces].all(axis=1)
    built_at, _skin, built = close_the_cut(
        piece.vertices, faces[keep], other.vertices, other.faces, _MIDDLE,
        under=(piece.vertices, piece.faces))
    got = ti3gamut.cap_over_the_cut(cut, stands, which)
    assert got is not None, "two equal balls offset sideways get no lid"
    built_at = np.asarray(built_at, float)
    drawn_at = np.asarray(got[0], float)
    seam = _seam_of(built)
    was = _off_the_ellipse(built_at[seam])
    now = _off_the_ellipse(drawn_at[seam])
    assert np.median(now) > 3.0 * np.median(was), (
        f"the drawn seam is {np.median(now):.5f} off the ellipse against the "
        f"built seam's {np.median(was):.5f} — the tuck did not happen, and a "
        f"tuck that did not happen passes the rest of this test")
    tuck = np.linalg.norm(built_at[seam] - drawn_at[seam], axis=1)
    ray = drawn_at[seam] - _MIDDLE
    unit = ray / np.linalg.norm(ray, axis=1)[:, None]
    back = _off_the_ellipse(drawn_at[seam] + unit * float(np.median(tuck)))
    assert np.allclose(back, was, atol=1e-9), (
        f"putting the tuck back does not bring the ellipse back: worst "
        f"{np.abs(back - was).max():.3e} — the tuck is not one number along "
        f"each corner's own ray")
