"""A saved page set to "follow you" wears the colours of whoever opens it.

    ../gv-venv/bin/python scripts/audit_follows_the_reader.py

WHY THIS EXISTS. A saved page opens in the colouring it was saved in and could
do nothing else, so a page written from a dark window arrives as a black
rectangle in the middle of somebody's light document. Reported from the
published showcase: "the viewer frames stand out because they are black by
default although we offer multiple colorschemes."

WHAT MUST BE TRUE, and every answer is known before the check runs:

  saved as "follow you", opened by a reader whose machine is DARK
      -> the page is the dark paper, #111111
  the same file, opened by a reader whose machine is LIGHT
      -> the page is the light paper, #efebe6
  the same file, the reader switching from light to dark WITH IT OPEN
      -> it changes over without a reload
  saved as "dark", opened by a light reader
      -> still dark. The old behaviour is not what changed, and a page
         somebody deliberately pinned must stay pinned.
  the button's own words
      -> name the new colouring and say what it needs, or nobody finds it

The failure directions are opposite and both matter: a page that ignores the
reader is the fault being fixed, and a page that ignores the person who SAVED
it has broken every page saved before today.

Run in real Chromium and real WebKit, because prefers-color-scheme is the
reader's browser answering, not ours.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

DARK_PAPER = "#111111"
LIGHT_PAPER = "#efebe6"


def rgb(css: str) -> str:
    """'rgb(17, 17, 17)' -> '#111111', so the two can be compared."""
    css = (css or "").strip()
    if css.startswith("#"):
        return css.lower()
    if css.startswith("rgb"):
        parts = [int(float(p)) for p in
                 css[css.index("(") + 1:css.index(")")].split(",")[:3]]
        return "#%02x%02x%02x" % tuple(parts)
    return css


def a_page(where: pathlib.Path, appearance: str) -> pathlib.Path:
    """One real saved page, written by the window's own Save.

    Driven rather than called: the scheme list a page can move through is
    baked into it when it is written, so a page from docs/ predates this
    colouring and could never reach it. Only a page written by today's code
    carries it.
    """
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.argv = ["audit_follows_the_reader"]
    import prefs

    prefs.use_a_scratch_store()
    from PyQt6.QtWidgets import QApplication
    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
    win = gamut_app.GamutApp([])
    win.resize(1300, 900)
    win.show()

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)

    pump(2.5)
    win._set_appearance(appearance)
    pump(1.5)
    profiles = sorted(pathlib.Path(tempfile.gettempdir())
                      .glob("showme-*/printer-*.icc"))
    # THE RUN'S PANEL WRITES THE PAGE. The page writer lives there, not on the
    # window, and this is the same route audit_routes drives.
    panel = win._timeline
    panel.add(list(profiles[:3]))
    pump(12)
    show = panel._picture_of
    for i in range(show.count()):
        if show.itemText(i).startswith("Where it moved"):
            show.setCurrentIndex(i)
            show.activated.emit(i)
            break
    pump(8)
    out = where / f"saved-{appearance}.html"
    panel.write_page(out, carry_viewer=True, controls=True, numbers=True,
                     offer={"appearance": True, "camera": True})
    pump(1)
    win.close()
    pump(0.4)
    return out


def press_round_to_follow(tab, tries: int = 8) -> str:
    """Press the appearance button until the page is on "follow you".

    That is the only way to reach it today: the colouring a page OPENS in is
    the one the window was wearing when it was saved, and nothing in the save
    dialog offers this one yet. Recorded as a gap rather than papered over --
    it is what the published showcase needs.
    """
    # THE APPEARANCE BUTTON LIVES BEHIND "more…", which is shut when the page
    # opens. Pressing a button nobody can see would prove nothing about what a
    # reader can reach, so this opens the panel the way a reader does.
    button = tab.locator('button[data-cq="appearance"]').first
    if not button.count():
        return "(no appearance button on this page)"
    if not button.is_visible():
        opener = tab.locator('button[data-cq="more"]').first
        if opener.count():
            opener.click()
            tab.wait_for_timeout(600)
    if not button.is_visible():
        return "(the appearance button is on the page but out of reach)"
    for _ in range(tries):
        label = (button.text_content() or "").strip()
        if "follow you" in label:
            return label
        button.click()
        tab.wait_for_timeout(700)
    return (button.text_content() or "").strip()


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed, so this check is skipped.\n"
              "  pip install playwright && python -m playwright install "
              "webkit chromium")
        return 0
    import ti3gamut

    problems: list[str] = []

    problems_words_later = True     # the page has to exist first

    with tempfile.TemporaryDirectory() as tmp:
        where = pathlib.Path(tmp)
        pinned = a_page(where, "dark")
        following = pinned      # the same file, pressed round
        print(f"  wrote one page, saved dark "
              f"({pinned.stat().st_size // 1024} kB)")

        # ---- THE WORDS, read off the page a reader is handed, not off the
        # source that was meant to produce it.
        written = pinned.read_text(encoding="utf-8", errors="replace")
        if "follow you" not in written:
            problems.append("the page never says \"follow you\", so nobody "
                            "discovers the colouring")
        for needed, why in (("dark if that machine is set to dark",
                             "what it does"),
                            ("nothing installed", "what it needs")):
            if needed not in written:
                problems.append(f"the tooltip does not say {why} "
                                f"({needed!r} missing from the page)")

        with sync_playwright() as play:
            try:
                engines = {n: getattr(play, n).launch()
                           for n in ("chromium", "webkit")}
            except Exception as why:                    # noqa: BLE001
                print(f"  no browser, so this check is skipped: {why}")
                return 0

            for name, browser in engines.items():
                print(f"\n  {name}")
                for wants, expected in (("dark", DARK_PAPER),
                                        ("light", LIGHT_PAPER)):
                    tab = browser.new_page(
                        viewport={"width": 1000, "height": 760})
                    tab.emulate_media(color_scheme=wants)
                    tab.goto(following.resolve().as_uri())
                    tab.wait_for_timeout(4000)
                    landed = press_round_to_follow(tab)
                    tab.wait_for_timeout(900)
                    if "follow you" not in landed:
                        problems.append(
                            f"{name}: the appearance button never reached "
                            f"\"follow you\" — it stopped at {landed!r}")
                    got = rgb(tab.evaluate(
                        "getComputedStyle(document.body).backgroundColor"))
                    ok = got == expected
                    print(f"      a {wants:5s} reader opens the following "
                          f"page → {got}  {'ok' if ok else 'WRONG'}")
                    if not ok:
                        problems.append(
                            f"{name}: a {wants} reader got {got}, wanted "
                            f"{expected}")
                    tab.close()

                # it changes over without a reload
                tab = browser.new_page(viewport={"width": 1000, "height": 760})
                tab.emulate_media(color_scheme="light")
                tab.goto(following.resolve().as_uri())
                tab.wait_for_timeout(4000)
                press_round_to_follow(tab)
                tab.wait_for_timeout(900)
                before = rgb(tab.evaluate(
                    "getComputedStyle(document.body).backgroundColor"))
                tab.emulate_media(color_scheme="dark")
                tab.wait_for_timeout(1200)
                after = rgb(tab.evaluate(
                    "getComputedStyle(document.body).backgroundColor"))
                print(f"      switching to dark with it open → {before} "
                      f"→ {after}  "
                      f"{'ok' if after == DARK_PAPER else 'DID NOT FOLLOW'}")
                if after != DARK_PAPER:
                    problems.append(
                        f"{name}: switching the machine to dark left the page "
                        f"at {after} — it followed once and then stopped")
                tab.close()

                # and a pinned page stays pinned
                tab = browser.new_page(viewport={"width": 1000, "height": 760})
                tab.emulate_media(color_scheme="light")
                tab.goto(pinned.resolve().as_uri())
                tab.wait_for_timeout(4000)
                got = rgb(tab.evaluate(
                    "getComputedStyle(document.body).backgroundColor"))
                print(f"      a light reader opens a page SAVED dark → {got}  "
                      f"{'ok' if got == DARK_PAPER else 'OVERRULED'}")
                if got != DARK_PAPER:
                    problems.append(
                        f"{name}: a page saved dark was repainted {got} for a "
                        f"light reader — every page saved before today has "
                        f"changed behaviour")
                tab.close()
            for browser in engines.values():
                browser.close()

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: it follows the reader, keeps following, and leaves a "
          "pinned page alone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
