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
who keeps it somewhere of their own.
"""
from __future__ import annotations

import os
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


def looks_like_argyll(folder) -> bool:
    """Whether *folder* actually holds the tools, so a wrong pick can be
    turned down at the moment it is made rather than at the moment it fails."""
    folder = Path(folder)
    for name in ("iccgamut", "cxf2ti3", "txt2ti3", "targen"):
        if (folder / name).is_file() or (folder / f"{name}.exe").is_file():
            return True
    return False

#: What each file type needs, in the user's words rather than the tool's.
NEEDS_ARGYLL = {
    ".cxf": "cxf2ti3",
    ".mxf": "cxf2ti3",
    ".txt": "txt2ti3",
}

_cache: dict = {}


def _candidate_folders():
    """Every folder worth looking in, most likely first."""
    if EXTRA_FOLDER:
        yield Path(EXTRA_FOLDER)
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        yield Path(override)
    home = Path.home()
    if sys.platform == "darwin":
        roots = [Path("/Applications"), home / "Applications", home]
    elif os.name == "nt":
        roots = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
                 Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
                 Path(os.environ.get("LOCALAPPDATA", str(home))),
                 Path("C:/"), home]
    else:
        roots = [Path("/opt"), Path("/usr/local"), home, home / "Applications"]
    for root in roots:
        # THE VERSION-NUMBERED FOLDER IS THE COMMON CASE. The official
        # download unpacks as Argyll_V3.5.0, so looking only for a folder
        # called exactly "Argyll" misses the ordinary installation.
        try:
            for found in sorted(root.glob("Argyll*"), reverse=True):
                if found.is_dir():
                    yield found / "bin"
                    yield found
        except OSError:
            continue
    for fixed in ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin",
                  "/opt/local/bin", r"C:\Argyll\bin"):
        yield Path(fixed)


def find_tool(name: str) -> "str | None":
    """Where ArgyllCMS keeps *name*, if it is installed anywhere usual."""
    if name in _cache:
        return _cache[name]
    found = shutil.which(name)
    if not found:
        for folder in _candidate_folders():
            for candidate in (folder / name, folder / f"{name}.exe"):
                try:
                    if candidate.is_file() and os.access(candidate, os.X_OK):
                        found = str(candidate)
                        break
                except OSError:
                    continue
            if found:
                break
    _cache[name] = found
    return found


def forget() -> None:
    """Search again next time -- for a test, or after somebody installs it."""
    _cache.clear()


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
