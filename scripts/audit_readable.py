"""Can every word in the window be read, in both appearances?

THE PROJECT HAS A STANDING RULE about this — light and dark both have to be
readable — and it has been enforced by eye, one report at a time. That is how
a switched-off control came to be written at 2.26:1 on a light window: every
judgement about the greying had been made in dark mode, where the same key
gives 5.51:1.

THE MEASUREMENT IS THE FRAGILE PART, and it has been wrong four times --
each time reporting a fault in perfectly readable text, each time found by a
case whose answer was known before it was asked. They are written into the
code at the place each one happened: which pixel counts as "the ink", the
one-pixel border of a small button, the tick at the start of a row, and the
ground a widget is actually drawn on. A number that repeats to the second
decimal across two different widgets is a measurement, not a fault.

WHAT THIS DOES, AND WHY IT IS NOT A LIST OF COLOURS. A stylesheet says what a
colour should be; a screenshot says what was drawn. This builds the window in
each appearance, photographs it, and then, for every piece of text on screen,
measures the ink against the paper it was drawn on:

  * the background is the commonest colour in the widget's own rectangle;
  * the ink is the colour furthest from it, taken at the 2nd percentile so a
    single antialiased pixel cannot speak for a whole label;
  * the two are compared by the usual contrast ratio.

Nothing is assumed about which colour a widget was GIVEN, so a rule that
lands on the wrong widget, an inline colour in rich text, or a palette that
was never consulted are all caught the same way.

    python scripts/audit_readable.py

Exit code 1 if any text falls below the floor for what it is.
"""
from __future__ import annotations

import collections
import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_readable"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

#: What each kind of text has to reach, and why each floor is where it is.
#:
#:   body    ordinary reading text: the usual 4.5:1.
#:   quiet   the explanations under a section: still read, still 3:1 at least,
#:           and deliberately not as loud as the controls they explain.
#:   off     a switched-off control. Exempt from 4.5 by every accessibility
#:           standard there is -- it is not something you are being asked to
#:           act on -- but "exempt" is not "may be invisible".
#:   large   the big accent buttons: white on a saturated ground, at a size
#:           and weight the standards themselves treat as large text.
#:   glyph   one or two characters -- x, the three dots -- where the shape
#:           carries the meaning and the word does not exist.
FLOORS = {"body": 4.5, "quiet": 3.0, "off": 3.0, "large": 3.0, "glyph": 3.0}


def contrast(one, other) -> float:
    def channel(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    def light(rgb):
        r, g, b = rgb[:3]
        return (0.2126 * channel(r) + 0.7152 * channel(g)
                + 0.0722 * channel(b))

    a, b = light(one), light(other)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def ink_and_paper(image, rect, skip_left: int = 0):
    """The colour of the writing and the colour behind it, from the pixels.

    *skip_left* leaves out the tick or the radio at the start of a row. A
    checkbox's indicator is further from the panel than its letters are -- an
    unchecked one is a bordered box, a checked one is the accent -- so it, and
    not the words, was being measured: two switches in the export dialog came
    back at 3.86:1 while their text is #22211f on #f7f4ef, which is 14.66:1.
    """

    left, top, wide, tall = rect
    if wide < 8 or tall < 6:
        return None
    # THE FRAME IS NOT THE WRITING. A small button is mostly its own fill with
    # a one-pixel border, and the border is further from that fill than the
    # letters are -- so the three dots on the "…" button were reported at
    # 1.71:1, which is the contrast between the button's fill and its border,
    # exactly. The glyph itself is 11:1. Sampled inside the frame.
    inset = 3
    if wide > 2 * inset + 4 and tall > 2 * inset + 4:
        left, top, wide, tall = (left + inset, top + inset,
                                 wide - 2 * inset, tall - 2 * inset)
    if skip_left and wide > skip_left + 12:
        left, wide = left + skip_left, wide - skip_left
    patch = image.crop((left, top, left + wide, top + tall)).convert("RGB")
    pixels = list(patch.getdata())
    if not pixels:
        return None
    paper = collections.Counter(pixels).most_common(1)[0][0]
    # WHICH PIXEL IS "THE INK" DECIDES EVERYTHING, and two ways of choosing
    # it were wrong before this one. The single furthest pixel lets one stray
    # antialiased value speak for a label. The middle of the furthest tenth
    # goes the other way: in a rect that is mostly background, that tenth is
    # nearly all half-lit edge, so ordinary black-on-white labels came out at
    # 2.80:1 when the two colours are 14.66:1 apart.
    #
    # The letters' own colour is the furthest one that occurs REPEATEDLY: a
    # letter has a core of identical pixels, an antialiased edge does not.
    seen = collections.Counter(pixels)
    solid = [colour for colour, times in seen.items() if times >= 3]
    if not solid:
        return None
    ink = max(solid, key=lambda p: sum((p[i] - paper[i]) ** 2
                                       for i in range(3)))
    if sum((ink[i] - paper[i]) ** 2 for i in range(3)) < 400:
        return None                       # nothing written here
    return ink, paper


def main() -> int:
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import (QApplication, QCheckBox, QGroupBox, QLabel,
                                 QPushButton, QRadioButton, QScrollArea,
                                 QWidget)
    from PIL import Image

    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    win = gamut_app.GamutApp([])
    win.resize(1500, 1000)
    win.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(3)
    import demo_profiles
    profiles = demo_profiles.the_run_of_profiles()
    if profiles:
        win._load(profiles[0])
        pump(6)
    column = win.findChild(QScrollArea).widget()
    for box in column.findChildren(QGroupBox):
        if hasattr(box, "_refold"):
            box._fold_open = True
            box._refold()
    pump(3)
    # A CROSS-SECTION, so the controls it switches off are in the picture as
    # well -- they are the ones this audit was written for.
    win._slice_on.setChecked(True)
    pump(5)

    folder = pathlib.Path(tempfile.mkdtemp(prefix="readable-"))
    problems, counted = [], 0
    for appearance in ("dark", "light"):
        win._set_appearance(appearance)
        pump(5)
        shot = folder / f"{appearance}.png"
        column.grab().save(str(shot))
        image = Image.open(shot)
        scale = image.width / max(1, column.width())
        print(f"\n  {appearance}")
        worst = []
        for widget in column.findChildren((QLabel, QCheckBox, QRadioButton,
                                           QPushButton)):
            if not widget.isVisibleTo(column) or not widget.text().strip():
                continue
            if isinstance(widget, gamut_app.Hint):
                continue
            spot = widget.mapTo(column, widget.rect().topLeft())
            rect = (int(spot.x() * scale), int(spot.y() * scale),
                    int(widget.width() * scale), int(widget.height() * scale))
            ticked = isinstance(widget, (QCheckBox, QRadioButton))
            found = ink_and_paper(image, rect,
                                  skip_left=int(22 * scale) if ticked else 0)
            if found is None:
                continue
            ink, paper = found
            ratio = contrast(ink, paper)
            counted += 1
            words = widget.text().strip()
            accent = contrast(paper, (255, 69, 115)) < 1.6
            kind = ("off" if not widget.isEnabled()
                    else "glyph" if len(words) <= 2
                    else "large" if accent
                    else "quiet" if widget.objectName() in ("hint", "slot")
                    else "body")
            worst.append((ratio, kind, widget.text().strip()[:44]))
            if ratio < FLOORS[kind]:
                problems.append(
                    f"[readable] {appearance}: “{widget.text().strip()[:44]}” "
                    f"is {ratio:.2f}:1 against what it is drawn on, and a "
                    f"{kind} one has to reach {FLOORS[kind]}:1")
        worst.sort()
        for ratio, kind, text in worst[:6]:
            print(f"      {ratio:>6.2f}:1  {kind:<5}  {text}")

    # ---- AND THE WINDOWS THAT OPEN ON TOP OF IT --------------------------
    # The column is where most of the words are and not where all of them
    # are: the two save dialogs and the message box carry sentences somebody
    # has to read before pressing anything, and they were never in this.
    #
    # SHOWN RATHER THAN EXECUTED, because exec() waits for a person and a
    # check has none. Everything about how they are painted is the same
    # either way -- the stylesheet is the window's, applied at polish.
    for appearance in ("dark", "light"):
        win._set_appearance(appearance)
        pump(3)
        for name, make in (
                ("the picture dialog", lambda: gamut_app.PictureDialog(win)),
                ("the web page dialog", lambda: gamut_app.WebPageDialog(win)),
                ("a message", lambda: gamut_app.Notice(
                    win, "Two profiles were not read",
                    "Both of these were made on the same day, which is not "
                    "what this view is for. Open profiles of one device made "
                    "on different days.", cancel="Cancel"))):
            dialog = make()
            dialog.show()
            pump(2.0)
            # EACH WIDGET RENDERED ONTO THE DIALOG'S OWN GROUND, rather than
            # cropped out of a photograph of the dialog. Cropping needs the
            # widget's position to agree with the picture, and offscreen it
            # does not: measured, a checkbox reported itself 10 points tall
            # at half the y it was drawn at, so every rectangle landed on the
            # explanation line above and two switches came back at 3.86:1 --
            # which is the contrast of THAT line, in both appearances,
            # identical to the second decimal. A number that repeats exactly
            # across two different widgets is a measurement, not a fault.
            ground = dialog.palette().color(dialog.backgroundRole())
            for widget in dialog.findChildren((QLabel, QCheckBox, QRadioButton,
                                               QPushButton)):
                if not widget.isVisibleTo(dialog) or not widget.text().strip():
                    continue
                if isinstance(widget, gamut_app.Hint):
                    continue
                if widget.width() < 24 or widget.height() < 10:
                    continue
                # THE PARENT IS RENDERED, AND THE WIDGET FOUND INSIDE IT.
                # Filling with the dialog's own background colour was wrong
                # wherever something paints a card of its own: the message
                # box draws one, so its title came back at 1.31:1 -- pale
                # text on the dialog's ground rather than on the card it is
                # actually written on. A parent renders its background AND
                # its children, and the mapping to it is one hop.
                parent = widget.parentWidget() or dialog
                picture = QImage(parent.size() * 2,
                                 QImage.Format.Format_RGB32)
                picture.fill(ground)
                painter = QPainter(picture)
                painter.scale(2, 2)
                parent.render(painter, QPoint(0, 0),
                              flags=QWidget.RenderFlag.DrawChildren)
                painter.end()
                shot = folder / "one.png"
                picture.save(str(shot))
                spot = widget.mapTo(parent, widget.rect().topLeft())
                ticked = isinstance(widget, (QCheckBox, QRadioButton))
                found = ink_and_paper(Image.open(shot),
                                      (spot.x() * 2, spot.y() * 2,
                                       widget.width() * 2,
                                       widget.height() * 2),
                                      skip_left=44 if ticked else 0)
                if found is None:
                    continue
                ink, paper = found
                ratio = contrast(ink, paper)
                counted += 1
                words = widget.text().strip()
                accent = contrast(paper, (255, 69, 115)) < 1.6
                kind = ("off" if not widget.isEnabled()
                        else "glyph" if len(words) <= 2
                        else "large" if accent
                        else "quiet" if widget.objectName() in ("hint", "slot",
                                                               "noticeBody")
                        else "body")
                if ratio < FLOORS[kind]:
                    problems.append(
                        f"[readable] {appearance}, {name}: “{words[:40]}” is "
                        f"{ratio:.2f}:1 against what it is drawn on, and a "
                        f"{kind} one has to reach {FLOORS[kind]}:1")
            dialog.close()
            dialog.deleteLater()
            pump(0.4)

    # ---- AND THE PAGES SOMEBODY IS SENT ----------------------------------
    # A saved page carries four grounds a reader can switch between, and the
    # window's own appearance is only two of them. Nothing here is rendered:
    # these are plain colour pairs, so they are compared as such.
    #
    # THE FLOOR IS THE QUIET ONE, and that is a decision rather than a
    # convenience: a caption and an axis number annotate a picture rather
    # than being read as prose, and the standards' 4.5 is written for prose.
    # Below 3:1 they stop being legible at all, and that is the line.
    from ti3gamut import SCENE_COLOURS

    print("\n  the grounds a saved page can be switched to")
    for name, ground in SCENE_COLOURS.items():
        page, plot = ground.get("page"), ground.get("plot")
        if not page or not plot or len(str(page)) != 7:
            continue                      # "none" is see-through, not a colour
        def rgb(value):
            value = value.lstrip("#")
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        for what, ink, paper in (("the caption", ground.get("caption"), page),
                                 ("the lettering", ground.get("text"), plot)):
            if not ink or len(str(ink)) != 7:
                continue
            ratio = contrast(rgb(ink), rgb(paper))
            counted += 1
            print(f"      {name:<6} {what:<14} {ratio:>6.2f}:1")
            if ratio < FLOORS["quiet"]:
                problems.append(
                    f"[readable] a page on {name}: {what} is {ratio:.2f}:1 "
                    f"against the ground it is drawn on")

    import shutil
    shutil.rmtree(folder, ignore_errors=True)
    print(f"\n  {counted} pieces of text measured, in two appearances.")
    if problems:
        for line in sorted(set(problems)):
            print("  " + line)
        print(f"\n{len(set(problems))} of them cannot be read properly.")
        win.close()
        return 1
    print("  Clean: every word reaches the floor for what it is.")
    win.close()
    pump(0.3)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
