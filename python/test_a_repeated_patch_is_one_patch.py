"""A colour printed twice is one colour, measured twice.

WHAT WAS WRONG. Charts repeat patches on purpose — demo/Glossy-paper.ti3
prints 110 of its device values more than once, 243 of its 1,168 patches. The
drift comparison indexed them with `setdefault`, so the FIRST of each won and
the rest were discarded. Two costs, and the second is the serious one:

  * the comparison ran on 1,035 patches of 1,168;
  * the answer depended on the ORDER OF THE FILE. Shuffling the second chart
    moved the average from 0.7652 to 0.7683 and the worst from 2.5639 to
    2.6526 — a chart re-saved in another order was a different reading.

Averaging the repeats is what they are printed for: every patch counts, the
order cannot matter, and the instrument's own noise is halved where a colour
was read twice.
"""
import copy
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


def _read(name):
    import ti3gamut
    where = _DEMO / f"{name}.ti3"
    if not where.is_file():
        pytest.skip("no demo charts")
    return ti3gamut.read_measurement(where)


def test_the_chart_really_does_repeat_patches():
    """Otherwise everything below is a test about nothing."""
    m = _read("Glossy-paper")
    dev = np.round(np.asarray(m.device, float), 5)
    _seen, counts = np.unique(dev, axis=0, return_counts=True)
    assert (counts > 1).sum() >= 50, (
        "this chart no longer repeats patches, so the case has evaporated")


def test_the_answer_does_not_depend_on_the_order_of_the_file():
    import ti3gamut
    before, after = _read("Glossy-paper"), _read("Glossy-paper-months-later")
    straight = ti3gamut.compare_measurements(before, after)
    rng = np.random.default_rng(7)
    order = rng.permutation(len(np.asarray(after.lab)))
    mixed = copy.deepcopy(after)
    for field in ("lab", "device"):
        object.__setattr__(mixed, field, np.asarray(getattr(after, field))[order])
    shuffled = ti3gamut.compare_measurements(before, mixed)
    assert abs(shuffled.average - straight.average) < 1e-9, (
        f"shuffling the second chart moved the average from "
        f"{straight.average:.4f} to {shuffled.average:.4f}")
    assert abs(shuffled.worst - straight.worst) < 1e-9, (
        f"shuffling moved the worst from {straight.worst:.4f} to "
        f"{shuffled.worst:.4f}")


def test_two_readings_of_one_colour_are_averaged_not_dropped():
    """Built so the right answer is arithmetic: one colour, read as 4 and as 6,
    against the same colour read as 5 and 5. Averaged, the pair is 5 against 5
    and nothing has moved. Taking the first of each says it moved by one."""
    import ti3gamut
    from ti3gamut import Measurement
    device = np.array([[10.0, 20.0, 30.0], [10.0, 20.0, 30.0],
                       [40.0, 50.0, 60.0]])
    one = Measurement(name="one", device=device, instrument="made up",
                      n_patches=3,
                      lab=np.array([[50.0, 4.0, 0.0], [50.0, 6.0, 0.0],
                                    [70.0, 0.0, 0.0]]))
    two = Measurement(name="two", device=device, instrument="made up",
                      n_patches=3,
                      lab=np.array([[50.0, 5.0, 0.0], [50.0, 5.0, 0.0],
                                    [70.0, 0.0, 0.0]]))
    got = ti3gamut.compare_measurements(one, two)
    assert got.worst < 1e-6, (
        f"the repeated colour averages to the same place in both, so nothing "
        f"moved; it reports {got.worst:.4f}")
