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


def _mesh(gamut, name: str, opacity: float, wireframe: bool):
    """One Plotly mesh for a gamut, painted with its own colours."""
    import plotly.graph_objects as go
    v = gamut.cylindrical()
    colours = [f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
               for r, g, b in gamut.colors]
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2],
        i=gamut.faces[:, 0], j=gamut.faces[:, 1], k=gamut.faces[:, 2],
        vertexcolor=colours, opacity=opacity, name=name, showlegend=True,
        flatshading=False, hoverinfo="name",
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


def write_html(gamuts, out: Path, title: str, opacity: float | None = None,
               points: bool = False, patches=None,
               aspect: str = "data") -> Path:
    """One self-contained page: plotly.js is inlined, so it works offline.

    *opacity* overrides the default (opaque alone, semi-transparent when two
    are shown so the inner one stays visible). *points* also plots every
    measured patch, which shows where the chart sampled densely and where it
    left the boundary to guesswork.
    """
    import plotly.graph_objects as go
    fig = go.Figure()
    base = opacity if opacity is not None else (1.0 if len(gamuts) == 1 else 0.55)
    for i, (name, g) in enumerate(gamuts):
        fig.add_trace(_mesh(g, name, opacity=base, wireframe=i > 0))
        if points and patches is not None and i < len(patches):
            fig.add_trace(_patch_cloud(patches[i], name))
    fig.update_layout(
        title=title,
        scene=dict(
            xaxis_title="a*  (chroma →)", yaxis_title="b*", zaxis_title="L*",
            aspectmode=aspect,
            xaxis=dict(backgroundcolor="#181a1f", gridcolor="#333"),
            yaxis=dict(backgroundcolor="#181a1f", gridcolor="#333"),
            zaxis=dict(backgroundcolor="#181a1f", gridcolor="#333"),
        ),
        paper_bgcolor="#111318", font_color="#e8ecf2",
        legend=dict(orientation="h", y=-0.02),
        margin=dict(l=0, r=0, t=54, b=0),
    )
    # include_plotlyjs="inline" is the whole point: no CDN, no network, ever.
    fig.write_html(str(out), include_plotlyjs="inline", full_html=True)
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
