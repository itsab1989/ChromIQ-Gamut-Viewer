"""Does the shape actually carry on turning when the reader lets go?

    python scripts/check_momentum.py [path/to/page.html]

WHY THIS IS A SCRIPT AND NOT A UNIT TEST. Momentum is thirty lines of
JavaScript whose whole job is to react to a real pointer over a real drawing
library in a real browser, and every part of it that could go wrong goes wrong
outside Python: the drag has to reach the library, the library has to move its
internal camera, this page has to read that camera while it moves, and the
throw has to survive a `mouseup` that arrives on the window rather than on the
picture. A Python test can prove the settings reach the page. Only a browser
can prove the shape moves.

It matters that this is measured rather than reasoned about, because the first
design was wrong twice, and both times plausibly:

  * reading `gd.layout.scene.camera` inside the drag gives a STALE camera --
    measured at 0.000 of movement across a 180px drag. The live one is inside
    the built scene, which is what `liveCam()` reaches for.
  * the page only intercepts touches when there are TWO of them, so a
    one-finger drag -- the gesture this is for -- is handled entirely by the
    drawing library and never reaches any handler here. Sampling the camera
    rather than the pointer is what makes that not matter.

WHAT IT PROVES, in both engines:

  1. WITH MOMENTUM ON, the shape is still turning after the button comes up,
     and has turned further a moment later.
  2. IT STOPS ON ITS OWN, inside about a second and a half.
  3. WITH MOMENTUM OFF, the shape stops dead -- the behaviour of every page
     saved before this existed, which is what was promised.
  4. A NEW PRESS STOPS IT, because grabbing a moving thing to stop it is what
     anybody tries first.
  5. A SLOW DRAG THAT STOPS BEFORE LETTING GO throws nothing. Parking the
     shape has to park it.

Needs Playwright and its two browsers:

    pip install playwright && python -m playwright install webkit chromium
"""
from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

#: How far the shape must still turn after release for a throw to count, in
#: degrees. Below this it is indistinguishable from the shape not moving.
CARRIES_AT_LEAST = 2.0

#: And how long it may still be moving. The half-life is 0.22s, so from the
#: fastest throw allowed this is comfortably over.
STOPS_WITHIN_MS = 1600

#: A drag that stops dead must not drift by more than this, in degrees. It is
#: not zero because the library itself settles by a hair.
STILL_MEANS = 0.35

ANGLE = """(function(){
  var gd = document.querySelector('.js-plotly-plot');
  var s = gd && gd._fullLayout && gd._fullLayout.scene
          && gd._fullLayout.scene._scene;
  var cam = (s && s.getCamera) ? s.getCamera()
            : (gd.layout && gd.layout.scene && gd.layout.scene.camera);
  if (!cam || !cam.eye) return "null";
  var c = cam.center || {x:0,y:0,z:0};
  var x = cam.eye.x-c.x, y = cam.eye.y-c.y, z = cam.eye.z-c.z;
  var r = Math.sqrt(x*x+y*y);
  return JSON.stringify({az: Math.atan2(y,x)*180/Math.PI,
                         el: Math.atan2(z,r)*180/Math.PI});})();"""


def angle(tab):
    got = json.loads(tab.evaluate(ANGLE))
    return None if got is None else (got["az"], got["el"])


def apart(a, b):
    """Degrees between two readings, taking the short way round."""
    if a is None or b is None:
        return 0.0
    d = (b[0] - a[0] + 180) % 360 - 180
    return (d * d + (b[1] - a[1]) ** 2) ** 0.5


def throw(tab, *, steps=14, span=260, pause=8, stop_first=False):
    """Drag across the picture and let go, the way a hand does.

    STOPPING BEFORE LETTING GO is a real gesture and a separate case: a finger
    that comes to rest and then lifts has parked the shape, and reading its
    speed from the whole drag rather than the last moment of it would throw
    something the user plainly did not throw.
    """
    box = tab.locator(".js-plotly-plot").first.bounding_box()
    x0, y = box["x"] + box["width"] / 2 - span / 2, box["y"] + box["height"] / 2
    tab.mouse.move(x0, y)
    tab.mouse.down()
    for i in range(1, steps + 1):
        tab.mouse.move(x0 + span * i / steps, y)
        tab.wait_for_timeout(pause)
    if stop_first:
        for _ in range(6):                 # held still, in the same place
            tab.mouse.move(x0 + span, y)
            tab.wait_for_timeout(30)
    tab.mouse.up()


def look(tab, page, on):
    """Open the page with momentum on or off, and settle it."""
    tab.goto(page.as_uri())
    tab.wait_for_timeout(6000)
    tab.evaluate("window.cqSpin.set({on:false, glide:%s});"
                 % ("true" if on else "false"))
    tab.wait_for_timeout(400)


def main() -> int:
    page = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if page is None:
        page = HERE.parent / "docs" / "pages" / "14-a-paper-against-adobe-rgb.html"
    if not page.exists():
        print(f"no page at {page} -- run make_sample_pages.py first")
        return 1
    page = page.resolve()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed, so this check is skipped.")
        return 0

    faults: list[str] = []
    print(f"  {page.name}\n")
    with sync_playwright() as play:
        try:
            engines = {n: getattr(play, n).launch()
                       for n in ("webkit", "chromium")}
        except Exception as why:                        # noqa: BLE001
            print(f"  no browser, so this check is skipped: {why}")
            return 0

        for name, browser in engines.items():
            tab = browser.new_page(viewport={"width": 1200, "height": 900})

            # 1 + 2: it carries on, and then it stops.
            look(tab, page, on=True)
            throw(tab)
            at_release = angle(tab)
            tab.wait_for_timeout(220)
            carried = apart(at_release, angle(tab))
            tab.wait_for_timeout(STOPS_WITHIN_MS)
            settled = angle(tab)
            tab.wait_for_timeout(400)
            after = apart(settled, angle(tab))
            print(f"  {name:9s} momentum ON : carried {carried:6.2f}° after "
                  f"letting go, {after:5.2f}° once it had stopped")
            if carried < CARRIES_AT_LEAST:
                faults.append(f"{name}: nothing carried on after the drag "
                              f"({carried:.2f}°, wanted {CARRIES_AT_LEAST}°)")
            if after > STILL_MEANS:
                faults.append(f"{name}: still moving {after:.2f}° after "
                              f"{STOPS_WITHIN_MS}ms -- it never stops")

            # 3: switched off, it stops dead, as it always did.
            #
            # THE BASELINE IS TAKEN A MOMENT AFTER THE BUTTON COMES UP, and
            # that is measurement rather than leniency. The drawing library
            # finishes the last move of the drag after the release: measured
            # in WebKit, the shape turns 2.77 degrees once and then never
            # again -- flat across every window from 60ms to 1s. A throw does
            # the opposite and keeps adding (19.9, 43.7, 61.3, 78.8 ...), so
            # the two are told apart by whether the movement CONTINUES, not by
            # whether there is any. Reading the baseline before that last
            # frame lands would report the library's own catching-up as a
            # throw, and did.
            look(tab, page, on=False)
            throw(tab)
            tab.wait_for_timeout(200)
            stopped = angle(tab)
            tab.wait_for_timeout(600)
            drift = apart(stopped, angle(tab))
            print(f"  {name:9s} momentum OFF: drifted {drift:5.2f}°")
            if drift > STILL_MEANS:
                faults.append(f"{name}: switched off, it still drifted "
                              f"{drift:.2f}° -- that is a behaviour change "
                              f"for every page saved without it")

            # 4: pressing on it stops it.
            look(tab, page, on=True)
            throw(tab)
            tab.wait_for_timeout(90)
            box = tab.locator(".js-plotly-plot").first.bounding_box()
            tab.mouse.move(box["x"] + box["width"] / 2,
                           box["y"] + box["height"] / 2)
            tab.mouse.down()
            grabbed = angle(tab)
            tab.wait_for_timeout(500)
            crept = apart(grabbed, angle(tab))
            tab.mouse.up()
            print(f"  {name:9s} grabbed mid-throw: crept {crept:5.2f}°")
            if crept > STILL_MEANS:
                faults.append(f"{name}: holding it still let it turn "
                              f"{crept:.2f}° -- it cannot be caught")

            # 5: parking it parks it.
            #
            # THE SAME BASELINE AS SCENARIO 3, AND FOR THE SAME REASON. This
            # read its baseline the instant the button came up, which is
            # before the drawing library has finished the drag, so it counted
            # the library's own catching-up as a throw -- exactly the trap
            # written up above, left in place here because the two scenarios
            # were fixed a fortnight apart.
            #
            # It reported "webkit: a drag that stopped before the button came
            # up still threw 42.64 degrees", and the page was innocent. Proved
            # by instrumenting letGo() inside a copy of the page: on this
            # gesture it refuses, and says why -- "still: turn 0.000" -- in
            # both engines. Proved again from the other side by running the
            # identical gesture with momentum switched OFF, where our throw
            # cannot run at all: WebKit still moved 42.66 degrees. Something
            # that happens with the feature turned off is not the feature.
            #
            # What it is: the library eases the camera towards the drag and
            # WebKit's is still catching up at the moment of release. A trace
            # across the whole gesture puts every degree of it inside the
            # first 100 ms -- 15.9 round and 41.8 up -- and then 0.000 in
            # every 100 ms window for the next second. A throw does the
            # opposite and keeps adding.
            look(tab, page, on=True)
            throw(tab, stop_first=True)
            tab.wait_for_timeout(200)
            parked = angle(tab)
            tab.wait_for_timeout(600)
            slipped = apart(parked, angle(tab))
            print(f"  {name:9s} stopped before letting go: slipped "
                  f"{slipped:5.2f}°")
            if slipped > STILL_MEANS:
                faults.append(f"{name}: a drag that stopped before the button "
                              f"came up still threw {slipped:.2f}°")
            tab.close()
            print()
        for browser in engines.values():
            browser.close()

    if faults:
        print(f"{len(faults)} fault(s):")
        for line in faults:
            print(f"  - {line}")
        return 1
    print("Momentum carries, stops, can be caught, and stays off when it is "
          "off -- in both engines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
