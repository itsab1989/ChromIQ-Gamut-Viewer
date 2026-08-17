"""Four runs of demo ICC profiles, so anybody can try the timeline at once.

    python scripts/make_demo_runs.py [--out FOLDER]

WHY THESE ARE GENERATED AND NOT COMMITTED. Each is a 1257 kB copy of a
1257 kB profile differing in about six thousand bytes, so twenty-one of them
would be twenty-six megabytes of near-duplicate binary in the repository for
something that takes ten seconds to make. The release workflow runs this and
attaches the result, so a person downloading the application can try the
feature on real files without owning a printer, a spectrophotometer or five
years of patience.

WHY FOUR RUNS RATHER THAN ONE. The whole point of the timeline is that runs
have SHAPES, and the shape decides what you do about it. One run can only
show one shape, and the interesting comparison is between them: a steady
creep and a single jump reach the same total by completely different routes
and want completely different responses.

EVERY SET CHECKS ITSELF before it is written, because a demo that does not
demonstrate the thing is worse than no demo -- it teaches the reader that the
feature does not work.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

#: name → (what it should show, [(profile, date, how far the curve is bent)])
RUNS = {
    "1 - drifting steadily": (
        "every step about the size of the last, so it will keep going", [
            ("printer-2019", (2019, 3, 12, 9, 0, 0), 0.0000),
            ("printer-2020", (2020, 3, 10, 9, 0, 0), 0.0015),
            ("printer-2021", (2021, 3, 15, 9, 0, 0), 0.0030),
            ("printer-2022", (2022, 3, 11, 9, 0, 0), 0.0045),
            ("printer-2023", (2023, 3, 14, 9, 0, 0), 0.0060)]),
    "2 - it moved all at once": (
        "three quiet years and then a jump, on a date you can look up", [
            ("scanner-2019", (2019, 6, 1, 9, 0, 0), 0.0000),
            ("scanner-2020", (2020, 6, 1, 9, 0, 0), 0.0002),
            ("scanner-2021", (2021, 6, 1, 9, 0, 0), 0.0004),
            ("scanner-2022", (2022, 6, 1, 9, 0, 0), 0.0060),
            ("scanner-2023", (2023, 6, 1, 9, 0, 0), 0.0062)]),
    "3 - wandered off and came back": (
        "it ends where it started, having been a long way away in between", [
            ("press-2019", (2019, 3, 1, 9, 0, 0), 0.0000),
            ("press-2020", (2020, 3, 1, 9, 0, 0), 0.0030),
            ("press-2021", (2021, 3, 1, 9, 0, 0), 0.0060),
            ("press-2022", (2022, 3, 1, 9, 0, 0), 0.0030),
            ("press-2023", (2023, 3, 1, 9, 0, 0), 0.0006)]),
    "4 - twice a year, six profiles": (
        "the axis spaced by real time, with two profiles in some years", [
            ("proofer-2022-03", (2022, 3, 1, 9, 0, 0), 0.0000),
            ("proofer-2022-09", (2022, 9, 1, 9, 0, 0), 0.0012),
            ("proofer-2023-03", (2023, 3, 1, 9, 0, 0), 0.0024),
            ("proofer-2023-09", (2023, 9, 1, 9, 0, 0), 0.0036),
            ("proofer-2024-03", (2024, 3, 1, 9, 0, 0), 0.0048),
            ("proofer-2024-09", (2024, 9, 1, 9, 0, 0), 0.0060)]),
}

READ_ME = """ChromIQ Gamut Viewer — demo profiles to try the timeline with
=============================================================

Four runs of made-up ICC profiles, each showing a different shape of drift.
They are derived from the demo Glossy-paper profile by bending its output
curves, so they are real, readable profiles of one imaginary device — nothing
here was measured off paper, and none of it describes a real printer.

HOW TO USE THEM
---------------
1. Open the ChromIQ Gamut Viewer.
2. Press "Follow one device over time…" in the right-hand column.
3. Press "Add profiles…" and choose ALL the .icc files in ONE folder below.
4. Read the graph. Then use "Show me" to look at any single step as a cloud
   of colour, and "coloured by" to ask which WAY it went rather than how far.

Do not mix two folders into one run — they are four different imaginary
devices, and a run is meant to be one device followed through time.

WHAT EACH FOLDER SHOWS
----------------------
{what}

THINGS WORTH TRYING
-------------------
* Pick a single step under "Show me". The cloud shows WHERE in colour that
  step moved, which a line on a graph cannot say.
* Switch "coloured by" from "how far it moved" to "warmer or cooler". A
  distance has no direction: two devices drifting opposite ways give the same
  number and the same cloud.
* Use "from" and "to" to compare any two profiles, not only neighbours.
* In folder 3, compare 2019 with 2021, then 2019 with 2023, and watch the
  cloud go hot and then cold again.
* "Save this as a web page…" writes whichever picture you are looking at, as
  one file that opens in any browser with nothing installed.

You can delete this folder whenever you like. Nothing refers to it.
"""


def main(out: pathlib.Path) -> int:
    spec = importlib.util.spec_from_file_location(
        "mkprof", HERE / "make_demo_profiles.py")
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    import drift_series

    out.mkdir(parents=True, exist_ok=True)
    said, wrong = [], []
    for name, (claim, run_spec) in RUNS.items():
        folder = out / name
        folder.mkdir(parents=True, exist_ok=True)
        mk.RUN = run_spec
        with contextlib.redirect_stdout(io.StringIO()):
            mk.main(folder)
        made = sorted(folder.glob("*.icc"))
        run = drift_series.build(made)
        if len(made) != len(run_spec):
            wrong.append(f"{name}: {len(made)} of {len(run_spec)} written")
        # EACH SET PROVES ITS OWN CLAIM. A demo that does not demonstrate the
        # thing teaches the reader that the feature does not work.
        if name.startswith("1") and not run.steady:
            wrong.append(f"{name}: not a steady creep after all")
        if name.startswith("2") and run.steady:
            wrong.append(f"{name}: no single jump in it")
        if name.startswith("3") and not run.came_back:
            wrong.append(f"{name}: it did not come back")
        if name.startswith("4") and len(run.usable) != 6:
            wrong.append(f"{name}: {len(run.usable)} usable, wanted 6")
        said.append(f"{name}\n    {claim}\n    {len(made)} profiles, "
                    f"ΔE {run.total:.2f} first to last")
        print(f"  {name:34s} {len(made)} profiles  ΔE {run.total:5.2f}  "
              f"steady={run.steady!s:5s} came back={run.came_back}")

    (out / "READ ME FIRST.txt").write_text(
        READ_ME.format(what="\n\n".join(said)), encoding="utf-8")
    if wrong:
        print("\nthese sets do not show what they claim:")
        for line in wrong:
            print(f"  - {line}")
        return 1
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"\n{len(RUNS)} runs written to {out} ({total / 1e6:.0f} MB), "
          f"every set shows what it claims.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="demo-runs")
    raise SystemExit(main(pathlib.Path(ap.parse_args().out)))
