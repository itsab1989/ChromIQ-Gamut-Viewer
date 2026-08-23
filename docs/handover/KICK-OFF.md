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

WHERE THINGS STAND (2026-08-23, v2.52.1 released, 1,117 tests, both gates
green; THE CRON JOB WAS DELETED AT HIS WORD on 2026-08-23 — he asked for a
break, so nothing is running):

  * THE SEAM'S OWN FAULT IS SETTLED AND FIXED, and it was NOT the shared cut
    curve the queue expected. The lid IS the piece's own vertex indices and
    its seam loop's corners move 0.000000000 Lab — two rims that are the same
    array cannot disagree. It is the TRIANGULATION: where the rim is concave,
    a flat lid triangle strung across the dent lies outside the piece
    sideways, past the silhouette, which is also why Detail 40 shrank the
    teeth. Seven of sRGB's 7,999 on his own pair, in three places, all one
    ring from the rim, photographed in red. Withheld from the drawn copy
    only, +0.68 s, guarded so it can never take a share of a lid.
  * THE HATCHING WAS A DEPTH BUFFER, not the lid. gl-plot3d never sets a near
    or far plane, so 0.01/1000 over a unit cube on a 16-bit buffer makes one
    depth step bigger than a Lab. Fitted per frame: 121->10, 158->24, 193->16,
    34->27 at four cameras. The near plane is floored at the library's own
    0.01, which is what stops the fix ever being worse than no fix.
  * A WALL THE LIBRARY PAINTS ON THE CAMERA'S OWN SIDE was Basti's own find
    ("the walls move in front of it sometimes"), caused by giving depth its
    precision back — it stopped hiding it. Cured: 110 of 320 turning frames
    to 3.
  * ⚠ NOT YET RELEASED AND NOT YET AGREED FIXED. A hostile subagent has not
    seen the finished seam, which is the release criterion. Two findings from
    the last hostile review are open and both are real: `fit()` can be
    deleted from the render wrapper with all 1,117 tests green (the planes
    then freeze and a zoom clips the gamut), and the 250 ms sweep period is
    held by nothing. `QUEUE-when-the-cron-resumes.md` ends with the list.
  * Still HIS to decide: the 30-second black window on a slow download
    (one number and one sentence in `_say_if_the_viewer_never_arrives`).
  * Not worth doing unless he asks: removing the redraw blink. Measured, and
    the flash he saw was mostly the test harness driving the window.
  * HIS DISK: `scratch/` is 17 GB, nearly all of it old subagent output
    (`hostile-final` 4.4 G, `hostile` 3.7 G, `hvout` 1.5 G, `hostile-depth`
    1.0 G). All re-derivable. He was told; ASK before clearing any of it.

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
