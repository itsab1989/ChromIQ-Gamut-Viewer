"""The rules a picture is saved by. No window, no files left behind."""
import math

import pytest

import picture


# --- what a format can and cannot do ----------------------------------------

def test_a_format_that_cannot_be_see_through_says_so_rather_than_lying():
    """Every other application writes black and says nothing. Choosing it is
    the moment to say it, not after the file is on disk."""
    why = picture.check_transparency("jpeg", "transparent")
    assert why and "cannot hold" in why
    assert "PNG" in why and "WebP" in why          # says what WOULD work
    assert picture.check_transparency("png", "transparent") is None
    assert picture.check_transparency("webp", "transparent") is None
    assert picture.check_transparency("jpeg", "white") is None


def test_quality_only_means_something_where_it_means_something():
    assert picture.is_lossy("jpeg") and picture.is_lossy("webp")
    assert not picture.is_lossy("png") and not picture.is_lossy("svg")


def test_a_moving_picture_offers_full_colour_before_it_offers_gif():
    """A GIF holds 256 colours, which for a picture whose subject IS colour
    bands every gradient. It stays available and is not the default."""
    first = picture.MOVING_FORMATS[0]
    assert first[0] == "webp" and first[2] is True
    gif = [f for f in picture.MOVING_FORMATS if f[0] == "gif"][0]
    assert "256" in gif[1]


# --- a loop that closes ------------------------------------------------------

def test_a_full_turn_closes_exactly():
    """The last frame must not sit short of the first, or the loop jumps once
    every time round -- the difference between a picture somebody watches and
    one they notice."""
    for count in (12, 24, 60, 144):
        angles = picture.turn_angles(count, "round", 60)
        assert angles[0] == 0.0
        assert len(angles) == count
        step = angles[1] - angles[0]
        assert step * count == pytest.approx(360.0)
        assert angles[-1] + step == pytest.approx(360.0)   # closes on the first


def test_a_swing_returns_to_where_it_began():
    angles = picture.turn_angles(24, "swing", 60)
    assert angles[0] == pytest.approx(0.0)
    assert max(angles) == pytest.approx(30.0, abs=0.5)     # half of 60 each way
    assert min(angles) == pytest.approx(-30.0, abs=0.5)
    # and it comes back: the last frame is one step from the first
    assert angles[-1] == pytest.approx(-angles[1], abs=1e-9)


def test_the_angles_never_drift_open_however_many_frames():
    """Absolute positions, not "a little more each time": a rounded step
    accumulates over a hundred frames and the loop creeps open."""
    angles = picture.turn_angles(360, "round", 0)
    assert angles[-1] == pytest.approx(359.0)
    assert all(b > a for a, b in zip(angles, angles[1:]))


def test_frames_are_counted_sensibly_and_bounded():
    assert picture.frames_for(6, 24, "round") == 144
    assert picture.frames_for(4, 15, "round") == 60
    assert picture.frames_for(3, 25, "swing") % 2 == 0      # symmetrical ends
    assert picture.frames_for(0, 24, "round") >= 2          # never zero frames
    assert picture.frames_for(9999, 60, "round") <= 600      # never absurd


# --- sizes -------------------------------------------------------------------

def test_a_size_is_offered_by_what_it_is_for():
    keys = [k for k, _l, _w in picture.SIZES]
    assert keys[0] == "forum" and "custom" in keys
    for key, label, width in picture.SIZES:
        if key == "custom":
            continue
        assert width >= picture.MIN_WIDTH and label[0].isupper()


@pytest.mark.parametrize("given,expect", [
    (1600, 1600), (0, picture.MIN_WIDTH), (99999, picture.MAX_WIDTH),
    ("2400", 2400), (2400.7, 2401), (None, 2400), ("nonsense", 2400),
])
def test_any_width_at_all_comes_back_drawable(given, expect):
    assert picture.clamp_width(given) == expect


# --- saying how big before making it ----------------------------------------

def test_the_estimate_grows_the_way_the_file_does():
    small = picture.estimate_bytes(1600, 1000, "png")
    large = picture.estimate_bytes(3200, 2000, "png")
    assert 3.5 < large / small < 4.5                 # four times the pixels
    assert picture.estimate_bytes(1600, 1000, "webp") < small
    assert picture.estimate_bytes(1600, 1000, "jpeg", quality=40) < \
           picture.estimate_bytes(1600, 1000, "jpeg", quality=95)
    one = picture.estimate_bytes(800, 600, "webp", frames=1)
    many = picture.estimate_bytes(800, 600, "webp", frames=100)
    assert many > one * 20                            # a hundred frames cost more
    assert many < one * 100                           # but not a hundred times


def test_the_line_under_the_button_says_what_matters():
    still = picture.describe(2400, 1600, "png")
    assert "2400 × 1600" in still and ("kB" in still or "MB" in still)
    moving = picture.describe(1200, 800, "webp", frames=144)
    assert "144 frames" in moving
    assert "size of the window" in moving             # the honest caveat
    assert "any size" in picture.describe(800, 600, "svg")


@pytest.mark.parametrize("count,shown", [
    (512, "512 bytes"), (2048, "2 kB"), (5 * 1024 * 1024, "5.0 MB"),
])
def test_sizes_are_written_the_way_people_read_them(count, shown):
    assert picture.human_size(count) == shown


# --- names -------------------------------------------------------------------

def test_the_name_says_what_is_in_the_picture():
    assert picture.suggest_name(["Glossy-paper"], "png") == "Glossy-paper.png"
    assert picture.suggest_name(["Glossy", "Matte"], "webp") == "Glossy-vs-Matte.webp"
    assert picture.suggest_name(["Glossy"], "png", slicing=True,
                                lightness=50) == "Glossy-L50.png"
    assert picture.suggest_name(["Glossy"], "webp", moving=True) == \
           "Glossy-turning.webp"
    assert picture.suggest_name([], "png") == "gamut.png"


@pytest.mark.parametrize("nasty", [
    "a/b", "a:b", "a\\b", 'a"b', "a?b", "a*b", "a|b", "a\x00b", "  spaced  ",
])
def test_a_name_no_system_will_refuse(nasty):
    got = picture.safe_name(nasty)
    assert not any(c in got for c in '<>:"/\\|?*')
    assert got == got.strip()
    assert got


def test_nothing_of_the_users_is_ever_overwritten(tmp_path):
    """The rule everywhere else here: a picture exported an hour ago is
    theirs. A second export beside it, never over it."""
    first = tmp_path / "gamut.png"
    first.write_bytes(b"x")
    second = picture.next_free(first)
    assert second != first and not second.exists()
    assert second.name == "gamut-2.png"
    second.write_bytes(b"x")
    assert picture.next_free(first).name == "gamut-3.png"
    assert picture.next_free(tmp_path / "unused.png").name == "unused.png"
