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
    marked = [t for t in figure.data if "outside" in (t.name or "")]
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
