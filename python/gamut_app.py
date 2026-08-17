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
from PyQt6.QtCore import (QEvent, QRect, QSettings, QSize, QStandardPaths, Qt,
                          QTimer, QUrl, pyqtSignal)
from PyQt6.QtGui import (QColor, QDesktopServices, QFont, QFontMetrics,
                         QIcon, QImage, QLinearGradient,
                         QPainter, QPalette,
                         QPen, QPixmap)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
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

from version import APP_NAME, __version__
from gamutview import SPACES, build_gamut, coverage, outside_of
from gamutview import xyz_to_lab
from references import (REFERENCE_SPACES, gam_gamut, icc_gamut,
                        reference_gamut)
from spectral import optimal_colour_solid
from ti3gamut import (CONVERTERS, compare_measurements, neutral_axis,
                      read_measurement, write_html, write_slice_html)

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
        accent="#ff4573", accent_hot="#ff6b90", on_accent="#ffffff",
        second="#262626",        # BG_WIDGET    — default button fill
        second_hover="#3a3a3a",
        plot_bg="#111111",       # the 3D viewer fill, gamut_panel.py:86
        grid="#262626", arrow="#e6e6e6",
        # THE INSIDE OF ANYTHING YOU OPEN OR TYPE IN -- a list, a number box,
        # an empty tickbox. On a dark window that is an inset, darker than the
        # surface around it, which is what BG_DARK already was.
        field="#101010",
        kept="rgb(105,112,126)"),
    "light": dict(
        bg="#eeece8",            # LM_BG_WINDOW
        panel="#f7f4ef",         # LM_BG_SURFACE — group-box fill
        line="#d0ccc6",          # LM_BORDER
        line_soft="#b0aba4",     # LM_BORDER_HI
        text="#22211f",          # LM_TEXT_MAIN
        dim="#7a7570",           # LM_TEXT_DIM
        faint="#a8a4a0",         # LM_TEXT_FAINT
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
QPushButton:disabled {{ background: {c["second"]}; color: {c["faint"]}; }}
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
QPushButton#closer {{ background: transparent; color: {c["faint"]};
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
QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {c["faint"]}; }}
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
QLabel#hint {{ color: {c["faint"]}; font-size: 11px; }}
/* The two links at the foot of the column. Not buttons competing with the
   controls above: quiet text that takes the accent when pointed at, the way
   a link does. */
/* Links, and they look like links: in the accent at rest, so they are
   findable, and brighter when pointed at. Grey text that only turns
   colourful under the pointer is a link nobody knows is there. */
QPushButton#footLink {{ background: transparent; border: none; padding: 2px 0;
                        color: {c["accent"]}; font-size: 11px;
                        text-align: left; min-height: 0; }}
QPushButton#footLink:hover {{ color: {c["accent_hot"]};
                              text-decoration: underline; }}
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
QToolButton#hintToggle {{ color: {c["faint"]}; font-size: 11px;
                          border: none; background: transparent;
                          padding: 1px 0; text-align: left; }}
QToolButton#hintToggle:hover {{ color: {c["accent"]}; }}
QToolButton#hintToggle:checked {{ color: {c["dim"]}; }}
/* The two words that name a group of choices below them, rather than
   labelling one control beside them. They read as headings, so they are set
   as headings. */
QLabel#prefsHeading {{ color: {c["text"]}; font-weight: 600; }}
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
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Fixed if hug
                           else QSizePolicy.Policy.MinimumExpanding)
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
        if self._hug and needed != self.maximumHeight():
            self.setMaximumHeight(needed)

    def resizeEvent(self, event) -> None:      # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._refit()

    def setText(self, text: str) -> None:      # noqa: N802 (Qt naming)
        super().setText(text)
        self._refit()


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
    """A slider with the same rule, for the same reason."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:        # noqa: N802 (Qt naming)
        if self.hasFocus():
            super().wheelEvent(event)
        else:
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


class Stopped(Exception):
    """The person stopped it. Not a fault, and never reported as one."""


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

    def __init__(self, parent) -> None:
        super().__init__(parent)
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
            for i, (name, label, default, why) in enumerate(items):
                check = QCheckBox(label, box)
                check.setChecked(default)
                self._offer[name] = check
                grid.addWidget(check, i, 0)
                hint = Hint(why, box)
                hint.setObjectName(f"hint_offer_{name}")
                grid.addWidget(hint, i, 1, Qt.AlignmentFlag.AlignVCenter)
                hint.follow(check)
            stack.addWidget(box)
            self._offer_groups.append(box)
            strip.toggled.connect(box.setEnabled)
        stack.addStretch(1)

        area = FadingScrollArea(self)
        area.setWidget(held)
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
                # NOT INSIDE "offer", THOUGH IT SITS BESIDE ONE. The offers say
                # which CONTROLS the reader is handed; this says how the page
                # BEHAVES before they touch anything, and it applies just as
                # much to a page saved with no controls at all.
                "glide": self._glide.isChecked(),
                "offer": {name: box.isChecked()
                          for name, box in self._offer.items()}}


class TimelineDialog(QDialog):
    """One device, several profiles of it, and how far it has moved.

    WHY THIS IS NOT PART OF THE MAIN WINDOW. That window holds at most two
    files and compares their SHAPES: how much colour each holds, how much they
    share, which reaches further in which hues. Eighteen places in it depend on
    there being one or two, and every one of them is right to. This asks a
    different question — has one device moved, and how fast — of as many
    profiles as somebody has. A list and a graph, not a gamut.

    Keeping them apart is what stops the reader having to work out which of
    two similar-looking answers applies to them.
    """

    #: How finely each profile is sampled, per channel. The same grid the pair
    #: comparison uses, because there is nothing to gain by coarsening it:
    #: measured, ten comparisons take under a hundredth of a second.
    GRID = 9

    def __init__(self, parent, appearance: str = "dark",
                 preview: bool = True) -> None:
        """*preview* False builds the window without its graph view.

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
        self._preview = preview
        self.setWindowTitle("Follow one device over time")
        self.setModal(False)          # so files can be dragged in from Finder
        self._appearance = appearance
        self._paths: list = []
        self._run = None
        self.resize(940, 720)
        self.setMinimumSize(560, 460)
        self.setAcceptDrops(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        head = QLabel("Open the profiles you have of one device — a scanner, "
                      "a printer, a screen — made on different days.", self)
        head.setWordWrap(True)
        row = QHBoxLayout()
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
        outer.addLayout(row)

        self._list = QListWidget(self)
        self._list.setMaximumHeight(150)
        self._list.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove)
        self._list.setToolTip(
            "The profiles in this run, oldest first. Drag a row to move it.")
        self._list.model().rowsMoved.connect(self._reordered)
        outer.addWidget(self._list)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        add = QPushButton("Add profiles…", self)
        add.setToolTip("Choose one or more ICC profiles of the same device.")
        add.clicked.connect(self._on_add)
        self._remove_btn = QPushButton("Remove the selected one", self)
        self._remove_btn.setObjectName("secondary")
        self._remove_btn.clicked.connect(self._on_remove)
        self._clear_btn = QPushButton("Remove them all", self)
        self._clear_btn.setObjectName("secondary")
        self._clear_btn.clicked.connect(self._on_clear)
        for b in (add, self._remove_btn, self._clear_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        self._save_btn = QPushButton("Save this as a web page…", self)
        # SECONDARY, like every other export in this application. Adding
        # profiles is the one thing this window is for until there are some,
        # so it keeps the accent; two accent buttons side by side is two
        # things claiming to be the main one.
        self._save_btn.setObjectName("secondary")
        self._save_btn.setToolTip(
            "One file that opens in any browser, with the graph in it. "
            "Nothing needs installing to read it.")
        self._save_btn.clicked.connect(self._on_save)
        self._table_btn = QPushButton("Save the numbers as a table…", self)
        self._table_btn.setObjectName("secondary")
        self._table_btn.setToolTip(
            "Every step as a row, for a spreadsheet — with what the numbers "
            "do and do not mean written beside them.")
        self._table_btn.clicked.connect(self._on_table)
        buttons.addWidget(self._table_btn)
        buttons.addWidget(self._save_btn)
        outer.addLayout(buttons)

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

        self._verdict = WrappedLabel("", self, hide_when_empty=True)
        outer.addWidget(self._verdict)
        self._complaints = WrappedLabel("", self, hide_when_empty=True)
        self._complaints.setObjectName("hint")
        outer.addWidget(self._complaints)

        # THE CAVEAT LIVES BESIDE THE GRAPH, not only behind the ⓘ. A trend
        # line is the kind of picture people trust more than they should, and
        # somebody who never opens the help will still read this.
        self._caution = WrappedLabel(
            "Remember: this is how far apart the PROFILES are, not how far "
            "the device drifted. Chart fade and any change in how you built "
            "them are inside these numbers too.", self)
        self._caution.setObjectName("hint")
        outer.addWidget(self._caution)

        self._refresh()

    # --- the list ----------------------------------------------------------

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
        here = {p.resolve() for p in self._paths}
        for raw in paths:
            path = Path(raw)
            try:
                if path.resolve() in here:
                    continue
            except OSError:
                pass
            self._paths.append(path)
        self._rebuild()

    def _on_add(self) -> None:
        parent = self.parent()
        chooser = parent._file_dialog(
            "Choose profiles of one device", QFileDialog.FileMode.ExistingFiles,
            "ICC profiles (*.icc *.icm)", profiles=True)
        if chooser.exec():
            self.add(chooser.selectedFiles())

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
            item = QListWidgetItem(text, self._list)
            item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
            item.setToolTip(str(entry.path))
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
            self._complaints.setText(
                "Nothing open yet. Add two or more profiles of one device.")
            self._blank()
            return

        self._verdict.setText(drift_series.verdict(self._run))
        said = list(self._run.complaints)
        if drawable and self._run.ordered_by != "date":
            said.append(
                "These are in the order you added them, because not every "
                "profile carries a usable date. Drag a row to move it.")
        self._complaints.setText("\n\n".join(said))
        self._draw()

    def _draw(self) -> None:
        """Put the graph in the view, writing into the window's own folder.

        THE PARENT'S TEMPORARY FOLDER, not one of this dialog's own. That
        folder is swept at startup and removed when the window closes, so a
        page written into it cannot become the kind of litter that once left
        644 folders and 27 GB behind. A second folder here would be a second
        thing to remember to clean up.
        """
        import drift_series

        if self._view is None:
            return
        if not (self._run and self._run.since_first):
            self._blank()
            return
        figure = drift_series.figure(self._run, mode=self._appearance)
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
        """Empty the graph, when there is one to empty."""
        if self._view is not None:
            self._view.setHtml("")

    def look(self, appearance: str) -> None:
        """Follow the window's light/dark setting."""
        if appearance != self._appearance:
            self._appearance = appearance
            self._paint_view()
            self._draw()

    # --- taking it away ----------------------------------------------------

    def _on_save(self) -> None:
        import drift_series

        parent = self.parent()
        first = self._run.usable[0].name if self._run.usable else "device"
        chooser = parent._file_dialog(
            "Where should the page go?", QFileDialog.FileMode.AnyFile,
            "Web page (*.html)", f"{first}-over-time.html", profiles=False)
        chooser.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        chooser.setDefaultSuffix("html")
        if not chooser.exec():
            return
        target = Path(chooser.selectedFiles()[0])
        figure = drift_series.figure(
            self._run, mode=self._appearance,
            title=f"How far {first} has moved")
        try:
            target.write_text(self.page_html(figure), encoding="utf-8")
        except OSError as exc:
            Notice.warn(self, "That could not be saved", str(exc))
            return
        Notice.say(self, "Saved",
                   f"Written to\n{target}\n\nIt opens in any browser, and the "
                   f"sentence explaining what the lines do and do not mean is "
                   f"saved with it.")

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

    def page_html(self, figure) -> str:
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

        from ti3gamut import SCENE_COLOURS
        c = SCENE_COLOURS["light" if self._appearance == "light" else "dark"]
        body = figure.to_html(full_html=False, include_plotlyjs=True,
                              config={"displayModeBar": False},
                              default_height="100%", div_id="timeline")
        first = self._run.usable[0].name if self._run.usable else "this device"
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
 @media (max-width:520px) {{ .picture {{ height:60vh; }} }}
</style></head><body>
<div class="picture">{body}</div>
<div class="words">
<p class="verdict">{_escape(drift_series.verdict(self._run))}</p>
<p class="caveat"><b>What this does not tell you.</b> These lines show how far
apart the <b>profiles</b> are, not how far the device drifted. Each profile
records one day's measurements of one chart, so if the charts faded between
them, or they were built differently, that is inside these numbers too. A line
that climbs steadily is just as consistent with charts ageing as with a device
drifting, and no arithmetic can separate the two.</p>
<p class="caveat">The numbers are ΔE2000. Below 1 nobody can see the
difference; above 3 anybody can.</p>
</div></body></html>
"""

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

    def __init__(self, text: str, parent=None, *, title: str = "") -> None:
        super().__init__(parent)
        self._text = text
        self._title = title or "About this setting"
        self.setObjectName("hintIcon")
        self.setFixedSize(QSize(Hint.ICON + 4, Hint.ICON + 4))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.setVisible(control.isVisible())

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
        self._store = QSettings("MeasuredGamutViewer", "MeasuredGamutViewer")
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
        v.setContentsMargins(0, 0, 0, 0)
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
            shut.setCursor(Qt.CursorShape.PointingHandCursor)
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
            "Closes everything open at once — both of the shapes, whatever "
            "kind of file they came from, and the chart with them if one is "
            "open.\n\n"
            "To close just one, use the × beside its name. Nothing is deleted "
            "either way: closing only takes it off the screen, and the files "
            "on your drive are untouched.")
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
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        self._chart_label = WrappedLabel("", row)
        self._chart_label.setObjectName("slot")
        rl.addWidget(self._chart_label, 1)
        shut = QPushButton("×", row)
        shut.setObjectName("closer")
        shut.setFixedSize(22, 22)
        shut.setToolTip("Close this chart")
        shut.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self._chart_dot.valueChanged.connect(lambda _v: self._redraw())
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
        self._chart_dot_opacity.setRange(10, 100)
        self._chart_dot_opacity.setValue(100)
        self._chart_dot_opacity.valueChanged.connect(lambda _v: self._redraw())
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
        self._chart_out_dot.valueChanged.connect(lambda _v: self._redraw())
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
        self._chart_out_opacity.setRange(10, 100)
        self._chart_out_opacity.setValue(100)
        self._chart_out_opacity.valueChanged.connect(lambda _v: self._redraw())
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
        self._chart_skin_opacity.setRange(5, 100)
        self._chart_skin_opacity.setValue(30)
        self._chart_skin_opacity.valueChanged.connect(lambda _v: self._redraw())
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
        self._target.addItem("all shapes together", "all")
        self._target.addItem("the first shape", 0)
        self._target.addItem("the second shape", 1)
        self._target.addItem("the comparison", 2)
        self._target.currentIndexChanged.connect(self._on_target_changed)
        target_hint = Hint(
            "Everything below applies to whatever is chosen here. Leave it on "
            "all shapes together and one change moves them all, which is what "
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
        orow.addWidget(QLabel("How solid it looks", g_look))
        self._opacity = NoScrollSlider(Qt.Orientation.Horizontal, g_look)
        # FULLY OPAQUE BY DEFAULT. Any transparency blends the shape with
        # whatever is behind it -- which darkens colours on a dark background
        # and washes them out on a light one, so the same setting flattered one
        # appearance and spoiled the other. Solid shows the measured colours as
        # they are; the slider is there for looking inside two shapes at once.
        self._opacity.setRange(15, 100); self._opacity.setValue(100)
        self._opacity.valueChanged.connect(self._on_opacity_changed)
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
        self._grid_on = QCheckBox("Show the box and its grid", g_look)
        self._grid_on.setChecked(True)
        self._grid_on.stateChanged.connect(self._redraw)
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
        lv.addWidget(self._slice_on)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Lightness", g_look))
        self._slice_at = NoScrollSlider(Qt.Orientation.Horizontal, g_look)
        self._slice_at.setRange(0, 100)
        self._slice_at.setValue(50)
        self._slice_at.valueChanged.connect(
            lambda v: self._slice_lbl.setText(f"L* {v}"))
        self._slice_at.sliderReleased.connect(self._redraw)
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
        drow.addWidget(QLabel("Depth", g_look))
        self._depth = NoScrollSlider(Qt.Orientation.Horizontal, g_look)
        self._depth.setRange(0, 100)
        self._depth.setValue(35)
        self._depth.valueChanged.connect(self._on_depth_changed)
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
        self._outline_paint.addItem("the same as the shapes", "match")
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
            "form. Choose the same as the shapes and the cage stays in step "
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
        self._rings.valueChanged.connect(
            lambda v: self._rings_lbl.setText(str(v)))
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
        self._detail.valueChanged.connect(
            lambda v: self._detail_lbl.setText(f"{v} steps"))
        self._detail.sliderReleased.connect(self._on_compare_changed)
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
        self._show_lost = QCheckBox("Show what the comparison cannot print",
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
        self._agree.valueChanged.connect(
            lambda v: self._agree_lbl.setText("all of it" if v == 100
                                              else ("hidden" if v == 0
                                                    else f"{v}%")))
        self._agree.sliderReleased.connect(self._redraw)
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
        self._differ.valueChanged.connect(
            lambda v: self._differ_lbl.setText("all of it" if v == 100
                                               else ("hidden" if v == 0
                                                     else f"{v}%")))
        self._differ.sliderReleased.connect(self._redraw)
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

        self._neutral = QCheckBox("Show the greys", g_look)
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

        self._ideal_neutral = QCheckBox("…and a perfectly neutral line",
                                        g_look)
        self._ideal_neutral.setEnabled(False)      # nothing to compare yet
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
        _r = QHBoxLayout(); _r.setContentsMargins(16, 0, 0, 0)
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

        self._side_by_side = QCheckBox("Show them in two rooms, side by side",
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
        self._link_cameras = QCheckBox("Keep both rooms pointing the same way",
                                       self._link_row)
        self._link_cameras.setChecked(True)
        self._link_cameras.stateChanged.connect(self._redraw)
        _lr.addWidget(self._link_cameras)
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
        _lr.addWidget(link_hint)

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
        dv.addLayout(_r)
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

        self._reset_btn = QPushButton("Start again with standard settings",
                                      col)
        self._reset_btn.setObjectName("secondary")
        self._reset_btn.clicked.connect(self._reset_defaults)
        v.addWidget(self._reset_btn)
        self._export_btn = QPushButton("Save the numbers as a table…", col)
        self._export_btn.setObjectName("secondary")
        self._export_btn.clicked.connect(self._on_export)
        self._export_btn.setEnabled(False)
        v.addWidget(self._export_btn)
        # A SEPARATE QUESTION, SO A SEPARATE WINDOW. Everything above compares
        # what is open right now -- at most two shapes, held side by side. This
        # follows ONE device through as many profiles as somebody has of it,
        # which is a question about time rather than about shape, and it wants
        # a list and a graph rather than a gamut. Putting it in this column
        # beside the other "do something with all this" buttons keeps it
        # findable without pretending it is one more way of drawing a shape.
        self._timeline_btn = QPushButton("Follow one device over time…", col)
        self._timeline_btn.setObjectName("secondary")
        self._timeline_btn.setToolTip(
            "Open several profiles of the SAME device, made on different "
            "days, and see how far it has moved between them.")
        self._timeline_btn.clicked.connect(self._on_timeline)
        v.addWidget(self._timeline_btn)
        self._glossary_btn = QPushButton("What do these words mean?", col)
        self._glossary_btn.setObjectName("secondary")
        self._glossary_btn.clicked.connect(self._on_glossary)
        v.addWidget(self._glossary_btn)
        # ARGYLLCMS, MENTIONED BUT NEVER NAGGED ABOUT. Most people never need
        # it: measurements, gamut files and profiles all open without it, and
        # only .cxf, .mxf and .txt are converted by it. So there is no warning
        # on startup and no badge -- just a quiet line for anybody who wonders,
        # and a way to point at it when the search cannot find it.
        self._argyll_label = WrappedLabel("", col)
        self._argyll_label.setObjectName("argyllStatus")
        v.addWidget(self._argyll_label)
        argyll_row = QHBoxLayout()
        argyll_row.setContentsMargins(0, 0, 0, 0)
        argyll_row.setSpacing(6)
        self._argyll_btn = QPushButton("Where ArgyllCMS is…", col)
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
            "button offers the download page — it is free.", col)
        argyll_hint.setObjectName("hint_argyll_hint")
        argyll_row.addWidget(argyll_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(argyll_row)

        # THE ENCODER, ON THE SAME FOOTING AS ARGYLLCMS: mentioned quietly for
        # anybody who wonders, never nagged about. One copy travels with the
        # application, so for most people this line only ever says so.
        self._ffmpeg_label = WrappedLabel("", col)
        self._ffmpeg_label.setObjectName("argyllStatus")
        v.addWidget(self._ffmpeg_label)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.setContentsMargins(0, 0, 0, 0)
        ffmpeg_row.setSpacing(6)
        self._ffmpeg_btn = QPushButton("Where ffmpeg is…", col)
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
            "free, and there is a build for every system.", col)
        ffmpeg_hint.setObjectName("hint_ffmpeg_hint")
        ffmpeg_row.addWidget(ffmpeg_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(ffmpeg_row)

        self._update_btn = QPushButton("Check for a newer version…", col)
        self._update_btn.setObjectName("secondary")
        self._update_btn.clicked.connect(lambda: self._check_updates(asked=True))
        v.addWidget(self._update_btn)
        self._auto_update = QCheckBox("Look for a newer version when the app starts", col)
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
            "the button just above.", col)
        update_hint.setObjectName("hint_update_hint")
        # THE ONLY TICKBOX IN A COLUMN OF BUTTONS, so it goes at the end
        # rather than in the middle of them: sitting between two buttons it
        # read as a stray control that had lost its group.
        self._auto_update_row = QHBoxLayout()
        self._auto_update_row.setContentsMargins(0, 0, 0, 0)
        self._auto_update_row.setSpacing(6)
        self._auto_update_row.addWidget(self._auto_update, 1)
        self._auto_update_row.addWidget(update_hint, 0,
                                        Qt.AlignmentFlag.AlignVCenter)
        self._picture = QPushButton("Save this view as a picture…", col)
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
            "file that is already there is never written over.", col)
        picture_hint.setObjectName("hint_picture_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0); _r.setSpacing(6)
        _r.addWidget(self._picture, 1)
        _r.addWidget(picture_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(_r)
        self._save = QPushButton("Save this view as a web page…", col)
        self._save.setObjectName("secondary")
        self._save.clicked.connect(self._on_save)
        self._save.setEnabled(False)
        self._export_btn.setEnabled(False)
        v.addWidget(self._save)

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
        # LAST, once every group exists. Run partway down the column it tidied
        # the groups built so far and left the rest as they were, which looks
        # exactly like a bug in the ones it missed.
        self._tighten_groups(col)
        v.addLayout(self._auto_update_row)
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

    def _readout_text(self) -> str:
        """Everything the readouts are showing, as plain text.

        Read from the labels themselves rather than worked out again, so the
        page cannot disagree with the window it came from.
        """
        parts = []
        volume = self._volume.text().strip()
        if volume and volume != "—":
            parts.append(f"Colour held: {volume} {self._volume_units()}")
        for name in ("_coverage", "_picture_loss", "_pair", "_drift", "_drift_worst",
                     "_chart_headline", "_chart_rows", "_chart_spread"):
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
        if self._chart is not None and self._chart_placed is not None:
            names.append(self._chart[0].stem)
        return names

    def _on_picture(self) -> None:
        """Save what is on screen as a picture."""
        if (not self._slots and self._reference is None
                and not self._chart_drawable()):
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
        self._run_js_now(
            "(function(){var d=document.getElementsByClassName("
            "'plotly-graph-div')[0];"
            f"if(d)Plotly.relayout(d,{json.dumps(want)});}})()")

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
        if self._slots:
            self._redraw()          # the scene is repainted to match

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
        needs = max(346, column.minimumSizeHint().width(),
                    *(box.minimumSizeHint().width()
                      for box in column.findChildren(QGroupBox)) or (0,))
        if needs > column.minimumWidth():
            column.setFixedWidth(needs)
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
        if self._placed:
            return
        self._placed = True
        # Re-apply now the window is actually up: a setVisible(False) issued
        # while the parent was still hidden does not survive the parent being
        # shown, so the controls that depend on what is loaded have to be
        # settled here as well as during construction.
        self._apply_side_by_side_availability()
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
        for box in root.findChildren(QGroupBox):
            if box.layout() is not None:
                self._attach_in_layout(box.layout(), box)

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
            if not isinstance(hint, Hint) or i == 0:
                i += 1
                continue
            j = i - 1
            while j >= 0:
                candidate = layout.itemAt(j)
                widget = candidate.widget()
                if candidate.layout() is not None:
                    break
                if widget is not None and widget.isVisibleTo(box):
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
        self._sync_slider_labels()
        self._on_manual_light()

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

    def _after_shape_setting(self, key: str) -> None:
        """Record a per-shape (or shared) value, then repaint."""
        self._remember_shape_setting(key)
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
        return d.lab_a, d.deltas, "how far it moved"

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
        for label, delta, lab_a, lab_b in d.worst_patches:
            rows.append((f"moved most: {label}", f"{delta:.2f}",
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
        """Open the timeline window, or bring the open one forward.

        ONE WINDOW, NOT ONE PER CLICK. Pressing the button twice should show
        the run already being built, not a second empty list beside it -- and
        a second window would keep its own list, so the user would have two
        answers and no way to tell which was which.
        """
        existing = getattr(self, "_timeline", None)
        if existing is not None:
            try:
                existing.look(self._appearance)
                existing.show()
                existing.raise_()
                existing.activateWindow()
                return
            except RuntimeError:
                pass            # Qt deleted it; make a new one below
        self._timeline = TimelineDialog(self, appearance=self._appearance)
        # OPENED WITH WHAT IS ALREADY IN FRONT OF THEM. Somebody who has two
        # profiles open and presses this means those two, and being handed an
        # empty list would read as the button having done nothing.
        already = [p for p, _g, m in self._slots
                   if m is None and p.suffix.lower() in (".icc", ".icm")]
        if already:
            self._timeline.add(already)
        self._timeline.show()

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
        """Close everything on screen — which now includes the chart."""
        self._slots.clear()
        self._chart = None
        self._chart_placed = None
        self._refresh_slot_labels()
        self._refresh_chart_panel()
        self._fill_chart_profiles()
        self._show_placeholder()
        self._volume.setText("—")
        self._volume_hint.setText(self._volume_units())
        self._clear_btn.setVisible(False)
        self._save.setEnabled(False)

    def _on_save(self) -> None:
        """Write the scene as a standalone page the user can keep or send.

        Saved beside the first measurement by default, because that is where
        the user will look for it, and it carries its own viewer so it still
        opens with no network and no ChromIQ.
        """
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
                              controls=chosen.get("controls", True),
                              offer=chosen.get("offer"),
                              glide=chosen.get("glide", False),
                              carry_viewer=chosen["carry_viewer"],
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
        if len(self._slots) >= 2:
            self._slots.pop(0)                 # newest two win
        try:
            g, m = self._build_one(path)
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
        self._slots.append((path, g, m))
        # A FILE MAY HAVE CHANGED ON DISK since it was last judged against.
        # The cache is keyed by path, so an edited measurement reopened under
        # the same name would be judged against the shape it used to have.
        # Emptying it here costs one rebuild and cannot be wrong.
        self._lab_gamuts.clear()
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

    def _build_one(self, path: Path):
        """The gamut of one file, whichever kind it is.

        A profile has no patches, so there is no Measurement to return with
        it -- everything downstream treats that None as "this one was not
        measured" rather than assuming a chart.
        """
        suffix = path.suffix.lower()
        if suffix in (".icc", ".icm", ".gam"):
            reader = gam_gamut if suffix == ".gam" else icc_gamut
            return reader(path, white_point=self._white.currentData(),
                          space=self._build_space()), None
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
        "This window",
    })

    #: Controls inside a space-dependent section that are nonetheless the same
    #: in every space, each with the reason it is exempt. Attribute names,
    #: because that is what somebody grepping for it would type.
    SPACE_INDEPENDENT = {
        "_space": "the control that chooses the space cannot depend on it",
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
                g, m = self._build_one(path)
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

    def _spin_options(self, glide: bool = False) -> dict:
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
            layout.setContentsMargins(left, top, right, 2)
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

    def _refresh_style_controls(self) -> None:
        """Show a style control only when the shape it governs is on screen.

        A control for something that does not exist is worse than no control:
        it invites a change that does nothing and leaves somebody wondering
        what they did wrong.
        """
        have = (len(self._slots) >= 1, len(self._slots) >= 2,
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
                shown = QFontMetrics(lab.font()).elidedText(
                    path.stem, Qt.TextElideMode.ElideMiddle, _TEXT_WIDTH - 34)
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

    def _manual_lighting(self) -> dict:
        """The five values as the sliders currently stand."""
        out = {}
        for key, (slider, lo, hi) in self._light_sliders.items():
            out[key] = lo + (hi - lo) * slider.value() / 100.0
        return out

    def _on_light_changed(self, key: str, value: float, label) -> None:
        label.setText(f"{value:.2f}")
        if self._manual_light.isChecked():
            self._push_lighting(self._manual_lighting())

    def _push_lighting(self, values: dict) -> None:
        """Send a lighting dictionary into the scene already on screen."""
        page = self._view.page()
        if page is None or not self._slots:
            return
        body = ",".join(f"'{k}':{v}" for k, v in values.items())
        page.runJavaScript(
            "(function(){var el=document.getElementsByClassName("
            "'plotly-graph-div')[0];"
            "if(!el||!window.Plotly||!el.data)return;"
            "var idx=[];for(var i=0;i<el.data.length;i++)"
            "if(el.data[i].type==='mesh3d')idx.push(i);"
            f"if(idx.length)Plotly.restyle(el,{{lighting:{{{body}}}}},idx);"
            "})();")

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

    def _on_opacity_changed(self, value: int) -> None:
        """Change how solid the shapes look, live, as the slider moves.

        Rebuilding the whole page for each step would take long enough that the
        picture only caught up after letting go, which is not what a slider is
        for. Plotly can restyle a scene that is already on screen, so the
        change is pushed straight into the page: the shapes fade as you drag,
        the camera stays exactly where you put it, and nothing is recomputed.
        """
        page = self._view.page()
        if page is None or not self._slots:
            return
        page.runJavaScript(
            "(function(){var d=document.getElementsByClassName("
            "'plotly-graph-div')[0];"
            f"if(d&&window.Plotly)Plotly.restyle(d,{{opacity:{value / 100.0}}});"
            "})();")

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
        for _slider, _label in ((self._agree, self._agree_lbl),
                                (self._differ, self._differ_lbl)):
            _slider.setEnabled(can_split)
            _label.setEnabled(can_split)
            _slider.setToolTip(
                "" if can_split else
                self._why_not_in_this_space("shapes") if not shapes else
                "Open a second measurement, or choose something under Compare "
                "with, and these can fade the part the two of them share, or "
                "the parts only one of them reaches.")

    def _redraw(self) -> None:
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
        self._view.setUrl(QUrl.fromLocalFile(str(out)))
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
                     notes: str = "", offer=None, glide: bool = False) -> bool:
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
        if self._slice_on.isChecked():
            # A CROSS-SECTION IS DRAWN FLAT, LOOKING DOWN. There is no camera,
            # so no movement settings travel with it and the strip leaves out
            # everything about movement -- but it does get a strip. Zooming,
            # moving and getting back to the opening view are as useful on a
            # cut as on a shape, and on a phone the drawing library's own
            # toolbar is hidden, so without one there was no way back from a
            # zoom at all.
            if self._side_by_side.isChecked() and len(gamuts) >= 2:
                self._write_two_slices(gamuts, out, controls=controls,
                                       offer=offer)
            else:
                write_slice_html(gamuts, out, float(self._slice_at.value()),
                                 self._scene_title(), mode=self._appearance,
                                 controls=controls, offer=offer)
            return True
        if self._side_by_side.isChecked() and len(gamuts) >= 2:
            self._write_two_rooms(gamuts, out, clouds, lost,
                                  controls=controls, offer=offer, glide=glide)
        else:
            write_html(gamuts, out, self._scene_title(),
                       # SPLIT WHETHER OR NOT IT IS FADED RIGHT NOW. The
                       # reader gets a slider for the agreement, and a trace
                       # that was never written into the page cannot be faded
                       # by anybody -- so the two halves travel whenever the
                       # control is being handed over, even at full strength
                       # where the picture is identical either way.
                       split=bool(controls and len(gamuts) > 1
                                  and (offer is None
                                       or offer.get("agree", True))),
                       spin=self._spin_options(glide),
                       # NO FLOATING STRIP IN THIS WINDOW. It has its own
                       # movement controls, and a second set over the picture
                       # is two controls for one thing that can disagree.
                       # The strip is for a page somebody was sent.
                       controls=controls, offer=offer,
                       carry_viewer=carry_viewer, notes=notes,
                       patches=clouds, styles=styles, lost=lost,
                       **self._render_options())
        return False

    def _write_two_slices(self, gamuts, out, controls: bool = False,
                          offer=None) -> None:
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
            cuts = slice_levels(gamuts[:2])
            if cuts is not None:
                cuts["title"] = ""
                cuts["at"] = min(
                    range(len(cuts["levels"])),
                    key=lambda i: abs(cuts["levels"][i] - lightness))
        extent = cuts["extent"] if cuts else slice_extent(gamuts, lightness)
        pages = [(name, build_slice_figure(
            [(name, g)], lightness, "", mode=self._appearance,
            extent=extent, legend=False, first=i, slidable=cuts is not None))
            for i, (name, g) in enumerate(gamuts[:2])]
        write_side_by_side_html(pages, out, mode=self._appearance,
                                linked=self._link_cameras.isChecked(),
                                spin={"cuts": cuts} if cuts else None,
                                controls=controls, offer=offer)

    def _write_two_rooms(self, gamuts, out, clouds, lost,
                         controls: bool = False, offer=None,
                         glide: bool = False) -> None:
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

        options = self._render_options()
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
                **options)))
        write_side_by_side_html(figures, out, mode=self._appearance,
                                linked=self._link_cameras.isChecked(),
                                spin=self._spin_options(glide),
                                controls=controls, offer=offer)

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
        """A line to compare the greys against means nothing without them.

        Greyed out rather than hidden, so it is clear the choice exists and
        what turns it on — and unticked when the greys go, so the picture
        always matches the boxes.
        """
        self._ideal_neutral.setEnabled(on)
        if on:
            self._make_room_to_see_inside()
        if not on and self._ideal_neutral.isChecked():
            self._ideal_neutral.blockSignals(True)
            self._ideal_neutral.setChecked(False)
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

    def _render_options(self) -> dict:
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
            mode=self._appearance,
            paint=self._shared["paint"],
            depth=self._shared["depth"],
            mesh_paint=self._shared["mesh_paint"],
            rings=self._shared["rings"],
            per_shape=self._per_shape_list(),
            neutrals=(self._neutral_list() if self._neutral.isChecked()
                      else None),
            ideal_neutrals=(self._neutral.isChecked()
                            and self._ideal_neutral.isChecked()),
            chart=self._chart_cloud(),
            chart_look=self._chart_look(),
            drift=self._drift_for_figure(),
            light=self._light_position(),
            grid=self._grid_on.isChecked(),
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
        gamuts = [(p.stem, g) for p, g, _m in self._slots]
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
            ab, _ = coverage(a, b)
            ba, _ = coverage(b, a)
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
            _overlap, _union, share = shared_volume(a, b)
            reach_a, reach_b = hue_reach(a), hue_reach(b)
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
            return
        self._drift_box.setVisible(True)
        (_pa, _ga, before), (_pb, _gb, after) = self._slots
        try:
            d = compare_measurements(before, after)
        except ValueError as exc:
            self._drift.setText(str(exc))
            self._drift_worst.setText("")
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
            f"Of those, {summary}. The ones that moved most:\n"
            + "\n".join(lines))

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
            return
        except Exception as exc:               # noqa: BLE001
            self._drift.setText(
                f"These two profiles could not be compared: {exc}")
            self._drift_worst.setText("")
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
            f"Of those, {summary}. The ones that moved most:\n"
            + "\n".join(lines) + note)

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
