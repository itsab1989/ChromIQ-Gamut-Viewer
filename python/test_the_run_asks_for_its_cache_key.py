"""The run's shells are remembered by the rule that says what they depend on.

⚠ THE LAST HAND-WRITTEN CACHE KEY IN THE WINDOW, and it was wrong in BOTH
directions against `shapes.KINDS`:

    key = (str(path), host._white.currentData(), "lab",
           host._mode.currentData())

* It INCLUDED `mode`. A profile depends on `("white", "space")` and nothing
  else, so every nudge of "How the shape is worked out" was a guaranteed
  miss that rebuilt an ArgyllCMS shell to get a bit-identical answer —
  and `_shells_for`'s own docstring says building one is "the slowest thing
  this application does", on a method that runs on every drag of the
  threshold slider.
* It OMITTED `tick`. A measurement DOES depend on it, so two readings of one
  paper would have shared a key. Nothing reaches that today except through a
  pair of file filters in a DIFFERENT class — the guard style this work
  exists to replace, in `_build_one`'s own words.

`shapes.key_for` reads the dependencies from the one table, so the key cannot
disagree with what the builder actually used.
"""
import pathlib
import sys
import weakref as _weakref
from types import SimpleNamespace as NS

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

IMAGE = (".png", ".jpg", ".jpeg", ".tif", ".tiff")


def _host(mode="device", white="D50", tick=False, built=None):
    """A window stand-in carrying the REAL `_settings`, not a fake one.

    ⚠ BOUND, NOT IMITATED. A stand-in that returned its own idea of a
    `Settings` would let this pass over a `_settings()` that had stopped
    reading one of the five controls — which is the fault this whole line of
    work is about.
    """
    import gamut_app
    import shapes
    host = NS(_white=NS(currentData=lambda: white),
              _mode=NS(currentData=lambda: mode),
              _relative=NS(isChecked=lambda: tick),
              _detail=NS(value=lambda: 20),
              _space=NS(currentData=lambda: "lab"),
              _build_space=lambda: "lab")
    host._settings = gamut_app.GamutApp._settings.__get__(
        host, gamut_app.GamutApp)
    host._build_one = lambda path, space="lab", **kw: (
        built.append((str(path), space)) or (NS(space=space), None))
    return host


def _key(host, path):
    import shapes
    return shapes.key_for(shapes.thing_for(path, IMAGE),
                          host._settings().drawn_in("lab"))


def test_a_profile_is_not_rebuilt_when_the_mode_moves():
    """A profile does not depend on how a SHAPE is worked out."""
    p = pathlib.Path("/x/Glossy-paper.icc")
    assert _key(_host(mode="device"), p) == _key(_host(mode="hull"), p), (
        "the run rebuilds an ArgyllCMS shell when a setting it does not "
        "depend on moves")


def test_a_profile_is_rebuilt_when_the_white_moves():
    """...and it does depend on the white point, in every space.

    ⚠ THIS TEST WAS REWRITTEN TWICE IN ONE DAY, THE FIRST TIME WRONGLY. It
    was made to assert that a profile in CIELAB does NOT key on white,
    because its Lab vertices are white-independent. They are — and the
    per-vertex screen colours are not: `icc_gamut` computes them by going
    back out of Lab through a Bradford adaptation, which is not
    white-invariant. `colors` differed on 2233 of 2233 vertices while
    `vertices` was bit-identical, and a run on screen kept its shells painted
    in D50 while the control read D65.

    So the original claim was right and the clever narrowing was wrong. The
    lesson is in the shape of the mistake: the measurement compared the field
    that was easy to compare, and the shape has more than one field.
    """
    import shapes
    p = pathlib.Path("/x/Glossy-paper.icc")
    thing = shapes.thing_for(p, IMAGE)
    for space in ("lab", "luv", "xyz"):
        a = shapes.key_for(thing, shapes.Settings(white="D50", space=space))
        b = shapes.key_for(thing, shapes.Settings(white="D65", space=space))
        assert a != b, (
            f"a profile in {space} shares one cached shell across two white "
            "points, and the shape it paints differs between them")


def test_two_readings_of_one_paper_do_not_share_a_key():
    """A measurement DOES depend on the paper-white tick."""
    p = pathlib.Path("/x/Glossy-paper.ti3")
    assert _key(_host(tick=False), p) != _key(_host(tick=True), p), (
        "the same paper read two ways shares one cache entry, which is the "
        "fault that made coverage swing 66.9% to 82.9%")


def test_the_key_carries_the_kind():
    """Two files with one stem, one a profile and one a measurement — this
    project's own demo set has exactly that pair in one folder."""
    import shapes
    host = _host()
    prof = _key(host, pathlib.Path("/x/Glossy-paper.icc"))
    meas = _key(host, pathlib.Path("/x/Glossy-paper.ti3"))
    assert prof != meas, "a profile and a measurement share a cache entry"
    assert prof[0] == "profile" and meas[0] == "measurement", (prof, meas)


def test_the_run_does_not_write_its_own_key():
    """⚠ THE RULE, NOT THE ONE KEY THAT WAS WRONG.

    `_shells_for` must ask `key_for` rather than assemble a tuple of its own.
    A key built by hand is a second copy of the dependency table, and this
    one disagreed with it in both directions for months.
    """
    import ast
    import inspect
    import gamut_app

    src = inspect.getsource(gamut_app.TimelineDialog._shells_for)
    tree = ast.parse(src.strip())
    asks = [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "key_for"]
    assert asks, "_shells_for no longer asks `key_for` for its cache key"

    # and it does not build one by hand: no tuple literal is assigned to
    # anything called `key` in this method.
    handmade = [n for n in ast.walk(tree)
                if isinstance(n, ast.Assign)
                and any(getattr(t, "id", "") == "key" for t in n.targets)
                and isinstance(n.value, ast.Tuple)]
    assert not handmade, (
        "_shells_for assembles its own cache key again — that is a second "
        "copy of `shapes.KINDS`, and the first copy was wrong in both "
        "directions")


def test_the_key_a_caller_actually_uses_carries_the_white():
    """⚠ THE GUARDS ABOVE WATCH `key_for`, AND THE FAULT CAME BACK AT THE
    CALLER.

    `f393d6f` reverted an optimisation that dropped `white` from a profile's
    cache key and left a run painted in D50 while the control read D65. Its
    message claimed "three tests fail if the conditional comes back". A hunt
    put it back in a form all three miss — `key_for` untouched, `depends_on`
    still one-parameter, and the CALLER handing over a doctored snapshot:

        _settled = host._settings().drawn_in("lab")
        if thing.kind in ("profile", "gamutfile"):
            _settled = dataclasses.replace(_settled, white="D50")
        key = shapes.key_for(thing, _settled)

    Every key pinned to D50, the builder never running on a white change, and
    both gates green at exactly the baseline count. Narrowing inside
    `key_for` IS caught; narrowing one line earlier is not — because all
    those guards ask what `key_for` does with honest settings, and none asks
    what settings a caller hands it.

    So this drives the caller and reads the keys it actually stored.
    """
    import gamut_app
    from types import SimpleNamespace as NS

    made = []

    def host_for(white):
        host = NS(_white=NS(currentData=lambda: white),
                  _mode=NS(currentData=lambda: "device"),
                  _relative=NS(isChecked=lambda: False),
                  _detail=NS(value=lambda: 20),
                  _space=NS(currentData=lambda: "lab"),
                  _build_space=lambda: "lab")
        host._settings = gamut_app.GamutApp._settings.__get__(
            host, gamut_app.GamutApp)
        host._build_one = lambda p, space="lab", **k: (
            made.append((pathlib.Path(p).name, white, space))
            or (NS(space=space, vertices=[[0.0, 0, 0]]), None))
        return host

    a = pathlib.Path("/x/printer-2019.icc")
    b = pathlib.Path("/x/printer-2021.icc")

    dialog = NS(_shell_cache={}, _trouble=lambda *_a: None,
                _name_in_run=lambda p: pathlib.Path(p).stem)
    dialog._host = host_for("D50")
    gamut_app.TimelineDialog._shells_for(dialog, a, b)
    after_d50 = set(dialog._shell_cache)

    dialog._host = host_for("D65")
    gamut_app.TimelineDialog._shells_for(dialog, a, b)
    after_d65 = set(dialog._shell_cache)

    assert len(after_d50) == 2, sorted(after_d50)
    assert len(after_d65) == 4, (
        "moving the white point added no cache entry, so the run kept the "
        f"shells it built under the other white: {sorted(after_d65)}")
    assert after_d50 < after_d65

    # ⚠ AND THE WHITE IS IN THE KEY THE CALLER STORED, whatever `key_for`
    # would have said on its own. This is the assertion the reintroduction
    # walked past.
    whites = {k[2] for k in after_d65}
    assert whites == {"D50", "D65"}, (
        f"the stored keys carry {sorted(whites)} — a caller is pinning the "
        "white before it reaches `key_for`, so two shapes painted "
        "differently share one entry")

    # AND THE BUILDER REALLY RAN AGAIN, which is what the reader sees.
    assert [w for _n, w, _s in made].count("D65") == 2, (
        f"the shells were not rebuilt under the new white: {made}")


def _run(built, made=None):
    """A TimelineDialog stand-in that builds through the REAL `_shells_for`.

    ⚠ THE ONLY THING FAKED IS THE ARGYLLCMS BUILD, and the docstring that
    used to stand here said so while faking `_name_in_run` as well — a real
    method that did not need faking, since bound to a stand-in with no `_run`
    it returns `path.stem`, exactly what the lambda returned. It bought
    nothing and cost the claim its truth. `_trouble` is a Qt label and is
    fair. Every source comment is a claim; this one is now the one it says.
    """
    import gamut_app

    host = NS(_white=NS(currentData=lambda: "D50"),
              _mode=NS(currentData=lambda: "device"),
              _relative=NS(isChecked=lambda: False),
              _detail=NS(value=lambda: 20),
              _space=NS(currentData=lambda: "lab"),
              _build_space=lambda: "lab")
    host._settings = gamut_app.GamutApp._settings.__get__(
        host, gamut_app.GamutApp)

    def build(path, space="lab", **_kw):
        stem = pathlib.Path(path).stem
        built.append(stem)
        shell = _Shell(stem, space)          # a real object, weighable
        if made is not None:
            made.append(_weakref.ref(shell))
        return shell, None

    host._build_one = build
    dialog = NS(_shell_cache={}, _host=host, _trouble=lambda *_a: None)
    dialog._name_in_run = gamut_app.TimelineDialog._name_in_run.__get__(
        dialog, gamut_app.TimelineDialog)
    return dialog


class _Shell:
    """Stands where a gamut stands: an object, so it can be weighed."""

    def __init__(self, name, space):
        self.name, self.space = name, space
        self.vertices = [[0.0, 0.0, 0.0]]


def _pair(n):
    return (pathlib.Path(f"/x/step-{n}a.icc"),
            pathlib.Path(f"/x/step-{n}b.icc"))


def test_a_long_run_does_not_hold_every_shell_it_ever_built():
    """⚠ THE CAP ITSELF WAS UNGUARDED — and then guarded by a number that
    three separate one-line changes moved out from under.

    The first version of this counted `len(_shell_cache)` once, at the end of
    an even number of inserts. A hunt walked past it three ways, each with
    both gates green at the baseline count:

      * a SECOND STORE beside the cache — 400 gamuts held after a 200-step
        run while the watched length read 8;
      * `if len(...) > 9: keep_newest(..., 8)`, so the cache alternates
        9, 8, 9, 8 and every even sample lands on 8;
      * and the LRU switched off once the cache is full (see the guard below).

    A dict's length is a PROXY. What the cap exists for is memory — this
    method's own words, "a cache that grows with the run would hold a
    printer's whole history" — so this weighs what is still reachable, which
    no second store and no sampling luck can hide, and it looks after EVERY
    call rather than at the end.
    """
    import gc
    import gamut_app

    built, shells = [], []
    dialog = _run(built, shells)

    # ⚠ AFTER EVERY CALL, AND WITH AN ODD NUMBER OF INSERTS TOO. Consecutive
    # pairs share a file — which is what walking a run actually does — so
    # these calls insert ONE shell, not two, and the cache passes through the
    # odd sizes the "> 9" walk-past hid in.
    for n in range(14):
        gamut_app.TimelineDialog._shells_for(
            dialog, pathlib.Path(f"/x/walk-{n}.icc"),
            pathlib.Path(f"/x/walk-{n + 1}.icc"))
        assert len(dialog._shell_cache) <= 8, (
            f"after the step to walk-{n + 1} the run holds "
            f"{len(dialog._shell_cache)} shells, over a bound that says 8")

    for n in range(12):
        gamut_app.TimelineDialog._shells_for(dialog, *_pair(n))
        assert len(dialog._shell_cache) <= 8, (
            f"after pair {n} the run holds {len(dialog._shell_cache)} shells")

    # ⚠ AND WEIGHED, NOT COUNTED. Every shell this run ever built was handed
    # out as a real object and is held here only weakly, so what survives a
    # collection is what the application is really keeping alive — wherever
    # it is keeping it.
    gc.collect()
    alive = sum(1 for ref in shells if ref() is not None)
    assert len(shells) >= 26, len(shells)          # the run really did build
    assert alive <= 8, (
        f"{alive} of the {len(shells)} gamuts this run built are still in "
        "memory; the cap is bounding a dict while something else holds the "
        "shapes")


def test_the_pair_a_reader_keeps_coming_back_to_is_not_the_first_thrown_away():
    """⚠ `keep_newest` WAS ADOPTED HERE WITHOUT `recall`, WHICH MAKES IT FIFO.

    A plain dict keeps INSERTION order, and the pair a reader keeps returning
    to is the one opened FIRST — so it was permanently the oldest and went
    first, while pairs glanced at once survived for being newest. Exactly
    backwards, and exactly what `recall` exists to prevent.

    ⚠ AND THE FIRST VERSION OF THIS GUARD STOPPED ONE PAIR SHORT. It drove
    four pairs against a cache of eight, so the cache only filled on the
    second-to-last step and the single degraded read found its answer by luck
    of ordering. A hunt turned the LRU off once the cache is full —
    `recall(...) if len(cache) < 8 else cache.get(key)`, which reads as an
    optimisation — and this guard, both gates and a 389-test probe all passed
    while the build counts went bit-for-bit back to the pre-fix numbers.
    Measured on the gesture below: the home pair rebuilt 1 time here, 3 times
    under that change.

    So it runs well past the point where the cache stays full, and asserts
    the thing a reader would notice: NOTHING is built twice while it is being
    looked at.
    """
    import gamut_app

    built = []
    dialog = _run(built)
    home = _pair(0)

    gamut_app.TimelineDialog._shells_for(dialog, *home)
    for n in range(1, 13):
        gamut_app.TimelineDialog._shells_for(dialog, *_pair(n))
        gamut_app.TimelineDialog._shells_for(dialog, *home)   # kept in view

    assert built.count("step-0a") == 1, (
        "the pair the reader kept coming back to was rebuilt "
        f"{built.count('step-0a')} times; the cache is evicting what is on "
        "screen and keeping what was glanced at once")
    assert len(built) == len(set(built)) == 26, (
        f"{len(built)} builds for {len(set(built))} distinct files — "
        "something was built twice while the reader was looking at it")

    # ⚠ AND SOMETHING REALLY WAS EVICTED. The assertion that used to close
    # this test read `built.count("step-1a") == 1` and CANNOT FAIL: pair 1 is
    # asked for exactly once, so it counts 1 under every policy — under FIFO,
    # under no cap at all, and under no cache at all. It reported the
    # positive half of the LRU claim while observing no eviction whatever.
    # Asking for pair 1 again is what tells "the cache kept the right thing"
    # apart from "the cache kept everything".
    gamut_app.TimelineDialog._shells_for(dialog, *_pair(1))
    assert built.count("step-1a") == 2, (
        "pair 1 was still cached after twelve later pairs — nothing is being "
        "evicted at all, so keeping the home pair proves nothing")
