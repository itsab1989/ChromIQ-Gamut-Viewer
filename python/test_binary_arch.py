"""Reading what a built binary really is.

WHY THIS MATTERS ENOUGH TO CHECK. On a machine with an emulation layer, a
toolchain for the other architecture runs quite happily and emits a working
binary of the wrong kind. The tests pass -- they run under emulation too --
the packaging succeeds, the upload succeeds, and the artefact goes out under
a name that is not true. The only symptom is that it is slow on exactly the
machines it was built for.

So the build reads the machine field the linker wrote. These check that the
reader is right, because a guard nobody has tested is a guard nobody can
trust.
"""
import importlib.util
import pathlib
import struct

import pytest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "check_binary_arch.py"


def _reader():
    spec = importlib.util.spec_from_file_location("archcheck", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pe(path, machine):
    """A Windows PE header, which is all the reader looks at."""
    raw = bytearray(b"\0" * 512)
    raw[0:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3C, 0x80)
    raw[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", raw, 0x84, machine)
    path.write_bytes(bytes(raw))
    return path


def _elf(path, machine, little=True):
    raw = bytearray(b"\0" * 128)
    raw[0:4] = b"\x7fELF"
    raw[4] = 2                                   # 64-bit
    raw[5] = 1 if little else 2
    struct.pack_into("<H" if little else ">H", raw, 18, machine)
    path.write_bytes(bytes(raw))
    return path


def _macho_fat(path, cpus):
    raw = bytearray(b"\0" * 4096)
    struct.pack_into(">I", raw, 0, 0xCAFEBABE)
    struct.pack_into(">I", raw, 4, len(cpus))
    for i, cpu in enumerate(cpus):
        struct.pack_into(">I", raw, 8 + i * 20, cpu)
    path.write_bytes(bytes(raw))
    return path


def test_a_windows_arm64_binary_is_read_as_arm64(tmp_path):
    mod = _reader()
    assert mod.architectures(_pe(tmp_path / "a.exe", 0xAA64)) == ["arm64"]


def test_a_windows_x64_binary_is_not_mistaken_for_arm(tmp_path):
    """THE WHOLE POINT. These two differ by two bytes in the header, and by
    everything on the machine somebody runs them on."""
    mod = _reader()
    assert mod.architectures(_pe(tmp_path / "b.exe", 0x8664)) == ["x86_64"]


def test_a_linux_arm64_binary_is_read_as_arm64(tmp_path):
    mod = _reader()
    assert mod.architectures(_elf(tmp_path / "c", 0xB7)) == ["arm64"]
    assert mod.architectures(_elf(tmp_path / "d", 0x3E)) == ["x86_64"]


def test_a_universal_macos_binary_reports_every_architecture_in_it(tmp_path):
    mod = _reader()
    both = _macho_fat(tmp_path / "e", [7 | 0x01000000, 12 | 0x01000000])
    assert mod.architectures(both) == ["x86_64", "arm64"]


def test_the_check_passes_only_for_what_was_asked_for(tmp_path):
    mod = _reader()
    arm = _pe(tmp_path / "f.exe", 0xAA64)
    assert mod.main(["x", str(arm), "arm64"]) == 0
    assert mod.main(["x", str(arm), "x64"]) == 1
    assert mod.main(["x", str(arm), "x86_64"]) == 1


def test_the_names_the_world_uses_all_mean_the_same_thing(tmp_path):
    """A build machine says x64, a wheel says amd64, a compiler says x86_64.
    Three spellings of one architecture must not read as three answers."""
    mod = _reader()
    intel = _pe(tmp_path / "g.exe", 0x8664)
    for spelling in ("x64", "amd64", "x86_64"):
        assert mod.main(["x", str(intel), spelling]) == 0, spelling
    arm = _pe(tmp_path / "h.exe", 0xAA64)
    for spelling in ("arm64", "aarch64"):
        assert mod.main(["x", str(arm), spelling]) == 0, spelling


def test_a_file_that_is_not_a_binary_is_refused_rather_than_guessed(tmp_path):
    mod = _reader()
    junk = tmp_path / "notes.txt"
    junk.write_text("this is not an executable at all")
    with pytest.raises(ValueError):
        mod.architectures(junk)
    assert mod.main(["x", str(junk), "arm64"]) == 1


def test_a_missing_file_says_so(tmp_path):
    mod = _reader()
    assert mod.main(["x", str(tmp_path / "nothing-here"), "arm64"]) == 1


def test_every_platform_the_build_makes_is_checked():
    """A guard that only covers the architecture somebody happened to think
    of is half a guard. Every matrix entry must say what it expects, and the
    step that reads it must be wired in."""
    import yaml
    flow = yaml.safe_load(
        (HERE.parent / ".github" / "workflows" / "release.yml").read_text())
    entries = flow["jobs"]["build"]["strategy"]["matrix"]["include"]
    assert len(entries) >= 6, f"only {len(entries)} builds"
    for entry in entries:
        assert entry.get("expect"), f"{entry['label']} says nothing it expects"
    steps = flow["jobs"]["build"]["steps"]
    ran = [s.get("run", "") for s in steps]
    assert any("check_binary_arch.py" in r for r in ran), (
        "nothing reads the built binary's architecture")


def test_windows_is_built_for_both_architectures():
    """It was the one platform covered on a single architecture, while macOS
    and Linux each had both."""
    import yaml
    flow = yaml.safe_load(
        (HERE.parent / ".github" / "workflows" / "release.yml").read_text())
    entries = flow["jobs"]["build"]["strategy"]["matrix"]["include"]
    by_os = {}
    for entry in entries:
        which = entry["label"].split()[0]
        by_os.setdefault(which, set()).add(entry["expect"])
    for which, kinds in by_os.items():
        assert kinds == {"arm64", "x86_64"}, (
            f"{which} is built for {kinds} only")
