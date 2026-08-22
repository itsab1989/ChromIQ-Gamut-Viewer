# Start here to carry on with the ChromIQ Gamut Viewer fork

Paste the block below into a new session. Everything it refers to is in this
folder and mirrored at `fork/docs/handover/` on GitHub.

---

```text
CARRY ON WITH THE ChromIQ Gamut Viewer FORK.

Repo: ~/develop/ChromIQ-Gamut-Viewer/fork
Origin: itsab1989/ChromIQ-Gamut-Viewer. Commit as itsab1989 <itsab1989@users.noreply.github.com>.
Venv: ../gv-venv/bin/python
Both gates: `pytest -q` and `GAMUTVIEW_NO_ARGYLL=1 pytest -q`
Scratch: ~/develop/ChromIQ-Gamut-Viewer/scratch  (NOT /private/tmp, swept nightly)

FIRST, EVERY TIME: read START-HERE.md and QUEUE-when-the-cron-resumes.md in
this folder, in full. They carry the state, what is proved DONE, and the traps
that have each cost a night. Do not re-derive their diagnoses.

WHERE THINGS STAND (2026-08-22, v2.52.1, 1,055 tests):
  * Everything Basti reported by hand is shipped. The script sweep is finished.
  * The lid ("Close where it is cut") had six faults found and fixed; it stays
    OFF by default. With it on the seam shows the triangles of the shape the
    lid is cut from, and raising Detail shrinks them. Not recommended as-is;
    the remaining work is ONE SHARED CUT CURVE in the re-cut.
  * Still HIS to decide: the 30-second black window on a slow download
    (one number and one sentence in `_say_if_the_viewer_never_arrives`).
  * Not worth doing unless he asks: removing the redraw blink. Measured, and
    the flash he saw was mostly the test harness driving the window.

HOW TO WORK — this is the part that matters:
  * BE THE CRITIC. Try to break it. Read the real code and cite file:line.
  * BUILD SHAPES WHOSE ANSWER IS ARITHMETIC. This is the best instrument in
    the repository: `scripts/make_awkward_shapes.py` writes measurements the
    window can open, each awkward in a NAMED way. An ellipsoid has an exact
    volume and two of them meet in an exact ellipse, so a number can be wrong
    in a way no opinion can argue with. It found a wrong lid, a wrong drift,
    and retired two of my own false claims.
  * TEST THE CLAIM THE CODE ITSELF MAKES. The drift fault came from checking a
    docstring's promise -- patches paired on device values, not sample numbers
    -- with a shuffle.
  * A MEASUREMENT THAT CANNOT SEE THE THING LOOKS EXACTLY LIKE ONE THAT FOUND
    NOTHING WRONG. Every new rule must refuse an empty or implausibly small
    population. MUTATION-PROVE every check, and PROVE THE MUTATION LANDED --
    three mutations in one session silently did nothing and the tests "passed".
  * DRIVE IT ON SCREEN AND LOOK AT THE PICTURE. Screenshots do not reach him.
    A striped lid and a hatched surface were both invisible to every number.
  * CROSS THE OPTIONS. Measure at HIS settings, not the defaults: his own
    profile is at ~/Library/ColorSync/Profiles/ET8550_EpsPremSG_i1Studio_AdobeRGB_Mar26.icc
  * COMMIT AND PUSH AFTER EVERY VERIFIED STEP. Never `git add -A` -- name the
    files, other processes edit this tree.
  * REBUILD docs/pages and docs/screenshots when a change shows in them. A
    saved page's <head> is built in FOUR places; count the artifacts.
  * Say what each stretch of work cost, and correct yourself in public when a
    measurement turns out to have been wrong.

RELEASES: bump python/version.py, prepend CHANGELOG.md, both gates green, tag,
push branch and tag, then CONFIRM 11 ASSETS on the release.

STANDING RULES: on-screen tests have standing permission. Subagents one at a
time and only if asked -- a hostile review of the lid found six real faults, so
they are worth asking for. NO personal data on GitHub: no customer names, no
employers, in files, release notes or history, EXCEPT Sebastian Reiprich's own
author credit. Never touch ~/ChromIQ or ~/Downloads/Argyll_V3.5.0_orig; leave
~/Desktop/ChromIQ-demo-profiles alone. Never delete Basti's files.

WHEN TO STOP: when he says so.
```
