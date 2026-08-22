"""Both lids of a pair are remembered at once, whatever the middle is.

WHAT WAS WRONG. The cache key held the middle. In CIELAB both shapes of a pair
share one middle — (50, 0, 0) — so the key matched and the store held both. In
any other space the middle is the OTHER shape's own centroid, which is a
different point for each of the two, so every call took the "not my key"
branch and emptied the store the other had just filled.

Measured, six asks alternating between the two shapes of one pair:

    CIELAB     close_the_cut ran 2 times   1.59 s
    CIE XYZ    close_the_cut ran 6 times   4.65 s

A fade drag outside Lab rebuilt both lids on every step of the drag.

The middle is kept WITH the answer instead, so it is still part of the
question — asking about a different middle must never hand back the lid built
for another one, which is the fault the key was protecting against.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


@pytest.fixture(scope="module")
def a_cut_pair():
    import ti3gamut
    from gamutview import build_gamut
    # FAR ENOUGH APART TO BE CAPPED AT ALL: two readings of one paper are
    # 0.535 Lab apart and are refused now (ti3gamut.TOO_CLOSE_TO_CLOSE).
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                           / "scripts"))
    import make_awkward_shapes
    import tempfile
    folder = pathlib.Path(tempfile.mkdtemp(prefix="apart-"))
    make_awkward_shapes.make(folder)
    made = [(n, build_gamut(np.asarray(
        ti3gamut.read_measurement(folder / f"{n}.ti3").lab, float),
        input_space="lab")) for n in ("two-lobes", "ball")]
    out, _s, stands, _l = ti3gamut.recut_where_they_part(made)
    return [(made[0][0], out[0][1]), (made[1][0], out[1][1])], stands


def _counting(monkeypatch):
    import gamutview
    real = gamutview.close_the_cut
    calls = []

    def counted(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(gamutview, "close_the_cut", counted)
    return calls


def test_two_middles_do_not_evict_each_other(a_cut_pair, monkeypatch):
    """One middle per shape, which is what every space but Lab gives."""
    import ti3gamut
    cut, stands = a_cut_pair
    calls = _counting(monkeypatch)
    ti3gamut._LAST_CAP = None
    middles = {0: (50.0, 0.0, 0.0), 1: (48.0, 2.0, -3.0)}
    for _ in range(3):
        for which in (0, 1):
            ti3gamut.cap_over_the_cut(cut, stands, which, centre=middles[which])
    assert len(calls) <= 2, (
        f"six asks about two shapes rebuilt the lid {len(calls)} times; the "
        f"store is being emptied between them")


def test_a_different_middle_is_a_different_question(a_cut_pair, monkeypatch):
    """The half the key was protecting, which must survive the fix."""
    import ti3gamut
    cut, stands = a_cut_pair
    calls = _counting(monkeypatch)
    ti3gamut._LAST_CAP = None
    here = ti3gamut.cap_over_the_cut(cut, stands, 0, centre=(50.0, 0.0, 0.0))
    there = ti3gamut.cap_over_the_cut(cut, stands, 0, centre=(52.0, 1.0, -1.0))
    assert len(calls) == 2, "the second middle was answered from the first"
    if here is not None and there is not None:
        one, two = np.asarray(here[0]), np.asarray(there[0])
        # A different corner COUNT is already proof they are different lids;
        # comparing values would raise on the shape mismatch, which is how
        # this first failed.
        different = one.shape != two.shape or not np.allclose(one, two)
        assert different, ("two middles gave the very same lid, so one of "
                           "them is not the lid for its own question")


def test_the_same_question_twice_is_answered_once(a_cut_pair, monkeypatch):
    """Otherwise there is no cache at all and the measurement above is empty."""
    import ti3gamut
    cut, stands = a_cut_pair
    calls = _counting(monkeypatch)
    ti3gamut._LAST_CAP = None
    for _ in range(3):
        ti3gamut.cap_over_the_cut(cut, stands, 0, centre=(50.0, 0.0, 0.0))
    assert len(calls) == 1, f"asked the same thing three times, built {len(calls)}"
