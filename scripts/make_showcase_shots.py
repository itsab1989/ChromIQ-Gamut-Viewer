"""Photographs of the showcase pages, taken from the pages themselves.

    ../gv-venv/bin/python scripts/make_showcase_shots.py

Each card on `docs/showcase/index.html` carries a picture of the page it
links to. The pictures are taken here, in Chromium via Playwright, from the
very files the card opens -- never drawn separately, so a card cannot show a
scene its page does not contain. Chromium rather than Firefox because a
headless Firefox photograph of a WebGL canvas comes out background-coloured
(measured; see audit_other_engines.py).

Each page is given until its scene is drawn -- a live WebGL context with a
sized buffer, or enough SVG for a graph -- and a beat longer for the control
strip, then photographed at 1100x760.

Exit 1 if a page is missing, its scene never drew, or two photographs come
out byte-identical -- two different scenes cannot take the same picture.
That last check exists because the first run of this produced seven
identical 152 kB photographs and a size floor called them all fine: they
were the pages' own "The 3D viewer did not arrive" fallback, pixel for
pixel, because the viewer was being fetched from a CDN and the fetch
failed. (It is also why the showcase pages carry the viewer inside them.)
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PAGES = ROOT / "docs" / "showcase" / "pages"
SHOTS = ROOT / "docs" / "showcase" / "shots"

#: page -> the moment worth photographing. The slice pages get a beat more:
#: their layout settles after the cut is drawn.
WANTED = [
    "01-two-papers-both-ways.html",
    "02-against-adobe-rgb.html",
    "04-a-chart-in-ink-amounts.html",
    "06-a-year-on-the-shelf.html",
    "07-five-batches-nothing-to-see.html",
    "08-the-batch-where-something-happened.html",
    "09-two-shells-the-same-size.html",
    "10-the-cut-at-54.html",
    "11-the-cut-at-20.html",
]

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


def main() -> int:
    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(parents=True, exist_ok=True)
    wrong = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # A NARROWER WINDOW, ON PURPOSE. The pages centre a 3D scene in
        # whatever width they get; at 1100px the shape is a small island in
        # black margins, and a card wearing that photograph advertises the
        # margins. 860px is a size people really use (the audit's tablet
        # width), and the scene fills it.
        page = browser.new_page(viewport={"width": 860, "height": 720},
                                device_scale_factor=2)
        for name in WANTED:
            source = PAGES / name
            if not source.is_file():
                wrong.append(f"{name}: page missing")
                continue
            page.goto(source.resolve().as_uri())
            waited = 0
            while waited < 20_000 and not page.evaluate(READY):
                page.wait_for_timeout(250)
                waited += 250
            # ASK THE PAGE, NOT THE FILE SIZE. A photograph of the page's own
            # failure screen is a perfectly plausible number of kilobytes.
            if not page.evaluate(READY):
                wrong.append(f"{name}: the scene never drew — this "
                             f"photograph would be of a failure screen")
                continue
            page.wait_for_timeout(1500)
            target = SHOTS / (source.stem + ".png")
            page.screenshot(path=str(target))
            print(f"  {target.name:45s} "
                  f"{target.stat().st_size / 1024:6.0f} kB")
        browser.close()

    # TWO DIFFERENT SCENES CANNOT TAKE THE SAME PICTURE. Byte-identical
    # photographs mean every one of them is some shared state -- a fallback,
    # a loading screen -- and not the scene its card promises.
    import hashlib
    seen: dict[str, str] = {}
    for shot in sorted(SHOTS.glob("*.png")):
        digest = hashlib.md5(shot.read_bytes()).hexdigest()
        if digest in seen:
            wrong.append(f"{shot.name} is byte-identical to {seen[digest]}")
        seen[digest] = shot.name

    if wrong:
        for line in wrong:
            print("  " + line)
        return 1
    print(f"\n{len(WANTED)} photographs in {SHOTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
