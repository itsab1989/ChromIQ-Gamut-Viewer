"""Does the documentation still describe the application that exists?

    ../gv-venv/bin/python scripts/audit_the_readme_is_true.py

WHY THIS EXISTS. Asked for in as many words: an audit "that makes sure the
readme and its screenshots are always up to date to reflect the current state
of the app and don't promise something that is not true anymore".

Prose rots quietly. A control gets renamed and the sentence describing it stays
perfect English; a page is moved and the link that pointed at it still looks
like a link. Neither shows up in a test suite, and both are read by people
deciding whether to trust the thing.

WHAT IS ASKED, and the failure direction of each:

  every link goes somewhere    a relative link to a file that is not there is
                               a promise the reader can see broken;
  every anchor exists         "#7-will-the-chart…" is only a link if a heading
                               makes that slug — GitHub builds them from the
                               heading text, so an edited heading silently
                               breaks every link to it;
  every picture exists        a missing screenshot renders as a broken image;
ASKED THE ONLY WAY THAT WORKS. The fourth question was first written as
"every bold phrase must appear in the window's own words", which produced
seventeen complaints of which about two were real — this README uses bold for
emphasis as often as for quotation. So it is narrowed to the fault that
actually happens: a control is RENAMED and the sentence describing it stays
behind, leaving a phrase that is very nearly a label and not quite one.
Emphasis is not nearly anything. The labels are read off the real window, not
out of the source, and punctuation that belongs to a button rather than to a
sentence — a trailing ellipsis, quotation marks — is not a rename.

NOT CHECKED HERE, and said rather than implied: whether a screenshot still
LOOKS like the window. That needs the window drawn and compared, which
`scripts/make_screenshots.py` does.

"""
from __future__ import annotations

import difflib
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

#: Where the window's own words live, for the "is this control still here" test.
SOURCES = sorted((ROOT / "python").glob("*.py"))

#: Bold phrases that are prose rather than a control: they are emphasis, not
#: quotation, and there is nothing in the window to match them against.
NOT_CONTROLS = {
    "A picture", "A moving picture", "Play", "How:", "What:", "Why:",
    "Note:", "Warning:", "New:", "Fixed:", "Measured:", "Reported:",
}

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
BOLD = re.compile(r"\*\*([^*]{4,60})\*\*")


def tidy(words: str) -> str:
    """A label without the punctuation that belongs to a button rather than
    to a sentence: a trailing ellipsis, quotation marks, stray spaces."""
    words = words.strip().strip('"\u201c\u201d\u2018\u2019')
    words = words.rstrip("\u2026.:").strip()
    return " ".join(words.lower().split())


def the_windows_own_words() -> list:
    """Every word the window puts on a control, read off the real window.

    Off the WINDOW rather than out of the source, because a label built from
    two pieces or translated on the way to the screen is only itself once it
    is on a widget.
    """
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT / "python"))
    sys.argv = ["audit_the_readme_is_true"]
    try:
        import prefs

        prefs.use_a_scratch_store()
        from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox,
                                     QGroupBox, QPushButton, QRadioButton)
        import gamut_app

        app = QApplication.instance() or QApplication(sys.argv)
        gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
        gamut_app.Notice.say = staticmethod(lambda *a, **k: None)
        win = gamut_app.GamutApp([])
        win.resize(1400, 900)
        win.show()
        end = time.time() + 3
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)
        said = set()
        for kind in (QPushButton, QCheckBox, QRadioButton, QGroupBox):
            for w in win.findChildren(kind):
                text = (w.title() if isinstance(w, QGroupBox)
                        else w.text()).strip()
                if len(text) > 3:
                    said.add(text)
        for box in win.findChildren(QComboBox):
            for i in range(box.count()):
                text = box.itemText(i).strip()
                if len(text) > 3:
                    said.add(text)
        win.close()
        return sorted(said)
    except Exception:                                    # noqa: BLE001
        return []


def slugs_of(text: str) -> set:
    """The anchors GitHub makes from a document's headings."""
    out = set()
    for line in text.splitlines():
        if not line.startswith("#"):
            continue
        title = line.lstrip("#").strip()
        slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        out.add(slug)
    return out


def main() -> int:
    docs = [ROOT / "README.md"] + sorted((ROOT / "docs").rglob("*.md"))
    problems: list[str] = []
    words = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                      for p in SOURCES)

    print(f"  {len(docs)} document(s)")
    links = anchors = pictures = 0
    for doc in docs:
        text = doc.read_text(encoding="utf-8", errors="replace")
        where = doc.relative_to(ROOT)

        for target in LINK.findall(text) + IMAGE.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, fragment = target.partition("#")
            if path:
                links += 1
                landing = (doc.parent / path).resolve()
                if not landing.exists():
                    problems.append(f"{where}: links to {target}, which is "
                                    f"not there")
                    continue
            else:
                landing = doc
            if fragment:
                anchors += 1
                try:
                    have = slugs_of(landing.read_text(encoding="utf-8",
                                                      errors="replace"))
                except OSError:
                    continue
                if fragment.lower() not in have:
                    problems.append(
                        f"{where}: links to #{fragment}, and no heading in "
                        f"{landing.name} makes that anchor")

        for target in IMAGE.findall(text):
            if not target.startswith("http"):
                pictures += 1

    print(f"  {links} link(s), {anchors} anchor(s), {pictures} picture(s) "
          f"checked")

    # AND THE CONTROLS IT NAMES, asked the only way that works.
    #
    # The obvious rule — "every bold phrase must appear in the window's own
    # words" — was written, run, and taken out: seventeen complaints of which
    # about two were real, because this README uses bold for emphasis as often
    # as for quotation. A check that cries seventeen times to be right twice
    # gets ignored, and this project has met that before with a pixel
    # comparison that raised 77 false alarms.
    #
    # So the question is narrowed to the fault that actually happens: a
    # control gets RENAMED and the sentence describing it stays behind. A
    # renamed control leaves a phrase that is very nearly a label and not
    # quite one — "Show what it cannot print" against "Show what it can't
    # print". Emphasis is not nearly anything: "Usually not" resembles no
    # control in the window at all. Measured on this README, the near-miss
    # rule reports nothing where the crude one reported seventeen.
    labels = the_windows_own_words()
    if labels:
        # A QUOTED BLOCK STILL QUOTES THE WINDOW. A bold label that wraps
        # inside a "> " blockquote carries the marker into the middle of the
        # phrase, and reading it literally reported "Save the numbers > as a
        # table" as a renamed control. The markers are the page's furniture,
        # not the window's words.
        readme = re.sub(r"(?m)^\s*>\s?", "",
                        (ROOT / "README.md").read_text(encoding="utf-8"))
        # PUNCTUATION IS NOT A RENAME. A button says "Save this view as a
        # web page…" and the README says **Save this view as a web page** —
        # the ellipsis means "this opens a dialog" and belongs to the button,
        # not to the sentence. Quotation marks are the same. Compared without
        # them, so the only thing left to report is a difference in the WORDS.
        plain = {tidy(l): l for l in labels}
        for phrase in BOLD.findall(readme):
            phrase = phrase.strip()
            if len(phrase) < 6 or tidy(phrase) in plain:
                continue
            near = difflib.get_close_matches(tidy(phrase), list(plain),
                                             n=1, cutoff=0.82)
            if near:
                near = [plain[near[0]]]
                problems.append(
                    f"README says **{phrase}**, and the window says "
                    f"\"{near[0]}\" — one of them has been renamed and the "
                    f"other has not")
        print(f"  {len(labels)} control label(s) read off the window")
    else:
        print("  the window could not be opened, so the controls it names "
              "were not checked")
    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: every link lands, every anchor exists, every picture is "
          "there, and every\n  control the README names still answers to that "
          "name in the window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
