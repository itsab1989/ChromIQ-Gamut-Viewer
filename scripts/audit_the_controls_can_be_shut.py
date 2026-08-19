"""Whatever you open in a saved page, you can close again.

    ../gv-venv/bin/python scripts/audit_the_controls_can_be_shut.py

WHY THIS EXISTS. Reported from an iPhone, on a viewer wrapped in a frame on
the showcase page: "they fill the whole frame and i can't see the less button
any more so i can't close them and effectively can't see the shape again,
effectively giving me no real ability to use the controls without being locked
out."

A control that cannot be shut is worse than one that was never offered: the
shape goes away and nothing brings it back. The two faults behind it were a
panel whose only height cap sat behind `@media (max-height:560px)`, so a 608 px
frame got none and it opened TALLER than the thing it sat in, and a
scrollIntoView that walked up into the showcase and carried the strip off the
top of the frame.

WHAT MUST BE TRUE, in every state below, each answer known in advance:

  the panel never exceeds the view it opens into  -- or part of it is
      unreachable however you scroll;
  the way back stays inside the view              -- the one control that must
      never be lost is the one that closes it;
  pressing it again puts the picture back         -- a fix that leaves the
      reader looking at empty page is the same fault in the other direction.

CROSSED, BECAUSE ONE AT A TIME PROVED NOTHING HERE. The fault needed a
particular height AND a frame: it was invisible on a desktop, invisible on a
short phone (where the old media query did apply), and invisible in a page
opened directly. So: three heights x framed and standalone x two engines.

MEASURED FROM INSIDE. Reading the button's position in the OUTER page's
coordinates reported "out of reach" every time, including once when the fix
had already worked — the frame's own scroll and the page's are different
things. Every reading here is taken in the document that owns the button.
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SHOWCASE = HERE.parent / "docs" / "showcase"
INDEX = SHOWCASE / "index.html"
#: A scene page with the full set of controls behind "more…".
PAGE = SHOWCASE / "pages" / "02-against-adobe-rgb.html"

#: Heights that matter: the one reported, one just under the old media query
#: where the cap DID apply, and a roomy one.
HEIGHTS = (608, 540, 900)

ASK = """(function () {
  var more = document.querySelector('button[data-cq="more"]');
  var panel = document.querySelector('.cq-spin-panel');
  if (!more) return null;
  var m = more.getBoundingClientRect();
  var p = panel ? panel.getBoundingClientRect() : null;
  return {label: (more.textContent || '').trim(),
          top: Math.round(m.top), bottom: Math.round(m.bottom),
          view: window.innerHeight,
          reachable: m.top >= 0 && m.bottom <= window.innerHeight,
          panel: p ? Math.round(p.height) : 0,
          hidden: panel ? !!panel.hidden : true,
          canvas: !!document.querySelector('canvas')};
})()"""


def main() -> int:
    for needed in (INDEX, PAGE):
        if not needed.is_file():
            print(f"missing {needed} — run make_showcase_pages.py first")
            return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed, so this check is skipped.\n"
              "  pip install playwright && python -m playwright install "
              "webkit chromium")
        return 0

    problems: list[str] = []
    with sync_playwright() as play:
        try:
            engines = {n: getattr(play, n).launch()
                       for n in ("chromium", "webkit")}
        except Exception as why:                        # noqa: BLE001
            print(f"  no browser, so this check is skipped: {why}")
            return 0

        print(f"  {'engine':9s} {'how':11s} {'view':>5s} {'panel':>6s} "
              f"{'the way back':>14s}  shuts again")
        print("  " + "-" * 66)
        for name, browser in engines.items():
            for height in HEIGHTS:
                for framed in (False, True):
                    tab = browser.new_page(
                        viewport={"width": 390, "height": height},
                        is_mobile=True, has_touch=True)
                    if framed:
                        tab.goto(INDEX.resolve().as_uri())
                        tab.wait_for_timeout(700)
                        tab.locator("figure a[href$='.html']").nth(1).click()
                        tab.wait_for_timeout(9000)
                        where = tab.frame_locator("figure iframe").first
                        doc = tab.frames[-1]
                    else:
                        tab.goto(PAGE.resolve().as_uri())
                        tab.wait_for_timeout(6000)
                        where = tab
                        doc = tab
                    how = "in a frame" if framed else "on its own"

                    opener = where.locator('button[data-cq="more"]').first
                    if not opener.count():
                        problems.append(f"{name} {how} {height}: no controls "
                                        f"to open at all")
                        tab.close()
                        continue
                    opener.click()
                    tab.wait_for_timeout(1200)
                    got = doc.evaluate(ASK)

                    # and pressing it again must bring the picture back
                    where.locator('button[data-cq="more"]').first.click()
                    tab.wait_for_timeout(1000)
                    after = doc.evaluate(ASK)
                    shuts = bool(after and after["hidden"] and after["canvas"])

                    print(f"  {name:9s} {how:11s} {height:5d} "
                          f"{got['panel']:6d} "
                          f"{got['top']:5d}–{got['bottom']:<8d} "
                          f"{'yes' if shuts else 'NO'}")

                    if got["panel"] > got["view"]:
                        problems.append(
                            f"{name} {how} at {height}: the panel is "
                            f"{got['panel']} px in a {got['view']} px view, so "
                            f"part of it cannot be reached at all")
                    if not got["reachable"]:
                        problems.append(
                            f"{name} {how} at {height}: the way back sits at "
                            f"{got['top']}–{got['bottom']} in a "
                            f"{got['view']} px view — the reader is locked in")
                    if not shuts:
                        problems.append(
                            f"{name} {how} at {height}: pressing it again did "
                            f"not put the picture back")
                    tab.close()
        for browser in engines.values():
            browser.close()

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: the controls fit where they open, the way back is always "
          "on screen,\n  and pressing it again brings the shape back — framed "
          "and on their own,\n  at every height, in both engines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
