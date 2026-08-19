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
NOT ASKED, AND THE REASON IS MEASURED. The fourth question — "is every
control the README names still in the window?" — was written, run, and taken
out again: it produced seventeen complaints of which about two were real,
because this README uses bold for emphasis as often as for quotation. The
detail is in the comment where it would go. It needs the window's own list of
control labels to compare against; guessing from punctuation does not work.

NOT CHECKED HERE, and said rather than implied: whether a screenshot still
LOOKS like the window. That needs the window drawn and compared, which
`scripts/make_screenshots.py` does; this asks the questions that can be
answered from the text and the tree.
"""
from __future__ import annotations

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

        # THE CONTROLS IT QUOTES — NOT YET, AND THE REASON IS MEASURED.
        #
        # The obvious rule is "every bold phrase in the README is a control's
        # name, so it must appear in the window's own words". Written and run,
        # it produced SEVENTEEN complaints and about two of them were real:
        # this README uses bold for emphasis as much as for quotation, so
        # "**Usually not**", "**Where an installer puts it**" and
        # "**88.8% of the picture unlike the solid one to 0.7%**" were all
        # reported as missing controls.
        #
        # A check that cries seventeen times to be right twice will be ignored,
        # and then it is worse than nothing — this project has met that before
        # with a pixel comparison that raised 77 false alarms. Telling a quoted
        # LABEL from an emphasised PHRASE needs the window's own list of
        # control texts to compare against, not a guess from punctuation, and
        # that is the piece of work this line is waiting for.

    print(f"  {links} link(s), {anchors} anchor(s), {pictures} picture(s) "
          f"checked")
    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: every link lands, every anchor exists and every picture "
          "is there.\n  Whether the words still describe the window is NOT "
          "asked here — see the note\n  in the loop above for why not, and "
          "what it would take.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
