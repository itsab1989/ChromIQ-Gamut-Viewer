See the gamut your printer **actually measured** — not the one its profile claims.

Open the `.ti3` file ArgyllCMS writes when you read a printed chart, and this
shows the gamut those patches enclose: in 3D, painted in its own colours, with
its volume in the same cubic Lab units ArgyllCMS reports. Open a second chart
and both are drawn together, with the difference stated in per cent.

**Why it is not the same as a profile's gamut.** The usual way to look at a
gamut is to ask the finished ICC profile. A profile is a fitted model of your
printer: it smooths, it interpolates, and near the edges it can promise a little
more or a little less than the paper really gave. This asks the measurements
instead — every vertex is a patch that was printed and read.

**The shape follows your printer's real boundary.** A printer's gamut is dented,
especially in the deep blues. Given the device values alongside the
measurements — which a `.ti3` already contains — the surface keeps those dents
instead of throwing a convex hull over them and claiming more colour than you
have. You can switch between the two and see the difference.

### What you can find out

| Question | What you get |
|---|---|
| What can this paper print? | The shape, its volume, and how dark the blacks reach against the paper white |
| Will an image survive on it? | Coverage against sRGB, Adobe RGB, Display P3, ProPhoto RGB, Rec. 2020 or any ICC profile — **in both directions**, because they answer different questions |
| *Where* does it fall short? | The regions the comparison cannot reproduce, picked out in red on the shape itself |
| Which of two papers? | How much they share, and which one reaches further in each hue family |
| Has my printer drifted? | Two readings compared patch by patch in ΔE2000, naming the patches that moved most |
| Does my profile match reality? | The measured gamut against the gamut of the profile built from it |
| Are my greys grey? | The neutral axis drawn through the solid, with every grey's colour cast |

Also: a cross-section at any lightness for reading two shapes against each
other, contour rings inside the cage, CIELAB / CIELUV / CIE XYZ to draw in,
light and dark appearance, five accent colours, per-shape styling so each
gamut can be shown its own way, and every setting remembered between sessions.

Anything that might be jargon has a plain-language entry under **What do these
words mean?**

### It opens more than `.ti3`

`.cxf`, `.mxf` and `.txt` measurements are converted with ArgyllCMS's own
`cxf2ti3` / `txt2ti3`; `.icc`, `.icm` and `.gam` are read as comparisons, ICC
profiles through ArgyllCMS `iccgamut`. Converted copies go to a temporary
folder, never beside your original.

### Which file to download

| Your computer | File |
|---|---|
| Mac with Apple silicon (M1 and later) | `GamutViewer-macOS-arm64.zip` |
| Intel Mac | `GamutViewer-macOS-x86_64.zip` |
| Windows | `GamutViewer-Windows-x64.zip` |
| Linux | `GamutViewer-Linux-x86_64.tar.gz` |
| Linux on ARM (Raspberry Pi and similar) | `GamutViewer-Linux-aarch64.tar.gz` |

Unpack it and run it. Nothing is uploaded anywhere and no network is used.

On macOS the first launch needs **right-click ▸ Open** rather than a double
click, because the app is not signed with an Apple developer certificate.

### If you would rather have just the picture

The repository also carries a command-line version that needs neither Qt nor a
web engine and writes one self-contained HTML file you can open in any browser
or send to somebody:

```bash
pip install -r python/requirements-cli.txt
python python/ti3gamut.py yourchart.ti3 --open
```

Built on the MIT-licensed [Yet Another Color Gamut
Visualizer](https://github.com/QiuJueqin/Yet-Another-Color-Gamut-Visualizer) by
Qiu Jueqin, ported to Python and extended.

---

<p align="center">
  <a href="https://ko-fi.com/itsab1989"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support this on Ko-fi" height="36"></a>
  <br>
  <sub>The ChromIQ Gamut Viewer is free and always will be. If it's useful to you, a coffee is a kind way to say thanks — completely optional, and it stays fully featured either way.</sub>
</p>
