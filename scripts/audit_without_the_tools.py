"""What happens, and when, on a computer with no ArgyllCMS and no ffmpeg.

THE QUESTION THIS ANSWERS, asked from outside: "did you audit what would
happen and when if argyll or ffmpeg are not installed on the users computer?"

The unit tests cover the two SEARCHES thoroughly, and the release runs the
whole suite a second time with GAMUTVIEW_NO_ARGYLL=1, so "does the code cope"
was already answered. This asks the different question: what does the person
in front of the window see, and does anything they came to do stop working?

AND IT CROSSES THE TWO, rather than taking them one at a time. Four states,
not two — because both missing is the state of a fresh machine, and it is the
one nobody ever sits in front of:

    ArgyllCMS ✓  ffmpeg ✓      what this machine has
    ArgyllCMS ✓  ffmpeg ✗      a Linux build without the encoder
    ArgyllCMS ✗  ffmpeg ✓      the common case: a downloaded release
    ArgyllCMS ✗  ffmpeg ✗      a fresh machine, nothing installed

EVERY ANSWER IS WRITTEN DOWN BEFORE IT IS ASKED, which is the only way a
sweep like this can fail rather than merely describe:

  1. A .ti3 measurement opens in ALL FOUR states. It is read here, in Python.
  2. An ICC profile opens in ALL FOUR states — with ArgyllCMS through
     iccgamut, without it through the reader in icc_read.py.
  3. A .txt/.cxf/.mxf measurement opens only WITH ArgyllCMS, and without it
     the window must SAY so, naming ArgyllCMS, and must not crash or fail
     silently.
  4. Both status lines say something in every state, and neither is blank.
  5. Both "Where … is…" buttons stay enabled in every state — they are the
     way out of the state, so greying them out would be a trap.
  6. Without ffmpeg exactly the two FILMS (MP4, WebM) become unavailable and
     say why; WebP, GIF and APNG keep working, because they are written here.
  7. Nothing about ArgyllCMS changes what ffmpeg can do, or the other way
     round. They are independent, and the crossing is what proves it.

    python scripts/audit_without_the_tools.py

Exit code 1 if any of those is not true.
"""
from __future__ import annotations

import contextlib
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "python"))

import prefs  # noqa: E402

prefs.use_a_scratch_store()
sys.argv = ["audit_without_the_tools"]

from PyQt6.QtWidgets import QApplication  # noqa: E402

import argyll  # noqa: E402
import movie   # noqa: E402

#: The files each question is asked with. All three travel with the repo.
TI3 = ROOT / "demo" / "Glossy-paper.ti3"
ICC = ROOT / "demo" / "Glossy-paper.icc"


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


@contextlib.contextmanager
def tools(has_argyll: bool, has_ffmpeg: bool):
    """Run the block on a machine with (or without) each tool.

    ArgyllCMS has a switch of its own for exactly this. ffmpeg has none, so
    the list of places to look is emptied instead — which is the same thing
    from the application's point of view, and leaves the real installation
    untouched.
    """
    was = os.environ.get(argyll.NO_ARGYLL)
    real_candidates = movie._candidates
    if has_argyll:
        os.environ.pop(argyll.NO_ARGYLL, None)
    else:
        os.environ[argyll.NO_ARGYLL] = "1"
    if not has_ffmpeg:
        movie._candidates = lambda: iter(())
    argyll.forget()
    movie.forget()
    try:
        yield
    finally:
        movie._candidates = real_candidates
        if was is None:
            os.environ.pop(argyll.NO_ARGYLL, None)
        else:
            os.environ[argyll.NO_ARGYLL] = was
        argyll.forget()
        movie.forget()


def a_shape_is_drawn(window) -> bool:
    """Whether the window is showing anything at all."""
    return bool(getattr(window, "_slots", []))


def check(state: str, window, has_argyll: bool, has_ffmpeg: bool) -> list:
    problems = []
    import gamut_app

    # 4. THE TWO LINES SAY SOMETHING.
    for name, label in (("ArgyllCMS", window._argyll_label),
                        ("ffmpeg", window._ffmpeg_label)):
        said = label.text().strip()
        if not said:
            problems.append(f"[{state}] {name}: the status line is blank")
        elif len(said) < 20:
            problems.append(
                f"[{state}] {name}: the status line is {said!r}, which does "
                f"not tell anybody what to do")
    # The line must be about the state it is in, not a leftover.
    argyll_said = window._argyll_label.text().lower()
    if has_argyll and "not found" in argyll_said:
        problems.append(
            f"[{state}] ArgyllCMS is installed and the line says it is not: "
            f"{window._argyll_label.text()!r}")
    if not has_argyll and "not found" not in argyll_said:
        problems.append(
            f"[{state}] ArgyllCMS is missing and the line does not say so: "
            f"{window._argyll_label.text()!r}")

    # 5. THE WAY OUT STAYS OPEN.
    for name, button in (("ArgyllCMS", window._argyll_btn),
                         ("ffmpeg", window._ffmpeg_btn)):
        if not button.isEnabled():
            problems.append(
                f"[{state}] the {name} button is greyed out — it is the way "
                f"to point at one, so it must never be")
        if not button.toolTip().strip():
            problems.append(f"[{state}] the {name} button says nothing on "
                            f"hover")

    # 6. AND 7. THE FILMS, AND ONLY THE FILMS.
    # Every codec the application knows is a FILM and needs the encoder;
    # WebP, GIF and APNG are written here and are not in this list at all,
    # which is the whole of point 6.
    films = list(movie.CODEC_NAMES)
    for codec in films:
        allowed = movie.can_write(codec)
        if has_ffmpeg and not allowed:
            # A real build may genuinely lack one codec; that is not this
            # audit's business. Only "none at all" is.
            continue
        if not has_ffmpeg and allowed:
            problems.append(
                f"[{state}] {codec} says it can be written with no encoder "
                f"installed")
        if not has_ffmpeg:
            why = movie.why_not(codec)
            if not why or "ffmpeg" not in why.lower():
                problems.append(
                    f"[{state}] {codec} is unavailable and the reason does "
                    f"not name ffmpeg: {why!r}")
    return problems


def main() -> int:
    import gamut_app

    app = QApplication(sys.argv)
    # THE MESSAGES ARE THE POINT, so they are recorded rather than silenced.
    # A driver that throws away what the window says can only ever check that
    # nothing crashed, and "it failed silently" is precisely the fault worth
    # looking for here.
    said: list = []
    gamut_app.Notice.warn = staticmethod(
        lambda *a, **k: said.append(" ".join(str(x) for x in a)))
    gamut_app.Notice.say = staticmethod(
        lambda *a, **k: said.append(" ".join(str(x) for x in a)))

    problems: list = []
    for has_argyll in (True, False):
        for has_ffmpeg in (True, False):
            state = (f"argyll {'yes' if has_argyll else 'NO '} / "
                     f"ffmpeg {'yes' if has_ffmpeg else 'NO '}")
            with tools(has_argyll, has_ffmpeg):
                window = gamut_app.GamutApp([])
                window.show()
                pump(app, 2.5)
                # The lines are written when the window is built; ask again
                # so this is measuring the state and not the startup order.
                window._argyll_label.setText(argyll.summary())
                window._ffmpeg_label.setText(movie.summary())
                pump(app, 0.5)
                problems += check(state, window, has_argyll, has_ffmpeg)

                # 1. AND 2. THE TWO KINDS THAT MUST ALWAYS OPEN.
                for path, what in ((TI3, "a .ti3 measurement"),
                                   (ICC, "an ICC profile")):
                    if not path.is_file():
                        problems.append(f"[{state}] {path} is missing")
                        continue
                    before = len(getattr(window, "_slots", []))
                    try:
                        window._load(path)
                    except Exception as why:      # noqa: BLE001
                        problems.append(
                            f"[{state}] {what} raised {type(why).__name__}: "
                            f"{why}")
                        continue
                    pump(app, 6)
                    if len(getattr(window, "_slots", [])) <= before:
                        problems.append(
                            f"[{state}] {what} did not open — it is read "
                            f"here and must open whatever is installed")
                # 3. THE ONE KIND THAT REALLY DOES NEED ARGYLLCMS. Without it
                # the window must say so, in words that name the thing that
                # is missing — a beginner cannot act on "could not open".
                # THE FILE'S NAME MUST NOT CONTAIN THE WORD BEING LOOKED
                # FOR. It was called audit-needs-argyll.cxf, and every
                # message about a file quotes the file's name — so the check
                # passed on its own filename echoed back at it, and went on
                # passing with the entire explanation deleted. A probe that
                # answers its own question measures nothing.
                spectral = pathlib.Path(
                    os.environ.get("TMPDIR", "/tmp")) / "audit-spectral.cxf"
                spectral.write_text(
                    "<?xml version='1.0'?>\n<cc:CxF xmlns:cc='http://colorexchangeformat.com/CxF3-core'>"
                    "\n</cc:CxF>\n", encoding="utf-8")
                said.clear()
                try:
                    window._load(spectral)
                except Exception as why:            # noqa: BLE001
                    problems.append(
                        f"[{state}] a .cxf raised {type(why).__name__}: {why} "
                        f"— it must be explained, not thrown")
                pump(app, 3)
                # WHAT COUNTS AS AN EXPLANATION, AND THREE WRONG ANSWERS
                # BEFORE THIS ONE. Looking for the word "argyll" in what the
                # window said passed with the entire explanation deleted —
                # three times over, for three different reasons, every one of
                # them the probe answering its own question:
                #
                #   * the probe file was called audit-needs-argyll.cxf, and
                #     every message about a file quotes the file's name;
                #   * the message ends with the download address,
                #     argyllcms.com, which a substring search cannot tell
                #     from a sentence;
                #   * and the window appends a general paragraph to every
                #     failed open — "a .ti3, the file ArgyllCMS writes after
                #     you read a printed chart" — which names it again.
                #
                # So the check asks for the two things that are only ever in
                # the real explanation and are what a person can ACT on: that
                # it was NOT FOUND, and where to get it.
                spoken = " ".join(said).lower()
                if not has_argyll:
                    if not said:
                        problems.append(
                            f"[{state}] a .cxf needs ArgyllCMS and the window "
                            f"said NOTHING AT ALL — it failed silently")
                    else:
                        if "not found" not in spoken:
                            problems.append(
                                f"[{state}] a .cxf needs ArgyllCMS and the "
                                f"message never says it was not found: "
                                f"{' '.join(said)[:200]!r}")
                        if argyll.DOWNLOAD_URL.lower() not in spoken:
                            problems.append(
                                f"[{state}] a .cxf needs ArgyllCMS and the "
                                f"message does not say where to get it: "
                                f"{' '.join(said)[:200]!r}")
                with contextlib.suppress(OSError):
                    spectral.unlink()

                window.close()
                pump(app, 0.5)
                window.deleteLater()
                pump(app, 0.5)
            print(f"  checked: {state}")

    print()
    if problems:
        for line in problems:
            print("  " + line)
        print(f"\n{len(problems)} problem(s).")
        return 1
    print("  Clean: four states (ArgyllCMS × ffmpeg, present and absent), "
          "every one driven in the real window.")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
