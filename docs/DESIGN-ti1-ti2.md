# Design — opening a `.ti1` / `.ti2` chart, and checking it against a profile

**Status: built and shipped in v2.2.0.** Basti's ruling, 2026-08-15, is
recorded in §0. §10 records what the real files turned out to be, which is not
what §4 and §5 assumed — four of the assumptions here were wrong, and every one
of them was found by opening an actual file rather than by reasoning about the
format.

## 0. What was decided

> *"I want to allow to visualise that the patches ChromIQ gave me really are
> inside of the gamut. So those file types should be supported. It does not
> hurt to support them since this is a separate project anyway, and even added
> as a tool inside ChromIQ, more options are better."*

**All three variants get built, A first**, and the file types are supported
whether or not any single check is the sharpest one available.

**And a correction to §2 below, which overstated its case.** Checking
ChromIQ's patches against the profile they were built from is *not* worthless
because it is circular. It does not verify the printer — but it verifies **the
chart builder**, and that has real failure modes worth catching:

* the builder used one rendering intent and the check another;
* device values scaled 0–255 where the file wants 0–100;
* patches clipped to the gamut's bounding box rather than to its surface;
* a profile silently swapped between building and printing.

Any of those puts patches outside a gamut they were promised to be inside, and
every one of them is invisible until somebody draws the picture. What it must
NOT do is *claim* to be a colour verification. The wording on screen carries
that distinction:

* **A** — *"Do these patches sit inside what this profile says it can print?"*
  A check of the chart, against the profile it was made from or any other.
* **B** — *"Do they sit inside what the paper actually achieved?"* A check of
  the profile, against a measurement. The one that finds printer trouble.
* **C** — *"Are they spread evenly?"* A check of the chart on its own, needing
  no profile at all.

Three questions, three answers, named so nobody mistakes one for another —
which is principle 7, and the whole reason to write them down before building.

## 1. What is being asked

ChromIQ's Create Chart tab has a verification mode that builds a chart **from
a profile's gamut** — patches chosen to sit inside what the profile says the
printer can do. The question is whether those patches really do sit inside it,
and whether they are spread sensibly through the space rather than bunched.

Today this viewer opens **measurements** (`.ti3`, `.cxf`, `.mxf`, `.txt`),
**profiles** (`.icc`, `.icm`), **gamut files** (`.gam`) and **pictures**. A
`.ti1` or `.ti2` is none of those, and the difference matters more than it
looks.

## 2. The one thing that makes this different: there is no measurement

| File | What it holds | What it can answer |
|---|---|---|
| `.ti3` | device values **and** what came back off the paper | what the printer really did |
| `.ti2` | device values, plus where each patch sits on the sheet | what will be *asked for* |
| `.ti1` | device values only | what will be *asked for* |

A `.ti1` is a **request**, not a result. Nothing in it has been printed or
measured. So the viewer must never draw it as though it were a gamut: a hull
around a set of requested RGB values is not a gamut of anything, and calling
it one would be exactly the sort of confident-looking nonsense this
application exists to avoid.

**What it can honestly show** is where those requested values *land* once a
profile is asked what colour they would make. That is a prediction, it depends
entirely on the profile, and it must be labelled as one.

### The circularity trap, stated plainly

If the chart was built **from** profile P, and we then push its patches
through **the same** profile P and ask "are they inside P's gamut?", the
answer is nearly always yes — and it is yes *by construction*, not because
anything was verified. That check would look reassuring and mean nothing.

This has to be designed around, not papered over. Three honest questions,
which are different:

* **A — Are the patches inside the profile's gamut?** Only meaningful when the
  profile doing the drawing is **not** the one the chart was built from, or
  when the chart came from somewhere else entirely (a vendor chart, an
  i1Profiler target, a hand-made `.ti1`).
* **B — Are the patches inside what the paper actually achieved?** Push them
  through the profile to Lab, compare against a **measured** `.ti3` gamut.
  This is a real check with a real answer, and it is the useful one: it says
  "your profile promises these, and the paper did not deliver them."
* **C — Are they well spread?** No gamut needed at all. Show the points and
  their spacing — clumping and gaps are visible immediately, and this is the
  question a chart designer actually has.

**All three are worth building** — see §0. A must name the profile it is
checking against on screen, so that using the same profile twice is a visible
choice rather than an accident, and the caption must say what A does and does
not prove.

## 3. The user's journey, click by click

1. **Open a measurement, a profile or a picture…** — the dialog gains
   *Charts to be printed (\*.ti1 \*.ti2 \*.txt)*.
2. The file opens as a **cloud of points**, never a solid, with a caption that
   says so: *"1188 patches to be printed — not measured. Shown through
   \<profile\>."*
3. If **no profile is open**, the points cannot be placed at all, and the
   viewer says so rather than guessing: *"A chart on its own is a list of ink
   amounts. Open the ICC profile you built it from, or the measurement of the
   paper, and these can be placed."*
4. Once a profile or measurement is open, **Compare with** gains the chart, and
   the figures panel reports: how many patches, how many fall outside, the
   worst distance outside in ΔE, and the largest gap between neighbours.
5. **Where the files land:** nothing is written. This is a read-only view, like
   opening a measurement.

## 4. What already exists, and must be reused

| Need | Already in the code |
|---|---|
| Reading a `.ti3` table | `ti3gamut.py` — the same CGATS reader handles `.ti1`/`.ti2`, which are the same format with different fields |
| Device values → Lab through a profile | `icc_read.py` (`_lut_to_pcs`, `_matrix_to_pcs`, `PCS_WHITE`) |
| A profile's own surface | `references.icc_gamut`, and ArgyllCMS `iccgamut` when present |
| Drawing loose points | `ti3gamut._patch_cloud` |
| Inside/outside a shape | `gamutview.outside_of`, `coverage` |
| i1Profiler targets | `CONVERTERS` in `ti3gamut.py` already handles `.txt` via ArgyllCMS `txt2ti3` |

**Nothing new is needed to read the file.** A `.ti1` is CGATS with
`RGB_R/G/B` fields and no `LAB_*` or `XYZ_*` — which is precisely how the
loader should decide what it has, rather than trusting the extension.

## 5. Colour science, stated

* Device values are `0..100` in CGATS, not `0..255`. Getting this wrong
  scales every patch by 2.55 and looks plausible.
* The profile's **A2B1** (relative colorimetric) table is the right one for
  "where would this land", with A2B0 as a fallback. The intent must be stated
  on screen, because A2B0 and A2B1 disagree near the edges — which is exactly
  where this check lives.
* PCS white is the ICC constant `0.964203, 1.0, 0.824905`, **not** CIE D50.
  `icc_read.PCS_WHITE` already carries this.
* "Outside" is measured as ΔE from the patch to the nearest point on the
  target surface. ΔE2000 for reporting; ΔE76 is not good enough near the
  edges of a gamut.

## 6. Edge cases

* A `.ti1` with no RGB fields (a CMYK target) → say so; this viewer is RGB.
* A `.ti2` whose patches repeat (charts often duplicate for averaging) → count
  unique device values, and say how many were repeats.
* A chart with 3 patches → too few to say anything about spread; report the
  patches and skip the spacing figure.
* A chart opened with **no** profile and **no** measurement → the state
  message in step 3, never an empty window.
* A profile that is v4 → already handled; `icc_read` reads what ArgyllCMS
  declines.
* Values outside 0..100 → clamp, and say how many were clamped.

## 7. Tests

Pure: field detection on real `.ti1`/`.ti2`/`.txt` samples; the 0..100 scale;
duplicate counting; spread figures on a known grid. Against real data: a chart
ChromIQ itself built from a known profile, where the expected answer is known
in advance. On screen: open a chart with no profile (the message), then with
one (the cloud), then against a measurement (the outside count).

## 8. Rating, and why

Correctness **8** — the arithmetic is all reused and already tested; the risk
is entirely in *what is claimed*, not in the numbers. Robustness **7** — the
file variants are the unknown; real vendor `.ti1` files are less uniform than
the specification suggests. Maintainability **9** — no new reader, no new
maths. Efficiency **9** — a few thousand points is nothing.

## 9. Open questions

**Answered in §0:** all three, A first, with the file types supported
regardless.

All five are now answered, and four of them by the files rather than by
argument:

1. **A chart is a thing you open**, in a slot of its own — never in `_slots`
   beside the shapes, so "a chart must not be drawn as a solid" is structural
   rather than a convention somebody has to keep. It coexists with the two
   shape slots and the comparison, so **A** and **B** fall out of the same
   mechanism: the answer is reported against *every* shape on screen, one line
   each. That also makes the circularity visible rather than hidden — the line
   for the profile that placed the patches says so, in those words.
2. **Relative colorimetric**, from `A2B1`, with `A2B0` as a fallback, and the
   one actually used is named on screen. No real `.ti1` records the intent it
   was built with, so there is nothing to follow.
3. **The `.ti2` positions are used** — not to draw with, but in the exported
   table, so a patch reported outside can be found on the printed sheet. It
   costs one column and turns "627 are outside" from where the question ends
   into where it starts.
4. **Read directly.** Not a preference: `txt2ti3` refuses an i1Profiler target
   outright — *"doesn't contain field XYZ_X, LAB_L or spectral"* — because it
   converts measurements and a chart has none. Reading it here also means it
   works with no ArgyllCMS installed at all.
5. **Yes, exportable.** Save the numbers as a table gains the counts per shape
   and then one line per patch that is outside: which shape, patch number,
   position on the sheet, the ink amounts in the file's own units, the
   predicted Lab, and how far outside in ΔE2000.

## 10. What the real files turned out to be

Every one of these was found by opening a file, and every one contradicts
something written above in good faith.

**A `.ti1` is three tables, not one.** Not a corner case — it is what `targen`
writes every time. The first table is the chart, the second the eight density
extremes, the third the nine device combinations. §4 said *"nothing new is
needed to read the file"*, and that was wrong: reading from the first
`BEGIN_DATA` to the last `END_DATA` swallows all three with their headers, and
the first thing the number parser meets is the word `chart` out of the second
table's `DESCRIPTOR` line:

    ValueError: could not convert string to float: 'chart'

A perfectly well-formed file, and an error naming a word from a comment. Hence
`cgats.py`. The same fix makes `read_ti3` take the first table rather than
everything between the first and last markers.

**A `.ti1` carries XYZ columns.** §2's table says a `.ti1` holds *"device
values only"*. It does not: `targen` writes `XYZ_X XYZ_Y XYZ_Z` from its own
device model. With no `-c` profile that model is crude — the black patch comes
out as XYZ 1, 1, 1 — so the file read as a perfectly plausible measured gamut
made entirely of predictions. They are kept as `Chart.expected`, never used to
place a patch, and `ACCURATE_EXPECTED_VALUES "true"` marks the files where
`targen` was given a real profile to predict with.

**`COLOR_REP` is `iRGB`, not `RGB`.** Anything matching on the literal string
`"RGB"` rejects every inkjet chart ArgyllCMS has ever written.

**Counting what is outside needs three numbers, not two.** A gamut surface is
built from a grid of samples and the real edge bulges between them, so patches
always land a whisker outside any surface — including the surface of the very
profile that placed them. Pushing the 5960-patch ChromIQ verification set
through a real printer profile and measuring against that same profile:

| grid | vertices | outside | worst ΔE | average ΔE |
|---|---|---|---|---|
| 9³ | 486 | 353 | 0.584 | 0.063 |
| 17³ | 1734 | 262 | 0.220 | 0.022 |
| 25³ | 3750 | 209 | 0.185 | 0.013 |
| 33³ | 6534 | 162 | 0.073 | 0.008 |
| 41³ | 10086 | 122 | 0.046 | 0.007 |

The count barely moves and the distance collapses. The count is the sampling;
the distance is the answer. Anything within **1.0 ΔE2000** of the surface is
reported as *on the edge* rather than outside.

### The one that would have shipped a false alarm

**A chart and a measurement are not necessarily measured against the same
white**, and nothing above noticed. A chart is placed through the profile's
relative colorimetric table, and *relative colorimetric* means, by definition,
that the paper's white becomes L\* 100. A measurement read absolutely keeps the
white the instrument saw. On the demo glossy paper that is L\* 100 against
L\* 93.8, so every light patch floats above the measured shape for no reason to
do with the printer. The same chart, the same paper, the same profile:

| the measurement judged against | outside | worst ΔE |
|---|---|---|
| an absolute D50 | **624** | 4.54 |
| its own white | **0** | 0.96 |

Six hundred patches of pure artefact, and a picture of them would have looked
entirely convincing. The window says which one is being looked at and names the
tick box that changes it — and never moves it, because that setting changes
every other figure on screen as well.

## 11. What is deliberately not claimed

* **The test is against a skin over the shape's own corners**, the same surface
  the rest of the application paints with, so the counts here can never
  disagree with the colouring beside them. A real printer's edge has dents and
  a skin bridges them, which makes the test careful in exactly one direction: a
  patch it calls outside really is outside, and a patch down in a dent may be
  called inside. It can miss something; it cannot invent something.
* **A `.ti1`'s own XYZ is never drawn.** It is a prediction from a device
  model, and drawing it would be inventing a measurement.
* **Question A is not a colour verification** and the window says so in those
  words whenever the profile doing the judging is the one that placed the
  patches.
