"""Finding ArgyllCMS, and saying plainly what it is needed for.

WHAT NEEDS IT AND WHAT DOES NOT
-------------------------------
Most of this application needs nothing installed at all:

* ``.ti3`` measurements are read here, directly.
* ``.gam`` surface files are read here, directly.
* ``.icc`` and ``.icm`` profiles are read here when they have to be -- version
  4 profiles have to be, because ArgyllCMS declines them.

Two things do need it:

* ``.cxf``, ``.mxf`` and ``.txt`` measurements, which are converted by
  ArgyllCMS's own ``cxf2ti3`` and ``txt2ti3``. These formats have corners --
  spectral tables, several colour specifications in one file, vendor
  extensions -- and ArgyllCMS already handles them correctly. Re-implementing
  that would be a worse answer, not a better one.
* ``.icc`` and ``.icm`` profiles get a better answer from it. ``iccgamut``
  walks the profile's real surface in full precision, where reading it here
  samples a grid; the two agree to well under a per cent, but the tool is the
  more exact of the two and stays the first choice.

So: a person with only ``.ti3`` files never needs ArgyllCMS, and a person
opening a ``.cxf`` does. That is worth saying somewhere they will see it,
rather than at the moment the file fails to open.

WHERE IT LOOKS
--------------
On the PATH first, then every usual place on each platform, including
version-numbered folders like ``Argyll_V3.5.0`` -- which is how the official
download unpacks, so it is the single most likely place to find it and was the
one not being looked in. ``CHROMIQ_ARGYLL_BIN`` overrides the lot for anybody
who keeps it somewhere of their own, and the window's "Find or get ArgyllCMS…"
button overrides it for everybody else, because nobody sets an environment
variable to open a file.

THE PATH IS NEARLY USELESS IN THE SHIPPED APPLICATION, which is why the list of
folders below carries the whole weight. Measured on macOS: ``launchctl getenv
PATH`` is unset, so an application started from Finder inherits launchd's
default of ``/usr/bin:/bin:/usr/sbin:/sbin`` -- not the shell's PATH. On a
machine with ArgyllCMS in ``/Applications/Argyll/bin`` AND on the login shell's
PATH, ``shutil.which("xicclu")`` still answers None inside the bundle. The same
goes for a Homebrew install: ``/opt/homebrew/bin`` is not on that PATH either.
So a folder missing from this list is a tool that cannot be found, however
carefully the user installed it.

The usual places, all of them checked rather than assumed:

* the official download, unpacked and left where it landed -- ``Downloads`` is
  the single most likely folder on any platform, and was not being looked in.
* Homebrew, which really does carry it: the ``argyll-cms`` formula installs
  ``prefix.install "bin"``, so the tools are symlinked into
  ``$(brew --prefix)/bin``. That is ``/opt/homebrew/bin`` on Apple silicon,
  ``/usr/local/bin`` on Intel, and ``/home/linuxbrew/.linuxbrew/bin`` on Linux
  -- the formula has arm64_linux and x86_64_linux bottles, so Linux Homebrew is
  a real installation and not a curiosity. ``HOMEBREW_PREFIX`` covers anyone
  who moved it.
* MacPorts in ``/opt/local/bin``, and a distribution package in ``/usr/bin``.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

#: Point this at a folder of Argyll binaries to override the search entirely.
ENV_OVERRIDE = "CHROMIQ_ARGYLL_BIN"

#: Where to get it. Free, and the same toolkit that measured the chart.
DOWNLOAD_URL = "https://www.argyllcms.com/"

#: A folder the user chose by hand, for the case where it is somewhere the
#: search does not know about. Set by the window from its saved settings; kept
#: here as a plain string so this module needs nothing from Qt.
EXTRA_FOLDER: "str | None" = None


def set_folder(folder: "str | None") -> None:
    """Use *folder* before looking anywhere else. Empty clears it."""
    global EXTRA_FOLDER
    EXTRA_FOLDER = folder or None
    forget()


#: The tools looked for when deciding whether a folder is an installation.
#: Any one of them is enough -- a folder holding `iccgamut` is ArgyllCMS.
MARKER_TOOLS = ("iccgamut", "xicclu", "cxf2ti3", "txt2ti3", "targen")


def _holds_tools(folder) -> bool:
    """Whether the programs themselves are directly inside *folder*."""
    folder = Path(folder)
    for name in MARKER_TOOLS:
        if (folder / name).is_file() or (folder / f"{name}.exe").is_file():
            return True
    return False


def tools_folder(chosen) -> "Path | None":
    """The folder to actually search, given whatever the user picked.

    PEOPLE PICK THE ARGYLL FOLDER, NOT ITS BIN FOLDER, and they are not wrong
    to: `/Applications/Argyll` is the thing with the name on it, while `bin` is
    an implementation detail they have no reason to care about. Turning that
    pick down -- which is what happened before -- teaches somebody that the
    button does not work, at the exact moment they are trying to help
    themselves. So both are accepted and the right one is worked out here.
    """
    chosen = Path(chosen)
    if _holds_tools(chosen):
        return chosen
    if _holds_tools(chosen / "bin"):
        return chosen / "bin"
    return None


def looks_like_argyll(folder) -> bool:
    """Whether *folder* is an installation, so a wrong pick can be turned down
    at the moment it is made rather than at the moment it fails."""
    return tools_folder(folder) is not None

#: What each file type needs, in the user's words rather than the tool's.
NEEDS_ARGYLL = {
    ".cxf": "cxf2ti3",
    ".mxf": "cxf2ti3",
    ".txt": "txt2ti3",
}

_cache: dict = {}


def _version_order(folder) -> list:
    """Sort key reading the version out of a folder name, as numbers.

    A PLAIN STRING SORT GETS THIS WRONG, and it is the ordinary case rather
    than an exotic one: sorted() puts `Argyll_V3.5.0` above `Argyll_V3.10.0`,
    because it compares "5" against "1" as text. Somebody with both installed
    would be given the older one. Reading the digits as numbers is what makes
    3.10 later than 3.5.
    """
    return [int(part) for part in re.findall(r"\d+", Path(folder).name)]


def _argyll_folders_in(root):
    """Every ArgyllCMS-looking folder directly inside *root*, newest first.

    CASE-INSENSITIVE, and that is not tidiness. Linux filesystems are
    case-sensitive, so a glob for `Argyll*` never matches a folder called
    `argyll` or `argyll-cms` -- which is what a tarball unpacks to and what a
    distribution package installs. The same search then quietly behaves
    differently on the two platforms.
    """
    try:
        found = [f for f in root.iterdir()
                 if f.name.lower().startswith("argyll") and f.is_dir()]
    except OSError:
        return []
    # Two passes, because the sort is stable: the name pass settles ties, and
    # the version pass then orders by version without disturbing them. That
    # puts `Argyll_V3.5.0` ahead of a `Argyll_V3.5.0_orig` copy kept beside it.
    found.sort(key=lambda f: f.name)
    found.sort(key=_version_order, reverse=True)
    return found


def _roots():
    """The folders whose contents are worth listing, most likely first."""
    home = Path.home()
    # DOWNLOADS IS THE MOST LIKELY FOLDER ON EVERY PLATFORM and was the one
    # missing: the official build is a zip, and what people do with a zip is
    # unpack it and carry on. Desktop and Documents are the same habit.
    landing = [home / "Downloads", home / "Desktop", home / "Documents"]
    if sys.platform == "darwin":
        return [Path("/Applications"), home / "Applications", home] + landing
    if os.name == "nt":
        # OneDrive redirects Desktop and Documents on a great many Windows
        # machines, which moves them out from under the home folder entirely.
        onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
        redirected = ([Path(onedrive), Path(onedrive) / "Desktop",
                       Path(onedrive) / "Documents"] if onedrive else [])
        return [Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
                Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
                Path(os.environ.get("LOCALAPPDATA", str(home))),
                Path("C:/"), home] + landing + redirected
    return ([Path("/opt"), Path("/usr/local"), Path("/usr/share"), home,
             home / "Applications"] + landing)


def _fixed_folders():
    """Folders that hold the tools directly, rather than a folder holding them.

    These are the package managers. Homebrew symlinks the tools straight into
    its own bin, so there is no `Argyll` folder to find -- only `xicclu` next
    to everything else that was ever brewed.
    """
    prefix = os.environ.get("HOMEBREW_PREFIX")
    return ([f"{prefix}/bin"] if prefix else []) + [
        "/opt/homebrew/bin",                    # Homebrew, Apple silicon
        "/usr/local/bin",                       # Homebrew on Intel, and hand-built
        "/home/linuxbrew/.linuxbrew/bin",       # Homebrew on Linux, shared
        str(Path.home() / ".linuxbrew" / "bin"),  # Homebrew on Linux, one user
        "/opt/local/bin",                       # MacPorts
        "/usr/bin",                             # a distribution package
        "/usr/local/Argyll/bin",
        r"C:\Argyll\bin",
    ]


def _candidate_folders():
    """Every folder worth looking in, most likely first, each one only once."""
    seen = set()

    def fresh(folder):
        """Skip anything already offered -- the roots overlap by design."""
        key = str(folder)
        if key in seen:
            return False
        seen.add(key)
        return True

    if EXTRA_FOLDER and fresh(EXTRA_FOLDER):
        yield Path(EXTRA_FOLDER)
    override = os.environ.get(ENV_OVERRIDE)
    if override and fresh(override):
        yield Path(override)
    for root in _roots():
        # THE VERSION-NUMBERED FOLDER IS THE COMMON CASE. The official
        # download unpacks as Argyll_V3.5.0, so looking only for a folder
        # called exactly "Argyll" misses the ordinary installation.
        for found in _argyll_folders_in(root):
            for where in (found / "bin", found):
                if fresh(where):
                    yield where
    for fixed in _fixed_folders():
        if fresh(fixed):
            yield Path(fixed)


#: Tools that were found but could not be run, from the last search. A zip
#: unpacked by something that dropped the executable bit gives exactly this,
#: and "not found" would be a lie about it.
_unrunnable: list = []


#: Set this to anything and the search finds nothing, wherever ArgyllCMS
#: really is.
#:
#: WHY THIS EXISTS, and it is worth the four lines. Most of this application
#: works without ArgyllCMS and takes a different path when it is absent --
#: profiles are read directly, and three separate fallbacks depend on it. The
#: machines that run the checks have no ArgyllCMS; the machine they are
#: written on has it installed in /Applications, which no PATH change hides,
#: because the search deliberately looks in fixed folders as well.
#:
#: So the developer cannot see what most users see, and it has already cost a
#: release: a fallback added for "ArgyllCMS is missing" was written with only
#: its happy path, passed locally where that branch is never taken with a bad
#: file, and failed on all five build machines at once.
#:
#:     GAMUTVIEW_NO_ARGYLL=1 pytest -q      # as a machine without it
NO_ARGYLL = "GAMUTVIEW_NO_ARGYLL"


def find_tool(name: str) -> "str | None":
    """Where ArgyllCMS keeps *name*, if it is installed anywhere usual."""
    if os.environ.get(NO_ARGYLL):
        return None
    if name in _cache:
        return _cache[name]
    found = shutil.which(name)
    if not found:
        for folder in _candidate_folders():
            for candidate in (folder / name, folder / f"{name}.exe"):
                try:
                    if not candidate.is_file():
                        continue
                    # THE EXECUTABLE BIT IS A POSIX IDEA. Windows has none,
                    # and os.access(..., X_OK) there answers True for any file
                    # that exists -- including a text file. Asking anyway does
                    # not make the answer more careful, it makes it meaningless
                    # on one platform while looking identical in the source.
                    if os.name == "nt" or os.access(candidate, os.X_OK):
                        found = str(candidate)
                        break
                    # THERE, BUT NOT ALLOWED TO RUN. Worth remembering rather
                    # than passing over in silence: the file is sitting where
                    # the user says it is, and telling them it was not found
                    # sends them looking for the wrong problem entirely.
                    if str(candidate) not in _unrunnable:
                        _unrunnable.append(str(candidate))
                except OSError:
                    continue
            if found:
                break
    _cache[name] = found
    return found


def searched_folders() -> list:
    """Every folder a search actually opens, in order. For tests and for
    anyone asking the precise question "is this path probed?"."""
    return [str(f) for f in _candidate_folders()]


def shorten(folder) -> str:
    """A path as somebody would write it, so a list of them stays narrow.

    THIS IS A LAYOUT CONSTRAINT, not a cosmetic one. The message box is a
    fixed 470 points wide by design, and a wrapping label demands room for its
    longest line: written out in full, eight home-folder paths pushed what the
    dialog needed from 389 points to 597 and the buttons were cut off the
    right-hand edge. Measured, after it happened.
    """
    text = str(folder)
    try:
        home = str(Path.home())
    except (OSError, RuntimeError):
        return text
    if text == home:
        return "~"
    if text.startswith(home + os.sep) or text.startswith(home + "/"):
        return "~" + text[len(home):]
    return text


def _existing(folders) -> list:
    """Those that are really there, in order, each one once.

    DROPS WHAT DOES NOT EXIST because a Mac being told that C:\\Argyll\\bin was
    checked reads as a fault rather than as diligence, and stops the reader
    believing the rest of the message.
    """
    seen, kept = set(), []
    for folder in folders:
        try:
            if not Path(folder).is_dir():
                continue
        except OSError:
            continue
        short = shorten(folder)
        if short not in seen:
            seen.add(short)
            kept.append(short)
    return kept


def searched_places() -> tuple:
    """Where it looked, as ``(folders searched by name, folders of tools)``.

    NOT THE SAME as searched_folders(), and the difference is the whole point.
    That one names the folders actually opened, which on a machine with
    nothing installed does not include Downloads at all -- there is no Argyll
    folder inside it to open. So the one thing the user most needs to hear,
    "yes, I did look in your Downloads", is precisely what it cannot say.

    Two lists rather than one because they are searched for different things,
    and saying so once is shorter and clearer than repeating the reason on
    every line.
    """
    return _existing(_roots()), _existing(_fixed_folders())


def found_but_not_runnable() -> list:
    """Tools that are present but have no executable bit, from the last
    search. Empty until a search has actually run."""
    return list(_unrunnable)


def forget() -> None:
    """Search again next time -- for a test, or after somebody installs it."""
    _cache.clear()
    _unrunnable.clear()


def status() -> dict:
    """Whether it is here, where, and which version -- for showing somebody."""
    tool = find_tool("iccgamut")
    if tool is None:
        return {"found": False, "folder": None, "version": None}
    version = None
    try:
        import subprocess
        done = subprocess.run([tool], capture_output=True, text=True, timeout=15)
        for line in ((done.stdout or "") + (done.stderr or "")).splitlines():
            if "Version" in line:
                version = line.split("Version", 1)[1].strip().split()[0]
                break
    except Exception:                                    # noqa: BLE001
        pass
    return {"found": True, "folder": str(Path(tool).parent), "version": version}


def summary() -> str:
    """One line for the window, saying what somebody actually wants to know."""
    got = status()
    if got["found"]:
        which = f" {got['version']}" if got["version"] else ""
        return f"ArgyllCMS{which} found — every file type can be opened."
    return ("ArgyllCMS was not found — nothing is wrong. Measurements and "
            "profiles still open; only .cxf, .mxf and .txt files need it.")
