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


def depends_on(thing: Thing) -> tuple:
    return KINDS[thing.kind]["depends"]


def key_for(thing: Thing, settings: Settings) -> tuple:
    """What decides this shape, and nothing else — the one cache key.

    ⚠ THE FILE'S OWN TIMESTAMP IS IN IT. A cache keyed by path alone answers
    for the shape a file USED to have, and the guard against that was
    "remember to clear the caches when a file is opened" — a rule already
    half-forgotten once, across four caches with four different key rules.

    ⚠ AND A FILE THAT CANNOT BE STATTED GETS A STABLE KEY, not an unrepeatable
    one. An earlier version of this comment claimed the opposite — "never
    answer from cache" — which was simply false, and a review showed it in one
    line. What is TRUE is narrower and worth stating exactly: the key of a
    missing file differs from the key that file had while it existed, so no
    cache can hand back its old shape; but two lookups of the SAME missing
    file agree, so if anything ever cached a result under it, that result
    would be returned. Nothing does today, because a build of a missing file
    raises before it can be stored.
    """
    parts: list = [thing.kind, str(thing.path) if thing.path else thing.name]
    if thing.path is not None:
        try:
            parts.append(thing.path.stat().st_mtime_ns)
        except OSError:          # gone, or unreadable — see the note above
            parts.append(None)
    for setting in depends_on(thing):
        parts.append(getattr(settings, setting))
    return tuple(parts)
