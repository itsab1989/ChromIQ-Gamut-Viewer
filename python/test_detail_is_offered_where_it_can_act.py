"""Detail is live only where it changes something.

WHAT IT ACTUALLY GOVERNS, measured in the real window with the slider taken
from 20 to 40:

    the file you opened   an ICC profile      4,926 faces both times
                          a measured chart      978 faces both times
    the comparison        sRGB              4,332 -> 18,252 faces

So it rebuilds the shape you compare AGAINST, and only when that is one of the
named colour spaces — the "icc" branch of _on_compare_changed calls _build_one,
which takes no step count, and "everything the eye can see" is a fixed shape.
It stayed live in all of those states, inviting a drag that could not answer,
which is the fault this window has fixed three times elsewhere.

WHY A TEST AND NOT ONLY AN AUDIT: dimming a control on a PARAPHRASE of the
drawing's condition is how the drift marker's tick was broken in four states
at once (see _apply_closing_availability). Both directions are checked here —
that it dims where it cannot act, and that it stays live where it can.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


class _Slider:
    def __init__(self):
        self.on = True
        self.tip = ""

    def setEnabled(self, value):
        self.on = bool(value)

    def isEnabled(self):
        return self.on

    def setToolTip(self, text):
        self.tip = text

    def toolTip(self):
        return self.tip


class _Compare:
    def __init__(self, data):
        self.data = data

    def currentData(self):
        return self.data


class _Window:
    """Only the parts _apply_detail_availability reads."""

    def __init__(self, choice):
        self._detail = _Slider()
        self._detail_lbl = _Slider()
        self._compare = _Compare(choice)


def _ask(choice):
    import gamut_app
    window = _Window(choice)
    gamut_app.GamutApp._apply_detail_availability(window)
    return window._detail


def test_it_is_live_for_every_named_space():
    from references import REFERENCE_SPACES
    assert len(REFERENCE_SPACES) >= 3, "too few spaces to be a real check"
    for name in REFERENCE_SPACES:
        slider = _ask(("space", name))
        assert slider.isEnabled(), f"dimmed for {name}, which it does rebuild"
        assert slider.toolTip(), f"no hover for {name}"


def test_it_dims_where_it_can_do_nothing():
    for choice, expect in ((None, "Compare with"),
                           (("icc", None), "profile"),
                           (("visible", None), "eye can see")):
        slider = _ask(choice)
        assert not slider.isEnabled(), f"live for {choice}, where it does nothing"
        assert expect in slider.toolTip(), (
            f"the hover for {choice} does not say why: {slider.toolTip()!r}")


def test_every_hover_stays_short():
    # The rule asked for in as many words: hovers stay short, the long version
    # goes behind the ⓘ. 200 characters is the window's own limit.
    import gamut_app
    for choice in (None, ("icc", None), ("visible", None), ("space", "sRGB")):
        tip = _ask(choice).toolTip()
        assert 0 < len(tip) <= gamut_app._HOVER_LIMIT, (
            f"{choice}: {len(tip)} characters")


def test_the_label_dims_with_it():
    import gamut_app
    window = _Window(None)
    gamut_app.GamutApp._apply_detail_availability(window)
    assert not window._detail_lbl.isEnabled(), (
        "the number beside a dimmed slider must dim with it, or the row reads "
        "as half alive")
