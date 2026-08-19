"""Every check in `scripts/` is named in the README, and every one it names exists.

WHY THIS EXISTS. The checks in `scripts/` are the half of the testing that a
unit test cannot do -- they drive the real window, or a real browser, and each
one exists because a fault got past everything else. They are only useful to
somebody who knows they are there, and the only place that says so is the
README.

Measured on the day this was written: the README listed 19 of the 27, and the
eight it did not name included the three most recently added -- the page at any
size, the light/dark switch, and the computer with no ArgyllCMS and no ffmpeg.
Each had been written that same week, run, found a real fault, and then gone
undocumented. Nobody was careless; the list is simply a place you have to
remember to go, and the check itself works whether or not you go there.

BOTH DIRECTIONS, because they fail differently. A check missing from the
README is invisible and never gets run. A README naming a script that no
longer exists is worse than silence -- somebody types the line, gets "no such
file", and has no way to tell whether the check was deleted on purpose or the
name is a typo.

WHAT THIS DELIBERATELY DOES NOT CHECK. Not that the one-line description is
accurate; a test cannot read English. Not `drive_*.py`, `make_*.py` or
`mutation_test_*.py`, which are tools and demonstrations rather than checks --
`audit_*` and `check_*` are the two prefixes that mean "this answers a
question about the built application", and they are the ones somebody needs
the list to discover.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"
_README = _ROOT / "README.md"


def _the_checks():
    """Every standalone check, by file name."""
    return sorted(
        p.name
        for p in _SCRIPTS.glob("*.py")
        if p.name.startswith(("audit_", "check_"))
    )


def test_every_check_is_named_in_the_readme():
    text = _README.read_text(encoding="utf-8")
    missing = [name for name in _the_checks() if name not in text]
    assert not missing, (
        "These checks exist and the README does not mention them, so nobody "
        "reading it knows to run them:\n  "
        + "\n  ".join(missing)
        + "\n\nAdd a line for each to the list of scripts in README.md, saying "
        "in one phrase what question it answers."
    )


def test_the_readme_names_no_script_that_is_gone():
    import re

    text = _README.read_text(encoding="utf-8")
    named = sorted(set(re.findall(r"scripts/[A-Za-z0-9_]+\.py", text)))
    ghosts = [ref for ref in named if not (_ROOT / ref).exists()]
    assert not ghosts, (
        "The README tells the reader to run these, and they are not in the "
        "tree:\n  "
        + "\n  ".join(ghosts)
        + "\n\nEither the script was renamed or removed and the README was not "
        "updated, or the path is a typo. Both leave somebody at a 'no such "
        "file' with no way to tell which."
    )


def test_there_are_checks_to_find():
    # Guards the two tests above against passing because the glob found
    # nothing -- an empty list satisfies "none are missing" perfectly.
    found = _the_checks()
    assert len(found) >= 20, (
        f"Only {len(found)} check(s) found in {_SCRIPTS}. The tests above pass "
        "trivially on an empty list, so this says the folder is being read at "
        "all."
    )
