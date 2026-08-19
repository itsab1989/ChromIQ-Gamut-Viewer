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
speaks for Chrome and Edge, and NOT for Firefox or Safari. Those are
`audit_other_engines.py`'s job: the same questions, from `page_questions.py`,
asked of real Gecko and real WebKit. One caveat carries over from measuring:
a headless Firefox SCREENSHOT cannot photograph a WebGL canvas (a canvas
cleared to bright pink comes out background-coloured), but the canvas's own
context answers truthfully in all three engines, which is what the questions
read.

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

# THE QUESTIONS LIVE IN ONE PLACE, shared with the audit that asks them of
# Firefox, WebKit and stock Chromium. Two private copies is how one audit
# quietly starts asking something easier than the other.
sys.path.insert(0, str(HERE))
from page_questions import ASK, SIZES, judge, said             # noqa: E402


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
            found = judge(got, where)
            problems.extend(found)
            if not (len(found) == 1 and "did not load" in found[0]):
                print(f"  {where}: {said(got)}")
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
