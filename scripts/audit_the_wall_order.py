"""Is drawing the far wall first ever WORSE than not?

    python scripts/audit_the_wall_order.py

Exit code 1 if any state comes out rougher with the wall order on, or if a
shape loses any of its outline.

WHY. The far wall is now drawn wholly before the near wall, which fixed the
kite-shaped wedges -- measured on ONE shape at ONE camera. That is a default
that changes every see-through picture in the application and in every page
it saves, and one measurement is not a licence for it.

So it is crossed: several cameras against several things to draw, each on ONE
page with the switch thrown, which is the only fair comparison -- two
separately loaded pages are framed to their own content by fitToPane.

KNOWN IN ADVANCE, and both are failure directions:
  * ROUGHER anywhere means the reordering hurts that state.
  * FEWER LIT PIXELS means something stopped being drawn, which this is not
    supposed to be able to do: it drops nothing, it only reorders.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import tempfile

#: ON A REAL SCREEN, and that is not a preference. Run offscreen, the grab
#: comes back blank -- "SKIA: Failed to begin write access" -- so every
#: roughness is 0.000, every difference is +0.000, and the audit reports
#: CLEAN having looked at nothing. A check that cannot see is worse than no
#: check, because it reads as coverage.
os.environ.setdefault("QT_QPA_PLATFORM", "")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_the_wall_order"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

from PIL import Image                                          # noqa: E402
from PyQt6.QtCore import QEventLoop, QTimer, QUrl              # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView            # noqa: E402
from PyQt6.QtWidgets import QApplication                       # noqa: E402

import references, ti3gamut                                    # noqa: E402

#: How much rougher counts as worse. Two grabs of one unchanged page differ
#: by a little; this is comfortably above that and well below the 0.2 the
#: fix itself is worth.
NOISE = 0.02


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(900, 760)
    view.show()
    folder = pathlib.Path(tempfile.mkdtemp(prefix="wallorder-"))

    def wait(ms):
        loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

    def ask(js, ms=2500):
        got = []
        view.page().runJavaScript(js, got.append)
        wait(ms)
        return got[0] if got else None

    def look():
        """Roughness of the whole drawn shape, and how much of it is lit."""
        view.update(); wait(500); view.grab(); wait(500)
        shot = folder / "now.png"
        view.grab().save(str(shot))
        im = Image.open(shot).convert("RGB")
        px = im.load(); wide, tall = im.size
        g = lambda x, y: sum(px[x, y]) / 3
        lit = steps = n = 0
        for y in range(2, tall - 2, 2):
            for x in range(2, wide - 2, 2):
                if g(x, y) <= 45:
                    continue
                lit += 1
                steps += abs(g(x, y) - g(x + 2, y)) + abs(g(x, y) - g(x, y + 2))
                n += 2
        return lit, round(steps / max(1, n), 3)

    import demo_profiles
    profiles = demo_profiles.the_run_of_profiles()
    if len(profiles) < 2:
        print("  no demo profiles to draw")
        return 1
    shells = [(p.stem, references.icc_gamut(p)) for p in profiles[:2]]

    #: WHAT IS DRAWN. One shape is the simple case; two exercise the pooling,
    #: where the surfaces are welded into one and the walls of BOTH have to
    #: come out in the right order.
    scenes = [("one shape", shells[:1], 0.68),
              ("two shapes", shells, 0.68),
              ("two, one nearly clear", shells, 0.30),
              ("two, nearly solid", shells, 0.92)]

    #: FROM EVERYWHERE. Including the height that tore the old culling, and
    #: one from below, where the far wall is the floor of the shape.
    cameras = [("settled", 1.5, 1.5, 1.5), ("level", 2.2, 0.0, 0.9),
               ("from behind", -1.6, -1.6, 1.2), ("from below", 1.4, 1.4, -1.3),
               ("edge on", 0.1, 2.4, 0.2), ("high above", 0.6, 0.6, 2.6)]

    problems = []
    best = -9.9

    #: AND THE PAGE MUST ARRIVE WITH IT ON. Everything below throws the
    #: switch itself, so it measures the MECHANISM and says nothing about
    #: what a reader gets -- proved by mutation: switching the default off in
    #: the source left this audit reporting "Clean", because it turns it on
    #: before looking. The default is a separate claim and needs asking for
    #: separately.
    def default_is_on():
        said = ask("JSON.stringify(window.cqOrder.how())")
        try:
            return bool(json.loads(said).get("wall"))
        except Exception:                                  # noqa: BLE001
            return None
    print(f"  {'scene':24s} {'camera':12s} {'off':>7} {'ON':>7} {'better by':>10}"
          f"  {'lit lost':>9}")
    for label, shapes, opacity in scenes:
        out = folder / f"{label.replace(' ', '-').replace(',', '')}.html"
        ti3gamut.write_html(shapes, out, "", carry_viewer=True, controls=False,
                            opacity=opacity, grid=False)
        loop = QEventLoop()
        view.loadFinished.connect(lambda _ok: QTimer.singleShot(3200, loop.quit))
        view.load(QUrl.fromLocalFile(str(out)))
        QTimer.singleShot(25000, loop.quit); loop.exec()
        # Asked once per scene, before anything is switched.
        arrived = default_is_on()
        if arrived is False:
            problems.append(
                f"[{label}] the page arrives with the wall order OFF, so a "
                f"reader gets the wedges however well the switch works")
        elif arrived is None:
            problems.append(
                f"[{label}] the engine does not say whether the wall order "
                f"is on, so the default cannot be checked")
        for where, ex, ey, ez in cameras:
            ask("(function(){var d=document.getElementsByClassName("
                "'plotly-graph-div')[0];return Plotly.relayout(d,"
                "{'scene.camera.eye':{x:%f,y:%f,z:%f}})&&'ok';})()"
                % (ex, ey, ez), 2500)
            wait(900)
            ask("window.cqOrder.wallOrder(false, 1)")
            wait(700)
            lit_off, rough_off = look()
            ask("window.cqOrder.wallOrder(true, 1)")
            wait(700)
            lit_on, rough_on = look()
            better = rough_off - rough_on
            best = max(best, better)
            lost = lit_off - lit_on
            # NOTHING DRAWN IS NOT A PASS. If the grab came back blank there
            # is nothing to compare and the answer is unknown, not clean.
            if lit_off < 500:
                problems.append(
                    f"[{label} / {where}] only {lit_off} lit pixels -- the "
                    f"picture did not reach the grab, so this state was not "
                    f"measured")
            print(f"  {label:24s} {where:12s} {rough_off:7.3f} {rough_on:7.3f} "
                  f"{better:+10.3f}  {lost:9d}")
            if better < -NOISE:
                problems.append(
                    f"[{label} / {where}] rougher with the wall order on: "
                    f"{rough_off:.3f} became {rough_on:.3f}")
            if lost > max(40, lit_off * 0.002):
                problems.append(
                    f"[{label} / {where}] {lost} lit pixels went missing; "
                    f"the reordering is not supposed to drop anything")

    # AND IT HAS TO DO SOMETHING SOMEWHERE. Only asking "is it ever worse"
    # passes perfectly with the whole thing switched off -- every difference
    # would be 0.000 and nothing is worse than nothing. The state it was
    # built for is a shape seen from where a reader actually sits, so at
    # least one state must come out better by more than noise.
    if best <= NOISE:
        problems.append(
            f"the wall order improved nothing anywhere -- the best was "
            f"{best:+.3f}, which is inside noise. Is it still switched on?")

    import shutil
    shutil.rmtree(folder, ignore_errors=True)
    print()
    for line in problems:
        print("  " + line)
    if problems:
        print(f"\n{len(problems)} state(s) came out worse.")
    else:
        print("  Clean: the wall order is never worse, and never loses the "
              "outline.")
    view.deleteLater()
    sys.stdout.flush()
    return 1 if problems else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
