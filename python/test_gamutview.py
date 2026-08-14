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
    from gamutview import AXES, SPACES
    for space in SPACES:
        assert set(AXES[space]) == {"cylindrical", "x", "y", "z", "units"}
        assert AXES[space]["units"].startswith("cubic")


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


def test_the_unattended_check_is_off_by_default():
    """The release notes promise no network is used. Anything that reaches the
    network without being asked has to be opt-in, or that promise is false."""
    import gamut_app
    defaults = {key: default for key, _w, _k, default in
                gamut_app.GamutApp._persisted(_FakeApp())}
    assert defaults["auto_update"] is False


class _FakeApp:
    """Only enough of the window for _persisted() to build its table."""
    def __init__(self):
        import gamut_app
        for name in ("_opacity", "_depth", "_detail", "_slice_at", "_rings"):
            setattr(self, name, None)
        for name in ("_slice_on", "_points", "_show_lost", "_relative",
                     "_manual_light", "_mesh_colour", "_rings_on", "_neutral",
                     "_auto_update", "_side_by_side", "_link_cameras"):
            setattr(self, name, None)
        for name in ("_aspect", "_white", "_space", "_mode", "_style_mine",
                     "_style_second", "_style_other"):
            setattr(self, name, None)
        self._light_sliders = {k: (None,) for k, *_ in gamut_app.LIGHT_CONTROLS}
        # The movement controls are read, not just listed, so these answer.
        self._spin_on = _Value(False)
        self._grid_on = _Value(True)
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

    solid = write_html([("chart", g)], tmp_path / "a.html", "t", spin=spin)
    assert "cqSpin" in solid.read_text()

    flat = write_slice_html([("chart", g)], tmp_path / "b.html", 50.0, "t")
    assert "cqSpin" not in flat.read_text()


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
    text = out.read_text()
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
