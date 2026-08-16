"""Every percentage the README quotes, recomputed from the demo files.

WHY THIS EXISTS. Correcting the containment test moved five figures the README
states as fact, and all five had been sitting there wrong -- every one of them
flattering, which is the convex hull's signature. Nobody noticed, because a
number in prose is checked by whoever last edited the sentence.

The same gap had already been found in `docs/index.html`, where a card claimed
76.4% against the window's 77.4%. Two places is a pattern, so the figures are
pinned here instead of trusted.

TOLERANCE, AND WHY IT IS NOT TIGHTER. The first version of this allowed half
of the last place the README quotes, on the reasoning that coverage uses a
fixed seed and so repeats to the digit. It does -- on one machine. It broke
the release build within minutes of being pushed, because the numbers are not
the same on another:

    paper inside sRGB     75.9% here    76.01% on the Linux builder
    both can print        77.4% here    77.63%
    the demo volume     702,327 here   702,291

The shapes themselves differ. `build_gamut` triangulates each face of the
device cube with Qhull, and Qhull resolves a flat or near-flat run of points
differently between builds -- so the surface has the same points and slightly
different triangles, and everything measured from it moves a little. 36 cubic
Lab units in 702,327 is 0.005%.

So the allowance has to separate a figure that has gone STALE from one that is
merely being measured on a different machine. Measured, those are far apart:
the staleness this test was written after ran from 0.8 to 1.8 percentage
points, and the spread between two machines is at most 0.25. Half a point sits
cleanly between them.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def demo():
    """The two demo papers, sRGB and the demo profile, built as the app does."""
    import sys
    sys.path.insert(0, str(REPO / "python"))
    from ti3gamut import read_ti3
    from references import reference_gamut
    from gamutview import build_gamut

    shapes = {}
    for name in ("Glossy-paper", "Matte-paper"):
        m = read_ti3(REPO / "demo" / f"{name}.ti3")
        shapes[name] = build_gamut(m.lab, m.device, space="lab",
                                   input_space="lab")
    shapes["sRGB"] = reference_gamut("sRGB")
    return shapes


def quoted(pattern: str) -> float:
    """The number the README states, or a failure naming the missing line."""
    text = (REPO / "README.md").read_text(errors="replace")
    found = re.search(pattern, text)
    assert found, f"the README no longer contains a line matching {pattern!r}"
    return float(found.group(1))


#: How far the measurement may sit from the quoted figure for reasons that are
#: nobody's fault. Measured between this project's machines: 0.25 points. The
#: extra is headroom for a third one.
#:
#: THIS IS NOT THE WHOLE ALLOWANCE, and leaving it as the whole allowance
#: broke the build a second time. A figure written as "77%" is a rounded
#: figure: it is quoted correctly anywhere from 76.5 to 77.5, so half of the
#: last place it is quoted TO has to be added on top. Windows measured 77.63
#: against a README saying 77% -- 0.63 apart, and entirely correct.
MACHINES_DIFFER_BY = 0.35


def rounding_of(said: float) -> float:
    """Half of the last place the sentence actually quotes to."""
    text = f"{said:.10f}".rstrip("0")
    places = len(text.split(".")[1]) if "." in text and text.split(".")[1] else 0
    return 0.5 * 10 ** -places


def agrees(said: float, real: float) -> None:
    room = rounding_of(said) + MACHINES_DIFFER_BY
    assert said == pytest.approx(real, abs=room), (
        f"the README says {said}% where the code now says {real:.4f}% -- "
        f"more than {room:.2f} apart, which is staleness rather than rounding "
        f"or the difference between two machines")


def test_the_paper_against_srgb_both_ways(demo):
    from gamutview import coverage
    agrees(quoted(r"([\d.]+)% of what this paper can print also fits inside sRGB"),
           100 * coverage(demo["Glossy-paper"], demo["sRGB"])[0])
    agrees(quoted(r"([\d.]+)% of sRGB fits inside this paper"),
           100 * coverage(demo["sRGB"], demo["Glossy-paper"])[0])


def test_how_alike_the_two_papers_are(demo):
    """The one that reads 'both can print N% of everything either one can' --
    and the one that was wrong twice over, since `shared_volume` used hull
    volumes AND stripped the faces off before measuring coverage."""
    from gamutview import shared_volume
    agrees(quoted(r"Both can print ([\d.]+)% of everything either one can"),
           100 * shared_volume(demo["Glossy-paper"], demo["Matte-paper"])[2])


def test_the_measurement_against_its_own_profile(demo):
    from gamutview import coverage
    from references import icc_gamut
    icc = REPO / "demo" / "Glossy-paper.icc"
    if not icc.exists():
        pytest.skip("the demo profile is not in this checkout")
    try:
        profile = icc_gamut(icc)
    except ValueError as why:
        # READING AN ICC PROFILE NEEDS ArgyllCMS, and the build machines do
        # not have it. Skipping is right: the figure is still checked wherever
        # somebody can actually read a profile, and a test that cannot run is
        # not a test that failed.
        pytest.skip(f"cannot read the demo profile here: {why}")
    agrees(quoted(r"([\d.]+)% of what the measurement can print also fits "
                  r"inside the profile"),
           100 * coverage(demo["Glossy-paper"], profile)[0])
    agrees(quoted(r"([\d.]+)% of the profile fits inside the measurement"),
           100 * coverage(profile, demo["Glossy-paper"])[0])


def test_the_volume_and_the_two_ends_of_the_demo_paper(demo):
    """The figures under the very first picture, which every reader sees."""
    from gamutview import lightness_range
    text = (REPO / "README.md").read_text(errors="replace")
    g = demo["Glossy-paper"]

    said = re.search(r"([\d,]+) cubic Lab units", text)
    assert said, "the README no longer quotes the demo volume"
    # A RELATIVE ALLOWANCE, because the volume moves with the triangulation
    # too -- 36 cubic units between two machines, which is 0.005%. A tenth of
    # a percent is far inside that and far outside any real staleness.
    quoted_volume = int(said.group(1).replace(",", ""))
    assert quoted_volume == pytest.approx(g.volume, rel=0.001), (
        f"the README says {said.group(1)} cubic Lab units where the shape "
        f"encloses {g.volume:,.0f}")

    dark, light = lightness_range(g)
    ends = re.search(r"blacks\s*\n?>?\s*reaching L\\\* (\d+) against a paper "
                     r"white of L\\\* (\d+)", text)
    if ends:
        assert round(dark) == int(ends.group(1))
        assert round(light) == int(ends.group(2))
