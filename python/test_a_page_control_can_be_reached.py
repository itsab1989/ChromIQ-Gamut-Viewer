"""A control off the BOTTOM of a saved page is a fault too — and was unasked.

WHY THIS EXISTS. `scripts/page_questions.py` holds the questions both page
audits ask: `audit_the_page_at_any_size.py` in QtWebEngine, and
`audit_other_engines.py` in Gecko, WebKit and stock Chromium. Its own
docstring promised the reader's control strip was checked "inside the window
rather than off the bottom or the side". Only the side was ever measured:

  * the overflow loop asked `r.right > clientWidth || r.left < -1` and
    nothing about y;
  * `strip` was collected as `null` and never filled in or read;
  * the strip was looked for as `.cq-controls`, a name that matches NOTHING
    in any page this project writes — the strip is `.cq-spin-bar`.

So a page whose strip sits below the window, with no scroll that reaches it,
read Clean at all six sizes in all four engines. That is precisely the fault
reported from an iPhone that `audit_the_controls_can_be_shut.py` exists for:
"i can't see the less button any more ... effectively giving me no real
ability to use the controls without being locked out."

THE READINGS BELOW ARE REAL, not invented. Each is what the question actually
returned from chromium at 390x780 on `docs/pages/11-everything-handed-over.html`:
once as it ships, and twice with the strip pinned below the window — at 200vh,
past the end of everything you can scroll to, and at 120vh, which is still
INSIDE the document's scroll extent and is the case a reach-only rule misses.
A fixed element does not move when you scroll, so both are gone for good.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from page_questions import judge, rotted, said  # noqa: E402

_COUNTS = {"button": 44, "a": 1, ".cq-spin-bar": 1, ".cq-spin-panel": 1,
           ".modebar": 1}
_BASE = {"here": "Glossy-paper and Matte-paper — ChromIQ Gamut Viewer|5356490",
         "w": 390, "h": 780, "sideways": 0, "canvases": 1, "gl": 1, "glw": 780,
         "past": [], "svg": 13, "seen": 48, "counts": _COUNTS}

AS_IT_SHIPS = dict(_BASE, unreachable=[], strip="484..587 of 780")
BELOW_THE_DOCUMENT = dict(
    _BASE, strip="1560..1663 of 780",
    unreachable=["Pause−zoom+reset viewmor at y 1560..1663 "
                 "(pinned, window 780, scrolls to 1636)",
                 "more… at y 1621..1655 (window 780, scrolls to 1636)"])
BELOW_THE_WINDOW = dict(
    _BASE, strip="936..1039 of 780",
    unreachable=["Pause−zoom+reset viewmor at y 936..1039 "
                 "(pinned, window 780, scrolls to 1636)"])


def test_the_page_as_it_ships_is_clean():
    assert judge(AS_IT_SHIPS, "[as it ships]") == []


def test_a_strip_below_the_window_is_reported():
    for reading, where in ((BELOW_THE_DOCUMENT, "[at 200vh]"),
                           (BELOW_THE_WINDOW, "[at 120vh]")):
        found = judge(reading, where)
        assert found, (f"{where}: a control strip at {reading['strip']} cannot "
                       f"be reached by any scroll, and the question said "
                       f"nothing was wrong")
        assert any("out of reach" in line for line in found), found


def test_where_the_strip_IS_gets_said_out_loud():
    # A NUMBER NOBODY PRINTS IS A QUESTION NOBODY ASKED. The strip's position
    # is in every line of both audits' logs now, so a strip creeping towards
    # the edge is visible before it goes over.
    assert "strip 484..587 of 780" in said(AS_IT_SHIPS)
    assert "out of reach" in said(BELOW_THE_DOCUMENT)


def test_a_selector_that_matches_nothing_anywhere_is_reported():
    # THE ROT ITSELF. `.cq-controls` matched nothing for as long as it
    # existed, and a question that cannot see the thing it asks about reads
    # exactly like one that found nothing wrong.
    a_run_page = dict(_BASE, counts={"button": 0, ".cq-spin-bar": 0})
    assert rotted([AS_IT_SHIPS, a_run_page]) == [], (
        "a page that honestly offers no controls — the run pages are line "
        "graphs with no strip — must not be reported as a fault")
    dead = dict(_BASE, counts=dict(_COUNTS, **{".cq-spin-bar": 0}))
    assert rotted([dead, a_run_page]), (
        "a strip selector that matched nothing in the whole run went unsaid")
    assert rotted([]) , "a run that measured nothing at all went unsaid"


def test_both_audits_ask_the_run_level_question():
    # Two audits, one set of questions: neither may quietly stop asking.
    scripts = pathlib.Path(__file__).resolve().parent.parent / "scripts"
    for name in ("audit_other_engines.py", "audit_the_page_at_any_size.py"):
        text = (scripts / name).read_text()
        assert "rotted(readings)" in text, f"{name} no longer asks rotted()"
        assert "readings.append" in text or "readings)" in text, name


def test_the_dead_selector_is_gone():
    text = (pathlib.Path(__file__).resolve().parent.parent / "scripts"
            / "page_questions.py").read_text()
    body = text.split('"""', 2)[-1]
    assert "'button, a, .cq-spin-bar" in body
    assert "querySelectorAll('button, a, .cq-controls" not in body
