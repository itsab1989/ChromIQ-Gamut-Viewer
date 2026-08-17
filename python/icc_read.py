"""Read an ICC profile ourselves, when ArgyllCMS will not.

WHY THIS EXISTS
---------------
``iccgamut`` is the right tool for this job and stays the first choice: it is
ArgyllCMS's own answer, in full precision, and it agrees with what ChromIQ
reports elsewhere. But it is built on a library that understands ICC version 2
thoroughly and version 4 only in part, and it refuses a v4 profile outright:

    icc_get_luobj: Unable to locate usable conversion

That is not a rendering-intent problem -- every intent fails the same way. It
is the file format. And version 4 is not exotic: Display P3, Rec. 709,
Rec. 2020 and ROMM RGB all ship with macOS as v4, and paper makers hand out v4
output profiles. "Cannot open that one" is a poor answer for a file the
operating system itself supplies.

WHAT IT DOES
------------
Works out, for a grid of device values, the colour each one lands on, using
the profile's own numbers -- and hands that to the same ``build_gamut`` that
every measured chart goes through. So a profile is treated exactly like a
measurement: device values in, colours out, and the boundary followed rather
than a skin thrown over it.

Two families of profile cover essentially everything real:

* **matrix and curves** -- three primaries and three tone curves. Every RGB
  working space is one of these, and so is every v4 display profile that
  ArgyllCMS turns down, because the refusal is about the *curve* type (v4's
  parametric curves) rather than anything deeper.
* **lookup tables** -- ``A2B1`` for relative colorimetric, in any of the three
  encodings the specification defines (v2's 8- and 16-bit tables, and v4's).
  Printer and press profiles are these.

HOW IT IS KNOWN TO BE RIGHT
---------------------------
It is checked against ArgyllCMS, not against itself. On profiles ArgyllCMS
*can* read, both paths are run and the volumes compared -- see
``test_references.py``. A parser that agrees with a mature implementation on
every file both can read is a parser worth trusting on the files only one of
them can.

COLOUR SCIENCE
--------------
The PCS is D50 by definition, and that is what comes out: Lab under D50, the
same reference the rest of this application measures against. Relative
colorimetric is used, which is the "what can this profile actually reach"
question a gamut asks. No chromatic adaptation is applied on top -- a
well-formed profile has already adapted its numbers to D50, which is what its
``chad`` tag records having done.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

#: THE PCS WHITE IS A CONSTANT IN THE SPECIFICATION, not a matter of picking
#: a D50. ICC writes it as three s15Fixed16 numbers -- 0x0000F6D6, 0x00010000,
#: 0x0000D32D -- which come to 0.964203, 1.0, 0.824905. The CIE textbook D50 a
#: colour library hands you is 0.96422, 1.0, 0.82521: the Z differs in the
#: fourth decimal.
#:
#: That sounds ignorable and is not, because it is the difference between
#: agreeing with ArgyllCMS exactly and agreeing with it approximately. Measured
#: over 100 colours per profile: using the textbook D50 left a constant
#: max ΔE of 0.0248 against `icclu`; using the number below leaves 0.000002,
#: which is that tool's printing precision. Nothing about an ICC profile is
#: open to interpretation -- this was simply the wrong constant.
PCS_WHITE = np.array([0x0000F6D6, 0x00010000, 0x0000D32D]) / 65536.0


class UnsupportedProfile(Exception):
    """This profile cannot be evaluated here, with a reason worth reading."""


# --- the container ----------------------------------------------------------

def read_tags(path) -> dict:
    """Every tag in the file, as raw bytes, keyed by its four-letter name.

    The header and tag table are laid out identically in version 2 and
    version 4, so one reader serves both.
    """
    raw = Path(path).read_bytes()
    if len(raw) < 132:
        raise UnsupportedProfile("this file is too short to be an ICC profile")
    size = struct.unpack(">I", raw[0:4])[0]
    if raw[36:40] != b"acsp":
        raise UnsupportedProfile("this file is not an ICC profile")
    if size > len(raw):
        raise UnsupportedProfile("this ICC profile is truncated")
    count = struct.unpack(">I", raw[128:132])[0]
    if count > 1000:
        raise UnsupportedProfile("this ICC profile's tag table is not sane")
    tags = {}
    for i in range(count):
        at = 132 + i * 12
        if at + 12 > len(raw):
            raise UnsupportedProfile("this ICC profile's tag table is truncated")
        sig, offset, length = struct.unpack(">4sII", raw[at:at + 12])
        if offset + length > len(raw):
            continue                    # a tag pointing outside the file
        tags[sig.decode("latin1")] = raw[offset:offset + length]
    return tags


def describe(path) -> dict:
    """The few header fields worth telling somebody about."""
    raw = Path(path).read_bytes()[:132]
    if len(raw) < 132 or raw[36:40] != b"acsp":
        raise UnsupportedProfile("this file is not an ICC profile")
    # The version is a byte for the major number and a packed byte for the
    # rest: 4.3 is stored as 04 30. Shifting the first byte -- as though the
    # whole thing were packed into one -- reads every profile as version 0.
    return {
        "version": f"{raw[8]}.{raw[9] >> 4}.{raw[9] & 0xF}",
        "major": raw[8],
        "class": raw[12:16].decode("latin1"),
        "space": raw[16:20].decode("latin1").strip(),
        "pcs": raw[20:24].decode("latin1").strip(),
    }


# --- the pieces a profile is built from -------------------------------------

def _s15(raw: bytes, at: int) -> float:
    """s15Fixed16Number: the specification's own fixed-point number."""
    return struct.unpack(">i", raw[at:at + 4])[0] / 65536.0


def _xyz_tag(raw: bytes) -> np.ndarray:
    if raw[:4] != b"XYZ ":
        raise UnsupportedProfile("expected an XYZ tag and found something else")
    return np.array([_s15(raw, 8), _s15(raw, 12), _s15(raw, 16)])


def _curve(raw: bytes):
    """One tone curve, as a function taking and returning 0..1.

    Three shapes appear in real files: a gamma number, a sampled table, and
    version 4's parametric forms. The last is the one that makes ArgyllCMS
    turn a v4 display profile away, so it is the one that matters most here.
    """
    kind = raw[:4]
    if kind == b"curv":
        n = struct.unpack(">I", raw[8:12])[0]
        if n == 0:
            return lambda x: x                       # identity
        if n == 1:
            gamma = struct.unpack(">H", raw[12:14])[0] / 256.0
            return lambda x, g=gamma: np.power(np.clip(x, 0, 1), g)
        table = np.frombuffer(raw[12:12 + 2 * n], dtype=">u2").astype(float) / 65535.0
        grid = np.linspace(0.0, 1.0, len(table))
        return lambda x, t=table, g=grid: np.interp(np.clip(x, 0, 1), g, t)
    if kind == b"para":
        which = struct.unpack(">H", raw[8:10])[0]
        need = {0: 1, 1: 3, 2: 4, 3: 5, 4: 7}.get(which)
        if need is None:
            raise UnsupportedProfile(
                f"this profile uses a parametric curve of type {which}, "
                "which is not one the specification defines")
        p = [_s15(raw, 12 + 4 * i) for i in range(need)]
        return _parametric(which, p)
    raise UnsupportedProfile(
        f"this profile stores its tone curves as {kind.decode('latin1')!r}, "
        "which is not a shape this can evaluate")


def _parametric(which: int, p):
    """The five parametric curve types, straight from the specification.

    Type 3 is the sRGB-shaped one and by far the most common; Display P3,
    Rec. 709 and Rec. 2020 all use it.
    """
    def curve(x):
        x = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
        if which == 0:                                   # Y = X^g
            return np.power(x, p[0])
        if which == 1:                                   # CIE 122-1966
            g, a, b = p
            return np.where(x >= -b / a, np.power(a * x + b, g), 0.0)
        if which == 2:                                   # IEC 61966-3
            g, a, b, c = p
            return np.where(x >= -b / a, np.power(a * x + b, g) + c, c)
        if which == 3:                                   # IEC 61966-2-1 (sRGB)
            g, a, b, c, d = p
            return np.where(x >= d, np.power(a * x + b, g), c * x)
        g, a, b, c, d, e, f = p                          # type 4
        return np.where(x >= d, np.power(a * x + b, g) + e, c * x + f)
    return curve


def _curves_from(raw: bytes, count: int, at: int = 0):
    """*count* curves stored one after another, each padded to four bytes."""
    curves, cursor = [], at
    for _ in range(count):
        if cursor + 12 > len(raw):
            raise UnsupportedProfile("this profile's curve list is truncated")
        kind = raw[cursor:cursor + 4]
        if kind == b"curv":
            n = struct.unpack(">I", raw[cursor + 8:cursor + 12])[0]
            length = 12 + 2 * n
        elif kind == b"para":
            which = struct.unpack(">H", raw[cursor + 8:cursor + 10])[0]
            length = 12 + 4 * {0: 1, 1: 3, 2: 4, 3: 5, 4: 7}.get(which, 0)
        else:
            raise UnsupportedProfile(
                f"unexpected curve type {kind.decode('latin1')!r}")
        curves.append(_curve(raw[cursor:cursor + length]))
        cursor += length + (-length % 4)                 # padded to 4 bytes
    return curves


def _clut(values: np.ndarray, grid_points, out_channels: int, points: np.ndarray):
    """Multi-dimensional linear interpolation through a colour lookup table.

    Done here rather than reached for from a library because the table is laid
    out in the specification's own order -- the first input channel varying
    slowest -- and because it has to run on a grid of a few thousand points,
    which is nothing.
    """
    dims = len(grid_points)
    table = values.reshape(tuple(grid_points) + (out_channels,))
    points = np.clip(points, 0.0, 1.0)

    # Where each point sits between two grid nodes, per axis.
    lows, highs, fracs = [], [], []
    for axis in range(dims):
        n = grid_points[axis]
        scaled = points[:, axis] * (n - 1)
        low = np.floor(scaled).astype(int)
        low = np.clip(low, 0, n - 2 if n > 1 else 0)
        high = np.clip(low + 1, 0, n - 1)
        lows.append(low)
        highs.append(high)
        fracs.append(scaled - low)

    out = np.zeros((len(points), out_channels))
    for corner in range(1 << dims):
        weight = np.ones(len(points))
        index = []
        for axis in range(dims):
            if corner >> axis & 1:
                weight = weight * fracs[axis]
                index.append(highs[axis])
            else:
                weight = weight * (1.0 - fracs[axis])
                index.append(lows[axis])
        out += weight[:, None] * table[tuple(index)]
    return out


# --- the two families -------------------------------------------------------

def _matrix_to_pcs(tags: dict, device: np.ndarray) -> np.ndarray:
    """Three primaries and three curves: device RGB to PCS XYZ."""
    need = ("rXYZ", "gXYZ", "bXYZ", "rTRC", "gTRC", "bTRC")
    if not all(t in tags for t in need):
        raise UnsupportedProfile("this profile has neither a lookup table nor "
                                 "a complete set of primaries and curves")
    matrix = np.column_stack([_xyz_tag(tags["rXYZ"]),
                              _xyz_tag(tags["gXYZ"]),
                              _xyz_tag(tags["bXYZ"])])
    linear = np.column_stack([_curve(tags[t])(device[:, i])
                              for i, t in enumerate(("rTRC", "gTRC", "bTRC"))])
    return linear @ matrix.T


def _lut_to_pcs(raw: bytes, device: np.ndarray, pcs: str) -> np.ndarray:
    """An A2B lookup table, in any of the three encodings, to PCS XYZ."""
    kind = raw[:4]
    if kind in (b"mft1", b"mft2"):
        return _lut_v2(raw, device, pcs, wide=(kind == b"mft2"))
    if kind == b"mAB ":
        return _lut_v4(raw, device, pcs)
    raise UnsupportedProfile(
        f"this profile's lookup table is stored as {kind.decode('latin1')!r}, "
        "which is not an encoding the specification defines")


def _lut_v2(raw: bytes, device: np.ndarray, pcs: str, wide: bool) -> np.ndarray:
    """Version 2's lut8 and lut16: curves, table, curves, with a matrix."""
    n_in, n_out, grid = raw[8], raw[9], raw[10]
    if n_in != device.shape[1]:
        raise UnsupportedProfile(
            f"this profile expects {n_in} channels and the grid has "
            f"{device.shape[1]}")
    at = 48
    if wide:
        n_in_entries, n_out_entries = struct.unpack(">HH", raw[48:52])
        at = 52
    else:
        n_in_entries = n_out_entries = 256

    def table(count, entries, channels):
        nonlocal at
        if wide:
            block = np.frombuffer(raw[at:at + 2 * entries * channels],
                                  dtype=">u2").astype(float) / 65535.0
            at += 2 * entries * channels
        else:
            block = np.frombuffer(raw[at:at + entries * channels],
                                  dtype=np.uint8).astype(float) / 255.0
            at += entries * channels
        return block.reshape(channels, entries)

    in_curves = table(n_in, n_in_entries, n_in)
    grid_size = grid ** n_in * n_out
    if wide:
        clut = np.frombuffer(raw[at:at + 2 * grid_size],
                             dtype=">u2").astype(float) / 65535.0
        at += 2 * grid_size
    else:
        clut = np.frombuffer(raw[at:at + grid_size],
                             dtype=np.uint8).astype(float) / 255.0
        at += grid_size
    out_curves = table(n_out, n_out_entries, n_out)

    axis = np.linspace(0.0, 1.0, n_in_entries)
    shaped = np.column_stack([np.interp(device[:, i], axis, in_curves[i])
                              for i in range(n_in)])
    values = _clut(clut, [grid] * n_in, n_out, shaped)
    axis_out = np.linspace(0.0, 1.0, n_out_entries)
    values = np.column_stack([np.interp(values[:, i], axis_out, out_curves[i])
                              for i in range(n_out)])
    return _pcs_to_xyz(values, pcs, legacy=True)


def _lut_v4(raw: bytes, device: np.ndarray, pcs: str) -> np.ndarray:
    """Version 4's lutAtoBType: A curves, table, M curves, matrix, B curves."""
    n_in, n_out = raw[8], raw[9]
    if n_in != device.shape[1]:
        raise UnsupportedProfile(
            f"this profile expects {n_in} channels and the grid has "
            f"{device.shape[1]}")
    off_b, off_matrix, off_m, off_clut, off_a = struct.unpack(">IIIII", raw[12:32])

    values = device
    if off_a:
        values = np.column_stack([c(values[:, i]) for i, c in
                                  enumerate(_curves_from(raw, n_in, off_a))])
    if off_clut:
        grid_points = list(raw[off_clut:off_clut + n_in])
        precision = raw[off_clut + 16]
        body = raw[off_clut + 20:]
        total = int(np.prod(grid_points)) * n_out
        if precision == 1:
            clut = np.frombuffer(body[:total], dtype=np.uint8).astype(float) / 255.0
        elif precision == 2:
            clut = np.frombuffer(body[:2 * total],
                                 dtype=">u2").astype(float) / 65535.0
        else:
            raise UnsupportedProfile(
                "this profile's lookup table uses an entry size the "
                "specification does not define")
        values = _clut(clut, grid_points, n_out, values)
    if off_m:
        values = np.column_stack([c(values[:, i]) for i, c in
                                  enumerate(_curves_from(raw, n_out, off_m))])
    if off_matrix:
        e = [_s15(raw, off_matrix + 4 * i) for i in range(12)]
        matrix = np.array(e[:9]).reshape(3, 3)
        values = values @ matrix.T + np.array(e[9:12])
    if off_b:
        values = np.column_stack([c(values[:, i]) for i, c in
                                  enumerate(_curves_from(raw, n_out, off_b))])
    return _pcs_to_xyz(values, pcs, legacy=False)


def _pcs_to_xyz(values: np.ndarray, pcs: str, legacy: bool) -> np.ndarray:
    """Undo the PCS's own 0..1 encoding, which differs between Lab and XYZ.

    Version 2's Lab tables use an encoding where L* = 100 falls at 0xFF00
    rather than 0xFFFF -- a detail that quietly scales every result by
    100/100.39 if it is missed, which is the kind of error that looks like a
    rounding difference and is not.
    """
    from gamutview import lab_to_xyz
    if pcs == "Lab":
        if legacy:
            values = values * (65535.0 / 65280.0)
        lab = np.column_stack([values[:, 0] * 100.0,
                               values[:, 1] * 255.0 - 128.0,
                               values[:, 2] * 255.0 - 128.0])
        return lab_to_xyz(lab, PCS_WHITE)
    # XYZ PCS: encoded 0..1 standing for 0..1+32767/32768.
    return values * (65535.0 / 32768.0)


# --- what the rest of the application asks for ------------------------------

def profile_to_lab(path, steps: int = 17):
    """A grid of device values and the colour each one lands on.

    *steps* is per channel. Seventeen gives 4913 points for an RGB profile,
    which is denser than most measured charts and costs a fraction of a second.
    """
    tags = read_tags(path)
    head = describe(path)
    space = head["space"]
    channels = {"RGB": 3, "GRAY": 1, "CMYK": 4}.get(space)
    if channels is None:
        raise UnsupportedProfile(
            f"this is a {space or 'nameless'} profile, and only RGB, grey and "
            "CMYK ones describe a gamut this can draw")
    if channels == 1:
        raise UnsupportedProfile(
            "a grey profile has no colour to enclose -- it is a line rather "
            "than a shape, so there is no volume to show")
    if channels == 4:
        # Four inks do not make a cube, so there is no six-sided boundary to
        # walk: the same colour can be mixed several ways and the surface is
        # not a function of three values. The outer skin of everything the
        # profile can reach is the honest answer for these.
        steps = min(steps, 9)              # 9^4 = 6561 points, plenty

    axis = np.linspace(0.0, 1.0, steps)
    device = np.stack(np.meshgrid(*[axis] * channels, indexing="ij"),
                      axis=-1).reshape(-1, channels)

    from gamutview import xyz_to_lab
    for tag in ("A2B1", "A2B0"):
        if tag in tags:
            xyz = _lut_to_pcs(tags[tag], device, head["pcs"])
            break
    else:
        if channels != 3:
            raise UnsupportedProfile(
                "this profile has no lookup table, and only three-channel "
                "profiles can be described by primaries alone")
        xyz = _matrix_to_pcs(tags, device)
    return device, xyz_to_lab(xyz, PCS_WHITE)


def which_table(path) -> str:
    """Which conversion this profile is read through: A2B1, A2B0 or matrix.

    WHY THIS IS WORTH ASKING OUT LOUD. ``profile_to_lab`` prefers ``A2B1``,
    the relative colorimetric table, and falls back to ``A2B0``, the
    perceptual one, and finally to the primaries. That is the right order for
    drawing one profile. It is a trap for comparing two: a profile carrying
    only a perceptual table, held up against one carrying a colorimetric
    table, differs by a large amount that says nothing whatever about drift —
    perceptual rendering deliberately moves colour, and the two tables are not
    answering the same question.

    So a comparison asks each profile which table it used, and says so when
    they disagree, rather than reporting the difference between two different
    questions as though it were a measurement.
    """
    tags = read_tags(path)
    for tag in ("A2B1", "A2B0"):
        if tag in tags:
            return tag
    return "matrix"


#: What each of those means in words a reader stands a chance with.
TABLE_NAMES = {
    "A2B1": "its relative colorimetric table",
    "A2B0": "its perceptual table",
    "matrix": "its primaries, having no lookup table at all",
}


def profile_gamut(path, *, white_point="D50", space: str = "lab",
                  steps: int = 17, **_ignored):
    """The gamut of an ICC profile ArgyllCMS declines to open.

    The grid goes through the same ``build_gamut`` a measured chart does, with
    its device values alongside, so the boundary follows the profile's real
    dented surface rather than a skin stretched over it -- the same choice,
    for the same reason, as everywhere else here.
    """
    from gamutview import build_gamut
    # Inside an ICC profile "D50" is not a choice of illuminant, it is the
    # PCS, so the caller asking for it gets the specification's own constant
    # rather than a library's textbook one. Anything else is passed through:
    # asking to see the shape under another white is a different question.
    if isinstance(white_point, str) and white_point.upper() == "D50":
        white_point = PCS_WHITE
    device, lab = profile_to_lab(path, steps=steps)
    good = np.isfinite(lab).all(axis=1)
    if good.sum() < 8:
        raise UnsupportedProfile("this profile produced no usable colours")
    if device.shape[1] != 3:
        return build_gamut(lab[good], input_space="lab",
                           white_point=white_point, space=space)
    return build_gamut(lab[good], device[good], input_space="lab",
                       white_point=white_point, space=space)
