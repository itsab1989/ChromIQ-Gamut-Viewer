"""A saved page has to be able to fade the lid, and could not.

THE PAGE FADES FOR ITSELF, IN JAVASCRIPT. Its rule is `withAlpha`
(`ti3gamut.py`, in the spin script): it takes the TEXT of a colour, and
anything whose text has no "(" in it comes back untouched. The lid's colours
arrive as float triples in 0..1, so they were rewritten into "rgba(...)" —
but only when `_lid_alpha < 1.0`, which is the case the WINDOW had already
dealt with. At the default "where they differ" of 100 the lid went out as
floats, and nothing the reader did to the page afterwards could fade it.

Measured on a real profile against sRGB, agree 45, both solid, the page's own
"where they differ" clicked down to 0%, lid on against lid off:

    before   134,453 pixels of opaque lid
    after     13,133

and the lid's own first colour, read out of the running page:

    before   rgb(5,0,12)            unchanged by the fade
    after    rgba(5,0,12,0.000)

⚠ THE 13,133 THAT REMAIN ARE NOT THE LID'S COLOUR. They are a fully
transparent mesh still being composited: the page can recolour triangles but
cannot DROP them, which is what `_solid_remainder` does for the shells in
Python. Spread over the whole shape at a median 34 of 255. Written down
rather than counted as fixed.

This is the fault `test_the_lid_fades_with_what_it_closes.py` is named for,
fixed on the Python side and left standing in the page's JavaScript, and the
only check on it asked whether the mask EXISTS rather than whether the page
could use it.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


def _the_pages_own_rule(colour, alpha):
    """`withAlpha`, in Python, and deliberately no cleverer than it is.

    A copy of a rule is a weak test if it drifts, so it is kept to the one
    thing that matters and the original is quoted beside it:

        if (alpha >= 1 || text.indexOf("(") < 0) return colour;
    """
    text = str(colour)
    if "(" not in text:
        return colour, False
    bits = text[text.index("(") + 1:text.index(")")].split(",")
    return (f"rgba({bits[0]},{bits[1]},{bits[2]},{alpha:.3f})", True)


@pytest.fixture(scope="module")
def figure_with_a_lid():
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut
    paper_file = _DEMO / "Glossy-paper.ti3"
    if not paper_file.is_file():
        pytest.skip("no demo paper to cut")
    paper = build_gamut(ti3gamut.read_measurement(paper_file).lab,
                        input_space="lab")
    srgb = reference_gamut("sRGB", steps=20)
    ti3gamut._LAST_CUT = None
    ti3gamut._LAST_CAP = None
    return ti3gamut.build_figure(
        [("Glossy-paper", paper), ("sRGB", srgb)], "fade",
        agree=0.45, split=True, cap=True, styles=["solid", "solid"],
        camera={"eye": dict(x=1, y=1, z=1)})


def _lids(fig):
    return [t for t in fig.data
            if "where it is cut" in str(getattr(t, "name", ""))]


def test_the_lid_goes_out_as_text_the_page_can_act_on(figure_with_a_lid):
    """AT FULL STRENGTH, which is the case that was broken and the default."""
    lids = _lids(figure_with_a_lid)
    assert lids, "no lid was drawn at all, so this measures nothing"
    for lid in lids:
        colours = list(lid.vertexcolor)
        assert len(colours) > 100, f"{lid.name} has hardly any colours"
        for one in (colours[0], colours[len(colours) // 2], colours[-1]):
            faded, could = _the_pages_own_rule(one, 0.0)
            assert could, (
                f"{lid.name} wears {one!r}, which the page's own fade hands "
                f"back untouched — a lid that cannot be faded on the page")
            assert faded.endswith(",0.000)"), faded


def test_every_shape_and_its_lid_agree_about_what_a_colour_looks_like(
        figure_with_a_lid):
    """THE SHELL'S COLOURS WERE ALWAYS TEXT. The lid's being floats is the
    whole of the fault, so the two must not disagree about the form."""
    fig = figure_with_a_lid
    shells = [t for t in fig.data
              if getattr(t, "type", "") == "mesh3d"
              and "where it is cut" not in str(getattr(t, "name", ""))
              and getattr(t, "vertexcolor", None) is not None]
    assert shells, "no shell to compare against"
    for trace in shells + _lids(fig):
        one = list(trace.vertexcolor)[0]
        assert isinstance(one, str) and "(" in one, (
            f"{trace.name} wears {one!r}, which is not a colour the page's "
            f"fade can read")


def test_the_lid_still_carries_a_mask_the_page_can_fade_by(figure_with_a_lid):
    """AND THE COLOUR IS ONLY HALF OF IT. The page picks the alpha per vertex
    from `meta.stand`; text the rule can read is no use without one."""
    for lid in _lids(figure_with_a_lid):
        stand = (lid.meta or {}).get("stand")
        assert stand, f"{lid.name} carries no mask for the page to fade by"
        assert len(stand) == len(list(lid.vertexcolor)), (
            f"{lid.name}'s mask is {len(stand)} long against "
            f"{len(list(lid.vertexcolor))} colours")
        assert set(stand) == {"1"}, (
            f"{lid.name}'s mask is not all standing: {sorted(set(stand))}")


def test_the_lid_ships_no_corner_it_does_not_draw(figure_with_a_lid):
    """HALF OF ONE LID'S CORNERS WERE CARRIED AND NEVER USED.

    `close_the_cut` hands back ONE array for the piece and its lid, because
    the two share the seam by BEING the same corners — so the piece's own
    inside corners come with it and no lid triangle names them. Measured on
    Glossy-paper against sRGB at Detail 20 before this was trimmed: sRGB's lid
    shipped 7,053 corners and used 3,472, so 3,581 of them — 50.8% — carried a
    position, a colour and a character of the fade mask into every saved page
    and were never drawn. A page with two lids in it went from 5,898,144 to
    5,672,517 bytes, and the picture is identical to the pixel.

    ⚠ TRIMMED WHERE THE TRACE IS BUILT, NOT IN `cap_over_the_cut`, whose
    corners keep `close_the_cut`'s numbering. That is what lets a check
    compare built against drawn corner for corner, which is how the tuck is
    held to being one number straight down each ray.
    """
    lids = _lids(figure_with_a_lid)
    assert lids, "no lid was drawn at all"
    for lid in lids:
        corners = len(lid.x)
        assert corners > 100, f"{lid.name} has hardly any corners"
        used = set(int(n) for n in lid.i) | set(int(n) for n in lid.j) \
            | set(int(n) for n in lid.k)
        assert max(used) < corners, (
            f"{lid.name} names corner {max(used)} of {corners}")
        spare = corners - len(used)
        assert spare == 0, (
            f"{lid.name} ships {corners} corners and draws {len(used)} — "
            f"{spare} ({100 * spare / corners:.1f}%) are carried into every "
            f"saved page and never used")
        assert len(list(lid.vertexcolor)) == corners, (
            f"{lid.name} has {len(list(lid.vertexcolor))} colours for "
            f"{corners} corners")
        assert len((lid.meta or {}).get("stand", "")) == corners, (
            f"{lid.name}'s fade mask is not one character per corner")
