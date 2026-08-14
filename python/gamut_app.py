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

import csv
import json
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

import tempfile
from pathlib import Path
from pathlib import Path as pathlib_Path

import numpy as np

# QtWebEngine must be imported before the QApplication exists.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401  (import order)
from PyQt6.QtCore import (QEvent, QRect, QSettings, QSize, QStandardPaths, Qt,
                          QTimer, QUrl, pyqtSignal)
from PyQt6.QtGui import (QColor, QDesktopServices, QFont, QFontMetrics,
                         QIcon, QLinearGradient,
                         QPainter,
                         QPen, QPixmap)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
                             QFrame, QGroupBox, QHBoxLayout, QLabel,
                             QDialog, QMainWindow, QPushButton, QScrollArea, QSlider,
                             QDialogButtonBox, QListView, QSizeGrip,
                             QSizePolicy, QStyle,
                             QButtonGroup, QGridLayout, QRadioButton, QToolButton,
                             QVBoxLayout,
                             QWidget)

from version import APP_NAME, __version__
from gamutview import build_gamut, coverage, outside_of
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

SCHEMES = {
    "Magenta": dict(accent=SPEC_MAGENTA, dark_hot="#ff6b90", light_hot="#e02a58"),
    "Cyan": dict(accent=SPEC_CYAN, dark_hot="#5ad0e8", light_hot="#2597ad"),
    "Amber": dict(accent=SPEC_AMBER, dark_hot="#ffc75c", light_hot="#d8930f"),
    "Violet": dict(accent=SPEC_VIOLET, dark_hot="#b9a3ff", light_hot="#7e5fe0"),
    "Green": dict(accent=SPEC_GREEN, dark_hot="#7ce3bb", light_hot="#33b184"),
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
QPushButton#secondary {{ background: {c["second"]}; color: {c["text"]};
                        font-weight: 500; }}
QPushButton#secondary:hover {{ background: {c["second_hover"]}; }}
QPushButton#closer {{ background: transparent; color: {c["faint"]};
                     border: none; border-radius: 11px; padding: 0;
                     font-size: 17px; font-weight: 500; min-height: 0; }}
QPushButton#closer:hover {{ background: {c["second_hover"]};
                           color: {c["text"]}; }}
QComboBox {{ background: {c["panel"]}; border: 1px solid {c["line"]};
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
QComboBox QAbstractItemView {{ background: {c["panel"]};
                              selection-background-color: {c["accent"]}; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 3px;
                       border: 1px solid {c["line_soft"]};
                       background: {c["panel"]}; }}
QCheckBox::indicator:checked {{ background: {c["accent"]};
                               border-color: {c["accent"]}; }}
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
   drew one pixel into each other. Reserving 20px gives the row more than the
   widget needs, so the grid can never squeeze two rows into touching. */
QRadioButton {{ spacing: 7px; min-height: 20px; }}
QCheckBox {{ spacing: 8px; min-height: 20px; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px;
                          border: 1px solid {c["line_soft"]};
                          background: {c["panel"]}; }}
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


def _sidebar_urls(*extra) -> list:
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
                 hide_when_empty: bool = False) -> None:
        super().__init__(text, parent)
        self._hide_when_empty = hide_when_empty
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.MinimumExpanding)
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
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(0)

        head = QLabel(title, card)
        head.setObjectName("noticeTitle")
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
        # A width chosen before the text is laid out, not after. A dialog that
        # sizes itself to its longest sentence gives a different shape for
        # every message; a fixed measure keeps them all recognisably the same
        # window and keeps the lines short enough to read comfortably.
        self.setFixedWidth(470)
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
    kind = "gamut file" if path.suffix.lower() == ".gam" else "profile"
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
        self._tmp = Path(tempfile.mkdtemp(prefix="gamutview-"))
        #: Where the last file came from, so the next dialog opens there.
        self._last_folder = ""
        #: Renders so far, so each one gets a URL the view has not seen.
        self._render_count = 0
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
        controls.setWidget(self._build_controls())
        controls.setWidgetResizable(True)
        # 330 fitted before each control gained an 18px icon and 6px of spacing
        # beside it; several combo labels were clipped at the old width.
        controls.setFixedWidth(366)
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
                ("hint_cmp_hint", self._compare),
                ("hint_style_hint", self._style_combos[-1][0]),
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
        self._restore_everything()
        self._apply_space_availability()
        for icon in self.findChildren(Hint):
            icon.set_colour(SCHEMES.get(self._scheme, SCHEMES['Magenta'])['accent'])
        self._apply_mode()
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
        g_files = QGroupBox("Your measured chart", col)
        fv = QVBoxLayout(g_files)
        self._open_btn = QPushButton("Open a measured chart…", g_files)
        self._open_btn.clicked.connect(self._on_open)
        fv.addWidget(self._open_btn)
        # One row per open chart, each with its own way out. A single "close
        # everything" button meant a second chart could not be put back without
        # reopening the first, which is the wrong shape for comparing things.
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
            # competes with "Open a measured chart" for attention.
            shut = QPushButton("×", row)
            shut.setObjectName("closer")
            shut.setFixedSize(22, 22)
            shut.setToolTip("Close this chart")
            shut.setCursor(Qt.CursorShape.PointingHandCursor)
            shut.clicked.connect(lambda _checked=False, which=i:
                                 self._close_one(which))
            rl.addWidget(shut, 0)
            row.setVisible(False)
            fv.addWidget(row)
            self._slot_labels.append(lab)
            self._slot_rows.append(row)
        self._clear_btn = QPushButton("Close both charts", g_files)
        self._clear_btn.setObjectName("secondary")
        self._clear_btn.clicked.connect(self._on_clear)
        self._clear_btn.setVisible(False)
        hint = Hint(
            "Open the .ti3 file ArgyllCMS saved when you measured a printed "
            "chart — or simply drag it onto this window. Open a second one and "
            "both are drawn together, so you can see which paper holds more "
            "colour and exactly where they differ.\n\n"
            "You can open an ICC profile (.icc or .icm) the same way. A "
            "profile is not a measurement, so it goes into Compare with "
            "below rather than here — it is what your printer is described "
            "as being able to do, next to what it actually did.", g_files)
        hint.setObjectName("hint_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._clear_btn, 1)
        _r.addWidget(hint, 0, Qt.AlignmentFlag.AlignVCenter)
        fv.addLayout(_r)
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
            "the difference.", g_build)
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
        self._compare.addItem("Nothing — my chart alone", None)
        for _name in REFERENCE_SPACES:
            self._compare.addItem(_name, ("space", _name))
        self._compare.addItem("An ICC profile on my computer…", ("icc", None))
        self._compare.addItem("Everything the eye can see", ("visible", None))
        self._compare.currentIndexChanged.connect(self._on_compare_changed)
        cvv.addWidget(self._compare)
        self._compare_note = WrappedLabel("", g_cmp, hide_when_empty=True)
        self._compare_note.setObjectName("hint"); _wrapped(self._compare_note)
        cmp_hint = Hint(
            "Comparing with a second measurement asks which of two papers can "
            "print more. Comparing with a standard space asks whether the "
            "images people send you will survive on this paper. Comparing with "
            "every visible colour asks how much of what your eyes can see this "
            "paper can hold at all. They are three different questions and the "
            "answers are not interchangeable.", g_cmp)
        cmp_hint.setObjectName("hint_cmp_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._compare_note, 1)
        _r.addWidget(cmp_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        cvv.addLayout(_r)
        v.addWidget(g_cmp)

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
        self._target = NoScrollComboBox(g_look)
        self._target.addItem("Set this for: all shapes together", "all")
        self._target.addItem("Set this for: the first chart", 0)
        self._target.addItem("Set this for: the second chart", 1)
        self._target.addItem("Set this for: the comparison", 2)
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
        self._aspect.addItem("True proportions", "data")
        self._aspect.addItem("Even up the box", "cube")
        self._aspect.currentIndexChanged.connect(self._redraw)
        aspect_hint = Hint(
            "To scale, one step of colour difference is drawn the same length "
            "whichever direction it goes in, which is what makes the shape and "
            "the amount below honest. Printers have roughly twice as much "
            "range in colour as they do from black to white, so the true shape "
            "really is wide and flat — that is your printer, not a drawing "
            "error. Evening up the box is easier on the eye but no longer to "
            "scale.", g_look)
        aspect_hint.setObjectName("hint_aspect_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._aspect, 1)
        _r.addWidget(aspect_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_r)
        self._style_mine = NoScrollComboBox(g_look)
        self._style_second = NoScrollComboBox(g_look)
        self._style_other = NoScrollComboBox(g_look)
        self._style_combos = (
            (self._style_mine, "First chart"),
            (self._style_second, "Second chart"),
            (self._style_other, "The comparison"),
        )
        for combo, label in self._style_combos:
            combo.addItem(f"{label}: solid", "solid")
            combo.addItem(f"{label}: solid with its mesh", "solid+mesh")
            combo.addItem(f"{label}: outline only", "mesh")
            combo.currentIndexChanged.connect(self._redraw)
            combo.setVisible(False)
            if combo is not self._style_combos[-1][0]:
                lv.addWidget(combo)      # the last one is added with its ⓘ
        # An outer shape starts as a cage so whatever is inside stays visible.
        self._style_second.setCurrentIndex(2)
        self._style_other.setCurrentIndex(2)
        style_hint = Hint(
            "Each shape on screen is drawn its own way. A solid shape hides "
            "whatever is inside it, so the outer one starts as an outline — "
            "which is the only way to look at your printer sitting inside "
            "sRGB, or inside everything the eye can see, and still see your "
            "printer. Swap them round when the other one is the shape you want "
            "to look into.", g_look)
        style_hint.setObjectName("hint_style_hint")
        # One explanation covers all three combos, so it goes beside the last
        # of them rather than on a row of its own underneath the group.
        _sr = QHBoxLayout(); _sr.setContentsMargins(0, 0, 0, 0); _sr.setSpacing(6)
        _sr.addWidget(self._style_combos[-1][0], 1)
        _sr.addWidget(style_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        lv.addLayout(_sr)
        self._slice_on = QCheckBox("Slice it at one lightness", g_look)
        self._slice_on.stateChanged.connect(self._redraw)
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
            "slider from dark to light to see how the shape changes.", g_look)
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
            radio.setMinimumHeight(20)
            self._paint_group.addButton(radio)
            radio.toggled.connect(
                lambda on, which=key: self._set_paint(which) if on else None)
            self._paint_radios[key] = radio
            paint_grid.addWidget(radio, i // 2, i % 2)
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
        self._mesh_colour = QCheckBox("Colour the outlines too", g_look)
        self._mesh_colour.stateChanged.connect(
            lambda: self._after_shape_setting("mesh_paint"))
        mesh_hint = Hint(
            "Outlines are drawn in one plain grey by default, which reads "
            "clearly on top of a solid shape without competing with the "
            "colours underneath. Tick this and they are painted the same way "
            "the solid shapes are, which is worth it when a shape is shown as "
            "an outline on its own.", g_look)
        mesh_hint.setObjectName("hint_mesh_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._mesh_colour, 1)
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
        self._neutral = QCheckBox("Show the greys", g_look)
        self._neutral.stateChanged.connect(self._redraw)
        neutral_hint = Hint(
            "Draws a line through the patches where you asked for an equal "
            "amount of every colour — the greys. What comes back is rarely "
            "neutral: paper is warm or cool, inks are never perfectly "
            "balanced, and the drift is usually worst in the shadows. The "
            "shape of a gamut cannot show this at all, and it is what people "
            "notice first in a black-and-white print.", g_look)
        neutral_hint.setObjectName("hint_neutral_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._neutral, 1)
        _r.addWidget(neutral_hint, 0, Qt.AlignmentFlag.AlignVCenter)
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
            "It needs two shapes to show — a second chart, or a chart and "
            "something to compare it with — so it does nothing until you have "
            "them.", g_look)
        side_hint.setObjectName("hint_side_hint")
        lv.addWidget(side_hint)

        self._link_cameras = QCheckBox("Keep both rooms pointing the same way",
                                       g_look)
        self._link_cameras.setChecked(True)
        self._link_cameras.stateChanged.connect(self._redraw)
        lv.addWidget(self._link_cameras)
        link_hint = Hint(
            "Turn one shape and the other turns with it, so you are always "
            "comparing the same face of both. This is what makes two rooms "
            "worth having: two shapes seen from two different angles cannot "
            "be compared at all.\n\n"
            "Untick it to move each one on its own — useful when you want to "
            "look into the shadows of one while keeping the other where it "
            "is.\n\n"
            "Either way, nothing about your measurements changes. This only "
            "moves the camera.", g_look)
        link_hint.setObjectName("hint_link_hint")
        lv.addWidget(link_hint)
        v.addWidget(g_look)

        # --- the number -------------------------------------------------------
        g_vol = QGroupBox("How much colour it holds", col)
        vv = QVBoxLayout(g_vol)
        self._volume = QLabel("—", g_vol); self._volume.setObjectName("volume")
        vv.addWidget(self._volume)
        self._coverage = WrappedLabel("", g_vol, hide_when_empty=True)
        self._coverage.setObjectName("hint"); _wrapped(self._coverage)
        vv.addWidget(self._coverage)
        self._range = WrappedLabel("", g_vol, hide_when_empty=True)
        self._range.setObjectName("hint")
        vv.addWidget(self._range)
        self._volume_hint = Hint(
            "Open a chart to see how much colour it holds.", g_vol)
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
            "When both charts are two readings of the SAME chart — the same "
            "paper measured on two days, or before and after a nozzle clean — "
            "this compares them patch by patch. The gamut above answers how "
            "much colour there is; this answers whether anything has moved, "
            "which a shape cannot show, because two gamuts can be the same "
            "size and hold different colours.\n\n"
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
        self._drift_box.setVisible(False)
        v.addWidget(self._drift_box)

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
        pv.addWidget(self._accent_label)
        accent_hint = Hint(
            "The colour this window uses for the things you can change: "
            "buttons, the ⓘ you are reading now, a control you are pointing "
            "at, and the bar under the title.\n\n"
            "It is yours to pick and it changes nothing else. The greys, the "
            "text and the backgrounds stay exactly where they are, because "
            "those are what make the window readable — an accent is what "
            "makes it yours.\n\n"
            "One place it does reach the picture: choosing **In the accent "
            "colours** under How the shapes are coloured tints the gamut into "
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
        self._glossary_btn = QPushButton("What do these words mean?", col)
        self._glossary_btn.setObjectName("secondary")
        self._glossary_btn.clicked.connect(self._on_glossary)
        v.addWidget(self._glossary_btn)
        self._update_btn = QPushButton("Check for a newer version…", col)
        self._update_btn.setObjectName("secondary")
        self._update_btn.clicked.connect(lambda: self._check_updates(asked=True))
        v.addWidget(self._update_btn)
        self._auto_update = QCheckBox("Look for a newer version when the app starts", col)
        # OFF by default, and it must stay that way. This app tells people
        # nothing leaves their machine; looking for updates without being
        # asked would quietly make that untrue. Pressing the button above is
        # itself the consent, the same way pressing Open consents to a file
        # being read -- so the button is always available and only the
        # unattended check has to be switched on deliberately.
        self._auto_update.setChecked(False)
        update_hint = Hint(
            "Looks at the project's releases page and tells you whether a "
            "newer version has been published. It never downloads or installs "
            "anything by itself — the most it does is show you the version "
            "number and offer the link.\n\n"
            "Nothing about you, your printer or your measurements is sent. "
            "The request carries no account and no identifier, and there is "
            "no record kept of it here.\n\n"
            "Everything else in this window works with no internet connection "
            "at all, which is why this starts switched off: the only time the "
            "app reaches the network is when you press the button, or after "
            "you tick this box.", col)
        update_hint.setObjectName("hint_update_hint")
        _r = QHBoxLayout(); _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(6)
        _r.addWidget(self._auto_update, 1)
        _r.addWidget(update_hint, 0, Qt.AlignmentFlag.AlignVCenter)
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
        return col

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
        """One layout, and every layout nested inside it."""
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
            ("relative", self._relative, "check", False),
            ("manual_light", self._manual_light, "check", False),
            ("mesh_colour", self._mesh_colour, "check", False),
            ("rings_on", self._rings_on, "check", False),
            ("neutral", self._neutral, "check", False),
            ("side_by_side", self._side_by_side, "check", False),
            ("link_cameras", self._link_cameras, "check", True),
            ("auto_update", self._auto_update, "check", False),
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
        self._sync_slider_labels()
        self._on_manual_light()

    def _sync_slider_labels(self) -> None:
        """Every label that mirrors a slider, told what its slider now says."""
        self._opacity_lbl.setText(f"{self._opacity.value()}%")
        self._depth_lbl.setText(f"{self._depth.value()}%")
        self._detail_lbl.setText(f"{self._detail.value()} steps")
        self._slice_lbl.setText(f"L* {self._slice_at.value()}")
        self._rings_lbl.setText(str(self._rings.value()))

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
        if not self._slots:
            return
        default = self._slots[0][0].with_name(
            self._slots[0][0].stem + "-gamut.csv")
        dlg = self._file_dialog("Save the numbers as a table",
                                QFileDialog.FileMode.AnyFile,
                                "Comma-separated values (*.csv)", str(default))
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
            rows.append((f"{path.stem}: patches", m.n_patches, m.instrument))
            rows.append((f"{path.stem}: colour held", self._fmt_volume(g.volume),
                         self._volume_units()))
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
                ab, ab_err = coverage(a.vertices, b.vertices)
                ba, ba_err = coverage(b.vertices, a.vertices)
                rows.append((f"{an} inside {bn}", f"{100 * ab:.1f}",
                             f"per cent, +/- {100 * ab_err:.1f}"))
                rows.append((f"{bn} inside {an}", f"{100 * ba:.1f}",
                             f"per cent, +/- {100 * ba_err:.1f}"))
            except Exception:      # noqa: BLE001 — a table must still be written
                pass
        if len(self._slots) == 2:
            try:
                d = compare_measurements(self._slots[0][2], self._slots[1][2])
                rows.append(("patches in both readings", d.matched, ""))
                rows.append(("biggest difference", f"{d.worst:.2f}", "dE2000"))
                rows.append(("average difference", f"{d.average:.2f}", "dE2000"))
                rows.append(("patches above 1", d.over_one, "dE2000"))
            except ValueError:
                pass               # not two readings of one chart; say nothing
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
                    space=self._space.currentData()))
                self._compare_note.setText(REFERENCE_SPACES[name]["note"])
            elif choice[0] == "icc":
                dlg = self._file_dialog(
                    "Choose an ICC profile to compare against",
                    QFileDialog.FileMode.ExistingFile,
                    "Profiles and gamut files (*.icc *.icm *.gam);;All files (*)")
                if not dlg.exec():
                    self._compare.setCurrentIndex(0)
                    return
                path = dlg.selectedFiles()[0]
                self._last_folder = str(Path(path).parent)
                self._reference_path = Path(path)
                self._reference = (_profile_label(Path(path)), icc_gamut(
                    path, white_point=self._white.currentData(),
                    space=self._space.currentData()))
                self._compare_note.setText(
                    "The gamut this profile describes, asked of the profile "
                    "itself.")
            elif choice[0] == "visible":
                v, _f = optimal_colour_solid(
                    "D50" if self._white.currentData() == "D50" else "D65",
                    max(24, self._detail.value() * 3))
                lab = xyz_to_lab(v, self._white.currentData())
                self._reference = ("Every visible colour",
                                   build_gamut(lab, input_space="lab",
                                               space=self._space.currentData(),
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
        self._redraw()

    def _file_dialog(self, title: str, mode, name_filter: str,
                     preselect: str = "") -> QFileDialog:
        """A file dialog with useful places already in its sidebar.

        Qt's own dialog rather than the operating system's, because only that
        one lets the shortcuts down the left be set — which is the difference
        between finding a chart in one click and hunting for it.
        """
        dlg = QFileDialog(self, title)
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog)
        dlg.setFileMode(mode)
        dlg.setNameFilter(name_filter)
        dlg.setSidebarUrls(_sidebar_urls(self._last_folder))
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
        dlg = self._file_dialog(
            "Open a measured chart or a profile",
            QFileDialog.FileMode.ExistingFiles,
            "Everything this can open "
            "(*.ti3 *.cxf *.mxf *.txt *.icc *.icm *.gam);;"
            "Measured charts (*.ti3 *.cxf *.mxf *.txt);;"
            "ICC profiles (*.icc *.icm);;"
            "ArgyllCMS gamut files (*.gam);;All files (*)")
        if dlg.exec():
            for chosen in dlg.selectedFiles():
                self._last_folder = str(Path(chosen).parent)
                self._load(Path(chosen))

    def _close_one(self, which: int) -> None:
        """Close just this chart and leave the other one where it is."""
        if 0 <= which < len(self._slots):
            del self._slots[which]
        self._refresh_slot_labels()
        if self._slots:
            self._redraw()
        else:
            self._on_clear()

    def _on_clear(self) -> None:
        self._slots.clear()
        self._refresh_slot_labels()
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
        if not self._slots:
            return
        default = self._slots[0][0].with_name(self._slots[0][0].stem + "-gamut.html")
        dlg = self._file_dialog("Save this view as a web page",
                                QFileDialog.FileMode.AnyFile,
                                "Web page (*.html)", str(default))
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dlg.setDefaultSuffix("html")
        if not dlg.exec():
            return
        target = dlg.selectedFiles()[0]
        try:
            gamuts, clouds, styles, lost = self._scene_contents()
            write_html(gamuts, Path(target), self._scene_title(),
                       patches=clouds, styles=styles, lost=lost,
                       **self._render_options())
        except OSError as exc:
            Notice.warn(self, "That could not be saved", str(exc))
            return
        Notice.say(
            self, "Saved",
            f"Written to\n{target}\n\nIt opens in any browser and needs no "
            "network — the viewer travels inside the page.")

    def _load(self, path: Path) -> None:
        # An ICC profile is not a measurement, so it goes to the comparison
        # slot rather than the chart slots -- but it arrives through the same
        # button and the same drag, because that is where someone with a file
        # in their hand will try to put it.
        if path.suffix.lower() in (".icc", ".icm", ".gam"):
            self._load_profile_as_comparison(path)
            return
        if len(self._slots) >= 2:
            self._slots.pop(0)                 # newest two win
        try:
            g, m = self._build_one(path)
        except Exception as exc:               # noqa: BLE001 — always explain
            _log().warning("could not use %s: %s", path.name, exc)
            Notice.warn(
                self, "This file could not be used",
                f"{path.name}\n\n{exc}\n\nA measured chart is a .ti3 file — the "
                "one ArgyllCMS writes after you read a printed chart. A .ti1 or "
                ".ti2 is the chart before it was measured and has no colours in "
                "it yet.")
            return
        self._slots.append((path, g, m))
        _log().info("opened %s: %d patches, %d vertices, volume %.0f",
                    path.name, m.n_patches, len(g.vertices), g.volume)
        self._warn_if_too_few_patches(path, m)
        self._refresh_slot_labels()
        self._save.setEnabled(True)
        self._export_btn.setEnabled(True)
        self._redraw()

    def _load_profile_as_comparison(self, path: Path) -> None:
        """Show an ICC profile as the thing to compare against."""
        try:
            reader = (gam_gamut if path.suffix.lower() == ".gam"
                      else icc_gamut)
            g = reader(path, white_point=self._white.currentData(),
                       space=self._space.currentData())
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
        m = read_measurement(path, self._white.currentData(),
                             self._relative.isChecked())
        drive = None if self._mode.currentData() == "hull" else m.device
        g = build_gamut(m.lab, drive, input_space="lab",
                        space=self._space.currentData(),
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
        if m.n_patches >= self.TOO_FEW_PATCHES:
            return
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

    def _apply_space_availability(self) -> None:
        """Turn off the tools that need a lightness axis when there is none.

        The slice, the rings and the grey axis are all defined against
        lightness and the neutral centre, which CIELAB and CIELUV both have
        and CIE XYZ does not. Rather than draw something meaningless in XYZ,
        the three controls are switched off and say why. They come back
        exactly as they were when an opponent space is chosen again.
        """
        from gamutview import AXES
        usable = AXES[self._space.currentData()]["cylindrical"]
        why = ("" if usable else
               "Not available in CIE XYZ — it has no lightness axis and no "
               "grey axis to measure from. Choose CIELAB or CIELUV under "
               "Draw it in to use this.")
        for widget in (self._slice_on, self._slice_at, self._rings_on,
                       self._rings, self._neutral):
            widget.setEnabled(usable)
            widget.setToolTip(why)
        if not usable:
            # Untick rather than leave them ticked-but-dead, so the picture
            # always matches the controls.
            for box in (self._slice_on, self._rings_on, self._neutral):
                box.blockSignals(True)
                box.setChecked(False)
                box.blockSignals(False)

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
                    space=self._space.currentData()))
            elif choice[0] == "icc" and self._reference_path is not None:
                path = self._reference_path
                reader = (gam_gamut if path.suffix.lower() == ".gam"
                          else icc_gamut)
                self._reference = (_profile_label(path), reader(
                    path, white_point=self._white.currentData(),
                    space=self._space.currentData()))
            elif choice[0] == "visible":
                v, _f = optimal_colour_solid(
                    "D50" if self._white.currentData() == "D50" else "D65",
                    max(24, self._detail.value() * 3))
                lab = xyz_to_lab(v, self._white.currentData())
                self._reference = ("Every visible colour", build_gamut(
                    lab, input_space="lab", space=self._space.currentData(),
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

    def _refresh_style_controls(self) -> None:
        """Show a style control only when the shape it governs is on screen.

        A control for something that does not exist is worse than no control:
        it invites a change that does nothing and leaves somebody wondering
        what they did wrong.
        """
        have = (len(self._slots) >= 1, len(self._slots) >= 2,
                self._reference is not None)
        for (combo, _label), show in zip(self._style_combos, have):
            combo.setVisible(show)

    def _refresh_slot_labels(self) -> None:
        # "both" only when there really are two; a button that says the wrong
        # number is a small lie that makes people distrust the rest.
        self._clear_btn.setVisible(len(self._slots) == 2)
        self._refresh_style_controls()
        for i, row in enumerate(self._slot_rows):
            row.setVisible(i < len(self._slots))
        for i, lab in enumerate(self._slot_labels):
            if i < len(self._slots):
                path, _g, m = self._slots[i]
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
            "<p style='margin:0'>Use <b>Open a measured chart</b> on the left, "
            "or drag the file onto this window.</p>"
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
        pieces = len(self._slots) + (1 if self._reference is not None else 0)
        can_split = pieces >= 2
        self._side_by_side.setEnabled(can_split)
        self._side_by_side.setToolTip(
            "" if can_split else
            "Open a second chart, or choose something under Compare with, and "
            "this can put the two side by side.")
        if not can_split and self._side_by_side.isChecked():
            self._side_by_side.blockSignals(True)
            self._side_by_side.setChecked(False)
            self._side_by_side.blockSignals(False)
        linked_useful = can_split and self._side_by_side.isChecked()
        self._link_cameras.setVisible(linked_useful)
        for icon in self.findChildren(Hint):
            if icon.objectName() == "hint_link_hint":
                icon.setVisible(linked_useful)

    def _redraw(self) -> None:
        if not self._slots:
            return
        # The comparison can change without any chart changing, so the style
        # controls are refreshed here rather than only when charts are opened.
        self._refresh_style_controls()
        self._apply_side_by_side_availability()
        gamuts, clouds, styles, lost = self._scene_contents()
        # A NEW FILE EVERY TIME. Writing to one name and loading the same URL
        # let the web view serve its cached copy, so switching to light left
        # the scene dark -- the page had been rewritten and never re-read.
        # Counting up sidesteps caching entirely, and the old ones go with the
        # temporary folder when the app closes.
        self._render_count += 1
        out = self._tmp / f"scene-{self._render_count}.html"
        if self._slice_on.isChecked():
            write_slice_html(gamuts, out, float(self._slice_at.value()),
                             self._scene_title(), mode=self._appearance)
            self._view.setUrl(QUrl.fromLocalFile(str(out)))
            self._update_volume()
            self._update_coverage()
            self._update_drift()
            return
        if self._side_by_side.isChecked() and len(gamuts) >= 2:
            self._write_two_rooms(gamuts, out, clouds, lost)
        else:
            write_html(gamuts, out, self._scene_title(),
                       patches=clouds, styles=styles, lost=lost,
                       **self._render_options())
        self._view.setUrl(QUrl.fromLocalFile(str(out)))
        self._update_volume()
        self._update_coverage()
        self._update_drift()

    def _write_two_rooms(self, gamuts, out, clouds, lost) -> None:
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
        figures = []
        for i, (name, gamut) in enumerate(gamuts[:2]):
            figures.append((name, build_figure(
                [(name, gamut)], "",
                patches=[clouds[i]] if clouds and i < len(clouds) else None,
                styles=["solid"],
                lost=[lost[i]] if lost and i < len(lost) else None,
                **options)))
        write_side_by_side_html(figures, out, mode=self._appearance,
                                linked=self._link_cameras.isChecked())

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
            "mesh_paint": (self._mesh_colour,
                           lambda w: "colour" if w.isChecked() else "plain"),
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
                widget.setChecked(own[key] == "colour")
            widget.blockSignals(False)
        self._sync_slider_labels()

    def _neutral_list(self) -> list:
        """The measurement behind each shape, or None for a reference.

        Only a measured chart has greys to draw: a standard colour space or a
        profile has a perfect neutral axis by construction, so drawing one
        would say nothing.
        """
        out = [m for _p, _g, m in self._slots]
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
            light=self._light_position(),
        )

    def _scene_contents(self):
        """What goes into the picture: the shapes, their patches, their styles.

        One place, used by both the live view and the saved page, so a saved
        page is exactly what was on screen. Keeping two copies of this is how
        the save route came to be broken while the view looked fine.
        """
        gamuts = [(p.stem, g) for p, g, _m in self._slots]
        clouds = [m.lab for _p, _g, m in self._slots]
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
            self._shared_lbl.setText("")
            self._reach.setText("")
            self._pair_box.setVisible(False)
            return
        (a_name, a), (b_name, b) = pair
        try:
            ab, _ = coverage(a.vertices, b.vertices)
            ba, _ = coverage(b.vertices, a.vertices)
        except Exception:      # noqa: BLE001 — a readout must never crash a view
            self._coverage.setText("")
            self._pair_box.setVisible(False)
            return
        self._coverage.setText(
            f"{100 * ab:.1f}% of what {a_name} can print also fits inside "
            f"{b_name}.\n"
            f"{100 * ba:.1f}% of {b_name} fits inside {a_name}.\n"
            "The two numbers differ because fitting inside is not the same "
            "question in both directions.")
        self._update_pair(a_name, a, b_name, b)

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
            _overlap, _union, share = shared_volume(a.vertices, b.vertices)
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

    def _update_drift(self) -> None:
        """Compare two readings of one chart, when that is what is open."""
        if len(self._slots) != 2:
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
        """
        from gamutview import AXES
        return AXES[self._space.currentData()]["units"]

    def _update_range(self) -> None:
        """How black the blacks go and how bright the paper is.

        After the volume, this is the pair of numbers a printer looks for: a
        paper that cannot go dark loses shadow detail whatever its gamut
        volume says. Needs a lightness axis, so it is left blank in CIE XYZ.
        """
        from gamutview import AXES, lightness_range
        if not self._slots or not AXES[self._space.currentData()]["cylindrical"]:
            self._range.setText("")
            return
        try:
            lines = []
            for path, g, _m in self._slots:
                dark, light = lightness_range(g)
                lines.append(f"{path.stem}: blacks reach L* {dark:.0f}, "
                             f"paper white L* {light:.0f}")
        except Exception:      # noqa: BLE001 — a readout must never crash a view
            self._range.setText("")
            return
        self._range.setText("\n".join(lines))

    def _update_volume(self) -> None:
        self._update_range()
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
