"""Every drawing space, written out as a page and opened like a reader would.

    ../gv-venv/bin/python scripts/audit_every_space_can_be_sent.py
    ../gv-venv/bin/python scripts/audit_every_space_can_be_sent.py --prove

WHY THIS EXISTS. Two faults reported from the window on 2026-08-21 had lived
for weeks in configurations that NO saved page held, so every check that reads
`docs/pages` passed while they were broken. The same question asked of the
drawing spaces gives the same answer: measured across the 25 sample pages,
CIELAB appears in 17 and ink amounts in 2 — and **CIELUV and CIE XYZ appear in
none at all**.

WHY NOT SIMPLY ADD TWO MORE SAMPLE PAGES. Each is about five megabytes and
they are rewritten whole every time anything that reaches them changes, which
is why `docs/pages` is 125 MB and `.git` is 381. Coverage does not have to
cost that: this writes one page per space into a temporary folder, opens each
the way a reader would, asks it the same questions the size sweep asks — from
`page_questions.py`, so the two cannot drift apart — and deletes them again.

WHAT IS ASKED, each with its failure direction:

  the page arrives            — a blank page answers every other question
                                cleanly, which is why it is asked first;
  it does not scroll sideways — the commonest way a layout fails on somebody
                                else's screen;
  nothing sits past an edge, and nothing is out of reach of any scroll;
  something is actually drawn — a canvas with a live WebGL context, or
                                enough SVG marks to be a picture;
  and the axis titles are the ones that space uses, so a page written in one
  space and labelled with another's names is caught rather than admired.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "python"))

import prefs  # noqa: E402

prefs.use_a_scratch_store()

ASKED = [a for a in sys.argv[1:]]
sys.argv = ["audit_every_space_can_be_sent"]

from PyQt6.QtCore import QUrl                                  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView            # noqa: E402
from PyQt6.QtWidgets import QApplication                       # noqa: E402

sys.path.insert(0, str(HERE))
from page_questions import ASK, judge, said                    # noqa: E402

#: The spaces the window offers, and the words each one puts on its x axis.
#: Taken from `gamutview.AXES` at run time rather than copied, so a renamed
#: axis fails here instead of quietly matching nothing.
SIZES = [(1440, 900), (620, 800)]


def main() -> int:
    import gamutview
    import ti3gamut
    from gamutview import build_gamut

    paper = ROOT / "demo" / "Glossy-paper.ti3"
    if not paper.is_file():
        print(f"no demo paper at {paper}")
        return 1
    # THE SPACES A MEASURED SHAPE CAN BE DRAWN IN. "Ink amounts" is in the
    # window's chooser and is NOT one of them: it is a chart space — a cloud
    # of patches at the ink values that made them — and `build_gamut` refuses
    # it in as many words ("space must be one of lab, luv, xyz"). Two sample
    # pages already hold a chart drawn that way, so it is covered where it
    # belongs rather than demanded here.
    spaces = [s for s in gamutview.SPACES if s in gamutview.AXES]
    # A LIST THIS CHECK CANNOT SEE LOOKS EXACTLY LIKE A WINDOW THAT OFFERS
    # ONE SPACE. Three is what a shape can be drawn in; fewer means the table
    # moved and this is asking about nothing.
    if len(spaces) < 3:
        print(f"  only {len(spaces)} drawing space(s) found in gamutview.AXES "
              f"— this check cannot see what it is asking about")
        return 2

    m = ti3gamut.read_measurement(paper)
    app = QApplication(sys.argv)
    view = QWebEngineView()
    out = pathlib.Path(tempfile.mkdtemp(prefix="every-space-"))
    problems: list = []
    broken = "--prove" in ASKED
    try:
        for space in spaces:
            gamut = build_gamut(m.lab, m.device, input_space="lab",
                                space=space)
            page = out / f"{space}.html"
            ti3gamut.write_html([(paper.stem, gamut)], page,
                                f"{paper.stem} in {space}", space=space,
                                controls=True)
            if broken and space == "luv":
                # THE MUTATION: the scene's own element renamed, so the
                # drawing library is handed nothing to draw into and the page
                # comes up with no picture at all. It must be caught by
                # "nothing is drawn" — a blank page answers every other
                # question cleanly, which is the whole reason that rule is
                # asked first.
                #
                # ⚠ THE FIRST MUTATION HERE DID NOT LAND: it turned the mesh
                # into a `scatter3d`, and a scatter3d draws perfectly well.
                # The page was reported clean and the check called itself
                # blind, correctly.
                text = page.read_text(encoding="utf-8")
                if 'id="scene0"' not in text:
                    print("  --prove: THE MUTATION DID NOT LAND — no element "
                          "named scene0 to rename")
                    return 2
                page.write_text(text.replace('id="scene0"', 'id="scene0-x"', 1),
                                encoding="utf-8")
            wanted = gamutview.AXES[space]["x"]
            for wide, tall in SIZES:
                view.resize(wide, tall)
                view.show()
                view.load(QUrl.fromLocalFile(str(page)))
                end = time.time() + 25
                done = [False]
                view.loadFinished.connect(lambda ok: done.__setitem__(0, True))
                while time.time() < end and not done[0]:
                    app.processEvents()
                    time.sleep(0.01)
                settle = time.time() + 6
                while time.time() < settle:
                    app.processEvents()
                    time.sleep(0.01)
                box: dict = {}
                view.page().runJavaScript(ASK, lambda r: box.setdefault("r", r))
                waited = time.time() + 10
                while "r" not in box and time.time() < waited:
                    app.processEvents()
                    time.sleep(0.01)
                got = json.loads(box.get("r") or "{}")
                where = f"[{space} {wide}x{tall}]"
                if not got:
                    problems.append(f"{where} the page never answered")
                    continue
                problems.extend(judge(got, where))
                print(f"  {where}: {said(got)}")
            # AND THE WORDS ROUND THE OUTSIDE, which say which space this is.
            text = page.read_text(encoding="utf-8")
            if f'"text":"{wanted}"' not in text.replace("\\u2192", "→"):
                problems.append(
                    f"[{space}] the x axis is not labelled {wanted!r} — a "
                    f"page written in one space and labelled with another's "
                    f"names says the wrong thing about every number on it")
    finally:
        shutil.rmtree(out, ignore_errors=True)

    print()
    if broken:
        if any("nothing is drawn" in p for p in problems):
            print("  --prove: the scene was taken out of the CIELUV page and "
                  "the check said so.\n  It can see.")
            return 0
        print("  --prove: THE MUTATION DID NOT LAND — the page with its scene "
              "taken out\n  was reported as clean, so this check is blind.")
        return 1
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} problem(s).")
        return 1
    print(f"  Clean: {len(spaces)} drawing space(s), each written out as a "
          f"page and opened at {len(SIZES)} sizes.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
