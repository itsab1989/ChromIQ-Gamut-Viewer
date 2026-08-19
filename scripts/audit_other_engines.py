"""The saved pages and the showcase, opened in the engines QtWebEngine is not.

    ../gv-venv/bin/python scripts/audit_other_engines.py [page.html ...]
    ../gv-venv/bin/python scripts/audit_other_engines.py --prove
    ../gv-venv/bin/python scripts/audit_other_engines.py --shots FOLDER

WHY. `audit_the_page_at_any_size.py` runs in QtWebEngine, which is Chromium:
it speaks for Chrome and Edge and for nobody else. The pages this application
writes are opened by whoever they were sent to, and about half the world's
readers hold Safari (WebKit) or Firefox (Gecko). Until this script existed,
those two engines had never been tested at all -- asked for explicitly:
"Exports in other browsers and window sizes".

WHAT IT DOES. Every page, in real Gecko, real WebKit and stock Chromium, is
loaded once and then resized through the same six window shapes the
QtWebEngine audit uses -- a wide desktop down to a phone held upright -- with
the same questions asked at each, from `page_questions.py`: does it scroll
sideways, does anything stick out past the edge, is the reader's strip
reachable, is the shape really drawn. Resizing a live page rather than
reloading at each size is deliberate: it is what a person dragging a window
corner does, and it is the path no other audit covers. The smallest size is
then also given a FRESH load, because a layout computed once at load time can
be wrong in a way a resize never reaches.

WHAT A SCREENSHOT IS WORTH HERE. Chromium's and WebKit's photographs show the
scene; a headless Firefox photograph of a WebGL canvas comes out background-
coloured (measured, twice), so Firefox pictures prove layout and nothing
else. The drawn-or-not question is asked of the canvas's own context, which
answers truthfully in all three.

--prove is the mutation test: it copies a page, injects an element that is
wrong in a way this audit claims to catch (a fixed 3000px-wide strip, which
must scroll sideways at every size), CHECKS THE INJECTION LANDED, and then
demands the audit fail on the copy. A sweep that finds nothing proves nothing
until it has been made to find something.

Exit code 1 if any page at any size in any engine has a problem.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from page_questions import ASK, SIZES, judge, said  # noqa: E402

#: What is opened when no page is named: one of each kind of thing the
#: application saves -- a 3D scene, the heaviest control set, a flat cut,
#: two tied panes, an SVG line graph, the small page that fetches its viewer
#: from the network -- and the showcase page that links to all of them.
#: The index is prose and pictures, not a scene, and is judged as such.
DEFAULT = [
    ("docs/pages/04-two-papers.html", True),
    ("docs/pages/11-everything-handed-over.html", True),
    ("docs/pages/10-a-slice-through-both.html", True),
    ("docs/pages/12-a-cut-each.html", True),
    ("docs/pages/15-one-printer-over-five-years.html", True),
    ("docs/pages/08-without-the-viewer.html", True),
    ("docs/index.html", False),
]

ENGINES = ("chromium", "webkit", "firefox")

#: How long a scene is given to draw itself, altogether.
PATIENCE_MS = 20_000

READY = """(function () {
  var cs = document.getElementsByTagName('canvas');
  for (var i = 0; i < cs.length; i++) {
    var g = null;
    try { g = cs[i].getContext('webgl2') || cs[i].getContext('webgl'); }
    catch (e) {}
    if (g && g.drawingBufferWidth > 0) return true;
  }
  return document.querySelectorAll('svg path').length >= 20;
})()"""


def wait_until_drawn(page, expects_scene: bool) -> None:
    """Give the page until it has drawn something, or its patience runs out.

    A fixed sleep is either too short on the day Chromium falls back to
    software rendering or minutes too long everywhere else. The audit's own
    questions say whether the scene has arrived, so they are what is polled.
    """
    if not expects_scene:
        page.wait_for_timeout(600)
        return
    waited = 0
    while waited < PATIENCE_MS:
        if page.evaluate(READY):
            page.wait_for_timeout(400)   # the strip is built just after
            return
        page.wait_for_timeout(250)
        waited += 250


def look_at(page, where: str, expects_scene: bool, problems: list) -> None:
    got = json.loads(page.evaluate(ASK))
    found = judge(got, where, expects_scene)
    problems.extend(found)
    print(f"  {where}: {said(got)}")


def run(pages, shots: pathlib.Path | None) -> int:
    from playwright.sync_api import sync_playwright

    problems: list = []
    with sync_playwright() as p:
        for engine in ENGINES:
            browser = getattr(p, engine).launch()
            for path, expects_scene in pages:
                page_file = (ROOT / path) if not pathlib.Path(path).is_absolute() \
                    else pathlib.Path(path)
                if not page_file.is_file():
                    problems.append(f"[{engine}] {page_file.name}: not there")
                    continue
                tab = browser.new_page(
                    viewport={"width": SIZES[0][0], "height": SIZES[0][1]})
                tab.goto(page_file.resolve().as_uri())
                wait_until_drawn(tab, expects_scene)
                for wide, tall in SIZES:
                    tab.set_viewport_size({"width": wide, "height": tall})
                    tab.wait_for_timeout(700)   # the library re-lays itself out
                    where = f"[{engine} {page_file.name} {wide}x{tall}]"
                    before = len(problems)
                    look_at(tab, where, expects_scene, problems)
                    if shots and (len(problems) > before
                                  or (wide, tall) in (SIZES[1], SIZES[-1])):
                        shots.mkdir(parents=True, exist_ok=True)
                        tab.screenshot(path=str(
                            shots / f"{engine}-{page_file.stem}-{wide}x{tall}.png"))
                # AND THE SMALLEST SIZE FROM COLD, because a layout computed
                # once at load time can be wrong in a way no resize reaches.
                wide, tall = SIZES[-1]
                tab.set_viewport_size({"width": wide, "height": tall})
                tab.reload()
                wait_until_drawn(tab, expects_scene)
                look_at(tab, f"[{engine} {page_file.name} {wide}x{tall} "
                             f"fresh]", expects_scene, problems)
                tab.close()
            browser.close()

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} problem(s).")
        return 1
    print(f"  Clean: {len(pages)} page(s), {len(ENGINES)} engines, "
          f"{len(SIZES)} sizes and a cold load at the smallest.")
    return 0


def prove() -> int:
    """Break a page on purpose and demand this audit notice.

    The injection is asserted to have landed first: a mutation that silently
    fails to apply looks exactly like a blind check passing.
    """
    import tempfile

    source = ROOT / "docs" / "pages" / "04-two-papers.html"
    body = source.read_text(encoding="utf-8")
    marker = "</body>"
    assert marker in body, f"the page has no {marker}; the mutation cannot land"
    wrong = ('<div style="position:static;width:3000px;height:8px;'
             'background:#f0f">wide on purpose</div></body>')
    broken = body.replace(marker, wrong, 1)
    assert broken != body and "wide on purpose" in broken, \
        "the mutation did not land"
    folder = pathlib.Path(tempfile.mkdtemp(prefix="engine-audit-prove-"))
    target = folder / "broken-on-purpose.html"
    target.write_text(broken, encoding="utf-8")
    print(f"a deliberately broken page: {target}\n")
    code = run([(str(target), True)], shots=None)
    import shutil
    shutil.rmtree(folder, ignore_errors=True)
    if code == 0:
        print("\nTHE AUDIT DID NOT NOTICE a 3000px strip. It is blind, and "
              "its Clean means nothing.")
        return 1
    print("\nThe audit failed on the broken page, as it must. It can see.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="*", help="pages to audit (default: one "
                    "of each kind the application saves, and the showcase)")
    ap.add_argument("--prove", action="store_true",
                    help="mutation-test the audit itself")
    ap.add_argument("--shots", default=None, metavar="FOLDER",
                    help="photograph two sizes per page, and every failure")
    args = ap.parse_args()
    if args.prove:
        return prove()
    # AN INDEX IS PROSE AND PICTURES, whatever way it arrives. Demanding a
    # WebGL canvas of one reports the audit's own assumption as a fault.
    pages = ([(a, not pathlib.Path(a).name == "index.html")
              for a in args.pages] if args.pages
             else [(path, scene) for path, scene in DEFAULT])
    return run(pages, pathlib.Path(args.shots) if args.shots else None)


if __name__ == "__main__":
    raise SystemExit(main())
