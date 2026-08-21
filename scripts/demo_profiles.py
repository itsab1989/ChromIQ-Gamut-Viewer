"""The four demo profiles the audits drive the window with, wherever they are.

WHY THIS EXISTS. Nineteen audits began with the same two lines:

    profiles = sorted(pathlib.Path(tempfile.gettempdir())
                      .glob("showme-*/printer-*.icc"))

and those four files were made on 18 August 2026 by something outside this
checkout -- not a script here, not a test, and nothing ever deleted from the
history either. Nineteen checks stood on a folder the operating system empties
on its own schedule and on every reboot. Measured by pointing TMPDIR at an
empty folder: the audits that guard refuse plainly, and the ones that do not
die on `profiles[0]` with IndexError. Nothing reported a false Clean -- but the
day those files went, nineteen audits would simply stop answering, with no way
to make them again.

They live in the repository now, under demo/one-printer-over-time/, so there is
a copy that cannot be swept. Asked for in as many words: "any files needed for
tests can be uploaded to github as well".

THE TEMP FOLDER IS STILL LOOKED AT FIRST, and on purpose: anybody with a
freshly made set there is testing what they just built, and this must not
quietly answer with the older copy from the checkout instead.

WHAT THEY ARE. One printer, four years -- 2019, 2021, 2023 and 2024 -- which is
what "follow one device through time" is for. Read before they were committed:
each says `Glossy paper (demo profile)`, its copyright is a placeholder, and
the measurement data inside carries DESCRIPTOR "Demo measurement" and CREATED
"Demo". No customer, no employer, no person.
"""
from __future__ import annotations

import pathlib
import tempfile

#: Where the copy that cannot be swept lives.
KEPT = (pathlib.Path(__file__).resolve().parent.parent / "demo"
        / "one-printer-over-time")


def the_run_of_profiles() -> list:
    """Four ICC profiles of one printer, oldest first.

    The temp folder first, the checkout second. An empty list means neither
    had them, and every caller already says so in its own words rather than
    reporting a clean-looking nothing.
    """
    made = sorted(pathlib.Path(tempfile.gettempdir())
                  .glob("showme-*/printer-*.icc"))
    return made or sorted(KEPT.glob("printer-*.icc"))
