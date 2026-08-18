"""The saved page's ΔE threshold, RUN rather than read.

WHY THIS FILE EXISTS. The control that hides the colours which barely moved
lives as JavaScript inside the written page, where the Python suite cannot see
it -- and it has now had five faults, every one of them found by a person
looking at a published page rather than by a test:

  * it read the packed arrays instead of the decoded ones, built nothing at
    all, and reported "nan drawn";
  * the direction view filtered the drawn values but not the ΔEs they were
    paired with;
  * its readout said "everything" while nothing was hidden -- the object of
    the label to its left, which on a narrow window wrapped away from it and
    sat alone: "with nothing hidden there is the word everything in the middle
    of nowhere";
  * the counts in the key went stale, so "yellows — 134" stood over a single
    drawn dot;
  * its top end emptied the picture completely -- "729 of 729 colours ... are
    not drawn" over bare axes.

Asserting that the source contains a particular line would catch none of
those. So the script is lifted out of the page it is written into, given a
stand-in page and drawing library, and RUN, on traces this project's own
figure builder produced. What is checked is what the reader would see.

Node is used because it is the only JavaScript engine that can be relied on
here; where there is none, the file skips rather than pretending.
"""
import json
import shutil
import subprocess

import numpy as np
import pytest

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="no JavaScript engine")


def _traces(seed=7, n=360):
    """A split drift cloud, built by the real thing.

    Written by hand at first, which proved the harness and nothing else: the
    shape of a trace -- where the ΔE sits in customdata, what the name looks
    like, whether the colours are per-point -- is exactly what the control
    depends on and exactly what a hand-written stand-in gets to invent.
    """
    import ti3gamut

    rng = np.random.default_rng(seed)
    lab = np.column_stack([rng.uniform(20, 92, n), rng.uniform(-60, 60, n),
                           rng.uniform(-60, 60, n)])
    de = rng.uniform(0.65, 3.03, n)
    de[0] = 3.03                                   # one clear biggest mover
    fig = ti3gamut.build_figure([], "x", mode="dark", space="lab", grid=True,
                                drift=(lab, de, "d", None, True))
    out = []
    for t in fig.data:
        d = t.to_plotly_json()
        marker = d.get("marker") or {}
        def listy(v):
            return (np.asarray(v).tolist() if v is not None
                    and not isinstance(v, (str, int, float)) else v)
        out.append({"name": d.get("name"), "x": listy(d.get("x")),
                    "y": listy(d.get("y")), "z": listy(d.get("z")),
                    "customdata": listy(d.get("customdata")),
                    "marker": {"color": listy(marker.get("color")),
                               "size": listy(marker.get("size"))}})
    return out, de


def _script() -> str:
    """The control's own JavaScript, out of the page it is written into."""
    import ti3gamut

    page = ti3gamut._threshold_control("<html><body></body></html>", "dark")
    at = page.index("<script>") + len("<script>")
    return page[at:page.index("</script>", at)]


def _run(traces, positions):
    """Load the control on these traces, then put its slider at each position.

    *positions* are 0..1 across the travel, so a test can say "the far end"
    without knowing what the ends turned out to be.
    """
    stub = """
var TRACES = %s, POSITIONS = %s;
var says = {textContent: ""}, note = {textContent: ""};
var slider = {min: 0, max: 0, value: 0, _on: [],
  addEventListener: function (k, f) { this._on.push(f); },
  fire: function () { this._on.forEach(function (f) { f(); }); }};
var box = {hidden: true, querySelector: function (sel) {
  if (sel.indexOf('"cut"') >= 0) return slider;
  if (sel.indexOf("cutsays") >= 0) return says;
  return note; }};
var gd = {data: TRACES, _fullData: TRACES};
global.document = {
  querySelector: function (s) { return s === ".js-plotly-plot" ? gd : null; },
  getElementById: function (id) { return id === "cq-cut" ? box : null; }};
global.window = {setTimeout: setTimeout, Plotly: {restyle: function (g, up, at) {
  var t = g._fullData[at[0]];
  ["x", "y", "z", "customdata", "name"].forEach(function (k) {
    if (up[k] !== undefined) t[k] = up[k][0]; });
  if (up["marker.color"]) t.marker.color = up["marker.color"][0];
  if (up["marker.size"]) t.marker.size = up["marker.size"][0];
}}};

%s

function state() {
  var drawn = 0, names = [];
  gd._fullData.forEach(function (t) {
    drawn += (t.x || []).length;
    names.push({name: t.name, n: (t.x || []).length});
  });
  return {says: says.textContent, note: note.textContent, drawn: drawn,
          names: names, built: !box.hidden,
          slider: {min: +slider.min, max: +slider.max, value: +slider.value}};
}
var seen = [state()];
POSITIONS.forEach(function (p) {
  slider.value = Math.round(+slider.min + p * (+slider.max - +slider.min));
  slider.fire();
  seen.push(state());
});
console.log(JSON.stringify(seen));
""" % (json.dumps(traces), json.dumps(list(positions)), _script())
    done = subprocess.run([NODE, "-e", stub], capture_output=True, text=True,
                          timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@needs_node
def test_the_control_builds_itself_and_hides_nothing_to_start_with():
    traces, de = _traces()
    at_rest = _run(traces, [])[0]
    assert at_rest["built"], "the control never appeared"
    assert at_rest["drawn"] == len(de), "it hid colours before it was touched"
    # THE READOUT SAYS WHAT THE STATE IS, not what the label to its left is
    # missing. See this file's opening note.
    assert at_rest["says"] == "nothing hidden"
    assert "everything" not in at_rest["says"]
    # AND THE LINE UNDER IT IS NEVER EMPTY. It was, until the first drag, so
    # the page jumped by the height of a line the moment anybody touched the
    # slider -- and a page somebody else sent you is worth telling outright
    # that nothing has been left out of it.
    assert str(len(de)) in at_rest["note"] and at_rest["note"].strip()


@needs_node
def test_the_far_end_leaves_the_biggest_mover_standing():
    """A slider position that empties the picture is a broken-looking page.

    The window has always truncated here and this copy rounded up, so its last
    step hid all 729 of 729 colours and left bare axes.
    """
    traces, de = _traces()
    end = _run(traces, [1.0])[-1]
    assert end["drawn"] >= 1, "the far end of the slider empties the picture"
    # AND IT IS STILL AN END WORTH DRAGGING TO: what survives is the handful
    # at the top of the range, not most of the cloud. A share rather than a
    # count, because the count depends on how many colours the chart had.
    assert end["drawn"] < 0.05 * len(de), "the far end hides almost nothing"
    # AND IT DOES NOT REPEAT THE WORD THE LABEL ALREADY SAID: the row reads
    # "Hide anything under ——●  ΔE 3.0", not "under ... under".
    assert end["says"] == f"ΔE {end['slider']['value'] / 10:.1f}"
    assert f"of {len(de)} colours moved by less than" in end["note"]


@needs_node
def test_the_key_counts_what_is_drawn_now_and_not_what_it_used_to_be():
    """"yellows — 134" over one drawn dot is the key telling a lie."""
    traces, _de = _traces()
    rest, middle, end = _run(traces, [0.6, 1.0])

    for row in rest["names"]:
        # AT REST THE PLAIN COUNT, because "134 of 134" is noise.
        assert " of " not in row["name"], row["name"]
        assert row["name"].endswith(f"— {row['n']}"), row["name"]

    whole = {r["name"].split(" — ")[0]: r["n"] for r in rest["names"]}
    moved = [r for r in middle["names"] if r["n"]]
    assert moved, "the middle of the travel hid every colour"
    thinned = 0
    for row in moved:
        family = row["name"].split(" — ")[0]
        if row["n"] == whole[family]:
            # A FAMILY WITH NOTHING TAKEN OUT OF IT SAYS SO PLAINLY. "11 of
            # 11" is a number written twice, and one-patch families would
            # never read any other way.
            assert row["name"] == f"{family} — {row['n']}", row["name"]
            continue
        thinned += 1
        assert row["name"] == f"{family} — {row['n']} of {whole[family]}", (
            f"the key says {row['name']!r} over {row['n']} drawn dots")
    assert thinned, "nothing was thinned, so the count was never under test"
    assert any(r["n"] for r in end["names"])


@needs_node
def test_sliding_back_brings_every_colour_and_every_count_back():
    """Nothing is thrown away — the promise the control's docstring makes."""
    traces, de = _traces()
    seen = _run(traces, [1.0, 0.0])
    first, back = seen[0], seen[-1]
    assert back["drawn"] == first["drawn"] == len(de)
    assert [r["name"] for r in back["names"]] == [r["name"]
                                                  for r in first["names"]]
    assert back["says"] == "nothing hidden"


@needs_node
def test_it_leaves_a_page_with_no_drift_cloud_alone():
    """A control that cannot act is worse than a missing one.

    The shapes carry no ΔE per point, so there is nothing to hide by.
    """
    traces = [{"name": "Matte-paper", "x": [1, 2], "y": [1, 2], "z": [1, 2],
               "customdata": None, "marker": {"color": None, "size": None}}]
    assert not _run(traces, [])[0]["built"]
