"""A saved page must fit itself to the window it is opened in.

WHY THIS EXISTS. Two papers side by side on a phone came out with both shapes
cut straight through the side walls of their rooms — 80 to 155 vividly
coloured pixels in each room's outermost column, at every viewpoint, measured
with the spin paused and both rooms pinned to the same four cameras.

THE MACHINERY WAS ALREADY THERE AND NEVER RAN. `fitToPane` pulls the eye back
by as far as the pane is out of shape, capped at twice, always from the view
the page was written with. Measured against what the shapes actually need:

    room 195 x 654 (out of shape 3.35)   needs 2.00x   ← the cap, exactly
    room 310 x 660 (out of shape 2.13)   needs 1.30x
    room 410 x 700 (out of shape 1.71)   needs 1.15x

So the law was right. What was wrong is that every saved page said it had
already been placed: `_spin_options` set `placed` from "does this window have
a camera", which it always does once anything is drawn, and `fitAll` returns
at its first line when that is true. Measured before the fix: the same page
opened at 390, 620 and 1440 px put its eye at 2.598 every single time — the
written distance, never fitted. After it: 5.196 at 390, 5.188 at 620, 2.598
at 1440, and no shape touches a wall at any width or viewpoint.

The flag itself is right for the WINDOW's own view, which really does carry
its camera from the page before it, and that is why the fix is a distinction
rather than a deletion: asked for in as many words — "Never stack — zoom the
camera out instead so the shape fits a narrow room. This keeps side by side
at every width, which is what the option promises."
"""
import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_a_saved_page_is_not_marked_already_placed():
    import gamut_app
    from test_gamutview import _FakeApp
    # WITH A CAMERA, WHICH IS THE WHOLE POINT. Asked of a stub that has none,
    # `placed` is False whatever the rule says — and this test passed against
    # the old rule put back on purpose, proving nothing at all. A window that
    # has drawn anything has a camera; that is the state a save happens in.
    fake = _FakeApp()
    fake._camera = {"eye": {"x": 1.0, "y": 1.0, "z": 1.0}}
    # AND IT HAS TO BE THE READER'S OWN VIEW, which is the only kind that is
    # carried over unfitted. Without this the fixture cannot tell the rules
    # apart and the test passes on any of them — it did exactly that once.
    fake._camera_is_theirs = True
    live = gamut_app.GamutApp._spin_options(fake)
    saved = gamut_app.GamutApp._spin_options(fake, saved=True)
    assert live["placed"] is True, (
        "a view the reader dragged to is no longer carried over as theirs — "
        "the next page will fit it again, which pulls their chosen angle "
        "back a little on every rebuild")
    assert saved["placed"] is False, (
        "a saved page says its camera is already placed, so `fitAll` returns "
        "at its first line and the reader's window is never fitted — which "
        "is how two rooms on a phone cut both shapes in half")
    assert "placed" in live, "the live view no longer says either way"


def test_the_window_s_own_view_still_carries_its_camera():
    # THE FAILURE DIRECTION THAT MATTERS: switching this off everywhere would
    # bring back "the shape jumped around after i moved it. when i let go it
    # seemed like it snapped back while zooming out a touch" — every rebuild
    # would fit the camera it had just been handed, again.
    import gamut_app
    from test_gamutview import _FakeApp
    fake = _FakeApp()
    fake._camera = {"eye": {"x": 1.0, "y": 1.0, "z": 1.0}}
    fake._camera_is_theirs = True
    assert gamut_app.GamutApp._spin_options(fake)["placed"] is True

    # AND THE OTHER HALF OF THE SAME RULE: a camera nobody has dragged to is
    # only the view the last page opened at, and the next page must be free
    # to fit that to its own pane. Measured in the window with two rooms:
    # with this wrong, a rebuild at 900px went back to the written distance
    # and both shapes came through their side walls again.
    fresh = _FakeApp()
    fresh._camera = {"eye": {"x": 1.0, "y": 1.0, "z": 1.0}}
    fresh._camera_is_theirs = False
    assert gamut_app.GamutApp._spin_options(fresh)["placed"] is False


def test_every_save_path_says_it_is_saving():
    # Three writers reach `_spin_options`, and a page saved through any of
    # them is a fresh page in somebody else's window.
    src = inspect.getsource(__import__("gamut_app").GamutApp._write_scene)
    assert "saved: bool = False" in inspect.signature(
        __import__("gamut_app").GamutApp._write_scene).__str__().replace(
        "'", "") or "saved" in src, "the writer cannot be told it is saving"
    for name in ("_write_two_rooms", "_write_both_views"):
        text = inspect.getsource(getattr(__import__("gamut_app").GamutApp,
                                         name))
        assert "saved" in text, f"{name} cannot be told it is saving"


def test_the_rooms_are_never_stacked():
    # Asked for in as many words. Two rooms are two rooms at every width; the
    # narrow case is answered by pulling the eye back, not by giving up on
    # side by side.
    import re
    text = (_ROOT / "python" / "ti3gamut.py").read_text(encoding="utf-8")
    where = text[text.index("def write_side_by_side_html"):][:6000]
    # NOT "the word column is absent" — `body` stacks the row above the
    # strip and each `.half` stacks its caption above its picture, both
    # rightly. The question is whether a WIDTH RULE turns the row of rooms
    # into a column, and only that.
    rules = re.findall(r"@media[^{]*\{\{(.*?)\}\}", where, re.S)
    assert not any("flex-direction:column" in rule for rule in rules), (
        "a width rule stacks the two rooms — that is not two rooms side by "
        "side, which is what the control promises")
    assert ".row  {{ display:flex" in where, "the rooms are no longer a row"


def test_the_fit_is_still_capped_where_it_was_measured():
    text = (_ROOT / "python" / "ti3gamut.py").read_text(encoding="utf-8")
    assert "Math.min(2, h / w)" in text, (
        "the fitting law changed: a 195x654 room needs exactly twice, "
        "measured, and anything less leaves the shape through the wall")
