"""Tell somebody when a newer version exists — and nothing else.

WHY THIS IS OPT-IN
------------------
The release notes promise that nothing is uploaded anywhere and no network is
used. An update check is a network request, so switching one on by default
would quietly break a promise already made to everybody who downloaded 1.0.0.

So there are two ways to ask, and they are different in kind:

* **"Check for updates now"** is a button. Pressing it *is* the consent, the
  same way pressing Open is consent to read a file. Always available.
* **"Check when the app starts"** happens without anybody pressing anything,
  so it starts **off** and stays off until somebody turns it on.

WHAT IS SENT
------------
One ordinary HTTPS GET to the public GitHub releases API. No account, no
identifier, no measurement data, no file names, nothing about the machine
beyond what any HTTP request unavoidably carries. Nothing is ever downloaded
or installed automatically — the most this does is show a version number and
offer a link.
"""
from __future__ import annotations

import json
import re

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

#: The public releases endpoint. Chosen over scraping the HTML page because it
#: is a documented, stable API that returns the same answer to everybody.
RELEASES_API = ("https://api.github.com/repos/"
                "itsab1989/ChromIQ-Gamut-Viewer/releases/latest")
RELEASES_PAGE = "https://github.com/itsab1989/ChromIQ-Gamut-Viewer/releases"

#: Short on purpose. This runs at start-up when it is switched on, and a slow
#: or captive network must never hold the window up.
TIMEOUT_MS = 6000

_NUMBER = re.compile(r"\d+")


def parse_version(text: str) -> tuple[int, ...]:
    """A version string as comparable numbers. ``"v1.2.3"`` -> ``(1, 2, 3)``.

    Deliberately forgiving: a leading "v", extra labels and any separator are
    all accepted, because the answer comes from a tag somebody typed. Anything
    with no digits at all gives an empty tuple, which compares lower than every
    real version — so a tag nobody can parse is never announced as an update.
    """
    return tuple(int(n) for n in _NUMBER.findall(text or ""))


def is_newer(candidate: str, current: str) -> bool:
    """Is *candidate* a later version than *current*?

    Compared piece by piece as numbers, not as text — "1.10.0" is newer than
    "1.9.0", which a string comparison gets backwards. A shorter version is
    padded with zeros, so "1.1" and "1.1.0" are the same version rather than
    one being mysteriously newer than the other.
    """
    a, b = parse_version(candidate), parse_version(current)
    if not a:
        return False
    width = max(len(a), len(b))
    a = a + (0,) * (width - len(a))
    b = b + (0,) * (width - len(b))
    return a > b


class UpdateCheck(QObject):
    """One check, reported once through :attr:`finished`.

    ``finished(newer, version, url, problem)``:

    * ``newer``   True only when there is definitely a later version
    * ``version`` the version found, or "" when it could not be established
    * ``url``     where to get it
    * ``problem`` a plain-language reason when the check could not be made,
      empty when it succeeded. Never a raw error code: not being able to reach
      GitHub is a normal thing to happen, not a fault to alarm anybody about.
    """

    finished = pyqtSignal(bool, str, str, str)

    def __init__(self, current_version: str, parent: QObject | None = None):
        super().__init__(parent)
        self._current = current_version
        self._manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None

    def start(self) -> None:
        request = QNetworkRequest(QUrl(RELEASES_API))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setTransferTimeout(TIMEOUT_MS)
        self._reply = self._manager.get(request)
        # Held on self until it reports: a reply garbage-collected mid-flight
        # never delivers its signal, and the check silently never finishes.
        self._reply.finished.connect(self._on_reply)

    def _on_reply(self) -> None:
        reply, self._reply = self._reply, None
        if reply is None:
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.finished.emit(
                    False, "", RELEASES_PAGE,
                    "The update site could not be reached just now. That "
                    "usually means there is no internet connection at the "
                    "moment, and nothing is wrong with your copy.")
                return
            try:
                data = json.loads(bytes(reply.readAll().data()).decode("utf-8"))
                tag = str(data.get("tag_name") or "")
                url = str(data.get("html_url") or RELEASES_PAGE)
            except (ValueError, UnicodeDecodeError):
                self.finished.emit(
                    False, "", RELEASES_PAGE,
                    "The update site answered with something this version "
                    "could not read. Nothing is wrong with your copy.")
                return
            if not parse_version(tag):
                self.finished.emit(
                    False, "", RELEASES_PAGE,
                    "The update site did not name a version this time.")
                return
            self.finished.emit(is_newer(tag, self._current),
                               tag.lstrip("vV"), url, "")
        finally:
            reply.deleteLater()
