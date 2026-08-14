# What travels with the ChromIQ Gamut Viewer, and under what terms

The viewer itself is under the **MIT licence** — the file `LICENSE` in this
repository. A downloaded release also carries several other people's work, and
this page says what, why, and on what terms, because a few of them are not MIT
and pretending otherwise would be wrong.

## The short version

| What | Why it is here | Its licence |
|---|---|---|
| PyQt6 and Qt | the window, and the browser engine that draws the shape | GPL v3 / commercial (Riverbank), LGPL v3 (Qt) |
| Plotly | draws the shape itself | MIT |
| NumPy, SciPy | the arithmetic, and the hull that makes a surface from points | BSD |
| Pillow | reads pictures, writes the WebP, GIF and APNG loops | MIT-CMU |
| pillow-heif, pillow-jxl-plugin | HEIC and JPEG XL pictures | LGPL v3 / BSD |
| **ffmpeg** | **writes the MP4 and WebM films** | **GPL v2 or later** |

## ffmpeg, in detail

Saving the turning view as an **MP4 (H.264 or H.265)** or a **WebM (VP9)** is
done by [ffmpeg](https://ffmpeg.org/). A ready-made build travels with the
released application — through the
[`imageio-ffmpeg`](https://github.com/imageio/imageio-ffmpeg) package — so the
films work with nothing installed.

**It is run as a separate program.** The viewer starts it, hands it the frames
down a pipe, and reads back what it says. It is never linked into this
application and no part of ffmpeg is compiled into it. That is the same
arrangement ChromIQ uses for ArgyllCMS, and it is deliberate: the two programs
stay under their own licences rather than one reaching into the other.

**The build that ships is under the GPL.** It is compiled with `libx264` and
`libx265`, which are GPL v2-or-later, so the ffmpeg binary as distributed is
GPL v2-or-later. Distributing it carries obligations, and they are met like
this:

* the licence text travels with it, in the `imageio_ffmpeg` folder of the
  application;
* the corresponding source is FFmpeg's own, published at
  <https://github.com/FFmpeg/FFmpeg>, and the exact build recipe is
  imageio-ffmpeg's, published at
  <https://github.com/imageio/imageio-ffmpeg/tree/master/tools>;
* nothing about that binary has been modified.

**Nothing forces you to use it.** *Where ffmpeg is…* in the left-hand column
points the viewer at any ffmpeg you already have, and `CHROMIQ_FFMPEG` does the
same from the environment. Delete the bundled one and the application still
opens every file, saves every still picture, and makes WebP, GIF and APNG
moving pictures — only MP4 and WebM go grey.

### Patents

H.264 and H.265 are covered by patent pools in some countries. The same is true
of every application that plays or writes them. Anyone redistributing this
software commercially, or in a jurisdiction where that matters to them, should
take their own advice — or build without those two formats, which costs nothing
but the MP4 option. **WebM (VP9)** is royalty-free and is offered here partly
for that reason.

## Running from the source

`pip install -r python/requirements.txt` brings all of the above. Leaving
`imageio-ffmpeg` out is a supported way to run: `movie.py` imports it inside a
`try`, and the application says plainly that films cannot be made rather than
failing at the moment somebody asks for one.
