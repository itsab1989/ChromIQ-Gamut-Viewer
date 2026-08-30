"""Standard colour spaces to compare a printer against — and any ICC profile.

Two sources of a reference gamut:

* **Built in** — sRGB, Adobe RGB (1998), Display P3, ProPhoto RGB and Rec.2020
  are defined by their primaries and white point, so they need no files and no
  dependencies. ``reference_gamut("sRGB")`` is exact by construction.
* **Any ICC profile** — ``icc_gamut(path)`` reads a real ``.icc``/``.icm`` and
  builds its gamut, so a paper can be compared against the profile a client
  actually sent.

WHY A REFERENCE IS NOT THE SAME AS ANOTHER PAPER
------------------------------------------------
Comparing two measured papers asks "which of these two can I print on".
Comparing against sRGB asks something else: "will the images people send me
survive on this paper". Both are useful and they are not interchangeable, so
the viewer labels which kind each gamut is.

COLOUR SCIENCE
--------------
An RGB working space is a cube in its own coordinates, so its gamut is built
exactly the way a printer's mode-2 gamut is: the six faces of that cube, mapped
through the space's own primaries into XYZ and then Lab. That keeps the two
comparable — the same construction on both sides.

Working spaces are defined against **D65** (ProPhoto against D50). Comparing
one to a print measured under D50 needs a chromatic adaptation, which is done
with Bradford rather than by pretending the whites are the same.
"""
from __future__ import annotations

import pathlib
import subprocess

import numpy as np

from gamutview import (WHITE_POINTS, _bradford_adapt, _as_white_point,
                       build_gamut, xyz_to_lab)

__all__ = ["REFERENCE_SPACES", "reference_gamut", "icc_gamut",
           "gam_gamut"]

#: name -> (red xy, green xy, blue xy, white point, encoding gamma)
#: Primaries from each space's own definition; gamma only affects how the cube
#: is sampled, never the boundary, which is why an approximate gamma is safe.
REFERENCE_SPACES: dict[str, dict] = {
    "sRGB": dict(primaries=((0.6400, 0.3300), (0.3000, 0.6000), (0.1500, 0.0600)),
                 white="D65", gamma=2.2,
                 note="What most images and most screens assume."),
    "Adobe RGB (1998)": dict(
        primaries=((0.6400, 0.3300), (0.2100, 0.7100), (0.1500, 0.0600)),
        white="D65", gamma=2.2,
        note="Wider in the greens than sRGB; common in photography."),
    "Display P3": dict(
        primaries=((0.6800, 0.3200), (0.2650, 0.6900), (0.1500, 0.0600)),
        white="D65", gamma=2.2,
        note="What recent Apple screens show."),
    "ProPhoto RGB": dict(
        primaries=((0.734699, 0.265301), (0.159597, 0.840403), (0.036598, 0.000105)),
        white="D50", gamma=1.8,
        note="Very wide — parts of it are not visible colours at all."),
    "Rec.2020": dict(
        primaries=((0.7080, 0.2920), (0.1700, 0.7970), (0.1310, 0.0460)),
        white="D65", gamma=2.4,
        note="The ultra-HD television space."),
}


def _rgb_to_xyz_matrix(primaries, white) -> np.ndarray:
    """The 3x3 that takes linear RGB to XYZ for these primaries and white."""
    wp = _as_white_point(white)
    xy = np.asarray(primaries, dtype=float)
    # Each primary as XYZ at unit luminance.
    m = np.array([[x / y, 1.0, (1.0 - x - y) / y] for x, y in xy]).T
    scale = np.linalg.solve(m, wp)          # so R=G=B=1 gives the white point
    return m * scale


def reference_gamut(name: str, *, white_point: str = "D50", steps: int = 20,
                    space: str = "lab"):
    """The gamut of a standard RGB working space, in *space* under
    *white_point*.

    Built as the six faces of its own RGB cube — the same construction used for
    a printer's measured gamut — so the two are directly comparable rather than
    one being a hull and the other a boundary.

    *steps* is how finely each cube face is sampled. The default of 20 is where
    the volume stops changing: measured on sRGB, 8 steps under-states it by
    0.5% and looks visibly faceted, 20 is within 0.04% of a 32-step build, and
    every one of them takes hundredths of a second. Coarser is not faster in
    any way anybody would notice; it is only wrong and ugly.
    """
    try:
        spec = REFERENCE_SPACES[name]
    except KeyError:
        raise ValueError(
            f"unknown space {name!r}; known: {', '.join(REFERENCE_SPACES)}"
        ) from None
    if steps < 3:
        raise ValueError("steps must be at least 3 to describe a cube face")

    g = np.linspace(0.0, 1.0, steps)
    r, gg, b = np.meshgrid(g, g, g, indexing="ij")
    rgb = np.stack([r.ravel(), gg.ravel(), b.ravel()], axis=-1)
    linear = rgb ** spec["gamma"]
    xyz = linear @ _rgb_to_xyz_matrix(spec["primaries"], spec["white"]).T

    # The space's own white is not necessarily the one we are plotting under.
    src, dst = _as_white_point(spec["white"]), _as_white_point(white_point)
    if not np.allclose(src, dst):
        xyz = xyz @ _bradford_adapt(src, dst).T

    return build_gamut(xyz, rgb, input_space="xyz", space=space,
                       white_point=white_point)


def gam_gamut(path, *, white_point: str = "D50", space: str = "lab",
              stop=None):
    """A gamut straight out of an ArgyllCMS ``.gam`` file.

    *stop* is accepted and ignored ON PURPOSE, so that the two readers the
    window chooses between take the same arguments. This one runs no other
    program: it reads a finished surface out of a file, which is quick and
    has nothing to interrupt. Making the caller remember which of the two can
    be stopped is how a call site comes to pass it to the wrong one.

    ``iccgamut``, ``tiffgamut`` and ChromIQ itself all write these, and
    ``viewgam`` reads them — so anybody working with ArgyllCMS already has
    them lying around. They hold the finished surface, vertices and triangles
    both, which is exactly what this needs: no tool has to be run and nothing
    is recomputed.
    """
    path = pathlib.Path(path)
    if not path.is_file():
        raise ValueError(f"no such gamut file: {path}")
    try:
        verts, faces = _read_gam(path)
    except Exception as exc:      # noqa: BLE001 — say what, not how
        raise ValueError(
            f"{path.name} could not be read as an ArgyllCMS gamut file: "
            f"{exc}") from exc
    if len(verts) < 4:
        raise ValueError(f"{path.name} describes no usable volume")
    from gamutview import (Gamut, face_the_same_way, lab_to_xyz, mesh_volume,
                           xyz_to_srgb)
    # The file always holds Lab. Drawing in another space moves every
    # vertex, and the volume has to be recomputed there -- a number carried
    # over from Lab would be in the wrong units for the picture beside it.
    xyz = lab_to_xyz(verts, white_point)
    if space != "lab":
        from gamutview import _FROM_XYZ
        verts = _FROM_XYZ[space](xyz, white_point)
    # Wound one way before it leaves, for the reason in `build_gamut`: the
    # page's far-wall sort reads each triangle's cross product, and a mesh
    # that disagrees with itself puts half its faces in the wrong group.
    faces = face_the_same_way(faces, verts)
    return Gamut(vertices=verts, faces=faces,
                 colors=xyz_to_srgb(xyz, white_point),
                 # The volume the file's OWN triangles enclose. Measuring the
                 # convex hull of its vertices instead over-stated a real
                 # profile gamut by 8.3% and disagreed with what iccgamut
                 # reports for the same file -- a dented surface is exactly
                 # what these files describe.
                 volume=float(mesh_volume(verts, faces)),
                 space=space, mode="argyll-gam")


#: How finely ``iccgamut`` is asked to follow the profile's surface, its -d.
#:
#: NOT ASKED AT ALL UNTIL NOW, so Argyll's own default decided, and that
#: default is the outlier. This application has TWO ways of reading one
#: profile -- iccgamut, and the direct reader below it, used when ArgyllCMS
#: is missing or refuses -- and they should give the same answer for the same
#: file. Measured on five profiles, as the gap between the two readers'
#: volumes:
#:
#:     -d          default      8        6        4
#:     disagree      0.73%   0.19%    0.03%    0.16%
#:     per profile   0.15s   0.36s    0.71s    3.16s
#:
#: 6 is where the two doors into the same profile agree exactly, and 4
#: overshoots the other way.
#:
#: AND IT COSTS NOTHING TO TURN, which took two measurements to establish
#: because the first one was of the wrong thing. Timing twenty FORCED passes
#: back to back said 6 was over a frame's budget and 8 was not, and 8 shipped
#: on the strength of it. But the application never does that: the engine
#: skips a pass when the camera has barely turned, spaces itself out to three
#: times its own cost, stops when the picture settles, and never touches a
#: solid surface at all.
#:
#: Dragged for real instead -- mouse events at the canvas, so the scene's own
#: handler turns the camera the way a hand does, three seconds each:
#:
#:     -d   triangles   median    90th    worst   frames over 16.7 ms
#:     10       3,666   16.9ms  23.1ms   27.6ms   99 of 179
#:      8       5,958   16.5ms  26.2ms   69.5ms   81 of 178
#:      6       8,876   16.0ms  29.4ms   57.6ms   77 of 172
#:      4      18,180   16.1ms  38.1ms   66.9ms   64 of 173
#:
#: FIVE TIMES THE TRIANGLES DOES NOT SLOW THE DRAG. The count over budget
#: goes the other way, and Argyll's own default has the most of them. So the
#: triangle count is not what governs a drag, and there is nothing to trade:
#: 6 is both the most accurate and no dearer to turn.
#:
#: SOLID COSTS NOTHING AT ALL -- measured, 0.0 ms per pass, because a solid
#: surface hides its own far side and the engine leaves it alone.
#:
#: IT IS ALSO WHAT THE SHAPE LOOKS LIKE. The facets a reader can see at the
#: outline are 4.50 degrees across at the default and 2.91 at 6, measured as
#: the angle a face covers seen from the middle of the shape. Reported from
#: the window: "at the edges of the shape there still seem to be hints of
#: triangles instead of a smooth surface".
#:
#: WHAT IT COSTS is half a second per profile, once, and the result is kept:
#: shapes are cached on the file and the time it was written.
SURFACE_DETAIL = 6

#: How long to let ``iccgamut`` work before reading the profile here instead.
#:
#: SET FROM MEASUREMENT, not from caution. Timed on this machine over seven
#: real profiles -- the demo printer profile and six the operating system
#: ships, covering both cLUT and matrix kinds:
#:
#:     Glossy-paper.icc   A2B0,A2B1   0.15s
#:     AdobeRGB1998.icc   matrix      0.22s      <- the slowest of them
#:     ACESCG Linear.icc  matrix      0.14s
#:     Generic CMYK       A2B0,A2B1   0.09s
#:     Display P3, DCI-P3, Generic Gray -- declined in 0.00s, exit 1
#:
#: So ordinary work costs about a fifth of a second, and this leaves more than
#: a hundred times that. It was 180 seconds, which is not patience but a
#: three-minute frozen window: `icc_gamut` is called on the UI thread, and a
#: profile ArgyllCMS cannot finish reading -- they exist, measured, still
#: running after four minutes on a 344-byte file -- took the whole application
#: with it, with no message and no way to cancel.
#:
#: Not zero risk: a very large N-channel profile on a slow machine will cost
#: more than the ones timed here. That is what the fall-back is for, and the
#: fall-back reads the profile properly rather than failing.
ICCGAMUT_PATIENCE = 30


def _find_iccgamut() -> "str | None":
    """Where ArgyllCMS keeps iccgamut. See ``argyll.find_tool``."""
    from argyll import find_tool
    return find_tool("iccgamut")


def _read_gam(path) -> "tuple[np.ndarray, np.ndarray]":
    """Vertices and triangles from an ArgyllCMS ``.gam`` surface file.

    A ``.gam`` is CGATS text with two tables: the Lab position of every vertex,
    then the three vertex numbers of every triangle. Both are read here rather
    than only the vertices, because the triangles are what make the surface
    follow the profile's real, dented boundary instead of a hull thrown over
    the points.
    """
    text = pathlib.Path(path).read_text(errors="replace")
    blocks = []
    rest = text
    while "BEGIN_DATA_FORMAT" in rest:
        head, rest = rest.split("BEGIN_DATA_FORMAT", 1)
        fmt, rest = rest.split("END_DATA_FORMAT", 1)
        body, rest = rest.split("BEGIN_DATA", 1)[1].split("END_DATA", 1)
        blocks.append((fmt.split(), [l.split() for l in body.strip().splitlines()
                                     if l.strip()]))
    if len(blocks) < 2:
        raise ValueError("this .gam file has no vertex and triangle tables")
    (vfmt, vrows), (ffmt, frows) = blocks[0], blocks[1]
    li, ai, bi = (vfmt.index("LAB_L"), vfmt.index("LAB_A"), vfmt.index("LAB_B"))
    verts = np.array([[float(r[li]), float(r[ai]), float(r[bi])] for r in vrows])
    faces = np.array([[int(r[0]), int(r[1]), int(r[2])] for r in frows], dtype=int)
    return verts, faces


class Stopped(Exception):
    """Raised when the caller asked for a reading to be abandoned."""


def _run_stoppably(command, *, patience: float, stop=None, poll: float = 0.05):
    """`subprocess.run`, except that somebody can change their mind.

    WHY NOT subprocess.run. It takes a timeout and nothing else: once it is
    waiting, the only way out is for the timeout to expire. That is fine for a
    script and wrong for a window, where the person who started this is
    sitting in front of a Stop button.

    *stop* is a ``threading.Event``. When it is set, the tool is asked to end
    and then made to, and ``Stopped`` is raised — the caller wanted out, not
    an answer.

    THE TWO-STEP KILL IS DELIBERATE. `terminate` lets a well-behaved tool
    close the file it is writing; `kill` is for one that is wedged, which is
    the case this exists for. Half a second between them is long enough for
    the polite ending and short enough that nobody notices the difference.

    Returns the same CompletedProcess `subprocess.run` would, and raises the
    same TimeoutExpired, so every caller downstream is unchanged.
    """
    import time

    started = time.monotonic()
    with subprocess.Popen(command, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True) as running:
        while True:
            try:
                out, err = running.communicate(timeout=poll)
                return subprocess.CompletedProcess(
                    command, running.returncode, out, err)
            except subprocess.TimeoutExpired:
                pass
            if stop is not None and stop.is_set():
                running.terminate()
                try:
                    running.communicate(timeout=0.5)
                except subprocess.TimeoutExpired:
                    running.kill()
                    running.communicate()
                raise Stopped("asked to stop while reading the profile")
            if time.monotonic() - started > patience:
                running.kill()
                out, err = running.communicate()
                raise subprocess.TimeoutExpired(command, patience,
                                                output=out, stderr=err)


class IntentNotAvailable(ValueError):
    """Asked for an intent this profile cannot be read for.

    ⚠ ITS OWN CLASS, because catching plain ValueError to let this one out
    also let `build_gamut`'s out -- so a greyscale or device-link profile
    stopped saying "device-link and abstract profiles do not describe a
    gamut" and said "the gamut encloses no volume" instead, which tells the
    reader nothing about what they opened.
    """


#: What `iccgamut -i` calls each intent, in the words a reader would use.
_INTENT_WORDS = {"r": "relative colorimetric", "p": "perceptual",
                 "s": "saturation", "a": "absolute colorimetric"}


def icc_gamut(path, *, white_point: str = "D50", intent: str = "r",
              space: str = "lab", stop=None, **_ignored):
    """The gamut of any ICC profile, computed by ArgyllCMS itself.

    Asks ``iccgamut`` — the same tool ChromIQ uses — rather than pushing a grid
    through the profile here. That matters for accuracy: an eight-bit Lab
    round-trip clips a* and b* at ±128, which on a real printer profile
    inflated the answer roughly sevenfold. ArgyllCMS returns the surface it
    computed, in full precision, with its triangles, so the shape has the
    profile's real dents in it.

    *intent* is passed to ``iccgamut -i``: "r" relative colorimetric (the
    default, and the right one for "what can this profile actually reach"),
    "a" absolute, "p" perceptual, "s" saturation. The surface resolution is
    ``-d SURFACE_DETAIL``; see there for why it is asked for rather than
    left to Argyll.

    The profile is copied to a temporary folder first, because ``iccgamut``
    writes its result beside its input and nothing should appear uninvited in
    somebody's project folder.
    """
    import shutil
    import subprocess
    import tempfile

    path = pathlib.Path(path)
    if not path.is_file():
        raise ValueError(f"no such profile: {path}")

    # ⚠ AN ARGUMENT THAT IS ACCEPTED AND THEN IGNORED IS WORSE THAN ONE THAT
    # IS REFUSED. `intent` reaches ArgyllCMS below as `iccgamut -i`, but every
    # fallback in this function calls `profile_gamut`, which has no intent at
    # all and always answers relative colorimetric. So on a machine without
    # ArgyllCMS, or on a v4 profile Argyll declines to open -- Display P3,
    # Rec. 2020 and a good many paper makers' output profiles -- a caller
    # asking for perceptual or saturation was quietly handed the colorimetric
    # surface and no word about it. Found by a challenge of a feature that was
    # going to be built on top of this.
    #
    # Refusing is right rather than cautious: a plausible wrong surface is
    # this project's worst failure mode, and the default path ("r") is
    # untouched, so nothing that works today changes.
    def _cannot_honour(intent_asked: str, why: str) -> "IntentNotAvailable":
        return IntentNotAvailable(
            f"{path.name} can be read, but not for the "
            f"{_INTENT_WORDS.get(intent_asked, intent_asked)} intent.\n\n"
            f"{why}, and the reader used instead always answers relative "
            f"colorimetric — so the shape you would get back would not be "
            f"the one you asked for.\n\nInstalling ArgyllCMS gives this "
            f"profile its other intents; without it, relative colorimetric "
            f"is the one that can be shown.")

    tool = _find_iccgamut()
    if tool is None:
        # NO ARGYLLCMS IS NOT A REASON TO REFUSE A FILE WE CAN READ.
        #
        # This used to raise, and told the reader to go and install
        # ArgyllCMS. That was upside down in three ways at once. The direct
        # reader below opens the same profile in milliseconds; it is ALREADY
        # what happens when ArgyllCMS is present and wedges, and when it is
        # present and refuses (a v4 profile, which Display P3, Rec. 709 and
        # Rec. 2020 all are on macOS) -- so the one case that was turned away
        # was the simplest one of the three. And the README has said all
        # along that ArgyllCMS is usually not needed because profiles are
        # read directly, which was true of every path except this one.
        #
        # Basti found it by asking the right question: "you mentioned icc
        # profiles that argyll does not like -- is there a fallback so those
        # can be used anyway?" There was, for the profiles Argyll dislikes,
        # and not for the people who do not have Argyll at all.
        #
        # WHAT IT COSTS, measured on demo/Glossy-paper.icc: ArgyllCMS says
        # the volume is 818,514 and the direct reader 824,706, which is 0.76%
        # apart. ArgyllCMS is still asked first wherever it exists, because
        # it returns its own surface with the profile's real dents in it.
        #
        # AND A FILE THAT IS NOT A PROFILE STILL HAS TO SAY SO IN WORDS. The
        # first version of this returned the direct reader's answer and let
        # its own exception out -- so on a machine with no ArgyllCMS, opening
        # a text file renamed .icc raised UnsupportedProfile instead of the
        # sentence every other path here produces. Caught by CI, not by the
        # local run: this machine HAS ArgyllCMS, so the only branch that
        # exercises this line locally is a test that hands it a good profile.
        # The happy path of a new fallback is the half that gets written.
        from icc_read import profile_gamut
        if intent != "r":
            raise _cannot_honour(intent, "ArgyllCMS is not installed")
        try:
            return profile_gamut(path, white_point=white_point, space=space)
        except Exception as mine:                        # noqa: BLE001
            raise ValueError(
                f"{path.name} could not be read.\n\nArgyllCMS is not "
                f"installed, so it was read directly instead, and that did "
                f"not work either: {mine}\n\nIf this really is an ICC "
                f"profile, installing ArgyllCMS gives it a second way in — "
                f"it understands some profiles this reader does not."
            ) from mine

    with tempfile.TemporaryDirectory(prefix="iccgamut-") as tmp:
        work = pathlib.Path(tmp) / path.name
        # CONTENTS ONLY. copy2 also copies permissions, flags and extended
        # attributes, and the operating system refuses that for its own
        # protected files -- which is where the profiles people most want to
        # compare against live, so the obvious folder to browse to was the one
        # that failed. Nothing here needs the metadata; only the bytes.
        shutil.copyfile(path, work)
        try:
            done = _run_stoppably(
                [tool, "-i", intent, "-d", str(SURFACE_DETAIL), str(work)],
                patience=ICCGAMUT_PATIENCE, stop=stop)
        except subprocess.TimeoutExpired as exc:
            # FALL BACK RATHER THAN GIVE UP. This used to raise, which meant a
            # profile ArgyllCMS could not finish reading did not open AT ALL --
            # even though the reader in this very application opens it in
            # milliseconds, and does exactly that on any machine without
            # ArgyllCMS installed. Refusing a file we can read, because a
            # helper we did not need got stuck, is the wrong way round.
            from icc_read import profile_gamut
            if intent != "r":
                raise _cannot_honour(
                    intent, "ArgyllCMS gave up on this profile") from exc
            try:
                return profile_gamut(path, white_point=white_point, space=space)
            except Exception as mine:                    # noqa: BLE001
                raise ValueError(
                    f"{path.name} could not be read.\n\nArgyllCMS was still "
                    f"working on it after {ICCGAMUT_PATIENCE} seconds and was "
                    f"given up on, and reading it directly did not work "
                    f"either: {mine}") from exc
        gam = work.with_suffix(".gam")
        if done.returncode != 0 or not gam.is_file():
            # ARGYLL COULD NOT OPEN IT. Version 4 profiles are the common
            # case -- its library understands v2 thoroughly and v4 only in
            # part -- and those are ordinary files: Display P3, Rec. 709 and
            # Rec. 2020 all ship with macOS as v4, and paper makers hand out
            # v4 output profiles. Reading it here is a fair second try, and
            # it is checked against Argyll on every profile both can open.
            try:
                from icc_read import profile_gamut
                if intent != "r":
                    raise _cannot_honour(
                        intent, "ArgyllCMS could not open this profile")
                return profile_gamut(path, white_point=white_point, space=space)
            except IntentNotAvailable:
                raise
            except Exception as mine:                    # noqa: BLE001
                second = f"\n\nReading it directly did not work either: {mine}"
            detail = (done.stderr or done.stdout or "").strip().splitlines()
            why = detail[-1] if detail else f"exit code {done.returncode}"
            raise ValueError(
                f"{path.name} could not be read as a colour profile: "
                f"{why}.\n\nDevice-link and abstract profiles do not describe "
                f"a gamut, so there is nothing to draw for them.{second}")
        verts, faces = _read_gam(gam)

    if len(verts) < 4:
        raise ValueError(f"{path.name} describes no usable volume")
    from gamutview import (Gamut, face_the_same_way, lab_to_xyz, mesh_volume,
                           xyz_to_srgb)
    # The file always holds Lab. Drawing in another space moves every
    # vertex, and the volume has to be recomputed there -- a number carried
    # over from Lab would be in the wrong units for the picture beside it.
    xyz = lab_to_xyz(verts, white_point)
    if space != "lab":
        from gamutview import _FROM_XYZ
        verts = _FROM_XYZ[space](xyz, white_point)
    # Wound one way before it leaves, for the reason in `build_gamut`: the
    # page's far-wall sort reads each triangle's cross product, and a mesh
    # that disagrees with itself puts half its faces in the wrong group.
    faces = face_the_same_way(faces, verts)
    return Gamut(vertices=verts, faces=faces,
                 colors=xyz_to_srgb(xyz, white_point),
                 # The volume the file's OWN triangles enclose. Measuring the
                 # convex hull of its vertices instead over-stated a real
                 # profile gamut by 8.3% and disagreed with what iccgamut
                 # reports for the same file -- a dented surface is exactly
                 # what these files describe.
                 volume=float(mesh_volume(verts, faces)),
                 space=space, mode="icc-profile")
