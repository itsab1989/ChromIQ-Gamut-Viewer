# Two views in one saved page — the shells and the cut, with a switch

Asked for from the window:

> "could the exported web viewer files get a toggle to switch between the view
> of the shells and the sliced view … the other controls would then have to
> update accordingly so the user can manipulate each view in a way that makes
> sense for it."

This is what the build needs to know before it starts. It is written down
because the feasibility question has an answer already in the tree, and
re-deriving it is the expensive part.

## What already exists, measured rather than assumed

**A page can carry more than one figure.** `write_side_by_side_html`
(`python/ti3gamut.py:7232`) writes several scenes into one file, each in its
own division, and the two-room pages in `docs/pages/` are that writer's
output. Nothing about one-figure-per-page is baked in.

**The movement engine already asks each picture what kind it is.**
`isFlat(gd)` (`python/ti3gamut.py:3839`) answers from the drawn layout — a
scene has `scene`, a cut has `xaxis`/`yaxis` and no scene — and every control
in `cqSpin` already branches on it: turning, tipping and the camera belong to
a scene, and zoom and "back to the start" have a second body written in the
only terms a flat picture has. **So a page holding both would already drive
each correctly**; what is missing is the switch, not the understanding.

**The cut's data is small.** A cross-section is a set of rings, and
`slice_levels` already precomputes them for the live cut slider. A page
carrying both is the scene's mesh plus those rings — the viewer itself, which
dominates the file, is carried once either way.

## What has to be built

1. **A writer that puts both in one page**, one shown and one hidden, rather
   than choosing between them at save time.
2. **A switch in the strip** — `data-cq="view"` beside the others — that
   swaps which division is shown and tells `cqSpin` which ids are live.
3. **A strip that changes with it.** This is the half the request is really
   about. The rule is already stated by `isFlat`: the camera, "look from" and
   the turning belong to the shells; the lightness slider and its readout
   belong to the cut; zoom, "back to the start", the key and the appearance
   belong to both. A control that cannot act must not be offered — the window
   already holds that line for the split tick, and the reasoning is in
   `SPLIT_IS_THE_DESTINATIONS` and `COLOURING_IS_THE_FAMILIES`.
4. **The choice in the export dialog**, with a tooltip in the house voice:
   what it does, what it needs, and what it costs — a page carrying both is
   larger, and that is the reader's business.
5. **An audit that crosses the two views against every control**, because
   "which controls make sense here" is exactly where an inconsistency hides.
   `audit_offers.py` already crosses page kinds against the switches a page
   can honour and is the pattern to follow.

## What to watch

- **Both instances, always.** A page saved from the main window and one saved
  from a run go through different writers. Anything that reaches one must
  reach the other; that asymmetry has been reported here twice.
- **The strip must not change width when it changes contents.** A control that
  moves under the hand was reported once already and cost three attempts.
- **Nothing may be left unreachable.** `audit_the_controls_can_be_shut.py`
  exists because a panel once opened taller than the frame it sat in.
- **Size.** State the measured cost of carrying both in the tooltip rather
  than an estimate.
