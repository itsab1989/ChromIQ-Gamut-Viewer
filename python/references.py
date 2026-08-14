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


def reference_gamut(name: str, *, white_point: str = "D50", steps: int = 20):
    """The gamut of a standard RGB working space, in Lab under *white_point*.

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

    return build_gamut(xyz_to_lab(xyz, white_point), rgb, input_space="lab",
                       white_point=white_point)


def gam_gamut(path, *, white_point: str = "D50"):
    """A gamut straight out of an ArgyllCMS ``.gam`` file.

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
    from scipy.spatial import ConvexHull

    from gamutview import Gamut, lab_to_xyz, xyz_to_srgb
    return Gamut(vertices=verts, faces=faces,
                 colors=xyz_to_srgb(lab_to_xyz(verts, white_point), white_point),
                 volume=float(ConvexHull(verts).volume),
                 space="lab", mode="argyll-gam")


def _find_iccgamut() -> "str | None":
    """Where ArgyllCMS keeps iccgamut, if it is installed."""
    import shutil
    found = shutil.which("iccgamut")
    if found:
        return found
    for guess in ("/Applications/Argyll/bin/iccgamut",
                  "/usr/local/bin/iccgamut", "/opt/homebrew/bin/iccgamut",
                  r"C:\Argyll\bin\iccgamut.exe"):
        if pathlib.Path(guess).is_file():
            return guess
    return None


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


def icc_gamut(path, *, white_point: str = "D50", intent: str = "r", **_ignored):
    """The gamut of any ICC profile, computed by ArgyllCMS itself.

    Asks ``iccgamut`` — the same tool ChromIQ uses — rather than pushing a grid
    through the profile here. That matters for accuracy: an eight-bit Lab
    round-trip clips a* and b* at ±128, which on a real printer profile
    inflated the answer roughly sevenfold. ArgyllCMS returns the surface it
    computed, in full precision, with its triangles, so the shape has the
    profile's real dents in it.

    *intent* is passed to ``iccgamut -i``: "r" relative colorimetric (the
    default, and the right one for "what can this profile actually reach"),
    "a" absolute, "p" perceptual, "s" saturation.

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

    tool = _find_iccgamut()
    if tool is None:
        raise ValueError(
            "Reading an ICC profile needs ArgyllCMS, which does not appear to "
            "be installed. It is the same free toolkit that measured your "
            "chart in the first place — install it, or compare against one of "
            "the built-in colour spaces instead.")

    with tempfile.TemporaryDirectory(prefix="iccgamut-") as tmp:
        work = pathlib.Path(tmp) / path.name
        shutil.copy2(path, work)
        try:
            done = subprocess.run(
                [tool, "-i", intent, str(work)],
                capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                f"{path.name} took too long to read and was given up on") from exc
        gam = work.with_suffix(".gam")
        if done.returncode != 0 or not gam.is_file():
            detail = (done.stderr or done.stdout or "").strip().splitlines()
            why = detail[-1] if detail else f"exit code {done.returncode}"
            raise ValueError(
                f"{path.name} could not be read as a colour profile: "
                f"{why}.\n\nDevice-link and abstract profiles do not describe "
                "a gamut, so there is nothing to draw for them.")
        verts, faces = _read_gam(gam)

    if len(verts) < 4:
        raise ValueError(f"{path.name} describes no usable volume")
    from scipy.spatial import ConvexHull
    from gamutview import Gamut, lab_to_xyz, xyz_to_srgb
    return Gamut(vertices=verts, faces=faces,
                 colors=xyz_to_srgb(lab_to_xyz(verts, white_point), white_point),
                 volume=float(ConvexHull(verts).volume),
                 space="lab", mode="icc-profile")
