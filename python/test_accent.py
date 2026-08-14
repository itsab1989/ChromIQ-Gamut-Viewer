"""The accent has to reach the things the window paints itself.

A stylesheet carries the accent to every ordinary widget. The ⓘ icons are
drawn rather than styled, so the stylesheet goes straight past them -- and
re-applying it, which is what changing the accent does, left all thirty-five
in the colour they were built with. Nothing in a screenshot of the settings
would look wrong; only the icons would be the previous accent.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    """A window-less Qt application, with the imports in the one order that
    works: gamut_app pulls in QtWebEngineWidgets, and Qt refuses to load that
    once a QApplication exists. Creating the application first here broke six
    unrelated tests in the same run."""
    import gamut_app                                  # noqa: F401
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _painted(icon):
    """The most saturated pixel the icon actually put on screen."""
    image = icon.grab().toImage()
    best, score = None, -1
    for y in range(image.height()):
        for x in range(image.width()):
            colour = image.pixelColor(x, y)
            if colour.alpha() < 200:
                continue
            weight = colour.saturation() * colour.value()
            if weight > score:
                best, score = colour, weight
    return best


def test_an_icon_paints_the_colour_it_is_given(app):
    import gamut_app
    icon = gamut_app.Hint("why", None)
    seen = {}
    for name, scheme in gamut_app.SCHEMES.items():
        icon.set_colour(scheme["accent"])
        got = _painted(icon)
        assert got is not None, f"{name}: the icon painted nothing"
        want = scheme["accent"]
        for channel, at in (("red", 1), ("green", 3), ("blue", 5)):
            assert abs(getattr(got, channel)() - int(want[at:at + 2], 16)) < 26, \
                f"{name}: asked {want}, painted {got.name()}"
        seen[name] = got.name()
    # and the five are genuinely five, not one colour five times
    assert len(set(seen.values())) == len(gamut_app.SCHEMES), seen


def test_changing_the_colour_actually_redraws_it(app):
    """The icon caches its drawing per colour. A cache that ignores the new
    colour would pass every check above and still show the old one."""
    import gamut_app
    icon = gamut_app.Hint("why", None)
    icon.set_colour(gamut_app.SCHEMES["Magenta"]["accent"])
    first = icon.grab().toImage()
    icon.set_colour(gamut_app.SCHEMES["Green"]["accent"])
    second = icon.grab().toImage()
    assert first != second, "the icon drew the same thing for two colours"


def test_the_window_repaints_its_icons_whenever_it_repaints_itself():
    """_apply_mode is what runs on an appearance OR an accent change. If it
    stops recolouring the icons, they go stale again -- which is exactly the
    fault this guards."""
    import inspect

    import gamut_app
    source = inspect.getsource(gamut_app.GamutApp._apply_mode)
    assert "_recolour_hints" in source, \
        "_apply_mode no longer repaints the ⓘ icons"
