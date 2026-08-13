"""Measured Gamut Viewer — a small desktop app, and a fitting study.

    python gamut_app.py                 # then use "Open measurement…"
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
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
                             QFrame, QGroupBox, QHBoxLayout, QLabel,
                             QMainWindow, QMessageBox, QPushButton, QSlider,
                             QSizePolicy, QVBoxLayout, QWidget)

from version import APP_NAME, __version__
from gamutview import build_gamut
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
              padding: 7px 12px; font-weight: 600; }
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
"""


def _wrapped(label: QLabel) -> QLabel:
    """Let a word-wrapped label claim the height it actually needs.

    In a fixed-width column a wrapping QLabel reports a single line's height
    unless its vertical policy says otherwise, so whatever sits below it gets
    drawn over the top. Setting MinimumExpanding and seeding the minimum from
    heightForWidth fixes it for every label at once, rather than hard-coding
    heights that break in another language.
    """
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Preferred,
                        QSizePolicy.Policy.MinimumExpanding)
    label.setMinimumHeight(label.fontMetrics().height() * 2)
    return label


class GamutApp(QMainWindow):
    """One window: measurements on the left, the gamut on the right."""

    def __init__(self, initial: "list[Path] | None" = None) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1280, 840)
        self._slots: list[tuple[Path, object]] = []      # (path, Gamut)
        self._tmp = Path(tempfile.mkdtemp(prefix="gamutview-"))

        central = QWidget(self)
        row = QHBoxLayout(central)
        row.setContentsMargins(14, 14, 14, 14)
        row.setSpacing(14)
        row.addWidget(self._build_controls(), 0)

        self._view = QWebEngineView(central)
        self._view.setMinimumWidth(560)
        frame = QFrame(central)
        frame.setStyleSheet("border: 1px solid #2a2f3a; border-radius: 8px;")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.addWidget(self._view)
        row.addWidget(frame, 1)
        self.setCentralWidget(central)
        self._show_placeholder()

        for p in (initial or []):
            self._load(Path(p))

    # ---------------------------------------------------------------- controls
    def _build_controls(self) -> QWidget:
        col = QWidget(self)
        col.setFixedWidth(310)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        title = QLabel("Measured gamut", col)
        f = QFont(); f.setPointSize(19); f.setWeight(QFont.Weight.DemiBold)
        title.setFont(f)
        v.addWidget(title)
        sub = QLabel("The colours your printer actually put on paper — built "
                     "from the patches you measured, not from a profile.", col)
        sub.setObjectName("hint"); _wrapped(sub)
        v.addWidget(sub)

        # --- the measurements -------------------------------------------------
        g_files = QGroupBox("Measurements", col)
        fv = QVBoxLayout(g_files)
        self._open_btn = QPushButton("Open measurement…", g_files)
        self._open_btn.clicked.connect(self._on_open)
        fv.addWidget(self._open_btn)
        self._slot_labels = []
        for i in range(2):
            lab = QLabel("— empty —", g_files)
            lab.setObjectName("slot"); _wrapped(lab)
            fv.addWidget(lab)
            self._slot_labels.append(lab)
        self._clear_btn = QPushButton("Clear", g_files)
        self._clear_btn.setObjectName("secondary")
        self._clear_btn.clicked.connect(self._on_clear)
        self._clear_btn.setEnabled(False)
        fv.addWidget(self._clear_btn)
        hint = QLabel("Open a second one to compare two papers.", g_files)
        hint.setObjectName("hint"); _wrapped(hint)
        fv.addWidget(hint)
        v.addWidget(g_files)

        # --- how it is built --------------------------------------------------
        g_build = QGroupBox("How the shape is built", col)
        bv = QVBoxLayout(g_build)
        self._mode = QComboBox(g_build)
        self._mode.addItem("Follow the device boundary", "device")
        self._mode.addItem("Convex hull (over-states it)", "hull")
        self._mode.currentIndexChanged.connect(self._rebuild)
        bv.addWidget(self._mode)
        mode_hint = QLabel(
            "A printer's gamut is dented, especially in the deep blues. Using "
            "the device values you asked for keeps those dents; a convex hull "
            "bridges over them and claims more colour than you have.", g_build)
        mode_hint.setObjectName("hint"); _wrapped(mode_hint)
        bv.addWidget(mode_hint)
        v.addWidget(g_build)

        # --- colour science ---------------------------------------------------
        g_cs = QGroupBox("Reference", col)
        cv = QVBoxLayout(g_cs)
        self._white = QComboBox(g_cs)
        self._white.addItem("D50 — print measurement", "D50")
        self._white.addItem("D65 — display measurement", "D65")
        self._white.currentIndexChanged.connect(self._rebuild)
        cv.addWidget(self._white)
        self._relative = QCheckBox("Measure against the paper's own white", g_cs)
        self._relative.stateChanged.connect(self._rebuild)
        cv.addWidget(self._relative)
        rel_hint = QLabel(
            "On, two papers of different brightness can be compared fairly — "
            "this is what a relative-colorimetric profile does. Off, you see "
            "the absolute numbers the instrument reported.", g_cs)
        rel_hint.setObjectName("hint"); _wrapped(rel_hint)
        cv.addWidget(rel_hint)
        v.addWidget(g_cs)

        # --- appearance -------------------------------------------------------
        g_look = QGroupBox("Appearance", col)
        lv = QVBoxLayout(g_look)
        orow = QHBoxLayout()
        orow.addWidget(QLabel("Opacity", g_look))
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
        self._points = QCheckBox("Show the measured patches", g_look)
        self._points.stateChanged.connect(self._redraw)
        lv.addWidget(self._points)
        v.addWidget(g_look)

        # --- the number -------------------------------------------------------
        g_vol = QGroupBox("Gamut volume", col)
        vv = QVBoxLayout(g_vol)
        self._volume = QLabel("—", g_vol); self._volume.setObjectName("volume")
        vv.addWidget(self._volume)
        self._volume_hint = QLabel("cubic Lab units", g_vol)
        self._volume_hint.setObjectName("hint"); _wrapped(self._volume_hint)
        vv.addWidget(self._volume_hint)
        v.addWidget(g_vol)

        v.addStretch(1)
        self._save = QPushButton("Save as a web page…", col)
        self._save.setObjectName("secondary")
        self._save.clicked.connect(self._on_save)
        self._save.setEnabled(False)
        v.addWidget(self._save)
        return col

    # ------------------------------------------------------------------ actions
    def _on_open(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open a measurement", "",
            "Measured charts (*.ti3);;All files (*)")
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
                       points=self._points.isChecked(), patches=clouds)
        except OSError as exc:
            QMessageBox.warning(self, "That could not be saved", str(exc))
            return
        QMessageBox.information(
            self, "Saved",
            f"Written to\n{target}\n\nIt opens in any browser and needs no "
            "network — the viewer travels inside the page.")

    def _load(self, path: Path) -> None:
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
        self._refresh_slot_labels()
        self._clear_btn.setEnabled(True)
        self._save.setEnabled(True)
        self._redraw()

    def _build_one(self, path: Path):
        m = read_ti3(path, self._white.currentData(), self._relative.isChecked())
        drive = None if self._mode.currentData() == "hull" else m.device
        g = build_gamut(m.lab, drive, input_space="lab",
                        white_point=self._white.currentData())
        return g, m

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
                lab.setText(f"● {path.stem}\n   {m.n_patches} patches"
                            + (f", {m.instrument}" if m.instrument else ""))
            else:
                lab.setText("— empty —")

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
        out = self._tmp / "scene.html"
        write_html(gamuts, out, self._scene_title(),
                   opacity=self._opacity.value() / 100.0,
                   points=self._points.isChecked(), patches=clouds)
        self._view.setUrl(QUrl.fromLocalFile(str(out)))
        self._update_volume()

    def _scene_title(self) -> str:
        ref = ("the paper's own white" if self._relative.isChecked()
               else f"{self._white.currentData()} absolute")
        return f"Measured gamut — against {ref}"

    def _update_volume(self) -> None:
        if len(self._slots) == 1:
            g = self._slots[0][1]
            self._volume.setText(f"{g.volume:,.0f}")
            self._volume_hint.setText(
                "cubic Lab units — the same measure ArgyllCMS reports. "
                "Comparable between charts measured the same way.")
        else:
            (_, a, _), (_, b, _) = self._slots
            self._volume.setText(f"{a.volume:,.0f}  ·  {b.volume:,.0f}")
            big, small = max(a.volume, b.volume), min(a.volume, b.volume)
            which = (self._slots[0][0].stem if a.volume > b.volume
                     else self._slots[1][0].stem)
            self._volume_hint.setText(
                f"{which} holds {100 * (big / small - 1):.1f}% more colour.")


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
