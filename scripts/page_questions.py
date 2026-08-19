"""The questions a saved page is asked, wherever it is opened.

ONE COPY, TWO AUDITS. `audit_the_page_at_any_size.py` asks these in
QtWebEngine, which is Chromium and therefore speaks for Chrome and Edge.
`audit_other_engines.py` asks them in real Gecko (Firefox), real WebKit
(Safari's engine) and stock Chromium. Two audits with two private copies of
the questions is how one of them quietly starts asking something easier: the
JS below and the judgment of its answers live here so both are always asking
the same thing.

Nothing in this module touches Qt or Playwright — it is questions and
judgment only, so either audit can import it without dragging in the other's
machinery.
"""
from __future__ import annotations

#: The shapes of window a reader actually has. The last is a phone upright,
#: which is the one nobody tests and everybody uses.
SIZES = [(1680, 1000), (1280, 860), (1024, 700), (820, 900), (620, 800),
         (390, 780)]

ASK = """(function () {
  var d = document.documentElement, b = document.body;
  var out = {
    // WHETHER THIS IS THE PAGE AT ALL. Everything below reads as clean on a
    // blank document, so the first thing asked is whether anything arrived.
    here: (document.title || '') + '|' + (b ? b.innerHTML.length : 0),
    w: window.innerWidth, h: window.innerHeight,
    sideways: Math.max(d.scrollWidth, b ? b.scrollWidth : 0) - d.clientWidth,
    canvases: 0, gl: 0, glw: 0, past: [], strip: null
  };
  // AND HOW MUCH IS DRAWN IN SVG, because not every page is a 3D scene: the
  // run pages are LINE GRAPHS, which Plotly draws as SVG paths and which have
  // no canvas at all. Demanding a canvas of those reported six faults that
  // were the check's own assumption.
  var paths = document.querySelectorAll('svg path, svg .point, svg .trace');
  out.svg = paths.length;
  var cs = document.getElementsByTagName('canvas');
  out.canvases = cs.length;
  for (var i = 0; i < cs.length; i++) {
    var g = null;
    try { g = cs[i].getContext('webgl2') || cs[i].getContext('webgl'); }
    catch (e) {}
    if (g) { out.gl++; out.glw = Math.max(out.glw, g.drawingBufferWidth); }
  }
  var all = document.querySelectorAll('button, a, .cq-controls, .modebar');
  for (var j = 0; j < all.length; j++) {
    var r = all[j].getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > d.clientWidth + 1 || r.left < -1) {
      out.past.push((all[j].textContent || all[j].className || 'element')
                    .trim().slice(0, 24) + ' @' + Math.round(r.left) + '..' +
                    Math.round(r.right));
    }
  }
  return JSON.stringify(out);
})()"""


def judge(got: dict, where: str, expects_scene: bool = True) -> list:
    """What is wrong with one page at one size, as a list of sentences.

    *expects_scene* is False for pages that never drew anything — the
    showcase index is prose and pictures, and demanding a WebGL canvas of it
    would report the audit's own assumption as the page's fault.
    """
    problems = []
    # A PAGE THAT DID NOT ARRIVE CANNOT BE AUDITED, and must never be
    # reported as though it had been.
    body = int((got.get("here") or "|0").split("|")[-1] or 0)
    if body < 500:
        return [f"{where} the page did not load at all ({body} bytes of "
                f"body) — nothing below this was measured"]
    if got["sideways"] > 1:
        problems.append(f"{where} scrolls SIDEWAYS by {got['sideways']}px")
    for item in got["past"]:
        problems.append(f"{where} past the edge: {item}")
    if expects_scene:
        drawn_in_gl = (got["canvases"] >= 1 and got["gl"] >= 1
                       and got["glw"] >= 1)
        drawn_in_svg = got.get("svg", 0) >= 20
        if got["canvases"] >= 1 and not drawn_in_gl:
            problems.append(f"{where} a canvas with no live WebGL context")
        elif not drawn_in_gl and not drawn_in_svg:
            problems.append(
                f"{where} nothing is drawn — no WebGL canvas and only "
                f"{got.get('svg', 0)} SVG marks")
    return problems


def said(got: dict) -> str:
    """The one-line reading of a page's answers, for the audit's own log."""
    return (f"{got['canvases']} canvas, gl {got['gl']}, "
            f"svg {got.get('svg', 0)}, sideways {got['sideways']}px, "
            f"{len(got['past'])} past the edge")
