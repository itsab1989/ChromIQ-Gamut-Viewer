"""Reset means every setting in the window, including the styling section.

⚠ THE BUTTON'S OWN WORDING WAS FALSE. It asks:

    "Start again with the standard settings?
     Every setting in this window goes back to how it started: the
     appearance, the accent colour, how the shapes are drawn and coloured,
     the lighting, and everything else."

and an entire named section of the window — "Viewer and export styling",
eleven values — survived the press untouched. Driven, before the fix: 2 of 14
readouts moved, and those two were `_opacity` and its store key. The control,
the same window pressing nothing, moved 0 of 14 — so the probe could see the
section perfectly well; the reset simply never reached it.

WHY IT FELL OUT is the part worth keeping. That section is remembered by a
SECOND mechanism: `_remember_look` writes it to the store under
`picture_look`, so it is not in `_persisted()`, and `_reset_defaults` resets
`_persisted()` plus four things by hand. `_persisted()`'s own docstring warns
that a control forgotten there "would silently stop being remembered" — this
one is remembered twice over, and being remembered twice is what let it fall
out of the reset instead.
"""
import os
import pathlib
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    """Held, not merely created — see test_the_volume_note_reaches_a_reader."""
    from PyQt6.QtWidgets import QApplication
    import gamut_app                                  # noqa: F401
    yield QApplication.instance() or QApplication(["test"])


def test_the_section_can_go_back_to_how_it_started(app):
    """⚠ DRIVEN ON A REAL SECTION, not asserted about the source.

    `to_defaults` restores what the section held at the end of its own
    `__init__`, captured rather than typed out — so this also proves the
    capture happens at all, which it did not the first time: the line landed
    in `_remove_look` instead, where the anchor happened to be unique, and
    every press raised AttributeError out of a Qt slot.
    """
    from PyQt6.QtWidgets import QWidget
    import gamut_app

    holder = QWidget()
    section = gamut_app.LookSection(holder)
    started = section.snapshot()
    assert started, "the section reports nothing at all"

    moved = dict(started)
    moved.update(background="custom", colour="#111111",
                 walls="custom", wall_colour="#141414",
                 lettering="custom", lettering_colour="#e6e6e6",
                 gridlines="custom", gridlines_colour="#262626",
                 details=True, live=False)
    section.restore(moved)
    now = section.snapshot()
    changed = [k for k in started if started[k] != now.get(k)]
    assert len(changed) >= 8, (
        f"the section barely moved ({changed}), so putting it back proves "
        "nothing")

    section.to_defaults()
    assert section.snapshot() == started, (
        "the section did not go back to how it started: "
        f"{ {k: (started[k], section.snapshot()[k]) for k in started if started[k] != section.snapshot()[k]} }")


def test_the_snapshot_is_the_shape_restore_reads(app):
    """One assembly, not two. `_remember_look` used to build this by hand."""
    from PyQt6.QtWidgets import QWidget
    import gamut_app

    section = gamut_app.LookSection(QWidget())
    kept = section.snapshot()
    for key in ("background", "colour", "walls", "wall_colour", "lettering",
                "lettering_colour", "gridlines", "gridlines_colour",
                "look", "details", "live"):
        assert key in kept, f"the snapshot has lost {key!r}"
    section.restore(kept)
    assert section.snapshot() == kept, "a snapshot does not survive its own restore"


def _window(rebuild_says, did):
    import gamut_app
    panel = NS(snapshot=lambda: {"look": "kept"},
               to_defaults=lambda: did.append("styling reset"),
               restore=lambda saved: did.append(f"styling put back {saved}"))
    return NS(_slots=[("a-paper", object(), None)],
              _reference=None,
              _persisted=lambda: [],
              _looks_panel=panel,
              _appearance="dark", _scheme="Magenta", _paint="true",
              _per_shape={}, _shared={},
              _target=NS(blockSignals=lambda v: None,
                         setCurrentIndex=lambda i: None,
                         currentIndex=lambda: 0),
              _remember_everything=lambda: did.append("everything written"),
              _remember_look=lambda: did.append("styling written"),
              _sync_slider_labels=lambda: None,
              _on_manual_light=lambda: None,
              _apply_mode=lambda: None,
              _update_spin_labels=lambda: None,
              _apply_spin_availability=lambda: None,
              _apply_space_availability=lambda: None,
              _chart_drawable=lambda: False,
              _rebuild_reference=lambda: None,
              _rebuild=lambda redraw=True: rebuild_says,
              _put_settings_back=lambda: None,
              _remember_settled=lambda: None,
              _redraw=lambda: None)


def test_a_successful_reset_resets_the_styling_and_writes_it_down():
    """⚠ AND WRITES IT, SEPARATELY. `_remember_everything` walks `_persisted()`
    and does NOT write `picture_look`. Without the second write the window
    would show the defaults while the store still held the old styling, and
    the next start would put the old styling back — the same disagreement
    between the window and the disk that a refused reset used to commit."""
    import gamut_app
    did = []
    gamut_app.Notice.ask = staticmethod(lambda *a, **k: True)
    gamut_app.GamutApp._reset_defaults(_window(True, did))

    assert "styling reset" in did, (
        "the styling section survived a reset that promises 'every setting in "
        f"this window goes back to how it started' (did={did})")
    assert "styling written" in did, (
        f"the styling was reset on screen and not written down (did={did})")
    assert not any(d.startswith("styling put back") for d in did), (
        f"a successful reset undid its own styling reset (did={did})")


def test_a_refused_reset_puts_the_styling_back_and_writes_nothing():
    import gamut_app
    did = []
    gamut_app.Notice.ask = staticmethod(lambda *a, **k: True)
    gamut_app.GamutApp._reset_defaults(_window(False, did))

    assert "styling reset" in did, "the reset never reached the styling at all"
    assert any(d.startswith("styling put back") for d in did), (
        f"a refused reset left the styling section reset (did={did})")
    assert "styling written" not in did, (
        f"a refused reset wrote the styling to the store (did={did})")
    assert "everything written" not in did, (
        f"a refused reset wrote the settings to the store (did={did})")
