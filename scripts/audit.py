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

A CONTROL IS NOT ONLY ITS PIXELS. Five things are read before and after every
press: the picture, the word on the button, whether the button is holding
itself down (`aria-pressed`), the figure the page writes out beside it, and
what the drawing itself has been told, shape by shape. That matters because
plenty of perfectly good controls change no pixels at the moment they are
pressed:

  * how fast the shape turns, and how far it swings, show themselves only
    while it is moving -- and this audit measures it stopped. They were
    excused on exactly that ground, which means they were never tested. They
    each write their value on the page, so now they are read.
  * a shape sitting inside another one, with the outer one solid, cannot be
    seen at all -- so fading it changes nothing visible. Asked of the drawing
    rather than of the picture, the answer is exact.

HOW IT AVOIDS LYING TO YOU. Five rules, each of which was learned by this
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
  5. EVERY NAME IN THIS FILE IS CHECKED AGAINST A CONTROL THAT EXISTS. The
     excuse tables name controls as strings, and six of them named switches
     in the SAVE DIALOG rather than the buttons those switches produce --
     `fullscreen` where the button is `full`, `picture` where it is `shot`.
     An excuse matching nothing excuses nothing while looking as though it
     does, which is this audit committing the exact fault it was written to
     catch. `python/test_audit_script.py` fails on a name no control has.

THE ONE IT USED TO GET WRONG, and how, because the shape of the mistake is
worth more than the fix.

"Show the box and its grid" was reported as leaving ~314,000 pixels different
for several releases, and it does not: on its own it leaves 0, with the camera
identical. The warning here used to say so and to tell you to go and check by
hand — which is honest, and is also an audit asking a person to do its job.

What actually happened: turning the shape leaves it at a new angle, on
purpose. The audit put the camera back between controls with `setCamera`,
which moves what is on SCREEN and leaves the camera stored in the LAYOUT
where it was — so the first thing that relayouted the figure re-applied the
old angle and the shape jumped back, undoing the restore without a word. The
camera is now put back through `relayout`, which sets both.

The giveaway was in the numbers all along: "spin_on" and "grid_on" reported
the identical 314,313 pixels. One difference measured twice is not two
faults, and two independent controls agreeing to the pixel is not a
coincidence — it is a clue that the thing being measured belongs to neither
of them.

A finding is still a reason to go and look rather than a verdict. But an
audit that knows it cries wolf and says so in its own documentation has only
moved the work onto the reader; where the cause can be found, it is worth
finding.

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

# THE SETTINGS GO SOMEWHERE THROWAWAY, and this must happen before the
# window is built. A driver that uses the real store both destroys what
# the person using this application has chosen and leaves its own last
# state behind as their new preference -- which is how "the walls behind
# the shape are missing" was reported as a bug in the viewer. See
# python/prefs.py.
import prefs  # noqa: E402

prefs.use_a_scratch_store()

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
             "differ-less": "differ-more", "differ-more": "differ-less",
             # The movement's own steppers -- one pair for both directions
             # together, and a pair each for left-and-right and up-and-down
             # when the page offers a speed for each. These were treated as
             # switches, so pressing one twice was expected to put it back
             # and of course did not.
             "slower": "faster", "faster": "slower",
             "turn-slower": "turn-faster", "turn-faster": "turn-slower",
             "turn-narrower": "turn-wider", "turn-wider": "turn-narrower",
             "tilt-slower": "tilt-faster", "tilt-faster": "tilt-slower",
             "tilt-narrower": "tilt-wider", "tilt-wider": "tilt-narrower"}

#: Controls that jump to a fixed view. Pressing one twice changes nothing the
#: second time, so "put the view back" is what undoes them.
PRESETS = ("look-above", "look-front", "look-side", "look-angle")

#: Controls whose job is NOT to change the picture, each with the reason. A
#: control that changes nothing and is not named here is a finding. Adding a
#: name here is a claim you are making; make it a true one.
#: EVERY NAME IN HERE MUST BE A BUTTON THAT EXISTS. Six of them were not.
#: `fullscreen`, `picture`, `legend`, `remember`, `speed` and `sweep` are the
#: names of switches in the SAVE DIALOG, and the buttons those switches
#: produce on the page are called something else -- `full`, `shot`, `key`,
#: nothing at all, and a pair of steppers. So six excuses sat here matching
#: nothing, while the buttons they were meant to excuse were judged by the
#: ordinary rule. `test_audit_script.py` now fails on a name no button has.
#: `lr`, `ud` and `notes` USED TO BE IN HERE and are not any more. The first
#: two were excused as "chooses which way the movement goes", which cannot be
#: seen in a still picture -- but they hold themselves down when they are on,
#: and `aria-pressed` says so, so they are checked by that. `notes` shows and
#: hides the figures under the picture, which is 390,000 pixels of change:
#: it was excused as "opens the captions" and never needed to be.
ACTIONS = {
    "full": "asks the browser for the whole screen, which an embedded view "
            "does not have",
    "shot": "writes a PNG of the picture",
    "home": "puts the view back, and nothing has moved it",
    "shapes-back": "puts every shape back, and none has been changed",
    "play": "starts the movement, which this audit deliberately stops",
    "more": "opens and closes the panel this audit is reading",
}

#: Controls whose work is a NUMBER on the page rather than pixels in the
#: picture. Left of the arrow is the button, right of it is the readout it
#: writes to.
#:
#: WHY THIS IS BETTER THAN EXCUSING THEM. How fast the shape turns and how
#: far it swings only show themselves while it is moving, and this audit
#: measures with the movement stopped -- so judged by pixels they change
#: nothing, and the only honest verdict was "cannot be seen from here". Four
#: of them were excused on exactly that ground and were therefore never
#: tested at all.
#:
#: But each one writes what it did beside itself, in the words a reader
#: relies on, and that CAN be read: press it, the number moves; press its
#: opposite, the number comes back. So they are checked rather than excused,
#: and a stepper that stopped changing anything would now be caught.
READOUTS = {
    "slower": "speed", "faster": "speed",
    "turn-slower": "turn-speed", "turn-faster": "turn-speed",
    "turn-narrower": "turn-range", "turn-wider": "turn-range",
    "tilt-slower": "tilt-speed", "tilt-faster": "tilt-speed",
    "tilt-narrower": "tilt-range", "tilt-wider": "tilt-range",
    "cut-up": "cut-at", "cut-down": "cut-at",
    "agree-less": "agree-at", "agree-more": "agree-at",
    "differ-less": "differ-at", "differ-more": "differ-at",
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
    "agree": ("the shape drawn SOLID here contains every other shape on "
              "screen, so no part of its surface lies inside them and there "
              "is nothing for this to fade. Measured on the state below: "
              "0.0% of the glossy paper's surface -- 0 of 52,673 square Lab "
              "units -- agrees with both the matte paper and the comparison, "
              "and it comes to 0.0% against every one of the five built-in "
              "spaces, because the matte paper fits ENTIRELY inside the "
              "glossy one and a larger shape's boundary cannot lie inside a "
              "smaller shape it encloses. The 131 pixels that do move are the "
              "two wire cages, which are thin. Its opposite, `differ`, moves "
              "248,361 -- and on a saved page where the two shapes really do "
              "cross, this same control moves 55,756. THIS IS THE STATE'S "
              "DOING, NOT THE CONTROL'S: to exercise it here, the solid shape "
              "would have to be one that is not the largest on screen"),
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
def kind_of(widget) -> "str | None":
    """Which of the three ways of moving a control applies to this one."""
    from PyQt6.QtWidgets import QSlider, QCheckBox, QComboBox
    return ("slider" if isinstance(widget, QSlider) else
            "check" if isinstance(widget, QCheckBox) else
            "combo" if isinstance(widget, QComboBox) else None)


def window_controls(w) -> list:
    """Every control the run will move, in the order it will move them.

    ONE PLACE, BECAUSE `--list` IS A PROMISE. It listed the twenty-two ⓘ
    explanation folds -- which are remembered like any other setting, and
    which the run has always skipped on purpose -- so a third of the listing
    named work that was never going to happen. A listing that overstates
    what is checked is worse than no listing: somebody reads it, sees their
    new control in it, and concludes it was audited.

    The names come from the window, never from this file: `_persisted()` is
    the table it already keeps of everything worth remembering, and
    `_shape_controls()` adds the ones belonging to a single shape.
    """
    seen, out = set(), []
    for key, widget, _kind, _default in w._persisted():
        # THE EXPLANATION FOLDS ARE NOT PICTURE CONTROLS. Every ⓘ is
        # remembered as open or closed, which is right -- and what it opens
        # is a paragraph of text in the panel, not anything in the picture.
        # Asked here they would all report "does nothing", which is true and
        # useless, and would bury a control that really does.
        if key.startswith("hint") or key in seen or widget is None:
            continue
        if kind_of(widget) is None:
            continue
        seen.add(key)
        out.append((key, widget))
    for key, (widget, _read) in w._shape_controls().items():
        if widget is None or key in seen or kind_of(widget) is None:
            continue
        seen.add(key)
        out.append((key, widget))
    return out


def audit_window(bench, w, gamut_app) -> list:
    """Every setting the window remembers, moved and put back.

    The list comes from the window itself. `_persisted()` is the table it
    already keeps of every control worth remembering -- a control missing
    from it is one the window forgets between runs, which is its own bug --
    and `_shape_controls()` adds the ones that belong to a single shape.
    """
    rows, findings = [], []
    # THE ANGLE THE PICTURE OPENS AT, so every control is judged from the
    # same starting point rather than from wherever the one before it left
    # the shape.
    opening = bench.js(
        "JSON.stringify((function () {"
        "  var gd = document.querySelector('.js-plotly-plot');"
        "  var s = gd && gd._fullLayout && gd._fullLayout.scene;"
        "  var sc = s && s._scene;"
        "  return (sc && sc.getCamera ? sc.getCamera().eye"
        "                             : (s && s.camera && s.camera.eye));"
        "})());")
    try:
        opening_view = json.loads(opening) or {"x": 1.5, "y": 1.5, "z": 1.5}
    except (TypeError, ValueError):
        opening_view = {"x": 1.5, "y": 1.5, "z": 1.5}

    def move_and_restore(key, widget):
        kind = kind_of(widget)
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
        # AND THE SHAPE PUT BACK WHERE IT STARTED.
        #
        # Stopping the movement is not enough: it leaves the shape at
        # whatever angle it had reached, and the next control is then
        # measured against a picture that will never come back — because
        # redrawing does not restore a camera nobody stored. "Show the box
        # and its grid" was reported as leaving 314,150 pixels different by
        # exactly this, and on a page nothing had turned it leaves 0.
        # PUT BACK IN THE LAYOUT, NOT ONLY IN THE SCENE.
        #
        # setCamera moves what is on screen and leaves the camera STORED in
        # the layout where it was -- so the next thing that relayouts the
        # figure re-applies the old angle and the shape jumps back, undoing
        # this silently. That is the whole of the "grid_on does not come
        # back" finding this file has carried a warning about: "spin_on" left
        # the shape at a new angle, the restore looked like it worked, and
        # the first relayout inside the grid test put it back to where the
        # spin had left it. The two reported the identical number of pixels,
        # 314,313, which is what gave it away -- the same difference measured
        # twice, not two faults.
        bench.js("""
        (function () {
          var gd = document.querySelector('.js-plotly-plot');
          if (!gd || !window.Plotly) return;
          var eye = %s;
          Plotly.relayout(gd, {"scene.camera.eye": eye,
                               "scene.camera.center": {x: 0, y: 0, z: 0},
                               "scene.camera.up": {x: 0, y: 0, z: 1}});
        })();""" % json.dumps(opening_view))
        bench.pump(1.6)
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
            verdict = "DOES NOT COME BACK — test it on its own"
            findings.append(
                f"{key}: putting it back left {left} px different. Test it on "
                f"its own before believing it: a control tested after one that "
                f"leaves the movement running is measured on a turning shape.")
        else:
            verdict = "works"
        rows.append((key, moved, left, verdict))

    for key, widget in window_controls(w):
        move_and_restore(key, widget)
    report(rows, findings, "THE WINDOW'S OWN SETTINGS")
    return findings


# ------------------------------------------------------------- the layout
def audit_layout(bench, w) -> list:
    """Is anything in the controls column drawn outside the room it has?

    A control that is cut off is not found by pressing it: it works
    perfectly, changes the picture, and comes back -- and half of it is not
    on the screen. So the pressing audit above cannot see this class of
    fault at all, and it took a screenshot from somebody looking at the real
    window to notice that "How it looks" had lost its right-hand border and
    about four pixels of one row's ⓘ.

    The cause is worth knowing, because it will happen again: the column has
    a fixed width, the scroll area's horizontal scrollbar is deliberately
    off, and a tick's label cannot wrap. So one long label -- "Show what the
    comparison cannot print", 270 px of it -- made its section 372 px wide
    in a 356 px column, and the excess was simply cut.
    """
    from PyQt6.QtWidgets import QGroupBox, QScrollArea

    findings, rows = [], []
    areas = [a for a in w.findChildren(QScrollArea)
             if a.widget() is not None and a.isVisible()]
    for area in areas:
        port = area.viewport()
        for box in area.widget().findChildren(QGroupBox):
            if not box.isVisible():
                continue
            left = box.mapTo(port, box.rect().topLeft()).x()
            over = (left + box.width()) - port.width()
            name = (box.title() or "(untitled)")[:34]
            if over > 0:
                rows.append((name, box.width(), port.width(),
                             f"CUT OFF — {over} px past the right-hand edge"))
                findings.append(
                    f"the '{name}' section is {box.width()} px wide in a "
                    f"{port.width()} px column, so {over} px of it — its "
                    f"border, and whatever sits at that edge — is not drawn")
            else:
                rows.append((name, box.width(), port.width(), "fits"))
    print("\n  THE CONTROLS COLUMN")
    print("  " + "-" * 76)
    print(f"  {'section':36s} {'wide':>6s} {'room':>6s}  verdict")
    for name, wide, room, verdict in rows:
        print(f"  {name:36s} {wide:6d} {room:6d}  {verdict}")
    if not rows:
        print("  no sections found — has the column stopped being group boxes?")
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
    # DISCONNECTED AFTERWARDS. Connected and left, every page adds another
    # handler to the same view, and by the fourteenth page one load is
    # waking thirteen dead event loops.
    def loaded(_ok):
        QTimer.singleShot(8000, loop.quit)
    bench.view.loadFinished.connect(loaded)
    bench.view.load(QUrl.fromLocalFile(str(path.resolve())))
    QTimer.singleShot(60000, loop.quit)
    loop.exec()
    bench.view.loadFinished.disconnect(loaded)

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

    # IS THERE A DRAWING ON THIS PAGE AT ALL?
    #
    # One of the sample pages deliberately ships WITHOUT the drawing library,
    # to show what a reader sees when it never arrives — and its buttons are
    # still there, because the strip is written by the page and the library
    # is what failed. Every camera control on it does nothing, correctly, and
    # the audit reported ten faults on the one page whose whole subject is
    # that this can happen. Ten wrong findings is how an audit stops being
    # read.
    drawing = bench.js(
        "!!(window.Plotly && document.querySelector('.js-plotly-plot'))")

    still()
    a = bench.shot()
    bench.js("1", 1000)
    floor = bench.differs(a, bench.shot())
    was = bench.shot()
    press("in")
    press("out")
    still()
    redraw = bench.differs(was, bench.shot())
    # AND A REDRAW THIS PAGE ACTUALLY DOES.
    #
    # Zooming in and out is the cheapest control that provably returns, and
    # on a flat cross-section it does nothing at all -- so the floor came out
    # 0 and every real redraw on those pages looked like a fault. The cut is
    # their redraw: it rebuilds the outline from figures stored in the file,
    # deliberately rounded to a hundredth of a Lab unit to keep the page from
    # tripling in size. Coming back, every point lands within 0.005 of where
    # it was, which is a fiftieth of what a good instrument repeats to and
    # nothing anybody can see -- but it is about 1,700 pixels of antialiasing
    # along the edge, and no threshold taken from a page that never redraws
    # can tell that from a fault.
    #
    # So the floor is measured with it. The cut is checked independently by
    # its own readout, which returns to L* exactly, so this cannot hide a
    # broken one.
    if any(c["what"] == "cut-down" for c in controls):
        was = bench.shot()
        press("cut-down")
        press("cut-up")
        still()
        redraw = max(redraw, bench.differs(was, bench.shot()))
    threshold = max(floor * 3 + 400, redraw * 2 + 600)
    print(f"\n  {path.name}")
    print("  " + "-" * 76)
    print(f"  {len(controls)} controls on screen; a still page moves {floor} px"
          f", a redraw that changes nothing moves {redraw} px, so nothing "
          f"under {threshold} px counts")
    if floor > 3000:
        print("  THE PAGE WILL NOT SIT STILL — nothing here is a result")
        return [f"{path.name}: will not sit still"]
    if not drawing:
        print("  THERE IS NO DRAWING ON THIS PAGE. It carries its controls "
              "and no drawing library, which is what it is for — so nothing "
              "that moves a picture can do anything, and none of it is "
              "asked. What IS checked is that the page says so:")
        said = bench.js(
            "(function () { var t = document.body.innerText || '';"
            "  return t.indexOf('could not be drawn') >= 0"
            "      || t.indexOf('did not load') >= 0"
            "      || t.indexOf('viewer') >= 0; })();")
        print(f"    it tells the reader something went wrong: {bool(said)}")
        if not said:
            return [f"{path.name}: no drawing, and the page does not say so — "
                    f"a reader gets a row of buttons and an empty frame"]
        return []

    def words(what, where):
        """What the page SAYS about a control, beside what it draws.

        Four things a control can change that no pixel count will see:

          the word on the button itself;
          whether the button is holding itself down -- `aria-pressed`, which
            is what a screen reader announces;
          the figure the page writes out beside it;
          and what the drawing itself has been told: every shape's name,
            whether it is showing, and how solid it is.

        THE LAST ONE IS WHY A HIDDEN SHAPE STILL GETS TESTED. A page can hold
        one shape entirely inside another, and the outer one solid: fading
        the inner shape then changes not one pixel, and judged on the picture
        alone its perfectly good controls report "does nothing". Two did.
        Asked of the drawing instead, the answer is exact -- that shape's
        strength went from 1 to 0.9 -- whether or not anybody can see it.

        The rest is why four controls stopped being excused. "How fast it
        turns" cannot be seen in a still picture, so the only honest verdict
        used to be "not visible from here" -- and a control excused is a
        control never tested. It writes its speed on the page, and that can
        be read.
        """
        got = bench.js(
            "JSON.stringify((function () {"
            "  var b = document.querySelector('button[data-cq=\"%s\"]');"
            "  var r = %s;"
            "  var gd = document.querySelector('.js-plotly-plot');"
            "  var drawn = null;"
            # NOT SET IS THE SAME AS FULLY SOLID, and has to compare equal to
            # it. A control that fades a shape and puts it back leaves the
            # strength STATED at 1 where it had previously been left unsaid
            # -- the same picture, drawn the same way, described differently.
            # Read literally, that reported "the drawing is not back as it
            # was" for two controls that had left twelve pixels different out
            # of two million.
            "  if (gd && gd._fullData) drawn = gd._fullData.map(function (t) {"
            "    return [t.name || '', String(t.visible),"
            "            String(t.opacity === undefined ? 1 : t.opacity)];"
            "  });"
            "  return [b ? b.textContent.trim() : null,"
            "          b ? b.getAttribute('aria-pressed') : null,"
            "          r ? r.textContent.trim() : null,"
            "          drawn && JSON.stringify(drawn)];"
            "})());"
            % (what, ("document.querySelector('[data-cq=\"%s\"]')" % where)
               if where else "null"))
        try:
            return tuple(json.loads(got))
        except (TypeError, ValueError):
            return (None, None, None, None)

    rows, findings = [], []
    for c in controls:
        what = c["what"]
        undo = opposite_of(what)
        where = READOUTS.get(what)
        kind = ("step" if undo else "preset" if what in PRESETS else
                "action" if (what in ACTIONS or what.split("-")[0] in ACTIONS)
                else "switch")
        if kind == "preset":
            press("home")
        still()
        before, said = bench.shot(), words(what, where)
        press(what)
        still()
        moved = bench.differs(before, bench.shot())
        now = words(what, where)
        # DID IT DO ANYTHING AT ALL -- in the picture or in the words.
        did = moved > threshold or now != said
        # PUT IT BACK THE WAY ITS OWN KIND IS PUT BACK.
        #
        # A CYCLE IS FOUND, NOT LISTED. The page-colour button moves through
        # five colourings and names the one it is showing, so pressing it
        # twice lands three short of where it started -- and judged as a
        # switch it reported 42,244 pixels of "does not come back". Any
        # button that renames itself when pressed is walked round until its
        # own name comes back, which handles a two-state button and a
        # five-state one with the same rule, and a six-state one added later
        # without touching this file.
        rounds = 1
        if kind == "step":
            press(undo)
        elif kind == "preset":
            press("home")
        elif kind == "switch" and now[0] is not None and now[0] != said[0]:
            kind = "cycle"
            while rounds < 12 and words(what, where)[0] != said[0]:
                press(what)
                rounds += 1
        elif kind == "switch":
            press(what)
        still()
        left = bench.differs(before, bench.shot())
        back = words(what, where)
        returned = left <= threshold and back == said

        if kind == "action":
            why = ACTIONS.get(what) or ACTIONS.get(what.split("-")[0])
            verdict = f"as intended — {why}"
        elif not did and kind == "step" and (left > threshold or back != said):
            # AT THE END OF ITS RANGE, WHICH IS NOT BROKEN. A shape already
            # at full strength cannot be made stronger, and a sweep already
            # going right round cannot go wider. The pair is working if the
            # OTHER direction moves it, which the undo press has just shown
            # -- so press this one again to leave the page as it was found.
            press(what)
            still()
            verdict = "at its limit; its opposite moves it"
        elif not did:
            verdict = "DOES NOTHING"
            findings.append(
                f"{path.name}: {what} ({c['text']}) changed nothing — "
                f"{moved} px, the button still reads {said[0]!r}, and the "
                f"drawing was told nothing new")
        elif not returned:
            verdict = "DOES NOT COME BACK"
            why = ("the picture" if back[:3] == said[:3] else
                   "the picture and the words")
            findings.append(
                f"{path.name}: {what} ({c['text']}) left {left} px different "
                f"({why}); it reads {back[0]!r} where it read {said[0]!r}"
                + ("" if back[3] == said[3] else
                   ", and the drawing is not back as it was"))
        else:
            verdict = "works"
            if kind == "cycle":
                verdict = f"works — {rounds} presses round the cycle"
            elif now[2] is not None and now[2] != said[2]:
                verdict = f"works — {said[2]!r} → {now[2]!r} → back"
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
    # SAY IT AS IT HAPPENS. A full run takes the better part of an hour, and
    # redirected to a file Python holds every line in a buffer until the end
    # — so the one thing somebody wants from a long gate, knowing it is
    # getting somewhere, is exactly what they do not get.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):        # not a real stream
        pass

    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
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
        listed = window_controls(w)
        print(f"The window's settings, from its own table — {len(listed)} "
              f"that a run would move:")
        for key, widget in listed:
            note = ""
            if key in WINDOW_ACTIONS:
                note = "  — not expected to move the picture"
            elif key in NEEDS:
                note = f"  — needs {NEEDS[key].lstrip('_')} switched on first"
            print(f"  {key}  ({kind_of(widget)}){note}")
        # WHAT IS DELIBERATELY LEFT OUT, said out loud. A listing that shows
        # only what it checks is honest; one that also says what it skips,
        # and why, is the one somebody can disagree with.
        skipped = [k for k, wdg, _k, _d in w._persisted()
                   if wdg is not None and k.startswith("hint")]
        if skipped:
            print(f"\n  {len(skipped)} explanation folds (ⓘ) are not moved: "
                  f"each opens a paragraph of text in the panel, not anything "
                  f"in the picture.")
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
        # BEFORE ANYTHING IS PRESSED, while the window is as it opens.
        findings += audit_layout(bench, w)
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
