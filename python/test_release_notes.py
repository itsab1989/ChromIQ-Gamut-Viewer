"""What a release page says.

The failure this guards against is quiet: a release goes out carrying the
previous one's words, and nobody notices for months because the page looks
perfectly normal.
"""
import pytest

import release_body as rb


CHANGELOG = """# Changelog

## v2.0.0

### ✨ What's new

- The big one.

## v1.1.0

### 🐞 Fixed

- A small one.

## v1.0.0

- The first one.
"""


def test_the_notes_are_the_ones_for_that_version():
    assert "The big one." in rb.section_for("v2.0.0", CHANGELOG)
    assert "A small one." not in rb.section_for("v2.0.0", CHANGELOG)
    assert "A small one." in rb.section_for("v1.1.0", CHANGELOG)


def test_the_oldest_version_reads_to_the_end_of_the_file():
    """The last section has no heading after it to stop at."""
    got = rb.section_for("v1.0.0", CHANGELOG)
    assert got.strip() == "- The first one."


def test_the_heading_is_not_repeated():
    """The release page already carries the version in its own title."""
    assert "## v2.0.0" not in rb.section_for("v2.0.0", CHANGELOG)


@pytest.mark.parametrize("written", ["v2.0.0", "2.0.0", "refs/tags/v2.0.0"])
def test_the_tag_may_be_written_any_of_the_usual_ways(written):
    assert "The big one." in rb.section_for(written, CHANGELOG)


def test_a_version_with_no_section_stops_the_release():
    """THE point of this. A release with nothing to say must fail loudly
    rather than quietly repeat the last one's words."""
    with pytest.raises(rb.NotReleasable) as why:
        rb.section_for("v9.9.9", CHANGELOG)
    assert "v2.0.0" in str(why.value)          # says what it does have


def test_a_heading_with_nothing_under_it_stops_the_release():
    with pytest.raises(rb.NotReleasable):
        rb.section_for("v3.0.0", CHANGELOG + "\n## v3.0.0\n\n")


def test_a_changelog_with_no_versions_at_all_says_so():
    with pytest.raises(rb.NotReleasable) as why:
        rb.section_for("v1.0.0", "# Changelog\n\nnothing here yet\n")
    assert "no version headings" in str(why.value)


def test_the_previous_version_is_the_one_below_it():
    assert rb.previous_tag("v2.0.0", CHANGELOG) == "v1.1.0"
    assert rb.previous_tag("v1.1.0", CHANGELOG) == "v1.0.0"
    assert rb.previous_tag("v1.0.0", CHANGELOG) is None      # nothing before it


def test_the_page_leads_with_what_changed():
    """Somebody landing here asks what changed. That has to be the first
    thing on the page, not the third."""
    page = rb.compose("v2.0.0", changelog=CHANGELOG, evergreen="Evergreen text.")
    assert page.startswith("## What changed in v2.0.0")
    assert page.index("The big one.") < page.index("Evergreen text.")
    assert "compare/v1.1.0...v2.0.0" in page
    assert "Evergreen text." in page             # and the rest is still there


def test_the_first_ever_release_has_no_comparison_link():
    page = rb.compose("v1.0.0", changelog=CHANGELOG, evergreen="x")
    assert "compare/" not in page
    assert "the full history" in page.lower()


def test_the_real_changelog_covers_every_tag_that_exists():
    """Every released version must have notes, including the ones released
    before this check existed."""
    import subprocess
    try:
        done = subprocess.run(["git", "tag"], cwd=rb.ROOT, capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git is not available here")
    tags = [t for t in done.stdout.split() if t.startswith("v")]
    if not tags:
        pytest.skip("this checkout has no tags")
    text = rb.CHANGELOG.read_text(encoding="utf-8")
    missing = []
    for tag in tags:
        try:
            rb.section_for(tag, text)
        except rb.NotReleasable:
            missing.append(tag)
    assert not missing, f"released with no notes: {', '.join(missing)}"


def test_the_tag_and_the_application_version_must_agree():
    """A bundle tagged one thing and reporting another would offer people an
    update they already have, for ever."""
    import re
    version = re.search(r'__version__\s*=\s*"([^"]+)"',
                        (rb.HERE / "version.py").read_text(encoding="utf-8"))
    rb.check_version_matches(f"v{version.group(1)}")         # the true one
    with pytest.raises(rb.NotReleasable) as why:
        rb.check_version_matches("v99.0.0")
    assert "have to agree" in str(why.value)


# --- the rule itself, wired into the build ----------------------------------

def _yaml():
    """PyYAML is not something the application needs, only these two checks.
    It is installed for the test run in CI; without it they step aside rather
    than fail, because a missing test tool is not a broken workflow."""
    return pytest.importorskip("yaml")


def _workflow():
    return (rb.ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8")


def test_the_changelog_is_checked_before_anything_is_built():
    """Every release says what changed, and finding out otherwise must not
    cost a full build. The check runs first and the build waits on it."""
    jobs = _yaml().safe_load(_workflow())["jobs"]
    assert "notes" in jobs, "the pre-flight changelog check is gone"
    assert "notes" in jobs["build"].get("needs", []), \
        "the build no longer waits for the changelog check"
    # A manual run has no tag to check, so the skip must not stop the build.
    assert "skipped" in jobs["build"]["if"]


def test_the_release_page_is_built_from_the_changelog_not_a_fixed_file():
    """The whole point: a body_path pointing at a static file is how every
    release came to carry the same words."""
    steps = _yaml().safe_load(_workflow())["jobs"]["release"]["steps"]
    bodies = [s["with"]["body_path"] for s in steps
              if isinstance(s.get("with"), dict) and "body_path" in s["with"]]
    assert bodies, "nothing sets the release body"
    for body in bodies:
        assert body != ".github/release-notes.md", \
            "the release body is a fixed file again"
    assert any("release_body.py" in str(s.get("run", "")) for s in steps), \
        "the notes are no longer composed for this version"
