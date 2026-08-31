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


def things():
    out = [(shapes.Thing("measurement", DEMO / "Glossy-paper.ti3"), "a paper"),
           (shapes.Thing("profile", DEMO / "Glossy-paper.icc"), "a profile"),
           (shapes.a_space("sRGB"), "a colour space")]
    picture = a_picture()
    if picture is not None:
        out.append((shapes.Thing("picture", picture), "a photograph"))
    return out


@pytest.mark.slow
def test_nothing_the_table_denies_can_move_the_shape():
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
    checked = 0
    for thing, said in things():
        declared = set(shapes.depends_on(thing))
        for setting, (first, second) in OTHER.items():
            if setting in declared:
                continue
            base = shapes.Settings(detail=9)
            from dataclasses import replace as _replace
            a = _replace(base, **{setting: first})
            b = _replace(base, **{setting: second})
            checked += 1
            assert not moved(thing, a, b), (
                f"{said}: the table says {setting!r} does not reach it, and "
                "changing it MOVED THE SHAPE — every cache keyed by this "
                "rule would hand back a stale answer")
    assert checked >= 6, f"only {checked} denials were tried"


@pytest.mark.slow
def test_what_the_table_claims_is_measured_and_recorded():
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
    for thing, said in things():
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


def test_the_key_carries_the_file_s_timestamp_and_only_what_matters():
    s = shapes.Settings()
    paper = shapes.Thing("measurement", DEMO / "Glossy-paper.ti3")
    stamp = (DEMO / "Glossy-paper.ti3").stat().st_mtime_ns
    assert stamp in shapes.key_for(paper, s)
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
