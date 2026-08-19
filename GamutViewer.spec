# PyInstaller spec for the ChromIQ Gamut Viewer.
#
# The awkward part of freezing this is QtWebEngine: it is a browser, with its
# own helper process, resource packs and locales, and PyInstaller does not find
# them by walking imports. collect_all() drags the whole package in, which is
# what makes the bundle large and what makes it actually run.
import os
import pathlib
import sys
from PyInstaller.utils.hooks import collect_all

# THE VERSION THE OPERATING SYSTEM SHOWS COMES FROM version.py, and until now
# it did not. macOS Finder's Get Info reads CFBundleShortVersionString out of
# the bundle's Info.plist, and this file had "1.0.0" typed into it by hand --
# so every release since 1.0.0 has told Finder it was 1.0.0, while the window,
# the --version flag and the update check all said something else. Asked
# plainly: "is the app version also shown in macos finder when asking for
# infos? and other operating systems?" It was shown, and it was wrong.
#
# Read rather than repeated. python/version.py is one line of assignment with
# no imports, so it can be executed on its own without dragging PyQt in.
_VERSION_PY = pathlib.Path(SPECPATH) / "python" / "version.py"
_v: dict = {}
exec(_VERSION_PY.read_text(encoding="utf-8"), _v)
VERSION = _v["__version__"]
APP_NAME = _v["APP_NAME"]
CREDIT = _v["AUTHOR"]
# Windows wants four whole numbers and nothing else. The rule lives in
# version.py so a test can hold it to it; see test_version_metadata.py.
WIN_VERSION = _v["windows_version_tuple"]()

_we_datas, _we_binaries, _we_hidden = collect_all("PyQt6.QtWebEngineCore")
_wew_datas, _wew_binaries, _wew_hidden = collect_all("PyQt6.QtWebEngineWidgets")
# plotly ships its javascript as package data; without it every page is blank.
_pl_datas, _pl_binaries, _pl_hidden = collect_all("plotly")
# scipy.spatial's Qhull extensions are found by import, but its .libs are not.
_sp_datas, _sp_binaries, _sp_hidden = collect_all("scipy")

block_cipher = None

a = Analysis(
    ["python/gamut_app.py"],
    pathex=["python"],
    binaries=_we_binaries + _wew_binaries + _pl_binaries + _sp_binaries,
    datas=(_we_datas + _wew_datas + _pl_datas + _sp_datas
           + [("assets/icon.png", "assets")]),
    # imageio_ffmpeg IS NAMED HERE ON PURPOSE. It is imported inside a
    # try/except in movie.py -- so that running from the source without it
    # still works -- and the ffmpeg program itself is package data rather than
    # an import. PyInstaller's own hook collects the program once the package
    # is in the graph; naming it is what puts it there.
    hiddenimports=(_we_hidden + _wew_hidden + _pl_hidden + _sp_hidden
                   + ["gamutview", "ti3gamut", "version", "movie",
                      "imageio_ffmpeg", "imageio_ffmpeg.binaries"]),
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    # Nothing here needs a plotting backend, a notebook or a test runner.
    excludes=["matplotlib", "tkinter", "IPython", "notebook", "pytest",
              "PyQt6.QtMultimedia", "PyQt6.QtQuick3D", "PyQt6.QtBluetooth"],
    win_no_prefer_redirects=False, win_private_assemblies=False,
    cipher=block_cipher, noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# WHAT WINDOWS SHOWS UNDER RIGHT-CLICK -> PROPERTIES -> DETAILS, which until
# now was nothing at all: with no version resource compiled into the .exe that
# tab is empty, so a Windows user had no way of telling one download from
# another without starting it. The numbers and the names come from version.py
# above, so they cannot drift from the ones the window shows.
_win_version_file = None
if sys.platform == "win32":
    _win_version_file = os.path.join(workpath, "file_version_info.txt")
    pathlib.Path(_win_version_file).write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={WIN_VERSION!r},
    prodvers={WIN_VERSION!r},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', {CREDIT!r}),
      StringStruct('FileDescription', {APP_NAME!r}),
      StringStruct('FileVersion', {VERSION!r}),
      StringStruct('InternalName', 'GamutViewer'),
      StringStruct('LegalCopyright',
                   {f"{APP_NAME} — {CREDIT}. Built on Yet Another Color "
                     "Gamut Visualizer by Qiu Jueqin (MIT)."!r}),
      StringStruct('OriginalFilename', 'GamutViewer.exe'),
      StringStruct('ProductName', {APP_NAME!r}),
      StringStruct('ProductVersion', {VERSION!r})])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")

exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    icon=("assets/icon.icns" if sys.platform == "darwin"
          else "assets/icon.ico" if sys.platform == "win32" else None),
    version=_win_version_file,
    name="GamutViewer", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
               strip=False, upx=False, name="GamutViewer")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="ChromIQ Gamut Viewer.app",
                 icon="assets/icon.icns",
                 bundle_identifier="io.github.itsab1989.gamutviewer",
                 # WHAT FINDER'S GET INFO SHOWS.
                 #   CFBundleShortVersionString -> the "Version" line
                 #   NSHumanReadableCopyright   -> the "Copyright" line
                 #   CFBundleDisplayName        -> the name under the icon
                 # The first two were wrong and missing respectively; all
                 # three now come from version.py, so a release cannot ship
                 # saying one version in the window and another in Finder.
                 info_plist={
                     "CFBundleShortVersionString": VERSION,
                     "CFBundleVersion": VERSION,
                     "CFBundleDisplayName": APP_NAME,
                     "CFBundleName": APP_NAME,
                     "NSHumanReadableCopyright":
                         f"{APP_NAME} {VERSION} — {CREDIT}. Built on Yet "
                         "Another Color Gamut Visualizer by Qiu Jueqin (MIT).",
                     "NSHighResolutionCapable": True,
                     "LSMinimumSystemVersion": "11.0",
                 })
