"""Drive every combination the ink-amount view can be put in, on screen.

WHAT THIS IS FOR. A unit test can say that a function returns the right array.
It cannot say that opening a paper while ink amounts are showing leaves the
window in a sensible state, or that switching away and back gives you your
picture unchanged, or that a CMYK chart explains itself instead of drawing
three of its four inks. Those are questions about the whole window, and the
only honest way to ask them is to build the real one and use it.

Each scenario below says what SHOULD happen before it looks, so a wrong answer
is a failure rather than something to read and nod at. That matters more here
than usual: this view deliberately draws less than the others, so "nothing on
screen" is the correct outcome in some scenarios and a bug in others, and only
a written expectation can tell the two apart.

    python scripts/drive_ink_amounts.py

Exit code is 1 if any expectation is not met.
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["drive_ink_amounts"]

import numpy as np                                          # noqa: E402
from PyQt6.QtCore import QSettings                           # noqa: E402
from PyQt6.QtWidgets import QApplication                     # noqa: E402

DEMO = pathlib.Path(os.environ.get(
    "GAMUTVIEW_DEMO", str(HERE.parent.parent / "demo")))
#: A bigger chart to fall back on, named by an environment
#: variable rather than a path — a path here would publish
#: whatever somebody happened to call their own project.
BIG_CHART = pathlib.Path(os.environ.get("GAMUTVIEW_BIG_CHART", ""))

results: list = []


def check(name: str, expectation: str, ok: bool, detail: str = "") -> None:
    results.append((name, expectation, bool(ok), detail))
    mark = "  ok  " if ok else " FAIL "
    print(f"[{mark}] {name}")
    print(f"          expected: {expectation}")
    if detail:
        print(f"          got:      {detail}")


def main() -> int:
    QSettings("MeasuredGamutViewer", "MeasuredGamutViewer").clear()
    import chart as chart_mod
    import gamut_app

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
    w.resize(1560, 940)
    pump(1)

    def space(key):
        w._space.setCurrentIndex(w._space.findData(key))
        pump(2.5)

    chart_480 = DEMO / "verification-chart-480.ti1"
    chart_big = BIG_CHART
    glossy_icc = DEMO / "Glossy-paper.icc"
    glossy_ti3 = DEMO / "Glossy-paper.ti3"
    matte_ti3 = DEMO / "Matte-paper.ti3"
    a_chart = chart_480 if chart_480.is_file() else chart_big

    # ----------------------------------------------------------------- 1
    # The thing that was asked for: a chart, alone, no profile.
    space("rgb")
    w._open_chart_file(a_chart)
    pump(3)
    cloud = w._chart_cloud()
    check("1. a chart alone in ink amounts",
          "it draws, with no profile: dots positioned at the file's own "
          "numbers and Lab absent entirely",
          cloud is not None and cloud[1] is None and cloud[3] is not None,
          f"cloud={'None' if cloud is None else f'lab={cloud[1]}, device={cloud[3].shape}'}")

    read = w._chart[1]
    check("2. the dots are the file's numbers, untouched",
          "every position equals the file's device value × 100",
          np.allclose(cloud[3], np.asarray(read.device)[:, :3] * 100.0),
          f"max difference {np.abs(cloud[3] - np.asarray(read.device)[:, :3] * 100.0).max():.6g}")

    check("3. nothing else is drawn",
          "no gamut shapes at all — a paper in ink amounts would be the same "
          "full cube whatever paper it is",
          w._scene_contents()[0] == [],
          f"{len(w._scene_contents()[0])} shapes")

    check("4. the spacing figure is quoted in ink, not in Lab",
          "the sentence names ink amounts as its units",
          "each ink" in w._chart_spread.text(),
          w._chart_spread.text()[:90])

    # ----------------------------------------------------------------- 2
    # A profile added: colours change, positions do not.
    before = np.array(cloud[3], copy=True)
    if glossy_icc.is_file():
        w._chart_profile = glossy_icc
        w._fill_chart_profiles()
        w._place_chart()
        pump(4)
        after = w._chart_cloud()
        check("5. a profile paints but does not move",
              "the dots stay exactly where they were, and Lab appears so they "
              "can be given their real colours",
              np.allclose(after[3], before) and after[1] is not None,
              f"moved by at most {np.abs(after[3] - before).max():.6g}")

    # ----------------------------------------------------------------- 3
    # A paper opened WHILE in ink amounts — the case that was broken.
    if matte_ti3.is_file():
        w._load(matte_ti3)
        pump(12)
        check("6. a paper opens while ink amounts are showing",
              "it loads and is measured (in CIELAB, since a gamut cannot be "
              "built in ink amounts) even though it is not drawn",
              len(w._slots) == 1,
              f"{len(w._slots)} loaded")
        rows = w._chart_rows.text()
        check("7. the patches are still counted against it",
              "a line naming the paper, with inside/edge/outside counts",
              "Matte-paper" in rows and "outside" in rows,
              rows.split("\n")[0][:100])
        marked = w._chart_cloud()[2]
        check("8. the ones it cannot reach are picked out in the cube",
              "some dots marked, so the unreachable region is visible in ink "
              "amounts — which is what this view is for",
              marked is not None and 0 < int(marked.sum()) < len(marked),
              f"{'none' if marked is None else int(marked.sum())} of "
              f"{0 if marked is None else len(marked)} marked")

        # ------------------------------------------------------------- 4
        # The same question asked in CIELAB must give the same answer.
        ink_rows = w._chart_rows.text()
        space("lab")
        pump(8)
        lab_rows = w._chart_rows.text()
        check("9. the count does not depend on which space is showing",
              "identical counts in CIELAB and in ink amounts — the judgement "
              "is about colour and the space is only how it is drawn",
              ink_rows.split("Worst")[0] == lab_rows.split("Worst")[0],
              f"ink={ink_rows.split(chr(10))[0][:60]!r} "
              f"lab={lab_rows.split(chr(10))[0][:60]!r}")
        check("10. the shapes come back",
              "the paper is drawn again the moment a colour space is chosen",
              len(w._scene_contents()[0]) == 1,
              f"{len(w._scene_contents()[0])} shapes")
        check("11. the spacing figure changes its units with the space",
              "CIELAB quotes straight-line Lab distance",
              "in Lab" in w._chart_spread.text(),
              w._chart_spread.text()[:80])

    # ----------------------------------------------------------------- 5
    # Controls: off in ink amounts, back exactly as they were afterwards.
    space("lab")
    w._opacity.setValue(64)
    w._points.setChecked(True)
    pump(2)
    opacity_before = w._opacity.value()
    space("rgb")
    off = [n for n in ("_opacity", "_points", "_style_mine", "_side_by_side",
                       "_slice_on", "_neutral")
           if getattr(w, n).isEnabled()]
    check("12. surface controls go dead in ink amounts",
          "every control that only describes a drawn surface is switched off",
          not off, f"still enabled: {off or 'none'}")
    on = [n for n in ("_white", "_relative", "_detail", "_mode", "_grid_on",
                      "_aspect", "_chart_btn", "_open_btn")
          if not getattr(w, n).isEnabled()]
    check("13. everything still meaningful stays live",
          "the white point, how the shape is built, opening files and the "
          "chart controls all keep working",
          not on, f"wrongly disabled: {on or 'none'}")
    check("14. a switched-off control says why",
          "its tooltip explains, and names what to choose instead",
          "ink amounts" in w._opacity.toolTip()
          and "CIELAB" in w._opacity.toolTip(),
          w._opacity.toolTip()[:80])
    space("lab")
    check("15. nothing was lost on the way back",
          f"opacity is still {opacity_before} and its own tooltip is restored",
          w._opacity.value() == opacity_before
          and "ink amounts" not in w._opacity.toolTip(),
          f"opacity={w._opacity.value()}, tooltip={w._opacity.toolTip()[:40]!r}")

    # ----------------------------------------------------------------- 6
    # A four-ink chart cannot go on three axes, and says so.
    cmyk = pathlib.Path(os.environ.get("GAMUTVIEW_CMYK_CHART", ""))
    if cmyk.name and cmyk.is_file():
        w._close_chart()
        pump(1)
        w._open_chart_file(cmyk)
        pump(3)
        space("rgb")
        ok, why = w._chart_in_ink_ok()
        check("16. a CMYK chart refuses the three ink axes",
              "it explains that four inks do not fit three axes, and sends "
              "the reader to the view that does work for them",
              not ok and "CIELAB" in why and "Placed through" in why,
              why[:110])
        check("17. and it is not drawn rather than drawn wrong",
              "nothing in the picture — dropping a fourth ink would draw a "
              "chart that was never in the file",
              w._chart_cloud() is None,
              f"cloud={w._chart_cloud()}")
        note = w._chart_note.text()
        check("18. the panel says it too, not only the tooltip",
              "the reason is on the panel where somebody is already looking",
              "three axes" in note, note[:100])
        w._close_chart()
        pump(1)

    # ----------------------------------------------------------------- 7
    # Saving and exporting what is on screen.
    space("rgb")
    w._open_chart_file(a_chart)
    pump(3)
    check("19. a chart alone can be saved",
          "Save, Export and Picture are all live with no profile and no "
          "measurement open",
          w._save.isEnabled() and w._export_btn.isEnabled()
          and w._picture.isEnabled(),
          f"save={w._save.isEnabled()} export={w._export_btn.isEnabled()} "
          f"picture={w._picture.isEnabled()}")

    out = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "ink-view.html"
    w._write_current_page(out) if hasattr(w, "_write_current_page") else None
    if not out.exists():
        from ti3gamut import write_html
        write_html([], out, "ink", **w._render_options())
    page = out.read_text(errors="replace")
    check("20. the saved page is the ink view, not a Lab one",
          "the axes in the file say Red/Green/Blue",
          "Red  %" in page and "a*" not in page.split("Red  %")[0][-400:],
          f"{len(page):,} bytes, Red % present: {'Red  %' in page}")

    # ----------------------------------------------------------------- 8
    # A measurement opened in ink amounts: loaded, never drawn.
    # Cleared first — the Matte paper from scenario 6 is still open, and
    # counting it here made this scenario fail on its own arithmetic rather
    # than on anything the window did.
    w._on_clear()
    pump(2)
    space("rgb")
    w._open_chart_file(a_chart)
    pump(3)
    if glossy_ti3.is_file():
        w._load(glossy_ti3)
        pump(12)
        check("21. everything open survives the view it cannot appear in",
              "the measurement is loaded and measured, and drawn again as "
              "soon as CIELAB is chosen",
              len(w._slots) == 1 and w._scene_contents()[0] == [],
              f"{len(w._slots)} loaded, {len(w._scene_contents()[0])} drawn")
        space("lab")
        pump(6)
        check("22. and it is drawn the moment a colour space returns",
              "one shape on screen, with its volume measured in Lab units",
              len(w._scene_contents()[0]) == 1
              and "Lab" in w._volume_units(),
              f"{len(w._scene_contents()[0])} shapes, units={w._volume_units()!r}")

    # ----------------------------------------------------------------- 9
    # The skin over the patches, and the shape that must never be drawn.
    w._on_clear(); pump(2)
    space("rgb")
    w._open_chart_file(a_chart); pump(3)
    check("23. the skin controls appear only with a chart",
          "the group is on screen now, and the out-of-reach row is not — "
          "nothing is judging yet",
          w._chart_look_box.isVisible()
          and not w._chart_outside_row.isVisible(),
          f"group={w._chart_look_box.isVisible()} "
          f"outside row={w._chart_outside_row.isVisible()}")
    check("24. the skin's own settings appear only with a skin",
          "no colour or opacity row while the skin is set to none",
          not w._chart_skin_row.isVisible(),
          f"skin row={w._chart_skin_row.isVisible()}")
    w._chart_skin.setCurrentIndex(w._chart_skin.findData("solid")); pump(4)
    check("25. choosing a skin brings its settings with it",
          "the colour and opacity rows appear",
          w._chart_skin_row.isVisible(),
          f"skin row={w._chart_skin_row.isVisible()}")

    if glossy_icc.is_file() and matte_ti3.is_file():
        w._chart_profile = glossy_icc; w._fill_chart_profiles()
        w._place_chart(); pump(4)
        w._load(matte_ti3); pump(12)
        check("26. the out-of-reach row appears once something judges",
              "a paper is open, so there is something to be out of reach of",
              w._chart_outside_row.isVisible(),
              f"outside row={w._chart_outside_row.isVisible()}")
        import chart as _cm
        marked = w._chart_cloud()[2]
        dev = _cm.device_positions(w._chart[1])
        from scipy.spatial import ConvexHull
        import numpy as _np
        def _vol(pts):
            pts = _np.unique(_np.asarray(pts).round(6), axis=0)
            return ConvexHull(pts).volume
        skinned = _vol(dev[~marked]); whole = _vol(dev)
        lost_hull = _vol(dev[marked])
        check("27. the skin covers only what survives",
              "a shape over the surviving patches is clearly smaller than one "
              "over the whole chart",
              skinned < whole * 0.95,
              f"survivors {skinned:,.0f} vs whole {whole:,.0f} "
              f"= {skinned/whole:.0%}")
        check("28. and there is no skin over the lost ones, for a reason",
              "a shape round the lost patches would be most of the whole "
              "chart, because they wrap around the rest — so none is offered",
              lost_hull / whole > 0.75,
              f"round the lost ones {lost_hull:,.0f} = {lost_hull/whole:.0%} "
              f"of the whole chart")
        names = [t["name"] for t in
                 __import__("ti3gamut").build_figure(
                     [], "t", space="rgb", chart=w._chart_cloud(),
                     chart_look=w._chart_look()).data]
        check("29. nothing in the picture is called a gamut",
              "the skin is named for what it is, and never joins the volume "
              "figures or the comparison",
              any("a skin over the patches" in n for n in names)
              and not any("gamut" in n.lower() for n in names),
              str(names))
        w._chart_show_outside.setChecked(False); pump(5)
        after = [t["name"] for t in
                 __import__("ti3gamut").build_figure(
                     [], "t", space="rgb", chart=w._chart_cloud(),
                     chart_look=w._chart_look()).data]
        check("30. the lost patches can be hidden without losing the skin",
              "the red dots go, the skin and the survivors stay",
              not any("outside" in n for n in after)
              and any("skin" in n for n in after),
              str(after))
        w._chart_show_outside.setChecked(True); pump(3)

    print()
    bad = [r for r in results if not r[2]]
    print(f"{len(results) - len(bad)}/{len(results)} scenarios met their "
          f"expectation.")
    for name, expectation, _ok, detail in bad:
        print(f"  FAILED {name}: expected {expectation} — got {detail}")
    return 1 if bad else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
