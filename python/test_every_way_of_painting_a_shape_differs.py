"""Five ways of painting a shape, and no two of them may draw the same thing.

WHY THIS EXISTS. A control that quietly does what another already does is the
fault this project has met from the other side twice this week — a tick that
drew nothing until something else was touched, and a slider whose value never
reached the picture. The colouring chooser offers five answers to "what should
the colours mean", and each is a different question:

    true       the colours those patches will actually print as
    solid      one colour for the whole shape
    lightness  a ramp by how light each corner is
    chroma     a ramp by how far from grey it is
    accent     the window's own accent, shaded

If two of them come out the same, one of the five is a control with nothing
behind it — and nobody would see that from the outside, because both would
look like a perfectly good picture.

MEASURED, on a real paper, corner by corner. Every pair differs at 468 or
more of 491 corners, and the closest pair — the two ramps — averages 47.9
levels apart:

    true      vs solid       491 of 491 corners,  mean 170.0
    true      vs accent      485 of 491,          mean  32.6   ← closest
    lightness vs chroma      468 of 491,          mean  47.9

REAL MEASUREMENTS, not an invented ball: a made-up shape has a smooth even
spread of lightness and chroma, which is exactly the case where two ramps
would agree by accident.
"""
import itertools
import pathlib
import re
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


@pytest.fixture(scope="module")
def painted():
    import ti3gamut
    from gamutview import build_gamut
    paper = _DEMO / "Glossy-paper.ti3"
    if not paper.is_file():
        pytest.skip("no demo paper to measure")
    m = ti3gamut.read_measurement(paper)
    gamut = build_gamut(m.lab, m.device, input_space="lab")
    # A CHOOSER THIS TEST CANNOT SEE LOOKS EXACTLY LIKE ONE WHOSE ANSWERS ALL
    # DIFFER. Five is what the window offers.
    assert len(ti3gamut.SHAPE_PAINTS) >= 4, (
        f"only {len(ti3gamut.SHAPE_PAINTS)} ways of painting a shape found — "
        f"this rule is asking about a list it cannot see")
    out = {}
    for paint in ti3gamut.SHAPE_PAINTS:
        figure = ti3gamut.build_figure([("Glossy-paper", gamut)], "",
                                       paint=paint)
        meshes = [t for t in figure.data if t.type == "mesh3d"]
        assert meshes, f"painting a shape {paint!r} drew no surface at all"
        colours = meshes[0].vertexcolor
        assert colours is not None and len(colours) > 100, (
            f"{paint!r} put {0 if colours is None else len(colours)} colours "
            f"on a shape with hundreds of corners")
        out[paint] = np.array(
            [[int(n) for n in re.findall(r"\d+", c)] for c in colours], float)
    return out


def test_no_two_colourings_draw_the_same_picture(painted):
    for a, b in itertools.combinations(sorted(painted), 2):
        apart = np.abs(painted[a] - painted[b]).max(axis=1)
        differing = int((apart > 2).sum())
        assert differing > len(apart) * 0.5, (
            f"painting a shape by {a!r} and by {b!r} gives the same colours "
            f"at {len(apart) - differing} of {len(apart)} corners — one of "
            f"those two controls is doing nothing a reader could see")
        assert apart.mean() > 10, (
            f"{a!r} and {b!r} are only {apart.mean():.1f} levels apart on "
            f"average, which is not a choice anybody can act on")


def test_one_colour_each_really_is_one_colour(painted):
    # The answer known in advance for the one of the five that says what it
    # will be: every corner the same.
    one = painted["solid"]
    assert np.abs(one - one[0]).max() < 3, (
        "'one colour each' is painting a shape in more than one colour")


def test_the_true_colours_are_not_one_colour(painted):
    # And its opposite, so the test above cannot pass by everything being flat.
    true = painted["true"]
    assert np.abs(true - true[0]).max() > 40, (
        "the true colours are all the same, which no measured paper is")
