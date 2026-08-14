"""Check the whole graphical stack loads, and say precisely what did not.

Run from the build workflow on every platform. A bare ``import gamut_app``
that dies reports an ImportError naming a Python module, when the real cause
is almost always a missing *system* library underneath Qt -- and if the run is
later cancelled its logs are discarded, so the diagnosis has to be printed
while the job is still running.

A real file rather than an inline snippet, because the workflow runs the same
step on Linux, macOS and Windows: a shell heredoc is bash-only and fails on
the Windows runner, which defaults to PowerShell.
"""
import pathlib
import subprocess
import sys
import traceback

# Python puts the *script's* directory on sys.path, not the working directory
# -- so with this file in .github/ the application would not be importable at
# all, and the check would report a missing module that is not missing. The
# application's own directory is resolved from this file's location, which
# holds wherever the step is run from.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / "python"))

#: Loaded in this order so the first failure names the layer that broke,
#: rather than the application on top of all of them.
LAYERS = (
    ("Qt core", "PyQt6.QtCore"),
    ("Qt widgets", "PyQt6.QtWidgets"),
    ("QtWebEngine", "PyQt6.QtWebEngineWidgets"),
    ("the application", "gamut_app"),
)


def report_missing_libraries() -> None:
    """Name the shared libraries Qt cannot find, on platforms that can say.

    ``ldd`` is Linux-only; on macOS and Windows a failure here is not a
    missing system package and there is nothing useful to add.
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        import PyQt6
    except ImportError:
        return
    root = pathlib.Path(PyQt6.__file__).parent
    for lib in sorted(root.rglob("libQt6WebEngineCore.so*")):
        print(f"--- ldd {lib} ---", flush=True)
        try:
            done = subprocess.run(["ldd", str(lib)], capture_output=True,
                                  text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"(could not run ldd: {exc})")
            return
        for line in done.stdout.splitlines():
            if "not found" in line:
                print(f"  MISSING {line.strip()}")
        print(done.stdout)


def main() -> int:
    for name, module in LAYERS:
        try:
            __import__(module)
        except BaseException:            # noqa: BLE001 — a crash is a result
            print(f"FAIL {name} ({module})", flush=True)
            traceback.print_exc()
            report_missing_libraries()
            return 1
        print(f"ok   {name} ({module})", flush=True)
    print("the whole graphical stack loads, including QtWebEngine")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
