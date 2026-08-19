# The inside of an open shell — measurement trail (work in progress)

Four reports against 2.39.6, one mechanism. Every number below was measured;
the scripts beside this file are the instruments. Placed under docs/probes/
so the work survives a sweep of /private/tmp — relocate freely.

## The instruments

* `harvest.py` — loads a saved page in QWebEngine, presses it into the
  reported state (agree 0%, outline hidden), then per camera records a
  screenshot plus the GL scene's model/view/projection matrices and the drawn
  mesh (from `_fullData` — the written file is binary-packed).
* `classify.py` — z-buffer rasteriser over those matrices. Its screen-winding
  facing test turned out to be UNRELIABLE on the page mesh (see below); its
  loaders are reused by classify2.
* `classify2.py` — the winding-free classifier. At each covered pixel, count
  crossings of the CLOSED shell strictly before the drawn mesh's first hit:
  even → the sheet is seen from outside; odd → from inside the shape.
  Calibration is exact: on the closed shell itself, 10,704 covered pixels,
  0 classify inside. The --mutate flag flips the parity and the counts swap,
  so the numbers answer to the classification.
* `window_repro.py` — Basti's window scenes reproduced in the REAL window
  (GamutApp), against whichever tree argv[1] names, so 2.39.6 and the
  pre-fix baseline (367b066^) are photographed by the same script.

## Steep-angle question (page 14, agree 0%, outline hidden) — SETTLED

The remainder is three pieces (yellow/orange 100 faces, magenta 131,
blue/green 248; 479 of 1,324 — the fix's own numbers). At his angles the
pixels are covered by the pieces' INNER sides, depth-correct, and drawn lit:

* tilt at azimuth 270°: the yellow/orange piece's inside grows
  289 → 1,254 → 1,675 px across el −10° → −5° → 0°, then to ~3,000 px —
  a fast but continuous geometric reveal over ~5–10°, not a switch.
* inside luminance 50–120 against background 18; outside 90–140. The
  interior is shaded like a lit surface (the shader ignores orientation —
  flipping every face's winding redrew the picture pixel for pixel, measured
  earlier), so an inside view is indistinguishable from an outer surface.
  That is "I can see the outer edge from the inside", verbatim.
* both pieces show it (blue/green from its opposite azimuths and from
  above); outline shown/hidden changes nothing (only overlays wires);
  50% keeps the transparent path to the byte (1,324 faces, 508 rgba).

Nothing is mis-drawn: the depth buffer is right at ~99% of interior pixels
away from genuinely dark colours (probe precision 0.77–0.95 vs screenshots,
misses explained: silhouette antialiasing + drawn-but-near-black pixels).

## The page mesh's winding — a trap for the next probe

The drawn page mesh is NOT the pristine iccgamut shell: `recut_where_they_part`
duplicates rim corners and leaves T-junctions (346 boundary edges, 96
directed edges used twice on the "closed" 1,324-face page mesh), so
screen-space winding gives a different "outside" sign per camera. Classify
by volume parity, never by winding, on anything that went through the recut.

## Window reports (drift scene, verification scene) — measured so far

`window_repro.py`, real window, printer-2019 vs printer-2021 (scene A) and
printer-2019 vs sRGB + verification-chart-480 with a solid skin (scene B,
= the fourth screenshot's configuration), opacity 100%:

| state | 2.39.6 (fix) | baseline 367b066^ |
|---|---|---|
| A agree 0% | **3,191 of 5,532 faces drawn, 0 rgba** | 5,532 drawn, 1,442 rgba(…,0) |
| A differ 0% | 2,341 drawn (3,191+2,341=5,532 — partition exact) | 5,532 drawn, 1,861 rgba |
| A 100/100 | 4,462 faces (no recut), identical both trees | same |
| B agree 0% | 2,620 of 5,398, 0 rgba | 5,398 drawn, 1,624 rgba |
| B frame time (relayout turn) | median 2.8 ms | median 2.5 ms |

So: the geometry of the hole PREDATES the fix — before it the same faces
were drawn invisible (alpha 0), after it they are removed. What changed is
what is visible THROUGH the hole: the old transparent path never wrote the
depth buffer and painted a sorted wash; the opaque path shows the true
interior — lit back faces — plus whatever other traces lie inside.

`_solid_remainder` cannot fire off the ends: measured directly, opacity 0.55
keeps today's path, one corner at 0.99 or 0.01 keeps it, only exact 0/1
alphas at opacity exactly 1 remove anything, and never a straddling face.

Frame time: no regression measured in this harness (hardware GL; the fix
side is within noise of baseline and the fix REDUCES sorted faces). The lag
report is not reproduced here — likely software rendering or window size;
open.

## Window scenes, per-pixel — SETTLED

Parity classifier on the window's own harvested meshes; calibration on the
scene's own closed recut shell (B-a99): 15,797 and 54,696 covered pixels at
two cameras, 0 classified inside — exact.

* Scene A (2019 vs 2021, agree 0%): at the default camera **87% of the drawn
  shell's pixels (6,970 of 7,982) show the INTERIOR**; at a second tilt 90%;
  at a from-below tilt 0%. The standing remainder of a drift pair is thin
  scattered patches, and from most angles you look at their inner sides —
  lit like outer ones. "The inside looks shattered" is literally exact.
* Scene A (differ 0%): ~0% interior — the agreeing bulk stands and shows
  its exterior; that end of the control does not produce the effect.
* Scene B (2019 vs sRGB + chart, agree 0%): interior is only 2–9% at the
  probed cameras. The big "flat lid" is the standing remainder's TRUE
  EXTERIOR — the shape genuinely loses its top at agree 0% by design, with
  a hard cut edge along the sRGB intersection. The hide-one-trace probe
  attributes the lid to the printer shell (hiding the chart skin keeps it;
  hiding the shell leaves only grey skin and dots), and the streaky
  "shattered" texture appears only when the translucent chart skin
  (opacity 0.3, sorted transparent path) blends over that bright surface.

## The fix's own 16-view check — what it was and was not blind to

It was taken in the same class of configuration (page 14, two shapes,
agreement at 0%, outline shown and hidden). It asked one question: is any
pixel painted by a piece that lies BEHIND a nearer solid one (4,062 → 0).
That question is answered and stays answered. It never asked what should be
visible THROUGH the opening — the interior's appearance was outside its
frame, not wrongly measured.

## Verdict across all four reports

2.39.6 removed nothing that was visible before — the hole predates the fix
(same faces at alpha 0). Occlusion is now correct where it was wrong. What
the reports describe is the one thing the fix could not decide: an OPEN
shell's interior is drawn lit exactly like its exterior, so it reads as an
outer surface seen from inside ("outer edge from the inside") or as broken
skin ("shattered"). At agree 0% the picture is SUPPOSED to lose the
agreement; whether its interior should be culled, capped along the cut, or
shaded as an interior is a design decision, and per the project's standing
rule the default is to change nothing until Basti picks.

Candidate cures, each with a measured cost to check before choosing:
* back-face culling on the open remainder — hides interiors, but the same
  culling family shredded outlines at grazing angles when measured before
  (docs/THE-SEE-THROUGH-TRIANGLES.md), and plotly offers no native culling;
* a cap along the cut (a neutral "sliced" surface) — honest, reads like a
  cross-section, needs new geometry along the intersection curve;
* darkening back faces — impossible statically (a face changes side as the
  camera moves), so it means per-frame recolouring: a cost exactly where
  the 108.3 → 49.9 ms gain lives;
* or EXPLAIN it: one sentence in the agree-control tooltip saying that at
  0% the standing part is an open shell and from some angles you will see
  its hollow inside. Cheapest, changes no pixel, reaches window and pages
  through the same engine string.

## Performance

No regression measured: relayout-turn median in scene B, fix 2.8–3.0 ms vs
baseline 2.5–2.7 ms (hardware GL, within run-to-run noise), and the fix
strictly REDUCES the per-frame sorted-triangle count (on page 14 it halved
frame times, 108.3 → 49.9 ms). Basti's lag report did not reproduce in this
harness; if it persists on his machine it is likely software rendering or
window size, and wants measuring THERE rather than guessing here.
