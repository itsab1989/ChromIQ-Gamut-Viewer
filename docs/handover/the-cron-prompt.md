# The prompt this job runs on

Saved verbatim so a new session can be started from it if the copy on the
machine is ever lost. It fires every ten minutes or so; everything it needs is
in this folder.

```text
SELF-CHECK for the ChromIQ Gamut Viewer fork.

Repo: ~/develop/ChromIQ-Gamut-Viewer/fork
Origin: itsab1989/ChromIQ-Gamut-Viewer. Commit as itsab1989 <itsab1989@users.noreply.github.com>.
Venv: ../gv-venv/bin/python. Both gates: `pytest -q` and `GAMUTVIEW_NO_ARGYLL=1 pytest -q`.
Scratch space: ~/develop/ChromIQ-Gamut-Viewer/scratch  (NOT /private/tmp, which is swept nightly)

FIRST, EVERY CYCLE: read ~/develop/ChromIQ-Gamut-Viewer/START-HERE.md and then
QUEUE-when-the-cron-resumes.md, in full. They carry the ten things Basti
reported from his own first hands-on session on 2026-08-20, each with a named
place to look and the traps already known — plus what is proved DONE and must
not be rebuilt. Work what is left in them; do not re-derive their diagnoses.

WHAT IS LEFT, in order. Do not idle:
  1. ITEM 8, THE CAP — and it is BASTI'S DECISION, not work to be done
     unasked. His idea is drawn and it looks right (nine pictures in
     fork/docs/probes/inside-view/the-lid/). It is a prototype: 322 of the
     lid's 1,149 corners fail a strict containment test, because the two
     pieces are classified separately instead of sharing the cut. The real fix
     is ONE SHARED CUT CURVE in the re-cut. Do not ship it as it stands and do
     not decide it for him.
  2. Finish the "can every script still run" sweep — 16 of 22 answered. Left:
     audit_showcase_page, audit_the_controls_can_be_shut,
     audit_the_page_at_any_size, audit_the_switch_changes_nothing,
     check_layout, drive_all_combinations. FOREGROUND BATCHES OF TWO OR THREE:
     a background sweep was killed between sessions three times.
  3. Anything the checks turn up.

EVERYTHING ELSE ON THE ORIGINAL LIST IS DONE — all ten items but the cap,
measured and mostly mutation-proved, shipped through v2.43.1. Do not rebuild
any of it. Read the queue before believing anything is missing: a stale list
once had me overwrite an existing, better check with Write.

HOW TO WORK, every cycle:
  * Be the critic. Try to BREAK it. Read the real code and cite it.
  * CROSS the options; never one at a time. A sweep that finds nothing must
    itself be mutation-tested, and the mutation must be PROVEN to land.
  * MEASURE THE RIGHT PAIR — at HIS settings, not the defaults.
  * Cases whose answer is KNOWN IN ADVANCE, and the failure directions.
  * A MEASUREMENT THAT CANNOT SEE THE THING LOOKS EXACTLY LIKE ONE THAT FOUND
    NOTHING WRONG. Every new rule must refuse an empty or implausibly small
    population. This has cost four separate days.
  * DRIVE IT ON SCREEN, photograph it, and LOOK at the picture yourself —
    screenshots do not reach him, and reasoning from trace data once shipped a
    regression that the first screenshot settled in a glance.
  * REBUILD docs/pages AND docs/screenshots when a change shows in them, and
    PUSH them. Shipping the app is not shipping the page.
  * COMMIT AND PUSH AFTER EVERY VERIFIED STEP. Never `git add -A` — name the
    files, since other processes edit this tree.
  * Clean up every temp folder and kill every browser afterwards. BASTI'S OWN
    APP WINDOW IS NOT YOURS TO KILL.
  * Every new option needs a friendly, extensive, easy tooltip naming the exact
    control — outcome and prerequisite, not mechanism. Hover tooltips stay
    SHORT (200 characters); the long version goes behind the ⓘ. He asked for
    that in as many words.
  * Watch the usage window: prefer one focused run to a broad sweep, and say
    what a cycle cost.

WHEN IT MAY STOP: when the queue is done, driven on screen, audited end to end,
in a tagged release with pages and screenshots rebuilt and pushed, and Basti
has said so explicitly. Then delete this job and say plainly that it is done.

STANDING RULES: ON-SCREEN TESTS HAVE STANDING PERMISSION. SUBAGENTS one at a
time and only if asked. NO personal data on GitHub — no customer names, no
employers, in files, release notes or git history, EXCEPT Sebastian Reiprich's
own author credit, which he asked for. Never touch ~/ChromIQ or
~/Downloads/Argyll_V3.5.0_orig; leave ~/Desktop/ChromIQ-demo-profiles alone.
Never delete Basti's files.
```
