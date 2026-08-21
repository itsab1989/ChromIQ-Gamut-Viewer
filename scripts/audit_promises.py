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

#: What the page is drawing, in one string. THE PROMISE IS MEASURED, NOT
#: LOOKED UP. A first version kept a list of "the live ones" in this file and
#: compared names against it -- which is a check phrased in terms of the thing
#: it guards: the day a slider stops being live, the list still says it is and
#: the audit stays quiet. So the slider is dragged and the page is asked.
ASK = """
(function () {
  var d = document.getElementsByClassName('plotly-graph-div')[0];
  if (!d) return "no picture";
  var data = d._fullData || d.data || [];
  var seen = [];
  for (var i = 0; i < data.length; i++) {
    var t = data[i], m = t.marker || {};
    seen.push([t.type, (t.x || []).length, t.opacity,
               JSON.stringify(t.lighting || null),
               JSON.stringify(t.lightposition || null),
               JSON.stringify(m.size || null), m.opacity]);
  }
  return JSON.stringify(seen);
})()
"""


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
    # SOMETHING TO PROMISE ABOUT. A window with nothing open draws nothing,
    # and a slider dragged over an empty scene changes nothing for an honest
    # reason -- which would have made this audit pass by drawing no picture.
    import tempfile
    import demo_profiles
    profiles = demo_profiles.the_run_of_profiles()
    if profiles:
        win._load(profiles[0])
        pump(6)
    win._manual_light.setChecked(True)
    pump(4)

    def drawing():
        got = []
        page = win._view.page()
        if page is None:
            return "no page"
        page.runJavaScript(ASK, got.append)
        end = time.time() + 4
        while not got and time.time() < end:
            app.processEvents()
            time.sleep(0.005)
        return got[0] if got else "no answer"

    def moves_the_picture(slider):
        """Drag it -- valueChanged and no release -- and ask the page."""
        was, url = slider.value(), win._view.url().toString()
        before = drawing()
        lo, hi = slider.minimum(), slider.maximum()
        slider.setValue(hi if was < (lo + hi) // 2 else lo)
        pump(2.0)
        changed = drawing() != before and win._view.url().toString() == url
        slider.setValue(was)
        pump(1.2)
        return changed

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

    # WHICH SLIDERS A HINT IS SPEAKING FOR. Not "every slider under the same
    # group": the first version asked the hint's parent, which for a hint
    # written straight into a section is the whole section -- so the lighting
    # hint's promise was tested against the cross-section height, the rings,
    # the fineness and both fade sliders, and reported nine broken promises
    # where there was none. An audit that cries wolf is worse than no audit:
    # the next person reads past it.
    #
    # A hint is named for what it explains (hint_light_hint, hint_detail_hint),
    # so that name is the link, and a hint whose name matches nothing is
    # listed as not judged rather than guessed at.
    # The light sliders live in a dictionary rather than in attributes, so
    # they have no name to report -- and "slider(s) that do not: ?" is not a
    # finding anybody can act on.
    for key, (slider, _lo, _hi) in getattr(win, "_light_sliders", {}).items():
        by_widget.setdefault(slider, f"light: {key}")
    speaks_for = {"light": [s for s, _lo, _hi
                            in getattr(win, "_light_sliders", {}).values()]}
    for widget, attr in by_widget.items():
        speaks_for.setdefault(attr.lstrip("_"), []).append(widget)

    unjudged = []
    for hint in win.findChildren(gamut_app.Hint):
        text = hint.toolTip() + " " + getattr(hint, "_text", "")
        if not LIVE.search(text):
            continue
        checked += 1
        name = hint.objectName()
        key = name[len("hint_"):-len("_hint")] if name.startswith("hint_") \
            and name.endswith("_hint") else ""
        near = speaks_for.get(key, [])
        if not near:
            unjudged.append(name or "an unnamed hint")
            continue
        dead = [by_widget.get(s, "?") for s in near
                if not moves_the_picture(s)]
        if dead:
            problems.append(
                f"[promise] “{name}” says the picture moves as you drag, over "
                f"slider(s) that do not: {', '.join(sorted(set(dead)))}")

    print(f"\n  {checked} promise(s) found in the window's own words.")
    if unjudged:
        print("  not judged, because the hint's name matches no control: "
              + ", ".join(sorted(set(unjudged))))
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
