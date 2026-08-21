"""The drawn boundary was up to 15 Lab from where the two shapes cross.

`split_at_crossing` asks each triangle's three CORNERS which side they are on
and cuts the edges where the answer changes. That leaves two faults, and both
were measured on the paper this application ships with, against sRGB, which is
the reference most people compare to.

ONE — a facet whose corners agree is left alone, and the other shape can bulge
through its middle without reaching a corner. Three facets carrying 5.3% of
the standing area do exactly that.

TWO — between two corners of the seam the boundary is a straight line, and the
real crossing is not. That is why the seam came out IDENTICAL whether the
reference had 1,452 triangles or 60,492: one corner per crossed edge of THIS
mesh, and no more.

Sampled along the drawn seam, the gap between the two surfaces should be
nought all the way:

    as it was          29.8% of the seam strays >1 Lab, worst 14.64
    sharpened first     1.8%                            worst  1.01

A negative gap means this shape is INSIDE the other one there — the piece was
drawn standing over ground it does not reach at all.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"
_MIDDLE = np.array([50.0, 0.0, 0.0])


@pytest.fixture(scope="module")
def paper():
    import ti3gamut
    from gamutview import build_gamut
    f = _DEMO / "Glossy-paper.ti3"
    if not f.is_file():
        pytest.skip("no demo paper")
    return build_gamut(ti3gamut.read_measurement(f).lab, input_space="lab")


def _how_far_the_seam_strays(mine, theirs):
    """(share of the seam's length straying over 1 Lab, the worst of it)."""
    import ti3gamut
    from gamutview import (_rays_onto, boundary_loops, weld_by_position)
    out, _f, stands, _l = ti3gamut.recut_where_they_part(
        [("mine", mine), ("theirs", theirs)])
    cut = out[0][1]
    faces = np.asarray(cut.faces, int)
    keep = np.asarray(stands[0], bool)[faces].all(axis=1)
    kept, welded, _w = weld_by_position(cut.vertices, faces[keep])
    ask_mine = _rays_onto(mine.vertices, mine.faces, _MIDDLE)
    ask_theirs = _rays_onto(theirs.vertices, theirs.faces, _MIDDLE)
    total = strayed = worst = 0.0
    for loop in boundary_loops(welded):
        here = kept[np.asarray(loop[:-1], int)]
        nxt = np.roll(here, -1, axis=0)
        length = np.linalg.norm(nxt - here, axis=1)
        for i in range(len(here)):
            total += length[i]
            if length[i] < 0.3:
                continue
            t = np.linspace(0, 1, 9)[1:-1]
            along = here[i][None, :] + t[:, None] * (nxt[i] - here[i])[None, :]
            rays = along - _MIDDLE
            gap = float(np.nanmax(np.abs(ask_mine(rays) - ask_theirs(rays))))
            worst = max(worst, gap)
            if gap > 1.0:
                strayed += length[i]
    assert total > 100.0, (
        f"the seam is only {total:.1f} Lab long — too little to tell a good "
        f"cut from a bad one")
    return 100.0 * strayed / total, worst


def test_the_seam_lands_on_the_crossing(paper):
    from references import reference_gamut
    for name, bar in (("sRGB", 3.0), ("Adobe RGB (1998)", 1.5),
                      ("Display P3", 1.5)):
        share, worst = _how_far_the_seam_strays(
            paper, reference_gamut(name, steps=24))
        assert worst < bar, (
            f"against {name} the drawn seam strays {worst:.2f} Lab from where "
            f"the two shapes actually cross ({share:.1f}% of its length). "
            f"Unsharpened it was 14.64 Lab and 29.8% against sRGB.")


def test_the_fault_is_real_without_the_sharpening(paper, monkeypatch):
    """So this file cannot pass on a cut that never had the fault."""
    import gamutview
    from references import reference_gamut
    monkeypatch.setattr(gamutview, "sharpen_where_they_part",
                        lambda v, f, c, s, o, **k: (v, f, c, s))
    share, worst = _how_far_the_seam_strays(paper,
                                            reference_gamut("sRGB", steps=24))
    assert worst > 5.0, (
        f"without sharpening the seam is already within {worst:.2f} Lab — "
        f"something else now fixes it, and the test above proves nothing")


def test_it_is_not_the_other_shapes_resolution(paper):
    """The old seam was identical at every reference resolution.

    One corner per crossed edge of THIS mesh, and no more — which is why
    adding triangles to the reference never helped, and why the cure had to be
    to cut THIS mesh finer.
    """
    import gamutview
    import ti3gamut
    from references import reference_gamut
    real = gamutview.sharpen_where_they_part
    gamutview.sharpen_where_they_part = lambda v, f, c, s, o, **k: (v, f, c, s)
    try:
        from gamutview import boundary_loops, weld_by_position
        seen = set()
        for steps in (12, 24, 48):
            out, _f, stands, _l = ti3gamut.recut_where_they_part(
                [("mine", paper), ("theirs", reference_gamut("sRGB", steps=steps))])
            cut = out[0][1]
            faces = np.asarray(cut.faces, int)
            keep = np.asarray(stands[0], bool)[faces].all(axis=1)
            _kept, welded, _w = weld_by_position(cut.vertices, faces[keep])
            seen.add(sum(len(loop) - 1 for loop in boundary_loops(welded)))
    finally:
        gamutview.sharpen_where_they_part = real
    # THE SEAM, not the tally of standing corners: that last does wobble by
    # one as a corner sitting almost exactly on the crossing flips side, which
    # says nothing about how the boundary is drawn.
    assert len(seen) == 1, (
        f"the unsharpened seam now varies with the reference's resolution "
        f"({sorted(seen)} corners) — the reasoning in this file no longer holds")


def test_it_carries_colours_in_either_form(paper):
    """The caller swallows every exception, so a raise here is INVISIBLE.

    `recut_where_they_part` wraps the whole cut in a bare `except Exception`
    and falls back to the shape's old mesh — deliberately, so an odd file
    cannot empty the picture. The cost is that anything which raises in here
    is not reported anywhere: the gradient seam simply comes back, silently,
    and looks like the fault this whole file exists to fix.

    `split_at_crossing` takes colours as "rgb(r,g,b)" strings as well as
    numbers — that is what the drawing library is handed, and `_mix_colour`
    exists for it. This used to call `np.asarray(colors, float)` on them and
    raise ValueError. Not reachable today, because every gamut the
    application builds carries numbers. That is exactly the kind of thing
    that stops being true without anybody noticing.
    """
    import ti3gamut
    from gamutview import sharpen_where_they_part
    from references import reference_gamut
    other = reference_gamut("sRGB", steps=24)
    skin = ti3gamut.surfaces_of([("o", other)])[0]
    outside = lambda points: ~skin.contains(np.atleast_2d(points))  # noqa: E731
    v = np.asarray(paper.vertices, float)
    f = np.asarray(paper.faces, int)
    stands = outside(v)
    numbers = np.asarray(paper.colors, float)
    strings = [f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
               for r, g, b in numbers]
    shapes = {}
    for name, colours in (("numbers", numbers), ("rgb() strings", strings)):
        out_v, out_f, out_c, _s = sharpen_where_they_part(
            v, f, colours, stands, outside)
        assert len(out_f) > len(f), (
            f"{name}: nothing was cut finer, so this proves nothing")
        assert out_c is not None and len(out_c) == len(out_v), (
            f"{name}: {len(out_c) if out_c is not None else 0} colours for "
            f"{len(out_v)} corners — they have come apart")
        shapes[name] = len(out_f)
    assert shapes["numbers"] == shapes["rgb() strings"], (
        f"the two forms of colour gave different meshes, {shapes} — the "
        f"colours are steering the geometry, which they must not")
    for text in strings[:5]:
        assert text.startswith("rgb("), "the fixture is not string colours"


def test_a_facet_cannot_be_sampled_with_no_points_inside_it(paper):
    """Fewer than three a side leaves the weight list EMPTY.

    It used to accept 1 or 2 and quietly do nothing at all in phase one,
    which reads exactly like a phase one that looked and found nothing.
    """
    import ti3gamut
    from gamutview import sharpen_where_they_part
    from references import reference_gamut
    skin = ti3gamut.surfaces_of([("o", reference_gamut("sRGB", steps=16))])[0]
    outside = lambda points: ~skin.contains(np.atleast_2d(points))  # noqa: E731
    v = np.asarray(paper.vertices, float)
    f = np.asarray(paper.faces, int)
    for few in (0, 1, 2):
        with pytest.raises(ValueError, match="at least 3"):
            sharpen_where_they_part(v, f, paper.colors, outside(v), outside,
                                    samples=few)
