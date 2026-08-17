"""Comparing two ICC profiles colour by colour.

THE QUESTION THIS FEATURE ANSWERS. Somebody has two profiles of one scanner
made years apart and wants to know what has changed. Comparing the gamut
SURFACES cannot tell them: two profiles can enclose nearly the same shape and
map the inside of it quite differently, and for an input profile the inside is
nearly the whole profile. Feeding both the same device values and seeing where
they land is the only question that answers it.

Nothing here needs ArgyllCMS or any file on the machine: the profiles are
written by hand from the same helper the chart tests use, so a machine with a
full colour toolchain and a bare build runner give the same answers.
"""
import struct

import numpy as np
import pytest

from test_chart import write_matrix_profile


@pytest.fixture
def one(tmp_path):
    return write_matrix_profile(tmp_path / "before.icc")


@pytest.fixture
def other_gamma(tmp_path):
    """The same primaries and a different tone curve — so the two enclose the
    very same shape and disagree everywhere inside it. That is exactly the
    case a gamut comparison cannot see, and the reason this exists."""
    return write_matrix_profile(tmp_path / "after.icc", gamma=2.4)


def test_a_profile_against_itself_is_zero_everywhere(one):
    """THE CHECK THAT PROVES THE PIPELINE IS HONEST. Any comparison can
    produce plausible small numbers; only this one proves the two sides are
    genuinely being asked the same question. A non-zero answer here means the
    grids are not aligned, and every other figure the feature reports would be
    describing noise."""
    import ti3gamut
    drift = ti3gamut.compare_profiles(one, one)
    assert drift.worst == 0.0
    assert drift.average == 0.0
    assert drift.rms == 0.0
    assert drift.over_one == 0 and drift.over_three == 0
    assert drift.comparable


def test_the_same_shape_with_a_different_curve_still_differs(one, other_gamma):
    """THE WHOLE JUSTIFICATION FOR THIS FEATURE, measured rather than argued.

    These two profiles share their primaries and differ only in tone curve.
    Measured: their gamut volumes come out within **0.011%** of each other —
    the same shape, for any purpose anybody would put a volume to — while the
    colours inside disagree by up to ΔE 4.2, averaging 1.76. Every one of
    those is a colour the two profiles send to a different place.

    So a gamut comparison, the thing this application was built to do, is
    blind to this by construction. That is not a criticism of it; a gamut
    answers "how much colour is there", and this asks "does it still land
    where it did", which no shape can show.
    """
    import icc_read
    import ti3gamut

    volume_a = icc_read.profile_gamut(one).volume
    volume_b = icc_read.profile_gamut(other_gamma).volume
    apart = abs(volume_a - volume_b) / volume_a
    assert apart < 0.001, (
        f"these two are meant to be the same shape, and their volumes differ "
        f"by {100 * apart:.3f}% — the premise of the test has changed")

    drift = ti3gamut.compare_profiles(one, other_gamma)
    assert drift.worst > 1.0, (
        "two different tone curves must show up as a real difference")
    assert drift.average > 0.0
    assert drift.over_one > 0
    # The point in one line: the shape says nothing, the inside says plenty.
    assert drift.worst > 100 * apart


def test_the_two_are_asked_about_exactly_the_same_colours(one, other_gamma):
    """No patch matching is needed because the grid is BUILT rather than
    found — but if that ever stopped being true the comparison would pair
    unrelated colours and still return a confident number."""
    import icc_read
    device_a, _ = icc_read.profile_to_lab(one, 9)
    device_b, _ = icc_read.profile_to_lab(other_gamma, 9)
    assert device_a.shape == device_b.shape
    assert np.array_equal(device_a, device_b)


def test_the_grid_is_the_size_it_says_it_is(one):
    import ti3gamut
    drift = ti3gamut.compare_profiles(one, one, steps=5)
    assert drift.steps == 5 and drift.channels == 3
    assert drift.matched == 5 ** 3
    assert drift.device_space == "RGB"


def test_an_rgb_profile_against_a_cmyk_one_is_refused(one, tmp_path):
    """REFUSED, NOT ANSWERED. The grid is in device coordinates, so "the same
    input" means nothing across two device spaces: 50% grey asked of an RGB
    profile and of a CMYK one are not the same request. Pairing them would
    produce a confident figure describing nothing at all."""
    import ti3gamut
    cmyk = tmp_path / "cmyk.icc"
    raw = bytearray(one.read_bytes())
    raw[16:20] = b"CMYK"
    cmyk.write_bytes(bytes(raw))
    with pytest.raises(ValueError) as caught:
        ti3gamut.compare_profiles(one, cmyk)
    said = str(caught.value)
    assert "RGB" in said and "CMYK" in said, said
    assert "nothing to compare" in said


def test_a_file_that_is_not_a_profile_says_so(one, tmp_path):
    import icc_read
    import ti3gamut
    rubbish = tmp_path / "notes.txt"
    rubbish.write_text("this is not a profile at all")
    with pytest.raises(icc_read.UnsupportedProfile):
        ti3gamut.compare_profiles(rubbish, one)


def test_a_truncated_profile_says_so_rather_than_guessing(one, tmp_path):
    import icc_read
    import ti3gamut
    cut = tmp_path / "cut.icc"
    cut.write_bytes(one.read_bytes()[:200])
    with pytest.raises(icc_read.UnsupportedProfile):
        ti3gamut.compare_profiles(cut, one)


def test_two_profiles_read_through_different_tables_are_flagged(one, tmp_path):
    """THE TRAP THIS FEATURE WOULD OTHERWISE WALK INTO.

    A profile is read through its relative colorimetric table when it has one,
    and through its perceptual table when it does not. Held against each
    other, a colorimetric profile and a perceptual one differ by a large
    amount that says nothing whatever about drift: perceptual rendering moves
    colour deliberately, so the two are not answering the same question.

    Measured on real files: the demo printer profile (A2B1) against the
    system sRGB profile (matrix) came out at ΔE 45 worst and 12.7 average —
    numbers that look like catastrophic drift and mean nothing of the kind.
    """
    import ti3gamut
    drift = ti3gamut.compare_profiles(one, one)
    assert drift.comparable, "the same profile twice reads the same way"

    fake = ti3gamut.ProfileDrift(
        matched=1, total_a=1, total_b=1, worst=45.0, average=12.7, rms=15.0,
        over_one=1, over_three=1, worst_patches=[], steps=9, channels=3,
        table_a="A2B1", table_b="matrix", device_space="RGB")
    assert not fake.comparable, (
        "a lookup table against bare primaries must not be reported as a "
        "like-for-like comparison")


def test_which_table_each_profile_uses_is_reported(one):
    """So the window can say it, rather than the reader having to guess which
    of the three routes their file took."""
    import icc_read
    assert icc_read.which_table(one) == "matrix"
    assert set(icc_read.TABLE_NAMES) == {"A2B1", "A2B0", "matrix"}
    for words in icc_read.TABLE_NAMES.values():
        assert words and not words.endswith("."), words


def test_the_worst_colours_are_named_in_units_a_reader_knows(one, other_gamma):
    """"R0 G88 B0" is somewhere a person can go and look. A row number in a
    grid they never saw is not."""
    import ti3gamut
    drift = ti3gamut.compare_profiles(one, other_gamma)
    assert drift.worst_patches, "the worst colours were not reported at all"
    label, delta, lab_a, lab_b = drift.worst_patches[0]
    assert label.startswith("R") and "G" in label and "B" in label, label
    assert delta == pytest.approx(drift.worst)
    assert len(lab_a) == 3 and len(lab_b) == 3
    # Worst first, so the reader meets the biggest problem at the top.
    deltas = [d for _l, d, _a, _b in drift.worst_patches]
    assert deltas == sorted(deltas, reverse=True)


def test_it_reads_the_same_shape_a_measurement_drift_does(one, other_gamma):
    """The window shows either through the same box, because to the reader it
    is the same question asked of a different kind of file. A field missing
    here is a crash there."""
    import ti3gamut
    drift = ti3gamut.compare_profiles(one, other_gamma)
    for field in ("matched", "total_a", "total_b", "worst", "average", "rms",
                  "over_one", "over_three", "worst_patches"):
        assert hasattr(drift, field), field
    assert isinstance(drift, ti3gamut.Drift)


def test_a_bigger_grid_finds_at_least_as_much(one, other_gamma):
    """Sampling more finely cannot find LESS disagreement than sampling
    coarsely, because the coarse grid's points are a subset. A drop would mean
    the two grids are not nested and the figures move with the setting."""
    import ti3gamut
    coarse = ti3gamut.compare_profiles(one, other_gamma, steps=5)
    fine = ti3gamut.compare_profiles(one, other_gamma, steps=9)
    assert fine.worst >= coarse.worst - 1e-9


# --- what the window does with it -------------------------------------------
#
# GamutApp is not built here: constructing it brings up a QWebEngineView and
# aborts the run (see test_chart_panel). So these call the methods a real
# click reaches, with a stand-in for the parts of the window they read --
# which is the same approach the chart panel's checks take.

from types import SimpleNamespace


class FakeLabel:
    def __init__(self):
        self._text = ""
        self._shown = True

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def isVisible(self):
        return self._shown

    def setVisible(self, shown):
        self._shown = shown


def window_with(paths):
    """A stand-in carrying only what the drift methods actually touch."""
    import gamut_app
    slots = [(p, None, None) for p in paths]
    win = SimpleNamespace(
        _slots=slots, _drift=FakeLabel(), _drift_worst=FakeLabel(),
        _drift_box=FakeLabel(),
        # The family lines under the numbers. Carried by the stand-in because
        # the real method writes to them on EVERY path, including the ones
        # that refuse to answer -- a report left behind from the last pair
        # names colours belonging to files the reader has closed.
        _drift_families=FakeLabel(), _drift_families_note=FakeLabel(),
        PROFILE_SUFFIXES=gamut_app.GamutApp.PROFILE_SUFFIXES,
        PROFILE_GRID=gamut_app.GamutApp.PROFILE_GRID)
    win._say_drift_families = (
        lambda *a, **k: gamut_app.GamutApp._say_drift_families(win, *a, **k))
    # The real method calls self._profile_pair(), so the stand-in has to carry
    # it too -- bound to the real one rather than to a second copy of the
    # logic, which would let the two drift apart without anything noticing.
    win._profile_pair = lambda: gamut_app.GamutApp._profile_pair(win)
    return win


def drift_text(paths):
    import gamut_app
    win = window_with(paths)
    pair = gamut_app.GamutApp._profile_pair(win)
    assert pair is not None, "two profiles were not recognised as a pair"
    gamut_app.GamutApp._update_profile_drift(win, *pair)
    return win._drift.text(), win._drift_worst.text()


def test_two_open_profiles_are_recognised_as_something_to_compare(one,
                                                                  other_gamma):
    """The box used to hide itself the moment a profile was opened, because a
    profile carries no measured patches. That is exactly the case somebody
    comparing two profiles is in."""
    import gamut_app
    win = window_with([one, other_gamma])
    assert gamut_app.GamutApp._profile_pair(win) == (one, other_gamma)


def test_a_measurement_beside_a_profile_is_not_a_profile_pair(one, tmp_path):
    """Half and half is neither question, and answering it as though it were
    the profile one would compare a profile against nothing."""
    import gamut_app
    win = window_with([one, tmp_path / "reading.ti3"])
    win._slots[1] = (tmp_path / "reading.ti3", None, object())   # a measurement
    assert gamut_app.GamutApp._profile_pair(win) is None


def test_a_gam_file_is_not_offered_as_a_profile(one, tmp_path):
    """A .gam is a surface with no lookup table inside it, so there is nothing
    to ask for a colour. It has no measurement either, so without the suffix
    check it would fall through to the profile branch and raise."""
    import gamut_app
    win = window_with([one, tmp_path / "shape.gam"])
    assert gamut_app.GamutApp._profile_pair(win) is None


def test_the_window_says_the_numbers_and_what_they_mean(one, other_gamma):
    said, worst = drift_text([one, other_gamma])
    assert "colours asked of both profiles" in said
    assert "ΔE" in said
    assert "moved most" in worst
    # The colours are named in units somebody can act on.
    assert "R" in worst and "G" in worst and "B" in worst


def test_two_profiles_read_differently_are_warned_about_in_the_window(
        one, tmp_path, monkeypatch):
    """The number is large and means nothing, so the warning has to arrive
    with it rather than after it."""
    import ti3gamut
    import gamut_app

    real = ti3gamut.compare_profiles

    def mismatched(a, b, **kw):
        got = real(a, b, **kw)
        return ti3gamut.ProfileDrift(
            **{**got.__dict__, "table_a": "A2B1", "table_b": "A2B0"})

    monkeypatch.setattr(ti3gamut, "compare_profiles", mismatched)
    _said, worst = drift_text([one, one])
    assert "READ THIS FIRST" in worst
    assert "not read the same way" in worst
    assert "not drift" in worst


def test_a_refusal_is_shown_rather_than_a_number(one, tmp_path):
    """Mismatched device spaces must reach the reader as an explanation. A
    silent empty box would look like the feature is broken."""
    import gamut_app
    cmyk = tmp_path / "cmyk.icc"
    raw = bytearray(one.read_bytes())
    raw[16:20] = b"CMYK"
    cmyk.write_bytes(bytes(raw))
    said, worst = drift_text([one, cmyk])
    assert "RGB" in said and "CMYK" in said
    assert worst == "", "no worst-colour list belongs under a refusal"


def test_an_unreadable_profile_is_explained_not_crashed(one, tmp_path):
    rubbish = tmp_path / "broken.icc"
    rubbish.write_bytes(b"not a profile at all")
    said, _worst = drift_text([one, rubbish])
    assert said, "the box was left empty, which reads as a broken feature"


def test_the_saved_page_carries_the_comparison(one, other_gamma):
    """BOTH EXPORTS, not just the window.

    The saved page's notes are read from the readout labels themselves rather
    than worked out again, so a page cannot disagree with the window it came
    from. That means this comparison travels into the page by construction --
    but "by construction" is exactly the kind of claim that stops being true
    quietly, so it is checked.
    """
    import gamut_app
    win = window_with([one, other_gamma])
    pair = gamut_app.GamutApp._profile_pair(win)
    gamut_app.GamutApp._update_profile_drift(win, *pair)
    win._volume = FakeLabel()
    win._volume_units = lambda: "Lab units"
    notes = gamut_app.GamutApp._readout_text(win)
    assert "colours asked of both profiles" in notes
    assert "ΔE" in notes
    assert "moved most" in notes


def test_the_spreadsheet_carries_the_caveat_with_the_numbers(one, other_gamma):
    """A row of figures outlives the window that explained them. Somebody
    opening this next year must not read "biggest difference 4.20" with
    nothing to say what it does and does not mean."""
    import gamut_app
    win = window_with([one, other_gamma])
    rows = gamut_app.GamutApp._profile_drift_rows(win)
    assert rows, "the comparison never reached the spreadsheet"
    flat = " | ".join(str(cell) for row in rows for cell in row)
    assert "biggest difference" in flat
    assert "dE2000" in flat
    assert "NOT how far the device drifted" in flat, (
        "the caveat did not travel with the numbers")
    assert "colours asked of both" in flat


def test_nothing_is_written_to_the_spreadsheet_when_it_does_not_apply(one,
                                                                      tmp_path):
    """Two measurements are the other question, and a stray profile block
    under them would be a column of nothing."""
    import gamut_app
    win = window_with([one, tmp_path / "reading.ti3"])
    win._slots[1] = (tmp_path / "reading.ti3", None, object())
    assert gamut_app.GamutApp._profile_drift_rows(win) == []


# --- drawing it ------------------------------------------------------------

def test_the_drift_is_drawn_where_the_disagreement_is(one, other_gamma):
    """The numbers say HOW MUCH; only the picture says WHERE. "Average ΔE 2"
    comes out the same whether a device drifted a little everywhere, which
    points at calibration, or hardly at all except in the deep blues, which is
    a different problem. The figures cannot tell those apart."""
    import ti3gamut
    d = ti3gamut.compare_profiles(one, other_gamma)
    figure = ti3gamut.build_figure(
        [], "t", drift=(d.lab_a, d.deltas, "how far it moved"), space="lab")
    clouds = [t for t in figure.data if t.type == "scatter3d"]
    assert len(clouds) == 1
    assert len(clouds[0].x) == d.matched, "not every colour was drawn"
    assert list(clouds[0].marker.color) == list(d.deltas), (
        "the picture and the table must be drawn from the same numbers")


def test_the_scale_is_fixed_rather_than_stretched_to_the_data(one, other_gamma):
    """A scale that fits itself to whatever is in front of it makes two
    pictures uncomparable: a pair of nearly identical profiles would look as
    alarming as a pair that genuinely disagree, because the reddest point is
    always red. A fixed ceiling means the same colour means the same amount in
    every picture this ever draws."""
    import ti3gamut
    small = ti3gamut.compare_profiles(one, one)             # zero everywhere
    big = ti3gamut.compare_profiles(one, other_gamma)
    marks = []
    for drift in (small, big):
        figure = ti3gamut.build_figure(
            [], "t", drift=(drift.lab_a, drift.deltas, "d"), space="lab")
        marks.append(figure.data[-1].marker)
    assert marks[0].cmin == marks[1].cmin == 0.0
    assert marks[0].cmax == marks[1].cmax == ti3gamut.DRIFT_CEILING


def test_the_key_says_what_the_numbers_mean_in_words(one):
    """ΔE is not a unit anybody has intuitions about. "3 — plain" is."""
    import ti3gamut
    d = ti3gamut.compare_profiles(one, one)
    figure = ti3gamut.build_figure(
        [], "t", drift=(d.lab_a, d.deltas, "d"), space="lab")
    ticks = list(figure.data[-1].marker.colorbar.ticktext)
    assert any("same" in t for t in ticks)
    assert any("invisible" in t for t in ticks)
    assert any("plain" in t for t in ticks)


def test_colours_that_agree_are_drawn_quietly_rather_than_dropped(one,
                                                                  other_gamma):
    """Leaving them out would put holes in the cloud and invite the reading
    that something is missing there, when what is true is that nothing has
    changed there."""
    import numpy as _np
    import ti3gamut
    d = ti3gamut.compare_profiles(one, other_gamma)
    figure = ti3gamut.build_figure(
        [], "t", drift=(d.lab_a, d.deltas, "d"), space="lab")
    sizes = _np.asarray(figure.data[-1].marker.size)
    assert len(sizes) == d.matched, "a colour was dropped from the cloud"
    quiet = _np.asarray(d.deltas) < ti3gamut.DRIFT_FLOOR
    if quiet.any() and (~quiet).any():
        assert sizes[quiet].max() < sizes[~quiet].min(), (
            "the ones that moved must stand out from the ones that did not")


def test_every_point_needs_exactly_one_difference(one):
    """A mismatch here would pair a colour with another colour's number and
    paint a confident picture of nothing."""
    import numpy as _np
    import pytest as _pytest
    import ti3gamut
    with _pytest.raises(ValueError):
        ti3gamut.drift_cloud(_np.zeros((5, 3)), _np.zeros(4), "d")


def test_the_window_draws_it_only_when_it_means_something(one, other_gamma,
                                                          tmp_path):
    """Three ways it must stay out of the picture, each for its own reason."""
    import gamut_app
    win = window_with([one, other_gamma])
    win._space = SimpleNamespace(currentData=lambda: "lab")
    win._drift_draw = SimpleNamespace(isChecked=lambda: True)

    assert gamut_app.GamutApp._drift_for_figure(win) is not None

    # 1. Not asked for.
    win._drift_draw = SimpleNamespace(isChecked=lambda: False)
    assert gamut_app.GamutApp._drift_for_figure(win) is None

    # 2. IN INK AMOUNTS the axes are device values, so a Lab position painted
    #    into that cube puts every colour in the wrong place while looking
    #    perfectly plausible.
    win._drift_draw = SimpleNamespace(isChecked=lambda: True)
    win._space = SimpleNamespace(currentData=lambda: "rgb")
    assert gamut_app.GamutApp._drift_for_figure(win) is None

    # 3. Not two profiles at all.
    win._space = SimpleNamespace(currentData=lambda: "lab")
    win._slots[1] = (tmp_path / "reading.ti3", None, object())
    assert gamut_app.GamutApp._drift_for_figure(win) is None


def test_a_meaningless_comparison_is_never_painted(one, monkeypatch):
    """A picture of a meaningless number is worse than no picture: it looks
    like evidence. When the two were read through different tables the box
    explains why in words, and the cloud stays away."""
    import gamut_app
    import ti3gamut

    real = ti3gamut.compare_profiles

    def mismatched(a, b, **kw):
        got = real(a, b, **kw)
        return ti3gamut.ProfileDrift(
            **{**got.__dict__, "table_a": "A2B1", "table_b": "A2B0"})

    monkeypatch.setattr(ti3gamut, "compare_profiles", mismatched)
    win = window_with([one, one])
    win._space = SimpleNamespace(currentData=lambda: "lab")
    win._drift_draw = SimpleNamespace(isChecked=lambda: True)
    assert gamut_app.GamutApp._drift_for_figure(win) is None


def test_the_picture_export_photographs_the_cloud_that_is_on_screen():
    """BOTH EXPORTS, and the picture one works differently from the page one.

    A still is not rebuilt from a fresh figure -- it is Plotly.toImage called
    on the div already in the view. So whatever is on screen is what lands in
    the PNG, and the drift cloud reaches it through the same _render_options
    that put it on screen. That is worth pinning rather than trusting: if the
    still ever started rebuilding its own figure, it would quietly lose every
    option not passed to that rebuild, and nothing would look wrong until
    somebody compared a saved picture with the window.
    """
    import inspect

    import gamut_app
    still = inspect.getsource(gamut_app.GamutApp._save_still)
    assert "plotly-graph-div" in still, (
        "the still no longer photographs the view; check it still carries "
        "everything the window is showing")
    assert "Plotly.toImage" in still
    assert "build_figure" not in still, (
        "the still now builds its own figure, so it can silently disagree "
        "with the window it came from")
    # And the option really is in the one place both routes read.
    options = inspect.getsource(gamut_app.GamutApp._render_options)
    assert "drift=" in options


def test_the_drift_cloud_goes_into_one_room_not_both():
    """Two rooms show one shape each. The cloud is drawn at the FIRST
    profile's positions, so putting it in the second room would be one
    profile's colours floating inside the other profile's shape -- a picture
    that looks deliberate and says something untrue.

    The same trap the chart hit one line above it, which is why that one is
    popped out of the shared options and marked per room.
    """
    import inspect

    import gamut_app
    source = inspect.getsource(gamut_app.GamutApp._write_two_rooms)
    assert 'options.pop("drift"' in source, (
        "drift is still in the shared options, so both rooms draw it")
    assert "drift=drift if i == 0 else None" in source


# --- which way it went, not only how far ------------------------------------
#
# Basti: "is there an option for the heat map to visualize the direction of the
# drift?" There was not, and the information was already there and thrown away:
# compare_profiles computed lab_b, reduced it to a distance and dropped it.
#
# ΔE2000 is a MAGNITUDE. A printer drifting lighter and one drifting darker by
# the same amount give an identical number and an identical cloud, and want
# different cures.

def _bent(tmp_path, name, amount):
    """A profile whose curve is bent by *amount*, either way."""
    return write_matrix_profile(tmp_path / f"{name}.icc", gamma=2.2 + amount)


def test_the_movement_is_kept_and_it_is_a_direction(tmp_path):
    import ti3gamut
    a = _bent(tmp_path, "a", 0.0)
    b = _bent(tmp_path, "b", 0.2)
    d = ti3gamut.compare_profiles(a, b)
    assert d.lab_b is not None, "lab_b was computed and thrown away"
    moved = d.moved
    assert moved.shape == d.lab_a.shape
    # The distance is the length of the movement, which is the whole point:
    # one is the other with the direction taken off it.
    import numpy as np
    assert np.allclose(moved, np.asarray(d.lab_b) - np.asarray(d.lab_a))


def test_two_opposite_drifts_are_told_apart_by_direction_and_not_by_distance(
        tmp_path):
    """THE CLAIM THIS FEATURE MAKES, measured.

    Two runs bent the same amount in opposite directions: the distances agree
    to within a rounding, and the movements are equal and opposite.
    """
    import numpy as np
    import ti3gamut
    base = _bent(tmp_path, "base", 0.0)
    up = ti3gamut.compare_profiles(base, _bent(tmp_path, "up", 0.2))
    down = ti3gamut.compare_profiles(base, _bent(tmp_path, "down", -0.2))

    assert abs(up.average - down.average) < 0.35 * max(up.average, 0.01), (
        f"the distances should be close: {up.average:.2f} vs "
        f"{down.average:.2f}")
    one, other = up.moved.mean(axis=0), down.moved.mean(axis=0)
    assert np.sign(one[0]) == -np.sign(other[0]), (one, other)
    assert abs(one[0]) > 0.1 and abs(other[0]) > 0.1, (
        f"neither moved far enough for the test to mean anything: "
        f"{one}, {other}")


def test_each_direction_reads_its_own_axis_and_names_both_ends(tmp_path):
    import numpy as np
    import ti3gamut
    d = ti3gamut.compare_profiles(_bent(tmp_path, "a", 0.0),
                                  _bent(tmp_path, "b", 0.2))
    for axis, column in (("L", 0), ("a", 1), ("b", 2)):
        trace = ti3gamut.drift_direction(d.lab_a, d.moved, "t", axis=axis)[0]
        assert np.allclose(np.asarray(trace.marker.color, float),
                           d.moved[:, column]), axis
        # BOTH ENDS NAMED, because a scale that runs both ways from nothing is
        # only readable if the reader is told what each end means.
        words = list(trace.marker.colorbar.ticktext)
        less, more = ti3gamut.DIRECTIONS[axis][1], ti3gamut.DIRECTIONS[axis][2]
        assert less in words[0] and more in words[-1], words
        assert "no change" in words, words


def test_the_direction_scale_is_centred_on_no_change_and_fixed(tmp_path):
    """A signed quantity on a one-ended ramp reads as "more is worse", and a
    scale stretched to the data makes two pictures uncomparable."""
    import ti3gamut
    d = ti3gamut.compare_profiles(_bent(tmp_path, "a", 0.0),
                                  _bent(tmp_path, "b", 0.05))
    trace = ti3gamut.drift_direction(d.lab_a, d.moved, "t", axis="L")[0]
    assert trace.marker.cmin == -ti3gamut.DIRECTION_LIMIT
    assert trace.marker.cmax == +ti3gamut.DIRECTION_LIMIT
    assert trace.marker.cmin == -trace.marker.cmax


def test_the_direction_colours_are_not_the_magnitude_colours(tmp_path):
    """In a picture whose subject IS colour, painting "went redder" in red
    invites the reader to take a dot's colour for the colour it stands for.
    And carrying the magnitude view's red across would mean two different
    things wear one colour."""
    import ti3gamut
    magnitude = {c for _at, c in ti3gamut.DRIFT_SCALE}
    direction = {c for _at, c in ti3gamut.DIRECTION_SCALE}
    assert not (magnitude & direction), magnitude & direction


def test_a_direction_nobody_asked_for_is_refused_rather_than_guessed(tmp_path):
    import pytest
    import ti3gamut
    d = ti3gamut.compare_profiles(_bent(tmp_path, "a", 0.0),
                                  _bent(tmp_path, "b", 0.1))
    with pytest.raises(ValueError) as complaint:
        ti3gamut.drift_direction(d.lab_a, d.moved, "t", axis="chroma")
    assert "chroma" in str(complaint.value)


def test_the_figure_draws_a_direction_when_asked_and_a_distance_otherwise(
        tmp_path):
    """The fourth item in the drift tuple is what asks; three-item callers go
    on meaning "how far", which is the right default."""
    import ti3gamut
    d = ti3gamut.compare_profiles(_bent(tmp_path, "a", 0.0),
                                  _bent(tmp_path, "b", 0.2))
    far = ti3gamut.build_figure([], "t", space="lab",
                                drift=(d.lab_a, d.deltas, "how far"))
    which = ti3gamut.build_figure([], "t", space="lab",
                                  drift=(d.lab_a, d.moved, "which way", "L"))
    assert far.data[0].marker.cmin == 0.0, "a distance starts at nothing"
    assert which.data[0].marker.cmin < 0, "a direction runs both ways"
