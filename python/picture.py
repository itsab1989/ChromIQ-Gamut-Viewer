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

#: Formats a moving picture can be written as.
#:
#: WEBP FIRST, AND NOT GIF. A GIF holds 256 colours. For a picture whose whole
#: subject is colour that is close to self-defeating -- every gradient bands
#: visibly. WebP carries the full range in a file several times smaller. GIF
#: stays for the places that still take nothing else.
MOVING_FORMATS = (
    ("webp", "WebP — full colour, small file", True),
    ("gif", "GIF — 256 colours only, for somewhere that takes nothing else", False),
    ("apng", "APNG — full colour, larger file", True),
)

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
    for name, _label, transparent in MOVING_FORMATS:
        if name == fmt:
            return transparent
    return False


def is_lossy(fmt: str) -> bool:
    """Whether a quality setting means anything for *fmt*."""
    return any(name == fmt and lossy for name, _l, _t, lossy in STILL_FORMATS)


def check_transparency(fmt: str, background: str) -> "str | None":
    """The reason a see-through background cannot be honoured, or None.

    Said at the moment it is chosen rather than written silently as black,
    which is what every other application seems to do.
    """
    if background != "transparent":
        return None
    if holds_transparency(fmt):
        return None
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
    per_pixel = {"png": 0.30, "webp": 0.05, "jpeg": 0.12, "svg": 0.20,
                 "gif": 0.12, "apng": 0.32}.get(fmt, 0.25)
    if fmt in ("webp", "jpeg"):
        per_pixel *= 0.4 + 0.6 * (max(1, min(100, quality)) / 100.0)
    if frames > 1:
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
        return (f"{width} × {height}, {frames} frames — about {size}. "
                "The picture is the size of the window it is taken from.")
    if fmt == "svg":
        return f"{width} × {height} — about {size}, and sharp at any size."
    return f"{width} × {height} — about {size}."


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
    return f"{safe_name(stem)}.{fmt}"


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
