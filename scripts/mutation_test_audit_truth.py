"""Put the fault back, and see whether audit_truth still notices.

WHY THIS FILE EXISTS. audit_truth found a real fault on its first run — a
switch that said the box was off over a picture that drew it — and has been
quiet since. Quiet is not proof. A check phrased in terms of the thing it
guards cannot catch that thing being removed, and this project has been bitten
by exactly that four times.

The honest attempt to prove it, made when the audit was written, was
INCONCLUSIVE and was reported as such: the mutations crashed the window rather
than making it lie, so nothing was learned about the audit's reach. This one
mutates differently — not the drawing, but the LINK between a control and the
drawing, which is the only kind of fault that audit exists to catch:

  the box       the picture is drawn with the walls whatever the switch says
  the readout   the number beside the solidity slider is written once and
                never updated again
  the threshold the slider's value never reaches the picture, so every
                colour is drawn however far it is dragged

Each of these is a real fault that has happened here in one form or another,
and each is invisible on screen unless somebody counts.

    python scripts/mutation_test_audit_truth.py

Exit code 1 if any mutation goes UNNOTICED — which would mean the audit's
silence is worth nothing.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

# THE SETTINGS GO SOMEWHERE THROWAWAY. The audit under test isolates them on
# import as well; said here too, because the check that keeps drivers honest
# reads the file rather than the import graph -- and it caught this one.
import prefs  # noqa: E402

prefs.use_a_scratch_store()

#: name → (what is broken, the check that must report it)
MUTATIONS = {
    "box": ("the box switch no longer reaches the picture",
            "show the box and its grid"),
    "readout": ("the number beside the solidity slider stops being written",
                "the number beside it"),
    "threshold": ("the hide-anything-under value never reaches the picture",
                  "hide anything under"),
}


def apply(which: str) -> None:
    """Break one link between a control and the picture."""
    import gamut_app

    if which == "box":
        was = gamut_app.GamutApp._render_options

        def always_boxed(self):
            options = was(self)
            options["grid"] = True
            return options

        gamut_app.GamutApp._render_options = always_boxed
        # And the run's picture, which builds its own options dictionary.
        panel = gamut_app.TimelineDialog
        inner = panel._how_the_window_draws_shapes

        def boxed(self):
            look = inner(self)
            look["grid"] = True
            return look

        panel._how_the_window_draws_shapes = boxed
    elif which == "readout":
        # FREEZE THE NUMBER BESIDE THE SOLIDITY SLIDER, which is exactly the
        # fault that was reported: "how solid it looks says 100% although the
        # slider is more in the middle and this is what the viewer would
        # suggest as well". Nothing else changes -- the picture still fades
        # correctly, so only a check that compares the CONTROL with the
        # READOUT can see it.
        real_init = gamut_app.GamutApp.__init__

        def deaf(self, *args, **kwargs):
            real_init(self, *args, **kwargs)
            self._opacity_lbl.setText = lambda *_a, **_k: None

        gamut_app.GamutApp.__init__ = deaf
    elif which == "threshold":
        panel = gamut_app.TimelineDialog
        panel._cut_off = lambda self: 0.0
    else:
        raise SystemExit(f"no such mutation: {which}")


def run_one(which: str) -> tuple[bool, str]:
    """Run the audit in a fresh process with one mutation applied."""
    out = subprocess.run(
        [sys.executable, str(HERE / "mutation_test_audit_truth.py"),
         "--child", which],
        capture_output=True, text=True, timeout=900)
    return out.returncode != 0, out.stdout


def child(which: str) -> int:
    sys.argv = ["audit_truth"]
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_truth_under_test", HERE / "audit_truth.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)          # settings are isolated on import
    apply(which)
    return module.main()


def main() -> int:
    if "--child" in sys.argv:
        code = child(sys.argv[sys.argv.index("--child") + 1])
        sys.stdout.flush()
        os._exit(code)

    problems = []
    for which, (broken, must_name) in MUTATIONS.items():
        print(f"\n  MUTATION: {broken}")
        noticed, said = run_one(which)
        named = must_name in said
        if noticed and named:
            print(f"      caught, and named it: “{must_name}”")
            continue
        if noticed and not named:
            # CAUGHT, BUT BY THE WRONG CHECK. Worth knowing: a check that
            # fails for the wrong reason will go quiet the moment somebody
            # fixes the reason it happened to notice.
            problems.append(f"[mutation] {which}: the audit failed, but not "
                            f"on “{must_name}” — it noticed something else")
            print("      caught by SOMETHING ELSE")
            continue
        problems.append(f"[mutation] {which}: {broken} — and the audit still "
                        f"reported everything as agreeing")
        print("      NOT NOTICED")

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} mutation(s) went unnoticed. audit_truth's "
              f"silence does not mean what it claims to mean.")
        return 1
    print("  Every broken link was caught, by the check that should catch it. "
          "audit_truth's silence is worth something.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
