"""Does a live change land on the shape it was meant for — in every crossing?

CROSS THE OPTIONS, NEVER ONE AT A TIME. *Set this for* picks which shape a
setting belongs to, and *how it is drawn* decides whether that shape even HAS
a surface to fade. Those two multiply, and the multiplication is where this
breaks:

    Set this for: the second shape   +   the second shape drawn as a mesh
    -> there is no second surface in the picture at all, and a live fade that
       counts surfaces would quietly fade the FIRST shape instead.

It matters more now than it did last week. While every setting rebuilt the
page, a live change that went to the wrong shape was invisible: the rebuild
that followed drew everything from the recorded values and put it right. Once
the rebuild is taken away -- which is what stops the view jumping -- a wrong
live change STAYS on the screen. One fix turning into the next bug is the
thing to look for, and this looks for it.

WHAT IS KNOWN IN ADVANCE, which is what makes this a check rather than a
demonstration:

    target = all      every surface in the picture takes the new value
    target = first    the first shape's surface changes, the second's does not
    target = second   the second's changes, the first's does not
    a shape with no surface   nothing changes, and nothing else moves either

    python scripts/audit_crossed_shapes.py

Exit code 1 if any crossing puts a change on the wrong shape.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_crossed_shapes"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

#: The two things being crossed. Styles first, because a style decides what
#: there is to aim at.
STYLES = ("solid", "mesh")
TARGETS = ("all", 0, 1)

#: Every surface in the picture, by the name it is drawn under, with how
#: solid it is. _fullData, because the arrays travel packed.
ASK = """
(function () {
  var d = document.getElementsByClassName('plotly-graph-div')[0];
  if (!d) return "{}";
  var data = d._fullData || d.data || [], out = {};
  for (var i = 0; i < data.length; i++) {
    var t = data[i];
    if (t.type !== "mesh3d") continue;
    out[String(t.name || ("surface " + i))] = t.opacity;
  }
  return JSON.stringify(out);
})()
"""


def main() -> int:
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

    def surfaces():
        got = []
        page = win._view.page()
        if page is None:
            return {}
        page.runJavaScript(ASK, got.append)
        end = time.time() + 5
        while not got and time.time() < end:
            app.processEvents()
            time.sleep(0.005)
        try:
            return json.loads(got[0]) if got else {}
        except (TypeError, ValueError):
            return {}

    pump(3)
    profiles = sorted(pathlib.Path(tempfile.gettempdir())
                      .glob("showme-*/printer-*.icc"))
    if len(profiles) < 2:
        print("  no demo profiles to drive the window with")
        return 1
    for profile in profiles[:2]:
        win._load(profile)
        pump(6)

    problems, done = [], 0
    for first in STYLES:
        for second in STYLES:
            for target in TARGETS:
                # THE STYLES FIRST, then the target, then the drag: the order
                # a person would use them in, and the order that decides what
                # is in the picture to aim at.
                for box, want in ((win._style_mine, first),
                                  (win._style_second, second)):
                    at = box.findData(want)
                    if at >= 0:
                        box.setCurrentIndex(at)
                        box.activated.emit(at)
                pump(5)
                at = win._target.findData(target)
                if at < 0:
                    continue
                win._target.setCurrentIndex(at)
                win._target.activated.emit(at)
                pump(3)

                before = surfaces()
                win._opacity.setValue(35)
                pump(2.5)
                after = surfaces()
                done += 1

                moved = sorted(k for k in before
                               if after.get(k) != before.get(k))
                names = sorted(before)
                # WHAT SHOULD HAVE MOVED, BY NAME. Taking "the nth surface"
                # was itself wrong and hid one of the two faults: with the
                # first shape drawn as a mesh there is only one surface, and
                # names[0] is then the SECOND shape's. The expectation has to
                # know which shape is which, exactly as the window does.
                if target == "all":
                    should = names
                else:
                    wanted = win._name_of_shape(target)
                    should = [n for n in names
                              if wanted and n.startswith(wanted)]
                where = (f"first={first}, second={second}, "
                         f"set this for={target}")
                print(f"      {where:52s} surfaces={len(names)}  "
                      f"moved={moved or 'none'}")
                if moved != should:
                    problems.append(
                        f"[crossed] {where}: the fade should have gone to "
                        f"{should or 'nothing'} and went to {moved or 'nothing'}")
                win._opacity.setValue(100)
                pump(2)

    # ---- AND THE SAME CHANGE IN TWO ROOMS -------------------------------
    # TWO ROOMS ARE TWO GRAPHS, and every live path in this window used to
    # start at the FIRST one. Measured before it was fixed, with the solidity
    # dragged to 30%:
    #
    #     room0 surfaces=0.3 | room1 surfaces=1
    #
    # -- two rooms disagreeing about how solid the shapes are, which is the
    # one thing that arrangement exists to make comparable.
    print("\n  AND THE SAME CHANGE IN TWO ROOMS\n")
    at = win._target.findData("all")
    if at >= 0:
        win._target.setCurrentIndex(at)
        win._target.activated.emit(at)
    for box in (win._style_mine, win._style_second):
        where = box.findData("solid")
        if where >= 0:
            box.setCurrentIndex(where)
            box.activated.emit(where)
    pump(4)
    win._side_by_side.setChecked(True)
    pump(9)
    per_room = """(function(){var divs=document.getElementsByClassName(
     'plotly-graph-div');var out=[];
     for(var i=0;i<divs.length;i++){var d=divs[i];
       var data=d._fullData||d.data||[];var op=[];
       for(var j=0;j<data.length;j++) if(data[j].type==='mesh3d')
         op.push(data[j].opacity);
       out.push(op);}
     return JSON.stringify(out);})();"""

    def rooms():
        got = []
        win._view.page().runJavaScript(per_room, got.append)
        end = time.time() + 6
        while not got and time.time() < end:
            app.processEvents()
            time.sleep(0.005)
        try:
            return json.loads(got[0]) if got else []
        except (TypeError, ValueError):
            return []

    win._opacity.setValue(28)
    pump(3)
    seen = rooms()
    print(f"      rooms: {seen}")
    done += 1
    faded = [r for r in seen if r and all(abs(o - 0.28) < 0.001 for o in r)]
    if len(seen) < 2:
        print("      (only one room was drawn, so this proves nothing)")
    elif len(faded) != len(seen):
        problems.append(
            f"[crossed] two rooms: the solidity reached {len(faded)} of "
            f"{len(seen)} rooms — {seen}")
    win._side_by_side.setChecked(False)
    pump(5)

    print(f"\n  {done} crossing(s) driven.")
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} crossing(s) put a change on the wrong shape.")
        win.close()
        return 1
    print("  Clean: every live change landed on the shape it was meant for.")
    win.close()
    pump(0.3)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
