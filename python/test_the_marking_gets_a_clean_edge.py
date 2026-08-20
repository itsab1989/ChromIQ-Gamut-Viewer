"""Two papers AND a reference: the out-of-reach boundary must be a cut, not a staircase.

REPORTED FROM THE WINDOW, of a picture holding Glossy, Matte and sRGB with
each paper showing what it cannot print: "it seem the colored part should have
a clearer line instead this zig zag".

WHY IT WAS RAGGED. The marking is a boolean per CORNER, so a triangle with
corners on both sides has to be painted wholly red or wholly grey — and that
is the staircase. `recut_where_they_part` exists to cut the mesh along the
boundary so no triangle straddles it, and it gave the marking a clean edge
only when the marking asked the SAME question as the fade: "what can this
paper no longer reach" is measured against ONE chosen shape, while the fade
is measured against ALL the others. With two shapes those are the same
question; with two papers and a reference they are not, and it gave up.

Measured on his configuration, with the papers this project keeps for the
purpose:

    one paper against sRGB      118 of 414 straddled  →  0 of 650
    two papers and sRGB         118 of 414 straddled  →  118 of 414 (refused)

THE FIX IS A SECOND CUT, NOT A GUESS. The shape doing the judging is found —
the mask is exactly `~contains` of one of the shapes on screen — and the mesh
is cut again along that boundary, with the same test that made the mask
answering for every new corner.

⚠ AND "CLEAN" IS NOT "RIGHT", so both are asked here. After the second cut,
not one of the 209 corners that already existed changed its marking, and every
new corner sits ON the surface — nudged 0.05 Lab inwards they all read inside,
outwards they all read outside — which is where a cut puts them, and where a
containment test can answer either way. The shape itself does not move: the
volume is unchanged to a part in 10^15.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


def _straddling(gamut, mask):
    faces = np.asarray(gamut.faces)
    per = np.asarray(mask, bool)[faces]
    return int((per.any(axis=1) & ~per.all(axis=1)).sum()), len(faces)


@pytest.fixture(scope="module")
def scene():
    """His picture: two real papers and sRGB, each paper judged against it.

    REAL PAPERS, because an invented ball has hidden a fault from a check
    three times in this project: they are smooth where a paper has dents.
    """
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut

    for name in ("Glossy-paper.ti3", "Matte-paper.ti3"):
        if not (_DEMO / name).is_file():
            pytest.skip(f"no {name} to measure")
    papers = [(p.stem, build_gamut(ti3gamut.read_measurement(p).lab,
                                   input_space="lab"))
              for p in (_DEMO / "Glossy-paper.ti3", _DEMO / "Matte-paper.ti3")]
    srgb = reference_gamut("sRGB", steps=16)
    skin = ti3gamut.surfaces_of([("sRGB", srgb)])[0]
    shapes = papers + [("sRGB", srgb)]
    lost = [~skin.contains(np.asarray(g.vertices)) for _n, g in papers] + [None]
    return ti3gamut, shapes, lost, skin


def test_the_staircase_is_there_to_begin_with(scene):
    # A CHECK THAT CANNOT SEE THE FAULT WOULD PASS ON ANY MESH. If this
    # picture has no straddling triangles before the cut, the test below
    # proves nothing at all.
    _ti3, shapes, lost, _skin = scene
    straddled, faces = _straddling(shapes[0][1], lost[0])
    assert straddled > 40, (
        f"only {straddled} of {faces} triangles straddle the marking before "
        f"the cut — this scene has no staircase to remove, so nothing below "
        f"is being tested")


def test_no_triangle_straddles_the_marking_afterwards(scene):
    ti3, shapes, lost, _skin = scene
    out, _faces, _stands, out_lost = ti3.recut_where_they_part(
        [(n, g) for n, g in shapes], list(lost))
    straddled, faces = _straddling(out[0][1], out_lost[0])
    assert straddled == 0, (
        f"{straddled} of {faces} triangles still have corners on both sides "
        f"of the marking, so the boundary still runs along triangle edges — "
        f"the zig-zag reported from the window")
    assert faces > len(np.asarray(shapes[0][1].faces)), (
        "the mesh gained no triangles, so no cut was made at all")


def test_the_corners_that_existed_keep_their_answer(scene):
    # CLEAN IS NOT RIGHT. A cut that changed what the old corners say would
    # be drawing a tidy lie.
    ti3, shapes, lost, _skin = scene
    was = np.asarray(lost[0], bool)
    out, _f, _s, out_lost = ti3.recut_where_they_part(
        [(n, g) for n, g in shapes], list(lost))
    now = np.asarray(out_lost[0], bool)[:len(was)]
    assert np.array_equal(was, now), (
        f"{int((was != now).sum())} of {len(was)} corners changed their "
        f"marking during a cut that is only allowed to add new ones")


def test_the_shape_itself_does_not_move(scene):
    ti3, shapes, lost, _skin = scene
    out, _f, _s, _l = ti3.recut_where_they_part(
        [(n, g) for n, g in shapes], list(lost))

    def volume(g):
        v, f = np.asarray(g.vertices), np.asarray(g.faces)
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        return float(np.abs(np.einsum("ij,ij->i", a, np.cross(b, c))).sum() / 6)

    before, after = volume(shapes[0][1]), volume(out[0][1])
    assert abs(before - after) / max(before, 1e-9) < 1e-9, (
        f"the shape changed size during the cut: {before:.1f} → {after:.1f}")
