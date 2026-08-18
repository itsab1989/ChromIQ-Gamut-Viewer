"""Folding a group away, and getting it back.

WHY THIS FILE EXISTS. The first version of the fold walked a group's children,
hid the ones that were not already hidden, remembered that list, and put the
list back on opening. It shipped, and two minutes in the real window produced:

    "there is a viewer and export styling section that is empty"
    "collapsing sections is horrible. they don't collapse in place but they
     move around, become only a little smaller and empty"

Four groups start folded, and all four could never be opened again: the window
re-asserts every fold once it is up -- a setVisible(False) issued while the
parent is hidden does not always survive the parent being shown -- and that
second call recorded the list again, found everything already hidden, and
stored an empty one.

Nothing about that is visible in a screenshot of a FOLDED group, and there was
no test of folding at all. These drive it: fold, unfold, and ask what is on
screen afterwards.
"""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

NAME = ("MeasuredGamutViewer", "MeasuredGamutViewer")


@pytest.fixture(scope="module")
def app():
    """A Qt application, with the imports in the one order that works — see
    test_accent.py, where the same fixture explains itself at length."""
    import gamut_app                                  # noqa: F401
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _settle(app, seconds=0.05):
    """Let Qt do its own work. This project does not use pytest-qt."""
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.002)


def _forget(key):
    # THROUGH prefs, so this reaches whichever store is in force -- under the
    # suite that is a throwaway one, and it must not be somebody's real
    # preferences even for a key named "test".
    import prefs
    prefs.store().remove(f"fold/{key}")


@pytest.fixture
def group(app):
    """A group with three rows, one of which the application itself hides."""
    from PyQt6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget

    _forget("test")
    holder = QWidget()
    box = QGroupBox("What the colours are measured against", holder)
    inside = QVBoxLayout(box)
    rows = [QLabel(f"row {n}", box) for n in range(3)]
    for row in rows:
        inside.addWidget(row)
    # THE ROW THE APPLICATION HAS ITS OWN REASON TO HIDE -- the ones naming an
    # open file, hidden until there is one. Folding must not bring it back.
    rows[2].setVisible(False)
    QVBoxLayout(holder).addWidget(box)
    yield holder, box, rows
    holder.close()
    _forget("test")


def test_a_group_that_starts_shut_opens_with_everything_in_it(group, app):
    """The fault as it was reported: four groups that opened empty."""
    import gamut_app

    holder, box, rows = group
    gamut_app.make_foldable(box, "test", False)
    holder.show()
    _settle(app, 0.15)

    assert box._fold_open is False
    assert not rows[0].isVisible(), "it did not fold at all"

    box._fold_open = True
    box._refold()
    _settle(app)
    assert rows[0].isVisible() and rows[1].isVisible(), (
        "the group opened empty — exactly what was reported")
    assert not rows[2].isVisible(), (
        "opening the group put back a row the application had hidden")


def test_re_asserting_the_fold_does_not_lose_the_contents(group, app):
    """THE MECHANISM OF THE FAULT. The window re-asserts every fold once it
    is up, so the fold has to survive being told the same thing twice."""
    import gamut_app

    holder, box, rows = group
    gamut_app.make_foldable(box, "test", False)
    holder.show()
    _settle(app, 0.15)
    for _ in range(3):
        box._refold()
    box._fold_open = True
    box._refold()
    _settle(app)
    assert rows[0].isVisible(), "re-asserting the fold emptied the group"


def test_folding_and_opening_again_leaves_the_group_as_it_was(group, app):
    import gamut_app
    from PyQt6.QtWidgets import QGroupBox

    holder, box, rows = group
    gamut_app.make_foldable(box, "test", True)
    holder.show()
    _settle(app, 0.15)
    tall = box.height()
    assert rows[0].isVisible()

    box._fold_open = False
    box._refold()
    _settle(app)
    shut = box.height()
    # IT REALLY COLLAPSES, rather than becoming "only a little smaller".
    assert shut < tall / 2, f"folded to {shut} px against {tall} px open"
    assert box.isFlat(), "a shut group still draws an empty bordered box"
    # THE ARROW IS DRAWN, NOT SPOKEN. What is painted carries it; what the
    # window's own lists ask for is the plain heading, because three of them
    # are keyed on it and the arrow stopped every one of them matching.
    assert QGroupBox.title(box).startswith("▶")
    assert box.title() == "What the colours are measured against"

    box._fold_open = True
    box._refold()
    _settle(app)
    assert rows[0].isVisible() and rows[1].isVisible()
    assert not rows[2].isVisible()
    assert QGroupBox.title(box).startswith("▼")
    assert box.title() == "What the colours are measured against"
    assert not box.isFlat()


def test_a_shut_group_keeps_room_for_its_own_heading(group, app):
    """The heading was drawn as the single letter that fits in 44 px: "W".

    With the body hidden nothing inside asks for any width, and a group
    constrained to its contents is then given the width of nothing.
    """
    import gamut_app

    holder, box, rows = group
    gamut_app.make_foldable(box, "test", False)
    holder.show()
    _settle(app, 0.15)
    need = box.fontMetrics().horizontalAdvance(box.title())
    assert box.minimumWidth() >= need, (
        f"the heading needs {need} px and the group may shrink to "
        f"{box.minimumWidth()}")


def test_folding_hides_controls_and_never_sets_one(app):
    """A picture must look the same after a group is folded and opened.

    Folding is about how much of the column you want to look at. If it could
    change a setting on the way past, a reader tidying the column would change
    what they are being shown, which is the one thing it must not do.
    """
    import gamut_app
    from PyQt6.QtWidgets import (QCheckBox, QComboBox, QGroupBox, QVBoxLayout,
                                 QWidget)

    _forget("look")
    holder = QWidget()
    box = QGroupBox("How it looks", holder)
    inside = QVBoxLayout(box)
    tick = QCheckBox("Live preview", box)
    tick.setChecked(True)
    pick = QComboBox(box)
    pick.addItems(["one", "two", "three"])
    pick.setCurrentIndex(2)
    inside.addWidget(tick)
    inside.addWidget(pick)
    QVBoxLayout(holder).addWidget(box)

    gamut_app.make_foldable(box, "look", True)
    holder.show()
    _settle(app, 0.15)
    for open_up in (False, True, False, True):
        box._fold_open = open_up
        box._refold()
        _settle(app, 0.02)
        assert tick.isChecked() is True
        assert pick.currentIndex() == 2
    holder.close()
    _forget("look")


def test_the_heading_is_the_control_and_a_click_on_it_toggles(group, app):
    """The band at the top of the group, as it is in ChromIQ."""
    import gamut_app
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    holder, box, rows = group
    gamut_app.make_foldable(box, "test", True)
    holder.show()
    _settle(app, 0.15)

    def press(y):
        box.mousePressEvent(QMouseEvent(
            QMouseEvent.Type.MouseButtonPress, QPointF(30.0, float(y)),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
        _settle(app, 0.02)

    press(6)
    assert box._fold_open is False and not rows[0].isVisible()
    press(6)
    assert box._fold_open is True and rows[0].isVisible()
    # AND A PRESS LOWER DOWN BELONGS TO WHATEVER CONTROL IS THERE.
    press(box.height() - 4)
    assert box._fold_open is True
