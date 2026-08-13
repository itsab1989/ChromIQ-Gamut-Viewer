# PyInstaller spec for the Measured Gamut Viewer.
#
# The awkward part of freezing this is QtWebEngine: it is a browser, with its
# own helper process, resource packs and locales, and PyInstaller does not find
# them by walking imports. collect_all() drags the whole package in, which is
# what makes the bundle large and what makes it actually run.
import sys
from PyInstaller.utils.hooks import collect_all

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
    datas=_we_datas + _wew_datas + _pl_datas + _sp_datas,
    hiddenimports=(_we_hidden + _wew_hidden + _pl_hidden + _sp_hidden
                   + ["gamutview", "ti3gamut", "version"]),
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    # Nothing here needs a plotting backend, a notebook or a test runner.
    excludes=["matplotlib", "tkinter", "IPython", "notebook", "pytest",
              "PyQt6.QtMultimedia", "PyQt6.QtQuick3D", "PyQt6.QtBluetooth"],
    win_no_prefer_redirects=False, win_private_assemblies=False,
    cipher=block_cipher, noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="GamutViewer", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
               strip=False, upx=False, name="GamutViewer")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="Measured Gamut Viewer.app",
                 bundle_identifier="io.github.itsab1989.gamutviewer",
                 info_plist={
                     "CFBundleShortVersionString": "1.0.0",
                     "CFBundleVersion": "1.0.0",
                     "NSHighResolutionCapable": True,
                     "LSMinimumSystemVersion": "11.0",
                 })
