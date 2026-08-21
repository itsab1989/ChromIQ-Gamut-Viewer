"""Which section decides how wide the left column is — and does it move?

ASKED IN AS MANY WORDS, over a window that had grown a second time: "the left
panel became wider again for whatever reason" and "is it because of the what
this is telling you section or something in how it looks?" A guess is no
answer to that. This prints the number every group asks for, names the one the
column is sized from, and then does the things a person does — opens a run,
switches the appearance, folds and unfolds — and prints it again, so a section
that grows LATER is named rather than suspected.

    python scripts/audit_width.py

Exit code 1 if the column ever ends up wider than it started.
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
sys.argv = ["audit_width"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()


def main() -> int:
    from PyQt6.QtWidgets import QApplication, QGroupBox, QScrollArea

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
    area = win.findChild(QScrollArea)
    column = area.widget()

    def table(where):
        rows = []
        for box in column.findChildren(QGroupBox):
            body = getattr(box, "body", None)
            rows.append((
                (box.title() or "(no name)")[:38],
                box.minimumSizeHint().width(),
                body.minimumSizeHint().width() if body is not None else 0,
                "open" if getattr(box, "_fold_open", True) else "shut"))
        rows.sort(key=lambda r: -max(r[1], r[2]))
        print(f"\n  {where}: the column is {column.width()} wide, and asks "
              f"for {column.minimumSizeHint().width()} for itself")
        for name, own, inside, fold in rows[:6]:
            print(f"      {name:40s} heading {own:4d}   contents {inside:4d}"
                  f"   {fold}")
        return column.width()

    started = table("as it opens")
    seen = [("as it opens", started)]

    import demo_profiles
    profiles = demo_profiles.the_run_of_profiles()
    if len(profiles) >= 2:
        win._timeline.add(profiles)
        pump(7)
        seen.append(("with a run open", table("with a run open")))
        win._timeline._with_shapes.setChecked(True)
        pump(4)
        seen.append(("with the shapes on", table("with the shapes on")))

    for box in column.findChildren(QGroupBox):
        if hasattr(box, "_refold"):
            box._fold_open = not box._fold_open
            box._refold()
    pump(2)
    seen.append(("everything folded the other way",
                 table("everything folded the other way")))
    for box in column.findChildren(QGroupBox):
        if hasattr(box, "_refold"):
            box._fold_open = True
            box._refold()
    pump(2)
    seen.append(("everything open", table("everything open")))

    # THE APPEARANCE, because a theme change re-polishes every widget and
    # that is when stylesheet padding lands -- the one moment a section can
    # honestly answer a different width than it did a second ago.
    was = win._appearance
    win._set_appearance("light" if was == "dark" else "dark")
    pump(3)
    seen.append(("after the appearance changed",
                 table("after the appearance changed")))
    win._set_appearance(was)
    pump(3)
    seen.append(("and back again", table("and back again")))

    print("\n  WHAT THE COLUMN DID\n")
    for where, width in seen:
        mark = "" if width == started else f"   ← moved by {width - started:+d}"
        print(f"      {where:34s} {width:4d}{mark}")
    win.close()
    pump(0.3)
    grew = [w for _s, w in seen if w != started]
    if grew:
        print(f"\n  The column moved: {started} → {max(grew)}.")
        return 1
    print("\n  Clean: the column is sized once and never moves.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
