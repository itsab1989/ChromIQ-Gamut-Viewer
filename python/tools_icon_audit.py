"""Check that every ⓘ sits beside the control it explains.

Run with the app importable:  python tools_icon_audit.py

Written because this was got wrong repeatedly by looking at screenshots. An
icon on a row of its own reads as explaining nothing, and the only reliable
way to know is to ask, for each one, whether any control shares its row.
"""

import os, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# THE SETTINGS GO SOMEWHERE THROWAWAY, and this must happen before the
# window is built. A driver that uses the real store both destroys what
# the person using this application has chosen and leaves its own last
# state behind as their new preference -- which is how "the walls behind
# the shape are missing" was reported as a bug in the viewer. See
# python/prefs.py.
import prefs  # noqa: E402

prefs.use_a_scratch_store()
sys.argv=["x"]
from pathlib import Path
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (QApplication, QComboBox, QCheckBox, QSlider,
                             QPushButton, QLabel, QScrollArea, QGroupBox,
                             QRadioButton)
import gamut_app
DEMO = Path(os.environ.get("GAMUTVIEW_DEMO_TI3", ""))
app=QApplication(sys.argv); w=gamut_app.GamutApp([]); w.resize(1500,950); w.show()
def pump(s):
    e=time.time()+s
    while time.time()<e: app.processEvents(); time.sleep(0.01)
pump(4); # A chart is optional: without one the audit still checks every icon
# that is on screen. Point GAMUTVIEW_DEMO_TI3 at a .ti3 to check the
# rows that only appear once something is open.
if DEMO.name and DEMO.is_file():
    w._load(DEMO); pump(7)
inner = w.findChild(QScrollArea).widget()
# Radios and the big volume readout are controls the eye reads too;
# leaving them out made two correctly-placed icons look like orphans.
CTRL = (QComboBox, QCheckBox, QSlider, QPushButton, QRadioButton)

# Headings count too. An explanation that covers a whole set belongs beside
# the heading that names the set, and a checker that does not know that
# reports three correctly placed icons as orphans -- which it did, twice.
controls = [c for c in inner.findChildren(CTRL)
            if c.isVisible() and not isinstance(c, gamut_app.Hint)]
controls += [l for l in inner.findChildren(QLabel)
             if l.isVisible() and l.text() and l.objectName() not in ('hint',)]
orphans = []
for h in inner.findChildren(gamut_app.Hint):
    if not h.isVisible(): continue
    hy = h.mapTo(inner, h.rect().center()).y()
    group = h
    while group is not None and not isinstance(group, QGroupBox):
        group = group.parent()
    gname = group.title() if isinstance(group, QGroupBox) else "?"
    same_row = [c for c in controls
                if abs(c.mapTo(inner, c.rect().center()).y() - hy) <= 12]
    if same_row:
        c = same_row[0]
        txt = c.currentText() if isinstance(c, QComboBox) else (
              c.text() if hasattr(c, "text") else type(c).__name__)
        print(f"  ok      [{gname[:22]:22s}] beside {txt[:38]!r}")
    else:
        near = sorted(controls, key=lambda c: abs(c.mapTo(inner, c.rect().center()).y()-hy))
        n = near[0] if near else None
        ntxt = (n.currentText() if isinstance(n, QComboBox) else
                (n.text() if n is not None and hasattr(n,"text") else "?")) if n else "?"
        dy = (n.mapTo(inner, n.rect().center()).y()-hy) if n else 0
        orphans.append((gname, h.objectName(), ntxt, dy))
        print(f"  ORPHAN  [{gname[:22]:22s}] {h.objectName():22s} nearest {ntxt[:30]!r} ({dy:+d}px)")
print(f"\n  {len(orphans)} of {len(inner.findChildren(gamut_app.Hint))} icons have no control on their row")
import os; sys.stdout.flush(); os._exit(0)
