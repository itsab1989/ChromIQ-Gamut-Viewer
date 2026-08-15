"""The page somebody else opens: its name, its controls, and its honesty.

Everything here was written after a defect got out, and each test says which
one. There were no tests over this file at all, which is exactly why four
things went wrong in it at once: the tab had no name, the control strip was
invisible on a dark page, the strip changed the movement the page was saved
with, and the figures written under the picture could not be scrolled to.
"""
from __future__ import annotations

import re

import pytest

import ti3gamut


# --------------------------------------------------------------------------
# What the tab says
# --------------------------------------------------------------------------

class _Trace:
    def __init__(self, name):
        self.name = name


class _Fig:
    """Only what _page_title reads: some named traces and a caption."""

    def __init__(self, names, caption=""):
        self.data = [_Trace(n) for n in names]
        self.layout = type("L", (), {"title": type("T", (), {"text": caption})})


def title(names, caption=""):
    return ti3gamut._page_title(_Fig(names, caption))


def test_the_tab_is_named_after_what_is_in_the_picture():
    assert title(["Glossy-paper — patches"]) == "Glossy-paper"


def test_two_shapes_are_both_named():
    assert title(["Glossy-paper", "Matte-paper"]) == "Glossy-paper and Matte-paper"


def test_the_same_shape_drawn_twice_is_named_once():
    assert title(["Glossy — patches", "Glossy — outside"]) == "Glossy"


def test_how_a_shape_is_drawn_stays_out_of_the_tab():
    """The defect: a published page was called "Glossy-paper and Matte-paper
    (outline)". Which of the two is an outline belongs in the key beside the
    picture; in a row of browser tabs it is noise."""
    assert title(["Glossy-paper", "Matte-paper (outline)"]) == \
        "Glossy-paper and Matte-paper"


def test_brackets_the_user_typed_themselves_are_kept():
    """The other half of the same decision, and the reason this is a list of
    known endings and not a pattern. Somebody who names a measurement
    "Canon (matte)" gets that name back."""
    assert title(["Canon (matte)"]) == "Canon (matte)"


@pytest.mark.parametrize("suffix", ti3gamut._OWN_SUFFIXES)
def test_every_ending_this_file_adds_is_stripped(suffix):
    assert title([f"A paper{suffix}"]) == "A paper"


def test_title_knows_every_suffix_the_drawing_code_adds():
    """A NEW WAY OF DRAWING MUST NOT QUIETLY REACH THE TAB. Anything named
    "<the shape> (something)" in this module is an ending this module invents,
    so it has to be declared -- otherwise it leaks into the title the way
    "(outline)" did, and nobody notices until a page is already published."""
    import inspect

    found = set(re.findall(r'name=f"\{name\}( \([^"]+\))"',
                           inspect.getsource(ti3gamut)))
    undeclared = found - set(ti3gamut._OWN_SUFFIXES)
    assert not undeclared, (
        f"{sorted(undeclared)} is added to a trace name but not listed in "
        "_OWN_SUFFIXES, so it will show up in the browser tab")


def test_a_hostile_name_cannot_end_the_title_early():
    assert "<" not in title(['<script>x</script> & "p"'])
    assert "&amp;" in title(['a & b'])


def test_a_scene_with_no_named_shape_falls_back_to_the_caption():
    assert title([], "Measured gamut — from a D50 white") == \
        "Measured gamut — from a D50 white"


def test_a_page_always_gets_some_name():
    assert title([], "") == "Measured gamut"


def test_the_title_is_put_in_the_document_once():
    page = ti3gamut._titled("<html><head></head><body></body></html>", "A")
    assert page.count("<title>") == 1
    assert ti3gamut._titled(page, "B").count("<title>") == 1


# --------------------------------------------------------------------------
# The control strip
# --------------------------------------------------------------------------

SPIN = {"on": True,
        "turn": {"mode": "round", "speed": 7.0, "range": 60.0},
        "tilt": {"mode": "swing", "speed": 5.0, "range": 20.0}}


def test_the_strip_is_painted_from_the_page_palette():
    """The defect: the document sets a background and no text colour, so
    `color: inherit` came out browser-default black -- 1.04:1 against the dark
    page. The strip was invisible on seven of the eight published samples."""
    for mode in ("dark", "light"):
        script = ti3gamut._spin_script(["scene0"], SPIN, mode)
        wanted = ti3gamut.SCENE_COLOURS[mode]
        assert f'"ink": "{wanted["text"]}"' in script
        assert f'"paper": "{wanted["page"]}"' in script


def test_the_strip_never_inherits_its_colour():
    assert "color:inherit;background:transparent" not in ti3gamut._SPIN_CONTROLS_JS
    assert "var ink = settings.ink" in ti3gamut._SPIN_CONTROLS_JS


def test_the_strip_is_not_revealed_by_hovering():
    """There is no hover on a phone. The strip is simply there, at full
    strength, on its own background -- so there is no resting state for a
    touch device to be stuck in."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert ".cq-spin-bar:hover" not in js
    assert "opacity:.35" not in js


def test_the_strip_cannot_cover_the_key():
    """THE DEFECT, REPORTED FROM A PHONE: the strip was fixed to the bottom of
    the window, which is the band the drawing library puts the key in -- so it
    sat on top of names that a reader is told to click. Measured at five
    viewports it covered two rows on a desktop and all four on a phone, where
    it was also wider than the screen and wrapped onto two lines.

    In the flow it cannot overlap anything at any width, which is why this
    checks for the absence of the positioning rather than for a clearance."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "position:fixed" not in js
    assert "flex-wrap:wrap" in js     # two lines when it must, and room for it


def test_the_page_is_laid_out_as_a_column(tmp_path):
    page = _page(tmp_path)
    assert "display:flex;flex-direction:column;" in page
    assert "body > div:first-of-type{flex:1 1 auto;min-height:0;}" in page


def test_the_toolbar_is_moved_off_the_caption_on_a_narrow_screen(tmp_path):
    """Plotly's own toolbar sits top-right and the caption runs under it: on a
    phone that was 2,464 square pixels of buttons over the words. The toolbar
    has somewhere else to go; one line of SVG text that cannot wrap does not."""
    assert "@media (max-width:820px)" in _page(tmp_path)


def test_a_keyboard_can_see_where_it_is():
    assert ":focus-visible" in ti3gamut._SPIN_CONTROLS_JS


def test_the_two_directions_keep_their_own_speeds():
    """THE DEFECT WORTH THE MOST: the strip pushed one speed to both axes as
    soon as the page opened, so a page saved turning at 7 while tipping at 5
    arrived tipping at 7 -- forty per cent fast, on four of eight published
    pages. The whole promise of a saved page is that it shows what was saved."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert 'speed: speedFor("turn")' in js
    assert 'speed: speedFor("tilt")' in js
    assert "saved[which].speed * both / start" in js


def test_a_reader_can_get_the_view_back():
    assert 'button("home", "reset view"' in ti3gamut._SPIN_CONTROLS_JS
    assert "reset: reset" in ti3gamut._SPIN_JS
    # Captured before the first movement is applied, or "back" is wherever it
    # had already turned to.
    assert "keep(id, cam);" in ti3gamut._SPIN_JS


def test_a_still_page_still_offers_the_controls():
    """A scene saved standing still is the one a reader most wants to set
    going; a strip that only appeared on moving pages made that impossible."""
    script = ti3gamut._spin_script(["scene0"], dict(SPIN, on=False))
    assert "cqSpinControls" in script


def test_no_movement_settings_means_no_strip():
    assert ti3gamut._spin_script(["scene0"], None) == ""


# --------------------------------------------------------------------------
# The figures written under the picture
# --------------------------------------------------------------------------

def _page(tmp_path, notes=""):
    import plotly.graph_objects as go

    fig = go.Figure(go.Scatter3d(x=[0, 1], y=[0, 1], z=[0, 1], name="A paper"))
    out = tmp_path / "p.html"
    ti3gamut._write_dark_html(fig, out, mode="dark", spin=SPIN,
                              carry_viewer=False, notes=notes)
    # ENCODING NAMED, ALWAYS. Path.read_text() uses the platform default,
    # which on Windows is cp1252 -- and this page is full of em dashes and
    # ellipses, so every test that read one back died there while passing on
    # macOS. The page is written as UTF-8; it has to be read as UTF-8.
    return out.read_text(encoding="utf-8")


def test_a_picture_on_its_own_does_not_scroll(tmp_path):
    assert "overflow:hidden" in _page(tmp_path)


def test_the_page_scrolls_when_the_numbers_are_under_it(tmp_path):
    """The defect: the figures are appended after a scene that is already the
    full height of the window, so they sit entirely below the fold -- and with
    the overflow hidden, fifteen real wheel notches moved the published page
    not one pixel. They are the reason that page exists."""
    page = _page(tmp_path, notes="Colour held: 702,327 cubic Lab units")
    assert "overflow:auto" in page
    assert "702,327" in page
    # AND THE PICTURE MAKES ROOM. Letting it scroll is not enough on its own:
    # a 3D scene the full height of the window takes the wheel for zooming, so
    # there is nowhere left to scroll from and the figures stay out of reach.
    assert "body > div:first-of-type{height:auto !important;}" in page


def test_the_strip_does_not_sit_on_top_of_the_numbers(tmp_path):
    """It is fixed to the bottom of the window, so the last line of the
    figures needs room to clear it."""
    page = _page(tmp_path, notes="Colour held: 702,327")
    pad = re.search(r"padding:14px 22px (\d+)px", page)
    assert pad and int(pad.group(1)) >= 60


# --------------------------------------------------------------------------
# Where the strip belongs, and where it does not
# --------------------------------------------------------------------------

def test_the_application_view_gets_the_engine_but_not_the_strip():
    """The defect: the strip was going into the window's own view as well, so
    the application had two sets of movement controls -- and they could
    disagree, because a nudge of a panel slider goes straight to the engine
    and leaves the strip showing a number that is no longer true."""
    script = ti3gamut._spin_script(["scene0"], SPIN, "dark", False)
    assert "window.cqSpin" in script          # it still moves
    assert "cqSpinControls" not in script     # without a second set of controls


def test_a_saved_page_gets_both():
    script = ti3gamut._spin_script(["scene0"], SPIN, "dark", True)
    assert "window.cqSpin" in script
    assert "cqSpinControls" in script


# --------------------------------------------------------------------------
# The key beside the picture
# --------------------------------------------------------------------------

def _cage(paint="plain", key="#9aa3b2"):
    """A tiny gamut's outline traces, as build_figure would ask for them."""
    import numpy as np
    import gamutview

    pts = np.array([[50.0, 0, 0], [60, 20, 0], [40, 0, 20], [50, 10, 30],
                    [45, -20, 5], [55, 5, -20]])
    g = gamutview.build_gamut(pts, space="lab", input_space="lab")
    return ti3gamut._edges(g, "A paper", paint=paint, key=key,
                           page="#111111")


def test_the_outline_key_is_drawn_in_the_colour_it_was_given():
    """THE DEFECT, REPORTED FROM A PHONE AND THEN FROM THE APP: the loop that
    walks the triangle edges called its edge `key` -- the same name as this
    function's own argument, which is the colour the key is to be drawn in. So
    the colour was overwritten with the last edge visited, a pair of vertex
    numbers like (600, 610). Handed numbers instead of a colour, the drawing
    library falls back to black, and the little line beside "(outline)" was
    invisible on every dark page and in the window itself."""
    for trace in _cage(paint="plain", key="#9aa3b2"):
        if trace.showlegend:
            assert trace.line.color == "#9aa3b2", (
                f"the outline key is drawn in {trace.line.color!r}, which is "
                "not the colour it was given")


def test_a_coloured_outline_gets_a_key_that_can_be_seen():
    """Its key used to be the first colour BAND, and the bands are sorted by
    colour -- so "rgb(0,0,0)" sorted first and a coloured cage keyed on black
    every time. Measured at 1.11:1 against the dark page."""
    keys = [t for t in _cage(paint="true", key="#9aa3b2") if t.showlegend]
    assert len(keys) == 1, "a cage should put exactly one row in the key"
    assert str(keys[0].line.color).lower() not in ("#000000", "rgb(0,0,0)",
                                                   "black")


def test_every_key_is_tied_to_the_thing_it_names():
    """A key is a switch -- the README tells the reader to click it. The keys
    here are separate zero-point traces, so without a legendgroup joining them
    to the shape, clicking one hid the invisible proxy and left the shape on
    screen. Measured: clicking "Glossy-paper" set the 1-point proxy to
    legendonly and left the 914-vertex mesh fully visible."""
    for paint in ("plain", "true"):
        traces = _cage(paint=paint)
        groups = {t.legendgroup for t in traces}
        assert len(groups) == 1 and None not in groups, (
            f"{paint}: the cage and its key are in groups {groups}, so "
            "clicking the key cannot switch the cage")


def test_the_proxy_makers_take_a_group():
    import inspect

    for fn in (ti3gamut._legend_line, ti3gamut._legend_proxy):
        assert "group" in inspect.signature(fn).parameters
        assert fn("a", "#fff", "g").legendgroup == "g"
        # Falling back to the name keeps a lone key working on its own.
        assert fn("a", "#fff").legendgroup == "a"


def test_the_toolbar_gets_out_of_the_way_of_a_long_caption(tmp_path):
    """Plotly's toolbar sits top-right; the caption is one line of SVG text
    that cannot wrap and runs to 821px on the ink-amount page. On a tablet the
    two met. Above 1024px they never have."""
    assert "@media (max-width:1024px)" in _page(tmp_path)
