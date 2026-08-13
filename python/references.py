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

import numpy as np

from gamutview import (WHITE_POINTS, _bradford_adapt, _as_white_point,
                       build_gamut, xyz_to_lab)

__all__ = ["REFERENCE_SPACES", "reference_gamut", "icc_gamut"]

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


def reference_gamut(name: str, *, white_point: str = "D50", steps: int = 8):
    """The gamut of a standard RGB working space, in Lab under *white_point*.

    Built as the six faces of its own RGB cube — the same construction used for
    a printer's measured gamut — so the two are directly comparable rather than
    one being a hull and the other a boundary.
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


def icc_gamut(path, *, white_point: str = "D50", steps: int = 12,
              intent: int = 1):
    """The gamut of any ICC profile, by asking the profile itself.

    Sends an evenly spaced RGB cube through the profile to Lab and builds the
    boundary from the faces of that cube — the same construction as everything
    else here, so the numbers stay comparable.

    *intent* is a Little-CMS rendering intent: 0 perceptual, 1 relative
    colorimetric (the default, and the right one for asking "what can this
    profile actually reach"), 2 saturation, 3 absolute colorimetric.

    Needs ``littlecms`` (``pip install littlecms``) or ``Pillow`` with LittleCMS
    support, which is how Pillow is normally built.
    """
    from pathlib import Path

    path = Path(path)
    if not path.is_file():
        raise ValueError(f"no such profile: {path}")

    try:
        from PIL import Image, ImageCms
    except ImportError as exc:                      # pragma: no cover
        raise ValueError(
            "reading an ICC profile needs Pillow — pip install Pillow") from exc

    try:
        src = ImageCms.getOpenProfile(str(path))
    except Exception as exc:
        raise ValueError(f"{path.name} could not be read as an ICC profile: "
                         f"{exc}") from exc

    n_ch = len(ImageCms.getProfileInfo(src)) and 3   # RGB profiles only, for now
    g = np.linspace(0, 255, steps).astype(np.uint8)
    r, gg, b = np.meshgrid(g, g, g, indexing="ij")
    grid = np.stack([r.ravel(), gg.ravel(), b.ravel()], axis=-1).astype(np.uint8)

    img = Image.frombytes("RGB", (len(grid), 1), grid.tobytes())
    lab_profile = ImageCms.createProfile("LAB", 5000 if white_point == "D50"
                                         else 6500)
    try:
        xform = ImageCms.buildTransform(src, lab_profile, "RGB", "LAB",
                                        renderingIntent=intent)
        out = ImageCms.applyTransform(img, xform)
    except Exception as exc:
        raise ValueError(
            f"{path.name} is not an RGB profile this can use ({exc}). CMYK and "
            "device-link profiles are not supported yet.") from exc

    raw = np.frombuffer(out.tobytes(), dtype=np.uint8).reshape(-1, 3).astype(float)
    # Pillow's 8-bit LAB: L 0..255 -> 0..100, a/b 0..255 with 128 as zero.
    lab = np.column_stack([raw[:, 0] * 100.0 / 255.0, raw[:, 1] - 128.0,
                           raw[:, 2] - 128.0])

    # REFUSE A CLIPPED ANSWER RATHER THAN DRAW A WRONG ONE. Pillow's Lab is
    # eight bits per channel, so a* and b* cannot leave -128..127. A profile
    # whose colours reach those ends has been squashed into the byte range, and
    # the "gamut" that comes back is the shape of the encoding rather than the
    # shape of the profile -- on a real printer profile that inflated the
    # volume roughly sevenfold. A confident wrong answer is worse than none.
    at_edge = ((np.abs(lab[:, 1] + 128.0) < 0.5) | (np.abs(lab[:, 1] - 127.0) < 0.5)
               | (np.abs(lab[:, 2] + 128.0) < 0.5) | (np.abs(lab[:, 2] - 127.0) < 0.5))
    if at_edge.mean() > 0.02:
        raise ValueError(
            f"{path.name} cannot be read accurately here. Its colours run past "
            "what this reader can represent, so the shape would be wrong -- "
            "and wrong in the flattering direction. Compare against a measured "
            "chart, or one of the built-in colour spaces, instead.")
    return build_gamut(lab, grid.astype(float) / 255.0, input_space="lab",
                       white_point=white_point)
