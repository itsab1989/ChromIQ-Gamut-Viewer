"""Check that nothing on the control panel is cut off, in every space.

WHY THIS EXISTS. Adding an option to this window has gone wrong the same way
more than once: the option itself works perfectly, and its label is a few
pixels too long for the column, so what ships is a button reading
"Open a chart to be prin…". Screenshots do not catch it reliably — the eye
skips a truncated word it already knows — and neither does a unit test, because
the only thing that knows how wide a word is is a real font on a real widget.

So this asks the widgets themselves, in the real application, and it asks four
separate questions rather than one:

  1. IS ANY TEXT CUT OFF?  Every button, checkbox, label, radio and combobox
     is asked how much width its text needs, and compared with what it got.
  2. DOES ANYTHING OVERFLOW THE COLUMN?  A widget whose right edge is past the
     panel's is cut off even if its own text fits.
  3. DOES EVERY ⓘ SIT BESIDE SOMETHING?  An icon on a row of its own explains
     nothing. (The same rule ``tools_icon_audit.py`` checks; it is repeated
     here so one command covers the panel.)
  4. IS EVERY SPACE-DEPENDENT CONTROL REGISTERED?  Every interactive control
     is either in ``_space_dependent_controls`` or is genuinely the same in
     every space. This is the one that makes adding a space safe: a control
     nobody thought about shows up here rather than in somebody's hands, live
     over a picture it cannot change.

IT RUNS IN EVERY SPACE AND AT SEVERAL WIDTHS, because a label that fits in
CIELAB may not fit once a space with longer state messages is chosen, and the
column can be dragged.

    python scripts/audit_panel.py            # every space, every width
    python scripts/audit_panel.py --shots    # and write a PNG of each

Exit code is 1 if anything is wrong, so it can gate a release.
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_panel"]

from PyQt6.QtCore import QSettings, Qt                      # noqa: E402
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox,  # noqa: E402
                             QGroupBox, QLabel, QPushButton,
                             QRadioButton, QScrollArea, QSlider,
                             QSpinBox, QWidget)

#: Widths to check. The narrowest is the column's own minimum — what somebody
#: gets who has never dragged the splitter — and the widest is a wide window,
#: where a *centred* label can still be wrong even though nothing is clipped.
WIDTHS = (1200, 1560, 1900)

#: How many pixels of shortfall count as cut off. Qt's own elision kicks in at
#: one pixel, but a text width computed from font metrics can disagree with the
#: renderer's by a fraction, and a whole-pixel margin keeps this from crying
#: wolf on a label that is exactly full.
SLACK = 2

#: Controls a person operates. A ⓘ is a QPushButton subclass and is excluded
#: by name where it matters.
INTERACTIVE = (QPushButton, QCheckBox, QComboBox, QSlider, QRadioButton,
               QSpinBox)


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def text_of(widget) -> str:
    """The single line a widget draws, or "" when it draws none.

    A wrapped label is not a single line and is not checked for elision --
    it is checked for overflow instead, further down, which is the failure it
    can actually have.
    """
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, QLabel):
        return "" if widget.wordWrap() else widget.text()
    if hasattr(widget, "text"):
        return widget.text()
    return ""


def needed_width(widget, text: str) -> int:
    """How much width this widget wants in order to show *text* whole.

    ASKED OF QT, not estimated. A first version of this added its own guess at
    what a style reserves for a checkbox's box, a combobox's arrow and a
    button's padding, and reported seven perfectly good controls as clipped —
    including a fixed-size 22px button holding a single ×. Qt's own size hint
    already knows the style, the stylesheet, the font and the icon, and it is
    the number the layout itself is working from.
    """
    return widget.sizeHint().width()


def is_fixed(widget) -> bool:
    """A widget deliberately pinned to one width.

    The × that closes a slot, the +/− beside a slider and the … that opens a
    menu are all set to an exact size on purpose, because they hold one glyph
    and want to stay square. Their size hint is larger than the size they were
    given, and that is the author's decision rather than a fault.
    """
    return (widget.minimumWidth() == widget.maximumWidth()
            or widget.sizePolicy().horizontalPolicy().value == 0)  # Fixed


def clipped(widget) -> "tuple | None":
    """(text, needed, got) when this widget cannot show its text, else None."""
    text = text_of(widget)
    if not text or not widget.isVisible() or is_fixed(widget):
        return None
    needed = needed_width(widget, text)
    got = widget.width()
    if needed - got > SLACK:
        return text, needed, got
    return None


def audit_once(window, panel, label: str) -> list:
    """Every complaint about the panel as it stands right now."""
    problems = []
    right_edge = panel.mapToGlobal(panel.rect().topRight()).x()

    for widget in panel.findChildren(QWidget):
        if not widget.isVisible():
            continue
        name = widget.objectName() or widget.__class__.__name__
        cut = clipped(widget)
        if cut is not None:
            text, needed, got = cut
            problems.append(
                f"[{label}] CUT OFF  {name}: needs {needed}px, has {got}px "
                f"— {text!r}")
        # Overflow: the widget's own right edge past the column's.
        if widget.width() > 0:
            edge = widget.mapToGlobal(widget.rect().topRight()).x()
            if edge - right_edge > SLACK:
                problems.append(
                    f"[{label}] OVERFLOWS  {name}: {edge - right_edge}px "
                    f"past the panel's right edge")

    # Every ⓘ must share its row with the thing it explains.
    import gamut_app
    hints = [h for h in panel.findChildren(gamut_app.Hint) if h.isVisible()]
    others = [w for w in panel.findChildren(INTERACTIVE + (QLabel,))
              if w.isVisible() and not isinstance(w, gamut_app.Hint)]
    for hint in hints:
        band = hint.mapToGlobal(hint.rect().center()).y()
        shares = any(
            abs(o.mapToGlobal(o.rect().center()).y() - band) < 12
            and o.width() > 24
            for o in others)
        if not shares:
            problems.append(
                f"[{label}] ORPHAN ⓘ  {hint.objectName() or 'hint'} "
                f"explains nothing on its row")

    # AND THE OTHER DIRECTION, which is the one that let three unexplained
    # sliders ship: a control with no ⓘ anywhere near it. Reported per group,
    # because that is the unit a person reads — a group with no explanation at
    # all is the real fault, and a group whose ⓘ sits two rows up is fine.
    attribute = {id(v): k for k, v in vars(window).items()}
    for group in panel.findChildren(QGroupBox):
        if not group.isVisible():
            continue
        if group.title() in gamut_app.GamutApp.NO_HINT_NEEDED:
            continue
        controls = [c for c in group.findChildren(INTERACTIVE)
                    if c.isVisible() and not isinstance(c, gamut_app.Hint)]
        if not controls:
            continue
        bands = [h.mapToGlobal(h.rect().center()).y()
                 for h in group.findChildren(gamut_app.Hint) if h.isVisible()]
        headings = [l for l in group.findChildren(QLabel)
                    if l.isVisible() and l.text() and not l.wordWrap()
                    and not isinstance(l, gamut_app.Hint)]
        for control in controls:
            mid = control.mapToGlobal(control.rect().center()).y()
            if any(abs(b - mid) < 14 for b in bands):
                continue
            # ONLY CONTROLS WITH A HEADING OF THEIR OWN. A radio inside a
            # named set, or the × on a slot, is covered by the explanation
            # for the set — demanding one each would bury the panel in icons.
            # A slider sitting under its own caption is a different thing:
            # the caption names it and nothing says what it is for, which is
            # exactly how three of them shipped unexplained.
            top = control.mapToGlobal(control.rect().topLeft()).y()
            mine = [h for h in headings
                    if 0 <= top - h.mapToGlobal(h.rect().bottomLeft()).y() <= 14]
            if not mine:
                continue
            # A ⓘ ON THE HEADING counts. That is the app's other convention:
            # one icon beside the caption that names a set, explaining the
            # whole set beneath it. Reading only the control's own row called
            # four correctly-explained controls unexplained.
            if any(abs(b - h.mapToGlobal(h.rect().center()).y()) < 14
                   for h in mine for b in bands):
                continue
            name = attribute.get(id(control)) or control.objectName()
            problems.append(
                f"[{label}] NO ⓘ  {name or text_of(control)!r} "
                f"under {group.title()!r} has its own caption and no "
                f"explanation on its row")
    return problems


def audit_registry(window) -> list:
    """Every interactive control is either space-dependent or declared not.

    The check that makes a new space safe to add. It walks what is actually on
    the panel rather than a list somebody maintained, so a control added later
    cannot be missed by being forgotten -- only by being answered.
    """
    import gamut_app
    problems = []
    registered = set()
    for widget, _capability, _untick in window._space_dependent_controls():
        registered.add(id(widget))
        # A registered ROW covers what is on it: disabling a container
        # disables its children, so listing the row is listing them.
        for child in widget.findChildren(QWidget):
            registered.add(id(child))
    # The attribute the window keeps each control under, so a complaint names
    # the thing somebody has to go and edit rather than the words on it.
    attribute = {id(v): k for k, v in vars(window).items()}
    independent = gamut_app.GamutApp.SPACE_INDEPENDENT
    groups = gamut_app.GamutApp.SPACE_INDEPENDENT_GROUPS
    panel = window.findChild(QScrollArea).widget()

    for widget in panel.findChildren(INTERACTIVE):
        if isinstance(widget, gamut_app.Hint) or id(widget) in registered:
            continue
        # Saved looks are a self-contained thing about this window's own
        # settings; a space cannot change what "save this look" means.
        if _ancestor(widget, gamut_app.LookSection) is not None:
            continue
        group = _ancestor(widget, QGroupBox)
        if group is not None and group.title() in groups:
            continue
        name = attribute.get(id(widget)) or widget.objectName()
        if name in independent or name == "footLink":
            continue
        problems.append(
            f"[registry] UNANSWERED  {name or '?'} "
            f"({widget.__class__.__name__} {text_of(widget)!r}, under "
            f"{group.title() if group is not None else 'no group'!r}) is "
            f"neither space-dependent nor listed in SPACE_INDEPENDENT")
    return problems


def _ancestor(widget, kind):
    """The nearest parent of *kind*, or None."""
    node = widget.parent()
    while node is not None:
        if isinstance(node, kind):
            return node
        node = node.parent()
    return None


def main() -> int:
    shots = "--shots" in sys.argv
    QSettings("MeasuredGamutViewer", "MeasuredGamutViewer").clear()
    import gamut_app

    app = QApplication(sys.argv)
    window = gamut_app.GamutApp([])
    window.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
    pump(app, 3)

    panel = window.findChild(QScrollArea).widget()
    problems = list(audit_registry(window))

    # A chart open, because half the panel only exists once there is one.
    chart = os.environ.get("AUDIT_CHART", "")
    if chart and pathlib.Path(chart).is_file():
        window._open_chart_file(pathlib.Path(chart))
        pump(app, 2)

    out = HERE.parent.parent / "audit-shots"
    if shots:
        out.mkdir(exist_ok=True)

    for width in WIDTHS:
        window.resize(width, 940)
        pump(app, 1.5)
        for i in range(window._space.count()):
            space = window._space.itemData(i)
            window._space.setCurrentIndex(i)
            pump(app, 2)
            label = f"{width}px/{space}"
            problems += audit_once(window, panel, label)
            if shots:
                panel.grab().save(str(out / f"panel-{width}-{space}.png"))

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} problem(s).")
        return 1
    checked = len(WIDTHS) * window._space.count()
    print(f"  Clean: {checked} panel states checked "
          f"({len(WIDTHS)} widths × {window._space.count()} spaces), "
          f"every control answered for.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
