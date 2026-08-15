"""Every combination of the chart's options, checked against what must hold.

WHY A COMBINATORIAL RUN AND NOT MORE EXAMPLES. Each option on its own is easy
to get right and easy to test. What goes wrong is a *pair*: a setting that
reaches the screen and not the saved page, a look setting that quietly moves a
measurement, a shape drawn in one place and judged against another. Those only
appear when the options are crossed with each other, so they are crossed here.

Two phases, because they catch different faults:

  A — every combination, at the figure level. Fast enough to be exhaustive, and
      the level at which the INVARIANTS live: things that must be true of every
      combination without exception, such as "no look setting may move a dot"
      and "no count may depend on how anything is drawn".

  B — a representative set through the real window, comparing what is on
      screen with what a save actually writes. This is where an option that
      reaches one route and not the other shows up, and no figure-level check
      can see it.

    python scripts/drive_all_combinations.py

Exit code is 1 if any invariant is broken.
"""
from __future__ import annotations

import itertools
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["drive_all_combinations"]

import numpy as np                                          # noqa: E402

DEMO = pathlib.Path(os.environ.get(
    "GAMUTVIEW_DEMO", str(HERE.parent.parent / "demo")))
HOME = pathlib.Path.home() / "ChromIQ"

failures: list = []
checked = 0


def must(condition, what: str, detail: str = "") -> None:
    global checked
    checked += 1
    if not condition:
        failures.append((what, detail))
        print(f"  FAIL  {what}\n        {detail}")


# --------------------------------------------------------------------------
# Phase A — every combination, at the figure level
# --------------------------------------------------------------------------

SKINS = ("none", "outline", "mesh", "solid")
SKIN_COLOURS = ("grey", "patches", "accent")
SKIN_OPACITY = (0.05, 0.30, 1.0)
DOT_SIZE = (2.0, 3.2, 10.0)
DOT_OPACITY = (0.1, 1.0)
OUT_SIZE = (2.0, 14.0)
OUT_OPACITY = (0.1, 1.0)
SHOW_OUTSIDE = (True, False)
SPACES = ("lab", "luv", "xyz", "rgb")


def phase_a():
    import chart as cm
    from ti3gamut import build_figure

    chart_file = DEMO / "verification-chart-480.ti1"
    if not chart_file.is_file():
        chart_file = HOME / "knut" / "knut.ti1"
    c = cm.read_chart(chart_file)
    device = cm.device_positions(c)
    placed = cm.through_profile(c, DEMO / "Glossy-paper.icc")
    lab = placed.under("D50")
    # A real split rather than an invented one: judged against the matte paper.
    from gamutview import build_gamut
    from ti3gamut import read_measurement
    m = read_measurement(DEMO / "Matte-paper.ti3", "D50", True)
    paper = build_gamut(m.lab, input_space="lab", space="lab",
                        white_point="D50")
    outside = cm.outside_report(lab, paper).beyond
    n_out = int(outside.sum())
    print(f"Phase A — {len(device)} patches, {n_out} of them out of reach")

    # What the dots must sit at, worked out ONCE and independently of any
    # option, so a look setting that moves them is caught rather than trusted.
    from ti3gamut import _to_plot_space
    expected = {"rgb": device}
    for space in ("lab", "luv", "xyz"):
        expected[space] = _to_plot_space(lab, space)

    combos = list(itertools.product(
        SPACES, SKINS, SKIN_COLOURS, SKIN_OPACITY, DOT_SIZE, DOT_OPACITY,
        OUT_SIZE, OUT_OPACITY, SHOW_OUTSIDE))
    print(f"         {len(combos):,} combinations")
    survivors_hull = cm.skin(device[~outside])[0]

    for (space, skin, colour, sk_op, d_sz, d_op,
         o_sz, o_op, show_out) in combos:
        look = dict(skin=skin, skin_colour=colour, skin_opacity=sk_op,
                    dot_size=d_sz, dot_opacity=d_op, out_dot_size=o_sz,
                    out_dot_opacity=o_op, show_outside=show_out,
                    show_inside=True, accent="#22d3aa")
        tag = (f"{space}/{skin}/{colour}/op{sk_op}/d{d_sz}·{d_op}/"
               f"o{o_sz}·{o_op}/out={show_out}")
        fig = build_figure([], "t", space=space,
                           chart=("c", lab, outside, device),
                           chart_look=look)
        # A LEGEND PROXY IS NOT A DOT. It is a scatter3d holding no points at
        # all, drawn only so the key beside the name carries a colour that can
        # be seen — see _legend_proxy. Counting it as data made every
        # position check fail at once, which is a harness fault and looked
        # exactly like a catastrophic one.
        dots = [t for t in fig.data
                if t.type == "scatter3d" and t.hoverinfo != "skip"]
        meshes = [t for t in fig.data if t.type == "mesh3d"]

        # 1. No look setting may move a single dot. This is the invariant the
        #    whole feature rests on: the picture may be styled any way at all,
        #    and it still shows the same measurements in the same places.
        got = np.column_stack([np.concatenate([t.x for t in dots]),
                               np.concatenate([t.y for t in dots]),
                               np.concatenate([t.z for t in dots])])
        want = expected[space]
        if not show_out:
            want = want[~outside]
        must(len(got) == len(want)
             and np.allclose(np.sort(got, axis=0), np.sort(want, axis=0)),
             "a look setting moved the dots", tag)

        # 2. A skin appears when and only when one was asked for.
        must(bool(meshes) == (skin != "none"),
             f"skin traces={len(meshes)} for skin={skin!r}", tag)

        # 3. The skin never reaches past what survives. Drawing it over the
        #    lost patches would fill the picture — see _chart_skin.
        if meshes and survivors_hull is not None and space == "rgb":
            sv = np.column_stack([meshes[0].x, meshes[0].y, meshes[0].z])
            must(len(sv) <= len(survivors_hull) + 1e-9
                 and sv.max() <= device[~outside].max() + 1e-6,
                 "the skin reached past the surviving patches", tag)

        # 4. Every option set is the option drawn. An option that is accepted
        #    and then quietly dropped is the fault this whole run exists for.
        inside_dots = [t for t in dots if "outside" not in (t.name or "")]
        out_dots = [t for t in dots if "outside" in (t.name or "")]
        for t in inside_dots:
            must(t.marker.size == d_sz, "inside dot size not applied",
                 f"{tag}: got {t.marker.size}")
            must(t.marker.opacity == d_op, "inside dot opacity not applied",
                 f"{tag}: got {t.marker.opacity}")
        must(bool(out_dots) == (show_out and n_out > 0),
             "show-the-lost-ones not honoured", tag)
        for t in out_dots:
            must(t.marker.size == o_sz, "lost dot size not applied",
                 f"{tag}: got {t.marker.size}")
            must(t.marker.opacity == o_op, "lost dot opacity not applied",
                 f"{tag}: got {t.marker.opacity}")
        for t in meshes:
            if skin == "outline":
                must(t.opacity < 0.05, "outline drew a filled surface",
                     f"{tag}: opacity {t.opacity}")
            else:
                must(t.opacity == sk_op, "skin opacity not applied",
                     f"{tag}: got {t.opacity}")
            if colour == "grey":
                must(t.vertexcolor is None and t.color == "#8b93a3",
                     "grey skin was not grey", f"{tag}: {t.color}")
            elif colour == "accent":
                must(t.vertexcolor is None and t.color == "#22d3aa",
                     "accent skin ignored the accent", f"{tag}: {t.color}")
            else:
                must(t.vertexcolor is not None,
                     "patch-coloured skin has no vertex colours", tag)

        # 5. Nothing in the picture may be called a gamut. The skin is not
        #    one, and a legend that says otherwise is the misreading this
        #    feature could most easily cause.
        must(not any("gamut" in (t.name or "").lower() for t in fig.data),
             "something in the picture is named a gamut", tag)

    print(f"Phase A — {checked:,} checks over {len(combos):,} combinations")


# --------------------------------------------------------------------------
# Phase B — the real window, and what a save actually writes
# --------------------------------------------------------------------------

def phase_b():
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    QSettings("MeasuredGamutViewer", "MeasuredGamutViewer").clear()
    import gamut_app
    from ti3gamut import build_figure

    app = QApplication(sys.argv)
    w = gamut_app.GamutApp([])
    w.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(3)
    w.resize(1500, 940)
    pump(1)

    chart_file = DEMO / "verification-chart-480.ti1"
    w._open_chart_file(chart_file)
    w._chart_profile = DEMO / "Glossy-paper.icc"
    w._fill_chart_profiles()
    w._place_chart()
    pump(4)
    w._load(DEMO / "Matte-paper.ti3")
    pump(12)

    print("\nPhase B — the window against its own save")

    # THE COUNTS MAY NOT DEPEND ON THE SPACE. "Can this paper reach this
    # patch" is a question about colour; the space is only how the answer is
    # drawn. This gave three different answers before _in_lab: 240 in CIELAB,
    # 178 in CIELUV, 480 in CIE XYZ.
    counts = {}
    for space in ("lab", "luv", "xyz", "rgb"):
        w._space.setCurrentIndex(w._space.findData(space))
        pump(6)
        counts[space] = w._chart_rows.text().split("\n")[0]
    must(len(set(counts.values())) == 1,
         "the patch counts change with the space the picture is drawn in",
         "; ".join(f"{k}: {v}" for k, v in counts.items()))
    print(f"  every space agrees: {next(iter(counts.values()))}")
    sample = [
        ("rgb", "solid", "patches", 60, 25, 90, 40, True),
        ("rgb", "outline", "grey", 30, 100, 20, 100, False),
        ("lab", "mesh", "accent", 80, 50, 120, 60, True),
        ("luv", "none", "grey", 30, 100, 55, 100, True),
        ("xyz", "solid", "grey", 100, 100, 55, 30, False),
    ]
    for (space, skin, colour, sk_op, d_op, o_sz, o_op, show_out) in sample:
        w._space.setCurrentIndex(w._space.findData(space))
        w._chart_skin.setCurrentIndex(w._chart_skin.findData(skin))
        w._chart_skin_colour.setCurrentIndex(
            w._chart_skin_colour.findData(colour))
        w._chart_skin_opacity.setValue(sk_op)
        w._chart_dot_opacity.setValue(d_op)
        w._chart_out_dot.setValue(o_sz)
        w._chart_out_opacity.setValue(o_op)
        w._chart_show_outside.setChecked(show_out)
        pump(6)
        tag = f"{space}/{skin}/{colour}"

        # What the window says it is drawing, and what a save would write:
        # built from the same call the save route makes, so a setting that
        # reaches one and not the other cannot hide.
        live = w._chart_look()
        must(live["skin"] == skin and live["skin_colour"] == colour
             and abs(live["skin_opacity"] - sk_op / 100) < 1e-9
             and abs(live["dot_opacity"] - d_op / 100) < 1e-9
             and abs(live["out_dot_size"] - o_sz / 10) < 1e-9
             and abs(live["out_dot_opacity"] - o_op / 100) < 1e-9
             and live["show_outside"] == show_out,
             "the window's own settings do not match the controls",
             f"{tag}: {live}")

        options = w._render_options()
        must(options.get("chart_look") == live,
             "the save route does not carry the chart's look", tag)
        gamuts, clouds, styles, lost = w._scene_contents()
        saved = build_figure(gamuts, "t", patches=clouds, styles=styles,
                             lost=lost, **options)
        names = sorted(t.name or "" for t in saved.data)
        must(any("to be printed" in n for n in names),
             "the saved page has no chart in it", f"{tag}: {names}")
        must(bool([n for n in names if "outside" in n]) == show_out,
             "the saved page disagrees about the lost patches",
             f"{tag}: {names}")
        must(bool([n for n in names if "skin" in n]) == (skin != "none"),
             "the saved page disagrees about the skin",
             f"{tag}: {names}")

    # THE TWO-ROOMS CASE. Each room holds one shape, and the chart is judged
    # against the FIRST shape on screen — so a chart drawn into both rooms
    # would appear in the right-hand one marked against the left-hand paper.
    w._space.setCurrentIndex(w._space.findData("lab"))
    # Put the controls back: the last sample above left the lost patches
    # hidden and the skin on, and this check reads exactly those.
    w._chart_show_outside.setChecked(True)
    w._chart_skin.setCurrentIndex(w._chart_skin.findData("none"))
    w._load(DEMO / "Glossy-paper.ti3")
    pump(12)
    if len(w._slots) >= 2 and w._side_by_side.isEnabled():
        w._side_by_side.setChecked(True)
        pump(8)
        options = w._render_options()
        gamuts, clouds, styles, lost = w._scene_contents()
        room2 = build_figure([gamuts[1]], "", patches=[clouds[1]],
                             styles=["solid"], lost=None, **options)
        # Each room must mark the chart against ITS OWN paper.
        room1 = build_figure([gamuts[0]], "", patches=[clouds[0]],
                             styles=["solid"], lost=None,
                             chart=w._chart_marked_against(
                                 options.get("chart"), gamuts[0][1]),
                             **{k: v for k, v in options.items()
                                if k != "chart"})
        room2 = build_figure([gamuts[1]], "", patches=[clouds[1]],
                             styles=["solid"], lost=None,
                             chart=w._chart_marked_against(
                                 options.get("chart"), gamuts[1][1]),
                             **{k: v for k, v in options.items()
                                if k != "chart"})
        def lost_in(fig):
            for t in fig.data:
                if "outside" in (t.name or ""):
                    return len(t.x)
            return 0
        a, b = lost_in(room1), lost_in(room2)
        # And in a space the shapes are NOT built in: judging is rebuilt in
        # CIELAB from the slot, so the two rooms must still disagree here.
        w._space.setCurrentIndex(w._space.findData("luv"))
        pump(8)
        o2 = w._render_options()
        g2, c2, _s2, _l2 = w._scene_contents()
        luv = [lost_in(build_figure(
                   [g2[i]], "", patches=[c2[i]], styles=["solid"], lost=None,
                   chart=w._chart_marked_against(o2.get("chart"), g2[i][1],
                                                 w._slots[i]),
                   **{k: v for k, v in o2.items() if k != "chart"}))
               for i in (0, 1)]
        must(luv == [a, b],
             "the two rooms answer differently in CIELUV than in CIELAB, so "
             "one of them is judging against a shape in the wrong space",
             f"CIELAB {[a, b]} vs CIELUV {luv}")
        print(f"  two rooms in CIELUV agree with CIELAB: {luv}")
        w._space.setCurrentIndex(w._space.findData("lab"))
        pump(6)
        must(a != b,
             "both rooms mark the chart identically, so at least one of them "
             "is judging it against the other room's paper",
             f"{gamuts[0][0]} lost {a}, {gamuts[1][0]} lost {b}")
        print(f"  two rooms: {gamuts[0][0]} loses {a}, "
              f"{gamuts[1][0]} loses {b}")
        w._side_by_side.setChecked(False)
        pump(4)

    print(f"\n{checked:,} checks, {len(failures)} broken.")
    for what, detail in failures[:20]:
        print(f"  FAILED {what}: {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    phase_a()
    code = phase_b()
    sys.stdout.flush()
    os._exit(code)
