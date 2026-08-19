"""A saved page, opened at the sizes people really have.

WHY. The pages this application writes are the thing somebody SHARES -- to a
customer, a paper maker, a forum -- and they are opened on whatever the reader
happens to have: a laptop, a wide desktop, half a screen beside an email, a
phone held upright. Every one of them had been looked at in one engine at one
size, which is not a test, it is an anecdote.

WHAT IT ASKS, of each size, inside the page itself:

  1. does the page scroll SIDEWAYS?  A page that does is one somebody has to
     drag left and right to read, and it is the commonest way a layout that
     was fine on the author's screen fails on the reader's;
  2. does anything stick out past the window's edge?
  3. is the reader's control strip still reachable -- all of its buttons
     inside the window rather than off the bottom or the side;
  4. and is the shape actually drawn: a canvas, with a live WebGL context,
     sized to something rather than nothing.

WHAT IT CANNOT ANSWER. This runs in QtWebEngine, which is Chromium -- so it
speaks for Chrome and Edge, and NOT for Firefox or Safari. Those two need a
real window and a pair of eyes; a headless Firefox screenshot cannot even
photograph a WebGL canvas (measured: a canvas cleared to bright pink comes out
background-coloured), so a blank picture from one proves nothing at all.

    python scripts/audit_the_page_at_any_size.py [page.html ...]
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "python"))

import prefs  # noqa: E402

prefs.use_a_scratch_store()

# THE ARGUMENTS ARE TAKEN BEFORE QT IS GIVEN A TIDY sys.argv, and that order
# is the whole point: overwriting sys.argv first threw away the page this was
# asked to look at, so a run pointed at a deliberately broken page cheerfully
# audited the default ones instead and reported them clean. The mutation test
# caught it, by reading WHICH pages the output named rather than the exit
# code.
ASKED_FOR = [a for a in sys.argv[1:] if a.endswith(".html")]
sys.argv = ["audit_the_page_at_any_size"]

from PyQt6.QtCore import QUrl                                  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView            # noqa: E402
from PyQt6.QtWidgets import QApplication                       # noqa: E402

#: The shapes of window a reader actually has. The last is a phone upright,
#: which is the one nobody tests and everybody uses.
SIZES = [(1680, 1000), (1280, 860), (1024, 700), (820, 900), (620, 800),
         (390, 780)]

ASK = """(function () {
  var d = document.documentElement, b = document.body;
  var out = {
    // WHETHER THIS IS THE PAGE AT ALL. Everything below reads as clean on a
    // blank document, so the first thing asked is whether anything arrived.
    here: (document.title || '') + '|' + (b ? b.innerHTML.length : 0),
    w: window.innerWidth, h: window.innerHeight,
    sideways: Math.max(d.scrollWidth, b ? b.scrollWidth : 0) - d.clientWidth,
    canvases: 0, gl: 0, glw: 0, past: [], strip: null
  };
  // AND HOW MUCH IS DRAWN IN SVG, because not every page is a 3D scene: the
  // run pages are LINE GRAPHS, which Plotly draws as SVG paths and which have
  // no canvas at all. Demanding a canvas of those reported six faults that
  // were the check's own assumption.
  var paths = document.querySelectorAll('svg path, svg .point, svg .trace');
  out.svg = paths.length;
  var cs = document.getElementsByTagName('canvas');
  out.canvases = cs.length;
  for (var i = 0; i < cs.length; i++) {
    var g = null;
    try { g = cs[i].getContext('webgl2') || cs[i].getContext('webgl'); }
    catch (e) {}
    if (g) { out.gl++; out.glw = Math.max(out.glw, g.drawingBufferWidth); }
  }
  var all = document.querySelectorAll('button, a, .cq-controls, .modebar');
  for (var j = 0; j < all.length; j++) {
    var r = all[j].getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > d.clientWidth + 1 || r.left < -1) {
      out.past.push((all[j].textContent || all[j].className || 'element')
                    .trim().slice(0, 24) + ' @' + Math.round(r.left) + '..' +
                    Math.round(r.right));
    }
  }
  return JSON.stringify(out);
})()"""


def main() -> int:
    import json

    # ABSOLUTE, ALWAYS. QUrl.fromLocalFile takes the path as given, so a
    # relative one silently loads nothing -- and a page that never loaded
    # answers every question with a clean-looking nothing: no canvas, no
    # sideways scroll, no element past the edge. Seven pages were reported
    # that way before this line existed, and the giveaway was that even the
    # 3D ones said "0 canvas".
    pages = [pathlib.Path(a).resolve() for a in ASKED_FOR]
    if not pages:
        pages = [ROOT / "docs" / "pages" / "11-everything-handed-over.html",
                 ROOT / "docs" / "pages" / "04-two-papers.html"]
    app = QApplication(sys.argv)
    view = QWebEngineView()
    problems: list = []
    for page in pages:
        if not page.is_file():
            problems.append(f"{page.name}: not there")
            continue
        for wide, tall in SIZES:
            view.resize(wide, tall)
            view.show()
            view.load(QUrl.fromLocalFile(str(page)))
            end = time.time() + 25
            box: dict = {}
            done = [False]
            view.loadFinished.connect(lambda ok: done.__setitem__(0, True))
            while time.time() < end and not done[0]:
                app.processEvents()
                time.sleep(0.01)
            settle = time.time() + 6      # the shape is built after load
            while time.time() < settle:
                app.processEvents()
                time.sleep(0.01)
            view.page().runJavaScript(ASK, lambda r: box.setdefault("r", r))
            waited = time.time() + 10
            while "r" not in box and time.time() < waited:
                app.processEvents()
                time.sleep(0.01)
            got = json.loads(box.get("r") or "{}")
            if not got:
                problems.append(f"[{page.name} {wide}x{tall}] the page never "
                                f"answered")
                continue
            where = f"[{page.name} {wide}x{tall}]"
            # A PAGE THAT DID NOT ARRIVE CANNOT BE AUDITED, and must never be
            # reported as though it had been.
            body = int((got.get("here") or "|0").split("|")[-1] or 0)
            if body < 500:
                problems.append(f"{where} the page did not load at all "
                                f"({body} bytes of body) — nothing below this "
                                f"was measured")
                continue
            if got["sideways"] > 1:
                problems.append(f"{where} scrolls SIDEWAYS by "
                                f"{got['sideways']}px")
            for item in got["past"]:
                problems.append(f"{where} past the edge: {item}")
            drawn_in_gl = got["canvases"] >= 1 and got["gl"] >= 1 and got["glw"] >= 1
            drawn_in_svg = got.get("svg", 0) >= 20
            if got["canvases"] >= 1 and not drawn_in_gl:
                problems.append(f"{where} a canvas with no live WebGL context")
            elif not drawn_in_gl and not drawn_in_svg:
                problems.append(
                    f"{where} nothing is drawn — no WebGL canvas and only "
                    f"{got.get('svg', 0)} SVG marks")
            print(f"  {where}: {got['canvases']} canvas, gl {got['gl']}, "
                  f"svg {got.get('svg', 0)}, "
                  f"sideways {got['sideways']}px, "
                  f"{len(got['past'])} past the edge")
    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} problem(s).")
        return 1
    print(f"  Clean: {len(pages)} page(s) at {len(SIZES)} sizes, from a wide "
          f"desktop down to a phone held upright.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
