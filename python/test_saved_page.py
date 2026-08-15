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
    exactly when there is nothing under it to reach. With figures, the
    picture is capped and the page scrolls; without them, there is nothing
    below the fold in the first place."""
    alone = _page(tmp_path)
    assert "overflow:hidden" in alone, "nothing below it, so nothing scrolls"
    assert "min-height:62vh" not in alone, (
        "with nothing under it the picture may have the whole window")
    with_notes = _page(tmp_path, notes="Colour held: 702,327")
    assert "overflow:auto" in with_notes
    assert "min-height:62vh" in with_notes


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
    browser: it fails silently and looks like a rendering fault."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "Array.isArray(want) ? [want] : want" in js


def test_the_key_beside_a_name_keeps_its_strength_when_the_shape_fades():
    """Every mesh here travels with a scatter of one empty point whose only
    job is a readable marker in the legend. Fading that with the surface
    fades the key, and a key nobody can see is a fault this page has had
    twice already."""
    js = ti3gamut._SPIN_CONTROLS_JS
    assert "if (!part.proxy) {" in js
    assert "patch.opacity = st.opacity" in js


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
