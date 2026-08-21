"""Every way of drawing the chart's patches must change something.

`scripts/drive_all_combinations.py` crosses all of these against each other
and asks what must NOT change: no look setting may move a dot, no count may
depend on how anything is drawn. That is the half that catches a look setting
reaching into the measurement. The other half — that each setting reaches the
PICTURE at all — was unasked, and this week has twice shown what that costs: a
tick that drew nothing until another control was touched, and four sliders
whose values reach the trace and move no pixel.

⚠ AND THE FIRST ATTEMPT AT THIS REPORTED A FAULT THAT WAS NOT THERE. It
compared traces by a 200-character slice of their marker, and a dot's size
sits beyond that, so "dot size 3.2 → 10" came back as NOTHING CHANGED while
the figure plainly carried `marker.size=3.2` then `10.0`. Fixed-size slices
have now said "not there" about something plainly there four times in this
project; this compares whole figures.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"

#: One change per setting, away from the middle of its range so the picture
#: has somewhere to go.
CHANGES = [
    ("the skin over the patches", dict(skin="solid")),
    ("the skin drawn as an outline", dict(skin="outline")),
    ("no skin at all", dict(skin="none")),
    ("the skin in the colours of the patches", dict(skin_colour="patches")),
    ("the skin in the accent colour", dict(skin_colour="accent")),
    ("how solid the skin is", dict(skin_opacity=1.0)),
    ("how big the dots are", dict(dot_size=10.0)),
    ("how solid the dots are", dict(dot_opacity=0.1)),
    ("how big the out-of-reach dots are", dict(out_dot_size=14.0)),
    ("how solid the out-of-reach dots are", dict(out_dot_opacity=0.1)),
    ("whether what is out of reach is shown", dict(show_outside=False)),
    ("whether what is within is shown", dict(show_inside=False)),
]

BASE = dict(skin="mesh", skin_colour="grey", skin_opacity=0.30,
            dot_size=3.2, dot_opacity=1.0, out_dot_size=4.0,
            out_dot_opacity=1.0, show_outside=True, show_inside=True,
            accent="#22d3aa")


@pytest.fixture(scope="module")
def drawn():
    import chart as cm
    import ti3gamut
    from gamutview import build_gamut
    chart_file = _DEMO / "verification-chart-480.ti1"
    profile = _DEMO / "Glossy-paper.icc"
    paper_file = _DEMO / "Matte-paper.ti3"
    for f in (chart_file, profile, paper_file):
        if not f.is_file():
            pytest.skip(f"no {f.name} to draw with")
    c = cm.read_chart(chart_file)
    placed = cm.through_profile(c, profile)
    lab = placed.under("D50")
    device = cm.device_positions(c)
    m = ti3gamut.read_measurement(paper_file)
    paper = build_gamut(m.lab, input_space="lab", space="lab",
                        white_point="D50")
    outside = cm.outside_report(lab, paper).beyond
    # A CHART WITH NOTHING IN IT, OR WITH NOTHING OUT OF REACH, WOULD PASS
    # EVERY LINE BELOW. Both halves have to be there for the settings about
    # each half to have anything to change.
    assert len(lab) > 100, f"only {len(lab)} patches to draw"
    assert 0 < int(outside.sum()) < len(lab), (
        f"{int(outside.sum())} of {len(lab)} patches are out of reach — with "
        f"all or none of them beyond the paper, half these settings have "
        f"nothing to act on and this test proves nothing")

    def picture(**changes):
        figure = ti3gamut.build_figure(
            [], "t", chart=("c", lab, outside, device),
            chart_look=dict(BASE, **changes))
        return json.loads(figure.to_json())["data"]

    return picture


@pytest.mark.parametrize("what,change", CHANGES,
                         ids=[c[0].replace(" ", "-") for c in CHANGES])
def test_the_setting_reaches_the_picture(drawn, what, change):
    before, after = drawn(), drawn(**change)
    assert before != after, (
        f"changing {what} ({change}) draws exactly the same figure — the "
        f"control is there and nothing behind it")


def test_the_chart_really_is_drawn_to_begin_with(drawn):
    traces = drawn()
    assert len(traces) >= 3, (
        f"only {len(traces)} traces in the chart's picture — if it draws "
        f"almost nothing, 'this setting changed something' is a claim about "
        f"nothing")
