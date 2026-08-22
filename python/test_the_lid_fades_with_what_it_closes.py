"""A lid is the wall of what is left; fade that away and the lid goes too.

WHAT WAS WRONG. At "where they agree" 0.5 with "where they differ" at
nothing, the shell's own colours went to rgba(15,12,21,0.000) — emptied, as
asked — and the lid stayed at opacity 0.55 with opaque colours. Two coloured
membranes hanging in the space the reader had just cleared.

AND ON A SAVED PAGE it could not fade at all: the page's fade reads
`mark.charAt(v) === "1" ? differAt : agreeAt` from a trace's meta.stand, and
the lid carried no meta. The comment beside the trace records the same fault
being caught for the LEGEND ROW and not for the fade.

TWO TRAPS ON THE WAY, both of which look exactly like a fix that works:
  * `stand` is the standing mask only when the shell is SPLIT in two; the
    per-vertex mask always in scope is `standing`. Reading the wrong one left
    the lid opaque at every setting.
  * `_with_alpha` edits the TEXT of a colour and returns anything without a
    bracket untouched — and the lid's colours are float triples, not
    "rgb(...)" strings. Passing them through it changed nothing.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


@pytest.fixture(scope="module")
def two_papers(tmp_path_factory):
    """Two shapes FAR ENOUGH APART to be capped at all.

    The demo pair was used here first, and it is two readings of one paper --
    0.535 Lab apart, which `cap_over_the_cut` now refuses because a lid
    between surfaces that close cannot be told from the skin and the picture
    comes back hatched. See ti3gamut.TOO_CLOSE_TO_CLOSE.
    """
    import ti3gamut
    from gamutview import build_gamut
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                           / "scripts"))
    import make_awkward_shapes
    folder = tmp_path_factory.mktemp("apart")
    make_awkward_shapes.make(folder)
    made = []
    for name in ("two-lobes", "ball"):
        m = ti3gamut.read_measurement(folder / f"{name}.ti3")
        made.append((name, build_gamut(np.asarray(m.lab, float),
                                       input_space="lab")))
    return made


def _lid_of(gamuts, differ, split=True):
    import ti3gamut
    fig = ti3gamut.build_figure(gamuts, "t", styles=["solid", "solid"],
                                cap=True, agree=0.5, differ=differ, split=split)
    for trace in fig.data:
        if "where it is cut" in (getattr(trace, "name", "") or ""):
            return trace
    return None


def test_the_lid_is_there_at_all(two_papers):
    """Otherwise the rest of this file proves nothing."""
    assert _lid_of(two_papers, 1.0) is not None, "no lid to ask about"


def test_a_lid_fades_when_what_it_closes_fades(two_papers):
    faint = _lid_of(two_papers, 0.0)
    first = str(faint.vertexcolor[0])
    assert "rgba(" in first and first.endswith("0.000)"), (
        f"the lid stayed opaque while the shape was emptied: {first!r}")


def test_half_way_is_half_way(two_papers):
    half = str(_lid_of(two_papers, 0.5).vertexcolor[0])
    assert half.endswith("0.500)"), f"expected a half fade, got {half!r}"


def test_full_strength_carries_no_alpha_at_all(two_papers):
    """At the top of the slider the lid must not be asked to be transparent.

    ⚠ THIS USED TO SAY "AND MUST NOT BE TEXT EITHER", on the reasoning that
    text puts the mesh on the library's transparent path. That reasoning was
    wrong, and it cost a saved page its fade: the page fades in JavaScript
    through a rule that reads the TEXT of a colour and hands anything without
    a "(" straight back, so a lid written as float triples could never be
    faded by a reader. See `test_a_saved_page_can_fade_the_lid.py` — 134,453
    pixels of opaque lid at a setting where the window draws none.

    Measured before overruling it: writing the lid's colours as "rgb(...)"
    instead of floats changes the window's picture by 0 pixels, worst channel
    2 of 255, which is the rounding to whole numbers and nothing else. The
    shells have always been text.

    What is worth holding is the part underneath: at full strength there is no
    alpha on it.
    """
    whole = list(_lid_of(two_papers, 1.0).vertexcolor)
    assert whole, "the lid has no colours at all"
    for one in (whole[0], whole[len(whole) // 2], whole[-1]):
        assert "rgba" not in str(one), (
            f"at full strength the lid wears {one!r} — an alpha it was never "
            f"asked for puts the mesh on the library's transparent path")


def test_the_saved_page_can_fade_it(two_papers):
    """It needs the mask the page's fade reads, and all of it stands."""
    mark = (getattr(_lid_of(two_papers, 1.0), "meta", None) or {}).get("stand")
    assert mark, "the lid carries no standing mask, so a page cannot fade it"
    assert set(mark) == {"1"}, (
        "a lid is the wall of what STANDS; a '0' in its mask would make the "
        "page fade it with the agreeing part instead")


def test_no_mask_is_offered_when_the_shells_carry_none(two_papers):
    """It must not be singled out: with the shell whole, there is no mask on
    anything, and a lid that carried one would fade alone."""
    assert (getattr(_lid_of(two_papers, 1.0, split=False), "meta", None)
            or {}).get("stand") is None
