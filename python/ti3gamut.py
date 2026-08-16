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
import math
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
                         legendgroup=f"{name}-rings",
                         showlegend=key is None, hoverinfo="name")
    if key is None:
        return [rings]
    return [rings, _legend_line(f"{name} (rings inside)", key,
                                f"{name}-rings")]


def _band(colour: str, steps: int = 32) -> str:
    """A colour rounded to a coarse band, so a cage needs few traces."""
    try:
        r, g, b = (int(v) for v in colour[4:-1].split(","))
    except (ValueError, IndexError):
        return colour
    q = [min(255, (v // steps) * steps + steps // 2) for v in (r, g, b)]
    return f"rgb({q[0]},{q[1]},{q[2]})"


def _wire_segments(points, faces):
    """Every edge of a triangle mesh, once, as a single broken line.

    A triangle mesh shares each edge between two triangles, so drawing both
    doubles the work for an identical picture. The ``None`` between segments
    is what tells the drawing library to lift the pen.

    THIS IS THE ONLY WAY TO GET A WIRE CAGE, and that is worth writing down
    because there appears to be an easier one and it does nothing at all. A
    surface takes a ``contour`` setting, and it reads as "draw the mesh":

        Sets whether or not dynamic contours are shown on hover

    -- the drawing library's own words. It draws contour lines under the
    POINTER and nothing whatever the rest of the time. Measured: a surface
    with it off and the same surface with it on differ by 0 pixels.
    """
    seen = set()
    xs, ys, zs = [], [], []
    for tri in faces:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edge = (a, b) if a < b else (b, a)
            if edge in seen:
                continue
            seen.add(edge)
            xs += [points[a, 0], points[b, 0], None]
            ys += [points[a, 1], points[b, 1], None]
            zs += [points[a, 2], points[b, 2], None]
    return xs, ys, zs


def _edges(gamut, name: str, colour: str = "#9aa3b2", width: float = 1.0,
           paint: str = "plain", index: int = 0, key: str | None = None,
           page: str = "#111111", only=None):
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
    f = (np.asarray(gamut.faces)[np.asarray(only)] if only is not None
         else gamut.faces)
    if paint == "plain":
        xs, ys, zs = _wire_segments(v, f)
        cage = go.Scatter3d(x=xs, y=ys, z=zs, mode="lines",
                            line=dict(color=colour, width=width),
                            name=f"{name} (outline)",
                            legendgroup=f"{name}-outline",
                            showlegend=key is None, hoverinfo="name")
        if key is None:
            return [cage]
        return [cage, _legend_line(f"{name} (outline)", key,
                                   f"{name}-outline")]

    if only is not None and not len(f):
        return []                      # nothing of this cage is in this part
    per_vertex = _paint_vertices(gamut, paint, index)
    if per_vertex is None:                       # "true": each point's colour
        per_vertex = [f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
                      for r, g, b in gamut.colors]
    bands: dict = {}
    seen_again = set()
    for tri in f:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            # `edge` here too, for the same reason: `key` is this function's
            # colour argument and the loop above used to eat it.
            edge = (a, b) if a < b else (b, a)
            if edge in seen_again:
                continue
            seen_again.add(edge)
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
            showlegend=False, hoverinfo="name"))
    # A KEY OF ITS OWN, RATHER THAN THE FIRST BAND'S COLOUR. The bands are
    # sorted by their colour and "rgb(0,0,0)" sorts first, so a coloured cage
    # keyed on band zero took pure black every time -- 1.11:1 against the dark
    # page, which is invisible. Reported from a phone, then measured: the
    # outline key on two published pages could not be seen at all.
    traces.append(_legend_line(f"{name} (outline)",
                               _legend_swatch(per_vertex, page),
                               f"{name}-outline"))
    return traces


#: Colour used for the part of a gamut that the comparison cannot reach. A
#: warm red against the muted grey of the reachable part, so the eye goes
#: straight to what is lost without needing the legend.
_LOST = "rgb(232,23,93)"
_KEPT = "rgb(105,112,126)"


#: A MARK ON THE TRACES WHOSE COLOUR IS THE ANSWER, not decoration.
#:
#: A saved page lets the reader take the colour out of a shape and look at it
#: in grey, which is the readable choice when two shapes overlap and the
#: colours fight. On most of what is drawn here the colour is a picture of the
#: measurement and losing it costs nothing but prettiness.
#:
#: On two of them it is the measurement. The comparison mesh is painted red
#: where the other gamut cannot reach and grey where it can, and its name says
#: so — "red is out of reach". A chart's out-of-reach patches are red for the
#: same reason. Greyed, a two-state picture becomes a one-state picture that
#: still carries a name promising two, and a reader who pressed one button
#: three screens ago would have no way of knowing the picture had stopped
#: saying anything.
#:
#: So these traces carry this mark, and the saved page does not offer to grey
#: the group it belongs to at all. Not offered rather than offered-and-refused:
#: a control that is there and declines to work is the worse of the two.
_COLOUR_IS_THE_ANSWER = {"cq": "colour"}


def _mesh_lost(gamut, name: str, opacity: float, lost,
               kept: str = _KEPT, depth: float = 0.35, light=None,
               only=None, alphas=None, stand=None) -> "list":
    """The gamut painted by what the comparison cannot reproduce.

    *only* splits it exactly as it splits a plain mesh -- see :func:`_mesh`.
    The two features ask different questions of the same shape (this one is
    about the chosen comparison, the split is about the other shapes drawn
    beside it) and both can be true at once, so they compose rather than
    exclude each other.
    """
    import plotly.graph_objects as go
    v = _plot_points(gamut)
    colours = [_LOST if bad else kept for bad in lost]
    # THE FADE GOES ON BEFORE THE WELD, so it travels with the colours it
    # belongs to. Welding renumbers the vertices; a mask applied afterwards
    # would line up with nothing.
    if alphas is not None:
        colours = _with_alpha(colours, alphas)
    picked = (np.asarray(gamut.faces)[np.asarray(only)] if only is not None
              else gamut.faces)
    # THE MASK IS WELDED WITH THE COLOURS, not alongside them.
    #
    # A saved page has to be able to work this fade out for itself, which
    # means carrying which vertices stand out -- and it must be numbered the
    # way the drawn vertices are, not the way the gamut's are. Welding drops
    # duplicates and renumbers what is left, so the mask is put through the
    # very same call rather than through a second one that could disagree
    # with it. _weld indexes its middle argument and does not care what is in
    # it, which is what makes this safe.
    carried = None
    if stand is not None:
        keep, _remap = _weld_order(v, colours)
        carried = "".join("1" if stand[i] else "0" for i in keep)
    v, colours, faces = _weld(v, colours, picked)
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        vertexcolor=colours, opacity=opacity, flatshading=False,
        lighting=_lighting(depth),
        lightposition=light or _LIGHT_OVERHEAD,
        # BOTH COLOURS NAMED, not just the alarming one. "red is out of
        # reach" leaves a reader looking at a two-coloured shape having been
        # told what one of the two means, and quietly invites them to read
        # the grey as "the rest of the picture" rather than as the answer it
        # is. Saying both is four more words and removes the guess.
        name=f"{name} — red is out of reach, grey is within it", showlegend=True,
        hoverinfo="name",
        # The red IS the answer here — see _COLOUR_IS_THE_ANSWER.
        meta=dict(_COLOUR_IS_THE_ANSWER,
                  **({"stand": carried} if carried is not None else {})))


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

    A NAME NOBODY HANDLES IS REFUSED. Everything below was a chain of tests
    ending in "otherwise, by chroma", so a misspelling -- or the word "plain",
    which belongs to a cage and not to a surface -- came back as a chroma ramp
    and looked like a painting fault rather than a wrong name. The same shape
    of bug as the empty picture an unknown style used to draw.
    """
    if paint not in SHAPE_PAINTS:
        raise ValueError(
            f"unknown painting {paint!r}; expected one of "
            f"{', '.join(sorted(SHAPE_PAINTS))}. (\"plain\" is a cage's own "
            f"grey, not a way of painting a surface -- see outline_paint.)")
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


def _legend_line(name: str, colour: str, group: str | None = None):
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
        line=dict(color=colour, width=4), legendgroup=group or name,
        name=name, showlegend=True, hoverinfo="skip")


def _legend_proxy(name: str, colour: str, group: str | None = None):
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
        legendgroup=group or name,
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
    keep, remap = _weld_order(points, colours)
    if len(keep) == len(points):
        return points, colours, faces
    kept = np.asarray(keep)
    welded = ([colours[i] for i in kept] if isinstance(colours, list)
              else np.asarray(colours)[kept])
    return points[kept], welded, remap[np.asarray(faces)]


def _weld_order(points, colours):
    """WHICH vertices a weld keeps, and where every old one now points.

    Split out of :func:`_weld` so that anything else needing to follow the
    same renumbering can do so by the SAME rule rather than by a second
    implementation of it. That matters more than it looks: a weld groups by
    the point AND its colour, so a mask welded on its own -- with the mask
    values standing in for the colours -- can group differently and come back
    a different length, lined up with nothing. Asking for the indices once
    and indexing everything with them cannot drift.
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
    return keep, remap


def agreement_masks(gamuts):
    """Which triangles of each shape lie somewhere the others do NOT reach.

    Two gamuts drawn over each other are mostly the same gamut: the part where
    they agree is the bulk of both, it is drawn twice, and it hides the part
    where they differ -- which is the only part anybody is comparing them to
    see. Fading the agreement away leaves the disagreement standing on its own.

    A vertex is AGREED when every other shape also contains it. A triangle is
    agreed when all three of its vertices are. Returned per shape as a boolean
    per triangle: ``True`` where that triangle disagrees with something and is
    therefore part of the answer.

    AND, NOT OR, with three or more shapes. "Where they overlap" is the region
    every one of them holds; a point inside one of two others is still a
    disagreement and stays visible.

    Containment is `gamutview.outside_of`, which is the same test the
    red-and-grey comparison mesh already uses -- so the two features cannot
    disagree with each other about what "inside" means.

    NOT CACHED, deliberately. The test builds a triangulation of the shape
    being tested against, which is the expensive part -- and it was measured
    before deciding: **12 ms for two demo gamuts**, against a full redraw of
    the picture that costs far more than that. The obvious cache is keyed on
    the identity of the two shapes, and object identity is reused the moment
    one is garbage-collected: a freed gamut's key can be handed to a newly
    loaded one, which would quietly answer a containment question about a
    measurement that is no longer open. Twelve milliseconds is not worth a
    class of bug that shows up as one paper wearing another's shape.
    """
    from gamutview import outside_of

    out = []
    for i, (_name, a) in enumerate(gamuts):
        others = [b for j, (_m, b) in enumerate(gamuts) if j != i]
        faces = np.asarray(a.faces)
        if not others:
            # NOTHING TO AGREE WITH. One shape on its own disagrees with
            # everything, so all of it stays -- which makes the control a
            # no-op rather than a shape-eraser when somebody closes the
            # second measurement while it is turned down.
            out.append(np.ones(len(faces), bool))
            continue
        agreed = np.ones(len(a.vertices), bool)
        for b in others:
            try:
                got = outside_of(a, b)
            except Exception:          # noqa: BLE001 — a shape too small to
                # triangulate cannot contain anything, so nothing agrees with
                # it and the picture is left exactly as it was.
                got = np.ones(len(a.vertices), bool)
            agreed &= ~got
        out.append(~(agreed[faces[:, 0]] & agreed[faces[:, 1]]
                     & agreed[faces[:, 2]]))
    return out


def _with_alpha(colours, alphas):
    """The same colours, each carrying its own alpha.

    WHY ALPHA AND NOT A SECOND MESH. The obvious way to draw part of a shape
    faintly is to cut it into two meshes and give them two opacities. It was
    built that way first, and then measured against the picture as it ships:
    **120,481 pixels differed by more than eight levels, the worst by 79** --
    with the fade at FULL, where nothing should have changed at all.

    A browser blends transparent surfaces in the order it draws them. One
    closed surface, and the same surface cut into two open pieces, do not
    composite to the same thing; the difference shows as hard-edged patches
    across the shape, which is exactly what somebody looking at one asked
    about.

    Per-vertex alpha keeps ONE mesh. At full strength the colours are the very
    strings they always were, so the top of the slider is not merely close to
    a no-op -- it is the same array of colours and therefore the same picture.
    Measured at **0 pixels different**.
    """
    out = []
    for colour, alpha in zip(colours, alphas):
        text = str(colour)
        if alpha >= 1.0 or "(" not in text:
            out.append(colour)          # untouched: the same string, not a copy
            continue
        inside = text[text.index("(") + 1:text.index(")")].split(",")
        out.append(f"rgba({inside[0]},{inside[1]},{inside[2]},{alpha:.3f})")
    return out


def agreeing_edges(gamut, keep_faces):
    """The same split for a wire cage: every vertex the kept triangles touch.

    WITHOUT THIS THE FEATURE IS HALF APPLIED. A page showing one solid shape
    and one cage would fade the solid's agreement away and leave the cage
    drawn in full, so the reader sees a hole appear in one shape and nothing
    happen to the other -- and has no way of knowing the two were treated
    differently. A cage is a boundary like any other and is faded like one.
    """
    faces = np.asarray(gamut.faces)
    live = np.zeros(len(gamut.vertices), bool)
    if len(faces):
        live[np.unique(faces[np.asarray(keep_faces)])] = True
    return live


def _mesh(gamut, name: str, opacity: float,
          paint: str = "true", index: int = 0, depth: float = 0.35,
          page: str = "#111318", light=None, only=None, alphas=None,
          stand=None):
    """One Plotly mesh for a gamut, painted the way the user asked.

    *only* is an optional boolean per triangle. Given one, the mesh is drawn
    from those triangles alone -- which is how one shape becomes two meshes,
    the part that disagrees with the other shapes and the part that agrees,
    so the two can be drawn at different strengths. The drawing library allows
    exactly one opacity per trace, which is the whole reason for the split.
    """
    import plotly.graph_objects as go
    v = _plot_points(gamut)
    chosen = _paint_vertices(gamut, paint, index)
    colours = chosen if chosen is not None else [
        f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
        for r, g, b in gamut.colors]
    # THE FADE GOES ON BEFORE THE WELD, so it travels with the colours it
    # belongs to. Welding renumbers the vertices; a mask applied afterwards
    # would line up with nothing.
    if alphas is not None:
        colours = _with_alpha(colours, alphas)
    picked = (np.asarray(gamut.faces)[np.asarray(only)] if only is not None
              else gamut.faces)
    # THE MASK IS WELDED WITH THE COLOURS, not alongside them.
    #
    # A saved page has to be able to work this fade out for itself, which
    # means carrying which vertices stand out -- and it must be numbered the
    # way the drawn vertices are, not the way the gamut's are. Welding drops
    # duplicates and renumbers what is left, so the mask is put through the
    # very same call rather than through a second one that could disagree
    # with it. _weld indexes its middle argument and does not care what is in
    # it, which is what makes this safe.
    carried = None
    if stand is not None:
        keep, _remap = _weld_order(v, colours)
        carried = "".join("1" if stand[i] else "0" for i in keep)
    v, colours, faces = _weld(v, colours, picked)
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        vertexcolor=colours, opacity=opacity, name=name, showlegend=False,
        legendgroup=name,
        meta=(dict(stand=carried) if carried is not None else None),
        # Only the legend key uses this; vertexcolor paints the surface.
        color=_legend_swatch(chosen if chosen is not None else gamut.colors,
                             page),
        flatshading=False, hoverinfo="name",
        lighting=_lighting(depth),
        # THE LIGHT THE USER PLACED. Fixed overhead here, this argument was
        # accepted and then dropped, so Set the lighting myself moved nothing.
        lightposition=light or _LIGHT_OVERHEAD,
        # NO `contour` HERE. It reads like "draw the mesh" and is
        # documented as "dynamic contours … on hover": measured, a surface
        # with it on and one with it off differ by 0 pixels. A cage is a line
        # trace -- see _wire_segments and _edges.
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
    # THE CAGE IS A LINE TRACE, because a surface has no wires to turn on.
    #
    # Both of these were built on the surface's `contour` setting, which reads
    # like "draw the mesh" and is documented as "dynamic contours … on hover".
    # Measured against a page with no skin on it at all:
    #
    #     solid          214,308 pixels
    #     mesh           214,308 pixels   -- the same picture, to the pixel
    #     outline only     5,251 pixels   -- a surface at a fiftieth strength
    #
    # So "Mesh" was Solid under another name, and "Outline only" was a nearly
    # invisible film rather than a cage. Both now draw the edges themselves.
    wire = style in ("mesh", "outline")
    common = dict(
        x=verts[:, 0], y=verts[:, 1], z=verts[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        name=f"{name} — a skin over the patches", showlegend=False,
        hoverinfo="name", flatshading=False,
        lighting=_lighting(depth), lightposition=light or _LIGHT_OVERHEAD,
    )
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
    common["legendgroup"] = f"{name}-skin"
    out = []
    # OUTLINE ONLY MEANS ONLY THE OUTLINE. There is no surface at all now,
    # rather than one at a fiftieth of strength standing in for its absence,
    # so everything inside really is unobstructed.
    if style != "outline":
        out.append(go.Mesh3d(**common))
    if wire:
        xs, ys, zs = _wire_segments(verts, faces)
        out.append(go.Scatter3d(
            x=xs, y=ys, z=zs, mode="lines",
            # LIGHTER OVER A SURFACE THAN ON ITS OWN, which is the same rule
            # the gamut cages follow. A hull over 480 patches is hundreds of
            # edges: at full weight over a coloured solid they stop reading as
            # structure and become a grey haze — reported, on the first build
            # that drew them at all, as "looks like triangles again". On its
            # own there is nothing to compete with and the cage carries the
            # whole shape, so it keeps its weight.
            line=dict(color=key, width=1.0 if style == "outline" else 0.6),
            name=f"{name} — a skin over the patches",
            legendgroup=f"{name}-skin", showlegend=False, hoverinfo="name"))
    out.append(_legend_proxy(f"{name} — a skin over the patches", key,
                             f"{name}-skin"))
    return out


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
            legendgroup=f"{name}-printed",
            name=f"{name} — to be printed"))
        traces.append(_legend_proxy(f"{name} — to be printed",
                                    _legend_swatch(kept, page),
                                    f"{name}-printed"))
    if outside.any() and show_outside:
        traces.append(go.Scatter3d(
            x=v[outside, 0], y=v[outside, 1], z=v[outside, 2], mode="markers",
            marker=dict(size=out_size, opacity=out_opacity, color=_LOST,
                        symbol="circle", line=dict(width=0)),
            # A PROXY HERE TOO, always. Its own key would be drawn at the
            # trace's marker size and opacity, so turning the out-of-reach
            # dots down — which is the sensible thing to do when half a chart
            # is red — shrank and faded the key along with them, and the three
            # keys came out three different sizes. A key is a key whatever the
            # dots are doing.
            showlegend=False, hoverinfo="name",
            legendgroup=f"{name}-outside",
            # Red is what "outside" MEANS here — see _COLOUR_IS_THE_ANSWER.
            meta=dict(_COLOUR_IS_THE_ANSWER),
            name=f"{name} — outside"))
        traces.append(_legend_proxy(f"{name} — outside", _LOST,
                                    f"{name}-outside"))
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
#: THE TWO COLOURS OF THE COMPARISON MESH HAVE TO DIFFER IN BRIGHTNESS, not
#: only in hue, and `kept` below is where that is decided.
#:
#: It shipped not doing so. The red that means "out of reach" is rgb(232,23,93)
#: with a relative luminance of 0.186, and the grey that means "within reach"
#: was rgb(105,112,126) at 0.161 -- a contrast ratio of **1.12:1**, which is
#: to say the two were the same brightness and hue alone told them apart.
#: On a surface whose shading already varies its brightness everywhere, hue
#: alone is the weakest cue there is, and for the one reader in twelve who
#: cannot separate red from grey-blue it is no cue at all. Reported as "red
#: and grey with no clear distinction", then measured, and it was exactly that.
#:
#: The grey is now rgb(68,74,87): **1.99:1** against the red, and 2.12:1
#: against the page so the shape does not sink into the background instead.
#:
#: THE HONEST LIMIT: 3:1, which is what WCAG asks of a graphic against what
#: is next to it, cannot be reached on a near-black page with this red. It
#: needs the grey below a luminance of 0.029, and at that point the grey is
#: only 1.38:1 against the page and the reachable part of the shape all but
#: disappears. 1.99:1 is the best available before one problem is traded for
#: the other. What carries the rest is the name in the key, which now says
#: what BOTH colours mean rather than only the red.
#:
#: The light page was measured at the same time and left alone: 2.14:1 there
#: already, and moving its grey to gain more would cost it against the paper.
SCENE_COLOURS = {
    "dark": dict(page="#111111", plot="#141414", grid="#262626",
                 caption="#8a8a8a",   # TEXT_DIM: readable, not shouting
                 text="#e6e6e6", axis="#333333", kept="rgb(68,74,87)",
                 wire="#9aa3b2", mark="#9aa3b2"),
    "light": dict(page="#efebe6", plot="#f7f4ef", grid="#e0ddd7",
                  caption="#7a7570",  # LM_TEXT_DIM
                  text="#22211f", axis="#d0ccc6", kept="rgb(176,180,188)",
                  wire="#a8a4a0",     # LM_TEXT_FAINT: a cage, not a wall
                  mark="#7a7570"),    # LM_TEXT_DIM: one symbol, full weight
    # NOTHING BEHIND IT. The shape floating on the page it is embedded in,
    # which is what a picture dropped into a document or a forum post usually
    # wants. The writing stays mid-grey so it can be read on either.
    "none": dict(page="rgba(0,0,0,0)", plot="rgba(0,0,0,0)",
                 grid="rgba(0,0,0,0)", caption="#8a8a8a", text="#8a8a8a",
                 axis="rgba(0,0,0,0)", kept="rgb(120,124,132)",
                 wire="#9aa3b2", mark="#9aa3b2"),
    # A NEUTRAL GREY, which flatters neither the light end of a shape nor the
    # dark end. A gamut on black looks brighter than it is and one on white
    # looks duller; halfway is the honest ground to judge a colour against.
    "slate": dict(page="#6e7278", plot="#767a80", grid="#8b8f95",
                  caption="#20242a", text="#12151a", axis="#8b8f95",
                  kept="rgb(122,126,134)", wire="#3d4148", mark="#20242a"),
    # PLAIN BLACK AND WHITE, for printing a page out or throwing it on a
    # projector, where a near-black turns to mud and a warm white to yellow.
    "ink": dict(page="#ffffff", plot="#ffffff", grid="#c8c8c8",
                caption="#000000", text="#000000", axis="#c8c8c8",
                kept="rgb(190,190,190)", wire="#606060", mark="#000000"),
}

_PAGE_BACKGROUND = "#111318"

#: THE PAGE COLOURINGS A SAVED PAGE CAN BE SWITCHED BETWEEN.
#:
#: The window itself has two appearances and always will: light and dark are
#: what a person sets their whole computer to, and a third choice there would
#: be a preference nobody asked for. A saved page is a different thing — it is
#: read on somebody else's screen, in somebody else's document, next to
#: somebody else's text — so it carries a short list of page colourings and a
#: button to move through them.
#:
#: Only the PAGE changes: the paper behind the shape, the walls of the box,
#: the grid on them and the writing. Not one measured colour is touched, which
#: is the property that makes this safe to offer at all.
#:
#: Two of these are the window's own, so a page opens looking exactly as it
#: did when it was saved. The other three are the ones people actually ask a
#: picture to be: nothing at all behind it, a neutral grey that flatters
#: neither end, and plain black and white for printing or for a projector.
PAGE_SCHEMES = ("dark", "light", "none", "slate", "ink")

#: How a shape may be drawn. Exactly the three the window offers, and the only
#: three :func:`build_figure` knows what to do with. Kept here rather than
#: written into the branches that test it, so that the check and the drawing
#: cannot drift apart.
SHAPE_STYLES = ("solid", "solid+mesh", "mesh")

#: How a surface may be painted. The same five the window offers as "How the
#: shapes are coloured", named here so that a name nobody handles is refused
#: rather than quietly painted as something else.
SHAPE_PAINTS = ("true", "solid", "lightness", "chroma", "accent")

#: How a shape's WIRE CAGE may be coloured, which is a separate question from
#: how its surface is.
#:
#: It used to be one tick -- "Colour the outlines too" -- and a tick can only
#: say "the same as the shape". That left one useful picture unreachable: a
#: surface drained to grey by lightness or chroma, so the FORM of it reads,
#: with the cage over it still carrying the real colours. Asked for, and the
#: reason it could not be had was that the two questions had been folded into
#: one control.
#:
#: ``"match"`` keeps the old behaviour and keeps following the shape when the
#: shape's painting is changed; the five named ones are fixed regardless of it;
#: ``"plain"`` is the one flat grey that reads most clearly on top of a solid.
#: ``"colour"`` is the word older saved settings used for ``"match"`` and is
#: still understood, because a setting written last week must not come back
#: as an error.
OUTLINE_PAINTS = ("plain", "match") + SHAPE_PAINTS


def outline_paint(choice: str, shape_paint: str) -> str:
    """Which painting a wire cage takes, given its own choice and the shape's.

    Separated from :func:`build_figure` so the rule lives in one place: the
    window, the saved page and the command line all decide it the same way.
    """
    if choice in ("match", "colour"):
        return shape_paint
    if choice in OUTLINE_PAINTS:
        return choice
    raise ValueError(
        f"unknown outline colour {choice!r}; expected one of "
        f"{', '.join(sorted(OUTLINE_PAINTS))}")


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
#: WHY A SEE-THROUGH SHAPE HAS TO BE PUT IN ORDER BEFORE IT IS DRAWN.
#:
#: A shape drawn solid hides itself: the graphics card keeps the depth of what
#: it has already painted, and a triangle further away is thrown out. A shape
#: drawn even slightly see-through does not. Reading the drawing library's own
#: render loop (plotly.min.js, where it draws the transparent pass):
#:
#:     depthMask(false); blendFunc(ONE, ONE_MINUS_SRC_ALPHA);
#:     ... every see-through object drawn, in the order it sits in memory ...
#:
#: Depth WRITING is off for that pass. So a see-through shape never hides
#: itself: every triangle is blended in, the near ones and the far ones, in
#: whatever order they happen to sit in the file -- and with that blend the
#: LAST one to land on a pixel is the one that mostly shows. "Last in memory"
#: has nothing whatever to do with "nearest to the eye", so pieces of the far
#: side punch through the near side in hard-edged, triangle-shaped patches.
#: That is the "rough triangles" and the "sliced" look, and it is why the
#: same shape is fine at one angle and torn in half at another.
#:
#: MEASURED, before any of this was written. One paper, five camera angles,
#: at a THOUSANDTH of transparency -- where nothing can possibly blend, so
#: anything that changes is this and not see-through-ness:
#:
#:     angle              unlike the solid one   after ordering
#:     1.5, 1.5, 1.5             46.8%                0.5%
#:     -1.8, 0.6, 0.4            84.0%                0.3%
#:     0.2, -2.0, 1.1            56.8%                0.2%
#:     1.0, 1.0, -1.7            92.1%                0.3%
#:     -0.9, -1.4, -0.9           0.9%                0.3%
#:
#: The last row is why it is only seen SOMETIMES. And the brightness moves
#: with it: 123.7 against the solid shape's 153.3 at one angle, 153.5 once
#: ordered. So the "it goes dark as soon as it is see-through" and the "it
#: looks sliced" are one fault, not two.
#:
#: WHAT IS DONE ABOUT IT: put the triangles in memory farthest-first before
#: each frame, which is what the blend has always expected and never had. Two
#: decisions in here were made on measurement rather than taste:
#:
#: 1. BY DIRECTION, NOT BY DISTANCE FROM THE EYE. The first attempt worked out
#:    where the eye was among the measurements and sorted by distance from it.
#:    It put the eye INSIDE the shape -- 11.6, 7.0, 18.9, for a shape running
#:    from -79 to 82 -- and made the picture worse at three angles out of five.
#:    A direction needs no division by a small number and no centre.
#:
#: 2. BUCKETS, NOT A COMPARISON SORT, AND THE DRAWN OBJECT, NOT THE FRONT
#:    DOOR. At the largest size that occurs (18,252 triangles, which is what
#:    the Detail slider builds at 40) the obvious way costs 48.5 ms a frame --
#:    twenty frames a second, and the picture stutters. Dropping the triangles
#:    into buckets by depth and handing the list straight to the object that
#:    was drawn costs 0.48 ms: a hundred times less, and three per cent of a
#:    frame, so it can be kept up while the shape is turning.
#:
#:        triangles   sort+hand over, carefully   the same, quickly
#:              978            10.12 ms                0.26 ms
#:            5,310            22.72 ms                0.38 ms
#:           19,230            48.54 ms                0.48 ms
#:
#: The quick handover uses a door the library does not advertise, so every
#: step of reaching it is checked and any failure falls back to the front door
#: rather than breaking the page.
_ORDER_JS = """
window.cqOrder = (function () {
  var plots = [], raf = null, still = 0, watch = null, fast = true;
  var listening = false;
  //: Pooling can be turned off from outside. Not a setting anybody sees --
  //: it is how the tests compare the two ways of drawing the same page
  //: without editing the page, which is the only comparison that is fair.
  var pooling = true;
  var BUCKETS = 4096, tally = new Int32Array(BUCKETS + 1);

  function graphs() {
    var out = [], all = document.querySelectorAll('.js-plotly-plot');
    for (var n = 0; n < all.length; n++)
      if (all[n]._fullLayout && all[n]._fullData) out.push(all[n]);
    return out;
  }

  // IS ANY ONE COLOUR OF THIS SURFACE FADED? Stops at the first one it finds,
  // so the usual answer -- a shape whose colours are all solid -- costs one
  // look rather than a walk through every vertex.
  function someColourFades(colours) {
    if (!colours || !colours.length) return false;
    for (var n = 0; n < colours.length; n++) {
      var c = colours[n];
      if (typeof c === 'string') {
        if (c.charCodeAt(3) === 97 /* the a of rgba */) return true;
      } else if (c && c.length > 3 && c[3] < 1) {
        return true;
      }
    }
    return false;
  }

  // EVERY SEE-THROUGH SURFACE, and the triangle midpoints that will be sorted.
  // Worked out once per shape rather than per frame: the midpoints are fixed
  // in the measurements' own numbers and only the direction they are measured
  // along changes.
  function collect() {
    plots = [];
    var gs = graphs();
    for (var q = 0; q < gs.length; q++) {
      var gd = gs[q], keep = [], full = gd._fullData;
      for (var n = 0; n < full.length; n++) {
        var t = full[n];
        if (!t || t.type !== 'mesh3d' || !t.i || !t.j || !t.k) continue;
        // NOT DRAWN IS NOT THE SAME AS NOT THERE, and "false" is not the only
        // way a trace is not drawn. Clicking a shape's name in the key sets
        // its visibility to the string "legendonly", which is neither true nor
        // false -- so a test for `=== false` let a hidden shape through, the
        // drawn object for it could not be found, and everything else on the
        // page went through the slow front door for as long as it stayed
        // hidden. Measured, two papers with one of them hidden: a pass cost
        // 4.50 ms where it now costs 1.70 -- and the engine went on putting
        // 1,956 triangles in order for a picture showing 978, with the
        // pooling below switched off the whole time. Hiding a shape is
        // supposed to make the picture cheaper, and it made it dearer.
        if (t.i.length < 2 || t.visible !== true) continue;
        // A SOLID SURFACE ALREADY HIDES ITSELF and must be left exactly as it
        // is -- there is nothing to fix and reordering it would be work for
        // no picture. The opacity is read again every time this runs, because
        // the strength controls change it.
        //
        // AND A STRENGTH OF 1 DOES NOT MEAN SOLID. A surface can be made
        // see-through a second way, one colour at a time, which is how the
        // fade over the part two shapes agree on is drawn -- and the library
        // treats that exactly the same:
        //
        //     colour.length === 3 ? push(r, g, b, this.opacity)
        //                         : (push(r, g, b, a * this.opacity),
        //                            a < 1 && (this.hasAlpha = true))
        //
        // So a shape at full strength with a faded middle is a see-through
        // shape and tears in precisely the same way. Missing this would have
        // left the newest feature in the application showing the very fault
        // this is here to remove.
        if (!(t.opacity < 1) && !someColourFades(t.vertexcolor)) continue;
        var m = t.i.length, mid = new Float64Array(m * 3), f;
        for (f = 0; f < m; f++) {
          var a = t.i[f], b = t.j[f], c = t.k[f];
          mid[f * 3]     = (t.x[a] + t.x[b] + t.x[c]) / 3;
          mid[f * 3 + 1] = (t.y[a] + t.y[b] + t.y[c]) / 3;
          mid[f * 3 + 2] = (t.z[a] + t.z[b] + t.z[c]) / 3;
        }
        keep.push({uid: t.uid, index: n, m: m, mid: mid,
                   i: Int32Array.from(t.i), j: Int32Array.from(t.j),
                   k: Int32Array.from(t.k),
                   key: new Float64Array(m), slot: new Int32Array(m),
                   bin: new Int32Array(m),
                   // THE TRIANGLE LIST IN THE SHAPE THE LIBRARY USES: one
                   // little array of three per triangle, not one long one.
                   // Asked rather than assumed -- a flat list was tried and
                   // the shape disappeared entirely, because the rebuild
                   // reads cells[f][0] and a number has no [0].
                   //
                   // Made ONCE and written into ever after, so a frame
                   // allocates nothing at all: eighteen thousand small
                   // arrays a frame would be handed straight to the rubbish
                   // collector sixty times a second.
                   tri: (function () {
                     var t = new Array(m);
                     for (var f = 0; f < m; f++) t[f] = [0, 0, 0];
                     return t;
                   })()});
      }
      if (keep.length)
        plots.push({gd: gd, meshes: keep, was: null,
                    pool: null, blanked: null});
    }
    return plots.length;
  }

  // WHICH WAY THE EYE IS, IN THE SAME NUMBERS THE TRIANGLES ARE IN. The
  // library squashes each axis by aspectratio / range when it builds its
  // model, so undoing that on the camera's own eye vector gives the line of
  // sight in the measurements' units. Drawn in "data" proportions all three
  // come out equal and this is simply the eye vector; reading them anyway
  // keeps it right if a picture is ever drawn squared off instead.
  function lineOfSight(gd) {
    var sc = gd._fullLayout.scene;
    if (!sc) return null;
    var live = null;
    // DURING A DRAG THE REAL CAMERA IS INTERNAL -- the same thing cqSpin's
    // liveCam exists for. Reading the settled one would order the shape for
    // where it used to be and leave it torn for the whole gesture.
    try { if (sc._scene && sc._scene.getCamera) live = sc._scene.getCamera(); }
    catch (e) {}
    var e = (live && live.eye) || (sc.camera && sc.camera.eye);
    if (!e) return null;
    var ar = sc.aspectratio, ax = ['xaxis', 'yaxis', 'zaxis'];
    var kk = ['x', 'y', 'z'], out = [], len = 0;
    for (var d = 0; d < 3; d++) {
      var r = (sc[ax[d]] && sc[ax[d]].range) || [0, 1];
      var span = (r[1] - r[0]) || 1, a = (ar && ar[kk[d]]) || 1;
      out.push(e[kk[d]] * span / a);
      len += out[d] * out[d];
    }
    len = Math.sqrt(len);
    if (!(len > 0)) return null;
    return [out[0] / len, out[1] / len, out[2] / len];
  }

  // FARTHEST FIRST, WITHOUT COMPARING ANYTHING. Every triangle's reach along
  // the line of sight is a number in a known range, so they are dropped into
  // buckets in one pass and read back out in order. Two triangles in the same
  // bucket can come out the wrong way round, and that is deliberate: one
  // bucket is a four-thousandth of the shape's depth, far thinner than the
  // surface itself, and it buys an ordering that costs a tenth of a
  // millisecond instead of five.
  function order(A, look) {
    var key = A.key, mid = A.mid, m = A.m, f;
    var lo = Infinity, hi = -Infinity;
    for (f = 0; f < m; f++) {
      var v = mid[f * 3] * look[0] + mid[f * 3 + 1] * look[1]
            + mid[f * 3 + 2] * look[2];
      key[f] = v;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    var s = (hi > lo) ? BUCKETS / (hi - lo) : 0;
    tally.fill(0);
    for (f = 0; f < m; f++) {
      var b = (key[f] - lo) * s | 0;
      if (b < 0) b = 0; else if (b >= BUCKETS) b = BUCKETS - 1;
      A.bin[f] = b;
      tally[b + 1]++;
    }
    for (f = 0; f < BUCKETS; f++) tally[f + 1] += tally[f];
    for (f = 0; f < m; f++) A.slot[tally[A.bin[f]]++] = f;
    for (f = 0; f < m; f++) {
      var g = A.slot[f], t = A.tri[f];
      t[0] = A.i[g]; t[1] = A.j[g]; t[2] = A.k[g];
    }
  }

  // THE THING THAT WAS ACTUALLY DRAWN for a trace, found by the trace's own
  // identifier rather than by its size. Matching on triangle count seems
  // easier and is wrong the moment two shapes have the same number of them --
  // which two prints of the same chart do, measured: 978 and 978.
  function drawn(gd, uid) {
    try {
      var s = gd._fullLayout.scene._scene;
      var t = s && s.traces && s.traces[uid];
      if (t && t.mesh && typeof t.mesh.update === 'function') return t.mesh;
    } catch (e) {}
    return null;
  }

  // LISTEN TO WHAT THE LIBRARY TELLS THE SURFACE, and keep the last of it.
  //
  // The quick door cannot be opened by handing over a triangle list on its
  // own, and finding that out the hard way is the most useful thing that
  // happened here. The surface's own update reads, in the library's source:
  //
  //     this.hasAlpha = false;
  //     "opacity" in given && (this.opacity = given.opacity,
  //                            this.opacity < 1 && (this.hasAlpha = true));
  //
  // -- and whether the surface is see-through AT ALL is `hasAlpha`. So an
  // update that does not mention the strength declares the shape solid, and
  // it is then drawn in the solid pass. The picture that came back matched
  // the solid one perfectly, which read as a flawless fix and was the shape
  // being genuinely opaque: the wall behind it stopped showing through, 99.9%
  // of it to 0.4%. Nothing but asking what was BEHIND the shape could tell
  // those two apart.
  //
  // Rebuilding the whole set of parameters here would mean copying what the
  // library does to turn a trace into a surface, and getting one of them
  // wrong would fail exactly as quietly. So it is not rebuilt: the surface's
  // update is wrapped, the library's own parameters are kept as they go past,
  // and the quick door re-sends those with only the triangle list changed.
  function remember(obj) {
    if (obj.__cqWrapped) return;
    obj.__cqWrapped = true;
    var was = obj.update;
    obj.update = function (given) {
      if (given && given.cells && given.positions && !given.__cq)
        obj.__cqGiven = given;
      return was.call(obj, given);
    };
  }

  // THE SURFACE'S NORMALS, WORKED OUT ONCE INSTEAD OF SIXTY TIMES A SECOND.
  //
  // Reordering triangles cannot change a vertex normal: same vertex, same
  // neighbours, same answer. But the library recomputes every one of them on
  // every handover --
  //
  //     !cellNormals && !vertexNormals && (vertexNormals = f(cells, positions))
  //
  // -- and at 19,230 triangles that is most of the time spent: 35.9 ms a
  // handover becomes 15.4 ms when they are supplied, a saving of 57%.
  //
  // WRITTEN TO MATCH THE LIBRARY'S OWN, STEP FOR STEP, and that is the whole
  // point. An area-weighted normal is the obvious way to do it, takes four
  // lines, and moved the picture by 1.17% -- a small change to the shading
  // that nobody asked for, in exchange for speed, which is not a trade worth
  // making. The library weights each face by the SINE OF THE ANGLE at the
  // vertex instead (its cross product divided by the two edge lengths), so
  // that is what happens here, in the same order, giving the same numbers.
  //
  // Skipped entirely when the surface is drawn with flat facets, because then
  // the normals are per FACE and reordering the faces does reorder them.
  function normalsOnce(A, given) {
    if (A.normals !== undefined) return A.normals;
    A.normals = null;
    if (given.useFacetNormals || given.cellNormals || given.vertexNormals)
      return A.normals;
    var pos = given.positions, cells = given.cells;
    if (!pos || !cells) return A.normals;
    var eps = given.vertexNormalsEpsilon === undefined
      ? 1e-6 : given.vertexNormalsEpsilon;
    var out = new Array(pos.length), v, E;
    for (v = 0; v < pos.length; v++) out[v] = [0, 0, 0];
    for (v = 0; v < cells.length; v++) {
      var m = cells[v], b = 0, p = m[m.length - 1], k = m[0];
      for (var M = 0; M < m.length; M++) {
        b = p; p = k; k = m[(M + 1) % m.length];
        var T = pos[b], L = pos[p], x = pos[k];
        var C = [0, 0, 0], S = 0, g = [0, 0, 0], Q = 0;
        for (E = 0; E < 3; E++) {
          C[E] = T[E] - L[E]; S += C[E] * C[E];
          g[E] = x[E] - L[E]; Q += g[E] * g[E];
        }
        if (S * Q > eps) {
          var z = out[p], q = 1 / Math.sqrt(S * Q);
          for (E = 0; E < 3; E++) {
            var V = (E + 1) % 3, G = (E + 2) % 3;
            z[E] += q * (g[V] * C[G] - g[G] * C[V]);
          }
        }
      }
    }
    for (v = 0; v < pos.length; v++) {
      var w = out[v], Z = 0;
      for (E = 0; E < 3; E++) Z += w[E] * w[E];
      if (Z > eps) {
        var r = 1 / Math.sqrt(Z);
        for (E = 0; E < 3; E++) w[E] *= r;
      } else {
        for (E = 0; E < 3; E++) w[E] = 0;
      }
    }
    A.normals = out;
    return A.normals;
  }

  // ------------------------------------------------------------------------
  // TWO SEE-THROUGH SHAPES HAVE NO RIGHT ORDER, SO THEY ARE MADE ONE SHAPE.
  //
  // Sorting each shape's own triangles fixes each shape. It cannot fix two of
  // them against each other, because the library draws one whole surface and
  // then the next whole surface, and two gamuts of the same printer are not
  // one in front of the other -- they pass through each other. Whichever goes
  // down first is wrong over half the picture.
  //
  // Putting the SHAPES in depth order was tried and measured and is not the
  // answer: it rescues the angles where one really is in front and ruins the
  // ones where they cross, and it came out worse on average than leaving them
  // alone. There is no order of two surfaces that is right, which is the
  // whole point.
  //
  // MEASURED AGAINST WHAT RIGHT LOOKS LIKE. Weld the two shapes into a single
  // surface and the question disappears: one surface has one pool of
  // triangles, they are all sorted together, and every one of them is drawn
  // farthest-first. That weld is the reference, and it was checked before it
  // was believed -- welding the other way round moves the picture by 0.00%,
  // and at a thousandth of transparency it agrees with the solid shape to
  // 1.0%. Against it, at eight camera angles:
  //
  //     two shapes, both at 0.55        no ordering 76.2%   per shape 68.5%
  //     two shapes, 0.55 and 0.30                   73.4%             62.6%
  //     three shapes at 0.55                        81.5%             76.3%
  //
  // So this does the weld itself, every frame, on the drawn objects rather
  // than on the traces: all the see-through surfaces' vertices are laid end
  // to end ONCE, their triangles are sorted as one pool, and the whole lot is
  // handed to the first object while the others are given nothing to draw.
  // The page still holds two traces -- the key, the hover, the visibility
  // switches and the saved file are all untouched -- but the graphics card is
  // given one correctly ordered surface.
  //
  // THREE THINGS HAD TO SURVIVE THE WELD, and each is why a piece of the code
  // below exists:
  //
  // 1. A STRENGTH PER SHAPE. One surface has one opacity, and two shapes may
  //    be set to two different ones. The library multiplies each vertex's own
  //    alpha by the surface's opacity, so folding one into the other loses
  //    nothing: the pooled surface is set to full strength and every vertex
  //    carries alpha * its own shape's strength. Identical arithmetic, done
  //    once instead of twice.
  //
  // 2. THE SHADING. One surface has one light and one roughness. Shapes may
  //    each be given their own amount of shape definition, which is a
  //    different lighting, and there is no honest way to give one surface
  //    two. So shapes that are lit differently are NOT pooled: they keep
  //    exactly the behaviour they had before this, which is the second best
  //    picture rather than a wrong one.
  //
  // 3. THE HOVER. Pooled, every triangle belongs to the first surface, so
  //    asking the picture what is under the pointer would name the first
  //    shape everywhere. The vertices of each shape occupy a known stretch of
  //    the pooled surface, so each trace is taught to answer for its own
  //    stretch and to decline the rest -- which is how the right name comes
  //    back for the right shape.
  var EMPTY = [];
  var LIT = ['ambient', 'diffuse', 'specular', 'roughness', 'fresnel',
             'contourEnable', 'contourWidth', 'vertexNormalsEpsilon',
             'faceNormalsEpsilon'];

  function sameNumbers(a, b) {
    if (a === b) return true;
    if (!a || !b || a.length !== b.length) return false;
    for (var n = 0; n < a.length; n++) if (a[n] !== b[n]) return false;
    return true;
  }

  // MAY THESE SURFACES BECOME ONE? Everything that would change the picture if
  // it were pooled is a reason to decline, and declining costs nothing: the
  // per-shape ordering below carries on exactly as it did.
  function poolable(objs) {
    var first = objs[0].__cqGiven, n, q;
    for (n = 0; n < objs.length; n++) {
      var g = objs[n].__cqGiven;
      if (!g || !g.positions || !g.cells || !g.positions.length) return false;
      // COLOURED FROM A SCALE, LIT PER FACET, OR COLOURED PER TRIANGLE. None
      // of these survive being poured together: a scale is a texture the whole
      // surface shares, a facet normal belongs to a triangle and moves when
      // the triangles are reordered, and a colour per triangle would have to
      // be reordered alongside them. None is produced by this application
      // today; all three are declined rather than assumed away.
      if (g.colormap || g.texture || g.opacityscale || g.useFacetNormals
          || g.cellNormals || g.cellColors || g.cellIntensity
          || g.vertexIntensity || g.vertexUVs || g.cellUVs) return false;
      if (!g.vertexColors && !g.meshColor) return false;
      if (n && !sameNumbers(first.lightPosition, g.lightPosition)) return false;
      if (n && !sameNumbers(first.contourColor, g.contourColor)) return false;
      if (n) for (q = 0; q < LIT.length; q++)
        if (first[LIT[q]] !== g[LIT[q]]) return false;
      // Only triangles. A surface carrying stray points or edges would lose
      // them, because the pool is sorted as triangles and nothing else.
      for (q = 0; q < g.cells.length; q++)
        if (!g.cells[q] || g.cells[q].length !== 3) return false;
    }
    return true;
  }

  // THE POOL ITSELF, BUILT ONCE PER SET OF SHAPES rather than once per frame.
  // The vertices, their colours and their normals do not change while the
  // picture is only being turned; the ONLY thing a frame changes is which
  // order the triangles go in, and that is the one thing left to `order`.
  function getPool(P, objs) {
    var n, f, sig = [];
    for (n = 0; n < objs.length; n++) {
      var g0 = objs[n].__cqGiven;
      sig.push(P.meshes[n].uid + ':' + g0.positions.length + ':'
               + g0.cells.length + ':' + g0.opacity);
    }
    sig = sig.join('|');
    if (P.pool && P.pool.sig === sig) return P.pool;
    P.pool = null;
    if (!poolable(objs)) return null;
    var pos = [], col = [], nor = [], span = {}, faces = 0;
    var shift = 0, haveNormals = true;
    for (n = 0; n < objs.length; n++) {
      var g = objs[n].__cqGiven, A = P.meshes[n];
      var op = (typeof g.opacity === 'number') ? g.opacity : 1;
      var vs = g.positions.length, cs = g.vertexColors;
      for (f = 0; f < vs; f++) {
        pos.push(g.positions[f]);
        var c = cs ? cs[f] : g.meshColor;
        var a = (c && c.length > 3) ? c[3] : 1;
        col.push([c[0], c[1], c[2], a * op]);
      }
      // The normals are the ones already worked out for this surface on its
      // own, and they stay right: no triangle in the pool joins one shape's
      // vertices to another's, so a vertex has exactly the neighbours it had.
      var norms = normalsOnce(A, g);
      if (norms && norms.length === vs) {
        for (f = 0; f < vs; f++) nor.push(norms[f]);
      } else {
        haveNormals = false;
      }
      span[A.uid] = {lo: shift, hi: shift + vs, mesh: objs[n]};
      faces += g.cells.length;
      shift += vs;
    }
    var m = faces;
    var pool = {sig: sig, host: objs[0], span: span, m: m, count: objs.length,
                positions: pos, vertexColors: col,
                vertexNormals: haveNormals ? nor : null,
                base: objs[0].__cqGiven,
                i: new Int32Array(m), j: new Int32Array(m),
                k: new Int32Array(m), mid: new Float64Array(m * 3),
                key: new Float64Array(m), slot: new Int32Array(m),
                bin: new Int32Array(m), tri: new Array(m)};
    var at = 0;
    shift = 0;
    for (n = 0; n < objs.length; n++) {
      var cells = objs[n].__cqGiven.cells;
      for (f = 0; f < cells.length; f++) {
        var t = cells[f];
        pool.i[at] = t[0] + shift;
        pool.j[at] = t[1] + shift;
        pool.k[at] = t[2] + shift;
        at++;
      }
      shift += objs[n].__cqGiven.positions.length;
    }
    // THE MIDPOINTS COME FROM THE MEASUREMENTS, NOT FROM THE DRAWN VERTICES.
    //
    // Both are available and they are not in the same units: what the library
    // was handed has each axis multiplied by that axis's own scale, while the
    // direction the eye is in -- worked out by lineOfSight -- is deliberately
    // put back into the measurements' units so it can be compared with the
    // midpoints each surface already carries.
    //
    // Drawn in true proportions the three scales are equal, so the two agree
    // up to one common factor and the ORDER is the same either way, which is
    // why this went unnoticed. Squared off, they are not equal, and a depth
    // worked out in one set of units against a direction in the other puts
    // the triangles in the wrong order on exactly the setting somebody
    // chooses when they want to see the shape rather than its scale.
    //
    // Each surface has already worked its own midpoints out, in the right
    // units, and the pool's triangles are those surfaces' triangles in the
    // same order -- so they are copied rather than computed again, which is
    // both correct and cheaper.
    var into = 0;
    for (n = 0; n < objs.length; n++) {
      var A2 = P.meshes[n], had2 = objs[n].__cqGiven;
      if (A2.m !== had2.cells.length) return null;   // not the same surface
      for (f = 0; f < A2.m * 3; f++) pool.mid[into + f] = A2.mid[f];
      into += A2.m * 3;
    }
    for (f = 0; f < m; f++) pool.tri[f] = [0, 0, 0];
    P.pool = pool;
    return pool;
  }

  // EACH SHAPE ANSWERS FOR ITS OWN STRETCH OF THE POOL.
  //
  // The library asks every trace in turn "is this yours?", and a trace says
  // yes when the thing that was picked is the surface it drew. Pooled, one
  // surface was drawn for all of them, so all of them would say yes and the
  // first would win -- one paper's name over both shapes.
  //
  // What comes back from a pick is the number of a VERTEX, and each shape owns
  // a known stretch of the pooled vertices. So each trace is wrapped: outside
  // its stretch it declines, inside it the number is shifted back into the
  // shape's own numbering and its own answer is used unchanged. Nothing about
  // what hover SAYS is written here -- only which shape is asked.
  function ownHover(P) {
    var sc;
    try { sc = P.gd._fullLayout.scene._scene; } catch (e) { return; }
    if (!sc || !sc.traces) return;
    for (var n = 0; n < P.meshes.length; n++) {
      var tr = sc.traces[P.meshes[n].uid];
      if (!tr || tr.__cqPick || typeof tr.handlePick !== 'function') continue;
      tr.__cqPick = true;
      (function (trace, uid) {
        var was = trace.handlePick;
        trace.handlePick = function (e) {
          var pool = P.pool;
          if (pool && e && e.object === pool.host && e.data
              && typeof e.data.index === 'number') {
            var mine = pool.span[uid];
            if (!mine) return false;
            var at = e.data.index;
            if (at < mine.lo || at >= mine.hi) return false;
            var heldObject = e.object, heldIndex = at;
            e.object = mine.mesh;
            e.data.index = at - mine.lo;
            var answer = false;
            try { answer = was.call(this, e); }
            finally { e.object = heldObject; e.data.index = heldIndex; }
            return answer;
          }
          return was.call(this, e);
        };
      })(tr, P.meshes[n].uid);
    }
  }

  // GIVE A SURFACE ITS TRIANGLES BACK. Anything that was emptied into the pool
  // has to be drawable again the moment it leaves it -- a shape whose strength
  // is turned up to solid stops being pooled, and a surface still holding no
  // triangles would simply vanish. Surfaces that are about to be handed their
  // own order anyway are skipped: they are already being repaired.
  function restore(P, objs) {
    if (!P.blanked || !P.blanked.length) return;
    for (var n = 0; n < P.blanked.length; n++) {
      var o = P.blanked[n];
      if ((objs && objs.indexOf(o) >= 0) || !o.__cqGiven) continue;
      var back = {}, key;
      for (key in o.__cqGiven)
        if (o.__cqGiven.hasOwnProperty(key)) back[key] = o.__cqGiven[key];
      back.__cq = true;
      try { o.update(back); } catch (e) {}
    }
    P.blanked = null;
  }

  function hand(P, look) {
    var n, objs = [], every = true;
    for (n = 0; n < P.meshes.length; n++) {
      var o = drawn(P.gd, P.meshes[n].uid);
      if (!o) { every = false; break; }
      remember(o);
      objs.push(o);
      if (!o.__cqGiven) every = false;
    }
    if (fast && every) {
      try {
        var pool = (pooling && objs.length > 1) ? getPool(P, objs)
                                                : (P.pool = null);
        if (pool) {
          restore(P, objs);
          order(pool, look);
          var one = {}, k0;
          for (k0 in pool.base)
            if (pool.base.hasOwnProperty(k0)) one[k0] = pool.base[k0];
          one.positions = pool.positions;
          one.vertexColors = pool.vertexColors;
          if (pool.vertexNormals) one.vertexNormals = pool.vertexNormals;
          else delete one.vertexNormals;
          one.cells = pool.tri;
          // FULL STRENGTH, because every vertex is already carrying its own
          // shape's strength in its alpha. Left at the first shape's opacity
          // the second shape would be faded twice.
          one.opacity = 1;
          one.__cq = true;
          pool.host.update(one);
          for (n = 1; n < objs.length; n++) {
            var blank = {}, held = objs[n].__cqGiven, k1;
            for (k1 in held) if (held.hasOwnProperty(k1)) blank[k1] = held[k1];
            blank.cells = EMPTY;
            blank.__cq = true;
            objs[n].update(blank);
          }
          P.blanked = objs.slice(1);
          // AND CHECK THE POOL ACTUALLY LANDED. A handover that quietly drew
          // the old triangles would look like a fix and be nothing; the count
          // the surface reports back is the only thing that says otherwise.
          if (pool.host.triangleCount !== pool.m
              || (typeof pool.host.isTransparent === 'function'
                  && !pool.host.isTransparent())) {
            fast = false;
            P.pool = null;
          } else {
            ownHover(P);
            var sp = P.gd._fullLayout.scene._scene;
            if (sp && sp.glplot && sp.glplot.redraw) sp.glplot.redraw();
            return true;
          }
        }
        // EACH SHAPE ON ITS OWN, which is right for a single surface and the
        // best available for shapes that may not be pooled.
        restore(P, objs);
        for (n = 0; n < objs.length; n++) order(P.meshes[n], look);
        for (n = 0; n < objs.length; n++) {
          var send = {}, had = objs[n].__cqGiven, key;
          for (key in had) if (had.hasOwnProperty(key)) send[key] = had[key];
          send.cells = P.meshes[n].tri;
          var norms = normalsOnce(P.meshes[n], had);
          if (norms) send.vertexNormals = norms;
          send.__cq = true;
          objs[n].update(send);
        }
        // AND CHECK THAT IT IS STILL SEE-THROUGH. This is the guard that the
        // fault above would have tripped immediately, and it stays because
        // the next version of the library may reset something else in the
        // same way. If the shape has stopped being see-through, the quick
        // door is abandoned for good and the front door repairs the picture.
        for (n = 0; n < objs.length; n++) {
          if (typeof objs[n].isTransparent === 'function'
              && !objs[n].isTransparent()) { fast = false; break; }
        }
        if (fast) {
          var s = P.gd._fullLayout.scene._scene;
          if (s && s.glplot && s.glplot.redraw) s.glplot.redraw();
          return true;
        }
      } catch (e) { fast = false; }
    }
    // THE FRONT DOOR. Slower, always available, and the only thing used until
    // the library has been overheard building each surface at least once --
    // which the very first pass through here makes it do. It cannot pool,
    // because it works on the traces the page is written from and pooling is
    // deliberately confined to what is drawn.
    P.pool = null;
    restore(P, null);
    for (n = 0; n < P.meshes.length; n++) order(P.meshes[n], look);
    if (!window.Plotly || !Plotly.restyle) return false;
    var ii = [], jj = [], kk = [], which = [];
    for (var q = 0; q < P.meshes.length; q++) {
      var A = P.meshes[q], ni = new Array(A.m), nj = new Array(A.m),
          nk = new Array(A.m);
      for (var f = 0; f < A.m; f++) {
        ni[f] = A.tri[f][0]; nj[f] = A.tri[f][1]; nk[f] = A.tri[f][2];
      }
      ii.push(ni); jj.push(nj); kk.push(nk); which.push(A.index);
    }
    try { Plotly.restyle(P.gd, {i: ii, j: jj, k: kk}, which); }
    catch (e) { return false; }
    return true;
  }

  // NEVER MORE THAN A QUARTER OF THE TIME. How long this takes depends on how
  // many triangles there are, and that runs from 978 for one measured chart
  // to 19,230 when the Detail slider is at 40 -- measured at 2.3 ms and
  // 19.4 ms, and the second of those is longer than a frame. Rather than
  // guess a triangle count at which to give up, the last one is timed and the
  // next is made to wait three times as long as it took. A small shape is
  // re-ordered on every frame; a large one four or five times a second, which
  // is far more often than an eye can catch the difference while it turns.
  var cost = 0, ready = 0;

  function pass(force) {
    var did = false;
    var now = (window.performance || Date).now();
    if (!force && now < ready) return false;
    for (var q = 0; q < plots.length; q++) {
      var P = plots[q], look = lineOfSight(P.gd);
      if (!look) continue;
      if (!force && P.was) {
        // ONLY WHEN IT MATTERS. Both are one unit long, so the gap between
        // them is the angle turned through: 0.008 is about half a degree,
        // which cannot change which triangle is in front of which.
        var d = 0;
        for (var t = 0; t < 3; t++)
          d += (look[t] - P.was[t]) * (look[t] - P.was[t]);
        if (d < 0.000064) continue;
      }
      P.was = look;
      if (hand(P, look)) did = true;
    }
    if (did) {
      // Smoothed, so one slow frame -- a browser busy with something else --
      // does not stand the shape down for half a second afterwards.
      var took = (window.performance || Date).now() - now;
      cost = cost ? (cost * 3 + took) / 4 : took;
      ready = (window.performance || Date).now() + cost * 3;
    }
    return did;
  }

  // A LOOP THAT PUTS ITSELF BACK TO SLEEP. Watching every frame for ever
  // would keep a page awake that nobody is turning; stopping the moment the
  // picture settles means a still page costs nothing, and the backstop below
  // catches the one thing that moves the camera without saying so.
  function tick() {
    raf = window.requestAnimationFrame(tick);
    if (document.hidden) return;
    still = pass(false) ? 0 : still + 1;
    if (still > 45) { window.cancelAnimationFrame(raf); raf = null; }
  }
  function wake() {
    still = 0;
    if (raf === null) raf = window.requestAnimationFrame(tick);
  }

  // ONCE, AND ONLY ONCE. Opening a page runs the start below again and again
  // until the picture exists, and an earlier version hung its listeners on
  // every one of those attempts: eleven copies of each, and the library said
  // so out loud. Every one of them would have done the same work on the same
  // frame.
  function listen() {
    if (listening) return;
    var gs = graphs();
    if (!gs.length) return;
    listening = true;
    for (var q = 0; q < gs.length; q++) {
      var gd = gs[q];
      ['mousedown', 'wheel', 'touchstart', 'touchmove', 'keydown']
        .forEach(function (kind) {
          gd.addEventListener(kind, wake, {passive: true});
        });
      if (gd.on) {
        gd.on('plotly_relayout', wake);
        gd.on('plotly_relayouting', wake);
        // THE SHAPES THEMSELVES CHANGED, not the angle: a strength control
        // can make a solid surface see-through or the other way round, so
        // which surfaces need ordering has to be worked out again.
        gd.on('plotly_restyle', function () { collect(); wake(); });
        gd.on('plotly_afterplot', wake);
      }
    }
    // THE TURNING MOVES THE CAMERA WITHOUT TELLING ANYBODY. cqSpin sets it
    // straight on the scene -- "cheap: no relayout" -- so no event arrives
    // and a spinning page would never be put in order. This looks now and
    // then, does nothing but compare three numbers when nothing has moved,
    // and hands over to the frame loop when something has.
    if (watch === null) watch = window.setInterval(function () {
      if (raf !== null || document.hidden) return;
      for (var q = 0; q < plots.length; q++) {
        var look = lineOfSight(plots[q].gd), was = plots[q].was;
        if (!look) continue;
        if (!was) { wake(); return; }
        var d = 0;
        for (var t = 0; t < 3; t++)
          d += (look[t] - was[t]) * (look[t] - was[t]);
        if (d >= 0.000064) { wake(); return; }
      }
    }, 250);
  }

  // DONE ONCE THE PICTURE EXISTS, whether or not anything in it is
  // see-through. A page of solid shapes has nothing to order today and may
  // have something the moment a strength control is touched, so it still
  // needs its listeners -- and the retrying below has to stop, which is what
  // the answer here means.
  function start() {
    if (!graphs().length) return 0;
    listen();
    collect();
    pass(true);
    if (plots.length) wake();
    return 1;
  }

  return {start: start, collect: collect, wake: wake,
          now: function () { return pass(true); },
          pool: function (on) { pooling = !!on; return pass(true); },
          // For the tests: which door was used, and how much there is to do.
          how: function () {
            var n = 0, pooled = 0, surfaces = 0;
            for (var q = 0; q < plots.length; q++) {
              for (var m = 0; m < plots[q].meshes.length; m++)
                n += plots[q].meshes[m].m;
              surfaces += plots[q].meshes.length;
              if (plots[q].pool) pooled += plots[q].pool.count;
            }
            return {fast: fast, plots: plots.length, faces: n,
                    surfaces: surfaces, pooled: pooled};
          }};
})();
window.addEventListener('load', function () {
  // AFTER THE PICTURE EXISTS. The scene is built asynchronously, so asking on
  // load alone finds nothing to order on a slower machine; this keeps asking
  // until there is something, and then stops.
  var tries = 0;
  (function again() {
    if (window.cqOrder.start() || ++tries > 40) return;
    window.setTimeout(again, 120);
  })();
});
"""


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
  // A CROSS-SECTION HAS NO CAMERA. It is drawn flat, looking straight down,
  // and what stands in for moving the eye is the pair of axis ranges. Every
  // one of zoom, move and reset therefore has two bodies -- the same idea
  // expressed in the only terms each kind of picture has. Everything above
  // this line belongs to the turning, which a flat page never does.
  // A SCENE THAT EXISTS BUT IS NOT DRAWN YET IS STILL A SCENE. Asking whether
  // the built 3D scene is there would call a page flat for the first frames
  // after it opens -- and a flat page's zoom, applied to a scene, moves the
  // axes of a picture that has none.
  function isFlat(gd) {
    var fl = gd._fullLayout || {};
    return !fl.scene && !!(fl.xaxis && fl.yaxis);
  }
  function ranges(gd) {
    var fl = gd._fullLayout;
    if (!fl || !fl.xaxis || !fl.xaxis.range || !fl.yaxis) return null;
    return {x: fl.xaxis.range.slice(), y: fl.yaxis.range.slice()};
  }
  function setRanges(gd, r) {
    if (!window.Plotly || !r) return;
    Plotly.relayout(gd, {"xaxis.range": r.x.slice(),
                         "yaxis.range": r.y.slice()});
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
  // WHERE EACH SHAPE WAS WHEN THE PAGE OPENED. A reader who drags a shape
  // into a corner, or zooms until it fills the screen, otherwise has no way
  // back but reloading -- and reloading on a page that arrived by email is
  // not obvious either. Captured before the first movement is applied rather
  // than polled for, so it is the view the sender chose to the last decimal.
  var home = {};
  function keep(id, cam) {
    if (home[id] || !cam || !cam.eye) return;
    home[id] = {up: {x: (cam.up || {}).x, y: (cam.up || {}).y, z: (cam.up || {}).z},
                center: {x: (cam.center || {}).x, y: (cam.center || {}).y,
                         z: (cam.center || {}).z},
                eye: {x: cam.eye.x, y: cam.eye.y, z: cam.eye.z}};
  }
  function keepFlat(id, r) {
    if (home[id] || !r) return;
    home[id] = {x: r.x.slice(), y: r.y.slice()};
  }
  // A STILL PAGE NEVER STEPS, so it would never capture anything. Poll until
  // the drawing library has built each scene, then stop.
  function remember(tries) {
    var missing = false;
    for (var i = 0; i < ids.length; i++) {
      var gd = scene(ids[i]);
      if (gd && isFlat(gd)) keepFlat(ids[i], ranges(gd));
      else if (gd) keep(ids[i], liveCam(gd));
      if (gd) gestures(gd);       // a finger works from the first frame
      if (!home[ids[i]]) missing = true;
    }
    if (missing && (tries || 0) < 60)
      window.setTimeout(function () { remember((tries || 0) + 1); }, 120);
  }
  function reset() {
    rest();
    for (var i = 0; i < ids.length; i++) {
      var gd = scene(ids[i]), was = home[ids[i]];
      if (!gd || !was) continue;
      if (was.eye) setCam(gd, was);
      else setRanges(gd, was);
    }
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
    keep(id, cam);                // before anything is applied to it

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
  // ZOOMING AND MOVING, WHICH A FINGER CANNOT OTHERWISE DO.
  //
  // The drawing library's 3D camera decides between turning, moving and
  // zooming by WHICH MOUSE BUTTON is down -- left turns, right moves, middle
  // zooms -- or by a held Ctrl or Alt. Its touch handler reads one finger and
  // reports it as the left button, so on a phone the only one of the three
  // that can ever happen is turning. There is no gesture for the other two
  // and no key to hold down. Measured on a page in a browser told it was a
  // phone: a pinch and a two-finger drag both moved the picture by 0.0000.
  //
  // So both are done here instead, on the same eye/centre/up the turning uses.

  //: How close and how far the reader may get, as a multiple of the distance
  //: the page opened at. Far enough in to read one dent, far enough out to
  //: lose the shape in the middle of the screen -- and no further, because a
  //: view you cannot get back from is a broken page when reset is switched off.
  var NEAREST = 0.12, FURTHEST = 8;

  function zoomOne(one, scale) {
    var gd = one.gd, id = one.id;
    if (one.flat) {
      var r = one.was; if (!r) return;
      keepFlat(id, r);
      var was = home[id] || r;
      var span = (was.x[1] - was.x[0]);
      var now = (r.x[1] - r.x[0]) / scale;
      // The same stops as a scene, expressed in the width of the picture:
      // zoomed IN is a SMALLER span, so the near limit is the small one.
      now = Math.max(span * NEAREST, Math.min(span * FURTHEST, now));
      var k = now / (r.x[1] - r.x[0]);
      var mx = (r.x[0] + r.x[1]) / 2, my = (r.y[0] + r.y[1]) / 2;
      var hy = (r.y[1] - r.y[0]) / 2 * k, hx = now / 2;
      setRanges(gd, {x: [mx - hx, mx + hx], y: [my - hy, my + hy]});
      return;
    }
    var cam = one.was; if (!cam || !cam.eye) return;
    keep(id, cam);
    var c = cam.center || {x: 0, y: 0, z: 0};
    var e = [cam.eye.x - c.x, cam.eye.y - c.y, cam.eye.z - c.z];
    var d = Math.sqrt(e[0] * e[0] + e[1] * e[1] + e[2] * e[2]);
    if (!(d > 1e-9)) return;
    var was = home[id];
    var start = was && was.eye
      ? Math.sqrt(Math.pow(was.eye.x - was.center.x, 2)
                + Math.pow(was.eye.y - was.center.y, 2)
                + Math.pow(was.eye.z - was.center.z, 2)) : d;
    // BIGGER MEANS CLOSER, so the distance is divided rather than multiplied.
    var want = Math.max(start * NEAREST,
                        Math.min(start * FURTHEST, d / scale));
    var k = want / d;
    setCam(gd, {up: cam.up, center: c,
                eye: {x: c.x + e[0] * k, y: c.y + e[1] * k,
                      z: c.z + e[2] * k}});
  }

  // HOW THE PICTURE MOVES, NOT HOW THE EYE DOES: dx above zero means the
  // shape travels to the RIGHT across the screen, dy above zero means it
  // travels UP. Both are therefore applied backwards to the thing actually
  // being moved -- the eye goes left for the shape to go right, and the
  // window onto a flat cut slides left for the drawing inside it to go right.
  //
  // Worth stating this plainly because getting it backwards is the easiest
  // way in the world to ship four arrow buttons that all feel broken, and
  // because the two halves of this function had it two different ways round
  // the first time it was written: the left-and-right pair moved the eye and
  // the up-and-down pair moved the picture, so on a scene the arrows fought
  // each other and on a flat cut two of the four went the wrong way.
  function slideOne(one, dx, dy) {
    var gd = one.gd, id = one.id;
    if (one.flat) {
      var r = one.was; if (!r) return;
      keepFlat(id, r);
      var wx = (r.x[1] - r.x[0]), wy = (r.y[1] - r.y[0]);
      setRanges(gd, {x: [r.x[0] - dx * wx, r.x[1] - dx * wx],
                     y: [r.y[0] - dy * wy, r.y[1] - dy * wy]});
      return;
    }
    var cam = one.was; if (!cam || !cam.eye) return;
    keep(id, cam);
    var c = cam.center || {x: 0, y: 0, z: 0};
    var e = [cam.eye.x - c.x, cam.eye.y - c.y, cam.eye.z - c.z];
    var d = Math.sqrt(e[0] * e[0] + e[1] * e[1] + e[2] * e[2]);
    var u = cam.up ? [cam.up.x, cam.up.y, cam.up.z] : [0, 0, 1];
    // The two directions across the screen, taken from the camera itself so
    // they stay true however far it has been turned or tumbled.
    var right = unit(cross(u, e));
    if (!right) return;
    var upv = unit(cross(e, right));
    if (!upv) return;
    // SCALED BY THE DISTANCE, so one press moves the same fraction of the
    // picture whether you are far out or right up against the surface.
    // Negated: see above -- the eye goes the other way from the picture.
    var sx = -dx * d, sy = -dy * d;
    var mv = [right[0] * sx + upv[0] * sy,
              right[1] * sx + upv[1] * sy,
              right[2] * sx + upv[2] * sy];
    setCam(gd, {up: cam.up,
                center: {x: c.x + mv[0], y: c.y + mv[1], z: c.z + mv[2]},
                eye: {x: cam.eye.x + mv[0], y: cam.eye.y + mv[1],
                      z: cam.eye.z + mv[2]}});
  }

  // READ EVERY PICTURE FIRST, THEN CHANGE THEM ALL.
  //
  // Two cross-sections side by side are tied together: change the range on
  // one and a listener copies it to the other, so that the two always show
  // the same patch of colour space. Zooming them one after the other in a
  // single loop therefore zooms the second one twice -- it is changed once by
  // the link, and then again by this code, which by then is reading the
  // ALREADY zoomed range and dividing it a second time. The right-hand pane
  // would end up smaller than the left with every press, which is precisely
  // the fault the link exists to prevent.
  //
  // Reading all of them before writing any of them makes each step depend
  // only on where things were when the button was pressed.
  function each(apply) {
    var live = [], i;
    for (i = 0; i < ids.length; i++) {
      var gd = scene(ids[i]);
      if (!gd) continue;
      var flat = isFlat(gd);
      // The reading is taken HERE, before anything has been written to
      // anything -- that is the whole point of this function.
      live.push({gd: gd, id: ids[i], flat: flat,
                 was: flat ? ranges(gd) : liveCam(gd)});
    }
    for (i = 0; i < live.length; i++)
      if (live[i].was) apply(live[i]);
  }
  function zoom(scale) {
    if (!(scale > 0)) return;
    each(function (one) { zoomOne(one, scale); });
  }
  function slide(dx, dy) {
    each(function (one) { slideOne(one, dx || 0, dy || 0); });
  }

  // STANDING SOMEWHERE PARTICULAR TO LOOK FROM.
  //
  // Dragging is how you explore a shape and a poor way to arrive at a known
  // position: getting the eye exactly over the top of a gamut by hand takes
  // several goes and is never quite square, and two people comparing two
  // pages by eye are comparing two different angles unless both can get to
  // the same one. Four fixed places to stand fix that -- press the same one
  // on both pages and the two pictures are strictly comparable.
  //
  // The direction is in the picture's own three axes, whatever they are
  // named, so this means the same thing in ink amounts as in CIELAB.
  //
  // ONLY THE DIRECTION CHANGES. How far away the eye is and what it is
  // pointed at are left exactly as the reader had them, so pressing one of
  // these after zooming in on a corner keeps you at that corner, seen from
  // somewhere else. That is the useful behaviour: the alternative throws
  // away the very thing they were looking at.
  var LOOKS = {
    // Straight down the third axis. Its `up` cannot be the third axis too --
    // the eye would be sitting on it, the view would have no left or right,
    // and the picture flips or vanishes.
    above:  {eye: [0, 0, 1],          up: [0, 1, 0]},
    front:  {eye: [0, -1, 0],         up: [0, 0, 1]},
    side:   {eye: [1, 0, 0],          up: [0, 0, 1]},
    angle:  {eye: [1.3, -1.3, 0.85],  up: [0, 0, 1]}
  };
  function lookOne(one, where) {
    if (one.flat) return;                 // a cut is already looked straight at
    var cam = one.was; if (!cam || !cam.eye) return;
    keep(one.id, cam);
    var c = cam.center || {x: 0, y: 0, z: 0};
    var e = [cam.eye.x - c.x, cam.eye.y - c.y, cam.eye.z - c.z];
    var d = Math.sqrt(e[0] * e[0] + e[1] * e[1] + e[2] * e[2]);
    if (!(d > 1e-9)) return;
    var want = unit(where.eye);
    if (!want) return;
    setCam(one.gd, {
      up: {x: where.up[0], y: where.up[1], z: where.up[2]},
      center: c,
      eye: {x: c.x + want[0] * d, y: c.y + want[1] * d,
            z: c.z + want[2] * d}});
  }
  function look(name) {
    var where = LOOKS[name];
    if (!where) return;
    // STANDING STILL TO DO IT. Left turning, the shape would be carried on
    // round from the position just set and the reader would see it swing
    // away from the very view they asked for -- so the movement stops, which
    // is also what somebody pressing "from above" plainly means.
    on = false;
    rest();
    each(function (one) { lookOne(one, where); });
  }

  // TWO FINGERS, WHICH THE LIBRARY THROWS AWAY.
  //
  // Its own handler reads changedTouches[0] and nothing else, so during a
  // pinch it takes whichever finger moved last for a one-finger drag and
  // turns the shape wildly while you are trying to zoom. Both have to be
  // taken over together: doing the pinch without silencing the turning would
  // be worse than not doing it at all.
  //
  // Caught on the way DOWN the tree (capture) rather than on the way up,
  // because the library listens on the canvas inside this element -- a
  // listener here in the capture phase runs first, and stopping the event
  // there means the canvas never sees it. One finger is deliberately left
  // completely alone, so turning goes on working exactly as it did.
  function gestures(gd) {
    if (gd._cqGestures) return;
    gd._cqGestures = true;
    // THE ELEMENT HANDLES ITS OWN TOUCHES. Without this the browser is free
    // to read a drag as a page scroll and simply stop delivering the moves --
    // measured: a page whose touchstart nobody objects to gets touchstart and
    // touchend and not one touchmove in between.
    gd.style.touchAction = "none";
    var live = false, was = 0, mid = null;
    function span(t) {
      var dx = t[0].clientX - t[1].clientX, dy = t[0].clientY - t[1].clientY;
      return Math.sqrt(dx * dx + dy * dy);
    }
    function middle(t) {
      return {x: (t[0].clientX + t[1].clientX) / 2,
              y: (t[0].clientY + t[1].clientY) / 2};
    }
    function stop(ev) { ev.preventDefault(); ev.stopPropagation(); }
    gd.addEventListener("touchstart", function (ev) {
      if (ev.touches.length < 2) return;
      live = true; was = span(ev.touches); mid = middle(ev.touches);
      stop(ev);
    }, {capture: true, passive: false});
    gd.addEventListener("touchmove", function (ev) {
      if (!live) return;
      stop(ev);
      if (ev.touches.length < 2) return;
      var now = span(ev.touches), here = middle(ev.touches);
      if (was > 1 && now > 1) {
        var scale = now / was;
        // A sixtieth is below what a hand can hold still; acting on it makes
        // the picture creep while somebody is only trying to slide it.
        if (Math.abs(scale - 1) > 1 / 60) zoom(scale);
      }
      var box = gd.getBoundingClientRect();
      if (box.width > 0 && box.height > 0 && mid) {
        // The picture follows the fingers: they go right, it goes right.
        slide((here.x - mid.x) / box.width, -(here.y - mid.y) / box.height);
      }
      was = now; mid = here;
    }, {capture: true, passive: false});
    function ended(ev) {
      if (!live) return;
      stop(ev);
      // HELD UNTIL THE LAST FINGER IS UP. Handing a half-finished pinch back
      // to the library mid-gesture makes it turn the shape from wherever its
      // own stale last-position was, which reads as the picture jumping.
      if (ev.touches.length === 0) { live = false; mid = null; was = 0; }
    }
    gd.addEventListener("touchend", ended, {capture: true, passive: false});
    gd.addEventListener("touchcancel", ended, {capture: true, passive: false});
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
    if (o.ids !== undefined) { ids = o.ids; rest(); remember(0); }
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
  return {set: set, nudge: nudge, reset: reset, zoom: zoom, slide: slide,
          look: look, moving: function () { return on; }};
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


def _escape_title(text: str) -> str:
    """Plain text safe to put between <title> tags.

    A measurement can be called anything at all, including something with a
    < or an & in it, and a title is one of the few places a stray character
    ends the element early and takes the rest of the page with it.
    """
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").strip() or "Measured gamut")


#: Endings this module puts after a shape's own name when it draws that shape
#: more than one way. They belong in the key beside the picture, where they say
#: which of two entries is which -- and nowhere near the browser tab, where
#: "Glossy-paper and Matte-paper (outline)" is a mouthful that answers nothing.
#:
#: A LIST RATHER THAN A PATTERN, deliberately. Stripping anything in brackets
#: would eat a measurement the user themselves called "Canon (matte)", and the
#: name a person chose is the one thing the tab must keep. Only the endings
#: this file adds are removed, and `test_title_knows_every_suffix` fails if a
#: new one is added to the drawing code without being added here.
_OWN_SUFFIXES = (" (outline)", " (rings inside)")


def _page_title(fig) -> str:
    """What the browser tab should say: the things in the picture, by name.

    THE CAPTION IS THE WRONG SOURCE and looking at eight real exports is what
    showed it. A measurement's caption says what the colours were measured
    *against* — "Measured gamut — lightness and colour measured from a D50
    white" — which is true of nearly every page this application writes, so
    seven of eight tabs came out identical and a bookmark said nothing at all.

    The legend already names what is actually there: the papers, the
    comparison, the chart. Those are what somebody is looking for in a row of
    tabs, so those are what the tab says, with the caption kept as a fallback
    for a scene that somehow has no named shape in it.
    """
    names, seen = [], set()
    try:
        for trace in fig.data:
            raw = getattr(trace, "name", None) or ""
            # Traces are named "<thing> — outline", "<thing> — outside" and so
            # on; the thing is what matters and it appears several times.
            base = str(raw).split(" — ")[0].strip()
            for ending in _OWN_SUFFIXES:
                if base.endswith(ending):
                    base = base[: -len(ending)].strip()
                    break
            if base and base not in seen:
                seen.add(base)
                names.append(base)
    except Exception:                     # noqa: BLE001 — never take a page
        names = []                        # down over its own title
    if names:
        listed = (names[0] if len(names) == 1 else
                  " and ".join([", ".join(names[:-1]), names[-1]]))
        return _escape_title(listed)
    try:
        text = fig.layout.title.text or ""
    except Exception:                     # noqa: BLE001 — a title is not worth
        text = ""                         # taking a page down for
    # The caption is styled markup; the tab wants words.
    text = re.sub(r"<[^>]+>", "", str(text)).strip()
    if len(text) > 90:
        text = text[:87].rstrip(" ,;—-") + "…"
    return _escape_title(text)


def _titled(html: str, title: str) -> str:
    """The same document with a <title> in its head, added once."""
    if "<title>" in html[:4000]:
        return html
    full = f"<title>{title} — ChromIQ Gamut Viewer</title>"
    if "<head>" in html:
        return html.replace("<head>", "<head>" + full, 1)
    return html.replace("<body", full + "<body", 1)


def _spin_script(ids, spin, mode: str = "dark",
                 controls: bool = True, offer=None) -> str:
    """The turning engine plus the settings the window had when it was written.

    A saved page keeps whatever was on screen when it was saved, so a page sent
    to somebody arrives doing what the sender was looking at.

    *mode* is which paper the page is on, and it is passed down because the
    control strip has to paint itself: the document sets a background and no
    text colour, so anything inheriting its colour comes out browser-default
    black -- which on the dark page is very nearly the background.

    *controls* is the strip a reader gets along the bottom, and it is FALSE
    for the application's own view. That view is not a page somebody was sent:
    the window already has movement controls, with better labels than a strip
    can fit ("45 s a turn" rather than "speed 7"), and a second set floating
    over the picture is two controls for one thing. Worse, they can disagree
    -- a nudge of the speed slider goes straight to the engine, so the strip
    goes on showing a number that is no longer true and pressing + on it
    yanks the movement back to that stale figure. The engine still travels
    into the live view; only the strip stays out of it.

    *spin* may be ``{"flat": True}`` and nothing else, which is a page with no
    movement in it at all -- a cross-section, drawn looking straight down.
    That still wants the engine, because zooming, moving and getting back to
    where you started are not movement settings and apply to any picture.
    """
    if not spin:
        return ""
    import json

    which = "light" if mode == "light" else "dark"
    colours = SCENE_COLOURS[which]
    settings = dict(spin)
    settings["ids"] = list(ids)
    settings["ink"] = colours["text"]
    settings["paper"] = colours["page"]
    settings["mode"] = which
    settings["show"] = dict(offer or {})
    # BOTH PALETTES, but only when the page is allowed to switch between
    # them. A page that cannot change its paper has no use for the other one,
    # and there is no reason to put it in the file.
    if settings["show"].get("appearance"):
        settings["palettes"] = {k: dict(v) for k, v in SCENE_COLOURS.items()}
        # AND THE ORDER TO MOVE THROUGH THEM, starting from the one the page
        # was saved in, so the first press goes somewhere rather than
        # appearing to do nothing.
        settings["schemes"] = ([which]
                               + [k for k in PAGE_SCHEMES if k != which])
    if not controls:
        return (f"<script>{_SPIN_JS}\n"
                f"window.addEventListener('load', function () "
                f"{{window.cqSpin.set({json.dumps(settings)});}});</script>")
    # WRITTEN ONCE AND HANDED TO BOTH. These two used to be given their own
    # copy of the settings, which cost nothing while the settings were a
    # dozen numbers -- and then the cross-sections a reader can slide through
    # moved in, and one page was carrying 336 kB of outlines where it needed
    # 168.
    blob = json.dumps(settings)
    return (f"<script>{_SPIN_JS}\n{_SPIN_CONTROLS_JS}\n"
            f"window.addEventListener('load', function () "
            f"{{var s = {blob};window.cqSpin.set(s);"
            f"window.cqSpinControls(s);}});</script>")


#: The strip of controls the reader of a saved page gets.
#:
#: WHY IT IS BUILT IN JAVASCRIPT rather than written into the page's HTML: the
#: page is assembled by three different routes (one scene, two rooms, a flat
#: slice) and a bar added to each of them is three places to forget. Built by
#: the engine that does the turning, it appears exactly where the turning does
#: and nowhere else.
#:
#: IT APPEARS ON EVERY PAGE, moving or not. A first version showed it only
#: where the page was already turning, which meant a scene saved still could
#: never be set moving by the person reading it — and being able to is the
#: whole advantage a page has over a picture. A still page simply opens with
#: the button reading Play and nothing moving: no movement ever starts unbidden.
_SPIN_CONTROLS_JS = """
window.cqSpinControls = function (settings) {
  settings = settings || {};
  // COPIES, not the settings themselves. These are mutated as the reader
  // switches an axis off, and holding a reference to the originals is how
  // "switch it back on" would restore whatever it had just been set to
  // instead of what the page was saved with.
  var saved = {turn: Object.assign({}, settings.turn || {}),
               tilt: Object.assign({}, settings.tilt || {})};
  var turn = Object.assign({}, saved.turn), tilt = Object.assign({}, saved.tilt);
  // WHICH CONTROLS THIS PAGE WAS GIVEN. Chosen when it was saved, so one page
  // can be a bare picture with a Pause button and the next can hand over
  // everything. Anything not named here is simply not built.
  var show = settings.show || {};
  // A CROSS-SECTION IS ALREADY FLAT. It is drawn looking straight down and
  // there is no third direction to turn it in, so every control about
  // movement is not merely switched off here -- it is never built. A button
  // that is present and does nothing is worse than a missing one: the reader
  // presses it, nothing happens, and now they doubt the whole page.
  //
  // Zooming, moving and putting it back are exactly as useful on a flat cut
  // as on a shape, and that is why this page has a strip at all now: the
  // drawing library's own toolbar is its only way back from a zoom, and that
  // toolbar is hidden on anything narrower than a tablet. On a phone, a
  // cross-section could be zoomed into and never zoomed out of.
  var flat = !!settings.flat;
  var TURNS = {play: 1, speed: 1, speed_each: 1, lr: 1, ud: 1};
  function on(what, fallback) {
    if (flat && TURNS[what]) return false;
    return show[what] === undefined ? fallback : !!show[what];
  }
  var speeds = {turn: saved.turn.speed || 6, tilt: saved.tilt.speed || 6};
  // HOW FAR EACH DIRECTION SWINGS, which the window has always had a slider
  // for and a saved page had no way of touching -- a reader could change how
  // FAST it swung and not how far, which are two quite different things to
  // watch. The limits are the window's own (15-180 degrees left and right,
  // 10-120 up and down), so a page cannot be set to something the window
  // itself would not allow.
  var ranges = {turn: saved.turn.range || 60, tilt: saved.tilt.range || 40};
  var SWEEP = {turn: [15, 180], tilt: [10, 120]};
  // WHICH WAY EACH DIRECTION MOVES WHEN IT IS ON: a swing that comes back,
  // or a full turn that never does. The window has always offered both and a
  // saved page offered neither -- whatever it was saved with was all a
  // reader could ever have.
  //
  // THE TWO ARE ONE CONTROL HERE, not a sweep and a separate mode switch.
  // Widening the swing step by step and then one step further is exactly how
  // somebody would describe going all the way round, so the reading runs
  // 60°, 70° … 180°, round. One control, one idea, and three fewer buttons
  // in a row that has to survive a phone.
  var chosen = {
    turn: (saved.turn.mode && saved.turn.mode !== "off") ? saved.turn.mode : "round",
    tilt: (saved.tilt.mode && saved.tilt.mode !== "off") ? saved.tilt.mode : "swing"};
  function swings(which) { return on("sweep", false); }
  function sweepReads(which) {
    return chosen[which] === "round" ? "round"
           : Math.round(ranges[which]) + "\u00b0";
  }
  // ONE SPEED OR TWO. With the per-direction speeds switched off, the single
  // speed scales both together and keeps the proportion the page was saved
  // with -- a slow tip under a quicker turn stays a slow tip under a quicker
  // turn. Switched on, each direction is simply its own number.
  var both = Math.round(Math.max(speeds.turn, speeds.tilt)) || 6;
  var start = both;
  function speedFor(which) {
    if (on("speed_each", false)) return speeds[which];
    if (!saved[which].speed) return both;
    return Math.max(0.5, saved[which].speed * both / start);
  }
  var running = !!settings.on;
  var ink = settings.ink || "#e6e6e6";
  var paper = settings.paper || "#111111";
  // BOTH PALETTES TRAVEL when the page offers a light/dark switch, because
  // the page has to be able to become the other one without asking anybody.
  var palettes = settings.palettes || null;
  var mode = settings.mode || "dark";
  var picture = {grid: true, labels: true, key: true, notes: true};

  // ------------------------------------------------------------------ shapes
  //
  // ONE ROW PER THING THE KEY NAMES, and that is deliberate rather than
  // convenient. A page may hold a solid surface, a wire cage round a second
  // paper, a cloud of chart patches and a skin over them, and the reader has
  // no idea which of those the code calls a "gamut". What they can see is the
  // list of names under the picture. Building the rows from exactly that list
  // means the thing they press and the thing they read are the same thing.
  //
  // Gathered across EVERY picture on the page, so on a two-pane comparison a
  // name that appears in both panes is one row that acts on both. Two rows
  // doing half the job each is how a side-by-side page ends up with one pane
  // faded and the other not.
  var agreed = false;                  // does this page carry the split at all
  function findShapes() {
    var found = [], byKey = {};
    (settings.ids || []).forEach(function (id) {
      var gd = document.getElementById(id);
      if (!gd || !gd.data) return;
      gd.data.forEach(function (t, at) {
        var key = t.legendgroup || t.name || (id + " " + at);
        var g = byKey[key];
        if (!g) {
          g = byKey[key] = {key: key, label: t.name || key, parts: [],
                            mesh: false, fill: false, points: 0,
                            plain: true, drawn: false};
          found.push(g);
        }
        // A KEY-ONLY TRACE DRAWS NOTHING. Every mesh here is accompanied by a
        // scatter of one empty point that exists solely to put a readable
        // marker beside the name -- see _legend_proxy. Fading that along with
        // the surface fades the key itself, and a key nobody can see is how
        // this page lost its legend twice before.
        var count = (t.x && t.x.length) || 0;
        var proxy = count === 1 && (t.x[0] === null || t.x[0] === undefined);
        if (t.showlegend && t.name) g.label = t.name;
        g.parts.push({gd: gd, id: id, at: at, proxy: proxy});
        if (!proxy) {
          g.drawn = true;
          g.points += count;
          if (t.type === "mesh3d") g.mesh = true;
          if (t.fill && t.fill !== "none") g.fill = true;
          // See _COLOUR_IS_THE_ANSWER in the Python that wrote this page.
          if (t.meta && t.meta.cq === "colour") g.plain = false;
          // WHICH OF THIS SHAPE'S POINTS STAND OUTSIDE THE OTHERS, one
          // character per drawn vertex, worked out when the page was written
          // because only the Python has the whole 3D shape to work it out
          // from. Its presence is also what says this page can fade at all.
          if (t.meta && t.meta.stand) { g.stand = true; agreed = true; }
        }
      });
    });
    // A ROW FOR ANYTHING THAT ACTUALLY DRAWS A SHAPE. The cross-section pages
    // carry a single cross at the origin, named "neutral grey", to say where
    // no colour at all sits. It is one point. Offering to fade it, wire it or
    // take the colour out of it is three controls for a tick mark.
    return found.filter(function (g) {
      return g.drawn && (g.mesh || g.fill || g.points > 8);
    });
  }
  var shapes = on("opacity", true) || on("wires", true) || on("grey", true)
    ? findShapes() : [];

  // WHAT EACH SHAPE IS DOING NOW, started from what the page was saved with
  // rather than from a guess. A skin saved at three-tenths opens reading 30%.
  var dressed = {};
  shapes.forEach(function (g) {
    var first = null, i;
    for (i = 0; i < g.parts.length; i++)
      if (!g.parts[i].proxy) { first = g.parts[i]; break; }
    var t = first ? first.gd.data[first.at] : {};
    dressed[g.key] = {
      opacity: (typeof t.opacity === "number") ? t.opacity : 1,
      // A SURFACE OPENS WITH NO CAGE OVER IT. This used to be read off the
      // surface's `contour` setting, which never drew one in the first place.
      wires: false,
      filled: !!(t.fill && t.fill !== "none"),
      grey: false};
    g.opened = Object.assign({}, dressed[g.key]);
  });
  // HOW MUCH OF THE AGREEMENT IS LEFT, for the whole page rather than per
  // shape: it is a statement about a pair, and one shape agreeing more than
  // another is not a thing that can be true.
  var agreeAt = 1, differAt = 1;
  function withAlpha(colour, alpha) {
    var text = String(colour);
    if (alpha >= 1 || text.indexOf("(") < 0) return colour;
    var bits = text.slice(text.indexOf("(") + 1, text.indexOf(")")).split(",");
    return "rgba(" + bits[0] + "," + bits[1] + "," + bits[2] + ","
           + alpha.toFixed(3) + ")";
  }

  // WHICH CROSS-SECTIONS THIS PAGE CARRIES, if it is one that can be slid
  // through at all. Settled HERE, above the part that reads back what the
  // reader last chose, and that position is the whole of a bug: read out
  // first, the restore ran while this was still undefined, quietly did
  // nothing, and the page opened at the height it was saved at every single
  // time however far the reader had moved the slider.
  var cuts = settings.cuts || null;
  if (cuts && !(cuts.levels && cuts.levels.length > 1)) cuts = null;
  if (!on("cut", true)) cuts = null;
  var cutAt = cuts ? (cuts.at || 0) : 0;

  // TAKING THE COLOUR OUT OF SOMETHING, PROPERLY.
  //
  // Averaging the three numbers is the quick way and it is wrong: it makes
  // pure blue and pure yellow the same grey, when one is nearly black to look
  // at and the other nearly white. Since everything drawn here is already an
  // sRGB screen colour, the honest conversion is the one sRGB itself defines
  // -- undo the transfer curve, take the luminance Y with the Rec. 709
  // weights sRGB is built on, and put the curve back. A gamut greyed this way
  // keeps its light top and dark bottom, which is what makes the shape still
  // readable once the hue has gone.
  //
  // AND IT MUST KEEP A FADE IT IS GIVEN. A colour here can carry a fourth
  // number -- the fade over the part two shapes agree on is written into the
  // colours themselves, one vertex at a time, rather than into the shape's
  // overall strength. Dropping that fourth number turns "grey" into "grey and
  // solid again", which is what this did: greying one of two shapes took its
  // faded colours from 179 to none, while the shape left alone kept all 308
  // of its own. Two switches, one of them quietly undoing the other.
  var GREY = {};
  function toGrey(c) {
    if (GREY[c] !== undefined) return GREY[c];
    var s = String(c).trim(), r, g2, b, a = 1;
    var m = s.match(/^rgba?\\(([^)]+)\\)/i);
    if (m) {
      var bits = m[1].split(",");
      r = parseFloat(bits[0]); g2 = parseFloat(bits[1]); b = parseFloat(bits[2]);
      if (bits.length > 3) {
        var got = parseFloat(bits[3]);
        if (isFinite(got)) a = got;
      }
    } else if (s.charAt(0) === "#") {
      var h = s.slice(1);
      if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
      var n = parseInt(h, 16);
      if (!isFinite(n) || h.length < 6) return (GREY[c] = s);
      r = (n >> 16) & 255; g2 = (n >> 8) & 255; b = n & 255;
    } else {
      return (GREY[c] = s);          // a name we do not know: leave it alone
    }
    if (!(isFinite(r) && isFinite(g2) && isFinite(b))) return (GREY[c] = s);
    function lin(v) {
      v = v / 255;
      return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    }
    var Y = 0.2126 * lin(r) + 0.7152 * lin(g2) + 0.0722 * lin(b);
    var e = Y <= 0.0031308 ? 12.92 * Y : 1.055 * Math.pow(Y, 1 / 2.4) - 0.055;
    var v = Math.max(0, Math.min(255, Math.round(e * 255)));
    return (GREY[c] = a < 1
      ? "rgba(" + v + "," + v + "," + v + "," + a + ")"
      : "rgb(" + v + "," + v + "," + v + ")");
  }

  // THE COLOUR EACH TRACE WAS DRAWN WITH, kept outside the drawing library's
  // own data. Stashing it on the trace object would work until the day
  // something re-reads that object and complains about a field it has never
  // heard of; a map of our own cannot collide with anything.
  var ORIGINAL = {};
  function was(part, field, value) {
    var k = part.id + "\\u0000" + part.at + "\\u0000" + field;
    if (!(k in ORIGINAL)) ORIGINAL[k] = value;
    return ORIGINAL[k];
  }
  function greyed(value) {
    return Array.isArray(value) ? value.map(toGrey) : toGrey(value);
  }
  //: Where a colour can live on the traces this page draws. Measured from the
  //: real pages rather than listed from the documentation: a mesh carries
  //: `vertexcolor` (and a `color` its key is drawn from), a cage carries
  //: `line.color`, a cloud of patches carries `marker.color`, and a filled
  //: cross-section carries `line.color` with the fill derived from it.
  var COLOUR_FIELDS = ["vertexcolor", "color", "line.color", "marker.color",
                       "fillcolor"];
  function reach(t, field) {
    var bits = field.split("."), v = t, i;
    for (i = 0; i < bits.length; i++) {
      if (v === null || v === undefined) return undefined;
      v = v[bits[i]];
    }
    return v;
  }
  // A WIRE CAGE OVER A SURFACE, BUILT HERE FROM THE SURFACE'S OWN TRIANGLES.
  //
  // This button used to switch the surface's `contour` setting on, which reads
  // exactly like "draw the mesh" and is documented as
  //
  //     Sets whether or not dynamic contours are shown on hover
  //
  // -- so it drew lines under the pointer and nothing at all the rest of the
  // time. Measured on the published page, with the movement stopped and a
  // noise floor of nought: pressing it changed the picture by 0 pixels.
  // Reported simply as "I can't turn glossy to wires", which is exactly what
  // was happening.
  //
  // NOTHING IS ADDED TO THE FILE FOR THIS. The surface already carries every
  // vertex and every triangle, so the cage is worked out from those when the
  // button is first pressed: the same edges the application itself would
  // draw, each one once, since a triangle mesh shares each edge between two
  // triangles and drawing both doubles the work for an identical picture.
  //
  // AND IN THE SHAPE'S OWN COLOURS, because a cage the reader cannot tell
  // from a plain grey wire frame is not what "over its surface" promises --
  // asked for as "make the mesh look colourful like the shell would". A line
  // takes one colour for the whole trace, so the edges are grouped into bands
  // of colour, rounding each channel to the nearest 32 exactly as the
  // application does, which turns hundreds of distinct colours into a few
  // dozen traces and reads as the same smooth gradient.
  var caged = {};
  function bandOf(colour) {
    var text = String(colour);
    var at = text.indexOf("(");
    if (at < 0) return text;
    var bits = text.slice(at + 1, text.indexOf(")")).split(",");
    var out = [];
    for (var n = 0; n < 3; n++)
      out.push(Math.min(255, Math.round(parseFloat(bits[n]) / 32) * 32));
    return "rgb(" + out.join(",") + ")";
  }
  function buildCage(g) {
    var made = [];
    g.parts.forEach(function (part) {
      var full = part.gd._fullData && part.gd._fullData[part.at];
      var t = full || part.gd.data[part.at];
      if (!t || t.type !== "mesh3d" || !t.i || !t.j || !t.k) return;
      var seen = {}, bands = {}, m = t.i.length, f, e, a, b;
      var colours = t.vertexcolor;
      for (f = 0; f < m; f++) {
        var tri = [t.i[f], t.j[f], t.k[f]];
        for (e = 0; e < 3; e++) {
          a = tri[e]; b = tri[(e + 1) % 3];
          var lo = a < b ? a : b, hi = a < b ? b : a;
          var id = lo + "," + hi;
          if (seen[id]) continue;
          seen[id] = 1;
          var band = colours ? bandOf(colours[lo]) : "plain";
          var into = bands[band] || (bands[band] = {x: [], y: [], z: []});
          into.x.push(t.x[lo], t.x[hi], null);
          into.y.push(t.y[lo], t.y[hi], null);
          into.z.push(t.z[lo], t.z[hi], null);
        }
      }
      var add = [];
      Object.keys(bands).forEach(function (band) {
        var s = bands[band];
        add.push({type: "scatter3d", mode: "lines", x: s.x, y: s.y, z: s.z,
                  line: {color: band === "plain" ? "#9aa3b2" : band,
                         width: 1},
                  name: t.name, legendgroup: t.legendgroup || t.name,
                  showlegend: false, hoverinfo: "skip",
                  scene: t.scene || undefined});
      });
      if (!add.length) return;
      var from = part.gd.data.length;
      if (window.Plotly && window.Plotly.addTraces)
        keepingTheView(part.gd, function () {
          return window.Plotly.addTraces(part.gd, add);
        });
      for (var q = 0; q < add.length; q++)
        made.push({gd: part.gd, at: from + q, cage: true});
    });
    return made;
  }
  // ADDING OR REMOVING A TRACE MOVES THE CAMERA, so it is put back.
  //
  // Measured rather than guessed: turning the cage on and straight off again
  // left 159,910 pixels different on a page that had not otherwise moved, and
  // the difference picture was the whole scene drawn twice at two slightly
  // different scales -- two sets of axis numbers, two "b*" labels. Nothing
  // about the shapes had changed; the view had. Somebody who lines a shape up
  // and then presses wires would have it jump, which is its own small fault.
  function keepingTheView(gd, work) {
    var held = null;
    // A COPY, and the scene is looked up AGAIN afterwards rather than kept.
    // Adding a trace builds a new scene object, so a reference taken before
    // the change points at one that has been thrown away -- setting the
    // camera on it succeeds silently and moves nothing. Measured: everything
    // else about the scene came back identical, the axis ranges, the aspect,
    // the trace count, and only the camera had moved.
    try {
      var was = gd._fullLayout && gd._fullLayout.scene;
      var live = was && was._scene && was._scene.getCamera
        ? was._scene.getCamera() : (was && was.camera);
      if (live) held = JSON.parse(JSON.stringify(live));
    } catch (e) {}
    function putBack() {
      if (!held) return;
      try {
        var now = gd._fullLayout && gd._fullLayout.scene;
        if (now && now._scene && now._scene.setCamera)
          now._scene.setCamera(held);
      } catch (e) {}
    }
    var done = work();
    if (done && done.then) done.then(putBack, putBack); else putBack();
  }

  function showCage(g, want) {
    var have = caged[g.key];
    if (want && !have) {
      caged[g.key] = buildCage(g);
      return;
    }
    if (!want && have && have.length) {
      // TAKEN OUT FROM THE END BACKWARDS, so removing one does not renumber
      // the ones still to be removed.
      var byPlot = {};
      have.forEach(function (p) {
        (byPlot[p.gd.id] = byPlot[p.gd.id] || {gd: p.gd, at: []}).at.push(p.at);
      });
      Object.keys(byPlot).forEach(function (id) {
        var one = byPlot[id];
        one.at.sort(function (a, b) { return b - a; });
        if (window.Plotly && window.Plotly.deleteTraces)
          keepingTheView(one.gd, function () {
            return window.Plotly.deleteTraces(one.gd, one.at);
          });
      });
      caged[g.key] = null;
    }
  }

  function dressOne(g) {
    var st = dressed[g.key];
    // The cage first: greying below has to find it in place to grey it too.
    if (on("wires", true) && g.mesh) showCage(g, !!st.wires);
    // The cage's own traces are dressed alongside the surface, so greying a
    // shape greys the wires over it rather than leaving them in colour.
    var dressing = g.parts.concat(caged[g.key] || []);
    dressing.forEach(function (part) {
      var t = part.gd.data[part.at];
      if (!t) return;
      var patch = {}, any = false;
      // THE KEY KEEPS ITS FULL STRENGTH AND ITS COLOUR unless the reader
      // asked for grey, in which case it follows -- otherwise the list of
      // names would go on showing colours the picture no longer has.
      if (!part.proxy) {
        if (on("opacity", true)) { patch.opacity = st.opacity; any = true; }
        if (on("wires", true) && g.fill && t.fill !== undefined) {
          patch.fill = st.filled ? "toself" : "none"; any = true;
        }
      }
      // TWO REASONS TO REWRITE A TRACE'S COLOURS, and they are independent.
      //
      // Grey is offered only where the colour is decoration; the fade
      // applies wherever the page carries a mask. Written with the fade
      // nested inside the grey test -- as it was at first -- the comparison
      // mesh that is red for what a paper cannot reach could not be faded at
      // all, because grey is deliberately refused for it. The one page in
      // the showcase whose whole subject is comparing two measurements was
      // the one page where the new control did nothing.
      var mark = t.meta && t.meta.stand;
      // WHENEVER THERE IS A MASK, NOT ONLY WHEN SOMETHING IS FADED.
      //
      // Written as "…and something is faded", sliding back up to the top
      // skipped this whole block -- so the colours written on the way DOWN
      // were never written back, and the shape stayed faint at a reading of
      // 100%. The colours are always rebuilt from the originals, so the
      // reading and the picture cannot come apart.
      //
      // It costs nothing at rest: dressOne only runs on a press, or on load
      // for a shape whose stored settings differ from the saved ones.
      var fading = !!mark;
      var greying = on("grey", true) && g.plain;
      if (greying || fading) {
        COLOUR_FIELDS.forEach(function (field) {
          var had = reach(t, field);
          if (had === undefined || had === null) return;
          var origin = was(part, field, had);
          var want = (greying && st.grey) ? greyed(origin) : origin;
          // AND THEN THE AGREEMENT, ON TOP OF WHATEVER COLOUR THAT LEFT.
          //
          // Applied to the colours rather than to the trace's opacity, and
          // that is the whole design: cutting the surface into a faded half
          // and a solid half was built first and measured against the
          // picture as it ships -- 120,481 pixels differed by more than
          // eight levels with the fade at FULL, because a browser blends
          // transparent surfaces in the order it draws them and one closed
          // surface is not two open ones. One mesh with an alpha per point
          // has no such seam, and at the top it is the very same array of
          // colours, so it is not merely close to changing nothing.
          //
          // It composes with grey rather than fighting it: grey decides WHAT
          // colour each point is, this decides how much of it there is.
          if (fading && field === "vertexcolor" && Array.isArray(want)) {
            want = want.map(function (colour, at) {
              return withAlpha(colour,
                mark.charAt(at) === "1" ? differAt : agreeAt);
            });
          }
          // AN ARRAY HAS TO BE WRAPPED IN ANOTHER ONE. Handed a bare array,
          // restyle reads it as one value per trace and hands the FIRST
          // element to this trace -- so 491 vertex colours quietly became the
          // single string "rgb(15,12,21)" and the whole surface turned that
          // colour. Measured, not guessed: it fails silently and looks like a
          // rendering bug.
          patch[field] = Array.isArray(want) ? [want] : want;
          any = true;
        });
      }
      if (any && window.Plotly) window.Plotly.restyle(part.gd, patch, [part.at]);
    });
  }
  function moved(g) {
    var a = dressed[g.key], b = g.opened;
    return a.opacity !== b.opacity || a.wires !== b.wires
        || a.filled !== b.filled || a.grey !== b.grey
        || agreeAt < 1 || differAt < 1;
  }
  // ONLY WHAT HAS ACTUALLY CHANGED. Called once when the page opens, this
  // would otherwise re-draw every surface on it to the values it already has
  // -- a whole re-render of a chart of a thousand patches, for nothing, in
  // the first second somebody is looking at it.
  function dressAll() { shapes.filter(moved).forEach(dressOne); }
  function undress() {
    // THE AGREEMENT GOES BACK TOO. "As saved" that restored every shape's
    // strength and left the shared part faded would put the page in a state
    // it was never saved in, and leave the one control the reader most
    // likely moved as the one thing the button does not undo.
    agreeAt = 1; differAt = 1;
    shapes.forEach(function (g) {
      dressed[g.key] = Object.assign({}, g.opened);
      dressOne(g);
    });
  }

  function tint(hex, alpha) {
    var h = String(hex).replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    if (!isFinite(n)) return "rgba(0,0,0," + alpha + ")";
    return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + ","
           + (n & 255) + "," + alpha + ")";
  }
  function scenes() {
    return (settings.ids || []).map(function (id) {
      return document.getElementById(id);
    }).filter(function (gd) { return gd && gd.layout; });
  }
  function relayout(patch) {
    scenes().forEach(function (gd) {
      if (window.Plotly) window.Plotly.relayout(gd, patch);
    });
  }

  // WHAT THE READER IS ALLOWED TO REMEMBER. Comparing four papers means
  // opening four pages, and pressing Pause on every one of them is the sort
  // of small annoyance that stops somebody looking properly. Kept per page,
  // so one page's choices never surprise another.
  var STORE = "cq-view:" + (location.pathname || "page");
  function remember() {
    try {
      localStorage.setItem(STORE, JSON.stringify(
        {running: running, both: both, speeds: speeds, picture: picture,
         shapes: dressed, cutAt: cutAt, agreeAt: agreeAt, ranges: ranges,
         chosen: chosen,
         differAt: differAt,
         mode: mode, turn: turn.mode, tilt: tilt.mode}));
    } catch (e) {}
  }
  function recall() {
    try {
      var was = JSON.parse(localStorage.getItem(STORE) || "null");
      if (!was) return;
      running = !!was.running;
      both = was.both || both;
      // MERGED, NEVER REPLACED. What is remembered was written by whatever
      // version of this page the reader last opened, and a later one knows
      // about things an earlier one had never heard of. Assigning the stored
      // object straight over the defaults means every setting added since
      // arrives as "undefined", which reads as OFF -- so a reader who had
      // simply visited the page before would have come back to find the
      // written-out numbers gone, with nothing they did to explain it.
      if (was.speeds) speeds = Object.assign({}, speeds, was.speeds);
      if (was.ranges) ranges = Object.assign({}, ranges, was.ranges);
      if (was.chosen) chosen = Object.assign({}, chosen, was.chosen);
      if (was.picture) picture = Object.assign({}, picture, was.picture);
      // ONLY SHAPES THIS PAGE ACTUALLY HAS. What was stored may have been
      // written by an earlier page at the same address, or by a version of
      // this one drawn from a different measurement. Reading it back name by
      // name means an unknown name is simply ignored rather than creating a
      // row for a shape that is not there.
      if (was.shapes) {
        Object.keys(dressed).forEach(function (k) {
          if (was.shapes[k]) dressed[k] = Object.assign({}, dressed[k],
                                                        was.shapes[k]);
        });
      }
      // BOUNDED BY WHAT THIS PAGE ACTUALLY HAS. A remembered height from a
      // page with more cuts in it than this one would otherwise ask for a
      // level that does not exist, and the picture would open empty.
      if (typeof was.agreeAt === "number")
        agreeAt = Math.max(0, Math.min(1, was.agreeAt));
      if (typeof was.differAt === "number")
        differAt = Math.max(0, Math.min(1, was.differAt));
      if (was.cutAt !== undefined && cuts)
        cutAt = Math.max(0, Math.min(cuts.levels.length - 1, was.cutAt | 0));
      if (was.turn !== undefined) turn.mode = was.turn;
      if (was.tilt !== undefined) tilt.mode = was.tilt;
      if (was.mode) mode = was.mode;
    } catch (e) {}
  }
  if (on("remember", true)) recall();

  var bar = document.createElement("div");
  bar.className = "cq-spin-bar";
  var panel = document.createElement("div");
  panel.className = "cq-spin-panel";
  panel.hidden = true;

  function safe(text) {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      // THE QUOTE IS WRITTEN \\u0022 rather than typed. A regular expression
      // holding a quote character reads, to anything scanning this file for
      // an unclosed string, exactly like an unclosed string -- and one of
      // those really would take the whole strip down, so the check that looks
      // for them is worth keeping sharp rather than teaching exceptions to.
      .replace(/>/g, "&gt;").replace(/\\u0022/g, "&quot;");
  }
  function button(what, label, title, extra) {
    return '<button type="button" data-cq="' + what + '" title="' + safe(title)
           + '"' + (extra || "") + '>' + label + '</button>';
  }
  function row(what, label, title, extra) {
    return '<div class="cq-row"><span>' + label + '</span>'
           + '<span class="cq-ctl">'
           + button(what, "on", title) + (extra || "") + '</span></div>';
  }
  // A HEADING AND THE ROWS UNDER IT, added only if there are any rows.
  //
  // WHY SECTIONS AT ALL. This panel began as four switches and one flat list
  // was the right shape for it. It now runs to a speed for each direction,
  // four arrows, four places to stand, three controls for every shape on the
  // page and six more for the page itself -- and a flat list of twenty
  // unrelated things is not a panel, it is an inventory. Somebody looking for
  // "make the front one fainter" reads every line to find it.
  //
  // Grouped under plain-language headings there are five short lists instead,
  // and the heading answers "is what I want in here?" before any of the lines
  // are read. Empty groups are never drawn, so a page that hands over two
  // controls still shows two controls and no scaffolding.
  var body = "";
  function section(heading, rows, wide, aside) {
    if (!rows) return;
    // THE ASIDE SITS OUTSIDE THE GRID, under it.
    //
    // Put inside as a full-width cell it was part of the layout, so the row
    // of shape controls moved sideways the moment it appeared -- measured at
    // 300 pixels on a wide window. A note that shoves the button you are
    // reaching for is the very fault it was added to explain, and it is the
    // second time in this file that something has moved under a finger.
    // Below the grid it can only ever add height beneath everything.
    body += '<div class="cq-sect' + (wide ? " cq-wide" : "") + '">'
      + '<h4>' + heading + '</h4><div class="cq-rows">' + rows + '</div>'
      + (aside || "") + '</div>';
  }

  // ------------------------------------------------- moving the cut up and down
  //
  // THE ONE CONTROL A CROSS-SECTION PAGE WAS MISSING, and the one the window
  // itself has always had: a cut is taken at a lightness, and which lightness
  // is the interesting question. A page frozen at one of them can only ever
  // answer "does this paper reach further into the cyans" at whatever height
  // the sender happened to be looking at -- and the answer is different near
  // the white point from what it is in the shadows, which is the entire
  // reason the window has a slider rather than a number.
  //
  // The page cannot work these out for itself: slicing a gamut needs the
  // whole 3D shape, and a flat page has none. Every cut it can show was
  // therefore worked out when it was saved and travels inside it -- see
  // slice_levels in the Python. The slider only chooses between them, which
  // is why it is instant.
  function cutTraces() {
    var out = [];
    (settings.ids || []).forEach(function (id) {
      var gd = document.getElementById(id);
      if (!gd || !gd.data) return;
      gd.data.forEach(function (t, at) {
        if (t.name && cuts.rings[t.name]) out.push({gd: gd, at: at, name: t.name});
      });
    });
    return out;
  }
  function showCut(i) {
    if (!cuts) return;
    i = Math.max(0, Math.min(cuts.levels.length - 1, Math.round(i)));
    cutAt = i;
    var level = cuts.levels[i], missing = [], panes = {};
    cutTraces().forEach(function (one) {
      var ring = cuts.rings[one.name][i] || {x: [], y: []};
      if (!ring.x.length && missing.indexOf(one.name) < 0) missing.push(one.name);
      panes[one.gd.id] = one.gd;
      // Wrapped, because these are arrays -- see the note on restyle above.
      window.Plotly.restyle(one.gd, {x: [ring.x], y: [ring.y]}, [one.at]);
    });
    // THE CAPTION IS EDITED, NOT REBUILT. Two panes side by side each carry
    // their own, naming their own shape, and a caption rebuilt from one
    // template would put the same words over both. Replacing only the part
    // that says which height it is leaves everything else exactly as the
    // page was written, whichever pane it belongs to.
    var note = "";
    if (missing.length === 1)
      note = "  \\u2014  " + missing[0] + " does not reach this lightness";
    else if (missing.length > 1)
      note = "  \\u2014  " + missing.join(" and ") + " do not reach this lightness";
    Object.keys(panes).forEach(function (id) {
      var gd = panes[id];
      var was = (gd.layout && gd.layout.title && gd.layout.title.text) || "";
      if (was.indexOf("L* = ") < 0) return;
      window.Plotly.relayout(gd, {"title.text":
        was.slice(0, was.indexOf("L* = ")) + "L* = "
        + (Math.round(level * 10) / 10) + note});
    });
    say("cut-at", "L* " + Math.round(level));
    var slider = find("cut");
    if (slider && String(slider.value) !== String(i)) slider.value = String(i);
  }

  var head = "";
  if (cuts)
    head += group(button("cut-down", "&minus;", "Take the cut lower — nearer "
            + "black. A gamut is at its widest somewhere in the middle and "
            + "narrows to almost nothing at both ends, so this is where you "
            + "see how much colour is really left in the shadows.")
          + '<input type="range" class="cq-slider" data-cq="cut" min="0" max="'
          + (cuts.levels.length - 1) + '" step="1" value="' + cutAt
          + '" aria-label="the lightness the cut is taken at"'
          + ' title="Slide the cut up and down through the shape. Every one '
          + 'of these was worked out when the page was saved, so it moves as '
          + 'fast as you can drag it and needs nothing from the internet.">'
          + '<span class="cq-num" data-cq="cut-at">L* '
          + Math.round(cuts.levels[cutAt]) + '</span>'
          + button("cut-up", "+", "Take the cut higher — nearer white. Worth "
            + "going right to the top: near the paper white almost every "
            + "paper narrows to a small patch, and which of them keeps the "
            + "most colour up there is what decides whether a pale sky comes "
            + "out flat."));
  if (on("play", true))
    head += button("play", "Pause", "Stop the movement, or start it again. "
      + "You can always drag the shape yourself, moving or not.");
  // A MINUS AND A PLUS EITHER SIDE OF WHAT THEY CHANGE, wrapped together.
  // With speed and zoom both in the strip and every gap the same width, the
  // row read "speed 6 + − zoom +" -- and the plus for the speed sat next to
  // the minus for the zoom with nothing to say which belonged to which. The
  // wrapper makes the space between two groups twice the space inside one,
  // which is the whole fix: no dividers, no extra furniture, just grouping.
  function group(inner) {
    return '<span class="cq-grp">' + inner + '</span>';
  }
  if (on("speed", true) && !on("speed_each", false))
    head += group(button("slower", "&minus;", "Turn more slowly.")
          + '<span data-cq="speed">speed ' + both + '</span>'
          + button("faster", "+", "Turn more quickly."));
  // ZOOM SITS IN THE OPEN, not behind more…, because on a phone it is the
  // one thing a reader cannot do any other way. A pinch works on this page
  // now, but nobody is told that, and a pinch is also the gesture people try
  // once and give up on.
  if (on("zoom", true))
    head += group(button("out", "&minus;", "Zoom out — see more of it, "
            + "smaller.")
          + '<span data-cq="zoomed">zoom</span>'
          + button("in", "+", "Zoom in — get closer, and see less of it. "
            + "On a phone or a tablet you can also pinch with two fingers."));
  if (on("reset", true))
    head += button("home", "reset view", "Put the shape back the way the page "
      + "opened. Only your own turning, zooming and moving is undone — "
      + "nothing is closed and no figure changes.");
  // ---------------------------------------------------------------- shapes
  // WHAT CAN BE OFFERED FOR A SHAPE depends on what that shape is made of. A
  // wire cage has no surface to draw wires over; a cross-section has no wires
  // at all but can be an outline instead of a filled area; and a mesh whose
  // colour IS the answer is never offered in grey. Each row is built from
  // what its own shape can actually do, so no row anywhere carries a button
  // that would do nothing.
  function canWire(g) { return on("wires", true) && (g.mesh || g.fill); }
  function canGrey(g) { return on("grey", true) && g.plain; }
  function canFade(g) { return on("opacity", true) && !!g; }
  var HAS_SHAPES = shapes.some(function (g) {
    return canFade(g) || canWire(g) || canGrey(g);
  });

  // ------------------------------------------------------ where to stand
  // The tooltips name the picture's OWN axes, read off the drawing rather
  // than assumed, because these pages are drawn in two quite different kinds
  // of space: a* b* L* for a measured colour gamut and Cyan/Magenta/Yellow
  // percentages for a chart in ink amounts. A tooltip that says "lightness"
  // over a picture of ink amounts is simply wrong.
  function axisNames() {
    var out = null;
    (settings.ids || []).some(function (id) {
      var gd = document.getElementById(id);
      var sc = gd && gd._fullLayout && gd._fullLayout.scene;
      if (!sc) return false;
      function nm(ax) {
        var t = ax && ax.title;
        t = (t && (t.text !== undefined ? t.text : t)) || "";
        // "a*  (chroma →)" is the drawn label; the axis is called a*.
        return String(t).split(/\\s{2,}/)[0].trim();
      }
      var got = {x: nm(sc.xaxis), y: nm(sc.yaxis), z: nm(sc.zaxis)};
      if (got.x || got.y || got.z) { out = got; return true; }
      return false;
    });
    return out;
  }
  var AX = flat ? null : axisNames();
  function named(which, fallback) {
    return (AX && AX[which]) ? ("the " + AX[which] + " axis") : fallback;
  }
  var VIEWS = [
    ["above", "above",
     "Look straight down at it from above, along " + named("z", "the upright axis")
     + ". The height goes out of the picture and you see the spread across "
     + named("x", "the two flat axes").replace("the ", "") + " and "
     + named("y", "").replace("the ", "") + " — which is the same direction a "
     + "cross-section is drawn in, so the two pictures can be read together."],
    ["front", "front",
     "Stand square in front of it. Height on the screen is "
     + named("z", "the upright axis") + ", so this is the view for judging "
     + "how far up and down the shape reaches."],
    ["side", "side",
     "Step round ninety degrees and look at it from the side. Worth pressing "
     + "straight after “front”: two square-on views at right angles say more "
     + "about a shape than any single angle can."],
    ["angle", "angle",
     "Back to a three-quarter view, which is the one that reads as a solid "
     + "object rather than a flat outline. This is where most of these "
     + "pictures open."]
  ];
  function canStand() { return on("views", true) && !flat; }

  // ------------------------------------------------------- the page itself
  // ASKED OF THE BROWSER, NOT ASSUMED OF IT. Full screen for an ordinary
  // element does not exist on an iPhone at all — Safari there offers it for
  // video and nothing else — so on the very device this panel matters most,
  // a full-screen button would be a button that does nothing. Built only
  // where it works, missing everywhere else.
  //
  // It is the whole page that goes full screen rather than the picture on its
  // own, and that is deliberate: full-screening the picture alone would take
  // this strip off the screen with it, leaving somebody on a tablet with no
  // visible way back out of it.
  function canFull() {
    return on("fullscreen", true) && !!document.fullscreenEnabled
      && !!document.documentElement.requestFullscreen;
  }
  function canSave() {
    return on("picture", true) && !!(window.Plotly && window.Plotly.downloadImage);
  }

  var HAS_PANEL = on("lr", true) || on("ud", true) || on("speed_each", false)
    || swings("turn") || swings("tilt")
    || on("move", true) || on("grid", false) || on("labels", false)
    || on("key", false) || on("appearance", false)
    || HAS_SHAPES || canStand() || canFull() || canSave()
    || (agreed && on("agree", true))
    || (on("notes", true) && !!document.querySelector(".cq-notes"));
  if (HAS_PANEL)
    head += button("more", "more…", "Everything else you can change about "
      + "this picture: which way it moves and how fast, where you look at it "
      + "from, how solid each shape is drawn and whether it keeps its colour, "
      + "whether the box and its lettering are there, and whether the page is "
      + "light or dark.");
  bar.innerHTML = head;

  // ============================================================ the panel
  var moves = "";
  if (on("lr", true))
    moves += '<div class="cq-row"><span>left &amp; right</span>'
      + '<span class="cq-ctl">'
      + button("lr", "on", "Turn the shape left and right, or stop it turning "
        + "that way. This is the movement most people mean by “spin it”.")
      + (on("speed_each", false)
         ? button("turn-slower", "&minus;", "Turn left and right more slowly.")
           + '<span class="cq-num" data-cq="turn-speed">'
           + Math.round(speeds.turn) + '</span>'
           + button("turn-faster", "+", "Turn left and right more quickly.")
         : "")
      + (swings("turn")
         ? group(button("turn-narrower", "&minus;", "Swing a shorter way to "
             + "each side. A narrow swing keeps the shape almost facing you, "
             + "which is what you want when you have picked an angle and only "
             + "want enough movement to tell a dent from a shadow.")
           + '<span class="cq-num" data-cq="turn-range">'
           + sweepReads("turn") + '</span>'
           + button("turn-wider", "+", "Swing further to each side, up to "
             + "half a turn — and one press further than that sets it going "
             + "ALL THE WAY ROUND, turning steadily in one direction instead "
             + "of coming back. The reading says “round” when it is doing "
             + "that. A swing keeps the shape near the angle you picked; all "
             + "the way round is the one to leave running while you look at "
             + "something else. Press the minus to come back to a swing."))
         : "")
      + '</span></div>';
  if (on("ud", true))
    moves += '<div class="cq-row"><span>up &amp; down</span>'
      + '<span class="cq-ctl">'
      + button("ud", "on", "Tip the shape towards you and away again, or stop "
        + "it tipping. A little of this alongside the turning is what shows "
        + "the dents in a surface.")
      + (on("speed_each", false)
         ? button("tilt-slower", "&minus;", "Tip more slowly.")
           + '<span class="cq-num" data-cq="tilt-speed">'
           + Math.round(speeds.tilt) + '</span>'
           + button("tilt-faster", "+", "Tip more quickly.")
         : "")
      + (swings("tilt")
         ? group(button("tilt-narrower", "&minus;", "Tip a shorter way. A "
             + "small tip is enough to show that a surface is dented rather "
             + "than smooth, and it is much easier to watch than a large one.")
           + '<span class="cq-num" data-cq="tilt-range">'
           + sweepReads("tilt") + '</span>'
           + button("tilt-wider", "+", "Tip further, until you are looking "
             + "down onto the lid of the shape and then up at its floor — "
             + "which is the only way to see how flat the top is near white. "
             + "One press past the furthest tip sends it right over the top "
             + "and round, reading “round”, which is worth seeing once and "
             + "is not restful to leave running."))
         : "")
      + '</span></div>';
  section("how it moves", moves);

  var looking = "";
  if (on("move", true))
    looking += '<div class="cq-row"><span>move it</span>'
      + '<span class="cq-ctl">'
      + button("left", "&larr;", "Move the picture to the left, to bring "
        + "something on the right-hand side into the middle.")
      + button("right", "&rarr;", "Move the picture to the right, to bring "
        + "something on the left-hand side into the middle.")
      + button("up", "&uarr;", "Move the picture up.")
      + button("down", "&darr;", "Move the picture down. Together with the "
        + "zoom this lets you go and look at one corner of the shape closely. "
        + "On a phone or a tablet you can also drag with two fingers, and "
        + "“reset view” always brings the whole thing back.")
      + '</span></div>';
  if (canStand()) {
    var stand = "";
    VIEWS.forEach(function (v) { stand += button("look-" + v[0], v[1], v[2]); });
    looking += '<div class="cq-row"><span>look from</span>'
      + '<span class="cq-ctl">' + stand + '</span></div>';
  }
  section("where you look from", looking);

  var each = "";
  // WHERE THEY AGREE, ABOVE THE SHAPES IT ACTS ON. It belongs in this group
  // rather than with the grid and the lettering, because it is about the
  // shapes themselves -- and it goes first because it is the one control
  // here that acts on all of them at once, so reading down the group runs
  // from "all of them" to "this one".
  if (agreed && on("agree", true)) {
    each += '<div class="cq-row"><span>where they agree</span>'
      + '<span class="cq-ctl">'
      + group(button("agree-less", "&minus;",
          "Fade away the part that every shape reaches, so that what is left "
          + "standing is only where they differ. Two papers drawn over each "
          + "other are mostly the same paper: the part they share is the bulk "
          + "of both, it is drawn twice, and it sits in front of the very "
          + "thing you are comparing them to see.")
        + '<span class="cq-num" data-cq="agree-at">100%</span>'
        + button("agree-more", "+",
          "Bring the shared part back. At the top nothing is changed at all "
          + "and the picture is exactly the one that was saved. If a whole "
          + "shape faded away on the way down, that is the answer and not a "
          + "fault: it means that shape sits completely inside the others and "
          + "differs from them nowhere."))
      + '</span></div>';
    // AND THE OTHER WAY ROUND. The two are not the same control read
    // backwards: fading the shared part asks "where do these differ?", which
    // is what you ask when choosing between two papers, and fading the
    // differences asks "what can I print on both of them?", which is what
    // you ask when the same picture has to go out on both.
    each += '<div class="cq-row"><span>where they differ</span>'
      + '<span class="cq-ctl">'
      + group(button("differ-less", "&minus;",
          "Fade away the parts that only one shape reaches, leaving the part "
          + "they all have in common. That shared part is what you can print "
          + "on either of them and get the same colour, which is the question "
          + "to ask when one picture has to go out on both.")
        + '<span class="cq-num" data-cq="differ-at">100%</span>'
        + button("differ-more", "+",
          "Bring the differences back. Both of these sit at the top when the "
          + "page opens, and there they change nothing at all."))
      + '</span></div>';
  }
  shapes.forEach(function (g, n) {
    var st = dressed[g.key], ctl = "";
    if (canFade(g))
      ctl += group(button("shape-fainter-" + n, "&minus;",
          "Make " + g.label + " fainter, so whatever is behind it shows "
          + "through. This is the control for the oldest problem a picture of "
          + "two gamuts has: the one in front hides the one behind, and no "
          + "amount of turning fixes it.")
        + '<span class="cq-num" data-cq="shape-lit-' + n + '">'
        + Math.round(st.opacity * 100) + '%</span>'
        + button("shape-stronger-" + n, "+",
          "Make " + g.label + " more solid. At full strength a surface hides "
          + "everything behind it, which is exactly what you want when it is "
          + "the shape itself you are studying rather than the comparison. "
          + "It is also the cleanest: a see-through surface shows flat "
          + "patches of its own triangles at some angles, because the "
          + "browser blends them in the order it draws them rather than by "
          + "which is nearer. That is the drawing, not your measurement — "
          + "it is worst at a three-quarter view and least from straight "
          + "above, and going solid removes it altogether."));
    if (canWire(g))
      ctl += button("shape-wires-" + n, g.mesh ? "wires" : "filled",
        g.mesh
          ? ("Draw a net of fine lines over " + g.label + ", in the colours "
             + "the surface itself is painted in. Every line runs between two "
             + "measured points, so the net shows you where the chart sampled "
             + "densely and where the shape between two readings is the "
             + "drawing filling in rather than anything anybody measured — a "
             + "wide, empty patch of net is a part of the surface nobody "
             + "measured directly.\\n\\n"
             + "Turn the strength down with − at the same time and you are "
             + "left with the cage alone, which is the clearest way to show "
             + "one shape sitting inside another. Press grey and the net goes "
             + "grey with the shape. Nothing is added to or taken from the "
             + "measurement either way.")
          : ("Fill " + g.label + " in, or leave only its outline. Two filled "
             + "cross-sections lying over each other are hard to read however "
             + "faint they are; two outlines never are. Nothing is added or "
             + "removed from the measurement either way — only the colouring "
             + "in."));
    if (canGrey(g))
      ctl += button("shape-grey-" + n, "grey",
        "Take the colour out of " + g.label + " and draw it in grey. It "
        + "keeps its light and dark exactly — a grey here is the true "
        + "brightness of the colour it replaces, not an average of the three "
        + "numbers — so the shape stays every bit as readable and simply "
        + "stops competing for attention. The usual reason to want it: two "
        + "shapes both painted in their own colours make a picture nobody "
        + "can untangle, and one of them in grey makes the other obvious. "
        + "Press it again and the colour comes straight back; nothing about "
        + "the measurement is touched.");
    if (!ctl) return;
    each += '<div class="cq-row cq-shape"><span class="cq-name" title="'
      + safe(g.label) + '">' + safe(g.label) + '</span>'
      + '<span class="cq-ctl">' + ctl + '</span></div>';
  });
  // A LINE THAT APPEARS ONLY WHEN IT APPLIES.
  //
  // A see-through surface shows flat, hard-edged patches of its own triangles
  // at some angles -- the browser blends them in the order it draws them
  // rather than by which is nearer. Nothing is missing, and the outline is
  // identical, but it reads as a slice taken out of the shape.
  //
  // It was explained in the tooltip on the button that causes it, which is no
  // help at all to somebody looking at the picture wondering what they did:
  // reported as "it looks sliced" and then, plainly, "I don't know which
  // control does it". So the page says so itself, in the group the control
  // lives in, and only while a shape is actually see-through -- a standing
  // note about a thing that is not happening is just more to read.
  if (each)
    each += '<div class="cq-row cq-back"><span>changed your mind?</span>'
      + '<span class="cq-ctl">'
      + button("shapes-back", "as saved", "Put every shape back to the way "
        + "this page was saved — its strength, its wires and its colour. "
        + "Only how they are drawn is put back: nothing you have turned, "
        + "zoomed or hidden is disturbed.")
      + '</span></div>';
  section("each shape", each, true,
    each ? '<div class="cq-aside" data-cq="facets" hidden>'
           + 'a see-through shape shows its own facets at some angles — '
           + 'nothing is missing. Press + to make it solid, or “above”.'
           + '</div>' : "");

  var drawn = "";
  // ONLY IF THERE ARE ANY. Offering to hide something that is not on the
  // page is the clearest way there is to make a reader think it is broken.
  var HAS_NOTES = !!document.querySelector(".cq-notes");
  if (on("notes", true) && HAS_NOTES)
    drawn += row("notes", "the numbers",
      "Show or hide the written-out figures under the picture — what each "
      + "shape holds, how much of one fits inside the other, and any drift "
      + "between two readings. On a small screen they can be taller than the "
      + "screen itself, so putting them away gives the whole window back to "
      + "the shape. Nothing is lost: press it again and they come back.");
  if (on("grid", false))
    drawn += row("grid", "walls &amp; grid",
      "Draw the box around the shape, with its ruled walls, or take it away. "
      + "The walls are what let you judge where a bulge actually sits; "
      + "without them you get the shape on its own, which is the tidier "
      + "picture to drop into a document.");
  if (on("labels", false))
    drawn += row("labels", "lettering",
      "Show or hide the numbers and the axis names around the picture. "
      + "Hiding them leaves the shape and nothing else — useful when the "
      + "picture is going beside text that already explains it, and when you "
      + "want nobody reading numbers off a small screenshot.");
  if (on("key", false))
    drawn += row("key", "the names",
      "Show or hide the list of names under the picture. Each name is also a "
      + "switch: click one to hide that shape and click it again to bring it "
      + "back, or double-click to see that one on its own.");
  section("what is drawn", drawn);

  var pageRows = "";
  if (on("appearance", false))
    pageRows += '<div class="cq-row"><span>page colours</span>'
      + '<span class="cq-ctl">'
      + button("appearance", schemeName(mode),
        "Press to move through the ways this page can be coloured. NOT ONE "
        + "MEASURED COLOUR CHANGES — only the paper behind the shape, the "
        + "walls of the box around it, the grid on them and the writing. The "
        + "shape you are reading is the same shape whichever you pick.\\n\\n"
        + "dark and light are the two the window itself uses, and the page "
        + "opens on whichever it was saved in. none takes the background "
        + "away completely, so the shape floats on whatever the page is sitting "
        + "in — that is the one for dropping a picture into a document, a "
        + "slide or a forum post. slate is a neutral grey: a gamut on black "
        + "looks brighter than it really is and one on white looks duller, "
        + "and halfway is the fairest ground to judge a colour against. ink "
        + "is plain black and white, for printing the page out or putting it "
        + "on a projector, where a near-black goes to mud and a warm white "
        + "goes yellow.")
      + '</span></div>';
  if (canFull())
    pageRows += '<div class="cq-row"><span>full screen</span>'
      + '<span class="cq-ctl">'
      + button("full", "on", "Give the picture the whole screen, with the "
        + "browser’s own bars out of the way, and press it again to come "
        + "back. The controls come with it, so there is always a visible way "
        + "out — the Escape key works too.")
      + '</span></div>';
  if (canSave())
    pageRows += '<div class="cq-row"><span>save a picture</span>'
      + '<span class="cq-ctl">'
      + button("shot", "PNG", "Save what you are looking at, exactly as it "
        + "stands, as an ordinary picture file — the angle you turned it to, "
        + "the shapes you faded, everything. It lands in your downloads at "
        + "twice the size it is drawn on screen, so it is worth putting in a "
        + "document. This page is not sent anywhere to do it: the picture is "
        + "made by your own browser, from the numbers already inside the "
        + "page.")
      + '</span></div>';
  section("the page itself", pageRows);
  panel.innerHTML = body;

  var css = document.createElement("style");
  // IN THE FLOW, NOT FLOATING OVER THE PICTURE. It used to be fixed to the
  // bottom of the window, which is exactly the band the drawing library puts
  // the key in -- so the strip sat on top of the names, and those names are
  // switches a reader is told to click. Measured at five viewports it covered
  // two rows on a desktop and all four on a phone.
  //
  // Sitting under the picture instead, whatever height it needs is reserved
  // for it automatically -- one line or two, at any width -- so it cannot
  // cover anything at any size.
  css.id = "cq-spin-css";
  function paint() {
    css.textContent =
      // TWICE THE SPACE BETWEEN GROUPS AS INSIDE ONE. See `group()` above:
      // this pair of numbers is what tells a reader which minus goes with
      // which label, and it is the only thing that does.
      ".cq-grp{display:inline-flex;gap:6px;align-items:center}"
      // THE STRIP AND THE PANEL PAINT ABOVE THE PICTURE, ALWAYS.
      //
      // Opening the panel takes about seventy pixels off the picture, and the
      // drawing library only learns that when it is told to re-measure. For
      // the frame or two in between, the canvas is still its old height and
      // spills over the strip -- so the Play button and "less…" are sliced
      // in half by the panel's top edge, and a moment later it settles.
      // Reported exactly that way: "here, and then a second later it is back
      // to good".
      //
      // Telling it to re-measure sooner only shortens the flicker; stacking
      // the controls above the picture removes it whatever the timing, and
      // clipping the picture to its own box stops the canvas escaping in the
      // first place. Two rules, no reliance on when a frame lands.
      + ".cq-spin-bar,.cq-spin-panel{position:relative;z-index:2}"
      + "body > div:first-of-type{overflow:hidden}"
      // THE TEXT GROWS WITH THE WINDOW, between a floor and a ceiling.
      //
      // Pinned at 12px it was right on a laptop and looked lost on anything
      // bigger: on a 1900-pixel window the picture fills the screen and the
      // controls under it are the same twelve pixels they were at 1280, which
      // reads as tiny. Reported twice, once on a phone (a different cause --
      // see the viewport tag) and once on a wide desktop window, which is
      // this.
      //
      // clamp() keeps 12px as the floor, so nothing measured for a narrow
      // screen moves, and stops at 15px so a very wide window does not end up
      // with a row of enormous buttons. The padding is in em, so the buttons
      // grow with the text rather than staying the same size around it.
      + ".cq-spin-bar{flex:0 0 auto;display:flex;gap:18px;align-items:center;"
      + "justify-content:center;flex-wrap:wrap;margin:0 auto;max-width:100%;"
      + "font:clamp(12px,0.85vw,15px)/1 -apple-system,BlinkMacSystemFont,"
      + "'Segoe UI',sans-serif;"
      + "padding:8px 10px;color:" + ink + ";background:" + paper + ";"
      + "border-top:1px solid " + tint(ink, 0.14) + "}"
      + ".cq-spin-bar button{font:inherit;cursor:pointer;border-radius:999px;"
      + "padding:0.45em 0.85em;border:1px solid " + tint(ink, 0.45) + ";"
      + "background:transparent;color:inherit}"
      + ".cq-spin-bar button:hover{border-color:" + ink + "}"
      // A KEYBOARD MUST BE ABLE TO SEE WHERE IT IS. The browser's own focus
      // ring is drawn in its own colour and disappears against a dark page.
      + ".cq-spin-bar button:focus-visible,.cq-spin-panel button:focus-visible"
      + "{outline:2px solid " + ink + ";outline-offset:2px}"
      + ".cq-spin-bar button[aria-pressed=false]{opacity:.55}"
      + ".cq-spin-bar span{opacity:.85;min-width:54px;text-align:center}"
      // THE SLIDER IS THE WIDEST THING IN THE STRIP and the only one that
      // wants to grow, so it is allowed to -- down to 110px on a phone,
      // where the strip wraps around it, and capped on a desktop because a
      // 700px slider for 45 positions is absurd to aim with.
      + ".cq-spin-bar .cq-slider{flex:1 1 130px;max-width:230px;min-width:110px;"
      + "margin:0 2px;accent-color:" + ink + ";height:22px;cursor:pointer}"
      + ".cq-spin-bar .cq-slider:focus-visible{outline:2px solid " + ink + ";"
      + "outline-offset:2px}"
      + ".cq-spin-bar .cq-num{min-width:46px;text-align:center;"
      + "font-variant-numeric:tabular-nums}"
      + ".cq-spin-panel{flex:0 0 auto;color:" + ink + ";background:" + paper
      + ";border-top:1px solid " + tint(ink, 0.14) + ";padding:10px 14px 12px;"
      + "font:clamp(12px,0.85vw,15px)/1.4 -apple-system,BlinkMacSystemFont,"
      + "'Segoe UI',sans-serif;"
      // The panel widens with the text too, or fifteen-pixel words are laid
      // into columns measured for twelve-pixel ones.
      + "display:block;max-width:min(1120px,94vw);margin:0 auto;width:100%;"
      + "box-sizing:border-box}"
      // A HEADING AND ITS OWN LIST PER GROUP. The lists still flow into as
      // many columns as the width allows, so a desktop shows a group in one
      // line and a phone shows it stacked -- but a group never mixes with
      // the one after it, which is the entire reason for having them.
      + ".cq-spin-panel .cq-sect{margin:0 0 9px}"
      + ".cq-spin-panel .cq-sect:last-child{margin-bottom:0}"
      + ".cq-spin-panel h4{font:600 10px/1 -apple-system,BlinkMacSystemFont,"
      + "'Segoe UI',sans-serif;letter-spacing:.09em;text-transform:uppercase;"
      + "margin:0 0 5px;padding:0 0 4px;opacity:.55;"
      + "border-bottom:1px solid " + tint(ink, 0.12) + "}"
      + ".cq-spin-panel .cq-rows{display:grid;gap:7px 22px;"
      + "grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}"
      // THE SHAPES NEED MORE ROOM THAN A SWITCH DOES. Their labels are the
      // names in the key and those run to "a chart of 480 patches — a skin
      // over the patches"; squeezed into a 230px column beside four buttons
      // there is nothing left of the name but the first word, and the first
      // word is the same for every row on the page. A wider column of their
      // own, still allowed to sit two abreast once there is room for two.
      + ".cq-spin-panel .cq-wide .cq-rows{"
      + "grid-template-columns:repeat(auto-fit,minmax(330px,1fr))}"
      + ".cq-spin-panel .cq-shape{flex-wrap:wrap}"
      + ".cq-spin-panel .cq-name{flex:1 1 150px;min-width:0;overflow:hidden;"
      + "text-overflow:ellipsis;white-space:nowrap}"
      + ".cq-spin-panel .cq-back span:first-child{opacity:.6}"
      // The note runs the width of the group and reads as an aside, not as a
      // row with a missing control on the right-hand side.
      + ".cq-spin-panel .cq-aside{opacity:.55;margin:6px 0 0;"
      + "font-size:.92em;line-height:1.35;display:block}"
      + ".cq-spin-panel .cq-aside[hidden]{display:none}"
      + ".cq-spin-panel .cq-row{display:flex;align-items:center;"
      + "justify-content:space-between;gap:10px}"
      + ".cq-spin-panel .cq-ctl{display:flex;gap:5px;align-items:center;"
      + "flex-wrap:wrap;justify-content:flex-end}"
      + ".cq-spin-panel span{opacity:.9}"
      // A NUMBER BETWEEN TWO BUTTONS MUST NOT MOVE THEM.
      //
      // "100%" is wider than "50%", and with the readout sitting between the
      // minus and the plus, every press that crossed a digit shoved both
      // buttons sideways -- so the plus walked out from under the finger that
      // was pressing it. Reported from the real page, and the same fault the
      // strip along the top was given a minimum width for long ago; the panel
      // simply never inherited it.
      //
      // Two parts to the fix, and both are needed: a floor on the width so
      // the widest reading still fits, and tabular figures so that every
      // digit is the same width as every other -- without that, "11%" and
      // "88%" are different widths in most interface fonts and the buttons
      // twitch inside the space rather than jumping out of it.
      + ".cq-spin-panel .cq-num{display:inline-block;min-width:40px;"
      + "text-align:center;font-variant-numeric:tabular-nums}"
      + ".cq-spin-panel button{font:inherit;cursor:pointer;border-radius:999px;"
      + "padding:0.4em 0.8em;border:1px solid " + tint(ink, 0.45) + ";"
      + "background:transparent;color:inherit;min-width:34px}"
      + ".cq-spin-panel button[aria-pressed=false]{opacity:.5}"
      // CLOSED MEANS CLOSED.
      //
      // The panel is marked hidden the moment it is built and the button
      // reads "more…", and it was on screen the whole time regardless: a
      // rule written by the page ALWAYS beats the browser's own
      // [hidden]{display:none}, whatever its specificity, because author
      // styles outrank the browser's default styles by definition. So
      // "display:grid" two lines above quietly cancelled being hidden.
      //
      // Measured on a phone-sized window before this line existed: the panel
      // was 259px of an 844px screen, the picture was 78px, and 91% of what
      // the reader could see was controls. On every page since the panel was
      // introduced.
      //
      // It went unnoticed because the test that guarded it asked the element
      // whether it was hidden -- and it truthfully answered yes. Asking what
      // the browser actually DRAWS is the only question worth asking.
      + ".cq-spin-panel[hidden]{display:none}"

      // ================================================== THREE SHAPES OF IT
      //
      // The same controls, laid out for the screen they are actually on.
      // Everything above is written for the middle case and the two rules
      // below bend it at each end; nothing appears or disappears with the
      // width, because a control that is on a laptop and gone on a phone is
      // the most confusing thing a page can do to somebody comparing the two.
      //
      // A PHONE, or a narrow window (up to 520px). One column, because two
      // columns of 160px hold a label and no room for what it controls. A
      // row whose buttons will not fit beside its label puts them on the
      // next line instead of squeezing both, and the buttons are given a
      // bigger tap area -- 34px is close to the 44pt Apple asks for once the
      // gap between rows is counted, and these sit in pairs where hitting
      // the minus instead of the plus is an actual mistake.
      + "@media (max-width:520px){"
      + ".cq-spin-panel .cq-rows,.cq-spin-panel .cq-wide .cq-rows"
      + "{grid-template-columns:1fr;gap:9px 0}"
      + ".cq-spin-panel .cq-row{flex-wrap:wrap}"
      + ".cq-spin-panel .cq-ctl{justify-content:flex-start}"
      + ".cq-spin-panel button,.cq-spin-bar button"
      + "{min-height:34px;padding:7px 12px}"
      + "}"

      // A SHORT SCREEN -- a phone held sideways, or a browser window someone
      // has dragged down to a strip. There is 390px of height in a sideways
      // phone and an open panel is taller than that on its own, so without a
      // ceiling here the picture is pushed clean off the screen by its own
      // controls.
      //
      // WHY ONLY WHEN IT IS SHORT, and not always: a panel with its own
      // scrollbar inside a page that also scrolls means a reader whose thumb
      // lands on the panel scrolls the panel instead of the page, which on a
      // tall phone is a trap for no gain -- there the page has room and can
      // simply be longer. Nested scrolling is worth its cost only where the
      // alternative is losing the picture altogether. Scroll chaining is
      // deliberately left alone, so a thumb that reaches the end of the panel
      // carries on to the page rather than stopping dead.
      + "@media (max-height:560px){"
      + ".cq-spin-panel{max-height:46vh;overflow-y:auto}"
      + "}"

      // A TABLET, AND ANYTHING BIGGER, is left to the two grids above, and
      // that is a decision rather than an omission. A fixed three columns at
      // some chosen width was written here first and then measured against
      // what `auto-fit` was already doing: identical at every size tested,
      // and worse in one case -- a group of two rows given three fixed
      // columns leaves the third empty and squeezes both rows into
      // two-thirds of the width for nothing. Reflow that counts the rows it
      // actually has beats a breakpoint that guesses.
      //
      // What it settles on, measured at 320, 390, 500, 768, 844 and 1280:
      // one column up to 520px, up to two from there, up to three from about
      // 740px, and the shape rows two abreast from about 700px -- "up to",
      // because a group of two rows takes two columns and not three.;
  }
  paint();
  document.head.appendChild(css);
  // DIRECTLY UNDER THE PICTURE, not at the end of the page.
  //
  // Appended to the body it landed after the written-out numbers, which on a
  // page carrying them is several screens of text on a phone -- so the
  // controls for the picture sat below everything, and a reader who wanted to
  // pause the movement had to scroll away from the very thing they were
  // trying to pause. Put next to what it acts on, it is on screen whenever
  // the picture is, and the numbers follow underneath where they are read.
  var anchor = document.getElementById((settings.ids || [])[0]);
  while (anchor && anchor.parentNode && anchor.parentNode !== document.body)
    anchor = anchor.parentNode;
  if (anchor && anchor.parentNode === document.body) {
    anchor.parentNode.insertBefore(bar, anchor.nextSibling);
    bar.parentNode.insertBefore(panel, bar.nextSibling);
  } else {
    document.body.appendChild(bar);
    document.body.appendChild(panel);
  }

  // AND NOW TELL THE DRAWING LIBRARY THE PICTURE IS SHORTER. A plot measures
  // its box once, when it is created, and only looks again on a window
  // resize. Adding this strip takes about seventy pixels off the bottom of
  // that box -- so the key went on being drawn where it would have gone in
  // the taller one, which put it straight back over the strip.
  function fit() {
    if (!window.Plotly) return;
    (settings.ids || []).forEach(function (id) {
      var gd = document.getElementById(id);
      if (gd) window.Plotly.Plots.resize(gd);
    });
  }
  fit();
  // AFTER THE BROWSER HAS LAID OUT, not merely soon. requestAnimationFrame
  // runs once the new heights are settled, which is the earliest moment the
  // picture can be measured correctly; the timer after it is the belt to
  // that pair of braces.
  if (window.requestAnimationFrame)
    window.requestAnimationFrame(function () { fit(); });
  window.setTimeout(fit, 60);
  window.addEventListener("resize", fit);
  // Turning a phone sideways is a resize the event above can miss.
  window.addEventListener("orientationchange", function () {
    window.setTimeout(fit, 120);
  });

  // A PAGE SAVED STILL HAS NOTHING TO TURN. Pressing Play on one has to do
  // something, so it falls back to turning all the way round.
  function wake() {
    if ((!turn.mode || turn.mode === "off") &&
        (!tilt.mode || tilt.mode === "off")) {
      // Whatever the reader last chose for the left-and-right direction, or
      // all the way round if they have never chosen anything. It used to set
      // a range here as well, which nothing reads any more: how far each
      // direction swings is kept in `ranges` now, so that the sweep buttons
      // and the engine cannot hold two different answers.
      turn.mode = chosen.turn;
    }
  }
  // QUOTED, ALWAYS. These names now carry a number on the end ("shape-lit-2")
  // and an unquoted attribute selector is a CSS identifier -- one character
  // outside what an identifier may hold and querySelector throws rather than
  // returning nothing, which takes the whole strip down with it.
  function find(what) {
    return bar.querySelector('[data-cq="' + what + '"]')
        || panel.querySelector('[data-cq="' + what + '"]');
  }
  function press(what, state) {
    var el = find(what);
    if (el) el.setAttribute("aria-pressed", state ? "true" : "false");
  }
  function say(what, text) {
    var el = find(what);
    if (el) el.textContent = text;
  }
  function applyPicture() {
    // THE NUMBERS ARE PART OF THE PAGE, NOT OF THE DRAWING, so they are shown
    // and hidden here rather than through the drawing library. Hiding them
    // shortens the page, which is the whole point on a phone.
    var written = document.querySelector(".cq-notes");
    if (written) {
      written.style.display = picture.notes ? "" : "none";
      press("notes", picture.notes);
      fit();
    }
    // A FLAT CUT HAS PLAIN AXES, NOT A SCENE, and the paths differ by that
    // one word. Asked to change a setting that is not there, the drawing
    // library complains into the console and changes nothing -- so the
    // switch would sit there looking live and do nothing at all.
    if (flat) {
      relayout({"xaxis.showgrid": picture.grid,
                "yaxis.showgrid": picture.grid,
                "xaxis.zeroline": picture.grid,
                "yaxis.zeroline": picture.grid,
                "xaxis.showticklabels": picture.labels,
                "yaxis.showticklabels": picture.labels,
                "xaxis.title.font.size": picture.labels ? 12 : 1,
                "yaxis.title.font.size": picture.labels ? 12 : 1,
                "showlegend": picture.key});
      press("grid", picture.grid);
      press("labels", picture.labels);
      press("key", picture.key);
      return;
    }
    relayout({"scene.xaxis.showgrid": picture.grid,
              "scene.yaxis.showgrid": picture.grid,
              "scene.zaxis.showgrid": picture.grid,
              "scene.xaxis.showbackground": picture.grid,
              "scene.yaxis.showbackground": picture.grid,
              "scene.zaxis.showbackground": picture.grid,
              "scene.xaxis.showticklabels": picture.labels,
              "scene.yaxis.showticklabels": picture.labels,
              "scene.zaxis.showticklabels": picture.labels,
              "scene.xaxis.title.font.size": picture.labels ? 12 : 1,
              "scene.yaxis.title.font.size": picture.labels ? 12 : 1,
              "scene.zaxis.title.font.size": picture.labels ? 12 : 1,
              "showlegend": picture.key});
    press("grid", picture.grid);
    press("labels", picture.labels);
    press("key", picture.key);
  }
  // THE LIST TO MOVE THROUGH, and what each one is called on the button.
  // A page saved before this carried two colourings and no list; it still
  // works, and simply moves between the two it has.
  var schemes = (settings.schemes && settings.schemes.length)
    ? settings.schemes.slice()
    : (palettes ? Object.keys(palettes) : [mode]);
  function schemeName(which) { return which; }
  function nextScheme() {
    var at = schemes.indexOf(mode);
    return schemes[(at < 0 ? 0 : at + 1) % schemes.length];
  }

  function applyMode() {
    if (!palettes) return;
    var p = palettes[mode] || palettes.dark;
    if (!p) return;
    ink = p.text; paper = p.page;
    paint();
    document.documentElement.style.background = p.page;
    document.body.style.background = p.page;
    if (flat) {
      relayout({"paper_bgcolor": p.page, "plot_bgcolor": p.plot,
                "font.color": p.text,
                "xaxis.gridcolor": p.grid, "yaxis.gridcolor": p.grid,
                "xaxis.zerolinecolor": p.grid, "yaxis.zerolinecolor": p.grid,
                "xaxis.color": p.caption, "yaxis.color": p.caption,
                "legend.font.color": p.text, "title.font.color": p.caption});
      say("appearance", schemeName(mode));
      return;
    }
    relayout({"paper_bgcolor": p.page, "plot_bgcolor": p.plot,
              "font.color": p.text,
              "scene.xaxis.backgroundcolor": p.plot,
              "scene.yaxis.backgroundcolor": p.plot,
              "scene.zaxis.backgroundcolor": p.plot,
              "scene.xaxis.gridcolor": p.grid,
              "scene.yaxis.gridcolor": p.grid,
              "scene.zaxis.gridcolor": p.grid,
              "scene.xaxis.color": p.caption,
              "scene.yaxis.color": p.caption,
              "scene.zaxis.color": p.caption,
              "legend.font.color": p.text,
              "title.font.color": p.caption});
    say("appearance", schemeName(mode));
  }

  function push() {
    // NOTHING TURNS ON A FLAT CUT, whatever a stored choice from some other
    // page or an older version of this one might say.
    if (flat) running = false;
    window.cqSpin.set(
      {on: running,
       turn: {mode: turn.mode, range: ranges.turn, speed: speedFor("turn")},
       tilt: {mode: tilt.mode, range: ranges.tilt, speed: speedFor("tilt")}});
    say("speed", "speed " + both);
    say("turn-speed", String(Math.round(speeds.turn)));
    say("tilt-speed", String(Math.round(speeds.tilt)));
    say("turn-range", sweepReads("turn"));
    say("tilt-range", sweepReads("tilt"));
    say("play", running ? "Pause" : "Play");
    press("lr", turn.mode && turn.mode !== "off");
    press("ud", tilt.mode && tilt.mode !== "off");
    // FROM THE ONE PLACE EVERY HANDLER ALREADY PASSES THROUGH. Hung off the
    // plural tellShapes() instead, it was missed by every per-shape press --
    // which calls the singular one -- so fading a shape to nothing left the
    // button still claiming the page was as it was saved.
    tellMore();
    if (on("remember", true)) remember();
  }

  function step(which, by) {
    speeds[which] = Math.min(12, Math.max(1, Math.round(speeds[which] + by)));
  }
  //: Ten degrees a press: fine enough that nobody overshoots the sweep they
  //: wanted, coarse enough that one press is plainly something.
  function sweep(which, by) {
    var limit = SWEEP[which];
    if (chosen[which] === "round") {
      // Coming back from a full turn lands on the widest swing there is,
      // which is the step it left from.
      if (by < 0) { chosen[which] = "swing"; ranges[which] = limit[1]; }
    } else if (Math.round(ranges[which] + by) > limit[1]) {
      chosen[which] = "round";
    } else {
      ranges[which] = Math.max(limit[0], Math.round(ranges[which] + by));
    }
    // A DIRECTION THAT IS RUNNING CHANGES UNDER THE READER'S HAND. One that
    // is switched off keeps the choice for when it is switched back on --
    // the same promise the on/off button already makes about the movement
    // the page was saved with.
    var axis = (which === "turn") ? turn : tilt;
    if (axis.mode && axis.mode !== "off") axis.mode = chosen[which];
  }

  //: How faint a shape may be made, and how solid. Not zero at the faint end:
  //: a shape at nothing is a shape that has vanished, and the reader who did
  //: it by holding the minus button has no way of telling that from a page
  //: that failed to draw. Hiding a shape outright is what the names in the
  //: key are for, and that at least says so plainly.
  //: THE STEPS A STRENGTH MOVES IN, and they are not even on purpose.
  //:
  //: Ten equal steps of a tenth sound right and do not look it: taking a
  //: surface from full to nine-tenths is barely visible, while the last step
  //: from a tenth to nothing removes almost everything that was left. So a
  //: reader pressing steadily sees nothing happen, nothing happen, nothing
  //: happen -- and then the shape is gone. Reported exactly that way: "it
  //: seemed it was fully there and then immediately completely gone".
  //:
  //: These are spaced so each press changes what you SEE by about as much as
  //: the last one, which means small steps at the faint end where the eye is
  //: most sensitive to them.
  //:
  //: IT DOES REACH NOTHING, and that was asked for: hiding the shared part
  //: outright is a thing somebody wants, and refusing it because a vanished
  //: shape MIGHT be mistaken for a fault is solving the wrong half of the
  //: problem. The right half is telling them -- which the button that opens
  //: this panel now does: a line under "each shape" naming what a see-through
  //: surface does to the picture and what to press about it, shown only while
  //: one actually is. An explanation beats a prohibition -- and a SPECIFIC
  //: explanation beats a vague one, which is why a label merely announcing
  //: that something had changed was tried here and taken out again.
  //:
  //: The rungs near the bottom are close together so that the last step
  //: before nothing is a small one rather than a cliff.
  var LADDER = [0, 0.05, 0.08, 0.11, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8,
                0.9, 1];
  // THE RUNGS, PLUS WHEREVER THIS PARTICULAR SHAPE STARTED.
  //
  // A page saved with two papers draws them at 0.55, a chart's skin at 0.30 --
  // values that are not on the ladder. Stepping off one of those snaps to the
  // nearest rung, and stepping back lands on that rung rather than where it
  // began: 0.55 went down to 0.4 and back to 0.5, so pressing plus as many
  // times as minus did NOT put the shape back. Caught by the check that
  // presses both and compares the drawing byte for byte.
  //
  // Giving each shape a ladder with its own starting value in it costs one
  // array and makes going back exact for any value a page can be saved with.
  var LADDERS = {};
  function ladderFor(start) {
    var key = String(start);
    if (LADDERS[key]) return LADDERS[key];
    var rungs = LADDER.slice();
    if (rungs.indexOf(start) < 0 && start >= 0 && start <= 1) rungs.push(start);
    rungs.sort(function (a, b) { return a - b; });
    return (LADDERS[key] = rungs);
  }
  function stepped(value, by, start) {
    var rungs = ladderFor(start === undefined ? value : start);
    var best = 0, gap = Infinity;
    for (var i = 0; i < rungs.length; i++) {
      var d = Math.abs(rungs[i] - value);
      if (d < gap) { gap = d; best = i; }
    }
    return rungs[Math.max(0, Math.min(rungs.length - 1, best + by))];
  }
  function tellShape(n) {
    var g = shapes[n]; if (!g) return;
    var st = dressed[g.key];
    say("shape-lit-" + n, Math.round(st.opacity * 100) + "%");
    press("shape-wires-" + n, g.mesh ? st.wires : st.filled);
    press("shape-grey-" + n, st.grey);
  }
  function tellShapes() {
    shapes.forEach(function (g, n) { tellShape(n); });
    say("agree-at", Math.round(agreeAt * 100) + "%");
    say("differ-at", Math.round(differAt * 100) + "%");
    tellMore();
  }
  // THE PAGE SAYS WHEN IT IS NO LONGER SHOWING WHAT IT WAS SAVED SHOWING.
  //
  // Several of these controls take a piece out of the picture on purpose:
  // fading away the part two shapes share leaves a shape with a bite out of
  // it, and turning one right down removes it altogether. That is what they
  // are for. But with the panel closed there was nothing on screen to say
  // so -- and a reader who pressed something a while ago, or who came back
  // to a page their browser had remembered settings for, sees a shape that
  // looks cut, or gone, and no reason for it.
  //
  // Reported exactly that way: a shape that "seemed fully there and then
  // immediately completely gone", by somebody who had not noticed which
  // control was doing it.
  //
  // One word on the button that opens the panel is enough. It is where a
  // reader is already looking when they wonder, the panel behind it shows
  // which control it is and what it is set to, and "as saved" in there puts
  // everything back. An explanation, rather than refusing to let them do it.
  function tellMore() {
    // JUST "more…". A label reading "(changed)" was tried and taken out
    // again: it says that SOMETHING is different without saying what, which
    // is only half an answer and leaves the reader hunting anyway. The note
    // below names the thing they can see and what to press about it, which
    // is the whole answer, so the vague one was only noise.
    say("more", (panel.hidden ? "more" : "less") + "\u2026");
    // AND THE NOTE ABOUT SEE-THROUGH SURFACES, only while one is.
    //
    // Here rather than in tellShapes(), which per-shape presses do not call
    // -- they call the singular tellShape(). That is the second time the
    // same trap has been walked into in this file: anything that has to be
    // true after EVERY press belongs on the one path every press takes.
    var thin = shapes.some(function (g) { return dressed[g.key].opacity < 1; })
      || agreeAt < 1 || differAt < 1;
    var note = panel.querySelector('[data-cq="facets"]');
    if (note) note.hidden = !thin;
  }
  function shapePress(what) {
    var bits = what.split("-");            // shape-fainter-2
    var n = parseInt(bits[2], 10);
    var g = shapes[n]; if (!g) return true;
    var st = dressed[g.key];
    if (bits[1] === "fainter")
      st.opacity = stepped(st.opacity, -1, g.opened.opacity);
    if (bits[1] === "stronger")
      st.opacity = stepped(st.opacity, 1, g.opened.opacity);
    // ONE BUTTON, TWO MEANINGS, AND NEVER BOTH AT ONCE: a solid has wires
    // drawn over it, a flat cut is filled in or left as an outline. Which of
    // the two a shape gets is decided when the row is built, from what that
    // shape actually is.
    if (bits[1] === "wires") {
      if (g.mesh) st.wires = !st.wires; else st.filled = !st.filled;
    }
    if (bits[1] === "grey") st.grey = !st.grey;
    dressOne(g);
    tellShape(n);
    return true;
  }

  function fullscreen() {
    var el = document.documentElement;
    if (document.fullscreenElement) {
      if (document.exitFullscreen) document.exitFullscreen();
    } else if (el.requestFullscreen) {
      // A REFUSAL IS NORMAL, NOT AN ERROR. A browser will decline this when
      // the press did not come from a real click -- which is exactly what
      // happens when a page is being driven by a script. Unhandled, the
      // rejected promise prints a red line in the console of a page that is
      // working perfectly.
      var p = el.requestFullscreen();
      if (p && p.catch) p.catch(function () {});
    }
  }
  function snapshot() {
    if (!(window.Plotly && window.Plotly.downloadImage)) return;
    var name = (document.title || "gamut").replace(/[^\\w .-]+/g, " ")
      .replace(/\\s+/g, " ").trim().slice(0, 70) || "gamut";
    (settings.ids || []).forEach(function (id, i) {
      var gd = document.getElementById(id);
      if (!gd || !gd._fullLayout) return;
      var box = gd.getBoundingClientRect();
      window.Plotly.downloadImage(gd, {
        format: "png",
        // TWICE THE SIZE IT IS DRAWN AT. A picture grabbed at screen size
        // looks soft the moment it is put in a document, and this costs
        // nothing but a moment.
        scale: 2,
        width: Math.max(320, Math.round(box.width || 900)),
        height: Math.max(240, Math.round(box.height || 600)),
        // Two panes are two files, numbered, rather than one file that
        // silently holds half of what is on screen.
        filename: (settings.ids || []).length > 1 ? name + " " + (i + 1) : name
      });
    });
  }

  function handler(ev) {
    var what = ev.target.getAttribute("data-cq");
    if (!what) return;
    if (what.indexOf("shape-") === 0) { shapePress(what); push(); return; }
    if (what.indexOf("agree-") === 0 || what.indexOf("differ-") === 0) {
      var by = (what.indexOf("-more") > 0 ? 1 : -1);
      if (what.indexOf("agree-") === 0) agreeAt = stepped(agreeAt, by);
      else differAt = stepped(differAt, by);
      shapes.forEach(dressOne);
      tellShapes();
      push();
      return;
    }
    if (what === "shapes-back") { undress(); tellShapes(); push(); return; }
    if (what.indexOf("look-") === 0) {
      if (window.cqSpin.look) window.cqSpin.look(what.slice(5));
      // The movement stops when a viewpoint is chosen -- see look() -- so the
      // Play button has to stop claiming otherwise.
      running = false;
      push();
      return;
    }
    if (what === "cut-down") { showCut(cutAt - 1); push(); return; }
    if (what === "cut-up") { showCut(cutAt + 1); push(); return; }
    if (what === "full") { fullscreen(); return; }
    if (what === "shot") { snapshot(); return; }
    if (what === "more") {
      panel.hidden = !panel.hidden;
      tellMore();
      fit();
      return;
    }
    if (what === "home") {
      if (window.cqSpin.reset) window.cqSpin.reset();
      return;
    }
    // A QUARTER BIGGER OR SMALLER A PRESS. Small enough that nobody
    // overshoots and loses the shape, large enough that one press is plainly
    // something rather than nothing.
    if (what === "in") { window.cqSpin.zoom(1.25); return; }
    if (what === "out") { window.cqSpin.zoom(1 / 1.25); return; }
    // A TWELFTH OF THE PICTURE a press, for the same reason.
    if (what === "left") { window.cqSpin.slide(-1 / 12, 0); return; }
    if (what === "right") { window.cqSpin.slide(1 / 12, 0); return; }
    if (what === "up") { window.cqSpin.slide(0, 1 / 12); return; }
    if (what === "down") { window.cqSpin.slide(0, -1 / 12); return; }
    if (what === "play") { running = !running; if (running) wake(); }
    if (what === "slower") both = Math.max(1, both - 1);
    if (what === "faster") both = Math.min(12, both + 1);
    if (what === "turn-slower") step("turn", -1);
    if (what === "turn-faster") step("turn", 1);
    if (what === "tilt-slower") step("tilt", -1);
    if (what === "tilt-faster") step("tilt", 1);
    if (what === "turn-narrower") sweep("turn", -10);
    if (what === "turn-wider") sweep("turn", 10);
    if (what === "tilt-narrower") sweep("tilt", -10);
    if (what === "tilt-wider") sweep("tilt", 10);
    // REMEMBERS WHAT IT WAS, so switching an axis off and on again brings back
    // the movement the page was saved with rather than a guess at one.
    // REMEMBERS WHAT IT WAS, and "what it was" is now what the reader last
    // chose rather than only what the page was saved with -- otherwise
    // setting a direction to go all the way round and then switching it off
    // and on again would quietly put it back to a swing.
    if (what === "lr") turn.mode = (turn.mode && turn.mode !== "off")
      ? "off" : chosen.turn;
    if (what === "ud") tilt.mode = (tilt.mode && tilt.mode !== "off")
      ? "off" : chosen.tilt;
    if (what === "grid") { picture.grid = !picture.grid; applyPicture(); }
    if (what === "labels") { picture.labels = !picture.labels; applyPicture(); }
    if (what === "key") { picture.key = !picture.key; applyPicture(); }
    if (what === "notes") { picture.notes = !picture.notes; applyPicture(); }
    if (what === "appearance") {
      mode = nextScheme();
      applyMode();
    }
    push();
  }
  bar.addEventListener("click", handler);
  panel.addEventListener("click", handler);
  // A SLIDER IS NOT A BUTTON. Dragging one fires "input" the whole way and
  // "click" only sometimes and only at the end, so the click handler above
  // would have let somebody drag it from top to bottom with the picture
  // never moving until they let go -- which reads as a slider that is broken
  // rather than one that is slow.
  bar.addEventListener("input", function (ev) {
    if (ev.target.getAttribute("data-cq") !== "cut") return;
    showCut(parseInt(ev.target.value, 10));
    push();
  });
  // THE PICTURE IS A DIFFERENT SIZE IN FULL SCREEN, and a plot measures its
  // box once. Without this the shape stays the size of the old window with a
  // wide black margin round it, which looks like the button half worked.
  ["fullscreenchange", "webkitfullscreenchange"].forEach(function (ev) {
    document.addEventListener(ev, function () {
      press("full", !!document.fullscreenElement);
      window.setTimeout(fit, 60);
    });
  });
  applyPicture();
  dressAll();
  tellShapes();
  // ONLY IF IT MOVED. The page was already drawn at the height it was saved
  // at, so re-applying that on every load would redraw every outline for
  // nothing in the first moment somebody is looking at it.
  if (cuts && cutAt !== (cuts.at || 0)) showCut(cutAt);
  if (mode !== (settings.mode || "dark")) applyMode();
  push();
};
"""


def write_side_by_side_html(pages, out: Path, mode: str = "dark",
                            linked: bool = True, spin=None,
                            controls: bool = True, offer=None) -> Path:
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
    _t = _escape_title(" and ".join(n for n, _f in pages) or "Measured gamut")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">\
<title>{_t} — ChromIQ Gamut Viewer</title><style>
 html,body {{ margin:0; padding:0; height:100%; overflow:hidden;
              background:{colours['page']}; }}
 body  {{ display:flex; flex-direction:column; }}
 .row  {{ display:flex; flex:1 1 auto; min-height:0; width:100%; }}
 @media (max-width:1024px) {{ .modebar {{ display:none !important; }} }}
 @media (max-width:820px) {{ .gtitle {{ font-size:11px !important; }} }}
 .half {{ flex:1 1 0; min-width:0; display:flex; flex-direction:column; }}
 .half + .half {{ border-left:1px solid {colours['grid']}; }}
 .cap  {{ height:22px; line-height:22px; padding:0 10px; font-size:12px;
          color:{colours['caption']}; background:{colours['page']};
          font-family:Menlo,Consolas,"Courier New",monospace;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
 .half > div:last-child {{ flex:1 1 auto; min-height:0; }}
</style></head><body><div class="row">{''.join(blocks)}</div>{resize}{link}<script>{_ORDER_JS}</script>{_spin_script(ids, ({"flat": True, **(spin or {})} if flat else spin), mode, controls, offer)}</body></html>"""
    Path(out).write_text(html, encoding="utf-8")
    return Path(out)


def _write_dark_html(fig, out: Path, mode: str = "dark", spin=None,
                     carry_viewer: bool = True, notes: str = "",
                     controls: bool = True, offer=None) -> Path:
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
    # A NAME FOR THE TAB, THE BOOKMARK AND THE PASTED LINK. Plotly writes a
    # document with no <title> at all, so a page saved for somebody else
    # arrived showing nothing but its file name — in the one feature that
    # exists for sending a measurement to another person. The caption already
    # says what the picture is, so it is what the tab says too.
    html = _titled(html, _page_title(fig))
    _PAGE_BACKGROUND = SCENE_COLOURS["light" if mode == "light" else "dark"]["page"]
    # HIDING THE OVERFLOW HIDES THE NUMBERS. A single full-bleed scene should
    # not scroll -- there is nothing under it and a stray scrollbar only makes
    # the picture jump. But the written-out figures are appended AFTER the
    # scene, which is already the full height of the window, so they land
    # entirely below the fold; with the overflow hidden a reader could not
    # reach them at all. Fifteen real wheel notches on the published page 03
    # moved it not one pixel, and those figures are the whole reason that page
    # exists. So: hidden when there is only a picture, scrollable when there
    # is something to scroll to.
    _overflow = "auto" if notes else "hidden"
    # A COLUMN: the picture, then the figures, then the controls. Laying the
    # page out rather than floating things over it is what makes the strip
    # unable to cover the key, at any width -- see _SPIN_CONTROLS_JS.
    style = (f"<style>html,body{{background:{_PAGE_BACKGROUND};margin:0;"
             f"padding:0;height:100%;overflow:{_overflow};}}"
             f"body{{display:flex;flex-direction:column;}}"
             f"body > div:first-of-type{{flex:1 1 auto;min-height:0;}}"
             # THE TOOLBAR SAT ON THE CAPTION on a narrow screen -- 2,464
             # square pixels of buttons straight over the words on a phone.
             #
             # It goes rather than moves, under 1024px, and that is a judgement
             # worth writing down. The toolbar holds zoom, pan, reset and
             # save-an-image: on a touch screen the first three are what
             # fingers already do, reset is on the strip along the bottom, and
             # the icons are 22px targets. So it costs a phone reader almost
             # nothing and gives back the whole width of the caption. The
             # threshold is 1024 rather than a phone width because the
             # caption is not a fixed size either: the ink-amount page's runs
             # to 821px, which reaches a top-right toolbar on a tablet while
             # a shorter one would not. Above that the two have never met.
             f"@media (max-width:1024px){{.modebar{{display:none !important;}}}}"
             # The caption is one line of SVG text that cannot wrap, and it is
             # the same 455px wide whatever the screen -- so on a phone the
             # end of it simply falls off. A smaller face does not fix that,
             # it only means more of the sentence survives.
             f"@media (max-width:820px){{.gtitle{{font-size:11px !important;}}}}"
             f"@media (max-width:480px){{.gtitle{{font-size:10px !important;}}}}"
             f"</style>")
    if notes or controls:
        # AND THE PICTURE HAS TO MAKE ROOM FOR WHAT IS UNDER IT. Letting the
        # page scroll
        # is not enough on its own: the scene is the full height of the
        # window, a 3D scene takes the wheel for zooming, and there is no
        # other part of the page to put the pointer over -- so fifteen wheel
        # notches zoomed the shape and moved the page not one pixel. Giving
        # the scene rather less than the window puts the figures on screen
        # from the start, where they can simply be read.
        #
        # THE WRAPPER, NOT THE PLOT. Plotly puts its graph div inside a plain
        # <div style="height:100%"> of its own, and that inline height would
        # otherwise win over the column's sizing and push the figures off the
        # bottom again. Letting it flex instead hands the leftover height to
        # the picture and the height it asks for to everything else.
        #
        # !important because that height is written inline, and an inline
        # style beats a rule that does not say so.
        #
        # THE PAGE GROWS; THE PICTURE DOES NOT SHRINK AWAY. Everything above
        # was still inside a body fixed at exactly the height of the window,
        # and a column of flexible children in a box that cannot grow does not
        # scroll -- it squeezes. Measured on a phone-sized window: a page of
        # numbers 466px tall left the picture 78px. The picture was the
        # smallest thing on a page whose entire purpose is the picture.
        #
        # So the body may grow past the window (min-height, not height), the
        # numbers keep whatever height they need (flex:0 0 auto), and the
        # picture is promised a good share of the first screen it can never be
        # squeezed below. Anything that does not fit goes below the fold,
        # which is what scrolling is for.
        #
        # 62vh is chosen so that the strip of controls and the first line or
        # two of the numbers are always visible under the picture: that is
        # what tells a reader on a phone there is more to come, and it leaves
        # them somewhere to put a thumb that is not the picture -- because the
        # picture now takes touches over completely.
        style += ("<style>html{height:100%;}"
                  "body{height:auto;min-height:100%;}"
                  "body > div:first-of-type"
                  "{height:auto !important;min-height:62vh;}"
                  ".cq-notes{flex:0 0 auto;}</style>")
        # WHY `controls` AND NOT ONLY `notes`.
        #
        # This was written for the written-out figures, because they were the
        # only thing that had ever sat under the picture, and it was applied
        # only when they were there. Then the panel of controls grew from
        # four switches to twenty-one -- and a page with NO figures on it,
        # whose picture was therefore still a rigid flex item in a body fixed
        # to the height of the window, had nothing to give the panel but the
        # picture itself.
        #
        # Measured on such a page with the panel open: **0 pixels of picture
        # at 320x568, and 127 at 390x844.** The page had become a wall of
        # buttons with the thing they control squeezed out of existence.
        #
        # It went unseen because every page measured until then carried the
        # figures, and so every page measured until then had this rule.
    # HOW WIDE THE PAGE THINKS IT IS, WHICH ON A PHONE IT OTHERWISE GETS
    # WRONG BY A FACTOR OF TWO AND A HALF.
    #
    # A phone browser handed a page with no viewport tag assumes the page was
    # written for a desktop: it lays it out in a pretend window about 980
    # pixels wide and then scales the whole thing down to fit the screen. On a
    # 390-pixel phone that is a scale of about 0.40 -- so a 12-pixel label is
    # drawn at five physical pixels and a 34-pixel button at fourteen.
    #
    # Reported as "on some occurrences the controls are tiny", and that is
    # exactly it. Worse, EVERY rule written for a narrow screen was dead: the
    # page believed it was 980 pixels wide, so the one-column layout, the
    # bigger tap targets and the short-screen cap never came into force on
    # the one device they were written for.
    #
    # IT WENT UNSEEN BECAUSE OF HOW IT WAS TESTED. Every viewport measurement
    # here resizes the real window, and a desktop browser in a narrow window
    # lays out at that width whether or not this tag is present -- so the
    # probes measured the layout this tag produces while the pages shipped
    # without it. The showcase index has had one all along, which is why that
    # page has always read properly on a phone and these have not.
    #
    # `width=device-width` says lay it out at the width of the screen, and
    # `initial-scale=1` says do not zoom it afterwards.
    head = ('<meta name="viewport" '
            'content="width=device-width,initial-scale=1">')
    if "</head>" in html:
        html = html.replace("</head>", head + style + "</head>", 1)
    else:
        html = head + style + html
    if notes:
        # THE NUMBERS TRAVEL WITH THE PICTURE. A shape sent to somebody
        # without them is a shape they cannot check, and "which paper was
        # that?" is where every one of these ends up otherwise.
        colours = SCENE_COLOURS["light" if mode == "light" else "dark"]
        # NAMED, so the reader can be given a switch for it. On a phone the
        # numbers are easily taller than the screen, and somebody who has read
        # them once wants them out of the way -- see the "notes" control.
        block = ("<div class=\"cq-notes\" style=\"font:13px/1.6 -apple-system,"
                 f"Segoe UI,Roboto,sans-serif;color:{colours['text']};"
                 f"background:{colours['page']};padding:14px 22px 78px;"
                 f"white-space:pre-wrap\">{notes}</div>")
        html = (html.replace("</body>", block + "</body>", 1)
                if "</body>" in html else html + block)
    # PUT THE SEE-THROUGH SURFACES IN ORDER -- always, and before anything
    # else. This is not a setting and not part of the turning: it is what
    # makes a see-through shape look like the solid one it is, and a page
    # without any movement in it can still be dragged round by hand. See
    # _ORDER_JS for what it fixes and what it was measured to cost.
    order = f"<script>{_ORDER_JS}</script>"
    html = (html.replace("</body>", order + "</body>", 1)
            if "</body>" in html else html + order)
    turn = _spin_script(["scene0"], spin, mode, controls, offer)
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


#: How far apart the cross-sections a saved page carries are, in L*, and how
#: many points each outline is drawn with.
#:
#: TWO L* IS THE STEP because it is small enough that sliding through them
#: reads as one shape changing rather than a series of stills, and because the
#: alternative costs real bytes: every level is an outline per shape, and at
#: one-unit steps a two-paper page carries about 90 of them. Measured on the
#: demo pair -- 45 levels at 120 points comes to 168 kB of the page, against
#: 4.9 MB for the viewer that draws it, so the slider is about three percent
#: of a file that already travels.
#:
#: 120 POINTS is a quarter fewer than the window itself draws and the
#: difference cannot be seen: an outline of a gamut has no feature narrower
#: than three degrees of hue.
_CUT_STEP = 2.0
_CUT_POINTS = 120


def slice_levels(gamuts, step: float = _CUT_STEP, points: int = _CUT_POINTS):
    """Every cross-section a reader can slide to, worked out once at save time.

    A cross-section in the window has a slider under it, and the saved page
    had one fixed height and no way to move it -- so the one view where "does
    this paper reach further into the cyans" is a glance rather than a guess
    could only ever answer that question at whatever lightness the sender
    happened to be looking at.

    Doing it here rather than in the page is not an optimisation, it is the
    only way round: slicing a gamut needs the whole 3D shape and a Delaunay
    triangulation of it, and a flat page carries neither. Precomputed, the
    page carries the answers and the slider only chooses between them.

    Returns ``None`` when there is nothing to slide through -- a single
    lightness, or no gamut that can be cut at all -- because a slider with one
    position is furniture.
    """
    from gamutview import slice_at

    lows = [float(g.vertices[:, 0].min()) for _n, g in gamuts]
    highs = [float(g.vertices[:, 0].max()) for _n, g in gamuts]
    if not lows:
        return None
    lo, hi = min(lows), max(highs)
    first = math.ceil(lo / step) * step
    levels = []
    while first <= hi:
        levels.append(round(first, 3))
        first += step
    if len(levels) < 2:
        return None

    rings: dict = {name: [] for name, _g in gamuts}
    span_lo, span_hi = None, None
    for level in levels:
        for name, g in gamuts:
            try:
                ring = slice_at(g, level, steps=points)
            except Exception:          # noqa: BLE001 — one bad cut, not a page
                ring = np.empty((0, 2))
            if len(ring):
                closed = np.vstack([ring, ring[:1]])      # join the ends
                low = closed.min(axis=0)
                high = closed.max(axis=0)
                span_lo = low if span_lo is None else np.minimum(span_lo, low)
                span_hi = high if span_hi is None else np.maximum(span_hi, high)
                # ROUNDED TO A HUNDREDTH of a Lab unit. Nothing was ever
                # measured to that precision -- an instrument repeating to
                # 0.1 ΔE is a good one -- and the full sixteen digits of a
                # double would triple the size of this for no visible change.
                rings[name].append(
                    {"x": [round(float(v), 2) for v in closed[:, 0]],
                     "y": [round(float(v), 2) for v in closed[:, 1]]})
            else:
                # AN EMPTY OUTLINE, KEPT RATHER THAN SKIPPED. A shape that
                # does not reach this height has to be able to come back when
                # the slider moves, and a trace that was never created cannot.
                rings[name].append({"x": [], "y": []})
    if span_lo is None:
        return None
    # TRIM THE ENDS THAT DRAW NOTHING.
    #
    # The range starts at the lowest point of the lowest shape, and a gamut's
    # lowest point is a corner rather than its neutral axis -- so for the
    # first few levels the cut misses every shape and the outline is empty.
    # Measured on the demo pair: the slider ran from L* 6 and drew nothing at
    # all until L* 12, which is three positions at the bottom of the travel
    # where dragging it does visibly nothing. A control with dead travel at
    # the end reads as a broken control.
    used = [i for i in range(len(levels))
            if any(rings[name][i]["x"] for name, _g in gamuts)]
    if not used:
        return None
    first_used, last_used = used[0], used[-1]
    levels = levels[first_used:last_used + 1]
    for name in rings:
        rings[name] = rings[name][first_used:last_used + 1]
    # ONE RANGE FOR EVERY LEVEL, so the picture does not jump about as the
    # slider moves. Left to itself each cross-section is scaled to fit, which
    # means the outline stays roughly the same size on screen while the number
    # beside it changes -- and the one thing this view exists to show is that
    # a gamut is wider in the middle than at the top.
    centre = (span_lo + span_hi) / 2.0
    half = max(float(np.max(span_hi - span_lo)) / 2.0, 1.0) * 1.08
    return {"levels": levels, "rings": rings,
            "extent": ((float(centre[0] - half), float(centre[0] + half)),
                       (float(centre[1] - half), float(centre[1] + half)))}


def build_slice_figure(gamuts, lightness: float, title: str,
                       mode: str = "dark", extent=None, legend: bool = True,
                       first: int = 0, slidable: bool = False):
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
            # A SHAPE THAT DOES NOT REACH THIS HEIGHT STILL GETS ITS TRACE
            # when the page can be slid through other heights, because a
            # trace that was never created cannot be brought back by moving
            # the slider -- the shape would simply be gone from the page for
            # good, at every lightness, because of the one it opened at.
            # Without a slider there is nothing to come back for, and an
            # empty outline in the key would only puzzle somebody.
            if not slidable:
                continue
            closed = np.empty((0, 2))
        else:
            closed = np.vstack([ring, ring[:1]])   # join the ends
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
                     mode: str = "dark", controls: bool = False,
                     offer=None) -> Path:
    """One page holding one flat cross-section. See :func:`build_slice_figure`.

    *controls* is the reader's strip. There is nothing to turn on a flat cut,
    so it carries only what still means something -- zoom, move, back to where
    it opened, and the slider that moves the cut up and down.
    """
    cuts = None
    if controls and (offer is None or offer.get("cut", True)):
        cuts = slice_levels(gamuts)
        if cuts is not None:
            cuts["title"] = title
            # WHICH OF THEM THE PAGE OPENED AT, so the slider starts under
            # the picture it is next to rather than in the middle.
            cuts["at"] = min(range(len(cuts["levels"])),
                             key=lambda i: abs(cuts["levels"][i] - lightness))
    spin = None
    if controls:
        spin = {"flat": True}
        if cuts is not None:
            spin["cuts"] = cuts
    _write_dark_html(
        build_slice_figure(gamuts, lightness, title, mode,
                           extent=cuts["extent"] if cuts else None,
                           slidable=cuts is not None),
        out, mode, spin=spin, controls=controls, offer=offer)
    return out


def write_html(gamuts, out: Path, title: str, **kwargs) -> Path:
    """One self-contained page holding one scene. See :func:`build_figure`."""
    mode = kwargs.get("mode", "dark")
    # Not a drawing option: it is what the page DOES once drawn, so it never
    # reaches build_figure.
    spin = kwargs.pop("spin", None)
    carry = kwargs.pop("carry_viewer", True)
    notes = kwargs.pop("notes", "")
    controls = kwargs.pop("controls", True)
    offer = kwargs.pop("offer", None)
    return _write_dark_html(build_figure(gamuts, title, **kwargs), out, mode,
                            spin=spin, carry_viewer=carry, notes=notes,
                            controls=controls, offer=offer)


def build_figure(gamuts, title: str, opacity: float | None = None,
                 points: bool = False, patches=None,
                 aspect: str = "data", styles=None, lost=None,
                 mode: str = "dark", paint: str = "true",
                 depth: float = 0.35, mesh_paint: str = "plain",
                 rings: int = 0, per_shape=None, neutrals=None,
                 ideal_neutrals: bool = False, chart=None,
                 light=None, grid: bool = True, space=None,
                 chart_look=None, agree: float = 1.0, differ: float = 1.0,
                 split: bool = False):
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
    # WHERE THE SHAPES AGREE, AND WHETHER TO DRAW IT SEPARATELY.
    #
    # Two gamuts over each other are mostly the same gamut: the agreement is
    # the bulk of both, it is drawn twice, and it hides the part where they
    # differ -- which is the only part anybody put them side by side to see.
    # Split into two meshes, the agreement can be faded and the disagreement
    # left standing on its own.
    #
    # SPLIT EVEN AT FULL STRENGTH when *split* is set, which is what a saved
    # page asks for: the reader has to be able to move the slider, and a
    # trace that was never written cannot be faded by anybody. On screen the
    # split is only made when it changes something, because it costs a
    # containment test per pair on every redraw.
    splits = None
    if len(gamuts) > 1 and (split or agree < 1.0 or differ < 1.0):
        splits = agreement_masks(gamuts)
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
        # A STYLE NOBODY HANDLES MUST NOT DRAW NOTHING.
        #
        # The two branches below ask for "solid", "solid+mesh" and "mesh", and
        # anything else falls between them and adds no trace at all -- a page
        # that opens, reports no error, and holds an empty box. Found by
        # asking this function for "outline", which is a real style name in
        # this file and belongs to a chart's skin rather than to a shape; the
        # page came back with nought traces and looked like a rendering fault.
        #
        # The window can only send the three, so this is not reachable from
        # the controls. It is reachable from the command line and from any
        # other caller, and an empty picture is the least useful way to be
        # told a name is wrong.
        if how not in SHAPE_STYLES:
            raise ValueError(
                f"unknown shape style {how!r}; expected one of "
                f"{', '.join(sorted(SHAPE_STYLES))}. (\"outline\" is a chart "
                f"skin, not a shape style -- see chart_look.)")
        marked = lost[i] if lost is not None and i < len(lost) else None
        # WHERE THIS SHAPE AGREES WITH THE OTHERS, AND WHERE IT DOES NOT.
        #
        # `disagrees` is per TRIANGLE; `standing` is per VERTEX -- a vertex
        # counts as standing out when any triangle it belongs to does. The
        # surface is faded with a per-vertex alpha rather than cut into two
        # meshes, because two transparent meshes do not composite to the same
        # thing as one: see _with_alpha, where that was measured.
        alphas = None
        disagrees = splits[i] if splits is not None else None
        if disagrees is not None:
            standing = agreeing_edges(g, disagrees)
            alphas = np.where(standing, differ, agree)
        # CARRIED INTO THE PAGE only when the reader is being given the
        # control. It is one character per vertex -- about half a kilobyte a
        # shape -- against the 66 kB a second copy of the mesh would have
        # cost, and a page nobody can fade has no use for it at all.
        stand = (agreeing_edges(g, disagrees)
                 if (split and disagrees is not None) else None)
        if marked is not None:
            fig.add_trace(_mesh_lost(g, name, base_i, marked, c["kept"],
                                     depth_i, light=light, alphas=alphas,
                                     stand=stand))
        elif how in ("solid", "solid+mesh"):
            fig.add_trace(_mesh(g, name, opacity=base_i,
                                paint=paint_i, index=i, depth=depth_i,
                                page=c["page"], light=light, alphas=alphas,
                                stand=stand))
            fig.add_trace(_legend_proxy(
                name, _legend_swatch(_paint_vertices(g, paint_i, i)
                                     or g.colors, c["page"]), name))
        if how in ("mesh", "solid+mesh"):
            # A CAGE CANNOT CARRY A COLOUR PER POINT -- the drawing library
            # gives a line one colour for the whole trace -- so this is the
            # one place the split survives. It costs far less here than it
            # would on a surface: lines are thin, they overlap each other
            # hardly at all, and the blending order that ruins two
            # transparent surfaces is not visible between two sets of wires.
            parts = ([(None, 1.0)] if disagrees is None
                     else [(disagrees, differ), (~disagrees, agree)])
            # WORK OUT WHICH HALVES ARE ACTUALLY DRAWN BEFORE DECIDING WHICH
            # ONE CARRIES THE NAME.
            #
            # A cage split in two used to hand its key to the half that
            # DISAGREES with the other shapes, and silence the other half so
            # the name could not appear twice. Both rules are right on their
            # own and together they lose the name altogether, because a shape
            # can have no disagreeing half at all: the matte paper fits
            # entirely inside the glossy one, so 0 of its 978 triangles
            # differ. The half carrying the key was skipped as empty and the
            # only half left was the silenced one.
            #
            # Reported as "no label indicator for the matte paper outline",
            # and it is on a published page: 11-everything-handed-over.html
            # shows a grey cage with nothing in the key to say whose it is.
            #
            # Choosing from the halves that survive, rather than from the
            # halves that were proposed, cannot lose it: whatever is drawn
            # first is named, and there is always a first.
            drawn_parts = [p for p in parts
                           if p[0] is None or bool(np.any(p[0]))]
            for at, (only, strength) in enumerate(drawn_parts):
                first = at == 0
                for trace in _edges(g, name, colour=c["wire"],
                                    width=1.0 if how == "mesh" else 0.7,
                                    # THE CAGE'S OWN COLOUR, which may follow
                                    # the surface's and no longer has to.
                                    paint=outline_paint(mesh_paint_i, paint_i),
                                    index=i,
                                    # THE FIRST HALF DRAWN CARRIES THE KEY,
                                    # and only the first, so the cage is
                                    # named exactly once however it is split.
                                    key=c["mark"] if first else None,
                                    page=c["page"], only=only):
                    if strength < 1.0:
                        trace.update(opacity=strength)
                    # AND SILENCED OUTRIGHT ON EVERY LATER HALF. Passing
                    # key=None does NOT mean "no entry in the list of names":
                    # _edges reads it as "no separate marker, so the cage
                    # itself carries the name", so the half meant to be silent
                    # would be the half that spoke.
                    if not first:
                        trace.update(showlegend=False)
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
        # A SHAPE MAY HAVE NO MEASURED PATCHES AT ALL, and one of them is on
        # screen the moment somebody compares against sRGB, Adobe RGB or any
        # other named space: a reference space is worked out from its own
        # definition, it was never printed, and nobody measured a patch of
        # it. The list carries None in its place.
        #
        # Without the last test this crashed outright -- a measured chart,
        # Compare with set to Adobe RGB (1998), tick Show every patch I
        # measured, and the window came apart with "too many indices for
        # array: array is 0-dimensional". Reachable in three clicks from an
        # opened file.
        #
        # The greys directly below already tested for it; this one did not,
        # which is the whole of the bug.
        if (points and patches is not None and i < len(patches)
                and patches[i] is not None):
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
