"""Writing a moving picture as a film — finding the encoder, and driving it.

WHY A SEPARATE PROGRAM RATHER THAN A LIBRARY
--------------------------------------------
MP4 and WebM are made by **ffmpeg**, run as a separate program with the frames
handed to it down a pipe. That is the same arrangement ChromIQ uses for
ArgyllCMS, and it is deliberate on three counts:

* **It keeps the licences apart.** The ffmpeg builds that can write H.264 and
  H.265 are under the GPL; this application is under the MIT licence. Calling a
  separate program leaves each under its own terms, where linking a library
  into this one would not.
* **The window stays alive.** Frames go out as they are taken, so the encoding
  happens *while* the picture is being grabbed rather than in one long silent
  step at the end. That step was the one thing here that could still stop the
  window answering.
* **Memory stays flat.** Holding a six-second loop at full size as pictures in
  memory costs several hundred megabytes; sending each frame as it arrives
  costs the eight frames the pipe is allowed to get ahead by.

WHERE THE ENCODER COMES FROM
----------------------------
In this order, and the first one found wins:

1. a path the person chose in the window, or ``CHROMIQ_FFMPEG``;
2. the copy that ships with this application (the ``imageio-ffmpeg`` package),
   so a downloaded release can write films with nothing installed;
3. ``ffmpeg`` on the PATH -- somebody who keeps their own build gets theirs;
4. the usual places on each platform, for an installation that is not on the
   PATH.

WHAT A BUILD CAN ACTUALLY DO IS ASKED, NOT ASSUMED
--------------------------------------------------
Not every ffmpeg can write every format: some Linux distributions ship one
without H.265, and a build without ``libx264`` cannot write an ordinary MP4 at
all. So the encoders are read out of the program itself and only the formats it
can really write are offered. The alternative -- offering all of them and
failing at the end of a two-minute export -- is the sort of thing this
application exists not to do.

QUALITY, AND WHAT THE NUMBER MEANS
----------------------------------
The Quality slider is 40 to 100 everywhere in this application, so it means the
same thing whatever is being saved. For a film it is turned into a *constant
rate factor*, which is how these encoders are asked for a quality rather than a
file size: lower is better, and every codec has its own scale, so the same 90
means the same picture whichever is chosen.
"""
from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

#: Point this at an ffmpeg program to override the search entirely.
ENV_OVERRIDE = "CHROMIQ_FFMPEG"

#: Where to get one. Free, and every platform has a build.
DOWNLOAD_URL = "https://ffmpeg.org/download.html"

#: A path the person chose by hand. Set by the window from its saved settings;
#: kept here as a plain string so this module needs nothing from Qt.
EXTRA_PATH: "str | None" = None

#: How long to wait for the program to say what it is, and what it can do.
ASK_TIMEOUT = 20

#: How far the frames are allowed to get ahead of the encoder. Eight frames of
#: a large picture is about thirty megabytes -- enough that a momentary pause
#: in the encoder never stalls the window, small enough that memory stays flat
#: however long the loop is.
QUEUE_DEPTH = 8

#: Every codec offered, and which encoders can write it, best first.
#:
#: The software encoders come first on purpose. A hardware one is quicker, but
#: it is tuned for filming the real world and gives noticeably softer edges on
#: a picture like this -- which is all sharp lines and flat colour. They are
#: kept as a fallback for a build that has nothing else, because a slightly
#: soft film is a great deal better than no film.
ENCODERS = {
    "h264": ("libx264", "h264_videotoolbox", "h264_nvenc", "h264_amf",
             "h264_qsv"),
    "hevc": ("libx265", "hevc_videotoolbox", "hevc_nvenc", "libkvazaar"),
    "vp9": ("libvpx-vp9", "vp9"),
}

#: What each codec is called where somebody might have to look it up.
CODEC_NAMES = {"h264": "H.264", "hevc": "H.265", "vp9": "VP9"}


class NoEncoder(Exception):
    """No program that could write this, said in words worth reading."""


class EncodingFailed(Exception):
    """The encoder refused, and this carries what it said about it."""


def set_path(path: "str | None") -> None:
    """Use *path* before looking anywhere else. Empty clears it."""
    global EXTRA_PATH
    EXTRA_PATH = str(path) if path else None
    forget()


_cache: dict = {}


def forget() -> None:
    """Search again next time -- for a test, or after somebody installs one."""
    _cache.clear()


def _bundled() -> "str | None":
    """The copy that travels with this application, if it is there.

    Optional on purpose: running from the source with nothing extra installed
    still opens every file and still writes WebP, GIF and APNG. Only the films
    need this.
    """
    try:
        import imageio_ffmpeg
        found = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                                    # noqa: BLE001
        return None
    return found if found and Path(found).is_file() else None


def _candidates():
    """Every ffmpeg worth trying, most likely first."""
    if EXTRA_PATH:
        yield EXTRA_PATH
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        yield override
    bundled = _bundled()
    if bundled:
        yield bundled
    on_path = shutil.which("ffmpeg")
    if on_path:
        yield on_path
    if os.name == "nt":
        home = Path.home()
        roots = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
                 Path(os.environ.get("ProgramFiles(x86)",
                                     r"C:\Program Files (x86)")),
                 Path(os.environ.get("LOCALAPPDATA", str(home))),
                 Path("C:/")]
        for root in roots:
            try:
                for found in sorted(root.glob("ffmpeg*"), reverse=True):
                    if found.is_dir():
                        yield str(found / "bin" / "ffmpeg.exe")
                        yield str(found / "ffmpeg.exe")
            except OSError:
                continue
    else:
        for fixed in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg",
                      "/usr/bin/ffmpeg", "/opt/local/bin/ffmpeg",
                      "/snap/bin/ffmpeg", "/var/lib/flatpak/exports/bin/ffmpeg"):
            yield fixed


def _quiet_run(command, timeout=ASK_TIMEOUT):
    """Run something and hand back its output, without ever opening a window.

    On Windows a subprocess started from a windowed application flashes a
    console up for as long as it runs. Asking ffmpeg what it can do would
    therefore blink a black box at somebody opening the save dialog.
    """
    extra = {}
    if os.name == "nt":
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(command, capture_output=True, text=True,
                          timeout=timeout, **extra)


def looks_like_ffmpeg(path) -> bool:
    """Whether *path* really is an ffmpeg, so a wrong pick is refused now.

    Refused at the moment it is chosen rather than at the end of a long export,
    which is the difference between a sentence and a wasted afternoon.
    """
    try:
        done = _quiet_run([str(path), "-version"])
    except Exception:                                    # noqa: BLE001
        return False
    return "ffmpeg version" in ((done.stdout or "") + (done.stderr or "")).lower()


def find_ffmpeg() -> "str | None":
    """The encoder this machine will use, or None if there is not one."""
    if "exe" in _cache:
        return _cache["exe"]
    found = None
    for candidate in _candidates():
        try:
            if not candidate or not Path(candidate).is_file():
                continue
        except OSError:
            continue
        if looks_like_ffmpeg(candidate):
            found = str(candidate)
            break
    _cache["exe"] = found
    return found


def _read_encoders(exe: str) -> set:
    """Every video encoder this build carries, read out of the program."""
    try:
        done = _quiet_run([exe, "-hide_banner", "-encoders"])
    except Exception:                                    # noqa: BLE001
        return set()
    names = set()
    for line in (done.stdout or "").splitlines():
        # " V....D libx264              libx264 H.264 / AVC ..."
        found = re.match(r"\s*[VAS][\.A-Z]{5}\s+(\S+)", line)
        if found:
            names.add(found.group(1))
    return names


def encoders() -> set:
    """The encoder names available, cached because asking costs a moment."""
    if "names" in _cache:
        return _cache["names"]
    exe = find_ffmpeg()
    names = _read_encoders(exe) if exe else set()
    _cache["names"] = names
    return names


def encoder_for(codec: str) -> "str | None":
    """The best encoder on this machine for *codec*, or None if there is none."""
    have = encoders()
    for name in ENCODERS.get(codec, ()):
        if name in have:
            return name
    return None


def can_write(codec: str) -> bool:
    """Whether a film in *codec* can be made here at all."""
    return encoder_for(codec) is not None


def why_not(codec: str) -> "str | None":
    """Why this format is not on offer, in words, or None when it is.

    Two quite different reasons, and telling them apart matters: no encoder at
    all is something to install, while an encoder that simply lacks one format
    is something to work around by choosing another.
    """
    if can_write(codec):
        return None
    pretty = CODEC_NAMES.get(codec, codec.upper())
    if find_ffmpeg() is None:
        return (f"A film needs ffmpeg, and there is not one on this computer. "
                f"It is free, every platform has a build, and this application "
                f"only ever runs it -- nothing is sent anywhere. Use "
                f"“Where ffmpeg is…” in the left-hand column to point at one "
                f"you already have, or fetch one from {DOWNLOAD_URL}.\n\n"
                f"Meanwhile WebP makes an excellent moving picture and needs "
                f"nothing installed at all.")
    return (f"The ffmpeg on this computer was built without {pretty}, so it "
            f"cannot write that one. Everything else in the list still works. "
            f"A full build from {DOWNLOAD_URL} carries the lot.")


def status() -> dict:
    """Whether there is one, where, which version, and what it can write."""
    exe = find_ffmpeg()
    if exe is None:
        return {"found": False, "path": None, "version": None,
                "codecs": (), "bundled": False}
    if "version" in _cache:
        version = _cache["version"]
    else:
        version = None
        try:
            done = _quiet_run([exe, "-version"])
            first = ((done.stdout or "") + (done.stderr or "")).splitlines()
            if first:
                found = re.search(r"ffmpeg version (\S+)", first[0])
                if found:
                    version = found.group(1)
        except Exception:                                # noqa: BLE001
            pass
        _cache["version"] = version
    bundled = _bundled()
    return {"found": True, "path": exe, "version": version,
            "codecs": tuple(c for c in ENCODERS if can_write(c)),
            "bundled": bool(bundled and os.path.realpath(bundled)
                            == os.path.realpath(exe))}


def summary() -> str:
    """One line for the window, saying what somebody actually wants to know."""
    got = status()
    if not got["found"]:
        return ("No ffmpeg found — MP4 and WebM films cannot be made. "
                "Everything else works, and WebP moving pictures need nothing.")
    kinds = ", ".join(CODEC_NAMES[c] for c in got["codecs"])
    which = f" {got['version'].split('-')[0]}" if got["version"] else ""
    where = " (the one that came with this application)" if got["bundled"] else ""
    if not kinds:
        return (f"ffmpeg{which} found{where}, but it was built without any of "
                "the formats used here — only WebP, GIF and APNG can be made.")
    return f"ffmpeg{which} found{where} — films can be made in {kinds}."


# --------------------------------------------------------------------------
# Turning the quality slider into what an encoder understands
# --------------------------------------------------------------------------

def crf_for(codec: str, quality: int) -> int:
    """The constant rate factor that means *quality* for this codec.

    Lower is better, and the scales differ: an H.265 file at 20 looks about
    like an H.264 one at 16, so the same slider position has to become a
    different number for each. The ends were chosen from what the picture
    actually is -- large flat areas of smooth colour with hard edges, which
    compresses far better than filmed footage, so these sit lower (better) than
    a video encoder's usual defaults.
    """
    quality = max(0, min(100, int(quality)))
    if codec == "hevc":
        # H.265 needs about four more than H.264 for the same picture.
        return int(round(38 - 0.20 * quality))           # 100 -> 18, 40 -> 30
    if codec == "vp9":
        # VP9's scale runs to 63 rather than 51 and sits higher again: around
        # eight above H.264 for a picture you cannot tell apart.
        return int(round(42 - 0.20 * quality))           # 100 -> 22, 40 -> 34
    return int(round(34 - 0.20 * quality))               # 100 -> 14, 40 -> 26


def bitrate_for(width: int, height: int, fps: int, quality: int) -> int:
    """Bits a second, for the hardware encoders that cannot take a quality.

    They are the fallback rather than the first choice, so this only has to be
    generous enough that the picture does not visibly suffer.
    """
    pixels = max(1, int(width)) * max(1, int(height))
    per_pixel = 0.06 + 0.14 * (max(0, min(100, quality)) / 100.0)
    return int(pixels * max(1, int(fps)) * per_pixel)


def even(size: int) -> int:
    """The nearest size an encoder will accept, never larger.

    H.264 and H.265 store colour at half resolution in each direction, so both
    sides must divide by two. One row is dropped rather than one added, because
    adding invents a row of pixels that was never drawn.
    """
    return max(2, int(size) // 2 * 2)


def command(exe: str, target, width: int, height: int, fps: int, codec: str,
            quality: int, *, transparent: bool = False,
            encoder: "str | None" = None) -> list:
    """The whole ffmpeg command line, built so it can be read in a test.

    Frames arrive as raw RGBA down the pipe -- no intermediate files, and the
    one format that carries a see-through background can use it directly.
    """
    encoder = encoder or encoder_for(codec)
    if encoder is None:
        raise NoEncoder(why_not(codec) or f"nothing here can write {codec}")
    width, height = even(width), even(height)
    args = [str(exe), "-hide_banner", "-nostdin", "-loglevel", "error",
            "-nostats", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{width}x{height}", "-r", str(int(fps)), "-i", "-",
            "-an", "-c:v", encoder]

    if encoder in ("libx264", "libx265"):
        args += ["-crf", str(crf_for(codec, quality)), "-preset", "slow"]
        # yuv420p, not something sharper: it is the only pixel format every
        # phone, browser and chat window will play. A file nobody can open is
        # not a better picture.
        args += ["-pix_fmt", "yuv420p"]
        if encoder == "libx265":
            # WITHOUT THIS TAG QUICKTIME WILL NOT OPEN IT. The file is a
            # perfectly good H.265 either way; Apple's players simply refuse
            # anything not marked hvc1, which looks exactly like a broken file.
            args += ["-tag:v", "hvc1", "-x265-params", "log-level=error"]
    elif encoder in ("libvpx-vp9", "vp9"):
        args += ["-crf", str(crf_for(codec, quality)), "-b:v", "0",
                 "-row-mt", "1", "-deadline", "good", "-cpu-used", "2"]
        # VP9 IS THE ONLY MOVING FORMAT THAT CAN BE SEE-THROUGH, and it needs
        # both the pixel format with an alpha channel and its look-ahead
        # turned off -- with it on, the transparency is dropped silently.
        args += (["-pix_fmt", "yuva420p", "-auto-alt-ref", "0"] if transparent
                 else ["-pix_fmt", "yuv420p"])
    else:
        args += ["-b:v", str(bitrate_for(width, height, fps, quality)),
                 "-pix_fmt", "yuv420p"]
        if encoder == "hevc_videotoolbox":
            args += ["-tag:v", "hvc1"]

    suffix = Path(str(target)).suffix.lower()
    if suffix == ".mp4":
        # Puts the index at the front, so the film starts playing as it
        # downloads rather than only once all of it has arrived.
        args += ["-movflags", "+faststart"]
    args.append(str(target))
    return args


# --------------------------------------------------------------------------
# The two ways a moving picture gets written
# --------------------------------------------------------------------------

class MovieWriter:
    """Frames in, a film out, with the encoding happening as they arrive.

    Handed one picture at a time and written straight down a pipe, so nothing
    is held except the few frames the encoder has not caught up with yet.
    """

    #: A film can be abandoned half way: the encoder is a separate program and
    #: can simply be stopped. Worth knowing, because the Stop button has to be
    #: honest about whether it will do anything.
    can_stop_while_writing = True

    def __init__(self, exe: str, target, width: int, height: int, fps: int,
                 codec: str, quality: int, *, transparent: bool = False) -> None:
        self.target = Path(target)
        self.width, self.height = even(width), even(height)
        self._expected = self.width * self.height * 4
        self._queue: queue.Queue = queue.Queue(maxsize=QUEUE_DEPTH)
        self._trouble: "BaseException | None" = None
        self._said: list = []
        self._frames = 0
        extra = {}
        if os.name == "nt":
            extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._command = command(exe, self.target, self.width, self.height, fps,
                                codec, quality, transparent=transparent)
        self._process = subprocess.Popen(
            self._command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, **extra)
        self._pump = threading.Thread(target=self._feed, daemon=True)
        self._pump.start()
        # DRAIN WHAT IT SAYS, ALWAYS. A program whose error pipe fills up stops
        # dead waiting for somebody to read it, and the export would hang with
        # no sign of why. This keeps the last few lines for the message.
        self._listen = threading.Thread(target=self._collect, daemon=True)
        self._listen.start()

    # -- the two background threads ----------------------------------------
    def _feed(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            try:
                self._process.stdin.write(item)
            except BaseException as exc:                  # noqa: BLE001
                self._trouble = exc
                break
        try:
            if self._process.stdin and not self._process.stdin.closed:
                self._process.stdin.close()
        except OSError:
            pass

    def _collect(self) -> None:
        stream = self._process.stderr
        if stream is None:
            return
        for line in stream:
            text = line.decode("utf-8", "replace").strip()
            if text:
                self._said.append(text)
                del self._said[:-12]

    # -- what the caller uses ----------------------------------------------
    def add(self, image) -> None:
        """One frame, as a Pillow image. Returns as soon as it is handed over.

        Cropped rather than scaled when it is a pixel or two over: the size was
        settled when the encoder was started and cannot change part way
        through, and a single row is not worth resampling the picture for.
        """
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        if image.width < self.width or image.height < self.height:
            # NOT CROPPED, AND NOT PADDED EITHER. Cropping past the edge fills
            # the difference with clear pixels, so a frame that is too small
            # would go in as the picture with a blank strip down one side --
            # a film that looks damaged rather than an error worth reading.
            raise EncodingFailed(
                f"a frame arrived {image.width}x{image.height} where the film "
                f"was started at {self.width}x{self.height}")
        if image.size != (self.width, self.height):
            image = image.crop((0, 0, self.width, self.height))
        raw = image.tobytes()
        if len(raw) != self._expected:                   # never silently wrong
            raise EncodingFailed(
                f"a frame arrived {len(raw)} bytes long where the film "
                f"expects {self._expected}")
        self._queue.put(raw)
        self._frames += 1
        if self._trouble is not None:
            raise EncodingFailed(self._message())

    def _message(self) -> str:
        said = "\n".join(self._said[-6:])
        return said or "the encoder stopped without saying why"

    def finish(self):
        """Close the pipe, wait for the film, and hand back where it is."""
        self._queue.put(None)
        self._pump.join()
        code = self._process.wait()
        self._listen.join(timeout=5)
        if code != 0:
            self.target.unlink(missing_ok=True)
            raise EncodingFailed(
                "The film could not be written. The encoder said:\n\n"
                + self._message())
        if not self.target.exists() or self.target.stat().st_size == 0:
            self.target.unlink(missing_ok=True)
            raise EncodingFailed("The encoder finished but wrote nothing.")
        return self.target

    def cancel(self) -> None:
        """Stop it and leave nothing behind — a half-written film is no use."""
        try:
            self._process.kill()
        except Exception:                                # noqa: BLE001
            pass
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        try:
            self._process.wait(timeout=5)
        except Exception:                                # noqa: BLE001
            pass
        self.target.unlink(missing_ok=True)


class FramesWriter:
    """WebP, GIF and APNG — written by Pillow, which needs every frame at once.

    These formats are built from the whole set rather than a stream, so the
    frames are kept. They are kept at the size that will actually be saved,
    which is what stops a long loop costing hundreds of megabytes.
    """

    #: Pillow writes the file in a single call that cannot be interrupted, so
    #: the Stop button is honest about being unable to stop this part.
    can_stop_while_writing = False

    def __init__(self, target, fps: int, fmt: str, quality: int = 90) -> None:
        self.target = Path(target)
        self.fps = max(1, int(fps))
        self.fmt = fmt
        self.quality = max(1, min(100, int(quality)))
        self._frames: list = []

    def add(self, image) -> None:
        self._frames.append(image)

    def finish(self):
        from PIL import Image

        if not self._frames:
            raise EncodingFailed("no frames were taken")
        gap = int(round(1000.0 / self.fps))
        first, rest = self._frames[0], self._frames[1:]
        extra: dict = {}
        if self.fmt == "gif":
            first = first.convert("P", palette=Image.Palette.ADAPTIVE)
            rest = [f.convert("P", palette=Image.Palette.ADAPTIVE) for f in rest]
        elif self.fmt == "webp":
            # THE QUALITY SLIDER WAS BEING IGNORED HERE. Left to itself Pillow
            # writes an animated WebP at 80, which puts a visible shimmer on
            # the surface of the shape as it turns -- the blocks the encoder
            # chose for one frame differ from the blocks it chose for the next,
            # and a smooth surface is exactly where that shows.
            #
            # `method` is how hard the encoder may work at finding a smaller
            # file for the same quality, and 4 is where it stops being worth
            # it. Measured on 120 frames of 900x700: method 4 took 1.8 s for
            # 1020 kB, method 6 took 49.2 s for 1015 kB. Half a per cent, for
            # twenty-seven times the wait.
            extra = {"quality": self.quality, "method": 4}
        first.save(self.target, save_all=True, append_images=rest, loop=0,
                   duration=gap, format={"webp": "WEBP", "gif": "GIF",
                                         "apng": "PNG"}[self.fmt], **extra)
        return self.target

    def cancel(self) -> None:
        self._frames = []
        self.target.unlink(missing_ok=True)


def writer_for(fmt: str, target, width: int, height: int, fps: int,
               quality: int, *, transparent: bool = False, codec=None):
    """The right writer for the format asked for, whichever kind it is."""
    if codec is None:
        return FramesWriter(target, fps, fmt, quality)
    exe = find_ffmpeg()
    if exe is None:
        raise NoEncoder(why_not(codec) or "there is no encoder on this computer")
    return MovieWriter(exe, target, width, height, fps, codec, quality,
                       transparent=transparent)
