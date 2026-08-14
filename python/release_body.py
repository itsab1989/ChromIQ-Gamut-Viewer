"""Compose what a release page says, from the changelog and the tag.

WHY
---
The release page is where somebody lands when they follow "a new version is
out". The first question they have is *what changed*, and a page that opens
with a description of the application does not answer it -- the same words
appeared on every release, so the one thing that differed between them was the
one thing not written down. The changelog already had the answer; it simply
never reached the page.

So: the version's own notes first, then the evergreen part -- which file to
download, how to open it -- and a link to the full history for anybody who
wants to see further back.

WHAT IT REFUSES TO DO
---------------------
Publish a release with nothing to say. If the changelog has no section for the
tag being built, this stops the build rather than putting out a page that
repeats the last one. A release whose notes are silently wrong is worse than a
build that failed loudly, because nobody finds out for months.

It also refuses a tag that does not match the version inside the application.
The in-app update check compares its own version against the newest tag, so a
bundle tagged v1.6.0 that reports 1.5.0 would offer somebody an update they
already have, for ever.

USE
---
    python python/release_body.py v1.5.0 --out body.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

CHANGELOG = ROOT / "CHANGELOG.md"
EVERGREEN = ROOT / ".github" / "release-notes.md"
REPO = "itsab1989/ChromIQ-Gamut-Viewer"


class NotReleasable(Exception):
    """Something is missing that a release must not go out without."""


def normalise(tag: str) -> str:
    """``v1.5.0``, ``1.5.0`` and ``refs/tags/v1.5.0`` all mean the same."""
    tag = tag.strip().rsplit("/", 1)[-1]
    return tag[1:] if tag.startswith("v") else tag


def section_for(tag: str, changelog: str) -> str:
    """The changelog entry for one version, without its heading.

    The heading goes because the release page already carries the version in
    its own title, and repeating it reads as a mistake.
    """
    wanted = normalise(tag)
    # Headings look like "## v1.5.0". Take everything up to the next one.
    pattern = re.compile(r"^##\s+v?" + re.escape(wanted) + r"\s*$", re.M)
    found = pattern.search(changelog)
    if not found:
        have = re.findall(r"^##\s+(v?\d[^\s]*)\s*$", changelog, re.M)
        raise NotReleasable(
            f"CHANGELOG.md has nothing for {tag}. It has: "
            f"{', '.join(have) if have else 'no version headings at all'}.\n"
            "Add a section for this version before tagging it -- a release "
            "with no notes is the thing this check exists to prevent.")
    rest = changelog[found.end():]
    end = re.search(r"^##\s+\S", rest, re.M)
    body = (rest[:end.start()] if end else rest).strip()
    if not body:
        raise NotReleasable(
            f"CHANGELOG.md has a heading for {tag} but nothing written under "
            "it. Say what changed, or do not tag it yet.")
    return body


def previous_tag(tag: str, changelog: str) -> "str | None":
    """The version released before this one, for a "what changed" link."""
    versions = re.findall(r"^##\s+(v?\d\S*)\s*$", changelog, re.M)
    plain = [normalise(v) for v in versions]
    wanted = normalise(tag)
    if wanted not in plain:
        return None
    at = plain.index(wanted)
    return f"v{plain[at + 1]}" if at + 1 < len(plain) else None


def check_version_matches(tag: str) -> None:
    """The tag and the version inside the application must agree."""
    text = (HERE / "version.py").read_text(encoding="utf-8")
    found = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not found:
        raise NotReleasable("python/version.py has no __version__ to check")
    if found.group(1) != normalise(tag):
        raise NotReleasable(
            f"the tag says {normalise(tag)} and python/version.py says "
            f"{found.group(1)}.\n\nThese have to agree: the update check "
            "compares the version the application reports against the newest "
            "tag, so a mismatch offers people an update they already have.")


def compose(tag: str, *, changelog: "str | None" = None,
            evergreen: "str | None" = None) -> str:
    """The whole page: what changed, then everything that is always true."""
    changelog = (CHANGELOG.read_text(encoding="utf-8")
                 if changelog is None else changelog)
    evergreen = (EVERGREEN.read_text(encoding="utf-8")
                 if evergreen is None else evergreen)

    parts = [f"## What changed in {tag}", "", section_for(tag, changelog), ""]

    was = previous_tag(tag, changelog)
    if was:
        parts += [f"[Every commit since {was}]"
                  f"(https://github.com/{REPO}/compare/{was}...{tag}) · "
                  f"[the full history]"
                  f"(https://github.com/{REPO}/blob/{tag}/CHANGELOG.md)", ""]
    else:
        parts += [f"[The full history]"
                  f"(https://github.com/{REPO}/blob/{tag}/CHANGELOG.md)", ""]

    parts += ["---", "", "## About the ChromIQ Gamut Viewer", "",
              evergreen.strip(), ""]
    return "\n".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tag", help="the tag being released, e.g. v1.5.0")
    ap.add_argument("--out", help="write here instead of standard output")
    ap.add_argument("--skip-version-check", action="store_true",
                    help="for filling in a release that is already out")
    args = ap.parse_args(argv)
    try:
        if not args.skip_version_check:
            check_version_matches(args.tag)
        body = compose(args.tag)
    except NotReleasable as why:
        print(f"error: {why}", file=sys.stderr)
        return 1
    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        print(f"wrote {len(body)} characters to {args.out}")
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
