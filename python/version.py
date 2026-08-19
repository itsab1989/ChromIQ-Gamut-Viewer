"""One place the version and the name are written down."""
__version__ = "2.39.0"
APP_NAME = "ChromIQ Gamut Viewer"

#: What this is built on. MIT permits redistributing a modified copy under
#: another name provided the copyright and permission notice travel with it,
#: which they do -- LICENSE is kept exactly as inherited and the original is
#: credited in the README and here.
UPSTREAM = ("Yet Another Color Gamut Visualizer by Qiu Jueqin, MIT — "
            "https://github.com/QiuJueqin/Yet-Another-Color-Gamut-Visualizer")

#: Who wrote the application around it. Shown at the foot of the controls
#: column, in the macOS bundle's Get Info panel, and in the Windows .exe's
#: Details tab -- one place, so those three cannot disagree.
AUTHOR = "Sebastian Reiprich"


def windows_version_tuple(version: str = __version__) -> tuple:
    """The four whole numbers a Windows version resource insists on.

    Windows will not take "2.39.0" and it will not take "2.39.0-beta.1": the
    FixedFileInfo block is four 16-bit numbers, full stop. A pre-release keeps
    the numeric part and drops the tail, so beta.1 and the final release show
    the same four numbers -- which is right, because that field is what
    Windows compares, and the full string is carried beside it in
    FileVersion, where it is shown to a person.
    """
    numbers = [int(n) for n in version.split("-")[0].split(".")][:3]
    return tuple((numbers + [0, 0, 0, 0])[:4])
