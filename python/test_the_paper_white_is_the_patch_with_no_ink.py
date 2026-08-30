"""The paper's white is the patch printed with no ink -- never merely the
brightest reading in the file.

``read_ti3(relative=True)`` divides every patch by one chosen patch and calls
that one the paper. It used to choose by the greatest Y and never look at what
was printed to get it. On a reflective print those are the same patch, so this
never showed in the field -- but a file that says otherwise turned the whole
measurement inside out in silence, which is the one failure this application
must not have:

    every patch moved   mean 53.33 dE2000, max 87.20
    b* of the real white           -998.31
    gamut volume        5,111,329 -> 26,494,611   (+418%)

and the panel went on calling that white "neutral".
"""
import pathlib

import numpy as np
import pytest

import ti3gamut


HEAD = """CTI3

DESCRIPTOR "A made-up measurement"
ORIGINATOR "this test"
DEVICE_CLASS "OUTPUT"
COLOR_REP "iRGB_XYZ"
TARGET_INSTRUMENT "none, this file was written by a test"

NUMBER_OF_FIELDS 7
BEGIN_DATA_FORMAT
SAMPLE_ID SAMPLE_LOC RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z
END_DATA_FORMAT

NUMBER_OF_SETS {n}
BEGIN_DATA
{rows}
END_DATA
"""


def _write(tmp_path, patches, name="made-up.ti3"):
    """patches: (R, G, B, X, Y, Z), device 0..100, XYZ 0..100."""
    rows = "\n".join(
        f'{i + 1} "P{i + 1}" ' + " ".join(f"{v:.6f}" for v in p)
        for i, p in enumerate(patches))
    path = tmp_path / name
    path.write_text(HEAD.format(n=len(patches), rows=rows))
    return path


#: A file whose brightest patch is NOT the blank one: yellow read back
#: brighter than the paper. Physically impossible on a reflective print,
#: which is exactly why nothing downstream would have questioned it.
LYING = [
    (100.0, 100.0, 100.0, 96.42, 100.00, 82.52),   # the paper, no ink
    (100.0, 100.0, 0.0, 90.00, 120.00, 5.00),      # yellow, and "brighter"
    (0.0, 0.0, 0.0, 2.00, 2.00, 1.60),             # black
    (100.0, 0.0, 0.0, 40.00, 22.00, 3.00),         # red
]


def test_the_blank_patch_is_the_white_even_when_another_patch_reads_brighter(
        tmp_path):
    path = _write(tmp_path, LYING)

    # ⚠ THE FIXTURE MUST ACTUALLY POSE THE QUESTION. A measurement whose
    # brightest patch already is the blank one cannot tell the two rules
    # apart, and a test that cannot see the fault looks exactly like one
    # that found nothing wrong.
    xyz = np.array([p[3:] for p in LYING])
    assert int(np.argmax(xyz[:, 1])) != 0, (
        "this fixture no longer separates the two rules")

    m = ti3gamut.read_ti3(path, relative=True)
    assert m.white_from == "the patch printed with no ink"

    # Row 0 is the paper, so the paper lands on L*100 and stays neutral.
    assert m.lab[0][0] == pytest.approx(100.0, abs=0.01)
    assert abs(m.lab[0][1]) < 0.5 and abs(m.lab[0][2]) < 0.5, (
        f"the paper came out {m.lab[0]}, which is not a white")

    # And the old rule really would have wrecked it -- pinned so that
    # deleting the guard fails here rather than passing quietly.
    yellow = ti3gamut.read_ti3(path, relative=True)
    assert yellow.lab[1][0] > 100.0, (
        "yellow reads brighter than the paper, and saying so is honest")


def test_a_file_with_no_blank_patch_says_which_patch_it_used(tmp_path):
    """A chart that never printed the paper. The greatest value present is
    then NOT a white, and claiming it is would be the very mistake the
    guard exists to refuse -- so it falls back and names the fallback."""
    partial = [
        (80.0, 80.0, 80.0, 60.00, 63.00, 52.00),
        (80.0, 0.0, 0.0, 30.00, 17.00, 2.00),
        (0.0, 0.0, 0.0, 2.00, 2.00, 1.60),
    ]
    m = ti3gamut.read_ti3(_write(tmp_path, partial), relative=True)
    assert m.white_from.startswith("the lightest patch")
    assert "no patch here is at full scale" in m.white_from


def test_read_absolutely_the_paper_is_still_named_and_left_where_it_is(
        tmp_path):
    """Reading absolutely does not divide by the white, but the window still
    has to be able to SAY which patch the paper is -- otherwise it falls back
    to the lightest one and calls a yellow the sheet."""
    m = ti3gamut.read_ti3(_write(tmp_path, LYING), relative=False)
    assert m.white_from == "the patch printed with no ink"
    # Left where the instrument found it, not moved to L*100.
    assert m.white_lab is not None
    assert m.white_lab[0] == pytest.approx(m.lab[0][0], abs=1e-9)
    # On a real paper that is plainly below 100: the instrument saw what it
    # saw, and reading absolutely does not move it.
    demo = pathlib.Path(__file__).resolve().parent.parent / "demo"
    real = ti3gamut.read_ti3(demo / "Glossy-paper.ti3", relative=False)
    assert 90.0 < real.white_lab[0] < 97.0, real.white_lab
    assert real.white_lab[0] == pytest.approx(max(real.lab[:, 0]), abs=0.01)


def test_the_greatest_value_present_is_not_good_enough(tmp_path):
    """⚠ THE MUTANT THIS SUITE LET THROUGH. A review mutated the rule from
    "at full scale" to "at the greatest value present" -- the exact bug the
    reader's own comment spends a paragraph refusing -- and only ONE test
    noticed, on a string. So here is the case that separates them by the
    numbers: a chart whose channels top out at different places, where the
    only patch at every column's maximum is a dark one."""
    odd = [
        (80.0, 90.0, 70.0, 6.00, 5.00, 4.00),    # every column's max, and DARK
        (80.0, 60.0, 60.0, 55.00, 60.00, 50.00),  # the lightest thing here
        (0.0, 0.0, 0.0, 2.00, 2.00, 1.60),
    ]
    m = ti3gamut.read_ti3(_write(tmp_path, odd), relative=True)
    assert m.white_from.startswith("the lightest patch"), (
        "no patch here is at full scale, so none of them is the paper")
    # Taking the column maxima instead would divide by Y 5.00 rather than
    # 60.00 and throw the whole file twelve times too light.
    assert m.lab[1][0] == pytest.approx(100.0, abs=0.01)
    assert m.lab[0][0] < 60.0, (
        f"the dark patch came out at L*{m.lab[0][0]:.0f}: the file was "
        "divided by the wrong patch")


def test_a_white_that_read_no_light_at_all_does_not_poison_the_file(tmp_path):
    """Found by a review of the guard itself. Dividing by the chosen patch is
    the next thing that happens, so a full-scale patch reading Y of zero
    turned every patch in the file to NaN -- where the old rule could not,
    because it divided by the greatest Y."""
    dead = [
        (100.0, 100.0, 100.0, 0.0, 0.0, 0.0),     # the only blank, and dead
        (100.0, 0.0, 0.0, 40.00, 22.00, 3.00),
        (0.0, 100.0, 0.0, 30.00, 50.00, 12.00),
        (0.0, 0.0, 0.0, 2.00, 2.00, 1.60),
    ]
    m = ti3gamut.read_ti3(_write(tmp_path, dead), relative=True)
    assert np.isfinite(m.lab).all(), "the file was turned to NaN"
    assert "reads as no light at all" in m.white_from
    assert m.lab[2][0] == pytest.approx(100.0, abs=0.01), (
        "the lightest patch that DID read something is the stand-in")


def test_a_file_where_nothing_read_any_light_says_so_instead_of_dividing(
        tmp_path):
    black = [(100.0, 100.0, 100.0, 0.0, 0.0, 0.0),
             (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]
    with pytest.raises(ValueError) as caught:
        ti3gamut.read_ti3(_write(tmp_path, black), relative=True)
    assert "reflected any light" in str(caught.value)


def test_the_words_suit_the_kind_of_device(tmp_path):
    """A screen has no ink and a scanner prints nothing, so "the patch
    printed with no ink" is wrong for both -- and the FALLBACK must not
    accuse an ordinary chart that simply never printed a blank."""
    for kind, expected in (("OUTPUT", "printed with no ink"),
                           ("DISPLAY", "driven to full white"),
                           ("INPUT", "at full scale on every channel")):
        path = _write(tmp_path, LYING, name=f"{kind}.ti3")
        path.write_text(path.read_text().replace(
            'DEVICE_CLASS "OUTPUT"', f'DEVICE_CLASS "{kind}"'))
        m = ti3gamut.read_ti3(path, relative=True)
        assert expected in m.white_from, f"{kind}: {m.white_from!r}"
    partial = [(80.0, 80.0, 80.0, 60.00, 63.00, 52.00),
               (0.0, 0.0, 0.0, 2.00, 2.00, 1.60),
               (80.0, 0.0, 0.0, 30.00, 17.00, 2.00)]
    m = ti3gamut.read_ti3(_write(tmp_path, partial, name="ordinary.ti3"),
                          relative=True)
    assert "no patch here is at full scale" in m.white_from
    assert "does not say what was printed" not in m.white_from, (
        "an ordinary chart that never printed a blank is not malformed, and "
        "must not be told that it is")


def test_the_paper_is_named_by_its_own_place_not_by_the_lightest_patch(
        tmp_path):
    """`paper_white()` argued that the lightest vertex IS the paper. Held
    against a file whose brightest patch is a yellow it reported that yellow
    as the paper -- L* 102, "very warm". `white_lab` is what tells it
    otherwise."""
    from gamutview import build_gamut, describe_white, paper_white
    m = ti3gamut.read_ti3(pathlib.Path(_write(tmp_path, LYING)), relative=True)
    g = build_gamut(m.lab, m.device, input_space="lab", space="lab")
    assert m.white_lab is not None
    assert describe_white(paper_white(g, m.white_lab)) == "neutral"
    # And the old answer is still what a caller with no measurement gets,
    # which is right for a profile: it has no patches and no paper.
    assert paper_white(g)[0] > 100.0, (
        "this fixture no longer separates the two answers")


def test_a_converted_measurement_keeps_every_field(tmp_path):
    """`read_measurement` copied five of six fields by hand and dropped the
    sixth the day it was added, so every .cxf, .txt and .mxf reported that no
    white had been chosen when one had."""
    import dataclasses
    m = ti3gamut.read_ti3(_write(tmp_path, LYING), relative=True)
    kept = dataclasses.replace(m, name="renamed")
    for field in dataclasses.fields(ti3gamut.Measurement):
        if field.name == "name":
            continue
        a, b = getattr(m, field.name), getattr(kept, field.name)
        same = (a is b) or (a == b if not isinstance(a, np.ndarray)
                            else np.array_equal(a, b))
        assert same, f"{field.name} was not carried over"


def test_every_real_measurement_that_ships_picks_its_blank_patch():
    """The guard must be a no-op on genuine files: on a reflective print the
    paper always is the brightest thing, so nothing a user already sees may
    move."""
    from pathlib import Path
    demo = Path(__file__).resolve().parent.parent / "demo"
    files = sorted(demo.glob("*.ti3"))
    assert len(files) >= 2, "no shipped measurements to check against"
    for path in files:
        m = ti3gamut.read_ti3(path, relative=True)
        assert m.white_from == "the patch printed with no ink", (
            f"{path.name} chose its white the fallback way")
        # And it is the same patch the old rule would have taken, so no
        # existing picture changes.
        assert m.lab[:, 0].max() == pytest.approx(100.0, abs=0.5), (
            f"{path.name}: the paper is no longer the lightest thing in it")
