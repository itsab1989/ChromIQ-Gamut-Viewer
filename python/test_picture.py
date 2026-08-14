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


# --- the loop closes, whatever anybody sets ---------------------------------

def test_the_loop_closes_for_every_setting_anybody_can_choose():
    """THE claim behind a moving picture, checked exhaustively rather than on
    one example.

    The export does exactly ONE complete cycle over the seconds asked for --
    360 degrees for a full turn, one there-and-back for a swing -- so the
    frame after the last is the first, whatever the sweep, the seconds or the
    frame rate. The speed slider does not enter into it, which is precisely
    why the loop cannot drift open.
    """
    for mode in ("round", "swing"):
        for seconds in (2, 6, 12):
            for fps in (15, 24, 25, 30, 50, 60):
                for sweep in (10, 38, 95, 180):
                    count = picture.frames_for(seconds, fps, mode)
                    angles = picture.turn_angles(count, mode, sweep)
                    assert len(angles) == count
                    steps = [b - a for a, b in zip(angles, angles[1:])]
                    if mode == "round":
                        wrap = 360.0 - angles[-1]
                    else:
                        wrap = angles[0] - angles[-1]
                    biggest = max(abs(s) for s in steps)
                    assert abs(wrap) <= biggest * 1.01 + 1e-9, (
                        f"{mode} {seconds}s {fps}fps {sweep}deg: the join is "
                        f"{abs(wrap):.4f} against a step of {biggest:.4f}")


def test_two_axes_moving_together_both_close_on_the_same_frame():
    """Left-and-right and up-and-down are given the same number of frames, so
    a shape doing both returns to its start in one place, not two."""
    count = picture.frames_for(6, 25, "swing")
    across = picture.turn_angles(count, "swing", 95)
    upward = picture.turn_angles(count, "swing", 38)
    assert len(across) == len(upward) == count
    assert across[0] == pytest.approx(0.0) and upward[0] == pytest.approx(0.0)
    # the step that wraps round is no larger than the steps inside the loop
    for angles in (across, upward):
        inside = max(abs(b - a) for a, b in zip(angles, angles[1:]))
        assert abs(angles[0] - angles[-1]) <= inside * 1.01 + 1e-9


def test_how_long_decides_the_export_not_how_fast():
    """Worth stating because it is a deliberate difference from the screen: a
    faster setting makes the LIVE view move faster, while the exported loop
    always fits exactly one cycle into the seconds chosen. That is what keeps
    it seamless, and it means the same export takes the same time to make
    whatever the speed slider says."""
    slow = picture.frames_for(6, 25, "swing")
    same = picture.frames_for(6, 25, "swing")
    assert slow == same
    assert picture.frames_for(12, 25, "swing") == 2 * slow
    # the angles span one cycle either way -- the speed never appears
    import inspect
    assert "speed" not in inspect.signature(picture.turn_angles).parameters


# --------------------------------------------------------------------------
# Getting see-through back out of a copy of the screen
# --------------------------------------------------------------------------

def _mix(colour, alpha, ground):
    """What a painter would put on screen for this colour over this ground."""
    import numpy as np
    colour = np.asarray(colour, dtype=float)
    ground = np.asarray(ground, dtype=float)
    return np.round(colour * alpha + ground * (1 - alpha)).astype("uint8")


def test_a_see_through_picture_is_recovered_exactly_from_two_grounds():
    """The claim: draw it on white, draw it on black, and the difference is
    the see-through. Checked against colours and coverages whose answer is
    known in advance rather than against another run of the same code."""
    import numpy as np

    wanted = [((255, 0, 0), 1.0), ((0, 128, 255), 0.5), ((255, 255, 255), 0.25),
              ((0, 0, 0), 0.75), ((90, 200, 40), 0.0)]
    on_white = np.zeros((1, len(wanted), 3), dtype="uint8")
    on_black = np.zeros((1, len(wanted), 3), dtype="uint8")
    for i, (colour, alpha) in enumerate(wanted):
        on_white[0, i] = _mix(colour, alpha, (255, 255, 255))
        on_black[0, i] = _mix(colour, alpha, (0, 0, 0))

    got = picture.alpha_from_two_grounds(on_white, on_black)
    for i, (colour, alpha) in enumerate(wanted):
        assert abs(int(got[0, i, 3]) - round(alpha * 255)) <= 2, (
            f"alpha wrong for {colour} at {alpha}")
        if alpha > 0.2:                       # below that the colour is moot
            for channel in range(3):
                assert abs(int(got[0, i, channel]) - colour[channel]) <= 4, (
                    f"colour wrong for {colour} at {alpha}")


def test_where_nothing_is_drawn_comes_back_completely_clear():
    import numpy as np

    on_white = np.full((4, 4, 3), 255, dtype="uint8")
    on_black = np.zeros((4, 4, 3), dtype="uint8")
    got = picture.alpha_from_two_grounds(on_white, on_black)
    assert (got[..., 3] == 0).all()


def test_where_the_shape_is_solid_nothing_is_taken_away():
    """A solid surface must not come back faintly see-through, or a saved loop
    would look washed out everywhere it was strongest."""
    import numpy as np

    same = np.full((4, 4, 3), 40, dtype="uint8")
    got = picture.alpha_from_two_grounds(same, same)
    assert (got[..., 3] == 255).all()
    assert (got[..., 0] == 40).all()
