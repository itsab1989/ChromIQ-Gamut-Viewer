"""Where the window's remembered settings live — and how a driver borrows them.

THIS FILE EXISTS BECAUSE THE AUDITS WERE WRITING INTO THE USER'S OWN
PREFERENCES. Every driver in scripts/ began with

    QSettings("MeasuredGamutViewer", "MeasuredGamutViewer").clear()

so that it started from the defaults — and that is the real store, the one the
person using this application keeps their choices in. Two things followed, and
both of them are worse than they sound:

  * the clear THREW AWAY what they had chosen, silently, every time a check
    was run;
  * the window writes its state back as it closes, so whatever the driver had
    last set was left behind as their new preference. An audit that switched
    the box off to see whether the control told the truth about it left the
    box switched off. It was reported the next morning exactly as a bug in the
    application: "the room / the walls / the grid or whatever it is called
    behind the shape is missing" — over a picture that was drawing precisely
    what the settings said.

A check must not be able to change the thing it is checking. So a driver calls
`use_a_scratch_store()` before it builds the window, and from that moment
`QSettings(ORG, APP)` — every one of them, including the ones inside the
application — resolves to a throwaway file under the system's temporary folder.

HOW IT WORKS, because the two obvious ways do not, and both were tried and
measured before this one was written:

  * `QSettings.setPath` HAS NO EFFECT ON NativeFormat ON macOS. Native means
    CFPreferences there, which ignores paths.
  * `QSettings.setDefaultFormat(IniFormat)` DOES NOT REACH `QSettings(org,
    app)` EITHER. Measured, on this machine, with the format asked of the
    object afterwards:

        default after  Format.IniFormat
        file  ~/Library/Preferences/com.measuredgamutviewer...plist
              Format.NativeFormat

    Only the argument-free `QSettings()` takes the default format; the
    two-name constructor is native whatever the default says. An isolation
    built on it would have LOOKED right and written to the real store anyway,
    which is the same fault one layer up.

So the store is constructed in ONE place — `store()`, here — and that is what
switches. When a scratch folder is in force it hands back an ini-format store
under that folder, and the rest of the application neither knows nor cares.
`test_settings_isolation.py` fails if anything else constructs its own.
"""
from __future__ import annotations

import os
import pathlib
import tempfile

#: The two names the application's store is registered under. In one place so
#: that a driver, a test and the window itself cannot drift apart on them.
ORG = "MeasuredGamutViewer"
APP = "MeasuredGamutViewer"

#: Set once `use_a_scratch_store` has been called, so that a second call — two
#: drivers imported into one process — does not move the store out from under
#: settings that have already been written to it.
_scratch: pathlib.Path | None = None


def store():
    """The application's settings, wherever they currently live."""
    from PyQt6.QtCore import QSettings

    if _scratch is None and isolated_by_default():
        # ASKED FOR BY THE ENVIRONMENT, so that the test suite -- which builds
        # dozens of windows and closes them, each one writing its state back --
        # cannot leave its last state behind as somebody's preference.
        use_a_scratch_store()
    if _scratch is None:
        return QSettings(ORG, APP)
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                     ORG, APP)


def scratch_folder() -> pathlib.Path | None:
    """The throwaway store's folder, or None if the real one is in use."""
    return _scratch


def use_a_scratch_store(folder=None) -> pathlib.Path:
    """Send every setting to a throwaway file for the rest of this process.

    Call it BEFORE the window is built. Returns the folder it chose, so a
    driver that wants to look at what was written can.
    """
    global _scratch
    from PyQt6.QtCore import QSettings

    if _scratch is not None and folder is None:
        return _scratch
    where = pathlib.Path(folder) if folder is not None else pathlib.Path(
        tempfile.mkdtemp(prefix="gv-settings-"))
    where.mkdir(parents=True, exist_ok=True)
    QSettings.setPath(QSettings.Format.IniFormat,
                      QSettings.Scope.UserScope, str(where))
    QSettings.setPath(QSettings.Format.IniFormat,
                      QSettings.Scope.SystemScope, str(where))
    _scratch = where
    # A SANITY CHECK THAT COSTS NOTHING AND HAS ALREADY EARNED ITS KEEP: if
    # the store still resolves to somewhere under the user's own preferences,
    # the isolation did not take and the driver would quietly go on writing
    # there. Better to say so than to find out from a bug report.
    #
    # COMPARED AS PATHS, NOT AS TEXT, and that distinction cost a Windows
    # build. The first version asked whether the folder's name appeared
    # ANYWHERE in the store's file name -- true on macOS and Linux by luck,
    # and false on Windows, where the same folder is handed back in its long
    # form while tempfile gave out the short one:
    #
    #     asked for  C:\Users\RUNNER~1\AppData\Local\Temp\gv-settings-…
    #     landed in  C:\Users\runneradmin\AppData\Local\Temp\gv-settings-…
    #
    # Those are one folder. The check called it a failure, refused to run,
    # and took thirteen tests down with it -- an isolation that was working
    # perfectly. macOS has the same trap waiting in /var against /private/var,
    # which is why both sides are resolved before they are compared.
    landed = pathlib.Path(store().fileName()).resolve()
    home = where.resolve()
    inside = landed == home or home in landed.parents
    if not inside:
        # Windows paths differ in case without differing at all.
        inside = str(landed).lower().startswith(str(home).lower())
    if not inside:
        raise RuntimeError(
            f"the settings were not isolated: they resolve to {landed}, "
            f"which is not inside {home}. Refusing to run, because this "
            f"could overwrite real preferences.")
    return where


def isolated_by_default() -> bool:
    """True when this process must never touch the real store.

    Set GAMUTVIEW_SCRATCH_SETTINGS=1 to make any entry point isolate itself —
    used by the test suite, and available to anything else that would rather
    not be trusted with somebody's preferences.
    """
    return os.environ.get("GAMUTVIEW_SCRATCH_SETTINGS", "") not in ("", "0")
