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
    assert "var draw = document.querySelectorAll('script[data-cq-draw]');" \
        in inside, ("cqViewerCame never reaches for the drawing instructions")
    # ⚠ ALL OF THEM. `defer` on the viewer's tag means EVERY load comes
    # through here, so re-running only the first draw call would leave a
    # two-scene page with half a picture and nothing said about it.
    assert "for (var i = 0; i < draw.length; i++)" in inside, (
        "cqViewerCame runs one draw call, not every one — a page with two "
        "scenes in it would come out half drawn")
    assert "if (window.cqDrawn) return;" in inside, (
        "nothing stops cqViewerCame drawing twice — the watchdog polls every "
        "quarter second and the retry's onload fires as well, and drawing is "
        "not instant, so the second call would put a picture over the first")


def test_it_moves_on_without_being_asked(page_without_the_viewer):
    """A button is no use when the address does not refuse, it just hangs.

    Reported from a phone: "i still get this and nothing there changes when i
    click the button." Nothing fires when a request is black-holed rather than
    refused — no `onerror`, so the button stays disabled and pressing it only
    re-asks the address that is already hanging. The page now fetches the NEXT
    address on its own every twelve seconds until the list is done. Driven in
    a browser, touching nothing: cdn.plot.ly, then jsdelivr at about 12 s,
    then unpkg at about 24 s.
    """
    body = page_without_the_viewer
    assert "reaching >= hosts.length - 1" in body, (
        "the page never moves on by itself — a reader whose first address "
        "hangs is left pressing a button that cannot help")
    assert "'cq-next=' + reaching" in body, (
        "the page re-asks the same address rather than the next one")
    # ⚠ ONE FETCH AT A TIME, and this is the assertion that matters most.
    # The first version moved on after twelve seconds WHATEVER was happening,
    # and broke the page it was meant to mend: the viewer is about 5 MB, a
    # phone takes longer than that over it, so a second copy was started while
    # the first was still coming. Both arrived, the second re-initialised the
    # library under the first, and the picture vanished. Reported exactly so.
    assert "}, 12000);" not in body, (
        "the page is back on a SCHEDULE — it will start a second copy of the "
        "viewer while the first is still downloading, and the picture will "
        "appear and then vanish")
    assert "nxt.onerror = function () { inflight = false; nextHost('failed'); }" \
        in body, (
            "the next address is not chained to the previous one's failure")
    assert "if (window.Plotly || !waiting || inflight) return;" in body, (
        "nothing stops a second fetch while one is outstanding")


def test_the_first_failure_starts_the_walk_itself(page_without_the_viewer):
    """The tag that fails must ASK for the next address, not just say so.

    ⚠ THIS FILE WAS ENTIRELY GREEN WHILE THE WALK WAS DEAD CODE. The walk used
    to start from a record: the notice lived at the END of the body, so the
    tag's `onerror` ran before the div existed, `cqNoViewer` could only
    remember the failure in `cqNoViewerWanted`, and the note script read that
    record on the way past and moved on to the mirror.

    MOVING THE NOTICE ABOVE THE TAG SILENTLY KILLED IT. The div now exists
    when `onerror` fires, so `cqNoViewer` shows it and remembers nothing; the
    flag stays false, and the one line that reads it has already run. Driven
    in a real browser against a local server, first address refused outright:
    the notice appeared at 0.3 s and NOT ONE mirror was ever requested. Every
    assertion above passed on that page, because every word in it was right.

    So what is checked is the CALL, on the tag, where the failure happens.
    """
    body = page_without_the_viewer
    spot = body.find('src="https://cdn.plot.ly')
    assert spot > 0, "the page has no viewer tag to fail"
    tag = body[body.rfind("<script", 0, spot):body.index(">", spot)]
    assert "cqTryTheNext" in tag, (
        "the viewer's own tag does not start the walk when it fails — the "
        "second and third addresses are dead code until the last resort")
    # AND THE FUNCTION IT CALLS MUST BE DEFINED BEFORE THE TAG, or the call is
    # a no-op that no string test would ever notice.
    assert 0 < body.find("window.cqTryTheNext = nextHost;") < spot, (
        "cqTryTheNext is defined after the tag that calls it, so the first "
        "failure cannot reach it")


def test_the_viewers_tag_does_not_block_the_parser(page_without_the_viewer):
    """An address that never answers must not stop the rest of the page.

    A plain `<script src>` blocks the parser until the request settles, and an
    address that hangs settles when it feels like it. Measured in a real
    browser with a first address that answered nothing for six seconds:
    `document.readyState` stuck at "loading" the whole time and `#cq-draw` was
    NOT IN THE DOM — so a mirror arriving during the wait had nothing to draw.
    With `defer` the same measurement parsed the rest at 39 ms and reached
    "interactive".
    """
    body = page_without_the_viewer
    spot = body.find('src="https://cdn.plot.ly')
    assert spot > 0, "the page has no viewer tag"
    tag = body[body.rfind("<script", 0, spot):body.index(">", spot)]
    assert re.search(r"\s(defer|async)[\s>=]", tag + ">"), (
        "the viewer's tag blocks the parser — one address that hangs leaves "
        "the drawing instructions unparsed and the page blank with no way "
        "back")


def test_the_notice_names_the_address_it_could_not_reach(
        page_without_the_viewer):
    # BOTH: the address it started with, shown as soon as the notice opens,
    # and the one each press of the button moves on to.
    assert "It tried to fetch: " in page_without_the_viewer, (
        'the notice does not name the address it failed on, so "could not be '
        'reached" cannot be acted on by anybody')
    assert "It is trying: " in page_without_the_viewer, (
        "a retry does not say which address it has moved on to")


def test_the_notice_does_not_lean_on_the_hidden_attribute(page_without_the_viewer):
    """`hidden` LOSES to an inline `display`, and that hid the picture.

    The notice was written `<div id="cq-noviewer" hidden style="…display:
    flex;…">`. The browser's own rule is `[hidden] { display: none }` at
    ordinary specificity and an inline style beats it — so the notice was on
    screen from the moment the parser reached it, for ever, and `n.hidden =
    true` was a no-op. The picture was drawn and intact BEHIND it: measured,
    the plot at 1,314 ms and the notice covering it at 1,365 ms.

    ⚠ EVERY OTHER TEST OF THIS PAGE STILL PASSED, because they ask whether
    words appear in the HTML and every word was right. Only rendering the page
    can see it, and that is `scripts/audit_the_notice_really_hides.py` — this
    is the cheap half, watching the shape of the tag.
    """
    body = page_without_the_viewer
    spot = body.find('id="cq-noviewer"')
    assert spot > 0, "the notice is not in the page at all"
    tag = body[spot:body.index(">", spot)]
    assert " hidden" not in tag, (
        "the notice is using the `hidden` attribute again, which an inline "
        "`display` overrides — it will sit on top of the picture for ever")
    assert "display:none" in tag.replace(" ", ""), (
        "the notice does not start hidden by its own style, so it is on "
        "screen before anything decides whether it should be")


def test_a_two_room_page_can_be_saved_without_the_viewer_too(tmp_path):
    """The tick was offered on a two-room page and quietly ignored.

    `write_side_by_side_html` wrote the library into the file whatever the box
    said — five megabytes either way — and never added the did-not-arrive
    notice, because it never asked. A control offered where it cannot act is
    exactly what this window keeps taking out, and this one had been lying for
    as long as two rooms have existed.

    Measured through the real writer: 5,149 kB carrying it, 419 kB fetching
    it, and the rendered page draws BOTH rooms with the movement strip.
    """
    import ti3gamut
    from gamutview import build_gamut
    from references import reference_gamut
    paper_file = _DEMO / "Glossy-paper.ti3"
    if not paper_file.is_file():
        pytest.skip("no demo paper")
    paper = build_gamut(ti3gamut.read_measurement(paper_file).lab,
                        input_space="lab")
    srgb = reference_gamut("sRGB", steps=16)
    # (caption, figure) pairs, which is what the writer walks
    pages = [("Glossy-paper",
              ti3gamut.build_figure([("Glossy-paper", paper)], "Glossy-paper")),
             ("sRGB", ti3gamut.build_figure([("sRGB", srgb)], "sRGB"))]
    sizes = {}
    for carry in (True, False):
        out = tmp_path / f"rooms-{carry}.html"
        ti3gamut.write_side_by_side_html(pages, out, carry_viewer=carry)
        sizes[carry] = out.stat().st_size
        body = out.read_text(encoding="utf-8")
        assert body.count("Plotly.newPlot") >= 2, (
            f"carry={carry}: only {body.count('Plotly.newPlot')} picture(s) — "
            f"a two-room page must draw both rooms")
        assert ("cq-noviewer" in body) is (not carry), (
            f"carry={carry}: the did-not-arrive notice is "
            f"{'present' if 'cq-noviewer' in body else 'missing'}, which is "
            f"backwards — only a page that FETCHES the viewer needs it")
    assert sizes[False] * 4 < sizes[True], (
        f"saving without the viewer gave {sizes[False]:,} bytes against "
        f"{sizes[True]:,} carrying it — the tick is being ignored again")
