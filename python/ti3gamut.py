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
            f"point the viewer at it with Where ArgyllCMS is… under The "
            f"application itself, at the foot of the left-hand column."
            f"\n\n.ti3 measurements, .gam files and ICC profiles "
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
                         space: str = "lab", lab=None):
    """The perfectly neutral line, drawn as a reference rather than as data.

    Deliberately quiet — thin, dashed and unmarked — because it is not a
    measurement of anything. The eye should read it as the wall the measured
    greys are leaning away from.
    """
    import plotly.graph_objects as go

    # A SHAPE WITH NO MEASURED GREYS CAN STILL SHOW WHERE NEUTRAL RUNS.
    #
    # Reported from the window, of a profile: "i could understand why this
    # can't show the measured grey from just a profile - but is a neutral line
    # impossible as well here?" It is not. The measured greys are only ever
    # borrowed for their LIGHTNESS RANGE -- the line itself is a* 0, b* 0 by
    # definition -- and a shape that was never measured still has a range: its
    # own. Passing `lab` hands that over directly.
    if lab is None:
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

    The cage can be painted the same ways the solid can, and it is ONE TRACE
    however it is painted.

    THAT IS A CORRECTION, and an expensive one to have got wrong. This used to
    read "Plotly gives a line one colour per trace rather than per point", and
    on that belief a coloured cage was cut into one trace per band of
    coarsened colour. The belief was wrong: ``scatter3d.line.color`` is
    ``array_ok`` -- checked against the library's own validator, and then
    rendered, because a validator accepting an array is not proof the WebGL
    renderer honours it.

    WHAT IT COST, measured on the shipped pages: an Adobe RGB cage has 6726
    edges and came out as 296 separate traces, each its own WebGL object with
    its own draw call. Page 14 shipped with 357 traces and page 18 with 642.
    Basti reported the consequence from an iPhone as "performance is bad".
    Rendered side by side at 900x700, the one-trace cage differs from the
    banded one over 2.25% of the picture by at most 29/255 -- and that
    difference is the banding disappearing, so the cheap version is also the
    accurate one.

    Each segment now carries its two real end colours rather than its first
    vertex's rounded one, which the banding could never do.

    Plain grey stays the default: it is cheaper still (one colour, no array),
    and on top of a solid shape a grey cage reads more clearly than a coloured
    one competing with the colours underneath it.
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
        # SPELT AS #rrggbb RATHER THAN rgb(r,g,b), and the reason is a
        # measured one rather than a style. A cage carries one of these per
        # point -- 20,178 of them for an Adobe RGB comparison -- and every one
        # is validated, serialised into the page and parsed by the browser.
        # Seven characters against eleven: the whole figure took 246 ms and
        # 1191 kB with the long spelling, 172 ms and 1055 kB with the short
        # one. Checked on all 2,400 vertex colours: not one decodes
        # differently, so this is the same picture written more briefly.
        per_vertex = [f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
                      for r, g, b in gamut.colors]
    xs, ys, zs, colours = [], [], [], []
    seen_again = set()
    for tri in f:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            # `edge` here too, for the same reason: `key` is this function's
            # colour argument and the loop above used to eat it.
            edge = (a, b) if a < b else (b, a)
            if edge in seen_again:
                continue
            seen_again.add(edge)
            xs += [v[a, 0], v[b, 0], None]
            ys += [v[a, 1], v[b, 1], None]
            zs += [v[a, 2], v[b, 2], None]
            # THE THIRD ENTRY IS THE LIFTED PEN, and it still needs a colour:
            # the array is read alongside x, y and z and has to be the same
            # length as them. Its value is never drawn.
            colours += [per_vertex[a], per_vertex[b], per_vertex[a]]
    # HANDED OVER AS A PLAIN DICT, not as a go.Scatter3d, and this is the
    # single biggest saving in a redraw.
    #
    # Building the object runs plotly's validator over every entry of the
    # colour list one at a time -- 151,758 calls to `to_scalar_or_list` in one
    # profiled redraw. The figure accepts a dict and converts it internally by
    # a faster route. Measured on the Adobe RGB cage,build plus add_trace
    # plus to_html: 453 ms through the class, 246 ms through a dict, and the
    # trace JSON that comes out is byte-for-byte identical.
    #
    # NOWHERE ELSE. Every other trace in this file carries a handful of
    # values, where the class is clearer and costs nothing worth counting.
    # This one carries twenty thousand.
    traces = [dict(
        type="scatter3d",
        x=xs, y=ys, z=zs, mode="lines",
        line=dict(color=colours, width=width),
        name=f"{name} (outline)", legendgroup=f"{name}-outline",
        showlegend=False, hoverinfo="name")]
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


def _is_a_shell(only=None) -> dict:
    """Mark a surface that is CLOSED, for the engine that orders the walls.

    WHY IT MATTERS. `cqOrder` draws the whole away-facing half of a surface
    before the whole toward-facing half, which fixes the kite-shaped wedges.
    The rule that makes that right is true of a closed shell and only of a
    closed shell: along any ray the near wall is nearer than the far wall, so
    far-wall-first is correct per pixel.

    AN OPEN SURFACE HAS NO FAR WALL. Splitting a sheet by which way its
    triangles point and drawing one group before the other has no such
    justification, and the two groups can come out in an order that changes
    as the shape turns -- patches appearing and disappearing during movement,
    which is exactly how it was reported.

    The window makes open surfaces routinely: `only` is a subset of the
    triangles, which is how ONE shape becomes an agreeing half and a
    differing half so the two can be drawn at different strengths. Those are
    the halves of a shell, not shells.

    Asking the drawn triangles whether they close was tried and is not good
    enough -- a closed shell of 914 corners comes back with 133 edges
    belonging to one triangle, because corners in the same place are kept
    apart where the colouring needs a sharp edge (see `_weld`).
    """
    return {} if only is not None else {"cqShell": 1}


def static_palette(mode: str):
    """Which palette the colours WRITTEN INTO a file come from.

    ONE ANSWER, BECAUSE TWO IS WHAT WENT WRONG. Eight places asked this, seven
    of them with the same ternary — "light" if the mode is light, otherwise
    dark — and the eighth, the one that builds the page's settings, resolved it
    differently. That was invisible while every page opened in one of the
    window's own two colourings, and the moment "follow you" arrived the two
    answers disagreed: the settings said light, the ternaries said dark, and a
    page came out with a DARK body and a LIGHT control strip. Reported from a
    phone: "the control strip is light mode but the rest is dark".

    "follow you" is not a palette — the page picks one at load from the
    reader's own machine. What is written into the file is only what shows
    before the script runs, and light is the safer of the two: a page that is
    going to be dark repaints itself immediately, while the reverse is a black
    flash in the middle of somebody's document.
    """
    if mode in SCENE_COLOURS:
        return SCENE_COLOURS[mode]
    return SCENE_COLOURS["light"]


def _mesh_lost(gamut, name: str, opacity: float, lost,
               kept: str = _KEPT, depth: float = 0.35, light=None,
               only=None, alphas=None, stand=None,
               lost_in_their_own_colours: bool = False) -> "list":
    """The gamut painted by what the comparison cannot reproduce.

    *only* splits it exactly as it splits a plain mesh -- see :func:`_mesh`.
    The two features ask different questions of the same shape (this one is
    about the chosen comparison, the split is about the other shapes drawn
    beside it) and both can be true at once, so they compose rather than
    exclude each other.
    """
    import plotly.graph_objects as go
    v = _plot_points(gamut)
    # WHAT THE OUT-OF-REACH PART IS PAINTED IN.
    #
    # One flat colour says WHERE the loss is and nothing about what is being
    # lost. Painting those faces in the colours they actually are says both:
    # grey means "this paper can print it", and anything you can SEE is what
    # you would not get. Asked for from the window: "is there a way to turn
    # this magenta out of reach section into the real colors that are out of
    # reach?"
    #
    # It is an option and not a replacement, because the two answer different
    # questions and one of them is weaker in a particular way: an out-of-reach
    # colour that happens to be dark and unsaturated sits close to the grey,
    # so the boundary that a flat magenta makes obvious can become hard to
    # find. The flat colour stays the default for that reason.
    if lost_in_their_own_colours:
        own = [f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
               for r, g, b in gamut.colors]
        colours = [own[i] if bad else kept for i, bad in enumerate(lost)]
    else:
        colours = [_LOST if bad else kept for bad in lost]
    # THE FADE GOES ON BEFORE THE WELD, so it travels with the colours it
    # belongs to. Welding renumbers the vertices; a mask applied afterwards
    # would line up with nothing. A fade at its ENDS leaves the colours plain
    # and removes the invisible triangles instead -- see _solid_remainder.
    picked = (np.asarray(gamut.faces)[np.asarray(only)] if only is not None
              else gamut.faces)
    if alphas is not None:
        colours, picked = _solid_remainder(colours, alphas, picked, opacity)
    # THE MASK IS WELDED WITH THE COLOURS, not alongside them.
    #
    # A saved page has to be able to work this fade out for itself, which
    # means carrying which vertices stand out -- and it must be numbered the
    # way the drawn vertices are, not the way the gamut's are. Welding drops
    # duplicates and renumbers what is left, so the mask is put through the
    # very same call rather than through a second one that could disagree
    # with it. _weld indexes its middle argument and does not care what is in
    # it, which is what makes this safe.
    # THE SIDE IS PART OF WHAT MAKES A CORNER ITSELF. Two corners in the same
    # place on opposite sides of the boundary are two corners, and welding
    # them cost the saved page its sharp edge -- see `_weld_order`.
    carried = None
    if stand is not None:
        keep, _remap = _weld_order(v, colours, stand)
        carried = "".join("1" if stand[i] else "0" for i in keep)
    v, colours, faces = _weld(v, colours, picked, stand)
    # A SIMPLE SKIN IS LIT FACET BY FACET. Reported from the window of two
    # shapes drawn that way: "this one looks scattered", and the picture
    # showed long wedges radiating across the surface with hard edges between
    # them.
    #
    # It is the shading, not the shape. Smooth shading averages the normals of
    # the facets meeting at each corner, and "Wrap it in a simple skin" is a
    # hull over unevenly spread measured points: MEASURED, 151 of its 414
    # triangles are needles — the longest edge more than eight times its own
    # width, the worst 714 times — against 40 of 978 for "Follow the real
    # edge". An average taken across a needle is smeared along it, and that
    # smear is the streak.
    #
    # Lit facet by facet the same hull comes out clean, which is what a coarse
    # wrap actually is. The shape, the volume and the colours are untouched:
    # this changes how the light is worked out and nothing else.
    smooth = getattr(gamut, "mode", "") != "hull"
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        vertexcolor=colours, opacity=opacity, flatshading=not smooth,
        lighting=_lighting(depth, opacity),
        lightposition=light or _LIGHT_OVERHEAD,
        # BOTH COLOURS NAMED, not just the alarming one. "red is out of
        # reach" leaves a reader looking at a two-coloured shape having been
        # told what one of the two means, and quietly invites them to read
        # the grey as "the rest of the picture" rather than as the answer it
        # is. Saying both is four more words and removes the guess.
        name=f"{name} — red is out of reach, grey is within it", showlegend=True,
        hoverinfo="name",
        # The red IS the answer here — see _COLOUR_IS_THE_ANSWER.
        meta=dict(_COLOUR_IS_THE_ANSWER, **_is_a_shell(only),
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


#: A light with no direction in it at all: every face gets the same amount,
#: whichever way it points.
_FLAT_LIGHT = dict(ambient=1.0, diffuse=0.0, specular=0.0, roughness=1.0,
                   fresnel=0.0)


def _lighting(depth: float, opacity: float = 1.0) -> dict:
    """Plotly lighting for a given amount of shape definition.

    At 0 the surface is lit flat and shows only its colours; turning it up
    trades some of that for shading, which is what makes a rounded thing look
    rounded. Kept as one number because "ambient, diffuse, specular, roughness
    and fresnel" is not a question anybody wants to be asked.

    AND IT OPENS UP THE MOMENT THE SKIN IS SEE-THROUGH, which is the cure for
    the "cut triangles" reported three times.

    THROUGH A SEE-THROUGH SKIN YOU SEE ITS OWN INSIDE. The far side's faces
    point away from the light, so they are drawn nearly black, and that
    darkness follows their triangles -- which is exactly what a bite taken
    out of the surface looks like. Everything else was ruled out first, each
    by driving it:

        two shapes crossing     one shape alone shows it too
        the window's own view   the saved page shows it too
        the shading depth       depth 0 and depth 100 are identical
        the order of the faces  reordering them changed 0 pixels
                                (proved live: dropping half moved 169,473)
        which way faces point   splitting away/towards changed nothing
        the gamut's own shape   a convex ball shows it too

    Then the light was flooded, and it went. Measured as roughness -- how
    hard a step there is between neighbouring pixels of the skin -- on that
    ball, at three opacities and five blends between this light and a flat
    one:

        opacity   as today   half way   flat
           0.90       4.82       2.89   1.15
           0.68       4.06       2.45   1.00
           0.40       2.78       1.71   0.75

    It is WORST just below solid, not at the most see-through, so a gentle
    blend by (1 - opacity) would have left the worst case untouched.

    AND THEN IT WAS TRIED ON THE REAL THING AND DID ALMOST NOTHING. The same
    measurement, on the application's own picture of two profiles at 68% --
    same window, same camera, the lighting restyled in place so that only it
    differed:

        with the old light   9.38
        with the flat light  9.27

    A cure that takes a ball from 4.06 to 1.00 and a gamut from 9.38 to 9.27
    is not the cure for what was reported. So the flat light is NOT applied:
    it would have thrown away the modelling on every see-through surface in
    the application and fixed nothing anybody has seen.

    THE COLOURS WERE TRIED NEXT and are not it either: painted one flat
    lilac, the same skin at 68% still shows the same slivers (roughness 8.96
    against 9.39), so they are not the shape's own dark inside showing
    through.

    THE SLIVERS IN OUR OWN SHELL WERE THE NEXT SUSPECT AND ARE NOT IT. Of
    1,824 faces, 26 are thinner than a fiftieth of their own longest edge
    squared, and the thinnest of them sit in the yellow-orange corner the
    wedges were photographed in. Every one was collapsed away -- 26 down to
    0, no holes, the shortest edge of each merged so the neighbours close
    over it -- and the flank came back at 0.848 against 0.886: ONE needle
    gone and every kite exactly where it was. Deleting those faces instead
    made it worse (2.60) and gave the game away: the wedges turned into real
    HOLES in the same places, so those faces are covering ground.

    IT IS THE SHAPE'S OWN FAR WALL, SEEN THROUGH THE NEAR ONE. Every number
    below is the roughness of one crop of that flank -- the mean step between
    neighbouring pixels -- at one camera, on one shape at 68%:

        as it is drawn today               0.886   the kites
        welding coincident corners         0.886   one corner of 914 merged
        flipping the winding               0.886   all 1,824 faces are wound
                                                   inward, consistently, and
                                                   reversing every one of
                                                   them redrew the picture
                                                   pixel for pixel -- so the
                                                   library lights both sides
        flat facets                        0.965   worse
        no lighting at all, live on the    0.822   AND THE KITES ARE STILL
        page (ambient 1, diffuse 0,                THERE. So they are not
        specular 0)                                shading of any kind
        solid, nothing behind to show      0.808   not one of them
        only the half facing you           0.562   not one of them

    -- the last measured on the page itself and put back again to 0.886, so
    the picture answers to this and not to the passing of time.

    At 68% you are looking at both walls; near the outline the far one is
    almost edge-on, so a whole triangle of it lands in a few pixels and its
    facet edges read as wedges rather than as a gradient. It is its COLOURS
    showing through and not its light, which is why no lighting change
    touches it.

    WHY IT TORE, FOUND LATER, AND IT WAS NOT THE IDEA. The culling turned
    each face outward by asking whether it pointed away from the shape's
    MIDDLE, which is only true of a convex shape. This one is not: measured
    against the convex hull of its own corners, **7.4% of it is dents** --
    `icc_gamut` says so in its own docstring, "it returns its own surface with
    the profile's real dents in it", and I read past it. Inside every dent
    that test gives the opposite answer, so FRONT faces were culled, and that
    is the band that went missing.

    NO ASSUMPTION IS NEEDED. The shell ArgyllCMS hands over is a closed,
    consistently wound manifold and it survives the weld intact -- measured on
    two profiles: all 5,472 directed edges walked exactly once in each
    direction, none repeated, before and after `_weld`. The signed volume
    names the convention outright, -818,514 for a shape whose volume is
    818,514, so the faces are wound inward and the outward normal is simply
    the negative of the cross product. No centroid, no convexity.

    WHAT IS LEFT is a thin band right at the outline where faces are almost
    exactly edge-on and flicker between facing you and not. Keeping the ones
    within a small angle of edge-on closes it, and costs nothing to look at
    because an edge-on face covers almost no pixels:

        slack (cosine)   0.00    0.02    0.05    0.10
        of the whole    98.3%   99.0%   99.5%   99.8%

    AND ONE MEASUREMENT OF MINE THAT DOES NOT COUNT: the same comparison at
    the settled camera sat at 92.7% whatever the slack, which looked like a
    hole and is not. The two pictures are two separately loaded pages, and
    `fitToPane` fits each one to ITS OWN content -- a smaller mesh is framed
    differently, so the pixel counts were never comparable. The honest way to
    compare is one page with the switch thrown, which is what
    `window.cqOrder.farWall` exists for.

    AND THEN IT WAS BUILT PROPERLY AND MEASURED, AND IT CANNOT WORK. With the
    orientation taken from the winding instead of the middle, the body comes
    out clean -- the kites in the middle of the flank really do go. What is
    left is the OUTLINE, where faces run nearly edge-on and flicker between
    facing you and not, and dropping them shreds the rim into shards. Keeping
    the nearly-edge-on ones closes it, and the amount of slack needed was
    measured on ONE page with the switch thrown, which is the only fair
    comparison:

        slack (cosine)   faces kept   outline restored   flank roughness
        0.10                696          93.0%   shreds       1.014
        0.20                980          97.5%                0.897
        0.35              1,468         100.0%                0.894
        0.50              1,547         100.0%                0.892

    THERE IS NO VALUE THAT DOES BOTH. By the time the outline is whole again
    (0.35) it is keeping 1,468 of 1,824 faces -- barely culling at all -- and
    the flank is back to 0.894 against the 0.891 of the shape drawn whole.
    The kites ARE the far wall where it runs nearly edge-on, and that is
    exactly the band that must be kept for the outline to survive. The two
    requirements are the same faces.

    So back-face culling is not the answer and no tolerance makes it one.
    What is left to try is not geometry at all: the far wall is seen THROUGH
    the near one, so anything that changes how the two are blended -- rather
    than which of them exists -- is where to look next.

    AND THE ORDERING IS NOT IT EITHER, asked exactly rather than assumed. The
    sort above is approximate on purpose -- 4,096 buckets, two triangles in
    one bucket coming out either way round -- and near the outline the far
    wall is foreshortened, so many of its triangles crowd into few buckets.
    That is what an unstable order would look like. Replaced with a full
    comparison sort on ONE page, the flank came back at 0.886 against 0.886,
    and 0.886 again when it was switched back. Not the buckets.

    NOR IS IT HOW COARSE THE SHELL IS. At iccgamut's default the facets are
    4.50 degrees across; at -d 3 they are 1.43 and there are 14,412 of them
    instead of 1,824. Eight times the geometry:

        -d      faces    see-through 68%   solid 100%
        default  1,824        0.886           0.808
        6        4,462        0.912           0.808
        4        9,110        0.902           0.808
        3       14,412        0.844           0.813

    The solid column does not move at all, and the see-through one never
    comes down to it. Whatever this is, it is not facet size.

    WHAT IT IS: THE RENDERER'S SEE-THROUGH PATH ITSELF. Reported from the
    window in those words -- "as soon as transparency comes into play the
    triangles appear" -- and the opacity sweep agrees, on one shape, one
    camera, one crop:

        opacity     0.15  0.30  0.45  0.60  0.68  0.80  0.92  1.00
        layer step  .128  .210  .247  .240  .218  .160  .074  .000
        flank       .233  .445  .630  .800  .886 1.013 1.137  .808

    THE LAYER-COUNT EXPLANATION IS WRONG AND THIS IS WHAT KILLS IT. Inside
    the far wall's own horizon you look through two thicknesses of shell and
    outside it through one, and that step is biggest around half opacity --
    so wedges made of it would peak there. They do not. They climb all the
    way to 0.92, where the step has nearly gone, and then vanish in a single
    jump at solid. Reported from the window in exactly those terms: "when you
    increase the opacity step by step those triangles are not affected and
    only in the very last step they become totally solid like the rest".

    What matches every number is that the library draws a see-through surface
    down a different path from a solid one, and the artefact belongs to that
    path; its visibility simply tracks how bright the shape is, which is why
    it looks worst just below solid. It is also why an exact sort changes
    nothing: sorting TRIANGLES cannot fix blending that interleaves at the
    PIXEL level wherever triangles overlap in depth.

    SO THERE ARE THREE HONEST ANSWERS, and only the first two are ours:
    draw it solid; draw one layer instead of two (culling -- measured above,
    and it cannot be separated from the outline); or a renderer that composes
    transparency without depending on order, which this library does not
    offer.

    NOT DRAWING THE FAR WALL WAS THE ONLY CURE FOUND, AND IT IS NOT SHIPPABLE.
    It was built -- each face turned outward against the shape's own middle,
    the eye's position (not merely its direction) taken from the scene's
    `dataScale` and `glplot.bounds`, the pristine triangle list kept because
    handing the surface a short list leaves the trace holding that short list
    padded with zeros. At the settled camera it is right, and the count it
    keeps matches an independent reckoning exactly, 724 and 494 at two
    angles. Turned to a camera level with the top of the shape it TEARS: a
    band goes missing where the surface runs edge-on to the eye. A shape that
    comes apart as you turn it is worse than the wedges, so it is not in.
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
    # THE PATCHES THEMSELVES, so anything that wants to ask a further question
    # of them can. ``worst_patches`` holds the eight biggest and nothing else,
    # which is enough to name a culprit and not enough to say which colour
    # families moved -- and the family report needs every patch or its
    # averages describe the eight worst rather than the chart.
    #
    # These were being worked out and dropped on the floor, the same way
    # ``lab_b`` was before the direction view needed it. Keeping them costs
    # one reference each.
    lab_a: object = None       # (N, 3) where the first measurement put each
    lab_b: object = None       # (N, 3) where the second put the same patch
    deltas: object = None      # (N,) how far apart those two are, in dE2000

    #: WHICH WAY, not just how far. dE2000 is a MAGNITUDE and throws the
    #: direction away by construction, so a printer going lighter and one
    #: going darker by the same amount give an identical number -- and they
    #: are different faults wanting different cures.
    @property
    def moved(self):
        """(N, 3) how far each colour moved in L*, a* and b*, with its sign.

        Positive L* is lighter, positive a* is toward red, positive b* is
        toward yellow.
        """
        if self.lab_a is None or self.lab_b is None:
            return None
        return np.asarray(self.lab_b, float) - np.asarray(self.lab_a, float)


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
                 over_three=int((de > 3.0).sum()), worst_patches=worst,
                 lab_a=lab_a, lab_b=lab_b, deltas=de)


@dataclass(frozen=True)
class ProfileDrift(Drift):
    """How far two ICC profiles disagree, and under what conditions.

    Carries everything a measurement drift does, so the window can show either
    through the same box, plus the three things that are only true of profiles
    and that a reader has to be told before trusting the number.
    """
    steps: int = 0             # per channel, so steps**channels points
    channels: int = 0
    table_a: str = ""          # A2B1, A2B0 or matrix -- see icc_read
    table_b: str = ""
    device_space: str = ""     # RGB or CMYK
    # The points themselves come from Drift, so the picture and the table are
    # drawn from one set of numbers -- working them out twice is how a caption
    # ends up disagreeing with the cloud it sits under. They live up there
    # because a measurement pair needs them for exactly the same reasons.

    @property
    def comparable(self) -> bool:
        """Whether the two were read through the same kind of table.

        False means the figures describe two different questions rather than
        one difference, and the window must say so rather than print them
        plainly.
        """
        return self.table_a == self.table_b


def compare_profiles(path_a, path_b, *, steps: int = 9,
                     top: int = 8) -> ProfileDrift:
    """Colour-by-colour difference between two ICC profiles.

    THE QUESTION THIS ANSWERS, and the one it does not. Somebody with two
    profiles of the same scanner made years apart wants to know what has
    changed. Comparing the gamut SURFACES cannot tell them: two profiles can
    enclose almost the same shape and map the inside of it quite differently,
    and for an input profile the inside is nearly the whole profile. So this
    asks the only question that does answer it — feed both the same device
    values, and see where the two send them.

    It is the same idea as ``compare_measurements`` and deliberately returns
    the same shape, because to the reader it is the same question asked of a
    different kind of file. What differs is that no patch matching is needed:
    a grid is BUILT rather than found, so both profiles are asked about
    exactly the same colours by construction.

    WHAT IT DOES NOT MEASURE, and the help text has to say so: this is how far
    two CHARACTERISATIONS disagree, not how far a device drifted. A profile is
    a record of one day's measurements of one chart. If the chart has faded,
    or the two were built with different settings, that is in this number too,
    and no amount of arithmetic here can separate it out.

    Needs nothing installed: the profiles are read here, so this works on a
    machine with no ArgyllCMS at all.
    """
    import icc_read
    from gamutview import delta_e_2000

    head_a, head_b = icc_read.describe(path_a), icc_read.describe(path_b)
    space_a, space_b = head_a["space"], head_b["space"]
    if space_a != space_b:
        # REFUSED RATHER THAN ANSWERED. The grid is in device coordinates, so
        # "the same input" means nothing across two different device spaces --
        # 50% grey asked of an RGB profile and of a CMYK one are not the same
        # request, and pairing them would produce a confident figure
        # describing nothing at all.
        raise ValueError(
            f"These two profiles do not describe the same kind of device — "
            f"one is {space_a} and the other is {space_b}. The comparison "
            f"works by asking both of them for the same ink or light amounts, "
            f"and there is no such thing as the same amount across two "
            f"different kinds of device, so there is nothing to compare.")

    device_a, lab_a = icc_read.profile_to_lab(path_a, steps)
    device_b, lab_b = icc_read.profile_to_lab(path_b, steps)
    if device_a.shape != device_b.shape:
        # Should be impossible once the spaces match, since the grid is built
        # from the channel count -- but a silent mismatch here would pair
        # unrelated colours, so it is checked rather than assumed.
        raise ValueError(
            "These two profiles could not be asked about the same set of "
            "colours, so there is nothing to compare.")

    de = delta_e_2000(lab_a, lab_b)
    channels = device_a.shape[1]
    order = np.argsort(de)[::-1][:top]
    worst = [(_device_label(device_a[i], space_a), float(de[i]),
              lab_a[i].tolist(), lab_b[i].tolist())
             for i in (int(j) for j in order)]
    return ProfileDrift(
        matched=int(len(de)), total_a=int(len(de)), total_b=int(len(de)),
        worst=float(de.max()), average=float(de.mean()),
        rms=float(np.sqrt((de ** 2).mean())),
        over_one=int((de > 1.0).sum()), over_three=int((de > 3.0).sum()),
        worst_patches=worst, steps=int(steps), channels=int(channels),
        table_a=icc_read.which_table(path_a),
        table_b=icc_read.which_table(path_b), device_space=space_a,
        lab_a=lab_a, lab_b=lab_b, deltas=de)


def _device_label(values, space: str) -> str:
    """One grid point written the way the file's own units read.

    Percentages rather than 0-255, because a profile is asked in fractions and
    an ink amount is quoted in per cent everywhere else in this application.
    """
    names = "CMYK" if space == "CMYK" else "RGB"
    return " ".join(f"{n}{v * 100:.0f}" for n, v in zip(names, values))


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
    and how high it is, is asking a question about a room.

    ⚠ THE REACH IS NOT ONE NUMBER, AND THE COMMENT THAT SAID IT WAS COST BOTH
    OF THESE SLIDERS THEIR MEANING. It used to read: "The radius is fixed and
    large so only the DIRECTION matters." It is the other way round. The
    drawing library does not take this as a point in the room: it maps it
    through the inverse of the projection as a HOMOGENEOUS point, so as the
    radius grows the lamp converges on a projective point at infinity — the
    same limit from either sign — and ends up glued to the camera axis.
    Measured on a real paper, driving the page directly:

        the lamp above against the same lamp below, at reach    1: 229,586 px
                                                            at 2, 10, 100
                                                            and 2000:      0

    At the reach this used (2000) the two lamp sliders moved nothing at all:
    swinging the bearing right round at the height the window opens with gave
    0 px. With the upward reach brought back to 1 the same swing gives
    228,038 px, and with 500 sideways, 227,769.

    So the two directions get their own scales: far enough sideways to keep
    the bearing meaning a bearing, close enough vertically that up and down
    are different places rather than the same limit.
    """
    import math

    radians = math.radians(direction_deg)
    sideways, upwards = 500.0, 1.0
    lift = max(-1.0, min(1.0, height))
    flat = math.sqrt(max(0.0, 1.0 - lift * lift))
    return dict(x=sideways * flat * math.cos(radians),
                y=sideways * flat * math.sin(radians),
                z=upwards * lift)


#: Where the light hangs when nobody has moved it: overhead. At the same
#: scale as `light_position` above — a z of 2000 here is the same projective
#: limit, which is what made "overhead" and "underneath" the same picture.
_LIGHT_OVERHEAD = dict(x=0, y=0, z=1)


def _weld(points, colours, faces, sides=None):
    """Join vertices that sit in the same place and carry the same colour.

    A boundary built from the faces of the device cube repeats every point
    along the twelve edges where two faces meet -- on a real 1168-patch chart
    that is 27% of them. Two copies of a corner cannot share a normal, so the
    renderer shades each one on its own and lays a crease along every seam:
    the surface looks chipped and grainy where it is in fact continuous.

    This changes no geometry, no colour and no volume -- only which triangles
    agree about a corner. The dents stay: they are real, they are the whole
    point of following the measured boundary, and nothing here smooths them.

    *sides* keeps apart two corners that are in the same place for a reason --
    see :func:`_weld_order`.
    """
    keep, remap = _weld_order(points, colours, sides)
    if len(keep) == len(points):
        return points, colours, faces
    kept = np.asarray(keep)
    welded = ([colours[i] for i in kept] if isinstance(colours, list)
              else np.asarray(colours)[kept])
    return points[kept], welded, remap[np.asarray(faces)]


def _weld_order(points, colours, sides=None):
    """WHICH vertices a weld keeps, and where every old one now points.

    Split out of :func:`_weld` so that anything else needing to follow the
    same renumbering can do so by the SAME rule rather than by a second
    implementation of it. That matters more than it looks: a weld groups by
    the point AND its colour, so a mask welded on its own -- with the mask
    values standing in for the colours -- can group differently and come back
    a different length, lined up with nothing. Asking for the indices once
    and indexing everything with them cannot drift.

    *sides* IS WHAT KEEPS THE CUT SHARP, and leaving it out put the fault
    straight back into the one place it mattered most.

    `recut_where_they_part` deliberately makes two corners in the same place,
    one for each side of the boundary, so that no triangle straddles it. When
    the fade is applied here they carry different alphas, so their colours
    differ and this leaves them alone. But a SAVED PAGE is written at full
    strength and hands the reader the slider -- and at full strength the two
    copies are the same colour, so they welded back into one, every triangle
    along the boundary straddled it again, and the reader's slider drew the
    very gradient the re-cut exists to remove. Measured on the demo page: 361
    of 1,324 triangles. The picture on screen was right and the page somebody
    was sent was not, which is the worst way for this to be wrong.
    """
    keys, order, keep = [], {}, []
    if sides is None:
        sides = [None] * len(points)
    for point, colour, side in zip(points, colours, sides):
        keys.append((tuple(np.round(point, 6)),
                     colour if isinstance(colour, str)
                     else tuple(np.atleast_1d(np.round(colour, 6))),
                     None if side is None else bool(side)))
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

    ONE THING DOES CHANGE at the top of the slider, and it is not this
    function. A page that hands the reader the control is re-cut along the
    boundary first (`recut_where_they_part`), so a shape drawn as a WIRE CAGE
    gains wires: the extra triangle edges lie exactly along the curve where
    the two shapes cross. Measured on the demo page at full strength, 1,252
    pixels of 3,936,000 differ from the same page before the re-cut, and every
    one of them is on that curve. The surface itself is unchanged -- it is
    shaded smoothly, so more triangles covering the same shape draw the same
    picture -- and the volume and area are unchanged to seven figures.
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


def _solid_remainder(colours, alphas, faces, opacity):
    """The solid remainder of an extreme fade, handed back genuinely solid.

    Returns ``(colours, faces)``. Almost always it is today's pair exactly:
    the colours wrapped by :func:`_with_alpha`, the faces untouched. The one
    exception is a fade at its ENDS -- every vertex at alpha 0 or alpha 1,
    on a mesh whose own strength is 1 -- where the picture the reader is owed
    is not translucent at all: the faded part is invisible and the standing
    part is solid.

    Drawn the usual way that picture is wrong, and it was reported from a
    published page: "it is like i am looking through the remaining shape
    although the part is solid. i only set to 0% where they agree". Measured
    on that page (14, glossy paper against Adobe RGB, agreement at 0%): the
    remaining pieces differed from a genuinely opaque render of the same
    triangles by up to 4,062 pixels per view, sixteen views, every one of
    them showing a farther piece painted OVER a nearer solid one. The cause
    is the drawing path: one vertex below alpha 1 puts the whole mesh on the
    library's transparent path, which never writes the depth buffer, so
    "solid" pieces only occlude if the per-frame triangle sort gets every
    pixel right -- and a sort of triangles cannot promise that (see
    docs/THE-SEE-THROUGH-TRIANGLES.md).

    So at the ends the invisible triangles are REMOVED and the colours left
    plain: nothing on the transparent path, the depth buffer in charge, and
    the same sixteen views measured again at 0 wrongly-covered pixels. Any
    alpha strictly between 0 and 1 -- an intermediate slider, a triangle
    straddling the boundary on a mesh that was not re-cut, a shape strength
    below 1 -- keeps today's behaviour to the byte.

    The vertex array is NOT filtered: :func:`_weld` keeps every vertex
    whether or not a face still points at it, so the carried ``stand`` mask
    and the saved page's numbering stay exactly as they were.
    """
    faces = np.asarray(faces)
    if alphas is None:
        return colours, faces
    al = np.asarray(alphas, float)
    if opacity == 1 and len(faces):
        corners = al[faces]
        gone = (corners == 0).all(axis=1)
        kept = faces[~gone]
        if gone.any() and len(kept) and (al[kept] == 1).all():
            return colours, kept
    return _with_alpha(colours, al), faces


#: What a trace can carry that a change of DETAIL moves. Colours are named
#: separately because the field is `vertexcolor` on the trace and `c` here --
#: kept short because this list is sent across as JSON, once per drag step, for
#: a comparison that can run to nine thousand points.
_RESTYLE_FIELDS = ("x", "y", "z", "i", "j", "k")


def traces_for_restyle(figure):
    """EVERY trace of *figure*, in order, for a change that moves the vertices.

    Where :func:`surfaces_for_restyle` sends a shape's colours and triangles
    for a fade -- which leaves every point exactly where it was -- this sends
    the points as well, because a change of detail rebuilds the comparison
    from scratch and nothing about it stays put.

    IN ORDER, AND WITH THE NAMES, because the names are NOT unique: a cage
    drawn over sRGB is three traces all called "sRGB (outline)". Pushing by
    name would send one trace's points to all three. So the caller checks the
    page's whole ordered list of (name, type) against this one and pushes by
    position only if every single one matches -- position matching is
    dangerous exactly when nobody checked, and safe when somebody did.

    NOTHING IS ROUNDED. A shorter payload was measured -- two decimal places
    takes 2,467 kB down to 1,106 -- and refused, because these arrays have to
    be what a rebuilt page would have held, to the digit, or the picture
    changes under the reader when they let go. The transfer was never the
    cost: 1.9 MB reaches the window in 25 ms.
    """
    out = []
    for trace in figure.data:
        one = {"n": str(getattr(trace, "name", "") or ""),
               "t": getattr(trace, "type", None)}
        for field in _RESTYLE_FIELDS:
            got = getattr(trace, field, None)
            if got is None:
                continue
            if field in "xyz":
                one[field] = [None if v is None else float(v) for v in got]
            else:
                one[field] = [int(v) for v in got]
        colours = getattr(trace, "vertexcolor", None)
        # A SINGLE COLOUR IS NOT A LIST OF THEM -- see surfaces_for_restyle,
        # where a flat colour would have been sent letter by letter.
        if colours is not None and not isinstance(colours, str) \
                and len(colours):
            one["c"] = [str(c) for c in colours]
        out.append(one)
    return out


def frame_for_relayout(figure):
    """The caption and BOTH WHOLE AXES of a flat cross-section.

    A cut is drawn to FILL its frame, so moving it up or down changes the axes
    as well as the outlines -- at L* 30 the picture runs from -114.8 to 50.4
    across, and at L* 70 from -52.2 to 103.0. A push that sent the outlines
    alone would draw the new cut inside the old frame, which reads as the
    shape sliding sideways rather than the reader moving the cut. And the
    caption names the height, so it travels too or the picture and the
    sentence over it disagree.

    THE WHOLE AXIS, NOT ITS RANGE. Written as the two ranges and the caption
    -- which is what the axes visibly consist of -- three heights out of five
    matched a rebuild exactly and two were out by eleven thousand pixels. The
    picture said what the reasoning had missed: every GRIDLINE stood in a
    different place and every tick number with it, because the spacing between
    them is worked out per axis and is not implied by the range. The two that
    failed were the two whose spacing differed from the height the page was
    opened at; the three that passed had simply landed on the same spacing.

    That is the whole argument for measuring a picture in pixels rather than
    reasoning about what a change touches.
    """
    got = {}
    title = getattr(getattr(figure.layout, "title", None), "text", None)
    if title is not None:
        got["title.text"] = title
    for axis in ("xaxis", "yaxis"):
        span = getattr(getattr(figure.layout, axis, None), "range", None)
        if span is not None:
            got[f"{axis}.range"] = [float(v) for v in span]
    return got


def surfaces_for_restyle(figure):
    """Every drawn surface of *figure*, as a picture already on screen wants it.

    Keyed by the trace's own name, because a trace is found by name and never
    by position: matching by position once faded the wrong shape.

    WHY THIS LIVES HERE AND NOT IN THE WINDOW. The window pushes a fade into
    the scene it is already showing rather than writing six megabytes of page
    and loading it again, and what it pushes has to be what a rebuilt page
    would have held -- otherwise the live picture and the saved one drift
    apart, which is this project's oldest recurring fault. Taking both from
    `build_figure`'s own output is the only arrangement in which they cannot:
    there is no second implementation to go stale. The check that proves it,
    in pixels, is `scripts/audit_a_live_change_is_the_real_thing.py`.

    THE TRIANGLES TRAVEL, not only the colours. At either end of a fade the
    faces that would be invisible are dropped, so that what is left can go
    back on the opaque path -- see `_solid_remainder` -- and a push that sent
    colours alone would leave the reader a see-through shell where a rebuild
    gives them a solid one.
    """
    out = {}
    for trace in figure.data:
        if getattr(trace, "type", None) != "mesh3d":
            continue
        colours = getattr(trace, "vertexcolor", None)
        # A SINGLE COLOUR IS NOT A LIST OF THEM, and Python is happy to walk
        # a string one character at a time. A shape painted one flat colour
        # would have been handed over as its seven letters, and the surface
        # would have come out the colour of "#".
        if colours is None or isinstance(colours, str) or not len(colours):
            continue
        name = str(getattr(trace, "name", "") or "")
        if not name or trace.i is None:
            continue
        out[name] = {"c": [str(c) for c in colours],
                     "i": [int(v) for v in trace.i],
                     "j": [int(v) for v in trace.j],
                     "k": [int(v) for v in trace.k]}
    return out


def surfaces_of(gamuts):
    """One reusable containment test per shape, built once.

    Asking "is this colour inside that shape" needs the shape's surface
    prepared first, and preparing it is the expensive half. `outside_of` does
    that and throws it away, which is right for one question asked once and
    wrong for a redraw that asks four questions of two shapes.

    Measured on the demo pair: building a faded scene prepared **four
    surfaces where two would do** -- once to decide which vertices stand out,
    and again to find where the boundary crosses each edge -- at about 10 ms
    each.

    A shape too small to enclose anything gets ``None``, and every caller
    treats that as "agrees with nothing", which is what the containment test
    would have raised about.
    """
    from gamutview import enclosure

    out = []
    for _name, g in gamuts:
        try:
            out.append(enclosure(g))
        except Exception:          # noqa: BLE001 — see disagreeing_vertices
            out.append(None)
    return out


def disagreeing_vertices(gamuts, skins=None):
    """Which vertices of each shape lie somewhere the others do not reach.

    The same question `agreement_masks` answers for triangles, kept at the
    resolution it is actually decided at. A vertex is either outside the
    other shapes or it is not; nothing about a neighbouring triangle changes
    that.

    WHY THIS EXISTS. The surface is faded with an alpha per vertex, and that
    alpha used to be worked out by taking the per-TRIANGLE answer and marking
    every vertex those triangles touch. That dilates the disagreement by a
    whole ring: a vertex sitting comfortably inside the other gamut was
    painted as standing out because one triangle beside it did.

    Measured on the demo pair against Adobe RGB: 239 vertices are genuinely
    outside, 335 were painted as though they were -- **96 of them, a seventh
    of the whole surface, drawn as disagreement where the paper and the space
    agree**. Every error went the same way. Reported as "parts of where they
    agree do not become transparent", which is exactly what it was.

    *skins* is an optional list of prepared surfaces, one per shape, from
    :func:`surfaces_of` -- so a caller that already has them, or that needs
    them again afterwards, does not pay to build them twice.
    """
    if skins is None:
        skins = surfaces_of(gamuts)

    out = []
    for i, (_name, a) in enumerate(gamuts):
        others = [s for j, s in enumerate(skins) if j != i]
        if not others:
            # Nothing to agree with, so all of it stands -- the same choice
            # agreement_masks makes, and for the same reason.
            out.append(np.ones(len(a.vertices), bool))
            continue
        stands = np.zeros(len(a.vertices), bool)
        for skin in others:
            if skin is None:       # too small to contain anything
                stands |= True
            else:
                stands |= ~skin.contains(a.vertices)
        out.append(stands)
    return out


def recut_where_they_part(gamuts, lost=None):
    """Re-cut every shape so the fade has an edge instead of a slope.

    Returns ``(gamuts, per_triangle, per_vertex, lost)`` -- the same shapes,
    re-triangulated so that no triangle straddles the boundary between where
    they agree and where they do not, together with the masks that go with
    the new meshes.

    THE FADE IS AN ALPHA PER VERTEX, so a triangle with two corners agreeing
    and one not has that difference painted smoothly across its whole width.
    "Does this colour fall outside the other shape?" has two answers and no
    third, and it was being drawn as a slope between them.

    Measured on the demo pair: of the glossy paper's 978 triangles, **173
    straddled the boundary -- a fifth of the surface, averaging 16.5 Lab units
    across**. So turning the agreement down did not open a clean hole where
    the two shapes part company; it thinned a wide band around it, and the
    parts that plainly agreed never went away. Reported as "parts of where
    they agree do not become transparent -- the cut should be more straight",
    and it should.

    After this, every triangle is one flat colour at one flat alpha and the
    edge lies exactly where the two surfaces cross. The shape itself does not
    move: the new corners sit on the straight edges between the old ones, and
    the volume and surface area are unchanged to seven figures.

    A SHAPE SHOWING ITS LOST COLOURS IS RE-CUT ONLY WHEN THAT MASK ASKS THE
    SAME QUESTION. "What can this paper no longer reach" is a second boolean
    per vertex, measured against one chosen shape; the fade is measured
    against ALL the others. With two shapes on screen -- the ordinary case,
    and every saved page -- those are the same question and the new corners
    inherit the answer exactly. With a chart, a second paper AND a reference
    they are not, and there is no way to answer for a new corner without the
    test that made the mask. Rather than guess, that shape keeps its old
    mesh: the marking stays right and the fade keeps its slope.
    """
    from gamutview import (Gamut, sharpen_where_they_part,
                           split_at_crossing)

    # ONE SURFACE PER SHAPE, PREPARED ONCE. Deciding which vertices stand out
    # and finding where the boundary crosses an edge are the same question
    # asked of the same shapes, and each used to prepare its own copy -- four
    # surfaces per redraw where two will do, at about 10 ms each.
    skins = surfaces_of(gamuts)
    stands = disagreeing_vertices(gamuts, skins)
    out_g, out_faces, out_stands = [], [], []
    out_lost = None if lost is None else []
    for i, (name, g) in enumerate(gamuts):
        mine = stands[i]
        marked = lost[i] if lost is not None and i < len(lost) else None
        marked_after = None
        others = [s for j, s in enumerate(skins) if j != i and s is not None]
        same_question = marked is None or (
            len(marked) == len(mine) and np.array_equal(np.asarray(marked, bool),
                                                        mine))
        recut = None
        # THE MARKING GETS ITS OWN CUT WHEN IT ASKS ITS OWN QUESTION.
        #
        # "What can this paper no longer reach" is measured against ONE chosen
        # shape; the fade is measured against ALL the others. With two shapes
        # they are the same question and one cut serves both. With two papers
        # AND a reference — reported from the window as "the coloured part
        # should have a clearer line instead this zig zag" — they are not, and
        # this used to give up and leave that shape its old mesh. Measured on
        # his picture: 118 of the paper's 414 triangles have corners on both
        # sides of the marking, and each must be painted wholly red or wholly
        # grey. That staircase IS the zig-zag.
        #
        # Rather than guess a new corner's marking, the shape doing the
        # judging is FOUND — it is one of the shapes on screen, and the mask
        # is exactly `~contains` of one of them — and then the mesh is cut a
        # second time along THAT boundary, with the same test that made the
        # mask answering for every new corner. Exact, not interpolated.
        judge = None
        if marked is not None and not same_question:
            want = np.asarray(marked, bool)
            for j, skin in enumerate(skins):
                if j == i or skin is None:
                    continue
                try:
                    if np.array_equal(~skin.contains(np.asarray(g.vertices)),
                                      want):
                        judge = skin
                        break
                except Exception:      # noqa: BLE001 — a shape that cannot
                    continue           # answer is simply not the judge
        if len(others) == len(gamuts) - 1 and others and (same_question
                                                          or judge is not None):
            try:
                def outside_them_all(points, others=others):
                    beyond = np.zeros(len(points), bool)
                    for skin in others:
                        beyond |= ~skin.contains(points)
                    return beyond

                # FINE ENOUGH TO SEE THE BOUNDARY FIRST. The cut below
                # only asks each triangle's CORNERS, so it misses a shape
                # bulging through the middle of a facet, and between two
                # corners of the seam it draws a straight line where the real
                # crossing bends. Measured against sRGB on the demo paper:
                # 29.8% of the seam's length was more than 1 Lab from where
                # the two shapes actually cross, the worst of it 14.64 Lab,
                # and a negative gap means the piece was drawn STANDING over
                # ground it does not reach. Sharpened first: 1.8% and 1.01
                # Lab, which is under what an eye can find.
                ready = sharpen_where_they_part(g.vertices, g.faces, g.colors,
                                                mine, outside_them_all)
                recut = split_at_crossing(ready[0], ready[1], ready[2],
                                          ready[3], outside_them_all)
                if judge is not None:
                    # AND AGAIN ALONG THE MARKING'S OWN BOUNDARY. The first
                    # cut follows where this shape parts from the others; the
                    # marking parts from one shape somewhere else entirely,
                    # and a corner on the first curve says nothing about the
                    # second.
                    v1, f1, c1, s1 = recut

                    def out_of_reach(points, skin=judge):
                        return ~skin.contains(points)

                    v2, f2, c2, m2 = split_at_crossing(
                        v1, f1, c1, out_of_reach(np.asarray(v1)),
                        out_of_reach)
                    # THE FADE'S ANSWER FOR THE NEW CORNERS, by the same test
                    # that gave it to the old ones — never interpolated.
                    recut = (v2, f2, c2, outside_them_all(np.asarray(v2)))
                    marked_after = m2
            except Exception:          # noqa: BLE001 — a shape too small to
                # enclose anything cannot be cut along its boundary either,
                # and the picture is left exactly as it was.
                recut = None
        if recut is None:
            out_g.append((name, g))
            out_stands.append(mine)
            faces = np.asarray(g.faces)
            out_faces.append(~(mine[faces[:, 0]] & mine[faces[:, 1]]
                               & mine[faces[:, 2]]) if len(faces)
                             else np.zeros(0, bool))
            if out_lost is not None:
                out_lost.append(marked)
            continue
        v2, f2, c2, s2 = recut
        out_g.append((name, Gamut(vertices=v2, faces=f2, colors=c2,
                                  volume=g.volume, space=g.space, mode=g.mode)))
        out_stands.append(s2)
        # EVERY TRIANGLE IS ONE-SIDED NOW, so one corner answers for it and
        # the per-triangle mask cannot disagree with the per-vertex one.
        out_faces.append(s2[f2[:, 0]] if len(f2) else np.zeros(0, bool))
        if out_lost is not None:
            # WHERE THE MARKING WAS CUT ON ITS OWN, it carries its own answer
            # rather than the fade's — they are different questions and the
            # whole point of the second cut is that they can differ.
            out_lost.append(None if marked is None
                            else (marked_after if judge is not None else s2))
    return out_g, out_faces, out_stands, out_lost


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
    # would line up with nothing. A fade at its ENDS leaves the colours plain
    # and removes the invisible triangles instead -- see _solid_remainder.
    picked = (np.asarray(gamut.faces)[np.asarray(only)] if only is not None
              else gamut.faces)
    if alphas is not None:
        colours, picked = _solid_remainder(colours, alphas, picked, opacity)
    # THE MASK IS WELDED WITH THE COLOURS, not alongside them.
    #
    # A saved page has to be able to work this fade out for itself, which
    # means carrying which vertices stand out -- and it must be numbered the
    # way the drawn vertices are, not the way the gamut's are. Welding drops
    # duplicates and renumbers what is left, so the mask is put through the
    # very same call rather than through a second one that could disagree
    # with it. _weld indexes its middle argument and does not care what is in
    # it, which is what makes this safe.
    # THE SIDE IS PART OF WHAT MAKES A CORNER ITSELF. Two corners in the same
    # place on opposite sides of the boundary are two corners, and welding
    # them cost the saved page its sharp edge -- see `_weld_order`.
    carried = None
    if stand is not None:
        keep, _remap = _weld_order(v, colours, stand)
        carried = "".join("1" if stand[i] else "0" for i in keep)
    v, colours, faces = _weld(v, colours, picked, stand)
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        vertexcolor=colours, opacity=opacity, name=name, showlegend=False,
        legendgroup=name,
        meta=dict(_is_a_shell(only),
                  **({"stand": carried} if carried is not None else {})),
        # Only the legend key uses this; vertexcolor paints the surface.
        color=_legend_swatch(chosen if chosen is not None else gamut.colors,
                             page),
        # A SIMPLE SKIN IS LIT FACET BY FACET — see the note in `_mesh_lost`,
        # which paints the other half of the same shape and must agree.
        flatshading=getattr(gamut, "mode", "") == "hull", hoverinfo="name",
        lighting=_lighting(depth, opacity),
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
        # LIT FACET BY FACET, for the same reason the simple skin over a shape
        # is. This is a hull over a cloud of measured patches, and a hull over
        # unevenly spread points is full of needles — MEASURED on the
        # verification chart placed through a real profile: 25 of its 92
        # triangles have a longest edge more than eight times their own width,
        # the worst 355 times. Smooth shading averages the light across every
        # facet meeting at a corner, and over a needle that average smears
        # into a streak, which was reported from the window of the other
        # hull: "this one looks scattered".
        hoverinfo="name", flatshading=True,
        lighting=_lighting(depth, opacity),
        lightposition=light or _LIGHT_OVERHEAD,
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


#: Where the eye is told to stop caring, in ΔE2000. Below 1 nobody can see a
#: difference at all, so painting those as though they were something is a
#: picture that cries wolf; above 5 the scale would spend most of its range on
#: a handful of outliers and flatten everything a reader could act on.
DRIFT_FLOOR = 1.0
DRIFT_CEILING = 5.0

#: The scale, and it is chosen rather than inherited. Plotly's default runs
#: dark blue to yellow, which reads as a colour in its own right and fights a
#: picture whose whole subject is colour. This runs from the page's own quiet
#: grey through amber to the same red the rest of the application uses for
#: "out of reach", so "worse" reads as "hotter" without a key.
DRIFT_SCALE = [[0.0, "#4a4f5a"], [0.25, "#6d7280"], [0.5, "#c9a227"],
               [0.75, "#e8712f"], [1.0, "#ff4573"]]

#: WHICH WAY IT WENT, on a scale that runs both ways from nothing.
#:
#: A SECOND SCALE RATHER THAN THE SAME ONE, because these answer a different
#: kind of question. The scale above is a magnitude: it starts at "no
#: difference" and gets hotter. A direction has a middle -- no change -- and
#: two opposite ends, and drawing signed data on a one-ended ramp is how a
#: reader comes to believe that "more blue" means "worse".
#:
#: TEAL TO ORANGE, DELIBERATELY NOT THE AXIS'S OWN COLOURS. Painting the
#: redder-or-greener view in red and green reads beautifully and is a trap:
#: the dots would be red and green in a picture whose subject IS colour, and
#: somebody would take the colour of a dot for the colour it represents. One
#: neutral pair for all three views means the key has to be read once, and it
#: cannot be mistaken for the thing it describes. It is also safe for the
#: commonest colour blindness, which red-green is not.
DIRECTION_SCALE = [[0.0, "#1b7f79"], [0.25, "#63b0aa"], [0.5, "#5a5f6b"],
                   [0.75, "#e39b53"], [1.0, "#d1671a"]]

#: The three questions a direction can answer, and the words for each end.
#: Keyed by the Lab axis they read, in the order L*, a*, b*.
DIRECTIONS = {
    "L": ("lighter or darker", "darker", "lighter", 0),
    "a": ("redder or greener", "greener", "redder", 1),
    "b": ("warmer or cooler", "cooler (blue)", "warmer (yellow)", 2),
}

#: How far, in Lab units, the direction scale runs to at each end. Fixed for
#: the same reason the magnitude ceiling is: two pictures of two different
#: pairs are only worth putting side by side if the same colour means the
#: same amount in both. Five is the round number just above the dE ceiling
#: the magnitude view already uses.
DIRECTION_LIMIT = 5.0


def hidden_below(deltas, hide_below: float):
    """Which colours to leave out, and the note that must travel with them.

    ONE NUMBER MEANING ONE THING. The threshold is always ΔE2000 between the
    two, in every view -- not the axis value the direction view happens to be
    painted by. A reader who sets "hide anything under 2" and then switches
    from how-far to which-way must not find a different set of dots left.

    A PICTURE WITH THINGS TAKEN OUT OF IT HAS TO SAY SO. Somebody sent a saved
    page showing eleven dots cannot tell whether the printer is nearly perfect
    or whether seven hundred were hidden. So this returns the sentence as well
    as the mask, and the callers put it where it cannot be missed.
    """
    import numpy as _np

    deltas = _np.asarray(deltas, dtype=float)
    if not hide_below:
        return _np.ones(deltas.shape, bool), ""
    keep = deltas >= hide_below
    gone = int((~keep).sum())
    if not gone:
        return keep, ""
    total = int(deltas.size)
    return keep, (f"{gone} of {total} colours moved by less than ΔE "
                  f"{hide_below:.1f} and are not drawn.")


def drift_direction(lab, moved, name: str, axis: str = "L",
                    space: str = "lab", limit: float = DIRECTION_LIMIT,
                    by_family: bool = False, deltas=None,
                    hide_below: float = 0.0):
    """Which WAY each colour moved, along one axis of Lab, with its sign.

    THE NUMBER THE MAGNITUDE VIEW THROWS AWAY. ΔE2000 is a distance, so a
    printer drifting lighter and one drifting darker by the same amount give
    the same figure and the same cloud -- and they are different faults with
    different cures. This asks the question the distance cannot: not how far,
    but which way.

    ONE AXIS AT A TIME, rather than the whole vector at once. Three arrows in
    a cube is a thicket at 729 points, and a hue wheel would mislead the
    moment somebody read a dot's colour as the colour it stands for. Asked one
    question at a time -- has it got lighter, has it gone warmer, has it gone
    redder -- each picture has an answer somebody can act on.

    Drawn at profile A's positions, like the magnitude view, so the two can be
    switched between without anything moving.
    """
    import numpy as _np
    import plotly.graph_objects as go

    # WHICH FAMILY EACH DOT IS HEADING FOR, which is not an axis at all. The
    # three axes ask "how much lighter, redder, warmer"; this asks where the
    # colour is going, and answers in the colour of the place. It rides in on
    # the same argument because it takes the same input -- the movement of
    # every point -- and because a reader picks between them in one chooser.
    if axis == "toward":
        lab = _np.asarray(lab, dtype=float)
        moved = _np.asarray(moved, dtype=float)
        de = (_np.asarray(deltas, float) if deltas is not None
              else _np.linalg.norm(moved, axis=1))
        if hide_below:
            keep, _said = hidden_below(de, hide_below)
            lab, moved, de = lab[keep], moved[keep], de[keep]
        x, y, z = lab[:, 1], lab[:, 2], lab[:, 0]
        if space == "rgb":
            x, y, z = lab[:, 0], lab[:, 1], lab[:, 2]
        # SIZED BY HOW FAR IT WENT, the same rule as every other drift view,
        # so the eye is drawn to the colours that moved rather than to
        # whichever destination happens to have the loudest swatch.
        sizes = _np.where(de < 1.0, 2.0, 4.0 + 3.0 * _np.clip(
            (de - 1.0) / max(limit - 1.0, 1e-9), 0.0, 1.0))
        return _split_by_destination(lab, lab + moved, x, y, z, sizes, de)
    if axis not in DIRECTIONS:
        raise ValueError(
            f"{axis!r} is not one of the directions this can draw; "
            f"choose from {', '.join(sorted(DIRECTIONS))}")
    lab = _np.asarray(lab, dtype=float)
    moved = _np.asarray(moved, dtype=float)
    if moved.ndim != 2 or moved.shape[0] != lab.shape[0]:
        raise ValueError("every point needs one movement, in three parts")
    asks, less, more, column = DIRECTIONS[axis]
    values = moved[:, column]

    x, y, z = lab[:, 1], lab[:, 2], lab[:, 0]
    if space == "rgb":
        x, y, z = lab[:, 0], lab[:, 1], lab[:, 2]

    # SIZED BY HOW FAR IT WENT, EITHER WAY, so the eye is drawn to the places
    # that moved rather than to whichever end of the scale happens to be
    # darker. A point that barely moved is small and grey whichever way it
    # went, which is the truth about it.
    size = _np.abs(values)
    quiet = size < 1.0
    sizes = _np.where(quiet, 2.0, 4.0 + 3.0 * _np.clip(
        (size - 1.0) / max(limit - 1.0, 1e-9), 0.0, 1.0))

    # HIDDEN BY dE2000, NOT BY THIS AXIS. A colour can move a long way and
    # barely change in b*, so thresholding on the painted value would leave a
    # different set of dots in each of the three direction views -- and the
    # reader would reasonably read that as the data changing.
    if hide_below:
        if deltas is None:
            raise ValueError(
                "hiding by ΔE needs the ΔE values; this was given only the "
                "movement, and thresholding on one axis would mean something "
                "different in each view")
        keep, _said = hidden_below(deltas, hide_below)
        lab = lab[keep]
        x, y, z = x[keep], y[keep], z[keep]
        values, sizes = values[keep], sizes[keep]
        # AND THE ΔE ITSELF, which travels with every dot so a saved page can
        # hide by it. Left unfiltered it stayed the full length while
        # everything beside it shrank, and pairing the two raised on the spot.
        deltas = _np.asarray(deltas, float)[keep]

    if by_family:
        return _split_by_family(
            lab, x, y, z, values, sizes, limit,
            "%{customdata:+.2f} " + axis + "*", DIRECTION_SCALE,
            -limit, limit,
            dict(title=dict(text=asks, side="right"),
                 thickness=12, len=0.78, x=1.02,
                 tickvals=[-limit, -1.0, 0.0, 1.0, limit],
                 ticktext=[f"{limit:.0f} {less}", f"1 {less}",
                           "no change", f"1 {more}", f"{limit:.0f} {more}"]),
            deltas=deltas)

    return [go.Scatter3d(
        x=x, y=y, z=z, mode="markers", name=name,
        customdata=_pairs(values, deltas),
        hovertemplate=("%{customdata[0]:+.2f} " if deltas is not None
                       else "%{customdata:+.2f} ") + axis + "*<extra></extra>",
        marker=dict(
            size=sizes, color=values, colorscale=DIRECTION_SCALE,
            cmin=-limit, cmax=limit, opacity=0.85,
            colorbar=dict(
                title=dict(text=asks, side="right"),
                # LONGER THAN THE MAGNITUDE KEY, because this one has five
                # marks and three of them sit within a fifth of the middle:
                # at 0.55 of the height, "1 cooler", "no change" and "1
                # warmer" were printed almost on top of each other. Seen in
                # the screenshot of the feature, not reasoned about.
                thickness=12, len=0.78, x=1.02,
                tickvals=[-limit, -1.0, 0.0, 1.0, limit],
                ticktext=[f"{limit:.0f} {less}", f"1 {less}",
                          "no change", f"1 {more}", f"{limit:.0f} {more}"])))]


def _drift_extent(lab, space: str):
    """The box that holds ALL the colours, whichever of them are switched on.

    Returned as (x range, y range, z range) in the order the scene draws them,
    with a little air so nothing sits against a wall.

    THE POINT IS THAT IT DOES NOT DEPEND ON WHAT IS VISIBLE. Worked out once
    from every colour, it is the same box with one family showing as with all
    seven -- which is what makes "where does this family sit" a question the
    picture can answer. Left to itself the drawing library fits the box to
    whatever is switched on, so every family fills the frame and they all look
    alike.
    """
    import numpy as _np

    lab = _np.asarray(lab, dtype=float)
    if space == "rgb":
        cols = (0, 1, 2)
    else:
        cols = (1, 2, 0)          # a* across, b* deep, L* up
    out = []
    for c in cols:
        lo, hi = float(lab[:, c].min()), float(lab[:, c].max())
        pad = max((hi - lo) * 0.05, 1.0)
        out.append([lo - pad, hi + pad])
    return out


def colour_axis_for(which=None, ceiling: float = DRIFT_CEILING,
                    limit: float = DIRECTION_LIMIT) -> dict:
    """The colour key as a property of the SCENE rather than of any trace.

    WHY THIS IS NOT ON THE TRACES. Split into families, the key used to hang
    on whichever family happened to be drawn first -- which is what "draw the
    bar once" naturally means, and is wrong. Switching that one family off
    took the whole ΔE scale off the page and left the rest of the dots painted
    in colours with nothing to read them against. Hiding any OTHER family
    looked perfectly fine, so a check that tried one would have passed.

    Owned by the layout, the key cannot be switched off by anything, and every
    family is guaranteed to share one scale rather than merely being handed
    matching limits.
    """
    if which:
        asks, less, more, _column = DIRECTIONS[which]
        return dict(
            colorscale=DIRECTION_SCALE, cmin=-limit, cmax=limit,
            colorbar=dict(
                title=dict(text=asks, side="right"),
                thickness=12, len=0.78, x=1.02,
                tickvals=[-limit, -1.0, 0.0, 1.0, limit],
                ticktext=[f"{limit:.0f} {less}", f"1 {less}", "no change",
                          f"1 {more}", f"{limit:.0f} {more}"]))
    return dict(colorscale=DRIFT_SCALE, cmin=0.0, cmax=ceiling,
                colorbar=_drift_key(ceiling))


def _drift_key(ceiling):
    """The colour key the distance view uses, in one place."""
    return dict(title=dict(text="ΔE2000", side="right"),
                thickness=12, len=0.55, x=1.02,
                tickvals=[0, 1, 3, 5],
                ticktext=["0 — same", "1 — invisible", "3 — plain",
                          "5+ — obvious"])


def _pairs(values, deltas, pick=None):
    """[painted value, ΔE] per point, or just the value when no ΔE is known.

    Two columns rather than one so a saved page can hide dots by how far they
    really moved, whichever way the picture happens to be painted.
    """
    import numpy as _np

    values = _np.asarray(values, float)
    if deltas is None:
        return values
    deltas = _np.asarray(deltas, float)
    if pick is not None:
        deltas = deltas[pick]
    return _np.column_stack([values, deltas])


def _split_by_family(lab, x, y, z, values, sizes, ceiling, hover, scale,
                     cmin, cmax, key, deltas=None):
    """One trace per colour family instead of one for the lot.

    WHY THIS IS WORTH SEVEN TRACES WHERE THE REST OF THIS FILE FOUGHT TO GET
    DOWN TO ONE. The cage went from 296 traces to one because 296 named groups
    are not information -- nobody wants to switch off "the 141st edge". Seven
    families ARE the information: they are the same seven the written report
    is about, so splitting on them turns the legend into a filter that costs
    no new code at all. Click "blues" and the blues go; click again and they
    come back. That works in the window, in a saved page, offline, on a phone,
    because it is the drawing library's own behaviour rather than anything of
    ours.

    THE COUNT IS IN THE NAME for the same reason it is in every sentence: a
    family of eleven and a family of a hundred and thirty-seven look identical
    once they are dots, and the number is the only thing that says how much
    of the picture you are looking at.

    ONE KEY, NOT SEVEN. Every trace shares the fixed scale, and only the first
    draws the colour bar -- otherwise the page would carry seven identical
    bars stacked down the side.
    """
    import plotly.graph_objects as go

    from gamutview import HUE_FAMILIES, which_family

    mine = which_family(lab)
    order = [n for n, _c in HUE_FAMILIES] + ["greys"]
    out, drawn_key = [], False
    for family in order:
        pick = mine == family
        if not pick.any():
            # NOT AN EMPTY TRACE. A legend entry that switches nothing on or
            # off is a control that does nothing, and this file already holds
            # that a button which cannot act is worse than a missing one.
            continue
        count = int(pick.sum())
        out.append(go.Scatter3d(
            x=x[pick], y=y[pick], z=z[pick], mode="markers",
            name=f"{family} — {count}",
            # NO LEGEND GROUP, AND THAT IS A CORRECTION OF MY OWN MISTAKE.
            #
            # I put these under a heading -- "Where they disagree, by colour
            # family" -- so the key would not read as one flat list mixing
            # two kinds of switch. It cost two real faults to fix a worry
            # nobody had reported:
            #
            #   * a grouped legend toggles as a GROUP by default, so clicking
            #     "blues" hid all seven families at once. The filter, which is
            #     the entire reason for splitting the cloud, stopped working.
            #   * grouped entries stack in a column instead of flowing across,
            #     so the key grew to 564x163px and ate the picture's room.
            #
            # Both were reported from the published page. The names carry the
            # distinction on their own -- "reds — 137" does not read like
            # "printer-2019" -- and a flat legend flows horizontally and
            # toggles one entry at a time, which is what it is for.
            # THE PAINTED VALUE AND THE ΔE, side by side. The saved page's
            # threshold has to know how far each dot moved, and in the
            # direction views the painted value is one axis of the movement
            # rather than its size -- so carrying only that would give the
            # page a slider meaning something different in each view.
            customdata=_pairs(values[pick], deltas, pick),
            hovertemplate=(hover.replace("customdata:", "customdata[0]:")
                           if deltas is not None else hover)
            + f"<extra>{family}</extra>",
            marker=dict(
                # THE KEY BELONGS TO THE PICTURE, NOT TO ANY ONE FAMILY.
                # Hung on the first trace -- which is what "draw the bar once"
                # naturally means -- it is switched off with that family, so
                # hiding the reds took the ΔE scale off the page and left the
                # remaining dots painted in colours with nothing to read them
                # against. Basti hit it on the published page.
                #
                # A layout colour axis is owned by the scene instead, so every
                # family points at the same one and none of them can take it
                # away. It also guarantees they share a scale rather than
                # merely being given equal limits.
                size=sizes[pick], color=values[pick],
                coloraxis="coloraxis", opacity=0.85)))
        drawn_key = True
    return out


#: THE SWATCH FOR EACH DESTINATION, worked out rather than picked by eye.
#: Every family centre is drawn at one lightness and converted through the
#: same D50 path the shapes themselves use, so the yellow in the key is the
#: hue the word "yellows" actually means in this application rather than a
#: designer's idea of yellow.
#:
#: ONE LIGHTNESS FOR ALL SIX, because only the HUE is being shown. Letting
#: each swatch keep its own natural lightness would make the yellows shout and
#: the blues disappear, which is a fact about human vision and not about the
#: printer being looked at.
#:
#: AND AS MUCH CHROMA AS sRGB WILL HOLD AT THAT HUE, found per family rather
#: than fixed. A single chroma for all six is limited by the worst of them:
#: measured, a flat C* 45 put the reds at rgb(215,110,147) and the magentas at
#: rgb(196,117,185) -- two pinks a reader has to compare rather than
#: recognise. Pushing each hue to the edge of what the screen can show keeps
#: every one of them the true hue and as far from its neighbours as the screen
#: allows. The lightness stays fixed, so nothing is traded away except the
#: part that was never being shown.
_DESTINATION_LIGHT = 60.0

#: A colour that has not moved far enough for its direction to mean anything
#: is drawn in this instead -- the same neutral the rest of the application
#: uses for "nothing to see here". It must not read as a seventh family.
_GOING_NOWHERE = "rgb(120,124,132)"


def destination_colours(families=None):
    """One sRGB swatch per family, by hue, for the "heading for" view."""
    import numpy as np

    from gamutview import HUE_FAMILIES, lab_to_xyz, xyz_to_srgb

    families = families or HUE_FAMILIES
    out = {}
    for name, centre in families:
        rad = np.radians(centre)

        def at(chroma, rad=rad):
            lab = np.array([[_DESTINATION_LIGHT,
                             chroma * np.cos(rad), chroma * np.sin(rad)]])
            return xyz_to_srgb(lab_to_xyz(lab), clip=False)[0]

        # HOW MUCH CHROMA THIS HUE WILL TAKE, by halving. Twenty steps settles
        # it to a hundredth of a unit, which is far finer than a screen can
        # show and costs nothing worth measuring.
        low, high = 0.0, 130.0
        for _ in range(20):
            mid = (low + high) / 2
            rgb = at(mid)
            if rgb.min() < 0.0 or rgb.max() > 1.0:
                high = mid
            else:
                low = mid
        rgb = np.clip(at(low), 0.0, 1.0)
        out[name] = "rgb({},{},{})".format(*(int(round(v * 255)) for v in rgb))
    return out


def _split_by_destination(lab_a, lab_b, x, y, z, sizes, deltas):
    """One trace per family the colours are HEADING FOR.

    WHY THIS IS WORTH A VIEW OF ITS OWN. "How far it moved" is a distance and
    cannot say which way; splitting by the family a colour is IN says where
    the movement is. Neither answers the question somebody actually asks out
    loud, which is "what are my greys going TO". This does, dot by dot, in the
    colour of the place each one is heading.

    THE QUIET ONES ARE DRAWN AND NOT COLOURED, in one group of their own that
    says so. Leaving them out would put holes in the cloud and invite the
    reading that something is missing there; colouring them would claim a
    direction that is arithmetic on instrument noise. See
    gamutview.heading_for, which decides which is which and is shared with the
    written report so the picture and the sentences cannot disagree.
    """
    import numpy as np
    import plotly.graph_objects as go

    from gamutview import HUE_FAMILIES, heading_for

    going = heading_for(lab_a, lab_b)
    swatches = destination_colours()
    out = []
    for family, _centre in HUE_FAMILIES:
        pick = np.array([g == family for g in going])
        if not pick.any():
            continue
        out.append(go.Scatter3d(
            x=x[pick], y=y[pick], z=z[pick], mode="markers",
            name=f"toward the {family} — {int(pick.sum())}",
            customdata=_pairs(deltas[pick], deltas[pick]),
            hovertemplate=("heading for the " + family
                           + ", ΔE %{customdata[0]:.2f}<extra></extra>"),
            marker=dict(size=sizes[pick], color=swatches[family],
                        opacity=0.9, line=dict(width=0)),
            showlegend=True))
    quiet = np.array([not g for g in going])
    if quiet.any():
        out.append(go.Scatter3d(
            x=x[quiet], y=y[quiet], z=z[quiet], mode="markers",
            name=f"not heading anywhere — {int(quiet.sum())}",
            customdata=_pairs(deltas[quiet], deltas[quiet]),
            hovertemplate=("moved ΔE %{customdata[0]:.2f}, too little to say "
                           "where<extra></extra>"),
            marker=dict(size=sizes[quiet], color=_GOING_NOWHERE,
                        opacity=0.55, line=dict(width=0)),
            showlegend=True))
    return out


def drift_cloud(lab, deltas, name: str, space: str = "lab",
                floor: float = DRIFT_FLOOR, ceiling: float = DRIFT_CEILING,
                by_family: bool = False, hide_below: float = 0.0):
    """Where two profiles disagree, drawn where the disagreement happens.

    THE NUMBERS ALONE DO NOT SAY WHERE. "Biggest difference ΔE 10.2, average
    5.1" is true and nearly useless on its own: it cannot tell somebody
    whether their scanner has drifted evenly, which is a calibration matter,
    or only in the deep blues, which is a different problem with a different
    cause. The same figures come out of both, and they want opposite actions.

    So each colour is drawn at the place profile A puts it, painted by how far
    profile B sends it instead. A cloud that is grey everywhere but hot in one
    lobe is a picture somebody can act on without reading a single number.

    DRAWN AT A's POSITIONS, not halfway between, and that is a real choice
    rather than an arbitrary one: A is the older profile in the case this was
    built for, so the picture reads "here is what you had, and here is how far
    it has moved" — which is the question, in the order it is asked.

    Points below *floor* are drawn small and quiet rather than dropped. Nobody
    can see a ΔE below 1, but leaving those out would show a cloud with holes
    in it and invite the reading that something is missing there, when what is
    actually true is that nothing has changed there.
    """
    import numpy as _np
    import plotly.graph_objects as go

    lab = _np.asarray(lab, dtype=float)
    deltas = _np.asarray(deltas, dtype=float)
    if lab.ndim != 2 or lab.shape[0] != deltas.shape[0]:
        raise ValueError("every point needs exactly one difference")

    # L* up the page, as everywhere else in this application.
    x, y, z = lab[:, 1], lab[:, 2], lab[:, 0]
    if space == "rgb":
        x, y, z = lab[:, 0], lab[:, 1], lab[:, 2]

    quiet = deltas < floor
    sizes = _np.where(quiet, 2.0, 4.0 + 3.0 * _np.clip(
        (deltas - floor) / max(ceiling - floor, 1e-9), 0.0, 1.0))

    if hide_below:
        keep, _said = hidden_below(deltas, hide_below)
        lab = lab[keep]
        x, y, z = x[keep], y[keep], z[keep]
        deltas, sizes = deltas[keep], sizes[keep]

    if by_family:
        return _split_by_family(lab, x, y, z, deltas, sizes, ceiling,
                                "ΔE %{customdata:.2f}", DRIFT_SCALE,
                                0.0, ceiling, _drift_key(ceiling),
                                deltas=deltas)

    return [go.Scatter3d(
        x=x, y=y, z=z, mode="markers", name=name,
        customdata=_pairs(deltas, deltas),
        hovertemplate="ΔE %{customdata[0]:.2f}<extra></extra>",
        marker=dict(
            size=sizes, color=deltas, colorscale=DRIFT_SCALE,
            cmin=0.0, cmax=ceiling,
            # CLAMPED, NOT SCALED TO THE DATA. A scale that stretches to fit
            # whatever is in front of it makes two pictures uncomparable: a
            # pair of nearly identical profiles would come out looking as
            # alarming as a pair that genuinely disagree, because the reddest
            # point is always red. A fixed ceiling means the same colour means
            # the same thing in every picture this ever draws.
            opacity=0.85,
            colorbar=dict(
                title=dict(text="ΔE2000", side="right"),
                thickness=12, len=0.55, x=1.02,
                tickvals=[0, 1, 3, 5],
                ticktext=["0 — same", "1 — invisible", "3 — plain",
                          "5+ — obvious"])))]


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
            meta=dict(_COLOUR_IS_THE_ANSWER, **_is_a_shell()),
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
    #
    # AND MEASURABLY NEUTRAL, which it was not. Every part of this scheme was
    # a blue-grey of about 4 units of chroma -- small to look at, and working
    # against the one thing the scheme is for: a faintly blue surround pushes
    # a neutral towards warm by simultaneous contrast, so the ground being
    # used to judge a colour was tinting it.
    #
    # Each colour is now the neutral grey of THE SAME LIGHTNESS it had, to a
    # tenth of an L* unit, so every contrast inside the scheme is exactly
    # what it was and only the cast is gone:
    #
    #     page  #6e7278 L* 47.9 -> #727272 L* 48.0
    #     plot  #767a80 L* 51.1 -> #7a7a7a L* 51.2
    #     grid  #8b8f95 L* 59.3 -> #8f8f8f L* 59.4
    #     text  #12151a L*  6.7 -> #151515 L*  6.8
    "slate": dict(page="#727272", plot="#7a7a7a", grid="#8f8f8f",
                  caption="#242424", text="#151515", axis="#8f8f8f",
                  kept="rgb(126,126,126)", wire="#414141", mark="#242424"),
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
#: "follow" is not a palette of its own — it is dark or light, chosen by the
#: reader's own system setting and changed again if they change it while the
#: page is open. It exists because a saved page opens in the colouring it was
#: saved in and can do nothing else, so a page written from a dark window
#: arrives as a black rectangle in the middle of somebody's light document or
#: web page. Reported from the published showcase: "the viewer frames stand
#: out because they are black by default although we offer multiple
#: colorschemes."
PAGE_FOLLOWS_THE_READER = "follow"
PAGE_SCHEMES = ("dark", "light", PAGE_FOLLOWS_THE_READER, "none", "slate",
                "ink")

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
  // A GESTURE BELONGS TO THE ROOM IT BEGAN IN -- AND CAPTURING THE POINTER
  // IS NOT HOW TO SAY SO.
  //
  // Taking the pointer stopped BOTH rooms turning at all. Measured in pixels
  // rather than in camera readings, on shapes built in the right space:
  //
  //     capture on    inside one room    left 759 px changed, right 0
  //     capture on    across the seam    left 805, right 1,830  (labels only)
  //     capture off   inside one room    left 79,034, right 76,171
  //     capture off   across the seam    left 63,741, right 61,789
  //
  // With the pointer captured the events are delivered to the element that
  // took it, and the drawing library's own handlers never see them -- so the
  // room holding the gesture cannot turn either, and the "fix" for a drag
  // that crossed the divider quietly cost the drag itself. It shipped in
  // 2.40.0 and is taken back out here.
  //
  // The check that was supposed to guard this measured `getCamera()`, which
  // this file's own relay WRITES -- so it read its own push as movement and
  // called a dead picture alive. It now measures pixels.
  a.addEventListener("mousedown", function () { active = a; }, true);
  b.addEventListener("mousedown", function () { active = b; }, true);
  // AND THE LAST WORD IS SAID AFTER THE GESTURE ENDS.
  //
  // The relay runs while the library reports movement, so whatever the camera
  // does AFTER its last report -- the tail of a drag, a glide slowing to a
  // stop -- was never carried to the other room. Measured on a linked pair,
  // as the distance between the two cameras once the mouse came up:
  //
  //     a drag inside one room        1.09 and 1.12 apart
  //     across the divider, leftward  0.79
  //     across the divider, rightward 4.15
  //
  // on eye vectors about 2.6 long, so the rooms were never actually showing
  // the same face and the divider only made it worse. One final push when the
  // gesture ends costs nothing and leaves them identical.
  function settleBoth() {
    if (!active) return;
    var src = active, dst = (active === a) ? idB : idA;
    active = null;
    window.setTimeout(function () {
      var c = liveCam(src);
      if (c) Plotly.relayout(dst, {"scene.camera": c});
    }, 260);
  }
  window.addEventListener("mouseup", settleBoth, true);
  window.addEventListener("pointercancel", settleBoth, true);
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


#: THE WHEEL ZOOMS WHEREVER IT IS POINTED, including at a shape.
#:
#: Reported from the window: "when hovering the mouse over something that
#: triggers showing a label (srgb comparison in my case just now) i cannot
#: zoom". Measured on a written page, crossing WHERE the wheel lands against
#: WHAT is under it -- because the first attempt changed both at once and
#: proved nothing:
#:
#:     centre, on the shape        label shown   camera 2.598 -> 2.598
#:     centre-ish, off the shape   no label      camera 2.598 -> 0.146
#:     corner, off the shape       no label      zoomed
#:     low left, on the shape      label shown   camera 1.501 -> 1.501
#:
#: Two places on the shape refuse; two off it work. The wheel is NOT being
#: swallowed -- all five events land either way -- and taking the label down
#: first (Plotly.Fx.unhover) does not help, so what blocks it is the hover
#: PICK being live rather than the label being drawn.
#:
#: So the camera is moved here instead of asking the library to move it, which
#: nothing can refuse. The event is taken in the capture phase and stopped, so
#: the library's own zoom cannot also run and double it -- measured after: all
#: four positions zoom, at one rate.
_WHEEL_JS = """
(function () {
  function reach(el) {
    var s = el._fullLayout && el._fullLayout.scene && el._fullLayout.scene._scene;
    if (s && s.getCamera) return s.getCamera();
    return el.layout && el.layout.scene && el.layout.scene.camera;
  }
  function arm(el) {
    el.addEventListener("wheel", function (e) {
      var c = reach(el);
      if (!c || !c.eye) return;            // a flat cut has no camera to move
      var k = e.deltaY > 0 ? 1.1 : 1 / 1.1;
      e.preventDefault();
      e.stopPropagation();
      Plotly.relayout(el, {"scene.camera.eye": {
        x: c.eye.x * k, y: c.eye.y * k, z: c.eye.z * k}});
    }, true);
  }
  function armAll() {
    var d = document.getElementsByClassName("plotly-graph-div");
    for (var i = 0; i < d.length; i++) if (!d[i].__cqWheel) {
      d[i].__cqWheel = true;
      arm(d[i]);
    }
  }
  if (document.readyState === "complete") armAll();
  window.addEventListener("load", armAll);
})();
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
  //: THE FAR WALL IS DRAWN WHOLLY BEFORE THE NEAR WALL (see
  //: docs/THE-SEE-THROUGH-TRIANGLES.md). A depth sort of triangle middles is
  //: right about which TRIANGLE is farther and still wrong about pixels
  //: where the rim's foreshortened far-wall facets and the near wall overlap
  //: in depth -- the kite-shaped wedges. Splitting the order by which way a
  //: face points settles those pixels for every triangle at once: at any
  //: pixel of a closed shell the near wall is nearer than the far wall, so
  //: far-wall-first is right PER PIXEL, which no depth ordering can promise.
  //: Within each wall the depth sort stays. The switch below exists so a
  //: test can throw it and measure both ways on one page; wallSign -1
  //: inverts the two walls, which is the mutation that proves the switch
  //: reaches the drawn picture.
  var wall = true, wallSign = 1;
  var BUCKETS = 4096, tally = new Int32Array(2 * BUCKETS + 1);

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
        // ONLY A CLOSED SURFACE HAS A WALL BEHIND IT. Without this the wall
        // order was applied to every see-through mesh alike, including the
        // agreeing and differing HALVES of a shape -- open sheets, where the
        // rule it rests on is not true and the two groups can swap as the
        // shape turns. The page says which are closed; see `_is_a_shell`.
        var shut = !!(t.meta && t.meta.cqShell);
        var nrm = shut ? new Float64Array(m * 3) : null, vol = 0;
        for (f = 0; f < m; f++) {
          var a = t.i[f], b = t.j[f], c = t.k[f];
          mid[f * 3]     = (t.x[a] + t.x[b] + t.x[c]) / 3;
          mid[f * 3 + 1] = (t.y[a] + t.y[b] + t.y[c]) / 3;
          mid[f * 3 + 2] = (t.z[a] + t.z[b] + t.z[c]) / 3;
          if (!nrm) continue;
          // The triangle's own cross product, fixed in the measurements'
          // numbers: which way it points against the line of sight is the
          // only view-dependent part, and that is one dot product a frame.
          var ux = t.x[b] - t.x[a], uy = t.y[b] - t.y[a], uz = t.z[b] - t.z[a];
          var wx = t.x[c] - t.x[a], wy = t.y[c] - t.y[a], wz = t.z[c] - t.z[a];
          nrm[f * 3]     = uy * wz - uz * wy;
          nrm[f * 3 + 1] = uz * wx - ux * wz;
          nrm[f * 3 + 2] = ux * wy - uy * wx;
          vol += t.x[a] * nrm[f * 3] + t.y[a] * nrm[f * 3 + 1]
               + t.z[a] * nrm[f * 3 + 2];
        }
        // MADE TO POINT INTO THE SHAPE WHICHEVER WAY THE FACES ARE WOUND.
        // The shells this application builds are wound inward (measured:
        // signed volume -818,514 for a shape of volume 818,514) and their
        // cross products already point in; a surface wound the other way
        // has positive signed volume, and flipping the stored normals once
        // here means the far-wall test below never needs to know. An OPEN
        // surface has no far wall and a near-zero signed volume; either
        // sign leaves its picture the depth sort it always had.
        if (vol > 0) for (f = 0; f < m * 3; f++) nrm[f] = -nrm[f];
        keep.push({uid: t.uid, index: n, m: m, mid: mid, nrm: nrm,
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
    // THE AXIS RANGES CANNOT BE TRUSTED AFTER A RELAYOUT. On this page they
    // read the data's own spans when it opens, and junk the moment any
    // camera relayout has run -- measured: the same probe returned
    // [-88..92, -80..130, 1.7..103] before and [-1..6, -1..4, -1..6] after,
    // which bent the line of sight from (.577,.577,.577) to (.47,.29,.84)
    // and quietly missorted every frame after the first drag. The scene's
    // own dataScale is what the library ACTUALLY multiplied each axis by,
    // and it does not move; the ranges stay only as the fallback for a
    // scene not yet built.
    var ds = null;
    try { ds = sc._scene && sc._scene.dataScale; } catch (err) {}
    for (var d = 0; d < 3; d++) {
      var a = (ar && ar[kk[d]]) || 1, span;
      if (ds && ds[d]) {
        span = 1 / ds[d];
      } else {
        var r = (sc[ax[d]] && sc[ax[d]].range) || [0, 1];
        span = (r[1] - r[0]) || 1;
      }
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
    var banks = (wall && A.nrm) ? 2 : 1;
    tally.fill(0);
    for (f = 0; f < m; f++) {
      var b = (key[f] - lo) * s | 0;
      if (b < 0) b = 0; else if (b >= BUCKETS) b = BUCKETS - 1;
      if (banks === 2) {
        // The faces are wound inward (measured: the shell's signed volume is
        // the negative of its volume), so the cross product points INTO the
        // shape and a face whose cross product runs WITH the line of sight
        // is the far wall. Bank 0 is drawn first.
        var toward = (A.nrm[f * 3] * look[0] + A.nrm[f * 3 + 1] * look[1]
                    + A.nrm[f * 3 + 2] * look[2]) * wallSign < 0;
        if (toward) b += BUCKETS;
      }
      A.bin[f] = b;
      tally[b + 1]++;
    }
    for (f = 0; f < banks * BUCKETS; f++) tally[f + 1] += tally[f];
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
                nrm: new Float64Array(m * 3),
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
      for (f = 0; f < A2.m * 3; f++) {
        pool.mid[into + f] = A2.mid[f];
        pool.nrm[into + f] = A2.nrm[f];
      }
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
          wallOrder: function (on, sign) {
            wall = !!on; wallSign = (sign === -1) ? -1 : 1;
            return pass(true);
          },
          // For the tests: which door was used, and how much there is to do.
          how: function () {
            var n = 0, pooled = 0, surfaces = 0;
            for (var q = 0; q < plots.length; q++) {
              for (var m = 0; m < plots[q].meshes.length; m++)
                n += plots[q].meshes[m].m;
              surfaces += plots[q].meshes.length;
              if (plots[q].pool) pooled += plots[q].pool.count;
            }
            // WHETHER THE PAGE ARRIVED WITH THE WALL ORDER ON, which is a
            // different claim from whether it works. A check that throws the
            // switch itself proves the mechanism and nothing about the
            // default -- measured: switching the default off left the wall
            // audit reporting "Clean", because it turns it on before it
            // looks. So the default is reported, and asked for separately.
            return {fast: fast, plots: plots.length, faces: n,
                    surfaces: surfaces, pooled: pooled, wall: wall};
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
  // A TALL NARROW PANE CROPS THE SHAPE, and the camera cannot know that on
  // its own. The eye at 1.5 frames a printer's gamut for a pane wider than it
  // is tall; put the same scene in a portrait pane -- which is what the
  // application's own view becomes on a laptop, 424 wide by 833 tall at a
  // 1000px window -- and the shape runs off both sides with the whole
  // lightness axis outside the view. Photographed at that size before this
  // was written: no L* axis, no numbers, the magenta side cut off.
  //
  // So the eye is pulled back by as much as the pane is out of shape, and no
  // further than twice. A pane wider than it is tall is left exactly as it
  // was, which is every desktop window and every saved page opened normally.
  // Done BEFORE home is remembered, so "back to the start" comes back to a
  // view that fits rather than to the one that did not.
  // ALWAYS FROM THE VIEW THE PAGE WAS WRITTEN WITH, never from the last fit.
  // Fitting from wherever the camera happens to be compounds: two rooms in a
  // window dragged narrower twice went 1.500 -> 2.007 -> 3.904, each pull
  // applied to the one before it, and the shape walked off into the distance.
  // Caught by crossing two rooms with a resize rather than trying either on
  // its own.
  var base = {};
  function fitToPane(id) {
    var gd = scene(id);
    if (!gd || !gd._fullLayout || !gd._fullLayout.scene) return;
    var w = gd.clientWidth || gd.offsetWidth || 0;
    var h = gd.clientHeight || gd.offsetHeight || 0;
    var cam = liveCam(gd);
    if (!cam || !cam.eye) return;
    if (!base[id]) base[id] = {eye: {x: cam.eye.x, y: cam.eye.y, z: cam.eye.z},
                               up: cam.up, center: cam.center};
    var from = base[id];
    if (!w || !h) return;
    // A pane that is wider than it is tall wants the written view back --
    // which matters when a window is dragged narrow and then wide again.
    // HOW FAR BACK. Measured on two rooms side by side, walking the eye back
    // from the written view until no coloured pixel touched a wall, at four
    // viewpoints with the spin paused:
    //
    //     room 195 x 654 (out of shape 3.35)   needs 2.00x
    //     room 310 x 660 (out of shape 2.13)   needs 1.30x
    //     room 410 x 700 (out of shape 1.71)   needs 1.15x
    //
    // — which is what this line already gave, and the ceiling of two is the
    // narrowest case exactly. The reason two rooms on a phone were cut in
    // half anyway is that THIS NEVER RAN on a saved page: see `placed`.
    //
    // The pull is still taken from the view the page was written with, never
    // from the last fit, so dragging a window narrower twice cannot compound
    // it — which is a fault this already had once.
    var pull = (h <= w) ? 1 : Math.min(2, h / w);
    whileWeMoveIt(function () {
      setCam(gd, {eye: {x: from.eye.x * pull, y: from.eye.y * pull,
                        z: from.eye.z * pull},
                  up: from.up, center: from.center});
    });
  }
  // AND AGAIN WHEN THE PANE CHANGES SHAPE, which is how a person actually
  // meets this: the window opens wide and gets dragged narrower, and fitting
  // once at load would have been measured as "no change" -- as it was, before
  // this was added.
  //
  // ONLY WHILE THE VIEW IS STILL THE ONE IT OPENED AT. Somebody who has
  // turned the shape has said where they want to look from, and a window
  // resize is no reason to overrule them. Compared against the remembered
  // home, which is also updated so that "back to the start" keeps meaning a
  // view that fits.
  // WHETHER ANYBODY HAS TOUCHED IT, kept as a fact rather than worked out by
  // comparing cameras. The comparison was tried first and it was wrong: a
  // relayout updates layout.scene.camera immediately while the scene's own
  // camera lags a frame behind, so a shape the reader had just turned still
  // matched its remembered view -- and the next resize scaled THEIR angle
  // instead of leaving it alone. Measured: turned to (-2.100, 0.400, 0.600),
  // resized, and it became (-2.577, 0.491, 0.736).
  var touched = {}, ourOwn = 0;
  // OUR OWN CAMERA CHANGES ARE NOT SOMEBODY TAKING THE VIEW OVER. The fitting
  // moves the camera with the same call a reader's drag ends in, so without
  // this the very first fit marked the picture as "theirs" and every later
  // one was skipped -- the page's own touchedYet() said True before anybody
  // had touched anything.
  function markTouched(id) { if (!ourOwn) touched[id] = true; }
  function whileWeMoveIt(what) {
    ourOwn += 1;
    try { what(); } finally {
      window.setTimeout(function () { ourOwn = Math.max(0, ourOwn - 1); }, 400);
    }
  }
  function untouched(id) { return !touched[id]; }
  var refitting = null;
  function refit() {
    if (refitting) window.clearTimeout(refitting);
    refitting = window.setTimeout(function () {
      refitting = null;
      for (var i = 0; i < ids.length; i++) {
        var id = ids[i], gd = scene(id);
        // NOT GATED ON `alreadyPlaced` ANY MORE. A pane that has changed
        // shape since the page was written needs fitting whoever wrote it —
        // and the compounding that gate existed to prevent is gone now that
        // the application is handed `reading()`, the view the fit was
        // measured from, rather than the fitted one. Measured in the window
        // with two rooms: at 1000px wide the shapes came through their side
        // walls by 170 and 108 pixels, at 800px by 270 and 234.
        if (!gd || isFlat(gd) || !untouched(id)) continue;
        fitToPane(id);          // always measured from base[id]
        var now = liveCam(gd);
        if (now && now.eye) home[id] = {up: now.up, center: now.center,
                                        eye: {x: now.eye.x, y: now.eye.y,
                                              z: now.eye.z}};
      }
    }, 180);
  }
  if (window.addEventListener) window.addEventListener("resize", refit);
  // A CAMERA THAT WAS HANDED TO US IS ALREADY WHERE IT BELONGS.
  //
  // The application rewrites this page for anything it cannot restyle, and
  // writes the camera the reader is looking from into the new one. If the
  // fitting then runs, it pulls that camera back AGAIN -- and since every
  // rebuild starts a new page, the "measure from the written view" rule that
  // stops one page compounding cannot see the previous one. Reported as
  // exactly that: "the shape jumped around after i moved it. when i let go it
  // seemed like it snapped back while zooming out a touch".
  //
  // A saved page has no such history: it is opened fresh, in a window whose
  // shape nobody knew when it was written, and there the fitting is the whole
  // point. So the window says which kind of page this is.
  var alreadyPlaced = false;
  function fitAll(tries) {
    if (alreadyPlaced) return;
    var missing = false;
    for (var i = 0; i < ids.length; i++) {
      var gd = scene(ids[i]);
      if (!gd) { missing = true; continue; }
      if (!isFlat(gd)) fitToPane(ids[i]);
    }
    if (missing && (tries || 0) < 60)
      window.setTimeout(function () { fitAll((tries || 0) + 1); }, 120);
  }
  function remember(tries) {
    var missing = false;
    for (var i = 0; i < ids.length; i++) {
      var gd = scene(ids[i]);
      if (gd && isFlat(gd)) keepFlat(ids[i], ranges(gd));
      else if (gd) keep(ids[i], liveCam(gd));
      if (gd) gestures(gd);       // a finger works from the first frame
      // AND THE WATCHER, from the first frame as well. It used to be attached
      // only by step(), which runs while a picture is TURNING -- so on a page
      // that is not moving, nothing was listening, and "has the reader taken
      // this view over?" answered no however hard they dragged. Measured with
      // the page's own touchedYet(): False after a turn.
      if (gd) watch(gd);
      if (!home[ids[i]]) missing = true;
    }
    if (missing && (tries || 0) < 60)
      window.setTimeout(function () { remember((tries || 0) + 1); }, 120);
  }
  function reset() {
    rest();
    stopGlide();          // or the view would drift straight back off again
    for (var i = 0; i < ids.length; i++) {
      // BACK TO THE START MEANS BACK TO THE START, so the pane's own fitting
      // governs again from here: somebody who presses this is asking for the
      // view the page chose, not for the one they had been holding.
      touched[ids[i]] = false;
      var gd = scene(ids[i]), was = home[ids[i]];
      if (!gd || !was) continue;
      // OURS, not theirs -- putting the view back is not the reader taking it
      // over, and without this the press that says "back to the start"
      // immediately marked the picture as theirs again and the pane stopped
      // fitting it.
      whileWeMoveIt(function () {
        if (was.eye) setCam(gd, was);
        else setRanges(gd, was);
      });
    }
  }
  // ANY GESTURE AT ALL ENDS A THROW. Touching the shape to stop it is what
  // anybody would try first, and a scroll wheel or a pinch arriving mid-throw
  // means they have moved on to doing something else with it.
  function hold() { held = Date.now(); rest(); stopGlide(); }
  function watch(gd) {
    if (gd._cqSpinWatched) return;
    gd._cqSpinWatched = true;
    // ANYTHING A PERSON DOES TO THE SHAPE COUNTS, including the drag that the
    // drawing library reports afterwards as a relayout. Registered once,
    // inside the guard, or a page that watches twice marks twice.
    try {
      if (gd.on) gd.on("plotly_relayout", function (what) {
        for (var k in what) if (String(k).indexOf("camera") >= 0)
          markTouched(gd.id);
      });
    } catch (e) {}
    ["mousedown", "wheel", "touchstart", "touchmove"].forEach(function (ev) {
      gd.addEventListener(ev, hold, true);
      gd.addEventListener(ev, function () { markTouched(gd.id); }, true);
    });
    // AFTER hold, so that clearing the old throw cannot clear the new grab.
    ["mousedown", "touchstart"].forEach(function (ev) {
      gd.addEventListener(ev, grab, true);
    });
    armReleases();
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
    // is also what somebody pressing "from above" plainly means. A throw still
    // in the air is the same argument twice over.
    on = false;
    rest();
    stopGlide();
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
    // ONE FINGER SCROLLS THE PAGE. TWO WORK THE SHAPE.
    //
    // This said `touchAction = "none"` and the reasoning was sound as far as
    // it went: without it the browser reads a drag as a page scroll and stops
    // delivering the moves -- measured, a page whose touchstart nobody
    // objects to gets touchstart and touchend and not one touchmove between.
    //
    // What it missed is that "none" also forbids the browser to scroll the
    // page from a touch STARTING on the picture, and by this project's own
    // layout rule the picture is 55% to 85% of the first screen. Measured by
    // walking down the middle of the screen a row at a time, 74-80% of a
    // phone screen could not begin a scroll, on every 3D page ever written.
    // The controls and the written-out numbers below were unreachable.
    //
    // Basti, twice, and the second one is what settled it: "i can't reach the
    // control options (it does not scroll to them)", then -- after the page
    // began scrolling itself when the panel opens -- "the scrolling still
    // does not work". Bringing the panel to somebody who presses a button
    // does not help somebody who wants to read the page.
    //
    // `pan-y` is the standard way out and not an invention here: it is what
    // an interactive map inside a scrolling page does, and readers already
    // meet it there. The browser takes a one-finger VERTICAL drag and scrolls
    // the page with it; a horizontal one still reaches the picture, so
    // turning the shape left and right goes on working exactly as it did.
    // Two fingers are ours entirely -- pinch to zoom, drag to slide and tip.
    //
    // WHAT IT COSTS, said plainly rather than glossed: tipping the shape up
    // and down with ONE finger is gone, because that gesture is now how a
    // reader scrolls. It is still there on two fingers, and on the up and
    // down buttons in the strip, and in the look-from presets. Being able to
    // read the page at all is worth more than the third route to tipping.
    gd.style.touchAction = "pan-y";
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

  // CARRYING ON A LITTLE WHEN THEY LET GO.
  //
  // Asked for because a shape that stops dead the instant a finger lifts does
  // not feel like an object: "it should not move like crazy after letting go,
  // just a bit to make it feel natural".
  //
  // WHAT IS MEASURED, AND WHY IT IS NOT THE FINGER. The obvious way is to
  // watch the pointer and turn pixels into degrees -- and it needs a constant
  // this file does not own, because the drawing library decides for itself how
  // far a drag turns a scene. Guess that constant and the throw leaves at a
  // different speed from the drag that caused it, which is precisely the thing
  // that reads as broken. So what is sampled is the CAMERA: where the eye
  // actually is, several times a second, while the drag is happening. The
  // speed that comes out is in the same units the movement already uses, and
  // it is right by construction on any device, at any drag speed, whatever the
  // library does internally.
  //
  // liveCam() is what makes that possible. During a drag the camera in the
  // layout is stale -- measured: 0.000 of movement over a 180px drag -- and
  // the real one is inside the built scene, which liveCam already reaches for
  // because the turning needed exactly the same thing.
  //
  // AND IT COSTS NOTHING TO EXCLUDE PANNING AND ZOOMING. Sampling the eye's
  // DIRECTION rather than its position means a pan (which moves eye and centre
  // by the same vector) and a zoom (which only changes the distance between
  // them) both come out as no movement at all, with no special case to write
  // and none to get wrong. Momentum is for turning, and turning is the only
  // thing this can see.
  var glide = {turn: 0, tilt: 0};      // radians a second, dying away
  var glideOn = false;                 // whether this page carries it at all
  var marks = [], grabbing = false, sampler = null;

  //: HOW THE THROW DIES AWAY, as the time it takes to halve.
  //:
  //: three.js's OrbitControls -- the convention nearly every 3D viewer on the
  //: web follows -- keeps 95% of the speed EVERY FRAME (dampingFactor 0.05,
  //: applied as `sphericalDelta *= 1 - dampingFactor`). Checked in its source
  //: rather than remembered. At 60fps that is a half-life of 0.22s.
  //:
  //: SAID AS A HALF-LIFE ON PURPOSE, because three.js's own form is per FRAME
  //: and so it dies twice as fast on a 120Hz iPad as on a 60Hz laptop -- the
  //: same page, two different feels, and the iPad is where this was asked for.
  //: A half-life in seconds is the same movement on any screen.
  var HALF_LIFE = 0.22;
  //: Below this it has stopped. Going on would cost a wakeup every frame to
  //: move the shape by less than the width of a line.
  var STILL = 1.5 * Math.PI / 180;
  //: THE FASTEST THROW THAT WILL BE HONOURED, and the number that decides
  //: whether this feels right or silly. A flick can produce an arbitrarily
  //: large speed over one short interval, and what was asked for is "not like
  //: crazy after letting go, just a bit to make it feel natural".
  //:
  //: How far a throw carries after release is speed x HALF_LIFE / ln2, so
  //: this cap IS the answer to "how much further can it possibly go": at
  //: 150 degrees a second, no flick however hard carries more than about 48
  //: degrees. An eighth of a turn is plainly a follow-through and is nowhere
  //: near a spin.
  //:
  //: Measured before it was chosen: at 300 the hardest flick this can be
  //: given carried **102 degrees** past the drag, which is a third of the way
  //: round and reads as the shape having been let go of, not carried.
  var FASTEST = 150 * Math.PI / 180;
  //: HOW FAR BACK TO LOOK FOR THE SPEED. A finger SLOWS as it lifts, so the
  //: last step before release is close to no movement and taking it alone
  //: reads every throw as a stop. Averaging over the last eighth of a second
  //: is what makes a throw a throw.
  var LOOK_BACK = 0.12;
  //: ... and how long ago is too long ago. Somebody who dragged the shape,
  //: held it still and then lifted has plainly parked it, and parking it must
  //: park it.
  var STALE = 0.09;

  function nowSeconds() {
    return ((window.performance && window.performance.now)
            ? window.performance.now() : Date.now()) / 1000;
  }
  function firstScene() {
    for (var i = 0; i < ids.length; i++) {
      var gd = scene(ids[i]);
      if (gd && !isFlat(gd)) return gd;
    }
    return null;                 // every picture here is a flat cut
  }
  // WHERE THE EYE IS POINTING, as a pair of angles that step() can be handed
  // straight back: turning is the angle round the L* axis, tipping is the
  // angle above the plane. Straight down the pole has no round-the-axis angle
  // at all, and reading one there would be reading noise.
  function angles(gd) {
    var cam = liveCam(gd);
    if (!cam || !cam.eye) return null;
    var c = cam.center || {x: 0, y: 0, z: 0};
    var x = cam.eye.x - c.x, y = cam.eye.y - c.y, z = cam.eye.z - c.z;
    var flatR = Math.sqrt(x * x + y * y);
    if (!(flatR > 1e-9)) return null;
    return {az: Math.atan2(y, x), el: Math.atan2(z, flatR)};
  }
  function shortest(d) {         // -PI..PI: crossing behind must not read as a
    while (d > Math.PI) d -= 2 * Math.PI;              // whole turn the other
    while (d < -Math.PI) d += 2 * Math.PI;             // way round
    return d;
  }
  function sample() {
    if (!grabbing) { sampler = null; return; }
    sampler = window.requestAnimationFrame(sample);
    var gd = firstScene(); if (!gd) return;
    var a = angles(gd); if (!a) return;
    marks.push({t: nowSeconds(), az: a.az, el: a.el});
    if (marks.length > 30) marks.shift();
  }
  function grab() {
    glide.turn = 0; glide.tilt = 0;
    marks = [];
    if (grabbing) return;
    grabbing = true;
    if (sampler === null) sampler = window.requestAnimationFrame(sample);
  }
  // THE PICTURE CATCHES UP WHEN THE HAND LETS GO, not when the reader happens
  // to point at something.
  //
  // Reported: "if the mouse arrow lands on the shape itself when letting go it
  // jumps a little bit", and — the clue that solved it — "a label popped up".
  // Measured: releasing over a shape moves the camera 69 degrees in Chromium
  // and 37 in WebKit, IN A SINGLE FRAME, while releasing over the walls moves
  // nothing. Turning the hover off removes the jump entirely, so the label and
  // the jump are the same event: pointing at a shape makes the library draw a
  // readout, and that redraw commits a camera the picture had not yet caught
  // up with.
  //
  // Turning hover off would cure it and take something real away — pointing at
  // a shape to read its name is behaviour these pages offer. So the catching-up
  // is done at the moment the button comes up, where it belongs to the gesture
  // the reader just made, instead of arriving later out of nowhere.
  function settle() {
    for (var i = 0; i < ids.length; i++) {
      var gd = scene(ids[i]);
      if (!gd || isFlat(gd)) continue;
      var cam = liveCam(gd);
      if (cam) setCam(gd, cam);
    }
  }

  function letGo() {
    if (!grabbing) return;
    grabbing = false;
    settle();
    if (sampler !== null) {
      window.cancelAnimationFrame(sampler); sampler = null;
    }
    var taken = marks; marks = [];
    if (!glideOn || taken.length < 2) return;
    var last2 = taken[taken.length - 1];
    if (nowSeconds() - last2.t > STALE) return;      // held still, then lifted
    var first = last2;
    for (var i = taken.length - 1; i >= 0; i--) {
      if (last2.t - taken[i].t > LOOK_BACK) break;
      first = taken[i];
    }
    var span = last2.t - first.t;
    if (!(span > 0.008)) return;             // too short an interval to divide
    var turn = shortest(last2.az - first.az) / span;
    var tilt = (last2.el - first.el) / span;
    if (!isFinite(turn) || !isFinite(tilt)) return;
    turn = Math.max(-FASTEST, Math.min(FASTEST, turn));
    tilt = Math.max(-FASTEST, Math.min(FASTEST, tilt));
    if (Math.abs(turn) < STILL && Math.abs(tilt) < STILL) return;
    glide.turn = turn; glide.tilt = tilt;
    if (raf === null) {
      last = (window.performance || Date).now();
      raf = window.requestAnimationFrame(frame);
    }
  }
  function gliding() {
    return Math.abs(glide.turn) > STILL || Math.abs(glide.tilt) > STILL;
  }
  function stopGlide() { glide.turn = 0; glide.tilt = 0; }
  // ON THE WINDOW, NOT ON THE PICTURE. A drag that ends with the pointer off
  // the edge of the picture -- which is most of the fast ones, because a throw
  // travels -- never delivers a mouseup to the element it started on.
  function armReleases() {
    if (window._cqLetGo) return;
    window._cqLetGo = true;
    ["mouseup", "touchend", "touchcancel", "pointercancel", "blur"]
      .forEach(function (ev) {
        window.addEventListener(ev, letGo, true);
      });
  }

  function frame(now) {
    if (!on && !gliding()) { raf = null; return; }
    raf = window.requestAnimationFrame(frame);
    var dt = (now - last) / 1000; last = now;
    if (document.hidden) return;
    if (!isFinite(dt) || dt <= 0) return;
    if (dt > 0.1) dt = 0.1;       // back from a hidden tab: step, do not jump
    // THE THROW FIRST, AND THE MOVEMENT WAITS BEHIND IT. Two things turning
    // the same shape at once is the one way this could feel worse than not
    // having it: the swing would fight the throw and neither would read as
    // deliberate. So while a throw is alive it is the only thing moving, the
    // swing's phase is held at its centre, and when the throw dies away the
    // swing takes over from wherever it left the shape.
    if (gliding()) {
      var gt = glide.turn * dt, gl = glide.tilt * dt;
      var keeps = Math.pow(0.5, dt / HALF_LIFE);
      glide.turn *= keeps; glide.tilt *= keeps;
      if (!gliding()) stopGlide();
      for (var j = 0; j < ids.length; j++) step(ids[j], gt, gl);
      rest();
      return;
    }
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
    if (o.placed !== undefined) alreadyPlaced = !!o.placed;
    if (o.ids !== undefined) { ids = o.ids; rest(); fitAll(0); remember(0); }
    ["turn", "tilt"].forEach(function (which) {
      var got = o[which]; if (!got) return;
      var a = axes[which];
      if (got.mode !== undefined && got.mode !== a.mode) { a.mode = got.mode; a.phase = 0; }
      if (got.range !== undefined && got.range !== a.range) { a.range = got.range; a.phase = 0; }
      if (got.speed !== undefined) a.speed = got.speed;
    });
    if (o.on !== undefined) { if (o.on && !on) rest(); on = !!o.on; }
    // PAUSE STOPS EVERYTHING THAT IS MOVING. Somebody pressing pause while a
    // throw is still running and watching the shape carry on turning would
    // reasonably conclude the button is broken.
    if (o.on === false) stopGlide();
    if (o.glide !== undefined) {
      glideOn = !!o.glide;
      if (!glideOn) stopGlide();
    }
    if ((on || gliding()) && raf === null) {
      last = (window.performance || Date).now();
      raf = window.requestAnimationFrame(frame);
    }
  }
  // WHERE THE READER IS LOOKING FROM, WITHOUT THE FITTING. The application
  // asks the page for the camera a few times a second and writes it into the
  // next page it builds. If it is handed the FITTED camera, then a window
  // that pulled the eye back writes that pulled-back view into the next page,
  // which pulls it back again — the compounding that `placed` was invented to
  // stop, at the cost of the fitting never running in the window at all.
  //
  // So what is offered here is the view the fit was measured FROM: `base[id]`
  // while the fitting still governs the pane, and the live camera once a
  // reader has taken it over, because then it is theirs and no fit applies.
  function reading(id) {
    var which = id || ids[0];
    var gd = scene(which);
    if (!gd) return null;
    if (base[which] && untouched(which)) return base[which];
    return liveCam(gd);
  }
  return {set: set, nudge: nudge, reset: reset, zoom: zoom, slide: slide,
          look: look, moving: function () { return on; },
          glides: function () { return glideOn; },
          reading: reading,
          // For checking, from the outside, whether the pane's own fitting
          // still governs this graph or whether a reader has taken it over.
          //
          // ASKED WITH NO NAME IT MEANS "HAS ANYBODY TOUCHED ANYTHING", and
          // that is not a convenience: `touched[undefined]` is false however
          // hard a reader has dragged, so the application asking this without
          // an id was told the view was nobody's and fitted the reader's own
          // camera on the next rebuild — 2.220 came back as 4.441, which is
          // the "snapped back while zooming out a touch" that started all of
          // this. Two rooms are linked, so either one counts.
          touchedYet: function (id) {
            if (id !== undefined) return !!touched[id];
            for (var i = 0; i < ids.length; i++)
              if (touched[ids[i]]) return true;
            return false;
          }};
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

    # EVERY COLOURING THE PAGE KNOWS, not just the two the window has.
    #
    # This flattened anything that was not "light" to "dark", which was right
    # while a page could only ever open in one of the window's own two. It is
    # what silently swallowed "follow you": the choice arrived here intact --
    # proved by printing it at the writer's door -- and was turned into "dark"
    # one line before the settings were built, so the page opened dark and the
    # two files came out BYTE-IDENTICAL. The choice had reached everything
    # except the last line that mattered.
    which = mode if mode in PAGE_SCHEMES else (
        "light" if mode == "light" else "dark")
    # "follow you" is not a palette, so the STATIC colours written into the
    # file have to be one of the two it chooses between. Light is the safer
    # start: a page that is going to be dark repaints itself the instant the
    # script runs, while the reverse -- black arriving first -- is the flash
    # this whole option exists to stop.
    #
    # KNOWN AND NOT YET FIXED: a reader whose machine is dark gets one frame
    # of light paper before the script repaints. Curing it means writing both
    # colours into the stylesheet behind a prefers-color-scheme query, in the
    # two page writers, and that is a separate piece of work.
    colours = static_palette(which)
    settings = dict(spin)
    settings["ids"] = list(ids)
    settings["ink"] = colours["text"]
    settings["paper"] = colours["page"]
    settings["mode"] = which
    settings["show"] = dict(offer or {})
    # BOTH PALETTES, but only when the page is allowed to switch between
    # them. A page that cannot change its paper has no use for the other one,
    # and there is no reason to put it in the file.
    # OR WHEN THE PAGE HAS TO WORK ITS COLOURING OUT FOR ITSELF.
    #
    # The palettes used to travel only when the reader was given the button to
    # change colouring with, which was right when a page opened in exactly the
    # colours it was written with. "Follow you" is decided at load from the
    # reader's own machine, and a page cannot decide anything without the two
    # palettes to choose between: measured on a chart page saved to follow —
    # a dark reader got the light colours, because applyMode returns at its
    # first line when there is nothing to apply.
    if (settings["show"].get("appearance")
            or which == PAGE_FOLLOWS_THE_READER):
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
            # THE SETTINGS ARE KEPT WHERE THE PAGE CAN REACH THEM AGAIN. A
            # page that can switch between two pictures has to rebuild its
            # strip for whichever is showing, and it can only do that from the
            # settings it was built with. Nothing else reads this.
            f"{{var s = {blob};window.cqSettings = s;window.cqSpin.set(s);"
            f"window.cqSpinControls(s);}});</script>")



#: The caption, kept inside the picture it belongs to.
#:
#: WHY IT IS NOT PART OF THE MOVEMENT SCRIPT, where it was written first: a
#: cross-section has no camera, so the application's flat view carries no
#: movement script at all -- measured by asking the page, which answered
#: `cqSpin? False` -- and the flat view is exactly where the caption is
#: longest and the trouble worst. This runs in every page, moving or still,
#: flat or not.
#:
#: WHAT IT DOES. One line written for a wide pane runs off the right-hand
#: edge of a narrow one: photographed in the application's cross-section at a
#: 1000px window, "...from a D50 white * lightness L* = 50" stopped mid-word
#: at the frame, and measured there at 512 pixels of text in a 424 pixel pane.
#: The caption is built as clauses joined by a middle dot, so that is where a
#: reader would break it, and that is where this breaks it. The one-line form
#: is remembered, so widening the window puts it back.
_CAPTION_JS = """
window.cqCaption = (function () {
  var oneLine = {}, asOneLine = {}, timer = null;
  var JOIN = "  \u00b7  ";
  function each(fn) {
    var divs = document.getElementsByClassName("plotly-graph-div");
    for (var i = 0; i < divs.length; i++) fn(divs[i]);
  }
  function fit(gd) {
    if (!gd || !gd.layout || !gd.layout.title || !window.Plotly) return;
    var now = String(gd.layout.title.text || "");
    if (!now) return;
    var key = gd.id || "one";
    if (oneLine[key] === undefined) oneLine[key] = now.split("<br>").join(JOIN);
    var full = oneLine[key];
    var room = (gd.clientWidth || 0) - 28;
    if (room <= 0 || full.indexOf(JOIN) < 0) return;
    var el = gd.querySelector ? gd.querySelector(".gtitle") : null;
    var wide = 0;
    try { wide = el && el.getBBox ? el.getBBox().width : 0; } catch (e) {}
    if (!wide) return;
    var broken = full.split(JOIN).join("<br>");
    var want = now;
    // Wrapped or not, the measurement is of what is DRAWN -- so the decision
    // is made from the state it is in: too wide on one line means break it,
    // and comfortably narrow while broken means it will fit joined up again.
    if (now.indexOf("<br>") < 0) {
      // Remembered while it is still on one line, because that is the only
      // moment its true width can be measured -- guessing it from the wrapped
      // text (twice the longer line, and then some) kept a caption in two
      // lines through a window half as wide again as it needed. Measured: it
      // came back at 1900 where 1600 was plenty.
      asOneLine[key] = wide;
      if (wide > room) want = broken;
    } else if (asOneLine[key] && asOneLine[key] <= room) {
      want = full;
    }
    if (want !== now) Plotly.relayout(gd, {"title.text": want});
  }
  function soon() {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(function () { timer = null; each(fit); }, 160);
  }
  window.addEventListener("load", function () { window.setTimeout(soon, 300); });
  window.addEventListener("resize", soon);
  return {fit: function () { each(fit); }};
})();
"""

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
  // WHETHER A DRAG CARRIES ON AFTER THE FINGER LIFTS. Set when the page was
  // saved; the reader may be given a switch for it, or may not. A page saved
  // before this existed has no such setting, and `undefined` reads as off --
  // which is exactly right, because off is how those pages have always
  // behaved and reopening one must not change it under the reader.
  var carries = !!settings.glide;
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
  var anyDiffers = false;              // ... and is any part of it standing out
  var anyAgrees = false;               // ... and is any part of it shared
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
        // WHAT THIS PART OPENED AT, kept per part rather than per shape.
        //
        // A shape can be drawn as more than one trace at DIFFERENT
        // strengths: a chart's skin is a surface at 0.3 with a cage over it
        // at full strength. The shape's own strength is read off its first
        // trace, and it used to be written to every one of them -- so the
        // first press of anything flattened them all onto one number and the
        // cage could never come back. Measured on the ink-amounts page:
        // fainter then stronger left the cage at 0.3 where it had opened at
        // 1, and 11,537 pixels different on a page whose floor is 0.
        g.parts.push({gd: gd, id: id, at: at, proxy: proxy,
                      opened: (typeof t.opacity === "number") ? t.opacity : 1});
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
          // AND WHETHER THERE IS ANYTHING ON EACH SIDE OF THE QUESTION.
          //
          // "This page can fade" is not the same as "this page has something
          // to fade in both directions". A shape that sits entirely inside
          // the others -- the matte paper inside the glossy one does, at
          // every single one of its 978 triangles -- has a mask of nothing
          // but zeros: everything agrees and nothing differs. The control
          // that fades away the differences was still offered, and pressing
          // it moved the picture by 0 pixels. Measured on two published
          // pages, and it breaks this file's own rule that no row anywhere
          // carries a button that would do nothing.
          if (t.meta && t.meta.stand) {
            g.stand = true; agreed = true;
            if (t.meta.stand.indexOf("1") >= 0) anyDiffers = true;
            if (t.meta.stand.indexOf("0") >= 0) anyAgrees = true;
          }
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
  // AND A SCENE HAS NO CROSS-SECTION TO SLIDE.
  //
  // On a page holding both views the levels are carried once, for the whole
  // page, so the strip built them for the shells as well -- cut, cut-at,
  // cut-up and cut-down offered over a three-dimensional shape that has no
  // cut to move. That is exactly the lie the line above refuses in the other
  // direction, where a flat picture is not offered the turning controls.
  //
  // Only the LIGHTNESS controls go: the ΔE hider on a drift page is also
  // called "cut" and belongs on a scene, and it is built from the traces'
  // own data rather than from these levels.
  if (!flat) cuts = null;
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
    // ONE INSTRUCTION FOR THE WHOLE SHAPE, NOT ONE PER TRACE.
    //
    // This used to call restyle inside the loop below, once for every trace
    // it touched. On a page whose shapes are one or two traces that is a few
    // calls and nobody notices. On the showcase page comparing a paper with
    // Adobe RGB it is not: the comparison cage is drawn in true colours, a
    // line takes one colour for a whole trace, and that cage is 347 traces.
    // So one press of "where they agree" asked the drawing library to
    // rebuild the scene 349 times in a row.
    //
    // MEASURED, on a desktop with a real graphics card:
    //
    //     page 11, 4 traces        5 calls      0.3 s
    //     page 14, 348 traces    349 calls     36.4 s
    //
    // Reported from a phone as the page hanging on the button press -- and
    // then not coming back on reload, because the reading is remembered and
    // replayed, so the same 349 rebuilds ran again while the page was
    // opening. The page LOADS fine; it is only the press that is ruinous,
    // which is exactly what was described.
    //
    // Traces are gathered by which fields they need and handed over in one
    // call each. Grouped rather than merged wholesale because restyle spreads
    // a value list across the traces it is given, so a trace that wants no
    // vertexcolor must not be in the same call as one that does -- it would
    // be handed `undefined` and lose its colours.
    var groups = {}, divs = [];
    function later(part, patch) {
      var keys = Object.keys(patch).sort();
      if (!keys.length) return;
      // ONE GRAPH DIV PER CALL, AND IT IS PART OF THE KEY. Two scenes side
      // by side are two divs, and a trace index means nothing to the wrong
      // one -- so the div is grouped on as well as the field names.
      var which = divs.indexOf(part.gd);
      if (which < 0) { which = divs.length; divs.push(part.gd); }
      var id = which + ":" + keys.join("|");
      var slot = groups[id];
      if (!slot) {
        slot = groups[id] = {gd: part.gd, at: [], values: {}};
        keys.forEach(function (k) { slot.values[k] = []; });
      }
      slot.at.push(part.at);
      keys.forEach(function (k) { slot.values[k].push(patch[k]); });
    }
    // AND ONLY WHAT IS ACTUALLY DIFFERENT.
    //
    // Setting a trace to the value it already holds cannot change the
    // picture, and it is not free: it is uploaded and the scene is rebuilt
    // like any other change. Every part of a shape was being handed its
    // strength on every press, whatever the press was about -- so fading
    // where two shapes AGREE, which only ever touches the one surface that
    // carries the mask, was rewriting the strength of all 347 traces of the
    // comparison cage as well, to the number they were already at.
    //
    // Comparing first is exact rather than a guess about what a press
    // "should" touch: if the value is the same, restyling it is a no-op by
    // definition, so nothing can be missed by leaving it out.
    function differs(had, want) {
      if (Array.isArray(want)) {
        if (!Array.isArray(had) || had.length !== want.length) return true;
        for (var i = 0; i < want.length; i++)
          if (had[i] !== want[i]) return true;
        return false;
      }
      return had !== want;
    }
    dressing.forEach(function (part) {
      var t = part.gd.data[part.at];
      if (!t) return;
      var patch = {}, any = false, meant = null;
      // THE KEY KEEPS ITS FULL STRENGTH AND ITS COLOUR unless the reader
      // asked for grey, in which case it follows -- otherwise the list of
      // names would go on showing colours the picture no longer has.
      if (!part.proxy) {
        // NOT SET MEANS FULLY SOLID, which is the same thing as 1 and must
        // compare equal to it. Without this the very first press rewrote the
        // strength of all 344 traces of the cage -- from "not stated" to
        // "1" -- which is a rebuild of the scene to draw exactly what was
        // already on it. Measured: 359 ms of a 500 ms press.
        var strength = (t.opacity === undefined ? 1 : t.opacity);
        // EACH PART KEEPS ITS OWN SHARE OF THE STRENGTH.
        //
        // The slider is one number for the whole shape, and its parts do not
        // all start at the same place -- a skin at 0.3 under a cage at 1. So
        // the shape's strength is applied as a RATIO of what it opened at,
        // which has the property that matters: back at the strength it was
        // saved with, every part is handed exactly its own opening value,
        // and "as saved" is exact rather than approximately right.
        var mine = (typeof part.opened === "number") ? part.opened
                                                     : g.opened.opacity;
        var share = g.opened.opacity ? (st.opacity / g.opened.opacity) : 1;
        var want_op = (st.opacity === g.opened.opacity)
          ? mine : Math.max(0, Math.min(1, mine * share));
        meant = on("opacity", true) ? want_op : strength;
        if (on("opacity", true) && differs(strength, want_op)) {
          patch.opacity = want_op; any = true;
        }
        if (on("wires", true) && g.fill && t.fill !== undefined) {
          var fill = st.filled ? "toself" : "none";
          if (differs(t.fill, fill)) { patch.fill = fill; any = true; }
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
      // THE SOLID REMAINDER IS DRAWN GENUINELY SOLID.
      //
      // One vertex below alpha 1 puts the whole mesh on the library's
      // transparent path, which never writes the depth buffer -- so with one
      // group faded to NOTHING and the other left at full strength, the
      // "solid" remainder only hid what lay behind it when the per-frame
      // triangle sort got every pixel right, which a sort of triangles
      // cannot promise. Reported from the page comparing a paper with Adobe
      // RGB, agreement at 0%: "it is like i am looking through the remaining
      // shape although the part is solid". Measured there: up to 4,062
      // pixels per view painted with a piece that lay BEHIND a solid one,
      // sixteen views, with the comparison outline shown and hidden alike.
      //
      // So at the fade's ENDS the invisible triangles are removed and the
      // colours left plain: nothing on the transparent path, the depth
      // buffer back in charge, and the same sixteen views measured again at
      // 0 wrongly-covered pixels. Anything strictly between 0 and 1 -- an
      // intermediate slider, a straddling triangle on a mesh that was not
      // re-cut, a shape strength below 1 -- keeps the path it always had,
      // to the byte. The full triangle list is remembered through the same
      // store the colours use, so sliding back up always restores it. The
      // Python that draws the window and writes these pages does the very
      // same thing -- see _solid_remainder.
      var plainRemainder = false;
      if (fading && t.type === "mesh3d" && t.i && t.j && t.k) {
        // FROM THE DRAWN DATA, NOT THE WRITTEN FILE. A saved page stores its
        // triangle lists binary-packed ({dtype, bdata}), which has no length
        // and no elements to walk -- read off gd.data this whole block ran,
        // matched nothing, and silently did nothing. The library's _fullData
        // carries the decoded lists; they are copied to plain arrays ONCE,
        // into the same store the colours use, so every later press compares
        // and restores real numbers.
        var full = (part.gd._fullData || [])[part.at] || t;
        var di = (full.i && full.i.length !== undefined) ? full.i : t.i;
        var dj = (full.j && full.j.length !== undefined) ? full.j : t.j;
        var dk = (full.k && full.k.length !== undefined) ? full.k : t.k;
        if (di && di.length !== undefined) {
          var iAll = was(part, "i", Array.prototype.slice.call(di)),
              jAll = was(part, "j", Array.prototype.slice.call(dj)),
              kAll = was(part, "k", Array.prototype.slice.call(dk));
          var ni = iAll, nj = jAll, nk = kAll;
          var ends = (meant === null
                      ? (t.opacity === undefined ? 1 : t.opacity)
                      : meant) === 1
            && (agreeAt === 0 || agreeAt === 1)
            && (differAt === 0 || differAt === 1)
            && (agreeAt < 1 || differAt < 1);
          if (ends) {
            var ki = [], kj = [], kk = [], whole = true, f;
            for (f = 0; f < iAll.length; f++) {
              var fa = mark.charAt(iAll[f]) === "1" ? differAt : agreeAt;
              var fb = mark.charAt(jAll[f]) === "1" ? differAt : agreeAt;
              var fc = mark.charAt(kAll[f]) === "1" ? differAt : agreeAt;
              if (fa === 0 && fb === 0 && fc === 0) continue;  // invisible
              if (fa < 1 || fb < 1 || fc < 1) { whole = false; break; }
              ki.push(iAll[f]); kj.push(jAll[f]); kk.push(kAll[f]);
            }
            // ONLY when every triangle still drawn is wholly solid AND
            // something was actually removed; an empty remainder is the
            // shape that agrees everywhere, which fades away whole exactly
            // as before.
            if (whole && ki.length && ki.length < iAll.length) {
              ni = ki; nj = kj; nk = kk; plainRemainder = true;
            }
          }
          // AGAINST WHAT IS DRAWN NOW, element for element -- `differs`
          // cannot read the written file's binary-packed lists, and a patch
          // that is not needed is a scene rebuild for nothing.
          var q = 0, same = ni.length === di.length;
          if (same) for (q = 0; q < ni.length; q++)
            if (ni[q] !== di[q]) { same = false; break; }
          if (!same) {
            patch.i = ni; patch.j = nj; patch.k = nk; any = true;
          }
        }
      }
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
          // ... unless the solid remainder above took over: then the colours
          // stay plain on purpose, because one rgba vertex is enough to put
          // the whole mesh back on the transparent path.
          if (fading && !plainRemainder
              && field === "vertexcolor" && Array.isArray(want)) {
            want = want.map(function (colour, at) {
              return withAlpha(colour,
                mark.charAt(at) === "1" ? differAt : agreeAt);
            });
          }
          // ONE VALUE FOR THIS ONE TRACE. The wrapping that restyle needs --
          // a list with one entry per trace -- is done when the group is
          // handed over, so an array of 491 vertex colours arrives as one
          // trace's worth rather than as 491 traces' worth. Getting that
          // wrong fails silently and looks like a rendering bug: the colours
          // quietly became the single string "rgb(15,12,21)" and the whole
          // surface turned that colour.
          if (!differs(had, want)) return;
          patch[field] = want;
          any = true;
        });
      }
      if (any) later(part, patch);
    });
    if (window.Plotly) {
      Object.keys(groups).forEach(function (id) {
        var slot = groups[id];
        if (!slot.at.length) return;
        window.Plotly.restyle(slot.gd, slot.values, slot.at);
      });
    }
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
         // THE CUT'S HEIGHT IS ONLY WORTH REMEMBERING WHEN THERE IS A CUT.
         //
         // On a page carrying both views, the strip is built first for the
         // SHAPES, where there is no cross-section and cutAt is 0 by
         // default. Storing that 0 and restoring it a moment later, when the
         // reader switches to the cut, threw away the height the page was
         // saved at: a page written at L* 50 opened its cut at L* 8, the
         // bottom of the range, while carrying at: 21 all along.
         shapes: dressed, agreeAt: agreeAt, ranges: ranges,
         ...(cuts ? {cutAt: cutAt} : {}),
         chosen: chosen, carries: carries,
         differAt: differAt,
         mode: mode, turn: turn.mode, tilt: tilt.mode}));
    } catch (e) {}
  }
  // A REMEMBERED CHOICE MUST NEVER BE ABLE TO SHUT THE READER OUT.
  //
  // What is remembered is applied while the page is opening, so anything
  // that goes wrong applying it goes wrong again on the next load, and
  // again after that. Reloading is the ONE thing a reader can do -- there
  // is no console on a phone and no menu on this page -- and it is exactly
  // the thing that would not help.
  //
  // It happened. A press of "where they agree" on the page comparing a
  // paper with Adobe RGB asked for 349 rebuilds of the scene, the phone
  // stopped responding, and reloading replayed the same 349 rebuilds while
  // the page was opening. The rebuilds are fixed; this makes the trap
  // itself impossible, whatever causes it next time.
  //
  // A mark is written before the stored choices are applied and cleared
  // once the page is up. Finding it still there means the last attempt
  // never finished, so the choices are thrown away and the page opens the
  // way it was saved -- which is always a state that works, because it is
  // the one the file was written in.
  var OPENING = STORE + ":opening";
  function busy() {
    try { localStorage.setItem(OPENING, "1"); } catch (e) {}
  }
  function opened() {
    try { localStorage.removeItem(OPENING); } catch (e) {}
  }
  //: Cleared on a LATER FRAME, never straight away. Reaching a frame is the
  //: closest thing there is to proof that the browser is still answering the
  //: reader, which is the whole question being asked.
  function settled() {
    if (window.requestAnimationFrame)
      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(opened);
      });
    else window.setTimeout(opened, 300);
  }
  function recall() {
    try {
      if (localStorage.getItem(OPENING)) {
        localStorage.removeItem(OPENING);
        localStorage.removeItem(STORE);
        return;
      }
      var was = JSON.parse(localStorage.getItem(STORE) || "null");
      if (!was) return;
      busy();
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
      // ONLY IF THIS PAGE GAVE THEM THE SWITCH. Restoring a choice made on
      // some other page at the same address, onto a page whose sender did not
      // hand the switch over, would leave the reader with behaviour they can
      // see and cannot change.
      if (typeof was.carries === "boolean" && on("glide", false))
        carries = was.carries;
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
    // `wide` may name a class of its own. Three groups need a wider column
    // than the rest and they need three different widths, because what sets
    // the width is the widest ROW the group actually holds -- see the CSS.
    var extra = wide === true ? " cq-wide" : (wide ? " " + wide : "");
    body += '<div class="cq-sect' + extra + '">'
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
  // AND ON A TOUCH SCREEN, SAY WHICH FINGERS DO WHAT.
  //
  // The picture takes a one-finger vertical drag as a page scroll now, so
  // that the controls and the numbers below it can be reached at all (see
  // gestures() for the measurement behind that). Somebody who tries to tip
  // the shape with one finger and gets the page moving instead has met a
  // change in behaviour, and a change nobody explains reads as a fault.
  //
  // ONLY WHERE IT APPLIES. `(hover: none) and (pointer: coarse)` is the pair
  // that means "a finger, not a mouse" -- either one alone catches the wrong
  // devices, a touch-screen laptop most obviously. A reader with a mouse
  // never sees this, because for them nothing whatever has changed.
  head += '<span class="cq-fingers" hidden>Two fingers turn and tip it &middot;'
    + ' one finger scrolls the page</span>';
  bar.innerHTML = head;
  try {
    if (window.matchMedia
        && window.matchMedia("(hover: none) and (pointer: coarse)").matches) {
      var fingers = bar.querySelector(".cq-fingers");
      if (fingers) fingers.hidden = false;
    }
  } catch (e) { /* an old browser simply does not get the hint */ }

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
  section("how it moves", moves, "cq-turns");

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
  // NOT ON A FLAT CUT. A cross-section is drawn looking straight down and
  // cannot be turned at all, so there is nothing for a throw to carry.
  if (!flat && on("glide", false))
    looking += row("glide", "when you let go",
      "Whether the shape carries on turning for a moment after you let go of "
      + "it, instead of stopping the instant your finger or the mouse button "
      + "lifts. It slows to a stop on its own in about a second. Switch it "
      + "off to have the shape stay exactly where you left it.");
  section("where you look from", looking, "cq-looks");

  var each = "";
  // WHERE THEY AGREE, ABOVE THE SHAPES IT ACTS ON. It belongs in this group
  // rather than with the grid and the lettering, because it is about the
  // shapes themselves -- and it goes first because it is the one control
  // here that acts on all of them at once, so reading down the group runs
  // from "all of them" to "this one".
  if (agreed && anyAgrees && on("agree", true)) {
    each += '<div class="cq-row"><span>where they agree</span>'
      + '<span class="cq-ctl">'
      + group(button("agree-less", "&minus;",
          "Fade away the part that every shape reaches, so that what is left "
          + "standing is only where they differ. Two papers drawn over each "
          + "other are mostly the same paper: the part they share is the bulk "
          + "of both, it is drawn twice, and it sits in front of the very "
          + "thing you are comparing them to see. "
          // THE SAME EXPLANATION AS THE WINDOW'S, SHORTENED TO A TOOLTIP.
          // Four reports of one thing -- "shattered", "the outer edge from
          // the inside" -- and the measurement said the picture is right:
          // what is left at the bottom is an OPEN shell, and its far wall is
          // lit like an outside because there is no separate inside to shade.
          // Capping the opening is a design decision nobody has taken; saying
          // so costs nothing and answers the question where it is asked.
          + "At the very bottom what is left is an open shell, so from some "
          + "angles you are looking into it and its far wall reads as an "
          + "outer surface — that is the shape being hollow, not broken. "
          + "Come up one press and it is whole again, merely faint.")
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
    if (anyDiffers)
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
        + "opens on whichever it was saved in. follow you takes its cue from "
        + "the machine reading it: dark if that machine is set to dark, light "
        + "if it is set to light, and it changes over by itself if you switch "
        + "at dusk with the page still open — that is the one to save when "
        + "you do not know where the page is going, because a dark page "
        + "dropped into somebody's light document arrives as a black "
        + "rectangle in the middle of it. It needs nothing installed and no "
        + "internet; a browser too old to be asked is treated as light. "
        + "none takes the background "
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
      + "grid-template-columns:repeat(auto-fit,minmax(430px,1fr))}"
      // A COLUMN WIDE ENOUGH FOR THE WIDEST ROW IN *THIS* GROUP.
      //
      // 230px is right for a group of switches and much too narrow for a
      // group whose rows carry five controls. Where a row does not fit, its
      // controls wrap to a second line UNDER the name -- and in a grid of two
      // columns that puts one row's buttons level with the next column's
      // name, which is the very "which buttons belong to which option"
      // complaint these columns were rearranged to answer.
      //
      // MEASURED ON A REAL PAGE at three window widths, rather than chosen:
      //
      //   group                 widest row needs   plain 230px column gives
      //   how it moves               452px            445px at 1000px wide
      //   where you look from        384px            372px at  844px wide
      //
      // Both missed, and "left & right" missed by SEVEN PIXELS -- which is
      // why this was invisible on every desktop and showed up on a phone held
      // sideways. The numbers below are those two, rounded up.
      //
      // min(100%,...) IS THE PART THAT MATTERS ON A PHONE. A bare 470px
      // minimum on a 320px screen asks for a track wider than the panel, and
      // the row overflows sideways instead of stacking. Clamped to the width
      // available it simply becomes one column, which is what a phone wants.
      + ".cq-spin-panel .cq-turns .cq-rows{"
      + "grid-template-columns:repeat(auto-fit,minmax(min(100%,470px),1fr))}"
      + ".cq-spin-panel .cq-looks .cq-rows{"
      + "grid-template-columns:repeat(auto-fit,minmax(min(100%,400px),1fr))}"
      // THE NAME SHORTENS; THE ROW DOES NOT BREAK.
      //
      // This was `wrap`, and wrapping is what a browser does BEFORE it
      // shrinks anything: given a name that wants 288px, controls that need
      // 181 and a 456px row, it puts the controls on a second line rather
      // than take 25px off a name that is explicitly allowed to give them up.
      // So the ellipsis added for exactly this case never once fired, and a
      // shape's buttons sat under its name beside the next shape's name --
      // the fault this was all meant to fix, still there on a long name.
      //
      // Measured on a page whose shape is called "Glossy-paper — red is out
      // of reach": wrapped at 1024x1366 and at 2560x1440, in both engines.
      // A phone puts the wrap back, further down, where a name and three
      // buttons genuinely cannot share a line.
      + ".cq-spin-panel .cq-shape{flex-wrap:nowrap}"
      // AND THE BUTTONS THEMSELVES DO NOT BREAK EITHER.
      //
      // Stopping the ROW from wrapping was half of it: the name then shortened
      // as intended, and the three buttons -- which are their own flex box --
      // wrapped INSIDE it instead, so one still dropped to a second line. Same
      // fault, one level down, and it survived the first fix.
      //
      // Pinned at their natural width and forbidden to break, they are the
      // fixed part of the row and the name is the part that gives, which is
      // the right way round: a shortened name still reads (and the whole of it
      // is in the tooltip), where a button on its own under a name reads as
      // belonging to something else.
      + ".cq-spin-panel .cq-shape .cq-ctl"
      + "{flex:0 0 auto;flex-wrap:nowrap}"
      // AND THE NAME DOES NOT PUSH THEM OFF THE LINE. Set to grow, it took
      // every spare pixel of the row and the four controls beside it wrapped
      // underneath -- so on an iPad held sideways the shape's own buttons sat
      // on a second line, under a name, next to another shape's name. That is
      // the "issues finding the glossy paper controls". It takes what it needs
      // and no more, and still shortens with an ellipsis when there is not
      // enough room for the whole name.
      + ".cq-spin-panel .cq-name{flex:0 1 auto;min-width:0;overflow:hidden;"
      + "text-overflow:ellipsis;white-space:nowrap}"
      + ".cq-spin-panel .cq-back span:first-child{opacity:.6}"
      // The note runs the width of the group and reads as an aside, not as a
      // row with a missing control on the right-hand side.
      + ".cq-spin-panel .cq-aside{opacity:.55;margin:6px 0 0;"
      + "font-size:.92em;line-height:1.35;display:block}"
      + ".cq-spin-panel .cq-aside[hidden]{display:none}"
      // A CONTROL STAYS NEAR THE NAME IT BELONGS TO.
      //
      // The row was `justify-content:space-between`, which pins the name to
      // the left of its column and the buttons to the right. In one column
      // that reads well. The lists flow into as many columns as the width
      // allows, and on an iPad held sideways the panel is 1120px across --
      // four columns, each about 257px, and the buttons end up some 150px
      // from the word they act on. Reported as "the buttons themselves are
      // often quite far away from the option name and i had issues finding
      // the glossy paper controls".
      //
      // Two columns instead: the name takes what it needs up to a ceiling,
      // and the buttons follow straight after it. The ceiling is what keeps
      // the rows lined up under each other -- without it every row would
      // start its buttons at a different place and the group would read as a
      // ragged edge. And a real gap is kept: pushed together they read as one
      // object and the eye has nothing to separate the label from the button
      // it labels. 14px is about a word space at this size.
      + ".cq-spin-panel .cq-row{display:grid;align-items:center;"
      + "grid-template-columns:minmax(0,12.5em) auto;"
      + "justify-content:start;gap:14px}"
      + ".cq-spin-panel .cq-ctl{display:flex;gap:5px;align-items:center;"
      + "flex-wrap:wrap;justify-content:flex-start}"
      // The shape rows keep their own flow: a name that can run long, then
      // four controls that must be allowed to wrap under it on a narrow
      // screen rather than being squeezed.
      + ".cq-spin-panel .cq-row.cq-shape{display:flex;"
      + "justify-content:flex-start;gap:12px}"
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
      // EVERY GROUP NAMED, because the three above are more specific than
      // the plain `.cq-rows` and would otherwise keep their own columns here
      // and ignore the tighter gap a phone is given.
      + ".cq-spin-panel .cq-rows,.cq-spin-panel .cq-wide .cq-rows,"
      + ".cq-spin-panel .cq-turns .cq-rows,.cq-spin-panel .cq-looks .cq-rows"
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
      // NEVER TALLER THAN WHAT IT OPENS INTO, at any height, and the "any
      // height" is the fix. This cap lived behind @media (max-height:560px),
      // which is a phone held upright and nothing else -- so a viewport of,
      // say, 608 px got no cap at all and the panel grew to 684 px, TALLER
      // THAN THE THING IT SAT IN. Measured on a framed page at 390x780: the
      // way back ("less…") ended up at y=-247, above the visible area, with
      // 1561 px of content in a 608 px frame. Reported from an iPhone: "they
      // fill the whole frame and i can't see the less button any more so i
      // can't close them and effectively can't see the shape again".
      //
      // A control that cannot be shut is worse than one that was never
      // offered, so the panel is now capped wherever it is opened -- 60vh in
      // the ordinary case, and the old tighter 46vh on a short screen where
      // the picture needs what is left. It scrolls inside itself, and the
      // strip that opened it stays exactly where it was.
      + ".cq-spin-panel{max-height:60vh;overflow-y:auto}"
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
  function schemeName(which) {
    return which === "follow" ? "follow you" : which;
  }
  function nextScheme() {
    var at = schemes.indexOf(mode);
    return schemes[(at < 0 ? 0 : at + 1) % schemes.length];
  }
  // WHICH PALETTE "follow you" MEANS AT THIS MOMENT. Not a palette of its
  // own: it is dark or light, decided by the reader's own system setting, so
  // a page dropped into somebody else's light document stops being a black
  // rectangle in the middle of it. A browser too old to answer is treated as
  // light, because a page that cannot ask is most likely being printed or
  // read in a plain document.
  function theirs() {
    try {
      if (window.matchMedia
          && window.matchMedia("(prefers-color-scheme: dark)").matches)
        return "dark";
    } catch (e) {}
    return "light";
  }
  // AND IT KEEPS FOLLOWING. Somebody who turns their machine dark at dusk
  // with the page still open should watch it follow, not have to reload.
  // Attached once; it does nothing unless the page is on "follow you".
  try {
    if (window.matchMedia) {
      var watch = window.matchMedia("(prefers-color-scheme: dark)");
      var react = function () { if (mode === "follow") applyMode(); };
      if (watch.addEventListener) watch.addEventListener("change", react);
      else if (watch.addListener) watch.addListener(react);
    }
  } catch (e) {}

  function applyMode() {
    if (!palettes) return;
    var p = palettes[mode === "follow" ? theirs() : mode] || palettes.dark;
    if (!p) return;
    ink = p.text; paper = p.page;
    paint();
    document.documentElement.style.background = p.page;
    document.body.style.background = p.page;
    // AND THE FIGURES UNDERNEATH, which are part of the page.
    //
    // They are written into the file with their colours stated on the
    // element, from the palette the page was saved in -- so they did not
    // follow, and switching a page saved dark over to "light" left a black
    // block of text under a pale picture. On "ink", the one colouring whose
    // whole purpose is being printed, it left a solid black rectangle across
    // the bottom of the page.
    //
    // Nothing about the numbers changes; they are the same numbers on every
    // colouring. Only what they are written on.
    var written = document.querySelectorAll(".cq-notes");
    for (var w = 0; w < written.length; w++) {
      written[w].style.color = p.text;
      written[w].style.background = p.page;
    }
    // AND THE SLIDER'S OWN WORDS, which are written with the colours the file
    // was saved in and were being left behind by every change of colouring.
    //
    // Reported from a phone: "the text that belongs to the hide anything under
    // slider is hard do read". Measured on that page: 1.17:1 against the
    // paper, where everything else on it is 15.13:1 — the light palette's
    // near-black ink sitting on a dark page, which is the same fault as the
    // control strip that stayed light, in a third place.
    //
    // The accent goes too, or the slider's handle keeps the old ink while its
    // label changes.
    var cut = document.getElementById("cq-cut");
    if (cut) {
      cut.style.color = p.text;
      var runner = cut.querySelector("input[type=range]");
      if (runner) runner.style.accentColor = p.text;
    }
    if (flat) {
      relayout({"paper_bgcolor": p.page, "plot_bgcolor": p.plot,
                "font.color": p.text,
                "xaxis.gridcolor": p.grid, "yaxis.gridcolor": p.grid,
                "xaxis.zerolinecolor": p.grid, "yaxis.zerolinecolor": p.grid,
                // READING MATTER, not a caption -- see the 3D case below.
                "xaxis.color": p.text, "yaxis.color": p.text,
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
              // THE AXIS LETTERING IS READING MATTER, not a caption. This
              // said p.caption, which is the dim grey the small title line
              // is drawn in -- so pressing this button dimmed every axis
              // number and name, and returning to the colouring the page
              // was saved in did not bring them back. The title keeps
              // caption below, because a title IS a caption.
              "scene.xaxis.color": p.text,
              "scene.yaxis.color": p.text,
              "scene.zaxis.color": p.text,
              "legend.font.color": p.text,
              "title.font.color": p.caption});
    say("appearance", schemeName(mode));
  }

  function push() {
    // NOTHING TURNS ON A FLAT CUT, whatever a stored choice from some other
    // page or an older version of this one might say.
    if (flat) running = false;
    window.cqSpin.set(
      {on: running, glide: carries && !flat,
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
    press("glide", carries);
    // FROM THE ONE PLACE EVERY HANDLER ALREADY PASSES THROUGH. Hung off the
    // plural tellShapes() instead, it was missed by every per-shape press --
    // which calls the singular one -- so fading a shape to nothing left the
    // button still claiming the page was as it was saved.
    tellMore();
    if (on("remember", true)) remember();
    // AND THE PRESS SURVIVED. Everything the handler was going to do has
    // been done and the page is still answering, so the mark set on the way
    // in comes off -- on a later frame, because that is what proves it.
    settled();
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
  // BRING THE CONTROLS TO THE READER, BECAUSE ON A PHONE THEY CANNOT COME TO
  // THEM.
  //
  // The picture carries `touch-action: none`. It has to: without it the
  // browser reads a drag as a page scroll and stops delivering the moves a
  // pinch is made of. But `touch-action: none` also means the browser will
  // never scroll the page from a touch that STARTS on the picture -- and by
  // this project's own layout rule the picture is 55% to 85% of the first
  // screen. So the bigger and better the picture, the less of the screen is
  // left that a scroll can begin from.
  //
  // MEASURED, WebKit, walking down the middle of the screen a row at a time:
  // 74-80% of the first screen cannot start a scroll, on every 3D page this
  // application has ever written, while the panel ran 411px (page 01) to
  // 1005px (page 14) past the bottom of the window.
  //
  // Basti found the one way round it that a reader can find by accident:
  // "when i slightly zoom in the controls area on my phone i can then
  // scroll, but when the page fits the screen i can't". Zooming makes the
  // visual viewport smaller than the page, and panning THAT is always
  // allowed, whatever touch-action says.
  //
  // So the page scrolls itself. Nothing about the gestures changes -- one
  // finger still turns the shape, which is the whole reason touch-action is
  // there -- and pressing "more…" now puts the controls where the reader can
  // see them, on a phone and on anything else too small to hold both.
  function reachPanel() {
    if (!panel.scrollIntoView) return;             // very old browser
    if (panel.hidden) {
      // CLOSING PUTS THE PICTURE BACK. Having scrolled somebody down to the
      // controls, leaving them looking at empty page when they press "less…"
      // would be the same fault in the other direction.
      window.scrollTo({top: 0, behavior: "smooth"});
      return;
    }
    var box = panel.getBoundingClientRect();
    // Already all on screen: scrolling would only move the picture for
    // nothing. The 4px is for the rounding two engines disagree about.
    if (box.bottom <= window.innerHeight + 4) return;
    // WHEN IT CANNOT ALL FIT, THE WAY BACK WINS. Scrolling the panel into
    // view pushes the strip that opened it off the top -- measured inside a
    // framed page at 390x780: "less…" ended up at y=-4, four pixels above the
    // visible area, which is as unreachable as four hundred. Reported from an
    // iPhone: "i can't see the less button any more so i can't close them".
    //
    // So the STRIP is brought to the top instead. The panel is capped and
    // scrolls inside itself, so everything in it is still reachable, and the
    // one control that must never be lost is the one that is guaranteed.
    // AND IT SCROLLS THIS PAGE ONLY. scrollIntoView walks up through every
    // ancestor, and inside a frame that ancestor is somebody ELSE'S page: the
    // showcase scrolled itself whenever a reader opened the controls, which
    // is how the strip left the top of the frame -- y=-114, measured, worse
    // than the fault it was meant to cure. Reported as "clicking the more
    // button for controls scrolls down a bit on the whole page".
    //
    // Computing the offset and scrolling this window moves this document and
    // nothing above it, framed or not.
    if (bar) {
      var top = bar.getBoundingClientRect().top
                + (window.pageYOffset || document.documentElement.scrollTop || 0);
      window.scrollTo({top: Math.max(0, top - 6), behavior: "smooth"});
      return;
    }
    // "nearest" rather than "start": where the panel does fit once scrolled
    // to, this stops as soon as it is all visible instead of pushing the
    // picture off the top regardless.
    panel.scrollIntoView({block: "nearest", behavior: "smooth"});
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
    // MARKED BEFORE THE WORK, NOT AFTER IT. If this press is the one that
    // never finishes, the mark is still set when the page is next opened,
    // and the choices that led here are thrown away rather than replayed.
    // Set only at the end -- or only when the page opens -- a reader would
    // have had to reload twice to get out, and nobody reloads twice.
    busy();
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
      reachPanel();
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
    if (what === "glide") carries = !carries;
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
  // AT LOAD, AND ALWAYS WHEN THE COLOURING HAS TO BE WORKED OUT. This ran
  // only when the remembered colouring DIFFERED from the saved one, which is
  // right for a fixed palette and wrong for "follow you": a page saved that
  // way has mode === settings.mode, so nothing ran and the reader got the
  // static colours the file was written with. Measured before this line
  // changed: pressing the button round to "follow you" worked perfectly and
  // saving a page as "follow you" did nothing at all -- the feature looked
  // finished from inside the window and was not.
  if (mode === "follow" || mode !== (settings.mode || "dark")) applyMode();
  push();
  // THE PAGE IS UP -- said on a later frame, so the mark survives anything
  // that stops the browser reaching one, including the tab being killed for
  // using too much memory, which is how a phone ends a page that will not
  // respond.
  settled();
};
"""


def write_two_views_html(views, out: Path, mode: str = "dark", spin=None,
                         controls: bool = True, offer=None,
                         notes: str = "") -> Path:
    """One page holding the shells AND a cut through them, with a switch.

    Asked for from the window: "could the exported web viewer files get a
    toggle to switch between the view of the shells and the sliced view ... the
    other controls would then have to update accordingly".

    WHY THIS IS A NEW WRITER AND NOT A FLAG ON ANOTHER. A page has always
    carried one KIND of picture, chosen when it was saved, and every writer
    reads that choice once and builds around it. Two kinds in one file is a
    different shape of page — two figures, one shown — and pretending otherwise
    would put an "if" in the middle of four writers instead of one place.

    WHAT IT COSTS, and it is the reason the choice belongs to whoever saves:
    the viewer that dominates the file is carried once either way, so the
    second view costs only its own data. The scene is a mesh; the cut is a set
    of rings. Measured on the demo pair, a page with both is about a tenth
    larger than a page with the scene alone.

    *views* is [(caption, figure), (caption, figure)] — the shells first, the
    cut second, because that is the order the switch offers them in and the
    first is the one the page opens on.
    """
    import plotly.io as pio
    from html import escape as html_escape

    colours = static_palette(mode)
    blocks, ids = [], []
    for i, (caption, fig) in enumerate(views):
        flat = not any(getattr(t, "type", "") in ("scatter3d", "mesh3d")
                       for t in fig.data)
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
        if not flat:
            fig.update_layout(scene=dict(domain=dict(x=[0, 1], y=[0, 1])))
        div = pio.to_html(fig, include_plotlyjs=(i == 0), full_html=False,
                          div_id=f"scene{i}",
                          config={"displaylogo": False, "responsive": True,
                                  "scrollZoom": True, **_MODEBAR_ONLY})
        ids.append(f"scene{i}")
        # THE SECOND ONE IS BUILT AND HIDDEN, not built when it is asked for.
        # A picture drawn on demand is a picture the reader waits for, and the
        # data is already in the file either way.
        blocks.append(
            f'<div class="cq-view" data-view="{i}"'
            f'{"" if i == 0 else " hidden"}>'
            f'<div class="cap">{caption}</div>{div}</div>')

    switch = (
        '<div class="cq-views" style="display:flex;gap:.6em;'
        'justify-content:center;padding:.6em 0">'
        + "".join(
            f'<button type="button" data-cq="view" data-goes="{i}"'
            f'{" aria-pressed=\"true\"" if i == 0 else ""}>'
            f'{caption}</button>'
            for i, (caption, _fig) in enumerate(views))
        + "</div>")

    turn = _spin_script(ids, spin, mode, controls, offer)
    swap = """<script>
// THE SWITCH, AND WHAT IT TELLS THE REST OF THE PAGE.
//
// Showing the other picture is the easy half. The half that was asked for is
// that the controls follow: the movement engine decides what a control may do
// by asking each picture whether it is flat, so it is handed the ids that are
// SHOWING and works the rest out itself — the camera and the turning for the
// shells, the lightness for the cut.
(function () {
  var views = [].slice.call(document.querySelectorAll(".cq-view"));
  var buttons = [].slice.call(
    document.querySelectorAll('button[data-cq="view"]'));
  function show(which) {
    views.forEach(function (v, i) { v.hidden = (i !== which); });
    buttons.forEach(function (b, i) {
      if (i === which) b.setAttribute("aria-pressed", "true");
      else b.removeAttribute("aria-pressed");
    });
    var live = views[which].querySelector(".js-plotly-plot");
    if (live && window.Plotly) window.Plotly.Plots.resize(live);
    // AND THE STRIP IS REBUILT FOR THE PICTURE THAT IS SHOWING. This is the
    // half the switch was asked for: "the other controls would then have to
    // update accordingly so the user can manipulate each view in a way that
    // makes sense for it".
    //
    // The strip already knows how — it drops the turning controls when it is
    // told the picture is flat — but it is told ONCE, when the page loads. So
    // it is handed the page's own settings again with two things changed: the
    // id that is showing, and whether that one is flat. Handing it anything
    // less rebuilds it from nothing, which is measured: with only the ids it
    // came back with no controls at all.
    if (!live || !window.cqSettings) return;
    var flat = !(live._fullLayout && live._fullLayout.scene);
    var s = {};
    for (var k in window.cqSettings) s[k] = window.cqSettings[k];
    s.ids = [live.id];
    s.flat = flat;
    if (window.cqSpin) window.cqSpin.set(s);
    if (window.cqSpinControls) {
      var old = document.querySelector(".cq-spin-bar");
      var panel = document.querySelector(".cq-spin-panel");
      if (old && old.parentNode) old.parentNode.removeChild(old);
      if (panel && panel.parentNode) panel.parentNode.removeChild(panel);
      window.cqSpinControls(s);
    }
  }
  buttons.forEach(function (b, i) {
    b.addEventListener("click", function () { show(i); });
  });
  window.addEventListener("load", function () { show(0); });
})();
</script>"""

    written = (f'<div class="cq-notes" style="font:13px/1.6 -apple-system,'
               f'BlinkMacSystemFont,sans-serif;color:{colours["text"]};'
               f'background:{colours["page"]};max-width:46em;margin:0 auto;'
               f'padding:0 1.5em 1.5em">{notes}</div>') if notes else ""
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html_escape(views[0][0])}</title><style>
 html {{ height:100%; }}
 body {{ margin:0; padding:0; min-height:100%; background:{colours['page']};
         color:{colours['text']}; display:flex; flex-direction:column; }}
 .cq-view {{ flex:1 1 auto; min-height:62vh; width:100%; }}
 .cq-view[hidden] {{ display:none; }}
 .cap {{ font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
         color:{colours['caption']}; padding:.6em 1.2em 0; }}
 .cq-views button {{ font:inherit; cursor:pointer; border-radius:999px;
        padding:.45em .95em; border:1px solid {colours['grid']};
        background:transparent; color:inherit; }}
 .cq-views button[aria-pressed] {{ border-color:{colours['text']}; }}
</style></head><body>{switch}{''.join(blocks)}{written}
<script>{_ORDER_JS}</script><script>{_WHEEL_JS}</script><script>{_CAPTION_JS}</script>{turn}{swap}
</body></html>"""
    Path(out).write_text(html, encoding="utf-8")
    return Path(out)


def write_side_by_side_html(pages, out: Path, mode: str = "dark",
                            linked: bool = True, spin=None,
                            controls: bool = True, offer=None,
                            notes: str = "", stacked: bool = False) -> Path:
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

    # ONE ABOVE THE OTHER, WHEN THAT IS WHAT WAS ASKED FOR. Both
    # arrangements are worth having: side by side keeps the two shapes at the
    # same height, which is what the eye needs to compare how far each one
    # reaches; one above the other gives each the whole width, which is what a
    # tall narrow window has to spare. Neither is a way of avoiding a cut
    # shape -- each room pulls its own view back far enough for that,
    # whichever way round they are, so this is a choice about reading rather
    # than a repair. 68vh because `scripts/check_layout.py` asks that the
    # first picture hold 55-85% of the first screen, and 56vh measured 51-54%.
    colours = static_palette(mode)
    # SINGLE BRACES. This is a plain string that is INTERPOLATED into the
    # f-string below, so doubling them the way the surrounding CSS does puts
    # `{{` into the page and the rule never applies -- which it did, and both
    # arrangements came out identical.
    # BOTH ROOMS ON SCREEN AT ONCE. Reported from the window, of the
    # arrangement this option had just added: "split in top/bottom shows the
    # bottom one nearly out of the window". It asked for 68vh EACH and lifted
    # the row's ceiling, so the two together wanted 136vh and the second sat
    # below the fold — two rooms you cannot see at the same time are not a
    # comparison, which is the whole reason to have two.
    #
    # So the row keeps the ceiling it has in either arrangement, and the two
    # halves share it: about 40vh each on a full screen, with a floor low
    # enough that a short window still shows both rather than pushing one
    # away.
    stack_css = ("" if not stacked else
                 " .row  { flex-direction:column; }\n"
                 " .half { min-height:31vh; }\n"
                 " .half + .half { border-left:none;\n"
                 "                 border-top:1px solid "
                 + colours["grid"] + "; }")
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
                                  "scrollZoom": True, **_MODEBAR_ONLY})
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
    # THE NUMBERS TRAVEL WITH THIS PAGE TOO, and until now they did not.
    # Measured by writing all four arrangements and asking each which controls
    # it built: only the single 3D scene carried a block of figures. The other
    # three -- two rooms, a cross-section, two cross-sections -- arrived with
    # the styling for one and nothing in it, from a button whose dialog had
    # just asked whether the numbers should travel.
    written = ""
    if notes:
        written = ("<div class=\"cq-notes\" style=\"font:13px/1.6 "
                   "-apple-system,Segoe UI,Roboto,sans-serif;color:"
                   f"{colours['text']};background:{colours['page']};"
                   "padding:14px 22px 78px;white-space:pre-wrap\">"
                   f"{notes}</div>")
    _t = _escape_title(" and ".join(n for n, _f in pages) or "Measured gamut")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">\
<title>{_t} — ChromIQ Gamut Viewer</title><style>
 /* THE PAGE GROWS AND SCROLLS; THE PICTURE KEEPS ITS SHARE OF THE FIRST
    SCREEN. This was `height:100%; overflow:hidden`, which means the page can
    never be taller than the window -- so when the reader opens the panel of
    controls, the only place its height can come from is the picture.
    Measured on a two-room page with the panel open: the picture down to
    **24% of a 390x844 phone**, and at 320x700 to **0%**. It vanished.
    A page cannot scroll to reveal what it has pushed off when it has been
    told never to scroll.
    The single-scene pages were given this same treatment for the same fault
    and this one was missed, because their layout is one block and this is a
    flex row -- the selector that fixed them could not match here. */
 html {{ height:100%; }}
 body {{ margin:0; padding:0; height:auto; min-height:100%;
         background:{colours['page']}; display:flex; flex-direction:column; }}
 /* 62vh is a floor rather than a share, so a long panel pushes itself below
    the fold instead of eating the shape; 80vh is the ceiling, so there is
    always something visible under the picture saying the page carries on. */
 .row  {{ display:flex; flex:1 1 auto; min-height:62vh; max-height:80vh;
          width:100%; }}
 @media (max-width:1024px) {{ .modebar {{ display:none !important; }} }}
 @media (max-width:820px) {{ .gtitle {{ font-size:11px !important; }} }}
 .half {{ flex:1 1 0; min-width:0; display:flex; flex-direction:column; }}
 .half + .half {{ border-left:1px solid {colours['grid']}; }}
{stack_css}
 /* THE ROOMS STAY SIDE BY SIDE AT EVERY WIDTH — asked for in as many
    words: "Never stack — zoom the camera out instead so the shape fits a
    narrow room. This keeps side by side at every width, which is what the
    option promises." The fitting is `fitToPane` below; what was wrong was
    its ceiling, not the idea. */
 .cap  {{ height:22px; line-height:22px; padding:0 10px; font-size:12px;
          color:{colours['caption']}; background:{colours['page']};
          font-family:Menlo,Consolas,"Courier New",monospace;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
 .half > div:last-child {{ flex:1 1 auto; min-height:0; }}
</style></head><body><div class="row">{''.join(blocks)}</div>{written}{resize}{link}<script>{_ORDER_JS}</script><script>{_WHEEL_JS}</script><script>{_CAPTION_JS}</script>{_spin_script(ids, ({"flat": True, **(spin or {})} if flat else spin), mode, controls, offer)}</body></html>"""
    Path(out).write_text(html, encoding="utf-8")
    return Path(out)


def _js(text: str) -> str:
    """One python string, safe to paste into a <script> block."""
    import json as _json

    return _json.dumps(text or "").replace("</", "<\\/")


def _say_if_the_viewer_never_arrives(html: str, mode: str) -> str:
    """A page that fetches its viewer has to say so when it cannot get it.

    Saved without the drawing library inside it, a page is a few dozen
    kilobytes instead of five megabytes -- and it fetches the library from the
    internet the first time it is opened. With no connection it drew nothing:
    a full set of controls over an empty box, saying nothing about why, which
    reads as a broken file rather than a missing download.

    WHAT DECIDES, and this took three attempts to get right.

    IT USED TO BE A TIMER. Four seconds, then "you need the internet". The
    viewer is 4.85 MB and took 2.4 s to fetch here on a good connection, so
    four seconds is a coin toss on a phone -- and Basti met exactly that: the
    page told him he had no internet while the download was still in flight.
    Worse, the notice covers the whole window, so when the viewer did arrive
    the picture was drawn behind it and stayed hidden.

    THEN IT WAS A LISTENER ADDED AT THE END OF THE PAGE. Too late: the fetch
    has usually already failed by then, the error event has come and gone, and
    a listener attached afterwards never hears it. Measured in both engines,
    with the request aborted outright: nothing was shown at all.

    SO THE HANDLERS ARE WRITTEN ONTO THE TAG, and the functions they call are
    defined immediately before it. That registers them while the page is still
    being parsed, before the fetch can resolve either way. The attribute is
    written defensively as well, because nothing here is entitled to assume
    the order a browser does things in.

    Three ways it can end, and each says something different:

      the viewer arrives   -- nothing is ever shown, and anything already
                              showing is taken away again
      the fetch fails      -- "could not be reached", promptly, which is the
                              only case where saying so is true
      neither, for 30 s    -- "taking a long time", which is not the same
                              claim and does not go away if it does arrive
    """
    c = static_palette(mode)

    # DEFINED BEFORE THE TAG THAT CALLS THEM. Both are safe to call before the
    # notice itself exists further down the page: the wish is remembered and
    # acted on when it does.
    functions = (
        "<script>\n"
        "window.cqNoViewerWanted = false;\n"
        "window.cqNoViewer = function (why) {\n"
        "  if (window.Plotly) return;\n"
        "  var n = document.getElementById('cq-noviewer');\n"
        "  if (!n) { window.cqNoViewerWanted = why || true; return; }\n"
        "  var line = n.querySelector('[data-cq=\\\"why\\\"]');\n"
        "  if (line && why) line.textContent = why;\n"
        "  n.hidden = false;\n"
        "};\n"
        "window.cqViewerCame = function () {\n"
        "  window.cqNoViewerWanted = false;\n"
        "  var n = document.getElementById('cq-noviewer');\n"
        "  if (n) n.hidden = true;\n"
        "};\n"
        "</script>\n")

    hooks = (
        ' onerror="window.cqNoViewer&&cqNoViewer(&#39;The viewer could not be '
        'reached at all \u2014 the browser reported the download as '
        'failed.&#39;)"'
        ' onload="window.cqViewerCame&&cqViewerCame()"')

    tag = re.search(r'<script[^>]*\bsrc="[^"]*plot[^"]*"', html)
    # THE ADDRESS AND THE HASH THE PAGE ITSELF USES, read back out rather than
    # written down twice. A retry that fetched a different build, or quoted a
    # hash from memory, would be blocked by the browser and look like one more
    # failure -- with no way for the reader to tell the difference.
    whole = re.search(r'<script[^>]*\bsrc="[^"]*plot[^"]*"[^>]*>', html)
    src = sri = ""
    if whole:
        found = re.search(r'\bsrc="([^"]+)"', whole.group(0))
        src = found.group(1) if found else ""
        found = re.search(r'\bintegrity="([^"]+)"', whole.group(0))
        sri = found.group(1) if found else ""
    if tag:
        html = html[:tag.start()] + functions + html[tag.start():tag.end()] \
            + hooks + html[tag.end():]

    # NAME THE SCRIPT THAT DRAWS, so a retry can run it a second time.
    #
    # WITHOUT THIS THE RETRY LOOKS LIKE IT WORKED AND IS USELESS. The call that
    # draws the picture sits in an inline script AFTER the viewer's tag, so
    # when the viewer fails that call still runs, throws because Plotly is not
    # there, and is gone. Fetching the viewer afterwards puts the library in
    # place with nothing left to ask it to draw: the notice disappears, the
    # page goes blank, and the reader is worse off than before. Measured in
    # both engines -- viewer arrived, notice gone, picture never drawn.
    html = re.sub(r'(<script[^>]*>)(\s*(?:window\.PLOTLYENV|Plotly\.newPlot))',
                  r'<script id="cq-draw">\2', html, count=1)

    note = (
        "<div id=\"cq-noviewer\" hidden style=\"position:fixed;inset:0;"
        "display:flex;align-items:center;justify-content:center;"
        f"background:{c['page']};color:{c['text']};z-index:9;"
        "font:15px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"
        "\"><div style=\"max-width:34rem;padding:2rem;text-align:left\">"
        "<p style=\"font-size:1.15rem;margin:0 0 .6rem\"><b>The 3D viewer "
        "did not arrive.</b></p>"
        "<p data-cq=\"why\" style=\"margin:0 0 .6rem\">It was saved "
        "<i>without</i> the 3D viewer inside it, which is what keeps it to a "
        "few dozen kilobytes instead of about five megabytes. The viewer is "
        "fetched when the page opens, and this time it could not be "
        "reached.</p>"
        "<p style=\"margin:0 0 .6rem\">Nothing is wrong with this file and no "
        "measurement is missing. <b>The commonest reason on a phone is that "
        "the download was interrupted</b> — switching to another app, or "
        "locking the screen, stops it, and it is about 5 MB. A network that "
        "filters or proxies downloads can stop it too. So this does not "
        "necessarily mean you are offline.</p>"
        "<p style=\"margin:0 0 1rem\">Try it again below — it keeps this page "
        "as it is. If it has to work with no connection at all, save it again "
        "from the application with <b>Put the 3D viewer inside the file</b> "
        "ticked; that makes a bigger file that never needs the internet.</p>"
        "<button type=\"button\" data-cq=\"retry\" style=\"font:inherit;"
        f"padding:.6rem 1.1rem;border-radius:8px;border:1px solid {c['text']};"
        f"background:transparent;color:{c['text']};cursor:pointer;"
        "min-height:44px\">Try to fetch the viewer again</button>"
        "<span data-cq=\"tries\" style=\"margin-left:.7rem;opacity:.75\">"
        "</span>"
        "</div></div>\n"
        "<script>(function () {\n"
        "  // A FAILURE THAT HAPPENED BEFORE THIS EXISTED is acted on now.\n"
        "  if (window.cqNoViewerWanted)\n"
        "    window.cqNoViewer(window.cqNoViewerWanted === true ? '' :\n"
        "                      window.cqNoViewerWanted);\n"
        "  // AND IF IT SIMPLY TURNS UP, whichever way, the notice goes -- so\n"
        "  // a slow arrival cannot leave the picture behind a covered\n"
        "  // window, which is what the old four-second timer did.\n"
        "  var watch = window.setInterval(function () {\n"
        "    if (window.Plotly) {\n"
        "      window.cqViewerCame(); window.clearInterval(watch);\n"
        "    }\n"
        "  }, 250);\n"
        "  // A LONG STOP, for a request that neither fails nor finishes.\n"
        "  // Thirty seconds rather than four, and it says 'taking a long\n"
        "  // time' rather than 'you have no internet', because slow is not\n"
        "  // the same as absent.\n"
        "  window.setTimeout(function () {\n"
        "    window.cqNoViewer('The viewer is taking a long time to arrive. "
        "It is about 5 MB, so this can happen on a slow connection. Leave the "
        "page open and it may still appear.');\n"
        "  }, 30000);\n"
        "  // TRY AGAIN WITHOUT LOSING THE PAGE, which is the thing a reader\n"
        "  // on a phone actually wants. Being told to reload when the line is\n"
        "  // fine is useless advice, and an interrupted download -- switching\n"
        "  // app, locking the screen -- is the commonest way this fails.\n"
        "  //\n"
        "  // A FRESH URL EACH TIME, because a failed fetch can sit in the\n"
        "  // cache and be served again instantly as the same failure. The\n"
        "  // integrity hash is over the CONTENT, not the address, so a query\n"
        "  // string cannot break it.\n"
        "  var tries = 0;\n"
        "  var note = document.getElementById('cq-noviewer');\n"
        "  var button = note && note.querySelector('[data-cq=\\\"retry\\\"]');\n"
        "  var says = note && note.querySelector('[data-cq=\\\"tries\\\"]');\n"
        "  if (button) button.addEventListener('click', function () {\n"
        "    if (window.Plotly) { window.cqViewerCame(); return; }\n"
        "    tries += 1;\n"
        "    button.disabled = true;\n"
        "    if (says) says.textContent = 'fetching\\u2026';\n"
        "    var again = document.createElement('script');\n"
        "    var where = " + _js(src) + ";\n"
        "    again.src = where + (where.indexOf('?') < 0 ? '?' : '&')\n"
        "                + 'cq-retry=' + tries;\n"
        "    again.crossOrigin = 'anonymous';\n"
        "    if (" + _js(sri) + ") again.integrity = " + _js(sri) + ";\n"
        "    again.onload = function () {\n"
        "      // RUN THE DRAWING AGAIN. The first attempt threw when the\n"
        "      // viewer was missing, so there is no picture waiting -- only\n"
        "      // the instructions for one.\n"
        "      var draw = document.getElementById('cq-draw');\n"
        "      if (draw) {\n"
        "        var run = document.createElement('script');\n"
        "        run.text = draw.textContent;\n"
        "        document.body.appendChild(run);\n"
        "      }\n"
        "      window.cqViewerCame();\n"
        "    };\n"
        "    again.onerror = function () {\n"
        "      button.disabled = false;\n"
        "      if (says) says.textContent =\n"
        "        'still no luck (' + tries + (tries === 1 ? ' try' : ' tries')\n"
        "        + ')';\n"
        "    };\n"
        "    document.head.appendChild(again);\n"
        "  });\n"
        "})();</script>\n")
    at = html.rfind("</body>")
    return html[:at] + note + html[at:] if at > 0 else html + note


def _clear_hover_streaks(html: str) -> str:
    """Stop the pointing lines leaving black streaks behind them.

    THE FAULT, AS REPORTED: "when i drag with the mouse over the shape it
    draws lines to indicate where i am pointing. but the lines leave black
    residual lines as long as the shape does not move." Then, zoomed in: "those
    lines cut in the shape. on more and more places. but a tiny movement and
    everything is back to normal."

    IT IS ONE ENGINE, AND THAT IS WHY THE FIRST FIX WAS WRONG. Measured by
    hovering across the shape and comparing the picture with a clean one:
    WebKit leaves 739 pixels of streak behind, Chromium leaves none. The spike
    lines are drawn into the WebGL buffer and Safari does not clear what they
    wrote until something else forces a full redraw. Turning the lines off
    fixes it and costs every other browser a genuinely useful feature, so it
    is not what is done here.

    THE CURE IS THE READER'S OWN WORKAROUND, AUTOMATED. A tiny movement clears
    it, so the camera is moved by a millionth of a unit -- far too little to
    see, enough to force the redraw. Measured with that in place: 739 pixels
    of streak become 51, which is 0.008% of the window and invisible.

    Throttled to one per animation frame, so a fast drag cannot queue hundreds
    of them: 2.7ms each in WebKit, 1.5ms in Chromium, against a frame budget
    of about 17ms. Applied in every engine rather than sniffing for Safari --
    one code path to maintain, and the next engine to grow this bug is covered
    without anybody noticing it had to be.
    """
    js = """
<script>(function () {
  function ready(fn) {
    var gd = document.querySelector(".js-plotly-plot");
    if (window.Plotly && gd && gd.on) return fn(gd);
    window.setTimeout(function () { ready(fn); }, 250);
  }
  ready(function (gd) {
    var waiting = false, sign = 1;
    gd.on("plotly_hover", function () {
      if (waiting) return;
      waiting = true;
      window.requestAnimationFrame(function () {
        waiting = false;
        var scene = gd._fullLayout && gd._fullLayout.scene;
        if (!scene || !scene.camera || !scene.camera.eye) return;
        sign = -sign;
        window.Plotly.relayout(gd, {
          "scene.camera.eye.x": scene.camera.eye.x + sign * 1e-6});
      });
    });
  });
})();</script>
"""
    at = html.rfind("</body>")
    return html[:at] + js + html[at:] if at > 0 else html + js


def _threshold_control(html: str, mode: str, its_own_slider: bool = True) -> str:
    """A live "hide anything under ΔE n" slider, inside the saved page.

    WHY IT IS LIVE RATHER THAN BAKED IN AT SAVE TIME. Whoever opens the page
    is usually not whoever made it, and the interesting threshold is not known
    in advance: on one chart the story is at ΔE 1, on another at 3. Fixing it
    when the file is written hands the reader one frozen opinion and no way to
    ask a second question. Everything needed is already in the file -- each
    dot carries how far it moved -- so the slider costs no data, only the code
    to move it.

    IT BUILDS ITSELF ONLY WHERE IT APPLIES. A page with no drift cloud in it
    has nothing to hide by, and a control that cannot act is worse than a
    missing one, so it looks for dots carrying a ΔE and does nothing at all if
    there are none.

    NOTHING IS THROWN AWAY. The full arrays are kept aside on load and the
    picture is redrawn from them each time, so sliding back to the left brings
    every colour back exactly as it was.
    """
    c = static_palette(mode)
    # THE CONTROL ITSELF IS FOR A SAVED PAGE. In the application's own view
    # the window already has this slider in its column, and two of them a few
    # inches apart is two controls for one thing that can disagree. The
    # WORKING PART is handed out either way -- see window.cqHideBelow -- so
    # the window's own slider drives exactly the code a reader would.
    js = """
<!-- A WIDTH OF ITS OWN, or the whole control sizes itself to whatever it
     currently says. It is a flex item in the page's column, so "max-width and
     auto margins" left it shrink-to-fit: measured, the box went 498 px wide
     saying "nothing hidden" and 461 px saying "ΔE 3.0", and the slider inside
     it lost 18 px the moment the reader moved the thumb. Reported as "it
     changes its width ... which is kind of jumpy and confusing".
     Two earlier attempts failed because they treated the symptom — pinning
     the readout, then giving the row its own line — while this box went on
     shrinking, and one of them made the jump worse (39 px). -->
<div id="cq-cut" hidden style="width:100%;box-sizing:border-box;
     max-width:46em;margin:0 auto;padding:.4em 1.5em 1.2em;
     font:14px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     color:__TEXT__">
  <label style="display:flex;align-items:center;gap:.8em;flex-wrap:wrap">
    <span>Hide anything under</span>
    <!-- THE READING TRAVELS WITH THE SLIDER, in a box of their own that does
         not wrap inside. Loose in the row, the reading was pushed onto a line
         by itself whenever the row ran out of width -- which is how the word
         it used to say ended up "in the middle of nowhere". Wrapping the pair
         together means a narrow phone drops both under the words, and the
         reading is never orphaned from the control it belongs to. -->
    <span style="display:flex;align-items:center;gap:.8em;flex:1 1 18em">
      <input type="range" data-cq="cut" min="0" max="0" step="1" value="0"
             style="flex:1 1 8em;min-width:7em;min-height:44px;
                    accent-color:__TEXT__">
      <!-- AND THE READOUT KEEPS ITS OWN WIDTH, which only works now that the
           box around it does. It says "nothing hidden" at one end and "ΔE 3.0"
           along the rest — 97 px against 42 px — and being sized to its
           content it handed the difference to the track. 7.2em is the wider of
           those two at this size, measured rather than guessed. -->
      <span data-cq="cutsays" style="flex:0 0 auto;white-space:nowrap;
            min-width:7.2em;opacity:.85">nothing hidden</span>
    </span>
  </label>
  <p data-cq="cutnote" style="margin:.4em 0 0;opacity:.75"></p>
</div>
<script>(function () {
  function ready(fn) {
    if (window.Plotly && document.querySelector(".js-plotly-plot")) return fn();
    window.setTimeout(function () { ready(fn); }, 250);
  }
  ready(function () {
    var gd = document.querySelector(".js-plotly-plot");
    var box = document.getElementById("cq-cut");
    if (!gd || !gd.data || !box) return;
    // READ FROM _fullData, NOT FROM data, AND THAT IS THE WHOLE TRICK.
    // The drawing library packs any sizeable array into base64 --
    // {dtype, bdata, shape} -- so gd.data[i].x is an object, gd.data[i].
    // customdata[0] is null, and every length is NaN. It has already decoded
    // them for its own use in _fullData, where customdata comes back as an
    // array of two-number arrays. Reading the packed form is how a first
    // attempt at this built no control at all and reported "nan drawn".
    var src = gd._fullData || gd.data;
    function flat(v) {
      if (!v) return [];
      if (Array.isArray(v)) return v;
      if (v.length !== undefined) return Array.prototype.slice.call(v);
      if (v._inputArray) return Array.prototype.slice.call(v._inputArray);
      return [];
    }
    var kept = [], most = 0, any = false;
    src.forEach(function (t, i) {
      var cd = t.customdata;
      if (!cd || !cd.length || cd[0] == null || cd[0].length < 2) {
        kept.push(null); return;
      }
      any = true;
      var de = [];
      for (var q = 0; q < cd.length; q += 1) { de.push(cd[q][1]); }
      de.forEach(function (v) { if (v > most) most = v; });
      var marker = t.marker || {};
      // THE NAME IS KEPT IN TWO HALVES because the count in it has to move
      // with the threshold. "yellows — 134" beside a single drawn dot is the
      // key telling the reader something that is no longer true, and it was
      // doing exactly that: at ΔE 2.9 the key still read 134, 132 and 11
      // above 1, 6 and 6 dots.
      var base = (t.name || "").split(" — ")[0];
      kept.push({i: i, x: flat(t.x), y: flat(t.y), z: flat(t.z),
                 cd: Array.prototype.slice.call(cd), de: de,
                 base: base, all: cd.length,
                 colour: flat(marker.color), size: flat(marker.size)});
    });
    if (!any) return;
    var least = Infinity;
    kept.forEach(function (k) {
      if (k) k.de.forEach(function (v) { if (v < least) least = v; });
    });
    if (!isFinite(least)) least = 0;
    var slider = box.querySelector('[data-cq="cut"]');
    var says = box.querySelector('[data-cq="cutsays"]');
    var note = box.querySelector('[data-cq="cutnote"]');
    // THE SAME RULE AS THE WINDOW: from this pair's smallest difference to
    // its largest, in tenths. A slider whose ends do nothing teaches the
    // reader that the control is broken.
    //
    // AND THE TOP END STOPS JUST BELOW THE BIGGEST, not just above it. With
    // Math.ceil the last step emptied the picture completely -- "729 of 729
    // colours ... are not drawn" over a bare set of axes, which reads as a
    // page that has broken rather than a threshold nobody's colours reach.
    // Rounding down leaves the biggest mover, or movers, standing: the far
    // end of the slider now answers "which colour moved most", which is a
    // question worth having an end of the travel for. The window has always
    // truncated here; only this copy rounded up.
    var lo = Math.floor(least * 10), hi = Math.floor(most * 10);
    if (hi <= lo) return;
    slider.min = lo; slider.max = hi; slider.value = lo;
    box.hidden = false;
    function apply() {
      var cut = slider.value / 10, shown = 0, total = 0;
      kept.forEach(function (k) {
        if (!k) return;
        var x = [], y = [], z = [], cd = [], col = [], sz = [];
        for (var j = 0; j < k.de.length; j += 1) {
          total += 1;
          if (k.de[j] < cut) continue;
          shown += 1;
          x.push(k.x[j]); y.push(k.y[j]); z.push(k.z[j]); cd.push(k.cd[j]);
          if (k.colour.length) col.push(k.colour[j]);
          if (k.size.length) sz.push(k.size[j]);
        }
        var up = {x: [x], y: [y], z: [z], customdata: [cd]};
        if (k.colour.length) up["marker.color"] = [col];
        if (k.size.length) up["marker.size"] = [sz];
        // THE COUNT IN THE KEY IS THE DRAWN COUNT, not the family's size,
        // whenever anything is being left out -- "greys \u2014 2 of 11" rather
        // than a key still claiming eleven over two dots. With the threshold
        // right down it goes back to the plain "greys \u2014 11", because then
        // the two numbers are the same and saying it twice is noise.
        if (k.base) {
          up.name = [k.base + " \u2014 "
                     + (x.length === k.all ? k.all
                        : x.length + " of " + k.all)];
        }
        window.Plotly.restyle(gd, up, [k.i]);
      });
      var hidden = total - shown;
      // TRUE AT BOTH ENDS, AND ON A LINE OF ITS OWN IT STILL HAS TO MEAN
      // SOMETHING. This read "everything" while nothing was hidden, which is
      // the leading words' object -- "Hide anything under ... everything" --
      // and on a narrow window it wrapped away from them and sat by itself:
      // "with nothing hidden there is the word everything in the middle of
      // nowhere". It now says what the state IS rather than finishing a
      // sentence it may be separated from, and it is kept off a line of its
      // own as well.
      says.textContent = hidden ? ("\u0394E " + (cut).toFixed(1))
                                : "nothing hidden";
      // THE PAGE SAYS WHAT IS MISSING FROM IT, for the same reason the
      // window does: a picture with eleven dots in it cannot otherwise be
      // told apart from a printer that is nearly perfect. It says so at rest
      // too -- an empty line here made the page jump by its own height on the
      // first drag, and "all of them are drawn" is worth stating outright on
      // a page somebody else sent you.
      note.textContent = hidden
        ? (hidden + " of " + total + " colours moved by less than \u0394E "
           + cut.toFixed(1) + " and are not drawn.")
        : ("All " + total + " colours are drawn. Drag to leave out the ones "
           + "that moved least.");
    }
    slider.addEventListener("input", apply);
    // AND THE WINDOW CAN ASK FOR THE SAME THING WITHOUT REBUILDING ANYTHING.
    // The application's own threshold slider used to redraw the whole page on
    // every step: the view went black, loaded again, and only settled when the
    // drag ended -- "dragging the hide anything under slider also blacks out
    // the whole viewer and then puts everything back at once instead of only
    // granularly hiding what the slider promises".
    //
    // What the reader of a saved page gets is exactly what the window wants:
    // the dots are already drawn, and hiding some of them is a restyle. So
    // the same function is handed out under a name the window can call, and
    // there is one implementation rather than two that would drift.
    window.cqHideBelow = function (de) {
      var tenths = Math.round(de * 10);
      slider.value = Math.max(+slider.min, Math.min(+slider.max, tenths));
      apply();
      return slider.value / 10;
    };
    apply();
  });
})();</script>
"""
    js = js.replace("__TEXT__", c["text"])
    if not its_own_slider:
        # THE SLIDER IS HIDDEN, NOT DELETED, and the difference is the whole
        # bug. Cut out of the page, its elements went with it -- and the script
        # that does the hiding reads the slider for its value and the two
        # lines beside it for what to say, so it found nothing and gave up
        # before defining anything. The window's slider then moved and no dot
        # moved with it: "now dragging the slider does not black out / redraw
        # everything but in turn nothing gets hidden".
        #
        # Left in place and hidden, the machinery is all there and the window
        # drives it; nobody sees a second control.
        js = js.replace('<div id="cq-cut" hidden style="',
                        '<div id="cq-cut" hidden data-cq-window="1" style="'
                        'display:none !important;', 1)
    at = html.rfind("</body>")
    return html[:at] + js + html[at:] if at > 0 else html + js


#: THE STRIP'S OWN RESET, AND ONLY THE ONE THAT GOES HOME. The viewer offers
#: two: "Reset camera to last save", which returns to the camera this file
#: wrote into the figure, and "Reset camera to default", which returns to the
#: drawing library's own framing. Measured in a browser, by turning the shape
#: with the mouse and pressing each:
#:
#:     Reset camera to last save   ->  eye 1.5, 1.5, 1.5   (where it opened)
#:     Reset camera to default     ->  eye 1.25, 1.25, 1.25
#:
#: The second is exactly the framing build_figure pulls away from on purpose:
#: it frames the data tightly, which on a wide flat gamut crops the corners
#: and opens on a close-up of the middle. Two buttons a pixel apart, one of
#: them named "default", and the inviting one is the worse view -- so the
#: worse one is not offered. Nothing new is added: the reader already had the
#: right button and now it is the only one.
#:
#: AND NOTHING ELSE IN THE CONFIGURATION IS TOUCHED, which cost a report
#: within the hour. The first version of this handed the main page the whole
#: config the two-room writer uses -- responsive, scrollZoom, the logo -- none
#: of which that page had ever had. The picture behaved differently on a wheel
#: and on a resize, and the report was "something is weird about the viewer
#: now. i don't know what it shows and i can't really manipulate it". One
#: button was being removed; one key changes.
_MODEBAR_ONLY = {"modeBarButtonsToRemove": ["resetCameraDefault3d"]}


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
                       full_html=True, div_id="scene0",
                       config=dict(_MODEBAR_ONLY))
    # A NAME FOR THE TAB, THE BOOKMARK AND THE PASTED LINK. Plotly writes a
    # document with no <title> at all, so a page saved for somebody else
    # arrived showing nothing but its file name — in the one feature that
    # exists for sending a measurement to another person. The caption already
    # says what the picture is, so it is what the tab says too.
    html = _titled(html, _page_title(fig))
    # THE READER'S OWN THRESHOLD. It builds itself only on a page that has a
    # drift cloud in it, so every other kind of page is untouched.
    html = _threshold_control(html, mode, its_own_slider=controls)
    # The pointing lines leave streaks in one engine; this clears them without
    # taking the lines away. See _clear_hover_streaks.
    html = _clear_hover_streaks(html)
    # THE CAPTION FITS THE PANE IT IS IN, on every page this writes -- moving
    # or still, flat or not. See _CAPTION_JS for why it is not part of the
    # movement script.
    html = html.replace("</body>", f"<script>{_CAPTION_JS}</script></body>", 1)
    if not carry_viewer:
        html = _say_if_the_viewer_never_arrives(html, mode)
    _PAGE_BACKGROUND = static_palette(mode)["page"]
    # HIDING THE OVERFLOW HIDES WHATEVER IS UNDER THE PICTURE, and the first
    # time round only half of that was noticed.
    #
    # This was `"auto" if notes else "hidden"`, on the reasoning that a page
    # with only a picture has nothing to scroll to, and a stray scrollbar just
    # makes the picture jump. The written-out figures were the exception that
    # forced `auto`: they are appended after a scene that is already the full
    # height of the window, so with the overflow hidden fifteen real wheel
    # notches moved the published page 03 not one pixel.
    #
    # THE CONTROL PANEL IS APPENDED THE SAME WAY and was never counted. It is
    # built by the viewer at run time, so `notes` cannot see it -- and on
    # every page saved without the numbers the reader got `overflow:hidden`,
    # which means the document cannot scroll AT ALL. The panel sat below the
    # fold with no way to reach it: not by dragging, and not by pressing
    # "more…" either, because scrollIntoView cannot scroll a page that has
    # been told it does not scroll.
    #
    # Basti, on page 18 -- which is saved without the numbers -- after the
    # gesture fix and the scroll-into-view fix had both landed: "even after
    # pressing more i can't scroll". Page 14 carries the numbers, so it
    # scrolled, which is why "it worked before on the examples i tried".
    #
    # SO THE CONDITION IS "IS ANYTHING UNDER IT", which is figures OR
    # controls. Both, not one -- exactly the invariant the check beside this
    # already states in words and only half enforced. A page with neither
    # still gets `hidden`, and rightly: there is genuinely nothing to reach,
    # and a scrollbar on a picture that fills the window only makes it jump.
    _overflow = "auto" if (notes or controls) else "hidden"
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
        # AND THE PICTURE IS SIZED BY THE COLUMN, NOT BY A PERCENTAGE OF IT.
        #
        # The box above keeps `height:auto`, which is the whole point of it --
        # the page may grow past the window. But the drawing library gives its
        # own div `height:100%`, and a percentage height only resolves against
        # a parent whose height is DEFINITE. Chromium resolves it anyway
        # against the height flex worked out; WebKit follows the stricter
        # reading, finds nothing to take a percentage of, and falls back to
        # the library's built-in default of 450px.
        #
        # Measured on the same page in a 1024x1366 window: the box came out
        # 1128px tall in both engines, and the picture inside it 1128px in
        # Chromium against **450px in WebKit** -- so two thirds of an iPad
        # screen was black, and the same on a Mac in Safari. Reported as "a
        # lot of black space that could be used for viewing the shape".
        #
        # Making the box a flex column and letting the picture be a flex item
        # takes the percentage out of it entirely: flex sizing does not need a
        # definite parent, so both engines agree. `min-height:0` is what lets
        # a flex item be smaller than its contents, and without it the item
        # refuses to shrink and the page grows a scrollbar it does not need.
        style += ("<style>html{height:100%;}"
                  "body{height:auto;min-height:100%;}"
                  "body > div:first-of-type"
                  "{height:auto !important;min-height:62vh;"
                  "display:flex;flex-direction:column;}"
                  # AND IT IS CAPPED, or the fix trades one fault for a worse
                  # one. Left to grow, the flex item takes the whole column
                  # and the picture fills the screen edge to edge -- measured
                  # at 100% of the viewport in WebKit at every size tried,
                  # which pushes the control strip entirely below the fold.
                  # That is the very thing the 62vh floor above exists to
                  # prevent: a reader on a phone has to be able to see that
                  # there is something under the picture.
                  "body > div:first-of-type > .js-plotly-plot"
                  "{flex:1 1 auto;min-height:62vh;max-height:80vh;"
                  "height:auto !important;}"
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
        colours = static_palette(mode)
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
    order = f"<script>{_ORDER_JS}</script><script>{_WHEEL_JS}</script>"
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
#: IT MUST MATCH WHAT THE PAGE OPENS WITH, and for a while it did not.
#:
#: This was 120, a quarter fewer than `slice_at` draws by default, on the
#: argument that the difference cannot be seen -- an outline of a gamut has
#: no feature narrower than three degrees of hue, and side by side the two
#: are indistinguishable.
#:
#: That argument is sound about two pictures and wrong about one. The page is
#: DRAWN at the default, and the slider restyles it from these -- so the very
#: first press of the cut swapped a 181-point outline for a 121-point one and
#: the reader watched the shape coarsen. Coming back to the height it started
#: at did not undo it, because the fine outline was gone. Measured on the
#: cross-section pages: the reading returned to L* 50 exactly and 3,141
#: pixels of the picture did not, on a page whose noise floor is 0.
#:
#: Matching costs 73 kB on a 4.9 MB page -- 1.45% -- to make the page agree
#: with itself. `test_saved_page.py` fails if these two ever drift apart
#: again, because nothing else would notice.
_CUT_STEP = 2.0
_CUT_POINTS = 180


def slice_levels(gamuts, step: float = _CUT_STEP, points: int = _CUT_POINTS,
                 include: float = None):
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
    # AND THE HEIGHT THE SENDER WAS ACTUALLY LOOKING AT, if the grid missed
    # it. The grid is every second lightness, so a reader could never slide
    # to an odd one -- and the page is drawn at the sender's EXACT height and
    # titled with it. Saved at L* 51 the picture said 51 and the strip under
    # it said 50, because 51 was not one of the 45 levels the page carried.
    #
    # Measured on the demo profile: 45 levels from 10 to 98, and 51 simply
    # absent. Adding the one the sender chose costs a single ring set -- about
    # 1.6 kB against the 73 kB the whole grid takes -- and makes the page open
    # where the window was, which is the whole promise of saving a view.
    if include is not None:
        wanted = round(float(include), 3)
        if lo <= wanted <= hi and not any(abs(v - wanted) < 1e-6 for v in levels):
            levels.append(wanted)
            levels.sort()
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

    c = static_palette(mode)
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
        # THE LETTERING SAID OUT LOUD, for the same reason as the 3D view:
        # left to the library's default, the numbers are drawn in the page
        # font and change colour the first time anything relayouts the axes.
        xaxis=dict(title="a*   green ← → red", zeroline=True,
                   zerolinecolor=c["axis"], gridcolor=c["grid"],
                   color=c["text"], scaleanchor="y", scaleratio=1),
        yaxis=dict(title="b*   blue ← → yellow", zeroline=True,
                   zerolinecolor=c["axis"], gridcolor=c["grid"],
                   color=c["text"]),
        paper_bgcolor=c["page"], plot_bgcolor=c["plot"], font_color=c["text"],
        legend=dict(orientation="h", y=-0.12, itemclick="toggle",
                    itemdoubleclick="toggleothers"), showlegend=legend,
        margin=dict(l=0, r=0, t=54, b=0))
    if extent is None and not slidable:
        # A LITTLE AIR ON ONE PANE AS WELL. Two panes side by side have always
        # had it -- slice_extent pads its square by 8% -- while a single cut
        # was left to the drawing library, which fits the axis exactly to the
        # data. Measured in the application's own pane: the x range came back
        # as -82.579..82.404 against a shape spanning -82.579..82.404, so the
        # widest colours sat ON the frame with nothing between them and it,
        # and in a narrow window that reads as a picture cut off.
        #
        # THE SAME FUNCTION AS THE TWO-PANE PATH, not a second rule that can
        # drift from it.
        #
        # NOT WHEN THE PAGE CARRIES A SLIDER: those pages step through many
        # heights, and a range worked out from the one being drawn would make
        # the picture rescale under the reader's hand at every step.
        extent = slice_extent(gamuts, lightness)
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
                     offer=None, notes: str = "",
                     carry_viewer: bool = True) -> Path:
    """One page holding one flat cross-section. See :func:`build_slice_figure`.

    *controls* is the reader's strip. There is nothing to turn on a flat cut,
    so it carries only what still means something -- zoom, move, back to where
    it opened, and the slider that moves the cut up and down.

    *notes* ARE THE NUMBERS, AND THEY USED TO BE DROPPED IN SILENCE. This took
    the argument and did nothing with it, and the window never passed one
    anyway -- so a cross-section saved as a web page arrived with the styling
    for a block of numbers, five rules of it, and no numbers. Every other page
    this application writes carries them.

    Found by asking each kind of page which controls it builds, and noticing
    that the cut alone would not build "put the numbers away": there was
    nothing to put away.
    """
    cuts = None
    if controls and (offer is None or offer.get("cut", True)):
        # THE HEIGHT THIS PAGE IS DRAWN AT IS ONE THE READER CAN GET BACK TO.
        # Without `include` the grid is every second lightness, so a page
        # saved at an odd one opened with its strip a step away from its own
        # title. See slice_levels.
        cuts = slice_levels(gamuts, include=lightness)
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
        out, mode, spin=spin, controls=controls, offer=offer,
        notes=notes, carry_viewer=carry_viewer)
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


#: How long the longest side of the drawn room may be before it is scaled
#: down. Measured rather than chosen: a room 2.60 long still fits its picture
#: and one 3.27 long spills over two edges of it.
ROOM_CEILING = 2.6


def _say_what_is_missing(title, hidden_note, emptied, names):
    """The caption, with a word about anything the picture no longer holds.

    A picture that has been emptied by a setting looks exactly like one that
    went wrong, and the reader cannot tell which from looking. This is the
    same courtesy the drift cloud already had when its dots fell below the
    threshold: say it on the picture, where the question is asked.
    """
    parts = [title] if title else []
    if hidden_note:
        parts.append(hidden_note)
    if emptied:
        if len(emptied) >= len(names) and names:
            parts.append("nothing is left to show: every shape here agrees "
                         "with the others everywhere, so hiding what they "
                         "agree on hides all of it")
        elif len(emptied) == 1:
            parts.append(f"{emptied[0]} is not drawn: it agrees with the "
                         f"others everywhere, so nothing of it stands out")
        else:
            parts.append(f"{len(emptied)} shapes are not drawn: they agree "
                         f"with the others everywhere, so nothing of them "
                         f"stands out")
    return " — ".join(parts)


def _room_shape(extent):
    """The proportions of the drawn room, scaled so the longest side is 1.

    *extent* is ((x0, x1), (y0, y1), (z0, z1)) in the space being drawn.
    """
    sides = [max(hi - lo, 1e-9) for lo, hi in extent]
    longest = max(sides)
    return dict(x=sides[0] / longest, y=sides[1] / longest,
                z=sides[2] / longest)


def build_figure(gamuts, title: str, opacity: float | None = None,
                 points: bool = False, patches=None,
                 aspect: str = "data", styles=None, lost=None,
                 mode: str = "dark", paint: str = "true",
                 depth: float = 0.35, mesh_paint: str = "plain",
                 rings: int = 0, per_shape=None, neutrals=None,
                 ideal_neutrals: bool = False, chart=None,
                 light=None, grid: bool = True, space=None,
                 chart_look=None, agree: float = 1.0, differ: float = 1.0,
                 split: bool = False, drift=None, camera=None,
                 lost_in_their_own_colours: bool = False):
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
    c = static_palette(mode)
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
    #
    # AND THE SHAPES ARE RE-CUT ALONG THAT BOUNDARY FIRST, so the fade has an
    # edge rather than a slope across every triangle that straddles it -- see
    # `recut_where_they_part`.
    splits = stands = None
    # AND WHENEVER SOMETHING IS MARKED AS OUT OF REACH, which is the same
    # question asked for a different reason.
    #
    # Reported from the window: "what is out of reach here should probably be
    # a clean cut along the shell of srgb. instead it is zig zagging". It was
    # the mesh and not the measurement, and it was measured on his own shapes
    # at his own settings: of the paper's 978 triangles, 175 -- 17.9% of the
    # surface -- have corners both inside sRGB and outside it, and each of
    # those must be painted wholly red or wholly grey. That staircase IS the
    # zig-zag. After the re-cut: 1,328 triangles and NOT ONE straddles, for
    # 18 ms.
    #
    # The cure was already here and simply never invoked for this: the fade
    # got a clean edge and the marking did not, for no reason but which
    # branch ran. `recut_where_they_part` has carried the mask through from
    # the start, and refuses the job for the one case it cannot answer -- a
    # chart, a second paper and a reference together, where a new corner's
    # marking cannot be worked out -- leaving that shape its old mesh.
    #: Shapes the fade has taken away entirely, named beside the caption so an
    #: empty picture explains itself.
    _emptied = []
    marked = any(m is not None for m in (lost or ()))
    if len(gamuts) > 1 and (split or marked or agree < 1.0 or differ < 1.0):
        gamuts, splits, stands, lost = recut_where_they_part(gamuts, lost)
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
        # EACH VERTEX ANSWERS FOR ITSELF. Taking the per-triangle answer and
        # marking every vertex those triangles touch dilates the
        # disagreement by a ring: 96 vertices of the demo paper -- a seventh
        # of its surface -- were drawn as standing out from Adobe RGB where
        # they sit inside it. See `disagreeing_vertices`.
        standing = (stands[i] if stands is not None else None)
        if standing is not None:
            alphas = np.where(standing, differ, agree)
        # CARRIED INTO THE PAGE only when the reader is being given the
        # control. It is one character per vertex -- about half a kilobyte a
        # shape -- against the 66 kB a second copy of the mesh would have
        # cost, and a page nobody can fade has no use for it at all.
        stand = (standing if (split and standing is not None) else None)
        # A SHAPE THE FADE HAS TAKEN AWAY ENTIRELY IS WORTH SAYING SO.
        #
        # With "where they agree" at nothing, a shape lying wholly inside the
        # others has no part left that stands out -- and two identical
        # measurements leave the picture EMPTY but for its walls. That is the
        # honest answer and it looks exactly like a fault. The tooltip says so
        # three scrolls away; the picture itself said nothing.
        #
        # ASKED OF THE FADE, NOT OF THE TRIANGLES. A shape faded to nothing
        # usually keeps every triangle it had -- `_solid_remainder` refuses to
        # drop them when none would be left -- so counting faces finds
        # nothing. What makes it invisible is that no corner of it is lit.
        if alphas is not None and not np.asarray(alphas, float).any():
            _emptied.append(name)
        if marked is not None:
            fig.add_trace(_mesh_lost(
                g, name, base_i, marked, c["kept"], depth_i, light=light,
                alphas=alphas, stand=stand,
                lost_in_their_own_colours=lost_in_their_own_colours))
        elif how in ("solid", "solid+mesh"):
            _surface = _mesh(g, name, opacity=base_i,
                             paint=paint_i, index=i, depth=depth_i,
                             page=c["page"], light=light, alphas=alphas,
                             stand=stand)
            fig.add_trace(_surface)
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
        # THE PERFECTLY NEUTRAL LINE STANDS ON ITS OWN, and until now it did
        # not. Basti asked for these two to be settled independently -- "i get
        # your argument but i'd rather set them independently" -- and the
        # WINDOW was decoupled while the drawing was not: the line was drawn
        # only inside the test below, so a shape with no measured greys never
        # got one however it was ticked. A profile has no greys to show and a
        # perfectly good lightness range to draw the line over.
        has_greys = (neutrals is not None and i < len(neutrals)
                     and neutrals[i] is not None)
        if ideal_neutrals and not has_greys:
            for trace in _ideal_neutral_trace(None, name, "#9aa3b2",
                                              _axes_space, lab=g.vertices):
                fig.add_trace(trace)
        if has_greys:
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
    # DEFINED FOR EVERY FIGURE, not only the ones with a drift cloud in
    # them. Set inside the branch alone, these were undefined for every
    # other picture this function draws -- which is most of them.
    _hidden_note = ""
    if drift is not None:
        # LAST, so it reads over the shapes rather than through them. This is
        # the subject of the picture whenever it is present -- nobody asks for
        # a drift cloud and then wants to look at something else.
        drift_lab, drift_de, drift_name = drift[:3]
        # A FOURTH ITEM ASKS WHICH WAY RATHER THAN HOW FAR, and older
        # three-item callers go on meaning "how far" -- which is the right
        # default, because how far is the first question and which way the
        # second. When it is present, the second value is the (N, 3) movement
        # in Lab rather than the (N,) distance.
        which = drift[3] if len(drift) > 3 else None
        # A FIFTH ITEM SPLITS THE CLOUD INTO ITS COLOUR FAMILIES, which turns
        # the legend into a filter: click "blues" and the blues go. Absent,
        # the cloud is one trace as it has always been.
        families = bool(drift[4]) if len(drift) > 4 else False
        # A SIXTH ITEM HIDES THE COLOURS THAT BARELY MOVED, in ΔE2000.
        floor_de = float(drift[5]) if len(drift) > 5 else 0.0
        # WHAT WAS TAKEN OUT, WORKED OUT BEFORE ANYTHING IS DRAWN, so the
        # sentence exists even when the answer is "all of it" and there is no
        # trace left to hang it on.
        _de_for_gate = (drift[6] if len(drift) > 6 else
                        (None if which else drift_de))
        _left, _hidden_note = (hidden_below(_de_for_gate, floor_de)
                               if floor_de and _de_for_gate is not None
                               else (None, ""))
        if which:
            drawn = drift_direction(drift_lab, drift_de, drift_name,
                                    axis=which, space=_axes_space,
                                    by_family=families, deltas=_de_for_gate,
                                    hide_below=floor_de)
        else:
            drawn = drift_cloud(drift_lab, drift_de, drift_name,
                                space=_axes_space, by_family=families,
                                hide_below=floor_de)
        for trace in drawn:
            fig.add_trace(trace)
        if families:
            # THE KEY BELONGS TO THE SCENE when the picture can be taken
            # apart, so no family can switch it off -- see colour_axis_for.
            #
            # AND THE KEY IS ASKED FOR BY NAME, because the drawing library
            # switches it off on its own as soon as only one family is left.
            # Reported from the published page: "here are still two patches
            # left but no more labels visible". Measured in a browser at
            # ΔE 3.0 on that page -- six families emptied, greys still holding
            # two dots, and the layout's own showlegend had flipped to false:
            #
            #     reds ... magentas   visible=False  n=0
            #     greys — 11          visible=True   n=2      key: (nothing)
            #
            # The library marks an emptied trace not-visible, and its default
            # is to draw no key for a single visible trace. That default is
            # right for a picture of one thing and wrong for this one, where
            # the last family standing is the whole answer: it is the reader's
            # only way of knowing WHICH colours those two dots are.
            # NO SHARED SCALE OVER A PICTURE OF NAMES, and this CRASHED
            # rather than merely looking wrong: colour_axis_for describes a
            # measurement along an axis and reads DIRECTIONS[which], which
            # has no entry for "toward". Ticking "Split it into colour
            # families" while the cloud is coloured by the family each colour
            # is HEADING FOR took the whole window down with a KeyError.
            #
            # Reachable from both windows and never crossed until now: each
            # control was driven with the other left alone. The destinations
            # are already their own key -- one trace per family, each in the
            # colour of the place -- so the split has nothing to add and the
            # scale would be a scale over names.
            if which == "toward":
                fig.update_layout(showlegend=True)
            else:
                fig.update_layout(coloraxis=colour_axis_for(which),
                                  showlegend=True)
        if True:
            # PIN THE BOX WHENEVER A DRIFT CLOUD IS DRAWN. NO EXCEPTIONS.
            #
            # Splitting the cloud into families gave the reader seven switches,
            # and switching one off made the axes rescale to whatever was left
            # -- so the whole scene jumped, redrew at a different size, and the
            # numbers down the side changed. Measured on the published page:
            # hiding one family moved the a* axis from -88..92.4 to -87.6..79.
            # On a phone, where turning several off in a row is exactly how the
            # thing is used, the view moves under the finger every time.
            #
            # It also destroys the only reason to hide a family. The question
            # is WHERE IN THE SPACE this family sits, and an axis that resizes
            # itself to the answer makes every family fill the same box and
            # look alike.
            #
            # So the range is taken from ALL the colours, once, and fixed.
            # Hiding some then removes their dots and moves nothing else --
            # which is what the flat panes have always done for the same
            # reason, see the note on `extent` above.
            #
            # AND IT IS UNCONDITIONAL, which it was not at first. It was tied
            # to the family split, on the reasoning that only a split picture
            # could lose points. The threshold then gave the UNSPLIT picture a
            # second way to lose them, the rule did not cover it, and the same
            # squashed walls came back -- reported twice, from two different
            # switches. A rule with an "except when" in it will be outgrown by
            # the next feature; this one has none.
            _pinned = _drift_extent(drift_lab, _axes_space)
    else:
        _pinned = None
    from gamutview import AXES
    # The axes are named for the space the gamuts were built in, so a
    # picture can never be read against the wrong labels.
    # A ROOM THAT WOULD BE DRAWN LARGER THAN ITS PICTURE IS SCALED DOWN, and
    # NOTHING ELSE IS TOUCHED.
    #
    # Left to itself the drawing library sizes the room in data units with no
    # ceiling: each side is its range divided by the mean of the three. That
    # is right and is kept -- it is why a wide gamut looks wide -- but it has
    # no limit, and past a point the room is drawn bigger than the picture
    # holding it. Measured by flattening a gamut step by step and looking at
    # where the ink lands:
    #
    #     L* spread 30   longest side 1.21   fits
    #     L* spread  5   longest side 2.19   fits
    #     L* spread  3   longest side 2.60   fits
    #     L* spread 1.5  longest side 3.27   SPILLS OVER THE EDGE
    #
    # -- the shape cut off at two edges, the axis titles pushed out of the
    # picture, one label left reading "na". A chart covering only the midtones
    # does this.
    #
    # So the sides are worked out here, and only if the longest exceeds what
    # was measured to fit is the whole set scaled down to it. Proportions are
    # divided by one number, so nothing is squashed; a picture under the
    # ceiling is left entirely alone, which is every ordinary gamut.
    _room = None
    _ticks = None
    if not _pinned and aspect == "data":
        _corners = [np.asarray(_to_plot_space(np.asarray(g.vertices, float),
                                              _axes_space), float)
                    for _n, g in gamuts
                    if getattr(g, "vertices", None) is not None
                    and len(g.vertices)]
        if _corners:
            _all = np.vstack(_corners)
            _sides = np.array([max(_all[:, i].max() - _all[:, i].min(), 1e-9)
                               for i in range(3)])
            # THE LIBRARY NORMALISES BY THE GEOMETRIC MEAN, not the plain
            # one, and the difference decides whether this rule ever fires.
            # Checked against what it actually produced: a normal gamut came
            # out 1.21, 1.05, 0.79 and a flat one 3.27, 2.85, 0.11 -- both
            # sets multiply to 1.00, which the arithmetic mean does not give.
            # Written with the plain mean this clamp computed 1.56 where the
            # page said 3.27, and so never fired on the very case it was for.
            _ratio = _sides / max(float(np.exp(np.log(_sides).mean())), 1e-9)
            if _ratio.max() > ROOM_CEILING:
                _ratio = _ratio * (ROOM_CEILING / _ratio.max())
                _room = dict(x=float(_ratio[0]), y=float(_ratio[1]),
                             z=float(_ratio[2]))
            # AND A SHORT SIDE GETS FEWER NUMBERS ALONG IT.
            #
            # The drawing library puts about the same number of ticks on every
            # axis whatever its length on screen, so the short side of a
            # lopsided room ends up with its labels written on top of one
            # another. Seen on two of the awkward shapes: a gamut with one
            # patch far out in a*, and one covering only the midtones, both
            # came out with the L* numbers as a single unreadable blob down
            # the left of the picture.
            #
            # Asked in proportion to how long each side is actually drawn --
            # nine along the longest, fewer along the others, never below
            # three, which is enough to say what an axis is.
            _ticks = dict(zip(("x", "y", "z"), (
                max(3, int(round(9 * side / _ratio.max())))
                for side in _ratio)))

    _axes = AXES[_axes_space]
    fig.update_layout(
        # A caption, not a headline. Plotly's default title is large and
        # centred, which made a line of explanatory text the loudest thing on
        # the page -- louder than the shape it describes. Small, dimmed, set
        # in the same monospace the figures below use, and moved to the left
        # so it reads as a label on the picture rather than a banner over it.
        title=_caption(
            # THE PICTURE SAYS WHAT IS MISSING FROM IT. A saved page showing
            # eleven dots cannot otherwise be told apart from a printer that
            # is nearly perfect, and this is the kind of picture people
            # forward to somebody else.
            _say_what_is_missing(title, _hidden_note, _emptied,
                                 [n for n, _g in gamuts]), c),
        scene=dict(
            xaxis_title=_axes["x"], yaxis_title=_axes["y"],
            zaxis_title=_axes["z"],
            xaxis_nticks=(_ticks["x"] if _ticks else None),
            yaxis_nticks=(_ticks["y"] if _ticks else None),
            zaxis_nticks=(_ticks["z"] if _ticks else None),
            aspectmode=("manual" if (_pinned or _room) else aspect),
            # WHEN THE BOX IS PINNED THE PROPORTIONS ARE PINNED TOO. With
            # aspectmode "data" the drawing library still works the shape of
            # the room out from the ranges it decides to use, so fixing the
            # ranges alone is only half of it: switch every family off but the
            # greys and what is left is a sliver of a*/b*, the room is drawn
            # as a tall thin slab, and the key is pushed off the side of the
            # picture. Basti found that on a phone -- "when only greys are
            # visible ... there is no more legend on the right side as well".
            #
            # Given the ratio outright, the room keeps its shape whatever is
            # switched on, and everything drawn beside it stays where it is.
            # AND THE LARGEST SIDE IS THE ONE, NOT THE FIRST.
            #
            # Dividing by x alone leaves the ratio bigger than 1 whenever
            # another side is longer, and a room drawn larger than the box
            # holding it spills over the edges. Found by drawing a gamut that
            # is nearly flat -- a chart covering only the midtones -- where
            # the drawing library's own "data" proportions came out
            # x=3.27, y=2.85, z=0.11 against a normal shape's 1.21, 1.05,
            # 0.79: the shape was cut off at two edges of the picture, the
            # axis titles were pushed out of it, and one label was left
            # reading "na".
            #
            # Dividing every side by the longest keeps the proportions exactly
            # -- nothing is squashed, which is the whole point of measuring in
            # Lab units -- and only changes how big the room is drawn.
            aspectratio=(_room_shape(_pinned) if _pinned
                         else (_room if _room else None)),
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
            # WHERE THE READER IS ALREADY LOOKING FROM, when somebody hands
            # one over. The window rewrites this page for anything it cannot
            # restyle in place, and a page opens at the camera it was written
            # with -- so a shape turned to the angle somebody wanted snapped
            # back to three-quarters-front a few seconds after they let go of
            # a slider. Reported exactly like that: "i drag let go it settles
            # and after a few seconds it jumps".
            #
            # It travels into a SAVED page too, which is what the button
            # offering to save "this view" has always said it would do.
            camera=camera or dict(eye=dict(x=1.5, y=1.5, z=1.5)),
            # THE BOX AROUND THE SHAPE, or nothing at all. Turned off, the
            # walls, the grid, the numbers and the axis names all go with it
            # and the shape is left floating on the page -- which is what a
            # picture for somebody else usually wants, and which takes the
            # scale away, which is why it is not the default.
            # THE LETTERING, SAID OUT LOUD RATHER THAN INHERITED. Left
            # unset, each axis keeps the drawing library's own default of
            # #444 and the numbers are drawn in the page font instead, which
            # looks right and is not the same thing -- so the moment
            # anything relayouts the axes, the numbers change colour. That
            # is exactly what happened: pressing the page-colour button
            # dimmed every axis number and name from #e6e6e6 to #8a8a8a and
            # never put them back, so a page walked round the colourings and
            # back to the one it was saved in no longer looked like the page
            # that was sent.
            xaxis=dict(backgroundcolor=c["plot"], gridcolor=c["grid"],
                       color=c["text"], visible=grid),
            yaxis=dict(backgroundcolor=c["plot"], gridcolor=c["grid"],
                       color=c["text"], visible=grid),
            zaxis=dict(backgroundcolor=c["plot"], gridcolor=c["grid"],
                       color=c["text"], visible=grid),
        ),
        paper_bgcolor=c["page"], font_color=c["text"],
        legend=dict(orientation="h", y=-0.02, itemclick="toggle",
                    itemdoubleclick="toggleothers"),
        margin=dict(l=0, r=0, t=54, b=0),
    )
    # THE POINTING LINES, KEPT, AND MADE TO STOP LEAVING STREAKS.
    #
    # Point at the shape and three lines run out to the walls to say where you
    # are. In WebKit they are written into the WebGL buffer and not cleared,
    # so they cut black slashes across the surface until something forces a
    # redraw -- "a tiny movement and everything is back to normal". Chromium
    # never shows it: measured by hovering across the shape and comparing with
    # a clean picture, WebKit left 614 pixels of streak and Chromium 0.
    #
    # EVERY CURE MEASURED, ALONE, rather than the first one that helped:
    #
    #     nothing                        614
    #     thinner lines                  301
    #     no projections on the walls    186
    #     both of those                   63
    #     a hair of camera movement       51
    #     all three together              51
    #
    # ALL THREE STILL LEAVES 51, AND AN EARLIER NOTE HERE CLAIMED 0. That
    # zero came from measuring the combination by applying the two settings
    # with a relayout immediately before the baseline shot -- and a relayout
    # is itself a full redraw, which cleans the buffer. The test made the
    # result it was measuring. Baked into the figure, where they belong, the
    # honest number is 51 pixels: 0.008% of the window, scattered single
    # pixels rather than the slashes that were reported, and 92% less than
    # the fault. It is a reduction of a WebKit bug, not a cure for one.
    #
    # So all three. The two settings below cost nothing and are not
    # noticeable -- the lines still point, they are simply one pixel wide and
    # do not paint a second copy of themselves onto the side walls. The third
    # is the reader's own workaround, automated, in _clear_hover_streaks.
    fig.update_scenes(xaxis_spikesides=False, yaxis_spikesides=False,
                      zaxis_spikesides=False,
                      xaxis_spikethickness=1, yaxis_spikethickness=1,
                      zaxis_spikethickness=1)

    if _pinned:
        # SAID WITH THE UNDERSCORE FORM so it merges with the titles, colours
        # and visibility set just above rather than replacing each axis whole.
        fig.update_scenes(
            xaxis_range=_pinned[0], xaxis_autorange=False,
            yaxis_range=_pinned[1], yaxis_autorange=False,
            zaxis_range=_pinned[2], zaxis_autorange=False)

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
