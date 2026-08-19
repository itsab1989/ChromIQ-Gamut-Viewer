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

## Open (next pass)

* Which trace paints the "flat lid" in scene B — hide-one-trace probe is in
  window_repro.py (run on baseline; fix-tree re-run pending).
* Parity classification of the window meshes (inside-view pixel counts per
  camera, fix vs baseline) — meshes and matrices are harvested.
* Whether the fix's own 16-camera check (4,062 → 0) was taken in the same
  two-shape agree-0 configuration — to be answered from the fix's trail.
* The design question the numbers pose: an open shell's interior is lit like
  an exterior, so it does not READ as an interior. Candidate cures to
  measure, not pick: back-face culling on the open remainder / a cap along
  the cut / darkening back faces. Any cure must reach the window AND the
  saved pages and must not give back the 108.3 → 49.9 ms gain.
