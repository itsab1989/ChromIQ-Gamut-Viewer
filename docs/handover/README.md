# Picking this up from nothing

Everything a new session needs to carry on, kept here so it survives the
machine it was written on. Asked for in as many words: *"even if it is deleted
from my drive i can always reach it from a new session and proceed from where
we left of"*.

Read them in this order:

1. **[the-cron-prompt.md](the-cron-prompt.md)** — the standing instructions,
   verbatim. Paste it into a new session and the job runs as before.
2. **[START-HERE.md](START-HERE.md)** — the state of the work, the rules
   learned the hard way, and the traps that have each cost a night.
3. **[QUEUE-when-the-cron-resumes.md](QUEUE-when-the-cron-resumes.md)** — the
   ten things reported from the first hands-on session, what is proved done,
   and what is still Basti's decision rather than work to be done unasked.

## The three files are copies

They live on the machine at `~/develop/ChromIQ-Gamut-Viewer/`, beside the
checkout rather than inside it, and this folder is a copy taken when it was
last refreshed. To bring it up to date:

```bash
cd ~/develop/ChromIQ-Gamut-Viewer
cp START-HERE.md QUEUE-when-the-cron-resumes.md fork/docs/handover/
cd fork && git add docs/handover && git commit -m "Refresh the handover" && git push
```

If the two disagree, **the copies outside the checkout are the live ones** —
this folder is the lifeboat, not the original.

## What is not here, and where it is

* The work itself is the repository around this folder, and its history is the
  real record of what was done and why — every commit says what was measured.
* The pictures the decisions were made from are in `docs/probes/`: the lid
  prototype in `inside-view/the-lid/`, and the hover wall in `the-hover-wall/`.
* The releases, with their notes, are the tags — `v2.50.3` is the newest.

## What is still open

Three things, all of them deliberately left to Basti and none of them blocked
on work:

* **The cap** — his idea, drawn and looking right, but a prototype. The real
  fix is one shared cut curve in the re-cut. Not to be shipped as it stands.
* **The black window on a slow download** — thirty seconds before the page
  says anything. That threshold is deliberate; changing it is one number and
  one sentence.
* **`_families`, 1,026 characters on hover** — the last wall of text, in a box
  with no ⓘ to move the words into, so it is layout work in a function whose
  own comments record two attempts that broke the column.
