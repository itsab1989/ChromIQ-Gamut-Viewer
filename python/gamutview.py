"""Build a 3D colour gamut from measured colour values — a Python port.

A port of ``gamutview.m`` (Qiu Jueqin, 2019, MIT) so the same idea can be used
from a Python project. The original both *computes* the gamut and *draws* it in
a MATLAB figure; this port does only the computing and hands back plain arrays,
because every Python project already has its own idea of how to draw (Plotly,
Matplotlib, VTK, a Qt WebEngine view…). Drawing is a dozen lines on top — see
``demo.py``.

WHAT IT IS FOR
--------------
Given a set of colours a device actually produced — for a printer, the patches
of a measured chart — it returns the closed surface that encloses them, its
volume, and a colour for every vertex, so the shape can be drawn in the colour
it represents.

THE TWO MODES, AND WHY THE SECOND ONE MATTERS
---------------------------------------------
**Mode 1 —** ``build_gamut(colors)``. The convex hull of the measured cloud.
Simple, but a real printer gamut is *not* convex: hulls bridge straight over
the concavities a printer actually has, most visibly in the dark blues and the
cyan-to-blue ridge, so this over-states the gamut.

**Mode 2 —** ``build_gamut(colors, drive_values)``. This is the useful one, and
it is the original's real contribution. If you also pass the device values you
*asked* for (the RGB sent to the printer) alongside what you *measured*, the
surface is built as the six faces of the device cube mapped through the
measurement — so the shape follows the device's real, dented boundary instead
of a hull thrown around it. A measured ``.ti3`` has both halves of that pair
already: the device RGB and the measured XYZ or Lab.

COLOUR SCIENCE
--------------
Conversions are explicit about their white point, which is a thing worth being
fussy about: the same XYZ under D50 and under D65 give different Lab, so a
gamut plotted under the wrong one is the wrong shape. The default is **D50**,
the ICC profile connection space illuminant and what print measurement uses;
pass ``white_point="D65"`` for display work. sRGB output always uses D65, its
own defined white, with a Bradford adaptation applied when the working white
differs — never a silent mismatch.

Only what a gamut needs is implemented: XYZ, Lab, LCh and sRGB. It is not a
general colour library; use ``colour-science`` if you need one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

__all__ = ["Gamut", "build_gamut", "xyz_to_lab", "lab_to_xyz", "xyz_to_srgb",
           "lab_to_lch_cartesian", "WHITE_POINTS"]

Space = Literal["xyz", "lab"]

#: CIE 1931 2° white points, XYZ normalised to Y = 1.
WHITE_POINTS: dict[str, np.ndarray] = {
    "D50": np.array([0.96422, 1.00000, 0.82521]),
    "D65": np.array([0.95047, 1.00000, 1.08883]),
    "A":   np.array([1.09850, 1.00000, 0.35585]),
    "E":   np.array([1.00000, 1.00000, 1.00000]),
}

_EPSILON = 1e-6
# CIE standard, exact rational forms rather than the rounded 0.008856 / 903.3.
_KAPPA = 24389.0 / 27.0
_DELTA3 = 216.0 / 24389.0

# sRGB primaries, D65 (IEC 61966-2-1).
_XYZ_TO_LINEAR_SRGB = np.array([
    [3.2404542, -1.5371385, -0.4985314],
    [-0.9692660, 1.8760108, 0.0415560],
    [0.0556434, -0.2040259, 1.0572252],
])
# Bradford cone response, for adapting between white points.
_BRADFORD = np.array([
    [0.8951, 0.2664, -0.1614],
    [-0.7502, 1.7135, 0.0367],
    [0.0389, -0.0685, 1.0296],
])


def _as_white_point(wp) -> np.ndarray:
    """A white point from a name ("D50") or an XYZ triple."""
    if isinstance(wp, str):
        try:
            return WHITE_POINTS[wp.upper()]
        except KeyError:
            raise ValueError(
                f"unknown white point {wp!r}; known: {', '.join(WHITE_POINTS)}"
            ) from None
    wp = np.asarray(wp, dtype=float).reshape(3)
    if wp[1] <= 0:
        raise ValueError("white point must have Y > 0")
    return wp


def _bradford_adapt(src, dst) -> np.ndarray:
    """3x3 matrix adapting XYZ from white point *src* to *dst*."""
    s = _BRADFORD @ src
    d = _BRADFORD @ dst
    return np.linalg.inv(_BRADFORD) @ np.diag(d / s) @ _BRADFORD


def xyz_to_lab(xyz, white_point="D50") -> np.ndarray:
    """CIE XYZ (Y = 1 for white) to CIE L*a*b* under *white_point*."""
    xyz = np.asarray(xyz, dtype=float)
    r = xyz / _as_white_point(white_point)
    f = np.where(r > _DELTA3, np.cbrt(np.abs(r)), (_KAPPA * r + 16.0) / 116.0)
    return np.stack([116.0 * f[..., 1] - 16.0,
                     500.0 * (f[..., 0] - f[..., 1]),
                     200.0 * (f[..., 1] - f[..., 2])], axis=-1)


def lab_to_xyz(lab, white_point="D50") -> np.ndarray:
    """The inverse of :func:`xyz_to_lab`."""
    lab = np.asarray(lab, dtype=float)
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    f = np.stack([fx, fy, fz], axis=-1)
    cube = f ** 3
    r = np.where(cube > _DELTA3, cube, (116.0 * f - 16.0) / _KAPPA)
    # L* below the linear-segment knee has its own inverse for Y.
    r[..., 1] = np.where(lab[..., 0] > _KAPPA * _DELTA3,
                         ((lab[..., 0] + 16.0) / 116.0) ** 3,
                         lab[..., 0] / _KAPPA)
    return r * _as_white_point(white_point)


def xyz_to_srgb(xyz, white_point="D50", clip: bool = True) -> np.ndarray:
    """CIE XYZ to non-linear sRGB in 0..1, for painting a vertex its own colour.

    sRGB is defined against D65, so when *white_point* is anything else the XYZ
    is Bradford-adapted to D65 first rather than being fed in as though the two
    whites were the same. Out-of-gamut colours — most of a printer's darkest and
    most saturated corners, and everything outside sRGB — are clipped, which is
    honest for *painting a picture* and useless for measurement. Never treat the
    result as a colour value; it is ink for the screen.
    """
    xyz = np.asarray(xyz, dtype=float)
    src = _as_white_point(white_point)
    d65 = WHITE_POINTS["D65"]
    if not np.allclose(src, d65):
        xyz = xyz @ _bradford_adapt(src, d65).T
    linear = xyz @ _XYZ_TO_LINEAR_SRGB.T
    if clip:
        linear = np.clip(linear, 0.0, 1.0)
    srgb = np.where(linear <= 0.0031308,
                    12.92 * linear,
                    1.055 * np.power(np.abs(linear), 1 / 2.4) - 0.055)
    return np.clip(srgb, 0.0, 1.0) if clip else srgb


def lab_to_lch_cartesian(lab) -> np.ndarray:
    """Lab to the cylindrical arrangement the original plots: (C·cos h, C·sin h, L).

    The same points, laid out so hue runs around the axis and lightness up it —
    which is how a gamut is usually read.
    """
    lab = np.asarray(lab, dtype=float)
    c = np.hypot(lab[..., 1], lab[..., 2])
    h = np.arctan2(lab[..., 2], lab[..., 1])
    return np.stack([c * np.cos(h), c * np.sin(h), lab[..., 0]], axis=-1)


@dataclass(frozen=True)
class Gamut:
    """A closed gamut surface.

    ``vertices``  (N, 3) points, in *space*.
    ``faces``     (M, 3) triangles indexing ``vertices``.
    ``colors``    (N, 3) sRGB 0..1 per vertex, for painting the surface.
    ``volume``    enclosed volume of the convex hull, in the units of *space*
                  cubed (for Lab, cubic ΔE units — Argyll's "units").
    ``space``     which space ``vertices`` are in.
    ``mode``      "hull" or "device-cube", i.e. which of the two it used.
    """
    vertices: np.ndarray
    faces: np.ndarray
    colors: np.ndarray
    volume: float
    space: str
    mode: str

    def cylindrical(self) -> np.ndarray:
        """``vertices`` laid out as (C·cos h, C·sin h, L). Lab only."""
        if self.space != "lab":
            raise ValueError("cylindrical() needs a Lab gamut")
        return lab_to_lch_cartesian(self.vertices)


def _finite_rows(*arrays):
    """Drop any row that is NaN or infinite in any of *arrays*, together."""
    keep = np.ones(len(arrays[0]), dtype=bool)
    for a in arrays:
        if a is not None:
            keep &= np.isfinite(a).all(axis=1)
    return keep


def build_gamut(colors, drive_values=None, *, space: Space = "lab",
                input_space: Space = "xyz", white_point="D50") -> Gamut:
    """Build the gamut surface enclosing *colors*.

    ``colors``        (N, 3) measured values — the patches of a chart.
    ``drive_values``  (N, 3) optional device values that produced them, in any
                      consistent units (0..1 or 0..255). Supplying them selects
                      mode 2, which follows the device's real boundary instead
                      of throwing a convex hull around it. Strongly preferred.
    ``space``         the space to build in: "lab" (default) or "xyz".
    ``input_space``   what ``colors`` already are: "xyz" (default) or "lab".
    ``white_point``   name or XYZ triple; D50 for print, D65 for display.

    Rows that are NaN or infinite are dropped — a failed patch reading should
    not take the whole gamut with it — and duplicate device values are removed,
    keeping the first of each.
    """
    from scipy.spatial import ConvexHull, QhullError

    colors = np.asarray(colors, dtype=float)
    if colors.ndim != 2 or colors.shape[1] != 3:
        raise ValueError(f"colors must be (N, 3), got {colors.shape}")
    if drive_values is not None:
        drive_values = np.asarray(drive_values, dtype=float)
        if drive_values.shape != colors.shape:
            raise ValueError(
                f"drive_values {drive_values.shape} must match colors "
                f"{colors.shape} — they are pairs, one per patch")

    keep = _finite_rows(colors, drive_values)
    colors = colors[keep]
    if drive_values is not None:
        drive_values = drive_values[keep]
    if len(colors) < 4:
        raise ValueError(
            f"need at least 4 usable colours to enclose a volume, got {len(colors)}")

    # Into the space we are building in, and keep XYZ for painting.
    if input_space == space:
        pts = colors
    elif input_space == "xyz" and space == "lab":
        pts = xyz_to_lab(colors, white_point)
    elif input_space == "lab" and space == "xyz":
        pts = lab_to_xyz(colors, white_point)
    else:
        raise ValueError(f"cannot go from {input_space!r} to {space!r}")
    xyz = colors if input_space == "xyz" else lab_to_xyz(colors, white_point)

    try:
        hull = ConvexHull(pts)
    except QhullError as exc:
        raise ValueError(
            "the colours do not enclose a volume — they may be collinear, "
            "coplanar, or all the same") from exc
    volume = float(hull.volume)

    if drive_values is None:
        idx = np.unique(hull.vertices)
        verts, mode = pts[idx], "hull"
        remap = {old: new for new, old in enumerate(idx)}
        faces = np.array([[remap[i] for i in s] for s in hull.simplices
                          if all(i in remap for i in s)], dtype=int)
        v_xyz = xyz[idx]
    else:
        _, first = np.unique(drive_values, axis=0, return_index=True)
        first.sort()
        dv, pts_u, xyz_u = drive_values[first], pts[first], xyz[first]
        verts, faces, v_xyz = _device_cube_surface(dv, pts_u, xyz_u)
        mode = "device-cube"

    return Gamut(vertices=verts, faces=faces,
                 colors=xyz_to_srgb(v_xyz, white_point),
                 volume=volume, space=space, mode=mode)


def _device_cube_surface(drive_values, pts, xyz):
    """Mode 2: the six faces of the device cube, mapped into measurement space.

    Each face is the set of patches holding one channel at its extreme, which is
    a 2D grid once that channel is dropped; Delaunay over the remaining two
    channels triangulates it in *device* space, and the triangles are then used
    on the measured points. Triangulating in device space rather than measured
    space is the whole trick — the device grid is regular even where the
    measurement is dented, so the surface follows the real boundary.

    The original walks each face finding four nearest neighbours per vertex;
    Delaunay is the same intent, without the ordering assumptions.
    """
    from scipy.spatial import Delaunay, QhullError

    lo, hi = drive_values.min(axis=0), drive_values.max(axis=0)
    verts_out: list[np.ndarray] = []
    xyz_out: list[np.ndarray] = []
    faces_out: list[np.ndarray] = []
    n = 0
    for channel in range(3):
        for value in (lo[channel], hi[channel]):
            on_face = np.abs(drive_values[:, channel] - value) <= _EPSILON
            if on_face.sum() < 3:
                continue                      # not a populated face; skip it
            flat = np.delete(drive_values[on_face], channel, axis=1)
            try:
                tri = Delaunay(flat)
            except QhullError:
                continue                      # degenerate face, nothing to add
            verts_out.append(pts[on_face])
            xyz_out.append(xyz[on_face])
            faces_out.append(tri.simplices + n)
            n += int(on_face.sum())

    if not faces_out:
        raise ValueError(
            "no populated faces of the device cube — drive_values must include "
            "patches at the extremes of each channel (the faces of the RGB cube)")
    return (np.vstack(verts_out), np.vstack(faces_out), np.vstack(xyz_out))
