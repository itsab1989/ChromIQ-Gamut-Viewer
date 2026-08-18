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
    landed = pathlib.Path(prefs.store().fileName())
    assert str(where) in str(landed), landed
    assert "Library/Preferences" not in str(landed), landed
    # AND IT IS A REAL, WRITABLE STORE -- an isolation that silently swallowed
    # every write would hide state faults instead of causing them.
    prefs.store().setValue("a_probe", 41)
    prefs.store().sync()
    assert int(prefs.store().value("a_probe")) == 41
    prefs.store().remove("a_probe")
