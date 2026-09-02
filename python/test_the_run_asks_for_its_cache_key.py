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


def test_a_profile_is_rebuilt_when_the_white_moves_where_it_can_move_it():
    """...but only where the white point can actually reach it.

    ⚠ THIS TEST ASSERTED THE OPPOSITE AND WAS RIGHT TO, UNTIL IT WAS
    MEASURED. It was written as the control for the `mode` test above — "a
    profile DOES depend on white, so the probe can move" — and `_key` pins
    the space to CIELAB, which is the one space where that is false. Built
    through the real `icc_gamut` under D50 and D65: every profile in this
    repository and a `.gam` from ArgyllCMS's own `iccgamut` come back
    BIT-IDENTICAL in CIELAB, and different in CIELUV and CIE XYZ. An ICC
    profile's connection space is D50-referred; the conversion that lets
    white matter happens on the way OUT of Lab.

    So the control moves to where the effect is real. The CIELAB half is now
    the other assertion — that the key does NOT carry a setting which cannot
    change the answer, because carrying it rebuilt an ArgyllCMS shell on
    every nudge of the white point for an identical picture.

    `test_white_really_is_inert_for_a_profile_in_cielab` in `test_shapes.py`
    is the measurement this rests on, taken against the builders themselves.
    """
    import shapes
    p = pathlib.Path("/x/Glossy-paper.icc")
    thing = shapes.thing_for(p, IMAGE)

    def key(white, space):
        return shapes.key_for(thing, shapes.Settings(white=white, space=space))

    for space in ("luv", "xyz"):
        assert key("D50", space) != key("D65", space), (
            f"a profile in {space} no longer keys on the white point, and "
            "there it genuinely moves the shape — two different shapes would "
            "share one cache entry")

    assert key("D50", "lab") == key("D65", "lab"), (
        "a profile in CIELAB still keys on the white point, so the run "
        "rebuilds a shell to get a bit-identical answer")


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
