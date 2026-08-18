"""Cross what is open against a run, and ask what the reader can see.

    python scripts/audit_run_beside_the_rest.py

Exit code 1 if the column widens, if a run's arrival is not explained where
the reader is looking, or if the run's answer lands off the bottom.

The run has only ever been driven ALONE. Basti's constraint is about the
crowded window, and the crowded window is a run open BESIDE a file, a
comparison and a chart -- which is also the only state where the big view
changing owner needs explaining. That explanation is one line, and this asks
whether the reader is ever shown it.
"""
import itertools
import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
sys.argv = ["audit_run_beside_the_rest"]

import prefs                                                   # noqa: E402

prefs.use_a_scratch_store()

from PyQt6.QtWidgets import QApplication, QScrollArea           # noqa: E402

import gamut_app                                                # noqa: E402

app = QApplication(sys.argv)
gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

profiles = sorted(pathlib.Path(tempfile.gettempdir())
                  .glob("showme-*/printer-*.icc"))
chart = HERE.parent / "demo" / "verification-chart-480.ti1"


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


print(f"  {'file':5s} {'compare':8s} {'chart':6s} | "
      f"{'width':5s} {'run drawn':9s} {'the line above the run':38s} seen?")
problems = []
for a_file, compare, a_chart in itertools.product((0, 1), repeat=3):
    win = gamut_app.GamutApp([])
    win.resize(1280, 800)
    win.show()
    pump(2.5)
    if a_file:
        win._load(profiles[0])
        pump(6)
    if compare:
        win._load_profile_as_comparison(profiles[1])
        pump(6)
    if a_chart and chart.exists():
        win._open_chart_file(chart)
        pump(7)
    win._timeline.add(list(profiles[:3]))
    pump(11)

    area = win.findChild(QScrollArea)
    inner = area.widget()
    bar = area.verticalScrollBar()
    line = win._who_owns
    said = line.text()
    top = line.mapTo(inner, line.rect().topLeft()).y()
    bottom = top + line.height()
    shown = (line.isVisibleTo(inner) and said
             and bottom > bar.value()
             and top < bar.value() + area.viewport().height())
    # AND THE ANSWER ITSELF, which is what the scroll was built for. Moving
    # the landing up to catch the line above costs about forty pixels at the
    # bottom, and the thing at the bottom is the verdict.
    words = getattr(win._timeline, "_words_box", None)
    wtop = words.mapTo(inner, words.rect().topLeft()).y() if words else -1
    verdict_seen = (words is not None
                    and wtop < bar.value() + area.viewport().height() - 40)
    if not verdict_seen:
        problems.append(
            f"the answer is off the bottom with file={a_file} "
            f"compare={compare} chart={a_chart}")
    print(f"  {a_file:<5d} {compare:<8d} {a_chart:<6d} | "
          f"{inner.width():<5d} {str(getattr(win, '_run_drawn', False)):9s} "
          f"{(said[:36] + '…') if len(said) > 36 else said:38s} "
          f"{'yes' if shown else ('NO' if said else '-')}   "
          f"answer {'yes' if verdict_seen else 'NO'}")
    if inner.width() != 503:
        problems.append(f"column is {inner.width()} px with "
                        f"file={a_file} compare={compare} chart={a_chart}")
    if said and not shown:
        problems.append(
            f"the line explaining the big view is off screen with "
            f"file={a_file} compare={compare} chart={a_chart}")
    if (a_file or compare) and not said:
        problems.append(
            f"nothing explains the big view with file={a_file} "
            f"compare={compare} chart={a_chart}")
    win.close()
    pump(0.6)

print()
for p in problems:
    print("  " + p)
print(f"\n  {len(problems)} problem(s)." if problems
      else "  Clean: a run beside anything else still explains itself, and "
           "the column never widens.")
sys.stdout.flush()
os._exit(1 if problems else 0)
