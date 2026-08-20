"""A change pushed into the picture on screen draws what a rebuild would draw.

    ../gv-venv/bin/python scripts/audit_a_live_change_is_the_real_thing.py
    ../gv-venv/bin/python scripts/audit_a_live_change_is_the_real_thing.py --prove

WHY THIS EXISTS. "Where they agree", "Where they differ" and "Detail" all used
to wait for the handle to be let go and then rebuild the whole page -- about a
second of black. Reported twice and then as a rule: "should be live", "btw all
sliders should work this way". They are live now, and the way they are live is
that the window works out what `build_figure` would have drawn and pushes
those arrays straight into the scene that is already up.

TWO KINDS OF CHANGE ARE ASKED HERE, and they are two because they are
different in kind rather than in degree:

  a fade    leaves every point where it is and rewrites colours -- plus, at
            either end, a triangle list;
  detail    REBUILDS the comparison, so every point moves, every triangle is
            new, and the paper beside it is re-cut against a new boundary.
            98,499 points at 40 steps. If a push can carry that it can carry
            anything this window does.

THAT MAKES THIS THE CHECK THAT MATTERS, and it is not "did the picture
change". A live push that reaches the wrong trace, or that sends the colours
without the triangles, changes the picture too -- and the rebuild on release
puts it right, so the fault hides behind the very thing it broke. What has to
be true is stronger:

  the live picture IS the rebuilt one   otherwise the reader chooses a fade by
                                        looking at one picture and is handed
                                        another the moment they let go;
  at BOTH ENDS as well as the middle    the ends are where the invisible
                                        triangles are dropped so the rest can
                                        be drawn solid, which is the one place
                                        the push has to replace geometry and
                                        not merely colour;
  for BOTH sliders                      they take opposite halves of the same
                                        mask, and a mistake that swapped them
                                        would look perfectly sensible.

MEASURED IN PIXELS, on a real paper against sRGB, at one fixed camera. Neither
trace
digests nor camera readings can be trusted for this: a page stores its arrays
packed binary, so every length read off `gd.data` is `undefined` -- which is
how a note came to be written into this project saying a page will not let its
triangles be replaced. It will. That note cost the two sliders months of
rebuilding, and it was never true.

A REAL PAPER, NOT AN INVENTED BALL. Three separate checks were fooled in one
night by made-up shapes: one built in the wrong colour space, one whose
lightness range was too narrow to tell two answers apart, one that behaved
differently under the same drag. `demo/Glossy-paper.ti3` has awkward
proportions, dents and a full lightness range -- and sRGB beside it is the
pair in his own screenshots.

AND THE FIXTURE IS MADE TO PROVE IT BITES before any answer is read from it.
See `faces`: if these shapes kept the same triangles at every fade, "0 pixels
different" would say nothing whatever about replacing a triangle list, which
is the one claim here a colours-only push could fake. Two earlier attempts at
this check did exactly that and looked perfect.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

#: One camera for every picture, so the fade is the only thing that varies. A
#: turned room and a faded one differ by tens of thousands of pixels alike.
CAMERA = dict(eye=dict(x=1.55, y=1.35, z=0.85),
              center=dict(x=0, y=0, z=0), up=dict(x=0, y=0, z=1))

#: Both ends and two places in between, for each slider on its own. The ends
#: are not decoration: they are the only values at which the push has to
#: replace a triangle list rather than a colour array.
WHERE = [("where they agree", "agree", 1.0),
         ("where they agree", "agree", 0.6),
         ("where they agree", "agree", 0.05),
         ("where they agree", "agree", 0.0),
         ("where they differ", "differ", 0.6),
         ("where they differ", "differ", 0.05),
         ("where they differ", "differ", 0.0)]

#: What the window sends. Written out here rather than imported from the
#: window because a check that shares the code under test cannot fail; the
#: ARRAYS come from the same place the window gets them, which is the half
#: that has to be shared.
PUSH = """(function (want) {
  var el = document.getElementsByClassName('plotly-graph-div')[0], did = 0;
  if (!el || !window.Plotly) return 0;
  for (var i = 0; i < el.data.length; i++) {
    var n = String(el.data[i].name || '');
    if (!Object.prototype.hasOwnProperty.call(want, n)) continue;
    var w = want[n];
    window.Plotly.restyle(el, {vertexcolor: [w.c], i: [w.i], j: [w.j],
                               k: [w.k]}, [i]);
    did++;
  }
  return did;
})"""


def papers():
    """A real paper against sRGB -- the pair in his own screenshots.

    NOT TWO PAPERS, and the difference is the whole usefulness of this check.
    Glossy against Matte keeps the same 414 and 440 triangles at every fade,
    because after the re-cut some triangles still straddle the boundary and
    `_solid_remainder` refuses a surface it cannot leave wholly solid. Against
    sRGB the same paper goes 1,314 triangles to 566 -- so this is the pair
    that exercises replacing a triangle list, which is the one claim here that
    a colours-only push could fake.
    """
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut

    f = HERE.parent / "demo" / "Glossy-paper.ti3"
    if not f.is_file():
        return None
    return [("Glossy-paper",
             build_gamut(ti3gamut.read_measurement(f).lab, input_space="lab")),
            ("sRGB", reference_gamut("sRGB"))]


#: FULLY SOLID, BECAUSE THAT IS WHERE THE GEOMETRY MOVES.
#:
#: At either end of a fade the invisible faces are dropped so that what is
#: left can go back on the opaque path -- but `_solid_remainder` refuses that
#: for a shape drawn at anything under full strength, and two shapes are drawn
#: see-through by default. Measured at the default: 414 and 440 triangles at
#: every fade, both ends included. So an earlier version of this check pushed
#: nothing but colours, said "0 pixels different" seven times, and proved
#: nothing at all about replacing a triangle list -- which is the one claim it
#: exists to settle. Fully solid, against sRGB, the paper goes 650 triangles
#: to 370 and the comparison 4,998 to 3,725.
SOLID = dict(opacity=1.0, styles=["solid", "solid"])


def a_page(where, name, shapes, **fade):
    import ti3gamut

    out = where / f"{name}.html"
    ti3gamut.write_html(shapes, out, "", split=True, controls=False,
                        camera=CAMERA, spin={"on": False}, **SOLID, **fade)
    return out


def arrays(shapes, **fade):
    import ti3gamut

    figure = ti3gamut.build_figure(shapes, "", split=True, camera=CAMERA,
                                   **SOLID, **fade)
    return ti3gamut.surfaces_for_restyle(figure)


def faces(shapes, **fade):
    """How many triangles each surface has, so the fixture can prove it bites."""
    import ti3gamut

    figure = ti3gamut.build_figure(shapes, "", split=True, camera=CAMERA,
                                   **SOLID, **fade)
    return {t.name: len(t.i) for t in figure.data if t.type == "mesh3d"}


#: The detail the picture is OPENED at, so every push has to move it.
OPENED_AT = 29

#: Detail is the comparison's own resolution, so the shapes themselves change.
DETAILS = [12, 20, 29, 40]

#: HIS OWN CONFIGURATION for the detail half, and not for tidiness: a cage
#: over the comparison with rings inside it is what makes the trace list carry
#: DUPLICATE NAMES -- three traces every one of which is called
#: "sRGB (outline)". That is the only reason the push has to match by position
#: at all, so a check that drew two plain solids would leave the whole
#: ordered-list guard untested. Drawn this way the picture holds 9 traces;
#: drawn as two solids it holds 4 and proves nothing about them.
HIS_WAY = dict(styles=["solid", "mesh"], rings=13)

#: What the window sends for a change of DETAIL: every trace, in order, points
#: and all. Mirrors `_DETAIL_JS` in the window -- written out rather than
#: imported, because a check that shares the code under test cannot fail it.
#: The ARRAYS come from the same place the window gets them, which is the half
#: that has to be shared.
PUSH_ALL = """(function (want) {
  var el = document.getElementsByClassName('plotly-graph-div')[0], i;
  if (!el || !window.Plotly || !el.data) return 0;
  if (el.data.length !== want.length) return 0;
  for (i = 0; i < want.length; i++) {
    if (String(el.data[i].name || '') !== want[i].n) return 0;
    if (el.data[i].type !== want[i].t) return 0;
  }
  var FIELDS = {x: 'x', y: 'y', z: 'z', i: 'i', j: 'j', k: 'k',
                c: 'vertexcolor'};
  for (i = 0; i < want.length; i++) {
    var patch = {}, any = false, f;
    for (f in FIELDS) {
      if (!Object.prototype.hasOwnProperty.call(want[i], f)) continue;
      patch[FIELDS[f]] = [want[i][f]];
      any = true;
    }
    if (any) window.Plotly.restyle(el, patch, [i]);
  }
  return want.length;
})"""


def at_detail(steps):
    """The paper and sRGB built at a given detail — his own pair."""
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut

    f = HERE.parent / "demo" / "Glossy-paper.ti3"
    return [("Glossy-paper",
             build_gamut(ti3gamut.read_measurement(f).lab, input_space="lab")),
            ("sRGB", reference_gamut("sRGB", steps=steps))]


def detail_page(where, steps):
    import ti3gamut

    out = where / f"detail-{steps}.html"
    ti3gamut.write_html(at_detail(steps), out, "", split=True, controls=False,
                        camera=CAMERA, spin={"on": False}, **HIS_WAY)
    return out


def detail_arrays(steps):
    import ti3gamut

    figure = ti3gamut.build_figure(at_detail(steps), "", split=True,
                                   camera=CAMERA, **HIS_WAY)
    return ti3gamut.traces_for_restyle(figure)


def points(steps):
    """How many points the picture holds, so the fixture can prove it bites."""
    return sum(len(t.get("x", ())) for t in detail_arrays(steps))


#: The height the flat picture is OPENED at, so every push has to move it.
CUT_AT = 50
CUTS = [20, 35, 50, 65, 80]

#: A cross-section is drawn to FILL its frame, so its axes and its caption
#: move with it. The window sends both in one call; so does this.
PUSH_FLAT = """(function (both) {
  var el = document.getElementsByClassName('plotly-graph-div')[0], i;
  var want = both[0], frame = both[1];
  if (!el || !window.Plotly || !el.data) return 0;
  if (el.data.length !== want.length) return 0;
  for (i = 0; i < want.length; i++) {
    if (String(el.data[i].name || '') !== want[i].n) return 0;
    if (el.data[i].type !== want[i].t) return 0;
  }
  var FIELDS = {x: 'x', y: 'y', z: 'z', i: 'i', j: 'j', k: 'k',
                c: 'vertexcolor'};
  if (frame) window.Plotly.relayout(el, frame);
  for (i = 0; i < want.length; i++) {
    var patch = {}, any = false, f;
    for (f in FIELDS) {
      if (!Object.prototype.hasOwnProperty.call(want[i], f)) continue;
      patch[FIELDS[f]] = [want[i][f]];
      any = true;
    }
    if (any) window.Plotly.restyle(el, patch, [i]);
  }
  return want.length;
})"""


#: Where the drawn area actually sits inside the picture. Plotly measures the
#: left margin from the WIDEST tick label and settles it when the page is
#: drawn -- so a cut whose numbers reach 100 gets a wider margin than one whose
#: reach 80, and that measurement is not redone the same way for a picture
#: changed in place. Measured: built, the area starts at x=271; pushed to the
#: same height it starts at x=270.5. Half a pixel, and every gridline, glyph
#: and outline in the picture lights up because of it.
#: WHAT IS ACTUALLY DRAWN, read from the library's decoded arrays. A page
#: packs anything sizeable binary, so `t.x.length` off `gd.data` is undefined
#: and every reading from it is the same constant -- four false verdicts in
#: this project so far. `_fullData` carries the decoded lists.
WHAT_IS_DRAWN = """(function () {
  var el = document.getElementsByClassName('plotly-graph-div')[0], out = [];
  var full = (el && el._fullData) || [];
  for (var i = 0; i < full.length; i++) {
    var t = full[i], xs = t.x || [], ys = t.y || [];
    var at = function (a, n) {
      return a.length ? +Number(a[Math.min(n, a.length - 1)]).toFixed(4)
                      : null;
    };
    out.push([String(t.name || ''), t.type, xs.length, ys.length,
              at(xs, 0), at(xs, Math.floor(xs.length / 2)), at(xs, 99999),
              at(ys, 0), at(ys, Math.floor(ys.length / 2)), at(ys, 99999),
              String((t.line || {}).color), String(t.fillcolor)]);
  }
  return JSON.stringify([out, (el.layout.title || {}).text,
                         (el._fullLayout.xaxis || {}).range,
                         (el._fullLayout.yaxis || {}).range]);
})()"""

WHERE_IT_SITS = """(function () {
  var el = document.getElementsByClassName('plotly-graph-div')[0];
  var f = el && el._fullLayout;
  // A ROOM HAS NO FLAT AXES -- it is drawn in a scene -- so this answers only
  // for a cross-section, which is the one picture whose frame can move.
  if (!f || !f.xaxis || !f.yaxis) return null;
  return {x: f.xaxis._offset, y: f.yaxis._offset,
          w: f.xaxis._length, h: f.yaxis._length};
})()"""


def cut_page(where, lightness, shapes):
    import ti3gamut

    out = where / f"cut-{lightness}.html"
    ti3gamut.write_slice_html(shapes, out, float(lightness), "Measured gamut",
                              controls=False)
    return out


def cut_arrays(lightness, shapes):
    import ti3gamut

    figure = ti3gamut.build_slice_figure(shapes, float(lightness),
                                         "Measured gamut", "dark",
                                         extent=None, slidable=False)
    return [ti3gamut.traces_for_restyle(figure),
            ti3gamut.frame_for_relayout(figure)]


def shoot(browser, path, tag, out_dir, want=None, script=None):
    tab = browser.new_page(viewport={"width": 1200, "height": 820})
    tab.goto(path.resolve().as_uri())
    tab.wait_for_selector(".plotly-graph-div", timeout=40000)
    tab.wait_for_timeout(6000)
    did = None
    if want is not None:
        did = tab.evaluate(script or PUSH, want)
        tab.wait_for_timeout(3000)
    shot = out_dir / f"{tag}.png"
    tab.locator(".plotly-graph-div").first.screenshot(path=str(shot))
    where = tab.evaluate(WHERE_IT_SITS)
    drawn = tab.evaluate(WHAT_IS_DRAWN)
    tab.close()
    return shot, did, (where, drawn)


#: Rows the caption is written across, and everything below them is the room.
#:
#: THE CAPTION IS NOT THE PICTURE, and telling them apart is the whole reason
#: this is a number rather than a whole-image comparison. At either end of a
#: fade the caption gains a sentence -- "Matte-paper is not drawn: it agrees
#: with the others everywhere" -- and that sentence is written by Python when
#: the page is built, so a push cannot produce it. Measured: the live picture
#: and the rebuilt one differ by 2,477 pixels at a fade of nothing, and every
#: one of those pixels lies in rows 19-31. The shapes below are identical.
#:
#: The window knows this and rebuilds at the ends for exactly that sentence --
#: see `_after_fade`. So the drawn shapes are what has to match here, and the
#: caption is asked about separately, in Python, where it can be read rather
#: than guessed at from pixels.
CAPTION_ROWS = 60


def apart(a, b):
    """Pixels different overall, and pixels different BELOW the caption."""
    import numpy as np
    from PIL import Image

    x = np.asarray(Image.open(a).convert("RGB"), int)
    y = np.asarray(Image.open(b).convert("RGB"), int)
    if x.shape != y.shape:
        return -1, -1, -1
    d = np.abs(x - y).max(axis=2) > 12
    return int(d.sum()), int(d[CAPTION_ROWS:].sum()), int(d.size)


def main() -> int:
    prove = "--prove" in sys.argv
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed, so this check is skipped.")
        return 0
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed, so this check is skipped.")
        return 0

    shapes = papers()
    if shapes is None:
        print("the demo measurements are not here, so this check is skipped.")
        return 0

    # THE FIXTURE HAS TO BITE BEFORE ANY ANSWER FROM IT IS WORTH READING.
    #
    # If these shapes keep the same triangles at every fade, then "0 pixels
    # different at the ends" says nothing about replacing a triangle list --
    # the push would only ever have sent colours, and the strongest claim
    # this check makes would be untested. It happened: at the strength two
    # shapes are drawn at by default, every count was identical.
    full, at_zero = faces(shapes), faces(shapes, agree=0.0)
    if full == at_zero:
        print(f"  These shapes keep the same triangles whatever the fade "
              f"({full}), so this\n  run cannot say whether a triangle list "
              f"can be replaced — which is the\n  one thing it exists to "
              f"settle. Pick shapes that cross.")
        return 2
    print(f"  the ends do move geometry: {full} at full strength, "
          f"{at_zero} at nothing\n")

    if prove:
        print("  --prove: every push is given the arrays for a DIFFERENT "
              "fade than the\n  one the page is compared against. The "
              "pictures must stop matching.\n")

    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        where = pathlib.Path(tmp)
        full = a_page(where, "full", shapes)
        with sync_playwright() as play:
            browser = play.chromium.launch()
            print(f"  {'slider':20s} {'at':>6s}  {'sent':>4s}  "
                  f"{'the shapes':>14s}  {'the caption':>13s}")
            print("  " + "-" * 66)
            for label, which, value in WHERE:
                fade = {which: value}
                # THE MUTATION IS ON THE ARRAYS, NOT ON THE PICTURE. Sending a
                # neighbouring fade is exactly the fault this is for -- a push
                # that lands, reports success and draws the wrong thing.
                sent = dict(fade)
                if prove:
                    sent[which] = 0.85 if value < 0.8 else 0.2
                built = a_page(where, f"built-{which}-{value}", shapes, **fade)
                want = arrays(shapes, **sent)
                # PROVEN TO LAND. The mutation here is the DATA handed over,
                # which looks as though it cannot fail to apply -- and that is
                # exactly the assumption that let two other checks in this
                # tree run for weeks sabotaging nothing. If a neighbouring
                # value happens to produce the same arrays, --prove would be
                # comparing a picture with itself and calling that proof.
                if prove and want == arrays(shapes, **fade):
                    print(f"  THE MUTATION DID NOT LAND at {label} {value}: "
                          f"the arrays for a different\n  fade are identical "
                          f"to the right ones, so this run tested nothing.")
                    return 2
                live, did, _sat = shoot(browser, full,
                                        f"live-{which}-{value}",
                                        where, want=want)
                shot, _, _sat2 = shoot(browser, built,
                                       f"shot-{which}-{value}", where)
                everything, shapes_only, total = apart(live, shot)
                caption = everything - shapes_only
                print(f"  {label:20s} {value:>6.2f}  {str(did):>4s}  "
                      f"{shapes_only:>9,} px  {caption:>10,} px")
                if not did:
                    problems.append(
                        f"{label} at {value}: nothing was pushed at all — the "
                        f"picture cannot have been faded, whatever it looks "
                        f"like")
                elif shapes_only != 0:
                    problems.append(
                        f"{label} at {value}: the shapes drawn live and the "
                        f"shapes a rebuild draws differ by {shapes_only:,} "
                        f"pixels — a reader who lets go of the handle is "
                        f"handed a different picture from the one they chose")
                # THE CAPTION IS ALLOWED TO DIFFER AT AN END AND NOWHERE ELSE.
                # That is not a licence: it is the exact rule `_after_fade`
                # implements, and a caption that changed in the MIDDLE of a
                # slider would mean the window's rule is wrong and a reader
                # would be left with a sentence that does not match the
                # picture.
                elif caption and value not in (0.0, 1.0):
                    problems.append(
                        f"{label} at {value}: the caption differs by "
                        f"{caption:,} pixels somewhere that is not an end of "
                        f"the slider — the window only rebuilds at the ends, "
                        f"so this sentence would never reach the reader")

            # ---------------------------------------------------- and DETAIL
            #
            # A DIFFERENT KIND OF CHANGE, and that is why it is here rather
            # than in a check of its own. A fade leaves every point where it
            # is; detail REBUILDS the comparison, so every point moves, every
            # triangle is new, and the paper drawn beside it is re-cut against
            # a different boundary. If a push can carry that, it can carry
            # anything this window does.
            here = points(OPENED_AT)
            moved = {d: points(d) for d in DETAILS}
            names = [t["n"] for t in detail_arrays(OPENED_AT)]
            if len(set(names)) == len(names):
                print(f"\n  Every trace here has its own name ({names}), so "
                      f"this run cannot say\n  whether the ordered-list guard "
                      f"tells duplicates apart — which is the\n  only reason "
                      f"the push matches by position at all.")
                return 2
            if len(set(moved.values())) < len(moved):
                print(f"\n  Detail does not change how many points the "
                      f"picture holds ({moved}),\n  so this run cannot say "
                      f"whether the push carried them.")
                return 2
            repeats = len(names) - len(set(names))
            print(f"\n  detail moves the points: {moved}, opened at "
                  f"{OPENED_AT} ({here:,})")
            print(f"  and {len(names)} traces carry {repeats} repeated "
                  f"name(s), so position is the only way to tell them "
                  f"apart\n")
            print(f"  {'change':20s} {'at':>6s}  {'sent':>4s}  "
                  f"{'the shapes':>14s}  {'the caption':>13s}")
            print("  " + "-" * 66)
            opened = detail_page(where, OPENED_AT)
            for steps in DETAILS:
                sent = steps
                if prove:
                    # A NEIGHBOURING DETAIL, not a wild one: the fault this
                    # guards against is a push that lands, reports success and
                    # draws a picture close enough to pass a careless eye.
                    sent = 20 if steps != 20 else 29
                built = detail_page(where, steps)
                if prove and detail_arrays(sent) == detail_arrays(steps):
                    print(f"  THE MUTATION DID NOT LAND at detail {steps}: "
                          f"the arrays for {sent}\n  steps are identical to "
                          f"the right ones, so this run tested nothing.")
                    return 2
                live, did, _sat = shoot(browser, opened,
                                        f"live-detail-{steps}", where,
                                        want=detail_arrays(sent),
                                        script=PUSH_ALL)
                shot, _, _sat2 = shoot(browser, built,
                                       f"shot-detail-{steps}", where)
                everything, shapes_only, total = apart(live, shot)
                caption = everything - shapes_only
                print(f"  {'detail':20s} {steps:>6d}  {str(did):>4s}  "
                      f"{shapes_only:>9,} px  {caption:>10,} px")
                if not did:
                    problems.append(
                        f"detail at {steps}: the push was refused — the "
                        f"picture cannot have followed the handle, whatever "
                        f"it looks like")
                elif shapes_only != 0:
                    problems.append(
                        f"detail at {steps}: the shapes drawn live and the "
                        f"shapes a rebuild draws differ by {shapes_only:,} "
                        f"pixels — a reader who lets go of the handle is "
                        f"handed a different picture from the one they chose")

            # ------------------------------------------ and THE CROSS-SECTION
            #
            # The cheapest of the three to work out -- 7 ms, three traces, 363
            # points -- and the only one that moves the FRAME as well as what
            # is drawn in it. A cut is drawn to fill its picture, so the axes
            # run from -114.8 to 50.4 across at L* 30 and from -52.2 to 103.0
            # at L* 70, and the caption names the height. A push that sent the
            # outlines alone would draw the new cut inside the old frame, under
            # a sentence naming a lightness it is not at -- which looks like
            # the shape sliding sideways rather than the cut moving.
            flat = at_detail(20)
            frames = {L: cut_arrays(L, flat)[1].get("xaxis.range")
                      for L in CUTS}
            if len(set(map(str, frames.values()))) < len(frames):
                print(f"\n  These cuts share a frame ({frames}), so this run "
                      f"cannot say whether\n  the axes travelled with the "
                      f"outlines.")
                return 2
            print(f"\n  every height has its own frame, so the axes have to "
                  f"travel too\n")
            print(f"  {'change':20s} {'at':>6s}  {'sent':>4s}  "
                  f"{'the shapes':>14s}  {'the caption':>13s}")
            print("  " + "-" * 66)
            opened_cut = cut_page(where, CUT_AT, flat)
            for L in CUTS:
                sent = L
                if prove:
                    # THE NEXT HEIGHT UP THE SLIDER, not the far end: a cut one
                    # step away is the picture a careless check would accept.
                    sent = 35 if L != 35 else 50
                built = cut_page(where, L, flat)
                if prove and cut_arrays(sent, flat) == cut_arrays(L, flat):
                    print(f"  THE MUTATION DID NOT LAND at L* {L}: the arrays "
                          f"for L* {sent} are\n  identical to the right ones, "
                          f"so this run tested nothing.")
                    return 2
                live, did, sat = shoot(browser, opened_cut, f"live-cut-{L}",
                                       where, want=cut_arrays(sent, flat),
                                       script=PUSH_FLAT)
                shot, _, was = shoot(browser, built, f"shot-cut-{L}", where)
                everything, shapes_only, total = apart(live, shot)
                caption = everything - shapes_only
                # HALF A PIXEL IS NOT A WRONG PICTURE, and telling the two
                # apart is the difference between a check somebody trusts and
                # one they learn to ignore. The drawn area's own position is
                # asked for, so a picture that is merely STANDING somewhere
                # else can be named as that rather than reported as the shapes
                # being wrong. If it sits in the same place and the pixels
                # still differ, it IS the shapes, and that is a fault.
                # THE EXCUSE HAS TO BE NARROW OR IT EXCUSES EVERYTHING.
                #
                # Written as "the frame moved, so never mind", --prove came
                # back green with every height wrong: pushing a NEIGHBOURING
                # cut moves the frame too, so the excuse covered the very
                # fault it was meant to leave visible. So it now takes all
                # three: the same drawn arrays to four decimal places, the
                # same axis ranges, the same caption -- and only then is a
                # frame standing under a pixel to one side allowed to account
                # for the difference.
                (sat, live_drawn), (was, built_drawn) = sat, was
                identical = live_drawn == built_drawn
                slid = (sat and was
                        and abs(sat["x"] - was["x"]) < 1
                        and abs(sat["y"] - was["y"]) < 1
                        and (sat["x"], sat["y"]) != (was["x"], was["y"]))
                moved_over = identical and slid
                shifted = ("" if not (sat and was)
                           or (sat["x"], sat["y"]) == (was["x"], was["y"])
                           else f"  ← the whole picture sits "
                                f"{abs(sat['x'] - was['x']):.1f} px across"
                                + ("" if identical
                                   else ", AND what is drawn differs"))
                print(f"  {'a cross-section':20s} {L:>6d}  {str(did):>4s}  "
                      f"{shapes_only:>9,} px  {caption:>10,} px{shifted}")
                if not did:
                    problems.append(
                        f"the cut at L* {L}: the push was refused — the "
                        f"picture cannot have followed the handle")
                elif (shapes_only or caption) and not moved_over:
                    problems.append(
                        f"the cut at L* {L}: what is drawn live and what a "
                        f"rebuild draws differ by {shapes_only:,} pixels in "
                        f"the picture and {caption:,} in the caption, in the "
                        f"same frame — the reader is not looking at the "
                        f"height they chose")
            browser.close()

    print()
    if prove:
        if problems:
            print("  With the wrong arrays pushed, the pictures stopped "
                  "matching, as they must.\n  The check can see.")
            return 0
        print("  THE PICTURES STILL MATCHED with the wrong fade pushed. This "
              "check is blind.")
        return 1
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: a change pushed into the picture already on screen draws, "
          "pixel for\n  pixel, what a rebuild would have drawn — both fades "
          "at both ends and in\n  between, detail across four resolutions "
          "with every point moved, and the\n  cross-section at five heights."
          "\n\n  Two things differ and both are named rather than waved "
          "through: the caption\n  at an end of a fade, which is the "
          "sentence the window rebuilds to fetch,\n  and a cut whose widest "
          "tick label changes width, which stands half a pixel\n  to one "
          "side because a margin is measured when a page is drawn and is not\n"
          "  measured again the same way in place. Every number that decides "
          "the picture\n  is identical there — the arrays to four decimals, "
          "both axis ranges, the\n  caption — which is what that excuse "
          "requires before it will apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
