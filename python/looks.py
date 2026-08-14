"""Looks somebody saved themselves — kept in a folder, so they can be shared.

WHAT A LOOK IS
--------------
The set of choices that decide what a saved picture looks like rather than
what is in it: what is behind the shape, what the three walls are, and what
colour the lettering and the grid lines come out. Nothing about size, format,
length or speed — those belong to the file, not to the look, and mixing them
in would mean a look you saved for a document quietly changed how long your
next moving picture ran for.

WHERE THEY LIVE, AND WHY THERE
------------------------------
In a folder called **Picture Looks**, beside the presets ChromIQ itself keeps
— ``~/Library/Preferences/ChromIQ/presets`` on a Mac, ``%APPDATA%\\ChromIQ\\
presets`` on Windows, ``~/.config/ChromIQ/presets`` elsewhere. The same place,
the same one-file-per-preset arrangement and the same three buttons as the
Presets on ChromIQ's own manual tabs, for the same stated reason: so they can
be browsed, copied and shared with an ordinary file manager.

An ordinary folder in an ordinary place, so:

* you can find it without being told twice;
* a look is one small file, so sharing one is sending somebody a file, and
  using one they sent is putting it in that folder;
* nothing here has to be exported or imported, because there is nothing to
  export — the folder IS the store.

The folder is looked at every time the list is drawn, so a file dropped in
while the application is running appears the next time the save window is
opened. Nothing needs restarting.

REMOVING ONE NEVER DESTROYS IT
------------------------------
"Remove" moves the file into ``Looks/old/<date and time>/``. Somebody who
removes the wrong one, or changes their mind a week later, still has it — and
a look can be the result of a long afternoon of matching a house style, which
is exactly the sort of thing that must not be one click from gone.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

#: What a look is allowed to carry. Anything else in a file is ignored rather
#: than refused, so a look written by a later version still works here — it
#: simply brings across the parts this version understands.
FIELDS = ("background", "colour", "walls", "wall_colour",
          "lettering", "lettering_colour", "gridlines", "gridlines_colour")

SUFFIX = ".gamutlook.json"


class LookProblem(Exception):
    """Something about a look could not be done, with a reason worth reading."""


def presets_root() -> Path:
    """The folder ChromIQ keeps its own presets in, on each platform.

    The same rule as ChromIQ's core/platform_paths.py, deliberately: two
    applications from the same family putting shareable presets in two
    different places is the sort of small inconsistency that costs somebody an
    afternoon of hunting.
    """
    import os
    import sys

    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "ChromIQ"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Preferences" / "ChromIQ"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".config") / "ChromIQ"
    return base / "presets"


def folder() -> Path:
    """Where saved looks are kept. Made when it is first needed."""
    return presets_root() / "Picture Looks"


def safe_name(name: str) -> str:
    """A file name every system accepts, from whatever was typed."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(name)).strip(" .")
    cleaned = re.sub(r"[-\s]{2,}", " ", cleaned)
    return cleaned[:60]


def path_for(name: str) -> Path:
    return folder() / f"{safe_name(name)}{SUFFIX}"


def save(name: str, values: dict) -> Path:
    """Write a look, replacing one of the same name — after keeping the old.

    Saving over a look you already had is the one place here where something
    could be lost without being asked about, so the one being replaced is put
    away first, the same way a removed one is.
    """
    name = safe_name(name)
    if not name:
        raise LookProblem(
            "A look needs a name. Something that says where you use it — "
            "“Our white reports” or “Dark slides” — is worth more in six "
            "months than “Look 3”.")
    where = folder()
    where.mkdir(parents=True, exist_ok=True)
    target = path_for(name)
    if target.exists():
        _put_away(target)
    kept = {key: values[key] for key in FIELDS if key in values}
    target.write_text(json.dumps(
        {"name": name, "saved": time.strftime("%Y-%m-%d %H:%M"),
         "made_by": "ChromIQ Gamut Viewer", "look": kept},
        indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def _put_away(target: Path) -> Path:
    """Move a look into old/<date and time>/ rather than deleting it."""
    old = folder() / "old" / time.strftime("%Y-%m-%d %H-%M-%S")
    old.mkdir(parents=True, exist_ok=True)
    moved = old / target.name
    target.replace(moved)
    return moved


def remove(name: str) -> Path:
    """Take a look off the list, keeping the file in old/<date and time>/."""
    target = path_for(name)
    if not target.exists():
        raise LookProblem(f"There is no saved look called “{name}”.")
    return _put_away(target)


def load_all() -> list:
    """Every saved look, newest name order, skipping anything unreadable.

    A file that cannot be read is passed over rather than allowed to stop the
    list: one bad file — hand-edited, half-copied, written by something else —
    must not take the other twenty with it.
    """
    where = folder()
    found = []
    try:
        files = sorted(where.glob(f"*{SUFFIX}"))
    except OSError:
        return []
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            values = data.get("look") or {}
            if not isinstance(values, dict):
                continue
            kept = {k: v for k, v in values.items()
                    if k in FIELDS and isinstance(v, str)}
            if not kept:
                continue
            found.append({"name": str(data.get("name") or file.name[:-len(SUFFIX)]),
                          "look": kept, "file": file,
                          "saved": str(data.get("saved") or "")})
        except Exception:                              # noqa: BLE001
            continue
    return found


def describe(entry: dict) -> str:
    """One line saying what a saved look does, for under the chooser."""
    values = entry.get("look", {})
    behind = {"as-shown": "the background as it looks on screen",
              "white": "a white background", "black": "a black background",
              "transparent": "nothing behind the shape",
              "custom": f"a background of {values.get('colour', 'your own')}"
              }.get(values.get("background", "as-shown"), "your background")
    ink = {"follow": "lettering that follows it", "dark": "dark lettering",
           "light": "light lettering",
           "custom": f"lettering in {values.get('lettering_colour', 'your colour')}"
           }.get(values.get("lettering", "follow"), "your lettering")
    when = f" · saved {entry['saved']}" if entry.get("saved") else ""
    return f"Your own look: {behind}, with {ink}.{when}"
