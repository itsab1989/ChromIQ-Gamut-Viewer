"""ChromIQ Gamut Viewer — a small desktop app, and a fitting study.

    python gamut_app.py                 # then use "Open a measured chart…"
    python gamut_app.py chart.ti3       # or start with a file

Two jobs at once. On its own it is a usable little tool: open the ``.ti3`` that
ArgyllCMS wrote when you read a printed chart, and see the gamut those patches
actually enclose, in 3D, painted in its own colours, with its volume. Open a
second one and the two are drawn together, so you can see which paper holds
more colour and where.

It is also built deliberately the way ChromIQ builds its own gamut view —
PyQt6, a QWebEngineView, a Plotly scene, a control column down the left — so
that what you see here is what it would look like living inside ChromIQ, and
the controls can be judged before anybody commits to them.

Runs on macOS, Windows and Linux: PyQt6 + numpy + scipy + plotly, all of them
wheels on all three.

    pip install PyQt6 PyQt6-WebEngine numpy scipy plotly
"""
from __future__ import annotations

import math

import movie
import picture
import prefs
from imagegamut import readable_extensions

#: Worked out once: which picture formats this machine can actually open.
IMAGE_EXTENSIONS = tuple(readable_extensions())

import csv
import json
import os
import sys

# ASKING THE VERSION SHOULD NOT NEED A BROWSER ENGINE. Everything below pulls
# in Qt and QtWebEngine, which on some machines -- headless build runners in
# particular -- cannot load at all. Answering here means "which version is
# this?" works anywhere, and keeps that question separate from "does the whole
# graphical stack work?", which deserves its own answer rather than being
# smuggled into a version check.
if __name__ == "__main__" and "--version" in sys.argv:
    from version import APP_NAME, __version__ as _v

    print(f"{APP_NAME} {_v}")
    raise SystemExit(0)

import shutil
import tempfile
import time
from pathlib import Path
from pathlib import Path as pathlib_Path

import numpy as np

# QtWebEngine must be imported before the QApplication exists.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401  (import order)
from PyQt6.QtCore import (QEvent, QRect, QSize, QStandardPaths, Qt,
                          QTimer, QUrl, pyqtSignal)
from PyQt6.QtGui import (QColor, QDesktopServices, QFont, QFontMetrics,
                         QIcon, QImage, QKeySequence, QLinearGradient,
                         QPainter, QPalette,
                         QPen, QPixmap, QShortcut)
from PyQt6.QtWidgets import (QApplication, QBoxLayout, QCheckBox, QComboBox,
                             QFileDialog,
                             QFrame, QGroupBox, QHBoxLayout, QLabel, QLayout,
                             QDialog, QMainWindow, QPushButton, QScrollArea, QSlider,
                             QColorDialog, QDialogButtonBox, QListView,
                             QAbstractItemView, QListWidget, QListWidgetItem,
                             QProgressBar, QProgressDialog,
                             QSizeGrip, QSpinBox,
                             QSizePolicy, QStyle, QStyleOptionProgressBar,
                             QButtonGroup, QGridLayout, QRadioButton, QToolButton,
                             QVBoxLayout,
                             QWidget)

from version import APP_NAME, UPSTREAM, __version__
from gamutview import SPACES, build_gamut, coverage, outside_of
from gamutview import xyz_to_lab
from references import (REFERENCE_SPACES, Stopped, gam_gamut,
                        icc_gamut, reference_gamut)
from spectral import optimal_colour_solid
from ti3gamut import (CONVERTERS, DIRECTIONS, compare_measurements,
                      neutral_axis, read_measurement, write_html,
                      write_slice_html)

# Dark, close to ChromIQ's own, so the fit is judged on layout rather than on
# a colour scheme that would never ship.
#: Every colour the window uses, once per appearance. Two palettes rather than
#: two stylesheets: the shapes are identical, only the paint differs, so a new
#: control cannot end up styled in one mode and forgotten in the other.
#: ChromIQ's own tokens, value for value, from its ui/styles.py (dark) and
#: ui/light_styles.py (light) -- the name each carries there is in the comment.
#: Not approximations: two windows meant to look like one application have to
#: be the same colours, and "nearly" reads as a copy rather than a companion.
PALETTES = {
    "dark": dict(
        bg="#181818",            # BG_PANEL     — window and group fill
        panel="#101010",         # BG_DARK      — the darker inset
        line="#333333",          # BORDER
        line_soft="#4a4a4a",     # BORDER_HI
        text="#e6e6e6",          # TEXT_MAIN
        dim="#8a8a8a",           # TEXT_DIM
        faint="#8a8a8a",         # TEXT_DIM
        # WHAT A SWITCHED-OFF CONTROL IS WRITTEN IN. Its own key, because
        # "faint" is right for a hint and wrong for a control somebody has to
        # be able to READ while it is unavailable. Measured against the panel
        # it sits on: text 15.25:1, this 5.51:1 -- plainly secondary, plainly
        # legible.
        disabled="#8a8a8a",
        # THE TWO LINKS AT THE FOOT, in the accent -- which on this dark
        # window comes to 5.37:1 and needs nothing done to it.
        link="#ff4573",
        accent="#ff4573", accent_hot="#ff6b90", on_accent="#ffffff",
        second="#262626",        # BG_WIDGET    — default button fill
        second_hover="#3a3a3a",
        plot_bg="#111111",       # the 3D viewer fill, gamut_panel.py:86
        grid="#262626", arrow="#e6e6e6",
        # THE INSIDE OF ANYTHING YOU OPEN OR TYPE IN -- a list, a number box,
        # an empty tickbox. On a dark window that is an inset, darker than the
        # surface around it, which is what BG_DARK already was.
        field="#101010",
        kept="rgb(105,112,126)",
        # The dark window's dim is comfortably above the floor already; the
        # key exists in both so the stylesheet needs no special case.
        credit="#9a958f"),
    "light": dict(
        bg="#eeece8",            # LM_BG_WINDOW
        panel="#f7f4ef",         # LM_BG_SURFACE — group-box fill
        line="#d0ccc6",          # LM_BORDER
        line_soft="#b0aba4",     # LM_BORDER_HI
        text="#22211f",          # LM_TEXT_MAIN
        dim="#7a7570",           # LM_TEXT_DIM
        # THE CREDIT AT THE FOOT NEEDS ITS OWN, and audit_readable is what
        # said so: at 10px on the window ground, LM_TEXT_DIM comes to 3.86:1
        # against the 4.5:1 a small piece of body text has to reach. The
        # panel fill is a shade lighter than the window, which is why the
        # same key measures 4.16 elsewhere and fails here. This is the
        # LIGHTEST step along the same grey that passes -- 4.53:1 on the
        # window, 4.88 on a panel -- so the line stays as quiet as it was
        # meant to be and can still be read.
        credit="#6f6a65",
        faint="#a8a4a0",         # LM_TEXT_FAINT
        # NOT "faint" ON A LIGHT WINDOW, and this is why the key exists.
        # Measured on the group-box fill: faint comes to 2.26:1, which is
        # barely there -- a disabled control ought to look unavailable, not
        # nearly invisible. LM_TEXT_DIM gives 4.16:1 against text at 14.66:1.
        disabled="#7a7570",      # LM_TEXT_DIM
        # THE SAME ACCENT ON A LIGHT WINDOW IS 2.80:1, which is under the
        # floor for text somebody is meant to read and click. Measured across
        # the same hue: #e02a58 gives 3.83, #c81f4a gives 4.75, #b81a45 gives
        # 5.44 and starts to look brown beside the accent it belongs to. The
        # middle one clears 4.5 and still reads as the same pink.
        link="#c81f4a",
        accent="#ff4573", accent_hot="#e02a58", on_accent="#ffffff",
        second="#edebe6",        # LM_BG_WIDGET
        second_hover="#e0ded8",
        plot_bg="#efebe6",       # LM_BG_VIEWER, gamut_panel.py:86
        grid="#e4e1db", arrow="#22211f",
        # AND ON A LIGHT WINDOW IT IS WHITE, because the idea inverts: a field
        # is lighter than what surrounds it, not darker. This used to be the
        # group-box fill, which meant a list sitting on a group box was
        # painted the identical colour -- reported as looking greyed out, and
        # it did. A new name rather than a change to `panel`, so the surfaces
        # still match ChromIQ's own light styling exactly.
        field="#ffffff",
        kept="rgb(176,180,188)"),
}


#: The five things Plotly's 3D lighting actually takes, with the range each one
#: accepts and a plain-language name. Exposed individually behind "Set the
#: lighting myself" for anybody who wants to dial in a particular look; the
#: Depth slider drives all five together for everybody else.
LIGHT_CONTROLS = (
    ("ambient", "Ambient — light from everywhere", 0.0, 1.0, 0.80),
    ("diffuse", "Diffuse — light the surface scatters", 0.0, 1.0, 0.36),
    ("specular", "Specular — the shiny highlight", 0.0, 2.0, 0.08),
    ("roughness", "Roughness — how soft that highlight is", 0.0, 1.0, 0.78),
    ("fresnel", "Fresnel — glow around the edges", 0.0, 5.0, 0.06),
    ("direction", "Which side the light comes from", 0.0, 360.0, 45.0),
    ("height", "How high the light hangs", -1.0, 1.0, 0.85),
)

#: How the shapes in the picture are coloured. Each answers a different
#: question, which is why this is a choice rather than a preference.
#: How tall a row holding a tick or a radio has to be, in one place.
#:
#: It is both a stylesheet floor and a layout floor, and it must be the same
#: number in both -- a stylesheet is applied at polish, long after a grid has
#: decided how tall its rows are, so the stylesheet alone stretches the widget
#: inside a row that was never made big enough for it.
TICK_ROW = 20

PAINTS = (
    ("true", "True colours"),
    ("solid", "One colour each"),
    ("lightness", "By lightness"),
    ("chroma", "By chroma"),
    ("accent", "In the accent colours"),
)

#: Accent colours to choose from. Only the accent changes: the greys, the
#: text and the backgrounds stay put, because they are what makes the window
#: readable and an accent is what makes it yours. Each is picked to hold up
#: against both the dark and the light background at the same weight.
#: ChromIQ's own five spectrum hues, verbatim from its ui/styles.py, so the
#: two applications are literally the same colours rather than near misses.
SPEC_MAGENTA = "#ff4573"
SPEC_AMBER   = "#ffb42d"
SPEC_GREEN   = "#56d6a5"
SPEC_CYAN    = "#37bcd6"
SPEC_VIOLET  = "#9f82ff"

#: The stripe under the title. Five plain spectrum blocks, identical in light
#: and dark -- ChromIQ paints only the chrome around them per theme, so this
#: needs no per-mode palette either.
TAB_COLORS = (SPEC_MAGENTA, SPEC_AMBER, SPEC_GREEN, SPEC_CYAN, SPEC_VIOLET)

#: In ChromIQ's own order -- the sequence its colour bar runs in, magenta
#: through violet -- because these are its five hues and a companion listing
#: them in a different order looks like a different set.
SCHEMES = {
    "Magenta": dict(accent=SPEC_MAGENTA, dark_hot="#ff6b90", light_hot="#e02a58"),
    "Amber": dict(accent=SPEC_AMBER, dark_hot="#ffc75c", light_hot="#d8930f"),
    "Green": dict(accent=SPEC_GREEN, dark_hot="#7ce3bb", light_hot="#33b184"),
    "Cyan": dict(accent=SPEC_CYAN, dark_hot="#5ad0e8", light_hot="#2597ad"),
    "Violet": dict(accent=SPEC_VIOLET, dark_hot="#b9a3ff", light_hot="#7e5fe0"),
}


def chevron_png(path: pathlib_Path, colour: str, dpr: float = 2.0,
                size: int = 10) -> str:
    """Draw the little arrow a combo box shows, and save it.

    Styling a combo box's drop-down at all makes Qt stop drawing its own
    arrow, so one has to be supplied. Drawing it here rather than shipping an
    image means it is the right colour in either appearance and the right
    resolution on any screen -- an arrow bitmap made for one of those is
    wrong on the other.
    """
    px = int(size * dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(colour))
    pen.setWidthF(1.6 * dpr)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    inset = px * 0.22
    painter.drawPolyline(*[
        __import__("PyQt6.QtCore", fromlist=["QPointF"]).QPointF(x, y)
        for x, y in ((inset, px * 0.36), (px / 2, px - inset),
                     (px - inset, px * 0.36))])
    painter.end()
    pm.save(str(path))
    return str(path)


def stylesheet(mode: str, scheme: str = "Magenta",
               arrow_image: str = "") -> str:
    """The whole window's styling, painted from one palette and one accent."""
    c = dict(PALETTES["light" if mode == "light" else "dark"])
    arrow_rule = (f"QComboBox::down-arrow {{ image: url({arrow_image}); "
                  f"width: 10px; height: 10px; }}" if arrow_image else "")
    chosen = SCHEMES.get(scheme, SCHEMES["Magenta"])
    c["accent"] = chosen["accent"]
    c["accent_hot"] = (chosen["light_hot"] if mode == "light"
                       else chosen["dark_hot"])
    return f"""
QWidget {{ background: {c["bg"]}; color: {c["text"]};
           font-family: "Inter"; font-size: 13px; }}
/* ChromIQ's own group-box metrics: radius 4, margin-top 14, padding-top 4,
   and no fill -- it inherits the window colour there too. */
QGroupBox {{ border: 1px solid {c["line"]}; border-radius: 4px;
            margin-top: 14px; padding: 4px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; top: 2px;
                   padding: 0 4px; color: {c["dim"]}; }}
QPushButton {{ background: {c["accent"]}; color: {c["on_accent"]}; border: none;
              border-radius: 5px; padding: 7px 12px; font-weight: 600;
              min-height: 20px; }}
QPushButton:hover {{ background: {c["accent_hot"]}; }}
QPushButton:disabled {{ background: {c["second"]}; color: {c["disabled"]}; }}
/* A QUIET BUTTON STILL HAS TO BE A BUTTON. Its fill is one step from the
   window it sits on -- #edebe6 on #eeece8 in the light appearance, a contrast
   ratio of 1.01:1, which is nothing at all -- so with no edge it simply was
   not there. An edge rather than a darker fill, because a darker fill reads
   as pressed. line_soft is the token whose whole job this is, and it lands at
   1.93:1 light and 2.00:1 dark, so neither appearance is favoured.
   The padding gives back the two pixels the border takes, so these stay
   exactly the size of the solid buttons beside them. */
/* The bar that fills while a moving picture is made. Left alone it is drawn
   in the operating system's own blue, which is the one colour in the window
   that answers to nothing the user chose. */
/* The number sits high unless the bar is given one fixed height and no
   padding of its own: Qt centres the text in the content box, and a box that
   is taller than it says leaves the figure riding above the middle. */
QProgressBar {{ background: {c["second"]}; border: 1px solid {c["line_soft"]};
               border-radius: 5px; text-align: center; color: {c["text"]};
               padding: 0; min-height: 20px; max-height: 20px;
               margin: 6px 0 12px 0; }}
QProgressBar::chunk {{ background: {c["accent"]}; border-radius: 4px; }}
QProgressDialog {{ background: {c["bg"]}; }}
QProgressDialog QLabel {{ color: {c["text"]}; }}
QPushButton#secondary {{ background: {c["second"]}; color: {c["text"]};
                        border: 1px solid {c["line_soft"]};
                        padding: 6px 11px; font-weight: 500; }}
QPushButton#secondary:hover {{ background: {c["second_hover"]}; }}
/* A BUTTON THE SIZE OF ITS GLYPH. #secondary carries 11 pixels of padding
   each side, which on a 26-pixel button leaves four for the character —
   so the +, the − and the … were all clipped. This is the same button with
   the padding taken out and a floor under the width instead. */
QPushButton#glyph {{ background: {c["second"]}; color: {c["text"]};
                    border: 1px solid {c["line_soft"]};
                    padding: 0; min-width: 26px; font-weight: 600; }}
QPushButton#glyph:hover {{ background: {c["second_hover"]}; }}
QPushButton#closer {{ background: transparent; color: {c["dim"]};
                     border: none; border-radius: 11px; padding: 0;
                     font-size: 17px; font-weight: 500; min-height: 0; }}
QPushButton#closer:hover {{ background: {c["second_hover"]};
                           color: {c["text"]}; }}
QComboBox {{ background: {c["field"]}; border: 1px solid {c["line"]};
            border-radius: 5px; padding: 5px 28px 5px 8px; }}
/* Qt draws the drop-down as its own sub-button inside the box: it paints a
   second border beside the arrow and squares off the rounded right-hand
   corner, which is what made the right edge look cut. Give it no border, no
   background of its own, and the same corner radius as the box it sits in. */
QComboBox::drop-down {{ subcontrol-origin: padding;
                       subcontrol-position: top right; width: 26px;
                       border: none; background: transparent;
                       border-top-right-radius: 5px;
                       border-bottom-right-radius: 5px; }}
/* Pointing at something you can change should say so in the colour the rest
   of the window uses for "this is yours to touch". A grey highlight is
   indistinguishable from the resting border on a dark background, and the
   radios were already using the accent -- so half the controls answered the
   pointer and half appeared not to. */
QComboBox:hover {{ border-color: {c["accent"]}; }}
QComboBox:focus {{ border-color: {c["accent"]}; }}
QComboBox:on {{ border-color: {c["accent"]}; }}
QCheckBox::indicator:hover {{ border: 1px solid {c["accent"]}; }}
QCheckBox::indicator:focus {{ border: 1px solid {c["accent"]}; }}
QSlider::handle:horizontal:hover {{ background: {c["accent_hot"]}; }}
QPushButton#secondary:focus {{ border: 1px solid {c["accent"]}; }}
{arrow_rule}
QComboBox QAbstractItemView {{ background: {c["field"]};
                              selection-background-color: {c["accent"]}; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 3px;
                       border: 1px solid {c["line_soft"]};
                       background: {c["field"]}; }}
QCheckBox::indicator:checked {{ background: {c["accent"]};
                               border-color: {c["accent"]}; }}
QSpinBox, QDoubleSpinBox {{ background: {c["field"]};
                           border: 1px solid {c["line"]}; border-radius: 5px;
                           padding: 3px 6px; color: {c["text"]};
                           selection-background-color: {c["accent"]};
                           selection-color: {c["on_accent"]}; }}
QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {c["accent"]}; }}
QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {c["accent"]}; }}
QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {c["disabled"]}; }}
QLineEdit, QPlainTextEdit, QTextEdit {{ background: {c["field"]};
                           border: 1px solid {c["line"]}; border-radius: 5px;
                           padding: 3px 6px; color: {c["text"]};
                           selection-background-color: {c["accent"]};
                           selection-color: {c["on_accent"]}; }}
QLineEdit:focus {{ border-color: {c["accent"]}; }}
QSlider::groove:horizontal {{ height: 4px; background: {c["line"]};
                             border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0;
                             border-radius: 6px; border: none;
                             background: {c["accent"]}; }}
/* A CONTROL THAT CANNOT ACT HAS TO LOOK LIKE IT. Qt greys a disabled widget
   through the palette, and this stylesheet paints over the palette -- so a
   slider switched off by the application was drawn in the accent colour,
   exactly like a live one, and the label beside it stayed white. Measured
   from a screenshot of the cross-section view, where three controls are
   disabled because a flat cut has no surface for them to act on: nothing on
   screen said so. Written out here, they dim. */
/* THE PSEUDO-STATE GOES AFTER THE SUB-CONTROL, and getting that backwards
   is not a no-op: written "QSlider:disabled::groove", Qt dropped the groove's
   own height and radius for EVERY slider in the window, so the live ones grew
   a fat grey bar. Seen at once in a screenshot, which is the only reason it
   did not ship. */
QSlider::groove:horizontal:disabled {{ background: {c["line_soft"]}; }}
QSlider::handle:horizontal:disabled {{ background: {c["disabled"]}; }}
QLabel:disabled {{ color: {c["disabled"]}; }}
QCheckBox:disabled {{ color: {c["disabled"]}; }}
QRadioButton:disabled {{ color: {c["disabled"]}; }}
/* A radio has to be round, and in Qt that means the radius must be half of
   the WHOLE box -- content plus both borders. 14 + 1 + 1 = 16, so 8. Thicken
   the border to draw a ring and the box grows to 22 while the radius stays 8,
   which is how a circle turns into a rounded square. The checked state keeps
   the same 1px border and simply fills. */
/* A floor under the row height. The 14px indicator plus its border makes a
   radio 16px tall, but in a grid the rows were allotted 15px and the buttons
   drew one pixel into each other. Reserving TICK_ROW gives the row more than
   the widget needs.

   THE SAME NUMBER HAS TO REACH THE LAYOUT AS WELL, which is why it comes from
   Python rather than being typed here: a floor set only in a stylesheet is
   applied at polish, and by then a grid has already worked out its rows from
   the unstyled metrics and will not be told again. Measured, before this was
   written down: the grid gave three rows 66 pixels -- 18 each -- while every
   radio in them insisted on 20, so the rows sat 17 apart and the checked one
   was drawn as half a circle with the descenders of "By lightness" cut off. */
QRadioButton {{ spacing: 7px; min-height: {TICK_ROW}px; }}
QCheckBox {{ spacing: 8px; min-height: {TICK_ROW}px; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px;
                          border: 1px solid {c["line_soft"]};
                          background: {c["field"]}; }}
QRadioButton::indicator:checked {{ background: {c["accent"]};
                                  border: 1px solid {c["accent"]}; }}
QRadioButton::indicator:hover {{ border: 1px solid {c["accent"]}; }}
/* The window's own message box. The card carries the background so the
   frameless dialog has a visible edge, and the heading is the only bold
   thing in it — a body that is entirely bold emphasises nothing. */
QDialog#notice {{ background: transparent; }}
QFrame#noticeCard {{ background: {c["panel"]}; border: 1px solid {c["line"]};
                     border-radius: 10px; }}
QLabel#noticeTitle {{ font-size: 15px; font-weight: 600; color: {c["text"]};
                      background: transparent; }}
QLabel#noticeBody {{ font-size: 12px; font-weight: 400; color: {c["dim"]};
                     background: transparent; }}
QFrame#noticeCard QScrollArea {{ background: transparent; }}
QFrame#noticeCard QScrollArea > QWidget > QWidget {{ background: transparent; }}
/* THE EXPLANATIONS ARE TEXT SOMEBODY READS, and they were written in the
   faintest colour the palette has. Measured from a screenshot of the real
   window, ink against the paper it was drawn on:

       dark   5.44:1     light   2.03:1

   Every explanatory paragraph in this window, at two to one, on a light
   window. TEXT_DIM instead: 4.16:1 there, unchanged in dark, where the two
   keys are the same colour anyway. */
QLabel#hint {{ color: {c["dim"]}; font-size: 11px; }}
/* The two links at the foot of the column. Not buttons competing with the
   controls above: quiet text that takes the accent when pointed at, the way
   a link does. */
/* Links, and they look like links: in the accent at rest, so they are
   findable, and brighter when pointed at. Grey text that only turns
   colourful under the pointer is a link nobody knows is there. */
QPushButton#footLink {{ background: transparent; border: none; padding: 2px 0;
                        color: {c["link"]}; font-size: 11px;
                        text-align: left; min-height: 0; }}
QPushButton#footLink:hover {{ color: {c["accent_hot"]};
                              text-decoration: underline; }}
/* Who wrote it, and what it was built on. The very last thing in the column
   and the quietest: dimmer and smaller than the links above it, in the same
   dim key every explanatory paragraph uses, so it is there for anybody who
   looks for it and competes with nothing. */
QLabel#footCredit {{ color: {c["credit"]}; font-size: 10px;
                     padding: 6px 0 2px 0; }}
QLabel#eyebrow {{ color: {c["dim"]}; font-size: 10px; font-weight: 600;
                  letter-spacing: 1.4px; }}
QFrame#mastheadRule {{ background: {c["accent"]}; border: none; }}
QLabel#mastheadTitle {{ color: {c["text"]}; background: transparent; }}
QToolButton#hintIcon {{ background: transparent; border: none; padding: 0;
                        margin: 0; }}
QToolButton#hintIcon:hover {{ background: rgba(128,128,128,40);
                              border: none; border-radius: 11px; }}
QToolButton#hintIcon:pressed {{ background: rgba(128,128,128,64);
                                border: none; border-radius: 11px; }}
QToolButton#hintIcon::menu-indicator {{ image: none; width: 0; }}
/* The line that unfolds an explanation. Quiet enough that it never competes
   with the control it belongs to, but it takes the accent colour on hover so
   it is visibly something you can click rather than another caption. */
QToolButton#hintToggle {{ color: {c["dim"]}; font-size: 11px;
                          border: none; background: transparent;
                          padding: 1px 0; text-align: left; }}
QToolButton#hintToggle:hover {{ color: {c["accent"]}; }}
QToolButton#hintToggle:checked {{ color: {c["dim"]}; }}
/* The two words that name a group of choices below them, rather than
   labelling one control beside them. They read as headings, so they are set
   as headings. */
QLabel#prefsHeading {{ color: {c["text"]}; font-weight: 600; }}
/* THE TICK IN A GROUP'S TITLE, which folds it away. Left unstyled it is drawn
   by the platform -- a blue box with a white check on macOS -- and blue is
   not one of this window's colours. Every other tick here is the accent, so
   this one is too, and it borrows the same rules rather than inventing a
   second look for the same idea. */
QGroupBox::indicator {{ width: 14px; height: 14px; border-radius: 3px;
                        border: 1px solid {c["line"]};
                        background: {c["field"]}; }}
QGroupBox::indicator:hover {{ border: 1px solid {c["accent"]}; }}
QGroupBox::indicator:checked {{ background: {c["accent"]};
                                border: 1px solid {c["accent"]}; }}
QLabel#volume {{ font-size: 21px; font-weight: 600; color: {c["text"]}; }}
QLabel#slot {{ color: {c["dim"]}; }}
QScrollArea {{ border: none; background: {c["bg"]}; }}
QScrollBar:vertical {{ background: {c["bg"]}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c["line"]}; border-radius: 5px;
                              min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c["line_soft"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


#: Kept so existing references still work; the dark palette is the default.
_QSS = stylesheet("dark")


#: The three navigation buttons in Qt's file dialog, and the standard icon
#: each one should show.
_NAV_BUTTONS = {
    "backButton": QStyle.StandardPixmap.SP_ArrowBack,
    "forwardButton": QStyle.StandardPixmap.SP_ArrowForward,
    "toParentButton": QStyle.StandardPixmap.SP_FileDialogToParent,
}
_NAV_BTN_SIZE = QSize(28, 28)
_NAV_ARROW_SIZE = QSize(16, 16)


def _nav_icon(icon: QIcon, color: QColor, dpr: float = 1.0) -> QIcon:
    """Repaint a standard arrow in *color*, centred on a button-sized canvas.

    Qt draws its dialog's back, forward and up arrows in a colour chosen for a
    light toolbar. On the dark toolbar this app uses they are all but
    invisible, so each is recoloured. The arrow is then centred on a canvas the
    size of the button, because Qt puts an icon at the button's top-left corner
    and an off-centre arrow looks like a mistake.

    EVERYTHING IS DRAWN AT THE SCREEN'S REAL RESOLUTION. A Retina display packs
    two device pixels into every point, so a 28-point button needs a 56-pixel
    image; handing it 28 pixels and letting Qt stretch them is what makes an
    icon look soft and blocky. Each pixmap is created at *dpr* times the size
    and then told what its ratio is, so Qt draws it at one image pixel per
    screen pixel. On a non-Retina display the ratio is 1 and this is exactly
    the plain behaviour.
    """
    arrow_px = _NAV_ARROW_SIZE * dpr
    raw = icon.pixmap(arrow_px)
    tinted = QPixmap(raw.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, raw)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()

    canvas = QPixmap(_NAV_BTN_SIZE * dpr)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.drawPixmap((canvas.width() - tinted.width()) // 2,
                       (canvas.height() - tinted.height()) // 2, tinted)
    painter.end()
    canvas.setDevicePixelRatio(dpr)
    return QIcon(canvas)


def _style_dialog_toolbar(dlg, arrow_colour: str = "#e0e0e0") -> None:
    """Make the dialog's own controls readable on whichever background is set.

    A light arrow vanishes on a pale toolbar just as surely as a dark one
    vanishes on a dark toolbar, so the colour follows the appearance instead
    of being fixed.
    """
    style = dlg.style()
    dpr = dlg.devicePixelRatioF() or 1.0
    for name, pixmap in _NAV_BUTTONS.items():
        button = dlg.findChild(QToolButton, name)
        if button is None:
            continue
        button.setIcon(_nav_icon(style.standardIcon(pixmap),
                                 QColor(arrow_colour), dpr))
        button.setIconSize(_NAV_BTN_SIZE)
        button.setFixedSize(_NAV_BTN_SIZE)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    grip = dlg.findChild(QSizeGrip)
    if grip is not None:
        grip.hide()

    # THE LOUD BUTTON MUST BE THE ONE YOU MEAN TO PRESS. This app paints every
    # push button in its accent colour, which in a file dialog lands on Cancel
    # -- so the way out shouted and Open sat there grey. Accept takes the
    # accent, Reject takes the quiet treatment, which is the same order of
    # emphasis the rest of the window uses.
    boxes = dlg.findChildren(QDialogButtonBox)
    for box in boxes:
        accept = box.button(QDialogButtonBox.StandardButton.Open) or \
            box.button(QDialogButtonBox.StandardButton.Save) or \
            box.button(QDialogButtonBox.StandardButton.Ok)
        reject = box.button(QDialogButtonBox.StandardButton.Cancel)
        if accept is not None:
            accept.setObjectName("")
        if reject is not None:
            reject.setObjectName("secondary")
        for button in (accept, reject):
            if button is not None:
                button.style().unpolish(button)
                button.style().polish(button)


def _profile_folders() -> list:
    """Where each platform keeps its ICC profiles.

    Every one of these is the folder that operating system genuinely installs
    into, so the profiles that came with the machine and the ones a paper
    maker put there are both a single click away in the file dialog. A folder
    that does not exist, or that holds no profile, is dropped rather than
    offered as a shortcut to nothing.
    """
    return [Path(where) for where in
            profile_folder_names(sys.platform, os.name, str(Path.home()),
                                 os.environ.get("SystemRoot", "C:/Windows"),
                                 os.environ.get("LOCALAPPDATA", ""))]


def profile_folder_names(platform: str, osname: str, home: str,
                         windows_root: str = "C:/Windows",
                         local_appdata: str = "") -> list:
    """The folders, as plain strings, for any platform.

    Strings rather than Path objects so every platform's list can actually be
    checked from any other: pathlib decides whether a Path is a Windows one
    from os.name at the moment it is built, so a test that fakes the platform
    and then builds a Path simply raises instead of testing anything.
    """
    # The same folders ChromIQ offers (ui/widgets.py, icc_profile_paths), so
    # the two applications send somebody to the same places. Reusing its list
    # rather than deriving another one is the point: this has been in the
    # field, and a near-copy that quietly differs is worse than either.
    if platform == "darwin":
        return ["/Library/ColorSync/Profiles",               # everyone's
                "/System/Library/ColorSync/Profiles",        # Apple's own
                f"{home}/Library/ColorSync/Profiles"]        # yours
    if platform.startswith("win") or osname == "nt":
        # Honour %SystemRoot%: Windows is not always installed on C:.
        folders = [f"{windows_root}/System32/spool/drivers/color"]
        if local_appdata:
            folders.append(f"{local_appdata}/Microsoft/Windows/Color")
        return folders
    return ["/usr/share/color/icc",
            "/usr/local/share/color/icc",
            f"{home}/.local/share/icc",     # XDG per-user (colord, GNOME)
            f"{home}/.color/icc"]           # older Argyll and oyranos


def _holds_profiles(folder: Path) -> bool:
    """Whether it is worth offering: does anything of the right kind live here?"""
    try:
        for entry in folder.iterdir():
            if entry.suffix.lower() in (".icc", ".icm"):
                return True
    except OSError:
        return False
    return False


#: Worked out once: the folders exist or they do not, and that does not change
#: while the application is running.
PROFILE_FOLDERS = _profile_folders()


def _sidebar_urls(*extra, profiles: bool = True) -> list:
    """Folders worth one click in the file dialog.

    The OS-correct, localized standard folders rather than hard-coded English
    paths under home, so this reads "Schreibtisch" on a German Mac and lands in
    the right place on Windows. ChromIQ's working folder is included because
    that is where the charts this app reads actually live, and so is the folder
    you last opened something from, since the second file usually sits beside
    the first. Anything that does not exist is dropped rather than shown as a
    dead entry.
    """
    SL = QStandardPaths.StandardLocation
    candidates = []
    for loc in (SL.DesktopLocation, SL.PicturesLocation,
                SL.DownloadLocation, SL.DocumentsLocation):
        where = QStandardPaths.writableLocation(loc)
        if where:
            candidates.append(Path(where))
    candidates.append(Path.home() / "ChromIQ")
    # WHERE PROFILES LIVE, now that a profile is something you can open here
    # rather than only compare against. These are the folders the operating
    # system itself keeps them in, so the ones that come with the machine --
    # sRGB, Adobe RGB, Display P3 -- and the ones a paper maker installs are
    # both a single click away. Anything absent is dropped, so a Mac shows the
    # Mac ones and a PC shows its own.
    # WHERE PROFILES LIVE IS FOR OPENING, NOT FOR SAVING. Those folders
    # belong to the operating system and nothing can be written into them, so
    # offering them while saving a picture is three shortcuts to a refusal.
    if profiles:
        candidates.extend(f for f in PROFILE_FOLDERS if _holds_profiles(f))
    candidates.extend(Path(e) for e in extra if e)
    seen, urls = set(), []
    for c in candidates:
        key = str(c)
        if key not in seen and c.exists():
            seen.add(key)
            urls.append(QUrl.fromLocalFile(key))
    return urls


#: Inside width of the control column, in pixels: the column is 310 wide, a
#: group box eats about 24 of it and its layout another 16. Text is measured
#: against this when a widget cannot yet report a width of its own.
_TEXT_WIDTH = 262


class WrappedLabel(QLabel):
    """A word-wrapped label that always claims the height its text needs.

    Measuring once when the label is built is not enough, and "sometimes cut
    off" is the symptom: the real width changes when the scroll bar appears or
    disappears, when the window is resized, when the text is replaced, and on
    another machine with another font. Each time, a height measured against a
    guessed width is the wrong height and the last lines disappear behind
    whatever sits below.

    So the height is recomputed from the width the label actually has, every
    time either of them changes. Nothing is guessed and nothing is hard-coded,
    which also means a translation twice the length of the English still fits.
    """

    def __init__(self, text: str = "", parent=None, *,
                 hide_when_empty: bool = False, hug: bool = False) -> None:
        super().__init__(text, parent)
        self._hide_when_empty = hide_when_empty
        # AND IT CAN BE SELECTED AND COPIED, because half of these readouts
        # say so. "written out so you can paste it into an email or a report"
        # is on the family report's own ⓘ, and until now it was not true of
        # the window at all: a QLabel hands the mouse straight through, so
        # there was nothing to drag over and nothing for Ctrl+C to take.
        # Basti asked the obvious question: "a hover tooltip from the info
        # section says it is written so one can copy it for an email for
        # example. but can one really copy or export the info text?"
        #
        # BY MOUSE AND BY KEYBOARD both, so a reader can drag over one line or
        # press Ctrl+A inside the readout and take the lot.
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        # A TEXT CURSOR WHERE TEXT CAN BE TAKEN, which is the only thing that
        # says so before somebody tries.
        self.setCursor(Qt.CursorShape.IBeamCursor)
        # TAKE EXACTLY THE TEXT'S HEIGHT AND NO SPARE.
        #
        # The default here is MinimumExpanding, which is right for a readout
        # that shares a column with nothing else and wrong for a note at the
        # bottom of a dialog: it swallows every point the window has going
        # spare. Measured on the save dialog -- two lines of text holding
        # **252 points** against a 79-point need, taken from the list of
        # switches directly above it, on a screen that had none to spare.
        #
        # A weaker policy is not enough. `Minimum` still carries the grow
        # flag, and the note went on taking the same 252 points; the height
        # has to be capped outright, which is what this does.
        self._hug = hug
        self.setWordWrap(True)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred,
                             QSizePolicy.Policy.Fixed if hug
                             else QSizePolicy.Policy.MinimumExpanding)
        # THE LAYOUT ASKS AT THE REAL WIDTH, EVERY TIME, instead of trusting a
        # height that was worked out once and kept.
        #
        # Reported as a difference between the appearances, in both
        # directions: "comparing dark and light mode on some instances there
        # is a line of text missing in dark, while light sometimes leaves too
        # much space", and then the reproduction that names the mechanism —
        # "with the wider left column the initial dark mode is good. you
        # switch to light mode and then there is unused space added below the
        # text. you switch back to dark and the space is still there".
        #
        # Nothing about light or dark is involved. Switching the appearance
        # re-applies the stylesheet, which re-POLISHES every widget, and Qt
        # applies stylesheet padding at polish -- so widths move for a moment
        # and every paragraph measured itself against a width it does not
        # end up with. The answer was then kept as a minimum height, which is
        # a floor: the extra space could never come back out, whichever
        # appearance you returned to.
        #
        # heightForWidth is Qt's own answer to this. QLabel already computes
        # it correctly for a wrapped label; what was missing is the size
        # policy SAYING SO, without which no layout ever calls it.
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._refit()

    def _refit(self) -> None:
        # A readout with nothing to say should take no room. Empty text still
        # measures one line high, which left a blank band under the Compare
        # with box before anything had been chosen, and another where the
        # coverage figures appear. Opt-in, because a hint's label is hidden
        # while it is folded even though it has plenty of text -- showing it
        # again here would unfold it behind the user's back.
        if self._hide_when_empty:
            has_text = bool(self.text().strip())
            if self.isVisibleTo(self.parentWidget()) != has_text:
                self.setVisible(has_text)
            if not has_text:
                self.setMinimumHeight(0)
                return
        width = max(60, self.width())
        rect = self.fontMetrics().boundingRect(
            QRect(0, 0, width, 10_000),
            int(Qt.TextFlag.TextWordWrap), self.text())
        needed = rect.height() + 4
        if needed != self.minimumHeight():
            self.setMinimumHeight(needed)
            self.updateGeometry()
            # AND EVERY LAYOUT ABOVE IT IS TOLD TO WORK AGAIN.
            #
            # updateGeometry() says "my hint has changed"; it does not make
            # anything act on it. A layout that has already handed this label
            # 48 px goes on handing it 48 px, even after the label has just
            # said 36 is enough -- a minimum is a floor, and lowering a floor
            # does not lower what is standing on it. Measured: twelve pixels
            # of nothing under the name of an open chart, which stayed until
            # the appearance was switched, because re-polishing is the only
            # thing that was resizing anything.
            holder = self.parentWidget()
            for _ in range(6):        # as far as the column, never further
                if holder is None:
                    break
                if holder.layout() is not None:
                    holder.layout().invalidate()
                holder = holder.parentWidget()
        # AND NEVER TALLER THAN ITS OWN WORDS, WHICH IS THE WHOLE OF THE
        # "UNUSED SPACE" REPORT.
        #
        # Reported as an appearance bug -- "you switch to light mode and then
        # there is unused space added below the text. you switch back to dark
        # and the space is still there" -- and it is nothing of the kind.
        # Traced by watching every measurement of one label as a chart was
        # opened:
        #
        #     _refit  width 422 -> min 36..36   height 36 -> 36
        #     _refit  width 422 -> min 20..36   height 21 -> 36
        #     _refit  width 422 -> min 36..36   height 41 -> 41
        #     _refit  width 422 -> min 36..36   height 48 -> 48
        #
        # The MINIMUM is right throughout: 36 px for 36 px of words. The
        # HEIGHT drifts to 48 anyway, because the policy is MinimumExpanding
        # -- the label is allowed to grow, so it soaks up whatever vertical
        # space its group has going spare, and how much it gets depends on
        # the order the layouts happen to run in. Re-polishing on an
        # appearance change runs them again and it lands on 36.
        #
        # A paragraph has no business absorbing space: it is words, and it
        # needs exactly as much room as the words take. Capping it puts the
        # spare where it belongs -- the group tightens to its contents, which
        # is what _tighten_groups asks for anyway.
        if needed != self.maximumHeight():
            self.setMaximumHeight(needed)

    def resizeEvent(self, event) -> None:      # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._refit()

    def setText(self, text: str) -> None:      # noqa: N802 (Qt naming)
        super().setText(text)
        self._refit()
        # AND AGAIN ONCE THE LAYOUT HAS HAD ITS SAY.
        #
        # Measured, driving the real window: the label naming an open chart
        # came out 48 px tall for 36 px of words -- twelve pixels of nothing
        # under the text -- and stayed that way until the appearance was
        # switched, after which it was 36 and correct for ever. Nine of the
        # thirteen paragraphs in the column changed height across that round
        # trip, which is the whole of "there is unused space added below the
        # text" and of the line missing in the other direction.
        #
        # The reason is ordinary and has nothing to do with light or dark:
        # text is set BEFORE the layout has given the label the width it will
        # end up with -- a file is opened, the readouts are written, and the
        # column is measured afterwards -- so it wraps to more lines than it
        # needs and keeps that height as a floor. Switching the appearance
        # re-polishes everything, which resizes it, which is the only thing
        # that ever asked it to measure itself again.
        #
        # Asked a second time on the next turn of the event loop, when the
        # width is real. It is one measurement of one label and it happens
        # only when the words change.
        QTimer.singleShot(0, self._refit)


class ElidingLabel(QLabel):
    """One line that shrinks to fit, with the middle taken out.

    WHY, AND IT WAS SEEN RATHER THAN REASONED. A profile added to a run is
    listed by its file name, and a real file name is long: "Studio printer —
    heavy matte cotton 310gsm — 2025-03-14 after the new inks" is 613 px of
    text in a 312 px list. A QListWidget answers that by growing a HORIZONTAL
    SCROLLBAR, so the column that holds the settings sprouted a little strip
    with arrows at each end -- reported from the window as "it looked like
    there were some side scrolling elements somewhere ... in the main window,
    left column".

    Nobody wants to scroll a settings column sideways to read a file name.

    THE MIDDLE IS WHAT GOES, not the end, and that is the whole point for
    these names: they begin with the device and the paper and END with the
    date, which is how one is told from the next. Cutting the tail off would
    leave a list of rows that all read the same.

    The full name is still there for anybody who wants it -- on the row's
    tooltip, and as the widget's accessible text, so a screen reader is given
    the name and not the abbreviation.
    """

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._full = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        # NO MINIMUM OF ITS OWN. A QLabel asks for the width of its whole
        # text, which is exactly what made the list scroll: the label
        # insisted, the row obeyed, and the list grew a scrollbar to reach
        # the rest of it.
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,
                           QSizePolicy.Policy.Preferred)
        super().setText(text)

    def setText(self, text: str) -> None:      # noqa: N802 (Qt naming)
        self._full = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        super().setText(text)
        self._shorten()

    def full_text(self) -> str:
        """The name as it really is, for anything that reads rather than looks."""
        return self._full

    def resizeEvent(self, event) -> None:      # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._shorten()

    def _shorten(self) -> None:
        room = max(0, self.width())
        if room <= 0:
            return
        shown = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideMiddle, room)
        if shown != super().text():
            super().setText(shown)


class NoScrollComboBox(QComboBox):
    """A combo box that ignores the wheel unless it has been clicked into.

    Scrolling a long column of settings should scroll the column. If a combo
    box under the pointer takes the wheel instead, a setting changes without
    anybody choosing it -- and in a window where every control redraws the
    picture, that is a silent change of what you are looking at.

    Focus is the test, not the pointer: once it has been clicked into, the
    wheel is clearly meant for it. The same rule ChromIQ uses.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # AND IT DOES NOT DEMAND THE WIDTH OF ITS LONGEST ITEM.
        #
        # A combo box asks, by default, for enough room to show the widest
        # thing in its list. Several of these hold FILE NAMES -- "Placed
        # through" lists the open profiles, "Compare with" lists the other
        # file -- and a real name is long: measured with one open, the
        # chooser demanded 613 px and dragged its whole group to 683 px in a
        # 358 px column, so "A chart to be printed" was drawn 306 px past the
        # column's right edge and simply cut off.
        #
        # Found by crossing a long file name against every place the window
        # shows one, after a photograph caught the same thing in the run's
        # list. One list fixed proves nothing about the other four.
        #
        # A combo already elides its own text when it is narrower than its
        # contents, and the whole name is there the moment the list is
        # opened, so nothing is lost by letting the layout decide the width.
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(12)

    def wheelEvent(self, event) -> None:        # noqa: N802 (Qt naming)
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoScrollSpinBox(QSpinBox):
    """A number box that ignores the wheel unless it has been clicked into.

    The same rule as every other control here: scrolling past something must
    never change it. A spin box is the worst offender, because a stray notch
    of the wheel silently alters a number nobody looked at.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:        # noqa: N802 (Qt naming)
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoScrollSlider(QSlider):
    """A slider the wheel never moves.

    THE FOCUS EXCEPTION WAS THE FAULT. This used to let the wheel through
    once the slider had focus, which sounds reasonable and means that the
    moment somebody DRAGS a slider -- which is how it gets focus -- scrolling
    the column past it starts changing it again. Reported exactly that way:
    "hovering over how it looks slider and scrolling changes its value
    although it should not".

    The wheel belongs to the column, which is longer than the window. A
    keyboard still adjusts a focused slider by arrow key, which is the precise
    control the wheel was pretending to be.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:        # noqa: N802 (Qt naming)
        event.ignore()


class _ScrollFade(QWidget):
    """A vertical gradient strip: opaque on the edge, clear on the inside.

    A long column cut off dead straight at the top or bottom gives no hint
    that there is more of it. Fading it into the background says "this
    continues" without spending a row on saying so. ChromIQ does the same
    thing in ui/fade_scroll.py, and this is its behaviour.
    """

    def __init__(self, position: str, parent) -> None:
        super().__init__(parent)
        self._position = position               # "top" or "bottom"
        self._colour = QColor("#181818")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_colour(self, colour: str) -> None:
        self._colour = QColor(colour)
        self.update()

    def paintEvent(self, _event) -> None:       # noqa: N802 (Qt naming)
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, 0, self.height())
        opaque = QColor(self._colour); opaque.setAlpha(255)
        clear = QColor(self._colour); clear.setAlpha(0)
        if self._position == "top":
            gradient.setColorAt(0.0, opaque)
            gradient.setColorAt(1.0, clear)
        else:
            gradient.setColorAt(0.0, clear)
            gradient.setColorAt(1.0, opaque)
        painter.fillRect(self.rect(), gradient)
        painter.end()


class FadeScrollArea(QScrollArea):
    """A scroll area whose top and bottom edges fade into the background.

    Each fade only appears when there is something in that direction to
    scroll to, so the window never suggests more content than it has.
    """

    FADE_H = 18

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._top = _ScrollFade("top", self.viewport())
        self._bottom = _ScrollFade("bottom", self.viewport())
        self.verticalScrollBar().valueChanged.connect(self._refresh)
        self.verticalScrollBar().rangeChanged.connect(self._refresh)
        self._refresh()

    def set_colour(self, colour: str) -> None:
        self._top.set_colour(colour)
        self._bottom.set_colour(colour)

    def resizeEvent(self, event) -> None:       # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        width = self.viewport().width()
        self._top.setGeometry(0, 0, width, self.FADE_H)
        self._bottom.setGeometry(0, self.viewport().height() - self.FADE_H,
                                 width, self.FADE_H)
        bar = self.verticalScrollBar()
        scrollable = bar.maximum() > bar.minimum()
        self._top.setVisible(scrollable and bar.value() > bar.minimum())
        self._bottom.setVisible(scrollable and bar.value() < bar.maximum())
        self._top.raise_()
        self._bottom.raise_()


class SpectrumStripe(QWidget):
    """A thin full-width band of the five ChromIQ tab hues, painted as equal
    blocks -- the same stripe ChromIQ's masthead and chart-design windows use.

    The hues are plain spectrum colours, identical in light and dark mode;
    only the chrome around them changes per theme, so this needs no per-mode
    palette. They are deliberately NOT derived from the chosen accent: the
    stripe is the family mark, and it stays the family's colours whichever
    accent this window happens to be wearing.
    """

    HEIGHT = 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:      # noqa: N802 (Qt naming)
        painter = QPainter(self)
        width = self.width()
        n = len(TAB_COLORS)
        for i, colour in enumerate(TAB_COLORS):
            x0 = int(round(i * width / n))
            x1 = int(round((i + 1) * width / n)) if i < n - 1 else width
            painter.fillRect(x0, 0, x1 - x0, self.HEIGHT, QColor(colour))
        painter.end()


class Masthead(QWidget):
    """Eyebrow, title and the spectrum stripe -- ChromIQ's own masthead.

    The metrics are ChromIQ's, not an impression of them: a 22x2 accent rule
    before the eyebrow, the eyebrow in Menlo 12px at #808080, and the title in
    Georgia 30px with letter spacing at 85%. Matching them exactly is the
    point -- these two windows are meant to look like one family, and
    "close enough" reads as a copy rather than a companion.
    """

    def __init__(self, eyebrow: str, title: str, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        inner = QVBoxLayout()
        inner.setContentsMargins(22, 18, 22, 12)
        inner.setSpacing(4)

        step_row = QHBoxLayout()
        step_row.setContentsMargins(0, 0, 0, 0)
        step_row.setSpacing(8)
        self._rule = QFrame(self)
        self._rule.setFixedSize(22, 2)
        self._rule.setObjectName("mastheadRule")
        step_row.addWidget(self._rule, 0, Qt.AlignmentFlag.AlignVCenter)
        eyebrow_label = QLabel(eyebrow, self)
        eyebrow_label.setStyleSheet(
            "color: #808080; background: transparent;"
            " font-family: Menlo; font-size: 12px; font-weight: 300;")
        step_row.addWidget(eyebrow_label, 0, Qt.AlignmentFlag.AlignVCenter)
        step_row.addStretch(1)
        inner.addLayout(step_row)

        title_label = QLabel(title, self)
        title_label.setObjectName("mastheadTitle")
        title_label.setStyleSheet(
            "background: transparent; font-family: Georgia; font-size: 30px;")
        font = QFont()
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 85)
        title_label.setFont(font)
        inner.addWidget(title_label)
        lay.addLayout(inner)
        lay.addWidget(SpectrumStripe(self))



def grey_the_scales(box, split, plain_tooltip) -> None:
    """Grey the colourings that cannot act while the cloud is split by family.

    THE OTHER HALF OF A PAIR THIS WINDOW ALREADY HALF-ENFORCES. When the cloud
    is coloured by destination, the split tick greys out, and the comment there
    says why: a control that goes on claiming a grouping the picture does not
    use "is a control saying something untrue, which this window has already
    learnt is worse than one that does nothing".

    The same was true in the other direction and nothing said so. Measured with
    two profiles open, five colourings crossed against the tick: with the tick
    OFF, five colourings give five different pictures; with it ON they give
    TWO. "How far it moved", "lighter or darker", "redder or greener" and
    "warmer or cooler" come out identical -- names, point counts and colours
    alike -- because a cloud cut into seven named groups has nowhere to put a
    sliding scale. All four stayed lit and selectable and did nothing.

    ONE FUNCTION FOR BOTH WINDOWS. The greying above it was written in the
    main window and only there, which is the asymmetry Basti asked to stop:
    "in general both path should benefit from any improvements". The timeline
    carries the identical pair, so it calls this too.

    THE ENTRIES, NOT THE BOX. Greying the whole thing would shut the reader
    out of "the colour it is heading for", which is the one entry that does
    act -- it takes the grouping over and greys the tick in turn -- and they
    would have to untick first to find that out.
    """
    if box is None or split is None:
        return
    split_on = split.isChecked() and split.isEnabled()
    model = box.model()
    # WHAT IS PROVED HERE, AND WHAT IS NOT. That the four entries cannot be
    # chosen is proved: audit_two_groupings reads isEnabled() on each item in
    # both states and fails if a dead one can still be picked (mutation-tested
    # -- remove the line below and it names all four).
    #
    # How a disabled entry LOOKS was not established, and an attempt to
    # "fix" it was reverted rather than shipped on a guess. Three instruments
    # were tried on an open popup and none can be trusted here: widget.grab()
    # returned byte-identical images for a foreground colour proved to be on
    # the model and readable back from it, and render() painted something
    # that was not the list at all. Qt greys disabled entries by itself in
    # every style this application has been run under, so the likeliest
    # reading is that the photograph was wrong and the window is right --
    # but if a greyed entry ever looks live on screen, the cure is a styled
    # delegate on box.view() plus a colour on the item, and the reason it
    # is not here already is that nothing could show it was needed.
    for i in range(box.count()):
        item = model.item(i) if hasattr(model, "item") else None
        if item is None:
            continue                       # not a standard model: leave it be
        item.setEnabled(not (split_on and box.itemData(i) != "toward"))
    if plain_tooltip is not None:
        box.setToolTip(GamutApp.COLOURING_IS_THE_FAMILIES if split_on
                       else plain_tooltip)


def pick_colour(parent, current: str, title: str, clearable: bool = True):
    """Choose a colour — in this application's own window, not the system's.

    WHY NOT THE SYSTEM'S. The one macOS opens is a floating palette that keeps
    its own state, ignores the colours already in the picture, wears none of
    this application's styling, and on some machines hides behind the window
    that asked for it. Qt's own is a plain dialog that behaves like every other
    dialog here, and it can be given the two things the system one will not:
    the colours already in use as a starting point, and a see-through setting.

    Returns ``#rrggbb``, ``rgba(r,g,b,a)`` when it is partly see-through, or
    None when nothing was chosen.
    """
    was = QColor(current) if current else QColor("#ffffff")
    if not was.isValid():
        was = QColor("#ffffff")
    dialog = QColorDialog(was, parent)
    dialog.setWindowTitle(title)
    # Qt's own rather than the system's, for the reasons above — the same
    # choice the file dialogs here make, and for the same reason.
    dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    if clearable:
        # SEE-THROUGH IS A COLOUR CHOICE TOO. Without this the only way to
        # make one part of the picture see-through was to leave the picker and
        # find a different control, which is a strange thing to have to do
        # while choosing a colour.
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
    # The colours already in the picture, ready to hand: matching the shape or
    # the page it is going on is the commonest thing anybody wants here, and
    # hunting for the same grey twice is how two panels end up almost matching.
    for slot, colour in enumerate(("#ffffff", "#efebe6", "#f7f4ef", "#d0ccc6",
                                   "#8a8a8a", "#262626", "#141414", "#111111",
                                   "#22211f", "#e6e6e6")):
        if slot < QColorDialog.customCount():
            QColorDialog.setCustomColor(slot, QColor(colour))
    if not dialog.exec():
        return None
    picked = dialog.currentColor()
    if not picked.isValid():
        return None
    if clearable and picked.alpha() < 255:
        return (f"rgba({picked.red()},{picked.green()},{picked.blue()},"
                f"{picked.alpha() / 255:.3f})")
    return picked.name()


def _chequerboard(across: int, down: int, square: int = 9):
    """The grey chequers that say "nothing is here", as a Pillow image.

    The convention every picture editor uses for see-through, and worth
    following exactly: somebody who has met it once knows immediately that the
    squares are not part of their picture. Made small and pale so it never
    competes with the shape sitting on it.
    """
    from PIL import Image, ImageDraw

    board = Image.new("RGBA", (max(1, across), max(1, down)), (255, 255, 255, 255))
    draw = ImageDraw.Draw(board)
    for y in range(0, down, square):
        for x in range(0, across, square):
            if (x // square + y // square) % 2:
                draw.rectangle([x, y, x + square - 1, y + square - 1],
                               fill=(214, 214, 214, 255))
    return board


def _baseline_for(groove, ink) -> float:
    """Where to put the baseline so the INK sits on the middle of the groove.

    tightBoundingRect is measured from the baseline, and its ``top`` is how far
    above that the ink begins — a negative number, and NOT simply minus the
    height, because a font can put ink below the baseline and because the two
    disagree by a fraction on some. Assuming they were the same put the number
    a pixel and a half high on Windows, where the substituted font differs from
    the one this was worked out on. Using the rectangle as given is exact
    wherever it runs.
    """
    wanted = groove.top() + groove.height() / 2.0        # middle of the bar
    return wanted - ink.top() - ink.height() / 2.0


class CentredProgressBar(QProgressBar):
    """A progress bar whose percentage sits on the middle of the bar.

    TWO THINGS WERE WRONG, and only one of them was the one being nudged.

    THE BAR IS NOT THE WIDGET. The stylesheet gives it a margin — six pixels
    above and twelve below, so it does not touch the label over it or the Stop
    button under it — and Qt then centres the number on the *widget*, margins
    and all. The middle of the widget is several pixels below the middle of the
    coloured bar, so the figure sat low. No amount of adjusting the padding
    could fix that, because the padding was never what was wrong.

    AND QT CENTRES ON THE FONT, NOT ON THE TEXT. The font box reaches from the
    top of a capital to the bottom of a descender, and "73%" has no descender,
    so the ink lands off-centre inside its own box by another half-pixel — a
    whole one on a high-resolution screen.

    So: the bar is drawn by the style as usual, and the number is placed on the
    middle of the ink, on the middle of the **groove**. Right at any size, on
    any screen, in any font.
    """

    def _groove(self):
        """The coloured bar itself, without the margin around it."""
        option = QStyleOptionProgressBar()
        self.initStyleOption(option)
        rect = self.style().subElementRect(
            QStyle.SubElement.SE_ProgressBarGroove, option, self)
        return rect if rect.isValid() and rect.height() > 0 else self.rect()

    def paintEvent(self, _event) -> None:
        option = QStyleOptionProgressBar()
        self.initStyleOption(option)
        wanted = option.text
        show = self.isTextVisible() and bool(wanted)
        option.textVisible = False          # the style draws groove and chunk
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_ProgressBar,
                                 option, painter, self)
        if not show:
            return
        groove = self._groove()
        metrics = painter.fontMetrics()
        ink = metrics.tightBoundingRect(wanted)
        across = groove.left() + (groove.width()
                                  - metrics.horizontalAdvance(wanted)) / 2.0
        baseline = _baseline_for(groove, ink)
        painter.setPen(option.palette.color(QPalette.ColorRole.Text))
        painter.drawText(int(round(across)), int(round(baseline)), wanted)

    def ink_offset(self) -> float:
        """How far the number sits from the middle of the bar, for a test.

        Positive is low, negative is high, and zero is the point of all this.
        """
        groove = self._groove()
        ink = QFontMetrics(self.font()).tightBoundingRect(self.text())
        baseline = _baseline_for(groove, ink)
        middle = baseline + ink.top() + ink.height() / 2.0
        return middle - (groove.top() + groove.height() / 2.0)


# `Stopped` USED TO BE DEFINED HERE, AND THAT WAS A TRAP WORTH REMOVING.
#
# It said the same thing as `references.Stopped` -- the person stopped it, not
# a fault -- and both existed at once. Because this definition came AFTER the
# import at the top of the file, it silently shadowed the other one: an
# `except Stopped` written down here caught the class defined here and let the
# one raised by the profile reader straight through, into the handler that
# tells somebody their file "could not be used". Which is exactly wrong for a
# thing they asked for.
#
# The suite did not catch it, because nothing exercised pressing Stop at that
# call site. One name, one class, imported from `references` -- see the import
# at the top of this file.


def make_foldable(box, key: str, start_open: bool = True):
    """Let a group of controls be folded away, and remember whether it was.

    WHY THE COLUMN NEEDED THIS, MEASURED BEFORE ANYTHING WAS BUILT. With
    nothing open the left column was 372 x 2681 px against a window that shows
    about 880 of it -- two and a half screens before anybody had loaded a file.
    Fourteen groups, no sense of where you are among them, and no way to put
    one away. "How it looks" alone was 946 px, 46% of everything, and most
    people set it once and never open it again.

    THE SAME ARROW CHROMIQ USES, not a tick, and that is Basti's call: "those
    arrows are better for collapsing options. a checkbox looks like it
    activates things."

    ONE BODY, HIDDEN WHOLE -- AND THE FIRST VERSION OF THIS DID NOT DO THAT.
    It walked the group's children, hid the ones that were not already hidden,
    remembered the list, and put that list back on opening. Every part of that
    is a way to lose something, and it lost plenty. Reported after two minutes
    in the real window: "collapsing sections is horrible. they don't collapse
    in place but they move around, become only a little smaller and empty",
    and "there is a viewer and export styling section that is empty".

    THE FAULT, TRACED. A group that started shut recorded its list during
    __init__ and hid them. The window is then shown, and a later pass
    re-asserts every fold -- because a setVisible(False) issued while the
    parent is hidden does not always survive the parent being shown. That
    second call recorded the list AGAIN, found everything already hidden,
    and stored an empty one. From then on the group could never be opened:
    there was nothing left to put back. Four groups shipped like that.

    So it works the way ChromIQ's own CollapsibleGroupBox does instead. The
    group's entire layout is moved onto one body widget, and folding shows or
    hides that single widget. Nothing is remembered, nothing is walked, and
    every control inside keeps its own visibility -- so a row hidden because
    no file is loaded stays hidden when the group is opened, which the list
    version had to be taught separately and got wrong twice.

    WHAT IS REMEMBERED, AND WHAT IS NOT. Only whether the group was open.
    Nothing inside is touched, so folding can never change what a picture
    looks like: it hides controls, it does not set them.
    """
    inner = box.layout()
    body = QWidget()
    # MOVING A LAYOUT IS ALLOWED, and it takes its widgets with it -- their
    # parent stays the group, so nothing else in the window has to know. The
    # group is left free to take a layout of its own.
    body.setLayout(inner)
    body.setParent(box)
    outer = QVBoxLayout(box)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(body)
    # NEVER TALLER THAN WHAT IS IN IT, which is the rule _tighten_groups
    # applies to every group. That pass ran before this one and put the
    # constraint on the layout this has just moved, so the group itself needs
    # it again -- otherwise a folded group keeps the height of its contents
    # and "becomes only a little smaller".
    #
    # WHICH CONSTRAINT DEPENDS ON WHETHER IT IS OPEN, and both halves of that
    # were learned the hard way.
    #
    # OPEN: SetMinAndMaxSize, which is what _tighten_groups applied before
    # this pass moved the layout. It writes the group's least WIDTH from its
    # contents, and the column is sized from those least widths -- so leaving
    # it off shrank the column by ten pixels and "How it looks", which
    # genuinely needs 366, was handed 346 and clipped. Reported as "how it
    # looks section became too wide now".
    #
    # SHUT: the maximum only. SetMinAndMaxSize would then write the least
    # width from a layout holding one hidden widget, which asks for nothing --
    # the group's least width became 6 px and the heading was drawn as the
    # single letter that fits in it, "W". Shut, the minimum is set from the
    # heading instead; see below.
    box._fold_title = box.title()
    # THE NAME EVERYTHING ELSE ASKS FOR IS THE NAME WITHOUT THE ARROW, which
    # is how ChromIQ's own collapsible group behaves and is not decoration:
    # this window keeps three lists keyed on a group's heading -- which
    # sections depend on the colour space, which need no ⓘ, which are
    # space-independent -- and the arrow silently stopped every one of them
    # matching. The panel audit went from clean to twenty-eight "a control
    # nobody thought about" reports, none of which was true. Qt paints from
    # its own copy, so the arrow is still drawn.
    box.title = lambda _b=box: _b._fold_title
    box.body = body
    box.setToolTip(
        "Click the heading to fold this group away, or to open it again.\n\n"
        "It only hides these controls. Nothing you have set is changed and "
        "the picture stays exactly as it is — this is about how much of the "
        "column you want to look at, not about what the window does.\n\n"
        "Whether it was open is remembered, so a group you never use stays "
        "out of the way next time.")

    def shown(open_up: bool, remember: bool = True) -> None:
        body.setVisible(bool(open_up))
        outer.setSizeConstraint(
            QLayout.SizeConstraint.SetMinAndMaxSize if open_up
            else QLayout.SizeConstraint.SetMaximumSize)
        # THE FRAME GOES WITH THE CONTENTS. A shut group with its border still
        # drawn is an empty box, which reads as something broken rather than
        # something put away. ChromIQ drops the frame for the same reason.
        box.setFlat(not open_up)
        # A FILLED TRIANGLE, and a big one. ChromIQ settled this: the small
        # ▸ / ▾ do not read as something to press, and the trailing space
        # sets the arrow off from the words.
        drawn = ("▼  " if open_up else "▶  ") + box._fold_title
        box.setTitle(drawn)
        # WITH THE BODY GONE, NOTHING IN THE GROUP ASKS FOR ANY WIDTH, and a
        # group constrained to its contents will then be given the width of
        # nothing -- which is how a heading came to be drawn as the single
        # letter that fits, "W". The title is what is left, so the title is
        # what the width is asked of.
        box.setMinimumWidth(
            0 if open_up
            else box.fontMetrics().horizontalAdvance(drawn) + 34)
        # AND THE LEAST HEIGHT HAS TO BE GIVEN BACK, or the group cannot
        # shrink at all: while it was open, the constraint wrote a minimum
        # height from its contents, and a minimum outranks the new maximum.
        # Measured with the fold on a three-row group: 78 px open, 78 px shut.
        box.setMinimumHeight(0)
        box.updateGeometry()
        # AND THE COLUMN IS ASKED AGAIN, because a group nobody had opened yet
        # was not part of the width it was sized to. "How it looks" needs 366
        # px for one unwrappable label; while it was folded the column settled
        # at 346, and opening it then clipped its right-hand edge -- reported
        # as "how it looks section became too wide now". Widening only ever
        # grows, so this can be asked as often as it likes.
        # THE COLUMN IS NOT RESIZED HERE. It is sized once, for the widest
        # thing any group could ever show -- see _widen_the_column_to_fit_it,
        # which asks each group's BODY rather than the group itself, so a
        # folded one still answers honestly. Widening on every open made the
        # whole column jump under the hand.
        if remember:
            prefs.store().setValue(f"fold/{key}", bool(open_up))

    saved = prefs.store().value(f"fold/{key}")
    open_up = (bool(start_open) if saved is None else
               (saved if isinstance(saved, bool)
                else str(saved).lower() not in ("false", "0", "")))
    box._fold_open = open_up
    shown(open_up, remember=False)

    # THE TITLE BAND IS THE CONTROL, as it is in ChromIQ: a press in the top
    # strip of the group toggles it, and anything lower is left to whatever
    # control is there.
    def pressed(event, _box=box):
        band = _box.fontMetrics().height() + 10
        if (event.button() == Qt.MouseButton.LeftButton
                and event.position().y() <= band):
            _box._fold_open = not _box._fold_open
            shown(_box._fold_open)
            event.accept()
            return
        QGroupBox.mousePressEvent(_box, event)

    box.mousePressEvent = pressed
    # NO HAND CURSOR HERE, and that is deliberate. Setting it on the group set
    # it on everything INSIDE the group as well -- Qt hands a widget's cursor
    # down to every child that has not asked for one of its own -- so the
    # pointer became a hand over labels, over readouts, over empty space, in
    # rooms where a click does nothing at all. Reported plainly: "i don't want
    # the mouse arrow to turn into a hand symbol in some occasions".
    #
    # THE HEADING IS STILL THE CONTROL; what it lost is a promise it was
    # making on behalf of the whole section. The triangle at the left of the
    # heading is what says a section folds, and it says it without following
    # the mouse around.
    # RE-ASSERTED ONCE THE WINDOW IS UP, and now that is safe: showing or
    # hiding one widget says the same thing however many times it is said.
    # The version that remembered a list of children could not survive being
    # asked twice, which is precisely what broke it.
    box._refold = lambda: shown(box._fold_open, remember=False)
    return box


class LookSection(QGroupBox):
    """Everything around the shape: background, walls, lettering, grid lines.

    NAMED FOR THE TWO THINGS IT GOVERNS. These choices decide what a saved
    picture looks like, and — with Live preview ticked — what this window looks
    like as well, because they are the same thing rather than two settings that
    have to be kept in step.

    IN THE WINDOW RATHER THAN IN THE SAVE DIALOG, and that is the whole point.
    These choices used to live inside the window that opens when you press
    Save, where you could not see what any of them did until the file was
    written and opened. Here they sit beside the picture, and with "Show it in
    the window too" ticked the view in front of you IS the picture that will be
    saved — so setting one up is a matter of looking at it rather than of
    imagining it.

    That also makes it a way to have the application itself look how you like:
    the view is not a preview of a separate thing, it is the thing.
    """

    def __init__(self, parent, on_change=None) -> None:
        super().__init__("Viewer and export styling", parent)
        self._parent = parent
        self._on_change = on_change
        self._settling = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(8)
        rows = QGridLayout()
        rows.setHorizontalSpacing(8)
        rows.setVerticalSpacing(8)
        rows.setColumnStretch(0, 1)
        self._rows = rows
        line = 0

        # ONE CHOICE THAT SETS THE OTHER SIX. Background, walls, lettering and
        # grid lines all depend on each other — a white background wants dark
        # lettering, a see-through one wants lettering picked for a page that
        # is not on this screen — and getting four of them right by trial is
        # not a reasonable thing to ask of anybody. Each of these is one answer
        # that works, named for where the picture is going.
        self._look = NoScrollComboBox(self)
        # LET IT SHRINK RATHER THAN CLIP. A combo asks for room for its
        # longest entry, and next to three buttons in a narrow column that is
        # room it may not get — at which point Qt cuts the text off mid-word
        # instead of giving way. Naming a short minimum lets the layout squeeze
        # it, and the list itself still opens at full width.
        self._look.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._look.setMinimumContentsLength(8)
        self._look.currentIndexChanged.connect(self._apply_look)
        # THE SAME THREE BUTTONS AS THE PRESETS ON CHROMIQ'S OWN MANUAL TABS,
        # in the same order and doing the same things: save what is set now,
        # take one off the list, and open the folder they live in. Somebody who
        # knows one knows the other.
        # THE BUTTONS GO UNDER THE CHOOSER, not beside it. Measured: this
        # column is 346 pixels wide, and a combo sharing a row with three
        # buttons is left about 116 for its text — while "For a white
        # document" needs 133. Something had to give, and the three small
        # buttons giving up their place costs nothing, while the chooser
        # losing the end of every other entry costs the point of it.
        look_holder = QWidget(self)
        look_stack = QVBoxLayout(look_holder)
        look_stack.setContentsMargins(0, 0, 0, 0)
        look_stack.setSpacing(4)
        look_stack.addWidget(self._look)
        under = QWidget(look_holder)
        look_row = QHBoxLayout(under)
        look_row.setContentsMargins(0, 0, 0, 0)
        look_row.setSpacing(6)
        look_stack.addWidget(under)
        look_row.addStretch(1)
        self._look_save = QPushButton("+", self)
        self._look_save.setObjectName("glyph")
        self._look_save.setFixedWidth(26)
        self._look_save.setToolTip("Save what is set now as a look of your own")
        self._look_save.clicked.connect(self._save_look)
        look_row.addWidget(self._look_save)
        self._look_remove = QPushButton("−", self)
        self._look_remove.setObjectName("glyph")
        self._look_remove.setFixedWidth(26)
        self._look_remove.setToolTip("Take the chosen look off the list")
        self._look_remove.clicked.connect(self._remove_look)
        look_row.addWidget(self._look_remove)
        self._look_folder = QPushButton("…", self)
        self._look_folder.setObjectName("glyph")
        self._look_folder.setFixedWidth(26)
        self._look_folder.setToolTip(
            "Open the folder your saved looks are kept in, for copying one to "
            "somebody else or putting one they sent you in")
        self._look_folder.clicked.connect(self._open_looks_folder)
        look_row.addWidget(self._look_folder)
        self._fill_looks()
        line = self._row(rows, line, "How it should look", look_holder, Hint(
            "A whole set of choices at once — what is behind the shape, what "
            "the three walls are, and what colour the lettering and the grid "
            "lines come out — picked to go together.\n\n"
            "They are named for WHERE THE PICTURE IS GOING, because that is "
            "the question you actually have.\n\n"
            "FOR A WHITE DOCUMENT is the safe answer for a report, a letter "
            "or anything printed: white behind and around, with dark lettering "
            "that can be read on it.\n\n"
            "FOR A PRINTED REPORT, WITH A SOFT BOX is the same with the three "
            "walls a shade of grey, so the shape sits inside something instead "
            "of floating on the page.\n\n"
            "FOR A DARK SLIDE turns it round: black behind, light lettering.\n\n"
            "CUT OUT leaves nothing behind the shape at all, so it takes on "
            "whatever page you drop it onto. There are two, and the difference "
            "is only the lettering — choose the one that matches the page it "
            "is going on, because nothing here can see that page. Use a kind "
            "of file that can hold see-through: PNG or WebP for a picture, "
            "WebM for a film.\n\n"
            "AS IT LOOKS ON SCREEN changes nothing at all, and is right when "
            "the window already looks the way you want it.\n\n"
            "None of this is a cage. Tick Adjust these myself to see exactly "
            "what a look has set and change any of it; the chooser then simply "
            "says My own settings.", self))
        self._look_row = line - 1

        self._look_why = WrappedLabel("", self)
        self._look_why.setObjectName("hint")
        rows.addWidget(self._look_why, line, 0, 1, 2)
        self._look_why_row = line
        line += 1

        self._details = QCheckBox("Adjust these myself", self)
        self._details.toggled.connect(self._refresh)
        line = self._row(rows, line, "", self._details, Hint(
            "Opens every one of the choices a look sets, so you can change any "
            "of them on their own.\n\n"
            "Worth opening if you need an exact colour — a house style, or the "
            "precise grey of the page this is going on. Otherwise leaving it "
            "closed is no loss: the looks above are the combinations that work, "
            "and what you get is shown underneath either way.", self))
        self._details_row = line - 1

        self._background = NoScrollComboBox(self)
        for key, label in picture.BACKGROUNDS:
            self._background.addItem(label, key)
        self._background.currentIndexChanged.connect(self._went_custom)
        self._background_row = line
        line = self._row(rows, line, "Behind the shape", self._background, Hint(
            "What fills the space around the shape.\n\n"
            "As it looks on screen keeps the dark or light background you are "
            "looking at now. White suits a printed page or a document. Black "
            "suits a slide.\n\n"
            "SEE-THROUGH leaves nothing there at all, so the shape sits "
            "directly on whatever page you drop it onto and takes that "
            "background as its own. This is usually the one you want for a "
            "document or a slide, and it needs a kind of file that can hold "
            "it — PNG or WebP. Choose it with JPEG and this will say so "
            "rather than quietly filling it with black.", self))

        self._walls = NoScrollComboBox(self)
        self._walls.addItem("The same as behind the shape", "same")
        for key, label in picture.BACKGROUNDS:
            self._walls.addItem(label, key)
        self._walls.currentIndexChanged.connect(self._went_custom)
        self._walls_label_row = line
        line = self._row(rows, line, "The grid's walls", self._walls, Hint(
            "The three panels the grid is drawn on, behind and beneath the "
            "shape — separate from the page colour above, so you can have "
            "them differ.\n\n"
            "Leaving them the same as the background is usually right: the "
            "picture then reads as one thing. Setting them apart is worth it "
            "when you want the box to stand out a little from the page it is "
            "sitting on, or to fade back so the shape carries the picture on "
            "its own.\n\n"
            "SEE-THROUGH here removes the panels as well, so the shape floats "
            "with only the grid lines around it — and with the background "
            "see-through too, nothing is left but the shape and its lines. "
            "That is the version that drops cleanly onto any coloured page or "
            "slide. It needs a kind of file that can hold see-through, which "
            "PNG and WebP both can.\n\n"
            "If you would rather have no grid at all, untick Show the box and "
            "its grid in the main window before saving.", self))
        self._walls_row = line - 1

        self._wall_colour = QPushButton("Choose a colour…", self)
        self._wall_colour.setToolTip(
            "Opens the colour picker for the three PANELS the grid is drawn on, behind and beneath the shape."
            "\n\nThe colours already in the picture are offered in the picker's own swatches, because matching the shape or the page it is going onto is the commonest thing to want here — and hunting for the same grey twice is how two panels end up almost matching.\n\nOnce you have chosen, this button shows the colour it is set to. It only changes what a picture LOOKS like; nothing measured is touched.")
        self._wall_colour.setObjectName("secondary")
        self._wall_colour.clicked.connect(self._pick_wall_colour)
        self._wall_chosen = "#202020"
        line = self._row(rows, line, "Wall colour", self._wall_colour, Hint(
            "Any colour you like on the three panels the grid sits on.\n\n"
            "The walls are what give the picture its depth: without them a "
            "shape floats with nothing behind it and it is much harder to see "
            "which way round it is.\n\n"
            "Keep them close to the background so they read as a room rather "
            "than as three coloured panels competing with the shape. A shade "
            "or two lighter than the page on a dark theme, a shade or two "
            "darker on a light one, is usually all it wants.", self))
        self._wall_colour_row = line - 1

        self._colour = QPushButton("Choose a colour…", self)
        self._colour.setToolTip(
            "Opens the colour picker for the PAGE the shape sits on — everything outside the grid box."
            "\n\nThe colours already in the picture are offered in the picker's own swatches, because matching the shape or the page it is going onto is the commonest thing to want here — and hunting for the same grey twice is how two panels end up almost matching.\n\nOnce you have chosen, this button shows the colour it is set to. It only changes what a picture LOOKS like; nothing measured is touched.")
        self._colour.setObjectName("secondary")
        self._colour.clicked.connect(self._pick_colour)
        self._chosen = "#ffffff"
        line = self._row(rows, line, "Colour", self._colour, Hint(
            "Any colour you like behind the shape.\n\n"
            "This is the page the picture is drawn on, so it is the one to "
            "change for a house style, a slide "
            "background, or the exact grey of the page it is going on.", self))
        self._colour_row = line - 1

        self._lettering = NoScrollComboBox(self)
        for key, label in picture.INK_CHOICES:
            self._lettering.addItem(label, key)
        self._lettering.currentIndexChanged.connect(self._went_custom)
        line = self._row(rows, line, "Lettering", self._lettering, Hint(
            "The numbers up the sides of the box and the names of the three "
            "axes — the part that says how big the shape actually is.\n\n"
            "FOLLOW THE BACKGROUND is the one to leave it on. Whatever you "
            "chose behind the shape is measured, and the lettering comes out "
            "dark on a light background and light on a dark one, so it can "
            "always be read.\n\n"
            "It matters more than it sounds. On screen the lettering is a pale "
            "grey, which is right on the dark window — and saving that same "
            "picture on a white background gives pale grey on white, which is "
            "very nearly invisible. Nothing about the picture looks broken; "
            "the scale simply cannot be read.\n\n"
            "Choose DARK or LIGHT yourself when you know where the picture is "
            "going and it is not what you are looking at now — a see-through "
            "picture is the usual case, because nobody here can know what page "
            "you are about to drop it onto. Dark for a white document, light "
            "for a dark slide.\n\n"
            "A COLOUR OF MY OWN is there for a house style. It is worth "
            "checking it against your background: anything close in brightness "
            "to what is behind it will be hard to read however nice it looks.",
            self))
        self._lettering_row = line - 1

        self._lettering_colour = QPushButton("Choose a colour…", self)
        self._lettering_colour.setToolTip(
            "Opens the colour picker for the LETTERING — the numbers up the sides of the box and the names of the three axes."
            "\n\nThe colours already in the picture are offered in the picker's own swatches, because matching the shape or the page it is going onto is the commonest thing to want here — and hunting for the same grey twice is how two panels end up almost matching.\n\nOnce you have chosen, this button shows the colour it is set to. It only changes what a picture LOOKS like; nothing measured is touched.")
        self._lettering_colour.setObjectName("secondary")
        self._lettering_colour.clicked.connect(self._pick_lettering_colour)
        self._lettering_chosen = "#22211f"
        line = self._row(rows, line, "Lettering colour", self._lettering_colour,
                         Hint("Any colour you like for the numbers and the "
                              "names of the axes.\n\n"
                              "These are the smallest text in the picture, so "
                              "they are the first thing to become unreadable "
                              "against an unusual background. Check them "
                              "against whatever you have set behind the shape "
                              "before saving — a mid grey reads on both a "
                              "light and a dark page, which is why it is the "
                              "safe choice for a picture going somewhere you "
                              "cannot control.", self))
        self._lettering_colour_row = line - 1

        self._gridlines = NoScrollComboBox(self)
        for key, label in picture.INK_CHOICES:
            self._gridlines.addItem(label, key)
        self._gridlines.currentIndexChanged.connect(self._went_custom)
        line = self._row(rows, line, "Grid lines", self._gridlines, Hint(
            "The faint lines ruled across the three walls, which are what let "
            "you see roughly where a part of the shape sits.\n\n"
            "FOLLOW THE BACKGROUND keeps them a fifth of the way from the wall "
            "colour towards the lettering — visible, and no louder than that. "
            "That is deliberate: at full contrast the lines bunch together "
            "where the walls meet and turn into a dark cage that shouts down "
            "the shape it is only there to frame.\n\n"
            "Set them DARK or LIGHT yourself if you want the box to stand out "
            "more, or to fall further back. A colour of your own is there if "
            "you want the box in a house colour.\n\n"
            "If you would rather have no box at all — no walls, no lines, no "
            "numbers, just the shape floating on the page — untick Show the "
            "box and its grid in the main window before saving. That is often "
            "the right answer for a picture going into a document.", self))
        self._gridlines_row = line - 1

        self._gridlines_colour = QPushButton("Choose a colour…", self)
        self._gridlines_colour.setToolTip(
            "Opens the colour picker for the GRID LINES ruled across the walls."
            "\n\nThe colours already in the picture are offered in the picker's own swatches, because matching the shape or the page it is going onto is the commonest thing to want here — and hunting for the same grey twice is how two panels end up almost matching.\n\nOnce you have chosen, this button shows the colour it is set to. It only changes what a picture LOOKS like; nothing measured is touched.")
        self._gridlines_colour.setObjectName("secondary")
        self._gridlines_colour.clicked.connect(self._pick_gridlines_colour)
        self._gridlines_chosen = "#d0ccc6"
        line = self._row(rows, line, "Grid colour", self._gridlines_colour,
                         Hint("Any colour you like for the lines across the "
                              "walls.\n\n"
                              "The grid is what lets you say WHERE something "
                              "is rather than only what shape it is — how "
                              "light a part of the surface is, or how far out "
                              "into the reds it reaches.\n\n"
                              "It should be quiet: just visible enough to "
                              "follow, never so strong that it competes with "
                              "the shape in front of it. If in doubt make it "
                              "fainter, because a grid that shouts is the "
                              "quickest way to make a good picture look "
                              "busy.", self))
        self._gridlines_colour_row = line - 1


        outer.addLayout(rows)

        # THE VIEW IS THE PREVIEW. Without this the only way to find out what
        # a look does was to save a file and open it; with it, everything above
        # happens in front of you and can be adjusted until it is right.
        self._live = QCheckBox("Live preview", self)
        self._live.setChecked(True)
        self._live.toggled.connect(self._changed)
        live_row = QHBoxLayout()
        live_row.setContentsMargins(0, 0, 0, 0)
        live_row.setSpacing(6)
        live_row.addWidget(self._live, 1)
        live_row.addWidget(Hint(
            "Puts everything chosen above straight onto the view in this "
            "window, so what you are looking at is exactly what a saved "
            "picture will hold — and stays that way while you work, rather "
            "than only while a dialog is open.\n\n"
            "Leave it ticked. It is the difference between choosing a "
            "background and seeing one: colours that sound right together are "
            "very often not, and nothing here has to be saved to find that "
            "out.\n\n"
            "It is also how you make the application look the way you want it "
            "to. The view is not a preview of something else — it is the "
            "thing — so a look you set up here is simply how the window is "
            "from now on, and it is remembered when you next open it.\n\n"
            "Untick it and the window goes back to its own dark or light "
            "colours, while everything chosen here is still applied to the "
            "file when you save it. The Save window shows a small picture of "
            "the result either way, so nothing is hidden.\n\n"
            "One thing cannot be shown here: SEE-THROUGH. There is no such "
            "thing as a see-through window, so a cut-out look is drawn on "
            "white while you work on it, and the small picture in the Save "
            "window shows it properly, on chequers.", self), 0,
            Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(live_row)
        self._refresh()

    def _row(self, grid, line, label, control, hint):
        """The name ABOVE its control, not beside it.

        Measured: the left-hand column is 346 pixels wide, and this section
        laid out the way the dialogs are — name, control, ⓘ, all in a row —
        asked for 492. It did not shrink to fit; it was simply cut off, taking
        the three small buttons beside the chooser off the edge with it.
        Stacking the name over the control gives every one of them the whole
        width, and the section now asks for less than the column has.
        """
        holder = QWidget(self)
        stack = QVBoxLayout(holder)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(2)
        if label:
            stack.addWidget(QLabel(label, holder))
        stack.addWidget(control)
        grid.addWidget(holder, line, 0)
        grid.addWidget(hint, line, 1, Qt.AlignmentFlag.AlignVCenter)
        hint.follow(control)
        return line + 1

    def _show_row(self, line: int, on: bool) -> None:
        for column in range(2):
            item = self._rows.itemAtPosition(line, column)
            if item is not None and item.widget() is not None:
                item.widget().setVisible(on)

    def live(self) -> bool:
        """Whether the window itself should wear this look."""
        return self._live.isChecked()

    def values(self) -> dict:
        """The eight choices, as the export and the viewer both want them."""
        return {
            "background": self._background.currentData(),
            "colour": self._chosen,
            "walls": self._walls.currentData(),
            "wall_colour": self._wall_chosen,
            "lettering": self._lettering.currentData(),
            "lettering_colour": self._lettering_chosen,
            "gridlines": self._gridlines.currentData(),
            "gridlines_colour": self._gridlines_chosen,
        }

    def restore(self, saved: dict) -> None:
        """Put back what was set last time this application was open."""
        self._settling = True
        try:
            for control, key in ((self._background, "background"),
                                 (self._walls, "walls"),
                                 (self._lettering, "lettering"),
                                 (self._gridlines, "gridlines")):
                at = control.findData(saved.get(key))
                if at >= 0:
                    control.setCurrentIndex(at)
            for button, key, attribute in (
                    (self._colour, "colour", "_chosen"),
                    (self._wall_colour, "wall_colour", "_wall_chosen"),
                    (self._lettering_colour, "lettering_colour",
                     "_lettering_chosen"),
                    (self._gridlines_colour, "gridlines_colour",
                     "_gridlines_chosen")):
                if saved.get(key):
                    setattr(self, attribute, saved[key])
                    button.setText(f"  {saved[key]}")
            at = self._look.findData(saved.get("look", "screen"))
            if at >= 0:
                self._look.setCurrentIndex(at)
            self._details.setChecked(bool(saved.get("details")))
            self._live.setChecked(saved.get("live", True) not in (False, "false"))
        finally:
            self._settling = False
        self._refresh()

    def chosen_look(self) -> str:
        return str(self._look.currentData() or "screen")

    def details_open(self) -> bool:
        return self._details.isChecked()

    def _changed(self, *_a) -> None:
        if self._on_change is not None and not self._settling:
            self._on_change()

    def _refresh(self, *_a) -> None:
        open_up = self._details.isChecked()
        for row in (self._background_row, self._walls_row,
                    self._lettering_row, self._gridlines_row):
            self._show_row(row, open_up)
        self._show_row(self._colour_row, open_up
                       and self._background.currentData() == "custom")
        self._show_row(self._wall_colour_row, open_up
                       and self._walls.currentData() == "custom")
        self._show_row(self._lettering_colour_row, open_up
                       and self._lettering.currentData() == "custom")
        self._show_row(self._gridlines_colour_row, open_up
                       and self._gridlines.currentData() == "custom")
        key = self.chosen_look()
        if key.startswith("mine:"):
            import looks as _looks
            entry = getattr(self, "_saved_looks", {}).get(key)
            self._look_why.setText(_looks.describe(entry) if entry else "")
        else:
            self._look_why.setText(picture.look_because(key))
        self._show_row(self._look_why_row, bool(self._look_why.text()))
        self._changed()

    def _fill_looks(self) -> None:
        """The ready-made looks, then whatever this person has saved.

        Read from the folder every time rather than once at startup, so a look
        somebody sent you and dropped in appears as soon as you open this
        window again — nothing to import, and nothing to restart.
        """
        import looks as _looks

        keep = self._look.currentData() if self._look.count() else "screen"
        self._look.blockSignals(True)
        self._look.clear()
        for key, label, _why, _values in picture.LOOKS:
            if key == "custom":
                continue                     # always last, after the saved ones
            self._look.addItem(label, key)
        self._saved_looks = {}
        try:
            mine = _looks.load_all()
        except Exception as exc:             # noqa: BLE001 — never fatal
            _log().warning("saved looks could not be read: %s", exc)
            mine = []
        for entry in mine:
            key = f"mine:{entry['name']}"
            self._saved_looks[key] = entry
            self._look.addItem(f"{entry['name']} (yours)", key)
        self._look.addItem("My own settings", "custom")
        at = self._look.findData(keep)
        self._look.setCurrentIndex(at if at >= 0 else 0)
        self._look.blockSignals(False)
        self._look_remove.setEnabled(
            str(self._look.currentData() or "").startswith("mine:"))

    def _save_look(self) -> None:
        """Keep what is set now, under a name, as a file that can be shared."""
        import looks as _looks

        from PyQt6.QtWidgets import QInputDialog

        suggested = ""
        current = self._look.currentData()
        if str(current or "").startswith("mine:"):
            suggested = str(current)[5:]
        name, said = QInputDialog.getText(
            self, "Save this look",
            "A name for it — something that says where you use it, such as\n"
            "“Our white reports” or “Dark slides”:", text=suggested)
        if not said or not name.strip():
            return
        values = self.choices()
        try:
            where = _looks.save(name.strip(), values)
        except Exception as exc:             # noqa: BLE001 — always explain
            Notice.warn(self, "That look could not be saved", str(exc))
            return
        self._fill_looks()
        at = self._look.findData(f"mine:{_looks.safe_name(name.strip())}")
        if at >= 0:
            self._look.blockSignals(True)
            self._look.setCurrentIndex(at)
            self._look.blockSignals(False)
            self._look_remove.setEnabled(True)
        self._refresh()
        Notice.say(self, "Saved",
                   f"“{name.strip()}” is now in the list.\n\n"
                   f"It is one file, here:\n{where}\n\n"
                   "Send that file to somebody and they can drop it into the "
                   "same folder on their computer to get the same look. The "
                   "… button beside the list opens the folder.")

    def _remove_look(self) -> None:
        """Take a saved look off the list, keeping the file itself."""
        import looks as _looks

        key = str(self._look.currentData() or "")
        if not key.startswith("mine:"):
            return
        name = key[5:]
        if not Notice.ask(
                self, f"Take “{name}” off the list?",
                "It comes off the list of looks straight away.\n\n"
                "The file itself is NOT deleted — it is moved into an “old” "
                "folder beside the others, with today's date on it. If you "
                "change your mind, or took the wrong one off, it is still "
                "there and can be moved back.",
                yes="Take it off", no="Keep it"):
            return
        try:
            moved = _looks.remove(name)
        except Exception as exc:             # noqa: BLE001 — always explain
            Notice.warn(self, "That look could not be removed", str(exc))
            return
        self._fill_looks()
        self._refresh()
        Notice.say(self, "Taken off the list",
                   f"“{name}” is no longer offered.\n\nThe file is kept, "
                   f"here:\n{moved}")

    def _open_looks_folder(self) -> None:
        """Show the folder saved looks live in, for sharing one either way."""
        import looks as _looks

        where = _looks.folder()
        try:
            where.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            Notice.warn(self, "That folder could not be opened", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(where)))

    def _apply_look(self, *_a) -> None:
        """Set every background choice at once from the look that was picked.

        NOTHING IS LOST BY TRYING ONE. A look only moves the controls below it,
        every one of which can be moved back, and the picture underneath shows
        the result straight away — so choosing one is a thing to experiment
        with rather than a decision to weigh up.
        """
        key = str(self._look.currentData() or "")
        self._look_remove.setEnabled(key.startswith("mine:"))
        if key.startswith("mine:"):
            entry = getattr(self, "_saved_looks", {}).get(key)
            values = dict(entry["look"]) if entry else None
        else:
            values = picture.look(key)
        if values is None:                  # "My own settings" — leave it be
            self._refresh()
            return
        self._settling = True
        try:
            for control, name in ((self._background, "background"),
                                  (self._walls, "walls"),
                                  (self._lettering, "lettering"),
                                  (self._gridlines, "gridlines")):
                if name in values:
                    at = control.findData(values[name])
                    if at >= 0:
                        control.setCurrentIndex(at)
            for button, field, attribute in (
                    (self._wall_colour, "wall_colour", "_wall_chosen"),
                    (self._colour, "colour", "_chosen"),
                    (self._lettering_colour, "lettering_colour",
                     "_lettering_chosen"),
                    (self._gridlines_colour, "gridlines_colour",
                     "_gridlines_chosen")):
                if field in values:
                    setattr(self, attribute, values[field])
                    button.setText(f"  {values[field]}")
        finally:
            self._settling = False
        self._refresh()

    def _went_custom(self, *_a) -> None:
        """One of the details was changed by hand, so the look is now theirs."""
        if getattr(self, "_settling", False):
            return                          # this was a look being applied
        at = self._look.findData("custom")
        if at >= 0 and self._look.currentIndex() != at:
            self._look.blockSignals(True)
            self._look.setCurrentIndex(at)
            self._look.blockSignals(False)
        self._refresh()

    def _pick_colour(self) -> None:
        picked = pick_colour(self, self._chosen,
                             "A colour behind the shape")
        if picked:
            self._chosen = picked
            self._colour.setText(f"  {picked}")
            self._went_custom()

    def _pick_wall_colour(self) -> None:
        picked = pick_colour(self, self._wall_chosen,
                             "A colour for the grid's walls")
        if picked:
            self._wall_chosen = picked
            self._wall_colour.setText(f"  {picked}")
            self._went_custom()

    def _pick_lettering_colour(self) -> None:
        picked = pick_colour(self, self._lettering_chosen,
                             "A colour for the numbers and names")
        if picked:
            self._lettering_chosen = picked
            self._lettering_colour.setText(f"  {picked}")
            self._went_custom()

    def _pick_gridlines_colour(self) -> None:
        picked = pick_colour(self, self._gridlines_chosen,
                             "A colour for the lines on the walls")
        if picked:
            self._gridlines_chosen = picked
            self._gridlines_colour.setText(f"  {picked}")
            self._went_custom()

class PictureDialog(QDialog):
    """Choosing what kind of picture to make.

    Everything here is a question somebody would actually ask -- how big, what
    kind of file, what is behind it -- and the line at the foot says how large
    the answer will be, so nobody presses Save and is handed a forty-megabyte
    surprise.
    """

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("Save this view as a picture")
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(10)
        self._parent = parent

        rows = QGridLayout()
        rows.setHorizontalSpacing(8)
        rows.setVerticalSpacing(8)
        rows.setColumnStretch(1, 1)
        line = 0

        self._kind = NoScrollComboBox(self)
        self._kind.addItem("A still picture", "still")
        self._kind.addItem("A moving picture or a film that turns and repeats",
                           "moving")
        self._kind.currentIndexChanged.connect(self._refresh)
        line = self._row(rows, line, "What to make", self._kind, Hint(
            "A STILL is one picture: the shape exactly as it stands, at "
            "whatever size you ask for. It can be far larger than this window "
            "and razor sharp, because the viewer draws it again rather than "
            "copying the screen.\n\n"
            "A MOVING PICTURE turns the shape and repeats, for ever, in a "
            "file you can drop into a forum post or a chat the same way as a "
            "still. It shows every side in the space one picture takes — which "
            "is the whole difficulty with a gamut on paper, where you only "
            "ever see one face of it.\n\n"
            "The same choice also makes a FILM — an MP4 or a WebM. A film is "
            "much smaller for the same sharpness and is what you want for "
            "anything long or large; a moving picture is what you want where "
            "it has to start by itself with nothing to press. Both are made "
            "the same way here, and Kind of file is where you say which.\n\n"
            "Either way it is copied from this window as it is, so it comes "
            "out the size the window is. If you want something enormous and "
            "perfectly sharp, take a still.", self))

        self._format = NoScrollComboBox(self)
        self._format.currentIndexChanged.connect(self._refresh)
        line = self._row(rows, line, "Kind of file", self._format, Hint(
            "PNG is the safe answer: sharp, lossless, and it can be "
            "see-through. Every program opens one.\n\n"
            "WEBP is the same picture in a file several times smaller, and "
            "everything made in the last few years opens it. Worth choosing "
            "for anything going on a website or into a message.\n\n"
            "JPEG makes the smallest file of all, and pays for it: fine "
            "detail is smeared a little and it cannot be see-through.\n\n"
            "SVG is not made of pixels at all — it is the outlines "
            "themselves, so it stays perfectly sharp however far it is "
            "enlarged, and the file is tiny. The right choice for a printed "
            "document or a poster.\n\n"
            "It is offered for the flat cross-section only. The 3D view is "
            "drawn by your graphics card, and there are no outlines in it to "
            "save — an SVG of it would just be an ordinary picture in an SVG "
            "wrapper, thirty times the size and no sharper. Tick Slice it at "
            "one lightness if you want a drawing that scales.\n\n"
            "FOR A MOVING PICTURE there are two families here, and which you "
            "want depends entirely on where it is going.\n\n"
            "WEBP, GIF and APNG are pictures that happen to move. They drop "
            "into a forum post, a README, a chat window or a document exactly "
            "like a still, they start on their own and they repeat for ever "
            "with no play button and nothing to press. WebP is the one to "
            "choose: full colour, and a fraction of the size of the other two. "
            "GIF is there because a few places still take nothing else, and it "
            "holds only 256 colours — on a gamut, whose whole subject is "
            "colour, the gradients come out in visible bands. APNG is "
            "lossless and perfectly sharp, and several times larger than "
            "WebP.\n\n"
            "MP4 and WEBM are films. For the same sharpness they are markedly "
            "smaller — about half the WebP for H.264, and nearer a third for "
            "H.265 and VP9, measured on this application's own view. The trade "
            "is that a film has a play button: "
            "somewhere like a README it shows as a still with a triangle on "
            "it, and it repeats only if the player is set to repeat.\n\n"
            "MP4 (H.264) is the one everything plays — every phone, every "
            "browser, every chat window, going back years. MP4 (H.265) is the "
            "same picture in roughly half the file, and needs a device from "
            "about 2016 onwards. WEBM (VP9) is for a web page, and it is the "
            "only moving kind here that can be see-through.\n\n"
            "The films are made by ffmpeg, which comes with this application. "
            "If a line here says “not available here”, hold the pointer over "
            "it and it will say why.", self))

        self._size = NoScrollComboBox(self)
        for key, label, width in picture.SIZES:
            self._size.addItem(f"{label}"
                               + (f"  ({width} px)" if width else ""), key)
        self._size.setCurrentIndex(1)
        self._size.currentIndexChanged.connect(self._refresh)
        line = self._row(rows, line, "How large", self._size, Hint(
            "Named by what the picture is for, because that is the question "
            "you actually have. The width in pixels is beside each one for "
            "anybody who thinks in those.\n\n"
            "For a forum post or an email, 1600 is plenty and keeps the file "
            "small. For a document, 2400 stays sharp when somebody zooms in. "
            "For printing, 3600 is about 300 dots an inch across a 30 cm "
            "page.\n\n"
            "Bigger is not automatically better: a picture four times the "
            "width is sixteen times the file, and nobody thanks you for a "
            "forty-megabyte attachment. This only applies to a still — a "
            "moving picture comes out the size of the window.", self))

        self._custom = NoScrollSpinBox(self)
        self._custom.setRange(picture.MIN_WIDTH, picture.MAX_WIDTH)
        self._custom.setValue(2400)
        self._custom.setSuffix(" px wide")
        self._custom.valueChanged.connect(self._refresh)
        line = self._row(rows, line, "Width", self._custom, Hint(
            "The exact width you want, in pixels. The height follows the "
            "shape of the window, so the picture is never stretched.\n\n"
            "Anything from 200 to 8000. The upper limit is there because a "
            "picture larger than that takes a long time to draw and is bigger "
            "than anything will display.", self))
        self._custom_row = line - 1

        self._quality = NoScrollSlider(Qt.Orientation.Horizontal, self)
        self._quality.setRange(40, 100)
        self._quality.setValue(90)
        self._quality.valueChanged.connect(self._refresh)
        line = self._row(rows, line, "Quality", self._quality, Hint(
            "How much detail is kept in the kinds of file that trade some "
            "away for a smaller size.\n\n"
            "90 is a good place to be: no difference you would notice, at a "
            "fraction of the size. Below about 70 the smooth gradients across "
            "a gamut start to show blotches, which is exactly the thing the "
            "picture is meant to show. Lossless kinds ignore this entirely, "
            "so it disappears when you choose one.\n\n"
            "IT MATTERS MOST ON SOMETHING THAT MOVES. A surface that is "
            "perfectly clean in a still can shimmer as it turns, because the "
            "encoder makes a slightly different job of each frame and the eye "
            "is very good at spotting that. If a saved loop looks like it is "
            "crawling, this is the setting to raise — 95 or higher costs a "
            "little size and stops it.\n\n"
            "For a film it becomes the encoder's own quality setting rather "
            "than a size, so the same number means the same picture whether "
            "you choose H.264, H.265 or VP9. Each of the three needs a "
            "different figure internally for that, which is done for you.",
            self))
        self._quality_row = line - 1

        self._moving_size = NoScrollComboBox(self)
        self._moving_size.addItem("The size of the window", 0)
        self._moving_size.addItem("1200 px wide", 1200)
        self._moving_size.addItem("900 px wide — good for a README", 900)
        self._moving_size.addItem("600 px wide — small file", 600)
        self._moving_size.addItem("A width of my own", -1)
        self._moving_size.currentIndexChanged.connect(self._refresh)
        line = self._row(rows, line, "How large", self._moving_size, Hint(
            "How wide the moving picture is.\n\n"
            "A moving picture is copied from this window as it stands, so the "
            "window's own size is as large as it can be — asking for more "
            "would only stretch it and make it blurry. Anything smaller is "
            "scaled down cleanly, and that is usually what you want: a loop "
            "for a page or a forum post rarely needs to be more than about "
            "900 pixels across, and every pixel you drop makes the file "
            "markedly smaller.\n\n"
            "If you want a bigger moving picture than the largest offered "
            "here, make the window itself bigger and open this again — the "
            "list follows whatever the window is.", self))
        self._moving_size_row = line - 1

        self._moving_width = NoScrollSpinBox(self)
        self._moving_width.setRange(120, 4000)
        self._moving_width.setValue(900)
        self._moving_width.setSuffix(" px wide")
        self._moving_width.valueChanged.connect(self._refresh)
        line = self._row(rows, line, "Width", self._moving_width, Hint(
            "The exact width you want. The height follows the shape of the "
            "window, so nothing is stretched, and anything wider than the "
            "window is brought back down to it — a copy of the screen cannot "
            "hold more detail than the screen had.", self))
        self._moving_width_row = line - 1

        self._seconds = NoScrollSlider(Qt.Orientation.Horizontal, self)
        self._seconds.setRange(2, 12)
        self._seconds.setValue(6)
        self._seconds.valueChanged.connect(self._refresh)
        line = self._row(rows, line, "How long", self._seconds, Hint(
            "How many seconds one time round takes before it repeats.\n\n"
            "Six is comfortable: long enough to follow one part of the "
            "surface all the way round, short enough that somebody watching "
            "does not lose patience. Longer means a bigger file, since every "
            "second is more frames.\n\n"
            "It loops for ever and joins up exactly, so there is no jump each "
            "time it comes round.\n\n"
            "This is what decides how fast the saved picture moves, and the "
            "How fast slider in the main window does not: the file always "
            "holds exactly one complete journey — once round for a full turn, "
            "or once there and back for a swing — fitted into the seconds you "
            "choose here. That is precisely what lets it join up perfectly "
            "every time, whatever else is set. If the movement in the file "
            "looks too quick, ask for more seconds.", self))
        self._seconds_row = line - 1

        self._fps = NoScrollComboBox(self)
        for n, label in ((15, "15 a second — smallest file"),
                         (24, "24 a second — smooth, like film"),
                         (25, "25 a second — European television"),
                         (30, "30 a second — smoother"),
                         (50, "50 a second — very smooth, large file"),
                         (60, "60 a second — smoothest, largest file")):
            self._fps.addItem(label, n)
        self._fps.setCurrentIndex(1)
        self._fps.currentIndexChanged.connect(self._refresh)
        line = self._row(rows, line, "Smoothness", self._fps, Hint(
            "How many pictures make up each second of movement.\n\n"
            "24 is what film uses, and for something turning slowly it "
            "already looks perfectly smooth — most people cannot tell it from "
            "60. 15 halves the file and is still quite watchable for a gentle "
            "rotation.\n\n"
            "25 and 50 are the European television rates, worth choosing if "
            "the picture is going somewhere that expects them. 30 and 60 are "
            "the American ones, and 60 is as smooth as anything gets.\n\n"
            "Above 30 the file grows quickly for a difference you will "
            "struggle to see on a shape that is drifting round. If you want "
            "smoother movement rather than more frames of it, slow the "
            "turning down instead — the same journey over more seconds looks "
            "calmer at any rate.\n\n"
            "It only affects the moving picture, and it changes the file size "
            "more than anything else here.", self))
        self._fps_row = line - 1

        outer.addLayout(rows)

        # WHAT IT WILL ACTUALLY LOOK LIKE. Every one of these choices changes
        # the picture, and two of them change it in ways nothing on screen can
        # show: a see-through background is not something the window can be
        # made to display, and lettering chosen for somewhere else is by
        # definition not lettering for here. Without this the only way to find
        # out was to save the file and open it.
        self._preview_label = QLabel("What you will get", self)
        self._preview_label.setObjectName("hint")
        outer.addWidget(self._preview_label)
        self._preview = QLabel(self)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(150)
        outer.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignHCenter)
        # Redrawing costs a copy of the window, so a slider being dragged waits
        # until it stops rather than taking one for every pixel of travel.
        self._preview_soon = QTimer(self)
        self._preview_soon.setSingleShot(True)
        self._preview_soon.setInterval(220)
        self._preview_soon.timeout.connect(self._draw_preview)

        self._summary = WrappedLabel("", self)
        self._summary.setObjectName("hint")
        outer.addWidget(self._summary)

        # THE OTHER EXPORT, NAMED HERE. Two ways of saving a view and nothing
        # saying which to reach for is how somebody ends up sending a picture
        # when they wanted the turnable page, or trying to attach the page to
        # a forum post that will not take it. One line each way.
        pair = WrappedLabel(
            "A picture goes straight into a forum post, an email or a "
            "document, and everybody can see it without clicking. If you want "
            "the person at the other end to be able to turn the shape "
            "themselves, use Save this view as a web page… instead — or send "
            "both, which is what reads best in a post.", self)
        pair.setObjectName("hint")
        outer.addWidget(pair)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Choose where to save…", self)
        save.clicked.connect(self.accept)
        save.setDefault(True)
        buttons.addWidget(save)
        outer.addLayout(buttons)

        self._rows = rows
        self._refresh()

    def _row(self, grid, line, label, control, hint):
        name = QLabel(label, self)
        grid.addWidget(name, line, 0)
        grid.addWidget(control, line, 1)
        grid.addWidget(hint, line, 2, Qt.AlignmentFlag.AlignVCenter)
        hint.follow(control)
        return line + 1

    def _show_row(self, line: int, on: bool) -> None:
        for column in range(3):
            item = self._rows.itemAtPosition(line, column)
            if item is not None and item.widget() is not None:
                item.widget().setVisible(on)

    def _refresh(self, *_a) -> None:
        moving = self._kind.currentData() == "moving"
        wanted = MOVING_KINDS if moving else STILL_KINDS
        # SVG MEANS "MADE OF LINES", and the 3D view is not: it is drawn by
        # the graphics card, so what comes out is a picture inside an SVG
        # wrapper -- 426 kB against 12, and no sharper when enlarged. Measured.
        # It is offered for the flat cross-section, which really is lines.
        if not moving and not self._parent._slice_on.isChecked():
            wanted = tuple(k for k in wanted if k[0] != "svg")
        if [self._format.itemData(i) for i in range(self._format.count())] != \
                [k for k, _l in wanted]:
            self._format.blockSignals(True)
            self._format.clear()
            for key, label in wanted:
                self._format.addItem(label, key)
            # A FORMAT THAT CANNOT BE MADE HERE IS SHOWN, NOT HIDDEN. Quietly
            # dropping MP4 from the list would leave somebody looking for
            # something they have every reason to expect and no way to find out
            # why it is missing. Greyed out, with the reason a click away, at
            # least answers the question.
            model = self._format.model()
            for row, (key, _label) in enumerate(wanted):
                codec = picture.codec_for(key)
                if codec and not movie.can_write(codec):
                    item = model.item(row)
                    if item is not None:
                        item.setEnabled(False)
                        item.setText(f"{_label}  — not available here")
                        item.setToolTip(movie.why_not(codec) or "")
            self._format.blockSignals(False)
            if not self._format.currentData() or self._format.currentIndex() < 0:
                self._format.setCurrentIndex(0)
            # Landing on a greyed row would leave Save doing nothing, so step
            # off it to the first one that can actually be made.
            while (self._format.currentIndex() < self._format.count() - 1
                   and not self._format.model().item(
                       self._format.currentIndex()).isEnabled()):
                self._format.setCurrentIndex(self._format.currentIndex() + 1)
        fmt = self._format.currentData() or wanted[0][0]
        custom = self._size.currentData() == "custom"
        self._show_row(self._custom_row, custom and not moving)
        # THE QUALITY SLIDER APPLIES TO MOVING PICTURES TOO, and it was hidden
        # for them — so an animated WebP was written at whatever the library
        # felt like, which is 80, and the surface shimmered as it turned. It
        # means the same thing for a film, where it becomes the encoder's
        # quality rather than a file size.
        self._show_row(self._quality_row, picture.is_lossy(fmt))

        for line in (self._seconds_row, self._fps_row, self._moving_size_row):
            self._show_row(line, moving)
        self._show_row(self._moving_width_row,
                       moving and self._moving_size.currentData() == -1)
        for key, _label, width in picture.SIZES:
            if key == self._size.currentData() and width:
                self._custom.blockSignals(True)
                self._custom.setValue(width)
                self._custom.blockSignals(False)
        self._show_row(self._custom_row - 1, not moving)   # the size row itself

        view = self._parent._view
        if moving:
            shot = view.grab()
            wide, tall = shot.width(), shot.height()
            asked = self._moving_size.currentData()
            if asked == -1:
                asked = self._moving_width.value()
            if asked and asked < wide:
                tall = int(round(tall * asked / wide))
                wide = asked
            frames = picture.frames_for(self._seconds.value(),
                                        self._fps.currentData(),
                                        self._parent._turn_mode.currentData()
                                        or "round")
        else:
            wide = picture.clamp_width(self._custom.value())
            tall = int(round(wide * view.height() / max(1, view.width())))
            frames = 1
        self._preview_soon.start()
        said = picture.describe(wide, tall, fmt, frames, self._quality.value())
        if moving and not movie.find_ffmpeg():
            said += ("\n\nMP4 and WebM are greyed out because no ffmpeg was "
                     "found. WebP needs nothing and makes an excellent moving "
                     "picture; for the films, see “Where ffmpeg is…” in the "
                     "left-hand column.")
        self._summary.setText(said)

    def _draw_preview(self) -> None:
        """Show the scene exactly as it will be saved.

        THE SAME CODE PATH AS THE EXPORT, deliberately: the preview asks the
        parent window for one frame made the way a saved frame is made, so it
        cannot drift away from what the file will hold. A preview that is a
        second opinion is worse than none.
        """
        try:
            shot = self._parent.preview_frame(self.choices())
        except Exception as exc:                # noqa: BLE001 — never fatal
            _log().debug("preview could not be drawn: %s", exc)
            self._preview.clear()
            self._preview_label.setText(
                "What you will get — not available for this view")
            return
        if shot is None:
            self._preview.clear()
            return
        self._preview.setPixmap(shot)
        clear = self._background_choice() == "transparent"
        self._preview_label.setText(
            "What you will get — the chequers are what will be see-through"
            if clear else "What you will get")

    def _background_choice(self) -> str:
        return self._parent.look_choices().get("background", "as-shown")

    def choices(self) -> dict:
        want = {
            "moving": self._kind.currentData() == "moving",
            "format": self._format.currentData(),
            "width": self._custom.value(),
            "quality": self._quality.value(),
            "seconds": self._seconds.value(),
            "fps": self._fps.currentData(),
            "moving_width": (self._moving_width.value()
                             if self._moving_size.currentData() == -1
                             else self._moving_size.currentData()),
        }
        # THE LOOK COMES FROM THE WINDOW, not from here. It is chosen in the
        # left-hand column, where it can be seen on the actual view rather
        # than guessed at inside a dialog — so this simply asks for it.
        want.update(self._parent.look_choices())
        return want


#: The two lists the dialog swaps between, kept beside it.
STILL_KINDS = tuple((k, l) for k, l, _t, _q in picture.STILL_FORMATS)
MOVING_KINDS = tuple((k, l) for k, l, _t, _e, _c in picture.MOVING_FORMATS)



class FadingScrollArea(QScrollArea):
    """A scrolling list that says so, by fading out at the edge there is more.

    A list clipped by a hard line reads as a list that has ended. That is the
    whole fault: somebody looks at five groups of tick boxes, sees the last
    one cut off square at the bottom of the box, and has no reason to think a
    sixth exists. A scrollbar answers it only once they have gone looking for
    one, and on a trackpad the bar is not even drawn until they scroll.

    So the last few points of the list are faded towards the colour behind it,
    at whichever end still has something past it -- both ends when the list is
    in the middle, neither when it all fits. It follows the palette rather
    than painting a fixed dark, so it is right in light mode too.
    """

    #: How deep the fade is, in points. Enough that a row of tick boxes is
    #: visibly dissolving rather than merely dimmed, and not so much that it
    #: hides a row somebody is trying to read.
    DEPTH = 26

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # AN OVERLAY, NOT A PAINT ON THE VIEWPORT.
        #
        # The obvious two ways both put the gradient UNDERNEATH the rows it is
        # meant to fade, and the first attempt here did exactly that: this
        # widget's own paintEvent runs before its child viewport draws, and an
        # event filter on the viewport runs before the viewport's own handler
        # too. Either way the tick boxes land on top of the fade and nothing
        # shows. A child widget raised above the viewport paints last, which
        # is the only ordering that works.
        self._veil = _ScrollVeil(self)
        bar = self.verticalScrollBar()
        bar.valueChanged.connect(self._veil.update)
        bar.rangeChanged.connect(lambda *_: self._veil.update())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        view = self.viewport()
        self._veil.setGeometry(view.x(), view.y(), view.width(), view.height())
        self._veil.raise_()

    def fades(self) -> tuple:
        """(top, bottom) depth of the fade right now, in points.

        Returned rather than only drawn so a test can ask whether the edge
        with something past it is the edge being faded, without reading
        pixels.
        """
        bar = self.verticalScrollBar()
        if bar.maximum() <= bar.minimum():
            return (0, 0)                                  # it all fits
        tall = self.viewport().height()
        return tuple(
            min(self.DEPTH, tall // 3, room) if room > 0 else 0
            for room in (bar.value() - bar.minimum(),
                         bar.maximum() - bar.value()))


class _ScrollVeil(QWidget):
    """The gradient itself, sitting over a `FadingScrollArea`'s viewport."""

    def __init__(self, area) -> None:
        super().__init__(area)
        self._area = area
        # IT MUST NOT EAT THE SCROLL. A plain child widget over the viewport
        # swallows the wheel and every click that lands on it, so the list
        # would go dead under the very edge this is drawing attention to.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        from PyQt6.QtGui import QLinearGradient, QPainter

        top_deep, bottom_deep = self._area.fades()
        if not (top_deep or bottom_deep):
            return
        # THE COLOUR BEHIND THE LIST, so this is right in light mode too --
        # a fade to a fixed dark would draw a grey smear on a white dialog.
        behind = self._area.palette().color(
            self._area.viewport().backgroundRole())
        paint = QPainter(self)
        paint.setPen(Qt.PenStyle.NoPen)
        for at_top, deep in ((True, top_deep), (False, bottom_deep)):
            if deep <= 0:
                continue
            edge = 0 if at_top else self.height() - deep
            fade = QLinearGradient(0, edge, 0, edge + deep)
            solid, clear = QColor(behind), QColor(behind)
            solid.setAlpha(255)
            clear.setAlpha(0)
            fade.setColorAt(0.0, solid if at_top else clear)
            fade.setColorAt(1.0, clear if at_top else solid)
            paint.fillRect(0, edge, self.width(), deep, fade)
        paint.end()


class WebPageDialog(QDialog):
    """Choosing what the saved web page carries.

    The page is the export that stays turnable, so the questions are about
    what travels with it: the viewer that draws it, and the numbers that say
    what it is.
    """

    #: WHICH SWITCHES DEPEND ON WHAT IS IN THE PAGE, and what has to be true
    #: for each. Everything not named here applies to any page there is.
    #:
    #: Asked for in as many words: "the export dialog should only allow to
    #: choose control options for the webviewer navigation of the exported
    #: variant that are applicable for what is exported". It does make sense,
    #: and more than the one case that prompted it: a page of one shape was
    #: offering "fade where they agree", which needs two; a cross-section was
    #: offering four ways to turn a camera it does not have; and a page with
    #: nothing but a cloud of dots in it was offering to draw the surfaces as
    #: wires.
    #:
    #: A SWITCH THAT CANNOT ACT IS WORSE THAN A MISSING ONE -- this file's own
    #: rule, applied to the dialog that hands them out.
    NEEDS = {
        # FADING ONE AGAINST THE OTHER NEEDS TWO SHAPES **AND A ROOM**. The
        # first version of this asked only for two, and the offers audit found
        # it: a cross-section of two papers was offering the fade, and the
        # page does not build it there. "two_shapes" was the rule I assumed;
        # "fade" is the rule the page actually follows.
        "agree": "fade",
        # AND OPACITY AND GREY ARE NOT ABOUT SURFACES, which is the same
        # mistake the other way round. A drift cloud has no surfaces at all
        # and still builds both -- its colour families are the things being
        # made fainter or grey. Withholding them meant a reader saving that
        # page could not hand over two controls it was going to have anyway.
        "wires": "surfaces",         # a cloud of dots has no edges to draw
        "cut": "flat",               # the cross-section's own slider
        "play": "camera",            # a flat page has no camera at all
        "speed": "camera",
        "speed_each": "camera",
        "sweep": "camera",
        "lr": "camera",
        "ud": "camera",
        "glide": "camera",
        "views": "camera",
    }

    def __init__(self, parent, for_a_cloud: bool = True, shows=None) -> None:
        """*for_a_cloud* False when the view is a flat line graph.

        A LINE CHART HAS NO CAMERA TO TURN AND NO FAMILIES TO HIDE, so the
        questions about what the reader may do with the shape are put away
        rather than asked and quietly ignored. Offering a control that cannot
        exist is the same fault as a button that cannot act, which this file
        holds is worse than a missing one.

        *shows* says what is actually in the page being written --
        ``{"two_shapes": bool, "surfaces": bool, "flat": bool,
        "camera": bool}`` -- and switches that need something absent are left
        out. Absent, everything is offered, which is what every caller that
        has not been taught to describe its page gets.
        """
        super().__init__(parent)
        self._for_a_cloud = bool(for_a_cloud)
        self._shows = dict(shows or {})
        self.setWindowTitle("Save this view as a web page")
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(10)
        rows = QGridLayout()
        rows.setHorizontalSpacing(8)
        rows.setVerticalSpacing(8)
        rows.setColumnStretch(1, 1)

        self._carry = NoScrollComboBox(self)
        self._carry.addItem("Carry the viewer inside it — works anywhere", True)
        self._carry.addItem("Fetch it when opened — about 4.7 MB smaller", False)
        rows.addWidget(QLabel("The file", self), 0, 0)
        rows.addWidget(self._carry, 0, 1)
        carry_hint = Hint(
            "Whether the little program that draws the shape travels inside "
            "the page or is fetched when somebody opens it.\n\n"
            "CARRYING IT is the safe answer and the one to keep for anything "
            "you are storing. The page works on a machine that has never been "
            "online, on an aeroplane, and in ten years when the place it "
            "would have fetched from has gone. The viewer adds about 4.7 MB "
            "to the file.\n\n"
            "FETCHING IT leaves that 4.7 MB out, which is often the "
            "difference between an email that sends and one that bounces. The "
            "cost is that whoever opens it needs an internet connection the "
            "first time, and that in some years' time it may stop working "
            "altogether.\n\n"
            "Your measurements travel inside the page either way, so the "
            "smaller file is still not tiny — a chart of a thousand patches "
            "with something to compare it against carries a good deal of its "
            "own numbers.\n\n"
            "Your measurements are inside the page either way. Nothing about "
            "them is ever sent anywhere.\n\n"
            "GETTING IT TO SOMEBODY. It is a single file, so it travels the "
            "way any file does: attach it to an email, put it on a memory "
            "stick, or drop it in whatever you share folders with. Whoever "
            "receives it opens it by double-clicking — there is nothing to "
            "install.\n\n"
            "PUTTING IT IN A FORUM POST is the one thing you cannot do "
            "directly, and it is worth knowing why: forums deliberately strip "
            "web pages out of posts, because a page can carry a program and "
            "no forum can afford to run a stranger's. So no forum will show "
            "this inside a post, and most will not accept it as an "
            "attachment either.\n\n"
            "WHAT TO DO INSTEAD, and it reads better anyway: put a PICTURE in "
            "the post and a LINK underneath it. Use Save this view as a "
            "picture… for the picture — a still, or a few seconds of the "
            "shape turning — so people see what you mean without clicking "
            "anything. Then upload this page anywhere that gives you a web "
            "address and put that address under the picture, for anyone who "
            "wants to turn the shape themselves.\n\n"
            "For that, choose Fetch it when opened above: it makes the file "
            "about 4.7 MB smaller, which is the difference between something "
            "you can upload almost anywhere and something you cannot.", self)
        carry_hint.setObjectName("hint_carry_hint")
        rows.addWidget(carry_hint, 0, 2, Qt.AlignmentFlag.AlignVCenter)
        carry_hint.follow(self._carry)

        self._numbers = QCheckBox("Put the numbers under the picture", self)
        self._numbers.setChecked(True)
        rows.addWidget(self._numbers, 1, 0, 1, 2)
        numbers_hint = Hint(
            "Adds everything the readouts on the left are showing — how much "
            "colour each shape holds, how much of one fits inside the other "
            "both ways round, and any drift between two readings — as plain "
            "text underneath the picture.\n\n"
            "Worth keeping on for anything you are sending to somebody else. "
            "A shape on its own is a shape they cannot check: it does not say "
            "which paper, measured against what, or how big it actually is. "
            "With the numbers there the page answers those questions without "
            "anybody having to ask you.\n\n"
            "Turn it off if you want nothing but the picture.", self)
        numbers_hint.setObjectName("hint_numbers_hint")
        rows.addWidget(numbers_hint, 1, 2, Qt.AlignmentFlag.AlignVCenter)
        numbers_hint.follow(self._numbers)

        # HOW THE PAGE BEHAVES, not which buttons it carries -- which is why
        # this sits up here with the other two questions about the page itself
        # rather than down in the list of controls to hand over. A page saved
        # with no controls at all still has this, or does not.
        self._glide = QCheckBox(
            "Let the shape carry on turning when they let go", self)
        self._glide.setChecked(True)
        rows.addWidget(self._glide, 2, 0, 1, 2)
        # AND NOT WHERE THERE IS NO CAMERA TO CARRY ON TURNING. This one
        # sits with the questions about the page rather than in the list of
        # controls, so the rule that puts the list away (NEEDS says glide
        # needs a camera) never reached it.
        #
        # KEYED ON THE CAMERA, NOT ON "is it a cloud", and that second version
        # is the one the audit caught: hidden only for a line graph, it was
        # still offered over a CROSS-SECTION, which is drawn flat and has no
        # camera either. Same promise the file cannot keep, one page further
        # along.
        if not self._for_a_cloud or not self._shows.get("camera", True):
            self._glide.setChecked(False)
            self._glide.hide()
        # AND THE PAGE MAY CARRY BOTH VIEWS, with a switch between them.
        #
        # Asked for from the window: "could the exported web viewer files get
        # a toggle to switch between the view of the shells and the sliced
        # view ... the other controls would then have to update accordingly
        # so the user can manipulate each view in a way that makes sense for
        # it". The writer, the switch and the per-view strip are built; this
        # is the question that reaches them.
        self._both_views = QCheckBox(
            "Carry a cross-section too, with a switch", self)
        self._both_views.setChecked(False)
        rows.addWidget(self._both_views, 3, 0, 1, 2)
        # NOT WHERE THERE IS NOTHING TO SWITCH BETWEEN. A page already saved
        # flat IS the cross-section, and a picture with no camera has no
        # shapes view to switch back to -- the same rule the glide above
        # follows, for the same reason.
        if not self._shows.get("camera", True):
            self._both_views.setChecked(False)
            self._both_views.hide()
        both_hint = Hint(
            "Puts BOTH pictures in the one file — the shapes as you see them "
            "here, and a flat cross-section through them — with a switch "
            "along the bottom that moves between the two.\n\n"
            "WHY IT IS WORTH THE SPACE. The two answer different questions "
            "and neither replaces the other. The shapes show you how much "
            "colour there is and where it runs out; a cut through them at one "
            "lightness shows exactly how far each one reaches in every "
            "direction at that lightness, which is genuinely hard to judge by "
            "eye from a solid you are turning around. Sending both means the "
            "person reading it can ask either question without you having to "
            "guess in advance which one they wanted.\n\n"
            "THE CONTROLS FOLLOW THE VIEW. On the shapes they can turn, tip "
            "and zoom; on the cut those disappear — a flat picture has no "
            "angle to be seen from — and the lightness controls take their "
            "place, so the cut can be moved up and down through the shapes "
            "rather than being stuck where you left it.\n\n"
            "WHAT IT COSTS: about a tenth more file. The viewer that draws "
            "the picture is the bulk of the page and travels once either way; "
            "the second view adds only its own outlines.\n\n"
            "It needs shapes with a camera — a page saved as a cross-section "
            "already IS that view, so there would be nothing to switch to, "
            "and this is simply not offered there.", self)
        both_hint.setObjectName("hint_both_views")
        rows.addWidget(both_hint, 3, 2)
        if self._both_views.isHidden():
            both_hint.hide()

        glide_hint = Hint(
            "Whether a drag ends the way a real object would. With this on, "
            "letting go of the shape leaves it turning for about a second, "
            "slowing to a stop on its own; with it off it stops the instant "
            "the finger or the mouse button lifts, which is how saved pages "
            "have always behaved.\n\n"
            "It is worth having on for a page somebody will read on a phone "
            "or a tablet. A shape that stops dead under a finger does not "
            "feel like a thing you are holding, and turning a gamut right "
            "round to look at the back of it then takes four or five separate "
            "drags instead of one flick.\n\n"
            "IT IS ONLY EVER A GENTLE ONE. A hard flick does not send it "
            "spinning: how fast it leaves is capped, and it always slows to a "
            "stop in about a second. Touching the shape stops it at once, so "
            "nobody has to wait for it.\n\n"
            "It does nothing on a saved cross-section, which is drawn flat "
            "and cannot be turned at all — so on those it is simply not "
            "there. Turn it off and the page behaves exactly as pages saved "
            "before this option existed.", self)
        glide_hint.setObjectName("hint_glide_hint")
        rows.addWidget(glide_hint, 2, 2, Qt.AlignmentFlag.AlignVCenter)

        # WHICH COLOURS IT OPENS IN, and it is a question worth asking because
        # the answer used to be "whatever this window happens to be wearing".
        # Reported of the published pages: "the viewer frames stand out
        # because they are black by default although we offer multiple
        # colorschemes" -- a page written from a dark window arrives as a
        # black rectangle in the middle of somebody's light document.
        #
        # "Follow whoever opens it" leads and is the default, because a saved
        # page is the thing most likely to be sent to somebody whose screen we
        # know nothing about. Every other colouring is still here, and the
        # reader can move through all of them in the page itself.
        self._colours = NoScrollComboBox(self)
        self._colours.addItem("Follow whoever opens it — dark or light, "
                              "their choice", "follow")
        self._colours.addItem("Dark, whatever they use", "dark")
        self._colours.addItem("Light, whatever they use", "light")
        self._colours.addItem("No background at all — for dropping into a "
                              "document", "none")
        self._colours.addItem("Neutral grey — the fairest ground to judge a "
                              "colour on", "slate")
        self._colours.addItem("Plain black and white — for printing it out",
                              "ink")
        rows.addWidget(QLabel("Colours", self), 3, 0)
        rows.addWidget(self._colours, 3, 1)
        colours_hint = Hint(
            "Which colours the page wears when somebody opens it — the paper "
            "behind the shape, the walls of the box around it and the "
            "writing. NOT ONE MEASURED COLOUR CHANGES: the shape is the same "
            "shape on every one of them.\n\n"
            "FOLLOW WHOEVER OPENS IT is the one to keep unless you have a "
            "reason not to. The page asks the machine reading it whether it "
            "is set to dark or to light and dresses itself to match, and if "
            "they switch over at dusk with the page still open it follows "
            "them. It is the answer for a page you are sending somebody, "
            "because a dark page dropped into a light document arrives as a "
            "black rectangle in the middle of it — and a light one in a dark "
            "document glares.\n\n"
            "DARK and LIGHT pin it, which is what you want when the page is "
            "going somewhere you have already seen: a slide deck that is "
            "black throughout, or a printed handout.\n\n"
            "NO BACKGROUND AT ALL leaves the shape floating on whatever the "
            "page is sitting in. That is the one for dropping a picture into "
            "a document or a forum post where the surrounding paper should "
            "show through.\n\n"
            "NEUTRAL GREY is the fairest ground to judge a colour against: a "
            "gamut on black looks brighter than it is and one on white looks "
            "duller, and halfway is neither. PLAIN BLACK AND WHITE is for "
            "printing the page or putting it on a projector, where a "
            "near-black goes to mud and a warm white goes yellow.\n\n"
            "WHAT IT NEEDS: nothing. No internet, nothing installed, and no "
            "setting on the reader's machine — a browser too old to be asked "
            "which way it is set is treated as light. And whoever opens it "
            "can still move through all six from the strip under the "
            "picture, so nothing you choose here shuts a door.",
            self, title="What colours the page opens in")
        rows.addWidget(colours_hint, 3, 2, Qt.AlignmentFlag.AlignVCenter)
        glide_hint.follow(self._glide)

        outer.addLayout(rows)

        # WHAT THE PERSON OPENING IT CAN CHANGE.
        #
        # A saved page is read by somebody who does not have this window, and
        # until now it arrived with one fixed set of buttons. Which of them
        # make sense depends entirely on where the page is going: one for a
        # printer to turn over and look at wants everything; one embedded in a
        # website beside a paragraph of text may want no strip at all.
        #
        # The four that were always there stay ticked, so a person who never
        # opens this section gets exactly the page they got before.
        self._offer: dict = {}
        # WHAT THE PERSON OPENING IT CAN CHANGE, IN GROUPS.
        #
        # This was one flat list of nine, which was the right shape for nine.
        # It is twenty now, and twenty checkboxes in a column is a dialog
        # taller than a laptop screen and a list nobody reads to the end of.
        # Grouped, the person saving a page can find the one they came for by
        # reading five headings instead of twenty labels -- and skip four
        # groups whole when they only wanted to add a zoom button.
        #
        # THE ORDER MIRRORS THE PANEL the reader gets, deliberately: whoever
        # ticks these boxes is the first person to open the page they make,
        # and a settings list that arrives in a different order from the
        # thing it configures makes them hunt twice.
        offers = [
            ("Moving the shape", [
            ("play", "Stop and start the movement", True,
             "Puts a Play and Pause button on the page.\n\n"
             "Worth keeping on for anything that moves. A shape turning by "
             "itself is what makes somebody look at it in the first place, "
             "but it is also the thing that gets in the way the moment they "
             "want to study one corner of it — and without this they can only "
             "grab it and hold it still with the mouse.\n\n"
             "On a page you saved standing still it reads Play, and pressing "
             "it sets the shape turning. Nothing ever starts moving on its "
             "own."),
            ("speed", "One speed for the movement", True,
             "A minus and a plus, so whoever opens the page can slow the "
             "movement down or speed it up.\n\n"
             "One number covers both directions, and it keeps them in the "
             "proportion you saved them in: if you set a quick turn with a "
             "slow tip under it, that is what they get, only faster or "
             "slower altogether.\n\n"
             "Turn this off and switch on a speed for each direction below "
             "if you would rather they could set the two apart."),
            ("speed_each", "A speed for each direction", False,
             "Gives left-and-right and up-and-down a speed of their own, "
             "instead of one number for both.\n\n"
             "This is what this window itself offers you, and it is worth "
             "handing on when the pairing matters — a slow tip under a "
             "quicker turn shows the dents in a surface far better than "
             "either on its own, and somebody who cannot set them apart "
             "cannot find that.\n\n"
             "It costs two more buttons in the panel. If in doubt, leave "
             "this off and keep the single speed above: most people only "
             "want it a bit slower."),
            ("sweep", "How far it swings, and whether it goes right round", False,
             "Gives each direction a minus and a plus for HOW FAR it moves, "
             "separately from how fast — which are two quite different "
             "things to watch, and until now a saved page could only ever "
             "hand over the speed.\n\n"
             "WHAT IT CHANGES. A narrow swing keeps the shape almost facing "
             "the way you pointed it, and gives just enough movement to tell "
             "a dent in the surface from a shadow on it. A wide one carries "
             "it round both edges so you can see what is hiding at the sides. "
             "The reading is in degrees, and the limits are this window's own "
             "— 15° to 180° left and right, 10° to 120° up and down — so a "
             "page cannot be set to something this window would refuse.\n\n"
             "AND ONE PRESS PAST THE WIDEST SWING sets that direction going "
             "ALL THE WAY ROUND, turning steadily in one direction instead of "
             "coming back; the reading then says “round”. That matters "
             "because it is the only way somebody reading your page can get "
             "to the full turn if you saved it swinging — and pressing the "
             "minus brings it back to a swing again. Nothing is lost either "
             "way.\n\n"
             "It costs two more buttons in each direction's row. If you are "
             "handing over a page for somebody to glance at, the single "
             "speed above is usually enough; this is for a page somebody is "
             "going to sit and study."),
            ("lr", "Turn left and right on or off", True,
             "A switch for the turning — the movement most people mean by "
             "“spin it”.\n\n"
             "Switching it off and on again brings back the turning you "
             "saved rather than a guess at one, so nothing is lost by "
             "trying it."),
            ("ud", "Tip up and down on or off", True,
             "A switch for the tipping: the shape leaning towards the "
             "viewer and away again.\n\n"
             "A little of this alongside the turning is what shows a surface "
             "is dented rather than smooth. On its own it can be unsettling "
             "to watch, which is exactly why it is worth letting somebody "
             "turn it off."),
            ]),
            ("Looking at it", [
            ("cut", "Move the cut up and down  (cross-sections only)", True,
             "Puts the same slider under a saved cross-section that this "
             "window has: it slides the cut up and down through the shapes, "
             "from the shadows to the paper white.\n\n"
             "WITHOUT IT A SAVED CUT IS FROZEN at whatever lightness you "
             "happened to be looking at, and that is a real loss — which "
             "paper reaches further into the cyans has a different answer "
             "near the white point from the one it has in the shadows, and "
             "the person you sent it to can only see the one you left it "
             "at.\n\n"
             "Every outline they can slide to is worked out here, when you "
             "save, and travels inside the page — a flat cut on its own does "
             "not carry enough to work one out. So it moves as fast as they "
             "can drag it and needs nothing from the internet, and it adds "
             "about 170 kB to a file that is already several megabytes.\n\n"
             "It only appears on a page showing a cross-section. On a page "
             "showing the 3D shape there is nothing to slide, and no slider "
             "is built."),
            ("zoom", "Zoom in and out", True,
             "A minus and a plus that bring the shape closer or take it "
             "further away.\n\n"
             "WORTH KEEPING ON, ESPECIALLY FOR A PHONE. On a computer you "
             "can zoom with the scroll wheel, so buttons only save a little "
             "trouble. On a phone or a tablet there is no wheel, and the "
             "part of the viewer that draws the shape understands one finger "
             "and nothing else — so without these buttons somebody reading "
             "your page on a phone can turn the shape and can never get any "
             "closer to it.\n\n"
             "The page now also understands a two-finger pinch, but nothing "
             "on screen says so, and a pinch is the sort of thing people try "
             "once and give up on. The buttons are the part they can see.\n\n"
             "There are limits at both ends, so nobody can zoom so far in or "
             "out that they lose the shape and cannot find it again."),
            ("move", "Move the picture about", True,
             "Four arrows that slide the picture left, right, up and down, "
             "so a corner of the shape can be brought into the middle.\n\n"
             "This is what you would do on a computer by dragging with the "
             "right-hand mouse button, or by holding Ctrl and dragging. On a "
             "phone neither of those exists — there is no second button and "
             "no Ctrl key — so these arrows are the only way, apart from the "
             "two-finger drag the page now understands.\n\n"
             "Most useful together with the zoom above: get close first, "
             "then move to the part you actually wanted. “Put the view back” "
             "returns the whole shape whenever it goes wrong."),
            ("glide", "Switch the carry-on-turning off and on", False,
             "Hands the reader a switch for the setting above — whether the "
             "shape carries on turning for a moment after they let go of it, "
             "or stops the instant they do.\n\n"
             "TWO SEPARATE QUESTIONS, and this is the second one. The tick "
             "box higher up decides how the page BEHAVES when it opens. This "
             "one decides whether the person reading it can change their "
             "mind. Leave this off and the page simply behaves the way you "
             "chose, with nothing to press.\n\n"
             "Worth handing over when you do not know what the page is being "
             "read on. It is a pleasure to use on a tablet and some people "
             "dislike it with a mouse, and there is no way to know from here "
             "which of those you are sending it to.\n\n"
             "It costs one button, and it is not built at all on a saved "
             "cross-section — a flat cut cannot be turned, so there would be "
             "nothing for the switch to do."),
            ("views", "Four fixed places to look from", True,
             "Four buttons — above, front, side and angle — that put the eye "
             "exactly square to the shape instead of wherever a drag "
             "happened to leave it.\n\n"
             "WHY IT IS MORE THAN A CONVENIENCE. Dragging is how you explore "
             "a shape and a poor way to arrive at a known position: getting "
             "the eye squarely over the top of a gamut by hand takes several "
             "goes and is never quite square. So two people looking at two "
             "of your pages are comparing two different angles without "
             "either of them realising, and a difference they see may be "
             "nothing but that. Pressing “above” on both makes the two "
             "pictures strictly comparable.\n\n"
             "“Above” is worth knowing about: it looks straight down the "
             "lightness axis, which is the same direction a cross-section is "
             "drawn in — so a shape seen from above and a cut through it can "
             "be read side by side.\n\n"
             "It only turns the eye. How far away it is and what it is "
             "pointed at stay exactly as they were, so pressing one after "
             "zooming into a corner keeps you at that corner."),
            ("reset", "Put the view back", True,
             "A reset button that returns the shape to the way the page "
             "opened.\n\n"
             "Worth keeping on. It is easy to drag a shape somewhere you did "
             "not mean to, or to zoom until nothing makes sense, and on a "
             "page that arrived by email there is no obvious way back — "
             "most people would not think to reload it.\n\n"
             "It undoes only their own turning and zooming. Nothing is "
             "closed and no figure changes."),
            ("fullscreen", "Fill the screen", True,
             "A switch that gives the picture the whole screen, with the "
             "browser’s own bars out of the way, and puts it back again.\n\n"
             "The controls go full screen with it, so there is always a "
             "visible way out; the Escape key works too.\n\n"
             "ON AN IPHONE THE BUTTON SIMPLY WILL NOT BE THERE. Safari on a "
             "phone offers full screen for video and for nothing else, and a "
             "button that is present and does nothing is worse than a "
             "missing one — the reader presses it, nothing happens, and now "
             "they doubt the whole page. The page asks the browser it is "
             "opened in and builds the button only where it works, so the "
             "same file behaves correctly everywhere. Leaving this ticked "
             "costs nothing on the devices that cannot use it."),
            ]),
            ("How each shape is drawn", [
            ("agree", "Fade where they agree, or where they differ", True,
             "Two rows of controls, one each way round, so the person "
             "reading the page can dissolve either half of the picture and "
             "look at the other.\n\n"
             "WHERE THEY AGREE fades the part every shape reaches, leaving "
             "only the places they differ. WHERE THEY DIFFER does the "
             "opposite, leaving the part they all have in common. Those are "
             "two different questions: the first is the one you ask when "
             "choosing between two papers, and the second is the one you ask "
             "when the same picture has to go out on both and you want to "
             "know which colours are safe on either.\n\n"
             "WHY IT IS WORTH HANDING OVER. Two papers drawn over each other "
             "are mostly the same paper. The part they share is the bulk of "
             "both, it is drawn twice, and it sits in front of the part where "
             "they differ — which is the only part anybody put them side by "
             "side to see. This dissolves the agreement and leaves the "
             "difference standing on its own, and it is the sort of thing a "
             "reader wants to try both ways rather than be handed one of.\n\n"
             "AT THE TOP nothing is changed at all: the picture is exactly "
             "the one you saved. Somewhere in the middle is usually the most "
             "useful — fully hidden loses all sense of how big the agreement "
             "was, while faint keeps the whole shape as context with the "
             "difference standing out of it.\n\n"
             "IF A WHOLE SHAPE DISAPPEARS as they slide it down, that is the "
             "answer and not a fault: it means that shape lies completely "
             "inside the others and disagrees with them nowhere. Sliding back "
             "up brings it in again, whole.\n\n"
             "These only appear on a page with two or more shapes on it — one "
             "on its own has nothing to agree with — and they cost the file "
             "about half a kilobyte per shape, which is one character for "
             "each measured point saying which side of the question it falls "
             "on.\n\n"
             "The fading is done to the colours themselves rather than by "
             "drawing the shape twice, which is why the top of the range is "
             "not merely close to leaving the picture alone but leaves it "
             "pixel for pixel identical.\n\n"
             "IT IS ABOUT THE SURFACES, not about volume. What is left is the "
             "piece of each boundary lying outside the others, and on two "
             "shapes that graze each other a great many boundary points fall "
             "just outside while very little volume does. The written-out "
             "figures under the picture are where the volume is answered."),
            ("opacity", "Make a shape fainter or more solid", True,
             "A minus, a percentage and a plus for every shape on the page, "
             "each one on its own.\n\n"
             "THIS IS THE CONTROL FOR THE OLDEST PROBLEM a picture of two "
             "gamuts has: the one in front hides the one behind, and no "
             "amount of turning fixes it. You choose one strength when you "
             "save the page; this lets the person reading it choose a "
             "different one for the shape they happen to care about, which "
             "is not a decision you can make for them in advance.\n\n"
             "A SEE-THROUGH SURFACE SHOWS ITS OWN FACETS at some angles — "
             "flat patches with hard edges, which look like a slice taken "
             "out of the shape. That is the drawing and not your "
             "measurement: a browser blends see-through surfaces in the "
             "order it draws them rather than by which one is nearer. "
             "Measured on one paper, it is about four times worse at a "
             "three-quarter view than from straight above, and it goes "
             "altogether when the shape is solid — so if a shape looks cut, "
             "press the plus or look at it from above.\n\n"
             "It stops short of invisible at one end and solid at the other, "
             "so nobody can fade a shape away and be left wondering whether "
             "the page failed to draw it. Hiding one outright is what the "
             "names underneath are for, and those at least say so.\n\n"
             "The little marker beside each name keeps its full strength "
             "whatever the shape does, so the key stays readable."),
            ("wires", "Draw the edges instead of the surface", True,
             "A switch per shape that changes what the surface is made of.\n\n"
             "ON A SOLID SHAPE it lays a net of fine lines over the surface. "
             "The lines follow the measured points, so they show where the "
             "measurement is dense and where the shape between two readings "
             "is the drawing’s guess rather than anything anybody measured — "
             "which is worth knowing before trusting a bulge. Turned down to "
             "faint at the same time, what is left is the cage alone, and "
             "that is the clearest way there is to show one shape sitting "
             "inside another.\n\n"
             "ON A CROSS-SECTION it fills the outline in or empties it. Two "
             "filled cuts lying over each other are hard to read however "
             "faint they are; two outlines never are.\n\n"
             "Nothing is added to or taken from the measurement either way. "
             "Only the colouring-in changes."),
            ("grey", "Take the colour out of a shape", True,
             "A switch per shape that draws it in grey instead of its own "
             "colours, and back again.\n\n"
             "The usual reason to want it: two shapes both painted in the "
             "colours they hold make a picture nobody can untangle, and "
             "putting one of them in grey makes the other obvious "
             "immediately.\n\n"
             "IT KEEPS THE LIGHT AND DARK EXACTLY. Each colour becomes its "
             "own true brightness — worked out the way the screen itself "
             "defines brightness, not by averaging the three numbers, which "
             "would make a pure blue and a pure yellow the same grey when "
             "one is nearly black to look at and the other nearly white. So "
             "the shape stays every bit as readable and simply stops "
             "competing for attention.\n\n"
             "SOME SHAPES ARE NOT OFFERED IT, and that is deliberate. Where "
             "the colour IS the measurement — the comparison shape that is "
             "red for what a paper cannot reach, and a chart’s out-of-reach "
             "patches — a greyed picture would still carry a name promising "
             "two things while showing one. Those keep their colours and the "
             "switch is not built for them at all."),
            ]),
            ("What the picture shows", [
            ("notes", "Put the numbers away", True,
             "Lets whoever opens the page hide the written-out figures "
             "underneath it, and bring them back.\n\n"
             "Only appears if you asked for the numbers at the top of this "
             "window — there is nothing to hide otherwise.\n\n"
             "This matters most on a phone, where those figures are easily "
             "taller than the whole screen: somebody who has read them once "
             "can put them away and give the picture the entire window. "
             "Nothing is deleted and nothing is recalculated — the same "
             "numbers come straight back."),
            ("grid", "Show or hide the box and its grid", False,
             "Lets whoever opens the page take away the ruled box around the "
             "shape, and put it back.\n\n"
             "The walls are what let somebody judge where a bulge actually "
             "sits — without them a shape floats with nothing to measure it "
             "against. But they are also clutter if the picture is going "
             "into a document that explains itself, and a bare shape on a "
             "plain background makes a much cleaner screenshot.\n\n"
             "Letting them choose costs nothing: the measurement is the same "
             "either way."),
            ("labels", "Show or hide the lettering", False,
             "Lets them take away the numbers and the axis names.\n\n"
             "Useful in two opposite situations. When the page is going "
             "beside text that already says what the axes are, the lettering "
             "is noise. And when somebody is going to take a screenshot for "
             "a forum, small text that cannot quite be read is worse than no "
             "text at all.\n\n"
             "The shape and its colours are untouched — only the writing "
             "around the edge goes."),
            ("key", "Show or hide the names underneath", False,
             "Lets them hide the list of names under the picture.\n\n"
             "Those names are also switches — clicking one hides that shape, "
             "double-clicking shows it on its own — so hiding the list takes "
             "that away too. Best kept for a page with a single shape on it, "
             "where the list says nothing they cannot already see."),
            ]),
            ("The page itself", [
            ("appearance", "Let them change the page colours", False,
             "Puts a button on the page that moves through five ways of "
             "colouring it, so whoever opens it can match it to whatever "
             "they are putting it in.\n\n"
             "NOT ONE MEASURED COLOUR CHANGES. Only the paper behind the "
             "shape, the walls of the box around it, the grid on them and "
             "the writing. A gamut is the same gamut on every one of "
             "them.\n\n"
             "dark and light are the two this window itself uses. none takes "
             "the background away altogether, so the shape floats on "
             "whatever the page is sitting in — that is the one for dropping "
             "a picture into a document, a slide or a forum post. slate is a "
             "neutral grey, which is the fairest ground to judge a colour "
             "against: a gamut on black looks brighter than it really is and "
             "one on white looks duller. ink is plain black and white, for "
             "printing the page or putting it on a projector, where a "
             "near-black goes to mud and a warm white goes yellow.\n\n"
             "You still choose which one it OPENS as, under This window; "
             "this only decides whether they can change it afterwards. It "
             "adds the other sets of page colours to the file, which is 838 "
             "bytes — nothing beside a page that is already several "
             "megabytes."),
            ("picture", "Save it as a picture file", True,
             "A button that writes what is on screen — at that exact angle, "
             "with whatever they have faded or greyed — into an ordinary "
             "PNG in their downloads.\n\n"
             "This is what somebody needs when your page is the evidence and "
             "their report is where it has to go. Without it they are taking "
             "a screenshot, which comes out at whatever their screen "
             "happens to be; this comes out at twice the size the picture is "
             "drawn, which is enough to put in a document and still read.\n\n"
             "Nothing is sent anywhere to do it. The picture is made by "
             "their own browser out of the numbers already inside the page, "
             "with no internet involved at any point.\n\n"
             "A page with two pictures side by side saves two files, "
             "numbered, rather than one file holding half of what they can "
             "see."),
            ("remember", "Remember what they chose", True,
             "The page keeps whatever the reader set — paused, faster, "
             "tipping switched off, one shape faded, the numbers put away — "
             "and opens that way next time they come back to it.\n\n"
             "This matters most when somebody has several of your pages to "
             "look through: without it, every one of them has to be paused "
             "again by hand, which is the sort of small annoyance that stops "
             "people looking properly.\n\n"
             "It is kept by their own browser, for that page alone. Nothing "
             "is sent anywhere and nothing about them is stored."),
            ]),
        ]

        strip = QCheckBox("Give them controls at all", self)
        strip.setChecked(True)
        self._strip = strip
        rows.addWidget(strip, 3, 0, 1, 2)
        if not self._for_a_cloud:
            strip.setChecked(False)
            strip.hide()
        strip_hint = Hint(
            "Whether the page carries the row of controls along the bottom "
            "at all.\n\n"
            "Leave it on for anything you are sending to a person. Turn it "
            "off when the page is going to sit inside a website beside your "
            "own text, where a row of buttons you did not design would look "
            "out of place — the shape can still be dragged, zoomed and its "
            "names clicked, exactly as before. Only the buttons go.", self)
        strip_hint.setObjectName("hint_strip_hint")
        rows.addWidget(strip_hint, 3, 2, Qt.AlignmentFlag.AlignVCenter)
        strip_hint.follow(strip)

        # ONE BOX PER GROUP, ALL OF THEM INSIDE A SCROLL AREA.
        #
        # Twenty checkboxes in a column is about 640 pixels before the two
        # questions above them, the note below and the buttons -- a dialog
        # comfortably taller than the usable height of a 13-inch laptop, and
        # a dialog taller than the screen is one whose Save button cannot be
        # reached. Given a ceiling and a scrollbar it grows as far as the
        # screen allows and then stops, on any machine.
        #
        # The ceiling is worked out from the screen this window is actually
        # on rather than fixed, because the two ends of that range are a
        # 768-pixel-high laptop and a 27-inch desktop, and one number cannot
        # be right for both.
        held = QWidget(self)
        stack = QVBoxLayout(held)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(10)
        self._offer_groups: list = []
        for title, items in offers:
            box = QGroupBox(title, held)
            grid = QGridLayout(box)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(6)
            grid.setColumnStretch(0, 1)
            at = 0
            for name, label, default, why in items:
                need = self.NEEDS.get(name)
                if need is not None and shows is not None \
                        and not self._shows.get(need, False):
                    continue
                i = at
                at += 1
                check = QCheckBox(label, box)
                check.setChecked(default)
                self._offer[name] = check
                grid.addWidget(check, i, 0)
                hint = Hint(why, box)
                hint.setObjectName(f"hint_offer_{name}")
                grid.addWidget(hint, i, 1, Qt.AlignmentFlag.AlignVCenter)
                hint.follow(check)
            if not at:
                # A GROUP WITH NOTHING LEFT IN IT is a heading over a gap.
                box.deleteLater()
                continue
            stack.addWidget(box)
            self._offer_groups.append(box)
            strip.toggled.connect(box.setEnabled)
        stack.addStretch(1)

        area = FadingScrollArea(self)
        area.setWidget(held)
        if not self._for_a_cloud:
            # AND THE WHOLE LIST GOES WITH IT. Twenty-two switches about
            # turning, hiding families and fading a comparison, offered over a
            # line chart with two lines on it, would be a page of promises the
            # file cannot keep.
            #
            # AFTER setWidget, AND THAT IS THE WHOLE OF THE BUG THIS FIXES.
            # Hiding it first looks right and is undone one line later:
            # QScrollArea.setWidget SHOWS the widget it is handed. So the
            # intent was written, defeated by ordering, and never checked --
            # measured on the dialog for a line graph, 26 of the 27 switches
            # a cloud gets were still being offered, over a page that draws
            # no controls at all.
            held.hide()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # A SMALLER DEFAULT, AND STILL NO CEILING ON WHAT THE USER WANTS.
        #
        # This list has grown to twenty-two switches in five groups, and at
        # its natural size the dialog opened taller than most windows anybody
        # keeps open -- 1,138 points on a 1440-point screen, which is a wall of
        # tick boxes before you have decided anything. Reported as "pretty
        # high ... maybe not strictly limited, a smaller default".
        #
        # THE CEILING IS ON THE WINDOW'S OPENING SIZE, NOT ON THE LIST. It was
        # written the other way round first -- a maximum height on the
        # scrolling area alone -- and that is wrong for a reason that only
        # showed up on Windows: capping the one part that scrolls does not cap
        # the window, because everything ELSE in the dialog (two questions,
        # three tick boxes, five hint buttons, the note and the buttons) is
        # fixed, and how tall that comes out depends on the platform's fonts
        # and margins. Measured: the same dialog that fits comfortably on
        # macOS opened **874 points tall on an 800-point screen** on Windows,
        # with the list already at its cap. The Save button was off the bottom
        # of the screen -- the exact fault the cap was added to prevent.
        #
        # Bounding the window instead is right on every platform because it
        # measures the thing that actually has to fit. The list keeps only a
        # floor, so it can give up height when the window is short, and there
        # is NO maximum on it at all -- so dragging the dialog taller still
        # hands the list every pixel of it, which is what was promised.
        # The fade along the bottom edge is what says there is more below --
        # a list that simply stops at a hard line reads as a list that ends.
        area.setMinimumHeight(150)
        self._area = area
        outer.addWidget(area, 1)
        strip.toggled.connect(area.setEnabled)
        # WHAT IT IS, AND HOW TO GET IT TO SOMEBODY. The second half was
        # missing, and somebody reading this dialog asked the obvious question
        # it did not answer: how do I put this in a forum post? Kept to two
        # short lines -- the long version is behind the ⓘ beside "The file",
        # where it costs no room that a control could have used.
        note = WrappedLabel(
            "The page opens in any browser and keeps everything you can do "
            "here: turning it, zooming in, and reading a name by pointing at "
            "a shape.\n"
            "It is one file, so you can email it, put it on a memory stick, "
            "or upload it and send the link. For a forum post, send a link "
            "and put a picture in the post itself — see the ⓘ above.", self,
            hug=True)
        note.setObjectName("hint")
        outer.addWidget(note, 0)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Choose where to save…", self)
        save.clicked.connect(self.accept)
        save.setDefault(True)
        buttons.addWidget(save)
        outer.addLayout(buttons)

    #: The most of the screen's usable height this dialog may open at. Not the
    #: most it may BE -- the user can drag it as tall as they like. Three
    #: quarters leaves room for the window behind it to still be recognisable
    #: as a window, and it is comfortably under the point where a title bar
    #: and a dock start eating the buttons.
    OPENS_AT_MOST = 0.75

    def fit_within(self, room: int) -> None:
        """Open no taller than *room* allows, whatever the platform's metrics.

        Separate from showEvent so that it can be handed a screen height and
        checked, rather than only ever being exercised against whatever screen
        the machine running the tests happens to have. The Windows runner
        reports 800 and this machine reports 1440; the fault that made this
        necessary was visible only on the first.
        """
        ceiling = max(360, int(room * self.OPENS_AT_MOST))
        if self.height() > ceiling:
            self.resize(self.width(), ceiling)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # ONCE, ON THE WAY UP. Doing it on every show would undo a size the
        # user had chosen by dragging, which is the opposite of the point.
        if getattr(self, "_fitted", False):
            return
        self._fitted = True
        # AND ON THE NEXT TURN OF THE LOOP, NOT NOW. Resizing inside showEvent
        # happens before the layout has been activated, so the layout runs
        # afterwards and puts the height straight back: measured at 676 points
        # on the 800-point screen this was meant to fit, from a call that had
        # already asked for 600. One turn later the dialog is laid out, its
        # height is real, and a resize sticks.
        QTimer.singleShot(0, self._fit_to_this_screen)

    def _fit_to_this_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        self.fit_within(screen.availableGeometry().height() if screen else 900)

    def choices(self) -> dict:
        return {"carry_viewer": bool(self._carry.currentData()),
                "numbers": self._numbers.isChecked(),
                "controls": self._strip.isChecked(),
                "colours": self._colours.currentData(),
                # NOT INSIDE "offer", THOUGH IT SITS BESIDE ONE. The offers say
                # which CONTROLS the reader is handed; this says how the page
                # BEHAVES before they touch anything, and it applies just as
                # much to a page saved with no controls at all.
                "glide": self._glide.isChecked(),
                # WHETHER THE PAGE CARRIES BOTH PICTURES. Like glide, this is
                # about what the page IS rather than which controls it hands
                # out, so it sits beside the offers rather than inside them.
                "both_views": (self._both_views.isChecked()
                               and not self._both_views.isHidden()),
                # EVERY SWITCH ANSWERED, INCLUDING THE ONES NOT SHOWN. A
                # name missing from this dict falls to whatever default the
                # writer has, and for most of them that default is "offer it"
                # -- so leaving a switch out of the dialog would have HANDED
                # IT OUT instead of withholding it.
                "offer": {**{name: False for name in self.NEEDS},
                          **{name: box.isChecked()
                             for name, box in self._offer.items()}}}


def family_report(lab_a, lab_b, spans: str, *, of: str = "profiles",
                  over_time: bool = True):
    """Which colour families moved, as (the lines to show, the footnote).

    WINDOW-FREE AND SHARED BY EVERY PLACE THAT SHOWS IT: the timeline, the
    main window's measurement pair, the main window's profile pair, the saved
    web page and the exported table. It was a method on the timeline window
    for one release, which is why the main window -- where somebody with two
    .ti3 files of one chart actually works -- had no report at all.

    *of* says what the two things ARE, because what the number MEANS is not
    the same for both, and getting that wrong is worse than leaving it out.

      "profiles"     -- two characterisations. How far apart the PROFILES are
                        is not how far the device drifted: each is one day's
                        measurements of one chart, so chart fade and any
                        change in how they were built are inside the number.
      "measurements" -- two readings of one chart, which is the verification
                        case: print the chart again later, on the same paper
                        and the same printer, and read it.

    AND THE MEASUREMENT CASE HAS TWO QUITE DIFFERENT SHAPES, which an earlier
    version of this ran together and got wrong. Reading the SAME SHEET twice
    shows the sheet ageing and the instrument's own repeatability, and nothing
    else. PRINTING IT AGAIN puts the whole process between the two readings --
    the printer, the ink batch, the paper batch, the day's conditions -- which
    is usually the very thing somebody wants to know, and is not "the chart
    fading". The note says both rather than assuming which one happened,
    because the files cannot tell us.

    *over_time* says whether these are ONE THING AT TWO TIMES or TWO DIFFERENT
    THINGS, and it changes the verbs, because "moved" is a claim about time.

    The same arithmetic answers both, and the second is worth as much as the
    first: two measurements of one chart printed on two DIFFERENT PAPERS on
    the same day say which paper holds the blues and which holds the skin
    tones -- a buying decision, not a drift report. Two printers, same paper,
    same chart, says whether two machines agree. Nothing "moved" in either
    case, and saying so would be false.

    IT CANNOT BE INFERRED FROM THE FILES. Two .ti3 of one chart could be one
    printer months apart or two papers on one afternoon, and the file names
    are not evidence. So the caller says which it is; it is never guessed.

    Returns None when there is nothing honest to say, which the caller must
    treat as "show nothing" rather than "show an empty box".
    """
    import gamutview

    try:
        rows = gamutview.family_drift(lab_a, lab_b)
    except (ValueError, TypeError):
        return None

    lines = [r.sentence for r in rows if r.patches]
    if not lines:
        return None
    heading = ("which colour families moved" if over_time
               else "how the two compare, family by family")
    shown = f"{spans} — {heading}:\n" + "\n".join(lines)

    borderline = sum(r.near_boundary for r in rows)
    total = sum(r.patches for r in rows)
    where = ", ".join(f"{name} around {centre:.0f}°"
                      for name, centre in gamutview.HUE_FAMILIES)
    thing = "colours" if of == "profiles" else "patches"
    if not over_time:
        means = (
            "These are two different things measured, not one thing at two "
            "times — so nothing here has \"drifted\". Each line says how the "
            "second differs from the first in that family, which is what you "
            "want when you are choosing between two papers, or asking whether "
            "two printers agree. For that comparison to mean anything both "
            "must be the SAME CHART, measured the same way.")
    else:
        means = (
                "These are two profiles, so this is how far apart the two "
            "DESCRIPTIONS are — not how far the printer moved. Each profile "
            "is one day's measurements of one chart, so a faded chart or a "
            "change in how they were built is inside these numbers too."
            if of == "profiles" else
            "These are two readings of the same chart. If the second was "
            "PRINTED again rather than only measured again, then everything "
            "between the two prints is in these numbers — the printer, the "
            "ink batch, the paper batch and the conditions on the day — "
            "which is usually exactly what you wanted to find out. If "
            "instead it is the same sheet read twice, what you are seeing is "
            "the sheet ageing and the instrument's "
            "own repeatability.")
    note = (
        f"{means} "
        f"Where one family stops and the next begins is a line this window "
        f"draws, not one that exists in nature. The families are centred on "
        f"{where} of hue, and each one reaches half way to its neighbours. "
        f"Anything less colourful than chroma "
        f"{gamutview.NEUTRAL_CHROMA:.0f} is called a grey instead, because "
        f"below that a colour's hue is mostly noise and would put it in a "
        f"family at random.")
    if borderline:
        note += (
            f" Of these {total} {thing}, {borderline} sit within "
            f"{gamutview.BOUNDARY_DEGREES:.0f}° of one of those lines and "
            f"could honestly have been counted either side of it.")
    return shown, note


class TimelineDialog(QDialog):
    """One device, several profiles of it, and how far it has moved.

    TWO QUESTIONS, ONE WINDOW. The window around this holds at most two files
    and compares their SHAPES: how much colour each holds, how much they
    share, which reaches further in which hues. Eighteen places in it depend
    on there being one or two, and every one of them is right to. This asks a
    different question — has one device moved, and how fast — of as many
    profiles as somebody has. A list and a graph, not a gamut.

    THIS USED TO BE A SEPARATE WINDOW, and that was the wrong answer. Nothing
    told a reader it existed, and a second window is a second place to lose
    what you were doing. Given *hosted*, the same object builds itself as a
    PANEL for the main window's left column instead — stacked for its width,
    handing its picture to the big view beside it — so the two questions live
    together and the reader is never asked which window they should have
    opened. The dialog form is still what a saved page and the tests use.

    What keeps the two answers apart is now the section they sit in and the
    line above the big view saying whose picture is being shown, rather than
    a window boundary.
    """

    #: How finely each profile is sampled, per channel. The same grid the pair
    #: comparison uses, because there is nothing to gain by coarsening it:
    #: measured, ten comparisons take under a hundredth of a second.
    GRID = 9

    def __init__(self, parent, appearance: str = "dark",
                 preview: bool = True, hosted: bool = False) -> None:
        """*preview* False builds the window without its graph view.

        *hosted* True builds the same thing as a PANEL for the main window's
        left column instead of a window of its own — asked for in as many
        words: "i would like to load the profiles in the main window directly
        with the ability to close individual ones or all, then the options i
        can choose in what is at the moment still in its own window", and
        again after seeing it: "clicking follow the device over time still
        opens the window with the same name instead of giving me all those
        options in the main window".

        WHY THE SAME CLASS RATHER THAN A SECOND PANEL. Everything here — the
        run, the ordering, the verdict, the family report, the threshold, the
        saved page and the table — is one body of behaviour, and this project
        has been bitten three times by the same thing written in two places:
        the readout list that existed in three copies, so the report survived
        "Close them all" and was missing from every saved page. A hosted panel
        that re-implemented any of it would be the fourth.

        WHAT HOSTING CHANGES IS THE SHAPE, NOT THE WORK: the rows stack
        instead of running across, because the column is 366 px wide and this
        window was 940; there is no graph view of its own, because the point
        of the move is to use the big one; and the picture is handed to the
        host to draw.

        A REAL CAPABILITY, not a test hatch, though the tests are what needed
        it first. Everything this window computes -- the run, the verdict, the
        table, the saved page -- is worked out without drawing anything, so a
        caller that only wants the file has no use for a browser engine.

        And that engine is not free to make. This project already learned, and
        wrote down, that constructing a QWebEngineView inside pytest aborts
        the whole run; it survives on macOS and killed the Windows build here,
        stopping the suite dead at 32% with no summary. So the checks build
        the window without one, and the graph is proved by the driver scripts
        that run the real application.
        """
        super().__init__(parent)
        self._hosted = bool(hosted)
        self._host = parent if self._hosted else None
        if self._hosted:
            # A QDialOG IS A WIDGET FIRST. Told it is a plain one, it draws
            # inline in whatever layout it is put into, with no title bar and
            # no window of its own -- so the panel and the window really are
            # the same object rather than two that have to be kept in step.
            self.setWindowFlags(Qt.WindowType.Widget)
            preview = False
        self._preview = preview
        self.setWindowTitle("Follow one device over time")
        self.setModal(False)          # so files can be dragged in from Finder
        self._appearance = appearance
        self._paths: list = []
        self._run = None
        #: Shapes already built, by file and the time it was written.
        self._shell_cache: dict = {}
        if not self._hosted:
            self.resize(940, 720)
            # NOT WHEN IT IS A PANEL. A window's least size is a promise about
            # a window; carried into the column it is a 560 px floor inside a
            # 366 px space, and the whole column is dragged out to fit it.
            # Measured on the first drive: the group came out 596 px wide and
            # every label in it was cut -- "coloured by" needing 95 px in 73.
            self.setMinimumSize(560, 460)
        self.setAcceptDrops(True)

        outer = QVBoxLayout(self)
        # NO MARGINS OF ITS OWN INSIDE THE COLUMN. The group it sits in
        # already has its padding, and a second set inside that reads as the
        # panel being indented from everything above it.
        outer.setContentsMargins(0, 0, 0, 0) if self._hosted else \
            outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(8 if self._hosted else 10)

        head = QLabel("Open the profiles you have of one device — a scanner, "
                      "a printer, a screen — made on different days.", self)
        head.setWordWrap(True)
        row = QHBoxLayout()
        # ONE EXPLANATION, NOT TWO. Hosted, the group this panel sits in
        # already carries a sentence saying what it is for and an ⓘ with the
        # long answer. Both together put two paragraphs and two icons within
        # sixty pixels of each other, which is what "two tooltip icons next to
        # some options" looks like from the outside.
        row.setEnabled(True)
        row.setSpacing(8)
        row.addWidget(head, 1)
        row.addWidget(Hint(
            "WHAT THIS IS FOR. You profiled a device, and then months or years "
            "later you profiled it again. This asks whether it has moved, by "
            "how much, and whether it moved steadily or all at once.\n\n"
            "WHAT TO OPEN. Two or more ICC profiles (.icc or .icm) of the SAME "
            "device. They have to be the same kind — all of a scanner, or all "
            "of one printer on one paper. Profiles of two different devices "
            "cannot be followed over time, because there is no \"over time\" "
            "between them.\n\n"
            "HOW THEY ARE ORDERED. By the date inside each profile, when every "
            "one of them carries a usable date. If any does not, the list "
            "keeps the order you added them in and says so — sorting some by "
            "date and guessing at the rest would look authoritative and be "
            "partly invented. Drag a row to put it where you want it.\n\n"
            "THE TWO LINES. One shows how far the device has moved ALTOGETHER "
            "since the first profile. The other shows how far it moved SINCE "
            "THE ONE BEFORE. They answer different questions and they often "
            "disagree: five steps of half a ΔE each look like nothing "
            "happening, and add up to a difference anybody can see.\n\n"
            "WHAT IT CANNOT TELL YOU, and it matters here more than anywhere "
            "else in this application. Each profile records ONE day's "
            "measurements of ONE chart. If your charts faded between the "
            "profiles, or you changed how you built them, that is inside these "
            "numbers too. A line that climbs steadily is just as consistent "
            "with charts ageing as with a device drifting, and no arithmetic "
            "can separate them. To measure the device alone you need a chart "
            "you trust not to have changed.",
            self, title="Following a device over time"), 0,
            Qt.AlignmentFlag.AlignTop)
        if self._hosted:
            for i in reversed(range(row.count())):
                widget = row.itemAt(i).widget()
                if widget is not None:
                    widget.setParent(None)
        else:
            outer.addLayout(row)

        self._list = QListWidget(self)
        # AND IT NEVER SCROLLS SIDEWAYS. A settings column is read top to
        # bottom; a strip with arrows at each end, to reach the rest of a
        # file name, is not something anybody should be asked to operate.
        # The rows elide instead -- see ElidingLabel -- and this is the
        # backstop that makes that the ONLY answer: with the bar switched
        # off, a row too wide is a fault that shows rather than a scrollbar
        # that hides it.
        self._list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # AS TALL AS THE RUN, UP TO A POINT. A fixed 150 px is right in a
        # window with room to spare and wrong in a column: four profiles left
        # sixty pixels of empty list under them, in the one place where
        # height is the scarce thing. Six rows is where it stops and scrolls,
        # which is more profiles than most people have of one device.
        self._list.setMaximumHeight(150)
        if self._hosted:
            self._list.setMinimumHeight(52)
        self._list.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove)
        self._list.setToolTip(
            "Every profile in this run, oldest first, with the date inside "
            "each one.\n\n"
            "TO REORDER: drag a row. That is only worth doing when the "
            "profiles carry no usable date and the list has kept the order "
            "you added them in — with dates, they are already in the right "
            "order and moving one would tell the graph a time that is not "
            "true.\n\n"
            "TO REMOVE ONE: pick it and press the Delete key, or use Remove "
            "the selected one below. The file itself is never touched.\n\n"
            "A row saying \u2014 could not be read is a file this cannot "
            "open: not an ICC profile, or one of a different kind of device "
            "from the rest. It is kept in the list, and left out of the "
            "graph, so it is obvious which one is the problem.")
        self._list.model().rowsMoved.connect(self._reordered)
        # THE KEY EVERYBODY TRIES FIRST. The button below does the same thing
        # and says so; this is for the hand that is already on the list.
        _gone = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self._list)
        _gone.setContext(Qt.ShortcutContext.WidgetShortcut)
        _gone.activated.connect(self._on_remove)
        _gone2 = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._list)
        _gone2.setContext(Qt.ShortcutContext.WidgetShortcut)
        _gone2.activated.connect(self._on_remove)
        outer.addWidget(self._list)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        add = QPushButton("Add profiles…", self)
        add.setToolTip("Choose one or more ICC profiles of the same device.")
        add.clicked.connect(self._on_add)
        # KEPT AS AN OBJECT, NEVER SHOWN. Every row now carries its own ×,
        # which is the whole of what this did; it stays here unparented so
        # that the settings, the tests and the panel audits that name it keep
        # working, and so that nothing has to guess what happened to it.
        self._remove_btn = QPushButton("Remove the selected one", self)
        self._remove_btn.setVisible(False)
        self._remove_btn.setObjectName("secondary")
        self._remove_btn.setToolTip(
            "Takes the profile you have picked in the list above out of this "
            "run.\n\n"
            "WHAT IT IS FOR: one profile in a run is often not comparable "
            "with the rest — it was made of a different paper, or with a "
            "chart you no longer trust — and a single odd profile bends every "
            "line in the graph. Take it out and the rest still make sense.\n\n"
            "IT ONLY CHANGES THIS LIST. The file itself is untouched and "
            "stays exactly where it is on your disk; add it again whenever "
            "you like.\n\n"
            "Pick a row in the list first — until you do, there is nothing "
            "for this to remove.")
        self._remove_btn.clicked.connect(self._on_remove)
        self._clear_btn = QPushButton("Remove them all", self)
        self._clear_btn.setObjectName("secondary")
        self._clear_btn.setToolTip(
            "Empties this run completely: every profile in the list above, "
            "the graph, and everything written under it.\n\n"
            "WHAT IT IS FOR: starting a different device. A run is one "
            "printer, scanner or screen followed through time, so the way to "
            "look at a second device is to clear this one and add its "
            "profiles.\n\n"
            "THE BIG VIEW GOES BACK to whatever else you have open — the "
            "files in What you are looking at, or the empty-window text if "
            "there are none.\n\n"
            "NO FILE IS DELETED. This forgets them; it does not touch your "
            "disk.")
        self._clear_btn.clicked.connect(self._on_clear)
        for b in (add, self._clear_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        # NAMED FOR WHAT IT SAVES, because in the column it is no longer
        # alone: the window's own "Save this view as a web page…" is eight
        # inches below it, and two buttons with the same words meaning two
        # different files is the kind of thing somebody discovers by sending
        # the wrong one to a customer.
        self._save_btn = QPushButton(
            "Save this run as a web page…" if hosted
            else "Save this as a web page…", self)
        # SECONDARY, like every other export in this application. Adding
        # profiles is the one thing this window is for until there are some,
        # so it keeps the accent; two accent buttons side by side is two
        # things claiming to be the main one.
        self._save_btn.setObjectName("secondary")
        self._save_btn.setToolTip(
            "One file that opens in any browser, with the graph in it. "
            "Nothing needs installing to read it.")
        self._save_btn.clicked.connect(self._on_save)
        self._table_btn = QPushButton(
            "Save the run's numbers as a table…" if hosted
            else "Save the numbers as a table…", self)
        self._table_btn.setObjectName("secondary")
        self._table_btn.setToolTip(
            "Every step as a row, for a spreadsheet — with what the numbers "
            "do and do not mean written beside them.")
        self._table_btn.clicked.connect(self._on_table)
        buttons.addWidget(self._table_btn)
        # ONE SAVE-AS-A-WEB-PAGE BUTTON IN THE WINDOW, NOT TWO. Hosted, the
        # window's own "Save this view as a web page…" saves whatever is on
        # screen -- and while a run is showing, that IS this panel's picture.
        # Two buttons with the same words and different files is how somebody
        # sends the wrong one; and this one, until now, could not offer the
        # reader any controls at all.
        if self._hosted:
            self._save_btn.hide()
        else:
            buttons.addWidget(self._save_btn)
        if self._hosted:
            # THE TWO REMOVALS SHARE A LINE, and only those two. Four buttons
            # each on their own line came to 160 px of an 827 px panel --
            # nearly a fifth of it spent on things a reader uses once -- and
            # the two that belong together were the two furthest apart in
            # meaning from the one above them. Add is the accent and keeps its
            # own line; the table export keeps its own because its name is the
            # longest thing here.
            self._stack(buttons)
        outer.addLayout(buttons)

        # --- which picture, and of which pair ---------------------------------
        #
        # WHY THIS IS A CHOOSER AND NOT A SECOND WINDOW. The line answers WHEN
        # a device moved and how fast; the cloud answers WHERE in colour it
        # moved. They are two views of one run, and a reader who has to open a
        # second window to get from one to the other reads them as two
        # results. Asked for twice by Basti, the second time: "if i selected
        # multiple profiles, have them in the trend view, can i then choose
        # two of them for the heatmap comparison view?"
        #
        # ONE ENTRY PER STEP, PLUS THE WHOLE RUN, because a step is the unit
        # the rest of this window already works in -- it is what both lines
        # are drawn from and what the table has a row for. Naming the pair in
        # the entry is what stops the picture being anonymous once it is on
        # screen or saved.
        picture_row = QHBoxLayout()
        picture_row.setSpacing(8)
        picture_label = self._picture_label = QLabel("Show me", self)
        self._picture_of = NoScrollComboBox(self)
        self._picture_of.setToolTip(
            "Which of the two pictures to show.\n\n"
            "WHEN it moved is the graph: two lines against the dates, which "
            "says how fast the device is drifting and whether it is creeping "
            "steadily or moved all at once.\n\n"
            "WHERE it moved is a cloud of colour: every colour drawn where "
            "the earlier profile puts it and painted by how far the later one "
            "sends it instead. That is the question the graph cannot answer, "
            "and the two want opposite actions — a device that has drifted "
            "evenly everywhere is a calibration job, one that has moved only "
            "in the deep blues is a different problem.")
        self._picture_of.activated.connect(lambda _i: self._draw())
        picture_row.addWidget(picture_label, 0)
        picture_row.addWidget(self._picture_of, 1)
        self._coloured_label = QLabel("coloured by", self)
        picture_row.addWidget(self._coloured_label, 0)
        # WHICH QUESTION THE COLOURS ANSWER. "How far" is the first thing
        # anybody wants and stays the default; the three named directions are
        # the second thing, and they are what ΔE cannot say -- a printer going
        # lighter and one going darker by the same amount give an identical
        # number and an identical cloud, and want different cures.
        self._coloured_by = NoScrollComboBox(self)
        self._coloured_by.addItem("how far it moved", None)
        for _key, (_asks, _less, _more, _col) in DIRECTIONS.items():
            self._coloured_by.addItem(_asks, _key)
        # THE COLOUR IT IS HEADING FOR, which is the question people ask out
        # loud. "How far" is a distance with no direction; the three axes give
        # a direction in numbers -- lighter, redder, warmer -- and neither
        # says the thing somebody actually reports, which is "my greys have
        # gone warm" or "the blues are heading for the magentas".
        self._coloured_by.addItem("the colour it is heading for", "toward")
        self._coloured_by.setToolTip(
            "What the colours in the cloud stand for.\n\n"
            "THE COLOUR IT IS HEADING FOR paints every dot in the family it "
            "is moving toward — the blues that are on their way to the "
            "magentas come out magenta, wherever they sit in the picture. It "
            "is the one that answers the question people ask out loud: not "
            "\"how far\" and not \"how much redder\", but \"what are my "
            "greys going to\".\n\n"
            "WHAT IT NEEDS: nothing you have not already got. Any two files "
            "this box can compare can be drawn this way.\n\n"
            "A DOT THAT HAS BARELY MOVED IS DRAWN GREY AND SAID TO BE HEADING "
            "NOWHERE, and that is deliberate. Below about ΔE 1 the direction "
            "of a movement is mostly the instrument — a hand-held "
            "spectrophotometer repeats to about ΔE 0.1 on white and two "
            "different ones agree to about 0.4 — so painting those dots a "
            "confident colour would make a printer that has not moved look "
            "like it was marching somewhere. They are kept in the picture, "
            "quietly, because leaving them out would put holes in the cloud "
            "and invite the reading that something is missing there.\n\n"
            "GREYS ARE HEADING NOWHERE TOO, however far they moved: a colour "
            "with almost no chroma has no hue worth naming, so the direction "
            "it set off in is noise even when the distance is real. The "
            "written lines below still tell you what happened to them.\n\n"
            "HOW FAR IT MOVED is the distance, in ΔE2000, and it is the "
            "question to ask first. It cannot tell you which way, because a "
            "distance has no direction: a printer that has gone lighter and "
            "one that has gone darker by the same amount give exactly the "
            "same number and exactly the same picture.\n\n"
            "THE OTHER THREE ask which way, one question at a time — has it "
            "got lighter or darker, redder or greener, warmer or cooler. The "
            "scale runs both ways from no change in the middle, so the two "
            "ends are opposite directions rather than more and less of one "
            "thing.\n\n"
            "The colours of the dots are deliberately NOT red and green or "
            "blue and yellow: in a picture whose subject is colour, painting "
            "\"went redder\" in red invites you to read a dot's colour as the "
            "colour it stands for. One teal-to-orange scale for all three "
            "means the key is learned once and cannot be mistaken for the "
            "thing it describes.")
        self._coloured_by_words = self._coloured_by.toolTip()
        self._coloured_by.activated.connect(lambda _i: self._draw())
        self._coloured_by.activated.connect(
            lambda _i: self._show_only_what_applies())
        picture_row.addWidget(self._coloured_by, 0)
        self._picture_hint = Hint(
            "TWO AT A TIME, AND ONLY TWO, and it is worth saying why rather "
            "than leaving you to wonder.\n\n"
            "Every dot in the cloud is painted by how far apart two profiles "
            "put that one colour. A third profile would need a second colour "
            "on the same dot, and there is nowhere to put it — so a cloud of "
            "three would have to either hide something or invent something.\n\n"
            "That is not really a limitation, because a run is made of steps "
            "and each step IS a pair. Pick the step you want to look at and "
            "you are asking exactly the question the graph raised: it went up "
            "sharply between these two, so where did it go?\n\n"
            "THE WHOLE RUN, first to last, is offered as well. It answers a "
            "different question — not what happened in any one year, but "
            "where the device has ended up compared with where it began.\n\n"
            "The numbers are ΔE2000. Below 1 nobody can see the difference; "
            "above 3 anybody can. The colours are fixed to that scale rather "
            "than stretched to fit, so two of these pictures can be held "
            "against each other.",
            self, title="Why only two profiles at a time")
        picture_row.addWidget(self._picture_hint, 0,
                              Qt.AlignmentFlag.AlignVCenter)
        if self._hosted:
            # The ⓘ goes with the chooser it explains -- "Show me", item 1,
            # not "coloured by" -- and the second caption keeps its own
            # chooser company.
            self._stack(picture_row, groups=((1, 4), (2, 3)))
            # AND NO CHOOSER MAY DICTATE THE WIDTH OF THE COLUMN. These hold
            # sentences -- "Where it moved — printer-2019 → printer-2024,
            # altogether (ΔE 3.03)" -- and left to itself a combo asks for its
            # longest item in full. Measured while switching the window to
            # light: one of them went from a least width of 115 px to 483,
            # which dragged the whole section to 547 in a 403 px space and cut
            # its frame off on the right. Reported exactly that way: "it also
            # makes the one device over time section wider and its frame cut
            # off on the right".
            #
            # WHY IT ONLY SHOWED WHEN THE THEME CHANGED: re-applying the
            # stylesheet is when Qt re-asks every widget how big it wants to
            # be, so the demand was there all along and the answer had simply
            # not been asked for again.
            for box in (self._picture_of, self._coloured_by):
                box.setSizeAdjustPolicy(
                    QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                box.setMinimumContentsLength(10)
        outer.addLayout(picture_row)

        # --- ANY two of them, not only the ones next to each other -----------
        #
        # Basti: "can i choose any two profiles from the trend for the direct
        # comparison and then go back to the full overview?"
        #
        # The chooser above lists the steps, which are the pairs somebody
        # reaches for most -- the graph jumped between these two, so where did
        # it go. But they are not the only pairs worth asking about: the
        # profile from before a head clean against the one six months later
        # need not be next to each other in the run at all.
        #
        # SHORTCUTS ABOVE, FREEDOM HERE, and the two are one thing: picking a
        # step fills these in, and changing these turns the chooser above to
        # "a pair you chose". Neither can disagree with what is drawn, because
        # both read the same two boxes.
        #
        # WHY NOT LIST EVERY PAIR IN ONE PLACE: a run of sixty profiles has
        # 1,770 pairs. Two lists of sixty is the same freedom in 120 lines
        # instead of 1,770.
        self._pair_row = QWidget(self)
        pair_row = QHBoxLayout(self._pair_row)
        pair_row.setContentsMargins(0, 0, 0, 0)
        pair_row.setSpacing(8)
        pair_row.addWidget(QLabel("from", self._pair_row), 0)
        self._pair_from = NoScrollComboBox(self._pair_row)
        self._pair_from.setToolTip(
            "The EARLIER of the two profiles — the one the cloud is drawn at, "
            "and the one the colours are measured from.")
        self._pair_from.activated.connect(lambda _i: self._pair_picked())
        pair_row.addWidget(self._pair_from, 1)
        pair_row.addWidget(QLabel("to", self._pair_row), 0)
        self._pair_to = NoScrollComboBox(self._pair_row)
        self._pair_to.setToolTip(
            "The LATER of the two — where those same colours have got to.")
        self._pair_to.activated.connect(lambda _i: self._pair_picked())
        pair_row.addWidget(self._pair_to, 1)
        if self._hosted:
            self._stack(pair_row, groups=((0, 1), (2, 3)))
            # THE SAME CAP AS THE TWO CHOOSERS ABOVE: these hold a profile
            # name and a date, which is more than a column is willing to
            # widen for. See the note on _picture_of.
            for box in (self._pair_from, self._pair_to):
                box.setSizeAdjustPolicy(
                    QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                box.setMinimumContentsLength(10)
        self._pair_row.setVisible(False)
        outer.addWidget(self._pair_row)

        self._view = QWebEngineView(self) if preview else None
        if self._view is not None:
            self._view.setMinimumHeight(240)
            # THE VIEW IS WHITE UNTIL A PAGE PAINTS OVER IT, and in a dark
            # window that is a white frame round the graph and a white flash
            # every time it redraws. Both the widget and the page underneath
            # have to be told, which is what the main window does for exactly
            # the same reason.
            self._paint_view()
            outer.addWidget(self._view, 1)

        # EVERYTHING SAID ABOUT THE PICTURE, IN ITS OWN SCROLLING PANEL.
        #
        # THE PICTURE IS THE POINT AND IT WAS THE SMALLEST THING ON SCREEN.
        # Each of these readouts is worth having, and stacked in the window's
        # own layout they compete with the graph for height -- so as the words
        # grew, the picture shrank to its 240px floor and the key underneath
        # it was cut off. Basti photographed exactly that: a window where the
        # cloud is a sliver and the sentences fill the rest.
        #
        # Bounded and scrolling, the words can be as long as they need to be
        # and cost the picture nothing. The reader scrolls the words; the
        # picture stays the size it was.
        # WHAT CHANGES THE PICTURE, gathered above what describes it.
        controls = QVBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        outer.addLayout(controls)
        said_panel = QWidget(self)
        said = QVBoxLayout(said_panel)
        said.setContentsMargins(0, 0, 0, 0)
        said.setSpacing(6)

        self._verdict = WrappedLabel("", self, hide_when_empty=True)
        said.addWidget(self._verdict)
        self._complaints = WrappedLabel("", self, hide_when_empty=True)
        self._complaints.setObjectName("hint")
        said.addWidget(self._complaints)

        # THE CAVEAT LIVES BESIDE THE GRAPH, not only behind the ⓘ. A trend
        # line is the kind of picture people trust more than they should, and
        # somebody who never opens the help will still read this.
        # AND IT GOES AWAY WHEN THERE ARE NO NUMBERS TO BE CAUTIOUS ABOUT.
        # With one profile open the panel correctly says "A run needs at
        # least two profiles of the same device" -- and then warned, in the
        # next breath, about what a set of numbers does not mean when no
        # numbers have been shown. Found by driving a run of exactly one.
        # BUILT EMPTY, AND FILLED WHEN THERE ARE NUMBERS. Built with its
        # words it showed the moment the window opened -- before anything was
        # open to be cautious about -- and then vanished on the first redraw,
        # which is the disappearing-line fault all over again. Caught by
        # audit_the_switch_changes_nothing on the run that introduced it.
        self._caution = WrappedLabel("", self, hide_when_empty=True)
        self._caution.setObjectName("hint")
        said.addWidget(self._caution)

        # --- the picture, split into the families the report talks about -----
        #
        # THE SAME SEVEN GROUPS AS THE SENTENCES BELOW, so the two halves of
        # the answer can be read against each other: the line says the blues
        # went toward the magentas, and switching every other family off shows
        # WHERE in the blues it happened. Filed by the same rule, from the
        # same function, so the picture cannot disagree with the words.
        #
        # THE LEGEND IS THE FILTER, and that is why this is one checkbox
        # rather than seven. Splitting the cloud into a trace per family gives
        # the drawing library's own click-to-hide behaviour for nothing, in
        # the window and in a saved page alike, offline and on a phone.
        self._by_family = QCheckBox("Split it into colour families", self)
        self._by_family.setToolTip(
            "Draws the picture as seven groups — reds, yellows, greens, "
            "cyans, blues, magentas and greys — instead of one cloud, and "
            "puts them in the key at the side with the number of colours in "
            "each.\n\n"
            "WHAT IT IS FOR: click a family in the key to hide it, and click "
            "it again to bring it back. With everything but the blues hidden "
            "you can see exactly where in the blues your printer moved, which "
            "a single cloud cannot show you — the interesting part is usually "
            "buried under everything else.\n\n"
            "THE GROUPS ARE THE ONES THE LIST UNDERNEATH DESCRIBES. If the "
            "text says the blues drifted toward the magentas, this is the way "
            "to go and look at those very colours.\n\n"
            "IT KEEPS WORKING IN A SAVED PAGE. Save the view as a web page "
            "and whoever opens it can hide and show the families too, with "
            "nothing installed and no internet needed.\n\n"
            "GREYS ARE COLOURS TOO CLOSE TO NEUTRAL to have a hue worth "
            "naming. They are their own group rather than being scattered "
            "among the six.")
        self._split_words = self._by_family.toolTip()
        self._by_family.stateChanged.connect(lambda _s: self._draw())
        # Ticking it greys the scales it silences, here as in the main window.
        self._by_family.stateChanged.connect(
            lambda _s: self._show_only_what_applies())
        # THE CONTROLS ARE NOT READOUTS, and hosted they no longer sit among
        # them. Basti, looking at the panel in the column: "maybe in this
        # section the options to split into color families and hide anything
        # under should be moved up over the info text above it and then all
        # the info text in the section should be put in a collapsible
        # subsection of its own".
        #
        # HE IS RIGHT, AND THE REASON IS NAMEABLE: everything that CHANGES the
        # picture belongs together, and everything that DESCRIBES it belongs
        # together. As built, the two switches sat between two blocks of
        # prose, so the eye had to cross a paragraph to get from one control
        # to the next -- and the prose was in a box with a scrollbar of its
        # own, inside a column that already scrolls, which is a fault in its
        # own right: nobody expects a second scrollbar.
        # THE SAME KIND OF ROW AS THE TICK BELOW IT. Added straight to the
        # column while its neighbour sat in a row with an ⓘ, it started four
        # pixels to the left -- the same fault, and the same measurement, as
        # the pair in "Has anything changed?". Reported again here: "split
        # into colour families and show the two shapes checkboxes are not
        # correctly aligned".
        _split_row = QHBoxLayout()
        _split_row.setContentsMargins(0, 0, 0, 0)
        _split_row.setSpacing(6)
        _split_row.addWidget(self._by_family, 1)
        (controls if self._hosted else said).addLayout(_split_row)

        # THE TWO SHAPES AROUND THE CLOUD, off unless it is asked for.
        #
        # WHY IT IS WORTH HAVING AT ALL, and it is the most surprising picture
        # this application draws: two profiles of one printer five years apart
        # hold 818,514 and 815,615 units of colour -- 0.35% apart, the same
        # size by any measure anybody quotes. By VOLUME that printer has not
        # changed. Inside those two identical shells the colours have moved by
        # up to ΔE 3.03. The shells and the cloud together say that in one
        # picture; either alone says half of it.
        #
        # OFF BY DEFAULT, because the cloud is the answer to the question that
        # was asked and two surfaces over it hide dots. Asked for by Basti:
        # "when comparing two runs in the heatmap view aren't there really any
        # options to show the shapes / mesh with the applicable options? maybe
        # not on by default there but as an option?"
        self._with_shapes = QCheckBox("Show the two shapes around it", self)
        self._with_shapes.setToolTip(
            "Draws the outline of each profile's whole gamut around the "
            "cloud, so you can see the colours moving inside the shapes they "
            "came from.")
        shapes_hint = Hint(
            "Draws both profiles as SHAPES around the cloud of dots: the "
            "outline of everything the earlier one can print, and the "
            "outline of everything the later one can.\n\n"
            "WHY IT IS WORTH LOOKING AT, and it is the most surprising thing "
            "this window can show you. Two profiles of one printer five years "
            "apart can hold almost exactly the same amount of colour — 0.35% "
            "apart in one real example — so by VOLUME, which is how most "
            "tools judge a printer, nothing has happened. Inside those two "
            "nearly identical shells the colours had moved by up to ΔE 3.03, "
            "which anybody can see on a print. The shells and the cloud "
            "together say that in one picture.\n\n"
            "WHAT YOU NEED FIRST: a pair chosen in Show me above, so that "
            "there is a cloud to put them around. With the graph showing "
            "there are no two shapes to draw.\n\n"
            "IT IS OFF UNTIL YOU ASK, because two surfaces over a cloud hide "
            "dots, and the dots are the answer to the question you came with. "
            "Turn it on when you want the context, off when you want to read "
            "the movement.\n\n"
            "IT TRAVELS INTO A SAVED WEB PAGE with everything else, and "
            "whoever opens that page gets the controls for the shapes too — "
            "make one fainter, draw it as edges only, take the colour out of "
            "it — so they can look inside them exactly as you can here.",
            self, title="The shapes around the cloud")
        shapes_hint.setObjectName("hint_with_shapes")
        shapes_hint.follow(self._with_shapes)
        self._with_shapes.setChecked(False)
        self._with_shapes.stateChanged.connect(lambda *_a: self._draw())

        # THE CONTROLS FOR THEM ARE THE ONES THE COLUMN ALREADY HAS.
        #
        # There were three here for a while -- how solid, as edges, in grey --
        # and Basti was right to take them out again: "i'd still rather use
        # the controls (also for mesh / grey / color / opacity) from the how
        # it looks section instead of the device over time section. they seem
        # redundant there and are not as many as in the other section where i
        # can make a mesh colorful for example and should also be able to
        # manipulate transparency of agreeing and disagreeing areas which we
        # have tweaked to perfection already".
        #
        # HOW IT LOOKS ALREADY GOVERNS THESE SHAPES, because they are drawn by
        # the same code as every other shape in this window and every one of
        # its settings is handed over -- see _how_the_window_draws_shapes. Set
        # this for now names the run's two profiles while the run owns the
        # picture, so each of them can be styled on its own.
        _shapes_row = QHBoxLayout()
        _shapes_row.setContentsMargins(0, 0, 0, 0)
        _shapes_row.setSpacing(6)
        _shapes_row.addWidget(self._with_shapes, 1)
        _shapes_row.addWidget(shapes_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        (controls if self._hosted else said).addLayout(_shapes_row)

        # --- hide the colours that barely moved -------------------------------
        #
        # WHY THIS EARNS ITS PLACE. The sentences under the picture give a
        # MEAN, and a mean hides the shape: "blues: ΔE 1.7 toward the
        # magentas (132 patches)" is equally true when all 132 moved 1.7 and
        # when 120 did not move at all and 12 moved 15. Pull this up to 2 and
        # only the colours anybody could see are left on screen.
        #
        # A SLIDER RATHER THAN A BOX TO TYPE IN, because the useful thing is
        # to drag it and watch the cloud thin out; the number beside it says
        # exactly where you are.
        cut_row = QHBoxLayout()
        cut_row.setContentsMargins(0, 0, 0, 0)
        cut_row.setSpacing(8)
        self._cut_label = QLabel("Hide anything under", self)
        cut_row.addWidget(self._cut_label, 0)
        self._cut = NoScrollSlider(Qt.Orientation.Horizontal, self)
        # TENTHS, because that is as fine as the data supports and as fine as
        # the instrument does. An i1Pro repeats to about ΔE 0.1 on white and
        # two different instruments agree to about 0.4, so a hundredth would
        # be reading the instrument talking to itself -- and measured on a
        # real run, 62% of hundredth-steps change no dot at all.
        self._cut.setMinimum(0)
        self._cut.setSingleStep(1)
        self._cut.setPageStep(5)
        self._cut.setValue(0)
        self._cut.setToolTip(
            "Leaves out every colour that moved less than this, so what is "
            "left on screen is only the movement worth looking at.\n\n"
            "WHY YOU WANT IT: the lines underneath give an AVERAGE for each "
            "family, and an average hides the shape. \"Blues: ΔE 1.7\" reads "
            "the same whether all of them moved 1.7, or nearly all of them "
            "sat still and a handful moved a great deal — and those are very "
            "different problems. Drag this up to 2 and only the colours "
            "anybody could actually see are left.\n\n"
            "WHERE IT STOPS: at the biggest difference in THIS pair, because "
            "beyond that there would be nothing left to hide and the rest of "
            "the slider would do nothing. If the two files are identical the "
            "slider is switched off altogether.\n\n"
            "IN STEPS OF ΔE 0.1, which is as fine as the numbers support: a "
            "hand-held spectrophotometer repeats to about ΔE 0.1 on white, "
            "and two different instruments agree to about 0.4, so anything "
            "finer would be reading the instrument rather than your "
            "printing.\n\n"
            "IT CHANGES THE PICTURE ONLY. The sentences underneath always "
            "describe every colour, so two people with the slider in "
            "different places still quote the same numbers to each other. "
            "The picture says how many it left out, and a saved web page says "
            "so too.")
        self._cut.valueChanged.connect(self._cut_changed)
        cut_row.addWidget(self._cut, 1)
        self._cut_says = QLabel("nothing hidden", self)
        # A FLOOR IN THE WINDOW, where it shares a line with the slider and
        # the words would otherwise jog it about as they change. In the
        # column it sits at the end of the caption's line with the slider
        # below, so it needs no reserved room at all.
        self._cut_says.setMinimumWidth(0 if hosted else 116)
        cut_row.addWidget(self._cut_says, 0)
        cut_hint = Hint(
            "The picture keeps every colour by default. Sliding this to the "
            "right takes out the ones that moved least, one tenth of a ΔE at "
            "a time, until only the biggest movements are left.\n\n"
            "It is the quickest way to answer \"where is the real problem\" "
            "on a chart where most patches are fine: raise it until only a "
            "handful of dots remain, and those are the colours to go and look "
            "at on the print.\n\n"
            "Nothing is thrown away — put it back to the left and every "
            "colour returns.", self)
        cut_hint.setObjectName("hint_cut")
        cut_row.addWidget(cut_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        cut_hint.follow(self._cut)
        self._cut_row = cut_row
        if self._hosted:
            # THE SLIDER GETS THE WIDTH, and the words go above it. Squeezed
            # into one row between a caption, a reading and an ⓘ, it was
            # about 60 px long for a range of two and a half ΔE -- roughly
            # four pixels per tenth, which is not something a hand can aim.
            # Reported: "the slider of the option below is too short to give
            # granular control".
            #
            # THE SAME THREE THINGS, IN TWO ROWS: the caption and its ⓘ, then
            # the slider with its reading beside it. Nothing is lost and the
            # slider is three times the length.
            items = [cut_row.takeAt(0) for _ in range(cut_row.count())]
            widgets = [item.widget() for item in items]
            top = QHBoxLayout()
            top.setContentsMargins(0, 0, 0, 0)
            top.setSpacing(6)
            # THE CAPTION, THE READING AND THE ⓘ ON ONE LINE; the slider
            # gets the whole of the next. Sharing its line with the reading
            # left it 156 px for 24 steps; alone it has the width of the
            # column, which is fourteen pixels a tenth -- an amount a hand can
            # actually place.
            top.addWidget(widgets[0], 0)                  # the caption
            top.addStretch(1)
            top.addWidget(widgets[2], 0)                  # what it reads
            if len(widgets) > 3 and widgets[3] is not None:
                top.addWidget(widgets[3], 0, Qt.AlignmentFlag.AlignVCenter)
            bottom = QHBoxLayout()
            bottom.setContentsMargins(0, 0, 0, 0)
            bottom.setSpacing(6)
            bottom.addWidget(widgets[1], 1)               # the slider itself
            controls.addLayout(top)
            controls.addLayout(bottom)
        else:
            said.addLayout(cut_row)

        # --- which colour families moved --------------------------------------
        #
        # THE SAME ANSWER AS THE PICTURE, IN A FORM SOMEBODY CAN SEND. Asked
        # for by a paper manufacturer who wanted "reds: stayed the same, blues:
        # drifted toward green" to paste into an email. The direction view
        # above already knows this and shows it as a cloud; a cloud cannot be
        # pasted anywhere and has to be interpreted by whoever is looking.
        #
        # UNDER the picture and the verdict rather than beside them, because it
        # is a summary of what is already on screen and not a third thing to
        # choose between.
        self._families = WrappedLabel("", self, hide_when_empty=True)
        self._families.setObjectName("families")
        self._families.setToolTip(
            "Which colour families moved between these two profiles, and "
            "which way — the same answer the picture above is showing, "
            "written out so you can paste it into an email or a report.\n\n"
            "EVERY LINE SAYS HOW MANY PATCHES IT STANDS ON. A family with "
            "four colours in it and one with four hundred produce the same "
            "kind of sentence, and only that number tells you how much to "
            "trust it.\n\n"
            "\"STAYED THE SAME\" MEANS UNDER ΔE 1, the same figure this "
            "application uses everywhere else for a difference a careful eye "
            "would begin to notice.\n\n"
            "\"MIXED\" MEANS THE COLOURS IN THAT FAMILY MOVED, BUT NOT "
            "TOGETHER. There is no single direction that would be true of "
            "them, so none is given rather than inventing one from the "
            "average.\n\n"
            "\"BUT NOT CERTAINLY\" MEANS THE MOVEMENT IS NO BIGGER THAN ITS "
            "OWN SCATTER — take it as a hint to look, not as a finding.\n\n"
            "THE GREYS are colours too close to neutral to have a hue worth "
            "naming, so they are never said to have drifted toward a colour. "
            "They are reported as warmer, cooler, redder, greener, lighter or "
            "darker instead.")
        said.addWidget(self._families)
        self._families_note = WrappedLabel("", self, hide_when_empty=True)
        self._families_note.setObjectName("hint")
        said.addWidget(self._families_note)


        if self._hosted:
            # IN THE COLUMN THE WORDS FOLD; THEY DO NOT SCROLL. A box with its
            # own scrollbar inside a column that already scrolls gives the
            # reader two of them a few pixels apart, and the inner one hides
            # its own contents from any attempt to read the panel by scrolling
            # the column. Folded away, the words take no room at all; opened,
            # they take exactly as much as they need and the column carries
            # them, which is what a column is for.
            #
            # OPEN TO BEGIN WITH, because the words ARE the answer: somebody
            # who has just added four profiles is here to read "it has drifted
            # steadily", and a heading they have to find first would hide the
            # thing they came for.
            words = self._words_box = QGroupBox(
                "What this is telling you", self)
            inside = QVBoxLayout(words)
            inside.setContentsMargins(10, 4, 10, 6)
            inside.addWidget(said_panel)
            outer.addWidget(words, 0)
            make_foldable(words, "run-words", True)
        else:
            said_area = FadeScrollArea(self)
            said_area.setWidget(said_panel)
            said_area.setWidgetResizable(True)
            said_area.setFrameShape(QFrame.Shape.NoFrame)
            said_area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            # A CEILING, NOT A HEIGHT, in the window: short readouts take the
            # room they need and no more; long ones stop here and scroll,
            # which is the only way the graph above keeps a usable share of a
            # small window. The column has no such fight to settle.
            said_area.setMaximumHeight(300)
            outer.addWidget(said_area, 0)

        self._refresh()

    # --- the list ----------------------------------------------------------


    @staticmethod
    def _stack(row, groups=()):
        """Turn a row that runs across into one that runs down.

        THE COLUMN IS 366 PX AND THIS WINDOW WAS 940. Four buttons side by
        side become four 80 px buttons, and "Remove the selected one" is not a
        thing that fits in eighty pixels -- it becomes "Remove the sel…", which
        this project has shipped before and has an audit script to stop.

        *groups* names which items stay side by side, by their position in the
        row, e.g. ``((0,), (1, 4), (2, 3))``. Anything not named gets a line
        of its own, in the order it was in.

        AN ⓘ MUST TRAVEL WITH WHAT IT EXPLAINS, and that is why the grouping
        is by index rather than "keep the next two together". The picture row
        is caption, chooser, caption, chooser, icon -- the icon explains the
        FIRST chooser, four places to its left. Stacked naively it landed
        beside the second one, and the panel audit caught it at once: "'' under
        'One device over time' has its own caption and no explanation on its
        row".
        """
        items = [row.takeAt(0) for _ in range(row.count())]
        widgets = [item.widget() for item in items]
        row.setDirection(QBoxLayout.Direction.TopToBottom)
        row.setSpacing(6)
        named = {i for group in groups for i in group}
        plan = list(groups) + [(i,) for i in range(len(items))
                               if i not in named]
        # In the order the row had them, judged by the first of each group.
        for group in sorted(plan, key=lambda g: g[0]):
            live = [widgets[i] for i in group if widgets[i] is not None]
            if not live:
                # A STRETCH IS DROPPED. Sideways it pushed the exports to the
                # right; downwards it would push them off the bottom.
                continue
            if len(live) == 1:
                row.addWidget(live[0])
                continue
            sub = QHBoxLayout()
            sub.setContentsMargins(0, 0, 0, 0)
            sub.setSpacing(6)
            for widget in live:
                stretch = 1 if isinstance(widget, (QComboBox, QSlider)) else 0
                sub.addWidget(widget, stretch, Qt.AlignmentFlag.AlignVCenter)
            row.addLayout(sub)
        return row

    def _reordered(self, *_a) -> None:
        """Follow the rows the user dragged, rather than the order they came.

        A HAND-SORTED RUN IS THE USER'S ORDER, so re-sorting it by date after
        they moved something would undo the move in front of them. The list is
        the truth once they have touched it.
        """
        order = []
        for i in range(self._list.count()):
            path = self._list.item(i).data(Qt.ItemDataRole.UserRole)
            if path:
                order.append(Path(path))
        if order:
            self._paths = order
            self._rebuild(sort=False)

    def add(self, paths) -> None:
        """Take on more profiles, ignoring any already in the run."""
        # THE SET GROWS AS IT GOES, and that one line is the difference
        # between "ignoring any already in the run" and doing it properly:
        # worked out once before the loop, the same file named twice in ONE
        # drop went in twice. Two identical profiles in a run draw a step of
        # ΔE 0 and a flat piece of graph, which reads as a device that did not
        # move rather than as a file added twice.
        here = {p.resolve() for p in self._paths}
        for raw in paths:
            path = Path(raw)
            try:
                if path.resolve() in here:
                    continue
                here.add(path.resolve())
            except OSError:
                pass
            self._paths.append(path)
        self._rebuild()
        self._bring_the_answer_into_view()

    def _bring_the_answer_into_view(self) -> None:
        """Scroll the column to this panel when a run is added to it.

        THE ANSWER WAS BELOW THE FOLD AND NOTHING WENT TO IT. Measured on a
        1280x800 window with four profiles added: "What this is telling you"
        sits 925 px down the column, the pane shows to 687, and adding the
        run moved the scroll from 0 to 0. So the reader clicks Add profiles…,
        the big view fills with a graph, and the sentence saying what the
        graph MEANS is 238 px below anything they can see, with no hint that
        it is there.

        SCROLLED TO THE PANEL'S TOP, NOT TO THE ANSWER. Asking
        `ensureWidgetVisible` for the words themselves was tried first and
        photographed: it scrolls far enough to fit the whole box, which is
        tall, and the reader lands on a wall of text with the section
        heading, the list and Add profiles… all off the top of the pane.
        That is the opposite of "we need to keep a good overview".

        The panel is 827 px against a 687 px pane -- only 140 px too tall --
        so putting its top at the top of the pane shows the heading, the
        list, every button, both choosers AND the first lines of the answer,
        and leaves the rest one short scroll away.

        Does nothing in the standalone window, which has no column to scroll.
        """
        if not self._hosted or not self._paths:
            return
        node = self.parentWidget()
        while node is not None and not isinstance(node, QScrollArea):
            node = node.parentWidget()
        if node is None:
            return

        def settle():
            inner = node.widget()
            if inner is None:
                return
            # THE SENTENCE THAT SAYS THE VIEW CHANGED HANDS COMES FIRST.
            #
            # Found by crossing what is open against a run rather than by
            # driving a run on its own: with a file or a comparison also
            # open, the big view stops showing them and starts showing the
            # run, and one line above this panel is the only thing that says
            # so -- "The big view is showing this run. printer-2019 is still
            # open as well, and it comes back as soon as you remove these
            # profiles."
            #
            # Landing on the panel's top edge scrolled straight past it, in
            # all six of the eight states where it has anything to say. The
            # line was VISIBLE before any of this was built, because nothing
            # scrolled at all -- so a fix for one fault had quietly made
            # another.
            #
            # It costs about forty pixels at the bottom of the view and it is
            # the difference between a picture that changed and a picture
            # that changed FOR A REASON.
            start = self
            owner = getattr(self._host, "_who_owns", None)
            if (owner is not None and owner.text()
                    and owner.isVisibleTo(inner)):
                start = owner
            top = start.mapTo(inner, start.rect().topLeft()).y()
            bar = node.verticalScrollBar()
            # EXACTLY THE PANEL'S TOP EDGE, and nothing clever. Stopping a
            # little short to catch the section's heading was tried and
            # photographed: the heading does not fit either, so the pane
            # opens on a sentence cut through the middle, which reads as a
            # drawing fault rather than as more text above. Landing on the
            # list's own top edge is clean, and the heading is one small
            # scroll up from a reader who just clicked a button inside it.
            bar.setValue(max(bar.minimum(), min(bar.maximum(), top)))

        # AFTER THE LAYOUT HAS SETTLED. Asked in the same breath as the
        # rebuild, the panel has not yet grown to its new height and the
        # scroll lands short of where it needs to be.
        QTimer.singleShot(0, settle)

    def _on_add(self) -> None:
        parent = self.parent()
        chooser = parent._file_dialog(
            "Choose profiles of one device", QFileDialog.FileMode.ExistingFiles,
            "ICC profiles (*.icc *.icm)", profiles=True)
        if chooser.exec():
            self.add(chooser.selectedFiles())

    def _drop_one(self, path: str) -> None:
        """Take one profile out of the run, named by its own path.

        Named rather than numbered because the rows reorder by dragging: a
        button that remembered which POSITION it was born at would take
        somebody else's profile out after a drag, and it would look like the
        list had simply lost track.
        """
        keep = [p for p in self._paths if str(p) != str(path)]
        if len(keep) != len(self._paths):
            self._paths = keep
            self._rebuild()
            if not self._paths:
                self._blank()

    def _on_remove(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < len(self._paths):
            # REMOVED FROM THE RUN, NEVER FROM THE DISK. Nothing in this
            # window owns the user's files.
            self._paths.pop(row)
            self._rebuild()

    def _on_clear(self) -> None:
        self._paths = []
        self._rebuild()
        # AND THE PICTURE GOES WITH THEM. _rebuild redraws, and a redraw with
        # no run in it is the path that hands the view back -- but only if it
        # is actually walked, which it was not: with the list already empty
        # _refresh had nothing to say and the run's picture stayed on screen.
        self._blank()

    def dragEnterEvent(self, event) -> None:       # noqa: N802  (Qt's name)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:            # noqa: N802  (Qt's name)
        dropped = [u.toLocalFile() for u in event.mimeData().urls()
                   if u.isLocalFile()]
        wanted = [p for p in dropped
                  if Path(p).suffix.lower() in (".icc", ".icm")]
        if wanted:
            self.add(wanted)
            event.acceptProposedAction()

    # --- working it out ----------------------------------------------------

    def _rebuild(self, sort: bool = True) -> None:
        import drift_series

        if len(self._paths) < 1:
            self._run = None
        else:
            self._run = drift_series.build(self._paths, steps=self.GRID)
            if sort and self._run.ordered_by == "date":
                # The run put itself in date order, so the list must show that
                # order rather than the order the files arrived in.
                self._paths = [e.path for e in self._run.entries]
        self._refresh()

    def _refresh(self) -> None:
        import drift_series

        self._list.blockSignals(True)
        self._list.clear()
        entries = self._run.entries if self._run else []
        for entry in entries:
            if entry.usable:
                text = f"{entry.name}    {entry.dated}"
            else:
                text = f"{entry.name}    — could not be read"
            # THE ROW CARRIES ITS OWN × , like the files above it. Asked for
            # from the window: "in the other section ... there is an X next to
            # each one to close it. but in the section for the runs this is
            # different. you would have to select them there and click the
            # close selected button. what do you think is better? with the X
            # we would not need the close selected button".
            #
            # Better, and for three reasons beyond matching: it is one click
            # where selecting-then-clicking is three; it cannot act on the
            # wrong thing, because an × means the row it sits on and nothing
            # else, where "the selected one" with nothing selected means
            # whatever the list last remembered; and it gives the crowded
            # column a row of its height back by removing a button.
            item = QListWidgetItem("", self._list)
            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            # THE WORDS STAY ON THE ROW ITSELF as well as on the widget that
            # draws them. A row drawn by a widget of its own has no text of
            # its own, and everything that reads the list rather than looks
            # at it -- a screen reader, a test, the panel audits -- was
            # handed a list of six empty strings. The widget paints; this is
            # what the row IS.
            item.setData(Qt.ItemDataRole.AccessibleTextRole, text)
            item.setToolTip(str(entry.path))
            row = QWidget(self._list)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 0, 2, 0)
            rl.setSpacing(6)
            said = ElidingLabel(text, row)
            said.setObjectName("slot")
            rl.addWidget(said, 1)
            shut = QPushButton("×", row)
            shut.setObjectName("closer")
            shut.setFixedSize(22, 22)
            shut.setToolTip("Take this profile out of the run")
            # BY PATH, NOT BY POSITION. The rows can be dragged into another
            # order, and a row that remembered "I am the third" would then
            # remove somebody else's profile.
            shut.clicked.connect(
                lambda _checked=False, which=str(entry.path):
                self._drop_one(which))
            rl.addWidget(shut, 0)
            item.setSizeHint(row.sizeHint())
            self._list.setItemWidget(item, row)
        # AN EMPTY LIST IS A FRAME AROUND NOTHING, and in the column it is a
        # framed 52 px of nothing sitting on top of the button that fills it.
        # Reported from the window exactly that way: "one device over time
        # shows an empty frame over the add button".
        #
        # It has a least height for the good reason written where it is made
        # -- a list that grows and shrinks by one row as profiles arrive is
        # worse than one that holds still -- and that reason does not apply
        # when there is nothing in it at all.
        #
        # HIDING IT COSTS NO DROP TARGET. The rows can be dragged among
        # themselves (InternalMove), but a file is dropped on the PANEL, which
        # is still there and still the same size everywhere else.
        self._list.setVisible(bool(entries))
        self._show_only_what_applies()
        if self._hosted:
            rows = max(1, min(6, self._list.count()))
            step = max(18, self._list.sizeHintForRow(0)
                       if self._list.count() else 18)
            self._list.setMaximumHeight(rows * step + 2 * self._list.frameWidth() + 4)
        if not entries:
            for path in self._paths:
                item = QListWidgetItem(Path(path).stem, self._list)
                item.setData(Qt.ItemDataRole.UserRole, str(path))
        self._list.blockSignals(False)

        has = len(self._paths)
        self._remove_btn.setEnabled(has > 0)
        self._clear_btn.setEnabled(has > 0)
        drawable = bool(self._run and self._run.since_first)
        self._save_btn.setEnabled(drawable)
        self._table_btn.setEnabled(drawable)

        if self._run is None:
            self._verdict.setText("")
            self._complaints.setText(self.NOTHING_OPEN)
            self._blank()
            return

        self._fill_pictures()
        said = list(self._run.complaints)
        if drawable and self._run.ordered_by != "date":
            said.append(
                "These are in the order you added them, because not every "
                "profile carries a usable date. Drag a row to move it.")
        self._grumbles = said
        self._draw()

    #: What the answer box says before there is anything to answer about.
    #: ONE PLACE, because it is written by two: the pass that fills the panel
    #: and the pass that draws it. Kept apart, they went out of step at once
    #: -- the second wrote an empty string over the first.
    NOTHING_OPEN = "Nothing open yet. Add two or more profiles of one device."

    def _say(self) -> None:
        """Put the words that belong to whichever picture is about to be drawn.

        THE WORDS UNDER A PICTURE HAVE TO BE ABOUT THAT PICTURE. The verdict
        was written once, from the whole run, and left there whichever picture
        was showing -- so choosing a single step put "it has drifted steadily,
        from the first to the last, ΔE 3.03" under a cloud of one year.

        CALLED FROM `_draw` RATHER THAN FROM THE CHOOSER, and that is the
        second half of the fix. The first attempt updated the words where the
        combo box is handled, which is right for a person clicking it and
        wrong for everything else -- the screenshot generator set the box and
        called `_draw`, and published a picture of one comparison with the
        sentence for another underneath it. Anything that redraws now says the
        right thing by construction, because saying it is part of drawing.
        """
        import drift_series

        # AND WITH NOTHING OPEN IT STILL SAYS SO. This line wrote the list
        # of complaints straight over whatever was in the box, and with no
        # run there are no complaints -- so it wrote nothing, and the box
        # went empty. _refresh had put "Nothing open yet..." there when the
        # panel was built, and this wiped it the first time anything redrew.
        #
        # WHICH LOOKED LIKE A THEME BUG, because the first thing that redraws
        # a freshly opened window is usually the appearance switch: the line
        # was there when the window opened and gone once you had been to the
        # other appearance and back, and nothing brought it back. Found by
        # driving that round trip and comparing what the window SAYS before
        # and after -- a switch may change how the window looks and must
        # never change what it tells you.
        self._complaints.setText(
            "\n\n".join(getattr(self, "_grumbles", []))
            or (self.NOTHING_OPEN if self._run is None else ""))
        pair = self._chosen_pair()
        # THE FAMILY SPLIT ONLY WHERE IT CAN DO SOMETHING. Splitting into
        # families is a thing you do to the CLOUD; the graph has no colours in
        # it to split. A checkbox sitting there while the graph shows would
        # answer a click with nothing, which this window holds is worse than a
        # control that is not there at all.
        self._show_only_what_applies()
        if pair is None or self._run is None:
            self._verdict.setText(
                drift_series.verdict(self._run) if self._run else "")
            # NOTHING TO COMPARE, NOTHING TO CAUTION ABOUT.
            self._caution.setText(
                "" if not (self._run and self._run.since_first) else
                "Remember: this is how far apart the PROFILES are, not how "
                "far the device drifted. Chart fade and any change in how you "
                "built them are inside these numbers too.")
        else:
            self._verdict.setText(self._pair_verdict(pair))
            self._caution.setText(
                "Remember: this is how far apart these two PROFILES are, not "
                "how far the device drifted between them. Each is one day's "
                "measurements of one chart, so chart fade and any change in "
                "how you built them are inside these numbers too.")
        self._say_the_families(pair)

    def _show_only_what_applies(self) -> None:
        """Hide the controls that could do nothing where they stand.

        THE SPLIT AND THE THRESHOLD ARE THINGS YOU DO TO A CLOUD. The graph
        has no colours to split or to hide, and a control that answers a click
        with nothing is worse than one that is not there -- this file's rule,
        applied to its own panel.

        CALLED FROM THE REFRESH AS WELL AS THE DRAW, which is what was missing:
        with no run at all, nothing had drawn yet, so the rule had never run
        and the column showed a tick and a slider over an empty list. The
        panel audit saw the other half of it, an ⓘ left beside them: "ORPHAN
        ⓘ hint_cut explains nothing on its row".
        """
        # NOTHING OPEN, NOTHING TO CHOOSE BETWEEN. With no profiles at all
        # "Show me" is an empty dropdown and "coloured by" offers five ways to
        # paint a picture that does not exist. Found while fixing the empty
        # frame reported just above it -- "one device over time shows an empty
        # frame over the add button" -- which is the same fault twice more in
        # the same section: a control drawn around nothing.
        #
        # These come back the moment a profile arrives, which is also when
        # they have something in them.
        started = bool(self._paths)
        for part in (self._picture_label, self._picture_of,
                     self._coloured_label, self._coloured_by,
                     self._picture_hint):
            part.setVisible(started)
        useful = self._chosen_pair() is not None
        self._by_family.setVisible(useful)
        # AND THE SAME RULE AS THE MAIN WINDOW'S, because it is the same pair
        # of controls. "Split it into colour families" groups the cloud by the
        # family each colour IS IN; "the colour it is heading for" groups it by
        # the family it is going TO, and wins -- the split is not even passed
        # on. Ticked together they used to CRASH the window (see build_figure);
        # with that fixed the tick would merely have sat there lit, claiming a
        # grouping the picture does not use.
        #
        # Fixed in the main window first and only there, which is exactly the
        # asymmetry Basti asked to stop: "in general both path should benefit
        # from any improvements".
        by_destination = self._coloured_by.currentData() == "toward"
        self._by_family.setEnabled(useful and not by_destination)
        self._by_family.setToolTip(
            GamutApp.SPLIT_IS_THE_DESTINATIONS if by_destination
            else self._split_words)
        # AND THE SAME PAIR FROM THE OTHER SIDE, by the same function the main
        # window calls -- see grey_the_scales.
        grey_the_scales(self._coloured_by, self._by_family,
                        getattr(self, "_coloured_by_words", None))
        self._with_shapes.setVisible(useful)
        for part in (self._cut, self._cut_label, self._cut_says):
            part.setVisible(useful)
        # AND EVERY ⓘ GOES WITH THE CONTROL IT EXPLAINS. An icon follows its
        # partner by listening for that partner being shown or hidden, and a
        # control hidden before it was ever on screen sends no such event.
        for icon in self.findChildren(Hint):
            partner = getattr(icon, "_followed", None)
            if partner is not None:
                icon.setVisible(not partner.isHidden())

    def _say_the_families(self, pair) -> None:
        """The family-by-family report for whatever is on screen.

        FOR THE PAIR WHEN THERE IS ONE, AND FOR THE WHOLE RUN OTHERWISE, so
        the words are always about the picture above them. The run's version
        is first against last, which is the comparison the graph's own verdict
        is about.

        THE FOOTNOTE IS NOT OPTIONAL. The line between one colour family and
        the next is drawn by this application and exists nowhere in nature --
        the request this was built from said so before anybody
        had written a line of it. So the report says where the line is, and
        how many colours sat close enough to it to have gone either way.
        """
        said = self._family_report(pair)
        self._families.setText("" if said is None else said[0])
        self._families_note.setText("" if said is None else said[1])

    def _family_report(self, pair):
        """The report for whichever pair this window is showing.

        Finding the pair is this window's job; saying it is not -- the words
        come from the shared helper, so the timeline, the main window and the
        exports cannot drift apart in what they claim.
        """
        if self._run is None:
            return None
        try:
            if pair is not None:
                path_a, path_b, spans = pair
            else:
                # THE USABLE ENTRIES, not the paths that were added. A profile
                # that could not be read is still in _paths, and taking the
                # first and last of THAT list means comparing files the rest
                # of this window has already refused.
                usable = self._run.usable
                if len(usable) < 2:
                    return None
                path_a, path_b = usable[0].path, usable[-1].path
                spans = f"{usable[0].name} to {usable[-1].name}"
            from ti3gamut import compare_profiles
            d = compare_profiles(path_a, path_b, steps=self.GRID)
            if not d.comparable or d.lab_a is None:
                return None
        except Exception:              # noqa: BLE001 — a missing report is
            return None                # not worth losing the picture over
        return family_report(d.lab_a, d.lab_b, spans, of="profiles")

    def _pair_verdict(self, pair) -> str:
        """What one step amounts to, in the same voice the run's verdict uses.

        Deliberately says the SAME two thresholds -- 1 and 3 -- as everything
        else in this application, so a reader who has learned them once does
        not meet a second vocabulary in the second picture.
        """
        import drift_series
        from ti3gamut import compare_profiles

        path_a, path_b, spans = pair
        try:
            d = compare_profiles(path_a, path_b, steps=self.GRID)
        except Exception:              # noqa: BLE001 — the panel must still say something
            return f"{spans} could not be compared."
        if not d.comparable:
            return (f"{spans} were not read the same way, so there is no "
                    f"honest number to give you for them.")
        if d.worst < drift_series.INVISIBLE:
            return (f"{spans}: nothing here that anybody could see. The "
                    f"biggest difference anywhere in the cube is ΔE "
                    f"{d.worst:.2f}, below the point at which a difference "
                    f"becomes visible at all.")
        scale = ("visible on a careful look" if d.worst < drift_series.OBVIOUS
                 else "plainly visible")
        share = 100.0 * d.over_one / max(d.matched, 1)
        # WHERE TO LOOK DEPENDS ON WHAT IS DRAWN. "The largest and reddest
        # dots" is true of the distance view and false of the direction ones,
        # whose dots are teal and orange and whose two ends mean opposite
        # things rather than more and less. Sending a reader to look for red
        # in a picture with no red in it is worse than saying nothing.
        axis = self._coloured_by.currentData()
        # THE TWO SHAPES, BUILT FROM THE SAME NUMBERS THE CLOUD IS DRAWN
        # FROM. compare_profiles already asked both profiles for the same grid
        # of ink amounts and holds where each puts them, so the hull of those
        # points IS that profile's gamut -- no second reading of the file, no
        # second opinion about what its shape is, and nothing to keep in step.
        if axis == "toward":
            # WHERE MOST OF IT IS GOING, counted rather than eyeballed. The
            # picture shows six destinations at once and the eye is a poor
            # judge of which group is biggest when they are scattered through
            # a cloud; this is the sentence somebody would want to quote.
            #
            # AND IT CRASHED HERE FIRST. This method looked the chooser's
            # answer up in the table of the three axes without asking whether
            # it was one of them, so the moment the new view was picked in the
            # real window the whole panel threw KeyError: 'toward'. Nothing in
            # the test suite touched it; driving the window did, immediately.
            moved = d.moved
            if moved is not None:
                from gamutview import heading_for
                going = heading_for(d.lab_a, d.lab_a + moved)
                counts = {}
                for name in going:
                    counts[name] = counts.get(name, 0) + 1
                quiet = counts.pop("", 0)
                total = len(going)
                if not counts:
                    return (f"{spans}: nothing here is heading anywhere in "
                            f"particular. All {total} colours either moved "
                            f"less than ΔE 1 — too little for the direction "
                            f"to mean anything — or are too close to neutral "
                            f"to have a hue at all. The biggest difference "
                            f"anywhere is ΔE {d.worst:.2f}.")
                best = max(counts.items(), key=lambda kv: kv[1])
                named = sum(counts.values())
                return (f"{spans}: of {total} colours, {named} are heading "
                        f"somewhere and {quiet} are not moving enough to say. "
                        f"The largest group, {best[1]} of them, is heading "
                        f"toward the {best[0]}. Each dot is painted the "
                        f"colour of the family it is going to; the grey ones "
                        f"are the colours that stayed put. The biggest "
                        f"difference anywhere is ΔE {d.worst:.2f}, which is "
                        f"{scale}.")
        if axis:
            asks, less, more, column = DIRECTIONS[axis]
            moved = d.moved
            if moved is not None:
                import numpy as _np
                middle = float(_np.mean(moved[:, column]))
                went = (more if middle > 0 else less)
                strength = ("hardly at all on average" if abs(middle) < 0.5
                            else f"by {abs(middle):.2f} on average")
                return (f"{spans}, {asks}: taken all together it has gone "
                        f"{went}, {strength}. The biggest difference anywhere "
                        f"is ΔE {d.worst:.2f}, which is {scale}. The two ends "
                        f"of the scale are opposite directions, and the "
                        f"middle is no change — so the pale dots are the "
                        f"colours that stayed put.")
        return (f"{spans}: the biggest difference is ΔE {d.worst:.2f}, which "
                f"is {scale}, and the average is {d.average:.2f}. "
                f"{d.over_one} of {d.matched} colours moved by more than 1 "
                f"({share:.0f}%), and {d.over_three} by more than 3. The ones "
                f"that moved most are the largest and reddest dots — that is "
                f"where to look, and it is what the graph cannot tell you.")

    def _fill_pictures(self) -> None:
        """The trend, then one entry per step, then the whole run.

        REBUILT WHENEVER THE RUN CHANGES, and what the reader had chosen is
        kept when it still exists. Removing a profile from the middle of a run
        changes which pairs there ARE, so a remembered index would quietly
        start showing a different pair than the one on the label -- which is
        the worst way for this to fail, because nothing looks wrong.
        """
        was = self._picture_of.currentData()
        self._picture_of.blockSignals(True)
        self._picture_of.clear()
        self._picture_of.addItem("When it moved — the graph", None)
        run = self._run
        usable = list(run.usable) if run else []
        steps = list(run.since_previous) if run else []
        # TWO ENDS WITH ONE NAME IS NOT A CHOICE ANYBODY CAN MAKE. A printer
        # profiled into a folder per month gives every profile the same file
        # name, so this list read "Where it moved — the-printer → the-printer"
        # and every entry in it looked identical. The step already carries the
        # two dates; they are put in exactly where the names do not separate.
        for i, step in enumerate(steps):
            before, after = step.before, step.after
            if before == after and step.before_on and step.after_on:
                before = f"{before} ({step.before_on})"
                after = f"{after} ({step.after_on})"
            self._picture_of.addItem(
                f"Where it moved — {before} → {after} "
                f"(ΔE {step.worst:.2f})", ("step", i))
        # THE WHOLE RUN IS A PAIR TOO, and the one people ask for first: not
        # what happened in any single year but where it has ended up against
        # where it began. Offered only when there is more than one step, since
        # with two profiles it would be the same picture listed twice.
        if len(steps) > 1 and run is not None:
            first_name, last_name = usable[0].name, usable[-1].name
            if first_name == last_name:
                first_name = f"{first_name} ({usable[0].dated})"
                last_name = f"{last_name} ({usable[-1].dated})"
            self._picture_of.addItem(
                f"Where it moved — {first_name} → {last_name}, "
                f"altogether (ΔE {run.total:.2f})", ("whole", 0))
        # ONLY WHERE THERE IS A CHOICE TO MAKE. With two profiles there is
        # exactly one possible pair and the step above already is it, so this
        # entry would be a second name for one picture -- which is how
        # somebody comes to believe they are looking at two different answers.
        if len(usable) > 2:
            self._picture_of.addItem(
                "Where it moved — any two you choose below", ("pair", 0))
        self._picture_of.blockSignals(False)
        if was is not None:
            found = _entry_at(self._picture_of, was)
            self._picture_of.setCurrentIndex(max(found, 0))
        self._picture_of.setEnabled(bool(steps))

        # The two boxes that hold whichever pair is being compared.
        for box in (self._pair_from, self._pair_to):
            keep = box.currentData()
            box.blockSignals(True)
            box.clear()
            for i, entry in enumerate(usable):
                box.addItem(f"{entry.name}    {entry.dated}", i)
            box.blockSignals(False)
            if keep is not None and 0 <= keep < len(usable):
                box.setCurrentIndex(keep)
        if usable and self._pair_from.currentIndex() < 0:
            self._pair_from.setCurrentIndex(0)
        if usable and self._pair_to.currentIndex() < 0:
            self._pair_to.setCurrentIndex(len(usable) - 1)
        self._sync_pair_boxes()

    def _sync_pair_boxes(self) -> None:
        """Make the two boxes show whichever pair the chooser above names."""
        choice = self._picture_of.currentData()
        run = self._run
        if choice is None or run is None or not run.usable:
            self._pair_row.setVisible(False)
            return
        self._pair_row.setVisible(True)
        kind, index = choice
        usable = run.usable
        if kind == "whole":
            a, b = 0, len(usable) - 1
        elif kind == "step":
            a, b = index, index + 1
        else:
            return                     # "a pair you choose" -- leave them be
        for box, at in ((self._pair_from, a), (self._pair_to, b)):
            box.blockSignals(True)
            box.setCurrentIndex(min(max(at, 0), box.count() - 1))
            box.blockSignals(False)

    def _pair_picked(self) -> None:
        """The reader set the two boxes themselves, so the chooser follows.

        Written this way round -- the boxes are the truth and the chooser
        names it -- because the alternative is two controls that can each say
        something different about one picture, and then one of them is lying.
        """
        at = _entry_at(self._picture_of, ("pair", 0))
        if at >= 0:
            self._picture_of.blockSignals(True)
            self._picture_of.setCurrentIndex(at)
            self._picture_of.blockSignals(False)
        self._draw()

    def _chosen_pair(self):
        """(path A, path B, what to call it), or None while showing the graph.

        WORKED OUT FROM THE CHOOSER ITSELF, not from whether something has
        synced the two boxes yet. The first version read the boxes, which
        meant the answer was only right AFTER a redraw -- so anything that
        set the chooser and then asked got the previous pair. That is the
        third time in this feature that "handle it where the click arrives"
        has produced a control that is right for a person and wrong for
        everything else, and it is the last: a shortcut resolves here, the
        boxes are consulted only for the entry that means "whatever they say".

        The paths come from the ENTRIES rather than from a step's names. Two
        profiles of one device very often share a stem -- printer-2019.icc
        beside printer-2019.icm is the ordinary case -- so looking a path up
        by name would compare the wrong file and print a plausible number
        under it.
        """
        run = self._run
        choice = self._picture_of.currentData()
        if choice is None or run is None or not run.usable:
            return None
        usable = run.usable
        kind, index = choice
        if kind == "whole":
            a, b = 0, len(usable) - 1
        elif kind == "step":
            a, b = index, index + 1
        else:
            a = self._pair_from.currentData()
            b = self._pair_to.currentData()
        if a is None or b is None:
            return None
        if not (0 <= a < len(usable) and 0 <= b < len(usable)):
            return None
        if a == b:
            # THE SAME PROFILE TWICE is not a comparison: every colour would
            # be exactly where it was, and a cloud of nothing-happened reads
            # as good news about a device nobody actually asked about. Said
            # out loud rather than silently falling back to the graph, which
            # would look like the control had simply not worked.
            self._trouble(
                f"Both boxes are set to {usable[a].name}. A profile compared "
                f"with itself is identical everywhere, which would draw a "
                f"picture of nothing happening — choose two different ones.")
            return None
        before, after = usable[a], usable[b]
        return before.path, after.path, f"{before.name} → {after.name}"

    def figure_now(self):
        """The picture this panel is asking for, or None if there is not
        enough to draw one.

        ONE SOURCE FOR BOTH ROUTES. The window drew it here and the host draws
        it there; two calls with almost identical argument lists is exactly
        how the save route came to be broken once before while the window
        looked perfectly fine.
        """
        import drift_series

        if not (self._run and self._run.since_first):
            return None
        return (self._cloud_figure()
                or drift_series.figure(self._run, mode=self._appearance))

    def _draw(self) -> None:
        """Put the graph in the view, writing into the window's own folder.

        THE PARENT'S TEMPORARY FOLDER, not one of this dialog's own. That
        folder is swept at startup and removed when the window closes, so a
        page written into it cannot become the kind of litter that once left
        644 folders and 27 GB behind. A second folder here would be a second
        thing to remember to clean up.
        """
        import drift_series

        # THE TWO BOXES FIRST, so that however the chooser above came to be
        # set -- clicked, restored, or set by a script -- the pair they hold
        # is the pair it names. Doing this only where the click is handled is
        # the same mistake twice over: it was made for the sentence under the
        # picture, found in a screenshot, and would have been made again here.
        # A shortcut fills them; "any two you choose" leaves them alone.
        self._sync_pair_boxes()
        self._say()
        # HOSTED, THE PICTURE IS NOT THIS PANEL'S TO DRAW. It goes to the view
        # the whole application is built around -- which is the reason for
        # moving the panel into the column in the first place.
        if getattr(self, "_hosted", False):
            drawer = getattr(self._host, "_draw_the_run", None)
            if drawer is not None:
                drawer(self)
            return
        if self._view is None:
            return
        if not (self._run and self._run.since_first):
            self._blank()
            return
        figure = self.figure_now()
        if figure is None:
            self._blank()
            return
        parent = self.parent()
        folder = getattr(parent, "_tmp", None) or Path(tempfile.gettempdir())
        target = Path(folder) / "timeline.html"
        try:
            figure.write_html(str(target), include_plotlyjs=True,
                              config={"displayModeBar": False})
            self._view.load(QUrl.fromLocalFile(str(target)))
        except OSError as exc:
            _log().warning("could not draw the timeline: %s", exc)
            self._blank()

    def _cut_changed(self, _value=None) -> None:
        """Say where the slider is, and hide the dots that fall under it.

        LIVE, NOT A REBUILD. Every step used to write a new page and load it:
        the view went black, drew again, and only settled when the drag ended.
        "dragging the hide anything under slider also blacks out the whole
        viewer and then puts everything back at once instead of only granularly
        hiding what the slider promises."

        THE PAGE ALREADY KNOWS HOW. Whoever opens a saved page gets this exact
        control, and the working half of it is handed out as window.cqHideBelow
        -- so the window's own slider drives the same code rather than a second
        copy of it, and the dots simply disappear and come back as it moves.
        """
        self._cut_says.setText(self._cut_reads())
        host = self._host if getattr(self, "_hosted", False) else None
        run_js = getattr(host, "_run_js_now", None)
        if run_js is None or self._chosen_pair() is None:
            self._draw()
            return
        run_js(f"if(window.cqHideBelow)window.cqHideBelow({self._cut_off():.2f});")

    def _cut_reads(self) -> str:
        """What the slider is doing, in words that are true at both ends.

        AND IN WORDS THAT STILL MEAN SOMETHING ON THEIR OWN. This said
        "everything", which is the object of the label to its left -- "Hide
        anything under ... everything". Reported on the saved page, where a
        narrow window wraps the two apart: "with nothing hidden there is the
        word everything in the middle of nowhere". A readout beside a control
        has to say what the state IS, not finish a sentence it may be
        separated from.
        """
        if not self._hiding_anything():
            return "nothing hidden"
        return f"ΔE {self._cut.value() / 10:.1f}"

    def _fit_cut_to(self, worst: float, smallest: float = 0.0) -> None:
        """Let the slider run across THIS pair, and no further at either end.

        A FIXED 0..5 WOULD BE MOSTLY INERT. Measured on one step of the demo
        run, whose biggest difference is ΔE 1.07: 82% of a 0..5 slider's
        travel would hide nothing further, so a reader dragging it would watch
        nothing happen for more than half its length and reasonably conclude
        the control was broken.

        AND THE BOTTOM END MATTERS TOO, which only showed up on screen. Every
        colour in a pair may have moved at least a little -- the smallest
        difference across the whole demo run is ΔE 0.65 -- so a slider
        starting at zero spends its first fifth hiding nothing while the
        label beside it reads "under ΔE 0.5". That is a control announcing an
        action it is not performing. Starting at the smallest difference makes
        the left-hand end mean "everything", truthfully, and every step from
        there take something out.

        Switched off entirely when the two are identical, because then there
        is nothing to hide at any setting.
        """
        top = int(max(worst, 0.0) * 10)
        floor = int(max(smallest, 0.0) * 10)
        usable = top > floor
        self._cut.setEnabled(usable)
        self._cut_label.setEnabled(usable)
        self._cut_says.setEnabled(usable)
        self._cut.blockSignals(True)
        self._cut.setMinimum(floor)
        self._cut.setMaximum(max(top, floor + 1))
        if self._cut.value() < self._cut.minimum():
            self._cut.setValue(self._cut.minimum())
        self._cut.blockSignals(False)
        self._cut_says.setText(
            self._cut_reads() if usable else "nothing to hide")

    def _hiding_anything(self) -> bool:
        """Whether the slider is actually leaving anything out."""
        return self._cut.isEnabled() and self._cut.value() > self._cut.minimum()

    def _cut_off(self) -> float:
        """The threshold in ΔE, or 0 when nothing is being left out."""
        return self._cut.value() / 10.0 if self._hiding_anything() else 0.0

    def _how_the_window_draws_shapes(self) -> dict:
        """The look the window uses for a shape, borrowed whole.

        THE LIGHTING AND THE TRANSPARENCY ARE NOT MINE TO INVENT. Basti, when
        this option went in: "we spent so much time to get the lighting and
        transparency right. i don't want to do it again from the ground up."

        So none of it is done again. The window keeps every render option in
        one place -- _render_options, which its live view and its saved page
        both call, for exactly this reason -- and this takes that dictionary
        and drops the handful of entries that describe the OTHER picture: the
        chart it may have open, its own drift cloud, the per-shape styles that
        name shapes this panel does not have, and the space, which is settled
        for a drift cloud and not up for choosing.

        WHAT IT KEEPS is everything that decides how a surface looks: its
        opacity, how the light falls on it, how deep the shading goes, how the
        edges are drawn, the rings inside it, the proportions of the box and
        whether the box is there at all.
        """
        host = self._host
        options = getattr(host, "_render_options", None)
        if options is None:
            return {}
        look = dict(options())
        for named_elsewhere in ("chart", "chart_look", "drift", "space",
                                "neutrals", "ideal_neutrals", "points"):
            look.pop(named_elsewhere, None)
        # PER-SHAPE SETTINGS ARE KEPT, and this is the whole of Basti's point:
        # "How it looks" can already make one shape fainter, draw it as a
        # coloured mesh, take the colour out of it, and fade where the two
        # agree or differ -- all of it tweaked over months. Dropping those
        # entries meant the run's two shells could not be styled at all, which
        # is what put three poorer controls in the run's own group for a
        # while.
        #
        # THE FIRST TWO ENTRIES ARE THE TWO SHELLS, in the order they are
        # drawn: the earlier profile, then the later one. That is exactly what
        # "the first shape" and "the second shape" mean in Set this for while
        # a run owns the picture, and the window renames those entries to the
        # profiles' own names so nobody has to guess.
        # READ FROM THE WINDOW'S OWN TABLE, not from the list it builds for
        # its open files. That list has one entry per FILE, so with a run and
        # nothing else open it is empty -- and every per-shape setting landed
        # in a dictionary nobody read. Measured: "printer-2019 at 85%" left
        # both shells at 0.2.
        #
        # Entry 0 and entry 1 are what "Set this for" calls the first and the
        # second shape, which is what those two entries are renamed to while a
        # run owns the picture.
        own = getattr(host, "_per_shape", {}) or {}
        look["per_shape"] = [dict(own.get(0, {})), dict(own.get(1, {}))]
        # AND WHETHER EACH IS A SURFACE OR A MESH, which is not part of the
        # render options at all: the window works its styles out beside the
        # shapes themselves, in _scene_contents. Without them the two shells
        # were solid whatever the choosers said -- "printer-2019 as a mesh"
        # changed nothing at all.
        chosen = (getattr(host, "_style_mine", None),
                  getattr(host, "_style_second", None))
        if all(chosen):
            look["styles"] = [box.currentData() for box in chosen]
        return look

    def _name_in_run(self, path) -> str:
        """What a profile in this run is CALLED, and never the same as another.

        A RUN IS ONE DEVICE OVER TIME, so two of its profiles sharing a file
        name is not a mistake -- it is what happens when the same printer is
        profiled into a folder per month. Both shells were then called
        the-printer, "Set this for" offered the same words twice, and fading
        the first faded both:

            surfaces   the-printer#0, the-printer#2
            faded      the-printer#0, the-printer#2

        The DATE is what tells them apart here, which is why the rows in the
        list carry it, so the date is what is added -- and only where a name
        is shared. Everywhere else the plain name stays.
        """
        path = Path(path)
        stem = path.stem
        run = getattr(self, "_run", None)
        entries = list(getattr(run, "entries", []) or [])
        same = [e for e in entries if Path(getattr(e, "path", "")).stem == stem]
        if len(same) < 2:
            return stem
        for entry in entries:
            if Path(getattr(entry, "path", "")) == path:
                dated = getattr(entry, "dated", "")
                return f"{stem} ({dated})" if dated else stem
        return stem

    def _shells_for(self, path_a, path_b):
        """The two profiles as shapes, built the way the window builds shapes.

        NOT A SECOND WAY OF MAKING A GAMUT, and that is the whole of this
        method. Basti, on seeing the option go in: "we spent so much time to
        get the lighting and transparency right. i don't want to do it again
        from the ground up" -- and he was right to say it, because the first
        version of this did exactly that: it took the 9x9x9 grid the
        comparison already had and hulled it here.

        TWO THINGS WERE WRONG WITH THAT, and both are invisible in a
        screenshot:

          * ACCURACY. The comparison samples 729 points because that is
            plenty for asking how far two profiles disagree. The window builds
            a SHAPE from ArgyllCMS where it can, and from a 17-step grid --
            4,913 points -- where it cannot. A hull of 729 is a coarser
            surface: the same shape with its corners rounded off.
          * EVERYTHING ELSE THE WINDOW KNOWS. How the edge is followed, which
            white point, which space: all of it is chosen in the column and
            all of it was being ignored here.

        So this asks the window for the shape, through the same call the
        window uses when a file is opened.

        AND IT IS REMEMBERED, keyed on the file and the time it was written,
        because this runs on every redraw -- every drag of the threshold
        slider -- and building a gamut from ArgyllCMS is the slowest thing
        this application does.
        """
        host = self._host
        builder = getattr(host, "_build_one", None)
        if builder is None:
            return []
        made = []
        for path in (Path(path_a), Path(path_b)):
            try:
                key = (str(path), path.stat().st_mtime_ns,
                       host._white.currentData(), "lab",
                       host._mode.currentData())
            except OSError:
                return []
            if key not in self._shell_cache:
                try:
                    # ALWAYS IN LAB, WHATEVER THE WINDOW IS DRAWING IN. The
                    # run's picture is a cloud of ΔE2000 differences, which is
                    # a Lab measurement, and its shells have to stand in the
                    # same space or the axes are labelled for one and the
                    # shapes built for the other. The window says so outright
                    # rather than drawing it: "asked to label the axes 'lab'
                    # while the shapes were built in 'luv'". Found by the
                    # control sweep, which changed the space with a run open.
                    gamut, _measured = builder(path, space="lab")
                except Exception as exc:   # noqa: BLE001 — a view must not fall
                    _log().warning("could not build the shape of %s: %s",
                                   path, exc)
                    self._trouble(
                        "The shapes could not be worked out for this pair, so "
                        "only the colours are drawn.")
                    return []
                # ONE PAIR AT A TIME IS ALL THAT IS EVER WANTED, and a gamut
                # is a few megabytes of triangles; a cache that grows with the
                # run would hold a printer's whole history in memory.
                if len(self._shell_cache) > 4:
                    self._shell_cache.clear()
                self._shell_cache[key] = gamut
            made.append((self._name_in_run(path), self._shell_cache[key]))
        return made

    def _cloud_figure(self, split_for_fading: bool = False):
        """The chosen step as a heat-map, or None while the graph is showing.

        NEVER RAISES, because it is on the redraw path: an unreadable pair
        must leave the reader looking at the graph and a sentence, not at a
        window that has fallen over. The one thing it will not do is draw a
        picture of a comparison that does not mean anything -- two profiles
        read through different tables answer different questions, and a cloud
        of that difference would look exactly like drift.
        """
        pair = self._chosen_pair()
        if pair is None:
            return None
        from ti3gamut import build_figure, compare_profiles

        path_a, path_b, spans = pair
        try:
            d = compare_profiles(path_a, path_b, steps=self.GRID)
        except Exception as exc:      # noqa: BLE001 — a view must not crash
            _log().warning("could not compare %s with %s: %s",
                           path_a, path_b, exc)
            self._trouble(f"These two could not be compared: {exc}")
            return None
        if not d.comparable:
            self._trouble(
                f"{spans} were not read the same way — one through "
                f"{d.table_a}, the other through {d.table_b}. Those answer "
                f"different questions, so the difference between them would "
                f"be mostly that rather than drift, and a picture of it would "
                f"look exactly like a device that had moved.")
            return None
        self._trouble("")
        # THE PICTURE SAYS WHICH PAIR IT IS. A cloud that names neither
        # profile is a picture of nothing in particular the moment it is saved
        # or screenshotted, and this window can show several of them.
        axis = self._coloured_by.currentData()
        if axis:
            asks = ("the colour it is heading for" if axis == "toward"
                    else DIRECTIONS[axis][0])
            moved = d.moved
            if moved is None:          # a comparison from before lab_b was kept
                axis = None
        split = self._by_family.isChecked()
        # THE TWO SHAPES, when they have been asked for. Built through the
        # window's own builder and drawn with the window's own look; see
        # _shells_for and _how_the_window_draws_shapes.
        shells = self._shells_for(path_a, path_b) \
            if self._with_shapes.isChecked() else []
        # THE SLIDER FOLLOWS THIS PAIR. Set before the picture is built, so a
        # reader who chose a step with a small worst difference is not handed
        # a control whose right-hand half does nothing.
        import numpy as _np
        self._fit_cut_to(d.worst, float(_np.min(d.deltas)))
        cut = self._cut_off()
        look = self._how_the_window_draws_shapes() if shells else {}
        # WITH NO SHELLS THERE IS NO LOOK TO INHERIT, and the box is still a
        # thing the reader can switch off.
        if "grid" not in look:
            host_grid = getattr(getattr(self, "_host", None), "_grid_on", None)
            look["grid"] = (host_grid.isChecked() if host_grid is not None
                            else True)
        if "camera" not in look:
            # WHERE THE READER IS LOOKING FROM, whether or not this picture
            # has shapes in it. With no shells there is no look to inherit,
            # and a cloud on its own is exactly the picture somebody turns to
            # find an angle they like.
            asks = getattr(getattr(self, "_host", None), "_camera_now", None)
            look["camera"] = asks() if asks is not None else None
        # WHAT THIS PICTURE DECIDES FOR ITSELF is named below as well, and
        # Python refuses the same argument twice: a drift cloud is always
        # drawn in Lab and always in the window's own light or dark.
        #
        # THE BOX IS NOT ONE OF THOSE. It was, and that made "Show the box and
        # its grid" a switch that did nothing to this picture while still
        # showing itself ticked or unticked -- a control saying something
        # untrue, which is worse than one that does nothing. Found by the
        # audit that compares every control with the picture: "says False,
        # draws True".
        for mine in ("mode", "space"):
            look.pop(mine, None)
        if axis == "toward":
            # NOT "IN LAB UNITS": this one is not a measurement along an axis,
            # it is a name. Saying "in Lab units" over a picture of six named
            # destinations would be the caption describing a different view.
            return build_figure(
                shells, f"Where {spans} is heading — the family each colour is "
                    f"moving toward",
                mode=self._appearance, space="lab", **look,
                split=split_for_fading,
                drift=(d.lab_a, moved, f"heading for: {spans}", "toward",
                       split, cut, d.deltas))
        if axis:
            return build_figure(
                shells, f"Which way {spans} moved — {asks}, in Lab units",
                mode=self._appearance, space="lab", **look,
                split=split_for_fading,
                drift=(d.lab_a, moved, f"{asks}: {spans}", axis, split, cut,
                       d.deltas))
        return build_figure(
            shells, f"Where {spans} disagree — ΔE2000, biggest {d.worst:.2f}, "
                f"average {d.average:.2f}",
            mode=self._appearance, space="lab", **look,
            split=split_for_fading,
            drift=(d.lab_a, d.deltas, f"how far it moved: {spans}", None,
                   split, cut))

    def _trouble(self, said: str) -> None:
        """Say why a cloud could not be drawn, under the ones already there.

        ADDED TO THE RUN'S OWN COMPLAINTS rather than replacing them: "one of
        these could not be read" and "this pair cannot be compared" are two
        different things to know, and the second arriving must not take the
        first off the screen.
        """
        if not said:
            return
        already = list(getattr(self, "_grumbles", []))
        if said not in already:
            self._complaints.setText("\n\n".join(already + [said]))

    def _paint_view(self) -> None:
        """Give the view the page's own colour, so it never flashes white."""
        if self._view is None:
            return
        from ti3gamut import SCENE_COLOURS
        page = SCENE_COLOURS["light" if self._appearance == "light"
                             else "dark"]["page"]
        self._view.setStyleSheet(f"background: {page};")
        self._view.page().setBackgroundColor(QColor(page))

    def _blank(self) -> None:
        """Empty the graph AND everything said about it.

        WORDS OUTLIVE THE PICTURE UNLESS SOMETHING TAKES THEM AWAY. Removing
        every profile emptied the graph and left the family report sitting
        underneath it, naming two files that were no longer open and reporting
        how their reds had moved. It looked like a result. Found by clearing
        the window in a driver and reading what was still on it, which is not
        something a test that never empties anything can notice.
        """
        if self._view is not None:
            self._view.setHtml("")
        # HOSTED, THE PICTURE IS NOT OURS TO EMPTY -- it belongs to the window
        # this panel sits in, and it must go back to whatever else is open
        # rather than being wiped. Measured on the first drive: "Remove them
        # all" left the run's picture on screen, the note still claiming the
        # view was showing a run, and a file open behind it that nothing would
        # draw.
        if getattr(self, "_hosted", False):
            release = getattr(self._host, "_release_the_picture", None)
            if release is not None:
                release()
        self._families.setText("")
        self._families_note.setText("")

    def look(self, appearance: str) -> None:
        """Follow the window's light/dark setting."""
        if appearance != self._appearance:
            self._appearance = appearance
            self._paint_view()
            self._draw()

    # --- taking it away ----------------------------------------------------

    def write_page(self, target, *, carry_viewer: bool = True,
                   controls: bool = True, offer=None,
                   numbers: bool = True, colours: str = None) -> str:
        """Write whatever this panel is showing as a page, and say what it is.

        ONE WRITER, TWO CALLERS. This panel's own Save button used to write
        the page itself, and the main window's Save wrote a different kind
        entirely -- so the same words on two buttons produced two files with
        different capabilities, and the run's had no reader controls at all.
        Reported: "can those save as a webpage buttons not be unified? one for
        both? and if i am correct the one for the run until now did not allow
        to choose the controls the user would have on the webpage".

        WHAT THE OPTIONS MEAN HERE. A drift cloud is a 3D scene and takes all
        of them -- the viewer travelling inside, the reader's control strip,
        which controls are offered. THE GRAPH IS A LINE CHART and takes only
        two: whether the viewer travels, and whether the words go with it. The
        rest are not silently ignored; the caller is told which page it is
        getting, see `shows_a_cloud`.
        """
        import drift_series
        from ti3gamut import _write_dark_html

        target = Path(target)
        pair = self._chosen_pair()
        if pair is None:
            first = self._run.usable[0].name if self._run.usable else "device"
            figure = drift_series.figure(
                self._run, mode=(colours or self._appearance),
                title=f"How far {first} has moved")
            target.write_text(self.page_html(figure, carry=carry_viewer,
                                             words=numbers,
                                             colours=colours),
                              encoding="utf-8")
            return ("the sentence explaining what the lines do and do not "
                    "mean is saved with it")
        # SPLIT WHEN THERE ARE TWO SHAPES IN IT, so the reader's "where they
        # agree" and "where they differ" sliders have two halves to fade
        # between. A trace that was never written into the page cannot be
        # faded by anybody, which is why the main window's save does exactly
        # this and for the same reason. It is a property of the FIGURE, not of
        # the writer, so the picture is rebuilt for the page it is about to
        # become rather than the screen it came from.
        figure = self._cloud_figure(split_for_fading=self.shows_two_shapes())
        if figure is None:
            raise ValueError("that pair could not be compared")
        # THE SAME WRITER THE MAIN WINDOW USES, so a cloud saved from here
        # turns, zooms and carries its controls exactly like one saved from
        # there. Two writers for one kind of page is how the two come to
        # behave differently.
        # SPLIT WHEN THERE ARE TWO SHAPES IN IT, so the reader's "where they
        # agree" and "where they differ" sliders have two halves to fade
        # between. A trace that was never written into the page cannot be
        # faded by anybody, which is why the main window's save does the same
        # thing for the same reason.
        # AND THE READER'S WHOLE STRIP, which this page never had. The
        # controls along the bottom -- turning, zooming, the four fixed
        # views, the shape switches, the two fade sliders -- are built from
        # the movement settings, and passing none meant building none. A page
        # saved from here arrived with the ΔE threshold and nothing else,
        # while the same picture saved from the window arrived with all of
        # it. Found by opening both in a browser and listing what each built.
        spin = None
        asks = getattr(self._host, "_spin_options", None)
        if asks is not None:
            try:
                spin = asks()
            except Exception:             # noqa: BLE001 — a save must not fall
                spin = None
        _write_dark_html(figure, target, colours or self._appearance,
                         spin=spin,
                         notes=self._cloud_notes(pair) if numbers else "",
                         carry_viewer=carry_viewer, controls=controls,
                         offer=offer)
        return ("what the colours mean, and what the numbers do not tell you, "
                "are saved with it")

    def shows_two_shapes(self) -> bool:
        """Whether the picture has both profiles drawn as shapes in it.

        WHAT THE FADE NEEDS. "Where they agree" and "where they differ" fade
        one shape against the other, so they mean something exactly when
        there are two -- and the run's cloud has none unless the reader has
        asked for them. Basti: "the learnings from the transparency, where
        they agree, where they don't agree sliders should also be inherited
        by this so those options can be offered by us safely".
        """
        return bool(self._with_shapes.isChecked() and self.shows_a_cloud())

    def shows_a_cloud(self) -> bool:
        """Whether the picture is a 3D cloud rather than the line graph.

        The saved page's options are not the same for the two, and a dialog
        offering controls that cannot exist is worse than one that says so.
        """
        return self._chosen_pair() is not None

    def _on_save(self) -> None:
        """Save WHATEVER IS SHOWING, which is the only honest thing it can do.

        A Save button that always wrote the graph would quietly disagree with
        the screen the moment somebody chose a step -- they would press it
        looking at a cloud and get a line chart, and only find out later.
        """
        import drift_series

        parent = self.parent()
        first = self._run.usable[0].name if self._run.usable else "device"
        pair = self._chosen_pair()
        stem = (f"{first}-over-time" if pair is None
                else f"{_clean_stem(pair[2])}-where-it-moved")
        # THE SAME QUESTIONS EVERY OTHER SAVE ASKS, and this one never asked
        # them. It went straight to the file chooser and wrote the page with
        # every default, so a run always travelled with the viewer inside it:
        # 4.9 MB, and no way to ask for the small one. Every other page in
        # this application offers the choice -- about five megabytes and it
        # works with no network at all, or forty kilobytes and it fetches the
        # viewer the first time it is opened -- and a run is the page most
        # likely to be sent to somebody, because it is the one with a story.
        #
        # Found by driving the real window rather than by reading this.
        #
        # AND THE DIALOG IS TOLD WHAT KIND OF PAGE IT IS. It has known how to
        # do that since somebody asked for it -- "the export dialog should
        # only allow to choose control options ... applicable for what is
        # exported" -- so a line graph is not offered four ways to turn a
        # camera it does not have. `shows_a_cloud` is the panel's own answer
        # to that question and was already written for this.
        cloud = self.shows_a_cloud()
        options = WebPageDialog(
            parent, for_a_cloud=cloud,
            shows={"two_shapes": self.shows_two_shapes(),
                   "surfaces": cloud, "flat": False, "camera": cloud,
                   "fade": cloud and self.shows_two_shapes()})
        if not options.exec():
            return
        chosen = options.choices()
        chooser = parent._file_dialog(
            "Where should the page go?", QFileDialog.FileMode.AnyFile,
            "Web page (*.html)", f"{stem}.html", profiles=False)
        chooser.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        chooser.setDefaultSuffix("html")
        if not chooser.exec():
            return
        target = Path(chooser.selectedFiles()[0])
        try:
            said = self.write_page(
                target,
                carry_viewer=chosen.get("carry_viewer", True),
                controls=chosen.get("controls", True),
                numbers=chosen.get("numbers", True),
                offer=chosen.get("offer"),
                colours=chosen.get("colours"))
        except ValueError:
            Notice.warn(self, "There is nothing to save",
                        "That pair could not be compared, so there is no "
                        "picture to write.")
            return
        except OSError as exc:
            Notice.warn(self, "That could not be saved", str(exc))
            return
        Notice.say(self, "Saved",
                   f"Written to\n{target}\n\nIt opens in any browser, and "
                   f"{said}.")

    def _cloud_notes(self, pair) -> str:
        """The words that travel with a saved cloud.

        THE CAVEAT GOES IN THE FILE, not just on the screen it came from. A
        picture outlives the window that explained it, and this one is the
        kind people trust more than they should.
        """
        _a, _b, spans = pair
        words = (f"Where {spans} disagree.\n\n"
                 f"Every colour is drawn where the earlier profile puts it, "
                 f"painted by how far the later one sends it instead, in "
                 f"ΔE2000. Below 1 nobody can see the difference; above 3 "
                 f"anybody can. The scale is fixed rather than stretched to "
                 f"fit, so this can be held against another one of these.\n\n"
                 f"What it does not tell you: this is how far apart the two "
                 f"PROFILES are, not how far the device drifted. Each profile "
                 f"is one day's measurements of one chart, so chart fade and "
                 f"any change in how they were built are inside these numbers "
                 f"too.")
        # THE FAMILY REPORT TRAVELS WITH THE PICTURE, for the same reason the
        # caveat above it does: the page is the thing that gets sent to
        # somebody else, and it is the sentences rather than the cloud that
        # they will quote. A page that showed the cloud and kept the summary
        # back would be the least useful half of the answer.
        said = self._family_report(pair)
        if said is not None:
            words += f"\n\n{said[0]}\n\n{said[1]}"
        return words

    def _on_table(self) -> None:
        parent = self.parent()
        first = self._run.usable[0].name if self._run.usable else "device"
        chooser = parent._file_dialog(
            "Where should the table go?", QFileDialog.FileMode.AnyFile,
            "Table (*.csv)", f"{first}-over-time.csv", profiles=False)
        chooser.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        chooser.setDefaultSuffix("csv")
        if not chooser.exec():
            return
        target = Path(chooser.selectedFiles()[0])
        try:
            with open(target, "w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerows(self.rows())
        except OSError as exc:
            Notice.warn(self, "That could not be saved", str(exc))
            return
        Notice.say(self, "Saved", f"Written to\n{target}")

    def page_html(self, figure, *, carry: bool = True,
                  words: bool = True, colours: str = None) -> str:
        """The saved page: the graph, then the words, both on the first screen.

        WRITTEN HERE RATHER THAN LEFT TO THE DRAWING LIBRARY, and the reason is
        a measured one. Its own full-page output fills the viewport — measured
        at 96% to 99% of the first screen across ten window sizes in both
        engines — which puts everything underneath below the fold. The graph
        would have arrived without the sentence that says what it does not
        mean, on every screen, which is precisely the failure this feature is
        most exposed to: a rising line read as proof a device is failing.

        So the graph is given a bounded share of the screen and the words go
        under it. `check_layout.py` holds the picture between 55% and 85% of
        the first screen for every page in this project, and this is now one
        of them rather than an exception to them.
        """
        import drift_series

        # THE CAPTION SCRIPT TRAVELS WITH EVERY PAGE, and this one is written
        # here by hand rather than by ti3gamut's writer -- which is how four
        # published pages came to have no such script at all while the audit
        # that watches for exactly this said "Clean". It watches for this one
        # now too.
        from ti3gamut import _CAPTION_JS, SCENE_COLOURS
        # THE CHOICE FIRST, THE WINDOW SECOND. This page — the run's graph —
        # was the one route that ignored "what colours should it open in",
        # because it is written here rather than by the shared writer. Caught
        # by an audit that read the mode back out of the saved file and found
        # "dark" in a page saved to follow the reader.
        look = colours or self._appearance
        c = SCENE_COLOURS["light" if look == "light" else "dark"]
        # THE CAVEAT IS NOT OPTIONAL, and *words* does not reach it. Leaving
        # the numbers out is a reasonable thing to want -- a picture for a
        # slide. Leaving out the sentence that says a rising line is just as
        # consistent with charts ageing as with a device failing is not: that
        # sentence exists because this is the picture in the whole application
        # most likely to be believed too readily.
        #
        # THE VIEWER TRAVELS OR IT DOES NOT, and that is the reader's
        # choice on the way out, exactly as it is for every other page this
        # application writes: about five megabytes and it works with no
        # network at all, or forty kilobytes and it fetches the viewer the
        # first time it is opened.
        body = figure.to_html(full_html=False,
                              include_plotlyjs=True if carry else "cdn",
                              config={"displayModeBar": False},
                              default_height="100%", div_id="timeline")
        first = self._run.usable[0].name if self._run.usable else "this device"
        # AND THE TITLE SHRINKS WITH THE WINDOW, exactly as it does on every
        # page ti3gamut writes. The caption is one line of SVG text that
        # cannot wrap and is the same width whatever the screen, so on a phone
        # the end of it falls off -- measured at 390px before this: 463px of
        # title in a 390px page, the last dozen characters gone, and no
        # sideways scroll to warn anybody because the SVG simply clips.
        #
        # THE SAME OMISSION THIS METHOD'S DOCSTRING ALREADY WARNS ABOUT: the
        # caption script is written here by hand rather than by ti3gamut's
        # writer, "which is how four published pages came to have no such
        # script at all while the audit that watches for exactly this said
        # Clean". _write_dark_html emits these two media queries; this writer
        # did not, so a scene page kept every word on a phone and a graph page
        # did not.
        #
        # Measured with them in place, on a page the application really saves:
        # 13px -> 11px -> 10px, and all 68 characters of "How far <device> has
        # moved -- the biggest difference at each step" inside a 390px page,
        # 30px clear of the edge.
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>How far {_escape(first)} has moved — {APP_NAME}</title>
<style>
 html {{ height:100%; }}
 body {{ margin:0; padding:0; min-height:100%; background:{c['page']};
         color:{c['text']}; display:flex; flex-direction:column;
         font:14px/1.65 -apple-system, system-ui, "Segoe UI", Roboto,
              Helvetica, Arial, sans-serif; }}
 /* THE GRAPH TAKES MOST OF THE SCREEN AND NOT ALL OF IT. 68vh leaves the
    verdict and the caveat visible without scrolling on every size checked,
    and the floor stops it collapsing on a window dragged very short. */
 .picture {{ flex:0 0 auto; height:68vh; min-height:260px; width:100%; }}
 .words {{ flex:1 1 auto; max-width:46em; margin:0 auto; padding:1.2em 1.5em 3em; }}
 .words p {{ margin:0 0 .9em; }}
 .verdict {{ font-size:15px; font-weight:600; }}
 .caveat {{ opacity:.82; }}
 /* One family per line, so the list can be read down and pasted out. No
    bullets: these are sentences, not items to choose between. */
 .families {{ list-style:none; margin:0 0 .9em; padding:0; }}
 .families li {{ margin:0 0 .25em; }}
 @media (max-width:520px) {{ .picture {{ height:60vh; }} }}
 @media (max-width:820px) {{ .gtitle {{ font-size:11px !important; }} }}
 @media (max-width:480px) {{ .gtitle {{ font-size:10px !important; }} }}
</style></head><body>
<div class="picture">{body}</div>
<div class="words">
{f'<p class="verdict">{_escape(drift_series.verdict(self._run))}</p>' if words else ''}
<p class="caveat"><b>What this does not tell you.</b> These lines show how far
apart the <b>profiles</b> are, not how far the device drifted. Each profile
records one day's measurements of one chart, so if the charts faded between
them, or they were built differently, that is inside these numbers too. A line
that climbs steadily is just as consistent with charts ageing as with a device
drifting, and no arithmetic can separate the two.</p>
<p class="caveat">The numbers are ΔE2000. Below 1 nobody can see the
difference; above 3 anybody can.</p>
{self._families_html() if words else ''}</div>
<script>{_CAPTION_JS}</script></body></html>
"""

    def _family_rows(self) -> list:
        """The family report as spreadsheet rows, first profile against last.

        The same numbers the panel and the saved page show, from the same
        call, so a table can never quote a figure the window does not.
        """
        import gamutview

        run = self._run
        if run is None or len(run.usable) < 2:
            return []
        try:
            from ti3gamut import compare_profiles
            d = compare_profiles(run.usable[0].path, run.usable[-1].path,
                                 steps=self.GRID)
            if not d.comparable or d.lab_a is None:
                return []
            rows = gamutview.family_drift(d.lab_a, d.lab_b)
        except Exception:                                  # noqa: BLE001
            return []

        spans = f"{run.usable[0].name} → {run.usable[-1].name}"
        out = [(f"colour family ({spans})", "what it did", "colours it stands on")]
        for r in rows:
            if not r.patches:
                # SAID RATHER THAN OMITTED. A family missing from the table
                # reads as one that was not measured; this one was measured
                # and had nothing in it, which is a different fact.
                out.append((r.name, "nothing in this family", "0"))
                continue
            what = "stayed the same" if not r.changed else r.toward
            if r.changed and r.also:
                what += f", also {r.also}"
            if r.changed and not r.certain:
                what += " (not certain — no bigger than its own scatter)"
            out.append((r.name, f"ΔE {r.mean_de:.2f} {what}", str(r.patches)))
        borderline = sum(r.near_boundary for r in rows)
        out.append(("where the line is",
                    f"families centred every 45–75° of hue; anything under "
                    f"chroma {gamutview.NEUTRAL_CHROMA:.0f} is a grey",
                    f"{borderline} sat within "
                    f"{gamutview.BOUNDARY_DEGREES:.0f}° of a line and could "
                    f"have gone either way"))
        return out

    def _families_html(self) -> str:
        """The family report, for the saved graph page.

        THE PAGE IS THE THING THAT GETS SENT. Somebody saves this to show a
        colleague or a paper supplier, and what they will quote is the list of
        sentences, not the line chart. Keeping it on screen only would send
        the half that needs interpreting and hold back the half that does not.

        It describes the FIRST profile against the LAST, which is the same
        comparison the verdict above it is about.
        """
        said = self._family_report(None)
        if said is None:
            return ""
        shown, note = said
        head, _, body = shown.partition("\n")
        lines = "".join(f"<li>{_escape(line)}</li>"
                        for line in body.splitlines() if line.strip())
        return (f'<p class="verdict">{_escape(head)}</p>'
                f'<ul class="families">{lines}</ul>'
                f'<p class="caveat">{_escape(note)}</p>')

    def rows(self) -> list:
        """The run as table rows, caveat included.

        Separated from the saving so it can be checked without a file dialog,
        and so the two exports cannot drift apart in what they claim.
        """
        import drift_series

        run = self._run
        if run is None:
            return []
        out = [("profile", "made on", "read through"),
               *[(e.name, e.dated, e.table or "—") for e in run.entries]]
        out.append(("", "", ""))
        out.append(("step", "ΔE2000 since the first",
                    "ΔE2000 since the one before"))
        for i, step in enumerate(run.since_first):
            previous = (run.since_previous[i].worst
                        if i < len(run.since_previous) else "")
            out.append((step.after, f"{step.worst:.2f}",
                        f"{previous:.2f}" if previous != "" else ""))
        # WHICH FAMILIES MOVED, AS ROWS RATHER THAN AS A PARAGRAPH, because
        # this is the file that goes into a spreadsheet: a reader wants to
        # sort by how far each family went, and a sentence in one cell cannot
        # be sorted. The patch count keeps its own column for the same reason
        # it is never left off the sentence -- a family of four and one of
        # four hundred must not sort as equals.
        families = self._family_rows()
        if families:
            out.append(("", "", ""))
            out.extend(families)

        out.append(("", "", ""))
        out.append(("in short", drift_series.verdict(run), ""))
        out.append(("what this is",
                    "how far apart the PROFILES are",
                    "NOT how far the device drifted — chart fade and any "
                    "change in how each profile was built are in these "
                    "numbers too"))
        out.append(("ordered by", run.ordered_by, ""))
        for complaint in run.complaints:
            out.append(("note", complaint, ""))
        return out


def _escape(text: str) -> str:
    """The few characters that would otherwise end a tag early."""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _entry_at(combo, wanted):
    """Where *wanted* sits in a combo box, comparing by VALUE.

    NOT `findData`, and that is a measured correction rather than a
    preference. Qt compares the stored item data as QVariants, and for a
    Python object it has no way to do that except by identity -- so
    `findData(("whole", 0))` finds an item holding ("whole", 0) only when the
    two tuples happen to be the same object. They are when both literals sit
    in one code object, which is exactly what a small isolated check does, and
    they are not across modules. Measured on the real window: the item was at
    index 5 and findData returned -1.

    What that cost: the timeline rebuilt its chooser whenever the run changed
    and used findData to put the reader back on what they had been looking at.
    It never found it, so every add or remove quietly threw them back to the
    graph. The check that should have caught it read the fallback as the
    correct answer to a different question.

    Returns -1 when it is not there, like the method it replaces.
    """
    for i in range(combo.count()):
        if combo.itemData(i) == wanted:
            return i
    return -1


def _clean_stem(said: str) -> str:
    """A suggested file name, from a sentence naming what is in the picture.

    "printer-2019 → printer-2021" is a good thing to call a file and a bad
    thing to put in one: an arrow is not a character every file system and
    every mail client agrees about, and a leading or trailing separator makes
    a name that looks broken. So the parts are kept and everything between
    them becomes a single hyphen.

    Capped, because a run of profiles with long descriptive names produces a
    long sentence, and some file systems still stop at 255 bytes -- a name
    that cannot be written is a save that fails at the last step.
    """
    kept = "".join(ch if (ch.isalnum() or ch in "-_.") else " " for ch in said)
    return "-".join(kept.split())[:120] or "comparison"


class Notice(QDialog):
    """The window's own message box, instead of the system one.

    A native QMessageBox looked wrong here for three reasons, all visible at
    once in a single screenshot of the reset question:

    * Its heading text is drawn bold *and* the whole body inherits that, so
      five sentences arrive shouting with nothing standing out from anything
      else.
    * Its standard "?" glyph is painted for the system appearance, not this
      window's, so in dark mode it was a near-black question mark on a
      near-black panel — a smudge.
    * On macOS the frame follows the *system* appearance while the panel
      follows *this window's* setting, so a dark dialog wore a light title
      bar.

    This draws the panel itself: a real heading, an unbolded body under it,
    and the same buttons the rest of the window uses. Frameless, so the title
    bar cannot contradict the appearance the user chose. Escape still cancels,
    because QDialog rejects on Escape and the cancelling button is the one
    that carries the default.
    """

    #: How wide every one of these is, and the gap either side of the text.
    #: Named rather than repeated so the label can be sized from them: the two
    #: numbers have to agree, and they did not.
    WIDTH = 470
    SIDE = 26
    #: The card's own border, from `QFrame#noticeCard { border: 1px solid … }`
    #: in the stylesheet. It is drawn INSIDE the 470, so the text has two
    #: points less room than the arithmetic suggests — which is exactly two
    #: points more than it had, and enough to clip the buttons. Kept here
    #: beside the other two so the sum is written down once; if that rule
    #: changes, this changes with it.
    BORDER = 1

    def __init__(self, parent, title: str, body: str, *, rich: bool = False,
                 ok: str = "OK", cancel: str | None = None,
                 scroll: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setObjectName("notice")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(self)
        card.setObjectName("noticeCard")
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(Notice.SIDE, 22, Notice.SIDE, 20)
        lay.setSpacing(0)
        # THE TEXT IS TOLD ITS WIDTH RATHER THAN ASKED FOR ONE, and without
        # this a long message silently breaks the dialog.
        #
        # A word-wrapping QLabel does not ask for the width its longest line
        # needs; it asks for a width that keeps the block from becoming absurdly
        # tall, so the MORE text it holds the WIDER it wants to be, whatever the
        # lines say. This window is a fixed 470 points across, so that request
        # cannot be met, and the layout quietly overflows: measured at 610
        # points wanted against 470 given, which cut the right-hand end off both
        # buttons. Nothing warns about it -- the dialog simply comes up wrong.
        #
        # Fixing the label's width instead makes the wrap point the real one and
        # lets heightForWidth do the rest, so the box grows downwards as it
        # always should have. Found by measuring a message that had grown by a
        # dozen lines; every earlier one fitted by luck rather than by design.
        inner = Notice.WIDTH - 2 * (Notice.SIDE + Notice.BORDER)

        head = QLabel(title, card)
        head.setObjectName("noticeTitle")
        head.setFixedWidth(inner)
        head.setWordWrap(True)
        head.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Minimum)
        lay.addWidget(head)
        lay.addSpacing(10)      # heading to body: they belong together

        # A plain wrapping label, NOT the WrappedLabel used in the side panel.
        # That one claims MinimumExpanding height so it survives a scroll area
        # whose width keeps changing; in a dialog of fixed width it simply
        # grows, and the message ends up floating in the middle of a window
        # twice the height it needs.
        text = QLabel(body, card)
        text.setObjectName("noticeBody")
        text.setFixedWidth(inner)
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Minimum)
        if rich:
            text.setTextFormat(Qt.TextFormat.RichText)
        text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        if scroll:
            # Only the glossary is long enough to need this; everything else
            # would gain a scroll bar it never uses.
            area = QScrollArea(card)
            area.setWidgetResizable(True)
            # ROOM FOR THE SCROLL BAR ITSELF. It is drawn inside the viewport,
            # so a label sized to the full inner width is wider than what is
            # left for it, and the reader gets a sideways scroll bar as well —
            # on the one message in the application long enough to need this.
            area.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
            text.setFixedWidth(inner - area.verticalScrollBar().sizeHint().width())
            area.setWidget(text)
            area.setMinimumHeight(360)
            lay.addWidget(area, 1)
        else:
            lay.addWidget(text)

        lay.addSpacing(20)      # body to buttons: a clear break before acting
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        if cancel is not None:
            no = QPushButton(cancel, card)
            no.setObjectName("secondary")
            no.clicked.connect(self.reject)
            buttons.addWidget(no)
            no.setDefault(True)          # Enter cancels; the safe way round
        yes = QPushButton(ok, card)
        yes.clicked.connect(self.accept)
        buttons.addWidget(yes)
        if cancel is None:
            yes.setDefault(True)
        lay.addLayout(buttons)
        # NEVER NARROWER THAN ITS OWN BUTTONS, whatever the design says.
        #
        # 470 is a deliberate measure -- it keeps every message recognisably
        # the same window and the lines short enough to read. It is also a
        # number chosen on one machine. On Windows the same two buttons ask
        # for 632 points, so "Open the download page" ran 134 points past the
        # right-hand edge: the dialog whose whole purpose is offering somebody
        # that button clipped it, on the platform I was not looking at.
        #
        # So the width is a floor rather than a fixed size. Almost every
        # message keeps exactly the 470 it always had; the few that cannot fit
        # their own actions grow instead of hiding them, which is the only
        # answer that is right on every platform at once.
        wanted = buttons.sizeHint().width() + 2 * (Notice.SIDE + Notice.BORDER)
        width = max(Notice.WIDTH, wanted)
        inner = width - 2 * (Notice.SIDE + Notice.BORDER)
        head.setFixedWidth(inner)
        text.setFixedWidth(inner if not scroll else
                           inner - area.verticalScrollBar().sizeHint().width())
        # A width chosen before the text is laid out, not after. A dialog that
        # sizes itself to its longest sentence gives a different shape for
        # every message; a fixed measure keeps them all recognisably the same
        # window and keeps the lines short enough to read comfortably.
        self.setFixedWidth(width)
        # Fixed to exactly what the content needs. With only a minimum, the
        # dialog opened taller than its text and QVBoxLayout handed the spare
        # height to the labels, which pushed the heading away from the body it
        # introduces and left a band of nothing under both.
        lay.setSizeConstraint(
            QVBoxLayout.SizeConstraint.SetMinimumSize if scroll
            else QVBoxLayout.SizeConstraint.SetFixedSize)

    # The three shapes the window actually uses, named for what they do.
    @staticmethod
    def say(parent, title: str, body: str) -> None:
        """Tell the user something that needs no decision."""
        Notice(parent, title, body).exec()

    @staticmethod
    def warn(parent, title: str, body: str) -> None:
        """Explain something that did not work. Never a bare error string."""
        Notice(parent, title, body).exec()

    @staticmethod
    def ask(parent, title: str, body: str, *, ok: str = "Yes",
            cancel: str = "Cancel") -> bool:
        """Ask before doing something the user cannot undo with one click."""
        return Notice(parent, title, body, ok=ok,
                      cancel=cancel).exec() == QDialog.DialogCode.Accepted


#: HOW LONG A HOVER TOOLTIP MAY BE. Two hundred characters is about two
#: lines at the width Qt wraps them to, which is what somebody reads on the
#: way past a control. Anything longer belongs behind the ⓘ, which opens a
#: window wide enough for it. Reported from the real window, of a tooltip that
#: reached across the whole screen: "those hover tooltips should be short and
#: the extended version would be behind the tooltip icons."
_HOVER_LIMIT = 200


def _one_sentence(text: str) -> str:
    """The first sentence of an explanation, for a hover.

    THE SAME RULE THE ⓘ ITSELF USES for what it shows on hover -- see
    Hint._summary -- so a control that borrows an icon's words and one that
    has its own end up the same length.
    """
    first = (text or "").strip().split("\n\n")[0]
    cut = first.find(". ")
    return (first[:cut + 1] if cut > 0 else first)[:_HOVER_LIMIT]


class Hint(QToolButton):
    """The ⓘ beside a control: click it and the explanation opens.

    These explanations are long on purpose -- they are written for somebody
    meeting a printer gamut for the first time. Eighteen long paragraphs laid
    into a 310px column is most of the column, and folding each one away still
    spent a row on every one.

    A single ⓘ says the same thing in one glyph, in the place the eye already
    looks for help, and the full text then arrives in a window wide enough to
    read it. It is also the convention ChromIQ uses throughout, which matters
    because these two are meant to sit beside each other.

    Hovering shows the first sentence, so the common question is answered
    without a click at all.
    """

    #: Kept so the persistence table needs no special case. Nothing about an
    #: ⓘ is worth remembering between sessions, so it never fires.
    stateChanged = pyqtSignal(int)

    #: ChromIQ draws its ⓘ at 18 logical pixels; matched so the two sit at
    #: the same weight beside the same kind of control.
    ICON = 18

    #: One QIcon per (colour, device pixel ratio). A window has twenty of
    #: these and they share a handful of colours, so all but the first draw
    #: of each becomes a dict lookup instead of a repaint.
    _CACHE: "dict[tuple, QIcon]" = {}

    def explanation(self) -> str:
        """The full text behind the icon."""
        return self._text

    def in_a_sentence(self) -> str:
        """The short version, for a control that only has to answer a hover.

        THE HOVER IS SHORT AND THE ICON IS LONG, and that is the rule for the
        whole window: "some tooltips from hovering extend very far. those
        hover tooltips should be short and the extended version would be
        behind the tooltip icons." A hover tooltip is read on the way past --
        a paragraph in one is a wall that covers the thing it is describing,
        and one of them measured 2,139 characters, wider than the screen.
        """
        return self._summary()

    def __init__(self, text: str, parent=None, *, title: str = "") -> None:
        super().__init__(parent)
        self._text = text
        self._title = title or "About this setting"
        self.setObjectName("hintIcon")
        self.setFixedSize(QSize(Hint.ICON + 4, Hint.ICON + 4))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # No button frame: a QToolButton paints the platform's raised box and
        # its shadow otherwise, which on a light background looks like a
        # button around the icon rather than an icon.
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setToolTip(self._summary())
        self.setAccessibleName("Explain this setting")
        self.clicked.connect(self._open)
        self.set_colour(SPEC_MAGENTA)

    def set_colour(self, colour: str) -> None:
        """Repaint the icon in *colour*, cached per colour and screen."""
        dpr = float(self.devicePixelRatioF() or 1.0)
        key = (colour, round(dpr, 3))
        icon = Hint._CACHE.get(key)
        if icon is None:
            phys = round(Hint.ICON * dpr)
            pix = QPixmap(phys, phys)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            qc = QColor(colour)
            painter.setPen(QPen(qc, max(1.0, phys * 0.10)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            margin = int(phys * 0.07)
            painter.drawEllipse(margin, margin,
                                phys - 2 * margin, phys - 2 * margin)
            font = QFont()
            font.setFamilies(["Georgia", "Times New Roman", "serif"])
            font.setItalic(True)
            font.setBold(True)
            font.setPixelSize(max(8, int(phys * 0.54)))
            painter.setFont(font)
            painter.setPen(qc)
            painter.drawText(
                QRect(0, 0, phys, int(phys * 1.05)),
                int(Qt.AlignmentFlag.AlignHCenter
                    | Qt.AlignmentFlag.AlignVCenter), "i")
            painter.end()
            pix.setDevicePixelRatio(dpr)
            icon = QIcon(pix)
            Hint._CACHE[key] = icon
        self.setIcon(icon)
        self.setIconSize(QSize(Hint.ICON, Hint.ICON))

    def _summary(self) -> str:
        """The first sentence, for the hover tooltip."""
        first = self._text.strip().split(chr(10) + chr(10))[0]
        cut = first.find(". ")
        return (first[:cut + 1] if cut > 0 else first)[:200]

    def _open(self) -> None:
        Notice.say(self.window(), self._title, self._text)

    def follow(self, control) -> None:
        """Show and hide with *control*.

        An explanation for something that is not on screen is worse than no
        explanation: it points at nothing and takes up a place in the column
        that the eye tries to make sense of.
        """
        if control is None:
            return
        self._followed = control
        control.installEventFilter(self)
        # isHidden(), NOT isVisible(). Nothing is "visible" until every
        # ancestor has been shown, and this is called while the window is
        # still being built -- so an icon tied to a perfectly ordinary control
        # was hidden at birth and never told to appear, because the Show event
        # it waits for had already happened. Measured: of four icons added by
        # the tooltip sweep, one was on screen.
        self.setVisible(not control.isHidden())

    def eventFilter(self, watched, event):      # noqa: N802 (Qt naming)
        if watched is getattr(self, "_followed", None):
            if event.type() == QEvent.Type.Show:
                self.setVisible(True)
            elif event.type() == QEvent.Type.Hide:
                self.setVisible(False)
        return super().eventFilter(watched, event)

    def isChecked(self) -> bool:
        return False

    def setChecked(self, on: bool) -> None:
        return


def _join_words(words) -> str:
    """"a", "a and b", "a, b and c" -- never "a, b, c" with a bare comma.

    Count-aware by construction, so no message ever has to say "family(s)".
    """
    words = list(words)
    if len(words) <= 1:
        return words[0] if words else ""
    return f"{', '.join(words[:-1])} and {words[-1]}"


def _log():
    """The application's logger, fetched lazily so importing this module does
    not create a log file for a process that never shows a window."""
    from logger import get_logger
    return get_logger("app")


def _profile_label(path: Path) -> str:
    """What to call a profile in the readouts, so it cannot be mistaken for
    a measurement.

    A profile built from a chart usually carries the chart's own name, so
    comparing the two produced sentences like "97.2% of what Glossy-paper can
    print also fits inside Glossy-paper" — which reads as nonsense and hides
    the one distinction this whole window exists to draw. Saying "(profile)"
    keeps described and measured apart on every line that mentions them.
    """
    suffix = path.suffix.lower()
    if suffix == ".gam":
        kind = "gamut file"
    elif suffix in (".icc", ".icm"):
        kind = "profile"
    else:
        # A measurement may be the comparison too, and calling it a profile
        # would be exactly the confusion this function exists to prevent.
        kind = "measured"
    return f"{path.stem} ({kind})"


def _wrapped(label: QLabel, width: int = 0) -> QLabel:
    """Kept so existing calls read the same; the label refits itself now."""
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Preferred,
                        QSizePolicy.Policy.MinimumExpanding)
    if isinstance(label, WrappedLabel):
        label._refit()
    return label


#: Every term this window uses that a beginner might not know. Principle: if a
#: word appears on screen, it is explained here in plain language, with what it
#: means FOR YOU rather than what it means in a textbook.
GLOSSARY = [
    ("Gamut",
     "The full set of colours something can manage. Your printer has one, your "
     "screen has one, and your eyes have one. When an image asks for a colour "
     "outside the gamut, the nearest available colour is printed instead — "
     "which is why a gamut that is too small shows up as flat, muddy skies and "
     "greens that all look the same."),
    ("Measured chart (.ti3)",
     "The file ArgyllCMS saves when you read a printed test chart with a "
     "spectrophotometer. It holds two things for every patch: the colour you "
     "asked the printer for, and the colour that actually came out. That pair "
     "is what lets this window draw the real edge of your printer rather than "
     "a smoothed guess."),
    ("Patch",
     "One small square of colour on a printed test chart. A typical chart has "
     "several hundred to a couple of thousand of them."),
    ("ICC profile",
     "A file that describes how a particular printer, paper and ink behave "
     "together, so your applications can print predictable colour. It is a "
     "model built from measurements — which is why what a profile promises "
     "and what the paper actually did are worth comparing."),
    ("Coverage",
     "How much of one gamut fits inside another, as a percentage. It is not "
     "the same in both directions: paper A can hold nearly all of paper B "
     "while B holds only part of A. Both numbers are shown, because which one "
     "matters depends on which way you are moving an image."),
    ("How much colour it holds",
     "A single number for the size of a gamut. Useful for comparing two "
     "papers measured the same way; not meaningful on its own, and not "
     "comparable between different measurement setups. ArgyllCMS reports the "
     "same quantity."),
    ("D50 and D65",
     "Two standard kinds of daylight. Colour only means anything relative to "
     "the light you view it under, so measurements name their light. Printed "
     "work is judged under D50; screens under D65."),
    ("sRGB, Adobe RGB, ProPhoto RGB",
     "Standard sets of colours that images are stored in. sRGB is what most "
     "photographs and most screens assume, and it is smaller than a good "
     "photo printer — so comparing your paper against it tells you whether an "
     "sRGB workflow is throwing away ink you have already paid for."),
    ("CIELAB",
     "The way of writing down a colour that this window uses unless you "
     "change it, and the right one for print. It has three numbers: L* for "
     "how light the colour is, and a* and b* for what colour it actually is. "
     "Its useful property is that the same distance anywhere in it looks like "
     "about the same size of change, which is what makes it fair to measure a "
     "volume in."),
    ("CIELUV",
     "Another way of writing down the same colours, with exactly the same "
     "lightness as CIELAB but the colour part arranged differently. It is the "
     "one screens and light sources are usually described in. Your paper will "
     "look like a different shape and give a different volume in it — that is "
     "the two spaces disagreeing about distance, not a mistake."),
    ("CIE XYZ",
     "The measurement in its rawest form, before anything is done to make "
     "distances match what the eye notices. Everything else here is worked "
     "out from it. It is honest but hard to read by eye: equal distances in "
     "it do not look equally different, and it has no lightness axis and no "
     "grey axis, so the slice, the rings and the greys are switched off while "
     "you are looking at it."),
    ("L*",
     "How light a colour is, from 0 for black to 100 for a perfect white. "
     "Your paper white is the highest L* the paper reaches and your blacks "
     "are the lowest — the gap between them is the contrast the paper can "
     "actually give you, whatever its gamut volume says."),
    ("Chroma",
     "How far a colour sits from grey. Low chroma is muted and close to grey, "
     "high chroma is vivid. It says nothing about which colour it is: a deep "
     "red and a deep blue can have the same chroma."),
    ("Hue family",
     "A group of neighbouring colours under one everyday name — the reds, "
     "yellows, greens, cyans, blues and magentas. Comparing two papers family "
     "by family is usually the practical answer to which one to use: a paper "
     "that reaches further in the cyans and blues suits skies and water, one "
     "that reaches further in the yellows and reds suits skin and autumn."),
    ("Shared colour",
     "How much of everything either paper can print is printable by both of "
     "them. Unlike coverage it is the same number whichever way round you "
     "ask, so it answers \"are these two alike?\" rather than \"will this "
     "image survive the swap?\"."),
]


#: How long a leftover folder has to have sat there before a new run will
#: clear it away. An hour is far longer than the gap between one run writing
#: its folder and that run being visible in the process table, and far shorter
#: than anybody would want to keep gigabytes of dead scenes.
FORGOTTEN_AFTER_SECONDS = 3600


def _sweep_up_after_runs_that_never_finished(mine: Path) -> None:
    """Clear away scene folders left by runs that were killed or crashed.

    Closing the window takes its own folder with it, which covers the ordinary
    case. It does not cover the two that actually filled a disk: a run that
    crashes, and a run that is killed -- and a test suite, an audit or a
    screenshot driver starts the window hundreds of times and does not always
    let it close politely.

    Measured on the machine this is developed on: **644 folders holding 27 GB**
    after two days, which is what prompted this.

    A FOLDER IS ONLY TAKEN WHEN NOBODY IS USING IT. Each run writes its process
    id and a new run keeps any folder whose process is still alive, so two
    windows open at once cannot delete each other's scenes. Where that cannot
    be answered -- a recycled process id, a folder from before this was added
    and carrying no id at all -- age decides, and the folder has to have been
    untouched for an hour. Anything that goes wrong here is ignored: failing to
    tidy up is not a reason to refuse to start.
    """
    try:
        (mine / "owner.pid").write_text(str(os.getpid()))
        here = mine.parent
        now = time.time()
        for folder in here.glob("gamutview-*"):
            if folder == mine or not folder.is_dir():
                continue
            try:
                if now - folder.stat().st_mtime < FORGOTTEN_AFTER_SECONDS:
                    continue                  # too recent to judge by age
                owner = folder / "owner.pid"
                if owner.exists():
                    try:
                        os.kill(int(owner.read_text().strip()), 0)
                        continue              # its window is still open
                    except (ProcessLookupError, ValueError, OverflowError):
                        # Gone, or the file does not hold a process id at all.
                        # OverflowError is in there because a number too large
                        # to BE a process id raises that rather than saying no
                        # such process -- and without it the exception left
                        # this function through the guard below, which is
                        # written to ignore everything, so the sweep stopped
                        # silently at the first such folder and swept nothing.
                        pass
                    except PermissionError:
                        continue              # alive and not ours to touch
                shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                continue
    except Exception:        # noqa: BLE001 — tidying must never stop a start
        pass


#: Send a whole scene's worth of new points into the picture already on screen.
#:
#: THE ORDERED LIST IS CHECKED BEFORE A SINGLE TRACE IS TOUCHED, and that check
#: is what makes pushing by POSITION safe here. Everywhere else in this window
#: a trace is found by its name, because matching by position once faded the
#: wrong shape -- but a change of detail cannot be done by name at all: a cage
#: drawn over sRGB is three traces every one of which is called
#: "sRGB (outline)", so a name would send one trace's points to all three.
#: Position is the only way to tell them apart, and position is only dangerous
#: when nobody checked. Anything unexpected -- a different number of traces, a
#: name out of place, a type that has changed -- and this touches nothing at
#: all and answers no, so the window falls back to the rebuild that has always
#: worked.
#:
#: ONE RESTYLE PER TRACE rather than one batched call. Batched, a trace with no
#: triangles has to be handed `undefined` in the middle of the triangle list,
#: which is a shape of call the drawing library does not document and does not
#: need to accept. Measured, the difference is a few milliseconds on a payload
#: of nearly two megabytes.
_DETAIL_JS = """
  var el = document.getElementsByClassName('plotly-graph-div')[0];
  if (!el || !window.Plotly || !el.data) return false;
  if (el.data.length !== want.length) return false;
  var i;
  for (i = 0; i < want.length; i++) {
    if (String(el.data[i].name || '') !== want[i].n) return false;
    if (el.data[i].type !== want[i].t) return false;
  }
  // THE FRAME FIRST, WHEN THERE IS ONE, and the order was measured rather
  // than chosen. A flat cross-section is drawn to fill its picture, so moving
  // it up or down moves the axes as well -- and its caption names the height
  // it was cut at. Sent without them the new outlines would be drawn inside
  // the old frame, under a sentence naming a lightness they are not at.
  //
  // Sent AFTER the outlines, one height in five came out ten thousand pixels
  // away from what a rebuild draws: the spacing between gridlines is settled
  // from whatever is on the axis at the moment it is asked, so the outlines
  // arrived first and the axis was worked out around the wrong ones. Frame
  // first, and that height matches to the pixel.
  var FIELDS = {x: 'x', y: 'y', z: 'z', i: 'i', j: 'j', k: 'k',
                c: 'vertexcolor'};
  if (frame) window.Plotly.relayout(el, frame);
  for (i = 0; i < want.length; i++) {
    var patch = {}, any = false, f;
    for (f in FIELDS) {
      if (!Object.prototype.hasOwnProperty.call(want[i], f)) continue;
      patch[FIELDS[f]] = [want[i][f]];
      any = true;
    }
    if (any) window.Plotly.restyle(el, patch, [i]);
  }
  return true;
"""


class GamutApp(QMainWindow):
    """One window: measurements on the left, the gamut on the right."""

    def __init__(self, initial: "list[Path] | None" = None) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        # NEVER OPEN BIGGER THAN THE SCREEN. A window that starts off the
        # bottom of a laptop display hides its own buttons and cannot always
        # be dragged back -- reported from a real display. Ask the screen
        # how much room there actually is -- availableGeometry excludes the
        # menu bar and the dock -- and take the smaller of that and a
        # comfortable size, leaving a small margin so the frame is grabbable.
        screen = QApplication.primaryScreen()
        room = (screen.availableGeometry() if screen is not None
                else QRect(0, 0, 1280, 840))
        self.resize(min(1280, room.width() - 40), min(840, room.height() - 60))
        # Positioned properly in showEvent, not here: at this point the
        # controls have not been built, so the window still grows afterwards
        # and any centring done now is centring the wrong size.
        self._placed = False
        self._slots: list[tuple[Path, object]] = []      # (path, Gamut, Measurement)
        self._reference: tuple[str, object] | None = None   # (name, Gamut)
        # Where an ICC or .gam comparison came from. Remembered so that
        # changing the space or the white point can rebuild it in the new
        # one instead of asking for the file again -- or, worse, leaving a
        # comparison behind in the space it was first built in.
        self._reference_path: Path | None = None
        #: The chart waiting to be printed, when one is open: its path, what
        #: was read out of it, and where its patches land once a profile has
        #: been asked. KEPT APART FROM ``_slots`` ON PURPOSE — a chart is not a
        #: gamut and must never become one, and holding it in the same list as
        #: the measured shapes is how it would quietly get drawn as a solid.
        self._chart: "tuple[Path, object] | None" = None
        self._chart_placed = None            # chart.Placement, or None
        self._chart_profile: Path | None = None
        self._tmp = Path(tempfile.mkdtemp(prefix="gamutview-"))
        _sweep_up_after_runs_that_never_finished(self._tmp)
        #: Where the last file came from, so the next dialog opens there.
        self._last_folder = ""
        #: Renders so far, so each one gets a URL the view has not seen.
        self._render_count = 0
        #: WHERE THE READER HAS TURNED THE SHAPE TO, kept up to date from the
        #: page itself. Anything this window cannot restyle in place is drawn
        #: by writing a new page and loading it, and a page opens at the
        #: camera it was written with -- so every rebuild threw away the angle
        #: somebody had chosen. See _watch_the_camera.
        self._camera = None
        self._camera_watch = None
        # Papers rebuilt in CIELAB for judging, keyed by everything that
        # changes the shape. See _in_lab.
        self._lab_gamuts: dict = {}
        #: Per-shape overrides, by slot (0, 1) and 2 for the comparison. A key
        #: is present only when that shape has been set on its own; otherwise
        #: it follows the shared value, so "global" needs no bookkeeping.
        self._per_shape = {0: {}, 1: {}, 2: {}}
        #: The values every shape follows unless it has its own. Held apart
        #: from the sliders on purpose: while a single shape is selected the
        #: sliders show THAT shape, so reading the shared value off a slider
        #: would hand one shape's setting to all the others.
        self._shared = dict(opacity=1.0, depth=0.35, rings=0,
                            mesh_paint="plain", paint="true")
        #: Light or dark. Remembered between runs, because an appearance you
        #: have to set again every time is not really a setting.
        # THROUGH prefs.store AND NOT BUILT HERE, so that a driver can send
        # the whole application's settings to a throwaway file and be sure it
        # has: an audit that writes into somebody's real preferences turns
        # every state it tries into their new default. See python/prefs.py.
        self._store = prefs.store()
        self._appearance = str(self._store.value("appearance", "dark"))
        if self._appearance not in PALETTES:
            self._appearance = "dark"
        self._scheme = str(self._store.value("scheme", "Magenta"))
        if self._scheme not in SCHEMES:
            self._scheme = "Magenta"
        self._paint = str(self._store.value("paint", "true"))
        if self._paint not in dict(PAINTS):
            self._paint = "true"

        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # Eyebrow names the family, title names this window.
        self._masthead = Masthead("CHROMIQ", "Measured gamut", central)
        outer.addWidget(self._masthead)
        body = QWidget(central)
        outer.addWidget(body, 1)
        row = QHBoxLayout(body)
        row.setContentsMargins(14, 12, 14, 14)
        row.setSpacing(14)
        # The column scrolls: its help text is as long as it needs to be, and
        # on a short screen that is taller than the window. Scrolling keeps
        # every control reachable instead of trimming the explanations.
        controls = FadeScrollArea(body)
        column = self._build_controls()
        controls.setWidget(column)
        controls.setWidgetResizable(True)
        # 330 fitted before each control gained an 18px icon and 6px of spacing
        # beside it; several combo labels were clipped at the old width.
        #
        # AND IT IS A FLOOR, NOT THE ANSWER. Pinned at 366 flat, this clipped
        # whatever outgrew it -- with the horizontal scrollbar deliberately
        # off, an overflowing section is simply cut, with no way to scroll to
        # the missing part. "How it looks" needs 372, because "Show what the
        # comparison cannot print" is 270 px of label that cannot wrap and
        # the ⓘ has to sit beside it; so that section lost its right-hand
        # border and about four pixels of that row's ⓘ. Reported from a
        # screenshot of the real window.
        #
        # Taken from the column itself, plus room for the scrollbar that sits
        # beside it, so the two can never disagree again.
        gutter = controls.verticalScrollBar().sizeHint().width()
        controls.setFixedWidth(max(366, column.minimumWidth() + gutter
                                   + 2 * controls.frameWidth()))
        # KEPT, so the width can be settled again once the window is polished
        # and the sections finally admit how wide they are -- see
        # _widen_the_column_to_fit_it.
        self._controls_area = controls
        controls.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        row.addWidget(controls, 0)

        self._view = QWebEngineView(body)
        # 420, not 560: with the 366px controls column beside it, a 560 floor
        # made the whole window refuse to go below 972px, which would hang off
        # the side of a genuinely small display. A 420px scene is still worth
        # looking at, and anybody can make the window bigger.
        self._view.setMinimumWidth(420)
        # A web view paints white until a page has loaded, and again for an
        # instant on every reload, which reads as a bright frame round a dark
        # scene and as a flash when anything changes. Both the widget and the
        # page it shows are told to be the same dark as the rest of the window.
        self._view.setStyleSheet("background: #111111;")
        self._view.page().setBackgroundColor(QColor("#111111"))
        frame = self._frame = QFrame(body)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.addWidget(self._view)
        row.addWidget(frame, 1)
        self.setCentralWidget(central)
        self.setAcceptDrops(True)      # drop a .ti3 anywhere on the window
        self._attach_hint_icons(self.findChild(QScrollArea))
        # Five explanations cover a whole group rather than one control, so
        # the generic pass has nothing obvious to attach them to. Each is
        # named here with the control it belongs beside -- the one the group
        # is really about -- because an icon on a row of its own reads as
        # explaining nothing.
        for _name, _control in (
                ("hint_hint", self._open_btn),
                # BESIDE ITS OWN OPEN BUTTON, exactly as the group above it.
                #
                # This explanation was left where it was written, which put it
                # beside the note near the bottom of the group -- and that
                # note hides itself when there is no chart open, taking the ⓘ
                # with it. So the two groups that begin with an open button
                # did not match: one carried its explanation beside the
                # button, always, and the other carried it three rows down
                # and only once you had already done the thing the
                # explanation was there to help you do.
                ("hint_chart_hint", self._chart_btn),
                ("hint_cmp_hint", self._compare),
                ("hint_style_hint", self._style_combos[0][0]),
                ("hint_paint_hint", self._paint_label),
                ("hint_appearance_hint", self._appearance_label),
                ("hint_accent_hint", self._accent_label),
                ("hint_volume_hint", self._volume)):
            self._pair_icon(_name, _control)
        # AND EVERY CONTROL BESIDE AN ⓘ BORROWS ITS WORDS, so that hovering
        # the thing itself answers as well as hovering the icon. Run after
        # the icons have been placed, because it reads the rows they ended up
        # in. See _lend_the_hint_words_to_the_control.
        self._lend_the_hint_words_to_the_control(self.findChild(QScrollArea))
        # AND NOTHING IS EXPLAINED AT LENGTH ON A HOVER. Last, so it sees the
        # words every earlier pass has handed out. See _shorten_the_hovers.
        self._shorten_the_hovers(self.findChild(QScrollArea))
        # A hidden control must take its ⓘ with it. Anything already managed
        # by an explicit show/hide list keeps that behaviour; the attach pass
        # ties the rest to the control they were placed beside.
        for _icon in self.findChildren(Hint):
            _followed = getattr(_icon, "_followed", None)
            if _followed is not None:
                _icon.setVisible(_followed.isVisible())
        import argyll as _argyll
        _argyll.set_folder(self._store.value("argyll_folder", "") or None)
        self._refresh_argyll()
        movie.set_path(self._store.value("ffmpeg_path", "") or None)
        self._refresh_ffmpeg()
        self._restore_look()
        self._restore_everything()
        self._apply_space_availability()
        self._follow_neutral(self._neutral.isChecked())
        # Settle the turning controls: fill in the value labels and hide the
        # rows that do not apply yet. Nothing is loaded, so this only tidies
        # the column -- but an empty label beside a slider looks broken.
        self._update_spin_labels()
        self._apply_spin_availability()
        self._recolour_hints()
        self._apply_mode()
        self._refresh_chart_panel()      # its empty state, before anything is open
        self._show_placeholder()
        # Anything the user moves is written straight away, so a crash or a
        # force-quit cannot lose a setting they just chose.
        for _key, widget, kind, _default in self._persisted():
            signal = (widget.valueChanged if kind == "slider"
                      else widget.stateChanged if kind == "check"
                      else widget.currentIndexChanged)
            signal.connect(lambda *_a: self._remember_everything())

        # Deferred so the window is on screen first: a check that runs
        # during construction would hold up the first paint on a slow
        # network, and its dialog could arrive before the window.
        if self._auto_update.isChecked():
            QTimer.singleShot(1500,
                              lambda: self._check_updates(asked=False))

        for p in (initial or []):
            self._load(Path(p))

    # ------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, event) -> None:    # noqa: N802 (Qt naming)
        """Accept a dragged file, so opening one needs no dialog at all."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:         # noqa: N802 (Qt naming)
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self._load(Path(url.toLocalFile()))
        event.acceptProposedAction()

    # ---------------------------------------------------------------- controls
    def _build_controls(self) -> QWidget:
        col = QWidget(self)
        col.setFixedWidth(346)
        v = QVBoxLayout(col)
        # TWO PIXELS OF AIR EITHER SIDE OF EVERY SECTION. With no margin at
        # all a section is exactly as wide as the column, so its own frame is
        # drawn on the first and last pixel of the viewport -- hard against
        # the scroll area on one side and the scrollbar's gutter on the other.
        # Measured on the real platform: "How it looks" 372 px wide in a 372
        # px viewport, its right border at x=371 with the last two pixels
        # #333333. Reported from the window twice, the second time as "how it
        # looks is still a little too wide. the frame is cut off".
        #
        # HERE RATHER THAN IN THE COLUMN'S WIDTH, which is where it was tried
        # first and does not work: a section stretches to whatever width the
        # column has, so widening the column widens the section with it and
        # the frame lands on the last pixel again.
        v.setContentsMargins(2, 0, 2, 0)
        v.setSpacing(12)

        # NO HEADING HERE. The window is already titled, the first group says
        # "Your measured chart", and a lone title above a column of controls
        # does no work -- it either repeats the window title or, with its
        # explanation moved to the empty view where it is actually needed,
        # sits there with nothing under it. The controls start straight away.
        # Two radio buttons rather than one button that toggles: a toggle has
        # to name the mode you are NOT in, which reads as a statement about the
        # current state and is read wrongly about half the time. Radios show
        # both choices and which one is active, and cannot be misread.

        # --- the measurements -------------------------------------------------
        g_files = QGroupBox("What you are looking at", col)
        fv = QVBoxLayout(g_files)
        # GENERAL RATHER THAN A LIST, and the measurement is why. There are
        # FOUR kinds of file now, and naming them all needs far more room than
        # a button in a 346 px column has: a full-width button here is 276 px,
        # "Open a measurement, profile or chart…" needs 272 and does not even
        # mention pictures. Four pixels of clearance is a label that clips on
        # the first platform whose font runs a shade wider. This one needs 201,
        # and the tooltip beside it has room to name all four properly.
        self._open_btn = QPushButton("Open something to look at…", g_files)
        self._open_btn.setToolTip(
            "Opens any of the four kinds of file this window understands. You "
            "can drag one onto the window instead, and you can start with "
            "whichever kind you have.\n\n"
            "A MEASUREMENT (.ti3, .cxf, .mxf, .txt) is what your instrument "
            "read off a printed chart — what your printer really did, on that "
            "paper, on that day.\n\n"
            "An ICC PROFILE (.icc, .icm) or an ArgyllCMS gamut file (.gam) is "
            "what your printer is *described* as being able to do. Opening the "
            "profile and the measurement it was built from, together, shows "
            "you how well the description matches.\n\n"
            "A PICTURE — a photograph, or anything else you can open — shows "
            "the colours that are actually in it, which is rarely as many as "
            "people expect. Open one beside a paper and the readouts answer "
            "the real question: will this image survive on that paper, and "
            "which of its colours will not make it?\n\n"
            "A CHART (.ti1, .ti2, or an i1Profiler target) is the other end of "
            "the story: patches waiting to be printed, none of them measured "
            "yet. One opened here goes to A chart to be printed, further down "
            "this column, because it is drawn as a cloud of dots rather than "
            "as a shape.")
        self._open_btn.clicked.connect(self._on_open)
        fv.addWidget(self._open_btn)
        # One row per open chart, each with its own way out. A single "close
        # everything" button meant a second chart could not be put back without
        # reopening the first, which is the wrong shape for comparing things.
        self._image_facts: dict = {}
        self._slot_labels = []
        self._slot_rows = []
        for i in range(2):
            row = QWidget(g_files)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            lab = WrappedLabel("", row)
            lab.setObjectName("slot")
            rl.addWidget(lab, 1)
            # A small × rather than a "Close" button: it sits beside the name
            # of the chart it closes, so the word adds nothing that the
            # position does not already say, and a full-width button there
            # competes with "Open a measurement or a profile" for attention.
            shut = QPushButton("×", row)
            shut.setObjectName("closer")
            shut.setFixedSize(22, 22)
            shut.setToolTip("Close this one")
            shut.clicked.connect(lambda _checked=False, which=i:
                                 self._close_one(which))
            rl.addWidget(shut, 0)
            row.setVisible(False)
            fv.addWidget(row)
            self._slot_labels.append(lab)
            self._slot_rows.append(row)
        # "Close both" WAS TRUE OF TWO THINGS AND THERE CAN NOW BE THREE. A
        # chart open beside two measurements made the word a small lie, and
        # leaving the chart behind after a button that says "both" is exactly
        # the sort of surprise this window is careful about.
        self._clear_btn = QPushButton("Close them all", g_files)
        self._clear_btn.setObjectName("secondary")
        self._clear_btn.setToolTip(
            "Starts you again with an empty window.\n\n"
            "It closes everything at once: both shapes, whatever kind of file "
            "they came from, the chart if one is open, and the comparison you "
            "picked under Compare with. The figures go with them, because "
            "every one of those sentences is about a file you have just "
            "closed.\n\n"
            "TO CLOSE JUST ONE, use the × beside its name instead. That is "
            "the one to reach for when you are working through several papers "
            "against the same comparison — close the paper, open the next, "
            "and your sRGB or Adobe RGB stays exactly where it was. Use this "
            "button when you want a clean start rather than the next paper.\n\n"
            "NOTHING IS EVER DELETED, either way. Closing only takes a file "
            "off the screen. Every file on your drive is untouched, and you "
            "can open the same one again straight afterwards.")
        self._clear_btn.clicked.connect(self._on_clear)
        self._clear_btn.setVisible(False)
        hint = Hint(
            "Four kinds of file can go here, and you can start with any of "
            "them.\n\n"
            "A MEASUREMENT is the .ti3 file ArgyllCMS saves once you have read "
            "a printed chart with your instrument. The chart is the sheet of "
            "patches you printed; the measurement is what your instrument made "
            "of it, and that is the file. Every corner of the shape it draws "
            "is a patch that was really printed and really read, which is what "
            "makes it worth looking at.\n\n"
            "An ICC PROFILE (.icc or .icm) is the other kind — what your "
            "printer is *described* as being able to do. A profile is a "
            "fitted model: it smooths, it fills in the gaps, and near the "
            "edges it can promise a little more than the paper really gave. "
            "An ArgyllCMS gamut file (.gam) works here too.\n\n"
            "Open one, or drag it onto this window. Open a second and both "
            "are drawn together, so you can see which holds more colour and "
            "exactly where they differ — a paper against another paper, or a "
            "profile against the measurement it was built from, which is the "
            "comparison that shows you whether the profile is telling the "
            "truth.\n\n"
            "A PICTURE — a photograph or anything else you can open — shows "
            "the colours that are actually in it. Open one beside a paper and "
            "the readouts answer the question people really have: will this "
            "image survive on that paper, and which of its colours will not "
            "make it? Tick Show what the comparison cannot print and the ones "
            "that fall outside are picked out on the shape.\n\n"
            "A picture is read through its own colour profile when it carries "
            "one. When it does not, sRGB is assumed — the usual convention, "
            "right far more often than not — and the line under the name says "
            "so, because an assumption that changes the answer should never "
            "be made quietly.\n\n"
            "A CHART is the fourth, and it is the odd one out: a .ti1, a .ti2 "
            "or an i1Profiler target, holding the patches you are ABOUT to "
            "print. Nothing in it has been printed and nothing measured, so "
            "there is no shape to draw — the patches appear as a cloud of "
            "dots, put where a profile says they would land. Open one here or "
            "drag it in and it goes to A chart to be printed, further down "
            "this column, where you choose that profile.\n\n"
            "Each one always says underneath which kind it is, because "
            "mistaking them is the one confusion this window exists to clear "
            "up. A third shape can join them through Compare with, below.",
            g_files)
        hint.setObjectName("hint_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._clear_btn, 1)
        _r.addWidget(hint, 0, Qt.AlignmentFlag.AlignVCenter)
        fv.addLayout(_r)
        # SAY WHEN SOMETHING OPEN IS NOT IN THE PICTURE. Ink amounts draw the
        # chart and nothing else, on purpose — but a paper listed right here
        # and missing from the picture and the legend reads as a fault, and
        # there was nothing on screen to say otherwise. Reported from the real
        # window, where exactly that happened.
        self._not_drawn_note = WrappedLabel("", g_files, hide_when_empty=True)
        self._not_drawn_note.setObjectName("hint")
        _wrapped(self._not_drawn_note)
        fv.addWidget(self._not_drawn_note)
        v.addWidget(g_files)

        # --- how it is built --------------------------------------------------
        g_build = QGroupBox("How the shape is worked out", col)
        bv = QVBoxLayout(g_build)
        self._mode = NoScrollComboBox(g_build)
        self._mode.addItem("Follow the real edge", "device")
        self._mode.addItem("Wrap it in a simple skin", "hull")
        self._mode.currentIndexChanged.connect(self._rebuild)
        mode_hint = Hint(
            "Follow the real edge is the one to use. The edge of what a printer "
            "can print is not smooth — it has real "
            "dents in it, most noticeably in the deep blues. The recommended "
            "setting keeps those dents, because it also reads the colour "
            "values you asked the printer for, which every measured chart "
            "stores alongside the results. The simpler setting stretches a "
            "skin over the whole thing, which looks tidier but claims more "
            "colour than your printer really has. Switch between them to see "
            "the difference.\n\n"
            "If the skin shows long dark streaks fanning across the surface, "
            "nothing is wrong with your measurement. That is the skin bridging "
            "a gap between two patches that are far apart, and it has to "
            "stretch one long thin triangle to do it — the streak is the shape "
            "of that stretch. It is a fair warning that the skin is guessing "
            "there. Follow the real edge has no gaps to bridge, so the streaks "
            "do not appear.", g_build)
        mode_hint.setObjectName("hint_mode_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._mode, 1)
        _r.addWidget(mode_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        bv.addLayout(_r)
        v.addWidget(g_build)

        # --- what to compare against -----------------------------------------
        g_cmp = QGroupBox("Compare with", col)
        cvv = QVBoxLayout(g_cmp)
        self._compare = NoScrollComboBox(g_cmp)
        self._compare.addItem("Nothing — this one on its own", None)
        for _name in REFERENCE_SPACES:
            self._compare.addItem(_name, ("space", _name))
        # Measured: the box gives its text 276 px. "A profile, measurement or
        # picture…" needs 257, which is nineteen pixels of clearance and the
        # kind of margin that clips on somebody else's font; this one needs
        # 209. The ⓘ beside it carries the full list, which is what it is for.
        self._compare.addItem("A profile, paper or picture…", ("icc", None))
        self._compare.addItem("Everything the eye can see", ("visible", None))
        # ACTIVATED, NOT currentIndexChanged. Choosing the entry you are
        # already on changes no index, so nothing fired and the dialog never
        # opened: swapping to a different file meant picking something else
        # first and coming back. activated fires whenever a person picks a
        # line, which is the thing actually being responded to.
        self._compare.setToolTip(
            "Adds a third shape to hold what you have open against.\n\n"
            "A standard colour space — sRGB and the rest — asks whether the "
            "images people send you will survive on this paper. A file off "
            "your drive can be another paper's measurement, an ICC profile, an "
            "ArgyllCMS .gam, or a PICTURE: hold a paper up against a "
            "photograph and the readouts say how much of that photograph it "
            "can print. Every colour the eye can see asks how much of what "
            "your eyes manage this paper holds at all.\n\n"
            "This is for SHAPES. A chart that has not been printed yet is not "
            "one — it is a list of ink amounts with no place in colour space "
            "until a profile says where they land — so charts have their own "
            "section, A chart to be printed, just below. Whatever you choose "
            "here still gets its own line in that chart's figures, so the two "
            "work together.")
        self._compare.activated.connect(lambda _i: self._on_compare_changed())
        cvv.addWidget(self._compare)
        self._compare_note = WrappedLabel("", g_cmp, hide_when_empty=True)
        self._compare_note.setObjectName("hint"); _wrapped(self._compare_note)
        cmp_hint = Hint(
            "Comparing with a second measurement asks which of two papers can "
            "print more. Comparing with a standard space asks whether the "
            "images people send you will survive on this paper. Comparing with "
            "every visible colour asks how much of what your eyes can see this "
            "paper can hold at all. They are three different questions and the "
            "answers are not interchangeable.\n\n"
            "A CHART THAT HAS NOT BEEN PRINTED does not belong here, and not "
            "as a rule of tidiness: a chart is a list of ink amounts, it has "
            "no shape, and there is nothing to compare until a profile says "
            "where those amounts would land. Charts have their own section "
            "underneath. Whatever you pick here does get counted against an "
            "open chart, though — it earns its own line in Are the patches "
            "inside?, alongside every other shape on screen.", g_cmp)
        cmp_hint.setObjectName("hint_cmp_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._compare_note, 1)
        _r.addWidget(cmp_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        cvv.addLayout(_r)
        v.addWidget(g_cmp)

        # --- a chart that has not been printed yet ----------------------------
        # ITS OWN GROUP, not a third entry in Compare with, because it is not a
        # shape and cannot be compared with anything on its own. A chart is a
        # list of ink amounts; it has no position in colour space until a
        # profile is asked where those amounts would land.
        g_chart = QGroupBox("A chart to be printed", col)
        chv = QVBoxLayout(g_chart)
        self._chart_btn = QPushButton("Open a chart to be printed…", g_chart)
        self._chart_btn.setToolTip(
            "Opens a chart that has not been printed yet: a .ti1 or .ti2 from "
            "ChromIQ or ArgyllCMS, or the .txt or .pxf file i1Profiler saves "
            "for a target.\n\n"
            "A chart is a list of ink amounts about to be asked for. Nothing "
            "in it has been printed and nothing in it has been measured, so it "
            "is never drawn as a shape — the patches appear as a cloud of "
            "dots, placed where an ICC profile says each one would land.\n\n"
            "Choose that profile under Placed through, just below. With the "
            "measurement of the paper open as well, the panel counts how many "
            "of the patches your printer can actually reach.")
        self._chart_btn.clicked.connect(self._on_open_chart)
        chv.addWidget(self._chart_btn)

        row = QWidget(g_chart)
        # NO TALLER THAN WHAT IS IN IT, and this row is where that was
        # learned. A plain QWidget wrapping a row of controls takes Qt's
        # default policy, which lets it GROW -- so at the narrow width it
        # opened 62 px tall around a 36 px label, pushed everything below it
        # down by 26, and the last paragraph in the group ended 8 px past the
        # group's own bottom edge. That is the cut sentence, again, from one
        # level up: "narrowing cuts off the text ... in dark mode but it is
        # there in light mode".
        #
        # It looked like an appearance fault for the usual reason: switching
        # re-polishes every widget, the layouts run again, and the row settles
        # at 36 -- measured -8px as it opens, +10px after a switch, and +10px
        # for ever after that.
        row.setSizePolicy(QSizePolicy.Policy.Preferred,
                          QSizePolicy.Policy.Maximum)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        self._chart_label = WrappedLabel("", row)
        self._chart_label.setObjectName("slot")
        rl.addWidget(self._chart_label, 1)
        shut = QPushButton("×", row)
        shut.setObjectName("closer")
        shut.setFixedSize(22, 22)
        shut.setToolTip("Close this chart")
        shut.clicked.connect(self._close_chart)
        rl.addWidget(shut, 0)
        row.setVisible(False)
        chv.addWidget(row)
        self._chart_row = row

        self._chart_through_row = QWidget(g_chart)
        tl = QVBoxLayout(self._chart_through_row)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(4)
        # Kept, because the same control is required in a colour space and
        # optional in ink amounts, and a label that does not say which leaves
        # somebody hunting for a profile they do not need.
        self._chart_through_name = QLabel("Placed through",
                                          self._chart_through_row)
        self._chart_through_name.setObjectName("name")
        tl.addWidget(self._chart_through_name)
        self._chart_through = NoScrollComboBox(self._chart_through_row)
        # ACTIVATED, for the same reason Compare with uses it: picking the
        # entry you are already on changes no index, so choosing "another
        # profile…" a second time would do nothing at all.
        self._chart_through.activated.connect(lambda _i: self._on_chart_profile())
        through_hint = Hint(
            "Which ICC profile should be asked where these patches will land. "
            "Choose the profile the chart was built for — usually the one for "
            "the printer and paper you are about to print it on.\n\n"
            "WHY IT IS NEEDED AT ALL. A chart file holds ink amounts, not "
            "colours: \"70% red, 40% green, 20% blue\" is an instruction to a "
            "printer, and what colour comes out of it depends entirely on "
            "which printer and which paper. A profile is the only thing that "
            "can answer that, so until one is chosen there is nowhere in "
            "colour space to draw the patches.\n\n"
            "IT IS OPTIONAL IN ONE VIEW. Choose Ink amounts under Draw it in "
            "and the patches appear with no profile at all, because there the "
            "axes are the ink amounts themselves and the file already holds "
            "them. A profile is still worth choosing there — it is what "
            "paints each dot the colour it will really print as, and it lets "
            "the patches be counted against a paper you have open.\n\n"
            "The list offers every profile you already have open, so the "
            "usual answer is one click. Choose another profile… to pick any "
            "file on your computer.\n\n"
            "A profile with no relative colorimetric table is used through "
            "its perceptual one instead, and the panel says so when that "
            "happens — perceptual squeezes the whole space to fit, which "
            "moves patches that are perfectly reachable.",
            self._chart_through_row)
        through_hint.setObjectName("hint_chart_through_hint")
        _tr = QHBoxLayout(); _tr.setContentsMargins(0, 0, 0, 0); _tr.setSpacing(6)
        _tr.addWidget(self._chart_through, 1)
        _tr.addWidget(through_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        tl.addLayout(_tr)
        self._chart_through_row.setVisible(False)
        chv.addWidget(self._chart_through_row)

        self._chart_note = WrappedLabel("", g_chart, hide_when_empty=True)
        self._chart_note.setObjectName("hint"); _wrapped(self._chart_note)
        chart_hint = Hint(
            "A CHART IS THE OTHER END OF THE STORY from everything else this "
            "window opens.\n\n"
            "A measurement is what came back off the paper. A chart is the "
            "list of ink amounts about to be asked FOR — a .ti1 as ChromIQ or "
            "ArgyllCMS generates it, a .ti2 once it has been laid out on a "
            "sheet, or the .txt or .pxf file i1Profiler saves for the same "
            "thing. Nothing in it has been printed. Nothing in it has been "
            "measured.\n\n"
            "So it is never drawn as a solid shape. A shape thrown around a "
            "set of requested ink amounts is not the gamut of anything. The "
            "patches are drawn as a cloud of dots instead, and only where a "
            "profile says those amounts would land — which is why Placed "
            "through has to be answered before anything appears.\n\n"
            "WHAT IT ANSWERS. Open the profile the chart was built from and "
            "the question is whether the chart builder did its job: patches "
            "outside a gamut they were promised to be inside mean something "
            "went wrong between the two, and that really happens — a rendering "
            "intent that did not match, ink amounts counted 0 to 255 where the "
            "file wanted 0 to 100, patches clipped to a box around the gamut "
            "instead of to its surface, or simply the wrong profile. It does "
            "NOT check your printer, because the same profile is answering "
            "both questions.\n\n"
            "Open the MEASUREMENT of the paper as well, and it does check your "
            "printer: the patches your profile promises, held against what the "
            "paper really achieved. That is the one that finds trouble.\n\n"
            "Every shape on screen gets its own line in Are the patches "
            "inside?, below, so both questions are answered in the same "
            "picture and neither can be mistaken for the other.",
            g_chart)
        chart_hint.setObjectName("hint_chart_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._chart_note, 1)
        _r.addWidget(chart_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        chv.addLayout(_r)
        v.addWidget(g_chart)

        # --- one device, followed through time --------------------------------
        # UP HERE WITH THE OTHER WAYS IN, AND IN THE ACCENT, because that is
        # what it is: a button that opens files. It spent its first releases at
        # the bottom of this column in the quiet style, among "start again",
        # "what do these words mean" and the ArgyllCMS paths -- the things you
        # go looking for once. Nobody looking for a way to open profiles reads
        # that far down, and the two buttons that do the same job are both up
        # here and both in the accent. A third one dressed differently and
        # filed elsewhere reads as a different kind of thing.
        #
        # ITS OWN GROUP rather than a third button in "What you are looking
        # at", because the question is genuinely different. Everything above
        # compares what is open right now -- at most two shapes, side by side.
        # This follows ONE device through as many profiles as somebody has of
        # it, which is a question about time rather than about shape, and it
        # answers with a list and a graph rather than a gamut.
        g_time = QGroupBox("One device over time", col)
        tv = QVBoxLayout(g_time)
        # THE PANEL ITSELF, IN THE COLUMN, rather than a button that opens a
        # window. Asked for twice: "i would like to load the profiles in the
        # main window directly with the ability to close individual ones or
        # all, then the options i can choose in what is at the moment still in
        # its own window", and after seeing it still open a window, "clicking
        # follow the device over time still opens the window with the same
        # name instead of giving me all those options in the main window".
        #
        # THE REASON IT IS WORTH MOVING is the picture, not the controls. The
        # window it lived in gave the graph 240 px in a 940 px dialog; here it
        # draws into the view this whole application is built around, which is
        # the size of the screen.
        #
        # THE SAME OBJECT, NOT A COPY: TimelineDialog told it is hosted builds
        # its controls stacked for a 366 px column and hands its picture to
        # this window. See TimelineDialog.__init__.
        time_hint = Hint(
            "Two profiles of one printer, made a year apart, tell you whether "
            "anything has changed. Several of them tell you the shape of the "
            "change — and that matters, because a device that has drifted the "
            "same way for three years and one that wanders back and forth "
            "need quite different answers.\n\n"
            "WHAT TO OPEN, with Add profiles… just below: at least two ICC "
            "profiles (.icc or .icm) of the SAME device, made on different "
            "days. They must all be of the same kind — RGB profiles together, "
            "or CMYK profiles together — because the comparison works by "
            "asking every profile for the same ink or light amounts, and "
            "there is no such thing as the same amount across two different "
            "kinds of device.\n\n"
            "WHAT YOU GET: a graph of how far each profile sits from the "
            "first one, any two of them comparable directly, a report naming "
            "which colour families moved and which way, and the cloud of "
            "colours drawn in the big view beside this column.\n\n"
            "The profiles are read here, so this needs nothing installed and "
            "no internet.", g_time)
        time_hint.setObjectName("hint_timeline")
        time_note = WrappedLabel(
            "Several profiles of one printer, scanner or screen, made on "
            "different days: how far it has moved, and which colours moved "
            "most.", g_time)
        time_note.setObjectName("hint")
        _wrapped(time_note)
        _b = QHBoxLayout()
        _b.setContentsMargins(0, 0, 0, 0)
        _b.setSpacing(6)
        _b.addWidget(time_note, 1)
        _b.addWidget(time_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        tv.addLayout(_b)
        # WHICH QUESTION THE BIG VIEW IS ANSWERING, said only when both a run
        # and other files are open and the picture could be either. Empty
        # otherwise, and it hides itself when empty.
        self._who_owns = WrappedLabel("", g_time, hide_when_empty=True)
        self._who_owns.setObjectName("hint")
        _wrapped(self._who_owns)
        tv.addWidget(self._who_owns)
        self._timeline = TimelineDialog(self, appearance=self._appearance,
                                        preview=False, hosted=True)
        tv.addWidget(self._timeline)
        v.addWidget(g_time)

        # --- how the chart's patches are drawn --------------------------------
        # A whole group that only exists while there is a chart to apply it to.
        # Every row inside it appears on the same rule: the out-of-reach
        # controls need something to be out of reach OF, and the skin's own
        # settings need a skin. A control that cannot do anything is worse
        # than a missing one — it invites a click and answers with nothing.
        self._chart_look_box = QGroupBox("How the patches are drawn", col)
        clv = QVBoxLayout(self._chart_look_box)

        clv.addWidget(QLabel("How big the dots are",
                             self._chart_look_box))
        self._chart_dot = NoScrollSlider(Qt.Orientation.Horizontal,
                                         self._chart_look_box)
        self._chart_dot.setRange(20, 100)      # tenths, so 2.0 to 10.0
        self._chart_dot.setValue(32)
        self._chart_dot.valueChanged.connect(
            lambda v: self._restyle_the_chart('printed', 'marker.size',
                                              v / 10.0))
        dot_hint = Hint(
            "How large each patch is drawn. This changes nothing about the "
            "chart itself — only how easy its patches are to see.\n\n"
            "Small dots suit a big chart: a 1,000-patch target drawn large "
            "becomes a solid mass with nothing visible inside it. Larger dots "
            "suit a small chart, or a picture meant to be looked at from "
            "across a room.\n\n"
            "The patches that are out of reach are always drawn a little "
            "larger than the rest, whatever this is set to, so they can still "
            "be picked out.", self._chart_look_box)
        dot_hint.setObjectName("hint_chart_dot_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0); _r.setSpacing(6)
        _r.addWidget(self._chart_dot, 1)
        _r.addWidget(dot_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        clv.addLayout(_r)

        clv.addWidget(QLabel("How solid the dots are", self._chart_look_box))
        self._chart_dot_opacity = NoScrollSlider(Qt.Orientation.Horizontal,
                                                 self._chart_look_box)
        # ALL THE WAY DOWN, like every other percentage in this window. A
        # floor here meant the control stopped short of what its label
        # promises, and what it was protecting against -- something invisible
        # and unrecoverable -- is not true: the switches in this same group
        # put the dots and the skin back.
        self._chart_dot_opacity.setRange(0, 100)
        self._chart_dot_opacity.setValue(100)
        self._chart_dot_opacity.valueChanged.connect(
            lambda v: self._restyle_the_chart('printed',
                                              'marker.opacity',
                                              v / 100.0))
        dot_op_hint = Hint(
            "How much of each dot you can see through. Fully solid is the "
            "usual choice and the one to come back to.\n\n"
            "Turning it down is worth doing on a dense chart: several hundred "
            "patches drawn solid hide one another, and the ones at the front "
            "are all you ever see. Made semi-transparent they build up, so "
            "where the chart samples heavily reads as darker and you can see "
            "into the middle of the cloud.\n\n"
            "This is about seeing the chart, not about the chart itself — no "
            "number anywhere in the window changes with it.",
            self._chart_look_box)
        dot_op_hint.setObjectName("hint_chart_dot_opacity_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0); _r.setSpacing(6)
        _r.addWidget(self._chart_dot_opacity, 1)
        _r.addWidget(dot_op_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        clv.addLayout(_r)

        self._chart_show_outside = QCheckBox(
            "Show the ones out of reach", self._chart_look_box)
        self._chart_show_outside.setChecked(True)
        self._chart_show_outside.stateChanged.connect(self._redraw)
        outside_hint = Hint(
            "The patches a paper cannot reach are drawn larger and in red, so "
            "they can be found without reading a number. Untick this to see "
            "only what will survive — useful when the red is so dense that it "
            "hides everything behind it.\n\n"
            "This appears only while something is open for them to be out of "
            "reach OF: a measured paper, or the profile itself.",
            self._chart_look_box)
        outside_hint.setObjectName("hint_chart_outside_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0); _r.setSpacing(6)
        _r.addWidget(self._chart_show_outside, 1)
        _r.addWidget(outside_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        self._chart_outside_row = QWidget(self._chart_look_box)
        orl = QVBoxLayout(self._chart_outside_row)
        orl.setContentsMargins(0, 0, 0, 0)
        orl.setSpacing(4)
        orl.addLayout(_r)

        # THEIR OWN SIZE AND SOLIDITY, separately from the ones that fit. The
        # two sets are being read for different reasons — the survivors as a
        # cloud with a shape, the lost ones as individual findings — and one
        # slider for both means every change to one spoils the other.
        orl.addWidget(QLabel("How big the out-of-reach dots are",
                             self._chart_outside_row))
        self._chart_out_dot = NoScrollSlider(Qt.Orientation.Horizontal,
                                             self._chart_outside_row)
        self._chart_out_dot.setRange(20, 140)
        self._chart_out_dot.setValue(55)
        self._chart_out_dot.valueChanged.connect(
            lambda v: self._restyle_the_chart('outside', 'marker.size',
                                              v / 10.0))
        out_dot_hint = Hint(
            "How large the patches a paper cannot reach are drawn, set "
            "separately from the rest so the two can be balanced against each "
            "other.\n\n"
            "They start larger than the others on purpose: they are usually "
            "the minority and the whole point is to find them without "
            "counting. Make them larger still when only a handful are out of "
            "reach and they are getting lost; make them smaller when half the "
            "chart is red and the size is burying everything behind it.\n\n"
            "Setting them to the same size as the rest is perfectly "
            "reasonable once you are reading the shape rather than hunting "
            "for individual patches.", self._chart_outside_row)
        out_dot_hint.setObjectName("hint_chart_out_dot_hint")
        _r2 = QHBoxLayout(); _r2.setContentsMargins(0, 0, 0, 0); _r2.setSpacing(6)
        _r2.addWidget(self._chart_out_dot, 1)
        _r2.addWidget(out_dot_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        orl.addLayout(_r2)

        orl.addWidget(QLabel("How solid the out-of-reach dots are",
                             self._chart_outside_row))
        self._chart_out_opacity = NoScrollSlider(Qt.Orientation.Horizontal,
                                                 self._chart_outside_row)
        self._chart_out_opacity.setRange(0, 100)
        self._chart_out_opacity.setValue(100)
        self._chart_out_opacity.valueChanged.connect(
            lambda v: self._restyle_the_chart('outside',
                                              'marker.opacity',
                                              v / 100.0))
        out_op_hint = Hint(
            "How much of each out-of-reach dot you can see through, set "
            "separately from the ones that fit.\n\n"
            "Fully solid is right while you are looking for them. Turn it "
            "down when they form a dense shell around everything else — on a "
            "chart where half the patches are out of reach they can close "
            "over the picture completely, and made semi-transparent you can "
            "see the surviving patches and the skin through them while still "
            "knowing where the losses are.\n\n"
            "Untick Show the ones out of reach above to take them away "
            "entirely. Nothing here changes a single count in Are the patches "
            "inside? — those are measured from the colours, not from what is "
            "drawn.", self._chart_outside_row)
        out_op_hint.setObjectName("hint_chart_out_opacity_hint")
        _r2 = QHBoxLayout(); _r2.setContentsMargins(0, 0, 0, 0); _r2.setSpacing(6)
        _r2.addWidget(self._chart_out_opacity, 1)
        _r2.addWidget(out_op_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        orl.addLayout(_r2)
        clv.addWidget(self._chart_outside_row)

        clv.addWidget(QLabel("A skin over the patches",
                             self._chart_look_box))
        self._chart_skin = NoScrollComboBox(self._chart_look_box)
        self._chart_skin.addItem("No skin — the dots on their own", "none")
        self._chart_skin.addItem("Outline only", "outline")
        self._chart_skin.addItem("Mesh", "mesh")
        self._chart_skin.addItem("Solid", "solid")
        self._chart_skin.currentIndexChanged.connect(self._on_chart_skin)
        skin_hint = Hint(
            "Draws a closed surface over the patches, so you can see how far "
            "out this chart reaches instead of judging it from a cloud of "
            "dots. Start with Outline only — it shows the shape without "
            "hiding anything inside it. Mesh adds a fine net over the "
            "surface; Solid is the surface on its own.\n\n"
            "IT LOOKS FACETED, AND THAT IS THE SHAPE RATHER THAN A FAULT. "
            "A skin is stretched over a few hundred scattered patches, so "
            "it is made of large flat triangles meeting at real angles, and "
            "each one catches the light differently — long fan-shaped "
            "streaks across the surface are those triangles. They are there "
            "just as much when the skin is fully solid, which is drawn a "
            "completely different way, so nothing about being see-through "
            "causes them. A gamut built from a measured chart looks smooth "
            "by comparison because it is built from far more points.\n\n"
            "IT IS NOT A GAMUT, and the difference matters. A gamut is the "
            "boundary of everything a paper can print. This is a skin over "
            "the patches one chart happens to ask for, and a chart only "
            "samples wherever its author chose to put a patch. On the demo "
            "files the skin comes out 8% smaller than the paper's own "
            "measured gamut — 663,257 against 724,277 cubic Lab units — "
            "purely because the chart puts no patch on some parts of the "
            "boundary. Read as a gamut it would understate the paper every "
            "time, so it is never counted in How much colour it holds and "
            "never joins a comparison.\n\n"
            "WHEN A PAPER IS OPEN the skin covers only the patches that "
            "paper can reach. There is deliberately no skin over the ones "
            "out of reach: those are the furthest out, so they wrap around "
            "the rest, and a shape drawn round them came to 87% of a shape "
            "round the whole chart. It would fill the picture and read as "
            "\"almost all of this is lost\" on a chart where a third of it "
            "is.\n\n"
            "A chart whose patches all lie on one plane — a grey ramp, a "
            "single hue sweep — encloses no solid, so no skin is drawn for "
            "it.", self._chart_look_box)
        skin_hint.setObjectName("hint_chart_skin_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0); _r.setSpacing(6)
        _r.addWidget(self._chart_skin, 1)
        _r.addWidget(skin_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        clv.addLayout(_r)

        self._chart_skin_row = QWidget(self._chart_look_box)
        srl = QVBoxLayout(self._chart_skin_row)
        srl.setContentsMargins(0, 0, 0, 0)
        srl.setSpacing(4)
        srl.addWidget(QLabel("What colour the skin is", self._chart_skin_row))
        self._chart_skin_colour = NoScrollComboBox(self._chart_skin_row)
        self._chart_skin_colour.addItem("Grey — let the dots carry the colour",
                                        "grey")
        self._chart_skin_colour.addItem("The colours of the patches",
                                        "patches")
        self._chart_skin_colour.addItem("The accent colour", "accent")
        self._chart_skin_colour.currentIndexChanged.connect(
            lambda _i: self._redraw())
        skin_colour_hint = Hint(
            "Grey is the one to start with. The dots inside are already "
            "painted with the colours those patches will print as, and a "
            "coloured skin over the top competes with them — you end up "
            "reading the skin's colour instead of the patches'.\n\n"
            "Choose the colours of the patches when the skin is the subject "
            "rather than the dots: for a picture of the chart's reach on its "
            "own, or with the dots turned right down in size. The skin then "
            "takes its colour from the patches it is stretched over, the same "
            "way a measured gamut takes its colour from the measurements.\n\n"
            "Either way the shape is identical. This changes only what it is "
            "painted with.", self._chart_skin_row)
        skin_colour_hint.setObjectName("hint_chart_skin_colour_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0); _r.setSpacing(6)
        _r.addWidget(self._chart_skin_colour, 1)
        _r.addWidget(skin_colour_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        srl.addLayout(_r)
        srl.addWidget(QLabel("How solid the skin is", self._chart_skin_row))
        self._chart_skin_opacity = NoScrollSlider(
            Qt.Orientation.Horizontal, self._chart_skin_row)
        self._chart_skin_opacity.setRange(0, 100)
        self._chart_skin_opacity.setValue(30)
        self._chart_skin_opacity.valueChanged.connect(
            lambda v: self._restyle_the_chart('skin', 'opacity',
                                              v / 100.0))
        skin_opacity_hint = Hint(
            "How much of the skin you can see through. Low is nearly clear, "
            "high is nearly solid.\n\n"
            "Keep it low while the dots matter — the whole point of a skin "
            "over a chart is to show its reach WITHOUT hiding the patches "
            "inside, and a solid one turns them into a blank shell. Around a "
            "third of the way along is enough to read the shape.\n\n"
            "Turn it up when the shape itself is the subject, or when you are "
            "saving a picture for somebody who will only look at it once. "
            "This has no effect while the skin is set to Outline only, which "
            "draws the cage and no surface at all.", self._chart_skin_row)
        skin_opacity_hint.setObjectName("hint_chart_skin_opacity_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0); _r.setSpacing(6)
        _r.addWidget(self._chart_skin_opacity, 1)
        _r.addWidget(skin_opacity_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        srl.addLayout(_r)
        self._chart_skin_row.setVisible(False)
        clv.addWidget(self._chart_skin_row)

        self._chart_look_box.setVisible(False)
        v.addWidget(self._chart_look_box)

        # --- colour science ---------------------------------------------------
        g_cs = QGroupBox("What the colours are measured against", col)
        cv = QVBoxLayout(g_cs)
        self._white = NoScrollComboBox(g_cs)
        self._white.addItem("Daylight D50 — for print", "D50")
        self._white.addItem("Daylight D65 — for screens", "D65")
        self._white.currentIndexChanged.connect(self._on_white_changed)
        cv.addWidget(self._white)
        self._relative = QCheckBox("Judge each paper against its own white", g_cs)
        self._relative.stateChanged.connect(self._rebuild)
        rel_hint = Hint(
            "Papers are not equally bright — a warm rag paper starts off duller "
            "than a bright glossy one. Tick this and each paper is judged "
            "against its own white, so two papers can be compared fairly on "
            "shape rather than on brightness. This is what happens anyway when "
            "you print with a normal profile. Leave it unticked to see the raw "
            "numbers your instrument reported.", g_cs)
        rel_hint.setObjectName("hint_rel_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._relative, 1)
        _r.addWidget(rel_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        cv.addLayout(_r)

        cv.addWidget(QLabel("Draw it in", g_cs))
        self._space = NoScrollComboBox(g_cs)
        self._space.addItem("CIELAB — for print", "lab")
        self._space.addItem("CIELUV — for displays", "luv")
        self._space.addItem("CIE XYZ — the raw measurement", "xyz")
        self._space.addItem("Ink amounts — a chart on its own", "rgb")
        self._space.currentIndexChanged.connect(self._on_space_changed)
        space_hint = Hint(
            "CIELAB is the one to use for print, and the one every number in "
            "this window is quoted in unless you change it. It is built so "
            "that moving the same distance anywhere in it looks like the same "
            "size of change, which is what makes a volume worth comparing.\n\n"
            "CIELUV has exactly the same lightness but arranges the colours "
            "differently. It is the space displays and light sources are "
            "usually described in, and it stretches the blues and greens, so "
            "the same paper looks like a different shape.\n\n"
            "CIE XYZ is the measurement before any of that is applied. It is "
            "the honest raw form and it is deliberately not uniform: equal "
            "distances in it do not look equally different, so shapes drawn "
            "in it are hard to judge by eye. It has no lightness axis and no "
            "grey axis either, so the slice, the rings and the greys are not "
            "available while it is chosen.\n\n"
            "INK AMOUNTS is not a colour space at all, and it is the one "
            "choice here that changes what the window is for. The three axes "
            "are the printer's own controls — how much red, green and blue "
            "ink to lay down, each from 0 to 100 — which is exactly what a "
            "chart file contains. So a chart can be looked at here on its "
            "own, with no profile and no measurement, and what you see is the "
            "patch set itself: how evenly it samples the printer's range, "
            "where it crowds, and where it leaves a hole.\n\n"
            "Nothing else can be drawn beside it, and that is not a "
            "limitation being apologised for. Every RGB printer's boundary in "
            "its own ink amounts is the same full cube, on every paper — so a "
            "paper drawn here would be a shape that is perfectly true and "
            "tells you nothing. The papers and profiles you have open stay "
            "open and come back the moment you choose CIELAB again.\n\n"
            "A profile is still worth choosing under Placed through while you "
            "are here. It cannot move the dots — the ink amounts are where "
            "they are — but it is the only thing that can say what colour "
            "each one will come out, so it paints them, and it lets the "
            "patches be counted against a paper you have open.\n\n"
            "Volumes and percentages are only comparable within one space. "
            "Change this and every number changes with it — that is expected, "
            "not a fault.", g_cs)
        space_hint.setObjectName("hint_space_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._space, 1)
        _r.addWidget(space_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        cv.addLayout(_r)
        v.addWidget(g_cs)

        # --- appearance -------------------------------------------------------
        g_look = QGroupBox("How it looks", col)
        lv = QVBoxLayout(g_look)

        # THE NAMES UNDER THE PICTURE ARE BUTTONS, and nothing said so. Every
        # 3D view here has had that behaviour from the start — it is Plotly's
        # own — and somebody who does not already know it has no way to find
        # it. Said once, at the top of the group about how the picture looks,
        # because it applies to every shape in it rather than to one control.
        legend_note = WrappedLabel(
            "Click a name under the picture to hide or show that shape.",
            g_look)
        legend_note.setObjectName("hint"); _wrapped(legend_note)
        legend_hint = Hint(
            "The names along the bottom of the picture are not just a key — "
            "each one is a switch.\n\n"
            "CLICK A NAME to take that shape out of the picture, and click it "
            "again to bring it back. Nothing is closed and no number changes: "
            "the file stays open, every figure in this panel stays exactly as "
            "it was, and only the drawing of it goes. It is the quickest way "
            "to answer \"which of these am I actually looking at\" when two "
            "shapes overlap, or to lift a solid paper off a chart's patches "
            "for a moment without changing a single setting.\n\n"
            "DOUBLE-CLICK A NAME to show that one on its own and hide "
            "everything else. Double-click it again to bring the rest back.\n\n"
            "It works for every name there: the papers, the comparison, the "
            "measured patches, a chart's patches, the ones out of reach and "
            "the skin over them — so a chart can be looked at with its lost "
            "patches hidden without ever touching Show the ones out of "
            "reach.\n\n"
            "What you hide this way is a way of LOOKING, not a setting. It is "
            "not remembered, and a picture saved while something is hidden is "
            "saved with everything in it, because the hiding lives in the page "
            "on screen rather than in what was drawn.", g_look)
        legend_hint.setObjectName("hint_legend_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0); _r.setSpacing(6)
        _r.addWidget(legend_note, 1)
        _r.addWidget(legend_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_r)

        self._target = NoScrollComboBox(g_look)
        # THE NAME BELONGS BESIDE THE CONTROL, ONCE -- not inside every item.
        # Carried in the item text it was repeated on all four lines of the
        # open list, where the only thing that differs is the value.
        self._target.addItem("all shapes", "all")
        self._target.addItem("the first shape", 0)
        self._target.addItem("the second shape", 1)
        self._target.addItem("the comparison", 2)
        self._target.currentIndexChanged.connect(self._on_target_changed)
        target_hint = Hint(
            "Everything below applies to whatever is chosen here. Leave it on "
            "all shapes and one change moves them all, which is what "
            "you want most of the time. Pick a single shape and only that one "
            "changes — so you can, for instance, have your own chart solid and "
            "fully opaque while the thing you are comparing against is a faint "
            "outline behind it. A shape you have set on its own keeps its own "
            "value and stops following the shared one.", g_look)
        target_hint.setObjectName("hint_target_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        target_name = QLabel("Set this for", g_look)
        _r.addWidget(target_name)
        _r.addWidget(self._target, 1)
        _r.addWidget(target_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_r)
        orow = QHBoxLayout()
        # KEPT, so it can be greyed out with the slider it names. A bright
        # label over a dead control says the control is live.
        self._opacity_name = QLabel("How solid it looks", g_look)
        orow.addWidget(self._opacity_name)
        self._opacity = NoScrollSlider(Qt.Orientation.Horizontal, g_look)
        # FULLY OPAQUE BY DEFAULT. Any transparency blends the shape with
        # whatever is behind it -- which darkens colours on a dark background
        # and washes them out on a light one, so the same setting flattered one
        # appearance and spoiled the other. Solid shows the measured colours as
        # they are; the slider is there for looking inside two shapes at once.
        # AND IT GOES ALL THE WAY DOWN. The floor was 15%, on the reasoning
        # that a shape nobody can see is a shape nobody can find again -- but
        # the picture already answers that: every shape has its name under it
        # and clicking the name brings it back, which is what the note above
        # this slider says. A control that stops short of what its label
        # promises is the smaller of the two faults. Reported plainly: "i
        # can't turn how solid it looks completely down to 0".
        #
        # At 0 the surface is gone and its outline, its rings and its name
        # remain -- which is a useful state in its own right: the shape's
        # extent without anything hiding what is inside it.
        self._opacity.setRange(0, 100); self._opacity.setValue(100)
        self._opacity.valueChanged.connect(self._on_opacity_changed)
        # RECORDED ON EVERY STEP, not only when the handle is let go. The
        # slider writes its own value to the settings on every step already;
        # the record the renderer reads was written on release alone, so the
        # two copies of one number parted company the moment somebody dragged
        # and quit -- and the settings are written eagerly precisely because
        # quitting mid-anything is the case they are for.
        #
        # Measured before the fix, by opening a second window afterwards: the
        # slider came back saying 0.64 beside a shape drawn at 0.37. A control
        # that says something untrue about the picture beside it is the fault
        # this window has been reported for twice.
        self._opacity.valueChanged.connect(
            lambda _v: self._remember_shape_setting("opacity"))
        self._opacity.valueChanged.connect(
            lambda _v: self._say_if_two_solids_will_show_the_seam())
        self._opacity.sliderReleased.connect(
            lambda: self._after_shape_setting("opacity"))
        orow.addWidget(self._opacity, 1)
        self._opacity_lbl = QLabel("100%", g_look)
        self._opacity_lbl.setFixedWidth(38)
        self._opacity.valueChanged.connect(
            lambda x: self._opacity_lbl.setText(f"{x}%"))
        self._opacity_live = True
        orow.addWidget(self._opacity_lbl)
        lv.addLayout(orow)
        self._aspect = NoScrollComboBox(g_look)
        # Named beside the box like every other row here. "True proportions"
        # was doing double duty as the name AND the value, which reads fine on
        # its own and reads as a missing label once its neighbours have one.
        # Measured: the box gives the text 133px, so "true to the
        # measurements" (158px) cannot be said here. The ⓘ beside it carries
        # the full explanation, which is what it is for.
        self._aspect.addItem("as measured", "data")
        self._aspect.addItem("evened into a cube", "cube")
        self._aspect.currentIndexChanged.connect(self._redraw)
        aspect_hint = Hint(
            "Left as measured, one step of colour difference is drawn the same "
            "length whichever direction it goes in, which is what makes the "
            "shape and the amount below honest. Printers have roughly twice as "
            "much range in colour as they do from black to white, so the true "
            "shape really is wide and flat — that is your printer, not a "
            "drawing error. Evened into a cube it is easier on the eye, and no "
            "longer to scale: use it to look around inside the shape, and come "
            "back to as measured before you judge how big it is.", g_look)
        aspect_hint.setObjectName("hint_aspect_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        aspect_name = QLabel("Proportions", g_look)
        _r.addWidget(aspect_name)
        _r.addWidget(self._aspect, 1)
        _r.addWidget(aspect_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_r)
        # THE WORDS SOMEBODY LOOKING FOR IT WOULD USE. Reported twice, and
        # the second time as a question rather than a fault: "the room / the
        # walls / the grid or whatever it is called behind the shape is
        # missing", and then "it is ok when this wall can be turned off and on
        # but i'd need to know the option that does it". The switch was called
        # "Show the box and its grid", which is accurate and is not what the
        # thing is called by the person hunting for it.
        self._grid_on = QCheckBox("Show the walls, the grid and the numbers",
                                  g_look)
        self._grid_on.setChecked(True)
        self._grid_on.stateChanged.connect(self._on_grid_changed)
        lv.addWidget(self._grid_on)
        grid_hint = Hint(
            "The box the shape sits in: the three walls behind it, the grid "
            "on them, the numbers up the sides and the names of the axes.\n\n"
            "Leave it on while you are reading the shape. It is what tells "
            "you how light a part of the surface is, or how far out into the "
            "reds it reaches — without it you can see the shape but you "
            "cannot say where anything is.\n\n"
            "Turn it off for a picture meant for somebody else. The shape is "
            "left floating on the page with nothing around it, which looks "
            "much better in a document, on a slide or in a forum post, and it "
            "is what Save this view as a web page will then write out.\n\n"
            "It applies to the whole picture, so with two rooms side by side "
            "both of them lose the box together and the pair still match.",
            g_look)
        grid_hint.setObjectName("hint_grid_hint")
        lv.addWidget(grid_hint)
        self._style_mine = NoScrollComboBox(g_look)
        self._style_second = NoScrollComboBox(g_look)
        self._style_other = NoScrollComboBox(g_look)
        self._style_combos = (
            (self._style_mine, "First shape"),
            (self._style_second, "Second shape"),
            # "Comparison", not "The comparison": the name column is taken out
            # of the control's width, and the extra word cost enough of it to
            # clip "solid with its mesh" in the box beside it.
            (self._style_other, "Comparison"),
        )
        # ONE GRID for the three, so the names line up and the three controls
        # start at the same edge. Ragged labels on rows that sit directly under
        # each other read as a mistake rather than as three separate rows.
        _sg = QGridLayout()
        _sg.setContentsMargins(0, 0, 0, 0)
        _sg.setHorizontalSpacing(6)
        _sg.setVerticalSpacing(4)
        _sg.setColumnStretch(1, 1)
        self._style_labels = []
        for _row, (combo, label) in enumerate(self._style_combos):
            combo.addItem("solid", "solid")
            combo.addItem("solid with its mesh", "solid+mesh")
            combo.addItem("outline only", "mesh")
            combo.currentIndexChanged.connect(self._redraw)
            combo.setVisible(False)
            name = QLabel(label, g_look)
            name.setVisible(False)   # kept with its combo by _refresh_style_controls
            self._style_labels.append(name)
            _sg.addWidget(name, _row, 0)
            _sg.addWidget(combo, _row, 1)
        # An outer shape starts as a cage so whatever is inside stays visible.
        self._style_second.setCurrentIndex(2)
        self._style_other.setCurrentIndex(2)
        # WHEN TWO SEE-THROUGH SOLIDS CUT THROUGH EACH OTHER, and only then.
        #
        # Measured on the run's two shells, in the state it was reported from:
        #
        #     both solid, 68%        wedges bitten out of the yellow flank
        #     both solid, 100%       clean
        #     one solid, one mesh    clean
        #
        # It is not the draw order -- that is sorted, and sorting cannot help
        # two surfaces that pass through one another, because no single order
        # is right for them. Nothing in the drawing library can: what is drawn
        # is what a graphics card does with two transparent skins that
        # intersect. So the window says so, in the one state where it happens,
        # and names the two ways out.
        self._two_solids_note = WrappedLabel("", g_look, hide_when_empty=True)
        self._two_solids_note.setObjectName("hint")
        _wrapped(self._two_solids_note)
        lv.addWidget(self._two_solids_note)
        style_hint = Hint(
            "Each shape on screen is drawn its own way. A solid shape hides "
            "whatever is inside it, so the outer one starts as an outline — "
            "which is the only way to look at your printer sitting inside "
            "sRGB, or inside everything the eye can see, and still see your "
            "printer. Swap them round when the other one is the shape you want "
            "to look into.\n\n"
            "This applies while the shapes share one picture. Give them a room "
            "each with Show them in two rooms, side by side and every one is "
            "drawn solid — there is nothing behind it to see through, so an "
            "outline would only show you less of the same gamut.", g_look)
        style_hint.setObjectName("hint_style_hint")
        # One explanation covers all three rows, so it sits beside the FIRST of
        # them. Beside the last, it went with the comparison -- and with no
        # comparison loaded the explanation disappeared while two of the three
        # controls it describes were still on screen.
        _sg.addWidget(style_hint, 0, 2, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_sg)
        # Every drop-down in this group opens its box at the same edge. A few
        # pixels apart is the worst of both: not aligned, and close enough that
        # it reads as a slip rather than as five separate rows.
        self._name_column = [target_name, aspect_name, *self._style_labels]
        self._align_names()
        self._slice_on = QCheckBox("Slice it at one lightness", g_look)
        self._slice_on.stateChanged.connect(self._redraw)
        self._slice_on.stateChanged.connect(
            lambda *_a: self._apply_spin_availability())
        self._slice_on.stateChanged.connect(
            lambda *_a: self._apply_flat_availability())
        lv.addWidget(self._slice_on)
        slice_hint = Hint(
            "Swaps the solid shape for a flat cross-section: one horizontal "
            "slice through it, at the lightness you choose with the slider "
            "below.\n\n"
            "This is the view that answers 'how far does each one reach in "
            "each direction' without you having to judge it through a "
            "three-dimensional shape. Two outlines lying on the same flat "
            "picture can be compared at a glance — where one bulges past the "
            "other, and by how much — which is genuinely hard to do by eye "
            "when both are solids you are turning around.\n\n"
            "The mid-tones are usually where two papers differ most, so L* 50 "
            "is a good place to start. Slide down towards the shadows to see "
            "which of them holds on to deep colour, and up towards the "
            "highlights to see where each one runs out.\n\n"
            "Everything you have chosen about the shapes still applies — the "
            "colours, what is out of reach, which of them are shown. What "
            "goes away is the turning: a flat picture has no angle to be "
            "seen from, so the movement controls have nothing to do until you "
            "untick this and the shape comes back exactly as it was.", g_look)
        slice_hint.setObjectName("hint_slice_hint")
        lv.addWidget(slice_hint)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Lightness", g_look))
        self._slice_at = NoScrollSlider(Qt.Orientation.Horizontal, g_look)
        self._slice_at.setRange(0, 100)
        self._slice_at.setValue(50)
        self._slice_at.valueChanged.connect(self._on_cut_changed)
        self._slice_at.sliderReleased.connect(self._after_cut)
        srow.addWidget(self._slice_at, 1)
        self._slice_lbl = QLabel("L* 50", g_look)
        self._slice_lbl.setFixedWidth(46)
        srow.addWidget(self._slice_lbl)
        lv.addLayout(srow)
        slice_hint = Hint(
            "Cuts straight through every shape at the lightness you choose and "
            "draws the result flat, looking down. Two shapes in 3D hide each "
            "other and depth is hard to judge on a screen; two outlines side by "
            "side are simply readable — which one reaches further into the "
            "cyans at this lightness is a glance rather than a guess. Move the "
            "slider from dark to light to see how the shape changes.\n\n"
            "Two shapes are drawn over each other here, which is usually what "
            "you want for a cut. If you would rather have them apart, tick "
            "Show them in two rooms, side by side as well and each gets its "
            "own half — both on one shared scale, so a smaller gamut still "
            "looks smaller.", g_look)
        slice_hint.setObjectName("hint_slice_hint")
        lv.addWidget(slice_hint)
        drow = QHBoxLayout()
        self._depth_name = QLabel("Depth", g_look)
        drow.addWidget(self._depth_name)
        self._depth = NoScrollSlider(Qt.Orientation.Horizontal, g_look)
        self._depth.setRange(0, 100)
        self._depth.setValue(35)
        self._depth.valueChanged.connect(self._on_depth_changed)
        # Same reasoning as the solidity slider above: recorded as it moves,
        # so a window opened later cannot disagree with its own control.
        self._depth.valueChanged.connect(
            lambda _v: self._remember_shape_setting("depth"))
        self._depth.sliderReleased.connect(
            lambda: self._after_shape_setting("depth"))
        drow.addWidget(self._depth, 1)
        self._depth_lbl = QLabel("35%", g_look)
        self._depth_lbl.setFixedWidth(46)
        drow.addWidget(self._depth_lbl)
        lv.addLayout(drow)
        depth_hint = Hint(
            "How much the surface is shaded. At nothing it is lit evenly and "
            "you see only its colours, which is the honest picture; turning it "
            "up trades some of that for shading, which is what makes a rounded "
            "thing look rounded and a dent look like a dent. It moves as you "
            "drag, so you can stop wherever the shape reads best to you.",
            g_look)
        depth_hint.setObjectName("hint_depth_hint")
        lv.addWidget(depth_hint)

        self._manual_light = QCheckBox("Set the lighting myself", g_look)
        self._manual_light.stateChanged.connect(self._on_manual_light)
        lv.addWidget(self._manual_light)
        self._light_rows = []
        self._light_sliders = {}
        for key, label, lo, hi, start in LIGHT_CONTROLS:
            row = QWidget(g_look)
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(1)
            cap = QLabel(label, row)
            cap.setObjectName("hint")
            rl.addWidget(cap)
            hb = QHBoxLayout()
            slider = NoScrollSlider(Qt.Orientation.Horizontal, row)
            slider.setRange(0, 100)
            slider.setValue(int(round((start - lo) / (hi - lo) * 100)))
            value_lbl = QLabel(f"{start:.2f}", row)
            value_lbl.setFixedWidth(46)
            slider.valueChanged.connect(
                lambda v, k=key, lo=lo, hi=hi, lbl=value_lbl:
                self._on_light_changed(k, lo + (hi - lo) * v / 100.0, lbl))
            hb.addWidget(slider, 1)
            hb.addWidget(value_lbl)
            rl.addLayout(hb)
            row.setVisible(False)
            lv.addWidget(row)
            self._light_rows.append(row)
            self._light_sliders[key] = (slider, lo, hi)
        light_hint = Hint(
            "Everything about the light in the 3D view, for anybody who wants "
            "to dial in a particular look. Nothing here changes a single "
            "measurement — it only changes how the shape is lit.\n\n"
            "HOW BRIGHT, AND HOW SOFT.\n"
            "Ambient is light arriving from every direction at once, so more "
            "of it flattens the shape and shows its colours plainly. Diffuse "
            "is light the surface scatters, which is what makes a curve look "
            "curved. Specular is the shiny highlight and Roughness decides "
            "how soft that highlight is — a low roughness gives a small hard "
            "glint, a high one a broad sheen. Fresnel adds a glow around the "
            "edges, where a real surface catches the light at a glancing "
            "angle.\n\n"
            "WHERE IT SHINES FROM.\n"
            "Which side the light comes from swings it around the shape, like "
            "walking a lamp around a table: 0 is straight ahead, 90 is off to "
            "one side. How high the light hangs lifts it from below the shape "
            "(-1) through level with it (0) to directly overhead (+1).\n\n"
            "A light high and a little to one side is the usual choice, and "
            "it is what you get with this switched off. Moving it lower "
            "throws longer shadows across the surface, which can make a "
            "shallow dent easier to see.\n\n"
            "Every one of them moves the picture as you drag.", g_look)
        light_hint.setObjectName("hint_light_hint")
        lv.addWidget(light_hint)
        self._light_rows.append(light_hint)

        v_paint = self._paint_label = QLabel(
            "How the shapes are coloured", g_look)
        lv.addWidget(v_paint)
        self._paint_group = QButtonGroup(self)
        self._paint_radios = {}
        paint_grid = QGridLayout()
        paint_grid.setContentsMargins(0, 0, 0, 10)
        # Real space between the rows. Without it the grid was handed one
        # pixel less than the buttons are tall and they touched.
        paint_grid.setVerticalSpacing(6)
        paint_grid.setHorizontalSpacing(16)
        for i, (key, label) in enumerate(PAINTS):
            radio = QRadioButton(label, g_look)
            # Set here, not only in the stylesheet. A QSS min-height is applied
            # at polish, which happens AFTER the grid has worked out its row
            # heights from the unstyled metrics -- so the rows were sized for a
            # 14px button that then drew 20px tall and ran into the row below.
            radio.setMinimumHeight(TICK_ROW)
            self._paint_group.addButton(radio)
            radio.toggled.connect(
                lambda on, which=key: self._set_paint(which) if on else None)
            self._paint_radios[key] = radio
            paint_grid.addWidget(radio, i // 2, i % 2)
        # AND THE ROWS THEMSELVES, not only the buttons in them. Setting the
        # floor on the widget is not enough: the grid had already answered
        # "18 pixels a row" and does not ask again, so the buttons drew 20 into
        # rows 17 apart. Told directly, the grid reserves the room first and
        # the six pixels of spacing beside it are then real.
        for _row in range((len(PAINTS) + 1) // 2):
            paint_grid.setRowMinimumHeight(_row, TICK_ROW)
        lv.addLayout(paint_grid)
        # Directly under the radios it describes. It used to sit further down
        # the column, immediately below the rings explanation, so two "What
        # this does" lines stacked up and the lower one pointed at a control
        # three settings away.
        paint_hint = Hint(
            "True colours paints every point the colour it represents, which "
            "is the honest picture of one gamut. One colour each is easier "
            "when two shapes overlap — you can tell at a glance which is "
            "which. By lightness and by chroma throw away the hue on purpose, "
            "so the shape itself is what you see.", g_look)
        paint_hint.setObjectName("hint_paint_hint")
        lv.addWidget(paint_hint)
        # THE OUTLINE'S COLOUR IS ITS OWN QUESTION.
        #
        # This was a tick, "Colour the outlines too", and a tick can only say
        # "the same as the shape". So one genuinely useful picture could not
        # be reached at all: the solid drained to grey by lightness, so that
        # its FORM reads, with the cage over it still carrying the real
        # colours. Asked for in exactly those terms -- colourful outlines,
        # independent of whether the shape itself is grey or colourful.
        #
        # The five fixed choices are taken from PAINTS rather than typed out
        # again, so the outline can never end up offering a painting the
        # shapes do not, or missing one they gained.
        self._outline_paint = NoScrollComboBox(g_look)
        self._outline_paint.addItem("plain grey", "plain")
        # SHORTER BECAUSE THE COLUMN IS AS WIDE AS ITS WIDEST DROP-DOWN.
        # Measured: this entry wanted 145 px of text, which made its box 210
        # and its row 330 -- the widest thing in the whole column, and so the
        # number every other section was stretched to. "as the shapes" says
        # the same thing in 88.
        self._outline_paint.addItem("as the shapes", "match")
        # Lower-cased from the radios above rather than typed out again: the
        # combos on this panel read as the end of their label ("Proportions:
        # as measured"), the radios are sentences of their own, and one list
        # written twice is one list that will disagree with itself.
        for _key, _label in PAINTS:
            self._outline_paint.addItem(_label[0].lower() + _label[1:], _key)
        self._outline_paint.currentIndexChanged.connect(
            lambda: self._after_shape_setting("mesh_paint"))
        mesh_hint = Hint(
            "An outline is the wire cage of a shape. You have one on screen "
            "whenever First shape, Second shape or Comparison is set to "
            "outline only or to solid with its mesh — without one, this "
            "setting has nothing to change.\n\n"
            "Plain grey is the starting point, and it is the right one on top "
            "of a solid shape: hundreds of thin lines in the colours "
            "underneath compete with those colours instead of showing the "
            "form. Choose as the shapes and the cage stays in step "
            "with whatever you pick above under How the shapes are coloured, "
            "so changing one changes both.\n\n"
            "The five below that ignore the shapes entirely, which is the "
            "whole point of them. The picture worth knowing about: set How "
            "the shapes are coloured to By lightness, so the solid drains to "
            "grey and its form is what you see, and set this to true colours "
            "— now the cage over it still carries the colour each point "
            "really is. Every shape can be given its own, using Set this for "
            "at the top of this panel.", g_look)
        mesh_hint.setObjectName("hint_mesh_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(QLabel("Outline colour", g_look))
        _r.addWidget(self._outline_paint, 1)
        _r.addWidget(mesh_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_r)

        rrow = QHBoxLayout()
        self._rings_on = QCheckBox("Show rings inside", g_look)
        self._rings_on.stateChanged.connect(
            lambda: self._after_shape_setting("rings"))
        rrow.addWidget(self._rings_on)
        self._rings = NoScrollSlider(Qt.Orientation.Horizontal, g_look)
        self._rings.setRange(1, 20)
        self._rings.setValue(6)
        self._rings.valueChanged.connect(self._on_rings_changed)
        self._rings.sliderReleased.connect(
            lambda: self._after_shape_setting("rings"))
        rrow.addWidget(self._rings, 1)
        self._rings_lbl = QLabel("6", g_look)
        self._rings_lbl.setFixedWidth(28)
        rrow.addWidget(self._rings_lbl)
        lv.addLayout(rrow)
        rings_hint = Hint(
            "A cage shows only the outer surface, because that is what a "
            "gamut is — a solid with a boundary rather than something with "
            "structure inside. These rings are cross-sections stacked within "
            "it, which show how the shape narrows between black and white: "
            "that is what tells you whether your mid-tones or your highlights "
            "are the tight part.", g_look)
        rings_hint.setObjectName("hint_rings_hint")
        lv.addWidget(rings_hint)
        detrow = QHBoxLayout()
        detrow.addWidget(QLabel("Detail", g_look))
        self._detail = NoScrollSlider(Qt.Orientation.Horizontal, g_look)
        self._detail.setRange(6, 40)
        self._detail.setValue(20)
        self._detail.valueChanged.connect(self._on_detail_changed)
        # WHY THIS ONE WAITS AND THE OTHERS DO NOT.
        #
        # Every other live slider changes something the window already has:
        # colours, a strength, a ring count. Detail rebuilds the shape you are
        # comparing against, from nothing -- and then everything drawn beside
        # it has to be re-cut along the new boundary. Measured on his own
        # configuration, that is 160 ms at 20 steps, 297 at 29 and 522 at 40,
        # and it happens on the thread that draws the window. Fired on every
        # step of a drag it would make the HANDLE ITSELF sticky, which is a
        # worse fault than the one being fixed.
        #
        # So the picture catches up whenever the handle pauses, even briefly,
        # and once more when it is let go. What that buys is not speed: it is
        # that the picture changes IN PLACE -- no second of black, no camera
        # thrown back to three-quarters-front -- which is what the report was
        # actually about.
        self._detail_soon = QTimer(self)
        self._detail_soon.setSingleShot(True)
        self._detail_soon.timeout.connect(self._push_detail)
        self._detail.sliderReleased.connect(self._on_detail_released)
        detrow.addWidget(self._detail, 1)
        self._detail_lbl = QLabel("20 steps", g_look)
        self._detail_lbl.setFixedWidth(64)
        detrow.addWidget(self._detail_lbl)
        lv.addLayout(detrow)
        detail_hint = Hint(
            "How finely the shape you compare against is built. Normal is "
            "accurate to within a twentieth of a percent and draws in about a "
            "second; fine is smoother to look at; rough is there for a slow "
            "computer. Your own measured chart is not affected — its detail "
            "comes from how many patches you measured.", g_look)
        detail_hint.setObjectName("hint_detail_hint")
        lv.addWidget(detail_hint)
        # SHORTER BECAUSE THE COLUMN IS AS WIDE AS ITS WIDEST LABEL, and a
        # tick cannot wrap. Measured: this one asked for 270 px, "Keep both
        # rooms pointing the same way" for 272, and the column has to be wider
        # than all of them -- 520 in the end, which was noticed at once: "the
        # left panel used to be less wide". The ⓘ beside each carries what the
        # longer sentence said.
        self._show_lost = QCheckBox("Show what it cannot print",
                                    g_look)
        self._show_lost.stateChanged.connect(self._redraw)
        lost_hint = Hint(
            "Paints your chart by what the thing you are comparing against "
            "cannot reproduce: red where the colour is out of its reach, grey "
            "where it is fine. A percentage tells you how much you lose; this "
            "tells you which colours, so you can decide whether it matters for "
            "the pictures you actually print.", g_look)
        lost_hint.setObjectName("hint_lost_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._show_lost, 1)
        _r.addWidget(lost_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_r)

        # AND WHAT THE OUT-OF-REACH PART IS PAINTED IN. Asked for from the
        # window — "is there a way to turn this magenta out of reach section
        # into the real colors that are out of reach?" — and asked for as an
        # OPTION rather than a new default: "that out of reach in colors thing
        # should be an option not a default that cant be changed".
        self._lost_in_colour = QCheckBox("…in the colours themselves", g_look)
        self._lost_in_colour.stateChanged.connect(self._redraw)
        colour_hint = Hint(
            "Paints the out-of-reach part of the shape in the colours it is "
            "actually made of, instead of one flat red.\n\n"
            "WHAT IT CHANGES: grey still means the comparison can print it. "
            "Everything you can SEE is what you would not get — so instead of "
            "\"you lose this region\", the picture says \"you lose these "
            "colours\", and you can tell a lost deep blue from a lost bright "
            "orange without turning the shape round.\n\n"
            "WHEN THE FLAT RED IS BETTER, and it is the default for this "
            "reason: a colour that is out of reach but dark and close to "
            "neutral is painted a dark, nearly grey colour, which sits very "
            "near the grey that means the opposite. One flat red can be seen "
            "from any angle at any size, so it is the one to keep when you "
            "want to see WHERE the loss is at a glance, or when the picture is "
            "going into a document at postage-stamp size.\n\n"
            "WHAT IT NEEDS: nothing beyond Show what it cannot print, the tick "
            "above — this simply repaints what that already draws. Nothing "
            "measured changes and no number on the screen moves; it travels "
            "into a saved picture or page exactly as you see it here.", g_look)
        colour_hint.setObjectName("hint_lost_colour_hint")
        _rc = QHBoxLayout(); _rc.setContentsMargins(16, 0, 0, 0)
        _rc.setSpacing(6)
        _rc.addWidget(self._lost_in_colour, 1)
        _rc.addWidget(colour_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_rc)

        # WHERE THE SHAPES AGREE, FADED AWAY.
        #
        # A SLIDER RATHER THAN A TICK BOX, and that is a measured decision.
        # Hiding the agreement outright has a cliff in it: a shape that lies
        # entirely inside another disagrees NOWHERE, so every one of its
        # triangles goes and the shape vanishes -- 0 of 978 on the demo pair.
        # That is the correct answer and it looks exactly like a fault. Faded
        # instead, the shape is still faintly there at 40% and the reader can
        # see for themselves that it agrees everywhere.
        #
        # It also has a true do-nothing position. At 100% the picture is what
        # it was, which is what makes a new control safe to leave switched on.
        agrow = QHBoxLayout()
        agrow.addWidget(QLabel("Where they agree", g_look))
        self._agree = NoScrollSlider(Qt.Orientation.Horizontal, g_look)
        self._agree.setRange(0, 100)
        self._agree.setValue(100)
        self._agree.valueChanged.connect(self._on_agree_changed)
        self._agree.sliderReleased.connect(self._after_fade)
        agrow.addWidget(self._agree, 1)
        self._agree_lbl = QLabel("all of it", g_look)
        self._agree_lbl.setFixedWidth(52)
        agrow.addWidget(self._agree_lbl)
        lv.addLayout(agrow)
        agree_hint = Hint(
            "Fades away the part of each shape that the other shapes reach "
            "too, so what is left standing is only where they disagree.\n\n"
            "WHY THIS IS WORTH HAVING. Two papers drawn over each other are "
            "mostly the same paper. The part they share is the bulk of both, "
            "it is drawn twice, and it sits in front of the part where they "
            "differ — which is the only part you put them side by side to "
            "see. Sliding this down dissolves the agreement and leaves the "
            "difference on its own.\n\n"
            "AT THE TOP — “all of it” — nothing is changed at all. The "
            "picture is exactly what it would be without this control, so "
            "you can leave it alone and lose nothing.\n\n"
            "SOMEWHERE IN THE MIDDLE is usually the most useful. Fully "
            "hidden, you lose all sense of how big the agreement was; faint, "
            "you keep the whole shape as context with the difference "
            "standing out of it.\n\n"
            "IF ONE SHAPE DISAPPEARS ENTIRELY, that is your answer and not a "
            "fault: it means that shape lies completely inside the others "
            "and disagrees with them nowhere. Slide back up and you will see "
            "it fade in again, whole.\n\n"
            "AND WHAT IS LEFT IS AN OPEN SHELL, so turning it round you will "
            "at some angles be looking INTO it. A gamut is drawn as a closed "
            "skin with nothing inside; take the shared part away and the skin "
            "has a hole where that part used to be, like a bowl with a bite "
            "out of the rim. Through the hole you see the far wall from "
            "behind — and it is lit exactly like the outside, because there "
            "is no separate inside to shade. So it can look like a broken "
            "surface, or like an outer edge in a place it could not be. "
            "Nothing is wrong with it, and nothing has been left out: turn "
            "the shape a little and the same wall reads as the outside again."
            "\n\nIF YOU WOULD RATHER NOT SEE THAT, the two ways round it are "
            "to slide back up a little — anything above the very bottom keeps "
            "the shape whole and merely faint — or to use “Where they differ” "
            "instead, which leaves the shared bulk standing and closed.\n\n"
            "It needs at least two shapes on screen — one on its own has "
            "nothing to agree with, and the slider is greyed out until a "
            "second arrives.\n\n"
            "WHAT IT IS NOT: this is about the SURFACES, not about volume. "
            "The part left standing is the piece of each boundary that lies "
            "outside the others, and on two shapes that graze each other a "
            "great many boundary points fall just outside while very little "
            "volume does. Read it as “here is where they part company”, and "
            "read the figures on the left for how much colour that is worth.",
            g_look)
        agree_hint.setObjectName("hint_agree_hint")
        lv.addWidget(agree_hint)

        # AND THE OTHER WAY ROUND, because it answers the other question.
        # Fading the shared part asks "where do these two differ?"; fading
        # the differences asks "what can I print on BOTH of them?" -- which
        # is the one a person with two papers and one image actually has.
        # Two plain sliders rather than one that runs both ways: a control
        # whose middle is "normal" and whose two ends mean opposite things
        # takes a paragraph to explain, and these take a line each.
        dfrow = QHBoxLayout()
        dfrow.addWidget(QLabel("Where they differ", g_look))
        self._differ = NoScrollSlider(Qt.Orientation.Horizontal, g_look)
        self._differ.setRange(0, 100)
        self._differ.setValue(100)
        self._differ.valueChanged.connect(self._on_differ_changed)
        self._differ.sliderReleased.connect(self._after_fade)
        dfrow.addWidget(self._differ, 1)
        self._differ_lbl = QLabel("all of it", g_look)
        self._differ_lbl.setFixedWidth(52)
        dfrow.addWidget(self._differ_lbl)
        lv.addLayout(dfrow)
        differ_hint = Hint(
            "The opposite of the slider above: this one fades away the parts "
            "that only ONE of the shapes reaches, leaving the part they all "
            "have in common.\n\n"
            "WHAT IT ANSWERS. “Where they agree” answers *where do these two "
            "differ* — the question you ask when choosing between two papers. "
            "This one answers *what can I print on both of them* — the "
            "question you ask when the same picture has to go out on both, "
            "and you want to know which colours are safe to use. The shape "
            "left standing is the part every measurement on screen can "
            "reach.\n\n"
            "The two work together. Pull this one down and the shared core is "
            "what remains; pull the one above down instead and the "
            "differences are what remain; leave both at the top and nothing "
            "is changed at all.\n\n"
            "AT THE TOP nothing is changed, so you can leave it alone and "
            "lose nothing.\n\n"
            "It needs at least two shapes, and it is about the SURFACES: what "
            "is left is the piece of each boundary that lies inside all the "
            "others, not a solid of the shared volume. The written-out "
            "figures on the left are where volume is answered.", g_look)
        differ_hint.setObjectName("hint_differ_hint")
        lv.addWidget(differ_hint)

        self._neutral = QCheckBox("Show the greys as they came out", g_look)
        self._neutral.stateChanged.connect(self._redraw)
        self._neutral.toggled.connect(self._follow_neutral)
        neutral_hint = Hint(
            "Draws a line through the patches where you asked for an equal "
            "amount of every colour — the greys. What comes back is rarely "
            "neutral: paper is warm or cool, inks are never perfectly "
            "balanced, and the drift is usually worst in the shadows. The "
            "shape of a gamut cannot show this at all, and it is what people "
            "notice first in a black-and-white print.\n\n"
            "The line runs up the INSIDE of the shape, so the shape is turned "
            "down to about a third when you tick this — at full strength it is "
            "an opaque solid and the line is hidden behind it. How solid it "
            "looks is yours to set from there; it will not be changed "
            "again.", g_look)
        neutral_hint.setObjectName("hint_neutral_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._neutral, 1)
        _r.addWidget(neutral_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_r)

        # A NAME THAT STANDS ON ITS OWN. It began "…and a perfectly neutral
        # line", which only reads as anything after the line above it -- and
        # that made sense while the two were tied together. They are not any
        # more, so each says what it draws: one is what your greys DID, the
        # other is where perfectly neutral greys WOULD run.
        self._ideal_neutral = QCheckBox("Show a perfectly neutral line",
                                        g_look)
        self._ideal_neutral.toggled.connect(
            lambda on: self._make_room_to_see_inside() if on else None)
        self._ideal_neutral.stateChanged.connect(self._redraw)
        ideal_hint = Hint(
            "Adds a second, quieter line: where the greys would run if they "
            "were perfectly neutral — no colour at all, only lightness.\n\n"
            "IT IS THERE TO LEAN AGAINST. On its own, a wandering grey line is "
            "hard to read: you cannot tell by eye whether it is drifting or "
            "whether you are looking at it from an angle. With a straight one "
            "beside it the answer is immediate, and so is which way and at "
            "which lightness — a lean towards yellow in the midtones and back "
            "towards blue in the shadows is a very different fault from a "
            "steady warm cast all the way up, and they are told apart at a "
            "glance rather than by squinting.\n\n"
            "It runs over exactly the range your own greys cover — from your "
            "blackest black to your paper white — and not from black to white "
            "in the abstract. Your printer cannot reach either extreme and "
            "nothing here suggests it should have: the question this answers "
            "is how far the greys LEAN, not how far they reach.\n\n"
            "It is dotted and pale on purpose. It is not a measurement of "
            "anything you printed — it is the definition of neutral, drawn in "
            "the same space, so the two can be compared directly.\n\n"
            "Turn the shape down with How solid it looks to see both "
            "lines properly: at full strength the surface is opaque and "
            "everything inside it is hidden.", g_look)
        ideal_hint.setObjectName("hint_ideal_hint")
        # NO INDENT. It was inset by 16 px to read as a sub-option of the
        # greys above it, which is what it was. Now that the two are set
        # independently the indent says something untrue, and it showed:
        # "their checkboxes are not aligned, the neutral line's one (and in
        # turn the label itself) is a little more to the right".
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._ideal_neutral, 1)
        _r.addWidget(ideal_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_r)

        self._points = QCheckBox("Show every patch I measured", g_look)
        self._points.stateChanged.connect(self._redraw)
        lv.addWidget(self._points)
        points_hint = Hint(
            "Draws every patch of the chart as a small dot in its own colour, "
            "inside the shape they produced.\n\n"
            "This is the evidence the shape is built from, and it answers a "
            "question the smooth surface hides: where did the chart actually "
            "sample, and where is the boundary a guess between two widely "
            "spaced patches? A dense cloud means the edge is well measured; a "
            "sparse one at the corners means the shape there is an "
            "interpolation.\n\n"
            "It is worth a look when a gamut seems surprisingly large or "
            "oddly shaped — a boundary drawn from very few points in that "
            "region is the usual explanation.", g_look)
        points_hint.setObjectName("hint_points_hint")
        lv.addWidget(points_hint)

        self._side_by_side = QCheckBox("Two rooms, side by side",
                                       g_look)
        self._side_by_side.stateChanged.connect(self._on_side_by_side)
        lv.addWidget(self._side_by_side)
        side_hint = Hint(
            "Two shapes in one picture is the right way to see where one "
            "reaches past the other — but it is the wrong way to judge either "
            "on its own, because the shape in front hides the one behind it "
            "and whichever is drawn on top looks bigger than it is.\n\n"
            "Tick this and each gets a room of its own, side by side. The "
            "question changes from \"where do they differ\" to \"what does "
            "each of these actually look like\", and both are worth asking.\n\n"
            "It needs two shapes to show — a second file, or one file and "
            "something to compare it with — so it does nothing until you have "
            "them.\n\n"
            "It works on the flat cross-section too. Tick Slice it at one "
            "lightness as well and you get the two cuts next to each other, "
            "drawn on one shared scale so their sizes can honestly be "
            "compared — which is the whole reason to put them side by side "
            "rather than on top of one another.", g_look)
        side_hint.setObjectName("hint_side_hint")
        lv.addWidget(side_hint)

        # A CONTAINER, hidden as a whole. Hiding the check box on its own left
        # its spacing behind, so the option under it sat seven pixels lower
        # than every other option in this group -- small, and the sort of
        # thing that reads as untidiness without anybody seeing why. The
        # lighting rows are built this way for the same reason.
        self._link_row = QWidget(g_look)
        _lr = QVBoxLayout(self._link_row)
        _lr.setContentsMargins(0, 0, 0, 0)
        _lr.setSpacing(4)
        self._link_cameras = QCheckBox("Both rooms point the same way",
                                       self._link_row)
        self._link_cameras.setChecked(True)
        self._link_cameras.stateChanged.connect(self._redraw)
        lv.addWidget(self._link_row)
        link_hint = Hint(
            "Turn one shape and the other turns with it, so you are always "
            "comparing the same face of both. This is what makes two rooms "
            "worth having: two shapes seen from two different angles cannot "
            "be compared at all.\n\n"
            "Untick it to move each one on its own — useful when you want to "
            "look into the shadows of one while keeping the other where it "
            "is.\n\n"
            "On the flat cross-section it does the matching thing: zoom or "
            "drag one cut and the other follows, so both always show the same "
            "patch of colour. Without that you could be looking closely at the "
            "reds on one side and at everything on the other, and the two "
            "shapes would appear wildly different sizes for no reason at "
            "all.\n\n"
            "Either way, nothing about your measurements changes. This only "
            "moves the view.", g_look)
        link_hint.setObjectName("hint_link_hint")
        # THE ⓘ IS PUT IN THE ROW BY HAND, and it has to be.
        #
        # Reported from the window: "clicked two rooms side by side option and
        # a tooltip icon appears below both rooms point the same way - should
        # probably be at its right side". Measured with two shapes open and
        # the tick on: the icon sat 25 px BELOW the checkbox at the same left
        # edge.
        #
        # It was never a wrap. `_attach_in_layout` is what puts every other ⓘ
        # on its control's row, and it walks LAYOUTS -- it never descends into
        # a widget's own layout. This checkbox lives inside a container widget
        # so that hiding the option takes its spacing with it (see above), so
        # the pass walked straight past the pair and left the icon where it
        # was added. Hence by hand, and marked as such so the pass does not
        # try to move it again.
        _link_line = QHBoxLayout()
        _link_line.setContentsMargins(0, 0, 0, 0)
        _link_line.setSpacing(6)
        _link_line.addWidget(self._link_cameras, 1)
        _link_line.addWidget(link_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        link_hint.setProperty("placed_by_hand", True)
        link_hint.follow(self._link_cameras)
        _lr.addLayout(_link_line)

        self._spin_on = QCheckBox("Turn it by itself", g_look)
        self._spin_on.stateChanged.connect(self._on_spin_changed)
        lv.addWidget(self._spin_on)
        spin_hint = Hint(
            "Sets the shape moving gently on its own, so you can watch it "
            "from every side without holding the mouse.\n\n"
            "It is more than a nicety. Depth is genuinely hard to judge on a "
            "flat screen: a dent in the deep blues and a shadow can look "
            "identical in a still picture. As soon as the shape moves, your "
            "eyes get the same depth cue they use in the real world, and the "
            "dent becomes obvious.\n\n"
            "It never gets in your way. Touch the picture and it stops at "
            "once, waits while you drag or zoom, and picks up again from "
            "wherever you left it — so anything you set by hand is kept.\n\n"
            "You can have it turning left and right, tipping up and down, or "
            "both at the same time. Each is set on its own below.", g_look)
        spin_hint.setObjectName("hint_spin_hint")
        lv.addWidget(spin_hint)

        self._spin_rows, self._name_extras = [], []
        self._turn_mode, self._turn_speed, self._turn_sweep = self._axis_controls(
            g_look, lv, "Left and right",
            "Turns the shape the way a turntable does, keeping upright "
            "upright: black stays at the bottom and white at the top, and the "
            "hues come round one after another.\n\n"
            "This is the one to reach for first. It shows you every hue in "
            "turn — where the reds run out, how far the cyans reach — while "
            "the shape stays the right way up and stays easy to read.\n\n"
            "Back and forth swings a little way to each side and returns, "
            "which keeps the shape facing the way you pointed it. All the way "
            "round carries it through a complete circle, which is lovely to "
            "leave running but will take it away from the angle you chose.",
            speed_default=8, sweep_default=60, sweep_range=(15, 180))
        self._tilt_mode, self._tilt_speed, self._tilt_sweep = self._axis_controls(
            g_look, lv, "Up and down",
            "Tips the shape towards you and away again, so you look down onto "
            "the top of it and then up from underneath.\n\n"
            "This is what shows you the lid and the floor of the gamut — how "
            "flat the top is near white, and how the shape closes in towards "
            "black — which a turntable alone never brings into view.\n\n"
            "It works alongside left and right rather than instead of it: set "
            "both and the shape drifts through a slow, easy tumble. It starts "
            "at not at all, because one direction of movement at a time is "
            "usually plenty.\n\n"
            "All the way round takes it right over the top and back up the "
            "other side. The picture turns with it rather than flipping over, "
            "so the movement stays smooth the whole way round.",
            speed_default=6, sweep_default=40, sweep_range=(10, 120),
            start_off=True)
        self._name_column.extend(self._name_extras)
        self._align_names()
        v.addWidget(g_look)

        # --- the number -------------------------------------------------------
        g_vol = QGroupBox("How much colour it holds", col)
        vv = QVBoxLayout(g_vol)
        self._volume = QLabel("—", g_vol); self._volume.setObjectName("volume")
        vv.addWidget(self._volume)
        self._coverage = WrappedLabel("", g_vol, hide_when_empty=True)
        self._coverage.setObjectName("hint"); _wrapped(self._coverage)
        vv.addWidget(self._coverage)
        # Only a picture has one of these, so it is empty the rest of the time.
        self._picture_loss = WrappedLabel("", g_vol, hide_when_empty=True)
        _wrapped(self._picture_loss)
        vv.addWidget(self._picture_loss)
        self._range = WrappedLabel("", g_vol, hide_when_empty=True)
        self._range.setObjectName("hint")
        vv.addWidget(self._range)
        self._volume_hint = Hint(
            "Open a chart to see how much colour it holds.\n\n"
            "The figure is the volume the measured surface encloses, in the "
            "units of whichever space is chosen under Draw it in — cubic Lab "
            "units for CIELAB, which is the one to leave it on for print.\n\n"
            "IT IS FOR COMPARING, not for reading on its own. There is no "
            "such thing as a good number here: a paper holding 700,000 cubic "
            "Lab units means nothing until you have a second paper measured "
            "the same way to hold it against. Open two and the panel does the "
            "comparing for you.\n\n"
            "Underneath it are the two figures that decide how much contrast "
            "you actually get: how dark the blacks reach, and how bright the "
            "paper white is. A paper that cannot go dark loses shadow detail "
            "however large its volume turns out to be.", g_vol)
        self._volume_hint.setObjectName("hint_volume_hint")
        vv.addWidget(self._volume_hint)
        v.addWidget(g_vol)

        # Only meaningful when there are two shapes to hold against each
        # other, so it stays hidden until there are.
        self._pair_box = QGroupBox("How the two compare", col)
        pv2 = QVBoxLayout(self._pair_box)
        # NOT self._shared -- that name already holds the shared per-shape
        # settings, and taking it silently broke every redraw.
        self._shared_lbl = WrappedLabel("", self._pair_box,
                                        hide_when_empty=True)
        pv2.addWidget(self._shared_lbl)
        self._reach = WrappedLabel("", self._pair_box, hide_when_empty=True)
        self._reach.setObjectName("hint")
        pair_hint = Hint(
            "How much of everything either one can print is printable by "
            "both. The two percentages above answer \"does this one fit "
            "inside that one\", one direction at a time; this answers how "
            "much they have in common, which is a different question and one "
            "number rather than two.\n\n"
            "Underneath it, the hue families where one reaches further out "
            "from grey than the other. This is usually the practical answer "
            "to \"which paper should I use\": a paper that wins in the cyans "
            "and blues suits skies and water, one that wins in the yellows "
            "and reds suits skin and autumn. Families closer than a couple of "
            "units apart are called about the same, because a difference that "
            "small is neither visible nor worth trusting.",
            self._pair_box)
        pair_hint.setObjectName("hint_pair_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._reach, 1)
        _r.addWidget(pair_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        pv2.addLayout(_r)
        self._pair_box.setVisible(False)
        v.addWidget(self._pair_box)

        # Only meaningful with two readings of one chart, so it stays out of
        # the way until there are two charts open.
        self._drift_box = QGroupBox("Has anything changed?", col)
        dv = QVBoxLayout(self._drift_box)
        self._drift = WrappedLabel("", self._drift_box, hide_when_empty=True)
        dv.addWidget(self._drift)
        self._drift_worst = WrappedLabel("", self._drift_box, hide_when_empty=True)
        self._drift_worst.setObjectName("hint")

        # WHICH COLOUR FAMILIES MOVED, in the main window as well as in the
        # timeline. For one release this existed only in "Follow one device
        # over time", so somebody holding two readings of one chart -- the
        # case this whole box exists for -- got a ΔE summary and nothing about
        # WHERE the movement was.
        self._drift_families = WrappedLabel("", self._drift_box,
                                            hide_when_empty=True)
        self._drift_families.setToolTip(
            "Which colour families moved between the two files you have "
            "open, and which way — written out so you can paste it straight "
            "into an email or a report.\n\n"
            "WHAT YOU NEED FIRST: two files of the same kind open together. "
            "Either two measurements (.ti3) of the same chart, or two ICC "
            "profiles of the same device. Open them with Open something to "
            "look at…, at the top of this column.\n\n"
            "TWO MEASUREMENTS IS THE VERIFICATION CASE, and the most useful "
            "one: print your chart again weeks or months later on the same "
            "paper and the same printer, read it, and open both readings "
            "here. The lines then tell you which colours your printer has "
            "actually drifted in.\n\n"
            "WHAT IS IN THAT NUMBER, because it is more than the printer. "
            "Reprinting puts the whole process between the two readings: the "
            "printhead's temperature changes how much ink each nozzle puts "
            "down, low humidity dries ink near the nozzles and darkens it, "
            "paper takes up moisture and changes size, and no two ink or "
            "paper batches are quite identical. That is usually exactly what "
            "you want to know — it is what your printing really does on a "
            "different day. If instead you measured the SAME sheet twice, "
            "you are seeing that sheet ageing plus your instrument's own "
            "repeatability, which for a typical hand-held spectrophotometer "
            "is around ΔE 0.1.\n\n"
            "TWO PROFILES IS A DIFFERENT QUESTION. That compares two "
            "DESCRIPTIONS of a device rather than the device: each profile "
            "is one day's measurements of one chart, so a faded chart or a "
            "change in how you built them is inside the number too.\n\n"
            "EVERY LINE SAYS HOW MANY IT STANDS ON. A family with four "
            "patches in it and one with four hundred produce the same kind "
            "of sentence, and only that number tells you how much to trust "
            "it.\n\n"
            "\"STAYED THE SAME\" MEANS UNDER ΔE 1 — the same figure this "
            "window uses everywhere else for a difference a careful eye "
            "begins to notice.\n\n"
            "\"MIXED\" MEANS THEY MOVED BUT NOT TOGETHER. There is no one "
            "direction that would be true of them all, so none is given "
            "rather than inventing one out of the average.\n\n"
            "\"BUT NOT CERTAINLY\" MEANS THE MOVEMENT IS NO BIGGER THAN ITS "
            "OWN SCATTER — treat it as a hint to go and look, not as a "
            "finding.\n\n"
            "THE GREYS are patches too close to neutral to have a hue worth "
            "naming, so they are never said to have drifted toward a colour. "
            "They are reported as warmer, cooler, redder, greener, lighter "
            "or darker instead. Greys drifting while the colours hold still "
            "is a common and useful pattern: it usually points at the light "
            "inks or the paper rather than at one colourant.")
        self._drift_families_note = WrappedLabel("", self._drift_box,
                                                 hide_when_empty=True)
        self._drift_families_note.setObjectName("hint")
        drift_hint = Hint(
            "This answers one question — have these two moved apart? — and it "
            "answers it for two kinds of file.\n\n"
            "TWO MEASUREMENTS. When both files are readings of the SAME "
            "chart — the same paper measured on two days, or before and after "
            "a nozzle clean — they are compared patch by patch. Patches are "
            "paired on the ink amounts that were asked for, not on the patch "
            "number, because charts are usually shuffled.\n\n"
            "TWO ICC PROFILES. When both files are profiles, both are asked "
            "for the same 729 colours and the answers are held side by side. "
            "This is the one to use for two profiles of the same scanner or "
            "printer made months or years apart.\n\n"
            "WHY NOT JUST COMPARE THE SHAPES? Because a shape cannot show "
            "this. Two profiles can enclose almost exactly the same volume "
            "and send the colours inside it to quite different places — "
            "measured on a real pair, 0.011% apart in size and up to ΔE 4.2 "
            "apart inside. For a scanner profile, the inside is nearly the "
            "whole profile, so the shape is the part that matters least.\n\n"
            "WHAT IT DOES NOT TELL YOU, and this matters if you are chasing a "
            "drifting device: this is how far apart the two PROFILES are, not "
            "how far the device drifted. A profile records one day's "
            "measurements of one chart. If that chart faded between the two, "
            "or the two profiles were built with different settings, that is "
            "inside this number as well, and no arithmetic here can separate "
            "it out. To measure the device alone you need a chart you trust "
            "not to have changed.\n\n"
            "The numbers are ΔE2000. Below 1 nobody can see it. Around 2 a "
            "careful eye finds it on a smooth gradient. Above 3 it is plain, "
            "and worth investigating before you print anything that matters.",
            self._drift_box)
        drift_hint.setObjectName("hint_drift_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._drift_worst, 1)
        _r.addWidget(drift_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        # AND IT LEAVES WHEN THE LINES IT EXPLAINS LEAVE. This readout hides
        # itself when it is empty -- one file open, or two that agree exactly
        # -- and the ⓘ beside it stayed, alone in the middle of the box with
        # nothing to point at. Reported from the window: "has anything changed
        # section has a tooltip icon without anything it belongs to
        # sometimes". The icons the generic pass places are tied this way
        # already; this row is built by hand and was never tied.
        drift_hint.follow(self._drift_worst)
        dv.addLayout(_r)
        # WHICH QUESTION IS BEING ASKED, because the same arithmetic answers
        # two and the words are not interchangeable.
        #
        # IT CANNOT BE INFERRED FROM THE FILES, and this is the whole reason
        # for asking. Two .ti3 of one chart could be one printer months apart
        # -- the verification case -- or two papers on one afternoon, and the
        # file names are not evidence. "Moved" is a claim about TIME: said of
        # two papers it is simply false, and it is exactly the sort of false
        # sentence somebody pastes into an email.
        #
        # THE MAIN CHROMIQ APPLICATION WOULD NOT NEED TO ASK. Its folder model
        # already knows: two .ti3 in different runs of one target are one
        # thing over time, and two in different targets are different things.
        # See docs/PORTING-TO-CHROMIQ.md.
        same_row = QHBoxLayout()
        same_row.setContentsMargins(0, 0, 0, 0)
        same_row.setSpacing(6)
        same_label = QLabel("These two are", self._drift_box)
        same_row.addWidget(same_label, 0)
        self._same_thing = NoScrollComboBox(self._drift_box)
        self._same_thing.addItem("one thing at two times", True)
        self._same_thing.addItem("two different things", False)
        self._same_thing.setToolTip(
            "Says what the two open files are to each other, which decides "
            "the words the lines below are written in.\n\n"
            "ONE THING AT TWO TIMES — the same printer on the same paper, "
            "measured again weeks or months later, or two profiles of one "
            "device. The lines then say what MOVED, and in which direction, "
            "because there is a before and an after.\n\n"
            "TWO DIFFERENT THINGS — two papers, two printers, two inks, "
            "measured from the same chart. Nothing has \"drifted\" here: the "
            "lines say how the second DIFFERS from the first in each colour "
            "family, which is what you want when you are choosing between two "
            "papers or asking whether two machines agree.\n\n"
            "WHY YOU ARE ASKED: the files cannot say. Two measurements of one "
            "chart look identical whether they are one printer months apart "
            "or two papers on one afternoon, and a file name is not evidence. "
            "Guessing would put \"the reds drifted\" into a report about two "
            "papers, which is not true of either of them.\n\n"
            "IT CHANGES ONLY THE WORDS. Every number is the same either way — "
            "the same ΔE, the same families, the same patch counts.")
        self._same_thing.activated.connect(lambda _i: self._update_drift())
        same_row.addWidget(self._same_thing, 1)
        same_hint = Hint(
            "The same arithmetic answers two quite different questions, and "
            "only you know which one you are asking.\n\n"
            "\"Has my printer drifted since March?\" is one thing at two "
            "times. \"Which of these two papers holds the blues better?\" is "
            "two different things, measured on one afternoon, and nothing in "
            "it has moved anywhere.\n\n"
            "Both are worth asking and this window answers both. What it "
            "must not do is describe the second as though it were the first: "
            "\"the blues drifted toward the magentas\" said of two papers "
            "reads as a fault in a printer that is behaving perfectly.\n\n"
            "The numbers do not change when you switch this. The verbs do.",
            self._drift_box, title="One thing at two times, or two things?")
        same_hint.setObjectName("hint_same_thing")
        same_row.addWidget(same_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        dv.addLayout(same_row)
        # UNDER THE NUMBERS, because it explains them rather than competing
        # with them: the reader has just been told how far the two moved
        # apart, and this says which colours did the moving.
        dv.addWidget(self._drift_families)
        dv.addWidget(self._drift_families_note)
        # IN THIS BOX RATHER THAN AMONG THE DRAWING OPTIONS, because this is
        # where somebody is standing when the question occurs to them. They
        # have just read "biggest difference ΔE 3.30" and the next thought is
        # "where?" — so the answer sits under the number that prompted it,
        # not in a panel they would have to go looking for.
        self._drift_draw = QCheckBox("Show me where, in the picture",
                                     self._drift_box)
        self._drift_draw.setChecked(False)
        self._drift_draw.setToolTip(
            "Paint every colour into the picture, coloured by how far the two "
            "profiles disagree about it.")
        self._drift_draw.stateChanged.connect(self._redraw)
        self._drift_draw.stateChanged.connect(
            lambda _s: self._refresh_drift_controls())
        _d = QHBoxLayout(); _d.setContentsMargins(0, 0, 0, 0)
        _d.setSpacing(6)
        _d.addWidget(self._drift_draw, 1)
        _d.addWidget(Hint(
            "The numbers above say HOW MUCH the two profiles disagree. This "
            "says WHERE, which is usually the more useful half.\n\n"
            "Tick it and every colour is drawn at the place the FIRST profile "
            "puts it, painted by how far the second one sends it instead. "
            "Quiet grey means the two agree; amber means a careful eye would "
            "see it; red means anybody would.\n\n"
            "WHY THIS IS WORTH LOOKING AT. \"Average ΔE 2\" comes out the same "
            "whether a scanner has drifted a little everywhere — which points "
            "at calibration — or hardly at all except in the deep blues, which "
            "is a different problem with a different cause. The numbers cannot "
            "tell those apart. One look at the picture can.\n\n"
            "The scale is fixed rather than stretched to fit, so the same "
            "colour means the same amount in every picture. Two profiles that "
            "barely differ come out looking calm, which is the truth about "
            "them.\n\n"
            "Colours the two agree about are still drawn, just small and "
            "quiet. Leaving them out would put holes in the cloud and invite "
            "the reading that something is missing there, when what is true "
            "is that nothing has changed there.",
            self._drift_box, title="Showing the drift in the picture"),
            0, Qt.AlignmentFlag.AlignVCenter)
        dv.addLayout(_d)

        # --- and WHAT the colours in that cloud stand for ---------------------
        #
        # THE THIRD OPTION THAT EXISTED IN ONE WINDOW ONLY. The two below this
        # were brought over for the reason written there; this one was left,
        # and it is the one that answers the question people ask out loud.
        # The main window's cloud could only ever be painted by DISTANCE --
        # `_drift_for_figure` returned its axis as a hard-coded None -- while
        # the run panel three sections up offered five ways to paint the same
        # kind of cloud. The main window is where somebody with two profiles
        # of one printer actually works.
        by_row = QHBoxLayout()
        by_row.setContentsMargins(0, 0, 0, 0)
        by_row.setSpacing(8)
        self._drift_by_label = QLabel("coloured by", self._drift_box)
        by_row.addWidget(self._drift_by_label, 0)
        self._drift_by = NoScrollComboBox(self._drift_box)
        self._drift_by.addItem("how far it moved", None)
        for _key, (_asks, _less, _more, _col) in DIRECTIONS.items():
            self._drift_by.addItem(_asks, _key)
        self._drift_by.addItem("the colour it is heading for", "toward")
        self._drift_by.setToolTip(
            "What the colours in the cloud stand for. It changes the picture "
            "under \"Show me where, in the picture\" and nothing else — no "
            "number above it moves.\n\n"
            "HOW FAR IT MOVED is the plain answer and the one to start with: "
            "quiet grey where the two agree, amber where a careful eye would "
            "see it, red where anybody would. It says how much, and nothing "
            "about which way.\n\n"
            "LIGHTER OR DARKER, REDDER OR GREENER, WARMER OR COOLER each ask "
            "one direction. This is what ΔE cannot tell you: a printer going "
            "lighter and one going darker by the same amount give an "
            "identical number and an identical cloud, and they want different "
            "cures.\n\n"
            "THE COLOUR IT IS HEADING FOR paints every dot in the family it "
            "is moving toward — blues on their way to the magentas come out "
            "magenta, wherever they sit in the picture. It answers what "
            "somebody actually reports: not \"how far\" and not \"how much "
            "redder\", but \"what are my greys going to\".\n\n"
            "WHAT IT NEEDS: two profiles open and \"Show me where, in the "
            "picture\" ticked. Without that tick there is no cloud for this "
            "to paint, and this box is greyed out until there is.\n\n"
            "IF YOU CANNOT SEE THE CLOUD, the two shapes are drawn over it: "
            "the colours sit INSIDE the gamut, which is where they belong. "
            "Turn \"How solid it looks\" down, under How it looks, and they "
            "come through. Photographed at full solidity only the rim of the "
            "cloud shows, which reads as a picture with hardly anything in "
            "it.\n\n"
            "A DOT THAT HAS BARELY MOVED IS DRAWN GREY and said to be heading "
            "nowhere. Below about ΔE 1 the direction of a movement is mostly "
            "the instrument — a hand-held spectrophotometer repeats to about "
            "ΔE 0.1 and two different ones agree to about 0.4 — so painting "
            "those a confident colour would be inventing a direction out of "
            "noise.")
        self._drift_by_tooltip = self._drift_by.toolTip()
        self._drift_by.activated.connect(lambda _i: self._redraw())
        self._drift_by.activated.connect(
            lambda _i: self._refresh_drift_controls())
        by_row.addWidget(self._drift_by, 1)
        by_row.addWidget(Hint(
            "One cloud, five questions, and the numbers above answer none of "
            "them.\n\n"
            "\"Average ΔE 2\" is the same figure whether every colour drifted "
            "a little — which points at calibration — or the deep blues "
            "drifted a lot and nothing else moved, which is a different "
            "problem with a different cure. Painting the cloud by how far it "
            "moved separates those two at a glance.\n\n"
            "The three directions go further. A number cannot tell lighter "
            "from darker, and a print that has gone light and one that has "
            "gone dark are not the same fault. Pick the direction you "
            "suspect and the cloud says whether you are right.\n\n"
            "And the last one answers in names rather than numbers: this "
            "family is heading for that one. It is the sentence people use "
            "when they describe the problem to somebody else.\n\n"
            "Everything here is only about the picture. Nothing you choose "
            "changes a measurement.",
            self._drift_box, title="What the cloud's colours mean"),
            0, Qt.AlignmentFlag.AlignVCenter)
        dv.addLayout(by_row)

        # --- the same two options the timeline window offers ------------------
        #
        # THEY EXISTED IN ONE WINDOW ONLY. The timeline could split its cloud
        # into colour families and hide the colours that barely moved; the
        # main window drew the same kind of cloud and could do neither -- and
        # the main window is the one that can also show the SHAPES, which is
        # where the two halves of the answer meet. A reader who found the
        # controls in one place and not the other would reasonably think they
        # had done something wrong.
        self._drift_split = QCheckBox("Split it into colour families",
                                      self._drift_box)
        self._drift_split.setToolTip(
            "Draws the cloud as seven groups — reds, yellows, greens, cyans, "
            "blues, magentas and greys — instead of one, and puts them in the "
            "key at the side with the number of colours in each.\n\n"
            "WHAT IT IS FOR: click a family in the key to hide it, and again "
            "to bring it back. With everything but the blues hidden you can "
            "see exactly where in the blues the two disagree, which a single "
            "cloud cannot show you because the interesting part is buried "
            "under everything else.\n\n"
            "THE GROUPS ARE THE ONES THE LIST ABOVE DESCRIBES, so if the text "
            "says the blues drifted toward the magentas, this is how you go "
            "and look at those very colours.\n\n"
            "IT KEEPS WORKING IN A SAVED PAGE — whoever opens it can hide and "
            "show the families too, with nothing installed and no internet "
            "needed.\n\n"
            "GREYS are colours too close to neutral to have a hue worth "
            "naming, so they are their own group rather than being scattered "
            "among the six.")
        self._split_tooltip = self._drift_split.toolTip()
        self._drift_split.stateChanged.connect(self._redraw)
        # AND THE COLOURINGS IT SILENCES ARE GREYED THE MOMENT IT IS TICKED.
        # The combo above already refreshes the controls when it changes; this
        # is the same edge from the other end, and without it the four dead
        # entries only grey out on the NEXT unrelated change.
        self._drift_split.stateChanged.connect(
            lambda _s: self._refresh_drift_controls())
        # IN A ROW OF ITS OWN, exactly like the tick above it, and that is the
        # whole reason for the row. Added straight to the column it began two
        # pixels to the left of "Show me where, in the picture" -- measured,
        # x=10 against x=12 -- because the other one sits inside a row that
        # also holds an ⓘ. Two ticks under each other, off by two pixels, is
        # the kind of thing that reads as sloppiness without being nameable.
        # Reported from the window: "checkboxes are not aligned correctly".
        _s = QHBoxLayout(); _s.setContentsMargins(0, 0, 0, 0)
        _s.setSpacing(6)
        _s.addWidget(self._drift_split, 1)
        dv.addLayout(_s)

        cut_row = QHBoxLayout()
        cut_row.setContentsMargins(0, 0, 0, 0)
        cut_row.setSpacing(8)
        self._drift_cut_label = QLabel("Hide anything under", self._drift_box)
        cut_row.addWidget(self._drift_cut_label, 0)
        self._drift_cut = NoScrollSlider(Qt.Orientation.Horizontal, self._drift_box)
        self._drift_cut.setMinimum(0)
        self._drift_cut.setMaximum(1)
        self._drift_cut.setSingleStep(1)
        self._drift_cut.setPageStep(5)
        self._drift_cut.setToolTip(
            "Leaves out every colour the two agree about more closely than "
            "this, so what is left is only the disagreement worth looking "
            "at.\n\n"
            "WHY YOU WANT IT: the lines above give an AVERAGE for each "
            "family, and an average hides the shape. \"Blues: ΔE 1.7\" reads "
            "the same whether all of them moved 1.7 or nearly all sat still "
            "and a handful moved a great deal — and those are very different "
            "problems. Drag this up and only the colours anybody could see "
            "are left.\n\n"
            "WHERE IT STOPS: at the biggest difference between THESE two, "
            "because past that there would be nothing left to hide. If the "
            "two agree everywhere the slider is switched off.\n\n"
            "IN STEPS OF ΔE 0.1, which is as fine as the numbers support: a "
            "hand-held spectrophotometer repeats to about ΔE 0.1 on white and "
            "two different instruments agree to about 0.4, so anything finer "
            "would be reading the instrument rather than the printing.\n\n"
            "IT CHANGES THE PICTURE ONLY — every number and sentence above "
            "still describes all the colours, so two people with the slider "
            "in different places quote each other the same figures. The "
            "picture says how many it left out, and so does a saved page.")
        self._drift_cut.valueChanged.connect(self._drift_cut_changed)
        cut_row.addWidget(self._drift_cut, 1)
        self._drift_cut_says = QLabel("nothing hidden", self._drift_box)
        self._drift_cut_says.setMinimumWidth(116)
        cut_row.addWidget(self._drift_cut_says, 0)
        dv.addLayout(cut_row)
        self._drift_cut_row = cut_row

        self._drift_box.setVisible(False)
        v.addWidget(self._drift_box)

        # Only there when a chart is open, because with none it would be a
        # heading over three empty lines.
        self._chart_box = QGroupBox("Are the patches inside?", col)
        cbv = QVBoxLayout(self._chart_box)
        self._chart_headline = WrappedLabel("", self._chart_box,
                                            hide_when_empty=True)
        cbv.addWidget(self._chart_headline)
        self._chart_rows = WrappedLabel("", self._chart_box,
                                        hide_when_empty=True)
        cbv.addWidget(self._chart_rows)
        self._chart_spread = WrappedLabel("", self._chart_box,
                                          hide_when_empty=True)
        self._chart_spread.setObjectName("hint")
        chart_numbers_hint = Hint(
            "INSIDE, ON THE EDGE, OUTSIDE — three counts rather than two, and "
            "the middle one is the one that saves an evening.\n\n"
            "A gamut surface is not an exact object. It is worked out from a "
            "grid of samples, and between those samples the real boundary "
            "bulges out a little further than the shape drawn through them. So "
            "a handful of patches always land a whisker outside any surface, "
            "including the surface of the very profile that placed them. "
            "Pushing a 5960-patch chart through a real printer profile and "
            "measuring against that same profile: at a coarse sampling 353 "
            "patches came out \"outside\", and at a fine one 122 did — but the "
            "distance they were outside by fell from 0.58 to 0.05. They were "
            "on the surface the whole time.\n\n"
            "So a patch within 1.0 ΔE of the surface is called ON THE EDGE. "
            "One ΔE is the standard threshold for a difference nobody can see "
            "with the two colours side by side, and it is more than ten times "
            "the error measured above. A patch further out than that is "
            "outside for a reason worth finding.\n\n"
            "WHICH SURFACE. The test is against the same surface this window "
            "uses everywhere else — a skin over the shape's own corners — so "
            "the counts here can never disagree with the colouring on the "
            "shape beside them. A real printer's edge has dents in it and a "
            "skin bridges them, which makes this test careful in exactly one "
            "direction: a patch it calls outside really is outside, and a "
            "patch sitting down in a dent may be called inside. It can miss "
            "something; it cannot invent something.\n\n"
            "HOW FAR APART tells you about the chart itself rather than about "
            "any printer, and needs nothing else open. Patches much closer "
            "together than the rest are the chart doubling up and spending "
            "paper twice on one colour; the largest gap is the widest hole in "
            "what it samples. It is straight-line distance in Lab rather than "
            "ΔE, because it is a question about coverage of the space, not "
            "about what the eye can tell apart.",
            self._chart_box)
        chart_numbers_hint.setObjectName("hint_chart_numbers_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._chart_spread, 1)
        _r.addWidget(chart_numbers_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        cbv.addLayout(_r)
        self._chart_box.setVisible(False)
        v.addWidget(self._chart_box)

        v.addStretch(1)

        # Appearance and accent live at the FOOT of the column. Between the
        # heading and the sentence that explains it, they separated a title
        # from its own description and left the heading looking orphaned --
        # and they are preferences about the window, not about the subject.
        g_prefs = QGroupBox("This window", col)
        pv = QVBoxLayout(g_prefs)
        # One rhythm for the whole group: every label sits the same distance
        # above its choices, and every set the same distance below the one
        # before. Left to itself each row inherited a different gap and the
        # three sets read as three unrelated blocks.
        pv.setSpacing(4)
        pv.setContentsMargins(8, 6, 8, 8)
        # The label sits above its choices, the same shape as Accent and the
        # shape-colour set below it -- three groups laid out three different
        # ways is three things to parse instead of one.
        self._appearance_label = QLabel("Appearance", g_prefs)
        self._appearance_label.setObjectName("prefsHeading")
        pv.addWidget(self._appearance_label)
        appearance_hint = Hint(
            "Light or dark, for the window and for the picture inside it. "
            "The choice is remembered, so the application opens the way you "
            "left it.\n\n"
            "It is worth trying both on the shape you are looking at: a gamut "
            "with a lot of dark, saturated colour in it reads more easily on "
            "a dark background, and a pale paper reads more easily on a light "
            "one.\n\n"
            "Nothing about your measurements changes — this only changes how "
            "they are drawn.", g_prefs)
        appearance_hint.setObjectName("hint_appearance_hint")
        pv.addWidget(appearance_hint)
        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 10)
        # Light and Dark are two choices, not one word: without room between
        # them they read as a single run of text and the pair of radios is
        # harder to tell apart than it should be. The accent grid below uses
        # the same gap.
        theme_row.setSpacing(18)
        # EACH SET NEEDS ITS OWN GROUP. Radio buttons sharing a parent are one
        # exclusive group in Qt, so choosing an accent silently unchecked the
        # appearance -- both sets looked empty and neither could be read off the
        # screen. Grouping them explicitly keeps the two questions separate.
        self._theme_group = QButtonGroup(self)
        self._theme_light = QRadioButton("Light", g_prefs)
        self._theme_dark = QRadioButton("Dark", g_prefs)
        for radio in (self._theme_light, self._theme_dark):
            self._theme_group.addButton(radio)
            theme_row.addWidget(radio)
        theme_row.addStretch(1)      # keep the pair together on the left
        theme_row.addStretch(1)
        self._theme_light.toggled.connect(
            lambda on: self._set_appearance("light") if on else None)
        self._theme_dark.toggled.connect(
            lambda on: self._set_appearance("dark") if on else None)
        pv.addLayout(theme_row)

        # Five names will not fit one row of a 310 px column -- squeezed onto
        # one line they came out as "Ma", "Tea", "Am". A grid gives every name
        # its full width, and reads as a set of choices rather than a cramped
        # strip.
        self._accent_label = QLabel("Accent", g_prefs)
        self._accent_label.setObjectName("prefsHeading")
        pv.addWidget(self._accent_label)
        accent_hint = Hint(
            "The colour this window uses for the things you can change: "
            "buttons, the ⓘ you are reading now, a control you are pointing "
            "at, and the bar under the title.\n\n"
            "It is yours to pick and it changes nothing else. The greys, the "
            "text and the backgrounds stay exactly where they are, because "
            "those are what make the window readable — an accent is what "
            "makes it yours.\n\n"
            "One place it does reach the picture: choosing In the accent "
            "colours under How the shapes are coloured tints the gamut into "
            "this same family.", g_prefs)
        accent_hint.setObjectName("hint_accent_hint")
        pv.addWidget(accent_hint)
        scheme_grid = QGridLayout()
        scheme_grid.setContentsMargins(0, 0, 0, 10)
        # 4px left the accent radios almost touching -- the same fault as the
        # appearance pair, found by measuring the gap rather than looking.
        scheme_grid.setHorizontalSpacing(16)
        scheme_grid.setVerticalSpacing(6)
        self._scheme_group = QButtonGroup(self)
        self._scheme_radios = {}
        for i, name in enumerate(SCHEMES):
            radio = QRadioButton(name, g_prefs)
            radio.setMinimumHeight(20)
            self._scheme_group.addButton(radio)
            radio.setToolTip(f"Use the {name.lower()} accent colour")
            radio.toggled.connect(
                lambda on, which=name: self._set_scheme(which) if on else None)
            self._scheme_radios[name] = radio
            scheme_grid.addWidget(radio, i // 3, i % 3)
        pv.addLayout(scheme_grid)
        v.addWidget(g_prefs)

        # HOW A SAVED PICTURE LOOKS — and, with one box ticked, how this
        # window looks too. Here rather than inside the Save dialog because
        # every one of these choices is a thing to look at rather than a thing
        # to imagine.
        self._looks_panel = LookSection(col, self._on_look_changed)
        v.addWidget(self._looks_panel)

        # ==================================================================
        # THE FOOT OF THE COLUMN, IN TWO NAMED SECTIONS RATHER THAN NINE
        # LOOSE BUTTONS.
        #
        # Reported from the window: "those buttons at the bottom of the column
        # stand out a bit. could they be placed in another collapsible section
        # called something like app settings". They did stand out, and for a
        # reason worth writing down. Everything above them is a group with a
        # heading that says what its controls are about; these nine were the
        # only things in the whole column with no heading over them — a
        # picture saver, a page saver, a table saver, a glossary, two "where
        # is it" pickers, an update check, a tickbox and a reset, in one
        # undifferentiated stack that a reader has to sort out for themselves.
        #
        # THEY ARE NOT ONE THING, SO THEY ARE NOT ONE SECTION. There are two
        # intents here, and the tooltips had already noticed: each of the
        # three save buttons calls itself one of "THE THREE WAYS OF TAKING
        # SOMETHING WITH YOU" — a grouping the text was asserting with no
        # layout behind it, and the three were not even next to each other
        # (the table sat five controls above the picture). The rest is
        # housekeeping about the application itself: what it can find, whether
        # it is current, what the words mean, and the way back to standard
        # settings.
        #
        # WHICH ONE STARTS OPEN. Saving is why somebody came; it stays open.
        # The housekeeping is set once or never, so it starts folded — which
        # is the whole point of the exercise, since folded it is one line
        # instead of eight controls and two paragraphs.
        # ==================================================================
        g_take = QGroupBox("Take it away with you", col)
        tk = QVBoxLayout(g_take)
        tk.setSpacing(6)
        tk.setContentsMargins(8, 6, 8, 8)
        self._picture = QPushButton("Save this view as a picture…", g_take)
        self._picture.setObjectName("secondary")
        self._picture.clicked.connect(self._on_picture)
        self._picture.setEnabled(False)
        picture_hint = Hint(
            "Makes a picture of what is on screen, to put in a document, on a "
            "slide, or in a forum post.\n\n"
            "This is the third way of taking something away with you, and the "
            "three answer different questions. A PICTURE is for showing "
            "somebody. A WEB PAGE — the button below — keeps it turnable, so "
            "whoever opens it can look from any side themselves. A TABLE of "
            "numbers is for doing arithmetic on.\n\n"
            "You can choose how large it is, what kind of file, and what is "
            "behind the shape — including nothing at all, so it sits on "
            "whatever page you drop it onto. It can also be a moving picture "
            "that turns and repeats, which shows the shape from every side in "
            "the space of one still.\n\n"
            "Nothing is written until you have chosen where it goes, and a "
            "file that is already there is never written over.", g_take)
        picture_hint.setObjectName("hint_picture_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0); _r.setSpacing(6)
        _r.addWidget(self._picture, 1)
        _r.addWidget(picture_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        tk.addLayout(_r)
        self._save = QPushButton("Save this view as a web page…", g_take)
        self._save.setObjectName("secondary")
        self._save.setToolTip(
            "Writes what you are looking at as a web page that anybody can "
            "open — and TURN. Not a picture of the shape: the shape itself, "
            "which whoever opens it can spin, tip, zoom into and take apart "
            "for themselves.\n\n"
            "IT NEEDS NOTHING INSTALLED. It opens in any browser, on a phone "
            "as well as a computer, with no internet connection and nothing "
            "to set up — so it is the one to send to a customer, a paper "
            "manufacturer, or a forum.\n\n"
            "EVERYTHING THE WINDOW SAYS TRAVELS WITH IT: the readings, the "
            "colour-family lines, the note about what the numbers do not "
            "mean, and the reader's own controls for hiding families and "
            "small differences. A page showing eleven dots would otherwise be "
            "impossible to tell apart from a printer that is nearly "
            "perfect.\n\n"
            "You are asked whether the drawing engine travels inside the file "
            "— about five megabytes, and then it works with no network at all "
            "— or is fetched when it is opened, which makes the file tiny but "
            "needs the internet the first time.\n\n"
            "It needs something open to show, so it waits until there is.")
        self._save.clicked.connect(self._on_save)
        self._save.setEnabled(False)
        # AN ⓘ OF ITS OWN, LIKE THE PICTURE ABOVE IT. Reported the moment the
        # three were finally sitting together, which is the point of putting
        # them together: "some of the save buttons lack a tooltip icon". They
        # each had the full paragraph, but only as a hover, where the window's
        # own rule says a hover is one sentence and the paragraph lives behind
        # the icon. _shorten_long_hovers does the second half automatically
        # once the icon is on the row.
        save_hint = Hint(
            "Writes what you are looking at as a web page that anybody can "
            "open — and TURN. Not a picture of the shape: the shape itself, "
            "which whoever opens it can spin, tip, zoom into and take apart "
            "for themselves.\n\n"
            "IT NEEDS NOTHING INSTALLED. It opens in any browser, on a phone "
            "as well as a computer, with no internet connection and nothing "
            "to set up — so it is the one to send to a customer, a paper "
            "manufacturer, or a forum.\n\n"
            "EVERYTHING THE WINDOW SAYS TRAVELS WITH IT: the readings, the "
            "colour-family lines, the note about what the numbers do not "
            "mean, and the reader's own controls for hiding families and "
            "small differences. A page showing eleven dots would otherwise be "
            "impossible to tell apart from a printer that is nearly "
            "perfect.\n\n"
            "You are asked whether the drawing engine travels inside the file "
            "— about five megabytes, and then it works with no network at all "
            "— or is fetched when it is opened, which makes the file tiny but "
            "needs the internet the first time.\n\n"
            "IT WAITS UNTIL THERE IS SOMETHING TO SHOW. With nothing open the "
            "button is greyed out; open a profile, a measurement or a chart "
            "and it comes alive.", g_take)
        save_hint.setObjectName("hint_save_hint")
        _sr = QHBoxLayout(); _sr.setContentsMargins(0, 0, 0, 0)
        _sr.setSpacing(6)
        _sr.addWidget(self._save, 1)
        _sr.addWidget(save_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        tk.addLayout(_sr)
        self._export_btn = QPushButton("Save the numbers as a table…", g_take)
        self._export_btn.setObjectName("secondary")
        self._export_btn.setToolTip(
            "Writes what this window is showing as a table of numbers you "
            "can open in any spreadsheet.\n\n"
            "WHAT IS IN IT: every reading the window has — how much colour "
            "each file holds, how much they share, and where they differ — "
            "with a row that says what each column is and what its units "
            "are, so it still makes sense to somebody who was not here when "
            "you saved it.\n\n"
            "THIS IS THE THIRD WAY OF TAKING SOMETHING WITH YOU, and the "
            "three answer different questions. A PICTURE is for showing "
            "somebody. A WEB PAGE keeps the shape turnable, so whoever opens "
            "it can look from any side. A TABLE is for doing arithmetic on — "
            "putting the numbers in a report, or watching one figure across "
            "twenty prints.\n\n"
            "It needs something open to describe, so it waits until there "
            "is.")
        self._export_btn.clicked.connect(self._on_export)
        self._export_btn.setEnabled(False)
        export_hint = Hint(
            "Writes what this window is showing as a table of numbers you can "
            "open in any spreadsheet — Excel, Numbers, LibreOffice, or "
            "anything that reads a comma-separated file.\n\n"
            "WHAT IS IN IT: every reading the window has — how much colour "
            "each file holds, how much they share, where they differ, and the "
            "colour-family lines — with a row that says what each column is "
            "and what its units are, so it still makes sense to somebody who "
            "was not here when you saved it.\n\n"
            "THIS IS THE THIRD WAY OF TAKING SOMETHING WITH YOU, and the "
            "three answer different questions. A PICTURE is for showing "
            "somebody. A WEB PAGE keeps the shape turnable, so whoever opens "
            "it can look from any side. A TABLE is for doing arithmetic on — "
            "putting the numbers in a report, or watching one figure across "
            "twenty prints.\n\n"
            "IT WAITS UNTIL THERE IS SOMETHING TO DESCRIBE. With nothing open "
            "the button is greyed out; open a profile, a measurement or a "
            "chart and it comes alive.", g_take)
        export_hint.setObjectName("hint_export_hint")
        _er = QHBoxLayout(); _er.setContentsMargins(0, 0, 0, 0)
        _er.setSpacing(6)
        _er.addWidget(self._export_btn, 1)
        _er.addWidget(export_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        tk.addLayout(_er)
        v.addWidget(g_take)

        g_app = QGroupBox("The application itself", col)
        ap = QVBoxLayout(g_app)
        ap.setSpacing(6)
        ap.setContentsMargins(8, 6, 8, 8)
        self._glossary_btn = QPushButton("What do these words mean?", g_app)
        self._glossary_btn.setObjectName("secondary")
        self._glossary_btn.setToolTip(
            "Every word this window uses, in plain language: gamut, ΔE, "
            "CIELAB, chroma, hue, lightness, ink limit, rendering intent, "
            "and the rest.\n\n"
            "Written for somebody meeting colour management for the first "
            "time rather than for somebody who already knows the terms — "
            "each entry says what the thing IS, and then why anybody printing "
            "would care.\n\n"
            "It opens in a window of its own, so you can leave it beside this "
            "one while you work, and you can search it.\n\n"
            "Nothing you have open is affected in any way.")
        self._glossary_btn.clicked.connect(self._on_glossary)
        glossary_hint = Hint(
            "Every word this window uses, in plain language: gamut, ΔE, "
            "CIELAB, chroma, hue, lightness, ink limit, rendering intent, "
            "and the rest.\n\n"
            "Written for somebody meeting colour management for the first "
            "time rather than for somebody who already knows the terms — each "
            "entry says what the thing IS, and then why anybody printing "
            "would care about it.\n\n"
            "It opens in a window of its own, so you can leave it beside this "
            "one while you work, and you can search it for a word you have "
            "just met on a button or in a reading.\n\n"
            "Nothing you have open is affected in any way, and it needs no "
            "internet connection: the whole glossary travels with the "
            "application.", g_app)
        glossary_hint.setObjectName("hint_glossary_hint")
        _gr = QHBoxLayout(); _gr.setContentsMargins(0, 0, 0, 0)
        _gr.setSpacing(6)
        _gr.addWidget(self._glossary_btn, 1)
        _gr.addWidget(glossary_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        ap.addLayout(_gr)
        # ARGYLLCMS, MENTIONED BUT NEVER NAGGED ABOUT. Most people never need
        # it: measurements, gamut files and profiles all open without it, and
        # only .cxf, .mxf and .txt are converted by it. So there is no warning
        # on startup and no badge -- just a quiet line for anybody who wonders,
        # and a way to point at it when the search cannot find it.
        self._argyll_label = WrappedLabel("", g_app)
        self._argyll_label.setObjectName("argyllStatus")
        ap.addWidget(self._argyll_label)
        argyll_row = QHBoxLayout()
        argyll_row.setContentsMargins(0, 0, 0, 0)
        argyll_row.setSpacing(6)
        self._argyll_btn = QPushButton("Where ArgyllCMS is…", g_app)
        self._argyll_btn.setObjectName("secondary")
        self._argyll_btn.clicked.connect(self._on_choose_argyll)
        argyll_row.addWidget(self._argyll_btn, 1)
        argyll_hint = Hint(
            "ArgyllCMS is the free toolkit that measures printed charts in "
            "the first place. This viewer uses it for two things, and needs "
            "it for only one of them.\n\n"
            "It is NEEDED to open a .cxf, .mxf or .txt measurement, which it "
            "converts to the .ti3 form everything else uses. If you only ever "
            "open .ti3 files, gamut files or ICC profiles, you never need it "
            "at all and can ignore this.\n\n"
            "It is PREFERRED for ICC profiles, where it works the surface out "
            "in full precision. Without it, profiles are still read here — "
            "the two answers agree to well under one per cent.\n\n"
            "It is looked for automatically in all the usual places, so this "
            "button is only for when it lives somewhere unusual: press it and "
            "choose the folder holding the tools, which is normally the bin "
            "folder inside the ArgyllCMS one. If you do not have it, the "
            "button offers the download page — it is free.", g_app)
        argyll_hint.setObjectName("hint_argyll_hint")
        argyll_row.addWidget(argyll_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        ap.addLayout(argyll_row)

        # THE ENCODER, ON THE SAME FOOTING AS ARGYLLCMS: mentioned quietly for
        # anybody who wonders, never nagged about. One copy travels with the
        # application, so for most people this line only ever says so.
        self._ffmpeg_label = WrappedLabel("", g_app)
        self._ffmpeg_label.setObjectName("argyllStatus")
        ap.addWidget(self._ffmpeg_label)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.setContentsMargins(0, 0, 0, 0)
        ffmpeg_row.setSpacing(6)
        self._ffmpeg_btn = QPushButton("Where ffmpeg is…", g_app)
        self._ffmpeg_btn.setObjectName("secondary")
        self._ffmpeg_btn.clicked.connect(self._on_choose_ffmpeg)
        ffmpeg_row.addWidget(self._ffmpeg_btn, 1)
        ffmpeg_hint = Hint(
            "ffmpeg is the free program that writes films. It is used for "
            "exactly one thing here: saving the turning view as an MP4 or a "
            "WebM.\n\n"
            "You almost certainly do not need to do anything. A copy travels "
            "with this application, so the films work straight out of the box, "
            "and the line above says which one is being used.\n\n"
            "Nothing else needs it. Every file still opens, every still "
            "picture is still saved, and WebP, GIF and APNG moving pictures "
            "are made here without it — so if it is missing, nothing is broken "
            "and the two film formats are simply greyed out.\n\n"
            "This button is for two cases. If you keep your own build and "
            "would rather it were used, point at it. And if the copy that "
            "came with the application is not there — some ways of installing "
            "leave it out, and a few Linux builds are made without H.265 — "
            "point at one that has what you want. Press it and choose the "
            "ffmpeg program itself, not a folder.\n\n"
            "It runs on your computer and nothing is ever sent anywhere. If "
            "you do not have one, the button offers the download page — it is "
            "free, and there is a build for every system.", g_app)
        ffmpeg_hint.setObjectName("hint_ffmpeg_hint")
        ffmpeg_row.addWidget(ffmpeg_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        ap.addLayout(ffmpeg_row)

        self._update_btn = QPushButton("Check for a newer version…", g_app)
        self._update_btn.setObjectName("secondary")
        self._update_btn.setToolTip(
            "Asks the project's releases page whether a newer version has "
            "been published, and tells you what it finds.\n\n"
            "IT NEVER DOWNLOADS OR INSTALLS ANYTHING. The most it does is "
            "show you the version number and offer you the link, which you "
            "open yourself if you want to.\n\n"
            "NOTHING ABOUT YOU IS SENT. No account, no identifier, nothing "
            "about your computer, your printer or your measurements — and no "
            "record of the question is kept here.\n\n"
            "This is the only thing in the whole window that ever reaches the "
            "internet. Everything else works with no connection at all.")
        self._update_btn.clicked.connect(lambda: self._check_updates(asked=True))
        # ITS OWN ⓘ, EVEN THOUGH THE TICKBOX BELOW HAS ONE. They are two
        # different questions -- "ask now" and "ask every time" -- and the
        # icon belonging to the second explained the first only by accident
        # of being nearby.
        ask_hint = Hint(
            "Asks the project's releases page whether a newer version has "
            "been published, right now, and tells you what it finds either "
            "way.\n\n"
            "IT NEVER DOWNLOADS OR INSTALLS ANYTHING. The most it does is "
            "show you the version number and offer you the link, which you "
            "open yourself if you want to. Nothing is replaced behind your "
            "back and the copy you are running is untouched.\n\n"
            "NOTHING ABOUT YOU IS SENT. No account, no identifier, nothing "
            "about your computer, your printer or your measurements — and no "
            "record of the question is kept here.\n\n"
            "This and the tickbox below are the only things in the whole "
            "window that ever reach the internet. Everything else — opening "
            "files, drawing, measuring, saving a picture or a page — works "
            "with no connection at all.", g_app)
        ask_hint.setObjectName("hint_ask_update_hint")
        _ur = QHBoxLayout(); _ur.setContentsMargins(0, 0, 0, 0)
        _ur.setSpacing(6)
        _ur.addWidget(self._update_btn, 1)
        _ur.addWidget(ask_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        ap.addLayout(_ur)
        self._auto_update = QCheckBox("Look for a newer version when the app starts", g_app)
        # ON by default, and deliberately. It is the one thing here that
        # reaches the network, so it is named plainly, it is one click to turn
        # off, and it asks the releases page for a version number and nothing
        # else -- no account, no identifier, nothing about the machine, the
        # printer or the measurements. It never downloads or installs
        # anything. The README and the release notes say so in those words,
        # and they have to keep saying it while this is on.
        self._auto_update.setChecked(True)
        update_hint = Hint(
            "Looks at the project's releases page and tells you whether a "
            "newer version has been published. It never downloads or installs "
            "anything by itself — the most it does is show you the version "
            "number and offer the link.\n\n"
            "Nothing about you, your printer or your measurements is sent. "
            "The request carries no account and no identifier, and there is "
            "no record kept of it here.\n\n"
            "Everything else in this window works with no internet connection "
            "at all.\n\nThis starts switched on, because a colour tool "
            "quietly running a year out of date helps nobody — and it is the "
            "only thing in this window that ever reaches the internet. Untick "
            "it and it will never look again; everything else here works with "
            "no network whatever. You can still ask whenever you like, with "
            "the button just above.", g_app)
        update_hint.setObjectName("hint_update_hint")
        # THE TICKBOX BELONGS UNDER THE BUTTON IT REPEATS, and now it can be:
        # while these controls were loose in the column it was added last of
        # all, AFTER the ♥ links at the very foot, so the only tickbox in the
        # column sat below the two link words with nothing around it. Inside a
        # section it goes where it reads -- immediately under "Check for a
        # newer version…", which is the same question asked automatically.
        self._auto_update_row = QHBoxLayout()
        self._auto_update_row.setContentsMargins(0, 0, 0, 0)
        self._auto_update_row.setSpacing(6)
        self._auto_update_row.addWidget(self._auto_update, 1)
        self._auto_update_row.addWidget(update_hint, 0,
                                        Qt.AlignmentFlag.AlignVCenter)
        ap.addLayout(self._auto_update_row)

        # LAST IN THE SECTION, because it is the one thing here that undoes
        # work. It asks first, and it touches no file.
        self._reset_btn = QPushButton("Start again with standard settings",
                                      g_app)
        self._reset_btn.setObjectName("secondary")
        self._reset_btn.setToolTip(
            "Puts every setting in this column back to what it was the first "
            "time you opened the application.\n\n"
            "WHAT IT CHANGES: how the shape is drawn — its colours, its "
            "opacity, the box and grid, the rings, the cross-section, the "
            "lighting — and the choices under How it looks and This window. "
            "It is the way back when you have changed a dozen things trying "
            "to find one and the picture no longer looks like anybody "
            "else's.\n\n"
            "WHAT IT DOES NOT TOUCH: your files. Nothing you have open is "
            "closed and nothing on disk is altered — the same measurements "
            "and profiles stay loaded and are simply drawn the standard way "
            "again.\n\n"
            "It asks first, so a mis-click costs nothing.")
        self._reset_btn.clicked.connect(self._reset_defaults)
        reset_hint = Hint(
            "Puts every setting in this column back to what it was the first "
            "time you opened the application.\n\n"
            "WHAT IT CHANGES: how the shape is drawn — its colours, its "
            "opacity, the box and grid, the rings, the cross-section, the "
            "lighting — and the choices under How it looks and This window. "
            "It is the way back when you have changed a dozen things trying "
            "to find one and the picture no longer looks like anybody "
            "else's.\n\n"
            "WHAT IT DOES NOT TOUCH: your files. Nothing you have open is "
            "closed and nothing on disk is altered — the same measurements "
            "and profiles stay loaded and are simply drawn the standard way "
            "again. No picture, page or table you have already saved is "
            "changed either.\n\n"
            "It asks first, so a mis-click costs nothing.", g_app)
        reset_hint.setObjectName("hint_reset_hint")
        _rr = QHBoxLayout(); _rr.setContentsMargins(0, 0, 0, 0)
        _rr.setSpacing(6)
        _rr.addWidget(self._reset_btn, 1)
        _rr.addWidget(reset_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        ap.addLayout(_rr)
        v.addWidget(g_app)

        # THE VERY FOOT OF THE COLUMN: where to find the project, and where to
        # say thanks. Quiet, and the last thing met on the way down rather
        # than something competing with the controls. ChromIQ opens the same
        # Ko-fi page from its Welcome window.
        links = QHBoxLayout()
        links.setContentsMargins(0, 10, 0, 2)
        links.setSpacing(12)
        support = QPushButton("♥  Support ChromIQ", col)
        support.setObjectName("footLink")
        support.setCursor(Qt.CursorShape.PointingHandCursor)
        support.setToolTip(
            "Opens ko-fi.com in your browser.\n\n"
            "This application is free and stays fully featured whether or not "
            "anybody ever does this. If it has been useful to you, a coffee is "
            "a kind way to say so.")
        support.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://ko-fi.com/itsab1989")))
        links.addWidget(support, 0)
        website = QPushButton("ChromIQ website", col)
        website.setObjectName("footLink")
        website.setCursor(Qt.CursorShape.PointingHandCursor)
        website.setToolTip(
            "Opens the ChromIQ website in your browser, where the printer "
            "profiling application this one accompanies is introduced, with "
            "screenshots of each step.")
        website.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://itsab1989.github.io/ChromIQ/")))
        links.addWidget(website, 0)
        links.addStretch(1)
        v.addLayout(links)

        # WHO WROTE IT, AND WHAT IT WAS BUILT ON. Asked for in these words:
        # "can you find a good spot at the bottom to add my name Sebastian
        # Reiprich as the author of this gui or whatever would be the correct
        # attribution".
        #
        # The correct attribution is two sentences rather than one, and the
        # second was owed anyway. This window -- every control in the column,
        # every reading, the exported page -- was written for ChromIQ; the
        # drawing underneath began as Qiu Jueqin's MIT-licensed visualizer,
        # which the LICENSE and the README already credit and which the
        # application itself did NOT, because version.UPSTREAM was written
        # down and then never shown to anybody. Both lines belong at the foot
        # of the column, where somebody looking for who made a thing looks.
        #
        # QUIET, AND LAST. It is smaller than the links above it, it takes no
        # accent colour, and nothing about it can be pressed -- a credit that
        # competes with the controls is an advertisement.
        # AND IT IS NAMED AS AN APPLICATION, not as a window. The first draft
        # of this line read "This window by …", which is how the column's
        # preferences group is headed, and it was wrong here for a reason
        # worth keeping: "calling our app 'this window' is a bit of an
        # understatement after all of this work". A heading over two radio
        # buttons can afford to mean the literal window; a credit is naming
        # the whole thing, and the whole thing is an application.
        credit = WrappedLabel(
            f"{APP_NAME} {__version__} — designed and written by "
            "Sebastian Reiprich.\n"
            "Built on Yet Another Color Gamut Visualizer by Qiu Jueqin (MIT).",
            col)
        credit.setObjectName("footCredit")
        credit.setToolTip(UPSTREAM)
        v.addWidget(credit)
        # LAST, once every group exists. Run partway down the column it tidied
        # the groups built so far and left the rest as they were, which looks
        # exactly like a bug in the ones it missed.
        self._tighten_groups(col)
        # FOLDED HERE, AFTER _tighten_groups, AND THE ORDER IS THE FIX.
        # That pass constrains every group to the size of its contents;
        # run before it, a fold was simply undone by it and the group
        # collapsed to 44 px with its heading drawn as one letter.
        for _box, _key, _open in (
                (g_files, "looking", True),
                (g_build, "worked-out", True),
                (g_cmp, "compare", True),
                (g_chart, "chart", True),
                (g_time, "over-time", True),
                (self._chart_look_box, "patch-look", False),
                (g_cs, "measured-against", False),
                (g_look, "looks", False),
                (self._looks_panel, "styling", False),
                (g_vol, "volume", True),
                (self._pair_box, "pair", True),
                (self._drift_box, "drift", True),
                (self._chart_box, "chart-inside", True),
                (g_prefs, "window", False),
                # Saving is why somebody came, so it is open; the
                # housekeeping is set once or never, so it is folded.
                (g_take, "take-away", True),
                (g_app, "application", False),
        ):
            make_foldable(_box, _key, _open)

        # AT LEAST AS WIDE AS WHAT IS IN IT.
        #
        # This column was pinned at 346 px, and one section outgrew it:
        # "How it looks" asks for 372, because "Show what the comparison
        # cannot print" is 270 px of unwrappable label and the ⓘ beside it
        # has to go somewhere. The section was drawn 26 px wider than the
        # column and clipped by the viewport -- its right-hand border cut
        # off, and about four pixels of that row's ⓘ with it. Reported from
        # a screenshot: "the How it looks section seems cut off on its right
        # side", which is exactly what it was.
        #
        # 346 stays the FLOOR rather than the answer, so nothing about the
        # column narrows, and a label added tomorrow widens it by however
        # much it needs instead of being quietly cut. Measured here rather
        # than guessed: the width comes from the layout once every group
        # exists, which is why this is the last thing in the method.
        # THE MINIMUM, NOT THE HINT. A group's size HINT is what it would
        # like; its MINIMUM is what it will take anyway, and a section whose
        # widest label cannot wrap takes it whatever the column says. Sized
        # from the hint this came out 363 against a section that insists on
        # 372, and the border was still cut -- by one pixel instead of
        # sixteen, which is the same fault and harder to see.
        col.setFixedWidth(max(346, col.sizeHint().width(),
                              col.minimumSizeHint().width(),
                              v.minimumSize().width()))
        return col


    # ------------------------------------------------------------- pictures
    def _is_picture(self, name: str) -> bool:
        """Whether a shape on screen came from a picture rather than a printer."""
        for path, _g, _m in self._slots:
            if path.stem == name:
                return str(path) in self._image_facts
        return False

    #: EVERY READOUT, IN READING ORDER, NAMED ONCE.
    #:
    #: This list was written out in three separate places -- the one that
    #: clears them when the files are closed, the one that copies them into a
    #: saved page, and the stand-in the tests use. Adding the colour-family
    #: lines meant updating three, and two of them were found only afterwards:
    #: the report survived "Close them all", and it was missing from every
    #: saved page. A list that must be kept in step by hand will not be.
    READOUTS = ("_coverage", "_picture_loss", "_pair", "_drift",
                "_drift_worst", "_drift_families", "_drift_families_note",
                "_chart_headline", "_chart_rows", "_chart_spread")

    def _readout_text(self) -> str:
        """Everything the readouts are showing, as plain text.

        Read from the labels themselves rather than worked out again, so the
        page cannot disagree with the window it came from.
        """
        parts = []
        volume = self._volume.text().strip()
        if volume and volume != "—":
            parts.append(f"Colour held: {volume} {self._volume_units()}")
        for name in self.READOUTS:
            label = getattr(self, name, None)
            if label is None:
                continue
            try:
                if label.isVisible() and label.text().strip():
                    parts.append(label.text().strip())
            except Exception:              # noqa: BLE001 — a note is not vital
                continue
        return "\n\n".join(parts)

    def _picture_shapes(self) -> list:
        """The names in the picture, for suggesting what to call the file."""
        names = [path.stem for path, _g, _m in self._slots]
        if self._reference is not None:
            names.append(self._reference[0])
        # AND A CHART, BUT ONLY ONE THAT WOULD BE DRAWN. A chart open with no
        # profile to place it through is not in the picture either way, so
        # naming it would promise the reader something back that was never
        # there. Measured: _chart set, _chart_drawable False, and the right
        # sentence is no sentence.
        if self._chart is not None and self._chart_drawable():
            names.append(Path(self._chart[0]).stem)
        if self._chart is not None and self._chart_placed is not None:
            names.append(self._chart[0].stem)
        return names

    def _on_picture(self) -> None:
        """Save what is on screen as a picture.

        WHAT IS ON SCREEN INCLUDES THE RUN, and this asked only about files.
        The picture is re-rendered from the view itself -- whatever page it is
        showing -- so the run needed nothing but to be counted as a picture
        here; the guard was turning the button's own action away.
        """
        if (not self._slots and self._reference is None
                and not self._chart_drawable()
                and not getattr(self, "_run_drawn", False)):
            return
        dlg = PictureDialog(self)
        if not dlg.exec():
            return
        want = dlg.choices()
        why = picture.check_transparency(want["format"], want["background"])
        if why:
            Notice.warn(self, "That cannot be see-through", why)
            return
        suggested = picture.suggest_name(
            self._picture_shapes(), want["format"],
            slicing=self._slice_on.isChecked(),
            lightness=float(self._slice_at.value()),
            moving=want["moving"])
        # THE EXTENSION IS NOT ALWAYS THE CHOICE. H.264 and H.265 both live in
        # an .mp4, VP9 in a .webm, and an APNG is a .png — so it comes from one
        # place rather than from whichever name the list happened to use.
        suffix = picture.extension_for(want["format"])
        chooser = self._file_dialog("Where should the picture go?",
                                    QFileDialog.FileMode.AnyFile,
                                    f"{'Film' if picture.is_film(want['format']) else 'Picture'}"
                                    f" (*.{suffix})", suggested, profiles=False)
        chooser.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        chooser.setDefaultSuffix(suffix)
        if not chooser.exec():
            return
        target = picture.next_free(Path(chooser.selectedFiles()[0]))
        self._last_folder = str(target.parent)
        try:
            if want["moving"]:
                made = self._save_moving(target, want)
            else:
                made = self._save_still(target, want)
        except Stopped:
            _log().info("picture stopped before it was finished")
            Notice.say(self, "Stopped",
                       "Nothing was written. The view is exactly as it was, "
                       "and you can start again whenever you like.")
            return
        except movie.NoEncoder as why:
            _log().info("no encoder for %s: %s", want["format"], why)
            Notice.warn(self, "That kind of film cannot be made here", str(why))
            return
        except Exception as exc:            # noqa: BLE001 — always explain
            _log().warning("could not save %s: %s", target.name, exc)
            Notice.warn(self, "That picture could not be saved", str(exc))
            return
        _log().info("saved %s (%s)", made.name, picture.human_size(
            made.stat().st_size if made.exists() else 0))
        Notice.say(self, "Saved",
                   f"Written to\n{made}\n\n"
                   f"{picture.human_size(made.stat().st_size)}."
                   + ("\n\nIt is a film, so it opens with a play button rather "
                      "than showing straight away. It repeats when the player "
                      "is set to repeat — a moving picture such as WebP loops "
                      "by itself, and that is the difference between the two."
                      if picture.is_film(want["format"]) else ""))

    def _background_for(self, want, which: str = "background") -> "str | None":
        """A chosen colour, or None to leave that part as it looks on screen."""
        choice = want.get(which, "as-shown")
        if which == "walls" and choice == "same":
            choice = want.get("background", "as-shown")
            custom = want.get("colour", "#ffffff")
        else:
            custom = want.get("wall_colour" if which == "walls" else "colour",
                              "#ffffff")
        if choice == "as-shown":
            return None
        if choice == "transparent":
            return "rgba(0,0,0,0)"
        if choice == "custom":
            return custom
        return {"white": "#ffffff", "black": "#000000"}.get(choice)

    def _save_still(self, target: Path, want) -> Path:
        """One picture, re-rendered by the viewer at the size asked for.

        Rendered rather than grabbed, because a still is worth being sharp:
        this can make a picture far larger than the window, and can make one
        that is not pixels at all.
        """
        import base64
        import json

        width = picture.clamp_width(want["width"])
        height = int(round(width * self._view.height()
                           / max(1, self._view.width())))
        paper = self._background_for(want)
        walls = self._background_for(want, "walls")
        options = {"format": want["format"], "width": width, "height": height,
                   "scale": 1}
        # THE WALLS ARE NOT THE PAGE. Clearing paper_bgcolor alone left the
        # three panels the grid sits on still painted, so "see-through" came
        # out with a solid box floating in nothing. They are separate
        # properties and both have to be said.
        changes, restore = {}, {}
        if paper is not None:
            changes["paper_bgcolor"] = paper
            changes["plot_bgcolor"] = paper
            restore["paper_bgcolor"] = None
            restore["plot_bgcolor"] = None
        if walls is not None:
            for axis in ("xaxis", "yaxis", "zaxis"):
                changes[f"scene.{axis}.backgroundcolor"] = walls
                restore[f"scene.{axis}.backgroundcolor"] = None
        script = (
            "(function(){window.__shot=null;window.__shotErr=null;"
            "var d=document.getElementsByClassName('plotly-graph-div')[0];"
            "if(!d){window.__shotErr='nothing is drawn';return;}"
            "var was={};"
            + (f"var want={json.dumps(changes)};"
               "Object.keys(want).forEach(function(k){"
               "  var cur=d.layout, parts=k.split('.'), i;"
               "  for(i=0;i<parts.length-1&&cur;i++)cur=cur[parts[i]];"
               "  was[k]=cur?cur[parts[parts.length-1]]:null;});"
               "Plotly.relayout(d,want);" if changes else "")
            + f"Plotly.toImage(d,{json.dumps(options)})"
              ".then(function(u){window.__shot=u;"
            + ("Plotly.relayout(d,was);" if changes else "")
            + "},function(e){window.__shotErr=String(e);"
            + ("Plotly.relayout(d,was);" if changes else "")
            + "});})()")
        self._run_js(script)
        url = self._wait_for("window.__shot", "window.__shotErr", seconds=90)
        head, _, payload = url.partition(",")
        if want["format"] == "svg":
            from urllib.parse import unquote
            target.write_text(unquote(payload), encoding="utf-8")
        else:
            target.write_bytes(base64.b64decode(payload))
        return target

    def _page_backgrounds(self, want) -> dict:
        """What the page has to be told so the picture gets the background asked.

        The page colour and the three panels the grid is drawn on are separate
        properties, and both have to be said: clearing the first alone leaves a
        solid box floating in nothing.
        """
        paper = self._background_for(want)
        walls = self._background_for(want, "walls")
        changes: dict = {}
        if paper is not None:
            changes["paper_bgcolor"] = paper
            changes["plot_bgcolor"] = paper
        if walls is not None:
            for axis in ("xaxis", "yaxis", "zaxis"):
                changes[f"scene.{axis}.backgroundcolor"] = walls

        # THE LETTERING HAS TO BE READABLE ON WHATEVER IT LANDS ON. The numbers
        # and names round the box are drawn in the colour the window is using,
        # and saving on a white background with the dark theme's pale grey left
        # a picture whose scale could not be read at all — while nothing about
        # it looked broken, which is why it went unnoticed.
        #
        # What they sit on is the WALLS where there are walls, and the page
        # otherwise; that is the surface behind the text, so that is what
        # decides it.
        behind = walls if walls not in (None, "rgba(0,0,0,0)") else paper
        ink = self._ink_choice(want, "lettering", behind)
        if ink is not None:
            changes["font.color"] = ink
            changes["title.font.color"] = picture.mix(
                behind or ink, ink, 0.62) if behind else ink
            changes["legend.font.color"] = ink
            for axis in ("xaxis", "yaxis", "zaxis"):
                changes[f"scene.{axis}.color"] = ink
        lines = self._ink_choice(want, "gridlines", behind, grid=True)
        if lines is not None:
            for axis in ("xaxis", "yaxis", "zaxis"):
                changes[f"scene.{axis}.gridcolor"] = lines
                changes[f"scene.{axis}.zerolinecolor"] = lines
        return changes

    def _ink_choice(self, want, which: str, behind, grid: bool = False):
        """The colour asked for the lettering or the grid lines, or None.

        None means "leave it exactly as it looks on screen", which is both the
        answer when nothing was chosen and the right answer for a see-through
        background — nobody here knows what page that picture is going onto,
        so guessing would be worse than leaving it.
        """
        choice = want.get(which, "follow")
        if choice == "custom":
            return want.get(f"{which}_colour", picture.DARK_INK)
        if choice == "dark":
            return picture.mix("#ffffff", picture.DARK_INK, 1.0) if not grid \
                else picture.grid_for("#ffffff")
        if choice == "light":
            return picture.LIGHT_INK if not grid else picture.grid_for("#111111")
        if choice != "follow" or behind in (None, "rgba(0,0,0,0)"):
            return None
        return picture.grid_for(behind) if grid else picture.ink_for(behind)

    def _set_page_backgrounds(self, changes: dict, restore: bool = False) -> None:
        """Put the chosen background on the live page, or take it off again.

        A MOVING PICTURE HAD NONE OF THIS. The background choices reached the
        still route only, so asking for white, or for see-through, and then
        saving a loop gave back whatever was on screen — quietly, which is the
        worst way to be wrong.
        """
        import json

        if not changes:
            return
        want = {k: None for k in changes} if restore else changes
        # EVERY GRAPH IN THE PAGE, for the same reason the live restyles now
        # do: two rooms are two graphs, and a background put on one of them is
        # a saved film with one room styled and one not.
        self._run_js_now(
            "(function(){var divs=document.getElementsByClassName("
            "'plotly-graph-div');for(var r=0;r<divs.length;r++)"
            f"Plotly.relayout(divs[r],{json.dumps(want)});}})()")

    def look_choices(self) -> dict:
        """The styling chosen in the left-hand column, for saving a picture."""
        return self._looks_panel.values()

    def _on_look_changed(self) -> None:
        """Put the chosen look on the view, or take it off again.

        THE VIEW IS THE PREVIEW, so this runs on every change rather than only
        when something is saved. It is a relayout of the page that is already
        drawn — no rebuilding, no re-reading of anything — so it is quick
        enough to sit under a colour picker being dragged.
        """
        # The section settles itself as it is built, which happens before the
        # window has finished putting itself together — so there is a moment
        # when this is called and there is nothing yet to call it on.
        panel = getattr(self, "_looks_panel", None)
        if panel is None or getattr(self, "_view", None) is None:
            return
        self._set_page_backgrounds(self._page_view())
        self._remember_look()

    def _page_view(self) -> dict:
        """What the page should be wearing right now.

        ALWAYS SOMETHING EXPLICIT, never "put it back to the default". Asking
        Plotly to forget a colour does not return it to what this application
        set — it returns it to Plotly's own default, which is white. So
        unticking Show it in the window too turned the window white instead of
        returning it to its own dark, and every export left it that way after
        it finished. The window's two schemes are written down as looks
        precisely so there is something exact to go back TO.
        """
        panel = getattr(self, "_looks_panel", None)
        if panel is not None and panel.live():
            want = panel.values()
        else:
            want = (picture.LIGHT_THEME if getattr(self, "_appearance", "dark")
                    == "light" else picture.DARK_THEME)
        wanted = self._page_backgrounds(want)
        # SEE-THROUGH CANNOT BE SHOWN IN A WINDOW, so on screen it stands in as
        # white — which is what a cut-out picture is nearly always going onto.
        # The small picture in the Save window shows the real thing, on
        # chequers, and says so.
        return {k: ("#ffffff" if v == "rgba(0,0,0,0)" else v)
                for k, v in wanted.items()}

    def _remember_look(self) -> None:
        """Keep the look for next time, like every other setting here."""
        if getattr(self, "_store", None) is None:
            return
        try:
            kept = dict(self._looks_panel.values())
            kept["look"] = self._looks_panel.chosen_look()
            kept["details"] = self._looks_panel.details_open()
            kept["live"] = self._looks_panel.live()
            self._store.setValue("picture_look", json.dumps(kept))
        except Exception as exc:                 # noqa: BLE001 — never fatal
            _log().debug("the look could not be remembered: %s", exc)

    def _restore_look(self) -> None:
        saved = self._store.value("picture_look", "")
        if not saved:
            return
        try:
            self._looks_panel.restore(json.loads(saved))
        except Exception as exc:                 # noqa: BLE001
            _log().debug("the saved look could not be read: %s", exc)

    def preview_frame(self, want, across: int = 340):
        """One frame of the scene as it would be saved, small, for the dialog.

        Made by the export's own steps -- the same backgrounds, the same
        lettering, and for a see-through picture the same arithmetic over two
        grounds -- so what is shown is what will be written rather than an
        artist's impression of it.
        """
        from PIL import Image

        changes = self._page_backgrounds(want)
        see_through = self._background_for(want) == "rgba(0,0,0,0)"
        try:
            if see_through:
                pale = {k: ("#ffffff" if v == "rgba(0,0,0,0)" else v)
                        for k, v in changes.items()}
                dark = {k: ("#000000" if v == "rgba(0,0,0,0)" else v)
                        for k, v in changes.items()}
                for key in ("paper_bgcolor", "plot_bgcolor"):
                    pale.setdefault(key, "#ffffff")
                    dark.setdefault(key, "#000000")
                self._set_page_backgrounds(pale)
                on_white = Image.fromqpixmap(self._view.grab()).convert("RGB")
                self._set_page_backgrounds(dark)
                on_black = Image.fromqpixmap(self._view.grab()).convert("RGB")
                frame = Image.fromarray(picture.alpha_from_two_grounds(
                    np.asarray(on_white), np.asarray(on_black)), "RGBA")
            else:
                self._set_page_backgrounds(changes)
                frame = Image.fromqpixmap(self._view.grab()).convert("RGBA")
        finally:
            self._set_page_backgrounds(self._page_view())
        tall = max(1, int(round(across * frame.height / max(1, frame.width))))
        frame = frame.resize((across, tall), Image.LANCZOS)
        if see_through:
            frame = Image.alpha_composite(_chequerboard(across, tall), frame)
        shot = QPixmap.fromImage(QImage(
            frame.convert("RGBA").tobytes(), frame.width, frame.height,
            frame.width * 4, QImage.Format.Format_RGBA8888))
        return shot

    def _finish_writing(self, writer, progress, reached: int = 78) -> Path:
        """Let the file be written without the window going dead.

        THIS IS THE STEP THAT USED TO LOOK LIKE A HANG. The frames are taken
        smoothly and the window answers throughout that part; then everything
        stopped for several seconds while the file was put together, with no
        bar moving and no way to tell it apart from a crash.

        So the writing happens on a thread of its own and the window keeps
        painting. A film can also be abandoned part way, because the encoder is
        a separate program that can simply be stopped; the picture kinds cannot
        be, and the dialog says so rather than offering a button that does
        nothing.
        """
        import threading
        import time as _time

        outcome: dict = {}

        def work():
            try:
                outcome["made"] = writer.finish()
            except BaseException as exc:                  # noqa: BLE001
                outcome["trouble"] = exc

        # THE BAR CREEPS ON RATHER THAN JUMPING TO THE END. Nobody can say how
        # far through an encoder really is, so the rest of the bar is filled at
        # a steady rate that reaches the end at about the time this usually
        # takes — and simply waits there if it takes longer. It never claims to
        # be finished before it is.
        import threading
        import time as _time

        started = _time.time()
        # Measured on this application's own exports: writing an animated WebP
        # of a few hundred frames takes a handful of seconds, and a film has
        # almost nothing left to do because the encoder kept up.
        expected = 0.4 if writer.can_stop_while_writing else 6.0
        progress.setLabelText(
            "Writing the file…\nThis is the part that takes a moment."
            if writer.can_stop_while_writing else
            "Writing the file…\nThis last step cannot be stopped part way.")
        # THE BUTTON KEEPS ITS WORD AND LOSES ITS POWER, rather than the
        # other way about. Changing the text of a button on a dialog that is
        # already showing leaves it at the width it was sized for, so the
        # longer word arrived clipped. A greyed-out Stop says the same thing,
        # stays the same size, and matches the sentence above it.
        if not writer.can_stop_while_writing:
            for button in progress.findChildren(QPushButton):
                button.setEnabled(False)
        QApplication.processEvents()

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        asked_to_stop = False
        while thread.is_alive():
            if (not asked_to_stop and progress.wasCanceled()
                    and writer.can_stop_while_writing):
                asked_to_stop = True
                writer.cancel()
            along = min(1.0, (_time.time() - started) / max(0.1, expected))
            progress.setValue(int(reached + (99 - reached) * along))
            QApplication.processEvents()
            _time.sleep(0.02)
        thread.join()
        progress.setValue(100)
        if asked_to_stop:
            raise Stopped("stopped while the file was being written")
        if "trouble" in outcome:
            raise outcome["trouble"]
        return outcome["made"]

    def _save_moving(self, target: Path, want) -> Path:
        """A loop that turns, grabbed frame by frame from the live view.

        Grabbed rather than re-rendered, and stepped to exact angles rather
        than left to run: measured on this machine, re-rendering a frame takes
        about 630 ms against 6 ms to grab one, so a six-second loop would cost
        a minute and a half instead of a few seconds. Stepping also makes the
        loop close exactly, which is what stops it jerking once every time
        round.

        EACH FRAME IS FINISHED AS IT IS TAKEN -- brought down to the size asked
        for, given its background, and handed to the writer -- rather than kept
        and dealt with at the end. For a film that means the encoding runs
        alongside the grabbing and nothing is held at all; for the picture
        kinds it means what is kept is the small version rather than the full
        screen, which is the difference between forty megabytes and four
        hundred for a long loop.
        """
        import movie
        from PIL import Image

        mode = self._turn_mode.currentData()
        tilt_mode = self._tilt_mode.currentData()
        if mode == "off" and tilt_mode == "off":
            mode = "round"                  # something has to move
        count = picture.frames_for(want["seconds"], want["fps"],
                                   mode if mode != "off" else tilt_mode)
        angles = (picture.turn_angles(count, mode,
                                      float(self._turn_sweep.value()))
                  if mode != "off" else [0.0] * count)
        # UP AND DOWN GOES INTO THE FILE TOO. It was left out entirely, so a
        # shape set to tip as well as turn came out only turning.
        tilts = (picture.turn_angles(count, tilt_mode,
                                     float(self._tilt_sweep.value()))
                 if tilt_mode != "off" else [0.0] * count)
        # HOW BIG THE PICTURE WILL BE IS SETTLED BEFORE ANYTHING IS TAKEN.
        # A film's size cannot change part way through -- the encoder is told
        # once, at the start -- so it is worked out from one grab up front and
        # every frame is brought to exactly that.
        shot = self._view.grab()
        wide, tall = shot.width(), shot.height()
        asked = int(want.get("moving_width") or 0)
        if 0 < asked < wide:
            tall = int(round(tall * asked / wide))
            wide = asked
        fmt = want["format"]
        codec = picture.codec_for(fmt)
        if codec:
            wide, tall = movie.even(wide), movie.even(tall)
        paper = self._background_for(want)
        see_through = paper == "rgba(0,0,0,0)"
        writer = movie.writer_for(fmt, target, wide, tall, want["fps"],
                                  want["quality"], transparent=see_through,
                                  codec=codec)
        # THE PAGE IS TOLD FIRST, and the frames are grabbed with it already
        # wearing the background asked for.
        changes = self._page_backgrounds(want)
        # SEE-THROUGH IS NOT A COLOUR THE PAGE CAN BE GIVEN. A copy of the
        # screen has no see-through in it — the graphics card has already put
        # everything on a solid ground — so asking politely and grabbing gave
        # back a picture that was quietly solid. Instead each frame is taken
        # twice, once on white and once on black, and the two are subtracted:
        # see picture.alpha_from_two_grounds, which is exact rather than a
        # trick and gets the soft edges right.
        pale = dark = None
        if see_through:
            pale = {k: ("#ffffff" if v == "rgba(0,0,0,0)" else v)
                    for k, v in changes.items()}
            dark = {k: ("#000000" if v == "rgba(0,0,0,0)" else v)
                    for k, v in changes.items()}
            # Anything the person left as it looks on screen is opaque, and
            # must stay opaque in both passes or it would come out ghosted.
            for key in ("paper_bgcolor", "plot_bgcolor"):
                pale.setdefault(key, "#ffffff")
                dark.setdefault(key, "#000000")
            self._set_page_backgrounds(pale)
        else:
            self._set_page_backgrounds(changes)
        # A SOLID COLOUR IS STILL LAID UNDERNEATH as well, because the page
        # answers with the colour but the grab can come back with an alpha
        # channel of its own; compositing on a flat ground of exactly the
        # colour asked for makes the two agree whatever the platform does.
        flat = None
        if paper and not see_through:
            colour = QColor(paper)
            flat = Image.new("RGBA", (wide, tall),
                             (colour.red(), colour.green(), colour.blue(), 255))

        was_on = self._spin_on.isChecked()
        self._spin_on.setChecked(False)     # we are driving it ourselves
        QApplication.processEvents()
        # SAY WHAT IS HAPPENING, AND LET IT BE STOPPED. Taking a hundred and
        # sixty frames keeps the window busy for a quarter of a minute, and
        # the shape stands still throughout because it is being stepped rather
        # than left to turn -- so without this the application looks as though
        # it has hung, which is exactly how it looked. QProgressDialog is used
        # rather than something of our own because it pumps the event queue
        # itself: the window keeps painting, and the shape can be seen moving
        # through the frames as they are taken.
        # THE BAR COVERS THE WHOLE JOB, not just the frames. Counting only the
        # frames put it at 100% the moment the last one was taken — with a
        # good few seconds of writing still to come, which is a bar saying
        # "finished" while nothing is finished. Taking the frames is most of
        # the work for a film, because the encoder keeps up as they arrive,
        # and rather less than that for a WebP, which cannot start until it
        # has them all. So the frames fill the bar to there, and the writing
        # has the rest.
        frames_reach = 96 if codec else 78
        progress = QProgressDialog("Taking the frames…", "Stop", 0, 100, self)
        progress.setWindowTitle("Saving a moving picture")
        # ROOM BETWEEN THE BAR AND THE BUTTON. Qt lays a progress dialog out
        # tightly enough that the two touch, which reads as one broken control
        # rather than two.
        progress.setMinimumWidth(360)
        # AND THE NUMBER IN THE MIDDLE OF THE BAR, which Qt does not manage on
        # its own — see CentredProgressBar.
        progress.setBar(CentredProgressBar(progress))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        taken, previous, tilted, stopped = 0, 0.0, 0.0, False
        try:
            for number, (angle, lift) in enumerate(zip(angles, tilts), start=1):
                if progress.wasCanceled():
                    stopped = True
                    break
                self._run_js_now("if(window.cqSpin)window.cqSpin.nudge("
                                 f"{angle - previous},{lift - tilted});")
                previous, tilted = angle, lift
                if see_through:
                    # The same frame on two grounds, subtracted. The shape does
                    # not move between the two — it is being stepped by hand,
                    # not left to turn — so the only difference between them is
                    # the ground, which is what makes the arithmetic exact.
                    on_white = Image.fromqpixmap(self._view.grab()).convert("RGB")
                    self._set_page_backgrounds(dark)
                    on_black = Image.fromqpixmap(self._view.grab()).convert("RGB")
                    self._set_page_backgrounds(pale)
                    frame = Image.fromarray(picture.alpha_from_two_grounds(
                        np.asarray(on_white), np.asarray(on_black)), "RGBA")
                else:
                    frame = Image.fromqpixmap(self._view.grab()).convert("RGBA")
                # SMALLER IF ASKED, never larger: this is a copy of the screen,
                # and no amount of enlarging puts back detail it never had.
                if frame.size != (wide, tall):
                    frame = frame.resize((wide, tall), Image.LANCZOS)
                if flat is not None:
                    frame = Image.alpha_composite(flat, frame)
                writer.add(frame)
                taken += 1
                progress.setLabelText(
                    f"Taking the frames… {number} of {len(angles)}")
                progress.setValue(int(frames_reach * number / len(angles)))
        except BaseException:
            writer.cancel()
            raise
        finally:
            # PUT IT BACK. Whatever happens, the view returns to where it was:
            # an export must not quietly leave the shape facing elsewhere, nor
            # wearing the background somebody picked for a file.
            self._run_js_now(f"if(window.cqSpin)window.cqSpin.nudge("
                             f"{-previous},{-tilted});")
            self._set_page_backgrounds(self._page_view())
            self._spin_on.setChecked(was_on)
            QApplication.processEvents()
        if stopped:
            # NOTHING IS WRITTEN. Stopping half way through would otherwise
            # leave a file holding part of a journey, which loops badly and
            # looks like a fault rather than a choice.
            writer.cancel()
            progress.close()
            raise Stopped("stopped before the picture was finished")
        if not taken:
            writer.cancel()
            progress.close()
            raise ValueError("no frames could be taken")
        try:
            made = self._finish_writing(writer, progress, frames_reach)
        finally:
            progress.close()
        return made

    def _show_page(self, path) -> None:
        """Put a newly written page on screen.

        A SECOND VIEW WAS TRIED HERE AND TAKEN OUT AGAIN. Loading into a spare
        and swapping the two on loadFinished removes the blink that every
        rebuild causes -- and it left the frame EMPTY: the widget that ended
        up in the layout was the one that had just been sent to about:blank.
        Reported with a photograph of a window with no picture in it at all.

        A blink is cosmetic. An empty viewer is not, and a cure that can do
        that has no business in the redraw path until it is proved by a driver
        that watches the frame rather than the address in it.
        """
        self._view.setUrl(QUrl.fromLocalFile(str(path)))

    def _run_js_now(self, script: str, seconds: float = 2.0) -> None:
        """Run it and WAIT until the page has actually done it.

        runJavaScript hands back immediately. Turning a frame and grabbing it
        in the next breath therefore photographed the shape before it had
        moved: measured, one frame in forty-eight came out identical to the
        one before it, and the frame after covered twice the distance -- which
        is exactly what a jump in a loop looks like.
        """
        import time as _time
        page = self._view.page()
        if page is None:
            return
        # WAIT FOR THE PICTURE TO BE PAINTED, not for the script to return.
        # The shape is drawn by the graphics card on its own schedule, so a
        # script that has finished says nothing about what is on screen yet:
        # waiting only for the script still grabbed thirteen frames in
        # forty-eight before they had moved. Two turns of the browser's own
        # drawing loop mean a frame has actually been put up.
        page.runJavaScript(
            script + ";window.__painted=0;"
            "requestAnimationFrame(function(){"
            "requestAnimationFrame(function(){window.__painted=1;});});")
        end = _time.time() + seconds
        while _time.time() < end:
            got = {}
            page.runJavaScript("window.__painted",
                               lambda r: got.setdefault("r", r))
            waited = _time.time() + 1.0
            while "r" not in got and _time.time() < waited:
                QApplication.processEvents()
                _time.sleep(0.001)
            if got.get("r"):
                break
            QApplication.processEvents()
            _time.sleep(0.002)
        QApplication.processEvents()

    def _run_js(self, script: str) -> None:
        page = self._view.page()
        if page is not None:
            page.runJavaScript(script)

    def _wait_for(self, ready: str, failed: str, seconds: float = 30.0):
        """Wait for a value the page sets when it has finished.

        runJavaScript hands back before a promise resolves, so asking for the
        picture and reading the answer in the same breath returns nothing --
        which is how a first attempt at timing this measured the call rather
        than the work, and was twenty times too fast.
        """
        import time as _time
        page = self._view.page()
        if page is None:
            raise ValueError("there is no page to take a picture of")
        end = _time.time() + seconds
        while _time.time() < end:
            box = {}
            page.runJavaScript(f"[{ready},{failed}]",
                               lambda r: box.setdefault("r", r))
            waited = _time.time() + 2.0
            while "r" not in box and _time.time() < waited:
                QApplication.processEvents()
                _time.sleep(0.005)
            got = box.get("r") or [None, None]
            if got[1]:
                raise ValueError(str(got[1]))
            if got[0]:
                return got[0]
            QApplication.processEvents()
            _time.sleep(0.02)
        raise ValueError("the picture took too long to make")

    # ------------------------------------------------------------------ actions
    def _set_appearance(self, which: str) -> None:
        """Switch to light or dark, and remember it for next time."""
        if which == self._appearance:
            return
        self._appearance = which
        self._store.setValue("appearance", which)
        self._apply_mode()
        # THE RUN'S PICTURE IS DRAWN BY THE PANEL, so it has to be told too.
        # Without this, switching between light and dark while following a
        # device emptied the view and nothing brought it back: _redraw stands
        # aside while the run owns the picture, and the panel had not been
        # asked to draw a new one. Reported from the window: "when a run is
        # active and changing the window appearance the viewer is cleared and
        # i can't bring the view of the run back".
        panel = getattr(self, "_timeline", None)
        if panel is not None:
            panel.look(which)
        if self._slots:
            self._redraw()          # the scene is repainted to match
        # AND THE COLUMN IS ASKED ITS SIZE AGAIN, ONCE THE POLISH HAS LANDED.
        # Re-polishing every widget is when Qt applies stylesheet padding, so
        # the sections answer a different width after a theme change than
        # before it, and the widest of them was then cut on the right --
        # reported in the same breath as the emptied view: "it also makes the
        # one device over time section wider and its frame cut off on the
        # right".
        #
        # ASKED IMMEDIATELY, THE ANSWER IS STILL THE OLD ONE. Measured by
        # driving the switch: the section reached 548 px in a 403 px viewport
        # on the first change and was correct on every one after it, which is
        # exactly what "asked one event too early" looks like.
        QTimer.singleShot(0, self._widen_the_column_to_fit_it)

    def _ask_the_layouts_again(self) -> None:
        """Every layout asked how much room it needs, now the styling is on.

        A layout answers that question once and keeps the answer. The
        stylesheet is applied at POLISH, which happens later -- so a grid can
        have decided its rows are 18 pixels tall while every button in them
        will draw 20, and there is nothing to make it think again.

        Measured, in the window and not from the code: the five radios under
        "How the shapes are coloured" sat 17 pixels apart in rows they each
        needed 20 for. The checked one was drawn as half a circle and the
        descenders of "By lightness" were cut off, and it is visible in any
        screenshot of that panel.

        Asking again is cheap, happens once as the window comes up, and fixes
        the whole family rather than the one row it was noticed on.
        """
        for lay in self.findChildren(QLayout):
            lay.invalidate()
        if self.layout() is not None:
            self.layout().activate()
        self._widen_the_column_to_fit_it()

    def _widen_the_column_to_fit_it(self) -> None:
        """The controls column, now that its sections know their own size.

        Same reason as above, and found the same way -- from a screenshot of
        the real window rather than from the code. "How it looks" holds
        "Show what the comparison cannot print", 270 px of label that a tick
        cannot wrap, with an ⓘ beside it; the section will take 372 px
        whatever it is told. The column was pinned at 346 and the scroll area
        at 366 with its horizontal scrollbar deliberately off, so the section
        was simply cut: its right-hand border gone, and about four pixels of
        that row's ⓘ with it.

        Asked before the window is polished, every section still answers 363,
        which is why sizing it at build time left the fault behind at one
        pixel instead of sixteen. Asked here, they answer honestly.

        The 346 floor stays, so nothing narrows; a longer label widens the
        column by exactly what it needs instead of being quietly clipped.
        """
        area = getattr(self, "_controls_area", None)
        column = area.widget() if area is not None else None
        if column is None:
            return
        # THE COLUMN'S OWN MARGINS ARE PART OF WHAT IT NEEDS, which is why
        # this asks the column first and the sections second: a section that
        # needs 372 needs 376 of column around it. See _build_controls.
        # ASK A FOLDED GROUP WHAT IT WOULD NEED IF IT WERE OPEN. A shut group
        # says "as wide as my heading", so a column sized from that grew every
        # time somebody opened one -- and a column that jumps wider under the
        # hand is worse than the clipping it was meant to cure. Reported at
        # once: "when i enlarged the how it looks section the whole left panel
        # became wider which it should not".
        #
        # ITS BODY STILL ANSWERS WHILE IT IS HIDDEN, which is what makes this
        # possible: measured, "This window" folded says 119 px for itself and
        # 250 for its body. So the column is sized ONCE, for the widest thing
        # it could ever have to show, and folding changes nothing about it.
        # HOW MUCH A GROUP'S OWN FRAME COSTS, measured from one that is
        # actually open rather than worked out from a folded one. Folded, a
        # group's least width is its HEADING, which is smaller than its
        # contents -- so the difference came out negative, the frame counted
        # as nothing, and the column was fourteen pixels short. That is what
        # cut the ⓘ column down the right-hand side.
        # A HIDDEN BODY UNDER-REPORTS ITSELF, AND THAT IS WHAT MADE THE COLUMN
        # GROW A SECOND TIME. The note above says a folded group's body still
        # answers honestly while it is hidden. Measured, it does not quite:
        #
        #     How it looks                     hidden 320   shown 348
        #     What the colours are measured..  hidden 287   shown 315
        #     Viewer and export styling        hidden 182   shown 204
        #
        # Polishing it does not help; only showing it does. So the column was
        # sized from 320, and the next time anything asked -- opening the
        # section, or changing the appearance, which re-polishes everything --
        # the same body said 348 and the column grew by exactly 28. Reported
        # twice, the second time as "the left panel became wider again for
        # whatever reason".
        #
        # SO EACH BODY IS MEASURED ONCE, HONESTLY: shown, asked, and put back,
        # with the column's painting switched off around it so nothing of it
        # reaches the screen. The answer is kept on the group, and every later
        # call uses it -- which is what makes the width settle instead of
        # ratcheting upwards.
        column.setUpdatesEnabled(False)
        try:
            for box in column.findChildren(QGroupBox):
                body = getattr(box, "body", None)
                if body is None or hasattr(box, "_widest_body"):
                    continue
                # AND ITS OWN FRAME IS MEASURED IN THE SAME BREATH, for the
                # same reason: the difference between what a group asks for
                # and what its contents ask for is only true while the
                # contents are THERE. Asked of a folded group it is the width
                # of a heading minus the width of nothing, which is not a
                # frame at all -- and using that number left two sections 12
                # and 14 px short of what they needed.
                if body.isHidden():
                    body.setVisible(True)
                    if body.layout() is not None:
                        body.layout().invalidate()
                        body.layout().activate()
                    box._widest_body = body.minimumSizeHint().width()
                    box._own_frame = (box.minimumSizeHint().width()
                                      - box._widest_body)
                    body.setVisible(False)
                else:
                    box._widest_body = body.minimumSizeHint().width()
                    box._own_frame = (box.minimumSizeHint().width()
                                      - box._widest_body)
        finally:
            column.setUpdatesEnabled(True)

        def inside_of(box):
            body = getattr(box, "body", None)
            if body is None:
                return box.minimumSizeHint().width()
            return max(getattr(box, "_widest_body", 0),
                       body.minimumSizeHint().width())

        # ONE FRAME ALLOWANCE FOR EVERY GROUP, and it is deliberately the
        # widest of them.
        #
        # PER-GROUP WAS TRIED AND TAKEN BACK OUT. It is arithmetically right
        # -- a long title is already paid for by the other half of `wants`,
        # so charging it to all fifteen groups wasted 140 px, and the column
        # went from 503 to 363. But narrower means every wrapped paragraph
        # needs MORE LINES, and the heights around them are settled before
        # that is known: the sentence under "Placed through" came out cut off
        # mid-word, reported from the window as "under choose an icc profile
        # the text is cut off".
        #
        # AND THE NARROWING IS NOW IN, because the fault that stopped it has
        # been found and fixed. It was never the paragraphs: the row holding
        # an open file's name was free to GROW, swallowed the group's spare
        # height, and pushed the last sentence under the frame. Capped, the
        # narrow column is clean -- audit_panel across 24 states with a chart
        # open, and audit_the_switch_changes_nothing across three content
        # states, each driven dark -> light -> dark.
        #
        # WHAT IT IS WORTH: 504 -> 358 px, and every one of those 146 pixels
        # goes to the picture, which is the thing anybody opened the window
        # for. The history below is kept because it is the reasoning, and
        # because the next person to touch this arithmetic should know what
        # it broke the first time. What is measured and
        # kept: the allowance is 80 px and comes from "Are the patches
        # inside?", a group whose TITLE is long and whose body is tiny, and
        # the column needs only 381 of the 503 it takes.
        #
        # WHAT IS NOW KNOWN, measured by rebuilding the window with the
        # per-group allowance in place and driving it:
        #
        #   * THE COLUMN REALLY DOES NARROW: 504 -> 358 px, and every wrapped
        #     paragraph re-wraps and grows taller exactly as it should.
        #   * A WRAPPED PARAGRAPH CANNOT BE CUT BY NARROWING. All eleven
        #     wrapping labels in this column are WrappedLabel, which
        #     recomputes its own minimum height from the width it actually
        #     has on every resize. Capping one at 20 px on purpose did not
        #     even produce a cut -- it put the height straight back. That is
        #     why four separate checks for a cut sentence all reported clean:
        #     they were right.
        #   * WHAT NARROWING REALLY COSTS IS SLACK. At 358 the auto-update
        #     tickbox -- "Look for a newer version when the app starts", 303
        #     px of label that cannot wrap -- is given exactly 303 px. Not
        #     clipped, and one pixel or one translation from it.
        #   * AND IT IS NOT CLEAN YET. With a chart open, at 358, audit_panel
        #     reports nine ORPHAN ⓘ in the light theme that it does not
        #     report at 504. Real or an artefact of that audit's
        #     centre-to-centre rule, it is unexplained, so the width stays.
        #
        # The saving is real and still there to collect. What it needs now is
        # that ⓘ question settled, and a floor under the slack so the width
        # does not sit on a knife edge.
        edge = 22
        for box in column.findChildren(QGroupBox):
            body = getattr(box, "body", None)
            if body is not None and getattr(box, "_fold_open", False):
                edge = max(edge, box.minimumSizeHint().width()
                           - body.minimumSizeHint().width())
        wants = []
        for box in column.findChildren(QGroupBox):
            # EACH GROUP PAYS FOR ITS OWN FRAME, not for the widest frame in
            # the column. A long TITLE is already paid for by the other half
            # of `wants` below, so charging it to all fifteen groups spent
            # 146 px on nothing.
            # ONLY WHERE THE QUESTION HAS AN ANSWER. A group's own frame is
            # the difference between what it asks for and what its contents
            # ask for -- true while it is OPEN, and meaningless once it is
            # folded, because a folded group asks for the width of its
            # HEADING and nothing else. Computed there it came out far too
            # small, and two sections were left 12 and 14 px short of what
            # they needed: caught by audit_panel with a long-named chart
            # open, which is what changes the group that dominates.
            #
            # A folded group falls back to the shared allowance, which is the
            # widest real frame in the column and cannot be too small.
            # THE FRAME THIS GROUP ACTUALLY HAS, measured above with its
            # contents shown, whether or not it happens to be folded now.
            frame = getattr(box, "_own_frame", edge)
            inside = inside_of(box)
            # THE WIDER OF THE TWO ANSWERS, because each is right about a
            # different thing: a shut group knows its heading, an open one
            # knows its contents, and taking the body's alone made the column
            # eleven pixels short -- cut through the ⓘ column on the right.
            wants.append(max(inside + max(frame, 0) + 4,
                             box.minimumSizeHint().width() + 4))
        needs = max(346, column.minimumSizeHint().width(), *(wants or (0,)))
        if needs > column.minimumWidth():
            column.setFixedWidth(needs)
        # AND EVERY PARAGRAPH IS MEASURED AGAIN, AT THE WIDTH IT ENDED UP
        # WITH. This is the other half of the cut sentence, and it is what
        # made the fault look like a property of the dark appearance.
        #
        # A WrappedLabel works its height out from the width it has, and it
        # is told to do so by its own resizeEvent. But a paragraph whose text
        # is set BEFORE the column has settled -- which is every paragraph
        # that describes a file, because the file is opened first and the
        # column is measured afterwards -- keeps the height it worked out at
        # the width it had then, and nothing resizes it again. Switching the
        # appearance re-polishes every widget, which does resize them, which
        # is why the same window was right in one appearance and wrong in the
        # other. Reported exactly that way: "comparing dark and light mode on
        # some instances there is a line of text missing in dark, while light
        # sometimes leaves too much space" -- one stale measurement, and it
        # errs in both directions depending on which way the width moved.
        #
        # Asked here because here is where the width stops moving: this runs
        # once as the window comes up, and again after every appearance
        # change, which are the two moments the answer can go stale.
        for paragraph in column.findChildren(WrappedLabel):
            paragraph._refit()
        gutter = area.verticalScrollBar().sizeHint().width()
        wide = needs + gutter + 2 * area.frameWidth()
        if wide > area.width():
            area.setFixedWidth(wide)

    def showEvent(self, event) -> None:            # noqa: N802 (Qt naming)
        """Centre the window the first time it is shown, and never again.

        Doing it in __init__ centred a size the window did not end up being:
        the controls are built afterwards, the window grows to fit them, and
        it drifts down and to the right by half of whatever it gained.

        The screen used is the one the window is actually on, not the primary
        one. With two displays those are often different, and centring on the
        wrong one is what puts a window in a corner.
        """
        super().showEvent(event)
        # The stylesheet lands at polish, which is after the names were first
        # measured. Measure them again now they are wearing it.
        self._align_names()
        self._ask_the_layouts_again()
        # AND THE CAMERA IS WATCHED FROM HERE ON. It lives in the browser and
        # moves when somebody drags the shape; nothing tells this side of the
        # window that it has, so it is asked. Every page written from now on
        # opens where the reader is looking instead of snapping back.
        #
        # A POLL, AND NOT A ONE-OFF READ BEFORE WRITING, because runJavaScript
        # answers later: a page written in the same breath would be written
        # with the answer to the question before it.
        if getattr(self, "_camera_watch", None) is None:
            self._camera_watch = QTimer(self)
            self._camera_watch.setInterval(400)
            self._camera_watch.timeout.connect(self._watch_the_camera)
            self._camera_watch.start()
        if self._placed:
            return
        self._placed = True
        # Re-apply now the window is actually up: a setVisible(False) issued
        # while the parent was still hidden does not survive the parent being
        # shown, so the controls that depend on what is loaded have to be
        # settled here as well as during construction.
        self._apply_side_by_side_availability()
        self._apply_flat_availability()
        # …and the folded groups, for exactly the same reason.
        for box in self.findChildren(QGroupBox):
            refold = getattr(box, "_refold", None)
            if refold is not None:
                refold()
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        room = screen.availableGeometry()
        # Never larger than the screen it is on, with a margin so the frame
        # stays grabbable, and never smaller than the window can actually be.
        width = max(self.minimumWidth(), min(self.width(), room.width() - 40))
        height = max(self.minimumHeight(), min(self.height(), room.height() - 60))
        if (width, height) != (self.width(), self.height()):
            self.resize(width, height)
        frame = self.frameGeometry()
        frame.moveCenter(room.center())
        # If the frame is taller than the screen, centring would push its
        # title bar off the top where it cannot be grabbed. Keep it inside.
        frame.moveTop(max(room.top(), frame.top()))
        frame.moveLeft(max(room.left(), frame.left()))
        self.move(frame.topLeft())

    def _pair_icon(self, name: str, control) -> None:
        """Put the ⓘ called *name* on the same row as *control*.

        Used for the handful of explanations that describe a whole group: the
        generic pass cannot guess which control such a hint belongs to, but a
        person can, so those are named. The icon is taken out of wherever it
        currently sits and inserted beside the control at the control's own
        place in its layout, so the row order does not change.
        """
        icon = self.findChild(Hint, name)
        if icon is None or control is None:
            return
        here = icon.parentWidget().layout() if icon.parentWidget() else None
        for layout in self._layouts_of(here):
            index = layout.indexOf(icon)
            if index >= 0:
                layout.takeAt(index)
                break
        holder = control.parentWidget()
        target = holder.layout() if holder is not None else None
        for layout in self._layouts_of(target):
            index = layout.indexOf(control)
            if index < 0:
                continue
            if isinstance(layout, QGridLayout):
                # A grid has no insertLayout; put the icon in the cell beside
                # the control instead, which is the same result.
                row_i, col_i, span_r, span_c = layout.getItemPosition(index)
                layout.addWidget(icon, row_i, col_i + span_c,
                                 1, 1, Qt.AlignmentFlag.AlignVCenter)
            else:
                layout.takeAt(index)
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(6)
                row.addWidget(control, 1)
                row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
                layout.insertLayout(index, row)
            icon.follow(control)
            return
        # The control is nested somewhere unexpected; leave the icon where it
        # is rather than dropping it out of the window entirely.
        icon.setParent(control.parentWidget())
        icon.show()

    @staticmethod
    def _layouts_of(layout):
        """*layout* and every layout nested inside it, depth first."""
        if layout is None:
            return
        yield layout
        for i in range(layout.count()):
            child = layout.itemAt(i)
            if child is not None and child.layout() is not None:
                yield from GamutApp._layouts_of(child.layout())

    def _shorten_the_hovers(self, root) -> None:
        """No hover tooltip longer than a couple of lines, anywhere.

        THE RULE, IN BASTI'S WORDS: "some tooltips from hovering extend very
        far. those hover tooltips should be short and the extended version
        would be behind the tooltip icons." Measured before this ran: 31 of
        the column's 54 tooltips were over 300 characters and the longest was
        2,139 -- a wall of text wider than the screen, covering the very
        control it was describing.

        THE LONG VERSION IS NEVER THROWN AWAY. A control that already has an ⓘ
        beside it keeps its words there. A control that has none is GIVEN one,
        carrying exactly the text its tooltip used to have, tied to its
        visibility so it leaves when the control does. That is the window's
        own idiom everywhere else, and it is what makes shortening the hover
        safe rather than lossy.
        """
        from PyQt6.QtWidgets import QAbstractButton, QComboBox, QSlider

        if root is None:
            return
        holder = root.widget() if hasattr(root, "widget") else root
        if holder is None:
            return
        for control in holder.findChildren((QAbstractButton, QComboBox,
                                            QSlider)):
            if isinstance(control, Hint):
                continue
            tip = control.toolTip().strip()
            if len(tip) <= _HOVER_LIMIT:
                continue
            if self._icon_beside(control) is None:
                spot = self._row_of(control)
                if spot is None:
                    # NOWHERE TO PUT AN ICON IS A REASON TO LEAVE THE WORDS
                    # ALONE. A long tooltip is a poor thing; a shortened one
                    # whose full text now lives nowhere at all is worse.
                    continue
                row, at, sideways = spot
                if not sideways:
                    # A CONTROL STACKED IN A COLUMN GETS NO ICON, and both
                    # ways of giving it one were tried and measured.
                    #
                    # Dropped into the column itself, the icon lands UNDER the
                    # button rather than beside it -- the panel audit's own
                    # definition of an orphan, and it reported exactly that.
                    # Given a row of its own beside the button, the row then
                    # asks for the button's full label PLUS the icon, and the
                    # panel overflowed its column by 11 px at 760 -- which is
                    # the fault this whole audit exists to prevent.
                    #
                    # So the words are shortened and the long version is not
                    # rehoused. These are buttons whose labels already say
                    # what they do ("Remove them all"), and the section they
                    # sit in carries an ⓘ of its own.
                    control.setToolTip(_one_sentence(tip))
                    continue
                # THE ICON IS NOT MADE UNTIL THERE IS SOMEWHERE TO PUT IT.
                # Built first and thrown away second, it existed for a moment
                # as a child of the panel with no place in any layout -- which
                # is a widget drawn at the top left corner of its parent, over
                # whatever is there. That is what a stray ⓘ sitting on the
                # list of profiles was.
                icon = Hint(tip, control.parentWidget(),
                            title="About this setting")
                icon.setObjectName("hint_from_tooltip")
                row.insertWidget(at + 1, icon, 0,
                                 Qt.AlignmentFlag.AlignVCenter)
                icon.follow(control)
            control.setToolTip(_one_sentence(tip))

    def _icon_beside(self, control):
        """The ⓘ in this control's own row, if it has one.

        ASKED OF THE LAYOUT, NOT OF THE PIXELS. The first version compared
        the two widgets' centres, which is the right question at the wrong
        moment: this runs while the window is still being built, every widget
        is at y=0, and so every icon looked as though it were beside every
        control. The effect was silent and exactly backwards -- the sweep
        believed each control already had an explanation and added none.
        """
        spot = self._row_of(control)
        if spot is None or not spot[2]:
            return None
        row = spot[0]
        for i in range(row.count()):
            found = row.itemAt(i).widget()
            if isinstance(found, Hint):
                return found
        return None

    def _row_of(self, control):
        """(the layout holding this control, its place, does it run across).

        THE CLASS IS NOT THE DIRECTION, and taking one for the other is what
        produced the orphan. The run panel's rows are QHBoxLayouts turned
        vertical -- _stack calls setDirection on them rather than building
        new ones -- so a check of `isinstance(..., QHBoxLayout)` says "this
        runs across" about a layout that plainly runs down.
        """
        from PyQt6.QtWidgets import QBoxLayout

        parent = control.parentWidget()
        if parent is None:
            return None
        holder = getattr(parent, "body", parent)
        across = (QBoxLayout.Direction.LeftToRight,
                  QBoxLayout.Direction.RightToLeft)
        for layout in self._layouts_of_window(holder):
            if not isinstance(layout, QBoxLayout):
                continue
            for i in range(layout.count()):
                if layout.itemAt(i).widget() is control:
                    return layout, i, layout.direction() in across
        return None

    def _lend_the_hint_words_to_the_control(self, root) -> None:
        """A control beside an ⓘ answers for itself when it is hovered too.

        THE ⓘ IS NOT THE FIRST PLACE ANYBODY LOOKS. Hovering the thing itself
        is, and eight buttons at the foot of the column answered that with
        silence -- "some of the buttons at the bottom of the left sections
        have no tooltip". Every one of them had a full explanation sitting an
        inch to its right, behind an icon.

        THE SAME WORDS, NOT A SECOND SET. Copying each explanation into a
        shorter tooltip would make two texts about one control that nobody
        would ever remember to keep in step -- and this file has been bitten
        by exactly that, three times, by lists that had to be updated by hand.
        So the control borrows the icon's own text.

        ONLY WHERE THERE IS NOTHING ALREADY: a control that explains itself
        keeps its own words, which are usually shorter and better aimed.
        """
        from PyQt6.QtWidgets import QAbstractButton

        for row in self._layouts_of_window(root):
            items = [row.itemAt(i).widget() for i in range(row.count())]
            icons = [w for w in items if isinstance(w, Hint)]
            others = [w for w in items
                      if w is not None and not isinstance(w, Hint)]
            if len(icons) != 1 or len(others) != 1:
                continue
            control = others[0]
            if not isinstance(control, QAbstractButton):
                continue
            # AND A LONG TOOLTIP THE CONTROL ALREADY HAD IS SHORTENED, not
            # left alone: the rule is about what a hover shows, not about
            # where the words came from. The full text is behind the icon
            # beside it either way.
            mine = control.toolTip().strip()
            if mine and len(mine) <= _HOVER_LIMIT:
                continue
            control.setToolTip(_one_sentence(mine)
                               if mine else icons[0].in_a_sentence())

    @staticmethod
    def _layouts_of_window(root):
        """Every layout under *root*, rows and columns alike."""
        from PyQt6.QtWidgets import QLayout

        seen = []

        def walk(layout):
            if layout is None:
                return
            seen.append(layout)
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.layout() is not None:
                    walk(item.layout())
                elif item.widget() is not None:
                    holder = getattr(item.widget(), "body", item.widget())
                    if holder.layout() is not None:
                        walk(holder.layout())

        # THE SCROLL AREA HOLDS THE COLUMN; IT IS NOT THE COLUMN. Asked for
        # its own layout it answers None, and the first version of this walked
        # nothing at all and reported success -- five buttons stayed silent
        # while the pass said it had run.
        from PyQt6.QtWidgets import QScrollArea

        if isinstance(root, QScrollArea):
            root = root.widget()
        if root is not None:
            holder = getattr(root, "body", root)
            walk(holder.layout() if hasattr(holder, "layout") else None)
        return seen

    def _attach_hint_icons(self, root) -> None:
        """Move any ⓘ that ended up on a row of its own onto the row above.

        An explanation has to point at the thing it explains. A help icon
        floating on its own line reads as belonging to nothing -- and several
        in a row read as a column of decorations.

        Rather than restructure every place a hint is added, the layouts are
        walked once after they are built, nested ones included: any Hint
        sitting alone as a row is lifted out and put at the end of the row
        above it. Anything it cannot sensibly point at is stepped over -- a
        readout that hides itself when empty, or a group heading -- because
        attaching to one of those leaves the icon beside an invisible partner,
        which looks exactly like being alone.

        Each icon is then tied to the visibility of what it explains, so a
        control that is hidden takes its ⓘ with it.
        """
        if root is None:
            return
        # AND IT KEEPS OUT OF THE RUN PANEL. Every ⓘ in there was placed
        # beside the thing it explains when that panel was a window, and this
        # pass -- which pairs an icon with whatever widget is above it --
        # re-pairs them by a rule that does not know about a readout which
        # hides itself when empty. Driven with four profiles open, it left an
        # icon alone in the middle of the readouts with nothing beside it.
        panel = getattr(self, "_timeline", None)
        if panel is not None:
            for icon in panel.findChildren(Hint):
                icon.setProperty("placed_by_hand", True)
        for box in root.findChildren(QGroupBox):
            # THE FOLD MOVES A GROUP'S LAYOUT ONTO A BODY WIDGET, so asking
            # the group for its layout now answers "one item: the body", and
            # this pass would walk past every ⓘ in the window without a word.
            holder = getattr(box, "body", box)
            if holder.layout() is not None:
                self._attach_in_layout(holder.layout(), box)

    def _attach_in_layout(self, layout, box) -> None:
        """One layout, and every layout nested inside it.

        A GRID IS LEFT ALONE. This exists to pair an ⓘ with the control above
        it in a column of stacked widgets, where nothing says which belongs to
        which. In a grid every hint has already been put in its own column
        beside its own control on purpose, so there is nothing to work out —
        and trying to rearrange one asks a grid for a method only a box layout
        has.
        """
        if isinstance(layout, QGridLayout):
            return
        i = 0
        while i < layout.count():
            item = layout.itemAt(i)
            if item is None:
                i += 1
                continue
            if item.layout() is not None:
                self._attach_in_layout(item.layout(), box)
                i += 1
                continue
            hint = item.widget()
            if isinstance(hint, Hint) and hint.property("placed_by_hand"):
                i += 1
                continue
            if not isinstance(hint, Hint) or i == 0:
                i += 1
                continue
            j = i - 1
            while j >= 0:
                candidate = layout.itemAt(j)
                widget = candidate.widget()
                if candidate.layout() is not None:
                    break
                # HIDDEN IS NOT THE SAME AS ABSENT, and treating it as the
                # same is what put four icons on one row. This pass runs
                # while the window is being built, when every control that
                # depends on a file being open is hidden -- so each of their
                # icons walked past its own partner and landed on the last
                # row that happened to be showing. Basti photographed the
                # result: "…and a perfectly neutral line" with four ⓘ beside
                # it, and three controls below it with none.
                #
                # An icon belongs to the control it was written for, whether
                # or not that control is on screen at this instant; going
                # with it when it appears and disappears is what follow() is
                # for.
                if widget is not None:
                    # A heading is not something an icon can point at; a
                    # readout showing a number is.
                    if not (isinstance(widget, QLabel)
                            and widget.objectName() not in ("volume", "hint")):
                        break
                j -= 1
            if j < 0:
                i += 1
                continue
            above = layout.itemAt(j)
            layout.takeAt(i)
            if above.layout() is not None:
                above.layout().addWidget(hint, 0,
                                         Qt.AlignmentFlag.AlignVCenter)
                hint.follow(self._first_widget_in(above.layout()))
            else:
                control = above.widget()
                layout.takeAt(j)
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(6)
                row.addWidget(control, 1)
                row.addWidget(hint, 0, Qt.AlignmentFlag.AlignVCenter)
                layout.insertLayout(j, row)
                hint.follow(control)

    @staticmethod
    def _first_widget_in(layout):
        """The first real widget in a row, which is what that row is about."""
        for k in range(layout.count()):
            widget = layout.itemAt(k).widget()
            if widget is not None and not isinstance(widget, Hint):
                return widget
        return None

    def _persisted(self):
        """Every control worth remembering, as (key, widget, kind, default).

        One table rather than a save call sprinkled through twenty handlers:
        a control added to the window and forgotten here would silently stop
        being remembered, and nobody would notice until they restarted.
        """
        return (
            ("opacity", self._opacity, "slider", 100),
            ("depth", self._depth, "slider", 35),
            ("detail", self._detail, "slider", 20),
            ("slice_at", self._slice_at, "slider", 50),
            ("slice_on", self._slice_on, "check", False),
            ("points", self._points, "check", False),
            ("show_lost", self._show_lost, "check", False),
            ("lost_in_colour", self._lost_in_colour, "check", False),
            ("agree", self._agree, "slider", 100),
            ("differ", self._differ, "slider", 100),
            ("relative", self._relative, "check", False),
            ("manual_light", self._manual_light, "check", False),
            # How the chart's patches are drawn. Remembered like every other
            # look setting, so a chart opened tomorrow appears the way it was
            # left rather than back at the defaults.
            ("chart_dot", self._chart_dot, "slider", 32),
            ("chart_dot_opacity", self._chart_dot_opacity, "slider", 100),
            ("chart_out_dot", self._chart_out_dot, "slider", 55),
            ("chart_out_opacity", self._chart_out_opacity, "slider", 100),
            ("chart_show_outside", self._chart_show_outside, "check", True),
            ("chart_skin", self._chart_skin, "combo", "none"),
            ("chart_skin_colour", self._chart_skin_colour, "combo", "grey"),
            ("chart_skin_opacity", self._chart_skin_opacity, "slider", 30),
            ("outline_paint", self._outline_paint, "combo", "plain"),
            ("drift_by", self._drift_by, "combo", None),
            ("rings_on", self._rings_on, "check", False),
            ("neutral", self._neutral, "check", False),
            ("ideal_neutral", self._ideal_neutral, "check", False),
            ("spin_on", self._spin_on, "check", False),
            ("turn_mode", self._turn_mode, "combo", "swing"),
            ("turn_speed", self._turn_speed, "slider", 8),
            ("turn_sweep", self._turn_sweep, "slider", 60),
            ("tilt_mode", self._tilt_mode, "combo", "off"),
            ("tilt_speed", self._tilt_speed, "slider", 6),
            ("tilt_sweep", self._tilt_sweep, "slider", 40),
            ("grid_on", self._grid_on, "check", True),
            ("side_by_side", self._side_by_side, "check", False),
            ("link_cameras", self._link_cameras, "check", True),
            ("auto_update", self._auto_update, "check", True),
            ("rings", self._rings, "slider", 6),
            ("aspect", self._aspect, "combo", "data"),
            ("white", self._white, "combo", "D50"),
            ("space", self._space, "combo", "lab"),
            ("shape_mode", self._mode, "combo", "device"),
            ("style_first", self._style_mine, "combo", "solid"),
            ("style_second", self._style_second, "combo", "mesh"),
            ("style_other", self._style_other, "combo", "mesh"),
        ) + tuple(
            (f"light_{key}", self._light_sliders[key][0], "slider",
             int(round((start - lo) / (hi - lo) * 100)))
            for key, _label, lo, hi, start in LIGHT_CONTROLS
        ) + tuple(
            # Whether each explanation is folded open. Found rather than
            # listed, so a hint added to the window is remembered without
            # anybody having to remember to add it here as well. Every one
            # defaults to False: folded, which is what a second visit wants.
            (h.objectName(), h, "check", False)
            for h in self.findChildren(Hint) if h.objectName())

    def _remember_everything(self) -> None:
        """Write the current state of every remembered control."""
        for key, widget, kind, _default in self._persisted():
            if kind == "slider":
                self._store.setValue(key, widget.value())
            elif kind == "check":
                self._store.setValue(key, widget.isChecked())
            else:
                self._store.setValue(key, widget.currentData())
        self._store.setValue("appearance", self._appearance)
        self._store.setValue("scheme", self._scheme)
        self._store.setValue("paint", self._paint)
        # Per-shape overrides as JSON: a nested dictionary is not something a
        # settings store keeps faithfully on every platform, and one string
        # that either parses or does not is easier to reason about than three
        # half-restored dictionaries.
        self._store.setValue(
            "per_shape",
            json.dumps({str(k): v for k, v in self._per_shape.items()}))
        self._store.setValue("target", self._target.currentData())
        self._store.setValue("shared", json.dumps(self._shared))

    def _restore_everything(self) -> None:
        """Put every remembered control back where it was left.

        Signals are blocked while restoring so that setting fifteen controls
        does not trigger fifteen redraws of a window that has nothing in it
        yet; one redraw happens when a chart is opened.
        """
        for key, widget, kind, default in self._persisted():
            raw = self._store.value(key, default)
            widget.blockSignals(True)
            try:
                if kind == "slider":
                    widget.setValue(int(raw))
                elif kind == "check":
                    widget.setChecked(raw in (True, "true", "True", 1, "1"))
                else:
                    index = widget.findData(raw)
                    if index >= 0:
                        widget.setCurrentIndex(index)
            except (TypeError, ValueError):
                pass          # a stored value we cannot use: keep the default
            finally:
                widget.blockSignals(False)
        raw = self._store.value("per_shape", "")
        if raw:
            try:
                stored = json.loads(raw)
                self._per_shape = {int(k): dict(v) for k, v in stored.items()}
                for i in (0, 1, 2):
                    self._per_shape.setdefault(i, {})
            except (ValueError, TypeError, AttributeError):
                self._per_shape = {0: {}, 1: {}, 2: {}}   # unreadable: start clean
        shared_raw = self._store.value("shared", "")
        if shared_raw:
            try:
                self._shared.update(json.loads(shared_raw))
            except (ValueError, TypeError):
                pass                       # unreadable: keep the defaults
        index = self._target.findData(self._store.value("target", "all"))
        if index >= 0:
            self._target.blockSignals(True)
            self._target.setCurrentIndex(index)
            self._target.blockSignals(False)
        self._carry_over_the_old_outline_tick()
        # AND THE TWO COPIES ARE MADE TO AGREE BEFORE ANYTHING IS DRAWN.
        #
        # A shape setting is kept twice: as the slider's own value, and inside
        # the record the renderer reads. They are restored from two different
        # keys, so a window could open with the handle at 55% and the shapes
        # drawn at 100% -- reported exactly that way: "how solid it looks was
        # then at 55% although the shapes suggest to be at 100%. clicking the
        # knob and moving it corrected the viewer immediately".
        #
        # Touching the control cured it because that is when the record is
        # written. The control is the thing a person can see, so the control
        # wins: every shared value is taken from the widget that shows it.
        for key, (widget, read) in self._shape_controls().items():
            if widget is None:
                continue
            try:
                self._shared[key] = read(widget)
            except Exception:              # noqa: BLE001 — never block a start
                pass
        self._sync_slider_labels()
        self._on_manual_light()
        # AND THE CLOUD'S OWN CONTROLS MATCH THE TICK THEY DEPEND ON FROM THE
        # FIRST FRAME. Wired only to the tick's own signal, a window that
        # opens with the cloud off -- which is how it opens -- showed three
        # lit controls with nothing to act on until somebody happened to
        # touch it. Found by driving: "before the tick: coloured-by enabled =
        # True", where the whole point of the greying is that it is False.
        self._refresh_drift_controls()

    def _carry_over_the_old_outline_tick(self) -> None:
        """Bring a setting written by the version that had a tick, not a list.

        The outline's colour used to be one tick, "Colour the outlines too",
        remembered as ``mesh_colour`` = true/false and written into the shapes
        as ``mesh_paint`` = "colour"/"plain". Somebody who had ticked it must
        find the outlines still coloured after updating, not quietly back to
        grey -- a setting that resets itself is worse than one that never
        existed, because the picture changed and nothing said so.

        Nothing is thrown away: the old key is left in the store, so going
        back to the previous version finds it exactly as it was.
        """
        if self._store.value("outline_paint", None) is None:
            was = self._store.value("mesh_colour", None)
            if was is not None:
                ticked = was in (True, "true", "True", 1, "1")
                at = self._outline_paint.findData("match" if ticked else "plain")
                if at >= 0:
                    self._outline_paint.blockSignals(True)
                    self._outline_paint.setCurrentIndex(at)
                    self._outline_paint.blockSignals(False)
        # And the same word wherever it was written against a shape.
        if self._shared.get("mesh_paint") == "colour":
            self._shared["mesh_paint"] = "match"
        for own in self._per_shape.values():
            if own.get("mesh_paint") == "colour":
                own["mesh_paint"] = "match"

    def _sync_slider_labels(self) -> None:
        """Every label that mirrors a slider, told what its slider now says."""
        self._opacity_lbl.setText(f"{self._opacity.value()}%")
        self._depth_lbl.setText(f"{self._depth.value()}%")
        self._detail_lbl.setText(f"{self._detail.value()} steps")
        self._slice_lbl.setText(f"L* {self._slice_at.value()}")
        self._rings_lbl.setText(str(self._rings.value()))
        # THE SAME WORDING THE SLIDER ITSELF USES while being dragged, or a
        # reset would leave the label reading "40%" beside a slider back at
        # the top. Both routes into this window's stored settings come
        # through here, which is why it is the only place it belongs.
        for _slider, _label in ((self._agree, self._agree_lbl),
                                (self._differ, self._differ_lbl)):
            _v = _slider.value()
            _label.setText("all of it" if _v == 100
                           else ("hidden" if _v == 0 else f"{_v}%"))

    def _reset_defaults(self) -> None:
        """Put every setting back to its starting value, after asking."""
        if not Notice.ask(
                self, "Start again with the standard settings?",
                "Every setting in this window goes back to how it started: "
                "the appearance, the accent colour, how the shapes are drawn "
                "and coloured, the lighting, and everything else. Any shape "
                "you set on its own goes back to following the shared "
                "settings.\n\n"
                "The charts you have open stay open, and no file of yours is "
                "touched.",
                ok="Reset the settings", cancel="Keep my settings"):
            return
        for key, widget, kind, default in self._persisted():
            widget.blockSignals(True)
            if kind == "slider":
                widget.setValue(int(default))
            elif kind == "check":
                widget.setChecked(bool(default))
            else:
                index = widget.findData(default)
                if index >= 0:
                    widget.setCurrentIndex(index)
            widget.blockSignals(False)
        self._appearance, self._scheme, self._paint = "dark", "Magenta", "true"
        self._apply_space_availability()
        self._per_shape = {0: {}, 1: {}, 2: {}}    # every shape shares again
        self._shared = dict(opacity=1.0, depth=0.35, rings=0,
                            mesh_paint="plain", paint="true")
        self._target.blockSignals(True)
        self._target.setCurrentIndex(0)
        self._target.blockSignals(False)
        # Write the fresh values out BEFORE anything reads them back. Restoring
        # first re-read the store, which still held what was being reset, so
        # the sliders quietly went back to where they had just been moved from.
        self._remember_everything()
        self._sync_slider_labels()
        self._on_manual_light()
        self._apply_mode()
        if self._slots:
            self._redraw()

    #: Settings the picture on screen can be restyled into without being
    #: written again. Letting go of these must NOT rebuild: the change is
    #: already on screen, and the rebuild's only visible effect is the pause
    #: and the jump that follow it -- "i drag let go it settles and after a
    #: few seconds it jumps".
    RESTYLED_IN_PLACE = ("opacity", "depth")

    def _after_shape_setting(self, key: str) -> None:
        """Record a per-shape (or shared) value, and repaint if it needs it."""
        self._remember_shape_setting(key)
        if key in self.RESTYLED_IN_PLACE:
            # RECORDED AND NOT REDRAWN. The value still has to be written down
            # -- every future rebuild reads it from there -- but the picture
            # was changed under the hand and rebuilding it would only take it
            # away and put it back.
            return
        # THE RINGS ARE THE SAME, WHEN THE PUSH LANDED. They are pushed live
        # while the handle moves, so rebuilding on release would take the
        # picture away and put back exactly what is there. But a restyle can
        # only reach a trace that EXISTS -- rings drawn as none at build time
        # have no trace to change -- so the page is asked whether it managed,
        # and a no falls through to the redraw that always worked.
        if key == "rings" and getattr(self, "_rings_live", False):
            return
        # AND WHATEVER THE PUSH DID, A VALUE THAT HAS NOT MOVED SINCE THE
        # PICTURE WAS DRAWN NEEDS NO PICTURE. Letting go of the rings slider
        # without moving it rebuilt the page every time, because no movement
        # means no push, and no push means `_rings_live` is False.
        if key in getattr(self, "_drawn_with", {}):
            control = {"rings": self._rings, "detail": self._detail}.get(key)
            if control is not None and control.value() == self._drawn_with[key]:
                return
        self._redraw()

    def _set_paint(self, which: str) -> None:
        """Change how the shapes themselves are coloured, and remember it."""
        if which == self._paint:
            return
        self._paint = which
        self._store.setValue("paint", which)
        self._remember_shape_setting("paint")
        if self._slots:
            self._redraw()

    def _recolour_hints(self) -> None:
        """Repaint every ⓘ in the accent.

        The icons are DRAWN, not styled, so the stylesheet that carries the
        accent everywhere else goes straight past them: re-applying it left
        thirty-five of them in the colour they were built with. Anything this
        window paints itself has to be told separately, which is the same trap
        the scroll fade and the chevron are in.
        """
        accent = SCHEMES.get(self._scheme, SCHEMES["Magenta"])["accent"]
        for icon in self.findChildren(Hint):
            icon.set_colour(accent)

    def _set_scheme(self, which: str) -> None:
        """Change the accent colour, and remember it for next time."""
        if which == self._scheme or which not in SCHEMES:
            return
        self._scheme = which
        self._store.setValue("scheme", which)
        # The bar is built FROM the accent, so it is rebuilt when the accent
        # changes -- otherwise a new accent leaves the old bar behind.
        self._apply_mode()

    def _apply_mode(self) -> None:
        """Repaint the whole window, and say what the button will do next.

        The button names the mode it will switch TO, not the one you are in:
        a button that says "Dark" while the window is already dark reads as a
        statement rather than an action.
        """
        app = QApplication.instance()
        if app is not None:
            arrow = chevron_png(
                self._tmp / f"chevron-{self._appearance}.png",
                PALETTES[self._appearance]["dim"],
                self.devicePixelRatioF() or 1.0)
            app.setStyleSheet(stylesheet(self._appearance, self._scheme,
                                         arrow.replace("\\", "/")))
        radio = (self._theme_light if self._appearance == "light"
                 else self._theme_dark)
        if not radio.isChecked():
            radio.blockSignals(True)
            radio.setChecked(True)
            radio.blockSignals(False)
        painted = self._paint_radios.get(self._paint)
        if painted is not None and not painted.isChecked():
            painted.blockSignals(True)
            painted.setChecked(True)
            painted.blockSignals(False)
        chosen = self._scheme_radios.get(self._scheme)
        if chosen is not None and not chosen.isChecked():
            chosen.blockSignals(True)
            chosen.setChecked(True)
            chosen.blockSignals(False)
        # The viewer fill, not the window fill: the page inside it paints
        # itself this colour too (SCENE_COLOURS), so matching them means no
        # seam shows at the edge of the scene while a page is loading.
        area = self.findChild(FadeScrollArea)
        if area is not None:
            area.set_colour(PALETTES[self._appearance]["bg"])
        self._recolour_hints()
        colour = PALETTES[self._appearance]["plot_bg"]
        self._view.setStyleSheet(f"background: {colour};")
        page = self._view.page()
        if page is not None:
            page.setBackgroundColor(QColor(colour))
        self._frame.setStyleSheet(
            f"border: 1px solid {PALETTES[self._appearance]['line']};"
            f"border-radius: 8px; background: {colour};")
        if not self._slots:
            self._show_placeholder()

    def _on_export(self) -> None:
        """Write what is on screen as a table, for a report or a spreadsheet.

        A picture is convincing and a number is quotable. This writes both
        halves of what the window says — the volumes, the coverage in each
        direction, the grey drift, and the drift between two readings — as
        comma-separated text that opens in any spreadsheet.
        """
        if not self._slots and self._chart is None:
            return
        first = self._slots[0][0] if self._slots else self._chart[0]
        default = first.with_name(first.stem + "-gamut.csv")
        dlg = self._file_dialog("Save the numbers as a table",
                                QFileDialog.FileMode.AnyFile,
                                "Comma-separated values (*.csv)", str(default),
                                profiles=False)
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dlg.setDefaultSuffix("csv")
        _style_dialog_toolbar(dlg, PALETTES[self._appearance]["arrow"])
        if not dlg.exec():
            return
        target = Path(dlg.selectedFiles()[0])
        rows = [("what", "value", "units or note")]
        ref = "the paper's own white" if self._relative.isChecked() else (
            f"{self._white.currentData()} absolute")
        rows.append(("measured against", ref, ""))
        rows.append(("drawn in", self._space.currentText(),
                     self._volume_units()))
        for path, g, m in self._slots:
            if m is None:
                rows.append((f"{path.stem}: kind", "ICC profile",
                             "described, not measured"))
            else:
                rows.append((f"{path.stem}: patches", m.n_patches, m.instrument))
            rows.append((f"{path.stem}: colour held", self._fmt_volume(g.volume),
                         self._volume_units()))
            if m is None:
                continue
            lab, _labels = neutral_axis(m)
            if len(lab):
                cast = float(np.hypot(lab[:, 1], lab[:, 2]).max())
                rows.append((f"{path.stem}: greys", len(lab),
                             f"worst colour cast {cast:.1f}"))
        if self._reference is not None:
            name, g = self._reference
            rows.append((f"{name}: colour held", self._fmt_volume(g.volume),
                         self._volume_units()))
        pair = None
        if self._reference is not None and self._slots:
            pair = ((self._slots[0][0].stem, self._slots[0][1]),
                    self._reference)
        elif len(self._slots) == 2:
            pair = ((self._slots[0][0].stem, self._slots[0][1]),
                    (self._slots[1][0].stem, self._slots[1][1]))
        if pair is not None:
            (an, a), (bn, b) = pair
            try:
                ab, ab_err = coverage(a, b)
                ba, ba_err = coverage(b, a)
                rows.append((f"{an} inside {bn}", f"{100 * ab:.1f}",
                             f"per cent, +/- {100 * ab_err:.1f}"))
                rows.append((f"{bn} inside {an}", f"{100 * ba:.1f}",
                             f"per cent, +/- {100 * ba_err:.1f}"))
            except Exception:      # noqa: BLE001 — a table must still be written
                pass
        if len(self._slots) == 2 and all(x[2] is not None for x in self._slots):
            try:
                d = compare_measurements(self._slots[0][2], self._slots[1][2])
                rows.append(("patches in both readings", d.matched, ""))
                rows.append(("biggest difference", f"{d.worst:.2f}", "dE2000"))
                rows.append(("average difference", f"{d.average:.2f}", "dE2000"))
                rows.append(("patches above 1", d.over_one, "dE2000"))
            except ValueError:
                pass               # not two readings of one chart; say nothing
        rows.extend(self._profile_drift_rows())
        rows.extend(self._chart_rows_for_export())
        try:
            with open(target, "w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerows(rows)
        except OSError as exc:
            Notice.warn(self, "That could not be saved", str(exc))
            return
        Notice.say(
            self, "Saved",
            f"Written to\n{target}\n\nIt opens in any spreadsheet, and every "
            "row says what it is and what the units are.")

    def _drift_cut_changed(self, _value=None) -> None:
        """Hide the colours that barely moved — under the hand, not after it.

        THE SAME CONTROL THE TIMELINE HAS, and it was the only one of the two
        still rebuilding the page on every step: the view went black and came
        back on each notch instead of thinning out as it moved. See
        TimelineDialog._cut_changed for the reasoning and for where the
        working half of this lives (window.cqHideBelow, handed out by the page
        that carries a drift cloud).

        AND IT PUTS ITSELF RIGHT WHEN THE PAGE CANNOT DO IT. A picture with no
        drift cloud in it has no such function, and a slider that silently did
        nothing there would be worse than one that rebuilds: the answer comes
        back from the page, and a "no" falls through to the redraw that always
        worked.
        """
        self._drift_cut_says.setText(self._drift_cut_reads())
        page = self._view.page() if self._view is not None else None
        if page is None:
            self._redraw()
            return

        def fell_back(did_it):
            if not did_it:
                self._redraw()

        page.runJavaScript(
            "(function(){if(window.cqHideBelow){window.cqHideBelow("
            f"{self._drift_cut.value() / 10.0:.2f});return true;}}"
            "return false;})();", fell_back)

    def _drift_cut_reads(self) -> str:
        """The same words as the timeline's, and see _cut_reads for why."""
        if not self._drift_hiding():
            return "nothing hidden"
        return f"ΔE {self._drift_cut.value() / 10:.1f}"

    def _drift_hiding(self) -> bool:
        return (self._drift_cut.isEnabled()
                and self._drift_cut.value() > self._drift_cut.minimum())

    def _fit_drift_cut(self, deltas) -> None:
        """Span only this pair, at both ends. Same rule as the timeline's.

        A fixed 0..5 would be mostly inert on a close pair, and a slider that
        starts below the smallest difference spends its first stretch
        announcing an action it is not performing.
        """
        import numpy as _np

        deltas = _np.asarray(deltas, float)
        lo = int(float(deltas.min()) * 10)
        hi = int(float(deltas.max()) * 10)
        usable = hi > lo
        for part in (self._drift_cut, self._drift_cut_label,
                     self._drift_cut_says):
            part.setEnabled(usable)
        self._drift_cut.blockSignals(True)
        self._drift_cut.setMinimum(lo)
        self._drift_cut.setMaximum(max(hi, lo + 1))
        if self._drift_cut.value() < lo:
            self._drift_cut.setValue(lo)
        self._drift_cut.blockSignals(False)
        self._drift_cut_says.setText(
            self._drift_cut_reads() if usable else "nothing to hide")

    def _drift_for_figure(self):
        """The drift cloud for the picture, or None when it does not apply.

        ASKED ON EVERY REDRAW, so it has to be cheap and it has to be silent
        about failure: a picture must still be drawn when a profile turns out
        to be unreadable, and a raise here would take the whole view down over
        a readout.

        Measured at 9 steps per channel: 729 colours in well under a tenth of
        a second, which is below the threshold at which a redraw feels slower.
        """
        if not getattr(self, "_drift_draw", None) or \
                not self._drift_draw.isChecked():
            return None
        # ONLY IN A SPACE WHERE THE POSITIONS MEAN SOMETHING. In ink amounts
        # the picture's axes are device values, and a Lab position painted
        # into that cube would put every colour in the wrong place while
        # looking perfectly plausible.
        if self._space.currentData() == "rgb":
            return None
        pair = self._profile_pair()
        if pair is None:
            return None
        from ti3gamut import compare_profiles
        try:
            d = compare_profiles(*pair, steps=self.PROFILE_GRID)
        except Exception:          # noqa: BLE001 — a readout must never crash a view
            return None
        if not d.comparable:
            # The number is meaningless when the two were read different ways,
            # and a picture of a meaningless number is worse than no picture:
            # it looks like evidence. The box says why in words.
            return None
        self._fit_drift_cut(d.deltas)
        split = self._drift_split.isChecked()
        cut = (self._drift_cut.value() / 10.0 if self._drift_hiding() else 0.0)
        axis = self._drift_colouring()
        # WHERE EACH COLOUR WENT, not merely how far. The named directions and
        # the destination family are drawn from the MOVEMENT of every point;
        # only the plain "how far" view can be drawn from the distances alone.
        # A comparison made before lab_b was kept has no movements, and asking
        # for one of these of such a pair would draw an empty cloud rather
        # than say so -- so it falls back to the distances, which are always
        # there.
        moved = getattr(d, "moved", None)
        if axis is not None and moved is None:
            axis = None
        if axis == "toward":
            return (d.lab_a, moved, "heading for", "toward", split, cut,
                    d.deltas)
        if axis is not None:
            return (d.lab_a, moved, DIRECTIONS[axis][0], axis, split, cut,
                    d.deltas)
        return (d.lab_a, d.deltas, "how far it moved", None, split, cut)

    #: Why the split is greyed out while the cloud is painted by destination.
    #: Says what to do about it and names the control to do it with, because
    #: "unavailable" on its own leaves somebody hunting for the reason.
    SPLIT_IS_THE_DESTINATIONS = (
        "Not available while the cloud is coloured by the colour it is "
        "heading for, because that already splits it — one group per family "
        "the colours are moving TOWARD, each in the colour of the place, all "
        "of them in the key.\n\n"
        "This tick splits by the family each colour IS IN, which is the other "
        "question. To get it back, set \"coloured by\" to anything else: how "
        "far it moved, or one of the three directions.")

    #: And the same sentence from the other side. The pair above has always
    #: been enforced in ONE direction -- the tick greys when the destination
    #: colouring wins -- and the reverse was never looked at, by the window or
    #: by the audit that crosses them.
    #:
    #: Measured: with the split ticked, five colourings draw TWO distinct
    #: pictures. "How far it moved", "lighter or darker", "redder or greener"
    #: and "warmer or cooler" come out byte-identical, because a cloud cut
    #: into seven named groups has no room left for a sliding scale. Only
    #: "the colour it is heading for" differs, and that one greys the tick.
    #: So four of the five sat there lit and selectable and changed nothing.
    #:
    #: The four are greyed rather than the whole box, so that the destination
    #: colouring -- the one entry that DOES act, by taking the grouping over
    #: -- stays reachable without unticking anything first.
    COLOURING_IS_THE_FAMILIES = (
        "These are greyed out while \"Split it into colour families\" is "
        "ticked, because the cloud is already drawn as seven named groups — "
        "one per family — and a sliding scale of colour has nowhere to show "
        "itself in a picture built that way.\n\n"
        "To use them, untick \"Split it into colour families\" just below.\n\n"
        "\"The colour it is heading for\" stays available: it does its own "
        "grouping, by the family each colour is moving toward, and takes over "
        "from the tick when you choose it.")

    def _refresh_drift_controls(self) -> None:
        """Grey out the three that only act on the cloud, when there is none.

        ALL THREE DEPEND ON ONE TICK. "Split it into colour families", "Hide
        anything under" and "coloured by" describe a cloud that is only drawn
        when "Show me where, in the picture" is ticked -- `_drift_for_figure`
        returns None before it reads any of them -- and until now all three
        stayed lit and inviting with nothing to act on.

        It came up while writing the tooltip for the new one: it says the box
        is greyed out until there is a cloud to paint, and a tooltip that
        promises something nothing does is worse than no tooltip. Rather than
        make the newcomer the odd one out, the two beside it were brought to
        the same rule.
        """
        drawing = bool(getattr(self, "_drift_draw", None)
                       and self._drift_draw.isChecked())
        for name in ("_drift_by", "_drift_by_label", "_drift_split",
                     "_drift_cut", "_drift_cut_label", "_drift_cut_says"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setEnabled(drawing)
        # AND ONE OF THEM CANNOT ACT WHILE ANOTHER IS SET A CERTAIN WAY.
        #
        # "Split it into colour families" groups the cloud by the family each
        # colour IS IN. "The colour it is heading for" groups it by the family
        # each colour is going TO. Two groupings of one cloud, and the
        # destination one wins -- the split is not even passed on. Crossed
        # rather than driven one at a time: six traces with the tick, six
        # without, and the tick still lit and ticked, claiming a grouping the
        # picture does not use. That is a control saying something untrue,
        # which this window has already learnt is worse than one that does
        # nothing.
        #
        # (The same crossing found a crash: the shared colour scale is built
        # from DIRECTIONS, which has no "toward" in it. See build_figure.)
        split = getattr(self, "_drift_split", None)
        if split is not None and drawing:
            by_destination = self._drift_colouring() == "toward"
            split.setEnabled(not by_destination)
            split.setToolTip(self.SPLIT_IS_THE_DESTINATIONS if by_destination
                             else self._split_tooltip)
            grey_the_scales(self._drift_by, split,
                            getattr(self, "_drift_by_tooltip", None))

    def _drift_colouring(self):
        """Which question the cloud's colours answer, or None for how far.

        Read through one method because three places need it -- the picture,
        the control's own availability, and the tests' stand-in window -- and
        because a window built before this control existed must still answer.
        """
        box = getattr(self, "_drift_by", None)
        return None if box is None else box.currentData()

    def _profile_drift_rows(self) -> list:
        """The two-profile comparison as table rows, for the spreadsheet.

        THE CAVEAT TRAVELS WITH THE NUMBERS. A row of figures in a file
        outlives the window that explained them, and somebody opening this
        next year will read "biggest difference 4.20" with nothing to say what
        it does and does not mean. So the qualification is a row of its own,
        and so is the warning when the two were not read the same way.
        """
        import icc_read
        from ti3gamut import compare_profiles

        pair = self._profile_pair()
        if pair is None:
            return []
        path_a, path_b = pair
        try:
            d = compare_profiles(path_a, path_b, steps=self.PROFILE_GRID)
        except Exception:          # noqa: BLE001 — a table must still be written
            return []
        rows = [
            ("", "", ""),
            ("comparing", path_a.name, f"against {path_b.name}"),
            ("colours asked of both", d.matched,
             f"{d.steps} steps per channel, {d.device_space}"),
            ("biggest difference", f"{d.worst:.2f}", "dE2000"),
            ("average difference", f"{d.average:.2f}", "dE2000"),
            ("difference, rms", f"{d.rms:.2f}", "dE2000"),
            ("colours above 1", d.over_one, "dE2000"),
            ("colours above 3", d.over_three, "dE2000"),
            ("read through", d.table_a, f"and {d.table_b}"),
            ("what this is", "how far apart the two PROFILES are",
             "NOT how far the device drifted — chart fade and any change in "
             "how each profile was built are in this number too"),
        ]
        if not d.comparable:
            rows.append(
                ("WARNING", "the two were not read the same way",
                 f"one through {icc_read.TABLE_NAMES[d.table_a]}, the other "
                 f"through {icc_read.TABLE_NAMES[d.table_b]} — these answer "
                 f"different questions, so the difference above is mostly "
                 f"that rather than drift"))
        lead = "moved most" if self._one_thing_over_time() else "differs most"
        for label, delta, lab_a, lab_b in d.worst_patches:
            rows.append((f"{lead}: {label}", f"{delta:.2f}",
                         "Lab {:.1f} {:.1f} {:.1f} -> {:.1f} {:.1f} {:.1f}"
                         .format(*lab_a, *lab_b)))
        return rows

    def _chart_rows_for_export(self) -> list:
        """The chart's answer as table rows — the counts, then the patches.

        THE PATCHES THEMSELVES, ONE PER LINE, because "627 are outside" is
        where the question starts rather than where it ends. The row carries
        the ink amounts in the file's own units and, when the chart is a .ti2,
        the position on the sheet — so somebody can walk to the printed page
        and look at the patch this is talking about.
        """
        import chart as chart_mod

        if self._chart is None or self._chart_placed is None:
            return []
        path, read = self._chart
        placed = self._chart_placed
        lab = self._chart_lab()
        rows = [("", "", ""),
                ("chart", path.name, f"{read.kind}, not measured"),
                ("chart: patches", read.n_patches,
                 f"{read.duplicates} repeat another"),
                ("chart: placed through", placed.profile,
                 f"{placed.intent} ({placed.tag})"),
                ("chart: ink amounts counted to", f"{read.scale:g}",
                 "as the file writes them"
                 if read.scale_certain else "assumed — the file does not say")]
        spread = chart_mod.spread(lab)
        if spread is not None:
            rows.append(("chart: widest gap", f"{spread.largest_gap:.2f}",
                         "straight-line Lab between nearest neighbours"))

        detail = []
        for name, gamut, _p, _measured in self._judging_shapes():
            try:
                report = chart_mod.outside_report(lab, gamut,
                                                  against=name)
            except Exception:      # noqa: BLE001 — a table must still be written
                continue
            rows.append((f"chart inside {name}", report.n_inside,
                         f"{report.n_edge} within {report.tolerance:g} dE2000 "
                         f"of the surface, {report.n_beyond} beyond it"))
            if report.n_beyond:
                rows.append((f"chart outside {name}: worst",
                             f"{report.worst:.2f}", "dE2000"))
            for i in np.nonzero(report.beyond)[0]:
                detail.append((
                    name, i + 1,
                    read.locations[i] if i < len(read.locations) else "",
                    *[f"{v * read.scale:.4f}" for v in read.device[i]],
                    *[f"{v:.3f}" for v in lab[i]],
                    f"{report.distance[i]:.3f}"))
        if detail:
            channels = "".join(read.channels)
            rows.append(("", "", ""))
            rows.append(("patches outside, one per line", "", ""))
            rows.append(("outside what", "patch number", "position on sheet")
                        + tuple(channels) + ("L*", "a*", "b*", "dE2000 outside"))
            rows.extend(detail)
        return rows

    def _check_updates(self, *, asked: bool) -> None:
        """Ask the releases page whether there is a newer version.

        *asked* is True when somebody pressed the button. It decides how
        talkative the answer is: a check you asked for always answers, even to
        say you are up to date, because silence after pressing a button reads
        as a fault. The unattended check at start-up only ever speaks up when
        there really is something newer — nobody wants a dialog every morning
        telling them nothing has changed.
        """
        from updates import RELEASES_PAGE, UpdateCheck

        if asked:
            self._update_btn.setEnabled(False)
            self._update_btn.setText("Checking…")

        def done(newer: bool, version: str, url: str, problem: str) -> None:
            if asked:
                self._update_btn.setEnabled(True)
                self._update_btn.setText("Check for a newer version…")
            if newer:
                Notice.say(
                    self, f"Version {version} is available",
                    f"You are running {__version__}, and {version} has been "
                    "published.\n\n"
                    "Nothing has been downloaded or changed. To update, open "
                    f"the releases page and take the file for your computer:\n"
                    f"{url}\n\n"
                    "Your settings and your measurement files are not touched "
                    "by updating.")
            elif not asked:
                return                      # up to date, unasked: stay quiet
            elif problem:
                Notice.say(self, "The check could not be made", problem)
            else:
                Notice.say(
                    self, "You are up to date",
                    f"{__version__} is the newest version published.\n\n"
                    f"You can always see what has changed at\n{RELEASES_PAGE}")

        # Held on self until it reports. A check that is garbage-collected
        # mid-request never delivers its answer, and the button stays greyed
        # out for ever.
        self._update_check = UpdateCheck(__version__, self)
        self._update_check.finished.connect(done)
        self._update_check.start()

    def _on_timeline(self) -> None:
        """Put what is already open into the run, and open the group.

        THERE IS NO WINDOW TO OPEN ANY MORE -- the panel lives in the column.
        What is left of this is the useful half of what the button did:
        somebody with two profiles already open means those two.
        """
        panel = getattr(self, "_timeline", None)
        if panel is None:
            return
        already = [p for p, _g, m in self._slots
                   if m is None and p.suffix.lower() in (".icc", ".icm")]
        if already:
            panel.add(already)
        box = panel.parent()
        while box is not None and not isinstance(box, QGroupBox):
            box = box.parent()
        if box is not None and hasattr(box, "_refold"):
            box._fold_open = True
            box._refold()

    def _on_glossary(self) -> None:
        """Explain every word this window uses, in plain language.

        Shown on demand rather than crammed into the controls, so the panel
        stays readable while nobody is ever stuck on a word they did not
        choose to learn.
        """
        body = "".join(
            f"<p><b>{term}</b><br>{text}</p>" for term, text in GLOSSARY)
        Notice(self, "What do these words mean?", body,
               rich=True, ok="Close", scroll=True).exec()

    def _on_compare_changed(self) -> None:
        """Build whatever the user chose to compare against, and say what it is.

        Every branch either produces a gamut or explains in plain words why it
        could not, and puts the combo box back to "Nothing" so the screen never
        claims a comparison that is not there.
        """
        choice = self._compare.currentData()
        self._reference = None
        if not (choice and choice[0] == "icc"):
            self._reference_path = None
        self._compare_note.setText("")
        try:
            if choice is None:
                pass
            elif choice[0] == "space":
                name = choice[1]
                self._reference = (name, reference_gamut(
                    name, white_point=self._white.currentData(),
                    steps=self._detail.value(),
                    space=self._build_space()))
                self._compare_note.setText(REFERENCE_SPACES[name]["note"])
            elif choice[0] == "icc":
                # PICTURES BELONG HERE TOO. They were readable all along --
                # _build_one has handled them since pictures were added -- and
                # simply were not offered, so "hold this paper up against that
                # photograph" could only be done by opening the photograph as
                # one of the two shapes.
                pictures = " ".join(f"*{e}" for e in IMAGE_EXTENSIONS)
                dlg = self._file_dialog(
                    "Choose a file to compare against",
                    QFileDialog.FileMode.ExistingFile,
                    "Everything this can compare against "
                    f"(*.icc *.icm *.gam *.ti3 *.cxf *.mxf *.txt {pictures});;"
                    "ICC profiles (*.icc *.icm);;"
                    "Measurements (*.ti3 *.cxf *.mxf *.txt);;"
                    f"Pictures ({pictures});;"
                    "ArgyllCMS gamut files (*.gam);;All files (*)")
                if not dlg.exec():
                    self._compare.setCurrentIndex(0)
                    return
                path = dlg.selectedFiles()[0]
                self._last_folder = str(Path(path).parent)
                self._reference_path = Path(path)
                chosen = Path(path)
                built, _m = self._build_one(chosen)
                self._reference = (_profile_label(chosen), built)
                self._compare_note.setText(
                    "The gamut this profile describes, asked of the profile "
                    "itself." if chosen.suffix.lower() in (".icc", ".icm", ".gam")
                    else "The colours actually in this picture — not the space "
                         "it was saved in."
                    if chosen.suffix.lower() in IMAGE_EXTENSIONS
                    else "The gamut this measurement reached — every corner of "
                         "it a patch that was printed and read.")
            elif choice[0] == "visible":
                v, _f = optimal_colour_solid(
                    "D50" if self._white.currentData() == "D50" else "D65",
                    max(24, self._detail.value() * 3))
                lab = xyz_to_lab(v, self._white.currentData())
                self._reference = ("Every visible colour",
                                   build_gamut(lab, input_space="lab",
                                               space=self._build_space(),
                                               white_point=self._white.currentData()))
                self._compare_note.setText(
                    "Every colour a printed surface could possibly show under "
                    "this light. No printer comes close, and that is normal.")
        except Exception as exc:      # noqa: BLE001 — always explain, never crash
            Notice.warn(
                self, "That comparison could not be prepared", str(exc))
            self._reference = None
            self._compare.setCurrentIndex(0)
            return
        self._chart_profile_offer()
        self._redraw()

    def _file_dialog(self, title: str, mode, name_filter: str,
                     preselect: str = "", profiles: bool = True) -> QFileDialog:
        """A file dialog with useful places already in its sidebar.

        Qt's own dialog rather than the operating system's, because only that
        one lets the shortcuts down the left be set — which is the difference
        between finding a chart in one click and hunting for it.
        """
        dlg = QFileDialog(self, title)
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog)
        dlg.setFileMode(mode)
        dlg.setNameFilter(name_filter)
        dlg.setSidebarUrls(_sidebar_urls(self._last_folder, profiles=profiles))
        if preselect:
            dlg.selectFile(preselect)
        if self._last_folder:
            dlg.setDirectory(self._last_folder)
        # Qt opens its own dialog small, and the shortcuts down the left get
        # the leftovers -- so folder names like "Downloads" arrive truncated,
        # which defeats the point of having them. Give the dialog a sensible
        # size (within the screen, as the main window is) and the sidebar
        # enough width for the longest name actually in it.
        screen = QApplication.primaryScreen()
        room = screen.availableGeometry() if screen is not None else None
        if room is not None:
            dlg.resize(min(1000, room.width() - 80), min(640, room.height() - 120))
        sidebar = dlg.findChild(QListView, "sidebar")
        if sidebar is not None:
            metrics = sidebar.fontMetrics()
            widest = max((metrics.horizontalAdvance(Path(u.toLocalFile()).name)
                          for u in dlg.sidebarUrls()), default=0)
            sidebar.setMinimumWidth(widest + 62)   # room for icon and padding
        _style_dialog_toolbar(dlg, PALETTES[self._appearance]["arrow"])
        return dlg

    def _on_open(self) -> None:
        # ASKED OF THE LIBRARY, not listed by hand: the picture formats that
        # can be opened depend on what is installed, so offering a fixed list
        # would either promise something that fails or hide something that
        # works.
        pictures = " ".join(f"*{e}" for e in IMAGE_EXTENSIONS)
        dlg = self._file_dialog(
            "Open a measurement, a profile, a chart or a picture",
            QFileDialog.FileMode.ExistingFiles,
            "Everything this can open "
            f"(*.ti3 *.cxf *.mxf *.txt *.icc *.icm *.gam *.ti1 *.ti2 *.pxf "
            f"{pictures});;"
            "Measurements (*.ti3 *.cxf *.mxf *.txt);;"
            "ICC profiles (*.icc *.icm);;"
            "Charts to be printed (*.ti1 *.ti2 *.txt *.pxf);;"
            f"Pictures ({pictures});;"
            "ArgyllCMS gamut files (*.gam);;All files (*)")
        if dlg.exec():
            for chosen in dlg.selectedFiles():
                self._last_folder = str(Path(chosen).parent)
                self._load(Path(chosen))

    # ---- a chart waiting to be printed -----------------------------------

    def _on_open_chart(self) -> None:
        """Open a .ti1, .ti2 or i1Profiler target — a chart, not a measurement."""
        dlg = self._file_dialog(
            "Open a chart that has not been printed yet",
            QFileDialog.FileMode.ExistingFile,
            "Charts to be printed (*.ti1 *.ti2 *.txt *.pxf *.cxf);;"
            "ArgyllCMS charts (*.ti1 *.ti2);;"
            "i1Profiler targets (*.txt *.pxf);;All files (*)")
        if not dlg.exec():
            return
        path = Path(dlg.selectedFiles()[0])
        self._last_folder = str(path.parent)
        self._open_chart_file(path)

    def _open_chart_file(self, path: Path) -> None:
        """Read one chart and show it, or say plainly why it could not be."""
        import chart as chart_mod

        try:
            read = chart_mod.read_chart(path)
        except Exception as exc:               # noqa: BLE001 — always explain
            _log().warning("could not read chart %s: %s", path.name, exc)
            Notice.warn(
                self, "This chart could not be used",
                f"{path.name}\n\n{exc}\n\nThis opens a chart that is waiting "
                "to be printed: a .ti1 or .ti2 from ChromIQ or ArgyllCMS, or "
                "the .txt or .pxf file i1Profiler saves for a target. A chart "
                "that has already been measured is a .ti3, and that goes "
                "through Open a measurement or a profile… instead.")
            return
        self._chart = (path, read)
        _log().info("opened chart %s (%s): %d patches, %d repeated",
                    path.name, read.kind, read.n_patches, read.duplicates)
        # A chart the user has just opened deserves a profile suggested rather
        # than an empty box: if exactly one profile is already on screen, that
        # is almost certainly the one it belongs to.
        if self._chart_profile is None:
            for candidate in self._profiles_on_screen():
                self._chart_profile = candidate
                break
        self._fill_chart_profiles()
        self._place_chart()

    def _chart_profile_offer(self) -> None:
        """Keep Placed through in step with whatever is open.

        Opening the profile a chart belongs to should be enough: a person who
        has a chart on screen with nothing to place it through, and who then
        opens a profile, has already said what they want.
        """
        if self._chart is None:
            return
        had = self._chart_profile
        if had is None:
            for candidate in self._profiles_on_screen():
                self._chart_profile = candidate
                break
        self._fill_chart_profiles()
        if self._chart_profile is not had:
            self._place_chart()
        else:
            self._refresh_chart_panel()

    def _profiles_on_screen(self) -> list:
        """Every ICC profile already open, in the order they were opened.

        Only an ICC profile can place a chart's patches. A measurement holds
        the patches of a *different* chart, and a .gam file is a bare surface
        with no way in from device values at all — so neither can answer "where
        would this ink amount land", and offering them would be offering
        something that cannot work.
        """
        seen, out = set(), []
        for path, _g, _m in self._slots:
            if path.suffix.lower() in (".icc", ".icm") and path not in seen:
                seen.add(path)
                out.append(path)
        ref = self._reference_path
        if (ref is not None and ref.suffix.lower() in (".icc", ".icm")
                and ref not in seen):
            out.append(ref)
        return out

    def _fill_chart_profiles(self) -> None:
        """Refill the Placed-through box from what is open, keeping the choice."""
        want = self._chart_profile
        self._chart_through.blockSignals(True)
        self._chart_through.clear()
        for path in self._profiles_on_screen():
            self._chart_through.addItem(f"{path.stem} — already open", str(path))
        if want is not None and self._chart_through.findData(str(want)) < 0:
            self._chart_through.addItem(want.stem, str(want))
        self._chart_through.addItem("Choose an ICC profile…", "")
        index = (self._chart_through.findData(str(want))
                 if want is not None else -1)
        self._chart_through.setCurrentIndex(max(0, index))
        self._chart_through.blockSignals(False)

    def _on_chart_profile(self) -> None:
        """A different profile chosen to place the patches through."""
        data = self._chart_through.currentData()
        if data:
            self._chart_profile = Path(data)
        else:
            dlg = self._file_dialog(
                "Choose the profile to place these patches through",
                QFileDialog.FileMode.ExistingFile,
                "ICC profiles (*.icc *.icm);;All files (*)")
            if not dlg.exec():
                self._fill_chart_profiles()
                return
            self._chart_profile = Path(dlg.selectedFiles()[0])
            self._last_folder = str(self._chart_profile.parent)
        self._fill_chart_profiles()
        self._place_chart()

    def _place_chart(self) -> None:
        """Work out where the chart's patches land, and show the result.

        Failing to place them is not an error to hide: the chart stays open and
        the panel says what is missing, because "open a profile" is something
        the person can act on and an empty window is not.
        """
        import chart as chart_mod

        self._chart_placed = None
        if self._chart is None:
            self._refresh_chart_panel()
            return
        if self._chart_profile is not None:
            try:
                self._chart_placed = chart_mod.through_profile(
                    self._chart[1], self._chart_profile)
            except Exception as exc:          # noqa: BLE001 — always explain
                _log().warning("could not place chart: %s", exc)
                Notice.warn(self, "These patches could not be placed", str(exc))
                self._chart_profile = None
                self._fill_chart_profiles()
        self._refresh_chart_panel()
        if self._chart_drawable():
            # A chart that can be drawn is something to look at, so everything
            # that saves or exports the view has something to work with. In
            # ink amounts that is true with no profile at all, which is the
            # whole point of the view.
            self._save.setEnabled(True)
            self._export_btn.setEnabled(True)
            self._picture.setEnabled(True)
        if self._slots or self._reference is not None or self._chart_drawable():
            self._redraw()
        else:
            self._update_chart_numbers()

    def _close_chart(self) -> None:
        self._chart = None
        self._chart_placed = None
        self._refresh_chart_panel()
        if self._slots or self._reference is not None:
            self._redraw()

    def _refresh_chart_panel(self) -> None:
        """The chart's name, and what is still needed before it can be shown."""
        self._chart_row.setVisible(self._chart is not None)
        self._chart_through_row.setVisible(self._chart is not None)
        self._chart_through_name.setText(
            "Placed through — optional here" if self._drawing_in_ink()
            else "Placed through")
        if self._chart is None:
            self._chart_label.setText("")
            # A LINE HERE EVEN WITH NOTHING OPEN, for two reasons. It says what
            # the section is for before anybody has to click to find out — and
            # it is the only wide thing in the group when it is empty, so
            # without it the box shrinks to the width of its button and the ⓘ
            # drops onto a line of its own, which is what every other group in
            # this column does not do.
            self._chart_note.setText(
                "A .ti1 or .ti2 from ChromIQ or ArgyllCMS, or an i1Profiler "
                "target: the patches you are about to print, shown where a "
                "profile says each one would land.")
            self._chart_box.setVisible(False)
            self._refresh_chart_look_box()
            return
        path, read = self._chart
        kind = {"CTI1": "an ArgyllCMS chart", "CTI2": "an ArgyllCMS chart, "
                "laid out on a sheet", "CxF3": "an i1Profiler target"}.get(
                    read.kind, "a chart")
        patches = ("1 patch" if read.n_patches == 1
                   else f"{read.n_patches} patches")
        self._chart_label.setText(f"{path.stem}\n{patches} — {kind}")
        self._chart_note.setText(self._chart_state_note())
        self._update_chart_numbers()
        self._refresh_chart_look_box()

    def _chart_state_note(self) -> str:
        """One line saying what the chart is, or what it still needs.

        NEVER AN EMPTY PANEL. A chart with no profile cannot be drawn at all —
        there is nowhere to draw it — and the difference between "this window
        is broken" and "this window is waiting for one more file" is entirely
        in whether it says so.
        """
        _path, read = self._chart
        in_ink = self._drawing_in_ink()
        if in_ink:
            ok, why = self._chart_in_ink_ok()
            if not ok:
                return why
        if self._chart_profile is None:
            if in_ink:
                return ("Shown as the ink amounts the file actually holds — "
                        "no profile needed, and nothing here is a guess. The "
                        "dots are painted with those amounts read as screen "
                        "colour, which is a legend and not a prediction: "
                        "choose the ICC profile these patches were built for "
                        "under Placed through and they take the colours they "
                        "will really print as.")
            return ("A chart on its own is a list of ink amounts, and ink "
                    "amounts have no place in colour space until something "
                    "says what they would print as. Choose the ICC profile "
                    "these patches were built for under Placed through, and "
                    "they appear. To see the patch set on its own instead, "
                    "with no profile at all, choose Ink amounts under Draw "
                    "it in.")
        placed = self._chart_placed
        if placed is None:
            return ("These patches could not be placed through that profile. "
                    "Choose another one under Placed through.")
        extra = []
        if read.duplicates:
            extra.append(
                f"{read.duplicates} of them repeat a patch already in the "
                "chart, which charts do on purpose"
                if read.duplicates > 1 else
                "one of them repeats a patch already in the chart, which "
                "charts do on purpose")
        if read.clamped:
            extra.append(f"{read.clamped} held ink amounts outside the "
                         "possible range and were pulled back into it")
        if not read.scale_certain:
            extra.append("this file does not say whether its ink amounts "
                         "count to 100 or to 255, and 100 was assumed — "
                         "nothing in it goes high enough to tell")
        tail = (" " + "; ".join(s[0].upper() + s[1:] for s in extra) + "."
                if extra else "")
        if in_ink:
            # The profile has not moved anything — it cannot, the ink amounts
            # are the axes — so saying "shown where it says they would land"
            # here would describe the wrong picture entirely.
            return (f"To be printed, not measured. Shown as the ink amounts "
                    f"the file holds, painted with the colours "
                    f"{placed.profile} says they will print as, from its "
                    f"{placed.intent} table.{tail}")
        return (f"To be printed, not measured. Shown where "
                f"{placed.profile} says they would land, using its "
                f"{placed.intent} table.{tail}")

    def _chart_lab(self):
        """Where the chart's patches sit, under the white point now chosen.

        Everything else in the window moves when the white point changes, and
        a chart left in the profile's own D50 would be drawn a few ΔE away
        from where the shapes around it moved to — the exact size of error
        that looks like a result.
        """
        if self._chart_placed is None:
            return None
        return self._chart_placed.under(self._white.currentData())

    def _build_space(self) -> str:
        """The space to BUILD a gamut in, which is not always the one drawn in.

        A gamut can only be built in a colour space, because building one means
        measuring a boundary and a volume. Ink amounts are not one, so while
        they are chosen every shape is built in CIELAB instead — the papers,
        profiles and pictures you have open keep loading, keep their numbers,
        and are simply not drawn until a colour space is chosen again.

        The alternative was to refuse to open anything while in ink amounts,
        which would have made a view meant for looking at a chart quietly
        break the rest of the window. This way the ink view costs nothing:
        switch to it and back, and everything is where it was.
        """
        space = self._space.currentData()
        return space if space in SPACES else "lab"

    def _on_chart_skin(self) -> None:
        """The skin's own settings only exist while there is a skin."""
        self._chart_skin_row.setVisible(
            self._chart_skin.currentData() != "none")
        self._redraw()

    def _chart_look(self) -> dict:
        """Every setting the renderer needs for the chart's patches.

        One place, read by both the live view and the saved page, for the same
        reason ``_render_options`` exists: two nearly identical argument lists
        are how an option comes to reach one route and not the other.
        """
        return dict(
            dot_size=self._chart_dot.value() / 10.0,
            dot_opacity=self._chart_dot_opacity.value() / 100.0,
            out_dot_size=self._chart_out_dot.value() / 10.0,
            out_dot_opacity=self._chart_out_opacity.value() / 100.0,
            show_inside=True,
            show_outside=self._chart_show_outside.isChecked(),
            skin=self._chart_skin.currentData() or "none",
            skin_colour=self._chart_skin_colour.currentData() or "grey",
            skin_opacity=self._chart_skin_opacity.value() / 100.0,
            accent=SCHEMES.get(self._scheme,
                               SCHEMES["Magenta"])["accent"],
        )

    def _refresh_chart_look_box(self) -> None:
        """Show these controls only where they can do something.

        The group itself needs a chart that can actually be drawn. The
        out-of-reach row needs something for the patches to be out of reach
        OF, which is what ``_judging_shapes`` answers, and a profile to have
        placed them — without one there is no colour to judge and every patch
        is simply "a patch".
        """
        drawable = self._chart_drawable()
        self._chart_look_box.setVisible(drawable)
        judged = bool(self._judging_shapes()) and self._chart_placed is not None
        self._chart_outside_row.setVisible(drawable and judged)
        self._chart_skin_row.setVisible(
            drawable and self._chart_skin.currentData() != "none")

    def _drawing_in_ink(self) -> bool:
        """True while the axes are the printer's own ink amounts.

        Asked in a good many places, and asked as a question about the window
        rather than a string comparison, so that the one fact "we are not in a
        colour space" has a single name.
        """
        return self._space.currentData() == "rgb"

    def _chart_in_ink_ok(self) -> tuple:
        """Whether the open chart can go on the three ink axes, and why not.

        Returns ``(False, "")`` when there is no chart at all — nothing is
        wrong, there is simply nothing to draw, and a reason would be a
        complaint about something the person has not done yet.
        """
        import chart as chart_mod
        if self._chart is None:
            return False, ""
        return chart_mod.can_draw_in_ink(self._chart[1])

    def _chart_drawable(self) -> bool:
        """Whether there is a chart that can actually be put in the picture.

        The two halves of the window ask different things of a chart. A colour
        space needs a profile, because ink amounts have no place in one until
        something says what colour they make. Ink amounts need no profile and
        never did — the file already holds the numbers — but they do need the
        chart to have exactly three of them.
        """
        if self._chart is None:
            return False
        if self._drawing_in_ink():
            return self._chart_in_ink_ok()[0]
        return self._chart_placed is not None

    def _chart_cloud(self):
        """The chart as (name, Lab, outside-mask, ink amounts), or None.

        The mask marks the patches that fall outside the FIRST shape on
        screen — the one the eye reads as the subject. Marking against several
        at once would put one dot in two states.

        Lab is None when no profile has been chosen, which only happens in the
        ink-amount view: there the dots are positioned from the ink amounts
        and painted with them too. Everywhere else a chart without a profile
        is not drawable at all, so the pair can never disagree.
        """
        import chart as chart_mod
        if not self._chart_drawable():
            return None
        path, read = self._chart
        in_ink = self._drawing_in_ink()
        lab = self._chart_lab()
        device = None
        if in_ink:
            try:
                device = chart_mod.device_positions(read)
            except Exception:      # noqa: BLE001 — a view must never crash
                return None
        marked = None
        judged = self._judging_shapes()
        # Judging still needs a profile, in either view: the question "can the
        # paper reach this patch" is about colour, and only a profile can say
        # what colour an ink amount makes. So in ink amounts the dots appear
        # with no profile, and turn red only once one is chosen.
        if judged and lab is not None:
            try:
                marked = chart_mod.outside_report(lab, judged[0][1]).beyond
            except Exception:      # noqa: BLE001 — a view must never crash
                marked = None
        return (path.stem, lab, marked, device)

    def _judging_shapes(self) -> list:
        """Every shape a chart can be counted against: (name, gamut, path).

        THE PATH IS CARRIED, not just the name, and that is not tidiness. A
        profile and the measurement it was built from routinely have the same
        stem — ``Glossy-paper.icc`` beside ``Glossy-paper.ti3`` is the ordinary
        case, not a contrived one. Deciding "is this the profile that placed
        the patches?" by comparing names told the reader that a *measurement*
        had placed them, and printed the wrong verdict under it. Caught by
        driving the window with exactly that pair of files open.
        """
        out = [(p.stem, self._in_lab(g, p, m), p, m is not None)
               for p, g, m in self._slots]
        if self._reference is not None:
            # A comparison built from a file is a measurement when it is one;
            # a standard colour space or the visible solid is not, and neither
            # has a paper white to be judged against.
            measured = (self._reference_path is not None
                        and self._reference_path.suffix.lower()
                        not in (".icc", ".icm", ".gam"))
            out.append((self._reference[0],
                        self._in_lab(self._reference[1],
                                     self._reference_path, None),
                        self._reference_path, measured))
        return out

    def _chart_marked_against(self, chart, gamut, slot=None):
        """The chart, with its lost patches worked out against *this* shape.

        Each room in the side-by-side view holds one paper, and the chart in
        it has to answer for that paper — which is the whole reason somebody
        put two rooms up. Returns the chart unchanged when there is nothing to
        judge it by, and never raises: a marking that cannot be worked out
        leaves the patches unmarked rather than taking the picture down.
        """
        if chart is None or gamut is None:
            return chart
        name, lab, _old, device = chart
        if lab is None:
            return chart
        import chart as chart_mod
        path = slot[0] if slot else None
        measurement = slot[2] if slot else None
        try:
            marked = chart_mod.outside_report(
                lab, self._in_lab(gamut, path, measurement)).beyond
        except Exception:          # noqa: BLE001 — a view must never crash
            marked = None
        return (name, lab, marked, device)

    def _in_lab(self, gamut, path=None, measurement=None):
        """The same paper as a gamut BUILT in CIELAB, whatever is being drawn.

        JUDGING IS NOT A DRAWING QUESTION. "Can this paper reach this patch"
        is about colour, so its answer must be the same whichever space the
        picture happens to be using — and the distance quoted beside it is
        ΔE2000, which is defined on CIELAB and on nothing else.

        Left alone the shape is built in whatever is chosen under Draw it in,
        while a chart's patches are always Lab. Held against each other those
        disagree: quietly in CIELUV, and catastrophically in CIE XYZ where a
        gamut runs 0 to 1 and the patches run 0 to 100, so every patch lands
        outside. On the demo files the same chart and paper answered 240
        outside in CIELAB, 178 in CIELUV and 480 in CIE XYZ — three answers
        to a question that has one.

        IT IS REBUILT RATHER THAN CONVERTED, and the difference is real. A
        convex hull is not convex any more once it has been through the
        Lab↔XYZ curve, so converting the drawn shape's vertices gives a
        surface that is close to the Lab one and not the same: on random
        points the two hulls kept 47 and 51 vertices. Close is not the
        standard for a number quoted in ΔE, so the Lab shape is built from
        the same measurements the drawn one came from, and cached — the
        answer then cannot depend on the picture at all.
        """
        if gamut.space == "lab":
            return gamut
        white = self._white.currentData()
        key = (str(path), white, self._relative.isChecked(),
               self._mode.currentData(), self._detail.value())
        hit = self._lab_gamuts.get(key)
        if hit is not None:
            return hit
        try:
            if measurement is not None:
                drive = (None if self._mode.currentData() == "hull"
                         else measurement.device)
                built = build_gamut(measurement.lab, drive, input_space="lab",
                                    space="lab", white_point=white)
            elif path is not None:
                reader = (gam_gamut if Path(path).suffix.lower() == ".gam"
                          else icc_gamut)
                built = reader(Path(path), white_point=white, space="lab")
            else:
                return gamut
        except Exception:          # noqa: BLE001 — never take the view down
            return gamut
        self._lab_gamuts[key] = built
        return built

    def _update_chart_numbers(self) -> None:
        """The three questions, answered against whatever else is open."""
        import chart as chart_mod

        if self._chart is None:
            self._chart_box.setVisible(False)
            self._refresh_chart_look_box()
            return
        self._chart_box.setVisible(True)
        _path, read = self._chart
        placed = self._chart_placed
        in_ink = self._drawing_in_ink()
        patches = ("1 patch" if read.n_patches == 1
                   else f"{read.n_patches} patches")
        if placed is None:
            self._chart_headline.setText(
                f"{patches} waiting to be printed. None of them has been "
                "measured.")
            self._chart_rows.setText(
                "Choose a profile under Placed through and they can be "
                "counted against whatever else you have open."
                if in_ink else
                "Choose a profile under Placed through and they can be "
                "counted.")
            # The spacing figure needs no profile in ink amounts: it is a
            # question about the chart, and the chart is right here.
            self._show_chart_spread(in_ink and self._chart_in_ink_ok()[0])
            return

        self._chart_headline.setText(
            f"{patches}, drawn as the ink amounts themselves and painted "
            f"through {placed.profile}." if in_ink else
            f"{patches}, placed through {placed.profile}.")
        lab = self._chart_lab()

        lines = []
        for name, gamut, path, measured in self._judging_shapes():
            try:
                report = chart_mod.outside_report(lab, gamut,
                                                  against=name)
            except Exception as exc:      # noqa: BLE001 — never crash a readout
                lines.append(f"{name}: could not be counted ({exc}).")
                continue
            same = (path is not None and self._chart_profile is not None
                    and Path(path) == Path(self._chart_profile))
            lines.append(self._chart_verdict(name, report, same)
                         + self._white_mismatch_caution(measured))
        self._chart_rows.setText(
            "\n\n".join(lines) if lines else
            "Nothing else is open to count them against. Open the profile as "
            "a shape, or the measurement of the paper, and each one gets a "
            "line here.")

        self._show_chart_spread(in_ink)

    def _show_chart_spread(self, in_ink: bool) -> None:
        """How evenly the chart samples whatever it is being drawn in.

        THE UNITS ARE NOT THE SAME IN THE TWO VIEWS and the sentence has to
        say which it is quoting. In a colour space the answer is a distance in
        Lab — how far apart the patches will look. In ink amounts it is a
        distance in ink — how finely the chart samples the printer's controls,
        which is the question the chart's author was actually answering. The
        two are different numbers about the same chart, and a figure carrying
        the wrong name for its units is the kind of wrong that gets quoted.
        """
        import chart as chart_mod

        points = None
        if in_ink:
            if self._chart is not None and self._chart_in_ink_ok()[0]:
                try:
                    points = chart_mod.device_positions(self._chart[1])
                except Exception:     # noqa: BLE001 — never crash a readout
                    points = None
        else:
            points = self._chart_lab()
        spread = None if points is None else chart_mod.spread(points)
        if spread is None:
            # NEVER LEFT EMPTY WHILE A CHART IS OPEN. The ⓘ that explains
            # these figures shares this row, and an empty label collapses and
            # leaves the icon sitting on a line of its own explaining nothing
            # — which is exactly what the panel audit reported.
            self._chart_spread.setText(
                "" if self._chart is None else
                "How far apart the patches are is measured once a profile has "
                "placed them. Choose one under Placed through — or choose Ink "
                "amounts under Draw it in to measure the spacing of the ink "
                "amounts themselves, which needs no profile.")
            return
        repeated = (
            "" if not spread.repeats else
            " One patch lands exactly where another does and was left "
            "out of these; charts repeat patches on purpose."
            if spread.repeats == 1 else
            f" {spread.repeats} patches land exactly where another does "
            f"and were left out of these; charts repeat patches on "
            f"purpose.")
        units = ("how much of each ink, out of 100" if in_ink
                 else "straight-line distance in Lab")
        self._chart_spread.setText(
            f"How far apart: closest pair {spread.closest:.1f}, typical "
            f"{spread.median_gap:.1f}, widest gap {spread.largest_gap:.1f}"
            f" — {units}.{repeated}")

    #: Above this many ΔE outside the profile that placed them, patches are
    #: not explained by how finely the surface was sampled, and the chart
    #: builder is worth suspecting. Measured: the worst a real 5960-patch chart
    #: managed against its own profile was 1.3 ΔE, and it fell to 0.05 as the
    #: surface was sampled more finely. Twice that leaves ample room.
    CHART_BUILDER_SUSPECT = 2.0

    def _white_mismatch_caution(self, measured: bool) -> str:
        """Warn when a chart is being counted against two different whites.

        THIS IS THE ONE THAT WOULD HAVE SHIPPED A FALSE ALARM, and the numbers
        are not subtle. A chart is placed through the profile's relative
        colorimetric table, and "relative colorimetric" means, by definition,
        that the paper's white becomes L* 100. A measurement read absolutely
        keeps the white the instrument actually saw — L* 93.8 on the demo
        glossy paper. So every light patch in the chart floats above the
        measured shape by that difference, for no reason to do with the
        printer at all. Measured on a real 5960-patch chart against the
        measurement of the very paper its profile describes:

            measurement judged absolutely     624 patches outside, worst 4.5
            measurement judged against its    0 patches outside, worst 1.0
            own white

        Six hundred patches of pure artefact. The tick box that fixes it is
        already in this window, so the answer is to say which one is being
        looked at and where the switch is — never to move it quietly, because
        it changes every other figure on screen as well.
        """
        if not measured or self._relative.isChecked():
            return ""
        return ("\nThese two are measured against different whites: the chart "
                "is placed relative to the paper's white, and this "
                "measurement is being judged against an absolute D50, so the "
                "lightest patches sit above it whatever the printer did. Tick "
                "Judge each paper against its own white, further down, to "
                "compare them like for like.")

    def _chart_verdict(self, name, report, same_profile: bool) -> str:
        """One shape's line, in words rather than in three bare numbers.

        The sentence differs when the shape doing the judging is the very
        profile that placed the patches, because then a clean answer proves
        something quite different from a clean answer against a measurement —
        and letting the reader assume otherwise is the whole trap this feature
        had to be designed around.
        """
        head = (f"{name}: {report.n_inside} inside, {report.n_edge} on the "
                f"edge, {report.n_beyond} outside.")
        if same_profile:
            if report.all_inside:
                return (head + "\nEvery patch sits inside the profile it was "
                        "placed through — which is what should happen, and is "
                        "a check of the chart rather than of your printer.")
            # HOW BADLY WRONG DECIDES WHICH IT IS, and the scale of the two
            # cases is nothing alike. A chart builder that went wrong — ink
            # amounts counted to 255 instead of 100, the wrong rendering
            # intent, the wrong profile entirely — puts a great many patches a
            # very long way out. A surface drawn through a grid of samples
            # leaves one or two a whisker out, measured at 1.3 ΔE on a real
            # profile. Printing the alarming sentence for the second case
            # would send somebody hunting a fault that is not there.
            if report.worst < self.CHART_BUILDER_SUSPECT \
                    and report.n_beyond <= max(1, report.n_patches // 100):
                return (head + f"\nThe furthest out is {report.worst:.1f} ΔE, "
                        "which is the thickness of the boundary itself rather "
                        "than a fault: a gamut surface is drawn through a grid "
                        "of samples, and the real edge bulges very slightly "
                        "between them. Nothing here needs looking into — and "
                        "this is a check of the chart rather than of your "
                        "printer, because the same profile answered both "
                        "halves of the question.")
            return (head + f"\nWorst {report.worst:.1f} ΔE, and "
                    f"{report.n_beyond} of them. These were placed through "
                    "this very profile, so they should all have been inside "
                    "it. Something differs between the way the chart was "
                    "built and the way it is being read — the rendering "
                    "intent, ink amounts counted to 255 where the file wanted "
                    "100, patches clipped to a box around the gamut instead "
                    "of to its surface, or simply a different profile.")
        if report.all_inside:
            return (head + f"\nEverything this chart asks for is within reach "
                    f"of {name}.")
        return (head + f"\nWorst {report.worst:.1f} ΔE, average of those "
                f"{report.average:.1f}. {name} cannot reach what those "
                "patches ask for.")

    def _close_one(self, which: int) -> None:
        """Close just this chart and leave the other one where it is."""
        if 0 <= which < len(self._slots):
            del self._slots[which]
        self._refresh_slot_labels()
        self._fill_chart_profiles()
        if self._slots or self._chart_placed is not None:
            self._redraw()
        else:
            self._on_clear()

    def _on_clear(self) -> None:
        """Close everything on screen: the files, the chart AND the comparison.

        THE COMPARISON USED TO SURVIVE THIS, and what that left behind was not
        a harmless setting. Measured, with two papers open and Adobe RGB
        chosen, immediately after pressing the button:

            files open              []
            shapes actually drawn   ['Adobe RGB (1998)']
            the readout said        "90.7% of the colour Glossy-paper can
                                     print also fits inside Adobe RGB (1998)"

        So a shape stayed in the picture with nothing left to compare it to,
        and the figures went on describing a paper that had just been closed.
        The second of those is the worse one: a wrong sentence on screen about
        a file the person can see is gone.

        ONE BUTTON RATHER THAN TWO, and that is a decision rather than the
        lazy option. Basti asked whether there should be a second Clear for
        the comparison, or a tick-box beside this one. There is already a
        second way to drop it -- "Nothing — this one on its own", the first
        entry in Compare with -- sitting inside the group it belongs to, so
        another control would be a third route to something two already cover.

        And the two gestures already mean different things. The × beside a
        file closes that one and keeps everything else, which is how somebody
        works through one paper after another against a fixed comparison.
        "Close them all" is the start-again gesture, and starting again with
        a comparison still loaded is not starting again.
        """
        self._slots.clear()
        self._chart = None
        self._chart_placed = None
        # Through the combo box and its own handler rather than by assigning
        # to _reference: the handler is what also clears the note under it and
        # keeps the box showing what is really loaded. Index 0 is "Nothing",
        # which opens no dialog.
        self._compare.setCurrentIndex(0)
        self._on_compare_changed()
        self._refresh_slot_labels()
        self._refresh_chart_panel()
        self._fill_chart_profiles()
        self._show_placeholder()
        self._volume.setText("—")
        self._volume_hint.setText(self._volume_units())
        # THE FIGURES GO WITH THE FILES THEY DESCRIBED. Every one of these is
        # a sentence about something now closed, and they are read straight
        # back out by _readout_text() into a saved picture's caption.
        for name in self.READOUTS:
            label = getattr(self, name, None)
            if label is not None:
                label.setText("")
        self._clear_btn.setVisible(False)
        self._save.setEnabled(False)

    def _on_save(self) -> None:
        """Write the scene as a standalone page the user can keep or send.

        Saved beside the first measurement by default, because that is where
        the user will look for it, and it carries its own viewer so it still
        opens with no network and no ChromIQ.

        AND IT SAVES WHATEVER IS ON SCREEN, which since the run panel moved
        into the column includes the run's own picture. One button, one set of
        options, whichever question the view is answering -- see
        _save_the_run_page.
        """
        if getattr(self, "_run_drawn", False):
            self._save_the_run_page()
            return
        if not self._slots and self._chart_placed is None:
            return
        options = WebPageDialog(self)
        if not options.exec():
            return
        chosen = options.choices()
        first = (self._slots[0][0] if self._slots
                 else self._chart[0] if self._chart is not None
                 else Path(self._reference[0] if self._reference else "gamut"))
        default = first.with_name(first.stem + "-gamut.html")
        dlg = self._file_dialog("Save this view as a web page",
                                QFileDialog.FileMode.AnyFile,
                                "Web page (*.html)", str(default),
                                profiles=False)
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dlg.setDefaultSuffix("html")
        if not dlg.exec():
            return
        target = picture.next_free(Path(dlg.selectedFiles()[0]))
        try:
            gamuts, clouds, styles, lost = self._scene_contents()
            # THE SAME WRITER THE VIEW USES. Saving used to call the
            # single-scene route directly, so two rooms saved as one overlaid
            # scene and a cross-section saved as a 3D shape -- three of the
            # four arrangements this window can show wrote a different picture
            # than the one on screen, from a button that says "this view".
            self._write_scene(gamuts, clouds, styles, lost, target,
                              saved=True,
                              controls=chosen.get("controls", True),
                              offer=chosen.get("offer"),
                              glide=chosen.get("glide", False),
                              colours=chosen.get("colours"),
                              carry_viewer=chosen["carry_viewer"],
                              both_views=chosen.get("both_views", False),
                              notes=(self._readout_text()
                                     if chosen["numbers"] else ""))
        except OSError as exc:
            Notice.warn(self, "That could not be saved", str(exc))
            return
        # THE NEXT QUESTION IS ALWAYS "HOW DO I SHOW THIS TO SOMEBODY", and
        # the honest answer is not the obvious one: a forum will not run a
        # page like this, however it is pasted in. Saying so here saves an
        # evening of trying, and names the thing that does work.
        Notice.say(
            self, "Saved",
            f"Written to\n{target}\n\n"
            f"{picture.human_size(target.stat().st_size)}. It opens in any "
            "browser by double-clicking it, and needs no network at all — the "
            "3D viewer travels inside the page. Whoever you send it to can "
            "turn the shape, zoom in, and click the names underneath to hide "
            "and show them.\n\n"
            "SENDING IT BY EMAIL OR CHAT: attach the file as it is. Nothing "
            "else has to travel with it.\n\n"
            "PUTTING IT IN A FORUM POST: a forum will not run this page — "
            "they all strip out the part that draws it, whichever way you "
            "paste it in. What works is two things together: post a moving "
            "picture so there is something to look at in the thread, made "
            "with Save this view as a picture… → A moving picture, and put a "
            "link beside it to this page for anybody who wants to turn it "
            "themselves. Most forums will take the page as a file attachment "
            "as well.\n\n"
            "PUTTING IT ON A WEBSITE: upload it and link to it. If it is "
            "going somewhere with a reliable connection you can save it again "
            "without the viewer inside — the same page at about a sixtieth of "
            "the size, which fetches the viewer instead.")

    def _save_the_run_page(self) -> None:
        """The run's picture, saved through the window's own Save button.

        THE OPTIONS ARE THE SAME ONES, and that is the whole point of routing
        it here: until now the run's page was written by a button of its own
        that asked nothing, so it never carried the reader's control strip,
        never offered the light version without the viewer inside, and could
        not leave the numbers out. Reported: "the one for the run until now did
        not allow to choose the controls the user would have on the webpage".

        WHAT THE GRAPH CANNOT USE IT IS NOT ASKED. A line chart has no camera
        to turn and no families to hide, so the control questions are put away
        when the view is showing the graph rather than a cloud -- offering
        controls that cannot exist is worse than not offering them.
        """
        panel = getattr(self, "_timeline", None)
        if panel is None:
            return
        cloud = panel.shows_a_cloud()
        pair_of_shapes = panel.shows_two_shapes()
        options = WebPageDialog(
            self, for_a_cloud=cloud,
            shows={"two_shapes": pair_of_shapes, "surfaces": pair_of_shapes,
                   "flat": False, "camera": cloud, "fade": pair_of_shapes})
        if not options.exec():
            return
        chosen = options.choices()
        first = panel._run.usable[0].name if panel._run.usable else "device"
        default = Path.home() / f"{_clean_stem(first)}-over-time.html"
        dlg = self._file_dialog("Save this view as a web page",
                                QFileDialog.FileMode.AnyFile,
                                "Web page (*.html)", str(default),
                                profiles=False)
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dlg.setDefaultSuffix("html")
        if not dlg.exec():
            return
        target = picture.next_free(Path(dlg.selectedFiles()[0]))
        try:
            said = panel.write_page(
                target, carry_viewer=chosen["carry_viewer"],
                controls=chosen.get("controls", True) if cloud else False,
                offer=chosen.get("offer") if cloud else None,
                numbers=chosen["numbers"],
                colours=chosen.get("colours"))
        except (OSError, ValueError) as exc:
            Notice.warn(self, "That could not be saved", str(exc))
            return
        Notice.say(
            self, "Saved",
            f"Written to\n{target}\n\n"
            f"{picture.human_size(target.stat().st_size)}. It opens in any "
            f"browser by double-clicking it, and {said}.")

    def _load(self, path: Path) -> None:
        # ONE RULE: OPENING A FILE SHOWS YOU THAT FILE. A profile opened here
        # used to become the comparison instead, which draws nothing at all
        # when there is no chart to draw it against -- so opening a profile
        # first appeared to do nothing whatever. Comparing is what the
        # Compare with box is for, and it says so.
        # A CHART DROPPED ON THE WINDOW OPENS AS A CHART. Somebody dragging a
        # .ti1 in has said exactly what they want; making them read an error
        # and then find the other button would be pedantry. Decided on the
        # file's contents, so a measurement saved under a chart's name still
        # opens as a measurement.
        import chart as chart_mod
        if chart_mod.looks_like_chart(path):
            self._open_chart_file(path)
            return
        # THE ROOM IS MADE AFTER THE FILE IS READ, NOT BEFORE.
        #
        # This dropped the oldest of the two open files first and read the new
        # one second -- so a file that could NOT be read took a good one with
        # it. Measured, with two profiles open and a .ti3 containing no
        # patches picked by mistake:
        #
        #     open before   printer-2019.icc, printer-2021.icc
        #     said          "This file could not be used"
        #     open after    printer-2021.icc
        #
        # A message that says nothing worked, over a window that has quietly
        # closed something, is the worst pair of facts to hand somebody: the
        # one thing they are sure of is that they did not ask for that.
        try:
            g, m = self._build_patiently(path)
        except Stopped:
            # ASKED FOR IS NOT WRONG. Somebody pressed Stop; telling them the
            # file "could not be used" would blame them for their own
            # decision, and offer a paragraph of advice about file types to
            # somebody who has just said they did not want to wait.
            _log().info("stopped while opening %s", path.name)
            return
        except Exception as exc:               # noqa: BLE001 — always explain
            _log().warning("could not use %s: %s", path.name, exc)
            Notice.warn(
                self, "This file could not be used",
                f"{path.name}\n\n{exc}\n\nThis opens a measured chart (a .ti3, "
                "the file ArgyllCMS writes after you read a printed chart), an "
                "ICC profile (.icc or .icm), an ArgyllCMS gamut file (.gam), "
                "or an ordinary picture.\n\n"
                "A chart that has not been printed yet — a .ti1, a .ti2, or an "
                "i1Profiler target — is opened too, and lands under A chart to "
                "be printed rather than here. Drag one onto the window and it "
                "goes to the right place by itself.")
            return
        if len(self._slots) >= 2:
            self._slots.pop(0)                 # newest two win
        self._slots.append((path, g, m))
        # A FILE MAY HAVE CHANGED ON DISK since it was last judged against.
        # The cache is keyed by path, so an edited measurement reopened under
        # the same name would be judged against the shape it used to have.
        # Emptying it here costs one rebuild and cannot be wrong.
        self._lab_gamuts.clear()
        # A rebuilt shape is a different object, and everything worked out
        # about the old pair describes shapes that are gone.
        self._forget_the_pair()
        _log().info("opened %s (%s): %s%d vertices, volume %.0f",
                    path.name, "measurement" if m is not None else "profile",
                    f"{m.n_patches} patches, " if m is not None else "",
                    len(g.vertices), g.volume)
        self._warn_if_too_few_patches(path, m)
        self._refresh_slot_labels()
        self._chart_profile_offer()
        self._save.setEnabled(True)
        self._export_btn.setEnabled(True)
        self._picture.setEnabled(True)
        self._redraw()

    def _load_profile_as_comparison(self, path: Path) -> None:
        """Show an ICC profile as the thing to compare against."""
        try:
            reader = (gam_gamut if path.suffix.lower() == ".gam"
                      else icc_gamut)
            g = reader(path, white_point=self._white.currentData(),
                       space=self._build_space())
        except Exception as exc:      # noqa: BLE001 — always explain
            Notice.warn(
                self, "This profile could not be used",
                f"{path.name}\n\n{exc}")
            return
        self._reference = (_profile_label(path), g)
        self._reference_path = path
        self._compare.blockSignals(True)
        self._compare.setCurrentIndex(
            self._compare.findData(("icc", None)))
        self._compare.blockSignals(False)
        self._compare_note.setText(
            f"Comparing against {path.stem} — the colours this profile says "
            "are available.")
        self._redraw()

    #: How long a file may take before the window says anything about it.
    #:
    #: MEASURED, on this application's own demo files: a profile read through
    #: ArgyllCMS takes 149 ms, the same profile read directly 9 ms, and a
    #: measurement 31 ms. So four hundred milliseconds is never reached by a
    #: file that is behaving, and a dialog that flickers up on every ordinary
    #: open would be worse than the silence it replaced.
    #:
    #: The case it exists for is at the other end entirely: ArgyllCMS wedging
    #: on a profile it cannot finish, which is thirty seconds.
    PATIENCE_BEFORE_SAYING = 0.4

    def _build_patiently(self, path: Path):
        """Build a gamut without the window going dead while it happens.

        THE FAULT THIS FIXES. `icc_gamut` runs ArgyllCMS, and ArgyllCMS can
        wedge on a profile it does not like -- measured at over four minutes
        on one, before this application gave up on it. That call was on the UI
        thread, so the whole window froze: nothing painted, nothing answered,
        no way to stop it, and then an error. On a machine with no ArgyllCMS
        the same file opened instantly, which meant the application was FASTER
        without the helper installed. That is upside down.

        SO THE READING HAPPENS ON A THREAD and the window keeps painting. If
        it is quick -- which it is, 149 ms at worst on real files -- nothing
        appears at all and this is invisible. If it is not, a dialog says
        which file is being read and offers Stop.

        WHAT STOP REALLY DOES, said plainly rather than implied: for a profile
        going through ArgyllCMS it ends that program, which is the case worth
        stopping. For everything else -- a measurement, a picture -- the work
        is arithmetic in this process and cannot be interrupted part way; the
        window stops waiting and lets it finish into nothing. That is why the
        button is only offered where it can keep its word.
        """
        import threading
        import time as _time

        outcome: dict = {}
        stop = threading.Event()

        def work():
            try:
                outcome["got"] = self._build_one(path, stop=stop)
            except BaseException as exc:                  # noqa: BLE001
                outcome["trouble"] = exc

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        thread.join(self.PATIENCE_BEFORE_SAYING)
        progress = None
        try:
            while thread.is_alive():
                if progress is None:
                    progress = QProgressDialog(
                        f"Reading {path.name}…\n\nThis one is taking longer "
                        f"than usual. ArgyllCMS is sometimes slow on a "
                        f"profile it does not care for; the file will still "
                        f"open, read directly, if it gives up.",
                        "Stop", 0, 0, self)
                    progress.setWindowTitle("Opening")
                    progress.setWindowModality(
                        Qt.WindowModality.WindowModal)
                    progress.setMinimumDuration(0)
                    progress.setAutoClose(False)
                    progress.setAutoReset(False)
                    progress.show()
                if progress.wasCanceled() and not stop.is_set():
                    stop.set()
                    progress.setLabelText(
                        f"Stopping…\n\nWaiting for ArgyllCMS to let go of "
                        f"{path.name}.")
                QApplication.processEvents()
                _time.sleep(0.02)
        finally:
            if progress is not None:
                progress.close()
        thread.join()
        if "trouble" in outcome:
            raise outcome["trouble"]
        return outcome["got"]

    def _build_one(self, path: Path, stop=None, space=None):
        """The gamut of one file, whichever kind it is.

        A profile has no patches, so there is no Measurement to return with
        it -- everything downstream treats that None as "this one was not
        measured" rather than assuming a chart.

        *stop* is passed to the one reader that can honour it -- ArgyllCMS is
        a separate program and can be ended. The rest is arithmetic here and
        runs to completion whatever happens; see `_build_patiently`.
        """
        suffix = path.suffix.lower()
        if suffix in (".icc", ".icm", ".gam"):
            reader = gam_gamut if suffix == ".gam" else icc_gamut
            return reader(path, white_point=self._white.currentData(),
                          space=space or self._build_space(), stop=stop), None
        if suffix in IMAGE_EXTENSIONS:
            from imagegamut import image_gamut
            built, facts = image_gamut(
                path, white_point=self._white.currentData(),
                space=self._build_space())
            self._image_facts[str(path)] = facts
            return built, None
        m = read_measurement(path, self._white.currentData(),
                             self._relative.isChecked())
        drive = None if self._mode.currentData() == "hull" else m.device
        g = build_gamut(m.lab, drive, input_space="lab",
                        space=self._build_space(),
                        white_point=self._white.currentData())
        return g, m

    #: Below this many patches a measured chart cannot describe the edge of a
    #: printer in any useful way: the shape collapses towards a flat sliver and
    #: two different small charts look alike. Chosen because a chart that even
    #: samples each of the three channels at 4 levels is 64 patches, and real
    #: profiling charts start in the hundreds.
    TOO_FEW_PATCHES = 60

    def _warn_if_too_few_patches(self, path: Path, m) -> None:
        """Say plainly when a chart is too small to mean anything.

        Drawing a gamut from a handful of patches produces a shape that looks
        plausible and is not: it is the hull of a few dots, not the edge of a
        printer. Two such charts look alike whatever printer made them, which
        is exactly how this went unnoticed. Better to say so than to let
        somebody compare two meaningless shapes and believe the answer.
        """
        if m is None or m.n_patches >= self.TOO_FEW_PATCHES:
            return                 # a profile has no patches to count
        patches = "1 patch" if m.n_patches == 1 else f"{m.n_patches} patches"
        Notice.say(
            self, "This chart is very small",
            f"{path.name} holds only {patches}.\n\n"
            "That is too few to show what a printer can really print. The "
            "shape drawn from it is the outline of a handful of dots rather "
            "than the edge of your printer, and two small charts will look "
            "much the same however different the printers were.\n\n"
            "It is still drawn, in case that is what you wanted — a partly "
            "measured chart, or a small verification chart, will look like "
            "this. For a true picture, open a full profiling measurement: "
            "those usually hold several hundred patches or more.")

    #: How long the handle must be still before the picture catches up, in
    #: milliseconds. Not tuned by feel: it has to be longer than a step of an
    #: ordinary drag (so a sweep across the slider does not queue up twenty
    #: rebuilds) and shorter than a pause a person would call a wait.
    DETAIL_SETTLES_AFTER = 150

    def _on_cut_changed(self, value: int) -> None:
        """Move the cross-section as the handle moves. No waiting at all.

        The cheapest of the live controls by a long way -- **7 ms** to work
        out, three traces, 363 points -- so unlike Detail this needs no pause
        to hide behind and fires on every step.

        A CUT IS DRAWN TO FILL ITS FRAME, so the axes move with it and the
        caption names the height. Those travel too; see `frame_for_relayout`.
        Sending the outlines alone would draw the new cut inside the old
        frame, which reads as the shape sliding sideways rather than the
        reader moving the cut.
        """
        self._slice_lbl.setText(f"L* {value}")
        self._push_cut()

    def _push_cut(self) -> bool:
        self._cut_live = False
        view = getattr(self, "_view", None)
        page = view.page() if view is not None else None
        if page is None or getattr(self, "_run_drawn", False):
            return False
        # ONLY THE ONE ARRANGEMENT THIS WAS WORKED OUT FOR. Two cuts side by
        # side are two pictures; the tick being off means there is no cut on
        # screen at all. Both fall back to the rebuild that has always worked.
        if not self._slice_on.isChecked() or self._side_by_side.isChecked():
            return False
        gamuts, _clouds, _styles, _lost = self._scene_contents()
        if not gamuts:
            return False
        from ti3gamut import (build_slice_figure, frame_for_relayout,
                              traces_for_restyle)

        try:
            figure = build_slice_figure(
                gamuts, float(self._slice_at.value()), self._scene_title(),
                self._appearance, extent=None, slidable=False)
        except Exception:                  # noqa: BLE001 — never on a drag
            return False
        wanted = traces_for_restyle(figure)
        if not wanted:
            return False

        def answered(ok):
            self._cut_live = bool(ok)

        page.runJavaScript(
            f"(function(want,frame){{{_DETAIL_JS}}})"
            f"({json.dumps(wanted)},"
            f"{json.dumps(frame_for_relayout(figure))})", answered)
        return True

    def _after_cut(self) -> None:
        """Letting go of the cross-section: rebuild only if the push missed.

        AND NOT AT ALL IF IT DID NOT MOVE. This was the one the first pass at
        that guard missed — the fades, the rings and the detail were given it
        and the cut was not, so a press and release on this handle still wrote
        a whole page. Found by the check, in the state it is actually met in:
        a slider nobody has touched since the picture was drawn.
        """
        if self._slice_at.value() == getattr(self, "_drawn_with", {}).get(
                "cut", self._slice_at.value() + 1):
            return
        if getattr(self, "_cut_live", False) and self._push_cut():
            self._update_volume()
            self._update_coverage()
            self._update_drift()
            return
        self._redraw()

    def _on_detail_changed(self, value: int) -> None:
        self._detail_lbl.setText(f"{value} steps")
        self._detail_soon.start(self.DETAIL_SETTLES_AFTER)

    def _push_detail(self) -> bool:
        """Rebuild the comparison and send it into the picture on screen.

        Returns whether it landed, so letting go can rebuild the page when it
        did not -- the same "the page says whether it managed, and a no falls
        through to the redraw that always worked" the rings, the fades and the
        grid tick use.

        IT REFUSES MORE THAN IT ACCEPTS, on purpose. A cross-section, two
        rooms, or a run that owns the view are all pictures this was not
        worked out for, and a push that half-lands on one of them leaves the
        reader looking at a shape that is partly the old detail and partly the
        new -- which nothing on screen would explain. Every one of those falls
        back to the rebuild, which has always been right and is merely slow.
        """
        self._detail_soon.stop()
        self._detail_live = False
        view = getattr(self, "_view", None)
        page = view.page() if view is not None else None
        if page is None or getattr(self, "_run_drawn", False):
            return False
        if self._slice_on.isChecked() or self._side_by_side.isChecked():
            return False
        if self._reference is None:
            # Detail only ever describes the comparison. With none open there
            # is nothing to rebuild and nothing to send.
            return False
        self._rebuild_reference()
        gamuts, clouds, styles, lost = self._scene_contents()
        if len(gamuts) < 1:
            return False
        from ti3gamut import build_figure, traces_for_restyle

        try:
            figure = build_figure(gamuts, self._scene_title(), split=True,
                                  patches=clouds, styles=styles, lost=lost,
                                  **self._render_options())
        except Exception:                  # noqa: BLE001 — never on a drag
            return False
        self._scene_inputs = (list(gamuts), clouds, styles, lost)
        wanted = traces_for_restyle(figure)
        if not wanted:
            return False

        def answered(ok):
            self._detail_live = bool(ok)

        page.runJavaScript(
            f"(function(want,frame){{{_DETAIL_JS}}})"
            f"({json.dumps(wanted)},null)", answered)
        return True

    def _on_detail_released(self) -> None:
        """A finer or rougher comparison — rebuilt, never asked for again.

        THIS SLIDER USED TO OPEN A FILE DIALOG. It was wired straight to
        `_on_compare_changed`, which is the handler for CHOOSING a comparison
        — and choosing one that lives in a file means being asked which file.
        So with a profile, a measurement or a picture as the comparison,
        letting go of Detail put a file chooser on screen (twice, measured)
        asking the reader to find again the very file already drawn in front
        of them. Any answer but the same file silently swapped the comparison;
        Cancel put the box back to "Nothing" and took the shape off the
        screen altogether.

        `_rebuild_reference` is the one for a SETTING that changed, and its
        own docstring says why: it "never opens a file dialog: this runs in
        response to a setting being changed, and being asked for a file again
        because you changed the white point would be baffling". The white
        point and the drawing space have always gone through it. Detail is a
        setting in exactly the same sense and never should have been an
        exception.

        (A comparison read from a file has no detail to change — its shape
        comes from the file. Rebuilding it is a few milliseconds of work that
        changes nothing, which is the right price for having one path that is
        always correct.)

        AND IF THE PICTURE HAS BEEN KEEPING UP, letting go does not rebuild it
        at all — see `_push_detail`. The readings beside it still have to
        follow, because those are worked out in Python and no push can carry
        them.
        """
        if self._detail.value() == getattr(self, "_drawn_with", {}).get(
                "detail", self._detail.value() + 1):
            return          # let go without moving it; see `_write_scene`
        if getattr(self, "_detail_live", False) and self._push_detail():
            self._chart_profile_offer()
            self._update_volume()
            self._update_coverage()
            self._update_drift()
            self._update_chart_numbers()
            return
        self._rebuild_reference()
        self._chart_profile_offer()
        self._redraw()

    def _on_white_changed(self) -> None:
        """A different white point: the charts and the comparison both move.

        Lab and Luv are both defined against a white point, so a comparison
        left in the old one would be a different shape from the charts it is
        drawn beside.
        """
        self._rebuild()
        self._rebuild_reference()
        self._redraw()

    def _on_space_changed(self) -> None:
        """A different space to draw in: everything on screen has to move.

        The charts, the comparison and the numbers are all expressed in the
        chosen space, so rebuilding only the charts would leave a comparison
        sitting in the space it was first built in and quietly compare two
        different geometries.
        """
        self._apply_space_availability()
        self._rebuild()
        self._rebuild_reference()
        self._redraw()

    def _space_dependent_controls(self) -> list:
        """Every control that only works in some spaces, and what each needs.

        THE REGISTRY, and the reason there is one. This used to be a single
        boolean and a hand-written tuple of six widgets, which was correct for
        exactly as long as there were three spaces and nobody added a control.
        A fourth space that can do far less than the other three turns "did
        anyone remember this one?" from a small risk into the likeliest way to
        ship something broken — a slider still live over a picture it cannot
        change, sitting there looking as though it ought to do something.

        So each entry names the capability it needs (see ``gamutview``), and
        ``tests/test_gamutview.py`` walks every interactive control on the
        panel and fails on any that is neither listed here nor named in
        ``SPACE_INDEPENDENT`` below. Adding a control now forces the question
        to be answered rather than leaving it to be noticed.

        ``untick`` marks the ones that must not be left ticked-but-dead: a
        switched-off checkbox that is still ticked describes a picture that is
        not on screen.
        """
        rows = [
            # (widget, capability it needs, untick when unavailable)
            (self._slice_on, "hue_circle", True),
            (self._slice_at, "hue_circle", False),
            (self._rings_on, "hue_circle", True),
            (self._rings, "hue_circle", False),
            (self._neutral, "hue_circle", True),
            (self._ideal_neutral, "hue_circle", True),
            # THE SURFACE CONTROLS, and the line they are on the far side of.
            # What matters is whether a control changes how a surface is
            # DRAWN or what the surface IS. Drawing controls go dead in ink
            # amounts, because nothing is drawn. The ones that change what
            # gets built — how the edge is followed, how finely it is
            # sampled — stay live, because the shapes are still built even
            # while they are not shown, and the patch count in "Are the
            # patches inside?" is measured against them.
            (self._target, "shapes", False),
            (self._style_mine, "shapes", False),
            (self._style_second, "shapes", False),
            (self._style_other, "shapes", False),
            (self._opacity, "shapes", False),
            (self._depth, "shapes", False),
            (self._outline_paint, "shapes", True),
            (self._points, "shapes", True),
            (self._show_lost, "shapes", True),
            (self._agree, "shapes", True),
            (self._differ, "shapes", True),
            (self._side_by_side, "shapes", True),
            (self._manual_light, "shapes", True),
            # A white point is what a colour is read against — still true in
            # ink amounts, where the dots are painted through a profile and
            # counted against a paper. See the capability's note in gamutview.
            (self._white, "white_point", False),
            (self._relative, "white_point", False),
        ]
        # How a surface is painted, and the lighting on it. Registered through
        # the group and the row list they already live in, so adding another
        # radio or another slider is covered without touching this.
        rows += [(b, "shapes", False) for b in self._paint_group.buttons()]
        rows += [(r, "shapes", False) for r in self._light_rows]
        return rows

    #: Whole sections whose controls mean the same thing in every space, so
    #: that the audit does not demand an answer for each theme radio in turn.
    #: Named by the heading a person reads, which is also what they would
    #: search for. Opening and closing files is in here on purpose: a paper
    #: opened while ink amounts are showing still loads, still keeps its
    #: numbers and still counts the chart's patches — it is only not drawn.
    #: Groups whose controls need no ⓘ of their own: they are housekeeping,
    #: or every control in them is a plain named thing whose label already
    #: says the whole of it. Anything not listed here must have an
    #: explanation on the row, and scripts/audit_panel.py enforces it —
    #: added after three sliders shipped with no ⓘ at all.
    NO_HINT_NEEDED = frozenset({
        "This window",
    })

    SPACE_INDEPENDENT_GROUPS = frozenset({
        "What you are looking at",
        "How the shape is worked out",
        "Compare with",
        "A chart to be printed",
        "How the patches are drawn",
        "How much colour it holds",
        "How the two compare",
        "Has anything changed?",
        "Are the patches inside?",
        # Following one device over time asks how far it has MOVED, in ΔE2000
        # between two readings, and that question is the same whichever space
        # the shape beside it happens to be drawn in.
        "One device over time",
        "This window",
        # Neither section has anything to do with the space the shape is
        # drawn in: one writes the picture, the page and the table, the
        # other is housekeeping about the application.
        "Take it away with you",
        "The application itself",
    })

    #: Controls inside a space-dependent section that are nonetheless the same
    #: in every space, each with the reason it is exempt. Attribute names,
    #: because that is what somebody grepping for it would type.
    SPACE_INDEPENDENT = {
        "_space": "the control that chooses the space cannot depend on it",
        "_lost_in_colour": "repaints the out-of-reach faces the shape already "
                           "has; whichever space the shape is drawn in, those "
                           "faces are the same faces",
        "_aspect": "box proportions apply to a cloud of dots as much as to a "
                   "surface",
        "_grid_on": "the box and its grid frame any scene",
        "_spin_on": "turning the view is about the camera, not the contents",
        "_turn_mode": "as _spin_on",
        "_turn_speed": "as _spin_on",
        "_turn_sweep": "as _spin_on",
        "_tilt_mode": "as _spin_on",
        "_tilt_speed": "as _spin_on",
        "_tilt_sweep": "as _spin_on",
        "_link_cameras": "only ever visible with two rooms, which ink amounts "
                         "cannot produce, so it is hidden rather than dead",
        "_detail": "changes how finely a gamut is BUILT, and the shapes are "
                   "still built in ink amounts even though they are not "
                   "drawn — the patch counts are measured against them",
        # The buttons along the bottom of the column, which sit outside any
        # group box. Saving, exporting and the housekeeping links all work on
        # whatever is on screen, whatever space that is.
        "_save": "saves whatever is on screen",
        "_picture": "as _save",
        "_export_btn": "the numbers are the numbers, in any space",
        "_reset_btn": "housekeeping",
        "_glossary_btn": "housekeeping",
        "_argyll_btn": "housekeeping",
        "_ffmpeg_btn": "housekeeping",
        "_update_btn": "housekeeping",
        "_auto_update": "housekeeping",
    }

    def _why_not_in_this_space(self, capability: str) -> str:
        """Plain words for a control that the current space cannot support."""
        space = self._space.currentData()
        if space == "rgb":
            reasons = {
                "hue_circle":
                    "Not available in ink amounts — the axes are how much of "
                    "each ink to lay down, so there is no lightness axis and "
                    "no grey axis to measure from.",
                "shapes":
                    "Not available in ink amounts — nothing is drawn here but "
                    "the chart's own patches. Every RGB printer fills the "
                    "same full cube of ink amounts, so a paper drawn here "
                    "would be true and would tell you nothing.",
                "white_point":
                    "Not available in ink amounts — 70% of an ink is 70% of "
                    "an ink whatever light you look at it under. A white "
                    "point is what a measured colour is read against, and "
                    "these are not measurements.",
            }
            return (reasons.get(capability, "Not available in ink amounts.")
                    + " Choose CIELAB under Draw it in to use this.")
        return ("Not available in CIE XYZ — it has no lightness axis and no "
                "grey axis to measure from. Choose CIELAB or CIELUV under "
                "Draw it in to use this.")

    def _apply_space_availability(self) -> None:
        """Switch off the tools the chosen space cannot support, and say why.

        Driven entirely by the registry above, so that the rule and the list
        of controls it applies to cannot drift apart. Everything comes back
        exactly as it was when a space that supports it is chosen again — the
        values are never rewritten, only the enabled state and the tooltip.
        """
        from gamutview import can_do
        space = self._space.currentData()
        # CAPTURED ONCE, BEFORE ANYTHING IS OVERWRITTEN. A control switched
        # off here has its tooltip replaced by the reason, so re-reading it
        # later would remember the reason as the original and the real help
        # text would be gone for the rest of the session. This runs the first
        # time round, while every tooltip is still the one it was built with.
        if not hasattr(self, "_original_tooltips"):
            self._original_tooltips = {
                w: w.toolTip() for w, _c, _u in
                self._space_dependent_controls()}
        for widget, capability, untick in self._space_dependent_controls():
            ok = can_do(space, capability)
            widget.setEnabled(ok)
            if not ok:
                widget.setToolTip(self._why_not_in_this_space(capability))
            elif widget in self._original_tooltips:
                widget.setToolTip(self._original_tooltips[widget])
            if not ok and untick and hasattr(widget, "setChecked"):
                # Untick rather than leave them ticked-but-dead, so the
                # picture always matches the controls.
                widget.blockSignals(True)
                widget.setChecked(False)
                widget.blockSignals(False)
        self._follow_neutral(can_do(space, "hue_circle")
                             and self._neutral.isChecked())
        self._refresh_chart_panel()
        self._refresh_not_drawn_note()

    def _rebuild_reference(self) -> None:
        """Rebuild the comparison in the current space and white point.

        Silent about a comparison that is simply not set, and never opens a
        file dialog: this runs in response to a setting being changed, and
        being asked for a file again because you changed the white point
        would be baffling.
        """
        choice = self._compare.currentData()
        if choice is None:
            return
        try:
            if choice[0] == "space":
                self._reference = (choice[1], reference_gamut(
                    choice[1], white_point=self._white.currentData(),
                    steps=self._detail.value(),
                    space=self._build_space()))
            elif choice[0] == "icc" and self._reference_path is not None:
                path = self._reference_path
                reader = (gam_gamut if path.suffix.lower() == ".gam"
                          else icc_gamut)
                self._reference = (_profile_label(path), reader(
                    path, white_point=self._white.currentData(),
                    space=self._build_space()))
            elif choice[0] == "visible":
                v, _f = optimal_colour_solid(
                    "D50" if self._white.currentData() == "D50" else "D65",
                    max(24, self._detail.value() * 3))
                lab = xyz_to_lab(v, self._white.currentData())
                self._reference = ("Every visible colour", build_gamut(
                    lab, input_space="lab", space=self._build_space(),
                    white_point=self._white.currentData()))
        except Exception as exc:      # noqa: BLE001 — always explain
            Notice.warn(self, "That comparison could not be rebuilt", str(exc))
            self._reference = None
            self._compare.setCurrentIndex(0)

    def _rebuild(self) -> None:
        """A setting that changes the shape — rebuild every loaded measurement."""
        if not self._slots:
            return
        rebuilt = []
        for path, _g, _m in self._slots:
            try:
                g, m = self._build_patiently(path)
                rebuilt.append((path, g, m))
            except Exception as exc:            # noqa: BLE001
                Notice.warn(self, "That setting cannot be used here",
                                    f"{path.name}\n\n{exc}")
                return
        self._slots = rebuilt
        self._refresh_slot_labels()
        self._redraw()

    def _refresh_argyll(self) -> None:
        """Say where things stand, without making it sound like a problem."""
        import argyll
        argyll.forget()
        got = argyll.status()
        self._argyll_label.setText(argyll.summary())
        self._argyll_btn.setText("Where ArgyllCMS is…" if got["found"]
                                 else "Find or get ArgyllCMS…")
        self._argyll_label.setToolTip(got["folder"] or "")

    def _on_choose_argyll(self) -> None:
        """Point the viewer at ArgyllCMS, or at the page to download it from.

        Offered rather than demanded. Somebody who does not have it is not
        stuck: everything except three file types works without it, so this
        never blocks anything, and the wording says so.
        """
        import argyll
        got = argyll.status()
        if not got["found"]:
            wanted = Notice.ask(
                self, "ArgyllCMS was not found",
                "Nothing is broken. Your measurements, gamut files and ICC "
                "profiles all open without it — only .cxf, .mxf and .txt "
                "files are converted by it.\n\n"
                "If you have not got it, it is free, and it is the same "
                "toolkit that reads a printed chart in the first place.\n\n"
                "If you have got it and it simply lives somewhere unusual, "
                "choose the folder you installed it into — either the "
                "ArgyllCMS folder itself or the bin folder inside it, "
                "whichever you find first.\n\n"
                + self._where_it_looked(),
                yes="Open the download page", no="Choose the folder…")
            if wanted:
                QDesktopServices.openUrl(QUrl(argyll.DOWNLOAD_URL))
                return
        start = got["folder"] or str(Path.home())
        # THE OPTION HAS TO BE PASSED HERE TOO. This is a static convenience
        # method rather than the shared factory, so it does not inherit
        # anything from it — left alone it opens the system's own folder
        # chooser while every other dialog in the window is ours, which is a
        # difference somebody notices without being able to say what it is.
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose the folder holding the ArgyllCMS tools", start,
            QFileDialog.Option.DontUseNativeDialog
            | QFileDialog.Option.ShowDirsOnly)
        if not chosen:
            return
        # EITHER FOLDER IS ACCEPTED. Somebody who picks /Applications/Argyll
        # has picked the right thing by every reasonable reading — `bin` is our
        # detail, not theirs — so the bin folder inside it is found for them
        # rather than being demanded of them.
        holding = argyll.tools_folder(chosen)
        if holding is None:
            # TURNED DOWN NOW rather than at the moment a file fails to open,
            # which would be a puzzle days later in a different part of the app.
            Notice.warn(
                self, "That folder does not hold the tools",
                f"None of the ArgyllCMS programs are in:\n{chosen}\n\n"
                "The folder to choose is the ArgyllCMS folder itself, or the "
                "bin folder inside it — the one with the programs in it, "
                "iccgamut and cxf2ti3 and the rest. Either will do.\n\n"
                + self._not_runnable_note()
                + "Nothing has been changed.")
            return
        holding = str(holding)
        self._store.setValue("argyll_folder", holding)
        argyll.set_folder(holding)
        self._refresh_argyll()
        Notice.say(self, "That is where it will look",
                   f"ArgyllCMS will be used from:\n{holding}\n\n"
                   "Every file type can be opened now.")

    @staticmethod
    def _where_it_looked() -> str:
        """The folders the search covered, for the "not found" message.

        Named rather than summarised, and capped rather than complete: a wall
        of paths is not read by anybody. The point is to let somebody see at a
        glance that the obvious place was already tried, so they reach for the
        button instead of arguing with the message.

        KEPT NARROW ON PURPOSE. This box is a fixed 470 points wide, and a
        wrapping label asks for room enough for its longest line — so paths
        are written the short way, and the reason they are searched is said
        once above the list rather than repeated on every line. Spelled out in
        full it cost the dialog 597 points of width and cut the buttons off.
        """
        import argyll

        def listed(folders, limit):
            shown = folders[:limit]
            more = len(folders) - len(shown)
            # A bare ~ is the home folder, and reads as a stray mark on its own
            # line to anybody who has not met the shorthand.
            lines = "\n".join(f"    {'~ (your home folder)' if w == '~' else w}"
                              for w in shown)
            return lines + (f"\n    …and {more} more" if more > 0 else "")

        roots, tools = argyll.searched_places()
        said = "It looked on your PATH"
        if roots:
            said += (",\nand for a folder whose name starts with “Argyll” in:\n"
                     + listed(roots, 6))
        if tools:
            said += "\nas well as the usual tool folders:\n" + listed(tools, 4)
        return said + "\n"

    @staticmethod
    def _not_runnable_note() -> str:
        """Said only when it applies: the tools are there but have no
        permission to run, which reads as "missing" and is not.

        This is a real way to end up stuck rather than a hypothetical one — a
        zip unpacked by a tool that does not carry Unix permissions leaves
        every program in place and none of them runnable.
        """
        import argyll
        stuck = argyll.found_but_not_runnable()
        if not stuck:
            return ""
        return ("One thing worth knowing: the ArgyllCMS programs WERE found "
                f"here, but your system will not run them —\n    {stuck[0]}\n"
                "That usually means the download was unpacked by something "
                "that dropped their permission to run. Unpacking it again "
                "with your system's own unzip normally fixes it.\n\n")

    def _look_after_appearance(self) -> None:
        """Dark or light was switched, so the page follows — unless a look of
        the person's own is being shown, which is theirs and stays put."""
        if getattr(self, "_looks_panel", None) is not None:
            self._set_page_backgrounds(self._page_view())

    def _refresh_ffmpeg(self) -> None:
        """Say where the encoder stands, without making it sound like a fault."""
        movie.forget()
        got = movie.status()
        self._ffmpeg_label.setText(movie.summary())
        self._ffmpeg_btn.setText("Where ffmpeg is…" if got["found"]
                                 else "Find or get ffmpeg…")
        self._ffmpeg_label.setToolTip(got["path"] or "")

    def _on_choose_ffmpeg(self) -> None:
        """Point the viewer at an ffmpeg, or at the page to download one from.

        A FILE, NOT A FOLDER, and that is the difference from the ArgyllCMS
        button beside it: ArgyllCMS is a folder of many tools, while this is
        one program. Asking for the right thing is worth more than making the
        two buttons look alike.
        """
        got = movie.status()
        if not got["found"]:
            wanted = Notice.ask(
                self, "No ffmpeg was found",
                "Nothing is broken. Every file still opens, still pictures "
                "still save, and WebP, GIF and APNG moving pictures are made "
                "here without it. Only the MP4 and WebM films need it.\n\n"
                "A copy normally travels with this application. If it is not "
                "there, it is free and every system has a build.\n\n"
                "If you already have one and it simply lives somewhere "
                "unusual, choose the ffmpeg program itself instead.",
                yes="Open the download page", no="Choose the program…")
            if wanted:
                QDesktopServices.openUrl(QUrl(movie.DOWNLOAD_URL))
                return
        start = str(Path(got["path"]).parent) if got["path"] else str(Path.home())
        chooser = self._file_dialog("Choose the ffmpeg program",
                                    QFileDialog.FileMode.ExistingFile,
                                    "Every program (*)", profiles=False)
        chooser.setDirectory(start)
        if not chooser.exec():
            return
        chosen = chooser.selectedFiles()[0]
        if not movie.looks_like_ffmpeg(chosen):
            # TURNED DOWN NOW rather than at the end of a two-minute export,
            # which is where the mistake would otherwise surface.
            Notice.warn(
                self, "That is not an ffmpeg",
                f"This does not answer as ffmpeg does:\n{chosen}\n\n"
                "The one to choose is the program called ffmpeg itself — not "
                "ffplay, not ffprobe, and not the folder it sits in.\n\n"
                "Nothing has been changed.")
            return
        self._store.setValue("ffmpeg_path", chosen)
        movie.set_path(chosen)
        self._refresh_ffmpeg()
        kinds = ", ".join(movie.CODEC_NAMES[c]
                          for c in movie.status()["codecs"]) or "none"
        Notice.say(self, "That is the one it will use",
                   f"Films will be made with:\n{chosen}\n\n"
                   f"It can write: {kinds}.")

    def _axis_controls(self, group, into, name: str, why: str,
                       speed_default: int, sweep_default: int,
                       sweep_range, start_off: bool = False):
        """One direction of movement: how it moves, how fast, and how far.

        Both directions are built from this so they cannot drift apart in
        wording, in layout or in behaviour -- two hand-written copies of the
        same three rows is how one of them ends up with a control the other
        never got.
        """
        holder = QWidget(group)
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.setSpacing(4)
        mode = NoScrollComboBox(group)
        mode.addItem("not at all", "off")
        mode.addItem("back and forth", "swing")
        mode.addItem("all the way round", "round")
        mode.setCurrentIndex(0 if start_off else 1)
        mode.currentIndexChanged.connect(self._on_spin_changed)
        mode_name = QLabel(name, group)
        mode_row = QWidget(holder)
        row = QHBoxLayout(mode_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(mode_name)
        row.addWidget(mode, 1)
        hint = Hint(why, group)
        hint.setObjectName(f"hint_axis_{name.split()[0].lower()}_hint")
        row.addWidget(hint, 0, Qt.AlignmentFlag.AlignVCenter)
        holder_layout.addWidget(mode_row)

        speed = NoScrollSlider(Qt.Orientation.Horizontal, group)
        speed.setRange(2, 30)
        speed.setValue(speed_default)
        speed.valueChanged.connect(self._on_spin_changed)
        speed_name = QLabel("How fast", group)
        speed_value = QLabel("", group)
        speed_value.setMinimumWidth(88)
        speed_holder = QWidget(holder)
        speed_row = QHBoxLayout(speed_holder)
        speed_row.setContentsMargins(0, 0, 0, 0)
        speed_row.setSpacing(6)
        speed_row.addWidget(speed_name)
        speed_row.addWidget(speed, 1)
        speed_row.addWidget(speed_value)
        speed_hint = Hint(
            f"How quickly it moves {name.lower()}. The number beside the "
            "slider says it the way that is easiest to picture: how long one "
            "full turn takes, or how long it takes to travel across and "
            "back.\n\n"
            "Slower is usually better. A gentle drift lets you follow one "
            "part of the surface as it comes round; anything hurried is "
            "harder to read and tiring to watch. If you are unsure, leave it "
            "and lower it if the movement feels busy.\n\n"
            "This direction keeps its own speed, so you can have a slow tip "
            "up and down against a quicker turn — or the other way about.",
            group)
        speed_hint.setObjectName(f"hint_axis_{name.split()[0].lower()}_speed")
        speed_row.addWidget(speed_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        holder_layout.addWidget(speed_holder)

        sweep = NoScrollSlider(Qt.Orientation.Horizontal, group)
        sweep.setRange(*sweep_range)
        sweep.setValue(sweep_default)
        sweep.valueChanged.connect(self._on_spin_changed)
        sweep_name = QLabel("How far", group)
        sweep_value = QLabel("", group)
        sweep_value.setMinimumWidth(88)
        sweep_holder = QWidget(holder)
        sweep_row = QHBoxLayout(sweep_holder)
        sweep_row.setContentsMargins(0, 0, 0, 0)
        sweep_row.setSpacing(6)
        sweep_row.addWidget(sweep_name)
        sweep_row.addWidget(sweep, 1)
        sweep_row.addWidget(sweep_value)
        sweep_hint = Hint(
            f"How wide the movement is when it is going back and forth "
            f"{name.lower()}.\n\n"
            "A narrow travel of 30° or so is a nudge: enough movement to "
            "bring out the dents and hollows while the shape stays almost "
            "still and stays facing you. A wide one shows much more of the "
            "surface, at the cost of carrying the shape well away from the "
            "angle you set.\n\n"
            "This has no effect when it is going all the way round, so it is "
            "hidden then.", group)
        sweep_hint.setObjectName(f"hint_axis_{name.split()[0].lower()}_sweep")
        sweep_row.addWidget(sweep_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        holder_layout.addWidget(sweep_holder)
        into.addWidget(holder)

        # Each row is shown or hidden whole. The ⓘ is not listed: it already
        # follows the control it sits beside.
        self._spin_rows.append({
            "mode": mode,
            "holder": holder,
            "mode_row": [mode_row],
            "speed_row": [speed_holder],
            "sweep_row": [sweep_holder],
            "speed_value": speed_value, "sweep_value": sweep_value,
            "speed": speed, "sweep": sweep,
        })
        self._name_extras.append(mode_name)
        return mode, speed, sweep

    def _watch_the_camera(self) -> None:
        """Keep track of where the reader is looking, from the page itself.

        THERE IS NO OTHER WAY TO KNOW. The camera lives in the browser: it
        moves when somebody drags the shape, and nothing tells this side of
        the window that it has. So it is asked, a few times a second, and the
        answer is kept for the next time a page has to be written.

        DURING A DRAG THE REAL CAMERA IS INTERNAL. `layout.scene.camera` is
        only brought up to date when the drawing library relayouts, so a
        picture asked mid-turn answers with where the shape USED to be; the
        scene object underneath it knows the truth. Both are tried, in that
        order, which is the same thing the page's own movement script does.
        """
        page = self._view.page() if self._view is not None else None
        if page is None:
            return
        # NOT WHILE THE PICTURE IS TURNING ITSELF. A camera caught mid-swing
        # is not a viewpoint anybody chose, and writing it into the next page
        # makes the same view come out at a different angle every time it is
        # written -- which would have made every documentation page and every
        # saved sample differ from run to run for no reason a reader could
        # see. What a person drags to is theirs; what the animation is doing
        # this second is not.
        if getattr(self, "_spin_on", None) is not None \
                and self._spin_on.isChecked():
            return

        def keep(raw):
            if not raw:
                return
            try:
                got = json.loads(raw)
            except (TypeError, ValueError):
                return
            if not (isinstance(got, dict) and got.get("eye")):
                return
            # WHICH WAY IS UP IS NOT THE READER'S VIEWPOINT, and carrying it
            # over was a fault waiting to be seen. A tilt that swings over the
            # top of the shape leaves the scene's "up" pointing DOWN -- caught
            # in a saved page as up = (-0.14, -0.37, -0.92) -- and a page
            # opened that way is upside down and drags backwards in both
            # directions. Which is exactly what was reported while this was
            # being built: "when clicking and dragging the shape move in the
            # opposite direction i would expect ... both for up/down and
            # left/right", and then "now this works again for whatever
            # reason" -- the reason being a rebuild that threw the flipped
            # camera away.
            #
            # The eye is what somebody chooses by dragging; up is world-up and
            # stays world-up. Dragging never rolls the scene, so nothing a
            # reader can do is lost by pinning it.
            self._camera = {"eye": got["eye"],
                            "center": got.get("center",
                                              {"x": 0, "y": 0, "z": 0}),
                            "up": {"x": 0, "y": 0, "z": 1}}

        page.runJavaScript(
            "(function(){var d=document.getElementsByClassName("
            "'plotly-graph-div')[0];if(!d)return '';var c=null;"
            "try{var s=d._fullLayout&&d._fullLayout.scene&&"
            "d._fullLayout.scene._scene;if(s&&s.getCamera)c=s.getCamera();}"
            "catch(e){}"
            "if(!c)c=d.layout&&d.layout.scene&&d.layout.scene.camera;"
            "return c?JSON.stringify(c):'';})();", keep)

    def _camera_now(self):
        """The camera to write into the next page, or None for the default.

        A CROSS-SECTION HAS NONE, and neither has a window with nothing in it
        yet -- in both cases the last remembered angle is exactly right to
        keep, because it is where the reader will be put back when a shape
        returns.
        """
        # ASKED WITH getattr BECAUSE THIS IS REACHED FROM A STUB. Three
        # tests call _spin_options against an object that stands in for the
        # window and has no camera at all; a plain attribute made them fail
        # for a reason that has nothing to do with what they check.
        return getattr(self, "_camera", None)

    def _spin_options(self, glide: bool = False,
                      saved: bool = False) -> dict:
        """What the page's turning engine should be doing, right now.

        *glide* is the one setting here that is NOT a reading of this window:
        this window has no momentum, because a shape dragged with a mouse on a
        desktop is not what it is for. It is a choice made when a page is
        saved, and it defaults to off so that every path that does not ask for
        it -- the live view above all -- behaves exactly as it always has.
        """
        return dict(
            on=self._spin_on.isChecked(),
            glide=bool(glide),
            # THIS PAGE'S CAMERA CAME FROM THE LAST ONE, so the page must not
            # fit it again -- see the note beside fitAll. Only true for the
            # window's own view, and only once there is a camera to carry:
            # the first draw of a session is a fresh page like any other.
            #
            # AND *SAVED* IS THE OTHER HALF OF THAT SENTENCE, which was
            # missing. This asked only whether THIS WINDOW has a camera, which
            # it always has once anything is drawn -- so every page anybody
            # saved said "already placed" and switched off the fitting whose
            # entire purpose is a window whose shape nobody knew when the page
            # was written. Measured: a two-room page opened at 390, 620 and
            # 1440 px put its eye at 2.598 every time, the written distance,
            # never fitted -- and the shapes came through the side walls of
            # their rooms at every viewpoint. The reader's copy is a fresh
            # page and must fit itself; only the live view carries a camera
            # forward.
            placed=(self._camera_now() is not None) and not saved,
            turn=dict(mode=self._turn_mode.currentData(),
                      speed=float(self._turn_speed.value()),
                      range=float(self._turn_sweep.value())),
            tilt=dict(mode=self._tilt_mode.currentData(),
                      speed=float(self._tilt_speed.value()),
                      range=float(self._tilt_sweep.value())))

    def _on_spin_changed(self, *_args) -> None:
        """A movement control moved.

        Deliberately NOT a redraw. Every other control here rebuilds the page
        and loads it again, which would throw away the viewpoint and restart
        the movement on every nudge of a speed slider -- the control would be
        fighting the thing it controls. The engine is already in the page, so
        the new settings are handed to it where it stands.
        """
        self._update_spin_labels()
        self._apply_spin_availability()
        self._push_spin()

    def _update_spin_labels(self) -> None:
        """Say each speed as a length of time, which is what a person can picture.

        Degrees per second means nothing to most people. "45 s a turn" means
        exactly what it says, and a swing is quoted for the whole journey --
        across and back -- because that is the movement you actually watch.
        """
        for axis in self._spin_rows:
            speed = max(1, axis["speed"].value())
            sweep = axis["sweep"].value()
            if axis["mode"].currentData() == "round":
                axis["speed_value"].setText(f"{round(360 / speed)} s a turn")
            else:
                # A sine sweep: the setting is the peak rate, so one complete
                # there-and-back takes pi x travel / peak.
                axis["speed_value"].setText(
                    f"{round(math.pi * sweep / speed)} s a swing")
            axis["sweep_value"].setText(f"{sweep}° wide")

    #: What a flat cross-section has no use for, with the reason each one is
    #: dead there. MEASURED rather than reasoned: every shape control was
    #: touched with a cut on screen and the page asked what changed. Rings,
    #: the styles, both fade sliders, the box and the measured patches all
    #: change a cut; these three do not, because build_slice_figure draws
    #: outlines and takes no opacity and no light at all.
    NOTHING_TO_ACT_ON_IN_A_CUT = (
        "A cross-section is drawn flat, as outlines: there is no surface to "
        "make more or less solid and no light falling on one. Switch off "
        "Slice it at one lightness to use this.")

    def _apply_flat_availability(self) -> None:
        """Grey out what a cross-section cannot use.

        The window's own rule, stated where two rooms are handled: a control
        that cannot do anything is worse than a missing one, because it
        invites a change and answers with nothing. Three of them survived into
        the flat view -- how solid, how deep the shading, and the whole manual
        light block.

        GREYED RATHER THAN HIDDEN, which is the other half of the same rule
        and the choice already made for the neutral line: it stays visible so
        it is clear the setting exists, and its tooltip says which switch
        brings it back.
        """
        flat = self._slice_on.isChecked()
        for widget in (self._opacity, self._opacity_lbl, self._opacity_name,
                       self._depth, self._depth_lbl, self._depth_name,
                       self._manual_light):
            widget.setEnabled(not flat)
            if flat:
                if not widget.property("cq_tip_when_live"):
                    widget.setProperty("cq_tip_when_live", widget.toolTip())
                widget.setToolTip(self.NOTHING_TO_ACT_ON_IN_A_CUT)
            else:
                was = widget.property("cq_tip_when_live")
                if was is not None:
                    widget.setToolTip(str(was))
        for slider, _lo, _hi in self._light_sliders.values():
            slider.setEnabled(not flat)

    def _apply_spin_availability(self) -> None:
        """Show only what applies, and nothing that does not.

        The slice view is drawn flat, looking down: there is no camera to
        move, so the whole block goes rather than sitting there inviting a
        change that would do nothing. A direction that is set to not at all
        needs neither a speed nor a distance, and how far means nothing to
        something going all the way round.
        """
        turnable = not self._slice_on.isChecked()
        running = turnable and self._spin_on.isChecked()
        self._spin_on.setVisible(turnable)
        for axis in self._spin_rows:
            how = axis["mode"].currentData()
            # The container as well, not only the rows inside it: a visible
            # box with everything hidden inside still keeps its own margins,
            # which is where the band of empty space under the last option
            # came from -- two of them, about eighteen pixels each.
            axis["holder"].setVisible(running)
            for widget in axis["mode_row"]:
                widget.setVisible(running)
            for widget in axis["speed_row"]:
                widget.setVisible(running and how != "off")
            for widget in axis["sweep_row"]:
                widget.setVisible(running and how == "swing")

    def _push_spin(self) -> None:
        """Hand the settings to the page that is already loaded."""
        page = self._view.page()
        if page is None:
            return
        import json
        page.runJavaScript(
            "if (window.cqSpin) window.cqSpin.set("
            f"{json.dumps(self._spin_options())});")

    def _tighten_groups(self, column) -> None:   # noqa: D401
        """Take the slack out of the bottom of every group, in one place.

        A group box carries its own padding AND its layout carries margins, so
        the two stack up into a band of empty space under the last control --
        the same amount in every group, which is why it reads as a gap rather
        than as breathing room. Trimming the layout's own bottom margin leaves
        the top and sides alone, so the titles still sit where they did.

        Done for every group at once rather than per group: a number set in
        eight places drifts, and then one section looks wrong for no reason
        anybody can see.
        """
        for group in column.findChildren(QGroupBox):
            layout = group.layout()
            if layout is None:
                continue
            # EMPTY ROWS STILL TAKE UP ROOM. Moving an ⓘ beside the control it
            # explains leaves the row it used to sit in behind, and a layout
            # with nothing in it keeps its margins regardless -- 29px each,
            # three of them, stacked under the last control in one group. They
            # are invisible in every sense except the space they occupy.
            for i in reversed(range(layout.count())):
                inner = layout.itemAt(i).layout()
                if inner is None:
                    continue
                if not any(inner.itemAt(j).widget() is not None
                           for j in range(inner.count())):
                    layout.removeItem(layout.itemAt(i))
            left, top, right, _bottom = layout.getContentsMargins()
            # AND THE BOTTOM IS THE STYLESHEET'S OWN 8, NOT 2 — WHICH CUT A
            # SENTENCE IN HALF FOR EVERY RELEASE UNTIL NOW.
            #
            # Reported from the window with a photograph: "under placed
            # through the small text was cut off but seemingly only in dark
            # mode". It was cut, and the "only in dark" is the clue that
            # names the cause.
            #
            # Qt maps a stylesheet's padding onto the layout's contents
            # margins AT POLISH. QGroupBox is styled `padding: 4px 8px 8px
            # 8px`, so the bottom is 8; this pass ran after that and wrote 2
            # over it, which leaves the last line of a paragraph under the
            # group's own frame. Dark is what the window opens in, so nothing
            # re-polishes and the 2 stands. Switching to light re-polishes,
            # the 8 comes back, and the sentence is whole again — which is
            # exactly what makes it look like a dark-mode fault.
            #
            # MEASURED, in the real window, with the chart open and the
            # paragraph under "Placed through" at four lines:
            #
            #     bottom 2   last line cut through the middle
            #     bottom 5   still cut
            #     bottom 8   whole, in both appearances
            #
            # So it takes the style's own number rather than the smallest one
            # that happens to work at this font and this screen. What this
            # pass was really for -- the three empty rows above, 29 px each,
            # left behind when an ⓘ moved -- is untouched and is where the
            # space it was reclaiming actually was.
            layout.setContentsMargins(left, top, right, 8)
            # NEVER TALLER THAN WHAT IS IN IT. A group will otherwise take any
            # spare height the column hands out, which shows as a band of
            # nothing under the last control -- and the band grows as options
            # are hidden, which is exactly when it is most noticeable.
            layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
            group.setSizePolicy(QSizePolicy.Policy.Preferred,
                                QSizePolicy.Policy.Maximum)
            # A nested layout at the very bottom carries its own margin on top
            # of the group's, which is why one section kept six pixels more
            # than the rest after the group itself had been trimmed.
            last = layout.itemAt(layout.count() - 1) if layout.count() else None
            inner = last.layout() if last is not None else None
            if inner is not None:
                l2, t2, r2, _b2 = inner.getContentsMargins()
                inner.setContentsMargins(l2, t2, r2, 0)

    def _align_names(self) -> None:
        """Give every drop-down name in How it looks the same column width.

        The rows are built in separate layouts -- some have a slider between
        them -- so nothing lines them up on its own. Taking the widest name and
        making it the floor for all of them puts every box on the same edge,
        and costs the boxes only as much width as the longest name needs.

        Run again after the window is shown: a stylesheet is applied at polish,
        which is after these were first measured, and a name that gained
        padding in between would otherwise size the column from a stale number.
        """
        if not getattr(self, "_name_column", None):
            return
        widest = max(label.sizeHint().width() for label in self._name_column)
        for label in self._name_column:
            label.setMinimumWidth(widest)

    def _name_the_shapes_being_styled(self) -> None:
        """Say WHICH shapes "Set this for" is talking about.

        The entries are written for the window's own two files -- "the first
        shape", "the second shape" -- and while a run owns the picture those
        are the run's two profiles instead. Nobody should have to work out
        that "the first shape" now means printer-2019.
        """
        panel = getattr(self, "_timeline", None)
        showing = (getattr(self, "_run_drawn", False) and panel is not None
                   and panel.shows_two_shapes())
        pair = panel._chosen_pair() if showing else None
        names = ("the first shape", "the second shape")
        if pair is not None:
            names = (panel._name_in_run(pair[0]), panel._name_in_run(pair[1]))
        for at, name in zip((1, 2), names):
            if self._target.itemData(at) in (0, 1):
                self._target.setItemText(at, name)
        # THE COMPARISON'S OWN ENTRY IS NOT A RUN'S SHAPE, so it says so
        # rather than sitting there meaning nothing.
        third = self._target.findData(2)
        if third >= 0:
            self._target.setItemText(
                third, "the comparison" if not showing
                else "the comparison (not in this picture)")

    def _refresh_style_controls(self) -> None:
        """Show a style control only when the shape it governs is on screen.

        A control for something that does not exist is worse than no control:
        it invites a change that does nothing and leaves somebody wondering
        what they did wrong.
        """
        self._name_the_shapes_being_styled()
        panel = getattr(self, "_timeline", None)
        two_shells = (getattr(self, "_run_drawn", False) and panel is not None
                      and panel.shows_two_shapes())
        have = (len(self._slots) >= 1 or two_shells,
                len(self._slots) >= 2 or two_shells,
                self._reference is not None)
        for (combo, _label), name, show in zip(self._style_combos,
                                               self._style_labels, have):
            combo.setVisible(show)
            name.setVisible(show)      # or the word is left behind on its own

    def _refresh_not_drawn_note(self) -> None:
        """Say when something open is deliberately not in the picture.

        Ink amounts draw a chart and nothing else, which is the whole design —
        every RGB printer fills the same cube of ink amounts, so a paper drawn
        there would be true and would say nothing. But a paper listed in this
        very group and absent from both the picture and the legend reads as a
        fault, and nothing on screen said otherwise.

        It names what is missing and what to do about it, and it says the
        numbers are unaffected — because "is it still being counted?" is the
        next question anybody would ask.
        """
        open_shapes = len(self._slots) + (1 if self._reference is not None
                                          else 0)
        if not self._drawing_in_ink() or not open_shapes:
            self._not_drawn_note.setText("")
            return
        names = [p.stem for p, _g, _m in self._slots]
        if self._reference is not None:
            names.append(self._reference[0])
        listed = (names[0] if len(names) == 1
                  else " and ".join([", ".join(names[:-1]), names[-1]]))
        thing = "is" if len(names) == 1 else "are"
        self._not_drawn_note.setText(
            f"{listed} {thing} open and not drawn here. Ink amounts show a "
            f"chart on its own: every RGB printer fills the same full cube of "
            f"them, so a paper drawn here would be true and would tell you "
            f"nothing. Nothing is lost — the measurements still count the "
            f"chart's patches under Are the patches inside?, and everything "
            f"is drawn again the moment you choose CIELAB under Draw it in.")

    def _refresh_slot_labels(self) -> None:
        # "both" only when there really are two; a button that says the wrong
        # number is a small lie that makes people distrust the rest.
        self._clear_btn.setVisible(len(self._slots) == 2)
        self._refresh_not_drawn_note()
        self._refresh_style_controls()
        for i, row in enumerate(self._slot_rows):
            row.setVisible(i < len(self._slots))
        for i, lab in enumerate(self._slot_labels):
            if i < len(self._slots):
                path, _g, m = self._slots[i]
                if m is None:
                    # NEVER CALL A PROFILE OR A PICTURE A MEASUREMENT. Telling
                    # them apart is what this application is for, so the line
                    # under the name says which one you are looking at.
                    suffix = path.suffix.lower()
                    facts = self._image_facts.get(str(path))
                    if facts is not None:
                        patches = (f"a picture — {facts['colours']:,} colours "
                                   f"in {facts['pixels']:,} pixels")
                        measured = (", read with its own profile"
                                    if facts["profile"] else ", read as sRGB")
                    elif suffix in (".icc", ".icm"):
                        patches = "an ICC profile — what it describes"
                        measured = ", not a measurement"
                    else:
                        patches = "a gamut file — the surface it holds"
                        measured = ", not a measurement"
                else:
                    patches = ("1 patch" if m.n_patches == 1
                               else f"{m.n_patches} patches")
                    measured = (f", measured with your {m.instrument}"
                                if m.instrument else "")
                # A chart name is usually one long token with no spaces, so
                # word wrap cannot break it and the end simply disappears off
                # the edge. Shortening it in the MIDDLE keeps both the part
                # that says which printer and the part that says which paper
                # or date -- the two halves people actually tell files apart
                # by. The full name is on the tooltip.
                # Measure against the column, not against the label: asked
                # during the first layout a label reports a width it has not
                # been given yet, which shortened names that had ample room.
                # THE NAME THE PICTURE USES, so the row, the legend and
                # "Set this for" all say the same thing about the same file.
                names = self._slot_names()
                shown = QFontMetrics(lab.font()).elidedText(
                    names[i] if i < len(names) else path.stem,
                    Qt.TextElideMode.ElideMiddle, _TEXT_WIDTH - 34)
                lab.setText(f"● {shown}\n   {patches}{measured}")
                lab.setToolTip(str(path))
            else:
                # Nothing to say about a slot that holds nothing: an empty
                # placeholder under a real chart reads as if something failed.
                lab.setText("")

    # ------------------------------------------------------------------ drawing
    def _show_placeholder(self) -> None:
        """What the empty view says.

        This is where the explanation of what the app is for belongs, and the
        only place it is needed: once a chart is open the picture makes the
        point far better than a sentence does, and at the top of the control
        column it sat between somebody and the first thing they wanted to
        click.
        """
        c = PALETTES[self._appearance]
        self._view.setHtml(
            "<html><body style='background:" + c["bg"] + ";color:" + c["faint"]
            + ";font:14px -apple-system,Segoe UI,sans-serif;display:flex;"
            "align-items:center;justify-content:center;height:100%;margin:0'>"
            "<div style='text-align:center;max-width:30em;line-height:1.55'>"
            "<div style='font-size:52px;margin-bottom:12px'>◱</div>"
            "<p style='color:" + c["text"] + ";font-size:17px;margin:0 0 14px'>"
            "See what your printer can really print</p>"
            "<p style='margin:0 0 14px'>Open the <b>.ti3</b> file ArgyllCMS "
            "saved when you measured a printed chart, and this draws every "
            "colour that printer actually put on paper — what it really did, "
            "on that paper, on that day, rather than what a profile predicts "
            "it can do.</p>"
            "<p style='margin:0 0 14px'>Use <b>Open a measurement or a "
            "profile</b> on the left, or drag the file onto this window.</p>"
            "<p style='margin:0;font-size:13px'>Got a chart you have not "
            "printed yet — a <b>.ti1</b>, a <b>.ti2</b> or an i1Profiler "
            "target? <b>Open a chart</b> shows where its patches would land, "
            "and counts how many fall outside what your printer can reach.</p>"
            "</div></body></html>")

    def _on_manual_light(self) -> None:
        """Show or hide the five individual lighting controls.

        The Depth slider is the everyday way in: one number for how shaded the
        surface is. These are the same lighting underneath, taken apart for
        anybody who wants a particular look — so turning them on turns Depth
        off rather than having two controls quietly fight each other.
        """
        manual = self._manual_light.isChecked()
        for row in self._light_rows:
            row.setVisible(manual)
        self._depth.setEnabled(not manual)
        self._depth_lbl.setEnabled(not manual)
        if manual:
            self._push_lighting(self._manual_lighting())
        else:
            self._on_depth_changed(self._depth.value())

    #: The two sliders that PLACE the light rather than describe it. Plotly
    #: keeps those apart -- lighting is how a surface answers light,
    #: lightposition is where the lamp stands -- and sending them together
    #: means sending two of them to an attribute that has no such keys.
    LIGHT_IS_PLACED_BY = ("direction", "height")

    def _manual_lighting(self) -> dict:
        """How the surface answers the light, as the sliders stand.

        WITHOUT THE TWO THAT PLACE IT. They were in here, and they were being
        pushed into the scene as `lighting.direction` and `lighting.height` --
        attributes that do not exist, so the drawing library dropped them and
        the two sliders did nothing at all while their own hint promised
        "every one of them moves the picture as you drag".

        Found by the audit that drags every slider and asks the page what
        changed: five of the seven answered and these two did not.
        """
        out = {}
        for key, (slider, lo, hi) in self._light_sliders.items():
            if key in self.LIGHT_IS_PLACED_BY:
                continue
            out[key] = lo + (hi - lo) * slider.value() / 100.0
        return out

    def _push_light_position(self) -> None:
        """Move the lamp in the scene already on screen."""
        page = self._view.page() if self._view is not None else None
        if page is None or not (self._slots
                                or getattr(self, "_run_drawn", False)):
            return
        where = self._light_position()
        body = ",".join(f"'{k}':{float(v)}" for k, v in where.items())
        page.runJavaScript(self._in_every_room(
            "var idx=[];for(var i=0;i<el.data.length;i++)"
            "if(el.data[i].type==='mesh3d')idx.push(i);"
            f"var which={self._which_meshes_js()};"
            f"if(which.length){{Plotly.restyle(el,"
            f"{{lightposition:{{{body}}}}},which);did++;}}"))

    def _on_light_changed(self, key: str, value: float, label) -> None:
        label.setText(f"{value:.2f}")
        if not self._manual_light.isChecked():
            return
        if key in self.LIGHT_IS_PLACED_BY:
            self._push_light_position()
        else:
            self._push_lighting(self._manual_lighting())

    def _in_every_room(self, body: str) -> str:
        """Wrap a live change so it reaches EVERY graph in the page.

        TWO ROOMS ARE TWO GRAPHS, and every live path in this window began

            document.getElementsByClassName('plotly-graph-div')[0]

        which is the left one. Measured, with two papers side by side and the
        solidity dragged to 30%:

            room0 surfaces=0.3 | room1 surfaces=1

        -- two rooms disagreeing about how solid the shapes are, which is the
        one thing that arrangement exists to make comparable. It survived
        because it corrects itself: anything that rebuilds the page draws both
        rooms from the same recorded value. Now that the controls people drag
        no longer rebuild, it would have stayed on screen.

        *body* is written against `el`, one graph at a time.
        """
        return ("(function(){var divs=document.getElementsByClassName("
                "'plotly-graph-div');var did=0;"
                "for(var r=0;r<divs.length;r++){var el=divs[r];"
                "if(!el||!window.Plotly||!el.data)continue;"
                + body +
                "}return did>0;})();")

    def _restyle_the_chart(self, group: str, field: str, value) -> None:
        """Change how the chart's patches are drawn, in the picture on screen.

        THESE FIVE SLIDERS REBUILT THE WHOLE PAGE ON EVERY STEP. Not on
        release -- on every step of the drag, because they were wired to
        `valueChanged`, so a slow drag across a 1,000-patch chart wrote and
        loaded the page dozens of times and the view went black between each
        of them.

        Which traces: the ones in the chart's own legend group, and NOT the
        key beside the name. A key is a key whatever the dots are doing -- a
        restyle that caught the proxies too would shrink and fade the legend
        along with the patches, which is the fault the proxies were added to
        cure in the first place.
        """
        page = self._view.page() if self._view is not None else None
        if page is None:
            return
        import json as _json
        page.runJavaScript(self._in_every_room(
            "var idx=[];for(var i=0;i<el.data.length;i++){var t=el.data[i];"
            f"if(String(t.legendgroup||'').slice(-{len(group) + 1})==='-{group}'"
            "&&t.hoverinfo!=='skip')idx.push(i);}"
            f"if(idx.length){{Plotly.restyle(el,{{{_json.dumps(field)}:"
            f"{_json.dumps(value)}}},idx);did++;}}"))

    def _slot_names(self) -> list:
        """What the open files are CALLED, and never the same thing twice.

        TWO FILES CAN SHARE A NAME. Opening Glossy-paper.ti3 from January and
        Glossy-paper.ti3 from June -- which is exactly how somebody keeps a
        paper measured twice -- put two shapes called Glossy-paper in the
        picture, two identical rows in the list, and two identical keys in the
        legend. Neither the reader nor the window could tell them apart:
        "Set this for: the first shape" faded BOTH, because the live change
        finds its shape by name.

        The folder is what distinguishes them, so the folder is what is added,
        and only to the ones that need it: a name that is already unique is
        left exactly as it was.
        """
        paths = [Path(path) for path, _g, _m in self._slots]
        stems = [path.stem for path in paths]
        names = []
        for path in paths:
            if stems.count(path.stem) == 1:
                names.append(path.stem)
                continue
            # THE FOLDER IS NOT ALWAYS WHAT DIFFERS. Glossy-paper.ti3 and
            # Glossy-paper.icc sit in ONE folder in this project's own demo
            # set -- the measurement and the profile made from it -- so
            # adding the folder to both would have produced the same name
            # twice all over again. What differs is taken in turn: the
            # extension first, because "Glossy-paper.ti3" and
            # "Glossy-paper.icc" is what a person sees in their own folder,
            # and the folder after it.
            others = [other for other in paths if other != path
                      and other.stem == path.stem]
            if all(other.name != path.name for other in others):
                names.append(path.name)
            elif all(other.parent.name != path.parent.name
                     for other in others):
                names.append(f"{path.stem} ({path.parent.name})")
            else:
                names.append(str(path))
        return names

    def _name_of_shape(self, which: int) -> str:
        """What the shape at this position is CALLED in the picture.

        Its position among the surfaces is not the same thing, which is the
        whole reason this exists -- see _which_meshes_js.
        """
        panel = getattr(self, "_timeline", None)
        if getattr(self, "_run_drawn", False) and panel is not None \
                and panel.shows_two_shapes():
            pair = panel._chosen_pair()
            if pair is not None and which in (0, 1):
                return panel._name_in_run(pair[which])
        if which == 2:
            return str(self._reference[0]) if self._reference else ""
        names = self._slot_names()
        if which < len(names):
            return names[which]
        return ""

    def _which_meshes_js(self) -> str:
        """The JavaScript that picks the shapes a live change applies to.

        SET THIS FOR: ONE SHAPE MEANT ALL OF THEM WHILE THE HANDLE WAS DOWN.
        The live restyle changed every surface in the picture and the rebuild
        that followed put the other shapes back -- so the fault was invisible
        as long as there was a rebuild to correct it. Taking the rebuild away
        (which is what stops the view jumping) would have left the wrong
        picture standing, which is how one fix becomes the next bug.

        BY NAME, AND NOT BY POSITION AMONG THE SURFACES, which is the second
        fault and was found by crossing the two controls that decide this
        rather than trying them one at a time. A shape drawn as a mesh has NO
        surface in the picture, so "the second surface" is not the second
        shape -- with one shape solid and the other a mesh, asking for the
        second faded the first:

            first=solid, second=mesh, set this for=the second shape
                the fade should have gone to nothing and went to printer-2019

        Nothing is the right answer there: a wireframe has no solidity to
        change, and the value is still recorded for when it is drawn solid
        again.
        """
        target = self._target.currentData()
        if not isinstance(target, int):
            return "idx"
        name = self._name_of_shape(target)
        if not name:
            return "[]"
        # EXACTLY THE NAME, not a name that starts with it. A prefix match
        # looks equivalent until two files share one: with printer-2019 and
        # printer-2019-again open, asking for the first shape faded both --
        #
        #     faded: ['printer-2019', 'printer-2019-again']
        #
        # and nothing on screen would say why the wrong shape had changed. A
        # surface carries its shape's name and nothing else; the outline, the
        # rings and the chart's skin are separate traces with names of their
        # own, and none of them is a mesh3d belonging to another shape.
        return ("idx.filter(function(n){return String(el.data[n].name||'')"
                f"==={json.dumps(name)};}})")

    def _push_lighting(self, values: dict) -> None:
        """Send a lighting dictionary into the scene already on screen."""
        page = self._view.page()
        # THE RUN'S SHELLS COUNT AS SHAPES ON SCREEN. This asked whether any
        # FILE was open, which was the same question until the run panel began
        # drawing shapes of its own -- and then the live fade stopped happening
        # for exactly the picture that has two shapes in it.
        if page is None or not (self._slots
                                or getattr(self, "_run_drawn", False)):
            return
        body = ",".join(f"'{k}':{v}" for k, v in values.items())
        page.runJavaScript(self._in_every_room(
            "var idx=[];for(var i=0;i<el.data.length;i++)"
            "if(el.data[i].type==='mesh3d')idx.push(i);"
            f"var which={self._which_meshes_js()};"
            f"if(which.length){{Plotly.restyle(el,"
            f"{{lighting:{{{body}}}}},which);did++;}}"))

    def _on_depth_changed(self, value: int) -> None:
        """Change the shading live, without rebuilding the picture.

        The same trick the solidity slider uses: Plotly can restyle a scene
        already on screen, so the shading moves as you drag, the camera stays
        where you put it, and nothing is recomputed.
        """
        self._depth_lbl.setText(f"{value}%")
        d = max(0.0, min(1.0, value / 100.0))
        self._push_lighting(dict(
            ambient=0.95 - 0.45 * d, diffuse=0.10 + 0.75 * d,
            specular=0.02 + 0.18 * d, roughness=0.95 - 0.5 * d,
            fresnel=0.02 + 0.1 * d))




    @staticmethod
    def _fade_words(value: int) -> str:
        """What an agreement handle says beside itself.

        The ends are named rather than numbered, because "100%" and "0%" do
        not say what they do: at the top nothing is hidden at all, and at the
        bottom that part is gone.
        """
        if value == 100:
            return "all of it"
        return "hidden" if value == 0 else f"{value}%"



    def _on_rings_changed(self, value: int) -> None:
        """Restack the rings inside the shapes as the slider moves.

        Reported from the window: "show rings inside slider only updates the
        viewer when i let go from dragging it - should be live", and then, of
        the sliders as a whole, "all sliders should work this way".

        THE GEOMETRY WAS NEVER WHY THIS WAS NOT LIVE. Measured before writing
        a line of it: the rings inside one shape cost 0.9 ms at six of them,
        1.8 ms at thirteen and 2.9 ms at twenty. What cost the time was the
        only path available -- ``_redraw`` writes a whole new page and loads
        it, which is a second of black for a change that is one trace's worth
        of numbers. So this takes the road the solidity and the shading
        already take: work the numbers out here, and push them into the
        picture that is already on screen.

        AND IT IS ONE TRACE, which is what makes that possible. ``_rings``
        strings every cross-section into a single line with a gap between
        them (see the ``None`` separators there), so changing how many rings
        there are changes that trace's points and nothing else -- no trace has
        to be added or taken away, which a restyle could not do.
        """
        self._rings_lbl.setText(str(value))
        # RECORDED ON EVERY STEP, for the reason written out at the solidity
        # slider: the settings are written eagerly precisely because quitting
        # mid-drag is the case they are for, and a record written on release
        # alone parts company with the picture the moment somebody drags and
        # quits.
        self._remember_shape_setting("rings")
        self._push_rings(value)

    def _push_rings(self, count: int) -> None:
        """Send new rings into the scene already on screen.

        Sets ``_rings_live`` from the page's own answer, so that letting go
        rebuilds only when the push could not land -- the same "the page says
        whether it managed, and a no falls through to the redraw that always
        worked" that the grid tick uses.
        """
        self._rings_live = False
        page = self._view.page() if self._view is not None else None
        if page is None or not self._rings_on.isChecked():
            return
        if not (self._slots or getattr(self, "_run_drawn", False)):
            return
        wanted = self._rings_for_live(count)
        if not wanted:
            return

        def answered(ok):
            self._rings_live = bool(ok)

        page.runJavaScript(self._in_every_room(
            f"var want={json.dumps(wanted)};"
            "for(var i=0;i<el.data.length;i++){"
            "var n=String(el.data[i].name||'');"
            "if(!Object.prototype.hasOwnProperty.call(want,n))continue;"
            "Plotly.restyle(el,{x:[want[n][0]],y:[want[n][1]],"
            "z:[want[n][2]]},[i]);did++;}"), answered)

    def _rings_for_live(self, count: int) -> dict:
        """The ring points for every shape this slider currently sets.

        Keyed by the trace's own name, because a trace is found by name and
        never by position -- the reasoning is written out in
        ``_which_meshes_js``, where matching by position faded the wrong
        shape.

        ONLY THE SHAPES THE SLIDER IS SET FOR. With "set this for" naming one
        shape, the others keep the ring counts they were drawn with, and
        pushing this value into them would be the same fault the solidity
        slider had: one shape meant all of them while the handle was down.
        """
        from ti3gamut import _rings

        target = self._target.currentData()
        only = self._name_of_shape(target) if isinstance(target, int) else None
        pairs = list(zip(self._slot_names(),
                         (g for _p, g, _m in self._slots)))
        if self._reference is not None:
            pairs.append((str(self._reference[0]), self._reference[1]))
        out = {}
        for name, gamut in pairs:
            if not name or gamut is None:
                continue
            if only is not None and name != only:
                continue
            try:
                traces = _rings(gamut, name, int(count), "#888")
            except Exception:              # noqa: BLE001 — a shape too small
                continue                   # to slice is not worth a crash
            if not traces:
                continue
            line = traces[0]
            out[f"{name} (rings inside)"] = [list(line.x), list(line.y),
                                             list(line.z)]
        return out

    def _on_agree_changed(self, value: int) -> None:
        self._agree_lbl.setText(self._fade_words(value))
        self._push_fade()

    def _on_differ_changed(self, value: int) -> None:
        self._differ_lbl.setText(self._fade_words(value))
        self._push_fade()

    def _surfaces_for_live(self) -> dict:
        """The shapes' surfaces as they would be drawn at this fade.

        Keyed by the trace's own name, because a trace is found by name and
        never by position -- the reasoning is written out in
        ``_which_meshes_js``, where matching by position faded the wrong
        shape.

        THE FIGURE IS BUILT AGAIN, AND THAT IS THE POINT. The colours and the
        triangles handed over here are the ones `build_figure` would write
        into a rebuilt page, so the live picture and the page cannot come
        apart -- there is no second implementation of the fade to drift. What
        the rebuild costs is not the figure at all: it is writing six
        megabytes of page and loading it. Measured on the two demo papers,
        the figure alone is **16-19 ms** at every fade, warm.
        """
        stashed = getattr(self, "_scene_inputs", None)
        if not stashed:
            return {}
        gamuts, clouds, styles, lost = stashed
        # NOTHING TO AGREE WITH. One shape carries no mask, so there is no
        # fade to push and the caller must fall back to the rebuild.
        if len(gamuts) < 2:
            return {}
        from ti3gamut import build_figure, surfaces_for_restyle

        try:
            figure = build_figure(gamuts, self._scene_title(), split=True,
                                  patches=clouds, styles=styles, lost=lost,
                                  **self._render_options())
        except Exception:                  # noqa: BLE001 — never on a drag
            return {}
        return surfaces_for_restyle(figure)

    def _push_fade(self) -> None:
        """Fade the picture that is already on screen, as the handle moves.

        Reported of two sliders and then of the lot of them: "should be live",
        "btw all sliders should work this way". These two were the last that
        were not, and the reason on file was that a fade changes a shape's
        TRIANGLES -- at either end the invisible ones are dropped so what is
        left can be drawn genuinely solid -- and that a written page would not
        let its triangle list be replaced.

        THAT NOTE WAS WRONG, and how it came to be wrong is worth keeping. It
        was taken by reading `el.data[i].i`, which a page stores packed binary
        (`{dtype, bdata}`): no length, no elements, so every reading off it is
        a constant and "nothing changed" is the only answer such a reading can
        give. The same mistake has now produced four false verdicts in this
        project. The decoded lists are in `_fullData`, and a saved page has
        been replacing them from its own buttons all along -- which was
        measured in PIXELS before a line of this was written: a page faded by
        its buttons and a page WRITTEN by Python at that fade come out
        identical, 0 of 1,008,000 pixels different at 5% and at 40% on both
        sliders, while a pair that ought to differ differs by 36,419.

        ``_fade_live`` records whether the picture could take it, so letting
        go rebuilds only when the push did not land -- the same "the page says
        whether it managed, and a no falls through to the redraw that always
        worked" the rings and the grid tick use. It cannot land on two rooms,
        where each room holds one shape and there is nothing to agree with.
        """
        self._fade_live = False
        view = getattr(self, "_view", None)
        page = view.page() if view is not None else None
        if page is None:
            return
        if not (self._slots or getattr(self, "_run_drawn", False)):
            return
        wanted = self._surfaces_for_live()
        if not wanted:
            return

        def answered(ok):
            self._fade_live = bool(ok)

        page.runJavaScript(self._in_every_room(
            f"var want={json.dumps(wanted)};"
            "for(var i=0;i<el.data.length;i++){"
            "var n=String(el.data[i].name||'');"
            "if(!Object.prototype.hasOwnProperty.call(want,n))continue;"
            "var w=want[n];"
            "Plotly.restyle(el,{vertexcolor:[w.c],i:[w.i],j:[w.j],k:[w.k]},"
            "[i]);did++;}"), answered)

    def _after_fade(self) -> None:
        """Let go of a fade: rebuild only when the words have to change.

        The picture itself is already right -- it was faded live on every step
        -- so a rebuild here would be a second of black for nothing. There is
        one thing the push cannot do, and it is not the drawing: the caption
        names any shape the fade has taken away entirely ("it agrees with the
        others everywhere, so nothing of it stands out"), and that sentence is
        written by Python when the page is built.

        A SHAPE CAN ONLY GO DARK AT AN END OF A SLIDER. Its corners are lit at
        `agree` where it shares them and at `differ` where it stands out, so
        every corner is unlit only if one of those is exactly nothing. That
        makes the test exact rather than a guess: rebuild when either slider
        is at the bottom now, or was at the bottom when the picture was drawn
        and has since come off it. Anywhere else the caption a rebuild would
        write is the caption already on screen.
        """
        now = (self._agree.value(), self._differ.value())
        drawn = getattr(self, "_fade_drawn", (100, 100))
        # NOTHING MOVED, NOTHING TO DO. A press and release on the handle is
        # not a change, and rebuilding for it is a second of black for
        # nothing — see `_write_scene`, where the drawn values are recorded.
        if now == drawn:
            return
        if getattr(self, "_fade_live", False) and 0 not in now + drawn:
            return
        self._redraw()

    def _on_opacity_changed(self, value: int) -> None:
        """Change how solid the shapes look, live, as the slider moves.

        Rebuilding the whole page for each step would take long enough that the
        picture only caught up after letting go, which is not what a slider is
        for. Plotly can restyle a scene that is already on screen, so the
        change is pushed straight into the page: the shapes fade as you drag,
        the camera stays exactly where you put it, and nothing is recomputed.
        """
        page = self._view.page()
        # THE RUN'S SHELLS ARE SHAPES ON SCREEN TOO -- the same omission the
        # lighting had, and with the same result: the slider went dead for
        # exactly the picture that has two shapes in it.
        if page is None or not (self._slots
                                or getattr(self, "_run_drawn", False)):
            return
        page.runJavaScript(self._in_every_room(
            "var idx=[];for(var i=0;i<el.data.length;i++)"
            "if(el.data[i].type==='mesh3d')idx.push(i);"
            f"var which={self._which_meshes_js()};"
            f"if(which.length){{Plotly.restyle(el,"
            f"{{opacity:{value / 100.0}}},which);did++;}}"))

    def _on_grid_changed(self, *_args) -> None:
        """Show or hide the box, in the picture already on screen.

        THE READER'S OWN COPY HAS ALWAYS DONE THIS WITHOUT A REBUILD -- the
        strip's "walls & grid" button relayouts the axes where they stand --
        while this window wrote and loaded a whole new page for the same tick,
        which is a second or two of black for a change that is one property
        per axis.

        AND IT PUTS ITSELF RIGHT. A flat cross-section has its axes at the top
        level rather than inside a scene, and a picture may not have loaded
        yet; the page answers whether it managed, and a "no" falls through to
        the redraw that always worked.
        """
        on = "true" if self._grid_on.isChecked() else "false"
        page = self._view.page() if self._view is not None else None
        if page is None:
            self._redraw()
            return

        def fell_back(did_it):
            if not did_it:
                self._redraw()

        page.runJavaScript(self._in_every_room(
            f"var on={on};"
            "if(el._fullLayout&&el._fullLayout.scene){Plotly.relayout(el,{"
            "'scene.xaxis.visible':on,'scene.yaxis.visible':on,"
            "'scene.zaxis.visible':on});did++;}"
            "else if(el._fullLayout&&el._fullLayout.xaxis){"
            "Plotly.relayout(el,{'xaxis.visible':on,'yaxis.visible':on});"
            "did++;}"), fell_back)

    def _on_side_by_side(self) -> None:
        """Side by side changes which other controls make sense."""
        self._apply_side_by_side_availability()
        self._redraw()

    def _apply_side_by_side_availability(self) -> None:
        """Show the controls that only mean something in one arrangement.

        Two rooms need two shapes, and the camera link needs two rooms. A
        control that cannot do anything is worse than a missing one: it
        invites a click and answers with nothing.
        """
        from gamutview import can_do
        pieces = len(self._slots) + (1 if self._reference is not None else 0)
        # THIS RUNS AFTER the space registry, inside every redraw, so it has
        # to agree with it. Left to itself it would switch two rooms back on
        # in ink amounts, where there are no shapes to put in either of them.
        shapes = can_do(self._space.currentData(), "shapes")
        can_split = pieces >= 2 and shapes
        self._side_by_side.setEnabled(can_split)
        self._side_by_side.setToolTip(
            "" if can_split else
            self._why_not_in_this_space("shapes") if not shapes else
            "Open a second chart, or choose something under Compare with, and "
            "this can put the two side by side.")
        if not can_split and self._side_by_side.isChecked():
            self._side_by_side.blockSignals(True)
            self._side_by_side.setChecked(False)
            self._side_by_side.blockSignals(False)
        linked_useful = can_split and self._side_by_side.isChecked()
        self._link_row.setVisible(linked_useful)
        # ONE SHAPE HAS NOTHING TO AGREE WITH, so the slider is dead until a
        # second arrives -- and it says why rather than simply refusing to
        # move. Left live it would be a control that does nothing, which this
        # window treats as worse than a control that is not there.
        #
        # A RUN'S TWO SHELLS ARE TWO SHAPES. They are not open files and they
        # are not the comparison, so counting only those left both sliders
        # greyed over a picture with two shapes plainly in it -- reported from
        # a screenshot of exactly that -- and the tooltip advised opening a
        # second measurement, which is not what that picture needs.
        #
        # TWO ROOMS IS LEFT AS IT WAS: the run draws one scene, so a second
        # room would be an arrangement it cannot honour.
        panel = getattr(self, "_timeline", None)
        two_shells = (getattr(self, "_run_drawn", False) and panel is not None
                      and panel.shows_two_shapes())
        can_fade = shapes and (pieces >= 2 or two_shells)
        self._say_if_two_solids_will_show_the_seam(can_fade)
        for _slider, _label in ((self._agree, self._agree_lbl),
                                (self._differ, self._differ_lbl)):
            _slider.setEnabled(can_fade)
            _label.setEnabled(can_fade)
            _slider.setToolTip(
                "" if can_fade else
                self._why_not_in_this_space("shapes") if not shapes else
                "Open a second measurement, or choose something under Compare "
                "with, and these can fade the part the two of them share, or "
                "the parts only one of them reaches.")

    def _say_if_two_solids_will_show_the_seam(self, two_shapes=None) -> None:
        """DELIBERATELY SILENT, and the reason is worth more than the note.

        This said that two see-through solids show ragged edges where they
        cut through each other, and named two ways out. The first half was
        wrong. Measured afterwards, with the second shell hidden and nothing
        else changed:

            two shells, 68%     wedges
            ONE shell, 68%      the same wedges
            both solid, 100%    clean
            the saved page      the same wedges

        So it is one closed surface blending with itself, not two surfaces
        crossing -- and it is in the written page as well, so it is not the
        window's own view either. Flattening the shading changes nothing
        (depth 0 and depth 100 are identical), which rules out the far side
        being lit from behind.

        What is left is the order the mesh's own triangles are drawn in: the
        wedges are triangle-shaped, and a see-through mesh whose faces are
        drawn in buffer order blends them in whatever order they happen to
        sit. That is fixable the way the traces already are -- sorted back to
        front from the camera -- and it is the next piece of work rather than
        a sentence in the panel.

        A note that misnames a fault is worse than no note: somebody follows
        its advice, the fault stays, and now the window has lied to them.
        """
        note = getattr(self, "_two_solids_note", None)
        if note is not None:
            note.setText("")

    def _draw_the_run(self, panel) -> None:
        """Draw the run's picture in the big view, or give the view back.

        WHO OWNS THE PICTURE, and it needs a rule rather than a race. Two
        different things can be open at once: a PAIR of files, whose shapes
        this window compares, and a RUN of profiles of one device, which asks
        how far that device has moved. They are different questions and only
        one picture can be on screen.

        THE RUN WINS WHILE IT HAS SOMETHING TO SAY, because it is the more
        specific answer: opening a second file is something people do while
        browsing, and adding profiles to a run is a deliberate act with an
        obvious subject. Take the run away -- Remove them all -- and the view
        goes straight back to whatever else is open, with nothing to press.

        AND THE WINDOW SAYS SO IN WORDS rather than leaving the reader to work
        out which of two similar-looking pictures they are looking at; see
        _say_who_owns_the_picture.
        """
        figure = panel.figure_now()
        if figure is None:
            self._release_the_picture()
            return
        self._run_drawn = True
        self._say_who_owns_the_picture()
        self._let_the_exports_follow_the_picture()
        self._match_the_opacity_to_the_shells(panel)
        # AND "SET THIS FOR" NAMES THE RUN'S PROFILES while they are what it
        # governs. _redraw stands aside when the run owns the picture, and it
        # was the only thing that refreshed those names.
        self._refresh_style_controls()
        self._render_count += 1
        out = self._tmp / f"run-{self._render_count}.html"
        try:
            # THE SAME WRITER AS EVERY OTHER PICTURE IN THIS APPLICATION, and
            # this is not tidiness. Writing the figure straight out skips
            # everything _write_dark_html adds, and one of those things is the
            # script that puts see-through surfaces in DRAW ORDER. Without it
            # a shape at anything under full opacity comes apart on screen:
            # holes, missing triangles, a slice taken out of the side.
            # Reported, with a photograph, the moment the shapes could be made
            # fainter: "this is no transparency but missing triangles and
            # stuff again which we should have fixed for good already".
            #
            # It HAD been fixed for good -- in the writer this one call was
            # going around. The picture that gets SAVED went through it and
            # was fine; the picture on screen did not.
            from ti3gamut import _write_dark_html
            _write_dark_html(figure, out, self._appearance,
                             spin=self._spin_options(),
                             carry_viewer=True, controls=False)
        except OSError as exc:
            _log().warning("could not draw the run: %s", exc)
            return
        self._show_page(out)
        self._drop_the_scene_before_last()

    def _let_the_exports_follow_the_picture(self) -> None:
        """Whatever is on screen can be saved, whoever put it there.

        THE THREE EXPORT BUTTONS ASKED THE WRONG QUESTION. They were switched
        on when a FILE was opened, which was the same thing as "there is a
        picture" until the run panel moved into the column -- and then it was
        not: a run of four profiles drew a picture into the big view with both
        Save buttons greyed out beside it. Reported within minutes of the
        window being handed over: "currently both export buttons are not
        working (as picture and web page)".

        Asked here as "is there a picture", which is the thing they act on.
        """
        # THE PANEL IS BUILT BEFORE THE BUTTONS ARE. It settles itself while
        # the column is still being made, and asking for a button that does
        # not exist yet threw AttributeError out of the constructor.
        buttons = [getattr(self, name, None)
                   for name in ("_save", "_export_btn", "_picture")]
        if not all(buttons):
            return
        page, table, still = buttons
        files = bool(self._slots or self._reference is not None
                     or self._chart_drawable())
        drawn = files or bool(getattr(self, "_run_drawn", False))
        # THE TWO THAT SAVE A PICTURE FOLLOW THE PICTURE. Both re-render or
        # re-write whatever the view is showing, so a run counts.
        page.setEnabled(drawn)
        still.setEnabled(drawn)
        # THE TABLE FOLLOWS THE READOUTS, WHICH ARE NOT THE SAME THING. It
        # writes what this window says -- the volumes, the coverage, the drift
        # between two readings -- and with only a run open there are none of
        # those to write. The run has a table of its own, in its own group,
        # naming what it holds: enabling this one would be a second button
        # for a different table with nothing to put in it.
        table.setEnabled(files)

    def _match_the_opacity_to_the_shells(self, panel) -> None:
        """Put the opacity slider where the picture actually is, once.

        THE SLIDER AND THE PICTURE HAVE TO AGREE. Two shapes drawn by this
        application are 0.55 solid unless somebody says otherwise -- the rule
        that keeps a pair readable -- while the slider in the column reads
        100% because nothing has ever told it different. Handing the run's
        shells the slider's value makes them opaque and hides the cloud they
        are drawn around; ignoring the slider leaves a control that does
        nothing, which is what put three poorer controls in the run's group
        for an afternoon.

        So the first time a pair of shells appears with none of the window's
        own shapes open, the slider is moved to what the rule would have
        chosen. After that it is the reader's, and it governs these shells
        exactly as it governs any other.
        """
        if getattr(self, "_matched_the_shell_opacity", False):
            return
        if self._slots or not panel.shows_two_shapes():
            return
        self._matched_the_shell_opacity = True
        self._opacity.blockSignals(True)
        self._opacity.setValue(55)
        self._opacity.blockSignals(False)
        # AND THE NUMBER BESIDE IT, which is written by a separate connection
        # -- blocked along with everything else. The slider sat at 55 with
        # "100%" printed next to it: "how solid it looks says 100% although
        # the slider is more in the middle".
        self._opacity_lbl.setText("55%")
        self._shared["opacity"] = 0.55
        # THE READING BESIDE THE SLIDER FOLLOWS IT, through the window's own
        # handler rather than a second copy of what that handler does.
        handler = getattr(self, "_on_opacity_changed", None)
        if handler is not None:
            handler(55)

    def _release_the_picture(self) -> None:
        """The run has nothing to show: give the view back to what is open."""
        was, self._run_drawn = getattr(self, "_run_drawn", False), False
        self._say_who_owns_the_picture()
        self._let_the_exports_follow_the_picture()
        if not was:
            return
        if self._slots or self._reference is not None or self._chart_drawable():
            self._redraw()
        else:
            self._show_placeholder()

    def _say_who_owns_the_picture(self) -> None:
        """One line, only when it is needed: which question the view answers.

        NOTHING IS SAID WHEN THERE IS NOTHING TO CONFUSE. With only a run
        open, or only files, the picture is the only thing it could be and a
        line explaining that is noise.
        """
        note = getattr(self, "_who_owns", None)
        if note is None:
            return
        # EVERYTHING THAT IS OPEN, NOT JUST THE FILES. The first version built
        # the names from the open files alone and then counted the comparison
        # as well, so with only "Adobe RGB (1998)" chosen the sentence came
        # out with a hole in it: "The view is showing the run below.  is still
        # open". Reported exactly that way.
        names = [path.stem for path, _g, _m in self._slots]
        if self._reference is not None:
            names.append(self._reference[0])
        if not (getattr(self, "_run_drawn", False) and names):
            note.setText("")
            return
        # NO DASHES. They read as machine-written, and this is a sentence
        # somebody has to trust. Two short sentences say it better anyway.
        if len(names) == 1:
            note.setText(
                f"The big view is showing this run. {names[0]} is still open "
                f"as well, and it comes back as soon as you remove these "
                f"profiles.")
        else:
            note.setText(
                f"The big view is showing this run. {_join_words(names)} are "
                f"still open as well, and they come back as soon as you "
                f"remove these profiles.")

    def _redraw(self) -> None:
        # THE RUN OWNS THE VIEW WHILE IT HAS ONE. Opening a file, changing a
        # colour or moving a slider still updates every reading and every
        # option; what it must not do is quietly replace the run's picture
        # with the pair's. See _draw_the_run for the rule and why.
        if getattr(self, "_run_drawn", False):
            self._refresh_style_controls()
            self._apply_side_by_side_availability()
            self._update_volume()
            self._update_coverage()
            self._update_drift()
            self._say_who_owns_the_picture()
            # AND THE RUN'S PICTURE IS REDRAWN, because it is the picture.
            # Standing aside was right when the run drew itself and nothing
            # here could touch it; now that How it looks governs its shells,
            # every one of those controls came through here and stopped. The
            # opacity slider moved and the shapes did not.
            panel = getattr(self, "_timeline", None)
            if panel is not None and not getattr(self, "_redrawing_run", False):
                self._redrawing_run = True
                try:
                    panel._draw()
                finally:
                    self._redrawing_run = False
            return
        # A PLACED CHART IS A PICTURE IN ITS OWN RIGHT. Returning early when
        # only a chart is open would leave somebody who opened a chart and a
        # profile looking at the empty-window text with no idea why.
        if (not self._slots and self._reference is None
                and not self._chart_drawable()):
            return
        # The comparison can change without any chart changing, so the style
        # controls are refreshed here rather than only when charts are opened.
        self._refresh_style_controls()
        self._apply_side_by_side_availability()
        gamuts, clouds, styles, lost = self._scene_contents()
        # A NEW FILE EVERY TIME. Writing to one name and loading the same URL
        # let the web view serve its cached copy, so switching to light left
        # the scene dark -- the page had been rewritten and never re-read.
        # Counting up sidesteps caching entirely.
        self._render_count += 1
        out = self._tmp / f"scene-{self._render_count}.html"
        flat = self._write_scene(gamuts, clouds, styles, lost, out,
                                 controls=False)
        self._show_page(out)
        self._drop_the_scene_before_last()
        self._update_volume()
        self._update_coverage()
        self._update_drift()
        if not flat:
            self._update_chart_numbers()

    def _drop_the_scene_before_last(self) -> None:
        """Delete the scene two redraws ago. It cost 27 GB of somebody's disk.

        Every redraw writes a self-contained page with plotly.js inlined --
        about **6 MB** -- under a name that counts up, because writing to one
        name and reloading the same URL let the web view serve its cached
        copy. That part is right and is kept. What was missing is that
        nothing ever deleted them: a session that redraws sixty times left
        360 MB behind, for ever, and the folder holding them was never
        removed either.

        Found on the machine this is developed on: **644 leftover folders,
        27 GB**, from two days of work. A user does not redraw as often as a
        test run does, but nothing here was bounded, so it was only a matter
        of how long.

        THE ONE BEFORE LAST, not the last. The view has been told to load the
        newest file and may not have finished reading it, and the one before
        that is what it was showing until a moment ago. Two back is safe by
        the time a third redraw has happened, and keeping the names counting
        up means a URL is never reused, so the caching this exists to avoid
        cannot come back.
        """
        stale = self._tmp / f"scene-{self._render_count - 2}.html"
        try:
            stale.unlink()
        except OSError:          # never written, or already gone
            pass

    def closeEvent(self, event):
        """Take the temporary folder with us, which is what it is for."""
        try:
            shutil.rmtree(self._tmp, ignore_errors=True)
        except Exception:        # noqa: BLE001 — never block a window closing
            pass
        super().closeEvent(event)

    def _write_scene(self, gamuts, clouds, styles, lost, out, *,
                     controls: bool = False, carry_viewer: bool = True,
                     notes: str = "", offer=None, glide: bool = False,
                     colours: str = None, both_views: bool = False,
                     saved: bool = False) -> bool:
        """Write whatever is on screen, whichever of the four it is.

        ONE PLACE, BECAUSE THERE WERE TWO AND THEY DISAGREED. This window can
        show four arrangements -- one scene, two rooms, a cross-section, two
        cross-sections -- and only the first of them was ever reachable from
        **Save this view as a web page…**. So somebody looking at two rooms
        got a single overlaid scene; somebody looking at a cross-section got a
        3D shape. The button says *this view*, and for three of the four it
        wrote a different one.

        Returns True when the page written is a flat cross-section, which has
        no camera to move and no chart numbers to report.

        *controls* is the reader's strip along the bottom: off for this
        window's own view, on for a page somebody is sent.
        """
        # WHAT THE PICTURE ON SCREEN WAS BUILT WITH, recorded here because this
        # is the one place all four arrangements go through.
        #
        # LETTING GO OF A SLIDER YOU DID NOT MOVE USED TO REBUILD THE WHOLE
        # PAGE. Measured on four of them — the two fades, the rings and the
        # detail — a press and release with no movement wrote a new page every
        # time: a second of black for a change nobody made. It is the same
        # blink the live pushes were built to remove, surviving in the one case
        # they cannot cover, because a slider that does not move emits no
        # `valueChanged` and so never pushes anything.
        #
        # So every release handler asks this first: is the value already the
        # one the picture was drawn with? Then there is nothing to do.
        self._fade_drawn = (self._agree.value(), self._differ.value())
        self._drawn_with = {
            "agree": self._agree.value(), "differ": self._differ.value(),
            "rings": self._rings.value(), "detail": self._detail.value(),
            "cut": self._slice_at.value()}
        if self._slice_on.isChecked():
            # A CROSS-SECTION IS DRAWN FLAT, LOOKING DOWN. There is no camera,
            # so no movement settings travel with it and the strip leaves out
            # everything about movement -- but it does get a strip. Zooming,
            # moving and getting back to the opening view are as useful on a
            # cut as on a shape, and on a phone the drawing library's own
            # toolbar is hidden, so without one there was no way back from a
            # zoom at all.
            # AND THE NUMBERS GO WITH IT. They were not passed here at all,
            # so a cross-section saved as a web page arrived carrying the
            # styling for a block of figures and no figures -- while the same
            # button, on the same numbers, in 3D, carried them. One of the
            # four arrangements quietly saved less than the other three.
            if self._side_by_side.isChecked() and len(gamuts) >= 2:
                self._write_two_slices(gamuts, out, controls=controls,
                                       colours=colours,
                                       offer=offer, notes=notes,
                                       carry_viewer=carry_viewer)
            else:
                write_slice_html(gamuts, out, float(self._slice_at.value()),
                                 self._scene_title(), mode=(colours or self._appearance),
                                 controls=controls, offer=offer, notes=notes,
                                 carry_viewer=carry_viewer)
            return True
        if both_views and gamuts:
            # BOTH PICTURES IN ONE FILE, with a switch. Only from the single
            # scene: two rooms are already two pictures, and a cross-section
            # is the very view this would switch to.
            self._write_both_views(gamuts, out, clouds, styles, lost,
                                   saved=saved,
                                   controls=controls, offer=offer,
                                   glide=glide, notes=notes, colours=colours)
            return False
        if self._side_by_side.isChecked() and len(gamuts) >= 2:
            self._write_two_rooms(gamuts, out, clouds, lost, saved=saved,
                                  controls=controls, offer=offer, glide=glide,
                                  notes=notes, colours=colours)
        else:
            # WHAT THIS SCENE WAS DRAWN FROM.
            self._scene_inputs = (list(gamuts), clouds, styles, lost)
            write_html(gamuts, out, self._scene_title(),
                       # SPLIT WHETHER OR NOT IT IS FADED RIGHT NOW, AND FOR
                       # THIS WINDOW AS WELL AS FOR A PAGE SOMEBODY IS SENT.
                       #
                       # A trace that was never written cannot be faded by
                       # anybody, so the mask travels whenever the control is
                       # being handed over -- and this window hands it over
                       # too, on two sliders of its own. It used to rebuild
                       # the entire page when one of them was let go, which
                       # is a second of black for a change the saved page had
                       # been making live all along; now the same mask lets
                       # the window push the fade into the picture on screen.
                       # See `_push_fade`, and `window.cqFade` in ti3gamut.
                       #
                       # AT FULL STRENGTH IT COSTS NOTHING VISIBLE, which had
                       # to be measured rather than assumed, because carrying
                       # the mask also forces the shapes to be re-cut along
                       # their crossing and that changes the triangle count.
                       # Two real papers, one fixed camera, the picture with
                       # the mask against the picture without: **0 of
                       # 1,008,000 pixels different**, worst channel 0.
                       split=bool(len(gamuts) > 1
                                  and (offer is None
                                       or offer.get("agree", True))),
                       spin=self._spin_options(glide, saved=saved),
                       # NO FLOATING STRIP IN THIS WINDOW. It has its own
                       # movement controls, and a second set over the picture
                       # is two controls for one thing that can disagree.
                       # The strip is for a page somebody was sent.
                       controls=controls, offer=offer,
                       carry_viewer=carry_viewer, notes=notes,
                       patches=clouds, styles=styles, lost=lost,
                       **self._render_options(colours))
        return False

    def _write_two_slices(self, gamuts, out, controls: bool = False,
                          offer=None, notes: str = "",
                          carry_viewer: bool = True,
                          colours: str = None) -> None:
        """Two cross-sections, side by side, on one range.

        The same question as two rooms in 3D -- what does each of these look
        like on its own -- asked of a flat cut, where it is easier to answer
        because nothing is hiding behind anything.

        The shared range is the part that matters. Left to itself each pane
        scales to whatever is in it, so a small gamut and a large one come out
        the same size and the picture says the opposite of the truth.
        """
        from ti3gamut import (build_slice_figure, slice_extent, slice_levels,
                              write_side_by_side_html)

        lightness = float(self._slice_at.value())
        # THE SLIDER GOES ON BOTH PANES OR NEITHER. Worked out from both
        # shapes at once so the two panes step through the same list of
        # heights -- two panes on two lists is a side-by-side comparison of
        # two different cuts, which is the one thing this view must never be.
        cuts = None
        if controls and (offer is None or offer.get("cut", True)):
            cuts = slice_levels(gamuts[:2], include=lightness)
            if cuts is not None:
                cuts["title"] = ""
                cuts["at"] = min(
                    range(len(cuts["levels"])),
                    key=lambda i: abs(cuts["levels"][i] - lightness))
        extent = cuts["extent"] if cuts else slice_extent(gamuts, lightness)
        pages = [(name, build_slice_figure(
            [(name, g)], lightness, "", mode=(colours or self._appearance),
            extent=extent, legend=False, first=i, slidable=cuts is not None))
            for i, (name, g) in enumerate(gamuts[:2])]
        write_side_by_side_html(pages, out, mode=(colours or self._appearance),
                                linked=self._link_cameras.isChecked(),
                                spin={"cuts": cuts} if cuts else None,
                                controls=controls, offer=offer, notes=notes)

    def _write_both_views(self, gamuts, out, clouds, styles, lost, *,
                          controls: bool = False, offer=None,
                          glide: bool = False, notes: str = "",
                          colours: str = None,
                          saved: bool = False) -> None:
        """One page holding the shapes AND a cut through them, with a switch.

        Asked for from the window: "could the exported web viewer files get a
        toggle to switch between the view of the shells and the sliced view".

        THE CUT IS GIVEN ITS LEVELS, which is what lets the reader move it.
        Worked out the same way the two-pane cut page works them out -- once,
        from the shapes together, so there is one list of heights rather than
        one per shape -- and carried in the page's settings, where the strip
        looks for them. Without them a reader could switch to the cut and then
        be stuck at whatever lightness it was saved at, which is half of what
        was asked for.
        """
        from ti3gamut import (build_figure, build_slice_figure, slice_levels,
                              write_two_views_html)

        lightness = float(self._slice_at.value())
        cuts = slice_levels(gamuts[:2], include=lightness)
        if cuts is not None:
            cuts["title"] = ""
            cuts["at"] = min(range(len(cuts["levels"])),
                             key=lambda i: abs(cuts["levels"][i] - lightness))
        shapes = build_figure(
            gamuts, self._scene_title(), patches=clouds, styles=styles,
            lost=lost,
            split=bool(controls and len(gamuts) > 1
                       and (offer is None or offer.get("agree", True))),
            **self._render_options(colours))
        cut = build_slice_figure(
            gamuts, lightness, "", mode=(colours or self._appearance),
            extent=(cuts["extent"] if cuts else None),
            slidable=cuts is not None)
        write_two_views_html(
            [("The shapes", shapes), ("A cut through them", cut)], out,
            mode=(colours or self._appearance),
            spin={**self._spin_options(glide, saved=saved), "cuts": cuts},
            controls=controls, offer=offer, notes=notes)

    def _write_two_rooms(self, gamuts, out, clouds, lost,
                         controls: bool = False, offer=None,
                         glide: bool = False, notes: str = "",
                         colours: str = None,
                         saved: bool = False) -> None:
        """One page, two scenes, each holding a single shape.

        Each is built by the same code that builds the single view, so the two
        arrangements cannot drift apart in how they draw anything -- the only
        difference is how many shapes go into each picture.

        **The per-shape solid/outline choice is deliberately not carried over.**
        An outline exists so you can see through one shape to the one behind
        it, which is what the second shape needs to be in an overlay. In a room
        of its own there is nothing behind it, so an outline would only be a
        worse drawing of the same gamut -- the wireframe that used to appear on
        the right-hand side. Each room draws its shape solid.
        """
        from ti3gamut import build_figure, write_side_by_side_html

        options = self._render_options(colours)
        # THE CHART IS MARKED PER ROOM, not once for both. Left alone, every
        # room got the same chart — and its red patches are worked out against
        # the FIRST shape on screen, so the right-hand room showed a chart
        # judged against the LEFT-hand room's paper while sitting inside its
        # own. Two rooms exist precisely to compare two papers, so a chart
        # that answers for the wrong one is worse than no chart at all.
        chart = options.pop("chart", None)
        # THE DRIFT CLOUD BELONGS TO THE FIRST ROOM ONLY, and left in the
        # shared options it went into both. It is drawn at the FIRST profile's
        # positions, so in the second room it would be one profile's colours
        # floating inside the other profile's shape -- a picture that looks
        # deliberate and says something untrue. Room one reads "here is what
        # you had, and here is how far it has moved"; room two is simply the
        # other shape. Same trap as the chart above, one line further down.
        drift = options.pop("drift", None)
        # AND EACH ROOM GETS ITS OWN SHAPE'S SETTINGS, not the first shape's.
        #
        # Reported from the window: "when enabling the two rooms the shapes on
        # screen don't keep their visuals from before, turning it off again
        # resets the view to how it was before" -- and that second half was
        # the diagnosis. Nothing was lost; it was never handed over.
        #
        # `per_shape` is a list in the order the shapes are DRAWN, and each
        # room is built with a single shape. Passed the whole list, the
        # renderer reads entry 0 for the one shape it has, so both rooms drew
        # with the FIRST shape's settings. Measured with two shapes set
        # deliberately apart: room two came out at opacity 1.0 where its shape
        # was set to 0.30, and with no rings where its shape asked for twelve.
        per_shape = options.pop("per_shape", None)
        figures = []
        for i, (name, gamut) in enumerate(gamuts[:2]):
            # THE SLOT, not just the shape. Judging happens in CIELAB, and
            # rebuilding a paper there needs the file it came from — handing
            # over the drawn shape alone left CIELUV and CIE XYZ marking the
            # chart against a shape in the wrong space, which is the fault
            # this room-by-room marking was added to fix.
            slot = self._slots[i] if i < len(self._slots) else None
            figures.append((name, build_figure(
                [(name, gamut)], "",
                patches=[clouds[i]] if clouds and i < len(clouds) else None,
                styles=["solid"],
                lost=[lost[i]] if lost and i < len(lost) else None,
                chart=self._chart_marked_against(chart, gamut, slot),
                drift=drift if i == 0 else None,
                per_shape=([per_shape[i]] if per_shape and i < len(per_shape)
                           else None),
                **options)))
        write_side_by_side_html(figures, out,
                                mode=(colours or self._appearance),
                                linked=self._link_cameras.isChecked(),
                                spin=self._spin_options(glide, saved=saved),
                                controls=controls, offer=offer, notes=notes)

    #: The controls that can belong to one shape rather than all of them, as
    #: key → (widget, how to read it). Anything not here is window-wide by
    #: nature: the appearance, the accent, the proportions of the axes.
    def _shape_controls(self) -> dict:
        return {
            "opacity": (self._opacity, lambda w: w.value() / 100.0),
            "depth": (self._depth, lambda w: w.value() / 100.0),
            "rings": (self._rings, lambda w: (w.value()
                                              if self._rings_on.isChecked()
                                              else 0)),
            "mesh_paint": (self._outline_paint, lambda w: w.currentData()),
            "paint": (None, lambda _w: self._paint),
        }

    def _remember_shape_setting(self, key: str) -> None:
        """Record a control's value against whatever it is currently setting."""
        widget, read = self._shape_controls()[key]
        value = read(widget)
        target = self._target.currentData()
        if target == "all":
            # Shared again: drop any per-shape override so nothing is left
            # quietly disagreeing with the control the user just moved.
            self._shared[key] = value
            for own in self._per_shape.values():
                own.pop(key, None)
        else:
            self._per_shape[target][key] = value

    def _on_target_changed(self) -> None:
        """Show the values that belong to whichever shape is now selected."""
        target = self._target.currentData()
        for key, (widget, _read) in self._shape_controls().items():
            if widget is None:
                continue
            own = (self._shared if target == "all"
                   else self._per_shape.get(target, {}))
            if key not in own:
                own = self._shared          # this shape follows the shared value
            if key not in own:
                continue
            widget.blockSignals(True)
            if key == "opacity":
                widget.setValue(int(round(own[key] * 100)))
            elif key == "depth":
                widget.setValue(int(round(own[key] * 100)))
            elif key == "rings":
                widget.setValue(max(1, int(own[key])))
                self._rings_on.blockSignals(True)
                self._rings_on.setChecked(bool(own[key]))
                self._rings_on.blockSignals(False)
            elif key == "mesh_paint":
                # "colour" is what the old tick wrote for "the same as the
                # shapes", and a shape set on its own before this window
                # gained the choice still says it.
                want = "match" if own[key] == "colour" else own[key]
                at = widget.findData(want)
                if at >= 0:
                    widget.setCurrentIndex(at)
            widget.blockSignals(False)
        self._sync_slider_labels()

    def _make_room_to_see_inside(self) -> None:
        """Turn the shape down when something is drawn inside it.

        A LINE INSIDE AN OPAQUE SOLID CANNOT BE SEEN, so ticking Show the
        greys on a shape at full strength appears to do nothing at all — the
        line is there, behind a wall. Rather than leave somebody to discover
        How solid it looks for themselves, the shape drops to a third the
        first time it is needed.

        Only from FULL strength, and only downwards. Somebody who has already
        chosen a value has said what they want, and this must not overrule it;
        and it is never put back, because by then the number is theirs.

        RECORDED, NOT ONLY PUSHED — and that distinction was the whole bug.
        Moving the slider by hand does two things: it restyles the page live
        while the handle is down (``valueChanged``), and it records the value
        when the handle is let go (``sliderReleased``). Calling ``setValue``
        from code fires the first and never the second, so the number went into
        the picture on screen and never into ``_shared`` — where every rebuild
        reads it from. Ticking Show the greys also triggers a redraw, so the
        page was rebuilt at full strength a moment later and the shape closed
        up again. It looked exactly like the feature doing nothing, twice
        reported, and once published in the gallery.
        """
        if self._opacity.value() >= 100:
            self._opacity.setValue(38)
            self._after_shape_setting("opacity")

    def _follow_neutral(self, on: bool) -> None:
        """Make room to see inside, because both these lines are drawn inside.

        THE TWO WERE TIED TOGETHER AND ARE NOT ANY MORE. The neutral line was
        greyed out until the greys were shown, and unticked when they went
        away, on the argument that a line to compare the greys against means
        nothing without them. That argument is sound and was not what was
        wanted: "i get your argument but i'd rather set them independently".
        It is a fair call -- the perfectly neutral line is a fact about the
        space rather than about this print, and somebody may well want to see
        where neutral runs with nothing else in the way.

        What is kept is the part that was never about the coupling: both
        lines run up the INSIDE of the shape, so a surface at full strength
        hides them. Ticking either turns it down far enough to see in, once,
        and leaves it alone afterwards.
        """
        if on:
            self._make_room_to_see_inside()
            self._ideal_neutral.blockSignals(False)

    def _neutral_list(self) -> list:
        """The measurement behind each shape, or None for a reference.

        Only a measured chart has greys to draw: a standard colour space or a
        profile has a perfect neutral axis by construction, so drawing one
        would say nothing.
        """
        out = [m for _p, _g, m in self._slots]   # None where it was a profile
        if self._reference is not None:
            out.append(None)
        return out

    def _per_shape_list(self) -> list:
        """Per-shape overrides in the order the shapes are drawn."""
        out = [dict(self._per_shape[i]) for i in range(len(self._slots))]
        if self._reference is not None:
            out.append(dict(self._per_shape[2]))
        return out

    def _light_value(self, key: str) -> float:
        """One lighting slider, back in the units the renderer wants."""
        slider, lo, hi = self._light_sliders[key]
        return lo + (hi - lo) * slider.value() / 100.0

    def _light_position(self) -> dict:
        """Where the light hangs, from the two controls that place it.

        With "Set the lighting myself" off, this is a plain key light: high
        and a little to one side, which is what makes a curved surface read as
        curved. The controls only take over once somebody asks for them.
        """
        from ti3gamut import light_position
        if not self._manual_light.isChecked():
            return light_position(45.0, 0.85)
        return light_position(self._light_value("direction"),
                              self._light_value("height"))

    def _render_options(self, colours: str = None) -> dict:
        """Every option the renderer takes, from the controls, in one place.

        The live view and the saved page both use this. Keeping two copies of
        the argument list is how new options twice reached the save route and
        never the screen: the two calls look almost identical, so an edit meant
        for one silently landed on the other.
        """
        return dict(
            # The SHARED values, not whatever the sliders happen to show --
            # while one shape is selected the sliders describe that shape.
            opacity=self._shared["opacity"],
            points=self._points.isChecked(),
            aspect=self._aspect.currentData(),
            # THE SAVE'S CHOICE FIRST, THE WINDOW'S LOOK SECOND. This read
            # the window's appearance flat, and it is where "what colours
            # should it open in" was lost for every single-scene page:
            # seven of the eleven showcase pages went on being written
            # dark after the option existed and was being passed in.
            mode=(colours or self._appearance),
            lost_in_their_own_colours=bool(
                getattr(self, "_lost_in_colour", None)
                and self._lost_in_colour.isChecked()),
            paint=self._shared["paint"],
            depth=self._shared["depth"],
            mesh_paint=self._shared["mesh_paint"],
            rings=self._shared["rings"],
            per_shape=self._per_shape_list(),
            neutrals=(self._neutral_list() if self._neutral.isChecked()
                      else None),
            # ITS OWN TICK, AND NOTHING ELSE'S. The window stopped tying
            # these two together when Basti asked for them to be independent;
            # this line kept tying them, so the control was independent in
            # appearance and still could not act alone.
            ideal_neutrals=self._ideal_neutral.isChecked(),
            chart=self._chart_cloud(),
            chart_look=self._chart_look(),
            drift=self._drift_for_figure(),
            light=self._light_position(),
            grid=self._grid_on.isChecked(),
            # WHERE THE SHAPE HAS BEEN TURNED TO. See _watch_the_camera: a
            # rebuilt page that opens at the library's default angle is the
            # jump reported after letting go of a slider.
            camera=self._camera_now(),
            agree=self._agree.value() / 100.0,
            differ=self._differ.value() / 100.0,
            # Named explicitly rather than read off the first shape, because
            # in ink amounts there is no first shape to read it off and the
            # axes would fall back to being labelled a*, b*, L*.
            space=self._space.currentData(),
        )

    def _scene_contents(self):
        """What goes into the picture: the shapes, their patches, their styles.

        One place, used by both the live view and the saved page, so a saved
        page is exactly what was on screen. Keeping two copies of this is how
        the save route came to be broken while the view looked fine.
        """
        # IN INK AMOUNTS THERE ARE NO SHAPES, and this is the one place that
        # has to be true — everything downstream reads the list it returns.
        # The reason is not that the surface is hard to compute: it is that
        # every RGB printer's boundary in its own ink amounts is the same unit
        # cube, whatever paper it is on. A shape here would be correct and
        # would tell nobody anything, while sitting in the picture looking
        # like a result. The panel says so in words rather than leaving an
        # empty scene to be read as a fault.
        if self._drawing_in_ink():
            return [], [], [], None
        gamuts = list(zip(self._slot_names(),
                          (g for _p, g, _m in self._slots)))
        # None where the file was a profile: there are no measured patches to
        # show, and inventing some would be exactly the claim this application
        # exists to avoid making.
        clouds = [(m.lab if m is not None else None) for _p, _g, m in self._slots]
        per_chart = (self._style_mine.currentData(),
                     self._style_second.currentData())
        styles = [per_chart[i] for i in range(len(self._slots))]
        # Marking what is out of reach needs something to be out of reach OF,
        # so it only applies when a comparison is loaded, and only to the
        # charts -- painting the comparison by its own reach says nothing.
        against = None
        if self._reference is not None:
            against = self._reference[1]
        elif len(self._slots) == 2:
            against = self._slots[1][1]
        lost = None
        if self._show_lost.isChecked() and against is not None:
            # Only the charts being judged get painted. Painting the shape that
            # is doing the judging against itself would colour it entirely
            # "kept", which says nothing and looks like a bug.
            judged = len(self._slots) if self._reference is not None else 1
            lost = []
            for i, (_p, g, _m) in enumerate(self._slots):
                if i >= judged:
                    lost.append(None)
                    continue
                try:
                    lost.append(outside_of(g, against))
                except Exception:      # noqa: BLE001 — a view must not crash
                    lost.append(None)
        if self._reference is not None:
            gamuts.append(self._reference)
            clouds.append(None)
            styles.append(self._style_other.currentData())
            if lost is not None:
                lost.append(None)
        return gamuts, clouds, styles, lost

    def _scene_title(self) -> str:
        """What the picture shows, and what its numbers are measured from.

        Deliberately not the word "against": the Compare-with panel already
        uses that for the shape being compared to, and a title reading
        "against D50" beside a panel reading "Compare with sRGB" invites the
        reader to think D50 is the comparison. This says where zero is
        instead, which is what the white point actually decides.
        """
        ref = ("the paper's own white" if self._relative.isChecked()
               else f"a {self._white.currentData()} white")
        # IN INK AMOUNTS NOTHING IS MEASURED AND THERE IS NO LIGHTNESS, so the
        # usual caption is false in every clause. Caught by looking at the
        # rendered picture rather than at the code: the panel was already
        # careful and the caption above the scene still said "lightness and
        # colour measured from a D50 white" over a cube of ink percentages.
        if self._drawing_in_ink() and self._chart is not None:
            painted = ("" if self._chart_placed is None else
                       f", painted through {self._chart_placed.profile}")
            return (f"{self._chart[0].stem} — the ink amounts this chart asks "
                    f"for, not measured and not yet printed{painted}")
        # A CHART ON ITS OWN IS NOT A MEASURED GAMUT, and a caption saying it
        # was would be the one claim this whole feature was designed not to
        # make. Named for what is actually in the picture.
        if self._chart_placed is not None and not self._slots \
                and self._reference is None:
            return (f"{self._chart[0].stem} — patches to be printed, not "
                    f"measured, shown where {self._chart_placed.profile} says "
                    f"they would land")
        return f"Measured gamut — lightness and colour measured from {ref}"

    def _how_much_fits(self, a, b) -> tuple:
        """(a inside b, b inside a), worked out once per pair of shapes.

        THE BIGGEST SINGLE COST IN A REDRAW, and almost all of it was wasted.
        Profiled on two papers against Adobe RGB: the whole redraw took 358 ms
        and `coverage` was 177 ms of it -- 49% -- recomputed from scratch every
        single time.

        NOTHING IT DEPENDS ON CHANGES BETWEEN MOST REDRAWS. It reads the two
        SHAPES, and a shape is rebuilt only when a file is opened or closed,
        or the colour space or white point changes. Every other redraw -- and
        those are the ones that have to feel smooth, because they are what a
        slider does -- asks the same question of the same two objects and gets
        the same answer back at sixty milliseconds a time.

        KEYED ON THE OBJECTS THEMSELVES, and the shapes are held with the
        answer so that the identities cannot be reused underneath it. That is
        not fussiness: `id()` is only unique among objects that are ALIVE, and
        a cache holding ids alone would happily answer for a gamut that had
        been collected and a new one built at the same address. Holding the
        pair keeps them alive and keeps the key honest.

        Both directions together, because they are always wanted together and
        each costs the same.
        """
        return self._remembered("fits", a, b,
                                lambda: (coverage(a, b)[0], coverage(b, a)[0]))

    def _remembered(self, what: str, a, b, work):
        """*work*'s answer for this pair of shapes, worked out once.

        KEYED ON THE OBJECTS THEMSELVES, and the shapes are held alongside the
        answer so their identities cannot be reused underneath it. That is not
        fussiness: `id()` is unique only among objects that are ALIVE, so a
        cache holding ids alone would happily answer for a gamut that had been
        collected and a new one built at the same address.

        Cleared wherever the shapes are rebuilt -- see the call to
        `_forget_the_pair` beside `_lab_gamuts.clear()`.
        """
        cache = getattr(self, "_fits_cache", None)
        if cache is None:
            cache = self._fits_cache = {}
        key = (what, id(a), id(b))
        found = cache.get(key)
        if found is not None:
            return found[2]
        answer = work()
        # SMALL BY CONSTRUCTION. At most two shapes and a comparison are open,
        # so this holds a handful of entries; clearing it wherever the shapes
        # are rebuilt is what keeps it from being a memory leak with a view.
        if len(cache) > 12:
            cache.clear()
        cache[key] = (a, b, answer)
        return answer

    def _forget_the_pair(self) -> None:
        """Throw away what was worked out about the shapes that were open."""
        getattr(self, "_fits_cache", {}).clear()

    def _update_coverage(self) -> None:
        """Both directions, always — one number would hide the difference.

        Coverage is not symmetric: a paper can hold nearly all of what a
        smaller one shows while the smaller one holds only part of it. Which
        way round matters is exactly what decides whether an image will survive
        the swap, so both are shown and each is named.
        """
        pair = None
        if self._reference is not None and self._slots:
            pair = ((self._slots[0][0].stem, self._slots[0][1]), self._reference)
        elif len(self._slots) == 2:
            pair = ((self._slots[0][0].stem, self._slots[0][1]),
                    (self._slots[1][0].stem, self._slots[1][1]))
        if pair is None:
            self._coverage.setText("")
            self._picture_loss.setText("")
            self._shared_lbl.setText("")
            self._reach.setText("")
            self._pair_box.setVisible(False)
            return
        (a_name, a), (b_name, b) = pair
        try:
            ab, ba = self._how_much_fits(a, b)
        except Exception:      # noqa: BLE001 — a readout must never crash a view
            self._coverage.setText("")
            self._picture_loss.setText("")
            self._pair_box.setVisible(False)
            return
        # A PICTURE DOES NOT PRINT ANYTHING. "What X can print" is right for
        # a paper or a profile and simply wrong for a photograph, which only
        # holds colours -- and getting that backwards is the sort of sentence
        # that makes somebody distrust the number beside it.
        holds = "holds" if self._is_picture(a_name) else "can print"
        self._coverage.setText(
            f"{100 * ab:.1f}% of the colour {a_name} {holds} also fits inside "
            f"{b_name}.\n"
            f"{100 * ba:.1f}% of {b_name} fits inside {a_name}.\n"
            "The two numbers differ because fitting inside is not the same "
            "question in both directions.")
        self._update_picture_loss(a_name, a, b_name, b)
        self._update_pair(a_name, a, b_name, b)

    def _update_picture_loss(self, a_name, a, b_name, b) -> None:
        """For a picture, how much of the PICTURE a shape cannot print.

        WHY THIS IS A SEPARATE NUMBER, and why the coverage figure above is not
        the answer people read it as. Coverage measures a share of the SPACE a
        shape encloses. Most of that space is unsaturated middle colour that
        any paper reaches easily, while a photograph's pixels crowd towards the
        edges — so the two come apart badly. Measured on a real Display P3
        photograph against a real glossy paper:

            of the space its colours enclose     7.3% out of reach
            of its distinct colours             27.1% out of reach
            of the picture itself, by pixel     39.8% out of reach

        "92.7% fits" is true and reads as "93% of my photograph will print",
        which is out by a factor of five in the comforting direction. A paper
        or a profile has no such number — nobody has said which of its colours
        matter more — but a picture does, so where there is one it is shown.
        """
        from imagegamut import out_of_reach

        self._picture_loss.setText("")
        for name, shape, against, against_name in ((a_name, a, b, b_name),
                                                   (b_name, b, a, a_name)):
            if not self._is_picture(name):
                continue
            facts = None
            for path, kept in self._image_facts.items():
                if Path(path).stem == name:
                    facts = kept
                    break
            if facts is None:
                continue
            try:
                lost = out_of_reach(facts, against)
            except Exception:      # noqa: BLE001 — a readout must never crash
                return
            if lost is None:
                return
            if not lost["of_the_picture"]:
                self._picture_loss.setText(
                    f"Every colour in {name} is one {against_name} can print.")
                return
            self._picture_loss.setText(
                f"{100 * lost['of_the_picture']:.0f}% of {name} itself is out "
                f"of reach of {against_name} — counting how much of the "
                f"picture each colour covers, not how much space its colours "
                f"enclose. The worst is {lost['worst']:.1f} ΔE beyond what "
                f"{against_name} can print.")
            return

    #: Below this much chroma apart, two hue families are called the same.
    #: Roughly the point where a difference stops being visible, and well
    #: inside what a percentage rounded to one decimal place can imply: the
    #: demo papers differ by 0.6 in the reds while one sits entirely inside
    #: the other, which is sampling precision rather than a real advantage.
    REACH_MARGIN = 2.0

    def _update_pair(self, a_name, a, b_name, b) -> None:
        """What two shapes have in common, and where each one wins.

        Everything here needs the hue circle and the lightness axis, so in CIE
        XYZ the box is hidden rather than filled with numbers that would not
        mean what they say.
        """
        from gamutview import AXES, hue_reach, shared_volume
        if not AXES[self._space.currentData()]["cylindrical"]:
            self._pair_box.setVisible(False)
            return
        try:
            # THE SHAPES, NOT THEIR POINTS. Stripped to bare vertices this
            # loses the triangles, and every figure in the sentence falls back
            # to the convex hull -- see gamutview.shared_volume.
            #
            # REMEMBERED PER PAIR, like the coverage above and for the same
            # reason: these read the two SHAPES, which are rebuilt only when a
            # file is opened or the space or white point changes. Every other
            # redraw asked the same question of the same objects and paid for
            # the answer again -- and those are exactly the redraws that have
            # to feel smooth, because they are what moving a slider does.
            share, reach_a, reach_b = self._remembered(
                "pair", a, b,
                lambda: (shared_volume(a, b)[2], hue_reach(a), hue_reach(b)))
        except Exception:      # noqa: BLE001 — a readout must never crash a view
            self._pair_box.setVisible(False)
            return
        self._shared_lbl.setText(
            f"Both can print {100 * share:.0f}% of everything either one can.")
        wins_a = [n for n in reach_a
                  if reach_a[n] - reach_b[n] > self.REACH_MARGIN]
        wins_b = [n for n in reach_b
                  if reach_b[n] - reach_a[n] > self.REACH_MARGIN]
        lines = []
        if wins_a:
            lines.append(f"{a_name} reaches further in the "
                         f"{_join_words(wins_a)}.")
        if wins_b:
            lines.append(f"{b_name} reaches further in the "
                         f"{_join_words(wins_b)}.")
        if not lines:
            lines.append("Neither reaches meaningfully further than the other "
                         "in any hue family.")
        self._reach.setText("\n".join(lines))
        self._pair_box.setVisible(True)

    #: Files this window will compare colour by colour rather than patch by
    #: patch. Kept beside the check that uses it so the two cannot drift apart.
    PROFILE_SUFFIXES = (".icc", ".icm")

    def _profile_pair(self):
        """The two open files as profiles, or None if that is not what they are.

        A profile carries no measured patches — slot[2] is None — which is why
        the drift box used to hide itself the moment one was opened. That is
        precisely the case somebody comparing two profiles is in.
        """
        if len(self._slots) != 2:
            return None
        if any(slot[2] is not None for slot in self._slots):
            return None                      # at least one is a measurement
        paths = [slot[0] for slot in self._slots]
        if not all(p.suffix.lower() in self.PROFILE_SUFFIXES for p in paths):
            return None                      # .gam files have no lookup table
        return paths[0], paths[1]

    def _one_thing_over_time(self) -> bool:
        """Has the reader said the two open files are one thing at two times?

        #123's chooser. Kept as a method rather than read where it is needed,
        because it turned out to be needed in FOUR places and was read in
        one: the family heading switched to "how the two compare" while the
        line above it still said "The ones that moved most" and the exported
        table still had a "moved most:" row for every patch. Two papers
        printed on one afternoon have not moved anywhere, and that is the
        whole reason the chooser exists.

        True when there is no chooser yet, which is what every path that has
        only one file wants.
        """
        picker = getattr(self, "_same_thing", None)
        return True if picker is None else bool(picker.currentData())

    def _the_ones_that(self) -> str:
        """"moved most" or "differ most", by what the reader chose."""
        return ("The ones that moved most:" if self._one_thing_over_time()
                else "The ones that differ most:")

    def _say_drift_families(self, lab_a=None, lab_b=None, spans="",
                            of="profiles") -> None:
        """Fill — or clear — the family lines under the drift numbers.

        CLEARED BY DEFAULT AND ON EVERY PATH THAT CANNOT FILL THEM. A report
        left behind from the last pair is worse than none: it names colours
        that belong to files the reader has already closed. That fault has
        happened once in this application and is not repeated by accident.
        """
        said = None
        if lab_a is not None and lab_b is not None:
            said = family_report(lab_a, lab_b, spans, of=of,
                                 over_time=self._one_thing_over_time())
        self._drift_families.setText("" if said is None else said[0])
        self._drift_families_note.setText("" if said is None else said[1])

    def _update_drift(self) -> None:
        """Has anything changed — asked of two readings, or of two profiles.

        ONE BOX FOR BOTH, because to the reader it is one question. "Have
        these two moved apart" is the same thing to ask of two measurements of
        a chart and of two profiles of a scanner; only the way of answering it
        differs, and that is our problem rather than theirs.
        """
        pair = self._profile_pair()
        if pair is not None:
            self._update_profile_drift(*pair)
            return
        # Two READINGS, and a profile was never read: there are no patches to
        # pair up, so there is no drift to speak of.
        if len(self._slots) != 2 or any(x[2] is None for x in self._slots):
            self._drift_box.setVisible(False)
            self._say_drift_families()
            return
        self._drift_box.setVisible(True)
        (_pa, _ga, before), (_pb, _gb, after) = self._slots
        try:
            d = compare_measurements(before, after)
        except ValueError as exc:
            self._drift.setText(str(exc))
            self._drift_worst.setText("")
            self._say_drift_families()
            return
        matched = ("1 patch" if d.matched == 1 else f"{d.matched} patches")
        verdict = ("Nothing anybody could see." if d.worst < 1.0
                   else "Visible on a careful look." if d.worst < 3.0
                   else "Plainly visible — worth looking into.")
        self._drift.setText(
            f"{matched} appear in both readings.\n"
            f"Biggest difference ΔE {d.worst:.2f}, average {d.average:.2f}.\n"
            f"{verdict}")
        lines = [f"    {label} — ΔE {de:.2f}"
                 for label, de, _a, _b in d.worst_patches[:4]]
        above = []
        if d.over_three:
            above.append(f"{d.over_three} above 3")
        if d.over_one:
            above.append(f"{d.over_one} above 1")
        summary = (", ".join(above) if above
                   else "no patch differs by more than 1")
        self._drift_worst.setText(
            f"Of those, {summary}. {self._the_ones_that()}\n"
            + "\n".join(lines))
        # AND WHICH COLOURS DID THE MOVING. Two readings of one chart are the
        # DEVICE, near enough -- the only thing between them is the chart
        # itself ageing -- so this gets a different caveat from a pair of
        # profiles, and saying which is which is the point of having one.
        # THE STEMS, NOT THE PATHS. _clean_stem sanitises a name into
        # something safe for a file; handed a full path it returns the whole
        # path with the separators replaced, and the heading came out as
        # "private-tmp-claude-502--Users-...-Glossy-pap → ...". Found by
        # reading the window rather than the test.
        self._say_drift_families(
            d.lab_a, d.lab_b,
            f"{Path(self._slots[0][0]).stem} → {Path(self._slots[1][0]).stem}",
            of="measurements")

    #: How finely the two profiles are sampled, per channel. 9 gives 729
    #: colours for an RGB profile and takes well under a tenth of a second,
    #: measured -- fine enough that the figures stop moving, cheap enough to
    #: run on every redraw without the window noticing.
    PROFILE_GRID = 9

    def _update_profile_drift(self, path_a, path_b) -> None:
        """Two ICC profiles, compared colour by colour.

        THE QUESTION A GAMUT CANNOT ANSWER, which is why this is here at all.
        Two profiles can enclose almost exactly the same shape and send the
        colours inside it to quite different places. Measured on a pair
        differing only in tone curve: 0.011% apart by volume — the same shape
        by any measure — and up to ΔE 4.2 apart inside. For an input profile,
        such as a scanner's, the inside is nearly the whole profile.
        """
        import icc_read
        from ti3gamut import compare_profiles

        self._drift_box.setVisible(True)
        try:
            d = compare_profiles(path_a, path_b, steps=self.PROFILE_GRID)
        except (ValueError, icc_read.UnsupportedProfile) as exc:
            # Refused for a reason worth reading, rather than answered with a
            # number that would describe nothing. Mismatched device spaces
            # land here, and so does a file that is not a profile.
            self._drift.setText(str(exc))
            self._drift_worst.setText("")
            self._say_drift_families()
            return
        except Exception as exc:               # noqa: BLE001
            self._drift.setText(
                f"These two profiles could not be compared: {exc}")
            self._drift_worst.setText("")
            self._say_drift_families()
            return

        verdict = ("Nothing anybody could see." if d.worst < 1.0
                   else "Visible on a careful look." if d.worst < 3.0
                   else "Plainly visible — worth looking into.")
        self._drift.setText(
            f"{d.matched} colours asked of both profiles.\n"
            f"Biggest difference ΔE {d.worst:.2f}, average {d.average:.2f}.\n"
            f"{verdict}")

        lines = [f"    {label} — ΔE {de:.2f}"
                 for label, de, _a, _b in d.worst_patches[:4]]
        above = []
        if d.over_three:
            above.append(f"{d.over_three} above 3")
        if d.over_one:
            above.append(f"{d.over_one} above 1")
        summary = (", ".join(above) if above
                   else "no colour differs by more than 1")
        note = ""
        if not d.comparable:
            # SAID BEFORE THE NUMBERS ARE BELIEVED. A colorimetric table held
            # against a perceptual one differs by a large amount that has
            # nothing to do with drift, because perceptual rendering moves
            # colour on purpose. Measured on real files: ΔE 45 worst, 12.7
            # average, and meaningless.
            note = (f"\n\nBUT READ THIS FIRST: these two were not read the "
                    f"same way — one through {icc_read.TABLE_NAMES[d.table_a]}, "
                    f"the other through {icc_read.TABLE_NAMES[d.table_b]}. "
                    f"Those answer different questions, so the difference "
                    f"above is mostly that, and not drift. Compare two "
                    f"profiles of the same kind for a figure you can trust.")
        self._drift_worst.setText(
            f"Of those, {summary}. {self._the_ones_that()}\n"
            + "\n".join(lines) + note)
        # AND WHICH COLOURS DID THE MOVING. Two PROFILES are two
        # characterisations, not the device, so the footnote says so -- the
        # opposite of what a measurement pair gets, which is why the helper
        # is told which it is being handed rather than guessing.
        self._say_drift_families(
            d.lab_a, d.lab_b,
            f"{Path(path_a).stem} → {Path(path_b).stem}", of="profiles")

    @staticmethod
    def _fmt_volume(value: float) -> str:
        """A volume with enough figures to be worth reading.

        Lab and Luv run 0..100 per axis, so their volumes are hundreds of
        thousands and want thousands separators. XYZ runs 0..1, so the same
        format rounded every real answer to "0". The number of significant
        figures follows the size rather than the space, which also keeps a
        very small measured gamut readable in any of them.
        """
        if value >= 1000:
            return f"{value:,.0f}"
        if value >= 1:
            return f"{value:,.2f}"
        return f"{value:.4f}"

    def _volume_units(self) -> str:
        """What the volume figure is counted in, for the space now chosen.

        Never hard-coded to Lab: a number labelled "cubic Lab units" beside a
        shape drawn in Luv or XYZ would be wrong, and volumes are not
        comparable between spaces.

        THE SPACE IT WAS BUILT IN, not the one on the axes. In ink amounts
        those are different: the shapes are still measured in CIELAB, they
        are simply not drawn, so their volumes are Lab volumes and saying
        otherwise would put an ink unit on a colour measurement.
        """
        from gamutview import AXES
        return AXES[self._build_space()]["units"]

    def _update_range(self) -> None:
        """How black the blacks go and how bright the paper is.

        After the volume, this is the pair of numbers a printer looks for: a
        paper that cannot go dark loses shadow detail whatever its gamut
        volume says. Needs a lightness axis, so it is left blank in CIE XYZ.
        """
        from gamutview import (AXES, describe_white, hidden_end,
                               lightness_range, paper_white)
        if not self._slots or not AXES[self._space.currentData()]["cylindrical"]:
            self._range.setText("")
            return
        try:
            lines = []
            lost = []
            for path, g, _m in self._slots:
                dark, light = lightness_range(g)
                # AND WHAT COLOUR THAT WHITE IS. Every other number in this
                # window is blind to it -- volume barely moves when a white
                # shifts, and coverage only counts points in or out -- so two
                # papers can read as near-identical here while one is a cool
                # brightened white and the other a warm cream, which is
                # visible on every print at a glance. See paper_white().
                lab = paper_white(g)
                how = describe_white(lab)
                tint = (" and neutral" if how == "neutral"
                        else f" and {how} (a* {lab[1]:+.1f}, b* {lab[2]:+.1f})")
                lines.append(f"{path.stem}: blacks reach L* {dark:.0f}, "
                             f"paper white L* {light:.0f}{tint}")
                # AND WHETHER THAT END CAN ACTUALLY BE SEEN. The numbers above
                # are printed whether or not the shape they describe is
                # visible, and at one end of the picture it may not be: a
                # glossy paper's blacks come within four levels of a dark
                # page. Saying "blacks reach L* 4" beside a part of the shape
                # nobody can make out is the readout quietly disagreeing with
                # the picture. Only for True colours, because that is the only
                # painting that uses the measured colour -- By lightness and
                # the rest already draw both ends in something visible, which
                # is exactly what the note goes on to suggest.
                if getattr(self, "_paint", "true") == "true":
                    end = hidden_end(g, self._page_colour())
                    if end is not None:
                        lost.append((path.stem, *end))
            # INSIDE THE GUARD, not after it. The promise on this method is
            # that a readout never takes the view down with it, and a note
            # built outside the try would be the one line here that could.
            note = self._hidden_end_note(lost)
            if note:
                lines.append(note)
        except Exception:      # noqa: BLE001 — a readout must never crash a view
            self._range.setText("")
            return
        self._range.setText("\n".join(lines))

    def _page_colour(self) -> str:
        """The colour actually behind the shape in the view, right now.

        Read rather than assumed. The window has a light appearance as well as
        a dark one and they hide OPPOSITE ends of the shape -- the dark page
        loses the blacks, the light page loses the paper white -- so a rule
        written against either one alone would be wrong half the time.

        Only the two themes are consulted. The colour pickers further up this
        file belong to the still-picture dialog and change what is exported,
        not what is on screen here; reading one of those would warn about a
        page the reader is not looking at.
        """
        from ti3gamut import SCENE_COLOURS
        which = ("light" if getattr(self, "_appearance", "dark") == "light"
                 else "dark")
        return SCENE_COLOURS[which]["page"]

    @staticmethod
    def _hidden_end_note(lost) -> str:
        """One plain sentence about an end of the shape that cannot be seen.

        Written out in full for one shape and for two rather than with an
        "(s)", because a reader should never have to do grammar to read a
        warning. Both ends need their own verb as well: "blacks" is plural and
        "paper white" is not, and one sentence serving both produced "Glossy's
        paper white come within four levels", which is the kind of thing that
        makes a reader distrust the number beside it.
        """
        if not lost:
            return ""
        which = lost[0][1]
        blacks = which == "blacks"
        end = "deepest black" if blacks else "brightest white"
        near = min(g for _n, _w, _s, g in lost)
        share = max(s for _n, _w, s, _g in lost)
        if len(lost) == 1:
            who = f"{lost[0][0]}'s {which} {'come' if blacks else 'comes'}"
            reach = "the paper reaches"
            it = "them" if blacks else "it"
        else:
            names = " and ".join(n for n, *_ in lost)
            plural = "blacks" if blacks else "paper whites"
            who = f"{names} have {plural} that come"
            reach = "either paper reaches"
            it = "them"
        return (f"{who} within {near:.0f} levels of the page behind {it}, so "
                f"{share:.0f}% of that end is drawn but cannot be seen — and "
                f"it is the {end} {reach}. Under “How the shapes are "
                f"coloured”, choose “By lightness” to see it.")

    def _update_volume(self) -> None:
        self._update_range()
        if not self._slots:
            # Only a comparison is open. It is still a shape with a size, and
            # saying nothing here while one is plainly on screen reads as a
            # fault rather than as a blank.
            if self._reference is not None:
                name, g = self._reference
                self._volume.setText(self._fmt_volume(g.volume))
                self._volume_hint.setText(
                    f"{name}, measured in {self._volume_units()}. Open a chart "
                    "or a profile as well and the two are compared.")
            else:
                self._volume.setText("—")
                self._volume_hint.setText("")
            return
        if len(self._slots) == 1:
            g = self._slots[0][1]
            self._volume.setText(self._fmt_volume(g.volume))
            self._volume_hint.setText(
                f"Measured in {self._volume_units()}. It is useful for "
                "comparing two papers measured the same way — on its own the "
                "number does not mean much, and it cannot be compared with a "
                "figure from another space.")
        else:
            (_, a, _), (_, b, _) = self._slots
            self._volume.setText(
                f"{self._fmt_volume(a.volume)}  ·  {self._fmt_volume(b.volume)}")
            big, small = max(a.volume, b.volume), min(a.volume, b.volume)
            which = (self._slots[0][0].stem if a.volume > b.volume
                     else self._slots[1][0].stem)
            self._volume_hint.setText(
                f"{which} holds {100 * (big / small - 1):.1f}% more colour "
                "than the other one.")


def main(argv=None) -> int:
    from logger import configure, get_logger, install_exception_hook
    _log = configure()
    install_exception_hook()
    get_logger("app").info("log file: %s", _log or "(could not be opened)")
    argv = list(sys.argv if argv is None else argv)
    if "--version" in argv:
        print(f"{APP_NAME} {__version__}")
        return 0
    app = QApplication(argv)
    # The icon lives beside the code in development and beside the executable
    # once frozen, so both places are tried rather than one assumed.
    for candidate in (Path(__file__).resolve().parent.parent / "assets" / "icon.png",
                      Path(getattr(sys, "_MEIPASS", ".")) / "assets" / "icon.png"):
        if candidate.is_file():
            app.setWindowIcon(QIcon(str(candidate)))
            break
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(_QSS)
    files = [Path(a) for a in argv[1:] if not a.startswith("-")]
    win = GamutApp(files)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
