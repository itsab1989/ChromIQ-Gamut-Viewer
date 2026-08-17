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
        PROFILE_SUFFIXES=gamut_app.GamutApp.PROFILE_SUFFIXES,
        PROFILE_GRID=gamut_app.GamutApp.PROFILE_GRID)
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
