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

# QtWebEngine must be imported before the QApplication exists.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401  (import order)
from PyQt6.QtCore import (QRect, QSettings, QSize, QStandardPaths, Qt,
                          QUrl)
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QIcon, QPainter,
                         QPen, QPixmap)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
                             QFrame, QGroupBox, QHBoxLayout, QLabel,
                             QMainWindow, QMessageBox, QPushButton, QScrollArea, QSlider,
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
from ti3gamut import read_ti3, write_html, write_slice_html

# Dark, close to ChromIQ's own, so the fit is judged on layout rather than on
# a colour scheme that would never ship.
#: Every colour the window uses, once per appearance. Two palettes rather than
#: two stylesheets: the shapes are identical, only the paint differs, so a new
#: control cannot end up styled in one mode and forgotten in the other.
PALETTES = {
    "dark": dict(
        bg="#111318", panel="#1a1e26", line="#2a2f3a", line_soft="#3a4150",
        text="#e8ecf2", dim="#9fb3c8", faint="#7b828e",
        accent="#e8175d", accent_hot="#ff2e73", on_accent="#ffffff",
        second="#232833", second_hover="#2e3440",
        plot_bg="#15181e", grid="#262b34", arrow="#e0e0e0",
        kept="rgb(105,112,126)"),
    "light": dict(
        bg="#f7f7f5", panel="#ffffff", line="#d9d9d4", line_soft="#c4c4be",
        text="#1c1b18", dim="#4a4a44", faint="#6f6f68",
        accent="#e8175d", accent_hot="#c9134f", on_accent="#ffffff",
        second="#ececE7", second_hover="#e0e0da",
        plot_bg="#ffffff", grid="#e4e4de", arrow="#1c1b18",
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
)

#: How the shapes in the picture are coloured. Each answers a different
#: question, which is why this is a choice rather than a preference.
PAINTS = (
    ("true", "True colours"),
    ("solid", "One colour each"),
    ("lightness", "By lightness"),
    ("chroma", "By chroma"),
)

#: Accent colours to choose from. Only the accent changes: the greys, the
#: text and the backgrounds stay put, because they are what makes the window
#: readable and an accent is what makes it yours. Each is picked to hold up
#: against both the dark and the light background at the same weight.
SCHEMES = {
    "Magenta": dict(accent="#e8175d", dark_hot="#ff2e73", light_hot="#c9134f"),
    "Teal": dict(accent="#0f9b8e", dark_hot="#17b9aa", light_hot="#0c7d72"),
    "Amber": dict(accent="#d98324", dark_hot="#f09a3c", light_hot="#b56a17"),
    "Violet": dict(accent="#7d5ba6", dark_hot="#9670c4", light_hot="#66478a"),
    "Slate": dict(accent="#4a6b8a", dark_hot="#5f83a6", light_hot="#3a5670"),
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
QWidget {{ background: {c["bg"]}; color: {c["text"]}; font-size: 13px; }}
QGroupBox {{ border: 1px solid {c["line"]}; border-radius: 6px; margin-top: 10px;
            padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
                   color: {c["dim"]}; }}
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
QComboBox:hover {{ border-color: {c["line_soft"]}; }}
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
QSlider::handle:horizontal {{ width: 13px; margin: -5px 0; border-radius: 7px;
                             background: {c["accent"]}; }}
/* A radio has to be round, and in Qt that means the radius must be half of
   the WHOLE box -- content plus both borders. 14 + 1 + 1 = 16, so 8. Thicken
   the border to draw a ring and the box grows to 22 while the radius stays 8,
   which is how a circle turns into a rounded square. The checked state keeps
   the same 1px border and simply fills. */
QRadioButton {{ spacing: 7px; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px;
                          border: 1px solid {c["line_soft"]};
                          background: {c["panel"]}; }}
QRadioButton::indicator:checked {{ background: {c["accent"]};
                                  border: 1px solid {c["accent"]}; }}
QRadioButton::indicator:hover {{ border: 1px solid {c["accent"]}; }}
QLabel#hint {{ color: {c["faint"]}; font-size: 11px; }}
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

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.MinimumExpanding)
        self._refit()

    def _refit(self) -> None:
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
]


class GamutApp(QMainWindow):
    """One window: measurements on the left, the gamut on the right."""

    def __init__(self, initial: "list[Path] | None" = None) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        # NEVER OPEN BIGGER THAN THE SCREEN. A window that starts off the
        # bottom of a laptop display hides its own buttons and cannot always
        # be dragged back (Sebastian, 2026-08-14). Ask the screen how much
        # room there actually is -- availableGeometry already excludes the
        # menu bar and the dock -- and take the smaller of that and a
        # comfortable size, leaving a small margin so the frame is grabbable.
        screen = QApplication.primaryScreen()
        room = (screen.availableGeometry() if screen is not None
                else QRect(0, 0, 1280, 840))
        self.resize(min(1280, room.width() - 40), min(840, room.height() - 60))
        self.move(room.center().x() - self.width() // 2,
                  room.top() + max(0, (room.height() - self.height()) // 2))
        self._slots: list[tuple[Path, object]] = []      # (path, Gamut, Measurement)
        self._reference: tuple[str, object] | None = None   # (name, Gamut)
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
        row = QHBoxLayout(central)
        row.setContentsMargins(14, 14, 14, 14)
        row.setSpacing(14)
        # The column scrolls: its help text is as long as it needs to be, and
        # on a short screen that is taller than the window. Scrolling keeps
        # every control reachable instead of trimming the explanations.
        controls = QScrollArea(central)
        controls.setWidget(self._build_controls())
        controls.setWidgetResizable(True)
        controls.setFixedWidth(330)
        controls.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        row.addWidget(controls, 0)

        self._view = QWebEngineView(central)
        self._view.setMinimumWidth(560)
        # A web view paints white until a page has loaded, and again for an
        # instant on every reload, which reads as a bright frame round a dark
        # scene and as a flash when anything changes. Both the widget and the
        # page it shows are told to be the same dark as the rest of the window.
        self._view.setStyleSheet("background: #111318;")
        self._view.page().setBackgroundColor(QColor("#111318"))
        frame = self._frame = QFrame(central)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.addWidget(self._view)
        row.addWidget(frame, 1)
        self.setCentralWidget(central)
        self.setAcceptDrops(True)      # drop a .ti3 anywhere on the window
        self._restore_everything()
        self._apply_mode()
        self._show_placeholder()
        # Anything the user moves is written straight away, so a crash or a
        # force-quit cannot lose a setting they just chose.
        for _key, widget, kind, _default in self._persisted():
            signal = (widget.valueChanged if kind == "slider"
                      else widget.stateChanged if kind == "check"
                      else widget.currentIndexChanged)
            signal.connect(lambda *_a: self._remember_everything())

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
        col.setFixedWidth(310)
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
        fv.addWidget(self._clear_btn)
        hint = WrappedLabel(
            "Open the .ti3 file ArgyllCMS saved when you measured a printed "
            "chart — or simply drag it onto this window. Open a second one and "
            "both are drawn together, so you can see which paper holds more "
            "colour and exactly where they differ.\n\n"
            "You can open an ICC profile (.icc or .icm) the same way. A "
            "profile is not a measurement, so it goes into Compare with "
            "below rather than here — it is what your printer is described "
            "as being able to do, next to what it actually did.", g_files)
        hint.setObjectName("hint"); _wrapped(hint)
        fv.addWidget(hint)
        v.addWidget(g_files)

        # --- how it is built --------------------------------------------------
        g_build = QGroupBox("How the shape is worked out", col)
        bv = QVBoxLayout(g_build)
        self._mode = QComboBox(g_build)
        self._mode.addItem("Follow the real edge", "device")
        self._mode.addItem("Wrap it in a simple skin", "hull")
        self._mode.currentIndexChanged.connect(self._rebuild)
        bv.addWidget(self._mode)
        mode_hint = WrappedLabel(
            "Follow the real edge is the one to use. The edge of what a printer "
            "can print is not smooth — it has real "
            "dents in it, most noticeably in the deep blues. The recommended "
            "setting keeps those dents, because it also reads the colour "
            "values you asked the printer for, which every measured chart "
            "stores alongside the results. The simpler setting stretches a "
            "skin over the whole thing, which looks tidier but claims more "
            "colour than your printer really has. Switch between them to see "
            "the difference.", g_build)
        mode_hint.setObjectName("hint"); _wrapped(mode_hint)
        bv.addWidget(mode_hint)
        v.addWidget(g_build)

        # --- what to compare against -----------------------------------------
        g_cmp = QGroupBox("Compare with", col)
        cvv = QVBoxLayout(g_cmp)
        self._compare = QComboBox(g_cmp)
        self._compare.addItem("Nothing — my chart alone", None)
        for _name in REFERENCE_SPACES:
            self._compare.addItem(_name, ("space", _name))
        self._compare.addItem("An ICC profile on my computer…", ("icc", None))
        self._compare.addItem("Everything the eye can see", ("visible", None))
        self._compare.currentIndexChanged.connect(self._on_compare_changed)
        cvv.addWidget(self._compare)
        self._compare_note = WrappedLabel("", g_cmp)
        self._compare_note.setObjectName("hint"); _wrapped(self._compare_note)
        cvv.addWidget(self._compare_note)
        cmp_hint = WrappedLabel(
            "Comparing with a second measurement asks which of two papers can "
            "print more. Comparing with a standard space asks whether the "
            "images people send you will survive on this paper. Comparing with "
            "every visible colour asks how much of what your eyes can see this "
            "paper can hold at all. They are three different questions and the "
            "answers are not interchangeable.", g_cmp)
        cmp_hint.setObjectName("hint"); _wrapped(cmp_hint)
        cvv.addWidget(cmp_hint)
        v.addWidget(g_cmp)

        # --- colour science ---------------------------------------------------
        g_cs = QGroupBox("What the colours are measured against", col)
        cv = QVBoxLayout(g_cs)
        self._white = QComboBox(g_cs)
        self._white.addItem("Daylight D50 — for print", "D50")
        self._white.addItem("Daylight D65 — for screens", "D65")
        self._white.currentIndexChanged.connect(self._rebuild)
        cv.addWidget(self._white)
        self._relative = QCheckBox("Judge each paper against its own white", g_cs)
        self._relative.stateChanged.connect(self._rebuild)
        cv.addWidget(self._relative)
        rel_hint = WrappedLabel(
            "Papers are not equally bright — a warm rag paper starts off duller "
            "than a bright glossy one. Tick this and each paper is judged "
            "against its own white, so two papers can be compared fairly on "
            "shape rather than on brightness. This is what happens anyway when "
            "you print with a normal profile. Leave it unticked to see the raw "
            "numbers your instrument reported.", g_cs)
        rel_hint.setObjectName("hint"); _wrapped(rel_hint)
        cv.addWidget(rel_hint)
        v.addWidget(g_cs)

        # --- appearance -------------------------------------------------------
        g_look = QGroupBox("How it looks", col)
        lv = QVBoxLayout(g_look)
        self._target = QComboBox(g_look)
        self._target.addItem("Set this for: all shapes together", "all")
        self._target.addItem("Set this for: the first chart", 0)
        self._target.addItem("Set this for: the second chart", 1)
        self._target.addItem("Set this for: the comparison", 2)
        self._target.currentIndexChanged.connect(self._on_target_changed)
        lv.addWidget(self._target)
        target_hint = WrappedLabel(
            "Everything below applies to whatever is chosen here. Leave it on "
            "all shapes together and one change moves them all, which is what "
            "you want most of the time. Pick a single shape and only that one "
            "changes — so you can, for instance, have your own chart solid and "
            "fully opaque while the thing you are comparing against is a faint "
            "outline behind it. A shape you have set on its own keeps its own "
            "value and stops following the shared one.", g_look)
        target_hint.setObjectName("hint")
        lv.addWidget(target_hint)
        orow = QHBoxLayout()
        orow.addWidget(QLabel("See-through", g_look))
        self._opacity = QSlider(Qt.Orientation.Horizontal, g_look)
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
        self._aspect = QComboBox(g_look)
        self._aspect.addItem("True proportions", "data")
        self._aspect.addItem("Even up the box", "cube")
        self._aspect.currentIndexChanged.connect(self._redraw)
        lv.addWidget(self._aspect)
        aspect_hint = WrappedLabel(
            "To scale, one step of colour difference is drawn the same length "
            "whichever direction it goes in, which is what makes the shape and "
            "the amount below honest. Printers have roughly twice as much "
            "range in colour as they do from black to white, so the true shape "
            "really is wide and flat — that is your printer, not a drawing "
            "error. Evening up the box is easier on the eye but no longer to "
            "scale.", g_look)
        aspect_hint.setObjectName("hint"); _wrapped(aspect_hint)
        lv.addWidget(aspect_hint)
        self._style_mine = QComboBox(g_look)
        self._style_second = QComboBox(g_look)
        self._style_other = QComboBox(g_look)
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
            lv.addWidget(combo)
        # An outer shape starts as a cage so whatever is inside stays visible.
        self._style_second.setCurrentIndex(2)
        self._style_other.setCurrentIndex(2)
        style_hint = WrappedLabel(
            "Each shape on screen is drawn its own way. A solid shape hides "
            "whatever is inside it, so the outer one starts as an outline — "
            "which is the only way to look at your printer sitting inside "
            "sRGB, or inside everything the eye can see, and still see your "
            "printer. Swap them round when the other one is the shape you want "
            "to look into.", g_look)
        style_hint.setObjectName("hint")
        lv.addWidget(style_hint)
        self._slice_on = QCheckBox("Slice it at one lightness", g_look)
        self._slice_on.stateChanged.connect(self._redraw)
        lv.addWidget(self._slice_on)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Lightness", g_look))
        self._slice_at = QSlider(Qt.Orientation.Horizontal, g_look)
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
        slice_hint = WrappedLabel(
            "Cuts straight through every shape at the lightness you choose and "
            "draws the result flat, looking down. Two shapes in 3D hide each "
            "other and depth is hard to judge on a screen; two outlines side by "
            "side are simply readable — which one reaches further into the "
            "cyans at this lightness is a glance rather than a guess. Move the "
            "slider from dark to light to see how the shape changes.", g_look)
        slice_hint.setObjectName("hint")
        lv.addWidget(slice_hint)
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Depth", g_look))
        self._depth = QSlider(Qt.Orientation.Horizontal, g_look)
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
        depth_hint = WrappedLabel(
            "How much the surface is shaded. At nothing it is lit evenly and "
            "you see only its colours, which is the honest picture; turning it "
            "up trades some of that for shading, which is what makes a rounded "
            "thing look rounded and a dent look like a dent. It moves as you "
            "drag, so you can stop wherever the shape reads best to you.",
            g_look)
        depth_hint.setObjectName("hint")
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
            slider = QSlider(Qt.Orientation.Horizontal, row)
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
        light_hint = WrappedLabel(
            "These are the five numbers the 3D view actually takes. Ambient is "
            "light arriving from every direction, so more of it flattens the "
            "shape and shows its colours plainly. Diffuse is light the surface "
            "scatters, which is what makes a curve look curved. Specular is "
            "the shiny highlight and roughness decides how soft that highlight "
            "is. Fresnel adds a glow around the edges. Every one of them moves "
            "the picture as you drag.", g_look)
        light_hint.setObjectName("hint")
        light_hint.setVisible(False)
        lv.addWidget(light_hint)
        self._light_rows.append(light_hint)

        v_paint = QLabel("How the shapes are coloured", g_look)
        lv.addWidget(v_paint)
        self._paint_group = QButtonGroup(self)
        self._paint_radios = {}
        paint_grid = QGridLayout()
        paint_grid.setContentsMargins(0, 0, 0, 0)
        for i, (key, label) in enumerate(PAINTS):
            radio = QRadioButton(label, g_look)
            self._paint_group.addButton(radio)
            radio.toggled.connect(
                lambda on, which=key: self._set_paint(which) if on else None)
            self._paint_radios[key] = radio
            paint_grid.addWidget(radio, i // 2, i % 2)
        lv.addLayout(paint_grid)
        self._mesh_colour = QCheckBox("Colour the outlines too", g_look)
        self._mesh_colour.stateChanged.connect(
            lambda: self._after_shape_setting("mesh_paint"))
        lv.addWidget(self._mesh_colour)
        mesh_hint = WrappedLabel(
            "Outlines are drawn in one plain grey by default, which reads "
            "clearly on top of a solid shape without competing with the "
            "colours underneath. Tick this and they are painted the same way "
            "the solid shapes are, which is worth it when a shape is shown as "
            "an outline on its own.", g_look)
        mesh_hint.setObjectName("hint")
        lv.addWidget(mesh_hint)

        rrow = QHBoxLayout()
        self._rings_on = QCheckBox("Show rings inside", g_look)
        self._rings_on.stateChanged.connect(
            lambda: self._after_shape_setting("rings"))
        rrow.addWidget(self._rings_on)
        self._rings = QSlider(Qt.Orientation.Horizontal, g_look)
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
        rings_hint = WrappedLabel(
            "A cage shows only the outer surface, because that is what a "
            "gamut is — a solid with a boundary rather than something with "
            "structure inside. These rings are cross-sections stacked within "
            "it, which show how the shape narrows between black and white: "
            "that is what tells you whether your mid-tones or your highlights "
            "are the tight part.", g_look)
        rings_hint.setObjectName("hint")
        lv.addWidget(rings_hint)
        paint_hint = WrappedLabel(
            "True colours paints every point the colour it represents, which "
            "is the honest picture of one gamut. One colour each is easier "
            "when two shapes overlap — you can tell at a glance which is "
            "which. By lightness and by chroma throw away the hue on purpose, "
            "so the shape itself is what you see.", g_look)
        paint_hint.setObjectName("hint")
        lv.addWidget(paint_hint)
        detrow = QHBoxLayout()
        detrow.addWidget(QLabel("Detail", g_look))
        self._detail = QSlider(Qt.Orientation.Horizontal, g_look)
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
        detail_hint = WrappedLabel(
            "How finely the shape you compare against is built. Normal is "
            "accurate to within a twentieth of a percent and draws in about a "
            "second; fine is smoother to look at; rough is there for a slow "
            "computer. Your own measured chart is not affected — its detail "
            "comes from how many patches you measured.", g_look)
        detail_hint.setObjectName("hint")
        lv.addWidget(detail_hint)
        self._show_lost = QCheckBox("Show me what the comparison cannot print",
                                    g_look)
        self._show_lost.stateChanged.connect(self._redraw)
        lv.addWidget(self._show_lost)
        lost_hint = WrappedLabel(
            "Paints your chart by what the thing you are comparing against "
            "cannot reproduce: red where the colour is out of its reach, grey "
            "where it is fine. A percentage tells you how much you lose; this "
            "tells you which colours, so you can decide whether it matters for "
            "the pictures you actually print.", g_look)
        lost_hint.setObjectName("hint")
        lv.addWidget(lost_hint)
        self._points = QCheckBox("Show every patch I measured", g_look)
        self._points.stateChanged.connect(self._redraw)
        lv.addWidget(self._points)
        v.addWidget(g_look)

        # --- the number -------------------------------------------------------
        g_vol = QGroupBox("How much colour it holds", col)
        vv = QVBoxLayout(g_vol)
        self._volume = QLabel("—", g_vol); self._volume.setObjectName("volume")
        vv.addWidget(self._volume)
        self._coverage = WrappedLabel("", g_vol)
        self._coverage.setObjectName("hint"); _wrapped(self._coverage)
        vv.addWidget(self._coverage)
        self._volume_hint = WrappedLabel(
            "Open a chart to see how much colour it holds.", g_vol)
        self._volume_hint.setObjectName("hint"); _wrapped(self._volume_hint)
        vv.addWidget(self._volume_hint)
        v.addWidget(g_vol)

        v.addStretch(1)

        # Appearance and accent live at the FOOT of the column. Between the
        # heading and the sentence that explains it, they separated a title
        # from its own description and left the heading looking orphaned --
        # and they are preferences about the window, not about the subject.
        g_prefs = QGroupBox("This window", col)
        pv = QVBoxLayout(g_prefs)
        # The label sits above its choices, the same shape as Accent and the
        # shape-colour set below it -- three groups laid out three different
        # ways is three things to parse instead of one.
        pv.addWidget(QLabel("Appearance", g_prefs))
        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
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
        pv.addWidget(QLabel("Accent", g_prefs))
        scheme_grid = QGridLayout()
        scheme_grid.setContentsMargins(0, 0, 0, 0)
        scheme_grid.setHorizontalSpacing(4)
        self._scheme_group = QButtonGroup(self)
        self._scheme_radios = {}
        for i, name in enumerate(SCHEMES):
            radio = QRadioButton(name, g_prefs)
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
        self._glossary_btn = QPushButton("What do these words mean?", col)
        self._glossary_btn.setObjectName("secondary")
        self._glossary_btn.clicked.connect(self._on_glossary)
        v.addWidget(self._glossary_btn)
        self._save = QPushButton("Save this view as a web page…", col)
        self._save.setObjectName("secondary")
        self._save.clicked.connect(self._on_save)
        self._save.setEnabled(False)
        v.addWidget(self._save)
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
            ("rings", self._rings, "slider", 6),
            ("aspect", self._aspect, "combo", "data"),
            ("white", self._white, "combo", "D50"),
            ("shape_mode", self._mode, "combo", "device"),
            ("style_first", self._style_mine, "combo", "solid"),
            ("style_second", self._style_second, "combo", "mesh"),
            ("style_other", self._style_other, "combo", "mesh"),
        ) + tuple(
            (f"light_{key}", self._light_sliders[key][0], "slider",
             int(round((start - lo) / (hi - lo) * 100)))
            for key, _label, lo, hi, start in LIGHT_CONTROLS)

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
        answer = QMessageBox.question(
            self, "Start again with the standard settings?",
            "Every setting in this window goes back to how it started: the "
            "appearance, the accent colour, how the shapes are drawn and "
            "coloured, the lighting, and everything else. Any shape you set "
            "on its own goes back to following the shared settings.\n\n"
            "The charts you have open stay open, and no file of yours is "
            "touched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
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
        colour = PALETTES[self._appearance]["bg"]
        self._view.setStyleSheet(f"background: {colour};")
        page = self._view.page()
        if page is not None:
            page.setBackgroundColor(QColor(colour))
        self._frame.setStyleSheet(
            f"border: 1px solid {PALETTES[self._appearance]['line']};"
            f"border-radius: 8px; background: {colour};")
        if not self._slots:
            self._show_placeholder()

    def _on_glossary(self) -> None:
        """Explain every word this window uses, in plain language.

        Shown on demand rather than crammed into the controls, so the panel
        stays readable while nobody is ever stuck on a word they did not
        choose to learn.
        """
        body = "".join(
            f"<p><b>{term}</b><br>{text}</p>" for term, text in GLOSSARY)
        box = QMessageBox(self)
        box.setWindowTitle("What do these words mean?")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText("<div style='max-width:34em'>" + body + "</div>")
        box.exec()

    def _on_compare_changed(self) -> None:
        """Build whatever the user chose to compare against, and say what it is.

        Every branch either produces a gamut or explains in plain words why it
        could not, and puts the combo box back to "Nothing" so the screen never
        claims a comparison that is not there.
        """
        choice = self._compare.currentData()
        self._reference = None
        self._compare_note.setText("")
        try:
            if choice is None:
                pass
            elif choice[0] == "space":
                name = choice[1]
                self._reference = (name, reference_gamut(
                    name, white_point=self._white.currentData(),
                    steps=self._detail.value()))
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
                self._reference = (Path(path).stem, icc_gamut(
                    path, white_point=self._white.currentData()))
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
                                               white_point=self._white.currentData()))
                self._compare_note.setText(
                    "Every colour a printed surface could possibly show under "
                    "this light. No printer comes close, and that is normal.")
        except Exception as exc:      # noqa: BLE001 — always explain, never crash
            QMessageBox.warning(
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
            "Charts, profiles and gamut files "
            "(*.ti3 *.icc *.icm *.gam);;"
            "Measured charts (*.ti3);;ICC profiles (*.icc *.icm);;"
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
        self._volume_hint.setText("cubic Lab units")
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
            QMessageBox.warning(self, "That could not be saved", str(exc))
            return
        QMessageBox.information(
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
            QMessageBox.warning(
                self, "This file could not be used",
                f"{path.name}\n\n{exc}\n\nA measured chart is a .ti3 file — the "
                "one ArgyllCMS writes after you read a printed chart. A .ti1 or "
                ".ti2 is the chart before it was measured and has no colours in "
                "it yet.")
            return
        self._slots.append((path, g, m))
        self._warn_if_too_few_patches(path, m)
        self._refresh_slot_labels()
        self._save.setEnabled(True)
        self._redraw()

    def _load_profile_as_comparison(self, path: Path) -> None:
        """Show an ICC profile as the thing to compare against."""
        try:
            reader = (gam_gamut if path.suffix.lower() == ".gam"
                      else icc_gamut)
            g = reader(path, white_point=self._white.currentData())
        except Exception as exc:      # noqa: BLE001 — always explain
            QMessageBox.warning(
                self, "This profile could not be used",
                f"{path.name}\n\n{exc}")
            return
        self._reference = (path.stem, g)
        self._compare.blockSignals(True)
        self._compare.setCurrentIndex(
            self._compare.findData(("icc", None)))
        self._compare.blockSignals(False)
        self._compare_note.setText(
            f"Comparing against {path.stem} — the colours this profile says "
            "are available.")
        self._redraw()

    def _build_one(self, path: Path):
        m = read_ti3(path, self._white.currentData(), self._relative.isChecked())
        drive = None if self._mode.currentData() == "hull" else m.device
        g = build_gamut(m.lab, drive, input_space="lab",
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
        QMessageBox.information(
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
                QMessageBox.warning(self, "That setting cannot be used here",
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

        The same trick the see-through slider uses: Plotly can restyle a scene
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
        """Change how see-through the shapes are, live, as the slider moves.

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

    def _redraw(self) -> None:
        if not self._slots:
            return
        # The comparison can change without any chart changing, so the style
        # controls are refreshed here rather than only when charts are opened.
        self._refresh_style_controls()
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
            return
        write_html(gamuts, out, self._scene_title(),
                   patches=clouds, styles=styles, lost=lost,
                   **self._render_options())
        self._view.setUrl(QUrl.fromLocalFile(str(out)))
        self._update_volume()
        self._update_coverage()

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

    def _per_shape_list(self) -> list:
        """Per-shape overrides in the order the shapes are drawn."""
        out = [dict(self._per_shape[i]) for i in range(len(self._slots))]
        if self._reference is not None:
            out.append(dict(self._per_shape[2]))
        return out

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
        ref = ("the paper's own white" if self._relative.isChecked()
               else f"{self._white.currentData()} absolute")
        return f"Measured gamut — against {ref}"

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
            return
        (a_name, a), (b_name, b) = pair
        try:
            ab, _ = coverage(a.vertices, b.vertices)
            ba, _ = coverage(b.vertices, a.vertices)
        except Exception:      # noqa: BLE001 — a readout must never crash a view
            self._coverage.setText("")
            return
        self._coverage.setText(
            f"{100 * ab:.1f}% of what {a_name} can print also fits inside "
            f"{b_name}.\n"
            f"{100 * ba:.1f}% of {b_name} fits inside {a_name}.\n"
            "The two numbers differ because fitting inside is not the same "
            "question in both directions.")

    def _update_volume(self) -> None:
        if len(self._slots) == 1:
            g = self._slots[0][1]
            self._volume.setText(f"{g.volume:,.0f}")
            self._volume_hint.setText(
                "This is the same measure ArgyllCMS reports. It is useful for "
                "comparing two papers measured the same way — on its own the "
                "number does not mean much.")
        else:
            (_, a, _), (_, b, _) = self._slots
            self._volume.setText(f"{a.volume:,.0f}  ·  {b.volume:,.0f}")
            big, small = max(a.volume, b.volume), min(a.volume, b.volume)
            which = (self._slots[0][0].stem if a.volume > b.volume
                     else self._slots[1][0].stem)
            self._volume_hint.setText(
                f"{which} holds {100 * (big / small - 1):.1f}% more colour "
                "than the other one.")


def main(argv=None) -> int:
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
