# What to do when the cron resumes

Basti's instruction, 2026-08-20 ~01:54, during the 50-minute pause:

> "what i write down in the time before the 50 minutes pass is just for you to
> set to the list of things that should be done when the chron job gets active
> again"

So: anything he says between now and 02:42 is **collected here, not acted on**.
Read this file first when the pause ends, before anything else.

## Collected during the pause

### 01:56 — the "show rings inside" slider is not live

> "show rings inside slider only updates the viewer when i let go from dragging
> it - should be live"

Reported from his own window running at `~/develop/ChromIQ-Gamut-Viewer/fork`.

Where to look, so this is not re-derived: a slider that only acts on release is
one connected to `sliderReleased` / `editingFinished` rather than to
`valueChanged`, or one whose handler is guarded to skip while
`slider.isSliderDown()`. Find the rings control in `python/gamut_app.py` and
compare how the sliders that ARE live are wired — that comparison is the whole
diagnosis.

Two traps already on record for this exact area:

* **`setValue` fires only half a slider** — see the memory of that name; a fix
  that works when dragged can still do nothing when set programmatically, so
  test both.
* **Every fix must reach the exported pages as well as the window**, and the
  live page has its own controls script. A rings control that goes live in the
  window and not in a saved page is the asymmetry this project keeps repeating.

### 01:58 — the "details" slider has the same fault

> "same what i just said is true for the details slider"

So it is at least two controls, not one. **Treat it as a class, not as two
bugs**: find every slider in the window, ask each one whether it acts while
being dragged, and fix the wiring in one place. Two reported almost certainly
means others nobody has dragged yet — and a fix applied twice by hand is how
the third gets missed.

The check that belongs with this: drive each slider programmatically, hold it
down, move it, and assert the picture changed BEFORE the release. That is a
rule whose answer is known in advance for every slider in the column, and it
crosses the two states (dragging, released) rather than testing one.

### 02:00 — hovering a shape blocks zooming

> "in the app - when hovering the mouse over something that triggers showing a
> label (srgb comparison in my case just now) i cannot zoom"

So: pointer over a trace that pops its name → the wheel does nothing. Move off
it and zoom works again.

This is the SAME MECHANISM as the release jump already solved on the pages, and
that history is the shortcut here: pointing at a shape makes the drawing
library work out what is under the pointer and draw its label, and **that
redraw was measured to commit a camera the picture had not caught up with**
(69.48° in one frame in chromium, 37.54° in webkit; 0.00° over the walls).
Cured there by settling the camera when the button comes up — `settle()` in
`letGo` — and explicitly NOT by turning hover off, because reading a shape's
name is behaviour the pages advertise. Same rule applies here: do not fix this
by disabling the label.

What to establish first, in this order:

1. Is the wheel event being swallowed, or is the zoom happening and then being
   undone by the hover redraw? Those need opposite fixes. Log the camera across
   a wheel tick with the pointer on a shape and off it — the pair is the
   measurement, one alone proves nothing.
2. Does the saved PAGE do it too, or only the window? If only the window, the
   difference is QtWebEngine's wheel handling, not the figure.
3. Whether it depends on the trace: he saw it on the sRGB comparison, which is
   an outline. Cross it against a solid shape and the chart dots.

### 02:04 — the out-of-reach boundary zig-zags instead of cutting cleanly

> "what is out of reach here should probably be a clean cut along the shell of
> srgb. instead it is zig zagging"

Screenshot: proofer-2022-03 solid with "Show what it cannot print" on (red =
out of reach, grey = within), sRGB as outline only, **"Where they agree" and
"Where they differ" both at "all of it"**, rings 13, detail 29. The red/grey
border runs in stair-steps that follow triangle edges rather than following
sRGB's surface.

**THE LIKELY CAUSE, and it is citable rather than a guess.** The out-of-reach
marking is a per-VERTEX mask, so the border can only ever run along mesh edges
— which is exactly a zig-zag at chart resolution. The machinery that would make
it a clean cut already exists and simply is not being invoked here:
`recut_where_they_part` → `split_at_crossing` (ti3gamut.py:1808) inserts new
vertices exactly along the crossing, and `_mesh_lost` already carries the
`lost` mask through it. But ti3gamut.py:8785 only calls it when

    len(gamuts) > 1 and (split or agree < 1.0 or differ < 1.0)

and in his screenshot BOTH fades are at "all of it", so none of those is true
and no re-cut happens. **The fade gets a clean edge; the out-of-reach colouring
does not, for no reason other than which branch runs.** First thing to try:
extend that condition to the marking, and measure the cost — the re-cut is a
containment test per pair per redraw, which is why it is behind a condition at
all.

⚠ **DO NOT confuse this with the answer already on record.** A Fable agent
proved that the ragged magenta boundary on the *two-shape comparison pages* is
the measurement and not the drawing — two 91.9%-coincident shells genuinely
interleave at chart resolution, mispainting confined to 0.15% of area, all
within 0.049 Lab. That answer is about shells that nearly coincide. **This is a
different case**: a proofer against sRGB are not near-coincident, and the
stair-stepping follows mesh edges. Verify which of the two this is before
touching anything — if the border tracks triangle edges it is the mesh; if it
tracks the true crossing it is the measurement and must be left alone.

### 02:06 — "Show a perfectly neutral line" draws nothing from a profile

> "i could understand why this can't show the measured grey from just a profile
> - but is a neutral line impossible as well here?"

Screenshot: proofer-2022-03 (an ICC profile) against sRGB. **Both** "Show the
greys as they came out" AND "Show a perfectly neutral line" are ticked, and
neither draws anything.

**He is right, and the answer is almost certainly no — a neutral line is not
impossible.** The two ticks need different things and are probably sharing one
guard:

* *the greys as they came out* genuinely needs MEASUREMENTS — the grey patches
  as the printer actually produced them. A profile has no such patches, so
  nothing to draw is correct and honest.
* *a perfectly neutral line* needs NOTHING BUT THE AXIS. It is a* = b* = 0 from
  black to white — definitional, not measured. And if it is meant as the
  profile's own neutral axis (R=G=B fed through its table), that is still
  computable from a profile alone.

So this looks like the fault this project has fixed twice already in this same
window: **a control offered where it cannot act**, or here the reverse — a
control that CAN act being suppressed by the neighbouring one's prerequisite.
Find the guard both ticks pass through and check whether the neutral line is
behind the has-measurements condition by accident.

Failure directions to keep straight: if the line is drawn but invisible (behind
the solid, or grey-on-grey at this camera) that is a different fault with a
different fix, so establish WHICH before changing anything — draw it with the
shape hidden first.

Whatever the outcome, the tick must not sit there doing nothing: either it
draws, or it is disabled with a tooltip saying what it needs — the rule this
window already applies to the split tick and the colourings.

### His log — use it rather than guessing his steps

> "btw. you can always look at my log to reproduce what i have done while
> writing this"

Standing permission, worth using: the window keeps a log of what was opened and
changed. Find where it is written (check `python/gamut_app.py` for the log
widget and any file it mirrors to) and READ IT before trying to reproduce any
of the reports above — it gives his exact sequence instead of a reconstruction.
This is the "reproduce with the user's real layout" rule, handed over for free.

### 02:08 — an ⓘ dropped onto its own line, AND the audit that should catch it said Clean

> "clicked two rooms side by side option and a tooltip icon appears below both
> rooms point the same way - should probably be at its right side"

Screenshot: with "Two rooms, side by side" ticked, its sub-option **"Both rooms
point the same way"** appears, and its ⓘ has wrapped onto a line of its own
underneath the label instead of sitting at its right.

**The fix is the small half. The big half is that `audit_panel` question 3 is
exactly this rule — "DOES EVERY ⓘ SIT BESIDE SOMETHING? An icon on a row of its
own explains nothing" — and it reported `Clean: 24 panel states` on 2026-08-20,
hours before this screenshot.** So the audit has a blind spot and the blind
spot matters more than the icon.

The likely reason, to be confirmed rather than assumed: **"Both rooms point the
same way" only exists once "Two rooms, side by side" is ticked.** The audit
opens the six folded SECTIONS before measuring — it learned that lesson — but a
sub-option revealed by a TICKBOX is a different kind of hidden, and if the
audit never ticks that box the control is never built, never measured, and
counted as clean by absence. That is the same failure as measuring a hidden
widget: no size, no complaint.

So the work is:

1. Confirm the audit never reaches that state (drive it, print the controls it
   actually measured, look for this label).
2. Make it reach every control that a tick or a choice can reveal — not just
   every folded section. Cross the revealing controls rather than testing the
   default state.
3. **Mutation-test it**: with the fix in place, put the wrapped ⓘ back on
   purpose and prove the audit now fails. A check that could not see this fault
   cannot be trusted to have seen the others in that state either.
4. Then fix the row itself. The label is long and the column is 369 px, so this
   is a wrap, and the cure is the same as elsewhere in this window: keep the ⓘ
   with what it explains, shorten the label, or let the row give the icon its
   space — and the ⓘ must travel with its own control, which is why the
   grouping is by index in `_stack`.

Note it also proves `audit_panel`'s six questions are only as good as the
states it visits — worth re-reading its "IT OPENS EVERY FOLDED SECTION FIRST"
comment, which is the same lesson learned once already and not carried far
enough.

### 02:10 — two rooms loses the shapes' appearance, and going back restores it

> "also when enabling the two rooms the shapes on screen don't keep their
> visuals from before, turning it off again resets the view to how it was
> before"

That second clause is the diagnosis, not just a detail: **the settings are not
lost, they are not being HANDED to the two-rooms picture.** If they were lost,
turning it off would not bring them back. So one builder is given the per-shape
appearance and the other is not.

Where to look: `ti3gamut` carries per-shape settings as `per_shape` — `paint`,
`opacity`, `depth`, `rings`, `mesh_paint` are all read from it at the call site
around ti3gamut.py:8790, each falling back to the window-wide value. The
side-by-side/two-rooms writer is a different path (`_write_two_rooms` and the
window's equivalent). Check whether that path is passed `per_shape`, `styles`
and the appearance at all, or whether it builds each room from defaults.

Establish first, because it changes the fix: is it the PER-SHAPE settings that
are dropped, or the window-wide ones, or the camera? His words say "visuals",
and the screenshot before it had rings 13, detail 29, "show what it cannot
print" on, true colours. Name which of those survive the switch and which do
not — the ones that survive tell you which argument is being passed and which
is missing.

The check that belongs with it, and it is a crossing rather than a single case:
for each appearance control, set it away from its default, turn two rooms ON,
and assert the picture still reflects it — then OFF, and assert it is still
there. Answers known in advance for every control. This is the same family as
the two-view audit in `scripts/audit_two_views.py`, which crosses page kinds
against the controls they honour, and that is the pattern to copy.

⚠ And whatever is fixed here must be checked in the EXPORTED two-room pages
too, not only the window — `docs/pages/09-a-room-each.html` and
`12-a-cut-each.html` are that writer's output, and "every fix reaches all
viewer instances AND the web export" is the rule this project has broken three
times.

### 02:12 — triangles pop in and out on the translucent shape while turning

> "when moving around the shape on the right shows triangles appearing and
> disappearing instead of smooth transitions"

Two rooms, the right room is sRGB drawn see-through (depth 35%). While the
camera moves, individual triangles blink in and out rather than the surface
changing smoothly.

**This is THE KNOWN FAULT, not a new one — do not re-derive it.** It is written
up in `docs/THE-SEE-THROUGH-TRIANGLES.md`, and the memory
`project_see_through_triangles` records that nine causes have been ruled out
and culling exhausted. The mechanism: a mesh with any vertex below full
strength goes on the drawing library's TRANSPARENT path, which never writes the
depth buffer, so what covers what is decided by a per-frame sort of triangle
middles. A sort of middles cannot be right for every pixel, and as the camera
turns the order flips — which is exactly a triangle blinking.

**What this report adds, and it is worth stating plainly: the 2.39.6 fix only
cured the ENDS of the fade.** `_solid_remainder` puts a mesh back on the opaque
path only when every vertex is at exactly 0 or 1 and the shape's own strength
is 1. A shape at 35% depth is none of those, so it is still sorted, and this is
the same fault surviving in the case the fix deliberately did not touch. That
is a fair thing to say to Basti rather than presenting it as unrelated.

Do NOT spend a cycle re-testing the ruled-out causes. What would actually move
this forward, in order of cost:

1. Establish whether it is worse in TWO ROOMS than in one — two scenes, two
   sorts, and he saw it in the two-room view. If the second room makes it
   worse, that is new information and cheap to get.
2. Whether the number of rings/detail steps changes it (he is at rings 13,
   detail 29 — more geometry, more sorting).
3. Only then the hard question, which is a rendering-library limitation and
   needs a stronger model than has been thrown at it so far — the brief for
   that is already written in the fork's `docs/THE-SEE-THROUGH-TRIANGLES.md`.

### 02:14 — a drag that crosses the seam hands the gesture to the other room

> "when two rooms are visible and i drag a shape around both move the same way.
> but if i am crossing their seperator while dragging the one where i started
> from stops moving and only the other one still moves"

So the linking works — until the pointer crosses the divider mid-gesture, at
which point the room he STARTED in freezes and the other one keeps turning.

**Almost certainly not a linking bug at all, but a lost pointer.** The drag is
being handled by whichever plot the pointer is over: when it leaves the first
room's element, that element stops receiving move events (and very likely gets
a leave/cancel), so its drag ends mid-gesture; the second room, now under the
pointer, begins one of its own. The reason only ONE then moves is that the room
that is driving relays its camera to the other, and after the hand-over the
roles have swapped — so the picture is consistent with the mechanism, which is
a good sign the diagnosis is right.

The standard cure is to make the gesture belong to the element it STARTED on
for its whole life: `setPointerCapture` on pointerdown (released on pointerup),
or handling the drag on the shared container rather than per-plot. Either way
the rule to implement is "a gesture belongs to where it began", which is also
what a person expects — the shape should not care where the cursor wandered.

Establish first: does the first room stop because it received a leave/cancel,
or because it stopped getting moves? Log the events across the seam. Those look
identical on screen and need different handling.

⚠ Both instances again: this must be fixed in the window AND in the exported
two-room pages (`docs/pages/09-a-room-each.html`, `12-a-cut-each.html`), which
carry their own controls script. And it is worth checking whether the same
hand-over happens when the pointer leaves the picture ENTIRELY — off the top of
the window, onto the control column — because that is the same lost pointer and
Basti has not tried it yet.

### 02:16 — "some shapes and combinations looked better in past versions"

> "i feel like some of the shapes and combinations did look better before in
> the past versions. although i might be very wrong here because i did not yet
> operate the app myself before and only watched the examples you repeated
> again and again for your tests. so it might as well be a coincidence that i
> just found those things just now"

His caveat is fair and so is the suspicion. **Do not argue this from memory in
either direction — it is measurable, and measuring it is cheap.** Two
explanations fit the evidence equally well right now:

* a real visual regression somewhere in the 2.3x series, or
* observer effect: this is the first time he has driven the app himself, at his
  own settings (rings 13, detail 29, two rooms, out-of-reach on), and the test
  examples never used those combinations. Nine reports in one evening from a
  first hands-on session is exactly what finding-by-using looks like.

**The measurement:** render ONE scene, at HIS settings, from several tags —
say the current head, v2.39.0, v2.38.x and one from before the 2.3x work —
and compare the images. `docs/probes/inside-view/window_repro.py` (committed at
`94c37b4`) already builds his configuration in a real window and photographs
it, so it is the instrument; a git worktree per tag is the rest. Keep the
settings identical and the camera fixed — the whole point is that only the
version varies.

Cases whose answer is known in advance: if nothing changed visually, the images
are pixel-identical or near it, and the answer is "his eye is new, not the
app". If something did change, the tag where it changes names the commit, and
that is the whole diagnosis.

⚠ Watch the trap this project has hit repeatedly: MEASURE THE RIGHT PAIR. The
settings must be his, not the defaults — most of these reports only appear at
his combination, and a sweep at default settings would come back clean and
prove nothing.

Also worth measuring before shipping: a live redraw on every drag step is the
reason some controls were deliberately made release-only. If the rings redraw
is expensive, the answer may be live-but-throttled rather than live-on-every-
step — measure the redraw cost first, then choose.

## ⚠ THE TABLE BELOW WAS WRONG, AND IT COST THE TWO FADES MONTHS

**`Plotly.restyle` DOES replace a mesh's triangle list.** Both fades are live
as of `b3a545d`, by exactly the route the table said was impossible. The
verdicts in it were taken by reading `t.i.length` off `gd.data`, where a page
stores its arrays packed binary — `undefined`, so "nothing changed" is the
only answer such a reading can give. Fourth false verdict from that one
mistake. **Read `_fullData`, or measure pixels.**

Kept because the `Plotly.react` row is still true and still the wrong road:

| way | does it replace the triangles? | cost |
|---|---|---|
| ~~`Plotly.restyle` with plain arrays~~ | **YES** — the reading was wrong | a few kB |
| ~~assign `el.data[i].i` then `Plotly.redraw`~~ | untested since; irrelevant now | — |
| `Plotly.react` with the whole data array | yes, 978 → 583, camera untouched | **2,405 ms**, 1,151 kB of JSON |
| rebuild the page (what it did) | yes | ~1 s of black |

**How the fades are live now, and the shape of it reuses for anything else.**
`ti3gamut.surfaces_for_restyle(figure)` takes what `build_figure` would have
drawn and hands the window colours *and* triangles per mesh; `_push_fade`
restyles them into the scene already up. Nothing is reimplemented, so the live
picture and a saved page cannot drift. Building the figure is **16–19 ms** —
it was never the figure that made a redraw slow, it was writing six megabytes
of page and loading it.

Letting go still rebuilds at either **end** of a slider and only there, for
the caption ("… is not drawn: it agrees with the others everywhere"), which
Python writes and a push cannot produce. The rule is exact rather than a
guess: a shape's corners are lit at `agree` where it shares them and at
`differ` where it stands out, so it can only go dark when one of those is
exactly nothing.

### ✅ ITEM 1 IS FINISHED — and here is what pushing in place actually costs

All seven sliders are live. Three routes, and which one a control takes is
decided by what it moves and how much that costs:

| control | what it sends | cost | when it fires |
|---|---|---|---|
| rings, solidity, depth | one field | ~0 | every step |
| both fades | colours + triangles (`surfaces_for_restyle`) | 16–19 ms | every step |
| **the cross-section** | 3 traces + the frame (`traces_for_restyle` + `frame_for_relayout`) | **7 ms** | every step |
| **detail** | every trace, points and all (`traces_for_restyle`) | **160–522 ms** | after a **150 ms pause** |

**The transfer was never the cost.** QtWebEngine takes 1.9 MB through
`runJavaScript` in 25 ms and `Plotly.restyle` takes 6–26 ms of it. What costs
is `build_figure`, and it runs on the GUI thread — which is the whole reason
detail waits for a pause and nothing else does.

**Three things had to be measured because reasoning got them wrong:**

* **the frame goes before the outlines.** The other way round, one cut height
  in five was ten thousand pixels out — gridline spacing is settled from
  whatever is on the axis when it is asked.
* **send the two axis RANGES, not the whole axis.** Whole, it was 54,000 to
  162,000 pixels out: an axis carries `autorange` and an equal-scale tie to
  its neighbour, and handing those back fights the range beside them. Only
  the range differs between two heights anyway.
* **detail must be pushed by POSITION**, after checking the whole ordered
  list. Nine traces, five repeated names — `'sRGB (outline)'` three times.

**⚠ One difference survives and it is not the picture.** At L\* 80 the numbers
up the side reach 100, one character wider than at 50, so the left margin is
wider — and a margin is measured when a page is DRAWN and is not measured
again the same way in place. The drawn area starts at x=271 built and x=270.5
pushed. Half a pixel, and every gridline, glyph and outline lights up: 11,634
pixels. `Plots.resize` does not fix it; clearing the margins makes it seven
times worse. If it is ever worth fixing, pinning `margin.l` on the flat figure
is the direction — that would also stop the picture jogging sideways as the
reader drags through the height where the label width changes.

### THE OLD DETAIL FEASIBILITY NOTE — kept for the numbers

Measured on his own configuration (a paper against sRGB drawn as a cage,
rings 13), pushing each detail into the window's real picture:

| detail | build the figure | payload | transfer + restyle, in the window |
|---|---|---|---|
| 20 | 160 ms | 515 kB | **14 ms** |
| 29 | 297 ms | 1,021 kB | **16 ms** |
| 40 | 522 ms | 1,873 kB | **25 ms** |

**The transfer is not the problem and never was** — QtWebEngine takes 1.9 MB
through `runJavaScript` in 25 ms, and `Plotly.restyle` itself is 6–26 ms. Nor
is rebuilding the comparison (`reference_gamut("sRGB", steps=N)` is 3.5 ms at
12, 55 ms at 40). **The cost is `build_figure`, 160–522 ms, and it runs on the
GUI thread.** Firing that on every `valueChanged` would make the handle itself
sticky — worse than what it replaces.

So the design this wants is a **debounced** push: restart a ~150 ms timer on
each step and push when the handle pauses, plus one final push on release.
That gives a picture that updates in place — no second of black, no camera
jump — at 2–5× faster than the rebuild it replaces. Deliberately NOT built at
the end of a long cycle: a 300 ms blocking build wired in without time to
drive it properly on screen is exactly the sort of half-verified change this
project has been bitten by.

Three things to know before starting:

* **the trace list is stable across detail** — 9 traces, same names, at 12,
  20, 29 and 40 — so nothing has to be added or taken away, which a restyle
  could not do. The push must still REFUSE and fall back if it ever differs.
* **the names are NOT unique**: `'sRGB (outline)'` appears three times, so
  detail cannot be pushed by name the way the fade and the rings are. Check
  the page's whole ORDERED list of (name, type) first, then push by index —
  position matching is only dangerous when nobody checked.
* **the vertices move**, so `x/y/z` must travel; `surfaces_for_restyle`
  carries only colours and triangles. And the PAPER's own mesh changes too
  (42 kB of it), because the re-cut against a different-resolution sRGB
  changes the paper's triangles — pushing only the comparison's traces would
  leave the paper wrong.

✅ **`split=True` on the window's own view is load-bearing — and now named.**
Measured on a real paper against sRGB, drawn solid: **without the mask, 209
corners at full strength and 445 once faded; with it, 445 at every fade.** So
a window drawing without it would hand 445 colours to a 209-corner mesh on the
first nudge of a fade slider, and paint it wrongly with nothing to say so.
Two rules guard it (`288cdf0`): one in `build_figure`, one pinning the window
ASKING for it — which the first cannot see, and which was gated on `controls`
until this week. Mutation-proved.

### AND ONE REAL BUG CAME OUT OF MEASURING THIS (fixed, `35ec26e`)

Letting go of Detail, with a profile/measurement/picture as the comparison,
opened a **file chooser** — twice — asking for the file already on screen.
Cancel put the box back to "Nothing" and took the shape away. The slider was
wired to `_on_compare_changed` (the handler for CHOOSING) instead of
`_rebuild_reference` (the one for a setting that changed, which says so in its
own docstring). The rule that guards it is about the class, so a future
control cannot repeat it through a different widget.

**THE DESIGN THAT SHOULD WORK, not yet built.** Keep the GEOMETRY CONSTANT
through a drag, so only colours change and only colours have to be pushed:

1. draw with the shapes ALREADY re-cut whenever two or more are open — the
   re-cut costs 19 ms at 900 patches, 29 ms at 1,600, measured, once per draw
   and not per step;
2. then "where they agree" and "where they differ" only change a per-vertex
   alpha, which `restyle` of `vertexcolor` handles — a few kB, not a megabyte;
3. let the release rebuild apply `_solid_remainder`, which drops the invisible
   faces for the depth-correct picture. That is a geometry change and belongs
   where a rebuild already happens.

⚠ Check what forcing the re-cut does to the OUT-OF-REACH boundary first — it
is the same machinery item 4 needs, so the two may be one change. And check
the triangle count at full strength: the re-cut takes 978 faces to 1,328, and
"the picture is identical either way" is a claim about appearance, not counts.

## SWEPT AND FOUND SOUND overnight — do not re-derive these

Each was drawn with deliberately awkward inputs and LOOKED at:

| subsystem | what was tried | verdict |
|---|---|---|
| degenerate measurements | 1, 2, 3 collinear points, all-identical, all at L\*0, a NaN row | refused with plain-language errors; NaN dropped |
| charts | 1 patch inside/outside, every patch outside, the paper's own patches, a NaN, an empty chart | correct; **the paper's own 1,168 patches judge 1,168 inside / 0 outside** |
| cuts outside the shape | L\* 0, 100, and beyond both ends | already says "does not reach this lightness" |
| drawing spaces | lab, luv, xyz | all fit, sensible proportions and ticks |
| ink amounts | white point crossed | the chooser acts on the NUMBERS, not the picture — see the dead end below |
| drift cloud | no drift, one patch moved, everything moved hugely | correct; the threshold slider is withheld when it could only empty the picture |
| chart drawing | patches, skin, out-of-reach hidden | correct |
| two-view page | 3 sizes × 2 engines × both views | 12 states clean |

## RELEASED SO FAR: v2.40.0, v2.40.1, v2.40.2 (2026-08-20)

v2.40.0 carried the nine daytime fixes AND a regression (two rooms could not
be turned). v2.40.1 fixed that plus four found overnight. v2.40.2 fixes the
two-view cut opening at the wrong height.

**THE FIXTURE LESSON, which cost the most time tonight and will again.** An
invented shape hid a real fault from a check THREE separate times:

- `build_gamut` handed Lab without `input_space="lab"` builds nonsense
  silently — rings returned nothing, `slice_levels` returned None;
- a made-up ball's lightness range was too narrow to tell "saved at L* 50"
  from "the bottom of the range", so a mutation that genuinely broke the
  saved height slipped past;
- a wrong-space shape behaved differently under the same drag, so two
  instruments disagreed about one tree for an hour.

**Use `demo/Glossy-paper.ti3` and `demo/Matte-paper.ti3`.** Real papers have
awkward proportions, dents and a full lightness range. `audit_two_views` and
`audit_two_rooms_drag` now draw them.

**AND READ ARRAYS FROM `_fullData`, NEVER FROM `data`.** A page packs any
sizeable array binary: `t.i.length` and `t.x.length` are both `undefined`, and
every reading taken from them is a constant. This caused three false
"nothing changed" verdicts, one of which stood for hours.

## THE OVERNIGHT RUN, 2026-08-20 — five fixes, all from LOOKING at pictures

Basti asked for a long push: break it, question things, no assumptions, tests
for every fix. The method that produced all of it: **render a page in
chromium, open the PNG, and look.** Trace data and camera readings had been
lying to me for hours; the first picture I opened settled three questions.

| what | how it was found |
|---|---|
| **two rooms could not be turned at all** — a regression I shipped in 2.40.0 | pixels: capture on → 759 changed, capture off → 79,034 |
| the linking was never exact (1.09–4.15 apart) | the same instrument, once it was trustworthy |
| a flat gamut spilled out of its picture | drew a midtones-only gamut and looked |
| a short axis wrote its numbers on top of each other | same, on two different awkward shapes |
| an emptied picture looked broken | two identical shapes, agreement hidden |

⚠ **`getCamera()` IS WRITTEN BY THE LINKING SCRIPT.** The check that was meant
to guard the two-room drag read it, so it saw its own relay's push and called
a dead picture alive. Pixels answer "did it turn"; cameras answer only "do the
two agree".

⚠ **`build_gamut` reads Lab as XYZ unless told** — see the memory of that
name. Four false faults in a day, and two of my own tests passing vacuously on
empty output.

⚠ **Tick labels are drawn INSIDE the WebGL canvas**, so no DOM selector can
measure them. A first attempt to check label overlap found zero labels on
every axis and would have reported the fault cured.

## WHERE THE TEN STAND, end of 2026-08-20

| # | item | state |
|---|---|---|
| 1 | sliders not live | **DONE — all seven follow the handle**, pixel-proved and mutation-proved (`b3a545d`, `33e9a6e`, `47c1a25`, shipped in v2.41.0 and v2.42.0). `audit_sliders_are_live` reports Clean |
| 2 | the ⓘ on its own line | **DONE.** Row FIXED (`2303216`); and a rule that catches a stranded icon at last (`88550f8`), mutation-proved — by asking the LAYOUT, after four attempts that measured pixels |
| 3 | two rooms | **DONE.** Appearance FIXED (`2acad0b`); seam drag FIXED and now genuinely measured — all four journeys in step, 0.0000 apart, with a mutation that bites (`68d230e`) |
| 4 | out-of-reach zig-zag | FIXED (`62529b5`), mutation-proved |
| 5 | neutral line from a profile | FIXED (`f0b12cb`) |
| 6 | hover blocks zoom | FIXED (`4cb7cac`), pages rebuilt |
| 7 | "looked better before" | ANSWERED: v2.39.6, v2.39.0 and v2.36.0 draw **identically, trace for trace**, at his settings. The instrument is mutation-proved (master draws 8 traces where 2.39.6 draws 7) |
| 8 | the cap | STILL his decision — but it can now be taken **by looking**: his lid is drawn, in `docs/probes/inside-view/the-lid/` (`97ab334`). It works and it looks right; 28% of its corners fail a strict containment test, so it is a prototype and the real fix is still one shared cut curve. PARKED — but the fourth cure from `NOTES.md`, the one that changes no pixel, is SHIPPED (`f277bde`, v2.43.0): the control now says in plain words that what stands at the bottom is an open shell, why its far wall looks like an outside, and the two ways round it. The cap itself is untouched. The opening branches at **72 corners**, so it is mesh repair — but HIS idea (the other shell is the lid) measures far better: 0 triangles dropped between them, boundaries a median 2.4 Lab apart. The real fix is one shared cut curve |
| 9 | two-view export | **DONE.** Writer, switch, per-view controls, the cut's slider, AND the dialog's tick + ⓘ were all built — what was missing was that **nothing drove the tick**. Driven from the dialog to the file now, both directions, mutation-proved (`840a840`) |
| 10 | what the checks turn up | `build_gamut` reads Lab as XYZ unless told — see the memory of that name |

## Already queued before the pause

1. **The cap decision** — judge first, build only if he agrees. An unrun
   feasibility probe is ready at
   `/private/tmp/.../scratchpad/can_the_cut_be_capped.py`: how many rims the
   opening has, whether each is closed, how far each strays from its own
   best-fit plane. Alternatives and their measured costs are in
   `docs/probes/inside-view/NOTES.md` (commits `fdc8a57`, `94c37b4`).
2. **The two-view export** — the writer and switch work; the export dialog's
   choice with its tooltip and the cut view's own lightness slider are not
   built. See `docs/DESIGN-two-views-in-one-page.md`.
3. **The lag on the chart scene** — reported from his window, **not
   reproduced** here (2.8 ms against 2.5 ms baseline). Needs his machine.

## Do not rebuild — verified done 2026-08-20

The × per row, the two named button sections, the author credit, the column
width (369 px, stable across seven states), the cut-sentence check
(`audit_panel` questions 5 and 6), and exports in other engines
(`audit_other_engines`, three engines, mutation-proved). A stale task list
once had me overwrite an existing, better check — **check the tree before
building anything this list calls missing.**

## ⚠ A MUTATION GOES STALE AS QUIETLY AS ANYTHING ELSE — 2 of 4 were dead

Asked of every check offering `--prove`, and the answer was worse than
expected:

| check | its mutation | state |
|---|---|---|
| `audit_two_rooms_drag` | disabled `setPointerCapture` | **dead since v2.40.1**, which removed pointer capture. Refused a call nobody made |
| `audit_the_cut_opens_where_it_was_saved` | — | **there was none.** `--prove` re-ran the ordinary pass and printed "this check is blind", every time, since the day it was written |
| `audit_sliders_are_live` | old wiring on the rings slider | sound |
| `audit_other_engines` | a broken-on-purpose page | sound — 21 problems |

**Neither failure is visible from outside.** A mutation that matches nothing
and a check that is genuinely blind print the same words. The only thing that
tells them apart is the check asking whether its own sabotage took hold.

Both are fixed (`68d230e`, `27b6e00`), and
`test_every_mutation_test_proves_its_own_mutation_landed` now fails by name if
a `--prove` script does not carry the guard. `audit_two_rooms_drag` now cuts
the CAMERA RELAY instead — every link ends in
`Plotly.relayout(other, {"scene.camera": ...})`, so it sabotages the mechanism
whatever shape it is written in.

**And the seam drag is genuinely fixed.** All four journeys turn both rooms
exactly in step, 0.0000 apart, from either side. The residual on file —
"right to left now stops instead of diverging" — was cured by the same 2.40.1
change that made the mutation meaningless, and nobody had re-measured it.

## A CHECK THAT LOOKS PERFECT MAY BE PROVING NOTHING — twice in one hour

Both attempts at the new pixel check reported "0 pixels different" seven times
over while testing **only colours**, because `_solid_remainder` refuses to
drop triangles from a shape that is not fully solid — and two shapes are drawn
see-through by default. Glossy against Matte keeps 414 and 440 triangles at
every fade, both ends included. Fully solid against sRGB the same paper goes
**650 to 370**.

So the check now measures its own fixture before reading any answer from it
(`faces()`), and refuses to report at all if the shapes keep their triangles.
The same guard went into `test_the_triangles_travel_with_the_colours`. This is
the third distinct way an invented or badly-chosen fixture has hidden a real
question in two days.


## ⚠ THE CRON PROMPT IS NOW OUT OF DATE IN ONE PLACE — 2026-08-20, later

Its item 2, "finish the sweep, 16 of 22", is **DONE: 22 of 22**, all six
foreground, all clean. Do not run them again as a sweep. What is left in the
prompt is item 1 (the cap, Basti's decision) and item 3 (whatever the checks
turn up), and item 3 is where the work now is.

### The vein that is paying: A CLAIM WIDER THAN THE POPULATION MEASURED

Three in three days, each found by asking a check what it can actually SEE
rather than what it says:

* "every slider follows its handle" — **seven of nineteen** were driven
  (`1a55ce6`, closed: all nineteen now asked by a gate rule);
* "the strip is inside the window rather than off the bottom or the side" —
  **only the side** was ever measured, and the strip was looked for under
  `.cq-controls`, a name matching nothing anywhere (`edd9938`);
* the page-sizing checks between them look at **8 of 23 pages**, so six
  page KINDS had never been opened at any size by anything. Sizing one of
  each found them clean — and then LOOKING at the two-room page on a phone
  found the shapes cut in half by their own walls (`0ff163f`).

**Where to point this next**: any check whose printed verdict names a
population ("Clean: N states") should be asked what N is a fraction OF.

### v2.44.0 shipped both. What is NOT done

* `docs/screenshots` were not rebuilt this cycle — nothing that reaches them
  changed (only the narrow-window rule, and the shots are taken wide), and
  `git status` after `make_sample_pages` showed only `09-a-room-each.html`
  and `12-a-cut-each.html`. No showcase page carries `class="half"`, so none
  of them uses the two-room writer.
* The release build for v2.44.0 was **queued, not yet verified at 11
  assets** — check `gh run list` and say so.


## 2026-08-20, LATE — v2.45.0, AND WHAT IS OPEN

**Basti asked for two things and both are shipped.**

1. *"Never stack — zoom the camera out instead so the shape fits a narrow
   room."* Done, and the machinery already existed: `fitToPane` pulls the eye
   back by how far the pane is out of shape, capped at twice, which measures
   EXACTLY right (a 195x654 room needs 2.00x, 310x660 needs 1.30x, 410x700
   needs 1.15x). It never ran, because `_spin_options` marked every page
   `placed` from "does this window have a camera". Now `placed` means THIS
   VIEW IS THE READER'S OWN, the page offers `cqSpin.reading()` (the view the
   fit was measured from), and the window remembers that instead of the
   fitted camera — so nothing compounds and a turned view is never re-fitted.
2. *"or can we give the option to choose whether the user wants left/right or
   top/bottom split?"* Done: a chooser beside the camera link, remembered,
   travelling into saved pages, short hover + long ⓘ, withheld when there is
   nothing to arrange, declared in the space registry.

**⚠ THE TYPE IS NOT THE SHAPE, and pulling back further will not fix it.**
The shape fits every room now. The axis titles still touch the wall on a
phone — measured with a PALE-pixel rule (bright, nearly colourless: type and
gridlines) rather than the coloured-pixel one: 0 px at 1440, 3 px at 820
(clean at 1.15x), and at 390 it is 5 px at 1.0x, 12 px at 1.3x and 5 px at
2.2x. It does not improve with distance, because the titles are placed
against the box rather than the shape. So this is a margin question, not a
camera one, and zooming further would shrink every shape for nothing.

### The six gate findings still to attribute

`scripts/audit.py --window` now reaches controls it used to skip, and reports:

| finding | first thing to establish |
|---|---|
| ~~light_roughness, light_fresnel, light_direction, light_height: 0 px~~ | ⚠ **THIS ROW WAS WRONG AND IT SAID SO CONFIDENTLY.** "The values arrive and the drawing library ignores them" was my own verdict, and a later measurement found a REAL BUG: the lamp was being placed 2,000 units away, which the library takes through the picture's projection, so every direction converged on one point behind the camera. Above against below, close in: **229,586 pixels different**; at the distance it was using, **0**. Fixed in v2.47.0. A dismissal in a table is as durable as a fact and reads exactly like one |
| ~~lost_in_colour: 0 px~~ | **ATTRIBUTED 2026-08-21 — a NEEDS entry, not a fault.** Measured: with no marking switched on, the colours it paints are IDENTICAL either way; with marking on they DIFFER. The control repaints the out-of-reach faces, and with nothing marked there are none. The check measured a control whose prerequisite was off |
| ~~rings_on: 0 px~~ | **ATTRIBUTED 2026-08-21 — the CHECK is wrong, not the window.** The guess in this row ("rings need a solid shape") is also wrong: the drawing adds its traces in EVERY state tried, 4 -> 8 with two papers solid, the same drawn as outlines, 2 -> 4 with one paper. And they reach the screen: rings off against on is **10,625 pixels** at full opacity and **22,573** see-through, worst channel 213. Whatever the gate was measuring, it was not the picture |
| ~~aspect, rings: "putting it back left 325,747 px different"~~ | **ATTRIBUTED 2026-08-21 — the CHECK's state, exactly as this row suspected.** Re-measured one at a time with nothing moving: aspect there-and-back moves **226,351 px** and puts back **0 px different**; rings moves **24,127 px** and puts back **0**. Both restore the picture exactly. Nothing to fix in the window |

**ALL SIX ARE NOW ATTRIBUTED (2026-08-21), and not one was a fault in the
window.** Four were the check's own state — a prerequisite switched off, a
measurement that could not see the thing, the movement left running — and
the lamp row was a REAL bug that this table had dismissed as "not work".
That is the score to remember: the table was wrong five times out of six,
in both directions.

**Attribute them one at a time.** Establish whether the window or the check
is wrong BEFORE changing either — the way `drive_chart`'s eleven were, and
the way `drift_by` was this week (it was the check: a control whose
prerequisite is dead cannot be judged).


## 2026-08-21 — THREE MORE FROM HIS WINDOW, and the reason they hid

All three reported on 2.45.1, all measured, all fixed, all in **v2.46.0**:

| what he said | what it was |
|---|---|
| "the colored part should have a clearer line instead this zig zag" | the clean cut REFUSED his case. The marking is measured against ONE shape and the fade against ALL the others; where those differ the shape kept its old mesh. 118 of 414 triangles straddled the boundary, before and after. Now cut a second time along the marking's own boundary: 0 of 650 |
| "split in top/bottom shows the bottom one nearly out of the window" | the arrangement asked 68vh EACH and lifted the row's ceiling. They share it now: rooms at 21–333 and 354–666 of an 833px view |
| "this one looks scattered" | the LIGHT, not the shape. A hull is 36.5% needles (worst edge ratio 714) against 4.1% for the real edge, and smooth shading smears the light along a needle. Lit facet by facet it is clean |

### ⚠ WHY EVERY CHECK PASSED WHILE ALL THREE WERE BROKEN

**The folder they read did not hold those pictures.** Measured across the 23
sample pages: NOT ONE was drawn as a simple skin, and exactly ONE showed what
a paper cannot print — with a single paper, the case that already worked.

Fixed at the root: `13b-two-papers-and-what-neither-can-print.html` and
`13c-wrapped-in-a-simple-skin.html` exist now, both named in the size sweep
and the three-engine sweep (both work from FIXED LISTS, not the folder — an
overclaim of mine, corrected), and
`python/test_the_sample_pages_cover_what_can_be_drawn.py` asks on every
commit whether the folder still holds one of each kind of picture.

**The next thing to point this at**: the paint modes (true colours, one
colour each, by lightness, by chroma, accent), the drawing spaces, and the
chart skins are not covered by that rule yet — the markers for them in a
written page still have to be worked out.

### ⚠ AND THE SAMPLE RUN LEAKED BETWEEN PAGES

Adding two pages in the middle changed FIVE later ones. `fresh()` did not put
back how the shape is worked out (a simple skin left the chooser on "hull",
and the next two pages were written as hulls) or where the reader is looking
from. Both restored — and the camera leak was older: THIRTEEN pages carried
`1.5, 1.5000000000000002, ...`, the standard view after a round trip through
a page, where they now carry an exact `1.5, 1.5, 1.5`.

## ⚠ THIS SESSION ENDED HERE — see `START-HERE.md` beside this file

The 10-minute job was stopped on 2026-08-20 at Basti's request, because the
session had grown slow. `START-HERE.md` and `CRON-PROMPT.txt` in this folder
are the handover; a pointer sits on his Desktop. Scratch space is now
`~/develop/ChromIQ-Gamut-Viewer/scratch`, not `/private/tmp`.

## State

`~/develop/ChromIQ-Gamut-Viewer/fork` at `c32d0bd`, pushed. Gates green:
891, and 888 + 3 skipped. Released: … v2.42.0, **v2.43.0** (the open-shell
explanation, the two dead mutations, the stranded-ⓘ rule).

### 🔴 THREE SCRIPTS IN TWO DAYS COULD NOT RUN AT ALL — and one more is open

| script | why it could not run | state |
|---|---|---|
| `make_doc_shots` | framed on a row in a folded section | fixed `af8ce54` |
| `drive_ink_amounts` | two guarded calls to methods the window lacks | fixed `fdad4ca`; its checks settled `5a41587` |
| `drive_chart` | defaulted to `demo-data`, a folder no checkout has | fixed `8b90b32` |

**"Not a wrong answer — no answer" is the shape to look for.** A script nobody
runs routinely fails in private, and a guarded call to a name that is gone
never fails at all.

✅ **Six of `drive_chart`'s eleven were stale (`29a064a`) — and I nearly
"fixed" the app to satisfy them, which would have undone a change Basti asked
for.** They demanded hover tooltips of 80+ characters naming all four file
kinds. His words: *"those hover tooltips should be short and the extended
version would be behind the tooltip icons."* `_HOVER_LIMIT` is 200,
`_one_sentence` trims every hover, and the long text goes to an ⓘ — or, for a
control stacked in a column, to the ⓘ the section already carries (measured:
2,282 characters, all four kinds named). **The checks looked in the one place
the rule forbids.** Now asked properly and mutation-proved.

✅ **All eleven attributed (`bde3a66`) — and NOT ONE was an application
fault.** `drive_chart` now says EVERY CHECK PASSED, from a script that could
not be run at all three days ago.

The last three: *"marks some but not all"* demanded a fault of a chart the
script writes for itself, whose every patch is inside by construction — the
window says so in words. It now asks the invariant that holds for any chart:
**the dots marked out of reach are the number the words give** (151/151, 0/0,
151/151 on the verification chart). *"a separate 'outside' one"* wanted that
trace unconditionally, i.e. a legend entry naming an empty set. And *"every
visible group fills the column"* was **failing on an empty set** —
`.parent().parent()` is the button's own group box, which contains no groups.
Reaching the real column then showed 329 against 365, which is a sub-panel
nested inside another group and indented as it should be.

⚠ **`git checkout --` to undo a mutation takes the fix with it.** Twice in one
day. Copy the file instead.

~~**`drive_chart` now runs and reports ELEVEN failures.**~~ Newly VISIBLE, not
newly created. Several look like stale expectations — *"its tooltip names
measurements / profiles / charts / pictures"* fails against a tooltip reading
*"Opens any of the four kinds of file this…"*, the same sentence said shorter.
Others (*"it marks some but not all [0]"*) could be either. **Attribute them
one at a time**, the way 24/25/26 were: establish whether the app or the check
is wrong BEFORE changing either.

⚠ The broad "can every script still run" sweep produced NO OUTPUT — `python`
buffers, so a background run must use `python -u` or the whole thing is lost.

### ⚠ `isVisible()` IS FALSE FOR ANYTHING IN A FOLDED SECTION — three times in one day

A row inside a shut section reports **`visible=False, hidden=False`**. Three
separate places were caught by it:

1. `make_doc_shots` could not run at all — it framed on a row in a folded
   section (fixed, `af8ce54`);
2. `drive_ink_amounts` checks **25 and 26 fail** on exactly that reading
   (`_chart_skin_row`: visible=False, hidden=False, inside 'How the patches
   are drawn' with `fold_open=False`) — **not yet attributable, and NOT made
   to pass**; the instrument cannot tell "the row is missing" from "the
   section is shut", so neither answer is worth reporting until it can. This
   is the next thing to settle;
3. `audit_panel` learned it long ago and opens every folded section first —
   which is the fix, and which never travelled.

### ⚠ A GUARDED CALL TO A METHOD THAT DOES NOT EXIST NEVER RUNS (fixed, `fdad4ca`)

Asked statically of every script — does each name a window attribute that
still exists — two came back, both wearing `if hasattr(...) else None`:
`_close_them_all` (the second pair was measured with FOUR shapes open) and
`_write_current_page` (nothing was saved, so a fallback wrote a page with **no
shapes in it** and check 20 asked whether *that* was the ink view).

The grep is three lines and worth repeating after any renaming.

### ⚠ THE SCREENSHOTS COULD NOT BE REMADE AT ALL (fixed, `af8ce54`)

`make_doc_shots.py` stopped on its first picture — *"Outline colour is not on
screen in the grab"* — and had been stopping there, so three of the four
pictures were from an older run and the first could not be produced by
anybody. **The row is neither missing nor renamed: "How it looks" is FOLDED
SHUT**, so the group's inner widget is hidden and no scrolling reaches a child
of it. `audit_panel` learned this long ago and opens every folded section
first; the lesson had not travelled to the second script.

The failure mode was not a wrong picture but **no** picture, and it was silent
because nobody runs that script except when they already suspect staleness.
All four are remade and all four had drifted.

⏳ **Basti's call:** "Carry a cross-section too, with a switch" is absent from
shot 22, because the dialog withholds it for a picture that cannot hold two
views and the shot is taken in such a state. Correct behaviour, honest
picture — but the newest export option is invisible in the picture that
documents the export options. Staging the shot to include it is a choice, not
a fix.

**docs/pages and docs/showcase/pages are current** — rebuilt and pushed with
`f277bde`, because the wording lives in the page writer. Worth knowing that
they regenerate BYTE-IDENTICAL when nothing that reaches them has changed
(checked the cycle before), so `git status` after a rebuild is a reliable
answer to "is the page stale". Released: v2.40.0, v2.40.1, v2.40.2, v2.41.0 (the
live fades), **v2.42.0 (all seven sliders + the Detail file-dialog bug)**.

**Items 1, 2, 3 and 9 are finished.** The only one left is **8 — the cap**,
and that is parked on Basti's decision, not on work.

### ⚠ MAKING A CONTROL LIVE PUTS IT IN `audit_what_you_save`'s SUBJECT

That check opens with the list of controls that change the picture WITHOUT
writing a page, and warns about the quiet failure: "the screen is right, the
reader's copy is not". The list was written when there were seven. The two
fades, Detail and the cross-section made it eleven, and none was added.

**All four are now in it** (`898e651`, `e3a8e89`) and all four were sound:
0.620 both sides, 33 steps both sides, L\* 37 both sides. Driven through
`valueChanged` alone — a reader mid-drag, the state where the two are free to
disagree. Detail needs a longer pump than the rest: it is the one that waits
for the handle to pause before it pushes.

⚠ **Compare like with like.** Detail's expected side first counted the
reference shape's own corners (6,534 at 33 steps) against the **47,232 points
the page gives it** — the page holds a CAGE over that shape, line segments
with gaps, not a list of corners. The check reported the app broken on the
strength of it. Fourth time in this project a number has been compared with a
different quantity.

⚠ Two traps made `--prove` silently run the ORDINARY pass and report Clean:
`sys.argv` is emptied at import so Qt gets a tidy one (take the flag before,
as `ASKED`), and the mutation's verdict must come BEFORE the ordinary report
or that report's `return 1` wins.

### ⚠ A STALE "STILL TO DO" CAN HIDE A REAL GAP OF A DIFFERENT SHAPE

Item 9 said "only the export dialog's choice + tooltip is left". The choice
and the tooltip were built. What was missing was that **nothing had ever
driven them** — `both_views` did not occur in `scripts/` or in any test,
`audit_two_views` handed the writer its arguments directly, and the
sample-page harness replaces the export dialog with a stand-in whose
`choices()` never mentions it. That is the exact fault `make_sample_pages`
warns about in its own first paragraph.

⚠ **A QtWebEngine window and playwright do not survive each other.** Inlined,
`audit_two_views` **died before printing a line and still exited 0** — the
worst way for a check to fail, and it reads as Clean. The same pairing crashes
the unit-test gate outright. Drive the window in a SUBPROCESS.

⚠ Two modal traps, ten minutes each: the window's "saved" notice is modal
(`Notice.warn`/`Notice.say` must be stubbed), and `QFileDialog.exec` cannot be
patched from outside — replace the window's own `_file_dialog`. Everything else on the list
of ten is done and measured.

### Why the stranded ⓘ took five attempts (`88550f8`)

Four measured pixels and failed; the fourth is the one that explains the other
three. Walking layouts from `window.layout()` found **0 stranded out of 83
icons with the fault in place** — because that walk never reaches the control
column at all. It is inside a scroll area. **A measurement that cannot see the
thing it is asking about looks exactly like one that found nothing wrong.**

The rule that works has no pixels in it and starts from each icon rather than
from the window: an ⓘ still alone on a row of a column when the window is
finished is one that neither `_attach_in_layout` nor a by-hand placement
reached. A grid is exempt, for the same reason the attaching pass exempts it.

⚠ **And the mutation nearly sabotaged itself.** Qt hides a widget removed from
a layout, so the fault was in place and invisible to the very rule meant to
catch it — reading as "this check is blind", which is precisely the confusion
that hid two dead mutations earlier the same day.

⚠ **The old scratchpad copy at `/private/tmp/.../scratchpad/fork` is a stale
1.2 GB duplicate** and is NOT the tree being worked on. A `__pycache__` left
over from when the tree lived there makes pytest print that path in
tracebacks, which reads exactly like "the gate ran against the wrong tree" and
does not mean it. `find python scripts -name __pycache__ -exec rm -rf {} +`
settles it.

On the disk question: the viewer's own leftovers were **11 folders, 111 MB**
(swept), not the 27 GB that was fixed earlier — those come from a window that
is killed rather than closed, so `closeEvent` never runs. 629 GB free.

---

## FOR BASTI — THE WALL OF TEXT CAME BACK, ON A WIDGET THE FIX DID NOT WALK

Your complaint was: *"some tooltips from hovering extend very far. those hover
tooltips should be short and the extended version would be behind the tooltip
icons."* The fix, `_shorten_the_hovers` in `python/gamut_app.py`, works: it
cuts every over-long hover to its first sentence and moves the long version
behind an ⓘ, creating one where there is none. Measured, it is doing real
work — disable it and nine controls in one panel state go straight back over
the limit.

**But it walks `QAbstractButton, QComboBox, QSlider` and nothing else.** The
labels, the group headings and the run's list are not asked. So:

| what | characters on hover |
|---|---|
| the wall you complained about | 2,139 |
| `_drift_families`, still there today | **2,494** |
| the run's list of profiles | 668 |
| every folding group heading (17 of them) | 348 |

It is reachable: the label hides while it is empty and shows the moment it has
a line to report, which is exactly when somebody hovers it. Driven and
photographed — `fork/docs/probes/the-hover-wall/a-2494-character-hover.png` —
it opens a box **481 × 562 px, over half the height of this screen**, dropped
over the panel by a pointer merely passing across.

**Why it is not already fixed.** Extending the walker to labels is not one
line. That function's own comments record two attempts at giving a control an
icon that both broke the column — one put the ⓘ under the button, the other
overflowed the panel by 11 px — and the drift box already has an ⓘ whose words
are DIFFERENT from the label's, so the obvious move silently throws 2,494
words away. Your rule is clear; the safe way to apply it here is not, and
guessing at it is how the last three evenings went wrong.

Not shipped, not decided. The guard that keeps the working half working is in:
`audit_panel.py` now asks the OUTCOME — no control answers a hover with an
essay — so removing the shortener is caught even though every older rule
would still say Clean.

---

## ~~FOR BASTI — NINETEEN AUDITS STAND ON FOUR FILES NOTHING CAN REBUILD~~

**SETTLED 2026-08-21.** He answered: *"any files needed for tests can be
uploaded to github as well and feel free to add more if you need any"*. The
four profiles were read first — all four say `Glossy paper (demo profile)`,
a placeholder copyright, and `DESCRIPTOR "Demo measurement"` inside; no
customer, no employer, no person — and they are now in the checkout at
`demo/one-printer-over-time/`. `scripts/demo_profiles.py` looks in the temp
folder FIRST and falls back to that copy, so a freshly built set still wins.
Proved with TMPDIR empty: the audit that used to die at `profiles[0]` now
finishes Clean with identical rows. What originally made them is still
unknown, and no longer matters.

The record of what it was:


`scripts/audit_two_groupings.py`, `audit_what_you_save.py`, `audit_controls.py`
and sixteen others begin the same way:

```python
profiles = sorted(pathlib.Path(tempfile.gettempdir())
                  .glob("showme-*/printer-*.icc"))
```

Those four profiles are real and the audits pass on them today:

```
/var/folders/1b/…/T/showme-gzcjocho/printer-2019.icc   18 Aug 01:07
                                    printer-2021.icc   18 Aug 01:07
                                    printer-2023.icc   18 Aug 01:07
                                    printer-2024.icc   18 Aug 01:07
```

**Nothing in this repository creates them.** Not a script, not a test, and
nothing that was ever deleted from the history either — searched with
`git log -S`. They were made on 18 August by something outside the checkout,
and nineteen audits have been standing on them ever since.

`/var/folders/…/T` is cleared by macOS on its own schedule and on a reboot.
When that happens:

* the audits that guard say so plainly — *"no demo profiles to drive the
  window with"*, exit 1 — and that is the good case;
* the ones that do not guard die on `profiles[0]` with `IndexError: list
  index out of range`. Measured, by pointing `TMPDIR` at an empty folder.

Neither is silent, so nothing here is reporting a false Clean. The cost is
that **the day those files go, nineteen audits stop answering, and there is no
way to make them again.**

**I have not copied them anywhere, and deliberately.** They may be built from
your own measurements, and the standing rule is that nothing of yours goes on
GitHub. Moving or duplicating files of yours is not mine to do either. What
they are, and whether ChromIQ made them, is something only you know.

If you want them to survive, the safe move is a copy somewhere durable that is
yours:

```bash
cp -R /var/folders/1b/*/T/showme-*/ ~/develop/ChromIQ-Gamut-Viewer/fixtures/
```

and then a decision about whether the audits should look there as well.

---

## REPORTED 2026-08-22: THE PICTURE BLINKS BLACK ON EVERY REDRAW

*"sometimes they show wholes for a split seconds before they become whole …
it would be nice if you could rather hold them back until they are complete"*

MEASURED, watching the view itself at 50 ms intervals through one fade change:

    120 frames watched, 16 unlike the settled picture
    t+3.56s  182,888 px unlike  -- the view is entirely BLACK
    t+3.88s  182,888 px unlike  -- still black
    t+4.22s    7,970 px unlike  -- the picture, all but settled
    t+4.57s          0          -- settled

So it is not a partial shape first: the view empties, stays empty for about
0.7 s, and the new picture then arrives nearly whole. `_show_page` loads
straight into the live view (`self._view.setUrl(...)`), and a browser paints
the blank document before it paints the plot.

⚠ THE OBVIOUS CURE HAS ALREADY FAILED ONCE, and its own note says why: a
second view was loaded and the two swapped on `loadFinished`, and it left the
frame EMPTY -- the widget put into the layout was the one just sent to
about:blank. Reported then with a photograph of a window with no picture in
it. `_show_page`'s docstring asks for a cure "proved by a driver that watches
the frame rather than the address in it", which is now written:
scratch-side frame watching, comparing `win._view.grab()` against the settled
picture.

SAFER SHAPE FOR THE FIX, and the reason: do not swap widgets at all. Grab the
last good frame into a QLabel laid OVER the view, load as now, and drop the
label once the frame has settled. A frozen picture cannot become an empty
viewer -- the worst it can do is show the previous picture a moment too long,
which is exactly what was asked for.

⚠ **TRIED 2026-08-22, AND IT DOES NOT WORK. REVERTED.** Both shapes of it
were built and measured, `_show_page` confirmed to run (traced, three times
per change):

* a QLabel raised over the view: the held picture showed in four frames of
  six and the blank page still flashed through the other two;
* the same, with the view HIDDEN behind it: unchanged, still 100% black
  frames at t+3.56 and t+3.88.

A `QWebEngineView` is a NATIVE surface. It paints above ordinary widgets
whatever the stacking order says, and hiding it does not stop the hole it
leaves being painted blank. Anything built out of Qt widgets over that view
will flicker.

⚠ **AND THE MEASUREMENT WAS BLIND AT FIRST**, which cost a whole attempt:
grabbing `_view` photographs what is UNDER the overlay, so the fix looked
like it changed nothing. `_frame` is what a person sees.

WHAT IS LEFT TO TRY, in the order I would try it:
1. **Rebuild less often.** The blink exists because a fade change writes a
   whole new page. There is already a live path that restyles in place
   (`_push_detail`, and the fades' own per-vertex alpha) -- widening it to
   cover this change removes the blink instead of hiding it.
2. A frameless top-level window over the view, which composites above a
   native surface where a child widget does not. More machinery, and it can
   show in the task switcher.
3. Ask the page to paint the previous picture as its own background while it
   loads -- inside the page, where there is no native-surface problem.

NOT THE SAME QUESTION AS THE SAVED PAGES. He asked whether this helps exports
for the web: it does not. The overlay is a Qt widget in the app window and
none of it exists in a saved page. Whether an exported page blinks in a
browser is unmeasured -- and worth measuring, because the cure there would be
inside the page (hide the plot until `plotly_afterplot`) and would be the
same fix as (3).

---

## WHICH ACTIONS BLINK, MEASURED 2026-08-22

Driven with his profile and sRGB, watching whether `_show_page` runs:

    drag How solid it looks        changes it in place
    drag Depth                     changes it in place
    tick the walls and grid off    changes it in place
    tick Show rings inside         REWRITES THE PAGE
    first shape solid -> outline   REWRITES THE PAGE
    page colours dark -> light     REWRITES THE PAGE
    colour space Lab -> XYZ        REWRITES THE PAGE

⚠ **AND FADES DO NOT BLINK, WHICH CORRECTS MY OWN REPORT.** The blink I
measured on a fade was mine: `_push_fade` sets `_fade_live` from an
ASYNCHRONOUS callback, and my driver called `_after_fade()` before it landed,
so the release fell through to a rebuild. Let go after a moment, as a person
does, and `_fade_live` is True and nothing is rebuilt. Any future driver that
measures a fade must wait for that callback or it will provoke the very fault
it is looking for.

WHERE THE WORK IS, if this is worth doing:

* **rings** and **colour space** genuinely need new geometry -- a rebuild
  there is honest, and `audit_sliders` already records rings that way.
* **page colours** change nothing but appearance. Backgrounds and axes can be
  relaid out in place and the vertex colours restyled; this is the strongest
  candidate.
* **solid -> outline** has a precedent that says it need not rebuild: a SAVED
  PAGE already offers the reader "draw the edges instead of the surface" and
  does it live, without reloading anything. Whatever the page does, the window
  could do.


---

## THE BLINK: WHAT IT IS WORTH, AFTER HE SAID WHERE HE SAW IT

*"my complaint rose when i was watching your automated tests. i don't exactly
know what you did"*

That matters, and it agrees with what the measurements found:

* **fades do not blink** in ordinary use -- the rebuild I measured on one was
  my own driver releasing before the live push's asynchronous callback landed;
* opacity, depth and the walls/grid all change in place;
* what genuinely rewrites the page is new geometry: opening a file, changing
  the comparison, rings, a change of colour space -- and a test driver does
  those back to back, over and over, which is what he was watching.

SO THE FLASH HE SAW IS LARGELY THE TEST HARNESS, not the application in use.

⚠ A CURE EXISTS AND IS CHEAP TO REACH, if it is ever wanted: the whole figure
can be pushed into the page ALREADY OPEN. Measured, his profile against sRGB:
0.8 MB of figure JSON, `Plotly.react` answered "reacted" in **0.1 s**, against
about 0.7 s of blank for a reload. `traces_for_restyle` already does the
narrow version of this for a detail change.

WHAT WOULD HAVE TO BE PROVED FIRST, and was NOT proved here: that the pushed
picture is the same picture as a rebuilt one. My comparison built two
different scenes (two shapes against three) and measured 166,465 differing
pixels, which says nothing about `react` and everything about the test. The
real check is the same scene both ways, expecting 0 pixels above threshold.

RECOMMENDATION: do not rebuild the redraw path for this. The user-visible
blink is mostly the harness; the change touches every picture the window
draws; and the project's own rule -- the same picture however you reach it --
would demand the pixel comparison above on every kind of scene before it could
ship. Worth doing only if he asks for it in ordinary use.


---

## ⚠⚠ THE SEAM — READ THIS ONE, THEN ONLY WHAT IT SENDS YOU TO

Ten sections below were written about the seam in a single day and most are
SUPERSEDED. Each one that is has a marker on its first line. The settled
answer, in four sentences:

  * THE CAUSE WAS THE DEPTH BUFFER, not the lid's geometry, colours, winding,
    shading, draw order, alpha, or the closeness threshold. gl-plot3d never
    sets a near or far plane and falls back to 0.01/1000 over a unit cube, and
    this machine's buffer is SIXTEEN bits — one step of depth larger than a
    Lab at the distance these shapes are drawn from.
  * FIXED in 4470f70 (`_DEPTH_JS`), which fits the planes to the scene's own
    corners. Speckle the lid adds, product page, four cameras: 121→2, 158→1,
    193→4, 34→1.
  * THE SEAM WORK IS REAL BUT SECONDARY: the tuck, the sewn seam colours and
    the lighting are all still in and all still measured.
  * WHAT IS LEFT is the two SHELLS fighting each other (~3,500-4,400 speckle
    with no lid at all). Some was precision; most is geometric and may be the
    honest answer rather than a fault. Settle that before touching it.

THE SECTIONS WORTH READING, in this order:
  1. "THE CAUSE WAS THE DEPTH BUFFER ALL ALONG" — the answer and the two
     measurement traps that cost the week.
  2. "THE HATCH IS NOT THE LID'S PAINT — IT IS THE LID'S DEPTH" — how it was
     narrowed down; six levers with numbers.
  3. "WHAT THE LITERATURE SAYS" — why a stencil and a polygon offset are not
     reachable, and what is.
  4. "THE TIMELINE'S OWN PICTURE GETS NEITHER SCRIPT" — open, unconfirmed.

EVERYTHING ELSE ABOUT THE SEAM IS HISTORY. It is kept because two of the
entries are retractions of my own published claims, and a record that quietly
loses those is worth less than one that keeps them.

---


## THE SEAM: WHICH THEORY IS IT? MEASURED 2026-08-22

> ⚠ SUPERSEDED. The two theories it retires stay retired; the mechanism it
> proposes at the end (the clearance collapsing at the rim) is NOT the
> cause. See "THE CAUSE WAS THE DEPTH BUFFER ALL ALONG".

The job asked this to be settled before anything was changed. It is settled,
and the answer is that NEITHER standing theory explains it alone.

Driven at his settings -- his profile against sRGB, agree 45, both drawn as
surfaces -- counting how many pixels the lid changes:

    Detail  6   sRGB about   400 faces    2,673 pixels
    Detail 20   sRGB       4,332 faces    2,057 pixels
    Detail 40   sRGB      18,252 faces    1,885 pixels

A FORTY-FIVE-FOLD finer comparison removes THIRTY PER CENT. If the artifact
were the facets of the shape the lid is cut from, the visible area would fall
about sevenfold. So resolution modulates it and cannot remove it.

And the queue's older theory -- that the lid and the piece are classified
separately so their rims disagree -- does not fit either: the lid's rim IS the
piece's own corners, unmoved, and `test_a_lid_closes_the_cut.py` asserts it.

WHAT IS LEFT AT DETAIL 40, looked at rather than counted: not a sawtooth but a
fine vertical COMB where the lid runs nearly parallel to the skin, and a
serrated top edge. Both absent with the lid off.

MY MECHANISM, now under hostile review: in `close_the_cut` the lid is held
under the skin by `step = min(clearance, 0.01 * (reach - far))`. At the rim
the drop `reach - far` goes to zero, so the clearance goes to zero exactly
where the two surfaces meet, and the depth buffer is left to choose between
them pixel by pixel.

⚠ DO NOT ACT ON THAT PARAGRAPH UNTIL THE REVIEW COMES BACK. The last three
things I was sure of about this lid -- that the 7,999-face lid proved it
worked, that the seam wobbled 3.4 Lab, that the teeth were the comparison's
facets -- were each refuted by a measurement.

---

## THE SEAM: SETTLED, AND WHAT IT COST TO SETTLE IT (2026-08-22, later)

> ⚠ SUPERSEDED, and it was not settled. Its measurements hold; its
> conclusion does not. See "THE CAUSE WAS THE DEPTH BUFFER ALL ALONG".

WHICH THEORY. Neither of the two standing ones. Both were refuted by
measurement, and the refutations are cheap to repeat:

* NOT two lids whose rims are independent chordings of one crossing curve.
  Capping ONE shape at a time (`scratch/whose_comb.py`) shows each lid lays
  its own artifact, and every one of the printer's 1,134 lid rim corners sits
  on a piece rim corner to within **8.3e-08 Lab**. A hostile review
  reproduced 5.0e-08 per component independently.
  ⚠ THE FIRST RUN OF THAT DRIVER SAID THE OPPOSITE, because the scratch prefs
  store carried `sRGB = mesh` over from the previous driver and a mesh is
  ineligible for a lid. Set every style you depend on EXPLICITLY and print
  what it ended up as.
* NOT the facets of the shape the lid is cut from. Detail 6 → 20 → 40 is a
  forty-five-fold finer comparison and removes only about thirty per cent.

WHAT IT IS. The lid is in the right place and still cannot be painted. No lid
CORNER is above the skin it is held under (ring 1 sits a median 1.71 Lab
below), and 0.01% of its AREA pokes through, by 0.072 Lab. The lid and the
piece meet at a FOLD along the seam and they meet BY BEING THE SAME CORNERS,
so the two surfaces are at exactly the same depth all along that line and the
picture picks between them in bites. Painting the lid red proves whose pixels
they are: 4,805 of the 4,873 it changes turn red. Flipping the winding moves
0 pixels.

THE CURE, in `cap_over_the_cut`: the DRAWN rim is tucked diag/400 down each
corner's own ray. What `close_the_cut` builds is untouched — the piece's own
corners, unmoved, which every closure check rests on.

MEASURE IT WITH TWO NUMBERS. OUTSIDE = pixels the lid changes at his camera,
where it ought to be invisible. INSIDE = pixels it CLOSES when you look into
the opening from underneath with the other shape drawn as a cage. The first
alone is minimised by DRAWING NO LID, and that is exactly how a bad rule
scored well here for two commits. `scratch/two_sided.py` prints both.

    where the cycle started   OUTSIDE 4,659   INSIDE 77,512
    now                       OUTSIDE   349   INSIDE 74,475

⚠ A RULE THAT SCORED WELL AND WAS WORSE, and what it cost to catch. Between
those two lines I shipped a rule that withheld lid triangles hugging the
skin. It halved OUTSIDE on his pair and, on sRGB against Display P3 — two
reference spaces, the default space, the default Detail — withheld **97.1%**
of one lid. 103 configurations flagged, worst 98.06%. Reverted in a1c6111.
The tuck alone beats it on both numbers.

### DONE (a98c08e): THE LID NOW FOLLOWS THE PAINTING

`cap_over_the_cut` paints from `theirs.colors` and the seam sewing from
`mine.colors`; neither consults `_paint_vertices`. Measured at the 297 sewn
seam corners, Glossy against sRGB, lid against the skin beside it:

    true   0.0/255      solid  197.5      chroma 150.8
    lightness 132.4     accent  32.7

So in four of the five shipped paint modes the lid is a patch of true colour
inside a shape painted some other way. Older than any of this week's work.
Fixed by interpolating `_paint_vertices(theirs, paint, 1 - which)` through a
new `_painted_floats`, with `paint` reaching `cap_over_the_cut` from
`build_figure` and joining the cap cache's key. Measured after:

    True colours      349 px   One colour each 2,595   By lightness 271
    By chroma         267      In the accents    436

⚠ AND "ONE COLOUR EACH" BARELY MOVED, BECAUSE WHAT IS LEFT IS NOT THE LID.

### NEXT JOB: THE TWO SHAPES FIGHT WHERE THEY CONVERGE

On the ridge near the white point his profile and sRGB run a hair apart, and
the depth buffer picks between them facet by facet. Measured in "One colour
each", pink pixels on that ridge:

    no lid at all      8,504        with the painted lid   9,385

So it is there with the LID OFF, it is the two SHAPES, and it is much older
than this week. True colours hide it because both surfaces are nearly the
same colour there; any flat painting makes it obvious. Nothing about the lid
will fix it — it wants either a hair of separation between the two skins, or
one of them not drawn where they coincide, and BOTH of those are the kind of
change that turned into a 97%-withheld lid last time. Measure with two
numbers before touching it.

### ALSO OPEN, from the same review

* `cap_over_the_cut` costs ~70-76 ms more per shape than it did (a second
  full `_rays_onto` cast). ~150 ms per pair on a 2 s call.
* In XYZ **no pair ever gets a lid**: `TOO_CLOSE_TO_CLOSE = 1.0` is absolute
  and the whole gamut spans about 1. Pre-existing.
* `_at.setdefault` picks the first of several duplicate crossing corners when
  sewing. Measured harmless today (0.0/255 spread among the duplicates) and
  fragile.


---

## THE SECOND HOSTILE REVIEW, AND WHAT SURVIVED IT (2026-08-22, later still)

Its verdict was NOT FIXED. One part was right and is fixed in c9af3b7; the
rest did not survive checking, and the checks are cheap to repeat.

RIGHT: the tuck opens a slit of rim-perimeter x tuck, and diag/400 is a share
of the SHAPE applied to a lid that can be a sliver of it. On sRGB against
Display P3 the slit was 790% of the lid's own area. Capped at a twentieth of
the lid's area spread along its own rim. His pair does not move.

RIGHT: `test_every_seam_corner_is_tucked_and_by_how_much` had a cosine check
that could never fire, because a sideways slide that changes the radius is
caught by the magnitude check first. It now measures the part of the MOVE
that lies across the ray, and a mutation that keeps the radius exact proves
it.

DID NOT SURVIVE — and each of these is a trap worth knowing:

* "52.9%-60.1% of the drawn lid's corners lie on the shape's own skin." Those
  corners are the RIM, and the rim is 53.9% and 62.5% of those two lids —
  a figure its own report gives. As drawn, after the tuck, 0.0%-1.0%.
  `scratch/whose_number.py` asks it four ways.
* "A bright white herringbone worth 14,703 speckle pixels on Display P3
  against Rec.2020." Rendered in the app's own viewer on this machine's GPU:
  4,876 speckle with the lid, 4,593 without — 283 apart, and the two pictures
  are indistinguishable. ⚠ THE REVIEW RENDERED THROUGH SWIFTSHADER. Depth
  ties are precisely what differs between a software rasteriser and the GPU
  the user has. Ask a subagent to render through the app's own viewer, or
  take its speckle numbers as being about its own renderer.
* "OUTSIDE = 349 is not reproducible; 57,763." At agree 45 an opaque lid
  replaces the see-through interior, which is the lid doing its job.

### STILL OPEN

* DONE (7ea4c4d): the feature was dead in CIE XYZ, because
  `TOO_CLOSE_TO_CLOSE` was a flat 1.0 Lab asked in whatever space the reader
  chose, and an XYZ gamut spans about 1.0 in total. It is a share (0.005) of
  the diagonal of the two shapes TOGETHER now -- the extent the picture is
  drawn over. All six calibration verdicts hold; the CIELAB threshold moves
  from 1.0 to 1.32 Lab on a paper. XYZ now draws 7,530 and 7,999 triangles
  where it drew none, and the lid is where a lid belongs: 0.00% of its area
  outside the piece, both pieces wrapping their middle at exactly 4.0000pi.
  ⚠ ASSERT THE PROMISE, NOT YOUR EXPECTATION. My first test asserted
  [True, True] in every space and failed -- Display P3 contains nearly all of
  sRGB, so sRGB has nothing to cap and rightly gets no lid in Luv or XYZ.
  The tick and the drawing agreed all along.
* The two shapes fight where they converge (see the section above).


---

## THE THIRD HOSTILE REVIEW (2026-08-22, evening)

Verdict NOT FIXED, on a fault that was real and is now fixed (39ce9a6): a
SAVED PAGE could not fade the lid. Its other findings, checked:

DONE (39ce9a6): the page fades in JavaScript through `withAlpha`, which reads
the TEXT of a colour and returns anything without a "(" untouched. The lid
went out as float triples at the default "where they differ" of 100.
134,453 -> 13,133 pixels on his own pair. ⚠ A TEST OF MINE HELD IT IN PLACE
and its stated reason was false: writing the colours as text changes the
window by 0 pixels.

### STILL OPEN, from that review, in the order I would take them

1. DONE (d1da566). THE CAP'S REASON WAS FALSE, and the cap was right. c9af3b7 said
   the tuck removes `rim perimeter x tuck` of lid area. It does not -- the rim
   corners move and the triangles touching them STRETCH. Measured with the cap
   removed, real lid area before -> after: sRGB vs Display P3's sliver lid
   25.82 -> 172.2 (it GROWS 6.7x), and across every pair at HEAD the real area
   change is between -1.8% and +0.4%. So `_lid_area / _rim_len` in
   `cap_over_the_cut` and the 5% assertion in `test_the_lids_seam_is_tucked.py`
   pin arithmetic rather than geometry. Re-derive the cap from what actually
   happens (a sliver lid stretched into a skirt) or drop it.
   FIXED: the tuck is now the largest that leaves the lid's own AREA within a
   fiftieth of what it was, found by halving rather than by a formula. On the
   sliver the model said 790.3% lost where the truth is 566.87% GAINED --
   the wrong sign, not just the wrong size.
   ⚠ AND HOLDING THE AREA STILL IS SATISFIED PERFECTLY BY NEVER TUCKING. A
   mutation returning 0 passed 11 of 11 checks; the loop now asserts each lid
   is still tucked.
2. DONE with 1: the modelled cap cost 21% of the tuck's benefit where it bit.
   The measured cap makes the tuck 3-4x larger there -- sRGB vs Adobe RGB
   0.0513 -> 0.2052, Display P3 vs Rec.2020 0.1070 -> 0.3780 -- and his own
   pair does not move at all.
3. HALF DONE (27ed86a). THE TICK'S REASON FOR REFUSING WAS WRONG when the
   closeness threshold was why. `gamut_app.py:15285` says "one shape reaches past the other
   everywhere, or the middle lies outside one of them" -- neither is true for
   sRGB vs Adobe RGB in CIELUV, where both cover 4pi and thousands of faces
   stand. AND THE REFUSAL COSTS A GOOD LID: at 0.001 that pair's outside
   speckle goes 6,008 -> 4,885 and it closes 24,399 pixels of opening, with a
   clean picture. The same two shapes in CIELAB get lids of 7,999 and 9,842
   triangles. A presentational choice turns the feature off.
   FIXED: `which_shapes_could_be_capped(..., saying=True)` returns (can it,
   why not) and the window has a sentence per reason.
   ⚠ STILL OPEN -- THE THRESHOLD ITSELF. That CIELUV pair's shares are
   0.00256 and 0.00393; two readings of one paper, which MUST be refused, is
   0.00213. They OVERLAP, so there is no threshold that keeps both verdicts
   and no nudge will do. Either the question is wrong (median gap over the
   picture's extent may not be what decides whether a lid can be told from
   the skin) or the answer has to be measured from the PICTURE -- e.g. drive
   both pairs on screen at a range of thresholds and count speckle. Do that
   before touching TOO_CLOSE_TO_CLOSE again; the last two thresholds I set
   from a model were both wrong.
4. "ONE COLOUR EACH": on the ridge where the two gamuts converge, saturated
   pink is 1,124 pixels with the lid against 272 without -- 4.1x. The
   herringbone is the two SHAPES (see below), but the lid is opaque where the
   agreeing shell is 45% see-through, so every pixel the depth buffer awards
   it comes out at full strength. Cause: the clearance step at
   `gamutview.py:1548` goes to zero exactly where the two surfaces converge.
5. DONE (0db7773). HALF OF EACH LID'S VERTICES WERE SHIPPED AND NEVER DRAWN: `cap_over_the_cut`
   returns `close_the_cut`'s shared corner array, which carries the piece's
   own non-seam corners. sRGB's lid ships 7,053 corners and uses 3,472 --
   50.8% dead, each with a colour and a mask character, in every saved page.
   FIXED where the trace is built (not in `cap_over_the_cut`, whose numbering
   a check depends on): a two-lid page 5,898,144 -> 5,672,517 bytes, picture
   identical to the pixel.
6. THE 13,133 PIXELS LEFT after the page-fade fix are a fully transparent mesh
   still being composited. The page can recolour triangles but not drop them,
   which is what `_solid_remainder` does in Python.

⚠ AND A JAVASCRIPT ERROR I HAVE NOT PINNED DOWN. Driving the window with the
lid ON throws 8 x "Uncaught TypeError: Cannot read properties of null
(reading 'join')" per redraw, 0 with it off, at line 2012 of the scene HTML --
which is inside the minified plotly bundle, in its GLSL tokenizer. It did NOT
reproduce when I bisected the lid trace's properties one at a time, so it is
probably on the FADE/restyle path rather than the first draw
(`scratch/js_error.py` reproduces, `scratch/js_bisect.py` does not).


---

## THE THRESHOLD'S OWN PICTURE — REPRODUCED, AND I HAD IT BACKWARDS

> ⚠ THIS SECTION CORRECTS ITSELF PART-WAY THROUGH. Read to the end before
> acting on any number in it.
## (2026-08-22, late; corrected the same evening in 6bd619a)

`TOO_CLOSE_TO_CLOSE` exists because "the picture comes back hatched with
diagonal stripes" for two readings of one paper, and its note records 32,308
pixels of a 1600x1050 window changing when the tick goes on.

I COULD NOT REPRODUCE THAT, on this code OR on v2.52.1 which predates this
week's work. `scratch/find_the_hatch.py`, threshold forced to 0, two readings
of one paper, six settings (agree 15/45/85 x his camera and from above),
1600x1050, counting isolated-pixel speckle:

    the lid's own speckle:  -96  -362  -50  -147  -2  +9

The lid TAKES SPECKLE AWAY in five of six. `scratch/threshold_sweep.py` says
the same for sRGB vs Adobe RGB in CIELUV: +33 speckle over 299,584 changed
pixels, and the picture is clean to look at.

⚠ BUT MY SETTINGS ARE NOT ITS SETTINGS: I measure 184,934 to 1,332,149 pixels
changing where the note says 32,308, so I am not drawing the picture it drew.
Until that picture is reproduced, "I could not find the hatching" is not "the
hatching is gone", and the threshold stays where it is. THIS IS THE OPEN
QUESTION, and it is worth real effort: if the hatching is genuinely cured by
this week's work then the threshold is refusing good lids in every space, and
that is the project's own worse mistake at its largest.

⚠⚠ RESOLVED, AND THE PARAGRAPHS ABOVE ARE WRONG. The hatching is there on
THIS code. Every measurement above drew the two shapes SEMI-TRANSPARENT --
`build_figure`'s default for a pair -- and a see-through shell hides the
fight completely. With `opacity=1.0`, which is what the window's slider gives
at 100 and therefore what a reader sees, the diagonal stripes appear at once.

RUN `scripts/show_the_hatching.py`. The speckle the LID adds:

    one paper, months apart      share 0.00213    1,077    hatches
    sRGB vs Adobe RGB in Luv     share 0.00369    1,820    hatches
    two different papers         share 0.01795       57    clean
    a paper against sRGB         share 0.02203      740    HATCHES

SO: the review's "that CIELUV pair draws cleanly" is the same mistake -- it is
the worst hatcher of the four, and the threshold is right to refuse it. Queue
item 3's second half is ANSWERED: not a fault.

BUT THE SHARE IS A PROXY AND A POOR ONE: the last row is ALLOWED and hatches
more than the two refused; the ordering does not even hold. A better rule
would ask how much of the LID ends up within a hair of the skin, which is
about two surfaces rather than one number between them. Anyone taking that
on: measure it on the four pairs above with `opacity=1.0`, and do not set a
threshold from a model -- three of mine were wrong that way.

⚠ AND THE LESSON THAT COST THE MOST THIS WEEK: every "I could not find it"
here has turned out to be an instrument that could not see it. Semi-
transparent shapes hid the hatching; a pink-pixel count hid the teeth; a
cosine hid a sideways slide. Before believing a negative, make the thing
appear on purpose first.


---

## THE SEAM IS FIXED AT THE DEFAULT AND NOT AT FULL OPACITY (2026-08-22, night)

> ⚠⚠ WRONG, AND CORRECTED IN 4470f70. The window does NOT default to 55%:
> `_shared` is opacity 1.0 (`gamut_app.py:7009`) and the slider's default is
> 100. The 55% only applies when the timeline panel owns the picture. So the
> hatching was the DEFAULT view, not one slider away from it.

HIS OWN PAIR, with the instrument that can see hatching:

    opacity 1.00    the lid adds 1,114 speckle    hatches
    opacity 0.55    the lid adds     76 speckle   clean

The window sets 55% itself the first time two shapes appear
(`_matched_the_shell_opacity`, gamut_app.py) -- so the picture he is SHOWN is
clean, and every OUTSIDE/INSIDE number in the commits is honest for it. One
slider away it hatches. Do not quote "OUTSIDE 348" without saying which.

THE HOLD IS NOT THE LEVER (measured, table in `close_the_cut`'s docstring):
no share keeps the narrow-pair volume within 5% AND clears the hatch, because
where two surfaces converge there is no room to hold a lid in.

### THE ONE THING LEFT TO TRY, and how not to repeat my mistake

Do not DRAW the lid where the gap is below what the PICTURE can separate.
That is a local form of TOO_CLOSE_TO_CLOSE. My first attempt (reverted in
a1c6111) used a share of the SHAPE, no picture, and withheld 97% of a lid on
sRGB against Display P3.

THIS TIME THERE IS AN INSTRUMENT: `scripts/show_the_hatching.py` draws a pair
OPAQUE and counts the speckle the lid adds. Calibrate the local threshold on
it, and hold any candidate to BOTH numbers:
  * the speckle the lid adds at opacity 1.0 (must fall)
  * how much of the lid is withheld (must stay small on every pair in
    `scratch/shy_probe.py`, which is where 97% showed up)
and check `two_sided.py` at the default opacity has not moved.


---

## THE HATCH IS NOT THE LID'S PAINT — IT IS THE LID'S DEPTH (2026-08-22, night)

Three levers tried against the hatching at opacity 1.0 on his own pair
(1,114 speckle the lid adds). ALL THREE DEAD, with numbers:

1. HOLD THE LID FURTHER UNDER THE SKIN -- see the table in `close_the_cut`.
   No share keeps the narrow-pair volume within 5% and clears the hatch.
2. WITHHOLD LID TRIANGLES WHOSE CORNERS HUG THE SKIN, calibrated small this
   time (diag/8000 .. diag/1000, i.e. a tenth to eight times the clearance):
   1,114 -> 1,096 -> 1,089 -> 1,067 -> 1,038. Nearly nothing, and the demo
   paper does not move AT ALL (737 throughout). The hatch is not there.
3. DRAW THE LID AFTER THE SHELLS instead of before: 1,114 both ways, to the
   pixel. Draw order is not it either.

⚠ AND WHY THEY ARE DEAD. Paint the lid pure red at opacity 1.0 and measure
the hatch INSIDE THAT RUN (not across runs -- a red lid breaks the depth ties
differently, and comparing one run's hatch against another run's pixels is
how I first got 13.6%):

    the hatch is 1,189 pixels, of which 219 are red -- 18.4%.
    the red lid covers 2,170 pixels of the whole 1600x1050 frame.

So the lid is very nearly INVISIBLE at full opacity and still adds ~1,000
speckle pixels, 81.6% of which show the SHELLS' colours. It is not painting
the hatch; it is writing DEPTH at the crossing surface and changing which
shell wins, pixel by pixel. Only 5.6% of the hatch is near a place the shells
already fight, so these are new fights, not amplified old ones.

THAT REFRAMES THE JOB: the remaining artifact is not "the lid looks wrong",
it is "a third opaque surface at the crossing changes how two nearly
coincident shells resolve". Anything that helps must either move the lid OFF
the crossing surface (no room -- lever 1) or stop it writing depth where it
is not seen (not expressible through the drawing library, as far as I know).
Worth asking whether the lid should be drawn at full opacity at all when the
shells are opaque -- the picture he is shown uses 55%, where it is clean.


---

## WHAT THE LITERATURE SAYS, AND THE FIRST NEW LEVER IN FIVE CYCLES
## (2026-08-22, night — Basti asked whether anyone has solved this already)

THEY HAVE, AND THE ANSWER NAMES OUR MISTAKE. Capping a clipped solid is a
classic problem. The three standard cures are:

  1. STENCIL-BUFFER CAPPING (SIGGRAPH '97/'99 course notes, "Capping Clipped
     Solids with the Stencil Buffer"): embed ONE capping polygon in the
     clipping plane and let the stencil trim it to the solid's interior.
  2. POLYGON OFFSET / depth bias (`glPolygonOffset`) for coplanar surfaces.
  3. Change the GEOMETRY so two surfaces are not in the same place --
     "merging coincident vertices, removing duplicate faces, or offsetting
     surfaces by a tiny amount".

NONE OF THE FIRST TWO IS REACHABLE HERE. Plotly's `mesh3d` exposes no stencil
and no polygon offset; the gl3d traces go through gl-mesh3d/regl and the trace
attributes are colour, lighting, flatshading and opacity. Cure 3 is the one I
have been attempting for five cycles, and the volume forbids it (see the table
in `close_the_cut`).

⚠ BUT NOTE WHAT CURE 1 ACTUALLY DOES: it caps with ONE surface. We draw the
other shape's skin TWICE -- once as its own shell, once as the lid laid a
median 0.116 Lab beneath it. That duplicate is the fight.

AND THE LID IS NOT REDUNDANT, which I checked before getting excited: with the
other shape drawn SOLID it still closes 426,841 pixels (more than the 317,929
with it drawn as a cage). The reason is the whole of it:

    THE LID IS AN OPAQUE COPY OF A SURFACE THE READER HAS FADED.
    At agree 45 the other shape's skin is see-through in the agreeing region,
    so the hole shows; the lid blocks it. Two surfaces in the same place at
    different opacities is a depth fight, and no offset this library exposes
    can settle it.

### THE LEVER THAT FOLLOWS, AND IT IS NEW

Do not ADD a surface to close the hole. Stop FADING the one already there.

The fade is per-vertex. The part of the other shape's skin that lies under
this shape's standing part could simply be kept at full strength, instead of
being faded and then covered by an opaque copy of itself. That is cure 1 in
this application's own terms: cap with ONE surface, the one that is already
in the scene, trimmed by the mask rather than by a stencil.

WHAT TO CHECK BEFORE BUILDING IT:
  * is the region "the other shape's skin under this one's standing part"
    exactly what `stands` already marks? If so this is a mask change, not a
    geometry change, and `cap_over_the_cut` could go entirely.
  * both numbers, as always: the hatch at opacity 1.0 (`scripts/
    show_the_hatching.py`) and what it closes (`scratch/two_sided.py`).
  * what it does to a saved page's fade, which reads the same masks.

SOURCES
  https://www.opengl.org/archives/resources/code/samples/sig99/advanced99/notes/node21.html
  https://www.opengl.org/archives/resources/code/samples/sig99/advanced99/notes/node20.html
  https://en.wikipedia.org/wiki/Z-fighting
  https://plotly.github.io/plotly.py-docs/generated/plotly.graph_objects.Mesh3d.html


---

## COULD WE WRITE THE POLYGON OFFSET OURSELVES? (Basti asked, 2026-08-22)

TECHNICALLY YES. The viewer is `plotly.min.js` from the installed package
(4,851,164 bytes, in the venv), inlined into every saved page by
`include_plotlyjs="inline"`. Its shaders are in there as readable source:
`gl_Position` appears 129 times, `gl_FragDepth` 3. A depth bias could be
injected by string surgery on that bundle.

I ADVISE AGAINST IT, for three reasons that are not about difficulty:

  1. IT WOULD APPLY TO EVERY mesh3d, NOT THE LID. Polygon offset has to be
     per-trace or it shifts everything equally and cancels. gl-mesh3d exposes
     no per-trace uniform we could key on, so the patch would need a new one
     threaded from the trace attributes through the bundle -- a fork of the
     library, not a patch.
  2. EVERY SAVED PAGE WOULD CARRY A MODIFIED VENDOR LIBRARY to whoever it is
     sent to. This application's whole point is handing a page to someone
     else; handing them a patched plotly is a different kind of promise.
  3. IT BREAKS ON EVERY plotly UPDATE, silently, in a 4.8 MB minified file.

WHAT IS CHEAP AND AVAILABLE INSTEAD, in the order I would take them:
  * ORTHOGRAPHIC CAMERA -- already measured: hatch 1,074 -> 408 for 37% of
    what the lid closes. It is one line and it is a reader's choice, so it
    belongs in the window as an option, not as a silent default.
  * LEAVE IT: the picture a reader is actually shown uses 55% opacity, where
    his own pair measures 76 speckle -- clean. The hatch needs the opacity
    slider at 100.
  * SAY IT: the lid's tooltip could name the one setting it does not survive.

⚠ AND WHAT IS NOT WORTH TRYING, measured, six levers, numbers in the source.


---

## THE SEAM: THE CAUSE WAS THE DEPTH BUFFER ALL ALONG (2026-08-22, 4470f70)

Not the lid's geometry. Not its colours, winding, shading, draw order, alpha,
or the threshold. THE DRAWING LIBRARY NEVER SETS A NEAR OR FAR PLANE: gl-plot3d
falls back to zNear 0.01 / zFar 1000 over a scene that is a unit cube, so
nearly all the depth precision is spent in empty space in front of the shapes.

⚠ AND THE DEPTH BUFFER HERE IS SIXTEEN BITS. `gl.getParameter(gl.DEPTH_BITS)`
through the window's own viewer returns 16, not 24. At 16 bits over that range
one step of depth is bigger than a Lab at the distance these shapes are drawn
from, so a lid laid a median 0.116 Lab under the skin CANNOT be told from it.
Everything else I measured for a week was downstream of that.

`_DEPTH_JS` (python/ti3gamut.py) fits zNear/zFar to the eight corners of
`glplot.bounds` along the view direction, chained on `onrender`, assigned
without a redraw. Product page, opacity 1.0, four cameras, speckle the LID
adds: 121 -> 2, 158 -> 5, 193 -> 17 and 34 -> 132.
⚠ THESE ARE THE CORRECTED NUMBERS. This line first read "121 -> 2,
158 -> 1, 193 -> 4, 34 -> 1", measured before the box was corrected in
f085156 -- which made the ONE CAMERA THAT GOT WORSE read as the best of
the four. Any number in this file taken before f085156 is suspect.

### TWO MEASUREMENT TRAPS THAT COST A WEEK, AND BOTH ARE STILL LIVE

1. ⚠ `fig.to_html(...)` IS NOT THE PRODUCT'S PAGE. It carries none of this
   application's scripts -- no `_ORDER_JS`, no `_spin_script`, and now no
   `_DEPTH_JS`. Every scratch driver that used it (`show_the_hatching.py`,
   `his_pair_hatch.py`, `does_it_hatch.py`, `lid_alpha_trade.py`, ...) was
   measuring a different page. The same pair: 740 speckle by that route, 707
   on a page a reader gets. USE `ti3gamut.write_html`.
2. ⚠ AND `write_html` LEAVES opacity=None, which `build_figure` turns into
   0.55 for a pair. THE WINDOW PASSES 1.0 (`gamut_app.py:7009`, slider default
   100 at `:11655`). A page written without `opacity=1.0` is not what a reader
   sees, and the hatching is invisible at 0.55. I told Basti the window
   defaulted to 55% -- it does not; `_match_the_opacity_to_the_shells` only
   fires when the timeline panel owns the picture.

`scratch/product_page.py` does both correctly and is the driver to copy.

### STILL OPEN
* The two SHELLS still fight each other (~3,500-4,400 speckle with no lid at
  all). Some of it WAS depth precision -- two cameras improved by ~470 and
  ~276 with the near plane -- but most survives. A review argues the rest is
  geometric: the two surfaces really do cross, and which is in front IS the
  answer the reader is reading, so biasing one would move the crossing curve
  and misreport a gamut's size. Do not "fix" it without settling that.
* The Plotly `join` error, 8 per redraw with the lid on (see earlier entry).
* No test pins `_DEPTH_JS` yet.


---

## THE TIMELINE'S OWN PICTURE GETS NEITHER SCRIPT (found 2026-08-22)

`TimelineDialog._draw` (`gamut_app.py:5431`) writes its view with a plain
`figure.write_html(...)`, not through `_write_dark_html`. So the picture in
that dialog carries NEITHER `_ORDER_JS` NOR `_DEPTH_JS`.

It matters because that dialog draws SEE-THROUGH SURFACES: `_cloud_figure`
(`gamut_app.py:5680`) goes through `build_figure`, and
`_match_the_opacity_to_the_shells` (`:16081`) exists solely to set those
shells to 55% — which is the exact configuration `_ORDER_JS` was written for.
The README says the far-to-near ordering applies to "both the window and every
saved page" (README.md:840); this is a picture inside the window that does not
get it.

⚠ NOT YET CONFIRMED ON SCREEN. This is read off the code, not photographed —
drive the timeline with a run of profiles and check
`typeof window.cqOrder` on its page before believing it, and before changing
anything. If it is real, the fix is to route that view through the same writer
the rest of the window uses rather than to inject the scripts a second way.

⚠ AND CHECK WHETHER THE README'S CLAIM HAS TO CHANGE TOO, or whether fixing
the dialog makes it true again. Prefer making it true.


---

## THE DEPTH FIX: WHAT A REVIEW FOUND, AND WHAT IS STILL OPEN (2026-08-22)

A hostile review of `_DEPTH_JS` returned "it regresses" and was right. Ten
faults; four are fixed, six are open. Fixed:

  * ⚠ THE PLANES WERE FITTED TO THE WRONG BOX. `gl.bounds` is the data's box
    BEFORE the model matrix and the camera sits after it, so the far plane cut
    the axis box away: 113,649 pixels erased from above, 256,077 along b*,
    axis titles printed twice. The drawn box is exactly ±aspect/2. Fixed in
    f085156; erased pixels along b* went 13,413 -> 28.
  * THE PAD had to change with it: it was a share of the VIEW-ALIGNED span,
    which collapses looking down an axis -- exactly where the tick text lives.
    It is half the box across now. ⚠ A wider pad brings the hatching back
    (0.9 of the box -> speckle 227/112/230/130), so this is a knee, not a
    free parameter.
  * MY TEST WAS CIRCULAR AND ALL ITS CAMERAS WERE DIAGONAL, where the error
    cancels. It checks the DRAWN box now and carries five axis-aligned eyes.
  * `_ORDER_JS`'s 82-line doc block had been annexed by `_DEPTH_JS` (no blank
    line between them). Given back in 3d42e9d.

### STILL OPEN, worth doing in this order

1. ⚠ ONE CAMERA IS WORSE THAN NO FIX AT ALL. Seen from below the lid's own
   speckle is 132 against 34 with the planes left alone; the other three are
   2, 5, 17 against 121, 158, 193. Not explained. Find out whether it is the
   fix or a pre-existing fight it exposes before claiming the seam is done.
2. THE 25 PAGES IN `docs/pages` STILL CARRY THE OLD RENDERING -- 25 of 25 have
   `window.cqOrder`, 0 of 25 have the depth script. They are what the README
   points a reader at. Regenerating them is a big diff; check first whether
   the pictures actually change.
3. `Plotly.toImage` -- THE PNG BUTTON -- DOES NOT GET THE FIX. A review
   measured 0 pixels different between fitted and unfitted planes on an
   exported image: it renders a clone with no chain. Anything a reader saves
   as a picture still hatches.
4. THE TIMELINE PANEL (`gamut_app.py:5431`) writes with a plain
   `figure.write_html`, so it gets neither `_ORDER_JS` nor `_DEPTH_JS` --
   measured `armed:false, zNear:0.01`. It is the one panel whose shells are
   deliberately see-through.
5. SETTLED, AND MY CLAIM WAS WRONG. I said `write_slice_html` "gets neither
   script". It gets BOTH -- a cross-section page carries `cqOrder` twice and
   `__cqDepth` five times -- because it writes through `_write_dark_html`,
   which injects them. My check had read only the function's own body with
   `ast`, not what it calls.
   AND THE SCRIPT CORRECTLY DOES NOTHING THERE: asked of the running page,
   `scenes: 0`. A cross-section is flat, there is no depth buffer to fit, and
   the picture is two overlapping polygons with axes and a key
   (`scratch/slicearms/slice.png`). Nothing to do.
6. THE "98-99% GONE" IN 4470f70 OVERSTATES IT. The before column reproduces
   exactly; the after column does not (a review measured 1/13/3/11 against the
   claimed 2/1/4/1). Re-take on `write_html` pages at three or more cameras
   before quoting it anywhere a reader will see.

⚠ AND THE PAD WAS CHOSEN FROM FIVE CAMERAS ON ONE PAIR. It is the least
justified number in the change.


---

## THE NO-VIEWER EXPORT IS STILL UNPROVEN ON A REAL PAGE (2026-08-22)

Basti asked whether the depth fix reaches the exported web files, "especially
the ones without the viewer included". Measured:

    with the viewer inlined   6,232,347 bytes   armed, planes 0.71 / 4.49
    without it                1,389,727 bytes   the script IS in the file

⚠ BUT THE SECOND ONE HAS NEVER BEEN SEEN TO WORK. In a QWebEngineView here the
viewer never arrives and the page shows its own notice, "The 3D viewer did not
arrive". `curl` fetches the same URL in 2.7 s and 4,851,164 bytes, so the
machine IS connected and it is QWebEngine's fetch that does not complete. The
fix for a LATE viewer (the sweep now runs until a scene is armed rather than
for ten seconds) is proved only in a node harness -- viewer landing at sweep
0, 5, 100 and 400 -- not on a page that really downloaded one.

TO FINISH IT: open `scratch/cdnreal/cdn.html` in a real browser (Safari or
Chrome, not the embedded view) and check
`gd._fullLayout.scene._scene.glplot.onrender.__cqDepth` in its console. One
minute of work, and it is the only way to be sure the file people are actually
sent carries the fix.

⚠ AND A LESSON ABOUT MY OWN DRIVERS. This ran for forty seconds reporting
"nothing drawn yet" while the window said, in plain words, why. I had saved
the screenshot and not looked at it. The drivers now return the page's own
visible text when they cannot find a figure, and START-HERE says to look
before concluding.


---

## ZOOM IS CLEAN (2026-08-22, `scratch/zoom_check.py`)

The planes are fitted every frame, so zoom was the case least sure of. Same
direction, seven distances, his own pair, pixels the library drew that the
fitted planes erase:

    0.30x (eye inside the shape)   0.0010 / 2.6677    erased 0
    0.55x                          0.0010 / 3.3172    erased 1
    0.90x                          0.4499 / 4.2265    erased 6
    1.30x                          1.4891 / 5.2657    erased 2
    2.60x                          4.8665 / 8.6431    erased 5
    5.00x                         11.1017 / 14.8783   erased 2
    12.0x                         29.2877 / 33.0643   erased 2

Pulled right in the near plane clamps and nothing is lost; pushed far out the
range tightens to 1.1:1 against the library's 100,000:1.

⚠ AND THE THIRD INSTRUMENT ERROR OF THE SAME FAMILY. The first run of this
reported 0.0100 / 1000.0000 at EVERY distance, which reads exactly like the
fix never applying. It was the driver: it loads the fitted page and then the
unfitted one, and asks the page that loaded LAST. Ending the loop on the
fitted page fixed it. Every "the fix did not work" and every "I could not find
it" in this whole week has been the instrument, not the code -- semi-
transparent shapes hid the hatching, a pink-pixel count hid the teeth, a
cosine hid a sideways slide, a page written by `fig.to_html` was not the
product's page, and now a readout of the wrong page. CHECK WHAT THE
MEASUREMENT IS POINTING AT BEFORE BELIEVING WHAT IT SAYS.


---

## THE "FROM BELOW" CAMERA: THE FLAG IS REAL AND STILL THERE (2026-08-22)

The one camera where the depth fix left things worse (speckle the lid adds:
132, against 34 with the planes left alone) has now been LOOKED AT rather than
counted: `scratch/px-0.5/low-pair.png`.

IT IS A TRIANGULAR FLAP. A pale wedge with dotted edges projects above the
surface along one edge, where the lidless picture is clean. That is the "row
of triangular flags" the job description names -- so the seam artifact is NOT
fully cured, and this camera is where what remains of it shows.

WHY THE FIX MADE IT WORSE, most likely: with the depth buffer given its
precision back, a lid triangle that genuinely sticks out now WINS RELIABLY
instead of flickering. The fix did not create the flap; it stopped hiding it
behind a fight.

⚠ AND IT IS NOT RADIAL POKE-THROUGH. Measured on his own pair with 120,000
samples: 0 of 8,000 triangles of the printer's lid are outside its own skin,
and 1 of 7,999 of sRGB's, worst +0.0002 Lab. The lid is where it belongs
ALONG EVERY RAY FROM THE MIDDLE.

SO THE INSTRUMENT CANNOT SEE IT, AGAIN. A ray from the middle asks how deep a
point is along that ray. A flat lid triangle strung across a concave part of
the rim sticks out AT THE SILHOUETTE -- sideways, past the edge of the shape
-- and no radial test asks about that. Whoever takes this next: measure the
silhouette, not the radius. Render the lid alone against the piece alone and
compare outlines, or test each lid triangle against the piece's surface by
distance rather than along a ray.

It is 132 pixels at one camera, so it is small -- but it is the ORIGINAL
FAULT, and it is the reason not to claim the seam is finished.


---

## THE FLAP MEASURED AT LAST: SEVEN TRIANGLES (2026-08-22, `scratch/flap.py`)

Asked WITHOUT assuming the shape is star-shaped about the middle -- count
crossings along an arbitrary direction, odd is inside -- on his own pair:

    printer's lid   8,000 triangles,   0 with their middle outside the piece
    sRGB's lid      7,999 triangles,   7 outside  (0.09%), sitting
                    46.5..93.8 Lab from the middle of a shape spanning 132.8

THE RADIAL TEST FOUND NONE OF THEM. `_where_the_ray_leaves` from the middle
asks one distance per direction, which is only meaningful if the surface is
star-shaped about that middle; where the rim is concave a flat lid triangle
strung across the dent sticks out SIDEWAYS and every radial test says it is
fine. Two of them did, at 120,000 samples.

⚠ THIS IS THE ORIGINAL FAULT -- "a row of triangular flags where the lid meets
the skin" -- and seven triangles is the right size for the single flap
photographed from below (`scratch/px-0.5/low-pair.png`, 132 speckle pixels).

### HOW TO FIX IT, and what to check

Withhold or pull back those triangles in the DRAWN copy only, exactly as the
tuck does, so `close_the_cut` still hands back a closed solid and the volume
is unaffected.
  ⚠ CHECK FIRST whether any of the seven owns a SEAM edge. Dropping one that
    does opens the seam, which is the fault the seam guard exists to stop.
  ⚠ AND HOLD IT TO THE THREE NUMBERS: the flap gone from the picture at the
    "from below" camera (132 -> ?), nothing withheld on the reference pairs in
    `scratch/shy_probe.py` (a broad withholding rule took 97% of a lid once),
    and `two_sided.py` unmoved at the default.
  ⚠ AND SEVEN IS A SMALL POPULATION. A rule that fires on seven triangles of
    16,000 must be shown to fire on the RIGHT seven -- render the lid alone
    with those triangles coloured, and look.


---

## THE FLAP FIX: DIAGNOSIS COMPLETE, IMPLEMENTATION HAS TWO CONSTRAINTS
## (2026-08-22, `scratch/flap.py`, `scratch/flap_detail.py`, worktree
## `scratch/flapfix`)

WHAT THE SEVEN ARE, on his own pair (sRGB's lid, 7,999 triangles):
  * NONE owns a seam edge -- so dropping them cannot reopen the seam, which
    was the first guard.
  * ALL SEVEN ARE AT RING 1 FROM THE RIM. The flap is a rim phenomenon,
    exactly as the fault description says: "where the lid meets the skin".
  * three pairs share an edge, and they span 109.7 Lab -- so THREE PLACES,
    not one.
  * their area is 1.64 of 24,133 Lab^2: 0.007% of the lid.
  * the printer's lid has none at all.

A FIRST IMPLEMENTATION IS IN `scratch/flapfix` AND IS NOT READY, for two
reasons that measurement found:

  1. ⚠ IT MUST RUN AFTER THE TUCK, NOT BEFORE. Placed before, it drops 15
     triangles instead of 7 -- the tuck pulls the rim in by ~0.7 Lab, which
     pulls some of them back inside. Judge the geometry that is actually
     DRAWN.
  2. ⚠ IT COSTS 12.7 SECONDS FOR BOTH LIDS, against about 2 before. The
     crossing test is 8,000 points x 9,192 faces x 2 directions. That is far
     too slow: `cap_over_the_cut` is on the path of a first draw.

     THE WAY OUT IS RING 1. Every one of the seven is one ring from the rim,
     so the test never needs to run over the whole lid. Rings 0-2 would cover
     them with a fraction of the work; a spatial bucket over the piece's faces
     would cut it much further.

⚠ AND THE THIRD GUARD IS STILL UNDONE: colour those triangles and LOOK, to
prove a rule that fires on seven of eight thousand fires on the RIGHT seven.
Then the three numbers: the flap gone from the "from below" camera (132 -> ?),
nothing withheld on `scratch/shy_probe.py`'s reference pairs, and
`two_sided.py` unmoved at the default.


---

## THE FLAP FIX: CORRECT, AND STILL TOO SLOW (2026-08-22)

The version in `scratch/flapfix2` (worktree removed; the diff is described
here in full) withholds EXACTLY the right triangles:

    printer's lid   8,000 drawn,  0 withheld
    sRGB's lid      7,992 drawn,  7 withheld

matching `scratch/flap.py`'s independent count. Two constraints from the
previous attempt are met: it runs AFTER the tuck, and it only tests triangles
within one ring of the rim, which is where every one of the seven is.

⚠ WHAT STOPS IT SHIPPING IS THE COST.

    baseline (no test)                 3.9 s for both lids
    whole lid, two directions         12.7 s
    rings=2, two directions            8.2 s
    rings=1, two directions            7.4 s
    rings=1, ONE direction             6.0 s

+3.5 s on a first draw is too much for a feature meant to be on by default.

⚠ AND DO NOT BUY THE LAST 1.4 SECONDS BY DROPPING THE SECOND DIRECTION. It is
there because a ray that grazes an edge is miscounted, and a miscount there
calls an INSIDE triangle outside -- which puts a hole in the lid. A slow draw
is better than a hole.

### THE OPTIMISATION THAT IS LEFT

The cost is faces, not points: every candidate is tested against all 9,192 of
the piece's triangles. For a FIXED direction, a face can only be crossed by
the ray from P if P's projection onto the plane perpendicular to that
direction falls inside the face's 2D extent. Bucket the faces into a grid over
that projection once per direction, and each point tests tens of faces instead
of nine thousand.

That is the whole remaining work, and it is ordinary. Everything about WHICH
triangles to drop is settled and measured.


---

## THE WALL THAT COMES IN FRONT OF THE SHAPE (2026-08-23) — REPORTED BY BASTI,
## CAUSED BY THE DEPTH FIX, MECHANISM SETTLED

He reported it twice, and both reports were right:

> "for this one the wall were placed very weird"
> "they are in the box only the walls move in front of it sometimes"
> "so far i did not see it in your stills but only in the moving ones"

HE IS RIGHT ABOUT THE STILLS TOO. At 24 cameras round the orbit with the spin
STOPPED, the walls cover at most 26 pixels of the shape — nothing. It is only
ever seen moving because the fault lives in a band of camera azimuth under a
degree wide, and a spinning page crosses it in a few frames.

### IT IS MINE. The numbers, at one camera, spin stopped, camera read back and
### verified equal to 1e-6:

    wall pixels drawn over the shape     before the depth fix        1
                                         after  the depth fix    2,386

`docs/pages/22-a-run-with-its-shapes.html` against its own committed copy from
before `4f3b6fd`. 2,149 of those 2,386 pixels are exactly #141414, which is
`SCENE_COLOURS["dark"]["plot"]` — the wall background — sitting on top of the
gamut. Turning the x wall off through relayout takes it to 100.

### THE MECHANISM, AND IT IS ARITHMETIC

gl-plot3d paints one of each axis's two faces, and which one is in
`glplot.axes.lastCubeProps.axis` as a sign per axis. Painted on the face the
CAMERA IS ON, the wall is in front of everything:

    the wall is wrong  <=>  axis[i] * eye[i] > 0

Swept through the band with the spin stopped, eleven cameras, the rule against
the pixels:

    eye y      axis        rule       pixels covered
    -0.300   [ 1, 1,-1]    clean            0
    -0.150   [ 1, 1,-1]    clean            1
    -0.080   [ 1, 1,-1]    clean            0
    -0.040   [-1, 1,-1]    COVERED      2,377
    -0.017   [-1, 1,-1]    COVERED      2,387
     0.000   [-1, 1,-1]    COVERED      2,388
     0.017   [-1, 1,-1]    COVERED      2,394
     0.040   [-1, 1,-1]    COVERED      2,420
     0.080   [ 1,-1,-1]    clean            2
     0.150   [ 1,-1,-1]    clean            0
     0.300   [ 1,-1,-1]    clean            0

ELEVEN OF ELEVEN. The camera's x never moves — it is fixed at -2.0166 — and
the library still flips the X face as Y crosses zero, which is why the band is
where it is.

⚠ THE FIX DID NOT CREATE THIS, IT STOPPED HIDING IT. With the library's own
0.01/1000 over 16 bits, one depth step is bigger than the whole scene, so
nothing was ordered by depth at all and the shape won by draw order. Given its
precision back, the near wall correctly wins — over a wall the library should
not have painted. The same sentence covers the "from below" flap: the fix did
not make either fault, it stopped a fight that was hiding them.

### WHAT WORKS AND WHAT DOES NOT

    Plotly.relayout(gd, {"scene.xaxis.showbackground": false})   2,386 -> 100
    glplot.axes.backgroundEnable[0] = false, then a forced frame  2,386 -> 2,386

The second does nothing: the library re-applies that array from the layout on
every frame, so the only lever is relayout.

⚠ AND A RELAYOUT PER FRAME IS NOT OBVIOUSLY SAFE. His very first screenshot
was of a driver of MINE that called `Plotly.relayout` for the camera while the
page's own spin was also writing it; the frames in between are on neither
path, and that is what "the walls were placed very weird" was. Any cure that
relayouts on a spinning page must be photographed on a spinning page before it
is believed. Toggle only on the verdict CHANGING (about eight times a
revolution), never every frame, and remember each axis's ORIGINAL
`showbackground` so a page saved with the walls off is not given walls.

### THE INSTRUMENT, and it took four tries

`scratch/wallover.py` — wall grey with shape colour on both sides ACROSS it.
Three earlier versions each looked like a clean result and were not:

  * counting coloured pixels frame to frame measured the SPIN (a shape turning
    "loses" 10,921 pixels between two frames three apart);
  * asking for colour on all FOUR sides can never fire on a line of any
    orientation — what is above a vertical line is the line;
  * and the sensitivity check that was supposed to catch that pasted a 94-pixel
    SLAB, whose middle has no colour within five pixels either side, and
    concluded the check was blind when the test was.

It now proves itself on a pasted line before it reports anything, and the
run stops if that proof fails.

⚠ ALSO FOUND BY A CHECK THAT EARNED ITS KEEP: `str(np.float64(1.6))` is
`"np.float64(1.6)"`, which is not JavaScript. A driver built its camera from
`round(1.6*np.cos(t), 4)` and every `Plotly.relayout` was silently a no-op, so
24 cameras of numbers were all taken at whatever camera happened to be there.
Caught only because the camera is read back and compared to what was asked.
Read the camera back, always.


---

## THE WALL IS CURED (2026-08-23, `b987731`)

The rule from the entry above is now in `_DEPTH_JS`. Only when the verdict
CHANGES does it relayout that axis's `showbackground` off, and only for an
axis that had one — a page saved with the walls off is never given walls.

MEASURED ON A TURNING PAGE, which is the only place it matters and the only
place a relayout could do harm:

    frames with a wall over the shape   110 of 320   ->   3 of 320
    blank frames                                 0   ->   0
    camera step, max over median              1.4x   ->   2.1x

A barely visible hitch about eight times a revolution, against a third of all
frames having a wall across the gamut. The three that remain are the frame
the band is entered on, where the relayout lands one frame late.

⚠ IT DOES NOT HAPPEN ON HIS OWN PAIR AT ALL. His profile against sRGB, the
same eleven cameras: at most 17 pixels covered, rule or no rule. A cure
measured only on his pair would have reported a clean result from a picture
that never had the fault — which is the same shape of mistake as a check that
cannot see.

⚠ AND THE BLOCK WENT INTO THE WRONG SCRIPT FIRST. `function arm(gd) {` occurs
TWICE in `ti3gamut.py` and a string anchor took the one in
`_LINK_CAMERAS_JS`. It parsed, and 20 of 24 tests passed. Caught only by
asserting `var SIDES` was in `_DEPTH_JS` afterwards. Both neighbours are now
asserted byte-identical after any such move. START-HERE already says to print
the enclosing `def` before editing; this is the same rule for a string
anchor — CHECK THE ANCHOR IS UNIQUE.

⚠ AND A THRESHOLD THAT FAILS ON A WORKING CHECK IS THE SAME FAULT AS A CHECK
THAT CANNOT SEE. `scratch/wallover.py`'s proof demanded a flat 150 and got
126 on a shorter pasted line, so it stopped a run in which it had plainly
worked. It scales with the line it pastes now.


---

## WHAT IS LEFT BEFORE A RELEASE (2026-08-23)

1. A hostile subagent has NOT yet seen the finished seam. That is the
   release criterion in the job description and it is not met.
2. From the hostile review of the depth work, two findings are still open and
   both are real:
   * `fit()` can be deleted from inside the render wrapper and all 1,117
     tests stay green. The planes then freeze at the camera the page armed
     at, and about a dozen wheel notches in, the near plane cuts the front
     off the gamut — silently. THE ENTIRE PER-FRAME MECHANISM IS UNTESTED.
   * the 250 ms sweep period is held by nothing: both node harnesses throw
     the delay away, so `}, 250)` can become `}, 10)` — which re-creates the
     bug e1d2650 fixed — or `}, 20000)`, with the file green.
3. The flap rule ships but changes no pixel anybody can find (see the entry
   above); that is written into its commit message and should stay written.

---

## WHAT IS LEFT BEFORE A RELEASE (2026-08-30) — the 2026-08-23 list is DONE

All three items from the 2026-08-23 list are closed:

1. ~~a hostile subagent has not seen the finished seam~~ — four have, and they
   found more than the seam.
2. ~~`fit()` deletable with all tests green; the 250 ms sweep held by nothing~~
   — both pinned by
   `python/test_the_depth_fix_does_not_stop_after_the_first_frame.py`, each
   mutation run on every gate and asserted to have landed.
3. the flap rule still changes no pixel anybody can find; that stays written
   into its commit message.

### ⚠⚠ AND THE BIG ONE, WHICH THE RECORD HAD BACKWARDS

The record said the depth fix "did not create the wall fault, it stopped hiding
it". **It CAUSED it.** gl-plot3d picks which of each wall's two faces to paint
by orienting against the NDC origin, whose pre-image sits `2nf/(n+f)` in front
of the eye — so it MOVES WITH THE PLANES WE SET. Fitted symmetrically about the
box it landed INSIDE the box, the orientation test went ambiguous over wide
arcs, and the library fell through to a projected-area tie-break that paints
the bigger-looking — i.e. NEARER — face.

    page 22, 240 turning frames, a wall shown on the camera's own side
    our old fit, no wall rule ............ 81/240   33.8%
    the fit as it is now ................. 5/240    2.1%
    stock library, no fit at all ......... 4/240    1.7%   <- the control

`fit()` now keeps that point at 0.4 of the distance to the nearest corner.
γ anywhere in 0.2..0.9 gives identical picks — a plateau, not a knife edge.
THE WHOLE WALL RULE IS DELETED (~90 lines).

⚠ AND PATCHING THE BUNDLED PLOTLY WAS REFUSED FOR A REASON WORTH KEEPING: a
page saved WITHOUT the viewer fetches an unmodified plotly from the CDN when
its reader opens it, so nothing patched into our own copy could ever reach the
file that travels furthest from here. Basti asked for exactly that case. All
four exports are proved by screenshot, the no-viewer ones verified to have
really fetched `https://cdn.plot.ly/plotly-3.7.0.min.js`.

### THE OTHER FIVE, all fixed

* FOUR PUBLISHED PAGES had NEITHER `_DEPTH_JS` NOR `_ORDER_JS` — 15, 16, 17,
  19, the timeline pages. They are NOT 2D line graphs; a review said so and was
  wrong. `TimelineDialog.page_html` writes its page by hand, and its own
  comment already recorded that this is "how four published pages came to have
  no such script at all". All 25 carry everything now.
* KNUT'S REPORT: "184 on the edge" printed one line above "every patch sits
  inside", in BOTH judging branches. Root cause is Argyll's tessellation chord
  error (predicted 0.069 median vs 0.0696 observed), not a fault here.
* A page saved without walls regained them at load (`applyPicture` forcing
  hardcoded defaults) — and my first fix for it CLOBBERED the reader's
  remembered choice, which a regression check caught.
* A page saved orthographic opened perspective: `setCam` dropped `projection`.
* An invisible axis read as a grid, so the button opened pressed over a
  boxless page.

### ⚠ THE VEIN THAT PAID BEST THIS WEEK: A CHECK PINNING THE FAULT

Five times, most sharply `test_a_patch_too_close_to_see_is_on_the_edge...`,
which asserted a verdict said BOTH "1 on the edge" AND "every patch sits
inside" of the same message. The check was not missing Knut's fault; it was
DEMANDING it. **When a test fails after a fix, ask which of the two is wrong.**

### AND THE INSTRUMENT LEDGER GREW AGAIN

`cqSpin` has no `stop()` (use `set({on:false})`); `gl.camera.eye` is not the
layout camera; a thin-line detector cannot see a slab; `sys.argv` emptied for
Qt BEFORE the argument is read silently measures the default page; a page
written without `spin=` carries no `cqSpin` at all, so "turning" frames are
identical stills; and `show_the_hatching.py`'s speckle counter both MISSED real
hatching and FLAGGED phantom hatching (1064 -> 161 run to run). Basti's rule —
diagnose from screenshots, and if a number and a picture disagree the picture
is right — was vindicated six times in one session.

### WHAT IS ACTUALLY LEFT

1. The release: bump, CHANGELOG, tag, push, confirm 11 assets. Notes drafted at
   `scratch/CHANGELOG-2.53.0-draft.md`.
2. STILL BASTI'S DECISION: the 30-second black window on a slow download.
3. NOT BUILT, DESIGNED ONLY: the full audit tool he asked for —
   `docs/DESIGN-the-full-audit.md`, with nine numbered open questions he has
   not answered yet. `scripts/audit.py` already discovers controls dynamically
   and `drive_all_combinations.py` already crosses 6,912 combinations; what is
   missing is a single entry point and a friendly report on his Desktop.
