"""A saved cross-section opens at the height its sender was looking at.

    ../gv-venv/bin/python scripts/audit_the_cut_opens_where_it_was_saved.py
    ../gv-venv/bin/python scripts/audit_the_cut_opens_where_it_was_saved.py --prove

WHY THIS EXISTS. A page carries the height the cut was saved at, so whoever
opens it sees what was sent. On the page that holds BOTH views it did not: a
page written at L* 50 opened its cut at L* 8, the bottom of the range, while
carrying the right answer -- `at: 21` of 43 levels -- in its own settings all
along.

The cause is worth keeping, because it is the sort of thing that comes back.
The strip is built FIRST for the shapes, where there is no cross-section and
the height is 0 by default. That 0 was stored as the reader's remembered
choice, and restored a moment later when they switched to the cut, over the
top of the height the page was saved at. The shapes view had no business
remembering a cut height at all.

WHAT MUST BE TRUE, and the failure direction:

  the cut opens where it was saved   otherwise the reader is looking at a
                                     different slice from the one that was
                                     sent, with nothing to tell them so;
  on both kinds of page              a cut on its own always got this right,
                                     so a check that only looks at one kind
                                     proves nothing about the other -- and it
                                     was the other that was broken.

MEASURED ON A REAL MEASUREMENT, not on a made-up ball. This began as a rule
inside `audit_two_views.py` and could not be made to fail there even with the
fault deliberately restored: that page's invented shape has a lightness range
narrow enough that the saved height and the bottom of the range round to the
same number. The demo paper spans L* 8 to 92, where the two are eight and
fifty and cannot be confused.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

#: The height the page is written at, chosen to sit well away from both ends.
SAVED_AT = 50.0

#: THE FAULT, PUT BACK ON PURPOSE. The cure was to stop a view that has no
#: cross-section from remembering a cut height at all: the strip is built
#: first for the shapes, where the height is 0 by default, and that 0 was
#: stored as the reader's remembered choice and restored a moment later over
#: the top of the height the page was saved at.
#:
#: ⚠ THIS CHECK HAD NO MUTATION AT ALL. `--prove` re-ran the ordinary pass,
#: found nothing wrong -- correctly, because nothing had been broken -- and
#: announced "this check is blind". It had been saying so since the day it was
#: written, about a fault it never restored. A `--prove` that changes nothing
#: is worse than none: it reads as a checked box.
WITH_THE_FAULT_BACK = ("...(cuts ? {cutAt: cutAt} : {}),", "cutAt: cutAt,")

WHERE = """(function () {
  var s = window.cqSettings || {}, c = s.cuts || null;
  var says = document.querySelector('[data-cq="cut-at"]');
  return JSON.stringify({
    carried: c ? Math.round(c.levels[c.at || 0]) : null,
    levels: c ? c.levels.length : 0,
    says: says ? says.textContent.replace(/[^0-9-]/g, "") : null});
})()"""


def the_paper():
    import ti3gamut
    from gamutview import build_gamut

    demo = HERE.parent / "demo" / "Glossy-paper.ti3"
    if not demo.is_file():
        return None
    return build_gamut(ti3gamut.read_measurement(demo).lab, input_space="lab")


def put_the_fault_back(page: pathlib.Path) -> bool:
    """Rewrite a written page so it remembers a cut height it has not got.

    Done to the FILE rather than to the module, because a page carries its own
    copy of the script and that copy is what a reader runs. Returns whether
    the swap actually landed -- a mutation that quietly matches nothing is the
    fault this whole exercise is about.
    """
    was, now = WITH_THE_FAULT_BACK
    text = page.read_text(encoding="utf-8")
    if was not in text:
        return False
    page.write_text(text.replace(was, now), encoding="utf-8")
    return True


def pages(where: pathlib.Path, paper):
    """The two kinds of page that can hold a cut, each saved at SAVED_AT."""
    import ti3gamut

    cuts = ti3gamut.slice_levels([("Glossy-paper", paper)], include=SAVED_AT)
    cuts["title"] = ""
    cuts["at"] = min(range(len(cuts["levels"])),
                     key=lambda i: abs(cuts["levels"][i] - SAVED_AT))

    both = where / "both.html"
    ti3gamut.write_two_views_html(
        [("The shapes",
          ti3gamut.build_figure([("Glossy-paper", paper)], "Measured gamut")),
         ("A cut through them",
          ti3gamut.build_slice_figure([("Glossy-paper", paper)], SAVED_AT, "",
                                      extent=cuts["extent"], slidable=True))],
        both, spin={"on": False, "cuts": cuts}, controls=True)

    alone = where / "alone.html"
    ti3gamut.write_slice_html([("Glossy-paper", paper)], alone, SAVED_AT,
                              "a cut", controls=True)
    return {"a page holding both views": (both, True),
            "a cut on its own": (alone, False)}


def main() -> int:
    prove = "--prove" in sys.argv
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed, so this check is skipped.")
        return 0

    paper = the_paper()
    if paper is None:
        print("the demo measurement is not here, so this check is skipped.")
        return 0

    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        made = pages(pathlib.Path(tmp), paper)
        if prove:
            landed = [put_the_fault_back(page) for page, _s in made.values()]
            if not all(landed):
                print("  THE MUTATION DID NOT LAND — the line it rewrites is "
                      "not in the written\n  page any more, so this run "
                      "tested nothing. Look at what replaced it\n  before "
                      "believing any Clean report from this check.")
                return 2
            print("  --prove: both pages have been rewritten to remember a "
                  "cut height even\n  when they hold no cut. The cut must "
                  "now open in the wrong place.\n")
        with sync_playwright() as play:
            browser = play.chromium.launch()
            for name, (page, switch) in made.items():
                tab = browser.new_page(viewport={"width": 1100, "height": 800})
                tab.goto(page.resolve().as_uri())
                tab.wait_for_timeout(9000)
                if switch:
                    tab.locator('button[data-cq="view"]').nth(1).click()
                    tab.wait_for_timeout(2500)
                got = json.loads(tab.evaluate(WHERE))
                tab.close()
                print(f"  {name:26s} saved at L* {got['carried']}, "
                      f"opens at L* {got['says']}  "
                      f"({got['levels']} heights to choose from)")
                if got["carried"] is None or not got["says"]:
                    problems.append(f"{name}: no cut was built at all")
                elif str(got["carried"]) != got["says"]:
                    problems.append(
                        f"{name}: opens at L* {got['says']} where it was "
                        f"saved at L* {got['carried']} — the reader is not "
                        f"looking at what was sent")
            browser.close()

    print()
    if prove:
        if problems:
            print("  With the fault restored, the cut opened at the wrong "
                  "height, as it must.\n  The check can see.")
            return 0
        print("  THE CUT STILL OPENED IN THE RIGHT PLACE with the fault "
              "restored. This check is blind.")
        return 1
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: both kinds of page open their cut at the height they were "
          "saved at.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
