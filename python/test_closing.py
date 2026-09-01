"""What "Close them all" really closes.

WHY A STAND-IN RATHER THAN THE WINDOW. Constructing ``GamutApp`` inside pytest
brings up a QWebEngineView and aborts the run -- the same reason
``test_chart_panel`` works this way. So the method is called exactly as a
click reaches it, against an object holding the parts of the window it reads.

WHAT WENT WRONG, and it is the reason this file exists. The button said it
closed everything and left the comparison behind. Measured in the real
application, two papers open and Adobe RGB chosen, straight after the press:

    files open              []
    shapes actually drawn   ['Adobe RGB (1998)']
    the readout said        "90.7% of the colour Glossy-paper can print also
                             fits inside Adobe RGB (1998)"

A shape with nothing left to compare against, and figures still describing a
file that had just been closed. The second is the worse one: a saved picture
takes its caption straight from those labels, so a wrong sentence does not
stay on the screen where somebody might notice it.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class Label:
    """Just enough of a text label to be set, read and asked if it is empty."""

    def __init__(self, text=""):
        self._text = text

    def setText(self, text):        # noqa: N802  (Qt's name)
        self._text = text

    def text(self):
        return self._text

    def isVisible(self):            # noqa: N802  (Qt's name)
        return True


class _Text:
    """Anything with setText that a handler may touch on the way past."""

    def __init__(self):
        self.value = ""

    def setText(self, t):           # noqa: N802  (Qt's name)
        self.value = t

    def text(self):
        return self.value


class Combo:
    """A stand-in for Compare with, remembering what it was set to."""

    def __init__(self, index=2, data=None):
        self.index = index
        self.handled = 0
        #: What `currentData()` answers, when a test needs a kind of
        #: comparison other than the colour space this stand-in defaults to.
        #: Without it a test asking for the file chooser silently got a
        #: colour space instead and exercised nothing it meant to.
        self.data = data

    def setCurrentIndex(self, i):   # noqa: N802  (Qt's name)
        self.index = i

    def currentIndex(self):         # noqa: N802  (Qt's name)
        return self.index

    def currentData(self):          # noqa: N802  (Qt's name)
        if self.data is not None:
            return self.data
        return None if self.index == 0 else ("space", "Adobe RGB (1998)")


@pytest.fixture
def window():
    """A window with two papers, a chart, a comparison and a full readout."""
    import gamut_app                                       # noqa: F401
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    # EVERY READOUT THE WINDOW HAS, taken from the window's own list rather
    # than a copy of it here. A copy is what let two of them be forgotten:
    # the colour-family lines survived "Close them all" and were missing from
    # every saved page, because three separate lists had to be kept in step.
    import gamut_app as _app
    figures = {name: Label(f"a sentence about {name}")
               for name in _app.GamutApp.READOUTS}
    w = SimpleNamespace(
        READOUTS=_app.GamutApp.READOUTS,
        _slots=[("a", 1, None), ("b", 2, None)],
        _chart=("chart", None),
        _chart_placed=object(),
        _compare=Combo(index=2),
        _reference=("Adobe RGB (1998)", object()),
        _reference_path=None,
        _volume=Label("702,327"),
        _volume_hint=Label(""),
        _clear_btn=SimpleNamespace(setVisible=lambda v: None),
        _save=SimpleNamespace(setEnabled=lambda v: None),
        _refresh_slot_labels=lambda: None,
        _refresh_chart_panel=lambda: None,
        _fill_chart_profiles=lambda: None,
        _show_placeholder=lambda: None,
        _volume_units=lambda: "cubic Lab units",
        _image_facts={},
        _lab_gamuts={},
        _other_whites={},
        _reference_cache={},
        _compare_note=_Text(),
        **figures)
    # ⚠ THE REAL HELPERS, BOUND. "Close them all" now also gives back the
    # colours of every photograph it closes — about 9.6 MB each — and this
    # fixture is what proves the gesture still does everything else. A stub
    # that shrugged would let the freeing quietly stop happening.
    for helper in ("_facts_key", "_forget_unused_facts", "_forget_shapes_of",
                   "_lays_down_ink"):
        setattr(w, helper,
                getattr(_app.GamutApp, helper).__get__(w, _app.GamutApp))

    def compare_changed():
        # The real handler, reduced to the one thing this test is about.
        w._reference = None if w._compare.currentData() is None else w._reference
        w._compare.handled += 1

    w._on_compare_changed = compare_changed
    return w


def close_them_all(w):
    import gamut_app
    gamut_app.GamutApp._on_clear(w)


def test_closing_them_all_closes_the_comparison_too(window):
    close_them_all(window)
    assert window._compare.index == 0, (
        "Compare with was left showing a comparison that is no longer loaded")
    assert window._reference is None, (
        "the comparison shape survived, so it is still drawn with nothing "
        "left to compare it against")


def test_it_goes_through_the_combo_box_rather_than_behind_it(window):
    """Assigning to _reference would leave the box naming a shape that is gone.

    The handler is also what clears the note underneath, so reaching past it
    would leave that behind too.
    """
    close_them_all(window)
    assert window._compare.handled == 1, (
        "the comparison was cleared without telling the control that shows it")


def test_the_figures_go_with_the_files_they_described(window):
    """⚠ FROM THE WINDOW'S OWN LIST, NOT A COPY OF IT.

    This test held a fourth hand-written copy of the readout names — the
    exact fault `READOUTS` exists to prevent, and its comment describes:
    "a list that must be kept in step by hand will not be". The copy still
    named `_pair`, which is not a widget on the window at all and never was,
    and it was missing `_range` and `_shared_lbl`, which are.

    A list that omits a readout cannot notice that readout going stale.
    """
    import gamut_app
    close_them_all(window)
    left = {name: getattr(window, name).text()
            for name in gamut_app.GamutApp.READOUTS
            if getattr(window, name, None) is not None
            and getattr(window, name).text()}
    assert not left, (
        f"these still describe files that were just closed: {sorted(left)}")


def test_the_readout_a_saved_picture_would_carry_is_empty_afterwards(window):
    """The caption of an exported picture is read straight out of the labels.

    So this is not only about what is on screen: a stale figure here becomes a
    stale figure printed under a picture somebody sends to a forum.
    """
    import gamut_app
    close_them_all(window)
    said = gamut_app.GamutApp._readout_text(window)
    assert said.strip() == "", f"a picture saved now would be captioned {said!r}"


def test_the_files_and_the_chart_still_go(window):
    """The behaviour that was already right, kept right."""
    close_them_all(window)
    assert window._slots == []
    assert window._chart is None
    assert window._chart_placed is None
    assert window._volume.text() == "—"


def test_the_pictures_colours_are_handed_back_too(window):
    """⚠ "CLOSE THEM ALL" GAVE BACK EVERYTHING BUT THE MEMORY.

    It emptied the slots, the chart, the comparison and every readout in the
    window's own list — and left each photograph's colours behind. An entry
    is the picture's colours themselves, up to 300,000 of them in two float64
    arrays: about 9.6 MB a photograph, held for the life of the window.
    Twenty photographs in a sitting is roughly 190 MB that the start-again
    gesture could never give back.

    This belongs beside the other four things the gesture closes, and in the
    same fixture, because the fault was that a list of things to release had
    to be kept in step by hand — which is how the colour-family lines came to
    survive it once already.
    """
    window._image_facts = {("/a/holiday.png", 111): {"colours": 9},
                           ("/b/sunset.png", 222): {"colours": 9}}
    close_them_all(window)
    assert window._image_facts == {}, (
        "the photographs' colours survived Close them all — about 9.6 MB "
        "each, for the life of the window")


def test_every_name_in_the_readout_list_is_a_readout_that_exists():
    """⚠ `_pair` SAT IN THAT LIST AND WAS NOT A WIDGET AT ALL.

    Both consumers skip a missing name with `getattr(..., None)`, so it did
    nothing, quietly, for as long as it was there: not cleared, not copied
    into a saved page, not noticed. A list whose entries are silently
    optional is a list that cannot be wrong out loud.

    The other half of the same fault: `_range` and `_shared_lbl` ARE
    readouts and were missing from it, so every saved page went out without
    the range panel and without "Both can print …% of everything either one
    can". Driven before fixing, both absent from `_readout_text()`.
    """
    import inspect
    import gamut_app

    src = inspect.getsource(gamut_app.GamutApp)
    for name in gamut_app.GamutApp.READOUTS:
        assert f"self.{name} = " in src, (
            f"{name} is in READOUTS and is never assigned on the window — "
            f"both consumers skip it in silence, so it does nothing at all")
    # AND THE READOUTS THAT EXIST ARE IN IT. These four are the sentences a
    # saved page carries; leaving one out loses it from every export.
    for name in ("_coverage", "_picture_loss", "_range", "_shared_lbl"):
        assert name in gamut_app.GamutApp.READOUTS, (
            f"{name} is a readout and is not in the list, so it is neither "
            f"cleared with the files nor carried into a saved page")


def test_cancelling_the_chooser_puts_back_what_was_there(window):
    """⚠ CANCEL THREW THE COMPARISON AWAY AND LEFT ITS NUMBERS ON SCREEN.

    `_on_compare_changed` clears the comparison before it knows whether a new
    one is coming. The cancel arm then returned early — past the refresh — so
    pressing Cancel discarded the comparison already loaded AND left the
    sentences describing it behind. Driven:

        before   box "sRGB",     76.0% ... also fits inside sRGB
        cancel   box "Nothing",  76.0% ... also fits inside sRGB

    ⚠ AND THE FIRST REPAIR TRADED ONE DISAGREEMENT FOR ANOTHER. It restored
    the comparison from `currentIndex()` — but this handler runs AFTER the
    box has moved to what was just picked, so the box read "A profile, paper
    or picture…" over a comparison that was still sRGB. The index that is put
    back is the last one that SETTLED.
    """
    import gamut_app

    class Cancelled:
        def exec(self):
            return 0

        def selectedFiles(self):
            return []

    window._file_dialog = lambda *a, **k: Cancelled()
    window._compare_settled = 3
    window._reference = ("sRGB", object())
    window._reference_m = None
    window._reference_path = None
    window._compare.data = ("icc", None)     # "open a file…" was chosen
    window._compare.index = 7                # and the box has already moved
    window._compare_note = _Text()
    window._last_folder = ""
    window._chart_profile_offer = lambda: None
    window._redraw = lambda: None
    gamut_app.GamutApp._on_compare_changed(window)

    assert window._reference is not None, (
        "Cancel threw away the comparison that was already loaded")
    assert window._compare.index == 3, (
        f"the box was left showing something other than the comparison that "
        f"is actually loaded: index {window._compare.index}")


def _chooser(window, returns):
    """Point the comparison chooser at a result, cancelled or not."""
    class Dialog:
        def exec(self):
            return 0 if returns is None else 1

        def selectedFiles(self):
            return [] if returns is None else [str(returns)]
    window._file_dialog = lambda *a, **k: Dialog()
    window._compare.data = ("icc", None)
    window._compare.index = 7
    window._chart_profile_offer = lambda: None
    window._redraw = lambda: None
    window._last_folder = ""


def test_cancelling_puts_back_the_sentence_beside_the_box_too(window):
    """⚠ HALF A RESTORATION READS AS A FAULT IN THE FILE.

    Cancel put back the comparison, the index and the path, and left
    `_compare_note` cleared — so the line describing the comparison vanished
    while the box and every number stayed. The comment on that arm claimed
    the screen never says a comparison is there when it is not; it said
    nothing about the reverse.
    """
    import gamut_app
    window._compare_note = _Text()
    window._compare_note.setText("What most images and most screens assume.")
    window._compare_settled = 3
    window._reference = ("sRGB", object())
    window._reference_m = None
    window._reference_path = None
    _chooser(window, None)
    gamut_app.GamutApp._on_compare_changed(window)

    assert window._reference is not None
    assert window._compare.index == 3
    assert window._compare_note.text() == (
        "What most images and most screens assume."), (
        "the sentence describing the comparison vanished while the "
        "comparison, the box and every number stayed")


def test_a_comparison_that_cannot_be_used_leaves_nothing_describing_it(window):
    """⚠ THE ERROR ARM DID WHAT CANCEL USED TO DO.

    The box went to "Nothing — this one on its own" while
    "77.4% … fits inside Matte-paper (measured)" stayed on screen, and
    `_reference_path` kept pointing at the file that had just failed — so
    the next setting change tried it again. A comparison that could not be
    prepared is not loaded, and nothing may still describe one.
    """
    import gamut_app
    window._compare_note = _Text()
    window._compare_note.setText("a sentence about the old comparison")
    window._reference = ("sRGB", object())
    window._reference_m = None
    window._reference_path = None
    _chooser(window, "/nowhere/broken.ti3")

    def cannot(_path):
        raise ValueError("this file could not be used")
    window._build_one = cannot
    # The real one wants a QWidget parent; this window is a stand-in.
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    window._compare_settled = 3
    gamut_app.GamutApp._on_compare_changed(window)

    assert window._reference is None
    assert window._reference_path is None, (
        "the failed file is still the comparison path, so the next setting "
        "change will try it again")
    assert window._compare_note.text() == "", (
        "a sentence about a comparison that is not loaded")
    assert window._compare.index == 0
