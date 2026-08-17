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
