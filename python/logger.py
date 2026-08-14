"""A log file, so a fault that happened once can still be looked at.

WHY THERE IS ONE
----------------
A bug reported as "it did something odd and then I closed it" is very hard to
act on. A log turns that into a timestamped line somebody can read. This
follows ChromIQ's arrangement (``core/logger.py``) so a person who has seen
one has seen the other.

WHAT IT DOES NOT DO
-------------------
It never leaves the machine. Nothing is uploaded, and the file is plain text
you can open, read and delete yourself.

**It cannot grow without limit.** Five files of 2 MB each, rotated, so the
most it can ever occupy is 10 MB — a log that quietly eats a disk is a bug of
its own. ChromIQ uses the same shape with a larger cap; this application is
much smaller and writes far less.

WHERE IT IS
-----------
``log_path()`` says exactly, and the About text shows it, because "there is a
log somewhere" is no use to anybody.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

#: 2 MB per file, five files kept: 10 MB at the very most, ever.
MAX_BYTES = 2_000_000
BACKUP_COUNT = 4

_configured = False


def log_dir() -> Path:
    """Where the log lives, following each platform's own convention.

    Overridable with ``GAMUTVIEW_LOG_DIR``, which is what the tests use so a
    test run never writes into the real one.
    """
    override = os.environ.get("GAMUTVIEW_LOG_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "ChromIQ Gamut Viewer"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "ChromIQ Gamut Viewer" / "logs"
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "chromiq-gamut-viewer"


def log_path() -> Path:
    return log_dir() / "gamut-viewer.log"


def configure(force: bool = False) -> Path | None:
    """Start logging to file. Safe to call more than once.

    Returns the path, or None when the file could not be opened. A read-only
    disk, a full one, or a path the platform will not accept must not stop the
    application from running: logging is a convenience, and refusing to open a
    window because a log file cannot be created would be absurd.
    """
    global _configured
    if _configured and not force:
        return log_path()
    root = logging.getLogger("gamutview")
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
            encoding="utf-8")
    except (OSError, ValueError):
        # OSError covers a full or read-only disk; ValueError covers a path
        # the platform rejects outright. Neither is worth refusing to start
        # over -- the application runs perfectly well without a log.
        _configured = True
        return None
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-14s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(handler)
    root.propagate = False
    _configured = True
    _banner(root)
    return path


def _banner(root: logging.Logger) -> None:
    """A line between one run and the next, so sessions can be told apart."""
    try:
        from version import APP_NAME, __version__
    except Exception:                       # noqa: BLE001 — never fatal
        APP_NAME, __version__ = "ChromIQ Gamut Viewer", "unknown"
    root.info("=" * 72)
    root.info("%s %s started — %s, python %s", APP_NAME, __version__,
              sys.platform, sys.version.split()[0])


def get_logger(name: str) -> logging.Logger:
    """A logger for one module. Configures the file on first use."""
    configure()
    return logging.getLogger(f"gamutview.{name}")


def install_exception_hook() -> None:
    """Write an unhandled crash to the log before the process dies.

    This is the case a log exists for: the user sees the application vanish,
    and afterwards there is still a full traceback to read.
    """
    previous = sys.excepthook

    def hook(kind, value, traceback):
        try:
            get_logger("crash").critical(
                "unhandled exception", exc_info=(kind, value, traceback))
        finally:
            previous(kind, value, traceback)

    sys.excepthook = hook
