"""Saving what is on screen as a picture — the decisions, without any Qt.

WHY THIS IS ITS OWN MODULE
--------------------------
Everything here is a rule rather than a widget: which sizes are offered and
what they are for, what a format can and cannot hold, how many frames make a
loop that closes, what the file should be called, and roughly how big it will
be. Rules are worth testing on their own, and none of them needs a window.

THREE EXPORTS, THREE QUESTIONS
------------------------------
The application already saves a **web page** (let somebody turn it themselves)
and a **table** (do arithmetic on the numbers). A picture answers the third
question: put it in a document, a slide, or a forum post. They are kept apart
deliberately -- each is the right answer to exactly one of those.

HOW EACH IS MADE, AND WHY THEY DIFFER
-------------------------------------
Measured, not assumed:

* a **still** is re-rendered by the viewer itself at whatever size is asked
  for, which takes about 0.7 s and can be a vector;
* a **moving picture** is grabbed from the view as it stands, which takes
  about 6 ms a frame -- a hundred times quicker. Re-rendering 144 frames would
  take a minute and a half, so it does not.

The trade is honest and worth stating: a still can be any size and razor
sharp; a moving picture is the size of the window it was taken from.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

#: What a picture is for, and how wide it should be for that. Named by the
#: job rather than by the number, because "2400 pixels" answers a question
#: nobody asked -- the pixels are shown beside each, for anybody who thinks in
#: them.
SIZES = (
    ("forum", "For a forum post or an email", 1600),
    ("document", "For a document", 2400),
    ("slide", "For a slide", 1920),
    ("print", "For printing", 3600),
    ("custom", "A size of my own", 0),
)

#: Every still format, with what it is good for and what it cannot do.
STILL_FORMATS = (
    ("png", "PNG — sharp, and can be see-through", True, False),
    ("webp", "WebP — the same, in a much smaller file", True, True),
    ("jpeg", "JPEG — smallest, but no see-through", False, True),
    ("svg", "SVG — scales to any size at all", True, False),
)

#: Formats a moving picture can be written as: key, label, whether it can be
#: see-through, the file extension, and the codec it needs an encoder for
#: (None for the three that need nothing installed).
#:
#: THE TWO FAMILIES ARE DIFFERENT ANIMALS, and the order says which to reach
#: for first. WebP, GIF and APNG are *pictures that move*: they drop into a
#: forum post, a README or a chat window exactly like a still, and need nothing
#: installed. MP4 and WebM are *films*: about half the size for the same
#: sharpness (measured, not reasoned about), with a play button, and they need
#: an encoder.
#:
#: WEBP BEFORE GIF, ALWAYS. A GIF holds 256 colours. For a picture whose whole
#: subject is colour that is close to self-defeating -- every gradient bands
#: visibly. WebP carries the full range in a file several times smaller. GIF
#: stays for the places that still take nothing else.
MOVING_FORMATS = (
    ("webp", "WebP — full colour, and it drops in like a picture", True,
     "webp", None),
    ("gif", "GIF — 256 colours only, for somewhere that takes nothing else",
     True, "gif", None),
    ("apng", "APNG — full colour and lossless, much larger file", True,
     "png", None),
    ("h264", "MP4 (H.264) — a film: sharpest for the size, plays everywhere",
     False, "mp4", "h264"),
    ("hevc", "MP4 (H.265) — the same again in about half the file",
     False, "mp4", "hevc"),
    ("vp9", "WebM (VP9) — a film that can be see-through, for a web page",
     True, "webm", "vp9"),
)

#: The formats that are films rather than pictures, and the codec each needs.
MOVING_CODECS = {key: codec for key, _l, _t, _e, codec in MOVING_FORMATS
                 if codec}


def extension_for(fmt: str) -> str:
    """The file extension for a format, which is not always its name.

    An APNG is a PNG, and both films live in a container named after neither
    the codec nor the choice: H.264 and H.265 go in an ``.mp4`` and VP9 in a
    ``.webm``. Getting this from one place is what stops a file being called
    ``.h264`` and refusing to open anywhere.
    """
    for key, _label, _transparent, extension, _codec in MOVING_FORMATS:
        if key == fmt:
            return extension
    return fmt


def codec_for(fmt: str) -> "str | None":
    """Which codec a format needs an encoder for, or None when it needs none."""
    return MOVING_CODECS.get(fmt)


def is_moving(fmt: str) -> bool:
    """Whether *fmt* is one of the moving kinds at all."""
    return any(key == fmt for key, *_rest in MOVING_FORMATS)


def is_film(fmt: str) -> bool:
    """Whether *fmt* is a film — which is what needs an encoder installed."""
    return fmt in MOVING_CODECS

#: Backgrounds worth offering, beyond a colour of one's own.
BACKGROUNDS = (
    ("as-shown", "As it looks on screen"),
    ("white", "White"),
    ("black", "Black"),
    ("transparent", "See-through"),
    ("custom", "A colour of my own"),
)

MIN_WIDTH, MAX_WIDTH = 200, 8000


def holds_transparency(fmt: str) -> bool:
    """Whether *fmt* can carry a see-through background at all."""
    for name, _label, transparent, _lossy in STILL_FORMATS:
        if name == fmt:
            return transparent
    for name, _label, transparent, _ext, _codec in MOVING_FORMATS:
        if name == fmt:
            return transparent
    return False


def is_lossy(fmt: str) -> bool:
    """Whether a quality setting means anything for *fmt*.

    It does for the films as well as for the lossy stills: there the number
    becomes a constant rate factor rather than a JPEG quality, but it answers
    exactly the same question, so it is the same slider.
    """
    if any(name == fmt and lossy for name, _l, _t, lossy in STILL_FORMATS):
        return True
    return is_film(fmt) or fmt == "webp"


def check_transparency(fmt: str, background: str) -> "str | None":
    """The reason a see-through background cannot be honoured, or None.

    Said at the moment it is chosen rather than written silently as black,
    which is what every other application seems to do.
    """
    if background != "transparent":
        return None
    if holds_transparency(fmt):
        return None
    if is_film(fmt):
        # A FILM IS ALMOST NEVER SEE-THROUGH, and the one that can be is worth
        # naming rather than leaving somebody to find.
        return ("An MP4 cannot hold a see-through background — every pixel in "
                "a film of that kind is solid, which is why one always arrives "
                "on a black or white ground.\n\n"
                "Two ways round it. WebM (VP9) is a film that can be "
                "see-through, and it plays on a web page and in most modern "
                "browsers. Or choose WebP, which is a moving picture rather "
                "than a film and drops into a document, a forum post or a chat "
                "window exactly like a still.\n\n"
                "Otherwise pick a colour, and it will be exactly that colour "
                "rather than a surprise.")
    return (f"A {fmt.upper()} file cannot hold a see-through background — "
            "every pixel in one is solid. Choose PNG or WebP for that, or "
            "pick a colour instead.")


def clamp_width(width) -> int:
    """A width that can actually be drawn, whatever was typed."""
    try:
        width = int(round(float(width)))
    except (TypeError, ValueError):
        return 2400
    return max(MIN_WIDTH, min(MAX_WIDTH, width))


def frames_for(seconds: float, per_second: int, mode: str) -> int:
    """How many frames a loop needs so that it CLOSES.

    A swing already returns to where it began. A full turn does not unless the
    frames divide 360 exactly -- otherwise the last frame sits a little short
    of the first and the loop visibly jumps every time round, which is the
    difference between a picture somebody watches and one they notice.
    """
    count = int(round(max(0.5, float(seconds)) * max(1, int(per_second))))
    count = max(2, min(600, count))
    if mode == "round":
        # Any count divides a circle evenly, but the LAST frame must not
        # repeat the first: 360/count is the step, and count steps close it.
        return count
    # A swing is sampled over a whole there-and-back, so an even count keeps
    # the two ends symmetrical.
    return count + (count % 2)


def turn_angles(count: int, mode: str, sweep: float) -> list:
    """The rotation of each frame, in degrees from where it started.

    Absolute positions rather than "a bit more each time": stepping by a
    rounded amount accumulates error over a hundred frames and the loop drifts
    open. These close by construction.
    """
    count = max(2, int(count))
    if mode == "round":
        return [i * 360.0 / count for i in range(count)]
    half = float(sweep) / 2.0
    # One full there-and-back of a sine, so the first and last frames meet.
    return [half * math.sin(2 * math.pi * i / count) for i in range(count)]


def estimate_bytes(width: int, height: int, fmt: str, frames: int = 1,
                   quality: int = 90) -> int:
    """Roughly how large the file will be, for saying so before making it.

    Measured against real exports of this application's own pictures rather
    than guessed from a formula: a gamut is a large area of smooth colour on a
    plain ground, which compresses far better than a photograph, and a
    photograph's rule of thumb would overstate it several times over.
    """
    pixels = max(1, int(width)) * max(1, int(height))
    # THE MOVING FIGURES ARE MEASURED, NOT REASONED ABOUT. Taken from real
    # exports of this application's own view — 72 frames of 900 x 768 at
    # quality 92 — because a first attempt at working them out from what each
    # format does was wrong by two to three times in both directions. A film
    # does not store each frame, only what changed, and a shape turning slowly
    # changes very little; but the WebP beside it is doing the same thing, so
    # the gap is about two, not the twenty that reasoning suggested.
    per_pixel = {"png": 0.30, "webp": 0.081, "jpeg": 0.12, "svg": 0.20,
                 "gif": 0.106, "apng": 0.41,
                 "h264": 0.0141, "hevc": 0.0109, "vp9": 0.0104}.get(fmt, 0.25)
    if fmt in ("webp", "jpeg"):
        per_pixel *= 0.4 + 0.6 * (max(1, min(100, quality)) / 100.0)
    if frames > 1:
        if is_film(fmt):
            # Every frame after the first is cheap, and the first is not much
            # dearer than the rest, so this is very nearly a straight line.
            per_pixel *= 0.5 + 0.5 * (max(1, min(100, quality)) / 100.0)
            return int(pixels * per_pixel * frames)
        # Frame after frame differs only where the shape moved, so every one
        # after the first costs a fraction of a whole picture.
        return int(pixels * per_pixel * (1 + 0.35 * (frames - 1)))
    return int(pixels * per_pixel)


def human_size(count: int) -> str:
    if count < 1024:
        return f"{count} bytes"
    if count < 1024 * 1024:
        return f"{count / 1024:.0f} kB"
    return f"{count / (1024 * 1024):.1f} MB"


def describe(width: int, height: int, fmt: str, frames: int = 1,
             quality: int = 90) -> str:
    """The one line shown under the button, so nobody is surprised."""
    size = human_size(estimate_bytes(width, height, fmt, frames, quality))
    if frames > 1:
        seconds = f"{frames} frames"
        if is_film(fmt):
            return (f"{width} × {height}, {seconds} — about {size}. "
                    "A film of the window as it stands, so it comes out no "
                    "larger than the window is.")
        return (f"{width} × {height}, {seconds} — about {size}. "
                "The picture is the size of the window it is taken from.")
    if fmt == "svg":
        return f"{width} × {height} — about {size}, and sharp at any size."
    return f"{width} × {height} — about {size}."


#: What the lettering and the grid lines can be set to.
#:
#: "Follow the background" is first and is what almost everybody wants: the
#: numbers round the box are the one part of the picture that has to stay
#: readable, and whether they should be dark or light is decided entirely by
#: what is behind them. Saving on white with the dark theme's pale grey
#: lettering gives a picture whose scale cannot be read at all -- and nothing
#: about it looks broken, which is why it goes unnoticed.
INK_CHOICES = (
    ("follow", "Follow the background"),
    ("dark", "Dark"),
    ("light", "Light"),
    ("custom", "A colour of my own"),
)

#: Lettering that is readable rather than absolute black or white. Pure black
#: on pure white is harsher than anything else in this application, and the
#: two here are the same pair the window itself uses.
DARK_INK, LIGHT_INK = "#22211f", "#e6e6e6"

#: How far the grid lines are pulled from the background towards the
#: lettering. THE CAGE IS NOT THE TEXT: at full contrast the lines converge at
#: the rims into a dark mass that shouts down the shape they are only there to
#: frame. About a fifth of the way is a box you can read a position off and
#: still see past.
GRID_STRENGTH = 0.22


#: Ready-made combinations of background, walls, lettering and grid lines.
#:
#: WHY THESE EXIST. Six controls that all affect one another is four too many
#: to get right by trial: a white background needs dark lettering, a see-through
#: one needs lettering chosen for a page nobody here can see, and walls that
#: look right on a slide are wrong in a document. Each of these is one answer
#: that works, arrived at by looking at the result rather than by reasoning
#: about the settings — and every one of them can still be adjusted afterwards,
#: which simply moves the chooser to "My own settings".
#:
#: The names say where the picture is GOING, because that is the question
#: somebody actually has. "Transparent PNG with light glyphs" is not.
#: The window's own two schemes, written out as looks.
#:
#: THESE ARE NOT COPIES OF THE THEME — THEY ARE THE THEME. The same figures
#: the window itself paints with (ti3gamut.SCENE_COLOURS), so choosing "The
#: window's own dark" gives back exactly what the application looks like with
#: nothing else set. That matters for two reasons: somebody who has wandered
#: off into their own colours can always get back, and anybody building a look
#: of their own has the real one to start from rather than an approximation.
DARK_THEME = {"background": "custom", "colour": "#111111",
              "walls": "custom", "wall_colour": "#141414",
              "lettering": "custom", "lettering_colour": "#e6e6e6",
              "gridlines": "custom", "gridlines_colour": "#262626"}
LIGHT_THEME = {"background": "custom", "colour": "#efebe6",
               "walls": "custom", "wall_colour": "#f7f4ef",
               "lettering": "custom", "lettering_colour": "#22211f",
               "gridlines": "custom", "gridlines_colour": "#e0ddd7"}

LOOKS = (
    ("screen", "As it looks on screen",
     "Exactly what is in the window now, nothing changed.", {}),
    ("theme-dark", "The window's own dark",
     "The colours this application uses in dark mode, exactly.", DARK_THEME),
    ("theme-light", "The window's own light",
     "The colours this application uses in light mode, exactly.", LIGHT_THEME),
    ("document", "For a white document",
     "White behind and around it, dark lettering. The safe answer for "
     "anything going into a report, a letter or a printed page.",
     {"background": "white", "walls": "white",
      "lettering": "follow", "gridlines": "follow"}),
    ("report", "For a printed report, soft box",
     "White page with the box a shade of grey, so the shape sits in "
     "something rather than floating. Dark lettering.",
     {"background": "white", "walls": "custom", "wall_colour": "#f2efe9",
      "lettering": "follow", "gridlines": "follow"}),
    ("slide", "For a dark slide",
     "Black behind it and light lettering, for a presentation on a dark "
     "background.",
     {"background": "black", "walls": "custom", "wall_colour": "#111111",
      "lettering": "follow", "gridlines": "follow"}),
    ("cutout-light", "Cut out — for a light page",
     "Nothing behind the shape at all, and dark lettering, so it drops "
     "straight onto a white or pale page and takes that as its own "
     "background.",
     {"background": "transparent", "walls": "transparent",
      "lettering": "dark", "gridlines": "dark"}),
    ("cutout-dark", "Cut out — for a dark page",
     "The same, with light lettering, for dropping onto a dark page or a "
     "dark slide.",
     {"background": "transparent", "walls": "transparent",
      "lettering": "light", "gridlines": "light"}),
    ("custom", "My own settings",
     "Whatever you set below. This is chosen for you as soon as you change "
     "any of them.", None),
)


def look(key: str):
    """The settings behind one look, or None for "my own"."""
    for name, _label, _why, values in LOOKS:
        if name == key:
            return values
    return None


def look_because(key: str) -> str:
    """The sentence under the chooser saying what this look is for."""
    for name, _label, why, _values in LOOKS:
        if name == key:
            return why
    return ""


def _channels(colour: str):
    """The three numbers behind a #rrggbb, or None if it is not one."""
    text = str(colour).strip()
    if text.startswith("rgba") or text.startswith("rgb"):
        try:
            parts = text[text.index("(") + 1:text.index(")")].split(",")
            return tuple(float(p) / 255.0 for p in parts[:3])
        except (ValueError, IndexError):
            return None
    if not text.startswith("#"):
        return None
    text = text[1:]
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None


def relative_luminance(colour: str) -> float:
    """How bright a colour looks, on the scale everybody measures contrast on.

    The standard weighting rather than a plain average: the eye is far more
    sensitive to green than to blue, so a plain average calls a saturated blue
    much lighter than it looks and would put dark lettering on it.
    """
    got = _channels(colour)
    if got is None:
        return 0.0
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
              for c in got]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(one: str, other: str) -> float:
    """How far apart two colours are to read, from 1 (invisible) to 21."""
    a, b = relative_luminance(one), relative_luminance(other)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def ink_for(background: str) -> str:
    """Lettering that can be read on *background*, chosen by measuring it."""
    return DARK_INK if relative_luminance(background) > 0.18 else LIGHT_INK


def mix(background: str, towards: str, amount: float) -> str:
    """*amount* of the way from one colour to another, as #rrggbb."""
    start, end = _channels(background), _channels(towards)
    if start is None or end is None:
        return towards
    amount = max(0.0, min(1.0, float(amount)))
    blended = [s + (e - s) * amount for s, e in zip(start, end)]
    return "#" + "".join(f"{int(round(c * 255)):02x}" for c in blended)


def grid_for(background: str, strength: float = GRID_STRENGTH) -> str:
    """Grid lines that frame the shape without competing with it."""
    return mix(background, ink_for(background), strength)


def alpha_from_two_grounds(on_white, on_black):
    """Recover a see-through picture from the same view drawn twice.

    WHY THIS EXISTS. A still picture is re-drawn by the viewer, which can hand
    back a see-through one directly. A moving picture is copied from the screen
    a frame at a time, and a copy of the screen has no see-through in it: the
    graphics card has already mixed everything onto a solid ground, and the
    copy arrives with every pixel fully opaque however politely the page was
    asked. Choosing "see-through" therefore used to give back a solid picture
    in whatever colour happened to be behind it -- quietly, which is the worst
    way to be wrong.

    THE WAY OUT IS ARITHMETIC, and it is exact rather than a trick. Draw the
    same frame twice, once on white and once on black. Wherever the shape is
    solid, the two copies agree. Wherever nothing is drawn, one is white and
    the other is black. And along an edge, where the shape is half there, the
    two differ by exactly how much of the ground shows through. For one channel

        on_white = colour x alpha + 1 x (1 - alpha)
        on_black = colour x alpha + 0 x (1 - alpha)

    so subtracting gives ``1 - alpha`` straight away, and the colour follows.
    No guessing at a background to remove, no fringe of the wrong colour along
    the edges, and anti-aliasing and semi-transparent surfaces both come out
    right.

    It costs a second copy of every frame, so it is done only when see-through
    is actually asked for.

    Both arguments are height x width x 3 arrays of 0..255. Returns height x
    width x 4, ready to be a picture.
    """
    import numpy as np

    white = np.asarray(on_white, dtype=np.float32)[..., :3] / 255.0
    black = np.asarray(on_black, dtype=np.float32)[..., :3] / 255.0
    # The ground shows through by the same amount in all three channels, so
    # averaging them is what makes this steady rather than noisy.
    clear = np.clip((white - black).mean(axis=2), 0.0, 1.0)
    alpha = 1.0 - clear
    # Where almost nothing is there, the colour cannot be recovered and does
    # not matter -- but dividing by it would turn rounding into confetti.
    safe = np.maximum(alpha, 1e-3)[..., None]
    colour = np.clip(black / safe, 0.0, 1.0)
    colour = np.where(alpha[..., None] < 4e-3, 0.0, colour)
    out = np.empty(white.shape[:2] + (4,), dtype=np.uint8)
    out[..., :3] = np.round(colour * 255.0).astype(np.uint8)
    out[..., 3] = np.round(alpha * 255.0).astype(np.uint8)
    return out


_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(text: str) -> str:
    """A file name that every system will accept, from anything at all."""
    cleaned = _UNSAFE.sub("-", str(text)).strip(" .")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:80] or "gamut"


def suggest_name(shapes, fmt: str, *, slicing: bool = False,
                 lightness: float = 50.0, moving: bool = False) -> str:
    """What to call the file, from what is actually in the picture.

    A name saying which papers, and at which lightness, is what stops a folder
    of exports becoming a folder of "gamut-1" through "gamut-9".
    """
    names = [safe_name(s) for s in shapes if str(s).strip()]
    if not names:
        stem = "gamut"
    elif len(names) == 1:
        stem = names[0]
    else:
        stem = f"{names[0]}-vs-{names[1]}"
    if slicing:
        stem += f"-L{lightness:.0f}"
    if moving:
        stem += "-turning"
    return f"{safe_name(stem)}.{extension_for(fmt)}"


def next_free(path) -> Path:
    """A name that is not in use, so nothing of anybody's is overwritten.

    Never replaces a file. The rule everywhere else in this application is
    that nothing of the user's is destroyed, and a picture they exported an
    hour ago is theirs.
    """
    path = Path(path)
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for n in range(2, 1000):
        candidate = path.with_name(f"{stem}-{n}{suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError(f"there are already a thousand files called {stem}")
