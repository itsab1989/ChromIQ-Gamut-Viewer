"""Tests for the Python port. Run: python -m pytest python/ -q"""
import numpy as np
import pytest

from gamutview import (WHITE_POINTS, build_gamut, lab_to_lch_cartesian,
                       lab_to_xyz, xyz_to_lab, xyz_to_srgb)


def rgb_cube(n=6):
    """An n x n x n grid of sRGB drive values, and their XYZ under D65."""
    g = np.linspace(0.0, 1.0, n)
    r, gg, b = np.meshgrid(g, g, g, indexing="ij")
    rgb = np.stack([r.ravel(), gg.ravel(), b.ravel()], axis=-1)
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m = np.linalg.inv(np.array([[3.2404542, -1.5371385, -0.4985314],
                                [-0.9692660, 1.8760108, 0.0415560],
                                [0.0556434, -0.2040259, 1.0572252]]))
    return rgb, lin @ m.T


# --- colour science ---------------------------------------------------------

@pytest.mark.parametrize("wp", ["D50", "D65", "A"])
def test_white_maps_to_L100_and_neutral_ab(wp):
    """Its own white point must land on L*=100 with no colour — the definition."""
    lab = xyz_to_lab(WHITE_POINTS[wp][None, :], wp)[0]
    assert lab[0] == pytest.approx(100.0, abs=1e-9)
    assert lab[1] == pytest.approx(0.0, abs=1e-9)
    assert lab[2] == pytest.approx(0.0, abs=1e-9)


def test_lab_round_trip_including_below_the_knee():
    """Lab -> XYZ -> Lab, over dark values where the curve is linear, not cubic."""
    rng = np.random.default_rng(7)
    lab = np.column_stack([rng.uniform(0, 100, 400),
                           rng.uniform(-90, 90, 400),
                           rng.uniform(-90, 90, 400)])
    lab[:60, 0] = rng.uniform(0, 8, 60)          # under the linear-segment knee
    back = xyz_to_lab(lab_to_xyz(lab, "D50"), "D50")
    assert np.abs(back - lab).max() < 1e-8


def test_srgb_adapts_the_white_point_instead_of_ignoring_it():
    """D50 white must come out white, which needs Bradford adaptation to D65."""
    out = xyz_to_srgb(WHITE_POINTS["D50"][None, :], "D50")[0]
    assert np.allclose(out, 1.0, atol=2e-3), out
    # Fed in as though D50 were D65, it would not be neutral.
    naive = xyz_to_srgb(WHITE_POINTS["D50"][None, :], "D65")[0]
    assert np.ptp(naive) > 0.01


def test_srgb_primaries_come_back_as_primaries():
    rgb, xyz = rgb_cube(2)
    out = xyz_to_srgb(xyz, "D65")
    assert np.abs(out - rgb).max() < 2e-3


def test_cylindrical_keeps_lightness_and_chroma():
    lab = np.array([[50.0, 30.0, 40.0]])
    x, y, l = lab_to_lch_cartesian(lab)[0]
    assert l == pytest.approx(50.0)
    assert np.hypot(x, y) == pytest.approx(50.0)      # C* of (30, 40)


# --- the gamut itself -------------------------------------------------------

def test_hull_mode_encloses_a_volume_and_paints_its_vertices():
    _, xyz = rgb_cube(5)
    g = build_gamut(xyz, white_point="D65")
    assert g.mode == "hull" and g.space == "lab"
    assert g.volume > 0
    assert g.faces.shape[1] == 3
    assert g.faces.max() < len(g.vertices)             # every index is real
    assert len(g.colors) == len(g.vertices)
    assert g.colors.min() >= 0.0 and g.colors.max() <= 1.0


def test_device_cube_mode_uses_the_faces_of_the_cube():
    rgb, xyz = rgb_cube(6)
    g = build_gamut(xyz, rgb, white_point="D65")
    assert g.mode == "device-cube"
    assert g.faces.max() < len(g.vertices)
    # Six faces of a 6x6x6 grid: 36 points each, none of the interior.
    assert len(g.vertices) == 6 * 36
    assert g.volume > 0


def test_device_cube_reports_a_smaller_or_equal_volume_than_the_hull():
    """The point of mode 2: a hull cannot be smaller than the real boundary."""
    rgb, xyz = rgb_cube(6)
    hull = build_gamut(xyz, white_point="D65")
    cube = build_gamut(xyz, rgb, white_point="D65")
    # Both report the hull volume; what differs is the surface that is drawn.
    assert cube.volume == pytest.approx(hull.volume)
    assert len(cube.vertices) > len(hull.vertices)     # the dents are kept


def test_a_failed_reading_does_not_take_the_gamut_with_it():
    rgb, xyz = rgb_cube(5)
    xyz = xyz.copy()
    xyz[10] = np.nan
    xyz[20] = np.inf
    g = build_gamut(xyz, rgb, white_point="D65")
    assert np.isfinite(g.vertices).all()
    assert np.isfinite(g.colors).all()


def test_lab_input_is_accepted_without_a_pointless_round_trip():
    _, xyz = rgb_cube(5)
    lab = xyz_to_lab(xyz, "D50")
    a = build_gamut(lab, input_space="lab")
    b = build_gamut(xyz, input_space="xyz")
    assert a.volume == pytest.approx(b.volume, rel=1e-9)


def test_the_white_point_changes_the_shape_so_it_cannot_be_ignored():
    _, xyz = rgb_cube(5)
    assert (build_gamut(xyz, white_point="D50").volume
            != pytest.approx(build_gamut(xyz, white_point="D65").volume))


@pytest.mark.parametrize("bad,msg", [
    (np.zeros((3, 3)), "at least 4"),
    (np.zeros((10, 3)), "do not enclose"),
])
def test_useless_input_says_why(bad, msg):
    with pytest.raises(ValueError, match=msg):
        build_gamut(bad)


def test_mismatched_pairs_are_refused():
    _, xyz = rgb_cube(4)
    with pytest.raises(ValueError, match="must match"):
        build_gamut(xyz, np.zeros((5, 3)))


def test_unknown_white_point_lists_the_known_ones():
    _, xyz = rgb_cube(4)
    with pytest.raises(ValueError, match="D50"):
        build_gamut(xyz, white_point="D99")
