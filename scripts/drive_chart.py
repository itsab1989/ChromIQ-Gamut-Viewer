"""Drive the real application through the whole chart journey, on screen.

Not a unit test. The window is built, the buttons are pressed through the
handlers a person's click reaches, and what the panels SAY is read back off
the labels. Everything here is a claim about the application, not about a
function.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "python"))
sys.argv = ["x"]
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

QSettings("MeasuredGamutViewer", "MeasuredGamutViewer").clear()
import gamut_app

# WHERE THE FILES COME FROM. A real measurement and the profile built from it
# cannot be invented, so point GAMUT_DEMO at a folder holding a .ti3 and the
# .icc built from it. Every chart this needs is written here instead, so the
# parts that are about reading charts run on any machine.
#
#     GAMUT_DEMO=~/my-profiling-folder python scripts/drive_chart.py
DEMO = Path(os.environ.get("GAMUT_DEMO", Path(ROOT) / "demo-data"))
MEASUREMENT = next(iter(sorted(DEMO.glob("*.ti3"))), None)
PROFILE = next(iter(sorted(DEMO.glob("*.icc"))), None)
CHARTS = Path(os.environ.get(
    "GAMUT_CHARTS", Path(os.environ.get("TMPDIR", "/tmp")) / "gamut-charts"))
CHARTS.mkdir(parents=True, exist_ok=True)


def make_charts():
    """One chart, written out in every form this understands.

    THE SAME PATCHES EVERY TIME, so that "the .txt and the .ti1 agree" is a
    claim about the reader rather than about which file happened to be handy.
    """
    import numpy as np
    rng = np.random.default_rng(4)
    device = np.vstack([
        [[100.0, 100, 100], [100, 100, 100], [0, 0, 0], [0, 0, 0]],
        np.stack(np.meshgrid(*[np.linspace(0, 100, 6)] * 3,
                             indexing="ij"), axis=-1).reshape(-1, 3),
        rng.uniform(0, 100, size=(80, 3))])
    rows = "\n".join(
        f"{i + 1} " + " ".join(f"{v:.4f}" for v in triple)
        + " 50.0000 50.0000 50.0000"           # predicted, never measured
        for i, triple in enumerate(device))
    (CHARTS / "driven-chart.ti1").write_text(
        'CTI1\n\nDESCRIPTOR "Argyll Calibration Target chart information 1"\n'
        'ORIGINATOR "Argyll targen"\nCOLOR_REP "iRGB"\n\n'
        "NUMBER_OF_FIELDS 7\nBEGIN_DATA_FORMAT\n"
        "SAMPLE_ID RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z\nEND_DATA_FORMAT\n\n"
        f"NUMBER_OF_SETS {len(device)}\nBEGIN_DATA\n{rows}\nEND_DATA\n"
        # The second and third tables targen always writes, which a reader
        # that concatenates everything swallows into the chart.
        'CTI1\n\nDESCRIPTOR "Argyll Calibration Target chart information 1"\n'
        'DENSITY_EXTREME_VALUES "1"\n\nNUMBER_OF_FIELDS 7\n'
        "BEGIN_DATA_FORMAT\nINDEX RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z\n"
        "END_DATA_FORMAT\n\nNUMBER_OF_SETS 1\nBEGIN_DATA\n"
        "0 100.0000 100.0000 100.0000 95.1 100.0 108.8\nEND_DATA\n")
    # The same chart as i1Profiler saves it: 0..255, and no XYZ at all.
    rows255 = "\n".join(
        f"{i + 1} " + " ".join(f"{v * 2.55:.4f}" for v in triple)
        for i, triple in enumerate(device))
    (CHARTS / "driven-chart.txt").write_text(
        'CGATS.5\n\nORIGINATOR "ChromIQ"\n\nKEYWORD "SampleID"\n'
        "NUMBER_OF_FIELDS 4\nBEGIN_DATA_FORMAT\nSampleID RGB_R RGB_G RGB_B\n"
        f"END_DATA_FORMAT\n\nNUMBER_OF_SETS {len(device)}\nBEGIN_DATA\n"
        f"{rows255}\nEND_DATA\n")
    # And a CMYK one, which no RGB profile can place.
    (CHARTS / "driven-cmyk.ti1").write_text(
        'CTI1\nCOLOR_REP "CMYK"\nNUMBER_OF_FIELDS 5\nBEGIN_DATA_FORMAT\n'
        "SAMPLE_ID CMYK_C CMYK_M CMYK_Y CMYK_K\nEND_DATA_FORMAT\n"
        "BEGIN_DATA\n1 0 0 0 0\n2 100 100 100 100\n3 50 20 10 5\nEND_DATA\n")
    return len(device)


N_PATCHES = make_charts()
CHART = CHARTS / "driven-chart.ti1"
SMALL = CHART
I1TXT = CHARTS / "driven-chart.txt"
CMYK = CHARTS / "driven-cmyk.ti1"

if MEASUREMENT is None or PROFILE is None:
    print(f"\nNo measurement and profile found in {DEMO}.\n"
          "Point GAMUT_DEMO at a folder holding a .ti3 and the .icc built "
          "from it:\n\n    GAMUT_DEMO=~/ChromIQ/my-paper/runs/run1 "
          "python scripts/drive_chart.py\n")
    raise SystemExit(2)

app = QApplication(sys.argv)
w = gamut_app.GamutApp([])
w.resize(1400, 900)
w.show()

failures = []
said = []


def pump(seconds=0.6):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def check(claim, ok, detail=""):
    mark = "ok  " if ok else "FAIL"
    print(f"  {mark}  {claim}" + (f"   [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(claim)


def panel():
    return "\n".join(x for x in (
        w._chart_headline.text(), w._chart_rows.text(),
        w._chart_spread.text()) if x)


# Every dialog answered without a person, and every popup recorded rather
# than shown -- an unanswered modal is how a driver hangs for ever.
def no_dialogs(files=None):
    gamut_app.Notice.warn = staticmethod(
        lambda parent, title, body: said.append(("warn", title, body)))
    gamut_app.Notice.say = staticmethod(
        lambda parent, title, body: said.append(("say", title, body)))
    gamut_app.Notice.ask = staticmethod(lambda *a, **k: True)


no_dialogs()
pump(2.5)

print("\n=== 1. a chart, opened with nothing else on screen ===")
w._open_chart_file(CHART)
pump(1.5)
check("the chart is open and named", CHART.stem in w._chart_label.text(),
      w._chart_label.text())
check("it says how many patches", f"{N_PATCHES} patches" in w._chart_label.text(),
      w._chart_label.text())
check("nothing is drawn, and it says what is missing",
      w._chart_placed is None and "Placed through" in w._chart_note.text(),
      w._chart_note.text())
check("the numbers panel is showing, and asks for a profile",
      w._chart_box.isVisible() and "Placed through" in w._chart_rows.text(),
      panel())
check("no popup complained", not said, said[:1])
print("    note: " + w._chart_note.text()[:120])

print("\n=== 2. placed through a profile, still with nothing else ===")
w._chart_profile = PROFILE
w._fill_chart_profiles()
w._place_chart()
pump(2.0)
check("the patches were placed", w._chart_placed is not None)
check("the note says they are to be printed, not measured",
      "not measured" in w._chart_note.text(), w._chart_note.text())
check("it names the profile and the intent",
      PROFILE.stem in w._chart_note.text()
      and "relative colorimetric" in w._chart_note.text(),
      w._chart_note.text())
check("the caption on the picture does not call it a measured gamut",
      "Measured gamut" not in w._scene_title(), w._scene_title())
check("the caption names the profile", PROFILE.stem in w._scene_title(),
      w._scene_title())
check("with no shape open, it says there is nothing to count against",
      "Nothing else is open" in w._chart_rows.text(), panel())
check("how far apart is reported anyway — it needs no shape",
      "How far apart" in w._chart_spread.text(), w._chart_spread.text())
check("saving a picture is possible with only a chart open",
      w._picture.isEnabled() and w._save.isEnabled())
print("    " + panel().replace("\n", "\n    ")[:400])

print("\n=== 3. the profile it was built from, as a shape (question A) ===")
w._load(PROFILE)
pump(2.5)
rows = w._chart_rows.text()
check("the profile gets a line of its own", f"{PROFILE.stem}:" in rows, rows)
check("it says all three counts",
      "inside" in rows and "on the edge" in rows and "outside" in rows, rows)
check("and it says what a clean answer here does and does not prove",
      "check of the chart rather than of your printer" in rows
      or "should all have been inside" in rows, rows)
print("    " + rows.replace("\n", "\n    ")[:420])

print("\n=== 4. the measurement of the paper as well (question B) ===")
# THE TWO FILES SHARE A STEM ON PURPOSE. Glossy-paper.icc beside
# Glossy-paper.ti3 is the ordinary case, and deciding "did this one place the
# patches?" by name told the reader a measurement had.
w._load(MEASUREMENT)
pump(3.0)
rows = w._chart_rows.text()
check("both shapes are reported", rows.count("inside,") >= 2, rows)
check("the two lines differ — A and B are not the same question",
      len({ln for ln in rows.split("\n\n")}) >= 2, rows)
check("only ONE of them is called the profile that placed the patches",
      rows.count("placed through this very profile")
      + rows.count("placed it through") <= 1
      and rows.count("thickness of the boundary") <= 1, rows)
check("the measurement's line says the paper could not reach them",
      "cannot reach what those patches ask for" in rows, rows)
print("    " + rows.replace("\n", "\n    ")[:700])

print("\n=== 4b. the two whites — the false alarm this nearly shipped ===")
rows = w._chart_rows.text()
check("the measurement's line warns the two whites differ",
      "measured against different whites" in rows, rows[-300:])
check("and it names the tick box that fixes it",
      "Judge each paper against its own white" in rows, rows[-300:])
before = rows
w._relative.setChecked(True)
pump(4.0)
rows = w._chart_rows.text()
check("ticking it drops the warning", "different whites" not in rows,
      rows[-200:])
outside_before = int(before.split(" on the edge, ")[-1].split(" outside")[0])
outside_after = int(rows.split(" on the edge, ")[-1].split(" outside")[0])
check("and the count of outside patches changes a great deal",
      outside_after < outside_before,
      f"{outside_before} -> {outside_after}")
print(f"    against an absolute white: {outside_before} outside")
print(f"    against the paper's own:   {outside_after} outside")
print("    " + rows.replace("\n", "\n    ")[:420])
w._relative.setChecked(False)
pump(4.0)

print("\n=== 5. the picture itself ===")
cloud = w._chart_cloud()
check("the renderer is handed the chart", cloud is not None)
if cloud:
    # FOUR, not three. The chart grew a fourth part -- the ink amounts, which
    # is what the ink-amount view draws from -- and this driver went on
    # unpacking three and died on the line. It is not shipped, so nothing a
    # user touches was affected; it did mean this whole check had been
    # silently unrunnable since. Named rather than positional from here on, so
    # a fifth part cannot do it again.
    name, lab, marked, ink = cloud
    check("with a mask of what falls outside", marked is not None
          and len(marked) == len(lab))
    check("and it marks some but not all", 0 < int(marked.sum()) < len(marked),
          str(None if marked is None else int(marked.sum())))
import ti3gamut
fig = ti3gamut.build_figure([("x", w._slots[0][1])], "t", chart=cloud)
names = [t.name for t in fig.data if t.name]
check("the page carries a 'to be printed' trace",
      any("to be printed" in n for n in names), str(names))
check("and a separate 'outside' one",
      any("outside" in n for n in names), str(names))
check("no trace calls the chart a gamut or a surface",
      not any(getattr(t, "type", "") == "mesh3d" and "verification" in (t.name or "")
              for t in fig.data))

print("\n=== 6. a chart in the wrong place, and a measurement in the chart's ===")
said.clear()
w._load(SMALL)               # a .ti1 dragged onto the window
pump(1.2)
check("a .ti1 dropped on the window opens as a chart, not as an error",
      w._chart is not None and w._chart[0] == SMALL and not said,
      str(said[:1]))
said.clear()
w._open_chart_file(MEASUREMENT)
pump(0.8)
check("a .ti3 offered as a chart is refused with a reason",
      bool(said) and "measurement" in said[-1][2], str(said[-1:])[:160])
check("and the chart already open is left alone", w._chart[0] == SMALL)

print("\n=== 7. the other file forms, and a chart that cannot fit ===")
w._open_chart_file(I1TXT)
pump(1.5)
check("an i1Profiler .txt opens", w._chart is not None
      and w._chart[0] == I1TXT)
check("its ink amounts were read as 0..255", w._chart[1].scale == 255.0,
      str(w._chart[1].scale))
check("and it holds the same patches as the .ti1 of the same chart",
      w._chart[1].n_patches == N_PATCHES, str(w._chart[1].n_patches))
said.clear()
w._open_chart_file(CMYK)
pump(1.5)
check("a CMYK chart opens", w._chart[1].channels == ("C", "M", "Y", "K"))
check("but says plainly it cannot go through an RGB profile",
      bool(said) and ("CMYK" in said[-1][2] and "RGB" in said[-1][2]),
      str(said[-1:])[:200])
check("and the chart is still open, waiting for a profile that fits",
      w._chart is not None and w._chart_placed is None)

print("\n=== 8. closing it puts everything back ===")
w._close_chart()
pump(1.0)
check("the chart is gone", w._chart is None and w._chart_placed is None)
check("its panel row is hidden", not w._chart_row.isVisible())
check("its numbers box is hidden", not w._chart_box.isVisible())
check("and the shapes that were open are still drawn", len(w._slots) == 2)

print("\n=== 9. every button says what it does, and none of it is clipped ===")
for label, button in (("Open", w._open_btn), ("Close", w._clear_btn),
                      ("Chart", w._chart_btn)):
    button.setVisible(True)
    pump(0.2)
    need, room = button.sizeHint().width(), button.width()
    check(f'"{button.text()}" fits its button', need <= room,
          f"needs {need}, has {room}")
    check(f"{label} has a tooltip that explains it",
          len(button.toolTip()) > 80, button.toolTip()[:40])
# THE LABEL IS GENERAL AND THE TOOLTIP IS SPECIFIC, which is the only way
# four kinds of file fit: naming three of them already needed 272 of the 276
# pixels a button in this column has.
check("the Open button does not claim to open only some kinds",
      not any(word in w._open_btn.text().lower()
              for word in ("measurement", "profile", "chart", "picture")),
      w._open_btn.text())
for word in ("measurement", "profile", "chart", "picture"):
    check(f"its tooltip names {word}s", word in w._open_btn.toolTip().lower())
entries = [w._compare.itemText(i) for i in range(w._compare.count())]
# EVERY GROUP THE SAME WIDTH. A group whose only wide child is hidden shrinks
# to its button and drops its ⓘ onto a line of its own, which is what the
# chart section did before it had something to say when empty.
from PyQt6.QtWidgets import QGroupBox
w._close_chart()
pump(1.0)
col = w._open_btn.parent().parent()
widths = {g.title(): g.width() for g in col.findChildren(QGroupBox)
          if g.title() and g.isVisible()}
check("every visible group fills the column",
      len(set(widths.values())) == 1,
      ", ".join(f"{t}={x}" for t, x in widths.items()))
check("the chart section says what it is for before anything is open",
      ".ti1" in w._chart_note.text(), w._chart_note.text())

check("Compare with offers pictures too",
      any("picture" in e.lower() for e in entries), " | ".join(entries))
check("the Close button no longer promises only two",
      "both" not in w._clear_btn.text().lower(), w._clear_btn.text())
check("Compare with says where charts go instead",
      "chart" in w._compare.toolTip().lower(), w._compare.toolTip()[:60])

print("\n=== 10. Close them all really does close them all ===")
w._open_chart_file(SMALL)
w._chart_profile = PROFILE
w._place_chart()
pump(1.5)
check("a chart and two shapes are open",
      w._chart is not None and len(w._slots) == 2)
w._on_clear()
pump(1.0)
check("and one click closes every one of them",
      w._chart is None and not w._slots and not w._chart_box.isVisible())

print("\n" + ("EVERY CHECK PASSED" if not failures
              else f"{len(failures)} FAILED:\n  " + "\n  ".join(failures)))
sys.stdout.flush()
os._exit(1 if failures else 0)
