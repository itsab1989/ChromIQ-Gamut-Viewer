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
    canvases: 0, gl: 0, glw: 0, past: [], unreachable: [],
    seen: 0, strip: null
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
  // THE READER'S OWN STRIP, BY THE NAME IT REALLY HAS. This asked for
  // `.cq-controls`, which matches NOTHING in any page this project writes --
  // the strip is `.cq-spin-bar` and the opened controls are `.cq-spin-panel`.
  // Its buttons were reached through the plain `button` selector, so the
  // question looked answered; the strip's own box was never measured.
  var all = document.querySelectorAll(
      'button, a, .cq-spin-bar, .cq-spin-panel, .modebar');
  out.seen = all.length;
  // AND EACH SELECTOR'S OWN TALLY. One dead name among four live ones is
  // invisible in a total -- which is how `.cq-controls` asked about the
  // reader's strip for months while matching nothing at all.
  out.counts = {};
  var names = ['button', 'a', '.cq-spin-bar', '.cq-spin-panel', '.modebar'];
  for (var k = 0; k < names.length; k++) {
    out.counts[names[k]] = document.querySelectorAll(names[k]).length;
  }
  var scrollY = window.pageYOffset || d.scrollTop || 0;
  var reach = Math.max(d.scrollHeight, b ? b.scrollHeight : 0);
  for (var j = 0; j < all.length; j++) {
    var el = all[j], r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    var name = (el.textContent || el.className || 'element').trim().slice(0, 24);
    if (r.right > d.clientWidth + 1 || r.left < -1) {
      out.past.push(name + ' @' + Math.round(r.left) + '..' + Math.round(r.right));
    }
    // AND WHETHER IT CAN BE REACHED AT ALL, which is a different question
    // from whether it is on screen: a page is ALLOWED to be taller than the
    // window, so anything below the fold is fine if scrolling gets you there.
    // Two things are not. A fixed element does not move when you scroll, so
    // one below the window is gone for good -- which is exactly what was
    // reported from an iPhone, the strip carried off the frame with no way
    // back. And anything past the end of everything you can scroll to is
    // unreachable however hard you try.
    var pinned = false;
    try { pinned = getComputedStyle(el).position === 'fixed'; } catch (e) {}
    var out_of_view = r.bottom > d.clientHeight + 1 || r.top < -1;
    var out_of_reach = r.bottom + scrollY > reach + 1 || r.top + scrollY < -1;
    if ((pinned && out_of_view) || (!pinned && out_of_reach)) {
      out.unreachable.push(name + ' at y ' + Math.round(r.top) + '..' +
                           Math.round(r.bottom) + (pinned ? ' (pinned, ' : ' (') +
                           'window ' + d.clientHeight + ', scrolls to ' +
                           Math.round(reach) + ')');
    }
  }
  var bar = document.querySelector('.cq-spin-bar');
  if (bar) {
    var br = bar.getBoundingClientRect();
    out.strip = Math.round(br.top) + '..' + Math.round(br.bottom) + ' of ' +
                d.clientHeight;
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
    # OFF THE BOTTOM COUNTS TOO, and only this asks it. A page is allowed to
    # be taller than the window; what it may not do is put a control where no
    # amount of scrolling reaches it.
    for item in got.get("unreachable", []):
        problems.append(f"{where} out of reach: {item}")
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
            f"{len(got['past'])} past the edge, "
            f"{len(got.get('unreachable', []))} out of reach, "
            f"strip {got.get('strip') or '(none)'}, "
            f"{got.get('seen', 0)} measured")


def rotted(readings: list) -> list:
    """Which of the selectors above matched NOTHING in a whole run.

    A page is allowed to offer no controls — the run pages are line graphs
    with no strip, no buttons and the modebar turned off, and demanding one
    of those reported 21 faults that were this check's own assumption. What
    is never allowed is a name that matches nothing ANYWHERE: that is a
    question which cannot see the thing it asks about, and it reads exactly
    like a run that found nothing wrong. `.cq-controls` was such a name.

    *readings* is every answer collected in the run. Only the selectors that
    must exist somewhere are demanded: `.cq-spin-panel` is built when the
    reader opens the controls and may honestly be absent from every page.
    """
    must = ["button", ".cq-spin-bar"]
    totals = {name: 0 for name in must}
    for got in readings:
        for name in must:
            totals[name] += (got.get("counts") or {}).get(name, 0)
    if not readings:
        return ["nothing was measured at all — no page answered"]
    return [f"the selector {name!r} matched nothing in any of "
            f"{len(readings)} page state(s) — this question cannot see what "
            f"it claims to ask about" for name in must if totals[name] == 0]
