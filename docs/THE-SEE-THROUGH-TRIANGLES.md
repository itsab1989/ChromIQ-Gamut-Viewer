# The see-through triangles

Dark, kite-shaped wedges on a shape that is smooth everywhere else. They
appear the moment a surface is made see-through, they change as the shape
turns, and they are gone the instant it is solid.

Reported from the window, three times, in these words:

> "at the edges of the shape there still seem to be hints of triangles
> instead of a smooth surface"
> "triangles here as well that change during movement"
> "as soon as transparency comes into play the triangles appear it seems"
> "when you increase the opacity step by step those triangles are not
> affected and only in the very last step they become totally solid like the
> rest"

This is the whole trail, so that whoever picks it up next starts from the
answer rather than from the suspects. **Nothing here is a guess; every line
is a measurement, and the ones that turned out to be wrong are kept with the
reason.**

## How it is measured

One shape (`printer-2019.icc` read through `iccgamut`), one camera, one crop
of the yellow-orange flank where the wedges are, drawn at 68% unless said
otherwise. The number is **roughness**: the mean absolute step in brightness
between neighbouring pixels. Higher is rougher.

Two reference points to hold everything against:

| | roughness |
|---|---|
| the same shape drawn **solid** | **0.808** |
| the same shape at 68% | 0.886 |

The gap between those two is the fault. Everything below is an attempt to
close it.

**Compare on ONE page with a switch, never two pages.** Two separately loaded
pages are framed to their own content by `fitToPane`, so their pixel counts
are not comparable — that mistake once read as a 7% hole that did not exist.
`window.cqOrder.farWall(true|false)` exists for this.

## What it is NOT — nine things, each measured

| suspect | result | |
|---|---|---|
| sliver triangles in our own hull | 0.848 | 26 needle-thin faces of 1,824 collapsed away, none left, no holes — one needle went, every kite stayed |
| deleting those faces instead | 2.600 | far worse, and it gave the game away: the wedges became real **holes** in the same places, so those faces cover ground |
| coincident corners | 0.886 | welding at a hundredth of a Lab unit merged one corner of 914 |
| the winding | 0.886 | all faces wound inward, consistently; reversing every one redrew the picture **pixel for pixel**, so the library lights both sides |
| flat facets | 0.965 | worse |
| the lighting curve | — | flooding the light cured a test ball (4.06 → 1.00) and not a gamut (9.38 → 9.27) |
| softened normals | 0.886–0.889 | 441 vertices turned toward the eye, four strengths, no difference |
| **no lighting at all** | **0.822** | ambient 1, diffuse 0, specular 0, set live on the page — **the wedges are still there**, so they are not shading of any kind |
| the vertex colours | 8.96 vs 9.39 | painted one flat lilac, the same wedges |

## What it is NOT — the two that took longest

**Not the blend ORDER.** Our engine sorts a see-through surface's triangles
farthest-first every frame, into 4,096 buckets, and two triangles in one
bucket come out either way round *on purpose*. Near the outline the far wall
is foreshortened, so many of its triangles crowd into few buckets — exactly
what an unstable order would look like. Replaced with a full comparison sort,
on one page: **0.886 → 0.886 → 0.886** switching back and forth. Not the
buckets.

**Not how coarse the shell is.** Eight times the geometry does not close the
gap:

| `iccgamut -d` | faces | at 68% | solid |
|---|---|---|---|
| default | 1,824 | 0.886 | 0.808 |
| 6 | 4,462 | 0.912 | 0.808 |
| 4 | 9,110 | 0.902 | 0.808 |
| 3 | 14,412 | 0.844 | 0.813 |

The solid column does not move at all, and the see-through one never comes
down to it.

## What DOES remove them, and why it cannot ship

Not drawing the far wall — the half of the shell facing away — removes every
wedge: **0.886 → 0.562**, put back to 0.886 to prove the picture answers to
the switch and not to the passing of time.

Three variants were built and all three fail:

1. **Drop every face that does not face you.** The wedges go; the **outline
   shreds** into shards, because right at the outline faces are almost
   exactly edge-on and flicker between facing you and not.
2. **Keep the nearly edge-on ones too.** The outline comes back and so do the
   wedges. There is no tolerance that does both:

   | slack (cosine) | faces kept | outline restored | flank |
   |---|---|---|---|
   | 0.10 | 696 | 93.0% — shreds | 1.014 |
   | 0.20 | 980 | 97.5% | 0.897 |
   | 0.35 | 1,468 | **100%** | 0.894 — kites back |

   By the time the outline is whole it keeps 1,468 of 1,824 faces — barely
   culling — and the flank is back to 0.894 against 0.891 for the shape drawn
   whole. **The kites ARE the far wall where it runs nearly edge-on, which is
   precisely the band the outline needs. The two requirements are the same
   faces.**
3. **Tell the two edge-on kinds apart by SIDE** — the outline is edge-on on
   the near side, the far wall is edge-on on the far side, and one dot
   product says which. Outline 97.1%, flank **0.955 against 0.912** with the
   wall drawn: worse, because the boundary of the culled region becomes its
   own seam.

An earlier attempt tore a band out of the shape and was blamed on the idea.
It was not: it turned each face outward by asking whether it pointed away
from the shape's **middle**, which is only true of a convex shape, and this
one is **7.4% dents** — `iccgamut` keeps them on purpose. Inside a dent that
test gives the opposite answer, so front faces were culled. **No assumption
is needed:** the shell is a closed, consistently wound manifold — measured on
two profiles, all 5,472 directed edges walked exactly once in each direction,
none repeated, *before and after* the weld the page does — and its signed
volume names the convention outright (−818,514 for a shape of volume
818,514, so the faces are wound inward).

## The evidence that says whose fault it is

| opacity | 0.15 | 0.30 | 0.45 | 0.60 | 0.68 | 0.80 | 0.92 | **1.00** |
|---|---|---|---|---|---|---|---|---|
| two-layer step | .128 | .210 | .247 | .240 | .218 | .160 | .074 | .000 |
| flank | .233 | .445 | .630 | .800 | .886 | 1.013 | **1.137** | **.808** |

The obvious explanation — that a wedge is the boundary between looking
through **two** thicknesses of shell and **one** — predicts a peak near half
opacity, where that step is largest. **It is wrong.** The wedges climb all
the way to 0.92, where the step has nearly gone, and then vanish in a single
jump at solid.

What fits every number: the library draws a see-through surface down a
**different path** from a solid one, and the artefact belongs to that path.
Its visibility simply tracks how bright the shape is, which is why it looks
worst just below solid. That is also why an exact sort changes nothing —
sorting **triangles** cannot fix blending that interleaves at the **pixel**
level wherever triangles overlap in depth.

## THE ANSWER, and it was the blend after all

**Draw the whole away-facing wall first, then the whole toward-facing wall,
each half still sorted farthest-first.** A pure reordering: nothing is
culled, nothing is dropped.

Why it works where a depth sort cannot. A sort of triangle *middles* is right
about which TRIANGLE is farther and still wrong at pixels where the rim's
foreshortened far-wall facets and the near wall overlap in depth — those
pixels are the kites. Splitting the order by which way a face points settles
all of them at once: at any pixel of a closed shell the near wall is nearer
than the far wall, so far-wall-first is correct **per pixel**, which no
ordering of triangles can promise.

Measured on one page with the switch thrown, and checked independently
afterwards:

| state | lit pixels | flank |
|---|---|---|
| wall order off | 60,918 | 0.912 |
| **wall order ON** | **60,918** | **0.704** |
| off again | 60,918 | 0.912 |
| ON again | 60,918 | 0.704 |
| the two walls inverted (mutation) | 60,914 | 0.759 |

**The lit pixels are identical** — that is the line every culling variant
failed. Nothing is removed, so the outline cannot shred.

It costs one dot product per triangle: a forced pass went 5.82 → 6.82 ms at
5,966 faces, which the engine's own throttle absorbs.

AND A SECOND FAULT WAS FOUND ON THE WAY: after any camera relayout,
`_fullLayout.scene.*.range` turns to junk (`[-88..92, …]` becomes
`[-1..6, …]`), so `lineOfSight` bent from (0.577, 0.577, 0.577) to
(0.468, 0.286, 0.836) and **every frame after a drag was sorted for the wrong
direction**. The scene's `dataScale` is bit-identical across relayouts and is
now what is read, with the ranges kept only as a fallback.

Known residual: rays passing through two shells *disjointly* — one wholly
behind the other — get one swapped pair. No camera in a sixteen-angle sweep
showed it above noise; it is the place to look if a two-shape angle ever
regresses.

## Where this came from

The direction below was written before the fix existed and is kept because it
was right: the answer was in the blend, not in which faces exist.

## What was tried before



Three honest answers, and only the first two are ours:

* draw it solid;
* draw one layer instead of two — culling, measured above, and it cannot be
  separated from the outline by any rule tried so far;
* compose transparency without depending on draw order (order-independent
  transparency — depth peeling, or weighted blended OIT). Plotly does not
  expose this, so it would mean reaching past it to the WebGL context, or
  drawing the shell ourselves.

**Anything that changes only WHICH FACES EXIST has been exhausted.** The next
idea has to change **how the two are blended**.

Whatever is tried must reach every instance of the viewer **and the web
export** — the saved page is written by the same `build_figure`, so a fix in
the engine reaches both, and one that is not in the engine reaches neither.

## Where the code is

* `python/ti3gamut.py` — `_ORDER_JS` / `window.cqOrder`: the per-frame depth
  sort, the pooling of several see-through surfaces into one, and the
  "quick door" that hands a triangle list straight to the drawn object.
  `_lighting()` carries the same trail in its docstring.
* `python/references.py` — `icc_gamut`, and `SURFACE_DETAIL`, which is what
  the shape's own facets come from.
