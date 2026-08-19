"""The version the operating system shows must be the version we shipped.

WHY THIS EXISTS. The macOS bundle carried "CFBundleShortVersionString":
"1.0.0", typed in by hand when the spec was written and never touched again.
Finder's Get Info reads exactly that field, so every release from 1.0.1
onwards told anybody who asked that they had version 1.0.0 — while the
window's title bar, the --version flag and the update check all said
something else. Nothing in the tests looked at the spec, because the spec is
only ever executed by PyInstaller on a release runner.

Nobody noticed for twenty-odd releases. The question that found it came from
outside: "is the app version also shown in macos finder when asking for
infos? and other operating systems?"

So these are the guards. They are deliberately about the SHAPE of the spec
rather than about a number: a test asserting "the spec says 2.39.0" would
have to be edited on every release, which is the same hand-editing that
caused the fault.
"""
from __future__ import annotations

import pathlib
import re

import pytest

import version

SPEC = pathlib.Path(__file__).resolve().parent.parent / "GamutViewer.spec"


def test_the_spec_reads_the_version_rather_than_repeating_it():
    """No version number is typed into the spec at all."""
    text = SPEC.read_text(encoding="utf-8")
    # A version literal anywhere in the spec is the fault coming back. The
    # macOS minimum system version is a different kind of number and is
    # allowed; it is a floor, not a release.
    allowed = {"11.0"}
    # COMMENTS MAY SAY THE OLD NUMBER, and this test's first run insisted
    # they could not: the comment explaining that "1.0.0" used to be typed in
    # here failed the check that stops it being typed in here. The history is
    # the reason the guard exists, so it stays and the guard reads code only.
    code = "\n".join(line.split("#")[0] for line in text.splitlines())
    literals = {m for m in re.findall(r'"(\d+\.\d+(?:\.\d+)?)"', code)}
    assert not (literals - allowed), (
        f"a version number is typed into GamutViewer.spec: "
        f"{sorted(literals - allowed)} — read it from version.py instead")
    assert "version.py" in text
    assert '"CFBundleShortVersionString": VERSION' in text


def test_finder_gets_the_name_the_author_and_the_copyright():
    """The three Get Info lines are all filled in, from one place."""
    text = SPEC.read_text(encoding="utf-8")
    for key in ("CFBundleShortVersionString", "CFBundleVersion",
                "CFBundleDisplayName", "NSHumanReadableCopyright"):
        assert key in text, f"{key} is not in the macOS bundle"
    # The author's name is not written into the spec either.
    assert 'CREDIT = _v["AUTHOR"]' in text
    assert version.AUTHOR == "Sebastian Reiprich"


def test_windows_gets_a_version_resource():
    """The .exe's Details tab is filled in, which it never used to be."""
    text = SPEC.read_text(encoding="utf-8")
    assert "VSVersionInfo" in text
    assert "version=_win_version_file" in text
    for field in ("FileVersion", "ProductVersion", "ProductName",
                  "FileDescription", "LegalCopyright", "CompanyName"):
        assert f"'{field}'" in text, f"{field} is missing from the .exe"


@pytest.mark.parametrize("given, want", [
    ("2.39.0", (2, 39, 0, 0)),
    ("1.0.0", (1, 0, 0, 0)),
    ("2.39.0-beta.1", (2, 39, 0, 0)),      # a pre-release keeps the numbers
    ("2.40", (2, 40, 0, 0)),               # two parts is still four numbers
    ("10.11.12", (10, 11, 12, 0)),
])
def test_windows_version_tuple(given, want):
    """Four whole numbers, whatever the version string looks like."""
    assert version.windows_version_tuple(given) == want


def test_the_windows_tuple_starts_from_our_own_version():
    """The default argument is the real version, not a placeholder."""
    assert (version.windows_version_tuple()
            == version.windows_version_tuple(version.__version__))
    assert version.windows_version_tuple()[0] == int(
        version.__version__.split(".")[0])
