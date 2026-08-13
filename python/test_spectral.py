"""Tests for the spectral locus / optimal-colour solid."""
import numpy as np
import pytest
from scipy.spatial import Delaunay

import spectral
from gamutview import WHITE_POINTS, lab_to_xyz, xyz_to_lab


def test_the_grid_is_the_cie_table():
    w = spectral.wavelengths()
    assert len(w) == 95 and w[0] == 360 and w[-1] == 830
    assert np.allclose(np.diff(w), 5)


@pytest.mark.parametrize("ill,ref", [("D50", "D50"), ("D65", "D65")])
def test_a_perfect_white_reflector_reproduces_the_published_white_point(ill, ref):
    """The strongest check available: integrating a flat 1.0 reflectance under
    an illuminant must give that illuminant's own white point. It exercises the
    colour-matching functions, the daylight reconstruction and the
    normalisation at once, against numbers nobody here chose."""
    xyz = spectral.spectrum_to_xyz(np.ones(95), ill)
    assert np.allclose(xyz, WHITE_POINTS[ref], atol=6e-4), (xyz, WHITE_POINTS[ref])
    lab = xyz_to_lab(xyz[None, :], ref)[0]
    assert lab[0] == pytest.approx(100.0, abs=0.02)
    assert abs(lab[1]) < 0.1 and abs(lab[2]) < 0.1


def test_equal_energy_gives_equal_tristimulus():
    xyz = spectral.spectrum_to_xyz(np.ones(95), "E")
    assert np.allclose(xyz, 1.0, atol=1e-3)


def test_black_is_black_and_half_is_half():
    assert np.allclose(spectral.spectrum_to_xyz(np.zeros(95), "D50"), 0.0)
    half = spectral.spectrum_to_xyz(np.full(95, 0.5), "D50")
    assert half[1] == pytest.approx(0.5, abs=1e-6)


def test_the_solid_spans_black_to_white():
    v, f = spectral.optimal_colour_solid("D50", steps=32)
    lab = xyz_to_lab(v, "D50")
    assert lab[:, 0].min() == pytest.approx(0.0, abs=0.5)
    assert lab[:, 0].max() == pytest.approx(100.0, abs=0.5)
    assert f.shape[1] == 3 and f.max() < len(v)


def test_a_real_printer_gamut_lies_inside_it():
    """The physical requirement: no printed surface can be outside the limit
    for surface colours. Uses a synthetic but plausible printer cloud so the
    test needs no measurement file."""
    v, _ = spectral.optimal_colour_solid("D50", steps=32)
    inside = Delaunay(v)
    rng = np.random.default_rng(3)
    # Chroma has to taper towards black and white: the solid is widest in the
    # mid tones and closes to a point at either end, so a uniform Lab box is
    # NOT a plausible printer and would poke outside near L* 8 and 96. Scaling
    # the radius by how far the lightness is from either end models a real
    # printer's shape and is the honest thing to assert.
    ell = rng.uniform(8, 96, 500)
    taper = np.sin(np.pi * ell / 100.0)          # 0 at both ends, 1 mid-tone
    ang = rng.uniform(0, 2 * np.pi, 500)
    rad = rng.uniform(0, 55, 500) * taper
    lab = np.column_stack([ell, rad * np.cos(ang), rad * np.sin(ang)])
    assert (inside.find_simplex(lab_to_xyz(lab, "D50")) >= 0).all()


def test_the_illuminant_changes_the_shape():
    """Not an artefact: which colours a surface can show depends on the light."""
    a, _ = spectral.optimal_colour_solid("D50", steps=24)
    b, _ = spectral.optimal_colour_solid("D65", steps=24)
    assert not np.allclose(np.sort(a, axis=0)[:min(len(a), len(b))],
                           np.sort(b, axis=0)[:min(len(a), len(b))])


@pytest.mark.parametrize("bad", ["D30", "tungsten", "F11"])
def test_an_unusable_illuminant_says_so(bad):
    with pytest.raises(ValueError):
        spectral.illuminant_spd(bad)


def test_a_wrongly_sized_spectrum_says_what_it_wanted():
    with pytest.raises(ValueError, match="95 samples"):
        spectral.spectrum_to_xyz(np.ones(31), "D50")


def test_too_few_steps_is_refused():
    with pytest.raises(ValueError, match="at least 8"):
        spectral.optimal_colour_solid("D50", steps=4)
