"""Two profiles of one imaginary scanner, five years apart.

    python scripts/make_demo_profiles.py

WHY THESE ARE MADE RATHER THAN MEASURED, and why that is honest here.

The profile comparison answers "have these two moved apart", and showing it
needs two profiles of ONE device made at different times. Nobody has a pair
like that lying in a repository, and the two that ship with an operating
system -- sRGB and Adobe RGB -- are two different SPACES rather than one
device twice, which is a different question wearing the same clothes.

So this writes a pair, and every page built from them says in its own title
that they are an illustration. What is illustrated is real: the SHAPE of the
disagreement is what a scanner drifting does, and the arithmetic that measures
it is the same arithmetic run on real files.

WHAT MAKES THEM DIFFER, chosen to be the case a gamut comparison cannot see:

* the tone curve moves, 2.20 to 2.32, which is a lamp ageing -- the single
  most ordinary thing that happens to a scanner over years;
* the blue primary drifts a little, which is what a filter set does.

Neither changes the enclosed volume by much. Measured on the pair this
writes, they come out well under a per cent apart in volume while colours
inside them disagree by several dE -- so the gamut view says "nothing to see"
and the comparison says exactly where the trouble is. That contrast is the
whole reason the feature exists, and it is the reason the demo is built this
way rather than by simply making one profile obviously worse.

The files are small, valid, matrix/TRC RGB profiles written by hand, so they
need nothing installed and are identical on every machine.
"""
from __future__ import annotations

import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
DEMO = HERE.parent / "demo"


def _s15(value: float) -> bytes:
    """s15Fixed16Number, the specification's own fixed-point number."""
    return struct.pack(">i", int(round(value * 65536.0)))


def _xyz_body(x: float, y: float, z: float) -> bytes:
    return b"XYZ " + b"\0" * 4 + _s15(x) + _s15(y) + _s15(z)


def _gamma_curve(gamma: float) -> bytes:
    """A `curv` tag holding one number, which the specification reads as a
    pure gamma -- the compact form, and the one a real display profile uses."""
    return (b"curv" + b"\0" * 4 + struct.pack(">I", 1)
            + struct.pack(">H", int(round(gamma * 256.0))))


def _tag(sig: bytes, body: bytes):
    return sig, body


def write_profile(path: pathlib.Path, *, gamma: float, blue) -> pathlib.Path:
    """One valid RGB matrix/TRC profile, sRGB's primaries but for *blue*."""
    tags = [
        _tag(b"rXYZ", _xyz_body(0.4360, 0.2225, 0.0139)),
        _tag(b"gXYZ", _xyz_body(0.3851, 0.7169, 0.0971)),
        _tag(b"bXYZ", _xyz_body(*blue)),
        _tag(b"rTRC", _gamma_curve(gamma)),
        _tag(b"gTRC", _gamma_curve(gamma)),
        _tag(b"bTRC", _gamma_curve(gamma)),
        _tag(b"wtpt", _xyz_body(0.9642, 1.0, 0.8249)),
    ]
    table = struct.pack(">I", len(tags))
    at = 132 + 12 * len(tags)
    entries, blob = b"", b""
    for sig, body in tags:
        entries += struct.pack(">4sII", sig, at + len(blob), len(body))
        blob += body + b"\0" * (-len(body) % 4)
    header = bytearray(128)
    header[12:16] = b"scnr"          # an INPUT profile: this is a scanner
    header[16:20] = b"RGB "
    header[20:24] = b"XYZ "
    header[36:40] = b"acsp"
    header[8] = 2                    # version 2, as most scanner profiles are
    header[9] = 0x40
    raw = bytes(header) + table + entries + blob
    raw = struct.pack(">I", len(raw)) + raw[4:]
    path.write_bytes(raw)
    return path


def main() -> int:
    DEMO.mkdir(parents=True, exist_ok=True)
    before = write_profile(DEMO / "scanner-2019.icc", gamma=2.20,
                           blue=(0.1431, 0.0606, 0.7139))
    # The lamp has aged and the blue filter has shifted. Small numbers on
    # purpose: a drift big enough to see in the SHAPE would not demonstrate
    # anything, because the gamut view already shows that.
    after = write_profile(DEMO / "scanner-2024.icc", gamma=2.32,
                          blue=(0.1465, 0.0631, 0.6980))

    sys.path.insert(0, str(HERE.parent / "python"))
    import icc_read
    import ti3gamut

    volumes = [icc_read.profile_gamut(p).volume for p in (before, after)]
    apart = abs(volumes[0] - volumes[1]) / volumes[0]
    drift = ti3gamut.compare_profiles(before, after)

    print(f"  {before.name}  and  {after.name}\n")
    print(f"  by volume they are   {100 * apart:.2f}% apart"
          f"   ({volumes[0]:,.0f} against {volumes[1]:,.0f})")
    print(f"  inside they are      up to dE {drift.worst:.2f}, "
          f"averaging {drift.average:.2f}")
    print(f"  colours a careful eye would notice: {drift.over_one} of "
          f"{drift.matched}\n")
    if apart > 0.03:
        print("  These differ too much in SIZE to make the point: a gamut "
              "comparison would already show it.")
        return 1
    if drift.worst < 1.5:
        print("  These differ too little INSIDE to make the point: there "
              "would be nothing for the comparison to find.")
        return 1
    print("  The shape says almost nothing and the inside says plenty, "
          "which is what these are for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
