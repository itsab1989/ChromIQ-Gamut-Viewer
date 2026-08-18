"""What a control must do to the picture, and what it must not do to the view.

FOUR REPORTS IN ONE MORNING, and they turned out to be three faults:

  * "sliders should update the viewer 'live' not only after i let go";
  * "i drag let go it settles and after a few seconds it jumps";
  * "when clicking and dragging the shape move in the opposite direction i
    would expect" -- which is what a rebuilt page looks like when it opens
    from a camera other than the one the reader had turned it to;
  * "i don't want the mouse arrow to turn into a hand symbol in some
    occasions".

Each of these is cheap to check and expensive to find by hand, which is the
whole argument for this file.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent


def test_the_camera_travels_into_the_page():
    """A written page opens where the reader was looking, not at the default.

    THE JUMP AFTER LETTING GO OF A SLIDER WAS THIS. Anything the window
    cannot restyle in place is drawn by writing a new page and loading it,
    and a page opens at the camera it was written with -- so every rebuild
    put the shape back to three-quarters-front.
    """
    from ti3gamut import build_figure

    mine = dict(eye=dict(x=-0.4, y=2.2, z=0.15),
                up=dict(x=0, y=0, z=1), center=dict(x=0, y=0, z=0))
    fig = build_figure([], "a page", camera=mine, drift=_a_cloud())
    got = fig.layout.scene.camera
    assert (round(got.eye.x, 3), round(got.eye.y, 3), round(got.eye.z, 3)) \
        == (-0.4, 2.2, 0.15)


def test_without_one_it_still_opens_at_the_view_that_frames_a_gamut():
    """The default is not the library's -- it was raised on purpose.

    A printer's gamut is about twice as wide as it is tall, and the library's
    own framing crops it. Passing no camera must keep that, or every page
    written before this option existed changes the day it is written again.
    """
    from ti3gamut import build_figure

    eye = build_figure([], "a page", drift=_a_cloud()).layout.scene.camera.eye
    assert (eye.x, eye.y, eye.z) == (1.5, 1.5, 1.5)


def _a_cloud():
    import numpy as np

    rng = np.random.default_rng(3)
    lab = np.column_stack([rng.uniform(20, 92, 40), rng.uniform(-60, 60, 40),
                           rng.uniform(-60, 60, 40)])
    return (lab, rng.uniform(0.4, 4.0, 40), "a → b", None, False)


def test_the_settings_that_restyle_in_place_do_not_rebuild():
    """Recorded, and NOT redrawn.

    The value still has to be written down -- every future rebuild reads it
    from there, and forgetting that was its own bug once ("Show the greys"
    turned the shape down on screen and never in the settings, so the next
    rebuild closed it up again). What must not happen is the rebuild, because
    the drag has already shown the answer and the rebuild's only visible
    effects are the pause and the jump.
    """
    import gamut_app

    for key in ("opacity", "depth"):
        assert key in gamut_app.GamutApp.RESTYLED_IN_PLACE
    # And the ones that genuinely change what is drawn are NOT in the list:
    # rings are lines that do not exist yet, a painting is a different array
    # of colours per point.
    for key in ("rings", "mesh_paint"):
        assert key not in gamut_app.GamutApp.RESTYLED_IN_PLACE


def test_a_live_change_goes_only_to_the_shapes_it_was_meant_for():
    """Set this for: one shape must not fade all of them under the hand.

    It did, and it was invisible: the rebuild that followed put the others
    back. Taking the rebuild away is what would have made it visible -- one
    fix turning into the next bug -- so the picker is part of the live path.
    """
    import gamut_app

    src = gamut_app.GamutApp._which_meshes_js
    import inspect
    text = inspect.getsource(src)
    assert "isinstance(target, int)" in text
    assert "idx" in text


def test_no_hand_cursor_where_a_click_does_nothing():
    """The pointer said "press me" over labels, readouts and empty space.

    Qt hands a widget's cursor down to every child that has not asked for one
    of its own, so setting it on a group set it on everything inside the
    group. Only two links, which really do open a browser, may keep it.
    """
    text = (ROOT / "gamut_app.py").read_text(encoding="utf-8")
    hands = re.findall(r"^\s*(\w+)\.setCursor\(Qt\.CursorShape\."
                       r"PointingHandCursor\)", text, re.M)
    assert sorted(hands) == ["support", "website"], hands


@pytest.mark.parametrize("group,field", [("printed", "marker.size"),
                                         ("outside", "marker.opacity"),
                                         ("skin", "opacity")])
def test_the_chart_sliders_restyle_rather_than_rewrite(group, field):
    """Five sliders wrote and loaded the whole page on EVERY step of a drag.

    Not on release: on every step, because they were wired to valueChanged
    and straight into the redraw. A slow drag over a thousand-patch chart
    therefore rebuilt the page dozens of times, and the view went black
    between each of them.
    """
    import inspect

    import gamut_app

    text = inspect.getsource(gamut_app.GamutApp._build_controls)
    assert "_restyle_the_chart" in text
    body = inspect.getsource(gamut_app.GamutApp._restyle_the_chart)
    # AND IT LEAVES THE LEGEND ALONE. The key beside a name is drawn by a
    # trace of its own in the same group; catching it would shrink and fade
    # the key along with the dots, which is the very fault those proxies were
    # added to cure.
    assert "hoverinfo!=='skip'" in body.replace(" ", "")


def test_the_page_is_never_written_upside_down():
    """The reader's viewpoint travels; which way is up does not.

    A tilt that swings over the top of the shape leaves the scene's own "up"
    pointing DOWN — caught in a saved page as

        "up":{"x":-0.14,"y":-0.37,"z":-0.92}

    and a page opened that way is upside down and drags backwards in both
    directions. Reported, while this was being built, as exactly that: "when
    clicking and dragging the shape move in the opposite direction i would
    expect (both for up/down and left/right)".
    """
    import inspect

    import gamut_app

    text = inspect.getsource(gamut_app.GamutApp._watch_the_camera)
    assert '"up": {"x": 0, "y": 0, "z": 1}' in text
    # AND THE EYE IS STILL CARRIED, or the fix for one report would undo the
    # fix for the other: without the eye, every rebuild goes home again.
    assert '"eye": got["eye"]' in text


def test_no_written_page_carries_an_upside_down_camera():
    """The pages in docs/ are what somebody is actually sent."""
    import json
    import pathlib
    import re

    pages = sorted((ROOT.parent / "docs" / "pages").glob("*.html"))
    assert pages, "no sample pages to check"
    bad = []
    for page in pages:
        for found in re.findall(r'"camera":\{"up":\{"x":([-\d.eE]+),'
                                r'"y":([-\d.eE]+),"z":([-\d.eE]+)\}',
                                page.read_text(errors="ignore")):
            if float(found[2]) <= 0:
                bad.append(f"{page.name}: up={found}")
    assert not bad, bad


def test_a_cut_greys_out_what_it_cannot_use():
    """A flat cross-section has no surface and no light.

    MEASURED, NOT REASONED: with a cut on screen every shape control was
    touched and the page asked what changed. Rings, the styles, both fade
    sliders, the box and the measured patches all change a cut; how solid,
    how deep the shading, and the manual light do not — build_slice_figure
    takes no opacity and no lighting at all.

    The window's own rule, written where two rooms are handled: a control
    that cannot do anything is worse than a missing one, because it invites
    a change and answers with nothing.
    """
    import gamut_app

    text = (ROOT / "gamut_app.py").read_text(encoding="utf-8")
    assert "_apply_flat_availability" in text
    assert "NOTHING_TO_ACT_ON_IN_A_CUT" in text
    # And it says which switch brings them back, which is the half of a
    # message that lets somebody act on it.
    assert "Slice it at one lightness" in gamut_app.GamutApp.NOTHING_TO_ACT_ON_IN_A_CUT


def test_disabled_controls_are_actually_drawn_disabled():
    """Qt greys a disabled widget through the palette; this app paints over it.

    So a slider switched off by the application was drawn in the accent
    colour, exactly like a live one. The stylesheet has to say so itself.

    AND THE PSEUDO-STATE GOES AFTER THE SUB-CONTROL. Written the other way
    round — "QSlider:disabled::groove" — Qt dropped the groove's own height
    and radius for EVERY slider in the window, so the live ones grew a fat
    grey bar. Caught in a screenshot; this keeps it caught.
    """
    text = (ROOT / "gamut_app.py").read_text(encoding="utf-8")
    assert "QSlider::groove:horizontal:disabled" in text
    assert "QSlider::handle:horizontal:disabled" in text
    assert "QLabel:disabled" in text
    # AT THE START OF A LINE, which is where a rule lives. The first version
    # of this looked for the string anywhere and failed on the COMMENT that
    # explains the mistake -- a check reading the wrong thing, in miniature,
    # in a test written to guard against exactly that.
    assert not re.search(r"^QSlider:disabled::", text, re.M), (
        "the pseudo-state must follow the sub-control, or the rule applies to "
        "every slider in the window")


def _contrast(one: str, other: str) -> float:
    """WCAG contrast between two hex colours."""
    def channel(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    def light(hexv):
        hexv = hexv.lstrip("#")
        r, g, b = (int(hexv[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    a, b = light(one), light(other)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def test_a_switched_off_control_can_still_be_read():
    """Unavailable is not the same as invisible, in either appearance.

    A cross-section switches three controls off, and they have to say which
    they are while they are off. Measured against the group-box fill they sit
    on, before this had a colour of its own:

        dark    text 15.25:1   disabled 5.51:1
        light   text 14.66:1   disabled 2.26:1   ← LM_TEXT_FAINT, barely there

    So the disabled state has its own key rather than borrowing the one meant
    for hints.
    """
    import gamut_app

    for name, palette in gamut_app.PALETTES.items():
        against = _contrast(palette["disabled"], palette["panel"])
        alive = _contrast(palette["text"], palette["panel"])
        assert against >= 3.0, (
            f"{name}: a switched-off control comes to {against:.2f}:1 against "
            f"the panel, which is not readable")
        # And it must not be mistaken for a live one: clearly dimmer.
        assert alive > against * 1.5, (
            f"{name}: {against:.2f}:1 against {alive:.2f}:1 is not a visible "
            f"difference between live and switched off")


def test_a_file_that_cannot_be_read_takes_nothing_with_it():
    """A refused file used to close a good one.

    The window keeps the newest two files, and it made room BEFORE reading
    the new one — so when the read failed, the oldest was already gone.
    Measured, with two profiles open and a .ti3 containing no patches picked
    by mistake:

        open before   printer-2019.icc, printer-2021.icc
        said          "This file could not be used"
        open after    printer-2021.icc

    A message saying nothing worked, over a window that has quietly closed
    something, is the worst pair of facts to hand somebody.
    """
    import inspect

    import gamut_app

    text = inspect.getsource(gamut_app.GamutApp._load)
    made_room = text.index("self._slots.pop(0)")
    read_it = text.index("g, m = self._build_patiently(path)")
    assert read_it < made_room, (
        "the room is made before the file is read, so a file that cannot be "
        "read still closes one that could")


def test_two_files_with_one_name_are_two_shapes():
    """Glossy-paper.ti3 from January and Glossy-paper.ti3 from June.

    That is how somebody keeps a paper measured twice, and it put two shapes
    called Glossy-paper in the picture, two identical rows in the list and two
    identical keys in the legend. Neither the reader nor the window could tell
    them apart: "Set this for: the first shape" faded BOTH, because the live
    change finds its shape by name.

    Measured before the fix:

        surfaces   printer-2019#0, printer-2019#2
        faded      printer-2019#0, printer-2019#2   ← one shape too many
    """
    import pathlib

    import gamut_app

    class Stub:
        _slots = [(pathlib.Path("/a/January/Glossy-paper.ti3"), None, None),
                  (pathlib.Path("/a/June/Glossy-paper.ti3"), None, None)]

    names = gamut_app.GamutApp._slot_names(Stub())
    assert names == ["Glossy-paper (January)", "Glossy-paper (June)"]
    assert len(set(names)) == 2

    # AND A NAME THAT IS ALREADY ITS OWN IS LEFT ALONE: adding a folder to
    # every name would put clutter on every legend in the application to cure
    # a case that is rare.
    class Alone:
        _slots = [(pathlib.Path("/a/January/Glossy-paper.ti3"), None, None),
                  (pathlib.Path("/a/June/Matte-paper.ti3"), None, None)]

    assert gamut_app.GamutApp._slot_names(Alone()) == ["Glossy-paper",
                                                       "Matte-paper"]


def test_a_run_tells_two_profiles_of_one_name_apart():
    """One printer profiled into a folder per month shares a file name.

    A run is one device over time, so that is not a mistake — and both shells
    were called the-printer, "Set this for" offered the same words twice, and
    fading the first faded both:

        surfaces   the-printer#0, the-printer#2
        faded      the-printer#0, the-printer#2

    The date is what tells them apart, which is why the rows carry it.
    """
    import inspect

    import gamut_app

    text = inspect.getsource(gamut_app.TimelineDialog._name_in_run)
    assert "dated" in text
    # Only where a name is shared: a run of plainly-named profiles must not
    # grow a date on every legend key.
    assert "if len(same) < 2:" in text

    # AND EVERY PLACE THAT NAMES A SHELL USES IT, or the picture, the legend
    # and the picker drift apart again.
    for method in (gamut_app.TimelineDialog._shells_for,
                   gamut_app.GamutApp._name_of_shape,
                   gamut_app.GamutApp._name_the_shapes_being_styled):
        assert "_name_in_run" in inspect.getsource(method), method.__name__


def test_two_files_in_one_folder_are_told_apart_by_their_suffix():
    """Glossy-paper.ti3 and Glossy-paper.icc — this project's own demo set.

    The measurement and the profile made from it sit in ONE folder, so adding
    the folder to both names would have produced the same name twice all over
    again. What differs is taken in turn: the extension first, because
    "Glossy-paper.ti3" beside "Glossy-paper.icc" is what a person sees in
    their own folder; the folder after it; and the whole path only if even
    that is shared.
    """
    import pathlib

    import gamut_app

    class OneFolder:
        _slots = [(pathlib.Path("/demo/Glossy-paper.ti3"), None, None),
                  (pathlib.Path("/demo/Glossy-paper.icc"), None, None)]

    assert gamut_app.GamutApp._slot_names(OneFolder()) == ["Glossy-paper.ti3",
                                                            "Glossy-paper.icc"]


def test_a_step_with_two_ends_of_one_name_carries_the_dates():
    """"Where it moved — the-printer → the-printer" is not a choice.

    Every entry in the list read the same, so there was no way to pick the
    step you wanted. The step already carries both dates; they go in exactly
    where the names fail to separate.
    """
    import inspect

    import gamut_app

    text = inspect.getsource(gamut_app.TimelineDialog._fill_pictures)
    assert "step.before_on" in text and "step.after_on" in text
    assert "if before == after" in text
