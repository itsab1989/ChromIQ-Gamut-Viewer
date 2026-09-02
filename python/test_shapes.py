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

    #: The one branch that is allowed to build for itself, and why.
    ALLOWED = {"_in_lab"}

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
        if used and node.name not in ALLOWED:
            guilty[node.name] = sorted(used)

    assert not guilty, (
        "the window builds a shape without going through `shapes.shape_for`, "
        "so a setting can reach one shape and miss another:\n  "
        + "\n  ".join(f"{k}: {v}" for k, v in sorted(guilty.items())))


def test_that_rule_can_actually_fail():
    """The control for the rule above, on a function written here.

    A rule that has never been seen to fail is a rule nobody has checked.
    """
    import ast

    sneaky = '''
def _a_route_that_builds_for_itself(self):
    reader = gam_gamut if self.kind == "gamutfile" else icc_gamut
    return reader(self.path)
'''
    tree = ast.parse(sneaky)
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in BUILDERS:
            used.add(node.id)
    assert used == {"gam_gamut", "icc_gamut"}, (
        f"the finder misses a builder reached through an alias: {used}")


# --------------------------------------------------------------------------
# The one conditional dependency, and the measurement it rests on
# --------------------------------------------------------------------------

def test_white_leaves_the_key_only_where_it_cannot_move_the_shape():
    """⚠ A KEY THAT CARRIES A SETTING THE BUILD IGNORES IS A GUARANTEED MISS.

    `_shells_for` pins `space="lab"` on purpose — "ALWAYS IN LAB, WHATEVER
    THE WINDOW IS DRAWING IN" — and CIELAB is the one space where the white
    point cannot reach a profile. So with a run on screen, one nudge of the
    white point rebuilt BOTH ArgyllCMS shells, took about 1.5 s of blocked
    main thread, and returned shapes identical to four decimal places:

        ('profile', '.../printer-2019.icc', 'D50', 'lab')
        ('profile', '.../printer-2019.icc', 'D65', 'lab')   <- two keys,
        ('profile', '.../printer-2021.icc', 'D50', 'lab')      one shape
        ('profile', '.../printer-2021.icc', 'D65', 'lab')

    This is the same fault the commit before it removed from this very key
    one field along: `mode` was dropped because a profile does not depend on
    it, and nobody noticed that pinning the space does the same to `white`.

    ⚠ THE DECLARATION STAYS AS IT IS. `KINDS["profile"]` keeps `white`,
    because in CIELUV and CIE XYZ a profile really does move with it, and
    under-declaring is the direction that shows somebody a wrong number.
    Only the pinned-to-CIELAB case drops it.
    """
    import pathlib
    prof = shapes.thing_for(pathlib.Path("/x/p.icc"), (".png",))
    gam = shapes.thing_for(pathlib.Path("/x/p.gam"), (".png",))
    meas = shapes.thing_for(pathlib.Path("/x/p.ti3"), (".png",))

    for thing, said in ((prof, "a profile"), (gam, "a gamut file")):
        lab50 = shapes.key_for(thing, shapes.Settings(white="D50", space="lab"))
        lab65 = shapes.key_for(thing, shapes.Settings(white="D65", space="lab"))
        assert lab50 == lab65, (
            f"{said} in CIELAB still keys on the white point, so every nudge "
            "of it rebuilds an ArgyllCMS shell for an identical answer")

        luv50 = shapes.key_for(thing, shapes.Settings(white="D50", space="luv"))
        luv65 = shapes.key_for(thing, shapes.Settings(white="D65", space="luv"))
        assert luv50 != luv65, (
            f"{said} in CIELUV no longer keys on the white point — and there "
            "it genuinely moves the shape, so two different shapes would "
            "share one cache entry")
        assert lab50 != luv50, f"{said}: two spaces share a key"

    # A MEASUREMENT IS UNTOUCHED: its white is read from the file, not from
    # a D50 connection space, and it moves the shape in every space.
    m50 = shapes.key_for(meas, shapes.Settings(white="D50", space="lab"))
    m65 = shapes.key_for(meas, shapes.Settings(white="D65", space="lab"))
    assert m50 != m65, (
        "two readings of one paper share a cache entry — that is the fault "
        "that made coverage swing 66.9% to 82.9%")


def test_the_static_declaration_is_unchanged():
    """Asked with no settings, the table answers what it always did."""
    import pathlib
    prof = shapes.thing_for(pathlib.Path("/x/p.icc"), (".png",))
    assert shapes.depends_on(prof) == ("white", "space"), (
        "the declaration itself changed — under-declaring is the dangerous "
        "direction and this is what an audit of the table reads")


@pytest.mark.slow
def test_white_really_is_inert_for_a_profile_in_cielab(tmp_path):
    """⚠ THE MEASUREMENT THE KEY RULE RESTS ON, taken against the real
    builders rather than argued from the ICC specification.

    If this ever stops holding, the cache above starts serving a shape built
    under the wrong white — a wrong number rather than a slow one, which is
    the direction that matters. So it is checked by building, not by
    reasoning about connection spaces.
    """
    import pathlib
    import numpy as np
    from references import icc_gamut

    here = pathlib.Path(__file__).resolve().parent.parent / "demo"
    profiles = sorted(here.rglob("*.icc"))
    assert len(profiles) >= 3, (
        f"only {len(profiles)} profiles to check — this test is watching "
        "almost nothing")

    for p in profiles:
        d50 = np.asarray(icc_gamut(p, white_point="D50", space="lab").vertices,
                         float)
        d65 = np.asarray(icc_gamut(p, white_point="D65", space="lab").vertices,
                         float)
        assert d50.shape == d65.shape and np.array_equal(d50, d65), (
            f"{p.name}: the white point MOVES this profile in CIELAB, so "
            "dropping it from the cache key now serves the wrong shape")

    # AND THE CONTROL: white is not simply inert everywhere, or the rule
    # above would be hiding a builder that ignores its argument.
    one = profiles[0]
    a = np.asarray(icc_gamut(one, white_point="D50", space="luv").vertices,
                   float)
    b = np.asarray(icc_gamut(one, white_point="D65", space="luv").vertices,
                   float)
    assert not np.array_equal(a, b), (
        f"{one.name}: the white point does not move it in CIELUV either, so "
        "`icc_gamut` is ignoring the argument and this test proves nothing")
