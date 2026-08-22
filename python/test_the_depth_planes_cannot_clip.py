"""The near and far planes are fitted in JavaScript, so they are tested in it.

WHY THEY EXIST. gl-plot3d never sets either, and falls back to zNear 0.01 and
zFar 1000 over a scene that is a unit cube — a hundred thousand to one. Depth
precision is spent nearest the eye, so nearly all of it lands in empty space
in front of the shapes. This machine's depth buffer is SIXTEEN bits
(`gl.getParameter(gl.DEPTH_BITS)` through the window's own viewer), and at 16
bits over that range one step of depth is larger than a Lab at the distance
these shapes are drawn from. A lid laid a median 0.116 Lab under the skin
cannot be told from it, and the picture hatches wherever the two run close.
Fitted, the lid's own speckle went 121 → 2, 158 → 5 and 193 → 17 at three of
four cameras on a page a reader would get. ⚠ AT THE FOURTH — seen from below
— it is 34 → 132, WORSE than leaving the planes alone, and that is not
understood. It is written here because the first version of this docstring
quoted 34 → 1: numbers taken before the box was corrected, which made the one
camera that got worse read as the best of the four.

⚠ THE SHIPPED FUNCTION IS WHAT RUNS HERE, not a copy of it in Python. A copy
is a test of the copy: it drifts, and it passes while the thing it stands for
is broken. `fit` is lifted out of `_DEPTH_JS` by matching its braces and run
under `node`, so a change to the real body is a change to what is measured.

WHAT MUST HOLD. Every corner of the scene has to sit between the planes from
any camera — including one pushed inside the shape, where the nearest corner
is behind the eye and the near plane has to clamp instead of going negative.
A plane that clipped would take the front off a gamut, which is worse than
any hatching.
"""
import json
import pathlib
import shutil
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_NODE = shutil.which("node")

#: The bounds a real two-shape scene reports, read off the running page.
#: ⚠ THE BOX THE CAMERA SEES IS `aspect`, NOT `bounds`. `bounds` is the
#: data's own box BEFORE the model matrix, and fitting to it put the far plane
#: through the axis box: 113,649 pixels of grid wall and tick text erased at
#: one of the page's own "look from" buttons. The drawn box is exactly
#: ±aspect/2 about the origin. Both are read off a running page; `_BOUNDS` is
#: kept only so a check can prove they are NOT the same box.
_ASPECT = [1.0954679926284856, 1.4693597294706, 0.6212582573094755]
_DRAWN = [[-_ASPECT[0] / 2, -_ASPECT[1] / 2, -_ASPECT[2] / 2],
          [_ASPECT[0] / 2, _ASPECT[1] / 2, _ASPECT[2] / 2]]
_BOUNDS = [[-0.5007121452005382, -0.5049202423673854, -0.03125],
           [0.5617878547994619, 0.5575797576326144, 1.03125]]

#: ⚠ THE AXIS-ALIGNED ONES ARE THE POINT. On the main diagonal the error in
#: fitting to the wrong box cancels — |x| ≈ |y| against an offset in z — so a
#: list of diagonal cameras passes while the far plane cuts the axis box away.
#: These five are what the page's own "look from" buttons produce, and they
#: are where 113,649 pixels went missing.
_EYES = [[1.5, 1.5, 1.5], [-1.5, -1.4, 0.6], [0.1, -0.4, 1.9],
         [-1.3, -1.3, -0.4], [6.0, 5.6, 2.4], [0.45, 0.42, 0.18],
         [0.0, 0.0, 0.05],
         [0.03, 0.03, 2.2], [0.02, 2.2, 0.02], [2.2, 0.02, 0.02],
         [0.03, 0.03, -2.2], [0.02, -2.2, 0.02]]


def _the_shipped_fit():
    """`fit` exactly as `_DEPTH_JS` carries it."""
    import ti3gamut
    src = ti3gamut._DEPTH_JS
    at = src.index("function fit(")
    depth, end = 0, None
    for n in range(src.index("{", at), len(src)):
        if src[n] == "{":
            depth += 1
        elif src[n] == "}":
            depth -= 1
            if depth == 0:
                end = n + 1
                break
    assert end is not None, "could not find the end of fit() in _DEPTH_JS"
    body = src[at:end]
    assert "zNear" in body and "zFar" in body and "bounds" in body, (
        f"what was lifted out of _DEPTH_JS does not look like the fit: "
        f"{body[:120]!r}")
    return body


def test_the_fit_is_still_findable_in_the_script():
    """IF IT IS NOT, EVERY OTHER CHECK HERE WOULD SKIP OR LIE. Renaming or
    restructuring the script must break this loudly, not silently."""
    body = _the_shipped_fit()
    assert 400 < len(body) < 9000, f"fit() is {len(body)} characters, which is "\
        f"not the shape of the function these tests were written against"
    # ⚠ THIS IS A CHECK ON THE TEXT, AND IT IS HERE BECAUSE NOTHING ELSE CAN
    # SEE THE FAULT. The failure is that `gl.bounds` is the data's box BEFORE
    # the model matrix while the camera sits after it — and only the real
    # matrix, on a real page, makes the two disagree. A fake `gl` cannot: fed
    # `bounds`, the fit gives planes WIDER than the drawn box, so every
    # camera below passes. The rendered evidence is in the queue: 113,649
    # pixels erased at "above", 13,413 looking along b*, both gone once the
    # box was ±aspect/2.
    assert "gl.aspect" in body, "fit() no longer reads `aspect`"
    # ⚠ THE ASSIGNMENT, NOT THE WORD. `gl.bounds` is named in fit()'s own
    # comment explaining why it is the wrong box, so asking whether the string
    # appears failed on the correct code.
    assert "a[0] / 2" in body and "= gl.bounds" not in body, (
        "fit() is not building the drawn box from aspect, or has gone back to "
        "`gl.bounds` — which is the box BEFORE the model matrix, and clips the "
        "axis box at every camera the page's own buttons produce")


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
def test_no_camera_can_clip_the_scene():
    body = _the_shipped_fit()
    harness = body + """
var cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(function (c) {
  var gl = {camera: {eye: c, center: [0, 0, 0]}, aspect: ASPECT,
            bounds: BOUNDS, zNear: 0.01, zFar: 1000};
  fit(gl);
  return [gl.zNear, gl.zFar];
})));
""".replace("BOUNDS", json.dumps(_BOUNDS)).replace("ASPECT", json.dumps(_ASPECT)).replace("ASPECT", json.dumps(_ASPECT))
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        where = f.name
    done = subprocess.run([_NODE, where, json.dumps(_EYES)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    planes = json.loads(done.stdout)
    # ⚠ THE DRAWN BOX, which is not the one the fit is handed. Checking the
    # corners the fit derived from would be a tautology, and was: the first
    # version of this file passed while the planes cut the axis box away.
    lo, hi = np.asarray(_DRAWN[0]), np.asarray(_DRAWN[1])
    looked = 0
    for eye, (near, far) in zip(_EYES, planes):
        assert far > near > 0, f"from {eye}: near {near}, far {far}"
        e = np.asarray(eye, float)
        view = -e / np.linalg.norm(e)
        for x in (lo[0], hi[0]):
            for y in (lo[1], hi[1]):
                for z in (lo[2], hi[2]):
                    along = float((np.array([x, y, z]) - e) @ view)
                    if along <= 0:
                        continue        # behind the eye; nothing to clip
                    looked += 1
                    assert near <= along <= far, (
                        f"from {eye} a corner sits {along:.4f} along the view, "
                        f"outside [{near:.4f}, {far:.4f}] — the picture would "
                        f"be clipped")
    assert looked > 40, f"only {looked} corners were in front of any eye"


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
def test_it_is_a_large_improvement_and_not_a_small_one():
    """WHY IT IS WORTH DOING. Against the 100,000:1 the library leaves."""
    body = _the_shipped_fit()
    harness = body + """
var gl = {camera: {eye: [1.5, 1.5, 1.5], center: [0, 0, 0]}, aspect: ASPECT,
          bounds: BOUNDS, zNear: 0.01, zFar: 1000};
fit(gl);
console.log(JSON.stringify([gl.zNear, gl.zFar]));
""".replace("BOUNDS", json.dumps(_BOUNDS)).replace("ASPECT", json.dumps(_ASPECT))
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        where = f.name
    done = subprocess.run([_NODE, where], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    near, far = json.loads(done.stdout)
    assert far / near < 30.0, (
        f"the fitted range is {far / near:.1f}:1 — not much better than the "
        f"100,000:1 it replaces, so the depth precision is still spent in "
        f"empty space")


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
def test_it_leaves_a_scene_it_cannot_measure_alone():
    """A PAGE THAT CANNOT DO THIS MUST DRAW WHAT IT DREW BEFORE. Missing
    bounds, a missing camera, an eye sitting on the centre — each has to come
    back with the planes untouched rather than with something absurd."""
    body = _the_shipped_fit()
    harness = body + """
var out = [];
[{camera: {eye: [1,1,1], center: [0,0,0]}},
 {aspect: ASPECT},
 {camera: {eye: [0,0,0], center: [0,0,0]}, aspect: ASPECT},
 {camera: {eye: [1,1,1], center: [0,0,0]}, aspect: [0,0,0]}
].forEach(function (gl) {
  gl.zNear = 0.01; gl.zFar = 1000;
  fit(gl);
  out.push([gl.zNear, gl.zFar]);
});
console.log(JSON.stringify(out));
""".replace("BOUNDS", json.dumps(_BOUNDS)).replace("ASPECT", json.dumps(_ASPECT))
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        where = f.name
    done = subprocess.run([_NODE, where], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    # ⚠ EVERY ONE OF THEM MUST BE LEFT ALONE, the flat scene included. Asked
    # only for planes that are SANE, a mutation that dropped the degenerate
    # guard passed: a box of zero size still yields far > near > 0 once the
    # pad is added, and the picture would be drawn against planes fitted to
    # nothing.
    for n, (near, far) in enumerate(json.loads(done.stdout)):
        assert (near, far) == (0.01, 1000), (
            f"case {n}: the planes moved to {near}, {far} on a scene this "
            f"cannot measure — it must leave them alone")


_PAGE = r"""
// A fake page, so the arming can be driven through the two ways it used to
// stop working in silence.
const scenes = {};
function newScene(key) {
  const gl = {camera: {eye: [1.5, 1.5, 1.5], center: [0, 0, 0]},
              aspect: [1.0954679926284856, 1.4693597294706, 0.6212582573094755],
              zNear: 0.01, zFar: 1000, onrender: null};
  scenes[key] = {_scene: {glplot: gl}};
  return gl;
}
const gd = {_fullLayout: scenes, __handlers: {},
            on(name, fn) { (this.__handlers[name] ||= []).push(fn); },
            fire(name) { (this.__handlers[name] || []).forEach(f => f()); }};
global.document = {readyState: "complete", addEventListener() {},
                   querySelectorAll: () => [gd]};
global.setInterval = () => 0;
global.clearInterval = () => {};
const one = newScene("scene");
eval(require("fs").readFileSync(process.argv[2], "utf8"));
const armed = g => !!(g.onrender && g.onrender.__cqDepth);
const out = {};
out.first_armed = armed(one);
out.first_fitted = one.zNear !== 0.01;
one.onrender = function () { return "library"; };
out.after_replaced = armed(one);
gd.fire("plotly_afterplot");
out.re_armed = armed(one);
const late = newScene("scene2");
out.late_before = armed(late);
gd.fire("plotly_afterplot");
out.late_after = armed(late);
out.late_fitted = late.zNear !== 0.01;
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
def test_the_arming_survives_the_two_ways_it_used_to_stop(tmp_path):
    """BOTH OF THESE WERE REAL AND BOTH WERE SILENT — the page goes on drawing
    and only the hatching comes back.

    THE MARK WAS ON THE SCENE, NOT ON THE FUNCTION. Written as a flag on the
    glplot object it says "armed" for ever, so if the library assigns
    `onrender` again — a restyle, a rebuild — ours is gone and is never put
    back.

    AND THE SWEEP WAS BOUNDED. It ran forty times over ten seconds; a scene
    built after that — the reader opens another file, changes the colour
    space, adds a comparison — is a NEW glplot and was never armed at all.
    """
    import ti3gamut
    script = tmp_path / "depth.js"
    script.write_text(ti3gamut._DEPTH_JS)
    page = tmp_path / "page.js"
    page.write_text(_PAGE)
    done = subprocess.run([_NODE, str(page), str(script)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    got = json.loads(done.stdout)
    assert got["first_armed"] and got["first_fitted"], (
        f"the opening sweep did not arm or fit the scene: {got}")
    assert not got["after_replaced"], (
        "the harness did not manage to take our handler off, so what follows "
        "proves nothing")
    assert got["re_armed"], (
        f"the library replaced `onrender` and nothing put ours back: {got}")
    assert not got["late_before"], (
        "the harness's late scene was already armed, so what follows proves "
        "nothing")
    assert got["late_after"] and got["late_fitted"], (
        f"a scene built after the opening sweep is never armed: {got}")


_LATE = r"""
// A page saved WITHOUT the viewer inside it: nothing is drawn until the
// viewer arrives from the network, which on a slow connection is long after
// a bounded sweep would have given up.
let timer = null, arrived = false;
const scenes = {};
const gl = {camera: {eye: [1.5, 1.5, 1.5], center: [0, 0, 0]},
            aspect: [1.0954679926284856, 1.4693597294706, 0.6212582573094755],
            zNear: 0.01, zFar: 1000, onrender: null};
const gd = {_fullLayout: scenes, on() {}};
global.document = {readyState: "complete", addEventListener() {},
                   querySelectorAll: () => (arrived ? [gd] : [])};
global.setInterval = (fn) => { timer = fn; return 1; };
global.clearInterval = () => { timer = null; };
eval(require("fs").readFileSync(process.argv[2], "utf8"));
const AFTER = Number(process.argv[3]);
let n = 0;
for (; n < 900 && timer; n++) {
  if (n === AFTER) { arrived = true; scenes.scene = {_scene: {glplot: gl}}; }
  timer();
}
console.log(JSON.stringify({armed: !!(gl.onrender && gl.onrender.__cqDepth),
                            fitted: gl.zNear !== 0.01, sweeps: n,
                            still_sweeping: !!timer}));
"""


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
@pytest.mark.parametrize("late", [0, 5, 100, 400])
def test_a_page_whose_viewer_arrives_late_is_still_fixed(late, tmp_path):
    """THE PAGE THAT TRAVELS FURTHEST IS THE ONE WITHOUT THE VIEWER IN IT.

    Saved that way it is 1.4 MB instead of 6.2 MB and fetches the viewer when
    the reader opens it — so nothing exists to arm until the network answers.
    The sweep used to run forty times at 250 ms and stop: on any connection
    slower than ten seconds the fix never happened, and the only symptom was
    the hatching being there.

    It now stops when a scene has actually been armed, and otherwise keeps
    looking for two minutes.
    """
    import ti3gamut
    script = tmp_path / "depth.js"
    script.write_text(ti3gamut._DEPTH_JS)
    page = tmp_path / "late.js"
    page.write_text(_LATE)
    done = subprocess.run([_NODE, str(page), str(script), str(late)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    got = json.loads(done.stdout)
    assert got["armed"] and got["fitted"], (
        f"a viewer arriving at sweep {late} was never armed: {got}")
    assert not got["still_sweeping"], (
        f"it is still sweeping after arming: {got}")
    assert got["sweeps"] <= late + 8, (
        f"it swept {got['sweeps']} times for a viewer that arrived at "
        f"{late} — it should stop once there is something armed")
