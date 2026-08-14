# Wearing ChromIQ's styling

Written down because it was got wrong twice, and because the same list is what
any future ChromIQ mockup, documentation capture or companion window needs.

The rule underneath all of it: **two windows meant to look like one
application have to be the same values, not similar ones.** A near miss reads
as a copy. Everything below is taken from ChromIQ's own source, and the name
each value carries there is kept in a comment beside it.

---

## 1. The colours

| Ours | ChromIQ's name | Dark | Light |
|---|---|---|---|
| `bg` | `BG_PANEL` / `LM_BG_WINDOW` | `#181818` | `#eeece8` |
| `panel` | `BG_DARK` / `LM_BG_SURFACE` | `#101010` | `#f7f4ef` |
| `line` | `BORDER` / `LM_BORDER` | `#333333` | `#d0ccc6` |
| `line_soft` | `BORDER_HI` / `LM_BORDER_HI` | `#4a4a4a` | `#b0aba4` |
| `text` | `TEXT_MAIN` / `LM_TEXT_MAIN` | `#e6e6e6` | `#22211f` |
| `dim` | `TEXT_DIM` / `LM_TEXT_DIM` | `#8a8a8a` | `#7a7570` |
| `faint` | `TEXT_DIM` / `LM_TEXT_FAINT` | `#8a8a8a` | `#a8a4a0` |
| `second` | `BG_WIDGET` / `LM_BG_WIDGET` | `#262626` | `#edebe6` |
| `plot_bg` | the gamut viewer fill | `#111111` | `#efebe6` |

The accents are ChromIQ's five spectrum hues exactly: `SPEC_MAGENTA #ff4573`,
`SPEC_AMBER #ffb42d`, `SPEC_GREEN #56d6a5`, `SPEC_CYAN #37bcd6`,
`SPEC_VIOLET #9f82ff`.

**The accent is per context, not per application.** ChromIQ's tabs each own
one (`TAB_COLORS`), so a mockup of the gamut panel — which lives in tab 5,
Check & Refine — is **violet**, while a Tools dialog is **magenta**
(`dialog_masthead()`'s default). Painting both magenta says they are the same
thing, and they are not.

## 2. The masthead

`dialog_masthead()` in `ui/tab_header.py:148` is the real thing. Its metrics,
which have to be matched rather than approximated:

* a **22 × 2** accent-coloured rule before the eyebrow;
* the eyebrow in **Menlo 12px, `#808080`, weight 300**, uppercased *by the
  caller* (ChromIQ passes `"TOOLS"`, not `"Tools"`);
* the title in **Georgia 30px** with **letter spacing at 85%**;
* then the **SpectrumStripe**, 4px tall.

**Beware an app-wide QSS rule fighting the widget's own font.** A
`QLabel#mastheadTitle` rule setting 25px semi-bold silently overrode the 30px
Georgia the widget asked for. The rule should carry colour only.

## 3. The stripe is not derived from the accent

`SpectrumStripe` paints five equal blocks of `TAB_COLORS`, **identical in
light and dark** — only the chrome around it changes per theme. An earlier
version here derived five hue-shifted bands from the chosen accent. It looked
plausible and it was wrong: the stripe is the family mark, and it stays the
family's colours whichever accent a window happens to be wearing.

## 4. The ⓘ

`TooltipButton` (`ui/tooltip_button.py:32`) draws it, and it is a **painted
icon, not the "ⓘ" character**: an 18px circle, pen width 10% of that, a 7%
margin, and an **italic bold serif "i"** at 54% of the size. Cached per
(colour, device pixel ratio), because a window has twenty of them sharing a
handful of colours.

Placement, learned the hard way:

* **Beside the control it explains**, at the end of that control's row.
* A single explanation covering **several** controls goes beside the **last**
  of them, not on a row underneath all of them.
* An explanation covering a **whole group** is the only one that may sit on
  its own row.
* Never stack lone icons in a column with nothing beside them — that was the
  worst-looking state this went through.

Adding an icon gutter costs about **36px of column width**. Budget it: two
labels here had to be shortened, with the full text one click away, which is
what the ⓘ is for.

## 5. Three things the app-wide stylesheet does *not* carry

This is why mockups and captures come out wrong even when the stylesheet is
applied:

1. **The accent is per tab** — `TAB_COLORS`, not one colour for the app.
2. **Sliders are styled per panel, never globally.** There is no app-wide
   `QSlider` rule, so an unstyled slider falls back to the platform's blue.
   `gamut_panel.py:99–106` uses violet with a theme-aware groove (`#1c1b18`
   light, `#333333` dark); `softproof_dialog.py:222` uses its own accent.
3. **Self-painting widgets need `set_appearance(mode)`** — `ToolsPopup`, the
   masthead, the preset popups, the fade-scroll edges. `MainWindow.apply_theme()`
   broadcasts to them (`ui/main_window.py:1537–1540`); anything rendering them
   outside the main window must call it, or it silently gets dark. Two
   published screenshots were byte-identical because of this.

## 6. Compact buttons

`QPushButton#compact_input` is max-height 22px with 1px/6px padding
(`ui/styles.py:386–389`) — the treatment the Measure tab and the chart
parameters use. Give secondary actions that height and leave the one button
the user always presses at full height.

**A QSS `min-height` beats `setMinimumHeight()`.** The compact rule sets
`min-height: 0`, which makes those buttons the only compressible thing in a
column — they collapsed to 4px when the content was taller than the window.
The floor has to be set in QSS too.

## 7. How to check, rather than look

Every one of the faults above was found by eye and could have been found by
measurement. What is worth asserting:

* **Clipping** — for every visible label, button, checkbox and combo,
  `width() >= sizeHint().width()`, in both themes.
* **Light really is light** — mean pixel brightness under 80 for dark, over
  150 for light, and the two never byte-identical.
* **The accent really is the accent** — sample the icon pixels and compare
  with the token.
* **Legend keys stay legible** — luminance contrast against the page. Note
  that Plotly shades a mesh's legend key with the trace's own lighting, so it
  draws *darker* than the colour handed to it; aim higher than looks right.
