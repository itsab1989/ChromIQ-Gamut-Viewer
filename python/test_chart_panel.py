"""What the chart panel SAYS — the sentences, not the arithmetic.

WHY THE WINDOW ITSELF IS NOT BUILT HERE. Constructing ``GamutApp`` inside
pytest brings up a QWebEngineView, and that aborts the whole run:

    QtWebEngineCore ... ScreenCaptureKitFullscreenModule ... abort

So everything here is tested through the methods a real click reaches, with a
stand-in for the parts of the window they read. The checks that genuinely need
a window on screen — that no button label is clipped in a 346 px column, that
nothing overflows it — live in ``scripts/drive_chart.py``, which runs the real
application and is run before a release.

The two faults this feature carried in development were both invisible from
the source and both are pinned here: a verdict that named the wrong file
because a profile and its measurement share a stem, and a warning without
which 624 patches were reported outside a paper that reaches every one of them.
"""
import os
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    """A window-less Qt application, imports in the one order that works."""
    import gamut_app                                  # noqa: F401
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


CORNERS = np.array([[0.0, 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100]])


def verdict(name, points, same_profile, suspect=2.0):
    import chart as chart_mod
    import gamut_app
    report = chart_mod.outside_report(np.atleast_2d(points), CORNERS)
    stub = SimpleNamespace(CHART_BUILDER_SUSPECT=suspect)
    return gamut_app.GamutApp._chart_verdict(stub, name, report, same_profile)


def caution(measured, judging_relative):
    import gamut_app
    stub = SimpleNamespace(
        _relative=SimpleNamespace(isChecked=lambda: judging_relative))
    return gamut_app.GamutApp._white_mismatch_caution(stub, measured)


# --------------------------------------------------------------------------
# Telling the two questions apart
# --------------------------------------------------------------------------

def test_a_clean_answer_against_the_placing_profile_says_what_it_proves(app):
    """It proves the chart builder did its job. It proves nothing whatever
    about the printer, because the same profile answered both halves — and a
    reader allowed to assume otherwise is the trap this was designed around."""
    said = verdict("P", [10.0, 5, 5], same_profile=True)
    assert "rather than of your printer" in said
    assert "0 outside" in said


def test_a_clean_answer_against_something_else_makes_no_such_excuse(app):
    said = verdict("Matte", [10.0, 5, 5], same_profile=False)
    assert "rather than of your printer" not in said
    assert "within reach of Matte" in said


def test_every_verdict_gives_all_three_counts(app):
    for same in (True, False):
        said = verdict("P", [10.0, 5, 5], same_profile=same)
        assert "inside" in said and "on the edge" in said and "outside" in said


def test_a_whisker_outside_the_placing_profile_is_not_called_a_fault(app):
    """MEASURED: a gamut surface is drawn through a grid of samples, and the
    real edge bulges slightly between them, so a couple of hundred patches of a
    5960-patch chart always land a whisker outside the very profile that placed
    them — by 1.3 ΔE at the application's own sampling, falling to 0.05 as the
    grid is made finer. Calling that a fault sends somebody hunting nothing."""
    # 3 Lab units out, which is 1.5 ΔE2000 here — past the edge band and
    # nowhere near the 2.0 at which the chart builder becomes the suspect.
    said = verdict("P", [50.0, 50.0, -3.0], same_profile=True)
    assert "1 outside" in said, said
    assert "thickness of the boundary" in said, said
    assert "Nothing here needs looking into" in said
    assert "Something differs" not in said


def test_a_patch_too_close_to_see_is_on_the_edge_and_nothing_is_outside(app):
    said = verdict("P", [0.0, 0.0, -0.05], same_profile=True)
    assert "1 on the edge, 0 outside" in said, said
    assert "Every patch sits inside" in said


def test_a_long_way_outside_the_placing_profile_names_the_real_causes(app):
    """Far out and in numbers is not sampling — it is the chart builder, and
    the four things that do it are worth naming rather than making somebody
    guess."""
    far = np.array([[50.0, 90, 90]] * 40)
    said = verdict("P", far, same_profile=True)
    assert "Something differs" in said
    for cause in ("intent", "255", "clipped", "different profile"):
        assert cause in said, cause


def test_a_measurement_that_cannot_reach_them_says_exactly_that(app):
    said = verdict("Matte", [[50.0, 90, 90]] * 40, same_profile=False)
    assert "cannot reach what those patches ask for" in said
    assert "average of those" in said


# --------------------------------------------------------------------------
# The two whites
# --------------------------------------------------------------------------

def test_a_measurement_on_another_white_is_flagged_and_the_fix_is_named(app):
    """THE FALSE ALARM THIS NEARLY SHIPPED. A chart is placed through the
    profile's relative colorimetric table, and "relative colorimetric" means
    the paper's white becomes L* 100. A measurement read absolutely keeps the
    white the instrument saw — L* 93.8 on the demo glossy paper. Every light
    patch then floats above the measured shape for no reason to do with the
    printer. Measured on a real 5960-patch chart against the measurement of
    the very paper its profile describes: 624 patches outside, and 0 once the
    two are judged against the same white."""
    said = caution(measured=True, judging_relative=False)
    assert "different whites" in said
    assert "Judge each paper against its own white" in said


def test_nothing_is_said_once_they_are_judged_the_same_way(app):
    assert caution(measured=True, judging_relative=True) == ""


def test_a_profile_has_no_paper_white_so_there_is_nothing_to_warn_about(app):
    assert caution(measured=False, judging_relative=False) == ""


def test_the_warning_never_moves_the_setting_itself(app):
    """It changes every other figure in the window as well, so it is the
    reader's to move — named, and left alone."""
    said = caution(measured=True, judging_relative=False)
    assert "Tick" in said


# --------------------------------------------------------------------------
# What reaches the picture
# --------------------------------------------------------------------------

def test_a_chart_is_drawn_as_dots_and_never_as_a_surface(app):
    """A shape thrown around a set of requested ink amounts is not the gamut of
    anything, and drawing one would be the single claim this feature exists not
    to make."""
    import ti3gamut
    lab = np.column_stack([np.linspace(10, 90, 30),
                           np.linspace(-40, 40, 30),
                           np.linspace(-30, 30, 30)])
    figure = ti3gamut.build_figure([], "t", chart=("mine", lab, None))
    assert {t.type for t in figure.data} == {"scatter3d"}
    assert any("to be printed" in (t.name or "") for t in figure.data)


def test_the_ones_outside_are_drawn_apart_from_the_rest(app):
    """Picked out rather than merely counted: somebody should find them without
    reading a number."""
    import ti3gamut
    lab = np.column_stack([np.linspace(10, 90, 30),
                           np.zeros(30), np.zeros(30)])
    outside = np.zeros(30, dtype=bool)
    outside[:4] = True
    figure = ti3gamut.build_figure([], "t", chart=("mine", lab, outside))
    names = [t.name for t in figure.data]
    assert any("to be printed" in n for n in names)
    # The DATA trace, not the key. Every name in the legend now has a proxy
    # standing in for it — a scatter holding no points — so that the key is a
    # solid, readable colour at a fixed size whatever the dots are set to.
    marked = [t for t in figure.data
              if "outside" in (t.name or "") and t.hoverinfo != "skip"]
    assert len(marked) == 1
    assert len(marked[0].x) == 4
    assert marked[0].marker.size > 3.2       # larger than the ordinary dots


def test_a_chart_with_nothing_outside_adds_no_empty_trace(app):
    import ti3gamut
    lab = np.column_stack([np.linspace(10, 90, 10),
                           np.zeros(10), np.zeros(10)])
    figure = ti3gamut.build_figure(
        [], "t", chart=("mine", lab, np.zeros(10, dtype=bool)))
    assert not any("outside" in (t.name or "") for t in figure.data)


def test_the_chart_is_drawn_over_the_shapes_rather_than_under_them(app):
    """Dots hidden inside a solid are dots nobody can read."""
    import ti3gamut
    from references import reference_gamut
    lab = np.column_stack([np.linspace(10, 90, 10),
                           np.zeros(10), np.zeros(10)])
    figure = ti3gamut.build_figure(
        [("sRGB", reference_gamut("sRGB"))], "t", chart=("mine", lab, None))
    last = figure.data[-1]
    assert "to be printed" in (last.name or "")


def test_a_saved_page_carries_the_chart_as_well(app, tmp_path):
    """The save route and the live view are two calls with almost identical
    argument lists, which is how the save route came to be broken once before
    while the window looked perfectly fine.

    The names are searched for as plotly ESCAPES them: an em dash goes into the
    page as \\u2014, so looking for the literal character reports a trace
    missing that is right there. That false alarm cost a few minutes.
    """
    import ti3gamut
    from references import reference_gamut
    lab = np.column_stack([np.linspace(10, 95, 40),
                           np.linspace(-60, 60, 40), np.linspace(-50, 50, 40)])
    outside = np.zeros(40, dtype=bool)
    outside[::5] = True
    out = tmp_path / "page.html"
    ti3gamut.write_html([("paper", reference_gamut("sRGB"))], out, "t",
                        chart=("mine", lab, outside), carry_viewer=False,
                        notes="248 inside, 72 on the edge, 160 outside.")
    page = out.read_text()
    assert "to be printed" in page
    assert "outside" in page
    assert "on the edge" in page          # the figures travelled too


# --------------------------------------------------------------------------
# Ink amounts — what reaches the picture with no profile at all
# --------------------------------------------------------------------------

def _ink_grid(steps=4):
    axis = np.linspace(0, 100, steps)
    return np.stack(np.meshgrid(axis, axis, axis, indexing="ij"),
                    axis=-1).reshape(-1, 3)


def test_a_chart_in_ink_amounts_draws_with_no_profile_and_no_shape(app):
    """The question that started this, in one test: a patch set, alone, on real axes.

    No Lab is passed at all, because none exists — nothing has said what these
    ink amounts print as. The dots still appear, at the numbers the file
    holds, and the axes say what they are.
    """
    import ti3gamut
    device = _ink_grid(4)
    figure = ti3gamut.build_figure([], "t", space="rgb",
                                   chart=("mine", None, None, device))
    assert {t.type for t in figure.data} == {"scatter3d"}
    assert len(figure.data[0].x) == 64
    scene = figure.layout.scene
    assert scene.xaxis.title.text == "Red  %"
    assert scene.yaxis.title.text == "Green  %"
    assert scene.zaxis.title.text == "Blue  %"


def test_the_dots_sit_at_the_ink_amounts_themselves(app):
    """Positions are the file's numbers, not a lookup of them."""
    import ti3gamut
    device = np.array([[0.0, 0.0, 0.0], [100.0, 50.0, 25.0]])
    figure = ti3gamut.build_figure([], "t", space="rgb",
                                   chart=("mine", None, None, device))
    got = np.column_stack([figure.data[0].x, figure.data[0].y,
                           figure.data[0].z])
    assert np.allclose(np.sort(got, axis=0), np.sort(device, axis=0))


def test_without_a_profile_the_dots_are_painted_with_the_ink_amounts(app):
    """A legend, not a prediction — and the panel says so beside them.

    Painting them with anything else would be inventing a colour for a patch
    nothing has yet been asked about.
    """
    import ti3gamut
    device = np.array([[100.0, 0.0, 0.0], [0.0, 100.0, 0.0]])
    figure = ti3gamut.build_figure([], "t", space="rgb",
                                   chart=("mine", None, None, device))
    assert list(figure.data[0].marker.color) == ["rgb(255,0,0)",
                                                 "rgb(0,255,0)"]


def test_with_a_profile_the_dots_keep_their_place_and_change_colour(app):
    """The profile cannot move them — the ink amounts ARE the axes.

    This is the one thing most likely to be got wrong by someone extending
    the view later: a profile is a colouring here, not a placement.
    """
    import ti3gamut
    device = np.array([[100.0, 0.0, 0.0], [0.0, 100.0, 0.0]])
    lab = np.array([[54.0, 81.0, 70.0], [88.0, -79.0, 81.0]])
    plain = ti3gamut.build_figure([], "t", space="rgb",
                                  chart=("mine", None, None, device))
    with_profile = ti3gamut.build_figure([], "t", space="rgb",
                                         chart=("mine", lab, None, device))
    assert np.allclose(plain.data[0].x, with_profile.data[0].x)
    assert np.allclose(plain.data[0].z, with_profile.data[0].z)
    assert (list(plain.data[0].marker.color)
            != list(with_profile.data[0].marker.color))


def test_drawing_a_chart_in_ink_amounts_without_the_amounts_is_refused(app):
    """Lab cannot be turned back into ink without inverting a profile, and
    quietly drawing the Lab on axes labelled Red/Green/Blue would be the
    worst possible way to be wrong."""
    import ti3gamut
    lab = np.array([[50.0, 10.0, -10.0]])
    with pytest.raises(ValueError, match="ink amounts needs the device"):
        ti3gamut.build_figure([], "t", space="rgb",
                              chart=("mine", lab, None, None))


def test_a_colour_space_still_refuses_a_chart_with_no_profile(app):
    """The other direction of the same rule."""
    import ti3gamut
    with pytest.raises(ValueError, match="needs a profile"):
        ti3gamut.build_figure([], "t", space="lab",
                              chart=("mine", None, None, _ink_grid(2)))


def test_labelling_the_axes_against_the_shapes_actually_built_is_refused(app):
    """A picture read against the wrong axes is the failure this whole
    feature could most easily introduce, so it is made impossible."""
    import ti3gamut
    from references import reference_gamut
    with pytest.raises(ValueError, match="wrong axes"):
        ti3gamut.build_figure([("sRGB", reference_gamut("sRGB"))], "t",
                              space="rgb")


def test_the_old_three_item_chart_still_works(app):
    """Pages and callers written before ink amounts existed keep working."""
    import ti3gamut
    lab = np.column_stack([np.linspace(10, 90, 8), np.zeros(8), np.zeros(8)])
    figure = ti3gamut.build_figure([], "t", chart=("mine", lab, None))
    assert len(figure.data[0].x) == 8


# --------------------------------------------------------------------------
# Judging is about colour, never about how the picture is drawn
# --------------------------------------------------------------------------

def test_a_hull_does_not_survive_the_trip_through_another_space(app):
    """WHY the judging shape is rebuilt rather than converted.

    The obvious fix for a gamut built in the wrong space is to convert its
    vertices back to Lab. It is not good enough: a convex hull stops being
    convex once it has been through the Lab-XYZ curve, so the converted
    surface is CLOSE to the Lab one and not the same. Close is not the
    standard for a figure quoted in ΔE, which is why _in_lab builds from the
    measurements instead. This pins the reason, so nobody simplifies it back.
    """
    import numpy as np
    from gamutview import _TO_XYZ, build_gamut, xyz_to_lab

    rng = np.random.default_rng(3)
    lab = np.column_stack([rng.uniform(5, 95, 300),
                           rng.uniform(-70, 70, 300),
                           rng.uniform(-70, 70, 300)])
    in_lab = build_gamut(lab, input_space="lab", space="lab",
                         white_point="D50")
    in_xyz = build_gamut(lab, input_space="lab", space="xyz",
                         white_point="D50")
    converted = xyz_to_lab(_TO_XYZ["xyz"](in_xyz.vertices, "D50"), "D50")
    assert len(converted) != len(in_lab.vertices), (
        "if these ever match, converting would be exact and the rebuild "
        "could be simplified away — check before doing it")


def test_a_chart_is_marked_against_the_shape_it_is_shown_with(app):
    """Two rooms exist to compare two papers, so a chart in the right-hand
    room must answer for the right-hand paper. It was answering for the
    left-hand one, because the mask is worked out once against the first
    shape on screen and both rooms were handed the same chart."""
    import numpy as np

    import gamut_app
    from references import reference_gamut

    lab = np.column_stack([np.linspace(20, 90, 40),
                           np.linspace(-60, 60, 40),
                           np.linspace(-50, 50, 40)])
    chart = ("c", lab, np.zeros(40, dtype=bool), None)
    small = reference_gamut("sRGB")
    wide = reference_gamut("ProPhoto RGB")

    class _Win:
        _white = SimpleNamespace(currentData=lambda: "D50")
        _in_lab = gamut_app.GamutApp._in_lab
        _chart_marked_against = gamut_app.GamutApp._chart_marked_against

    win = _Win()
    against_small = _Win._chart_marked_against(win, chart, small)[2]
    against_wide = _Win._chart_marked_against(win, chart, wide)[2]
    # A wider space loses fewer of them: the two answers must differ, or one
    # of the rooms is showing the other one's verdict.
    assert int(against_small.sum()) > int(against_wide.sum()), (
        int(against_small.sum()), int(against_wide.sum()))


def test_every_legend_key_is_a_proxy_of_the_same_size(app):
    """A key is a key whatever the dots are doing.

    Plotly draws a scatter's key from the trace itself, so the key inherited
    the marker size and opacity — turning the out-of-reach dots down, which is
    the sensible thing when half a chart is red, shrank and faded their key
    with them. And given a LIST of colours it keys on the first, which for a
    chart is very often black: on a dark page that marker vanished entirely.
    """
    import numpy as np

    import ti3gamut
    device = np.random.default_rng(1).uniform(0, 100, (60, 3))
    outside = np.zeros(60, dtype=bool)
    outside[:20] = True
    for out_size, out_op, dot_size in ((2.0, 0.1, 2.0), (14.0, 1.0, 10.0)):
        figure = ti3gamut.build_figure(
            [], "t", space="rgb", chart=("c", None, outside, device),
            chart_look=dict(skin="solid", skin_opacity=0.08,
                            out_dot_size=out_size, out_dot_opacity=out_op,
                            dot_size=dot_size))
        keys = [t for t in figure.data if t.showlegend]
        assert len(keys) == 3, [t.name for t in keys]
        # All three the same size, none of them carrying the dots' opacity,
        # and every one a solid colour rather than a list.
        assert {t.marker.size for t in keys} == {11}, (
            out_size, [t.marker.size for t in keys])
        for key in keys:
            assert isinstance(key.marker.color, str), key.name
            assert key.marker.opacity in (None, 1.0), key.name


def test_a_legend_key_is_lifted_until_it_can_be_seen(app):
    """Black patches on a dark page, and white ones on a light page."""
    from ti3gamut import SCENE_COLOURS, _legend_swatch

    dark = SCENE_COLOURS["dark"]["page"]
    light = SCENE_COLOURS["light"]["page"]

    def lum(hex_colour):
        r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    on_dark = _legend_swatch(["rgb(0,0,0)"] * 4, dark)
    on_light = _legend_swatch(["rgb(255,255,255)"] * 4, light)
    assert lum(on_dark) > lum(dark) + 0.3, on_dark
    assert lum(on_light) < lum(light) - 0.2, on_light


def test_the_save_dialog_opens_at_a_size_that_fits_a_screen(app):
    """It had grown to twenty-one switches in five groups and opened taller
    than most windows anybody keeps open -- 1,138 points on a 1440-point
    screen. Reported as "pretty high ... maybe not strictly limited, a smaller
    default", which is exactly right: the ceiling is on the list inside, not
    on the dialog, so dragging it taller still works."""
    import gamut_app
    dialog = gamut_app.WebPageDialog(None)
    dialog.show()
    app.processEvents()
    screen = app.primaryScreen().availableGeometry().height()
    assert dialog.height() < 0.8 * screen, (
        f"the dialog opens {dialog.height()} tall on a {screen} screen")
    area = dialog.findChild(gamut_app.FadingScrollArea)
    assert area is not None, "the list of switches no longer scrolls"
    dialog.close()


def test_the_scrolling_list_fades_at_the_edge_that_has_more_past_it(app):
    """A list clipped by a hard line reads as a list that has ended -- which
    is how a whole group of switches goes unnoticed. The fade is on whichever
    end still has something beyond it, and on neither when it all fits."""
    import gamut_app
    dialog = gamut_app.WebPageDialog(None)
    dialog.show()
    app.processEvents()
    area = dialog.findChild(gamut_app.FadingScrollArea)
    bar = area.verticalScrollBar()
    if bar.maximum() <= 0:
        dialog.close()
        return                      # a very tall screen: nothing to scroll
    bar.setValue(0)
    app.processEvents()
    top, bottom = area.fades()
    assert top == 0 and bottom > 0, "at the start only the bottom may fade"
    bar.setValue(bar.maximum())
    app.processEvents()
    top, bottom = area.fades()
    assert top > 0 and bottom == 0, "at the end only the top may fade"
    dialog.close()
