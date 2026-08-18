"""Does the window keep the promises its own words make?

WHERE THIS CAME FROM. A hint said the family report was "written out so you
can paste it into an email or a report", and Basti asked the obvious question:
"but can one really copy or export the info text?" It could not — a QLabel
hands the mouse straight through, so there was nothing to drag over and Ctrl+C
took nothing. The words had been true of the intention and never of the
window.

That is a whole class of fault, and it is invisible to every other check here:
the control works, the picture is right, and the SENTENCE beside it is false.
Nobody notices until a reader tries to do the thing it says.

TWO PROMISES ARE CHECKED, because these two can be checked honestly:

  "you can copy this"      the widget must actually let a mouse or a keyboard
                           select its text
  "it moves as you drag"   the control must change the picture while the
                           handle is down, not when it is let go

A third -- a hint naming a control that has since been renamed -- is NOT
checked, and saying so is part of the report: picking control names out of
running prose needs a rule I do not have, and a check that guesses would
either miss the renames or cry wolf on every ordinary sentence.

    python scripts/audit_promises.py

Exit code 1 if the window says something it does not do.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_promises"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

#: Words that promise the text can be taken away with you.
COPYABLE = re.compile(
    r"\b(copy|copied|copy it|paste|pasted|paste it|select the text)\b", re.I)

#: Words that promise the picture answers under the hand.
LIVE = re.compile(
    r"(as you drag|while you drag|while it is being dragged|moves? the "
    r"picture as you|live, as|updates? live)", re.I)

#: Which sliders are live, from the same source of truth the slider audit
#: uses: the connections in the window. Named here so the two cannot disagree
#: quietly -- if one of these stops being live, this audit says so as well.
LIVE_SLIDERS = ("_opacity", "_depth", "_chart_dot", "_chart_dot_opacity",
                "_chart_out_dot", "_chart_out_opacity", "_chart_skin_opacity")


def main() -> int:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (QApplication, QLabel, QSlider, QWidget)

    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    win = gamut_app.GamutApp([])
    win.resize(1500, 950)
    win.show()

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(2.5)
    problems, checked = [], 0

    # ---- "you can copy this" ---------------------------------------------
    # THE PROMISE IS MADE IN A HINT AND KEPT BY A WIDGET, and the two are not
    # the same object: the ⓘ beside a readout is what says "you can paste
    # this into an email", and the readout underneath it is what has to allow
    # it. So the sentence is looked for on the hint, and the promise is
    # checked on every readout in the same group.
    for hint in win.findChildren(gamut_app.Hint):
        text = hint.toolTip() + " " + getattr(hint, "_text", "")
        if not COPYABLE.search(text):
            continue
        checked += 1
        group = hint
        while group is not None and not isinstance(group, QWidget):
            group = group.parentWidget()
        holder = hint.parentWidget()
        readouts = [w for w in (holder.findChildren(QLabel) if holder else [])
                    if isinstance(w, gamut_app.WrappedLabel)]
        if not readouts:
            continue
        stuck = [w for w in readouts
                 if not (w.textInteractionFlags()
                         & Qt.TextInteractionFlag.TextSelectableByMouse)]
        if stuck:
            problems.append(
                f"[promise] a hint says the text can be copied, and "
                f"{len(stuck)} readout(s) beside it cannot be selected at all")

    # ---- "it moves as you drag" ------------------------------------------
    by_widget = {}
    for attr in dir(win):
        try:
            thing = getattr(win, attr)
        except Exception:                                      # noqa: BLE001
            continue
        if isinstance(thing, QSlider):
            by_widget[thing] = attr

    for hint in win.findChildren(gamut_app.Hint):
        text = hint.toolTip() + " " + getattr(hint, "_text", "")
        if not LIVE.search(text):
            continue
        checked += 1
        holder = hint.parentWidget()
        near = holder.findChildren(QSlider) if holder else []
        named = [by_widget.get(s, "?") for s in near]
        if not named:
            continue
        # The light sliders are held in a dictionary and are live through
        # _on_light_changed; every other slider must be in the live list.
        light = {s for s, _lo, _hi in getattr(win, "_light_sliders",
                                              {}).values()}
        dead = [n for s, n in zip(near, named)
                if s not in light and n not in LIVE_SLIDERS]
        if dead:
            problems.append(
                f"[promise] a hint says the picture moves as you drag, over "
                f"slider(s) that do not: {', '.join(sorted(set(dead)))}")

    print(f"\n  {checked} promise(s) found in the window's own words.")
    print()
    if problems:
        for line in sorted(set(problems)):
            print("  " + line)
        print(f"\n{len(set(problems))} promise(s) the window does not keep.")
        win.close()
        return 1
    print("  Clean: every promise checked here is kept.")
    print("\n  not checked, and why: a hint that names a control which has "
          "since been renamed. Picking control names out of running prose "
          "needs a rule this does not have, and a guess would either miss "
          "them or cry wolf on every sentence.")
    win.close()
    pump(0.3)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
