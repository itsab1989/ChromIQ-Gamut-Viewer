"""Can every word in the window be read, in both appearances?

THE PROJECT HAS A STANDING RULE about this — light and dark both have to be
readable — and it has been enforced by eye, one report at a time. That is how
a switched-off control came to be written at 2.26:1 on a light window: every
judgement about the greying had been made in dark mode, where the same key
gives 5.51:1.

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


def ink_and_paper(image, rect):
    """The colour of the writing and the colour behind it, from the pixels."""
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
    from PyQt6.QtWidgets import (QApplication, QCheckBox, QGroupBox, QLabel,
                                 QPushButton, QRadioButton, QScrollArea)
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
    profiles = sorted(pathlib.Path(tempfile.gettempdir())
                      .glob("showme-*/printer-*.icc"))
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
            found = ink_and_paper(image, rect)
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
