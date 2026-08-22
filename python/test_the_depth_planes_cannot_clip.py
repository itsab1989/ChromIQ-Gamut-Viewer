"""The near and far planes are fitted in JavaScript, so they are tested in it.

WHY THEY EXIST. gl-plot3d never sets either, and falls back to zNear 0.01 and
zFar 1000 over a scene that is a unit cube — a hundred thousand to one. Depth
precision is spent nearest the eye, so nearly all of it lands in empty space
in front of the shapes. This machine's depth buffer is SIXTEEN bits
(`gl.getParameter(gl.DEPTH_BITS)` through the window's own viewer), and at 16
bits over that range one step of depth is larger than a Lab at the distance
these shapes are drawn from. A lid laid a median 0.116 Lab under the skin
cannot be told from it, and the picture hatches wherever the two run close.
Fitted, the lid's own speckle went 121 → 2, 158 → 1, 193 → 4 and 34 → 1 at
four cameras on a page a reader would get.

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
_BOUNDS = [[-0.5007121452005382, -0.5049202423673854, -0.03125],
           [0.5617878547994619, 0.5575797576326144, 1.03125]]

_EYES = [[1.5, 1.5, 1.5], [-1.5, -1.4, 0.6], [0.1, -0.4, 1.9],
         [-1.3, -1.3, -0.4], [6.0, 5.6, 2.4], [0.45, 0.42, 0.18],
         [0.0, 0.0, 0.05]]


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
    assert 400 < len(body) < 4000, f"fit() is {len(body)} characters, which is "\
        f"not the shape of the function these tests were written against"


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
def test_no_camera_can_clip_the_scene():
    body = _the_shipped_fit()
    harness = body + """
var cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(function (c) {
  var gl = {camera: {eye: c, center: [0, 0, 0]}, bounds: BOUNDS,
            zNear: 0.01, zFar: 1000};
  fit(gl);
  return [gl.zNear, gl.zFar];
})));
""".replace("BOUNDS", json.dumps(_BOUNDS))
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        where = f.name
    done = subprocess.run([_NODE, where, json.dumps(_EYES)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    planes = json.loads(done.stdout)
    lo, hi = np.asarray(_BOUNDS[0]), np.asarray(_BOUNDS[1])
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
var gl = {camera: {eye: [1.5, 1.5, 1.5], center: [0, 0, 0]}, bounds: BOUNDS,
          zNear: 0.01, zFar: 1000};
fit(gl);
console.log(JSON.stringify([gl.zNear, gl.zFar]));
""".replace("BOUNDS", json.dumps(_BOUNDS))
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        where = f.name
    done = subprocess.run([_NODE, where], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    near, far = json.loads(done.stdout)
    assert far / near < 20.0, (
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
 {bounds: BOUNDS},
 {camera: {eye: [0,0,0], center: [0,0,0]}, bounds: BOUNDS},
 {camera: {eye: [1,1,1], center: [0,0,0]}, bounds: [[0,0,0],[0,0,0]]}
].forEach(function (gl) {
  gl.zNear = 0.01; gl.zFar = 1000;
  fit(gl);
  out.push([gl.zNear, gl.zFar]);
});
console.log(JSON.stringify(out));
""".replace("BOUNDS", json.dumps(_BOUNDS))
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
