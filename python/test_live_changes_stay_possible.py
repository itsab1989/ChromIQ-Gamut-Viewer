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
