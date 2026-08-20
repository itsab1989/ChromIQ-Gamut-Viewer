"""A saved page laid out in two engines, at ten window sizes.

    python scripts/check_layout.py [path/to/page.html]

WHY THIS EXISTS, AND WHY IT IS SEPARATE FROM THE AUDIT. `audit.py` drives the
window and the pages through Qt's web view, which is Chromium. Every picture
this project has ever rendered has been Chromium, and two faults reported from
an iPad turned out to be invisible there:

  * the picture came out **450px tall on a 1366px screen** in WebKit, because
    the drawing library's `height:100%` has no definite parent to take a
    percentage of. Chromium resolves it anyway. Two thirds of the screen was
    black.
  * a control sat about **150px from the name it belongs to** once the panel
    had room for four columns, and a shape's controls wrapped onto a second
    line beside a different shape's name.

Neither is a scripting fault or a colour fault; both are layout, and layout is
where two engines are allowed to disagree. So this checks the shape of the
page rather than what is drawn in it, in Chromium AND in WebKit, at sizes from
a phone held upright to a large desktop.

WHAT IT ASSERTS, and each number is one that was measured rather than chosen:

  * THE PICTURE TAKES BETWEEN 55% AND 85% OF THE FIRST SCREEN. Below that a
    reader is looking at a page of black; above it there is nothing under the
    picture to say the page continues, which is the whole reason the floor
    exists.
  * NO CONTROL SITS MORE THAN 60px FROM ITS NAME. They run 12-14px now.
  * NO ROW WRAPS its controls away from their name at 844px wide or more. A
    phone held upright genuinely cannot fit a name and four buttons on one
    line, so below that it may.
  * THE PAGE NEVER SCROLLS SIDEWAYS, at any size.
  * NO TWO LABELS ROUND THE PICTURE ARE PRINTED ON TOP OF EACH OTHER -- the
    title, the key, the axis names and the axis numbers. This one was added
    after a key printed across a title shipped in v2.17.0 and was reported
    from a phone: every rule above measures the page's FRAME, and none of
    them could see inside the drawing, so a collision there was invisible to
    the whole check. Measured in both engines it was wrong at 14 of 20 window
    sizes, a large desktop among them.

Needs Playwright and its two browsers:

    pip install playwright && python -m playwright install webkit chromium

It skips, rather than fails, when they are not installed -- this is a check to
run before a release, not a reason nobody can run the tests.
"""
from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT = HERE.parent / "docs" / "pages" / "14-a-paper-against-adobe-rgb.html"

#: Window sizes worth checking, and why each is here.
SIZES = [
    ("iPhone portrait",      390, 844),
    ("iPhone landscape",     844, 390),   # the shortest real screen
    ("iPad portrait",       1024, 1366),
    ("iPad landscape",      1366, 1024),  # where the controls scattered
    ("iPad Mini landscape", 1133, 744),
    ("laptop",              1440, 900),
    ("large desktop",       2560, 1440),
    ("short window",        1200, 500),
    ("very short",          1000, 360),   # a browser dragged to nothing
    ("narrow",               320, 700),   # the narrowest phone still sold
]

#: The picture's share of the first screen, as a fraction.
LEAST_PICTURE, MOST_PICTURE = 0.55, 0.85

#: How far a control may sit from the name it belongs to, in pixels.
FURTHEST = 60

#: Above this width, a control that has wrapped away from its name is a fault
#: rather than a phone.
WRAPS_ARE_A_FAULT_ABOVE = 800

#: The labels the drawing library puts round the outside of a picture, each
#: with the name this check calls it by. Only the ones drawn in the MARGINS
#: are listed: everything inside the plot area (a point's hover text, a band's
#: own caption) is allowed to sit over whatever it is describing, and reading
#: those as faults would drown the real ones.
LABELS = {".gtitle": "the title",
          ".legend .legendtext": "a key entry",
          ".xtitle": "the bottom axis name",
          ".ytitle": "the side axis name",
          ".xtick text": "a bottom axis number",
          ".ytick text": "a side axis number",
          ".colorbar .cbtitle": "the colour key's name"}

#: Two labels closer than this are touching by accident rather than by design.
#: Zero would fire on the one-pixel rounding two engines disagree about.
TOUCHING = 8.0

MEASURE = """(function(){
  var d=document.querySelector('.js-plotly-plot');
  // TWO ROOMS ONE ABOVE THE OTHER ARE ONE PICTURE, in the only sense this
  // check cares about: it asks whether the drawing holds enough of the first
  // screen to be worth looking at, and a page deliberately arranged as two
  // stacked rooms gives each of them half. Measuring only the first would
  // report every such page as half a picture — the check's own assumption,
  // not the page's fault.
  var all=document.querySelectorAll('.js-plotly-plot');
  var stacked=false, together=0;
  if(all.length===2){
    var a=all[0].getBoundingClientRect(), b=all[1].getBoundingClientRect();
    stacked = Math.abs(a.left-b.left)<2 && b.top>=a.bottom-2;
    if(stacked) together=Math.round(a.height+b.height);
  }
  var rows=document.querySelectorAll('.cq-spin-panel .cq-row'), pairs=[];
  for (var i=0;i<rows.length;i++){
    var r=rows[i], name=r.querySelector('span'), ctl=r.querySelector('.cq-ctl');
    if(!name||!ctl) continue;
    var a=name.getBoundingClientRect(), b=ctl.getBoundingClientRect();
    if(b.width===0||a.width===0) continue;
    pairs.push({label:(name.textContent||'').trim().slice(0,28),
                gap:Math.round(b.left-a.right),
                wrapped:Math.abs(a.top-b.top)>12});
  }
  // EVERY LABEL ROUND THE PICTURE, so two of them landing on top of each
  // other is a fault this check can see. It could not before: it measured
  // the page's frame and never looked inside the drawing, which is how a
  // key printed over a title reached a release.
  var LABELS = __LABELS__, marks=[];
  Object.keys(LABELS).forEach(function(sel){
    document.querySelectorAll(sel).forEach(function(n){
      var r=n.getBoundingClientRect();
      if(r.width<1||r.height<1) return;
      marks.push({kind:LABELS[sel], text:(n.textContent||'').trim().slice(0,34),
                  x:r.x, y:r.y, w:r.width, h:r.height});
    });
  });
  var over=[];
  for (var i=0;i<marks.length;i++) for (var j=i+1;j<marks.length;j++){
    var a=marks[i], b=marks[j];
    var dx=Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x);
    var dy=Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y);
    if(dx>0&&dy>0&&dx*dy>__TOUCHING__)
      over.push({a:a.kind, b:b.kind, at:Math.round(dx*dy),
                 says:a.text, and:b.text});
  }
  return JSON.stringify({
    picture: stacked?together:(d?Math.round(d.getBoundingClientRect().height):0),
    stacked: stacked,
    view: window.innerHeight, rows: pairs, over: over, labels: marks.length,
    sideways: document.documentElement.scrollWidth>window.innerWidth+1});})();"""

MEASURE = (MEASURE.replace("__LABELS__", json.dumps(LABELS))
                  .replace("__TOUCHING__", repr(TOUCHING)))

OPEN = """(function(){var b=document.querySelector('[data-cq="more"]');
  if(b) b.click();})();"""


def main() -> int:
    page = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not page.exists():
        print(f"no page at {page} -- run make_sample_pages.py first")
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed, so this check is skipped.\n"
              "  pip install playwright && python -m playwright install "
              "webkit chromium")
        return 0

    faults: list[str] = []
    print(f"  {page.name}\n")
    print(f"  {'size':22s} {'window':>11s}  {'engine':9s} {'picture':>12s} "
          f"{'widest gap':>11s}  verdict")
    print("  " + "-" * 78)
    with sync_playwright() as play:
        try:
            engines = {n: getattr(play, n).launch()
                       for n in ("webkit", "chromium")}
        except Exception as why:                       # noqa: BLE001
            print(f"  could not start a browser, so this check is skipped: {why}")
            return 0
        for label, wide, tall in SIZES:
            for name, browser in engines.items():
                tab = browser.new_page(viewport={"width": wide, "height": tall})
                tab.goto(page.resolve().as_uri())
                tab.wait_for_timeout(6000)
                tab.evaluate(OPEN)
                tab.wait_for_timeout(1200)
                got = json.loads(tab.evaluate(MEASURE))
                tab.close()

                share = got["picture"] / max(got["view"], 1)
                gaps = [r["gap"] for r in got["rows"] if not r["wrapped"]]
                widest = max(gaps) if gaps else 0
                said = []
                if not LEAST_PICTURE <= share <= MOST_PICTURE:
                    said.append(f"picture is {100 * share:.0f}% of the screen")
                if widest > FURTHEST:
                    said.append(f"a control sits {widest}px from its name")
                if wide >= WRAPS_ARE_A_FAULT_ABOVE:
                    for row in got["rows"]:
                        if row["wrapped"]:
                            said.append(f"{row['label']!r} wrapped away from "
                                        "its controls")
                if got["sideways"]:
                    said.append("the page scrolls sideways")
                for hit in got["over"]:
                    said.append(f"{hit['a']} is printed over {hit['b']} "
                                f"({hit['at']}px²): {hit['says']!r} "
                                f"across {hit['and']!r}")
                verdict = "ok" if not said else "; ".join(said)
                for one in said:
                    faults.append(f"{label} ({wide}x{tall}) in {name}: {one}")
                print(f"  {label:22s} {wide:5d}x{tall:<5d} {name:9s} "
                      f"{got['picture']:6d}px {100 * share:3.0f}% "
                      f"{widest:8d}px  {verdict}")
        for browser in engines.values():
            browser.close()

    print()
    if faults:
        print(f"{len(faults)} layout fault(s):")
        for line in faults:
            print(f"  - {line}")
        return 1
    print(f"Every size holds its shape in both engines "
          f"({len(SIZES)} sizes x 2 engines).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
