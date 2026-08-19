"""The showcase page: does every frame explain itself, and does it work?

    ../gv-venv/bin/python scripts/audit_showcase_page.py

WHY THIS EXISTS. The frames on docs/showcase/index.html are photographs of the
viewer, so each one shows a control strip that was not connected to anything.
Reported from the live site: "the controls on the showcase page invited me to
try right there - which is misleading". They are live on demand now, and a new
option carries two obligations here -- a friendly, extensive, easy tooltip
naming the exact control, and a check that the thing actually works.

WHAT MUST BE TRUE, each with its failure direction:

  every figure     links to a page that exists, shows a poster that exists,
                   and the poster has alt text -- otherwise a reader with no
                   pictures is told nothing at all;
  every figure     carries a tooltip long enough to be an explanation, saying
                   what pressing DOES and what it NEEDS, in words rather than
                   mechanism: "iframe", "JavaScript", "DOM" are the wrong
                   vocabulary for somebody reading about paper;
  a plain click    replaces the still with the real page, in place, with a
                   drawing inside it, and leaves the reader on the page;
  after the swap   a line says it is live and offers the full width;
  a Cmd-click      does NOT swap it -- the link must still behave like a link,
                   or middle-click and "open in new tab" quietly break.

Run in real Chromium and real WebKit, because this is a page for other
people's browsers.

Exit code 1 if any of that is untrue.
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
INDEX = HERE.parent / "docs" / "showcase" / "index.html"

#: A tooltip shorter than this is a label, not an explanation.
ENOUGH = 200
#: Words that describe the machinery rather than the outcome.
MACHINERY = ("iframe", "javascript", "dom ", "http", "<div", "css", "api")
#: It has to say what pressing does...
OUTCOME = ("turn", "zoom", "hide", "live")
#: ...and what it asks of the reader before they press.
PREREQUISITE = ("nothing installed", "no account", "seconds", "megabyte")


def main() -> int:
    if not INDEX.is_file():
        print(f"no showcase page at {INDEX}")
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

        for name, browser in engines.items():
            tab = browser.new_page(viewport={"width": 1200, "height": 900})
            tab.goto(INDEX.resolve().as_uri())
            tab.wait_for_timeout(600)
            links = tab.locator("figure a[href$='.html']")
            count = links.count()
            print(f"\n  {name}: {count} figure(s)")
            if count < 8:
                problems.append(f"{name}: only {count} figures found")

            # ---- what every figure promises, before anybody presses --------
            for i in range(count):
                link = links.nth(i)
                href = link.get_attribute("href") or ""
                tip = (link.get_attribute("title") or "").strip()
                label = (link.get_attribute("aria-label") or "").strip()
                shot = link.locator("img")
                alt = (shot.get_attribute("alt") or "").strip() if shot.count() else ""
                src = (shot.get_attribute("src") or "") if shot.count() else ""
                invite = link.locator(".live").count()
                where = f"{name}: figure {i + 1} ({href.split('/')[-1]})"

                if not (INDEX.parent / href).is_file():
                    problems.append(f"{where}: links to a page that is not there")
                if src and not (INDEX.parent / src).is_file():
                    problems.append(f"{where}: its poster {src} is not there")
                if len(alt) < 20:
                    problems.append(f"{where}: the poster has no alt text worth "
                                    f"the name ({len(alt)} characters)")
                if not invite:
                    problems.append(f"{where}: nothing on the picture says it "
                                    f"can be pressed")
                if not label:
                    problems.append(f"{where}: no aria-label, so a screen "
                                    f"reader is offered nothing")
                if len(tip) < ENOUGH:
                    problems.append(f"{where}: the tooltip is {len(tip)} "
                                    f"characters, which is a label and not an "
                                    f"explanation")
                low = tip.lower()
                if not any(w in low for w in OUTCOME):
                    problems.append(f"{where}: the tooltip never says what "
                                    f"pressing it DOES")
                if not any(w in low for w in PREREQUISITE):
                    problems.append(f"{where}: the tooltip never says what it "
                                    f"needs of the reader")
                for word in MACHINERY:
                    if word in low:
                        problems.append(f"{where}: the tooltip talks about "
                                        f"machinery ({word.strip()!r})")

            print(f"      every figure: page, poster, alt text, invitation, "
                  f"tooltip — checked")

            # ---- and then the thing itself ---------------------------------
            links.first.click()
            tab.wait_for_timeout(9000)
            frames = tab.locator("figure iframe")
            drew = 0
            if frames.count():
                try:
                    drew = tab.frame_locator("figure iframe").first.locator(
                        ".js-plotly-plot").count()
                except Exception:                        # noqa: BLE001
                    drew = -1
            note = tab.locator("p.after").count()
            stayed = tab.url.endswith("index.html")
            print(f"      a plain press: frames {frames.count()}, drawings "
                  f"inside {drew}, the 'it is live' line {note}, "
                  f"still on the page {stayed}")
            if not frames.count():
                problems.append(f"{name}: pressing a picture did not bring the "
                                f"viewer in")
            if drew < 1:
                problems.append(f"{name}: the frame arrived with nothing drawn "
                                f"in it")
            if not note:
                problems.append(f"{name}: nothing tells the reader it is now "
                                f"live")
            if not stayed:
                problems.append(f"{name}: pressing it navigated away instead "
                                f"of coming alive in place")

            # ---- and the link must still be a link -------------------------
            tab.goto(INDEX.resolve().as_uri())
            tab.wait_for_timeout(600)
            modifier = "Meta" if name == "webkit" else "Control"
            tab.locator("figure a[href$='.html']").first.click(
                modifiers=[modifier])
            tab.wait_for_timeout(1200)
            swapped = tab.locator("figure iframe").count()
            print(f"      with {modifier} held: frames {swapped} "
                  f"(0 is right — the browser's job)")
            if swapped:
                problems.append(f"{name}: a {modifier}-click was swallowed, so "
                                f"'open in a new tab' no longer works")
            tab.close()
        for browser in engines.values():
            browser.close()

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: every frame explains itself before it is pressed, comes "
          "alive when it is,\n  and still opens in a tab when asked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
