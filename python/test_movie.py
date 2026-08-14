"""Finding an encoder, driving it, and what comes out the other end.

Two halves. The first needs nothing installed and checks the decisions --
where it looks, in what order, what a quality means for each codec, what the
command line says. The second actually encodes and reads the result back with
the encoder itself, and is skipped where there is not one.

The second half matters more than it looks. Every one of these formats has a
detail that is invisible until something refuses to play it: an H.265 file
without the ``hvc1`` tag opens nowhere on a Mac, an odd number of pixels is
rejected outright, and a see-through WebM is silently written solid unless the
encoder is told twice.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import pytest

import movie
import picture


# --------------------------------------------------------------------------
# What the choices mean
# --------------------------------------------------------------------------

def test_every_moving_format_says_which_extension_it_really_uses():
    """The name in the list is not the name on disk, and that is on purpose."""
    assert picture.extension_for("h264") == "mp4"
    assert picture.extension_for("hevc") == "mp4"
    assert picture.extension_for("vp9") == "webm"
    # AN APNG IS A PNG. Called .apng it opens in a browser and in very little
    # else; called .png every viewer shows it and the ones that know about
    # animation animate it.
    assert picture.extension_for("apng") == "png"
    assert picture.extension_for("webp") == "webp"


def test_a_film_is_named_for_its_container_not_for_the_choice():
    for fmt, ending in (("h264", ".mp4"), ("hevc", ".mp4"), ("vp9", ".webm")):
        name = picture.suggest_name(["Glossy"], fmt, moving=True)
        assert name.endswith(ending), name
        assert "h264" not in name and "vp9" not in name


def test_the_kinds_that_need_an_encoder_are_exactly_the_films():
    needs = {k for k, _l, _t, _e, c in picture.MOVING_FORMATS if c}
    assert needs == {"h264", "hevc", "vp9"}
    for kind in ("webp", "gif", "apng"):
        assert picture.codec_for(kind) is None
        assert not picture.is_film(kind)


def test_only_one_moving_kind_of_film_can_be_see_through():
    """Worth pinning: it is the whole reason WebM is offered at all."""
    films = [k for k, _l, _t, _e, c in picture.MOVING_FORMATS if c]
    see_through = [k for k in films if picture.holds_transparency(k)]
    assert see_through == ["vp9"]


def test_asking_for_a_see_through_mp4_explains_the_two_ways_round_it():
    why = picture.check_transparency("h264", "transparent")
    assert why
    assert "WebM" in why and "WebP" in why
    # Never a bare refusal: it has to say what to do instead.
    assert "pick a colour" in why.lower()


def test_a_see_through_webm_is_allowed_because_it_really_works():
    assert picture.check_transparency("vp9", "transparent") is None


def test_the_quality_slider_applies_to_moving_pictures_too():
    """It was hidden for them, so an animated WebP came out at whatever the
    library felt like -- which is 80, and it shimmers."""
    assert picture.is_lossy("webp")
    for film in ("h264", "hevc", "vp9"):
        assert picture.is_lossy(film)
    assert not picture.is_lossy("apng")           # lossless, nothing to set


# --------------------------------------------------------------------------
# Turning a quality into what an encoder understands
# --------------------------------------------------------------------------

def test_better_quality_always_means_a_lower_rate_factor():
    for codec in ("h264", "hevc", "vp9"):
        values = [movie.crf_for(codec, q) for q in range(40, 101, 5)]
        assert values == sorted(values, reverse=True), codec
        assert len(set(values)) > 3, f"{codec} barely responds to the slider"


def test_each_codec_gets_its_own_number_for_the_same_picture():
    """The scales differ: the same 90 has to become three different figures
    or one of the three comes out visibly worse than the others."""
    at90 = {c: movie.crf_for(c, 90) for c in ("h264", "hevc", "vp9")}
    assert at90["hevc"] > at90["h264"], "H.265 needs a higher number to match"
    assert at90["vp9"] > at90["hevc"], "VP9's scale runs higher again"
    assert len(set(at90.values())) == 3


def test_a_quality_outside_the_slider_is_not_an_error():
    for silly in (-40, 0, 130, 1000):
        for codec in ("h264", "hevc", "vp9"):
            got = movie.crf_for(codec, silly)
            assert 0 <= got <= 51


def test_a_size_an_encoder_would_refuse_is_brought_down_never_up():
    """H.264 stores colour at half resolution, so both sides must divide by
    two. Rounding up invents a row of pixels nobody drew."""
    assert movie.even(901) == 900
    assert movie.even(900) == 900
    assert movie.even(1) == 2                      # never zero, never negative
    assert movie.even(0) == 2


# --------------------------------------------------------------------------
# The command line, which is where the invisible details live
# --------------------------------------------------------------------------

def _command(codec, **kw):
    return movie.command("ffmpeg", f"/tmp/x.{'webm' if codec == 'vp9' else 'mp4'}",
                         900, 700, 24, codec, 90,
                         encoder={"h264": "libx264", "hevc": "libx265",
                                  "vp9": "libvpx-vp9"}[codec], **kw)


def test_h265_is_tagged_so_apple_players_will_open_it():
    """Without hvc1 the file is a perfectly good H.265 that QuickTime refuses,
    which looks exactly like a broken export."""
    args = _command("hevc")
    assert "-tag:v" in args
    assert args[args.index("-tag:v") + 1] == "hvc1"


def test_an_mp4_is_written_so_it_starts_before_it_has_all_arrived():
    for codec in ("h264", "hevc"):
        args = _command(codec)
        assert "+faststart" in args


def test_every_film_asks_for_the_pixel_format_that_plays_everywhere():
    """Something sharper exists and almost nothing will play it. A file nobody
    can open is not a better picture."""
    for codec in ("h264", "hevc"):
        args = _command(codec)
        assert "-pix_fmt" in args
        assert args[args.index("-pix_fmt", args.index("-c:v")) + 1] == "yuv420p"
    # The file being written is always the last word, never a stray option.
    assert _command("h264")[-1].endswith(".mp4")


def test_a_see_through_webm_says_so_twice_because_once_is_not_enough():
    """Both the pixel format and the look-ahead: with the look-ahead left on,
    the transparency is dropped without a word."""
    args = _command("vp9", transparent=True)
    assert "yuva420p" in args
    assert "-auto-alt-ref" in args
    assert args[args.index("-auto-alt-ref") + 1] == "0"


def test_a_solid_webm_does_not_pay_for_an_alpha_channel_it_does_not_use():
    args = _command("vp9", transparent=False)
    assert "yuv420p" in args and "yuva420p" not in args


def test_the_frames_go_in_down_a_pipe_rather_than_through_a_folder():
    args = _command("h264")
    assert "-i" in args and args[args.index("-i") + 1] == "-"
    assert "rawvideo" in args


def test_an_odd_size_is_settled_in_the_command_not_left_to_fail():
    args = movie.command("ffmpeg", "/tmp/x.mp4", 901, 701, 24, "h264", 90,
                         encoder="libx264")
    assert "900x700" in args


def test_asking_for_a_codec_nothing_can_write_says_so_rather_than_guessing(
        monkeypatch):
    """Never a silent fallback to some other codec: somebody who asked for an
    MP4 and was handed something else would find out at the worst moment."""
    monkeypatch.setattr(movie, "encoders", lambda: set())
    monkeypatch.setattr(movie, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    with pytest.raises(movie.NoEncoder) as complaint:
        movie.command("ffmpeg", "/tmp/x.mp4", 900, 700, 24, "h264", 90)
    assert "H.264" in str(complaint.value)


# --------------------------------------------------------------------------
# Where it looks
# --------------------------------------------------------------------------

def test_a_chosen_path_beats_everything_else(monkeypatch, tmp_path):
    mine = tmp_path / "my-ffmpeg"
    mine.write_text("not really")
    monkeypatch.setattr(movie, "EXTRA_PATH", str(mine))
    monkeypatch.setattr(movie, "_bundled", lambda: "/somewhere/bundled/ffmpeg")
    order = list(movie._candidates())
    assert order[0] == str(mine)


def test_the_copy_that_travels_with_the_application_comes_before_the_system(
        monkeypatch):
    monkeypatch.setattr(movie, "EXTRA_PATH", None)
    monkeypatch.delenv(movie.ENV_OVERRIDE, raising=False)
    monkeypatch.setattr(movie, "_bundled", lambda: "/bundled/ffmpeg")
    monkeypatch.setattr(movie.shutil, "which", lambda _n: "/usr/bin/ffmpeg")
    order = list(movie._candidates())
    assert order.index("/bundled/ffmpeg") < order.index("/usr/bin/ffmpeg")


def test_nothing_installed_is_reported_as_a_choice_not_as_a_fault(monkeypatch):
    monkeypatch.setattr(movie, "_candidates", lambda: iter(()))
    movie.forget()
    try:
        assert movie.find_ffmpeg() is None
        said = movie.summary()
        assert "not" in said.lower()
        # It must say what still works, or it reads as a broken installation.
        assert "WebP" in said
        why = movie.why_not("h264")
        assert movie.DOWNLOAD_URL in why
        assert "Where ffmpeg is" in why
    finally:
        movie.forget()


def test_a_build_missing_one_format_is_told_apart_from_none_at_all(monkeypatch):
    """Two quite different problems: one is something to install, the other is
    something to work around by choosing another format."""
    monkeypatch.setattr(movie, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(movie, "encoders", lambda: {"libx264"})
    movie._cache.pop("names", None)
    assert movie.can_write("h264")
    why = movie.why_not("hevc")
    assert "built without" in why
    assert "Everything else in the list still works" in why


def test_the_encoder_list_is_read_out_of_the_program_not_guessed(monkeypatch):
    """Which formats a build carries differs by build, so it is asked rather
    than assumed -- the alternative is failing at the end of a long export."""
    class Fake:
        stdout = ("Encoders:\n"
                  " V..... libx264              libx264 H.264 / AVC\n"
                  " V....D libx265              libx265 H.265 / HEVC\n"
                  " A..... aac                  AAC (Advanced Audio Coding)\n")
        stderr = ""

    monkeypatch.setattr(movie, "_quiet_run", lambda *_a, **_k: Fake())
    names = movie._read_encoders("ffmpeg")
    assert {"libx264", "libx265", "aac"} <= names
    assert "Encoders:" not in names             # the heading is not an encoder
    assert not any(n.startswith("H.26") for n in names)


# --------------------------------------------------------------------------
# Actually encoding something, and reading it back
# --------------------------------------------------------------------------

needs_encoder = pytest.mark.skipif(movie.find_ffmpeg() is None,
                                   reason="no ffmpeg on this machine")


def _frames(count=12, width=160, height=120, see_through=False):
    from PIL import Image, ImageDraw

    made = []
    for i in range(count):
        ground = (0, 0, 0, 0) if see_through else (18, 18, 22, 255)
        img = Image.new("RGBA", (width, height), ground)
        draw = ImageDraw.Draw(img)
        angle = 2 * math.pi * i / count
        x = width / 2 + 30 * math.cos(angle)
        y = height / 2 + 20 * math.sin(angle)
        draw.ellipse([x - 28, y - 22, x + 28, y + 22],
                     fill=(230, 90, 160, 255))
        made.append(img)
    return made


def _describe(path):
    """Ask the encoder itself what it wrote — nothing else is proof."""
    done = subprocess.run([movie.find_ffmpeg(), "-hide_banner", "-i",
                           str(path), "-f", "null", "-"],
                          capture_output=True, text=True)
    return done.stderr


@needs_encoder
@pytest.mark.parametrize("codec,ending", [("h264", "mp4"), ("hevc", "mp4"),
                                          ("vp9", "webm")])
def test_a_film_comes_out_playable_and_the_right_length(codec, ending, tmp_path):
    if not movie.can_write(codec):
        pytest.skip(f"this ffmpeg was built without {codec}")
    target = tmp_path / f"loop.{ending}"
    writer = movie.writer_for(codec, target, 160, 120, 24, 90,
                              codec=picture.codec_for(codec))
    for frame in _frames():
        writer.add(frame)
    made = writer.finish()
    assert made.exists() and made.stat().st_size > 0
    said = _describe(made)
    assert "160x120" in said
    expected = {"h264": "h264", "hevc": "hevc", "vp9": "vp9"}[codec]
    assert f"Video: {expected}" in said


@needs_encoder
def test_an_h265_film_carries_the_tag_apple_players_insist_on(tmp_path):
    if not movie.can_write("hevc"):
        pytest.skip("this ffmpeg was built without H.265")
    target = tmp_path / "loop.mp4"
    writer = movie.writer_for("hevc", target, 160, 120, 24, 90, codec="hevc")
    for frame in _frames():
        writer.add(frame)
    assert "hvc1" in _describe(writer.finish())


@needs_encoder
def test_a_see_through_webm_really_carries_its_transparency(tmp_path):
    """Measured rather than trusted: the encoder accepts the request and drops
    it silently if it is not asked in exactly the right way."""
    if not movie.can_write("vp9"):
        pytest.skip("this ffmpeg was built without VP9")
    clear = tmp_path / "clear.webm"
    solid = tmp_path / "solid.webm"
    for target, see_through in ((clear, True), (solid, False)):
        writer = movie.writer_for("vp9", target, 160, 120, 24, 90,
                                  transparent=see_through, codec="vp9")
        for frame in _frames(see_through=True):
            writer.add(frame)
        writer.finish()
    assert "alpha_mode" in _describe(clear)
    assert "alpha_mode" not in _describe(solid)
    # The alpha is a real extra plane, not just a flag on the container.
    assert clear.stat().st_size > solid.stat().st_size


@needs_encoder
def test_an_odd_sized_window_is_accepted_rather_than_refused(tmp_path):
    """A window is whatever size somebody dragged it to, and half of those are
    odd. Refusing them would make the feature a lottery."""
    target = tmp_path / "odd.mp4"
    writer = movie.writer_for("h264", target, 161, 121, 24, 90, codec="h264")
    for frame in _frames(width=161, height=121):
        writer.add(frame)
    made = writer.finish()
    assert "160x120" in _describe(made)


@needs_encoder
def test_stopping_part_way_leaves_nothing_behind(tmp_path):
    """A half-written film loops badly and looks like a fault rather than a
    choice, so there must not be one."""
    target = tmp_path / "abandoned.mp4"
    writer = movie.writer_for("h264", target, 160, 120, 24, 90, codec="h264")
    for frame in _frames(6):
        writer.add(frame)
    writer.cancel()
    assert not target.exists()


@needs_encoder
def test_a_film_is_far_smaller_than_the_same_frames_as_a_moving_picture(tmp_path):
    """The claim the dialog makes, checked rather than asserted."""
    frames = _frames(48, 320, 240)
    sizes = {}
    for kind, ending in (("webp", "webp"), ("h264", "mp4")):
        target = tmp_path / f"same.{ending}"
        writer = movie.writer_for(kind, target, 320, 240, 24, 90,
                                  codec=picture.codec_for(kind))
        for frame in frames:
            writer.add(frame)
        sizes[kind] = writer.finish().stat().st_size
    assert sizes["h264"] < sizes["webp"]


def test_a_moving_picture_needs_nothing_installed(tmp_path):
    """The three that need no encoder must keep needing none, whatever happens
    to the film side."""
    for kind, ending in (("webp", "webp"), ("gif", "gif"), ("apng", "png")):
        target = tmp_path / f"loop.{ending}"
        writer = movie.writer_for(kind, target, 160, 120, 24, 90,
                                  codec=picture.codec_for(kind))
        assert isinstance(writer, movie.FramesWriter)
        for frame in _frames():
            writer.add(frame)
        made = writer.finish()
        assert made.exists() and made.stat().st_size > 0


def test_the_quality_asked_for_reaches_the_file(tmp_path):
    """The bug this is here for: the slider was hidden for moving pictures and
    never passed on, so every animated WebP was written at 80."""
    frames = _frames(24, 320, 240)
    sizes = {}
    for quality in (50, 95):
        target = tmp_path / f"q{quality}.webp"
        writer = movie.writer_for("webp", target, 320, 240, 24, quality)
        for frame in frames:
            writer.add(frame)
        sizes[quality] = writer.finish().stat().st_size
    assert sizes[95] > sizes[50], "the quality made no difference at all"


def test_a_frame_of_the_wrong_size_is_refused_rather_than_written_askew(
        tmp_path, monkeypatch):
    """A film's size is fixed when the encoder starts. A frame that does not
    match would be read as the next one shifted, which is a picture that tears
    rather than an error anybody could diagnose."""
    from PIL import Image

    class Pretend(movie.MovieWriter):
        def __init__(self):                      # no encoder, no subprocess
            self.target = tmp_path / "x.mp4"
            self.width, self.height = 160, 120
            self._expected = 160 * 120 * 4
            self._trouble = None
            self._frames = 0
            import queue as _q
            self._queue = _q.Queue(maxsize=4)

    writer = Pretend()
    writer.add(Image.new("RGBA", (160, 120), (0, 0, 0, 255)))   # exactly right
    writer.add(Image.new("RGBA", (200, 160), (0, 0, 0, 255)))   # cropped down
    assert writer._queue.qsize() == 2
    # One that is too small cannot be rescued: every later frame would be read
    # shifted, giving a film that tears rather than an error anybody could
    # make sense of. So it says so instead.
    with pytest.raises(movie.EncodingFailed):
        writer.add(Image.new("RGBA", (80, 60), (0, 0, 0, 255)))
