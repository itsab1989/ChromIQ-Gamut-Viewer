"""Two rooms on a narrow window must stop being two rooms.

WHY THIS EXISTS, measured rather than argued. `write_side_by_side_html` lays
its two rooms out as a flex row — `.half {flex:1 1 0}` — with no width below
which they stop dividing the window. On a phone that gives each room half of
390px, and a 3D box is fitted to the room's HEIGHT, so the shape has nowhere
to go but through the side walls.

The page was photographed in chromium with the spin PAUSED and both rooms
pinned to the same four cameras, counting the vividly coloured pixels (the
shape; type and gridlines are grey) in each room's outermost column:

    window   each room   coloured pixels on a side wall
    390       195 px     80–155, at EVERY angle, in BOTH rooms
    620       310 px     13–91,  at every angle, in both rooms
    820       410 px     0–75,   at two angles of four
    1024      512 px     0
    1440      720 px     0

A single-room page at the same widths is clean, which is what says this is
the split and not the scene. Two narrower-window rules were already in this
stylesheet — the modebar hidden at 1024, the titles shrunk at 820 — so the
narrowness was known; halving the width was never undone.

The height is part of the fix and not a taste: stacked, the FIRST room is the
first screen, and `scripts/check_layout.py` asks that a picture hold 55–85%
of it. At 56vh each room measured 51–54% and failed that check at four sizes
in both engines. 68vh clears it at every size.

This is a gate rule rather than another browser audit because the failure
arrives with a REWRITE of the stylesheet, and would then wait for somebody to
run a browser by hand.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def _a_two_room_page(tmp_path):
    from test_gamutview import rgb_cube
    from ti3gamut import build_figure, build_gamut, write_side_by_side_html
    _, xyz = rgb_cube(5)
    g = build_gamut(xyz, white_point="D65")
    pages = [(n, build_figure([(n, g)], "")) for n in ("one", "two")]
    out = write_side_by_side_html(pages, tmp_path / "two-rooms.html")
    return out.read_text(encoding="utf-8")


def _the_narrow_rule(css: str) -> str:
    """The whole `@media (max-width:1000px)` block, brace for brace.

    NOT a fixed slice of it. A 400-character window stopped before the rule
    it was looking for and reported it missing — which is the same mistake as
    the 26-line window that found a slider connected to nothing, and the
    1400-character one that found no `split`. A SEARCH THAT STOPS SHORT SAYS
    "NOT THERE" IN EXACTLY THE SAME WORDS AS ONE THAT LOOKED EVERYWHERE.
    """
    head = "@media (max-width:1000px)"
    assert head in css, (
        "the two rooms divide the window at every width again — at 390px "
        "that is 195px each, and the shape is cut by both walls at every "
        "angle")
    rest = css.split(head, 1)[1]
    depth, out = 0, []
    for ch in rest:
        out.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
    block = "".join(out)
    assert depth == 0 and len(block) > 40, "the narrow rule is empty"
    return block


def test_the_rooms_stack_before_they_get_too_narrow(tmp_path):
    stacked = _the_narrow_rule(_a_two_room_page(tmp_path))
    assert "flex-direction:column" in stacked, (
        "the narrow-window rule no longer stacks the rooms")
    assert "max-height:none" in stacked, (
        "stacked rooms still capped at 80vh would squeeze both into one "
        "screen, which is the cramped picture this fix exists to undo")


def test_a_stacked_room_is_big_enough_to_be_a_picture(tmp_path):
    stacked = _the_narrow_rule(_a_two_room_page(tmp_path))
    tall = [line for line in stacked.splitlines() if "min-height:" in line]
    assert tall, "a stacked room has no height floor at all"
    vh = int(tall[0].split("min-height:")[1].split("vh")[0])
    # check_layout wants 55-85% of the first screen; a couple of points go to
    # the caption and the legend under each room.
    assert 57 <= vh <= 85, (
        f"a stacked room asks for {vh}vh of the screen — check_layout wants "
        f"the picture between 55% and 85% of the first screen, and it is "
        f"measured a point or two under whatever this says")


def test_the_wide_layout_is_untouched(tmp_path):
    # THE FAILURE DIRECTION THAT MATTERS MOST: 'fixing' the phone by stacking
    # everywhere would throw away the whole point of two rooms.
    css = _a_two_room_page(tmp_path)
    before = css.split("@media (max-width:1000px)", 1)[0]
    assert ".row" in before and "display:flex" in before
    assert "flex-direction:column" not in before.split(".row", 1)[1][:200], (
        "the rooms are stacked at every width now, which is not two rooms")
