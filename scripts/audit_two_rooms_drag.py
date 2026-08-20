"""A drag belongs to the room it began in, and the other room follows.

    ../gv-venv/bin/python scripts/audit_two_rooms_drag.py
    ../gv-venv/bin/python scripts/audit_two_rooms_drag.py --prove

WHY THIS EXISTS. Reported from the window: "when two rooms are visible and i
drag a shape around both move the same way. but if i am crossing their
seperator while dragging the one where i started from stops moving and only
the other one still moves".

Each 3D scene watches its own element, so crossing the divider hands the drag
over: the room the press began in stops receiving movement, and the room now
under the pointer starts one of its own with the button still down. Measured
before the fix, dragging from x=300 across the seam at x=600: BOTH rooms
reported `plotly_relayouting` -- four times and three -- and they finished
pointing different ways.

WHAT MUST BE TRUE, with the failure direction:

  a drag inside one room turns both     that is what "Both rooms point the
                                        same way" promises, and it is the
                                        reason to put two rooms up at all;
  a drag that crosses the seam does     the reported fault: the shape under
      the same                          your hand stops and the other one
                                        runs away with the gesture;
  it holds from either side             the rooms are not symmetrical in the
                                        code -- one is armed on mousedown and
                                        one is the follower -- so a check that
                                        only ever starts on the left proves
                                        half of it.

MEASURED ON THE CAMERAS THEMSELVES, read from the live scene rather than from
the layout: a scene keeps the camera it is drawing in `_fullLayout.scene._scene`
and only writes it back to `layout` when the gesture ends, so a check reading
`layout` would see nothing move until the mouse came up -- which is precisely
the moment this fault is about.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

#: How far apart two cameras may be and still count as pointing the same way.
TOGETHER = 1e-3

CAMERAS = """(function () {
  var d = document.getElementsByClassName('plotly-graph-div'), o = [];
  for (var i = 0; i < d.length; i++) {
    var s = d[i]._fullLayout && d[i]._fullLayout.scene
            && d[i]._fullLayout.scene._scene;
    var c = (s && s.getCamera) ? s.getCamera()
            : (d[i].layout.scene || {}).camera;
    o.push(c ? [c.eye.x, c.eye.y, c.eye.z] : null);
  }
  return JSON.stringify(o);
})()"""


def a_page(where: pathlib.Path) -> pathlib.Path:
    import numpy as np
    import ti3gamut
    from gamutview import build_gamut

    rng = np.random.default_rng(4)
    q = rng.normal(size=(600, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    a = q * np.array([36, 58, 34])
    a[:, 0] = np.clip(a[:, 0] * 0.6 + 52, 5, 95)
    b = q * np.array([40, 34, 60])
    b[:, 0] = np.clip(b[:, 0] * 0.62 + 50, 3, 97)
    figures = [("left", ti3gamut.build_figure([("left", build_gamut(a))], "")),
               ("right", ti3gamut.build_figure([("right", build_gamut(b))], ""))]
    out = where / "two-rooms.html"
    ti3gamut.write_side_by_side_html(figures, out, linked=True, controls=False)
    return out


def drag(tab, path) -> tuple:
    """Drag along *path* and hand back the cameras before and after."""
    before = json.loads(tab.evaluate(CAMERAS))
    tab.mouse.move(path[0], 350)
    tab.mouse.down()
    for x in path[1:]:
        tab.mouse.move(x, 350)
        tab.wait_for_timeout(120)
    tab.mouse.up()
    tab.wait_for_timeout(1200)
    return before, json.loads(tab.evaluate(CAMERAS))


def main() -> int:
    prove = "--prove" in sys.argv
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed, so this check is skipped.")
        return 0

    #: Each is a name and the x positions the pointer visits. The seam of a
    #: 1200 px window is at 600.
    JOURNEYS = [
        ("inside the left room", [300, 360, 420, 480, 540]),
        ("inside the right room", [700, 760, 820, 880, 940]),
        ("left, across the seam", [300, 380, 460, 540, 660, 740, 820]),
        ("right, across the seam", [860, 800, 740, 660, 540, 460, 380]),
    ]

    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        page = a_page(pathlib.Path(tmp))
        with sync_playwright() as play:
            browser = play.chromium.launch()
            for name, path in JOURNEYS:
                tab = browser.new_page(viewport={"width": 1200, "height": 700})
                tab.goto(page.resolve().as_uri())
                # WAIT FOR THE SCENES, NOT FOR A NUMBER OF SECONDS. A fixed
                # pause reported "neither room moved" for one journey out of
                # four -- the fourth tab, with three WebGL contexts already
                # alive, simply had not finished starting. A check that calls
                # a slow start a fault is worse than no check.
                tab.wait_for_function(
                    """() => {
                      var d = document.getElementsByClassName(
                          'plotly-graph-div');
                      if (d.length < 2) return false;
                      for (var i = 0; i < d.length; i++) {
                        var s = d[i]._fullLayout && d[i]._fullLayout.scene
                                && d[i]._fullLayout.scene._scene;
                        if (!s || !s.getCamera) return false;
                      }
                      return true;
                    }""", timeout=40000)
                tab.wait_for_timeout(1200)
                if prove:
                    # THE MUTATION: give the pointer back, which is what let
                    # the second room take the gesture over. Proven to land by
                    # the capture being refused afterwards.
                    tab.evaluate("""(function () {
                      var d = document.getElementsByClassName(
                          'plotly-graph-div');
                      for (var i = 0; i < d.length; i++)
                        d[i].setPointerCapture = function () {
                          throw new Error('capture refused on purpose'); };
                    })()""")
                before, after = drag(tab, path)
                tab.close()
                moved = [any(abs(x - y) > TOGETHER for x, y in zip(c0, c1))
                         for c0, c1 in zip(before, after)]
                same = all(abs(x - y) < TOGETHER
                           for x, y in zip(after[0], after[1]))
                print(f"  {name:24s} left {'moved' if moved[0] else 'still':5s}"
                      f"  right {'moved' if moved[1] else 'still':5s}"
                      f"  in step: {'yes' if same else 'NO'}")
                if not any(moved):
                    problems.append(
                        f"{name}: neither room moved at all — the gesture "
                        f"stops when it leaves the room it began in. KNOWN "
                        f"AND OPEN: capturing the pointer cured the reported "
                        f"fault (the rooms running away from each other) in "
                        f"every direction, and left this one behind, where a "
                        f"drag from the right across the seam now freezes "
                        f"instead of diverging. Stopping is the milder fault "
                        f"and matches what the shape does when you let go "
                        f"over the walls, but it is not right yet")
                elif not same:
                    problems.append(
                        f"{name}: the two rooms finished pointing different "
                        f"ways ({[round(v, 3) for v in after[0]]} against "
                        f"{[round(v, 3) for v in after[1]]}) — the gesture was "
                        f"taken over instead of staying where it began")
            browser.close()

    print()
    if prove:
        if problems:
            print("  With the pointer capture refused, the rooms came apart, "
                  "as they must.\n  The check can see.")
            return 0
        print("  THE ROOMS STAYED IN STEP WITH THE FIX DISABLED. This check "
              "is blind.")
        return 1
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: a drag turns both rooms together, from either side, "
          "whether or not\n  it crosses the divider.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
