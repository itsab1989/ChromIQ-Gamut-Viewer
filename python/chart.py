"""A chart that has not been printed yet — and the three questions about it.

WHAT A CHART IS, AND WHY IT IS NOT A MEASUREMENT
------------------------------------------------
Everything else this application opens has been *measured*: a ``.ti3`` is what
came back off the paper, an ICC profile is a model fitted to numbers that came
back off the paper. A chart is the other end of the story. It is the list of ink
amounts about to be *asked for*:

===========  ==============================================  ====================
File         What it holds                                   What it can answer
===========  ==============================================  ====================
``.ti3``     device values **and** what came back            what the printer did
``.ti2``     device values, and where each patch sits        what will be asked for
``.ti1``     device values only                             what will be asked for
===========  ==============================================  ====================

So a chart must never be drawn as a gamut. A shape thrown around a set of
requested RGB values is not the gamut of anything, and calling it one would be
exactly the confident-looking nonsense this application exists to avoid. A
chart is drawn as a **cloud of points**, and only ever where a profile says
those points would land.

THE ONE THAT LOOKS LIKE A MEASUREMENT AND IS NOT
-------------------------------------------------
A ``.ti1`` from ``targen`` carries ``XYZ_X XYZ_Y XYZ_Z`` columns. They are not
measurements. They are what targen's device model *predicts*, and with no
``-c`` profile that model is a crude default: on a real ChromIQ chart the
"black" patch is written as XYZ 1, 1, 1 for want of anything better. Reading
those as though a spectrophotometer had reported them gives a plausible,
symmetrical, entirely fictional gamut.

They are kept and reported (``Chart.expected``) because they are worth
*comparing against*, and because ``ACCURATE_EXPECTED_VALUES "true"`` marks the
files where targen was given a real profile to predict with. They are never
used to place a patch.

THE THREE QUESTIONS, WHICH ARE DIFFERENT
-----------------------------------------
**A — do these patches sit inside what this profile says it can print?**
A check of the chart, against the profile it was made from or any other. When
it is the same profile both times the answer is nearly always yes, *by
construction* — and that is worth saying out loud rather than hiding, because
it is still a real check of the chart builder. Four things it catches, all of
which put patches outside a gamut they were promised to be inside: the builder
using one rendering intent and the check another; device values scaled 0..255
where the file wants 0..100; patches clipped to the gamut's bounding box
rather than to its surface; and a profile silently swapped between building and
printing.

**B — do they sit inside what the paper actually achieved?** Place them
through the profile, compare against a *measured* ``.ti3``. This is the one
that finds printer trouble: "your profile promises these and the paper did not
deliver them."

**C — are they spread evenly?** No profile needed for the question, though one
is needed to see it. Clumping and gaps are what a chart designer actually
worries about.

COLOUR SCIENCE, STATED
----------------------
* CGATS device values run **0..100**, not 0..255. i1Profiler's text export runs
  0..255. Getting that backwards scales every patch by 2.55 and looks entirely
  plausible, so the scale is decided from the file's own numbers and reported
  on screen rather than assumed.
* Patches are placed through the profile's **A2B1** table — relative
  colorimetric, the "where would this land" question — with A2B0 as a fallback.
  The one actually used is named on screen, because the two disagree near the
  edges, which is precisely where this check lives.
* PCS white is the ICC constant, not a textbook D50. ``icc_read.PCS_WHITE``.
* Outside is reported in **ΔE2000**, measured to the nearest point on the
  surface. ΔE76 is not good enough near the edge of a gamut.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import cgats

#: The device columns a chart can carry, and what to call each channel.
_DEVICE_SETS = (
    (("RGB_R", "RGB_G", "RGB_B"), ("R", "G", "B")),
    (("CMYK_C", "CMYK_M", "CMYK_Y", "CMYK_K"), ("C", "M", "Y", "K")),
)

#: A column whose presence means the file has been measured.
_MEASURED = ("XYZ_X", "XYZ_Y", "XYZ_Z", "LAB_L", "LAB_A", "LAB_B")

#: What the first line says for a chart that has not been measured. ``CTI1`` is
#: the chart as generated, ``CTI2`` the same chart laid out on a sheet.
CHART_KINDS = ("CTI1", "CTI2")

#: What the first line says for a measurement.
MEASURED_KINDS = ("CTI3",)

#: File endings offered in the Open-a-chart dialog. The decision is always made
#: on the file's contents; this list only decides what the dialog shows.
SUFFIXES = (".ti1", ".ti2", ".txt", ".pxf", ".cxf")


class ChartProblem(ValueError):
    """This file is not a chart, with a reason worth reading."""


@dataclass(frozen=True)
class Chart:
    """A list of patches waiting to be printed."""

    name: str
    device: np.ndarray            # (N, k) 0..1 — what will be asked of the printer
    channels: tuple               # ("R", "G", "B") or ("C", "M", "Y", "K")
    kind: str                     # what the file's first line called itself
    scale: float                  # 100.0 or 255.0 — what the file's numbers ran to
    scale_certain: bool           # False when the file gave nothing to decide on
    n_rows: int                   # rows in the file, repeats included
    duplicates: int               # rows repeating a device value already seen
    clamped: int                  # values outside the range, pulled back into it
    locations: tuple = ()         # sheet positions, when the file records them
    expected: np.ndarray | None = None      # XYZ the file predicts, Y = 1 white
    expected_accurate: bool = False         # predicted through a real profile
    keywords: dict = field(default_factory=dict)

    @property
    def n_patches(self) -> int:
        return len(self.device)

    @property
    def is_rgb(self) -> bool:
        return self.channels == ("R", "G", "B")

    def unique(self) -> "Chart":
        """The same chart with repeated device values collapsed to one.

        Charts repeat patches on purpose — white and black several times over
        for the instrument to calibrate against, and whole passes duplicated
        when somebody means to average two readings. Repeats say nothing about
        where the chart reaches, and drawing 5960 points where 5104 are
        distinct makes the dense parts look denser than they are.
        """
        _, first = np.unique(self.device, axis=0, return_index=True)
        first.sort()
        return Chart(
            name=self.name, device=self.device[first], channels=self.channels,
            kind=self.kind, scale=self.scale, scale_certain=self.scale_certain,
            n_rows=self.n_rows, duplicates=0, clamped=self.clamped,
            locations=tuple(self.locations[i] for i in first)
            if self.locations else (),
            expected=None if self.expected is None else self.expected[first],
            expected_accurate=self.expected_accurate, keywords=self.keywords)


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def looks_like_chart(path) -> bool:
    """True when this file is a chart rather than a measurement.

    Decided on the file's contents, never on its ending. People rename things,
    tools write ``.txt`` for four different formats, and a ``.ti1`` that has
    been measured and saved under the same name is not a chart any more.
    Anything unreadable answers False: this is used to choose which of two
    perfectly good readers to hand the file to, and the reader gives the better
    error message.
    """
    path = Path(path)
    try:
        if path.suffix.lower() in (".pxf", ".cxf", ".xml"):
            return _cxf_is_chart(path)
        text = path.read_text(errors="replace")
        kind = cgats.identifier(text)
        if kind in CHART_KINDS:
            return True
        if kind in MEASURED_KINDS:
            return False
        tables = cgats.read_tables(text)
        return (_device_columns(tables[0]) is not None
                and not any(t.has(*_MEASURED[:3]) or t.has(*_MEASURED[3:])
                            for t in tables))
    except Exception:            # noqa: BLE001 — a guess, and a wrong guess is
        return False             # answered properly by whichever reader runs


def _device_columns(table):
    """Which set of device columns this table carries, if any."""
    for names, channels in _DEVICE_SETS:
        if table.has(*names):
            return names, channels
    return None


def read_chart(path) -> Chart:
    """Read a chart from any of the forms this understands.

    Raises ``ChartProblem`` with a plain reason for anything it cannot use —
    including a measurement, which is a perfectly good file being opened in the
    wrong place.
    """
    path = Path(path)
    if not path.is_file():
        raise ChartProblem(f"there is no file at {path}")
    if path.suffix.lower() in (".pxf", ".cxf", ".xml"):
        return _read_cxf(path)
    return _read_cgats(path)


def _read_cgats(path: Path) -> Chart:
    text = path.read_text(errors="replace")
    kind = cgats.identifier(text)
    if kind in MEASURED_KINDS:
        raise ChartProblem(
            f"{path.name} is a measurement, not a chart waiting to be "
            "printed — every patch in it has already been read off the paper. "
            "Open it with Open… instead, and it draws as a gamut.")
    try:
        tables = cgats.read_tables(text)
    except cgats.CgatsProblem as exc:
        raise ChartProblem(str(exc)) from None

    # THE FIRST TABLE THAT HOLDS PATCHES. A .ti1 carries three: the chart, then
    # eight density extremes, then nine device combinations. The last two are
    # reference values targen records about the chart, not patches to print,
    # and a reader that concatenates them reports a chart 17 patches too long.
    for table in tables:
        found = _device_columns(table)
        if found and len(table):
            break
    else:
        raise ChartProblem(
            f"{path.name} has no RGB or CMYK columns, so there are no patches "
            "in it to place. A chart names the ink amounts for every patch — "
            "look for columns called RGB_R, RGB_G and RGB_B.")
    names, channels = found

    if kind not in CHART_KINDS and table.has(*_MEASURED[:3]):
        raise ChartProblem(
            f"{path.name} carries measured XYZ values, so it is a measurement "
            "rather than a chart waiting to be printed. Open it with Open… "
            "instead.")

    raw = table.numbers(*names)
    scale, certain = _scale_of(kind, raw, cgats.keyword(tables, "COLOR_REP"))
    device = raw / scale
    clamped = int(((device < -1e-9) | (device > 1 + 1e-9)).any(axis=1).sum())
    device = np.clip(device, 0.0, 1.0)

    _, first = np.unique(device, axis=0, return_index=True)
    duplicates = len(device) - len(first)

    expected = None
    if table.has(*_MEASURED[:3]):
        # PREDICTED, NOT MEASURED — kept for comparison, never used to place a
        # patch. Scaled the way a .ti3's XYZ is, so the two are in one unit.
        expected = table.numbers(*_MEASURED[:3]) / 100.0

    locations = ()
    if table.has("SAMPLE_LOC"):
        locations = tuple(table.text("SAMPLE_LOC"))

    return Chart(
        name=path.stem, device=device, channels=channels, kind=kind or "CGATS",
        scale=scale, scale_certain=certain, n_rows=len(table),
        duplicates=duplicates, clamped=clamped, locations=locations,
        expected=expected,
        expected_accurate=cgats.keyword(
            tables, "ACCURATE_EXPECTED_VALUES").lower() == "true",
        keywords={k: v for t in reversed(tables) for k, v in t.keywords.items()})


def _scale_of(kind: str, raw: np.ndarray, colour_rep: str):
    """What the file's device numbers run to, and whether that is certain.

    THIS IS THE ERROR THE DESIGN SINGLED OUT, and it is not hypothetical: a
    ``.ti1`` counts to 100 and the i1Profiler text export of the very same
    chart counts to 255. Reading one as the other scales every patch by 2.55
    or by 0.39, and the picture that comes out is smooth, plausible and wrong.

    ``CTI1`` and ``CTI2`` are ArgyllCMS's own formats and are defined as 0..100,
    so those need no guessing. For everything else the file's largest value
    decides: a chart essentially always contains its own white, so a maximum
    near 100 means a percentage and one well above it means a byte. When
    neither holds — a chart with no bright patch at all — 0..100 is assumed and
    ``scale_certain`` is False, so the window can say so instead of quietly
    picking one.
    """
    if kind in CHART_KINDS:
        return 100.0, True
    top = float(np.nanmax(raw)) if raw.size else 0.0
    if top > 100.5:
        return 255.0, True
    if top >= 99.5 or "100" in colour_rep:
        return 100.0, True
    return 100.0, False


#: CxF3's namespace, as X-Rite writes it and as ChromIQ's own exporter does.
_CXF_NS = {"cc": "http://colorexchangeformat.com/CxF3-core"}


def _cxf_root(path: Path):
    import xml.etree.ElementTree as ET
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ChartProblem(f"{path.name} is not readable XML: {exc}") from None


def _cxf_is_chart(path: Path) -> bool:
    root = _cxf_root(path)
    objects = root.findall(".//cc:Object", _CXF_NS)
    if not objects:
        return False
    # A measurement carries ColorValues (what came back); a chart carries only
    # DeviceColorValues (what will be asked for).
    return not root.findall(".//cc:ColorValues", _CXF_NS)


def _read_cxf(path: Path) -> Chart:
    """An i1Profiler ``.pxf`` target, which is CxF3 XML.

    Read here rather than handed to ArgyllCMS, and that is not a preference:
    ``txt2ti3`` refuses these outright — *"doesn't contain field XYZ_X, LAB_L
    or spectral"* — because it converts *measurements*, and a chart has none.
    There is nothing subtle left to parse once the measurements are gone, so
    reading it directly also means this works on a computer with no ArgyllCMS
    installed at all.
    """
    root = _cxf_root(path)
    if root.findall(".//cc:ColorValues", _CXF_NS):
        raise ChartProblem(
            f"{path.name} holds measured colours, so it is a measurement "
            "rather than a chart waiting to be printed. Open it with Open… "
            "instead.")
    objects = root.findall(".//cc:Object", _CXF_NS)
    values, top = [], 0.0
    for obj in objects:
        rgb = obj.find("cc:DeviceColorValues/cc:ColorRGB", _CXF_NS)
        if rgb is None:
            continue
        try:
            triple = [float(rgb.find(f"cc:{c}", _CXF_NS).text)
                      for c in ("R", "G", "B")]
        except (AttributeError, TypeError, ValueError):
            continue
        # CxF3 lets a file declare its own top value; 255 is the default and
        # what both X-Rite and ChromIQ write.
        top = max(top, float(rgb.get("MaxValue", 255)))
        values.append(triple)
    if not values:
        raise ChartProblem(
            f"{path.name} has no RGB patches in it. This reads an i1Profiler "
            "target — the file it saves for a chart to be printed. A .pxf "
            "holding measurements, or one in CMYK, is a different thing.")
    raw = np.asarray(values, dtype=float)
    scale = top or 255.0
    device = raw / scale
    clamped = int(((device < -1e-9) | (device > 1 + 1e-9)).any(axis=1).sum())
    device = np.clip(device, 0.0, 1.0)
    _, first = np.unique(device, axis=0, return_index=True)
    return Chart(name=path.stem, device=device, channels=("R", "G", "B"),
                 kind="CxF3", scale=scale, scale_certain=True,
                 n_rows=len(raw), duplicates=len(raw) - len(first),
                 clamped=clamped)


# --------------------------------------------------------------------------
# Placing the patches — question A and B both need this
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Placement:
    """Where a chart's patches land, according to one profile."""

    lab: np.ndarray            # (N, 3) Lab under the profile's own PCS white
    profile: str               # what to call the profile on screen
    intent: str                # in words, for the caption
    tag: str                   # the ICC tag actually used: A2B1, A2B0, matrix
    xyz: np.ndarray | None = None   # the same colours before a white was chosen

    def under(self, white_point) -> np.ndarray:
        """The same patches as Lab under another white point.

        The profile's own answer is XYZ; Lab is XYZ read against a white. The
        rest of this window lets somebody choose that white, and a chart left
        behind in D50 while every shape around it moved would be drawn in the
        wrong place — quietly, and by a few ΔE, which is the worst size of
        wrong for something being counted in ΔE.

        Asking for D50 gives back exactly what the profile said, because
        inside an ICC profile D50 is not a choice of illuminant — it is the
        connection space, and its white is a constant written into the
        specification rather than the textbook D50 a colour library hands you.
        The two differ in the fourth decimal of Z, which is worth 0.025 ΔE:
        small, and large enough to show up as a difference between this and
        every other reading of the same profile. ``icc_read.PCS_WHITE`` carries
        the number and the measurement behind it.
        """
        from gamutview import xyz_to_lab
        from icc_read import PCS_WHITE
        if self.xyz is None:
            return self.lab
        if isinstance(white_point, str) and white_point.upper() == "D50":
            white_point = PCS_WHITE
        return xyz_to_lab(self.xyz, white_point)


#: The tables to try, best first, and what each one is called in plain words.
#: A2B1 is relative colorimetric — "where would this land" — and it is the
#: right question for a gamut. A2B0 is perceptual and squeezes the whole space
#: to fit, which moves patches that are perfectly reachable; it is a fallback
#: only, and the window says when it was used.
_INTENTS = (("A2B1", "relative colorimetric"),
            ("A2B0", "perceptual (this profile has no relative "
                     "colorimetric table)"))


def through_profile(chart: Chart, profile_path, *, label: str = "") -> Placement:
    """Where this chart's patches land, according to *profile_path*.

    This is a **prediction**, and everything downstream says so. Nothing here
    has been printed.
    """
    from gamutview import xyz_to_lab
    from icc_read import (PCS_WHITE, UnsupportedProfile, _lut_to_pcs,
                          _matrix_to_pcs, describe, read_tags)

    profile_path = Path(profile_path)
    try:
        tags = read_tags(profile_path)
        head = describe(profile_path)
    except UnsupportedProfile as exc:
        raise ChartProblem(f"{profile_path.name} could not be read: {exc}") from None

    wanted = {"RGB": 3, "CMYK": 4}.get(head["space"])
    if wanted is None:
        raise ChartProblem(
            f"{profile_path.name} is a {head['space'] or 'nameless'} profile, "
            "and a chart can only be placed through an RGB or CMYK one.")
    if wanted != chart.device.shape[1]:
        theirs = "RGB" if wanted == 3 else "CMYK"
        mine = "RGB" if chart.is_rgb else "CMYK"
        raise ChartProblem(
            f"{chart.name} is a {mine} chart and {profile_path.name} is a "
            f"{theirs} profile, so the numbers in the chart are not the ones "
            f"this profile knows what to do with. Open the profile the chart "
            f"was built for.")

    for tag, intent in _INTENTS:
        if tag in tags:
            xyz = _lut_to_pcs(tags[tag], chart.device, head["pcs"])
            break
    else:
        if wanted != 3:
            raise ChartProblem(
                f"{profile_path.name} has no lookup table, and only a "
                "three-channel profile can be described by its primaries "
                "alone.")
        xyz = _matrix_to_pcs(tags, chart.device)
        tag, intent = "matrix", "the profile's own primaries and curves"
    return Placement(lab=xyz_to_lab(xyz, PCS_WHITE),
                     profile=label or profile_path.stem,
                     intent=intent, tag=tag, xyz=xyz)


# --------------------------------------------------------------------------
# Question A and B — what falls outside
# --------------------------------------------------------------------------

#: How far outside a surface a patch may sit and still be called "on the edge"
#: rather than "outside", in ΔE2000.
#:
#: NOT A FUDGE, AND THE MEASUREMENT IS WHY. A gamut surface is not an exact
#: object: it is built from a grid of samples, and between the samples the real
#: boundary bulges out a little further than the shape drawn through them.
#: Pushing the 5960-patch ChromIQ verification set through a real printer
#: profile and asking how many patches fell outside *that same profile*:
#:
#:     grid       vertices    outside   worst ΔE   average ΔE
#:      9^3            486        353      0.584        0.063
#:     17^3           1734        262      0.220        0.022
#:     25^3           3750        209      0.185        0.013
#:     33^3           6534        162      0.073        0.008
#:     41^3          10086        122      0.046        0.007
#:
#: The count barely moves and the distance collapses towards nothing. So the
#: count on its own is a bad headline — those patches are ON the surface, and
#: reporting "262 patches outside" would send somebody hunting a fault that is
#: the sampling of the surface they are being measured against.
#:
#: One ΔE2000 is the classic rule of thumb for a difference most people would
#: not notice side by side -- published thresholds run from about 0.8 to 3, so
#: it is a convention and not a cut-off -- and it is an order of magnitude
#: above the error measured here. A patch
#: further out than this is outside for a reason.
EDGE_TOLERANCE = 1.0


@dataclass(frozen=True)
class Outside:
    """How a placed chart fared against one shape."""

    against: str
    n_patches: int
    outside: np.ndarray        # True where the patch falls outside at all
    distance: np.ndarray       # ΔE2000 beyond the surface, 0 where inside
    tolerance: float = EDGE_TOLERANCE

    @property
    def beyond(self) -> np.ndarray:
        """The patches genuinely outside — the ones worth marking."""
        return self.distance > self.tolerance

    @property
    def n_outside(self) -> int:
        return int(self.outside.sum())

    @property
    def n_beyond(self) -> int:
        return int(self.beyond.sum())

    @property
    def n_edge(self) -> int:
        """Outside, but by less than anybody could see."""
        return self.n_outside - self.n_beyond

    @property
    def n_inside(self) -> int:
        return self.n_patches - self.n_outside

    @property
    def worst(self) -> float:
        return float(self.distance.max()) if len(self.distance) else 0.0

    @property
    def average(self) -> float:
        """Averaged over the ones genuinely outside, or 0 when there are none.

        Over *all* patches it would be a number that falls as the chart grows,
        which is the opposite of what somebody reads it as.
        """
        picked = self.distance[self.beyond]
        return float(picked.mean()) if len(picked) else 0.0

    @property
    def all_inside(self) -> bool:
        return self.n_beyond == 0


def outside_report(lab, gamut, *, against: str = "",
                   tolerance: float = EDGE_TOLERANCE) -> Outside:
    """Which patches fall outside *gamut*, and by how far.

    WHICH SURFACE IS BEING TESTED, precisely, because it decides what the
    number means. The test is against **the gamut's own measured boundary** --
    the surface the rest of this application uses when it paints which colours
    a comparison loses, so a chart's answer can never disagree with the
    colouring beside it.

    IT USED TO BE THE CONVEX HULL OF THAT BOUNDARY, and it was described here,
    and on screen, as conservative for it: a hull fills in every dent, so a
    patch sitting in a dent was called inside, and the answer could miss a
    problem but never invent one. That was true of the hull and is no longer
    what happens. Measured on the demo chart against Adobe RGB, the dents hold
    **172 patches the hull called safe**, and a chart's whole purpose is to say
    which patches are not.

    The distance is ΔE2000 from the patch to the nearest point **on that same
    surface** — not to the nearest vertex, which would overstate every answer
    by however far apart the vertices happen to be, and no longer to the hull,
    which understated it to zero for a patch in a shallow dent.
    """
    from gamutview import delta_e_2000, outside_of

    lab = np.asarray(lab, dtype=float)
    good = np.isfinite(lab).all(axis=1)
    outside = np.zeros(len(lab), dtype=bool)
    distance = np.zeros(len(lab), dtype=float)
    if not good.any():
        return Outside(against=against, n_patches=0, outside=outside,
                       distance=distance, tolerance=tolerance)

    verts = np.asarray(
        gamut.vertices if hasattr(gamut, "vertices") else gamut, dtype=float)
    rows = np.nonzero(good)[0]
    # THE GAMUT, NOT ITS POINTS. Stripped to bare vertices the
    # containment test has no surface to measure against and
    # falls back to the convex hull, which is what this whole
    # change is about -- see gamutview._Enclosure.
    out = outside_of(lab[good], gamut)
    outside[rows[out]] = True
    if out.any():
        # THE SAME SURFACE THAT DECIDED "OUTSIDE" MEASURES HOW FAR OUTSIDE.
        nearest = nearest_on_hull(lab[good][out], verts,
                                  getattr(gamut, "faces", None))
        distance[rows[out]] = delta_e_2000(lab[good][out], nearest)
    return Outside(against=against, n_patches=int(good.sum()), outside=outside,
                   distance=distance, tolerance=tolerance)


def nearest_on_hull(points, vertices, faces=None) -> np.ndarray:
    """The closest point on the surface of a gamut, for each of *points*.

    Pass *faces* and the measurement is against the gamut's own triangles.
    Without them there is no surface to measure to and the convex hull of
    *vertices* is used, which is what this did for everything.

    WHY THE HULL WAS NOT GOOD ENOUGH. The question beside this one -- "is this
    patch outside the gamut?" -- is now asked of the real, dented surface. The
    distance was still being measured to the hull thrown around it, and a hull
    lies outside the shape wherever the shape is dented. So a patch could be
    reported as outside and, in the same row, as **0.00 ΔE away from the
    boundary** -- which reads as a rounding error and is really the two halves
    of one row disagreeing about what the boundary is.

    Measured on the demo chart against Adobe RGB: of 172 patches called
    outside, 1 came back at 0.00 ΔE. One row in a table, and it would have
    been read as noise rather than as the contradiction it is.

    Not the closest vertex. On a real gamut the vertices are tens of ΔE apart
    in places, so "distance to the nearest corner" can be several times the
    distance to the surface between the corners — which would turn a patch
    barely outside into an alarming number.

    EVERY TRIANGLE IS MEASURED AGAINST, and that is a deliberate choice over a
    cleverer one. The obvious saving is to look only at the triangles near the
    point, found through its nearest corners. Measured on a real printer gamut,
    that shortlist was wrong by **4.1 ΔE**: the hull of a measured surface has
    long thin triangles, and a triangle can lie close to a point while all
    three of its corners are far from it. A gamut hull has a few hundred to a
    few thousand triangles, so being exact costs a fraction of a second — and a
    number that is quietly wrong by 4 ΔE is worse than no number at all.

    Chunked over the points, because the whole cross-product at once is a
    gigabyte on a large chart and nothing at all in pieces.
    """
    points = np.atleast_2d(np.asarray(points, dtype=float))
    vertices = np.asarray(vertices, dtype=float)
    if faces is None or len(faces) == 0:
        from scipy.spatial import ConvexHull
        triangles = vertices[ConvexHull(vertices).simplices]  # (M, 3, 3)
    else:
        triangles = vertices[np.asarray(faces, dtype=int)]    # (M, 3, 3)

    out = np.empty_like(points)
    # ~2 million point/triangle pairs at a time: a few hundred megabytes of
    # working space at the very most, whatever the size of either side.
    step = max(1, int(2_000_000 // max(1, len(triangles))))
    for start in range(0, len(points), step):
        block = points[start:start + step]
        spots = _closest_on_triangles(block[:, None, :], triangles[None, :, :, :])
        best = ((spots - block[:, None, :]) ** 2).sum(axis=2).argmin(axis=1)
        out[start:start + len(block)] = spots[np.arange(len(block)), best]
    return out


def _ratio(top, bottom):
    """*top* / *bottom*, clipped to 0..1, and 0 where the triangle is degenerate.

    A hull can carry triangles of no area at all — three points in a line, which
    happens wherever a measured surface is locally flat. Dividing by their zero
    would put a NaN into the answer and turn one bad triangle into a chart with
    no figures at all.
    """
    safe = np.where(np.abs(bottom) < 1e-12, 1.0, bottom)
    return np.clip(np.where(np.abs(bottom) < 1e-12, 0.0, top / safe), 0.0, 1.0)


def _closest_on_triangles(point, triangles) -> np.ndarray:
    """The closest point on each triangle to *point*.

    The standard barycentric solution (Ericson, *Real-Time Collision
    Detection*, §5.1.5). It covers all seven regions — the face itself, the
    three edges and the three corners — so a point out beyond a corner does not
    quietly get the projection onto the triangle's plane, which can be far
    closer than any point on the triangle really is.

    Shapes broadcast: ``point`` (..., 3) against ``triangles`` (..., 3, 3), so
    one call can measure many points against many triangles at once.
    """
    a, b, c = triangles[..., 0, :], triangles[..., 1, :], triangles[..., 2, :]
    ab, ac = b - a, c - a

    def dot(u, v):
        return (u * v).sum(axis=-1)

    ap = point - a
    d1, d2 = dot(ab, ap), dot(ac, ap)
    bp = point - b
    d3, d4 = dot(ab, bp), dot(ac, bp)
    cp = point - c
    d5, d6 = dot(ab, cp), dot(ac, cp)

    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4

    # The general case: somewhere on the face itself.
    v = _ratio(vb, va + vb + vc)
    w = _ratio(vc, va + vb + vc)
    out = a + v[..., None] * ab + w[..., None] * ac

    # Then each region the general case gets wrong, innermost first so that a
    # corner always wins over the edge it sits on.
    def instead(where, value):
        return np.where(where[..., None], value, out)

    out = instead((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0),
                  b + _ratio(d4 - d3, (d4 - d3) + (d5 - d6))[..., None] * (c - b))
    out = instead((vb <= 0) & (d2 >= 0) & (d6 <= 0),
                  a + _ratio(d2, d2 - d6)[..., None] * ac)
    out = instead((vc <= 0) & (d1 >= 0) & (d3 <= 0),
                  a + _ratio(d1, d1 - d3)[..., None] * ab)
    out = instead((d1 <= 0) & (d2 <= 0), a)
    out = instead((d3 >= 0) & (d4 <= d3), b)
    out = instead((d6 >= 0) & (d5 <= d6), c)
    return np.broadcast_to(out, np.broadcast_shapes(
        np.shape(point), triangles.shape[:-2] + (3,))).copy()


# --------------------------------------------------------------------------
# Question C — how the patches are spread
# --------------------------------------------------------------------------

#: The axes of the ink-amount view run 0 to 100, because that is what a .ti1
#: and a .ti2 are written in and what ChromIQ, Argyll and every printer dialog
#: call the same thing. Files that count 0 to 255 are already converted to the
#: shared 0..1 by ``read_chart``, so only one number appears here.
DEVICE_AXIS_MAX = 100.0


def device_positions(chart: "Chart") -> np.ndarray:
    """Where the chart's patches sit in ink amounts, as an (N, 3) array.

    NO PROFILE IS INVOLVED AND THAT IS THE POINT. These are the numbers the
    file actually holds — the amounts about to be asked of the printer — so
    they are true of the chart alone and stay true no matter which printer,
    paper or profile it is eventually sent to. Everywhere else in this window
    a chart has no position until a profile is asked where its patches would
    land; here it has one already, because the question is a different one.
    """
    ok, why = can_draw_in_ink(chart)
    if not ok:
        raise ChartProblem(why)
    return np.asarray(chart.device, dtype=float)[:, :3] * DEVICE_AXIS_MAX


def can_draw_in_ink(chart: "Chart") -> tuple:
    """Whether *chart* can go on three ink axes, and plain words if it cannot.

    A picture has three axes. An RGB chart has three ink amounts and fits
    exactly; a CMYK one has four and does not, and there is no honest way to
    flatten it — dropping black or mixing it into the other three would draw a
    chart that was never in the file. Rather than show a lie it says so, and
    the Lab view still works for it, because a profile can place any number of
    channels into the three the eye has.
    """
    n = 0 if chart.device is None else np.asarray(chart.device).shape[1]
    if chart.is_rgb and n == 3:
        return True, ""
    inks = ", ".join(chart.channels) if chart.channels else f"{n} channels"
    return False, (
        f"This chart is {inks}, and the ink-amount view has three axes. "
        f"Choose CIELAB under Draw it in and give it a profile under Placed "
        f"through: a profile can place any number of inks into the three "
        f"axes colour has.")


def skin(points):
    """A closed surface over *points*, as ``(vertices, faces)``.

    WHAT IT IS: the convex hull of the patches themselves — how far out into
    the space this chart reaches, which is a real question about the chart and
    is hard to judge from a cloud of dots alone.

    WHAT IT IS NOT, and the reason this returns bare arrays instead of a
    :class:`gamutview.Gamut`: it is not a gamut, of the printer or of anything
    else, and nothing in this application should be able to treat it as one.
    A gamut carries a volume, feeds the coverage figures and joins the
    comparison; a chart's skin must do none of those, because a chart only
    samples wherever its author chose to put patches. Measured on the demo
    files: the skin over the patches a glossy paper can reach comes out at
    663,257 cubic Lab units against the paper's own measured 724,277 — 8%
    smaller, purely because the chart does not put a patch on every part of
    the boundary. Quoted as a gamut it would understate the paper every time.
    Keeping it out of the ``Gamut`` type is what makes that impossible rather
    than merely discouraged.

    Returns ``(None, None)`` for anything too small or too flat to enclose a
    volume — four points at minimum, and not all in one plane.
    """
    from scipy.spatial import ConvexHull, QhullError

    pts = np.asarray(points, dtype=float)
    pts = pts[np.isfinite(pts).all(axis=1)]
    pts = np.unique(pts.round(9), axis=0)
    if len(pts) < 4:
        return None, None
    try:
        hull = ConvexHull(pts)
    except QhullError:
        # Every patch on one plane — a grey ramp, a single hue sweep. There is
        # no solid to draw and saying so beats drawing a degenerate one.
        return None, None
    return pts, hull.simplices


@dataclass(frozen=True)
class Spread:
    """How evenly a chart samples the space it is placed in."""

    closest: float             # the two patches nearest each other
    largest_gap: float         # the patch furthest from any neighbour
    median_gap: float
    n_patches: int             # after repeats were set aside
    repeats: int               # patches landing exactly where another does


def spread(lab, *, minimum: int = 4) -> "Spread | None":
    """How far apart the patches are, in straight-line Lab distance.

    STRAIGHT-LINE, AND SAID SO. Everything else here reports ΔE2000, which
    asks how different two colours *look*. Spacing is a different question —
    how thoroughly the chart samples the space — and Lab distance answers it
    without pretending to a perceptual judgement it is not making. Mixing the
    two silently would be worse than using either.

    Each patch's distance to its nearest neighbour: the smallest of those is
    where the chart doubles up, and the largest is the widest hole in it.
    Returns None for a chart too small to say anything about.

    REPEATED PATCHES ARE SET ASIDE FIRST. Charts repeat white and black several
    times over for the instrument to calibrate against, and those repeats land
    on exactly the same colour — so "the closest pair are 0.0 apart" comes out
    of every real chart, says nothing, and hides the answer somebody wanted.
    How many were set aside is reported rather than swallowed.
    """
    from scipy.spatial import cKDTree

    lab = np.asarray(lab, dtype=float)
    lab = lab[np.isfinite(lab).all(axis=1)]
    before = len(lab)
    lab = np.unique(lab.round(6), axis=0)
    repeats = before - len(lab)
    if len(lab) < minimum:
        return None
    # k=2 because the nearest point to any patch is itself.
    distances, _ = cKDTree(lab).query(lab, k=2)
    nearest = distances[:, 1]
    return Spread(closest=float(nearest.min()),
                  largest_gap=float(nearest.max()),
                  median_gap=float(np.median(nearest)),
                  n_patches=len(lab), repeats=repeats)
