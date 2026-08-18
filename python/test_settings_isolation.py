"""Nothing but prefs.py may decide where the settings live.

THE FAULT THIS GUARDS AGAINST HAS ALREADY HAPPENED, and it did not look like a
settings fault when it arrived. Eleven drivers began by clearing

    QSettings("MeasuredGamutViewer", "MeasuredGamutViewer")

which is the real store — the one the person using this application keeps
their choices in. Running a check wiped it; worse, the window writes its state
back as it closes, so the last state a driver had set became their new
default. An audit that switched the box off to see whether the control said so
switched the box off for good, and it came back the next morning as a bug
report about the application: "the room / the walls / the grid or whatever it
is called behind the shape is missing".

So the rule is one line long: the store is constructed in prefs.store() and
nowhere else. A grep is the right shape of test for it — the next driver
somebody writes is exactly where this comes back, and it will be written by
copying an existing one.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
#: `QSettings(` with the application's own names in it, anywhere but prefs.py.
BUILDS_ONE = re.compile(r'QSettings\(\s*\n?\s*"MeasuredGamutViewer"')


def _sources():
    for folder in ("python", "scripts", "utils"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            if path.name in ("prefs.py", "test_settings_isolation.py"):
                continue
            yield path


def test_only_prefs_decides_where_the_settings_live():
    guilty = [str(p.relative_to(ROOT)) for p in _sources()
              if BUILDS_ONE.search(p.read_text(encoding="utf-8"))]
    assert not guilty, (
        "these build the application's settings store themselves, which means "
        "they write to the real one whatever prefs.py has been asked to do: "
        + ", ".join(guilty) + ". Use prefs.store().")


def test_every_driver_sends_its_settings_somewhere_throwaway():
    """A script that builds the window must isolate before it does.

    Not "should": a driver reaches the end and the window's own closing
    handler writes everything it touched. Whatever the last state was is what
    the person finds when they next open the application.
    """
    missing = []
    for path in sorted((ROOT / "scripts").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "gamut_app" not in text:
            continue
        if "use_a_scratch_store" not in text:
            missing.append(path.name)
    assert not missing, (
        "these drive the real window without sending its settings somewhere "
        "throwaway first: " + ", ".join(missing)
        + ". Add `import prefs` and `prefs.use_a_scratch_store()` above it.")


def test_the_scratch_store_really_is_somewhere_else():
    """Proving the isolation, rather than trusting the call that asks for it.

    Two ways of doing this were tried first and BOTH looked right and wrote to
    the real store anyway -- setPath on NativeFormat, which macOS ignores, and
    setDefaultFormat, which the two-name constructor does not consult. So this
    asks the store where it actually is.
    """
    import prefs

    where = prefs.use_a_scratch_store()
    landed = pathlib.Path(prefs.store().fileName()).resolve()
    # AS PATHS, NOT AS TEXT -- see the test below, and the Windows build that
    # taught us the difference.
    assert where.resolve() in landed.parents, landed
    assert "Library/Preferences" not in str(landed), landed
    # AND IT IS A REAL, WRITABLE STORE -- an isolation that silently swallowed
    # every write would hide state faults instead of causing them.
    prefs.store().setValue("a_probe", 41)
    prefs.store().sync()
    assert int(prefs.store().value("a_probe")) == 41
    prefs.store().remove("a_probe")


def test_the_isolation_check_compares_paths_and_not_text():
    """One folder named two ways is still one folder.

    THIS BROKE A WINDOWS BUILD AND NOTHING ELSE. The check asked whether the
    scratch folder's name appeared anywhere in the store's file name — true on
    macOS and Linux by luck, false on Windows, where tempfile hands out the
    short form of a path and Qt hands back the long one:

        asked for  C:\\Users\\RUNNER~1\\AppData\\Local\\Temp\\gv-settings-…
        landed in  C:\\Users\\runneradmin\\AppData\\Local\\Temp\\gv-settings-…

    Same folder; the check called it a failure and refused to run, taking
    thirteen tests with it. macOS has the same trap in /var against
    /private/var, which is what this uses to reproduce it anywhere.
    """
    import os
    import tempfile

    import prefs

    real = pathlib.Path(tempfile.mkdtemp(prefix="gv-alias-real-"))
    link = pathlib.Path(tempfile.mkdtemp(prefix="gv-alias-")) / "by-another-name"
    try:
        os.symlink(real, link, target_is_directory=True)
    except (OSError, NotImplementedError):                     # pragma: no cover
        import pytest

        pytest.skip("this platform will not make a symlink")
    # Asked for by one name, stored under the other: the check must accept it.
    prefs.use_a_scratch_store(link)
    landed = pathlib.Path(prefs.store().fileName()).resolve()
    assert str(real.resolve()) in str(landed)


def test_the_suite_never_draws_on_somebody_s_screen():
    """A gate run must not put windows on top of what a person is doing.

    It builds windows and shows them — test_folding calls show() three times,
    test_drift_series builds a standalone "Follow one device over time" dialog
    with no parent, which takes the SYSTEM palette rather than this
    application's. Reported with a photograph of a light dialog sitting over
    the dark window: "how do you reach this window at this point? i thought
    it was fully integrated in the main windows left panel?" — it is not
    reachable at all; it was a test's.
    """
    import os

    assert os.environ.get("QT_QPA_PLATFORM") == "offscreen", (
        "the suite is drawing on the real platform, which puts its windows on "
        "whatever the person using this machine is looking at")
