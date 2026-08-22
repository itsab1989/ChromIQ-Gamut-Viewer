"""The depth fix, proved on a real page in a real browser.

EVERY OTHER CHECK ON THIS IS ABOUT THE SHAPE OF THE SCRIPT — that it parses,
that its fit cannot clip, that its arming survives. None of them would notice
the one failure that matters most in a shipped bundle: the drawing library
renaming something the script reaches for. `glplot`, `aspect`, `onrender` and
`plotly_afterplot` are not a documented interface. If a future plotly moves
any of them the script returns quietly, the page draws exactly as before, and
the only symptom is the hatching coming back.

So this opens a page the way a reader would and asks the page itself whether
the fix took: is our handler on `onrender`, and are the planes something
other than the library's own 0.01 and 1000.

⚠ IT USES THE VIEWER INLINED IN THE PAGE, so it needs no network. Skips, with
a reason, when playwright or its browser is not installed.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"

try:
    from playwright.sync_api import sync_playwright
except Exception:                                            # noqa: BLE001
    sync_playwright = None

_ASK = """() => {
  const gd = document.querySelector('.js-plotly-plot');
  if (!gd || !gd._fullLayout) {
    return {drawn: false,
            says: (document.body.innerText || '').trim().slice(0, 160)};
  }
  const keys = Object.keys(gd._fullLayout).filter(k => k.indexOf('scene') === 0);
  if (!keys.length) return {drawn: false, says: 'no scene in the layout'};
  const gl = gd._fullLayout[keys[0]]._scene.glplot;
  if (!gl) return {drawn: false, says: 'a scene with no glplot'};
  return {drawn: true,
          armed: !!(gl.onrender && gl.onrender.__cqDepth),
          zNear: gl.zNear, zFar: gl.zFar,
          hasAspect: Array.isArray(gl.aspect) && gl.aspect.length === 3,
          bits: gl.gl ? gl.gl.getParameter(gl.gl.DEPTH_BITS) : null};
}"""


@pytest.mark.skipif(sync_playwright is None, reason="playwright is not installed")
def test_a_page_a_reader_opens_really_gets_the_fix(tmp_path):
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut
    paper_file = _DEMO / "Glossy-paper.ti3"
    if not paper_file.is_file():
        pytest.skip("no demo paper to draw")
    paper = build_gamut(ti3gamut.read_measurement(paper_file).lab,
                        input_space="lab")
    srgb = reference_gamut("sRGB", steps=16)
    out = tmp_path / "page.html"
    ti3gamut._LAST_CUT = None
    ti3gamut._LAST_CAP = None
    ti3gamut.write_html([("Glossy-paper", paper), ("sRGB", srgb)], out,
                        "armed?", agree=0.45, split=True, cap=True,
                        styles=["solid", "solid"], opacity=1.0,
                        carry_viewer=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 900, "height": 640})
            page.goto(out.resolve().as_uri())
            got = None
            for _ in range(6):
                page.wait_for_timeout(2500)
                got = page.evaluate(_ASK)
                if got.get("drawn"):
                    break
            browser.close()
    except Exception as exc:                                 # noqa: BLE001
        pytest.skip(f"no browser to open the page with: {exc}")
    assert got and got.get("drawn"), (
        f"the page never drew anything, and it says: "
        f"{(got or {}).get('says', '(nothing)')!r}")
    assert got["hasAspect"], (
        "the scene has no `aspect` — the drawing library has moved what the "
        "depth script reaches for, and the script is now doing nothing")
    assert got["armed"], (
        f"the page drew but our handler is not on `onrender`: {json.dumps(got)}")
    assert got["zNear"] != 0.01 and got["zFar"] != 1000, (
        f"the planes are still the library's own defaults, so nothing was "
        f"fitted: {json.dumps(got)}")
    assert 0 < got["zNear"] < got["zFar"] < 50, (
        f"the fitted planes are not a sane range: {json.dumps(got)}")
