"""The two pictures in the README that show the saved page and its dialog.

    python scripts/make_doc_shots.py

Both go stale the moment a control is added, and a README picture that no
longer matches the window is worse than none: somebody looks for a switch that
is not where the picture says it is. So they are made by a script rather than
by hand, and remaking them is one command.

  21  a saved page as its reader sees it -- the real page from docs/pages,
      opened in a real browser, with the "more…" panel open so every control
      the page carries is visible at once.
  22  the save dialog's list of switches, from the real dialog.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
_ARGS = list(sys.argv[1:])
sys.argv = ["make_doc_shots"]

OUT = HERE.parent / "docs" / "screenshots"
PAGE = HERE.parent / "docs" / "pages" / "11-everything-handed-over.html"


def save(image, name: str) -> None:
    """Write it as WebP, which is what the README uses throughout."""
    target = OUT / name
    ok = image.save(str(target), "WEBP", 88)
    print(f"  {'wrote' if ok else 'FAILED'}  {target.relative_to(HERE.parent)}"
          f"  {image.width()}x{image.height()}")


def the_page():
    """A saved page, open, with everything it offers on screen."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QUrl, QTimer, QEventLoop, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    app = QApplication.instance() or QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(1180, 940)
    view.show()

    def js(code, wait=0):
        box, loop = {}, QEventLoop()
        QTimer.singleShot(wait, lambda: view.page().runJavaScript(
            code, lambda r: (box.setdefault("r", r), loop.quit())))
        QTimer.singleShot(20000, loop.quit)
        loop.exec()
        return box.get("r")

    loop = QEventLoop()
    view.loadFinished.connect(lambda ok: QTimer.singleShot(6000, loop.quit))
    view.load(QUrl.fromLocalFile(str(PAGE)))
    QTimer.singleShot(45000, loop.quit)
    loop.exec()

    # OPEN "more…", so the picture shows every control rather than the four
    # that happen to be in the open. A reader deciding whether this feature is
    # worth anything is looking at exactly this.
    at = js("(function(){var e=document.querySelector('[data-cq=more]');"
            "if(!e)return null;var b=e.getBoundingClientRect();"
            "return JSON.stringify([b.x+b.width/2,b.y+b.height/2]);})()")
    if at:
        x, y = json.loads(at)
        point = QPointF(x, y)
        target = view.focusProxy() or view
        for kind in (QMouseEvent.Type.MouseButtonPress,
                     QMouseEvent.Type.MouseButtonRelease):
            app.sendEvent(target, QMouseEvent(
                kind, point, view.mapToGlobal(point.toPoint()).toPointF(),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier))
            app.processEvents()
        js("1", 1200)
    # And stop the movement, or the shape is caught mid-turn at an angle
    # nobody chose.
    js("if (window.cqSpin) window.cqSpin.set({on: false});", 400)
    js("1", 600)
    save(view.grab(), "21-a-saved-page-as-its-reader-sees-it.webp")


def the_dialog():
    """The save dialog, with the list of switches."""
    from PyQt6.QtCore import QSettings, QTimer, QEventLoop
    from PyQt6.QtWidgets import QApplication

    QSettings("MeasuredGamutViewer", "MeasuredGamutViewer").clear()
    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    window = gamut_app.GamutApp([])
    window.resize(1280, 860)
    window.show()
    end = time.time() + 1.5
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)

    dialog = gamut_app.WebPageDialog(window)
    dialog.show()
    dialog.adjustSize()
    end = time.time() + 1.5
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    save(dialog.grab(), "22-choosing-what-the-reader-can-change.webp")
    dialog.close()


#: ONE PICTURE PER RUN, in its own process. Both of these hold a browser
#: view, and building the second one in a process that already had one costs
#: the first its graphics context: every frame after that comes back empty and
#: the file written is a 2 kB blank. Two runs, one each, is the whole fix.
#:
#: The page also has to be grabbed on a real screen rather than offscreen --
#: a browser view drawn by the GPU has nothing for an offscreen platform to
#: copy out, and the result is the same blank.
def main() -> int:
    which = _ARGS[0] if _ARGS else ""
    if not PAGE.exists():
        raise SystemExit(f"{PAGE} is missing -- run make_sample_pages.py first")
    if which == "page":
        the_page()
    elif which == "dialog":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        the_dialog()
    else:
        import subprocess
        print("Remaking the two saved-page pictures in the README:")
        for part in ("page", "dialog"):
            got = subprocess.run([sys.executable, __file__, part],
                                 capture_output=True, text=True)
            for line in got.stdout.splitlines():
                if "wrote" in line or "FAILED" in line:
                    print(line)
            if got.returncode:
                print(f"  {part} failed:\n{got.stderr[-800:]}")
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
