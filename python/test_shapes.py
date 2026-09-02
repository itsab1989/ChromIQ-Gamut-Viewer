"""The dependency table, proved by BUILDING — never by reading itself back.

⚠ A TABLE THAT ASSERTS ITSELF PROVES NOTHING, and this project has been
caught by exactly that three times in two days: a test that checked a word
appeared in a function's source, a sweep that matched its own record of what
it had corrected, and a stand-in that watched the wrong write. So every cell
below is decided by building the shape twice, changing ONE setting, and
looking at the vertices that come back.

The table is the thing four separate cache keys guessed at differently. Three
of them put `detail` in for files, which made every nudge of Detail a
guaranteed miss returning a bit-identical answer at 3.67 s a time.
"""
import pathlib

import numpy as np
import pytest

import shapes


HERE = pathlib.Path(__file__).resolve().parent.parent
DEMO = HERE / "demo"


def a_picture():
    for candidate in sorted((HERE / "docs").rglob("*.png")):
        return candidate
    return None


def build(thing, settings):
    """Build a thing the way the application's builders do today.

    ⚠ THIS DELIBERATELY CALLS THE REAL BUILDERS. The point of the test is to
    learn what they actually depend on, not what `shapes.KINDS` claims.
    """
    from gamutview import build_gamut, xyz_to_lab
    from references import icc_gamut, gam_gamut, reference_gamut
    from spectral import optimal_colour_solid
    from ti3gamut import read_measurement

    if thing.kind == "measurement":
        m = read_measurement(thing.path, settings.white, settings.tick)
        drive = None if settings.mode == "hull" else m.device
        return build_gamut(m.lab, drive, input_space="lab",
                           space=settings.space, white_point=settings.white)
    if thing.kind == "profile":
        return icc_gamut(thing.path, white_point=settings.white,
                         space=settings.space)
    if thing.kind == "gamutfile":
        return gam_gamut(thing.path, white_point=settings.white,
                         space=settings.space)
    if thing.kind == "picture":
        from imagegamut import image_gamut
        built, _facts = image_gamut(thing.path, white_point=settings.white,
                                    space=settings.space)
        return built
    if thing.kind == "space":
        return reference_gamut(thing.name, white_point=settings.white,
                               steps=settings.detail, space=settings.space)
    verts, _f = optimal_colour_solid(
        "D50" if settings.white == "D50" else "D65",
        max(24, settings.detail * 3))
    return build_gamut(xyz_to_lab(verts, settings.white), input_space="lab",
                       space=settings.space, white_point=settings.white)


def moved(thing, base, changed):
    """Did the shape actually change when that one setting changed?"""
    a = np.asarray(build(thing, base).vertices, float)
    b = np.asarray(build(thing, changed).vertices, float)
    if a.shape != b.shape:
        return True
    return not np.allclose(a, b, atol=1e-9)


OTHER = {"white": ("D50", "D65"), "space": ("lab", "luv"),
         "mode": ("device", "hull"), "tick": (False, True),
         "detail": (9, 17)}


def a_gamut_file(tmp_path):
    """A real .gam, made the way ChromIQ makes one. ⚠ WITHOUT THIS, THE
    `gamutfile` ROW OF THE TABLE IS DECIDED BY NOTHING — a review found that
    `depends=()` for it survived the whole suite, which would have served
    every .gam from cache in whatever space it was first built in."""
    import shutil
    import subprocess
    tool = shutil.which("iccgamut") or "/Applications/Argyll/bin/iccgamut"
    if not pathlib.Path(tool).exists():
        return None
    work = tmp_path / "Glossy-paper.icc"
    shutil.copyfile(DEMO / "Glossy-paper.icc", work)
    try:
        subprocess.run([tool, "-i", "r", "-d", "6", str(work)],
                       capture_output=True, timeout=120, check=True)
    except Exception:            # noqa: BLE001 — no Argyll, no fixture
        return None
    made = work.with_suffix(".gam")
    return made if made.is_file() else None


def things(tmp_path=None):
    out = [(shapes.Thing("measurement", DEMO / "Glossy-paper.ti3"), "a paper"),
           (shapes.Thing("profile", DEMO / "Glossy-paper.icc"), "a profile"),
           (shapes.a_space("sRGB"), "a colour space"),
           (shapes.the_visible_solid(), "the visible solid")]
    picture = a_picture()
    if picture is not None:
        out.append((shapes.Thing("picture", picture), "a photograph"))
    if tmp_path is not None:
        gam = a_gamut_file(tmp_path)
        if gam is not None:
            out.append((shapes.Thing("gamutfile", gam), "a gamut file"))
    return out


@pytest.mark.slow
def test_nothing_the_table_denies_can_move_the_shape(tmp_path):
    """⚠ THE SAFETY DIRECTION, AND IT IS THE ONLY HARD ONE.

    The two directions are not symmetric. A setting the table DENIES that
    really does move the shape is a correctness bug: every cache keyed by
    this rule hands back a stale answer, which is how three caches came to
    hold `detail` and how one nearly returned the shape a file used to have.
    A setting the table CLAIMS that does not move the shape is only a cost —
    an unnecessary rebuild, which is what `detail` in a file's key really
    was, at 3.67 s a nudge.

    So: denied settings are asserted, claimed settings are measured and
    reported. Guessing wrong in the safe direction must not fail a test;
    guessing wrong in the dangerous one must.
    """
    from dataclasses import replace as _replace
    checked = 0
    reached = set()
    for thing, said in things(tmp_path):
        reached.add(thing.kind)
        declared = set(shapes.depends_on(thing))
        for setting, (first, second) in OTHER.items():
            if setting in declared:
                continue
            # ⚠ IN EVERY SPACE, NOT JUST CIELAB. The first version of this
            # built its base as `Settings(detail=9)`, whose space defaults to
            # "lab", and never varied it — so the DANGEROUS direction was
            # only ever asserted in CIELAB while the safe one swept two
            # spaces. The asymmetry was exactly backwards, and deleting
            # `white` from a profile's dependencies passed all 1,195 tests:
            # a profile's shape is identical under D50 and D65 in CIELAB and
            # MOVES in both CIELUV and CIE XYZ.
            for space in ("lab", "luv", "xyz"):
                base = shapes.Settings(detail=9, space=space)
                a = _replace(base, **{setting: first})
                b = _replace(base, **{setting: second})
                checked += 1
                assert not moved(thing, a, b), (
                    f"{said}: the table says {setting!r} does not reach it, "
                    f"and in {space} changing it MOVED THE SHAPE — every "
                    "cache keyed by this rule would hand back a stale answer")
    # ⚠ A FLOOR ON CELLS CANNOT NOTICE A MISSING KIND: four kinds contributed
    # nine denials on their own while two kinds were never built at all.
    missing = set(shapes.KINDS) - reached - {"gamutfile"}
    assert not missing, f"these kinds were never built, so their row of the table is decided by nothing: {missing}"


@pytest.mark.slow
def test_what_the_table_claims_is_measured_and_recorded(tmp_path):
    """The other direction, measured rather than asserted — a claim that
    never moves anything is pure cost, and the record should say which.

    ⚠ MEASURED HERE, NOT GUESSED: the white point does NOT move a profile's
    shape in CIELAB — Argyll returns Lab vertices and only a conversion to
    another space uses the white — so `white` in a profile's key costs one
    Argyll call per white-point change while the picture is drawn in CIELAB.
    It stays in the table because a profile drawn in CIELUV or CIE XYZ DOES
    move, and under-declaring is the dangerous direction.
    """
    from dataclasses import replace as _replace
    idle = []
    for thing, said in things(tmp_path):
        for setting, (first, second) in OTHER.items():
            if setting not in set(shapes.depends_on(thing)):
                continue
            moves_somewhere = False
            for space in ("lab", "luv"):
                base = shapes.Settings(detail=9, space=space)
                if moved(thing, _replace(base, **{setting: first}),
                         _replace(base, **{setting: second})):
                    moves_somewhere = True
                    break
            if not moves_somewhere:
                idle.append(f"{said}: {setting}")
    assert not idle, (
        "these are claimed by the table and move nothing in any space, so "
        f"they are pure cost in every cache: {idle}")


def test_a_file_is_classified_in_one_place_and_a_picture_is_not_a_profile():
    """The disagreement that put "480 outside, worst 99.0 ΔE" on screen:
    `_in_lab` read every path that was not a .gam as an ICC profile."""
    from imagegamut import readable_extensions
    images = readable_extensions()
    assert shapes.thing_for("p.icc", images).kind == "profile"
    assert shapes.thing_for("p.ICM", images).kind == "profile"
    assert shapes.thing_for("s.gam", images).kind == "gamutfile"
    assert shapes.thing_for("holiday.png", images).kind == "picture"
    assert shapes.thing_for("holiday.JPG", images).kind == "picture"
    assert shapes.thing_for("paper.ti3", images).kind == "measurement"
    assert shapes.thing_for("paper.cxf", images).kind == "measurement"


def test_the_key_carries_only_what_matters():
    """⚠ AND NOT THE FILE'S TIMESTAMP, WHICH IT USED TO DEMAND. A key made
    from disk NOW, for a shape built when the file was OPENED, meant the
    numbers could describe content the window was not drawing — driven, a
    photograph re-saved in place: drawn volume 212,188, judged volume 0.
    The rebuild lives on the gesture that asks for the file again.
    """
    s = shapes.Settings()
    paper = shapes.Thing("measurement", DEMO / "Glossy-paper.ti3")
    stamp = (DEMO / "Glossy-paper.ti3").stat().st_mtime_ns
    assert stamp not in shapes.key_for(paper, s)
    # Detail reaches the synthetic kinds and nothing else.
    assert shapes.key_for(paper, s) == shapes.key_for(paper,
                                                      s.drawn_in("lab"))
    assert shapes.key_for(paper, s) != shapes.key_for(paper, s.with_tick(True))
    srgb = shapes.a_space("sRGB")
    from dataclasses import replace
    assert shapes.key_for(srgb, s) != shapes.key_for(srgb,
                                                     replace(s, detail=9))
    assert shapes.key_for(srgb, s) == shapes.key_for(srgb, s.with_tick(True))


def test_a_kind_that_needs_a_file_refuses_to_exist_without_one():
    """`Path(None)` crashed the window on an ordinary change of Draw it in.
    A thing that cannot be built cannot be made."""
    with pytest.raises(ValueError):
        shapes.Thing("measurement", None)
    with pytest.raises(ValueError):
        shapes.Thing("space", DEMO / "Glossy-paper.ti3")
    with pytest.raises(ValueError):
        shapes.Thing("nonsense", None)


def test_a_kind_with_no_builder_refuses_instead_of_reading_it_as_paper(
        tmp_path):
    """⚠ THE FALL-THROUGH RETURNED A PLAUSIBLE ANSWER, NOT AN ERROR.

    `shape_for` ended with the measurement build rather than a branch, so a
    kind nobody had written a builder for would have been read as a measured
    paper — and `read_measurement` SUCCEEDS on an ArgyllCMS ICC profile,
    because the CTI3 target is embedded in it as text.
    `demo/Glossy-paper.icc` gives 1168 patches and a paper white of L* 93.8
    that way. A wrong shape that looks entirely reasonable is worse than a
    crash, and the docstring claimed a `KeyError` that no line could raise.

    This proves the refusal by ADDING a kind to the table, which is exactly
    how the hole would be opened for real: the next kind someone adds.
    """
    import pytest
    import shapes

    added = dict(file=True, depends=("white", "space"))
    shapes.KINDS["spectral"] = added          # a kind with no builder
    try:
        paper = tmp_path / "looks-like-anything.icc"
        paper.write_bytes((HERE / "demo/Glossy-paper.icc").read_bytes())
        thing = shapes.Thing("spectral", paper)
        with pytest.raises(shapes.CannotBuild) as refused:
            shapes.shape_for(thing, shapes.Settings())
        assert "spectral" in str(refused.value)
    finally:
        del shapes.KINDS["spectral"]

    # AND THE FILE IT WAS HANDED REALLY WOULD HAVE READ AS A PAPER, so the
    # test above is not refusing something that would have failed anyway.
    from ti3gamut import read_measurement
    read_as_paper = read_measurement(HERE / "demo/Glossy-paper.icc", "D50",
                                     False)
    assert len(read_as_paper.lab) > 1000, (
        "the ICC no longer reads as a measurement, so this test is now "
        "proving less than it says it does")


# ⚠ NOT MARKED `slow`, ON PURPOSE. This is the ONLY test `shape_for` has —
# the file's other tests all go through the hand-written twin — so a marker
# that lets it be filtered out is a marker that will one day filter out the
# only thing watching the door. It costs about ten seconds.
def test_the_one_door_agrees_with_the_builders_it_replaced(tmp_path):
    """⚠ `shape_for` HAD NO TEST AT ALL. It could be made to `raise` on every
    call and this whole file still passed, because every test here went
    through `build()` above — a hand-written twin of the same six branches.

    Deleting that twin and pointing the tests at `shape_for`, which is the
    obvious repair, would be the wrong one: the twin is the INDEPENDENT
    ORACLE. The dependency table is proved by building against the real
    builders, and if the table were proved against `shape_for` instead, a
    door with a bug in it would simply agree with itself.

    So the twin stays and the door answers to it. Every kind, in two spaces
    and under both ticks: the same vertices, or this fails. Drift between
    them — the thing that made the twin a liability — now cannot be silent
    in either direction.
    """
    seen = set()
    for thing, said in things(tmp_path):
        for space in ("lab", "luv"):
            for tick in (False, True):
                settings = shapes.Settings(space=space, tick=tick, detail=9)
                theirs = build(thing, settings)
                made = shapes.shape_for(thing, settings)
                mine = made.gamut
                seen.add(thing.kind)
                a = np.asarray(theirs.vertices, float)
                b = np.asarray(mine.vertices, float)
                assert a.shape == b.shape, (
                    f"the door and the builders disagree in SIZE for "
                    f"{said} in {space}, tick={tick}: {a.shape} vs {b.shape}")
                assert np.allclose(a, b, atol=1e-9), (
                    f"the door and the builders disagree for {said} in "
                    f"{space}, tick={tick}")
                assert mine.space == space, (
                    f"{said} came back in {mine.space!r}, not {space!r}")

                # ⚠ AND WHAT IT WAS BUILT FROM AND UNDER, which is the whole
                # reason `Built` replaced a pair. A test that only checked
                # the vertices would pass a door that handed back the right
                # shape labelled with the wrong settings — and a shape
                # carrying the wrong settings is precisely what the
                # coherence check reads to decide whether the window agrees
                # with its own controls.
                assert made.thing is thing, (
                    f"{said}: the shape came back describing something else")
                assert made.settings == settings, (
                    f"{said}: built under {made.settings}, asked for "
                    f"{settings}")

                # A measurement, and ONLY a measurement, carries one.
                assert (made.measurement is not None) == (
                    thing.kind == "measurement"), (
                    f"{said}: measurement={made.measurement is not None} for "
                    f"a {thing.kind}")

                # ⚠ AND A PICTURE, AND ONLY A PICTURE, CARRIES ITS FACTS.
                # These used to be discarded by the door on purpose, because
                # the pair's second slot already meant "the measurement" —
                # and that discard is what blocked `_build_one`'s picture
                # branch from being routed here at all. Routing it while the
                # facts had nowhere to go would have silently dropped the
                # colour count from the slot label and the picture-loss
                # figure from the panel, with the whole suite green. This is
                # the assertion that makes that impossible.
                assert (made.facts is not None) == (thing.kind == "picture"), (
                    f"{said}: facts={made.facts is not None} for a "
                    f"{thing.kind}")
    assert seen == set(shapes.KINDS), (
        f"kinds never put through the door: {set(shapes.KINDS) - seen} — a "
        f"branch nothing builds is a branch nothing checks")


def test_a_refusal_does_not_come_back_as_the_shape_on_screen(tmp_path):
    """⚠ THE REFUSAL WAS ONE `except` SHORT OF BEING A REFUSAL.

    `shape_for` raises `CannotBuild` for a kind with no builder, so it is
    refused rather than read as a measured paper. But `_in_lab` and
    `_reference_in_lab` both end in

        except Exception:      # never take the view down
            return gamut

    and `gamut` there is THE SHAPE AS DRAWN — in whatever space the window
    happens to be showing. So the refusal was caught and converted into
    exactly the fault shapes.py's own header describes: a chart counted
    against a gamut in the wrong space, "0 inside, 0 on the edge, 480
    outside, worst 99.0 ΔE" against a truth of 390. One wrong shape traded
    for another, quietly.

    The narrow clause comes first now. This test proves the ORDER, which is
    the whole of the fix: a `CannotBuild` must reach `None`, and everything
    else must still hand back the drawn shape so the view survives.
    """
    import gamut_app
    from types import SimpleNamespace as NS

    drawn = NS(space="luv", vertices=[[0.0, 0.0, 0.0]])

    def hall(raising):
        return NS(_white=NS(currentData=lambda: "D50"),
                  _mode=NS(currentData=lambda: "device"),
                  _relative=NS(isChecked=lambda: False),
                  _detail=NS(value=lambda: 9),
                  _space=NS(currentData=lambda: "luv"),
                  _build_space=lambda: "luv",
                  _settings=gamut_app.GamutApp._settings.__get__(
                      raising, gamut_app.GamutApp),
                  _lab_gamuts={},
                  _shape_key=lambda path, space, **kw: (str(path), space))

    for raised, expected, why in (
            (shapes.CannotBuild("no builder"), None,
             "a refusal came back as the shape on screen"),
            (ValueError("this file is not readable"), drawn,
             "an ordinary read error took the view down")):
        me = hall(None)
        me._settings = lambda: shapes.Settings(space="luv")

        def refuse(*a, **k):
            raise raised
        old = shapes.shape_for
        shapes.shape_for = refuse
        try:
            got = gamut_app.GamutApp._in_lab(
                me, drawn, tmp_path / "anything.icc", None)
        finally:
            shapes.shape_for = old
        assert got is expected, why


def test_the_rule_is_never_written_out_a_second_time(tmp_path):
    """⚠ FOUR COPIES OF "IS THIS A MEASUREMENT?" AND THEY DID DISAGREE.

    `_judging_shapes` decided it from the suffix — "not a profile, not a
    .gam, not an image, so measured" — which is the same reasoning that once
    labelled every photograph "(measured)" and fired the paper-white caution
    about a file that has no paper.

    It agreed with `Thing.measured` on every suffix the chooser offers, and
    disagreed on one case that reaches the application: a file with NO
    extension. `thing_for` calls it a measurement, which is what `_build_one`
    then reads it as — so a no-extension .ti3 that opened perfectly well was
    marked "not measured", and the caution that belongs to a measured paper
    was withheld from it.

    This is the test for the rule itself, so the two answers cannot drift
    apart again in silence.
    """
    import pathlib
    import gamut_app

    def by_suffix(p):
        """The rule as `_judging_shapes` used to write it."""
        s = pathlib.Path(p).suffix.lower()
        return (s != "" and s not in (".icc", ".icm", ".gam")
                and s not in gamut_app.IMAGE_EXTENSIONS)

    disagreed = []
    for name in ("a.ti3", "a.icc", "a.icm", "a.gam", "a.png", "a.jpg",
                 "a.tif", "a.cxf", "a.txt", "no-extension-at-all"):
        thing = shapes.thing_for(pathlib.Path(name), gamut_app.IMAGE_EXTENSIONS)
        if thing.measured != by_suffix(name):
            disagreed.append((name, thing.measured, by_suffix(name)))
    assert disagreed == [("no-extension-at-all", True, False)], (
        f"the two rules now differ somewhere new: {disagreed}")
    # AND THE TABLE IS THE ONE THAT IS RIGHT THERE: an extensionless file is
    # built by `read_measurement`, so if it opened at all it IS a measurement.
    assert shapes.thing_for(pathlib.Path("no-extension-at-all"),
                            gamut_app.IMAGE_EXTENSIONS).kind == "measurement"


BUILDERS = ("read_measurement", "icc_gamut", "gam_gamut", "image_gamut",
            "reference_gamut", "optimal_colour_solid")


def test_the_window_does_not_build_a_shape_behind_the_door():
    """⚠ THE WHOLE POINT, STATED AS A RULE THAT CAN FAIL.

    Twelve places in `gamut_app.py` turned a thing into a gamut, and each read
    a different subset of the five settings that decide what a shape IS. Every
    blocker of 30-31 August was two of those places disagreeing: the tick
    honoured by one and not another, a measurement dropped on the way to a
    third, a colour space having no file so a fourth crashed on `Path(None)`.

    Not similar faults — the same fault, met twelve times. So the rule is not
    "the builders are called correctly", it is that **the window does not call
    them at all**: `shapes.shape_for` is the only caller, because it is the
    only thing that reads `shapes.KINDS`.

    ⚠ AND THE GREP THAT FINDS THEM MUST FOLLOW ALIASES. Two of the twelve
    called their builder through a local variable —

        reader = gam_gamut if thing.kind == "gamutfile" else icc_gamut

    — so a search for `icc_gamut(` walked straight past both. This walks the
    syntax tree for the NAME, however it is spelled, which catches the call,
    the alias and the argument alike.

    `_in_lab`'s measurement-in-hand branch is the one exception and it is
    listed by name below: it must NOT re-read the file, because the
    measurement it already holds embodies a paper-white tick that re-reading
    would silently change. It wants a rebuild, not a build.
    """
    import ast
    import pathlib

    #: ⚠ (METHOD, BUILDER), NOT A METHOD. This was `ALLOWED = {"_in_lab"}`,
    #: which exempted EVERY branch of that method for EVERY builder. A hunt
    #: injected `icc_gamut(path, ...)` into `_in_lab`'s early-return branch —
    #: nothing to do with a measurement in hand — and this rule stayed green.
    #:
    #: `_in_lab` may use `build_gamut` and nothing else, because the
    #: measurement it holds already embodies a paper-white tick and re-reading
    #: the file would silently change it. It wants a rebuild, not a build.
    ALLOWED = {("_in_lab", "build_gamut")}

    src = (pathlib.Path(__file__).resolve().parent / "gamut_app.py").read_text()
    tree = ast.parse(src)

    #: function name -> the builder names it mentions
    guilty = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        used = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and inner.id in BUILDERS:
                used.add(inner.id)
            elif isinstance(inner, ast.Attribute) and inner.attr in BUILDERS:
                used.add(inner.attr)
        stray = {b for b in used if (node.name, b) not in ALLOWED}
        if stray:
            guilty[node.name] = sorted(stray)

    assert not guilty, (
        "the window builds a shape without going through `shapes.shape_for`, "
        "so a setting can reach one shape and miss another:\n  "
        + "\n  ".join(f"{k}: {v}" for k, v in sorted(guilty.items())))


def test_that_rule_can_actually_fail():
    """The control for the rule above — ON THE REAL FILE.

    ⚠ THIS USED TO PARSE A NINE-LINE STRING WRITTEN INSIDE THE TEST, which
    proves the FINDER works on a toy and says nothing about whether the RULE
    guards `gamut_app.py`. That is the same shape as two other instruments
    found blind today: it exercised its mechanism and not its subject.

    So the injection goes into a copy of the real source, through the same
    walk the rule uses, and BOTH halves are checked: a stray builder in an
    ordinary method, reached through an alias; and a stray builder inside the
    EXEMPT method — which is the half that was open, because the exemption
    used to cover the whole of `_in_lab` rather than its one builder.
    """
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parent / "gamut_app.py").read_text()

    def offenders(text):
        tree = ast.parse(text)
        found = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            used = set()
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name) and inner.id in BUILDERS:
                    used.add(inner.id)
                elif isinstance(inner, ast.Attribute) and inner.attr in BUILDERS:
                    used.add(inner.attr)
            stray = {b for b in used
                     if (node.name, b) not in {("_in_lab", "build_gamut")}}
            if stray:
                found[node.name] = sorted(stray)
        return found

    assert offenders(src) == {}, (
        "the real file already breaks the rule: " + repr(offenders(src)))

    # (1) an ordinary method that builds for itself, through an ALIAS — the
    # form a name-based grep walks straight past, and how two of the twelve
    # original sites hid.
    anchor = "    def _refresh_slot_labels(self) -> None:"
    assert src.count(anchor) == 1, (
        "the anchor for injection (1) is gone; this control is testing "
        "nothing")
    aliased = src.replace(
        anchor,
        anchor + "\n        reader = gam_gamut if True else icc_gamut"
                 "\n        reader(None)", 1)
    assert offenders(aliased).get("_refresh_slot_labels") == [
        "gam_gamut", "icc_gamut"], (
        "a builder reached through an alias is not caught: "
        + repr(offenders(aliased).get("_refresh_slot_labels")))

    # (2) THE HALF THAT WAS OPEN: a builder that is NOT `build_gamut`, inside
    # the one method the rule exempts.
    where = "    def _in_lab(self"
    assert src.count(where) == 1, (
        "the anchor for injection (2) is gone; this control is testing "
        "nothing")
    at = src.index(where)
    end = src.index("\n", at)
    in_the_exempt_one = src[:end + 1] + "        icc_gamut(None)\n" + src[end + 1:]
    assert offenders(in_the_exempt_one).get("_in_lab") == ["icc_gamut"], (
        "the exemption still covers the whole method, so a builder with "
        "nothing to do with a measurement in hand passes unnoticed: "
        + repr(offenders(in_the_exempt_one).get("_in_lab")))

    # (3) AND THE ONE THING THAT MUST STILL BE ALLOWED, or the rule has been
    # tightened into a lie about why the exception exists.
    assert offenders(src).get("_in_lab") is None, (
        "`_in_lab` may use `build_gamut`: the measurement it holds already "
        "embodies a tick, so it must rebuild rather than re-read")


# --------------------------------------------------------------------------
# The one conditional dependency, and the measurement it rests on
# --------------------------------------------------------------------------

def test_white_stays_in_the_key_for_every_kind_that_declares_it():
    """⚠ IT WAS DROPPED FOR A PROFILE IN CIELAB, AND THAT PAINTED A RUN IN
    THE WRONG COLOURS.

    The argument was good and the measurement was of the wrong quantity. A
    profile's Lab VERTICES are white-independent — the connection space is
    D50-referred — so `_shells_for`, which pins CIELAB, was rebuilding an
    ArgyllCMS shell on every nudge of the white point to get identical
    geometry. Dropping `white` from the key there saved about 1.5 s a nudge.

    But a `Gamut` is not only vertices. `icc_gamut` and `gam_gamut` also
    compute a screen colour per vertex, and they do it by going back OUT of
    Lab — `xyz_to_srgb(lab_to_xyz(verts, W), W)` — and Bradford adaptation is
    a diagonal scaling in LMS, so that composition is not white-invariant:

        vertices IDENTICAL   faces IDENTICAL   volume IDENTICAL
        colors   DIFFERS     2233 of 2233, worst 70 of 255 in a channel

    Driven, with the key blind to white: a run on screen kept its two shells
    painted in D50 colours while the control read D65, and the builder never
    ran. 1922 of 2233 painted vertices were wrong.
    """
    import pathlib
    prof = shapes.thing_for(pathlib.Path("/x/p.icc"), (".png",))
    gam = shapes.thing_for(pathlib.Path("/x/p.gam"), (".png",))
    meas = shapes.thing_for(pathlib.Path("/x/p.ti3"), (".png",))

    for thing, said in ((prof, "a profile"), (gam, "a gamut file"),
                        (meas, "a measurement")):
        for space in ("lab", "luv", "xyz"):
            a = shapes.key_for(thing, shapes.Settings(white="D50", space=space))
            b = shapes.key_for(thing, shapes.Settings(white="D65", space=space))
            assert a != b, (
                f"{said} in {space} does not key on the white point — two "
                "shapes that are painted differently would share one entry")


def test_the_declaration_is_the_whole_answer():
    """`depends_on` reads the table and nothing else — no conditions."""
    import inspect
    import pathlib
    prof = shapes.thing_for(pathlib.Path("/x/p.icc"), (".png",))
    assert shapes.depends_on(prof) == ("white", "space")

    # ⚠ AND IT TAKES NO SETTINGS. A signature that accepts them is a place to
    # put a condition, and the last condition put there was measured on the
    # wrong field and painted a run in the wrong colours.
    params = inspect.signature(shapes.depends_on).parameters
    assert list(params) == ["thing"], (
        f"`depends_on` takes {list(params)} — anything beyond the thing is "
        "somewhere for a conditional dependency to hide")


@pytest.mark.slow
def test_a_profile_in_cielab_moves_with_the_white_point(tmp_path):
    """⚠ THE MEASUREMENT THAT WAS TAKEN OF THE WRONG FIELD.

    Its predecessor built each profile under both whites and compared
    `vertices`. They are identical, so it passed — and certified an
    assumption it did not test, because `colors` differs on every vertex and
    `colors` is what paints the shape.

    Every field is compared here. The point is no longer "white is inert" —
    it is that white REACHES a profile in CIELAB, so the key must carry it.
    """
    import pathlib
    import numpy as np
    from references import icc_gamut

    here = pathlib.Path(__file__).resolve().parent.parent / "demo"
    profiles = sorted(here.rglob("*.icc"))
    assert len(profiles) >= 3, (
        f"only {len(profiles)} profiles — this test is watching almost nothing")

    moved = []
    for p in profiles:
        a = icc_gamut(p, white_point="D50", space="lab")
        b = icc_gamut(p, white_point="D65", space="lab")
        same_verts = np.array_equal(np.asarray(a.vertices, float),
                                    np.asarray(b.vertices, float))
        ca, cb = getattr(a, "colors", None), getattr(b, "colors", None)
        assert ca is not None and cb is not None, (
            f"{p.name}: a Gamut no longer carries `colors`, so this test and "
            "the key rule it supports are both about a field that is gone")
        same_colors = np.array_equal(np.asarray(ca, float),
                                     np.asarray(cb, float))
        moved.append((p.name, same_verts, same_colors))

    # The geometry really is white-independent — that half of the old claim
    # was true, and is why the mistake was tempting.
    assert all(v for _n, v, _c in moved), (
        f"a profile's CIELAB vertices moved with the white point: {moved}")
    # And the painted colours really are not.
    assert not any(c for _n, _v, c in moved), (
        "a profile's colours no longer move with the white point — if that is "
        f"deliberate, the key may drop `white` again: {moved}")


def test_the_door_says_what_it_actually_returns():
    """⚠ A FALSE DOCSTRING HERE BLINDED AN INSTRUMENT, so this is not prose.

    `shape_for` went on saying "Returns `(gamut, measurement)`" for a day
    after it began returning a `Built`. The coherence driver this work leans
    on was written against that sentence — it unwrapped the door with
    `got[0] if isinstance(got, tuple) else got`, which tags the WRAPPER once
    a dataclass comes back instead of a pair. Every shape then came back
    untagged and the run reported `0 incoherences`: a green that meant
    nothing had been checked.

    So the door's own account of its return is checked against the return.
    """
    import inspect
    said = inspect.getdoc(shapes.shape_for) or ""
    first = said.split("\n\n")[0] + "\n\n" + (
        said.split("\n\n")[1] if said.count("\n\n") else "")

    assert "Built" in first, (
        "the door does not say it returns a `Built` in the first thing a "
        f"reader is told: {first[:120]!r}")
    # ⚠ NOT "the string appears nowhere" — the paragraph above quotes the
    # old sentence to say what went wrong with it, and a rule that forbids
    # naming a retired promise forbids explaining it. What must not exist is
    # a line that PROMISES the pair.
    promised = [line.strip() for line in said.splitlines()
                if line.strip().startswith("Returns")
                and "(gamut, measurement)" in line]
    assert not promised, (
        f"the door still promises the pair it stopped returning: {promised}")

    # AND THE PROMISE IS KEPT: what it says is what comes back.
    import pathlib
    thing = shapes.a_space("sRGB")
    made = shapes.shape_for(thing, shapes.Settings(space="lab", detail=6))
    assert isinstance(made, shapes.Built), type(made)
    for field in ("gamut", "thing", "settings", "measurement", "facts"):
        assert hasattr(made, field), f"a Built has no {field}"
    assert not isinstance(made, tuple), (
        "a Built that is also a tuple would let the old unwrapping keep "
        "working, and the next instrument would inherit the same blindness")
