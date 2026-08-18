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
import re
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
    # Bound to the REAL methods rather than to copies of what they do, so the
    # stand-in cannot quietly stop testing them.
    for name in ("_say_the_families", "_family_report", "_family_rows",
                 "_families_html", "_cloud_notes", "_blank"):
        setattr(win, name, _bind(gamut_app.TimelineDialog, name, win))
    return win


def _bind(cls, name, win):
    method = getattr(cls, name)
    return lambda *a, **k: method(win, *a, **k)


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


# --------------------------------------------------------------------------
# Out of the window — the page and the table people actually send
# --------------------------------------------------------------------------
#
# THE SAVED FILE IS THE PRODUCT. Somebody runs this to show a colleague or a
# paper supplier, and what gets quoted is the list of sentences rather than
# the picture. A report that lived only on screen would send the half that
# needs interpreting and keep back the half that does not.

def test_the_saved_cloud_page_carries_the_report(tmp_path):
    from test_chart import write_matrix_profile

    a = write_matrix_profile(tmp_path / "a.icc")
    b = write_matrix_profile(tmp_path / "b.icc", gamma=2.6)
    win = a_window([a, b], chosen=(a, b, "a → b"))
    notes = win._cloud_notes((a, b, "a → b"))
    assert "which colour families moved" in notes
    assert "patches)" in notes
    assert "not one that exists in nature" in notes


def test_the_saved_graph_page_carries_the_report(tmp_path):
    from test_chart import write_matrix_profile

    win = a_window([write_matrix_profile(tmp_path / "a.icc"),
                    write_matrix_profile(tmp_path / "b.icc", gamma=2.6)])
    html = win._families_html()
    assert "<ul class=\"families\">" in html
    assert html.count("<li>") >= 1
    assert "not one that exists in nature" in html


def test_the_saved_page_escapes_what_it_writes(tmp_path):
    """The family names are ours, but the profile names in the heading are the
    user's, and they end up in HTML.

    THE FIRST VERSION OF THIS TEST COULD NOT RUN ON WINDOWS. It made a file
    literally called ``<b>a.icc``, which is legal on macOS and Linux and is
    OSError: Invalid argument on Windows -- angle brackets are among the
    characters Windows forbids in a filename. It passed here and took both
    Windows jobs down in CI, which is exactly what those jobs are for.

    An ampersand needs escaping just as much and is legal on every platform
    this ships to, so the same rule is proved with a name a user could really
    have.
    """
    from test_chart import write_matrix_profile

    win = a_window([write_matrix_profile(tmp_path / "R&D paper.icc"),
                    write_matrix_profile(tmp_path / "b.icc", gamma=2.6)])
    html = win._families_html()
    assert "R&amp;D paper" in html
    assert "R&D paper" not in html


def test_the_table_carries_one_row_per_family_with_its_count(tmp_path):
    from test_chart import write_matrix_profile

    win = a_window([write_matrix_profile(tmp_path / "a.icc"),
                    write_matrix_profile(tmp_path / "b.icc", gamma=2.6)])
    rows = win._family_rows()
    assert rows, "there should be a family table"
    named = {r[0] for r in rows}
    for name, _c in HUE_FAMILIES:
        assert name in named
    assert "greys" in named
    # every family row carries a count, and it is a number
    for row_ in rows[1:-1]:
        assert row_[2].isdigit(), row_


def test_an_empty_family_is_said_in_the_table_rather_than_left_out(tmp_path):
    """A family missing from a spreadsheet reads as one that was not measured.
    It was measured, and it was empty, which is a different fact."""
    from test_chart import write_matrix_profile

    win = a_window([write_matrix_profile(tmp_path / "a.icc"),
                    write_matrix_profile(tmp_path / "b.icc", gamma=2.6)])
    rows = win._family_rows()
    counted = [r for r in rows if r[2] == "0"]
    for row_ in counted:
        assert "nothing in this family" in row_[1]


def test_the_table_says_where_the_arbitrary_line_is(tmp_path):
    from test_chart import write_matrix_profile

    win = a_window([write_matrix_profile(tmp_path / "a.icc"),
                    write_matrix_profile(tmp_path / "b.icc", gamma=2.6)])
    last = win._family_rows()[-1]
    assert last[0] == "where the line is"
    assert "grey" in last[1]
    assert "either way" in last[2]


def test_screen_page_and_table_all_quote_the_same_numbers(tmp_path):
    """THREE PLACES, ONE CALCULATION. Written three times this would be three
    chances for a saved file to disagree with the window it came from, and
    this project has already had a caption disagree with the cloud above it."""
    from test_chart import write_matrix_profile

    win = a_window([write_matrix_profile(tmp_path / "a.icc"),
                    write_matrix_profile(tmp_path / "b.icc", gamma=2.6)])
    win._say_the_families(None)
    on_screen = win._families.text()
    in_page = win._families_html()
    in_table = win._family_rows()

    for row_ in in_table[1:-1]:
        if row_[2] == "0":
            continue
        family, what, count = row_
        # the ΔE each one reports, to one decimal, must be the same everywhere
        de = what.split()[1]
        assert f"{family}: ΔE {float(de):.1f}" in on_screen or \
               f"{family}: stayed the same (ΔE {float(de):.1f}" in on_screen
        assert f"({count} patch" in on_screen
        assert f"({count} patch" in in_page


# --------------------------------------------------------------------------
# Every combination, rather than one option at a time
# --------------------------------------------------------------------------
#
# Testing one thing at a time proves nothing about pairs, and this project has
# already had a bug that only appeared when two settings were crossed. The
# cases above each move ONE family ONE way at ONE size. This crosses them and
# asks, of every result, things that must be true whatever the answer is --
# which is worth more than an expected value, because an invariant holds for
# the cases nobody thought to predict.

def _cloud(rng, centre, n, chroma, spread):
    ang = np.radians(centre + rng.uniform(-spread, spread, n))
    c = chroma * (1.0 + rng.uniform(-0.08, 0.08, n))
    return np.column_stack([np.full(n, 55.0) + rng.uniform(-6, 6, n),
                            c * np.cos(ang), c * np.sin(ang)])


def _moved(rng, lab, how):
    out = lab.copy()
    if how == "still":
        return out
    if how == "tiny":
        out[:, 2] += 0.15
    elif how in ("hue+", "hue-"):
        th = np.radians(9.0 if how == "hue+" else -9.0)
        rot = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
        out[:, 1:] = lab[:, 1:] @ rot.T
    elif how == "fade":
        out[:, 1:] *= 0.80
    elif how == "boost":
        out[:, 1:] *= 1.20
    elif how == "lighter":
        out[:, 0] += 4.0
    elif how == "darker":
        out[:, 0] -= 4.0
    elif how == "fade+dark":
        out[:, 1:] *= 0.82
        out[:, 0] -= 4.5
    elif how == "noise":
        out += rng.normal(0, 7.0, lab.shape)
    return out


#: A chroma nobody would call a colour. WRITTEN AS A NUMBER, NOT AS
#: NEUTRAL_CHROMA, and the difference is the whole value of the check. Phrased
#: as "if chroma < NEUTRAL_CHROMA" this tested the constant against itself:
#: setting NEUTRAL_CHROMA to 0 -- which is precisely the bug of dropping the
#: threshold and going back to the rule hue_reach uses -- made the condition
#: never true, the check was skipped, and the sweep reported a clean 3300.
#: A check phrased in terms of the thing it guards cannot catch its removal.
CERTAINLY_NEUTRAL = 4.0


def test_every_combination_keeps_the_promises_the_report_makes():
    rng = np.random.default_rng(20260817)
    names = [n for n, _c in HUE_FAMILIES]
    broken = []
    seen = 0

    for (name, centre) in HUE_FAMILIES:
        for how in ("still", "tiny", "hue+", "hue-", "fade", "boost",
                    "lighter", "darker", "fade+dark", "noise"):
            for n in (1, 3, 60):
                for chroma in (1.5, 4.0, 25.0, 55.0):
                    for spread in (2.0, 14.0):
                        before = _cloud(rng, centre, n, chroma, spread)
                        rows = family_drift(before, _moved(rng, before, how))
                        seen += 1
                        where = (f"{name} {how} n={n} C*={chroma} "
                                 f"spread={spread}")
                        by = {r.name: r for r in rows}

                        if sum(r.patches for r in rows) != n:
                            broken.append(f"{where}: colours lost or doubled")

                        if chroma <= CERTAINLY_NEUTRAL:
                            if by["greys"].patches != n:
                                broken.append(f"{where}: neutrals not grey")
                            if any(by[f].patches for f in names):
                                broken.append(f"{where}: neutral given a hue")

                        for r in rows:
                            if not r.patches:
                                if r.toward or r.mean_de or r.certain:
                                    broken.append(
                                        f"{where}: empty {r.name} claimed "
                                        f"something")
                                continue
                            want = ("1 patch" if r.patches == 1
                                    else f"{r.patches} patches")
                            if want not in r.sentence:
                                broken.append(
                                    f"{where}: {r.name} hides its count")
                            if (r.mean_de < QUIET_DE) != (r.toward == ""):
                                broken.append(
                                    f"{where}: {r.name} ΔE {r.mean_de:.2f} "
                                    f"but toward={r.toward!r}")
                            if r.patches == 1 and r.certain:
                                broken.append(
                                    f"{where}: {r.name} certain on one patch")
                            if r.name == "greys" and any(f in r.toward
                                                         for f in names):
                                broken.append(
                                    f"{where}: grey given a hue direction")
                            if r.toward == f"toward the {r.name}":
                                broken.append(
                                    f"{where}: {r.name} heading for itself")
                            if r.toward and r.name != "greys":
                                pure = {"lighter": "lighter",
                                        "darker": "darker",
                                        "fade": "toward grey",
                                        "boost": "more saturated"}.get(how)
                                if pure and r.toward != pure:
                                    broken.append(
                                        f"{where}: pure {how} came out as "
                                        f"{r.toward!r}")
                                if how in ("hue+", "hue-") and not \
                                        r.toward.startswith("toward the"):
                                    broken.append(
                                        f"{where}: rotation came out as "
                                        f"{r.toward!r}")

    assert seen >= 1400, f"only {seen} combinations were crossed"
    assert not broken, (f"{len(broken)} of {seen} combinations broke a "
                        f"promise:\n" + "\n".join(broken[:20]))


# --------------------------------------------------------------------------
# The picture, split into the same families as the sentences
# --------------------------------------------------------------------------

def test_the_cloud_can_be_split_into_the_families_the_report_names():
    """One trace per family turns the drawing library's own legend into a
    filter — in the window and in a saved page alike, offline, with no code
    of ours involved."""
    import ti3gamut

    rng = np.random.default_rng(11)
    n = 400
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    de = rng.uniform(0, 6, n)

    assert len(ti3gamut.drift_cloud(lab, de, "x")) == 1
    split = ti3gamut.drift_cloud(lab, de, "x", by_family=True)
    assert 2 <= len(split) <= len(HUE_FAMILIES) + 1


def test_splitting_keeps_every_colour_exactly_once():
    import ti3gamut

    rng = np.random.default_rng(12)
    n = 500
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    split = ti3gamut.drift_cloud(lab, rng.uniform(0, 6, n), "x",
                                 by_family=True)
    assert sum(len(t.x) for t in split) == n


def test_the_picture_counts_and_the_written_counts_are_the_same_numbers():
    """THE FAULT THIS EXISTS TO PREVENT. Two pieces of arithmetic filing
    colours into families would agree today and disagree after the first
    change to either, and the reader would have a picture contradicting the
    words underneath it. Both go through one function."""
    import ti3gamut

    rng = np.random.default_rng(13)
    n = 600
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    after = lab + rng.normal(0, 2.0, lab.shape)
    de = np.linalg.norm(after - lab, axis=1)

    in_words = {r.name: r.patches for r in family_drift(lab, after)
                if r.patches}
    in_picture = {t.name.split(" — ")[0]: int(t.name.split(" — ")[1])
                  for t in ti3gamut.drift_cloud(lab, de, "x", by_family=True)}
    assert in_words == in_picture


def test_the_split_picture_carries_exactly_one_colour_key():
    """Seven groups sharing one fixed scale, not seven bars down the side.

    THE TEST USED TO ASK WHICH TRACE CARRIED THE BAR, and passed while the
    real fault was live: the bar was on the first trace, so switching the reds
    off took it away. Asking "how many traces have their own scale" cannot
    catch that -- one is exactly what the broken version had.

    So it asks the thing that actually matters instead: no trace owns a scale
    at all, and they all read the same one, which lives on the scene where
    nothing can switch it off.
    """
    import ti3gamut

    rng = np.random.default_rng(14)
    n = 300
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    for values, axis in ((rng.uniform(0, 6, n), None),
                         (rng.normal(0, 3, (n, 3)), "b")):
        fig = ti3gamut.build_figure([], "x", mode="dark", space="lab",
                                    grid=True,
                                    drift=(lab, values, "d", axis, True))
        assert not any(t.marker.showscale for t in fig.data), (
            "a family owns the key and can take it away")
        assert all(t.marker.coloraxis == "coloraxis" for t in fig.data)
        assert fig.layout.coloraxis.colorbar.title.text
        assert fig.layout.coloraxis.cmin is not None


def test_an_empty_family_gets_no_legend_entry():
    """A legend row that switches nothing on or off is a control that does
    nothing, which this project holds is worse than a missing one."""
    import ti3gamut

    rng = np.random.default_rng(15)
    n = 80
    ang = np.radians(rng.uniform(-6, 6, n))          # reds only
    lab = np.column_stack([np.full(n, 55.0), 40 * np.cos(ang),
                           40 * np.sin(ang)])
    names = {t.name.split(" — ")[0]
             for t in ti3gamut.drift_cloud(lab, rng.uniform(0, 6, n), "x",
                                           by_family=True)}
    assert names == {"reds"}


def test_which_family_refuses_something_that_is_not_lab():
    from gamutview import which_family

    with pytest.raises(ValueError, match=r"\(N, 3\)"):
        which_family(np.zeros(9))


def test_no_single_family_owns_the_colour_key():
    """"turning off the reds turns off the heat map on the right."

    THE KEY BELONGED TO WHICHEVER FAMILY WAS DRAWN FIRST, which is what
    "draw the bar once" naturally means and is wrong: switching that family
    off took the ΔE scale off the page and left the remaining dots painted in
    colours with nothing to read them against. Hiding any OTHER family looked
    fine, which is why it survived a check that tried one.

    A layout colour axis is owned by the scene, so no trace can take it away.
    """
    import ti3gamut

    rng = np.random.default_rng(21)
    n = 500
    lab = np.column_stack([rng.uniform(20, 92, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, rng.uniform(0, 6, n), "d", None,
                                       True))
    # not one trace carries a scale of its own …
    assert not any(t.marker.showscale for t in fig.data)
    # … they all point at the scene's, which is where the key lives
    assert all(t.marker.coloraxis == "coloraxis" for t in fig.data)
    assert fig.layout.coloraxis.colorbar.title.text == "ΔE2000"
    assert (fig.layout.coloraxis.cmin, fig.layout.coloraxis.cmax) == (0.0, 5.0)


def test_the_direction_view_keeps_its_key_the_same_way():
    """The same trap, the other picture — and its key says something else."""
    import ti3gamut

    rng = np.random.default_rng(22)
    n = 300
    lab = np.column_stack([rng.uniform(20, 92, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, rng.normal(0, 3, (n, 3)), "d", "b",
                                       True))
    assert not any(t.marker.showscale for t in fig.data)
    assert fig.layout.coloraxis.colorbar.title.text == "warmer or cooler"
    # a direction runs both ways from nothing, and must still
    assert fig.layout.coloraxis.cmin < 0 < fig.layout.coloraxis.cmax


def test_the_last_family_standing_still_gets_its_name():
    """The key must not switch itself off when one family is left.

    REPORTED FROM THE PUBLISHED PAGE, with a photograph: the threshold pushed
    up until two dots remained, and every label gone. "here are still two
    patches left but no more labels visible."

    THE CAUSE, MEASURED IN A BROWSER rather than reasoned about. The drawing
    library marks a trace with no points left not-visible, and then applies
    its own rule that a single visible trace needs no key at all:

        reds ... magentas   visible=False  n=0
        greys — 11          visible=True   n=2     showlegend flipped to false

    That default is right for a picture of one thing. Here the last family
    standing is the whole answer -- it is the only way of knowing which
    colours those two dots are -- so the key is asked for by name.

    ASKED OF THE FIGURE, NOT OF THE SOURCE. What matters is what the scene
    says, and a figure that has been through the same call the page is
    written from is the thing that carries it.
    """
    import ti3gamut

    rng = np.random.default_rng(24)
    n = 240
    lab = np.column_stack([rng.uniform(20, 92, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    for values, axis in ((rng.uniform(0, 6, n), None),
                         (rng.normal(0, 3, (n, 3)), "L")):
        fig = ti3gamut.build_figure([], "x", mode="dark", space="lab",
                                    grid=True,
                                    drift=(lab, values, "d", axis, True))
        assert fig.layout.showlegend is True, (
            "the key is left to the library, which drops it as soon as only "
            "one family still has a dot in it")


def test_an_unsplit_cloud_still_carries_its_own_key():
    """One trace cannot be hidden without hiding everything, so nothing
    changes for it — and no page published before this looks different."""
    import ti3gamut

    rng = np.random.default_rng(23)
    n = 200
    lab = np.column_stack([rng.uniform(20, 92, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, rng.uniform(0, 6, n), "d"))
    assert fig.data[0].marker.colorbar.title.text == "ΔE2000"
    assert fig.layout.coloraxis.colorbar.title.text is None


# --------------------------------------------------------------------------
# The main window: two measurements, and two profiles
# --------------------------------------------------------------------------
#
# THE CASE THE DRIFT BOX EXISTS FOR HAD NOTHING. For one release the family
# report lived only in "Follow one device over time", so somebody holding two
# readings of one chart -- print it again months later on the same paper and
# the same printer, which is the verification case -- got a ΔE summary and no
# word about WHICH colours had moved.

def test_the_words_differ_for_measurements_and_for_profiles():
    """WHAT THE NUMBER MEANS IS NOT THE SAME, and an earlier version claimed
    in its docstring to say so while changing exactly one word.

    Two profiles are two DESCRIPTIONS of a device. Two measurements are the
    printing itself -- and if the second was printed again rather than only
    measured again, the whole process is in there: printhead temperature
    changes drop volume, low humidity darkens ink at the nozzles, paper takes
    up moisture. Calling that "the chart faded" is wrong.
    """
    from gamut_app import family_report

    rng = np.random.default_rng(31)
    n = 200
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-50, 50, n),
                           rng.uniform(-50, 50, n)])
    after = lab + [0, 0, 2.5]

    as_profiles = family_report(lab, after, "a → b", of="profiles")[1]
    as_measured = family_report(lab, after, "a → b", of="measurements")[1]
    assert as_profiles != as_measured

    assert "not how far the printer moved" in as_profiles
    assert "one day's measurements" in as_profiles

    assert "PRINTED" in as_measured
    assert "ink batch" in as_measured or "paper batch" in as_measured
    assert "same sheet read" in as_measured
    # and it must NOT blame chart fade for a reprint
    assert "chart faded" not in as_measured


def test_a_measurement_pair_counts_patches_and_a_profile_pair_colours():
    """A profile is asked about a GRID of colours nobody printed; a
    measurement pair stands on real patches. Calling both the same thing
    invites a reader to compare two numbers that are not alike."""
    from gamut_app import family_report

    rng = np.random.default_rng(32)
    n = 300
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-50, 50, n),
                           rng.uniform(-50, 50, n)])
    after = lab + rng.normal(0, 1.5, lab.shape)
    prof = family_report(lab, after, "a → b", of="profiles")[1]
    meas = family_report(lab, after, "a → b", of="measurements")[1]
    if "sit within" in prof:            # only said when some are borderline
        assert "colours," in prof
        assert "patches," in meas


def test_the_report_is_cleared_on_every_path_that_cannot_fill_it():
    """IT SURVIVED "Close them all" AND WENT ON NAMING CLOSED FILES — the same
    fault as the timeline window's, in a second place. Found by clearing the
    real window and reading what was left, not by a test."""
    import gamut_app

    class Label:
        def __init__(self):
            self._t = ""

        def setText(self, text):                      # noqa: N802 (Qt)
            self._t = text

        def text(self):
            return self._t

    win = SimpleNamespace(_drift_families=Label(),
                          _drift_families_note=Label())
    say = lambda *a, **k: gamut_app.GamutApp._say_drift_families(win, *a, **k)

    rng = np.random.default_rng(33)
    n = 120
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-50, 50, n),
                           rng.uniform(-50, 50, n)])
    say(lab, lab + [0, 0, 3.0], "a → b", of="measurements")
    assert win._drift_families.text(), "there should be a report to lose"

    say()                                   # the no-pair path
    assert win._drift_families.text() == ""
    assert win._drift_families_note.text() == ""


def test_the_heading_is_a_file_name_not_a_path():
    """It came out as "private-tmp-claude-502--Users-…-Glossy-pap → …" because
    a path was handed to a helper that sanitises names into safe file names.
    Read off the window, not caught by anything."""
    from gamut_app import family_report

    rng = np.random.default_rng(34)
    n = 100
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-50, 50, n),
                           rng.uniform(-50, 50, n)])
    said = family_report(lab, lab + [0, 0, 3.0],
                         "Glossy-paper → Glossy-paper-months-later",
                         of="measurements")
    assert said[0].startswith("Glossy-paper → Glossy-paper-months-later")
    assert "/" not in said[0].splitlines()[0]


def test_every_readout_the_window_has_is_in_the_one_list():
    """THE LIST WAS WRITTEN OUT THREE TIMES and two copies fell behind.

    Adding the colour-family lines meant updating the one that clears the
    readouts when files are closed, the one that copies them into a saved
    page, and the stand-in the tests use. Two were missed, and each showed up
    as its own bug: a report that outlived its files, and a saved page that
    silently left the report out.

    This walks the class for widgets that look like readouts and insists the
    list knows about them, so the next one cannot be forgotten quietly.
    """
    import inspect

    import gamut_app

    source = inspect.getsource(gamut_app.GamutApp._build_controls)
    # every "self._x = WrappedLabel(...)" that lives in a readout group box
    made = set(re.findall(r"self\.(_[a-z_]+)\s*=\s*WrappedLabel\(", source))
    listed = set(gamut_app.GamutApp.READOUTS)
    # the ones this test is about: anything the drift box owns
    drift_ones = {n for n in made if n.startswith("_drift")}
    missing = drift_ones - listed
    assert not missing, (
        f"these readouts are not in GamutApp.READOUTS and will be left "
        f"behind when the files are closed, and left out of saved pages: "
        f"{sorted(missing)}")


# --------------------------------------------------------------------------
# Hiding the colours that barely moved
# --------------------------------------------------------------------------

def test_the_threshold_means_dE_in_every_view():
    """ONE NUMBER MEANING ONE THING. A colour can move a long way and barely
    change in b*, so thresholding on the painted value would leave a different
    set of dots in each of the three direction views — and a reader switching
    between them would reasonably read that as the data changing."""
    import ti3gamut

    rng = np.random.default_rng(41)
    n = 400
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    de = rng.uniform(0, 6, n)
    moved = rng.normal(0, 3, (n, 3))

    far = ti3gamut.drift_cloud(lab, de, "x", hide_below=3.0)
    kept_distance = sum(len(t.x) for t in far)
    for axis in ("L", "a", "b"):
        way = ti3gamut.drift_direction(lab, moved, "x", axis=axis, deltas=de,
                                       hide_below=3.0)
        assert sum(len(t.x) for t in way) == kept_distance, (
            f"the {axis} view kept a different set of colours")


def test_hiding_by_dE_without_the_dE_values_is_refused():
    """Rather than quietly thresholding on one axis, which would mean
    something different in each view."""
    import ti3gamut

    rng = np.random.default_rng(42)
    n = 50
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    with pytest.raises(ValueError, match="needs the ΔE values"):
        ti3gamut.drift_direction(lab, rng.normal(0, 3, (n, 3)), "x",
                                 axis="b", hide_below=2.0)


def test_a_picture_with_things_taken_out_of_it_says_so():
    """Somebody sent a saved page showing eleven dots cannot tell whether the
    printer is nearly perfect or whether seven hundred colours were hidden.
    This is exactly the kind of picture people forward to other people."""
    import re

    import ti3gamut

    rng = np.random.default_rng(43)
    n = 300
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    de = rng.uniform(0, 4, n)

    plain = ti3gamut.build_figure([], "T", mode="dark", space="lab", grid=True,
                                  drift=(lab, de, "d", None, True, 0.0))
    assert "not drawn" not in re.sub(r"<[^>]+>", "", plain.layout.title.text)

    cut = ti3gamut.build_figure([], "T", mode="dark", space="lab", grid=True,
                                drift=(lab, de, "d", None, True, 2.0))
    said = re.sub(r"<[^>]+>", "", cut.layout.title.text)
    assert "are not drawn" in said
    assert "ΔE 2.0" in said


def test_a_threshold_above_everything_still_explains_itself():
    """THE EDGE CASE THAT MUST NOT BE AN EMPTY BOX. With every colour hidden
    there is no trace left to hang an explanation on, so the sentence is
    worked out before anything is drawn."""
    import re

    import ti3gamut

    rng = np.random.default_rng(44)
    n = 200
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    de = rng.uniform(0, 3, n)
    fig = ti3gamut.build_figure([], "T", mode="dark", space="lab", grid=True,
                                drift=(lab, de, "d", None, True, 99.0))
    assert sum(len(t.x) for t in fig.data) == 0, "nothing should be drawn"
    said = re.sub(r"<[^>]+>", "", fig.layout.title.text)
    assert f"{n} of {n} colours" in said
    # and the box is still the box, so the reader is not looking at a
    # collapsed room either
    assert fig.layout.scene.xaxis.range is not None


def test_the_box_does_not_move_when_the_threshold_does():
    """Same rule as hiding a family: the range comes from ALL the colours, so
    raising the threshold removes dots and moves nothing else."""
    import ti3gamut

    rng = np.random.default_rng(45)
    n = 400
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    de = rng.uniform(0, 6, n)
    boxes = []
    for t in (0.0, 1.0, 3.0, 5.0):
        fig = ti3gamut.build_figure([], "T", mode="dark", space="lab",
                                    grid=True, drift=(lab, de, "d", None,
                                                      True, t))
        sc = fig.layout.scene
        boxes.append((tuple(sc.xaxis.range), tuple(sc.yaxis.range),
                      tuple(sc.zaxis.range)))
    assert len(set(boxes)) == 1, f"the box moved with the threshold: {boxes}"


def test_nothing_is_hidden_at_zero():
    import ti3gamut

    rng = np.random.default_rng(46)
    n = 150
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    de = rng.uniform(0, 5, n)
    got = ti3gamut.drift_cloud(lab, de, "x", hide_below=0.0)
    assert sum(len(t.x) for t in got) == n
    _keep, said = ti3gamut.hidden_below(de, 0.0)
    assert said == ""


def test_the_threshold_cannot_squash_the_room_either():
    """REPORTED TWICE, FROM TWO DIFFERENT SWITCHES. Pinning the box was tied
    to the family split, because only a split picture could lose points. The
    threshold then gave the unsplit picture a second way to lose them: raise
    it from 600 dots to 51 and the room refitted around those 51.

    Crossed here rather than tried one at a time — split and unsplit, four
    thresholds each — because that is exactly the pair that was missed.
    """
    import ti3gamut

    rng = np.random.default_rng(51)
    n = 600
    lab = np.column_stack([rng.uniform(20, 95, n), rng.uniform(-80, 85, n),
                           rng.uniform(-75, 125, n)])
    de = rng.uniform(0.6, 3.0, n)

    seen = set()
    for split in (False, True):
        for cut in (0.0, 1.0, 2.0, 2.8):
            fig = ti3gamut.build_figure([], "T", mode="dark", space="lab",
                                        grid=True,
                                        drift=(lab, de, "d", None, split, cut))
            scene = fig.layout.scene
            seen.add((tuple(scene.xaxis.range), tuple(scene.yaxis.range),
                      tuple(scene.zaxis.range),
                      round(scene.aspectratio.y, 6),
                      round(scene.aspectratio.z, 6)))
    assert len(seen) == 1, (
        f"the room changed shape across split/threshold combinations: {seen}")


def test_one_family_toggles_one_family():
    """CLICKING "blues" HID ALL SEVEN. Putting the families in a legend group
    -- to stop the key reading as one flat list beside the shape names --
    made the drawing library toggle them as a GROUP, which is its default.
    The filter is the whole reason for splitting the cloud, and it stopped
    working; it was reported from the published page.

    Checked as a property of the traces rather than through a browser, so it
    holds without a rendering engine: no legend group means no group toggle.
    """
    import ti3gamut

    rng = np.random.default_rng(61)
    n = 400
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    for values, axis in ((rng.uniform(0, 5, n), None),
                         (rng.normal(0, 3, (n, 3)), "b")):
        fig = ti3gamut.build_figure([], "T", mode="dark", space="lab",
                                    grid=True,
                                    drift=(lab, values, "d", axis, True))
        for trace in fig.data:
            assert not trace.legendgroup, (
                f"{trace.name} is in a legend group, so clicking it toggles "
                f"every other family with it")


def test_the_key_flows_across_rather_than_down():
    """A grouped key stacks in a column and grew to 564x163px, eating the
    picture's room. Horizontal is what the layout asks for and what a flat
    legend obeys."""
    import ti3gamut

    rng = np.random.default_rng(62)
    n = 200
    lab = np.column_stack([rng.uniform(20, 90, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    fig = ti3gamut.build_figure([], "T", mode="dark", space="lab", grid=True,
                                drift=(lab, rng.uniform(0, 5, n), "d", None,
                                       True))
    assert fig.layout.legend.orientation == "h"


def test_the_window_asks_which_question_and_the_words_follow(tmp_path):
    """#123: the same arithmetic answers two questions, in different verbs.

    "Moved" is a claim about TIME. Said of two papers measured on one
    afternoon it is simply false — and it is exactly the sort of false
    sentence somebody pastes into an email. The files cannot say which case
    they are: two .ti3 of one chart look identical whether they are one
    printer months apart or two papers in one session.

    THE NUMBERS MUST NOT MOVE WITH THE WORDS, which is the half of this worth
    a test of its own: switching the chooser is a statement about what the
    files ARE, not a different measurement.
    """
    rng = np.random.default_rng(52)
    n = 240
    lab_a = np.column_stack([rng.uniform(25, 90, n), rng.uniform(-55, 55, n),
                             rng.uniform(-55, 55, n)])
    lab_b = lab_a + rng.normal(0.8, 0.3, (n, 3))

    from gamut_app import family_report

    over, _note_a = family_report(lab_a, lab_b, "A → B",
                                  of="measurements", over_time=True)
    apart, note_b = family_report(lab_a, lab_b, "A → B",
                                  of="measurements", over_time=False)

    assert "moved" in over.splitlines()[0]
    assert "moved" not in apart.splitlines()[0], (
        f"two different things cannot have moved: {apart.splitlines()[0]!r}")
    assert "drifted" in note_b or "different things" in note_b

    # THE SAME NUMBERS IN BOTH, to the last decimal.
    import re
    numbers = lambda text: re.findall(r"\d+\.\d+|\(\d+ patches\)", text)
    assert numbers(over) == numbers(apart), (
        "the reading changed when only the question was named")


def test_the_windows_chooser_really_reaches_the_words():
    """AND THIS IS THE TEST THAT MATTERS, because the one above does not.

    The first version of this checked family_report(over_time=False) against
    family_report(over_time=True) and passed with flying colours — while the
    window called family_report without the argument at all. Proved by
    deleting `over_time=over_time` from _say_drift_families: sixty-six tests,
    all green. A check phrased in terms of the thing it guards cannot catch
    that thing being disconnected, which is the fourth time this project has
    learned it.

    So this drives the window's own path, through a stand-in that carries the
    chooser, and asks what ends up in the label a reader would read.
    """
    import gamut_app

    class Label:
        def __init__(self):
            self._t = ""

        def setText(self, text):                      # noqa: N802 (Qt)
            self._t = text

        def text(self):
            return self._t

    class Picker:
        def __init__(self, answer):
            self._answer = answer

        def currentData(self):                        # noqa: N802 (Qt)
            return self._answer

    rng = np.random.default_rng(53)
    n = 200
    lab = np.column_stack([rng.uniform(25, 90, n), rng.uniform(-55, 55, n),
                           rng.uniform(-55, 55, n)])
    moved = lab + rng.normal(0.9, 0.25, (n, 3))

    said = {}
    for answer in (True, False):
        win = SimpleNamespace(_drift_families=Label(),
                              _drift_families_note=Label(),
                              _same_thing=Picker(answer))
        gamut_app.GamutApp._say_drift_families(win, lab, moved, "A → B",
                                               of="measurements")
        said[answer] = (win._drift_families.text(),
                        win._drift_families_note.text())

    assert said[True] != said[False], (
        "the chooser is not reaching the report at all")
    assert "moved" in said[True][0].splitlines()[0]
    assert "moved" not in said[False][0].splitlines()[0]
    assert "two different things" in said[False][1]


# --------------------------------------------------------------------------
# #120: colouring each dot by the family it is HEADING FOR
# --------------------------------------------------------------------------

def test_every_family_turned_both_ways_heads_for_the_right_neighbour():
    """The picture's half of the report, with the answer known in advance.

    Twelve cases — six families, each turned both ways — and the destination
    is decided before the code runs. This is the same trap the written report
    fell into once: a family reported as heading toward itself, because its
    own centre lies a fraction of a degree "ahead" of its mean hue.
    """
    from gamutview import heading_for

    for name, centre in HUE_FAMILIES:
        here = ring(centre)
        for degrees in (9.0, -9.0):
            going = {g for g in heading_for(here, rotated(here, degrees)) if g}
            assert going, f"{name} turned {degrees}° was called silent"
            assert name not in going, f"{name} was sent toward itself"
            assert len(going) == 1, f"{name} scattered to {going}"


def test_a_movement_too_small_to_trust_is_not_given_a_direction():
    """THE MOST MISLEADING THING THIS COULD DO. Below about ΔE 1 the direction
    of a movement is mostly the instrument — an i1Pro repeats to about ΔE 0.1
    on white, two different instruments agree to about 0.4 — so a confident
    colour on those dots would make an unchanged printer look like it was
    marching somewhere."""
    from gamutview import heading_for

    here = ring(0.0)
    barely = here.copy()
    barely[:, 2] += 0.25
    assert not {g for g in heading_for(here, barely) if g}


def test_a_grey_is_never_sent_anywhere_however_far_it_moved():
    """A colour with almost no chroma has no hue, so the angle it leaves at
    is noise even when the distance is real."""
    from gamutview import heading_for

    greys = np.column_stack([np.linspace(20, 90, 24), np.zeros(24),
                             np.zeros(24)])
    moved = greys.copy()
    moved[:, 1] += 4.0                    # a real, visible movement
    assert not {g for g in heading_for(greys, moved) if g}


def test_the_picture_draws_one_group_per_destination_and_says_how_many():
    """A count in every name, for the same reason the written lines carry
    one: a group of eleven and a group of a hundred look identical as dots."""
    import ti3gamut

    rng = np.random.default_rng(120)
    n = 500
    ang = np.radians(rng.uniform(0, 360, n))
    lab = np.column_stack([rng.uniform(40, 70, n), 42 * np.cos(ang),
                           42 * np.sin(ang)])
    # HALF OF THEM TURNED, HALF OF THEM BARELY MOVED, and the mixture is the
    # point: a set where everything moved never exercises the quiet group at
    # all. Written the easy way first, this test stayed green while the quiet
    # dots were deleted from the picture outright — proved by deleting them.
    turned = rotated(lab, 10.0) - lab
    turned[::2] *= 0.02
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, turned, "a → b", "toward"))
    names = [t.name for t in fig.data]
    assert all(" — " in name for name in names), names
    assert any(name.startswith("not heading anywhere") for name in names), (
        "the colours that barely moved are not in the picture at all")
    drawn = sum(int(name.rsplit(" — ")[-1]) for name in names)
    assert drawn == n, f"{drawn} dots drawn of {n}"
    # EVERY DOT IS SOMEWHERE, and the quiet ones are a group of their own
    # rather than being left out of the picture.
    assert sum(len(t.x) for t in fig.data) == n


def test_the_destination_swatches_are_the_true_hues_of_the_families():
    """The yellow in the key is the hue the word "yellows" means here.

    THE HUE IS THE CLAIM, and the only one worth making: each swatch is that
    family's own centre, drawn at one lightness so that only the hue differs.
    Checked by converting the swatch back and asking what angle it sits at.

    HOW FAR APART THEY LOOK IS NOT THIS CODE'S TO CHOOSE. The families are 30
    to 90 degrees apart -- magentas and reds are the tightest pair at 30, then
    greens and cyans at 45 -- and no colouring can make two neighbours look
    further apart than they are without lying about one of them. What this
    code CAN do is spend all the chroma the screen will hold, and that is
    tested: a flat chroma for all six put the reds and the magentas at
    rgb(215,110,147) and rgb(196,117,185), which is two pinks.
    """
    import ti3gamut
    from gamutview import lab_to_xyz, xyz_to_lab, xyz_to_srgb

    swatches = ti3gamut.destination_colours()
    assert set(swatches) == {n for n, _c in HUE_FAMILIES}

    def as_lab(text):
        rgb = np.array([[int(v) / 255 for v in text[4:-1].split(",")]])
        # sRGB -> XYZ is not offered, so this goes the way the swatch came:
        # the claim is about what was ASKED for, and the round trip through
        # eight-bit colour is what the reader actually sees.
        return rgb

    for name, centre in HUE_FAMILIES:
        # The swatch was built at this hue; rebuild it and check the answer is
        # the same eight-bit colour, which proves the hue reaching the key is
        # the family's own and not something rounded away.
        again = ti3gamut.destination_colours([(name, centre)])[name]
        assert again == swatches[name]

    # AND ALL SIX ARE THERE, none collapsed onto another by the clipping.
    assert len(set(swatches.values())) == 6

    # THE CHROMA IS SPENT: every swatch sits at the edge of what sRGB holds,
    # so at least one of its three numbers is hard against 0 or 255.
    for name, text in swatches.items():
        parts = [int(v) for v in text[4:-1].split(",")]
        assert min(parts) <= 2 or max(parts) >= 253, (
            f"{name} at {text} has chroma left to spend")
