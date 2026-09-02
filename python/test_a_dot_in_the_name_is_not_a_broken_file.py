"""A measurement whose name has a dot in it opens like any other.

⚠ EVERY .cxf, .mxf AND .txt WITH A DOT IN ITS NAME WAS REFUSED, and the
reason given named the wrong thing entirely.

`convert_to_ti3` hands ArgyllCMS a BASENAME and the tool writes
`<basename>.ti3` -- that is what `cxf2ti3`'s and `txt2ti3`'s own usage says.
The code then looked for the result with `Path.with_suffix(".ti3")`, which
REPLACES whatever follows the last dot rather than appending:

    Glossy-paper.v2          tool wrote  Glossy-paper.v2.ti3
                             code sought Glossy-paper.ti3
    chart 2026-08-29.10.30   tool wrote  chart 2026-08-29.10.30.ti3
                             code sought chart 2026-08-29.10.ti3

The conversion had succeeded and the finished file was in the folder. The
reader was told "could not be converted", with the reason quoted from the
last line the tool printed -- on a clean run its progress chatter, or
"exit code 0". Version suffixes and dated exports are ordinary names for a
measurement.

These tests never call ArgyllCMS. The stand-in does exactly what the real
tools' usage documents: read argv[-1] as a basename and write basename.ti3.
Everything else on the route -- the temporary folder, the subprocess call,
the existence check, the message, the cleanup -- is the real code.
"""
import pathlib
import shutil
import sys
import textwrap

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_TI3 = textwrap.dedent("""\
    CGATS.17

    KEYWORD "DEVICE_CLASS"
    DEVICE_CLASS "OUTPUT"
    COLOR_REP "RGB_XYZ"

    NUMBER_OF_FIELDS 7
    BEGIN_DATA_FORMAT
    SAMPLE_ID RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z
    END_DATA_FORMAT

    NUMBER_OF_SETS 2
    BEGIN_DATA
    1 100 100 100 95.05 100.00 108.90
    2 0 0 0 0.20 0.21 0.23
    END_DATA
    """)


@pytest.fixture
def a_tool_that_behaves_like_argyll(tmp_path, monkeypatch):
    """A stand-in `cxf2ti3`: last argument is a basename, write basename.ti3.

    ⚠ WRITTEN FROM THE TOOL'S OWN USAGE, not from what the caller hopes:

        usage: cxf2ti3 [-v level] infile.cxf outbase
         outbase       Basename of output file

    A stand-in that wrote whatever the caller went on to look for would have
    agreed with the bug and passed over it.
    """
    import ti3gamut

    fake = tmp_path / "cxf2ti3"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, pathlib\n"
        "base = pathlib.Path(sys.argv[-1])\n"
        "pathlib.Path(str(base) + '.ti3').write_text('''" + _TI3 + "''')\n")
    fake.chmod(0o755)
    monkeypatch.setattr(ti3gamut, "_find_tool", lambda _name: str(fake))
    return fake


def _source(tmp_path, name):
    src = tmp_path / name
    src.write_text("<CxF/>\n")
    return src


@pytest.mark.parametrize("name", [
    "Glossy-paper.cxf",                    # the plain case, and the control
    "Glossy-paper.v2.cxf",                 # a version suffix
    "chart 2026-08-29.10.30.cxf",          # an instrument's dated export
    "a.b.c.d.cxf",                         # several, for good measure
])
def test_a_dotted_name_converts(a_tool_that_behaves_like_argyll, tmp_path, name):
    import ti3gamut
    produced = ti3gamut.convert_to_ti3(_source(tmp_path, name))
    assert produced.is_file(), f"{name} was reported unconvertible"
    assert produced.read_text().startswith("CGATS.17")
    shutil.rmtree(produced.parent, ignore_errors=True)


def test_the_plain_name_is_the_control(a_tool_that_behaves_like_argyll,
                                       tmp_path):
    """⚠ THE ONLY DIFFERENCE BETWEEN PASSING AND FAILING WAS ONE DOT.

    Stated as its own test so that a change which broke conversion outright
    could not be mistaken for this fix working.
    """
    import ti3gamut
    plain = ti3gamut.convert_to_ti3(_source(tmp_path, "Glossy-paper.cxf"))
    dotted = ti3gamut.convert_to_ti3(_source(tmp_path, "Glossy-paper.v2.cxf"))
    assert plain.name == "Glossy-paper.ti3"
    assert dotted.name == "Glossy-paper.v2.ti3", (
        "the converted file has lost the part of the name after the dot")
    for p in (plain, dotted):
        shutil.rmtree(p.parent, ignore_errors=True)


def test_reading_one_leaves_no_folder_behind(a_tool_that_behaves_like_argyll,
                                             tmp_path, monkeypatch):
    """⚠ THE SECOND UNMANAGED TEMPORARY FOLDER IN THIS APPLICATION.

    `convert_to_ti3` makes a `mkdtemp` per conversion and nothing removed it,
    so every converted measurement ever opened left a folder holding a
    megabyte-odd .ti3 behind for good. The first such leak was the scenes,
    found as 644 folders holding 27 GB after two days -- see test_temp_files.
    The sweeper that cleans those only knows about `gamutview-*`, so these
    were never in reach of it.
    """
    import tempfile
    import ti3gamut

    home = tmp_path / "tmp"
    home.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(home))

    before = sorted(p.name for p in home.glob("gamut-convert-*"))
    measured = ti3gamut.read_measurement(_source(tmp_path, "Glossy-paper.v2.cxf"))
    after = sorted(p.name for p in home.glob("gamut-convert-*"))

    assert measured.name == "Glossy-paper.v2", measured.name
    assert after == before, (
        f"reading one measurement left {len(after) - len(before)} temporary "
        f"folder(s) behind: {[n for n in after if n not in before]}")


@pytest.fixture
def a_tool_that_fails(tmp_path, monkeypatch):
    """A stand-in that exits 1 and writes nothing, as a real tool does on a
    file it cannot parse."""
    import ti3gamut
    fake = tmp_path / "cxf2ti3-broken"
    fake.write_text("#!/usr/bin/env python3\n"
                    "import sys\n"
                    "sys.stderr.write('Error - could not read the file\\n')\n"
                    "sys.exit(1)\n")
    fake.chmod(0o755)
    monkeypatch.setattr(ti3gamut, "_find_tool", lambda _name: str(fake))
    return fake


def test_a_conversion_that_fails_leaves_no_folder_behind(
        a_tool_that_fails, tmp_path, monkeypatch):
    """⚠ THE LEAK WAS CLOSED ON THE SUCCESS PATH ONLY.

    The cleanup lives in `read_measurement` and wraps the READ, which is
    reached only once `convert_to_ti3` has returned. Its own two `raise`
    paths — the timeout, and "could not be converted" — walked out past the
    folder they had just made. Driven through the window:

        the tool exits 1, writes nothing    -> 1 folder leaked, per attempt
        the .ti3 is written but unreadable  -> 0

    Same gesture, same warning dialog, same file; the only difference is
    which side of the `return` the failure fell on. And the message a reader
    gets is one whose natural answer is to try again.
    """
    import tempfile
    import ti3gamut

    home = tmp_path / "tmp"
    home.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(home))

    src = tmp_path / "chart 2026-08-29.10.30.cxf"
    src.write_text("<CxF/>\n")

    before = sorted(p.name for p in home.glob("gamut-convert-*"))
    with pytest.raises(ValueError) as caught:
        ti3gamut.convert_to_ti3(src)
    after = sorted(p.name for p in home.glob("gamut-convert-*"))

    assert "could not be converted" in str(caught.value)
    assert after == before, (
        f"a failed conversion left {len(after) - len(before)} folder(s) "
        f"behind: {[n for n in after if n not in before]} — and a reader who "
        "retries makes one each time")


def test_a_conversion_that_works_keeps_its_folder_until_it_is_read(
        a_tool_that_behaves_like_argyll, tmp_path):
    """The control for the above, and the thing that must NOT change: the
    file has to survive long enough for the caller to read it."""
    import ti3gamut
    src = tmp_path / "Glossy-paper.v2.cxf"
    src.write_text("<CxF/>\n")
    produced = ti3gamut.convert_to_ti3(src)
    assert produced.is_file(), (
        "the folder was swept away with the converted file still in it")
    assert produced.read_text().startswith("CGATS.17")
    shutil.rmtree(produced.parent, ignore_errors=True)
