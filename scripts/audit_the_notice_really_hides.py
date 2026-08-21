"""Is the did-not-arrive notice really off the screen when the viewer comes?

    ../gv-venv/bin/python scripts/audit_the_notice_really_hides.py

WHY THIS IS NOT A TEST. It renders the page in a real browser, and a
QWebEngineView built inside the pytest suite segfaults the whole run — exit
139, a thousand passing tests thrown away with it. Every other on-screen check
here is a script for the same reason.

WHY IT EXISTS. The notice was written `<div id="cq-noviewer" hidden
style="…display:flex;…">`, and `hidden` LOSES to an inline `display`: the
browser's rule is `[hidden] { display: none }` at ordinary specificity and an
inline style beats it. So the notice was on screen from the moment the parser
reached it, for ever, and `n.hidden = true` was a no-op. The picture was drawn
and intact BEHIND an opaque sheet — measured, the plot at 1,314 ms and the
notice covering it at 1,365 ms. Fifty-one milliseconds of picture.

Reported as "i see the shape a split second and then the message is back", and
as a retry button that does nothing — which it cannot, because the viewer is
already there.

EVERY STRING TEST STILL PASSED. The words in the HTML were all correct. Only
asking the browser what it COMPUTED could see it.

Exit code is 1 if the notice is on screen while the picture is drawn.
"""
import http.server
import pathlib
import re
import shutil
import socketserver
import sys
import threading

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))


def main() -> int:
    import ti3gamut
    from gamutview import build_gamut
    import plotly

    where = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent
    where = where / "_notice_check"
    where.mkdir(parents=True, exist_ok=True)
    library = (pathlib.Path(plotly.__file__).parent / "package_data"
               / "plotly.min.js")
    shutil.copy(library, where / "plotly.min.js")
    paper = ti3gamut.read_measurement(HERE.parent / "demo" / "Glossy-paper.ti3")
    shape = build_gamut(paper.lab, input_space="lab")
    page = where / "page.html"
    ti3gamut.write_html([("Glossy-paper", shape)], page, title="x",
                        mode="dark", carry_viewer=False)
    text = page.read_text(encoding="utf-8")
    # THE VIEWER MUST ACTUALLY ARRIVE, or this measures nothing: the whole
    # question is what the notice does when it DOES.
    text = re.sub(r'src="https://[^"]*plotly[^"]*"', 'src="plotly.min.js"', text)
    text = text.replace(' integrity="', ' data-was-integrity="')
    page.write_text(text, encoding="utf-8")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(where), **k)

        def log_message(self, *a):
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/page.html"

    from PyQt6.QtCore import QEventLoop, QTimer, QUrl
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.resize(900, 780)
    view.show()
    loop = QEventLoop()
    view.loadFinished.connect(lambda _ok: loop.quit())
    view.load(QUrl(url))
    QTimer.singleShot(40000, loop.quit)
    loop.exec()
    box, wait = {}, QEventLoop()
    QTimer.singleShot(4000, lambda: view.page().runJavaScript(
        "(function(){var n=document.getElementById('cq-noviewer');"
        "return {plotly: !!window.Plotly,"
        " notice: n ? getComputedStyle(n).display : '(no div)',"
        " canvases: document.querySelectorAll('canvas').length};})()",
        lambda r: (box.setdefault("r", r), wait.quit())))
    QTimer.singleShot(40000, wait.quit)
    wait.exec()
    got = box.get("r") or {}
    server.shutdown()
    print(f"  the viewer arrived: {got.get('plotly')}")
    print(f"  pictures drawn:     {got.get('canvases')}")
    print(f"  the notice computes to: display:{got.get('notice')}")
    bad = (not got.get("plotly") or not got.get("canvases")
           or got.get("notice") != "none")
    print("  Clean: the notice is off the screen when the picture is there."
          if not bad else
          "  BROKEN: the notice is covering a picture that is already drawn.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
