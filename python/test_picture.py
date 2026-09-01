"""The rules a picture is saved by. No window, no files left behind."""
import math
import pathlib

import pytest

import picture

HERE = pathlib.Path(__file__).resolve().parent.parent


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


def _a_picture(folder, maker):
    """A small picture whose colours are decided by *maker*."""
    import numpy as np
    from PIL import Image
    folder.mkdir(parents=True, exist_ok=True)
    a = np.zeros((48, 48, 3), np.uint8)
    for y in range(48):
        for x in range(48):
            a[y, x] = maker(x, y)
    out = folder / "holiday.png"          # THE SAME STEM, on purpose
    Image.fromarray(a).save(out)
    return out


def test_a_pictures_figure_comes_from_that_picture_and_not_its_namesake(
        tmp_path):
    """⚠ ONE PHOTOGRAPH MEASURED AGAINST ANOTHER PHOTOGRAPH'S SHAPE.

    The figure looked its facts up by matching the STEM of the label against
    a dict of paths that was never emptied, taking the first entry that hit.
    Two folders holding a `holiday.png` are enough: with `wide/holiday.png`
    on screen and `narrow/holiday.png` opened earlier, the panel measured one
    picture's pixels against the other's shape and said

        "Every colour in holiday is one holiday (picture) can print."

    when the truth was 100% out of reach, worst 37.3 ΔE. A name is a stem and
    two folders can share one; a path is the identity a name stands in for.
    """
    import gamut_app
    from types import SimpleNamespace as NS
    from imagegamut import image_gamut

    wide = _a_picture(tmp_path / "wide",
                      lambda x, y: (x * 5 % 256, y * 5 % 256, (x + y) % 256))
    narrow = _a_picture(tmp_path / "narrow",
                        lambda x, y: (110 + x // 5, 110 + y // 5, 110))
    facts = {}
    shapes_by_path = {}
    for p in (narrow, wide):              # narrow FIRST, so a stem match hits it
        built, kept = image_gamut(p, white_point="D50", space="lab")
        facts[str(p)] = kept
        shapes_by_path[p] = built

    said = []
    # ⚠ THE REAL METHOD, not a stub that answers True. A stand-in that
    # invents its own answer stops testing the window and starts testing
    # itself — which is how three stand-ins in this suite came to be blind.
    hall = NS(_image_facts=facts,
              _picture_loss=NS(setText=said.append),
              _lays_down_ink=gamut_app.GamutApp._lays_down_ink.__get__(
                  NS(), gamut_app.GamutApp))
    gamut_app.GamutApp._update_picture_loss(
        hall, "holiday", shapes_by_path[wide],
        "holiday", shapes_by_path[narrow], (wide, narrow))
    text = [t for t in said if t]
    assert text, "no figure at all"
    line = text[0]

    # The truth, computed here from the file that is actually on screen.
    from imagegamut import out_of_reach
    truth = out_of_reach(facts[str(wide)], shapes_by_path[narrow])
    assert truth["of_the_picture"], (
        "these two pictures no longer differ, so this test proves nothing")
    assert f"{100 * truth['of_the_picture']:.0f}%" in line, (
        f"the figure does not match the picture on screen: {line!r}")
    assert "Every colour in holiday" not in line


def test_a_pictures_facts_do_not_outlive_the_file_they_describe(tmp_path):
    """`_image_facts` was keyed by path like three sibling caches and left
    out of every clear, so a photograph edited and reopened under the same
    name kept the pixels it used to have.

    ONE ENTRY, not the whole dict, and BEFORE the build. Emptying all of
    it broke the feature outright — opening a paper after a photograph threw
    the photograph's facts away and the figure vanished from a window still
    showing the picture. And the build is what writes those facts, so a
    clear placed with the sibling caches further down would discard the
    facts of the picture being opened.
    """
    import ast
    import inspect
    import gamut_app

    src = inspect.getsource(gamut_app.GamutApp._load)
    tree = ast.parse(src.strip())
    cleared = built = None
    for i, node in enumerate(ast.walk(tree)):
        pass
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if "_image_facts.pop(str(path), None)" in line:
            cleared = i
        if "_build_patiently(" in line and built is None:
            built = i
    assert cleared is not None, (
        "the file being opened keeps whatever facts it had last time")
    assert "_image_facts.clear()" not in src, (
        "emptying the whole dict discards the facts of pictures that are "
        "still on screen, and the figure disappears for them")
    assert built is not None
    assert cleared < built, (
        "the facts are emptied AFTER the build that writes them, which "
        "throws away the facts of the picture being opened")


def test_a_photograph_is_never_given_a_paper_white_or_blacks(tmp_path):
    """⚠ THE FIFTH SIBLING OF THE FAULT THIS RELEASE IS NAMED FOR.

    `_update_range` walked the slots with no test of kind at all, so a
    photograph in a slot was described as

        "holiday: blacks reach L* 0, paper white L* 98 and very warm"

    about a file that was never printed on anything and has no paper. The
    coverage line an inch above it had already been fixed for exactly this —
    its comment says getting it backwards "is the sort of sentence that makes
    somebody distrust the number beside it" — and the fix was never carried
    to the three readouts beside it.

    ⚠ AND IT SURVIVED A WEEK OF BEING PHOTOGRAPHED. It is in a screenshot
    taken while proving a different fix, two lines under the sentence being
    checked, read past every time. That is why this is a test and not a
    careful habit.
    """
    import gamut_app
    from types import SimpleNamespace as NS

    hall = NS(_lays_down_ink=gamut_app.GamutApp._lays_down_ink.__get__(
        NS(), gamut_app.GamutApp))
    picture = _a_picture(tmp_path / "shot",
                         lambda x, y: (x * 5 % 256, y * 5 % 256, 90))
    paper = HERE / "demo" / "Matte-paper.ti3"
    assert not gamut_app.GamutApp._lays_down_ink(hall, picture), (
        "a photograph was taken for something that lays down ink")
    assert gamut_app.GamutApp._lays_down_ink(hall, paper), (
        "a measured paper stopped counting as something that prints")
    assert gamut_app.GamutApp._lays_down_ink(hall, HERE / "demo" /
                                             "Glossy-paper.icc"), (
        "a printer profile stopped counting as something that prints")
    # A comparison with no file — a colour space, the visible solid — prints
    # nothing either, and must not raise on the way to saying so.
    assert not gamut_app.GamutApp._lays_down_ink(hall, None)


def test_the_verb_follows_the_other_sides_kind(tmp_path):
    """"can print" was hard-coded in both picture-loss sentences, so with two
    photographs open the panel said "Every colour in narrowshot is one
    wideshot (picture) can print". A photograph prints nothing."""
    import gamut_app
    from types import SimpleNamespace as NS
    from imagegamut import image_gamut

    wide = _a_picture(tmp_path / "w",
                      lambda x, y: (x * 5 % 256, y * 5 % 256, (x + y) % 256))
    narrow = _a_picture(tmp_path / "n",
                        lambda x, y: (110 + x // 5, 110 + y // 5, 110))
    facts, shapes_by = {}, {}
    for one in (wide, narrow):
        built, kept = image_gamut(one, white_point="D50", space="lab")
        facts[str(one)] = kept
        shapes_by[one] = built

    said = []
    hall = NS(_image_facts=facts,
              _picture_loss=NS(setText=said.append),
              _lays_down_ink=gamut_app.GamutApp._lays_down_ink.__get__(
                  NS(), gamut_app.GamutApp))
    gamut_app.GamutApp._update_picture_loss(
        hall, "w-shot", shapes_by[wide], "n-shot", shapes_by[narrow],
        (wide, narrow))
    line = [t for t in said if t]
    assert line, "no figure at all"
    assert "can print" not in line[0], (
        f"a photograph was said to print something: {line[0]!r}")
    assert "holds" in line[0], line[0]

    # AND THE POSITIVE HALF: against a real paper it must still say "print".
    said.clear()
    from ti3gamut import read_measurement
    from gamutview import build_gamut
    m = read_measurement(HERE / "demo" / "Matte-paper.ti3", "D50", False)
    paper_shape = build_gamut(m.lab, m.device, input_space="lab",
                              space="lab", white_point="D50")
    gamut_app.GamutApp._update_picture_loss(
        hall, "w-shot", shapes_by[wide], "Matte-paper", paper_shape,
        (wide, HERE / "demo" / "Matte-paper.ti3"))
    line = [t for t in said if t]
    assert line and "can print" in line[0], (
        f"a measured paper stopped printing: {line!r}")
