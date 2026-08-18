"""Finding ArgyllCMS, and being honest about needing it.

Nothing here installs, moves or runs anything of consequence: the searches are
pointed at folders the test makes itself, so a machine with ArgyllCMS and a
machine without both give the same answers.
"""
import os

import pytest

@pytest.fixture(autouse=True)
def _really_search(monkeypatch):
    """This file tests the SEARCH, so the "pretend it is not installed" switch
    must not reach it.

    GAMUTVIEW_NO_ARGYLL makes `find_tool` answer None however ArgyllCMS is
    installed, so that the rest of the suite can be run as a machine without
    it -- which is what every build machine is, and what the machine these
    are written on is not. Here it would turn every check into a check that
    the switch works, which is one line of it and not the point of the file.
    """
    import argyll
    monkeypatch.delenv(argyll.NO_ARGYLL, raising=False)


import argyll


@pytest.fixture(autouse=True)
def _clean():
    """Every test starts with no override and no remembered answer."""
    argyll.set_folder(None)
    os.environ.pop(argyll.ENV_OVERRIDE, None)
    yield
    argyll.set_folder(None)
    os.environ.pop(argyll.ENV_OVERRIDE, None)
    argyll.forget()


def _fake_install(root, name="iccgamut"):
    """A folder that looks like an ArgyllCMS installation."""
    binfolder = root / "bin"
    binfolder.mkdir(parents=True)
    tool = binfolder / name
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    return binfolder


def test_a_folder_the_user_chose_is_looked_in_first(tmp_path, monkeypatch):
    """The whole point of the button: somebody keeping it somewhere unusual
    must be able to say so and have it believed."""
    binfolder = _fake_install(tmp_path / "Somewhere Odd")
    monkeypatch.setattr(argyll.shutil, "which", lambda _n: None)
    argyll.set_folder(str(binfolder))
    assert argyll.find_tool("iccgamut") == str(binfolder / "iccgamut")


def test_the_version_numbered_folder_is_found(tmp_path, monkeypatch):
    """The official download unpacks as Argyll_V3.5.0, not as "Argyll" -- so
    looking only for the bare name misses the ordinary installation."""
    binfolder = _fake_install(tmp_path / "Argyll_V3.5.0")
    monkeypatch.setattr(argyll.shutil, "which", lambda _n: None)
    monkeypatch.setattr(argyll.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(argyll.sys, "platform", "linux")
    argyll.forget()
    assert argyll.find_tool("iccgamut") == str(binfolder / "iccgamut")


def test_the_newest_version_wins_when_there_are_several(tmp_path, monkeypatch):
    """Two installations side by side: the later one is the one to use."""
    _fake_install(tmp_path / "Argyll_V2.0.0")
    newer = _fake_install(tmp_path / "Argyll_V3.5.0")
    monkeypatch.setattr(argyll.shutil, "which", lambda _n: None)
    monkeypatch.setattr(argyll.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(argyll.sys, "platform", "linux")
    argyll.forget()
    assert argyll.find_tool("iccgamut") == str(newer / "iccgamut")


def test_the_environment_variable_still_works(tmp_path, monkeypatch):
    binfolder = _fake_install(tmp_path / "Elsewhere")
    monkeypatch.setattr(argyll.shutil, "which", lambda _n: None)
    os.environ[argyll.ENV_OVERRIDE] = str(binfolder)
    argyll.forget()
    assert argyll.find_tool("iccgamut") == str(binfolder / "iccgamut")


def test_nothing_installed_is_answered_calmly(tmp_path, monkeypatch):
    """Not having it is not an error. It must come back as None, and the line
    shown to the user must say the app still works."""
    monkeypatch.setattr(argyll.shutil, "which", lambda _n: None)
    monkeypatch.setattr(argyll.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(argyll, "_candidate_folders", lambda: iter([tmp_path]))
    argyll.forget()
    assert argyll.find_tool("iccgamut") is None
    said = argyll.summary()
    assert "not found" in said and "nothing is wrong" in said.lower()
    assert ".cxf" in said            # says exactly what is affected


def test_a_wrong_folder_is_recognised_as_wrong(tmp_path):
    """So the pick can be turned down while the user is still looking at the
    folder chooser, rather than days later when a file will not open."""
    (tmp_path / "empty").mkdir()
    assert not argyll.looks_like_argyll(tmp_path / "empty")
    assert not argyll.looks_like_argyll(tmp_path / "does-not-exist")
    assert argyll.looks_like_argyll(_fake_install(tmp_path / "Argyll"))


def test_picking_the_argyll_folder_works_as_well_as_picking_bin(tmp_path):
    """The pick somebody actually makes.

    `/Applications/Argyll` is the folder with the name on it; `bin` is an
    implementation detail they have no reason to know about. Turning that pick
    down -- which is what happened -- teaches somebody the button is broken at
    the moment they are trying to help themselves.
    """
    binfolder = _fake_install(tmp_path / "Argyll_V3.5.0")
    outer = tmp_path / "Argyll_V3.5.0"

    assert argyll.looks_like_argyll(outer), "the obvious pick was refused"
    assert argyll.tools_folder(outer) == binfolder      # and bin was found for them
    assert argyll.tools_folder(binfolder) == binfolder  # picking bin still works
    assert argyll.tools_folder(tmp_path / "nowhere") is None


def test_a_newer_version_wins_even_when_the_digits_read_as_text(tmp_path,
                                                                monkeypatch):
    """3.10 is later than 3.5, and a plain string sort says the opposite.

    The existing check used V2.0.0 against V3.5.0, where sorting as text gives
    the right answer by luck -- so it passed while the ordering was wrong. This
    is the pair that tells them apart.
    """
    _fake_install(tmp_path / "Argyll_V3.5.0")
    newer = _fake_install(tmp_path / "Argyll_V3.10.0")
    monkeypatch.setattr(argyll.shutil, "which", lambda _n: None)
    monkeypatch.setattr(argyll.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(argyll.sys, "platform", "linux")
    argyll.forget()
    assert argyll.find_tool("iccgamut") == str(newer / "iccgamut")


def test_a_lowercase_folder_is_found_too(tmp_path, monkeypatch):
    """Linux filesystems are case-sensitive, so a glob for `Argyll*` misses
    `argyll` and `argyll-cms` -- which is what a tarball unpacks to and what a
    distribution package installs. The same search then behaves differently on
    the two platforms for no reason the user can see."""
    binfolder = _fake_install(tmp_path / "argyll-cms")
    monkeypatch.setattr(argyll.shutil, "which", lambda _n: None)
    monkeypatch.setattr(argyll.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(argyll.sys, "platform", "linux")
    argyll.forget()
    assert argyll.find_tool("iccgamut") == str(binfolder / "iccgamut")


@pytest.mark.parametrize("landing", ["Downloads", "Desktop", "Documents"])
@pytest.mark.parametrize("platform,osname",
                         [("darwin", "posix"), ("win32", "nt"),
                          ("linux", "posix")])
def test_it_is_found_where_a_download_actually_lands(tmp_path, monkeypatch,
                                                     landing, platform, osname):
    """The gap this whole task came from. The official build is a zip, and
    what people do with a zip is unpack it and carry on -- so Downloads is the
    single most likely folder on any platform, and it was not being looked in.

    ASKS WHETHER THE FOLDER IS SEARCHED, not what find_tool finally answers,
    and that is deliberate. The roots include real system folders that are not
    redirected by faking the home directory -- /Applications on this very
    machine holds an installation -- so an equality check against find_tool
    passes or fails on what the developer happens to have installed rather
    than on the behaviour under test.
    """
    binfolder = _fake_install(tmp_path / landing / "Argyll_V3.5.0")
    monkeypatch.setattr(argyll.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(argyll.sys, "platform", platform)
    monkeypatch.setattr(argyll.os, "name", osname)
    argyll.forget()
    assert str(binfolder) in argyll.searched_folders(), (
        f"{landing} is not looked in on {platform}")


def test_the_homebrew_folders_are_looked_in():
    """Homebrew genuinely carries it: the argyll-cms formula does
    `prefix.install "bin"`, so the tools are symlinked into $(brew --prefix)/bin
    -- and the formula has arm64_linux and x86_64_linux bottles, so Linux
    Homebrew is a real installation rather than a curiosity.

    NONE OF THESE ARE ON THE PATH OF A BUNDLED APPLICATION. Measured on macOS:
    `launchctl getenv PATH` is unset, so an app started from Finder gets
    /usr/bin:/bin:/usr/sbin:/sbin. If the folder is not in this list, a
    Homebrew install cannot be found at all.
    """
    looked = set(argyll._fixed_folders())
    assert "/opt/homebrew/bin" in looked            # Apple silicon
    assert "/usr/local/bin" in looked               # Intel
    assert "/home/linuxbrew/.linuxbrew/bin" in looked   # Linux, shared
    assert "/opt/local/bin" in looked               # MacPorts
    assert "/usr/bin" in looked                     # a distribution package


def test_a_moved_homebrew_is_followed(monkeypatch):
    """HOMEBREW_PREFIX is what brew itself exports, so it is the honest answer
    for anybody who did not install it in the default place."""
    monkeypatch.setenv("HOMEBREW_PREFIX", "/somewhere/of/my/own")
    assert "/somewhere/of/my/own/bin" in argyll._fixed_folders()


@pytest.mark.skipif(os.name == "nt",
                    reason="Windows has no executable bit: os.access(X_OK) "
                           "answers True for any file that exists, so there "
                           "is no such thing as present-but-not-runnable to "
                           "detect. Found by this very check going red on the "
                           "Windows build while passing everywhere else.")
def test_a_tool_that_cannot_run_is_not_reported_as_missing(tmp_path,
                                                           monkeypatch):
    """A zip unpacked by something that does not carry Unix permissions leaves
    every program in place and none of them runnable. Saying "not found" sends
    somebody looking for the wrong problem entirely."""
    binfolder = tmp_path / "Argyll" / "bin"
    binfolder.mkdir(parents=True)
    tool = binfolder / "iccgamut"
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o644)                                    # there, but not runnable
    monkeypatch.setattr(argyll.shutil, "which", lambda _n: None)
    monkeypatch.setattr(argyll, "_candidate_folders", lambda: iter([binfolder]))
    argyll.forget()

    assert argyll.find_tool("iccgamut") is None           # honestly unusable
    assert str(tool) in argyll.found_but_not_runnable()   # but say why


def test_where_it_looked_can_be_shown_and_repeats_nothing(monkeypatch,
                                                          tmp_path):
    """The "not found" message names the folders. Duplicates would pad it with
    the same path three times, because the roots deliberately overlap."""
    monkeypatch.setattr(argyll.Path, "home", staticmethod(lambda: tmp_path))
    looked = argyll.searched_folders()
    assert looked, "the search covers nothing at all"
    assert len(set(looked)) == len(looked), "a folder is listed twice"


def test_the_message_says_it_looked_in_downloads_even_when_it_is_empty(
        tmp_path, monkeypatch):
    """The case the user is actually in when they read the message.

    A list built from the folders PROBED cannot mention Downloads on a machine
    with nothing installed -- there is no Argyll folder inside it to probe --
    which is exactly the machine whose owner needs telling that it was looked
    in. So the shown list names the places searched instead.
    """
    (tmp_path / "Downloads").mkdir()
    monkeypatch.setattr(argyll.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(argyll.sys, "platform", "darwin")
    argyll.forget()

    assert not any("Downloads" in f for f in argyll.searched_folders())
    roots, _tools = argyll.searched_places()
    assert any("Downloads" in place for place in roots), roots


def test_nothing_is_named_that_does_not_exist_on_this_machine(tmp_path,
                                                              monkeypatch):
    """A Mac told that C:\\Argyll\\bin was checked reads it as a fault rather
    than as diligence, and stops believing the rest of the message."""
    monkeypatch.setattr(argyll.Path, "home", staticmethod(lambda: tmp_path))
    roots, tools = argyll.searched_places()
    for place in list(roots) + list(tools):
        # Written the short way for the message, so "~" has to come back to a
        # real path before it can be asked whether it exists.
        folder = place.replace("~", str(tmp_path), 1) if place.startswith("~") \
            else place
        assert os.path.isdir(folder), f"named a folder that is not there: {folder}"


def test_the_search_survives_a_folder_it_may_not_read(tmp_path, monkeypatch):
    """A root that cannot be listed must not stop the search."""
    forbidden = tmp_path / "forbidden"
    forbidden.mkdir()
    binfolder = _fake_install(tmp_path / "Argyll")
    monkeypatch.setattr(argyll.shutil, "which", lambda _n: None)

    def folders():
        yield forbidden / "no" / "such" / "place"
        yield binfolder

    monkeypatch.setattr(argyll, "_candidate_folders", folders)
    argyll.forget()
    assert argyll.find_tool("iccgamut") == str(binfolder / "iccgamut")


def test_the_answer_is_remembered_rather_than_searched_for_again(monkeypatch):
    calls = []
    monkeypatch.setattr(argyll.shutil, "which",
                        lambda n: calls.append(n) or "/somewhere/iccgamut")
    argyll.forget()
    argyll.find_tool("iccgamut")
    argyll.find_tool("iccgamut")
    assert len(calls) == 1


def test_choosing_a_folder_starts_the_search_again():
    """Otherwise the remembered answer would outlive the setting that changed
    it, and the button would appear to do nothing."""
    argyll._cache["iccgamut"] = "/old/iccgamut"
    argyll.set_folder(None)
    assert "iccgamut" not in argyll._cache


def test_the_file_types_that_need_it_are_the_ones_documented():
    """This list is what the help text promises, so it must not drift."""
    assert set(argyll.NEEDS_ARGYLL) == {".cxf", ".mxf", ".txt"}
    assert argyll.DOWNLOAD_URL.startswith("https://")


# --- the file dialog's shortcuts, on every platform --------------------------

def test_each_platform_is_offered_its_own_profile_folders():
    """A shortcut list that is right on the machine it was written on and
    wrong everywhere else is worse than none: it sends somebody to a folder
    their system does not use.

    Checked as strings on purpose. pathlib decides whether a Path is a Windows
    one from os.name when it is BUILT, so a test that fakes the platform and
    then builds a Path raises instead of checking anything -- which is how an
    earlier attempt at this "passed" while testing nothing.
    """
    from gamut_app import profile_folder_names

    mac = profile_folder_names("darwin", "posix", "/Users/x")
    assert "/Users/x/Library/ColorSync/Profiles" in mac
    assert "/System/Library/ColorSync/Profiles" in mac      # sRGB, Display P3
    assert "/Library/ColorSync/Profiles" in mac             # what a paper maker adds

    win = profile_folder_names("win32", "nt", r"C:\\Users\\x", "C:/Windows",
                               "C:/Users/x/AppData/Local")
    assert "C:/Windows/System32/spool/drivers/color" in win   # for everyone
    assert "C:/Users/x/AppData/Local/Microsoft/Windows/Color" in win   # yours
    # %SystemRoot% is honoured: Windows is not always installed on C:.
    other = profile_folder_names("win32", "nt", "D:/Users/x", "D:/Windows")
    assert other[0].startswith("D:/Windows")

    linux = profile_folder_names("linux", "posix", "/home/x")
    assert "/home/x/.local/share/icc" in linux      # XDG, colord and GNOME
    assert "/usr/share/color/icc" in linux           # installed for everyone
    assert "/home/x/.color/icc" in linux             # Argyll and oyranos

    for got in (mac, win, linux):
        assert got, "a platform was left with no shortcuts at all"
        assert len(set(got)) == len(got), f"a folder is listed twice: {got}"


def test_a_folder_with_no_profiles_in_it_is_not_offered(tmp_path):
    """A shortcut that opens on an empty folder is a small lie about where
    things are."""
    from gamut_app import _holds_profiles
    empty = tmp_path / "empty"; empty.mkdir()
    assert not _holds_profiles(empty)
    assert not _holds_profiles(tmp_path / "not-there-at-all")
    (empty / "readme.txt").write_text("x")
    assert not _holds_profiles(empty)
    (empty / "something.icc").write_bytes(b"\0" * 8)
    assert _holds_profiles(empty)
    (empty / "another.ICM").write_bytes(b"\0" * 8)          # case does not matter
    assert _holds_profiles(empty)


def test_saving_is_not_offered_folders_it_cannot_write_to():
    """The profile folders belong to the operating system, so a save dialog
    offering them is offering three shortcuts to a refusal. They are for
    opening a profile, which is the only thing anybody does in them."""
    import gamut_app
    # COMPARED AS PATHS, NOT STRINGS. A URL hands back forward slashes on
    # every system while Windows writes its paths with backslashes, so a plain
    # string comparison quietly matches nothing there and the check passes by
    # accident -- which is how this first went out failing only on Windows.
    from pathlib import Path
    opening = {Path(u.toLocalFile()) for u in
               gamut_app._sidebar_urls("", profiles=True)}
    saving = {Path(u.toLocalFile()) for u in
              gamut_app._sidebar_urls("", profiles=False)}
    assert saving <= opening
    for folder in gamut_app.PROFILE_FOLDERS:
        assert Path(folder) not in saving
    # NOT "the list is non-empty": a machine with no desktop and no Pictures
    # folder -- a build runner, for one -- legitimately has none of these, and
    # the application drops what does not exist rather than offering a dead
    # entry. What must hold is that saving never loses an ordinary folder that
    # opening offers.
    ordinary = {u for u in opening
                if not any(Path(f) == u for f in gamut_app.PROFILE_FOLDERS)}
    assert saving == ordinary


def test_every_dialog_is_ours_rather_than_the_systems():
    """Only a non-native dialog can carry the shortcuts down the left, which
    is the difference between finding a file in one click and hunting."""
    import inspect

    import gamut_app
    source = inspect.getsource(gamut_app.GamutApp._file_dialog)
    assert "DontUseNativeDialog" in source
    assert "setSidebarUrls" in source
    # Exactly one dialog is ever built, and it is this one: any other route
    # making its own would get the system's, with no shortcuts in it.
    assert source.count("QFileDialog(") == 1
    whole = inspect.getsource(gamut_app.GamutApp)
    assert whole.count("QFileDialog(") == 1, "a second dialog is built somewhere"


def test_the_static_shortcuts_ask_for_our_dialog_too():
    """The gap the check above cannot see.

    ``QFileDialog.getExistingDirectory`` and its siblings are static
    convenience methods: they build their own dialog and inherit nothing from
    the shared factory, so counting ``QFileDialog(`` never notices them. One
    of them was opening the system's folder chooser for "Where ArgyllCMS is…"
    while every other dialog in the window was ours — the kind of difference
    somebody feels without being able to name it.

    Every one of them must be passed DontUseNativeDialog explicitly, and this
    reads the call rather than the file so a new one cannot be added quietly.
    """
    import ast
    import inspect
    import textwrap

    import gamut_app
    STATIC = {"getExistingDirectory", "getOpenFileName", "getOpenFileNames",
              "getSaveFileName", "getOpenFileUrl", "getSaveFileUrl",
              "getExistingDirectoryUrl"}
    tree = ast.parse(textwrap.dedent(inspect.getsource(gamut_app)))
    found = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in STATIC):
            continue
        owner = getattr(func.value, "id", "")
        if owner != "QFileDialog":
            continue
        found += 1
        text = ast.unparse(node)
        assert "DontUseNativeDialog" in text, (
            f"{func.attr} opens the system's dialog: {text[:120]}")
    # If this ever drops to zero the check has quietly stopped checking.
    assert found >= 1, "no static QFileDialog call found — has one been renamed?"


def test_the_surface_resolution_is_asked_for_and_not_left_to_argyll():
    """The two ways of reading one profile have to agree.

    ASKED FOR NOTHING UNTIL NOW, so Argyll's own default decided -- and that
    default is the outlier. This application reads a profile two ways:
    `iccgamut`, and the direct reader used when ArgyllCMS is missing or
    refuses. Measured on five profiles, as the gap between the two readers'
    volumes for the SAME file:

        -d          default      8        6        4
        disagree      0.73%   0.19%    0.03%    0.16%
        per profile   0.15s   0.36s    0.71s    3.16s

    6 is where the two doors into one profile agree exactly, and 4 overshoots
    the other way.

    AND IT COSTS NOTHING TO TURN, which took two measurements because the
    first was of the wrong thing. Twenty FORCED passes back to back said 6
    was over a frame and 8 was not, and 8 shipped on that. The application
    never does that: the engine skips a pass when the camera has barely
    turned, spaces itself to three times its own cost, stops when the picture
    settles, and never touches a solid surface. Dragged for real -- mouse
    events at the canvas, three seconds each:

        -d   triangles   median    90th   frames over 16.7 ms
        10       3,666   16.9ms  23.1ms   99 of 179
         8       5,958   16.5ms  26.2ms   81 of 178
         6       8,876   16.0ms  29.4ms   77 of 172
         4      18,180   16.1ms  38.1ms   64 of 173

    Five times the triangles does not slow the drag, and Argyll's own default
    has the MOST frames over budget. So there is nothing to trade.

    """
    import inspect

    import references

    assert references.SURFACE_DETAIL == 6, (
        "the surface resolution changed; 6 is where the two readers agree, "
        "and a real drag was measured to cost no more at 6 than at Argyll's "
        "own default")
    src = inspect.getsource(references.icc_gamut)
    assert '"-d", str(SURFACE_DETAIL)' in src, (
        "iccgamut is asked for no surface resolution again, so Argyll's "
        "default decides and the two readers disagree by 0.73%")
