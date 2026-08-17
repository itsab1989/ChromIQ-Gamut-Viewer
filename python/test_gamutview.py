"""Tests for the Python port. Run: python -m pytest python/ -q"""
import pathlib

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


def test_ciede2000_against_the_published_reference_pairs():
    """Sharma, Wu and Dalal (2005) published a set of pairs specifically to
    catch the mistakes every CIEDE2000 implementation makes — the hue-angle
    wrap, the rotation term near blue. Checked against those rather than
    against itself."""
    from gamutview import delta_e_2000
    cases = [
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
        ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0000),
        ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
        ((50.0, 2.49, -0.001), (50.0, -2.49, 0.0009), 7.1792),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
        ((22.7233, 20.0904, -46.694), (23.0331, 14.973, -42.5619), 2.0373),
        ((2.0776, 0.0795, -1.135), (0.9033, -0.0636, -0.5514), 0.9082),
    ]
    got = delta_e_2000([c[0] for c in cases], [c[1] for c in cases])
    want = np.array([c[2] for c in cases])
    assert np.abs(got - want).max() < 1e-4


def test_a_colour_does_not_differ_from_itself():
    from gamutview import delta_e_2000
    rng = np.random.default_rng(5)
    lab = np.column_stack([rng.uniform(0, 100, 200), rng.uniform(-100, 100, 200),
                           rng.uniform(-100, 100, 200)])
    assert delta_e_2000(lab, lab).max() < 1e-9


def test_delta_e_refuses_mismatched_sets():
    from gamutview import delta_e_2000
    with pytest.raises(ValueError, match="cannot compare"):
        delta_e_2000(np.zeros((3, 3)), np.zeros((4, 3)))


# --- the three spaces a gamut can be drawn in -------------------------------

def test_luv_white_is_the_definition():
    """Its own white point must give L*=100 with no colour, in every white."""
    from gamutview import WHITE_POINTS, xyz_to_luv
    for wp in ("D50", "D65", "A"):
        luv = xyz_to_luv(WHITE_POINTS[wp][None, :], wp)[0]
        assert luv[0] == pytest.approx(100.0, abs=1e-9), wp
        assert luv[1] == pytest.approx(0.0, abs=1e-9), wp
        assert luv[2] == pytest.approx(0.0, abs=1e-9), wp


def test_luv_round_trip_including_black_and_below_the_knee():
    """The u', v' denominator vanishes at black, which is the one input that
    can turn this into a division by zero rather than a colour."""
    from gamutview import luv_to_xyz, xyz_to_luv
    rng = np.random.default_rng(11)
    xyz = np.abs(rng.normal(size=(600, 3))) * 0.7
    xyz[:40] *= 1e-4                    # under the linear-segment knee
    xyz[0] = 0.0                        # exactly black
    back = luv_to_xyz(xyz_to_luv(xyz, "D50"), "D50")
    assert np.isfinite(back).all()
    assert np.abs(back - xyz).max() < 1e-9


def test_luv_shares_cielab_lightness_exactly():
    """Both are defined from Y through the same curve; if they ever disagree,
    one of the two implementations has drifted."""
    from gamutview import xyz_to_lab, xyz_to_luv
    rng = np.random.default_rng(12)
    xyz = np.abs(rng.normal(size=(400, 3))) * 0.6
    assert np.abs(xyz_to_lab(xyz, "D50")[:, 0]
                  - xyz_to_luv(xyz, "D50")[:, 0]).max() < 1e-12


@pytest.mark.parametrize("space", ["lab", "luv", "xyz"])
def test_a_gamut_can_be_built_in_each_space(space):
    rgb, xyz = rgb_cube(6)
    g = build_gamut(xyz, rgb, space=space, white_point="D65")
    assert g.space == space
    assert g.volume > 0
    assert np.isfinite(g.vertices).all()


def test_the_spaces_are_genuinely_different_shapes():
    """If two spaces gave the same volume, the choice would be doing nothing."""
    rgb, xyz = rgb_cube(6)
    vols = {s: build_gamut(xyz, rgb, space=s, white_point="D65").volume
            for s in ("lab", "luv", "xyz")}
    assert len({round(v, 6) for v in vols.values()}) == 3, vols


def test_only_the_opponent_spaces_have_a_hue_circle():
    """XYZ has no lightness axis and no hue angle, so asking for the
    cylindrical arrangement is a mistake worth reporting rather than a
    silently wrong picture."""
    rgb, xyz = rgb_cube(5)
    for space in ("lab", "luv"):
        assert build_gamut(xyz, rgb, space=space).cylindrical().shape[1] == 3
    with pytest.raises(ValueError, match="Lab or Luv"):
        build_gamut(xyz, rgb, space="xyz").cylindrical()


def test_every_space_round_trips_through_build_gamut():
    """Feeding a gamut's own vertices back in, saying which space they are in,
    must land on the same shape — this is what lets a reference built in one
    space be rebuilt in another."""
    rgb, xyz = rgb_cube(5)
    for space in ("lab", "luv", "xyz"):
        a = build_gamut(xyz, space=space, white_point="D50")
        b = build_gamut(a.vertices, input_space=space, space=space,
                        white_point="D50")
        assert b.volume == pytest.approx(a.volume, rel=1e-9)


def test_an_unknown_space_names_the_ones_that_work():
    _, xyz = rgb_cube(4)
    with pytest.raises(ValueError, match="lab"):
        build_gamut(xyz, space="hsv")
    with pytest.raises(ValueError, match="lab"):
        build_gamut(xyz, input_space="hsv")


def test_every_space_says_how_to_draw_and_label_it():
    """A space with no entry here would reach the plotting code and fail
    there instead, with no axis names."""
    from gamutview import AXES, DRAW_SPACES
    for space in DRAW_SPACES:
        assert set(AXES[space]) == {"cylindrical", "x", "y", "z", "units",
                                    "kind", "can"}
        assert AXES[space]["x"] and AXES[space]["y"] and AXES[space]["z"]


def test_every_colour_space_measures_a_volume_in_cubic_units():
    """Only the colour spaces claim a volume, and each says of what."""
    from gamutview import AXES, SPACES, can_do
    for space in SPACES:
        assert AXES[space]["kind"] == "colour"
        assert can_do(space, "volume")
        assert AXES[space]["units"].startswith("cubic")


def test_ink_amounts_is_a_device_space_and_converts_to_nothing():
    """The invariant the whole design rests on.

    Ink amounts are not a colour space: there is no conversion from "70% red"
    to XYZ without asking a profile what one particular printer does with it.
    Putting ``rgb`` into SPACES or into either conversion table would let a
    gamut be *built* in it, and the volume that came out would be a number
    about a cube of controls being read as a number about colour.
    """
    from gamutview import AXES, SPACES, _FROM_XYZ, _TO_XYZ, can_do
    assert "rgb" not in SPACES
    assert "rgb" not in _TO_XYZ
    assert "rgb" not in _FROM_XYZ
    assert AXES["rgb"]["kind"] == "device"
    for capability in ("hue_circle", "shapes", "volume"):
        assert not can_do("rgb", capability)


def test_ink_amounts_still_read_colour_against_a_white():
    """Found by driving the window, not by reading it.

    The axes do not depend on a white point, so switching the control off
    looked tidy — and took away the only way to answer the white-mismatch
    warning the very same panel raises. A chart drawn in ink amounts is still
    PAINTED through a profile and still COUNTED against a paper, and both of
    those read a colour against a white.
    """
    from gamutview import can_do
    assert can_do("rgb", "white_point")


def test_asking_about_an_unknown_space_or_capability_is_an_error():
    """Silently returning False would switch a working control off for ever."""
    from gamutview import can_do
    with pytest.raises(ValueError, match="capability"):
        can_do("lab", "sparkle")
    with pytest.raises(ValueError, match="space"):
        can_do("cmyk", "shapes")


# --- what two gamuts have in common -----------------------------------------

def test_shared_volume_of_a_gamut_with_itself_is_everything():
    from gamutview import shared_volume
    _, xyz = rgb_cube(5)
    lab = xyz_to_lab(xyz, "D65")
    overlap, union, share = shared_volume(lab, lab)
    assert share == pytest.approx(1.0, abs=0.02)
    assert overlap == pytest.approx(union, rel=0.02)


def test_shared_volume_is_symmetric_unlike_coverage():
    """The point of adding it: containment depends on which way round you ask,
    and this does not. A shape wholly inside another gives coverage 100% one
    way and much less the other, while the shared figure is one honest number
    either way round."""
    from gamutview import coverage, shared_volume
    _, big = rgb_cube(5)
    big_lab = xyz_to_lab(big, "D65")
    small_lab = big_lab * 0.5 + np.array([50.0, 0.0, 0.0]) * 0.5
    assert coverage(small_lab, big_lab)[0] > 0.99
    assert coverage(big_lab, small_lab)[0] < 0.60
    a = shared_volume(small_lab, big_lab)[2]
    b = shared_volume(big_lab, small_lab)[2]
    assert a == pytest.approx(b, abs=0.02)
    assert a < 0.60          # wholly inside, but much smaller: not "the same"


def test_shared_volume_refuses_something_with_no_volume():
    from gamutview import shared_volume
    _, xyz = rgb_cube(4)
    with pytest.raises(ValueError):
        shared_volume(np.zeros((3, 3)), xyz_to_lab(xyz, "D65"))


def test_lightness_range_is_the_darkest_and_brightest():
    from gamutview import lightness_range
    lab = np.array([[10.0, 0, 0], [90.0, 5, 5], [50.0, -3, 2], [30.0, 1, 1]])
    assert lightness_range(lab) == (10.0, 90.0)


def test_hue_reach_puts_every_hue_in_exactly_one_family():
    """Sectors meet halfway between neighbours, so a hue on a boundary must
    land in one family and not be counted in both."""
    from gamutview import HUE_FAMILIES, hue_reach
    angles = np.radians(np.arange(0, 360, 3.0))
    lab = np.column_stack([np.full(len(angles), 50.0),
                           50 * np.cos(angles), 50 * np.sin(angles)])
    reach = hue_reach(lab)
    assert set(reach) == {n for n, _c in HUE_FAMILIES}
    # Every family got some hue, and each reports the radius of the circle.
    for name, value in reach.items():
        assert value == pytest.approx(50.0, abs=1e-6), name


def test_hue_reach_finds_the_family_that_actually_reaches_further():
    from gamutview import hue_reach
    base = np.array([[50.0, 40.0, 0.0], [50.0, 0.0, 40.0],
                     [50.0, -40.0, 0.0], [50.0, 0.0, -40.0]])
    stretched = np.vstack([base, [[50.0, 0.0, 90.0]]])      # far into yellow
    assert hue_reach(stretched)["yellows"] > hue_reach(base)["yellows"]
    assert hue_reach(stretched)["blues"] == pytest.approx(
        hue_reach(base)["blues"])


# --- update checking -------------------------------------------------------

def test_versions_compare_as_numbers_not_as_text():
    """The mistake this exists to prevent: "1.10.0" is newer than "1.9.0",
    which a plain string comparison gets backwards."""
    from updates import is_newer
    assert is_newer("1.10.0", "1.9.0")
    assert not is_newer("1.9.0", "1.10.0")
    assert is_newer("2.0.0", "1.99.99")
    assert is_newer("v1.0.1", "1.0.0")          # a leading "v" is normal


def test_the_same_version_is_not_an_update():
    """Announcing an update to the version already running would be worse
    than saying nothing at all."""
    from updates import is_newer
    for a, b in (("1.0.0", "1.0.0"), ("v1.0.0", "1.0.0"),
                 ("1.1", "1.1.0"), ("1.1.0", "1.1")):
        assert not is_newer(a, b), (a, b)


def test_an_older_version_is_never_announced():
    from updates import is_newer
    assert not is_newer("0.9.0", "1.0.0")
    assert not is_newer("1.0.0", "1.0.1")


def test_a_tag_nobody_can_parse_is_never_an_update():
    """A release tagged something unexpected must not be reported as newer --
    silence is the safe answer when the version cannot be established."""
    from updates import is_newer, parse_version
    for junk in ("", "latest", "nightly", None):
        assert parse_version(junk) == ()
        assert not is_newer(junk or "", "1.0.0")


def test_version_parsing_is_forgiving_about_shape():
    from updates import parse_version
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.2.3-beta.4") == (1, 2, 3, 4)
    assert parse_version("2026.8") == (2026, 8)


def test_the_startup_check_is_on_and_is_the_only_thing_that_reaches_out():
    """Looking for a newer version on startup is on. That is a deliberate
    choice, and it is only defensible while the surrounding promises hold: it
    asks the releases page for a version number and nothing else, it sends
    nothing about the person, the machine or their measurements, and it never
    downloads or installs anything. If that ever stops being true, this
    default is the first thing that has to change back."""
    import gamut_app
    defaults = {key: default for key, _w, _k, default in
                gamut_app.GamutApp._persisted(_FakeApp())}
    assert defaults["auto_update"] is True
    # Somebody who already turned it off keeps it off: a stored choice is not
    # overridden by a change of default.
    assert "auto_update" in {k for k, _w, _kind, _d in
                             gamut_app.GamutApp._persisted(_FakeApp())}


class _FakeApp:
    """Only enough of the window for _persisted() to build its table."""
    def __init__(self):
        import gamut_app
        for name in ("_opacity", "_depth", "_detail", "_slice_at", "_rings"):
            setattr(self, name, None)
        for name in ("_slice_on", "_points", "_show_lost", "_relative",
                     "_manual_light", "_rings_on", "_neutral",
                     "_ideal_neutral",
                     "_auto_update", "_side_by_side", "_link_cameras"):
            setattr(self, name, None)
        for name in ("_aspect", "_white", "_space", "_mode", "_style_mine",
                     "_style_second", "_style_other",
                     # How the chart's patches are drawn.
                     "_chart_dot", "_chart_show_outside", "_chart_skin",
                     "_chart_dot_opacity", "_chart_out_dot",
                     "_chart_out_opacity",
                     "_chart_skin_colour", "_chart_skin_opacity",
                     # The outline's colour is a list of its own, not the
                     # tick it used to be.
                     "_outline_paint"):
            setattr(self, name, None)
        self._light_sliders = {k: (None,) for k, *_ in gamut_app.LIGHT_CONTROLS}
        # The movement controls are read, not just listed, so these answer.
        # Two rooms look up the slot each shape came from, so that the
        # paper can be rebuilt in CIELAB for judging. No slots here means no
        # chart to mark, which is what this stub is describing.
        self._slots = []
        self._lab_gamuts = {}
        self._spin_on = _Value(False)
        self._grid_on = _Value(True)
        # 100 = "all of it", which is the do-nothing position: the picture is
        # exactly what it would be without the control at all, so these tests
        # go on describing the same drawing they always did.
        self._agree = _Value(100)
        self._differ = _Value(100)
        self._turn_mode, self._turn_speed, self._turn_sweep = (
            _Value("swing"), _Value(8), _Value(60))
        self._tilt_mode, self._tilt_speed, self._tilt_sweep = (
            _Value("off"), _Value(6), _Value(40))

    def findChildren(self, _cls):
        return []

    def __getattr__(self, name):
        """Anything not stubbed above falls through to the window's own method,
        bound to this stand-in.

        So these tests run the REAL code against stub controls rather than a
        re-description of it -- a test that re-implements what it is checking
        passes whatever the window does.
        """
        import gamut_app
        method = getattr(gamut_app.GamutApp, name, None)
        if callable(method):
            return method.__get__(self, type(self))
        raise AttributeError(name)


def test_a_room_of_its_own_is_always_drawn_solid(monkeypatch):
    """An outline is for seeing through, and side by side there is nothing
    behind it to see. Carrying the overlay's "second chart: outline only" into
    a room of its own drew the right-hand paper as a grey wireframe: the same
    gamut, worse. Whatever the overlay styles say, each room draws solid."""
    import gamut_app
    import ti3gamut

    asked = []
    monkeypatch.setattr(ti3gamut, "build_figure",
                        lambda *a, **kw: asked.append(kw.get("styles")))
    monkeypatch.setattr(ti3gamut, "write_side_by_side_html",
                        lambda *a, **kw: None)

    fake = _FakeApp()
    fake._appearance = "dark"
    fake._link_cameras = _Checked(True)
    fake._render_options = lambda: {}
    gamut_app.GamutApp._write_two_rooms(
        fake, [("Glossy", None), ("Matte", None)],
        pathlib.Path("never-written.html"), None, None)

    assert asked == [["solid"], ["solid"]]


class _Checked:
    def __init__(self, value):
        self._value = value

    def isChecked(self):
        return self._value


class _Value:
    """One stand-in for a check box, a combo and a slider: the three ways the
    window asks a control what it holds."""
    def __init__(self, value):
        self._value = value

    def isChecked(self):
        return bool(self._value)

    def currentData(self):
        return self._value

    def value(self):
        return self._value

    def setVisible(self, on):
        self.shown = on


# --- turning by itself ------------------------------------------------------

def test_turning_is_off_until_it_is_asked_for():
    """A picture that starts moving on its own is startling, and drifting
    motion is genuinely unpleasant for some people. Nothing moves unasked --
    and up-and-down stays off even then, because one direction of movement at
    a time is usually plenty."""
    import gamut_app
    defaults = {key: default for key, _w, _k, default in
                gamut_app.GamutApp._persisted(_FakeApp())}
    assert defaults["spin_on"] is False
    assert defaults["grid_on"] is True        # the scale is on until it is not
    assert defaults["turn_mode"] == "swing"   # the mode that shows you something
    assert defaults["tilt_mode"] == "off"


def test_every_movement_setting_is_saved_and_reset():
    """_persisted() is the one table Save and Reset both read. A control left
    out of it silently keeps its value through a reset, which has happened
    before and is invisible until somebody tries it."""
    import gamut_app
    keys = {key for key, _w, _k, _d in
            gamut_app.GamutApp._persisted(_FakeApp())}
    assert {"spin_on",
            "turn_mode", "turn_speed", "turn_sweep",
            "tilt_mode", "tilt_speed", "tilt_sweep"} <= keys


def test_the_two_directions_are_independent():
    """Each carries its own way of moving, its own speed and its own distance,
    so a slow tip can run against a quicker turn."""
    import gamut_app
    fake = _FakeApp()
    fake._turn_mode, fake._turn_speed, fake._turn_sweep = (
        _Value("round"), _Value(12), _Value(90))
    fake._tilt_mode, fake._tilt_speed, fake._tilt_sweep = (
        _Value("swing"), _Value(3), _Value(25))
    got = gamut_app.GamutApp._spin_options(fake)
    assert got["turn"] == {"mode": "round", "speed": 12.0, "range": 90.0}
    assert got["tilt"] == {"mode": "swing", "speed": 3.0, "range": 25.0}


def test_the_speed_is_quoted_as_a_length_of_time():
    """Degrees per second means nothing to most people. Both readings are
    checked against the arithmetic, not against themselves."""
    import gamut_app
    fake = _spin_fake(("round", 8, 60), ("swing", 8, 60))
    gamut_app.GamutApp._update_spin_labels(fake)
    assert fake._spin_rows[0]["speed_value"].text == "45 s a turn"   # 360 / 8
    assert fake._spin_rows[1]["speed_value"].text == "24 s a swing"  # pi*60/8
    assert fake._spin_rows[1]["sweep_value"].text == "60° wide"


def test_the_ends_of_every_slider_still_read_sensibly():
    """Where a division goes wrong if it is going to: nothing may come out as
    zero, negative or absurd, in either direction."""
    import gamut_app
    for mode in ("round", "swing"):
        for speed in (2, 30):
            for sweep in (10, 180):
                fake = _spin_fake((mode, speed, sweep), (mode, speed, sweep))
                gamut_app.GamutApp._update_spin_labels(fake)
                for axis in fake._spin_rows:
                    seconds = int(axis["speed_value"].text.split()[0])
                    assert 0 < seconds < 1000, (mode, speed, sweep)


def test_a_direction_set_to_not_at_all_hides_its_own_two_sliders():
    """A control for something switched off invites a change that does
    nothing. How far goes too when it is going all the way round, because it
    means nothing there."""
    import gamut_app
    fake = _spin_fake(("swing", 8, 60), ("off", 6, 40))
    fake._spin_on = _Value(True)
    fake._slice_on = _Value(False)
    gamut_app.GamutApp._apply_spin_availability(fake)
    turn, tilt = fake._spin_rows
    assert all(w.shown for w in turn["mode_row"] + turn["speed_row"])
    assert all(w.shown for w in turn["sweep_row"])       # it is swinging
    assert all(w.shown for w in tilt["mode_row"])        # still choosable
    assert not any(w.shown for w in tilt["speed_row"])   # but nothing to set
    assert not any(w.shown for w in tilt["sweep_row"])

    fake._spin_rows[0]["mode"] = _Value("round")
    gamut_app.GamutApp._apply_spin_availability(fake)
    assert all(w.shown for w in turn["speed_row"])
    assert not any(w.shown for w in turn["sweep_row"])   # no distance to a circle


def test_the_flat_slice_view_hides_all_of_it():
    """The slice is drawn looking down. There is no camera to move."""
    import gamut_app
    fake = _spin_fake(("swing", 8, 60), ("swing", 6, 40))
    fake._spin_on = _Value(True)
    fake._slice_on = _Value(True)
    gamut_app.GamutApp._apply_spin_availability(fake)
    assert not fake._spin_on.shown
    for axis in fake._spin_rows:
        assert not any(w.shown for w in axis["mode_row"])


def test_the_engine_reaches_a_three_d_page_and_not_the_flat_one(tmp_path):
    """The flat page must not carry an engine that could never do anything."""
    from ti3gamut import write_html, write_slice_html
    _, xyz = rgb_cube(5)
    g = build_gamut(xyz, white_point="D65")
    spin = dict(on=True, turn=dict(mode="swing", speed=8.0, range=60.0),
                tilt=dict(mode="off", speed=6.0, range=40.0))

    # THE ENGINE BEING BUILT, not the word being mentioned. Looking for the
    # bare name found it in a COMMENT in another script -- the one that puts
    # see-through surfaces in order, which cross-references how the engine
    # reads the camera mid-drag -- and called a flat page carrier of an engine
    # it does not have. What matters is whether the thing is created.
    built = "window.cqSpin ="
    solid = write_html([("chart", g)], tmp_path / "a.html", "t", spin=spin)
    assert built in solid.read_text(encoding="utf-8")

    flat = write_slice_html([("chart", g)], tmp_path / "b.html", 50.0, "t")
    assert built not in flat.read_text(encoding="utf-8")


def test_both_rooms_are_handed_to_the_engine(tmp_path):
    """Side by side, the engine drives both scenes itself. cqLinkCameras only
    lets the view being DRAGGED lead, so with nobody dragging it would leave
    the second room standing still."""
    from ti3gamut import build_figure, write_side_by_side_html
    _, xyz = rgb_cube(5)
    g = build_gamut(xyz, white_point="D65")
    pages = [(n, build_figure([(n, g)], "")) for n in ("one", "two")]
    out = write_side_by_side_html(
        pages, tmp_path / "c.html",
        spin=dict(on=True, turn=dict(mode="round", speed=8.0, range=60.0),
                  tilt=dict(mode="round", speed=6.0, range=40.0)))
    text = out.read_text(encoding="utf-8")
    assert "cqSpin" in text
    assert '"ids": ["scene0", "scene1"]' in text


def test_changing_the_speed_talks_to_the_page_instead_of_reloading_it():
    """THE regression to guard. Every other control here rebuilds the page and
    loads it again. If movement went the same way, each nudge of a speed
    slider would throw the viewpoint away and restart it -- the control
    fighting the thing it controls. It must reach the live page."""
    import gamut_app
    fake = _spin_fake(("swing", 8, 60), ("off", 6, 40))
    fake._spin_on = _Value(True)
    fake._slice_on = _Value(False)
    sent = []
    fake._view = _View(sent)
    fake._redraw = lambda *_a: pytest.fail("movement must not reload the page")

    gamut_app.GamutApp._on_spin_changed(fake)

    assert len(sent) == 1 and "cqSpin" in sent[0]
    assert '"speed": 8' in sent[0]


def _spin_fake(turn, tilt):
    """A stand-in window carrying two directions of movement."""
    fake = _FakeApp()
    fake._spin_rows = []
    for mode, speed, sweep in (turn, tilt):
        fake._spin_rows.append({
            "mode": _Value(mode), "speed": _Value(speed), "sweep": _Value(sweep),
            "holder": _Shown(),
            "speed_value": _Text(), "sweep_value": _Text(),
            "mode_row": [_Shown(), _Shown()],
            "speed_row": [_Shown(), _Shown(), _Shown()],
            "sweep_row": [_Shown(), _Shown(), _Shown()],
        })
    (fake._turn_mode, fake._turn_speed, fake._turn_sweep) = (
        _Value(turn[0]), _Value(turn[1]), _Value(turn[2]))
    (fake._tilt_mode, fake._tilt_speed, fake._tilt_sweep) = (
        _Value(tilt[0]), _Value(tilt[1]), _Value(tilt[2]))
    return fake


class _Shown:
    """A widget that only remembers whether it was shown."""
    def __init__(self):
        self.shown = None

    def setVisible(self, on):
        self.shown = on


class _Text:
    """Catches what a label was asked to show."""
    def __init__(self):
        self.text = None

    def setText(self, value):
        self.text = value


class _View:
    """A page that records what was asked of it, instead of running it."""
    def __init__(self, into):
        self._into = into

    def page(self):
        return self

    def runJavaScript(self, script):
        self._into.append(script)


# --- the surface itself -----------------------------------------------------

def test_joining_repeated_corners_keeps_the_shape_exactly():
    """A boundary built from the faces of the device cube repeats every point
    along the twelve edges where two faces meet. Two copies of a corner cannot
    share a normal, so the renderer creases every seam and the surface looks
    grainy where it is continuous. Joining them must change the picture and
    nothing else: same positions, same colours, same volume, same dents."""
    from gamutview import mesh_volume
    from ti3gamut import _weld
    rgb, xyz = rgb_cube(6)
    g = build_gamut(xyz, rgb, white_point="D65")
    colours = [f"rgb({int(r*255)},{int(gr*255)},{int(b*255)})"
               for r, gr, b in g.colors]

    points, welded, faces = _weld(g.vertices, colours, g.faces)

    assert len(points) < len(g.vertices)              # copies really were there
    assert len(np.unique(np.round(points, 6), axis=0)) == len(points)
    assert len(welded) == len(points)
    assert faces.shape == g.faces.shape               # every triangle survives
    assert faces.max() < len(points)                  # and still points at one
    assert mesh_volume(points, faces) == pytest.approx(
        mesh_volume(g.vertices, g.faces), rel=1e-12)
    # every triangle keeps the three positions it had
    for new, old in zip(faces, g.faces):
        assert np.allclose(sorted(points[new].tolist()),
                           sorted(g.vertices[old].tolist()))


def test_a_shape_with_nothing_repeated_is_handed_back_untouched():
    """A hull shares its corners already. Welding must not copy it for nothing."""
    from ti3gamut import _weld
    _, xyz = rgb_cube(5)
    g = build_gamut(xyz, white_point="D65")
    colours = list(range(len(g.vertices)))
    points, welded, faces = _weld(g.vertices, colours, g.faces)
    assert points is g.vertices and welded is colours and faces is g.faces


def test_the_light_the_user_placed_reaches_the_surface():
    """Set the lighting myself moves a lamp. The argument was accepted and
    then dropped, so the controls turned nothing -- which is invisible unless
    the trace itself is asked where its light is."""
    from ti3gamut import build_figure, light_position
    _, xyz = rgb_cube(5)
    g = build_gamut(xyz, white_point="D65")
    placed = light_position(90.0, 0.2)

    fig = build_figure([("chart", g)], "", light=placed)
    meshes = [t for t in fig.data if t.type == "mesh3d"]
    assert meshes, "no surface drawn"
    for mesh in meshes:
        assert mesh.lightposition.x == pytest.approx(placed["x"])
        assert mesh.lightposition.y == pytest.approx(placed["y"])
        assert mesh.lightposition.z == pytest.approx(placed["z"])

    # and with nobody having moved it, the lamp is overhead
    plain = [t for t in build_figure([("chart", g)], "").data
             if t.type == "mesh3d"][0]
    assert (plain.lightposition.x, plain.lightposition.y) == (0, 0)
    assert plain.lightposition.z > 0


def test_moving_the_light_really_changes_where_it_is():
    """Four bearings, four different lamps -- a control that always produced
    the same position would pass a weaker test than this one."""
    from ti3gamut import light_position
    seen = {tuple(round(v, 3) for v in light_position(d, 0.3).values())
            for d in (0, 90, 180, 270)}
    assert len(seen) == 4
    high, low = light_position(0, 0.9), light_position(0, 0.1)
    assert high["z"] > low["z"]


# --- the legend key ---------------------------------------------------------

def test_the_legend_key_is_visible_on_both_pages():
    """A mesh painted per-vertex has no single colour, so Plotly draws its
    legend key in a default that vanishes on a dark page. The key must be
    legible against whichever page it is drawn on."""
    from ti3gamut import SCENE_COLOURS, _legend_swatch

    def luminance(hex_colour):
        r, g, b = (int(hex_colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    very_dark = np.zeros((10, 3)) + 0.03
    very_light = np.ones((10, 3)) - 0.03
    for mode, floor, ceiling in (("dark", 0.30, None), ("light", None, 0.70)):
        page = SCENE_COLOURS[mode]["page"]
        for colours in (very_dark, very_light):
            got = luminance(_legend_swatch(colours, page))
            if floor is not None:
                assert got >= floor, (mode, got)
            if ceiling is not None:
                assert got <= ceiling, (mode, got)


def test_the_legend_key_accepts_both_colour_forms():
    """Gamut.colors is a float array; the paint schemes hand back
    "rgb(r,g,b)" strings. Both reach this code in normal use."""
    from ti3gamut import _legend_swatch
    page = "#111318"
    assert _legend_swatch(np.array([[0.9, 0.1, 0.1]] * 4), page).startswith("#")
    assert _legend_swatch(["rgb(230,25,25)"] * 4, page).startswith("#")


def test_the_legend_key_never_brings_the_page_down():
    """Decoration must not be able to raise. Anything unusable falls back."""
    from ti3gamut import _legend_swatch
    for junk in (None, [], "not a list", [object()], [[1.0]], {}):
        assert _legend_swatch(junk, "#111318").startswith("#")


def test_the_key_still_looks_like_the_shape_it_stands_for():
    """Lifting it for legibility must not turn a red gamut into a grey chip."""
    from ti3gamut import _legend_swatch
    red = _legend_swatch(np.array([[0.55, 0.05, 0.05]] * 8), "#111318")
    r, g, b = (int(red[i:i + 2], 16) for i in (1, 3, 5))
    assert r > g and r > b, red


# --- tinting into the accent, and placing the light -------------------------

def _gamut_for_paint():
    # A fine cube, not a coarse one: with only six steps per channel there are
    # too few distinct hues for banding to be visible either way, and the test
    # would pass or fail on quantisation rather than on the thing it checks.
    _, xyz = rgb_cube(14)
    return build_gamut(xyz, input_space="xyz", white_point="D65")


def test_the_accent_tint_has_no_bands_in_it():
    """The first version snapped every colour to the nearest of six accent
    hues, which produced six flat regions with hard seams between them.

    Asserted as a property rather than against a fixed count, because how many
    distinct colours appear depends entirely on how finely the chart sampled:
    the smooth tint must produce meaningfully MORE distinct colours than
    snapping the same data would.
    """
    import colorsys
    import re as _re

    import numpy as _np

    from ti3gamut import _ACCENT_BANDS, _paint_vertices

    g = _gamut_for_paint()
    smooth = {tuple(int(v) // 6 for v in _re.findall(r"\d+", c))
              for c in _paint_vertices(g, "accent", 0)}

    snapped = set()
    for r, gg, b in _np.clip(_np.asarray(g.colors, float), 0, 1):
        h, l, s = colorsys.rgb_to_hls(float(r), float(gg), float(b))
        hue, sat = 0.0, 0.0
        if s >= 0.15:
            for lo, hi, ah, asat in _ACCENT_BANDS:
                if lo <= h * 360.0 < hi:
                    hue, sat = ah / 360.0, asat
                    break
        nr, ng, nb = colorsys.hls_to_rgb(hue, min(l, 0.92), sat)
        snapped.add(tuple(int(v * 255) // 6 for v in (nr, ng, nb)))

    assert len(smooth) > len(snapped) * 1.5, (len(smooth), len(snapped))


def test_the_tint_never_pushes_neighbours_much_further_apart():
    """A rough edge is two touching vertices that the tint separates far more
    than the measurement itself does. Judged against the real colours' own
    worst step, so the bar adapts to the data rather than being a magic
    number."""
    import re as _re

    import numpy as _np

    from ti3gamut import _paint_vertices
    g = _gamut_for_paint()
    edges = set()
    for t in g.faces:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            edges.add((min(a, b), max(a, b)))
    edges = _np.array(sorted(edges))
    tinted = _np.array([[int(v) for v in _re.findall(r"\d+", c)]
                        for c in _paint_vertices(g, "accent", 0)], float)
    real = _np.asarray(g.colors) * 255
    step_t = _np.linalg.norm(tinted[edges[:, 0]] - tinted[edges[:, 1]], axis=1)
    step_r = _np.linalg.norm(real[edges[:, 0]] - real[edges[:, 1]], axis=1)
    assert step_t.max() <= step_r.max() * 1.6, (step_t.max(), step_r.max())


def test_near_greys_are_left_grey():
    """Forcing a near-neutral into a colour it never had would be a lie about
    the measurement."""
    import re as _re

    import numpy as _np

    from ti3gamut import _accent_vertices

    class _Fake:
        colors = _np.array([[0.5, 0.5, 0.5], [0.2, 0.2, 0.205]])
    for text in _accent_vertices(_Fake()):
        r, g, b = (int(v) for v in _re.findall(r"\d+", text))
        assert max(r, g, b) - min(r, g, b) <= 6, text


def test_the_light_can_be_moved_around_and_above():
    """Direction swings it around the shape; height lifts it over the top."""
    from ti3gamut import light_position
    front = light_position(0.0, 0.0)
    side = light_position(90.0, 0.0)
    assert front["x"] > 0 and abs(front["y"]) < 1e-6
    assert side["y"] > 0 and abs(side["x"]) < 1e-6
    above = light_position(0.0, 1.0)
    assert above["z"] > 0 and abs(above["x"]) < 1e-6
    below = light_position(0.0, -1.0)
    assert below["z"] < 0


def test_the_light_stays_the_same_distance_however_it_is_placed():
    """Only the direction should change: moving a lamp closer would change the
    brightness, which is what the intensity controls are for."""
    import math

    from ti3gamut import light_position
    lengths = [math.dist((0, 0, 0), (p["x"], p["y"], p["z"]))
               for p in (light_position(d, h)
                         for d, h in ((0, 0), (90, 0.5), (200, -0.8), (330, 1)))]
    assert max(lengths) - min(lengths) < 1e-6, lengths


# --- two cross-sections, side by side ---------------------------------------

def _two_gamuts():
    """A big shape and a visibly smaller one, at a lightness both reach."""
    _, xyz = rgb_cube(6)
    big = build_gamut(xyz, white_point="D65")
    lab = xyz_to_lab(xyz, "D65")
    shrunk = lab * 0.6 + np.array([50.0, 0.0, 0.0]) * 0.4
    small = build_gamut(shrunk, input_space="lab", white_point="D65")
    return [("big", big), ("small", small)]


def test_two_cuts_are_drawn_on_one_shared_scale():
    """THE thing that would be wrong while looking perfectly fine. Each pane
    left to itself scales to whatever is in it, so a small gamut and a large
    one come out the same size and the picture says the opposite of the truth.
    """
    from ti3gamut import build_slice_figure, slice_extent
    pair = _two_gamuts()
    extent = slice_extent(pair, 50.0)
    assert extent is not None

    figures = [build_slice_figure([one], 50.0, "", extent=extent, legend=False)
               for one in pair]
    ranges = [(tuple(f.layout.xaxis.range), tuple(f.layout.yaxis.range))
              for f in figures]
    assert ranges[0] == ranges[1], ranges

    # and the range must actually hold both shapes, not just one
    for _name, g in pair:
        from gamutview import slice_at
        ring = slice_at(g, 50.0)
        if not len(ring):
            continue
        assert ring[:, 0].min() >= extent[0][0] and ring[:, 0].max() <= extent[0][1]
        assert ring[:, 1].min() >= extent[1][0] and ring[:, 1].max() <= extent[1][1]


def test_the_shared_range_survives_the_equal_units_constraint():
    """a* and b* are the same units, so the axes are locked together -- and
    with that constraint in force Plotly re-derives the range from the data
    unless autorange is switched off by name. Each pane then quietly went back
    to fitting its own shape, which is exactly the fault being prevented."""
    from ti3gamut import build_slice_figure, slice_extent
    pair = _two_gamuts()
    extent = slice_extent(pair, 50.0)
    fig = build_slice_figure([pair[1]], 50.0, "", extent=extent)
    assert fig.layout.xaxis.autorange is False
    assert fig.layout.yaxis.autorange is False
    assert fig.layout.xaxis.scaleanchor == "y"     # still equal units


def test_the_range_is_square_so_a_round_gamut_stays_round():
    from ti3gamut import slice_extent
    extent = slice_extent(_two_gamuts(), 50.0)
    width = extent[0][1] - extent[0][0]
    height = extent[1][1] - extent[1][0]
    assert width == pytest.approx(height, rel=1e-9)


def test_a_lightness_nothing_reaches_has_no_range_to_share():
    from ti3gamut import slice_extent
    assert slice_extent(_two_gamuts(), 100.0) is None
    assert slice_extent([], 50.0) is None


def test_each_cut_keeps_the_colour_its_shape_has_in_the_overlay():
    """Split apart, each figure holds one shape and would otherwise call it
    the first -- so both cuts came out the same colour and no longer matched
    the shapes they came from."""
    from ti3gamut import build_slice_figure
    pair = _two_gamuts()
    lines = []
    for i, one in enumerate(pair):
        fig = build_slice_figure([one], 50.0, "", legend=False, first=i)
        lines.append([t.line.color for t in fig.data
                      if getattr(t, "mode", "") == "lines"][0])
    assert lines[0] != lines[1], lines
    together = build_slice_figure(pair, 50.0, "")
    assert [t.line.color for t in together.data
            if getattr(t, "mode", "") == "lines"] == lines


def test_a_cut_on_its_own_needs_no_separator_before_the_lightness():
    from ti3gamut import build_slice_figure
    fig = build_slice_figure(_two_gamuts()[:1], 50.0, "")
    assert "·" not in str(fig.layout.title.text).split("lightness")[0]


# --------------------------------------------------------------------------
# The perfectly neutral line the measured greys are compared against
# --------------------------------------------------------------------------

def test_the_ideal_grey_axis_has_no_colour_in_it_at_all():
    """That is the whole definition: a* and b* both nought, at every
    lightness. Anything else is not neutral."""
    import numpy as np

    from ti3gamut import ideal_neutral_axis

    measured = np.array([[12.0, 1.4, -2.2], [50.0, -0.8, 3.1],
                         [95.0, 0.3, 4.9]])
    got = ideal_neutral_axis(measured)
    assert len(got) > 8, "a curve needs sampling, not two ends"
    assert np.allclose(got[:, 1], 0.0)
    assert np.allclose(got[:, 2], 0.0)


def test_it_covers_the_range_the_printer_actually_reached():
    """Not 0 to 100. A printer cannot reach either end, and a reference line
    running past both invites the reading that it failed to."""
    import numpy as np

    from ti3gamut import ideal_neutral_axis

    measured = np.array([[12.0, 1.4, -2.2], [50.0, -0.8, 3.1],
                         [95.0, 0.3, 4.9]])
    got = ideal_neutral_axis(measured)
    assert abs(float(got[:, 0].min()) - 12.0) < 1e-9
    assert abs(float(got[:, 0].max()) - 95.0) < 1e-9


def test_the_lightness_runs_evenly_from_one_end_to_the_other():
    import numpy as np

    from ti3gamut import ideal_neutral_axis

    got = ideal_neutral_axis(np.array([[20.0, 0.0, 0.0], [80.0, 0.0, 0.0]]),
                             steps=7)
    assert len(got) == 7
    steps = np.diff(got[:, 0])
    assert np.allclose(steps, steps[0])


def test_a_chart_with_no_greys_gets_no_line_rather_than_a_wrong_one():
    """Some charts have no equal-value patches at all. Inventing an axis for
    one would be drawing something nobody measured."""
    import numpy as np

    from ti3gamut import ideal_neutral_axis

    assert len(ideal_neutral_axis(np.empty((0, 3)))) == 0
    assert len(ideal_neutral_axis(np.array([[50.0, 1.0, 1.0]]))) == 0


def test_the_measured_greys_are_never_touched_by_it():
    """The reference is drawn beside the measurement, never instead of it."""
    import numpy as np

    from ti3gamut import ideal_neutral_axis

    measured = np.array([[12.0, 1.4, -2.2], [50.0, -0.8, 3.1]])
    before = measured.copy()
    ideal_neutral_axis(measured)
    assert np.array_equal(measured, before)


def test_showing_the_greys_makes_room_to_see_them(monkeypatch):
    """A line inside an opaque solid cannot be seen, so ticking the box would
    appear to do nothing at all. It drops the shape to a third — but only from
    full strength, because a value somebody chose is theirs."""
    import gamut_app

    class Slider:
        def __init__(self, value):
            self._value = value
        def value(self):
            return self._value
        def setValue(self, value):
            self._value = value

    class Box:
        def __init__(self, on=False):
            self.on = on
            self.enabled = False
        def isChecked(self):
            return self.on
        def setChecked(self, on):
            self.on = on
        def setEnabled(self, on):
            self.enabled = on
        def blockSignals(self, _on):
            pass

    class Stand:
        def __init__(self, opacity):
            self._opacity = Slider(opacity)
            self._ideal_neutral = Box()
            self.recorded = []
        def _after_shape_setting(self, key):
            # WHAT THIS TEST HAS TO WATCH, and did not. The old version
            # asserted that _on_opacity_changed had been called -- the live
            # restyle pushed into the page while a slider is being dragged.
            # That call does not record anything, and the next rebuild draws
            # from _shared, so the shape closed up again a moment later. The
            # test was green the whole time the feature did nothing.
            self.recorded.append((key, self._opacity.value()))
        _make_room_to_see_inside = gamut_app.GamutApp._make_room_to_see_inside
        _follow_neutral = gamut_app.GamutApp._follow_neutral

    full = Stand(100)
    full._follow_neutral(True)
    assert full._opacity.value() == 38, "an opaque shape hides the line"
    assert full.recorded == [("opacity", 38)], (
        "the value has to be RECORDED, not only pushed into the page — a "
        "rebuild reads it back from where a slider release puts it")

    chosen = Stand(70)
    chosen._follow_neutral(True)
    assert chosen._opacity.value() == 70, "a value somebody chose is theirs"
    assert chosen.recorded == []


def test_turning_the_greys_off_does_not_put_the_shape_back():
    """By then the number is theirs — quietly restoring it would undo a change
    they may have made on purpose in between."""
    import gamut_app

    class Box:
        def __init__(self):
            self.on = True
            self.enabled = True
        def isChecked(self):
            return self.on
        def setChecked(self, on):
            self.on = on
        def setEnabled(self, on):
            self.enabled = on
        def blockSignals(self, _on):
            pass

    class Slider:
        def __init__(self):
            self._value = 38
        def value(self):
            return self._value
        def setValue(self, value):
            self._value = value

    class Stand:
        def __init__(self):
            self._opacity = Slider()
            self._ideal_neutral = Box()
        def _on_opacity_changed(self, _value):
            pass
        _make_room_to_see_inside = gamut_app.GamutApp._make_room_to_see_inside
        _follow_neutral = gamut_app.GamutApp._follow_neutral

    stand = Stand()
    stand._follow_neutral(False)
    assert stand._opacity.value() == 38
    assert not stand._ideal_neutral.isChecked()


# ------------------------------------------------------- the colour of white


def test_the_paper_white_is_the_lightest_thing_the_gamut_reaches():
    from gamutview import paper_white
    lab = np.array([[95.0, -0.4, -3.4], [50.0, 20.0, 30.0],
                    [10.0, 0.0, 0.0], [80.0, 5.0, 5.0]])
    got = paper_white(lab)
    assert got == (95.0, -0.4, -3.4)


def test_a_tie_on_lightness_is_broken_towards_the_least_coloured():
    """Or a paper is described as more tinted than it is, by a stray sample a
    hundredth of a lightness away from the real white."""
    from gamutview import paper_white
    lab = np.array([[95.00, 8.0, 9.0], [94.99, 0.1, -0.2]])
    assert paper_white(lab)[1] == 0.1


def test_white_is_described_in_words_as_well_as_numbers():
    """b* is the axis that decides it for paper: brighteners push a white
    towards blue, age and rag content towards cream. a* moves far less, and
    leading with it would name a paper "greenish" over a fraction of its
    warmth."""
    from gamutview import describe_white
    assert describe_white([95, 0.0, 0.0]) == "neutral"
    assert describe_white([95, 0.4, -0.6]) == "neutral", (
        "under a chroma of 1 there is nothing to say, and saying something "
        "invites choosing between two papers on noise")
    assert describe_white([95, 0.0, 3.0]) == "warm"
    assert describe_white([95, 0.0, 7.5]) == "very warm"
    assert describe_white([95, 0.0, -4.0]) == "cool"
    assert describe_white([95, 3.0, 0.5]) == "pink-tinted"
    assert describe_white([95, -3.0, 0.5]) == "green-tinted"


def test_the_two_demo_papers_really_do_differ_in_their_white():
    """The finding that earned this its place: every other number in the
    window is blind to it. Volume barely moves when a white shifts and
    coverage only counts points in or out, so these two read as near enough
    the same paper -- and one is a cool brightened white, the other a warm
    cream, which is visible on every print."""
    from pathlib import Path
    import ti3gamut
    from gamutview import build_gamut, describe_white, paper_white
    demo = Path(__file__).resolve().parent.parent / "demo"
    out = {}
    for name in ("Glossy-paper.ti3", "Matte-paper.ti3"):
        m = ti3gamut.read_ti3(demo / name)
        g = build_gamut(m.lab, m.device, input_space="lab", space="lab")
        out[name] = paper_white(g)
    assert describe_white(out["Glossy-paper.ti3"]) == "cool"
    assert describe_white(out["Matte-paper.ti3"]) == "slightly warm"
    apart = abs(out["Glossy-paper.ti3"][2] - out["Matte-paper.ti3"][2])
    assert apart > 4.0, f"only {apart:.1f} b* apart"


def _demo(name):
    from pathlib import Path
    import ti3gamut
    from gamutview import build_gamut
    demo = Path(__file__).resolve().parent.parent / "demo"
    m = ti3gamut.read_ti3(demo / name)
    return build_gamut(m.lab, m.device, input_space="lab", space="lab")


def test_the_glossy_paper_loses_its_blacks_against_the_dark_page():
    """The report that found this: "something black at the bottom of the
    shape". It is not a spike and not a drawing fault -- the lowest vertex of
    either paper sits 0.00 below the next one, so there is no protrusion at
    all. It is the deepest black the paper prints, drawn in the colour it
    truly is, on a page of very nearly that colour."""
    from gamutview import hidden_end
    got = hidden_end(_demo("Glossy-paper.ti3"), "#111111")
    assert got is not None, "the blacks vanish on a dark page and it said nothing"
    which, share, near = got
    assert which == "blacks"
    assert share > 40.0, f"only {share:.1f}% called invisible"
    assert near < 5.0, f"nearest colour {near:.1f} levels from the page"


def test_the_matte_paper_keeps_its_blacks_against_the_same_page():
    """The half that makes the warning worth having. Both papers are drawn the
    same way on the same page and only one of them disappears -- and it is the
    one whose blacks are BETTER, L* 4.0 against L* 12.7. Somebody comparing
    the two sees more of the worse paper."""
    from gamutview import hidden_end
    assert hidden_end(_demo("Matte-paper.ti3"), "#111111") is None


def test_the_light_page_hides_the_other_end_instead():
    """The mirror image, and the reason the rule reads the page rather than
    the name of the theme."""
    from gamutview import hidden_end
    got = hidden_end(_demo("Glossy-paper.ti3"), "#efebe6")
    assert got is not None
    assert got[0] == "paper white", got


def test_a_mid_grey_page_hides_neither_end():
    """A page is a colour, not a theme. Nothing about "dark" or "light" is
    consulted; a background halfway between them loses no part of the shape
    and must produce no warning."""
    from gamutview import hidden_end
    for paper in ("Glossy-paper.ti3", "Matte-paper.ti3"):
        assert hidden_end(_demo(paper), "#7a7a7a") is None, paper


def test_the_page_may_be_written_any_of_the_usual_ways():
    """Short hex, long hex, 0-255 and 0-1 all name the same background."""
    from gamutview import hidden_end
    g = _demo("Glossy-paper.ti3")
    want = hidden_end(g, "#111111")
    for other in ("#111", "111111", (17, 17, 17), [17 / 255, 17 / 255, 17 / 255]):
        assert hidden_end(g, other) == want, other


def test_nonsense_page_colours_are_declined_rather_than_guessed():
    """A readout must never crash a view, and a warning invented from a
    colour nobody can parse is worse than no warning."""
    from gamutview import hidden_end
    g = _demo("Glossy-paper.ti3")
    for junk in (None, "", "not a colour", "#12345", (1, 2)):
        assert hidden_end(g, junk) is None, junk


def test_the_hidden_end_note_reads_as_english_in_all_four_shapes():
    """One shape or two, and either end -- four sentences, all of which a
    reader sees. The first draft produced "Glossy's paper white COME within
    four levels" and "it is the deepest black THE PAPER reaches" beside two
    named papers; a warning whose grammar is wrong invites doubt about the
    number in it, which is the opposite of what it is for."""
    import gamut_app
    note = gamut_app.GamutApp._hidden_end_note
    assert note([]) == ""

    one_dark = note([("Glossy", "blacks", 41.9, 4.4)])
    assert "Glossy's blacks come within 4 levels" in one_dark
    assert "the deepest black the paper reaches" in one_dark
    assert "page behind them" in one_dark

    one_light = note([("Glossy", "paper white", 12.7, 3.5)])
    assert "Glossy's paper white comes within" in one_light
    assert "page behind it" in one_light
    assert "the brightest white the paper reaches" in one_light

    two_dark = note([("Glossy", "blacks", 41.9, 4.4),
                     ("Other", "blacks", 22.0, 6.1)])
    assert "Glossy and Other have blacks that come" in two_dark
    assert "either paper reaches" in two_dark

    two_light = note([("Glossy", "paper white", 12.7, 3.5),
                      ("Other", "paper white", 15.0, 2.0)])
    assert "have paper whites that come" in two_light
    # The WORST of the two, not the first of them: a reader told "2 levels"
    # and "15%" knows how bad it gets, and one told the better figure does not.
    assert "within 2 levels" in two_light and "15% of that end" in two_light


def test_the_note_names_the_control_that_actually_fixes_it():
    """Naming the exact words on the exact control, because "try a different
    colouring" leaves a beginner hunting. If either label is ever reworded,
    this fails rather than letting the window send somebody to a control that
    no longer exists."""
    import gamut_app
    note = gamut_app.GamutApp._hidden_end_note(
        [("Glossy", "blacks", 41.9, 4.4)])
    assert "How the shapes are coloured" in note
    assert "By lightness" in note
    labels = dict(gamut_app.PAINTS)
    assert labels["lightness"] == "By lightness", (
        "the note points at a control label that has been changed")


# --------------------------------------------- the outline's own colour
#
# The cage's colour used to be one tick, "Colour the outlines too", and a tick
# can only say "the same as the shape". That left one genuinely useful picture
# unreachable: the solid drained to grey by lightness so its FORM reads, with
# the cage over it still carrying the real colours. Asked for in those terms.


def _two_papers():
    from pathlib import Path
    import ti3gamut
    from gamutview import build_gamut
    demo = Path(__file__).resolve().parent.parent / "demo"
    out = []
    for name in ("Glossy-paper.ti3", "Matte-paper.ti3"):
        m = ti3gamut.read_ti3(demo / name)
        out.append((name.split("-")[0],
                    build_gamut(m.lab, m.device, input_space="lab",
                                space="lab")))
    return out


def test_the_outline_may_be_coloured_whatever_the_shape_is():
    import ti3gamut
    assert ti3gamut.outline_paint("plain", "true") == "plain"
    assert ti3gamut.outline_paint("match", "lightness") == "lightness"
    # The word the old tick wrote. A setting saved last week must not come
    # back as an error.
    assert ti3gamut.outline_paint("colour", "accent") == "accent"
    # And a named one ignores the shape entirely, which is the whole point.
    for named in ti3gamut.SHAPE_PAINTS:
        assert ti3gamut.outline_paint(named, "lightness") == named


def test_an_outline_colour_nobody_handles_is_refused():
    import pytest
    import ti3gamut
    with pytest.raises(ValueError) as complaint:
        ti3gamut.outline_paint("rainbow", "true")
    said = str(complaint.value)
    assert "rainbow" in said
    for named in ti3gamut.OUTLINE_PAINTS:
        assert named in said, f"the complaint never mentions {named}"


def test_a_painting_nobody_handles_is_refused_rather_than_drawn_as_chroma():
    """Every test was a chain ending in "otherwise, by chroma", so a
    misspelling -- or "plain", which belongs to a cage and not a surface --
    came back as a chroma ramp and read as a painting fault."""
    import pytest
    import ti3gamut
    papers = _two_papers()
    for wrong in ("plain", "gray", "match"):
        with pytest.raises(ValueError):
            ti3gamut.build_figure(papers[:1], "", paint=wrong)


def _cage_colours(fig) -> set:
    """Every colour a cage is drawn in, however the cage is put together.

    ASKED OF THE PICTURE, NOT OF THE MECHANISM, and that distinction is the
    whole point of this helper. This test used to count the traces, because a
    coloured cage was once one trace per band of colour; when the cage became
    a single trace carrying a colour per point, the test failed while the
    picture got BETTER -- more colours, not fewer. A check that fails when an
    implementation improves is testing the implementation.
    """
    out = set()
    for t in fig.data:
        if not (t.name and "(outline)" in t.name and t.mode == "lines"
                and len(t.x or ()) > 3):
            continue
        colour = t.line.color
        if isinstance(colour, (list, tuple)):
            out.update(colour)
        else:
            out.add(colour)
    return out


def test_a_grey_shape_can_carry_an_outline_in_the_real_colours():
    import ti3gamut
    papers = _two_papers()
    fig = ti3gamut.build_figure(papers, "", styles=["solid", "solid+mesh"],
                                paint="lightness", mesh_paint="true")
    colours = _cage_colours(fig)
    assert len(colours) > 20, (
        f"a cage in true colours came out in {len(colours)} colours")
    # And the same page with the cage left plain is one grey, so the setting
    # is what changed it rather than the painting of the shape.
    plain = ti3gamut.build_figure(papers, "", styles=["solid", "solid+mesh"],
                                  paint="lightness", mesh_paint="plain")
    assert len(_cage_colours(plain)) == 1


def test_a_coloured_cage_is_one_trace_however_many_colours_it_has():
    """The saving behind that: 296 WebGL objects became one.

    An Adobe RGB cage has 6726 edges. Grouped into traces by coarsened colour
    it came out as 296 of them, each with its own draw call -- 357 traces on
    the published page 14 and 642 on page 18, which is what Basti met as
    "performance is bad" on a phone. A colour per point does the same picture
    in one.
    """
    import ti3gamut
    papers = _two_papers()
    for painting in ("true", "lightness", "chroma", "plain"):
        fig = ti3gamut.build_figure(papers, "", styles=["solid", "solid+mesh"],
                                    paint="lightness", mesh_paint=painting)
        cages = [t for t in fig.data
                 if t.name and "(outline)" in t.name and t.mode == "lines"
                 and len(t.x or ()) > 3]
        assert len(cages) == 1, (
            f"a cage painted {painting!r} came out as {len(cages)} traces; "
            f"one trace can carry a colour per point")


def test_a_cage_is_named_once_even_when_its_shape_agrees_entirely():
    """Reported: the matte paper's outline has no key at all on
    11-everything-handed-over.html.

    The cage is split into the half that disagrees with the other shapes and
    the half that agrees; the first carries the name and the second is
    silenced so it cannot be listed twice. Both rules are right on their own,
    and together they lose the name -- the matte paper fits entirely inside
    the glossy one, so 0 of its 978 triangles disagree, the half carrying the
    name is skipped as empty, and the only half left is the silenced one.
    """
    import numpy as np
    import ti3gamut
    papers = _two_papers()
    masks = ti3gamut.agreement_masks(papers)
    assert int(masks[1].sum()) == 0, (
        "this test is only meaningful while the second paper agrees "
        "everywhere; it now disagrees somewhere, so pick another pair")
    for split in (False, True):
        fig = ti3gamut.build_figure(papers, "", styles=["solid", "mesh"],
                                    split=split)
        named = [t.name for t in fig.data if t.showlegend]
        cages = [n for n in named if "(outline)" in n]
        assert len(cages) == 1, (
            f"split={split}: the cage is named {len(cages)} times: {named}")


def test_a_split_cage_is_still_named_only_once():
    """The other half of the same rule: when both halves ARE drawn, the name
    must not appear twice."""
    import ti3gamut
    papers = _two_papers()
    fig = ti3gamut.build_figure(papers, "", styles=["mesh", "mesh"],
                                agree=0.2, differ=1.0)
    named = [t.name for t in fig.data if t.showlegend]
    for name, _g in papers:
        wanted = f"{name} (outline)"
        assert named.count(wanted) == 1, f"{wanted} appears {named.count(wanted)} times"


def test_the_window_offers_every_outline_colour_that_can_be_drawn():
    """The list and the control must not drift apart."""
    import ti3gamut
    import gamut_app
    import inspect
    src = inspect.getsource(gamut_app.GamutApp)
    assert "self._outline_paint.addItem(\"plain grey\", \"plain\")" in src
    assert "\"the same as the shapes\", \"match\"" in src
    # The five named ones come from PAINTS itself rather than being typed
    # again, so they cannot fall behind it.
    assert "for _key, _label in PAINTS:" in src
    assert set(k for k, _ in gamut_app.PAINTS) == set(ti3gamut.SHAPE_PAINTS)


def test_a_row_with_a_tick_in_it_is_told_its_height_twice():
    """A stylesheet floor is applied at polish, long after a grid has decided
    how tall its rows are. Measured in the window: the five radios each
    insisted on 20 pixels in rows the grid had sized at 18, so they sat 17
    apart, the checked one drew as half a circle and the descenders of "By
    lightness" were cut off."""
    import gamut_app
    import inspect
    assert gamut_app.TICK_ROW >= 20
    qss = inspect.getsource(gamut_app.stylesheet)
    assert "min-height: {TICK_ROW}px" in qss, (
        "the stylesheet must take the number from Python, not repeat it")
    # And it really lands: the written-out sheet carries the number.
    assert f"min-height: {gamut_app.TICK_ROW}px" in gamut_app.stylesheet("dark")
    src = inspect.getsource(gamut_app.GamutApp)
    assert "setRowMinimumHeight(_row, TICK_ROW)" in src, (
        "and the layout has to be told the same number, because it will not "
        "ask again once the stylesheet lands")
    assert "_ask_the_layouts_again" in src


def test_a_reference_space_has_no_measured_patches_to_draw():
    """Found by pressing every control with a comparison loaded.

    A reference space is worked out from its own definition; it was never
    printed and nobody measured a patch of it, so its place in the list of
    patch clouds is None. Ticking "Show every patch I measured" crashed the
    window outright -- "too many indices for array: array is 0-dimensional" --
    three clicks from an opened file. The greys beside it already tested for
    None; this did not.
    """
    from pathlib import Path
    import ti3gamut
    from references import reference_gamut
    papers = _two_papers()
    demo = Path(__file__).resolve().parent.parent / "demo"
    m = ti3gamut.read_ti3(demo / "Glossy-paper.ti3")
    pair = [papers[0],
            ("Adobe RGB (1998)", reference_gamut("Adobe RGB (1998)"))]

    # The measured paper has a cloud; the space beside it has none.
    fig = ti3gamut.build_figure(pair, "", points=True, patches=[m.lab, None])
    clouds = [t.name for t in fig.data if t.name and "patches" in t.name]
    assert len(clouds) == 1, clouds

    # And neither of them having one is drawn rather than raised.
    fig = ti3gamut.build_figure(pair, "", points=True, patches=[None, None])
    assert not [t for t in fig.data if t.name and "patches" in t.name]


# --- the cut goes through the surface, not the hull around it ---------------

def _box(lo=0.0, hi=10.0, shift=(0.0, 0.0)):
    """A closed axis-aligned box, first axis = L*, as (vertices, faces)."""
    v = np.array([[x, y + shift[0], z + shift[1]]
                  for x in (lo, hi) for y in (lo, hi) for z in (lo, hi)], float)
    f = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
                  [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                  [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], int)
    return v, f


class _Shape:
    """The smallest thing `slice_at` accepts: vertices and faces."""
    def __init__(self, v, f):
        self.vertices, self.faces = v, f


def test_the_cut_of_a_box_is_its_exact_perimeter():
    """A plane through a 10-unit box meets it in a 40-unit square, exactly.
    Not nearly: a plane crosses a triangle in a straight line, so this is
    arithmetic rather than a search, and anything but 40.0 means the segments
    are being built wrong."""
    from gamutview import cut_segments
    v, f = _box()
    seg = cut_segments(v, f, 5.0)
    assert len(seg) == 8                          # two per side face
    total = sum(float(np.hypot(*(s[1] - s[0]))) for s in seg)
    assert total == pytest.approx(40.0, abs=1e-9)


def test_a_corner_lying_exactly_in_the_plane_does_not_double_a_point():
    """THE CASE THAT IS NOT RARE. A measured surface and a reference cube both
    put vertices on round numbers, and the cut slider asks for round numbers.
    Counting a zero-height corner as on both sides -- which reads as the
    careful thing to do -- makes a triangle report three crossings, and the
    first two are the same point twice, so the segment has no length and the
    outline loses that direction entirely."""
    from gamutview import cut_segments
    # One triangle with a corner exactly at L* = 5, spanning the plane.
    v = np.array([[5.0, 0.0, 0.0], [9.0, 4.0, 0.0], [1.0, 4.0, 0.0]])
    f = np.array([[0, 1, 2]])
    seg = cut_segments(v, f, 5.0)
    assert len(seg) == 1
    assert float(np.hypot(*(seg[0][1] - seg[0][0]))) > 1.0


def test_a_triangle_lying_wholly_in_the_plane_is_not_drawn_twice():
    """Its three edges already come from the neighbours that cross it."""
    from gamutview import cut_segments
    v, f = _box()
    flat = np.vstack([v, [[5.0, 20.0, 20.0], [5.0, 24.0, 20.0], [5.0, 20.0, 24.0]]])
    with_flat = np.vstack([f, [[8, 9, 10]]])
    assert len(cut_segments(flat, with_flat, 5.0)) == len(cut_segments(v, f, 5.0))


def test_neither_end_of_a_shape_offers_an_outline():
    """A cut at the very top or bottom has no inside for the grey axis to be
    in, and whichever side a corner exactly in the plane is counted on, the two
    ends stop behaving alike unless both are refused."""
    from gamutview import slice_at
    v, f = _box(shift=(-5.0, -5.0))
    assert len(slice_at(_Shape(v, f), 0.0)) == 0
    assert len(slice_at(_Shape(v, f), 10.0)) == 0
    assert len(slice_at(_Shape(v, f), 5.0)) == 180      # and between them, fine


def _box_with_a_dent():
    """A box whose +a* face is pushed inwards at its middle.

    A DENT NEEDS A FACE WITH A MIDDLE TO PUSH. Simply moving corners of a box
    gives a smaller box, which is still convex and still equal to its own
    hull -- so a test built that way passes on the hull code it is supposed to
    catch, which is what the first draft of this did.
    """
    v = [[x, y, z] for x in (0.0, 10.0) for y in (-5.0, 5.0)
         for z in (-5.0, 5.0)]
    f = [[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],          # the two L* ends
         [0, 4, 5], [0, 5, 1],                                 # y = -5
         [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]]           # z = -5, z = +5
    # y = +5, as four triangles around a centre pushed in to y = +1.
    v.append([5.0, 1.0, 0.0])
    for a, b in ((2, 3), (3, 7), (7, 6), (6, 2)):
        f.append([a, b, 8])
    return np.asarray(v, float), np.asarray(f, int)


def _dented_pair():
    """Two gamuts built from device values, so each follows its real boundary.

    `_two_gamuts` builds from colours alone, which gives mode="hull" -- a
    shape that IS its own convex hull, so a hull answer and a surface answer
    agree on it by construction and no test using it can tell them apart.
    """
    rgb, xyz = rgb_cube(6)
    big = build_gamut(xyz, rgb, white_point="D65")
    lab = xyz_to_lab(xyz, "D65")
    shrunk = lab * 0.6 + np.array([50.0, 0.0, 0.0]) * 0.4
    small = build_gamut(shrunk, rgb, input_space="lab", white_point="D65")
    assert big.mode == small.mode == "device-cube"
    return [("big", big), ("small", small)]


def test_the_outline_of_a_dented_shape_follows_the_dent():
    """THE WHOLE POINT, and what a whole release shipped without.

    The cut used to be taken through `Delaunay(vertices)`, which tessellates
    exactly the CONVEX HULL of those vertices -- so every dent was filled in
    before the outline was drawn, in the one picture whose entire purpose is
    showing where one paper reaches further than another.

    Measured on Adobe RGB, a distorted cube in Lab and nowhere near convex:
    the hull outline stood outside the real one in 138 to 159 of every 180
    directions at every lightness tried, by as much as 10.05 Lab units.
    """
    from gamutview import slice_at
    v, f = _box_with_a_dent()
    ring = slice_at(_Shape(v, f), 5.0, steps=360)
    assert len(ring)
    towards = np.argmin(np.abs(np.arctan2(ring[:, 1], ring[:, 0])))
    reach = float(np.hypot(*ring[towards]))
    assert reach == pytest.approx(1.0, abs=0.05), (
        f"reached {reach:.2f} towards the dent, which is 1.0 deep -- "
        "5.0 means the dent was filled in and this is the hull")


def test_every_point_of_a_real_outline_sits_on_the_real_surface():
    """Just inside it must be inside the gamut and just outside it must not --
    which is what "this is the boundary" means, asked of the same containment
    test the rest of the window uses. 720 checks per shape."""
    from gamutview import slice_at, _Enclosure
    for _name, g in _dented_pair():
        skin = _Enclosure(g.vertices, g.faces)
        lo, hi = g.vertices[:, 0].min(), g.vertices[:, 0].max()
        for L in np.linspace(lo + 0.15 * (hi - lo), hi - 0.15 * (hi - lo), 4):
            ring = slice_at(g, float(L), steps=180)
            if not len(ring):
                continue
            inner = np.column_stack([np.full(len(ring), L), ring * 0.97])
            outer = np.column_stack([np.full(len(ring), L), ring * 1.03])
            assert skin.contains(inner).all()
            assert not skin.contains(outer).any()


def test_the_shared_figure_is_measured_the_same_way_as_the_two_beside_it():
    """It was not, for two releases. `shared_volume` asked ConvexHull for both
    sizes and then handed `coverage` the bare vertices -- stripping the very
    triangles that tell it what the surface is, so that fell back to the hull
    too. Three hull answers in two lines, in a panel whose other rows had
    already been corrected, and every error flattered the overlap."""
    from gamutview import coverage, shared_volume, mesh_volume
    (an, a), (bn, b) = _dented_pair()
    _overlap, _union, share = shared_volume(a, b)

    fraction, _err = coverage(a, b)
    va = mesh_volume(a.vertices, a.faces)
    vb = mesh_volume(b.vertices, b.faces)
    want = fraction * va
    assert share == pytest.approx(want / (va + vb - want), rel=1e-9)


def test_stripping_a_shape_to_its_points_changes_the_shared_figure():
    """Proof the line above is load-bearing rather than decorative: passing
    the bare vertices, which is what the window used to do, gives a different
    answer.

    DIFFERENT, NOT LARGER. The first version of this asserted the hull answer
    is the bigger one, on the strength of the demo pair, where it is -- the
    hulls hold 8.3% and 6.1% more, so the overlap comes out flattered. That is
    a fact about those two shapes and not a theorem: the figure is a ratio of
    overlap to union, and filling in the dents of BOTH shapes swells the
    bottom of that fraction as well as the top. On this synthetic pair the
    Windows build came out the other way round, and it was right to.
    """
    from gamutview import shared_volume
    (an, a), (bn, b) = _dented_pair()
    whole = shared_volume(a, b)[2]
    stripped = shared_volume(a.vertices, b.vertices)[2]
    assert abs(stripped - whole) > 1e-4, (
        "stripping the triangles off changed nothing, so the shapes are not "
        "being measured by their surfaces at all")


# --- what a redraw does twice, it should only do once -----------------------
#
# Profiled on two papers against Adobe RGB: the whole redraw took 358 ms, and
# `coverage` was 177 ms of it -- 49% -- recomputed from scratch every time.
# Nothing it reads changes between most redraws: it asks the two SHAPES, and a
# shape is rebuilt only when a file is opened or closed or the colour space or
# white point changes. Every other redraw is what a slider does, and those are
# exactly the ones that have to feel smooth.

def _window_stub():
    """Just enough of the window for the remembering to be exercised."""
    from types import SimpleNamespace
    import gamut_app
    stub = SimpleNamespace()
    stub._remembered = gamut_app.GamutApp._remembered.__get__(stub)
    stub._forget_the_pair = gamut_app.GamutApp._forget_the_pair.__get__(stub)
    return stub


def test_the_same_pair_is_only_worked_out_once():
    stub = _window_stub()
    a, b = object(), object()
    runs = []
    answer = stub._remembered("fits", a, b, lambda: runs.append(1) or "42")
    again = stub._remembered("fits", a, b, lambda: runs.append(1) or "42")
    assert answer == again == "42"
    assert len(runs) == 1, f"worked out {len(runs)} times, not once"


def test_two_questions_about_one_pair_do_not_answer_each_other():
    """Coverage and the shared volume are both remembered for the same two
    shapes; keying on the pair alone would hand one the other's answer."""
    stub = _window_stub()
    a, b = object(), object()
    assert stub._remembered("fits", a, b, lambda: "coverage") == "coverage"
    assert stub._remembered("pair", a, b, lambda: "shared") == "shared"


def test_the_order_of_the_pair_is_part_of_the_question():
    """Coverage is not symmetric -- how much of A fits in B is a different
    number from how much of B fits in A -- so the two orders must not share
    an answer."""
    stub = _window_stub()
    a, b = object(), object()
    assert stub._remembered("fits", a, b, lambda: "a-then-b") == "a-then-b"
    assert stub._remembered("fits", b, a, lambda: "b-then-a") == "b-then-a"


def test_a_rebuilt_shape_is_asked_about_again():
    """Opening a file, or changing the space or white point, builds new
    objects. Measured in the real window: shared volume went from 78% in
    CIELAB to 81% in CIELUV, which it could not have done from a stale
    answer."""
    stub = _window_stub()
    a, b = object(), object()
    stub._remembered("fits", a, b, lambda: "old")
    stub._forget_the_pair()
    assert stub._remembered("fits", a, b, lambda: "new") == "new"


def test_the_shapes_are_held_so_their_identities_cannot_be_reused():
    """`id()` is unique only among objects that are ALIVE. A cache holding ids
    alone would answer for a gamut that had been collected and a new one built
    at the same address -- a wrong number that looks entirely plausible."""
    import gc
    stub = _window_stub()

    class Shape:
        pass

    a, b = Shape(), Shape()
    keys = (id(a), id(b))
    stub._remembered("fits", a, b, lambda: "held")
    del a, b
    gc.collect()
    # The cache still holds them, so nothing else can land on those addresses.
    kept = [v for v in stub._fits_cache.values()]
    assert kept and (id(kept[0][0]), id(kept[0][1])) == keys, (
        "the shapes were let go, so the ids in the key may now mean something "
        "else entirely")
