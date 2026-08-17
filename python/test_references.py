"""Tests for the standard-space and ICC reference gamuts."""
import numpy as np
import pytest

from gamutview import coverage
from references import REFERENCE_SPACES, reference_gamut


def test_the_spaces_rank_the_way_they_are_known_to():
    """Independent of this code: sRGB < Adobe RGB < Display P3 < Rec.2020 <
    ProPhoto is the published ordering. Getting it wrong would mean the
    primaries or the matrix are wrong."""
    v = {n: reference_gamut(n).volume for n in REFERENCE_SPACES}
    assert (v["sRGB"] < v["Adobe RGB (1998)"] < v["Display P3"]
            < v["Rec.2020"] < v["ProPhoto RGB"]), v


def test_srgb_fits_inside_adobergb_but_not_the_other_way():
    """The asymmetry everyone knows: Adobe RGB is wider in the greens."""
    s = reference_gamut("sRGB").vertices
    a = reference_gamut("Adobe RGB (1998)").vertices
    assert coverage(s, a)[0] > 0.99
    assert coverage(a, s)[0] < 0.80


def test_a_space_covers_itself_completely():
    g = reference_gamut("sRGB").vertices
    assert coverage(g, g)[0] > 0.999


def test_the_white_point_is_adapted_not_ignored():
    """sRGB is a D65 space. Plotted under D50 it must be chromatically adapted,
    so its shape differs — silently treating D65 as D50 would be a real error."""
    a = reference_gamut("sRGB", white_point="D50").volume
    b = reference_gamut("sRGB", white_point="D65").volume
    assert a != pytest.approx(b)


def test_every_space_builds_a_real_boundary():
    for name in REFERENCE_SPACES:
        g = reference_gamut(name, steps=5)
        assert g.mode == "device-cube"
        assert g.faces.max() < len(g.vertices)
        assert np.isfinite(g.vertices).all()
        assert REFERENCE_SPACES[name]["note"]        # each one explains itself


def test_an_unknown_space_lists_the_known_ones():
    with pytest.raises(ValueError, match="sRGB"):
        reference_gamut("Rec.709-ish")


def test_too_few_steps_is_refused():
    with pytest.raises(ValueError, match="at least 3"):
        reference_gamut("sRGB", steps=2)


def test_a_missing_icc_file_says_so():
    from references import icc_gamut
    with pytest.raises(ValueError, match="no such profile"):
        icc_gamut("/nonexistent/nope.icc")


def test_a_file_that_is_not_a_profile_says_so(tmp_path):
    """Reading a profile needs ArgyllCMS, which not every machine has -- so
    this accepts either honest refusal: "that is not a profile" when the tool
    is present, or "the tool is missing" when it is not. Asserting only the
    first assumed a tool that is not guaranteed, which is what broke this on
    the build machines while passing here."""
    from references import _find_iccgamut, icc_gamut
    bad = tmp_path / "not.icc"
    bad.write_text("this is not an ICC profile")
    with pytest.raises(ValueError, match="could not be read|needs ArgyllCMS"):
        icc_gamut(bad)
    if _find_iccgamut() is None:
        pytest.skip("ArgyllCMS is not installed, so only the refusal is checked")


def test_two_readings_of_one_chart_are_compared_patch_by_patch(tmp_path):
    """The drift check, on files built here so the test needs no measurement."""
    import numpy as np

    from ti3gamut import Measurement, compare_measurements

    rng = np.random.default_rng(11)
    device = np.column_stack([rng.uniform(0, 1, 60) for _ in range(3)])
    lab = np.column_stack([rng.uniform(10, 90, 60), rng.uniform(-40, 40, 60),
                           rng.uniform(-40, 40, 60)])
    before = Measurement("a", device, lab, "test", 60)
    # A small, believable drift: the second reading is very slightly lighter.
    after = Measurement("b", device, lab + np.array([0.4, 0.0, 0.0]), "test", 60)
    d = compare_measurements(before, after)
    assert d.matched == 60
    assert 0.2 < d.worst < 1.0            # small but real
    assert d.over_three == 0
    assert len(d.worst_patches) == 8


def test_two_different_charts_are_refused_rather_than_guessed():
    """A confident number describing nothing is worse than a refusal."""
    import numpy as np

    from ti3gamut import Measurement, compare_measurements

    rng = np.random.default_rng(3)
    a = Measurement("a", rng.uniform(0, 1, (40, 3)),
                    rng.uniform(0, 60, (40, 3)), "t", 40)
    b = Measurement("b", rng.uniform(0, 1, (40, 3)),
                    rng.uniform(0, 60, (40, 3)), "t", 40)
    with pytest.raises(ValueError, match="not two readings of the same chart|too few"):
        compare_measurements(a, b)


def test_the_greys_are_found_and_sorted_dark_to_light():
    import numpy as np

    from ti3gamut import Measurement, neutral_axis

    device = np.array([[0.0, 0.0, 0.0], [0.5, 0.5, 0.5], [1.0, 1.0, 1.0],
                       [1.0, 0.0, 0.0]])          # the last one is not a grey
    lab = np.array([[5.0, 1.0, -2.0], [52.0, 0.5, 1.0], [95.0, -0.2, 2.0],
                    [50.0, 70.0, 50.0]])
    lab_out, labels = neutral_axis(Measurement("x", device, lab, "t", 4))
    assert len(lab_out) == 3                       # the red is left out
    assert list(lab_out[:, 0]) == sorted(lab_out[:, 0])
    assert labels == ["0% grey", "50% grey", "100% grey"]


def test_a_chart_without_device_values_has_no_greys_to_show():
    import numpy as np

    from ti3gamut import Measurement, neutral_axis

    lab_out, labels = neutral_axis(
        Measurement("x", None, np.zeros((5, 3)), "t", 5))
    assert len(lab_out) == 0 and labels == []


def test_a_gamut_file_reports_the_volume_its_own_triangles_enclose():
    """A .gam describes a DENTED surface. Measuring the convex hull of its
    vertices instead over-states it -- 8.3% on a real profile gamut -- and
    makes this tool disagree with ArgyllCMS about the very file ArgyllCMS
    wrote. The triangles are in the file; they are what must be measured."""
    import numpy as np
    from scipy.spatial import ConvexHull

    from gamutview import Gamut, mesh_volume

    # A cube with one corner pushed inwards: dented, so hull > true volume.
    pts = np.array([[0., 0., 0.], [10., 0., 0.], [10., 10., 0.], [0., 10., 0.],
                    [0., 0., 10.], [10., 0., 10.], [10., 10., 10.],
                    [7., 7., 7.]])
    hull = ConvexHull(pts)
    true = mesh_volume(pts, hull.simplices)
    assert true == pytest.approx(float(hull.volume), rel=1e-9)

    # And the property that matters: for any closed surface, mesh_volume is
    # what the triangles enclose, never the hull of the points.
    dented = np.array([[0., 0., 0.], [10., 0., 0.], [10., 10., 0.], [0., 10., 0.],
                       [5., 5., 2.]])
    faces = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4],
                      [0, 2, 1], [0, 3, 2]])
    assert mesh_volume(dented, faces) < float(ConvexHull(
        np.vstack([dented, [[5., 5., 8.]]])).volume)


# --- ICC version 4, which ArgyllCMS declines --------------------------------

def _system_profiles():
    """Whatever ICC profiles this machine happens to carry."""
    import glob
    import pathlib
    return [pathlib.Path(p) for p in sorted(set(
        glob.glob("/System/Library/ColorSync/Profiles/*.icc")
        + glob.glob("/Library/ColorSync/Profiles/*.icc")
        + glob.glob("/usr/share/color/icc/**/*.icc", recursive=True)
        + glob.glob(r"C:\Windows\System32\spool\drivers\color\*.icm")))]


def test_the_header_is_read_the_way_the_specification_writes_it():
    """The version is a byte for the major number and a packed byte for the
    rest: 4.3 is stored as 04 30. Shifting the first byte reads EVERY profile
    as version 0, which silently makes the v4 path unreachable."""
    import icc_read
    seen = {}
    for path in _system_profiles():
        try:
            head = icc_read.describe(path)
        except icc_read.UnsupportedProfile:
            continue
        seen[head["major"]] = seen.get(head["major"], 0) + 1
    if not seen:
        pytest.skip("this machine carries no ICC profiles")
    assert set(seen) <= {2, 4, 5}, seen
    assert 0 not in seen


def test_our_reader_agrees_with_argyll_wherever_argyll_can_read_it():
    """THE check that makes the fallback trustworthy. A parser is only worth
    having if it gives the same answer as a mature implementation on every
    file both can open; agreeing on those is what earns the right to be
    believed on the files only one of them can.

    Three-channel profiles only: for four inks there is no cube to walk, so
    that path deliberately reports the outer skin and is a different quantity.
    """
    import icc_read
    from references import icc_gamut
    compared = []
    for path in _system_profiles():
        try:
            head = icc_read.describe(path)
        except icc_read.UnsupportedProfile:
            continue
        if head["class"] in ("abst", "link", "nmcl") or head["space"] != "RGB":
            continue
        try:
            theirs = icc_gamut(path).volume
        except Exception:                                # noqa: BLE001
            continue                                     # Argyll refused it
        try:
            ours = icc_read.profile_gamut(path).volume
        except icc_read.UnsupportedProfile:
            continue
        compared.append((path.name, theirs, ours))
    if not compared:
        pytest.skip("no profile on this machine can be read both ways")
    for name, theirs, ours in compared:
        off = abs(ours - theirs) / theirs
        assert off < 0.03, f"{name}: Argyll {theirs:,.0f} vs ours {ours:,.0f}"


def test_every_version_four_profile_here_can_now_be_opened():
    """The reason this exists at all. Any v4 RGB profile the machine carries
    must produce a real volume rather than a refusal."""
    import icc_read
    opened = 0
    for path in _system_profiles():
        try:
            head = icc_read.describe(path)
        except icc_read.UnsupportedProfile:
            continue
        if head["major"] < 4 or head["space"] != "RGB":
            continue
        if head["class"] in ("abst", "link", "nmcl"):
            continue
        gamut = icc_read.profile_gamut(path)
        assert gamut.volume > 1000, f"{path.name} gave {gamut.volume}"
        assert len(gamut.vertices) > 50
        opened += 1
    if not opened:
        pytest.skip("this machine carries no version 4 RGB profile")


def test_a_file_that_is_not_a_profile_says_so_rather_than_crashing(tmp_path):
    import icc_read
    for name, body in (("empty.icc", b""),
                       ("short.icc", b"\x00" * 60),
                       ("wrong.icc", b"\x00" * 40 + b"nope" + b"\x00" * 200)):
        bad = tmp_path / name
        bad.write_bytes(body)
        with pytest.raises(icc_read.UnsupportedProfile):
            icc_read.describe(bad)


def test_a_truncated_profile_is_refused_rather_than_half_read(tmp_path):
    """A profile cut in half must not produce a plausible-looking gamut."""
    import icc_read
    for path in _system_profiles():
        try:
            if icc_read.describe(path)["space"] != "RGB":
                continue
        except icc_read.UnsupportedProfile:
            continue
        cut = tmp_path / "cut.icc"
        cut.write_bytes(path.read_bytes()[:len(path.read_bytes()) // 2])
        with pytest.raises(Exception):                   # noqa: B017
            icc_read.profile_gamut(cut)
        return
    pytest.skip("this machine carries no RGB profile to cut in half")


def test_the_parametric_curves_match_their_definitions():
    """Type 3 is the sRGB shape and is what every v4 display profile uses, so
    it is checked against the numbers sRGB is actually defined by."""
    import numpy as np

    from icc_read import _parametric
    srgb = _parametric(3, [2.4, 1 / 1.055, 0.055 / 1.055, 1 / 12.92, 0.04045])
    x = np.array([0.0, 0.02, 0.04045, 0.5, 1.0])
    want = np.where(x >= 0.04045, ((x + 0.055) / 1.055) ** 2.4, x / 12.92)
    assert np.allclose(srgb(x), want, atol=1e-12)
    # A plain gamma, and the identity, both of which appear in real files.
    assert np.allclose(_parametric(0, [2.2])(x), x ** 2.2)
    assert _parametric(0, [1.0])(np.array([0.25]))[0] == pytest.approx(0.25)


def test_reading_a_profile_is_exact_not_approximate():
    """THE claim this reader rests on, checked against ArgyllCMS's own
    evaluator rather than against a gamut.

    Nothing in an ICC profile is open to interpretation: given a device value,
    the matrix, the curves and the tables in the file determine the colour. So
    the two implementations must not merely be close, they must agree to the
    precision the comparison can even express -- `icclu` prints six decimals,
    which is where this bottoms out.

    It is a separate check from the gamut comparison on purpose. A gamut is
    NOT in the file: it is the boundary of everything the mapping can reach,
    and finding a boundary needs sampling, which the specification says
    nothing about. Mixing the two would let a sampling difference hide a
    reading error.
    """
    import pathlib
    import shutil
    import subprocess

    import numpy as np

    import icc_read
    from gamutview import xyz_to_lab

    tool = shutil.which("icclu") or "/Applications/Argyll/bin/icclu"
    if not pathlib.Path(tool).is_file():
        pytest.skip("ArgyllCMS icclu is not installed here")

    rng = np.random.default_rng(3)
    device = np.vstack([np.eye(3), np.zeros((1, 3)), np.ones((1, 3)),
                        rng.random((60, 3))])
    checked = 0
    for path in _system_profiles():
        try:
            head = icc_read.describe(path)
        except icc_read.UnsupportedProfile:
            continue
        if head["space"] != "RGB" or head["class"] in ("abst", "link", "nmcl"):
            continue
        tags = icc_read.read_tags(path)
        if tags.get("A2B1") or tags.get("A2B0"):
            continue                       # covered by the gamut comparison
        fed = "\n".join(f"{a:.8f} {b:.8f} {c:.8f}" for a, b, c in device)
        try:
            done = subprocess.run([tool, "-ff", "-ir", "-pl", str(path)],
                                  input=fed, capture_output=True, text=True,
                                  timeout=90)
        except (OSError, subprocess.SubprocessError):
            continue
        theirs = np.array([[float(x) for x in line.split("->")[-1].split()[:3]]
                           for line in done.stdout.splitlines()
                           if line.strip().endswith("[Lab]")])
        if len(theirs) != len(device):
            continue                       # ArgyllCMS declined this one
        ours = xyz_to_lab(icc_read._matrix_to_pcs(tags, device),
                          icc_read.PCS_WHITE)
        worst = np.linalg.norm(ours - theirs, axis=1).max()
        assert worst < 0.001, f"{path.name}: worst ΔE {worst:.6f}"
        checked += 1
    if not checked:
        pytest.skip("no profile here can be read both ways")


def test_the_pcs_white_is_the_specification_constant_not_a_textbook_d50():
    """The specification fixes the PCS white as three exact s15Fixed16
    numbers. A colour library's CIE D50 differs in the fourth decimal of Z,
    which is small, constant, and the whole gap between agreeing with
    ArgyllCMS exactly and agreeing with it approximately."""
    import numpy as np

    import icc_read
    from gamutview import WHITE_POINTS

    written = np.array([0x0000F6D6, 0x00010000, 0x0000D32D]) / 65536.0
    assert np.allclose(icc_read.PCS_WHITE, written, atol=0)
    # and it is deliberately NOT the textbook one
    assert not np.allclose(icc_read.PCS_WHITE, WHITE_POINTS["D50"], atol=1e-5)


# --- when ArgyllCMS gets stuck ----------------------------------------------

def test_a_profile_argyll_cannot_finish_is_still_opened(tmp_path, monkeypatch):
    """THE FAULT THIS PINS. iccgamut does not always merely decline a profile
    -- sometimes it never returns. Measured on a hand-written 344-byte matrix
    profile: still running after four minutes, while the reader in this very
    application opened the same bytes in milliseconds.

    Giving up there meant the file did not open AT ALL, even though a machine
    with no ArgyllCMS installed opens it instantly by the direct route.
    Refusing a file we can read, because a helper we did not need got stuck,
    is the wrong way round.
    """
    import subprocess

    import references
    from test_chart import write_matrix_profile

    profile = write_matrix_profile(tmp_path / "slow.icc")

    def wedges(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="iccgamut", timeout=1)

    monkeypatch.setattr(references, "_find_iccgamut",
                        lambda: "/nowhere/iccgamut")
    monkeypatch.setattr(subprocess, "run", wedges)
    got = references.icc_gamut(profile)
    assert got.volume > 0, "the profile did not open when Argyll got stuck"


def test_the_patience_is_measured_rather_than_generous(tmp_path, monkeypatch):
    """180 seconds was not patience, it was a three-minute frozen window --
    icc_gamut runs on the UI thread. Real profiles were timed at 0.09s to
    0.22s, so this must stay far above those and nowhere near three minutes."""
    import references
    assert 5 <= references.ICCGAMUT_PATIENCE <= 60, (
        f"{references.ICCGAMUT_PATIENCE}s is either too tight for a large "
        f"profile or long enough to feel like a hang")


def test_the_timeout_that_is_asked_for_is_the_one_that_is_used(tmp_path,
                                                               monkeypatch):
    """A constant nothing reads is a comment. This checks the number actually
    reaches subprocess.run, which is the only place it does any good."""
    import subprocess

    import references
    from test_chart import write_matrix_profile

    profile = write_matrix_profile(tmp_path / "timed.icc")
    seen = {}

    def note(*args, **kw):
        seen["timeout"] = kw.get("timeout")
        raise subprocess.TimeoutExpired(cmd="iccgamut", timeout=1)

    monkeypatch.setattr(references, "_find_iccgamut",
                        lambda: "/nowhere/iccgamut")
    monkeypatch.setattr(subprocess, "run", note)
    references.icc_gamut(profile)
    assert seen["timeout"] == references.ICCGAMUT_PATIENCE
