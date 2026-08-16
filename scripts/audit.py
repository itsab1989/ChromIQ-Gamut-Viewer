"""Press every control there is, and say which ones do nothing.

    python scripts/audit.py                 # everything
    python scripts/audit.py --window        # only the window's own settings
    python scripts/audit.py --pages         # only saved pages
    python scripts/audit.py --list          # what it would test, and stop

WHY THIS EXISTS. Three controls in this application drew nothing at all for
several releases. Every one of them was found because somebody pointed at it,
and the reason no test caught them is that they *ran* perfectly: the code
executed, no error was raised, the button highlighted itself, and the picture
did not change by a single pixel. A unit test cannot see that. A person
looking at the screen can, and so can this.

WHAT IT IS FOR. Run it before cutting a release, and run it after adding a
control. It answers one question about each control:

    when you move it, does the picture change — and when you put it back,
    does the picture come back?

NOTHING IN HERE IS A LIST OF CONTROLS. That is the whole design. It finds them:

  * the window's own settings come from `GamutApp._persisted()`, the table the
    window already keeps of everything worth remembering, plus
    `_shape_controls()` for the per-shape ones;
  * a saved page's controls are read out of the page itself, every element
    carrying a `data-cq` attribute;
  * the shapes on a page are whatever the drawing library says is there.

So a control added tomorrow is audited tomorrow, by the person who added it,
without editing this file. If you add one and it does not appear here, that is
itself worth knowing — it means the window is not remembering it either.

USING THE 3D VIEWER FOR SOMETHING ELSE ENTIRELY. If you have kept the page
writer and thrown the rest away, `--pages` still applies: point it at any
directory of saved pages with `--dir`, and it will press whatever controls
those pages carry. It knows nothing about gamuts.

HOW IT AVOIDS LYING TO YOU. Four rules, each of which was learned by this
probe getting an answer wrong first:

  1. THE MOVEMENT IS STOPPED, through the page's own button rather than behind
     its back. A page that turns by itself differs from itself every frame, so
     every control "passes"; and stopping the animation without telling the
     panel leaves the panel restarting it on the next press.
  2. THE PANEL IS OPENED. Most controls live behind "more…", and an audit that
     never opens it reports on five buttons and calls it a page.
  3. EVERY KIND IS CHECKED BY ITS OWN RULE. A switch comes back when pressed
     again; a step comes back when its opposite is pressed; a preset comes
     back on "put the view back"; an action is allowed to change nothing, and
     has to say why. Pressing "zoom in" twice and calling it broken is not a
     finding.
  4. THE FLOOR IS MEASURED, INCLUDING A REDRAW. Two grabs of a still page
     differ by nothing; a picture rebuilt with the same numbers differs by a
     few thousand pixels at its edges. Judged against the wrong floor, two
     perfectly good controls looked broken.

Exit code is 1 if anything did nothing, so it can gate a release.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

import numpy as np                                        # noqa: E402

DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"

#: Controls on a saved page that step rather than switch: pressing the other
#: one is what undoes them. Read as "what undoes what", not as a list of
#: controls -- anything not named here is treated as a switch, and a switch
#: that turns out to be a step shows up as "does not come back" rather than
#: being silently excused.
OPPOSITES = {"in": "out", "out": "in", "cut-up": "cut-down",
             "cut-down": "cut-up", "left": "right", "right": "left",
             "up": "down", "down": "up",
             "agree-less": "agree-more", "agree-more": "agree-less",
             "differ-less": "differ-more", "differ-more": "differ-less"}

#: Controls that jump to a fixed view. Pressing one twice changes nothing the
#: second time, so "put the view back" is what undoes them.
PRESETS = ("look-above", "look-front", "look-side", "look-angle")

#: Controls whose job is NOT to change the picture, each with the reason. A
#: control that changes nothing and is not named here is a finding. Adding a
#: name here is a claim you are making; make it a true one.
ACTIONS = {
    "notes": "opens the captions, which are text beside the picture",
    "fullscreen": "asks the browser for the whole screen",
    "picture": "writes a file",
    "shot": "writes a PNG of the picture",
    "remember": "stores this view for the next visit",
    "home": "puts the view back, and nothing has moved it",
    "shapes-back": "puts every shape back, and none has been changed",
    "play": "starts the movement, which this audit deliberately stops",
    "more": "opens and closes the panel this audit is reading",
    "legend": "shows or hides the list of names",
    "lr": "chooses which way the movement goes",
    "ud": "chooses which way the movement goes",
    "sweep": "sets how far the movement swings",
    "speed": "sets how fast the movement goes",
    "slower": "sets how fast the movement goes",
    "faster": "sets how fast the movement goes",
}

#: A CONTROL WITH NOTHING TO ACT ON IS NOT A BROKEN CONTROL.
#:
#: Most of the window's settings need something on screen before they can do
#: anything: the Detail slider builds the shape being COMPARED against, and
#: with nothing to compare against there is no such shape; the lightness of a
#: cut means nothing until there is a cut. Run against one chart and nothing
#: else, eleven perfectly good controls reported "does nothing", which is a
#: report nobody can use.
#:
#: So the audit switches the parent on first. Left of the arrow is the control
#: being tested, right of it is what has to be true for it to have a job.
NEEDS = {
    "slice_at": "slice_on",
    "rings": "rings_on",
    "ideal_neutral": "neutral",
    "chart_dot": "_chart", "chart_out_dot": "_chart",
    "chart_dot_opacity": "_chart", "chart_out_opacity": "_chart",
    "chart_show_outside": "_chart", "chart_skin": "_chart",
    "chart_skin_colour": "_chart", "chart_skin_opacity": "_chart",
}

#: Window settings that are not expected to move the picture, with the reason.
WINDOW_ACTIONS = {
    "auto_update": "asks the releases page whether there is a newer version",
    "manual_light": "reveals five sliders; the picture moves when one moves",
    "link_cameras": "ties two scenes together, and there is one here",
    "side_by_side": "needs a second chart to have two rooms to put them in",
    "spin_on": ("starts the shape turning, so switching it off again leaves "
                "the shape wherever it had turned to -- which is the point "
                "of it, not a failure to come back"),
    "neutral": ("a line inside a solid shape cannot be seen, so the window "
                "turns the shape down the first time this is ticked -- once, "
                "deliberately, and it does not put it back, because by then "
                "the number is the user's"),
}


def opposite_of(what: str) -> "str | None":
    """What undoes this control, including the per-shape pairs.

    A shape's strength is a PAIR of buttons, − and +, one step each: pressing
    − twice makes it fainter twice, and it was never going to undo itself.
    """
    if what in OPPOSITES:
        return OPPOSITES[what]
    for a, b in (("fainter", "stronger"), ("stronger", "fainter")):
        if what.startswith(f"shape-{a}-"):
            return what.replace(f"shape-{a}-", f"shape-{b}-")
    return None


class Bench:
    """One window, one way of grabbing it, one way of comparing two grabs."""

    def __init__(self, app, view):
        self.app, self.view = app, view

    def pump(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            self.app.processEvents()
            time.sleep(0.005)

    def shot(self):
        from PyQt6.QtGui import QImage
        img = self.view.grab().toImage().convertToFormat(
            QImage.Format.Format_RGB32)
        w, h = img.width(), img.height()
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        return np.frombuffer(ptr, np.uint8).reshape(
            h, img.bytesPerLine() // 4, 4)[:, :w, :3].astype(float)

    @staticmethod
    def differs(a, b) -> int:
        """How many pixels differ by more than eight levels.

        Eight rather than one: a browser does not redraw a picture to the
        same bits twice, and an audit that counts every last bit finds a
        difference everywhere and means nothing.
        """
        return int((np.abs(a - b).max(axis=2) > 8).sum())

    def js(self, code: str, wait: int = 0):
        from PyQt6.QtCore import QTimer, QEventLoop
        box, loop = {}, QEventLoop()
        QTimer.singleShot(wait, lambda: self.view.page().runJavaScript(
            code, lambda r: (box.setdefault("r", r), loop.quit())))
        QTimer.singleShot(30000, loop.quit)
        loop.exec()
        return box.get("r")


def report(rows, findings, what: str) -> None:
    print(f"\n  {what}")
    print("  " + "-" * 76)
    print(f"  {'control':30s} {'moved':>9s} {'left':>8s}  verdict")
    for name, moved, left, verdict in rows:
        m = "—" if moved is None else str(moved)
        left_s = "—" if left is None else str(left)
        print(f"  {name:30s} {m:>9s} {left_s:>8s}  {verdict}")
    if findings:
        print(f"\n  {len(findings)} thing(s) to look at:")
        for line in findings:
            print("    * " + line)


# --------------------------------------------------------------- the window
def audit_window(bench, w, gamut_app) -> list:
    """Every setting the window remembers, moved and put back.

    The list comes from the window itself. `_persisted()` is the table it
    already keeps of every control worth remembering -- a control missing
    from it is one the window forgets between runs, which is its own bug --
    and `_shape_controls()` adds the ones that belong to a single shape.
    """
    from PyQt6.QtWidgets import QSlider, QCheckBox, QComboBox

    rows, findings = [], []
    seen = set()

    def move_and_restore(key, widget):
        kind = ("slider" if isinstance(widget, QSlider) else
                "check" if isinstance(widget, QCheckBox) else
                "combo" if isinstance(widget, QComboBox) else None)
        if kind is None:
            return
        # A CONTROL THAT IS NOT ON SCREEN IS NOT ASKED. The window hides the
        # ones whose shape is not loaded -- "a control for something that does
        # not exist is worse than no control" -- and pressing one anyway
        # reports it as doing nothing, which is the window being right.
        if not widget.isVisible():
            rows.append((key, None, None, "not on screen, so not asked"))
            return
        # NOTHING LEFT MOVING FROM THE CONTROL BEFORE THIS ONE. Turning the
        # movement on is itself one of the settings, and everything tested
        # after it was being measured on a turning picture.
        if getattr(w, "_spin_on", None) is not None and w._spin_on.isChecked():
            w._spin_on.setChecked(False)
            # LONG ENOUGH FOR IT TO ACTUALLY STOP. At 1.2 seconds the next
            # control was still being measured on a turning picture, and
            # reported the identical pixel count as the one that started it.
            bench.pump(3.0)
        parent = NEEDS.get(key)
        put_back_parent = None
        if parent and not parent.startswith("_"):
            switch = getattr(w, "_" + parent, None)
            if switch is not None and not switch.isChecked():
                switch.setChecked(True)
                put_back_parent = switch
                bench.pump(2.0)
        bench.pump(0.8)
        before = bench.shot()
        if kind == "slider":
            was = widget.value()
            lo, hi = widget.minimum(), widget.maximum()
            to = lo if abs(was - hi) < abs(was - lo) else hi
            widget.setValue(to)
            widget.sliderReleased.emit()
        elif kind == "check":
            was = widget.isChecked()
            widget.setChecked(not was)
        else:
            was = widget.currentIndex()
            to = (was + 1) % max(1, widget.count())
            widget.setCurrentIndex(to)
        bench.pump(2.4)
        moved = bench.differs(before, bench.shot())
        if kind == "slider":
            widget.setValue(was)
            widget.sliderReleased.emit()
        elif kind == "check":
            widget.setChecked(was)
        else:
            widget.setCurrentIndex(was)
        bench.pump(2.4)
        left = bench.differs(before, bench.shot())
        if put_back_parent is not None:
            put_back_parent.setChecked(False)
            bench.pump(1.2)
        why = WINDOW_ACTIONS.get(key)
        if why:
            verdict = f"as intended — {why}"
        elif moved < 600:
            verdict = "DOES NOTHING"
            findings.append(f"{key}: moving it changed {moved} px")
        elif left > 4000:
            verdict = "DOES NOT COME BACK"
            findings.append(f"{key}: putting it back left {left} px different")
        else:
            verdict = "works"
        rows.append((key, moved, left, verdict))

    for key, widget, _kind, _default in w._persisted():
        # THE EXPLANATION FOLDS ARE NOT PICTURE CONTROLS. Every ⓘ in the
        # window is remembered as open or closed, which is right -- and what
        # it opens is a paragraph of text in the panel, not anything in the
        # picture. Asked here they would all report "does nothing", which is
        # true and useless, and would bury a control that really does.
        if key.startswith("hint") or key in seen or widget is None:
            continue
        seen.add(key)
        move_and_restore(key, widget)
    for key, (widget, _read) in w._shape_controls().items():
        if widget is None or key in seen:
            continue
        seen.add(key)
        move_and_restore(key, widget)
    report(rows, findings, "THE WINDOW'S OWN SETTINGS")
    return findings


# ------------------------------------------------------- the see-through work
def audit_transparency(bench) -> list:
    """Are the see-through surfaces sorted, and are they still see-through?

    Two questions, and the second is the one that catches a fix that is not
    one: a picture can be made to match a correctly ordered reference by
    quietly going opaque, and that has happened here.
    """
    findings = []
    how = bench.js("window.cqOrder && JSON.stringify(window.cqOrder.how())")
    how = json.loads(how) if how else {}
    print("\n  THE SEE-THROUGH WORK")
    print("  " + "-" * 76)
    print(f"  {how}")
    if not how:
        print("  no ordering engine on this page — nothing to ask")
        return findings
    if how.get("surfaces", 0) > 1 and how.get("pooled", 0) != how["surfaces"]:
        # NOT AUTOMATICALLY A FAULT: shapes lit differently are declined on
        # purpose, because one surface has one light. It is worth printing so
        # somebody can say which case this is.
        print(f"  {how['surfaces']} see-through surfaces and "
              f"{how.get('pooled', 0)} pooled — expected when they are lit "
              f"differently, a finding otherwise")
    if not how.get("fast", True):
        findings.append("the ordering engine has fallen back to its slow path")
    return findings


# ----------------------------------------------------------- a saved page
def audit_page(bench, path: pathlib.Path) -> list:
    from PyQt6.QtCore import QUrl, QTimer, QEventLoop

    loop = QEventLoop()
    bench.view.loadFinished.connect(
        lambda ok: QTimer.singleShot(8000, loop.quit))
    bench.view.load(QUrl.fromLocalFile(str(path.resolve())))
    QTimer.singleShot(60000, loop.quit)
    loop.exec()

    def still():
        bench.js("""
        (function () {
          var n = 0;
          while (window.cqSpin && window.cqSpin.moving
                 && window.cqSpin.moving() && n++ < 3) {
            var b = document.querySelector('button[data-cq="play"]');
            if (!b) break;
            b.click();
          }
          if (window.cqSpin && window.cqSpin.set)
            window.cqSpin.set({on: false});
        })();""")
        bench.js("1", 900)

    def press(what):
        bench.js('(function () { var b = document.querySelector('
                 '\'button[data-cq="%s"]\'); if (b) b.click(); })();' % what)
        bench.js("1", 1300)

    still()
    press("more")
    bench.js("1", 1200)
    found = bench.js("""
    JSON.stringify([].slice.call(
      document.querySelectorAll('button[data-cq]')).map(function (b) {
        return {what: b.getAttribute('data-cq'), text: b.textContent.trim(),
                shown: !!(b.offsetWidth || b.offsetHeight)};
      }).filter(function (c) { return c.shown; }));""")
    controls = json.loads(found or "[]")

    still()
    a = bench.shot()
    bench.js("1", 1000)
    floor = bench.differs(a, bench.shot())
    was = bench.shot()
    press("in")
    press("out")
    still()
    redraw = bench.differs(was, bench.shot())
    threshold = max(floor * 3 + 400, redraw * 2 + 600)
    print(f"\n  {path.name}")
    print("  " + "-" * 76)
    print(f"  {len(controls)} controls on screen; a still page moves {floor} px"
          f", a redraw that changes nothing moves {redraw} px, so nothing "
          f"under {threshold} px counts")
    if floor > 3000:
        print("  THE PAGE WILL NOT SIT STILL — nothing here is a result")
        return [f"{path.name}: will not sit still"]

    rows, findings = [], []
    for c in controls:
        what = c["what"]
        undo = opposite_of(what)
        kind = ("step" if undo else "preset" if what in PRESETS else
                "action" if (what in ACTIONS or what.split("-")[0] in ACTIONS)
                else "switch")
        if kind == "preset":
            press("home")
        still()
        before = bench.shot()
        press(what)
        still()
        moved = bench.differs(before, bench.shot())
        if kind == "step":
            press(undo)
        elif kind == "switch":
            press(what)
        elif kind == "preset":
            press("home")
        still()
        left = bench.differs(before, bench.shot())
        if kind == "action":
            why = ACTIONS.get(what) or ACTIONS.get(what.split("-")[0])
            verdict = f"as intended — {why}"
        elif moved <= threshold and kind == "step" and left > threshold:
            verdict = "at its limit; its opposite moves it"
        elif moved <= threshold:
            verdict = "DOES NOTHING"
            findings.append(f"{path.name}: {what} ({c['text']}) moved "
                            f"{moved} px")
        elif left > threshold:
            verdict = "DOES NOT COME BACK"
            findings.append(f"{path.name}: {what} ({c['text']}) left "
                            f"{left} px different")
        else:
            verdict = "works"
        rows.append((f"{what} [{kind}]", moved, left, verdict))
    report(rows, findings, f"CONTROLS ON {path.name}")
    findings += audit_transparency(bench)
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--window", action="store_true",
                    help="only the window's own settings")
    ap.add_argument("--pages", action="store_true",
                    help="only saved pages")
    ap.add_argument("--dir", default=str(HERE.parent / "docs" / "pages"),
                    help="where the saved pages are")
    ap.add_argument("--list", action="store_true",
                    help="say what would be tested and stop")
    args = ap.parse_args(argv)
    both = not (args.window or args.pages)

    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    QSettings("MeasuredGamutViewer", "MeasuredGamutViewer").clear()
    import gamut_app

    # THE PROGRAM NAME HAS TO BE PASSED. Handed an empty list, Qt's own
    # command line never initialises and the web view complains before it
    # draws anything.
    app = QApplication([sys.argv[0]])
    w = gamut_app.GamutApp([])
    w.resize(1400, 940)
    w.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.ask = staticmethod(lambda *a, **k: True)
    bench = Bench(app, w._view)
    bench.pump(2.0)

    pages = sorted(pathlib.Path(args.dir).glob("*.html"))
    if args.list:
        print("The window's settings, from its own table:")
        for key, widget, kind, _d in w._persisted():
            if widget is not None:
                print(f"  {key}  ({kind})")
        print(f"\nSaved pages under {args.dir}:")
        for p in pages:
            print(f"  {p.name}")
        print("\nControls on a page are read from the page itself, so a "
              "control added to one is audited without touching this file.")
        return 0

    findings = []
    if both or args.window:
        chart = DEMO / "Glossy-paper.ti3"
        if not chart.exists():
            print(f"no demo chart at {chart}")
            return 1
        w._load(chart)
        bench.pump(3.0)
        # A SECOND SHAPE AND A COMPARISON, because half these settings are
        # about comparing and have nothing to say about one chart on its own.
        second = DEMO / "Matte-paper.ti3"
        if second.exists():
            w._load(second)
            bench.pump(3.0)
        for i in range(w._compare.count()):
            got = w._compare.itemData(i)
            if got and got[0] == "space":
                w._compare.setCurrentIndex(i)
                w._on_compare_changed()
                break
        bench.pump(3.0)
        # An outline on screen, or the outline's colour has nothing to colour.
        if getattr(w, "_style_second", None) is not None:
            at = w._style_second.findData("mesh")
            if at >= 0:
                w._style_second.setCurrentIndex(at)
        bench.pump(2.5)
        findings += audit_window(bench, w, gamut_app)
    if both or args.pages:
        if not pages:
            print(f"no saved pages under {args.dir} — write some with "
                  f"scripts/make_sample_pages.py first")
            return 1
        for p in pages:
            findings += audit_page(bench, p)

    print("\n" + "=" * 78)
    if findings:
        print(f"{len(findings)} thing(s) to look at:")
        for line in findings:
            print("  * " + line)
        print("\nA control that changes nothing is either broken or an action "
              "-- if it is an action, name it in ACTIONS with the reason, and "
              "make the reason a true one.")
        return 1
    print("Every control moved the picture and put it back.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
