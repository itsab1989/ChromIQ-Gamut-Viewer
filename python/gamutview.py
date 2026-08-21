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

    # WOUND ONE WAY BEFORE IT LEAVES. `ConvexHull.simplices` come back
    # unoriented -- measured, this paper's 414 triangles are 207 one way and
    # 207 the other, and the six faces of the device cube are triangulated
    # independently so they disagree too. The page's own far-wall sort reads
    # each triangle's cross product to decide which faces are the back of the
    # shell (`_ORDER_JS`), and on a half-and-half mesh half of them land in
    # the wrong group: 28,861 pixels of blotchy mottling across two
    # see-through shapes. It corrects ONE global sign, which cannot fix a mesh
    # that disagrees with itself. 1.4 ms here for the paper, 62 ms for the
    # densest reference, and only once when the shape is built.
    faces = face_the_same_way(faces, verts)
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


def weld_by_position(vertices, faces, *, places=7):
    """The same mesh with corners in the same place counted as one corner.

    ⚠ EVERY MEASUREMENT OF A CUT MESH'S BOUNDARY NEEDS THIS FIRST, and not
    knowing it cost a day. `split_at_crossing` below makes each crossing point
    FOUR times — twice for the odd corner's side of a straddling triangle and
    twice for the pair's — and welds none of them. Nothing is wrong with the
    picture: coincident corners draw identically. But the mesh is full of
    cracks, and a crack looks exactly like a boundary.

    Measured on a real paper cut against sRGB, the standing piece:

        as the cut leaves it   354 boundary edges over 290 corners,
                               and corners where 4, 6, 8, 10, 12 and even
                               SIXTEEN edges meet — which no rim can have
        welded by position     118 edges over 118 corners, every one of them
                               with exactly two edges: one closed loop

    So two thirds of what looked like the rim was cracks between copies of
    one place, and every number taken from it was about the cracks.

    Returns (vertices, faces, where_each_went) — the kept corners, the faces
    renumbered onto them, and for each original corner the index it welded to.
    """
    import numpy as np

    v = np.asarray(vertices, float)
    f = np.asarray(faces, int)
    kept, where = np.unique(np.round(v, places), axis=0, return_inverse=True)
    return kept, where[f] if len(f) else f.reshape(0, 3), where


def boundary_loops(faces):
    """The mesh's boundary, walked into chains, as lists of corners.

    An edge used by one triangle is a boundary edge; an edge used by two is
    inside. On a welded mesh every boundary corner has exactly two boundary
    edges and the chains close. On an unwelded one they do not, which is the
    quickest way to notice that welding was forgotten.
    """
    import numpy as np

    f = np.asarray(faces, int)
    seen: dict = {}
    for tri in f:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (min(int(a), int(b)), max(int(a), int(b)))
            seen[key] = seen.get(key, 0) + 1
    border = [k for k, n in seen.items() if n == 1]
    beside: dict = {}
    for a, b in border:
        beside.setdefault(a, []).append(b)
        beside.setdefault(b, []).append(a)
    left = {(min(a, b), max(a, b)) for a, b in border}
    loops = []
    while left:
        a, b = next(iter(left))
        chain = [a, b]
        left.discard((min(a, b), max(a, b)))
        while True:
            here = chain[-1]
            step = [w for w in beside.get(here, [])
                    if (min(here, w), max(here, w)) in left]
            if not step:
                break
            nxt = step[0]
            left.discard((min(here, nxt), max(here, nxt)))
            chain.append(nxt)
            if nxt == chain[0]:
                break
        loops.append(chain)
    return loops


def covers_the_sphere_once(vertices, faces, centre):
    """How much of the view from *centre* this mesh covers: 4π means once.

    WHY IT IS WORTH ASKING. A shape seen from a point inside it is a height
    field — one distance for each direction — and two such shapes can be cut
    against each other along their rays, with no matching of one mesh's
    corners to the other's. That is what makes closing an open shell exact
    rather than approximate. It holds for every gamut this application draws
    (measured: 4π to six figures for sRGB, Adobe RGB, Display P3, ProPhoto,
    Rec.2020 and the demo papers) — but it is a MEASURED PROPERTY, not a fact
    about meshes, and a shape dented enough to hide part of itself from the
    centre would break it silently.

    Returns the total solid angle. Compare it with 4π (12.566371) before
    relying on rays.
    """
    import numpy as np

    v = np.asarray(vertices, float) - np.asarray(centre, float)
    f = np.asarray(faces, int)
    if not len(f):
        return 0.0
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    la = np.linalg.norm(a, axis=1)
    lb = np.linalg.norm(b, axis=1)
    lc = np.linalg.norm(c, axis=1)
    top = np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)))
    bottom = (la * lb * lc
              + np.einsum("ij,ij->i", a, b) * lc
              + np.einsum("ij,ij->i", b, c) * la
              + np.einsum("ij,ij->i", c, a) * lb)
    return float(np.abs(2.0 * np.arctan2(top, bottom)).sum())


def face_the_same_way(faces, vertices=None, centre=None):
    """Wind every triangle the same way round, so the skin has one outside.

    WHY IT IS WORTH DOING. A triangle's front is decided by the order of its
    three corners, and that order is what a renderer turns into the normal it
    lights the facet by. Nothing upstream promises the order agrees between
    neighbours: a convex hull hands back triangles wound however each one fell
    out, and a grid split into pairs can alternate. MEASURED on this app's own
    shapes: the paper's 414 triangles are 207 one way and 207 the other, and
    sRGB's 6348 are 3174 and 3174 — an exact half-and-half, which is the
    signature of nobody ever having asked. Two things go wrong. The volume of
    a closed shape is a sum of signed pieces, so half of them subtract and the
    total collapses (the paper's came out at 35,662 against a true 765,392).
    And facet lighting turns half the skin's normals inward.

    HOW. Neighbours agree when the edge they share is walked in OPPOSITE
    directions by the two of them, exactly as two adjacent tiles of a fabric
    are stitched. So: pick a triangle, walk the mesh by shared edges, and flip
    whoever disagrees. Each connected piece is settled on its own, then turned
    outward — away from *centre* if one is given, otherwise by whichever way
    makes the piece enclose a positive volume. An edge shared by more than two
    triangles has no single answer; those are left alone rather than guessed.
    """
    import numpy as np

    f = np.asarray(faces, int).copy()
    if not len(f):
        return f
    beside: dict = {}
    for i, tri in enumerate(f):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            beside.setdefault((min(int(a), int(b)), max(int(a), int(b))), []).append(i)
    settled = np.zeros(len(f), bool)
    pieces = []
    for start in range(len(f)):
        if settled[start]:
            continue
        settled[start] = True
        piece = [start]
        queue = [start]
        while queue:
            here = queue.pop()
            tri = f[here]
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                key = (min(int(a), int(b)), max(int(a), int(b)))
                touching = beside.get(key, ())
                if len(touching) != 2:
                    continue  # a border, or a seam too crowded to be sure of
                other = touching[0] if touching[1] == here else touching[1]
                if settled[other]:
                    continue
                them = f[other]
                walks = [(them[0], them[1]), (them[1], them[2]), (them[2], them[0])]
                if (int(a), int(b)) in [(int(x), int(y)) for x, y in walks]:
                    f[other] = them[::-1]  # walked the shared edge the same way
                settled[other] = True
                piece.append(other)
                queue.append(other)
        pieces.append(piece)
    if vertices is None:
        return f
    v = np.asarray(vertices, float)
    from_here = np.asarray(centre, float) if centre is not None else v.mean(axis=0)
    for piece in pieces:
        mine = f[piece]
        a = v[mine[:, 0]] - from_here
        b = v[mine[:, 1]] - from_here
        c = v[mine[:, 2]] - from_here
        if np.einsum("ij,ij->i", a, np.cross(b, c)).sum() < 0:
            f[piece] = mine[:, ::-1]
    return f


def _rays_onto(vertices, faces, centre, *, rows=24, cols=48):
    """A caster that only tries the triangles a ray could possibly meet.

    WHY. Asking every triangle about every ray is fine once and ruinous in a
    loop: capping one cut calls it for every corner, again for every round of
    splitting and again for every smoothing pass, and it is linear in the
    other shape's triangle count. Measured before this existed: 2.5 s at the
    detail the window opens with, 8 s at the highest, and 43 s on sRGB
    against Display P3 — against 0.03 s for the cut that precedes it.

    HOW. Seen from *centre* every triangle covers a patch of the sky, so the
    sky is divided into a grid of directions and each triangle is filed under
    every cell that its own cap of sky reaches — the smallest cap around its
    middle direction that still holds all three corners, widened by half a
    cell. A ray then tries only its own cell's list. The cap can only ever
    offer TOO MANY candidates, never too few, so the answer is exactly the
    answer without it — which is what the test asserts, on every shape.
    """
    import numpy as np

    v = np.asarray(vertices, float) - np.asarray(centre, float)
    f = np.asarray(faces, int)
    corners = v[f]  # (M, 3, 3)
    unit = corners / np.maximum(1e-12, np.linalg.norm(corners, axis=2,
                                                      keepdims=True))
    # EACH TRIANGLE GETS A CAP OF SKY IT CANNOT ESCAPE, and not a box drawn
    # round its three corners. The corners' own latitudes do not bound the
    # patch: the arc BETWEEN two corners bulges, and can reach further from
    # the equator than either end of it. A box from the corners is therefore
    # too small, it drops candidates, and the caster quietly returns a
    # different answer -- measured on the paper's 414 big facets, which is
    # exactly where the bulge is worst. A cap around the middle direction,
    # wide enough to hold all three corners, cannot be too small.
    axis = unit.sum(axis=1)
    axis /= np.maximum(1e-12, np.linalg.norm(axis, axis=1, keepdims=True))
    reach = np.arccos(np.clip(np.einsum("ijk,ik->ij", unit, axis), -1, 1)).max(axis=1)
    lat_mid = (np.arange(rows) + 0.5) * (np.pi / rows)
    lon_mid = (np.arange(cols) + 0.5) * (2 * np.pi / cols) - np.pi
    la, lo = np.meshgrid(lat_mid, lon_mid, indexing="ij")
    middles = np.stack([np.sin(la) * np.cos(lo), np.sin(la) * np.sin(lo),
                        np.cos(la)], axis=-1).reshape(-1, 3)
    # HALF A CELL'S OWN WIDTH ON TOP, so a cap that only clips a cell's corner
    # is still filed there.
    margin = 0.5 * float(np.hypot(np.pi / rows, 2 * np.pi / cols))
    buckets: dict = {}
    for lo_i in range(0, len(f), 512):
        block = slice(lo_i, lo_i + 512)
        close = (middles @ axis[block].T
                 >= np.cos(np.minimum(np.pi, reach[block] + margin))[None, :])
        for cell, t in zip(*np.nonzero(close)):
            buckets.setdefault(int(cell), []).append(lo_i + int(t))
    filed = {k: np.asarray(w, int) for k, w in buckets.items()}
    a0, e1, e2 = (corners[:, 0], corners[:, 1] - corners[:, 0],
                  corners[:, 2] - corners[:, 0])

    def ask(directions, *, and_where=False):
        d = np.asarray(directions, float)
        d = d / np.maximum(1e-12, np.linalg.norm(d, axis=1, keepdims=True))
        out = np.full(len(d), np.nan)
        which = np.full(len(d), -1, int)
        where = np.zeros((len(d), 2))
        la = np.floor(np.arccos(np.clip(d[:, 2], -1, 1)) / np.pi * rows).astype(int)
        lo = np.floor((np.arctan2(d[:, 1], d[:, 0]) + np.pi)
                      / (2 * np.pi) * cols).astype(int)
        np.clip(la, 0, rows - 1, out=la)
        np.clip(lo, 0, cols - 1, out=lo)
        cell = la * cols + lo
        for key in np.unique(cell):
            mine = np.flatnonzero(cell == key)
            tris = filed.get(int(key))
            if tris is None:
                continue
            rays = d[mine]
            p = np.cross(rays[:, None, :], e2[tris][None, :, :])
            det = np.einsum("ijk,jk->ij", p, e1[tris])
            ok = np.abs(det) > 1e-12
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            sv = -a0[tris][None, :, :] * np.ones((len(rays), 1, 1))
            u = np.einsum("ijk,ijk->ij", sv, p) * inv
            q = np.cross(sv, e1[tris][None, :, :])
            vv = np.einsum("ijk,ik->ij", q, rays) * inv
            hit = ok & (u >= -1e-9) & (vv >= -1e-9) & (u + vv <= 1 + 1e-9)
            dist = np.einsum("ijk,jk->ij", q, e2[tris]) * inv
            hit &= dist > 1e-9
            far = np.where(hit, dist, np.inf)
            nearest = far.argmin(axis=1)
            rows_ = np.arange(len(rays))
            best = far[rows_, nearest]
            found = np.isfinite(best)
            out[mine] = np.where(found, best, np.nan)
            if and_where:
                which[mine] = np.where(found, tris[nearest], -1)
                where[mine, 0] = np.where(found, u[rows_, nearest], 0.0)
                where[mine, 1] = np.where(found, vv[rows_, nearest], 0.0)
        return (out, which, where) if and_where else out

    return ask


def _where_the_ray_leaves(vertices, faces, centre, directions, *,
                          and_where=False):
    """How far along each direction the mesh's surface is, from *centre*.

    Every triangle is asked at once — a gamut has hundreds, not millions, and
    a clever index would be more code than it saves. Where a direction somehow
    misses every triangle (it should not, on a shape that covers the view
    once), the distance comes back as NaN and the caller decides.

    With *and_where*, also returns which triangle was hit and where inside it
    — enough to read anything the mesh carries per corner, a colour above all,
    at the exact point the ray came out. A miss reports triangle -1.
    """
    import numpy as np

    v = np.asarray(vertices, float) - np.asarray(centre, float)
    f = np.asarray(faces, int)
    d = np.asarray(directions, float)
    d = d / np.maximum(1e-12, np.linalg.norm(d, axis=1, keepdims=True))
    a, e1, e2 = v[f[:, 0]], v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]
    out = np.full(len(d), np.nan)
    which = np.full(len(d), -1, int)
    where = np.zeros((len(d), 2))
    # In blocks, so a big mesh and many directions do not ask for one huge
    # array: 200 directions against every triangle at a time.
    for lo in range(0, len(d), 200):
        rays = d[lo:lo + 200]
        p = np.cross(rays[:, None, :], e2[None, :, :])
        det = np.einsum("ijk,jk->ij", p, e1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        # Möller-Trumbore, written out rather than borrowed, so the corner
        # cases are visible: the ray starts at the centre, so `s` is -a.
        s = -a[None, :, :] * np.ones((len(rays), 1, 1))
        u = np.einsum("ijk,ijk->ij", s, p) * inv
        q = np.cross(s, e1[None, :, :])
        vv = np.einsum("ijk,ik->ij", q, rays) * inv
        hit = ok & (u >= -1e-9) & (vv >= -1e-9) & (u + vv <= 1 + 1e-9)
        dist = np.einsum("ijk,jk->ij", q, e2) * inv
        hit &= dist > 1e-9
        far = np.where(hit, dist, np.inf)
        nearest = far.argmin(axis=1)
        best = far[np.arange(len(rays)), nearest]
        found = np.isfinite(best)
        out[lo:lo + 200] = np.where(found, best, np.nan)
        if and_where:
            rows = np.arange(len(rays))
            which[lo:lo + 200] = np.where(found, nearest, -1)
            where[lo:lo + 200, 0] = np.where(found, u[rows, nearest], 0.0)
            where[lo:lo + 200, 1] = np.where(found, vv[rows, nearest], 0.0)
    return (out, which, where) if and_where else out


def close_the_cut(vertices, faces, other_vertices, other_faces, centre, *,
                  under=None, clearance=None, sag=None, rounds=6, smooth=6,
                  most=8000):
    """A lid for an open piece, made from the piece's own rim.

    WHAT THIS IS FOR. Fade "where they agree" to nothing and what is left of a
    shape has a hole in it; turned round, you look into the hole and the far
    wall is lit like an outside, so it reads as torn skin. The honest cure is
    to close it with the piece of the OTHER shape that lies inside — and for
    that to look right the lid and the hole must share an edge exactly.

    HOW IT MANAGES THAT WITHOUT MATCHING ANYTHING. Every gamut here is a
    height field seen from a neutral point — one distance per direction, the
    view covered exactly once (`covers_the_sphere_once`). So the hole and the
    lid are THE SAME SET OF DIRECTIONS, one roofed and one floored: take the
    hole's own triangles and slide each corner down its own ray until it meets
    the other shape. The rim corners are already on that shape — the cut put
    them there — so they do not move, and the two pieces share them because
    they ARE them. Nothing is matched, so nothing can mismatch.

    ⚠ WELD FIRST. `split_at_crossing` leaves four copies of every crossing
    point, and an unwelded piece has cracks where its rim should be.

    ⚠ AND HOLD THE LID UNDER THE SKIN. The cut is coarser than the truth: a
    triangle whose three corners all stand outside the other shape can still
    have that shape bulging up through its middle — measured at 1.9% of one
    hole's area, by as much as 15.4 Lab. Left alone the lid pokes out through
    the skin it is meant to close. Pass the shape it must stay inside as
    *under* and it is held a hair beneath it, so where they would cross they
    touch instead.

    ⚠ AND THE LID SAGS. The hole's triangles are as coarse as the cut left
    them, and a flat triangle strung between three corners that sit on a
    curved floor hangs BELOW that floor in the middle — so the lid encloses
    too much. Measured on Glossy-paper against sRGB: 206,048 Lab³ where the
    true gap is 189,090, nine per cent too fat. Any lid edge that sags more
    than *sag* Lab is therefore split at its middle and the new corner dropped
    onto the floor too, up to *rounds* times. Rim edges are never split: the
    seam is the one thing that must stay exactly the hole's own corners.

    ⚠ AND THE CUT LEAVES NEEDLES. The lid starts as a copy of the hole's
    mesh, slivers and all. *smooth* passes let every corner but the seam's
    slide toward the average of its neighbours and then fall back down its own
    ray. A corner whose slide would turn a triangle inside out is put back:
    a folded lid is one that passes through itself.

    ⚠ AND *sag* IS A SHARE OF THE GAP, NOT A NUMBER OF Lab. It was 0.25 Lab
    flat, which is a fine tolerance on two shapes about 20 Lab apart and a
    useless one on two that are 2 Lab apart — and the second is the
    application's headline comparison, one paper measured months later against
    itself. Measured on that pair with the flat tolerance: 46.9% and 97.8%
    too much volume, with no structural symptom at all. Left as None it is
    one per cent of how far the lid actually drops, so the error stays the
    same share of the answer whatever the shapes.

    Returns (corners, the piece's triangles, the lid's triangles). The corners
    are shared, so the two can be drawn as one closed solid, and every
    triangle is wound the same way round (`face_the_same_way`).
    """
    import numpy as np

    kept, welded, _where = weld_by_position(vertices, faces)
    middle = np.asarray(centre, float)
    # ⚠ HELD FAR ENOUGH UNDER TO BE DRAWN, not just far enough to be inside.
    # It was a flat 0.02 Lab, which is inside the surface but far too close
    # for the picture to separate them: measured, 15.1% of the lid's corners
    # sat within 0.05 Lab of the skin, and the two stitched into a speckled
    # mess wherever they nearly met. Raised, that falls to 299 corners --
    # which is EXACTLY the seam, where the two must touch and do. A share of
    # the shape rather than a number of Lab, for the same reason the size
    # floor is: the space is the reader's to choose, and one Lab means
    # nothing in a gamut that spans 0.85.
    if clearance is None:
        clearance = max(1e-6, float(np.linalg.norm(kept.max(axis=0) - kept.min(axis=0))) / 800.0)

    # BUILT ONCE, ASKED HUNDREDS OF TIMES. The floor and the ceiling do not
    # move, and every corner, every round of splitting and every smoothing
    # pass casts against them again.
    floor_of = _rays_onto(other_vertices, other_faces, middle)
    roof_of = _rays_onto(under[0], under[1], middle) if under is not None else None

    def onto_the_floor(points):
        """Slide points down their own rays until they meet the other shape."""
        rays = np.asarray(points, float) - middle
        reach = np.linalg.norm(rays, axis=1)
        alive = reach > 1e-9
        if not alive.all():
            rays = np.where(alive[:, None], rays, np.array([1.0, 0.0, 0.0]))
        far = floor_of(rays)
        if roof_of is not None:
            ceiling = roof_of(rays)
            # The same share, for the same reason: a flat step here distorts
            # a narrow gap just as badly.
            hold = np.minimum(clearance,
                              0.01 * np.maximum(0.0, np.where(
                                  np.isfinite(ceiling), ceiling, reach) - far))
            far = np.where(np.isfinite(ceiling),
                           np.minimum(far, ceiling - hold), far)
        # A direction the other shape does not answer for keeps the piece's
        # own distance: the lid meets the skin there rather than flying off.
        far = np.where(np.isfinite(far), far, reach)
        # ⚠ AND JUST INSIDE THE OTHER SHAPE, NOT EXACTLY ON IT. The lid IS
        # that shape's surface -- which is the whole point -- and the other
        # shape is usually drawn as well, so laying the two at the same depth
        # asks the picture to choose between them pixel by pixel. It cannot,
        # and the answer is a speckled mess wherever they meet. Held a
        # thousandth of the shape under, which is far below anything the eye
        # can place and far above what the depth buffer can separate.
        #
        # ⚠ A HUNDREDTH OF THE LOCAL DROP, capped by *clearance*, and NOT a
        # flat share of the shape. Two measurements of one paper are about two
        # Lab apart, so a step sized for a 190 Lab shape is a tenth of the
        # whole gap and swells what the lid encloses: measured, +61.7% against
        # a ray count, where it had been +1.9%. Tied to the drop, the error it
        # can add is one per cent of the answer wherever the shapes are.
        step = np.minimum(clearance, 0.01 * np.maximum(0.0, reach - far))
        far = np.maximum(0.0, far - step)
        unit = rays / np.maximum(1e-12, np.linalg.norm(rays, axis=1, keepdims=True))
        return middle + unit * far[:, None]

    # ⚠ A PIECE WITH NO RIM IS ALREADY CLOSED, AND MUST BE LEFT ALONE.
    # When one shape lies wholly inside another nothing is cut away, so the
    # "piece" is the whole skin and it has no hole to cap. Capping it anyway
    # builds a SECOND closed shell inside the first, and since neither shares
    # an edge with the other every check here still passes: no edge is left
    # open, none is used more than twice, and each shell is wound outward on
    # its own. The volume then comes out as skin PLUS lid instead of skin
    # MINUS lid. Measured on two shapes that ship in `demo/` — Matte-paper
    # lies entirely inside Glossy-paper, 0 of its 222 corners outside — the
    # answer was 1,341,108 against a true 180,432: SIX HUNDRED AND FORTY-THREE
    # PER CENT out, with a clean bill of health from every test.
    rim = sorted({i for loop in boundary_loops(welded) for i in loop})
    if not rim:
        return kept, welded, np.zeros((0, 3), int)
    # ⚠ AND THE RAYS MUST MEAN SOMETHING. Everything here rests on the other
    # shape being a height field seen from *centre* — one distance for each
    # direction. A centre outside it, or a shape that folds, and the "floor"
    # a ray lands on is not the floor at all. A gamut of only the light
    # patches of a chart does not contain (50, 0, 0); asked to cap that, this
    # used to return 126 + 3,232 triangles with 13 of the piece's own facing
    # inward and still call itself closed. `covers_the_sphere_once` reads
    # 0.9128 of a full view there, and it was written for exactly this and
    # then never consulted.
    covered = covers_the_sphere_once(other_vertices, other_faces, middle)
    if abs(covered - 4.0 * np.pi) > 1e-2:
        raise ValueError(
            f"the shape being capped against covers {covered:.4f} of the view "
            f"from {tuple(np.round(middle, 3))}, not {4 * np.pi:.4f} — the "
            f"middle is outside it or it folds, and sliding corners down "
            f"their rays onto it would land them anywhere")
    lid = onto_the_floor(kept)
    # ONLY THE SEAM IS SHARED, and it is shared BY BEING THE SAME CORNERS.
    # The seam keeps the piece's own numbering, so its corners cannot drift
    # apart however the lid is worked on afterwards — there is nothing to keep
    # in step. Everything inside gets a copy of its own: share those as well
    # and every inside edge is used FOUR times, twice by the piece and twice
    # by the lid, which is two surfaces glued together and not a solid at all.
    # Measured that way: 0 edges open and 496 used more than twice.
    on_the_seam = np.zeros(len(kept), bool)
    if rim:
        on_the_seam[np.asarray(rim, int)] = True
    theirs = np.arange(len(kept))
    theirs[~on_the_seam] = len(kept) + np.arange(int((~on_the_seam).sum()))
    corners = np.vstack([kept, lid[~on_the_seam]])
    # The lid faces the other way round, so it closes rather than doubles.
    lid_faces = theirs[welded][:, ::-1].copy()
    held = len(kept)  # everything below this belongs to the piece and the seam
    seam_edges = set()
    for loop in boundary_loops(welded):
        for a, b in zip(loop, loop[1:]):
            seam_edges.add((min(int(a), int(b)), max(int(a), int(b))))

    # ---- THE SAG. Split whichever lid edge hangs furthest from the floor,
    # never a seam edge, and drop the new corner onto the floor as well.
    if sag is None:
        drop = np.linalg.norm(lid - kept, axis=1)
        inside = np.ones(len(kept), bool)
        inside[np.asarray(rim, int)] = False
        far = drop[inside] if inside.any() else drop
        # A TWENTIETH OF HOW FAR THE LID FALLS, and it is the NARROW pairs
        # that fix it there. On the paper against sRGB almost anything works:
        # a fifth of the drop still lands within +0.37% of a ray count. Two
        # measurements of one paper are another matter — their drop has a
        # median of half a Lab, and a coarser lid simply misses the floor:
        #
        #     a twentieth   +0.96%      a sixth   +8.60%
        #     a quarter    +15.99%      two fifths  +26.76%
        #
        # A lid that far off is not decoration, it is in the wrong place. The
        # cost is that the wide pairs then reach the ceiling and are trimmed,
        # which costs them nothing measurable.
        sag = max(1e-4, 0.05 * float(np.median(far)) if len(far) else 1e-4)
    # ⚠ AND A CEILING, BECAUSE THIS IS A THING TO LOOK AT. Two measurements
    # of one paper lie a tenth of a Lab apart over most of their shared
    # surface, so ANY share of that drop is microscopic and the splitting runs
    # away: 48,666 lid triangles at a hundredth, 11,840 at a tenth. None of it
    # is worth having. The numbers beside the picture are worked out from the
    # SHAPES and never from this lid, so what a coarser lid costs is a per
    # cent or two of a volume nobody reads off it — against a page that has to
    # carry and draw fifty thousand triangles it does not need.
    for _round in range(int(rounds)):
        if len(lid_faces) >= int(most):
            break
        want = {}
        for tri in lid_faces:
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                key = (min(int(a), int(b)), max(int(a), int(b)))
                if key not in want and key not in seam_edges:
                    want[key] = None
        if not want:
            break
        edges = np.asarray(list(want), int)
        middles = 0.5 * (corners[edges[:, 0]] + corners[edges[:, 1]])
        dropped = onto_the_floor(middles)
        hangs = np.linalg.norm(dropped - middles, axis=1)
        take = hangs > float(sag)
        if not take.any():
            break
        # A HARD BOUND, and not a look before each round. Splitting an edge
        # adds at most two triangles to each face that uses it, so a round
        # begun under the ceiling can end at four times it: checking only at
        # the top let a lid of 7,999 become 32,000. The worst-sagging edges
        # are worth the most, so they are taken first and the rest wait for a
        # round that has room -- or never come, which is the point.
        room = max(0, (int(most) - len(lid_faces)) // 2)
        if take.sum() > room:
            worst = np.argsort(np.where(take, hangs, -np.inf))[::-1][:room]
            take = np.zeros(len(hangs), bool)
            take[worst] = True
            if not take.any():
                break
        fresh = {}
        added = []
        for t in np.flatnonzero(take):
            fresh[(int(edges[t, 0]), int(edges[t, 1]))] = len(corners) + len(added)
            added.append(dropped[t])
        corners = np.vstack([corners, np.asarray(added, float)])
        cut_up = []
        for a, b, c in lid_faces:
            m = [fresh.get((min(int(a), int(b)), max(int(a), int(b)))),
                 fresh.get((min(int(b), int(c)), max(int(b), int(c)))),
                 fresh.get((min(int(c), int(a)), max(int(c), int(a))))]
            how_many = sum(x is not None for x in m)
            if how_many == 0:
                cut_up.append((a, b, c))
            elif how_many == 3:
                cut_up += [(a, m[0], m[2]), (m[0], b, m[1]),
                           (m[2], m[1], c), (m[0], m[1], m[2])]
            elif how_many == 1:
                k = [i for i, x in enumerate(m) if x is not None][0]
                p, q, r = ((a, b, c), (b, c, a), (c, a, b))[k]
                cut_up += [(p, m[k], r), (m[k], q, r)]
            else:
                k = [i for i, x in enumerate(m) if x is None][0]
                p, q, r = ((a, b, c), (b, c, a), (c, a, b))[k]
                cut_up += [(p, q, m[(k + 1) % 3]),
                           (p, m[(k + 1) % 3], m[(k + 2) % 3]),
                           (m[(k + 2) % 3], m[(k + 1) % 3], r)]
        lid_faces = np.asarray(cut_up, int)

    # ---- THE NEEDLES. Every lid corner but the seam's slides toward the
    # average of its neighbours and falls back down its ray. Nothing may fold.
    free = np.ones(len(corners), bool)
    free[:held] = False
    facing = face_the_same_way(lid_faces, corners, middle)

    def turned_inside_out(where):
        a = where[facing[:, 0]] - middle
        b = where[facing[:, 1]] - middle
        c = where[facing[:, 2]] - middle
        return np.einsum("ij,ij->i", a, np.cross(b, c)) <= 0

    for _pass in range(int(smooth)):
        pull = np.zeros_like(corners)
        count = np.zeros(len(corners))
        for a, b in ((0, 1), (1, 2), (2, 0)):
            np.add.at(pull, lid_faces[:, a], corners[lid_faces[:, b]])
            np.add.at(count, lid_faces[:, a], 1.0)
            np.add.at(pull, lid_faces[:, b], corners[lid_faces[:, a]])
            np.add.at(count, lid_faces[:, b], 1.0)
        moving = np.flatnonzero(free & (count > 0))
        if not len(moving):
            break
        towards = corners[moving] + 0.6 * (pull[moving] / count[moving, None]
                                           - corners[moving])
        before = corners[moving].copy()
        corners[moving] = onto_the_floor(towards)
        for _try in range(6):
            folded = np.flatnonzero(turned_inside_out(corners))
            if not len(folded):
                break
            guilty = np.intersect1d(np.unique(facing[folded]), moving)
            if not len(guilty):
                break
            corners[guilty] = before[np.searchsorted(moving, guilty)]

    settled = face_the_same_way(np.vstack([welded, lid_faces]), corners, middle)
    return corners, settled[:len(welded)], settled[len(welded):]


def sharpen_where_they_part(vertices, faces, colors, stands, is_outside, *,
                            rounds=6, samples=6, closer=1, too_small=None):
    """Give `split_at_crossing` a mesh fine enough to see the real boundary.

    WHY. `split_at_crossing` asks each triangle's three corners which side of
    the boundary they are on and cuts the edges where the answer changes. That
    leaves the drawn boundary wrong in two ways, and both were measured on the
    paper the application ships with, against sRGB, which is the reference
    most people compare to.

    ONE — A FACET WHOSE CORNERS AGREE IS LEFT ALONE, and the other shape can
    bulge up through its middle without ever reaching a corner. Three facets
    carrying 5.3% of the standing area do exactly that. There the boundary
    jumps straight across instead of going round the bulge.

    TWO — BETWEEN TWO CORNERS OF THE SEAM IT IS A STRAIGHT LINE, and the true
    crossing is not. The seam only gets a corner where it meets an edge of
    THIS mesh, so across one facet it chords over however much the other
    shape bends. That is why the seam is identical whether the reference has
    1,452 triangles or 60,492: one corner per crossed edge, and no more.

    Sampled along the drawn seam, the gap between the two surfaces should be
    nought all the way. Measured:

        as it ships               29.8% of the seam strays >1 Lab, worst 14.64
        after phase one           11.9%                              worst  4.21
        after both, closer=1       1.8%                              worst  1.01
        after both, closer=2       0.0%                              worst  0.78

    One Lab is about the smallest difference a good eye can find, so
    ``closer=1`` puts the seam under what anyone can see, for 1,762 triangles
    against 650. A negative gap means this shape is INSIDE the other one
    there, so what was drawn standing was ground it does not reach at all.

    HOW. Both phases mark EDGES and re-cut every triangle that uses a marked
    one — two, three or four pieces according to how many of its edges were
    marked — so no corner is ever left hanging in the middle of a neighbour's
    edge. Phase one repeats up to *rounds* times, or until no facet hides a
    crossing. Phase two quarters every straddling facet *closer* times.

    Returns ``(vertices, faces, colors, stands)`` describing the SAME surface.
    """
    import numpy as np

    v = np.asarray(vertices, float)
    f = np.asarray(faces, int)
    keep = np.asarray(stands, bool)
    # ⚠ COLOURS COME IN TWO FORMS, and `np.asarray(colors, float)` raises on
    # one of them. `split_at_crossing` deliberately takes "rgb(r,g,b)" strings
    # — that is what the drawing library is handed — and mixes them with
    # `_mix_colour`. This used to convert blindly, and the caller's bare
    # `except Exception` would have swallowed the ValueError and quietly left
    # the shape its OLD mesh: the gradient seam back, and no error anywhere to
    # say why. Not reachable today, because every gamut the application builds
    # carries numbers, and that is exactly the kind of thing that stops being
    # true without anybody noticing.
    as_text = (colors is not None and len(colors)
               and isinstance(colors[0], str))
    cols = (list(colors) if as_text
            else None if colors is None else np.asarray(colors, float))
    if not len(f):
        return v, f, colors, keep
    # ⚠ NOTHING TO SHARPEN WHERE THE WHOLE SHAPE AGREES WITH ITSELF, and
    # asking anyway does harm. A new corner is the middle of an edge, which
    # lies ON this surface — so where the two surfaces TOUCH, as two copies of
    # one shape do everywhere, the question "is this point outside the other?"
    # is put exactly on its own answer's boundary and comes back either way.
    # Two identical shapes agree everywhere and fading the agreement should
    # empty the picture; sharpening left specks of it standing, and the
    # caption that explains an emptied picture stopped appearing.
    #
    # A shape whose corners are unanimous has no boundary drawn on it to
    # sharpen. THE PRICE, stated: a bulge that pokes through one facet of an
    # otherwise wholly-inside shape is not found. That is the one case this
    # cannot see, and it is the price of not inventing a boundary where two
    # surfaces touch.
    if keep.all() or not keep.any():
        return v, f, colors, keep
    across = float(np.linalg.norm(v.max(axis=0) - v.min(axis=0)))
    # A FIFTIETH OF THE SHAPE, chosen against measurement and not taste.
    # On the paper against sRGB, worst error and what three references
    # crossing each other cost:
    #     across/200 (1.32 Lab)  worst 1.01   3,552 ms, 48,329 faces
    #     across/100 (2.65 Lab)  worst 1.01   2,630 ms, 34,964
    #     across/50  (5.29 Lab)  worst 1.16   1,394 ms, 17,603
    #     across/25  (10.6 Lab)  worst 4.05     334 ms,  7,121
    # A fiftieth keeps the seam inside what an eye can find and costs a third
    # of what a two-hundredth does; a twenty-fifth throws the accuracy away.
    floor = (float(too_small) if too_small is not None
             else max(1e-9, across / 50.0))
    # ⚠ FEWER THAN THREE SAMPLES A SIDE IS NO SAMPLES AT ALL: the weights
    # below take only the points strictly inside, and a triangle halved or
    # left whole has none. It used to accept 1 or 2 and quietly do nothing at
    # all in phase one, which reads exactly like a phase one that found
    # nothing to do.
    if int(samples) < 3:
        raise ValueError(
            f"samples must be at least 3 to have any point strictly inside a "
            f"facet, got {samples}")
    # ⚠ AND IT MUST NOT RUN AWAY. Three references crossing each other took
    # one mesh from 18,252 faces to 172,548 and 1.4 GB of memory. Each round
    # can at most quadruple, so a ceiling on the total is the one bound that
    # holds however many shapes are in the picture.
    ceiling = max(12000, 6 * len(f))

    def cut_along(edges):
        """Halve every named edge and re-cut whatever triangle uses one."""
        nonlocal v, f, keep, cols
        pairs = np.asarray(sorted(edges), int)
        middles = 0.5 * (v[pairs[:, 0]] + v[pairs[:, 1]])
        fresh = {tuple(e): len(v) + i for i, e in enumerate(pairs.tolist())}
        v = np.vstack([v, middles])
        if as_text:
            cols = cols + [_mix_colour(cols[int(a)], cols[int(b)], 0.5)
                           for a, b in pairs]
        elif cols is not None:
            cols = np.vstack([cols,
                              0.5 * (cols[pairs[:, 0]] + cols[pairs[:, 1]])])
        keep = np.concatenate([keep, np.asarray(is_outside(middles), bool)])
        out = []
        for a, b, c in f:
            m = [fresh.get((min(int(a), int(b)), max(int(a), int(b)))),
                 fresh.get((min(int(b), int(c)), max(int(b), int(c)))),
                 fresh.get((min(int(c), int(a)), max(int(c), int(a))))]
            how_many = sum(x is not None for x in m)
            if how_many == 0:
                out.append((a, b, c))
            elif how_many == 3:
                out += [(a, m[0], m[2]), (m[0], b, m[1]),
                        (m[2], m[1], c), (m[0], m[1], m[2])]
            elif how_many == 1:
                k = [i for i, x in enumerate(m) if x is not None][0]
                p, q, r = ((a, b, c), (b, c, a), (c, a, b))[k]
                out += [(p, m[k], r), (m[k], q, r)]
            else:
                k = [i for i, x in enumerate(m) if x is None][0]
                p, q, r = ((a, b, c), (b, c, a), (c, a, b))[k]
                out += [(p, q, m[(k + 1) % 3]),
                        (p, m[(k + 1) % 3], m[(k + 2) % 3]),
                        (m[(k + 2) % 3], m[(k + 1) % 3], r)]
        f = np.asarray(out, int)

    def big_enough(which):
        """Drop the facets too small to have misplaced the boundary anyway.

        A facet can only hide a bulge, or chord across a bend, by something
        like its own size, so below *too_small* across, cutting it again buys
        less than an eye can find.

        ⚠ IT IS A SHARE OF THE SHAPE, NOT A NUMBER OF Lab. It was a flat 1.0,
        and the space the reader is drawing in is theirs to choose: a gamut in
        CIE XYZ spans 0.005 to 0.85, its widest facet edge is 0.9264, and one
        Lab therefore threw away EVERY facet — the whole function became a
        silent no-op in that space, leaving the seam 8.4% of the shape's own
        radius out of place. A five-hundredth of the shape's diagonal is 0.95
        in Lab, which is what was measured there, and 0.004 in XYZ.

        ⚠ AND IT DOES NOT MAKE A FINE MESH CHEAP. An earlier version of this
        note claimed that at the highest Detail every one of the reference's
        18,252 facets is already under a Lab across, so none is touched. That
        was never measured and it is false — the median widest edge is 4.07
        Lab and 99.3% of them are over. Nothing here bounds the cost; what
        bounds it is that the answer is kept between redraws
        (`recut_where_they_part`).
        """
        if not len(which):
            return which
        tri = v[f[which]]
        widest = np.linalg.norm(
            np.stack([tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 1],
                      tri[:, 0] - tri[:, 2]]), axis=2).max(axis=0)
        return which[widest > floor]

    def edges_of(which):
        found = set()
        for tri in f[which]:
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                found.add((min(int(a), int(b)), max(int(a), int(b))))
        return found

    # ---- ONE: facets the boundary crosses without touching an edge.
    n = int(samples)
    weights = np.asarray(
        [(i / n, j / n, (n - i - j) / n) for i in range(n + 1)
         for j in range(n + 1 - i) if i and j and (n - i - j)], float)
    if len(weights):
        for _round in range(int(rounds)):
            corner_says = keep[f]
            settled = big_enough(np.flatnonzero(
                corner_says.all(axis=1) | (~corner_says).all(axis=1)))
            if not len(settled):
                break
            inside = np.einsum("kj,ijl->ikl", weights, v[f[settled]])
            beyond = np.asarray(is_outside(inside.reshape(-1, 3)), bool)
            beyond = beyond.reshape(len(settled), len(weights))
            hiding = big_enough(
                settled[(beyond != keep[f[settled][:, 0]][:, None]).any(axis=1)])
            if not len(hiding):
                break
            cut_along(edges_of(hiding))
            if len(f) >= ceiling:
                break

    # ---- TWO: the facets the boundary does cross, so the seam gets corners
    # along it rather than one chord from edge to edge.
    for _pass in range(int(closer)):
        says = keep[f]
        straddling = big_enough(
            np.flatnonzero(~(says.all(axis=1) | (~says).all(axis=1))))
        if not len(straddling):
            break
        cut_along(edges_of(straddling))
        if len(f) >= ceiling:
            break

    return v, f, (cols if colors is not None else None), keep


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


def _assign(lab, families=HUE_FAMILIES):
    """The raw filing of colours into families: (chroma, nearest, gaps).

    ONE RULE, USED BY THE SENTENCES AND BY THE PICTURE. The report says "the
    blues moved toward the magentas" and the cloud can be split into the same
    families and filtered to one of them. If those were two pieces of
    arithmetic they would agree today and disagree after the first change to
    either, and a reader would have a picture contradicting the words under it.
    """
    lab = np.asarray(lab, float)
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    hue = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360.0
    centres = np.array([c for _n, c in families])
    gap = np.abs(((hue[:, None] - centres[None, :]) + 180.0) % 360.0 - 180.0)
    return chroma, gap.argmin(axis=1), gap


def which_family(lab, *, families=HUE_FAMILIES, neutral: float = None):
    """Which family each colour belongs to, as names, greys included.

    The picture's half of :func:`family_drift`: given the colours a cloud is
    drawn at, say which family each dot is in, so the cloud can be split up
    and filtered exactly the way the sentences describe it.
    """
    if neutral is None:
        neutral = NEUTRAL_CHROMA
    lab = np.asarray(lab, float)
    if lab.ndim != 2 or lab.shape[1] != 3:
        raise ValueError("this needs (N, 3) L*a*b* values")
    chroma, nearest, _gap = _assign(lab, families)
    names = np.array([n for n, _c in families] + ["greys"], dtype=object)
    picked = np.where(chroma < neutral, len(families), nearest)
    return names[picked]


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
    chroma, nearest, gap = _assign(lab_a, families)
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


def heading_for(lab_a, lab_b, *, families=HUE_FAMILIES, quiet: float = None,
                neutral: float = None):
    """Which family each colour is HEADING FOR, dot by dot.

    THE OTHER HALF OF THE PICTURE. "How far it moved" is a distance and has no
    direction: a printer gone lighter and one gone darker by the same amount
    draw the same cloud. Splitting the cloud by the family each colour is IN
    says where the movement is; this says where it is GOING, which is the
    question anybody holding two profiles actually asks -- "my greys have gone
    warm" is a sentence about a destination.

    NOT THE FAMILY IT LANDS IN, for the same reason the written report does not
    use one: a blue that drifts a long way toward the greens is usually still a
    blue when it arrives, and "the blues went to the blues" answers nothing.
    What is named is the next family centre in the direction of travel -- see
    :func:`_neighbour`, which this shares so the picture and the sentences can
    never disagree.

    A QUIET COLOUR IS NOT HEADING ANYWHERE, and this is the whole reason for
    the threshold. Below about ΔE 1 the direction of a movement is mostly the
    instrument: a hand-held spectrophotometer repeats to roughly ΔE 0.1 on
    white and two different instruments agree to about 0.4, so a dot that has
    moved 0.3 has a direction that is arithmetic on noise. Painting it a
    confident red would be the single most misleading thing this application
    could do -- it would make an unchanged printer look like it was marching
    somewhere. Those dots are named "" and the caller draws them quietly.

    A COLOUR TOO CLOSE TO NEUTRAL TO HAVE A HUE cannot be said to have set off
    round the circle either: its own hue is noise, so the angle it leaves at is
    noise as well. Those are named "" too, however far they moved -- the amount
    is real, the direction is not.

    Returns an (N,) array of family names, "" where nothing honest can be said.
    """
    if quiet is None:
        quiet = QUIET_DE
    if neutral is None:
        neutral = NEUTRAL_CHROMA
    a = np.asarray(lab_a, float)
    b = np.asarray(lab_b, float)
    if a.shape != b.shape or a.ndim != 2 or a.shape[1] != 3:
        raise ValueError("this needs two matching (N, 3) L*a*b* sets")
    moved = delta_e_2000(a, b)
    chroma = np.hypot(a[:, 1], a[:, 2])
    mine = which_family(a, families=families, neutral=neutral)
    out = np.full(len(a), "", dtype=object)
    for i in range(len(a)):
        if not np.isfinite(moved[i]) or moved[i] < quiet:
            continue
        if chroma[i] < neutral:
            continue
        # WHICH WAY ROUND THE CIRCLE, from this colour's own hue: the sign of
        # the movement across the hue direction. Positive is anticlockwise in
        # a*/b*, which is the same convention _which_way uses for a family.
        hue = np.arctan2(a[i, 2], a[i, 1])
        across = (-np.sin(hue) * (b[i, 1] - a[i, 1])
                  + np.cos(hue) * (b[i, 2] - a[i, 2]))
        name = _neighbour(a[i], across, families, own=mine[i])
        out[i] = name.removeprefix("toward the ")
    return out


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
