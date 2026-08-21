"""The lighting explanation may not promise what the sliders do not do.

It used to end: "Every one of them moves the picture as you drag." Measured in
the real window at the settings it opens with, that was false for two of the
seven: Roughness and Fresnel shape a specular highlight, and the shine opens
at 0.08 — which is indistinguishable from none at all.

    roughness moved end to end, shine 0.00:      0 px
                                shine 0.08:      0 px   ← what it opens with
                                shine 0.15:  1,552 px
                                shine 0.25: 15,110 px
                                shine 0.40: 189,384 px

The shine stays low on purpose: at 0.25 and above the shape washes towards
white, and this is a picture of what colours a paper can print. So the words
have to carry the condition instead — a control whose explanation promises
more than it does is worse than one with no explanation at all.

(The other four were a real fault and are fixed: the lamp was pinned to the
camera by a reach of 2000 — see `test_the_lamp_is_placed_on_two_scales_and_not_one`.)
"""
import pathlib

_APP = (pathlib.Path(__file__).resolve().parent / "gamut_app.py").read_text(
    encoding="utf-8")
_HINT = _APP[_APP.index("light_hint = Hint("):
             _APP.index('light_hint.setObjectName("hint_light_hint")')]


def test_it_no_longer_promises_that_every_slider_moves_the_picture():
    assert "Every one of them moves the picture as you drag" not in _HINT, (
        "the explanation promises that every lighting slider moves the "
        "picture as you drag, and at the settings the window opens with that "
        "is false for Roughness and for Fresnel")


def test_it_says_what_the_two_quiet_ones_need():
    words = _HINT.lower()
    assert "specular" in words and "roughness" in words and "fresnel" in words
    assert "quarter" in words or "up" in words, (
        "the explanation does not say how far Specular has to go before "
        "Roughness and Fresnel show — 'turn it up' with no number sends "
        "somebody hunting")
    assert "washes" in words or "white" in words, (
        "the explanation does not say why the shine is left low, so the "
        "first thing a reader does is turn it up and lose the colours")
