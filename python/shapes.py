"""One place that says what a thing IS and what its shape depends on.

⚠ WHY THIS MODULE EXISTS, in one sentence: between 30 and 31 August 2026 this
application put six wrong numbers on screen, and every one of them was two
shapes built under two different readings of the same five controls.

    "0 inside, 0 on the edge, 480 outside. Worst 99.0 ΔE"   (the truth: 390)
    a room marking 480 of 480 while the sentence beside it said 143
    coverage moving 66.9% -> 82.9% on a nudge of an unrelated control
    a photograph 0% / 1% / 100% out of reach with only the drawing changed
    CIELUV on screen under a control reading CIE XYZ
    a crash on an ordinary change of "Draw it in"

Eight methods turned a thing into a shape, and each consulted a different
subset of the five settings. Sixteen build sites, four caches, four different
ideas of what changes a shape. Each fault was fixed where it was found, and
the branch nobody was looking at stayed wrong -- four times in a row.

NOTHING IMPORTS THIS YET. It is written first, and proved, and only then are
the callers moved onto it one at a time.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Thing:
    """Something a shape can be made of, named by KIND rather than by suffix.

    ⚠ ONE PLACE DECIDES WHAT A FILE IS. `_build_one` and `_in_lab` each had
    their own answer and they disagreed about a photograph: `_in_lab` read
    every path that was not a `.gam` as an ICC profile, so a picture held as
    the comparison was judged against a shape in the wrong space.
    """
    kind: str
    path: pathlib.Path | None = None
    name: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"no such kind: {self.kind!r}")
        wants_file = KINDS[self.kind]["file"]
        if wants_file and self.path is None:
            raise ValueError(f"a {self.kind} needs a file")
        if not wants_file and self.path is not None:
            raise ValueError(f"a {self.kind} has no file")

    @property
    def measured(self) -> bool:
        """Was this PRINTED AND READ BY AN INSTRUMENT.

        A picture is a file and is NOT measured. Deciding that from the
        suffix instead — "not a profile, so it must be measured" — is what
        labelled every photograph "(measured)" and fired the paper-white
        caution about a photograph that has no paper.

        `_both_whites` asks this before offering two readings of one white,
        because a paper's own white is a thing only a measurement has.
        """
        return self.kind == "measurement"


#: ⚠ WHAT EACH KIND ACTUALLY DEPENDS ON. Not "everything that could matter" —
#: that guess is what put Detail into three cache keys and made every nudge of
#: it a guaranteed miss returning a bit-identical answer, at 3.67 s a time.
#: `detail` reaches `reference_gamut(steps=)` and `optimal_colour_solid()` and
#: nothing else, so it belongs to the two SYNTHETIC kinds and nowhere else.
#: The paper-white tick and the shape mode reach a measurement and nothing
#: else. This table is proved against the real builders in test_shapes.py by
#: BUILDING, not by being read back.
KINDS = {
    "measurement": dict(file=True, depends=("white", "space", "mode", "tick")),
    "profile":     dict(file=True, depends=("white", "space")),
    "gamutfile":   dict(file=True, depends=("white", "space")),
    "picture":     dict(file=True, depends=("white", "space")),
    "space":       dict(file=False, depends=("white", "space", "detail")),
    "visible":     dict(file=False, depends=("white", "space", "detail")),
}

PROFILE_SUFFIXES = (".icc", ".icm")


def thing_for(path, image_suffixes) -> Thing:
    """Classify a file. The suffix test lives here and nowhere else."""
    path = pathlib.Path(path)
    suffix = path.suffix.lower()
    if suffix in PROFILE_SUFFIXES:
        return Thing("profile", path)
    if suffix == ".gam":
        return Thing("gamutfile", path)
    if suffix in image_suffixes:
        return Thing("picture", path)
    return Thing("measurement", path)


def a_space(name: str) -> Thing:
    return Thing("space", None, name)


def the_visible_solid() -> Thing:
    return Thing("visible", None, "Every visible colour")


@dataclass(frozen=True)
class Settings:
    """The five controls that decide what a shape IS, frozen together.

    ⚠ FROZEN AND PASSED, NOT READ FROM A WIDGET INSIDE A BUILDER. A snapshot
    can be compared for equality; eight methods each reaching into
    `self._white.currentData()` at a moment of their own choosing cannot, and
    that is precisely how one shape came to be built under the tick and
    another without it, on the same screen, at the same moment.
    """
    white: str = "D50"
    space: str = "lab"
    mode: str = "device"
    tick: bool = False
    detail: int = 20

    def drawn_in(self, space: str) -> "Settings":
        return replace(self, space=space)

    def with_tick(self, tick: bool) -> "Settings":
        return replace(self, tick=tick)


#: Kinds whose builder produces a CIELAB shape from a D50-referred source,
#: so the white point asked for cannot move it — but only while the shape is
#: being BUILT in CIELAB.
_PCS_IS_D50 = ("profile", "gamutfile")


def depends_on(thing: Thing, settings: "Settings | None" = None) -> tuple:
    """Which of the five settings decide this shape.

    ⚠ ONE OF THEM IS CONDITIONAL, AND MEASURED. `KINDS["profile"]` declares
    `("white", "space")` and is right to: a profile drawn in CIELUV or CIE
    XYZ DOES move with the white point, and under-declaring is the dangerous
    direction. But an ICC profile's connection space is D50-referred, so the
    CIELAB shape it yields is the same whatever white is asked for — and the
    conversion that makes white matter happens on the way OUT of Lab.

    So when the space is pinned to `"lab"`, `white` cannot change the answer
    for these kinds, and carrying it in the key is a guaranteed miss. With a
    run on screen that cost about 1.5 s of blocked main thread per nudge of
    the white point, rebuilding two ArgyllCMS shells to redraw a picture that
    did not change by one vertex — and `_shells_for`'s own docstring says
    building one is "the slowest thing this application does".

    MEASURED, not reasoned: every profile in this repository (four distinct
    shapes) and a `.gam` produced by ArgyllCMS's own `iccgamut`, under D50
    and D65 —

        lab   bit-identical vertices, all five files and the .gam
        luv   differs on every one   (1,124,157 vs 1,277,757 for one)
        xyz   differs on every one   (0.1263 vs 0.1643 for one)

    `test_white_really_is_inert_for_a_profile_in_cielab` builds both whites
    through the real builders and asserts that, so the day the assumption
    stops holding the suite says so — rather than a cache quietly serving a
    shape built under the wrong white, which is the direction that shows a
    reader a wrong number instead of costing a second.

    Called with no settings it answers the static declaration, which is what
    an audit of the table wants.
    """
    declared = KINDS[thing.kind]["depends"]
    if (settings is not None and thing.kind in _PCS_IS_D50
            and settings.space == "lab"):
        return tuple(name for name in declared if name != "white")
    return declared


def key_for(thing: Thing, settings: Settings) -> tuple:
    """What decides this shape, and nothing else — the one cache key.

    ⚠ THE FILE'S TIMESTAMP IS NOT IN IT, AND IT WAS. That looked obviously
    right — a cache keyed by path alone answers for the shape a file USED to
    have — and it made the window contradict itself instead.

    A reader's key is built from the file on disk NOW. The shape being DRAWN
    was built when the file was opened. Edit the file in place while it is
    open — a save from an editor, a sync, a restore from backup — and the key
    moves, so every number is recomputed from the new content while the
    picture on screen is still the old one. Driven, a photograph re-saved
    with far smaller colours, nothing reopened:

        the shape being drawn      volume 212,188
        the shape being judged     volume 0

    Nothing tells the reader which of those the percentages describe. The
    same mismatch, in the picture-facts cache, turned "holds" into "can
    print" about a photograph earlier the same day.

    So the window answers for the file you OPENED, and the rebuild happens on
    the gesture that asks for the file again — which is where `_load` already
    empties three caches, and where `_on_compare_changed` now empties the
    comparison's. A timestamp cannot be forgotten, but it also cannot be
    told the difference between "this file changed" and "you asked for it
    again", and only the second should move what is on screen.
    """
    parts: list = [thing.kind, str(thing.path) if thing.path else thing.name]
    for setting in depends_on(thing, settings):
        parts.append(getattr(settings, setting))
    return tuple(parts)


@dataclass(frozen=True)
class Built:
    """One shape, and everything that was true when it was made.

    ⚠ A PAIR COULD NOT SAY THIS. `shape_for` returned `(gamut, measurement)`,
    and three of its five call sites threw the second value away on the spot
    (`built, _m = ...`). A return whose second half is discarded at half its
    call sites is not describing the thing it returns — and `test_shapes`
    had to assert "the second value means 'the measurement' and nothing
    else", a test that exists only because the pair is ambiguous.

    ⚠ AND THE PICTURE'S FACTS HAD NOWHERE TO GO. `image_gamut` returns
    `(gamut, facts)`; the door discarded the facts deliberately, saying so,
    because the second slot already meant "the measurement". That deferral
    became a blocker: routing `_build_one`'s picture branch through the door
    while the facts had no home would have silently deleted the colour count
    from the slot label and the picture-loss figure from the panel, with the
    whole suite green. Named fields make that impossible to do by accident.

    ⚠ AND `settings` IS THE POINT, not bookkeeping. A shape that carries what
    it was built under can be checked against the controls that are live now
    — which is the whole of the coherence property every one of this
    release's thirteen faults violated. Without it that check has to be
    bolted on from outside by wrapping every builder; with it, the window can
    make the assertion about itself.
    """

    gamut: object
    thing: Thing
    settings: Settings
    measurement: object = None
    facts: object = None


class CannotBuild(ValueError):
    """This thing cannot be turned into a shape, and the reason is in words.

    ⚠ RAISED RATHER THAN FALLEN BACK FROM. Every fallback in this
    application's history returned the shape it happened to have — the drawn
    one — and a caller then measured CIELAB patches against it. "0 inside, 0
    on the edge, 480 outside, worst 99.0 ΔE" was a fallback, not an error.
    """


def shape_for(thing: Thing, settings: Settings, *, stop=None):
    """The shape of *thing* under *settings*. The only place that builds.

    Returns a `Built`: the gamut, the thing it was made from, the settings it
    was made under, and — for the kinds that have them — the measurement and
    the picture's facts.

    ⚠ THIS DOCSTRING SAID "Returns `(gamut, measurement)`" FOR A WHOLE DAY
    AFTER IT STOPPED BEING TRUE, and that is not a cosmetic slip. The
    coherence driver this work leans on was written against this sentence:
    it unwrapped the door with `got[0] if isinstance(got, tuple) else got`,
    which tags the WRAPPER once a `Built` comes back instead of a pair. Every
    shape then came back untagged and the run reported `0 incoherences` — a
    green that meant nothing had been checked. An instrument was written
    against this line, and this line was wrong.

    ⚠ EVERY KIND IS NAMED, AND AN UNNAMED ONE RAISES. `_in_lab` knew about
    profiles and gamut files and fell through to "read it as an ICC" for
    everything else, so a photograph raised and the DRAWN shape came back.

    This method had the same shape of hole until 1 September, and the
    docstring here claimed the opposite — that a kind with no branch was "a
    KeyError at once". It was not: `measurement` was the fall-through, so a
    kind nobody had written a branch for would have been READ AS A MEASURED
    PAPER. That is not a crash but a plausible wrong answer, because
    `read_measurement` SUCCEEDS on an ArgyllCMS ICC profile — the CTI3 target
    is embedded in it as text, and `demo/Glossy-paper.icc` yields 1168
    patches and a paper white of L* 93.8.

    So `measurement` is a branch like the others now, and the end of the
    method raises `CannotBuild`, which was defined here and never raised.
    """
    from gamutview import build_gamut, xyz_to_lab
    from references import gam_gamut, icc_gamut, reference_gamut
    from ti3gamut import read_measurement

    white, space = settings.white, settings.space
    if thing.kind == "profile":
        return Built(icc_gamut(thing.path, white_point=white, space=space,
                              stop=stop), thing, settings)
    if thing.kind == "gamutfile":
        return Built(gam_gamut(thing.path, white_point=white, space=space,
                              stop=stop), thing, settings)
    if thing.kind == "picture":
        from imagegamut import image_gamut
        # ⚠ THE FACTS COME BACK NOW, in a field of their own. They used to
        # be dropped here because the second slot of the pair already meant
        # "the measurement" — and that deferral was what blocked routing
        # `_build_one`'s picture branch through this door at all.
        built, facts = image_gamut(thing.path, white_point=white,
                                   space=space)
        return Built(built, thing, settings, facts=facts)
    if thing.kind == "space":
        return Built(reference_gamut(thing.name, white_point=white,
                                    steps=settings.detail, space=space),
                     thing, settings)
    if thing.kind == "visible":
        from spectral import optimal_colour_solid
        verts, _faces = optimal_colour_solid(
            "D50" if white == "D50" else "D65", max(24, settings.detail * 3))
        return Built(build_gamut(xyz_to_lab(verts, white),
                                input_space="lab", space=space,
                                white_point=white), thing, settings)
    if thing.kind == "measurement":
        m = read_measurement(thing.path, white, settings.tick)
        drive = None if settings.mode == "hull" else m.device
        return Built(build_gamut(m.lab, drive, input_space="lab",
                                space=space, white_point=white),
                     thing, settings, measurement=m)
    raise CannotBuild(
        f"there is no builder for a {thing.kind!r}, so this shape cannot be "
        f"made — which is said here rather than guessed at, because the "
        f"fall-through this replaces would have read it as a measured paper")
