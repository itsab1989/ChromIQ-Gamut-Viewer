"""No explanation opens a window taller than the screen, and no hover is a wall.

    ../gv-venv/bin/python scripts/audit_the_panel_hovers_stay_short.py

WHY THIS EXISTS, in his words: "some tooltips from hovering extend very far.
those hover tooltips should be short and the extended version would be behind
the tooltip icons." `_shorten_the_hovers` does exactly that for every button,
menu and slider. It walks QAbstractButton, QComboBox and QSlider — so a LABEL
kept its wall of text, and the drift box carried 2,494 characters on hover,
larger than the 2,139 that prompted the complaint in the first place.

Moving those words behind the ⓘ where they belong then made the ⓘ's own window
1,372 px tall on a 1,079 px screen, with its OK button past the bottom edge.
Both gates and the panel audit called that clean. So the rule is asked of the
window that actually opens.

WHY A SCRIPT AND NOT A TEST. The two-sided rule is a test — see
python/test_no_explanation_is_taller_than_the_screen.py — but that one builds
Notice on its own. Asking the REAL icons means building the real window, and a
QWebEngineView inside the suite takes the process down with it (exit 139).

IT REFUSES A POPULATION IT CANNOT SEE. A window that yields three icons has
not been built, and "none of them is too tall" would then mean nothing.
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(ROOT / "python"))
sys.argv = ["audit_the_panel_hovers_stay_short"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

from PyQt6.QtWidgets import QApplication, QScrollArea, QWidget  # noqa: E402

#: The same limit the window enforces on itself, named once.
import gamut_app                                                # noqa: E402

LIMIT = gamut_app._HOVER_LIMIT

#: Fewer icons than this means the window was not built, not that it is clean.
ENOUGH = 10


def settle(app, seconds=0.05):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.002)


def main() -> int:
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
    app = QApplication.instance() or QApplication(sys.argv)
    window = gamut_app.GamutApp([])
    window.resize(1400, 900)
    window.show()
    settle(app, 3)
    room = app.primaryScreen().availableGeometry().height()

    problems: list[str] = []
    icons = window.findChildren(gamut_app.Hint)
    tallest = ("", 0)
    for icon in icons:
        words = getattr(icon, "_text", "") or ""
        if not words.strip():
            continue
        dialog = gamut_app.Notice(window, "About this setting", words)
        dialog.adjustSize()
        settle(app)
        tall = dialog.sizeHint().height()
        scrolls = bool(dialog.findChildren(QScrollArea))
        name = icon.objectName() or "an ⓘ"
        if tall > tallest[1]:
            tallest = (name, tall)
        if tall > room:
            problems.append(
                f"[open] TOO TALL  {name} opens {tall} px on a {room} px "
                f"screen ({len(words)} characters, scrolls={scrolls}) — its "
                f"own buttons are past the bottom edge")
        dialog.deleteLater()
        app.processEvents()

    if len(icons) < ENOUGH:
        problems.append(
            f"[open] BLIND  only {len(icons)} ⓘ were found, so \"none of them "
            f"is too tall\" says nothing")

    # AND THE HOVERS THEMSELVES, on everything that is not an icon. Reported
    # rather than failed for the widgets the shortener does not walk: the
    # group headings share one 348-character sentence and the run's list
    # carries 668, and both are Basti's to decide. A CONTROL over the limit
    # is a fault, and audit_panel.py is where that is asked.
    walls = []
    for widget in window.findChildren(QWidget):
        if isinstance(widget, gamut_app.Hint):
            continue
        tip = " ".join((widget.toolTip() or "").split())
        if len(tip) > LIMIT:
            walls.append((len(tip), type(widget).__name__))
    walls.sort(reverse=True)

    print(f"  {len(icons)} ⓘ in the window, tallest opens "
          f"{tallest[1]} px of {room} px ({tallest[0]})")
    print(f"  {len(walls)} hover(s) over {LIMIT} characters on widgets the "
          f"shortener does not walk; longest {walls[0][0] if walls else 0}")
    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        window.close()
        return 1
    print("  Clean: every explanation opens a window that fits the screen.")
    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
