"""Which colour families moved, and which way.

WHY THESE TESTS LOOK LIKE THIS. The output of this feature is a handful of
English sentences, and a sentence like "yellows drifted toward red" is exactly
as plausible when it is wrong as when it is right. There is no picture beside
it to contradict it and no reader who can check it -- which is the whole reason
somebody wants it: they are going to paste it into an email and be believed.

So almost every case here MOVES COLOURS A KNOWN AMOUNT IN A KNOWN DIRECTION and
asks whether the report noticed. Three real faults were found this way and none
of them looked wrong on screen:

  * a family reported as heading toward itself, because its own centre lay a
    fraction of a degree "ahead" of its mean hue;
  * ΔE 8.2 of pure noise named "toward the yellows", because the mean of a
    cancelling set is small and the largest of three small numbers still wins;
  * one unreadable patch producing "nan ΔE" beside a confidently named
    direction.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from gamutview import (AGREEMENT, BOUNDARY_DEGREES, HUE_FAMILIES,
                       NEUTRAL_CHROMA, QUIET_DE, family_drift)


def ring(centre_deg, n=60, chroma=40.0, light=50.0, spread=8.0, seed=1):
    """A family's worth of colours around one hue centre."""
    rng = np.random.default_rng(seed)
    ang = np.radians(centre_deg + rng.uniform(-spread, spread, n))
    c = chroma + rng.uniform(-5, 5, n)
    return np.column_stack([np.full(n, light), c * np.cos(ang),
                            c * np.sin(ang)])


def rotated(lab, degrees):
    """The same colours, turned that far round the hue circle."""
    th = np.radians(degrees)
    rot = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    out = lab.copy()
    out[:, 1:] = lab[:, 1:] @ rot.T
    return out


def row(rows, name):
    return next(r for r in rows if r.name == name)


# --------------------------------------------------------------------------
# Which way it went — the answers known in advance
# --------------------------------------------------------------------------

def test_a_rotation_is_named_by_the_family_it_is_heading_for():
    """A red turned toward the yellows is heading for the yellows.

    IT REPORTED "toward the reds" until this test existed. A family's mean hue
    sits near its own centre but not on it, so for half of them their own
    centre lies a fraction of a degree ahead and wins by being nearest. The
    same colours turned the other way came out right, which is exactly why one
    example proves nothing.
    """
    reds = ring(0.0)
    assert row(family_drift(reds, rotated(reds, 8.0)),
               "reds").toward == "toward the yellows"


def test_the_same_rotation_the_other_way_names_the_other_neighbour():
    reds = ring(0.0)
    assert row(family_drift(reds, rotated(reds, -8.0)),
               "reds").toward == "toward the magentas"


def test_every_family_can_be_turned_both_ways_and_is_never_its_own_target():
    """The fault above was found in one family; it could have been in any."""
    names = [n for n, _c in HUE_FAMILIES]
    for name, centre in HUE_FAMILIES:
        here = ring(centre)
        for degrees in (7.0, -7.0):
            got = row(family_drift(here, rotated(here, degrees)), name)
            assert got.toward.startswith("toward the "), (name, degrees, got)
            went_to = got.toward.removeprefix("toward the ")
            assert went_to != name, f"{name} was reported as heading for itself"
            assert went_to in names


def test_losing_chroma_is_a_move_toward_grey_not_a_hue_move():
    """The request that prompted this asked for "tending toward gray" in so
    many words, so a report that could only name hues would not answer it."""
    greens = ring(150.0)
    faded = greens.copy()
    faded[:, 1:] *= 0.85
    assert row(family_drift(greens, faded), "greens").toward == "toward grey"


def test_gaining_chroma_is_named_the_other_way():
    greens = ring(150.0)
    fuller = greens.copy()
    fuller[:, 1:] *= 1.15
    assert row(family_drift(greens, fuller),
               "greens").toward == "more saturated"


def test_a_pure_lightness_change_claims_nothing_about_hue():
    greens = ring(150.0)
    darker = greens.copy()
    darker[:, 0] -= 4.0
    got = row(family_drift(greens, darker), "greens")
    assert got.toward == "darker"
    assert got.also == ""
    assert got.agreement == pytest.approx(1.0)


def test_two_movements_at_once_name_the_bigger_and_mention_the_other():
    greens = ring(150.0)
    both = greens.copy()
    both[:, 1:] *= 0.80
    both[:, 0] -= 5.0
    got = row(family_drift(greens, both), "greens")
    assert {got.toward, got.also} == {"toward grey", "darker"}


# --------------------------------------------------------------------------
# Declining to answer, which is most of the value
# --------------------------------------------------------------------------

def test_a_family_that_did_not_move_says_so_rather_than_naming_a_direction():
    greens = ring(150.0)
    got = row(family_drift(greens, greens.copy()), "greens")
    assert got.toward == "" and not got.changed
    assert "stayed the same" in got.sentence


def test_a_movement_under_the_visible_line_reads_as_unchanged():
    """ΔE 1 is what the rest of this application already calls the point a
    careful eye notices, and this deliberately does not invent a second one."""
    greens = ring(150.0)
    nudged = greens.copy()
    nudged[:, 2] += 0.2
    assert not row(family_drift(greens, nudged), "greens").changed


def test_colours_that_moved_a_long_way_in_no_one_direction_are_called_mixed():
    blues = ring(270.0)
    rng = np.random.default_rng(4)
    scattered = blues + rng.normal(0, 6.0, blues.shape)
    got = row(family_drift(blues, scattered), "blues")
    assert got.toward == "mixed"
    assert got.agreement < AGREEMENT


def test_noise_is_never_dressed_up_as_a_direction():
    """THE FAULT THIS CAUGHT, which no amount of looking would have found.

    Movements that cancel leave a mean near zero on every axis. The report
    then named whichever of those three near-zero numbers happened to be
    largest, and printed it beside a perfectly real ΔE of 8.2. The check for
    disagreement was measured on a*/b* alone and gated behind a threshold that
    cancelling noise cannot reach; measured on all three axes there is no gate
    to slip through.
    """
    rng = np.random.default_rng(3)
    here = ring(0.0, n=80, spread=3.0)
    got = row(family_drift(here, here + rng.normal(0, 8.0, here.shape)), "reds")
    assert got.mean_de > 3.0, "the movement really is large"
    assert got.toward == "mixed"
    assert not got.certain


def test_one_patch_cannot_support_a_direction():
    """A family of one agreed with itself perfectly and so reported the
    highest confidence in the table. The certainty is measured against the
    standard error of the mean, which a single patch does not have."""
    one = np.array([[50.0, 40.0, 10.0]])
    got = row(family_drift(one, one + [0, 3, 0]), "reds")
    assert got.patches == 1
    assert not got.certain
    assert "not certainly" in got.sentence


def test_a_consistent_move_on_many_patches_is_certain():
    here = ring(0.0, n=80, spread=3.0)
    got = row(family_drift(here, here + [0, 0, 3.0]), "reds")
    assert got.certain
    assert "not certainly" not in got.sentence


# --------------------------------------------------------------------------
# The greys, which are the part the existing rule had no answer for
# --------------------------------------------------------------------------

def test_neutrals_are_greys_rather_than_scattered_across_six_families():
    """MEASURED, NOT ASSUMED. Nudge one colour by 0.3 Lab units — less than
    two profiles of one printer differ by — and ask how often it keeps its
    family: 25% at C* 0.1, 55% at C* 0.5, 79% at C* 1, 100% at C* 5. A maximum
    barely notices that. A mean is made of it."""
    rng = np.random.default_rng(5)
    n = 200
    greys = np.column_stack([np.linspace(10, 95, n), rng.normal(0, 1.0, n),
                             rng.normal(0, 1.0, n)])
    rows = family_drift(greys, greys + [0, 0, 2.0])
    assert row(rows, "greys").patches == n
    assert all(r.patches == 0 for r in rows if r.name != "greys")


def test_a_grey_is_never_given_a_hue_to_have_drifted_toward():
    rng = np.random.default_rng(6)
    n = 80
    greys = np.column_stack([np.linspace(20, 90, n), rng.normal(0, 1.0, n),
                             rng.normal(0, 1.0, n)])
    got = row(family_drift(greys, greys + [0, 0, 2.5]), "greys")
    assert got.toward == "warmer (yellow)"
    for name, _c in HUE_FAMILIES:
        assert name not in got.toward


def test_the_neutral_threshold_is_the_documented_one():
    """A colour on the line is a colour, not a grey, and that is a decision
    somebody has to be able to look up rather than infer."""
    just_under = np.array([[50.0, NEUTRAL_CHROMA - 0.01, 0.0]])
    just_over = np.array([[50.0, NEUTRAL_CHROMA + 0.01, 0.0]])
    assert row(family_drift(just_under, just_under + [0, 0, 2]),
               "greys").patches == 1
    assert row(family_drift(just_over, just_over + [0, 0, 2]),
               "reds").patches == 1


# --------------------------------------------------------------------------
# The arbitrary line, which is the objection the feature was asked with
# --------------------------------------------------------------------------

def test_colours_that_could_be_called_either_family_are_counted():
    """"Of course then you have to draw an arbitrary line around what is a red
    and what is a yellow." The line cannot be removed, so the colours sitting
    on it are counted and the count is reported."""
    on_the_line = ring(45.0, n=40, spread=1.0)     # reds meet yellows at 45
    rows = family_drift(on_the_line, on_the_line + [0, 0, 2.0])
    near = sum(r.near_boundary for r in rows)
    assert near == 40, "every one of them sits within a few degrees of the line"


def test_colours_in_the_middle_of_a_family_are_not_counted_as_borderline():
    middle = ring(0.0, n=40, spread=2.0)
    rows = family_drift(middle, middle + [0, 0, 2.0])
    assert sum(r.near_boundary for r in rows) == 0


def test_the_greys_are_asked_about_their_own_line_not_a_hue_one():
    """A neutral is not filed by hue at all, so how near it lies to the
    red/yellow boundary says nothing about whether calling it a grey was a
    close call. Its chroma does. Reporting the hue answer here was wrong and
    looked entirely plausible."""
    n = 40
    # Every one of these sits a whisker under the neutral threshold, so every
    # one of them is a borderline grey and none is near a hue boundary.
    borderline = np.column_stack([
        np.full(n, 50.0),
        np.full(n, NEUTRAL_CHROMA - 0.2),
        np.zeros(n)])
    got = row(family_drift(borderline, borderline + [0, 0, 2.0]), "greys")
    assert got.patches == n
    assert got.near_boundary == n


def test_the_family_rule_is_the_one_the_rest_of_the_application_uses():
    """Two different definitions of "a red" in one program is the inconsistency
    this project keeps catching, so the report is built on HUE_FAMILIES rather
    than on a second list that happens to agree today."""
    rows = family_drift(ring(0.0), ring(0.0) + [0, 0, 1])
    assert [r.name for r in rows] == [n for n, _c in HUE_FAMILIES] + ["greys"]


# --------------------------------------------------------------------------
# Everything counted once, and the refusals
# --------------------------------------------------------------------------

def test_every_colour_lands_in_exactly_one_family():
    rng = np.random.default_rng(8)
    n = 500
    lab = np.column_stack([rng.uniform(10, 95, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    rows = family_drift(lab, lab + rng.normal(0, 1, lab.shape))
    assert sum(r.patches for r in rows) == n


def test_an_empty_family_is_not_a_family_that_did_not_move():
    """Two different statements that must never come out as the same line."""
    reds = ring(0.0)
    rows = family_drift(reds, reds + [0, 0, 2])
    empty = [r for r in rows if r.patches == 0]
    assert empty
    for r in empty:
        assert r.toward == "" and r.mean_de == 0.0
        assert "nothing in this family" in r.sentence


def test_every_sentence_carries_the_number_of_patches_it_stands_on():
    """A family of four and a family of four hundred must never read alike."""
    big = ring(90.0, n=300)
    small = np.array([[50.0, -20.0, -30.0], [55.0, -22.0, -28.0]])
    lab = np.vstack([big, small])
    rows = family_drift(lab, lab + [0, 0, 4.0])
    for r in rows:
        if r.patches == 1:
            assert "1 patch" in r.sentence and "patches" not in r.sentence
        elif r.patches:
            assert f"{r.patches} patches" in r.sentence


def test_an_unreadable_patch_is_refused_rather_than_averaged_around():
    """One NaN made a family's mean "nan" and left the direction beside it
    named in full confidence. A line reading "reds: nan ΔE, toward the
    yellows" is worse than no line at all."""
    lab = np.array([[50.0, np.nan, 0.0], [50.0, 40.0, 0.0]])
    with pytest.raises(ValueError, match="not numbers"):
        family_drift(lab, lab + [0, 1, 0])


def test_two_sets_of_different_lengths_are_refused():
    with pytest.raises(ValueError, match="same colours in the same order"):
        family_drift(np.zeros((4, 3)), np.zeros((5, 3)))


def test_nothing_to_compare_is_refused():
    with pytest.raises(ValueError, match="no colours"):
        family_drift(np.zeros((0, 3)), np.zeros((0, 3)))


def test_something_that_is_not_lab_is_refused():
    with pytest.raises(ValueError, match=r"\(N, 3\)"):
        family_drift(np.zeros(9), np.zeros(9))


def test_the_thresholds_are_the_ones_the_rest_of_the_module_uses():
    """QUIET_DE is the same ΔE 1 that Drift.over_one counts, on purpose."""
    assert QUIET_DE == 1.0
    assert NEUTRAL_CHROMA == 5.0
    assert 0.0 < AGREEMENT < 1.0
    assert BOUNDARY_DEGREES > 0.0


# --------------------------------------------------------------------------
# In the window
# --------------------------------------------------------------------------
#
# THROUGH A STAND-IN, NOT A REAL WINDOW, and that is not laziness. A real
# TimelineDialog builds a QWebEngineView, and building one inside pytest takes
# the whole process down with it -- which is why every other window test in
# this suite is written the same way. The methods under test are the REAL
# ones, called against an object carrying only what they touch, so they cannot
# quietly grow a dependency this misses.

class Label:
    """Enough of a WrappedLabel for the methods that write to one."""

    def __init__(self, text=""):
        self._text = text

    def setText(self, text):                              # noqa: N802 (Qt)
        self._text = text

    def text(self):
        return self._text


def a_window(paths, chosen=None):
    import drift_series
    import gamut_app

    win = SimpleNamespace(
        _paths=list(paths),
        _run=drift_series.build(list(paths), steps=5),
        _families=Label(), _families_note=Label(), _view=None,
        GRID=5)
    win._chosen_pair = lambda: chosen
    win._say_the_families = (
        lambda pair: gamut_app.TimelineDialog._say_the_families(win, pair))
    win._blank = lambda: gamut_app.TimelineDialog._blank(win)
    return win


def test_the_whole_run_is_reported_first_against_last(tmp_path):
    from test_chart import write_matrix_profile

    win = a_window([write_matrix_profile(tmp_path / "a.icc"),
                    write_matrix_profile(tmp_path / "b.icc", gamma=2.6)])
    win._say_the_families(None)
    said = win._families.text()
    assert said.startswith("a to b"), said
    assert "patches)" in said


def test_removing_every_profile_takes_the_report_away_with_them(tmp_path):
    """A REPORT THAT OUTLIVES ITS FILES IS A FALSE ONE. Emptying the window
    cleared the graph and left the family lines under it, naming two profiles
    that were no longer open. Found by clearing the window in a driver and
    reading what was still on it -- not something a test that never empties
    anything can notice."""
    from test_chart import write_matrix_profile

    win = a_window([write_matrix_profile(tmp_path / "a.icc"),
                    write_matrix_profile(tmp_path / "b.icc", gamma=2.6)])
    win._say_the_families(None)
    assert win._families.text(), "there should be a report to lose"

    win._blank()
    assert win._families.text() == ""
    assert win._families_note.text() == ""


def test_the_report_follows_the_pair_that_is_showing(tmp_path):
    """The verdict above it had this exact fault once and it was fixed by
    saying the words from _draw. This is filled the same way, or it drifts out
    of step with the picture in the same manner."""
    from test_chart import write_matrix_profile

    a = write_matrix_profile(tmp_path / "a.icc")
    b = write_matrix_profile(tmp_path / "b.icc", gamma=2.6)
    win = a_window([a, b])
    win._say_the_families(None)
    whole = win._families.text()

    win._chosen_pair = lambda: (a, b, "a → b")
    win._say_the_families((a, b, "a → b"))
    assert win._families.text().startswith("a → b")
    assert win._families.text() != whole


def test_a_run_with_nothing_usable_says_nothing_rather_than_guessing(tmp_path):
    from test_chart import write_matrix_profile

    win = a_window([write_matrix_profile(tmp_path / "only.icc")])
    win._say_the_families(None)
    assert win._families.text() == ""


def test_the_footnote_says_where_the_arbitrary_line_is(tmp_path):
    """The objection this feature was asked with, answered on screen rather
    than in a docstring nobody reads."""
    from test_chart import write_matrix_profile

    win = a_window([write_matrix_profile(tmp_path / "a.icc"),
                    write_matrix_profile(tmp_path / "b.icc", gamma=2.6)])
    win._say_the_families(None)
    note = win._families_note.text()
    assert "not one that exists in nature" in note
    assert "grey" in note
    for name, _c in HUE_FAMILIES:
        assert name in note
