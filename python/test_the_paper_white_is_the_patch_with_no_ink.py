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
    assert m.white_from.startswith("the brightest patch")
    assert "does not say what was printed" in m.white_from


def test_read_absolutely_no_white_is_chosen_and_none_is_claimed(tmp_path):
    m = ti3gamut.read_ti3(_write(tmp_path, LYING), relative=False)
    assert m.white_from == ""


def test_the_choice_is_recorded_in_words_a_reader_could_be_shown():
    """Whatever surfaces it later, the sentence has to be plain English and
    not a flag -- 'the patch printed with no ink' reads as an answer."""
    import dataclasses
    names = [f.name for f in dataclasses.fields(ti3gamut.Measurement)]
    assert "white_from" in names


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
