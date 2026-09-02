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
             # ⚠ THE CACHES ARE REAL DICTS AND THE FORGETTING IS THE REAL
             # METHOD. Choosing a file again is what rebuilds it — the shape
             # caches must be emptied of that path before the build, or an
             # edited file hands back the shape it used to have. A stand-in
             # with a no-op `_forget_shapes_of` would let this test pass over
             # a route that forgot nothing, which is exactly what it is here
             # to catch.
             _lab_gamuts={}, _other_whites={}, _reference_cache={},
             _slots=[],
             _reference=None, _reference_m=None, _reference_path=None,
             _compare=NS(blockSignals=lambda v: None,
                         findData=lambda d: 0,
                         setCurrentIndex=lambda i: None),
             _compare_note=NS(_t="", setText=lambda t, w=None: None),
             _redraw=lambda: None)
    said = {}
    win._compare_note = NS(setText=lambda t: said.__setitem__("note", t),
                           text=lambda: said.get("note", ""))
    for name in ("_build_one", "_settings", "_facts_key",
                 "_forget_shapes_of", "_forget_unused_facts"):
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

    # ⚠ AND THE FOURTH KIND, WHICH THIS TEST COULD NOT SEE. `_files()` offers
    # a .icc, a .ti3 and a .png — there is no .gam in this repository — so
    # the count above was "3 distinct for 3 kinds" while a fourth row sat in
    # the table with the profile's words copied into it. Choosing a .gam gave
    # a box reading "Glossy-paper (gamut file)" with "The gamut this profile
    # describes, asked of the profile itself" printed underneath: the window
    # contradicting itself, four lines apart, about the one distinction it
    # exists to draw. `_profiles_on_screen` says why that matters — "a .gam
    # file is a bare surface with no way in from device values at all" — and
    # it is why a .gam may not place a chart.
    #
    # The table is checked directly, because a fixture this repository does
    # not have cannot be relied on to check it.
    every = gamut_app.COMPARISON_NOTES
    assert len(set(every.values())) == len(every), (
        "two kinds share one sentence in COMPARISON_NOTES, so the note "
        f"under the box can contradict the label above it: {every}")
    assert "profile" not in every["gamutfile"], (
        "a gamut file is described as a profile: "
        f"{every['gamutfile']!r} — the label beside it says 'gamut file'")
    assert set(every) == {"profile", "gamutfile", "picture", "measurement"}, (
        f"the table no longer covers the kinds a comparison can be: "
        f"{sorted(every)}")


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

    # ⚠ FOLLOW THE VARIABLE. The first version of this rule read only the
    # COMPARISON, so a survivor written
    #
    #     suffix = path.suffix.lower()
    #     ...
    #     elif suffix in (".icc", ".icm"):
    #
    # walked straight past it: the `.suffix.lower()` is one line up, in an
    # assignment, and the comparison's text does not contain it. The rule was
    # added in the same commit that claimed "the suffix test lives in one
    # place at last", and there were EIGHT, not seven. Rewriting that same
    # survivor in the direct form made the rule fail at once — so the fault
    # was never the code being subtle, it was the finder reading one node.
    #
    # This is the second finder in this project to be widened for exactly
    # this reason; `_mentions_rebuild` had to learn the same lesson about
    # aliases. A finder that matches on how something is SPELLED will be
    # walked past.
    aliased = {t.id for node in ast.walk(tree)
               if isinstance(node, ast.Assign)
               and ".suffix.lower()" in ast.unparse(node.value)
               for t in node.targets if isinstance(t, ast.Name)}

    guilty = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        text = ast.unparse(node)
        asks_the_suffix = (
            ".suffix.lower()" in text
            or any(isinstance(node.left, ast.Name) and node.left.id == name
                   for name in aliased))
        if not asks_the_suffix:
            continue
        if "PROFILE_SUFFIXES" in text or "IMAGE_EXTENSIONS" in text:
            continue          # asking the one table is the point
        guilty.append(text[:90])
    assert not guilty, (
        "a suffix test outside `shapes.thing_for` decides what a file is:\n  "
        + "\n  ".join(guilty))


def test_the_rule_sees_a_suffix_held_in_a_variable():
    """⚠ THE CONTROL THE RULE DID NOT HAVE, and the reason it missed one.

    The rule above walked past

        suffix = path.suffix.lower()
        ...
        elif suffix in (".icc", ".icm"):

    because it read the COMPARISON, whose text does not contain
    `.suffix.lower()` — that is one line up, in an assignment. Eight copies
    existed while the commit that added the rule claimed there was one.

    This is the SECOND finder in this project to be walked past for exactly
    this reason: `_mentions_rebuild` had to learn the same lesson about a
    method reached through an alias. A finder that matches on how something
    is spelled will be got round; the lesson was written down that morning
    and not carried across to this rule the same afternoon.
    """
    import ast

    hidden = '''
def _a_label_that_decides_for_itself(self, path):
    suffix = path.suffix.lower()
    if suffix in (".icc", ".icm"):
        return "an ICC profile"
    return "a gamut file"
'''
    tree = ast.parse(hidden)
    aliased = {t.id for node in ast.walk(tree)
               if isinstance(node, ast.Assign)
               and ".suffix.lower()" in ast.unparse(node.value)
               for t in node.targets if isinstance(t, ast.Name)}
    assert aliased == {"suffix"}, (
        f"the finder cannot see a suffix put in a variable: {aliased}")

    caught = [ast.unparse(n) for n in ast.walk(tree)
              if isinstance(n, ast.Compare)
              and isinstance(n.left, ast.Name) and n.left.id in aliased]
    assert caught, (
        "the finder sees the assignment but not the comparison that uses it, "
        "which is the half that decides what the file IS")


def test_choosing_a_file_again_forgets_what_it_knew_about_it():
    """⚠ THE ROUTE WAS GIVEN THE BUILDER AND NOT THE FORGETTING.

    Its sibling — the reader's route through the chooser — empties three
    things before it builds, and says why: "ASKING FOR A FILE AGAIN IS WHAT
    REBUILDS IT. The cache key no longer carries the file's timestamp — that
    made the numbers describe a file the window was not drawing — so the
    rebuild belongs on the gesture instead ... Choosing a file that has been
    edited since must not hand back the shape it used to have."

    `_load_profile_as_comparison` was routed through `_build_one` one commit
    later and did none of the three, so it would hand back the shape an
    edited file used to have, and every photograph it opened stayed in
    `_image_facts` for the life of the window — about 9.6 MB each, by
    `_forget_unused_facts`'s own measurement. Driven before the fix:

        after choosing holiday2.png through the chooser
           _image_facts keys: ['holiday2.png']
        after _load_profile_as_comparison(holiday3.png)
           _image_facts keys: ['holiday2.png', 'holiday3.png']

    with holiday2 in no slot and not the comparison.
    """
    import gamut_app
    picture = next(iter(sorted((ROOT / "docs").rglob("*.png"))), None)
    assert picture is not None

    win = _window()
    stale = pathlib.Path("/x/an-old-photograph.png")
    # A shape and some facts the window is no longer showing, keyed the way
    # the real caches key them.
    win._lab_gamuts[("picture", str(picture), "D50", "lab")] = object()
    win._image_facts[win._facts_key(stale)] = {"colours": 1, "pixels": 1}
    win._reference_cache["anything"] = object()

    gamut_app.GamutApp._load_profile_as_comparison(win, picture)

    assert win._reference_cache == {}, (
        "the comparison cache survived a file being chosen again, so the "
        "numbers can describe a file the window is not drawing")
    assert not [k for k in win._lab_gamuts if k[1] == str(picture)], (
        "the shape of the file just chosen was kept, so an edited file hands "
        "back the shape it used to have")
    assert win._facts_key(stale) not in win._image_facts, (
        "a photograph nothing is showing kept its colours — about 9.6 MB — "
        "for the life of the window")
    # AND THE FILE JUST CHOSEN KEEPS ITS OWN, because it is the comparison.
    assert win._facts_key(picture) in win._image_facts, (
        "the picture now being compared against lost its own colours")
