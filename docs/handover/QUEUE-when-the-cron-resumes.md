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
