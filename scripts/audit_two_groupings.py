"""Cross the cloud's colouring against the split, which both group it.

    python scripts/audit_two_groupings.py

Exit code 1 if the tick that cannot act is still clickable, or if the one
that can act is greyed out. It found a CRASH the first time it was run: the
two set together asked for a shared colour scale over a picture of names.

Two controls group the same cloud by different rules: "Split it into colour
families" by the family each colour IS IN, and "the colour it is heading for"
by the family it is going TO. They cannot both be in charge, and the answer
is known in advance -- one of them wins and the other must not go on claiming
to work.
"""
import json
import pathlib
import sys
import tempfile
import time

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_two_groupings"]

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


ASK = """
(function () {
  var d = document.getElementsByClassName('plotly-graph-div')[0];
  if (!d) return "[]";
  var data = d._fullData || [], out = [];
  for (var i = 0; i < data.length; i++) {
    var t = data[i];
    if (t.type !== 'scatter3d') continue;
    var n = (t.x && t.x.length) || 0;
    if (n < 10 || String(t.mode || "").indexOf('markers') < 0) continue;
    out.push(String(t.name || ""));
  }
  return JSON.stringify(out);
})()
"""


def clouds():
    got = []
    page = win._view.page()
    page.runJavaScript(ASK, got.append)
    end = time.time() + 8
    while not got and time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    try:
        return json.loads(got[0]) if got else []
    except (TypeError, ValueError):
        return []


pump(3)
profiles = sorted(pathlib.Path(tempfile.gettempdir())
                  .glob("showme-*/printer-*.icc"))
win._load(profiles[0]); pump(7)
win._load(profiles[-1]); pump(9)
win._drift_draw.setChecked(True); pump(9)

box = win._drift_by
problems = []
print(f"  {'coloured by':32s} {'split':6s} traces  the key says")
for i in range(box.count()):
    for split in (False, True):
        box.setCurrentIndex(i)
        box.activated.emit(i)
        win._drift_split.setChecked(split)
        pump(9)
        names = clouds()
        label, key = box.itemText(i), box.itemData(i)
        first = ", ".join(n[:22] for n in names[:3]) or "(nothing)"
        print(f"  {label:32s} {str(split):6s} {len(names):5d}  "
              f"split clickable {str(win._drift_split.isEnabled()):5s}  "
              f"{first[:46]}")
        # THE TICK CANNOT BE CLICKED WHEN IT CANNOT ACT. Asking whether
        # setChecked changed the picture is the wrong question: a disabled
        # widget takes a programmatic tick perfectly happily, so a check
        # phrased that way goes on failing after the fault is fixed.
        can_click = win._drift_split.isEnabled()
        if key == "toward" and can_click:
            problems.append(
                "[toward] \"Split it into colour families\" is still "
                "clickable while the cloud is grouped by destination, so it "
                "claims a grouping the picture does not use")
        if key != "toward" and not can_click:
            problems.append(
                f"[{label}] the split is greyed out when it can act")
        if key != "toward" and split and len(names) < 2:
            problems.append(f"[{label}] split is on and the cloud is one trace")

print()
for p in problems:
    print("  " + p)
print(f"\n  {len(problems)} problem(s)." if problems
      else "  Clean.")
win.close(); pump(0.4)
sys.stdout.flush()
os._exit(1 if problems else 0)
