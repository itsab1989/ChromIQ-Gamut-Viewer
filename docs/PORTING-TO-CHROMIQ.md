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

---

# Taking the colour-family report into ChromIQ

Asked for by a paper manufacturer, who wanted this shape of answer when
comparing one year's profile with the next:

```
Reds:      stayed the same
Blues:     drifted toward green
Yellows:   drifted toward red
Grays:     drifted toward red
```

and said in the same breath what makes it hard:

> *"of course then you have to draw an arbitrary line around 'what is a red'
> and 'what is a yellow'"*

She is right, the line cannot be removed, and everything below follows from
deciding to **state it** instead.

## What moves across, and how much of it

One function and five constants, in `gamutview.py`:

| Name | What it is |
|---|---|
| `family_drift(lab_a, lab_b)` | the whole report — a `FamilyDrift` per family, greys last |
| `HUE_FAMILIES` | the six family centres, already used by `hue_reach` |
| `NEUTRAL_CHROMA` | below this a colour is a grey, not a hue |
| `QUIET_DE` | ΔE 1 — "stayed the same" |
| `BOUNDARY_DEGREES` | how close to a line counts as borderline |
| `AGREEMENT` | how much a family must move as one before a direction is named |

**No Qt, no ArgyllCMS, no file handling.** It takes two `(N, 3)` Lab arrays of
the same colours in the same order and returns dataclasses. It ports as a
single copy-paste into a new `core/hue_families.py`, and every test of it
(`test_family_drift.py`, 40 cases) ports with it unchanged.

`FamilyDrift.sentence` is the pasteable line, with the patch count already in
it. Use that rather than formatting the fields again — the count being part of
the sentence rather than a column is deliberate, see below.

## Where it would fit, concretely

1. **The Measurement Report (#127 `reports/`, Report v3).** ChromIQ already
   compares two `.ti3` files patch by patch and prints a ΔE summary. That
   comparison already computes the two Lab arrays; feed them straight in and
   add a "which colour families moved" block under the existing numbers. This
   is the smallest useful port and needs no new data anywhere.

2. **Verification (#133).** the person who asked asked for this form by name:
   *"Reds: 3dE trending toward orange, Blues: 0.1dE, Greens: 4dE tending
   toward gray"*. A verification run measures a chart through a profile and
   holds both sides already. Same call, same sentences.

3. **Deciding whether a refinement pass is worth printing.** A run where only
   the greys moved and one where the blues moved want different answers, and
   today the operator gets one ΔE for the lot.

4. **The `.ti3` Tools.** Paper/ink contrast already reports per-file figures;
   this is the same kind of statement about a pair.

## The four things worth knowing before porting

1. **`hue_reach`'s rule is safe for a maximum and not for a mean.** The
   existing families were built for "which family reaches furthest", which
   takes a MAX per family — and a near-neutral colour never wins a maximum, so
   its unstable hue never matters. A mean is *made of* those colours. Measured:
   nudge one colour by 0.3 Lab units and ask how often it keeps its family —

   | chroma | 0.1 | 0.3 | 0.5 | 1.0 | 2.0 | 3.0 | 5.0 |
   |---|---|---|---|---|---|---|---|
   | stays put | 25% | 39% | 55% | 79% | 97% | 99% | 100% |

   Hence `NEUTRAL_CHROMA = 5`. It costs 1.5% of a real 9-step grid, and on a
   printed chart the colours it catches are the grey ramp — which is exactly
   what a reader means by "the greys".

2. **The sectors are not equal, and the blues are the least trustworthy.**
   Measured from the centres: reds 60°, yellows 75°, greens 52.5°, cyans 60°,
   blues 67.5°, magentas 45°. And CIELAB is not hue-linear through the blues —
   at a fixed hue angle, raising chroma visibly shifts the hue. CIEDE2000
   carries a rotation term aimed squarely at it, a Gaussian centred on hue
   **275°** with a **25°** spread; see the `rt` term in
   `gamutview.delta_e_2000`. The "blues" sector runs 232.5–300°, sitting on
   top of that correction. Any ChromIQ version should keep saying so.

3. **The patch count belongs in the sentence, not in a column.** A family of
   four and one of four hundred produce the same kind of line, and only that
   number tells a reader how much to trust it. In the CSV it gets its own
   column as well, because a spreadsheet is sorted; on screen and in prose it
   is inside the sentence where it cannot be skipped.

4. **Three kinds of movement, never collapsed into one.** Hue, chroma and
   lightness are separated against the family's own position, because they
   are different faults with different cures — a driver or ink-mix problem, a
   fade or ink-limit problem, and a linearisation problem. This is also what
   lets the report say "tending toward gray", which was one of the request's own
   examples and is not a hue statement at all.

## What must not be ported without the wording

**The footnote.** Every place this report appears — the panel, the saved page,
the CSV — carries a note saying where the line is, that it is drawn by the
application rather than by nature, and how many colours sat within
`BOUNDARY_DEGREES` of one and could have gone either way. Measured on a
boundary, the split is 51/49; without that sentence, every number in the report
is an unexamined claim. It is the answer to the objection the feature was
requested with, and shipping the report without it would be shipping the half
that misleads.

**"Mixed" and "but not certainly".** A family whose colours moved a long way
in no one direction is reported as *mixed* rather than given the direction of
their average, and a movement no bigger than its own standard error says so.
Both exist because the alternative reads as a finding. ΔE 8.2 of pure noise was
reported as "toward the yellows" during development and looked entirely
plausible.

**Under #130 these sentences are user-facing message text**, so in ChromIQ they
go to §M-PROPOSED of `unified_measurement_management.md` before they are
written into any tab. The count-bearing ones already have explicit singular and
plural forms ("1 patch" / "N patches") rather than "(s)".

## The same report, drawn — and what makes it cheap

The written report has a picture half: `drift_cloud(..., by_family=True)` and
`drift_direction(..., by_family=True)` draw the cloud as **one trace per
family** instead of one for the lot, each named `"blues — 132"`.

**That single change buys the whole filter for nothing.** Plotly's legend
already hides and shows traces on a click, so splitting on the families turns
the key into seven switches — in the window, in a saved page, offline, on a
phone — with no JavaScript, no new control and nothing to test in a browser.
Anything ChromIQ draws through Plotly gets the same deal.

Three things to keep if this is ported:

1. **One rule for the picture and the words.** `which_family` and
   `family_drift` both go through `gamutview._assign`. Two implementations
   would agree today and disagree after the first edit to either, and the
   reader would be left with a legend contradicting the sentence under it.
   There is a test that compares the two counts directly.
2. **One colour key, not seven.** Every trace carries the same fixed `cmin`
   and `cmax`, and only the first sets `showscale`. Without that the page
   grows seven identical bars down its side, and the scale stops being
   comparable between pictures.
3. **No entry for an empty family.** A legend row that switches nothing is a
   control that answers a click with nothing — the same rule this project
   applies to buttons.

**Where the count goes.** In the legend name, for the same reason it is in
every sentence: once they are dots, a family of eleven and a family of a
hundred and thirty-seven look identical, and the number is the only thing that
says how much of the picture you are looking at.

**Do not read the legend swatch as the family's colour.** It takes its colour
from the ΔE scale, because that is what the dots are painted by. The name
carries the meaning. This project deliberately refuses to paint a
colour-about-colour picture in the colours it describes — see `DIRECTION_SCALE`
— and the same caution applies here.
