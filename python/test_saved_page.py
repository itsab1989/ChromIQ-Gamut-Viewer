"""The page somebody else opens: its name, its controls, and its honesty.

Everything here was written after a defect got out, and each test says which
one. There were no tests over this file at all, which is exactly why four
things went wrong in it at once: the tab had no name, the control strip was
invisible on a dark page, the strip changed the movement the page was saved
with, and the figures written under the picture could not be scrolled to.
"""
from __future__ import annotations

import inspect
import math
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

def _page(tmp_path, notes="", controls=True):
    import plotly.graph_objects as go

    fig = go.Figure(go.Scatter3d(x=[0, 1], y=[0, 1], z=[0, 1], name="A paper"))
    out = tmp_path / "p.html"
    ti3gamut._write_dark_html(fig, out, mode="dark", spin=SPIN,
                              carry_viewer=False, notes=notes,
                              controls=controls)
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
    assert "height:auto !important" in page


def test_the_numbers_cannot_squeeze_the_picture_away(tmp_path):
    """The defect, measured on a phone-sized window: the picture came out
    78px tall on an 844px screen because 466px of figures and 259px of
    controls were all being packed into a body fixed at exactly the height of
    the window. A column of flexible children in a box that cannot grow does
    not scroll, it squeezes -- and the picture was the smallest thing on a
    page that exists to show a picture.

    Three parts to the answer, and all three are needed: the body may grow
    past the window, the figures keep the height they ask for, and the picture
    is promised a share of the first screen it can never fall below."""
    page = _page(tmp_path, notes="Colour held: 702,327 cubic Lab units")
    assert "min-height:100%" in page, "the page must be allowed to grow"
    assert ".cq-notes{flex:0 0 auto;}" in page, "the figures must not shrink"
    floor = re.search(r"min-height:(\d+)vh", page)
    assert floor and 50 <= int(floor.group(1)) <= 75, (
        "the picture needs a guaranteed share of the first screen -- big "
        "enough to be the picture, small enough to leave the controls and "
        "the first lines of the figures visible under it")


def test_a_page_that_fills_the_screen_has_nothing_to_scroll_to(tmp_path):
    """THE TRAP THIS AVOIDS. The picture takes touches over completely now --
    one finger turns it, two zoom and move it, and it tells the browser in so
    many words not to treat any of that as scrolling. If such a picture filled
    the whole screen on a page that HAD something below it, every place a
    thumb could land would turn the shape instead of scrolling, and the rest
    of the page would be unreachable.

    The invariant that makes that impossible: a page only fills the screen
    exactly when there is nothing under it to reach.

    WHAT COUNTS AS "UNDER IT" CHANGED, and this test was written before it
    did. It used to be the written-out figures and nothing else, so the cap
    was applied only when there were figures. Then the strip of controls grew
    from four switches to twenty-one -- and a page with no figures, whose
    picture was still a rigid item in a body fixed to the height of the
    window, had nothing to give that panel but the picture. Measured with the
    panel open: **0 pixels of picture at 320x568.** The cap now applies
    whenever anything at all sits below, which is figures OR controls.
    """
    alone = _page(tmp_path, controls=False)
    assert "overflow:hidden" in alone, "nothing below it, so nothing scrolls"
    assert "min-height:62vh" not in alone, (
        "with nothing under it at all the picture may have the whole window")
    with_notes = _page(tmp_path, notes="Colour held: 702,327")
    assert "overflow:auto" in with_notes
    assert "min-height:62vh" in with_notes
    # AND THE CASE THAT WAS MISSED: controls, no figures.
    with_strip = _page(tmp_path)
    assert "min-height:62vh" in with_strip, (
        "a panel of twenty-one controls will squeeze an uncapped picture to "
        "nothing on a phone")
    # THE SAME CASE, THE OTHER HALF OF IT, AND IT SHIPPED. The cap above was
    # applied for controls-without-figures; the SCROLLING was not, so such a
    # page said `overflow:hidden` and the document could not move at all. The
    # panel sat below the fold with no way to reach it -- not by dragging,
    # because the picture refuses to start a scroll, and not by pressing
    # "more…" either, because scrollIntoView cannot scroll a page that has
    # been told it does not scroll.
    #
    # Basti met it on the published page 18, which is saved without the
    # figures: "even after pressing more i can't scroll". Page 14 carries the
    # figures and scrolled, which is why it "used to work" on the examples he
    # had tried before.
    assert "overflow:auto" in with_strip, (
        "a page with controls under the picture must be able to scroll to "
        "them; with overflow hidden they cannot be reached at all")


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
    """A tiny gamut's outline traces, as the FIGURE ends up holding them.

    PUT THROUGH A FIGURE FIRST, rather than read straight off the list
    `_edges` returns. The cage itself is now handed over as a plain dict --
    building it as a go.Scatter3d ran plotly's validator over every one of
    twenty thousand colour entries, and a redraw of the Adobe RGB comparison
    went from 453 ms to 246 ms by skipping that. The figure converts it, so
    everything downstream still sees a real trace with real attributes; only
    a check reading the intermediate list saw the difference, which is a
    check looking at the plumbing rather than at the picture.
    """
    import numpy as np
    import gamutview
    import plotly.graph_objects as go

    pts = np.array([[50.0, 0, 0], [60, 20, 0], [40, 0, 20], [50, 10, 30],
                    [45, -20, 5], [55, 5, -20]])
    g = gamutview.build_gamut(pts, space="lab", input_space="lab")
    figure = go.Figure()
    for trace in ti3gamut._edges(g, "A paper", paint=paint, key=key,
                                 page="#111111"):
        figure.add_trace(trace)
    return list(figure.data)


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


# --------------------------------------------------------------------------
# The control strip, and two bugs that stayed invisible because the tests
# guarding them asked the wrong question.
# --------------------------------------------------------------------------

def test_the_more_panel_is_actually_hidden_when_it_is_closed():
    """The bug: the panel was marked hidden the moment it was built, the
    button read "more…", and it was on screen the entire time -- because a
    rule the page writes always beats the browser's own
    ``[hidden]{display:none}``, whatever the specificity, and the panel's own
    ``display:grid`` therefore cancelled being hidden.

    Measured on a phone-sized window before the fix: the panel was 259px of
    an 844px screen, the picture was 78px, and 91 per cent of what the reader
    could see was controls. On every page since the panel was introduced.

    The test that guarded it asked the element whether it was hidden. It
    truthfully answered yes. So the rule has to be checked instead: setting
    ``display`` on a class is only safe next to a rule that puts it back."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert ".cq-spin-panel[hidden]{display:none}" in js, (
        "the panel sets its own display, so it must also say what hidden "
        "means -- or being hidden does nothing at all"
    )
    # And it has to beat every OTHER rule that sets the panel's display.
    # Written as "comes after display:grid" this test went on passing when
    # the panel became display:block and grew media queries after it -- it
    # was finding "display:grid" on the row grids inside, which is a
    # different element entirely and settles nothing.
    hidden = js.index(".cq-spin-panel[hidden]{display:none}")
    assert hidden > js.index(".cq-spin-panel{"), (
        "two rules of the same weight are settled by which is written last")
    assert ".cq-spin-panel{display" not in js[hidden:], (
        "a later rule setting the panel's own display would put it back on "
        "screen while it still called itself hidden")


def test_the_strip_sits_with_the_picture_not_after_the_numbers():
    """Appended to the body it landed after the written-out figures, which on
    a phone is several screens of text -- so the controls for the picture were
    below everything, and pausing the movement meant scrolling away from the
    thing being paused."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "insertBefore(bar, anchor.nextSibling)" in js
    assert js.index("insertBefore(bar") < js.index("appendChild(bar)"), (
        "appending to the body is the fallback, not the normal route")


def test_the_reader_can_put_the_numbers_away():
    """They can be taller than a phone screen, and somebody who has read them
    once wants the window back for the picture."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert 'row("notes", "the numbers"' in js
    assert 'querySelector(".cq-notes")' in js, (
        "offering to hide something that is not on the page is the clearest "
        "way there is to make a reader think the page is broken")


def _js_strings_are_closed(js: str):
    """Every quoted string in *js* ends on the line it starts on.

    Returns the offending line numbers. This exists because the script is
    written inside a PLAIN triple-quoted Python string, where a ``\\n`` typed
    into a tooltip is not two characters -- Python turns it into a real
    newline, which lands in the middle of a JavaScript string literal and
    stops the whole page working. Costing one round to find, twice.
    """
    bad, quote, comment = [], None, False
    for n, line in enumerate(js.splitlines(), 1):
        i = 0
        while i < len(line):
            c = line[i]
            if comment:
                if line[i:i + 2] == "*/":
                    comment = False
                    i += 1
            elif quote:
                if c == "\\":
                    i += 1
                elif c == quote:
                    quote = None
            elif line[i:i + 2] == "//":
                break
            elif line[i:i + 2] == "/*":
                comment = True
                i += 1
            elif c in "\"'":
                quote = c
            i += 1
        if quote:
            bad.append(n)
            quote = None
        if comment:
            comment = False
    return bad


def test_no_stray_escape_breaks_the_script():
    for name in ("_SPIN_JS", "_SPIN_CONTROLS_JS", "_LINK_AXES_JS"):
        js = getattr(ti3gamut, name)
        assert not _js_strings_are_closed(js), (
            f"{name}: a string is left open at line(s) "
            f"{_js_strings_are_closed(js)} -- most likely a backslash-n typed "
            f"into a tooltip, which Python turned into a real newline")


def test_the_scanner_would_have_caught_it():
    """The guard above is worth only as much as its ability to fail."""
    # Both lines are flagged -- the first opens a string it never closes, and
    # the second is left holding the other half of it. The first is the one
    # that names the mistake.
    assert _js_strings_are_closed('var a = "one\ntwo";')[0] == 1
    assert _js_strings_are_closed('var a = "fine"; // a library\'s comment') == []
    assert _js_strings_are_closed("var a = 'it\\'s fine';") == []


# --------------------------------------------------------------------------
# The controls for each shape, and the honesty of them
#
# Added with the controls themselves. Two of these guard faults that were
# already in the shipped code and that a full green suite had no opinion on.
# --------------------------------------------------------------------------

def _luminance(colour: str) -> float:
    """Relative luminance of an sRGB colour, per IEC 61966-2-1 / Rec. 709.

    The same definition WCAG uses for contrast, so the ratios below mean what
    they mean everywhere else.
    """
    text = colour.strip()
    if text.startswith("rgb"):
        bits = [float(v) for v in text[text.index("(") + 1:text.index(")")]
                .split(",")[:3]]
    else:
        h = text.lstrip("#")
        bits = [int(h[i:i + 2], 16) for i in (0, 2, 4)]

    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in bits)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def test_the_scanner_of_brightness_agrees_with_the_two_ends():
    """A measure that cannot fail is not a measure."""
    assert _contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert _contrast("#777777", "#777777") == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_the_red_and_the_grey_differ_in_brightness_not_only_in_hue(mode):
    """The comparison mesh paints out-of-reach red and within-reach grey, and
    those two have to be told apart by somebody looking at a shaded surface.

    IT SHIPPED AT 1.12:1 ON THE DARK PAGE -- the same brightness, so hue was
    the only thing separating them. Hue is the weakest cue on a surface whose
    shading already varies its brightness everywhere, and for a reader who
    cannot separate red from grey-blue it is not a cue at all. Reported as
    "red and grey with no clear distinction", and it was exactly that.

    The whole suite was green while that was true, which is the reason this
    test exists rather than a comment.
    """
    kept = ti3gamut.SCENE_COLOURS[mode]["kept"]
    got = _contrast(ti3gamut._LOST, kept)
    assert got >= 1.9, (
        f"{mode}: the red {ti3gamut._LOST} and the grey {kept} are only "
        f"{got:.2f}:1 apart in brightness -- at that distance the picture is "
        f"readable by hue alone")


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_and_the_grey_can_still_be_seen_against_the_page(mode):
    """Pushing the grey away from the red must not push it into the paper.

    The two pull in opposite directions on a near-black page and this is the
    other end of that trade -- without it, "make them differ" is satisfied
    perfectly by a shape nobody can see.
    """
    scene = ti3gamut.SCENE_COLOURS[mode]
    got = _contrast(scene["kept"], scene["page"])
    assert got >= 1.7, (
        f"{mode}: the within-reach grey is only {got:.2f}:1 against the page")


def test_the_key_says_what_both_of_those_colours_mean():
    """"red is out of reach" names one colour of a two-coloured shape and
    invites the reader to take the other for background."""
    import numpy as np

    class _G:
        # "xyz" rather than "lab" only because Lab is drawn as a hue circle
        # and that needs a real Gamut. Nothing here depends on the space.
        vertices = np.array([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0]])
        faces = np.array([[0, 1, 2]])
        space = "xyz"

    trace = ti3gamut._mesh_lost(_G(), "Paper", 1.0, [True, False, False])
    assert "red is out of reach" in trace.name
    assert "grey" in trace.name


def test_colour_that_is_the_answer_is_never_offered_in_grey():
    """A saved page lets the reader drop the colour out of a shape. On two of
    them the colour IS the measurement -- red for what cannot be reached --
    and a greyed one still carries a name promising two states while showing
    one. Marked in the Python, refused in the page."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert 'meta.cq === "colour"' in js
    assert "g.plain" in js, "the mark has to reach the decision"
    assert ti3gamut._COLOUR_IS_THE_ANSWER == {"cq": "colour"}


def test_grey_is_the_true_brightness_and_not_an_average():
    """Averaging the three numbers makes pure blue and pure yellow the same
    grey, when one is nearly black to look at and the other nearly white."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "0.2126" in js and "0.7152" in js and "0.0722" in js, (
        "the Rec. 709 luminance weights sRGB is built on")
    assert "0.04045" in js and "1.055" in js, (
        "and the transfer curve, undone before weighting and put back after")
    assert "/ 3" not in js.split("function toGrey")[1].split("function")[0]


def test_an_array_of_colours_is_wrapped_before_it_is_handed_over():
    """Handed a bare array, restyle reads it as one value per trace and gives
    the FIRST element to this trace -- so 491 vertex colours quietly become
    one string and the whole surface turns that colour. Measured in a real
    browser: it fails silently and looks like a rendering fault.

    The wrapping now happens where the traces are handed over rather than
    where the colours are worked out, because they are handed over in groups:
    each part contributes ONE entry to a list, and the list is what restyle
    is given. One trace still produces a one-entry list, which is the same
    thing it always was.
    """
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "slot.values[k].push(patch[k])" in js, (
        "each part must contribute one entry per field, so an array of "
        "vertex colours arrives as one trace's worth")
    assert "window.Plotly.restyle(slot.gd, slot.values, slot.at)" in js


def test_a_shape_is_restyled_in_one_go_however_many_traces_it_has():
    """One press asked for 349 rebuilds of the scene, and a phone hung.

    A cage drawn in true colours is a few hundred traces, because a line
    takes one colour for the whole trace. With restyle called inside the
    per-part loop, one press of "where they agree" on the Adobe RGB showcase
    page asked the drawing library to rebuild the scene once per trace:

        page 11, 4 traces        5 calls      0.3 s
        page 14, 348 traces    349 calls     36.4 s

    measured on a desktop with a real graphics card. It was reported from a
    phone as the page hanging on the press -- and staying hung through a
    reload, because the reading is remembered and replayed while the page is
    opening.
    """
    js = ti3gamut._SPIN_CONTROLS_JS
    body = js[js.index("function dressOne"):]
    body = body[:body.index("\n  function moved(")]
    # The only restyle in dressOne is the one that hands over a whole group.
    assert body.count("restyle(") == 1, (
        "dressOne must hand its traces over in groups, not one at a time — "
        f"found {body.count('restyle(')} restyle calls in it")
    assert "groups[id]" in body and "divs.indexOf(part.gd)" in body, (
        "traces are grouped by which fields they need AND by which graph "
        "they belong to — a trace index means nothing to the wrong graph")


def test_the_key_beside_a_name_keeps_its_strength_when_the_shape_fades():
    """Every mesh here travels with a scatter of one empty point whose only
    job is a readable marker in the legend. Fading that with the surface
    fades the key, and a key nobody can see is a fault this page has had
    twice already."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "if (!part.proxy) {" in js
    assert "patch.opacity = want_op" in js


def test_a_shape_drawn_at_two_strengths_comes_back_to_both():
    """A shape is not always one trace at one strength.

    A chart's skin is a surface at 0.3 with a cage over it at full strength.
    The shape's strength is read off its FIRST trace and used to be written
    to every one of them, so the first press flattened them onto one number
    and the cage could never come back: measured on the ink-amounts page,
    fainter then stronger left the cage at 0.3 where it opened at 1, and
    11,537 pixels different on a page whose noise floor is 0.

    Each part now keeps what it opened at, and the slider is applied as a
    ratio — so at the strength the page was saved with, every part is handed
    exactly its own value back and "as saved" is exact.
    """
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "opened: (typeof t.opacity" in js, (
        "each part must record the strength it opened at")
    assert "st.opacity / g.opened.opacity" in js, (
        "the shape's strength applies as a ratio of what it opened at")
    assert "(st.opacity === g.opened.opacity)" in js, (
        "back at the saved strength every part takes its own value exactly, "
        "rather than something a rounding away from it")


def test_the_panel_is_grouped_under_headings():
    """Twenty unrelated controls in one flat list is not a panel, it is an
    inventory: somebody looking for one of them reads every line."""
    js = ti3gamut._SPIN_CONTROLS_JS
    for heading in ("how it moves", "where you look from", "each shape",
                    "what is drawn", "the page itself"):
        assert f'section("{heading}"' in js
    assert "if (!rows) return;" in js, (
        "a heading over nothing is scaffolding the reader has to read past")


def test_a_control_is_never_built_where_it_could_do_nothing():
    """The rule this page already lived by, extended to the new ones: full
    screen does not exist for an ordinary element on an iPhone, and a cage
    has no surface to draw wires over."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "document.fullscreenEnabled" in js
    assert "window.Plotly && window.Plotly.downloadImage" in js
    assert "return on(\"wires\", true) && (g.mesh || g.fill);" in js
    assert "!flat" in js.split("function canStand")[1][:120], (
        "a cross-section is already looked straight at")


def test_the_number_between_two_buttons_cannot_move_them():
    """"100%" is wider than "50%", so every press that crossed a digit shoved
    the plus out from under the finger pressing it. Reported from the real
    page. Both halves are needed -- a floor on the width, and figures that
    are all the same width as each other."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert ".cq-num{display:inline-block;min-width:40px;" in js
    assert "font-variant-numeric:tabular-nums" in js
    assert 'class="cq-num" data-cq="shape-lit-' in js


def test_the_panel_gives_way_on_a_short_screen_and_not_otherwise():
    """A sideways phone has 390px of height and an open panel is taller than
    that, so it would push the picture off the screen. A tall phone has room
    and can simply be longer -- a panel with its own scrollbar inside a page
    that also scrolls is a trap for anybody whose thumb lands on it."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "@media (max-height:560px){" in js
    assert ".cq-spin-panel{max-height:46vh;overflow-y:auto}" in js
    assert "overscroll-behavior" not in js, (
        "chaining is what lets a thumb reaching the end of the panel carry "
        "on to the page")


def test_a_phone_gets_one_column_and_a_bigger_thing_to_press():
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "@media (max-width:520px){" in js
    assert "min-height:34px" in js


def test_the_selectors_are_quoted_because_the_names_carry_numbers():
    """An unquoted attribute selector is a CSS identifier, and querySelector
    THROWS on one it cannot parse rather than returning nothing -- which
    would take the whole strip down with it."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "'[data-cq=\"' + what + '\"]'" in js


# --------------------------------------------------------------------------
# Fading away where the shapes agree — and where they differ
#
# The first of these guards a fault that was BUILT, measured and thrown away:
# the fade was done by cutting each surface into two meshes, and at full
# strength — where nothing should have changed — 120,481 pixels differed by
# more than eight levels because a browser blends transparent surfaces in the
# order it draws them.
# --------------------------------------------------------------------------

def _gamuts():
    import numpy as np

    from gamutview import build_gamut
    rng = np.random.default_rng(20260815)

    def blob(scale):
        pts = rng.normal(size=(60, 3)) * np.array([12.0, 20.0, 20.0]) * scale
        pts[:, 0] += 50.0
        return build_gamut(pts, input_space="lab", space="lab")

    return [("big", blob(1.0)), ("small", blob(0.55))]


def test_where_they_agree_is_worked_out_from_containment_not_guessed():
    """The same test the red-and-grey comparison already uses, so the two
    features cannot disagree about what "inside" means."""
    import inspect

    source = inspect.getsource(ti3gamut.agreement_masks)
    assert "outside_of" in source
    assert "AND, NOT OR" in source, (
        "with three shapes, 'where they overlap' is the region every one of "
        "them holds -- a point inside one of two others still differs")


def test_a_shape_alone_agrees_with_nothing():
    """Closing the second measurement while the fade is turned down must not
    erase the one that is left."""
    import numpy as np

    only = [_gamuts()[0]]
    mask = ti3gamut.agreement_masks(only)[0]
    assert mask.all(), "all of it stands out when there is nothing to compare"


def test_a_shape_inside_another_agrees_everywhere():
    import numpy as np

    big, small = _gamuts()
    masks = ti3gamut.agreement_masks([big, small])
    assert masks[1].sum() < masks[0].sum(), (
        "the smaller shape is mostly inside the bigger one, so far less of "
        "it stands out")


def test_the_fade_is_done_to_the_colours_and_not_by_a_second_mesh():
    """MEASURED, and the reason the first implementation was thrown away.

    Cutting a closed surface into a faded half and a solid half changes how
    the browser composites it: 120,481 pixels differed by more than eight
    levels with the fade at FULL. One mesh carrying an alpha per point has no
    such seam -- and at full strength it hands back the very same colour
    strings, so the picture is identical by construction rather than by
    luck. Re-measured on the finished thing at 0 pixels different.
    """
    source = inspect.getsource(ti3gamut._with_alpha)
    assert "120,481" in source, "the measurement that forced this belongs here"
    assert 'out.append(colour)' in source, (
        "at full strength the very same string comes back, not a rebuilt one "
        "-- which is what makes the top of the range identical rather than "
        "merely close")


def test_full_strength_really_does_return_the_same_colours():
    got = ti3gamut._with_alpha(["rgb(1,2,3)", "rgb(4,5,6)"], [1.0, 1.0])
    assert got == ["rgb(1,2,3)", "rgb(4,5,6)"]


def test_and_a_lower_one_really_does_change_them():
    got = ti3gamut._with_alpha(["rgb(1,2,3)", "rgb(4,5,6)"], [0.25, 1.0])
    assert got == ["rgba(1,2,3,0.250)", "rgb(4,5,6)"]


def test_the_mask_follows_the_same_welding_as_the_colours_it_indexes():
    """A weld groups by the point AND its colour. A mask welded on its own,
    with its own values standing in for colours, can group differently and
    come back a different length -- lined up with nothing, so the fade lands
    on the wrong points and looks like a fault in the measurement."""
    import inspect
    import numpy as np
    from gamutview import build_gamut
    from references import reference_gamut

    assert "_weld_order" in inspect.getsource(ti3gamut._weld), (
        "one rule, used by both, rather than two implementations of it")

    # ASKED OF THE TRACE. The mask the page carries has one character per
    # DRAWN vertex, so if it were welded by a different rule it would come
    # back a different length and index nothing.
    rng = np.random.default_rng(3)
    lab = np.column_stack([rng.uniform(20, 90, 400),
                           rng.uniform(-70, 70, 400),
                           rng.uniform(-70, 70, 400)])
    pair = [("g", build_gamut(lab, input_space="lab")),
            ("s", reference_gamut("sRGB", steps=12))]
    fig = ti3gamut.build_figure(pair, "t", split=True)
    carried = [t for t in fig.data if (t.meta or {}).get("stand")]
    assert carried, "no shape carried the mask the reader's slider needs"
    for trace in carried:
        assert len(trace.meta["stand"]) == len(trace.vertexcolor), (
            "the mask and the colours came back different lengths — they were "
            "welded by different rules")


def test_the_saved_page_keeps_the_cut_sharp_at_full_strength():
    """THE WORST WAY FOR THIS TO BE WRONG: right on screen, wrong in the page
    somebody was sent.

    The shapes are re-cut so no triangle straddles the boundary, which needs
    two corners in the same place carrying different answers. On screen the
    fade is already applied when they are welded, so their colours differ and
    they survive. A saved page is written at FULL strength and hands the
    reader the slider -- and at full strength the two copies are the same
    colour, so they welded back into one and the reader's slider drew the very
    gradient the re-cut exists to remove. Measured on the demo page: 361 of
    1,324 triangles straddled again.
    """
    import numpy as np
    from gamutview import build_gamut
    from references import reference_gamut

    rng = np.random.default_rng(5)
    lab = np.column_stack([rng.uniform(20, 90, 400),
                           rng.uniform(-70, 70, 400),
                           rng.uniform(-70, 70, 400)])
    pair = [("g", build_gamut(lab, input_space="lab")),
            ("s", reference_gamut("sRGB", steps=12))]
    fig = ti3gamut.build_figure(pair, "t", split=True)
    for trace in fig.data:
        mark = (trace.meta or {}).get("stand")
        if not mark:
            continue
        side = np.array([ch == "1" for ch in mark])
        faces = np.column_stack([trace.i, trace.j, trace.k])
        n = side[faces].sum(axis=1)
        straddling = int(((n > 0) & (n < 3)).sum())
        assert straddling == 0, (
            f"{straddling} of {len(faces)} triangles straddle the boundary, so "
            "the reader's slider will paint a gradient across each of them")


def test_the_reader_gets_both_directions_and_they_are_not_the_same_control():
    js = ti3gamut._SPIN_CONTROLS_JS
    assert 'data-cq="agree-at"' in js and 'data-cq="differ-at"' in js
    assert "differAt" in js and "agreeAt" in js
    assert 'mark.charAt(at) === "1" ? differAt : agreeAt' in js, (
        "one asks where they differ, the other what they have in common")


def test_the_page_only_carries_the_mask_when_it_hands_over_the_control():
    """One character per measured point is small, and a page nobody can fade
    has no use for it at all."""
    src = inspect.getsource(ti3gamut.build_figure)
    assert "stand = (standing if (split and standing is not None) else None)" \
        in src, "the mask travels only when the reader gets the control"


def test_the_fade_asks_each_vertex_for_its_own_answer():
    """Not the triangles beside it.

    The alpha is per vertex, and it used to be worked out by taking the
    per-TRIANGLE agreement and marking every vertex those triangles touch.
    That dilates the disagreement by a whole ring: measured on the demo pair
    against Adobe RGB, 239 vertices are genuinely outside and 335 were
    painted as though they were — 96 of them, a seventh of the surface, drawn
    as disagreement where the two agree. Every error went the same way, and
    it was reported as "parts of where they agree do not become transparent".
    """
    src = inspect.getsource(ti3gamut.build_figure)
    assert "agreeing_edges(g, disagrees)" not in src, (
        "the surface's alpha must not come from a dilated per-triangle mask")

    # ASKED OF THE DRAWING, not of the source line that makes it. Pinning the
    # spelling of a statement makes the test fail when the line moves and pass
    # when the behaviour is lost some other way, which is backwards.
    import numpy as np
    from gamutview import build_gamut
    from references import reference_gamut

    rng = np.random.default_rng(11)
    lab = np.column_stack([rng.uniform(20, 90, 400),
                           rng.uniform(-70, 70, 400),
                           rng.uniform(-70, 70, 400)])
    pair = [("g", build_gamut(lab, input_space="lab")),
            ("s", reference_gamut("sRGB", steps=12))]
    fig = ti3gamut.build_figure(pair, "t", agree=0.2, differ=1.0)
    faded = [t for t in fig.data
             if getattr(t, "vertexcolor", None) is not None]
    assert faded, "no surface carried a colour per vertex"
    for trace in faded:
        strengths = {round(float(str(c).split(",")[3].rstrip(")")), 3)
                     for c in trace.vertexcolor if "rgba(" in str(c)}
        # Two strengths and no others: a vertex is either outside the other
        # shape or it is not, and a value between them is a vertex that was
        # given somebody else's answer.
        assert len(strengths) <= 1, (
            f"the surface carries {sorted(strengths)} — a fade with more than "
            "one faded value is a gradient, not a decision")


def test_a_dilated_mask_never_says_less_than_the_true_one():
    """The property that makes the old behaviour a one-way error.

    Built rather than measured, so it holds whatever demo files exist: a
    shape whose vertices are half in and half out of another.
    """
    import numpy as np
    from gamutview import build_gamut
    from references import reference_gamut

    rng = np.random.default_rng(4)
    lab = np.column_stack([rng.uniform(20, 90, 500),
                           rng.uniform(-70, 70, 500),
                           rng.uniform(-70, 70, 500)])
    g = build_gamut(lab, input_space="lab")
    ref = reference_gamut("sRGB", steps=20)
    per_vertex = ti3gamut.disagreeing_vertices([("g", g), ("s", ref)])[0]
    dilated = ti3gamut.agreeing_edges(
        g, ti3gamut.agreement_masks([("g", g), ("s", ref)])[0])
    assert (dilated | per_vertex == dilated).all(), (
        "the dilated mask must be a superset — if it ever says LESS, the two "
        "disagree about something other than the ring")
    assert dilated.sum() >= per_vertex.sum()


def test_a_strength_moves_in_steps_the_eye_can_see_evenly():
    """Ten equal steps of a tenth sound right and do not look it: full to
    nine-tenths is barely visible, while the last step removes almost all of
    what was left. Reported as a shape that "seemed fully there and then
    immediately completely gone"."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "var LADDER = [0, 0.05, 0.08, 0.11, 0.15, 0.2," in js
    assert "function stepped(value, by, start)" in js
    # AND IT KEEPS WHEREVER THE SHAPE STARTED as a rung of its own, or a
    # value the page was saved with -- 0.55 for two papers, 0.30 for a
    # chart's skin -- cannot be returned to by pressing plus as many times
    # as minus. Caught by pressing both and comparing the drawing.
    assert "function ladderFor(start)" in js
    # ONE LADDER FOR EVERY STRENGTH ON THE PAGE. Two similar controls moving
    # in different steps is the inconsistency this is meant to remove.
    assert js.count("stepped(") >= 4


def test_it_can_be_taken_all_the_way_to_nothing():
    """Asked for, and the right answer: hiding the shared part outright is a
    thing somebody wants. Refusing it because a vanished shape MIGHT be
    mistaken for a fault solves the wrong half of the problem."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "var LADDER = [0," in js


def test_the_button_does_not_say_only_that_something_changed():
    """A label reading "(changed)" was tried and taken out again.

    It says that SOMETHING is different without saying what, which is half an
    answer and leaves the reader hunting anyway — "not really helpful", as it
    was put. The note that names the thing they can see and what to press
    about it is the whole answer, so the vague one was only noise."""
    js = ti3gamut._SPIN_CONTROLS_JS
    # THE EMITTED STRING, not the word wherever it appears -- the comment
    # explaining why it was removed says it too, and a test that cannot tell
    # those apart forbids writing the reason down.
    assert '" (changed)"' not in js
    assert "changedFromSaved" not in js
    assert "function tellMore()" in js, (
        "it still has to exist, and be defined and not only called -- it was "
        "called from two places while defined in none, so the panel's own "
        "button stopped updating at all")
    # EVERY ROUTE THAT CHANGES THE PICTURE GOES THROUGH IT.
    assert js.count("tellMore()") >= 2


def test_a_saved_page_tells_a_phone_how_wide_it_is(tmp_path):
    """WITHOUT THIS EVERY RULE WRITTEN FOR A PHONE IS DEAD.

    A phone browser handed a page with no viewport tag assumes it was written
    for a desktop: it lays it out in a pretend window about 980 pixels wide
    and scales the result down to fit. On a 390-pixel phone that is a scale of
    roughly 0.40, so a 12-pixel label is drawn at five physical pixels — and
    every ``@media (max-width: …)`` rule in the strip is measured against 980
    and never fires.

    Reported as "on some occurrences the controls are tiny". It survived
    because the viewport measurements here resize the real window, and a
    desktop browser in a narrow window lays out at that width with or without
    the tag — so the probes were measuring the layout this tag produces while
    the pages shipped without it.
    """
    page = _page(tmp_path)
    assert 'name="viewport"' in page
    assert "width=device-width" in page
    assert "initial-scale=1" in page
    # AND IN THE HEAD, before the styles it governs.
    assert page.index('name="viewport"') < page.index("</head>")


@pytest.mark.parametrize("styles", [["solid", "solid"], ["solid", "mesh"],
                                    ["mesh", "mesh"], ["solid+mesh", "mesh"],
                                    ["mesh", "solid"]])
@pytest.mark.parametrize("agree,differ,split",
                         [(1.0, 1.0, False), (1.0, 1.0, True),
                          (0.3, 1.0, True), (1.0, 0.3, True),
                          (0.0, 0.0, True)])
def test_no_name_is_listed_twice(styles, agree, differ, split):
    """A cage is drawn in two halves when the fades are handed over, and the
    second half must not put its own entry in the list of names.

    IT DID. Passing ``key=None`` reads to `_edges` as "no separate marker, so
    the cage itself carries the name" — the opposite of silence — so a page
    with a cage on it listed that cage twice under one name, in every
    arrangement, whether or not anything was actually faded. Reported as "the
    outline was double in some", and reproduced here in 16 of 25
    combinations before the fix.
    """
    import collections

    fig = ti3gamut.build_figure(_gamuts(), "", styles=styles, agree=agree,
                                differ=differ, split=split)
    names = [t.name for t in fig.data if getattr(t, "showlegend", False)]
    twice = [n for n, count in collections.Counter(names).items() if count > 1]
    assert not twice, f"listed more than once: {twice}"


def test_the_page_says_why_a_see_through_shape_looks_sliced():
    """A see-through surface shows flat, hard-edged patches of its own
    triangles at some angles — the browser blends them in the order it draws
    them rather than by which is nearer. Nothing is missing and the outline is
    identical, but it reads as a slice taken out of the shape.

    Measured: 0.54% of the inside is hard-edged when solid against 0.87% from
    above and 3.47% at the three-quarter angle these pictures open at. Both
    routes to transparency draw it identically, so there is no cleaner one to
    switch to — the answer is to say so.

    Explaining it only in the tooltip of the button that causes it is no help
    to somebody looking at the picture wondering what they did: reported as
    "it looks sliced", then "I don't know which control does it".
    """
    js = ti3gamut._SPIN_CONTROLS_JS
    assert 'data-cq="facets"' in js
    assert "nothing is missing" in js
    assert "Press + to make it solid" in js, "name the cure, not only the cause"
    # SHOWN ONLY WHILE IT APPLIES. A standing note about something that is
    # not happening is just more to read.
    assert 'note.hidden = !thin' in js
    # AND UPDATED ON THE ONE PATH EVERY PRESS TAKES. Hung off the plural
    # tellShapes() it was missed by every per-shape press, which calls the
    # singular one -- the same trap as the "(changed)" label.
    # Checked by reading tellMore's own body rather than by comparing
    # positions in the file with some other function's -- which is a guess
    # about layout, and was wrong the first time it was written here.
    body = js[js.index("function tellMore()"):]
    body = body[:body.index("\n  }") + 4]
    assert "note.hidden" in body, (
        "the note has to be updated on the one path every press takes")


def test_the_picture_can_never_paint_over_the_controls():
    """Opening the panel takes about seventy pixels off the picture, and the
    drawing library only learns that when told to re-measure. For a frame or
    two the canvas is still its old height and spills over the strip, slicing
    the Play button in half. Reported as "here, and then a second later it is
    back to good".

    Telling it to re-measure sooner only shortens the flicker. Stacking the
    controls above the picture removes it whatever the timing, and clipping
    the picture to its own box stops the canvas escaping at all.
    """
    js = ti3gamut._SPIN_CONTROLS_JS
    assert ".cq-spin-bar,.cq-spin-panel{position:relative;z-index:2}" in js
    assert "body > div:first-of-type{overflow:hidden}" in js
    assert "requestAnimationFrame(function () { fit(); })" in js, (
        "and re-measured once the browser has actually laid out, which is "
        "the earliest the new height can be read")


def test_the_strip_grows_with_the_window_between_a_floor_and_a_ceiling():
    """Pinned at 12px it was right on a laptop and read as tiny on anything
    wider — reported from a desktop window. The floor keeps every measurement
    made for a narrow screen exactly where it was."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert js.count("clamp(12px,0.85vw,15px)") == 2, (
        "the strip and the panel, or the two disagree about their own size")
    assert "padding:0.45em 0.85em" in js and "padding:0.4em 0.8em" in js, (
        "buttons in em, so they grow with the text rather than staying the "
        "same size around it")


# ----------------------------------------------------------------- ordering
#
# A see-through surface never hides itself: the drawing library turns depth
# WRITING off for its transparent pass, so every triangle is blended in, near
# and far, in whatever order it sits in memory -- and the last one to land on a
# pixel is the one that mostly shows. Pieces of the far side punch through the
# near side in hard-edged triangles. Measured on one paper at seven angles, at
# a thousandth of see-through where nothing can possibly blend: up to 92.1% of
# the picture unlike the solid one, and back to 0.8% once the triangles are put
# in order.
#
# These guard the three things that were got WRONG on the way to that, each of
# which measured like a success at the time.


def test_the_ordering_reaches_every_page_and_is_not_a_setting(tmp_path):
    """Both the window and a saved page draw through the same writer, and a
    page with no movement in it can still be dragged round by hand -- so this
    is not part of the turning engine and not something to switch on."""
    js = ti3gamut._ORDER_JS
    assert "window.cqOrder" in js
    import plotly.graph_objects as go
    fig = go.Figure(go.Scatter3d(x=[0, 1], y=[0, 1], z=[0, 1], name="A paper"))
    out = tmp_path / "still.html"
    ti3gamut._write_dark_html(fig, out, mode="dark", spin=None,
                              carry_viewer=False, controls=False)
    assert "window.cqOrder" in out.read_text(encoding="utf-8"), (
        "a page with no turning in it at all still needs this")


def test_the_order_is_taken_from_the_DIRECTION_of_the_eye():
    """The first attempt worked out where the eye was among the measurements
    and sorted by distance from it. It put the eye INSIDE the shape -- 11.6,
    7.0, 18.9, for a shape running from -79 to 82 -- and made the picture
    worse at three angles out of five. A direction needs no division by a
    small number and no centre."""
    js = ti3gamut._ORDER_JS
    assert "function lineOfSight" in js
    assert "getCamera" in js, (
        "and read mid-drag, or the shape is ordered for where it used to be"
    )


def test_the_quick_door_re_sends_what_the_library_itself_gave():
    """Handing the surface a triangle list ALONE declares it solid.

        this.hasAlpha = false;
        "opacity" in given && (this.opacity = given.opacity,
                               this.opacity < 1 && (this.hasAlpha = true));

    -- and `hasAlpha` is the whole of whether it is see-through. The picture
    came back matching the solid one perfectly, which read as a flawless fix
    and was the shape being genuinely opaque: the wall behind it stopped
    coming through, 99.9% of it to 0.4%. Nothing but asking what was BEHIND
    the shape could tell those two apart.
    """
    js = ti3gamut._ORDER_JS
    assert "function remember" in js and "__cqGiven" in js, (
        "the library's own parameters are kept and re-sent, rather than a "
        "new set being built here -- one field wrong would fail as quietly")
    assert "isTransparent" in js, (
        "and it is checked afterwards, because the next version of the "
        "library may reset something else the same way")


def test_a_faded_colour_makes_a_surface_see_through_at_full_strength():
    """A strength of 1 does not mean solid. The library reads

        colour.length === 3 ? push(r, g, b, this.opacity)
                            : (push(...), a < 1 && (this.hasAlpha = true))

    so the fade over the part two shapes agree on -- which is written one
    colour at a time -- makes a see-through surface that tears in exactly the
    same way."""
    js = ti3gamut._ORDER_JS
    assert "someColourFades" in js
    assert "!(t.opacity < 1) && !someColourFades" in js


def test_greying_a_shape_keeps_a_fade_it_was_given():
    """Two switches, one quietly undoing the other: greying one of two shapes
    took its faded colours from 179 to none, while the shape left alone kept
    all 308 of its own."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert '"rgba(" + v + "," + v + "," + v + "," + a + ")"' in js
    assert "if (bits.length > 3)" in js, (
        "the fourth number is read back off the colour it came in with")


def test_the_ordering_never_takes_more_than_its_share_of_the_time():
    """978 triangles for one measured chart, 19,230 when the Detail slider is
    at 40 -- 2.3ms and 19.4ms, and the second is longer than a frame. Rather
    than guess a count at which to give up, the last one is timed."""
    js = ti3gamut._ORDER_JS
    assert "var cost = 0, ready = 0;" in js
    assert "cost * 3" in js


def test_a_shape_style_nobody_handles_is_refused_rather_than_drawn_empty():
    """Found while auditing, by asking for "outline".

    That is a real style name in this file -- it belongs to a CHART'S SKIN --
    and handing it to build_figure as a shape style matched neither of the two
    branches that add a surface. The page came back with nought traces: it
    opened, reported nothing wrong, and held an empty box, which reads exactly
    like a rendering fault. The window can only send the three, so this is not
    reachable from the controls, but it is reachable from the command line and
    from any other caller."""
    import pytest
    from pathlib import Path
    import ti3gamut
    from gamutview import build_gamut
    demo = Path(__file__).resolve().parent.parent / "demo"
    m = ti3gamut.read_ti3(demo / "Glossy-paper.ti3")
    g = build_gamut(m.lab, m.device, input_space="lab", space="lab")

    # Every style the window offers still draws something.
    for style in ti3gamut.SHAPE_STYLES:
        fig = ti3gamut.build_figure([("g", g)], "", styles=[style])
        assert len(fig.data) >= 2, f"{style} drew {len(fig.data)} traces"

    with pytest.raises(ValueError) as complaint:
        ti3gamut.build_figure([("g", g)], "", styles=["outline"])
    said = str(complaint.value)
    assert "outline" in said
    # It has to say what IS allowed, not only that this was not.
    for style in ti3gamut.SHAPE_STYLES:
        assert style in said, f"the complaint never mentions {style}"


def test_the_styles_the_window_offers_are_the_styles_that_can_be_drawn():
    """The list and the controls must not drift apart. If a fourth style is
    ever added to one and not the other, this says so rather than letting a
    page come out empty."""
    import ti3gamut
    import gamut_app
    import inspect
    src = inspect.getsource(gamut_app.GamutApp)
    offered = set()
    for line in src.splitlines():
        if "combo.addItem(" in line and line.rstrip().endswith(")"):
            bits = line.split('"')
            if len(bits) >= 5:
                offered.add(bits[3])
    assert set(ti3gamut.SHAPE_STYLES) <= offered | {"solid"}, (
        f"a style is drawable but not offered: "
        f"{set(ti3gamut.SHAPE_STYLES) - offered}")


# ------------------------------------------------------------- one pool
#
# Sorting each shape's own triangles fixes each shape and cannot fix two of
# them against each other: the library draws one whole surface and then the
# next, and two gamuts of the same printer pass THROUGH each other, so
# whichever goes down first is wrong over half the picture. Measured against a
# welded reference at eight camera angles, two shapes at their own strengths
# were 68.5% wrong on average and 76.6% at the worst angle.
#
# So all the see-through surfaces are handed to one drawn object per frame and
# sorted as a single pool. These guard the three things that had to survive
# that, each of which would fail silently.


def test_every_see_through_surface_is_sorted_as_one_pool():
    js = ti3gamut._ORDER_JS
    assert "function getPool" in js and "function poolable" in js
    assert "pool.host.update(one)" in js, (
        "the whole pool goes to ONE drawn object; the others are emptied")
    assert "blank.cells = EMPTY" in js


def test_a_strength_per_shape_survives_the_pool():
    """One surface has one opacity and two shapes may be set to two. The
    library multiplies each vertex's alpha by the surface's opacity, so
    folding one into the other loses nothing -- and the pooled surface must
    then be at FULL strength, or the second shape is faded twice."""
    js = ti3gamut._ORDER_JS
    assert "a * op" in js, "each vertex carries its own shape's strength"
    assert "one.opacity = 1;" in js


def test_shapes_lit_differently_are_not_pooled():
    """One surface has one light and one roughness. Every shape may be given
    its own amount of shape definition, which is a different lighting, and
    there is no honest way to give one surface two -- so those keep the
    per-shape ordering they had rather than getting a wrong picture."""
    js = ti3gamut._ORDER_JS
    assert "var LIT = [" in js
    for named in ("ambient", "diffuse", "specular", "roughness", "fresnel"):
        assert f"'{named}'" in js, f"{named} is not compared before pooling"
    assert "lightPosition" in js


def test_the_pool_says_which_shape_the_pointer_is_over():
    """Pooled, every triangle belongs to the first surface, so asking what is
    under the pointer would name the first shape everywhere. Each shape owns a
    known stretch of the pooled vertices and answers for its own."""
    js = ti3gamut._ORDER_JS
    assert "function ownHover" in js
    assert "handlePick" in js and "mine.lo" in js and "mine.hi" in js
    assert "e.object = heldObject" in js, (
        "and the selection is put back, so the next trace is asked fairly")


def test_the_pool_proves_it_landed_rather_than_assuming_it():
    """A handover that quietly drew the old triangles would look like a fix
    and be nothing. The count the surface reports back is the only thing that
    says otherwise -- the same lesson as the shape that matched the solid
    picture by having gone opaque."""
    js = ti3gamut._ORDER_JS
    assert "pool.host.triangleCount !== pool.m" in js
    assert "isTransparent" in js


def test_a_shape_hidden_from_the_key_is_not_looked_for():
    """Clicking a shape's name hides it by setting its visibility to the
    string "legendonly", which is neither true nor false. Tested for `false`,
    a hidden shape got through, the drawn object for it could not be found,
    and the whole picture fell back to the slow door for as long as it stayed
    hidden."""
    js = ti3gamut._ORDER_JS
    assert "t.visible !== true" in js, (
        "'legendonly' is not false, and a test for false lets it through")


def test_an_emptied_surface_gets_its_triangles_back():
    """A shape whose strength is turned up to solid stops being pooled, and a
    surface still holding no triangles would simply vanish."""
    js = ti3gamut._ORDER_JS
    assert "function restore" in js
    assert "P.blanked = objs.slice(1)" in js


def test_the_pool_measures_depth_in_the_measurements_own_units():
    """Two sets of numbers are available and they are not the same.

    What the library was handed has each axis multiplied by that axis's own
    scale; the direction the eye is in is deliberately put back into the
    measurements' units. Drawn in true proportions the scales agree and the
    order comes out the same either way, which is why using the wrong one went
    unnoticed. Measured on a chart's skin over two shapes, where they do not
    agree: 5.4% off a correctly blended reference, and 0.02% once the
    midpoints came from the same place the direction does.
    """
    js = ti3gamut._ORDER_JS
    assert "pool.mid[into + f] = A2.mid[f]" in js, (
        "the pool has to take each surface's own midpoints, which are already "
        "in the right units, rather than working new ones out from the drawn "
        "vertices")
    assert "if (A2.m !== had2.cells.length) return null;" in js, (
        "and only when the two really are the same surface")


# ------------------------------------------------------- a wire cage
#
# Three controls drew a wireframe by switching a surface's `contour` setting
# on. The drawing library documents that field as "dynamic contours … on
# hover": it draws lines under the pointer and nothing the rest of the time.
# Measured with the movement stopped and a noise floor of nought, pressing
# "wires" on a published page changed the picture by 0 pixels, and the chart
# skin's "Mesh" drew the identical 214,308 pixels that "Solid" draws.


def test_a_surfaces_contour_setting_is_never_used_to_draw_a_cage():
    """It is not a wireframe, it is a hover decoration, and it looks exactly
    like the thing somebody reaches for."""
    import inspect
    import ti3gamut
    src = inspect.getsource(ti3gamut)
    # The only mentions left are the ones explaining why it is not used.
    for line in src.splitlines():
        if "contour=dict(show=" in line:
            raise AssertionError(
                f"a surface is still being asked to draw its own wires: {line}")


def test_a_cage_is_built_from_the_edges_themselves():
    import ti3gamut
    import numpy as np
    points = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]])
    faces = np.array([[0, 1, 2], [1, 3, 2]])
    xs, ys, zs = ti3gamut._wire_segments(points, faces)
    # Five edges, not six: the two triangles share one, and a shared edge
    # drawn twice is twice the work for an identical picture.
    assert len(xs) == 5 * 3
    assert xs.count(None) == 5
    assert len(xs) == len(ys) == len(zs)


def test_the_chart_skins_three_styles_draw_three_different_things():
    from pathlib import Path
    import numpy as np
    import ti3gamut
    demo = Path(__file__).resolve().parent.parent / "demo"
    m = ti3gamut.read_ti3(demo / "Glossy-paper.ti3")

    def kinds(style):
        fig = ti3gamut.build_figure(
            [], "", space="lab", chart=("chart", m.lab, None),
            chart_look=dict(skin=style, skin_opacity=0.30))
        return [t.type + ("/lines" if getattr(t, "mode", "") == "lines" else "")
                for t in fig.data]

    solid, mesh, outline = kinds("solid"), kinds("mesh"), kinds("outline")
    assert "mesh3d" in solid and "scatter3d/lines" not in solid, solid
    # Mesh is a surface AND its cage -- not the surface on its own, which is
    # what it used to be.
    assert "mesh3d" in mesh and "scatter3d/lines" in mesh, mesh
    # Outline only means only the outline: no surface at all, rather than one
    # at a fiftieth of strength standing in for its absence.
    assert "mesh3d" not in outline and "scatter3d/lines" in outline, outline


def test_the_saved_page_builds_its_cage_rather_than_carrying_one():
    """The surface already holds every vertex and triangle, so a cage costs
    the file nothing -- and it is drawn in the surface's own colours, which is
    what "a net over its surface" has to mean."""
    js = ti3gamut._CONTROLS_JS if hasattr(ti3gamut, "_CONTROLS_JS") else None
    import inspect
    src = js or inspect.getsource(ti3gamut)
    assert "function buildCage" in src
    assert "function bandOf" in src, (
        "a line takes one colour for the whole trace, so a coloured cage is "
        "grouped into bands the way the application groups them")
    assert "deleteTraces" in src, "and turning it off has to remove them"


def test_a_page_opens_with_the_lettering_it_will_keep():
    """The axis numbers and names are declared, not inherited.

    Left unset, each axis keeps the drawing library's own default of #444 and
    the numbers are drawn in the page font, which LOOKS right and is not the
    same thing. The first relayout resolves them properly and they change
    colour — which is what happened: pressing the page-colour button dimmed
    every axis number and name and returning to the colouring the page was
    saved in did not bring them back, so a page that had been looked at no
    longer matched the page that was sent. Measured on the real page, dark →
    light → none → slate → ink → dark left 6,264 pixels different; with the
    colour declared it leaves 0.
    """
    for which in ("dark", "light"):
        fig = ti3gamut.build_figure([], "", space="lab", mode=which)
        want = ti3gamut.SCENE_COLOURS[which]["text"]
        scene = fig.layout.scene
        for axis in (scene.xaxis, scene.yaxis, scene.zaxis):
            assert axis.color == want, (
                f"{which}: the axis lettering is {axis.color!r}, not the "
                f"page's reading colour {want!r} — so it will change the "
                f"first time anything redraws the axes")


def test_the_colour_button_leaves_the_lettering_readable():
    """It set the axis colour to `caption`, which is the dim grey the small
    title line is drawn in — so every axis number faded on the first press."""
    import inspect
    src = inspect.getsource(ti3gamut)
    for axis in ("xaxis", "yaxis", "zaxis"):
        assert f'"scene.{axis}.color": p.text' in src, (
            f"scene.{axis}.color must follow the page's reading colour")
        assert f'"scene.{axis}.color": p.caption' not in src
    # The flat cross-section view has the same two lines, and had the same bug.
    assert '"xaxis.color": p.text, "yaxis.color": p.text' in src
    # A title IS a caption, so that one keeps it.
    assert '"title.font.color": p.caption' in src


def test_a_remembered_choice_cannot_shut_the_reader_out():
    """Reloading is the only thing a reader can do, so it has to work.

    What the reader last chose is applied while the page is opening, so
    anything that goes wrong applying it goes wrong again on every reload —
    and there is no console on a phone and no menu on this page. Reported
    exactly that way: a press hung the page, and reloading replayed the press
    that hung it.

    A mark is written before the choices are applied AND before every press,
    and taken off a frame later. Finding it still set means the last attempt
    never finished, so the choices go and the page opens the way it was
    saved — which is always a state that works, because it is the state the
    file was written in.
    """
    js = ti3gamut._SPIN_CONTROLS_JS
    assert 'var OPENING = STORE + ":opening"' in js
    # Set before the risky work in BOTH places, or the reader needs two
    # reloads to get out, and nobody reloads twice.
    recall = js[js.index("function recall()"):]
    recall = recall[:recall.index("\n  }")]
    assert "busy();" in recall, "the restore must mark before it applies"
    handler = js[js.index("function handler(ev)"):]
    handler = handler[:handler.index("\n  }")]
    assert "busy();" in handler, "a press must mark before it does the work"
    # Cleared only after a frame — reaching one is what proves the browser is
    # still answering. Cleared inline it would prove nothing.
    settled = js[js.index("function settled()"):]
    settled = settled[:settled.index("\n  }")]
    assert "requestAnimationFrame" in settled and "opened" in settled
    assert "localStorage.removeItem(STORE)" in recall, (
        "a stored choice that did not survive being applied must be thrown "
        "away, not kept to fail again")


def test_the_figures_underneath_follow_the_page_colours():
    """They are part of the page, and they did not follow it.

    The written-out figures are put in the file with their colours stated on
    the element, from the palette the page was saved in. So a page saved dark
    and switched to light kept a black block of text under a pale picture —
    and on "ink", the one colouring that exists to be printed, it left a solid
    black rectangle across the bottom of the page.

    Spotted in a screenshot of the five colourings side by side, which is the
    argument for making that picture at all.
    """
    js = ti3gamut._SPIN_CONTROLS_JS
    mode = js[js.index("function applyMode()"):]
    mode = mode[:mode.index("\n  }")]
    assert 'querySelectorAll(".cq-notes")' in mode, (
        "the figures under the picture must be repainted with the page")
    assert "style.color = p.text" in mode and "style.background = p.page" in mode


def _lab_of(hexcol):
    """sRGB hex to CIELAB, D65 — enough for asking "is this grey neutral"."""
    h = hexcol.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
           for c in rgb]
    x = 0.4124 * lin[0] + 0.3576 * lin[1] + 0.1805 * lin[2]
    y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    z = 0.0193 * lin[0] + 0.1192 * lin[1] + 0.9505 * lin[2]

    def f(t):
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) \
            + 4 / 29
    fx, fy, fz = f(x / 0.95047), f(y / 1.0), f(z / 1.08883)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def test_the_neutral_ground_is_actually_neutral():
    """slate exists to be judged against, so a cast in it is a fault.

    Its claim is that "a gamut on black looks brighter than it really is and
    one on white looks duller" — so this one is halfway and honest. Every
    part of it was a blue-grey of about 4 units of chroma, which is small to
    look at and works against exactly that: a faintly blue surround pushes a
    neutral towards warm by simultaneous contrast, so the ground being used
    to judge a colour was tinting it.

    Each part is now the neutral grey of the same lightness it had, so the
    contrasts are unchanged and only the cast is gone.
    """
    slate = ti3gamut.SCENE_COLOURS["slate"]
    for part, colour in slate.items():
        if not str(colour).startswith("#"):
            continue
        _L, a, b = _lab_of(colour)
        chroma = (a * a + b * b) ** 0.5
        assert chroma < 0.5, (
            f"slate's {part} is {colour}, {chroma:.1f} units off neutral — "
            f"the one scheme whose whole purpose is not tinting what is "
            f"judged against it")


def test_the_neutral_ground_sits_near_the_middle():
    """Halfway is the point of it; a 'neutral' at L* 20 would not be."""
    L, _a, _b = _lab_of(ti3gamut.SCENE_COLOURS["slate"]["page"])
    assert 44 < L < 56, f"slate's ground is L* {L:.1f}, not near the middle"


def test_the_slider_draws_the_cut_the_same_way_the_page_does():
    """One cut, one resolution — or the picture changes when it is touched.

    The page is DRAWN with `slice_at`'s default, and the reader's slider
    restyles it from outlines carried in the file. Those were worked out at
    120 points against a default of 180, on the argument that the difference
    cannot be seen. Side by side it cannot; in one page it can, because the
    first press of the cut swaps one for the other and the shape visibly
    coarsens — and returning to the height it started at does not undo it,
    since the fine outline is gone. Measured: the reading came back to L* 50
    exactly and 3,141 pixels of the picture did not, on a page whose noise
    floor is 0.
    """
    import inspect as _inspect
    from gamutview import slice_at
    drawn = _inspect.signature(slice_at).parameters["steps"].default
    assert ti3gamut._CUT_POINTS == drawn, (
        f"the slider carries outlines at {ti3gamut._CUT_POINTS} points while "
        f"the page is drawn at {drawn}, so touching the cut changes the "
        f"picture and moving it back does not change it back")


# --------------------------------------------------------- carrying on turning

def test_momentum_is_off_unless_a_page_asks_for_it():
    """A page saved before this existed carries no `glide` at all, and reading
    a missing setting must leave those pages behaving exactly as they did."""
    src = ti3gamut._SPIN_CONTROLS_JS
    assert "var carries = !!settings.glide;" in src, (
        "the page must read its own setting, and read a missing one as off")


def test_a_throw_is_measured_from_the_live_camera_not_the_layout():
    """THE FAULT THIS AVOIDS, measured: during a drag the camera in the layout
    does not move — 0.000 across a 180px drag — because the drawing library
    keeps the real one inside the built scene until the gesture ends. Reading
    the layout would make every throw come out as no throw at all."""
    src = ti3gamut._SPIN_JS
    body = src[src.index("function angles(gd)"):]
    body = body[:body.index("function shortest")]
    assert "liveCam(gd)" in body, "the speed must come from the live camera"
    assert "gd.layout" not in body, (
        "reading gd.layout here gives a stale camera and no throw")


def test_a_throw_dies_by_the_clock_not_by_the_frame():
    """three.js's own damping is applied per FRAME, so the same page dies
    twice as fast on a 120Hz iPad as on a 60Hz laptop. An iPad is where this
    was asked for, so the decay is per elapsed second instead."""
    src = ti3gamut._SPIN_JS
    assert "Math.pow(0.5, dt / HALF_LIFE)" in src, (
        "the decay must be taken over elapsed time, not per frame")


def test_a_hard_flick_cannot_send_it_spinning():
    """"Not like crazy after letting go, just a bit." How far a throw carries
    is speed x HALF_LIFE / ln2, so the cap on the speed is the cap on the
    travel: 150 degrees a second over a 0.22s half-life is about 48 degrees,
    whatever the flick."""
    src = ti3gamut._SPIN_JS
    assert "var FASTEST = 150 * Math.PI / 180;" in src
    assert "var HALF_LIFE = 0.22;" in src
    carries = 150 * 0.22 / math.log(2)
    assert 30 < carries < 60, (
        f"the hardest possible throw carries {carries:.0f} degrees, which is "
        f"not 'just a bit'")


def test_every_way_of_stopping_it_stops_it():
    """A moving thing you cannot stop is worse than one that never moved.
    Touching it, pausing, asking for a fixed view and putting the view back
    must each end a throw — and the first is what anybody tries first."""
    src = ti3gamut._SPIN_JS
    for where, why in [
            ("function hold()", "touching the shape, or a wheel, or a pinch"),
            ("function reset()", "putting the view back"),
            ("function look(name)", "asking for a fixed view"),
    ]:
        body = src[src.index(where):]
        body = body[:body.index("\n  function ", 10)]
        assert "stopGlide()" in body, f"a throw survives {why}"
    assert "if (o.on === false) stopGlide();" in src, "Pause must stop a throw"


def test_a_flat_cut_is_never_given_momentum():
    """A cross-section is drawn looking straight down and cannot be turned at
    all, so there is nothing for a throw to carry — and a control that is
    present and does nothing is worse than a missing one."""
    src = ti3gamut._SPIN_CONTROLS_JS
    assert "glide: carries && !flat" in src
    assert 'if (!flat && on("glide", false))' in src


def test_the_page_is_told_whether_it_may_carry_on(tmp_path):
    """The window's own view never has momentum; a saved page has it when the
    person saving it asked for that, and not otherwise."""
    import gamut_app
    src = inspect.getsource(gamut_app.GamutApp._spin_options)
    assert "glide: bool = False" in src or "glide=bool(glide)" in src
    assert "glide=bool(glide)" in src, (
        "the setting must reach the page's engine")


# --------------------------------------------------------------------------
# A page that fetches its viewer, and the reader who is told the wrong thing
# --------------------------------------------------------------------------

def test_a_failed_fetch_does_not_blame_the_connection(tmp_path):
    """"this one still tells me to reload when i have connection although i
    do have." The commonest way a 5 MB download fails on a phone is being
    interrupted -- switching app, locking the screen -- not being offline, and
    the page said the one thing it could not know."""
    import numpy as np

    import ti3gamut

    lab = np.column_stack([np.linspace(20, 90, 30), np.linspace(-40, 40, 30),
                           np.linspace(40, -40, 30)])
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, np.linspace(0, 5, 30), "d"))
    out = tmp_path / "cdn.html"
    ti3gamut._write_dark_html(fig, out, "dark", carry_viewer=False)
    body = out.read_text(encoding="utf-8")

    assert "the download was interrupted" in body
    assert "does not necessarily mean you are offline" in body


def test_a_page_that_fetches_its_viewer_offers_a_way_to_try_again(tmp_path):
    """Telling somebody to reload is useless when the line is fine. The
    button re-fetches without losing the page."""
    import numpy as np

    import ti3gamut

    lab = np.column_stack([np.linspace(20, 90, 30), np.linspace(-40, 40, 30),
                           np.linspace(40, -40, 30)])
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, np.linspace(0, 5, 30), "d"))
    out = tmp_path / "cdn.html"
    ti3gamut._write_dark_html(fig, out, "dark", carry_viewer=False)
    body = out.read_text(encoding="utf-8")

    assert 'data-cq="retry"' in body
    assert "min-height:44px" in body, "a finger needs about 44 px"
    # THE RETRY MUST REDRAW, or it puts the library in place with nothing left
    # asking it to draw anything: notice gone, page blank, reader worse off.
    assert 'id="cq-draw"' in body
    assert "document.getElementById('cq-draw')" in body
    # and it must fetch a fresh address, or a cached failure is served again
    assert "cq-retry=" in body


def test_a_page_that_carries_its_viewer_has_none_of_that(tmp_path):
    """Nothing is fetched, so there is nothing to explain or retry."""
    import numpy as np

    import ti3gamut

    lab = np.column_stack([np.linspace(20, 90, 30), np.linspace(-40, 40, 30),
                           np.linspace(40, -40, 30)])
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, np.linspace(0, 5, 30), "d"))
    out = tmp_path / "inline.html"
    ti3gamut._write_dark_html(fig, out, "dark", carry_viewer=True)
    body = out.read_text(encoding="utf-8")
    assert 'data-cq="retry"' not in body
    assert "cq-noviewer" not in body


# --------------------------------------------------------------------------
# The box must not move when a family is switched off
# --------------------------------------------------------------------------

def test_hiding_a_family_cannot_move_the_axes(tmp_path):
    """"when turning more and more options in the legend off the axes change
    their division and the view changes every time."

    Left to itself the drawing library fits the box to whatever is switched
    on. Measured on the published page: hiding one family moved the a* axis
    from -88..92.4 to -87.6..79. It also destroys the reason to hide one --
    "where does this family sit" cannot be answered by a box that resizes
    itself to the answer."""
    import numpy as np

    import ti3gamut

    rng = np.random.default_rng(2)
    n = 400
    lab = np.column_stack([rng.uniform(20, 92, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, rng.uniform(0, 6, n), "d", None,
                                       True))
    scene = fig.layout.scene
    for axis in (scene.xaxis, scene.yaxis, scene.zaxis):
        assert axis.autorange is False, "an axis is still free to rescale"
        assert axis.range is not None
    # the range covers every colour, not only the ones a reader leaves on
    assert scene.xaxis.range[0] <= lab[:, 1].min()
    assert scene.xaxis.range[1] >= lab[:, 1].max()
    assert scene.zaxis.range[0] <= lab[:, 0].min()
    assert scene.zaxis.range[1] >= lab[:, 0].max()


def test_the_room_keeps_its_shape_when_only_the_greys_are_left(tmp_path):
    """"when only greys are visible due to the distorted room there is no more
    legend on the right side as well." With aspectmode "data" the library also
    works the room's shape out from the ranges, so pinning the ranges alone is
    half of it."""
    import numpy as np

    import ti3gamut

    rng = np.random.default_rng(3)
    n = 300
    lab = np.column_stack([rng.uniform(20, 92, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, rng.uniform(0, 6, n), "d", None,
                                       True))
    assert fig.layout.scene.aspectmode == "manual"
    sides = [fig.layout.scene.aspectratio.x, fig.layout.scene.aspectratio.y,
             fig.layout.scene.aspectratio.z]
    assert all(side > 0 for side in sides)

    # THE SHAPE OF THE ROOM IS WHAT THIS GUARDS, not which side happens to be
    # the 1. It used to say `x == 1.0`, because the ratio was divided by x;
    # dividing by the LONGEST side instead -- so that a room can never be
    # drawn larger than the picture holding it -- leaves the proportions
    # identical and moves the 1 to whichever side is longest. Asserting the
    # convention rather than the property would have failed on a change that
    # kept every promise this test was written for.
    assert abs(max(sides) - 1.0) < 1e-9, (
        f"the longest side is {max(sides)}, so the room is drawn larger than "
        f"the picture that holds it")
    assert max(sides) <= ti3gamut.ROOM_CEILING, (
        "a pinned room may not exceed what was measured to fit either")

    # AND IT IS THE SAME ROOM WHATEVER IS SHOWN, which is the fault reported:
    # with only the greys left the ranges collapse, and a room worked out
    # from them would be a sliver.
    greys = lab[np.abs(lab[:, 1:]).max(axis=1) < 3]
    if len(greys) > 3:
        only = ti3gamut.build_figure(
            [], "x", mode="dark", space="lab", grid=True,
            drift=(lab, rng.uniform(0, 6, n), "d", None, True))
        again = [only.layout.scene.aspectratio.x,
                 only.layout.scene.aspectratio.y,
                 only.layout.scene.aspectratio.z]
        assert all(abs(a - b) < 1e-9 for a, b in zip(sides, again)), (
            "the room changed shape when the picture did")


def test_every_drift_cloud_has_its_box_pinned(tmp_path):
    """PINNED WHETHER OR NOT IT IS SPLIT, and that "whether or not" is the
    point. It was tied to the family split at first, on the reasoning that
    only a split picture could lose points. The ΔE threshold then gave the
    UNSPLIT picture a second way to lose them, the rule did not cover it, and
    the squashed walls came back — reported twice, from two different
    switches. A rule with an "except when" in it gets outgrown."""
    import numpy as np

    import ti3gamut

    rng = np.random.default_rng(4)
    n = 200
    lab = np.column_stack([rng.uniform(20, 92, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    for split in (False, True):
        fig = ti3gamut.build_figure([], "x", mode="dark", space="lab",
                                    grid=True,
                                    drift=(lab, rng.uniform(0, 6, n), "d",
                                           None, split))
        scene = fig.layout.scene
        assert scene.aspectmode == "manual", "the room can still be reshaped"
        for axis in (scene.xaxis, scene.yaxis, scene.zaxis):
            assert axis.autorange is False
            assert axis.range is not None


def test_only_the_reset_that_goes_home_is_offered(tmp_path):
    """Two resets a pixel apart, and the inviting one is the worse view.

    MEASURED IN A BROWSER, by turning the shape with the mouse and pressing
    each button in the viewer's own strip:

        Reset camera to last save   ->  eye 1.5, 1.5, 1.5   (where it opened)
        Reset camera to default     ->  eye 1.25, 1.25, 1.25

    The second is the framing build_figure pulls away from on purpose — it
    frames the data tightly, so a wide flat gamut opens as a cropped close-up
    of its middle. Nothing was added to fix this: the reader already had the
    right button, and now it is the only one.

    THE FIRST ATTEMPT AT THIS ADDED A BUTTON OF ITS OWN, floating in the
    picture's corner — and it covered the strip. Reported within minutes: "in
    the main window there already is a reset button and the new custom one
    covers this and the other buttons the viewer offers."
    """
    import numpy as np

    import ti3gamut

    rng = np.random.default_rng(41)
    lab = np.column_stack([rng.uniform(20, 92, 60), rng.uniform(-60, 60, 60),
                           rng.uniform(-60, 60, 60)])
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, rng.uniform(0.6, 3, 60), "d"))
    out = tmp_path / "one-reset.html"
    ti3gamut._write_dark_html(fig, out, "dark", carry_viewer=False)
    page = out.read_text(encoding="utf-8")
    assert "resetCameraDefault3d" in page, (
        "the strip offers the library's own framing again")
    assert "modeBarButtonsToRemove" in page
    # and the one that goes home is NOT taken away with it
    assert "resetCameraLastSave3d" not in page


def test_every_arrangement_carries_the_numbers(tmp_path):
    """ONE OF THE FOUR SAVED LESS THAN THE OTHERS, IN SILENCE.

    This window can show four arrangements — one scene, two rooms, a
    cross-section, two cross-sections — and the Save dialog asks, for all
    four, whether the numbers should travel with the picture. Only the single
    3D scene ever carried them. The other three arrived with the styling for a
    block of figures, five rules of it, and no figures.

    FOUND BY ASKING EACH PAGE WHICH CONTROLS IT BUILDS: the cross-section
    would not build "put the numbers away", because there was nothing to put
    away. Neither a screenshot nor a reading of one page could have shown it —
    it needed all four written and compared.
    """
    import numpy as np

    import ti3gamut

    rng = np.random.default_rng(61)

    def blob(scale):
        pts = rng.normal(size=(60, 3)) * np.array([12.0, 20.0, 20.0]) * scale
        pts[:, 0] += 50.0
        return ti3gamut.build_gamut(pts, input_space="lab", space="lab")

    two = [("paper-1", blob(1.0)), ("paper-2", blob(0.7))]
    NOTES = "Matte-paper holds 812,144 units of colour."

    made = {}
    ti3gamut.write_html(two[:1], tmp_path / "one.html", "one", notes=NOTES,
                        carry_viewer=False)
    made["one scene"] = tmp_path / "one.html"
    ti3gamut.write_slice_html(two, tmp_path / "cut.html", 50.0, "a cut",
                              notes=NOTES, carry_viewer=False)
    made["a cross-section"] = tmp_path / "cut.html"
    pages = [(name, ti3gamut.build_figure([(name, g)], name))
             for name, g in two]
    ti3gamut.write_side_by_side_html(pages, tmp_path / "rooms.html",
                                     notes=NOTES)
    made["two rooms"] = tmp_path / "rooms.html"
    flat = [(name, ti3gamut.build_slice_figure([(name, g)], 50.0, name))
            for name, g in two]
    ti3gamut.write_side_by_side_html(flat, tmp_path / "cuts.html",
                                     notes=NOTES)
    made["two cross-sections"] = tmp_path / "cuts.html"

    missing = [where for where, path in made.items()
               if NOTES not in path.read_text(encoding="utf-8")]
    assert not missing, f"these arrangements dropped the numbers: {missing}"


def test_a_page_fits_itself_to_a_tall_narrow_pane():
    """A portrait pane cropped the shape and lost the lightness axis entirely.

    The eye at 1.5 frames a printer's gamut for a pane wider than it is tall.
    The application's own view becomes portrait on a laptop — 424 wide by 833
    tall at a 1000px window — and there the magenta side ran off the edge and
    the whole L* axis was outside the view. Measured on the app's own pane,
    counting lit pixels in the outermost six columns:

        pane 1024   0 left   0 right
        pane  624  85 left  36 right      <- before
        pane  424 108 left 123 right      <- before
        every one   0 left   0 right      <- after

    THE CONDITIONS MATTER AS MUCH AS THE FIT. A page that re-fitted on every
    resize would overrule a reader who had turned the shape, so the fitting
    stops the moment anybody touches it and starts again when they press
    "back to the start".
    """
    import ti3gamut

    js = ti3gamut._SPIN_JS
    assert "function fitToPane" in js
    # A pane wider than it is tall gets the view the page was written with,
    # which is every desktop window and every saved page opened normally --
    # and is also what a window dragged narrow and then wide again must get
    # back.
    assert "var pull = (h <= w) ? 1 : Math.min(2, h / w);" in js
    # ALWAYS FROM THE WRITTEN VIEW. Fitting from wherever the camera happens
    # to be compounds: two rooms in a window dragged narrower twice went
    # 1.500 -> 2.007 -> 3.904, each pull applied to the one before it.
    assert "if (!base[id]) base[id]" in js
    assert "from.eye.x * pull" in js
    # The reader's own view wins, and pressing home hands it back.
    assert "function untouched(id) { return !touched[id]; }" in js
    assert "touched[ids[i]] = false;" in js


def test_one_cross_section_gets_the_same_air_as_two():
    """A single cut sat exactly on its own frame.

    Two panes side by side have always had room around them — slice_extent
    pads its square by 8% — while a single cut was left to the drawing
    library, which fits the axis exactly to the data. Measured in the
    application's own pane before this was fixed:

        x range  -82.579 … 82.404
        the data -82.579 … 82.404

    so the widest colours sat ON the frame, and in a narrow window that reads
    as a picture cut off.
    """
    import numpy as np

    import ti3gamut
    from gamutview import build_gamut

    rng = np.random.default_rng(9)
    points = rng.normal(size=(200, 3)) * np.array([12.0, 24.0, 24.0])
    points[:, 0] += 50.0
    gamuts = [("paper", build_gamut(points, input_space="lab", space="lab"))]

    fig = ti3gamut.build_slice_figure(gamuts, 50.0, "a cut")
    span = fig.layout.xaxis.range
    assert span is not None, "a single cut still fits its axis to the data"
    widest = max(abs(v) for v in span)
    # The air is the same 8% the two-pane path uses, so the two cannot drift.
    inside = ti3gamut.slice_extent(gamuts, 50.0)
    assert inside is not None
    assert round(span[0], 6) == round(inside[0][0], 6)
    assert round(span[1], 6) == round(inside[0][1], 6)
    assert widest > 0

    # AND NOT ON A PAGE THAT CARRIES A SLIDER. Those step through many
    # heights, and a range worked out from the one being drawn would rescale
    # the picture under the reader's hand at every step.
    slidable = ti3gamut.build_slice_figure(gamuts, 50.0, "a cut",
                                           slidable=True)
    assert slidable.layout.xaxis.range is None


def test_the_caption_fits_the_pane_it_is_in():
    """One line written for a wide pane runs off a narrow one.

    Photographed in the application's cross-section at a 1000px window:
    "…measured from a D50 white · lightness L* = 50" stopped mid-word at the
    frame, and measured there at 512 pixels of text in a 424 pixel pane.

    NOT PART OF THE MOVEMENT SCRIPT, which is where it was written first: a
    cross-section has no camera, so the flat view carries no movement script
    at all — asked of the running page, which answered `cqSpin? False` — and
    the flat view is exactly where the caption is longest.
    """
    import ti3gamut

    js = ti3gamut._CAPTION_JS
    # It breaks where the caption itself joins its clauses, which is where a
    # reader would break it. Asserted as the character rather than as the
    # escape: the script is an ordinary Python string, so \u00b7 in the source
    # is already a middle dot by the time the page is written -- and a test
    # that insisted on the escape would be testing how the source is spelled
    # rather than what the page does.
    assert 'JOIN = "  \u00b7  "' in js
    # And it remembers the one-line form so widening puts it back — measured
    # from the real width, not guessed from the wrapped one, which kept a
    # caption in two lines through a window half as wide again as it needed.
    assert "asOneLine[key] = wide;" in js
    assert "asOneLine[key] <= room" in js
    # Every page gets it: still or moving, flat or not.
    import inspect

    writer = inspect.getsource(ti3gamut._write_dark_html)
    assert "_CAPTION_JS" in writer


def test_a_page_arrives_with_the_far_wall_drawn_first():
    """The mechanism working is not the same claim as it being switched on.

    scripts/audit_the_wall_order.py measures the wall order by throwing the
    switch itself, so it says nothing about what a reader actually gets --
    proved by mutation: the default was switched off in the source and that
    audit still reported "Clean", because it turns it on before it looks.

    This is the other half, and it is the half a reader feels: a page must
    ARRIVE with the far wall drawn before the near one.
    """
    import ti3gamut

    js = ti3gamut._ORDER_JS
    assert "var wall = true" in js, (
        "pages are written with the wall order off, so the kite-shaped "
        "wedges come back however well the switch works")
    # AND THE ENGINE SAYS SO, which is what lets the audit ask.
    assert "wall: wall" in js, (
        "how() no longer reports the default, so nothing can check it")


# --- the height the sender was looking at ---------------------------------
#
# A saved cross-section is drawn at the sender's exact lightness and titled
# with it, while the slider under it can only reach the levels the page
# carries -- and those sit on a 2.0 grid. Saved at L* 51 the picture said 51
# and the strip said 50: the page disagreed with itself, and nothing in the
# suite would have noticed. Found by an agent driving the real window, then
# confirmed here from the grid itself: 45 levels from 10 to 98, and 51 not
# among them.

def _one_gamut():
    """A shape to cut, built without ArgyllCMS so this runs anywhere."""
    import numpy as np
    from gamutview import Gamut
    from scipy.spatial import ConvexHull
    rng = np.random.default_rng(7)
    pts = rng.normal(size=(400, 3)) * (26.0, 30.0, 30.0) + (52.0, 0.0, 0.0)
    hull = ConvexHull(pts)
    kept = pts[hull.vertices]
    # The same shape every run: a hull of 400 seeded points, tall enough in
    # lightness to be cut at several heights. Built the way test_chart.py
    # builds one rather than a second way of my own.
    return Gamut(vertices=kept, faces=ConvexHull(kept).simplices,
                 colors=np.zeros((len(kept), 3)), volume=1.0,
                 space="lab", mode="hull")


def test_a_cut_saved_at_an_odd_lightness_can_be_slid_back_to():
    """The level the page opens at is the one its title claims."""
    gamuts = [("paper", _one_gamut())]
    cuts = ti3gamut.slice_levels(gamuts, include=51.0)
    assert cuts is not None
    levels = [round(float(v), 3) for v in cuts["levels"]]
    assert 51.0 in levels, (
        "a page saved at L* 51 must be able to open at L* 51; the grid is "
        f"every {ti3gamut._CUT_STEP} and would otherwise stop at 50 or 52")
    nearest = min(range(len(levels)), key=lambda i: abs(levels[i] - 51.0))
    assert levels[nearest] == 51.0, "the strip would open a step off its title"


def test_the_grid_is_not_padded_when_it_already_has_the_height():
    """Nothing extra is carried when the sender was on the grid anyway."""
    gamuts = [("paper", _one_gamut())]
    plain = ti3gamut.slice_levels(gamuts)
    onit = ti3gamut.slice_levels(gamuts, include=plain["levels"][3])
    assert len(onit["levels"]) == len(plain["levels"])


def test_a_height_outside_the_shape_is_not_invented():
    """A lightness no part of the shape reaches adds no level."""
    gamuts = [("paper", _one_gamut())]
    plain = ti3gamut.slice_levels(gamuts)
    far = ti3gamut.slice_levels(gamuts, include=max(plain["levels"]) + 40)
    assert len(far["levels"]) == len(plain["levels"])
