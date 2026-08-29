"""The depth fix is a thing that KEEPS HAPPENING, and nothing tested that.

⚠ WHY THIS FILE EXISTS. A hostile review of `_DEPTH_JS` found two mutations
that the whole suite could not see, and both are the same shape: every check
we had asks what the script IS, and neither of these changes that.

  * `fit(gl)` can be deleted from inside the render wrapper and all 1,117
    tests stay green. `arm()` calls `fit` once itself, so the page still
    draws with fitted planes and `test_a_saved_page_really_arms_the_depth_fix`
    still finds them fitted — they simply never move again. Five notches of
    the page's own wheel zoom later, a corner of the drawn box is in front of
    the frozen near plane and the picture is being cut, silently.

    ⚠ AND "CUT" NAMES THE MILDER HALF. Photographed on a real page in real
    chromium, demo Glossy against Matte at opacity 1.0, the mutant against
    the shipped code at eight notches:
        IN  — the surface is sliced open down its right-hand edge, a layered
              shelf and a dark interior band where the shipped page draws one
              smooth curve. 30,052 pixels different.
        OUT — THE PAGE IS BLACK. The frozen far plane, 4.45, is nearer than
              the whole scene at |eye| 5.57, so the gamut, the axis box, the
              gridlines and every tick number are gone; the caption, the
              legend and one stranded hover label are all that is left. The
              shipped page at the same camera draws a small, complete,
              fully-labelled picture.
    The queue and this file both first said only "the near plane cuts the
    front off". Nobody had looked at the OTHER direction, where the loss is
    total. Pictures in `scratch/hostile-0829/`.
  * `}, 250)` can become `}, 10)` or `}, 20000)` with the file green. Both
    node harnesses in `test_the_depth_planes_cannot_clip` stub `setInterval`
    as `(fn) => { timer = fn; }` and throw the delay away, so they drive the
    sweep by hand and nothing anywhere reads the number. At 10 ms the sweep's
    whole life is 4.8 seconds, which re-creates exactly the bug `e1d2650`
    fixed — a page saved without the viewer inside it fetches 4.8 MB over the
    network, and on any connection slower than that the fix never happens.

THE TWO PROPERTIES, and neither is a threshold dressed as a law:

  1. THE PLANES FOLLOW THE CAMERA. Fitting is not a thing done once to a
     page; it is done to a FRAME, because the planes are distances along the
     view and the reader moves the view. The property asked here is the
     consequence rather than the mechanism: at every notch of the page's own
     wheel, in and out, every corner of the drawn box that is in front of the
     eye must lie between the planes. Frozen at the camera the page armed at,
     that fails after FIVE notches in and FOUR out — measured below, and the
     mutation proves it.
  2. IT KEEPS LOOKING FOR TWO MINUTES, AND LOOKS OFTEN. How long, because a
     scene that appears after the sweep gives up is never armed at all; how
     often, because a scene that appears between two looks keeps the
     library's own 0.01/1000 until the next one, and that is the hatching, on
     screen, for as long as the gap.

⚠ AND THE MUTATIONS ARE RUN HERE, IN THIS FILE, ON EVERY GATE. This project
has had three mutation checks that sabotaged nothing and printed the same
words as a check that was genuinely blind. So each one below asserts its own
edit LANDED in the script text before it believes anything the harness says,
and says `THE MUTATION DID NOT LAND` when it did not.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_NODE = shutil.which("node")

#: The aspect a real two-shape scene reports, read off a running page — the
#: same one `test_the_depth_planes_cannot_clip` measures against. The box the
#: camera sees is ±aspect/2; `gl.bounds` is the data's own box BEFORE the
#: model matrix and is the wrong one to judge against.
_ASPECT = [1.0954679926284856, 1.4693597294706, 0.6212582573094755]

#: One notch of the page's own wheel zoom, from `_WHEEL_JS`: the eye is
#: multiplied by 1.1 or by 1/1.1. Nothing else about this file depends on
#: plotly's internals — this is the gesture a reader actually makes.
_NOTCH = 1.1

#: How far to follow the reader. A dozen notches is about as far as anyone
#: scrolls in one go, and it is the distance the review quoted.
_NOTCHES = 14


def _corners():
    a = np.asarray(_ASPECT, float)
    lo, hi = -a / 2, a / 2
    return np.array([[x, y, z] for x in (lo[0], hi[0])
                     for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], float)


def _clipped(eye, near, far):
    """Corners of the drawn box, in front of the eye, outside the planes.

    ⚠ ASKED OF WHAT IS DRAWN, NOT OF WHAT THE FIT WAS HANDED. Checking the
    corners the fit derived its own numbers from is a tautology, and an
    earlier version of the sister file was exactly that while the planes cut
    the axis box away.
    """
    e = np.asarray(eye, float)
    view = -e / np.linalg.norm(e)
    along = (_corners() - e) @ view
    front = along[along > 0]
    return int((front < near).sum() + (front > far).sum())


#: A page that has drawn, and a reader turning the wheel on it. The script is
#: the shipped one, `eval`ed whole — arming, wrapper, sweep and all — so a
#: change to the real body is a change to what is measured here.
_ZOOM = r"""
const A = ASPECT;
const gl = {camera: {eye: [1.5, 1.5, 1.5], center: [0, 0, 0]},
            aspect: A, zNear: 0.01, zFar: 1000, onrender: null};
const gd = {_fullLayout: {scene: {_scene: {glplot: gl}}},
            on() {}, __h: []};
global.document = {readyState: "complete", addEventListener() {},
                   querySelectorAll: () => [gd]};
// The sweep is not the subject here; the frames are.
global.setInterval = () => 0;
global.clearInterval = () => {};
eval(require("fs").readFileSync(process.argv[2], "utf8"));
const OUT = process.argv[3] === "out";
const k = OUT ? NOTCH : 1 / NOTCH;
const steps = [];
for (let n = 0; n <= NOTCHES; n++) {
  // The frame the library draws after the wheel moved the camera. This is
  // the ONLY thing that stands between a moved camera and the planes.
  if (typeof gl.onrender === "function") gl.onrender();
  steps.push({eye: gl.camera.eye.slice(), near: gl.zNear, far: gl.zFar});
  gl.camera.eye = gl.camera.eye.map(v => v * k);
}
console.log(JSON.stringify(
  {armed: !!(gl.onrender && gl.onrender.__cqDepth), steps: steps}));
"""


def _zoom(script_text, out, tmp_path, tag):
    script = tmp_path / f"depth-{tag}.js"
    script.write_text(script_text)
    page = tmp_path / f"zoom-{tag}.js"
    page.write_text(_ZOOM.replace("ASPECT", json.dumps(_ASPECT))
                    .replace("NOTCHES", str(_NOTCHES))
                    .replace("NOTCH", repr(_NOTCH)))
    done = subprocess.run([_NODE, str(page), str(script),
                           "out" if out else "in"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    return json.loads(done.stdout)


def _without_the_per_frame_fit():
    """`_DEPTH_JS` with `fit` taken out of the render wrapper, and only there.

    ⚠ `fit(gl);` OCCURS TWICE — once at the end of `arm`, once inside the
    wrapper — and it is the second that matters. Taking the first would break
    arming outright, which every existing check would catch; taking the
    second leaves a page that fits once and never again, which none of them
    can see. The anchor carries the line above it so it can only match one.
    """
    import ti3gamut
    src = ti3gamut._DEPTH_JS
    anchor = "var mine = function () {\n        fit(gl);\n"
    assert src.count(anchor) == 1, (
        f"THE MUTATION DID NOT LAND: the render wrapper does not read "
        f"{anchor!r} — it has been rewritten, and this file is now proving "
        f"nothing. Re-anchor it on what the wrapper says today.")
    hurt = src.replace(anchor, "var mine = function () {\n")
    assert hurt != src, "THE MUTATION DID NOT LAND: the script is unchanged"
    assert "function fit(" in hurt and "fit(gl);" in hurt, (
        "THE MUTATION DID NOT LAND: it took out more than the one call — "
        "`fit` must still exist and must still be called by `arm`")
    return hurt


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
@pytest.mark.parametrize("out", [False, True])
def test_the_planes_follow_the_reader_through_a_zoom(out, tmp_path):
    """A ZOOM IS THE CASE THE PLANES ARE LEAST SAFE IN, and it is one gesture.

    The wheel multiplies the eye by 1.1 a notch. Fitted every frame the range
    simply travels with it; frozen where the page armed, the near plane stays
    0.7097 and the far plane 4.4864 while the box walks through them.
    """
    import ti3gamut
    got = _zoom(ti3gamut._DEPTH_JS, out, tmp_path, "real")
    assert got["armed"], f"the harness never armed the scene: {got}"
    moved = {(round(s["near"], 6), round(s["far"], 6)) for s in got["steps"]}
    assert len(moved) > _NOTCHES * 0.5, (
        f"the planes took only {len(moved)} distinct values over "
        f"{_NOTCHES + 1} notches — they are not following the camera at all, "
        f"and everything below would pass on a frozen page")
    for n, step in enumerate(got["steps"]):
        assert step["far"] > step["near"] > 0, f"notch {n}: {step}"
        assert _clipped(step["eye"], step["near"], step["far"]) == 0, (
            f"{'out' if out else 'in'}, notch {n}: a corner of the drawn box "
            f"is outside the planes {step['near']:.4f}..{step['far']:.4f} — "
            f"the picture is being cut")


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
@pytest.mark.parametrize("out", [False, True])
def test_a_page_that_fits_once_and_never_again_is_caught(out, tmp_path):
    """THE MUTATION THE WHOLE SUITE COULD NOT SEE, run on every gate.

    With `fit` gone from the wrapper the page still arms, and still draws its
    first frame against correctly fitted planes — which is why
    `test_a_saved_page_really_arms_the_depth_fix` stays green on it. What it
    loses is every frame after the first.

    Both halves are asserted: that the mutant is still armed and still fitted
    at rest (or the failure below would be about broken arming, not about the
    thing this is for), and that it then clips.
    """
    hurt = _without_the_per_frame_fit()
    got = _zoom(hurt, out, tmp_path, "hurt")
    assert got["armed"], (
        f"THE MUTATION DID NOT LAND as intended: it broke the arming, so "
        f"what follows would be proving the wrong thing: {got}")
    first = got["steps"][0]
    assert first["near"] != 0.01 and first["far"] != 1000, (
        f"THE MUTATION DID NOT LAND as intended: `arm` no longer fits at all, "
        f"so the mutant is a different fault from the one being proved: {got}")
    frozen = {(round(s["near"], 6), round(s["far"], 6)) for s in got["steps"]}
    assert len(frozen) == 1, (
        f"THE MUTATION DID NOT LAND: the planes still moved across the zoom, "
        f"so `fit` is being reached by some other route: {sorted(frozen)}")
    where = [n for n, s in enumerate(got["steps"])
             if _clipped(s["eye"], s["near"], s["far"])]
    assert where, (
        "THE MUTATION DID NOT LAND: with the planes frozen for "
        f"{_NOTCHES} notches nothing was clipped, so the check above cannot "
        "see this fault and is worth nothing")
    assert where[0] <= 12, (
        f"the frozen planes only start clipping at notch {where[0]}, further "
        f"than a reader would scroll in one go — the claim that this is "
        f"reachable needs re-measuring")


#: A page whose viewer never arrives: nothing is ever drawn, so the sweep
#: runs its whole life and the harness can read both numbers off it.
_TIMER = r"""
const started = [];
let ticks = 0, stopped = null;
global.document = {readyState: "complete", addEventListener() {},
                   querySelectorAll: () => []};
global.setInterval = (fn, ms) => {
  started.push({ms: ms, fn: fn});
  return started.length;
};
global.clearInterval = (id) => { stopped = id; };
eval(require("fs").readFileSync(process.argv[2], "utf8"));
// ⚠ NOT `while (stopped === null)`. A sweep that never stops would hang the
// gate; it has to be caught and reported as the fault it is.
const CAP = 50000;
if (started.length === 1) {
  while (stopped === null && ticks < CAP) { started[0].fn(); ticks += 1; }
}
console.log(JSON.stringify({intervals: started.length,
                            ms: started.length ? started[0].ms : null,
                            ticks: ticks, stopped: stopped !== null,
                            hit_cap: ticks >= CAP}));
"""


def _timing(script_text, tmp_path, tag):
    script = tmp_path / f"depth-{tag}.js"
    script.write_text(script_text)
    page = tmp_path / f"timer-{tag}.js"
    page.write_text(_TIMER)
    done = subprocess.run([_NODE, str(page), str(script)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    got = json.loads(done.stdout)
    got["life"] = (got["ms"] or 0) * got["ticks"] / 1000.0
    return got


#: How long the sweep must keep looking, in seconds. The page that travels
#: furthest is the one saved WITHOUT the viewer in it — 1.4 MB instead of
#: 6.2 — and it fetches 4,851,164 bytes from a CDN before there is anything
#: to arm. `e1d2650`'s bug was a sweep whose whole life was ten seconds.
_MUST_LOOK_FOR = 100.0

#: And how often, in milliseconds. A scene built between two looks keeps
#: gl-plot3d's own 0.01/1000 until the next one, and on a 16-bit buffer that
#: is the hatching, on screen, for the whole gap. A reader opens a file,
#: changes the colour space or adds a comparison and gets a new glplot every
#: time; a second is already generous.
_MUST_LOOK_EVERY = 1000.0

#: A sweep walks every `.js-plotly-plot` in the document, so it is not free.
#: With the life pinned above, this is what stops the period being bought
#: down to nothing: 100 s at 10 ms would be ten thousand sweeps.
_AT_MOST_TICKS = 2000


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
def test_the_sweep_looks_often_enough_and_for_long_enough(tmp_path):
    """THE PERIOD AND THE LIFE, WHICH WERE HELD IN PLACE BY NOTHING.

    Both node harnesses in the sister file stub `setInterval` as
    `(fn) => { timer = fn; }` and drive it by hand, so `}, 250)` could have
    been any number at all. These are the two properties the number is FOR.
    """
    import ti3gamut
    got = _timing(ti3gamut._DEPTH_JS, tmp_path, "real")
    assert not got["hit_cap"], (
        f"the sweep never stopped in 50,000 ticks — a timer that runs for "
        f"ever on every saved page is its own fault: {got}")
    assert got["intervals"] == 1, (
        f"expected exactly one repeating sweep, got {got['intervals']}")
    assert got["stopped"], f"the sweep never called clearInterval: {got}"
    assert got["life"] >= _MUST_LOOK_FOR, (
        f"the sweep gives up after {got['life']:.1f} s "
        f"({got['ticks']} looks of {got['ms']} ms). A page saved without the "
        f"viewer fetches 4.8 MB before there is anything to arm; at ten "
        f"seconds the fix silently never happened, which is the bug e1d2650 "
        f"fixed")
    assert got["ms"] <= _MUST_LOOK_EVERY, (
        f"the sweep looks only every {got['ms']} ms, so a scene built just "
        f"after a look keeps the library's own 0.01/1000 — the hatching, on "
        f"screen — for up to that long")
    assert got["ticks"] <= _AT_MOST_TICKS, (
        f"{got['ticks']} sweeps of the whole document is not free; the period "
        f"has been bought down instead of the life being lengthened")


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
@pytest.mark.parametrize("ms,breaks", [(10, "life"), (20000, "period")])
def test_moving_the_sweep_period_is_caught(ms, breaks, tmp_path):
    """THE TWO NUMBERS A REVIEW PUT THERE, each failing the right property.

    10 ms keeps the 480 looks and spends them in 4.8 seconds — the shipped
    bug, back. 20 s keeps the two minutes and looks six times in it, so a
    reader watches a hatched picture for up to twenty seconds. A single
    property could not tell those apart, which is why there are two.
    """
    import ti3gamut
    src = ti3gamut._DEPTH_JS
    # ⚠ READ THE PERIOD, DO NOT SPELL IT. Anchored on the literal `}, 250);`
    # this would cry THE MUTATION DID NOT LAND at anyone who re-tuned the
    # sweep to 300 — a check failing on correct code, which is how a suite
    # teaches people to ignore it. The number is whatever the script says.
    found = re.findall(r"setInterval\(function \(\) \{[\s\S]*?\},\s*(\d+)\);",
                       src)
    assert len(found) == 1, (
        f"THE MUTATION DID NOT LAND: found {len(found)} repeating sweeps in "
        f"the script, so this no longer knows which period to move")
    hurt = src.replace("}, %s);" % found[0], "}, %d);" % ms)
    assert hurt != src, "THE MUTATION DID NOT LAND: the script is unchanged"
    got = _timing(hurt, tmp_path, f"hurt{ms}")
    assert got["ms"] == ms, (
        f"THE MUTATION DID NOT LAND: the sweep still asks for {got['ms']} ms")
    if breaks == "life":
        assert got["life"] < _MUST_LOOK_FOR, (
            f"THE MUTATION DID NOT LAND: at {ms} ms the sweep still lives "
            f"{got['life']:.1f} s, so the check above cannot see this")
    else:
        assert got["ms"] > _MUST_LOOK_EVERY, (
            f"THE MUTATION DID NOT LAND: {ms} ms is still inside what the "
            f"check above allows")
