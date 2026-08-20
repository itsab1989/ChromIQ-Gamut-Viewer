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

⚠ AND A MUTATION GOES STALE AS QUIETLY AS ANYTHING ELSE. This sabotaged
`setPointerCapture`, which WAS the fix for about a day -- 2.40.1 took it out
again, because capturing the pointer stopped both rooms turning at all. From
that commit onwards the mutation refused a call nobody made, the rooms stayed
in step exactly as they should, and `--prove` announced the check was blind:
true of a mechanism that no longer existed, and it made every Clean report
above it worth nothing. It now cuts the CAMERA RELAY -- every link this page
has ends in `Plotly.relayout(other, {"scene.camera": ...})` -- and counts what
it dropped, so a mutation that fails to bite says so instead of passing.

MEASURED IN PIXELS, AND THAT CORRECTION MATTERS MORE THAN THE RULE.

This asked `getCamera()` at first, which sounds like the truthful source and is
not: the linking script WRITES that camera, so the check read its own relay's
push as movement and called a dead picture alive. It passed a version of the
page where neither room turned at all -- a regression that shipped -- and it
passed because the number it watched was one the code under test sets.

So the picture is photographed before and after, and a room counts as turned
when tens of thousands of its pixels change. A hover label is about a thousand;
a turn is sixty thousand; there is nothing in between to argue about.

AND THE SHAPES ARE BUILT IN THE RIGHT SPACE. `build_gamut` reads its input as
XYZ unless told otherwise, and the first version of this page handed it Lab --
which put the corners at L* -71,327 and, being a different scene entirely,
behaved differently under the same drag. Two instruments disagreed about one
tree until that was found.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

#: How many changed pixels count as a room having turned. A hover label is
#: about a thousand; a turn is sixty thousand.
TURNED = 20000

#: How far two cameras may sit apart and still show the same face. Measured on
#: a linked pair: a drag inside one room leaves them 0.0002-0.0009 apart, which
#: is the relay's own rounding and invisible; the fault reported from the
#: window left them 0.19 apart, which is a different face entirely.
APART = 0.01

#: How far apart two pictures may be and still count as pointing the same way,
#: as a share of the pixels in one room.
TOGETHER = 0.02

def halves(shot: pathlib.Path):
    """The two rooms of a photograph, as arrays."""
    import numpy as np
    from PIL import Image

    im = Image.open(shot).convert("RGB")
    wide, tall = im.size
    return (np.asarray(im.crop((0, 0, wide // 2, tall)), float),
            np.asarray(im.crop((wide // 2, 0, wide, tall)), float))


def moved(before: pathlib.Path, after: pathlib.Path):
    """How many pixels of each room changed, and whether the two agree."""
    import numpy as np

    lb, rb = halves(before)
    la, ra = halves(after)
    left = int((np.abs(la - lb).max(axis=2) > 12).sum())
    right = int((np.abs(ra - rb).max(axis=2) > 12).sum())
    return left, right


def a_page(where: pathlib.Path) -> pathlib.Path:
    """Two rooms, drawn from real measurements where they are to hand.

    AN INVENTED SHAPE HAS HIDDEN A FAULT FROM A CHECK THREE TIMES TONIGHT --
    most recently a cut that opened at the wrong height, which could not be
    made to fail on a made-up ball because its lightness range was too narrow
    to tell the two numbers apart. Real papers have awkward proportions,
    dents and a full lightness range; invented ones are smooth and tame.
    """
    import numpy as np
    import ti3gamut
    from gamutview import build_gamut

    demo = HERE.parent / "demo"
    real = [(p.stem, p) for p in (demo / "Glossy-paper.ti3",
                                  demo / "Matte-paper.ti3") if p.is_file()]
    if len(real) == 2:
        figures = [(name, ti3gamut.build_figure(
            [(name, build_gamut(ti3gamut.read_measurement(path).lab,
                                input_space="lab"))], ""))
            for name, path in real]
        out = where / "two-rooms.html"
        ti3gamut.write_side_by_side_html(figures, out, linked=True,
                                         controls=False)
        return out

    rng = np.random.default_rng(4)
    q = rng.normal(size=(600, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    a = q * np.array([36, 58, 34])
    a[:, 0] = np.clip(a[:, 0] * 0.6 + 52, 5, 95)
    b = q * np.array([40, 34, 60])
    b[:, 0] = np.clip(b[:, 0] * 0.62 + 50, 3, 97)
    # BUILT IN THE RIGHT SPACE. `build_gamut` reads its input as XYZ unless
    # told; handing it Lab put this page's corners at L* -71,327 and made it a
    # different scene from the one the window draws.
    figures = [("left", ti3gamut.build_figure(
                    [("left", build_gamut(a, input_space="lab"))], "")),
               ("right", ti3gamut.build_figure(
                    [("right", build_gamut(b, input_space="lab"))], ""))]
    out = where / "two-rooms.html"
    ti3gamut.write_side_by_side_html(figures, out, linked=True, controls=False)
    return out


#: The two rooms hold different shapes, so "are they pointing the same way"
#: cannot be asked of their pixels -- only of their cameras. That is the one
#: question a camera reading answers honestly here: the relay writes it, so it
#: is useless for "did anything turn" and exact for "do the two agree".
EYES = """(function () {
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


def drag(tab, path, shots: pathlib.Path, tag: str) -> tuple:
    """Drag along *path*, photographing before and after."""
    before = shots / f"{tag}-before.png"
    after = shots / f"{tag}-after.png"
    tab.screenshot(path=str(before))
    tab.mouse.move(path[0], 350)
    tab.mouse.down()
    for x in path[1:]:
        tab.mouse.move(x, 350)
        tab.wait_for_timeout(140)
    tab.mouse.up()
    tab.wait_for_timeout(1200)
    tab.screenshot(path=str(after))
    eyes = json.loads(tab.evaluate(EYES))
    apart = (max(abs(x - y) for x, y in zip(eyes[0], eyes[1]))
             if eyes[0] and eyes[1] else float("inf"))
    together = apart < APART
    left, right = moved(before, after)
    return left, right, together, apart


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
        shots = pathlib.Path(tmp) / "shots"
        shots.mkdir()
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
                    # THE MUTATION: CUT THE RELAY, which is the thing that
                    # makes the two rooms one gesture. Every link this page
                    # has -- the live one during a drag, and the settling push
                    # when the button comes up -- ends in the same call,
                    # `Plotly.relayout(other, {"scene.camera": ...})`, so
                    # dropping exactly those patches sabotages the mechanism
                    # whatever shape it is written in.
                    #
                    # IT USED TO SABOTAGE `setPointerCapture`, AND THAT WENT
                    # STALE WITHOUT A SOUND. Pointer capture WAS the fix for
                    # about a day; 2.40.1 took it out again, because capturing
                    # the pointer stopped both rooms turning at all. From that
                    # commit onwards the mutation refused a call nobody made,
                    # the rooms stayed in step exactly as they should, and the
                    # check reported itself blind -- which it was, about a
                    # mechanism that no longer existed. A mutation has to be
                    # aimed at the code that is there now.
                    tab.evaluate("""(function () {
                      window.__cqDropped = 0;
                      var real = window.Plotly.relayout;
                      window.Plotly.relayout = function (gd, patch) {
                        if (patch && typeof patch === 'object'
                            && Object.prototype.hasOwnProperty.call(
                                patch, 'scene.camera')) {
                          window.__cqDropped++;
                          return Promise.resolve(gd);
                        }
                        return real.apply(this, arguments);
                      };
                    })()""")
                left, right, together, apart = drag(
                    tab, path, shots, f"{name.replace(' ', '-')}")
                # PROVEN TO LAND, not assumed. A mutation that silently fails
                # to apply looks exactly like a check that passes, and this
                # one did for weeks.
                if prove:
                    dropped = tab.evaluate("window.__cqDropped || 0")
                    if not dropped:
                        print(f"  {name}: THE MUTATION DID NOT LAND — not one "
                              f"camera relay was cut, so this journey tested "
                              f"nothing.")
                        tab.close()
                        return 2
                tab.close()
                turned = [left >= TURNED, right >= TURNED]
                print(f"  {name:24s} left {left:7d} px  right {right:7d} px"
                      f"   {'both turned' if all(turned) else 'NEITHER TURNED' if not any(turned) else 'ONE ONLY'}"
                      f"   {'in step' if together else 'OUT OF STEP'}"
                      f" ({apart:.4f} apart)")
                if not any(turned):
                    problems.append(
                        f"{name}: neither room turned at all — the drag did "
                        f"nothing but pop a label ({left} and {right} pixels "
                        f"changed, where a turn is tens of thousands)")
                elif not all(turned):
                    problems.append(
                        f"{name}: only one room turned ({left} against "
                        f"{right} pixels) — the other was left behind")
                elif not together:
                    problems.append(
                        f"{name}: the two rooms turned by different amounts "
                        f"({left} against {right} pixels), so they are no "
                        f"longer showing the same face")
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
