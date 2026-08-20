"""The assumptions the live controls rest on, pinned so they cannot drift.

WHY THIS EXISTS. Asked from the window: "whenever you made changes to the
viewer which were supposedly improvements - did you make tests around those to
ensure changes in the future don't cause regressions around behaviour that was
working before?"

For these two, the honest answer had been no. Both were measured once, by hand,
and then guarded by an audit SCRIPT -- and the audits are not run by `pytest`,
so a change could break either of them with both gates still green. These are
the invariants those features stand on, in the gate where they belong.

They are deliberately about the MECHANISM rather than the picture: a rendering
audit needs a browser and a window and takes minutes, while what actually
breaks silently is an assumption someone did not know was being relied on.
"""
from __future__ import annotations

import numpy as np

import ti3gamut


def test_rings_are_built_as_one_trace():
    """The live rings slider needs the rings to be ONE trace.

    `_on_rings_changed` sends new points into the picture already on screen by
    restyling a single trace, and that only works because `_rings` strings
    every cross-section into one line with gaps between them. Drawn as one
    trace per ring, changing the count would have to ADD and REMOVE traces,
    which a restyle cannot do: the slider would silently stop working while
    still looking wired up.

    ASKED OF THE SOURCE, not of a drawn shape. A fixture was tried first and
    was worse than nothing: `_rings` returned no traces at all for it, so the
    rule "not more than one trace" passed while proving nothing. What must not
    change is that ONE trace is built, and that is visible here and cannot be
    faked by a shape that happens not to slice.
    """
    import inspect

    body = inspect.getsource(ti3gamut._rings)
    built = body.count("go.Scatter3d(")
    assert built == 1, (
        f"_rings now builds {built} Scatter3d traces; the live rings slider "
        f"restyles exactly one and would silently stop working")
    assert "+ [None]" in body, (
        "the rings are no longer separated by gaps, so they would be drawn "
        "joined to one another -- and the live push assumes the gaps")


def test_a_fade_at_its_ends_drops_only_invisible_triangles():
    """The see-through fix must never take away a triangle that paints.

    `_solid_remainder` cures the fault where a solid remainder was drawn
    see-through, by removing the fully invisible triangles so the mesh stays
    on the opaque, depth-buffered path. The danger in that trade is obvious
    and was reported as "cut out triangles": if it ever drops a triangle with
    a visible corner, geometry the reader could see disappears.
    """
    # THE TWO HALVES MUST BE CLEANLY SEPARATED, which is what the re-cut
    # guarantees before this is ever called: a face with one faded corner and
    # two lit ones is not "at the ends" at all, and the guard refuses the
    # whole mesh rather than drop it. Written first with a straddling face,
    # this test asserted a drop that must not happen.
    faces = np.array([[0, 1, 2], [3, 4, 5]])
    colours = [f"rgb({i},{i},{i})" for i in range(6)]
    alphas = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    kept_colours, kept = ti3gamut._solid_remainder(colours, alphas, faces, 1.0)
    assert len(kept) == 1, f"dropped {2 - len(kept)} triangles, expected 1"
    for tri in kept:
        assert alphas[tri].max() > 0, (
            "a triangle with no visible corner survived, so the mesh is still "
            "on the transparent path")
    assert all(not str(c).startswith("rgba") for c in kept_colours), (
        "the colours kept an alpha, which puts the whole mesh back on the "
        "transparent path and undoes the fix")


def test_a_fade_in_the_middle_is_left_exactly_as_it_was():
    """Anything strictly between the ends must keep the old behaviour.

    The fix claims to touch only the extremes. If it ever fires on a partial
    fade it would remove triangles the reader is still meant to see faintly,
    which is the same fault in a subtler dress.
    """
    faces = np.array([[0, 1, 2], [1, 2, 3]])
    colours = ["rgb(1,1,1)", "rgb(2,2,2)", "rgb(3,3,3)", "rgb(4,4,4)"]

    for alphas in (np.array([0.0, 0.0, 0.0, 0.5]),      # a middling corner
                   np.array([0.0, 0.0, 0.0, 0.99]),     # nearly, not quite
                   np.array([0.0, 0.5, 1.0, 1.0])):     # a straddling face
        got_colours, got_faces = ti3gamut._solid_remainder(
            colours, alphas, faces, 1.0)
        assert len(got_faces) == len(faces), (
            f"triangles were dropped for a fade at {alphas.tolist()}, which "
            f"is not at its ends")
        assert any(str(c).startswith("rgba") for c in got_colours), (
            "the fade was not applied at all for a partial setting")


def test_a_shape_that_is_not_fully_solid_is_left_alone():
    """A shape at half strength is see-through on purpose.

    The fix is only right when the shape's own strength is 1; below that the
    reader has asked to see through it, and dropping its invisible triangles
    would change a picture they chose.
    """
    faces = np.array([[0, 1, 2], [1, 2, 3]])
    colours = ["rgb(1,1,1)", "rgb(2,2,2)", "rgb(3,3,3)", "rgb(4,4,4)"]
    alphas = np.array([0.0, 0.0, 0.0, 1.0])
    _got_colours, got_faces = ti3gamut._solid_remainder(
        colours, alphas, faces, 0.55)
    assert len(got_faces) == len(faces), (
        "triangles were dropped from a shape drawn at 55% strength")


def test_the_out_of_reach_edge_is_cut_not_stepped():
    """What is out of reach must end on a clean line, not a staircase.

    Reported from the window: "what is out of reach here should probably be a
    clean cut along the shell of srgb. instead it is zig zagging". The mark is
    per CORNER, so a triangle whose corners disagree has to be painted wholly
    red or wholly grey -- and on his own shapes 175 of 978 triangles (17.9% of
    the surface) were exactly that. The cure is the re-cut that the fade
    already used, which inserts corners along the crossing; it simply was not
    invoked when nothing was faded.

    This pins the RESULT rather than the branch: no drawn triangle may carry
    corners of both colours. Written against the branch it would pass on a
    re-cut that had stopped cutting.
    """
    import numpy as np

    from gamutview import build_gamut

    rng = np.random.default_rng(4)
    q = rng.normal(size=(900, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    q *= rng.uniform(0.55, 1, size=(900, 1)) ** (1 / 3)
    a = q * np.array([36, 58, 34])
    a[:, 0] = np.clip(a[:, 0] * 0.6 + 52, 5, 95)
    b = q * np.array([40, 34, 60])
    b[:, 0] = np.clip(b[:, 0] * 0.62 + 50, 3, 97)
    pair = [("a paper", build_gamut(a)), ("a reference", build_gamut(b))]

    skins = ti3gamut.surfaces_of(pair)
    beyond = np.asarray(ti3gamut.disagreeing_vertices(pair, skins)[0], bool)
    assert 0.05 < beyond.mean() < 0.95, (
        "these two shapes do not cross, so there is no boundary to be ragged "
        "and this test would pass on anything")

    fig = ti3gamut.build_figure(pair, "", styles=["solid", "mesh"],
                                lost=[beyond, None])
    checked = 0
    for trace in fig.data:
        colours = list(getattr(trace, "vertexcolor", []) or [])
        if not colours or getattr(trace, "i", None) is None:
            continue
        red = np.array([str(c) == str(ti3gamut._LOST) for c in colours])
        if not red.any():
            continue
        faces = np.column_stack([list(trace.i), list(trace.j), list(trace.k)])
        per = red[faces]
        stepped = int((per.any(axis=1) & ~per.all(axis=1)).sum())
        assert stepped == 0, (
            f"{stepped} of {len(faces)} drawn triangles carry corners of both "
            f"colours, so the out-of-reach edge is a staircase again")
        checked += 1
    assert checked, "no marked mesh was drawn, so nothing was actually checked"
