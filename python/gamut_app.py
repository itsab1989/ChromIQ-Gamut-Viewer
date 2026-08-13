"""Measured Gamut Viewer — a small desktop app, and a fitting study.

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

import sys
import tempfile
from pathlib import Path

# QtWebEngine must be imported before the QApplication exists.
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401  (import order)
from PyQt6.QtCore import QRect, Qt, QUrl
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
                             QFrame, QGroupBox, QHBoxLayout, QLabel,
                             QMainWindow, QMessageBox, QPushButton, QScrollArea, QSlider,
                             QSizePolicy, QVBoxLayout, QWidget)

from version import APP_NAME, __version__
from gamutview import build_gamut, coverage
from gamutview import xyz_to_lab
from references import REFERENCE_SPACES, icc_gamut, reference_gamut
from spectral import optimal_colour_solid
from ti3gamut import read_ti3, write_html

# Dark, close to ChromIQ's own, so the fit is judged on layout rather than on
# a colour scheme that would never ship.
_QSS = """
QWidget { background: #111318; color: #e8ecf2; font-size: 13px; }
QGroupBox { border: 1px solid #2a2f3a; border-radius: 6px; margin-top: 10px;
            padding: 10px 8px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px;
                   color: #9fb3c8; }
QPushButton { background: #e8175d; color: #fff; border: none; border-radius: 5px;
              padding: 7px 12px; font-weight: 600; min-height: 20px; }
QPushButton:hover { background: #ff2e73; }
QPushButton:disabled { background: #333842; color: #7b828e; }
QPushButton#secondary { background: #232833; color: #e8ecf2; font-weight: 500; }
QPushButton#secondary:hover { background: #2e3440; }
QComboBox { background: #1a1e26; border: 1px solid #2a2f3a; border-radius: 5px;
            padding: 5px 8px; }
QComboBox QAbstractItemView { background: #1a1e26; selection-background-color: #e8175d; }
QCheckBox::indicator { width: 15px; height: 15px; border-radius: 3px;
                       border: 1px solid #3a4150; background: #1a1e26; }
QCheckBox::indicator:checked { background: #e8175d; border-color: #e8175d; }
QSlider::groove:horizontal { height: 4px; background: #2a2f3a; border-radius: 2px; }
QSlider::handle:horizontal { width: 13px; margin: -5px 0; border-radius: 7px;
                             background: #e8175d; }
QLabel#hint { color: #7b828e; font-size: 11px; }
QLabel#volume { font-size: 21px; font-weight: 600; color: #e8ecf2; }
QLabel#slot { color: #9fb3c8; }
QScrollArea { border: none; background: #111318; }
QScrollBar:vertical { background: #111318; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #2a2f3a; border-radius: 5px;
                              min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3a4150; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


#: Inside width of the control column, in pixels: the column is 310 wide, a
#: group box eats ~24 of it and its layout another ~16. Labels are measured
#: against this, so their height is right the first time.
_TEXT_WIDTH = 262


def _wrapped(label: QLabel, width: int = _TEXT_WIDTH) -> QLabel:
    """Let a word-wrapped label claim the height its text really needs.

    A wrapping QLabel in a fixed-width column reports one line's height unless
    it is told otherwise, so whatever sits below it is drawn over the top and
    the last lines vanish. Asking the font metrics to lay the text out at the
    column's real width gives the exact height, however many lines that turns
    out to be -- which matters because these strings are meant to explain
    things properly rather than fit a guessed two lines, and because a
    translation is never the same length as the English.
    """
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Preferred,
                        QSizePolicy.Policy.MinimumExpanding)
    rect = label.fontMetrics().boundingRect(
        QRect(0, 0, width, 10_000),
        int(Qt.TextFlag.TextWordWrap), label.text())
    label.setMinimumHeight(rect.height() + 4)
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
        frame = QFrame(central)
        frame.setStyleSheet("border: 1px solid #2a2f3a; border-radius: 8px;")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.addWidget(self._view)
        row.addWidget(frame, 1)
        self.setCentralWidget(central)
        self.setAcceptDrops(True)      # drop a .ti3 anywhere on the window
        self._show_placeholder()

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

        title = QLabel("What your printer can print", col)
        f = QFont(); f.setPointSize(19); f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        v.addWidget(title)
        sub = QLabel(
            "Every colour your printer actually put on paper, worked out from "
            "the patches you measured. This is what the printer really did, on "
            "that paper, on that day — not what a profile predicts it can do.",
            col)
        sub.setObjectName("hint"); _wrapped(sub)
        v.addWidget(sub)

        # --- the measurements -------------------------------------------------
        g_files = QGroupBox("Your measured chart", col)
        fv = QVBoxLayout(g_files)
        self._open_btn = QPushButton("Open a measured chart…", g_files)
        self._open_btn.clicked.connect(self._on_open)
        fv.addWidget(self._open_btn)
        self._slot_labels = []
        for i in range(2):
            lab = QLabel("", g_files)
            lab.setObjectName("slot"); _wrapped(lab)
            fv.addWidget(lab)
            self._slot_labels.append(lab)
        self._clear_btn = QPushButton("Close these charts", g_files)
        self._clear_btn.setObjectName("secondary")
        self._clear_btn.clicked.connect(self._on_clear)
        self._clear_btn.setEnabled(False)
        fv.addWidget(self._clear_btn)
        hint = QLabel(
            "Open the .ti3 file ArgyllCMS saved when you measured a printed "
            "chart — or simply drag it onto this window. Open a second one and "
            "both are drawn together, so you can see which paper holds more "
            "colour and exactly where they differ.", g_files)
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
        mode_hint = QLabel(
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
        self._compare_note = QLabel("", g_cmp)
        self._compare_note.setObjectName("hint"); _wrapped(self._compare_note)
        cvv.addWidget(self._compare_note)
        cmp_hint = QLabel(
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
        rel_hint = QLabel(
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
        orow = QHBoxLayout()
        orow.addWidget(QLabel("See-through", g_look))
        self._opacity = QSlider(Qt.Orientation.Horizontal, g_look)
        self._opacity.setRange(15, 100); self._opacity.setValue(85)
        self._opacity.sliderReleased.connect(self._redraw)
        orow.addWidget(self._opacity, 1)
        self._opacity_lbl = QLabel("85%", g_look)
        self._opacity_lbl.setFixedWidth(38)
        self._opacity.valueChanged.connect(
            lambda x: self._opacity_lbl.setText(f"{x}%"))
        orow.addWidget(self._opacity_lbl)
        lv.addLayout(orow)
        self._aspect = QComboBox(g_look)
        self._aspect.addItem("True proportions", "data")
        self._aspect.addItem("Even up the box", "cube")
        self._aspect.currentIndexChanged.connect(self._redraw)
        lv.addWidget(self._aspect)
        aspect_hint = QLabel(
            "To scale, one step of colour difference is drawn the same length "
            "whichever direction it goes in, which is what makes the shape and "
            "the amount below honest. Printers have roughly twice as much "
            "range in colour as they do from black to white, so the true shape "
            "really is wide and flat — that is your printer, not a drawing "
            "error. Evening up the box is easier on the eye but no longer to "
            "scale.", g_look)
        aspect_hint.setObjectName("hint"); _wrapped(aspect_hint)
        lv.addWidget(aspect_hint)
        self._points = QCheckBox("Show every patch I measured", g_look)
        self._points.stateChanged.connect(self._redraw)
        lv.addWidget(self._points)
        v.addWidget(g_look)

        # --- the number -------------------------------------------------------
        g_vol = QGroupBox("How much colour it holds", col)
        vv = QVBoxLayout(g_vol)
        self._volume = QLabel("—", g_vol); self._volume.setObjectName("volume")
        vv.addWidget(self._volume)
        self._coverage = QLabel("", g_vol)
        self._coverage.setObjectName("hint"); _wrapped(self._coverage)
        vv.addWidget(self._coverage)
        self._volume_hint = QLabel(
            "Open a chart to see how much colour it holds.", g_vol)
        self._volume_hint.setObjectName("hint"); _wrapped(self._volume_hint)
        vv.addWidget(self._volume_hint)
        v.addWidget(g_vol)

        v.addStretch(1)
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
                    name, white_point=self._white.currentData()))
                self._compare_note.setText(REFERENCE_SPACES[name]["note"])
            elif choice[0] == "icc":
                path, _ = QFileDialog.getOpenFileName(
                    self, "Choose an ICC profile", "",
                    "ICC profiles (*.icc *.icm);;All files (*)")
                if not path:
                    self._compare.setCurrentIndex(0)
                    return
                self._reference = (Path(path).stem, icc_gamut(
                    path, white_point=self._white.currentData()))
                self._compare_note.setText(
                    "The gamut this profile describes, asked of the profile "
                    "itself.")
            elif choice[0] == "visible":
                v, _f = optimal_colour_solid(
                    "D50" if self._white.currentData() == "D50" else "D65", 48)
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

    def _on_open(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open a measurement", "",
            "Measured charts and profiles (*.ti3 *.icc *.icm);;"
            "Measured charts (*.ti3);;ICC profiles (*.icc *.icm);;"
            "All files (*)")
        for p in paths:
            self._load(Path(p))

    def _on_clear(self) -> None:
        self._slots.clear()
        self._refresh_slot_labels()
        self._show_placeholder()
        self._volume.setText("—")
        self._volume_hint.setText("cubic Lab units")
        self._clear_btn.setEnabled(False)
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
        target, _ = QFileDialog.getSaveFileName(
            self, "Save the gamut as a web page", str(default),
            "Web page (*.html)")
        if not target:
            return
        try:
            write_html([(p.stem, g) for p, g in self._slots], Path(target),
                       self._scene_title(),
                       opacity=self._opacity.value() / 100.0,
                       points=self._points.isChecked(), patches=clouds,
                   aspect=self._aspect.currentData())
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
        if path.suffix.lower() in (".icc", ".icm"):
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
        self._clear_btn.setEnabled(True)
        self._save.setEnabled(True)
        self._redraw()

    def _load_profile_as_comparison(self, path: Path) -> None:
        """Show an ICC profile as the thing to compare against."""
        try:
            g = icc_gamut(path, white_point=self._white.currentData())
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

    def _refresh_slot_labels(self) -> None:
        for i, lab in enumerate(self._slot_labels):
            if i < len(self._slots):
                path, _g, m = self._slots[i]
                patches = ("1 patch" if m.n_patches == 1
                           else f"{m.n_patches} patches")
                measured = (f", measured with your {m.instrument}"
                            if m.instrument else "")
                lab.setText(f"● {path.stem}\n   {patches}{measured}")
                lab.setVisible(True)
            else:
                # Nothing to say about a slot that holds nothing: an empty
                # placeholder under a real chart reads as if something failed.
                lab.setText("")
                lab.setVisible(False)

    # ------------------------------------------------------------------ drawing
    def _show_placeholder(self) -> None:
        self._view.setHtml(
            "<html><body style='background:#111318;color:#7b828e;"
            "font:14px -apple-system,Segoe UI,sans-serif;display:flex;"
            "align-items:center;justify-content:center;height:100%;margin:0'>"
            "<div style='text-align:center;max-width:32em'>"
            "<div style='font-size:44px'>◱</div>"
            "<p>Open a measured chart — a <b>.ti3</b> file — to see the gamut "
            "it encloses.</p></div></body></html>")

    def _redraw(self) -> None:
        if not self._slots:
            return
        gamuts = [(p.stem, g) for p, g, _m in self._slots]
        clouds = [m.lab for _p, _g, m in self._slots]
        if self._reference is not None:
            gamuts.append(self._reference)
            clouds.append(None)
        out = self._tmp / "scene.html"
        write_html(gamuts, out, self._scene_title(),
                   opacity=self._opacity.value() / 100.0,
                   points=self._points.isChecked(), patches=clouds,
                   aspect=self._aspect.currentData())
        self._view.setUrl(QUrl.fromLocalFile(str(out)))
        self._update_volume()
        self._update_coverage()

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
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(_QSS)
    files = [Path(a) for a in argv[1:] if not a.startswith("-")]
    win = GamutApp(files)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
