"""Every percentage the README quotes, recomputed from the demo files.

WHY THIS EXISTS. Correcting the containment test moved five figures the README
states as fact, and all five had been sitting there wrong -- every one of them
flattering, which is the convex hull's signature. Nobody noticed, because a
number in prose is checked by whoever last edited the sentence.

The same gap had already been found in `docs/index.html`, where a card claimed
76.4% against the window's 77.4%. Two places is a pattern, so the figures are
pinned here instead of trusted.

TOLERANCE. Coverage is measured by sampling with a fixed seed, so it is
repeatable to the digit -- but the README rounds, and a figure quoted to one
decimal must not fail the build because the last place moved by 0.05. Half of
the last quoted place is the allowance, and nothing more.
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


def agrees(said: float, real: float) -> None:
    """Within half of the last place the README actually quotes."""
    places = len(f"{said:.10f}".rstrip("0").split(".")[1])
    assert said == pytest.approx(real, abs=0.5 * 10 ** -places), (
        f"the README says {said}% where the code now says {real:.4f}%")


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
    profile = icc_gamut(icc)
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
    assert int(said.group(1).replace(",", "")) == round(g.volume), (
        f"the README says {said.group(1)} cubic Lab units where the shape "
        f"encloses {g.volume:,.0f}")

    dark, light = lightness_range(g)
    ends = re.search(r"blacks\s*\n?>?\s*reaching L\\\* (\d+) against a paper "
                     r"white of L\\\* (\d+)", text)
    if ends:
        assert round(dark) == int(ends.group(1))
        assert round(light) == int(ends.group(2))
