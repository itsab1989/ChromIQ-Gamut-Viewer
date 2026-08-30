"""The near and far planes are fitted in JavaScript, so they are tested in it.

WHY THEY EXIST. gl-plot3d never sets either, and falls back to zNear 0.01 and
zFar 1000 over a scene that is a unit cube — a hundred thousand to one. Depth
precision is spent nearest the eye, so nearly all of it lands in empty space
in front of the shapes. This machine's depth buffer is SIXTEEN bits
(`gl.getParameter(gl.DEPTH_BITS)` through the window's own viewer), and at 16
bits over that range one step of depth is larger than a Lab at the distance
these shapes are drawn from. A lid laid a median 0.116 Lab under the skin
cannot be told from it, and the picture hatches wherever the two run close.
Fitted, the lid's own speckle goes 121 → 10, 158 → 24, 193 → 16 and 34 → 27
at the four cameras on a page a reader would get.

⚠ THE LAST OF THOSE WAS 34 → 132 — WORSE THAN NOT FITTING AT ALL — and the
cause is worth keeping: the near plane was floored at 1e-3, ten times closer
than gl-plot3d's own 0.01, and perspective depth resolution is proportional to
the near plane. Wherever the floor bit, the fit handed the buffer less
precision than leaving it alone. Two earlier versions of this docstring quoted
34 → 1 and then 121 → 2: the first taken before the drawn box was corrected,
the second with the toolbar still in frame, whose icons speckle exactly like a
hatched seam. Both made the fix read better than it was.

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
    # ⚠ THE BOUND IS WIDE BECAUSE THE FUNCTION CARRIES ITS OWN REASONS. It
    # grew when the near plane turned out to decide WHICH WALL the library
    # paints; that finding is written where the next person will meet it.
    assert 400 < len(body) < 14000, f"fit() is {len(body)} characters, which "\
        f"is not the shape of the function these tests were written against"
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
def test_the_two_numbers_that_were_tuned_are_the_numbers_that_are_checked():
    """⚠ THIS TEST EXISTS BECAUSE NOTHING COULD SEE THE TUNING.

    A hostile review mutated the pad to zero, the pad to five, the near floor
    to 1e-9 and the far pad away altogether, and the whole file stayed green.
    The clip test could not see them because it asked `near <= along <= far`:
    with no pad at all the nearest corner sits EXACTLY on the near plane, and
    equality passes. So the two numbers that took a day of measuring to choose
    were held in place by nothing but the comment beside them.

    THE FIRST PROPERTY: THE PAD CLEARS WHAT IS DRAWN OUTSIDE THE BOX. The
    shapes sit inside ±aspect/2; the tick marks, the tick numbers and the axis
    titles do not, and a plane that lands on the box takes them off. Measured
    in pixels the library drew that the fit erased, looking along b*: a pad of
    a fifth of the box erased 13,413, half the box erased 28. Half is the
    shipped number, so the check asks for a real fraction of it at BOTH ends
    — a far plane on the corner is fault enough on its own.

    THE SECOND PROPERTY: THE NEAR PLANE IS NEVER CLOSER THAN THE LIBRARY'S OWN
    FLOOR. Perspective depth resolution is proportional to the near plane, so
    a near of 1e-3 hands the buffer ten times less precision than gl-plot3d's
    untouched 0.01 — the fix becomes three to forty-eight times worse than no
    fix, at any camera close enough for the clamp to bite, which is a click
    and a half of the page's own wheel zoom. Two of the eyes below are inside
    the box, where `lo` goes negative and the clamp is the only thing between
    the reader and that.

    NEITHER IS AN ARBITRARY THRESHOLD DRESSED AS A LAW. Both are the reason
    the constants are what they are, written so that changing one of them
    without measuring goes red.
    """
    body = _the_shipped_fit()
    harness = body + """
var cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(function (c) {
  var gl = {camera: {eye: c, center: [0, 0, 0]}, aspect: ASPECT,
            bounds: BOUNDS, zNear: 0.01, zFar: 1000};
  fit(gl);
  return [gl.zNear, gl.zFar];
})));
""".replace("BOUNDS", json.dumps(_BOUNDS)).replace("ASPECT", json.dumps(_ASPECT))
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        where = f.name
    done = subprocess.run([_NODE, where, json.dumps(_EYES)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    planes = json.loads(done.stdout)

    across = float(np.linalg.norm(_ASPECT))
    #: Comfortably under the shipped half-a-box, comfortably over the fifth
    #: of a box that was measured erasing 13,413 pixels.
    want = 0.4 * across
    lo_box, hi_box = np.asarray(_DRAWN[0]), np.asarray(_DRAWN[1])
    corners = np.array([[x, y, z] for x in (lo_box[0], hi_box[0])
                        for y in (lo_box[1], hi_box[1])
                        for z in (lo_box[2], hi_box[2])], float)
    inside_the_box = clear_of_the_box = 0
    for eye, (near, far) in zip(_EYES, planes):
        e = np.asarray(eye, float)
        view = -e / np.linalg.norm(e)
        along = (corners - e) @ view
        lo, hi = float(along.min()), float(along.max())

        assert far - hi >= want, (
            f"from {eye} the far plane is only {far - hi:.4f} beyond the "
            f"furthest corner, and the axis furniture is drawn out there — "
            f"a fifth of the box erased 13,413 pixels of it")

        # ⚠⚠ THE NEAR PLANE IS NOT FREE — IT DECIDES WHICH WALL IS PAINTED.
        # gl-plot3d's cube.js orients its face pick against the NDC origin,
        # whose pre-image sits exactly 2*n*f/(n+f) in front of the eye. Fitted
        # symmetrically about the box, as this once was, that point lands
        # INSIDE the box, the pick goes ambiguous over wide arcs, and the
        # library falls through to a projected-area tie-break that paints the
        # NEARER face — a wall across the shape. Measured before the cure:
        # 86.2% of frames picked wrong in the worst regime, 29.2% on the
        # published page 22, against 1.2% with no fit at all.
        #
        # So the property that matters is not "how far in front of the corner
        # is the near plane" but "is the reference point clear of the box".
        reference = 2.0 * near * far / (near + far)
        # ⚠ ONLY WHERE "IN FRONT OF THE BOX" MEANS ANYTHING. With the eye
        # INSIDE the box the nearest corner is behind it (lo < 0) and there is
        # no outside to keep the reference point in; the near plane clamps to
        # the library's floor and cube.js is in the regime it always was.
        if lo <= 0:
            inside_the_box += 1
            assert near >= 0.01 - 1e-12, (
                f"from {eye}, inside the box, the near plane is {near!r} — "
                f"inside gl-plot3d's own floor")
            continue
        clear_of_the_box += 1
        assert reference < lo, (
            f"from {eye} the NDC origin's pre-image sits {reference:.4f} from "
            f"the eye and the nearest corner is at {lo:.4f} — it is INSIDE the "
            f"box, which is what makes the library paint the near wall")
        assert reference <= 0.9 * lo, (
            f"from {eye} the reference point is {reference:.4f} against a "
            f"nearest corner at {lo:.4f} — too close to the box to be safe; "
            f"the measured plateau puts it at 0.4..0.75 of that distance")

        if lo - want < 0.01:
            assert near >= 0.01 - 1e-12, (
                f"from {eye} the near plane is {near!r}, inside gl-plot3d's "
                f"own 0.01 floor — depth resolution is proportional to it")
        else:
            # The near plane is now placed to control the face pick, not to
            # sit a fixed pad in front of the corner — but it must still never
            # cut the box, which the clip test above already asserts.
            assert near < lo, (
                f"from {eye} the near plane at {near:.4f} is past the nearest "
                f"corner at {lo:.4f} — the picture would be cut")
        assert near >= 0.01, (
            f"from {eye} the near plane is {near!r}, inside the library's own "
            f"floor — depth resolution is proportional to it")
    # ⚠ REFUSE AN EMPTY POPULATION. If no camera were ever clear of the box the
    # root-fix invariant above would be asserted zero times and this whole test
    # would pass by never asking anything.
    assert clear_of_the_box >= 6, (
        f"only {clear_of_the_box} cameras sat clear of the box, so the "
        f"reference-point invariant was barely exercised")
    assert inside_the_box >= 1, (
        f"no camera was inside the box, so the clamp path is untested")
    # ⚠ `clamped` USED TO COUNT THIS and is now dead: under the old design the
    # floor bit wherever the near plane would have gone negative, which is
    # exactly the eye-inside-the-box case now counted above. Counting it twice
    # would look like two checks and be one.
    assert inside_the_box >= 2, (
        f"only {inside_the_box} cameras sat inside the box, so the floor that "
        f"stops the near plane going negative is barely exercised")

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


#: An orthographic scene, exactly as a real page reports one. ⚠ MEASURED,
#: NOT GUESSED: asked of a running page in two engines, `_ortho` is false in
#: perspective and true in orthographic on BOTH `gl.camera` and
#: `gl.cameraParams`. A review quoted the minified line `z._ortho=!0` without
#: establishing what `z` was, and a guard on the wrong object is a guard that
#: silently never fires.
_ORTHO_CASES = """
var out = [];
[["perspective, the control", {}, {}],
 ["orthographic on the camera", {_ortho: true}, {}],
 ["orthographic on cameraParams", {}, {_ortho: true}],
 ["orthographic on both", {_ortho: true}, {_ortho: true}]
].forEach(function (c) {
  var cam = {eye: [1.5, 1.5, 1.5], center: [0, 0, 0]};
  if (c[1]._ortho) cam._ortho = true;
  var gl = {camera: cam, aspect: ASPECT, bounds: BOUNDS,
            cameraParams: c[2], zNear: 0.01, zFar: 1000};
  fit(gl);
  out.push([c[0], gl.zNear, gl.zFar]);
  // AND AGAIN FROM A SCENE ALREADY FITTED WHILE IT WAS PERSPECTIVE, which
  // is the real sequence: a reader turns orthographic on after looking.
  gl.zNear = 0.7440993657831864; gl.zFar = 4.452053056923445;
  fit(gl);
  out.push([c[0] + " (already fitted)", gl.zNear, gl.zFar]);
});
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
def test_an_orthographic_scene_is_left_to_the_library():
    """FITTING AN ORTHOGRAPHIC SCENE BREAKS THE PICTURE, AND THE SYMPTOM
    DEPENDS ON THE RENDERER — which is why this is a guard and not a tuning.

    Everything `fit` measures is a distance ALONG THE VIEW FROM THE EYE,
    which is what a perspective frustum is built from. gl-plot3d's
    orthographic path is `ortho(-re, re, -1, 1, zNear, zFar)`, over a
    normalised box nowhere near those distances, so planes of 0.744 and
    4.452 swallow the whole scene.

    PHOTOGRAPHED ON A REAL PAGE, same page, same planes, same `_ortho`:

        chromium / SwiftShader   an EMPTY AXIS BOX, no gamut at all
        webkit   / Apple GPU     the shape drawn, but the gridlines drawn
                                 ACROSS the front of it

    ⚠ SO A CURE MEASURED ONLY IN HEADLESS CHROMIUM WOULD HAVE BEEN JUDGED
    AGAINST A PICTURE NOBODY ON THIS HARDWARE SEES. Headless chromium falls
    back to SwiftShader; headless WebKit renders on the Apple GPU.

    Nothing shipped reaches orthographic today. The queue's own
    next-recommended lever is to offer it as a reader's choice, at which
    point the two features are mutually exclusive — so this is pinned
    BEFORE that feature is built, not after it breaks.

    THE SECOND HALF OF EACH CASE IS THE ONE THAT MATTERS: a scene fitted
    while it was still perspective, then turned orthographic. Merely
    returning would leave the stale perspective planes in place, which is
    exactly what erases the picture, so the library's own fallback has to be
    put back.
    """
    body = _the_shipped_fit()
    harness = body + _ORTHO_CASES.replace("BOUNDS", json.dumps(_BOUNDS)) \
                                 .replace("ASPECT", json.dumps(_ASPECT))
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        where = f.name
    done = subprocess.run([_NODE, where], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    got = json.loads(done.stdout)
    by_name = {name: (near, far) for name, near, far in got}

    # The control must really fit, or the rest of this proves nothing: a
    # guard that refused EVERY scene would pass every assertion below.
    near, far = by_name["perspective, the control"]
    assert (near, far) != (0.01, 1000), (
        "the perspective control was not fitted at all, so this test cannot "
        "tell a working guard from a fit that never runs")
    assert 0 < near < far < 50, f"the control fitted absurdly: {near}, {far}"

    for name, (near, far) in by_name.items():
        if name.startswith("perspective"):
            continue
        assert (near, far) == (0.01, 1000), (
            f"{name}: the planes are {near}, {far} — an orthographic scene "
            f"must be left with the library's own fallback. Fitted, the "
            f"picture is an empty box in SwiftShader and has its gridlines "
            f"drawn across the shape on the Apple GPU")


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
def test_taking_the_orthographic_guard_out_is_caught():
    """THE MUTATION, RUN HERE, ON EVERY GATE — and it proves it landed.

    Without the guard an orthographic scene keeps the perspective planes,
    which is the shipped fault. If this ever stops failing, the check above
    has gone blind and says so in the words this project greps for.
    """
    import ti3gamut
    src = ti3gamut._DEPTH_JS
    anchor = "if ((cam && cam._ortho) || (gl.cameraParams && gl.cameraParams._ortho)) {"
    assert src.count(anchor) == 1, (
        "THE MUTATION DID NOT LAND: the orthographic guard does not read as "
        "this file expects — re-anchor it on what `fit` says today")
    hurt = src.replace(anchor, "if (false) {", 1)
    assert hurt != src, "THE MUTATION DID NOT LAND: the script is unchanged"

    at = hurt.index("function fit(")
    depth, end = 0, None
    for n in range(hurt.index("{", at), len(hurt)):
        if hurt[n] == "{":
            depth += 1
        elif hurt[n] == "}":
            depth -= 1
            if depth == 0:
                end = n + 1
                break
    harness = hurt[at:end] + _ORTHO_CASES.replace("BOUNDS", json.dumps(_BOUNDS)) \
                                         .replace("ASPECT", json.dumps(_ASPECT))
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        where = f.name
    done = subprocess.run([_NODE, where], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    got = {name: (near, far) for name, near, far in json.loads(done.stdout)}
    fitted = [n for n, planes in got.items()
              if not n.startswith("perspective") and planes != (0.01, 1000)]
    assert fitted, (
        "THE MUTATION DID NOT LAND: with the orthographic guard disabled the "
        "planes were still left alone, so the check above is proving nothing")


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

    It now looks for two minutes and then stops — see the two-room test
    below for why it does NOT stop early at the first thing it arms.
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
    assert got["sweeps"] <= 490, (
        f"it swept {got['sweeps']} times and the harness gave up before it "
        "did — a timer that never stops is its own fault")


_TWO_ROOMS = r"""
// Two rooms, the second arriving at sweep K, then a rebuild of the first.
let libraryRan = 0, libraryThis = null, libraryArgs = null;
function room(hasOwn) {
  const gl = {camera: {eye: [1.5, 1.5, 1.5], center: [0, 0, 0]},
              aspect: [1.0954679926284856, 1.4693597294706, 0.6212582573094755],
              zNear: 0.01, zFar: 1000,
              onrender: hasOwn ? function () {
                libraryRan += 1;
                libraryThis = this;
                libraryArgs = Array.prototype.slice.call(arguments);
              } : null};
  const gd = {_fullLayout: {scene: {_scene: {glplot: gl}}}, __h: [],
              on(n, f) { this.__h.push(f); },
              fire() { this.__h.forEach(f => f()); }};
  return {gl, gd};
}
let timer = null, visible = [];
global.document = {readyState: "complete", addEventListener() {},
                   querySelectorAll: () => visible.map(r => r.gd)};
global.setInterval = (fn) => { timer = fn; return 1; };
global.clearInterval = () => { timer = null; };
const A = room(true);
visible = [A];
eval(require("fs").readFileSync(process.argv[2], "utf8"));
const K = Number(process.argv[3]);
const B = room(false);
const armed = r => !!(r.gl.onrender && r.gl.onrender.__cqDepth);
for (let n = 0; n < 900 && timer; n++) {
  if (n === K) visible = [A, B];
  timer();
}
const out = {left: armed(A), right: armed(B),
             right_fitted: B.gl.zNear !== 0.01};
// and now the library rebuilds the LEFT room over our handler -- putting
// its own back, which ours must then wrap again AND go on calling
A.gl.onrender = function () {
  libraryRan += 1;
  libraryThis = this;
  libraryArgs = Array.prototype.slice.call(arguments);
};
A.gd.fire();
out.left_after_rebuild = armed(A);
out.right_still = armed(B);
// and the handler we wrapped at the very start has to still be being called,
// with its own `this` and its own arguments
B.gl.onrender = (function (was) {
  const mine = function () { return was.apply(this, arguments); };
  mine.__cqDepth = true;
  return mine;
})(B.gl.onrender);
libraryRan = 0;
const marker = {who: "gl"};
A.gl.onrender.call(marker, 7, "eight");
out.library_ran = libraryRan;
out.library_this = libraryThis === marker;
out.library_args = JSON.stringify(libraryArgs);
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(_NODE is None, reason="no node on the path to run it with")
@pytest.mark.parametrize("late", [1, 5, 40, 200])
def test_the_second_room_is_armed_however_late_it_opens(late, tmp_path):
    """A COMPARISON PAGE HAS TWO ROOMS AND THEY DO NOT ARRIVE TOGETHER.

    The sweep used to stop as soon as ANY scene was armed — 1.25 s after the
    first room drew. The second room is built later, and by then there was
    nothing left looking: it kept the library's own 0.01/1000 for ever, and
    the only symptom was the hatching being there in the right-hand picture
    and gone in the left. Driven here with the second room arriving at sweep
    5, 40 and 200, it was armed in none of them.

    Asking "is EVERY scene armed" instead does not fix it, which is the trap
    worth writing down: at sweep 5 the only scene on the page IS armed, so
    that question stops the sweep just the same. Nothing but continuing to
    look answers it.

    The tail of this test is the other half — the library assigns `onrender`
    again when it rebuilds a room, and `plotly_afterplot` has to put ours
    back on THAT room. It is one handler per div, because a `var` shared
    across the loop pointed every handler at the last div.
    """
    import ti3gamut
    script = tmp_path / "depth.js"
    script.write_text(ti3gamut._DEPTH_JS)
    page = tmp_path / "rooms.js"
    page.write_text(_TWO_ROOMS)
    done = subprocess.run([_NODE, str(page), str(script), str(late)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:600]
    got = json.loads(done.stdout)
    assert got["left"], f"the first room was never armed: {got}"
    assert got["right"] and got["right_fitted"], (
        f"a second room opening at sweep {late} was never armed: {got}")
    assert got["left_after_rebuild"], (
        f"the library rebuilt the first room and ours was not put back: {got}")
    assert got["right_still"], (
        f"rebuilding the first room disarmed the second: {got}")
    # ⚠ AND WE ARE A GUEST ON A HANDLER THAT IS NOT OURS. `onrender` is
    # gl-plot3d's own per-frame callback and Plotly hangs work on it; ours
    # wraps it, so failing to call through would silently take that work away
    # every frame — with the picture still drawing, which is how it would be
    # missed. Dropping the `was.apply` was the one mutation the whole file
    # could not see.
    assert got["library_ran"] == 1, (
        f"our handler was called once and the handler it wrapped ran "
        f"{got['library_ran']} times — gl-plot3d's own per-frame work is "
        f"being swallowed: {got}")
    assert got["library_this"], (
        f"the wrapped handler was called with the wrong `this`: {got}")
    assert got["library_args"] == '[7,"eight"]', (
        f"the wrapped handler was not given its arguments: {got}")
