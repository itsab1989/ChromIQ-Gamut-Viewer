"""Does every control tell the truth about the picture on screen?

ASKED FOR IN AS MANY WORDS: "audit that all of the options stay true to the
viewer" -- after a control read one thing while the picture plainly showed
another: "outline color was set to plain grey there which also did not match
the coloured way it was shown", and "how solid it looks says 100% although the
slider is more in the middle".

WHY THIS IS ITS OWN KIND OF FAULT. A control that does nothing is annoying and
obvious. A control that SAYS something untrue is worse and invisible: the
reader believes the window, quotes it, and saves a page they think they
understand. Both of tonight's were of the second kind, and both came from the
same place -- a value set somewhere without the control that displays it being
told.

HOW IT ASKS. For every control with a knowable effect, it reads the control,
reads the FIGURE the window is actually drawing, and compares. Not the code
path that connects them: the two ends. A control whose setting cannot be found
in the picture is reported with both numbers.

    python scripts/audit_truth.py

Exit code 1 if any control and the picture disagree.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

# THE SETTINGS GO SOMEWHERE THROWAWAY, and this must happen before the
# window is built. A driver that uses the real store both destroys what
# the person using this application has chosen and leaves its own last
# state behind as their new preference -- which is how "the walls behind
# the shape are missing" was reported as a bug in the viewer. See
# python/prefs.py.
import prefs  # noqa: E402

prefs.use_a_scratch_store()
sys.argv = ["audit_truth"]


def surfaces(figure):
    return [t for t in figure.data if t.type == "mesh3d"]


def wires(figure):
    return [t for t in figure.data
            if t.type == "scatter3d" and getattr(t, "mode", "") == "lines"]


def dots(figure):
    """The drawn colours, and NOT the legend keys.

    A key is a scatter3d holding one invisible point, drawn only so the name
    beside it carries a colour -- see _legend_proxy. Counted as data it made
    "729 drawn" read as 730, which is an audit reporting its own arithmetic.
    """
    return [t for t in figure.data
            if t.type == "scatter3d" and getattr(t, "mode", "") == "markers"
            and getattr(t, "hoverinfo", "") != "skip"]


#: (what it is called, how to read the control, how to read the picture, how to
#: say what disagreed). Each returns a comparable value, and None means "this
#: cannot be judged in the state the window is in", which is not a fault.
def checks(win, panel):
    def figure():
        return panel.figure_now()

    def solidity_control():
        return win._opacity.value() / 100.0

    def solidity_picture():
        made = surfaces(figure())
        return round(made[0].opacity, 3) if made else None

    def reading_beside_the_slider():
        text = win._opacity_lbl.text().rstrip("%")
        return float(text) / 100.0 if text.replace(".", "").isdigit() else None

    def first_shape_style_control():
        return win._style_mine.currentData()

    def first_shape_style_picture():
        """What the FIRST shape is drawn as, by name.

        Asked of the picture as a whole it was wrong in the ordinary case:
        the second shape's default is an outline, so a solid first shape and
        an outlined second one look exactly like one shape drawn as both --
        the audit reported "solid+mesh" over a perfectly correct picture.
        """
        fig = figure()
        first = None
        for name, _g in (panel._shells_for(*panel._chosen_pair()[:2])
                         if panel.shows_two_shapes() else []):
            first = name
            break
        if first is None:
            return None
        mine = [t for t in fig.data if str(t.name or "").startswith(first)]
        made = [t for t in mine if t.type == "mesh3d"]
        edges = [t for t in mine if t.type == "scatter3d"
                 and getattr(t, "mode", "") == "lines"]
        if made and edges:
            return "solid+mesh"
        if edges:
            return "mesh"
        return "solid" if made else None

    def box_control():
        return bool(win._grid_on.isChecked())

    def box_picture():
        scene = figure().layout.scene
        return bool(scene.xaxis.visible)

    def threshold_control():
        return round(_read_the_slider(), 2)

    def _read_the_slider():
        """The threshold as the SLIDER has it, not as the window reads it.

        THIS IS THE WHOLE POINT, AND THE FIRST VERSION GOT IT WRONG. It asked
        panel._cut_off() -- the very method the window uses to draw -- so when
        that method was made to lie, the expectation lied with it and the two
        agreed perfectly. The mutation test found it: "the hide-anything-under
        value never reaches the picture ... NOT NOTICED".
        
        A check phrased in terms of the thing it guards cannot catch that
        thing being broken. So this reads the handle: the number a person can
        see on screen, which is the only independent witness there is.
        """
        cut = panel._cut
        if cut.value() <= cut.minimum():
            return 0.0             # the far left is "nothing hidden"
        return cut.value() / 10.0

    def threshold_picture():
        """How many dots are drawn, against how many moved at least that far."""
        import numpy as np

        pair = panel._chosen_pair()
        if pair is None:
            return None
        from ti3gamut import compare_profiles
        d = compare_profiles(pair[0], pair[1], steps=panel.GRID)
        cut = _read_the_slider()
        want = int(np.sum(np.asarray(d.deltas) >= cut)) if cut else len(d.deltas)
        return want

    def threshold_drawn():
        return sum(len(t.x) for t in dots(figure()))

    def shapes_control():
        return bool(panel._with_shapes.isChecked())

    def shapes_picture():
        fig = figure()
        return bool(surfaces(fig) or wires(fig))

    def families_control():
        return bool(panel._by_family.isChecked())

    def families_picture():
        names = [str(t.name or "") for t in dots(figure())]
        return any(n.startswith(("reds", "yellows", "greens", "cyans",
                                 "blues", "magentas", "greys")) for n in names)

    return [
        ("how solid it looks → the surfaces",
         solidity_control, solidity_picture),
        ("how solid it looks → the number beside it",
         solidity_control, reading_beside_the_slider),
        ("first shape's style → what is drawn",
         first_shape_style_control, first_shape_style_picture),
        ("show the box and its grid → the axes",
         box_control, box_picture),
        ("hide anything under → how many dots are drawn",
         threshold_picture, threshold_drawn),
        ("show the two shapes → any shape in the picture",
         shapes_control, shapes_picture),
        ("split into colour families → the groups drawn",
         families_control, families_picture),
    ]


def main() -> int:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    win = gamut_app.GamutApp([])
    win.resize(1500, 950)
    win.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(3)
    profiles = sorted(pathlib.Path(tempfile.gettempdir())
                      .glob("showme-*/printer-*.icc"))
    if len(profiles) < 2:
        print("  no demo profiles to drive the window with")
        return 1
    panel = win._timeline
    panel.add(profiles)
    pump(7)
    for i in range(panel._picture_of.count()):
        if panel._picture_of.itemData(i) == ("whole", 0):
            panel._picture_of.setCurrentIndex(i)
            break
    panel._draw()
    pump(3)
    panel._with_shapes.setChecked(True)
    pump(4)

    # EVERY STATE THIS CAN BE ASKED IN, not just the one it opens in. A
    # control that agrees with the picture as it opens and disagrees after a
    # slider has been moved is exactly the fault this is looking for.
    states = [
        ("as it opens", lambda: None),
        ("after the opacity is dragged", lambda: (
            win._opacity.setValue(30), win._opacity.sliderReleased.emit())),
        ("with the first shape as a mesh", lambda: (
            win._style_mine.setCurrentIndex(
                win._style_mine.findData("mesh")),
            win._style_mine.activated.emit(0))),
        ("with the box switched off", lambda: (
            win._grid_on.setChecked(False))),
        ("with the threshold half way up", lambda: (
            panel._cut.setValue((panel._cut.minimum()
                                 + panel._cut.maximum()) // 2))),
        ("with the families split", lambda: (
            panel._by_family.setChecked(True))),
    ]

    problems = []
    for where, act in states:
        act()
        pump(3)
        print(f"\n  {where}")
        for name, control, picture in checks(win, panel):
            try:
                said, drawn = control(), picture()
            except Exception as exc:                      # noqa: BLE001
                problems.append(f"[truth] {where}: {name} could not be "
                                f"compared: {exc}")
                print(f"      ?     {name}")
                continue
            if said is None or drawn is None:
                print(f"      —     {name}  (not answerable here)")
                continue
            agree = (said == drawn)
            print(f"      {'ok  ' if agree else 'DIFFER'}  {name}"
                  f"{'' if agree else f'   says {said!r}, draws {drawn!r}'}")
            if not agree:
                problems.append(
                    f"[truth] {where}: {name} — the control says {said!r} and "
                    f"the picture shows {drawn!r}")

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} disagreement(s).")
        win.close()
        return 1
    print("  Clean: every control agrees with the picture, in every state.")
    win.close()
    pump(0.3)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
