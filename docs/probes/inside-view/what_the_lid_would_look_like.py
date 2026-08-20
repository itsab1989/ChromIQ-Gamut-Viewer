"""Basti's idea for closing the opening, drawn rather than measured.

He said it in one line: "can't this be calculated from the other shape that is
subtracted from the first one so to say? ... its shell would be what closes the
gap or am i wrong?"

He is not wrong, and it has been measured -- 0 triangles dropped between the
two pieces, their boundaries a median 2.4 Lab apart. But those are numbers
about a shape nobody has seen, and the question they are meant to settle is
"does this look right", which numbers cannot answer.

So this draws it. Three pictures, same shapes, same camera:

    as it ships     the standing remainder, open, its far wall lit like an
                    outside -- the thing reported four times
    his lid         the same, with the OTHER shell's inside part drawn in as
                    the missing surface
    the lid alone   so it is clear what has been added

The lid is his idea taken literally: the opening was made by removing the part
of the paper that agrees with sRGB, so what closes it is the piece of sRGB's
own shell that lies inside the paper. The two share the crossing curve by
construction, which is why the boundaries measure 2.4 Lab apart rather than
anything needing repair.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

FORK = pathlib.Path("/Users/Basti/develop/ChromIQ-Gamut-Viewer/fork")
sys.path.insert(0, str(FORK / "python"))

import numpy as np                                          # noqa: E402
import plotly.graph_objects as go                           # noqa: E402
import ti3gamut                                             # noqa: E402
from gamutview import build_gamut                           # noqa: E402
from playwright.sync_api import sync_playwright             # noqa: E402
from references import reference_gamut                      # noqa: E402

OUT = pathlib.Path("/private/tmp/claude-502/-Users-Basti-develop-ChromIQ/"
                   "b54296f1-3089-4f47-9963-bfd3535a2eb9/scratchpad/lid")

#: LOOKING INTO THE HOLE, which is the whole point. The notes measured that at
#: the default camera 87% of the standing shell's pixels are its interior; a
#: camera that does not see inside would show the lid making no difference and
#: prove nothing either way.
CAMERAS = {
    "from the front": dict(eye=dict(x=1.5, y=1.3, z=0.7)),
    "from above": dict(eye=dict(x=0.6, y=0.6, z=2.0)),
    "from below": dict(eye=dict(x=1.1, y=-1.4, z=-0.9)),
}

#: A colour that says "this is not a measurement, it is the cut". Neutral, and
#: darker than either shape so it reads as a surface rather than as more paper.
LID = "rgb(96,96,104)"


def the_pair():
    f = FORK / "demo" / "Glossy-paper.ti3"
    return [("Glossy-paper",
             build_gamut(ti3gamut.read_measurement(f).lab, input_space="lab")),
            ("sRGB", reference_gamut("sRGB", steps=20))]


def pieces():
    """The standing remainder, and the lid that would close it."""
    pair = the_pair()
    cut, splits, stands, _lost = ti3gamut.recut_where_they_part(pair)
    (name_a, a), (name_b, b) = cut
    standing = np.asarray(splits[0], bool)
    agreeing = ~np.asarray(splits[1], bool)
    print(f"  {name_a}: {standing.sum()} of {len(standing)} triangles stand "
          f"out and are what you see at agreement 0%")
    print(f"  {name_b}: {agreeing.sum()} of {len(agreeing)} triangles lie "
          f"inside it — the lid")
    return (name_a, a, standing), (name_b, b, agreeing)


def mesh(gamut, faces, name, colours=None, colour=None, opacity=1.0):
    v = np.asarray(gamut.vertices, float)
    f = np.asarray(gamut.faces, int)[faces]
    kw = dict(x=v[:, 1], y=v[:, 2], z=v[:, 0],
              i=f[:, 0], j=f[:, 1], k=f[:, 2],
              name=name, opacity=opacity, flatshading=False,
              lighting=dict(ambient=0.55, diffuse=0.75, specular=0.12,
                            roughness=0.85, fresnel=0.1),
              lightposition=dict(x=120, y=-80, z=180), showscale=False)
    if colours is not None:
        kw["vertexcolor"] = colours
    else:
        kw["color"] = colour
    return go.Mesh3d(**kw)


def own_colours(gamut):
    """The colour each corner stands for — carried by the shape itself.

    Taken from the gamut rather than worked out again, because the re-cut
    inserts new corners and gives them their colours; recomputing would be a
    second implementation that could disagree with the one on screen.
    """
    rgb = np.clip(np.asarray(gamut.colors, float), 0, 1)
    return [f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
            for r, g, b in rgb]


def a_page(where, tag, traces, camera):
    fig = go.Figure(data=traces)
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#111", plot_bgcolor="#111",
        margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
        scene=dict(aspectmode="data",
                   xaxis=dict(title="a*"), yaxis=dict(title="b*"),
                   zaxis=dict(title="L*"),
                   camera=dict(center=dict(x=0, y=0, z=0),
                               up=dict(x=0, y=0, z=1), **camera)))
    out = where / f"{tag}.html"
    fig.write_html(str(out), include_plotlyjs=True)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    (name_a, a, standing), (name_b, b, agreeing) = pieces()
    paper_colours = own_colours(a)

    open_shell = mesh(a, standing, name_a, colours=paper_colours)
    lid = mesh(b, agreeing, "the lid", colour=LID)

    with tempfile.TemporaryDirectory() as tmp:
        where = pathlib.Path(tmp)
        with sync_playwright() as play:
            browser = play.chromium.launch()
            for view, camera in CAMERAS.items():
                short = view.replace(" ", "-")
                for tag, traces in (
                        ("1-as-it-ships", [open_shell]),
                        ("2-with-his-lid", [open_shell, lid]),
                        ("3-the-lid-alone", [lid])):
                    page = a_page(where, f"{tag}-{short}", traces, camera)
                    tab = browser.new_page(
                        viewport={"width": 900, "height": 760})
                    tab.goto(page.resolve().as_uri())
                    tab.wait_for_selector(".plotly-graph-div", timeout=40000)
                    tab.wait_for_timeout(5000)
                    tab.locator(".plotly-graph-div").first.screenshot(
                        path=str(OUT / f"{short}--{tag}.png"))
                    tab.close()
                print(f"  drawn {view}")
            browser.close()
    print(f"\n  pictures in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
