# Changelog

## Unreleased

### 📝 The caption fits the pane it is in

One line written for a wide pane ran off the edge of a narrow one — measured
in the cross-section at a 1000-pixel window: **512 pixels of caption in a 424
pixel pane**, stopping mid-word at the frame. It now breaks at the middle dot
the caption itself uses to join its clauses, and goes back to one line when
there is room again.

It travels with **every** page — still or moving, flat or not, one room or
two, and the run's own graph. It did not at first: it went into the movement
script, and a cross-section has no movement script at all; then into the
writer most pages go through, which left six; then the two-room writer, which
left four. `audit_routes.py` watches for it now, and said "Clean" through the
first two of those.

### ✂️ A single cross-section gets the same air as two

Two cuts side by side have always had room around them; one cut was left to
the drawing library, which fits the axis exactly to the data — so the widest
colours sat **on** the frame:

    the x range   -82.579 … 82.404
    the data      -82.579 … 82.404

In a narrow window that reads as a picture cut off. It now uses the same
padded square the two-pane view has always used, so the two cannot drift
apart — except on a page carrying a lightness slider, where a range worked out
from the height being drawn would rescale the picture at every step.

## v2.34.0

### 📐 The picture fits a narrow window instead of running off the edge

On a laptop the viewer's pane becomes taller than it is wide — 424 by 833 at a
1000-pixel window — and the camera that frames a printer's gamut for a wide
pane cropped it there: the magenta side ran off the edge and **the whole
lightness axis was outside the view**. Measured on the application's own pane,
counting lit pixels in the outermost six columns:

    pane 1024    0 left    0 right
    pane  624   85 left   36 right      before
    pane  424  108 left  123 right      before
    every one    0 left    0 right      after

The eye is pulled back by as much as the pane is out of shape and no further
than twice, measured **from the view the page was written with** — when the
page opens, and again whenever the window changes shape. A pane wider than it
is tall gets that written view back, so a window dragged narrow and then wide
again returns to where it started.

**The conditions matter as much as the fit.** A page that re-fitted on every
resize would overrule somebody who had turned the shape, so the fitting stops
the moment anybody touches it — and starts again when they press *back to the
start*.

## v2.33.0

### 🏷 Two files whose names start alike are two shapes

*Set this for* picks the shape a change belongs to, and the live change found
it by asking which surface's name **starts with** that shape's name. Equivalent
until two files share a beginning: with `printer-2019` and
`printer-2019-again` open, asking for the first shape faded both, and nothing
on screen said why the other one had changed. The name is the whole name now.

### ✂️ A cross-section greys out what it cannot use

Measured rather than reasoned: with a cut on screen, every shape control was
touched and the page was asked what changed. Rings, the styles, both fade
sliders, the box and the measured patches all change a cut. **How solid it
looks, how deep the shading is, and the whole manual light block do not** — a
flat cut is drawn as outlines and takes no opacity and no light at all.

They are greyed out there now, with a tooltip that says which switch brings
them back. The window's own rule, written where two rooms are handled: a
control that cannot do anything is worse than a missing one, because it
invites a change and answers with nothing.

Greying needed the stylesheet to say so as well — Qt dims a disabled widget
through the palette, and this application paints over the palette, so a
switched-off slider had been drawn in the accent colour exactly like a live
one.

### 💾 A window opened later cannot disagree with its own slider

*How solid it looks* and *how deep the shading is* wrote their value into the
settings on every step of a drag, and into the record the picture is drawn
from only when the handle was let go. Drag and quit — which is exactly the
case those settings are written eagerly for — and the two parted company:

    the slider says 0.64, the picture is drawn at 0.37

Both are recorded as the handle moves now. A control that says something
untrue about the picture beside it is the fault this window has been reported
for twice, and this was a way to reach it that nobody had tried.

### 🪟 A live change reaches both rooms

Every live path in this window began at *the first* graph in the page — and
**two rooms are two graphs**. Measured, two papers side by side, solidity
dragged to 30%:

    before   room0 surfaces=0.3 | room1 surfaces=1
    now      room0 surfaces=0.3 | room1 surfaces=0.3

Two rooms disagreeing about how solid the shapes are is the one thing that
arrangement exists to rule out. It survived unnoticed because it used to
correct itself: anything that rebuilt the page drew both rooms from the same
recorded value. Now that the controls people drag no longer rebuild, it would
have stayed on the screen. The background chosen for a saved film had the same
fault, one room styled and one not.

### 🧱 The box and its grid stops rewriting the page

The reader's own copy of a page has always switched the walls with a relayout;
this window wrote and loaded a whole new page for the same tick. It relayouts
now, and falls back to the old way where a picture is flat or not loaded yet.

That takes the table to **80 controls touched, 34 rebuild** — from 41. The 34
that remain all change *what* is drawn rather than how it looks, and
`scripts/audit_controls.py` now says so, with the one open question named:
Light/Dark/Amber could be live too, at the cost of putting all three palettes
into every page this window writes.

## v2.32.0

### 🎚 The sliders answer under your hand

**How solid it looks** and **how deep the shading is** already changed the
picture as you dragged them — and then rebuilt the whole page when you let
go, which is the pause and the jump you saw a few seconds later. They now
record the value and leave the picture alone.

**The five sliders under *How the patches are drawn*** rebuilt the page on
*every step* of a drag, so a slow drag across a thousand-patch chart wrote and
loaded it dozens of times and the view went black between each. They restyle
the dots and the skin where they stand. Measured, in one drag: dot size 3.2 →
9.0, out-of-reach dots faded to 20%, **and no page loaded at all** — with the
legend keys left the size they were, because a key is a key whatever the dots
are doing.

The live fade also **respects *Set this for***. It faded every shape and the
rebuild afterwards quietly put the others back, so removing the rebuild would
have turned one fix into the next bug.

### 💡 Two light controls that had never moved anything

*Which side the light comes from* and *how high the light hangs* did nothing
at all. They were being sent into the scene as `lighting.direction` and
`lighting.height` — attributes that do not exist, so the drawing library
dropped them silently, while the hint beside those sliders promised "every one
of them moves the picture as you drag". They place the lamp now, live:
measured, the light moved from x 745, y 745, z 1700 to x 705, y −512, z −1800
across the two, with no page written.

Found by the audit that drags every slider and asks the page what changed:
five of the seven lighting sliders answered and these two did not.

### 🎯 A live change lands on the shape it was meant for

*Set this for* and *how each shape is drawn* multiply, and the multiplication
is where this broke. A shape drawn as a mesh has no surface in the picture at
all — so "the second surface" is not the second shape, and asking to fade the
second one faded the **first**:

    first=solid, second=mesh, set this for=the second shape
        the fade should have gone to nothing and went to printer-2019

It was invisible while every setting rebuilt the page, because the rebuild
redrew everything from the recorded values and put it right. Shapes are picked
by name now, and all twelve crossings of the two controls land where they
should.

### 🧭 The view stays where you put it

Anything this window cannot restyle in place is drawn by writing a new page
and loading it — and a page opens at the camera it was *written* with, so
every rebuild threw away the angle you had turned the shape to. Turned to a
low angle from the left, then rebuilt:

    before   -1.90, 0.35, 0.55  →  1.50, 1.50, 1.50
    now      -1.90, 0.35, 0.55  →  -1.90, 0.35, 0.55

The window now keeps track of where you are looking and writes it into every
page it makes, **saved pages included** — which is what the button offering to
save *this view* has always said it would do.

### 🙃 And the page is never written upside down

Carrying the camera over turned up a second fault the moment it was looked at.
A tilt that swings over the top of the shape leaves the scene's own *up*
pointing **down** — caught in a saved page as `up = (-0.14, -0.37, -0.92)` —
and a page opened that way is upside down and drags backwards in both
directions. Which is exactly what was reported while this was being built:
"when clicking and dragging the shape move in the opposite direction i would
expect (both for up/down and left/right)", and then "now this works again for
whatever reason" — the reason being a rebuild that threw the flipped camera
away.

Your viewpoint travels; which way is up stays up. A camera is not taken at all
while the picture is turning by itself, so a page written twice comes out the
same both times.

### 📐 The left column is sized once and never moves

A folded section under-reports how wide it needs to be — *How it looks* says
320 while it is shut and 348 once shown, and polishing it does not cure it. So
the column was sized from the small number and grew by exactly 28 pixels the
next time anything asked. Each section is now measured once, honestly, with
painting switched off, and the width does not move again for folding, opening
a run, or changing the appearance.

### 🖱 The pointer stops promising things

Qt hands a widget's cursor down to its children, so a hand cursor set on a
section applied to every label, readout and empty patch inside it. Only the
two links at the foot, which really do open a browser, keep it.

### ⚙️ The checks no longer write into your settings

Every driver in `scripts/` began by clearing the application's real settings
store — the one your own choices live in. It threw them away, and because the
window writes its state back as it closes, whatever a check last set became
your new default. The audit that switched the box off to see whether the
control said so **left the box switched off**, and it came back as a bug
report about the viewer: the walls behind the shape were missing, over a
picture drawing exactly what the settings said.

Settings now live behind one module, drivers send them somewhere throwaway,
and a test fails if any of that is forgotten.

## v2.31.0

### 🫧 The two shapes around the run's cloud

**Show the two shapes around it**, in *One device over time*. Off unless you
ask, because two surfaces over a cloud hide dots — and worth asking for,
because it is the most surprising picture this application draws: two profiles
of one printer five years apart can hold almost exactly the same amount of
colour, **0.35% apart**, while the colours inside those identical shells have
moved by up to **ΔE 3.03**.

They are **the window's own shapes**, built by the call the window makes when
you open a file — measured, 914 vertices against 914 — and not a coarser hull
of the comparison grid, which is what the first version did.

### 🎛 *How it looks* governs them, and there is no second set of controls

There were three controls for the shells in the run's own group for an
afternoon. They are gone: the section that already governs every other shape
in this window governs these two as well, and it offers far more — the outline
colour, the rings, the shading depth, the lighting, a style per shape and both
fade sliders.

*Set this for* names **the run's own profiles** while they are what it
governs, so nobody has to work out which is "the first shape".

Five things had to be fixed for that to be true, and none of them showed from
outside: the per-shape settings were read from the list of **open files**,
which is empty when only a run is loaded; surface-vs-mesh is not part of the
render options at all; the live fade asked whether a file was open; and the
redraw stood aside for the run, so every one of those controls reached it and
stopped.

### 🔺 The missing triangles, for good this time

The run's live picture went **around** the page writer, so it never got the
script that puts see-through surfaces in draw order — the shells came apart
into missing triangles the moment they were made fainter. It had been fixed
for good, in the writer that one call was avoiding. The saved page was always
right; only the screen was not.

### 💾 One Save button, and the run's page carries everything

The run's own *Save as a web page* button asked nothing, so its page could
never carry the reader's control strip, could not be saved without the viewer
inside, and could not leave the numbers out. There is now one button and one
dialog, and it offers **only what the page can honour** — proved in both
directions by writing every kind of page, opening it in a browser and reading
which controls it actually built.

That audit found two rules wrong, one each way: a cross-section was offered
*fade where they agree*, which it does not build, and a drift cloud was
refused *make a shape fainter*, which it builds perfectly well.

### 📋 The readouts can be copied

The family report has promised "paste it into an email or a report" since the
day it was written, and a QLabel hands the mouse straight through: there was
nothing to drag over and nothing for Ctrl+C to take. Every readout is now
selectable by mouse and keyboard.

### 💬 Hover short, ⓘ long

31 of the column's 54 tooltips were over 300 characters and the longest was
**2,139** — a wall of text wider than the screen, covering the control it was
describing. None is over 200 now; the long version lives behind the ⓘ, and a
control that had no icon is given one.

### Also

- The two threshold sliders no longer take the mouse wheel while the column is
  scrolled past them.
- A group opened this instant still answers with the width it had while it was
  shut, so the column was sized from a stale number and the widest section was
  cut. The same trap caused the theme-change fault; both now ask once the
  layout has settled.
- Four ⓘ collected on one row because the pass that places them treated a
  hidden control as an absent one. The panel audit now asks whether any row
  has collected icons.
- A new example page: **22 — a run, its two shapes, and the cloud between
  them**, saved through the window's own Save button rather than by calling
  the writer.
- 815 tests (812 + 3 skipped without ArgyllCMS), three audits clean:
  `audit_panel.py`, `audit_offers.py` and a state sweep that drives the window
  through the states a person moves between.

## v2.30.0

### 🕰 Follow one device over time, in the window rather than beside it

The run of profiles now lives in the **left column**, and its picture fills the
big view this whole application is built around. The window it used to open in
gave the graph 240 px inside a 940 px dialog.

It is the **same object**, not a copy: told it is hosted, it stacks its rows
for a 366 px column, drops its own small view, and hands its picture to the
window. A second panel that re-implemented the run, the ordering, the verdict
or the threshold would have been the fourth thing in this file written twice.

**Who owns the picture, written down once.** A pair of files and a run of
profiles are different questions and only one picture fits. The run wins while
it has something to say — adding profiles is deliberate, opening a second file
is browsing — the window says so in a line when both are open, and *Remove
them all* hands the view straight back.

Four faults, all found by driving it: the dialog's 560 px window minimum came
with it and dragged the column out to **596 px**, cutting every label;
*Remove them all* left the run's picture frozen with a file open behind it that
nothing would draw; the group and the panel both introduced themselves, giving
two paragraphs and two ⓘ within sixty pixels; and the ⓘ explaining *Show me*
was stacked beside *coloured by* instead — caught by the panel audit.

### 🎨 Every colour painted with the family it is heading for

A new entry in **coloured by**: *the colour it is heading for*. "How far it
moved" is a distance and cannot say which way; the three axes say it in numbers
— lighter, redder, warmer. Neither says the thing anybody reports out loud,
which is *"my greys have gone warm"*.

**What it will not say is most of the value.** A colour that moved less than
ΔE 1 is heading nowhere — below that the direction is mostly the instrument, an
i1Pro repeats to about ΔE 0.1 on white and two different ones agree to about
0.4 — so those dots stay in the picture, quietly, in a group that says so.
A grey is heading nowhere however far it moved: with no chroma there is no hue,
so the angle it left at is noise even when the distance is real. And nothing is
ever sent toward itself.

The key's swatches are the families' own hues at one lightness, at as much
chroma as sRGB will hold at each: a flat chroma put the reds at
`rgb(215,110,147)` and the magentas at `rgb(196,117,185)`, which is two pinks
to compare rather than six colours to recognise.

### 🧭 One thing at two times, or two different things?

**Has anything changed?** now asks. *"Moved"* is a claim about time: said of
two papers measured on one afternoon it is simply false, and it is exactly the
sort of false sentence somebody pastes into an email. The files cannot tell —
two `.ti3` of one chart look identical whether they are one printer months
apart or two papers in one session.

It changes only the verbs. Every number is the same either way.

*(ChromIQ itself would not need to ask: two `.ti3` in different runs of one
target are one thing over time, two in different targets are different things.
Recorded in `docs/PORTING-TO-CHROMIQ.md`.)*

### 💾 One Save button, and it offers only what the page can do

The run had a **Save as a web page** button of its own that asked nothing — so
its page could never carry the reader's control strip, could never be saved
without the viewer inside, and could not leave the numbers out. There is now
one button, one dialog, whichever question the view is answering.

And the dialog offers only what applies: a page of one shape was offering
*fade where they agree*, which needs two; a cross-section was offering four
ways to turn a camera it does not have; a line graph was offering all
twenty-two. Switches that are not shown are answered **no** rather than left to
a default — most of those defaults are "offer it".

### 🔢 Three of the four arrangements were saving less than they said

Found by writing every kind of page with everything offered and opening each in
a browser to see which controls it actually builds: **two rooms, a
cross-section and two cross-sections carried the styling for a block of figures
and no figures**, from a button whose dialog had just asked whether the numbers
should travel. Only the single 3D scene ever carried them.

### 🎚 Hide the colours that barely moved

A new slider under the picture: **Hide anything under ΔE …**. Everything that
moved less than that is left out, so what remains is only the movement worth
looking at.

**Why it earns its place.** The family lines give an *average*, and an average
hides the shape. "Blues: ΔE 1.7 (132 patches)" reads exactly the same whether
all 132 moved 1.7, or 120 sat still and 12 moved a great deal — and those are
very different problems. Pull the slider up and only the colours anybody could
see are left.

**It runs across this pair and no further, at both ends.** A fixed 0–5 would be
mostly inert: on one step of the demo run, whose biggest difference is ΔE 1.07,
**82%** of that travel would hide nothing. And it starts at the pair's
*smallest* difference, because a slider that begins below it spends its first
stretch reading "under ΔE 0.5" while hiding nothing at all — a control
announcing an action it is not performing.

**In steps of ΔE 0.1**, which is as fine as the numbers support: a hand-held
spectrophotometer repeats to about ΔE 0.1 on white and two different
instruments agree to about 0.4, so anything finer reads the instrument rather
than the printing.

**It changes the picture only.** Every number and sentence still describes all
the colours, so two people with the slider in different places quote each other
the same figures. The picture — and any saved page — says how many were left
out, because a page showing eleven dots cannot otherwise be told apart from a
printer that is nearly perfect.

### 🌐 …and the slider is in the saved web page too

Not baked in at save time. Whoever opens the page is usually not whoever made
it, and the interesting threshold is not known in advance — on one chart the
story is at ΔE 1, on another at 3. Everything needed was already in the file.

### 🧩 The main window gets the options the timeline had

The timeline could split its cloud into colour families and hide small
movements; the main window drew the same kind of cloud and could do neither —
and the main window is the only one that can show the **shapes** as well.

### 🏷 The key keeps telling the truth while the threshold moves

Three faults, all reported from the published page, all in the key or the
control beside it:

- **The last family standing had no name.** Push the threshold up until two
  dots are left and every label vanished — so the two dots on screen could not
  be identified at all. The drawing library marks an emptied group
  not-visible, then drops the key entirely for a single visible group. Right
  for a picture of one thing, wrong here, where the last family left *is* the
  answer. The key is now asked for by name.
- **The counts went stale.** `yellows — 134` stood over a single drawn dot. A
  thinned family now reads `yellows — 1 of 134`, and goes back to the plain
  count when nothing has been taken out of it.
- **The far end emptied the picture.** The last step hid *729 of 729* colours
  and left bare axes, which reads as a broken page. It now stops just below the
  biggest difference, so the end of the travel answers "which colour moved
  most".

The reading beside the slider was also its label's missing object — the word
"everything" — which on a narrow window wrapped away from the label and sat
alone in the middle of the page. It now says what the state *is*
(`nothing hidden`, or `ΔE 3.0`), cannot be separated from the slider, is drawn
in the page's own colour rather than the browser's blue, and the line under it
never goes empty.

### 🖱 The pointing lines stopped leaving black streaks

Point at the shape and three lines run out to the walls to say where you are.
In WebKit they were written into the picture and not cleared, so they cut black
slashes across the surface until something forced a redraw. Measured by
hovering across the shape against a clean picture: **WebKit 614 pixels of
streak, Chromium 0**. The lines are kept — they are what says where you are
pointing — and the streaks are down to **51**.

### 🔽 The left column folds, the way ChromIQ's own sections do

Fourteen groups, 2681 px tall in a window that shows about 880 of it: two and a
half screens before anybody had loaded a file. Every group's heading now folds
it away, with the same filled triangle ChromIQ uses for its Expert sections —
not a tick, which reads as "switch this off". Visible groups: **2042 px →
672 px**. It hides controls and sets nothing, so folding can never change a
picture; whether a group was open is remembered.

### 🖼 A new example: the shape says nothing, the inside says plenty

Two profiles of one printer five years apart hold **818,514** and **815,615**
units of colour — **0.35% apart**, the same size by any measure. By volume,
which is how most tools judge, that printer has not changed. Inside those two
identical shells the colours have moved by up to **ΔE 3.03**.

The generator *proves* that rather than repeating it: change the demo profiles
so the shells are no longer the same size and the page fails to build instead
of quietly making a claim its own data no longer supports.

### Also

- The saved page's threshold is now **run** by the test suite rather than read:
  the script is lifted out of the page, given a stand-in page and drawing
  library, and driven end to end. It had had five faults, every one of them
  found by somebody looking at a published page. Each of those five was broken
  back on purpose to prove the new tests catch it.
- The panel audit asks two new questions: does every button say something when
  it is hovered, and do the ticks in a box start on the same pixel. Both found
  faults the day they were added.
- 815 tests (812 + 3 skipped without ArgyllCMS). 21 example pages, every claim
  met, checked at 10 window sizes in two browser engines.

## v2.29.0

### 📋 Which colour families moved — now where you actually work

The colour-family report existed only inside **Follow one device over time**.
So somebody holding two readings of one chart — print the chart again months
later on the same paper and the same printer, read it, open both — got a ΔE
summary and **not one word about which colours had moved**. That is the
verification case, and it is the case the *Has anything changed?* box exists
for.

It is there now, for **two measurements and for two profiles**, in the main
window, under the numbers it explains.

### 🔬 The two cases mean different things, and now say so

An earlier version claimed in its own documentation to give them different
caveats and in fact changed a single word. Worse, the wording was wrong for
the commonest case.

**Two profiles** compares two *descriptions* of a device — not the device.
Each is one day's measurements of one chart, so a faded chart or a change in
how you built them is inside the number.

**Two measurements** is the printing itself. And if the second was **printed
again** rather than only measured again, everything between the two prints is
in there: the printhead's temperature changes how much ink each nozzle puts
down, low humidity dries ink near the nozzles and darkens it, paper takes up
moisture and changes size, and no two ink or paper batches are identical. That
is usually exactly what you wanted to find out — and calling it "the chart
faded" would have been simply untrue. If instead you read the *same sheet*
twice, you are seeing that sheet ageing plus your instrument's own
repeatability, around ΔE 0.1 for a typical hand-held spectrophotometer.

### 🐞 Two faults the tests could not see, found by driving the window

- **The heading was a mangled full path** —
  `private-tmp-claude-502--Users-…-Glossy-pap → …` — because a path was handed
  to a helper that turns names into safe *file* names.
- **The report survived "Close them all"** and went on naming colours in files
  that were no longer open. The same fault as the timeline window's, in a
  second place, three releases later.

Both now have tests that fail without the fix.

### 🧾 One list of readouts, not three

The names of the readouts were written out in **three** places — the code that
clears them when you close the files, the code that copies them into a saved
page, and the stand-in the tests use. Adding the colour-family lines meant
updating all three, and two were missed. Each showed up as its own bug: the
report survived *Close them all*, and it was **missing from every saved web
page**.

There is one list now, and a test that walks the window for readouts and fails
if the list does not know about them.

### 🔤 "Moved" is a claim about time, and is not always true

The same arithmetic answers a question nobody had asked it: two measurements
of one chart printed on **two different papers** say which paper holds the
blues and which holds the skin tones. Measured on the demo pair, matte against
glossy: **ΔE 3.1 average**, everything toward grey, worst in the blues at 4.0,
and the greys warmer and lighter.

Nothing "moved" there — they are two different things. So the report can now
be told whether it is describing *one thing at two times* or *two different
things*, and says "how the two compare" instead. It is never guessed from the
files, because two `.ti3` of one chart could be one printer months apart or
two papers on one afternoon, and the file names are not evidence.

### Also

- 783 tests (780 + 3 skipped without ArgyllCMS).
- The report's help text names what actually varies between two prints rather
  than gesturing at "conditions".

## v2.28.0

### 🔑 Switching off the reds no longer takes the colour key with them

Reported on the published page: hiding one family removed the ΔE scale from
the right-hand side, leaving the remaining dots painted in colours with
nothing to read them against.

**It was the reds specifically, and that is the whole shape of the bug.** The
key was drawn once, on the first group — which is what "draw the bar once"
naturally means, and is wrong, because that bar is then a property of that one
group and is switched off with it. Hiding any *other* family looked perfectly
fine, so trying one family would have found nothing.

The key now belongs to the **scene** rather than to any group, so nothing can
switch it off — and every family is guaranteed to be reading one scale rather
than merely being handed matching limits. Checked in both browser engines by
hiding all seven families in turn: the key survives every one.

**The test that was watching this had to change too.** It asked *how many
traces carry their own scale* and wanted the answer 1 — which is exactly what
the broken version had. A test phrased that way could never have caught it. It
now asks that **no** group owns a scale and that they all read the scene's.

### Also

- A cloud that has not been split is one trace with nothing to hide, so it
  keeps its own key and no page published before this changes.
- 779 tests (776 + 3 skipped without ArgyllCMS).

## v2.27.0

### 📱 Two faults found on a phone

**The box now holds still when you switch a colour family off.** Splitting the
cloud into seven groups gave you seven switches — and the drawing library was
refitting the whole scene to whatever was left, so the view jumped and the
numbers down the side changed every single time. Measured on the published
page: hiding one family moved the a\* axis from **−88…92.4 to −87.6…79**.

It also destroyed the only reason to hide a family. The question is *where in
the space does this family sit*, and an axis that resizes itself to the answer
makes every family fill the frame and look alike.

The range is now taken from **all** the colours, once, and fixed. So is the
shape of the room: with the aspect left on "data" the library works the
proportions out from the ranges too, so pinning the ranges alone was only half
of it — switch everything off but the greys and what remained was a sliver of
a\*/b\*, drawn as a tall thin slab with **the key pushed off the side of the
picture**. Verified at 390×844 in both browser engines, switching off down to
greys only: the box does not move and the key keeps all seven entries.

A cloud that has *not* been split is a single trace with nothing to hide, so it
is left exactly as it was and no page published before this changes framing.

### 🌐 A page that cannot fetch its viewer no longer blames your connection

A page saved without the 3D viewer inside it is a few dozen kilobytes instead
of about five megabytes, and fetches the viewer when it opens. When that fetch
failed it said *"reload the page when you have a connection"* — to somebody
whose connection was fine.

It was neither of the two obvious suspects: not the timer, and not the
integrity hash, which was checked against the CDN byte for byte and matches.
**The commonest way a 4.85 MB download fails on a phone is being interrupted** —
switching to another app or locking the screen stops it, and a network that
filters or proxies downloads can stop it too.

So the page now says that, says outright that it **does not necessarily mean
you are offline**, and offers a **Try to fetch the viewer again** button that
works without losing the page.

**And the retry actually redraws.** Without that it looked like it worked and
was useless: the instruction that draws the picture sits after the viewer's
own tag, so when the viewer fails that instruction still runs, fails, and is
gone — fetching the library afterwards left it in place with nothing asking it
to draw anything. Notice gone, page blank, reader worse off than before.
Measured in both engines before the fix.

### 🧭 Smaller things you pointed at

- **"Follow one device over time" now has its ⓘ beside the button**, like the
  other two ways in. It was beside the sentence underneath, so the third
  opener was the only one whose help was not where the eye had just been.
- **The timeline window's readouts scroll in their own panel.** As the words
  grew, the picture shrank to its floor and the key underneath it was cut off.
  The words are bounded now and the picture keeps its share. The window is due
  to move into the main window, so this is a stop-gap rather than a design.

### Also

- 776 tests (773 + 3 skipped without ArgyllCMS). Both fixes driven at phone
  size in Chromium and WebKit, with the fetch aborted outright.
- **Known gap, stated rather than hidden:** the colour-family report works for
  two measurements as well as two profiles — the engine carries what it needs —
  but only the profile pair has a screen. The `.ti3`-against-`.ti3` form is not
  yet reachable in the window.

## v2.26.0

### 🔬 The heat-map, split into the colour families the report talks about

The report says *"the blues drifted toward the magentas"*. Now you can go and
look at those very colours: tick **Split it into colour families** under the
picture and the cloud is drawn as seven groups instead of one — reds, yellows,
greens, cyans, blues, magentas and greys — each named in the key with **how
many colours are in it**.

**The key is the filter.** Click a family to hide it, click again to bring it
back. Hide everything but the blues and you see exactly where in the blues your
printer moved, which a single cloud cannot show you because the interesting
part is buried under everything else.

**It keeps working in a saved page.** Save the view as a web page and whoever
opens it can hide and show the families too — offline, on a phone, with nothing
installed. This is the drawing library's own behaviour rather than any code of
ours, which is exactly why it survives being saved.

**The picture and the sentences are filed by one function.** `which_family` and
`family_drift` share the same rule, so the number beside "blues" in the key is
the same number in the sentence underneath, always. Two pieces of arithmetic
would agree today and disagree after the first change to either, and a reader
would be left with a picture contradicting the words below it.

**One key, not seven.** All seven groups share the same fixed ΔE scale, so a
colour means the same amount here as in every other picture this draws — and
only one colour bar is drawn.

**A family with nothing in it gets no entry**, because a switch that turns
nothing on or off is a control that answers a click with nothing. The tick box
itself is hidden while the graph is showing, for the same reason: a line chart
has no colours to split.

### 📄 A new example page

**Which colours moved, in sentences** — the same first-to-last comparison as
the cloud, said in seven lines, with the families switchable in the page
itself. It is also the only example that exercises the timeline's own cloud
export, caveat and all.

### Also

- 770 tests (767 + 3 skipped without ArgyllCMS).
- Known cosmetic point for Basti to judge: the swatch beside each family in the
  key takes its colour from the ΔE scale, not from the family, so the dots are
  not "what a red looks like". The names carry the meaning and the key at the
  side says what the colour means, but it is worth an opinion.

## v2.25.0

### 🎨 Which colour families moved, and which way — in sentences you can send

Asked for by **a paper manufacturer**, comparing one year's profile with
the next. She wanted this shape of answer:

```
Reds:      stayed the same
Blues:     drifted toward green
Yellows:   drifted toward red
Grays:     drifted toward red
```

and named the hard part in the same breath:

> *"of course then you have to draw an arbitrary line around 'what is a red'
> and 'what is a yellow'"*

She is right. The line cannot be removed — so it is **stated** instead, in
three places at once: the panel in the timeline window, the saved web page and
the exported table all say where the families are centred, that the line is
drawn by this application and not by nature, and **how many colours sat close
enough to a line to have gone either way**. Measured on a boundary, the split
is 51/49; without that sentence every number in the report would be an
unexamined claim.

**Every line says how many patches it stands on.** A family of four and a
family of four hundred otherwise produce the same kind of sentence, and only
that number tells you how much to trust it. In the CSV it gets its own column
as well, because a spreadsheet gets sorted.

**Three kinds of movement, never collapsed into one.** A colour can swing round
the hue circle, move in or out from grey, or get lighter or darker — usually an
ink-mix problem, a fading or ink-limit problem, and a linearisation problem
respectively. So *"tending toward gray"*, which was one of the examples in
the request itself, is sayable and is not treated as a hue statement.

**It declines to answer when it should.** A family whose colours moved a long
way in no one direction reads as *mixed* rather than being given the direction
of their average, and a movement no bigger than its own scatter says *"but not
certainly"*. Both exist because the alternative reads as a finding: ΔE 8.2 of
pure noise was reported as "toward the yellows" during development, and looked
entirely plausible.

### 🩶 The greys are greys, and that is a measured decision

The existing family rule was built for *"which family reaches furthest"*, which
takes a **maximum** — and a near-neutral colour never wins a maximum, so its
unstable hue never mattered. This report takes a **mean**, which is made of
exactly those colours. Nudge one colour by 0.3 Lab units, less than two
profiles of one printer routinely differ by, and ask how often it keeps its
family:

| chroma | 0.1 | 0.3 | 0.5 | 1.0 | 2.0 | 3.0 | 5.0 |
|---|---|---|---|---|---|---|---|
| stays put | 25% | 39% | 55% | 79% | 97% | 99% | **100%** |

So anything under chroma 5 is reported as a grey and is never said to have
drifted toward a colour — it is warmer, cooler, redder, greener, lighter or
darker instead. It costs 1.5% of a real 9-step grid.

### 🔍 Four faults found, none of which looked wrong on screen

Every case below was built with its answer known in advance, because a sentence
like *"yellows drifted toward red"* is exactly as plausible when it is wrong.

- **A family reported as heading toward itself.** A family's mean hue sits near
  its own centre but not on it, so for half of them their own centre lies a
  fraction of a degree "ahead" and wins by being nearest. Reds turned firmly
  toward the yellows came out as "toward the reds" — and the same colours
  turned the *other* way came out right, which is why one example proves
  nothing.
- **Noise dressed up as a direction.** Movements that cancel leave a near-zero
  mean on every axis, and the largest of three near-zero numbers still wins.
- **One unreadable patch producing "nan ΔE"** beside a confidently named
  direction. Refused now, with the count.
- **A report that outlived its files.** "Remove them all" emptied the graph and
  left the family lines under it, naming two profiles that were no longer open.

### 🕘 "Follow one device over time" is where it can be found

It sat at the bottom of the left column in the quiet style, among *"start
again"* and the ArgyllCMS paths — the things you go looking for once. It is a
button that **opens files**, so it now sits with the other two, in the accent,
under its own heading, with a sentence saying what it is for.

### 🪟 And one the Windows runners caught

A test in this release wrote a file called `<b>a.icc`, to prove that a profile
name goes through HTML escaping before it reaches a saved page. Angle brackets
are legal in a filename on macOS and Linux and are **forbidden on Windows**, so
it passed here and took both Windows jobs down in CI — which is exactly what
those jobs are for. The rule is now proved with an ampersand, which needs
escaping just as much and is a name somebody could really have.

Every other test filename in the project was swept for the characters Windows
refuses. This was the only one.

### Also

- `Drift` carries the Lab arrays it was already computing and dropping, so the
  same report works for two **measurements** — the verification form that was
  asked for alongside it. `ProfileDrift`'s duplicate copies are gone.
- 763 tests (760 + 3 skipped without ArgyllCMS). The saved page holds its
  layout at 10 window sizes in both browser engines.

## v2.24.0

### 🪟 A Windows build for ARM, and a check that every build is what it claims

Basti asked whether there were Windows-on-ARM releases. There were not, and
Windows was the **only platform covered on a single architecture** — macOS and
Linux each had both. An ARM Windows machine was running the x64 build under
emulation, which works and is slowest exactly where this application spends its
time: NumPy and SciPy.

**The wheels were the question, so they were asked about rather than assumed.**
`pip` with no wheel falls back to building from source, and Qt does not build
inside a CI job. From PyPI:

| | win_arm64 wheel |
|---|---|
| PyQt6, PyQt6-Qt6, PyQt6-sip, both WebEngine packages | ✅ |
| NumPy, SciPy, Pillow, PyInstaller | ✅ |
| plotly | pure Python — one wheel serves every platform |

Nothing was missing, so there is now a sixth build:
**`GamutViewer-Windows-arm64.zip`**.

### 🔍 And the guard that had to come with it

A build machine can produce a binary for the wrong architecture and say
nothing. On a machine with an emulation layer, a toolchain for the other
architecture runs quite happily and emits a working binary of the wrong kind:
**the tests pass — they run under emulation too — the packaging succeeds, the
upload succeeds**, and the artefact goes out under a name that is not true. The
only symptom is that it is slow on precisely the machines it was built for.

So every build now opens its own binary and reads the machine field the linker
wrote — PE, ELF and Mach-O, including universal binaries. **Every platform, not
just the new one**: the same mistake is possible on any of them, and a check
that only guards the case somebody happened to think of is half a check.

Verified against real binaries before being trusted: this machine's Python
(arm64, agreeing with `file`), `/bin/ls` and `/usr/bin/ssh` (universal, both
architectures reported), and hand-built PE headers for ARM64 and x64 — each
accepted for its own architecture and refused for the other. `x64`, `amd64` and
`x86_64` are one answer, not three.

- 723 checks, up from 713.

## v2.23.0

### ⚡ A redraw is two to three times faster, and the reason was not what the note said

The task this came from said the re-cut for the agreement fade cost **81 ms +
105 ms per redraw**, and that it was the one thing that had got slower.
Measured before changing anything: **two papers 189 ms, the same two with the
fade on 193 ms.** Four milliseconds. That cost had already gone with the
re-cut work; optimising against it would have been effort spent in the wrong
place, which is why the first job was to measure rather than to fix.

What the profile actually found, on two papers against Adobe RGB:

| | ms | share |
|---|---|---|
| `coverage` | 177 | **49%** |
| build and write the page | 173 | 48% |
| everything else | 8 | 2% |

**Both halves were doing work nothing had asked for.**

**The readouts were recomputed on every redraw.** `coverage`, `shared_volume`
and `hue_reach` read the two SHAPES — and a shape is rebuilt only when a file
is opened or closed, or the colour space or white point changes. Every *other*
redraw asked the same question of the same two objects and paid for the answer
again — and those are exactly the redraws that have to feel smooth, because
they are what moving a slider does. They are remembered per pair now.

**And the cage was being validated a point at a time.** Building it as a
`go.Scatter3d` ran plotly's validator over every entry of the colour list:
**151,758 calls** to one function in a single profiled redraw. The figure takes
a plain dict and converts it by a faster route, and the trace JSON that comes
out is byte-for-byte identical. Colours are spelt `#rrggbb` rather than
`rgb(r,g,b)` for the same reason — seven characters against eleven, across
20,178 of them, checked on all 2,400 vertex colours to decode identically.

| scene | before | after | |
|---|---|---|---|
| one paper | 30 ms | 31 ms | already fast |
| two papers | 189 ms | **62 ms** | 3.0× |
| two papers, fade on | 193 ms | **65 ms** | 3.0× |
| two papers vs Adobe RGB | 358 ms | **176 ms** | 2.0× |
| a coloured cage, whole path | 453 ms | **172 ms** | 2.6× |

**The remembering is keyed on the shapes themselves, and holds them.** `id()`
is unique only among objects that are *alive*, so a cache keyed on ids alone
would cheerfully answer for a gamut that had been collected and a new one built
at the same address — a wrong number that looks entirely plausible. Checked in
the real window on all three ways it must forget: five more redraws give
identical text, a different file gives new numbers, and switching CIELAB to
CIELUV moved the shared volume from 78% to 81%.

- 713 checks, up from 708.

## v2.22.0

### ❄️ Opening a profile no longer freezes the window

`icc_gamut` runs ArgyllCMS, and ArgyllCMS can wedge on a profile it does not
like — **measured at over four minutes** on one before this application gave up
waiting. That call was on the UI thread, so the whole window froze: nothing
painted, nothing answered, no way to stop it, and then an error. On a machine
with **no** ArgyllCMS the same file opened instantly, which made the
application *faster without the helper installed*. Upside down.

Reading now happens on a thread of its own. Measured with the tool made to
wedge on purpose:

| | before | after |
|---|---|---|
| the window while it waits | frozen | **352 timer ticks in 8.2 s** |
| pressing Stop | no such thing | back in **0.9 s** |
| an ordinary profile | 149 ms | 149 ms, and no dialog at all |

**Nothing appears unless it is slow.** The grace period is 400 ms, chosen from
measurement: a profile through ArgyllCMS takes 149 ms, read directly 9 ms, a
measurement 31 ms. A dialog that flickered on every ordinary open would be
worse than the silence it replaced.

**Stop keeps its word where it can, and says so where it cannot.** For a
profile going through ArgyllCMS it ends that program. For a measurement or a
picture the work is arithmetic in this process and cannot be interrupted part
way — so the button is only offered where it means something.

### 🕳 And a shadowed exception that nearly shipped with it

`gamut_app` defined its own `Stopped` **after** importing `references.Stopped`,
so the local one silently won. The `except Stopped` written for the new Stop
button caught the local class and let the one actually raised straight through
— into the handler that tells you a file **"could not be used"**, which is
precisely the wrong thing to say to somebody who has just pressed Stop.

Nothing caught it because nothing exercised pressing Stop at that call site.
One name, one class now, and a check that the two are the same object whatever
order anything is imported in.

- 708 checks, up from 702.

## v2.21.0

### 📉 The run's own starting point is on the graph

Reported by Basti from a phone: *"such an overview should also show the 2019
reference as the reference point at zero. also the 2020 value has no 2020
label and does not seem to be on the exact line that would represent 2020. or
is this because the profiles were not created in the same distance from a time
point of view?"*

Right about both. **His own explanation was the one thing it was not** —
measured, all four gaps in that run are exactly 12 months.

Both came from one root: **the first profile was not plotted.** The cumulative
line is measured *from* it, so leaving it off drew a line whose origin was
nowhere on the picture, starting at a whole year of drift (ΔE 2.60) which
reads as where the run began. And with the run starting at 2020-03-01 the
padded axis began 2020-01-06 — five days after the 2020 tick would have
fallen — so the axis was labelled 2021, 2022, 2023 and the 2020 point sat in
an unnamed gap.

Now the line starts at the first profile at **ΔE 0**, and every profile gets a
tick of its own (by year, or by year and month where two share a year). The
"since the one before" line still starts at the second, because it has no
previous — and that difference between the two lines is worth seeing.

### 🧰 Demo profiles with every release

Twenty-one made-up profiles in four runs, attached to each release as
`ChromIQ-demo-profiles.zip`, so somebody who has just downloaded the
application can try the timeline without owning a printer, a
spectrophotometer and five years of patience.

| Folder | What it shows |
|---|---|
| **1 — drifting steadily** | every step the size of the last, so it will keep going |
| **2 — it moved all at once** | three quiet years and a jump, on a date you can look up |
| **3 — wandered off and came back** | ends where it started, having been ΔE 5.39 away |
| **4 — twice a year** | the axis spaced by real time, two profiles in some years |

**Generated, not committed** — twenty-one 1257 kB profiles differing in about
six thousand bytes each is 26 MB of near-duplicate binary for something that
takes ten seconds to make. **Each set checks that it really shows the shape it
claims** before it is written; a demo that does not demonstrate the thing
teaches the reader that the feature does not work, so a failure there stops
the release.

### 🛠 The build workflow, hardened

- **The Windows two-pass workaround is gone.** It ran the suite twice and
  passed if either attempt exited 0 — a workaround for a real fault where
  Windows printed "650 passed" and then exited 1. **Four consecutive releases
  have reported `plain=0`**, so it has not happened since the tidying that
  closed windows and removed temporary folders properly. It was never
  harmless: a second unraisable appearing later would have been swallowed, and
  every build paid for the suite twice. If it comes back, the build now goes
  red — which is the point.
- **Every job has a ceiling**: 10, 45 and 15 minutes. GitHub's default is six
  hours, and this project has already lost two and a half of them to one
  wedged tool.
- **One run at a time per tag**, with the superseded one cancelled. Retagging
  after a failed build is normal, and two runs racing to attach assets to one
  release means whichever finishes second wins — not necessarily the newer.
- **`actions/checkout@v5`** throughout, ending the Node 20 deprecation warning
  on every job of every build.

- 702 checks with ArgyllCMS, 699 without.

## v2.20.2

**v2.20.1 was tagged and did not build.** Its change was right and its error
handling was half-written, all five build machines said so, and this is the
same change with the other half. The v2.20.1 tag exists and has no release
against it; nothing was published from it.

What went wrong is the interesting part, and it is written up under v2.20.1
below: the machines that run the checks have **no ArgyllCMS** and the machine
these are written on **does**, so a fallback added for "ArgyllCMS is missing"
could not fail locally. `GAMUTVIEW_NO_ARGYLL=1` now reproduces that condition
anywhere, and the release workflow sets it rather than relying on the tools
happening to be absent.

## v2.20.1

### 🔓 A profile opens without ArgyllCMS, which is what the README always said

Basti: *"you mentioned icc profiles that argyll does not like — is there a
fallback so those can be used anyway here?"*

There was, for two of the three ways it can go wrong, and not for the third:

| ArgyllCMS is… | Before | Now |
|---|---|---|
| present, but **stuck** on the file | reads it directly after 30 s | unchanged |
| present, but **refuses** it (ICC v4) | reads it directly | unchanged |
| **not installed at all** | **refused, told you to install it** | **reads it directly** |

The one turned away was the simplest of the three — and the direct reader was
already the thing being fallen back to in the other two. **The documentation
was right and the code was wrong**: the README has said all along that
"measurements, gamut files and ICC profiles all open without it", and the error
message for `.cxf` files says in as many words that "ICC profiles need none of
this and open as they are".

ICC **v4** is not exotic, which is what makes this worth a release of its own:
Display P3, Rec. 709 and Rec. 2020 all ship with macOS as v4, and paper makers
hand out v4 output profiles.

**ArgyllCMS is still asked first wherever it exists.** It returns the surface
it computed, with the profile's real dents in it. Measured on the demo profile
the two readings are 0.76% apart by volume — 818,514 against 824,706 — and
that difference is checked by a test rather than assumed.

### 🧪 And the reason it took a failed build to notice

The first attempt at this shipped the fallback's **happy path only**: a file
that is not really a profile came back with the direct reader's own exception
instead of the sentence every other path here produces. All five build
machines caught it; the local run could not.

**They have no ArgyllCMS and this machine does** — and no `PATH` change hides
it, because the search deliberately looks in fixed folders as well. So the
branch that most users take is the one the developer's machine never reaches.

`GAMUTVIEW_NO_ARGYLL=1` now makes the search answer "not installed" wherever
ArgyllCMS really is, so the same run can be had anywhere:

```
GAMUTVIEW_NO_ARGYLL=1 pytest -q      # 694 passed, 3 skipped
pytest -q                            # 697 passed
```

The release workflow sets it explicitly rather than relying on the tools
happening to be absent, and `test_argyll.py` — which tests the search itself —
is exempt from it.

- 697 checks with ArgyllCMS, 694 without, up from 692.

## v2.20.0

### 🧭 Which way the drift went, not only how far

Asked by Basti: *"is there an option for the heat map to visualize the
direction of the drift?"* There was not, and the information was already there
and being thrown away — `compare_profiles` worked out where the second profile
puts every colour, reduced it to a distance, and dropped the rest.

**ΔE2000 is a distance, and a distance has no direction.** Measured on two runs
bent the same amount in opposite directions:

| | worst ΔE | average ΔE | mean move in L\* |
|---|---|---|---|
| bent one way | 3.51 | 1.61 | **+0.67** |
| bent the other | 3.70 | 1.62 | **−0.67** |

The distance cannot tell them apart. They are different faults with different
cures.

**Coloured by** now asks the question the distance cannot, one axis at a time —
*lighter or darker*, *redder or greener*, *warmer or cooler*. The scale runs
both ways from **no change** in the middle, so the two ends are opposite
directions rather than more and less of one thing, and the pale dots are the
colours that stayed put. Fixed at ±5 Lab units, for the same reason the
distance ceiling is fixed: two pictures are only worth putting side by side if
the same colour means the same amount in both.

**The dots are deliberately not red and green, or blue and yellow.** In a
picture whose subject is colour, painting "went redder" in red invites you to
read a dot's colour as the colour it stands for. One teal-to-orange scale for
all three is learned once, cannot be mistaken for the thing it describes, and
stays readable with the commonest colour blindness.

### 🔀 Any two profiles, not only the ones next to each other

Also asked: *"can i choose any two profiles from the trend for the direct
comparison and then go back to the full overview?"* Yes to both now. **from**
and **to** hold whichever two you like — the profile from before a head clean
and the one six months later need not be neighbours. Picking a step fills them
in; changing them switches the chooser to *any two you choose*; the first entry
puts the graph back. Both boxes on one profile is refused with a reason.

**And how many profiles a run can hold**, since that was asked too: no fixed
limit, and the arithmetic is not what would stop you. **24 real LUT profiles
build in 0.15 s**, six milliseconds apiece, flat with the count. Somebody
profiling monthly has twelve a year.

### 🐛 A remembered choice that was silently thrown away every time

Chasing the above turned up a real bug. The chooser is rebuilt whenever the run
changes, and put the reader back on what they were looking at through Qt's
`findData`. Qt compares stored item data as QVariants and can only do that by
identity for a Python object — so `findData(("whole", 0))` matched an item
holding `("whole", 0)` **only when the two tuples were the same object.** They
are when both literals sit in one code object, which is why an isolated check
appeared to prove it worked, and they are not across modules.

Measured on the real window: the item sat at index 5 and `findData` returned
**−1**. So every add or remove quietly threw the reader back to the graph — and
the check that should have caught it read that fallback as the correct answer
to a different question.

### 🧾 Also

- The sentence under the picture no longer sends you looking for "the largest
  and reddest dots" in a direction view, which has no red in it. It says which
  way the thing went instead.
- The direction key was printing "1 cooler", "no change" and "1 warmer" almost
  on top of each other; the bar is longer now. Found in the screenshot.
- 692 checks, up from 680.

## v2.19.0

### 🔎 From the graph, straight to any step of it

Asked twice by Basti, the second time: *"if i selected multiple profiles, have
them in the trend view, can i then choose two of them for the heatmap
comparison view (i guess more at once would not be possible)?"*

A line says **when** a device moved. It cannot say **where in colour** it
moved, and those want opposite actions — a device that has drifted evenly
everywhere is a calibration job, one that has moved only in the deep blues is
a different problem with a different cause. Both draw the same line.

**Show me** now lists the graph, then every step of the run by name — *Where it
moved — printer-2019 → printer-2021 (ΔE 1.07)* — and last the whole run, first
against last. Choose one and the graph is replaced by the heat-map for that
pair.

- **The picture names the pair**, so a screenshot of it is still about
  something.
- **The sentence underneath is about that pair too**, not about the run — and
  that was a real fault, caught by looking at the screenshot rather than the
  code: a cloud of one year had *"it has drifted steadily, from the first to
  the last, ΔE 3.03"* under it. Saying the right thing is now part of drawing,
  so nothing can redraw without it.
- **Save this as a web page… writes whichever picture you are looking at.** A
  Save that always wrote the graph would quietly disagree with the screen.
- **A pair that cannot honestly be compared is not drawn.** Two profiles read
  through different tables answer different questions, so the difference
  between them would be mostly that rather than drift — and a picture of it
  would look exactly like a device that had moved. The window says so instead.

**Two at a time, and the window now says why** rather than leaving you to
wonder. Every dot is painted by how far apart *two* profiles put that one
colour; a third would need a second colour on the same dot. That is less of a
limit than it sounds, because a run is made of steps and every step *is* a
pair.

**The trap that was designed out.** Removing a profile from the middle of a run
changes which pairs exist. A remembered index would have gone on showing an
entry whose words named one pair while the picture showed another — the worst
way for this to fail, because nothing would look wrong. The chooser is rebuilt
whenever the run changes and falls back to the graph rather than to a different
pair.

### 📸 The timeline can be photographed at all now

The whole feature shipped in v2.17.0 **with no screenshot anywhere**, because
`make_screenshots.py` could only ever grab the main window. A shot may now hand
back the widget to photograph, so windows of their own can be pictured — and
two are, one of the graph and one of a step. The generator also clears the demo
profiles it makes, which were 12 MB a run.

- 680 checks, up from 670.

## v2.18.0

Everything here was reported by Basti from an iPhone, or found by measuring
what he reported. Six faults, and five of them were in every page this
application has ever written rather than in the newest one.

### 📱 A saved page you can actually read on a phone

**The page could not scroll at all.** `html,body` carried
`overflow:hidden` unless the page had the written-out figures on it — so on
every page saved *without* the numbers, the document was frozen. The control
panel sat below the fold with no way to reach it: not by dragging, and not by
any button either, because a page told it does not scroll cannot be scrolled
by anything. Page 14 carries the figures and scrolled; page 18 does not and
did not, which is why it "used to work on the examples i tried". The rule is
now what the check beside it always claimed: scrollable when anything at all
sits under the picture, which is figures **or** controls.

**And the picture refused to start a scroll.** `touch-action: none` on the
picture is what makes a pinch possible — without it the browser eats the moves
— but it also forbids scrolling from any touch that begins there, and this
project's own layout rule holds the picture at 55–85% of the first screen.
Measured by walking down the middle of the screen a row at a time: **74–80% of
a phone screen could not begin a scroll**, while the panel ran 411px to 1005px
past the bottom.

One finger now scrolls the page; **two fingers turn, tip and zoom the shape** —
the convention an interactive map inside a scrolling page already uses, and the
strip says so on touch screens. One-finger *tipping* is the price, and it is
still on two fingers, on the up/down buttons and in the look-from presets.

Pressing **more…** also brings the controls to you now, and **less…** puts the
picture back. Measured after: 90–97% of the controls on screen at every phone
size in both engines, against 20–53% before.

### ⚡ The picture was hundreds of separate drawings

A coloured wireframe was cut into **one trace per band of colour**, on the
belief that a 3D line takes a single colour for the whole of it. It does not —
`scatter3d.line.color` accepts an array. Checked against the library's own
validator, then **rendered**, because a validator accepting an array is no
proof the renderer honours it.

An Adobe RGB cage has 6726 edges and came out as **296 traces**, each its own
WebGL object with its own draw call.

| page | traces before | after | first draw in WebKit |
|---|---|---|---|
| a paper against Adobe RGB | 357 | **2** | 2.3s → **0.8s** |
| where the drift happened | 642 | **7** | 3.9s → **0.9s** |

The single trace differs from the banded one over 2.25% of the picture by at
most 29/255 — and that difference is the **banding disappearing**, so the cheap
version is also the accurate one. Each segment now carries its two real end
colours.

### ↩️ A printer that wanders off and comes back

Basti's question: *"what if a profile drifts in one direction for two years and
then back, matching the initial one again — would this be visible?"*

The picture always showed it. The **words** did not. Measured on five profiles
built to do exactly that:

| | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|
| since the first | 2.60 | **5.39** | 2.60 | **0.54** |
| since the one before | 2.60 | 2.67 | 2.67 | 2.08 |

Reading only the two ends, the verdict printed *"Nothing has moved that anybody
could see"* — of a printer that had been ΔE 5.39 away in 2021, which anybody
can see, and that sentence is saved into the page and the exported table where
it outlives the chart that would have corrected it.

It now says it went away and came back, how far it went, **and the year**, and
the graph marks the furthest point. A run that only creeps is still told it is
creeping — checked, because a warning that fires on everything is worthless.

### 🧹 Closing everything now closes everything

**Close them all** left the shape chosen under **Compare with** on screen, and
left the figures describing files that had just been closed. Measured: two
papers closed, and the window still drew Adobe RGB and still said *"90.7% of
the colour Glossy-paper can print also fits inside Adobe RGB (1998)"*.

One button rather than two: the **×** beside a file is the "next paper, same
comparison" gesture, and this is the "start again" one. The tooltip says both,
and says that nothing is ever deleted.

### 🔤 Two labels printed on top of each other

The timeline graph's key was drawn across its own headline — reported from a
phone, then measured in both engines at **14 of 20 window sizes**, a large
desktop among them. A second collision underneath it: on a short window the
title also crossed the side-axis name, which stood on end is taller than the
plot area. Four candidate layouts were rendered and measured rather than
nudged.

**`check_layout.py` could not have caught either.** It measured the page's
frame and never looked inside the drawing. It now checks that no two labels
round a picture are printed on top of each other — which immediately found a
third, a date label across the axis zero on the new page.

### 🧾 Also

- A **new example page** for the wander-off-and-come-back run, and one for the
  drift heat-map, so both can be looked at rather than taken on trust.
- The page generator left three folders of demo profiles behind on every run —
  88 MB after an afternoon. It clears them when it passes and **keeps them when
  it fails**, because then they are the evidence.
- Every page now carries a ceiling of 12 traces, so hundreds cannot come back
  quietly.
- 670 checks, up from 658.

## v2.17.0

### ⏱ Follow one device through many profiles, not just two

Basti, re-reading the request this came from: the person probably wanted drift
**in intervals** — several profiles over time, not one pair.

**Follow one device over time…** opens a window holding as many profiles of one
device as you have. Two lines: how far it has moved **altogether** since the
first, and how far it moved **since the one before**.

**Both, because they disagree by design.** Measured on five profiles of one
scanner drifting evenly:

| | | | | |
|---|---|---|---|---|
| against the first | 0.55 | 1.08 | 1.68 | 2.19 → **2.67** |
| against the previous | 0.55 | 0.53 | 0.60 | 0.50 → 0.49 |

Read only the second and the answer is "nothing is happening, every year looks
like the last". Read only the first and steady creep cannot be told from one
bad year followed by four quiet ones. Showing one of them would mislead in one
of the two directions.

That difference is the useful one, so the window says which it is outright.
Even steps mean the device will keep creeping. **One big step means something
happened** — and the page then names the dates it happened between, because
that is a thing you can go and look up, where a trend is only something to
worry about.

**The axis is spaced by real time**, not evenly, and this is not a nicety: an
axis that puts 2019, 2020, 2021 and 2024 at even intervals draws a steady line
through a device that was quiet for three years and then moved. The slope is
what people read off it. If any profile carries no usable date the list keeps
the order you added them in and says so — sorting some by date and guessing at
the rest would look authoritative and be partly invented. Drag a row to move it.

**A build stamp is not a measurement date.** Several profiles that ship with
macOS carry `2022-01-01 00:00:00` exactly. Ordering a run by that would invent
the history you are trying to read, so it counts as no date at all.

Nothing is installed for any of this — profiles are read directly.

**What it cannot tell you, said under the graph rather than only behind the ⓘ,**
and saved into the exported page: this is how far apart the **profiles** are,
not how far the device drifted. Each is one day's measurements of one chart, so
chart fade and any change in how you built them are inside these numbers too. A
line climbing steadily is just as consistent with charts ageing as with a
device drifting. A trend line is the kind of picture people trust more than
they should.

Things it refuses or points out rather than drawing quietly: profiles of two
different kinds of device (there is no "over time" between them), a file that
will not read (named, with the rest of the run still shown), and the same file
added twice (which gives a clean zero that reads as good news and is a slip).

Three new examples on the showcase page — a printer drifting steadily, the same
run with one profile missing, and one that moved all at once (0.18, 0.18,
**5.05**, 0.17).

### 🔬 Compare two ICC profiles, which a gamut cannot do

From a request Basti forwarded: somebody has two profiles of one scanner made
years apart and wants to know what has changed.

**A gamut comparison cannot answer that, and it is worth being precise about
why.** Two profiles can enclose almost exactly the same shape and send the
colours inside it to quite different places. Measured on a pair differing only
in tone curve: **0.011% apart by volume** — the same shape for any purpose a
volume is put to — and up to **ΔE 4.2 apart inside**. For an input profile
such as a scanner's, the inside is nearly the whole profile, so the shape is
the part that matters least.

Open two profiles and the **Has anything changed?** box now answers for them,
the same box that already answers for two measurements — because to the reader
it is one question. Both profiles are asked for the same 729 colours and the
answers held side by side.

**It needs nothing installed.** The profiles are read here, so this works on a
machine with no ArgyllCMS at all.

**Show me where, in the picture** draws every colour at the place the first
profile puts it, painted by how far the second sends it instead. The numbers
say how much; this says where, which is usually the more useful half — "average
ΔE 2" reads the same whether a device drifted a little everywhere, which points
at calibration, or hardly at all except in the deep blues, which is a different
problem entirely. The scale is fixed rather than stretched to the data, so the
same colour means the same amount in every picture, and the key is labelled in
words because ΔE is not a unit anybody has intuitions about.

**The honest caveat, and it is in the help text as well as here:** this is how
far apart the two PROFILES are, not how far the device drifted. A profile
records one day's measurements of one chart. If that chart faded between the
two, or they were built with different settings, that is inside the number too,
and no arithmetic can separate it out.

Things it refuses rather than answering, each with a reason worth reading:

* **An RGB profile against a CMYK one.** 50% grey asked of one is not the same
  request as asked of the other, so pairing them would give a confident figure
  describing nothing.
* **Two profiles read through different tables.** A colorimetric table against
  a perceptual one differs by a large amount that has nothing to do with drift,
  because perceptual rendering moves colour on purpose. Measured on real files:
  ΔE 45 worst, 12.7 average, and meaningless. The window says so in front of
  the numbers, and the picture stays away — a picture of a meaningless number
  is worse than no picture, because it looks like evidence.
* A file that is not a profile, and a truncated one.

A profile compared with itself comes out 0.00 everywhere, which is the check
that proves the two sides are being asked the same question at all.

### 🔎 ArgyllCMS was not looked for where people actually put it

Prompted by Basti: *"we have to make sure the app can reliably detect argyll
on the users system or allow him to point at it. on my mac it is installed in
a location most people would probably not install it in."*

His own install was found — but testing the search rather than trusting it
turned up a row of ways it could fail for somebody else.

**The PATH is nearly useless inside the bundled application, so the folder
list carries the whole weight.** Measured on macOS: `launchctl getenv PATH` is
unset, so an app started from Finder inherits launchd's default of
`/usr/bin:/bin:/usr/sbin:/sbin` — not the shell's. On a machine with ArgyllCMS
in `/Applications/Argyll/bin` **and** on the login shell's PATH,
`shutil.which("xicclu")` still answers `None` inside the bundle. That makes
every gap in the folder list a tool that cannot be found, however carefully it
was installed. The gaps, all confirmed by measurement:

* **Downloads, Desktop and Documents were not searched at all.** The official
  build is a zip, and what people do with a zip is unpack it and leave it
  where it landed. Now covered on all three platforms, plus the OneDrive
  redirection of Desktop and Documents that a great many Windows machines
  have.
* **Homebrew is a real way to get it and was only half covered.** The
  `argyll-cms` formula does `prefix.install "bin"`, so the tools are symlinked
  into `$(brew --prefix)/bin` — and it ships `arm64_linux` and `x86_64_linux`
  bottles, so Linux Homebrew is an ordinary installation and not a curiosity.
  `/home/linuxbrew/.linuxbrew/bin` is now searched, and `HOMEBREW_PREFIX` is
  honoured for anyone who moved it.
* **`Argyll_V3.10.0` lost to `Argyll_V3.5.0`.** Folder names were sorted as
  text, which compares `5` against `1` as characters, so somebody with two
  versions installed was handed the older one. The digits are read as numbers
  now. The existing test compared `V2.0.0` with `V3.5.0`, where sorting as
  text gives the right answer by luck — so it passed while the ordering was
  wrong.
* **A lower-case folder was invisible on Linux.** Linux filesystems are
  case-sensitive, so a search for `Argyll*` never matched `argyll` or
  `argyll-cms` — which is what a tarball unpacks to and what a distribution
  package installs.

### 🖱 The obvious folder to choose was the one being refused

Picking `/Applications/Argyll` — the folder with the name on it — was turned
down with "that folder does not hold the tools", because only the `bin` folder
inside it was accepted. `bin` is our detail, not the user's. Both are taken
now and the right one is worked out for them.

Two other things about that button:

* **"Not found" says where it looked.** A bare "not found" invites the reply
  "well, did you look in…?", and this is the answer to it. It names the places
  searched rather than the folders found, because on a machine with nothing
  installed the folder list cannot mention Downloads at all — and that is
  exactly the machine whose owner needs telling it was looked in. Nothing is
  named that does not exist on this machine, since a Mac told that
  `C:\Argyll\bin` was checked reads it as a fault rather than as diligence.
* **A tool that is present but will not run is no longer reported as
  missing.** A zip unpacked by something that does not carry Unix permissions
  leaves every program in place and none of them runnable; calling that "not
  found" sends somebody looking for the wrong problem entirely.

### 💬 A long message box cut its own buttons off

Found while checking the above on screen rather than reading the string: the
"not found" message had grown by a dozen lines, and both buttons came up with
their right-hand ends sliced away.

The cause is a Qt behaviour worth writing down. **A word-wrapping `QLabel`
does not ask for the width its longest line needs — it asks for a width that
keeps the block from becoming absurdly tall, so the more text it holds the
wider it wants to be, whatever the lines say.** These message boxes are a
fixed 470 points across, so the request could not be granted and the layout
silently overflowed: 610 points wanted against 470 given. Nothing warns about
it; the dialog simply comes up wrong.

The text is now told its width instead of asked for one, so the box grows
downwards as it always should have. This was never specific to the new
message — every message box in the application was one paragraph away from it,
and the short ones fitted by luck rather than by design. The card's own 1-point
border is counted in as well, which is a further two points and by itself
enough to clip a button.

## v2.16.0

### 🕳 "Does this colour fit" was asked of a shape with the dents filled in

Found by somebody looking at a published page on a phone and saying that a
part of it plainly did not agree with Adobe RGB and yet refused to stand out
when the agreement was faded. Twice I answered that it was correct. It was
not.

Containment was `Delaunay(points).find_simplex(p) < 0` — and a Delaunay
triangulation tessellates exactly the **convex hull** of its points. So the
question being asked was "is this inside the convex hull", which is the same
question only for a convex gamut, and no gamut is convex. Measured on Adobe
RGB:

* **89.2%** of its own surface points lie strictly inside its own convex hull,
  by as much as **3.9 Lab units**;
* the hull encloses **6.1% more volume** than the space actually holds.

Every hollow was being filled in and counted as reachable colour. What that
cost, on the demo pair:

| | hull | real surface |
|---|---|---|
| paper vertices outside Adobe RGB | 191 | **239** |
| triangles shown as disagreeing | 300 | **392** |
| coverage of Adobe RGB | 91.70% | **90.72%** |

**Every one of the 48 disagreements went the same way** — a colour the paper
reaches and Adobe RGB does not, reported as agreeing. The error always
flattered the comparison.

It is now measured against the actual surface, by casting a ray and counting
crossings, which needs a closed surface and nothing else — no convexity, no
consistent winding. That the surfaces *are* closed was checked rather than
assumed: welded by position, the demo paper and every reference space have no
edge used once and none used more than twice.

**It is faster than what it replaced**, which was not the expectation going
in. Containment 31 ms → **17 ms**; coverage 182 ms → **65 ms**, because the
sample points are now drawn straight from inside the solid — cutting it into
tetrahedra and picking one in proportion to its volume — instead of being
thrown at the bounding box and sieved.

Three things it had to get right, each found by a shape whose answer was known
before any measurement was allowed near it:

* **a colour on the boundary is in the gamut.** A gamut is a closed set. This
  is not a nicety: placing a chart through a profile and asking whether it
  lands inside that same profile puts 98 of 125 patches exactly on the
  boundary, and judged by ray parity alone — which cannot answer for a point
  on the surface — 61 of those came out "outside". The convex hull never
  showed this, because its bulge put every boundary point comfortably inside.
* **the surface is turned before rays are cast.** A face standing exactly
  parallel to the ray projects to a line and is discarded as edge-on, so a
  point lying on it is seen by nothing — the side of a cube answered
  "outside". Turned by angles with no common measure, no face can be parallel
  to the ray.
* **a ray running along a shared edge is counted twice.** The centre of a cube
  projects precisely onto the diagonal where two triangles of a face meet, so
  the first answer this ever gave for the middle of a cube was "outside".

Volume was already right — `mesh_volume` sums the real tetrahedra — and that
was re-checked here against Monte Carlo at 400,000 points and against the
surface being star-shaped, which it is.

The reported figure for the demo pair moves from 76.4% to **77.4%**.

### ✂️ The fade was a slope where the answer is yes or no

The same reader, on the same page: *"parts of where they agree do not become
transparent — the cut so to say should be more straight."* Two separate faults
were doing that, one on top of the other.

**The mask was dilated.** The surface is faded with an alpha per *vertex*, and
that alpha was worked out by taking the per-*triangle* answer and marking
every vertex those triangles touch — so a vertex sitting comfortably inside
the other gamut was painted as standing out because one triangle beside it
did. Measured on the demo pair: **239** vertices are genuinely outside Adobe
RGB, **335** were painted as though they were. 96 of them — a seventh of the
whole surface — drawn as disagreement where the two agree, and every error the
same way.

**And what was left was still a gradient.** With the alpha per vertex, a
triangle with two corners agreeing and one not has that difference painted
smoothly across its whole width. Of the glossy paper's 978 triangles:

| | triangles | |
|---|---|---|
| wholly agreeing | 586 | |
| wholly differing | 219 | |
| **straddling the boundary** | **173** | **19.9% of the surface, 16.5 Lab units across on average, worst 36.2** |

A fifth of the shape was a slope standing in for an edge. That is why turning
the agreement down thinned a wide band instead of opening a clean hole.

Both shapes are now **re-cut along the boundary before anything is faded**.
Each straddling triangle is split where the two surfaces really cross — found
by bisection on the containment test, so it works for one other shape or for
six — and the new corners are made **twice**, once for each side. Every
triangle is then one flat colour at one flat alpha, and the edge lies exactly
on the crossing curve.

It is still **one mesh**. Cutting the shape into a faded piece and a solid
piece was tried in an earlier release and left 120,481 pixels wrong, because a
browser blends two open surfaces in the order it draws them and that is not
what one closed surface does. Nothing here opens the surface; only the corners
are renumbered.

Checked rather than assumed:

* triangles still straddling the boundary afterwards: **0** of 1,324 and 0 of
  4,760;
* volume and area unchanged to **seven figures** (+0.000033% and +0.000000%);
* every one of the 692 and 856 new corners sits on the other surface to within
  a **thousandth of a Lab unit**;
* the drawn cut leaves the true crossing curve by a median of **0.002 Lab**
  (paper) and **0.000** (Adobe RGB) — 236 of 346 and 258 of 428 cut edges are
  exactly straight, which is what a flat facet should give;
* fading the *disagreement* instead gives the identical edge: the two hidden
  sets are exact complements, and the two halves add back to the whole surface
  with **nothing drawn twice and nothing missing** — same triangle count, same
  area, and rims that match edge for edge (173 edges, 857.1 Lab long).

**The saved page nearly lost all of this.** Two corners in the same place
survive the weld only because the fade has already given them different
colours — and a page is written at *full* strength, where they are the same
colour. They welded back into one and **361 of 1,324 triangles straddled the
boundary again**, so the picture on screen was right and the page somebody was
sent was not. The side a corner is on is now part of what makes it that
corner.

At full strength the page differs from before by **1,252 pixels of 3,936,000**,
all of them on one curve: a shape drawn as a wire cage gains the cut edges as
wires, which trace exactly where the two shapes cross. The surface itself is
pixel-identical.

### 📏 The cut through a gamut was taken through the hull, not the gamut

The same fault as above, still in place in the one picture whose entire
purpose is showing where one paper reaches further than another. `slice_at`
found its outline with `Delaunay(v).find_simplex` — the convex hull again — so
every dent was filled in before the outline was drawn.

Measured on Adobe RGB, at seven lightnesses from L\* 20 to 80:

| | |
|---|---|
| directions where the hull outline stood outside the real one | **138 to 159 of every 180** |
| worst overshoot | **10.05 Lab units** |
| slice area | **+4.6%** |

Wrong everywhere, always outwards, and worst at the light and dark ends where
two papers differ most.

A plane crosses a triangle in a straight line, so the cross-section of a mesh
can simply be computed rather than searched for. There is now no bisection, no
containment test and no triangulation to build — and it is **68× faster**: one
cut 54.4 ms → **0.8 ms**, and the whole set a page carries 3,588 ms → **52 ms**.

Checked against the containment test the rest of the window uses: 1,440 points
of the new outlines, on both demo shapes, at four lightnesses each — just
inside every one of them is inside the gamut and just outside is outside.
**None wrong.**

Whether a gamut's slice is star-shaped about its grey axis was measured rather
than assumed: over 15,300 rays through both demo shapes, exactly two met more
than one boundary.

Both ends of a shape now behave alike. A cut has to say which side a corner
lying exactly in the plane is on, and whichever it says, one end of the shape
draws an outline and the other draws nothing — a box cut at its ceiling
returned the outline of its top face and the same box cut at its floor
returned nothing at all. Neither end is offered now, because at the very top
of a real gamut the cut is the single point of the paper white.

### 🧮 Three more answers were still coming from a convex hull

Found by sweeping every remaining use of `ConvexHull` and `Delaunay` rather
than waiting for the next photograph of a phone.

**"Both can print N% of everything either one can"** was wrong twice over.
`shared_volume` asked `ConvexHull` for both sizes *and* handed `coverage` the
bare vertices — stripping off the very triangles that tell it what the surface
is, so that fell back to the hull too. Three hull answers in two lines, in a
panel whose other rows had already been corrected. The hulls hold **8.3%** and
**6.1%** more than the shapes do; the sentence read **51.84% where the truth is
50.03%**, next to two percentages that were already right.

**A patch could be called outside and, in the same row, 0.00 ΔE from the
boundary.** "Is this patch outside?" is asked of the real, dented surface; the
distance beside it was measured to the hull thrown around it, which lies
outside the shape wherever the shape is dented. On the demo chart against
Adobe RGB, 1 of 172 patches came back at 0.00 — one row in a table, and it
would have been read as a rounding error rather than the two halves of a row
disagreeing about what the boundary is.

**And the help text still described the old behaviour.** It said the test was
against the convex hull and was therefore conservative — "it can miss a
problem; it cannot invent one". True of the hull, and no longer what happens:
the dents hold **172 patches the hull called safe**, and saying which patches
are not safe is what a chart is for.

### ⚡ The containment test, which everything here rests on, is much faster

Correcting the arithmetic made the picture right and the redraw slow: a faded
scene took **268 ms** where an unfaded one takes 19 ms, because deciding where
two shapes part company asks the containment test sixteen times over while it
bisects. Three changes, none of which give up a decimal place.

**Every point at once, instead of one grid cell at a time.** The test buckets
triangles into a 48×48 grid so a colour is only compared with the few
overhead. It then walked the cells in Python — and with a few hundred points
spread over 2,304 cells that is a few hundred passes through numpy on a
handful of rows each, where the arithmetic is the small part. Every candidate
pair is now built as one flat list and tested in a single stroke, and the grid
itself is built the same way rather than by three nested loops.

**The surfaces are prepared once.** A faded scene prepared **four where two
would do** — once to decide which vertices stand out, again to find where the
boundary crosses each edge.

**Sixteen halvings, not twenty-four.** The longest edge on either demo shape
is 36 Lab units, so sixteen place the cut within **0.0006 Lab** of the true
crossing — a thousandth of the smallest difference a good eye can find. The
other eight bought decimal places nothing can measure and a third of the time.

| | before | after | |
|---|---|---|---|
| containment, 675 colours | 9.9 ms | **0.6 ms** | 17× |
| preparing a surface | 6.6 ms | **2.3 ms** | 2.9× |
| re-cutting both shapes | 243 ms | **16.6 ms** | 14.6× |
| **a faded scene** | **268 ms** | **43 ms** | **6.2×** |
| a saved page | 274 ms | **50 ms** | 5.5× |

A faded scene is now 2.2× an unfaded one rather than 14×.

**The rewrite was proved identical, not assumed to be.** Old and new were run
against each other on **111,000 colours** per shape — random ones, ones far
outside, the shapes' own vertices, every triangle centre (all of which sit
exactly ON the surface, where this is hardest), and the empty case. **Zero
disagreements.** A test also pins that answering 1, 2, 7, 999 or 100,000 at a
time gives the same answer, because blocking is the one way a change made
purely for speed could quietly change what the picture says.

### 💬 Nobody was told how to get a saved page to anybody

Asked while looking at the save dialog: where does it say how to use this in a
forum post? It did not, anywhere. The dialog said only that the page opens in
any browser.

The honest answer needed saying, including the part that is a flat no. **A
forum will not show this inside a post**, and most will not take it as an
attachment either -- deliberately, because a web page can carry a program and
no forum can afford to run a stranger's. What works instead is a picture in
the post and a link underneath it: people see what you mean without clicking,
and anyone who wants to turn the shape themselves can. For that, *Fetch it
when opened* makes the file about 4.7 MB smaller, which is the difference
between something you can upload almost anywhere and something you cannot.

Two short lines under the switches, and the long version behind the ⓘ beside
**The file** -- where it costs no room that a control could have used. The
picture dialog now names the page export too, so each says when to reach for
the other rather than leaving somebody to guess which of two exports they
wanted.

### 📱 Two thirds of an iPad screen was black, and the controls were scattered

Reported from an iPad, and then found on a Mac in Safari too. Two faults, both
only visible in WebKit or only on a wide screen -- which is to say, never in
the engine every picture in this project had been rendered in.

**The picture was drawn at 450px on a 1366px screen.** The box holding it keeps
`height:auto` on purpose, so a page can grow past the window. But the drawing
library gives its own div `height:100%`, and a percentage height only resolves
against a parent whose height is DEFINITE. Chromium resolves it anyway against
what flex worked out; WebKit follows the stricter reading, finds nothing to
take a percentage of, and falls back to the library's built-in 450. Measured on
the same page in a 1024x1366 window: the box 1128px tall in **both** engines,
the picture inside it 1128 in Chromium and **450 in WebKit**.

The box is a flex column now and the picture a flex item, which takes the
percentage out of it. It is also **capped at 80vh** -- the first attempt let it
grow and it filled the screen edge to edge in WebKit at every size tried,
pushing the control strip below the fold, which is the very thing the 62vh
floor exists to prevent. Checked across ten window sizes from 320x700 to
2560x1440 in both engines: 62-80% of the first screen everywhere, never a black
third and never a picture with nothing under it.

**And a control sat a long way from the name it belonged to.** The rows were
`justify-content:space-between`, which pins the name left and the buttons
right. In one column that reads well; the lists flow into as many columns as
the width allows, and on an iPad held sideways that is four columns of about
257px, with the buttons some 150px from the word they act on. Worse, a shape's
name was set to grow and took every spare pixel, so its four controls wrapped
onto a second line -- under a name, beside a different shape's name. Reported
as "I had issues finding the glossy paper controls".

The name now takes what it needs up to a ceiling and the buttons follow
straight after it, with a real gap kept so the two do not read as one object.
Measured on the same ten sizes in both engines: every gap **12-14px**, down
from about 150, and no shape row wraps at any width from 844px up. Below that
-- a phone held upright -- a name and four buttons genuinely do not fit on one
line, and it still wraps, which is right.

Found with Playwright's WebKit. Every render in this project had been Chromium,
and Chromium is the engine that is lenient about all of this.

**And a row of controls still wrapped, by seven pixels.** The fix above was
checked at ten sizes and passed; then the check was pointed at more of them and
two failed -- a phone held sideways (844x390) and a window dragged down to a
strip (1000x360), in both engines. The columns these lists flow into have a
minimum width of 230px, which is right for a group of switches and too narrow
for a group whose rows carry five controls. Measured rather than reasoned
about: **"left & right" needs 452px and was given 445**, and where a row does
not fit, its controls wrap under the name -- which in two columns puts one
row's buttons level with the next column's name, the very confusion this was
rearranged to answer.

The two groups that hold wide rows now ask for a column wide enough for the
widest row they actually contain, clamped to the width available so a phone
still gets one column rather than a page that scrolls sideways. All ten sizes
pass in both engines.

### 🪟 The save dialog opened off the bottom of a Windows screen

The ceiling added to this dialog earlier in this release was put in the wrong
place, and only Windows could show it. It capped the height of the scrolling
LIST -- and capping the part that scrolls does not cap the window, because
everything else in the dialog is fixed and how tall that comes out depends on
the platform's fonts and margins. Measured on the CI runner: the same dialog
that fits comfortably on macOS opened **874 points tall on an 800-point
screen**, with the list already at its cap and the Save button below the bottom
edge. Exactly the fault the cap was added to prevent.

The ceiling is now on how tall the window OPENS, which is the thing that
actually has to fit, and the list keeps only a floor so it can give up height
on a short screen. There is no maximum on the list at all any more, so dragging
the dialog taller still hands it every pixel -- which is what was promised and
was not true.

Two smaller faults fell out of measuring it. The resize was being done inside
`showEvent`, before the layout had run, so the layout put the height straight
back -- 676 points from a call that had asked for 600. And the note along the
bottom was set to expand: **252 points for two lines of text needing 79**,
taken from the list directly above it. Both fixed; the list now gets 323 points
where it got 150.

It was found because the release build's Windows leg had been failing and the
failure had been pinned around rather than read. The pin is gone.

### 🎈 A saved page can carry on turning when the reader lets go

Asked for after using a page on an iPad: a shape that stops dead the instant a
finger lifts does not feel like an object -- "not like crazy after letting go,
just a bit to make it feel natural".

Two new controls when you save a page. **Whether the page has it** decides how
the page behaves when it opens; **whether the reader may switch it** decides
whether they get a button for it. Off, a page behaves exactly as every page
saved before this one did.

WHAT IS MEASURED IS THE CAMERA, NOT THE FINGER. Turning a drag in pixels into
degrees needs a constant this page does not own -- the drawing library decides
for itself how far a drag turns a scene -- and guessing it makes the throw
leave at a different speed from the drag that caused it. So the camera is
sampled several times a second during the drag instead, which is right by
construction on any device at any speed. It also excludes panning and zooming
for free: sampling the eye's DIRECTION means a pan (eye and centre move
together) and a zoom (only the distance changes) both come out as no movement,
with no special case to write.

HOW FAR IT CARRIES. The speed dies away with a half-life of 0.22s -- the same
feel as the convention nearly every 3D viewer on the web follows, taken from
the three.js source rather than from memory. Said as a half-life on purpose:
three.js applies its damping per FRAME, so the same page dies twice as fast on
a 120Hz iPad as on a 60Hz laptop, and an iPad is where this was asked for. The
speed is capped so that no flick, however hard, carries more than about 48
degrees -- an eighth of a turn, plainly a follow-through. The first cap tried
was three times that and measured **102 degrees** past the drag, which reads as
the shape having been let go of rather than carried.

Touching the shape stops it, and so do Pause, "look from" and "reset view". It
is never offered on a saved cross-section, which is drawn flat and cannot be
turned at all.

Proved in a browser rather than argued for: `scripts/check_momentum.py` drags
the shape in WebKit and Chromium and checks that it carries on, that it stops
on its own, that it can be caught mid-throw, that a drag which pauses before
letting go throws nothing, and that with the option off nothing moves at all.

### 📉 Five figures the README states as fact were wrong

Found by checking them rather than by reading them. Every percentage the front
page quotes was recomputed from the demo files:

| the README said | the truth |
|---|---|
| 77.7% of the paper fits inside sRGB | **75.9%** |
| 65.2% of sRGB fits inside the paper | **64.3%** |
| both can print 76% of everything either can | **77%** |
| 97.2% of the measurement fits inside its profile | **96.4%** |
| 83.9% of the profile fits inside the measurement | **82.6%** |

Four of the five were flattering, which is the convex hull's signature -- they
had been written from a containment test that filled in every dent. The fifth
moved because `shared_volume` was wrong in the other direction.

They are pinned by a test now, recomputed from the demo files and compared to
half of the last place the sentence actually quotes, so prose cannot drift
away from the code again. The same test covers the volume and the two ends of
the demo paper under the first picture. It was checked by putting an old
figure back and watching it fail, because a test that cannot fail guards
nothing.

The test that pins them had to be corrected before it was any use: its first
version allowed half of the last place the README quotes, on the reasoning
that coverage uses a fixed seed and repeats to the digit. It does -- on one
machine. It failed the release build within minutes, because `build_gamut`
triangulates the device cube with Qhull and Qhull resolves a flat run of
points differently between builds: the same measured points, slightly
different triangles, and every figure taken from the surface moves a little.
Between this project's development machine and its Linux builder, the demo
paper's volume differs by 36 cubic Lab units in 702,327 (**0.005%**) and the
coverage figures by up to **0.25 percentage points** -- comfortably inside the
sampling error already printed beside them, and now written down where the
figures are produced. The allowance is half a point, which sits cleanly
between that and the 0.8-to-1.8 points of real staleness this found.


### 🧹 The window left 27 GB of scenes behind

Reported as a disk filling up: 30 GB gone in two days. It was this.

Every redraw writes a self-contained page with plotly.js inlined — about
**6 MB** — under a name that counts up, because reloading one URL let the web
view serve its cached copy and switching to light left the scene dark. Nothing
ever deleted them, and the folder holding them was never removed either,
though the comment beside it said it was. **644 folders, 27 GB.**

Three fixes: the scene from two redraws ago is deleted, which caps a session
at two files however long somebody works; the folder goes when the window
closes, which is what it always claimed; and a starting window clears folders
left by runs that crashed or were killed. That last one writes down its own
process id and keeps any folder whose process is still alive, so two windows
open at once cannot delete each other's scenes — with age as the fallback
where there is no id to ask about.

### 📊 A card on the showcase quoted a figure nobody checked

`docs/index.html` said **76.4%** of the glossy paper fits inside the matte
where the window now says 77.4%. The generator that writes those pages exists
to catch exactly this and reported every claim met: it checked which of the
two papers fits inside the other, and never the number. It checks the number
now.

## v2.15.1

### 🧊 One press hung a published page, and reloading did not help

Reported from a phone against the showcase page comparing a paper with Adobe
RGB: *"it hung as soon as I tried to reduce opacity of where they agree. Then
I could not get it back to work, not even by re-loading the page."* The page
had **loaded quickly** — it was only the press.

That page is not big. It carries 491 vertices and 978 triangles, the same as
every other. What is different is the number of **traces**: a cage drawn in
true colours needs one trace per colour, because a line takes a single colour
for its whole length, so the Adobe RGB cage is 347 of them where every other
demo page has between 2 and 12.

And the code that re-dresses a shape called the drawing library **once per
trace**. Measured on a desktop with a real graphics card:

| page | traces | rebuilds asked for | one press took |
|---|---|---|---|
| everything handed over | 4 | 5 | 0.3 s |
| **a paper against Adobe RGB** | **348** | **349** | **36.4 s** |

Three things were wrong, and all three are fixed:

* **One instruction per shape, not one per trace.** Traces are gathered by
  which fields they need — and by which graph they belong to — and handed
  over together.
* **Only what is actually different.** Setting a trace to the value it
  already holds rebuilds the scene to draw exactly what is on it. Fading
  where two shapes *agree* touches one surface, and was rewriting the
  strength of all 347 cage traces as well. "Not stated" now compares equal to
  "fully solid", which is what it means — without that, the very first press
  still rewrote all of them.
* Together: **349 calls and 36.4 seconds became 2 calls and 0.3 seconds**,
  and the two remaining calls are the surface's own colours and the
  depth-sort that keeps a see-through shape drawn in the right order. Both
  are work that has to happen.

The picture is unchanged, which was checked rather than assumed: the press
still moves 51,918 pixels, pressing back returns it exactly, the cage keeps
its 297 distinct colours across 346 traces, and the surface keeps one colour
per vertex — 310 faded and 181 solid, matching the page's own mask exactly.

### 🪞 A shape drawn at two strengths could never come back

Found by the audit, on the ink-amounts page. A chart's skin is a surface at
**0.3** with a cage over it at **1** — one shape, two traces, two strengths.
The shape's strength was read off its *first* trace and written to all of
them, so the first press of anything flattened them onto one number:

```
during the fade:     cage 0.2   (with the skin)
after putting back:  cage 0.3   ← it opened at 1
```

11,537 pixels different on a page whose noise floor is 0 — and **as saved**
could not restore it either, because the value it restored to was already
wrong. Each part now keeps what it opened at and the slider applies as a
ratio of it, so at the strength the page was saved with every part is handed
exactly its own value back. Re-measured: **0 pixels**.

### ✂️ The cut slider redrew the shape cruder than the page opens

The cross-sections are drawn at `slice_at`'s default of 180 steps, and the
outlines carried for the reader's slider were worked out at 120 — on the
reasoning that the difference cannot be seen. That is true of two outlines
side by side and false of one page that swaps between them: the first press
of the cut coarsened the shape from 181 points to 121, and moving the slider
back did not restore it, because the fine outline was gone.

Matched, at 73 kB on a 4.9 MB page — **1.45%** — so the page agrees with
itself. What is left after that is the deliberate rounding of the stored
outlines to a hundredth of a Lab unit: every point returns to within **0.005**
Lab units, a fiftieth of what a good instrument repeats to.

### 📐 "How it looks" was cut off on its right-hand side

Reported from a screenshot of the real window. Every other section in the
controls column is 346 px wide; that one is **372**, because *"Show what the
comparison cannot print"* is 270 px of label that a tick cannot wrap and the
ⓘ has to sit beside it. The column was pinned at 346 and the scroll area at
366 with its horizontal scrollbar deliberately off — so the section was
simply cut: its right-hand border gone, and about four pixels of that row's
ⓘ with it.

The column now takes its width from its widest section, with 346 as a floor,
settled after the window is polished — before that every section still
answers 363 and the fault survives at one pixel instead of sixteen. The audit
checks it from now on, because a clipped control passes every press test
there is.

### 🔓 A remembered choice can no longer shut the reader out

The second half of that report is the worse half. What a reader chooses is
remembered and applied **while the page is opening**, so the press that hung
the page was replayed on every reload — and reloading is the only thing a
reader can do. There is no console on a phone and no menu on the page.

A mark is now written before the stored choices are applied and before every
press, and taken off a frame later. Finding it still set means the last
attempt never finished, so the choices are thrown away and the page opens the
way it was saved — which is always a state that works, because it is the
state the file was written in. Proved in a browser: a page put into exactly
the state a hang leaves behind comes back at 100% on **one** reload.

This is a guard, not a cure. The rebuild storm above is the cure; this is so
that the next thing nobody predicted cannot cost somebody their page.

### 🎨 The figures under the picture follow the page colours

Spotted in the new picture of the five colourings side by side, which is the
argument for making that picture at all. The written-out numbers are put in
the file with their colours stated on the element, from the palette the page
was saved in — so they never followed. A page saved dark and switched to
light kept a black block of text under a pale picture, and on **ink**, the one
colouring that exists to be printed, it left a solid black rectangle across
the bottom of the page.

### ⬜ The neutral ground is now measurably neutral

**slate** exists to be judged against: *"a gamut on black looks brighter than
it really is and one on white looks duller."* Every part of it was a blue-grey
of about 4 units of chroma — small to look at, and working against precisely
that, since a faintly blue surround pushes a neutral towards warm.

Each part is now the neutral grey of **the same lightness it had**, to a tenth
of an L\* unit, so every contrast inside the scheme is exactly what it was and
only the cast is gone: the ground goes `#6e7278` → `#727272`, L\* 47.9 → 48.0,
chroma 3.8 → 0.0.

### 🔡 The page-colour button dimmed the lettering and never put it back

Found by the release audit that shipped in v2.15.0, on its first full run.

Pressing the new colour button and going all the way round — dark, light,
none, slate, ink, dark — left the page **6,264 pixels different from the one
it opened as**, with the button reading `dark` again and the page reporting
every one of its colours correct. Going round a second time landed on exactly
the same picture, 0 pixels from the first lap, so nothing was accumulating.

The axis numbers and names were the difference. They were never *declared*:
each axis kept the drawing library's own default of `#444` and the lettering
was drawn in the page font instead, which looks right and is not the same
thing. The first relayout resolved them properly — and the colour button set
them to `caption`, the dim grey the small title line uses, rather than to
`text`, the colour the page is read in.

So the first press faded every axis number and name, and coming back to the
colouring the page was saved in did not bring them back: a page somebody had
looked at no longer matched the page that was sent.

Both halves are fixed — the figure now says what colour its lettering is, and
the button keeps it. Measured on the real page, the same lap now leaves **0
pixels**. A title is still drawn as a caption, because a title is one.

### 🔍 The audit checks four things it used to excuse, and three it could not see

The audit's own tables named **six controls that do not exist**: `fullscreen`,
`picture`, `legend`, `remember`, `speed` and `sweep` are switches in the save
dialog, and the buttons they produce are called `full`, `shot`, `key`, and a
pair of steppers. Six excuses matched nothing, while the buttons they were
meant to excuse were judged by the ordinary rule. `test_audit_script.py` now
fails on a name no button has — so this class of quiet rot cannot come back.

Three real improvements came out of fixing that:

* **Speed and sweep are checked, not excused.** They only show themselves
  while the shape is moving, and the audit measures it stopped — so the
  honest verdict used to be "cannot be seen from here", and a control excused
  is a control never tested. Each writes its value beside itself, so it is
  read: press it, the number moves; press the opposite, it comes back.
* **A hidden shape's controls are tested.** A page can hold one shape inside
  another with the outer one solid, so fading the inner one changes not a
  pixel. Asked of the drawing rather than the picture, the answer is exact —
  that shape's strength went from 1 to 0.9 — whether or not it can be seen.
* **A cycle is recognised as one.** The colour button walks five colourings,
  so pressing it twice lands three short of where it started; judged as a
  switch it reported 42,244 pixels of "does not come back". Any button that
  renames itself when pressed is now walked round until its own name returns,
  which handles two states and five with one rule — and a sixth added later
  without editing the audit.

`--list` also stopped over-promising: it printed the twenty-two ⓘ explanation
folds, which a run has always skipped on purpose, so a third of the listing
named work that was never going to happen. The listing and the run now take
their names from the same function, and the listing says what it skips and
why.

**And it stopped crying wolf about the grid.** "Show the box and its grid"
had been reported as leaving ~314,000 pixels for several releases; the file
carried a paragraph admitting it and telling you to check by hand. It was the
audit's own bug. Turning the shape leaves it at a new angle on purpose, and
the camera was put back with `setCamera`, which moves what is on screen and
leaves the camera stored in the **layout** where it was — so the first
relayout inside the next control's test re-applied the old angle and undid
the restore silently.

The giveaway was in the numbers all along: `spin_on` and `grid_on` reported
the *identical* 314,313 pixels. One difference measured twice is not two
faults, and two independent controls agreeing to the pixel is not a
coincidence. Put back through `relayout`, which sets both, `grid_on` leaves
**11 pixels** and the window audit passes clean.

The audit also knows about the page that deliberately ships **without** the
drawing library, to show what a reader sees when it fails to arrive. Its
camera controls have nothing to move, so it used to report ten faults on the
one page whose subject is exactly that; now it checks that the page *says*
something went wrong, which is the only thing that page can be judged on.

### 📸 The README pictures are remade by one command

`11-controls.webp` — the picture of the controls column — was the one remade
by hand, from a throwaway file outside the repository, while the other two
had a script. It is in `scripts/make_doc_shots.py` now, along with a new
picture of the five page colourings side by side, which is the only way to
show a control that cycles. That strip is built by pressing the page's own
button until it comes back round, so a sixth colouring would appear in it
without anybody editing the script.

*(An earlier draft of this note claimed that picture had gone two releases
without the **Outline colour** row. It had not — the commit that added the
row is the commit that remade the picture, and regenerating it produced a
byte-identical file, which is how the mistake was caught. The reason to keep
it in a script is the ordinary one: nothing but somebody's memory was keeping
it current.)*

The five colourings are written up in the README as well, with what each one
is for.

## v2.15.0

### 🕸 Three controls that drew a wireframe drew nothing at all

Reported against a published page: *"I can't turn glossy to wires."* Measured
on that page, with the movement stopped and a noise floor of **0 pixels**:
pressing **wires** changed the picture by **0 pixels**.

All three were built on a surface's `contour` setting, which reads exactly
like "draw the mesh" and is documented by the drawing library itself as:

> Sets whether or not dynamic contours are shown on hover

It draws lines under the pointer and nothing whatever the rest of the time. A
surface with it on and the same surface with it off differ by **0 pixels**.

The other two were found by asking what else was built on it, and both are in
the window rather than only on a saved page. Measured against a page with no
skin on it at all:

| Chart skin | pixels drawn |
|---|---|
| Solid | 214,308 |
| **Mesh** | **214,308** — the same picture, to the pixel |
| **Outline only** | **5,251** — a surface at a fiftieth of strength, no lines |

So **Mesh was Solid under another name**, and **Outline only** was a nearly
invisible film rather than a cage.

There is no wireframe on a surface in this drawing library, so all three now
draw the edges themselves — each edge once, since a triangle mesh shares every
edge between two triangles and drawing both doubles the work for an identical
picture.

**On a saved page it costs the file nothing.** The surface already carries
every vertex and every triangle, so the cage is worked out from those the
first time the button is pressed — and it is drawn **in the colours the
surface itself is painted in**, which is the second half of what was reported:
*"clicking colourful … does not give them the same colour the shell would
have."* Pressing **grey** now takes the colour out of the net as well as the
surface, instead of the two controls contradicting each other.

### 🔗 Seventeen loops, and one page nothing linked to

`docs/motion/page-7.md` exists, holds **six of the seventeen loops** — more
than any other page — and **page 1 was the only page in the set that did not
link to it**. Every other page did.

Two counts were wrong beside it. The README said **"Eight more loops"** in one
place and **"Seventeen more"** in another; seventeen is right (eighteen files,
one of which is deliberately a still frame, the poster for the MP4). And
**"two to a page"** was true of six pages out of seven — page 7 holds six,
because they are all charts and read as a set. All three now say what is
actually there.

### 💥 Ticking a box crashed the window

Found by pressing every setting with a comparison loaded, which is the audit
that should have existed all along. Open a measured chart, set **Compare with**
to **Adobe RGB (1998)** — or sRGB, or any other named space — and tick **Show
every patch I measured**: the window came apart with *"too many indices for
array: array is 0-dimensional"*. Three clicks from an opened file.

A reference space is worked out from its own definition. It was never printed
and nobody measured a patch of it, so its place in the list of patch clouds is
empty — and the code that draws the clouds never checked. The greys directly
beside it already did, which is the whole of the bug.

### 🔺 A skin looks faceted, and that is the shape

Questioned, and checked rather than assumed. Long fan-shaped streaks across a
chart's skin are the **hull's own triangles**: it is stretched over a few
hundred scattered patches, so it is made of large flat facets meeting at real
angles, and each catches the light differently.

The test that settles it: drawn **solid**, the picture is made entirely by the
depth buffer, where no ordering happens at all — and the faceting is just as
strong there. **17.7% of its pixels sit on an edge solid, 19.4% see-through.**
Nothing about being see-through causes it. The help text now says so, because
a picture that reads as broken and is not needs to say which it is.

### 🚫 A control that had nothing to act on, and a page that said nothing

Both found by pressing every control on every published page.

**"Where they differ" was offered when nothing differs.** A shape that sits
entirely inside the others — the matte paper inside the glossy one does, at
every one of its 978 triangles — has a mask of nothing but zeros: everything
agrees and nothing differs. The control was still there, and pressing it moved
the picture by **0 pixels**, on two published pages. Each of the two fades is
now offered only when there is something on its side of the question.

**A page saved without the 3D viewer drew nothing and did not say why.** That
page fetches the viewer from the internet, which is what keeps it to a few
dozen kilobytes instead of about five megabytes. With no connection it opened
as a full set of controls over an empty box — seventeen of them, none of which
could do anything — and read as a broken file. It now says, in plain words,
that it needs the internet the first time, that nothing is wrong with the file,
and how to save one that works offline for good. The note appears only if the
viewer really is missing, four seconds in, so a slow connection never flashes
it up.

### ✅ And two that turned out to be the measurement, not the app

Reported here because a number that looked like a fault and was not is worth
the same honesty as one that was. Stepping a shape's strength down and back
up, and a cut down and back up, both left a few thousand pixels different —
but asking the page for the **number** beside the buttons showed they returned
exactly: 30% → 20% → 30%, and L\* 50 → 48 → 50. A picture rebuilt with the
same values is not pixel-identical at its edges. The audit now takes its floor
from a redraw that provably changes nothing, rather than from two idle grabs.

### 🧪 The audit ships with the application

`scripts/audit.py` — press every control there is, and say which ones do
nothing.

```
python scripts/audit.py            # everything
python scripts/audit.py --window   # only the window's own settings
python scripts/audit.py --pages    # only saved pages
python scripts/audit.py --list     # what it would test, and stop
```

It answers one question about each control: **when you move it, does the
picture change — and when you put it back, does the picture come back?** Three
controls in this application drew nothing at all for several releases, and no
test caught them because they all *ran* perfectly: the code executed, nothing
raised, the button lit up, and not one pixel moved.

**Nothing in it is a list of controls**, which is the whole design. The
window's settings come from `_persisted()` — the table the window already
keeps of everything worth remembering — plus `_shape_controls()`. A page's
controls are read out of the page itself. So a control added tomorrow is
audited tomorrow, by whoever added it, without touching the audit. If a new
control does *not* show up in `--list`, that is worth knowing too: it means
the window is not remembering it either.

**If you have taken only the 3D viewer**, `--pages --dir <anywhere>` presses
whatever controls your own saved pages carry. It knows nothing about gamuts.

Four rules keep it from lying, and each was learned by getting an answer wrong
first: the movement is stopped **through the page's own button** rather than
behind its back; the panel is **opened**, or it audits five buttons and calls
it a page; every kind is checked by **its own rule** (a switch comes back when
pressed again, a step when its opposite is pressed, a preset on *put the view
back*, and an action may change nothing but has to say why); and the floor is
**measured including a redraw**, because a picture rebuilt with the same
numbers is not pixel-identical at its edges.

It also switches a control's **parent** on first — the lightness of a cut
means nothing until there is a cut. Without that, eleven perfectly good
controls reported "does nothing", which is a report nobody can use.

Exit code is 1 on a finding, so it can gate a release.

### 🔍 And the audit that should have found them

These were found because somebody pointed at one of them, which is not an
audit. Every control on every published page is now pressed, with the picture
measured before and after against a noise floor, and each kind checked against
the rule that applies to it: a switch must come back when pressed again, a
step must come back when its opposite is pressed, a preset must come back on
**put the view back**, and an action is allowed to change nothing — with the
reason named rather than shrugged at.

## v2.14.0

### 🎯 Two see-through shapes are drawn correctly, not just less wrongly

2.13.0 shipped a known limitation and named it honestly: two shapes that cross
stayed **77.1% wrong at the worst of six angles**, because triangles could only
be put in order *within* one surface. The reason given was that the drawing
library draws one whole surface at a time and cannot interleave two.

That reason was right and the conclusion drawn from it was not. The library
cannot interleave two surfaces — so the shapes are no longer given to it as
two. Every see-through surface in a picture is handed to **one** drawn object
each frame and sorted as a single pool of triangles, all of them far-to-near.
The page still holds two shapes: the key, the hover, the visibility switches
and the saved file are untouched. Only what reaches the graphics card changed.

**The reference was checked before anything was measured against it.** Weld the
shapes into one surface in Python, before the page is written, and the question
disappears — one pool, one order, correct blending by construction. Welding the
other way round moves the picture by **0.00%**; rendering the same page twice
moves it by **0.00%**; and at a thousandth of transparency it agrees with the
*solid* picture — drawn by the depth buffer, which does no ordering at all — to
**1.0%**. Measured against it at **eight** camera angles:

| | no ordering | each shape alone (2.13.0) | one pool |
|---|---|---|---|
| two shapes, both at 0.55 | 76.2% | 68.5% | **0.0%** |
| two shapes, 0.55 and 0.30 | 73.4% | 62.6% | **0.0%** |
| two shapes, both at 0.999 | 64.9% | 35.6% | **0.3%** |
| two shapes, faded where they agree | 45.7% | 9.8% | **0.0%** |
| two shapes, faded where they differ | 39.0% | 8.6% | **0.0%** |
| three shapes at 0.55 | 81.5% | 76.3% | **0.0%** |

And against the depth buffer, which shares no machinery with the reference at
all: **0.75% mean, 1.01% worst**, where per-shape ordering was 36.22% and
77.07%. That 77.07% is the 2.13.0 figure, reproduced exactly.

Still see-through, and asked every time rather than assumed: swapping the wall
behind the shapes between near-white and near-black, **95.0% of it comes
through** — identical to the un-pooled picture, against **2.2%** for a solid
control.

Two things had to survive the weld. A **strength per shape**: one surface has
one opacity, so each vertex carries its own shape's strength in its alpha
instead — the same multiplication the library was doing anyway, done once. And
**which shape the pointer is over**: pooled, every triangle belongs to the
first surface, so without a remap the picture would name the first shape
everywhere and look completely normal doing it. Each shape owns a known stretch
of the pooled vertices and answers for its own.

The one case it declines is shapes **lit differently**. One surface has one
light and one roughness, and every shape may be given its own shape definition;
there is no honest way to give one surface two, so those keep the per-shape
ordering — the second-best picture rather than a wrong one.

**One thing does change, on two surfaces that lie within a hair of each
other.** Asking the picture what is under the pointer at 66 points on the same
paper measured twice — two gamuts that are nearly coincident everywhere — 62
gave the identical answer and 4 named the other paper. At those pixels the two
surfaces are inside the depth buffer's precision of each other, so which one is
"nearest" was never anything but a tie; the un-pooled picture simply broke that
tie by trace order. On two shapes that genuinely cross and are far apart where
they do — sRGB against a printed paper — all **77 of 77** points agree, and
both shapes are named.

### 📏 Depth was measured in the wrong units, on one setting

Found by refusing to accept a row of the audit. A chart's skin over two shapes
came out **5.4% off the reference and 18.5% at the worst angle**, where every
other row was under 0.3%. Supplying the normals was ruled out by measurement
(identical to the decimal), and the reference was proved not to be at fault
(reordering its traces moves it 0.0%).

The cause: the pool worked each triangle's depth out from the vertices the
drawing library was handed — each axis multiplied by that axis's own scale —
while the direction the eye is in is deliberately converted back into the
measurements' own units. Drawn in true proportions the scales agree and the
order comes out the same either way, which is why nothing caught it. The
triangle midpoints now come from where the direction comes from.

| | before | after |
|---|---|---|
| a chart's skin over two shapes | 5.4% (18.5% worst) | **0.02%** |
| the same, squared off | — | **0.03%** |
| two shapes, squared off | — | **0.00%** |

**Proportions: as a cube** is the setting this would have gone wrong on, and no
row of the audit had used it. It is now two rows of its own.

### 🏷 A paper's outline had no name in the key

Reported against a published page: `11-everything-handed-over.html` draws the
matte paper as a grey cage with **nothing in the key to say whose it is**.

A cage is split into the half that disagrees with the other shapes and the half
that agrees, so the two can be faded separately. The first half carries the
name; the second is silenced so the cage cannot be listed twice. Both rules are
right on their own and together they lose the name entirely — the matte paper
fits **entirely inside** the glossy one, so **0 of its 978 triangles** disagree,
the half carrying the name was skipped as empty, and the only half left was the
silenced one.

The name now goes to the first half **that is actually drawn**, and there is
always a first.

### 🎨 The outline's colour is its own choice

"Colour the outlines too" was a tick, and a tick can only say *the same as the
shape*. That left a genuinely useful picture out of reach: the solid drained to
grey **By lightness** so its form reads, with the cage over it still carrying
the real colours.

**Outline colour** now offers *plain grey*, *the same as the shapes*, and the
five paintings the shapes themselves use — taken from that list rather than
typed out again, so the two cannot drift apart. Every shape can have its own.
A tick you had already set is carried over rather than quietly reset, and the
old value is left in the store so going back a version finds it unchanged.

A cage carries one colour per trace rather than per point, so a coloured one is
a few hundred traces. Measured before it was offered: **60 frames a second with
395 of them**.

### 📐 Radio rows drew into each other

Visible in any screenshot of the shape-colour panel: the checked button was
drawn as **half a circle** and the descenders of "By lightness" were cut off.

A stylesheet floor is applied at *polish*, long after a layout has decided how
tall its rows are — and it does not ask again. Measured in the window: the grid
gave three rows 18 pixels each while every radio in them insisted on 20, so
they sat **17 apart**. The height is now one number in Python that reaches both
the stylesheet and the layout, and every layout is asked again once the window
is up, which closes the same gap everywhere else it could open.

### 🐢 Hiding a shape made the picture dearer, not cheaper

Clicking a shape's name in the key hides it by setting its visibility to the
string `"legendonly"` — neither true nor false. The ordering engine tested for
`false`, so a hidden shape got through, the drawn object for it could not be
found, and everything else on the page went through the slow door for as long
as it stayed hidden.

Measured, two papers with one of them hidden: a pass cost **4.50 ms where it
now costs 1.70**, the engine went on putting **1,956 triangles in order for a
picture showing 978**, and the pooling above was switched off the whole time.

## v2.13.0

### 🔍 The audit that found the last one was itself only a spot check

Everything in 2.12.0 was measured at **one camera angle**, (1.5, 1.5, 1.5).
Eight cases, one angle each. Turning the same shape somewhere else shows why
that was never enough — the error swings from nothing to almost everything
depending only on which way you are looking.

Re-measured at **six angles**, worst case reported, with the ordering cut out
of the file rather than switched off:

| what is drawn | before | after |
|---|---|---|
| the shape itself | **88.8%** | **0.7%** |
| the shape with its wires shown | 83.5% | 10.2% |
| red and grey: what it cannot print | 68.4% | 0.7% |
| faded where two shapes agree | 84.2% | **0.0%** |
| faded where they disagree | 82.7% | **0.0%** |
| with every measured patch shown | 77.8% | 1.1% |
| with the neutral axis drawn | 86.9% | 0.7% |
| with lightness rings | 86.7% | 2.3% |
| painted by lightness | 86.4% | 0.7% |
| painted one flat colour | 48.1% | 0.7% |
| with the grid turned off | 96.6% | 0.8% |
| a skin over a chart's patches | 26.0% | 3.3% |
| the shape on a light page | 26.7% | **0.2%** |
| drawn as a cage only | 0.0% | 0.0% |
| three shapes at once | 88.5% | 3.5% |
| **two shapes, each at its own strength** | 90.2% | **77.1%** |

**The figure published for that last row in 2.12.0 — 58.1% → 10.5% — was one
camera and understated it badly.** The honest number is 77.1%, and the row is
the known limitation, not a regression: see below.

Every case was also checked to be **still see-through**, by swapping the wall
behind the shape between near-white and near-black. A shape drawn opaque hides
that change completely; this separates cleanly, **96.4% against 2.3%** on a
half-strength shape versus a solid one. Three shapes stacked pass only 4.0
levels of a 234-level swing — genuinely see-through, and close to the point
where an eye stops seeing it too.

### 🔬 The hover objection was wrong, and it cost a fix

2.12.0 rejected ordering whole shapes partly because the draw array "carries
the click-and-hover identities". That was never measured. It is false. The
library resolves a hover by **object identity**, never by position:

    yZ.handlePick = function (e) { if (e.object === this.mesh) { ... } }
    for (u = Object.keys(e.traces), ...) r.handlePick(f) && (c = r)

Measured on screen: forty points taken from lit pixels, thirty-six of them on
a shape, the draw order reversed — and **all thirty-six named the same paper
and the same patch**, with their labels still appearing. Reordering costs
nothing.

**The fix is still not shipped, for the reason that should have been given.**
Measured against a real reference — both papers welded into ONE surface, same
colours, lighting and strength, sorted as a single pool, which leaves no
"which shape is in front" question in it — ordering whole shapes makes the
average **worse**:

| | unlike correct blending, averaged over eight angles |
|---|---|
| as shipped | **20.7%** |
| shapes ordered by depth as well | 24.4% |

It rescues two angles (27.9% → 0.3%) and ruins two others (0.2% → 32.7%,
0.1% → 48.9%). Two gamuts that nest have no correct order as whole shapes, so
the sort flips on a near-tie. That is the limitation, and it is about geometry
rather than about hover.

### 👁 The blacks you cannot see, and the whites

Reported as "something black at the bottom of the shape. is spike the correct
word?" — and no, because there is nothing sticking out. The lowest vertex of
either demo paper sits **0.00 below the next one**; seventy-odd vertices share
the bottom eighth. It is not a spike, an ordering fault or a shading fault.

It is the deepest black the paper prints, drawn in the colour it truly is, on
a page of almost exactly that colour:

| | mean colour of the darkest eighth | dark page |
|---|---|---|
| Glossy | 19, 19, 29 (nearest 4.4 levels away) | 17, 17, 17 |
| Matte | 43, 35, 41 | 17, 17, 17 |

**41.9% of the glossy paper's darkest eighth is invisible** against the dark
page. Matte loses none of it — and matte is the paper whose blacks are
*worse*, L\* 12.7 against L\* 4.0. Somebody comparing the two on a dark page
sees more of the poorer paper. The light page does the mirror image, hiding
**12.7%** of the glossy paper's white.

Nothing has been repainted: the shape stays the colour it measured. The window
now **says so**, naming the control that fixes it —

> Glossy-paper's blacks come within 4 levels of the page behind them, so 42%
> of that end is drawn but cannot be seen — and it is the deepest black the
> paper reaches. Under "How the shapes are coloured", choose "By lightness" to
> see it.

— and the note disappears the moment you take the advice. It is worked out
against the **page actually behind the shape**, so a light appearance warns
about the white instead, and a mid grey warns about neither.

### ⚡ Ordering keeps up on every kind of page

Not one shape at one size. The whole spread, with frames counted while the
camera moves every frame rather than divided out of the pass time:

| page | triangles | one pass | frames/s while turning |
|---|---|---|---|
| one shape | 978 | 1.4 ms | **61** |
| one shape, wires shown | 978 | 1.2 ms | **61** |
| two shapes | 1,956 | 2.3 ms | **61** |
| three shapes | 2,934 | 3.1 ms | **61** |
| split: agree and differ | 1,956 | 1.7 ms | **61** |
| every patch shown | 978 | 1.8 ms | **61** |
| two scenes side by side | 1,956 | 3.1 ms | **61** |
| sRGB at Detail 40 | 18,252 | 15.1 ms | **61** |
| Detail 40 against a paper | 19,230 | 19.0 ms | **61** |

The largest is longer than a frame, which is what the cost budget exists for:
it waits three times as long as the last pass took, so a big shape is ordered
four or five times a second while it turns and the frame rate never drops.
The first pass on the largest page costs 99 ms because the vertex normals are
worked out then; every one after it is 15 ms.

### 🩹 A style nobody handles no longer draws nothing

Found while auditing, by asking `build_figure` for the shape style `"outline"`
— which is a real name in that file and belongs to a **chart's skin**. It
matched neither branch that adds a surface, so the page came back with **nought
traces**: it opened, reported nothing wrong, and held an empty box, which reads
exactly like a rendering fault. It now refuses, and says which three styles it
knows. Not reachable from the window's controls, which offer only those three;
reachable from the command line and from any other caller.


## v2.12.0

### 🩹 A see-through shape no longer tears itself apart

Reported as "weird artifacts", "really looking like rough triangles", and
"darker as soon as transparency is introduced" — three descriptions of one
fault, and the middle one names it exactly.

A shape drawn solid hides itself: the graphics card remembers the depth of
what it has already painted and throws away anything further back. A shape
drawn even *slightly* see-through does not. From the drawing library's own
render loop:

    depthMask(false); blendFunc(ONE, ONE_MINUS_SRC_ALPHA);
    ... every see-through object drawn, in the order it sits in memory ...

Depth **writing** is off for that pass, so a see-through shape never hides
itself. Every triangle is blended in, near ones and far ones, in whatever
order they happen to sit in the file — and with that blend, the last one to
land on a pixel is the one that mostly shows. "Last in memory" has nothing to
do with "nearest to the eye", so pieces of the **far** side punch through the
near side in hard-edged, triangle-shaped patches.

**Measured before anything was written**, on one paper at seven angles, at a
*thousandth* of see-through — where nothing can possibly blend, so anything
that changes is this and not transparency:

| angle | unlike the solid picture | after ordering |
|---|---|---|
| 1.5, 1.5, 1.5 | 46.8% | 0.5% |
| −1.8, 0.6, 0.4 | 84.0% | 0.3% |
| 0.2, −2.0, 1.1 | 56.8% | 0.2% |
| 1.0, 1.0, −1.7 | **92.1%** | 0.3% |
| −0.9, −1.4, −0.9 | 0.9% | 0.3% |

That last row is why it was only seen *sometimes*. And the brightness moves
with it — 123.7 against the solid shape's 153.3 at one angle, 153.5 once
ordered — so "it goes dark as soon as it is see-through" and "it looks sliced"
were **one fault, not two**.

Saved pages and the window both now put every see-through surface's triangles
in far-to-near order before each frame, which is what that blend has always
expected and never had.

| what is drawn | unlike the solid picture, before → after |
|---|---|
| the shape itself | 51.2% → **0.8%** |
| with its wires shown | 50.9% → **9.6%** |
| the red-and-grey "cannot print" shape | 41.4% → **0.7%** |
| a skin over a chart's patches | 25.9% → **3.8%** |
| faded where two shapes agree | 51.7% → **1.8%** |
| two shapes, each at its own strength | 58.1% → **10.5%** |

**What it still cannot do, said plainly.** Triangles can only be ordered
*within* one surface. Where two shapes cross, which one wins is decided by the
order the traces were added, and no ordering of whole shapes can fix it: a
matte paper sitting entirely inside a glossy one would need the two
interleaved — glossy's back, matte's back, matte's front, glossy's front — and
the library draws one whole surface at a time. That is the 10.5% in the last
row above.

### ⚡ And it is fast enough to keep up while the shape turns

Working out the order costs **0.10 ms** for 19,230 triangles; handing it over
is everything else. Two measured decisions:

- **Buckets, not a comparison sort.** Depth is a number in a known range, so
  the triangles are dropped into buckets in one pass instead of a sort asking
  a function which of two is nearer 275,000 times.
- **The normals are worked out once.** A vertex normal cannot change when the
  triangles are reordered — same vertex, same neighbours, same answer — yet
  the library recomputes every one on every handover. Supplying them takes
  35.9 ms down to 15.4 ms at the largest size. It is written to match the
  library's own calculation step for step, and that matters: an area-weighted
  normal is the obvious way, saves just as much, and moved the picture by
  1.17%. Matching its sine-of-angle weighting instead moves the picture by
  **0.00%, worst pixel 0 levels**.

| triangles | before | now |
|---|---|---|
| 978, one measured chart | 3.15 ms | **1.90 ms** |
| 2,934, three papers | 4.65 ms | **3.71 ms** |
| 21,186, three papers + Detail 40 | 31.19 ms | **16.94 ms** |

Spinning, with the ordering live: 60 a second at 978 and at 5,310 triangles,
56 at 19,230. It also never takes more than about a quarter of the time — the
last handover is timed and the next made to wait three times as long, so a
small shape is re-ordered every frame and a large one four or five times a
second.

### 🔍 The grey switch no longer deletes the fade

Two switches, one quietly undoing the other. Greying a shape converts each of
its colours to a grey of the same lightness — and dropped the fourth number,
the fade, which is how "where two shapes agree" is drawn. Greying one of two
shapes took its faded colours from **179 to none**, while the shape left alone
kept all 308 of its own.

### 🧻 What colour your paper white actually is

Every other number in the window is blind to it. Volume barely moves when a
white shifts and coverage only counts colours in or out, so two papers read as
near enough the same while one is a cool, brightened white and the other a
warm cream — a difference visible on every print, in every neutral, before
anybody looks at a saturated colour at all. It is also the difference the M0,
M1 and M2 measurement conditions exist for.

The lightness line now reads, on the two demo papers:

    Glossy-paper: blacks reach L* 4, paper white L* 94 and cool (a* -0.4, b* -3.4)
    Matte-paper:  blacks reach L* 13, paper white L* 92 and slightly warm (a* -0.1, b* +1.1)

In words *and* in numbers, because "b* +3.4" tells somebody who already knows
and "slightly warm" tells everybody. Ties on lightness are broken towards the
least coloured, so a stray sample a hundredth of a lightness away can never
make a paper sound more tinted than it is.

### 📱 The phone fix from v2.11.0 is now proved, not assumed

v2.11.0 added one viewport line to every saved page on the strength of the
standard plus a test that the line was present — and it shipped flagged as the
change most likely to alter what a phone shows and the one verified least.

Measured now, through the browser engine's own phone emulation, the same page
with the line and with it cut out:

| | laid out at | the narrow-screen rules |
|---|---|---|
| with the line | **390 px** | fire |
| without it | **980 px** | never fire |

On a 390-point screen that is a **0.40× squeeze** — exactly the figure that
had only been asserted. That is what made the controls tiny, and why every
narrow-screen rule written for them stayed silent.

## v2.11.0

### 🫥 Fade away where two shapes agree — or where they differ

Two papers drawn over each other are mostly the same paper. The part they
share is the bulk of both, it is drawn twice, and it sits in front of the part
where they differ — which is the only part anybody put them side by side to
see. There are now two controls, in the window and on a saved page, that
dissolve either half and leave the other standing.

- **Where they agree** fades the part every shape reaches, leaving only the
  places they differ. This is the question you ask when choosing between two
  papers.
- **Where they differ** does the opposite, leaving the part they all have in
  common. This is the question you ask when the same picture has to go out on
  both, and you want to know which colours are safe on either.

**Sliders, not a switch, and that was decided by measurement.** Hiding the
shared part outright has a cliff in it: a shape lying entirely inside another
agrees *everywhere*, so every one of its triangles goes and the shape vanishes
— exactly 0 of 978 on the demo pair. That is the correct answer and it looks
precisely like a fault. Faded instead, the shape is still faintly there and
the reader can see for themselves that it agrees everywhere.

**The top of the range changes nothing, and that is exact rather than
approximate.** The first implementation cut each surface into a faded half and
a solid half. Rendered against the picture as it ships, **120,481 pixels
differed by more than eight levels, the worst by 79 — with the fade at full**,
because a browser blends transparent surfaces in the order it draws them and
one closed surface is not the same as two open ones. Somebody looking at a
shape asked whether the shading was right; it was not, and it was measurable.

The fade is now carried on a per-point alpha inside a **single** mesh, so at
the top it hands back the very same array of colours. Re-measured on the
finished thing: **0 pixels different.**

The two compose with everything already there — a shape's own strength, and
the grey switch — rather than fighting them, and *as saved* puts both back.

### 🔄 A saved page can set how far it swings, and send it right round

The window has always had a sweep slider for each direction and a saved page
had none: a reader could change how *fast* it moved and not how *far*, which
are two different things to watch. Each direction now gets a minus and a plus
reading in degrees, with this window's own limits — 15° to 180° left and
right, 10° to 120° up and down.

**And one press past the widest swing sets it going all the way round**, with
the reading changing to *round*; the minus brings it back to a swing. That
matters because it was otherwise impossible: a page saved swinging could never
be set to turn continuously by the person reading it. Switching a direction
off and on again now keeps what the *reader* chose rather than reverting to
what the page was saved with.

### 📱 Fixed: a page without written-out numbers lost its picture entirely

A serious one, and it was found by asking a question I had not tested.

The picture is a flexible item in a page fixed to the height of the window, so
anything below it competes for room. That was handled — but only on pages that
carried the written-out figures, because when the rule was written those were
the only thing that ever sat below. Then the control panel grew from four
switches to twenty-three, and on a page with **no** figures there was nothing
to give it but the picture itself.

Measured with the panel open on such a page: **0 pixels of picture at 320×568,
and 127 at 390×844.** The page had become a wall of buttons with the thing they
control squeezed out of existence. It went unseen because every page I had
measured carried the figures, and so every page I had measured had the rule.

The picture now keeps a floor whenever anything sits under it — figures or
controls — and the page scrolls instead. Measured at 320, 390, 500, 768, 844
and 1280 pixels wide: the picture holds 62% of the screen at every one.

### 🪄 A strength now moves in steps you can see evenly, and the page says when it has been changed

Ten equal steps of a tenth sound right and do not look it. Taking a surface
from full to nine-tenths is barely visible; the last step from a tenth to
nothing removes almost everything left. So a reader pressing steadily sees
nothing happen, nothing happen, nothing happen — and then the shape is gone.
Reported exactly that way. Every strength on a saved page now moves along one
ladder whose rungs are close together at the faint end, so each press changes
what you see by about as much as the last.

**It still goes all the way to nothing**, because hiding something outright is
a thing people want, and refusing it in case a vanished shape is mistaken for
a fault solves the wrong half of the problem. The right half is saying so: the
button that opens the panel now reads **more… (changed)** whenever the picture
is not the one that was saved. The panel behind it shows which control it is,
and *as saved* puts everything back.

### 🔍 Why a see-through shape sometimes looks sliced — measured, and now explained

Somebody looking at a gamut asked whether flat, hard-edged patches across it
were right. They are the drawing, not the measurement: a browser blends
see-through surfaces in the order it draws them rather than by which is
nearer, so a surface shows its own triangles wherever those two orders
disagree.

Measured on one paper, counting hard edges inside the outline:

| | hard edges |
|---|---|
| solid | 0.54% |
| three-quarters | 1.50% |
| a third see-through | 1.14% |

and it depends strongly on where you are standing:

| seen from | hard edges |
|---|---|
| above | 0.87% |
| front | 1.13% |
| side | 1.21% |
| **a three-quarter angle** | **3.47%** |

Four times worse at the angle these pictures open at than from straight above.
Nothing is wrong and nothing is missing — the silhouette is identical, checked
at 0 pixels lost out of 148,518 — so the fix is to say so where somebody meets
it: both the window and the saved page now explain it, and name the two things
that remove it (turn the shape solid, or press **above**).

While chasing it, one hypothesis was tested and thrown away rather than
shipped: that greying a shape sinks its dark end into a dark page. It does
not — 53 of 675 vertices are below the visible threshold in their own colours
and 53 in grey, identically.

### 📐 Fixed: the controls were tiny on a phone, and tiny again on a big screen

Two reports, two different causes, both real.

**On a phone**, the saved pages carried **no viewport tag**. A phone browser
handed such a page assumes it was written for a desktop: it lays it out in a
pretend window about 980 pixels wide and scales the result down to fit. On a
390-pixel phone that is a scale of about **0.40** — a 12-pixel label drawn at
five physical pixels. Worse, every rule written for a narrow screen was dead,
because the page believed it was 980 wide: the one-column layout, the bigger
tap targets and the short-screen cap never came into force on the one device
they were written for. It survived because every viewport measurement here
resizes the real window, and a desktop browser in a narrow window lays out at
that width with or without the tag — so the probes were measuring the layout
the tag produces while the pages shipped without it.

**On a wide desktop window**, the strip was pinned at 12 pixels however big
the window got. It now grows with the window between a floor of 12 and a
ceiling of 15, with the buttons sized in em so they grow with the text.
Measured: 12px on a phone, 15px at 1920 and beyond.

### 🩹 Fixed: the picture briefly painted over its own controls

Opening the panel takes about seventy pixels off the picture, and the drawing
library only learns that when it is told to re-measure. For a frame or two the
canvas was still its old height and spilled over the strip, slicing the Play
button in half — "here, and then a second later it is back to good".

Re-measuring sooner only shortens a flicker. The controls now paint above the
picture whatever the timing, and the picture is clipped to its own box so the
canvas cannot escape at all. Sampled twenty times across the second after the
press, at three window sizes: **0 pixels of overlap.**

### 🪜 Fixed: a shape could not always be put back by pressing the other way

A page saved with two papers draws them at 55%, a chart's skin at 30% — values
that are not on the ladder of steps. Stepping off one snapped to the nearest
rung, and stepping back landed on that rung rather than where it began: 55%
went down to 40% and back to **50%**. Each shape now carries its own starting
value as a rung, so pressing plus as many times as minus returns exactly.

The label reading **(changed)** was tried and taken out again. It said that
*something* was different without saying what, which is half an answer and
leaves the reader hunting anyway. What replaced it is specific: a line under
*each shape*, shown only while a shape is actually see-through, naming what
that does to the picture and what to press about it.

### 🔦 Measured, not yet changed: a see-through surface is lit differently from a solid one

Asked directly — is the light source affecting solid surfaces the same way as
see-through ones? — and the answer is no. Measured on one paper from one
camera:

| | mean brightness | dark end | bright end |
|---|---|---|---|
| solid | 152.1 | 15.0 | 251.0 |
| 0.999 | 126.2 | 3.0 | 232.0 |
| half | 94.9 | 12.0 | 167.0 |

**A thousandth of transparency moves 202,546 of 543,011 pixels by more than
eight levels and the mean brightness by −25.9.** A thousandth cannot blend
anything, so that is not the alpha: it is a different rendering path. Two
things happen on it — the far side of a closed shape is drawn from the inside,
where the faces point away from the light, and the near surface itself is lit
differently (the specular highlight drops from 251 to 232 for that same
thousandth, and the highlight is on the near face).

**And it accounts for about half of what reads as a slice.** Hard-edged
structure inside the shape measures 0.54% when solid, **0.71% at 0.999** — a
thousandth of alpha, so that step is the path and not the blending — and 0.90%
at half, the rest being real compositing order. Which is exactly why the
patches appear *as soon as* a surface stops being opaque rather than gradually.

This is how the viewer has always rendered and nothing here changed it. It is
recorded because it has a consequence worth knowing: two shapes drawn at
different strengths are being compared at different apparent brightnesses, and
the shading is a drawing choice sitting on top of the measured colours rather
than part of them. Making it consistent across strengths is the next piece of
work, not a quiet edit at the end of this one.

### Also

- The fade was at first nested inside the code that handles the grey switch,
  which is deliberately refused for shapes whose colour *is* the measurement.
  So the one page in the showcase whose whole subject is comparing two
  measurements was the one page where the new control did nothing.
- Returning the fade to the top left the colours written on the way down in
  place, so a shape stayed faint at a reading of 100%. The colours are now
  always rebuilt from the originals, so the reading and the picture cannot
  come apart.
- `_weld` groups vertices by position **and** colour. A mask welded separately
  can group differently and come back a different length, lined up with
  nothing — so the rule now lives in one place and everything follows it.
- The window's new sliders are in the one table of remembered settings, which
  means they are saved between sessions and put back by *Start again with the
  standard settings* without either being wired up twice.
- 414 tests, up from 405.


## v2.10.0

### 🎚 A saved page hands over each shape on its own

Every shape on a page now gets its own row of controls — **fainter / more
solid**, **wires**, and **grey** — behind **more…**, one row per name in the
key underneath. That last part is deliberate: a page can hold a solid surface,
a wire cage round a second paper, a cloud of chart patches and a skin over
them, and nobody reading it knows which of those the code calls a shape. What
they can see is the list of names. The rows are built from exactly that list,
so the thing they press and the thing they read are the same thing.

- **Fainter / more solid** is the answer to the oldest problem a picture of
  two gamuts has: the front one hides the back one, and no amount of turning
  fixes it. The sender picks one strength when they save; this lets the reader
  pick a different one for the shape *they* care about, which is not a
  decision anybody can make in advance. It stops short of invisible and of
  solid, so nobody fades a shape away and is left wondering whether the page
  failed to draw it.
- **Wires** lays a net of fine lines over a surface, following the measured
  points — so it shows where the measurement is dense and where the shape
  between two readings is the drawing's guess. Turned faint at the same time,
  what is left is the cage alone, which is the clearest way to show one shape
  inside another. On a cross-section the same switch fills the outline in or
  empties it.
- **Grey** takes the colour out of one shape so the other becomes obvious. It
  keeps the light and dark exactly: each colour becomes its own true
  brightness, worked out the way sRGB itself defines brightness, not by
  averaging the three numbers — which would make a pure blue and a pure yellow
  the same grey when one is nearly black to look at and the other nearly
  white.

**Some shapes are never offered the grey switch, and that is the point.**
Where the colour *is* the measurement — the comparison shape that is red for
what a paper cannot reach, and a chart's out-of-reach patches — a greyed
picture would still carry a name promising two things while showing one, and a
reader who pressed a button three screens ago would have no way of knowing the
picture had stopped saying anything. Those traces are marked in the file and
the switch is not built for them at all. Not built rather than built and
refused: a control that is there and declines to work is the worse of the two.

### 🎚 And a cross-section can be slid up and down, as in the window itself

A saved cut was frozen at whatever lightness the sender happened to be looking
at. It now carries the same slider the window has, from the shadows to the
paper white.

The page cannot work these out for itself — slicing a gamut needs the whole 3D
shape and a triangulation of it, and a flat page carries neither. So every cut
the reader can reach is worked out **when the page is saved** and travels
inside it: 2 L\* apart, 120 points each, which comes to about 170 kB on a file
that is already several megabytes. It moves as fast as a finger can drag it
and needs nothing from the internet.

The axes are pinned across every height, so the outline shrinks and grows as
you slide instead of being rescaled to fit — which is the one thing this view
exists to show. Heights where nothing is drawn at all are trimmed off both
ends, so the slider has no dead travel. The caption follows, and names any
shape that does not reach the height you are at.

### 👁 Four places to stand, full screen, and a picture file

- **above · front · side · angle.** Dragging is how you explore a shape and a
  poor way to arrive at a known position: getting the eye squarely over the top
  of a gamut by hand takes several goes and is never quite square. So two
  people comparing two pages are comparing two different angles without
  realising, and a difference they see may be nothing but that. Pressing the
  same button on both makes the pictures strictly comparable. Only the
  direction changes — how far away the eye is and what it is pointed at stay
  as the reader had them.
- **Full screen**, built only where the browser has it. Safari on an iPhone
  offers full screen for video and nothing else, so there the button is simply
  not there rather than there and dead. The controls go full screen with the
  picture, so there is always a visible way back out.
- **Save a picture** writes what is on screen — that angle, those faded
  shapes — as a PNG at twice the size it is drawn, which is enough to put in a
  document and still read. Made by the reader's own browser out of numbers
  already in the page; nothing is sent anywhere.

### 🗂 Twenty controls needed a shape, on a phone and on a laptop

The panel behind **more…** was one flat list, which was right for nine
controls and is not right for twenty — a flat list of twenty unrelated things
is not a panel, it is an inventory, and somebody looking for *make the front
one fainter* reads every line to find it. It is now five short lists under
plain headings: **how it moves**, **where you look from**, **each shape**,
**what is drawn**, **the page itself**. Empty groups are never drawn, so a page
that hands over two controls still shows two controls and no scaffolding.

The layout follows the screen, measured at 320, 390, 500, 768, 844 and 1280
pixels: one column up to a phone's width, two on a tablet, three on a laptop,
and the shape rows two abreast once there is room. A fixed set of columns was
written first and then measured against what the grid was already doing —
identical everywhere, and worse in one case, because a group of two rows given
three fixed columns leaves the third empty for nothing. On a **short** screen —
a phone held sideways, where there is 390 pixels of height in total — the
panel is capped and scrolls, because otherwise it pushes the picture it
controls clean off the screen. On a tall phone it is left to grow and the page
simply gets longer: a panel with its own scrollbar inside a page that also
scrolls is a trap for anybody whose thumb lands on it, and it buys nothing
where there is room.

The save dialog got the same treatment — twenty checkboxes in one column is a
dialog taller than a 13-inch laptop screen, which is a dialog whose Save button
cannot be reached. Five named groups in a scroll area, sized from the screen it
is actually on.

### 🔴 Fixed: the red and the grey were the same brightness

Reported as *red and grey with no clear distinction*, and measurement agreed
exactly. The comparison mesh paints out-of-reach red and within-reach grey. On
the dark page those were `rgb(232,23,93)` and `rgb(105,112,126)` — a contrast
ratio of **1.12:1**, which is to say the same brightness, with hue alone
telling them apart. Hue is the weakest cue there is on a surface whose shading
already varies its brightness everywhere, and for the one reader in twelve who
cannot separate red from grey-blue it is no cue at all.

The grey is now `rgb(68,74,87)`: **1.99:1** against the red, and 2.12:1 against
the page so the shape does not sink into the background instead. **The honest
limit:** the 3:1 that WCAG asks of a graphic against what is next to it cannot
be reached on a near-black page with this red — it needs the grey below a
luminance of 0.029, and there the reachable part of the shape all but
disappears. 1.99:1 is the best available before one problem is traded for the
other, and the key now carries the rest: it says **"red is out of reach, grey
is within it"** rather than naming one colour of a two-coloured shape and
leaving the reader to take the other for background.

The whole test suite was green while 1.12:1 was true. There is now a test that
measures it.

### ➕ Fixed: the number between a minus and a plus shoved them apart

Reported from a real page. `100%` is wider than `50%`, and with the reading
sitting between the two buttons, every press that crossed a digit moved both —
so the plus walked out from under the finger pressing it. Both halves of the
fix were needed: a floor on the width so the widest reading still fits, and
tabular figures so every digit is the same width as every other. Without the
second, `11%` and `88%` are different widths in most interface fonts and the
buttons twitch inside the space rather than jumping out of it.

### ⓘ Fixed: one help icon was in the wrong place, and usually absent

*A chart to be printed* begins with an open button exactly as *Files* does, but
its explanation was left beside a note three rows further down — and that note
hides itself when no chart is open, taking the icon with it. So the group
carried its help only *after* you had already done the thing the help was there
for. It now sits beside the open button, always, six pixels below its top:
the same place, to the pixel, as the one above it.

### 📄 A thirteenth showcase page, and a note about reading it

**[What a paper can no longer reach, months later](https://itsab1989.github.io/ChromIQ-Gamut-Viewer/pages/13-what-a-paper-can-no-longer-reach.html)**
— the same glossy paper measured twice, months apart, with the surface painted
red where the later measurement can no longer reach it. It is also the page
that demonstrates the rule about colour: the grey switch is not offered for
this shape.

**Read the red as a share of the surface, not of the gamut.** It marks the
measured boundary points that fall outside the other shape, and on two gamuts
that graze each other a great many boundary points fall just outside while
almost no volume does. On this pair it is 54.1% of the surface and 1.8% of the
volume. The two numbers answer different questions and neither is wrong.

Which two papers this page compares was itself measured rather than chosen: the
glossy against the matte paints 91.3% of the surface red — a solid red blob
that demonstrates two colours by showing almost none of one of them — and the
other way round it is 0.0%, because the matte fits entirely inside the glossy.

### Also

- The settings a page carries are written into it **once** and handed to both
  things that need them. That cost nothing while they were a dozen numbers;
  with the cross-sections in there, one page was carrying 336 kB of outlines
  where it needed 168.
- Attribute selectors in the control strip are quoted. The new names carry a
  number on the end, an unquoted attribute selector is a CSS identifier, and
  `querySelector` **throws** on one it cannot parse rather than returning
  nothing — which would take the whole strip down with it.
- Buttons in the panel are at least 34 pixels tall on a phone. These sit in
  pairs where hitting the minus instead of the plus is an actual mistake.
- 405 tests, up from 389.


## v2.9.0

### 📱 A saved page can be zoomed and moved — which on a phone it could not

Reported from a phone: *pinching did not work to zoom in or out, or to move
left, right, up and down.* That is exactly right, and it was not a small
oversight — it was a hole in the middle of the feature.

**Why it happened.** The viewer that draws these shapes decides between
turning, moving and zooming by **which mouse button is down**: left turns,
right moves, middle zooms, or a held Ctrl or Alt. Its touch handler reads a
single finger and reports it as the left button. A phone has no second button
and no Ctrl key, so on a touch screen the only one of the three that could
ever happen was **turning**. A shape could be spun and never approached.
Measured on a page in a browser told it was a phone: a pinch and a two-finger
drag each moved the picture by 0.0000.

**Two answers, and both were needed.**

- **The gestures themselves.** A pinch now zooms and two fingers dragged
  together move the picture, handled by the page rather than by the viewer.
  One finger still turns the shape exactly as before.
- **Buttons, for anyone who would rather press something** — and for a desktop
  with no wheel, and for a keyboard. A **zoom** pair sits in the open next to
  the speed, and four arrows live behind **more…**. Both are ticked by default
  when you save, because without them a page cannot be read on a phone at all.

There are stops at both ends of the zoom, so nobody can send the shape so far
away or get so close that they lose it and cannot find it again, and **reset
view** now puts back moving and zooming as well as turning.

### 🔎 A flat cross-section gets the strip too

It used to get no controls, on the grounds that there is nothing to turn. True
— but zooming, moving and getting back to where you started mean as much on a
cut as on a shape, and the drawing library's own toolbar (the only other way
back from a zoom) is hidden on anything narrower than a tablet. **On a phone a
cross-section could be zoomed into and never zoomed out of.**

It now carries zoom, move and reset, and everything about movement is left out
rather than shown switched off.

### 🐛 The "more…" panel was never actually closed

**On every page since v2.8.0.** The panel is marked hidden the moment it is
built and the button reads *more…* — and it was on screen the whole time,
because a rule the page writes always beats the browser's own
`[hidden]{display:none}`, whatever the specificity. Its own `display:grid`
quietly cancelled being hidden.

Measured on a phone-sized window before the fix: the panel was **259 px of an
844 px screen, the picture was 78 px, and 91 per cent of what the reader could
see was controls.**

It went unnoticed because the test guarding it asked the element whether it was
hidden, and it truthfully answered *yes*. The test now checks the rule that
decides what is actually drawn.

### 🐛 The numbers under a picture squeezed it to nothing

The written-out figures were being packed into a page fixed at exactly the
height of the window, and a column of flexible things in a box that cannot grow
does not scroll — it squeezes. On a phone, 466 px of figures left **78 px of
picture**, on a page whose entire purpose is the picture.

Now the page may grow past the window, the figures keep the height they need,
and the picture is promised a share of the first screen it can never fall
below. Anything that does not fit goes below the fold, which is what scrolling
is for.

**The controls also moved to sit directly under the picture** instead of after
the figures — on a phone that was several screens of text, so pausing the
movement meant scrolling away from the thing being paused.

### ✨ The reader can put the numbers away

A new switch, offered by default whenever you include the numbers. On a small
screen those figures are easily taller than the screen itself, so somebody who
has read them once can give the whole window back to the shape. Nothing is
recalculated and nothing is lost.

### 🐛 The strip's two minus-and-plus pairs ran together

With speed and zoom both in the strip and every gap the same width, the row
read *speed 6 + − zoom +* — the plus for the speed sat right beside the minus
for the zoom with nothing to say which belonged to which. Each pair is now
grouped, so the space between two groups is twice the space inside one.

### 📄 A twelfth sample page

The window can show four arrangements — one scene, two rooms, one cut, and two
cuts — and the last of them appeared in no sample page, so nothing was checking
it. It is the one with the most to go wrong: the two panes are tied together,
so a zoom applied to them one after another zooms the second one twice, and two
panes that disagree about scale are exactly the lie a side-by-side comparison
exists to prevent. Verified identical to three decimals through zoom, move and
reset.

### 🔒 Kept safe

- A reader who had opened one of these pages before will not find the numbers
  missing. What a page remembers is written by whatever version was last
  opened, and settings added since now fall back to their defaults instead of
  arriving as *off*.
- A page saved without the strip is unchanged, and still drags, zooms and
  clicks exactly as before.

## v2.8.0

### ✨ You choose what the person opening a page can change

**Save this view as a web page…** now has a section of its own — *What the
person opening it can change* — with a switch for each control the page can
carry and an explanation of when it is worth handing over. Which controls make
sense depends entirely on where the page is going: one for a printer to turn
over wants everything, one embedded in a website beside your own text may want
no strip at all.

**The six that were always there stay ticked**, so a page saved without opening
that section is exactly the page you would have got before.

Beyond those, a page can now hand over:

- **A speed for each direction** — what this window itself has always given
  you, and worth passing on: a slow tip under a quicker turn shows the dents
  in a surface far better than either on its own, and somebody with one speed
  for both cannot find that.
- **The box and its grid** — the walls are what let somebody judge where a
  bulge sits, and clutter when the picture is going into a document that
  explains itself.
- **The lettering** — the numbers and axis names around the edge.
- **The list of names** — remembering that each name is also a switch.
- **A light-or-dark switch for the page**, so it can be matched to whatever it
  is being read in. The measured colours never change; only the paper.
- **Remembering what they chose**, kept by their own browser for that page
  alone, so somebody working through several of your pages does not have to
  press Pause on every one.

Everything past Play, speed and reset lives behind a **more…** button, so the
strip stays one line on a phone. The strip can also be switched off entirely.

### 🧹 Fixed

- **In light mode, lists and empty tickboxes are white inside.** They were
  painted the same colour as the group box behind them, four levels apart from
  the window itself, which made them read as greyed out. The dark window was
  always right — an inset there is *darker* than the surface, and the idea
  simply inverts on a light one. Number boxes and text fields had no rule at
  all and fell back to whatever the platform painted; they follow now too. The
  surface colours are untouched, so they still match ChromIQ exactly.

## v2.7.0

### 🔴 The key beside the picture was a decoration, not a switch

Reported from a phone, and it turned out to be three faults sitting on top of
each other. All of them are in the key — the names under the shape that the
README tells you to click.

**The outline's little line was invisible, in exports and in the window
itself.** The loop that walks a shape's triangle edges called its edge `key`,
which is also the name of the argument holding *the colour the key is drawn
in*. So the colour was overwritten with the last edge visited — a pair of
vertex numbers like `(600, 610)`. Handed numbers instead of a colour, the
drawing library falls back to black: **1.11:1 against the dark page**, which
is nothing at all. One word, and it had been there the whole time. Now
**7.42:1**.

**Clicking a name switched nothing.** The keys are separate zero-point traces
— they have to be, or a mesh's key is drawn with the scene's own lighting and
disappears — but nothing joined them to the shape they name. Measured:
clicking *Glossy-paper* hid the one-point proxy and left the 914-vertex mesh
fully on screen. Every key is now tied to its shape, so clicking hides it and
double-clicking shows it on its own.

**A coloured outline keyed itself on its first colour band**, and the bands
are sorted by colour, so `rgb(0,0,0)` sorted first and it keyed on black every
time. It now takes a colour that represents the cage and can still be seen.

### 🔴 On a phone the controls sat on top of the key

The strip along the bottom was fixed to the bottom of the window, which is
exactly the band the drawing library puts the key in. Measured at five
viewports it covered **two rows on a desktop and all four on a phone**, where
it was also wider than the screen.

It sits under the picture now rather than floating over it, so the room it
needs is reserved automatically — one line or two, at any width — and it
cannot cover anything at any size. Two things came out of the same
measurement:

- **The picture had to be told it was shorter.** A plot measures its box once,
  when it is created; adding the strip took about seventy pixels off the
  bottom and the key went on being drawn where it would have gone in the
  taller box — straight back over the strip.
- **Plotly's own toolbar sat on the caption**, 2,464 square pixels of buttons
  over the words on a phone. It is hidden below 1024px, where the caption
  needs the whole width and a finger does the zooming anyway.

All ten showcase pages are now checked at five viewports — iPhone SE through
desktop — for anything covering anything else.

## v2.6.0

### 🔴 Save this view wrote a different view

This window can show four arrangements — one scene, **two rooms side by side**,
a **cross-section**, and two cross-sections. Only the first of them was ever
reachable from **Save this view as a web page…**: the save route called the
single-scene writer directly instead of the one the window itself uses. So
somebody looking at two rooms got a single overlaid scene, and somebody looking
at a flat cross-section got a 3D shape. Three of the four wrote a different
picture than the one on screen, from a button that says *this view*.

Both routes go through one writer now, so they cannot drift apart again — which
is the same lesson the code already had written down one level below, about the
argument list.

Two of those arrangements had therefore never been saveable, so they are now
also in the showcase:

- **The same two papers, a room each** — overlaying two shapes hides the back
  one; two rooms show what each actually looks like, with the cameras kept
  together so you are never comparing two different angles.
- **A slice through both, at one lightness** — where two papers are close, a
  gap between two outlines is obvious where a solid shows nothing. It has no
  controls along the bottom, because a cross-section has no camera to move.

`scripts/make_sample_pages.py` now checks the arrangement of every page it
writes — how many rooms, and whether they are flat or 3D — so a page that comes
out as the wrong kind of picture fails rather than being published.

## v2.5.0

### 🔴 The strip on a saved page could not be seen

The controls added in v2.4.0 were painted with `color: inherit`, and a saved
page sets a background but no text colour — so they inherited the browser's
default black and came out at **1.04:1 against the dark page**. Invisible, on
seven of the eight pages published to show the feature off. On the light page
they reached 2.4:1, which is still under what anybody with ordinary eyesight
can read.

Measured in a real browser rather than reasoned about, and measured again
after: **15.13:1 on the dark page, 13.56:1 on the light one.** The strip now
carries the page's own palette and its own background, so the text is at full
strength whatever the shape behind it is doing. Two things came out of the
same look:

- **A touch screen has no hover**, so the rule that revealed the strip on
  hover left every phone and tablet with the resting look for ever.
- **A keyboard could not see where it was.** The browser's own focus ring is
  drawn in its own colour and vanishes against a dark page.

### 🔴 A saved page did not run at the speed it was saved at

The strip flattened both directions of movement to a single speed and pushed
it as soon as the page opened — so a page saved turning at 7 while tipping at
5 arrived **tipping at 7, forty per cent fast**. Four of the eight published
pages were affected. The two speeds are kept in proportion now: slower and
faster scale them together, and a page opens showing exactly what was saved.

### 🔴 The numbers written under a picture could not be reached

**Save this view as a web page… → include the numbers** appends the figures
after a scene that is already the full height of the window, so they landed
entirely below the fold — and the page had `overflow: hidden`. Fifteen real
wheel notches moved the published page not one pixel.

Letting it scroll was not enough on its own, and the measurement said so: a 3D
scene takes the wheel for zooming, and it filled the window, so there was
nowhere left to scroll from. The picture now makes room for the figures, which
are simply on screen where they can be read.

### ✨ New

- **reset view**, on the strip of every saved page. A reader who has turned or
  zoomed a shape somewhere they did not mean to had no way back but reloading
  — and reloading a page that arrived by email is not obvious either. It
  restores the view the page opened with, captured before the first movement
  is applied, so it is the view the sender chose.
- **The demo measurements now travel with the source**, in `demo/`. The
  showcase said they did and they did not, so nobody who cloned the repository
  could open anything or reproduce a single sample page.
- **`scripts/make_sample_pages.py`** writes all eight showcase pages by
  driving the real window through its own Save button, then reads each one
  back and checks it still shows what `docs/index.html` claims about it —
  including the patch counts. Run it after any change to the export.

### 🧹 Fixed

- **The reader's strip no longer appears inside the application itself.** The
  window has its own movement controls, with better labels than a strip can
  fit, and a second set floating over the picture was two controls for one
  thing — which could disagree, because a nudge of a panel slider goes
  straight to the engine and left the strip showing a number that was no
  longer true.
- **How a shape is drawn no longer follows its name into the browser tab.** A
  published page was called *Glossy-paper and Matte-paper (outline)*. Only the
  endings this application invents are removed, so a measurement somebody
  named *Canon (matte)* keeps its name.
- **Two claims on the showcase were wrong** and are corrected: the small page
  is 56 kB against 4.9 MB (ninety times smaller, not sixty), and the two
  papers were the wrong way round — the matte one fits entirely inside the
  glossy, not the reverse. Both are now checked by the generator rather than
  written by hand.

## v2.4.0

### 🏷 Saved pages now have a name

Every page written by **Save this view as a web page…** carries a proper
`<title>`, so the browser tab, a bookmark and a pasted link all say what is in
the picture — the papers, the comparison, the chart, by name. Before this there
was no title at all and a shared link showed nothing but a file name, in the one
feature that exists for sending a measurement to somebody else.

**The names come from the legend, not from the caption**, and looking at eight
real exports is what settled it: a measurement's caption says what the colours
were measured *against* ("…from a D50 white"), which is true of nearly every
page, so seven of eight tabs came out identical. Anything unusual in a name — a
`<`, an `&` — is escaped, a very long one is trimmed, and a scene with no named
shape falls back to the caption.

### ✨ New

- **A saved web page can now be set turning by whoever opens it.** Every page
  written by **Save this view as a web page…** gets a small strip along the
  bottom: **Play/Pause**, slower and faster, and switches for the left-and-right
  and up-and-down movement. It sits at a third opacity until the pointer is near
  it, so it never competes with the shape.

  **It is on every page, including one saved standing still.** A still page
  simply opens with the button reading **Play** and nothing moving — no movement
  ever starts unbidden — and pressing Play on a page with no movement saved in
  it falls back to turning all the way round, which is what somebody means when
  they press Play on a shape.

- **A live gallery of eight saved pages**, at
  <https://itsab1989.github.io/ChromIQ-Gamut-Viewer/> — a paper standing still
  and turning, two papers compared, a chart in ink amounts with its skin, the
  same chart in CIELAB, a light-mode page, and the small 80 kB variant that
  fetches its viewer instead of carrying it. Every one written by the app and
  not edited afterwards, so it is exactly what the button gives you.

- **The Saved message now answers the next question**, which is always "how do I
  show this to somebody". It names what works for email, for a website, and —
  the one that surprises people — for a forum, where the page will not run
  however it is pasted in, so a moving picture plus a link is the answer.

### 🔍 Verified end to end

Each page was rendered in a real browser with **every non-file request blocked**:
nothing is fetched, the camera really moves, Pause really stops it, a still page
really has no motion until asked, and the strip appears on all of them.


## v2.3.0

### ✨ New

- **A chart can now be looked at on its own, with no profile at all.**
  **Draw it in** has a fourth entry, **Ink amounts — a chart on its own**. Its
  three axes are not colour: they are the printer's own controls, how much of
  each ink from 0 to 100, which is exactly what a `.ti1` or `.ti2` file
  contains. So a patch set can be opened and seen straight away — nothing is
  predicted, because nothing needs to be, and the numbers on the axes are the
  numbers in the file. It answers a question about the *chart*: how evenly it
  samples the range the printer can be asked for, where it crowds, and where
  it leaves a hole. The spacing figure is quoted in ink amounts here rather
  than in Lab, and says which it is.

- **The patches a paper cannot reach, shown in ink-amount space.** With a
  profile under **Placed through** and a measured paper open, the out-of-reach
  patches are picked out in red at their ink amounts. On the demo files that
  is 240 of 480 — and in the cube they are visibly the whole *outer shell* of
  the ink range while the interior survives, a pattern that cannot be seen in
  CIELAB, where the same patches are scattered through the shape. The counts
  are identical in both views.

- **A profile still paints, and cannot move anything.** In ink amounts a
  profile is the only thing that can say what colour each patch will come out,
  so it colours the dots — but the ink amounts *are* the axes, so nothing
  shifts. The panel says which of the two it is doing.

### 🧭 How it behaves

- **Nothing else is drawn in ink amounts, on purpose.** Every RGB printer's
  boundary in its own ink amounts is the same full cube, on every paper, so a
  paper drawn there would be perfectly true and would tell you nothing. Papers,
  profiles and pictures stay open, keep their measurements, and are drawn
  again the moment CIELAB is chosen. Opening one while ink amounts are showing
  now works properly — it is measured in CIELAB and simply not shown.

- **A CMYK chart is not drawn there** and says why: four ink amounts do not fit
  three axes, and dropping the black or folding it into the other three would
  draw a chart that was never in the file. It sends you to CIELAB, where a
  profile can place any number of inks into the three axes colour has.

- **Controls that only describe a drawn surface switch off and explain
  themselves**, and come back exactly as they were. Controls that change what
  gets *built* — **Follow the real edge**, the detail slider — keep working,
  because the shapes are still measured and the patch counts are measured
  against them. So does the white point: the dots are painted through a
  profile and counted against a paper, and both read colour against a white.

### 🎞 Six new loops, and a page of their own

`docs/motion/page-7.md` is all charts — patch sets before anything has been
printed. A chart alone with no profile at all, the same patches with a profile
asked what colour they will be (not one dot moves), the outer shell a matte
paper cannot reach, the chart's own reach as a solid, the same chart and paper
in CIELAB for the contrast, and one in light mode with the skin in the accent
colour. All WebP, so they start on their own with nothing to click.

The README link now sits between Previous and Next on every one of the seven
pages; page 5 had it after Next, the only one out of order.

### 🩹 Two faults found by crossing the options

Every option had its own test and they all passed. Crossing 6,912 combinations
of space, skin, colours, opacities and dot sizes found two that no single-option
test could see.

- **The patch counts changed with the space the picture was drawn in.** A
  chart's patches are always CIELAB; a paper was built in whatever was chosen
  under **Draw it in**. Held against each other those disagree — and the
  distance quoted beside them is ΔE2000, which is defined on CIELAB and nothing
  else. The same chart and the same paper answered **240 patches outside in
  CIELAB, 178 in CIELUV and 480 in CIE XYZ**. The XYZ answer is the worst kind
  of wrong: a gamut there runs 0 to 1 while the patches run 0 to 100, so every
  patch lands outside and the panel reports a total loss with nothing to
  suggest anything is amiss. The paper is now rebuilt in CIELAB for judging, so
  the answer cannot depend on the picture.

- **A chart shown side by side was drawn into both rooms and judged against
  one.** Two rooms exist to compare two papers, and the right-hand room was
  showing a chart marked against the left-hand paper. Each room now marks it
  against its own: on the demo files the matte paper loses 240 patches and the
  glossy one 149.

### 🔍 Under it

- `scripts/drive_all_combinations.py` — 6,912 combinations and **60,075
  checks**, in two phases. The first asserts what must hold of every
  combination without exception: no look setting may move a patch, every option
  set is the option drawn, the skin appears only when asked for and never
  reaches past the surviving patches, and nothing in the picture is ever named
  a gamut. The second drives the real window and compares what is on screen
  with what a save actually writes, which is the only way to catch an option
  that reaches one route and not the other.

- **The panel audit gained the other half of its ⓘ rule.** It checked that no
  icon was orphaned and never that a control *had* one, which is how three
  sliders shipped with no explanation. It now reports any control with a
  caption of its own and nothing explaining it, and it found one more:
  **Placed through**, the control that decides whether a chart appears at all.

- **File dialogs.** `QFileDialog.getExistingDirectory` is a static convenience
  method, so it inherited nothing from the shared factory and opened the
  system's own folder chooser for **Where ArgyllCMS is…** while every other
  dialog in the window was the app's. The test that was supposed to prevent
  this counted constructor calls and could not see it; it now reads every
  static variant.

### 🐞 Fixed

- **The caption above the picture claimed a measurement that had not
  happened.** In ink amounts it still read "lightness and colour measured from
  a D50 white" over a cube of ink percentages — false in every clause. Found
  by looking at the rendered picture rather than at the code.

- **The ⓘ in "Are the patches inside?" sat explaining nothing** whenever a
  chart was open without a profile, because the line it shares collapsed when
  empty. That line now says what the missing figure needs instead.

### 🔍 Under it

- `scripts/audit_panel.py` — a new check that walks every interactive control
  on the real panel, at three widths in all four spaces, and fails on text
  that is cut off, anything past the column's edge, an orphaned ⓘ, or a
  control that is neither declared space-dependent nor declared independent.
  A control added later cannot be forgotten, only answered. Verified to fail
  on a deliberately over-long label and a deliberately unregistered checkbox.

- `scripts/drive_ink_amounts.py` — 22 scenarios driven through the real
  window, each stating what should happen before it looks.

- **Documented, with the measurements behind it**, in
  `docs/DESIGN-ti1-ti2.md` §12–§14: why a chart's own `XYZ` columns are never
  drawn (all 130 `.ti1`/`.ti2` files on this machine carry them; none is
  flagged accurate; against a real print they are 34.6 ΔE out, claiming a
  paper white of L\* 100 where the printer managed 92.6), what the ink-amount
  view can and cannot hold, and how the mutual exclusions are kept honest.


## v2.2.1

### 🐞 Fixed

- **Showing the greys left the shape opaque, so the line stayed invisible.**
  Ticking **Show the greys** turns the shape down to a third so the line
  running up the inside can be seen — and it did, for about a second. Moving
  the slider by hand does two things: it fades the picture while the handle is
  down, and it records the value when the handle is let go. Doing it from code
  did only the first, so the number never reached the place every redraw reads
  it from, and the next redraw closed the shape up again. Reported twice, and
  it went out in one of the gallery loops.

- **The chart section shrank when it was empty**, so its box was narrower than
  every other one in the column and its ⓘ dropped onto a line of its own. It
  now says what it is for before anything is open, which fills the row and
  answers the question a beginner has at that moment anyway.

- **How much of a picture will actually print, as its own figure.** The
  coverage percentage is a share of the SPACE a picture's colours occupy, and
  it reads as "how much of my photograph will print". Those are not the same
  thing and they are not close: for a Display P3 photograph against the demo
  paper, **92.7%** of the space its colours occupy fits inside the paper, while
  **38% of the photograph itself** is out of reach — counting how much of the
  picture each colour actually covers. Most of the space inside a gamut is
  unsaturated middle colour any paper reaches easily; a photograph's pixels
  crowd towards the edges. Both numbers are now shown, each saying which it is.

## v2.2.0

### ✨ New

- **Charts that have not been printed yet.** **Open a chart to be printed…**
  takes a `.ti1` or `.ti2` from ChromIQ or ArgyllCMS, or the `.txt` or `.pxf`
  file i1Profiler saves for a target, and shows you where its patches would
  land — so you can see, before spending the paper, whether the chart you are
  about to print asks for colours your printer can actually make.

  A chart is a list of ink amounts. Nothing in it has been printed and nothing
  measured, so it is never drawn as a shape: a shape thrown around a set of
  *requested* ink amounts is not the gamut of anything. The patches appear as a
  cloud of dots, put where an ICC profile you choose says each one would land,
  and the ones that fall outside are picked out on the picture.

- **Three counts, not two: inside, on the edge, and outside.** A gamut surface
  is worked out from a grid of samples, and between them the real boundary
  bulges out a little further than the shape drawn through them — so a handful
  of patches always land a whisker outside any surface, including the surface
  of the very profile that placed them. Anything within 1 ΔE, closer than
  anyone can see with the two side by side, is counted as **on the edge**.
  Without that, a perfectly good chart reports hundreds of patches "outside"
  and sends you hunting a fault that is the sampling of the surface.

- **It tells the two questions apart, and says which one you are asking.**
  Against the profile the chart was built *from*, the answer checks the chart
  builder rather than your printer, and the panel says so in those words — it
  is still a real check, and it catches a mismatched rendering intent, ink
  counted 0–255 where the file wants 0–100, patches clipped to a box around the
  gamut instead of to its surface, or simply the wrong profile. Against the
  **measurement** of your paper, it checks the printer. Both appear at once,
  one line each, so neither can be mistaken for the other.

- **It notices when the two are measured against different whites.** A chart is
  placed relative to the paper's white; a measurement read absolutely keeps the
  white the instrument saw. Comparing them puts the light patches outside for
  no reason to do with your printer — 624 of them on the demo paper, against
  none once the two are judged the same way. The panel says so and names the
  tick box that fixes it, and never moves it for you.

- **Save the numbers as a table now writes the patches themselves**, one line
  each: which shape it is outside, the patch number, its position on the
  printed sheet when the chart is a `.ti2`, the ink amounts in the file's own
  units, where it was predicted to land, and how far outside it is in ΔE2000.

- **Compare with takes a picture.** Photographs were readable all along and
  simply were not offered there, so holding a paper up against one meant
  opening it as a shape. Now it is one of the things to compare against, like
  any other file.

### 🐞 Fixed

- **A `.ti1` opened as a measurement drew a gamut made entirely of
  predictions.** Those files carry XYZ columns written by ArgyllCMS's device
  model, not read off any paper — with no profile to predict with, the black
  patch comes out as XYZ 1, 1, 1. It is refused by name now, and pointed at the
  right button.

- **A `.ti1` could not be read at all**, and failed with a message naming a word
  out of a comment: `could not convert string to float: 'chart'`. A `.ti1` is
  three tables in one file — the chart, the density extremes, the device
  combinations — and the reader took everything between the first and last
  markers, headers included. Measurements are read the same way now, so a
  `.ti3` carrying more than one table can no longer confuse it either.

- **Close both** is **Close them all**, and closes the chart with the rest.

### 🔍 Under the bonnet

- `cgats.py`, a proper multi-table CGATS reader, and `chart.py`, which reads a
  chart and counts it. Neither needs Qt; both are meant to be lifted into
  ChromIQ, and `docs/PORTING-TO-CHROMIQ.md` says how.
- The distance a patch sits outside is measured to the nearest point **on the
  surface**, not to the nearest corner of it — which on a real gamut, where the
  corners are tens of ΔE apart, is a very different number. A shortlist of
  nearby triangles was wrong by 4.1 ΔE on a real printer gamut, so every
  triangle is measured against; it costs a fraction of a second.
- 59 more tests, 317 in all, and `scripts/drive_chart.py` drives the real
  window through the whole journey.

## v2.1.0

### ✨ New

- **A perfectly neutral line to compare your greys against.** **Show the
  greys** draws what your printer did when asked for an equal amount of every
  colour; the new box under it adds a quiet dotted line showing where those
  greys would run with no colour in them at all. On its own a wandering grey
  line is hard to read — you cannot tell a drift from the angle you are
  looking from. With a straight one beside it the lean is obvious, and so is
  which way and at which lightness.

  It runs over exactly the range your own greys cover, from your blackest
  black to your paper white, and not from black to white in the abstract: your
  printer cannot reach either extreme, and the question is how far the greys
  **lean**, not how far they reach.

- **Ticking either one turns the shape down for you.** Both lines run up the
  inside of the solid, and at full strength a solid is opaque — so the box
  appeared to do nothing at all. The shape drops to about a third the first
  time it is needed, and only from full strength: a value you chose yourself
  is never overruled.

### 🐞 Fixed

- **The Stop button under the progress bar was clipped** while the file was
  being written. It now keeps its word and is greyed out instead, which says
  the same thing and stays the same size.

- **The How it looks section no longer runs past the column.**

### 📖 Documentation

- **[docs/DESIGN-ti1-ti2.md](docs/DESIGN-ti1-ti2.md)** — a full design for
  opening `.ti1` and `.ti2` charts and checking their patches against a
  profile, including the circularity trap that makes the obvious version of
  that check meaningless, and the questions that need answering before any of
  it is built.

- **[docs/PORTING-TO-CHROMIQ.md](docs/PORTING-TO-CHROMIQ.md)** — what would
  move across, and the five things that cost a day each.

## v2.0.1

### 🐞 Fixed

- **The look chooser was cut off.** Measured: the left-hand column is 346
  pixels, and a chooser sharing a row with three small buttons is left about
  116 for its text while *For a white document* needs 133. The buttons now sit
  under it, which costs nothing and gives it the width.

- **The percentage sat a pixel and a half high on Windows**, where the font is
  substituted for one this was never measured on. The ink rectangle is now
  used exactly as the font reports it rather than assumed to sit on the
  baseline.

### 📖 Documentation

- **The loops are now two to a page**, across five pages you can step through,
  each at 1100 pixels and quality 95 with every frame kept. Nine of them, up
  from six, including the neutral grey axis, two papers in rooms of their own,
  and one with **no background at all** — that one takes on whatever page it
  lands on, so it is dark on GitHub's dark theme and white on its light one.

- The sRGB comparison loop is withdrawn. It never showed what its caption
  claimed, and re-exporting it properly turned up something worth
  understanding first: with a comparison loaded the axes stretch until L* runs
  from −100 to 100 and the picture flattens to edge-on.

## v2.0.0

### ✨ New

- **Films: MP4 (H.264), MP4 (H.265) and WebM (VP9)** join WebP, GIF and APNG
  when saving the turning view. A film is markedly smaller for the same
  sharpness — about half an animated WebP for H.264, nearer a third for the
  other two, measured on this application's own view — and **WebM (VP9) is the
  only moving kind that can be see-through**, which is what a web page wants.
  A copy of ffmpeg travels with the application, so there is nothing to
  install; **Where ffmpeg is…** points at your own if you keep one. Only the
  formats a build can really write are offered, and the rest say why.

- **Viewer and export styling**, a section of its own in the left-hand column.
  What is behind the shape, what the three walls are, and what colour the
  lettering and the grid lines come out — with ready-made **looks** named for
  where the picture is going (*For a white document*, *For a dark slide*,
  *Cut out for a light page*), and the window's own dark and light among them.

- **Live preview.** With it ticked the view in front of you *is* the picture
  that will be saved, so setting one up is a matter of looking at it rather
  than imagining it — and it doubles as a way to have the application itself
  look how you like. It is remembered for next time.

- **Looks you save yourself**, under a name, as one small file each, kept
  beside ChromIQ's own presets and with the same three buttons: save, remove,
  open the folder. Sharing one is sending somebody a file. **Removing never
  deletes** — it moves the file into an `old` folder with the date on it.

- **A picture of the result in the Save window**, made by the export's own
  steps so it cannot disagree with the file. See-through is shown on chequers,
  which is the one thing no window can show directly.

- **Colour pickers that belong to this application** rather than the system's
  floating palette, each with a see-through setting and the colours already in
  the picture ready to hand.

### 🐞 Fixed

- **The Quality slider never reached a moving picture.** Every animated WebP
  was written at whatever the library felt like — 80 — which put a visible
  shimmer on the surface as it turned. It is now shown for moving pictures and
  films alike, and for a film it becomes the encoder's own quality, so the same
  number means the same picture whichever you choose.

- **See-through was silently solid.** A copy of the screen has no see-through
  in it, so asking for it politely and grabbing gave back a picture in whatever
  colour happened to be behind it. Each frame is now taken twice, on white and
  on black, and the difference *is* the transparency — exact, including the
  soft edges.

- **The lettering kept the screen's colour whatever it landed on**, so saving
  on a white background gave pale grey on white and the scale could not be
  read at all. It now follows the background it is actually on.

- **The percentage sat below the middle of the progress bar** — three pixels
  at ordinary resolution and five on a high-resolution screen — because Qt
  centres it on the whole widget, margin and all, rather than on the coloured
  bar.

- **The progress bar reached 100% with the file not yet written.** Taking the
  frames is most of the job for a film and rather less for a WebP; the bar now
  covers both parts and never claims to be finished before it is.

- **Writing the file no longer blocks the window.** It happens on a thread of
  its own, and a film can be stopped part way because the encoder is a separate
  program. This was the last thing here that could look like a hang.

- **A long moving picture no longer costs hundreds of megabytes of memory.**
  Frames are finished and handed on as they are taken rather than kept.

- An APNG is saved as `.png`, which every viewer opens, rather than `.apng`,
  which few do.

### 📖 Documentation

- A single sharp loop at the top of the README, and **six more with every
  setting behind each** on [docs/MOTION.md](docs/MOTION.md) — re-exported at
  full quality, keeping every frame.
- [docs/THIRD-PARTY.md](docs/THIRD-PARTY.md) says what travels with a release
  and under what terms, including why ffmpeg is run as a separate program.

## v1.9.6

### 🐞 Fixed

- A test compared folders as text. A URL gives forward slashes everywhere
  while Windows writes backslashes, so the comparison matched nothing there —
  failing on Windows alone.

## v1.9.5

### 🐞 Fixed

- A test assumed every machine has a Desktop and a Pictures folder, which a
  build runner does not — so the Linux builds failed on a machine state rather
  than on anything wrong with the application.

## v1.9.4

### 🐞 Fixed

- **The progress bar and its Stop button were touching**, which read as one
  broken control rather than two, and the percentage inside the bar sat above
  the middle.

### 📖 Documentation

- **Six moving pictures, on a page of their own** — `docs/MOTION.md` — each
  saying exactly which controls produced it. Two are on the README; the rest
  are one click away, so a page that loads on every visit does not carry ten
  megabytes of animation.

### Known

- **Writing the file at the end of a moving picture blocks the window** for a
  few seconds — longer for a large one. The frames are taken smoothly and the
  window answers throughout that part; it is the final encoding, a single
  step that cannot be interrupted, which still stops it. It needs to move off
  the main thread.

## v1.9.3

### 🐞 Fixed

- **Saving no longer offers folders you cannot write to.** Every file dialog
  here is the application's own rather than the system's, so it can carry
  useful shortcuts down the left — but the ones for opening a colour profile
  belong to the operating system, and offering them while saving a picture was
  three shortcuts to a refusal. Opening still offers them; saving offers the
  Desktop, Pictures, Downloads, Documents and your ChromIQ folder.

## v1.9.2

### 🐞 Fixed

- **The progress bar wears your accent colour** while a moving picture is
  made. Left to itself it was drawn in the operating system's own blue — the
  one thing in the window answering to nothing you chose.

## v1.9.1

### 🐞 Fixed

- **Saving a moving picture no longer looks like a hang.** Taking a hundred
  and sixty frames keeps the window busy for a quarter of a minute, and the
  shape stood still throughout — so the application appeared to have stopped
  responding, with a spinning cursor and nothing happening.
- **It now says what it is doing** — *Taking the frames… 62 of 160*, then
  *Putting the picture together…* — and the shape can be seen moving through
  the frames as they are taken. Measured: the window answers 238 times during
  an eighteen-second export, with no gap longer than 0.17 s.
- **It can be stopped.** Press **Stop** and nothing is written at all — a file
  holding half a journey would loop badly and look like a fault — and the view
  goes back to exactly where it was, to the sixth decimal.

## v1.9.0

### ✨ What's new

- **A moving picture has its own size now** — the window's size, 1200, 900,
  600, or a width of your own. Smaller is scaled down cleanly and makes a
  markedly smaller file; larger than the window is brought back down to it,
  because a copy of the screen cannot hold more detail than the screen had.

### 🐞 Fixed

- **Exported loops no longer jump.** A frame was sometimes photographed before
  the shape had finished moving, which left one frame identical to the one
  before and made the next cover twice the distance. Each frame now waits for
  the picture to be painted: measured over forty-eight frames, one stalled
  frame became none.
- **Up and down reaches the file.** A shape set to tip as well as turn was
  exported only turning — the tilt was worked out and then passed as zero.

## v1.8.0

### ✨ What's new

- **Open a picture and see whether it will print.** A photograph can now be
  one of the shapes: open it beside a paper you have measured and the readouts
  answer the question people actually have — how much of this image the paper
  can reproduce, and, picked out on the shape itself, exactly which colours it
  cannot.
- **It is the colours in the picture, not the space it was saved in.** A real
  photograph uses a small part of what its file could hold. Measured on this
  application's own test pictures: a warm sunset comes to **19% of sRGB**, a
  misty morning to **8%** — and both print almost perfectly, at 98% and 99.9%,
  where an image using all of sRGB would lose a third of its colours.
- **Nearly every picture format**: JPEG, PNG, TIFF, WebP, AVIF, **HEIC** —
  what every iPhone photograph is — **JPEG XL**, BMP, GIF, JPEG 2000 and more.
  Seventy-three file endings on a normal installation, and the list is asked
  of the machine rather than written down, so nothing is offered that would
  fail and nothing that works is hidden.
- **A picture's own colour profile is used** when it carries one. When it does
  not, sRGB is assumed — the usual convention — and the line under the name
  says so, because an assumption that changes the answer should never be made
  quietly.
- See-through pixels are ignored, since a pixel nobody can see is not a colour
  the picture shows.

### 🐞 Fixed

- A picture is never described as printing anything: the coverage line says
  what it *holds*. "What this photograph can print" was simply wrong.

## v1.7.1

### ✨ What's new

- **The web page has choices now.** It can **carry the viewer inside it**, so
  it opens on a machine that has never been online and still will in ten
  years — or **fetch the viewer when opened**, which leaves about 4.7 MB out
  of the file and is often the difference between an email that sends and one
  that bounces. Carrying it stays the standard, because working with no
  network at all is what this application promises everywhere else.
- **The numbers can travel with the picture.** Everything the readouts show —
  how much colour each shape holds, how much of one fits inside the other both
  ways round, any drift between two readings — is written under the picture as
  plain text. A shape sent without them is a shape nobody can check.
- **More frame rates for a moving picture**: 15, 24, 25, 30, 50 and 60 a
  second. 25 and 50 are the European television rates and 30 and 60 the
  American ones; 24 still looks perfectly smooth for something turning slowly,
  and above 30 the file grows quickly for a difference few people can see.
- A web page is never written over one already there, the same as every other
  export.

## v1.7.0

### ✨ What's new

- **Save this view as a picture…** — the third way of taking something with
  you, beside the web page and the table of numbers. A picture is for showing
  somebody; the web page keeps it turnable; the table is for arithmetic.
- **A still, at any size.** Named by what it is for — a forum post, a
  document, a slide, printing — or a width of your own. The viewer draws it
  again at that size rather than copying the screen, so it can be far larger
  than the window and stays sharp.
- **A moving picture that turns and repeats**, as WebP, GIF or APNG. It shows
  every side of the shape in the space one still takes, which is the whole
  difficulty with a gamut on paper. The loop closes exactly, so there is no
  jump each time round.
- **Choose what is behind it** — as on screen, white, black, a colour of your
  own, or **see-through**, so the shape sits directly on whatever page you
  drop it onto.
- **The grid's walls are set separately**, with their own colour or their own
  see-through, so you can have the box stand out from the page, fade back, or
  vanish entirely and leave the shape floating with only its grid lines.
- **It says how big the file will be** before you make it, so nothing is a
  surprise.
- **Nothing of yours is written over.** A picture saved beside one already
  there is named `-2`, never on top of it.

### 🐞 Fixed

- SVG is offered for the flat cross-section, where it genuinely is made of
  outlines and comes to about 12 kB. The 3D view is drawn by the graphics
  card and has no outlines to save — an SVG of it is an ordinary picture in a
  wrapper, thirty times the size and no sharper — so it is not offered there
  and the help says why.

## v1.6.1

### ✨ What's new

- **The flat cross-section works side by side too.** Tick **Slice it at one
  lightness** and **Show them in two rooms, side by side** together, and the
  two cuts are drawn in their own halves instead of on top of each other —
  useful when one shape sits almost entirely inside the other and the overlap
  hides what you are trying to see.
- **Both halves share one scale**, worked out from both shapes at once. Left
  to itself each half would size itself to whatever is in it, so a small gamut
  and a large one would be drawn exactly the same size — a comparison saying
  the opposite of the truth. A smaller gamut looks smaller.
- **Zoom or drag one cut and the other follows**, while **Keep both rooms
  pointing the same way** is ticked — the flat equivalent of keeping two 3D
  views aimed alike.

### 🐞 Fixed

- **Showing two rooms did nothing while slicing.** The control stayed ticked
  and available and was quietly ignored, which the app's own rule forbids: a
  control that cannot do anything is worse than one that is not there.
- Each cut keeps the colour its shape has in the overlaid view, instead of
  both being drawn in the first colour.

## v1.6.0

### ✨ What's new

- **Start with whatever you have.** An ICC profile can now be the thing you
  look at, not only the thing you compare against — so you can open a profile
  first, on its own, and see the shape it describes. Opening a file always
  shows you that file now; comparing is what **Compare with** is for.
- **Compare against a measurement too.** The **Compare with** list offers *A
  profile or a measurement file…*, so a paper can be held up against another
  paper's measurement as easily as against a profile or sRGB. Each open file
  says underneath which kind it is, because a profile is never a measurement.
- **The file dialog knows where profiles live** on all three systems — the
  ColorSync folders on a Mac, the colour folder on Windows including your own
  under AppData, and the ICC folders on Linux. The same list ChromIQ uses.
  Folders that hold nothing are not offered.
- **It looks for a newer version on starting.** One question to the releases
  page — is there a newer version? — and nothing else: no account, no name,
  nothing about your computer or your measurements, and it never downloads or
  installs anything. Untick it under **This window** and it never looks again.

### 🐞 Fixed

- **Opening an ICC profile appeared to do nothing.** It was loaded, put
  straight into the comparison, and a comparison is only ever drawn beside a
  chart — so with nothing else open, nothing was drawn and nothing was said.
- **Choosing the same entry in Compare with a second time did nothing at
  all** — no dialog, no file. Swapping to a different profile meant picking
  something else first and coming back.
- **Empty space at the bottom of a section.** Hidden rows were leaving their
  space behind in three different ways, and it grew as more options were
  hidden. Every section now ends the same distance below its last control, and
  grows back exactly as before when options return.
- **Turn it by itself sat lower than every other option** in its section, by
  seven pixels, because the row above it left its spacing behind when hidden.
- The accent colours are offered in the colour bar's own order: magenta,
  amber, green, cyan, violet.
- **Words that named only one kind of file** — the buttons, the group, the
  per-shape controls — now cover both. A *chart* is the sheet of patches you
  print; a *measurement* is what your instrument made of it, and that is the
  file you open.

## v1.5.2

### 🐞 Fixed

- **ICC profiles are now read exactly, rather than very nearly.** The
  specification fixes the colour connection space's white as three exact
  numbers, which are not quite the CIE D50 a colour library gives you — the
  Z differs in the fourth decimal. Using the textbook value left a constant
  difference of ΔE 0.0248 against ArgyllCMS on every profile tested; using
  the specification's own constant leaves ΔE 0.000002, which is the precision
  the comparison can express at all. Far too small to see, and the whole
  distance between agreeing with ArgyllCMS exactly and agreeing with it
  approximately.

### 📖 Documentation

- **What "agrees to 0.2%" actually means.** Reading a profile and working out
  a gamut are two different claims and the README now separates them: reading
  is exact, because nothing in the file is open to interpretation; the 0.2% is
  in deriving a *boundary*, which needs sampling the file says nothing about,
  because a gamut is not stored in a profile at all.

## v1.5.1

### 🐞 Fixed

- **The quieter buttons were nearly invisible in the light appearance.**
  Their fill sits one step away from the window behind them — a contrast of
  1.01 to 1, which is nothing at all — so **Start again with standard
  settings**, **What do these words mean?**, **Where ArgyllCMS is…** and the
  rest read as plain text rather than as buttons. They have an edge now, in
  both appearances. An edge rather than a darker fill, because a darker fill
  would make them look permanently pressed.
- **Appearance and Accent are set as the headings they are.** Each names the
  group of choices underneath it rather than labelling one control beside it,
  so they no longer read as part of the row below.

## v1.5.0

### ✨ What's new

- **ICC version 4 profiles open.** Display P3, Rec. 709, Rec. 2020, ROMM RGB
  and the v4 profiles paper makers hand out could not be compared against
  before — ArgyllCMS declines them, and it was doing all the reading. They are
  now read directly when it turns one down. On every profile both can read,
  the two answers agree to **well under one per cent** (median 0.2%), which is
  what makes the new reader worth believing on the files only it can open.
- **Turn it by itself.** The shape can move on its own, so you can watch it
  from every side without holding the mouse — which is the difference between
  guessing at a dent and seeing it, because depth only really reads when
  something moves. **Left and right** and **up and down** are set separately,
  each with its own way of moving (a limited swing back and forth, or all the
  way round), its own speed and its own distance. Touch the picture and it
  stops at once, then carries on from wherever you left it.
- **Show the box and its grid** can be turned off, leaving the shape floating
  on the page with no walls, numbers or axis names. Much better for a picture
  going into a document, a slide or a forum post.
- **ArgyllCMS is found wherever it is**, including the version-numbered folder
  the official download unpacks into, which was the one place not being looked
  in. **This window** now says whether it was found, and **Where ArgyllCMS
  is…** lets you point at it or open the download page. Nothing nags you about
  it: measurements, gamut files and ICC profiles all open without it, and only
  `.cxf`, `.mxf` and `.txt` need it.

### 🐞 Fixed

- **Setting the lighting yourself moved nothing.** Which side the light comes
  from and how high it hangs were read from the controls and then dropped
  before the surface was drawn. They work now — and the standard lighting is
  the high, slightly-to-one-side key light it was always meant to be, so every
  shape is modelled a little more clearly than before.
- **The surface looked grainy where it is smooth.** A boundary built from the
  faces of the device cube repeats every point along the twelve edges where
  two faces meet — 27% of them on a 1168-patch chart — and two copies of a
  corner cannot share a shading normal, so a crease was drawn along every
  seam. The dents are untouched; only the false creases have gone.
- **A profile in a system folder could not be opened at all** on macOS: the
  copy step asked to carry the file's permissions and flags across, which the
  operating system refuses for its own files. That is the folder holding
  sRGB, Adobe RGB and Display P3, so it was the obvious one to browse to.
- **The wire cage was a dark mass in the light appearance.** Hundreds of thin
  lines at the weight of text add up; on a pale page they shouted down the
  measured shape they are only there to frame, and went nearly solid at the
  rims. The cage is lighter now, while its key in the legend keeps its full
  weight so it can still be seen.
- **Side by side drew the second chart as a grey wireframe.** An outline is
  there so you can see *through* the shape on top to the one behind it. Side
  by side there is nothing behind it, so both are now drawn solid.
- **The names have come out of the drop-down boxes** and sit beside them,
  where they are said once instead of on every line of the open list.

## v1.4.0

### 🐞 Fixed

- **Side by side drew the second chart as a grey wireframe.** An outline is
  there so you can see *through* the shape on top to the one behind it, which
  is what you want when the two are drawn over each other. Side by side each
  chart has a picture to itself with nothing behind it, so the outline was
  only ever a worse drawing of the same gamut. Both are now drawn solid, and
  your solid/outline choice still applies as before when they are overlaid.

### ✨ What's new

- **Two links at the foot of the settings column**: one to the ChromIQ
  website, and one to Ko-fi if you would like to buy a coffee. The
  application is free and stays fully featured either way.

## v1.3.1

### 🐞 Fixed

- **"See-through: 100%" said the opposite of what it did.** At 100% the shape
  is fully solid, so the control is called **How solid it looks**.
- **The settings column fades at its edges** when there is more to scroll to,
  in both light and dark, so a long column no longer looks as though it stops
  where the window does.

## v1.3.0

### ✨ What's new

- **Move the light.** Two more controls under **Set the lighting myself**:
  which side the light comes from, and how high it hangs. Dropping it lower
  throws longer shadows across the surface, which can make a shallow dent
  easier to see.
- **The accent tint is smooth.** It used to snap every colour to one of six
  accent hues, which showed as six flat patches with hard seams. It is a
  continuous sweep now.
- **Show every patch I measured** has its own ⓘ, as does everything in
  **This window**.

### 🐞 Fixed

- Side by side: each shape is centred in **its own half**, and stays centred
  when the window is resized.

## v1.2.0

### ✨ What's new

- **Two rooms, side by side.** Overlaying two shapes shows where one reaches
  past the other; it does not let you judge either on its own, because the
  one in front hides the one behind. Tick **Show them in two rooms, side by
  side** and each gets its own scene.
- **Their cameras stay together** by default, so you are always comparing the
  same face of both. Untick **Keep both rooms pointing the same way** to move
  each on its own.
- **In the accent colours** — a new way to paint the shape, tinting it into
  the accent family while keeping every point's own lightness, so the shape
  still reads as a shape. The same idea, and the same hue bands, as ChromIQ's
  own theme-coloured gamut viewer.
- **Every setting in "This window" now has its ⓘ** as well.

## v1.1.0

### ✨ What's new

- **It looks like ChromIQ now**, because it is meant to sit beside it: the same
  masthead and colour bar, the same palette down to each value, the same Inter
  type, and the same round **ⓘ** beside every setting.
- **Every explanation is behind that ⓘ.** Hover for a one-line answer, click
  for the full text in a window wide enough to read it. An option that is
  hidden takes its ⓘ with it.
- **There is a log**, so a fault that happened once can still be looked at.
  It never leaves your machine and cannot grow past 10 MB.

### 🐞 Fixed

- The window opens **centred**, on the screen it actually appears on, and fits
  a small display — it can go down to 832px wide.
- Scrolling the settings column no longer **changes a setting** under the
  pointer.
- Hovering a combo box, checkbox or slider now outlines it in **your accent
  colour** instead of a grey that looked like nothing had happened.
- The legend key beside each shape is **visible on a dark page**.
- The caption above the picture is a caption, not a banner, and reads the same
  way in every view.
- Slider handles are round; checkbox labels have room; the radio choices under
  Appearance and Accent are no longer nearly touching.

## v1.0.1

### ✨ What's new

- **It can tell you when a newer version is out.** **Check for a newer
  version…** looks at the releases page and says what it finds. It never
  downloads or installs anything by itself — the most it does is show you a
  version number and offer the link.
- **Nothing about you is sent, and it stays off until you ask.** Everything
  else in the window works with no internet connection at all, so the
  unattended **Check when the app starts** option begins switched off. Pressing
  the button is itself the consent for that one request.
- A check you asked for always answers, even to say you are up to date. An
  unattended one speaks up only when there really is something newer.
- If the site cannot be reached, it says so as the ordinary thing it is —
  never as a fault with your copy.

### 📖 Documentation

- The release notes and README said no network was used. That is now stated
  precisely instead: no request is made unless you ask for one.

## v1.0.0

The first release. See the gamut your printer **actually measured** — not the
one its profile claims — and compare it against another paper, a standard
colour space, any ICC profile, or the boundary of what the eye can see.

### ✨ What's new

- **A gamut built from your measurements.** Open the `.ti3` file ArgyllCMS
  writes when you read a printed chart, and see the colours those patches
  enclose, in 3D, painted in their own colours, with the volume in the same
  cubic Lab units ArgyllCMS reports.

- **A shape that follows your printer's real boundary.** A printer's gamut is
  dented, especially in the deep blues. Given the device values alongside the
  measurements — which a `.ti3` already carries — the surface keeps those dents
  instead of throwing a convex hull over them and claiming more colour than you
  have. You can switch between the two and see the difference for yourself.

- **Compare two papers, honestly.** Coverage is shown in **both directions**,
  because it is not symmetric: a glossy paper might hold 96% of what a matte one
  shows while the matte holds only 71% of the glossy. One "similarity" number
  would hide exactly the difference that decides which paper to use.

- **Compare against a standard space.** sRGB, Adobe RGB (1998), Display P3,
  ProPhoto RGB and Rec.2020 are built in and need no files — useful for asking
  whether the images people send you will survive on a given paper.

- **Compare against any ICC profile.** Point it at an `.icc` or `.icm` and its
  gamut is built the same way, so a paper can be checked against the profile a
  client actually sent.

- **Compare against what the eye can see.** The boundary of every colour a
  surface can show under a chosen light, so a gamut can be judged against
  human vision rather than only against another piece of paper.

- **See *where* you lose colour, not just how much.** Tick **Show me what the
  comparison cannot print** and your chart is painted red wherever the colour
  is out of the other one's reach, grey where it is fine. A percentage tells
  you how much you lose; this tells you which colours, so you can decide
  whether it matters for the pictures you actually print.

- **Slice it at one lightness.** Two shapes in 3D hide each other and depth is
  hard to judge on a screen. Cut through them at the lightness you choose and
  they become two flat outlines side by side, where "this paper reaches
  further into the cyans" is a glance rather than a guess.

- **Draw each shape its own way.** Solid, solid with its mesh, or outline only
  — separately for your first chart, your second, and the comparison. An outer
  shape drawn as an outline is the only way to look at your printer sitting
  inside sRGB and still see your printer.

- **A page you can keep or send.** Save the view as one self-contained HTML
  file. The viewer travels inside the page, so it opens in any browser with no
  network, now or in five years.

### Colour science

Measurements are referenced to **D50**, as print measurement is, and every
conversion states its white point. Working spaces defined against D65 are
Bradford-adapted rather than treated as though the whites were the same.
Coverage is measured with a fixed seed, so the same pair of gamuts always gives
the same answer, and reports its own margin of error rather than inviting false
precision.

<p align="center">
  <a href="https://ko-fi.com/itsab1989"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support this on Ko-fi" height="36"></a>
  <br>
  <sub>The ChromIQ Gamut Viewer is free and always will be. If it's useful to you, a coffee is a kind way to say thanks — completely optional, and it stays fully featured either way.</sub>
</p>
