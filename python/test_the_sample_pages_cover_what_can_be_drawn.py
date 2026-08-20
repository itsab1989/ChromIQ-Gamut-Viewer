"""Every way of drawing a shape must appear in at least one saved page.

WHY THIS EXISTS, and it cost two faults in one day. On 2026-08-21 two things
were reported from the window:

    the out-of-reach boundary ran in stair-steps with TWO papers and a
    comparison open together;
    a simple skin looked scattered.

Both were real, and every check in this project passed while they were broken.
Measured across the 23 sample pages at the time: NOT ONE was drawn as a simple
skin, and exactly ONE showed what a paper cannot print — with a single paper,
which is the case that already worked. The checks were not weak; they were
reading a folder that did not contain the pictures.

`docs/pages` is what almost everything reads: the size sweep, the three-engine
sweep, the layout check, the live-change audit, the showcase. A way of drawing
that never appears there is a way of drawing nothing tests — so this asks the
folder whether it still holds one of each.

IT IS DELIBERATELY NOT A CROSSING. Every option against every other is
thousands of pages; what is asked here is that each DISTINCT KIND of picture
exists at least once, which is what the two faults needed and did not have.
"""
import pathlib

import pytest

_PAGES = pathlib.Path(__file__).resolve().parent.parent / "docs" / "pages"


@pytest.fixture(scope="module")
def pages():
    found = sorted(_PAGES.glob("*.html"))
    # A FOLDER THIS CHECK CANNOT SEE LOOKS EXACTLY LIKE ONE WITH EVERY KIND
    # OF PICTURE IN IT. Twenty is well under what is there and well over what
    # a rename or a moved folder would leave.
    assert len(found) >= 20, (
        f"only {len(found)} saved pages found under {_PAGES} — this rule "
        f"cannot see the folder it is asking about, so it is not checking "
        f"anything")
    return [(p.name, p.read_text(encoding="utf-8", errors="ignore"))
            for p in found]


def _holding(pages, what, test):
    named = [name for name, text in pages if test(text)]
    assert named, (
        f"no saved page {what} — so nothing that reads docs/pages sizes it, "
        f"opens it in three engines, drives it or photographs it, and a "
        f"fault living in that picture would pass every check in this "
        f"project. Add one to scripts/make_sample_pages.py.")
    return named


def test_a_shape_wrapped_in_a_simple_skin(pages):
    # The picture that looked scattered: a hull is full of needles and was
    # being shaded smoothly, which smears the light along them.
    _holding(pages, "is drawn as a simple skin",
             lambda t: '"flatshading":true' in t)


def test_two_shapes_judged_against_one_comparison(pages):
    # The picture whose out-of-reach boundary zig-zagged: the clean cut
    # refused the case where the marking and the fade ask different questions.
    _holding(pages, "shows TWO shapes each saying what it cannot print",
             lambda t: t.count("red is out of reach") >= 2)


def test_a_shape_that_says_what_it_cannot_print_at_all(pages):
    _holding(pages, "shows what a shape cannot print",
             lambda t: "red is out of reach" in t)


def test_two_rooms_side_by_side(pages):
    _holding(pages, "puts two shapes in rooms of their own",
             lambda t: 'class="half"' in t)


def test_a_picture_with_three_shapes_in_it(pages):
    # Two papers and a comparison is the arrangement most of the recent
    # faults have needed, and it is not the same as two shapes.
    _holding(pages, "holds three shapes at once",
             lambda t: t.count('"type":"mesh3d"') >= 3)


def test_a_page_the_reader_can_drive(pages):
    _holding(pages, "hands the reader a control strip",
             lambda t: "cq-spin-bar" in t)
