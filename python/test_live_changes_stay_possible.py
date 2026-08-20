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


def test_a_figure_reads_per_shape_by_its_own_position():
    """One shape in a figure always reads entry 0 of ``per_shape``.

    This is the contract that makes a room-per-shape view easy to get wrong,
    and it did: `_write_two_rooms` builds each room with ONE shape and used to
    hand it the whole list, so both rooms drew with the first shape's
    settings. Reported as "when enabling the two rooms the shapes on screen
    don't keep their visuals from before" -- and the giveaway was that turning
    it off restored them, which means they were never lost, only never handed
    over.

    Pinned here because the fix lives at the CALL SITE: whoever builds a
    figure holding a subset of the shapes has to hand over that subset's
    settings, and nothing in the renderer can notice if they do not.
    """
    import numpy as np

    from gamutview import build_gamut

    rng = np.random.default_rng(7)
    q = rng.normal(size=(500, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    lab = q * np.array([34, 44, 40])
    lab[:, 0] = np.clip(lab[:, 0] * 0.6 + 50, 6, 94)
    shape = build_gamut(lab)

    both = [{"opacity": 1.0}, {"opacity": 0.3}]
    fig = ti3gamut.build_figure([("only one", shape)], "", styles=["solid"],
                                per_shape=both)
    meshes = [t for t in fig.data if getattr(t, "i", None) is not None]
    assert meshes, "no surface was drawn, so nothing was checked"
    assert abs(meshes[0].opacity - 1.0) < 1e-6, (
        "a lone shape no longer reads entry 0 of per_shape; the two-room "
        "writer slices the list on that basis and would now hand over the "
        "wrong settings")

    only_the_second = [both[1]]
    fig = ti3gamut.build_figure([("only one", shape)], "", styles=["solid"],
                                per_shape=only_the_second)
    meshes = [t for t in fig.data if getattr(t, "i", None) is not None]
    assert abs(meshes[0].opacity - 0.3) < 1e-6, (
        "handing a figure just one shape's settings no longer works, which is "
        "exactly how each room is given its own")


def test_the_neutral_line_does_not_need_measured_greys():
    """A shape with no measured greys still shows where neutral runs.

    Asked from the window, of a profile: "i could understand why this can't
    show the measured grey from just a profile - but is a neutral line
    impossible as well here?" It is not. The line is a* 0, b* 0 by definition;
    the measured greys were only ever borrowed for their lightness range, and
    a shape that was never measured has a range of its own.

    This is also the second half of a decoupling that was only half done: the
    two ticks were separated in the window when Basti asked for them to be
    independent, while the drawing still refused to make the line without the
    greys.
    """
    import numpy as np

    from gamutview import build_gamut

    rng = np.random.default_rng(11)
    q = rng.normal(size=(500, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    lab = q * np.array([34, 44, 40])
    lab[:, 0] = np.clip(lab[:, 0] * 0.6 + 50, 6, 94)
    shape = build_gamut(lab)

    fig = ti3gamut.build_figure([("a profile", shape)], "", styles=["solid"],
                                neutrals=None, ideal_neutrals=True)
    lines = [t for t in fig.data
             if "perfectly neutral" in str(getattr(t, "name", ""))]
    assert lines, (
        "no neutral line was drawn for a shape without measured greys, so the "
        "tick is dead again for every profile")

    # AND IT KEEPS TO THE SHAPE'S OWN RANGE, which is the whole reason it is
    # not simply drawn from 0 to 100: a line running past a printer's black
    # and white invites the reading that it "failed" to reach them.
    zs = [v for v in lines[0].z if v is not None]
    lightness = np.asarray(shape.vertices)[:, 0]
    assert min(zs) >= lightness.min() - 1 and max(zs) <= lightness.max() + 1, (
        f"the neutral line runs {min(zs):.1f}–{max(zs):.1f} where the shape "
        f"reaches {lightness.min():.1f}–{lightness.max():.1f}")

    off = ti3gamut.build_figure([("a profile", shape)], "", styles=["solid"],
                                neutrals=None, ideal_neutrals=False)
    assert not [t for t in off.data
                if "perfectly neutral" in str(getattr(t, "name", ""))], (
        "a neutral line was drawn with its tick off")


def _blob(scale, seed=4, n=400):
    """A gamut of a given size in every direction, for nesting one in another."""
    import numpy as np

    from gamutview import build_gamut

    rng = np.random.default_rng(seed)
    q = rng.normal(size=(n, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    q *= rng.uniform(0.55, 1, size=(n, 1)) ** (1 / 3)
    lab = q * np.array(scale)
    lab[:, 0] = np.clip(lab[:, 0] * 0.6 + 52, 4, 96)
    return build_gamut(lab, input_space="lab")


def _ball(z_spread, seed=3):
    """A gamut as tall as *z_spread* in L*, and always wide in a*/b*."""
    import numpy as np

    from gamutview import build_gamut

    rng = np.random.default_rng(seed)
    q = rng.normal(size=(400, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    lab = q * np.array([z_spread, 46, 40])
    lab[:, 0] += 55
    return build_gamut(lab, input_space="lab")


def test_an_ordinary_gamut_keeps_the_library_s_own_proportions():
    """Nothing is imposed on a picture that already fits.

    The room is sized in Lab units on purpose -- that is why a wide gamut
    looks wide -- so the ceiling added for flat gamuts must not touch anything
    below it. Measured when it was written: a normal shape covered exactly the
    same pixels before and after, 53,544 of them.
    """
    fig = ti3gamut.build_figure([("a normal paper", _ball(30.0))], "")
    scene = fig.layout.scene
    assert scene.aspectmode == "data", (
        f"an ordinary gamut is no longer left to the library's own "
        f"proportions (aspectmode is {scene.aspectmode!r})")
    assert scene.aspectratio.x is None, (
        "a ratio was imposed on a picture that did not need one")


def test_a_flat_gamut_is_scaled_to_fit_its_picture():
    """A gamut with almost no lightness range must not spill over the edges.

    Measured by flattening a gamut step by step and looking at where the ink
    landed: a room whose longest side is 2.60 still fits, one at 3.27 is cut
    off at two edges with the axis titles pushed out of the picture. A chart
    covering only the midtones does this.
    """
    fig = ti3gamut.build_figure([("almost flat", _ball(1.5))], "")
    scene = fig.layout.scene
    assert scene.aspectmode == "manual", (
        "a flat gamut was left to size its own room, which overflows")
    sides = [scene.aspectratio.x, scene.aspectratio.y, scene.aspectratio.z]
    assert max(sides) <= ti3gamut.ROOM_CEILING + 1e-6, (
        f"the room is {max(sides):.2f} long, past the {ti3gamut.ROOM_CEILING} "
        f"that was measured to fit")

    # AND ITS PROPORTIONS ARE UNTOUCHED, which is the whole point: the sides
    # are divided by one number, so a wide gamut still looks wide.
    import numpy as np

    corners = np.asarray(_ball(1.5).vertices, float)
    real = np.array([corners[:, i].max() - corners[:, i].min()
                     for i in range(3)])
    # the drawn axes are (a*, b*, L*) where the shape's columns are (L*, a*, b*)
    real = np.array([real[1], real[2], real[0]])
    want = real / real.max()
    got = np.array(sides) / max(sides)
    assert np.allclose(got, want, atol=0.02), (
        f"the proportions were changed: drawn {got.round(3).tolist()} against "
        f"the shape's own {want.round(3).tolist()}")


def test_a_short_axis_gets_fewer_numbers_along_it():
    """A lopsided room must not write its labels on top of one another.

    Seen on two of the awkward shapes -- a gamut with one patch far out in a*,
    and one covering only the midtones -- where the L* numbers came out as a
    single unreadable blob down the left of the picture. The drawing library
    puts about as many ticks on every axis whatever its length on screen, so
    the short side of a lopsided room is where they collide.

    The labels are drawn inside the WebGL canvas, not as page text, so no
    selector can measure them and this asks the layout instead: the short side
    must be given fewer than the long one, and never fewer than three, which
    is the least that still says what an axis is.
    """
    import numpy as np

    from gamutview import build_gamut

    rng = np.random.default_rng(7)
    q = rng.normal(size=(400, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    lab = q * np.array([30, 40, 36])
    lab[:, 0] = np.clip(lab[:, 0] * 0.6 + 50, 5, 95)
    lab = np.vstack([lab, [[50.0, 120.0, 10.0]]])       # one patch far out
    fig = ti3gamut.build_figure(
        [("one patch far out", build_gamut(lab, input_space="lab"))], "")

    scene = fig.layout.scene
    along = {"x": scene.xaxis.nticks, "y": scene.yaxis.nticks,
             "z": scene.zaxis.nticks}
    assert all(n is not None for n in along.values()), (
        "no tick counts were asked for, so a short axis will crowd again")
    assert min(along.values()) >= 3, (
        f"an axis was left with {min(along.values())} numbers, which cannot "
        f"say what it is")
    assert along["z"] < along["x"], (
        f"the short side (L*, {along['z']}) was given as many numbers as the "
        f"long one (a*, {along['x']}), which is what made them collide")


def test_an_even_room_is_labelled_evenly():
    """And a shape that is not lopsided gets the same treatment on every side.

    The rule is about proportion, not about singling out an axis: an ordinary
    gamut is a little wider than it is tall, so its sides should differ by a
    little and no more.
    """
    fig = ti3gamut.build_figure([("a normal paper", _ball(30.0))], "")
    scene = fig.layout.scene
    along = [scene.xaxis.nticks, scene.yaxis.nticks, scene.zaxis.nticks]
    assert max(along) - min(along) <= 4, (
        f"an ordinary gamut's sides were labelled very differently: {along}")


def test_a_picture_emptied_by_the_fade_says_so():
    """An empty picture must not look like a broken one.

    Two identical measurements agree everywhere, so hiding what they agree on
    hides all of them and the page comes up showing nothing but its walls.
    That is the honest answer and it is indistinguishable from a fault. The
    tooltip explains it three scrolls away; the picture now says it itself,
    which is what this file already did for a drift cloud whose dots fall
    below the threshold.
    """
    same = [("one", _ball(30.0, seed=4)), ("the same again", _ball(30.0, seed=4))]
    fig = ti3gamut.build_figure(same, "Measured gamut",
                                styles=["solid", "solid"], agree=0.0,
                                split=True)
    said = fig.layout.title.text
    assert "nothing is left" in said, (
        f"an emptied picture said only {said!r}, which reads as a fault")

    # ONE SHAPE GONE IS NAMED, rather than lumped in with the rest: a shape
    # lying wholly inside the others disappears while the others stay.
    #
    # AND IT REALLY HAS TO BE INSIDE. Written first with two shapes that
    # differed only in lightness, they crossed in a*/b* and neither vanished
    # -- the fixture was wrong and the assertion looked like a fault in the
    # code.
    nested = [("the small one", _blob((16, 24, 20))),
              ("the big one", _blob((40, 58, 50)))]
    fig = ti3gamut.build_figure(nested, "Measured gamut",
                                styles=["solid", "solid"], agree=0.0,
                                split=True)
    said = fig.layout.title.text
    assert "the small one is not drawn" in said, (
        f"the shape that vanished was not named: {said!r}")

    # AND A PICTURE THAT IS FINE SAYS NOTHING, or the note becomes noise.
    fig = ti3gamut.build_figure(same, "Measured gamut",
                                styles=["solid", "solid"], split=True)
    assert fig.layout.title.text.strip() == "Measured gamut", (
        f"a picture with nothing missing still explained itself: "
        f"{fig.layout.title.text!r}")
