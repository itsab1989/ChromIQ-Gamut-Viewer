"""A run of profiles of one device, and what moved between the times.

Every profile here is written by hand, so a machine with a full colour
toolchain and a bare build runner give identical answers and nothing needs
installing.
"""
import struct

import pytest

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
    assert list(fig.data[0].x) == ["2020-06-01", "2021-06-01", "2024-06-01"]


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
    assert list(fig.data[0].x) == ["n1", "n2"]


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
    rows = [dialog._list.item(i).text() for i in range(5)]
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
    assert all(five_years[2].stem not in dialog._list.item(i).text()
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
    rows = [dialog._list.item(i).text() for i in range(dialog._list.count())]
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
