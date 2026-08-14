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
* The volume is the convex hull's, in cubic Lab units — the same quantity
  ArgyllCMS calls "units" and reports for ``iccgamut``. Comparable between two
  charts measured the same way; not comparable across white points.

Requires: numpy, scipy, plotly.
"""
from __future__ import annotations

import argparse
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


def read_ti3(path: Path, white_point: str = "D50",
             relative: bool = False) -> Measurement:
    """Parse an ArgyllCMS ``.ti3`` (CGATS) into device values and Lab.

    Only the columns a gamut needs are read; the spectral bands that make these
    files large are skipped. Raises ValueError with a plain reason when the file
    cannot give us what we need — an empty chart, no measurement columns, a
    device space that is not RGB.
    """
    text = path.read_text(errors="replace")
    if "BEGIN_DATA_FORMAT" not in text or "BEGIN_DATA" not in text:
        raise ValueError(f"{path.name} is not a CGATS/.ti3 file "
                         "(no BEGIN_DATA_FORMAT section)")

    fmt = text.split("BEGIN_DATA_FORMAT", 1)[1].split("END_DATA_FORMAT", 1)[0]
    columns = fmt.split()
    # Split AFTER the format section: "BEGIN_DATA_FORMAT" also starts with
    # "BEGIN_DATA", so searching the whole file finds the header first and the
    # column names end up parsed as numbers.
    after = text.split("END_DATA_FORMAT", 1)[1]
    body = after.split("BEGIN_DATA", 1)[1].rsplit("END_DATA", 1)[0]

    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("BEGIN_DATA"):
            continue
        parts = line.split()
        if len(parts) >= len(columns):
            rows.append(parts[:len(columns)])
    if not rows:
        raise ValueError(f"{path.name} has no measurement rows")

    def column(name: str) -> np.ndarray:
        i = columns.index(name)
        return np.array([float(r[i]) for r in rows], dtype=float)

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


def _edges(gamut, name: str, colour: str = "#9aa3b2", width: float = 1.0):
    """The triangle edges of a gamut, as a wire cage.

    A solid shape hides whatever is inside it. Drawn as a cage instead, an
    outer gamut can be seen through: which is the only way to look at a
    printer sitting inside sRGB, or inside everything the eye can see, and
    still see the printer. Every edge is drawn once — a triangle mesh shares
    each edge between two triangles, and drawing both doubles the work for an
    identical picture.
    """
    import plotly.graph_objects as go
    v = gamut.cylindrical() if gamut.space == "lab" else gamut.vertices
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
    return go.Scatter3d(x=xs, y=ys, z=zs, mode="lines",
                        line=dict(color=colour, width=width),
                        name=f"{name} (outline)", showlegend=True,
                        hoverinfo="name")


#: Colour used for the part of a gamut that the comparison cannot reach. A
#: warm red against the muted grey of the reachable part, so the eye goes
#: straight to what is lost without needing the legend.
_LOST = "rgb(232,23,93)"
_KEPT = "rgb(105,112,126)"


def _mesh_lost(gamut, name: str, opacity: float, lost,
               kept: str = _KEPT, depth: float = 0.35) -> "list":
    """The gamut painted by what the comparison cannot reproduce."""
    import plotly.graph_objects as go
    v = gamut.cylindrical() if gamut.space == "lab" else gamut.vertices
    colours = [_LOST if bad else kept for bad in lost]
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=gamut.faces[:, 0], j=gamut.faces[:, 1], k=gamut.faces[:, 2],
        vertexcolor=colours, opacity=opacity, flatshading=False,
        lighting=_lighting(depth),
        lightposition=dict(x=0, y=0, z=2000),
        name=f"{name} — red is out of reach", showlegend=True,
        hoverinfo="name")


#: A distinct colour per shape, for when telling them apart matters more than
#: seeing what colours they hold.
_FLAT = ("rgb(232,23,93)", "rgb(58,168,208)", "rgb(242,199,68)",
         "rgb(107,208,122)", "rgb(157,124,216)")


def _paint_vertices(gamut, paint: str, index: int) -> "list | None":
    """The colour of every vertex, for the chosen way of painting.

    Returns None for the plain case so the caller can use the gamut's own
    colours without copying them.
    """
    if paint == "true":
        return None
    if paint == "solid":
        return [_FLAT[index % len(_FLAT)]] * len(gamut.vertices)
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


def _mesh(gamut, name: str, opacity: float, wireframe: bool,
          paint: str = "true", index: int = 0, depth: float = 0.35):
    """One Plotly mesh for a gamut, painted the way the user asked."""
    import plotly.graph_objects as go
    v = gamut.cylindrical()
    chosen = _paint_vertices(gamut, paint, index)
    colours = chosen if chosen is not None else [
        f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
        for r, g, b in gamut.colors]
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=gamut.faces[:, 0], j=gamut.faces[:, 1], k=gamut.faces[:, 2],
        vertexcolor=colours, opacity=opacity, name=name, showlegend=True,
        flatshading=False, hoverinfo="name",
        lighting=_lighting(depth),
        lightposition=dict(x=0, y=0, z=2000),
        contour=dict(show=wireframe, color="#888", width=2),
    )


def _patch_cloud(lab, name: str):
    """Every measured patch as a dot, in its own colour — the raw evidence."""
    import plotly.graph_objects as go
    from gamutview import lab_to_lch_cartesian, xyz_to_srgb, lab_to_xyz
    v = lab_to_lch_cartesian(lab)
    rgb = xyz_to_srgb(lab_to_xyz(lab, "D50"), "D50")
    return go.Scatter3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2], mode="markers",
        marker=dict(size=2.5, color=[f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"
                                     for r, g, b in rgb]),
        name=f"{name} — patches", showlegend=True, hoverinfo="name")


#: Colours for the outlines in a slice, in the order gamuts are given.
_SLICE_COLOURS = ("#e8175d", "#3aa8d0", "#f2c744", "#6bd07a")


#: The page's own background. Plotly draws its plot on whatever the page is,
#: and a plain HTML page is white -- which shows as a bright frame around a
#: dark scene, and as a white flash every time the view reloads.
#: The scene's own colours, per appearance. Passed in rather than looked up,
#: so the page and the window around it can never disagree about which mode it
#: is showing.
SCENE_COLOURS = {
    "dark": dict(page="#111318", plot="#15181e", grid="#262b34",
                 text="#e8ecf2", axis="#3a4150", kept="rgb(105,112,126)",
                 wire="#9aa3b2"),
    "light": dict(page="#f7f7f5", plot="#ffffff", grid="#e4e4de",
                  text="#1c1b18", axis="#c4c4be", kept="rgb(176,180,188)",
                  wire="#6f6f68"),
}

_PAGE_BACKGROUND = "#111318"


def _write_dark_html(fig, out: Path, mode: str = "dark") -> Path:
    """Write the figure as a self-contained page whose paper matches the app."""
    html = fig.to_html(include_plotlyjs="inline", full_html=True)
    _PAGE_BACKGROUND = SCENE_COLOURS["light" if mode == "light" else "dark"]["page"]
    style = (f"<style>html,body{{background:{_PAGE_BACKGROUND};margin:0;"
             f"padding:0;overflow:hidden;}}</style>")
    if "</head>" in html:
        html = html.replace("</head>", style + "</head>", 1)
    else:
        html = style + html
    Path(out).write_text(html, encoding="utf-8")
    return Path(out)


def write_slice_html(gamuts, out: Path, lightness: float, title: str,
                     mode: str = "dark") -> Path:
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
            line=dict(color=_SLICE_COLOURS[i % len(_SLICE_COLOURS)], width=3),
            name=name, fill="toself", opacity=0.35))
    note = ""
    if empty:
        which = empty[0] if len(empty) == 1 else " and ".join(empty)
        note = (f"  —  {which} does not reach this lightness"
                if len(empty) == 1 else
                f"  —  {which} do not reach this lightness")
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers",
                             marker=dict(color=c["wire"], size=5, symbol="x"),
                             name="neutral grey", hoverinfo="name"))
    fig.update_layout(
        title=f"{title}  ·  lightness L* = {lightness:.0f}{note}",
        xaxis=dict(title="a*   green ← → red", zeroline=True,
                   zerolinecolor=c["axis"], gridcolor=c["grid"],
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(title="b*   blue ← → yellow", zeroline=True,
                   zerolinecolor=c["axis"], gridcolor=c["grid"]),
        paper_bgcolor=c["page"], plot_bgcolor=c["plot"], font_color=c["text"],
        legend=dict(orientation="h", y=-0.12),
        margin=dict(l=0, r=0, t=54, b=0))
    _write_dark_html(fig, out, mode)
    return out


def write_html(gamuts, out: Path, title: str, opacity: float | None = None,
               points: bool = False, patches=None,
               aspect: str = "data", styles=None, lost=None,
               mode: str = "dark", paint: str = "true",
               depth: float = 0.35) -> Path:
    """One self-contained page: plotly.js is inlined, so it works offline.

    *opacity* overrides the default (opaque alone, semi-transparent when two
    are shown so the inner one stays visible). *points* also plots every
    measured patch, which shows where the chart sampled densely and where it
    left the boundary to guesswork.
    """
    import plotly.graph_objects as go
    c = SCENE_COLOURS["light" if mode == "light" else "dark"]
    fig = go.Figure()
    base = opacity if opacity is not None else (1.0 if len(gamuts) == 1 else 0.55)
    for i, (name, g) in enumerate(gamuts):
        how = (styles[i] if styles is not None and i < len(styles) else "solid")
        marked = lost[i] if lost is not None and i < len(lost) else None
        if marked is not None:
            fig.add_trace(_mesh_lost(g, name, base, marked, c["kept"], depth))
        elif how in ("solid", "solid+mesh"):
            fig.add_trace(_mesh(g, name, opacity=base, wireframe=False,
                                paint=paint, index=i, depth=depth))
        if how in ("mesh", "solid+mesh"):
            fig.add_trace(_edges(g, name, colour=c["wire"],
                                 width=1.0 if how == "mesh" else 0.7))
        if points and patches is not None and i < len(patches):
            fig.add_trace(_patch_cloud(patches[i], name))
    fig.update_layout(
        title=title,
        scene=dict(
            xaxis_title="a*  (chroma →)", yaxis_title="b*", zaxis_title="L*",
            aspectmode=aspect,
            # START A LITTLE FURTHER BACK. Plotly's default camera frames the
            # data tightly, which on a wide, flat gamut crops the corners and
            # opens on a close-up of the middle. Pulling the eye out by a
            # quarter shows the whole shape at once; anybody who wants a
            # closer look can still scroll in.
            camera=dict(eye=dict(x=1.55, y=1.55, z=1.05)),
            xaxis=dict(backgroundcolor=c["plot"], gridcolor=c["grid"]),
            yaxis=dict(backgroundcolor=c["plot"], gridcolor=c["grid"]),
            zaxis=dict(backgroundcolor=c["plot"], gridcolor=c["grid"]),
        ),
        paper_bgcolor=c["page"], font_color=c["text"],
        legend=dict(orientation="h", y=-0.02),
        margin=dict(l=0, r=0, t=54, b=0),
    )
    # include_plotlyjs="inline" is the whole point: no CDN, no network, ever.
    _write_dark_html(fig, out, mode)
    return out


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
