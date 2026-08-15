# Taking the picture export into ChromIQ

Notes for whoever folds this viewer's export into ChromIQ itself. Written
while it was built, so the reasons are the real ones rather than reconstructed.

## The shape of it

Four modules, and only one of them knows about Qt:

| Module | Needs Qt | What it is |
|---|---|---|
| `picture.py` | no | the **rules**: which formats exist, what each can hold, how many frames close a loop, what to call the file, how big it will be, the ready-made looks, and the contrast arithmetic |
| `movie.py` | no | finding an encoder, what it can write, quality → codec settings, and the two **writers** (a pipe to ffmpeg, and Pillow) |
| `looks.py` | no | saved looks: one JSON file each, in ChromIQ's own presets folder |
| `gamut_app.py` | yes | the dialog, the section in the column, and grabbing the frames |

**Everything worth testing is outside Qt.** That was deliberate and it is why
the tests run in eight seconds without a display.

## The five things that cost a day each

1. **`runJavaScript` does not wait for a promise.** Timing measured through it
   is the call, not the work — a first attempt measured 33 ms for something
   that took 630. And a script that has *finished* says nothing about what is
   on screen: WebGL composites on its own schedule. Wait for **two**
   `requestAnimationFrame` ticks or frames get grabbed before the shape moved.
   `gamut_app._run_js_now`.

2. **A copy of the screen has no transparency in it.** The graphics card has
   already mixed everything onto a ground. Asking the page politely and
   grabbing gives a solid picture. Recover it by drawing each frame twice, on
   white and on black, and subtracting: `picture.alpha_from_two_grounds`. It is
   exact, including anti-aliased edges, and it costs one extra grab a frame.

3. **Qt centres a progress bar's percentage on the widget, margins and all**,
   and on the font box rather than on the ink. Three pixels low at ordinary
   resolution, five on a high-resolution screen. `gamut_app.CentredProgressBar`
   and `_baseline_for`.

4. **Pillow ignores a quality you never pass.** An animated WebP written
   without `quality=` comes out at 80 and the surface shimmers as it turns.
   And `method=6` costs 27× the time of `method=4` for 0.5% smaller —
   measured, 49.2 s against 1.8 s on 120 frames.

5. **Encode as you go, not at the end.** Holding a long loop as frames costs
   hundreds of megabytes and the final encode blocks the window for seconds.
   Piping raw RGBA to ffmpeg through a bounded queue keeps memory flat and
   makes the window responsive throughout. `movie.MovieWriter`.

## ffmpeg, and the licence

Run as a **separate program**, never linked. That is what keeps a GPL encoder
away from MIT application code, and it is the same arrangement ChromIQ already
uses for ArgyllCMS. See `docs/THIRD-PARTY.md`. The discovery order —
chosen path, environment variable, bundled copy, PATH, usual places — mirrors
`argyll.py` deliberately, so the two behave the same way.

**Only offer what the build can do.** `ffmpeg -encoders` is read once and
cached; a distribution build without libx265 must not be offered H.265 and
then fail at the end of a two-minute export.

## Settings and presets

Looks live in ChromIQ's own presets folder (`~/Library/Preferences/ChromIQ/
presets/Picture Looks` and the platform equivalents), one JSON file each, for
exactly the reason `core/preset_store.py` gives: so they can be browsed,
copied and shared with a file manager. Removing one **archives** it to
`old/<date and time>/` rather than deleting — ChromIQ's own rule.

## If it is ported

`picture.py`, `movie.py` and `looks.py` can move across unchanged. The Qt side
needs: a section in a column, a save dialog, a frame source (whatever ChromIQ
is drawing), and `_finish_writing` for the off-thread encode. ChromIQ already
has `NoScrollComboBox`, `NoScrollSpinBox` and its own file dialogs, so the
widget helpers here should be dropped in favour of those.

Strings here are plain English; ChromIQ would need `tr()` around every one,
and the parameter-style tooltips split into title and body.
