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


def test_device_cube_reports_a_smaller_volume_than_the_hull():
    """The point of mode 2: a hull cannot be smaller than the real boundary,
    and the number must follow the shape. This test used to assert the two
    volumes were EQUAL, which is what a hull-only measurement gave — the dents
    were drawn and then not counted."""
    rgb, xyz = rgb_cube(6)
    hull = build_gamut(xyz, white_point="D65")
    cube = build_gamut(xyz, rgb, white_point="D65")
    assert cube.volume < hull.volume                   # the dents cost something
    assert len(cube.vertices) > len(hull.vertices)     # and are kept


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


def test_coverage_is_asymmetric_and_reproducible():
    """The number people actually want when comparing two papers, and the
    reason one number is not enough: a small gamut sits entirely inside a large
    one (100%), while the large one only partly fits in the small (well under).
    Reporting a single "similarity" would hide exactly that."""
    from gamutview import coverage
    _, big = rgb_cube(5)
    big_lab = xyz_to_lab(big, "D65")
    small_lab = big_lab * 0.5 + np.array([50.0, 0.0, 0.0]) * 0.5   # shrunk inwards
    inside, se = coverage(small_lab, big_lab)
    assert inside > 0.99, inside
    outside, _ = coverage(big_lab, small_lab)
    assert outside < 0.60, outside
    assert se < 0.01                                   # honest precision
    assert coverage(small_lab, big_lab)[0] == inside   # same seed, same answer


def test_coverage_refuses_a_gamut_with_no_volume():
    from gamutview import coverage
    _, cube = rgb_cube(4)
    with pytest.raises(ValueError):
        coverage(np.zeros((3, 3)), xyz_to_lab(cube, "D65"))


def test_mesh_volume_against_shapes_whose_answer_is_known():
    """Checked against arithmetic, not against itself: a cube of side 2 holds 8,
    and a finely sampled unit sphere approaches 4/3 pi from below (a hull of
    points ON the sphere is inscribed, so slightly smaller)."""
    from scipy.spatial import ConvexHull

    from gamutview import mesh_volume
    cube = np.array([[x, y, z] for x in (0., 2.) for y in (0., 2.)
                     for z in (0., 2.)])
    assert mesh_volume(cube, ConvexHull(cube).simplices) == pytest.approx(8.0)

    pts = np.random.default_rng(0).normal(size=(2000, 3))
    pts /= np.linalg.norm(pts, axis=1, keepdims=True)
    got = mesh_volume(pts, ConvexHull(pts).simplices)
    assert 0.985 * (4 / 3 * np.pi) < got < (4 / 3 * np.pi)


def test_the_dented_shape_reports_less_than_a_skin_around_it():
    """The whole point of the two modes: a boundary with dents in it holds less
    colour than a skin stretched over the same points. Reporting the skin's
    volume beside the dented picture would credit a printer with colour it
    cannot print."""
    rgb, xyz = rgb_cube(6)
    dented = build_gamut(xyz, rgb, white_point="D65")
    skin = build_gamut(xyz, white_point="D65")
    assert dented.volume < skin.volume
    assert dented.volume > skin.volume * 0.5      # dented, not broken


def test_orientation_is_fixed_here_not_assumed_of_the_caller():
    """The device-cube faces are triangulated independently, so their windings
    disagree. Summing signed volumes without orienting them first cancels part
    of the shape away — it once gave a third of the true answer."""
    from gamutview import mesh_volume
    rgb, xyz = rgb_cube(5)
    g = build_gamut(xyz, rgb, white_point="D65")
    naive = abs(float(np.einsum(
        "ij,ij->i",
        g.vertices[g.faces[:, 0]],
        np.cross(g.vertices[g.faces[:, 1]], g.vertices[g.faces[:, 2]])).sum()) / 6)
    assert mesh_volume(g.vertices, g.faces) > naive * 1.5
