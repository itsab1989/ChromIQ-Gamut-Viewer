"""An ⓘ never opens a window taller than the screen it opens on.

WHY THIS EXISTS. The dialog took a `scroll` flag set by hand, and the comment
beside it said "only the glossary is long enough to need this". That stopped
being true the moment a long tooltip was moved behind an ⓘ where it belonged:
the drift box's explanation grew from 1,646 to 4,140 characters and the window
went to 1,372 px on a 1,079 px screen — its own OK button below the bottom
edge of the display.

BOTH GATES AND THE PANEL AUDIT CALLED THAT CLEAN, which is the whole reason
for this file. Nothing anywhere asked how tall an explanation had become.

BOTH DIRECTIONS, because a rule that scrolls everything is its own fault: a
short message gaining a scroll bar it never uses is what the original comment
was protecting against, and it is checked here too.
"""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    """A Qt application, with the imports in the one order that works — see
    test_accent.py, where the same fixture explains itself at length."""
    import gamut_app                                  # noqa: F401
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _built(app, body):
    """A Notice with *body* in it, laid out, and whether it scrolls."""
    import gamut_app
    from PyQt6.QtWidgets import QScrollArea

    dialog = gamut_app.Notice(None, "About this setting", body)
    dialog.adjustSize()
    end = time.time() + 0.05
    while time.time() < end:
        app.processEvents()
        time.sleep(0.002)
    tall = dialog.sizeHint().height()
    scrolls = bool(dialog.findChildren(QScrollArea))
    dialog.deleteLater()
    app.processEvents()
    return tall, scrolls


def _room(app):
    screen = app.primaryScreen()
    return screen.availableGeometry().height()


def test_a_long_explanation_still_fits_on_the_screen(app):
    # AS LONG AS THE ONE THAT FOUND THIS, and built out of real sentences
    # rather than one repeated word, because Qt wraps on spaces.
    body = ("Which colour families moved between the two files you have "
            "open, and which way. " * 40)
    assert len(body) > 3000, "the case is only a case if the text is long"
    tall, scrolls = _built(app, body)
    room = _room(app)
    assert tall <= room, (
        f"an explanation of {len(body)} characters opens {tall} px tall on a "
        f"{room} px screen, so its own buttons are past the bottom edge")
    assert scrolls, "it fits because it scrolls; that is the mechanism"


def test_a_short_message_gains_no_scroll_bar_it_never_uses(app):
    # THE OTHER DIRECTION. Scrolling everything would be a fault of its own,
    # and it is the one the original hand-set flag was avoiding.
    tall, scrolls = _built(app, "Nothing to report.")
    assert not scrolls, "a one-line message does not need a scroll bar"
    assert 0 < tall <= _room(app)


# THE REAL TEXT IS CHECKED ELSEWHERE, and deliberately not here. Asking the
# drift box for its own words means building the whole window, and a
# QWebEngineView inside this suite takes the process down with it — exit 139,
# and it has cost this project a green tree twice. The live text is measured
# by scripts/audit_the_panel_hovers_stay_short.py instead, which drives a real
# window in its own process.
