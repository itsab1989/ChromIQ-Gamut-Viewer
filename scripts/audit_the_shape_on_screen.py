"""Is the shape on the screen the shape in the numbers? Judged by looking.

    python scripts/audit_the_shape_on_screen.py <a folder to work in>

WHY. Everything else here checks the numbers that go INTO the picture. This
renders the picture and reads it back, because the faults that get reported
are seen, not computed: "this one looks scattered", "instead this zig zag".

WHAT IT KNOWS IN ADVANCE. A convex hull seen from anywhere covers a CONVEX
patch of the screen. So the lit pixels, divided by the area of their own
convex hull, must come to about one. It is measured from four cameras and
against a deliberately DENTED copy of the same shape:

    camera   whole    dented
    a        0.9934   0.9618
    b        0.9460   0.8774
    c        0.9658   0.8904
    d        0.9946   0.9148

⚠ READ IT PER CAMERA, NOT AS ONE NUMBER. "Whole" runs from 0.946 to 0.995,
and a dent at one camera (0.962) scores higher than a whole shape at another
(0.946), so an absolute threshold separates nothing. The shortfall is the
mask, not the drawing: where the gamut is dark it renders nearly black and
falls under the brightness cut, biting a piece out of the region measured.

⚠ AND IT CANNOT SEE A MISSING TRIANGLE. The first version of this tried to
prove itself by deleting 60 of the paper's 414 faces, and whole and holed came
out identical to three decimals — because an opaque closed shape shows its own
INSIDE through a hole and the outline never moves. Only something that moves
the outline shows up here. That is the shape of what this can and cannot do,
and it is why the mutation below dents the geometry instead.

⚠ THE FIRST RUN ALSO REPORTED 0.507 AND MEANT NOTHING BY IT: the legend's
swatch is coloured too, so the hull was drawn around the shape AND the legend
and came out half empty. Only the biggest lit blob is measured now.
"""
import sys, pathlib, dataclasses
sys.path.insert(0, "python")
import numpy as np, ti3gamut
from gamutview import build_gamut
from scipy.spatial import ConvexHull
from scipy import ndimage
OUT = pathlib.Path(sys.argv[1])
paper = build_gamut(ti3gamut.read_measurement("demo/Glossy-paper.ti3").lab,
                    input_space="lab")
v = np.asarray(paper.vertices, float)
mid = v.mean(axis=0)
# A REAL DENT: pull the corners on one side a third of the way in. Those are
# on the outline, so the silhouette must bite inwards. Removing triangles
# would NOT do it -- an opaque closed shape shows its own inside through a
# hole and the outline never moves, which is why the first attempt at this
# could not tell whole from holed.
pull = v[:, 1] > np.percentile(v[:, 1], 65)
dented = v.copy(); dented[pull] = mid + 0.62 * (v[pull] - mid)
CAMS = {"a": dict(eye=dict(x=1.7, y=1.3, z=0.7)),
        "b": dict(eye=dict(x=-1.5, y=1.1, z=-0.9)),
        "c": dict(eye=dict(x=0.3, y=0.2, z=2.1)),
        "d": dict(eye=dict(x=2.0, y=-0.2, z=0.1))}
shapes = {"whole": paper, "dented": dataclasses.replace(paper, vertices=dented)}
for cam, eye in CAMS.items():
    for name, g in shapes.items():
        ti3gamut.write_html([("Glossy-paper", g)], OUT / f"2{cam}-{name}.html",
                            title="silhouette", mode="dark", camera=eye,
                            grid=False, opacity=1.0)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QUrl, QTimer, QEventLoop
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtGui import QImage
app = QApplication.instance() or QApplication(sys.argv)
view = QWebEngineView(); view.resize(820, 700); view.show()
def lit(page, png):
    loop = QEventLoop(); view.loadFinished.connect(lambda ok, l=loop: l.quit())
    view.load(QUrl.fromLocalFile(str(page.resolve())))
    QTimer.singleShot(30000, loop.quit); loop.exec()
    w = QEventLoop(); QTimer.singleShot(4500, w.quit); w.exec()
    view.grab().save(str(png))
    img = QImage(str(png)).convertToFormat(QImage.Format.Format_RGB32)
    p = img.constBits(); p.setsize(img.sizeInBytes())
    a = np.frombuffer(p, np.uint8).reshape(img.height(), img.bytesPerLine()//4, 4)[:, :img.width(), :3].astype(int)
    hi = a.max(axis=2); lo = a.min(axis=2)
    m = (hi > 40) & ((hi - lo) > 25)
    # ONLY THE BIGGEST BLOB. The legend's swatch is coloured too, and a hull
    # drawn round the shape AND the legend is half empty by construction --
    # which is exactly the 0.507 the first run reported as if it meant
    # something about the drawing.
    lab, n = ndimage.label(m)
    if not n: return m & False
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    return lab == (int(np.argmax(sizes)) + 1)
print(f"  {'camera':<8}{'state':<9}{'lit':>10}{'hull':>10}   ratio")
for cam in CAMS:
    for name in shapes:
        m = lit(OUT / f"2{cam}-{name}.html", OUT / f"2{cam}-{name}.png")
        ys, xs = np.nonzero(m)
        pts = np.stack([xs, ys], 1).astype(float)
        h = ConvexHull(pts)
        print(f"  {cam:<8}{name:<9}{len(xs):>10,}{h.volume:>10,.0f}   {len(xs)/h.volume:6.4f}")
