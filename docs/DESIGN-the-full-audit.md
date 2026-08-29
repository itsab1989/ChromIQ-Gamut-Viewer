# The full audit — a design, not yet built

Written 2026-08-29, for Basti's request: *"a full audit script that ships with
the app in case anyone wants to work on it in the future… test every possible
option, combination of options and make sure that the ui works as intended…
give a detailed report of its findings in a friendly, extensive and easy to
understand way… saved as a txt file on the user's desktop… room for notes from
me… able to adapt to new functions being possibly added."*

**Nothing is built yet.** The open questions at the end change the shape of it,
and this project's own record says a stale task list once had somebody
overwrite an existing, better check. So: what exists first, then the gap, then
the plan, then the questions.

---

## 1. What already exists — read this before proposing anything

Fifty-eight scripts in `scripts/`. The relevant ones:

| what | where | lines | what it already does |
|---|---|---|---|
| **every control, pressed** | `scripts/audit.py` | 1,231 | Presses every control and asks *"does the picture change, and does it come back?"* **It finds the controls rather than listing them** — from `GamutApp._persisted()` and `_shape_controls()` for the window, and from `data-cq` attributes for a saved page. |
| **every combination** | `scripts/drive_all_combinations.py` | 417 | Two phases: every combination at the figure level (invariants), then a representative set through the real window comparing screen against what a save writes. 6,912 combinations, 65,836 checks. |
| 35 further audits | `scripts/audit_*.py`, `drive_*.py`, `check_*.py` | ~11,000 | One subject each — the panel, hovers, readability, bad files, two rooms, other engines, what you save, promises, sizes… |
| **demo data, already built** | `make_awkward_shapes.py`, `make_demo_profiles.py`, `make_demo_runs.py`, `make_showcase_measurements.py`, `demo_profiles.py` | ~810 | Measurements built to break the lid; one imaginary printer profiled four times over five years; four runs for the timeline; four invented papers. **The "create demo projects" half of the request is already written.** |
| the shared protocol | all of them | — | **Exit 0 = clean, exit 1 = a problem.** On success they print a plain-language sentence beginning `Clean:` — e.g. *"Clean: every bad file was explained, and none of them took the window down."* |

⚠ **`audit.py`'s discovery is the property the request asks for and it already
exists.** "The script should be able to adapt to new functions being possibly
added, so not static with the current version" — that is `audit.py`'s stated
design: *"a control added tomorrow is audited tomorrow, by the person who added
it, without editing this file."* The new tool must not replace that; it must
stand on it.

## 2. The gap — what is genuinely missing

1. **No single entry point.** Thirty-seven scripts, each run by hand. There is
   no `run_the_full_audit`.
2. **Nothing writes a report file.** Every script prints to the terminal and
   returns an exit code. Searched: no script writes a `.txt`, and none mentions
   the Desktop.
3. **No notes-space, no round trip.** Basti asked for a file he can annotate
   ("confirmed / my findings") and paste back into an agent.
4. **No reproduction guidance.** A failing audit prints what it measured, not
   *"here is how you see this yourself: open X, tick Y, look at Z."*
5. **No cleanup contract.** The makers write demo files; nothing guarantees
   they are removed afterwards.
6. **Failures are freeform.** Successes are uniform (`Clean: …`); failures are
   whatever each script chose to print.

## 3. The journey, end to end

**What the user has:** a checkout, a venv, and a screen.

**What they type:**

```bash
../gv-venv/bin/python scripts/run_the_full_audit.py
```

**What happens, in plain sight:** it prints what it is about to do and how long
it will take; builds its demo files in a temp folder it owns; runs each check,
saying which one is running and whether it came back clean; and at the end
prints where the report went.

**Where the files land** — the whole point of the request:

| what | where |
|---|---|
| the report | **the Desktop**, `ChromIQ audit report YYYY-MM-DD HHMM.txt` |
| the screenshots the report refers to | a folder beside it, same name |
| the demo files it made | a temp folder it owns, **deleted at the end** |

Desktop, per OS: macOS/Linux `~/Desktop` if it exists, else `~`;
Windows via `winreg` for a moved Desktop, else `%USERPROFILE%\Desktop`. If none
exists, write beside the checkout and **say so on the terminal** rather than
failing.

⚠ **NOTHING THE USER MADE IS EVER TOUCHED.** The tool writes only to its own
temp folder and to the two Desktop items. An existing report is never
overwritten — the timestamp is in the name, so each run is its own file.

## 4. The report, and the round trip

Plain text, wide enough to read, structured so an agent can parse it and a
person can write in it:

```
================================================================================
  ChromIQ Gamut Viewer — audit report
  2026-08-29 21:47   ·   version 2.52.1   ·   macOS 15.6   ·   this took 41 min
================================================================================

WHAT THIS IS
  This file lists everything the audit looked at and what it found. You do not
  need to understand the internals to use it. Each finding tells you what was
  expected, what happened instead, and exactly how to see it yourself.

  There is a NOTES line under every finding. Write in it. When you are done you
  can hand this whole file to an AI agent and it will know what you confirmed.

WHAT IT LOOKED AT
  37 checks · 6,912 option combinations · 214 controls · 25 saved pages
  Clean: 34        Needs your eye: 2        Could not run: 1

--------------------------------------------------------------------------------
  1. NEEDS YOUR EYE — the walls are drawn in front of the shape on some frames
--------------------------------------------------------------------------------
  WHAT SHOULD HAPPEN
    The grey walls of the box are behind the shape. Whichever way you turn it,
    the coloured shape is never covered by a wall.

  WHAT HAPPENED
    On 75 of 160 frames while the picture turned, a wall was drawn over the
    shape — up to 4,707 pixels of it. Worst frame: shots/01-wall-frame073.png

  HOW TO SEE IT YOURSELF
    1. Open docs/pages/22-a-run-with-its-shapes.html in a browser.
    2. Let it turn. Watch the left side of the shape.
    3. About eight times a revolution a grey panel crosses in front of it.

  WHY IT MATTERS
    The picture is a measurement. Anything drawn over the shape hides part of
    what a printer can do.

  YOUR NOTES  (confirmed? what did you see? anything else?)
  > ______________________________________________________________________
  > ______________________________________________________________________
```

**For the AI round trip:** a machine-readable block at the end of the file,
inside a fenced region, carrying the same findings with stable ids — so an
agent reading the pasted file gets structure, and a person reading it sees
only a tidy appendix.

⚠ **IT MUST NOT CHANGE CODE.** Basti was explicit. The tool reports and
photographs; it never edits. That is a property of the design, not a flag.

## 4a. ⚠ EVERY FINDING CARRIES ITS PICTURE — this is a hard requirement

Basti, 2026-08-29: *"we already noticed that you judging from off screen
measurements and data points only tends to get things wrong. thats why i
demanded you to analyse real screenshots for your diagnostics."*

So the report is built around photographs, not around counters:

* **No finding is printed without a screenshot beside it.** If a check cannot
  produce a picture of what it found, the report says so IN the finding —
  *"this one is measured, not photographed; judge it yourself by…"* — rather
  than presenting a number as if it were evidence.
* **A "clean" verdict on a visual check also carries its picture**, so the
  reader can see what right looks like. (This is open question 5.)
* **The renderer is named on every picture**: QtWebEngine is what the
  application uses; headless chromium falls back to SwiftShader; headless
  WebKit is the real Apple GPU. Depth ties differ between them, and a verdict
  from the wrong renderer has already misranked a finding in this project.
* **Moving pictures need moving frames.** Faults that live in a band of camera
  angle under a degree wide are invisible to still cameras: eleven stills
  reported "0 wall pixels over the shape" where 160 turning frames found 75.
  Any check about how the picture behaves WHILE IT MOVES must sample frames
  while it moves, and must prove the frames actually differ.

The reason, in one line: in a single session five numeric measurements each
produced a confident, clean-looking, wrong verdict, and a photograph overturned
every one. No number corrected a picture.

## 5. How it stays current

* **Checks are discovered, not listed** — `scripts/audit_*.py`, `drive_*.py`,
  `check_*.py` are globbed. A check added tomorrow runs tomorrow.
* **Controls are discovered** by standing on `audit.py`'s own discovery.
* **The tool refuses an implausible population.** If it finds fewer than ~25
  checks or ~50 controls it says *"this found almost nothing, which usually
  means it was run from the wrong folder"* and exits 1. This project's single
  most expensive lesson is that a measurement which cannot see the thing looks
  exactly like one that found nothing wrong.
* **A `--prove` self-test**: break something on purpose in a copy, and require
  the audit to fail. A sweep that finds nothing proves nothing until it has
  been made to find something.

## 6. Edge cases it must hold for

No ArgyllCMS · no ffmpeg · no network · no screen (says which checks it cannot
judge rather than printing the same word "Clean" — two audits already had this
fault) · no demo profiles · a read-only Desktop · a second run in the same
minute · interrupted with Ctrl-C (temp folder still removed) · a check that
hangs (per-check timeout, reported as "could not run") · a check that crashes
the whole process (each runs in a **subprocess** — a QtWebEngine window and
playwright do not survive each other, and that pairing has already killed a
gate outright).

## 7. What I am NOT proposing

* Not replacing `audit.py` or `drive_all_combinations.py`. They are the engine.
* Not a new result protocol for 37 scripts. Exit codes plus the `Clean:`
  sentence already carry it.
* Not a GUI. This is a developer and power-user tool.

## 8. OPEN QUESTIONS — these change the build, so I am not guessing

1. **How long may a full run take?** Driving the real window is minutes per
   check; the figure level is seconds. Options: (a) a **quick** pass of a few
   minutes and a **full** pass of an hour, (b) full only, (c) full by default
   with `--quick`. My recommendation: (a).
2. **Does it drive the real window by default?** On-screen checks are the ones
   that find real faults, but they take over the screen and cannot run on a
   machine with no display. Default to including them, with `--no-screen`?
3. **One report file per run, or one rolling file you keep annotating?**
   Timestamped-per-run is safer; a rolling file is easier to live with.
4. **How much does an all-clean report say?** A one-page "34 checks, all
   clean, here is what that means" — or the full list every time so you can see
   what was covered?
5. **Should it write the screenshots for CLEAN checks too**, or only for
   findings? All of them is a lot of files; only findings means you cannot see
   what "right" looks like for comparison.
6. **Is `~/Desktop` right for you specifically**, or would you rather it landed
   in `~/develop/ChromIQ-Gamut-Viewer/`? The request says Desktop; I want to be
   sure that is still true when it runs every day.
7. **What is a "demo project" here?** This app opens `.ti3` measurements, ICC
   profiles, charts and images — it has no project format of its own. I read
   the request as "build demo measurements and profiles, use them, delete
   them", which the existing makers already do. Confirm?
8. **Name.** `scripts/run_the_full_audit.py`? It sits beside 37 `audit_*.py`
   and must not be mistaken for one of them.

## 9. Rating of this design, honestly

| | | |
|---|---|---|
| correctness | 7 | The protocol it stands on (exit codes, `Clean:`) is real and verified. But it inherits every blind spot of the 37 checks, and this week alone found three of them blind. |
| robustness | 8 | Subprocess isolation, per-check timeouts, refuses an implausible population, cleans up on Ctrl-C. |
| maintainability | 9 | Discovers rather than lists; adds no protocol; ~500 lines standing on ~12,000 that already exist. |
| efficiency | 6 | A full pass is tens of minutes because driving a real window is slow. Question 1 decides whether that is acceptable. |

**Below 9 on correctness, and the reason is worth stating:** this tool makes
the existing checks *visible*, not *better*. If a check is blind, the report
will cheerfully print `Clean` for it. Question: should the first version also
run each check's `--prove` mutation where one exists (9 do today), so the
report can say **"this check was proved able to see its own fault"** beside
each clean verdict? That would raise correctness to 9 and roughly double the
runtime. I think it is worth it, and it is question 9.
