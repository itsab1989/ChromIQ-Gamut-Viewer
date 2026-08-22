"""A closeness threshold in Lab, asked in whatever space the reader chose.

`TOO_CLOSE_TO_CLOSE` refuses a lid between two shapes that run too close for
it to be told from the skin. It was a flat 1.0 — calibrated on CIELAB pairs,
where a paper spans about 260 — and it was asked in whatever space the reader
had picked. A CIE XYZ gamut spans about 1.0 IN TOTAL, so in XYZ it refused
every pair there is: `which_shapes_could_be_capped` answered [False, False]
for sRGB against Display P3 and for a real profile against sRGB, and the
picture with the tick on and the tick off differed by 0 pixels. The control
was dimmed for a whole colour space, and dimming one that would have worked
is the worse mistake.

It is a share of the diagonal of the two shapes TOGETHER now — the extent the
picture is drawn over, which is the scale a depth buffer works in. The five
pairs it was calibrated on, as that share:

    a dented ball against a ball      0.000 Lab   0.00000   refused
    one paper, months apart           0.566 Lab   0.00213   refused
    two different papers              4.749 Lab   0.01795   capped
    a paper against sRGB              6.697 Lab   0.02203   capped
    a pancake against a column       11.157 Lab   0.07007   capped
    two lobes against a ball         14.664 Lab   0.09076   capped

A two-hundredth sits 2.3x above the closest thing it must refuse and 3.6x
below the closest thing it must keep.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"
_MIDDLE = np.array([50.0, 0.0, 0.0])


@pytest.mark.parametrize("space", ("lab", "luv", "xyz"))
def test_a_lid_is_offered_and_drawn_in_every_space(space):
    """THE SAME TWO SHAPES, THE SAME QUESTION, THREE SPACES.

    Reference spaces rather than anybody's own profile, so this is fast and
    carries nothing personal.
    """
    import ti3gamut
    from references import reference_gamut
    a = reference_gamut("sRGB", steps=16, space=space)
    b = reference_gamut("Display P3", steps=16, space=space)
    gamuts = [("sRGB", a), ("Display P3", b)]
    middle = (_MIDDLE if space == "lab"
              else np.asarray(b.vertices, float).mean(axis=0))
    assert not ti3gamut.a_lid_could_not_be_told_from_the_skin(a, b, middle), (
        f"in {space} these two are judged too close for a lid, and they are "
        f"two named colour spaces one of which contains most of the other")
    ti3gamut._LAST_CUT = None
    ti3gamut._LAST_CAP = None
    offered = ti3gamut.which_shapes_could_be_capped(gamuts)
    out, _f, stands, _l = ti3gamut.recut_where_they_part(gamuts)
    cut = [("sRGB", out[0][1]), ("Display P3", out[1][1])]
    drawn = [ti3gamut.cap_over_the_cut(cut, stands, i) for i in (0, 1)]
    made = [got is not None and len(got[1]) > 100 for got in drawn]
    # ⚠ THE PROMISE, NOT A GUESS AT THE ANSWER. Display P3 contains nearly
    # all of sRGB, so sRGB has nothing standing outside it to cap and gets no
    # lid in CIELUV or XYZ — which is right, and asserting [True, True] here
    # was asserting my expectation over the shapes' own arithmetic.
    assert offered == made, (
        f"in {space} the tick says {offered} and the drawing does {made}")
    # AND A WHOLE SPACE MAY NOT GO DEAD, which is the fault this file is for.
    assert any(made), (
        f"in {space} neither shape gets a lid at all — the control is dead "
        f"in this space")


def test_the_pairs_it_was_calibrated_on_still_get_the_same_answer():
    """A THRESHOLD MOVED INTO ANOTHER FORM MUST NOT MOVE ANY VERDICT.

    Refused and capped are both asserted, so a threshold that drifted either
    way is caught — one that refuses everything passes half of any test that
    only checks refusals.
    """
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut

    def paper(stem):
        f = _DEMO / f"{stem}.ti3"
        if not f.is_file():
            pytest.skip(f"no {stem} to measure")
        return build_gamut(ti3gamut.read_measurement(f).lab, input_space="lab")

    months = (paper("Glossy-paper"), paper("Glossy-paper-months-later"))
    papers = (paper("Glossy-paper"), paper("Matte-paper"))
    against_srgb = (paper("Glossy-paper"), reference_gamut("sRGB", steps=20))
    assert ti3gamut.a_lid_could_not_be_told_from_the_skin(
        months[0], months[1], _MIDDLE), (
        "one paper measured twice is far enough apart to cap, and it is "
        "half a Lab — the picture comes back hatched")
    for name, (a, b) in (("two different papers", papers),
                         ("a paper against sRGB", against_srgb)):
        assert not ti3gamut.a_lid_could_not_be_told_from_the_skin(
            a, b, _MIDDLE), f"{name} is refused a lid it can have"


def test_the_threshold_is_a_share_and_not_a_number_of_lab():
    """ASKED BY SCALING A PAIR, not by reading the constant.

    Two shapes scaled by ten are ten times further apart and exactly as hard
    to tell apart on a picture, so the answer must not change. A flat number
    of Lab answers differently for each.
    """
    import dataclasses
    import ti3gamut
    from references import reference_gamut
    a = reference_gamut("sRGB", steps=16)
    b = reference_gamut("Display P3", steps=16)
    small = [dataclasses.replace(g, vertices=np.asarray(g.vertices, float) * 0.01)
             for g in (a, b)]
    big = [dataclasses.replace(g, vertices=np.asarray(g.vertices, float) * 100.0)
           for g in (a, b)]
    for tag, (x, y) in (("as they are", (a, b)),
                        ("a hundredth the size", small),
                        ("a hundred times the size", big)):
        middle = np.asarray(y.vertices, float).mean(axis=0)
        assert not ti3gamut.a_lid_could_not_be_told_from_the_skin(x, y, middle), (
            f"{tag}, the same two shapes are judged too close to cap")
