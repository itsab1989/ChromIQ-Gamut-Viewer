"""The log must be useful, must be capped, and must never write outside a
test's own temporary folder.

Every test here redirects the log directory with GAMUTVIEW_LOG_DIR into
pytest's tmp_path, which pytest removes afterwards. Nothing is left on the
machine running the suite -- a test that drops files in somebody's real log
folder is a bug in the test.
"""
import importlib
import logging

import pytest


@pytest.fixture
def log_module(tmp_path, monkeypatch):
    """A freshly configured logger writing into tmp_path and nowhere else."""
    monkeypatch.setenv("GAMUTVIEW_LOG_DIR", str(tmp_path))
    import logger as module
    importlib.reload(module)
    module.configure(force=True)
    yield module
    # Close the file handlers, or Windows cannot delete the directory and the
    # next test inherits an open handle.
    root = logging.getLogger("gamutview")
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()


def test_the_log_lands_where_it_says_it_does(log_module, tmp_path):
    assert log_module.log_path().parent == tmp_path
    assert log_module.log_path().is_file()


def test_it_records_what_was_logged(log_module):
    log_module.get_logger("test").info("a distinctive line")
    for handler in logging.getLogger("gamutview").handlers:
        handler.flush()
    assert "a distinctive line" in log_module.log_path().read_text(encoding="utf-8")


def test_it_cannot_grow_without_limit(log_module):
    """The cap is the point: a log that quietly eats a disk is its own bug."""
    assert log_module.MAX_BYTES <= 5_000_000
    total = log_module.MAX_BYTES * (log_module.BACKUP_COUNT + 1)
    assert total <= 20_000_000, f"{total} bytes is too much to promise"


def test_it_actually_rotates_rather_than_growing(log_module, tmp_path):
    """Not just configured to rotate -- observed rotating."""
    log = log_module.get_logger("rotate")
    handler = logging.getLogger("gamutview").handlers[0]
    handler.maxBytes = 2_000                 # keep the test quick
    for i in range(400):
        log.info("filler line %d %s", i, "x" * 80)
    handler.flush()
    written = sorted(p.name for p in tmp_path.iterdir())
    assert len(written) > 1, written
    assert all(p.stat().st_size <= 40_000 for p in tmp_path.iterdir())


def test_a_read_only_location_does_not_stop_the_app(tmp_path, monkeypatch):
    """A full or read-only disk must not prevent the window from opening."""
    import logger as module
    importlib.reload(module)
    monkeypatch.setattr(module, "log_dir",
                        lambda: tmp_path / "nope" / "\0bad")
    assert module.configure(force=True) is None      # returns None, no raise


def test_nothing_is_written_outside_the_test_folder(log_module, tmp_path):
    """The guard that keeps a suite from littering somebody's machine."""
    log_module.get_logger("test").warning("something")
    for handler in logging.getLogger("gamutview").handlers:
        handler.flush()
    produced = list(tmp_path.iterdir())
    assert produced, "expected the log inside tmp_path"
    assert all(p.parent == tmp_path for p in produced)
