"""Whatever the chooser accepts, the comparison can build.

⚠ `_load_profile_as_comparison` REFUSED TWO OF THE THREE KINDS ITS OWN
CHOOSER ACCEPTS, and blamed the file for it. It read

    reader = gam_gamut if path.suffix.lower() == ".gam" else icc_gamut

so everything that was not a `.gam` went to `icc_gamut`. That is the exact
fault `_rebuild_reference` was repaired for — its comment records it: "a .ti3
held as the comparison was read as an ICC profile, failed with 'bad magic
number', and the comparison was silently dropped" — and this method never got
the repair. Driven, before the fix:

    a profile      -> ('Glossy-paper (profile)', 'lab', 2233 vertices)
    a measurement  -> WARN 'This profile could not be used'; comparison None
    a photograph   -> WARN 'This profile could not be used'; comparison None

⚠ AND IT LOOKED DEAD. Its own comment said "No caller today", which is true
of `python/` — the only mention there is the `def` itself — and false of the
drivers: `scripts/audit_bad_files.py` calls it twice and
`scripts/audit_run_beside_the_rest.py` once. Two of this project's own audits
were exercising a build route no reader has.
"""
import pathlib
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"


def _window():
    """A stand-in whose BUILDING is the real thing.

    `_build_one`, `_settings` and `_facts_key` are bound from `GamutApp`, so
    what is under test is the route a file takes to become a shape — not a
    fake of it.
    """
    import gamut_app
    win = NS(_white=NS(currentData=lambda: "D50"),
             _mode=NS(currentData=lambda: "device"),
             _relative=NS(isChecked=lambda: False),
             _detail=NS(value=lambda: 20),
             _build_space=lambda: "lab",
             _image_facts={},
             _reference=None, _reference_m=None, _reference_path=None,
             _compare=NS(blockSignals=lambda v: None,
                         findData=lambda d: 0,
                         setCurrentIndex=lambda i: None),
             _compare_note=NS(_t="", setText=lambda t, w=None: None),
             _redraw=lambda: None)
    said = {}
    win._compare_note = NS(setText=lambda t: said.__setitem__("note", t),
                           text=lambda: said.get("note", ""))
    for name in ("_build_one", "_settings", "_facts_key"):
        setattr(win, name,
                getattr(gamut_app.GamutApp, name).__get__(
                    win, gamut_app.GamutApp))
    win._warned = []
    return win


def _files():
    picture = next(iter(sorted((ROOT / "docs").rglob("*.png"))), None)
    return [(DEMO / "Glossy-paper.icc", "profile", False),
            (DEMO / "Glossy-paper.ti3", "measured", True),
            (picture, "picture", False)]


@pytest.mark.parametrize("path,word,keeps_measurement", _files())
def test_every_kind_the_chooser_offers_becomes_a_comparison(
        path, word, keeps_measurement):
    import gamut_app
    assert path is not None, "a file is missing — this case is untested"

    warned = []
    old = gamut_app.Notice.warn
    gamut_app.Notice.warn = staticmethod(
        lambda *a, **k: warned.append(str(a[1:3])))
    try:
        win = _window()
        gamut_app.GamutApp._load_profile_as_comparison(win, path)
    finally:
        gamut_app.Notice.warn = old

    assert not warned, f"{path.name} was refused: {warned}"
    assert win._reference is not None, (
        f"{path.name} was accepted by the chooser and produced no comparison")
    name, gamut = win._reference
    assert f"({word})" in name, f"{path.name} is labelled {name!r}"
    assert len(gamut.vertices) > 0
    # A measured chart carries its measurement; nothing else does. Dropping it
    # is what made judging fall back to reading a .ti3 as an ICC profile.
    assert (win._reference_m is not None) == keeps_measurement, (
        f"{path.name}: measurement kept={win._reference_m is not None}, "
        f"expected {keeps_measurement}")


def test_the_note_follows_the_kind_and_not_the_suffix():
    """⚠ THE SENTENCE UNDER THE BOX WAS A THIRD SUFFIX TEST.

    One branch picked it with `.icc/.icm/.gam` then `IMAGE_EXTENSIONS` then
    "otherwise a measurement"; this method printed "the colours this profile
    says are available" for everything, including a photograph. Both now ask
    `shapes.thing_for`, which is the one place that decides what a file is.
    """
    import gamut_app
    said = {}
    for path, word, _m in _files():
        said[word] = gamut_app._comparison_note(path)
    assert "profile" in said["profile"]
    assert "picture" in said["picture"]
    assert "measurement" in said["measured"]
    assert len(set(said.values())) == 3, (
        f"two kinds share one sentence: {said}")


def test_nothing_decides_a_kind_by_its_suffix_outside_the_one_place():
    """⚠ SIX COPIES OF "WHAT IS THIS FILE" HAVE BEEN FOUND IN THIS FILE.

    `shapes.thing_for`'s docstring says "the suffix test lives here and
    nowhere else". This checks the claim, because it has been false four
    times: `_shape_key`, `_in_lab`, `_load_profile_as_comparison` and the
    comparison note each had their own answer.
    """
    import ast
    import inspect
    import gamut_app

    tree = ast.parse(inspect.getsource(gamut_app))
    guilty = []
    for node in ast.walk(tree):
        # `.suffix.lower()` compared against a literal or a container
        if not isinstance(node, ast.Compare):
            continue
        text = ast.unparse(node)
        if ".suffix.lower()" not in text:
            continue
        if "PROFILE_SUFFIXES" in text or "IMAGE_EXTENSIONS" in text:
            continue          # asking the one table is the point
        guilty.append(text[:90])
    assert not guilty, (
        "a suffix test outside `shapes.thing_for` decides what a file is:\n  "
        + "\n  ".join(guilty))
