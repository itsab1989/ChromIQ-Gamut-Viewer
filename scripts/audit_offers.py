"""Does the export dialog offer exactly what the page it writes can do?

BOTH DIRECTIONS, AND THE SECOND IS THE ONE NOBODY CHECKS. Asked for in as many
words: "the export dialog should only allow to choose control options for the
webviewer navigation of the exported variant that are applicable for what is
exported", and then -- the half that makes it an audit rather than a tidy-up --
"but everything that is applicable should be given as an option - which i think
would require an audit to make sure nothing is missed in both ways".

  OVER-OFFERED   a switch the dialog hands out that the page cannot honour.
                 The reader ticks it and the file arrives without it.
  UNDER-OFFERED  a switch the dialog withholds that the page WOULD have
                 honoured. Nobody learns the control exists, and nothing looks
                 wrong -- which is why it needs a machine to find it.

HOW IT KNOWS WHAT A PAGE CAN DO: it writes the page with everything offered,
OPENS IT IN A BROWSER, and reads which controls the page actually built. The
strip is assembled at load time by the page's own script, so nothing in the
file says what a reader will get -- reading the HTML would be a real
measurement of the wrong thing. Two of those in one evening is enough.

WRITTEN THE WAY THE WINDOW WRITES THEM, which is the other half of measuring
the right thing: with the viewer carried inside (fetched, and offline, the page
shows its "it never arrived" fallback and nothing else -- the first version of
this audit measured that and reported 21 controls missing), with the notes the
Save dialog offers, and with the two-shape split that gives the fade something
to fade between.

    python scripts/audit_offers.py

Exit code 1 if anything is offered wrongly in either direction.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_offers"]

import numpy as np                                            # noqa: E402

#: Which control in the built page proves a switch was honoured, by the
#: `data-cq` name the page puts on it. Measured in a browser rather than read
#: out of the source: several switches build controls whose names are nothing
#: like the switch's own -- "move" builds left/right/up/down, "reset" builds
#: "home", "picture" builds "shot".
MARKERS = {
    "play": ("play",),
    "speed": ("turn-faster", "turn-slower"),
    "speed_each": ("tilt-faster", "tilt-slower"),
    "sweep": ("turn-wider", "turn-narrower"),
    "lr": ("lr",),
    "ud": ("ud",),
    "cut": ("cut-up", "cut-down", "cut-at"),
    "zoom": ("in", "out"),
    "move": ("left", "right"),
    "glide": ("glide",),
    "views": ("look-front", "look-above"),
    "reset": ("home",),
    "agree": ("agree-at", "differ-at"),
    "opacity": ("shape-fainter-0", "shape-stronger-0"),
    "wires": ("shape-wires-0",),
    "grey": ("shape-grey-0",),
    "notes": ("notes",),
    "grid": ("grid",),
    "labels": ("labels",),
    "key": ("key",),
    "appearance": ("appearance",),
    "picture": ("shot",),
}

#: Switches that build no control of their own, with the reason. They are not
#: judged here -- an audit that reports a fault it cannot see is worse than one
#: that says which questions it did not ask.
NOT_A_BUTTON = {
    "fullscreen": ("the page asks the browser whether it CAN go full screen "
                   "and leaves the button out when it cannot; a headless "
                   "browser always says no, so this audit can never see it"),
    "remember": ("it stores what the reader chose, rather than drawing a "
                 "control -- there is nothing in the page to look for"),
}


def blob(seed, scale=1.0):
    """A closed surface standing in for a measured paper."""
    from gamutview import build_gamut

    rng = np.random.default_rng(seed)
    points = rng.normal(size=(80, 3)) * np.array([12.0, 20.0, 20.0]) * scale
    points[:, 0] += 50.0
    return build_gamut(points, input_space="lab", space="lab")


NOTES = "Matte-paper holds 812,144 units of colour."


def write_them(folder):
    """Every kind of page this application writes, with everything offered."""
    import ti3gamut

    every = {name: True for name in list(MARKERS) + list(NOT_A_BUTTON)}
    spin = {"on": True, "mode": "turn", "speed": 6, "sweep": 60,
            "tilt_mode": "swing", "tilt_speed": 4, "tilt_sweep": 30,
            "glide": True}
    one = [("paper-1", blob(1))]
    two = one + [("paper-2", blob(2, 0.75))]
    rng = np.random.default_rng(11)
    n = 300
    lab = np.column_stack([rng.uniform(20, 92, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    de = rng.uniform(0.4, 4.0, n)

    made = []
    ti3gamut.write_html(one, folder / "one.html", "one shape",
                        carry_viewer=True, controls=True, offer=every,
                        spin=spin, notes=NOTES)
    made.append(("one shape", "one.html",
                 {"two_shapes": False, "surfaces": True, "flat": False,
                  "camera": True, "fade": False}))
    ti3gamut.write_html(two, folder / "two.html", "two shapes",
                        carry_viewer=True, controls=True, offer=every,
                        spin=spin, notes=NOTES, split=True)
    made.append(("two shapes", "two.html",
                 {"two_shapes": True, "surfaces": True, "flat": False,
                  "camera": True, "fade": True}))
    ti3gamut.write_html([], folder / "cloud.html", "a drift cloud",
                        carry_viewer=True, controls=True, offer=every,
                        spin=spin, notes=NOTES,
                        drift=(lab, de, "2019 → 2024", None, True))
    made.append(("a drift cloud, no shapes", "cloud.html",
                 {"two_shapes": False, "surfaces": False, "flat": False,
                  "camera": True, "fade": False}))
    ti3gamut.write_slice_html(two, folder / "flat.html", 50.0, "a cut",
                              mode="dark", controls=True, offer=every,
                              notes=NOTES)
    made.append(("a cross-section", "flat.html",
                 {"two_shapes": True, "surfaces": True, "flat": True,
                  "camera": False, "fade": False}))
    return made


ASK = """
(function () {
  var seen = [];
  document.querySelectorAll("[data-cq]").forEach(function (e) {
    seen.push(e.getAttribute("data-cq"));
  });
  return JSON.stringify(seen);
})()
"""
OPEN = """(function(){var m=document.querySelector('[data-cq="more"]');
  if (m) { m.click(); return "opened"; } return "no panel";})()"""


def read_controls(folder, made):
    """Open each page in a browser and list the controls it really built."""
    from PyQt6.QtCore import QTimer, QUrl
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    app = QApplication.instance() or QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(1200, 820)
    view.show()
    left, found = list(made), {}

    def nxt():
        if not left:
            app.quit()
            return
        name, page, _shows = left.pop(0)
        view.load(QUrl.fromLocalFile(str(folder / page)))

        def got(raw):
            found[name] = set(json.loads(raw))
            nxt()

        def read(_r):
            # A LATER TICK THAN THE CLICK. The panel is built the first time
            # it is opened, so reading in the same block as the click reports
            # the bar and none of the panel -- which called every shape
            # control missing on every 3D page.
            QTimer.singleShot(1400, lambda: view.page().runJavaScript(ASK, got))

        QTimer.singleShot(7000, lambda: view.page().runJavaScript(OPEN, read))

    QTimer.singleShot(400, nxt)
    QTimer.singleShot(180_000, app.quit)
    app.exec()
    view.deleteLater()
    return found


def main() -> int:
    import gamut_app

    needs = gamut_app.WebPageDialog.NEEDS
    every = set(MARKERS)
    folder = pathlib.Path(tempfile.mkdtemp(prefix="offers-"))
    problems, seen_anywhere = [], set()
    try:
        made = write_them(folder)
        built = read_controls(folder, made)
        for name, _page, shows in made:
            has = built.get(name, set())
            can = {switch for switch, marks in MARKERS.items()
                   if any(mark in has for mark in marks)}
            seen_anywhere |= can
            offered = {switch for switch in every
                       if needs.get(switch) is None
                       or shows.get(needs[switch], False)}
            over, under = sorted(offered - can), sorted(can - offered)
            print(f"\n{name}")
            print(f"   built {len(has)} controls; can honour {len(can)} of "
                  f"{len(every)} switches; the dialog offers {len(offered)}")
            for switch in over:
                problems.append(f"[over]  {name}: '{switch}' is offered and "
                                f"the page does not build it")
            for switch in under:
                problems.append(f"[under] {name}: the page builds '{switch}' "
                                f"and the dialog does not offer it")
            if not over and not under:
                print("   exactly what it can do, in both directions")
        for switch in sorted(every - seen_anywhere):
            problems.append(
                f"[gone]  '{switch}' was built by no page at all — either the "
                f"name in the dialog and the name in the writer have drifted "
                f"apart, or this audit's marker for it is stale")
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    print("\nnot judged here, and why:")
    for switch, why in NOT_A_BUTTON.items():
        print(f"   {switch}: {why}")

    print()
    if problems:
        for line in sorted(problems):
            print("  " + line)
        print(f"\n{len(problems)} problem(s).")
        return 1
    print("  Clean: every page offers exactly the controls it can honour.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
