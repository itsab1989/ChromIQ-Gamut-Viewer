"""Harvest what page 14 actually draws, camera by camera.

Loads docs/pages/14-a-paper-against-adobe-rgb.html, puts it in the reported
state (agreement pressed down to 0%, the Adobe RGB outline hidden by its key),
then for a sweep of camera eyes records:

  * one screenshot per camera,
  * the exact model/view/projection matrices the GL scene used for it,
  * the canvas position inside the window,

plus, once, the mesh as drawn (vertices, the kept triangle list, the vertex
colours, the stand mask, lighting, lightposition).

Everything lands in OUT as camNNN.png + a JSON per camera + mesh.json, for
the offline classifier to chew on. Run on a real screen, not offscreen -- an
offscreen grab comes back blank and reads as coverage.

Usage: harvest.py <out-dir> <mode> <cameras.json>
  mode: agree0-hidden | agree0-shown | agree50-hidden | asaved-hidden
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "")
HERE = pathlib.Path(__file__).resolve().parent
FORK = pathlib.Path(os.environ.get(
    "FORK", str(HERE.parent / "fork"))).resolve()
ARGS = sys.argv[1:]
sys.argv = ["harvest"]

from PyQt6.QtCore import QEventLoop, QTimer, QUrl              # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView            # noqa: E402
from PyQt6.QtWidgets import QApplication                       # noqa: E402


def main() -> int:
    out = pathlib.Path(ARGS[0]); out.mkdir(parents=True, exist_ok=True)
    mode = ARGS[1]
    cameras = json.loads(pathlib.Path(ARGS[2]).read_text())

    app = QApplication.instance() or QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(900, 760)
    view.show()

    def wait(ms):
        loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

    def ask(js, ms=3500):
        got = []
        view.page().runJavaScript(js, got.append)
        wait(ms)
        return got[0] if got else None

    page = FORK / "docs/pages/14-a-paper-against-adobe-rgb.html"
    view.load(QUrl.fromLocalFile(str(page)))
    for _ in range(40):
        wait(500)
        ok = ask("(function(){var d=document.getElementsByClassName("
                 "'plotly-graph-div')[0];return !!(d&&d._fullLayout&&"
                 "d._fullLayout.scene&&d._fullLayout.scene._scene);})()",
                 ms=800)
        if ok:
            break
    else:
        print("page never became ready"); return 1
    wait(1500)

    # ---- the reported state, pressed the way the owner presses it --------
    if mode.startswith("agree0") or mode.startswith("agree50"):
        target = "0%" if mode.startswith("agree0") else "50%"
        for _ in range(30):
            says = ask("(function(){var n=document.querySelector("
                       "'[data-cq=\"agree-at\"]');return n?n.textContent:'';"
                       "})()", ms=300)
            if says == target:
                break
            ask("(function(){var b=document.querySelector("
                "'[data-cq=\"agree-less\"]');if(b)b.click();return 1;})()",
                ms=900)
        else:
            print("could not reach", target, "got", says); return 1
        print("agreement now:", says)

    if mode.endswith("hidden"):
        n = ask("""(function(){
          var d=document.getElementsByClassName('plotly-graph-div')[0];
          var hide=[];
          d.data.forEach(function(t,i){
            if ((t.name||'').indexOf('(outline)')>=0) hide.push(i);
          });
          if (hide.length) Plotly.restyle(d, {visible:'legendonly'}, hide);
          return hide.length;
        })()""", ms=4000)
        print("outline traces hidden:", n)
    wait(1000)

    # ---- the mesh as drawn now -------------------------------------------
    mesh = ask("""(function(){
      var d=document.getElementsByClassName('plotly-graph-div')[0];
      var out=null;
      (d._fullData||[]).forEach(function(t,i){
        if (t.type==='mesh3d' && t.meta && t.meta.stand) {
          var s=Array.prototype.slice;
          out={at:i, n:(t.x||[]).length,
               x:s.call(t.x), y:s.call(t.y), z:s.call(t.z),
               i:s.call(t.i), j:s.call(t.j), k:s.call(t.k),
               vertexcolor:s.call(t.vertexcolor||[]),
               stand:t.meta.stand, opacity:t.opacity,
               lighting:t.lighting, lightposition:t.lightposition};
        }
      });
      return JSON.stringify(out ? {found:true, at:out.at, n:out.n,
        faces:out.i.length, mesh:out} : {found:false});
    })()""", ms=6000)
    got = json.loads(mesh) if mesh else {"found": False}
    if not got.get("found"):
        print("no standing mesh found"); return 1
    (out / "mesh.json").write_text(json.dumps(got["mesh"]))
    print("mesh: trace", got["at"], got["n"], "vertices,",
          got["faces"], "faces drawn")

    # ---- the sweep ---------------------------------------------------------
    ratio = view.grab().width() / view.width()
    for name, ex, ey, ez in cameras:
        ask("(function(){var d=document.getElementsByClassName("
            "'plotly-graph-div')[0];return Plotly.relayout(d,"
            "{'scene.camera.eye':{x:%f,y:%f,z:%f}})&&'ok';})()"
            % (ex, ey, ez), ms=900)
        view.update(); wait(400)
        cam = ask("""(function(){
          var d=document.getElementsByClassName('plotly-graph-div')[0];
          var sc=d._fullLayout.scene._scene, gp=sc.glplot;
          var cp=gp.cameraParams, s=Array.prototype.slice;
          var cv=d.getElementsByTagName('canvas')[0];
          var r=cv.getBoundingClientRect();
          return JSON.stringify({
            model:s.call(cp.model), view:s.call(cp.view),
            projection:s.call(cp.projection),
            dataScale:s.call(sc.dataScale),
            buf:[gp.gl.drawingBufferWidth, gp.gl.drawingBufferHeight],
            rect:[r.left, r.top, r.width, r.height]});
        })()""", ms=1500)
        if not cam:
            print("no cameraParams at", name); return 1
        info = json.loads(cam)
        info["eye"] = [ex, ey, ez]
        info["ratio"] = ratio
        (out / f"{name}.json").write_text(json.dumps(info))
        view.grab().save(str(out / f"{name}.png"))
        print("  shot", name, "eye", (ex, ey, ez))
    print("done:", len(cameras), "cameras ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
