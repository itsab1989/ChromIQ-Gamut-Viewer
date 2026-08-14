"""Tests for the standard-space and ICC reference gamuts."""
import numpy as np
import pytest

from gamutview import coverage
from references import REFERENCE_SPACES, reference_gamut


def test_the_spaces_rank_the_way_they_are_known_to():
    """Independent of this code: sRGB < Adobe RGB < Display P3 < Rec.2020 <
    ProPhoto is the published ordering. Getting it wrong would mean the
    primaries or the matrix are wrong."""
    v = {n: reference_gamut(n).volume for n in REFERENCE_SPACES}
    assert (v["sRGB"] < v["Adobe RGB (1998)"] < v["Display P3"]
            < v["Rec.2020"] < v["ProPhoto RGB"]), v


def test_srgb_fits_inside_adobergb_but_not_the_other_way():
    """The asymmetry everyone knows: Adobe RGB is wider in the greens."""
    s = reference_gamut("sRGB").vertices
    a = reference_gamut("Adobe RGB (1998)").vertices
    assert coverage(s, a)[0] > 0.99
    assert coverage(a, s)[0] < 0.80


def test_a_space_covers_itself_completely():
    g = reference_gamut("sRGB").vertices
    assert coverage(g, g)[0] > 0.999


def test_the_white_point_is_adapted_not_ignored():
    """sRGB is a D65 space. Plotted under D50 it must be chromatically adapted,
    so its shape differs — silently treating D65 as D50 would be a real error."""
    a = reference_gamut("sRGB", white_point="D50").volume
    b = reference_gamut("sRGB", white_point="D65").volume
    assert a != pytest.approx(b)


def test_every_space_builds_a_real_boundary():
    for name in REFERENCE_SPACES:
        g = reference_gamut(name, steps=5)
        assert g.mode == "device-cube"
        assert g.faces.max() < len(g.vertices)
        assert np.isfinite(g.vertices).all()
        assert REFERENCE_SPACES[name]["note"]        # each one explains itself


def test_an_unknown_space_lists_the_known_ones():
    with pytest.raises(ValueError, match="sRGB"):
        reference_gamut("Rec.709-ish")


def test_too_few_steps_is_refused():
    with pytest.raises(ValueError, match="at least 3"):
        reference_gamut("sRGB", steps=2)


def test_a_missing_icc_file_says_so():
    from references import icc_gamut
    with pytest.raises(ValueError, match="no such profile"):
        icc_gamut("/nonexistent/nope.icc")


def test_a_file_that_is_not_a_profile_says_so(tmp_path):
    """Reading a profile needs ArgyllCMS, which not every machine has -- so
    this accepts either honest refusal: "that is not a profile" when the tool
    is present, or "the tool is missing" when it is not. Asserting only the
    first assumed a tool that is not guaranteed, which is what broke this on
    the build machines while passing here."""
    from references import _find_iccgamut, icc_gamut
    bad = tmp_path / "not.icc"
    bad.write_text("this is not an ICC profile")
    with pytest.raises(ValueError, match="could not be read|needs ArgyllCMS"):
        icc_gamut(bad)
    if _find_iccgamut() is None:
        pytest.skip("ArgyllCMS is not installed, so only the refusal is checked")
