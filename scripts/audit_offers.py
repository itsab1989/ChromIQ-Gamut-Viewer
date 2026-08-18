"""Does the export dialog offer exactly what the page it is writing can do?

BOTH DIRECTIONS, AND THE SECOND ONE IS THE ONE NOBODY CHECKS. Asked for in as
many words: "the export dialog should only allow to choose control options for
the webviewer navigation of the exported variant that are applicable for what
is exported", and then -- the half that makes it an audit rather than a tidy-up
-- "but everything that is applicable should be given as an option - which i
think would require an audit to make sure nothing is missed in both ways".

So this asks two questions of every kind of page this application can write:

  OVER-OFFERED  a switch the dialog hands out that the page cannot honour.
                The reader ticks it, and the file arrives without it.
  UNDER-OFFERED a switch the dialog withholds that the page WOULD have
                honoured. The reader never learns the control exists, and this
                is the failure nobody notices, because nothing looks wrong.

HOW IT KNOWS WHAT A PAGE CAN DO: it writes the page with EVERYTHING offered
and reads back which controls actually landed in it -- the `data-cq="…"`
markers the writer puts on each one. That is the page's own answer rather than
a second list to keep in step, which is what this project keeps being bitten
by. See the note in gamut_app.WebPageDialog.NEEDS.

    python scripts/audit_offers.py

Exit code 1 if anything is offered wrongly in either direction, so it can gate
a release.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_offers"]

import numpy as np                                            # noqa: E402

#: Which marker in the written page proves a switch was honoured. A switch
#: whose control cannot be found in ANY page is reported too: it means the
#: name in the dialog and the name in the writer have drifted apart.
MARKERS = {
    "play": ('data-cq="play"',),
    "speed": ('data-cq="speed"',),
    "speed_each": ('data-cq="speed-lr"', 'data-cq="speed-ud"'),
    "sweep": ('data-cq="sweep"', 'data-cq="sweep-lr"'),
    "lr": ('data-cq="lr"',),
    "ud": ('data-cq="ud"',),
    "cut": ('data-cq="cut-at"', 'data-cq="cut"'),
    "zoom": ('data-cq="zoom"',),
    "move": ('data-cq="move"',),
    "glide": ('data-cq="glide"',),
    "views": ('data-cq="look-front"',),
    "reset": ('data-cq="reset"',),
    "fullscreen": ('data-cq="fullscreen"',),
    "agree": ('data-cq="agree-at"', 'data-cq="differ-at"'),
    "opacity": ('data-cq="shape-fainter-', 'data-cq="shape-stronger-'),
    "wires": ('data-cq="shape-wires-',),
    "grey": ('data-cq="shape-grey-',),
    "notes": ('data-cq="notes"',),
    "grid": ('data-cq="grid"',),
    "labels": ('data-cq="labels"',),
    "key": ('data-cq="key"',),
    "appearance": ('data-cq="appearance"', 'data-cq="page-colour"'),
    "picture": ('data-cq="picture"',),
    "remember": ('data-cq="remember"',),
}


def a_gamut(seed, size=1.0):
    """A small closed surface standing in for a measured paper.

    Built the way the test suite builds one, so this audit and the tests are
    looking at the same kind of object.
    """
    from gamutview import build_gamut

    rng = np.random.default_rng(seed)
    points = rng.normal(size=(80, 3)) * np.array([12.0, 20.0, 20.0]) * size
    points[:, 0] += 50.0
    return build_gamut(points, input_space="lab", space="lab")


def pages():
    """Every kind of page the application writes, and what is in each."""
    rng = np.random.default_rng(11)
    n = 400
    cloud_lab = np.column_stack([rng.uniform(20, 92, n),
                                 rng.uniform(-60, 60, n),
                                 rng.uniform(-60, 60, n)])
    cloud_de = rng.uniform(0.4, 4.0, n)
    return [
        ("one shape", dict(gamuts=[("paper-1", a_gamut(1))]),
         {"two_shapes": False, "surfaces": True, "flat": False,
          "camera": True}),
        ("two shapes", dict(gamuts=[("paper-1", a_gamut(1)),
                                    ("paper-2", a_gamut(2, 0.8))]),
         {"two_shapes": True, "surfaces": True, "flat": False,
          "camera": True}),
        ("a drift cloud, no shapes",
         dict(gamuts=[], drift=(cloud_lab, cloud_de, "2019 → 2024", None,
                                True)),
         {"two_shapes": False, "surfaces": False, "flat": False,
          "camera": True}),
        ("a cross-section", dict(gamuts=[("paper-1", a_gamut(1)),
                                         ("paper-2", a_gamut(2, 0.8))],
                                 flat=True),
         {"two_shapes": True, "surfaces": True, "flat": True,
          "camera": False}),
    ]


def written(where, gamuts, drift=None, flat=False):
    """Write the page with EVERYTHING offered, and hand back its text."""
    import ti3gamut

    every = {name: True for name in MARKERS}
    if flat:
        ti3gamut.write_slice_html(gamuts, where, 50.0, "a cut",
                                  mode="dark", controls=True, offer=every)
    else:
        ti3gamut.write_html(gamuts, where, "a scene", carry_viewer=False,
                            controls=True, offer=every,
                            spin={"on": True, "mode": "turn", "speed": 6,
                                  "sweep": 0, "tilt_mode": "none",
                                  "tilt_speed": 4, "tilt_sweep": 30,
                                  "glide": True},
                            drift=drift)
    return where.read_text(encoding="utf-8")


def main() -> int:
    from PyQt6.QtWidgets import QApplication

    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)   # noqa: F841
    needs = gamut_app.WebPageDialog.NEEDS
    every = set(MARKERS)
    problems, seen_anywhere = [], set()
    folder = pathlib.Path(tempfile.mkdtemp(prefix="offers-"))
    try:
        for name, how, shows in pages():
            page = written(folder / f"{name.replace(' ', '-')}.html", **how)
            can = {switch for switch, marks in MARKERS.items()
                   if any(mark in page for mark in marks)}
            seen_anywhere |= can
            offered = {switch for switch in every
                       if needs.get(switch) is None
                       or shows.get(needs[switch], False)}
            over = sorted(offered - can)
            under = sorted(can - offered)
            print(f"\n{name}")
            print(f"   the page can honour {len(can)} of {len(every)}; "
                  f"the dialog offers {len(offered)}")
            for switch in over:
                problems.append(
                    f"[over]  {name}: '{switch}' is offered and the page does "
                    f"not carry it")
            for switch in under:
                problems.append(
                    f"[under] {name}: the page carries '{switch}' and the "
                    f"dialog does not offer it")
            if not over and not under:
                print("   exactly what it can do, in both directions")
        missing = sorted(every - seen_anywhere)
        for switch in missing:
            problems.append(
                f"[gone]  '{switch}' appears in no page at all — the name in "
                f"the dialog and the name in the writer have drifted apart, "
                f"or this audit's marker for it is stale")
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)

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
