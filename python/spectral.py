"""The boundary of what the eye can see — the spectral locus.

A port of the part of ``spectra2colors.m`` that a gamut view needs: turn a
spectrum into XYZ, and build the surface enclosing **every colour a human eye
can perceive**, so a printer's gamut can be shown inside it.

WHY THIS IS WORTH SEEING
------------------------
Comparing a printer against sRGB or AdobeRGB answers "how does this compare to
a working space". Comparing it against the *visible* boundary answers a more
honest question: **how much of what you can see can this paper hold?** The
answer is humbling for every printer ever made, and it is the right frame for
deciding whether a gamut is disappointing or simply normal.

WHAT IT IS, EXACTLY
-------------------
The **spectral locus** is the set of XYZ values of pure single-wavelength
lights. Real colours are mixtures, so every colour the eye can see lies inside
the cone spanned by those pure lights — the *object-colour solid* under a
chosen illuminant. That solid is what this builds: for each of many wavelength
bands, the reflectance that is 1 inside the band and 0 outside is the most
saturated real surface colour possible there ("optimal colours", the
MacAdam limits). Their convex hull is the boundary of every colour a reflective
surface can have under that light.

That last point matters and is easy to get wrong: this is the limit for
**surface colours under an illuminant**, which is the right comparison for a
print. It is not the (much larger) limit for self-luminous colours.

COLOUR SCIENCE
--------------
* CIE 1931 2-degree standard observer, 5 nm, 360-830 nm, from the CIE tables.
* The illuminant defaults to **D50** to match print measurement, and the solid
  is normalised so a perfect white reflector has Y = 1 — the same scale
  ``build_gamut`` expects.
* Changing the illuminant changes the shape. That is real, not an artefact:
  which colours a surface can show depends on the light falling on it.
"""
from __future__ import annotations

import numpy as np

__all__ = ["CIE_1931_2DEG", "wavelengths", "spectrum_to_xyz",
           "illuminant_spd", "optimal_colour_solid"]

#: CIE 1931 2-degree standard observer, (nm, x-bar, y-bar, z-bar) at 5 nm.
CIE_1931_2DEG: tuple[tuple[int, float, float, float], ...] = (
    (360, 0.000130, 0.000004, 0.000606),
    (365, 0.000232, 0.000007, 0.001086),
    (370, 0.000415, 0.000012, 0.001946),
    (375, 0.000742, 0.000022, 0.003486),
    (380, 0.001368, 0.000039, 0.006450),
    (385, 0.002236, 0.000064, 0.010550),
    (390, 0.004243, 0.000120, 0.020050),
    (395, 0.007650, 0.000217, 0.036210),
    (400, 0.014310, 0.000396, 0.067850),
    (405, 0.023190, 0.000640, 0.110200),
    (410, 0.043510, 0.001210, 0.207400),
    (415, 0.077630, 0.002180, 0.371300),
    (420, 0.134380, 0.004000, 0.645600),
    (425, 0.214770, 0.007300, 1.039050),
    (430, 0.283900, 0.011600, 1.385600),
    (435, 0.328500, 0.016840, 1.622960),
    (440, 0.348280, 0.023000, 1.747060),
    (445, 0.348060, 0.029800, 1.782600),
    (450, 0.336200, 0.038000, 1.772110),
    (455, 0.318700, 0.048000, 1.744100),
    (460, 0.290800, 0.060000, 1.669200),
    (465, 0.251100, 0.073900, 1.528100),
    (470, 0.195360, 0.090980, 1.287640),
    (475, 0.142100, 0.112600, 1.041900),
    (480, 0.095640, 0.139020, 0.812950),
    (485, 0.057950, 0.169300, 0.616200),
    (490, 0.032010, 0.208020, 0.465180),
    (495, 0.014700, 0.258600, 0.353300),
    (500, 0.004900, 0.323000, 0.272000),
    (505, 0.002400, 0.407300, 0.212300),
    (510, 0.009300, 0.503000, 0.158200),
    (515, 0.029100, 0.608200, 0.111700),
    (520, 0.063270, 0.710000, 0.078250),
    (525, 0.109600, 0.793200, 0.057250),
    (530, 0.165500, 0.862000, 0.042160),
    (535, 0.225750, 0.914850, 0.029840),
    (540, 0.290400, 0.954000, 0.020300),
    (545, 0.359700, 0.980300, 0.013400),
    (550, 0.433450, 0.994950, 0.008750),
    (555, 0.512050, 1.000000, 0.005750),
    (560, 0.594500, 0.995000, 0.003900),
    (565, 0.678400, 0.978600, 0.002750),
    (570, 0.762100, 0.952000, 0.002100),
    (575, 0.842500, 0.915400, 0.001800),
    (580, 0.916300, 0.870000, 0.001650),
    (585, 0.978600, 0.816300, 0.001400),
    (590, 1.026300, 0.757000, 0.001100),
    (595, 1.056700, 0.694900, 0.001000),
    (600, 1.062200, 0.631000, 0.000800),
    (605, 1.045600, 0.566800, 0.000600),
    (610, 1.002600, 0.503000, 0.000340),
    (615, 0.938400, 0.441200, 0.000240),
    (620, 0.854450, 0.381000, 0.000190),
    (625, 0.751400, 0.321000, 0.000100),
    (630, 0.642400, 0.265000, 0.000050),
    (635, 0.541900, 0.217000, 0.000030),
    (640, 0.447900, 0.175000, 0.000020),
    (645, 0.360800, 0.138200, 0.000010),
    (650, 0.283500, 0.107000, 0.000000),
    (655, 0.218700, 0.081600, 0.000000),
    (660, 0.164900, 0.061000, 0.000000),
    (665, 0.121200, 0.044580, 0.000000),
    (670, 0.087400, 0.032000, 0.000000),
    (675, 0.063600, 0.023200, 0.000000),
    (680, 0.046770, 0.017000, 0.000000),
    (685, 0.032900, 0.011920, 0.000000),
    (690, 0.022700, 0.008210, 0.000000),
    (695, 0.015840, 0.005723, 0.000000),
    (700, 0.011359, 0.004102, 0.000000),
    (705, 0.008111, 0.002929, 0.000000),
    (710, 0.005790, 0.002091, 0.000000),
    (715, 0.004109, 0.001484, 0.000000),
    (720, 0.002899, 0.001047, 0.000000),
    (725, 0.002049, 0.000740, 0.000000),
    (730, 0.001440, 0.000520, 0.000000),
    (735, 0.001000, 0.000361, 0.000000),
    (740, 0.000690, 0.000249, 0.000000),
    (745, 0.000476, 0.000172, 0.000000),
    (750, 0.000332, 0.000120, 0.000000),
    (755, 0.000235, 0.000085, 0.000000),
    (760, 0.000166, 0.000060, 0.000000),
    (765, 0.000117, 0.000042, 0.000000),
    (770, 0.000083, 0.000030, 0.000000),
    (775, 0.000059, 0.000021, 0.000000),
    (780, 0.000042, 0.000015, 0.000000),
    (785, 0.000029, 0.000011, 0.000000),
    (790, 0.000021, 0.000007, 0.000000),
    (795, 0.000015, 0.000005, 0.000000),
    (800, 0.000010, 0.000004, 0.000000),
    (805, 0.000007, 0.000003, 0.000000),
    (810, 0.000005, 0.000002, 0.000000),
    (815, 0.000004, 0.000001, 0.000000),
    (820, 0.000003, 0.000001, 0.000000),
    (825, 0.000002, 0.000001, 0.000000),
    (830, 0.000001, 0.000000, 0.000000),
)

_TABLE = np.array(CIE_1931_2DEG, dtype=float)


def wavelengths() -> np.ndarray:
    """The wavelengths the tables are defined on, in nm."""
    return _TABLE[:, 0].copy()


def _cmf() -> np.ndarray:
    """(N, 3) x-bar, y-bar, z-bar."""
    return _TABLE[:, 1:4]


def illuminant_spd(name: str = "D50") -> np.ndarray:
    """Relative spectral power of a CIE daylight illuminant, on our grid.

    D50 and D65 are reconstructed from the CIE daylight components S0/S1/S2
    rather than hard-coded, so any daylight temperature can be asked for as
    "D<temperature/100>" — D55 and D75 work too. "E" is the equal-energy
    illuminant, useful as a sanity check because it makes the solid symmetric.
    """
    name = name.upper()
    if name == "E":
        return np.ones(len(_TABLE))
    if not (name.startswith("D") and name[1:].isdigit()):
        raise ValueError(f"unknown illuminant {name!r}; try D50, D65 or E")
    cct = float(name[1:]) * 100.0
    if not 4000.0 <= cct <= 25000.0:
        raise ValueError(f"{name} is outside the CIE daylight range (D40-D250)")
    # CIE 15: chromaticity of a daylight of this correlated colour temperature.
    if cct <= 7000.0:
        x = (-4.6070e9 / cct ** 3 + 2.9678e6 / cct ** 2 + 0.09911e3 / cct
             + 0.244063)
    else:
        x = (-2.0064e9 / cct ** 3 + 1.9018e6 / cct ** 2 + 0.24748e3 / cct
             + 0.237040)
    y = -3.000 * x * x + 2.870 * x - 0.275
    m = 0.0241 + 0.2562 * x - 0.7341 * y
    m1 = (-1.3515 - 1.7703 * x + 5.9114 * y) / m
    m2 = (0.0300 - 31.4424 * x + 30.0717 * y) / m
    s = _DAYLIGHT_COMPONENTS
    return s[:, 0] + m1 * s[:, 1] + m2 * s[:, 2]


def spectrum_to_xyz(reflectance, illuminant="D50") -> np.ndarray:
    """XYZ of one or more reflectance spectra under *illuminant*.

    *reflectance* is (N,) or (M, N) on :func:`wavelengths`, 0..1. Normalised so
    a perfect white reflector gives Y = 1, which is the scale ``build_gamut``
    and ``xyz_to_lab`` work in.
    """
    r = np.atleast_2d(np.asarray(reflectance, dtype=float))
    if r.shape[1] != len(_TABLE):
        raise ValueError(
            f"reflectance must have {len(_TABLE)} samples (360-830 nm at 5 nm), "
            f"got {r.shape[1]}")
    spd = (illuminant_spd(illuminant) if isinstance(illuminant, str)
           else np.asarray(illuminant, dtype=float))
    cmf = _cmf()
    k = 1.0 / np.sum(spd * cmf[:, 1])          # so a white reflector has Y = 1
    xyz = k * (r * spd) @ cmf
    return xyz[0] if np.ndim(reflectance) == 1 else xyz


def optimal_colour_solid(illuminant: str = "D50", steps: int = 64):
    """The boundary of every colour a surface can show under *illuminant*.

    Returns ``(vertices, faces)`` in XYZ, ready to hand to a renderer or to
    convert to Lab. *steps* is how finely the wavelength boundaries are walked:
    64 gives a smooth solid in well under a second, 128 is smoother and slower.

    Optimal colours are the two-transition reflectances — 1 inside a band and 0
    outside, and their complements — which are the most saturated a real surface
    can be. Sweeping every start and width and hulling the result gives the
    solid. Black and white fall out of it naturally as the degenerate cases.
    """
    from scipy.spatial import ConvexHull

    if steps < 8:
        raise ValueError("steps must be at least 8 to close the solid")
    n = len(_TABLE)
    idx = np.unique(np.linspace(0, n - 1, steps).astype(int))
    spectra = [np.zeros(n), np.ones(n)]        # black and white
    for a in idx:
        for b in idx:
            if a == b:
                continue
            band = np.zeros(n)
            if a < b:
                band[a:b] = 1.0                # a normal band
            else:
                band[a:] = 1.0                 # a band wrapping the ends,
                band[:b] = 1.0                 # i.e. the complement: purples
            spectra.append(band)
    xyz = spectrum_to_xyz(np.array(spectra), illuminant)
    hull = ConvexHull(xyz)
    keep = np.unique(hull.vertices)
    remap = {old: new for new, old in enumerate(keep)}
    faces = np.array([[remap[i] for i in s] for s in hull.simplices], dtype=int)
    return xyz[keep], faces


#: CIE daylight components S0, S1, S2, on our 5 nm grid (300-830 nm clipped to
#: 360-830; the CIE table stops at 830 and is zero below 300).
_DAYLIGHT_COMPONENTS = np.array([
    [61.5000, 38.0000, 5.3000],
    [65.1500, 40.2000, 5.7000],
    [68.8000, 42.4000, 6.1000],
    [66.1000, 40.4500, 4.5500],
    [63.4000, 38.5000, 3.0000],
    [64.6000, 36.7500, 2.1000],
    [65.8000, 35.0000, 1.2000],
    [80.3000, 39.2000, 0.0500],
    [94.8000, 43.4000, -1.1000],
    [99.8000, 44.8500, -0.8000],
    [104.8000, 46.3000, -0.5000],
    [105.3500, 45.1000, -0.6000],
    [105.9000, 43.9000, -0.7000],
    [101.3500, 40.5000, -0.9500],
    [96.8000, 37.1000, -1.2000],
    [105.3500, 36.9000, -1.9000],
    [113.9000, 36.7000, -2.6000],
    [119.7500, 36.3000, -2.7500],
    [125.6000, 35.9000, -2.9000],
    [125.5500, 34.2500, -2.8500],
    [125.5000, 32.6000, -2.8000],
    [123.4000, 30.2500, -2.7000],
    [121.3000, 27.9000, -2.6000],
    [121.3000, 26.1000, -2.6000],
    [121.3000, 24.3000, -2.6000],
    [117.4000, 22.2000, -2.2000],
    [113.5000, 20.1000, -1.8000],
    [113.3000, 18.1500, -1.6500],
    [113.1000, 16.2000, -1.5000],
    [111.9500, 14.7000, -1.4000],
    [110.8000, 13.2000, -1.3000],
    [108.6500, 10.9000, -1.2500],
    [106.5000, 8.6000, -1.2000],
    [107.6500, 7.3500, -1.1000],
    [108.8000, 6.1000, -1.0000],
    [107.0500, 5.1500, -0.7500],
    [105.3000, 4.2000, -0.5000],
    [104.8500, 3.0500, -0.4000],
    [104.4000, 1.9000, -0.3000],
    [102.2000, 0.9500, -0.1500],
    [100.0000, 0.0000, 0.0000],
    [98.0000, -0.8000, 0.1000],
    [96.0000, -1.6000, 0.2000],
    [95.5500, -2.5500, 0.3500],
    [95.1000, -3.5000, 0.5000],
    [92.1000, -3.5000, 1.3000],
    [89.1000, -3.5000, 2.1000],
    [89.8000, -4.6500, 2.6500],
    [90.5000, -5.8000, 3.2000],
    [90.4000, -6.5000, 3.6500],
    [90.3000, -7.2000, 4.1000],
    [89.3500, -7.9000, 4.4000],
    [88.4000, -8.6000, 4.7000],
    [86.2000, -9.0500, 4.9000],
    [84.0000, -9.5000, 5.1000],
    [84.5500, -10.2000, 5.9000],
    [85.1000, -10.9000, 6.7000],
    [83.5000, -10.8000, 7.0000],
    [81.9000, -10.7000, 7.3000],
    [82.2500, -11.3500, 7.9500],
    [82.6000, -12.0000, 8.6000],
    [83.7500, -13.0000, 9.2000],
    [84.9000, -14.0000, 9.8000],
    [83.1000, -13.8000, 10.0000],
    [81.3000, -13.6000, 10.2000],
    [76.6000, -12.8000, 9.2500],
    [71.9000, -12.0000, 8.3000],
    [73.1000, -12.6500, 8.9500],
    [74.3000, -13.3000, 9.6000],
    [75.3500, -13.1000, 9.0500],
    [76.4000, -12.9000, 8.5000],
    [69.8500, -11.7500, 7.7500],
    [63.3000, -10.6000, 7.0000],
    [67.5000, -11.1000, 7.3000],
    [71.7000, -11.6000, 7.6000],
    [74.3500, -11.9000, 7.8000],
    [77.0000, -12.2000, 8.0000],
    [71.1000, -11.2000, 7.3500],
    [65.2000, -10.2000, 6.7000],
    [56.4500, -9.0000, 5.9500],
    [47.7000, -7.8000, 5.2000],
    [58.1500, -9.5000, 6.3000],
    [68.6000, -11.2000, 7.4000],
    [66.8000, -10.8000, 7.1000],
    [65.0000, -10.4000, 6.8000],
    [65.5000, -10.5000, 6.9000],
    [66.0000, -10.6000, 7.0000],
    [63.5000, -10.1500, 6.7000],
    [61.0000, -9.7000, 6.4000],
    [57.1500, -9.0000, 5.9500],
    [53.3000, -8.3000, 5.5000],
    [56.1000, -8.8000, 5.8000],
    [58.9000, -9.3000, 6.1000],
    [60.4000, -9.5500, 6.3000],
    [61.9000, -9.8000, 6.5000],
], dtype=float)
