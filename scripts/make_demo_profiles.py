"""One imaginary printer, profiled four times over five years.

    python scripts/make_demo_profiles.py [--out FOLDER]

NOT COMMITTED. Each one is a 1257 kB copy of a 1257 kB profile that differs
from it in about six thousand bytes, so four of them would put five megabytes
of near-duplicate binary in the repository for a demonstration that takes a
second to regenerate. The page generator writes them into a temporary folder
as it needs them, and `--out` is how.

WHY THESE ARE DERIVED FROM demo/Glossy-paper.icc RATHER THAN WRITTEN FRESH.

The first attempt at this wrote small matrix/TRC profiles by hand. They were
valid -- our own reader opened them in milliseconds and gave a sane gamut --
and ArgyllCMS's `iccgamut` WEDGED on them: still running after four minutes on
a 344-byte file. Measured, twice, and not explained: it is not the profile
class (scnr and mntr both wedge, prtr fails fast), not the missing desc and
cprt tags, and not the single-number gamma (a 256-point sampled curve wedges
too). Shipping files like that would ship a trap, because the main window
reads a profile through iccgamut first.

So this starts from a profile ArgyllCMS demonstrably likes -- the project's own
demo printer profile, which iccgamut reads in 0.15s -- and changes only the
part that a drifting device would change.

WHAT IS CHANGED, and why it is the honest thing to change. The A2B1 tag is a
`mft2` lookup table laid out as 52 bytes of header, three input curves, the
colour cube itself, and then three OUTPUT curves. The output curves are what
turn the cube's answer into the colour finally reported, so bending them is
precisely what an ageing lamp or a shifting ink does: every colour moves a
little, the shape barely changes, and no structure is disturbed. The cube is
left alone, so the file stays exactly as valid as the one it came from.

The point being demonstrated is real even though the drift is invented: a
device can move enough to matter while its gamut hardly changes size, so the
gamut view says "nothing to see" and the comparison says exactly where the
trouble is.

The generator CHECKS both halves of that and fails if either stops being true.
A demo that has quietly stopped demonstrating its own point is worse than none.
"""
from __future__ import annotations

import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
DEMO = HERE.parent / "demo"
SOURCE = DEMO / "Glossy-paper.icc"

#: The run, as (file stem, when it was made, how far the curves have bent).
#: The bend is small on purpose: big enough to see in the numbers, far too
#: small to see in the shape, which is the whole demonstration. The first
#: numbers tried here were fifteen times these -- 5.60% of volume and dE 38.6,
#: which the check below rejected outright. That is what the check is for.
RUN = [
    ("printer-2019", (2019, 3, 12, 10, 30, 0), 0.0000),
    ("printer-2021", (2021, 5, 4, 14, 15, 0), 0.0012),
    ("printer-2023", (2023, 6, 19, 9, 45, 0), 0.0024),
    ("printer-2024", (2024, 9, 2, 16, 20, 0), 0.0035),
]


def find_tag(raw: bytes, want: bytes):
    """Where a tag's data sits in the file, as (offset, length)."""
    count = struct.unpack(">I", raw[128:132])[0]
    for i in range(count):
        at = 132 + i * 12
        sig, offset, length = struct.unpack(">4sII", raw[at:at + 12])
        if sig == want:
            return offset, length
    raise SystemExit(f"{want!r} is not in this profile")


def bend_output_curves(raw: bytearray, offset: int, length: int,
                       amount: float) -> None:
    """Bend the three output curves of an mft2 table by *amount*.

    The layout, from the specification and confirmed against this very file:
    52 bytes of header, then `entries_in` samples for each input channel, then
    the colour cube, then `entries_out` samples for each output channel. The
    three sizes add up to the tag length exactly, which is the check that the
    reading is right rather than merely plausible.
    """
    channels_in = raw[offset + 8]
    channels_out = raw[offset + 9]
    grid = raw[offset + 10]
    entries_in, entries_out = struct.unpack(">HH", raw[offset + 48:offset + 52])

    inputs = channels_in * entries_in * 2
    cube = (grid ** channels_in) * channels_out * 2
    outputs = channels_out * entries_out * 2
    if 52 + inputs + cube + outputs != length:
        raise SystemExit(
            f"this table is not laid out as expected: 52 + {inputs} + {cube} "
            f"+ {outputs} != {length}")

    start = offset + 52 + inputs + cube
    for channel in range(channels_out):
        base = start + channel * entries_out * 2
        for i in range(entries_out):
            at = base + i * 2
            was = struct.unpack(">H", raw[at:at + 2])[0]
            share = i / max(entries_out - 1, 1)
            # A GENTLE S-BEND, strongest in the middle and nothing at the
            # ends. The ends are the paper white and the deepest black, and a
            # device drifting does not move those first -- so a bend that
            # shifted them would be a worse imitation as well as a wider one.
            lift = amount * 65535.0 * share * (1.0 - share) * 4.0
            raw[at:at + 2] = struct.pack(">H", max(0, min(65535,
                                                          int(was + lift))))


def write_one(stem: str, when, amount: float) -> pathlib.Path:
    raw = bytearray(SOURCE.read_bytes())
    if amount:
        for tag in (b"A2B1", b"A2B0"):
            offset, length = find_tag(raw, tag)
            bend_output_curves(raw, offset, length, amount)
    raw[24:36] = struct.pack(">6H", *when)
    out = DEMO / f"{stem}.icc"
    out.write_bytes(bytes(raw))
    return out


def main(out=None) -> int:
    global DEMO
    if out is not None:
        DEMO = pathlib.Path(out)
        DEMO.mkdir(parents=True, exist_ok=True)
    if not SOURCE.exists():
        print(f"missing {SOURCE}")
        return 1

    sys.path.insert(0, str(HERE.parent / "python"))
    import drift_series
    import icc_read

    made = [write_one(stem, when, amount) for stem, when, amount in RUN]
    print(f"  {len(made)} profiles written to {DEMO}\n")

    volumes = [icc_read.profile_gamut(p).volume for p in made]
    spread = (max(volumes) - min(volumes)) / max(volumes)
    run = drift_series.build(made)

    print(f"  by volume they span   {100 * spread:.2f}%"
          f"   ({min(volumes):,.0f} to {max(volumes):,.0f})")
    print(f"  inside, altogether    dE {run.total:.2f}")
    print(f"  ordered by            {run.ordered_by}")
    print(f"  steady                {run.steady}")
    for step in run.since_previous:
        print(f"    {step.before} -> {step.after}: dE {step.worst:.2f}")
    for complaint in run.complaints:
        print(f"  ! {complaint}")
    print()

    if spread > 0.03:
        print("  These differ too much in SIZE to make the point: the gamut "
              "view would already show it.")
        return 1
    if run.total < 1.0:
        print("  These differ too little INSIDE to make the point: there "
              "would be nothing for the comparison to find.")
        return 1
    if run.complaints:
        print("  The run has complaints, so it is not a clean demonstration.")
        return 1
    print("  The shape says almost nothing and the inside says plenty, "
          "which is what these are for.")
    return 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None,
                    help="where to write them (default: the demo folder)")
    raise SystemExit(main(ap.parse_args().out))
