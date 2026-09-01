"""What every test in this suite is given before it starts.

THE SUITE MUST NOT WRITE INTO SOMEBODY'S PREFERENCES. It builds windows, and a
window writes its state back; test_folding remembers and forgets fold keys by
name. Every one of those went into the real store until now, so running the
tests changed how the application would open afterwards.

Set before anything imports the application, because the store is chosen the
first time it is asked for.
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
os.environ.setdefault("GAMUTVIEW_SCRATCH_SETTINGS", "1")

# AND THE SUITE DRAWS NOWHERE NEAR THE PERSON USING THE MACHINE.
#
# It builds windows and shows them -- test_folding calls show() three times,
# test_drift_series builds a standalone "Follow one device over time" dialog
# with no parent, which takes the SYSTEM palette rather than this
# application's -- so a gate run threw a light-coloured window on top of
# whatever was on screen. Reported exactly that way, with a photograph:
# "how do you reach this window at this point? i thought it was fully
# integrated in the main windows left panel?"
#
# It is not reachable from the application at all. It was a test's window,
# on his screen, because the suite ran on the real platform.
#
# QT_QPA_PLATFORM= (empty) in the environment still wins, for anybody who
# wants to watch a test run.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def pytest_configure(config):
    """Name the marks this suite uses, so pytest stops calling them typos.

    ⚠ AND SO THAT SKIPPING THEM IS A DECISION SOMEBODY MAKES. `slow` was
    never registered, which meant two things at once: every run printed
    `PytestUnknownMarkWarning: Unknown pytest.mark.slow - is this a typo?`,
    and `-m "not slow"` was a filter nobody had thought about. It is
    registered here and the tests wearing it are the ones that BUILD real
    shapes off ArgyllCMS — the dependency table proved by building, which is
    minutes rather than seconds.

    The test of the one door is deliberately NOT among them. It is the only
    test `shape_for` has, and a marker that can hide the only test of a
    thing is a marker that will eventually hide it.
    """
    config.addinivalue_line(
        "markers",
        "slow: builds real gamuts through ArgyllCMS; minutes, not seconds")
