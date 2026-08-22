"""Show the hatching a lid makes between two shapes that run too close.

DOES THIS PAIR HATCH? Asked with the shapes OPAQUE, which is the only way
the hatching shows -- a semi-transparent shell hides it completely, and that
is how I talked myself into "no hatching anywhere" one cycle ago.
"""
import os, pathlib, sys, time
import numpy as np
ROOT = pathlib.Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "python"))
sys.argv = ["does_it_hatch"]
from PIL import Image
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication
import ti3gamut, references
from gamutview import build_gamut
OUT = (ROOT.parent / "scratch" / "hatchtest").resolve(); OUT.mkdir(exist_ok=True)
DEMO = ROOT / "demo"
app = QApplication.instance() or QApplication(sys.argv)
view = QWebEngineView(); view.resize(1600, 1050); view.show()
def pump(s):
    end = time.time()+s
    while time.time() < end: app.processEvents(); time.sleep(0.01)
pump(2)
def paper(stem):
    return build_gamut(ti3gamut.read_measurement(DEMO / f"{stem}.ti3").lab,
                       input_space="lab")
PAIRS = {
    "one paper twice": [("Glossy-paper", paper("Glossy-paper")),
                        ("months later", paper("Glossy-paper-months-later"))],
    "sRGB vs AdobeRGB, Luv": [
        ("sRGB", references.reference_gamut("sRGB", steps=20, space="luv")),
        ("Adobe RGB (1998)",
         references.reference_gamut("Adobe RGB (1998)", steps=20, space="luv"))],
    "two papers": [("Glossy-paper", paper("Glossy-paper")),
                   ("Matte-paper", paper("Matte-paper"))],
    "a paper vs sRGB": [("Glossy-paper", paper("Glossy-paper")),
                        ("sRGB", references.reference_gamut("sRGB", steps=20))],
}
ti3gamut.TOO_CLOSE_TO_CLOSE = 0.0
def spk(path):
    g = np.asarray(Image.open(path).convert("RGB"), int)
    l = np.abs(g[:, 1:-1] - g[:, :-2]).max(axis=2)
    r = np.abs(g[:, 1:-1] - g[:, 2:]).max(axis=2)
    return (l > 24) & (r > 24)
def shot(gs, cap, tag):
    ti3gamut._LAST_CUT = None; ti3gamut._LAST_CAP = None
    fig = ti3gamut.build_figure(gs, tag, agree=0.45, differ=1.0, opacity=1.0,
                                split=True, cap=cap, styles=["solid", "solid"],
                                camera={"eye": dict(x=-1.5, y=-1.4, z=0.6)})
    f = OUT / f"{tag}.html"
    f.write_text(fig.to_html(include_plotlyjs=True, full_html=True))
    view.load(QUrl.fromLocalFile(str(f.resolve()))); pump(11)
    p = OUT / f"{tag}.png"; view.grab().save(str(p)); return p
for name, gs in PAIRS.items():
    tag = name.replace(" ", "-").replace(",", "")
    on, off = shot(gs, True, tag + "-lid"), shot(gs, False, tag + "-off")
    own = int((spk(on) & ~spk(off)).sum())
    share = ti3gamut.how_far_apart(
        gs[0][1], gs[1][1],
        np.array([50.0, 0.0, 0.0]) if gs[0][1].space == "lab"
        else np.asarray(gs[1][1].vertices, float).mean(axis=0))
    v = np.vstack([np.asarray(gs[0][1].vertices, float),
                   np.asarray(gs[1][1].vertices, float)])
    span = float(np.linalg.norm(v.max(axis=0) - v.min(axis=0)))
    print(f"  {name:<24} share {share/span:.5f}   the lid's own speckle "
          f"{own:>6}   {'HATCHES' if own > 300 else 'clean'}", flush=True)
view.close(); pump(1)
