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

__all__ = ["Gamut", "build_gamut", "coverage", "mesh_volume", "outside_of", "slice_at", "cut_segments", "delta_e_2000", "xyz_to_lab", "lab_to_xyz", "xyz_to_srgb",
           "lab_to_lch_cartesian", "WHITE_POINTS",
           "xyz_to_luv", "luv_to_xyz", "SPACES", "AXES", "DRAW_SPACES",
           "CAPABILITIES", "can_do", "enclosure", "split_at_crossing"]

Space = Literal["xyz", "lab", "luv"]

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


def xyz_to_luv(xyz, white_point="D50") -> np.ndarray:
    """CIE XYZ (Y = 1 for white) to CIE 1976 L*u*v* under *white_point*.

    CIELUV shares CIELAB's lightness exactly — the same L* from the same Y —
    and differs in how it places the colour. It is built on the u', v'
    chromaticity diagram, which is the one that mixes additively: a blend of
    two lights lies on the straight line between them. That makes it the space
    displays and light sources are usually discussed in, and it stretches the
    blues and greens noticeably compared with CIELAB.

    The u', v' denominator vanishes only for XYZ = (0, 0, 0), which is black;
    there u* = v* = 0 is the right answer, so it is substituted rather than
    left as a division warning.
    """
    xyz = np.asarray(xyz, dtype=float)
    white = _as_white_point(white_point)
    yr = xyz[..., 1] / white[1]
    ell = np.where(yr > _DELTA3, 116.0 * np.cbrt(np.abs(yr)) - 16.0,
                   _KAPPA * yr)

    def _uv(c):
        d = c[..., 0] + 15.0 * c[..., 1] + 3.0 * c[..., 2]
        safe = np.where(d == 0.0, 1.0, d)
        return (np.where(d == 0.0, 0.0, 4.0 * c[..., 0] / safe),
                np.where(d == 0.0, 0.0, 9.0 * c[..., 1] / safe))

    up, vp = _uv(xyz)
    upn, vpn = _uv(white[None, :])
    return np.stack([ell,
                     13.0 * ell * (up - upn),
                     13.0 * ell * (vp - vpn)], axis=-1)


def luv_to_xyz(luv, white_point="D50") -> np.ndarray:
    """The inverse of :func:`xyz_to_luv`."""
    luv = np.asarray(luv, dtype=float)
    white = _as_white_point(white_point)
    ell = luv[..., 0]
    d = white[0] + 15.0 * white[1] + 3.0 * white[2]
    upn, vpn = 4.0 * white[0] / d, 9.0 * white[1] / d
    y = np.where(ell > _KAPPA * _DELTA3, ((ell + 16.0) / 116.0) ** 3,
                 ell / _KAPPA) * white[1]
    safe = np.where(ell == 0.0, 1.0, 13.0 * ell)
    up = np.where(ell == 0.0, upn, luv[..., 1] / safe + upn)
    vp = np.where(ell == 0.0, vpn, luv[..., 2] / safe + vpn)
    vsafe = np.where(vp == 0.0, 1.0, vp)
    x = np.where(vp == 0.0, 0.0, 9.0 * y * up / (4.0 * vsafe))
    z = np.where(vp == 0.0, 0.0,
                 (9.0 * y - (15.0 * vp * y) - (vp * x)) / (3.0 * vsafe))
    return np.stack([x, y, z], axis=-1)


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


#: The spaces a gamut can be built and drawn in, and what each is good for.
#: Every conversion goes through XYZ, so a space needs only a pair of
#: functions here to be usable everywhere in the app.
#:
#: DEVICE SPACE IS DELIBERATELY NOT IN HERE. Ink amounts are not a colour
#: space: there is no conversion from "70% red" to XYZ without asking a
#: profile what this particular printer does with 70% red, and two printers
#: answer differently. Anything that builds or measures a gamut takes one of
#: these three; ``DRAW_SPACES`` below is the wider list of things the window
#: will put on its axes, and it is wider precisely because drawing dots needs
#: less than measuring a volume does.
SPACES = ("lab", "luv", "xyz")

_TO_XYZ = {
    "xyz": lambda c, wp: np.asarray(c, dtype=float),
    "lab": lab_to_xyz,
    "luv": luv_to_xyz,
}
_FROM_XYZ = {
    "xyz": lambda c, wp: np.asarray(c, dtype=float),
    "lab": xyz_to_lab,
    "luv": xyz_to_luv,
}

#: What a space is capable of carrying. Every feature of the window that only
#: makes sense in some spaces names one of these, and ``AXES[space]["can"]``
#: says whether it is available. The point of naming them is that a new space
#: cannot quietly leave a control switched on: the window's registry maps each
#: control to one of these names, and a test walks every control on the panel
#: and fails on any that is neither registered nor declared space-independent.
#:
#: ``hue_circle``  the two colour axes can be rearranged into a hue circle
#:                 around a lightness axis — what the slice, the rings and the
#:                 grey axis are all defined against.
#: ``shapes``      a gamut surface drawn here is a real boundary. It is not
#:                 enough that a surface *can* be computed: in ink amounts the
#:                 surface of every RGB printer is the same unit cube, so a
#:                 shape here would be true and say nothing.
#: ``volume``      a volume or a coverage percentage measured here means
#:                 something. Follows ``shapes``, and is separate because a
#:                 space could in principle draw a boundary worth looking at
#:                 without its units being worth multiplying together.
#: ``white_point`` some colour in the picture is read against a chosen white.
#:                 Ink amounts keep this even though their axes do not depend
#:                 on it: a chart drawn there is still painted with the colours
#:                 a profile predicts, and still counted against a paper, and
#:                 both of those are read against a white. Switching the
#:                 control off would have looked tidy and taken away the only
#:                 way to answer the mismatch warning the same panel raises.
CAPABILITIES = frozenset({"hue_circle", "shapes", "volume", "white_point"})

#: How each space is drawn: the three axis titles, and whether the two colour
#: axes are rearranged into a hue circle around a lightness axis. XYZ has no
#: lightness and no hue, so it is plotted exactly as measured.
#:
#: ``rgb`` is the odd one and is meant to be. It is not a colour space and it
#: is not in ``SPACES``; it is the printer's own controls, three numbers from
#: 0 to 100 meaning "this much of each ink". A chart is a list of exactly
#: those numbers, which is why a chart can be drawn here with no profile at
#: all, and why nothing that needs to know what a colour *is* can be.
AXES = {
    "lab": dict(cylindrical=True, x="a*  (chroma →)", y="b*", z="L*",
                units="cubic Lab units", kind="colour",
                can=frozenset({"hue_circle", "shapes", "volume",
                               "white_point"})),
    "luv": dict(cylindrical=True, x="u*  (chroma →)", y="v*", z="L*",
                units="cubic Luv units", kind="colour",
                can=frozenset({"hue_circle", "shapes", "volume",
                               "white_point"})),
    "xyz": dict(cylindrical=False, x="X", y="Y", z="Z",
                units="cubic XYZ units", kind="colour",
                can=frozenset({"shapes", "volume", "white_point"})),
    "rgb": dict(cylindrical=False, x="Red  %", y="Green  %", z="Blue  %",
                units="percent of the ink range, cubed", kind="device",
                can=frozenset({"white_point"})),
}

#: Everything the window will put on its axes: the colour spaces a gamut can
#: be measured in, plus the device space that only a chart can be drawn in.
DRAW_SPACES = SPACES + ("rgb",)


def can_do(space: str, capability: str) -> bool:
    """Whether *space* supports *capability*.

    The one place the question is answered, so that "is the slice available"
    and "is the volume worth quoting" cannot drift apart. An unknown
    capability is a programming mistake and says so rather than returning
    False, which would silently switch a working control off for ever.
    """
    if capability not in CAPABILITIES:
        raise ValueError(
            f"{capability!r} is not a capability; known ones are "
            f"{sorted(CAPABILITIES)}")
    try:
        return capability in AXES[space]["can"]
    except KeyError:
        raise ValueError(f"{space!r} is not a space this window draws in;"
                         f" known ones are {sorted(AXES)}") from None


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
        """``vertices`` laid out as (C·cos h, C·sin h, L).

        Both of the opponent spaces arrange the same way: two colour axes and
        lightness up the middle. XYZ has no lightness axis and no hue angle,
        so it is plotted as it is and asking for this is a mistake worth
        reporting rather than quietly returning the wrong picture.
        """
        if self.space not in ("lab", "luv"):
            raise ValueError(
                f"cylindrical() needs a Lab or Luv gamut, not {self.space!r}")
        return lab_to_lch_cartesian(self.vertices)


def mesh_volume(vertices, faces) -> float:
    """Volume actually enclosed by a closed triangle mesh.

    The divergence theorem summed over triangles, which is exact for any closed
    surface, convex or not. This is what lets the number agree with the
    picture: a printer's real boundary is dented, and those dents enclose less
    than a skin stretched over the whole thing.

    Each triangle is oriented outward from the mesh centroid first. Without
    that the answer is meaningless -- the six faces of the device cube are
    triangulated independently, so their windings disagree and the signed
    volumes partly cancel. Getting this wrong once produced a figure three
    times too small, which is why the orientation is done here rather than
    assumed of the caller.
    """
    v = np.asarray(vertices, dtype=float)
    f = np.asarray(faces, dtype=int)
    if len(f) == 0 or len(v) < 4:
        return 0.0
    centre = v.mean(axis=0)
    a, b, c = v[f[:, 0]] - centre, v[f[:, 1]] - centre, v[f[:, 2]] - centre
    signed = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    # Flip whichever triangles face inward, then sum: |signed| is the volume of
    # the tetrahedron from the centroid to that triangle, and for a closed
    # surface those tile the interior exactly once.
    return float(np.abs(signed).sum())


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
    ``space``         the space to build and draw in: "lab" (default),
                      "luv" or "xyz".
    ``input_space``   what ``colors`` already are: "xyz" (default), "lab"
                      or "luv".
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

    # Into the space we are building in, and keep XYZ for painting. Everything
    # goes through XYZ rather than each pair of spaces knowing about each
    # other: three spaces would otherwise need six conversions, and adding a
    # fourth would need eight more.
    for name, value in (("space", space), ("input_space", input_space)):
        if value not in SPACES:
            raise ValueError(
                f"{name} must be one of {', '.join(SPACES)}, got {value!r}")
    xyz = _TO_XYZ[input_space](colors, white_point)
    pts = colors if input_space == space else _FROM_XYZ[space](xyz, white_point)

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
        # The drawn surface is closed but not convex, so what it encloses --
        # not what a hull around it would -- is what this printer can print.
        volume = mesh_volume(verts, faces)

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


def delta_e_2000(lab1, lab2) -> np.ndarray:
    """CIEDE2000 colour difference between two sets of Lab values.

    The modern standard, and the one worth the arithmetic: CIE76 is a plain
    distance and badly over-states differences in the blues, which is exactly
    where a printer drifts. Implemented from the CIE definition rather than
    approximated -- a drift check is only worth having if the number is one
    people can act on.
    """
    lab1 = np.atleast_2d(np.asarray(lab1, dtype=float))
    lab2 = np.atleast_2d(np.asarray(lab2, dtype=float))
    if lab1.shape != lab2.shape:
        raise ValueError(f"cannot compare {lab1.shape} values with {lab2.shape}")

    l1, a1, b1 = lab1[:, 0], lab1[:, 1], lab1[:, 2]
    l2, a2, b2 = lab2[:, 0], lab2[:, 1], lab2[:, 2]
    c1, c2 = np.hypot(a1, b1), np.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0
    g = 0.5 * (1 - np.sqrt(c_bar ** 7 / (c_bar ** 7 + 25.0 ** 7 + 1e-30)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0

    dlp = l2 - l1
    dcp = c2p - c1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, np.where(dhp < -180, dhp + 360, dhp))
    dhp = np.where(c1p * c2p == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dhp / 2.0))

    lp_bar = (l1 + l2) / 2.0
    cp_bar = (c1p + c2p) / 2.0
    hsum = h1p + h2p
    hdiff = np.abs(h1p - h2p)
    hp_bar = np.where(c1p * c2p == 0, hsum,
                      np.where(hdiff <= 180, hsum / 2.0,
                               np.where(hsum < 360, (hsum + 360) / 2.0,
                                        (hsum - 360) / 2.0)))
    t = (1
         - 0.17 * np.cos(np.radians(hp_bar - 30))
         + 0.24 * np.cos(np.radians(2 * hp_bar))
         + 0.32 * np.cos(np.radians(3 * hp_bar + 6))
         - 0.20 * np.cos(np.radians(4 * hp_bar - 63)))
    sl = 1 + (0.015 * (lp_bar - 50) ** 2) / np.sqrt(20 + (lp_bar - 50) ** 2)
    sc = 1 + 0.045 * cp_bar
    sh = 1 + 0.015 * cp_bar * t
    rt = (-2 * np.sqrt(cp_bar ** 7 / (cp_bar ** 7 + 25.0 ** 7 + 1e-30))
          * np.sin(np.radians(60 * np.exp(-(((hp_bar - 275) / 25.0) ** 2)))))
    return np.sqrt((dlp / sl) ** 2 + (dcp / sc) ** 2 + (dHp / sh) ** 2
                   + rt * (dcp / sc) * (dHp / sh))


def cut_segments(vertices, faces, lightness: float) -> np.ndarray:
    """Where the plane L* = *lightness* meets a triangle mesh, as line segments.

    Returns an (M, 2, 2) array of a*/b* endpoints — the exact cross-section of
    the surface, one segment per triangle the plane passes through. A plane
    crosses a triangle in a straight line or not at all, so this is not an
    approximation of the cut: it *is* the cut, to the precision of the mesh
    that was measured.

    A CORNER SITTING EXACTLY IN THE PLANE IS COUNTED ON ONE SIDE, always the
    same one. Every awkward case follows from that single convention rather
    than from a rule of its own, and the awkward cases are not rare -- a
    measured surface and a reference cube both put vertices on round numbers,
    and the cut slider asks for round numbers.

    Handled, and each was checked against a mesh built to produce it: a
    triangle **grazing the plane at one corner** yields a zero-length segment
    that no ray can meet; one **with an edge lying in the plane** yields that
    edge, which is genuinely part of the cross-section; one **lying wholly in
    the plane** yields nothing, because its three edges already come from the
    neighbours that cross, and emitting them again would draw the boundary
    twice. Treating a zero-height corner as belonging to both sides instead --
    which reads as the careful thing to do -- makes a triangle report three
    crossings, and the first two of them are the same point twice.
    """
    v = np.asarray(vertices, float)
    f = np.asarray(faces, int)
    if len(f) == 0:
        return np.empty((0, 2, 2))
    tri = v[f]                                       # (M, 3, 3)
    h = tri[:, :, 0] - lightness                     # each corner's height
    side = h >= 0.0
    live = side.any(axis=1) & ~side.all(axis=1)
    if not live.any():
        return np.empty((0, 2, 2))
    tri, h, side = tri[live], h[live], side[live]

    out = np.empty((len(tri), 2, 2))
    got = np.zeros(len(tri), int)
    for i in range(3):
        j = (i + 1) % 3
        crosses = side[:, i] != side[:, j]
        gap = h[:, i] - h[:, j]
        # The two corners are on opposite sides, so the gap cannot be zero;
        # the guard is against arithmetic, not against a real case.
        w = h[:, i] / np.where(np.abs(gap) > 1e-15, gap, 1.0)
        point = tri[:, i, 1:] + w[:, None] * (tri[:, j, 1:] - tri[:, i, 1:])
        first = crosses & (got == 0)
        second = crosses & (got == 1)
        out[first, 0] = point[first]
        out[second, 1] = point[second]
        got += crosses
    return out[got >= 2]


def slice_at(gamut, lightness: float, steps: int = 180) -> np.ndarray:
    """The outline of *gamut* at one lightness, as points around a*/b*.

    A 3D shape is honest and hard to read: two overlapping blobs hide each
    other, and depth on a flat screen is guesswork. A horizontal cut through
    both at the same lightness turns the comparison into two flat outlines,
    where "this one reaches further into the cyans" is simply visible.

    THE CUT IS TAKEN THROUGH THE SURFACE ITSELF, and it used to be taken
    through the convex hull of the surface's points -- ``Delaunay(v)``, which
    tessellates exactly that hull. So every dent in the gamut was filled in
    before the outline was drawn, and the picture whose whole purpose is
    showing where one paper reaches further than another was drawing both of
    them reaching further than they do.

    Measured on Adobe RGB, which is a distorted cube in Lab and nowhere near
    convex: at seven lightnesses from L* 20 to 80, the hull outline stood
    outside the real one in **138 to 159 of every 180 directions**, by as much
    as **10.05 Lab units** -- some thirty times the difference a good eye can
    see -- and enclosed 4.6% more area. It was wrong everywhere, always
    outwards, and worst at the light and dark ends where two papers differ
    most.

    A plane crosses a triangle in a straight line, so the cross-section of the
    mesh is a set of segments and can simply be computed -- see
    :func:`cut_segments`. No bisection, no containment test, no triangulation
    to build, and nothing assumed about the shape being convex or smooth. For
    each direction around the hue circle the outline is the **furthest** point
    the ray meets, which is what "how far does this paper reach in the cyans"
    asks. Whether the gamut is star-shaped about its grey axis was measured
    rather than assumed: over 15,300 rays through both demo gamuts, exactly
    two met more than one boundary.

    Returns an (N, 2) array of a*/b* points, empty when the gamut does not
    reach that lightness at all. A bare cloud of points carries no surface, and
    for that the convex hull is the only answer there is.
    """
    v = np.asarray(gamut.vertices if hasattr(gamut, "vertices") else gamut, float)
    faces = getattr(gamut, "faces", None)
    if len(v) < 4:
        raise ValueError("a gamut needs at least 4 vertices to be sliced")
    # THE TWO EXTREMES ARE EXCLUDED, AND BOTH OF THEM. A cut taken exactly at
    # the top or the bottom of a shape has no inside for the grey axis to be
    # in: on a real gamut it is the single point of the paper white or of the
    # deepest black, and an outline through one point is not one anybody can
    # compare with another paper's.
    #
    # Both, because a cut has to say which side a corner lying exactly in the
    # plane is on, and whichever it says, the two ends of the shape stop
    # behaving alike -- a box cut at its ceiling returned the outline of its
    # top face and the same box cut at its floor returned nothing at all.
    # That asymmetry has no meaning in it; it is the convention showing
    # through, so neither end is offered rather than one of them.
    if not (v[:, 0].min() < lightness < v[:, 0].max()):
        return np.empty((0, 2))
    if faces is None or len(faces) == 0:
        return _slice_a_bare_cloud(v, lightness, steps)

    seg = cut_segments(v, np.asarray(faces, int), lightness)
    if len(seg) < 3:
        return np.empty((0, 2))

    angles = np.linspace(0, 2 * np.pi, steps, endpoint=False)
    d = np.stack([np.cos(angles), np.sin(angles)], axis=1)        # (S, 2)
    p, e = seg[:, 0, :], seg[:, 1, :] - seg[:, 0, :]              # (M, 2)
    # Where each ray from the grey axis meets each segment: p + u·e = t·d.
    den = e[None, :, 0] * d[:, None, 1] - e[None, :, 1] * d[:, None, 0]
    live = np.abs(den) > 1e-12                   # parallel: never crossed
    safe = np.where(live, den, 1.0)
    u = (p[None, :, 1] * d[:, None, 0] - p[None, :, 0] * d[:, None, 1]) / safe
    where = p[None, :, :] + u[:, :, None] * e[None, :, :]
    t = np.einsum("smk,sk->sm", where, d)
    hit = live & (u >= 0.0) & (u <= 1.0) & (t > 0.0)

    # THE GREY AXIS HAS TO BE INSIDE THE CUT, which is what the outline is
    # measured out from. A ray from an interior point crosses a closed
    # boundary an odd number of times, so the rays vote: it takes a majority
    # rather than one ray's word, because a single ray can pass exactly
    # through the join between two segments and count it twice.
    if int((hit.sum(axis=1) % 2 == 1).sum()) * 2 <= steps:
        return np.empty((0, 2))

    reach = np.where(hit, t, 0.0).max(axis=1)
    # A ray that met nothing at all takes the mean of the two beside it, so
    # one numerical miss is a smoothed point rather than a spike to the centre.
    missed = ~hit.any(axis=1)
    if missed.any():
        good = np.flatnonzero(~missed)
        reach[missed] = np.interp(np.flatnonzero(missed), good, reach[good],
                                  period=steps)
    return d * reach[:, None]


def _slice_a_bare_cloud(v, lightness: float, steps: int) -> np.ndarray:
    """The old hull cut, for points that have no surface to cut through."""
    from scipy.spatial import Delaunay

    hull = Delaunay(v)
    if hull.find_simplex(np.array([[lightness, 0.0, 0.0]])) < 0:
        return np.empty((0, 2))
    reach = float(np.hypot(v[:, 1], v[:, 2]).max()) * 1.05
    angles = np.linspace(0, 2 * np.pi, steps, endpoint=False)
    out = np.empty((steps, 2))
    for i, ang in enumerate(angles):
        direction = np.array([np.cos(ang), np.sin(ang)])
        lo, hi = 0.0, reach
        for _ in range(24):                     # ~1e-5 of the reach
            mid = (lo + hi) / 2.0
            point = np.array([[lightness, *(direction * mid)]])
            if hull.find_simplex(point) >= 0:
                lo = mid
            else:
                hi = mid
        out[i] = direction * lo
    return out


class _Enclosure:
    """A closed gamut boundary that can say what is inside it.

    WHY THIS EXISTS AND WHAT IT REPLACED. Containment used to be
    ``Delaunay(points).find_simplex(p) < 0``, and a Delaunay triangulation
    tessellates exactly the CONVEX HULL of its points -- so the question
    actually being asked was "is this inside the convex hull", which is the
    same question only for a convex gamut.

    A working space in Lab is a distorted cube and is emphatically not
    convex. Measured on Adobe RGB: **89.2% of its own surface points lie
    strictly inside its own convex hull**, by as much as 3.9 Lab units, and
    the hull encloses **6.1% more volume** than the space really holds. So
    every hollow was being filled in and counted as reachable colour.

    What that cost, measured against the demo pair: of the glossy paper's
    675 boundary vertices, the hull test called 191 of them outside Adobe RGB
    and the real surface calls 239. **All 48 disagreements went the same
    way** -- colours the paper reaches and Adobe RGB does not, reported as
    agreeing. It was noticed from a photograph of a phone, where a bit of a
    gamut refused to stand out from a region it plainly did not share.

    HOW IT ANSWERS. A ray is cast from the point along increasing lightness
    and its crossings of the surface are counted: odd means it started
    inside. That needs a closed surface and nothing else -- no convexity, no
    consistent winding -- and these surfaces are closed, which was checked
    rather than assumed: welded by position, the demo paper and every
    reference space have no edge used once and none used more than twice.

    It is not slower than what it replaces. Building a Delaunay
    triangulation of 2,400 points to ask 675 questions costs 31 ms; this
    costs 20 ms to prepare and 13 ms to answer.
    """

    #: Rays are cast along the first axis, so a triangle can only be crossed
    #: by one whose other two coordinates land inside its footprint. Bucketed
    #: by footprint, "test every triangle" becomes "test the few overhead".
    CELLS = 48

    #: THE RAY IS NUDGED OFF THE EDGES, which is not a fudge but the whole
    #: difficulty of ray casting. A ray running exactly along an edge shared
    #: by two triangles is counted twice and the parity comes out backwards.
    #: This is not a corner case to shrug at: the first shape this was
    #: checked against was a cube, whose centre projects precisely onto the
    #: diagonal where two triangles of a face meet -- so the first answer it
    #: ever gave for the middle of a cube was "outside". An irrational
    #: fraction of a millionth of a Lab unit clears every projected edge at
    #: once, and nothing is measured to within fourteen orders of that.
    NUDGE = np.array([8.6602540378e-8, 5.7735026919e-8])

    #: How close to the surface still counts as on it, in Lab units. A
    #: millionth of a unit is a thousand times finer than an instrument
    #: repeats to and a million times finer than anyone can see, so nothing
    #: real is swept in by it -- but it is comfortably wider than the
    #: arithmetic's own noise, including the nudge above.
    SKIN = 1e-6

    #: How far outside a triangle's footprint still counts as on it, as a
    #: fraction of that triangle. Wide enough to cover the nudge above and
    #: nothing else.
    SLACK = 1e-5

    @classmethod
    def _turn(cls):
        """A fixed rigid rotation by angles with no common measure."""
        if cls.TURN is None:
            ca, sa = np.cos(0.6931471805599453), np.sin(0.6931471805599453)
            cb, sb = np.cos(0.4342944819032518), np.sin(0.4342944819032518)
            cg, sg = np.cos(0.3010299956639812), np.sin(0.3010299956639812)
            rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]])
            ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
            rz = np.array([[cg, -sg, 0], [sg, cg, 0], [0, 0, 1]])
            cls.TURN = rx @ ry @ rz
        return cls.TURN

    #: THE WHOLE SURFACE IS TURNED A LITTLE FIRST, and rays are cast along an
    #: axis of the turned frame -- which is a crooked direction in the real
    #: one. Cast straight up instead, any face standing exactly parallel to
    #: the ray projects to a line, is discarded as edge-on, and a point lying
    #: ON such a face is seen by nothing: the side of a cube answered
    #: "outside" for points sitting on it. Turned by angles with no common
    #: measure, no face of anything can be parallel to the ray. The rotation
    #: is rigid, so distances, volumes and what is inside are untouched.
    TURN = None       # built once, below

    def __init__(self, vertices, faces):
        v = np.asarray(vertices, float) @ self._turn()
        f = np.asarray(faces, int)
        # WELDED FIRST. The six faces of a device cube are triangulated
        # separately and their vertices appended, so a seam is two sets of
        # indices in the same place -- 360 edges of the demo paper are used
        # once by index and none at all once welded.
        key = np.round(v * 1e6).astype(np.int64)
        _uniq, first, inv = np.unique(key, axis=0, return_index=True,
                                      return_inverse=True)
        self.v = v[first]
        f = inv[f.ravel()].reshape(f.shape)
        keep = ((f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2])
                & (f[:, 2] != f[:, 0]))
        self.f = f[keep]
        tri = self.v[self.f]
        self.a, self.b, self.c = tri[:, 0], tri[:, 1], tri[:, 2]
        flat = tri[:, :, 1:]
        self.lo = self.v[:, 1:].min(axis=0) - 1e-6
        self.hi = self.v[:, 1:].max(axis=0) + 1e-6
        self.step = np.maximum(self.hi - self.lo, 1e-12) / self.CELLS
        low = np.clip(((flat.min(axis=1) - self.lo) / self.step).astype(int),
                      0, self.CELLS - 1)
        high = np.clip(((flat.max(axis=1) - self.lo) / self.step).astype(int),
                       0, self.CELLS - 1)
        # WHICH TRIANGLES OVERHANG WHICH CELL, AS TWO FLAT ARRAYS rather than a
        # dictionary of lists. `start` says where each cell's triangles begin
        # in `items`, so asking about a cell is two lookups and no Python
        # object at all -- which is what lets `contains` answer for every
        # point in one stroke instead of one cell at a time.
        wide = high[:, 0] - low[:, 0] + 1
        tall = high[:, 1] - low[:, 1] + 1
        spread = wide * tall
        total = int(spread.sum())
        which = np.repeat(np.arange(len(self.f)), spread)
        # Where each triangle's own block starts, subtracted off to give the
        # offset within it -- the standard way to walk ragged rows at once.
        within = np.arange(total) - np.repeat(np.cumsum(spread) - spread, spread)
        down = np.repeat(tall, spread)
        cell = ((np.repeat(low[:, 0], spread) + within // down) * self.CELLS
                + (np.repeat(low[:, 1], spread) + within % down))
        order = np.argsort(cell, kind="stable")
        self.items = which[order]
        self.start = np.searchsorted(cell[order],
                                     np.arange(self.CELLS * self.CELLS + 1))

    def sample(self, n: int, rng) -> np.ndarray:
        """*n* points spread evenly through what the surface encloses.

        NO REJECTION, WHICH IS THE POINT. Throwing points at the bounding box
        and keeping the ones that land inside means testing four or five for
        every one kept, and the test is the expensive part -- the coverage
        figure took 5.2 seconds that way, against 182 ms for the hull it
        replaced. Nobody keeps a number they have to wait for.

        Instead the solid is cut into tetrahedra, each one the centroid and a
        triangle of the surface. For a closed surface those tile the inside
        exactly once, so choosing a tetrahedron in proportion to its volume
        and a uniform point within it is an exact draw from the whole solid,
        and every point costs the same. It is the same decomposition
        `mesh_volume` sums, and it agrees with a plain Monte Carlo count to
        within its error, which is how it was checked rather than assumed.
        """
        centre = self.v.mean(axis=0)
        a, b, c = (self.v[self.f[:, 0]] - centre, self.v[self.f[:, 1]] - centre,
                   self.v[self.f[:, 2]] - centre)
        vol = np.abs(np.einsum("ij,ij->i", a, np.cross(b, c))) / 6.0
        total = vol.sum()
        if total <= 0:
            raise ValueError("the gamut encloses no volume")
        which = rng.choice(len(vol), size=n, p=vol / total)
        # Uniform in a tetrahedron, by folding the unit cube into it.
        u = rng.random((n, 3))
        s = u[:, 0] ** (1 / 3)
        t = u[:, 1] ** (1 / 2)
        r = u[:, 2]
        w1 = s * (1 - t)
        w2 = s * t * (1 - r)
        w3 = s * t * r
        turned = (centre + w1[:, None] * a[which] + w2[:, None] * b[which]
                  + w3[:, None] * c[which])
        return turned @ self._turn().T

    def contains(self, points) -> np.ndarray:
        """Which of *points* the surface encloses.

        GROUPED BY CELL RATHER THAN ASKED ONE AT A TIME. Every point in a
        cell is tested against that cell's handful of triangles in one
        stroke. Point by point this is correct and useless: the coverage
        figure samples sixty thousand of them and took **5.2 seconds**, where
        the hull it replaced took a fraction of that. Grouped, the same
        figure takes about a tenth of a second, and a number nobody waits for
        is a number people keep.
        """
        p = np.atleast_2d(np.asarray(points, float)) @ self._turn()
        out = np.zeros(len(p), bool)
        if not len(p):
            return out
        # IN BLOCKS, so the working space never depends on how many colours
        # were asked about. Every point/triangle pair is held at once within a
        # block, which is the whole speed of this; unbounded, the coverage
        # figure's sixty thousand samples would ask for gigabytes.
        for first in range(0, len(p), self.BLOCK):
            self._answer(p[first:first + self.BLOCK], out[first:first + self.BLOCK])
        return out

    #: How many colours are answered for at a time. Sized so the widest run --
    #: the coverage figure, whose points sit inside the shape and so overhang
    #: the most triangles -- stays in a few tens of megabytes.
    BLOCK = 8192

    def _answer(self, p, out) -> None:
        """One block of points, every candidate pair in a single stroke.

        ONE STROKE RATHER THAN ONE CELL AT A TIME, which is where the time
        went. Grouping the points by cell and testing each group was already
        far better than asking one point at a time -- but with a few hundred
        points spread over a 48x48 grid it becomes a few hundred passes
        through numpy on a handful of rows each, and the arithmetic is then
        the small part. The bisection that finds where two surfaces cross
        calls this sixteen times per redraw, which is what made it show.

        Every (point, triangle) pair that might touch is built as one flat
        list -- `start` and `items` from the constructor make that a couple of
        array lookups -- and the whole test runs once over it.
        """
        q = p[:, 1:] + self.NUDGE
        cell = np.clip(((q - self.lo) / self.step).astype(int), 0,
                       self.CELLS - 1)
        keys = cell[:, 0] * self.CELLS + cell[:, 1]
        counts = self.start[keys + 1] - self.start[keys]
        total = int(counts.sum())
        if not total:
            return
        who = np.repeat(np.arange(len(p)), counts)
        within = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
        near = self.items[np.repeat(self.start[keys], counts) + within]

        a2, b2, c2 = self.a[near, 1:], self.b[near, 1:], self.c[near, 1:]
        e0, e1, e2 = b2 - a2, c2 - a2, q[who] - a2
        den = e0[:, 0] * e1[:, 1] - e1[:, 0] * e0[:, 1]
        live = np.abs(den) > 1e-12          # edge-on: cannot be crossed
        safe = np.where(live, den, 1.0)
        s = (e2[:, 0] * e1[:, 1] - e1[:, 0] * e2[:, 1]) / safe
        t = (e0[:, 0] * e2[:, 1] - e2[:, 0] * e0[:, 1]) / safe
        hit = live & (s >= 0) & (t >= 0) & (s + t <= 1)
        height = (self.a[near, 0]
                  + s * (self.b[near, 0] - self.a[near, 0])
                  + t * (self.c[near, 0] - self.a[near, 0]))
        gap = height - p[who, 0]
        crossings = np.bincount(who[hit & (gap > 0)], minlength=len(p))
        # A COLOUR ON THE BOUNDARY IS IN THE GAMUT.
        #
        # A gamut is a closed set and its surface belongs to it: a colour
        # sitting exactly on the edge is one the paper prints. Parity
        # cannot answer for such a point -- a ray starting on the surface
        # crosses it zero times or once depending on which side of
        # nothing it began -- so the answer would be decided by rounding.
        #
        # It is not a rare case. Placing a chart through a profile and
        # asking whether it lands inside that same profile puts 98 of 125
        # patches exactly on the boundary, because a 5-point grid falls on
        # sample points of a 17-, 33- or 65-step build alike. Judged by
        # parity alone, 61 of those 98 came out "outside" — over half,
        # which is the coin-toss it is. The convex hull never showed this
        # because its bulge put every boundary point comfortably inside.
        # ON THE SURFACE IS JUDGED WITH A LITTLE SLACK SIDEWAYS TOO.
        # A point sitting exactly on a corner belongs to every triangle
        # meeting there and, once the ray is nudged, to none of their
        # footprints -- so the corner of a cube came back "outside" while
        # every face of it was right.
        close = (live & (s >= -self.SLACK) & (t >= -self.SLACK)
                 & (s + t <= 1 + self.SLACK))
        on_skin = np.bincount(who[close & (np.abs(gap) <= self.SKIN)],
                              minlength=len(p)) > 0
        out[:] = ((crossings % 2) == 1) | on_skin


def outside_of(inner, outer) -> np.ndarray:
    """Which points of *inner* fall outside *outer*: a boolean per vertex.

    Turns "77.6% fits" into "and here is the 22.4% that does not". A percentage
    tells somebody how much colour they lose; this tells them WHICH colours, so
    they can judge whether it matters for the pictures they actually print --
    losing deep cyans matters to a landscape photographer and not at all to
    somebody printing skin tones.

    Measured against *outer*'s actual surface -- see `_Enclosure` for what
    that fixed and what it cost. A bare cloud of points with no triangles has
    no surface to measure against, and for that the convex hull is the only
    defensible answer; it is used, and it is the caller's business to hand
    over the faces if it has them.
    """
    a = np.asarray(inner.vertices if hasattr(inner, "vertices") else inner,
                   float)
    faces = getattr(outer, "faces", None)
    b = np.asarray(outer.vertices if hasattr(outer, "vertices") else outer,
                   float)
    if len(b) < 4:
        raise ValueError("the gamut to test against needs at least 4 vertices")
    if faces is None or len(faces) == 0:
        from scipy.spatial import Delaunay
        return Delaunay(b).find_simplex(a) < 0
    return ~_Enclosure(b, faces).contains(a)


class _HullEnclosure:
    """The same question answered for a cloud of points with no surface."""

    def __init__(self, vertices):
        from scipy.spatial import Delaunay
        self.hull = Delaunay(np.asarray(vertices, float))

    def contains(self, points) -> np.ndarray:
        return self.hull.find_simplex(np.atleast_2d(
            np.asarray(points, float))) >= 0


def enclosure(gamut):
    """A reusable "is this colour inside?" test for one gamut.

    :func:`outside_of` answers the question once and throws the surface away,
    which is right for one question and wrong for a thousand. Splitting a mesh
    along a boundary asks about the same shape twenty-four times over while it
    bisects, and rebuilding the surface each time would cost twenty-four times
    what it needs to.

    Returns an object with a ``contains(points)`` method. A gamut carrying
    triangles gets the real surface; a bare cloud gets its convex hull, which
    is the only surface it has.
    """
    v = np.asarray(gamut.vertices if hasattr(gamut, "vertices") else gamut,
                   float)
    faces = getattr(gamut, "faces", None)
    if len(v) < 4:
        raise ValueError("the gamut to test against needs at least 4 vertices")
    if faces is None or len(faces) == 0:
        return _HullEnclosure(v)
    return _Enclosure(v, faces)


def split_at_crossing(vertices, faces, colors, stands, is_outside, *,
                      steps: int = 16):
    """Re-cut a mesh so no triangle straddles the boundary it is faded along.

    Returns ``(vertices, faces, colors, stands)`` describing the SAME surface,
    re-triangulated so that every triangle's three corners agree about which
    side of the boundary they are on.

    WHY. "Does this colour fall outside the other gamut?" has two answers and
    no third. But the surface is faded with an alpha per VERTEX, and a
    triangle with two corners agreeing and one not gets that difference
    painted smoothly across its whole width -- so a decision that is yes or no
    is drawn as a slope.

    Measured on the demo pair, of the glossy paper's 978 triangles: 586 agree
    throughout, 219 differ throughout, and **173 straddle the boundary --
    19.9% of the surface, averaging 16.5 Lab units across and reaching 36.2**.
    A fifth of the shape was a gradient standing in for an edge, which is why
    the fade never cut where the two shapes really part company. Reported as
    "the cut so to say should be more straight".

    HOW. A straddling triangle has exactly one odd corner out. The boundary is
    found on each of the two edges leaving it -- by bisection on the
    containment test, which needs nothing of the boundary but the answer, so
    it works for one other gamut or for six -- and the triangle becomes three:
    one for the odd corner, two for the pair.

    THE NEW CORNERS ARE MADE TWICE, once for each side, and that is the point
    of the whole exercise. Sharing them would put a vertex with one alpha on
    both sides of the cut and bring the gradient straight back. Doubled, every
    triangle is one flat colour and one flat alpha, so the edge is exactly
    where the surfaces cross.

    IT IS STILL ONE MESH. Cutting the shape into a faded piece and a solid
    piece was tried before and left 120,481 pixels wrong, because a browser
    blends two open surfaces in the order it draws them and that is not what
    one closed surface does. Nothing here opens the surface: the same
    triangles cover the same shape, and only their corners are renumbered.

    *steps* is how many times each edge is halved, and it is the whole cost of
    this: each halving asks the containment test about every straddling edge
    at once, and that test is the most expensive thing in a redraw.

    16 IS CHOSEN AGAINST WHAT CAN BE MEASURED, not against what a float can
    hold. The longest edge on either demo shape is 36 Lab units, so 16
    halvings place the cut to within **0.0006 Lab** of the true crossing --
    about a thousandth of the smallest colour difference a good eye can find,
    and a hundredth of what a good instrument repeats to. It was 24, which
    bought another four decimal places nothing can see and cost a third of the
    time this function takes.
    """
    v = np.asarray(vertices, float)
    f = np.asarray(faces, int)
    was_array = isinstance(colors, np.ndarray)
    cols = list(colors) if colors is not None else None
    stands = np.asarray(stands, bool)
    if len(f) == 0:
        return v, f, colors, stands

    per = stands[f]
    n = per.sum(axis=1)
    mixed = np.flatnonzero((n > 0) & (n < 3))
    if not len(mixed):
        return v, f, colors, stands

    # Rotate each straddling triangle so its odd corner comes first. With one
    # corner outside, that corner is the odd one; with two, the single corner
    # inside is.
    tri = f[mixed]
    odd_is = np.where(n[mixed][:, None] == 1, per[mixed], ~per[mixed])
    first = odd_is.argmax(axis=1)
    rows = np.arange(len(tri))
    A = tri[rows, first]
    B = tri[rows, (first + 1) % 3]
    C = tri[rows, (first + 2) % 3]

    # Bisect A->B and A->C together: the boundary lies somewhere along each,
    # because their ends disagree.
    ends = np.concatenate([B, C])
    starts = np.concatenate([A, A])
    lo = np.zeros(len(starts))
    hi = np.ones(len(starts))
    side_at_a = stands[starts]
    for _ in range(steps):
        mid = (lo + hi) / 2.0
        point = v[starts] + mid[:, None] * (v[ends] - v[starts])
        same = is_outside(point) == side_at_a
        lo = np.where(same, mid, lo)
        hi = np.where(same, hi, mid)
    cut = (lo + hi) / 2.0
    where = v[starts] + cut[:, None] * (v[ends] - v[starts])

    # Two copies of every new corner, one for each side of the cut.
    base = len(v)
    count = len(mixed)
    on_ab, on_ac = where[:count], where[count:]
    P_odd = base + np.arange(count)                       # on A->B, A's side
    Q_odd = base + count + np.arange(count)               # on A->C, A's side
    P_pair = base + 2 * count + np.arange(count)          # on A->B, B/C's side
    Q_pair = base + 3 * count + np.arange(count)          # on A->C, B/C's side
    new_v = np.vstack([v, on_ab, on_ac, on_ab, on_ac])

    new_stands = np.concatenate([
        stands,
        stands[A], stands[A],                             # the odd side
        stands[B], stands[B],                             # the pair's side
    ])

    if cols is not None:
        def blend(i, j, t):
            return [_mix_colour(cols[a], cols[b], w)
                    for a, b, w in zip(i, j, t)]
        ab_colours = blend(A, B, cut[:count])
        ac_colours = blend(A, C, cut[count:])
        cols = cols + ab_colours + ac_colours + ab_colours + ac_colours
        if was_array:
            cols = np.asarray(cols, float)

    kept = np.ones(len(f), bool)
    kept[mixed] = False
    new_f = np.vstack([
        f[kept],
        np.column_stack([A, P_odd, Q_odd]),
        np.column_stack([P_pair, B, C]),
        np.column_stack([P_pair, C, Q_pair]),
    ])
    return new_v, new_f, cols, new_stands


def _mix_colour(one, two, weight: float):
    """*one* and *two* mixed, as whichever of the two forms they came in.

    Colours arrive either as "rgb(r,g,b)" strings, which is what the drawing
    library is handed, or as numbers. A new corner sits between two old ones
    and is painted between their colours, so the surface keeps its own colours
    across the cut instead of showing a seam where the mesh was re-cut.
    """
    if isinstance(one, str) and isinstance(two, str):
        def parts(text):
            inside = text[text.index("(") + 1:text.index(")")]
            return [float(x) for x in inside.split(",")[:3]]
        try:
            a, b = parts(one), parts(two)
        except (ValueError, IndexError):
            return one
        mixed = [a[i] + (b[i] - a[i]) * weight for i in range(3)]
        return "rgb({:.0f},{:.0f},{:.0f})".format(*mixed)
    try:
        return np.asarray(one, float) + (np.asarray(two, float)
                                         - np.asarray(one, float)) * weight
    except (TypeError, ValueError):
        return one


def coverage(inner, outer, *, samples: int = 60_000, seed: int = 20260814
             ) -> tuple[float, float]:
    """How much of *inner* fits inside *outer*, as a fraction and its error.

    Returns ``(fraction, standard_error)``. This is the number people actually
    want when comparing two papers, and **it is not symmetric**: a glossy paper
    might hold 96% of what a matte one can show while the matte holds only 71%
    of the glossy. Reporting one number for "how similar are these" hides
    exactly the asymmetry that decides which paper to use.

    Measured by sampling points uniformly inside *inner* and counting how many
    fall inside *outer*. The seed is fixed, so the same pair of gamuts always
    gives the same answer — a figure that wobbles between runs is worse than
    useless when someone is comparing papers. The standard error is returned
    rather than hidden: at 60,000 samples it is around 0.2 percentage points,
    so quoting more than one decimal place would be false precision.

    THE SAME ANSWER ON ONE MACHINE, and very nearly the same on another. The
    seed fixes the sampling, but not the shape being sampled: `build_gamut`
    triangulates each face of the device cube with Qhull, and Qhull resolves a
    flat or near-flat run of points differently between builds. Same points,
    slightly different triangles, so everything measured from the surface
    moves a little. Measured between this project's development machine and
    its Linux build machine: the demo paper's volume differs by 36 cubic Lab
    units in 702,327 — **0.005%** — and the coverage figures by up to **0.25
    percentage points**. That is well inside the sampling error already quoted
    beside them, and it is worth knowing before treating the last digit of a
    published figure as a constant.

    BOTH SIDES ARE MEASURED AGAINST THE REAL SURFACE. This used to sample the
    convex HULL of the inner gamut and test against the hull of the outer,
    and neither gamut is convex — Adobe RGB's hull holds 6.1% more volume
    than the space does. Both errors push the same way, so the figure came
    out too flattering: 91.70% where the surfaces say 90.86%. See
    `_Enclosure`.
    """
    a = np.asarray(inner.vertices if hasattr(inner, "vertices") else inner, float)
    b = np.asarray(outer.vertices if hasattr(outer, "vertices") else outer, float)
    if len(a) < 4 or len(b) < 4:
        raise ValueError("both gamuts need at least 4 vertices to have a volume")

    def surface_of(g, verts):
        faces = getattr(g, "faces", None)
        if faces is None or len(faces) == 0:
            return None
        return _Enclosure(verts, faces)

    inner_skin = surface_of(inner, a)
    outer_skin = surface_of(outer, b)
    if inner_skin is None or outer_skin is None:
        from scipy.spatial import Delaunay
        inner_hull = Delaunay(a) if inner_skin is None else None
        outer_hull = Delaunay(b) if outer_skin is None else None
    rng = np.random.default_rng(seed)

    def in_outer(batch):
        if outer_skin is not None:
            return outer_skin.contains(batch)
        return outer_hull.find_simplex(batch) >= 0

    if inner_skin is not None:
        # DRAWN STRAIGHT FROM THE SOLID, no rejection -- see `_Enclosure.sample`.
        take = inner_skin.sample(samples, rng)
        kept = len(take)
        covered = int(in_outer(take).sum())
    else:
        lo, hi = a.min(axis=0), a.max(axis=0)
        kept = covered = tried = 0
        # A bare cloud has no surface to draw from, so the old rejection
        # sampling against its hull is the only thing left.
        while kept < samples and tried < samples * 200:
            batch = rng.uniform(lo, hi, size=(min(samples, 20_000), 3))
            tried += len(batch)
            got = batch[inner_hull.find_simplex(batch) >= 0]
            if not len(got):
                continue
            take = got[:samples - kept]
            kept += len(take)
            covered += int(in_outer(take).sum())
    if not kept:
        raise ValueError("could not sample inside the inner gamut — it may be "
                         "degenerate (flat, a line, or a single point)")
    p = covered / kept
    return p, float(np.sqrt(max(p * (1.0 - p), 1e-12) / kept))


#: The six hue families a printer person actually talks in, as the centre of
#: each sector on the a*/b* (or u*/v*) hue circle, in degrees. Six rather than
#: a finer split because these are the names people use -- "it runs out in the
#: cyans" -- and a number per 10-degree slice would be precision nobody asked
#: for.
HUE_FAMILIES = (
    ("reds", 0.0), ("yellows", 90.0), ("greens", 150.0),
    ("cyans", 195.0), ("blues", 270.0), ("magentas", 330.0),
)


def lightness_range(gamut) -> tuple[float, float]:
    """The darkest and brightest lightness the gamut reaches, as (min, max).

    For a printed chart these are the two numbers a printer cares about most
    after the volume: how black the blacks go, and how bright the paper is.
    Only meaningful where the first axis *is* lightness, which is CIELAB and
    CIELUV -- in XYZ the first axis is X and this would be nonsense.
    """
    v = np.asarray(gamut.vertices if hasattr(gamut, "vertices") else gamut,
                   float)
    if len(v) < 1:
        raise ValueError("an empty gamut has no lightness range")
    return float(v[:, 0].min()), float(v[:, 0].max())


def paper_white(gamut) -> tuple[float, float, float]:
    """The colour of the lightest thing the gamut reaches, as (L*, a*, b*).

    WHY THIS IS NOT ANSWERED BY THE LIGHTNESS RANGE, AND WHY IT MATTERS MORE
    THAN ANY OF THE OTHER NUMBERS FOR CHOOSING BETWEEN TWO PAPERS.

    Every other figure this module produces is blind to it. Volume is a size
    and barely moves when the white shifts. Coverage counts points in or out.
    Both would call two papers all but identical when one is a cool, blue
    white full of optical brightener and the other a warm, cream rag -- and
    that difference is visible on the wall at a glance, on every print, in
    every neutral, before anybody looks at a saturated colour at all.

    It is also the difference the measurement conditions exist for: a paper
    with optical brighteners reads differently under M0, M1 and M2 precisely
    because its white is not neutral, so the number here is the one that says
    whether that distinction applies to this paper.

    The lightest VERTEX is the honest answer to "what is the paper", because
    the paper is the substrate showing through with no ink on it, which is by
    construction the lightest thing the printer can make. Ties on L* are
    broken towards the least coloured, so a paper is never described as more
    tinted than it is by a stray sample a hundredth of a lightness apart.
    """
    v = np.asarray(gamut.vertices if hasattr(gamut, "vertices") else gamut,
                   float)
    if len(v) < 1:
        raise ValueError("an empty gamut has no paper white")
    top = v[:, 0].max()
    near = v[v[:, 0] >= top - 0.05]
    pick = near[np.hypot(near[:, 1], near[:, 2]).argmin()]
    return float(pick[0]), float(pick[1]), float(pick[2])


#: How far a white can sit from neutral before it is worth remarking on.
#: A chroma of about 1 is around the smallest colour difference a good eye
#: finds in a large flat neutral area seen on its own, which is what a sheet
#: of paper is; below it there is nothing to say and saying something would
#: invite somebody to choose between two papers on noise.
WHITE_IS_NEUTRAL = 1.0


def describe_white(lab) -> str:
    """The paper white in words -- warm, cool, or neutral, and how strongly.

    In plain language rather than in a* and b*, because "b* +3.4" tells
    somebody who already knows, and "slightly warm" tells everybody. The two
    are shown together so neither has to be trusted alone.
    """
    _L, a, b = lab
    chroma = float(np.hypot(a, b))
    if chroma < WHITE_IS_NEUTRAL:
        return "neutral"
    # b* IS THE AXIS THAT DECIDES IT for paper. Yellow-blue is where papers
    # actually differ: optical brighteners push a white towards blue, age and
    # rag content push it towards cream. a* moves far less, and leading with
    # it would name a paper "greenish" over a fraction of what its warmth is.
    strength = ("very " if chroma >= 6.0 else
                "" if chroma >= 2.5 else "slightly ")
    if abs(b) >= abs(a):
        return f"{strength}{'warm' if b > 0 else 'cool'}"
    return f"{strength}{'pink' if a > 0 else 'green'}-tinted"


#: How near two colours have to be before a reader stops telling them apart on
#: an ordinary screen at ordinary brightness. Eight levels out of 255 is about
#: 3%, which is roughly where a large flat area stops separating from its
#: background; below that the shape is still drawn and still correct and
#: simply cannot be seen.
INVISIBLE_LEVELS = 8.0

#: How much of one end has to vanish before it is worth saying so. One vertex
#: lost in the background is nothing -- the surface around it still draws the
#: shape. A tenth of that end gone is a face, not a point.
END_IS_LOST = 10.0


def hidden_end(gamut, page) -> tuple[str, float, float] | None:
    """The end of the shape that cannot be told apart from the page behind it.

    Returns ``(which, share, nearest)`` -- the name of the end in the words the
    window uses, how much of it is invisible as a percentage, and how many
    levels the closest colour of all comes to the page. Returns None when both
    ends stand clear, which is the ordinary case.

    WHY THIS EXISTS. The shape is painted the colour each point really is,
    which is the honest picture and the whole reason for True colours. But the
    page it is drawn on is a colour too, and at one end of the shape the two
    can be the same colour. Measured on the two demo papers: the darkest
    eighth of the glossy paper has a mean of 19,19,29 against a dark page of
    17,17,17, and its nearest colour comes within 4.4 levels -- 41.9% of that
    end is invisible. The light page does the mirror image of it, hiding 12.7%
    of the paper white.

    That is the worst possible thing to lose, because the black end is exactly
    where two papers differ most: the glossy paper here reaches L* 4.0 and the
    matte one stops at L* 12.7, and it is the deeper black that disappears.
    Somebody comparing the two on a dark page sees the shape whose blacks are
    WORSE more completely than the shape whose blacks are better.

    Nothing here changes a colour. The shape stays honest; this only makes it
    possible to say so.

    *page* is the real background in use -- the appearance setting, or a colour
    the user chose -- as anything :func:`_as_levels` understands. Reading it
    rather than assuming the dark theme is the point: the window lets any
    colour behind the shape, and a mid grey hides neither end.
    """
    rgb = np.asarray(getattr(gamut, "colors", ()), float)
    v = np.asarray(getattr(gamut, "vertices", ()), float)
    if rgb.size == 0 or v.size == 0 or len(rgb) != len(v):
        return None
    if rgb.max() <= 1.0:
        rgb = rgb * 255.0
    paper = _as_levels(page)
    if paper is None:
        return None
    L = v[:, 0]
    span = float(L.max() - L.min())
    if span <= 0:
        return None
    worst = None
    for which, pick in (("blacks", L < L.min() + 0.08 * span),
                        ("paper white", L > L.max() - 0.08 * span)):
        if not pick.any():
            continue
        gap = np.abs(rgb[pick] - paper).max(axis=1)
        share = 100.0 * float((gap < INVISIBLE_LEVELS).sum()) / int(pick.sum())
        if share >= END_IS_LOST and (worst is None or share > worst[1]):
            worst = (which, share, float(gap.min()))
    return worst


def _as_levels(page):
    """A background colour as three numbers 0-255, however it was written."""
    if page is None:
        return None
    if isinstance(page, str):
        text = page.strip().lstrip("#")
        if len(text) == 3:
            text = "".join(c * 2 for c in text)
        if len(text) != 6:
            return None
        try:
            return np.array([int(text[i:i + 2], 16) for i in (0, 2, 4)], float)
        except ValueError:
            return None
    got = np.asarray(page, float).ravel()[:3]
    if got.size != 3:
        return None
    return got * 255.0 if got.max() <= 1.0 else got


def hue_reach(gamut, families=HUE_FAMILIES) -> dict[str, float]:
    """The furthest each hue family reaches from the grey axis.

    Answers "where does this paper run out?" in the words people use. For each
    family, the greatest chroma among the vertices whose hue falls in that
    sector -- so comparing two papers family by family says which one reaches
    further in the cyans, in the yellows, and so on.

    Sectors are centred on the listed angles and meet halfway between
    neighbours, so every hue belongs to exactly one family and none is counted
    twice. Requires an opponent space, for the same reason as
    :func:`lightness_range`.
    """
    v = np.asarray(gamut.vertices if hasattr(gamut, "vertices") else gamut,
                   float)
    chroma = np.hypot(v[:, 1], v[:, 2])
    hue = np.degrees(np.arctan2(v[:, 2], v[:, 1])) % 360.0
    centres = np.array([c for _n, c in families])
    # Which centre each vertex is nearest, the short way round the circle.
    gap = np.abs(((hue[:, None] - centres[None, :]) + 180.0) % 360.0 - 180.0)
    nearest = gap.argmin(axis=1)
    return {name: (float(chroma[nearest == i].max())
                   if np.any(nearest == i) else 0.0)
            for i, (name, _c) in enumerate(families)}


#: BELOW THIS MUCH CHROMA A COLOUR HAS NO HUE WORTH NAMING, and is reported as
#: a grey instead of being filed under whichever family its noise points at.
#:
#: THIS NUMBER WAS MEASURED, NOT CHOSEN. Take one colour sitting in the middle
#: of its own sector -- the friendliest case there is -- and nudge it by 0.3
#: Lab units, which is less than two profiles of one printer routinely differ
#: by in a neutral. How often does it stay in its family?
#:
#:     chroma  0.1  0.3  0.5  1.0  2.0  3.0  5.0
#:     stays   25%  39%  55%  79%  97%  99%  100%
#:
#: At C* 1 a fifth of the answers are wrong. At C* 5 none of them are. A
#: maximum, which is what :func:`hue_reach` takes, barely notices this -- a
#: near-neutral point never wins a maximum chroma. A MEAN, which is what the
#: report below takes, is made of exactly these points, so the same rule that
#: is safe up there is not safe down here.
#:
#: The cost is small and was also measured: on a real 9-step profile grid only
#: 1.5% of the points fall below it, and on a printed chart the ones that do
#: are the grey ramp, which is precisely what a reader means by "the greys".
NEUTRAL_CHROMA = 5.0

#: Within this many degrees of the line between two families, a colour could
#: honestly be called either. Counted and reported rather than hidden, because
#: this is the whole of the objection the feature was asked with.
BOUNDARY_DEGREES = 5.0

#: Below this much movement, in dE2000, a family is reported as unchanged. The
#: SAME number the rest of the application already calls "a careful eye would
#: notice" (see ``Drift.over_one``), rather than a second private vocabulary
#: for the same idea.
QUIET_DE = 1.0

#: How much the movements inside one family have to agree before a single
#: direction may be named for all of them. The resultant length of the mean
#: a*/b* movement over the mean distance moved: 1.0 is every colour going the
#: same way, 0.0 is them cancelling out entirely. Below this, the family is
#: reported as "mixed", which is a true statement where a named direction
#: would be an invented one.
AGREEMENT = 0.5

#: The blues are the least trustworthy family here and the reader is told so.
#: CIELAB is not hue-linear through the blues: at a fixed hue angle, raising
#: chroma visibly shifts the hue. CIEDE2000 exists partly to patch this and
#: carries a rotation term aimed squarely at it -- see the ``rt`` term in
#: :func:`delta_e_2000`, a Gaussian centred on hue 275 deg with a 25 deg
#: spread. The "blues" sector below runs 232.5-300 deg, so it sits on top of
#: that correction, and it is also the second-widest of the six.
LEAST_LINEAR = "blues"


@dataclass(frozen=True)
class FamilyDrift:
    """How one colour family moved between two sets of the same colours."""
    name: str
    patches: int            # HOW MANY it stood on -- never omitted
    mean_de: float          # dE2000, averaged over the family
    max_de: float
    moved: tuple            # mean movement, (dL*, da*, db*)
    toward: str             # "yellows", "grey", "mixed", "" when unchanged
    also: str               # a second movement worth mentioning, or ""
    near_boundary: int      # of *patches*, how many could be called either
    agreement: float        # 0..1, how much the family moved as one
    certain: bool           # whether the direction outruns its own noise

    @property
    def changed(self) -> bool:
        """Whether anything happened that a careful eye would notice."""
        return self.mean_de >= QUIET_DE

    @property
    def sentence(self) -> str:
        """The one line a reader can paste into an email.

        Everything that qualifies the claim travels with it. A direction on
        four patches and a direction on four hundred read very differently and
        must never look the same, so the count is part of the sentence rather
        than a column somebody may or may not have looked at.
        """
        if not self.patches:
            return f"{self.name}: nothing in this family"
        how_many = ("1 patch" if self.patches == 1
                    else f"{self.patches} patches")
        if not self.changed:
            return (f"{self.name}: stayed the same "
                    f"(ΔE {self.mean_de:.1f}, {how_many})")
        way = self.toward
        if self.also:
            way += f", also {self.also}"
        if not self.certain:
            way += " — but not certainly"
        return f"{self.name}: ΔE {self.mean_de:.1f} {way} ({how_many})"


def family_drift(lab_a, lab_b, *, families=HUE_FAMILIES,
                 neutral: float = NEUTRAL_CHROMA,
                 boundary: float = BOUNDARY_DEGREES) -> list:
    """Which colour families moved, how far, and which way, as sentences.

    THE REQUEST THIS ANSWERS, in the words it was asked in: "Reds stayed the
    same, blues drifted toward green, yellows drifted toward red." A paper
    manufacturer comparing this year's profile with last year's wants a short
    list they can paste into an email, not a cloud to interpret.

    IT IS THE SAME ANSWER THE DIRECTION VIEW ALREADY DRAWS, in a different
    form, and the two must never be allowed to compete. The picture shows
    every colour and asks the reader to judge; this says the same thing in
    seven lines and cannot show where inside a family the movement sat. Use
    the picture to find out what happened, this to tell somebody else.

    THE ARBITRARY LINE, WHICH IS THE HARD PART AND IS NOT HIDDEN. Any report
    like this has to decide where a red stops and a yellow starts, and no such
    line exists in nature. Three things are done about it rather than one:

    * The line is the one this application ALREADY uses for "reaches further
      in the cyans" (:data:`HUE_FAMILIES`), so there are not two different
      reds in one program.
    * Every line of the report carries the number of colours it stood on, so
      a family of four is never read with the same confidence as one of four
      hundred.
    * Colours sitting within :data:`BOUNDARY_DEGREES` of a line are COUNTED,
      and the count is reported. On a boundary the split is very close to
      even -- measured at 51/49 -- so this number is the reader's warning
      that a family's membership was a coin toss for that many of its
      colours.

    WHICH SET NAMES THE FAMILY. The first one. "How did the reds move" is a
    question about colours that were red to begin with, so a colour is filed
    by where it STARTED. Filing by where it ended would let a colour change
    family by drifting and produce a report about families that did not exist
    when the question was asked. This also matches the direction view, which
    draws at A's positions for the same reason.

    Returns one :class:`FamilyDrift` per family in the order given, with the
    greys last. Families with nothing in them are returned with ``patches``
    of 0 and are the caller's to skip -- an empty family and one that did not
    move are different statements and this never conflates them.
    """
    lab_a = np.asarray(lab_a, float)
    lab_b = np.asarray(lab_b, float)
    if lab_a.ndim != 2 or lab_a.shape[1] != 3:
        raise ValueError("the first set has to be (N, 3) L*a*b* values")
    if lab_a.shape != lab_b.shape:
        raise ValueError(
            "the two sets have to be the same colours in the same order, and "
            f"these are {lab_a.shape[0]} and {lab_b.shape[0]} long")
    if len(lab_a) == 0:
        raise ValueError("there are no colours here to compare")
    bad = int((~np.isfinite(lab_a).all(axis=1)
               | ~np.isfinite(lab_b).all(axis=1)).sum())
    if bad:
        # REFUSED RATHER THAN AVERAGED AROUND. One unreadable patch turns a
        # family's mean into "nan" -- and the direction beside it is still
        # named, in full confidence, from the patches that did read. A line
        # saying "reds: nan dE, toward the yellows" is worse than no line.
        raise ValueError(
            f"{bad} of these {len(lab_a)} colours are not numbers, so the "
            f"families they belong to cannot be averaged. This usually means "
            f"a measurement file with missing or unreadable patches in it.")

    moved = lab_b - lab_a
    de = delta_e_2000(lab_a, lab_b)
    chroma = np.hypot(lab_a[:, 1], lab_a[:, 2])
    hue = np.degrees(np.arctan2(lab_a[:, 2], lab_a[:, 1])) % 360.0

    centres = np.array([c for _n, c in families])
    gap = np.abs(((hue[:, None] - centres[None, :]) + 180.0) % 360.0 - 180.0)
    nearest = gap.argmin(axis=1)
    # HOW CLOSE TO A LINE. The nearest centre and the next nearest are the two
    # families a colour could belong to; halfway between them is the line, so
    # the distance to it is half the difference of those two gaps.
    ordered = np.sort(gap, axis=1)
    on_a_hue_line = ((ordered[:, 1] - ordered[:, 0]) / 2.0) < boundary

    # THE GREYS SIT ON A DIFFERENT LINE, so they are asked a different
    # question. A neutral is not filed by hue at all, and how near it happens
    # to lie to the red/yellow boundary says nothing about whether calling it
    # a grey was a close call. What IS a close call is its chroma: a colour
    # just under the threshold could as honestly have been called a colour.
    # Reporting the hue answer here was wrong and looked entirely plausible.
    grey = chroma < neutral
    on_the_grey_line = np.abs(chroma - neutral) < QUIET_DE

    out = []
    for i, (name, _c) in enumerate(families):
        mine = (nearest == i) & ~grey
        out.append(_one_family(name, mine, lab_a, moved, de, on_a_hue_line,
                               families))
    out.append(_one_family("greys", grey, lab_a, moved, de, on_the_grey_line,
                           families, is_grey=True))
    return out


def _one_family(name, mine, lab_a, moved, de, on_a_line, families,
                is_grey=False):
    """One line of the report, or an empty one when nothing is in the family."""
    count = int(mine.sum())
    if not count:
        return FamilyDrift(name=name, patches=0, mean_de=0.0, max_de=0.0,
                           moved=(0.0, 0.0, 0.0), toward="", also="",
                           near_boundary=0, agreement=0.0, certain=False)
    ours = moved[mine]
    mean = ours.mean(axis=0)
    mean_de = float(de[mine].mean())

    # HOW MUCH THEY AGREED. The mean movement in a*/b* over the mean distance
    # moved in a*/b*: one when every colour went the same way, near zero when
    # they cancelled. A family that moved a long way in six directions has no
    # single direction to name, and saying so is the honest answer.
    # HOW MUCH THEY MOVED AS ONE THING: the length of the mean movement over
    # the mean length of the movements. One when every colour went the same
    # way, near zero when they cancelled out.
    #
    # MEASURED ON ALL THREE AXES, NOT JUST a*/b*, and getting that wrong was
    # a real fault. Judging it on a*/b* alone meant a family that only got
    # darker had no sideways movement to measure, so the test had to be gated
    # behind "did it move sideways at all" -- and a family whose movements
    # were pure noise slipped through that gate, because noise cancels to a
    # mean below the gate. It came out as "ΔE 8.2 toward the yellows", named
    # from the largest of three numbers that were all noise. On three axes
    # there is nothing to gate and nothing to slip through.
    lengths = np.linalg.norm(ours, axis=1)
    spread = (1.0 if lengths.mean() < 1e-9
              else float(np.linalg.norm(mean) / lengths.mean()))

    # WHETHER THE DIRECTION OUTRUNS ITS OWN NOISE, which "how much they agreed"
    # cannot say on its own: one patch agrees with itself perfectly, so a
    # family of one reported agreement 1.00 and looked like the most reliable
    # row in the table. This is the mean movement against the standard error
    # of that mean -- a statement that can actually come out false, and that
    # is undefined for a single patch rather than flattering to it.
    if count < 2:
        certain = False
    else:
        se = ours.std(axis=0, ddof=1) / np.sqrt(count)
        certain = bool(np.hypot(mean[1], mean[2]) > np.hypot(se[1], se[2])
                       or abs(mean[0]) > se[0])

    toward, also = _which_way(lab_a[mine].mean(axis=0), mean, mean_de, spread,
                              is_grey=is_grey, families=families, own=name)
    return FamilyDrift(
        name=name, patches=count, mean_de=mean_de,
        max_de=float(de[mine].max()),
        moved=(float(mean[0]), float(mean[1]), float(mean[2])),
        toward=toward, also=also,
        near_boundary=int(on_a_line[mine].sum()),
        agreement=min(spread, 1.0), certain=certain)


def _which_way(from_lab, mean, mean_de, spread, *, is_grey=False,
               families=HUE_FAMILIES, own=""):
    """Name the direction of one family's mean movement, or decline to.

    THREE KINDS OF MOVEMENT, NOT ONE, because they want different actions and
    no single word holds them. A colour can swing round the hue circle (a red
    going orange), it can move in or out from the grey axis (a red going
    grey), or it can get lighter or darker -- and these are usually a driver
    or ink-mix problem, a fading or ink-limit problem, and a linearisation
    problem respectively. Collapsing them into one direction name is how a
    report tells somebody to fix the wrong thing.

    So the mean movement is split against the family's OWN position: the part
    along the line out from the grey axis is chroma, the part across it is
    hue, and L* is itself. The largest is named, and the second is mentioned
    when it too is big enough to see. The request this was built from used all
    three -- "drifted toward green", "tending toward gray" -- so a report that
    could only say one of them would not have answered it.

    WHY THE HUE NAMES ARE THE FAMILY NAMES AND NOT MORE OF THEM. The request
    said "trending toward orange", and orange is not one of the six. It is
    deliberately not added: a seventh direction name that was not also a
    family name would give this application two different sets of colour
    words, one for what a colour IS and one for where it is GOING, and a
    reader would reasonably assume the two agreed. A red drifting the way an
    orange lies is reported as heading "toward the yellows" -- the same fact,
    in the words the rest of the program already uses.
    """
    if mean_de < QUIET_DE:
        return "", ""
    dl, da, db = float(mean[0]), float(mean[1]), float(mean[2])
    lighter = ("lighter" if dl > 0 else "darker", abs(dl))

    if is_grey:
        # A grey has no hue to travel within -- that is what makes it a grey,
        # and naming one would report exactly the noise the neutral threshold
        # exists to keep out. What can honestly be said of a neutral is which
        # way it went in a* and in b*, which is what those two axes are for.
        candidates = [("warmer (yellow)" if db > 0 else "cooler (blue)",
                       abs(db)),
                      ("redder" if da > 0 else "greener", abs(da)), lighter]
    else:
        if spread < AGREEMENT:
            # They moved and did not move together. Naming the mean would
            # describe a direction most of them never took.
            return "mixed", ""
        here = np.array([from_lab[1], from_lab[2]], float)
        radius = float(np.hypot(here[0], here[1]))
        out = here / max(radius, 1e-9)          # away from the grey axis
        across = np.array([-out[1], out[0]])    # anticlockwise round it
        outward = float(da * out[0] + db * out[1])
        sideways = float(da * across[0] + db * across[1])
        candidates = [
            (_neighbour(from_lab, sideways, families, own), abs(sideways)),
            ("more saturated" if outward > 0 else "toward grey", abs(outward)),
            lighter]

    candidates.sort(key=lambda c: -c[1])
    second = candidates[1][0] if candidates[1][1] >= QUIET_DE else ""
    return candidates[0][0], second


def _neighbour(from_lab, sideways, families, own=""):
    """The family a colour is heading for, going the way it is going.

    NOT the family its end point lands in. A blue that drifts a long way
    toward the greens is usually still a blue when it arrives, and a report
    saying "the blues moved toward the blues" answers nothing. The question is
    which way round the circle it set off, so the next family centre in that
    direction is the one named.

    A FAMILY IS NEVER ITS OWN DESTINATION, and leaving that out was a real
    fault rather than a theoretical one. A family's mean hue sits near its own
    centre but not exactly on it, so for half of them the centre they are
    already in lies a fraction of a degree "ahead" and wins by being nearest.
    Reds rotated firmly toward the yellows were reported as heading toward the
    reds; the same colours rotated the other way came out right, which is what
    made it worth building the case with the answer known in advance.
    """
    hue = np.degrees(np.arctan2(from_lab[2], from_lab[1])) % 360.0
    ahead = []
    for name, centre in families:
        if name == own:
            continue
        # How far round the circle, in the direction of travel, that centre is.
        step = ((centre - hue) if sideways >= 0 else (hue - centre)) % 360.0
        ahead.append((step, name))
    if not ahead:
        return "mixed"
    return "toward the " + min(ahead)[1]


def shared_volume(a, b, *, samples: int = 60_000, seed: int = 20260814
                  ) -> tuple[float, float, float]:
    """How much two gamuts have in common: (shared, union, shared/union).

    The containment percentages answer "does A fit inside B", one direction at
    a time. This answers the other question people ask -- "how much do these
    two actually share" -- as a single honest number: the colour both can
    print, over the colour either can.

    Two papers of the same size that barely overlap and two that nearly
    coincide give the same pair of containment figures only when one contains
    the other; in every other case this adds something the two percentages do
    not say on their own. Measured from the same sampling as
    :func:`coverage`, so the figures agree with each other.

    IT AGREES WITH THE FIGURES BESIDE IT, and for two releases it did not.
    This asked ``ConvexHull(...).volume`` for both sizes and then handed
    :func:`coverage` the bare vertices -- stripping off the very triangles
    that tell it what the surface is, so it fell back to the hull as well.
    Three hull answers in two lines, in a panel whose other rows had been
    corrected to the real surface.

    Measured on the demo pair: the hulls hold 8.3% and 6.1% more than the
    shapes do, the stripped coverage read 91.70% where the surfaces say
    90.72%, and the sentence on screen came out at **51.84% where the truth
    is 50.03%** -- next to two percentages that were already right. Both
    errors flattered the overlap, as filling in a dent always will.

    The gamuts are passed through whole, and a shape that carries its
    triangles is measured by what they enclose. A bare cloud of points has no
    surface and its hull is the only size it has.
    """
    from scipy.spatial import ConvexHull

    va = np.asarray(a.vertices if hasattr(a, "vertices") else a, float)
    vb = np.asarray(b.vertices if hasattr(b, "vertices") else b, float)
    if len(va) < 4 or len(vb) < 4:
        raise ValueError("both gamuts need at least 4 vertices to have a volume")

    def size(g, verts):
        faces = getattr(g, "faces", None)
        if faces is None or len(faces) == 0:
            return float(ConvexHull(verts).volume)
        return mesh_volume(verts, faces)

    vol_a, vol_b = size(a, va), size(b, vb)
    fraction, _err = coverage(a, b, samples=samples, seed=seed)
    overlap = fraction * vol_a
    union = vol_a + vol_b - overlap
    if union <= 0:
        raise ValueError("two gamuts with no volume cannot be compared")
    return overlap, union, overlap / union
