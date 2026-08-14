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
| Draw it in | `"lab"`, `"luv"`, `"xyz"` | `"lab"` | `space=` on `build_gamut`, `reference_gamut`, `icc_gamut`, `gam_gamut` |

D50 is the ICC connection-space illuminant and what print measurement normally
uses; D65 is for display work.

### The three spaces, and what changes with them

`gamutview.SPACES` lists them and `gamutview.AXES` says how each is drawn and
labelled. A space needs only a pair of conversions in `_TO_XYZ` / `_FROM_XYZ`
and one entry in `AXES` to work everywhere — everything converts through XYZ,
so spaces never need to know about each other.

| Space | Axes | Hue circle | Volume in | Use it for |
|---|---|---|---|---|
| CIELAB | `a*`, `b*`, `L*` | yes | cubic Lab units | print — the default, and what every other number here assumes |
| CIELUV | `u*`, `v*`, `L*` | yes | cubic Luv units | displays and light sources; same lightness as CIELAB, blues and greens stretched |
| CIE XYZ | `X`, `Y`, `Z` | no | cubic XYZ units | the raw measurement, before any uniform space is applied |

Three consequences the code has to honour, and does:

1. **Volumes are only comparable within one space.** On the demo chart:
   702,327 in Lab, 931,617 in Luv, 0.0786 in XYZ — the same paper each time.
   The units string comes from `AXES[space]["units"]` and is never hard-coded,
   and the reported figure switches to more decimal places below 1,000 so the
   XYZ answer does not round to `0`.
2. **The comparison must be rebuilt in the same space as the charts**, or two
   different geometries get drawn on one pair of axes. `_rebuild_reference()`
   does this for a reference space, an ICC profile (from the remembered path,
   so it never re-asks for the file) and the visible solid. Changing the
   **white point** rebuilds it for the same reason.
3. **The slice, the rings and the greys need a lightness axis and a neutral
   centre.** CIELAB and CIELUV have both; XYZ has neither. In XYZ those three
   controls are disabled and carry a tooltip saying why, rather than drawing
   something meaningless — see `_apply_space_availability()`.

### A correction worth reading before removing this control

An earlier version of this note said the white point should not be a control
inside ChromIQ, because "the application already knows a printed chart was
measured under D50". That was too strong, and it was rightly questioned in
review. What the files actually show:

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
* **Every explanation is behind an ⓘ.** The twenty help paragraphs are
  `Hint` widgets: ChromIQ's own info icon — an 18px circle with an italic
  serif *i*, painted and cached per (colour, device pixel ratio) — sitting at
  the end of the row its control is on. Hovering shows the first sentence;
  clicking opens the full text in a `Notice`, which is wide enough to read it
  properly rather than squeezing it into a 346px column. The icon follows the
  chosen accent.
* **The window wears ChromIQ's masthead.** Eyebrow, title and the spectrum
  stripe, with ChromIQ's own metrics rather than an impression of them: a
  22x2 accent rule, the eyebrow in Menlo 12px at `#808080`, the title in
  Georgia 30px with letter spacing at 85%. The five accent choices are
  ChromIQ's own `SPEC_*` values, so the two applications are literally the
  same colours.
* **The stripe is NOT derived from the accent.** It is always the five
  `TAB_COLORS`, identical in light and dark. The stripe is the family mark; it
  stays the family's colours whichever accent this window is wearing.
* **Superseded: every explanation folds.** The eighteen help paragraphs are `Hint`
  widgets: a "What this does" line with an arrow, folded by default, and each
  one is remembered separately under `hint_<name>`. They are discovered with
  `findChildren(Hint)` rather than listed by hand, so a new one is remembered
  without anybody having to add it to the table. Folded they cost one 19px row
  each; open they are 47% of the column — 3,527px against 1,871px measured on
  the real window. Reset folds them all again.
* **Each explanation sits under the control it explains.** Obvious, and it was
  wrong once: the shape-colouring paragraph was added after the rings
  paragraph, so two "What this does" lines stacked and the lower one pointed
  three settings up the column.
* **A QSS `min-height` is applied at polish**, which is *after* a `QGridLayout`
  has worked out its row heights. The radio rows were sized for a 14px button
  that then drew 20px tall and ran into the row below, so the minimum is set in
  Python with `setMinimumHeight(20)` as well.
* **The message boxes are the window's own** (`Notice`), not `QMessageBox`.
  The native one drew its whole body bold, painted a system "?" glyph that was
  near-black on a near-black panel, and on macOS wore a title bar following the
  *system* appearance while the panel followed this window's. `Notice` is
  frameless with a real heading, an unbolded body, and the same buttons as the
  rest of the window; `say` / `warn` / `ask` are the three shapes used.
* **An empty readout takes no room.** `WrappedLabel(hide_when_empty=True)`
  hides itself when its text is blank — otherwise the Compare-with box and the
  coverage box each reserved a blank line before anything had been chosen. It
  is opt-in because a folded hint's label is hidden while still holding plenty
  of text, and showing it again would unfold it behind the user's back.

### Checking for a newer version

| Control | Values | Default | Goes to |
|---|---|---|---|
| Check for a newer version… | button | — | `updates.UpdateCheck` |
| Check when the app starts | on / off | **off** | `auto_update` in `_persisted()` |

**The default is not a preference, it is a promise being kept.** The release
notes tell everybody the app uses no network. Pressing the button *is* the
consent for that one request, the same way pressing Open consents to a file
being read — so the button is always there. A check that happens without
anybody pressing anything is a different thing, so it starts off.

One ordinary HTTPS GET to the public releases API. No account, no identifier,
nothing about the machine, the printer or the measurements, and nothing is
downloaded or installed automatically — the most it does is show a version
number and offer a link.

Two rules the code has to honour, and does:

* **A check you asked for always answers**, even to say you are up to date.
  Silence after pressing a button reads as a fault.
* **An unattended check speaks only when there is something newer.** Nobody
  wants a dialog every morning telling them nothing has changed.

Versions compare as numbers, not text — `1.10.0` is newer than `1.9.0`, which
a string comparison gets backwards. A tag that cannot be parsed is never
announced as an update, so a release tagged `nightly` stays quiet. Being
unable to reach the site is reported as a normal thing that happens, never as
a fault with the user's copy.

---

## 5. What is reported

| Readout | Source | Units |
|---|---|---|
| How much colour it holds | `Gamut.volume` | the chosen space's cubic units, from `AXES[space]["units"]` |
| Blacks reach / paper white | `gamutview.lightness_range()` | L\*, opponent spaces only |
| Coverage, both directions | `gamutview.coverage()` | per cent, ±0.2 |
| Both can print … of everything either can | `gamutview.shared_volume()` | per cent |
| Where each one reaches further | `gamutview.hue_reach()` | chroma, by hue family |
| Has anything changed? | `ti3gamut.compare_measurements()` | ΔE2000 |
| Worst colour cast in the greys | `ti3gamut.neutral_axis()` | ΔE-ish chroma |

**Three questions, not one.** "Does A fit inside B" is asked in both
directions and answers whether an image will survive a swap. "How much do
they share" (`shared_volume`) is symmetric and answers how alike two papers
are — a small gamut wholly inside a large one scores 100% on containment one
way round and still shares only part of the total, which is the honest answer
to "are these the same?". "Where does each reach further" (`hue_reach`) is the
one that usually decides which paper to use.

**A hue family is only called a win by more than `REACH_MARGIN` = 2.0
chroma.** On the demo papers one sits entirely inside the other and yet its
reds measure 0.6 further out — sampling precision, not an advantage. Announcing
that as a win would be a readout contradicting itself two lines further up.

**Everything in "How the two compare" needs the hue circle and the lightness
axis**, so the whole box is hidden in CIE XYZ rather than filled with figures
that do not mean what they say. The same applies to blacks/paper white.

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

### Where the window opens, and how small it may get

| | |
|---|---|
| **Opens at** | 1280 × 840, or the screen's available area minus a margin, whichever is smaller |
| **Centred** | on the screen the window is actually on, on first show only |
| **Smallest it can be** | 832 × 179 |

**The centring happens in `showEvent`, not in `__init__`.** Done at
construction it centres a size the window does not end up being: the controls
are built afterwards, the window grows to fit them, and it drifts down and to
the right by half of whatever it gained. That is what puts it in a corner.

**It centres on `self.screen()`, not `QApplication.primaryScreen()`.** With
two displays those are often different, and centring on the wrong one is the
other way a window ends up in a corner.

**Only on the first show.** Re-centring on every show would drag the window
back from wherever the user had put it.

**The frame is kept inside the screen** after centring, so a window taller
than the display cannot have its title bar pushed off the top where it cannot
be grabbed.

**Why 832 and not less.** The controls column is a fixed 366px and the 3D view
has a floor of 420px. That floor was 560, which forced a 972px minimum — wide
enough to hang off the side of a small display. 420 is still a scene worth
looking at, and the window can always be made bigger.

### Hover and focus

Every control that can be changed answers the pointer in **the chosen accent**,
not a grey: combo boxes, checkbox indicators, radio indicators, slider handles.
The same colour is used for keyboard focus, so somebody tabbing through sees
exactly what somebody pointing sees.

A grey highlight is indistinguishable from the resting border on a dark
background. The radios already used the accent, so before this half the
controls appeared to answer the pointer and half appeared not to — which reads
as some of them being disabled.

## 7. The log

| | |
|---|---|
| **Where** | macOS `~/Library/Logs/ChromIQ Gamut Viewer/` · Windows `%LOCALAPPDATA%` · Linux `$XDG_STATE_HOME` |
| **File** | `gamut-viewer.log` |
| **Cap** | 2 MB per file, 5 files kept — **10 MB at the very most, ever** |
| **Override** | `GAMUTVIEW_LOG_DIR`, which is how the tests keep out of the real one |

Follows ChromIQ's `core/logger.py` so somebody who has seen one has seen the
other. It never leaves the machine; it is plain text you can read and delete.

**The cap is not decoration.** A log that quietly eats a disk is a bug of its
own, so the total is asserted in the tests rather than merely configured, and
rotation is *observed* happening rather than assumed from the settings.

**A log that cannot be written never stops the app.** A read-only disk, a full
one, or a path the platform rejects all return `None` and the window opens
anyway. That last case was a real hole — `configure()` caught `OSError` but
not `ValueError`, and a test written for the case found it.

**The tests leave nothing behind.** Every one redirects `GAMUTVIEW_LOG_DIR`
into pytest's `tmp_path` and closes its handlers afterwards, so no file is
written outside the test's own folder and Windows can still delete it. The
whole suite, 85 tests, runs in about 5 seconds.
