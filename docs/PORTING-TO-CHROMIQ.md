# Taking the picture export into ChromIQ

Notes for whoever folds this viewer's export into ChromIQ itself. Written
while it was built, so the reasons are the real ones rather than reconstructed.

## The shape of it

Four modules, and only one of them knows about Qt:

| Module | Needs Qt | What it is |
|---|---|---|
| `picture.py` | no | the **rules**: which formats exist, what each can hold, how many frames close a loop, what to call the file, how big it will be, the ready-made looks, and the contrast arithmetic |
| `movie.py` | no | finding an encoder, what it can write, quality → codec settings, and the two **writers** (a pipe to ffmpeg, and Pillow) |
| `looks.py` | no | saved looks: one JSON file each, in ChromIQ's own presets folder |
| `gamut_app.py` | yes | the dialog, the section in the column, and grabbing the frames |

**Everything worth testing is outside Qt.** That was deliberate and it is why
the tests run in eight seconds without a display.

## The five things that cost a day each

1. **`runJavaScript` does not wait for a promise.** Timing measured through it
   is the call, not the work — a first attempt measured 33 ms for something
   that took 630. And a script that has *finished* says nothing about what is
   on screen: WebGL composites on its own schedule. Wait for **two**
   `requestAnimationFrame` ticks or frames get grabbed before the shape moved.
   `gamut_app._run_js_now`.

2. **A copy of the screen has no transparency in it.** The graphics card has
   already mixed everything onto a ground. Asking the page politely and
   grabbing gives a solid picture. Recover it by drawing each frame twice, on
   white and on black, and subtracting: `picture.alpha_from_two_grounds`. It is
   exact, including anti-aliased edges, and it costs one extra grab a frame.

3. **Qt centres a progress bar's percentage on the widget, margins and all**,
   and on the font box rather than on the ink. Three pixels low at ordinary
   resolution, five on a high-resolution screen. `gamut_app.CentredProgressBar`
   and `_baseline_for`.

4. **Pillow ignores a quality you never pass.** An animated WebP written
   without `quality=` comes out at 80 and the surface shimmers as it turns.
   And `method=6` costs 27× the time of `method=4` for 0.5% smaller —
   measured, 49.2 s against 1.8 s on 120 frames.

5. **Encode as you go, not at the end.** Holding a long loop as frames costs
   hundreds of megabytes and the final encode blocks the window for seconds.
   Piping raw RGBA to ffmpeg through a bounded queue keeps memory flat and
   makes the window responsive throughout. `movie.MovieWriter`.

## ffmpeg, and the licence

Run as a **separate program**, never linked. That is what keeps a GPL encoder
away from MIT application code, and it is the same arrangement ChromIQ already
uses for ArgyllCMS. See `docs/THIRD-PARTY.md`. The discovery order —
chosen path, environment variable, bundled copy, PATH, usual places — mirrors
`argyll.py` deliberately, so the two behave the same way.

**Only offer what the build can do.** `ffmpeg -encoders` is read once and
cached; a distribution build without libx265 must not be offered H.265 and
then fail at the end of a two-minute export.

## Settings and presets

Looks live in ChromIQ's own presets folder (`~/Library/Preferences/ChromIQ/
presets/Picture Looks` and the platform equivalents), one JSON file each, for
exactly the reason `core/preset_store.py` gives: so they can be browsed,
copied and shared with a file manager. Removing one **archives** it to
`old/<date and time>/` rather than deleting — ChromIQ's own rule.

## If it is ported

`picture.py`, `movie.py` and `looks.py` can move across unchanged. The Qt side
needs: a section in a column, a save dialog, a frame source (whatever ChromIQ
is drawing), and `_finish_writing` for the off-thread encode. ChromIQ already
has `NoScrollComboBox`, `NoScrollSpinBox` and its own file dialogs, so the
widget helpers here should be dropped in favour of those.

Strings here are plain English; ChromIQ would need `tr()` around every one,
and the parameter-style tooltips split into title and body.

---

# Taking the chart check into ChromIQ

Added v2.2.0. This one is worth more to ChromIQ than the picture export is,
because ChromIQ **builds** the charts — its Create Chart tab has a mode that
picks patches from a profile's gamut, and nothing there has ever drawn the
result to check it.

## What moves across unchanged

| File | What it is | Depends on |
|---|---|---|
| `python/cgats.py` | a multi-table CGATS reader | numpy only |
| `python/chart.py` | reading a chart, placing it, counting it | numpy, scipy, and `icc_read` for the placing |

Neither imports Qt. `cgats.py` in particular is worth taking on its own: it
would replace the ad-hoc parsing in ChromIQ's own `.ti1`/`.ti2`/`.ti3` handling
and fixes a fault that code shares (see below).

## The four things the real files taught

Every one of these was found by opening an actual file. All four are live in
ChromIQ too.

**1. A `.ti1` is three tables.** Not a corner case — `targen` writes three
every time: the chart, the eight density extremes, the nine device
combinations. Any reader that goes from the first `BEGIN_DATA` to the last
`END_DATA` swallows all three with the headers between them, and reports

    ValueError: could not convert string to float: 'chart'

naming a word out of the second table's `DESCRIPTOR` line. **Worth grepping
ChromIQ for**: anything doing `text.split("BEGIN_DATA")[1].rsplit("END_DATA")`
has this bug, whether or not it has bitten yet.

**2. `COLOR_REP` is `iRGB`, not `RGB`,** for every inkjet chart ArgyllCMS has
ever written. A test for the literal `"RGB"` rejects all of them.

**3. A `.ti1` carries XYZ columns, and they are not measurements.** They come
out of `targen`'s device model; with no `-c` profile that model is crude enough
to write the black patch as XYZ 1, 1, 1. Read as measurements they make a
plausible, symmetrical, entirely fictional gamut. `ACCURATE_EXPECTED_VALUES
"true"` marks the files where `targen` had a real profile to predict with — the
ChromIQ verification set carries it.

**4. i1Profiler's text export counts ink to 255, and a `.ti1` counts to 100.**
The same chart, both ways, and reading either on the other's scale multiplies
every patch by 2.55 or 0.39 and still looks entirely plausible. `chart.py`
decides from the file's own numbers and says on screen when it could not tell.
Related: `txt2ti3` **refuses** an i1Profiler target outright — it converts
measurements and a chart has none — so these are parsed directly, which also
means the feature works with no ArgyllCMS installed.

## The colour science, which is where the trap is

A chart is placed through the profile's **A2B1** table, so the patches are
relative to the paper's white by definition — device white lands on L\* 100.
A measurement read **absolutely** keeps the white the instrument saw.

Compare the two and every light patch floats above the measured shape for no
reason to do with the printer. The same chart, paper and profile:

| the measurement judged against | outside | worst ΔE |
|---|---|---|
| an absolute D50 | **624** | 4.54 |
| its own white | **0** | 0.96 |

**ChromIQ has the same hazard anywhere it compares a profile's output with a
measurement**, and it is the one thing in this feature that would have shipped
a convincing false alarm. The viewer detects the mismatch, says so in the
readout, and names the tick box — it never moves the setting itself, because
that setting changes every other figure on screen.

The second number worth knowing: a gamut surface is drawn through a grid of
samples and the real edge bulges between them, so patches always land a whisker
outside any surface, *including the one that placed them*. Measured on the
5960-patch ChromIQ verification set against its own profile, the count moved
353 → 122 as the grid was refined while the distance fell 0.58 → 0.05 ΔE. So
the count is the sampling and the distance is the answer: anything within
**1.0 ΔE2000** is reported as *on the edge*, not outside.

## Where it would live in ChromIQ

Not as a fourth tab. Two places, both existing:

* **Create Chart → the verification mode**, as a *Check this chart* button
  beside the one that builds it. The profile is already known there, so
  **Placed through** needs no chooser at all — which removes the only control
  in the viewer's panel that a beginner has to think about.
* **Tools → Inspect a measurement**, which already opens `.ti3` files, gaining
  the same for a `.ti1`.

The answer belongs in the run folder as a report, following `#127`: the counts
per shape, and one line per patch that is outside carrying its `SAMPLE_LOC` —
so a patch reported outside can be found on the printed sheet. The viewer
writes exactly those columns from **Save the numbers as a table**.

## What must not be ported without the wording

The feature is one sentence away from claiming something false, and the
sentences are load-bearing:

* A chart is **drawn as dots, never as a surface**. Held apart from the shape
  slots in the code rather than by convention, so it cannot become one by
  accident.
* Against **the profile it was built from**, the answer checks the chart
  builder and *not the printer*, and the panel says so in those words. It is
  still a real check — it catches a mismatched rendering intent, ink counted
  0–255 where the file wants 0–100, patches clipped to a box around the gamut
  rather than to its surface, and a profile swapped between building and
  printing.
* Against **a measurement**, it checks the printer. That is the useful one.
* Both are reported at once, one line each, so neither can be mistaken for the
  other.

`tests/test_chart.py` and `test_chart_panel.py` carry the reasoning as well as
the assertions; `scripts/drive_chart.py` drives the real window through the
whole journey and is what caught the verdict naming the wrong file when a
profile and its measurement share a stem — which, for `Glossy-paper.icc`
beside `Glossy-paper.ti3`, is the ordinary case rather than a contrived one.
