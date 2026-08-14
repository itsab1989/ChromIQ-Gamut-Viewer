# Every setting, and what it decides

Written for whoever brings this into another application — ChromIQ or anything
else. Each entry gives the control as the user sees it, the value it produces,
where that value goes, and the reasoning behind the default, because a default
without a reason is just somebody's habit.

**Everything here is remembered.** Every control writes its value the moment it
is moved — not on quit — so a crash or a force-quit cannot lose a setting
somebody just chose. They come back on the next start. Nothing is stored in a
project file; it all lives in the platform's own settings store,
`QSettings("MeasuredGamutViewer", "MeasuredGamutViewer")`.

**"Start again with standard settings"** puts every one of them back, after
asking, and says plainly that open charts stay open and no file is touched.

The list lives in one place, `GamutApp._persisted()`, as
`(key, widget, kind, default)`. That is deliberate: a control added to the
window and forgotten there would silently stop being remembered, and nobody
would find out until they restarted.

---

## 1. What is on screen

### Your measured chart — up to two
| | |
|---|---|
| **Control** | "Open a measured chart…", drag-and-drop, or a path on the command line |
| **Accepts** | `.ti3`, `.cxf`, `.mxf`, `.txt` (measured charts), `.icc` / `.icm` (profiles), `.gam` (ArgyllCMS gamut surfaces) |
| **Produces** | `Measurement(name, device, lab, instrument, n_patches)` |
| **Where it goes** | `ti3gamut.read_measurement()` → `gamutview.build_gamut()` |

Files that are not `.ti3` are converted by the matching ArgyllCMS tool
(`cxf2ti3`, `txt2ti3`) rather than parsed here — these formats have corners and
ArgyllCMS already handles them, which is the same choice ChromIQ makes in
`workflow/reference_convert.py`. The converted copy goes to a temporary folder,
never beside the original: nobody's measurement folder should gain files
because they opened something to look at it. A `.gam` needs no tool at all — it
already holds the finished surface.

A profile is not a measurement, so it is routed to the comparison slot instead
of the chart slots. Two charts is the limit on purpose: a third would need a
third colour, a third coverage figure and a third row of controls, and nobody
has yet wanted one.

**A chart under 60 patches is called out.** Below that the shape is the outline
of a handful of dots rather than the edge of a printer, and any two small
charts look alike. The threshold is `GamutApp.TOO_FEW_PATCHES`; 60 was chosen
because an even 4-level sampling of three channels is 64, and real profiling
charts start in the hundreds. It warns and still draws, because a partial or
verification chart is a legitimate thing to look at.

### Compare with
| Option | What it answers |
|---|---|
| Nothing | — |
| A second measured chart | Which of two papers can print more |
| sRGB, Adobe RGB (1998), Display P3, ProPhoto RGB, Rec.2020 | Whether the images people send you will survive on this paper |
| An ICC profile from disk | How this paper compares with the profile a client sent |
| Everything the eye can see | How much of visible colour this paper holds at all |

These are three different questions and the answers are not interchangeable —
the interface says so, because "compare" invites the assumption that they are.

---

## 2. How the shape is worked out

| Value | Meaning |
|---|---|
| `"device"` *(default)* | Six faces of the device cube, mapped through the measurement |
| `"hull"` | Convex hull of the measured cloud |

Passed as `build_gamut(colors, drive_values)` versus `build_gamut(colors)`.

The default follows the printer's real, dented boundary; the hull bridges over
the concavities and over-states the gamut. Measured on a real chart: the hull
claims **8.5% more colour** than the boundary encloses. `"device"` needs the
device values, which every `.ti3` carries alongside the measurements.

---

## 3. What the colours are measured against

| Control | Values | Default | Goes to |
|---|---|---|---|
| White point | `"D50"`, `"D65"` | `"D50"` | `white_point=` on every conversion |
| Judge against the paper's own white | on / off | off | `relative=` on `read_ti3` |

D50 is the ICC connection-space illuminant and what print measurement normally
uses; D65 is for display work.

### A correction worth reading before removing this control

An earlier version of this note said the white point should not be a control
inside ChromIQ, because "the application already knows a printed chart was
measured under D50". That was too strong, and Sebastian was right to question
it. What the files actually show:

* **A `.ti3` records no illuminant or observer field.** Checked across several
  real measurements: there is `TARGET_INSTRUMENT`, `DEVCALSTD`, `COLOR_REP`
  and the spectral range — and nothing saying which illuminant the `XYZ_*`
  columns were computed under.
* **It is a choice, not a constant.** ArgyllCMS lets the observer be selected
  (`chartread -Q`), and measurement modes M0/M1/M2 differ in how they treat
  ultraviolet, which changes the result on optically brightened papers.
* **The spectra are usually in the file.** These charts carry `SPECTRAL_BANDS`
  with the per-band readings, which means XYZ can be recomputed under any
  illuminant rather than trusted from the `XYZ_*` columns.

So the honest position is the opposite of what was written first: the white
point is a **real** variable, and the best version of this feature would
compute XYZ from the spectra under a stated illuminant rather than reading
pre-computed columns and hoping. The `spectral.py` module already does exactly
that conversion for the visible-colour solid, so the machinery exists.

The relative option normalises to the brightest patch, so papers of different
brightness compare on shape rather than brightness. **Inside ChromIQ it should
follow the rendering intent already chosen** rather than being a second switch
that can contradict it.

---

## 4. How it looks

| Control | Values | Default | Live? |
|---|---|---|---|
| Appearance | `"light"`, `"dark"` | `"dark"` | stored |
| Accent | Magenta, Teal, Amber, Violet, Slate | Magenta | stored |
| How the shapes are coloured | `"true"`, `"solid"`, `"lightness"`, `"chroma"` | `"true"` | stored |
| Depth (shading) | 0–100 | 35 | **yes** — restyled in place |
| Set the lighting myself | on / off | off | — |
| ├ Ambient | 0.0–1.0 | 0.80 | **yes** |
| ├ Diffuse | 0.0–1.0 | 0.36 | **yes** |
| ├ Specular | 0.0–2.0 | 0.08 | **yes** |
| ├ Roughness | 0.0–1.0 | 0.78 | **yes** |
| └ Fresnel | 0.0–5.0 | 0.06 | **yes** |
| See-through (opacity) | 15–100 | 100 | **yes** — restyled in place |
| Proportions | `"data"`, `"cube"` | `"data"` | redraw |
| Detail | 6–40 steps | 20 | redraw |
| Draw each shape as | `"solid"`, `"solid+mesh"`, `"mesh"` | chart solid, others outline | redraw |
| Show every patch I measured | on / off | off | redraw |
| Show the greys | on / off | off | redraw |
| Show rings inside | on / off, 1–20 | off, 6 | redraw |
| Colour the outlines too | on / off | off | redraw |
| Set this for | all shapes / first / second / comparison | all | — |
| Show what the comparison cannot print | on / off | off | redraw |
| Slice it at one lightness | on / off, plus L\* 0–100 | off, 50 | redraw |

Notes worth carrying over:

* **Opacity defaults to fully opaque.** Any transparency blends the shape with
  what is behind it, which darkens colours on a dark background and washes them
  out on a light one — one value cannot flatter both.
* **Depth and opacity are restyled in the page**, not re-rendered. Rebuilding
  for every step of a slider means the picture only catches up when you let go,
  which is not what a slider is for.
* **Proportions default to true scale.** One unit of colour difference is the
  same length on every axis, which is what makes the shape and the volume
  honest. A printer has roughly twice the range in colour that it has from
  black to white, so the true shape really is wide and flat.
* **Detail 20 is where the volume stops changing** — 8 steps under-states sRGB
  by 0.5%, 20 is within 0.04% of a 32-step build, and all of them take
  hundredths of a second. It only affects the shape being compared against; a
  measured chart's detail comes from how many patches were measured, and
  pretending otherwise would be inventing data.
* **Three separate radio groups.** Radio buttons sharing a parent are one
  exclusive group in Qt, so appearance, accent and shape-colour each need their
  own `QButtonGroup` or picking one silently unchecks another.
* **The five lighting numbers are what Plotly's `mesh3d.lighting` takes.**
  Depth drives all five from one slider for everyday use; ticking "Set the
  lighting myself" reveals them and disables Depth, rather than leaving two
  controls fighting over the same values.
* **Reset must write before it reads.** Setting the widgets back and then
  restoring from the store re-read the values being reset, so the sliders
  quietly returned to where they had just been moved from.

---

## 5. What is reported

| Readout | Source | Units |
|---|---|---|
| How much colour it holds | `Gamut.volume` | cubic Lab units, as ArgyllCMS reports |
| Coverage, both directions | `gamutview.coverage()` | per cent, ±0.2 |
| Has anything changed? | `ti3gamut.compare_measurements()` | ΔE2000 |
| Worst colour cast in the greys | `ti3gamut.neutral_axis()` | ΔE-ish chroma |

**The drift check refuses rather than guesses.** Patches are matched on the
device values, not the sample number, because charts are randomised and the
same colour rarely carries the same number twice. When fewer than half the
patches appear in both files it says these are not two readings of one chart,
because a confident figure describing nothing is worse than no figure.

**ΔE is CIEDE2000**, verified against the Sharma, Wu and Dalal (2005) reference
pairs — the set published specifically to catch the hue-wrap and blue-rotation
mistakes every implementation makes. Worst error 0.00004. CIE76 was not used:
it badly over-states differences in the blues, which is exactly where a printer
drifts.

**Coverage is never shown as one number.** It is not symmetric: a paper can
hold nearly all of what a smaller one shows while the smaller holds only part
of it, and which direction matters is exactly what decides whether an image
survives being moved between papers.

The volume is the enclosed volume of the surface actually drawn, so it changes
when the shape does. A fixed seed and a stated margin of error mean the same
pair of gamuts always gives the same answer.

---

## 6. If this goes into ChromIQ

Two controls should disappear: the white point (the app knows) and the
relative-white switch (it should follow the rendering intent). One should
probably be added: which run's measurement to show, since ChromIQ already
knows about runs and this does not.

The open questions — a `scipy` dependency across six frozen targets, whether to
emit a `.gam` for `viewgam` rather than carry a second 3D renderer, and where
it should live — are in issue #1.
