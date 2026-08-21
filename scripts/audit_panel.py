"""Check that nothing on the control panel is cut off, in every space.

WHY THIS EXISTS. Adding an option to this window has gone wrong the same way
more than once: the option itself works perfectly, and its label is a few
pixels too long for the column, so what ships is a button reading
"Open a chart to be prin…". Screenshots do not catch it reliably — the eye
skips a truncated word it already knows — and neither does a unit test, because
the only thing that knows how wide a word is is a real font on a real widget.

So this asks the widgets themselves, in the real application, and it asks six
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
  5. CAN ANY PARAGRAPH BE CUT?  Every wrapping label must be a
     ``WrappedLabel``, which recomputes its own height from the width it is
     actually given. A plain QLabel with wordWrap has no such defence, and a
     narrower column silently takes its last line off.
  6. IS ANYTHING DRAWN UNDER A GROUP'S FRAME?  The lowest control in a group
     must clear the group's own bottom edge. This is the one that catches a
     cut sentence, and it took five attempts to find: the four before it
     asked the LABEL, which was the right height all along -- what it had no
     room for was the border sitting in the same pixels.

AND IT OPENS EVERY FOLDED SECTION FIRST, which it did not do for a long time:
six sections start folded, their contents are hidden, and hidden widgets have
no size to measure — so most of this column had never been looked at while
this printed "Clean".

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
import shutil
import sys
import tempfile
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

# THE ARGUMENTS ARE TAKEN BEFORE QT IS GIVEN A TIDY sys.argv. Overwriting it
# first throws them away, and a run asked to stand in another font then
# audits the default one and reports Clean about the wrong thing -- which is
# exactly what happened here, and in audit_the_page_at_any_size before it.
ASKED = list(sys.argv[1:])
sys.argv = ["audit_panel"]

from PyQt6.QtCore import QSettings, Qt                      # noqa: E402
from PyQt6.QtWidgets import (QApplication, QBoxLayout, QCheckBox,  # noqa: E402
                             QComboBox, QGridLayout, QGroupBox, QLabel,
                             QPushButton, QRadioButton, QScrollArea, QSlider,
                             QSpinBox, QWidget)

#: Widths to check. The narrowest is the column's own minimum — what somebody
#: gets who has never dragged the splitter — and the widest is a wide window,
#: where a *centred* label can still be wrong even though nothing is clipped.
WIDTHS = (1200, 1560, 1900)

#: How long a HOVER tooltip may be, in characters. Asked for in as many words:
#: the hover stays short and names the outcome and the prerequisite; the long
#: version goes behind the ⓘ, which is why every control here has one.
HOVER_LIMIT = 200

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


def on_screen(panel) -> set:
    """Which controls are visible right now, by identity rather than by name.

    Identity, because a dozen rows carry the same words: two `Hint`s reading
    "hint_axis_left_speed" and "hint_axis_up_speed" are different controls and
    a set keyed on their text would count them as one. The widgets live as
    long as the window, so `id()` is stable for the whole run.

    Only meaningful with every fold already open — inside a shut section a
    control reports `isVisible()` False whether a tickbox has revealed it or
    not, which is how the first attempt at this measurement could not tell
    revealed from hidden and answered "nothing is missed" about a question it
    could not see.
    """
    return {id(w) for w in panel.findChildren(QWidget) if w.isVisible()}


def audit_once(window, panel, label: str) -> list:
    """Every complaint about the panel as it stands right now."""
    problems = []
    right_edge = panel.mapToGlobal(panel.rect().topRight()).x()

    for widget in panel.findChildren(QWidget):
        if not widget.isVisible():
            continue
        # QT'S OWN TOOLTIP IS NOT PART OF THE PANEL. A hover tooltip is a
        # top-level popup that Qt parents to the widget under the mouse, so
        # findChildren hands it back with everything else — and it is drawn
        # BESIDE the window on purpose, which this read as "876px past the
        # panel's right edge". Eight identical complaints, none of them about
        # the layout, and they only appeared at all because the pointer
        # happened to be resting over the column while the audit ran.
        if widget.isWindow():
            continue
        # NAME THE SECTION, NOT THE CLASS. "OVERFLOWS QGroupBox" sends
        # somebody hunting through fifteen of them; the heading is what they
        # can see on screen and search the source for.
        name = widget.objectName() or widget.__class__.__name__
        if isinstance(widget, QGroupBox) and widget.title():
            name = f"{name} {widget.title()!r}"
        else:
            inside = _ancestor(widget, QGroupBox)
            if inside is not None and inside.title():
                name = f"{name} (inside {inside.title()!r})"
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

    import gamut_app

    # 5. EVERY WRAPPING PARAGRAPH MUST BE ONE THAT RE-FITS ITSELF.
    #
    # This is the guard that answers "what catches a cut sentence", and the
    # answer turned out to be a different question. FOUR checks were built for
    # a cut paragraph and all four reported Clean — heights, running past the
    # group, visibleRegion, and a pixel comparison. They were right. Driven at
    # the narrow width that had caused the report, with one paragraph then
    # deliberately capped at 20 px to make a cut on purpose, nothing was cut:
    # gamut_app.WrappedLabel recomputes its own minimum height from the width
    # it actually has, on every resize, so it simply put the height back.
    #
    # Measured in the real window: all eleven wrapping labels in the column
    # are WrappedLabel. A plain QLabel with wordWrap set has no such defence —
    # its height is whatever the layout gave it when it was built, and a
    # narrower column silently takes the last line off. So the check is not
    # "is anything cut" but "could anything be": one plain wrapping QLabel is
    # the fault, and it is visible the moment it is added rather than after
    # somebody narrows the column six months later.
    plain = [x for x in panel.findChildren(QLabel)
             if x.isVisible() and x.wordWrap() and x.text()
             and not isinstance(x, gamut_app.WrappedLabel)
             and not isinstance(x, gamut_app.Hint)]
    for x in plain:
        problems.append(
            f"[{label}] CAN BE CUT  a plain wrapping QLabel — its height is "
            f"whatever the layout gave it, so a narrower column takes the "
            # ITS OWN TEXT, NOT text_of(). That helper returns "" for a
            # wrapping label on purpose — it is about elision — so the first
            # version of this named the fault and then quoted nothing.
            f"last line off. Use WrappedLabel: {x.text()[:60]!r}")

    # 6. NOTHING MAY BE DRAWN UNDER A GROUP'S OWN FRAME — the check that
    #    finally catches a cut sentence, and the fifth attempt at it.
    #
    # THE FOUR BEFORE IT ASKED THE WIDGET, and the widget was not the one
    # getting it wrong: heights, running past the group, visibleRegion and a
    # pixel comparison all reported Clean while a photograph showed the last
    # line of a paragraph sliced in half. The label was the right height for
    # its text -- 60 px for 60 px of words, agreed by heightForWidth, by font
    # metrics and by the label itself. What it did NOT have was anywhere to
    # put it: the group's layout had a 2 px bottom margin written over the
    # stylesheet's 8, so the label's last line and the group's border were in
    # the same pixels.
    #
    # SO THE MEASUREMENT IS THE CLEARANCE, not the height: how far the lowest
    # thing in a group sits above the group's own bottom edge. Measured in the
    # real window, and it separates the two states cleanly:
    #
    #     cut       0 px   the label's bottom IS the group's bottom
    #     whole    6-12 px every group, both appearances
    #
    # Four is the floor because six is the tightest the window actually has,
    # and a border is one pixel with a four-pixel radius.
    FRAME = 4
    for group in panel.findChildren(QGroupBox):
        if not group.isVisible() or not getattr(group, "_fold_open", True):
            continue
        lowest = None
        for child in group.findChildren(QWidget):
            if not child.isVisible() or isinstance(child, QGroupBox):
                continue
            bottom = child.mapTo(group, child.rect().bottomLeft()).y()
            if lowest is None or bottom > lowest[0]:
                lowest = (bottom, child)
        if lowest is None:
            continue
        clearance = group.height() - lowest[0]
        if clearance < FRAME:
            problems.append(
                f"[{label}] UNDER THE FRAME  {group.title()!r}: its lowest "
                f"control ends {clearance}px above the group's edge, so it "
                f"is drawn under the border — {text_of(lowest[1])[:50]!r}")

    # Every ⓘ must share its row with the thing it explains.
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
            # AN ⓘ IN THE SAME SET THAT NAMES THIS CONTROL IS ITS
            # EXPLANATION, wherever it sits.
            #
            # The two clauses above are geometric — an icon on the control's
            # row, or on its caption — and the lighting controls keep to a
            # third convention the window has always had: seven sliders
            # revealed by one tickbox, under ONE ⓘ whose words name every one
            # of them ("Ambient is light arriving from every direction at
            # once ... Diffuse is light the surface scatters ... Fresnel adds
            # a glow around the edges"). Six complaints came out of that, and
            # the application was right in all six.
            #
            # This is not a blanket exemption for "there is an icon nearby":
            # the ⓘ has to say the control's NAME. A caption reading
            # "Ambient — light from everywhere" is explained by an ⓘ that
            # mentions Ambient and by no other.
            caption = mine[0].text().split("—")[0].split("--")[0].strip()
            named = any(
                caption and caption.lower() in h.explanation().lower()
                for h in group.findChildren(gamut_app.Hint)
                if h.isVisible() and hasattr(h, "explanation"))
            if named:
                continue
            name = attribute.get(id(control)) or control.objectName()
            problems.append(
                f"[{label}] NO ⓘ  {name or text_of(control)!r} "
                f"under {group.title()!r} has its own caption and no "
                f"explanation on its row")

        # AND THE OTHER DIRECTION: AN ⓘ WITH NOTHING BESIDE IT.
        #
        # Reported from the window, under "Both rooms point the same way",
        # hours after this file printed Clean.
        #
        # FOUR ATTEMPTS AT THIS MEASURED PIXELS AND ALL FOUR FAILED. The
        # record is worth keeping because every one of them looked reasonable:
        #
        #   "is there a control on this icon's row"    60 false alarms in six
        #       states -- this panel puts an ⓘ under a wrapped paragraph
        #       everywhere, and none of those has a control on its row;
        #   "...or any label whose row overlaps"       no false alarms and no
        #       detections: with the fault restored it still said Clean;
        #   "is the icon at the left margin"           every one of 44 visible
        #       icons sits 89-90% across its group and the stranded one at
        #       10% -- measured by hand, and the rule STILL said Clean with
        #       the fault restored;
        #   walking the layouts from `window.layout()`  0 stranded out of 83
        #       icons, with the fault in place -- because that walk never
        #       reaches the control column at all. It is inside a scroll area.
        #       A rule built on it measures an EMPTY SET and reports Clean
        #       about nothing, which is the same trap as a fixture that
        #       yields nothing.
        #
        # So this one has no pixels in it and starts from each icon rather
        # than from the window. Every ⓘ is added to a vertical stack and then
        # MOVED by `_attach_in_layout` into a row with the control above it,
        # or is put in a row by hand and marked `placed_by_hand`. An icon
        # still sitting alone on a row of a vertical stack when the window is
        # finished is one that neither pass reached -- which is exactly what
        # happened here, because that checkbox lives inside a container widget
        # and the attaching pass walks layouts and never descends into a
        # widget's own.
        #
        # A GRID IS LEFT ALONE for the same reason `_attach_in_layout` leaves
        # it alone: there each ⓘ is already in its own column beside its own
        # control, on purpose.
        for hint in panel.findChildren(gamut_app.Hint):
            if hint.isHidden():
                continue
            row = _holding_layout(hint)
            if row is None:
                problems.append(
                    f"[{label}] LOST ⓘ  {hint.objectName() or 'an ⓘ'} is not "
                    f"in any layout its parent owns, so nothing decides where "
                    f"it sits")
            elif _is_a_column(row):
                problems.append(
                    f"[{label}] STRANDED ⓘ  {hint.objectName() or 'an ⓘ'} "
                    f"sits alone on a row of a column, under the control it "
                    f"explains instead of beside it — `_attach_in_layout` "
                    f"never reached it (a control inside a container widget "
                    f"is invisible to it), and it is not marked "
                    f"`placed_by_hand`")
    return problems


#: Markdown that Qt renders as literal characters. ``a*``, ``b*``, ``L*`` and
#: ``C*`` are colour notation, not emphasis, so only DOUBLED stars count —
#: three real ones had shipped, printing "**In the accent colours**" complete
#: with its asterisks.
import re as _re
_MARKDOWN = _re.compile(r"\*\*|__[A-Za-z]|\[[^\]]+\]\(")


def _holding_layout(hint):
    """The layout that directly holds *hint*, found from its own parent.

    NOT BY WALKING FROM THE WINDOW, and that distinction is the whole reason
    the fourth attempt at this failed: a walk from `window.layout()` never
    reaches the control column, which lives inside a scroll area, so it finds
    no icons at all and calls that Clean.
    """
    parent = hint.parentWidget()
    if parent is None or parent.layout() is None:
        return None
    seen = set()

    def search(layout):
        if layout is None or id(layout) in seen:
            return None
        seen.add(id(layout))
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            if item.layout() is not None:
                got = search(item.layout())
                if got is not None:
                    return got
                continue
            if item.widget() is hint:
                return layout
        return None

    return search(parent.layout())


def _is_a_column(layout) -> bool:
    """A stack of rows, where a widget on its own IS a row of its own."""
    if isinstance(layout, QGridLayout):
        return False
    return (isinstance(layout, QBoxLayout)
            and layout.direction() in (QBoxLayout.Direction.TopToBottom,
                                       QBoxLayout.Direction.BottomToTop))


def strand_an_icon(panel) -> str:
    """Put the reported fault back, in the window that is already built.

    Takes the two-rooms icon out of the row it shares with its checkbox and
    drops it back into the column underneath — which is precisely where
    `_attach_in_layout` left it before it was placed by hand. Returns the name
    of the icon it moved, or "" if it could not move one, so a mutation that
    matches nothing says so instead of passing.
    """
    import gamut_app

    hint = panel.findChild(gamut_app.Hint, "hint_link_hint")
    if hint is None:
        return ""
    row = _holding_layout(hint)
    if row is None or _is_a_column(row):
        return ""
    column = hint.parentWidget().layout()
    if not _is_a_column(column):
        return ""
    row.removeWidget(hint)
    column.addWidget(hint)
    hint.setProperty("placed_by_hand", False)
    # TAKING A WIDGET OUT OF A LAYOUT HIDES IT, and a hidden icon is skipped
    # by the rule -- correctly, because an explanation for something not on
    # screen is not stranded, it is absent. Left like that the mutation
    # sabotages itself: the fault is in place and invisible to the very check
    # it is meant to provoke.
    hint.setVisible(True)
    after = _holding_layout(hint)
    if after is None or not _is_a_column(after) or hint.isHidden():
        return ""
    return hint.objectName()


def audit_help(window, panel) -> list:
    """Every ⓘ explanation: present, extensive, and naming things that exist.

    The three ways help text goes wrong here, in the order they have actually
    happened: it carries Markdown that Qt prints as characters; it is one
    terse line where the rest of the window writes a paragraph for a beginner;
    or it names a control that has since been renamed, sending somebody
    hunting for a label that is not there.
    """
    import gamut_app
    problems = []
    labels = {g.title() for g in panel.findChildren(QGroupBox)}
    for x in panel.findChildren((QCheckBox, QPushButton, QRadioButton, QLabel)):
        if x.text():
            labels.add(x.text().strip())
    for c in panel.findChildren(QComboBox):
        labels |= {c.itemText(i).strip() for i in range(c.count())}
    lowered = " ¦ ".join(sorted(labels)).lower()

    # "under X", where X runs to the end of the clause.
    names = _re.compile(r"under ([A-Z][A-Za-z ]{2,40}?)(?=[.,;:\n]| and | to | while | tints | is | are )")
    for hint in panel.findChildren(gamut_app.Hint):
        text = getattr(hint, "_text", "") or hint.toolTip() or ""
        name = hint.objectName() or "an ⓘ"
        if not text.strip():
            problems.append(f"[help] EMPTY  {name} explains nothing")
            continue
        if _MARKDOWN.search(text):
            problems.append(
                f"[help] MARKDOWN  {name} carries **, __ or a link — Qt "
                f"prints those as characters")
        if len(text) < 150:
            problems.append(
                f"[help] TERSE  {name} is {len(text)} characters; the rest of "
                f"this window writes a paragraph for a beginner")
        for found in names.findall(text):
            if found.strip().lower() not in lowered:
                problems.append(
                    f"[help] STALE  {name} sends the reader to "
                    f"{found.strip()!r}, which is not on the panel")
    return problems


def audit_hover(panel) -> list:
    """Every button says something when it is hovered, and the ticks line up.

    THE ⓘ IS NOT THE FIRST PLACE ANYBODY LOOKS. Hovering the control itself
    is, and eight buttons at the foot of the column answered that with
    silence, every one of them with a full explanation an inch to its right
    behind an icon. Reported from the window: "some of the buttons at the
    bottom of the left sections have no tooltip".

    THE RULE, NOT A LIST OF THE EIGHT: a button added tomorrow with nothing to
    say shows up here the day it is written.

    AND WHERE TICKS IN THE SAME BOX BEGIN. Two of them, under each other, two
    pixels apart -- because one sat in a row that also held an ⓘ and the other
    did not. It reads as sloppiness without being nameable: "checkboxes are
    not aligned correctly".
    """
    problems: list = []
    for button in panel.findChildren(QPushButton):
        if button.text().strip() and not button.toolTip().strip():
            problems.append(
                f"[hover] SILENT  {button.text().strip()!r} says nothing when "
                f"it is hovered")

    # AND NOT AN ESSAY EITHER, which is the same rule from the other side: the
    # hover stays short and the long version goes behind the ⓘ.
    #
    # MEASURED BEFORE IT WAS WRITTEN, so it starts green instead of crying
    # about the window as it stands: of 66 controls carrying a hover tooltip,
    # not one is over the limit. This rule buys nothing today. It is here
    # because of HOW the limit gets broken -- the ⓘ beside these same controls
    # runs to two and a half thousand characters, and the way this goes wrong
    # is one of those pasted into the hover by somebody in a hurry.
    #
    # WHAT THAT COSTS, driven rather than counted: the one 2,485-character
    # tooltip in the window opens a box 481 x 562 px -- over half the height
    # of this screen, dropped over the panel unasked by a pointer merely
    # passing across. That is the picture this number is standing in for.
    #
    # HIDDEN CONTROLS ARE NOT ASKED. "Remove the selected one" carries 530
    # characters and is deliberately never shown (see gamut_app.py, where it
    # is kept as an object so tests and audits naming it keep working). A rule
    # that fires on what no pointer can reach teaches people to ignore it, and
    # this audit has been burned by a noisy rule before -- see the
    # seventeen-complaint version in audit_the_readme_is_true.
    looked = 0
    for x in panel.findChildren((QPushButton, QCheckBox, QRadioButton,
                                 QComboBox)):
        if x.isHidden():
            continue
        text = " ".join(_re.sub(r"<[^>]+>", "", x.toolTip()).split())
        if not text:
            continue
        looked += 1
        if len(text) > HOVER_LIMIT:
            name = (x.text().strip() if hasattr(x, "text") and x.text()
                    else x.objectName() or type(x).__name__)
            problems.append(
                f"[hover] ESSAY  {name!r} answers a hover with {len(text)} "
                f"characters; the limit is {HOVER_LIMIT} and the long version "
                f"belongs behind its ⓘ")

    # AND IT MUST BE ABLE TO SEE THEM. A measurement that cannot reach the
    # controls looks exactly like one that found nothing wrong, which has cost
    # this project four separate days. The panel carries dozens; if this ever
    # examines a handful, the folds did not open or the panel was not built,
    # and the silence above means nothing.
    if looked < 20:
        problems.append(
            f"[hover] BLIND  only {looked} control(s) with a hover tooltip "
            f"were reachable, so \"none is too long\" says nothing")
    # TWO ⓘ ON ONE ROW IS ONE OF THEM POINTING AT THE WRONG THING. Every
    # icon belongs to exactly one control; a row with several has collected
    # the icons of controls that were hidden when they were placed. Four of
    # them ended up beside "…and a perfectly neutral line" that way, with the
    # three checkboxes below it left with none, and nothing in this audit
    # asked the question until now.
    from PyQt6.QtWidgets import QBoxLayout

    def rows_of(root):
        stack = [root.layout()] if root.layout() is not None else []
        while stack:
            lay = stack.pop()
            if lay is None:
                continue
            yield lay
            for i in range(lay.count()):
                item = lay.itemAt(i)
                if item.layout() is not None:
                    stack.append(item.layout())
                elif (item.widget() is not None
                      and item.widget().layout() is not None):
                    stack.append(item.widget().layout())

    import gamut_app as _app
    across = (QBoxLayout.Direction.LeftToRight,
              QBoxLayout.Direction.RightToLeft)
    seen_rows = set()
    for holder in [panel] + panel.findChildren(QWidget):
        for row in rows_of(holder):
            if id(row) in seen_rows or not isinstance(row, QBoxLayout):
                continue
            seen_rows.add(id(row))
            if row.direction() not in across:
                continue
            here = [row.itemAt(i).widget() for i in range(row.count())]
            icons = [x for x in here if isinstance(x, _app.Hint)]
            if len(icons) > 1:
                named = [getattr(x, "text", lambda: "")() for x in here
                         if x is not None and not isinstance(x, _app.Hint)]
                problems.append(
                    f"[hover] CROWDED  {len(icons)} ⓘ on one row, beside "
                    f"{[n for n in named if n]}")

    for box in panel.findChildren(QGroupBox):
        ticks = [t for t in box.findChildren(QCheckBox)
                 if t.parent() is box and not t.isHidden()]
        starts = {}
        for tick in ticks:
            starts.setdefault(
                tick.mapTo(box, tick.rect().topLeft()).x(), []).append(
                    tick.text().strip())
        if len(starts) > 1:
            where = ", ".join(f"x={x}: {', '.join(names)}"
                              for x, names in sorted(starts.items()))
            problems.append(
                f"[hover] RAGGED  ticks in {box.title().strip()!r} start on "
                f"different pixels — {where}")
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
    shots = "--shots" in ASKED
    prove = "--prove" in ASKED
    # THE WINDOW IN A FONT IT WAS NOT DRAWN IN.
    #
    # gamut_app styles the whole window `font-family: "Inter"`, and the
    # application does not ship it: nothing bundles a face and nothing calls
    # QFontDatabase.addApplicationFont. It happens to be installed on the
    # machine this was written on, so every run of every audit has measured a
    # window drawn in the intended font -- and anybody without Inter gets
    # whatever Qt substitutes, with different metrics for every label in the
    # column.
    #
    # Measured when that was noticed: the layout does not care. Helvetica,
    # Times New Roman and Courier New -- the last far wider -- each pass all
    # 24 states with nothing cut and nothing overflowing, because the column
    # is sized from what is inside it rather than from a number somebody
    # typed. This keeps that true: a width pinned to Inter's metrics would
    # pass here and clip on somebody else's machine.
    #
    #     python scripts/audit_panel.py --font "Courier New"
    font = None
    if "--font" in ASKED:
        at = ASKED.index("--font")
        if at + 1 < len(ASKED):
            font = ASKED[at + 1]
    import gamut_app

    if font:
        # WRAPPED, NOT REWRITTEN. The sheet is built per appearance and per
        # accent by gamut_app.stylesheet(), so the substitution has to happen
        # every time it is asked for, not once on a string.
        import re as _re

        _real = gamut_app.stylesheet

        def _in_another_font(*a, **k):
            return _re.sub(r'font-family: "[^"]+"',
                           f'font-family: "{font}"', _real(*a, **k), count=1)

        gamut_app.stylesheet = _in_another_font
        print(f"  standing in {font!r} for the window's own font")
    app = QApplication(sys.argv)
    window = gamut_app.GamutApp([])
    window.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
    pump(app, 3)

    # EVERY SECTION OPEN FIRST, AND THIS WAS A HOLE IN THE AUDIT.
    #
    # Every question below is asked of VISIBLE widgets — a hidden one has no
    # position and no width, so measuring it would report nonsense. But six
    # sections of this column start FOLDED, so their contents were hidden, so
    # this audit had never once looked at them: "How the patches are drawn",
    # "What the colours are measured against", "How it looks", "Viewer and
    # export styling", "This window", and now "The application itself" —
    # between them most of the controls in the window, including the three
    # sliders whose missing ⓘ this audit was written for.
    #
    # It reported "Clean" the whole time, and it was clean about the half it
    # was looking at. Opening every fold first costs nothing and is what makes
    # the count at the end mean what it says. The folds are opened in memory
    # only — _refold does not write to the settings store — so nobody's own
    # folded sections are disturbed by running this.
    panel = window.findChild(QScrollArea).widget()
    opened = 0
    for box in panel.findChildren(QGroupBox):
        if hasattr(box, "_refold") and not getattr(box, "_fold_open", True):
            box._fold_open = True
            box._refold()
            opened += 1
    pump(app, 1.5)
    print(f"  {opened} folded section(s) opened so they can be measured.")
    problems = list(audit_registry(window))
    problems += audit_help(window, panel)
    problems += audit_hover(panel)

    # A chart open, because half the panel only exists once there is one.
    # A CHART OPEN, AND ITS NAME AS LONG AS A REAL ONE.
    #
    # Half the panel only exists once a chart is open, and the name of what
    # is open is shown in three places -- the slot that names it, the chooser
    # that lists the profiles it can be placed through, and the readout under
    # them. Every one of those was tested for years with "Glossy-paper", and
    # a real name is not like that: "Verification chart 480 patches — built
    # for heavy matte cotton at 310gsm — March 2025" is what somebody
    # actually types.
    #
    # Measured with one: the "Placed through" chooser demanded 613 px for its
    # longest item and dragged its whole group 306 px past the column's right
    # edge. The run's list had already been caught scrolling sideways for the
    # same reason, from a photograph -- and the sweep written after that
    # found nothing, because every file IT opened had a short name.
    #
    # So the audit copies the chart under a long name and opens that. It
    # costs one file copy and it is the difference between testing the panel
    # and testing the panel's easy case.
    chart = os.environ.get("AUDIT_CHART", "")
    if not chart:
        built_in = HERE.parent / "demo" / "verification-chart-480.ti1"
        if built_in.is_file():
            chart = built_in
    if chart and pathlib.Path(chart).is_file():
        source = pathlib.Path(chart)
        long_name = (pathlib.Path(tempfile.mkdtemp(prefix="audit-panel-"))
                     / ("Verification chart 480 patches — built for heavy "
                        "matte cotton at 310gsm — March 2025" + source.suffix))
        shutil.copyfile(source, long_name)
        window._open_chart_file(long_name)
        pump(app, 2.5)

    # AND A PROFILE WITH A LONG NAME, WHICH IS THE OTHER HALF OF IT.
    #
    # The chart's name is drawn by a label, which wraps. The PROFILE's name
    # goes into two combo boxes -- "Placed through" and "Compare with" -- and
    # a combo asks for the width of its longest ITEM. That is the widget that
    # dragged a group 306 px off the side of the column, so an audit that
    # opens a long-named chart and a short-named profile still misses it.
    #
    # Proved by mutation rather than assumed: with the combo fix taken out
    # and only the chart renamed, this audit reported "Clean".
    profile = HERE.parent / "demo" / "Glossy-paper.icc"
    if profile.is_file():
        long_profile = (pathlib.Path(tempfile.mkdtemp(prefix="audit-panel-"))
                        / ("Studio printer — heavy matte cotton 310gsm — "
                           "2025-03-14 after the new inks" + profile.suffix))
        shutil.copyfile(profile, long_profile)
        window._load(long_profile)
        pump(app, 6)

    out = HERE.parent.parent / "audit-shots"
    if shots:
        out.mkdir(exist_ok=True)

    # NEVER WIDER THAN THE SCREEN. This resizes a real window on a real
    # desktop, and asking for 1900 px on a narrower display pushes it off the
    # edge — which is rude, and measures a layout nobody can actually see.
    # The widths are clamped to what fits, and duplicates dropped.
    available = app.primaryScreen().availableGeometry().width()
    widths = sorted({min(w, available - 40) for w in WIDTHS})

    # WHAT HAS ACTUALLY BEEN ON SCREEN, so the states below can be chosen by
    # what is still unmeasured rather than by guesswork.
    covered: set = set()

    for appearance in ("dark", "light"):
      # BOTH APPEARANCES. A label that fits is a label that fits, but an ⓘ
      # or a swatch that reads on one background can vanish on the other,
      # and the panel is re-polished when the theme changes — which is when
      # Qt applies stylesheet padding, so widths can move with it.
      window._set_appearance(appearance) if hasattr(
          window, "_set_appearance") else None
      pump(app, 2)
      for width in widths:
        window.resize(width, 940)
        pump(app, 1.5)
        for i in range(window._space.count()):
            space = window._space.itemData(i)
            window._space.setCurrentIndex(i)
            pump(app, 2)
            label = f"{appearance}/{width}px/{space}"
            problems += audit_once(window, panel, label)
            covered |= on_screen(panel)
            if shots:
                panel.grab().save(
                    str(out / f"panel-{appearance}-{width}-{space}.png"))

    # AND THE CONTROLS A TICKBOX REVEALS, which nothing above reaches.
    #
    # Reported from the window: "clicked two rooms side by side option and a
    # tooltip icon appears below both rooms point the same way - should
    # probably be at its right side". Question 3 of this audit is exactly that
    # rule -- an ⓘ on a row of its own explains nothing -- and it had reported
    # Clean hours earlier.
    #
    # The reason is the same one that was learned once already and not carried
    # far enough: this opens every folded SECTION before measuring, because a
    # hidden widget has no size. A control revealed by a TICKBOX is hidden in
    # the same way and was never revealed at all -- "Both rooms point the same
    # way" does not exist until "Two rooms, side by side" is ticked, so it was
    # never built, never measured, and counted clean by absence.
    #
    # Both states are kept rather than swapped: a tick can hide something as
    # well as show it, so measuring only the ticked one would trade this blind
    # spot for its mirror image.
    # AND A SECOND SHAPE, WITHOUT WHICH HALF OF THEM STAY HIDDEN ANYWAY.
    #
    # "Both rooms point the same way" needs TWO shapes as well as its tick:
    # side by side has no meaning with one, so the option stays invisible and
    # has no size, and ticking every box in the panel still did not reach it.
    # Measured: with one shape open and every tick on, that control reported
    # isVisible() False; with a second shape open it appeared, and its ⓘ was
    # sitting 25 px below it.
    # AND BACK TO THE DRAWING SPACE PEOPLE ACTUALLY USE. The loop above ends
    # on the LAST space in the chooser, which is "Ink amounts — a chart on
    # its own", and this pass then ran there by leftover rather than by
    # choice — measured: 11 tickboxes enabled in `rgb` against 19 in `lab`,
    # so the pass written specifically to reach the controls a tick reveals
    # was doing it in the space that offers the fewest of them.
    window._space.setCurrentIndex(0)
    pump(app, 2)

    second = HERE.parent / "demo" / "Matte-paper.ti3"
    if second.is_file():
        window._load(second)
        pump(app, 5)

    revealed = []
    revealed_candidates = [t for t in panel.findChildren(QCheckBox)
                           if t.isEnabled()]
    for tick in panel.findChildren(QCheckBox):
        if tick.isEnabled() and not tick.isChecked():
            tick.setChecked(True)
            revealed.append(tick)
    pump(app, 5)
    print(f"  {len(revealed_candidates)} tickbox(es) enabled in "
          f"{window._space.currentData()!r}, the space this pass measures in.")
    print(f"  {len(revealed)} tickbox(es) turned on, to build the controls "
          f"they reveal.")
    extra = 0
    for appearance in ("dark", "light"):
        window._set_appearance(appearance) if hasattr(
            window, "_set_appearance") else None
        pump(app, 2)
        for width in widths:
            window.resize(width, 940)
            pump(app, 2)
            problems += audit_once(window, panel,
                                   f"{appearance}/{width}px/revealed")
            covered |= on_screen(panel)
            extra += 1
            if shots:
                panel.grab().save(
                    str(out / f"panel-{appearance}-{width}-revealed.png"))

    # AND THE STATES WHERE ONE TICK ALONE SHOWS SOMETHING THE OTHERS HIDE.
    #
    # The pass above was written because a control revealed by a tickbox was
    # never built and so counted clean by absence. It ticks every box AT
    # ONCE, and its own comment says why that is not enough — "a tick can
    # hide something as well as show it". That is exactly what happens here:
    # measured on a real window with both papers open, the default state
    # shows 158 controls and all-ticks-on shows 188, but SIX appear in
    # neither. With only "Turn it by itself" on, the plain movement controls
    # are up — two choosers and four ⓘ (hint_axis_left_hint, _speed, _sweep,
    # hint_axis_up_hint) — and ticking the rest replaces them with the
    # adjust-them-yourself set. Four of the six are ⓘ icons, which is what
    # question 3 of this audit exists to look at.
    #
    # So rather than guess which combinations matter, this asks each tick on
    # its own whether it puts anything on screen that no measured state has
    # shown, and audits only those. On a window with nothing left over it
    # costs one pump per tickbox and reports zero extra states.
    alone = 0
    for tick in revealed_candidates:
        for other in revealed_candidates:
            other.setChecked(False)
        pump(app, 0.5)
        tick.setChecked(True)
        pump(app, 1.5)
        fresh = on_screen(panel) - covered
        if not fresh:
            continue
        alone += 1
        problems += audit_once(window, panel,
                               f"only '{tick.text()[:38]}' on")
        covered |= on_screen(panel)
        if shots:
            panel.grab().save(str(out / f"panel-only-{alone}.png"))
    print(f"  {alone} state(s) where one tick alone shows what the others "
          f"hide.")

    print()
    if prove:
        # THE MUTATION, DONE TO THE WINDOW THAT IS ALREADY BUILT rather than
        # to the source: the icon is taken out of the row it shares with its
        # checkbox and dropped back into the column underneath, which is
        # exactly where the attaching pass left it before it was placed by
        # hand.
        # THE OPTION HAS TO BE ON, or its icon is hidden and the rule skips
        # it -- correctly, because an explanation for something not on screen
        # is not stranded, it is absent. The state the loops above happen to
        # finish in is not something to rely on.
        if getattr(window, "_side_by_side", None) is not None:
            window._side_by_side.setChecked(True)
            pump(app, 1.5)
        stranded = strand_an_icon(panel)
        if not stranded:
            print("  THE MUTATION DID NOT LAND — no icon could be taken off "
                  "its row, so this\n  run tested nothing. Look at whether "
                  "hint_link_hint still shares a row\n  with its checkbox "
                  "before believing any Clean report from this check.")
            return 2
        pump(app, 1.0)
        caught = [p for p in audit_once(window, panel, "stranded on purpose")
                  if "STRANDED" in p]
        if caught:
            print(f"  --prove: {stranded} was taken off its row, and the "
                  f"audit named it:\n    {caught[0]}\n  The check can see.")
            return 0
        print(f"  --prove: {stranded} was taken off its row and the audit "
              f"still said nothing.\n  This check is blind.")
        return 1

    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} problem(s).")
        return 1
    checked = 2 * len(widths) * window._space.count() + extra + alone
    print(f"  Clean: {checked} panel states checked "
          f"(2 appearances × {len(widths)} widths × "
          f"{window._space.count()} spaces, plus {extra} with every tickbox "
          f"revealed and {alone} where one tick alone shows what the rest "
          f"hide), every control answered for.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
