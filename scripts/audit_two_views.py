"""A page holding both views offers each one only what it can honour.

    ../gv-venv/bin/python scripts/audit_two_views.py

WHY THIS EXISTS. Asked for from the window: a switch in the saved page between
the shells and the sliced view, and — the half that matters — "the other
controls would then have to update accordingly so the user can manipulate each
view in a way that makes sense for it".

"Which controls make sense here" is exactly where an inconsistency hides. A
control offered where it cannot act is a control that lies, and this project
has already fixed that fault twice in the window itself: the split tick that
stayed lit while the destination colouring was in charge, and four colourings
that could be chosen while the split made them do nothing.

WHAT MUST BE TRUE, each with its failure direction:

  the shells offer the turning controls   they are what a camera is for; a
                                          page that withholds them has lost
                                          something the reader had;
  the cut offers none of them             a cross-section has no camera at
                                          all, so play, speed, faster and
                                          slower cannot act — offering them
                                          is the lie;
  both offer what belongs to both         zoom, "back to the start" and the
                                          panel are about the picture, not
                                          about which kind it is;
  switching back restores                 a switch that only works once is a
                                          trap, and the reader is left in the
                                          view they did not choose;
  there is exactly one strip              rebuilding without removing leaves
                                          two, and the second is stale.

MEASURED IN BOTH ENGINES, because the strip is rebuilt by script and the two
engines have disagreed before about when a layout is readable.

THE PAGE IS BUILT HERE, in a temporary directory, from a blob of measurements
rather than a file on disk: the two-view writer is not yet reachable from the
export dialog, so there is no saved page to point at. When it is, this should
be pointed at a real one.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

#: What only a camera can honour. A flat cut has none.
TURNING = {"play", "speed", "faster", "slower", "lr", "ud", "sweep"}
#: What belongs to any picture at all.
EITHER = {"home", "in", "out", "more"}

#: Where the cut says it is sitting, and where the page was saved at.
WHERE = """(function () {
  var s = window.cqSettings || {}, c = s.cuts || null;
  var says = document.querySelector('[data-cq="cut-at"]');
  return JSON.stringify({
    saved: c ? Math.round(c.levels[c.at || 0]) : null,
    says: says ? says.textContent.replace(/[^0-9-]/g, "") : null});
})()"""

STRIP = """(function () {
  var out = [];
  document.querySelectorAll('.cq-spin-bar [data-cq], .cq-spin-panel [data-cq]')
    .forEach(function (b) {
      if (b.getBoundingClientRect().width > 0)
        out.push(b.getAttribute('data-cq'));
    });
  return {controls: out, bars: document.querySelectorAll('.cq-spin-bar').length,
          views: document.querySelectorAll('.cq-view').length,
          shown: [].slice.call(document.querySelectorAll('.cq-view'))
                   .map(function (v) { return v.hidden ? 0 : 1; })};
})()"""


def a_shape():
    """The shape these pages are drawn from."""
    import numpy as np
    import ti3gamut
    from gamutview import build_gamut

    # THE REAL MEASUREMENT WHERE THERE IS ONE. A made-up ball gave this page
    # a lightness range so narrow that the height it was saved at and the
    # bottom of the range rounded to the same number -- so the check could not
    # tell them apart, and a mutation that genuinely broke the saved height
    # (proved on the demo paper: L* 50 became L* 8) slipped past it.
    demo = HERE.parent / "demo" / "Glossy-paper.ti3"
    if demo.is_file():
        measured = ti3gamut.read_measurement(demo)
        return build_gamut(measured.lab, input_space="lab")

    rng = np.random.default_rng(9)
    q = rng.normal(size=(700, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    q *= rng.uniform(0.5, 1, size=(700, 1)) ** (1 / 3)
    lab = q * np.array([38, 52, 50])
    lab[:, 0] = np.clip(lab[:, 0] * 0.6 + 50, 4, 96)
    # SAYING WHAT THE NUMBERS ARE. `build_gamut` reads its input as XYZ unless
    # told otherwise, so handing it Lab silently builds a shape in the wrong
    # space -- corners at L* -71,327, no rings, and `slice_levels` returning
    # None, which is what made this page's cut unslidable and looked like a
    # fault in the writer.
    return build_gamut(lab, input_space="lab")


def a_page(where: pathlib.Path):
    """One page carrying the shells and a cut, written by the real writer."""
    import ti3gamut

    shape = a_shape()

    scene = ti3gamut.build_figure([("a paper", shape)], "Measured gamut")

    # THE CUT IS GIVEN SOMETHING TO SLIDE THROUGH, which was the gap this
    # page was written with and which docs/DESIGN-two-views-in-one-page.md
    # recorded: a reader could switch to the cross-section and then not move
    # it. The recipe is the one the two-pane cut page already uses -- the
    # levels worked out once, the figure built `slidable` over their shared
    # extent, and the levels carried into the page's settings, where the
    # control strip looks for `settings.cuts`.
    at = 50.0
    cuts = ti3gamut.slice_levels([("a paper", shape)], include=at)
    if cuts is not None:
        cuts["title"] = ""
        cuts["at"] = min(range(len(cuts["levels"])),
                         key=lambda i: abs(cuts["levels"][i] - at))
    cut = ti3gamut.build_slice_figure(
        [("a paper", shape)], at, "A cut at L* 50",
        extent=(cuts["extent"] if cuts else None),
        slidable=cuts is not None)
    out = where / "both.html"
    ti3gamut.write_two_views_html(
        [("The shells", scene), ("A cut through it", cut)], out,
        spin={"on": False, "cuts": cuts}, controls=True,
        offer={"appearance": True, "camera": True})
    return out


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed, so this check is skipped.\n"
              "  pip install playwright && python -m playwright install "
              "webkit chromium")
        return 0

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        page = a_page(pathlib.Path(tmp))
        print(f"  a page with both views: {page.stat().st_size // 1024} kB")

        with sync_playwright() as play:
            try:
                engines = {n: getattr(play, n).launch()
                           for n in ("chromium", "webkit")}
            except Exception as why:                     # noqa: BLE001
                print(f"  no browser, so this check is skipped: {why}")
                return 0

            for name, browser in engines.items():
                tab = browser.new_page(viewport={"width": 1100, "height": 900})
                tab.goto(page.resolve().as_uri())
                tab.wait_for_timeout(7000)

                seen = {}
                for step, label in ((0, "the shells"), (1, "the cut"),
                                    (0, "the shells again")):
                    tab.locator('button[data-cq="view"]').nth(step).click()
                    tab.wait_for_timeout(2500)
                    got = tab.evaluate(STRIP)
                    seen[label] = got
                    offered = set(got["controls"])
                    print(f"  {name:9s} {label:18s} "
                          f"{' '.join(sorted(offered)) or '(nothing)'}")
                    if got["bars"] != 1:
                        problems.append(
                            f"{name}, {label}: {got['bars']} strips on screen "
                            f"— a rebuilt strip must replace the old one")
                    if got["views"] != 2:
                        problems.append(f"{name}: {got['views']} views, wanted 2")
                    missing = EITHER - offered
                    if missing:
                        problems.append(
                            f"{name}, {label}: does not offer "
                            f"{' '.join(sorted(missing))}, which any picture "
                            f"can honour")

                shells = set(seen["the shells"]["controls"])
                cut = set(seen["the cut"]["controls"])
                again = set(seen["the shells again"]["controls"])

                if not (TURNING & shells):
                    problems.append(
                        f"{name}: the shells offer none of the turning "
                        f"controls, which is what a camera is for")
                # WHERE THE CUT OPENS IS CHECKED ELSEWHERE, and it had to
                # be. A rule for it here could not be made to fail even with
                # the fault deliberately restored: this page's invented shape
                # has a lightness range narrow enough that the saved height
                # and the bottom of the range round to the same number. It
                # lives in audit_the_cut_opens_where_it_was_saved.py, on the
                # demo paper, where the two are eight and fifty.

                # AND THE CUT MUST OFFER THE ONE CONTROL THAT IS ITS OWN.
                # Switching to a cross-section that cannot be moved is the
                # half of "manipulate each view in a way that makes sense for
                # it" that this page was asked for.
                if not ({"cut", "cut-at", "cut-up", "cut-down"} & cut):
                    problems.append(
                        f"{name}: the cut offers nothing to move it with — a "
                        f"reader can switch to the cross-section and is then "
                        f"stuck at whichever lightness it was saved at")
                # AND THE MIRROR OF IT, which this audit did not ask and
                # should have. Giving the cut its levels put the lightness
                # controls in the strip for BOTH views -- the shells offered
                # cut, cut-at, cut-up and cut-down, none of which a
                # three-dimensional scene can honour. That is the same lie
                # the turning controls would be on a flat cut, in the other
                # direction, and it was introduced by the very change that
                # cured the cut's missing slider.
                loose = {"cut", "cut-at", "cut-up", "cut-down"} & shells
                if loose:
                    problems.append(
                        f"{name}: the shells offer {' '.join(sorted(loose))} "
                        f"— a scene has no cross-section to move, so these "
                        f"cannot act there")
                stranded = TURNING & cut
                if stranded:
                    problems.append(
                        f"{name}: the cut offers {' '.join(sorted(stranded))} "
                        f"— a cross-section has no camera, so they cannot act")
                if shells != again:
                    problems.append(
                        f"{name}: switching back did not restore the controls "
                        f"({' '.join(sorted(shells ^ again))} differ)")
                if seen["the cut"]["shown"] != [0, 1]:
                    problems.append(
                        f"{name}: pressing the second button did not show the "
                        f"second view ({seen['the cut']['shown']})")
                tab.close()
            for browser in engines.values():
                browser.close()

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: each view offers what it can honour and nothing it cannot, "
          "the switch\n  goes both ways, and there is one strip throughout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
