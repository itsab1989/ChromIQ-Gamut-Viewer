"""Does #123's chooser reach everything the window writes down?

    python scripts/audit_one_thing_or_two.py

The answer is known in advance and it is the whole reason the chooser exists:
told that two files are TWO DIFFERENT PAPERS, nothing this window claims may
say they "moved" or "drifted". A paper does not drift.

KEYWORD MATCHING CANNOT ANSWER THIS and the first version of this check
proved it: with "two different things" chosen, the footnote reads *nothing
here has "drifted"* -- a denial, containing the word -- and the check
reported it as a fault twice over. So each place is held against the exact
sentence it is supposed to be showing.

Four places, crossed against both settings of the chooser:
  * the family heading
  * the footnote under it
  * the worst-patches readout above it
  * the rows of the exported table
"""
import pathlib
import sys
import time

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
FORK = HERE.parent
sys.path.insert(0, str(FORK / "python"))
sys.argv = ["audit_one_thing_or_two"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

from PyQt6.QtWidgets import QApplication                        # noqa: E402

import gamut_app                                                # noqa: E402

app = QApplication(sys.argv)
gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
win = gamut_app.GamutApp([])
win.resize(1400, 900)
win.show()


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


#: What each place must say, for each setting. Written out rather than
#: derived, so this cannot agree with the code by sharing its mistake.
WANT = {
    True: {"heading": "which colour families moved",
           "worst": "The ones that moved most:",
           "table": "moved most: "},
    False: {"heading": "how the two compare, family by family",
            "worst": "The ones that differ most:",
            "table": "differs most: "},
}
#: And the footnote must SAY SO when they are not one thing over time.
DENIAL = 'nothing here has "drifted"'

pump(3)
problems = []

#: BOTH KINDS OF PAIR. The window has two drift paths with their own copies of
#: these sentences -- two MEASUREMENTS of a chart, and two PROFILES -- and the
#: chooser sits above both. Only the measurement one was ever read.
import tempfile
import demo_profiles
profiles = demo_profiles.the_run_of_profiles()
PAIRS = [("two measurements", FORK / "demo" / "Glossy-paper.ti3",
          FORK / "demo" / "Matte-paper.ti3")]
if len(profiles) >= 2:
    PAIRS.append(("two profiles", profiles[0], profiles[-1]))

for kind, first, second in PAIRS:
  print(f"\n  === {kind} ===")
  # CLOSE WHAT IS OPEN BEFORE OPENING THE NEXT PAIR, or the second pair is
  # measured with FOUR shapes on screen.
  #
  # This read `win._close_them_all() if hasattr(win, "_close_them_all")` —
  # and the window has no such method, so the guard swallowed it and the line
  # did nothing, every run. A guarded call to a name that does not exist is
  # worse than a crash: it never fails, it simply is not there. The window's
  # own "close everything on screen" is `_on_clear`.
  win._on_clear()
  pump(2)
  win._load(first)
  pump(7)
  win._load(second)
  pump(9)
  for label, over_time in (("one thing at two times", True),
                           ("two different things", False)):
      box = win._same_thing
      box.setCurrentIndex(box.findText(label))
      box.activated.emit(box.currentIndex())
      pump(5)
      want = WANT[over_time]

      heading = win._drift_families.text().splitlines()[0] if win._drift_families.text() else ""
      worst = win._drift_worst.text().splitlines()[0] if win._drift_worst.text() else ""
      note = win._drift_families_note.text()
      rows = win._profile_drift_rows() if win._profile_pair() is not None else []
      if not rows:
          rows = [r for r in win._readout_text().splitlines()
                  if "most: " in r]
      table = " | ".join(str(r) for r in rows)

      ok_head = want["heading"] in heading
      ok_worst = worst.endswith(want["worst"])
      ok_note = (DENIAL in note) if not over_time else (DENIAL not in note)
      print(f"\n  chooser: {label}")
      print(f"      heading  {'ok ' if ok_head else 'NO '} {heading[:72]}")
      print(f"      worst    {'ok ' if ok_worst else 'NO '} {worst[:72]}")
      print(f"      footnote {'ok ' if ok_note else 'NO '} "
            f"{'says nothing drifted' if DENIAL in note else 'no denial in it'}")
      if not ok_head:
            problems.append(f"[{kind}: {label}] the heading reads {heading[:60]!r}")
      if not ok_worst:
            problems.append(f"[{kind}: {label}] the worst-patches line reads {worst[:60]!r}")
      if not ok_note:
            problems.append(f"[{kind}: {label}] the footnote is wrong about drift")

print()
for p in problems:
    print("  " + p)
print(f"\n  {len(problems)} problem(s)." if problems
      else "  Clean: every place the window writes down agrees with the "
           "chooser.")
win.close()
pump(0.4)
sys.stdout.flush()
os._exit(1 if problems else 0)
