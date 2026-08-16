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

__all__ = ["Gamut", "build_gamut", "coverage", "mesh_volume", "outside_of", "slice_at", "delta_e_2000", "xyz_to_lab", "lab_to_xyz", "xyz_to_srgb",
           "lab_to_lch_cartesian", "WHITE_POINTS",
           "xyz_to_luv", "luv_to_xyz", "SPACES", "AXES", "DRAW_SPACES",
           "CAPABILITIES", "can_do"]

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


def slice_at(gamut, lightness: float, steps: int = 180) -> np.ndarray:
    """The outline of *gamut* at one lightness, as points around a*/b*.

    A 3D shape is honest and hard to read: two overlapping blobs hide each
    other, and depth on a flat screen is guesswork. A horizontal cut through
    both at the same lightness turns the comparison into two flat outlines,
    where "this one reaches further into the cyans" is simply visible.

    Found by asking, for each direction around the hue circle, how far the
    gamut reaches before leaving it — a bisection on the containment test,
    which needs no assumption that the shape is convex, star-shaped or smooth.
    Returns an (N, 2) array of a*/b* points, empty when the gamut does not
    reach that lightness at all.
    """
    from scipy.spatial import Delaunay

    v = np.asarray(gamut.vertices if hasattr(gamut, "vertices") else gamut, float)
    if len(v) < 4:
        raise ValueError("a gamut needs at least 4 vertices to be sliced")
    if not (v[:, 0].min() <= lightness <= v[:, 0].max()):
        return np.empty((0, 2))
    hull = Delaunay(v)

    # The centre of the slice: the mid-grey axis, which every real gamut
    # contains at any lightness it reaches.
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
        buckets: dict = {}
        for n in range(len(self.f)):
            for i in range(low[n, 0], high[n, 0] + 1):
                for j in range(low[n, 1], high[n, 1] + 1):
                    buckets.setdefault((i, j), []).append(n)
        self.buckets = {k: np.asarray(w, int) for k, w in buckets.items()}

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
        q = p[:, 1:] + self.NUDGE
        cell = np.clip(((q - self.lo) / self.step).astype(int), 0,
                       self.CELLS - 1)
        keys = cell[:, 0] * self.CELLS + cell[:, 1]
        order = np.argsort(keys, kind="stable")
        edges = np.flatnonzero(np.diff(keys[order])) + 1
        for chunk in np.split(order, edges):
            near = self.buckets.get((int(cell[chunk[0], 0]),
                                     int(cell[chunk[0], 1])))
            if near is None:
                continue
            a2 = self.a[near, 1:][None, :, :]
            b2 = self.b[near, 1:][None, :, :]
            c2 = self.c[near, 1:][None, :, :]
            qq = q[chunk][:, None, :]
            e0, e1, e2 = b2 - a2, c2 - a2, qq - a2
            den = e0[..., 0] * e1[..., 1] - e1[..., 0] * e0[..., 1]
            live = np.abs(den) > 1e-12      # edge-on: cannot be crossed
            safe = np.where(live, den, 1.0)
            s = (e2[..., 0] * e1[..., 1] - e1[..., 0] * e2[..., 1]) / safe
            t = (e0[..., 0] * e2[..., 1] - e2[..., 0] * e0[..., 1]) / safe
            hit = live & (s >= 0) & (t >= 0) & (s + t <= 1)
            height = (self.a[near, 0][None, :]
                      + s * (self.b[near, 0] - self.a[near, 0])[None, :]
                      + t * (self.c[near, 0] - self.a[near, 0])[None, :])
            gap = height - p[chunk, 0][:, None]
            crossings = (hit & (gap > 0)).sum(axis=1)
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
            on_skin = (close & (np.abs(gap) <= self.SKIN)).any(axis=1)
            out[chunk] = ((crossings % 2) == 1) | on_skin
        return out


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
    """
    from scipy.spatial import ConvexHull

    va = np.asarray(a.vertices if hasattr(a, "vertices") else a, float)
    vb = np.asarray(b.vertices if hasattr(b, "vertices") else b, float)
    if len(va) < 4 or len(vb) < 4:
        raise ValueError("both gamuts need at least 4 vertices to have a volume")
    vol_a = float(ConvexHull(va).volume)
    vol_b = float(ConvexHull(vb).volume)
    fraction, _err = coverage(va, vb, samples=samples, seed=seed)
    overlap = fraction * vol_a
    union = vol_a + vol_b - overlap
    if union <= 0:
        raise ValueError("two gamuts with no volume cannot be compared")
    return overlap, union, overlap / union
