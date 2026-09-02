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
    offered, freed = [], []
    # ⚠ THE PANEL IS REFRESHED WITHOUT RE-PLACING THE CHART. Going through
    # `_chart_profile_offer` here put a SECOND modal dialog on screen —
    # "These patches could not be placed" — about a part of the window the
    # reader never touched. A failure arm reports its own failure and no
    # other.
    window._fill_chart_profiles = lambda: offered.append("filled")
    window._refresh_chart_panel = lambda: offered.append("refreshed")
    window._chart_profile_offer = lambda: offered.append("PLACED AGAIN")
    window._forget_unused_facts = lambda: freed.append(1)
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
    # ⚠ AND THE OTHER TWO THINGS THE CANCEL ARM DOES. This arm was brought
    # level with Cancel and stopped three-quarters of the way: the chart
    # panel went on naming a "Placed through" profile under a Compare with
    # of "Nothing", and a photograph's colours were never given back.
    assert "filled" in offered and "refreshed" in offered, (
        "the chart panel was left naming a profile for a comparison that "
        "is not loaded")
    assert "PLACED AGAIN" not in offered, (
        "the failure arm re-placed the chart, which opens a second modal "
        "dialog about something the reader did not touch")
    assert freed, (
        "a photograph's colours were not given back when the comparison "
        "failed to load")


def test_a_setting_that_cannot_be_used_is_put_back():
    """⚠ THE WINDOW DIED, and not even with a traceback.

    `_rebuild` warned "That setting cannot be used here" and returned without
    assigning the rebuilt slots — so the shapes stayed in the OLD space while
    the control now read the new one, and the `_redraw()` that follows raised

        ValueError: asked to label the axes 'luv' while the shapes were
                    built in 'lab'

    out of a Qt slot. PyQt terminates the process for that: driven, the app
    exited 1 with an empty stdout and no Python traceback at all, which is
    why an excepthook never saw it. Two ways in, both driven: a slot's file
    going away, and a Lab-only .ti3 with the paper-white tick on.

    Refusing a setting has to UNDO it. The refusal message already existed;
    what was missing was putting the control back.
    """
    import gamut_app
    from types import SimpleNamespace as NS

    class Combo:
        def __init__(self):
            self.index = 2
            self.blocked = False

        def currentIndex(self):     # noqa: N802  (Qt's name)
            return self.index

        def setCurrentIndex(self, i):   # noqa: N802
            assert self.blocked, (
                "the control was put back without blocking signals, so the "
                "handler runs again on its own correction")
            self.index = i

        def blockSignals(self, on):     # noqa: N802
            self.blocked = on

        def currentData(self):      # noqa: N802
            return "luv"

    redrawn = []
    put_back = []
    w = NS(_space=Combo(),
           _apply_space_availability=lambda: None,
           _rebuild_reference=lambda: None,
           _rebuild=lambda redraw=True: False,          # the rebuild refuses
           _put_settings_back=lambda: put_back.append(1),
           _remember_settled=lambda: None,
           _redraw=lambda: redrawn.append(1))
    gamut_app.GamutApp._on_space_changed(w)
    assert put_back, (
        "the refused setting was left on the control, so the axes name a "
        "space the shapes were never built in — and the redraw kills the app")
    assert redrawn, "the window was left un-redrawn after the refusal"

    # AND A SETTING THAT WORKS IS REMEMBERED, so the next refusal has
    # somewhere to go back to.
    remembered = []
    w2 = NS(_space=Combo(),
            _apply_space_availability=lambda: None,
            _rebuild_reference=lambda: None,
            _rebuild=lambda redraw=True: True,
            _put_settings_back=lambda: None,
            _remember_settled=lambda: remembered.append(1),
            _redraw=lambda: None)
    gamut_app.GamutApp._on_space_changed(w2)
    assert remembered, (
        "a setting that WORKED was not written down, so the next refusal "
        "has nothing correct to go back to")


def test_a_refusal_puts_back_every_control_it_refused():
    """⚠ THE REFUSAL UNDID ONE CONTROL AND KEPT THE REST.

    The first version restored the "Draw it in" combo and nothing else, so a
    paper-white tick or a shape mode the reader had just set was silently
    kept while the shapes went on describing the state before it. And the
    thing it restored FROM was a remembered combo index, set in `__init__`
    and updated only after a successful change — while `_restore_everything`
    puts the controls back from the store with signals BLOCKED. A window
    reopened in CIE XYZ therefore carried a settled index of 0, and the
    first refusal moved the combo to CIELAB over shapes built in XYZ,
    raising the very ValueError the refusal exists to prevent.

    So the snapshot is the five settings the shapes were built under, taken
    at the two moments the controls and the shapes are known to agree, and
    every control comes back from it.
    """
    import gamut_app
    import shapes
    from types import SimpleNamespace as NS

    class Combo:
        def __init__(self, data):
            self._data, self.index, self.blocked = data, 0, False

        def findData(self, value):      # noqa: N802  (Qt's name)
            return self._data.index(value) if value in self._data else -1

        def currentIndex(self):         # noqa: N802
            return self.index

        def setCurrentIndex(self, i):   # noqa: N802
            assert self.blocked, "a control was corrected without blocking"
            self.index = i

        def blockSignals(self, on):     # noqa: N802
            self.blocked = on

    class Tick:
        def __init__(self):
            self.on, self.blocked = False, False

        def isChecked(self):            # noqa: N802
            return self.on

        def setChecked(self, v):        # noqa: N802
            assert self.blocked, "the tick was corrected without blocking"
            self.on = v

        def blockSignals(self, on):     # noqa: N802
            self.blocked = on

    w = NS(_space=Combo(["lab", "luv", "xyz"]),
           _white=Combo(["D50", "D65"]),
           _mode=Combo(["device", "hull"]),
           _relative=Tick(),
           _apply_space_availability=lambda: None)
    # ⚠ THE SNAPSHOT IS MADE BY THE CODE, from controls in a known state.
    # An earlier version hand-built `shapes.Settings(space="xyz")` — and so
    # could not see that the real maker derives `space` from
    # `_build_space()`, which cannot represent Ink amounts. It fabricated
    # the value whose construction was the defect, and shipped green.
    w._space.index, w._white.index, w._mode.index = 2, 1, 1
    w._relative.on = True
    for combo in (w._space, w._white, w._mode):
        combo.currentData = (
            lambda c=combo: c._data[c.index])   # what a real combo answers
    gamut_app.GamutApp._remember_settled(w)

    # the reader now moves all four away from what the shapes hold
    w._space.index, w._white.index, w._mode.index = 0, 0, 0
    w._relative.on = False

    gamut_app.GamutApp._put_settings_back(w)

    assert w._space.index == 2, "the space was not put back"
    assert w._white.index == 1, "the white point was not put back"
    assert w._mode.index == 1, "the shape mode was not put back"
    assert w._relative.on is True, (
        "the paper-white tick was kept while everything else went back, so "
        "the shapes describe one state and the controls another")


def _refusing_window():
    """A window whose rebuild refuses, watching what the handler does."""
    from types import SimpleNamespace as NS
    seen = {"put_back": 0, "remembered": 0, "redrawn": 0}
    w = NS(_slots=[("a-paper", object(), None)],
           _rebuild=lambda redraw=True: False,
           _rebuild_reference=lambda: None,
           _apply_space_availability=lambda: None,
           _put_settings_back=lambda: seen.__setitem__(
               "put_back", seen["put_back"] + 1),
           _remember_settled=lambda: seen.__setitem__(
               "remembered", seen["remembered"] + 1),
           _redraw=lambda: seen.__setitem__("redrawn", seen["redrawn"] + 1),
           _space=None)
    return w, seen


def test_the_white_point_refuses_like_the_space_does():
    """⚠ THIS ROUTE DROPPED THE ANSWER ENTIRELY.

    `_on_white_changed` rebuilds the COMPARISON first and then the papers.
    Ignoring the refusal moved the comparison to the new white while the
    papers stayed on the old one — and the coverage line then compared two
    shapes measured against different whites. A wrong number, printed
    confidently, from the fault class this release is named after.
    """
    import gamut_app
    w, seen = _refusing_window()
    gamut_app.GamutApp._on_white_changed(w)
    assert seen["put_back"] == 1, (
        "the white point stayed on the refused value, so the comparison and "
        "the papers are measured against different whites")
    assert seen["remembered"] == 0, "a refused setting was written down as good"
    assert seen["redrawn"] >= 1, "the window was left showing the old state"


def test_the_shape_settings_refuse_like_the_space_does():
    """⚠ AND THIS ONE DID NOT EVEN REDRAW.

    `_on_shape_setting` carries the shape mode and the paper-white tick.
    Ignoring the refusal left the papers describing one state, the
    comparison — rebuilt just above — describing another, and nothing on
    screen redrawn to show either.
    """
    import gamut_app
    w, seen = _refusing_window()
    gamut_app.GamutApp._on_shape_setting(w)
    assert seen["put_back"] == 1, (
        "the shape mode or the tick stayed on the refused value")
    assert seen["remembered"] == 0
    assert seen["redrawn"] >= 1, (
        "the panel was left matching neither the old state nor the new one")


def test_every_route_that_rebuilds_obeys_the_refusal_rule():
    """⚠ THE ROUTES ARE DISCOVERED, NOT LISTED.

    The first version of this named two handlers by hand — which is how the
    rule came to hold on the space route and not on the white or the shape
    settings, and then not on Reset either. A test that lists the routes it
    checks cannot notice a new one, and `_reset_defaults` was a route nobody
    had ever looked at: pressing "Start again with the standard settings"
    while in CIE XYZ ended the process.

    So this asks the class which methods call `_rebuild()`, and holds every
    one of them to the same rule:

        refused   -> put every control back, do NOT write the snapshot
        worked    -> write the snapshot, put nothing back

    A new route that rebuilds and forgets either half fails here on the day
    it is written.
    """
    import inspect
    import gamut_app
    from types import SimpleNamespace as NS

    routes = sorted(name for name, fn in vars(gamut_app.GamutApp).items()
                    if callable(fn) and _mentions_rebuild(fn))
    assert routes, "no route calls _rebuild() — this test is watching nothing"

    for name in routes:
        for rebuild_says in (False, True):
            did = {"put_back": 0, "remembered": 0}
            w = NS(_slots=[("a-paper", object(), None)],
                   _reference=None,
                   _persisted=lambda: [],
                   _appearance="dark", _scheme="Magenta", _paint="true",
                   _per_shape={}, _shared={},
                   _target=NS(blockSignals=lambda v: None,
                              setCurrentIndex=lambda i: None,
                              currentIndex=lambda: 0),
                   _remember_everything=lambda: None,
                   _sync_slider_labels=lambda: None,
                   _on_manual_light=lambda: None,
                   _apply_mode=lambda: None,
                   _apply_space_availability=lambda: None,
                   _chart_drawable=lambda: False,
                   _rebuild_reference=lambda: None,
                   _rebuild=lambda redraw=True: rebuild_says,
                   _put_settings_back=lambda: did.__setitem__(
                       "put_back", did["put_back"] + 1),
                   _remember_settled=lambda: did.__setitem__(
                       "remembered", did["remembered"] + 1),
                   _redraw=lambda: None)
            gamut_app.Notice.ask = staticmethod(lambda *a, **k: True)
            getattr(gamut_app.GamutApp, name)(w)

            if rebuild_says:
                assert did["remembered"] == 1, (
                    f"{name} rebuilt successfully and never wrote the "
                    f"snapshot, so the next refusal restores settings the "
                    f"shapes were not built under")
                assert did["put_back"] == 0, f"{name} undid a change that worked"
            else:
                assert did["put_back"] == 1, (
                    f"{name} was refused and left the control on the refused "
                    f"value — the axes then name a space the shapes were "
                    f"never built in, and the redraw ends the process")
                assert did["remembered"] == 0, (
                    f"{name} wrote a refused setting down as good")


def _mentions_rebuild(fn):
    """Does this method reach `self._rebuild` at all?

    ⚠ BY THE SYNTAX TREE, NOT BY A SUBSTRING. The first version asked
    whether `"self._rebuild()"` appeared in the source, and a hunt walked
    straight past it: a route written

        remake = self._rebuild
        remake()

    rebuilds, forgets the rule, and the whole suite stays green. A test that
    finds its own subjects is only as good as the finding, so an attribute
    LOAD is what is looked for, which catches the alias as well as the call.

    ⚠ AND BY THE NAME AS A STRING TOO, because the attribute rule was not
    enough either. A hunt injected

        getattr(self, "_rebuild")()

    into a route, ran the whole gate, and got 1227 passed — the same count
    as the untouched baseline, to the test. There is no `ast.Attribute` node
    in that line at all: the method name is a string constant handed to
    `getattr`, so an attribute walk cannot see it, and the route dropped
    silently out of the rule.

    That is the SECOND time this finder has been widened after a hunt walked
    past it, which is the point worth keeping: each fix was right for the
    evasion in front of it and blind to the next one. Both forms are checked
    now — a load of the attribute, or the exact name appearing as a string
    anywhere in the method, which also covers `name = "_rebuild"` followed
    by `getattr(self, name)`.

    Checked when this was written: NO method of GamutApp contains the exact
    string "_rebuild" for any other reason, so the second rule costs nothing
    in false positives today. If one ever does, this will name it by failing
    rather than by going quiet, which is the right way round.
    """
    import ast
    import inspect
    try:
        tree = ast.parse(inspect.getsource(fn).strip())
    except (OSError, TypeError, SyntaxError, IndentationError):
        return False
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and node.attr == "_rebuild"
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"):
            return True
        if isinstance(node, ast.Constant) and node.value == "_rebuild":
            return True
    return False


def test_the_snapshot_holds_what_the_controls_hold():
    """⚠ AND IT IS MADE BY THE CODE, NOT FABRICATED BY THE TEST.

    The previous version of this file hand-built
    `shapes.Settings(space="xyz")` and never called the thing that makes the
    snapshot — so it could not see that `_settings()` derives `space` from
    `_build_space()`, which maps Ink amounts to "lab" ON PURPOSE (a shape is
    still measured in CIELAB there, it is simply not drawn). The snapshot
    could not represent Ink amounts at all, and a refusal sent the reader to
    CIELAB: the chart gone, the panel asking them to find an ICC profile, on
    a route that never touched the space. The test fabricated the value
    whose CONSTRUCTION was the defect, which is why it shipped green.

    So this calls `_remember_settled` on controls that say "rgb".
    """
    import gamut_app
    from types import SimpleNamespace as NS

    w = NS(_space=NS(currentData=lambda: "rgb"),
           _white=NS(currentData=lambda: "D50"),
           _mode=NS(currentData=lambda: "device"),
           _relative=NS(isChecked=lambda: False),
           _detail=NS(value=lambda: 20))
    gamut_app.GamutApp._remember_settled(w)

    assert w._settled[0] == "rgb", (
        f"the snapshot recorded {w._settled[0]!r} while the control said "
        f"'rgb' — restoring from it moves the reader out of Ink amounts")
    # AND IT IS NOT A `shapes.Settings`, whose `space` cannot hold this.
    w._build_space = gamut_app.GamutApp._build_space.__get__(
        w, gamut_app.GamutApp)
    w._settings = gamut_app.GamutApp._settings.__get__(w, gamut_app.GamutApp)
    assert w._settings().space == "lab", (
        "`_build_space` stopped collapsing Ink amounts, so this test is "
        "describing a hole that no longer exists")


def test_starting_again_rebuilds_the_shapes_it_resets():
    """⚠ PRESSING "START AGAIN WITH THE STANDARD SETTINGS" KILLED THE APP.

    It wrote every control — including "Draw it in" — with signals blocked,
    so no handler ran and nothing was rebuilt; the redraw then drew shapes
    built in one space under axes named for another, and the ValueError went
    out of a Qt slot, where PyQt ends the process. Driven in CIE XYZ: exit 1,
    nothing printed after the gesture.

    It also left the window able to hold two shapes in DIFFERENT spaces, and
    the next file opened made the panel say "Both can print 0% of everything
    either one can" where the truth was 77%.

    Reachable since the button was added. Nothing had ever pressed it in a
    driver — which is where the risk in this window now lives.
    """
    import gamut_app
    from types import SimpleNamespace as NS

    did = {"rebuilt": 0, "remembered": 0, "put_back": 0, "redrawn": 0}
    w = NS(_slots=[("a-paper", object(), None)],
           _reference=None,
           _persisted=lambda: [],
           _appearance="dark", _scheme="Magenta", _paint="true",
           _per_shape={}, _shared={},
           _target=NS(blockSignals=lambda v: None,
                      setCurrentIndex=lambda i: None,
                      currentIndex=lambda: 0),
           _remember_everything=lambda: None,
           _sync_slider_labels=lambda: None,
           _on_manual_light=lambda: None,
           _apply_mode=lambda: None,
           _apply_space_availability=lambda: None,
           _chart_drawable=lambda: False,
           _rebuild_reference=lambda: None,
           _rebuild=lambda redraw=True: did.__setitem__("rebuilt", did["rebuilt"] + 1)
           or True,
           _remember_settled=lambda: did.__setitem__(
               "remembered", did["remembered"] + 1),
           _put_settings_back=lambda: did.__setitem__(
               "put_back", did["put_back"] + 1),
           _redraw=lambda: did.__setitem__("redrawn", did["redrawn"] + 1))
    gamut_app.Notice.ask = staticmethod(lambda *a, **k: True)
    gamut_app.GamutApp._reset_defaults(w)

    assert did["rebuilt"] == 1, (
        "Reset wrote a new space onto the controls and never rebuilt the "
        "shapes, so the redraw draws them under axes that do not match — "
        "and that ValueError ends the process")
    assert did["remembered"] == 1, (
        "the settings a reset lands on were never written down, so the next "
        "refusal restores something the shapes were not built under")
    assert did["put_back"] == 0
    assert did["redrawn"] == 1


def test_nothing_is_cleared_until_the_shapes_agree_to_move():
    """⚠ THE REFUSAL LEFT EIGHT CONTROLS UNTICKED AND STILL LIVE.

    `_apply_space_availability` is DESTRUCTIVE on the way in: the rings, the
    grey axis, the slice, the ideal neutral, the measured points, what is out
    of reach, the two-room view and the manual light are cleared for the
    space being entered. Called BEFORE the rebuild, a refusal then put the
    space back and left the ticks gone — `_put_settings_back` restores four
    controls and re-ENABLES the rest; nothing re-ticks.

    ⚠ EIGHT, NOT ELEVEN, WHICH THIS DOCSTRING SAID UNTIL IT WAS COUNTED.
    Eleven rows carry `untick=True`, but the loop guards on
    `hasattr(widget, "setChecked")` and three of them have no such method:
    `_outline_paint` is a NoScrollComboBox, `_agree` and `_differ` are
    NoScrollSliders. Driven against the live window, printing the type of
    every `untick=True` row. Those three keep their values and are only
    disabled, which is defensible — but the flag does nothing on those rows
    and three separate pieces of prose claimed otherwise.

    Driven, rings and grey axis ticked in CIELAB with the slot's file
    removed:

        refused   ticked=False enabled=True    <- only the refusal does this
        succeeded ticked=False enabled=False   <- correct in CIE XYZ

    ⚠ AND THE POSITIVE HALF IS WHY THIS TEST HAS TWO PARTS. Moving that call
    is easy to get wrong in the other direction: my first attempt landed it
    in `_on_white_changed` — two handlers share identical text — and left
    the space handler never clearing anything at all. Driving the REFUSAL
    alone would have called that a success.
    """
    import gamut_app
    from types import SimpleNamespace as NS

    def window(rebuild_says):
        done = []
        return NS(_apply_space_availability=lambda: done.append("cleared"),
                  _rebuild_reference=lambda: None,
                  _rebuild=lambda redraw=True: rebuild_says,
                  _put_settings_back=lambda: done.append("put back"),
                  _remember_settled=lambda: done.append("remembered"),
                  _redraw=lambda: None), done

    refused, done = window(False)
    gamut_app.GamutApp._on_space_changed(refused)
    assert "cleared" not in done, (
        "the controls were cleared for a space the shapes refused to move "
        "to, and nothing re-ticks them")
    assert "put back" in done and "remembered" not in done

    worked, done = window(True)
    gamut_app.GamutApp._on_space_changed(worked)
    assert "cleared" in done, (
        "the space changed and the controls that cannot follow it were left "
        "ticked and live")
    assert "remembered" in done and "put back" not in done


# --------------------------------------------------------------------------
# The finder's own control
#
# ⚠ TWICE NOW A HUNT HAS WALKED PAST `_mentions_rebuild`, AND BOTH TIMES THE
# WHOLE GATE STAYED GREEN. First a substring check missed
# `remake = self._rebuild; remake()`; then the attribute walk that replaced
# it missed `getattr(self, "_rebuild")()` — injected into a real route, the
# gate reported 1227 passed, the same count as the untouched baseline.
#
# A finder with no control is not an instrument, it is a hope. These are the
# evasions that have actually been tried, written as ordinary module-level
# functions so `inspect.getsource` can read them exactly as it reads a
# method. Anything new that gets past the finder belongs here the same day.
# --------------------------------------------------------------------------

def _evasion_direct(self):
    self._rebuild()


def _evasion_with_an_argument(self):
    self._rebuild(redraw=False)


def _evasion_aliased(self):
    remake = self._rebuild
    remake()


def _evasion_by_getattr(self):
    getattr(self, "_rebuild")()


def _evasion_by_a_named_string(self):
    which = "_rebuild"
    getattr(self, which)()


def _not_a_route_at_all(self):
    self._redraw()


def test_the_route_finder_cannot_be_walked_past():
    """Every way anybody has actually reached `_rebuild` is still found."""
    caught = {
        "written out": _evasion_direct,
        "with an argument": _evasion_with_an_argument,
        "through an alias": _evasion_aliased,
        "through getattr": _evasion_by_getattr,
        "through a named string": _evasion_by_a_named_string,
    }
    missed = [how for how, fn in caught.items() if not _mentions_rebuild(fn)]
    assert not missed, (
        f"the finder walks past {missed} — a route written that way rebuilds, "
        "forgets the refusal rule, and the whole suite stays green")
    assert not _mentions_rebuild(_not_a_route_at_all), (
        "the finder now calls everything a route, so it proves nothing about "
        "any of them")
