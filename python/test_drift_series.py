"""A run of profiles of one device, and what moved between the times.

Every profile here is written by hand, so a machine with a full colour
toolchain and a bare build runner give identical answers and nothing needs
installing.
"""
import struct

import pytest
from PyQt6.QtCore import Qt

from test_chart import write_matrix_profile


def dated(path, when, *, gamma: float = 2.2):
    """A profile carrying a creation date, which is what orders a run.

    Bytes 24..36 of the header, six big-endian uint16. Written after the fact
    so the one helper still makes the profile.
    """
    write_matrix_profile(path, gamma=gamma)
    raw = bytearray(path.read_bytes())
    raw[24:36] = struct.pack(">6H", *when)
    path.write_bytes(bytes(raw))
    return path


@pytest.fixture
def five_years(tmp_path):
    """One scanner drifting evenly, five years running."""
    return [dated(tmp_path / f"scan-{2019 + i}.icc",
                  (2019 + i, 6, 1, 12, 0, 0), gamma=2.20 + 0.03 * i)
            for i in range(5)]


# --- reading one profile ----------------------------------------------------

def test_the_creation_date_is_read_from_the_header(tmp_path):
    import drift_series
    p = dated(tmp_path / "a.icc", (2021, 3, 17, 9, 30, 0))
    assert drift_series.read_created(p) == (2021, 3, 17, 9, 30, 0)


def test_a_build_stamp_is_not_treated_as_a_measurement_date(tmp_path):
    """MEASURED, not guessed: six of the profiles macOS ships carry
    2022-01-01 00:00:00 exactly — Display P3, DCI(P3) RGB and ACESCG Linear
    among them. Ordering a run by a date like that invents the very history
    the reader is trying to read."""
    import drift_series
    p = dated(tmp_path / "stamped.icc", (2022, 1, 1, 0, 0, 0))
    assert drift_series.read_created(p) is None


def test_an_unset_or_impossible_date_is_no_date(tmp_path):
    import drift_series
    assert drift_series.read_created(
        dated(tmp_path / "zero.icc", (0, 0, 0, 0, 0, 0))) is None
    assert drift_series.read_created(
        dated(tmp_path / "month13.icc", (2020, 13, 1, 0, 0, 0))) is None
    assert drift_series.read_created(tmp_path / "missing.icc") is None


def test_a_file_that_will_not_read_is_named_rather_than_thrown(tmp_path):
    """A run of eight with one bad file must show the seven and name the
    eighth, not refuse the afternoon."""
    import drift_series
    bad = tmp_path / "broken.icc"
    bad.write_bytes(b"not a profile")
    entry = drift_series.inspect(bad)
    assert not entry.usable
    assert entry.trouble
    assert entry.name == "broken"


# --- putting the run in order ----------------------------------------------

def test_a_dated_run_is_ordered_by_date_whatever_order_it_arrived_in(tmp_path):
    import drift_series
    late = dated(tmp_path / "z-late.icc", (2024, 1, 1, 0, 0, 0))
    early = dated(tmp_path / "a-early.icc", (2019, 1, 1, 0, 0, 0))
    middle = dated(tmp_path / "m-mid.icc", (2021, 1, 1, 0, 0, 0))
    run = drift_series.build([late, early, middle])
    assert [e.name for e in run.usable] == ["a-early", "m-mid", "z-late"]
    assert run.ordered_by == "date"


def test_one_undated_profile_makes_the_whole_run_keep_its_given_order(tmp_path):
    """Sorting by date with one file dropped somewhere arbitrary is worse than
    admitting the order came from the user: the picture would look
    authoritative and be partly invented."""
    import drift_series
    a = dated(tmp_path / "a.icc", (2019, 1, 1, 0, 0, 0))
    b = write_matrix_profile(tmp_path / "b.icc", gamma=2.3)   # no date written
    c = dated(tmp_path / "c.icc", (2024, 1, 1, 0, 0, 0))
    run = drift_series.build([c, a, b])
    assert run.ordered_by == "the order you added them"
    assert [e.name for e in run.usable] == ["c", "a", "b"]


def test_two_profiles_made_the_same_minute_keep_a_stable_order(tmp_path):
    import drift_series
    same = (2020, 5, 5, 5, 5, 5)
    b = dated(tmp_path / "b.icc", same)
    a = dated(tmp_path / "a.icc", same, gamma=2.3)
    first = [e.name for e in drift_series.build([b, a]).usable]
    second = [e.name for e in drift_series.build([a, b]).usable]
    assert first == second == ["a", "b"], "the order must not depend on luck"


# --- the two series ---------------------------------------------------------

def test_both_series_are_computed_and_they_disagree_by_design(five_years):
    """THE WHOLE POINT. Against the first, the numbers climb; against the
    previous, they are flat. Read only the second and the answer is "nothing
    is happening"; read only the first and steady creep cannot be told from
    one bad year. A tool showing one of them misleads in one direction."""
    import drift_series
    run = drift_series.build(five_years)
    assert len(run.since_first) == 4
    assert len(run.since_previous) == 4

    climbing = [s.worst for s in run.since_first]
    assert climbing == sorted(climbing), (
        "drift from a fixed baseline cannot go down as time passes")
    assert climbing[-1] > climbing[0] * 2

    steps = [s.worst for s in run.since_previous]
    assert max(steps) < 2 * min(steps), (
        "an evenly drifting device must give evenly sized steps")


def test_the_first_step_is_the_same_in_both_series(five_years):
    """Against-the-first and against-the-previous are the same comparison for
    the second profile. If they ever differ, one of the two is pairing the
    wrong files."""
    import drift_series
    run = drift_series.build(five_years)
    assert run.since_first[0].worst == pytest.approx(
        run.since_previous[0].worst)


def test_a_run_of_exactly_two_is_a_run(tmp_path):
    """The smallest honest case, and the one that must agree with the pair
    comparison rather than being a second implementation of it."""
    import drift_series
    import ti3gamut
    a = dated(tmp_path / "a.icc", (2020, 1, 1, 0, 0, 0), gamma=2.2)
    b = dated(tmp_path / "b.icc", (2022, 1, 2, 0, 0, 0), gamma=2.4)
    run = drift_series.build([a, b])
    assert len(run.since_first) == 1
    straight = ti3gamut.compare_profiles(a, b)
    assert run.since_first[0].worst == pytest.approx(straight.worst)


def test_one_profile_alone_is_explained_not_crashed(tmp_path):
    import drift_series
    run = drift_series.build([dated(tmp_path / "a.icc", (2020, 1, 1, 0, 0, 0))])
    assert run.since_first == []
    assert any("at least two" in c for c in run.complaints)


def test_no_profiles_at_all_is_explained_not_crashed():
    import drift_series
    run = drift_series.build([])
    assert run.since_first == [] and run.complaints
    assert run.total == 0.0


# --- everything that can be wrong with a run --------------------------------

def test_mixing_device_kinds_is_refused_and_the_odd_one_named(tmp_path):
    """The grid is in device coordinates, so 50% grey asked of an RGB profile
    and of a CMYK one are not the same request."""
    import drift_series
    a = dated(tmp_path / "a.icc", (2020, 1, 1, 0, 0, 0))
    b = dated(tmp_path / "b.icc", (2021, 1, 1, 0, 0, 0))
    raw = bytearray(b.read_bytes())
    raw[16:20] = b"CMYK"
    b.write_bytes(bytes(raw))
    run = drift_series.build([a, b])
    assert run.since_first == [], "it drew a line across two different devices"
    said = " ".join(run.complaints)
    assert "same kind of device" in said
    assert "CMYK" in said and "RGB" in said


def test_a_bad_file_does_not_take_the_rest_of_the_run_with_it(tmp_path):
    import drift_series
    good = [dated(tmp_path / f"g{i}.icc", (2020 + i, 1, 1, 0, 0, 0),
                  gamma=2.2 + 0.05 * i) for i in range(3)]
    bad = tmp_path / "rubbish.icc"
    bad.write_bytes(b"nope")
    run = drift_series.build(good + [bad])
    assert len(run.usable) == 3
    assert len(run.since_previous) == 2
    assert any("rubbish.icc could not be read" in c for c in run.complaints)


def test_the_same_file_twice_is_pointed_out(tmp_path):
    """It produces a perfectly clean zero that reads as wonderful news rather
    than as the slip it is."""
    import drift_series
    a = dated(tmp_path / "a.icc", (2020, 1, 1, 0, 0, 0))
    b = dated(tmp_path / "b.icc", (2021, 1, 1, 0, 0, 0), gamma=2.4)
    run = drift_series.build([a, b, a])
    assert any("more than once" in c for c in run.complaints)


def test_profiles_read_through_different_tables_are_flagged_but_still_drawn(
        tmp_path, monkeypatch):
    """Not fatal — the reader may have a good reason — but most of what the
    line shows would be that difference rather than drift, so it is said."""
    import drift_series
    import icc_read
    a = dated(tmp_path / "a.icc", (2020, 1, 1, 0, 0, 0))
    b = dated(tmp_path / "b.icc", (2021, 1, 1, 0, 0, 0), gamma=2.4)
    tables = {a.stem: "A2B1", b.stem: "matrix"}
    monkeypatch.setattr(icc_read, "which_table",
                        lambda p: tables.get(p.stem if hasattr(p, "stem")
                                             else str(p), "matrix"))
    run = drift_series.build([a, b])
    assert run.since_first, "it should still draw, having said its piece"
    assert any("not all read the same way" in c for c in run.complaints)


# --- what the run amounts to ------------------------------------------------

def test_a_steady_drift_is_called_steady(five_years):
    import drift_series
    run = drift_series.build(five_years)
    assert run.steady
    said = drift_series.verdict(run)
    assert "steadily" in said
    assert "keep going" in said


def test_one_big_jump_is_called_out_with_the_date_it_happened(tmp_path):
    """Even steps mean it will keep creeping; one big step means something
    HAPPENED, on a date the reader can go and look up. The advice differs
    completely, so the picture must make which one it is unmissable."""
    import drift_series
    gammas = [2.20, 2.21, 2.22, 2.60, 2.61]      # one bad year in the middle
    run = drift_series.build([
        dated(tmp_path / f"y{i}.icc", (2019 + i, 1, 1, 0, 0, 0), gamma=g)
        for i, g in enumerate(gammas)])
    assert not run.steady
    said = drift_series.verdict(run)
    assert "one point rather than gradually" in said
    assert run.worst_step.before == "y2" and run.worst_step.after == "y3"
    assert "y2" in said and "y3" in said


def test_a_device_that_has_not_moved_says_so_plainly(tmp_path):
    """Nobody should be sent looking for a fault that is below the point at
    which a difference can be seen at all."""
    import drift_series
    run = drift_series.build([
        dated(tmp_path / f"n{i}.icc", (2019 + i, 1, 1, 0, 0, 0),
              gamma=2.20 + 0.001 * i) for i in range(4)])
    assert run.total < drift_series.INVISIBLE
    said = drift_series.verdict(run)
    assert "Nothing has moved" in said
    assert "below the point at which" in said


def test_the_thresholds_are_the_ones_the_rest_of_the_application_uses():
    """One vocabulary across the application, not two. A reader who has
    learned what ΔE 1 and 3 mean in the pair comparison must not meet
    different numbers here."""
    import drift_series
    assert drift_series.INVISIBLE == 1.0
    assert drift_series.OBVIOUS == 3.0


def test_a_run_of_many_stays_quick(tmp_path):
    """Twenty profiles is 38 comparisons. Measured at well under a second for
    ten, so this is a guard against a future change that makes it quadratic --
    comparing every profile with every other would be 190 rather than 38."""
    import time

    import drift_series
    many = [dated(tmp_path / f"m{i:02d}.icc", (2000 + i, 1, 1, 0, 0, 0),
                  gamma=2.2 + 0.01 * i) for i in range(20)]
    start = time.time()
    run = drift_series.build(many)
    took = time.time() - start
    assert len(run.since_first) == 19 and len(run.since_previous) == 19
    assert took < 10.0, f"a run of twenty took {took:.1f}s"


def test_the_jump_is_reported_with_the_dates_it_happened_between(tmp_path):
    """"That is what is worth chasing" is only useful with a WHEN attached.
    Naming the profiles alone invites the very question the sentence was
    meant to answer."""
    import drift_series
    gammas = [2.20, 2.21, 2.60, 2.61]
    run = drift_series.build([
        dated(tmp_path / f"y{i}.icc", (2019 + i, 4, 9, 0, 0, 0), gamma=g)
        for i, g in enumerate(gammas)])
    said = drift_series.verdict(run)
    # y1 (2.21) -> y2 (2.60) is the jump, so 2020 -> 2021. Getting this
    # wrong the first time is exactly why the sentence needs the dates in it.
    assert "2020-04-09" in said and "2021-04-09" in said, said
    assert run.worst_step.spans.count("(") == 1


def test_undated_profiles_fall_back_to_names_rather_than_a_blank(tmp_path):
    """A run the user ordered by hand still has to name its worst step."""
    import drift_series
    run = drift_series.build([
        write_matrix_profile(tmp_path / "before.icc", gamma=2.2),
        write_matrix_profile(tmp_path / "after.icc", gamma=2.7),
    ])
    step = run.worst_step
    assert step is not None
    assert step.spans == "before to after"
    assert "(" not in step.spans, "an empty bracket where a date should be"


# --- the picture ------------------------------------------------------------

def test_both_lines_are_drawn_on_one_pair_of_axes(five_years):
    """Apart, on two charts, the eye reads each as its own story and the whole
    point — that flat steps add up to a long way — is lost in the gap."""
    import drift_series
    fig = drift_series.figure(drift_series.build(five_years))
    assert len(fig.data) == 2
    names = " ".join(t.name for t in fig.data)
    assert "altogether" in names and "each time" in names


def test_the_axis_is_spaced_by_real_time_when_the_dates_allow_it(tmp_path):
    """NOT A NICETY. The question is "how fast is it drifting", and an axis
    that puts 2019, 2020, 2021 and 2024 at even intervals draws a steady line
    through a device that was quiet for three years and then moved. The rate
    would be read straight off a picture that had thrown the rate away."""
    import drift_series
    years = [2019, 2020, 2021, 2024]
    run = drift_series.build([
        dated(tmp_path / f"u{y}.icc", (y, 6, 1, 0, 0, 0), gamma=2.20 + 0.03 * i)
        for i, y in enumerate(years)])
    fig = drift_series.figure(run)
    assert fig.layout.xaxis.type == "date"
    # THE FIRST PROFILE IS ON THE LINE NOW, at zero, so the run's own start
    # is visible rather than implied. Reported by Basti: the cumulative line
    # began at a whole year of drift, which reads as where the run began.
    assert list(fig.data[0].x) == ["2019-06-01", "2020-06-01", "2021-06-01",
                                   "2024-06-01"]
    assert fig.data[0].y[0] == 0.0


def test_an_undated_run_falls_back_to_names_rather_than_inventing_dates(
        tmp_path):
    """A mixture of real dates and invented ones is worse than an honest
    list: the picture would look authoritative and be partly made up."""
    import drift_series
    run = drift_series.build([
        write_matrix_profile(tmp_path / f"n{i}.icc", gamma=2.2 + 0.05 * i)
        for i in range(3)])
    fig = drift_series.figure(run)
    assert fig.layout.xaxis.type == "category"
    assert list(fig.data[0].x) == ["n0", "n1", "n2"]   # the first, at zero
    assert fig.data[0].y[0] == 0.0


def test_the_bands_say_what_the_numbers_mean_in_words(five_years):
    """ΔE is not a unit anybody has intuitions about, and a reader who learned
    1 and 3 from the pair comparison must not meet a second vocabulary."""
    import drift_series
    fig = drift_series.figure(drift_series.build(five_years))
    said = " ".join(str(a.text or "") for a in fig.layout.annotations)
    assert "nobody can see this" in said
    assert "anybody can see this" in said


def test_a_run_too_short_to_draw_gives_an_empty_picture_not_a_crash(tmp_path):
    import drift_series
    for paths in ([], [dated(tmp_path / "one.icc", (2020, 1, 1, 0, 0, 0))]):
        fig = drift_series.figure(drift_series.build(paths))
        assert len(fig.data) == 0


def test_the_picture_follows_the_light_and_dark_settings(five_years):
    """The rest of the application switches; a chart that did not would be the
    one white rectangle in a dark window."""
    import drift_series
    run = drift_series.build(five_years)
    dark = drift_series.figure(run, mode="dark")
    light = drift_series.figure(run, mode="light")
    assert dark.layout.paper_bgcolor != light.layout.paper_bgcolor
    assert dark.layout.font.color != light.layout.font.color


# --- the window ------------------------------------------------------------
#
# The dialog is built here WITHOUT ITS GRAPH VIEW (preview=False). I first
# built it complete, reasoning that one QWebEngineView is not the whole
# application -- and Windows disproved that: the suite stopped dead at 32%
# with seven failures and no summary at all, while macOS ran it happily. The
# project had already written this down, in test_chart_panel and
# test_audit_script; I did not take it seriously enough until it cost a
# release build.
#
# Everything below is computed without drawing: the run, the verdict, the
# table and the saved page's HTML. The graph itself is proved by the driver
# scripts, which run the real application.

@pytest.fixture(scope="module")
def app():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import gamut_app                                     # noqa: F401
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(["test"])


def test_the_window_lists_every_profile_with_its_date(app, five_years):
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    assert dialog._list.count() == 5
    rows = [dialog._list.item(i).data(Qt.ItemDataRole.AccessibleTextRole) for i in range(5)]
    assert all("20" in r for r in rows), rows
    assert "scan-2019" in rows[0] and "scan-2023" in rows[4]
    dialog.close()


def test_the_same_profile_cannot_be_added_twice(app, five_years):
    """Adding a folder twice is an ordinary slip, and the duplicate would
    show as a step of exactly zero — which reads as good news."""
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    dialog.add(five_years)
    app.processEvents()
    assert dialog._list.count() == 5
    dialog.close()


def test_removing_one_leaves_the_rest(app, five_years):
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    dialog._list.setCurrentRow(2)
    dialog._on_remove()
    app.processEvents()
    assert dialog._list.count() == 4
    assert all(five_years[2].stem not in dialog._list.item(i).data(Qt.ItemDataRole.AccessibleTextRole)
               for i in range(4))
    dialog.close()


def test_nothing_can_be_saved_until_there_is_something_to_save(app, tmp_path):
    """A save button that opens a file dialog and then writes an empty graph
    is worse than one that is plainly not available yet."""
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    app.processEvents()
    assert not dialog._save_btn.isEnabled()
    assert not dialog._table_btn.isEnabled()
    dialog.add([dated(tmp_path / "only.icc", (2020, 1, 1, 0, 0, 0))])
    app.processEvents()
    assert not dialog._save_btn.isEnabled(), "one profile is not a run"
    dialog.add([dated(tmp_path / "second.icc", (2021, 1, 1, 0, 0, 0),
                      gamma=2.4)])
    app.processEvents()
    assert dialog._save_btn.isEnabled()
    dialog.close()


def test_the_table_carries_the_caveat_and_the_verdict(app, five_years):
    """A row of figures outlives the window that explained it."""
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    flat = " | ".join(str(c) for row in dialog.rows() for c in row)
    assert "NOT how far the device drifted" in flat
    assert "in short" in flat
    assert "ordered by" in flat
    dialog.close()


def test_a_bad_file_is_shown_in_the_list_rather_than_silently_dropped(
        app, tmp_path, five_years):
    """Dropping it would leave somebody counting four rows where they added
    five and wondering which one went."""
    import gamut_app
    bad = tmp_path / "broken.icc"
    bad.write_bytes(b"not a profile")
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years + [bad])
    app.processEvents()
    rows = [dialog._list.item(i).data(Qt.ItemDataRole.AccessibleTextRole) for i in range(dialog._list.count())]
    assert any("broken" in r and "could not be read" in r for r in rows), rows
    dialog.close()


def test_the_window_follows_the_light_and_dark_setting(app, five_years):
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, appearance="dark", preview=False)
    dialog.add(five_years)
    app.processEvents()
    # ASKED OF THE FIGURE, not of the view, because these checks build the
    # window without one -- see TimelineDialog's docstring for why.
    import drift_series
    dark = drift_series.figure(dialog._run, mode="dark")
    dialog.look("light")
    app.processEvents()
    light = drift_series.figure(dialog._run, mode=dialog._appearance)
    assert dialog._appearance == "light"
    assert dark.layout.paper_bgcolor != light.layout.paper_bgcolor, (
        "the graph kept its dark colours in a light window")
    dialog.close()


def test_only_profiles_are_accepted_when_files_are_dropped(app):
    """A .ti3 dropped here is a measurement, which this window cannot follow
    over time — taking it would put a row in the list that can never work."""
    import inspect

    import gamut_app
    source = inspect.getsource(gamut_app.TimelineDialog.dropEvent)
    assert '".icc", ".icm"' in source


def test_the_saved_page_leaves_room_for_the_words(app, five_years):
    """MEASURED REGRESSION. The drawing library's own full-page output fills
    the viewport — 96% to 99% of the first screen across ten window sizes in
    both engines — which put the verdict and the caveat below the fold on
    every one of them. The graph would have arrived without the sentence
    saying what it does not mean, which is exactly the failure this feature is
    most exposed to: a rising line read as proof a device is failing.

    check_layout.py holds every page in this project between 55% and 85%. This
    keeps the page written here inside that band by construction, so the
    library's default cannot quietly come back.
    """
    import gamut_app
    import drift_series
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    html = dialog.page_html(drift_series.figure(dialog._run))
    assert "68vh" in html, "the graph is no longer given a bounded height"
    assert "min-height:260px" in html, "it can collapse on a very short window"
    assert "full_html" not in html
    # And the words really are in it, not merely allowed for.
    assert "What this does not tell you" in html
    assert "not how far the device drifted" in html
    assert "ΔE2000" in html
    dialog.close()


def test_the_saved_page_is_self_contained(app, five_years):
    """One file that opens anywhere. A page that fetched its drawing library
    from the internet would be a blank rectangle on a machine that is offline,
    or in five years when the address has moved."""
    import gamut_app
    import drift_series
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    html = dialog.page_html(drift_series.figure(dialog._run))
    # THE PROPERTY IS "NOTHING IS FETCHED", not "a string is absent". The
    # first version of this looked for "cdn.plot.ly" anywhere in the file and
    # failed -- because that address is a default constant INSIDE the bundled
    # library, which being present is the very proof it was inlined.
    import re as _re
    fetches = _re.findall(r'<(?:script|link)[^>]*(?:src|href)="([^"]*)"', html)
    remote = [u for u in fetches if not u.startswith(("data:", "#"))]
    assert not remote, f"the page fetches something: {remote[:3]}"
    assert len(html) > 500_000, "the drawing library does not look inlined"
    dialog.close()


# --- it went away and came back ---------------------------------------------
#
# Asked by Basti: "what if a profile drifts in one direction for two years and
# then back to the other, matching the initial one again -- would this be
# visible in the viewer somehow?"
#
# The picture always showed it: the cumulative line arches up and comes back
# while the step line stays flat, and two lines disagreeing in that particular
# way mean one thing only. The WORDS did not. Measured on five profiles built
# to do exactly that, the verdict read only the two ends and printed "Nothing
# has moved that anybody could see" about a device that had been dE 5.39 away
# in the middle year -- plainly visible, and saved into the page and the table
# where it outlives the chart that would have corrected it.

def out_and_back(tmp_path, ending: float = 2.20):
    """Five years: away for two, then back to (nearly) where it started."""
    bends = [2.20, 2.26, 2.32, 2.26, ending]
    return [dated(tmp_path / f"back-{2019 + i}.icc",
                  (2019 + i, 6, 1, 12, 0, 0), gamma=g)
            for i, g in enumerate(bends)]


def test_the_two_series_disagree_in_the_way_that_means_it_came_back(tmp_path):
    """The picture's half of the answer, as numbers.

    Cumulative rises then FALLS; each step stays about the same size. Neither
    on its own says "it came back" -- the pair does.
    """
    import drift_series
    run = drift_series.build(out_and_back(tmp_path))
    cumulative = [s.worst for s in run.since_first]
    steps = [s.worst for s in run.since_previous]
    assert cumulative[1] > cumulative[0], "it should be going away at first"
    assert cumulative[-1] < max(cumulative), (
        f"it never comes back: {cumulative}")
    assert max(steps) <= 2.0 * min(steps), (
        f"the year-on-year line should stay flat through all of it: {steps}")


def test_a_run_that_came_back_is_recognised_as_one(tmp_path):
    import drift_series
    run = drift_series.build(out_and_back(tmp_path))
    assert run.came_back
    assert run.furthest.worst > run.total, (
        "the furthest it ever got must be further than where it ended")


def test_the_verdict_names_the_excursion_and_when_it_happened(tmp_path):
    """The fault this whole block exists for: the sentence must not say
    'nothing has moved' about a device that was visibly wrong for a year."""
    import drift_series
    run = drift_series.build(out_and_back(tmp_path))
    said = drift_series.verdict(run)
    assert "Nothing has moved" not in said, said
    assert "went away and came back" in said, said
    assert f"{run.furthest.worst:.2f}" in said, (
        f"the size of the excursion is not in the sentence: {said}")
    assert "2021" in said, f"the reader is not told WHEN: {said}"


def test_ending_exactly_where_it_started_is_still_reported(tmp_path):
    """The extreme of it: total dE 0.00 and a real excursion behind it."""
    import drift_series
    run = drift_series.build(out_and_back(tmp_path, ending=2.20))
    assert run.total < drift_series.INVISIBLE
    assert run.came_back
    assert "went away and came back" in drift_series.verdict(run)


def test_a_run_that_only_creeps_is_NOT_called_a_return(tmp_path):
    """The false positive that would make the new sentence worthless.

    A device drifting one way and never coming back must still be told it is
    drifting one way and will keep going.
    """
    import drift_series
    steady = [dated(tmp_path / f"creep-{2019 + i}.icc",
                    (2019 + i, 6, 1, 12, 0, 0), gamma=2.20 + 0.03 * i)
              for i in range(5)]
    run = drift_series.build(steady)
    assert not run.came_back, (
        f"a straight creep was read as a return: "
        f"{[round(s.worst, 2) for s in run.since_first]}")
    assert "went away and came back" not in drift_series.verdict(run)


def test_a_wobble_too_small_to_see_is_not_announced(tmp_path):
    """A run that wanders by less than anybody can see is not a story.

    Below dE 1 there is nothing to warn about, and a warning about an
    invisible difference is how a useful sentence becomes noise.
    """
    import drift_series
    tiny = [dated(tmp_path / f"tiny-{2019 + i}.icc",
                  (2019 + i, 6, 1, 12, 0, 0), gamma=g)
            for i, g in enumerate([2.200, 2.203, 2.206, 2.203, 2.200])]
    run = drift_series.build(tiny)
    if run.furthest.worst < drift_series.INVISIBLE:
        assert not run.came_back
        assert "went away and came back" not in drift_series.verdict(run)


# --- from the trend, to one step's heat-map ---------------------------------
#
# Basti, twice, the second time: "if i selected multiple profiles, have them in
# the trend view, can i then choose two of them for the heatmap comparison
# view (i guess more at once would not be possible)?"
#
# He is right that more than two is impossible: every dot is painted by the dE
# between exactly TWO profiles, and a third would need a second colour on the
# same dot. A run is made of steps and each step IS a pair, so the step is the
# unit -- which is also the unit both lines and the exported table already use.

def test_the_chooser_offers_the_graph_then_every_step_then_the_whole_run(
        app, five_years):
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    combo = dialog._picture_of
    said = [combo.itemText(i) for i in range(combo.count())]
    # the graph, four steps, the whole run, and any-two-you-choose
    assert len(said) == 1 + 4 + 1 + 1, said
    assert dialog._chosen_pair() is None, "it must start on the graph"
    pairs = [combo.itemText(i) for i in range(combo.count())
             if (combo.itemData(i) or (None,))[0] in ("step", "whole")]
    assert all("→" in s and "ΔE" in s for s in pairs), (
        f"a step entry must name both profiles and its own size: {pairs}")
    dialog.close()


def test_a_step_resolves_to_the_two_files_it_names(app, five_years):
    """BY PATH, NOT BY NAME. Two profiles of one device very often share a
    stem, and looking one up by name would compare the wrong file and print a
    perfectly plausible number under it."""
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    dialog._picture_of.setCurrentIndex(1)
    a, b, spans = dialog._chosen_pair()
    assert a == five_years[0] and b == five_years[1], (a, b)
    assert "scan-2019" in spans and "scan-2020" in spans, spans
    dialog.close()


def test_the_last_entry_is_the_whole_run_first_against_last(app, five_years):
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    # FOUND BY DATA, not by position: "any two you choose" now sits after it,
    # and a test that counts from the end would quietly move to that instead.
    at = gamut_app._entry_at(dialog._picture_of, ("whole", 0))
    assert at >= 0, "the whole run is not on offer"
    dialog._picture_of.setCurrentIndex(at)
    a, b, _spans = dialog._chosen_pair()
    assert a == five_years[0] and b == five_years[-1], (a, b)
    dialog.close()


def test_two_profiles_do_not_get_the_same_picture_listed_twice(app, tmp_path):
    """With one step, 'the whole run' IS that step -- offering both would be
    two entries for one picture, which is how somebody comes to believe they
    are looking at two different answers."""
    import gamut_app
    pair = [dated(tmp_path / f"two-{2019 + i}.icc", (2019 + i, 6, 1, 12, 0, 0),
                  gamma=2.20 + 0.05 * i) for i in range(2)]
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(pair)
    app.processEvents()
    assert dialog._picture_of.count() == 2, [
        dialog._picture_of.itemText(i)
        for i in range(dialog._picture_of.count())]
    dialog.close()


def test_one_profile_alone_offers_no_comparison(app, tmp_path):
    import gamut_app
    only = [dated(tmp_path / "alone.icc", (2021, 6, 1, 12, 0, 0))]
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(only)
    app.processEvents()
    assert not dialog._picture_of.isEnabled()
    assert dialog._chosen_pair() is None
    dialog.close()


def test_removing_a_profile_never_leaves_a_different_pair_under_one_label(
        app, five_years):
    """THE TRAP THIS WHOLE REBUILD EXISTS FOR, and the worst way it could
    fail: taking a profile out of the middle changes which pairs there ARE, so
    a remembered index would go on showing an entry whose words name one pair
    while the picture shows another. Nothing would look wrong."""
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    dialog._picture_of.setCurrentIndex(2)
    before = dialog._chosen_pair()
    assert before is not None
    dialog._list.setCurrentRow(1)
    dialog._on_remove()
    app.processEvents()
    after = dialog._chosen_pair()
    label = dialog._picture_of.currentText()
    assert after is None or after[2] in label, (
        f"showing {after[2]!r} under the label {label!r}")
    dialog.close()


def test_the_file_name_offered_for_a_saved_cloud_is_writable(app):
    """An arrow is a fine thing to read and a poor thing to put in a name."""
    import gamut_app
    stem = gamut_app._clean_stem("printer-2019 → printer-2021")
    assert "→" not in stem and " " not in stem, stem
    assert stem.strip("-") == stem and stem, stem
    assert len(gamut_app._clean_stem("x" * 400)) <= 120
    assert gamut_app._clean_stem("→ →") == "comparison"


def test_the_words_under_the_picture_are_about_that_picture(app, five_years):
    """FOUND BY LOOKING AT THE SCREENSHOT, not at the code.

    The verdict was written once from the whole run and left there whichever
    picture was showing, so choosing a single step put "it has drifted
    steadily, from the first to the last" under a cloud of one year. The
    caveat had the same fault in the other direction.
    """
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()

    graph = dialog._verdict.text()
    assert "scan-2019" in graph and "scan-2023" in graph, graph

    dialog._picture_of.setCurrentIndex(1)
    dialog._draw()
    step = dialog._verdict.text()
    assert step != graph, "the sentence did not follow the picture"
    assert "scan-2019" in step and "scan-2020" in step, step
    assert "scan-2023" not in step, (
        f"a picture of one step is described in terms of the whole run: {step}")
    assert "these two PROFILES" in dialog._caution.text(), (
        dialog._caution.text())

    # And back again, because a one-way change is half a fix.
    dialog._picture_of.setCurrentIndex(0)
    dialog._draw()
    assert dialog._verdict.text() == graph
    dialog.close()


def test_a_step_nobody_could_see_says_so_and_counts_nothing(app, five_years):
    """Every step of this run is dE 0.73 -- below the point at which a
    difference is visible at all. Reciting "412 colours moved by more than 1"
    of a step where none did would be noise dressed as detail."""
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    dialog._picture_of.setCurrentIndex(1)
    dialog._draw()
    said = dialog._verdict.text()
    assert "nothing here that anybody could see" in said, said
    assert "more than 1" not in said, said
    dialog.close()


def test_a_step_anybody_could_see_quotes_the_usual_two_thresholds(
        app, tmp_path):
    """A second vocabulary for the same idea is how a reader stops trusting
    either. 1 and 3 mean the same here as in every other readout."""
    import gamut_app
    wide = [dated(tmp_path / f"wide-{2019 + i}.icc", (2019 + i, 6, 1, 12, 0, 0),
                  gamma=2.20 + 0.30 * i) for i in range(3)]
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(wide)
    app.processEvents()
    dialog._picture_of.setCurrentIndex(1)
    dialog._draw()
    said = dialog._verdict.text()
    assert "more than 1" in said and "more than 3" in said, said
    assert "ΔE" in said and "average" in said, said
    assert "largest and reddest" in said, (
        f"the sentence must say where to look in the picture: {said}")
    dialog.close()


def test_the_chosen_picture_survives_adding_another_profile(app, tmp_path):
    """THE BUG THIS FOUND, and it was not the one being looked for.

    The chooser is rebuilt whenever the run changes and puts the reader back
    on what they were looking at -- through `findData`. Qt compares stored
    item data as QVariants, and for a Python object it can only do that by
    identity, so findData(("whole", 0)) matches an item holding ("whole", 0)
    only when the two tuples are the same object. They are when both literals
    sit in one code object -- which is what a small isolated check does, and
    is why it appeared to work -- and are not across modules. Measured on the
    real window: the item was at index 5 and findData returned -1.

    So every add or remove quietly threw the reader back to the graph, and the
    check that should have caught it read that fallback as the right answer to
    a different question.
    """
    import gamut_app
    five = [dated(tmp_path / f"keep-{2019 + i}.icc", (2019 + i, 6, 1, 12, 0, 0),
                  gamma=2.20 + 0.03 * i) for i in range(5)]
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five[:4])
    app.processEvents()
    at = gamut_app._entry_at(dialog._picture_of, ("step", 1))
    assert at > 0
    dialog._picture_of.setCurrentIndex(at)
    chosen = dialog._picture_of.currentText()

    dialog.add(five[4:])                      # a new profile arrives
    app.processEvents()
    assert dialog._picture_of.currentText() == chosen, (
        f"choosing {chosen!r} was lost when the run changed; now on "
        f"{dialog._picture_of.currentText()!r}")
    assert dialog._chosen_pair() is not None
    dialog.close()


def test_any_two_profiles_can_be_compared_not_only_neighbours(app, five_years):
    """Basti: "can i choose any two profiles from the trend for the direct
    comparison and then go back to the full overview?"

    The steps are shortcuts, not the whole of it: the profile from before a
    head clean and the one six months later need not sit next to each other.
    """
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    at = gamut_app._entry_at(dialog._picture_of, ("pair", 0))
    assert at > 0, "there is no way to choose a pair by hand"
    dialog._picture_of.setCurrentIndex(at)
    dialog._pair_from.setCurrentIndex(1)      # the second and the fifth,
    dialog._pair_to.setCurrentIndex(4)        # which are not neighbours
    a, b, spans = dialog._chosen_pair()
    assert a == five_years[1] and b == five_years[4], (a, b)
    assert "scan-2020" in spans and "scan-2023" in spans, spans
    dialog.close()


def test_and_back_to_the_overview_again(app, five_years):
    """The second half of his question, which is the one that would be
    infuriating to get wrong: having gone to a pair, can you get back?"""
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    dialog._picture_of.setCurrentIndex(
        gamut_app._entry_at(dialog._picture_of, ("step", 1)))
    assert dialog._chosen_pair() is not None
    dialog._picture_of.setCurrentIndex(0)
    assert dialog._chosen_pair() is None, "the graph is not reachable again"
    dialog._draw()
    assert "scan-2019" in dialog._verdict.text(), dialog._verdict.text()
    dialog.close()


def test_the_same_profile_on_both_sides_is_refused_and_explained(
        app, five_years):
    """A profile against itself is identical everywhere, and a cloud of
    nothing-happened reads as good news about a device nobody asked about."""
    import gamut_app
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(five_years)
    app.processEvents()
    dialog._picture_of.setCurrentIndex(
        gamut_app._entry_at(dialog._picture_of, ("pair", 0)))
    dialog._pair_from.setCurrentIndex(2)
    dialog._pair_to.setCurrentIndex(2)
    assert dialog._chosen_pair() is None
    assert "same" in dialog._complaints.text().lower() or \
           "both boxes" in dialog._complaints.text().lower(), (
        dialog._complaints.text())
    dialog.close()


def test_the_sentence_does_not_send_you_looking_for_red_that_is_not_there(
        app, tmp_path):
    """FOUND IN THE SCREENSHOT of the direction view.

    "The ones that moved most are the largest and reddest dots" is true of
    the distance picture and false of the three direction ones, whose dots
    are teal and orange and whose ends mean opposite things rather than more
    and less of one thing.
    """
    import gamut_app
    wide = [dated(tmp_path / f"dir-{2019 + i}.icc", (2019 + i, 6, 1, 12, 0, 0),
                  gamma=2.20 + 0.30 * i) for i in range(3)]
    dialog = gamut_app.TimelineDialog(None, preview=False)
    dialog.add(wide)
    app.processEvents()
    dialog._picture_of.setCurrentIndex(
        gamut_app._entry_at(dialog._picture_of, ("step", 0)))

    dialog._draw()
    assert "reddest" in dialog._verdict.text(), "the distance view lost its cue"

    for i in range(dialog._coloured_by.count()):
        if dialog._coloured_by.itemData(i) == "L":
            dialog._coloured_by.setCurrentIndex(i)
            break
    dialog._draw()
    said = dialog._verdict.text()
    assert "reddest" not in said, said
    assert "lighter or darker" in said, said
    # AND IT SAYS WHICH WAY, which is the entire point of the view.
    assert ("gone lighter" in said or "gone darker" in said), said
    assert "no change" in said, said
    dialog.close()


# --- the reference profile is on the chart ----------------------------------
#
# Basti, from a phone, looking at page 19: "such an overview should also show
# the 2019 reference as the reference point at zero. also the 2020 value has no
# 2020 label and does not seem to be on the exact line that would represent
# 2020. or is this because the profiles were not created in the same distance
# from a time point of view?"
#
# Right about both, and his own explanation was the one thing it was not:
# measured, all four gaps in that run are exactly 12 months. Both came from one
# root -- the first profile was not plotted, so the cumulative line began at a
# whole year of drift, and the padded axis began five days after the 2020 tick
# would have fallen.

def test_the_first_profile_is_drawn_at_zero(app, five_years):
    import drift_series
    run = drift_series.build(five_years)
    fig = drift_series.figure(run)
    cumulative = next(t for t in fig.data
                      if t.name and "altogether" in t.name)
    assert len(cumulative.x) == len(run.usable), (
        "every profile should be on the cumulative line, the first included")
    assert cumulative.y[0] == 0.0, (
        f"the run starts where it starts: {cumulative.y[0]}")
    assert "2019" in str(cumulative.x[0]), cumulative.x[0]


def test_the_step_line_still_starts_at_the_second_profile(app, five_years):
    """It has no previous to be measured from, and that difference between the
    two lines is worth seeing rather than papering over with a zero."""
    import drift_series
    run = drift_series.build(five_years)
    fig = drift_series.figure(run)
    steps = next(t for t in fig.data if t.name and "each time" in t.name)
    assert len(steps.x) == len(run.usable) - 1
    assert steps.y[0] > 0.0


def test_every_profile_gets_a_tick_of_its_own(app, five_years):
    """A profile made in March sits between two round years with nothing
    naming it, which is what Basti met."""
    import drift_series
    run = drift_series.build(five_years)
    fig = drift_series.figure(run)
    ticks = list(fig.layout.xaxis.ticktext or [])
    assert len(ticks) == len(run.usable), ticks
    for entry in run.usable:
        assert any(str(entry.when[0]) in t for t in ticks), (entry.name, ticks)


def test_two_profiles_in_one_year_are_told_apart_on_the_axis(app, tmp_path):
    """Naming a tick by its year alone is only unambiguous while there is one
    profile per year; two would otherwise wear the same label."""
    import drift_series
    twice = [dated(tmp_path / "spring.icc", (2021, 3, 1, 9, 0, 0), gamma=2.20),
             dated(tmp_path / "autumn.icc", (2021, 9, 1, 9, 0, 0), gamma=2.26),
             dated(tmp_path / "later.icc", (2022, 3, 1, 9, 0, 0), gamma=2.32)]
    fig = drift_series.figure(drift_series.build(twice))
    ticks = list(fig.layout.xaxis.ticktext or [])
    assert len(set(ticks)) == len(ticks), f"two ticks read the same: {ticks}"
    assert all("-" in t for t in ticks), ticks


def test_the_axis_makes_room_for_the_first_profile(app, five_years):
    """The padding used to be measured from the SECOND profile, which is what
    put the axis five days the wrong side of a tick."""
    import drift_series
    run = drift_series.build(five_years)
    fig = drift_series.figure(run)
    low = str(fig.layout.xaxis.range[0])
    assert low < "{:04d}-{:02d}-{:02d}".format(*run.usable[0].when[:3]), (
        f"the first profile is at or outside the edge of the axis: {low}")


def test_the_axis_title_is_short_enough_for_a_short_window(five_years):
    """IT WAS MEASURED AGAINST THE WRONG THING. "ΔE2000 / the biggest
    difference" on two lines was checked at ten window sizes in two engines --
    all of them the SAVED PAGE, where the graph gets 68% of the screen. The
    application's own pane is about 200px tall, and there the second line, 153
    pixels when stood on end, runs through the caption; at 200px it starts
    outside the plot altogether.

    A title that cannot grow taller than the pane cannot collide with
    anything, so this pins the shape rather than re-measuring the pixels: one
    line, no break in it, and the meaning carried by the caption instead.
    """
    import drift_series

    fig = drift_series.figure(drift_series.build(five_years), mode="dark")
    axis_title = fig.layout.yaxis.title.text
    assert "<br>" not in axis_title, (
        "a two-line axis title is 153px stood on end and does not fit a 200px "
        "pane")
    assert axis_title == "ΔE2000"
    # and what it MEANS has not simply been dropped
    assert "biggest difference" in fig.layout.title.text


# --- the run panel in the column, and the answer being reachable ------------


def _settle(app, seconds=0.4):
    """Let Qt do its own work. This project does not use pytest-qt."""
    import time
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.002)


@pytest.fixture(scope="module")
def column():
    """ONE window for all three of these, and that is not tidiness.

    Each of them wants a real main window -- what is under test is a chain
    through the layout, not a calculation -- and building a third one in a
    single process crashes: QWebEngineView's page is created per window, and
    the third construction went down inside WebContentsAdapter with a stack
    of QtWebEngineCore and no Python frame to blame. Two passed, three did
    not, which is exactly the kind of thing that reads as a flaky test.

    So the window is built once and each test puts back what it changed.
    """
    from PyQt6.QtWidgets import QApplication, QScrollArea

    import gamut_app

    app = QApplication.instance() or QApplication([])
    win = gamut_app.GamutApp([])
    win.resize(1280, 800)
    win.show()
    _settle(app, 1.5)
    area = win.findChild(QScrollArea)
    yield app, win, area, win._timeline
    win.close()
    _settle(app, 0.2)


@pytest.fixture
def fresh(column):
    """The window handed back the way it was found."""
    app, win, area, panel = column
    was_paths = panel._paths
    was_rebuild = panel._rebuild
    was_bring = panel._bring_the_answer_into_view
    win._who_owns.setText("")
    area.verticalScrollBar().setValue(0)
    _settle(app, 0.2)
    yield app, win, area, panel
    panel._paths = was_paths
    panel._rebuild = was_rebuild
    panel._bring_the_answer_into_view = was_bring
    win._who_owns.setText("")
    area.verticalScrollBar().setValue(0)
    _settle(app, 0.1)


def test_adding_a_run_scrolls_the_column_to_it(fresh):
    """A run's answer must not arrive below the fold with nothing going to it.

    MEASURED IN THE REAL WINDOW BEFORE THIS EXISTED, at 1280x800 with four
    profiles added: "What this is telling you" sits 925 px down the column,
    the pane shows to 687, and adding the run moved the scroll from 0 to 0.
    The reader clicks Add profiles…, a graph fills the big view, and the
    sentence saying what it MEANS is 238 px below anything on screen.

    This drives the real window rather than reading the source, because the
    thing that can break is not a line of code but a chain: `add` has to call
    it, it has to find the column, and the column has to have been laid out
    by the time it asks. Any one of those going missing leaves the reader
    exactly where they were, and only a window can tell you that.
    """
    import pathlib

    app, win, area, panel = fresh
    bar = area.verticalScrollBar()
    assert bar.value() == 0

    # A RUN WITHOUT READING ANY PROFILES. What is under test is the scroll,
    # not the arithmetic, and four real profiles cost twelve seconds of a
    # gate that runs in twenty.
    panel._paths = [pathlib.Path("printer-2019.icc"),
                    pathlib.Path("printer-2024.icc")]
    panel._bring_the_answer_into_view()
    _settle(app, 0.5)

    inner = area.widget()
    top = panel.mapTo(inner, panel.rect().topLeft()).y()
    assert bar.value() > 0, (
        "adding a run left the column where it was, so the run's answer is "
        "still below the fold")
    assert abs(bar.value() - min(top, bar.maximum())) <= 2, (
        f"the column stopped at {bar.value()} rather than at the panel's own "
        f"top edge, {top}")

    # AND IT IS `add` THAT ASKS. The method working is half of it; the user's
    # own action reaching it is the other half, and that half is one line
    # that could be deleted without a single test noticing.
    asked = []
    panel._bring_the_answer_into_view = lambda: asked.append(True)
    panel._rebuild = lambda *a, **k: None
    panel.add([pathlib.Path("printer-2025.icc")])
    assert asked, "add() no longer brings the run's answer into view"


def test_an_empty_run_does_not_move_the_column(fresh):
    """Nothing added, nothing to go to.

    THE FIRST VERSION OF THIS TEST GUARDED NOTHING, and the mutation caught
    it rather than the other way round. It built the standalone dialog,
    deleted the `_hosted` guard, and passed anyway -- because a dialog with
    no parent leaves the search for a column empty and returns on the next
    line regardless. A test whose subject cannot fail is not a test.

    What can actually fail is the other half of the same guard: the panel is
    rebuilt on every removal too, and a run emptied by "Remove them all"
    must leave the reader where they are rather than jumping to a section
    that now says nothing.
    """
    app, win, area, panel = fresh
    bar = area.verticalScrollBar()
    bar.setValue(120)
    _settle(app, 0.2)
    panel._paths = []
    panel._bring_the_answer_into_view()
    _settle(app, 0.4)
    assert bar.value() == 120, (
        "an empty run scrolled the column to a section with nothing in it")


def test_the_landing_keeps_the_line_that_says_the_view_changed_hands(fresh):
    """With a file also open, the run takes the big view -- and says so.

    FOUND BY CROSSING, NOT BY DRIVING A RUN ALONE. A run on its own is the
    only state in which landing on the panel is right: in six of the eight
    states of {a file, a comparison, a chart}, the big view stops showing
    them and starts showing the run, and the single line above this panel is
    the only thing that says so. Landing on the panel's own top edge
    scrolled straight past it in all six.

    The line was visible before any of the scrolling was built -- because
    nothing scrolled at all -- so a fix for one fault had quietly made
    another. This pins the order: when there is something to explain, the
    explanation is where the view starts.
    """
    app, win, area, panel = fresh
    inner = area.widget()
    bar = area.verticalScrollBar()

    # THE STATE, NOT THE ARITHMETIC: the line has something to say, which in
    # the window happens because a file is open behind the run. Set directly,
    # so this costs no profile reading.
    win._who_owns.setText(
        "The big view is showing this run. printer-2019 is still open as "
        "well, and it comes back as soon as you remove these profiles.")
    panel._paths = ["printer-2019.icc", "printer-2024.icc"]
    _settle(app, 0.3)
    bar.setValue(0)
    panel._bring_the_answer_into_view()
    _settle(app, 0.5)

    line_top = win._who_owns.mapTo(inner, win._who_owns.rect().topLeft()).y()
    panel_top = panel.mapTo(inner, panel.rect().topLeft()).y()
    assert line_top < panel_top, "the fixture no longer matches the layout"
    assert abs(bar.value() - min(line_top, bar.maximum())) <= 2, (
        f"the view starts at {bar.value()}; the line explaining that the big "
        f"view changed hands is at {line_top} and the panel at {panel_top}, "
        f"so the explanation was scrolled past")

    # AND WITH NOTHING TO EXPLAIN it does not give the room away: an empty
    # line is hidden, and the run is the only thing the picture could be.
    win._who_owns.setText("")
    _settle(app, 0.3)
    bar.setValue(0)
    panel._bring_the_answer_into_view()
    _settle(app, 0.5)
    # MEASURED AGAIN, AFTER THE LINE WENT. It is hidden when empty, so the
    # whole column shrinks by its height and the panel moves up -- 474 to
    # 436. Held against the position from before, this failed by exactly
    # those 38 px and looked like a scrolling fault: a real measurement of
    # the wrong pair.
    panel_top_now = panel.mapTo(inner, panel.rect().topLeft()).y()
    assert panel_top_now < panel_top, (
        "the line is supposed to be hidden when it is empty")
    assert abs(bar.value() - min(panel_top_now, bar.maximum())) <= 4, (
        f"with nothing to explain the view should start at the panel, "
        f"{panel_top_now}, and it started at {bar.value()}")


def test_nothing_is_drawn_around_nothing_before_a_run_is_added(fresh):
    """An empty list is a frame around nothing, and so is an empty chooser.

    REPORTED FROM THE WINDOW: "one device over time shows an empty frame over
    the add button". The list holds a least height on purpose -- a list that
    grows and shrinks by a row as profiles arrive is worse than one that
    holds still -- and that reason stops applying when there is nothing in it
    at all, leaving 52 px of framed nothing sitting on the button that fills
    it.

    Driving the fix found the same fault twice more in the same section:
    "Show me" was an empty dropdown, and "coloured by" offered five ways to
    paint a picture that did not exist.

    All of them come back the moment a profile arrives, which is also the
    moment they have something in them.
    """
    app, win, area, panel = fresh
    inner = area.widget()
    panel._paths = []
    panel._refresh()
    panel._show_only_what_applies()
    _settle(app, 0.3)
    for name, widget in (("the list", panel._list),
                         ("Show me", panel._picture_label),
                         ("the picture chooser", panel._picture_of),
                         ("coloured by", panel._coloured_label),
                         ("the colour chooser", panel._coloured_by)):
        assert not widget.isVisibleTo(inner), (
            f"{name} is on screen with no run added, framing nothing")

    # AND THEY ARE BACK when there is something to show. Without this half
    # the test passes just as well with the whole section deleted.
    #
    # THROUGH _rebuild, NOT _refresh: the list is filled from the RUN, and
    # only _rebuild makes one. Setting the paths and refreshing left the run
    # at None, so the list stayed empty and stayed hidden -- and the test
    # blamed the window for it. Two profiles that cannot be read still make a
    # run, with both rows marked as unreadable, which is all this needs.
    import pathlib as _pl

    panel._paths = [_pl.Path("printer-2019.icc"), _pl.Path("printer-2024.icc")]
    panel._rebuild(sort=False)
    panel._show_only_what_applies()
    _settle(app, 0.3)
    assert panel._list.count() == 2, "the run did not take the two paths"
    assert panel._list.isVisibleTo(inner), "the list did not come back"
    assert panel._picture_of.isVisibleTo(inner), "the chooser did not come back"
