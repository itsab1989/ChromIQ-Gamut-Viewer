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
