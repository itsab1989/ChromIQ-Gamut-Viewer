"""The window's temporary scenes, which once cost 27 GB of somebody's disk.

Every redraw writes a self-contained page with plotly.js inlined -- about 6 MB
-- and for a long time nothing ever deleted one. Found on the development
machine as **644 leftover folders holding 27 GB** after two days of work.

These are cheap, do not open a window, and would each have caught it.
"""
import os
import pathlib
import shutil
import tempfile
import time

import pytest

import gamut_app


def test_a_run_clears_up_after_one_that_was_killed(tmp_path, monkeypatch):
    """Closing the window takes its own folder with it. That does not cover a
    run that crashed or was killed -- which is exactly what a test suite, an
    audit and a screenshot driver do, hundreds of times."""
    dead = tmp_path / "gamutview-dead"
    dead.mkdir()
    (dead / "scene-1.html").write_text("x" * 1000)
    # A process id that cannot be alive: PID 0 is never a user process, and
    # os.kill(0, 0) would signal our own process group rather than ask about
    # one, so a number well past the maximum is used instead.
    (dead / "owner.pid").write_text("4294967290")
    old = time.time() - gamut_app.FORGOTTEN_AFTER_SECONDS - 60
    os.utime(dead, (old, old))

    mine = tmp_path / "gamutview-mine"
    mine.mkdir()
    gamut_app._sweep_up_after_runs_that_never_finished(mine)

    assert not dead.exists(), "a folder whose window is gone must be cleared"
    assert mine.exists(), "and the sweep must never take its own"


def test_a_second_window_open_right_now_is_left_alone(tmp_path):
    """Two windows at once must not delete each other's scenes -- which is
    the one way a tidy-up like this could lose somebody their picture."""
    live = tmp_path / "gamutview-live"
    live.mkdir()
    (live / "owner.pid").write_text(str(os.getpid()))    # alive: us
    old = time.time() - gamut_app.FORGOTTEN_AFTER_SECONDS - 60
    os.utime(live, (old, old))

    mine = tmp_path / "gamutview-mine"
    mine.mkdir()
    gamut_app._sweep_up_after_runs_that_never_finished(mine)
    assert live.exists(), "a folder whose process is still running must stay"


def test_a_folder_touched_a_moment_ago_is_left_alone(tmp_path):
    """Age is the fallback for a folder carrying no id -- one written before
    this existed, or by a process id that has since been recycled. A recent
    one is a window that is very probably still starting up."""
    fresh = tmp_path / "gamutview-fresh"
    fresh.mkdir()
    mine = tmp_path / "gamutview-mine"
    mine.mkdir()
    gamut_app._sweep_up_after_runs_that_never_finished(mine)
    assert fresh.exists()


def test_the_sweep_says_who_owns_the_folder_it_keeps(tmp_path):
    """Without the id written down, the next run has only age to go on."""
    mine = tmp_path / "gamutview-mine"
    mine.mkdir()
    gamut_app._sweep_up_after_runs_that_never_finished(mine)
    assert (mine / "owner.pid").read_text().strip() == str(os.getpid())


def test_a_session_that_redraws_for_ever_keeps_two_scenes(tmp_path):
    """THE LEAK ITSELF, and the number that was unbounded.

    The name counts up on purpose -- reloading one URL let the web view serve
    its cached copy, so switching to light left the scene dark. That is kept.
    What is added is deleting the one from two redraws ago: not the newest,
    which the view may still be reading, and not the one before it, which is
    what it was showing a moment ago.

    Sixty redraws used to leave sixty files of about 6 MB. It is now two,
    however long somebody works.
    """
    class Fake:
        _tmp = tmp_path
        _render_count = 0
        _drop_the_scene_before_last = \
            gamut_app.GamutApp._drop_the_scene_before_last

    window = Fake()
    for _ in range(60):
        window._render_count += 1
        (tmp_path / f"scene-{window._render_count}.html").write_text("page")
        window._drop_the_scene_before_last()

    left = sorted(p.name for p in tmp_path.glob("scene-*.html"))
    assert len(left) == 2, f"{len(left)} scenes left behind: {left}"
    assert left == ["scene-59.html", "scene-60.html"]


def test_dropping_a_scene_that_was_never_written_is_not_an_error():
    """The first two redraws have nothing two back to delete."""
    with tempfile.TemporaryDirectory() as folder:
        class Fake:
            _tmp = pathlib.Path(folder)
            _render_count = 1
            _drop_the_scene_before_last = \
                gamut_app.GamutApp._drop_the_scene_before_last
        Fake()._drop_the_scene_before_last()      # must not raise


def test_closing_the_window_takes_its_folder_with_it():
    """Which the comment beside the folder always claimed happened."""
    import inspect
    src = inspect.getsource(gamut_app.GamutApp.closeEvent)
    assert "rmtree" in src and "_tmp" in src
