"""Finding ArgyllCMS, and being honest about needing it.

Nothing here installs, moves or runs anything of consequence: the searches are
pointed at folders the test makes itself, so a machine with ArgyllCMS and a
machine without both give the same answers.
"""
import os

import pytest

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
    opening = {u.toLocalFile() for u in gamut_app._sidebar_urls("", profiles=True)}
    saving = {u.toLocalFile() for u in gamut_app._sidebar_urls("", profiles=False)}
    assert saving <= opening
    for folder in gamut_app.PROFILE_FOLDERS:
        assert str(folder) not in saving
    # NOT "the list is non-empty": a machine with no desktop and no Pictures
    # folder -- a build runner, for one -- legitimately has none of these, and
    # the application drops what does not exist rather than offering a dead
    # entry. What must hold is that saving never loses an ordinary folder that
    # opening offers.
    ordinary = {u for u in opening
                if not any(str(f) == u for f in gamut_app.PROFILE_FOLDERS)}
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
