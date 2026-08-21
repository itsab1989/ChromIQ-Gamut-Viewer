"""Roughness and Fresnel dim while there is no highlight for them to shape.

This window's own rule, applied twice before: a control offered where it
cannot act is worse than one that is not there — it invites a drag and answers
with nothing, and a reader cannot tell that from a fault.

Roughness and Fresnel shape a SPECULAR highlight. Measured in the real window,
roughness dragged from one end to the other:

    shine 0.00:       0 px      shine 0.25:  15,110 px
    shine 0.08:       0 px  ←   shine 0.40: 189,384 px
    shine 0.15:   1,552 px      shine 1.00: 205,505 px

0.08 is what the window opens with, and the shine is left low on purpose: past
about a quarter the shape washes towards white and the colours lose their
strength, which a picture of what a paper can print must never do. So these
two spend most of their life inert, and the honest treatment is to say so
where the reader is looking.

Driven in the real window afterwards: dim at 0.00, 0.08 and 0.14 with the
hover explaining what to do, live at 0.15 and 0.40, and the other five
lighting sliders never touched.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


class _Row:
    def __init__(self):
        self.on = True

    def setEnabled(self, value):
        self.on = bool(value)

    def isEnabled(self):
        return self.on


class _Slider:
    def __init__(self):
        self.tip = ""

    def setToolTip(self, text):
        self.tip = text

    def toolTip(self):
        return self.tip


class _Window:
    """Just enough window for the rule to run against."""

    def __init__(self, shine):
        import gamut_app
        # The line itself comes from the real class, so this stub cannot
        # quietly test a different threshold from the one the window uses.
        self.NO_SHINE_TO_SHAPE = gamut_app.GamutApp.NO_SHINE_TO_SHAPE
        self._keys = [k for k, *_ in gamut_app.LIGHT_CONTROLS]
        self._light_row_of = {k: _Row() for k in self._keys}
        self._light_sliders = {k: (_Slider(), 0.0, 1.0) for k in self._keys}
        self._shine = shine

    def _light_value(self, key):
        return self._shine if key == "specular" else 0.5


def _ran(shine):
    import gamut_app
    w = _Window(shine)
    gamut_app.GamutApp._apply_shine_availability(w)
    return w


def test_they_dim_at_the_shine_the_window_opens_with():
    import gamut_app
    opens = dict((k, start) for k, _l, _lo, _hi, start
                 in gamut_app.LIGHT_CONTROLS)["specular"]
    w = _ran(opens)
    for key in ("roughness", "fresnel"):
        assert not w._light_row_of[key].isEnabled(), (
            f"{key} is live at the shine the window opens with ({opens}), "
            f"where dragging it from one end to the other changes not one "
            f"pixel")
        tip = w._light_sliders[key][0].toolTip()
        assert tip and len(tip) <= 200, (
            f"{key} is dim with a hover of {len(tip)} characters — the "
            f"window's limit is 200 and a dim control with no hover says "
            f"nothing at all")
        assert "Specular" in tip, f"{key}'s hover does not name what it needs"


def test_they_come_back_when_there_is_a_highlight():
    w = _ran(0.4)
    for key in ("roughness", "fresnel"):
        assert w._light_row_of[key].isEnabled(), (
            f"{key} is still dim at a shine of 0.4, where it moves the "
            f"picture by nearly two hundred thousand pixels")
        assert not w._light_sliders[key][0].toolTip(), (
            f"{key} keeps its 'nothing to shape yet' hover after the shine "
            f"arrives")


def test_the_five_that_always_act_are_never_dimmed():
    for shine in (0.0, 0.08, 0.4, 1.0):
        w = _ran(shine)
        for key in ("ambient", "diffuse", "specular", "direction", "height"):
            assert w._light_row_of[key].isEnabled(), (
                f"{key} was dimmed at a shine of {shine}; only the two that "
                f"shape the highlight wait for one")


def test_the_line_is_drawn_where_it_was_measured():
    import gamut_app
    line = gamut_app.GamutApp.NO_SHINE_TO_SHAPE
    assert 0.0 < line <= 0.2, (
        f"the line between 'no highlight to shape' and 'a highlight' is at "
        f"{line} — measured, roughness does nothing up to 0.08 and little at "
        f"0.15, so anything outside 0 to 0.2 is not what was measured")
