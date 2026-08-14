# Python port

A port of `gamutview.m` so the same idea can be used from Python. MIT, like the
original.

The MATLAB version both **computes** the gamut and **draws** it into a figure.
This port does only the computing and returns plain NumPy arrays, because every
Python project already has its own way of drawing — Plotly, Matplotlib, VTK, a
Qt WebEngine view. `demo.py` shows both.

```python
from gamutview import build_gamut

# colours you measured, and the device values that produced them
gamut = build_gamut(measured_xyz, drive_rgb, white_point="D50")

gamut.vertices      # (N, 3) points in Lab
gamut.faces         # (M, 3) triangles
gamut.colors        # (N, 3) sRGB 0..1, to paint each vertex its own colour
gamut.volume        # enclosed volume, cubic Lab units
gamut.cylindrical() # the same points as (C·cos h, C·sin h, L)
```

## The two modes

**`build_gamut(colors)`** takes the convex hull of the measured cloud. Simple,
but a real printer gamut is not convex: a hull bridges straight over the
concavities a printer actually has, most visibly along the cyan-to-blue ridge,
so it over-states the gamut.

**`build_gamut(colors, drive_values)`** is the one worth having, and it is the
original's real contribution. Give it the device values you *asked* for
alongside what you *measured*, and the surface is built from the six faces of
the device cube mapped through the measurement — so it follows the device's
real, dented boundary. Any measured chart already has both halves of that pair.

On an 8×8×8 sRGB grid the difference is plain:

```
  hull            55 vertices    106 triangles
  device-cube    384 vertices    588 triangles
```

Same volume — both report the hull's — but the second keeps the shape.

## Colour science

Conversions state their white point, which matters: the same XYZ under D50 and
under D65 give different Lab, so a gamut plotted under the wrong one is the
wrong shape. Default **D50**, the ICC connection-space illuminant and what print
measurement uses; pass `white_point="D65"` for display work. sRGB output is
always against D65, its own defined white, with a Bradford adaptation when the
working white differs — never a silent mismatch.

`gamut.colors` is ink for the screen, not a colour value: out-of-gamut points
(most of a printer's darkest, most saturated corners) are clipped.

Only XYZ, Lab, LCh and sRGB are implemented — what a gamut needs. For a general
colour library use [colour-science](https://www.colour-science.org/).

## Running it

```bash
pip install numpy scipy          # plotly or matplotlib for the demo
python -m pytest python/ -q      # 17 tests
python demo.py                   # writes gamut-demo.html
python demo.py --show            # matplotlib window instead
```

## Differences from the MATLAB original

* Computing and drawing are separated; nothing is plotted for you.
* Each cube face is triangulated with Delaunay over the two remaining device
  channels, rather than by walking four nearest neighbours per vertex. Same
  intent, without the assumptions about ordering.
* Rows that are NaN or infinite are dropped, so one failed patch reading does
  not take the whole gamut with it, and duplicate device values are removed.
* Unusable input raises with a reason: fewer than four colours, points that do
  not enclose a volume, mismatched pair lengths, an unknown white point.
* The spectral helpers (`spectra2colors`, the visible-spectrum data) are not
  ported. They are the interesting next piece if the visible-locus overlay is
  ever wanted.

## The demo app

```bash
pip install PyQt6 PyQt6-WebEngine numpy scipy plotly
python gamut_app.py                 # then "Open measurement…"
python gamut_app.py chart.ti3       # or start with a file
```

Open the `.ti3` ArgyllCMS wrote when you read a printed chart and see the gamut
those patches enclose, in 3D, in its own colours, with its volume. Open a second
one and both are drawn together with the difference stated in per cent.

There is a command-line version too, if you only want the picture:

```bash
python ti3gamut.py chart.ti3 --open
python ti3gamut.py glossy.ti3 matte.ti3 --relative
```

It writes one self-contained HTML file — the viewer travels inside the page, so
it opens anywhere with no network.

### The controls, and why each one is there

| Control | What it decides |
|---|---|
| **How the shape is built** | Follow the device boundary (keeps the printer's real dents) or convex hull (bridges over them and claims more colour than you have) |
| **Reference: D50 / D65** | Which white point Lab is computed under. D50 for print, D65 for displays |
| **Measure against the paper's own white** | On, two papers of different brightness compare fairly — what a relative-colorimetric profile does. Off, the absolute numbers the instrument reported |
| **Opacity** | So an inner gamut stays visible under an outer one |
| **Show the measured patches** | Every patch as a dot, so you can see where the chart sampled densely and where the boundary is guesswork |
| **Gamut volume** | Cubic Lab units, the same measure ArgyllCMS reports |

Runs on macOS, Windows and Linux — every dependency ships wheels for all three.

<p align="center">
  <a href="https://ko-fi.com/itsab1989"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support this on Ko-fi" height="36"></a>
  <br>
  <sub>The ChromIQ Gamut Viewer is free and always will be. If it's useful to you, a coffee is a kind way to say thanks — completely optional, and it stays fully featured either way.</sub>
</p>
