# Changelog

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
