"""A saved page tells the browser its colour before it can read any CSS.

WHY. Opening one and watching the frames every 50 ms:

    t+0.06s   100% WHITE     <- the browser's own blank canvas
    t+0.51s   100% dark      <- the page's own style has arrived
    t+0.98s   the shape

The style is in the head all along, and the browser cannot obey it until it
has parsed past five megabytes of inlined viewer. `color-scheme` is the one
thing it acts on before CSS: it decides what the canvas is painted before
anything else exists. Measured with it on the same page: 0% white in the
first frame.

THE TAG GOES BY THE PAGE'S OWN BACKGROUND, not by the name of a mode, so a
colouring added later cannot forget to appear in a list.
"""
import pathlib
import re
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


@pytest.fixture(scope="module")
def one_shape():
    import ti3gamut
    from gamutview import build_gamut
    where = _DEMO / "Glossy-paper.ti3"
    if not where.is_file():
        pytest.skip("no demo paper")
    m = ti3gamut.read_measurement(where)
    return [("Glossy", build_gamut(np.asarray(m.lab, float), input_space="lab",
                                   drive_values=np.asarray(m.device, float)))]


def _page(one_shape, tmp_path, mode):
    import ti3gamut
    out = tmp_path / f"{mode}.html"
    ti3gamut.write_html(one_shape, out, "t", mode=mode)
    return out.read_text(encoding="utf-8", errors="replace")


def test_every_colouring_says_what_it_is(one_shape, tmp_path):
    import ti3gamut
    for mode in ("dark", "light"):
        page = _page(one_shape, tmp_path, mode)
        said = re.search(r'<meta name="color-scheme" content="(\w+)">', page)
        assert said, f"{mode}: the page never says what to paint"
        background = ti3gamut.static_palette(mode)["page"]
        want = "dark" if ti3gamut._looks_dark(background) else "light"
        assert said.group(1) == want, (
            f"{mode}: page background {background} but it asks for "
            f"{said.group(1)}")


def test_it_comes_before_the_viewer(one_shape, tmp_path):
    """After the five megabytes it is useless: that wait is what it covers."""
    page = _page(one_shape, tmp_path, "dark")
    at = page.index('name="color-scheme"')
    charset = page.index("charset")
    assert 0 < at - charset < 120, "it must sit beside the charset, at the top"
    script = page.find("<script")
    assert script < 0 or at < script, "it arrives after the viewer's script"


def test_the_brightness_is_read_from_the_colour():
    """Both directions, so the rule cannot be right by luck."""
    import ti3gamut
    assert ti3gamut._looks_dark("#111111")
    assert ti3gamut._looks_dark("#000")
    assert not ti3gamut._looks_dark("#efebe6")
    assert not ti3gamut._looks_dark("#fff")


def test_it_is_not_added_twice(one_shape, tmp_path):
    page = _page(one_shape, tmp_path, "dark")
    assert page.count('name="color-scheme"') == 1


# ---------------------------------------------------------------------------
# AND EVERY PAGE THAT SHIPS, not only the one this file writes. The same
# one-line declaration needed FOUR homes before every page had it: the main
# writer, the two-views writer, the side-by-side writer, and the run's own
# page in gamut_app. Nothing in the code makes those four visible to each
# other, and a fix in the obvious place looked complete at 19 pages of 25.
# ---------------------------------------------------------------------------


def test_every_showcase_page_says_what_to_paint():
    pages = sorted((pathlib.Path(__file__).resolve().parent.parent
                    / "docs" / "pages").glob("*.html"))
    if not pages:
        pytest.skip("no showcase pages built here")
    # A handful would mean the folder is half-built, and "all of them carry
    # it" would then be a promise about almost nothing.
    assert len(pages) >= 10, f"only {len(pages)} pages to check"
    missing = [p.name for p in pages
               if 'name="color-scheme"' not in
               p.read_text(encoding="utf-8", errors="replace")[:4000]]
    assert not missing, (
        "these pages never tell the browser what to paint, so they flash "
        "white before they draw: " + ", ".join(missing))
