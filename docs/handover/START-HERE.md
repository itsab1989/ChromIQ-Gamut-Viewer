# START HERE — everything a new session needs to carry this on

Written 2026-08-20 for a fresh session, because the old one had grown slow.
Nothing in here assumes you remember anything.

**Read this file, then `QUEUE-when-the-cron-resumes.md` beside it, in full.**
The queue carries the ten things Basti reported from his own first hands-on
session, each with the diagnosis already made and the traps already met. Do
not re-derive them.

---

## 1. Where everything is

| | |
|---|---|
| repo | `~/develop/ChromIQ-Gamut-Viewer/fork` (branch `master`) |
| origin | `itsab1989/ChromIQ-Gamut-Viewer` |
| venv | `~/develop/ChromIQ-Gamut-Viewer/gv-venv/bin/python` — used as `../gv-venv/bin/python` from the repo |
| handover | this file and `QUEUE-when-the-cron-resumes.md`, one level up from the repo |
| scratch | `~/develop/ChromIQ-Gamut-Viewer/scratch` — **use this, not `/private/tmp`** |

### ⚠⚠ GREP FINDS THE STRING. ONLY READING WHICH FUNCTION HOLDS IT FINDS THE
### RIGHT ONE.

Threading one argument through the two-room save took three wrong edits, each
of which IMPORTED CLEANLY:

* a call edited in `_write_two_slices` believing it was `_write_two_rooms`
  (two calls to the same writer, 118 lines apart);
* `carry_viewer=carry` written where no such name existed;
* `include_plotlyjs` changed in `write_two_views_html` believing it was
  `write_side_by_side_html` — leaving that function reading a parameter it did
  not have.

The habit that catches all three: after locating a line, print the enclosing
`def` before editing it, and RUN the thing afterwards. Importing a module is
not running it.

### WHAT THAT FIX WAS — and it was a control that lied

"Put the 3D viewer inside the file" was offered on a two-room page and the
answer thrown away: 5,149 kB either way, and never the did-not-arrive notice.
Now 419 kB, both rooms drawn, the movement strip intact. Two cross-sections
had the same fault from the other direction. Shipped in v2.50.2.

### ⚠⚠ I SHIPPED A RELEASE NOTE THAT WAS NOT TRUE OF ITS OWN CODE — v2.50.0

Its notes said the page "tries the next address when the last one refuses".
Nothing called the walk at all, except a forty-five second last resort. The
whole feature was dead code and **every string test of it stayed green,
because every string was still there.**

AND I BROKE IT MYSELF, in the commit that moved the notice above the viewer's
tag. The walk began at `if (!window.Plotly && window.cqNoViewerWanted)` and
that flag is set ONLY when the notice div does not yet exist. Move the div
above the tag and it is never set. A one-line consequence of a change I made
for an unrelated reason, invisible to the suite. Corrected in v2.50.1.

⚠ AND THE MEASUREMENT I BUILT THE DIAGNOSIS ON WAS WRONG. I reported that a
dynamically added script "is never fetched while a parser-blocking script is
pending" and reasoned from it for a whole cycle. Measured properly — a
blocking script hanging five seconds, an inline script appending another after
one — the added script is requested at 1.290 s and RUNS. The browser was fine;
my probe was not. **Before building on a surprising measurement, make the
smallest possible case that isolates it.**

### ⚠⚠ A STRING IN THE HTML IS NOT A PICTURE ON THE SCREEN.

The did-not-arrive notice was written

    <div id="cq-noviewer" hidden style="position:fixed;inset:0;display:flex;…">

and `hidden` LOSES to an inline `display`: the browser's rule is
`[hidden] { display: none }` at ordinary specificity, and an inline style beats
it. So the notice was on screen from the moment the parser reached it, FOR
EVER, and `n.hidden = true` was a no-op. **The picture was drawn and intact
behind an opaque sheet** — the plot at 1,314 ms, the notice covering it at
1,365 ms. Fifty-one milliseconds of picture.

Reported as "i see the shape a split second and then the message is back", and
as a retry button that did nothing — which it could not, the viewer being
already there. I diagnosed it as a CACHING problem for three rounds and was
wrong every time.

⚠ EVERY TEST OF THAT PAGE PASSED THROUGHOUT. They ask whether words appear in
the HTML and every word was correct. **Only rendering the page and asking the
browser what it COMPUTED could see it.** That is
`scripts/audit_the_notice_really_hides.py`; it is a script and not a test
because a QWebEngineView built inside the suite segfaults the whole run
(exit 139, a thousand passing tests thrown away).

⚠ AND A PARSER-BLOCKING `<script src>` FREEZES EVERYTHING AFTER IT. With a
first address that never answers, the fallback appends the next script to the
DOM and **the server is never asked for it** — a dynamically added script is
not fetched while a blocking one is pending. So during a HANG there is no
recovery at all, and `#cq-draw` (after the tag) is never parsed either.
Measured, not reasoned.

### ⚠⚠ `pytest -q | tail` HIDES A FAILING GATE. USE `set -o pipefail`.

A pipeline's exit code is the LAST command's, so `pytest -q | tail -2` reports
what `tail` did — always success. Every

    pytest -q | tail -2 && git commit ... && git push

in this work therefore committed and pushed whatever the gate said. It went
out red once, with two failing tests, and nothing warned. Start any gate line
with `set -o pipefail`, or read the exit code and print it.

### ⚠⚠ NEVER PUT A SHELL VARIABLE IN AN `rm` PATH. IT STOPS EVERYTHING.

`rm -f $SP/*.html` asks for confirmation — "Dangerous rm operation on
possibly-empty variable path" — because an empty `$SP` makes it `rm -f
/*.html`. The run then BLOCKS until somebody presses a key. **This has cost
Basti two nights: he went to bed with work queued and found it stopped on a
prompt, seven hours wasted the second time.**

Write the whole path out, every time:

    rm -f /Users/Basti/develop/ChromIQ-Gamut-Viewer/scratch/thing/one.html

or delete from Python, where nothing can expand into `/`:

    python3 -c "import pathlib; [p.unlink() for p in pathlib.Path('/Users/…/scratch/thing').glob('*.html')]"

The same goes for `rm -rf` with a variable, and for any command that can stop
and wait. **If something might prompt, it must not be run unattended.**

⚠ That scratch folder already holds **764 MB in 667 files** of probe output
from earlier sessions — meshes, `.npy` arrays, one-off scripts. Nothing in it
is needed to build, test or release; it is kept only because a few probes were
expensive to produce. Basti mentioned his disk filling up, so it is worth
telling him it is there. **Do not clear it without asking** — some of it is
the evidence behind answers in the queue.

Both gates, from inside `fork`:

```bash
../gv-venv/bin/python -m pytest -q
GAMUTVIEW_NO_ARGYLL=1 ../gv-venv/bin/python -m pytest -q
```

At the time of writing: **1017 passed**, and **1013 passed + 4 skipped**.
Version **2.52.1** (released, 11 assets). **THE CRON JOB WAS STOPPED HERE,
2026-08-22, at his word.** To carry on, paste `KICK-OFF.md` (this folder, his
Desktop, and fork/docs/handover/) into a new session: it carries the method as
well as the state.

Ten releases: v2.49.0, v2.50.0,
v2.50.1 (correcting a false claim in v2.50.0), v2.50.2, v2.50.3, v2.50.4,
v2.50.5, v2.51.0 and v2.52.0.

⚠ **ASK A SHAPE WHOSE ANSWER IS ARITHMETIC.** He asked for demo files built to
expose faults, and they are the best instrument in this repository. An
ellipsoid has an exact volume and two of them meet in an exact ellipse, so a
number can be wrong in a way no opinion can argue with. What it found:

* the cut converges properly (0.51% -> 0.03% as the mesh refines), which
  RETIRED my claim that the seam wobbled -- I had compared an ellipse against
  a circle;
* the volume is honest and its error is counting: -3.0% at 400 patches,
  -0.06% at 20,000, so two charts of one paper differ by 2.3%;
* coverage lands inside the ± it prints, and that ± is not decoration;
* **and the drift comparison was keeping one of every repeated patch**, so a
  chart re-saved in another order was a different reading. Fixed in v2.52.0.

⚠ **AND CHECK THE CLAIM THE CODE ITSELF MAKES.** The drift fault was found by
testing the docstring's own promise -- that patches are paired on DEVICE
values and not on the sample number -- with a shuffle. My first idea (move
every patch equally and expect equal distances) was simply wrong: CIEDE2000
weights by chroma and hue.

⚠ **A SAVED PAGE'S HEAD IS BUILT IN FOUR PLACES**, and nothing in the code
makes them visible to each other: `_write_dark_html`, `write_two_views_html`,
`write_side_by_side_html` (all in ti3gamut) and `page_html` in gamut_app for a
run. One line added to the obvious one looked complete and covered **19 pages
of 25**. The rest were found by counting the files on disk. Anything that
belongs in every saved page needs all four, and
`test_a_saved_page_says_what_to_paint` now checks the ARTIFACTS rather than
one writer.

⚠ **THE CAP WAS ATTACKED AND SIX FAULTS CAME OUT**, all fixed in v2.51.0: a
lid built in the wrong place (a copy of the shape's own skin, 5.9 Lab adrift,
which I had cited as proof it worked); a lid between shapes closer than 1 Lab,
which can only speckle; a lid left drawn over a shape faded to nothing; a lid
with no standing mask, so a saved page could not fade it; a tick offered where
nothing can be closed (including the demo pair); and a tick dimmed where a lid
WOULD be drawn, because the rule never read `_style_other`. It is still off by
default: with it on the seam shows the triangles of the shape the lid is cut
from, and raising **Detail** shrinks them.

⚠ **A FOLDED GROUP IS NOT A MISSING CONTROL.** Measuring Detail's availability
in a fresh-preferences window read `isVisible() == False` in EVERY state,
including the one where the slider demonstrably works — and that nearly had a
correct fix reverted as pointless. Six groups start folded; `audit_panel`
opens them first for exactly this reason. Unfolded, the row is shown in all
four states and only its ENABLED flag differs.

⚠ **AND FOUR OTHER INSTRUMENTS WERE WRONG BEFORE ONE WAS RIGHT**, all in the
same investigation, all failing towards a tidy answer: a run that compared 40
with 40 because the scratch preferences carried the value between windows; a
change-detector that fired on the slider's own number redrawing in the panel;
a picture comparison that counted antialiasing; and a `grab()` of a rectangle
with negative coordinates, which returns a null pixmap and a `save()` that
quietly answers False. What settled it asks the built shape for its FACE COUNT
and never looks at pixels at all.

⚠ **ASK THE QUESTION IN THE STATE HE IS IN, NOT THE ONE THE WINDOW STARTS
IN.** v2.50.3's shortened hovers grew back the moment a tickbox was turned on
— 188 characters to 946, and a menu to 2,132 — because several controls keep a
copy of their own tooltip taken before the shortening pass runs. Every check
that looked at a freshly-opened window said Clean. Two papers open and the
tickboxes on is where it showed. Fixed in v2.50.4; the rule that catches it is
in `scripts/audit_the_panel_hovers_stay_short.py`, and it had to stop skipping
hidden controls before it could see the very fault it was written for.

⚠ **A HOVER TOOLTIP AND AN ⓘ ARE TWO PLACES TO PUT THE SAME WALL.** v2.50.3
took 2,494 characters off a hovered label and put them behind the ⓘ where the
rule says they belong — and the ⓘ's own window then stood 1,372 px tall on a
1,079 px screen, its OK button past the bottom edge. Both gates and
audit_panel called that clean. `Notice` decides scrolling by measuring the
text now. The lesson generalises: **moving a fault is not fixing it, and the
check that passed before the move will pass after it.**

⚠ THE FINER CUT MADE THE CAP EXPLODE, and it is worth knowing why before
touching either. The seam fix leaves a finer piece with islands in it, so the
lid built on it went from ~1,400 triangles to between 23,411 and 93,628.
Fixed by a coarser tolerance (a twentieth of the drop, not a hundredth --
same accuracy at a fifth of the size) and a HARD ceiling of 8,000. A ceiling
checked once a round is not a ceiling: a round begun at 7,999 ended at 32,000.
Verified across ten pairs: all CLOSED, within 1.5% of a 120,000-ray count,
none over 8,000 triangles, none slower than 0.75 s.
**v2.49.0 shipped** the seam fix, the re-cut cache and the viewer fallback.
It went through a hostile review first and every one of the eleven things that
review broke is mended — see the commits between `794df62` and `9ce999c`.
The only unreleased thing left is `close_the_cut`, which is NOT wired to
anything.

### THE VIEWER THAT NEVER ARRIVES — 2026-08-21

Reported: saved pages WITHOUT the viewer show the notice and "the button never
works for me". Cleared by measurement: the address answers 200 with 4,851,164
bytes, its integrity hash matches exactly, the host sends
`access-control-allow-origin: *` even for the `null` origin a file opened from
disk has, and the retry's `?cq-retry=N` changes neither bytes nor hash.

**Fixed three things around it.** A late-arriving viewer used to uncover a
BLANK page — `cqViewerCame` hid the notice and never drew. The retry only ever
asked the host that had already refused; it now walks three addresses
(cdn.plot.ly, jsdelivr, unpkg), measured byte-identical with the SAME sha256
and open CORS, so the page's own hash guards a mirror just as well. And the
notice names the address, since "could not be reached" cannot be acted on.

⚠ THE SUCCESS PATH IS UNTESTED and cannot be tested here: this machine's
embedded browser has NO network at all — a plain script tag, one with
crossorigin, one with the hash, and a server on 127.0.0.1 all fail alike. If
Basti still sees it, the notice now prints which address to check.

### THE RE-CUT IS KEPT BETWEEN REDRAWS — and the reason matters

⚠ I claimed dragging a fade slider never reaches `recut_where_they_part`. **It
does, on every step, on the GUI thread, with no debounce** —
`_agree.valueChanged` → `_on_agree_changed` → `_push_fade` →
`_surfaces_for_live` → `build_figure(split=True)` → the re-cut. Measured in
the real window: 153 ms a step before the sharpening, 422 ms after.

The answer never depended on the fade, so a drag asked for the same cut a
hundred times over — true long before the sharpening. One entry, keyed on the
shapes' CONTENT. A full 101-step drag: Detail 20 **5.79 s → 0.12 s**, Detail
40 **13.82 s → 0.50 s**, against the times BEFORE any of this work.

⚠ Any new work in `build_figure` is paid PER SLIDER STEP unless it is cached.
Check that before believing a cost is "only on rebuild" — I did not.
Unreleased since v2.47.0: the chart-skin faceting, the drift-tick dimming, the
weld helpers, `face_the_same_way` (now WIRED IN and a visible fix),
`close_the_cut` (NOT wired in, and not ready — see below).

⚠ `/private/tmp` **is swept nightly**. The whole project lived there once and a
venv was destroyed. Anything that must survive goes under `~/develop`.

---

## 2. Start the job again

This ran as a session-only cron every 10 minutes and was stopped on purpose
when this handover was written. **Recreate it in the new session** with
`CronCreate`, every 10 minutes, recurring, with the prompt in
`CRON-PROMPT.txt` beside this file — it is the exact text, verbatim.

Two things in that prompt are now out of date and are corrected here rather
than in it, so the original stays readable:

* the repo moved out of `/private/tmp` on 2026-08-20 — it is at
  `~/develop/ChromIQ-Gamut-Viewer/fork` and the old scratchpad copy is gone;
* the cap's feasibility probe is no longer in `/private/tmp`. It lives at
  `fork/docs/probes/inside-view/`, together with `what_the_lid_would_look_like.py`
  and nine pictures of the lid drawn.

---

## 3. Permissions and standing rules — these are Basti's, not mine

**ON-SCREEN TESTS: STANDING PERMISSION.** Driving the real window is expected
and has cracked more faults than anything else. Screenshots do not reach him,
so *look at the picture yourself* — chromium renders these WebGL pages and the
Read tool opens a PNG. Reasoning from trace data shipped a regression once;
the first screenshot settled it in a glance.

**SUBAGENTS: one at a time.** Parallel agents burn his usage far faster.
Never lose their work if a limit is hit.

**AND ONE OF THEM IS NOW STANDING, NOT ON REQUEST — 2026-08-21.** When Basti
hands a decision over, he asked for it to be challenged before it is acted on:

> "i trust your ruling on those but invoke an agent that is challenging your
> decisions critically to make sure the result is as good as possible.
> standing permission to drive the real app like a user would, take
> screenshots and analyse them to make sure the results are as good as
> possible!"

So: **every ruling of mine gets a hostile reviewer before it ships** — one
agent, briefed to reproduce the numbers its own way, attack the reasoning,
attack the ruling, and look at the actual pictures. Give it the measurements,
the proposed ruling, and the standing permission above; tell it not to be
agreeable and not to modify the repo.

⚠ THE ONE THIS RULE WAS BORN FROM, so nobody treats it as a formality. I had
ruled that four quiet lighting sliders were alive and only the defaults were
unlucky, and was about to ship an explanation. The critic reproduced my
figures, found one of them did not hold at the threshold I quoted, and located
the real fault: `light_position` pinned the lamp at a radius of 2000, which
the drawing library takes through the projection, so it converged on the
camera axis and above and below became the same picture. Two of the four
sliders were that bug. A documentation fix would have shipped over it.

⚠ AND THE CRITIC IS NOT THE DECIDER. It also advised raising the opening shine
to 0.4-0.5. Photographed at 0.08, 0.25 and 0.45, that washes the shape towards
white and weakens the colours, which a picture of what a paper can print must
not do — so that half was declined, with the pictures as the reason. Take what
survives measurement, not what the reviewer prefers.

**NEVER TOUCH** `~/ChromIQ`, `~/Downloads/Argyll_V3.5.0_orig`. **Leave**
`~/Desktop/ChromIQ-demo-profiles` alone. **Never delete Basti's files.**

**BASTI'S OWN APP WINDOW IS NOT YOURS TO KILL.** Kill only processes you
started.

**THIS FILE AND THE QUEUE ARE MIRRORED ON GITHUB**, in
`fork/docs/handover/`, together with the cron prompt itself. He asked for that
so the job survives losing the machine: *"even if it is deleted from my drive
i can always reach it from a new session and proceed from where we left of"*.
**The copies here are the live ones** — refresh the mirror whenever either
changes, with `cp START-HERE.md QUEUE-when-the-cron-resumes.md
fork/docs/handover/`. Checked before every push: they carry his own credit and
his own machine's paths, and nothing else personal.

**NO PERSONAL DATA ON GITHUB** — no customer names, no employers, in files,
release notes or git history. The one exception he asked for is **Sebastian
Reiprich's own author credit**. Commit as
`itsab1989 <itsab1989@users.noreply.github.com>`.

**Never `git add -A`** — name the files; other processes edit this tree.

**Clean up** every temp folder and kill every browser afterwards.

---

## 4. Where the work stands

**Nine of the ten queue items are finished**, each measured, most
mutation-proved. Releases so far: v2.40.0 → **v2.47.0**.

### BOTH DECISIONS ARE RULED — Basti handed them over on 2026-08-21

> "i trust your ruling on those but invoke an agent that is challenging your
> decisions critically to make sure the result is as good as possible."

**1. THE LIGHTING — settled, shipped in v2.47.0.** My first two readings were
BOTH wrong and are corrected here so nobody rebuilds on them:

* ~~"the values reach the traces and the drawing library ignores them"~~ —
  wrong;
* ~~"all four are alive, the defaults are merely unlucky"~~ — wrong, and it
  would have shipped a paragraph instead of a fix.

What was true: `light_position` pinned the lamp at a radius of 2000, and the
drawing library takes that through the projection, so a far lamp converges on
the camera axis and above and below become the same picture (229,586 px apart
close in; 0 px at the distance it used). Two of the four sliders were that
bug. The other two shape a highlight and have none to shape until Specular is
up — they dim now, and the shine stays low because raising it washes the
colours out, which a colour instrument must not do.

**2. THE CAP — ruled: build HIS idea, with one shared cut curve.** The
containment fault is gone (every lid corner sits ON the paper's surface,
median 0.000 Lab). What is left is that each shape is cut against the OTHER's
surface, so the two rims are two curves — no corner shared, only 19% of the
opening's rim within about two pixels of the lid's. My own alternative, a cap
built from the opening's own rim, closes the shape (18 loops, 0 edges left
open) and looks wrong: the big loop is 249 corners across 125.7 Lab and
strays 34.9 Lab — 28% of its width — out of its own best-fit plane. So the
surface that spans that rim is sRGB's shell, as he said. THE REMAINING WORK IS
THE INTERSECTION CURVE INSERTED INTO BOTH MESHES. Numbers in
`docs/probes/inside-view/NOTES.md`.

### The cap — item 8

At agreement 0% the standing remainder is an **open shell**, and its far wall
is lit exactly like an outside surface, so it reads as torn skin. That is
correct behaviour and is now **explained in the control's own words** (shipped
in v2.43.0), which was the one cure needing no ruling.

Whether to CLOSE the opening is a design decision about what the picture
means. **His own idea works and is drawn**: the piece of sRGB's shell that
lies inside the paper closes it, and the pictures are in
`fork/docs/probes/inside-view/the-lid/` — nine of them, three cameras × (as it
ships / with the lid / the lid alone). It looks right.

⚠ That was a **prototype**: 322 of the lid's 1,149 corners failed a strict
containment test, and the plan was "one shared cut curve in the re-cut".

### THE CAP IS BUILT — 2026-08-21, `close_the_cut` in `python/gamutview.py`

**The shared cut curve turned out to be unnecessary.** The lid is the hole's
OWN triangles slid down their own rays onto the other shape, so the seam is
shared by BEING the same vertex indices. Nothing is matched, so nothing can
mismatch. Measured on Glossy-paper against sRGB: 370 + 1364 triangles, **0
edges open, 0 used more than twice, one seam loop of 118 corners that move
0.000000000 Lab**, holding **187,551 Lab³** where an independent construction
built to a different design says 187,545 and a 60,000-ray dice count says
189,090. Takes 2.8 s. Nine pictures in
`fork/docs/probes/inside-view/the-lid-that-fits/`; the trail is in
`NOTES.md` under 2026-08-21.

⚠ **Every seam number in the entries above was measured on cracks.** The
unwelded mesh from `split_at_crossing` has four copies of each crossing point,
and "18 chains, 236 cut corners, 0.88 Lab apart" was all about those.

### THE WINDING — SHIPPED, AND IT IS A VISIBLE FIX

Shapes from the **convex-hull and device-cube paths** arrive wound half-and-half
(scipy's `ConvexHull.simplices` are unoriented; the paper is 207/207 of 414,
sRGB 3174/3174 of 6348). NOT "every shape": gamuts read through Argyll from an
ICC profile arrive already consistent. `build_gamut` and both `references.py`
builders now call `face_the_same_way`.

⚠ **I first told Basti this changed no pixel. It changes 28,861 of them.**
`cqOrder.order()` sorts every triangle into a near or far draw bank by its own
cross product (`ti3gamut.py:3540`), so half of each shell's faces were in the
wrong bank and two see-through shapes came out covered in blotchy dark
mottling. THE MEASUREMENT THAT SAID OTHERWISE COULD NOT SEE IT: it drew ONE
OPAQUE shape, and the far-wall sort only runs on see-through shells — and its
control, turning every triangle round, is cancelled by the page's own
`if (vol > 0)` normalisation at `ti3gamut.py:3444`. A no-op control that
looked like a pass. This is the fifth time that rule has been paid for.

⚠ **"Every cone from the middle points outward" is the WRONG test of winding.**
A correctly wound DENTED shape has triangles that fail it — 3 of the
device-cube paper's 978 — and dents are the whole point of `mesh_volume`. The
honest test is that no interior edge is walked the same way round by both its
triangles. Both I and the hostile reviewer got this wrong first.

### THE CAP — the four breaks are MENDED, 2026-08-21 (commit `db69a10`)

A hostile reviewer broke it four ways, each of which passed every test it had.
All four are fixed, each has a guard, and a mutation proves every guard lands.
Evidence in `scratch/hostile/`. What was wrong, and what it reads now:

* ~~Nested shapes: 643% volume error, every test passing.~~ **FIXED** — a
  piece with no rim is already closed and is returned untouched. Matte-paper
  lies entirely inside Glossy-paper (both ship in `demo/`), so the standing
  piece has NO rim; `boundary_loops` returns `[]`, the lid becomes a separate
  closed shell, and `face_the_same_way` turns it outward — so the volume is
  skin PLUS lid instead of skin MINUS lid. Two nested shells have no open and
  no crowded edges, so `test_the_lid_shuts_the_piece` is blind to it.
* ~~The drift pair 47% and 98% wrong.~~ **FIXED** — `sag` defaults to one
  per cent of the actual drop, not a flat 0.25 Lab. Now +1.9% and +0.6%. `sag=0.25` is an ABSOLUTE Lab
  tolerance and one paper measured months apart differs by a couple of Lab, so
  the flat lid triangles hang across most of the gap. It passes on
  paper-vs-sRGB only because that gap is ~20 Lab. sag=0.01 gets within 1.7%
  and costs 15 s.
* ~~A centre outside the shape not refused.~~ **FIXED** — it now raises,
  using `covers_the_sphere_once`, which was written for this and never called. A gamut of only light patches
  does not contain (50,0,0); `close_the_cut` returns 126+3232 triangles, 13 of
  the piece's own facing inward, and the edge test still says "closed".
  `covers_the_sphere_once` would have caught it at 0.9128 — it is never called.
* ~~Far too slow~~ **FIXED** — `_rays_onto` files each triangle under the
  cells of sky its bounding CAP reaches (a cap, not a box round its corners:
  the arc between two corners bulges, and a box drops candidates). Identical
  answers, asserted on four shapes. 0.60 s at the default Detail, 0.65 s at
  40, 2.68 s on the worst pair. Was: 2.5 s at the default Detail, 8 s at
  Detail 40, and 43 s on sRGB-vs-P3. `_where_the_ray_leaves` tests every
  triangle for every ray, once per sag round and once per smoothing pass.

⚠ `scratch/lid/lid.py` is **NOT an independent construction** — same design,
same algorithm, same comments. Two implementations of one design tell you the
code is right, never that the design is. Do not cite it as corroboration.

⚠ `test_the_seam_is_the_pieces_own_corners_unmoved` is nearly vacuous: five
wildly different lids all give 0.000000000, because it compares an array with
its own copy. It does catch the smoothing pass dragging the seam, and nothing
else.

### THE CAP IS WIRED — "Close where it is cut", 2026-08-21

Control, short hover, long ⓘ, remembered, `SPACE_INDEPENDENT`, into saved
pages, and dimmed with its own reason in each of four states. TWO SHAPES ONLY:
with three the hole ends wherever the ray next meets ANY of the others, which
is a different construction, so `cap_over_the_cut` declines rather than cap
against one arbitrary neighbour. Kept between redraws, ONE ENTRY PER SHAPE
(both are capped, and a single slot is evicted by the other every time: 4,104
ms a repeat against 45). First build 2,804 ms, then 45.

⚠ DRIVING IT FOUND TWO FAULTS READING COULD NOT: the availability asked an
attribute that does not exist, so the tick was dead in EVERY state — which
looks exactly like a rule working perfectly — and it ran before the redraw
stashes the scene, so it lagged a step.

⚠ THE SPECKLED EDGE IS NOT A GAP. Isolated by drawing the lid alone: it is the
shared rim, where 20% of the triangles are needles, pre-existing in the cut
(24.4% before the seam work, 20.3% after). Flat shading swings a needle's
normal away from its neighbour's. The pieces meet corner for corner.

⚠ BOTH OF THE LID'S INSETS ARE A SHARE OF THE LOCAL DROP, never of the shape:
sized for a 190 Lab shape, the step is a tenth of the whole gap between two
measurements of one paper and swelled the lid to +61.7% of a ray count.

### THE CAP HAS BEEN REVIEWED AND MENDED — 2026-08-21

A hostile reading broke it in eight places; every one is fixed and guarded.
Each is worth carrying forward as a KIND of mistake:

* **It was never remembered.** `close_cut` was not in `_persisted()`. I
  believed I had added it — a multi-part edit script died on an assertion
  before reaching that line and wrote nothing. ONE EDIT AT A TIME, verified:
  a script that writes only at the end writes nothing when it raises.
* **CIE XYZ could never work.** The middle was hard-coded (50, 0, 0), CIELAB's
  neutral point; an XYZ gamut spans 0 to 1, so every ray left from outside the
  shape and the refusal was caught and turned into "no lid", silently.
* **The lid took a row of its own** in a saved page's controls, so fading a
  shape left its lid at full strength. Pages key rows on `legendgroup || name`.
* **It covered an outline** — an opaque sheet inside a wire cage.
* **The dimming asked a paraphrase** of what the drawing asks, so it invited a
  click that did nothing in four states.
* **"No lid passes 8,000 triangles" was false.** The lid begins as a COPY of
  the piece it caps, so it is never smaller than that piece; the budget bounds
  what is ADDED.
* **The accuracy figure was 2-3x too kind** (+0.96% claimed, +2.00% measured).
* **A ceiling was credited with a bound it does not give** — removing it
  changes nothing; the SIZE FLOOR bounds the three-shape case. An equivalent
  mutant, and saying so beats inventing a test to catch nothing.

⚠ THE FILE NAMED FOR THE OFFER DID NOT TEST THE OFFER: gutting the dimming and
disconnecting the tick from the drawing BOTH passed all 1,006 tests.

⚠ A CHECK THAT ONLY IMPORTS CANNOT SEE A NAME USED BEFORE IT IS ASSIGNED. The
cache-key fix read `middle` eleven lines early, imported perfectly, and would
have thrown on the first call.

**WHAT IS LEFT ON THE CAP: a release.**
A control with a hover of at most 200 characters and a long ⓘ, persisted,
reaching saved pages, in `SPACE_INDEPENDENT`; the lid needs its colours read
off the other shape (`_where_the_ray_leaves(..., and_where=True)` gives the
triangle and the place inside it). It is 0.6–2.7 s, so compute it on
`_after_fade` and cache it per shape pair — it depends only on the pair, NOT
on where the fade slider sits. Then drive it on screen and put it before a
hostile reviewer again.

### THE SEAM IS FIXED TOO — `sharpen_where_they_part`, commit `794df62`

It was drawn up to **15 Lab** from where the shapes really cross, on 29.8% of
its length against sRGB. Now 1.01 Lab and 1.8%. The cut only ever asked each
triangle's CORNERS, so it missed a shape bulging through the middle of a facet
and drew a straight line between seam corners where the crossing bends. It is
NOT the reference's resolution: the old seam was identical from 1,452
reference triangles to 60,492.

⚠ It does nothing where a shape's corners are UNANIMOUS, deliberately. A new
corner is an edge's midpoint, which lies ON this surface, so where two
surfaces touch — two copies of one shape — the containment question is asked
on its own answer's boundary and comes back either way; sharpening left specks
of an emptied picture standing. The price: a bulge through one facet of an
otherwise wholly-inside shape is not found.

⚠ COST: the re-cut goes 21 ms → 111 ms at the default Detail, 45 → 526 at
Detail 40. Paid on a REBUILD only — dragging a fade slider restyles live and
never reaches here — and a rebuild already takes about a second. If that ever
needs to come down, the cost is `Skin.contains`, which is roughly linear in
the other mesh's triangle count; a size filter on the facets did NOT help
(measured).

⚠ The welded rim is now two or three loops, not one. That is the truth: a
shape bulging through a facet leaves the standing piece with an ISLAND. Two
assertions that said "one loop" encoded the old, wrong geometry. A control with a hover of at most 200
characters and a long ⓘ, persisted, reaching saved pages, in `SPACE_INDEPENDENT`
if it is; then drive it on screen. My ruling on the two open points, for Basti
to overrule: paint the lid in the OTHER shape's own colours (it IS that
shape's surface, and it answers the same instinct as his "turn this magenta
out-of-reach section into the real colors"); and offer it as a control rather
than doing it silently, because closing the shape changes what the picture
claims. Put it before a hostile reviewer before shipping.

### The sweep is FINISHED — 22 of 22, 2026-08-20

All six that were left ran in the foreground and came back clean:
`audit_showcase_page`, `audit_the_controls_can_be_shut`,
`audit_the_page_at_any_size`, `audit_the_switch_changes_nothing`,
`check_layout`, `drive_all_combinations` (65,836 checks, 0 broken). Re-run
2026-08-22 and unchanged: 65,808 in Phase A over 6,912 combinations, 28
more in Phase B.

⚠ **A REBUILT SCREENSHOT ALWAYS DIFFERS. THAT IS NOT A CHANGE.** Checked
2026-08-22, with 15 commits touching drawing or window code since the pictures
were last made: rebuild them and compare, and 1.4% to 6.1% of pixels differ —
which reads as "the app changed" and is mostly not. Two things separate the
two:

* **Threshold the difference.** Counting every pixel that differs at all
  counts the encoder's ±1. Above 40 levels, `11-controls` differed by ZERO.
* **Rebuild a second time and compare the two rebuilds.** That is the control,
  and it is the only honest one. `23-five-ways` differed from the committed
  copy by 5,111 pixels and from its own second rebuild by **7,359** — the
  variation between two runs of identical code was LARGER than the "change".
  The 3D pictures are captured from a moving page; the camera is not in
  exactly the same place twice.

Verdict that day: nothing had changed, and rebuilding would have committed
churn as an update. `08-slice` and `22-choosing` came back byte-identical, so
the encoder itself is deterministic — it is the rendering that moves.

⚠ **`make_doc_shots.py` TOOK AN UNKNOWN WORD TO MEAN "ALL FOUR"** — fixed
2026-08-22. It accepts `controls`, `page`, `colours` and `dialog`, and
anything else used to fall through to remaking everything, which is how
asking it what it knew (`make_doc_shots.py zzz`) modified three pictures. It
refuses now and exits 1. **The note here first said it "ignores its
arguments", which was wrong** — it read them all along, and only the unknown
case misbehaved.

⚠ **NUMBERS IN PROSE ROT, AND ONLY SOME OF THEM CAN BE GUARDED.** Three were
found stale by reading, not by any rule: the suite was called 851 tests when
it is 1,017, the showcase pages were called ten when the script writes 25, and
these checks were called 60,076 when they are 65,836. The first two are asked
now by `audit_the_readme_is_true` — `--collect-only` counts in 0.37s, and the
pages are counted on the disk. **The third cannot be**: knowing it costs the
heaviest run in the repository. It will rot again, and the only defence is
that it is written in two places that agree.

⚠ **AND A RULE WRITTEN FOR A CASE MUST BE TRIED AGAINST THAT CASE.** The page
rule first read `([0-9,]+) showcase pages` — and the sentence that prompted it
said "ten". Putting the old wording back printed "0 counted" and reported
Clean. It reads words as well as figures now.
**Do not run them again as a sweep** — run one when you have changed
something it looks at.

⚠ **AND RUN THEM ON A REAL SCREEN.** Two of them skip material checks when
`QT_QPA_PLATFORM=offscreen` is set: `audit_sliders` cannot judge the four
movement sliders (a browser with no screen throttles its animation loop away)
and `audit_what_you_save` does not judge the saved picture. Both now SAY so in
their summary instead of printing the same word "Clean" as a full run — that
was fixed on 2026-08-21 after the record above was written, so **it is not
known how the 22 were run.** Measured since, on a real screen: all four
movement sliders are live, and the saved picture carries what was on screen.

A plain `python scripts/audit_sliders.py` uses the real screen — OFFSCREEN is
true only when the variable is literally "offscreen", and no script sets it
itself. Two runs were misread as offscreen before that was noticed.

### What the sweep turned up, both shipped in v2.44.0

1. **Both page checks asked about the sides and never the bottom**
   (`edd9938`). `scripts/page_questions.py` promised the reader's strip was
   "inside the window rather than off the bottom or the side"; only the side
   was measured, `strip` was collected and never read, and the strip was
   looked for as `.cq-controls` — **a name that matches nothing in any page
   this project writes**; it is `.cq-spin-bar`. A strip pinned below the
   window read Clean at every size in every engine. Now asked properly, with
   the emptiness guard at RUN level per SELECTOR (per page it false-alarmed
   21 times on `15-one-printer-over-five-years.html`, which honestly has no
   controls at all).
2. **Two rooms divided any width they were given** (`0ff163f`). At 390 px
   each room is 195 and the shape goes through the side walls at every
   viewpoint — 80–155 coloured pixels in the edge column, measured with the
   spin paused and both rooms pinned to four cameras; one room is clean at
   the same widths. Below 1000 px they stack now. **This was the window too**
   — a 900 px window leaves the picture 482 px, and `_write_two_rooms` writes
   through the same function. Driven on screen: stacked at 900 and 760, side
   by side at 1500, and the view scrolls (1066 against 783) to the second
   room.

Run them in **foreground batches of two or three** — a background sweep was
killed between sessions three times running. `check_binary_arch` needs a built
binary as an argument; `audit_sliders` **cannot run headless by design** and
says so in its first line (it needs a compositor, or it would call every
movement slider dead).

---

## 5. How to work — the part that actually earned its keep

Read `QUEUE-when-the-cron-resumes.md` for the full list. These four have each
cost a day:

**A measurement that cannot see the thing looks exactly like one that found
nothing wrong.** Four costumes in one week: a 26-line window said a slider was
connected to nothing (its connect was 33 lines down); a 1400-char slice said
the window passed no `split`; a layout walk from `window.layout()` found 0
stranded icons of 83 because the column is inside a scroll area;
`.parent().parent()` measured no groups at all and failed on the empty set.
**Every new rule must refuse an empty or implausibly small population.**

**A mutation goes stale as quietly as anything else.** Two `--prove` modes
were sabotaging nothing — one aimed at code deleted in 2.40.1, one had no
mutation at all — and both printed "this check is blind", which is
indistinguishable from a check that really is. Every `--prove` must verify its
own sabotage landed and say `THE MUTATION DID NOT LAND` when it did not; a
gate rule enforces that phrase.

**`isVisible()` is False for anything inside a folded section**, whatever its
own state (`visible=False, hidden=False`). It made one script unrunnable and
made three checks in another fail on a correct application — while a fourth,
asking the opposite, passed for the same wrong reason. Ask `isHidden()`, or
open the folds first the way `audit_panel` does.

**A page packs any sizeable array binary**, so `gd.data[i].x.length` is
`undefined` and every reading from it is a constant. Four false "nothing
changed" verdicts. Read `_fullData`, or measure pixels.

And one small operational one: **`git checkout --` to undo a mutation takes
your fix with it.** Copy the file instead.

---

## 6. Releasing

Bump `python/version.py`, prepend to `CHANGELOG.md`, run **both** gates, then
commit, tag `vX.Y.Z`, and push the branch and the tag. The build publishes
**11 assets**; anything fewer means it is still uploading. Rebuild
`docs/pages` and `docs/screenshots` when a change shows in them — *shipping
the app is not shipping the page*. They regenerate byte-identical when nothing
that reaches them has changed, so `git status` after a rebuild is a reliable
answer to "is this stale".
