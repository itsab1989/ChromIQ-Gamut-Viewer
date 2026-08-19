"""Basti's two reported window scenes, reproduced in the REAL window.

Runs against whichever tree PYTHONPATH-equivalent argv[1] names, so the same
script photographs 2.39.6 and the pre-fix baseline:

  scene A -- the Measured comparison: printer-2019 solid (true colours,
             rings on) against printer-2021 as an outline;
  scene B -- the verification view: printer-2019 solid against sRGB outline,
             with verification-chart-480 opened and a solid skin over its
             patches.

Per scene it walks the fade states (agree,differ) in {(0,100),(100,0),
(100,100),(99,100)}, redraws, saves a screenshot per camera, dumps the drawn
standing mesh + GL camera matrices for the offline inside/outside
classifier, and in scene B times a relayout-driven turn (median ms per
frame). (99,100) exists to harvest the FULL recut mesh -- split on, nothing
removed -- which the parity classifier needs as its closed reference.

Usage: window_repro.py <tree> <outdir>
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "")
TREE = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(TREE / "python"))
ARGS = sys.argv[1:]
sys.argv = ["window_repro"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

import gamut_app                                               # noqa: E402
from PyQt6.QtWidgets import QApplication                      # noqa: E402
from PyQt6.QtGui import QPainter                               # noqa: E402

DEMO = TREE / "demo"
SHOWME = sorted(pathlib.Path("/var/folders/1b/yjhqw46j5y78ssphpcnfrs1r0000gp/T"
                             ).glob("showme-*"))[0]
P2019 = SHOWME / "printer-2019.icc"
P2021 = SHOWME / "printer-2021.icc"
CHART = DEMO / "verification-chart-480.ti1"

_app = None


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        _app.processEvents()
        time.sleep(0.005)


def ask(view, js, seconds=3.0):
    got = []
    view.page().runJavaScript(js, got.append)
    end = time.time() + seconds
    while not got and time.time() < end:
        _app.processEvents()
        time.sleep(0.005)
    return got[0] if got else None


def whole_window(window):
    shot = window.grab()
    view = getattr(window, "_view", None)
    if view is not None and view.width() > 1:
        picture = view.grab()
        where = view.mapTo(window, view.rect().topLeft())
        painter = QPainter(shot)
        painter.drawPixmap(where, picture)
        painter.end()
    return shot


class ChoosesForYou:
    def __init__(self, path):
        self._path = str(path)

    def exec(self):
        return 1

    def selectedFiles(self):
        return [self._path]


def compare_with(window, kind, name=None):
    for i in range(window._compare.count()):
        got = window._compare.itemData(i)
        if got and got[0] == kind and (name is None or got[1] == name):
            window._compare.setCurrentIndex(i)
            window._on_compare_changed()
            pump(3.0)
            return
    raise SystemExit(f"no Compare-with entry for {kind} {name!r}")


MESH_JS = """(function(){
  var d=document.getElementsByClassName('plotly-graph-div')[0];
  if(!d||!d._fullData) return 'nogd';
  var out=null, census=[];
  (d._fullData||[]).forEach(function(t,i){
    if (t.type!=='mesh3d') return;
    var n=(t.i&&t.i.length)||0;
    var rgba=0, vc=t.vertexcolor||[];
    for (var q=0;q<vc.length;q++) if ((vc[q]||'').indexOf('rgba')>=0) rgba++;
    census.push({at:i,name:t.name||'',faces:n,opacity:t.opacity,rgba:rgba});
    if ((t.name||'').indexOf('printer-2019')===0
        && (!out || n>out.i.length)) {
      var s=Array.prototype.slice;
      out={at:i, x:s.call(t.x), y:s.call(t.y), z:s.call(t.z),
           i:s.call(t.i), j:s.call(t.j), k:s.call(t.k),
           vertexcolor:s.call(t.vertexcolor||[]),
           opacity:t.opacity,
           lighting:t.lighting, lightposition:t.lightposition};
    }
  });
  return JSON.stringify({mesh:out||{}, census:census});
})()"""

CAM_JS = """(function(){
  var d=document.getElementsByClassName('plotly-graph-div')[0];
  var sc=d._fullLayout.scene._scene, gp=sc.glplot;
  var cp=gp.cameraParams, s=Array.prototype.slice;
  var cv=d.getElementsByTagName('canvas')[0];
  var r=cv.getBoundingClientRect();
  return JSON.stringify({
    model:s.call(cp.model), view:s.call(cp.view),
    projection:s.call(cp.projection), dataScale:s.call(sc.dataScale),
    rect:[r.left, r.top, r.width, r.height]});
})()"""

FRAME_JS = """(function(){
  var d=document.getElementsByClassName('plotly-graph-div')[0];
  window.__ft=[]; window.__ftdone=0;
  var stop=performance.now()+2600; var az=0.9;
  function tick(){
    var t=performance.now();
    if(t>stop){window.__ftdone=1;return;}
    az+=0.02;
    var r=1.8, e={x:r*Math.cos(az),y:r*Math.sin(az),z:0.7};
    Plotly.relayout(d, {'scene.camera.eye':e}).then(function(){
      window.__ft.push(performance.now()-t);
      requestAnimationFrame(tick);
    });
  }
  tick(); return 'started';
})()"""

CAMERAS = [
    ("default", None),
    ("tilt-a", (0.9 * -0.342, 0.9 * -0.94, -0.39)),      # az 250, el -12
    ("tilt-b", (1.27, 1.27, 0.35)),                       # az 45, el 11
]


def look_at(view, eye):
    if eye is None:
        return
    ask(view, "(function(){var d=document.getElementsByClassName("
              "'plotly-graph-div')[0];return Plotly.relayout(d,"
              "{'scene.camera.eye':{x:%f,y:%f,z:%f}})&&'ok';})()" % eye)
    pump(0.8)


def harvest_state(w, tag):
    view = w._view
    mesh = ask(view, MESH_JS, seconds=8.0)
    both = json.loads(mesh) if mesh and mesh not in ("nogd",) else {}
    got = both.get("mesh", {})
    faces = len(got.get("i", []))
    (OUT / f"{tag}-mesh.json").write_text(json.dumps(got))
    rgba = sum(1 for c in got.get("vertexcolor", []) if "rgba" in c)
    print(f"  [{tag}] printer-2019 skin: {faces} faces, {rgba} rgba "
          f"vertices, opacity {got.get('opacity')}")
    for t in both.get("census", []):
        print(f"      mesh3d[{t['at']}] {t['name'][:46]!r} faces {t['faces']}"
              f" opacity {t['opacity']} rgba {t['rgba']}")
    ratio = whole_window(w).width() / w.width()
    for name, eye in CAMERAS:
        look_at(view, eye)
        cam = ask(view, CAM_JS, seconds=4.0)
        if cam:
            info = json.loads(cam)
            info["ratio"] = whole_window(w).width() / w.width()
            # the screenshot below is of the whole window; the canvas rect is
            # relative to the VIEW, so shift by where the view sits
            where = view.mapTo(w, view.rect().topLeft())
            info["rect"][0] += where.x()
            info["rect"][1] += where.y()
            (OUT / f"{tag}-{name}.json").write_text(json.dumps(info))
        whole_window(w).save(str(OUT / f"{tag}-{name}.png"))
    look_at(view, (1.25, 1.25, 1.25))


def set_fade(w, agree, differ):
    w._agree.setValue(agree)
    w._differ.setValue(differ)
    w._redraw()
    pump(6.0)


def main() -> int:
    global _app
    _app = QApplication.instance() or QApplication(["window_repro"])
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.ask = staticmethod(lambda *a, **k: True)

    import version
    print("tree:", TREE, "version:", getattr(version, "VERSION", "?"))

    w = gamut_app.GamutApp([])
    w.resize(1240, 860)
    w.show()
    pump(2.0)

    # ---------------- scene A: 2019 solid vs 2021 outline, rings ----------
    w._load(P2019)
    pump(4.0)
    w._file_dialog = lambda *a, **k: ChoosesForYou(P2021)
    compare_with(w, "icc")
    w._style_mine.setCurrentIndex(0)
    w._style_second.setCurrentIndex(2)
    w._rings_on.setChecked(True)
    w._redraw(); pump(6.0)
    for agree, differ in ((0, 100), (100, 0), (100, 100), (99, 100)):
        set_fade(w, agree, differ)
        harvest_state(w, f"A-a{agree}-d{differ}")

    # ---------------- scene B: + chart with a solid skin, vs sRGB ---------
    compare_with(w, "space", "sRGB")
    w._open_chart_file(CHART)
    pump(4.0)
    at = w._chart_skin.findData("solid")
    if at >= 0:
        w._chart_skin.setCurrentIndex(at)
    w._redraw(); pump(6.0)
    for agree, differ in ((0, 100), (99, 100), (100, 100)):
        set_fade(w, agree, differ)
        harvest_state(w, f"B-a{agree}-d{differ}")
        if agree == 0:
            # WHICH TRACE PAINTS THE FLAT LID: hide one surface at a time.
            view = w._view
            for label, needle in (("noskin", "skin over"),
                                  ("noshell", "printer-2019")):
                ask(view, """(function(){
                  var d=document.getElementsByClassName('plotly-graph-div')[0];
                  var hide=[];
                  d.data.forEach(function(t,i){
                    if ((t.name||'').indexOf('%s')===0
                        || (t.name||'').indexOf('%s')>=0 && t.type==='mesh3d')
                      hide.push(i);
                  });
                  Plotly.restyle(d, {visible:'legendonly'}, hide);
                  return hide.length;
                })()""" % (needle, needle))
                pump(1.5)
                whole_window(w).save(str(OUT / f"B-a0-{label}.png"))
                ask(view, """(function(){
                  var d=document.getElementsByClassName('plotly-graph-div')[0];
                  var back=[];
                  d.data.forEach(function(t,i){
                    if (t.visible==='legendonly') back.push(i);
                  });
                  Plotly.restyle(d, {visible:true}, back);
                  return back.length;
                })()""")
                pump(1.5)
        # frame time under a relayout-driven turn
        view = w._view
        ask(view, FRAME_JS)
        end = time.time() + 8
        while time.time() < end:
            done = ask(view, "window.__ftdone", seconds=1.0)
            if done:
                break
            pump(0.3)
        times = ask(view, "JSON.stringify(window.__ft||[])", seconds=3.0)
        ts = sorted(json.loads(times or "[]"))
        if ts:
            med = ts[len(ts) // 2]
            print(f"  [B-a{agree}-d{differ}] frames {len(ts)}, "
                  f"median {med:.1f} ms, p90 {ts[int(len(ts)*0.9)]:.1f} ms")
            (OUT / f"B-a{agree}-d{differ}-frames.json").write_text(
                json.dumps(ts))
    w.close()
    print("done ->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
