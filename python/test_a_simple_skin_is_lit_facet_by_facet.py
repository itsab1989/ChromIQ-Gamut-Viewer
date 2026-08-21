""""Wrap it in a simple skin" looked scattered, and it was the shading.

REPORTED FROM THE WINDOW, of two papers drawn that way side by side: "this
one looks scattered". The picture showed long wedges radiating across the
surface with hard edges between them.

IT IS NOT THE SHAPE. A hull over unevenly spread measured points is full of
needles — triangles whose longest edge is many times their own width — and
smooth shading averages the normals of every facet meeting at a corner, so
that average is smeared along the needle. That smear is the streak. Measured
on Glossy-paper:

    follow the real edge     40 of 978 triangles are needles (4.1%),
                             worst edge ratio 21
    wrap it in a simple skin 151 of 414 are needles (36.5%),
                             worst edge ratio 714

Lit facet by facet the same hull comes out clean — photographed in the real
window before and after. Nothing about the shape, the volume or the colours
changes: this is how the light is worked out and nothing else.

WHY NOT EVERYWHERE. "Follow the real edge" has 4% needles and reads better
smooth: it is a surface that really is curved, and faceting a curved shape
would be drawing something the measurement does not say.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


def _needles(gamut):
    """Triangles whose longest edge is more than eight times their width."""
    v = np.asarray(gamut.vertices, float)
    f = np.asarray(gamut.faces, int)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    longest = np.maximum.reduce([np.linalg.norm(b - a, axis=1),
                                 np.linalg.norm(c - b, axis=1),
                                 np.linalg.norm(a - c, axis=1)])
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    width = 2 * area / np.maximum(longest, 1e-9)
    return int((longest / np.maximum(width, 1e-9) > 8).sum()), len(f)


@pytest.fixture(scope="module")
def shapes():
    import ti3gamut
    from gamutview import build_gamut
    paper = _DEMO / "Glossy-paper.ti3"
    if not paper.is_file():
        pytest.skip("no demo paper to measure")
    m = ti3gamut.read_measurement(paper)
    return (ti3gamut,
            build_gamut(m.lab, m.device, input_space="lab"),
            build_gamut(m.lab, None, input_space="lab"))


def test_the_skin_really_is_full_of_needles(shapes):
    # WITHOUT THIS THE RULE BELOW IS A PREFERENCE. Faceting is worth having
    # because this mesh cannot be shaded smoothly; a hull that came out
    # evenly triangulated would want the opposite.
    _ti3, real_edge, skin = shapes
    needles, faces = _needles(skin)
    assert needles > faces * 0.15, (
        f"only {needles} of {faces} triangles in the simple skin are needles "
        f"— the reason for lighting it facet by facet is not present in this "
        f"shape, so this rule is asserting a taste rather than a fix")
    even, _ = _needles(real_edge)
    assert even < _needles(real_edge)[1] * 0.10, (
        "following the real edge has become as needly as the hull, so the "
        "two should no longer be shaded differently")


def test_the_skin_is_lit_facet_by_facet(shapes):
    ti3, _real_edge, skin = shapes
    figure = ti3.build_figure([("Glossy-paper", skin)], "")
    meshes = [t for t in figure.data if t.type == "mesh3d"]
    assert meshes, "the simple skin drew no surface at all"
    assert all(t.flatshading for t in meshes), (
        "the simple skin is shaded smoothly again, which smears the light "
        "along every needle and is the streaking reported from the window")


def test_a_real_edge_stays_smooth(shapes):
    ti3, real_edge, _skin = shapes
    figure = ti3.build_figure([("Glossy-paper", real_edge)], "")
    meshes = [t for t in figure.data if t.type == "mesh3d"]
    assert meshes and not any(t.flatshading for t in meshes), (
        "a shape that follows the real edge is being faceted — that draws "
        "corners the measurement does not have")


# --------------------------------------------------------------------------
# AND THE SKIN OVER A CHART'S PATCHES, which is the same kind of surface in a
# different place and was missed when the shape's hull was fixed.
# --------------------------------------------------------------------------

def _chart_skin_mesh():
    import chart as cm
    import ti3gamut
    from gamutview import build_gamut
    chart_file = _DEMO / "verification-chart-480.ti1"
    profile = _DEMO / "Glossy-paper.icc"
    paper_file = _DEMO / "Matte-paper.ti3"
    for f in (chart_file, profile, paper_file):
        if not f.is_file():
            pytest.skip(f"no {f.name} to draw with")
    c = cm.read_chart(chart_file)
    lab = cm.through_profile(c, profile).under("D50")
    m = ti3gamut.read_measurement(paper_file)
    paper = build_gamut(m.lab, input_space="lab", space="lab",
                        white_point="D50")
    outside = cm.outside_report(lab, paper).beyond
    figure = ti3gamut.build_figure(
        [], "t", chart=("c", lab, outside, cm.device_positions(c)),
        chart_look=dict(skin="solid", skin_colour="grey", skin_opacity=0.30,
                        dot_size=3.2, dot_opacity=1.0, out_dot_size=4.0,
                        out_dot_opacity=1.0, show_outside=True,
                        show_inside=True, accent="#22d3aa"))
    meshes = [t for t in figure.data if t.type == "mesh3d"]
    assert meshes, "a solid skin over the patches drew no surface at all"
    return meshes[0]


def test_the_skin_over_a_chart_is_needly_too():
    # THE REASON, MEASURED, and without it the rule below is a preference.
    import numpy as np
    t = _chart_skin_mesh()
    v = np.stack([np.asarray(t.x, float), np.asarray(t.y, float),
                  np.asarray(t.z, float)], axis=1)
    f = np.stack([np.asarray(t.i, int), np.asarray(t.j, int),
                  np.asarray(t.k, int)], axis=1)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    longest = np.maximum.reduce([np.linalg.norm(b - a, axis=1),
                                 np.linalg.norm(c - b, axis=1),
                                 np.linalg.norm(a - c, axis=1)])
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    width = 2 * area / np.maximum(longest, 1e-9)
    needles = int((longest / np.maximum(width, 1e-9) > 8).sum())
    assert needles > len(f) * 0.15, (
        f"only {needles} of {len(f)} triangles in the chart's skin are "
        f"needles — the reason for lighting it facet by facet is not present "
        f"in this shape, so the rule below asserts a taste rather than a fix")


def test_the_skin_over_a_chart_is_lit_facet_by_facet():
    assert _chart_skin_mesh().flatshading, (
        "the skin over the patches is shaded smoothly again, which smears "
        "the light along every needle — the same streaking reported from the "
        "window of the shape's own simple skin")
