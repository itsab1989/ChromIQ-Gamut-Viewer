"""A setting made for one shape must reach that shape and no other.

WHY THIS EXISTS. The window lets several settings be set for ONE shape rather
than for all of them — how solid it is, how deep the fade goes, how it is
painted, how many rings it holds, and the colour of its cage. The fault that
goes with that is on record in this project, from the solidity slider: "one
shape meant all of them while the handle was down". It is invisible from the
outside, because a picture where both shapes moved looks exactly as reasonable
as one where the right one did.

So both halves are asked here, for every setting that can belong to one shape:

    the shape it was set for CHANGES      — or the setting did nothing;
    every other shape stays IDENTICAL     — or it reached further than asked.

Only the second half is the interesting one, and it is the one no check asked.

REAL PAPERS, and two DIFFERENT ones: with the same shape twice, "the other
shape did not change" can pass while a setting reaches both, because the two
traces would agree anyway.
"""
import copy
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"

#: Each setting a shape can carry on its own, and a value away from the
#: window-wide default so the picture has somewhere to go.
#: …and, where a setting needs one, the way the shapes have to be DRAWN for
#: it to have anything to act on. The colour of a cage cannot show on a shape
#: drawn solid: there is no cage. Asked without that, it reported the setting
#: as doing nothing — which would have been a fault in the fixture reported as
#: a fault in the window.
OWN = [("how solid it is", {"opacity": 0.25}, None),
       ("how deep the fade goes", {"depth": 0.9}, None),
       ("how it is painted", {"paint": "lightness"}, None),
       ("how many rings it holds", {"rings": 8}, None),
       ("the colour of its cage", {"mesh_paint": "accent"}, ["mesh", "mesh"])]


@pytest.fixture(scope="module")
def two_papers():
    import ti3gamut
    from gamutview import build_gamut
    files = [_DEMO / "Glossy-paper.ti3", _DEMO / "Matte-paper.ti3"]
    for f in files:
        if not f.is_file():
            pytest.skip(f"no {f.name} to draw with")
    shapes = [(f.stem, build_gamut(ti3gamut.read_measurement(f).lab,
                                   input_space="lab")) for f in files]
    # TWO DIFFERENT SHAPES. With the same paper twice, "the other one did not
    # change" would pass on a setting that reached both.
    a, b = (json.dumps(list(map(list, s.vertices[:20]))) for _n, s in shapes)
    assert a != b, "the two fixtures are the same shape, so this proves nothing"

    def picture(per_shape, styles=None):
        figure = ti3gamut.build_figure(shapes, "", per_shape=per_shape,
                                       rings=4, styles=styles)
        drawn = json.loads(figure.to_json())["data"]
        mine = [t for t in drawn if str(t.get("name", "")).startswith("Glossy")]
        theirs = [t for t in drawn if str(t.get("name", "")).startswith("Matte")]
        # A PICTURE THAT DREW NEITHER SHAPE WOULD PASS EVERY LINE BELOW.
        assert mine and theirs, (
            f"the two shapes drew {len(mine)} and {len(theirs)} traces — "
            f"there is nothing here to have changed")
        return mine, theirs

    return picture


@pytest.mark.parametrize("what,setting,styles", OWN,
                         ids=[o[0].replace(" ", "-") for o in OWN])
def test_it_reaches_the_shape_it_was_set_for(two_papers, what, setting, styles):
    plain = two_papers([{}, {}], styles)[0]
    changed = two_papers([copy.deepcopy(setting), {}], styles)[0]
    assert plain != changed, (
        f"setting {what} for the first shape alone changed nothing about it")


@pytest.mark.parametrize("what,setting,styles", OWN,
                         ids=[o[0].replace(" ", "-") for o in OWN])
def test_it_leaves_the_other_shape_alone(two_papers, what, setting, styles):
    before = two_papers([{}, {}], styles)[1]
    after = two_papers([copy.deepcopy(setting), {}], styles)[1]
    assert before == after, (
        f"setting {what} for the FIRST shape also changed the second — one "
        f"shape meaning all of them is the fault the solidity slider had, "
        f"and a picture where both moved looks just as reasonable as one "
        f"where the right one did")
