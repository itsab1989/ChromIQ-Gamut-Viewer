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
