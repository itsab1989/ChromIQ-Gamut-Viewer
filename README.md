# ChromIQ Gamut Viewer

**See the colours your printer *actually* produced — not the ones its profile
claims it can.**

Open the measurement file your instrument wrote when you read a printed chart,
and this draws the solid shape those colours enclose. Then it answers the
questions that shape exists to answer: will the photos people send me survive
on this paper, which of my two papers should I use, has my printer drifted
since last month, and does my ICC profile actually describe what came off the
printer?

<p align="center">
  <img src="docs/screenshots/hero-turning.webp" width="880"
       alt="A measured printer gamut turning gently, showing the dents and bulges of its real surface from every side">
</p>

<p align="center"><sub>A real measured gamut, turning. Made by the
application itself — <b>Turn it by itself</b>, then <b>Save this view as a
picture…</b>. <a href="docs/MOTION.md">Six more, with the settings behind
each →</a></sub></p>

<p align="center">
  <a href="https://ko-fi.com/itsab1989"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support this on Ko-fi" height="36"></a>
  <br>
  <sub>Free, and always will be. If it's useful to you a coffee is a kind way to say thanks — completely optional, and it stays fully featured either way.</sub>
</p>

> **A fork.** This began as [Yet Another Color Gamut
> Visualizer](https://github.com/QiuJueqin/Yet-Another-Color-Gamut-Visualizer)
> by Qiu Jueqin — a MATLAB tool whose real insight is at the heart of this one.
> It has been ported to Python, given a window, and extended a long way. The
> original is MIT licensed, which permits a modified copy under another name so
> long as the copyright notice travels with it; `LICENSE` is kept exactly as
> inherited. The name changed because it grew into a companion to
> [ChromIQ](https://github.com/itsab1989/ChromIQ) and reads the files ChromIQ
> produces.

---

## Why this is not the same as looking at your ICC profile

Most tools draw the gamut of a **finished ICC profile**. A profile is a fitted
model of your printer: it smooths, it interpolates, and near the edges it can
promise a little more or a little less than the paper really gave.

This draws the **measurements**. Every point on the surface is a patch that was
printed and read by an instrument.

|  | asks | answers |
|---|---|---|
| A profile's gamut | the finished ICC profile | what your printer is **described** as able to do |
| This | the measurement file | what it **did**, on that paper, on that day |

Holding the two against each other is a check you cannot easily make otherwise
— and it is [one of the six walkthroughs below](#5-does-my-icc-profile-match-what-my-printer-really-did).

---

## Getting it

Download the build for your machine from the
[**Releases**](https://github.com/itsab1989/ChromIQ-Gamut-Viewer/releases)
page. Nothing else needs installing — Python, Qt and the 3D viewer all travel
inside the download.

| Your computer | Download |
|---|---|
| Mac with Apple silicon (M1 and later) | `GamutViewer-macOS-arm64.zip` |
| Mac with an Intel processor | `GamutViewer-macOS-x86_64.zip` |
| Windows 10 or 11, 64-bit | `GamutViewer-Windows-x64.zip` |
| Linux, 64-bit Intel or AMD | `GamutViewer-Linux-x86_64.tar.gz` |
| Linux on ARM (including a Raspberry Pi 5) | `GamutViewer-Linux-aarch64.tar.gz` |

**On macOS**, the first launch needs a right-click → **Open** rather than a
double-click, because the build is not signed with a paid Apple developer
certificate. You only have to do that once.

Prefer to run from source? See [Running from
source](#running-from-source-and-the-tests) at the end.

### What you need to have ready

One **measured chart** — the file your instrument wrote after reading a printed
test chart. If you profile with [ArgyllCMS](https://www.argyllcms.com/) or with
[ChromIQ](https://github.com/itsab1989/ChromIQ), that is the `.ti3` file sitting
beside your profile. Other formats are listed under [What it
opens](#what-it-opens).

You do **not** need an internet connection or an account, and nothing about
you, your printer or your measurements is ever uploaded.

**One thing does reach the internet, and only one.** When the app starts it
asks this project's releases page a single question — "is there a newer
version?" — and tells you the answer. That is the whole of it. It sends no
account, no name, nothing about your computer, your printer or anything you
have measured, and it never downloads or installs a thing: if a newer version
exists, you get a version number and a link, and it is entirely up to you
whether you follow it.

It is switched on to begin with, because a colour tool quietly running a year
out of date helps nobody. If you would rather it did not, untick **Look for a
newer version when the app starts** under **This window** and it will never
look again — everything else in the app works with no network at all. You can
still check whenever you like with the **Check for a newer version…** button
just above it.

---

## Six things you can find out

Every screenshot below is the real window, driven through that exact step.

### 1. What can this paper actually print?

Open a measured chart — click **Open a measured chart…**, or drag the file onto
the window. The shape appears, painted in the colours it represents, and
**How much colour it holds** puts a number on it.

<img src="docs/screenshots/01-one-chart.webp" width="880" alt="One measured chart drawn as a solid coloured shape, with its volume reported beside it">

Underneath the volume you also get the two numbers that decide how much
contrast the paper can give you: **how dark the blacks reach, and how bright
the paper white is.** A paper that cannot go dark loses shadow detail no matter
how large its volume is.

> On the demo chart above: 1,168 patches, 702,327 cubic Lab units, blacks
> reaching L\* 4 against a paper white of L\* 94.

The volume on its own does not mean much — it is for **comparing** two papers
measured the same way. Everything below is a comparison.

### 2. Will the photos people send me survive on this paper?

Set **Compare with** to **sRGB** — what most photographs and most screens
assume. The comparison is drawn as an outline around your paper, and you get
coverage **in both directions**.

<img src="docs/screenshots/02-vs-srgb.webp" width="880" alt="A measured paper drawn inside the sRGB outline, with coverage reported in both directions">

Both directions, because they answer different questions and are rarely the
same number:

> 77.7% of what this paper can print also fits inside sRGB.
> 65.2% of sRGB fits inside this paper.

The first says how much of your paper an sRGB workflow can even address. The
second says how much of an incoming sRGB image your paper can reproduce. A
single "similarity" figure would hide exactly that difference.

To see **where** the colour is lost rather than how much, tick **Show what the comparison cannot print**. Everything the comparison cannot reach turns
warm red against muted grey:

<img src="docs/screenshots/03-where-lost.webp" width="880" alt="The same shape with the regions the comparison cannot reproduce highlighted in red">

You can compare against sRGB, Adobe RGB, Display P3, ProPhoto RGB, Rec. 2020,
any ICC profile on your computer, or **everything the eye can see** — the
theoretical limit for a surface colour under that light. No printer comes close
to the last one, and that is normal.

### 3. Which of my two papers should I use?

Open a second chart and both are drawn together. Three separate figures appear,
because "which is better" is really three questions:

<img src="docs/screenshots/13-how-the-two-compare.webp" width="880" alt="Two papers compared, showing shared colour, which reaches further in each hue family, and both lightness ranges">

- **Does one fit inside the other?** Coverage, both ways round.
- **How alike are they?** *Both can print 76% of everything either one can.*
  Unlike coverage this is the same number whichever way you ask it, so it
  answers "are these two the same paper, really?"
- **Where does each one win?** *Glossy-paper reaches further in the yellows,
  greens, cyans, blues and magentas.* This is usually the decision: a paper
  that reaches further in the cyans and blues suits skies and water, one that
  reaches further in the yellows and reds suits skin and autumn.

A hue family is only called a win when it is more than 2 chroma units clear.
Smaller than that is neither visible nor worth trusting, and announcing it
would let the readout contradict itself.

### 4. Has my printer changed since last time?

Open two readings of the **same** chart. As well as the shapes, you get a
patch-by-patch comparison in ΔE2000 — the modern colour-difference measure.

<img src="docs/screenshots/05-drift.webp" width="880" alt="Two readings of one chart compared patch by patch, listing the patches that moved most">

> 1,035 patches appear in both readings.
> Biggest difference ΔE 2.56, average 0.77.
> Visible on a careful look.
> …and the individual patches that moved most, named by their device values.

Patches are matched on the **device values** rather than the patch number,
because charts are randomised and the same colour rarely carries the same
number twice. If fewer than half the patches appear in both files, it says
these are not two readings of one chart instead of producing a confident
figure that describes nothing.

### 5. Does my ICC profile match what my printer really did?

Open your measured chart, then set **Compare with** to **An ICC profile on my
computer…** and pick the profile built from it.

<img src="docs/screenshots/06-profile-vs-measured.webp" width="880" alt="A measured chart drawn against the gamut of the ICC profile built from it">

A profile that bulges well outside the measured cloud is over-promising; one
that sits well inside is leaving gamut on the table. On the demo chart and the
profile built from it:

> 97.2% of what the measurement can print also fits inside the profile.
> 83.9% of the profile fits inside the measurement.

The profile is always labelled **(profile)** in the figures, so a profile and
the chart it was built from — which usually share a name — can never be
confused for each other.

ICC profiles are read through ArgyllCMS's own `iccgamut` when it is installed,
so the shape is the one ArgyllCMS itself would draw.

### 6. Are my greys actually grey?

Tick **Show the greys**. The neutral axis is drawn through the solid, and every
grey patch is marked with how far it has drifted from neutral.

<img src="docs/screenshots/07-greys.webp" width="880" alt="The neutral axis drawn through the gamut with each grey patch marked">

A colour cast in the greys is the thing viewers notice first in a black and
white print, and it is invisible in the overall shape.

---

## Reading the picture

### Or give each one a room of its own

Two shapes in one picture shows where one reaches past the other. It is the
wrong way to judge either on its own, though — the shape in front hides the
one behind, and whichever is drawn on top looks bigger than it is.

Tick **Show them in two rooms, side by side** and each gets its own scene:

<img src="docs/screenshots/14-side-by-side.webp" width="880" alt="Two measured papers drawn in two separate 3D scenes side by side">

Turn one and the other turns with it, so you are always comparing the same
face of both — that is what makes two rooms worth having. Untick **Keep both
rooms pointing the same way** to move each on its own.

### Tint it into the accent

**How the shapes are coloured → In the accent colours** paints the gamut in
the colour family the rest of the window uses. Each point keeps its own
lightness, so the shape still reads as a shape; only the palette changes.

<img src="docs/screenshots/15-accent-colours.webp" width="880" alt="A measured gamut tinted into the application's accent colours">

### Turn it, or cut it open

The 3D view can be spun, zoomed and panned with the mouse. When two shapes
overlap they hide each other, so **Slice it at one lightness** cuts both at the
same height and turns the comparison into two flat outlines, where "this one
reaches further into the cyans" is simply visible:

<img src="docs/screenshots/08-slice.webp" width="880" alt="A horizontal cross-section through both gamuts at one lightness, drawn as flat outlines">

**Show rings inside** stacks cross-sections within the cage, which is what
shows whether your mid-tones or your highlights are the tight part.

### Every shape, styled its own way

**Set this for** aims the appearance controls at *all shapes together*, the
*first chart*, the *second chart*, or the *comparison*. So you can leave one
paper as a solid and show the other as an outline over it, each with its own
opacity, colouring and depth.

<img src="docs/screenshots/11-controls.webp" width="880" alt="The controls column, with two explanations unfolded">

Every setting has an **ⓘ** beside it. Hover for a one-line answer, click for
the full explanation in a window wide enough to read it. An option that is
hidden takes its ⓘ with it.

### Light and dark

The whole window switches, and the 3D scene switches with it.

<img src="docs/screenshots/09-light.webp" width="880" alt="The same window in its light appearance">

There are five accent colours, four ways of colouring the shapes (true colours,
one colour each, by lightness, by chroma), a Depth slider, and — behind **Set
the lighting myself** — the five individual lighting values if you want to dial
in a particular look.

### Three colour spaces

**Draw it in** offers CIELAB, CIELUV and CIE XYZ. The same paper is a different
shape and a different volume in each:

| | CIELAB | CIELUV | CIE XYZ |
|---|---|---|---|
| | <img src="docs/screenshots/12-space-cielab.webp" width="260" alt="The gamut drawn in CIELAB"> | <img src="docs/screenshots/12-space-cieluv.webp" width="260" alt="The gamut drawn in CIELUV"> | <img src="docs/screenshots/12-space-ciexyz.webp" width="260" alt="The gamut drawn in CIE XYZ"> |
| Demo chart | 702,327 cubic Lab units | 931,617 cubic Luv units | 0.0786 cubic XYZ units |
| Good for | **print — the default** | displays and light sources | the raw measurement |

CIELUV has exactly the same lightness as CIELAB and arranges the colour
differently. CIE XYZ is the measurement before anything is done to make
distances match what the eye notices — honest, but hard to read by eye, and it
has no lightness axis and no grey axis, so the slice, the rings and the greys
are switched off while it is chosen rather than drawing something meaningless.

**Volumes and percentages are only comparable within one space.** Changing this
changes every number in the window, and that is expected.

### Every word explained

Anything that might be jargon has a plain-language entry under **What do these
words mean?** — fifteen of them, covering every such term the window can show.

<img src="docs/screenshots/10-glossary.webp" width="620" alt="The glossary window explaining each term in plain language">

---

## What it opens

| File | What it is | How it is read |
|---|---|---|
| `.ti3` | an ArgyllCMS or ChromIQ chart measurement | directly |
| `.cxf`, `.mxf` | X-Rite's measurement exchange formats | converted with ArgyllCMS `cxf2ti3` |
| `.txt` | a measurement table ArgyllCMS understands | converted with ArgyllCMS `txt2ti3` |
| `.icc`, `.icm` | an ICC profile — open it on its own, or use it as the comparison | ArgyllCMS `iccgamut`, or read directly if it declines |
| `.gam` | an ArgyllCMS gamut file | directly |

Converted copies are written to a temporary folder, **never beside your
original** — opening a file to look at it should not leave new files in your
measurement folder.

### Any of three kinds of file, in either place

**Open a measurement or a profile…** shows you the file you opened, whichever
kind it is. You can start with a profile and never open a chart at all. Open a
second and the two are drawn together.

**A picture can be one of them too** — a photograph, or anything else you can
open. What is drawn is *the colours actually in that picture*, not the space
it was saved in, and the difference is the whole point: measured on this
project's own test pictures, a warm sunset encloses **19% of sRGB** and a misty
morning **8%**. Open one beside a paper you have measured and the readouts
answer the real question — the sunset prints at **98%** on the demo paper and
the misty morning at **99.9%**, where an image using all of sRGB would lose a
third of its colours. Tick **Show what the comparison cannot print** and the
ones that fall outside are picked out on the shape itself.

A picture is read through its own colour profile when it carries one. When it
does not, sRGB is assumed — the usual convention — and the line under its name
says **read as sRGB**, because an assumption that changes the answer should
never be made quietly. JPEG, PNG, TIFF, WebP, AVIF, HEIC, JPEG XL, BMP, GIF
and JPEG 2000 all open; the list is asked of your own machine, so nothing is
offered that would fail.

**Compare with → A profile or a measurement file…** puts a third shape beside
them, and takes either kind as well — so you can hold a paper up against
another paper's measurement as readily as against a profile, sRGB or
everything the eye can see.

Every open file says underneath which kind it is. That distinction is the
point of the whole application, so a profile is never quietly called a
measurement: a *chart* is the sheet of patches you print, a *measurement* is
what your instrument made of it, and a *profile* is the fitted model built
afterwards.

The file dialog puts the places profiles actually live one click away — the
ColorSync folders on macOS, the colour folder on Windows including your own
under AppData, and the ICC folders on Linux. A folder holding nothing is not
offered.

### ICC version 4

Both versions open. ArgyllCMS reads version 2 thoroughly and version 4 only in
part, and declines a v4 profile outright — which matters, because v4 is not
exotic: **Display P3, Rec. 709, Rec. 2020 and ROMM RGB all ship with macOS as
v4**, and paper makers hand out v4 output profiles.

So when ArgyllCMS turns a profile down, the viewer reads it itself: it works
out where a dense grid of device values lands using the profile's own numbers,
and builds the boundary from that — the same way it treats a measured chart.
Matrix-and-curve profiles (every RGB working space, and every v4 display
profile) and lookup-table profiles (printers and presses) are both handled.

**It is checked against ArgyllCMS rather than against itself**, and in two
separate ways, because two different claims are being made.

**Reading the profile is exact.** Nothing in an ICC profile is open to
interpretation: given a device value, the matrix, the curves and the tables in
the file determine the colour. Fed the same values, this and ArgyllCMS's own
`icclu` return the same colour to a worst **ΔE of 0.000002** — which is that
tool's printing precision, not a real difference. If the two ever disagreed
about a colour, one of them would simply be wrong.

**A gamut is not in the file, and that is where the small difference lives.**
The file describes a *mapping* from device values to colours. A gamut is the
*boundary of everything that mapping can reach* — and finding a boundary means
sampling the mapping, which the specification says nothing about, because it is
not part of the format. ArgyllCMS samples on its own grid and builds a surface
its own way; this samples a 17-step grid per channel and follows the device
cube's faces. So the volumes land a median of **0.2%** apart, worst **0.9%**,
and always slightly *under* ArgyllCMS's — exactly what a sampled boundary does,
since it is inscribed in the true one.

Both tests live in `python/test_references.py` and run against whatever
profiles your own machine carries.

**One number is worth knowing about.** The specification fixes the connection
space's white as three exact numbers — 0.964203, 1.0, 0.824905 — which is not
quite the CIE D50 a colour library hands you (0.96422, 1.0, 0.82521). The Z
differs in the fourth decimal. Using the textbook value left a constant ΔE of
0.0248 against ArgyllCMS on every profile; using the specification's own
constant leaves nothing. It is a small number that decides whether "agrees
with ArgyllCMS" means exactly or approximately.

### Do you need ArgyllCMS?

**Usually not.** Measurements (`.ti3`), gamut files (`.gam`) and ICC profiles
all open without it. It is needed only for `.cxf`, `.mxf` and `.txt`, which it
converts — those formats have corners (spectral tables, several colour
specifications in one file, vendor extensions) and ArgyllCMS already handles
them correctly, so re-implementing that would be a worse answer, not a better
one. For ICC profiles it is *preferred* rather than required, because it works
the surface out in full precision.

It is found automatically in all the usual places, including the
version-numbered folder the official download unpacks into
(`Argyll_V3.5.0`). **This window** says whether it was found and where, and
**Where ArgyllCMS is…** lets you point at the folder yourself, or open
[argyllcms.com](https://www.argyllcms.com/) to get it — it is free, and it is
the same toolkit that reads a printed chart in the first place. Nothing nags
you about it on startup, because most people never need it.

### It moves, and you can take the movement with you

Depth is hard to judge on a flat screen — a dent in the deep blues and a
shadow look alike in a still picture. **Turn it by itself** sets the shape
moving, left and right, up and down, or both at once, and **Save this view as
a picture…** writes that movement out as a file you can drop into a forum
post, a document or a chat window.

Six kinds of file, in two families. **WebP, GIF and APNG** are pictures that
move: they start on their own and repeat for ever with nothing to press —
which is exactly what the loop at the top of this page is. **MP4 (H.264),
MP4 (H.265) and WebM (VP9)** are films: about half the size for the same
sharpness, with a play button. The films are made by ffmpeg, and a copy comes
with the application, so there is nothing to install.

The loop closes exactly — the file holds one complete journey fitted into the
seconds you chose — so it never jumps as it comes round.

**[Six more loops, with every setting behind each one →](docs/MOTION.md)**

### Everything around the shape is yours

**Viewer and export styling**, in the left-hand column, decides what a saved
picture looks like: what is behind the shape, what the three walls are, and
what colour the lettering and the grid lines come out. There are ready-made
looks named for where the picture is going — *For a white document*, *For a
dark slide*, *Cut out for a light page* — and the window's own dark and light
are two of them.

Tick **Live preview** and the view in front of you *is* the picture that will
be saved, so setting one up is a matter of looking at it rather than
imagining it. That also makes it a way to have the application itself look
how you like.

Looks you build yourself are saved under a name, as one small file each, in
the same folder ChromIQ keeps its own presets in — so sharing one is sending
somebody a file, and using one they sent is putting it in that folder.
Removing one never deletes it; it moves into an `old` folder with the date on
it.

*(There is [one dressed for a white document](docs/MOTION.md#dressed-for-a-white-page)
on the loops page, so this one stays light to load.)*

### A picture with nothing around it

<p align="center"><img src="docs/screenshots/18-no-grid.webp" width="820"
alt="The measured gamut drawn with no box, grid or axis labels around it"></p>

Untick **Show the box and its grid** and the walls, the grid, the numbers and
the axis names all go, leaving the shape floating on the page. Keep them while
you are reading the shape — they are what tell you how light a part of the
surface is — and drop them for a picture going into a document, a slide or a
forum post. It applies to the whole picture, so two rooms lose the box
together and the pair still match.

## What it saves

Three ways of taking something with you, answering three different questions.

| | For | Notes |
|---|---|---|
| **A picture** | showing somebody | still or moving, any size, see-through if you like |
| **A web page** | letting them turn it themselves | carries its viewer, or fetches it and saves 4.7 MB |
| **A table** | doing arithmetic on the numbers | plain CSV |

A **still** is redrawn by the viewer at whatever size you ask for, so it can be
far larger than the window — and for the flat cross-section it can be a real
vector SVG of about 12 kB. A **moving picture** is WebP, GIF or APNG. The
background and the grid's walls are set separately, each able to be a colour of
your own or see-through, so the shape can float on any page you drop it onto.

It says roughly how big the file will be before you make it, and never writes
over a file that is already there.


Nothing, unless you ask.

- **Save this view as a web page…** writes one self-contained HTML file. The 3D viewer
  travels inside the page, so it opens in any browser, needs no network, works
  when emailed to somebody, and will still work in five years.
- **Save the numbers as a table…** writes a CSV holding the volumes, both
  coverage directions with their margins, the grey cast, and the drift figures,
  with every row saying what it is and what the units are.

Your settings are remembered automatically and survive a restart — including
which explanations you left open. **Start again with the standard settings**
puts every one of them back, and never touches a file of yours.

---

## Where your settings and log live

Your settings are remembered automatically and survive a restart.
**Start again with standard settings** puts every one of them back, and never
touches a file of yours.

There is also a plain-text log, so a fault that happened once can still be
looked at afterwards:

| | |
|---|---|
| macOS | `~/Library/Logs/ChromIQ Gamut Viewer/gamut-viewer.log` |
| Windows | `%LOCALAPPDATA%\ChromIQ Gamut Viewer\logs\` |
| Linux | `$XDG_STATE_HOME/chromiq-gamut-viewer/` |

It never leaves your machine, and it cannot grow beyond **10 MB** — 2 MB a
file, five files kept. You can read or delete it whenever you like.

## Colour science, stated plainly

- **D50 by default**, the ICC connection-space illuminant and what print
  measurement uses. D65 is offered for display work. Lab is computed under
  whichever is chosen, and changing it rebuilds the charts *and* the comparison
  so the two are never in different spaces.
- **The shape follows the printer's real boundary**, not a skin thrown around
  it. A printer's gamut is genuinely dented — most visibly in the deep blues —
  and **Follow the real edge** keeps those dents by using the device values
  every measured chart stores alongside its results. The volume is the volume
  of that dented shape, so the number agrees with the picture instead of
  crediting your printer with colour it cannot print.
- **ΔE is CIEDE2000**, verified against the Sharma, Wu and Dalal (2005)
  reference pairs — the set published specifically to catch the hue-wrap and
  blue-rotation mistakes implementations make. Worst error 0.00004.
- **Coverage is measured by sampling**, 60,000 points with a fixed seed, so the
  same pair of gamuts always gives the same answer. The standard error is about
  0.2 percentage points, which is why nothing is quoted to more than one
  decimal place.
- **"Judge each paper against its own white"** normalises to the media white,
  which is what a relative-colorimetric profile does and what makes two papers
  of different brightness comparable on shape rather than brightness. Off by
  default, so what you see first is what the instrument actually reported.
- **sRGB output is only ever ink for the screen.** Painting a vertex its own
  colour means clipping everything outside sRGB, which is honest for drawing a
  picture and useless as a measurement. It is never treated as a colour value.

A full account of every setting, what it does, where it goes in the code and
why it was chosen is in [`docs/SETTINGS.md`](docs/SETTINGS.md).

---

## Running from source, and the tests

```bash
git clone https://github.com/itsab1989/ChromIQ-Gamut-Viewer.git
cd ChromIQ-Gamut-Viewer/python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python gamut_app.py                  # the window
python gamut_app.py mychart.ti3      # opening a chart straight away
```

There is also a command-line route that writes the HTML page directly, with no
window involved:

```bash
python ti3gamut.py mychart.ti3 -o gamut.html --open
python ti3gamut.py before.ti3 after.ti3      # two papers, one picture
```

The library underneath has no Qt in it and can be used on its own:

```python
from gamutview import build_gamut, coverage, shared_volume
from ti3gamut import read_measurement

m = read_measurement("mychart.ti3")
g = build_gamut(m.lab, m.device, input_space="lab")   # the dented boundary
print(f"{g.volume:,.0f} cubic Lab units from {m.n_patches} patches")
```

Tests:

```bash
cd python && python -m pytest . -q          # 68 tests
```

They check the colour science against published reference values rather than
against themselves — CIEDE2000 against the Sharma/Wu/Dalal pairs, CIELAB and
CIELUV against their definitions at three white points, mesh volumes against a
cube and a sphere whose answers are known from arithmetic.

---

## Releasing

**Every release says what changed.** That is a rule, and it is enforced rather
than remembered:

1. Add a `## vX.Y.Z` section to `CHANGELOG.md` saying what changed.
2. Set `__version__` in `python/version.py` to the same number.
3. Commit, then `git tag -a vX.Y.Z` and push the tag.

Pushing the tag builds all five platforms and publishes the release, with that
changelog section as the body of the page.

Two mistakes are refused rather than published:

* **A tag the changelog says nothing about.** The build stops in about fifteen
  seconds, before any platform is compiled, and names the versions that *do*
  have notes. Without this the release would go out carrying the previous
  version's words — a page that looks entirely normal and is wrong, which is
  the sort of thing nobody notices for months.
* **A tag that disagrees with `python/version.py`.** The in-app update check
  compares the version the application reports against the newest tag, so a
  bundle tagged v1.6.0 that reports 1.5.0 would offer people an update they
  already have, for ever.

To see what a release page will say before tagging:

```bash
python python/release_body.py v1.6.0
```

## Credits and licence

The gamut construction — and in particular the idea of following the device's
real boundary using the drive values, rather than wrapping a convex hull around
the measurements — is **Qiu Jueqin's**, from [Yet Another Color Gamut
Visualizer](https://github.com/QiuJueqin/Yet-Another-Color-Gamut-Visualizer).

The original MATLAB files (`gamutview.m`, `demo/`, `utils/`) are still in this
repository exactly as inherited, so the fork's provenance is visible and the
original remains runnable in MATLAB. The Python port lives in `python/`.

MIT licensed, as the original is. See [`LICENSE`](LICENSE), which is kept
exactly as inherited.

ICC profiles, `.gam` files and the non-`.ti3` measurement formats are read
using [ArgyllCMS](https://www.argyllcms.com/) when it is installed — its tools
are run as separate programs, never linked into this one.
