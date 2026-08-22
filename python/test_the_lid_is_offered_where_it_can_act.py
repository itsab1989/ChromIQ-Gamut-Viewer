"""The lid over the cut: drawn where there is an opening, and nowhere else.

Fading the agreement away leaves an OPEN shell, and turned round you look
into it: the far wall is lit exactly like an outside, because there is no
separate inside to shade. Reported from the window as "this one looks
scattered". The lid is the piece of the OTHER shape that lies inside this one.

WHAT THIS GUARDS is not the geometry — `test_a_lid_closes_the_cut` does that —
but the OFFER: that it appears exactly where it can act and refuses where it
cannot, because this window's own rule, paid for four times, is that a control
offered where it cannot act is worse than one that is not there.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


def _lids(figure):
    return [d for d in figure.data
            if "where it is cut" in (getattr(d, "name", "") or "")]


@pytest.fixture(scope="module")
def shapes():
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut
    paper_file = _DEMO / "Glossy-paper.ti3"
    if not paper_file.is_file():
        pytest.skip("no demo paper")
    paper = build_gamut(ti3gamut.read_measurement(paper_file).lab,
                        input_space="lab")
    return (paper, reference_gamut("sRGB", steps=24),
            reference_gamut("Display P3", steps=24))


def _fresh():
    """The kept answers cleared, so one case cannot serve another's lid."""
    import ti3gamut
    ti3gamut._LAST_CUT = None
    ti3gamut._LAST_CAP = None


def test_a_pair_with_an_opening_gets_a_lid(shapes):
    import ti3gamut
    paper, srgb, _p3 = shapes
    _fresh()
    fig = ti3gamut.build_figure([("Glossy-paper", paper), ("sRGB", srgb)],
                                "t", agree=0.0, cap=True)
    lids = _lids(fig)
    assert lids, "no lid was drawn for a pair with the agreement faded away"
    for lid in lids:
        assert len(np.asarray(lid.i)) > 100, (
            f"the lid has only {len(np.asarray(lid.i))} triangles")
        assert lid.vertexcolor is not None, "the lid was not painted"


def test_no_lid_where_nothing_has_been_cut_away(shapes):
    """At full strength the shape is whole: a lid would be a second skin.

    ⚠ WITH `split=True`, WHICH IS WHAT THE WINDOW SENDS. A saved page has to
    be able to move the slider itself, so the window asks for the masks even
    at full strength — and only then are they there to build a lid from.
    Asked WITHOUT it the masks are never worked out at all, so no lid appears
    whatever the guard says, and a mutation removing the guard passed.
    """
    import ti3gamut
    paper, srgb, _p3 = shapes
    _fresh()
    plain = ti3gamut.build_figure([("Glossy-paper", paper), ("sRGB", srgb)],
                                  "t", agree=0.0, split=True, cap=True)
    assert _lids(plain), (
        "no lid even with the agreement faded away — the case below cannot "
        "tell a working guard from a lid that never appears")
    _fresh()
    fig = ti3gamut.build_figure([("Glossy-paper", paper), ("sRGB", srgb)],
                                "t", agree=1.0, split=True, cap=True)
    assert not _lids(fig), (
        "a lid was drawn over a shape with no opening in it")


def test_no_lid_when_it_is_not_asked_for(shapes):
    import ti3gamut
    paper, srgb, _p3 = shapes
    _fresh()
    fig = ti3gamut.build_figure([("Glossy-paper", paper), ("sRGB", srgb)],
                                "t", agree=0.0, cap=False)
    assert not _lids(fig), "a lid was drawn without being asked for"


def test_three_shapes_are_refused_rather_than_guessed_at(shapes):
    """With three, the hole ends at whichever of the others comes first.

    That is a different construction from this one, and capping against one
    arbitrary neighbour would be quietly wrong — so it declines, and the
    window dims the tick with the reason.
    """
    import ti3gamut
    paper, srgb, p3 = shapes
    _fresh()
    three = [("Glossy-paper", paper), ("sRGB", srgb), ("Display P3", p3)]
    fig = ti3gamut.build_figure(three, "t", agree=0.0, cap=True)
    assert not _lids(fig), (
        "a lid was drawn for three shapes, where 'the other shape' is not one "
        "shape at all")
    # and the pair it is built from DOES get one, so this is not passing
    # because nothing anywhere gets a lid
    _fresh()
    pair = ti3gamut.build_figure(three[:2], "t", agree=0.0, cap=True)
    assert _lids(pair), (
        "the same shapes as a pair get no lid either — this test is not "
        "measuring the refusal, it is measuring a lid that never appears")


def test_the_lid_wears_the_other_shape_s_colours(shapes):
    """It IS that shape's surface, so it is painted in its colours."""
    import ti3gamut
    paper, srgb, _p3 = shapes
    _fresh()
    out, _f, stands, _l = ti3gamut.recut_where_they_part(
        [("Glossy-paper", paper), ("sRGB", srgb)])
    got = ti3gamut.cap_over_the_cut(out, stands, 0)
    assert got is not None, "nothing to check"
    corners, faces, colours = got
    assert len(colours) == len(corners), "a colour is missing from a corner"
    assert (colours >= 0).all() and (colours <= 1).all(), (
        "the lid's colours are outside 0..1")
    # sRGB's own surface is vivid; the grey the paint falls back to when a ray
    # misses would be a flat 0.5 everywhere
    spread = float(np.ptp(colours, axis=0).mean())
    assert spread > 0.3, (
        f"the lid's colours vary by only {spread:.3f} — it is not wearing the "
        f"other shape's colours, it is a flat fill")


def test_the_hover_is_short_enough_to_read_going_past():
    """Hovers stay under 200 characters; the long version is behind the ⓘ.

    Asked for in as many words, and this is the third control to be held to
    it.
    """
    text = pathlib.Path(__file__).resolve().parent / "gamut_app.py"
    body = text.read_text(encoding="utf-8")
    start = body.index('self._close_cut.setToolTip(')
    chunk = body[start:body.index(')', body.index('"', start) + 1) + 1]
    words = "".join(part for part in chunk.split('"')[1::2])
    assert 0 < len(words) <= 200, (
        f"the lid's hover is {len(words)} characters; a hover is read on the "
        f"way past and the long version belongs behind the ⓘ")
    assert "Needs" in words, (
        "the hover does not say what the control needs before it can act")


# ---------------------------------------------------------------------------
# THE OFFER ITSELF, which this file was named for and did not test. A hostile
# reading gutted `_apply_closing_availability` to "always enabled, no reason"
# and disconnected the tick from the drawing entirely, and ALL 1,006 tests
# still passed. Both are covered below.
# ---------------------------------------------------------------------------


class _Tick:
    """Just enough of a checkbox to be dimmed and given a reason."""

    def __init__(self):
        self.on, self.enabled, self.tip = False, True, ""

    def isChecked(self):          # noqa: N802 — Qt's spelling
        return self.on

    def setEnabled(self, yes):    # noqa: N802
        self.enabled = bool(yes)

    def setToolTip(self, text):   # noqa: N802
        self.tip = text


class _Slider:
    def __init__(self, v):
        self._v = v

    def value(self):
        return self._v


class _Box:
    def __init__(self, on=False):
        self._on = on

    def isChecked(self):          # noqa: N802
        return self._on


class _Combo:
    def __init__(self, data):
        self._data = data

    def currentData(self):        # noqa: N802
        return self._data

    def currentText(self):        # noqa: N802
        return self._data


def _window(shapes=2, agree=30, differ=100, style="solid", second="solid",
            rooms=False, slice_on=False, run=False, marking=None):
    """The real availability rule, run against stub controls."""
    import gamut_app
    who = type("Stub", (), {})()
    who._close_cut = _Tick()
    who._agree, who._differ = _Slider(agree), _Slider(differ)
    who._style_mine, who._style_second = _Combo(style), _Combo(second)
    who._side_by_side, who._slice_on = _Box(rooms), _Box(slice_on)
    who._run_drawn = run
    who._scene_inputs = ([None] * shapes, None, None, marking)
    gamut_app.GamutApp._apply_closing_availability(who)
    return who._close_cut


def test_the_tick_is_offered_exactly_where_the_drawing_can_act():
    """Every condition the drawing tests, and no paraphrase of one.

    The drawing asks for two shapes, `agree` below full, a shape drawn as a
    surface, no out-of-reach marking, and a single-room picture. This used to
    ask for two shapes and ANY fade, which left the tick inviting a click and
    answering with nothing in four separate states.
    """
    assert _window().enabled, "the plain case is not offered"
    cases = {
        "one shape": dict(shapes=1),
        "three shapes": dict(shapes=3),
        "nothing faded": dict(agree=100),
        "only the differ fade": dict(agree=100, differ=30),
        "both drawn as outlines": dict(style="mesh", second="mesh"),
        "two rooms": dict(rooms=True),
        "a cross-section": dict(slice_on=True),
        "a run of profiles": dict(run=True),
        "what is out of reach is marked": dict(marking=[object(), None]),
    }
    for why, how in cases.items():
        tick = _window(**how)
        assert not tick.enabled, (
            f"the tick is offered with {why}, where the drawing draws nothing")
        assert tick.tip and len(tick.tip) <= 200, (
            f"with {why} the tick gives no reason, or one too long to read "
            f"going past ({len(tick.tip)} characters)")
    # AND IT MUST NOT BE DIMMED WHERE IT WORKS: one outline is enough, since
    # the other shape still gets its lid.
    assert _window(second="mesh").enabled, (
        "one shape drawn as an outline should not take the other's lid away")


def test_the_tick_reaches_the_drawing():
    """Disconnecting it passed every other test in the suite.

    `cap=` is handed to `build_figure` at the call site rather than through
    `_render_options`, so there is nothing to read back off an object — the
    wiring is the source line, and this is what watches it.
    """
    body = (pathlib.Path(__file__).resolve().parent
            / "gamut_app.py").read_text(encoding="utf-8")
    assert "cap=self._close_cut.isChecked()," in body, (
        "the tick no longer reaches the drawing: build_figure is being told "
        "something other than what the reader ticked")


def test_it_is_remembered_between_sessions():
    """Being absent from the table is invisible to every other test.

    `_persisted()` is checked for controls it LISTS — that each round-trips —
    and never for whether a control is listed at all. So a new option simply
    left out is remembered by nobody and noticed by nothing: this one was, for
    a day, because a multi-part edit died on an assertion before it reached
    that line.
    """
    body = (pathlib.Path(__file__).resolve().parent
            / "gamut_app.py").read_text(encoding="utf-8")
    assert '("close_cut", self._close_cut, "check", False)' in body, (
        "the lid's tick is not in `_persisted()`, so it comes back unticked "
        "however the reader left it")


# ---------------------------------------------------------------------------
# What the hostile review of 2026-08-22 found: the conditions above are every
# one the drawing tests EXCEPT the two that decide most often — whether a lid
# can be made at all, and which styles the picture was really drawn with.
# ---------------------------------------------------------------------------


def test_the_pair_that_ships_is_not_offered_a_lid_it_cannot_have():
    """Glossy against Matte: one stands everywhere, the other nowhere.

    Every older condition passes — two shapes, faded, solid, one room, no
    marking — and `cap_over_the_cut` returns None for both. Measured before
    this: the tick was live and ticking it changed nothing on screen.
    """
    import numpy as np
    import ti3gamut
    from gamutview import build_gamut
    demo = pathlib.Path(__file__).resolve().parent.parent / "demo"
    made = []
    for name in ("Glossy-paper", "Matte-paper"):
        if not (demo / f"{name}.ti3").is_file():
            pytest.skip("no demo papers")
        m = ti3gamut.read_measurement(demo / f"{name}.ti3")
        made.append((name, build_gamut(np.asarray(m.lab, float),
                                       input_space="lab",
                                       drive_values=np.asarray(m.device, float))))
    assert ti3gamut.which_shapes_could_be_capped(made) == [False, False]
    out, _s, stands, _l = ti3gamut.recut_where_they_part(made)
    cut = [(made[0][0], out[0][1]), (made[1][0], out[1][1])]
    assert all(ti3gamut.cap_over_the_cut(cut, stands, i) is None for i in (0, 1)), (
        "the prediction and the drawing must agree, or one of them is lying")


def test_a_pair_that_can_be_capped_still_is():
    """The other direction: refusing too widely is the worse mistake."""
    import ti3gamut
    assert ti3gamut.which_shapes_could_be_capped(_far_apart_pair()) == [True, True]


def test_it_offers_rather_than_dims_when_it_cannot_tell():
    """A question it cannot answer must not silently turn into "no".

    Swallowing the failure and answering [False, False] dims the tick, and
    dimming one that would have worked is how the drift marker's tick was
    broken. The helper raises; the window offers.
    """
    import ti3gamut
    with pytest.raises(Exception):
        ti3gamut.which_shapes_could_be_capped([None, None])
    assert _window().enabled, (
        "the window must fall back to offering when the question cannot be "
        "answered")


def _window_with(gamuts, styles=("solid", "solid")):
    """The real rule, run against real shapes and the styles really drawn."""
    import gamut_app
    who = type("Stub", (), {})()
    who._close_cut = _Tick()
    who._agree, who._differ = _Slider(30), _Slider(100)
    who._style_mine, who._style_second = _Combo("solid"), _Combo("solid")
    who._side_by_side, who._slice_on = _Box(False), _Box(False)
    who._run_drawn = False
    who._scene_inputs = (list(gamuts), None, list(styles), None)
    gamut_app.GamutApp._apply_closing_availability(who)
    return who._close_cut


def _far_apart_pair():
    """Two shapes far enough apart that a lid between them means something.

    Two readings of one paper are 0.535 Lab apart and are refused now; see
    ti3gamut.TOO_CLOSE_TO_CLOSE and the hatched picture that prompted it.
    """
    import tempfile
    import numpy as np
    import ti3gamut
    from gamutview import build_gamut
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                           / "scripts"))
    import make_awkward_shapes
    folder = pathlib.Path(tempfile.mkdtemp(prefix="apart-"))
    make_awkward_shapes.make(folder)
    return [(n, build_gamut(np.asarray(
        ti3gamut.read_measurement(folder / f"{n}.ti3").lab, float),
        input_space="lab")) for n in ("two-lobes", "ball")]


def _demo_pair(one, two):
    import numpy as np
    import ti3gamut
    from gamutview import build_gamut
    demo = pathlib.Path(__file__).resolve().parent.parent / "demo"
    made = []
    for name in (one, two):
        if not (demo / f"{name}.ti3").is_file():
            pytest.skip("no demo papers")
        m = ti3gamut.read_measurement(demo / f"{name}.ti3")
        made.append((name, build_gamut(np.asarray(m.lab, float),
                                       input_space="lab",
                                       drive_values=np.asarray(m.device, float))))
    return made


def test_the_rule_itself_dims_on_the_pair_that_cannot_be_capped():
    """Drives `_apply_closing_availability`, not the helper underneath it.

    Written because the first version of these tests exercised only the
    helper: switching the rule's own use of it back off left all of them
    passing.
    """
    tick = _window_with(_demo_pair("Glossy-paper", "Matte-paper"))
    assert not tick.enabled, "offered on a pair where no lid can be made"
    assert "Nothing here can be closed" in tick.tip


def test_the_rule_itself_stays_live_where_a_lid_is_made():
    tick = _window_with(_far_apart_pair())
    assert tick.enabled, "dimmed on a pair that does get a lid"


def test_the_style_that_counts_is_the_one_drawn():
    """A comparison's style comes from `_style_other`, which the rule never
    read. With the paper an outline and the comparison solid, the drawing caps
    the comparison — so the tick must stay live."""
    pair = _far_apart_pair()
    assert _window_with(pair, styles=("mesh", "solid")).enabled, (
        "dimmed although the shape the drawing would cap is drawn solid")
    assert not _window_with(pair, styles=("mesh", "mesh")).enabled, (
        "offered although nothing in the picture is drawn as a surface")
