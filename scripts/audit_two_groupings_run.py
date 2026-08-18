"""The same crossing, on the OTHER path: a run, not two opened files.

"in case it makes a difference whether a profile / chart is loaded or the
viewer is populated from the files loaded from a run make sure to apply fixes
for both ways."

The two controls are the same pair in both places, so the rule must be too:
while the cloud is grouped by the family each colour is heading FOR, the tick
that groups by the family each colour is IN cannot act and must not pretend
to.
"""
import pathlib
import sys
import tempfile
import time

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_two_groupings_run"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

from PyQt6.QtWidgets import QApplication                        # noqa: E402

import gamut_app                                                # noqa: E402

app = QApplication(sys.argv)
gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
win = gamut_app.GamutApp([])
win.resize(1500, 950)
win.show()


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


pump(3)
profiles = sorted(pathlib.Path(tempfile.gettempdir())
                  .glob("showme-*/printer-*.icc"))
panel = win._timeline
panel.add(list(profiles))
pump(14)
# A PAIR HAS TO BE CHOSEN, or the split is not even on screen and the check
# reports "clean" about a control it never looked at -- coverage of nothing.
show = panel._picture_of
print("  Show me offers: "
      + " | ".join(f"{show.itemText(i)[:34]}" for i in range(show.count())))
for i in range(show.count()):
    if show.itemText(i).startswith("Where it moved"):
        show.setCurrentIndex(i)
        show.activated.emit(i)
        break
pump(10)
print(f"  a pair is chosen: {panel._chosen_pair() is not None}")

box = panel._coloured_by
problems = []
print(f"  {'coloured by':34s} split shown  clickable")
for i in range(box.count()):
    box.setCurrentIndex(i)
    box.activated.emit(i)
    pump(7)
    label, key = box.itemText(i), box.itemData(i)
    shown = panel._by_family.isVisible()
    can = panel._by_family.isEnabled()
    print(f"  {label:34s} {str(shown):5s} {str(can):9s}")
    if key == "toward" and can:
        problems.append(
            f"[run: {label}] the split is still clickable while the cloud is "
            f"grouped by destination")
    if key != "toward" and shown and not can:
        problems.append(f"[run: {label}] the split is greyed out when it can act")

# AND IT MUST NOT CRASH, which is what the same pair did before today.
box.setCurrentIndex(box.findData("toward"))
box.activated.emit(box.currentIndex())
panel._by_family.setChecked(True)
pump(8)
print(f"\n  with both set: the window is still up = {win.isVisible()}")

print()
for p in problems:
    print("  " + p)
print(f"\n  {len(problems)} problem(s)." if problems else "  Clean.")
win.close(); pump(0.4)
sys.stdout.flush()
os._exit(1 if problems else 0)
