"""A page that fetches its viewer must have somewhere else to ask.

REPORTED FROM A REAL WINDOW: "web exports saved without the viewer give me an
info when opening and a button to try to fetch the viewer again. but this
never works for me. i only ever get this info but not the real view."

The obvious suspects were all cleared by measurement: the address answers with
HTTP 200 and 4,851,164 bytes, its integrity hash matches what the page demands
exactly, the host sends `access-control-allow-origin: *` even for the `null`
origin a file opened from disk has, and the retry's cache-busting query string
does not change the bytes or the hash.

WHAT IS LEFT is that a content blocker, a company proxy or a school network
refuses ONE ADDRESS, not the file — and the same file is served by other
hosts, byte for byte, so the page's own integrity hash guards a mirror exactly
as well. Asking the same host again, which is what the retry used to do, is
the definition of no answer.

⚠ THE SUCCESS PATH IS NOT TESTED HERE and cannot be: it needs the network.
What is tested is that the page carries more than one address, that they are
all the same version so one hash can cover them, and that the drawing happens
once and only once however many things notice the viewer arrive.
"""
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_DEMO = pathlib.Path(__file__).resolve().parent.parent / "demo"


@pytest.fixture(scope="module")
def page_without_the_viewer(tmp_path_factory):
    import ti3gamut
    from gamutview import build_gamut
    reading = _DEMO / "Glossy-paper.ti3"
    if not reading.is_file():
        pytest.skip("no demo paper to draw")
    shape = build_gamut(ti3gamut.read_measurement(reading).lab,
                        input_space="lab")
    out = tmp_path_factory.mktemp("noviewer") / "page.html"
    ti3gamut.write_html([("Glossy-paper", shape)], out, title="no viewer",
                        mode="dark", carry_viewer=False)
    return out.read_text(encoding="utf-8")


def test_the_page_really_does_have_to_fetch_its_viewer(page_without_the_viewer):
    # THE SETTING ITSELF, so this file cannot pass on a page that carries the
    # viewer inside it and never asks anybody for anything.
    body = page_without_the_viewer
    assert "cq-noviewer" in body, (
        "the page has no did-not-arrive notice — it is not a page that "
        "fetches its viewer, so nothing below is being tested")
    assert len(body) < 1_500_000, (
        f"the page is {len(body):,} characters; the viewer looks to be inside "
        f"it after all")


def test_it_carries_more_than_one_address(page_without_the_viewer):
    hosts = set(re.findall(r"https://([a-z0-9.\-]+)/[^\"']*plotly[^\"']*",
                           page_without_the_viewer))
    assert len(hosts) >= 2, (
        f"the page knows only {sorted(hosts)} — one blocked address and the "
        f"reader has no way through, which is the fault this guards")


def test_every_address_asks_for_the_same_version(page_without_the_viewer):
    """One integrity hash covers them all, or it covers none of them."""
    found = re.findall(r"plotly[.\-@]?(?:js@)?(\d+\.\d+\.\d+)",
                       page_without_the_viewer)
    assert found, "no version could be read out of any address"
    assert len(set(found)) == 1, (
        f"the addresses ask for different versions {sorted(set(found))}; the "
        f"page carries ONE integrity hash and the browser would refuse every "
        f"mirror that did not match it")


def test_the_retry_moves_on_rather_than_asking_the_same_host_again(
        page_without_the_viewer):
    body = page_without_the_viewer
    assert "hosts[(tries - 1) % hosts.length]" in body, (
        "the retry does not walk the list of addresses — pressing it again "
        "asks the host that has already refused")


def test_arriving_late_draws_the_picture_rather_than_uncovering_nothing(
        page_without_the_viewer):
    """Hiding the notice is half the job.

    When the viewer turns up LATE the inline call that draws has already run
    and thrown, so there is no picture waiting behind the notice — only the
    instructions for one. Taking the notice away then uncovers a blank page,
    which is worse than the notice was.
    """
    body = page_without_the_viewer
    came = body.find("window.cqViewerCame = function")
    assert came > 0, "the page has no cqViewerCame"
    ends = body.find("};", came)
    inside = body[came:ends]
    # ⚠ THE TEST HERE IS THE CONDITION, NOT THE WORD. Asking whether
    # "cq-draw" appears anywhere inside passes just as happily when the whole
    # branch has been turned off — measured: mutating the condition to
    # `if (false)` left every assertion in this file green.
    assert "if (!document.querySelector('.js-plotly-plot')) {" in inside, (
        "cqViewerCame does not draw when there is no picture yet, so a viewer "
        "that arrives late leaves a blank page")
    assert "var draw = document.getElementById('cq-draw');" in inside, (
        "cqViewerCame never reaches for the drawing instructions")
    assert "if (window.cqDrawn) return;" in inside, (
        "nothing stops cqViewerCame drawing twice — the watchdog polls every "
        "quarter second and the retry's onload fires as well, and drawing is "
        "not instant, so the second call would put a picture over the first")


def test_the_notice_names_the_address_it_could_not_reach(
        page_without_the_viewer):
    # BOTH: the address it started with, shown as soon as the notice opens,
    # and the one each press of the button moves on to.
    assert "It tried to fetch: " in page_without_the_viewer, (
        'the notice does not name the address it failed on, so "could not be '
        'reached" cannot be acted on by anybody')
    assert "It is trying: " in page_without_the_viewer, (
        "a retry does not say which address it has moved on to")
