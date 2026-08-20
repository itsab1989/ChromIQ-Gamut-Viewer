"""Every slider changes the picture WHILE it is dragged, not on release.

    ../gv-venv/bin/python scripts/audit_sliders_are_live.py
    ../gv-venv/bin/python scripts/audit_sliders_are_live.py --prove

WHY THIS EXISTS. Reported from the window, twice in two minutes: "show rings
inside slider only updates the viewer when i let go from dragging it - should
be live", then "same what i just said is true for the details slider", and
then the rule that settles it: "all sliders should work this way".

Two reports of one fault means it is a class, not two bugs. A slider that only
acts on release is one connected to `sliderReleased` while `valueChanged` does
nothing but retitle a label, and nothing in the window says which is which --
so the way to keep this from coming back is to ask every slider the same
question rather than to fix the two that were noticed.

WHAT MUST BE TRUE, with the failure direction:

  the picture changes DURING the drag   a slider whose picture only catches up
                                        on release feels broken, and the
                                        reader cannot see what they are
                                        choosing while they choose it;
  it changes to the RIGHT thing         a live push that reaches the wrong
                                        trace is worse than none: the rebuild
                                        on release would put it right and hide
                                        the fault, which is how one fix
                                        becomes the next bug (see
                                        _which_meshes_js);
  releasing does not undo it            if letting go rebuilds the page, the
                                        shape jumps back and the camera moves,
                                        which is the fault the in-place
                                        restyle exists to avoid.

HOW A DRAG IS SIMULATED, and why not with setValue alone: a slider driven by
`setValue` emits `valueChanged` and never `sliderPressed`/`sliderReleased`, so
a check written that way cannot tell a live slider from a dead one -- it would
pass on both. `setValue` has already fooled this project once, which is the
memory "setValue fires only half a slider". So the handle is pressed
(`sliderPressed`), moved with `setSliderDown(True)` in force, measured, and
only then released.

WHAT IS MEASURED is the picture itself -- the number of points in the rings
trace, read out of the live page -- not the widget, not the settings, and not
a signal count. A control that says something true while the picture says
something else is the fault this window has been reported for twice.
"""
from __future__ import annotations

import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

import prefs                                                 # noqa: E402

prefs.use_a_scratch_store()

#: A DIGEST OF THE WHOLE PICTURE, not of one trace.
#
# Asking about the rings alone would answer for the rings slider and say
# nothing about the six others -- the wrong pair, measured well. This reads
# every trace in every room and records what any of these sliders could
# change: how many points it has, how many triangles, how solid it is, and a
# sample of its colours (the fades change colours and nothing else, so a
# digest without them would call the fade sliders live when they are dead).
LOOK = """(function () {
  var divs = document.getElementsByClassName('plotly-graph-div');
  var out = [];
  for (var r = 0; r < divs.length; r++) {
    var el = divs[r];
    if (!el || !el.data) continue;
    for (var i = 0; i < el.data.length; i++) {
      // READ THE TRIANGLES FROM _fullData, NOT FROM data.
      //
      // The written page packs i/j/k binary, so `el.data[i].i.length` is
      // undefined and a digest built on it cannot see a mesh gain or lose
      // triangles at all. That is not a small blind spot: hiding "where they
      // agree" changes ONLY the face list -- 1,328 triangles to 583, measured
      // -- so this check called a working slider dead, twice, and the push it
      // was accusing had already reported success.
      var t = el.data[i], full = (el._fullData || [])[i] || t;
      var c = t.vertexcolor || (t.marker && t.marker.color);
      var sample = '';
      if (c && c.length) sample = String(c[0]) + '|' +
          String(c[Math.floor(c.length / 2)]) + '|' + String(c.length);
      // AND THE LIGHTING, because the shading slider changes NOTHING ELSE.
      // Left out, this digest called that slider dead while it was working
      // perfectly -- a false alarm from asking the wrong question, which is
      // the same fault as a check that cannot see a real one.
      var l = t.lighting || {};
      var lit = [l.ambient, l.diffuse, l.specular, l.roughness,
                 l.fresnel].join(',');
      var faces = (full.i && full.i.length) ? full.i.length
                : ((t.i && t.i.length) ? t.i.length : 0);
      out.push([String(t.name || ''), t.type,
                (t.x || []).length, faces,
                t.opacity === undefined ? '' : String(t.opacity), sample,
                lit]);
    }
  }
  return JSON.stringify(out);
})()"""


def main() -> int:
    prove = "--prove" in sys.argv
    sys.argv = ["audit_sliders_are_live"]

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication

    import gamut_app

    app = QApplication(sys.argv)
    window = gamut_app.GamutApp()
    window.resize(1500, 950)
    window.show()

    def settle(ms=1500):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    demo = HERE.parent / "demo"
    profiles = sorted(demo.glob("*.icc")) + sorted(demo.glob("*.ti3"))
    if not profiles:
        print("no demo profile to open — run scripts/make_demo_profiles.py")
        return 0
    window._load(profiles[0])
    settle(4000)

    # THE TICKS THAT MAKE THESE SLIDERS MEAN ANYTHING MUST BE ON -- BUT NOT
    # ALL AT ONCE.
    #
    # A slider whose tickbox is off changes nothing, correctly, and dragging
    # it reports "not live" about a control that is not doing anything: a
    # false alarm, which costs the same trust as a miss. Measured with the
    # slice unticked, its slider moved nothing before OR after release.
    #
    # AND TICKING THEM ALL IS WORSE. "Slice it at one lightness" replaces the
    # shapes with a flat cross-section, which has no surfaces, no rings and no
    # shading -- so with it on, ALL SEVEN sliders were reported dead, including
    # the two that had just been measured live. The lightness slider therefore
    # gets its own picture, at the end, and the rest are asked in the picture
    # they belong to.
    window._rings_on.setChecked(True)
    settle(3000)

    def read():
        answer = {}
        loop = QEventLoop()

        def got(value):
            answer["v"] = value
            loop.quit()

        window._view.page().runJavaScript(LOOK, got)
        QTimer.singleShot(4000, loop.quit)
        loop.exec()
        return answer.get("v") or "[]"

    import json

    # A COMPARISON MUST BE OPEN, or three of these sliders have nothing to act
    # on and would be reported "live" for want of anything to change. His own
    # screenshots all have one: this is the configuration the reports came
    # from, not the default.
    # AND IT MUST ACTUALLY BE LOADED, not merely selected.
    #
    # The combo is connected to `activated`, which only a real click emits --
    # `setCurrentIndex` changes what the box SAYS and loads nothing. Measured
    # the hard way: with the box reading "sRGB" the window still had
    # `_reference = None` and one shape on screen, so three of these sliders
    # were being asked in a picture they cannot act on, and this check called
    # two of them live on that evidence. The handler is called here for the
    # same reason the window calls it.
    for i in range(window._compare.count()):
        data = window._compare.itemData(i)
        if data and data[0] == "space" and data[1] == "sRGB":
            window._compare.setCurrentIndex(i)
            window._on_compare_changed()
            break
    settle(6000)
    if window._reference is None:
        print("  no comparison could be loaded, so the fades and the detail "
              "have nothing\n  to act on — this run would prove nothing about "
              "them.")
        return 2
    names = [n for n, _g in getattr(window, "_scene_inputs", ([],))[0]]
    print(f"  the picture holds: {', '.join(names) or '(nothing)'}")

    # HOW MUCH OF THIS SHAPE AGREES WITH THE OTHER, because the two fade
    # sliders can only act on what exists. If nothing agrees, "where they
    # agree" has nothing to hide and changing it is CORRECTLY a no-op -- and
    # a check that calls that "not live" is accusing the window of a fault in
    # the data. The share is printed so the reader can tell the two apart.
    agreeing = None
    try:
        import ti3gamut as _t
        pairs = getattr(window, "_scene_inputs", ([],))[0]
        if len(pairs) > 1:
            stands = _t.disagreeing_vertices(pairs, _t.surfaces_of(pairs))
            agreeing = 100.0 * (1.0 - float(stands[0].mean()))
    except Exception:                                      # noqa: BLE001
        agreeing = None
    if agreeing is not None:
        print(f"  of {names[0]}'s surface, {agreeing:.1f}% lies inside "
              f"{names[-1]}")
        if agreeing < 0.5:
            print("  → almost nothing agrees, so 'where they agree' has "
                  "nothing to hide here")
    print()

    #: Every slider in "How it looks", with a value to drag it to that is far
    #: enough from the default to change the picture beyond doubt.
    WHICH = [
        ("Show rings inside", "_rings", 20),
        ("Detail", "_detail", 40),
        ("How solid the shapes are", "_opacity", 45),
        ("Depth", "_depth", 90),
        ("Where they agree", "_agree", 0),
        ("Where they differ", "_differ", 0),
        ("Slice it at one lightness", "_slice_at", 70),
    ]

    if prove:
        # THE MUTATION: put the OLD wiring back on the one slider that has
        # been fixed -- valueChanged retitles the label and touches nothing
        # else, which is exactly how it was when Basti reported it. If this
        # check still says Clean with that in force, it is blind.
        #
        # PROVEN TO LAND, because a mutation that silently fails to apply
        # looks identical to a check passing: after the drag the LABEL must
        # have followed the handle while the picture did not.
        window._rings.valueChanged.disconnect()
        window._rings.valueChanged.connect(
            lambda v: window._rings_lbl.setText(str(v)))
        print("  --prove: the rings slider is back on its old wiring — the "
              "label alone follows it\n")

    problems = []
    print(f"  {'slider':28s} {'during the drag':>16s} {'on release':>12s}")
    print("  " + "-" * 60)

    for label, attr, target in WHICH:
        slider = getattr(window, attr, None)
        if slider is None:
            problems.append(f"{label}: no slider called {attr}")
            continue
        # EACH SLIDER STARTS FROM A KNOWN PICTURE.
        #
        # Run one after another without this, each is asked in whatever state
        # the last one left: "where they differ" was dragged to nothing in a
        # picture whose agreeing half had already been hidden by the slider
        # before it, so there was nothing left to change and it was reported
        # as doing nothing. An answer known in advance needs a starting point
        # known in advance.
        if window._agree.value() != 100 or window._differ.value() != 100:
            window._agree.setValue(100)
            window._differ.setValue(100)
            window._redraw()
            settle(4000)

        # THE CUT GETS ITS OWN PICTURE, for the reason written above: it
        # replaces the shapes rather than changing them.
        if attr == "_slice_at":
            window._slice_on.setChecked(True)
            settle(4000)
        if slider.value() == target:
            target = slider.minimum() if target != slider.minimum() \
                else slider.maximum()

        before = json.loads(read())
        slider.setSliderDown(True)
        slider.sliderPressed.emit()
        slider.setValue(target)
        settle(2500)
        during = json.loads(read())
        slider.setSliderDown(False)
        slider.sliderReleased.emit()
        settle(3500)
        after = json.loads(read())

        moved = during != before
        undone = after != during
        print(f"  {label:28s} {'yes' if moved else 'NO':>16s} "
              f"{'kept' if not undone else 'rebuilt':>12s}")
        # RELEASE-ONLY AND NOTHING-AT-ALL ARE DIFFERENT ANSWERS, and calling
        # them both "not live" is how a check earns a reputation for crying
        # wolf. If letting go changed the picture, the digest can plainly see
        # this slider and the fault is real. If NOTHING changed at any point,
        # the picture never answered -- the control may be inert in this
        # state, or this digest may be blind to what it does, and either way
        # that is a question rather than a finding.
        if not moved and undone:
            problems.append(
                f"{label}: the picture did not change while the handle was "
                f"down, and rebuilt when it was let go — release-only")
        elif not moved:
            problems.append(
                f"{label}: the picture never changed, before or after the "
                f"release. Either this control does nothing in the state it "
                f"was asked in, or this check cannot see what it does — "
                f"settle which before believing it")

    print()
    if prove:
        landed = window._rings_lbl.text() == str(
            window._rings.value())
        if not landed:
            print(f"  THE MUTATION DID NOT LAND — the label says "
                  f"{window._rings_lbl.text()!r} beside a slider at "
                  f"{window._rings.value()}, so this run tested nothing.")
            return 2
        caught = any("Show rings inside" in p for p in problems)
        print("  the mutation landed (the label followed the handle).")
        if caught:
            print("  The audit reported the rings slider as dead, as it must. "
                  "It can see.")
            return 0
        print("  THE AUDIT DID NOT NOTICE a slider with its live handler "
              "removed. It is blind.")
        return 1

    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n  {len(problems)} problem(s).")
        return 1
    print("  Clean: every slider moved the picture while its handle was down.")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
