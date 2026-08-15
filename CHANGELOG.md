# Changelog

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
