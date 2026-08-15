"""See the gamut your printer *actually* measured — from a chart measurement.

    python ti3gamut.py mychart.ti3
    python ti3gamut.py mychart.ti3 -o gamut.html --open
    python ti3gamut.py before.ti3 after.ti3        # two papers, one picture

Reads the ``.ti3`` measurement file ArgyllCMS writes when you read a printed
chart, builds the gamut those patches enclose, and writes one self-contained
HTML file you can open in any browser, send to somebody, or keep beside the
measurement. Nothing is uploaded and nothing is fetched: the page carries its
own viewer, so it still works in five years with no network.

WHY THIS IS NOT THE SAME AS A PROFILE'S GAMUT
---------------------------------------------
The usual way to look at a gamut is to ask the finished ICC profile — that is
what ``iccgamut`` does. A profile is a *fitted model* of your printer: it
smooths, it interpolates, and near the edges it can promise a little more or a
little less than the paper really gave.

This asks the *measurements* instead. Every vertex here is a patch that was
printed and read. So the two answer different questions, and the difference
between them is itself worth seeing:

* the profile's gamut — what your printer is *described* as being able to do;
* this one — what it *did*, on that paper, on that day.

COLOUR SCIENCE, STATED PLAINLY
------------------------------
* ``.ti3`` XYZ is scaled to Y = 100 for the perfect diffuser; it is divided by
  100 here.
* Print measurement is referenced to **D50**, so that is the default white
  point, and Lab is computed under it. ``--white D65`` is there for display
  measurements.
* ``--relative`` normalises to the *media* white — the brightest patch — which
  is what a relative-colorimetric profile does and what makes two papers of
  different brightness comparable. Off by default, because the absolute numbers
  are what the instrument actually reported.
* The volume is the one the surface actually encloses, in cubic Lab units —
  the same quantity ArgyllCMS calls "units" and reports for ``iccgamut``, and
  it agrees with iccgamut to one part in 10^8 on the same file. In the default
  mode that is the DENTED boundary, not a hull thrown around it. Comparable
  between two charts measured the same way; not comparable across white points
  or across colour spaces.

Requires: numpy, scipy, plotly.
"""
from __future__ import annotations

import argparse
import re
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from gamutview import build_gamut, xyz_to_lab

# .ti3 device and measurement columns, in the order we want them.
_DEVICE_SETS = (("RGB_R", "RGB_G", "RGB_B"), ("CMYK_C", "CMYK_M", "CMYK_Y", "CMYK_K"))
_XYZ = ("XYZ_X", "XYZ_Y", "XYZ_Z")
_LAB = ("LAB_L", "LAB_A", "LAB_B")


@dataclass(frozen=True)
class Measurement:
    """What one ``.ti3`` holds, reduced to what a gamut needs."""
    name: str
    device: np.ndarray | None     # (N, 3) drive values 0..1, or None if not RGB
    lab: np.ndarray               # (N, 3) CIE Lab under the chosen white point
    instrument: str
    n_patches: int


#: Measurement files that are not .ti3, and the ArgyllCMS tool that turns each
#: into one. Converting rather than parsing is deliberate: these formats have
#: corners (spectral tables, several colour specifications in one file, vendor
#: extensions) and ArgyllCMS already handles them correctly. ChromIQ takes the
#: same approach in workflow/reference_convert.py.
CONVERTERS = {
    ".cxf": "cxf2ti3",
    ".txt": "txt2ti3",
    ".mxf": "cxf2ti3",     # X-Rite's measurement flavour of the same XML
}


def _find_tool(name: str) -> "str | None":
    """Where ArgyllCMS keeps *name*. One search, shared with everything else
    that needs it, so a folder the user chose by hand is honoured everywhere.
    """
    from argyll import find_tool
    return find_tool(name)


def convert_to_ti3(path: Path) -> Path:
    """Turn a measurement file ArgyllCMS understands into a ``.ti3``.

    The converted copy is written to a temporary folder, never beside the
    original: somebody's measurement folder should not gain files because they
    opened something to look at it.
    """
    import subprocess
    import tempfile

    tool_name = CONVERTERS[path.suffix.lower()]
    tool = _find_tool(tool_name)
    if tool is None:
        from argyll import DOWNLOAD_URL
        raise ValueError(
            f"Reading a {path.suffix} file needs ArgyllCMS, which was not "
            f"found on this computer.\n\nIt is free, and it is the same "
            f"toolkit that measures a chart in the first place — so if you "
            f"printed and read this chart yourself, you very likely have it "
            f"already and it is simply somewhere unusual.\n\n"
            f"Get it from {DOWNLOAD_URL}, or, if it is already installed, "
            f"point the viewer at it with Where ArgyllCMS is… under This "
            f"window.\n\n.ti3 measurements, .gam files and ICC profiles "
            f"need none of this and open as they are.")
    out_dir = Path(tempfile.mkdtemp(prefix="gamut-convert-"))
    stem = out_dir / path.stem
    try:
        done = subprocess.run([tool, str(path), str(stem)],
                              capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"{path.name} took too long to convert") from exc
    produced = stem.with_suffix(".ti3")
    if not produced.is_file():
        detail = (done.stderr or done.stdout or "").strip().splitlines()
        why = detail[-1] if detail else f"exit code {done.returncode}"
        raise ValueError(f"{path.name} could not be converted: {why}")
    return produced


def read_measurement(path, white_point: str = "D50",
                     relative: bool = False) -> "Measurement":
    """Read any measurement file this understands, converting when it must."""
    path = Path(path)
    if path.suffix.lower() in CONVERTERS:
        converted = convert_to_ti3(path)
        measured = read_ti3(converted, white_point, relative)
        # Keep the name the user knows it by, not the temporary copy's.
        return Measurement(name=path.stem, device=measured.device,
                           lab=measured.lab, instrument=measured.instrument,
                           n_patches=measured.n_patches)
    return read_ti3(path, white_point, relative)


def read_ti3(path: Path, white_point: str = "D50",
             relative: bool = False) -> Measurement:
    """Parse an ArgyllCMS ``.ti3`` (CGATS) into device values and Lab.

    Only the columns a gamut needs are read; the spectral bands that make these
    files large are skipped. Raises ValueError with a plain reason when the file
    cannot give us what we need — an empty chart, no measurement columns, a
    device space that is not RGB.
    """
    import cgats

    text = path.read_text(errors="replace")

    # A CHART IS NOT A MEASUREMENT, and it is caught here rather than later.
    # A .ti1 carries XYZ columns that came out of targen's device *model*, not
    # off any paper, so it would otherwise read as a perfectly plausible
    # measured gamut made entirely of predictions.
    from chart import CHART_KINDS
    kind = cgats.identifier(text)
    if kind in CHART_KINDS:
        which = "a .ti1" if kind == "CTI1" else "a .ti2"
        raise ValueError(
            f"{path.name} is {which} — a chart waiting to be printed, not a "
            "measurement.\n\nThe XYZ values in it are predictions from a "
            "device model rather than anything read off paper, so drawing it "
            "as a measured gamut would be inventing a result.\n\nOpen it with "
            "Open a chart… instead: the patches are shown as a cloud of "
            "points, placed through a profile you choose, and counted against "
            "whatever else is on screen.")

    try:
        tables = cgats.read_tables(text)
    except cgats.CgatsProblem as exc:
        raise ValueError(f"{path.name}: {exc}") from None

    # THE FIRST TABLE THAT HOLDS MEASUREMENTS. Reading from the first
    # BEGIN_DATA to the last END_DATA is what a two-split reader does, and on
    # any file with more than one table it swallows the headers in between:
    # the first thing the number parser then meets is a word out of a
    # DESCRIPTOR line, and the error names it.
    for table in tables:
        if table.has(*_XYZ) or table.has(*_LAB):
            break
    else:
        raise ValueError(
            f"{path.name} has no XYZ or Lab columns — it may be a chart that "
            "has not been measured yet rather than a measurement")
    if not len(table):
        raise ValueError(f"{path.name} has no measurement rows")

    columns = list(table.columns)
    rows = [list(r) for r in table.rows]

    def column(name: str) -> np.ndarray:
        return table.numbers(name)[:, 0]

    have = set(columns)
    if set(_XYZ) <= have:
        xyz = np.column_stack([column(c) for c in _XYZ]) / 100.0
        if relative:
            # Media white = the brightest patch. A relative-colorimetric view.
            xyz = xyz / xyz[np.argmax(xyz[:, 1])][1] * 1.0
            wp_xyz = xyz[np.argmax(xyz[:, 1])]
            xyz = xyz * (np.array([0.96422, 1.0, 0.82521]) / wp_xyz)
        lab = xyz_to_lab(xyz, white_point)
    elif set(_LAB) <= have:
        lab = np.column_stack([column(c) for c in _LAB])
        if relative:
            raise ValueError(
                "--relative needs XYZ columns; this file carries Lab only, "
                "which is already referenced to a white point")
    else:
        raise ValueError(
            f"{path.name} has no XYZ or Lab columns — it may be a .ti1/.ti2 "
            "(a chart that has not been measured yet) rather than a .ti3")

    device = None
    for names in _DEVICE_SETS:
        if set(names) <= have and len(names) == 3:
            device = np.column_stack([column(c) for c in names]) / 100.0
            break

    instrument = ""
    for line in text.splitlines():
        if line.startswith("TARGET_INSTRUMENT"):
            instrument = line.split('"')[1] if '"' in line else ""
            break

    return Measurement(name=path.stem, device=device, lab=lab,
                       instrument=instrument, n_patches=len(rows))


def neutral_axis(measurement, tolerance: float = 0.02):
    """The greys of a measured chart: what the paper did with equal amounts.

    Every patch whose device values are equal — 10/10/10, 50/50/50 and so on —
    asked the printer for a neutral grey. What came back rarely is one: paper
    is warm or cool, inks are not perfectly balanced, and the drift is usually
    worst in the shadows. A gamut cannot show this at all; the grey axis is a
    thin line through the middle of a solid, and it is what people actually
    notice in a black-and-white print.

    Returns (lab, labels) sorted from black to white, or empty when the chart
    has no equal-value patches — some do not.
    """
    if measurement.device is None:
        return np.empty((0, 3)), []
    dev = measurement.device
    spread = dev.max(axis=1) - dev.min(axis=1)
    picked = np.nonzero(spread <= tolerance)[0]
    if not len(picked):
        return np.empty((0, 3)), []
    lab = measurement.lab[picked]
    order = np.argsort(lab[:, 0])
    lab = lab[order]
    labels = [f"{dev[picked[i]].mean() * 100:.0f}% grey" for i in order]
    return lab, labels


def _to_plot_space(lab, space: str) -> np.ndarray:
    """Lab values to plotted coordinates in *space*.

    Both the grey axis and the patch cloud are computed in Lab -- that is what
    a measurement gives and what "neutral" is defined in -- so drawing them
    beside a gamut built in another space means converting them the same way
    the gamut was.
    """
    from gamutview import AXES, _FROM_XYZ, lab_to_lch_cartesian, lab_to_xyz
    pts = (np.asarray(lab, float) if space == "lab"
           else _FROM_XYZ[space](lab_to_xyz(lab, "D50"), "D50"))
    return lab_to_lch_cartesian(pts) if AXES[space]["cylindrical"] else pts


def ideal_neutral_axis(lab, steps: int = 48):
    """A perfectly neutral axis over the same lightness range, as Lab.

    WHAT "IDEAL" MEANS HERE, precisely: a* = 0 and b* = 0 at every lightness —
    no colour at all, only lightness. That is the definition of neutral under
    the white point everything else on screen is already measured against, so
    the two are directly comparable and nothing is being assumed.

    IT IS DRAWN OVER THE MEASURED RANGE, not from 0 to 100. A printer cannot
    reach either end: its blackest black might be L* 12 and its paper white
    L* 95, and a reference line running past both would invite the reading
    that the printer "failed" to reach lightnesses no paper of that kind can.
    The question this answers is how far the greys LEAN, not how far they
    reach.

    SAMPLED RATHER THAN DRAWN END TO END. In CIELAB a neutral axis really is a
    straight line, but this application also draws in CIE XYZ, where equal
    lightness steps are not equally spaced and the same axis is a curve. Two
    endpoints would be a straight line through the wrong place.
    """
    lab = np.asarray(lab, float)
    if len(lab) < 2:
        return np.empty((0, 3))
    low, high = float(lab[:, 0].min()), float(lab[:, 0].max())
    lightness = np.linspace(low, high, max(2, int(steps)))
    return np.column_stack([lightness, np.zeros_like(lightness),
                            np.zeros_like(lightness)])


def _ideal_neutral_trace(measurement, name: str, colour: str,
                         space: str = "lab"):
    """The perfectly neutral line, drawn as a reference rather than as data.

    Deliberately quiet — thin, dashed and unmarked — because it is not a
    measurement of anything. The eye should read it as the wall the measured
    greys are leaning away from.
    """
    import plotly.graph_objects as go

    lab, _labels = neutral_axis(measurement)
    ideal = ideal_neutral_axis(lab)
    if not len(ideal):
        return []
    pts = _to_plot_space(ideal, space)
    return [go.Scatter3d(
        x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode="lines",
        line=dict(color=colour, width=3, dash="dot"),
        name=f"{name} — perfectly neutral", showlegend=True,
        hovertext=f"a* 0, b* 0 — no colour at all, only lightness",
        hoverinfo="text")]


def _neutral_trace(measurement, name: str, colour: str,
                   space: str = "lab"):
    """The grey axis as a line through the solid, with its patches marked."""
    import plotly.graph_objects as go

    from gamutview import lab_to_lch_cartesian

    lab, labels = neutral_axis(measurement)
    if len(lab) < 2:
        return []
    pts = _to_plot_space(lab, space)
    return [go.Scatter3d(
        x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode="lines+markers",
        line=dict(color=colour, width=5),
        marker=dict(size=3.5, color=colour),
        name=f"{name} — greys", showlegend=True,
        text=[f"{lbl}: a* {p[1]:+.1f}, b* {p[2]:+.1f}"
              for lbl, p in zip(labels, lab)],
        hoverinfo="text")]


def _plot_points(gamut) -> np.ndarray:
    """Where each vertex goes on screen, for whichever space it is in.

    CIELAB and CIELUV are both opponent spaces: two colour axes and lightness,
    which read best rearranged into a hue circle around a vertical L*. CIE XYZ
    is not -- it has no lightness axis and no hue angle -- so it is drawn
    exactly as measured. Asking for a hue circle there would invent structure
    that is not in the space.
    """
    from gamutview import AXES
    if AXES[gamut.space]["cylindrical"]:
        return gamut.cylindrical()
    return gamut.vertices


def _rings(gamut, name: str, count: int, colour: str, width: float = 1.5,
           key: str | None = None):
    """Contour rings stacked inside a gamut, at evenly spaced lightnesses.

    The wire cage shows only the outer surface, because that is what a gamut
    is -- a solid with a boundary, not a lattice with structure inside. But an
    empty cage tells you nothing about how the shape narrows between black and
    white, which is exactly what decides whether mid-tones or highlights are
    the tight part. Stacking the cross-sections inside the cage shows that,
    and reuses the same slicing the flat view uses, so the two always agree.
    """
    import plotly.graph_objects as go

    from gamutview import lab_to_lch_cartesian, slice_at

    lows, highs = gamut.vertices[:, 0].min(), gamut.vertices[:, 0].max()
    xs, ys, zs = [], [], []
    for step in range(1, count + 1):
        level = lows + (highs - lows) * step / (count + 1)
        try:
            ring = slice_at(gamut, level, steps=90)
        except Exception:      # noqa: BLE001 — one bad level is not fatal
            continue
        if not len(ring):
            continue
        lab = np.column_stack([np.full(len(ring), level), ring])
        pts = lab_to_lch_cartesian(lab)
        pts = np.vstack([pts, pts[:1]])          # close the loop
        xs += list(pts[:, 0]) + [None]
        ys += list(pts[:, 1]) + [None]
        zs += list(pts[:, 2]) + [None]
    if not xs:
        return []
    rings = go.Scatter3d(x=xs, y=ys, z=zs, mode="lines",
                         line=dict(color=colour, width=width),
                         name=f"{name} (rings inside)",
                         showlegend=key is None, hoverinfo="name")
    if key is None:
        return [rings]
    return [rings, _legend_line(f"{name} (rings inside)", key)]


def _band(colour: str, steps: int = 32) -> str:
    """A colour rounded to a coarse band, so a cage needs few traces."""
    try:
        r, g, b = (int(v) for v in colour[4:-1].split(","))
    except (ValueError, IndexError):
        return colour
    q = [min(255, (v // steps) * steps + steps // 2) for v in (r, g, b)]
    return f"rgb({q[0]},{q[1]},{q[2]})"


def _edges(gamut, name: str, colour: str = "#9aa3b2", width: float = 1.0,
           paint: str = "plain", index: int = 0, key: str | None = None):
    """The triangle edges of a gamut, as a wire cage.

    A solid shape hides whatever is inside it. Drawn as a cage instead, an
    outer gamut can be seen through: which is the only way to look at a
    printer sitting inside sRGB, or inside everything the eye can see, and
    still see the printer. Every edge is drawn once — a triangle mesh shares
    each edge between two triangles, and drawing both doubles the work for an
    identical picture.

    The cage can be painted the same ways the solid can. Plotly gives a line
    one colour per trace rather than per point, so a coloured cage is drawn as
    several traces -- one per band of colour. Plain grey stays the default: it
    is a single trace, by far the cheapest, and on top of a solid shape a grey
    cage reads more clearly than a coloured one competing with the colours
    underneath it.
    """
    import plotly.graph_objects as go
    v = _plot_points(gamut)
    f = gamut.faces
    seen = set()
    xs, ys, zs = [], [], []
    for tri in f:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (a, b) if a < b else (b, a)
            if key in seen:
                continue
            seen.add(key)
            xs += [v[a, 0], v[b, 0], None]
            ys += [v[a, 1], v[b, 1], None]
            zs += [v[a, 2], v[b, 2], None]
    if paint == "plain":
        cage = go.Scatter3d(x=xs, y=ys, z=zs, mode="lines",
                            line=dict(color=colour, width=width),
                            name=f"{name} (outline)", showlegend=key is None,
                            hoverinfo="name")
        if key is None:
            return [cage]
        return [cage, _legend_line(f"{name} (outline)", key)]

    per_vertex = _paint_vertices(gamut, paint, index)
    if per_vertex is None:                       # "true": each point's colour
        per_vertex = [f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
                      for r, g, b in gamut.colors]
    bands: dict = {}
    seen_again = set()
    for tri in f:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (a, b) if a < b else (b, a)
            if key in seen_again:
                continue
            seen_again.add(key)
            # Group by a COARSENED colour: one trace per distinct colour gave
            # 491 traces for a single cage, which the browser draws slowly for
            # a picture the eye reads as a smooth gradient anyway. Rounding
            # each channel to the nearest 32 leaves a few dozen bands.
            bands.setdefault(_band(per_vertex[a]), []).append((a, b))
    traces = []
    for i, (edge_colour, edges) in enumerate(sorted(bands.items())):
        bx, by, bz = [], [], []
        for a, b in edges:
            bx += [v[a, 0], v[b, 0], None]
            by += [v[a, 1], v[b, 1], None]
            bz += [v[a, 2], v[b, 2], None]
        traces.append(go.Scatter3d(
            x=bx, y=by, z=bz, mode="lines",
            line=dict(color=edge_colour, width=width),
            name=f"{name} (outline)", legendgroup=f"{name}-outline",
            showlegend=(i == 0), hoverinfo="name"))
    return traces


#: Colour used for the part of a gamut that the comparison cannot reach. A
#: warm red against the muted grey of the reachable part, so the eye goes
#: straight to what is lost without needing the legend.
_LOST = "rgb(232,23,93)"
_KEPT = "rgb(105,112,126)"


def _mesh_lost(gamut, name: str, opacity: float, lost,
               kept: str = _KEPT, depth: float = 0.35, light=None) -> "list":
    """The gamut painted by what the comparison cannot reproduce."""
    import plotly.graph_objects as go
    v = _plot_points(gamut)
    colours = [_LOST if bad else kept for bad in lost]
    v, colours, faces = _weld(v, colours, gamut.faces)
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        vertexcolor=colours, opacity=opacity, flatshading=False,
        lighting=_lighting(depth),
        lightposition=light or _LIGHT_OVERHEAD,
        name=f"{name} — red is out of reach", showlegend=True,
        hoverinfo="name")


#: A distinct colour per shape, for when telling them apart matters more than
#: seeing what colours they hold.
_FLAT = ("rgb(232,23,93)", "rgb(58,168,208)", "rgb(242,199,68)",
         "rgb(107,208,122)", "rgb(157,124,216)")


#: Hue bands, and the accent hue each maps to. Mirrors ChromIQ's own
#: _THEME_ACCENTS (workflow/gamut_viewer.py:88) so the two applications tint a
#: gamut the same way: (from, to, accent hue, saturation).
_ACCENT_BANDS = (
    (330, 360, 345, 0.995),
    (  0,  30, 345, 0.995),
    ( 30,  80,  39, 0.990),
    ( 80, 165, 158, 0.600),
    (165, 210, 190, 0.630),
    (210, 330, 254, 1.000),
)

#: Lightness cap when remapping. Without it the gamut's white tip stays pure
#: white whatever hue it is given, and the brightest part of the shape loses
#: the tint entirely. ChromIQ caps at the same value for the same reason.
_ACCENT_L_CAP = 0.92


def _accent_vertices(gamut) -> list:
    """Every vertex tinted into the application's own accent family.

    Keeps each point's LIGHTNESS -- so the shape still reads as a shape, with
    its own highlights and shadows -- and moves its HUE into the accent
    family. Near-grey points stay grey rather than being forced into a colour
    they never had.

    The hue is moved SMOOTHLY. Snapping each colour to the nearest of six
    accent hues is the obvious way to do it and produces visible banding: six
    flat regions with hard seams where the shape crosses from one to the next.
    Interpolating between the accent hues keeps the sweep continuous, so the
    gamut still looks like a gamut and only its palette has changed.

    The control points are ChromIQ's own bands, used as anchors rather than
    buckets, so both applications land on the same colours -- this just fills
    in between them.
    """
    import colorsys

    src = np.array([(lo + hi) / 2.0 for lo, hi, _h, _s in _ACCENT_BANDS])
    dst = np.array([h for _lo, _hi, h, _s in _ACCENT_BANDS], dtype=float)
    sat = np.array([sa for _lo, _hi, _h, sa in _ACCENT_BANDS], dtype=float)
    order = np.argsort(src)
    src, dst, sat = src[order], dst[order], sat[order]
    # Close the circle at both ends, so a hue near 0 or 360 interpolates
    # across the seam instead of clamping to the first or last anchor.
    src_w = np.concatenate(([src[-1] - 360.0], src, [src[0] + 360.0]))
    dst_u = np.degrees(np.unwrap(np.radians(dst)))
    dst_w = np.concatenate(([dst_u[-1] - 360.0], dst_u, [dst_u[0] + 360.0]))
    sat_w = np.concatenate(([sat[-1]], sat, [sat[0]]))

    # A straight interpolation between six anchors is continuous but its RATE
    # is not: the hue turns at a different speed on each side of every anchor,
    # and where the map stretches a narrow band across a wide one, touching
    # vertices come out further apart in colour than they are in measurement.
    #
    # Building the map once as a dense table and smoothing it around the
    # circle removes those corners. The anchors still decide where each hue
    # ends up; this only stops the speed changing abruptly at them. Measured
    # on a real gamut it takes the worst step between neighbouring vertices
    # from 1.41x the true colours' own worst step to close to 1.
    grid = np.arange(0.0, 360.0, 1.0)
    hue_lut = np.interp(grid, src_w, dst_w)
    sat_lut = np.interp(grid, src_w, sat_w)
    window = 61   # degrees, either side blended
    kernel = np.hanning(window)
    kernel /= kernel.sum()
    pad = window // 2

    def _smooth_circular(values):
        wrapped = np.concatenate((values[-pad:], values, values[:pad]))
        return np.convolve(wrapped, kernel, mode="valid")

    # Hue is smoothed as a vector so the wrap at 360 does not average to the
    # opposite side of the circle.
    # SMOOTHING ALONE IS NOT ENOUGH, and it is worth saying why. Blurring the
    # map moves the steepness around but cannot remove it: six accents spaced
    # unevenly around the circle mean some stretches of hue are compressed and
    # others stretched whatever shape the curve has. Measured, widening the
    # blur from 31 to 121 degrees only took the worst step from 1.41x to 1.31x
    # of what the real colours do.
    #
    # So the RATE is limited directly. The map is differentiated, any stretch
    # faster than `max_rate` is clipped, and the result is re-integrated and
    # rescaled to close the circle again. That bounds how far apart two
    # touching vertices can be pushed, which is exactly the thing that reads
    # as a rough edge.
    max_rate = 1.25
    step = np.diff(np.concatenate((hue_lut, [hue_lut[0] + 360.0])))
    step = np.clip(step, 0.0, max_rate)
    step *= 360.0 / step.sum()                 # still one full turn
    hue_lut = (hue_lut[0] + np.concatenate(([0.0], np.cumsum(step)[:-1]))) % 360.0

    radians = np.radians(hue_lut)
    hue_lut = np.degrees(np.arctan2(_smooth_circular(np.sin(radians)),
                                    _smooth_circular(np.cos(radians)))) % 360.0
    sat_lut = _smooth_circular(sat_lut)

    colours = np.clip(np.asarray(gamut.colors, dtype=float), 0.0, 1.0)
    out = []
    for r, g, b in colours:
        h, l, s = colorsys.rgb_to_hls(float(r), float(g), float(b))
        l = min(l, _ACCENT_L_CAP)
        # NO BRANCH. A hard "below this saturation it is grey" test puts a
        # visible seam wherever the surface crosses that line, and a ramp with
        # a clamp puts two fainter ones at each end of the ramp. Measured on a
        # real gamut, those seams made the worst colour step between touching
        # vertices 1.4x what the real colours do.
        #
        # Instead the amount of colour fades in smoothly with a smoothstep, so
        # near-greys stay grey, vivid colours are fully tinted, and everything
        # between is a continuous blend with no edge anywhere.
        deg = h * 360.0
        index = int(deg) % 360
        new_h = float(hue_lut[index])
        reach = float(sat_lut[index])
        t = min(1.0, max(0.0, (s - 0.04) / 0.26))
        t = t * t * (3.0 - 2.0 * t)               # smoothstep: flat at both ends
        nr, ng, nb = colorsys.hls_to_rgb(new_h / 360.0, l, reach * t)
        out.append(f"rgb({int(nr * 255)},{int(ng * 255)},{int(nb * 255)})")
    return out


def _paint_vertices(gamut, paint: str, index: int) -> "list | None":
    """The colour of every vertex, for the chosen way of painting.

    Returns None for the plain case so the caller can use the gamut's own
    colours without copying them.
    """
    if paint == "true":
        return None
    if paint == "solid":
        return [_FLAT[index % len(_FLAT)]] * len(gamut.vertices)
    if paint == "accent":
        return _accent_vertices(gamut)
    v = gamut.vertices
    if paint == "lightness":
        t = np.clip(v[:, 0] / 100.0, 0, 1)
    else:                                   # chroma
        c = np.hypot(v[:, 1], v[:, 2])
        t = np.clip(c / max(1e-6, c.max()), 0, 1)
    # A ramp that stays readable on either background: dark blue-grey to warm
    # white, rather than pure black to pure white which loses an end each time.
    lo, hi = np.array([44, 52, 68]), np.array([250, 246, 236])
    rgb = (lo + (hi - lo) * t[:, None]).astype(int)
    return [f"rgb({r},{g},{b})" for r, g, b in rgb]


def _lighting(depth: float) -> dict:
    """Plotly lighting for a given amount of shape definition.

    At 0 the surface is lit flat and shows only its colours; turning it up
    trades some of that for shading, which is what makes a rounded thing look
    rounded. Kept as one number because "ambient, diffuse, specular, roughness
    and fresnel" is not a question anybody wants to be asked.
    """
    d = max(0.0, min(1.0, depth))
    return dict(ambient=0.95 - 0.45 * d, diffuse=0.10 + 0.75 * d,
                specular=0.02 + 0.18 * d, roughness=0.95 - 0.5 * d,
                fresnel=0.02 + 0.1 * d)


@dataclass(frozen=True)
class Drift:
    """How far two measurements of the same chart have moved apart."""
    matched: int          # patches found in both
    total_a: int
    total_b: int
    worst: float          # the largest single difference
    average: float
    rms: float
    over_one: int         # patches a careful eye would notice
    over_three: int       # patches anybody would notice
    worst_patches: list   # [(label, dE, lab_before, lab_after)], worst first


def compare_measurements(before, after, *, top: int = 8) -> Drift:
    """Patch-by-patch difference between two measurements of the same chart.

    This is the drift check: the same paper and printer measured on two days,
    or before and after a nozzle clean, or two sheets from the same run. The
    gamut view answers "how much colour is there"; this answers "has anything
    moved", which a gamut cannot show — a shape can be identical in size and
    quite different in content.

    Patches are matched on the DEVICE values, not on the sample number,
    because charts are usually randomised and the same colour rarely carries
    the same number twice. It refuses rather than guesses when too little
    matches: two different charts would otherwise produce a confident figure
    describing nothing.
    """
    from gamutview import delta_e_2000

    if before.device is None or after.device is None:
        raise ValueError(
            "Both measurements need the device values that were asked for, "
            "and at least one of these files does not carry them. Without "
            "them there is no way to tell which patch corresponds to which.")

    def index(m):
        out = {}
        for i, dev in enumerate(np.round(m.device, 5)):
            out.setdefault(tuple(dev), i)      # first wins, as read
        return out

    ia, ib = index(before), index(after)
    shared = [k for k in ia if k in ib]
    if not shared:
        raise ValueError(
            "These two measurements have no patches in common, so they are "
            "not two readings of the same chart. Comparing them patch by "
            "patch would produce a number that describes nothing.")
    smaller = min(len(ia), len(ib))
    if len(shared) < 0.5 * smaller:
        raise ValueError(
            f"Only {len(shared)} of {smaller} patches appear in both files, "
            "which is too few to call these the same chart. Patch-by-patch "
            "comparison needs two readings of one chart; for two different "
            "charts, compare the gamuts instead.")

    lab_a = np.array([before.lab[ia[k]] for k in shared])
    lab_b = np.array([after.lab[ib[k]] for k in shared])
    de = delta_e_2000(lab_a, lab_b)
    order = np.argsort(de)[::-1][:top]
    worst = [(f"R{k[0]*100:.0f} G{k[1]*100:.0f} B{k[2]*100:.0f}",
              float(de[i]), lab_a[i].tolist(), lab_b[i].tolist())
             for i, k in ((int(j), shared[int(j)]) for j in order)]
    return Drift(matched=len(shared), total_a=before.n_patches,
                 total_b=after.n_patches, worst=float(de.max()),
                 average=float(de.mean()),
                 rms=float(np.sqrt((de ** 2).mean())),
                 over_one=int((de > 1.0).sum()),
                 over_three=int((de > 3.0).sum()), worst_patches=worst)


def _as_rgb_array(colours):
    """Colours as an (N, 3) float array in 0..1, whatever form they arrive in.

    Returns None when nothing usable can be made of them, so the caller can
    fall back rather than raise: a legend key is decoration, and no colour
    scheme is worth losing the whole picture over.
    """
    if colours is None:
        return None
    try:
        first = colours[0]
    except (IndexError, TypeError, KeyError):
        return None
    if isinstance(first, str):
        out = []
        for text in colours:
            found = re.findall(r"[\d.]+", str(text))
            if len(found) >= 3:
                out.append([float(found[0]) / 255.0, float(found[1]) / 255.0,
                            float(found[2]) / 255.0])
        return np.asarray(out, dtype=float) if out else None
    try:
        arr = np.asarray(colours, dtype=float)
    except (TypeError, ValueError):
        return None
    if arr.ndim != 2 or arr.shape[1] < 3:
        return None
    return arr[:, :3]


def _caption(text: str, colours) -> dict:
    """The line of text above the picture, as a caption rather than a banner.

    Plotly's default title is large, centred and in the foreground colour,
    which made a sentence of explanation the loudest thing on the page --
    louder than the shape it describes. This is small, dimmed, monospace to
    match the figures underneath, and pulled in from the edges so it never
    touches the frame.

    Used by both the main view and the slice view, because the same window
    showing two different kinds of title is worse than either choice.
    """
    return dict(
        text=text,
        x=0.012, xanchor="left", y=0.98, yanchor="top",
        pad=dict(l=6, r=18, t=4),
        font=dict(size=12, color=colours["caption"],
                  family='Menlo, Consolas, "Courier New", monospace'))


def _legend_line(name: str, colour: str):
    """A legend key for a cage, in a colour of its own.

    The cage itself is drawn light, because hundreds of thin lines on a pale
    page add up to a dark mass if each one is the weight of text. One key in
    the legend is the opposite case: a single short line that has to be seen,
    with nothing to add up with. So the key is drawn at full weight while the
    cage stays light, and a line key rather than a dot keeps saying *outline*
    -- which is how the legend tells a cage from a solid at a glance.
    """
    import plotly.graph_objects as go

    return go.Scatter3d(
        x=[None], y=[None], z=[None], mode="lines",
        line=dict(color=colour, width=4),
        name=name, showlegend=True, hoverinfo="skip")


def _legend_proxy(name: str, colour: str):
    """A legend key that is not shaded by the scene's lighting.

    Plotly draws a mesh's own key by rendering a tiny piece of that mesh --
    lighting, opacity and all -- so on a dark page the key comes out far
    darker than the colour given to it, and the marker beside the name is
    barely there. Reported twice from the real window.

    A scatter trace with no points solves it: it never draws anything in the
    scene, and its legend key is a plain filled marker in exactly the colour
    asked for. The mesh keeps its name for hover; only the key moves.
    """
    import plotly.graph_objects as go

    return go.Scatter3d(
        x=[None], y=[None], z=[None], mode="markers",
        marker=dict(size=11, color=colour, line=dict(width=0)),
        name=name, showlegend=True, hoverinfo="skip")


def _legend_swatch(colours, page: str) -> str:
    """A colour for the legend key that both represents the shape and can be
    seen against the page.

    A mesh painted with ``vertexcolor`` has no single colour, so Plotly draws
    its legend key in a default that is almost invisible on a dark page -- the
    little marker before the name disappears and the legend stops being a key
    to anything.

    The average of the colours actually used is the honest representative. It
    is then lifted (on a dark page) or deepened (on a light one) only as far
    as it must be to stay legible, so it still looks like the shape it stands
    for rather than becoming a generic swatch.
    """
    # Two shapes reach here: a Gamut's own (N, 3) float array, and the
    # "rgb(r,g,b)" strings the paint schemes produce. Both are normal, so both
    # are handled rather than one of them crashing the whole page.
    arr = _as_rgb_array(colours)
    if arr is None or not len(arr):
        return "#9aa3b2"
    mean = arr.mean(axis=0)
    # Relative luminance, and the page's, on the same 0..1 scale.
    def lum(rgb):
        return float(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])
    page_rgb = np.array([int(page[i:i + 2], 16) / 255.0 for i in (1, 3, 5)])
    dark_page = lum(page_rgb) < 0.5
    # Plotly shades the legend key with the trace's own lighting, so it
    # draws DARKER than the colour given. Aiming at what looks right
    # unshaded leaves a key that is still hard to see, so the dark-page
    # target is set well above it.
    target = 0.68 if dark_page else 0.42
    have = lum(mean)
    if dark_page and have < target:
        mean = mean + (1.0 - mean) * ((target - have) / max(1e-6, 1.0 - have))
    elif not dark_page and have > target:
        mean = mean * (target / max(1e-6, have))
    r, g, b = (int(round(float(np.clip(c, 0.0, 1.0)) * 255)) for c in mean)
    return f"#{r:02x}{g:02x}{b:02x}"


def light_position(direction_deg: float, height: float) -> dict:
    """Where the light hangs, from a compass bearing and a height.

    Plotly wants x, y and z. Asking somebody for three coordinates to place a
    lamp is asking them to solve a puzzle; asking which side it shines from
    and how high it is, is asking a question about a room. The radius is fixed
    and large so only the DIRECTION matters -- moving a light nearer a shape
    of this size would change the brightness rather than the modelling, which
    is what the intensity controls are for.
    """
    import math

    radians = math.radians(direction_deg)
    reach = 2000.0
    lift = max(-1.0, min(1.0, height))
    flat = math.sqrt(max(0.0, 1.0 - lift * lift))
    return dict(x=reach * flat * math.cos(radians),
                y=reach * flat * math.sin(radians),
                z=reach * lift)


#: Where the light hangs when nobody has moved it: overhead.
_LIGHT_OVERHEAD = dict(x=0, y=0, z=2000)


def _weld(points, colours, faces):
    """Join vertices that sit in the same place and carry the same colour.

    A boundary built from the faces of the device cube repeats every point
    along the twelve edges where two faces meet -- on a real 1168-patch chart
    that is 27% of them. Two copies of a corner cannot share a normal, so the
    renderer shades each one on its own and lays a crease along every seam:
    the surface looks chipped and grainy where it is in fact continuous.

    This changes no geometry, no colour and no volume -- only which triangles
    agree about a corner. The dents stay: they are real, they are the whole
    point of following the measured boundary, and nothing here smooths them.
    """
    keys, order, keep = [], {}, []
    for point, colour in zip(points, colours):
        keys.append((tuple(np.round(point, 6)),
                     colour if isinstance(colour, str)
                     else tuple(np.atleast_1d(np.round(colour, 6)))))
    remap = np.empty(len(keys), dtype=np.int64)
    for i, key in enumerate(keys):
        at = order.get(key)
        if at is None:
            at = order[key] = len(keep)
            keep.append(i)
        remap[i] = at
    if len(keep) == len(keys):
        return points, colours, faces
    kept = np.asarray(keep)
    welded = ([colours[i] for i in kept] if isinstance(colours, list)
              else np.asarray(colours)[kept])
    return points[kept], welded, remap[np.asarray(faces)]


def _mesh(gamut, name: str, opacity: float, wireframe: bool,
          paint: str = "true", index: int = 0, depth: float = 0.35,
          page: str = "#111318", light=None):
    """One Plotly mesh for a gamut, painted the way the user asked."""
    import plotly.graph_objects as go
    v = _plot_points(gamut)
    chosen = _paint_vertices(gamut, paint, index)
    colours = chosen if chosen is not None else [
        f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
        for r, g, b in gamut.colors]
    v, colours, faces = _weld(v, colours, gamut.faces)
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        vertexcolor=colours, opacity=opacity, name=name, showlegend=False,
        # Only the legend key uses this; vertexcolor paints the surface.
        color=_legend_swatch(chosen if chosen is not None else gamut.colors,
                             page),
        flatshading=False, hoverinfo="name",
        lighting=_lighting(depth),
        # THE LIGHT THE USER PLACED. Fixed overhead here, this argument was
        # accepted and then dropped, so Set the lighting myself moved nothing.
        lightposition=light or _LIGHT_OVERHEAD,
        contour=dict(show=wireframe, color="#888", width=2),
    )


def _chart_skin(points, colours, name: str, style: str, opacity: float,
                page: str = "#111318", light=None, depth: float = 0.35):
    """A closed surface over a chart's patches — never over the lost ones.

    ONLY EVER THE ONES THAT SURVIVE, and that is a measured decision rather
    than a preference. The out-of-reach patches are the ones furthest out, so
    they *wrap around* the ones that fit: a hull over them came to 87% of a
    hull over the whole chart in ink amounts and 77% in CIELAB. A shape drawn
    round them would fill nearly the entire picture and read as "almost all of
    this is lost" on a chart where a third of it is. There is no honest shape
    for a set of points that surrounds another set, so none is offered.

    *style* is ``"solid"``, ``"mesh"`` or ``"outline"``. ``colours`` may be
    ``None`` for a plain grey skin, which is the readable choice when the dots
    inside it are already carrying the colour.
    """
    import plotly.graph_objects as go

    verts, faces = points, None
    if isinstance(points, tuple):
        verts, faces = points
    if verts is None or faces is None or not len(faces):
        return []
    verts = np.asarray(verts, float)
    faces = np.asarray(faces, int)
    wire = style in ("mesh", "outline")
    common = dict(
        x=verts[:, 0], y=verts[:, 1], z=verts[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        name=f"{name} — a skin over the patches", showlegend=False,
        hoverinfo="name", flatshading=False,
        lighting=_lighting(depth), lightposition=light or _LIGHT_OVERHEAD,
        contour=dict(show=wire, color="#888", width=2),
    )
    if style == "outline":
        # The cage alone: no filled facets at all, so everything inside stays
        # readable. Opacity near zero rather than a separate trace type keeps
        # the contour lines that carry the shape.
        common["opacity"] = 0.02
    else:
        common["opacity"] = float(opacity)
    key = "#8b93a3"
    if colours is None:
        common["color"] = "#8b93a3"
    elif isinstance(colours, str):
        # One colour for the whole skin — the window's accent.
        common["color"] = colours
        key = colours
    else:
        common["vertexcolor"] = colours
        common["color"] = _legend_swatch(colours, page)
        key = common["color"]
    # A PROXY FOR THE KEY, like every other surface here: Plotly draws a
    # mesh's own key by rendering a scrap of that mesh, lighting and opacity
    # included, so at a low opacity on a dark page the marker beside the name
    # all but disappears.
    return [go.Mesh3d(**common),
            _legend_proxy(f"{name} — a skin over the patches", key)]


def _patch_cloud(lab, name: str, space: str = "lab"):
    """Every measured patch as a dot, in its own colour — the raw evidence."""
    import plotly.graph_objects as go
    from gamutview import xyz_to_srgb, lab_to_xyz
    v = _to_plot_space(lab, space)
    rgb = xyz_to_srgb(lab_to_xyz(lab, "D50"), "D50")
    return go.Scatter3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2], mode="markers",
        marker=dict(size=2.5, color=[f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"
                                     for r, g, b in rgb]),
        name=f"{name} — patches", showlegend=True, hoverinfo="name")


def _chart_cloud(lab, name: str, outside=None, space: str = "lab",
                 device=None, size: float = 3.2, show_inside: bool = True,
                 show_outside: bool = True, with_positions: bool = False,
                 dot_opacity: float = 1.0, out_size: float = 5.5,
                 out_opacity: float = 1.0, page: str = "#111318"):
    """A chart's patches: dots where a profile says each one would land.

    DOTS, NEVER A SURFACE, and that is the whole design rather than a
    preference. These patches have not been printed. A shape thrown around a
    set of *requested* ink amounts is not the gamut of anything, and the
    picture would claim one.

    Drawn a little larger than the measured-patch cloud, with a thin outline,
    so that a chart on top of a solid still reads. Where *outside* marks the
    patches that fall beyond the shape being judged, those are drawn in the
    same red this application uses everywhere for "out of reach", in a ring
    twice the size — the eye should find them without reading a number.

    IN INK AMOUNTS the dots are positioned from *device* instead — the three
    numbers the file actually holds, 0 to 100 — and no profile is needed to
    put them somewhere true. A profile is still worth having, because it is
    the only thing that can say what colour each one will come out; without
    one the dots are painted with the ink amounts read as screen colour,
    which is a legend, not a prediction, and the window says so beside them.
    """
    import plotly.graph_objects as go
    from gamutview import lab_to_xyz, xyz_to_srgb

    device_space = space == "rgb"
    if device_space:
        if device is None:
            raise ValueError(
                "drawing a chart in ink amounts needs the device values; "
                "Lab cannot be turned back into ink without inverting a "
                "profile, and this window does not pretend it can")
        v = np.asarray(device, float)
        n = len(v)
    else:
        if lab is None:
            raise ValueError(
                f"a chart drawn in {space} needs a profile to say where its "
                f"patches land; only ink amounts can be drawn without one")
        lab = np.asarray(lab, float)
        v = _to_plot_space(lab, space)
        n = len(lab)

    # Colour comes from the profile's answer whenever there is one, in every
    # space. Only a chart drawn in ink amounts with no profile falls back to
    # the ink amounts as screen colour.
    if lab is not None:
        rgb = xyz_to_srgb(lab_to_xyz(np.asarray(lab, float), "D50"), "D50")
    else:
        rgb = np.clip(np.asarray(device, float) / 100.0, 0.0, 1.0)
    colours = [f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
               for r, g, b in rgb]
    if outside is None:
        outside = np.zeros(n, dtype=bool)
    outside = np.asarray(outside, dtype=bool)

    traces = []
    inside = ~outside
    if inside.any() and show_inside:
        kept = [c for c, keep in zip(colours, inside) if keep]
        traces.append(go.Scatter3d(
            x=v[inside, 0], y=v[inside, 1], z=v[inside, 2], mode="markers",
            marker=dict(size=size, opacity=dot_opacity, color=kept,
                        line=dict(width=0)),
            # THE KEY IS DRAWN SEPARATELY. Given a list of colours Plotly
            # keys the legend on the FIRST of them, and the first patch of a
            # chart is very often black — RGB 0,0,0 is where targen starts —
            # so the marker beside the name vanished into a dark page
            # entirely. The same fault the meshes already had, and the same
            # cure: a proxy carrying a colour that represents the cloud and
            # can still be seen. Reported from the real window.
            showlegend=False, hoverinfo="name",
            name=f"{name} — to be printed"))
        traces.append(_legend_proxy(f"{name} — to be printed",
                                    _legend_swatch(kept, page)))
    if outside.any() and show_outside:
        traces.append(go.Scatter3d(
            x=v[outside, 0], y=v[outside, 1], z=v[outside, 2], mode="markers",
            marker=dict(size=out_size, opacity=out_opacity, color=_LOST,
                        symbol="circle", line=dict(width=0)),
            # One flat colour, so its own key is already right — except that
            # a low opacity is carried into the key and fades it away.
            showlegend=out_opacity > 0.6, hoverinfo="name",
            name=f"{name} — outside"))
        if out_opacity <= 0.6:
            traces.append(_legend_proxy(f"{name} — outside", _LOST))
    if not with_positions:
        return traces
    # THE POINTS A SKIN MAY GO OVER: the ones that survive, never the lost
    # ones — see _chart_skin for the measurement behind that. Handed back
    # rather than recomputed so the skin and the dots cannot disagree.
    keep = inside if outside.any() else np.ones(n, dtype=bool)
    positions = (v[keep], [c for c, k in zip(colours, keep) if k])
    return traces, positions


#: Colours for the outlines in a slice, in the order gamuts are given.
_SLICE_COLOURS = ("#e8175d", "#3aa8d0", "#f2c744", "#6bd07a")


#: The page's own background. Plotly draws its plot on whatever the page is,
#: and a plain HTML page is white -- which shows as a bright frame around a
#: dark scene, and as a white flash every time the view reloads.
#: The scene's own colours, per appearance. Passed in rather than looked up,
#: so the page and the window around it can never disagree about which mode it
#: is showing.
#: The 3D scene's own colours. The page matches the fill ChromIQ gives its
#: gamut viewer exactly (gamut_panel.py:86) -- #111111 dark, #efebe6 light --
#: so a scene dropped into that panel has no seam at its edge, and the text
#: and grid come from ChromIQ's own tokens for the same reason.
#: ``wire`` is a DENSE FIELD of thin lines and ``mark`` is a single small
#: symbol, so the two cannot share a value. A cage of hundreds of edges adds
#: up: on a light page a text-weight grey turned the whole cage into a dark
#: mass that shouted down the measured shape it is only there to frame, and at
#: the rims, where the lines converge, it went nearly solid. The cage is
#: therefore a good deal lighter than the text on the same page, while one
#: 5-pixel marker still needs the full contrast to be seen at all.
SCENE_COLOURS = {
    "dark": dict(page="#111111", plot="#141414", grid="#262626",
                 caption="#8a8a8a",   # TEXT_DIM: readable, not shouting
                 text="#e6e6e6", axis="#333333", kept="rgb(105,112,126)",
                 wire="#9aa3b2", mark="#9aa3b2"),
    "light": dict(page="#efebe6", plot="#f7f4ef", grid="#e0ddd7",
                  caption="#7a7570",  # LM_TEXT_DIM
                  text="#22211f", axis="#d0ccc6", kept="rgb(176,180,188)",
                  wire="#a8a4a0",     # LM_TEXT_FAINT: a cage, not a wall
                  mark="#7a7570"),    # LM_TEXT_DIM: one symbol, full weight
}

_PAGE_BACKGROUND = "#111318"


#: Keeps two scenes pointing the same way. Taken from ChromIQ's own
#: cqLinkCameras (workflow/patch_cube.py), including the two subtleties that
#: make it work: the live camera during a drag lives on the scene's internal
#: object rather than in the layout, and only the view being driven is allowed
#: to lead -- otherwise the two push each other back and forth for ever.
_LINK_CAMERAS_JS = """
function cqLinkCameras(idA, idB) {
  var a = document.getElementById(idA), b = document.getElementById(idB);
  if (!a || !b) return;
  var active = null, wheelTimer = null;
  function liveCam(gd) {
    try {
      var s = gd._fullLayout && gd._fullLayout.scene && gd._fullLayout.scene._scene;
      if (s && s.getCamera) return s.getCamera();
    } catch (e) {}
    return gd.layout && gd.layout.scene && gd.layout.scene.camera;
  }
  function arm(gd) {                      // a wheel has no mouseup to end it
    active = gd;
    if (wheelTimer) clearTimeout(wheelTimer);
    wheelTimer = setTimeout(function () { active = null; }, 300);
  }
  a.addEventListener("mousedown", function () { active = a; }, true);
  b.addEventListener("mousedown", function () { active = b; }, true);
  window.addEventListener("mouseup", function () { active = null; }, true);
  a.addEventListener("wheel", function () { arm(a); }, true);
  b.addEventListener("wheel", function () { arm(b); }, true);
  function link(src, dstId) {
    function sync() {
      if (active !== src) return;         // only the driven view leads
      var c = liveCam(src);
      if (c) Plotly.relayout(dstId, {"scene.camera": c});
    }
    src.on("plotly_relayouting", sync);   // continuously, during the gesture
    src.on("plotly_relayout", sync);      // and once it is let go
  }
  link(a, idB); link(b, idA);
}
"""


#: Turns the shape by itself. Two ways, because they answer two questions: all
#: the way round is for getting the feel of a shape you have just opened, and a
#: small swing back and forth is for JUDGING A DENT -- the parallax reads depth
#: on a flat screen the way a still picture never can, without throwing away
#: the viewpoint you chose.
#:
#: Four things it must never do, each of which is a rule in the code below:
#:
#: 1. Fight the user. Any mouse gesture stops it at once, and it waits until
#:    they have finished before moving again. A wheel has no mouseup, so the
#:    pause is a timer, the same idiom cqLinkCameras uses.
#: 2. Undo their zoom or their tilt. Only the horizontal angle is driven; the
#:    distance and the height are read back from the live camera every frame,
#:    so whatever they set is kept.
#: 3. Drag them back to an angle they deliberately left. Back-and-forth takes
#:    its centre from wherever the camera is when they let go.
#: 4. Spin a hidden window. A page nobody is looking at does no work.
#:
#: Both scenes are driven from here rather than through cqLinkCameras, which
#: deliberately lets only the view being DRAGGED lead -- with nobody dragging,
#: the follower would never move.
_SPIN_JS = """
window.cqSpin = (function () {
  var ids = [], on = false, raf = null, last = 0, held = 0;
  var axes = {turn: {mode: "swing", speed: 8, range: 60, phase: 0},
              tilt: {mode: "off",   speed: 6, range: 40, phase: 0}};

  function scene(id) {
    var gd = document.getElementById(id);
    return (gd && gd._fullLayout) ? gd : null;
  }
  function liveCam(gd) {          // during a drag the real camera is internal
    try {
      var s = gd._fullLayout.scene && gd._fullLayout.scene._scene;
      if (s && s.getCamera) return s.getCamera();
    } catch (e) {}
    return gd.layout && gd.layout.scene && gd.layout.scene.camera;
  }
  function setCam(gd, cam) {
    var s = null;
    try { s = gd._fullLayout.scene._scene; } catch (e) {}
    if (s && s.setCamera) s.setCamera(cam);          // cheap: no relayout
    else if (window.Plotly) Plotly.relayout(gd, {"scene.camera": cam});
  }
  function cross(a, b) {
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]];
  }
  function unit(v) {
    var n = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
    return n > 1e-9 ? [v[0] / n, v[1] / n, v[2] / n] : null;
  }
  function rot(v, k, a) {         // Rodrigues: turn v about unit axis k
    var c = Math.cos(a), s = Math.sin(a);
    var d = k[0] * v[0] + k[1] * v[1] + k[2] * v[2];
    var x = cross(k, v);
    return [v[0] * c + x[0] * s + k[0] * d * (1 - c),
            v[1] * c + x[1] * s + k[1] * d * (1 - c),
            v[2] * c + x[2] * s + k[2] * d * (1 - c)];
  }
  function rest() {
    axes.turn.phase = 0; axes.tilt.phase = 0;
  }
  function hold() { held = Date.now(); rest(); }
  function watch(gd) {
    if (gd._cqSpinWatched) return;
    gd._cqSpinWatched = true;
    ["mousedown", "wheel", "touchstart", "touchmove"].forEach(function (ev) {
      gd.addEventListener(ev, hold, true);
    });
  }
  // HOW FAR TO MOVE THIS FRAME -- an increment, never an absolute angle. It is
  // what makes a drag or a zoom survive: nothing is ever forced back to a
  // remembered position, so whatever the user set is simply carried along. It
  // also gives back-and-forth its centre for free -- the phase is reset when
  // they let go, so the swing starts again from wherever they left it.
  function advance(a, dt) {
    if (a.mode === "off" || !(a.speed > 0)) return 0;
    var rate = a.speed * Math.PI / 180;
    if (a.mode === "round") return rate * dt;
    var half = a.range / 2 * Math.PI / 180;
    if (!(half > 0)) return 0;
    var was = a.phase;
    // Eased with a sine, so it slows into each turning point instead of
    // snapping. The setting is the PEAK rate, which is what makes one speed
    // mean the same thing whichever way it is moving.
    a.phase += rate / half * dt;
    return half * (Math.sin(a.phase) - Math.sin(was));
  }
  function step(id, turn, tilt) {
    var gd = scene(id); if (!gd) return;
    watch(gd);
    var cam = liveCam(gd); if (!cam || !cam.eye) return;
    var c = cam.center || {x: 0, y: 0, z: 0};
    var e = [cam.eye.x - c.x, cam.eye.y - c.y, cam.eye.z - c.z];
    var u = cam.up ? [cam.up.x, cam.up.y, cam.up.z] : [0, 0, 1];
    if (turn) {                   // left and right: a turntable about L*
      e = rot(e, [0, 0, 1], turn);
      u = rot(u, [0, 0, 1], turn);
    }
    if (tilt) {
      // UP AND DOWN TUMBLES THE WHOLE CAMERA, up vector and all. Simply
      // raising the eye is a turntable, and a turntable cannot go over the
      // top: at the pole the view has no left or right left to it and the
      // picture flips. Turning the eye AND its up about the same axis has no
      // pole at all, so a full tumble is as smooth as any other part of it.
      var side = unit(cross(e, u));
      if (side) { e = rot(e, side, tilt); u = rot(u, side, tilt); }
    }
    setCam(gd, {up: {x: u[0], y: u[1], z: u[2]}, center: c,
                eye: {x: c.x + e[0], y: c.y + e[1], z: c.z + e[2]}});
  }
  function frame(now) {
    if (!on) { raf = null; return; }
    raf = window.requestAnimationFrame(frame);
    var dt = (now - last) / 1000; last = now;
    if (document.hidden) return;
    if (!isFinite(dt) || dt <= 0) return;
    if (dt > 0.1) dt = 0.1;       // back from a hidden tab: step, do not jump
    if (Date.now() - held < 400) return;          // their gesture, not ours
    // ONE set of increments for the whole frame, so two rooms that are meant
    // to point the same way stay together to the last decimal.
    var turn = advance(axes.turn, dt), tilt = advance(axes.tilt, dt);
    if (!turn && !tilt) return;
    for (var i = 0; i < ids.length; i++) step(ids[i], turn, tilt);
  }
  // FOR SAVING A MOVING PICTURE. The frames are stepped to exact angles
  // rather than left to run in real time: that closes the loop precisely, and
  // it takes as long as drawing takes instead of as long as the movement
  // would have lasted.
  function nudge(turnDeg, tiltDeg) {
    var turn = (turnDeg || 0) * Math.PI / 180;
    var tilt = (tiltDeg || 0) * Math.PI / 180;
    if (!turn && !tilt) return;
    for (var i = 0; i < ids.length; i++) step(ids[i], turn, tilt);
  }
  function set(o) {
    if (o.ids !== undefined) { ids = o.ids; rest(); }
    ["turn", "tilt"].forEach(function (which) {
      var got = o[which]; if (!got) return;
      var a = axes[which];
      if (got.mode !== undefined && got.mode !== a.mode) { a.mode = got.mode; a.phase = 0; }
      if (got.range !== undefined && got.range !== a.range) { a.range = got.range; a.phase = 0; }
      if (got.speed !== undefined) a.speed = got.speed;
    });
    if (o.on !== undefined) { if (o.on && !on) rest(); on = !!o.on; }
    if (on && raf === null) {
      last = (window.performance || Date).now();
      raf = window.requestAnimationFrame(frame);
    }
  }
  return {set: set, nudge: nudge};
})();
"""


#: The flat equivalent of cqLinkCameras: zoom or pan one cross-section and
#: the other follows, so the two always show the same patch of colour space.
#: Without it, zooming into the reds on the left while the right still shows
#: everything makes two shapes look wildly different sizes -- which is the one
#: thing a side-by-side comparison must never do.
_LINK_AXES_JS = """
function cqLinkAxes(idA, idB) {
  var a = document.getElementById(idA), b = document.getElementById(idB);
  if (!a || !b) return;
  var busy = false;
  function follow(src, dstId) {
    src.on("plotly_relayout", function (change) {
      if (busy || !change) return;                 // do not answer ourselves
      var want = {};
      ["xaxis.range[0]", "xaxis.range[1]",
       "yaxis.range[0]", "yaxis.range[1]"].forEach(function (k) {
        if (change[k] !== undefined) want[k] = change[k];
      });
      if (change["xaxis.autorange"] !== undefined) {
        want["xaxis.autorange"] = change["xaxis.autorange"];
        want["yaxis.autorange"] = change["yaxis.autorange"];
      }
      if (!Object.keys(want).length) return;
      busy = true;
      Plotly.relayout(dstId, want).then(function () { busy = false; },
                                        function () { busy = false; });
    });
  }
  follow(a, idB); follow(b, idA);
}
"""


def _spin_script(ids, spin) -> str:
    """The turning engine plus the settings the window had when it was written.

    A saved page keeps whatever was on screen when it was saved, so a page sent
    to somebody arrives doing what the sender was looking at.
    """
    if not spin:
        return ""
    import json

    settings = dict(spin)
    settings["ids"] = list(ids)
    return (f"<script>{_SPIN_JS}\nwindow.addEventListener('load', function () "
            f"{{window.cqSpin.set({json.dumps(settings)});}});</script>")


def write_side_by_side_html(pages, out: Path, mode: str = "dark",
                            linked: bool = True, spin=None) -> Path:
    """Two scenes in one page, each with its own shape, side by side.

    Overlaying two gamuts is the right way to see where one reaches past the
    other, and the wrong way to judge either on its own -- the front shape
    hides the back one, and whichever is drawn second looks bigger. Two rooms
    side by side answers the other question: what does each of these actually
    look like?

    *pages* is a list of (title, plotly figure). They are written into one
    document rather than two, because two separate pages cannot keep their
    cameras together, and a comparison where the two halves face different
    ways compares nothing.
    """
    import plotly.io as pio

    colours = SCENE_COLOURS["light" if mode == "light" else "dark"]
    blocks, first_id = [], None
    ids = []
    flat = False                       # set per page; safe when there are none
    for i, (caption, fig) in enumerate(pages):
        # Centre the shape in ITS OWN half: give the scene the full width of
        # the pane and no legend gutter, or each one drifts toward the divider
        # and the two look misaligned even when they are identical.
        # A FLAT SLICE HAS NO SCENE. Handing a 2D figure a scene domain adds
        # an empty 3D scene to the page and leaves the chart sized for a
        # legend that is no longer there.
        flat = not any(getattr(t, "type", "") == "scatter3d"
                       or getattr(t, "type", "") == "mesh3d" for t in fig.data)
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
        if not flat:
            fig.update_layout(scene=dict(domain=dict(x=[0, 1], y=[0, 1])))
        div = pio.to_html(fig, include_plotlyjs=(i == 0), full_html=False,
                          div_id=f"scene{i}",
                          config={"displaylogo": False, "responsive": True,
                                  "scrollZoom": True})
        ids.append(f"scene{i}")
        blocks.append(f'<div class="half"><div class="cap">{caption}</div>'
                      f'{div}</div>')
    # PLOTLY MUST BE TOLD TO RE-MEASURE. A plot created inside a flex item
    # sizes itself to the width it saw at creation -- the full page -- and only
    # re-measures on a window resize. In two half-width panes that means each
    # shape is drawn for a box twice as wide as the one it is in, so it spills
    # over the divider and looks off-centre. Resizing them once after load,
    # and again whenever the window changes, puts each shape in the middle of
    # its own half.
    resize = ("<script>function cqFit(){["
              + ",".join(f"'{i}'" for i in ids)
              + "].forEach(function(id){var d=document.getElementById(id);"
                "if(d&&window.Plotly)Plotly.Plots.resize(d);});}"
                "window.addEventListener('load',function(){cqFit();"
                "setTimeout(cqFit,60);});"
                "window.addEventListener('resize',cqFit);"
                "if(window.ResizeObserver){"
                "var ro=new ResizeObserver(cqFit);ro.observe(document.body);}"
                "</script>")
    link = ""
    if linked and len(ids) == 2:
        joiner = "cqLinkAxes" if flat else "cqLinkCameras"
        body = _LINK_AXES_JS if flat else _LINK_CAMERAS_JS
        link = (f"<script>{body}\n"
                f"window.addEventListener('load', function() {{"
                f"{joiner}('{ids[0]}', '{ids[1]}');}});</script>")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
 html,body {{ margin:0; padding:0; height:100%; overflow:hidden;
              background:{colours['page']}; }}
 .row  {{ display:flex; height:100%; width:100%; }}
 .half {{ flex:1 1 0; min-width:0; display:flex; flex-direction:column; }}
 .half + .half {{ border-left:1px solid {colours['grid']}; }}
 .cap  {{ height:22px; line-height:22px; padding:0 10px; font-size:12px;
          color:{colours['caption']}; background:{colours['page']};
          font-family:Menlo,Consolas,"Courier New",monospace;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
 .half > div:last-child {{ flex:1 1 auto; min-height:0; }}
</style></head><body><div class="row">{''.join(blocks)}</div>{resize}{link}{_spin_script(ids, None if flat else spin)}</body></html>"""
    Path(out).write_text(html, encoding="utf-8")
    return Path(out)


def _write_dark_html(fig, out: Path, mode: str = "dark", spin=None,
                     carry_viewer: bool = True, notes: str = "") -> Path:
    """Write the figure as a page whose paper matches the application.

    *carry_viewer* decides whether the drawing library travels inside the file.
    Measured on a real chart: carrying it costs 4778 kB and the page opens for
    ever with no network at all; fetching it when opened costs 41 kB and needs
    the internet the first time. A hundred and sixteen times smaller is worth
    offering, and being the default would quietly break the promise this
    application makes everywhere else, so it is not.
    """
    # A KNOWN div id, so the turning engine has something to address. Plotly
    # invents a random one otherwise, and nothing outside the figure can find
    # it afterwards.
    html = fig.to_html(include_plotlyjs="inline" if carry_viewer else "cdn",
                       full_html=True, div_id="scene0")
    _PAGE_BACKGROUND = SCENE_COLOURS["light" if mode == "light" else "dark"]["page"]
    style = (f"<style>html,body{{background:{_PAGE_BACKGROUND};margin:0;"
             f"padding:0;overflow:hidden;}}</style>")
    if "</head>" in html:
        html = html.replace("</head>", style + "</head>", 1)
    else:
        html = style + html
    if notes:
        # THE NUMBERS TRAVEL WITH THE PICTURE. A shape sent to somebody
        # without them is a shape they cannot check, and "which paper was
        # that?" is where every one of these ends up otherwise.
        colours = SCENE_COLOURS["light" if mode == "light" else "dark"]
        block = ("<div style=\"font:13px/1.6 -apple-system,Segoe UI,Roboto,"
                 f"sans-serif;color:{colours['text']};background:"
                 f"{colours['page']};padding:14px 22px 22px;white-space:pre-wrap"
                 f"\">{notes}</div>")
        html = (html.replace("</body>", block + "</body>", 1)
                if "</body>" in html else html + block)
    turn = _spin_script(["scene0"], spin)
    if turn:
        html = (html.replace("</body>", turn + "</body>", 1)
                if "</body>" in html else html + turn)
    Path(out).write_text(html, encoding="utf-8")
    return Path(out)


def slice_extent(gamuts, lightness: float):
    """One square range covering every shape's cross-section, or None.

    THE WHOLE POINT OF SHOWING TWO SLICES SIDE BY SIDE is that their sizes can
    be compared, and left alone each pane scales to fit whatever is in it --
    so a small gamut and a large one are drawn exactly the same size and the
    picture says the opposite of the truth. One range, worked out from every
    shape at once, and both panes use it.

    Square, because a* and b* are the same units: a range that is wider than
    it is tall would stretch the shape and make a round gamut look oval.
    """
    from gamutview import slice_at

    lows, highs = [], []
    for _name, g in gamuts:
        try:
            ring = slice_at(g, lightness)
        except Exception:              # noqa: BLE001
            continue
        if len(ring):
            lows.append(ring[:, :2].min(axis=0))
            highs.append(ring[:, :2].max(axis=0))
    if not lows:
        return None
    low = np.min(np.vstack(lows), axis=0)
    high = np.max(np.vstack(highs), axis=0)
    centre = (low + high) / 2.0
    half = float(np.max(high - low)) / 2.0
    half = max(half, 1.0) * 1.08       # a little air, never a zero-width axis
    return ((float(centre[0] - half), float(centre[0] + half)),
            (float(centre[1] - half), float(centre[1] + half)))


def build_slice_figure(gamuts, lightness: float, title: str,
                       mode: str = "dark", extent=None, legend: bool = True,
                       first: int = 0):
    """A flat cross-section through every gamut at one lightness.

    Two 3D shapes hide each other and depth on a flat screen is guesswork; two
    outlines on a flat chart are simply readable. Colour runs left to right and
    front to back exactly as it does in the 3D view, so the two pictures agree.
    """
    import plotly.graph_objects as go

    from gamutview import slice_at

    c = SCENE_COLOURS["light" if mode == "light" else "dark"]
    fig = go.Figure()
    empty = []
    for i, (name, g) in enumerate(gamuts):
        try:
            ring = slice_at(g, lightness)
        except Exception:      # noqa: BLE001 — one bad shape must not blank the view
            ring = []
        if not len(ring):
            empty.append(name)
            continue
        closed = np.vstack([ring, ring[:1]])       # join the ends
        fig.add_trace(go.Scatter(
            x=closed[:, 0], y=closed[:, 1], mode="lines",
            # KEEP THE COLOUR EACH SHAPE HAS IN THE OVERLAID VIEW. Split into
            # two panes, each figure holds one shape and would otherwise call
            # it the first -- so both cuts came out the same colour and stopped
            # matching the shapes they came from.
            line=dict(color=_SLICE_COLOURS[(first + i) % len(_SLICE_COLOURS)],
                      width=3),
            name=name, fill="toself", opacity=0.35))
    note = ""
    if empty:
        which = empty[0] if len(empty) == 1 else " and ".join(empty)
        note = (f"  —  {which} does not reach this lightness"
                if len(empty) == 1 else
                f"  —  {which} do not reach this lightness")
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers",
                             marker=dict(color=c["mark"], size=5, symbol="x"),
                             name="neutral grey", hoverinfo="name"))
    fig.update_layout(
        title=_caption((f"{title}  ·  " if title else "")
                       + f"lightness L* = {lightness:.0f}{note}", c),
        xaxis=dict(title="a*   green ← → red", zeroline=True,
                   zerolinecolor=c["axis"], gridcolor=c["grid"],
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(title="b*   blue ← → yellow", zeroline=True,
                   zerolinecolor=c["axis"], gridcolor=c["grid"]),
        paper_bgcolor=c["page"], plot_bgcolor=c["plot"], font_color=c["text"],
        legend=dict(orientation="h", y=-0.12, itemclick="toggle",
                    itemdoubleclick="toggleothers"), showlegend=legend,
        margin=dict(l=0, r=0, t=54, b=0))
    if extent is not None:
        # BOTH PANES ON ONE RANGE, so their sizes mean something. autorange
        # has to be turned off by name: with an equal-units constraint in
        # force, Plotly re-derives the range from the data unless told not to,
        # and each pane quietly went back to fitting its own shape -- which is
        # precisely the lie this is here to prevent.
        fig.update_layout(
            xaxis=dict(range=list(extent[0]), autorange=False,
                       constrain="domain"),
            yaxis=dict(range=list(extent[1]), autorange=False,
                       constrain="domain"))
    return fig


def write_slice_html(gamuts, out: Path, lightness: float, title: str,
                     mode: str = "dark") -> Path:
    """One page holding one flat cross-section. See :func:`build_slice_figure`."""
    _write_dark_html(build_slice_figure(gamuts, lightness, title, mode), out,
                     mode)
    return out


def write_html(gamuts, out: Path, title: str, **kwargs) -> Path:
    """One self-contained page holding one scene. See :func:`build_figure`."""
    mode = kwargs.get("mode", "dark")
    # Not a drawing option: it is what the page DOES once drawn, so it never
    # reaches build_figure.
    spin = kwargs.pop("spin", None)
    carry = kwargs.pop("carry_viewer", True)
    notes = kwargs.pop("notes", "")
    return _write_dark_html(build_figure(gamuts, title, **kwargs), out, mode,
                            spin=spin, carry_viewer=carry, notes=notes)


def build_figure(gamuts, title: str, opacity: float | None = None,
                 points: bool = False, patches=None,
                 aspect: str = "data", styles=None, lost=None,
                 mode: str = "dark", paint: str = "true",
                 depth: float = 0.35, mesh_paint: str = "plain",
                 rings: int = 0, per_shape=None, neutrals=None,
                 ideal_neutrals: bool = False, chart=None,
                 light=None, grid: bool = True, space=None,
                 chart_look=None):
    """One self-contained page: plotly.js is inlined, so it works offline.

    *opacity* overrides the default (opaque alone, semi-transparent when two
    are shown so the inner one stays visible). *points* also plots every
    measured patch, which shows where the chart sampled densely and where it
    left the boundary to guesswork.

    *space* names the axes when there is nothing to read them off. Normally
    the first gamut says which space everything was built in; a chart drawn
    in ink amounts has no gamut beside it at all, and defaulting to Lab there
    would label a cube of ink percentages a*, b*, L*.
    """
    import plotly.graph_objects as go
    c = SCENE_COLOURS["light" if mode == "light" else "dark"]
    _axes_space = space or (gamuts[0][1].space if gamuts else "lab")
    if gamuts and space and gamuts[0][1].space != space:
        raise ValueError(
            f"asked to label the axes {space!r} while the shapes were built "
            f"in {gamuts[0][1].space!r}; that would read the picture against "
            f"the wrong axes")
    fig = go.Figure()
    base = opacity if opacity is not None else (1.0 if len(gamuts) == 1 else 0.55)
    for i, (name, g) in enumerate(gamuts):
        # Each shape may carry its own settings. Anything it does not name
        # falls back to the window-wide value, so a caller that knows nothing
        # about per-shape settings still gets exactly what it asked for.
        own = (per_shape[i] if per_shape is not None and i < len(per_shape)
               else {})
        paint_i = own.get("paint", paint)
        base_i = own.get("opacity", base)
        depth_i = own.get("depth", depth)
        rings_i = own.get("rings", rings)
        mesh_paint_i = own.get("mesh_paint", mesh_paint)
        how = (styles[i] if styles is not None and i < len(styles) else "solid")
        marked = lost[i] if lost is not None and i < len(lost) else None
        if marked is not None:
            fig.add_trace(_mesh_lost(g, name, base_i, marked, c["kept"],
                                     depth_i, light=light))
        elif how in ("solid", "solid+mesh"):
            fig.add_trace(_mesh(g, name, opacity=base_i, wireframe=False,
                                paint=paint_i, index=i, depth=depth_i,
                                page=c["page"], light=light))
            fig.add_trace(_legend_proxy(
                name, _legend_swatch(_paint_vertices(g, paint_i, i)
                                     or g.colors, c["page"])))
        if how in ("mesh", "solid+mesh"):
            for trace in _edges(g, name, colour=c["wire"],
                                width=1.0 if how == "mesh" else 0.7,
                                paint=("plain" if mesh_paint_i == "plain"
                                       else paint_i),
                                index=i, key=c["mark"]):
                fig.add_trace(trace)
        if rings_i:
            for trace in _rings(g, name, rings_i, c["wire"], key=c["mark"]):
                fig.add_trace(trace)
        if neutrals is not None and i < len(neutrals) and neutrals[i] is not None:
            if ideal_neutrals:
                # THE REFERENCE GOES DOWN FIRST, so the measured greys are
                # drawn over it rather than hidden behind it.
                for trace in _ideal_neutral_trace(neutrals[i], name,
                                                  "#9aa3b2", _axes_space):
                    fig.add_trace(trace)
            for trace in _neutral_trace(neutrals[i], name, "#ff6b6b",
                                        _axes_space):
                fig.add_trace(trace)
        if points and patches is not None and i < len(patches):
            fig.add_trace(_patch_cloud(patches[i], name, _axes_space))
    # THE CHART GOES ON LAST, so its dots sit over every surface rather than
    # behind them. Drawn even when there is no gamut at all: a chart placed
    # through a profile is a picture in its own right, and returning an empty
    # scene for one would look like a fault.
    if chart is not None:
        # Four items since ink amounts became drawable; the fourth is the
        # device values. Older three-item callers still work and simply
        # cannot be drawn in ink amounts, which is what they meant.
        chart_name, chart_lab, chart_outside = chart[:3]
        chart_device = chart[3] if len(chart) > 3 else None
        look = dict(skin="none", skin_opacity=0.30, skin_colour="grey",
                    dot_size=3.2, dot_opacity=1.0, out_dot_size=5.5,
                    out_dot_opacity=1.0, accent="#ff4573",
                    show_inside=True, show_outside=True)
        look.update(chart_look or {})
        # THE SKIN GOES DOWN FIRST so the dots read over it rather than
        # through it, and it is built from the very same positions the dots
        # are drawn at — passed back out of _chart_cloud rather than worked
        # out again here, so the two cannot describe different points.
        traces, positions = _chart_cloud(
            chart_lab, chart_name, chart_outside, _axes_space,
            device=chart_device, size=look["dot_size"],
            dot_opacity=look["dot_opacity"], out_size=look["out_dot_size"],
            out_opacity=look["out_dot_opacity"], page=c["page"],
            show_inside=look["show_inside"], show_outside=look["show_outside"],
            with_positions=True)
        if look["skin"] != "none" and positions is not None:
            import chart as _chart_mod
            surviving, colours = positions
            verts, faces = _chart_mod.skin(surviving)
            # NOT called `how`: that name is already the per-gamut style
            # inside this function, and quietly reusing it is how a later
            # edit ends up reading the wrong one.
            skin_how = look["skin_colour"]
            skin_paint = (None if skin_how == "grey" else
                          look["accent"] if skin_how == "accent" else colours)
            for trace in _chart_skin(
                    (verts, faces), skin_paint,
                    chart_name, look["skin"], look["skin_opacity"],
                    page=c["page"], light=light, depth=depth):
                fig.add_trace(trace)
        for trace in traces:
            fig.add_trace(trace)
    from gamutview import AXES
    # The axes are named for the space the gamuts were built in, so a
    # picture can never be read against the wrong labels.
    _axes = AXES[_axes_space]
    fig.update_layout(
        # A caption, not a headline. Plotly's default title is large and
        # centred, which made a line of explanatory text the loudest thing on
        # the page -- louder than the shape it describes. Small, dimmed, set
        # in the same monospace the figures below use, and moved to the left
        # so it reads as a label on the picture rather than a banner over it.
        title=_caption(title, c),
        scene=dict(
            xaxis_title=_axes["x"], yaxis_title=_axes["y"],
            zaxis_title=_axes["z"],
            aspectmode=aspect,
            # START A LITTLE FURTHER BACK, AND ABOVE. Plotly's default camera
            # frames the data tightly, which on a wide, flat gamut crops the
            # corners and opens on a close-up of the middle. Pulling the eye
            # out shows the whole shape at once; anybody who wants a closer
            # look can still scroll in.
            #
            # The height matters as much as the distance. A printer gamut is
            # about twice as wide in a*/b* as it is tall in L*, so a low eye
            # looks at it nearly edge-on and it reads as a flat sheet — the
            # lightness axis, which is half of what there is to see, collapses.
            # Keeping the eye above the default's 35 degrees rather than below
            # it shows the shape as a solid. Distance and elevation have to be
            # raised together; scaling x and y alone flattens the view.
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.5)),
            # THE BOX AROUND THE SHAPE, or nothing at all. Turned off, the
            # walls, the grid, the numbers and the axis names all go with it
            # and the shape is left floating on the page -- which is what a
            # picture for somebody else usually wants, and which takes the
            # scale away, which is why it is not the default.
            xaxis=dict(backgroundcolor=c["plot"], gridcolor=c["grid"],
                       visible=grid),
            yaxis=dict(backgroundcolor=c["plot"], gridcolor=c["grid"],
                       visible=grid),
            zaxis=dict(backgroundcolor=c["plot"], gridcolor=c["grid"],
                       visible=grid),
        ),
        paper_bgcolor=c["page"], font_color=c["text"],
        legend=dict(orientation="h", y=-0.02, itemclick="toggle",
                    itemdoubleclick="toggleothers"),
        margin=dict(l=0, r=0, t=54, b=0),
    )
    return fig


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Build a 3D gamut from a measured ArgyllCMS .ti3 chart.",
        epilog="Example: python ti3gamut.py glossy.ti3 matte.ti3 --relative --open")
    p.add_argument("ti3", nargs="+", type=Path,
                   help="one or more .ti3 measurement files")
    p.add_argument("-o", "--out", type=Path, default=None,
                   help="output HTML (default: <first file>-gamut.html)")
    p.add_argument("--white", default="D50", help="white point (default D50)")
    p.add_argument("--relative", action="store_true",
                   help="normalise to the media white, so papers of different "
                        "brightness compare fairly")
    p.add_argument("--hull", action="store_true",
                   help="convex hull only, ignoring device values (over-states "
                        "the gamut; useful to see by how much)")
    p.add_argument("--open", action="store_true",
                   help="open the result in your browser when it is written")
    a = p.parse_args(argv)

    gamuts, clouds = [], []
    for path in a.ti3:
        if not path.is_file():
            print(f"error: no such file: {path}", file=sys.stderr)
            return 2
        try:
            m = read_ti3(path, a.white, a.relative)
            g = build_gamut(m.lab, None if a.hull else m.device,
                            input_space="lab", white_point=a.white)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        gamuts.append((m.name, g))
        clouds.append(m.lab)
        mode = {"hull": "convex hull", "device-cube": "device boundary"}[g.mode]
        print(f"  {m.name}")
        print(f"    {m.n_patches} patches"
              + (f", measured with {m.instrument}" if m.instrument else ""))
        print(f"    gamut volume {g.volume:,.0f} cubic Lab units ({mode})")
        if m.device is None and not a.hull:
            print("    no RGB device columns — fell back to the convex hull")

    if len(gamuts) == 2:
        a_vol, b_vol = gamuts[0][1].volume, gamuts[1][1].volume
        bigger, smaller = max(a_vol, b_vol), min(a_vol, b_vol)
        which = gamuts[0][0] if a_vol > b_vol else gamuts[1][0]
        print(f"\n  {which} is the larger gamut, by "
              f"{100 * (bigger / smaller - 1):.1f}%")

    out = a.out or a.ti3[0].with_name(a.ti3[0].stem + "-gamut.html")
    ref = "media white" if a.relative else f"{a.white} absolute"
    write_html(gamuts, out, f"Measured gamut — {ref}", patches=clouds)
    print(f"\n  wrote {out}")
    if a.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
