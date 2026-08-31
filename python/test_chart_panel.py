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
import re
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
    """⚠ THIS TEST USED TO PIN A CONTRADICTION, and a colour-management
    practitioner walked straight into it.

    It asserted that a verdict saying "1 on the edge" ALSO said "Every patch
    sits inside the profile it was placed through". Both sentences were
    printed, one under the other, and they cannot both be true. Knut, on his
    own printer profile and 1,168-patch chart: "showed patches outside the
    gamut, and not all of them red highlighted." He was right — 184 of his
    patches really do sit outside the surface, by at most 0.68 ΔE2000 — and
    the page told him every patch was inside.

    `Outside.all_inside` means "none far enough out to MARK", which is a
    different claim from "none outside". The words now say which is which.
    """
    said = verdict("P", [0.0, 0.0, -0.05], same_profile=True)
    assert "1 on the edge, 0 outside" in said, said
    assert "Every patch sits inside" not in said, (
        "the verdict claims every patch is inside while its own first line "
        f"says one is on the edge: {said!r}")
    # It must NAME them, say how far, and say why they are not marked —
    # otherwise a dot drawn outside a shape with no mark reads as a broken
    # check, which is exactly how this was reported.
    assert "hair outside" in said, said
    assert "ΔE2000" in said, said
    assert "most people would not notice" in said, said


def test_when_nothing_is_even_on_the_edge_it_still_says_so_plainly(app):
    """THE OTHER HALF, so the fix above cannot swallow the clean case. A chart
    genuinely wholly inside must still get the short, reassuring sentence."""
    said = verdict("P", [0.0, 0.0, 0.0], same_profile=True)
    assert "0 on the edge, 0 outside" in said, said
    assert "Every patch sits inside" in said, said
    assert "hair outside" not in said, said


def test_a_long_way_outside_the_placing_profile_names_the_real_causes(app):
    """Far out and in numbers is not sampling — it is the chart builder, and
    the four things that do it are worth naming rather than making somebody
    guess."""
    far = np.array([[50.0, 90, 90]] * 40)
    said = verdict("P", far, same_profile=True)
    assert "Something differs" in said
    for cause in ("intent", "255", "clipped", "different profile"):
        assert cause in said, cause


def test_against_a_measurement_the_edge_patches_are_named_too(app):
    """THE OTHER JUDGING MODE, AND IT WAS MISSED THE FIRST TIME.

    When the same-profile branch stopped claiming "every patch sits inside"
    over its own "N on the edge", this branch went on doing it: it printed
    "193 on the edge" and then "Everything this chart asks for is within
    reach", with the dots visibly outside the shape and unmarked. That is
    Knut's complaint exactly, in the mode that judges a chart against a
    MEASUREMENT rather than against the profile that placed it.

    Fixing one branch and not its twin is how a fault survives being fixed.
    """
    said = verdict("Matte", [0.0, 0.0, -0.05], same_profile=False)
    assert "1 on the edge" in said, said
    assert "Everything this chart asks for is within reach" not in said, (
        f"the verdict claims everything is within reach while its own first "
        f"line says one patch is on the edge: {said!r}")
    assert "hair outside" in said, said
    assert "most people would not notice" in said, said


def test_against_a_measurement_a_clean_chart_still_reads_cleanly(app):
    """And the reassuring sentence must survive for a chart that really is
    wholly inside, or the fix above has simply traded one wrong answer for
    another."""
    said = verdict("Matte", [0.0, 0.0, 0.0], same_profile=False)
    assert "0 on the edge" in said, said
    assert "within reach" in said, said
    assert "hair outside" not in said, said


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
    """It had grown to twenty-two switches in five groups and opened taller
    than most windows anybody keeps open -- 1,138 points on a 1440-point
    screen. Reported as "pretty high ... maybe not strictly limited, a smaller
    default", which is exactly right: the ceiling is on how tall it OPENS, so
    dragging it taller still works."""
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


#: Screen heights worth proving this on. 800 is what the Windows CI runner
#: reports and is where this last broke; 720 and 640 are a small laptop and a
#: half-height window, both of which a printer plausibly works on.
@pytest.mark.parametrize("room", [1440, 1080, 900, 800, 720, 640])
def test_the_save_dialog_fits_a_small_screen_too(app, room):
    """THE ONE THAT WOULD HAVE CAUGHT IT. The first version of this ceiling
    capped the scrolling LIST rather than the window, and capping the part
    that scrolls does not cap the window: everything else in the dialog is
    fixed, and how tall that comes out depends on the platform's fonts and
    margins. Measured on Windows, where it slipped through: **874 points tall
    on an 800-point screen**, with the list already at its cap and the Save
    button below the bottom of the screen.

    The test that was there could not see it, because it asked about the
    screen the test was running on -- and on the machine this is developed on
    there is 1440 points of it, where even the broken version fitted. So this
    one hands the dialog a height instead of asking for one.
    """
    import gamut_app
    from PyQt6.QtWidgets import QPushButton
    dialog = gamut_app.WebPageDialog(None)
    dialog.show()
    app.processEvents()
    dialog.fit_within(room)
    app.processEvents()
    assert dialog.height() <= room, (
        f"on a {room}-point screen the dialog is {dialog.height()} tall, "
        f"so {dialog.height() - room} points of it are off the bottom")
    # AND THE SAVE BUTTON IS STILL REACHABLE, which is the thing that actually
    # matters -- a dialog can be the right height and still have its buttons
    # clipped if the list refuses to give up any room.
    buttons = [b for b in dialog.findChildren(QPushButton)
               if "save" in b.text().lower()]
    assert buttons, "the Save button has gone"
    bottom = buttons[0].mapTo(dialog, buttons[0].rect().bottomLeft()).y()
    assert bottom <= dialog.height(), (
        f"the Save button ends {bottom - dialog.height()} points below the "
        f"bottom of a dialog {dialog.height()} tall")
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


# --- the message box, at every length a message actually reaches -------------

@pytest.fixture
def styled(app):
    """The application's real stylesheet, put on and taken off again.

    THE DIALOG IS TWO POINTS NARROWER WITH IT ON, because the card carries
    `border: 1px solid` and the border is drawn inside the fixed width. Two
    points is enough to clip a button, so a check run against a bare
    application is not checking the thing the user sees.

    It was found the bad way: these tests passed on their own and failed in a
    full run, because some other module had left a stylesheet on the shared
    QApplication. That made the result depend on test ORDER — so the
    stylesheet is put on deliberately here, and taken off afterwards so no
    other module inherits it.
    """
    import gamut_app
    was = app.styleSheet()
    app.setStyleSheet(gamut_app.stylesheet("dark"))
    yield app
    app.setStyleSheet(was)


@pytest.mark.parametrize("sentences", [1, 3, 10, 30, 60])
def test_a_long_message_never_gets_wider_than_its_own_window(styled, sentences):
    """A word-wrapping QLabel does not ask for the width its longest LINE
    needs. It asks for a width that stops the block becoming absurdly tall, so
    the more text it holds the wider it wants to be, whatever the lines say.

    This box is a fixed 470 points across, so that request cannot be granted
    and the layout silently overflows instead: measured at 610 wanted against
    470 given, which cut the right-hand end off BOTH buttons, on the dialog
    whose whole purpose is offering somebody those two buttons. Nothing warns
    about it — it simply comes up wrong.

    Parametrised by length because that is the axis the fault lives on: the
    short messages fitted by luck, and every one in the application was short
    until one of them grew.
    """
    import gamut_app
    from gamut_app import Notice
    body = " ".join(f"Sentence number {i} saying something ordinary."
                    for i in range(sentences))
    dialog = Notice(None, "A message with a reasonably long heading on it",
                    body, ok="Open the download page",
                    cancel="Choose the folder…")
    dialog.show()
    styled.processEvents()
    wanted = dialog.layout().minimumSize().width()
    assert wanted <= dialog.width(), (
        f"{sentences} sentences ask for {wanted} points inside a window "
        f"{dialog.width()} wide — {wanted - dialog.width()} points of it, "
        f"including the buttons, are cut off")
    # AND IT IS STILL THE DESIGNED MEASURE unless the buttons genuinely need
    # more. Letting it grow is the fix for Windows, where the same two buttons
    # ask for 632 points; letting it grow FREELY would lose the thing 470 was
    # chosen for, which is that every message is recognisably the same window.
    from gamut_app import Notice
    assert dialog.width() >= Notice.WIDTH
    dialog.close()


def test_both_buttons_are_whole_however_long_the_message(styled):
    """The consequence the reader actually meets. Width arithmetic can be
    right in the abstract and still leave a button with its label sliced in
    half, so this asks the question about the buttons themselves.

    THE BODY IS LONG ON PURPOSE, and was made longer after the first version
    of this check passed with the fix taken out — twenty-five short paragraphs
    did not push the label far enough to squeeze anything, so it was a green
    test guarding nothing at all. Sixty sentences is past the measured point
    where the label starts asking for more width than the window has.
    """
    import gamut_app
    from PyQt6.QtWidgets import QPushButton
    from gamut_app import Notice
    body = " ".join(f"Sentence number {i} saying something ordinary enough."
                    for i in range(60))
    dialog = Notice(None, "ArgyllCMS was not found", body,
                    ok="Open the download page", cancel="Choose the folder…")
    dialog.show()
    styled.processEvents()
    for button in dialog.findChildren(QPushButton):
        right = button.mapTo(dialog, button.rect().topRight()).x()
        assert right <= dialog.width(), (
            f"“{button.text()}” runs {right - dialog.width()} points past the "
            f"right-hand edge of the dialog")
        assert button.width() >= button.sizeHint().width(), (
            f"“{button.text()}” is {button.sizeHint().width() - button.width()} "
            "points narrower than its own text needs")
    dialog.close()


def test_the_box_grows_for_buttons_it_cannot_otherwise_fit(styled):
    """THE WINDOWS FAULT, pinned on every platform.

    470 points is a deliberate measure — it keeps every message recognisably
    the same window. It is also a number chosen on one machine. On Windows the
    same two buttons ask for 632, so "Open the download page" ran 134 points
    past the right-hand edge: the dialog whose whole purpose is offering that
    button clipped it, on the platform nobody was looking at.

    The width is a floor now. This proves the growing works by asking for
    buttons wide enough to force it anywhere, rather than waiting for a
    platform where the ordinary ones do.
    """
    import gamut_app
    from PyQt6.QtWidgets import QPushButton
    from gamut_app import Notice
    dialog = Notice(None, "A choice", "Short.",
                    ok="A deliberately very long button label indeed here",
                    cancel="Another rather long button label for good measure")
    dialog.show()
    styled.processEvents()
    assert dialog.width() > Notice.WIDTH, (
        "the box refused to grow, so its buttons are cut off")
    for button in dialog.findChildren(QPushButton):
        right = button.mapTo(dialog, button.rect().topRight()).x()
        assert right <= dialog.width(), f"“{button.text()}” is clipped"
        assert button.width() >= button.sizeHint().width()
    dialog.close()


def test_an_ordinary_message_keeps_the_measure_it_always_had(styled):
    """The growing must be the exception. If every message started sizing
    itself to its content, the one thing the fixed width was for — every
    message being recognisably the same window — would be gone."""
    from gamut_app import Notice
    for ok, cancel in ((("OK"), None), ("Yes", "Cancel"), ("Save", "Discard")):
        dialog = Notice(None, "A heading", "A sentence or two of ordinary "
                        "length, of the sort most of these carry.",
                        ok=ok, cancel=cancel)
        dialog.show()
        styled.processEvents()
        assert dialog.width() == Notice.WIDTH, (
            f"an ordinary message grew to {dialog.width()}")
        dialog.close()


# --------------------------------------------------------------------------
# Counted both ways
#
# ⚠ THE ARTEFACT THAT FOOLED THREE REVIEWERS OF THIS APPLICATION, and the
# owner's own decision about what to do with it, taken on 2026-08-30 with the
# three alternatives and their costs in front of him: say both numbers,
# always. A chart is placed through a profile's relative colorimetric table,
# where the paper's white IS L* 100 by definition; a measurement read
# absolutely keeps the white the instrument saw. Everything light then floats
# above the measured shape for no reason to do with the printer.
#
# The tick box already existed. So did a warning. So did a docstring
# recording the same measurement. Three people LOOKING FOR FAULTS read it as
# a printer fault anyway, so more words in the same place were not the
# answer.
# --------------------------------------------------------------------------


def both_ways(measured_beyond, own_beyond, white_l, ticked=False):
    """The sentence, with the two counts and the paper they came from.

    ⚠ `ticked` IS ACCEPTED AND IGNORED, deliberately: the sentence must not
    depend on it. It used to, and printed "the same answer: 255 outside" when
    the two answers were 255 and 178."""
    import gamut_app
    return gamut_app.GamutApp._counted_both_ways(
        None,
        SimpleNamespace(n_beyond=measured_beyond),
        SimpleNamespace(n_beyond=own_beyond),
        SimpleNamespace(white_lab=(white_l, -0.4, -3.3)))


def test_both_counts_are_printed_whichever_mode_the_reader_is_in(app):
    """The whole point: a reader must not have to know which mode they are in
    to read the line correctly."""
    off = both_ways(725, 7, 91.2, ticked=False)
    on = both_ways(725, 7, 91.2, ticked=True)
    for said in (off, on):
        assert "725 outside as your instrument measured the paper" in said
        assert "7 once the paper is judged against its own white" in said
    assert "8.8 L* apart" in off and "8.8 L* apart" in on, (
        "the same two numbers, the same way round, in both modes")


def test_the_lightness_gap_is_taken_from_the_file_not_from_a_constant(app):
    """A sentence carrying a hard-coded 8.8 would be wrong for everybody but
    the one printer it was written on."""
    assert "6.2 L* apart" in both_ways(150, 0, 93.8, ticked=False)
    assert "8.8 L* apart" in both_ways(725, 7, 91.2, ticked=False)
    assert "L* 93.8" in both_ways(150, 0, 93.8, ticked=False)


def test_a_paper_already_at_L100_does_not_claim_a_gap(app):
    """Nothing to explain, so nothing is said about it -- but the two counts
    are still both printed, because that is what was asked for."""
    said = both_ways(3, 3, 100.0, ticked=False)
    assert "L* apart" not in said
    assert "the same answer" in said and "3 outside" in said


def test_the_reader_is_told_where_the_switch_is(app):
    said = both_ways(725, 7, 91.2, ticked=False)
    assert "Judge each paper against its own white" in said, (
        "naming the control is the difference between a fact and an action")
    assert "What the colours are measured against" in said, (
        "and the box it lives in, because the panel is long")


def test_when_the_file_cannot_be_read_both_ways_the_old_warning_still_fires(
        app):
    """A Lab-only .ti3 is exactly that case: `read_ti3` refuses to read one
    against its own white, by design, because Lab is already referenced to a
    white point. Nothing may crash and the reader must still be told."""
    said = caution(measured=True, judging_relative=False)
    assert "measured against different whites" in said
    assert "Judge each paper against its own white" in said


# --------------------------------------------------------------------------
# What a ΔE number is allowed to claim about an eye
#
# ⚠ THE APPLICATION ASSERTED SOMETHING THE LITERATURE DOES NOT SUPPORT, in
# five places, in a three-tier verdict, and in the pages it exports: "below 1
# nobody can see the difference; above 3 anybody can".
#
# Paravina et al. 2015 (J Esthet Restor Dent 27(S1):S1-S9) put 50:50
# perceptibility at 0.8 ΔE00 and acceptability at 1.8 — psychometric MIDPOINTS,
# not cut-offs — so at the threshold this called invisible, half the observers
# see it. Published just-noticeable values across four studies span 1.0, 2.15,
# 2.3 and 3.0 (Thomas, Colantoni & Trémeau, CCIW 2013).
#
# And where two MEASUREMENTS are compared the instrument outweighs the eye:
# ICC White Paper 22 found two identical handheld instruments disagreeing on
# the same patch by 0.47 ΔEab on average and 1.01 at worst, as BIAS rather
# than noise.
#
# The thresholds are unchanged. Only the claim is.
# --------------------------------------------------------------------------


#: ⚠ THE SHAPE OF THE CLAIM, NOT A LIST OF ITS SPELLINGS. This check has now
#: failed FIVE times, each time because it was widened to cover the last
#: escape rather than the thing being claimed: exact phrases, then a missing
#: word boundary, then a hyphen, then a line break, then an ELIDED VERB
#: ("above 3 anybody can", with the "see" left off). Each patch caught the
#: previous escape and none caught the next.
#:
#: So: a person-word, then optionally some words, then can/could, then
#: optionally some words, then see — or the verb left off entirely at the end
#: of a clause. Plus the two idioms that say it without a person at all.
_CLAIMS = (
    # nobody can see / nobody could ever see / nobody with a good eye can see
    re.compile(r"\b(nobody|no[- ]one|anybody|anyone|everybody|everyone)\b"
               r"[-\s\w]{0,30}?\b(can|could)\b[-\s\w]{0,20}?\bsee\b", re.I),
    # "above 3 anybody can." — the verb elided at the end of the clause
    re.compile(r"\b(nobody|no[- ]one|anybody|anyone|everybody|everyone)\b"
               r"[-\s]{1,3}(can|could)\b\s*[.,;)]", re.I),
    re.compile(r"becomes visible at all", re.I),
    re.compile(r"\binvisible to (anyone|everybody|the eye|the naked eye)\b",
               re.I),
)

#: What makes a sentence a claim about a COLOUR difference rather than about
#: an email attachment or a legend key.
_TOPIC = re.compile(r"ΔE|\bdE\b|Delta ?E|difference|moved|band", re.I)


def test_no_wording_anywhere_claims_a_difference_is_invisible_to_everyone(app):
    """⚠ THIS SWEEP FAILED ONCE, AND THE WAY IT FAILED IS THE LESSON.

    Its first version matched six EXACT PHRASES. Two live sentences were
    spelled differently — "Nothing has moved that anybody could see" and
    "below the point at which a difference becomes visible at all" — so it
    reported success while both were still on screen, one of them written
    into the pages this application exports. A list of strings can only find
    the strings somebody already thought of.

    So it matches the CLAIM now, as a pattern, and it reads string literals
    through `ast` rather than raw source: a grep over the text flags this
    repository's own record of what was corrected, and flags "anybody can
    make the window bigger", neither of which a reader ever meets.
    """
    import ast
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent
    # (nobody|anybody|no one|nothing) ... (can|could) see  — any wording.
    # ⚠ EVERY FORM IT HAS ESCAPED IN, and each of these was a real escape:
    # a space, a hyphen ("nobody-can-see-this band", in an alt attribute), and
    # a line break inside the sentence. Spelled-out "Delta E" counts as the
    # topic too, because a page wrote it that way.
    claims = _CLAIMS
    seen = 0
    # ⚠ references.py WAS NOT SCANNED, and a live sentence sat in it. A
    # sweep that names its own files will always name too few, so this takes
    # every module in the package.
    sources = [f for f in root.glob("*.py") if not f.name.startswith("test_")]
    sources += sorted((root.parent / "scripts").glob("*.py"))
    for source in sorted(sources):
        name = source.name
        tree = ast.parse(source.read_text())
        docs = set()
        for holder in ast.walk(tree):
            if isinstance(holder, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                   ast.AsyncFunctionDef)):
                body = getattr(holder, "body", None)
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    docs.add(id(body[0].value))
        # ⚠ f-STRINGS TOO. An f-string is a JoinedStr of pieces, so a claim
        # with a value interpolated into the middle of it is invisible to a
        # scan of plain constants — proven by putting one there.
        texts = []
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                joined = "".join(
                    part.value if isinstance(part, ast.Constant)
                    and isinstance(part.value, str) else " 0 "
                    for part in node.values)
                texts.append((node.lineno, joined))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docs:
                continue
            texts.append((node.lineno, node.value))
        for lineno, text in texts:
            node = type("N", (), {"value": text, "lineno": lineno})()
            seen += 1
            for claim in claims:
                for found in claim.finditer(node.value):
                    # ⚠ THE TOPIC MUST BE IN THE CLAIM'S OWN SENTENCE, not
                    # merely somewhere in the same constant. "everybody can
                    # see it without clicking" is about a PNG opening in an
                    # email, and "a key nobody can see" sits inside a
                    # thousand-line block of JavaScript that happens to say
                    # "difference" elsewhere. Flagging either would teach the
                    # next person to delete the sweep rather than fix a
                    # sentence.
                    near = node.value[max(0, found.start() - 140):
                                      found.end() + 140]
                    if not _TOPIC.search(near):
                        continue
                    raise AssertionError(
                        f"{name}:{node.lineno} still tells a reader "
                        f"{found.group(0)!r} — the thresholds may stay, the "
                        "claim about eyes may not")
    assert seen > 500, (
        f"only {seen} strings were scanned; this sweep is not looking at the "
        "application")


def test_the_sweep_catches_the_two_it_once_missed(app):
    """A measurement that cannot see the thing looks exactly like one that
    found nothing wrong. These are the exact sentences that were live in the
    application while the first version of the sweep reported success."""
    import re
    claims = (
        re.compile(r"\b(nobody|no one|anybody|anyone|everybody|everyone)\b"
                   r"[^.]{0,40}?\b(can|could)\s+see", re.I),
        re.compile(r"becomes visible at all", re.I),
    )
    missed = (
        "Nothing has moved that anybody could see. From 2019 to 2024 the "
        "biggest difference is ΔE 0.42, which is below the point at which a "
        "difference becomes visible at all.",
        "Two profiles: nothing here that anybody could see. The biggest "
        "difference anywhere in the cube is ΔE 0.31, below the point at "
        "which a difference becomes visible at all.",
        "below 1 nobody can see the difference; above 3 anybody can",
        "Nothing anybody could see.",
    )
    for sentence in missed:
        assert any(c.search(sentence) for c in claims), (
            f"the sweep still cannot see {sentence[:60]!r}")
    # And it must NOT fire on prose that merely shares the words.
    innocent = ("A picture goes straight into a forum post, an email or a "
                "document, and everybody can see it without clicking.")
    assert not any(c.search(innocent) for c in claims) or not re.search(
        r"ΔE|\bdE\b|difference|moved", innocent, re.I), (
        "the sweep flags a sentence about email attachments")


def test_the_hedge_is_one_sentence_used_everywhere_not_eight_copies(app):
    """A number set in eight places drifts, and then one panel disagrees with
    another about what an eye can do."""
    import gamut_app
    said = gamut_app.DE_RULES_OF_THUMB
    assert "rules of thumb rather than cut-offs" in said
    assert "0.8 to 3" in said, "the published range is the whole point"
    assert "two identical instruments can disagree" in said


def test_the_drift_verdict_names_the_instrument_when_the_drift_is_tiny(app):
    """A drift smaller than the instrument's own disagreement may BE the
    instrument. Saying so is the difference between a reader chasing it and a
    reader letting it go."""
    import gamut_app
    say = gamut_app.GamutApp._drift_verdict

    small = say(None, 0.62)
    assert "Most people would not notice this" in small
    assert "two identical instruments can disagree" in small, (
        "a drift under the instrument's own bias must say so")

    big = say(None, 2.56)
    assert "A careful eye would find this" in big
    assert "instruments can disagree" not in big, (
        "at 2.56 the instrument is not the explanation, and offering it "
        "would be an excuse rather than a fact")
    assert "Hard to miss." in say(None, 4.0)

    # And the profile wording differs, because a profile is not a reading.
    both = say(None, 0.62, profiles=True)
    assert "Each profile is built from measurements" in both
    assert "need not mean the device moved" in both


def test_one_verdict_serves_both_boxes(app):
    """⚠ IT WAS WRITTEN OUT TWICE, and when the measurement one was corrected
    the profile one kept saying "Nothing anybody could see." A sweep found it,
    review did not. One function now answers for both."""
    import inspect
    import gamut_app
    src = inspect.getsource(gamut_app.GamutApp)
    assert src.count("Most people would not notice this") == 1, (
        "the sentence is written more than once again, which is how the two "
        "boxes came to disagree")
    assert src.count("_drift_verdict(") == 3, (
        "one definition and two callers, no more and no less")


# --------------------------------------------------------------------------
# What the coverage number MEANS for the work
#
# ⚠ A WHOLE FEATURE WAS PLANNED ON TOP OF A NUMBER THIS PANEL ALREADY PRINTS.
# "Practical vs total gamut" was to be a new table answering "how much of your
# printer survives working in sRGB" — and the window has answered it all
# along: "90.6% of the colour knut can print also fits inside sRGB",
# photographed in the running application before a line was written.
#
# What was missing was never the arithmetic. It was that 90.6% reads as a
# fault in the printer when it is a limit of the space the reader chose, and
# that is the half they can act on.
# --------------------------------------------------------------------------


def coverage_text(ab, ba, kind, a_name="knut", b_name="sRGB", picture=False):
    import gamut_app
    said = {}
    stub = SimpleNamespace(
        _reference=(b_name, object()),
        _slots=[(SimpleNamespace(stem=a_name), object(), None)],
        _shared_lbl=SimpleNamespace(setText=lambda t: None),
        _reach=SimpleNamespace(setText=lambda t: None),
        _how_much_fits=lambda a, b: (ab, ba),
        _coverage=SimpleNamespace(setText=lambda t: said.setdefault("t", t)),
        _picture_loss=SimpleNamespace(setText=lambda t: None),
        _pair_box=SimpleNamespace(setVisible=lambda v: None),
        _compare=SimpleNamespace(currentData=lambda: kind),
        _is_picture=lambda name: picture,
        _update_picture_loss=lambda *a: None,
        _update_pair=lambda *a: None)
    gamut_app.GamutApp._update_coverage(stub)
    return said.get("t", "")


def test_the_share_that_does_not_fit_is_named_as_the_spaces_limit(app):
    said = coverage_text(0.906, 0.400, ("space", "sRGB"))
    assert "90.6% of the colour knut can print also fits inside sRGB" in said
    assert "The other 9.4%" in said
    assert "not a fault in knut" in said, (
        "the number reads as a fault in the printer unless it says otherwise")
    assert "limit of the working space you chose" in said


def test_against_another_paper_no_such_claim_is_made(app):
    """A paper is not a working space, and telling somebody their choice of
    space cost them 9% when they are comparing two papers would be nonsense."""
    said = coverage_text(0.906, 0.400, ("icc", None), b_name="Matte-paper")
    assert "The other" not in said
    assert "working space" not in said


def test_a_photograph_is_not_told_it_chose_a_working_space(app):
    said = coverage_text(0.906, 0.400, ("space", "sRGB"), picture=True)
    assert "The other" not in said


def test_a_space_that_holds_everything_claims_no_loss(app):
    """At 100% there is nothing to explain, and inventing 0.0% to explain
    would be noise."""
    said = coverage_text(0.9995, 0.30, ("space", "ProPhoto"))
    assert "The other" not in said


def test_the_both_ways_line_cannot_consult_the_tick_at_all(app):
    """⚠ THE FALSE NUMBER, PINNED AT ITS CAUSE.

    The first version asked for "the other reading" and trusted that the drawn
    shape was the one the tick named. For a paper in a slot that holds; for a
    paper opened as the COMPARISON it does not, because that shape is built
    through a reader that takes no paper-white setting. With the tick on, both
    halves were the absolute reading and the panel announced:

        "Counted both ways it is the same answer: 255 outside"

    when the two answers were 255 and 178. v2.53.2 printed nothing there, so
    silence was replaced by a confident falsehood, in the mode a careful
    reader deliberately turns on.

    The cure is structural: the sentence is handed two finished counts and
    cannot reach the tick, the slots, or the drawn shape.
    """
    import inspect
    import gamut_app
    src = inspect.getsource(gamut_app.GamutApp._counted_both_ways)
    for reachable in ("_relative", "_slots", "_compare", "self."):
        assert reachable not in src, (
            f"the sentence can still reach {reachable!r}, which is how it "
            "came to be wrong about which count was which")
    # And the two counts keep their names whatever order anything else is in.
    said = both_ways(255, 178, 92.1)
    assert "255 outside as your instrument measured the paper" in said
    assert "178 once the paper is judged against its own white" in said
    assert "the same answer" not in said


def test_the_paper_white_is_carried_into_whatever_space_is_drawn(app):
    """Limiting it to CIELAB undid the whole fix the moment somebody chose
    CIELUV: the same file read "L* 94 and cool" in CIELAB and "L* 96 and very
    warm (a* +61.1, b* +87.1)" in CIELUV, because the fallback went back to
    taking the lightest vertex — the yellow."""
    import gamut_app
    from types import SimpleNamespace as NS

    def carried(space):
        stub = NS(_space=NS(currentData=lambda: space),
                  _white=NS(currentData=lambda: "D50"))
        return gamut_app.GamutApp._white_in_this_space(stub, (93.8, -0.4, -3.3))

    lab = carried("lab")
    assert lab == pytest.approx((93.8, -0.4, -3.3), abs=1e-9)
    luv = carried("luv")
    assert luv is not None, "CIELUV threw the paper's white away"
    assert luv[0] == pytest.approx(93.8, abs=0.01), (
        "lightness is the same number in both spaces; only u* and v* differ")
    assert luv[1:] != lab[1:], "it was not converted, merely passed through"
    assert carried("xyz") is not None
    # Nothing to carry is not a failure.
    stub = NS(_space=NS(currentData=lambda: "luv"),
              _white=NS(currentData=lambda: "D50"))
    assert gamut_app.GamutApp._white_in_this_space(stub, None) is None


def test_no_document_or_script_publishes_the_claim_either(app):
    """⚠ F1 AND F2 SHIPPED PAST THIS CHECK TWICE, because it read Python and
    nothing else. The claim lives in the settings reference, the README, the
    front page, the showcase index and the page builders — and those are the
    copies a reader is most likely to meet, because they are the published
    ones."""
    import html
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    looked = 0
    # ⚠ NOT THE CHANGELOG. It records what the application SAID at each
    # release, quoting the old verdicts to explain what was fixed; rewriting
    # those would falsify the history rather than correct a claim. Python
    # under scripts/ goes through the source sweep above, which reads string
    # literals and so does not trip over a comment quoting the old wording.
    # ⚠ rglob, NOT glob. The first version used four flat patterns and so
    # read 13 files and missed 50 — INCLUDING ALL EIGHT PUBLISHED PAGES THE
    # SAME COMMIT HAD TO CORRECT. It was titled "the check that should have
    # caught six of them" and could not have caught them. The matching was
    # generalised and the SCOPE was left behind: the identical mistake one
    # level up, in the change that was meant to end it.
    for f in sorted(list(root.rglob("*.md")) + list(root.rglob("docs/**/*.html"))
                    + list(root.glob("docs/*.html"))):
        if f.name == "CHANGELOG.md":
            continue
        if "/scratch/" in str(f) or "/.git/" in str(f):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        if f.suffix == ".html":
            text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.S | re.I)
            # ⚠ ATTRIBUTE TEXT IS TEXT A READER MEETS. `alt`, `title` and
            # `aria-label` are read aloud by a screen reader and shown on
            # hover, and stripping the tags threw all of them away — 27 of
            # them ship in these pages today, and one of the claims escaped
            # in an alt attribute once already ("nobody-can-see-this band").
            # They are lifted out BEFORE the tags go.
            spoken = " ".join(
                m.group(1) for m in re.finditer(
                    r"""\b(?:alt|title|aria-label)\s*=\s*["']([^"']*)["']""",
                    text, re.I))
            text = re.sub(r"<(?!/?(img|a)\b)[^>]+>", " ", text)
            text = html.unescape(text) + " " + html.unescape(spoken)
        flat = " ".join(text.split())      # a line break must not hide it
        looked += 1
        for claim in _CLAIMS:
            for found in claim.finditer(flat):
                near = flat[max(0, found.start() - 140): found.end() + 140]
                if _TOPIC.search(near):
                    raise AssertionError(
                        f"{f.relative_to(root)} publishes "
                        f"{found.group(0)!r} — …{near[:150]}…")
    # ⚠ A FLOOR THAT THE OLD SCOPE PASSED AT 13 while missing 50 files is not
    # a floor. It is pinned to the published pages, which are the copies a
    # reader is most likely to meet.
    assert looked > 45, (
        f"only {looked} documents were read; the published pages are the "
        "ones this exists for")


def test_the_document_sweep_catches_every_form_that_escaped_it(app):
    """Each of these was live in this repository while a check reported
    success. They are the test, not examples of it."""
    import re
    escapes = (
        "below ΔE 1 most people would not notice the difference, above 3 "
        "anybody can, and red means the same amount",
        "every step inside the band nobody-can-see-this",
        "a difference nobody could ever see, ΔE 0.4",
        "a difference nobody with a good eye can see, ΔE 0.4",
        "a difference invisible to the naked eye, ΔE 0.4",
        "Nothing has moved that anybody could see. The biggest difference "
        "is ΔE 0.42",
    )
    for sentence in escapes:
        flat = " ".join(sentence.split())
        hit = any(c.search(flat) for c in _CLAIMS)
        assert hit and _TOPIC.search(flat), (
            f"the sweep still cannot see {sentence[:60]!r}")


# --------------------------------------------------------------------------
# One keying rule for every cache of a built shape
#
# ⚠ THREE CACHES, THREE DIFFERENT IDEAS OF WHAT CHANGES A SHAPE. Each keyed on
# "everything that matters" as its author imagined it, and each imagined a
# different set. The costliest held Detail — which nothing that builds a shape
# from a FILE consults — so every Detail nudge was a guaranteed miss returning
# a bit-identical answer, 3.67 s at a time on a photograph.
# --------------------------------------------------------------------------


def shape_key(name, space="lab", relative=None, white="D50", mode="device",
              stamp=None):
    import gamut_app
    from types import SimpleNamespace as NS
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    stub = NS(_white=NS(currentData=lambda: white),
              _mode=NS(currentData=lambda: mode))
    return gamut_app.GamutApp._shape_key(stub, root / name, space,
                                         relative=relative)


def test_detail_is_not_in_the_key_of_any_file_built_shape(app):
    """`_detail` reaches `reference_gamut(steps=)` and
    `optimal_colour_solid()` and nothing else — the two SYNTHETIC references.
    A file's shape does not depend on it, so nor may its key."""
    import ast
    import gamut_app
    import inspect
    # ⚠ THE CODE, NOT THE PROSE. The docstring explains why Detail is absent,
    # and a check over raw source flags its own explanation — which is how
    # the wording sweep failed twice.
    fn = ast.parse(inspect.getsource(gamut_app.GamutApp._shape_key).strip()).body[0]
    body = fn.body[1:] if (isinstance(fn.body[0], ast.Expr)
                           and isinstance(fn.body[0].value, ast.Constant)) else fn.body
    code = "\n".join(ast.unparse(stmt) for stmt in body)
    assert "_detail" not in code, (
        "Detail is back in the key, and every nudge of it is a miss")
    for name in ("demo/Glossy-paper.ti3", "demo/Glossy-paper.icc"):
        assert shape_key(name) == shape_key(name), "the key is not stable"


def test_the_key_carries_the_file_s_own_timestamp(app):
    """A cache keyed by path alone answers for the shape a file USED to have.
    The guard against that was "remember to clear all three caches", which had
    already been half-forgotten once; a timestamp cannot be forgotten."""
    key = shape_key("demo/Glossy-paper.ti3")
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    stamp = (root / "demo/Glossy-paper.ti3").stat().st_mtime_ns
    assert stamp in key, f"no timestamp in {key}"


def test_the_tick_and_the_mode_reach_a_measurement_and_not_a_profile(app):
    """Neither reaches a profile or a photograph, so putting them in their
    key costs misses and buys nothing."""
    ti3 = "demo/Glossy-paper.ti3"
    icc = "demo/Glossy-paper.icc"
    assert shape_key(ti3, relative=True) != shape_key(ti3, relative=False)
    assert shape_key(ti3, mode="hull") != shape_key(ti3, mode="device")
    assert shape_key(icc, relative=True) == shape_key(icc, relative=False), (
        "the paper-white tick does not reach a profile")
    assert shape_key(icc, mode="hull") == shape_key(icc, mode="device"), (
        "the shape mode does not reach a profile")


def test_an_entry_holding_both_readings_does_not_depend_on_the_tick(app):
    """`_both_whites` holds the absolute AND the own-white reading together,
    so the tick cannot change what it should hand back."""
    ti3 = "demo/Glossy-paper.ti3"
    assert shape_key(ti3, relative=None) == shape_key(ti3, relative=None)
    assert shape_key(ti3, relative=None) != shape_key(ti3, relative=True)


def test_the_white_point_and_the_space_are_always_in_the_key(app):
    ti3 = "demo/Glossy-paper.ti3"
    assert shape_key(ti3, white="D50") != shape_key(ti3, white="D65")
    assert shape_key(ti3, space="lab") != shape_key(ti3, space="luv")


# --------------------------------------------------------------------------
# A comparison that is not a file
#
# ⚠ TWO FAULTS, ONE CAUSE, AND FIXING EITHER ALONE MAKES THINGS WORSE.
#
# A comparison set to a colour space or to the visible solid has no file. The
# consolidated cache key called `Path(None)` on it and crashed the window on
# an ordinary "Draw it in" change — two unhandled TypeErrors, and the scene
# left showing CIELUV under a control reading CIE XYZ.
#
# And underneath that crash sat an older wrong answer: with no file and no
# measurement nothing could be rebuilt in CIELAB, so a chart was counted
# against a gamut drawn in another space — "sRGB: 0 inside, 0 on the edge,
# 480 outside, worst 99.0 ΔE". Guarding the None alone would have traded the
# crash back for that sentence, which is the worse of the two.
# --------------------------------------------------------------------------


def test_a_shape_with_no_file_is_refused_by_the_file_key(app):
    """`_shape_key` is for files, and says so instead of raising TypeError
    from `Path(None)` — which the OSError guard beside it cannot catch."""
    import gamut_app
    import pytest as _pytest
    from types import SimpleNamespace as NS
    stub = NS(_white=NS(currentData=lambda: "D50"),
              _mode=NS(currentData=lambda: "device"))
    with _pytest.raises(ValueError) as caught:
        gamut_app.GamutApp._shape_key(stub, None, "luv", relative=False)
    assert "_synthetic_key" in str(caught.value), (
        "it must point at the key that DOES answer for a shape with no file")


def test_judging_a_chart_by_a_colour_space_rebuilds_it_in_cielab(app):
    """The half that was left open. A colour space has no file, but it has a
    name, and this window can build it in whatever space it likes."""
    import gamut_app
    from types import SimpleNamespace as NS
    from references import reference_gamut
    drawn = reference_gamut("sRGB", white_point="D50", steps=9, space="luv")
    assert drawn.space == "luv"
    stub = NS(_reference=("sRGB", drawn), _reference_path=None,
              _compare=NS(currentData=lambda: ("space", "sRGB")),
              _white=NS(currentData=lambda: "D50"),
              _detail=NS(value=lambda: 9),
              _lab_gamuts={})
    # bound to the real one, so a change to how it is keyed reaches this test
    stub._synthetic_key = lambda choice: gamut_app.GamutApp._synthetic_key(
        stub, choice)
    built = gamut_app.GamutApp._reference_in_lab(stub)
    assert built is not None
    assert built.space == "lab", (
        "a chart's patches are CIELAB; judging them against a shape drawn in "
        "CIELUV is what printed 480 of 480 outside at ΔE 99")
    assert built is not drawn
    # And it is cached, so the second ask costs nothing.
    assert gamut_app.GamutApp._reference_in_lab(stub) is built


def test_a_comparison_already_in_cielab_is_handed_back_untouched(app):
    import gamut_app
    from types import SimpleNamespace as NS
    from references import reference_gamut
    lab = reference_gamut("sRGB", white_point="D50", steps=9, space="lab")
    stub = NS(_reference=("sRGB", lab), _reference_path=None,
              _compare=NS(currentData=lambda: ("space", "sRGB")),
              _white=NS(currentData=lambda: "D50"),
              _detail=NS(value=lambda: 9), _lab_gamuts={})
    stub._synthetic_key = lambda choice: gamut_app.GamutApp._synthetic_key(
        stub, choice)
    assert gamut_app.GamutApp._reference_in_lab(stub) is lab


def test_no_comparison_at_all_is_not_an_error(app):
    import gamut_app
    from types import SimpleNamespace as NS
    assert gamut_app.GamutApp._reference_in_lab(NS(_reference=None)) is None


def test_detail_belongs_in_the_key_of_a_shape_that_has_no_file(app):
    """The mirror of the file rule: `_detail` reaches `reference_gamut(steps=)`
    and `optimal_colour_solid()` and nothing else, so it belongs HERE and
    nowhere else."""
    import gamut_app
    from types import SimpleNamespace as NS
    stub = NS(_white=NS(currentData=lambda: "D50"), _detail=NS(value=lambda: 9))
    nine = gamut_app.GamutApp._synthetic_key(stub, ("space", "sRGB"))
    stub._detail = NS(value=lambda: 17)
    seventeen = gamut_app.GamutApp._synthetic_key(stub, ("space", "sRGB"))
    assert nine != seventeen, "Detail really does change a synthetic shape"


# --------------------------------------------------------------------------
# Marking a chart against a comparison that has no slot
#
# ⚠ THE PICTURE AND THE SENTENCE CAME APART BY A FACTOR OF THREE. Teaching
# `_judging_shapes` to rebuild a fileless comparison in CIELAB left
# `_chart_marked_against` on the old route, where `_in_lab` hands back the
# shape in the DRAWN space. With a chart, Compare with = sRGB and Draw it in
# = CIE XYZ, room two painted 480 of 480 patches unreachable while the
# numbers beside it said 143.
#
# ⚠ AND THE TEST THAT ALREADY DROVE THIS CALL COULD NOT SEE IT, because it
# built both shapes in CIELAB — where `_in_lab` returns on its first line.
# These build the comparison in another space, which is the whole point.
# --------------------------------------------------------------------------


def marked_against(drawn_space, chart_lab, reference_space="luv"):
    """What `_chart_marked_against` marks, with no slot and no file."""
    import gamut_app
    import numpy as np
    from types import SimpleNamespace as NS
    from references import reference_gamut
    drawn = reference_gamut("sRGB", white_point="D50", steps=9,
                            space=reference_space)
    stub = NS(_reference=("sRGB", drawn), _reference_path=None,
              _compare=NS(currentData=lambda: ("space", "sRGB")),
              _white=NS(currentData=lambda: "D50"),
              _detail=NS(value=lambda: 9), _lab_gamuts={},
              _in_lab=lambda g, p=None, m=None: g)
    stub._synthetic_key = lambda choice: gamut_app.GamutApp._synthetic_key(
        stub, choice)
    stub._reference_in_lab = lambda: gamut_app.GamutApp._reference_in_lab(stub)
    chart = ("chart", np.asarray(chart_lab, float), None, None)
    return gamut_app.GamutApp._chart_marked_against(stub, chart, drawn, None)


def test_a_chart_is_marked_against_the_comparison_rebuilt_in_cielab(app):
    import numpy as np
    # Two patches sRGB reaches easily, one it cannot: a saturated cyan.
    lab = [[50.0, 0.0, 0.0], [80.0, 5.0, -5.0], [55.0, -40.0, -55.0]]
    got = marked_against("xyz", lab, reference_space="luv")
    assert got[2] is not None, (
        "the comparison has no file, but it has a name — it must still be "
        "rebuilt in CIELAB rather than left unmarked")
    assert int(np.asarray(got[2]).sum()) < len(lab), (
        "marking every patch outside is what a wrong-space shape does")


def test_nothing_is_marked_when_no_cielab_shape_can_be_had(app):
    """A chart's patches are CIELAB. Measuring them against a shape built in
    another space is not a worse answer — it is a different question answered
    confidently, and the honest reply is to mark nothing."""
    import gamut_app
    import numpy as np
    from types import SimpleNamespace as NS
    from references import reference_gamut
    drawn = reference_gamut("sRGB", white_point="D50", steps=9, space="luv")
    stub = NS(_reference=None, _in_lab=lambda g, p=None, m=None: g)
    chart = ("chart", np.asarray([[50.0, 0.0, 0.0]], float), None, None)
    got = gamut_app.GamutApp._chart_marked_against(stub, chart, drawn, None)
    assert got[2] is None, "it marked patches against a shape in CIELUV"


def test_the_comparison_is_rebuilt_before_the_papers(app):
    """⚠ `_rebuild()` REDRAWS INTERNALLY. Rebuilding the papers first meant a
    redraw met the papers in the new space beside a comparison still in the
    old one; `build_figure` refuses to label axes that do not match its
    shapes, the slot aborted, and the comparison was never rebuilt at all —
    CIELAB left on screen under a control reading CIE XYZ."""
    import ast
    import inspect
    import gamut_app
    for name in ("_on_space_changed", "_on_white_changed", "_on_shape_setting"):
        src = inspect.getsource(getattr(gamut_app.GamutApp, name))
        calls = [n for n in
                 (ast.unparse(x) for x in ast.walk(ast.parse(src.strip()))
                  if isinstance(x, ast.Call))
                 if n in ("self._rebuild()", "self._rebuild_reference()")]
        assert "self._rebuild_reference()" in calls, f"{name} forgets it"
        assert calls.index("self._rebuild_reference()") < \
            calls.index("self._rebuild()"), (
            f"{name} rebuilds the papers before the comparison, so a redraw "
            "meets a half-converted scene")


# --------------------------------------------------------------------------
# A photograph held as the comparison
#
# ⚠ THE THIRD MEMBER OF A FAMILY CLOSED TWICE. A .ti3 comparison was fixed by
# carrying its measurement; a colour space and the visible solid by a
# synthetic rebuild. A PICTURE is a file, so it took the branch neither
# repair touched: `_in_lab` read every non-.gam path as an ICC profile, the
# read raised, the drawn shape came back, and a chart was counted against a
# gamut in the wrong space — "0 inside, 0 on the edge, 480 outside, worst
# 99.0 ΔE" against a truth of 390.
#
# And because the picture had just been taught to mark nothing in that case
# while the sentence still printed a number, the two disagreed AGAIN, with
# the halves swapped.
# --------------------------------------------------------------------------


def test_a_picture_is_rebuilt_in_cielab_like_everything_else(app):
    """⚠ BEHAVIOUR, NOT SOURCE TEXT. The first version of this asserted that
    "IMAGE_EXTENSIONS" appeared in the function, and a mutant that wrapped
    the branch in `if False and ...` kept the words and passed. A test that
    reads the source is a test of the source."""
    import pathlib
    import gamut_app
    from types import SimpleNamespace as NS
    from references import reference_gamut
    root = pathlib.Path(__file__).resolve().parent.parent
    picture = next(iter(sorted((root / "docs").rglob("*.png"))), None)
    assert picture is not None, "no picture in the tree to try"
    drawn = reference_gamut("sRGB", white_point="D50", steps=9, space="luv")
    stub = NS(_white=NS(currentData=lambda: "D50"),
              _mode=NS(currentData=lambda: "device"),
              _relative=NS(isChecked=lambda: False),
              _lab_gamuts={})
    stub._shape_key = lambda path, space, relative=None: (
        gamut_app.GamutApp._shape_key(stub, path, space, relative=relative))
    built = gamut_app.GamutApp._in_lab(stub, drawn, picture, None)
    assert built is not drawn, (
        "the photograph was read as an ICC profile, raised, and the drawn "
        "shape came back — which is how a chart came to be counted against "
        "a gamut in CIE XYZ")
    assert built.space == "lab"


def test_a_chart_is_not_counted_against_a_shape_in_another_space(app):
    """The same rule the marking obeys: ΔE is defined on CIELAB and on
    nothing else, so a shape that could not be rebuilt there gets no number
    — it gets a sentence saying why. Driven through the real method."""
    import numpy as np
    import gamut_app
    from types import SimpleNamespace as NS
    from references import reference_gamut
    said = {}
    wrong = reference_gamut("sRGB", white_point="D50", steps=9, space="luv")
    stub = NS(
        _chart=("chart.ti1", NS(n_patches=3)),
        _chart_placed=NS(profile="a-profile"),
        _chart_profile=None,
        _drawing_in_ink=lambda: False,
        _chart_box=NS(setVisible=lambda v: None),
        _refresh_chart_look_box=lambda: None,
        _chart_headline=NS(setText=lambda t: None),
        _chart_rows=NS(setText=lambda t: said.setdefault("rows", t)),
        _chart_lab=lambda: np.array([[50.0, 0.0, 0.0], [80.0, 5.0, -5.0]]),
        _judging_shapes=lambda: [("sRGB", wrong, None, False)],
        _show_chart_spread=lambda in_ink: None,
        _both_whites=lambda path, measured: None,
        _white_mismatch_caution=lambda measured: "",
        _chart_verdict=lambda *a: "SHOULD NOT BE REACHED")
    gamut_app.GamutApp._update_chart_numbers(stub)
    rows = said.get("rows", "")
    assert "not counted here" in rows, rows
    assert "SHOULD NOT BE REACHED" not in rows, (
        "it counted the patches against a shape built in CIELUV")
    assert "CIELAB" in rows, "it must say why, not merely decline"


def test_a_photograph_is_called_a_picture_and_not_a_measurement(app):
    """It was labelled "(measured)" in every line about it, and it fired the
    white-point caution — telling the reader to tick "Judge each paper
    against its own white" about a photograph that has no paper and no
    white. A cause that is not the cause is worse than no explanation."""
    import gamut_app
    from pathlib import Path
    assert gamut_app._profile_label(Path("holiday.png")).endswith("(picture)")
    assert gamut_app._profile_label(Path("holiday.jpg")).endswith("(picture)")
    assert gamut_app._profile_label(Path("paper.ti3")).endswith("(measured)")
    assert gamut_app._profile_label(Path("printer.icc")).endswith("(profile)")
    assert gamut_app._profile_label(Path("shape.gam")).endswith("(gamut file)")


def test_the_white_point_caution_does_not_fire_for_a_picture(app):
    """`measured` decides whether the two-white caution is offered, and a
    photograph is not a measurement of a paper.

    ⚠ BEHAVIOUR, NOT SOURCE TEXT. The first version asserted that a word
    appeared in the function, and a mutant — `and (True or suffix not in
    IMAGE_EXTENSIONS)` — kept the word, SURVIVED THE WHOLE SUITE, and put
    "tick Judge each paper against its own white" back on screen under a
    photograph that has no paper and no white. This drives the real method
    and reads the flag it produces.
    """
    import pathlib
    import gamut_app
    from types import SimpleNamespace as NS
    from references import reference_gamut
    root = pathlib.Path(__file__).resolve().parent.parent
    lab = reference_gamut("sRGB", white_point="D50", steps=9, space="lab")

    def measured_flag(path):
        stub = NS(_slots=[], _reference=("thing", lab),
                  _reference_path=path, _reference_m=None,
                  _compare=NS(currentData=lambda: ("icc", None)),
                  _white=NS(currentData=lambda: "D50"),
                  _detail=NS(value=lambda: 9), _lab_gamuts={},
                  _in_lab=lambda g, p=None, m=None: g)
        stub._reference_in_lab = lambda: gamut_app.GamutApp._reference_in_lab(
            stub)
        rows = gamut_app.GamutApp._judging_shapes(stub)
        return rows[-1][3]

    assert measured_flag(root / "demo" / "Glossy-paper.ti3") is True, (
        "a measurement is measured")
    assert measured_flag(pathlib.Path("holiday.png")) is False, (
        "a photograph was counted as a measurement, so the window offered "
        "it advice about a paper white it does not have")
    assert measured_flag(pathlib.Path("printer.icc")) is False


# --------------------------------------------------------------------------
# What a photograph loses, measured in the right space
#
# ⚠ THE FOURTH SIBLING. `_update_picture_loss` measures a photograph's own
# colours — always CIELAB — against the other shape, and it was handed the
# DRAWN shape. With only "Draw it in" changed and nothing else, the same
# photograph against the same profile read 0%, then 1%, then 100% out of
# reach, worst 2.1 then 10.1 then 99.0 ΔE, with the panel saying "99.9% fits
# inside" and "100% is out of reach" three lines apart over a picture that
# plainly showed the photograph inside the shape. It shipped in v2.53.2.
# --------------------------------------------------------------------------


def test_a_picture_s_loss_is_not_measured_against_a_wrong_space_shape(app):
    import gamut_app
    from types import SimpleNamespace as NS
    from references import reference_gamut
    # ⚠ WATCH THE CALL, NOT THE TEXT. With dummy facts the measurement
    # raises and the text is empty whether the refusal fired or not — so an
    # empty panel proved nothing and a mutant that deleted the refusal
    # passed. What must be true is that the measurement is never ATTEMPTED
    # against a shape in the wrong space.
    # ⚠ THE OUTCOME, NOT THE CALL. The refusal moved into
    # `chart.outside_report`, so the caller now DOES ask and is refused —
    # asserting "it never asks" pinned the old mechanism, not the promise.
    # What must hold is that no figure reaches the reader.
    import numpy as np
    # ⚠ "weights", NOT "weight". The first version of this test spelled the
    # key wrong, so `out_of_reach` returned None on its own `weights is None`
    # line BEFORE the refusal was ever reached — and the empty label it then
    # asserted had nothing to do with the thing under test. It passed with
    # the refusal disabled: a false all-clear about the one caller whose
    # hand-written guard this commit deleted. `imagegamut.py:283` is the
    # spelling that matters.
    facts = {"lab": np.array([[50.0, 0.0, 0.0], [70.0, 20.0, -30.0]]),
             "weights": np.array([0.5, 0.5])}
    # ⚠ THE LAST value, not the first. `_update_picture_loss` CLEARS the
    # label before it does anything, so a `setdefault` stand-in captures that
    # empty string and ignores the real sentence that follows — making both
    # halves of this test pass no matter what the code does. Third instrument
    # of mine to lie today, all in the same way: it could not see the thing
    # it was watching.
    stub = NS(_picture_loss=NS(setText=lambda t: said.__setitem__("t", t)),
              _is_picture=lambda name: name == "holiday",
              _image_facts={"/tmp/holiday.png": facts})
    said = {}
    wrong = reference_gamut("sRGB", white_point="D50", steps=9, space="luv")
    gamut_app.GamutApp._update_picture_loss(stub, "holiday", None,
                                            "a-profile", wrong)
    assert said.get("t", "") == "", (
        "a figure was printed for a photograph measured against a CIELUV "
        f"shape: {said.get('t', '')!r}")
    # ⚠ AND THE POSITIVE HALF, or a refusal that fires ALWAYS passes too.
    said.clear()
    right = reference_gamut("sRGB", white_point="D50", steps=9, space="lab")
    gamut_app.GamutApp._update_picture_loss(stub, "holiday", None,
                                            "a-profile", right)
    assert said.get("t", ""), (
        "it must still answer when the shape IS in CIELAB")


def test_two_papers_with_no_comparison_get_cielab_twins_too(app):
    """⚠ THE MUTANT THAT SURVIVED ALL 1,186 TESTS. The new test drove only
    the reference branch, so removing the twins from the TWO-SLOT branch
    passed the whole suite. On screen it empties the line rather than
    printing a false figure — the refusal inside `_update_picture_loss`
    catches it — so it was a missing test rather than a shipped fault, and
    it is a test now."""
    import gamut_app
    import pathlib as _pathlib
    from types import SimpleNamespace as NS
    from references import reference_gamut
    lab = reference_gamut("sRGB", white_point="D50", steps=9, space="lab")
    luv = reference_gamut("sRGB", white_point="D50", steps=9, space="luv")
    got = {}
    stub = NS(
        _reference=None, _reference_path=None,
        _slots=[(_pathlib.Path("holiday.png"), luv, None),
                (_pathlib.Path("paper.ti3"), luv, None)],
        _how_much_fits=lambda a, b: (0.9, 0.4),
        _coverage=NS(setText=lambda t: None),
        _picture_loss=NS(setText=lambda t: None),
        _shared_lbl=NS(setText=lambda t: None),
        _reach=NS(setText=lambda t: None),
        _pair_box=NS(setVisible=lambda v: None),
        _compare=NS(currentData=lambda: None),
        _is_picture=lambda name: name == "holiday",
        _in_lab=lambda g, p=None, m=None: lab,
        _update_pair=lambda *a: None,
        _update_picture_loss=lambda *a: got.setdefault("args", a))
    gamut_app.GamutApp._update_coverage(stub)
    args = got.get("args")
    assert args is not None, "the picture loss was never asked for"
    assert args[1].space == "lab" and args[3].space == "lab", (
        "two papers with no comparison were handed the drawn shapes")


def test_the_coverage_readout_hands_the_picture_loss_a_cielab_shape(app):
    """Driven through `_update_coverage`, which is where the pair is
    assembled and where the CIELAB twin has to come from."""
    import gamut_app
    from types import SimpleNamespace as NS
    from references import reference_gamut
    import pathlib
    lab = reference_gamut("sRGB", white_point="D50", steps=9, space="lab")
    luv = reference_gamut("sRGB", white_point="D50", steps=9, space="luv")
    got = {}
    stub = NS(
        _reference=("a-profile", luv), _reference_path=pathlib.Path("p.icc"),
        _slots=[(pathlib.Path("holiday.png"), luv, None)],
        _how_much_fits=lambda a, b: (0.9, 0.4),
        _coverage=NS(setText=lambda t: None),
        _picture_loss=NS(setText=lambda t: None),
        _shared_lbl=NS(setText=lambda t: None),
        _reach=NS(setText=lambda t: None),
        _pair_box=NS(setVisible=lambda v: None),
        _compare=NS(currentData=lambda: ("icc", None)),
        _is_picture=lambda name: True,
        _in_lab=lambda g, p=None, m=None: lab,
        _reference_in_lab=lambda: lab,
        _update_pair=lambda *a: None,
        _update_picture_loss=lambda *a: got.setdefault("args", a))
    gamut_app.GamutApp._update_coverage(stub)
    args = got.get("args")
    assert args is not None, "the picture loss was never asked for"
    assert args[1].space == "lab" and args[3].space == "lab", (
        "it was handed the drawn shapes, so a change of Draw it in moves a "
        "number that has nothing to do with the drawing")


# --------------------------------------------------------------------------
# The fifth sibling, closed by construction rather than by luck
#
# Four members of this family were found one at a time, each in a branch
# nobody was looking at. A review then enumerated every place something
# CIELAB meets a gamut in this window and found two more without the
# refusal: the single-room picture and the exported table.
#
# ⚠ IT IS LATENT. Across 65 real files — ICC, .gam, photographs, a third
# party's whole profile set — built in CIELUV and then in CIELAB, with
# ArgyllCMS and again without it, there is NO input where the drawn build
# succeeds and the CIELAB one fails. The guard is here because the family
# has a habit, not because a reader can reach it today.
# --------------------------------------------------------------------------


def test_the_single_room_picture_marks_nothing_against_a_wrong_space_shape(app):
    import numpy as np
    import gamut_app
    from types import SimpleNamespace as NS
    from references import reference_gamut
    luv = reference_gamut("sRGB", white_point="D50", steps=9, space="luv")
    stub = NS(_chart=(__import__("pathlib").Path("c.ti1"), NS()),
              _chart_drawable=lambda: True,
              _drawing_in_ink=lambda: False,
              _chart_lab=lambda: np.array([[50.0, 0.0, 0.0]]),
              _judging_shapes=lambda: [("sRGB", luv, None, False)])
    got = gamut_app.GamutApp._chart_cloud(stub)
    assert got is not None and got[2] is None, (
        "it marked patches against a shape built in CIELUV")
    # ⚠ AND THE POSITIVE HALF: a refusal that fires always would pass the
    # line above and break the application.
    lab_shape = reference_gamut("sRGB", white_point="D50", steps=9,
                                space="lab")
    stub._judging_shapes = lambda: [("sRGB", lab_shape, None, False)]
    ok = gamut_app.GamutApp._chart_cloud(stub)
    assert ok is not None and ok[2] is not None, (
        "a CIELAB shape must still be marked against")


def test_the_exported_table_says_why_instead_of_dropping_the_row(app):
    """A table that quietly loses a line is worse than one that explains
    itself: whoever opens it later has no window to look at, and a column
    that vanished between two exports reads as a fault in the export."""
    import numpy as np
    import gamut_app
    from types import SimpleNamespace as NS
    from references import reference_gamut
    luv = reference_gamut("sRGB", white_point="D50", steps=9, space="luv")
    stub = NS(_chart_lab=lambda: np.array([[50.0, 0.0, 0.0]]),
              _chart=(__import__("pathlib").Path("c.ti1"),
                      NS(n_patches=1, kind="a .ti1", duplicates=0,
                         scale=100, scale_certain=True)),
              _chart_placed=NS(profile="a-profile", intent="relative",
                               tag="A2B1"),
              _judging_shapes=lambda: [("sRGB", luv, None, False)],
              _drawing_in_ink=lambda: False)
    rows = gamut_app.GamutApp._chart_rows_for_export(stub)
    text = " ".join(str(cell) for row in rows for cell in row)
    assert "not counted" in text, (
        f"the row was dropped instead of explaining itself: {rows!r}")
    assert "CIELAB" in text, "and it must carry its reason into the file"
    # ⚠ AND THE POSITIVE HALF.
    lab_shape = reference_gamut("sRGB", white_point="D50", steps=9,
                                space="lab")
    stub._judging_shapes = lambda: [("sRGB", lab_shape, None, False)]
    good = " ".join(str(cell) for row in
                    gamut_app.GamutApp._chart_rows_for_export(stub)
                    for cell in row)
    assert "not counted" not in good, (
        "a CIELAB shape must still be counted")
