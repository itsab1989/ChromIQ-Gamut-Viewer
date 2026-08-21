"""Drive the main window's cloud chooser through all five colourings.

    python scripts/audit_cloud_colours.py

Exit code 1 if a colouring draws nothing, or gives the wrong KIND of answer:
a scale needs exactly one colour bar, and the destination families need a key
and no bar at all -- a colour bar over a picture of names reads as a scale
that does not exist.

Each answer is known in advance:
  * how far it moved      -- ONE trace, a colour bar beside it, no key
  * the three directions  -- ONE trace, a colour bar, two named ends
  * heading for           -- SEVERAL traces, one per destination family,
                             named in the key, and NO colour bar: it is a
                             name, not a measurement along a scale
and in every one of them the cloud must actually be drawn.
"""
import json
import pathlib
import sys
import tempfile
import time

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
FORK = HERE.parent
sys.path.insert(0, str(FORK / "python"))
sys.argv = ["audit_cloud_colours"]

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
  if (!d) return "{}";
  var data = d._fullData || d.data || [], out = {clouds: [], bar: 0};
  for (var i = 0; i < data.length; i++) {
    var t = data[i];
    if (t.type !== 'scatter3d') continue;
    var n = (t.x && t.x.length) || 0;
    // THE CLOUD, NOT EVERYTHING DRAWN AS POINTS. The two shells put a
    // wireframe and a one-point legend proxy in the picture as well, and
    // counting those made every colouring look like four clouds. Markers,
    // and more than a handful of them.
    if (n < 10 || String(t.mode || "").indexOf('markers') < 0) continue;
    out.clouds.push(String(t.name || "").slice(0, 28) + " ×" + n);
    if (t.marker && t.marker.showscale) out.bar++;
  }
  return JSON.stringify(out);
})()
"""


def picture():
    got = []
    page = win._view.page()
    if page is None:
        return {}
    page.runJavaScript(ASK, got.append)
    end = time.time() + 8
    while not got and time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    try:
        return json.loads(got[0]) if got else {}
    except (TypeError, ValueError):
        return {}


pump(3)
import demo_profiles
profiles = demo_profiles.the_run_of_profiles()
win._load(profiles[0])
pump(7)
win._load(profiles[-1])
pump(8)

box = win._drift_by
print(f"  the pair the window sees: {win._profile_pair() is not None}")
enabled_before = (box.isEnabled(), win._drift_split.isEnabled(),
                  win._drift_cut.isEnabled())
print(f"  before the tick: {enabled_before}")
win._drift_draw.setChecked(True)
pump(9)
enabled_after = (box.isEnabled(), win._drift_split.isEnabled(),
                 win._drift_cut.isEnabled())
print(f"  after the tick:  {enabled_after}")

problems = []
for i in range(box.count()):
    box.setCurrentIndex(i)
    box.activated.emit(i)
    pump(9)
    label, key = box.itemText(i), box.itemData(i)
    drawn = picture()
    clouds, bar = drawn.get("clouds", []), drawn.get("bar", 0)
    print(f"\n  {label:34s} traces {len(clouds):2d}  colour bar {bar}")
    for c in clouds[:8]:
        print(f"        {c}")
    if not clouds:
        problems.append(f"[{label}] nothing was drawn")
    if key == "toward":
        if len(clouds) < 2:
            problems.append(
                f"[{label}] one trace only — the destinations are not split "
                f"into a key")
        if bar:
            problems.append(
                f"[{label}] a colour bar over a picture of NAMES, which reads "
                f"as a scale that does not exist")
    else:
        if len(clouds) != 1:
            problems.append(f"[{label}] {len(clouds)} traces, expected one")
        if bar != 1:
            problems.append(
                f"[{label}] {bar} colour bars — a measurement along a scale "
                f"needs exactly one")

print()
for p in problems:
    print("  " + p)
print(f"\n  {len(problems)} problem(s)." if problems
      else "  Clean: every colouring draws, and says what kind of answer it "
           "is.")
# AND THE THREE CONTROLS FOLLOW THE TICK THEY DEPEND ON.
if enabled_before != (False, False, False):
    problems.append(
        f"with the cloud off, the controls that only act on it are still "
        f"lit: {enabled_before}")
if enabled_after != (True, True, True):
    problems.append(
        f"with the cloud on, its own controls are greyed out: "
        f"{enabled_after}")
win.close()
pump(0.5)
sys.stdout.flush()
os._exit(1 if problems else 0)
