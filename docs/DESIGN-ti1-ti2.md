# Design — opening a `.ti1` / `.ti2` chart, and checking it against a profile

**Status: decided, not yet built.** Basti's ruling, 2026-08-15, is recorded in
§0. The open questions at the end are answered there; what remains is the
building.

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

Still worth deciding while building, but none of them blocks a start:
1. Should a chart be a *thing you open* (its own slot, like a measurement) or a
   *thing you compare with*? Opening it means it can be shown alone, which is
   right for **C** and wrong for **A**.
2. Which intent should the prediction use — relative colorimetric, or whatever
   the chart was built with, if the chart records it?
3. Should `.ti2` sheet positions be used at all (they would allow "this corner
   of the sheet is where the out-of-gamut patches are"), or ignored?
4. i1Profiler `.pxf`/`.txt` targets: convert through ArgyllCMS as now, or read
   directly? ArgyllCMS is not always installed.
5. Does the answer need to be exportable — a table of the outside patches — or
   is seeing it enough?
