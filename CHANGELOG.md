# Changelog

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
