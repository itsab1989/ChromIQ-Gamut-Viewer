"""The README pictures that go stale whenever a control is added.

    python scripts/make_doc_shots.py

A README picture that no longer matches the window is worse than none:
somebody looks for a switch that is not where the picture says it is, and
concludes the feature is missing. So these are made by a script rather than by
hand, and remaking them is one command.

  11  the controls column in the window, framed on "How it looks".
  21  a saved page as its reader sees it -- the real page from docs/pages,
      opened in a real browser, with the "more…" panel open so every control
      the page carries is visible at once.
  22  the save dialog's list of switches, from the real dialog.
  23  the five ways of colouring a saved page, side by side.

11 IS HERE BECAUSE IT HAD NO SCRIPT. It was remade by hand from a throwaway
file outside the repository, so remaking it depended on somebody remembering
that it existed and still having the file.

IT WAS NOT ACTUALLY STALE, and that is worth writing down because the first
version of this note said it was. The reasoning went: the picture was last
committed in bf4829e, the Outline colour row came later, so the picture must
be missing a row. It was wrong -- bf4829e is the commit that ADDED that row,
and the picture was remade in it. Regenerating produced a byte-identical
file, which is what gave the mistake away.

So the argument for keeping it here is the plain one rather than the dramatic
one: a picture kept up to date by remembering to is a picture that will
eventually be wrong, and this one had nothing but memory behind it.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))

# THE SETTINGS GO SOMEWHERE THROWAWAY, and this must happen before the
# window is built. A driver that uses the real store both destroys what
# the person using this application has chosen and leaves its own last
# state behind as their new preference -- which is how "the walls behind
# the shape are missing" was reported as a bug in the viewer. See
# python/prefs.py.
import prefs  # noqa: E402

prefs.use_a_scratch_store()
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
    # SWITCHED ON FOR THE PICTURE, because a plain browser has it switched on.
    #
    # The page asks the browser whether full screen exists for an ordinary
    # element and builds that control only where it does -- which is right,
    # and which meant this README picture was taken in an embedded view where
    # it does NOT, and came out missing a row that every reader on Chrome,
    # Firefox or desktop Safari will see. A picture of the controls has to
    # show the controls people get.
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    view.settings().setAttribute(
        QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
    # TALL ENOUGH FOR THE WHOLE PANEL, and it has had to grow twice: the
    # picture takes 62% of whatever height this is, so every row added to the
    # panel needs about two and a half times its own height here. A README
    # picture that stops in the middle of the thing it illustrates is worse
    # than none, because a reader counts what is in it. If a group is missing
    # from the bottom of the grab, this number is why.
    view.resize(1180, 1040)
    # SHRUNK, NOT SQUEEZED. The window cannot be made taller than the screen
    # it is on, and the panel has outgrown that -- so the page is rendered at
    # three-quarter size instead. Every proportion is exactly what a reader
    # sees; there is simply more of it in the frame, and the grab is taken at
    # twice the pixel density so nothing is lost to the shrinking.
    view.setZoomFactor(0.7)
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
        # SCALED BY THE PAGE ZOOM. getBoundingClientRect answers in CSS
        # pixels and a synthetic mouse event is delivered in the widget's
        # own, which are the same thing only at 100%. At 70% the press
        # landed a third of the way up the page, the panel never opened, and
        # the picture came out showing a "more…" button as proof of it.
        zoom = view.zoomFactor()
        point = QPointF(x * zoom, y * zoom)
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


def the_controls():
    """The window's controls column, framed on "How it looks".

    This is the picture a reader checks a setting against, so it has to show
    the group whole -- heading down past the last row in it. The frame is
    chosen by scrolling to a NAMED WIDGET rather than to a pixel offset,
    because a pixel offset is wrong the moment a row is added above it, which
    is precisely the case this script exists for.
    """
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication, QScrollArea

    import gamut_app

    app = QApplication.instance() or QApplication(sys.argv)
    window = gamut_app.GamutApp([])
    window.resize(1500, 950)
    window.show()
    gamut_app.Notice.warn = staticmethod(lambda *a, **k: None)
    gamut_app.Notice.say = staticmethod(lambda *a, **k: None)

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(2.0)
    chart = HERE.parent / "demo" / "Glossy-paper.ti3"
    if not chart.exists():
        raise SystemExit(f"{chart} is missing")
    window._load(chart)
    pump(3.5)

    # THE LAST ROW OF THE GROUP HAS TO BE IN SHOT, and it is the newest one
    # that gets cut off. Scrolled to Outline colour with room underneath it.
    anchor = getattr(window, "_outline_paint", None)
    if anchor is None:
        raise SystemExit("the window has no _outline_paint — has the row "
                         "been renamed? This picture is framed on it.")
    for scroll in window.findChildren(QScrollArea):
        if scroll.isAncestorOf(anchor):
            scroll.ensureWidgetVisible(anchor, 0, 40)
            break
    pump(1.5)
    if not anchor.isVisible():
        raise SystemExit("Outline colour is not on screen in the grab")
    save(window.grab(), "11-controls.webp")


def the_page_colours():
    """The same saved page in each of its five colourings, side by side.

    A control that cycles through five things cannot be shown by a picture of
    the button. What a reader wants to know before ticking the switch is what
    the five look like, so this presses it four times and puts the results in
    one strip, each labelled with the name the button itself shows.

    THE NAMES COME FROM THE PAGE, not from a list here. If somebody adds a
    sixth colouring, this picture grows a sixth panel without anybody editing
    this file -- and if the cycle ever stops returning to where it started,
    that shows up here as a strip that does not close.
    """
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QUrl, QTimer, QEventLoop, QPointF, Qt
    from PyQt6.QtGui import (QMouseEvent, QPixmap, QPainter, QColor, QFont,
                             QPen)
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    app = QApplication.instance() or QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(560, 620)
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
    js("if (window.cqSpin) window.cqSpin.set({on: false});", 400)
    js("1", 800)

    # WHAT THE FILE SAYS IT OFFERS, read from the file rather than asked of
    # the script that is being checked. If the strip and the file disagree,
    # that is worth printing -- it means the button is not walking the list
    # the page was saved with.
    import re
    said = re.search(r'"schemes":\s*\[([^\]]*)\]', PAGE.read_text())
    order = ([w.strip().strip('"') for w in said.group(1).split(",")]
             if said else [])

    def click(what):
        at = js("(function(){var e=document.querySelector('[data-cq=%s]');"
                "if(!e)return null;var b=e.getBoundingClientRect();"
                "if(!b.width&&!b.height)return null;"   # in the page, not on it
                "return JSON.stringify([b.x+b.width/2,b.y+b.height/2]);})()"
                % what)
        if not at:
            return False
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
        js("1", 1400)
        return True

    def named():
        """What the button says it is showing, which is the page's own word."""
        got = js("(function(){var e=document.querySelector("
                 "'[data-cq=appearance]'); return e ? e.textContent.trim() "
                 ": null;})()")
        return got or "?"

    # PRESSED THROUGH THE PAGE, NOT THROUGH THE MOUSE, and the panel stays
    # shut. The colour button lives in "THE PAGE ITSELF", behind "more…" --
    # and with the panel open it sits at y=853 in a 620-pixel view, so a
    # synthetic press at its coordinates lands outside the window and this
    # script reported that the page has no colour button at all. Its handler
    # is an ordinary click listener, so asking the element to click itself
    # does the same thing and needs nothing to be on screen. It also keeps
    # the panel out of the picture, which is what this picture is of.
    def cycle():
        return js("""(function () {
          var b = document.querySelector('button[data-cq="appearance"]');
          if (!b) return false;
          b.click();
          return true;
        })();""") is True

    # WHERE THE PICTURE IS. The grab is the whole page -- picture, control
    # strip and the written-out figures underneath -- and what this picture
    # is about is the paper behind the shape, the walls, the grid and the
    # lettering. Shown whole, five times over, the figures dominate and the
    # thing being illustrated is a tenth of the frame. So each panel is cut
    # to the drawing itself, asked of the page rather than guessed.
    def _unused_picture_at():
        got = js("(function(){var e=document.querySelector('.js-plotly-plot');"
                 "if(!e)return null;var b=e.getBoundingClientRect();"
                 "return JSON.stringify([Math.round(b.x),Math.round(b.y),"
                 "Math.round(b.width),Math.round(b.height),"
                 "window.devicePixelRatio||1]);})()")
        return json.loads(got) if got else None

    # SETTLED BEFORE THE FIRST ONE, and settled the same way as the rest.
    # The first grab was taken straight after loading, while the figures
    # underneath had not yet been laid out -- so it came out taller than the
    # other four, and the strip was sized to it with half of it empty ground.
    js("1", 1800)

    shots = []
    seen = set()
    # ROUND THE CYCLE UNTIL IT REPEATS, rather than a fixed five times: the
    # number of colourings is the page's business, not this script's.
    for _ in range(12):
        name = named()
        if name in seen:
            break
        seen.add(name)
        # THE WHOLE PAGE, NOT ONLY THE PICTURE. Cut to the drawing alone this
        # picture could not show the fault it exists to illustrate: the
        # written-out figures underneath had their colours stated on the
        # element when the file was written, so they did NOT follow the
        # colouring -- a page saved dark and switched to "ink" for printing
        # kept a solid black rectangle across the bottom. Whoever looks at
        # this strip should be able to see that the figures follow too.
        whole = view.grab()
        # CUT TO WHAT THE PAGE SAYS IT IS. The grab is the whole widget, and
        # the page does not always fill it -- leaving half the strip as empty
        # ground under five panels. The page knows its own height; asking is
        # exact, and survives the window being any size at all.
        told = js("(function(){var b=document.body.getBoundingClientRect();"
                  "return JSON.stringify([Math.ceil(b.height),"
                  "window.devicePixelRatio||1]);})()")
        if told:
            from PyQt6.QtCore import QRect
            high, ratio = json.loads(told)
            deep = min(whole.height(), max(1, int(high * ratio)))
            whole = whole.copy(QRect(0, 0, whole.width(), deep))
        shots.append((name, whole))
        if not cycle():
            break
        js("1", 1500)
    if len(shots) < 2:
        raise SystemExit(
            "the page offers no colour button — remake the pages with "
            "scripts/make_sample_pages.py, which ticks it on page 11")
    if order and len(shots) != len(order):
        print(f"  NOTE: the page lists {len(order)} colourings "
              f"({', '.join(order)}) and the button cycled through "
              f"{len(shots)} — the strip shows what pressing it actually did")

    # SIZED FROM THE PANELS THERE ARE, not from the first one. The first grab
    # is taken before the figures underneath have been laid out, so the
    # picture still has the height they will take -- and a canvas cut to that
    # left a third of the strip as empty ground under the other four.
    pad, label = 10, 30
    widest = max(s.width() for _n, s in shots)
    tallest = max(s.height() for _n, s in shots)
    wide = widest * len(shots) + pad * (len(shots) + 1)
    tall = tallest + label + pad * 2
    strip = QPixmap(wide, tall)
    # A NEUTRAL GROUND, so that "none" -- which has no background of its own
    # -- is seen against something rather than against whatever this happens
    # to leave in memory.
    strip.fill(QColor("#8a8a8a"))
    paint = QPainter(strip)
    font = QFont()
    font.setPointSize(13)
    font.setBold(True)
    paint.setFont(font)
    for n, (name, shot) in enumerate(shots):
        x = pad + n * (widest + pad)
        paint.drawPixmap(x, pad + label, shot)
        paint.setPen(QPen(QColor("#ffffff")))
        paint.drawText(x, pad + label - 9, name)
    paint.end()
    # AND TRIMMED TO WHAT IS ON IT. The five grabs do not all come back the
    # same height -- the page reports its own height differently depending on
    # how far it has settled -- so the canvas is cut to the tallest and the
    # rest was empty ground. Rather than chase which grab is the odd one,
    # the finished strip is cut back to its last row that is not simply the
    # ground colour, which is right whatever the cause.
    image = strip.toImage()
    ground = QColor("#8a8a8a").rgb()
    bottom = image.height() - 1
    while bottom > 0:
        row = bottom
        if any(image.pixel(x, row) != ground
               for x in range(0, image.width(), 7)):
            break
        bottom -= 1
    if bottom < image.height() - 1:
        from PyQt6.QtCore import QRect
        strip = strip.copy(QRect(0, 0, strip.width(),
                                 min(strip.height(), bottom + pad + 1)))
    save(strip, "23-five-ways-of-colouring-a-page.webp")
    print(f"  the button cycled through: {', '.join(n for n, _ in shots)}")


def the_dialog():
    """The save dialog, with the list of switches."""
    from PyQt6.QtCore import QSettings, QTimer, QEventLoop
    from PyQt6.QtWidgets import QApplication

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
    # THE CAP COMES OFF FOR THE PICTURE, and only for the picture. The list of
    # switches is in a scroll area so the dialog fits a short screen; a
    # photograph of a scrollbar tells a reader nothing about what is in the
    # list, which is the entire reason this picture is in the README. Lifted,
    # the grab shows what somebody on a big screen actually sees.
    from PyQt6.QtWidgets import QScrollArea
    area = dialog.findChild(QScrollArea)
    if area is not None:
        area.setMaximumHeight(16777215)
    dialog.show()
    dialog.adjustSize()
    end = time.time() + 1.5
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    # ASKED AGAIN ONCE THE LAYOUT HAS SETTLED. Before the dialog is shown the
    # inner widget's size hint is a guess made without a width to wrap to, and
    # it came out one row short every time -- so the last switch in the list
    # was cut off in a picture whose whole job is to show the list.
    if area is not None:
        area.setMinimumHeight(area.widget().sizeHint().height() + 4)
        dialog.adjustSize()
        end = time.time() + 1.0
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
    elif which == "colours":
        the_page_colours()
    elif which == "controls":
        the_controls()
    elif which == "dialog":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        the_dialog()
    else:
        import subprocess
        print("Remaking the README pictures that go stale:")
        for part in ("controls", "page", "colours", "dialog"):
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
