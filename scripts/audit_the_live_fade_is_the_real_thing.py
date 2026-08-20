"""A fade pushed into the picture on screen draws what a rebuild would draw.

    ../gv-venv/bin/python scripts/audit_the_live_fade_is_the_real_thing.py
    ../gv-venv/bin/python scripts/audit_the_live_fade_is_the_real_thing.py --prove

WHY THIS EXISTS. "Where they agree" and "Where they differ" used to wait for
the handle to be let go, and then rebuilt the whole page -- about a second of
black. Reported twice and then as a rule: "should be live", "btw all sliders
should work this way". They are live now, and the way they are live is that
the window works out what `build_figure` would have drawn and pushes those
arrays straight into the scene that is already up.

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


def shoot(browser, path, tag, out_dir, want=None):
    tab = browser.new_page(viewport={"width": 1200, "height": 820})
    tab.goto(path.resolve().as_uri())
    tab.wait_for_selector(".plotly-graph-div", timeout=40000)
    tab.wait_for_timeout(6000)
    did = None
    if want is not None:
        did = tab.evaluate(PUSH, want)
        tab.wait_for_timeout(3000)
    shot = out_dir / f"{tag}.png"
    tab.locator(".plotly-graph-div").first.screenshot(path=str(shot))
    tab.close()
    return shot, did


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
                live, did = shoot(browser, full, f"live-{which}-{value}",
                                  where, want=want)
                shot, _ = shoot(browser, built, f"shot-{which}-{value}", where)
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
    print("  Clean: the shapes drawn by a fade pushed into the picture on "
          "screen are,\n  pixel for pixel, the shapes a rebuild would have "
          "drawn — at both ends and\n  in between, for both sliders. Only the "
          "caption differs, only at an end,\n  and that is the sentence the "
          "window rebuilds to fetch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
