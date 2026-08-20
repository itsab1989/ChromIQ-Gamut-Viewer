"""Two rooms, side by side or one above the other — and the choice travels.

ASKED FOR IN AS MANY WORDS: "or can we give the option to choose whether the
user wants left/right or top/bottom split? with all the requirements for new
options (tooltip, export)".

Both arrangements are worth having and neither is a repair: whichever way
round the rooms are, each one pulls its own view back far enough that the
shape fits inside it (see `test_two_rooms_on_a_narrow_page`). Side by side
keeps the two shapes at the same height, which is what the eye needs to
compare how far each reaches; one above the other gives each the whole width,
which is what a tall narrow window has to spare.

WHAT THIS GUARDS, each with its failure direction:

  it is remembered      — or it goes back to side by side every session, and
                          a setting that will not stay is worse than none;
  it reaches the FILE   — the asymmetry this project has broken three times:
                          a control that works on screen and not in the page
                          somebody is sent;
  the hover is SHORT    — "those hover tooltips should be short and the
                          extended version would be behind the tooltip icons",
                          asked for in as many words. 200 characters is the
                          window's own limit;
  the ⓘ is long and says what it NEEDS — a control whose explanation does not
                          name its prerequisite sends somebody looking for a
                          setting that is not there yet.
"""
import pathlib
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_APP = (_ROOT / "python" / "gamut_app.py").read_text(encoding="utf-8")


def _two_figures():
    import ti3gamut
    from gamutview import build_gamut
    rng = np.random.default_rng(3)
    q = rng.normal(size=(300, 3))
    q /= np.linalg.norm(q, axis=1)[:, None]
    a = q * np.array([36, 58, 34])
    a[:, 0] = np.clip(a[:, 0] * 0.6 + 52, 5, 95)
    return [(n, ti3gamut.build_figure(
        [(n, build_gamut(a, input_space="lab"))], "")) for n in ("one", "two")]


def test_both_arrangements_reach_the_page():
    import ti3gamut
    figures = _two_figures()
    out = pathlib.Path(tempfile.mkdtemp())
    beside = ti3gamut.write_side_by_side_html(
        figures, out / "beside.html", stacked=False).read_text(encoding="utf-8")
    above = ti3gamut.write_side_by_side_html(
        figures, out / "above.html", stacked=True).read_text(encoding="utf-8")
    stacks = ".row  { flex-direction:column"
    assert stacks not in beside, "side by side is stacking the two rooms"
    assert stacks in above, (
        "'one above the other' wrote a page that still puts the rooms in a "
        "row — the choice does not reach the file anybody is sent")
    # AND NOT BY DOUBLING THE BRACES. The rule is interpolated into an
    # f-string, so `{{` reaches the page literally and the arrangement is
    # silently ignored — which is exactly what the first version did.
    assert "{{" not in above.split(stacks)[1][:200]


def test_the_window_hands_its_choice_to_the_writer():
    assert 'stacked=(self._rooms_way.currentData()' in _APP, (
        "the window no longer tells the writer which arrangement to use")


def test_the_choice_is_remembered():
    assert '("rooms_way", self._rooms_way, "combo", "beside")' in _APP, (
        "the arrangement is not in _persisted(), so it is forgotten between "
        "sessions and Reset cannot put it back")


def test_it_is_withheld_when_there_is_nothing_to_arrange():
    assert "self._rooms_row.setVisible(linked_useful)" in _APP, (
        "the chooser stays on screen with one shape open, where it can do "
        "nothing — which this window treats as worse than a missing control")


def test_the_hover_is_short_and_the_icon_is_long():
    import re
    hover = re.search(r'self\._rooms_way\.setToolTip\(\s*((?:"[^"]*"\s*)+)\)',
                      _APP)
    assert hover, "the arrangement chooser has no hover tooltip at all"
    words = "".join(re.findall(r'"([^"]*)"', hover.group(1)))
    assert 0 < len(words) <= 200, (
        f"the hover is {len(words)} characters; the window's limit is 200 and "
        f"the long version belongs behind the ⓘ")
    assert "Two rooms" in words, "the hover does not name what it needs"

    icon = _APP[_APP.index("rooms_hint = Hint("):
                _APP.index('rooms_hint.setObjectName("hint_rooms_way_hint")')]
    text = "".join(re.findall(r'"([^"]*)"', icon))
    assert len(text) > 600, (
        f"the explanation behind the ⓘ is only {len(text)} characters — the "
        f"long version is what the icon is for")
    assert "SIDE BY SIDE" in text and "ONE ABOVE THE OTHER" in text, (
        "the explanation does not say what each choice does")
    assert "needs Two rooms" in text, (
        "the explanation does not name its prerequisite, so somebody whose "
        "chooser is missing has no way to find out why")
    assert "saved page" in text, (
        "the explanation does not say the choice travels into a file")
