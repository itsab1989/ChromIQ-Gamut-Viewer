"""What does the window do when the file is wrong?

EVERY CHECK HERE SO FAR HAS USED GOOD FILES. That is the comfortable half of
the story: the other half is what somebody meets on the day they pick the
wrong thing out of a folder — an empty file, a text file with an .icc name, a
measurement with no patches in it, a profile for a printer that is not RGB.

WHAT MUST BE TRUE, and it is the same for each of them:

  * SOMETHING IS SAID. Silence is the worst answer: the file appears to open
    and nothing changes, so the natural conclusion is that the application is
    broken rather than the file wrong.
  * WHAT WAS ALREADY OPEN IS STILL THERE. A bad file must not take the
    picture down with it, and it must not leave half of itself behind.
  * AND THE WINDOW STILL WORKS AFTERWARDS: a good file opened next draws.

Each case is driven against the real window, with the message box captured
rather than clicked, and the picture asked what it holds before and after.

    python scripts/audit_bad_files.py

Exit code 1 if a bad file passes without a word, takes the picture down, or
leaves the window unable to open the next one.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_bad_files"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

ASK = """
(function () {
  var d = document.getElementsByClassName('plotly-graph-div')[0];
  if (!d) return "nothing drawn";
  var data = d._fullData || d.data || [];
  var names = [];
  for (var i = 0; i < data.length; i++) names.push(String(data[i].name || ""));
  return names.join(" | ") || "no traces";
})()
"""


def bad_files(folder: pathlib.Path, good: pathlib.Path):
    """Files a person could plausibly pick by mistake."""
    made = []

    empty = folder / "empty.icc"
    empty.write_bytes(b"")
    made.append(("an empty file", empty, "must refuse"))

    prose = folder / "notes-really.icc"
    prose.write_text("These are my notes about the printer, not a profile.\n"
                     "It has an .icc name because I renamed it by mistake.\n",
                     encoding="utf-8")
    made.append(("a text file with an .icc name", prose, "must refuse"))

    half = folder / "truncated.icc"
    half.write_bytes(good.read_bytes()[:2048])
    made.append(("a profile cut off part way", half, "must refuse"))

    scrambled = folder / "scrambled.icc"
    raw = bytearray(good.read_bytes())
    for at in range(200, min(len(raw), 20000), 97):
        raw[at] = (raw[at] + 137) % 256
    scrambled.write_bytes(bytes(raw))
    # MAY WELL OPEN, and that is the right answer: the header is intact, so
    # this is still a profile as far as any reader is concerned -- its colours
    # are simply wrong, and no application can know that. What must not happen
    # is a silent HALF load: if it opens, it opens as a shape with a name like
    # any other.
    made.append(("a profile with its numbers scrambled", scrambled, "may open"))

    headerless = folder / "no-patches.ti3"
    headerless.write_text("CTI3\n\nDESCRIPTOR \"a measurement with no patches\"\n"
                          "NUMBER_OF_FIELDS 0\nBEGIN_DATA\nEND_DATA\n",
                          encoding="utf-8")
    made.append(("a measurement with no patches", headerless, "must refuse"))
    return made


def main() -> int:
    from PyQt6.QtWidgets import QApplication

    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    win = gamut_app.GamutApp([])
    win.resize(1400, 900)
    win.show()

    said = []
    gamut_app.Notice.warn = staticmethod(
        lambda parent, title, body, **k: said.append((title, body)))
    gamut_app.Notice.say = staticmethod(
        lambda parent, title, body, **k: said.append((title, body)))

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    def drawing():
        got = []
        page = win._view.page()
        if page is None:
            return "no page"
        page.runJavaScript(ASK, got.append)
        end = time.time() + 5
        while not got and time.time() < end:
            app.processEvents()
            time.sleep(0.005)
        return got[0] if got else "no answer"

    pump(3)
    profiles = sorted(pathlib.Path(tempfile.gettempdir())
                      .glob("showme-*/printer-*.icc"))
    if not profiles:
        print("  no demo profiles to drive the window with")
        return 1
    good = profiles[0]
    win._load(good)
    pump(7)
    before = drawing()
    print(f"  with a good profile open, the picture holds: {before[:70]}")
    if "nothing drawn" in before or "no traces" in before:
        print("  the window drew nothing even with a good file — nothing to "
              "compare against")
        return 1

    folder = pathlib.Path(tempfile.mkdtemp(prefix="bad-files-"))
    problems = []
    try:
        for what, path, rule in bad_files(folder, good):
            # THE PICTURE AS IT IS RIGHT NOW, not as it was at the start. One
            # baseline for the whole sweep made every case after the first
            # opening one look as though IT had changed the picture -- an
            # audit reporting its own bookkeeping.
            was_holding = drawing()
            was_open = len(win._slots)
            said.clear()
            win._load(path)
            pump(5)
            after = drawing()
            spoke = bool(said)
            kept = after == was_holding
            opened = len(win._slots) - was_open
            print(f"\n  {what}  ({rule})")
            print(f"      said something: {'yes' if spoke else 'no'}"
                  f"   the picture is unchanged: {'yes' if kept else 'no'}"
                  f"   files opened: {opened}")
            if spoke:
                print(f"      “{said[0][0]}”")
            if rule == "must refuse":
                if not spoke:
                    problems.append(
                        f"[bad file] {what} was opened without a word being "
                        f"said about it")
                if not kept:
                    problems.append(
                        f"[bad file] {what} changed the picture: it held "
                        f"{was_holding[:50]!r} and now holds {after[:50]!r}")
                if opened:
                    problems.append(
                        f"[bad file] {what} was refused and still left "
                        f"{opened} file(s) in the list")
            elif not spoke and opened != 1:
                # It parsed, nothing was said, and yet it did not arrive as a
                # file: that is the silent half-load this rule exists for.
                problems.append(
                    f"[bad file] {what} opened silently and did not appear as "
                    f"a file ({opened} added)")
        # ---- THE OTHER THREE WAYS A FILE GETS IN --------------------------
        # The list of open files is one of four routes, and the fault found
        # above -- room made before the file was read -- could live in any of
        # them. Crossed rather than assumed: a chart, a comparison, and a run
        # of profiles, each given something unreadable while a good one is
        # already in place.
        print("\n  the other ways a file gets in")
        demo = HERE.parent / "demo"
        chart = demo / "verification-chart-480.ti1"
        if chart.exists():
            win._open_chart_file(chart)
            pump(6)
            was = None if win._chart is None else pathlib.Path(win._chart[0]).name
            nonsense = folder / "not-a-chart.ti1"
            nonsense.write_text("CTI1\nthis file is nonsense\n",
                                encoding="utf-8")
            said.clear()
            win._open_chart_file(nonsense)
            pump(5)
            now = None if win._chart is None else pathlib.Path(win._chart[0]).name
            print(f"      a bad chart: the good one is {'kept' if now == was else 'GONE'}"
                  f", said {[t for t, _b in said] or 'nothing'}")
            if now != was:
                problems.append("[bad file] a bad chart closed the good one")
            if not said:
                problems.append("[bad file] a bad chart was refused in silence")

        win._load_profile_as_comparison(good)
        pump(6)
        was = win._reference[0] if win._reference else None
        bad_icc = folder / "not-a-profile.icc"
        bad_icc.write_text("nor is this\n", encoding="utf-8")
        said.clear()
        win._load_profile_as_comparison(bad_icc)
        pump(5)
        now = win._reference[0] if win._reference else None
        print(f"      a bad comparison: the good one is "
              f"{'kept' if now == was else 'GONE'}, said "
              f"{[t for t, _b in said] or 'nothing'}")
        if now != was:
            problems.append("[bad file] a bad comparison closed the good one")
        if not said:
            problems.append("[bad file] a bad comparison was refused in silence")

        # A RUN SAYS IT DIFFERENTLY, on purpose: a drop of twenty profiles
        # must not raise twenty message boxes, so the row itself carries the
        # answer and the panel writes the reason underneath.
        panel = win._timeline
        broken = folder / "printer-2022.icc"
        broken.write_text("not a profile at all\n", encoding="utf-8")
        panel.add(list(profiles[:2]) + [broken])
        pump(9)
        rows = [panel._list.item(i).text() for i in range(panel._list.count())]
        named = any("could not be read" in row and "printer-2022" in row
                    for row in rows)
        usable = [getattr(u, "name", u) for u in getattr(panel._run, "usable", [])]
        print(f"      a run with one bad profile: the row says so "
              f"{'yes' if named else 'NO'}, and {len(usable)} of "
              f"{len(rows)} are usable")
        if not named:
            problems.append(
                "[bad file] a run took a profile it cannot read without "
                "marking the row")
        if len(usable) != 2:
            problems.append(
                f"[bad file] a run with one bad profile among two good ones "
                f"found {len(usable)} usable")

        # AND THE WINDOW STILL WORKS. A message is no good if what it leaves
        # behind cannot open the next file.
        said.clear()
        win._load(profiles[1] if len(profiles) > 1 else good)
        pump(7)
        recovered = drawing()
        print(f"\n  a good profile afterwards: {recovered[:70]}")
        if "nothing drawn" in recovered or "no traces" in recovered:
            problems.append(
                "[bad file] after the bad ones, a good profile drew nothing")
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} problem(s).")
        win.close()
        return 1
    print("  Clean: every bad file was explained, and none of them took the "
          "picture with it.")
    win.close()
    pump(0.3)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
