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
        # ONE POSTER FOR EACH KIND OF READER. The pages follow whoever opens
        # them now, but a poster is a photograph and cannot: a dark still on a
        # light screen is exactly the black rectangle this was all about. So
        # each page is photographed twice, and the card picks with a media
        # query -- the still matches the reader before anything is pressed,
        # and the live page matches them after.
        for wants in ("light", "dark"):
            page.emulate_media(color_scheme=wants)
            shoot(page, wants, wrong)
        browser.close()
    return finish(wrong)


def shoot(page, wants, wrong):
    """Every wanted page, photographed as this kind of reader sees it."""
    suffix = "" if wants == "light" else "-dark"
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
            wrong.append(f"{name}: the scene never drew — this photograph "
                         f"would be of a failure screen")
            continue
        page.wait_for_timeout(1500)
        target = SHOTS / (source.stem + suffix + ".png")
        # CUT WHERE THE PAGE HAS A JOIN, not at whatever pixel the window
        # happens to end at. A plain viewport screenshot is 720 px of whatever
        # is there, and what was there was the middle of a sentence: reported
        # from the live site, "the first example has the text in its frame cut
        # off at the bottom".
        #
        # Asked of the page itself, so it works for a 3D scene, a graph and a
        # flat cut alike: which elements does the bottom edge cut THROUGH, and
        # where does the highest of them begin? Cut there.
        cut = page.evaluate("""(function () {
          var edge = 720, highest = edge;
          var all = document.body.querySelectorAll('*');
          for (var i = 0; i < all.length; i++) {
            var el = all[i];
            if (!el.textContent || !el.textContent.trim()) continue;
            if (el.children.length) continue;      // leaves carry the words
            var b = el.getBoundingClientRect();
            if (b.height <= 0 || b.width <= 0) continue;
            if (b.top < edge && b.bottom > edge && b.top < highest)
              highest = b.top;
          }
          return Math.floor(highest === edge ? edge : highest - 6);
        })()""")
        if cut and 240 < cut <= 720:
            page.screenshot(path=str(target),
                            clip={"x": 0, "y": 0, "width": 860, "height": cut})
        else:
            print(f"  {source.stem}: nothing to cut under (measured {cut}) "
                  f"— full window")
            page.screenshot(path=str(target))
        print(f"  {target.name:48s} {target.stat().st_size / 1024:6.0f} kB")


def finish(wrong) -> int:
    # TWO DIFFERENT SCENES CANNOT TAKE THE SAME PICTURE. Byte-identical
    # photographs mean every one of them is some shared state -- a fallback, a
    # loading screen -- and not the scene its card promises.
    #
    # COMPARED WITHIN ONE APPEARANCE, and that distinction was learnt here.
    # Comparing every shot against every other made the check fail the moment
    # the second pass arrived, because a page that cannot change colour
    # photographs the same twice -- which is a fact about the page, not a
    # broken photograph. Two rules, two questions.
    import hashlib
    for wants in ("light", "dark"):
        suffix = "" if wants == "light" else "-dark"
        seen: dict[str, str] = {}
        for name in WANTED:
            shot = SHOTS / (pathlib.Path(name).stem + suffix + ".png")
            if not shot.is_file():
                continue
            digest = hashlib.md5(shot.read_bytes()).hexdigest()
            if digest in seen:
                wrong.append(f"{shot.name} is byte-identical to "
                             f"{seen[digest]} — two scenes, one picture")
            seen[digest] = shot.name

    # AND WHICH PAGES LOOK THE SAME TO EITHER READER, said plainly rather than
    # failed. A page with no colouring machinery -- the graphs -- cannot
    # differ, and a shot cropped to the picture alone may not show enough
    # background to differ either. Worth knowing, not worth stopping for.
    same = []
    for name in WANTED:
        stem = pathlib.Path(name).stem
        light, dark = SHOTS / f"{stem}.png", SHOTS / f"{stem}-dark.png"
        if (light.is_file() and dark.is_file()
                and hashlib.md5(light.read_bytes()).hexdigest()
                == hashlib.md5(dark.read_bytes()).hexdigest()):
            same.append(stem)
    if same:
        print(f"\n  the same to a light and a dark reader ({len(same)}): "
              + ", ".join(same))

    if wrong:
        for line in wrong:
            print("  " + line)
        return 1
    print(f"\n{len(WANTED) * 2} photographs in {SHOTS} "
          f"({len(WANTED)} pages x light and dark)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
