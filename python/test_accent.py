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


# --------------------------------------------------------------------------
# The percentage inside the progress bar
# --------------------------------------------------------------------------

def _rows_of(bar):
    """Where the coloured bar is, and where the digits are — from the picture.

    Read out of the pixels rather than out of the stylesheet, because the
    stylesheet was exactly what everybody kept adjusting while the number went
    on sitting in the wrong place.
    """
    import numpy as np
    from PyQt6.QtGui import QImage

    image = bar.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    wide, tall = image.width(), image.height()
    raw = image.bits()
    raw.setsize(tall * image.bytesPerLine())
    pixels = np.frombuffer(raw, np.uint8).reshape(
        tall, image.bytesPerLine() // 4, 4)[:, :wide, :3].astype(int)
    # The filled part of the bar, found at the far left where it always is.
    edge = pixels[:, 6, :]
    filled = [y for y in range(tall)
              if edge[y][0] > 150 and edge[y][2] > 60 and edge[y][1] < 120]
    # The digits: rows across the middle that are not one flat colour.
    band = pixels[:, int(wide * 0.40): int(wide * 0.60), :]
    ink = [y for y in range(tall)
           if (band[y].max(axis=0) - band[y].min(axis=0)).max() > 60]
    return filled, ink


def _prepared(app, cls):
    from PyQt6.QtGui import QFont
    import gamut_app

    app.setFont(QFont("Helvetica Neue", 13))
    app.setStyleSheet(gamut_app.stylesheet("Dark", "Magenta"))
    bar = cls()
    bar.setRange(0, 100)
    bar.setValue(73)
    bar.resize(320, 40)
    bar.show()
    app.processEvents()
    return bar


def test_the_percentage_sits_on_the_middle_of_the_bar(app):
    """THE BAR IS NOT THE WIDGET. The stylesheet gives it a margin so it does
    not touch the label above or the button below, and Qt centres the number on
    the widget, margin and all — which put it three pixels low, and five on a
    high-resolution screen. Measured against the coloured bar, which is the
    thing anybody looking at it is comparing against."""
    import gamut_app

    bar = _prepared(app, gamut_app.CentredProgressBar)
    filled, ink = _rows_of(bar)
    assert filled, "the coloured bar was not found in the picture at all"
    assert ink, "the percentage was not found in the picture at all"
    middle = (filled[0] + filled[-1]) / 2
    centre = (ink[0] + ink[-1]) / 2
    assert abs(centre - middle) <= 1.0, (
        f"the number sits {centre - middle:+.1f} px from the middle of the bar")


def test_qt_left_to_itself_really_does_put_it_in_the_wrong_place(app):
    """The other half of the pair: without this the test above could pass
    against a bar that never needed fixing, and would quietly stop meaning
    anything the day somebody removed the fix."""
    from PyQt6.QtWidgets import QProgressBar

    bar = _prepared(app, QProgressBar)
    filled, ink = _rows_of(bar)
    assert filled and ink
    middle = (filled[0] + filled[-1]) / 2
    centre = (ink[0] + ink[-1]) / 2
    assert centre - middle > 1.0, (
        "Qt now centres this correctly on its own — if that is really so, "
        "CentredProgressBar can go, and this test with it")
