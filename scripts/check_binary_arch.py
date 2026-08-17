"""Read what a built binary REALLY is, and refuse it if it is not what we said.

    python scripts/check_binary_arch.py dist/GamutViewer/GamutViewer.exe arm64

WHY THIS EXISTS. A build machine can produce a binary for the wrong
architecture and say nothing about it: on an ARM machine with an emulation
layer, an x86_64 toolchain runs perfectly happily and emits an x86_64
executable. The job goes green, the artefact is uploaded under a name saying
"arm64", and the only way anybody finds out is that it is slow on the very
machines it was built for -- or refuses to start on one with no emulation.

Nothing else in the build can catch that. The tests pass (they run under
emulation too), the packaging succeeds, the upload succeeds. The one honest
check is to open the file and read the machine field the linker wrote.

THREE FORMATS, because this project ships all three:

  PE (Windows)   'MZ', then a pointer at 0x3C to 'PE\\0\\0', then Machine.
  ELF (Linux)    0x7f 'ELF', then e_machine at offset 18.
  Mach-O (macOS) the magic, then cputype -- and a universal binary is a fat
                 archive holding several, so every one of them is read.

Exit code is 1 when the file is not the architecture that was asked for, and
the message says what it actually found rather than only that it is wrong.
"""
from __future__ import annotations

import pathlib
import struct
import sys

#: PE Machine values, from the Microsoft PE format documentation.
PE_MACHINES = {0x014C: "x86", 0x8664: "x86_64", 0xAA64: "arm64",
               0x01C4: "armv7", 0x0200: "ia64"}

#: ELF e_machine values, from the System V ABI.
ELF_MACHINES = {0x03: "x86", 0x3E: "x86_64", 0xB7: "arm64", 0x28: "armv7",
                0x02: "sparc", 0x14: "ppc", 0x15: "ppc64"}

#: Mach-O cpu types, from <mach/machine.h>. The high bit means 64-bit.
MACHO_CPUS = {7: "x86", 7 | 0x01000000: "x86_64",
              12: "armv7", 12 | 0x01000000: "arm64"}

#: What the world calls each one, so "amd64" and "x64" are not two answers.
SAME = {"x64": "x86_64", "amd64": "x86_64", "x86_64": "x86_64",
        "arm64": "arm64", "aarch64": "arm64", "armv8": "arm64",
        "x86": "x86", "i386": "x86", "universal2": "universal2"}


def architectures(path: pathlib.Path) -> list:
    """Every architecture inside *path*, as this project names them."""
    raw = path.read_bytes()[:4096]
    if raw[:2] == b"MZ":                                  # Windows
        at = struct.unpack_from("<I", raw, 0x3C)[0]
        if raw[at:at + 4] != b"PE\0\0":
            raise ValueError("an MZ file whose PE header is not where it says")
        machine = struct.unpack_from("<H", raw, at + 4)[0]
        return [PE_MACHINES.get(machine, f"unknown PE 0x{machine:04x}")]
    if raw[:4] == b"\x7fELF":                             # Linux
        little = raw[5] == 1
        machine = struct.unpack_from("<H" if little else ">H", raw, 18)[0]
        return [ELF_MACHINES.get(machine, f"unknown ELF 0x{machine:02x}")]
    magic = struct.unpack_from(">I", raw, 0)[0]
    if magic in (0xCAFEBABE, 0xCAFEBABF):                 # a fat macOS binary
        count = struct.unpack_from(">I", raw, 4)[0]
        out = []
        for i in range(count):
            cpu = struct.unpack_from(">I", raw, 8 + i * 20)[0]
            out.append(MACHO_CPUS.get(cpu, f"unknown cpu {cpu}"))
        return out
    if magic in (0xFEEDFACE, 0xFEEDFACF):                 # big-endian thin
        cpu = struct.unpack_from(">I", raw, 4)[0]
        return [MACHO_CPUS.get(cpu, f"unknown cpu {cpu}")]
    if struct.unpack_from("<I", raw, 0)[0] in (0xFEEDFACE, 0xFEEDFACF):
        cpu = struct.unpack_from("<I", raw, 4)[0]
        return [MACHO_CPUS.get(cpu, f"unknown cpu {cpu}")]
    raise ValueError(f"{path.name} is not a PE, an ELF or a Mach-O binary")


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2])
        return 2
    path, wanted = pathlib.Path(argv[1]), argv[2].lower()
    if not path.is_file():
        print(f"no such file: {path}")
        return 1
    wanted = SAME.get(wanted, wanted)
    try:
        found = architectures(path)
    except (ValueError, struct.error) as why:
        print(f"could not read {path.name}: {why}")
        return 1
    print(f"{path.name}: {', '.join(found)}")
    # A universal binary satisfies any of the architectures it carries, which
    # is the whole point of one.
    if wanted in found or (wanted == "universal2" and len(found) > 1):
        return 0
    print(f"\nEXPECTED {wanted}, and this is {', '.join(found)}.\n\n"
          f"On a machine with an emulation layer a toolchain for the other "
          f"architecture runs quite happily and produces a working binary of "
          f"the wrong kind. The build goes green, the artefact is uploaded "
          f"under a name that is not true, and the only symptom is that it is "
          f"slow on exactly the machines it was built for.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
