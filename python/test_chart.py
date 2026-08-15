"""A chart waiting to be printed: reading it, placing it, and counting it.

Everything here is checked against something outside itself where it can be:
the same chart written in three different formats must give the same patches,
the shortlist-free nearest-point solver must agree with sampling a triangle
four thousand times over, and a chart placed through a profile must land inside
that profile.
"""
from __future__ import annotations

import struct

import numpy as np
import pytest

import cgats
import chart
from test_cgats import A_REAL_TI1, A_REAL_TI2


# --------------------------------------------------------------------------
# A profile to place things through, built here so this runs anywhere
# --------------------------------------------------------------------------

def _icc_tag(sig: bytes, body: bytes):
    return sig, body


def _xyz_body(x, y, z):
    return b"XYZ " + b"\0" * 4 + b"".join(
        struct.pack(">i", int(round(v * 65536))) for v in (x, y, z))


def _gamma_curve(gamma: float):
    return b"curv" + b"\0" * 4 + struct.pack(">I", 1) \
        + struct.pack(">H", int(round(gamma * 256)))


def write_matrix_profile(path, gamma: float = 2.2):
    """A minimal but genuinely valid RGB matrix/TRC profile, sRGB's primaries.

    Written by hand so this test needs nothing installed and gives the same
    answer on every machine. It exercises the same ``_matrix_to_pcs`` path a
    real display profile takes.
    """
    tags = [
        _icc_tag(b"rXYZ", _xyz_body(0.4360, 0.2225, 0.0139)),
        _icc_tag(b"gXYZ", _xyz_body(0.3851, 0.7169, 0.0971)),
        _icc_tag(b"bXYZ", _xyz_body(0.1431, 0.0606, 0.7139)),
        _icc_tag(b"rTRC", _gamma_curve(gamma)),
        _icc_tag(b"gTRC", _gamma_curve(gamma)),
        _icc_tag(b"bTRC", _gamma_curve(gamma)),
        _icc_tag(b"wtpt", _xyz_body(0.9642, 1.0, 0.8249)),
    ]
    table = struct.pack(">I", len(tags))
    at = 132 + 12 * len(tags)
    entries, blob = b"", b""
    for sig, body in tags:
        entries += struct.pack(">4sII", sig, at + len(blob), len(body))
        blob += body + b"\0" * (-len(body) % 4)
    header = bytearray(128)
    header[12:16] = b"mntr"
    header[16:20] = b"RGB "
    header[20:24] = b"XYZ "
    header[36:40] = b"acsp"
    header[8] = 2
    header[9] = 0x40
    raw = bytes(header) + table + entries + blob
    raw = struct.pack(">I", len(raw)) + raw[4:]
    path.write_bytes(raw)
    return path


@pytest.fixture
def profile(tmp_path):
    return write_matrix_profile(tmp_path / "test-space.icc")


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def test_a_ti1_reads_only_its_first_table(tmp_path):
    """The other two tables are reference values about the chart, not patches
    to print. Counting them makes the chart longer than it is."""
    where = tmp_path / "c.ti1"
    where.write_text(A_REAL_TI1)
    got = chart.read_chart(where)
    assert got.n_patches == 3
    assert got.kind == "CTI1"


def test_ink_amounts_from_a_ti1_are_read_as_0_to_100(tmp_path):
    """ArgyllCMS's own formats are defined that way, so there is nothing to
    guess. Reading 100 as though it were out of 255 scales every patch to 0.39
    of where it belongs, and the picture still looks entirely plausible."""
    where = tmp_path / "c.ti1"
    where.write_text(A_REAL_TI1)
    got = chart.read_chart(where)
    assert got.scale == 100.0 and got.scale_certain
    assert got.device.max() == pytest.approx(1.0)
    assert got.device[2].tolist() == pytest.approx([0.5, 0.5, 0.5])


def test_ink_amounts_from_an_i1profiler_export_are_read_as_0_to_255(tmp_path):
    where = tmp_path / "target.txt"
    where.write_text(
        "CGATS.5\n\nORIGINATOR \"ChromIQ\"\n\nKEYWORD \"SampleID\"\n"
        "NUMBER_OF_FIELDS 4\nBEGIN_DATA_FORMAT\nSampleID RGB_R RGB_G RGB_B\n"
        "END_DATA_FORMAT\n\nNUMBER_OF_SETS 3\nBEGIN_DATA\n"
        "1 255.0000 255.0000 255.0000\n2 0.0000 0.0000 0.0000\n"
        "3 128.0000 128.0000 128.0000\nEND_DATA\n")
    got = chart.read_chart(where)
    assert got.scale == 255.0 and got.scale_certain
    assert got.device.max() == pytest.approx(1.0)


def test_the_same_chart_in_two_formats_holds_the_same_patches(tmp_path):
    """THE CROSS-CHECK THAT MAKES THE SCALE RULE TRUSTWORTHY. One chart, one
    written counting to 100 and one counting to 255: if either is read on the
    wrong scale the two disagree by a factor of 2.55."""
    ti1 = tmp_path / "same.ti1"
    ti1.write_text(A_REAL_TI1)
    txt = tmp_path / "same.txt"
    rows = "\n".join(
        f"{i + 1} " + " ".join(f"{v * 255:.4f}" for v in triple)
        for i, triple in enumerate([(1, 1, 1), (0, 0, 0), (0.5, 0.5, 0.5)]))
    txt.write_text(
        "CGATS.5\n\nNUMBER_OF_FIELDS 4\nBEGIN_DATA_FORMAT\n"
        "SampleID RGB_R RGB_G RGB_B\nEND_DATA_FORMAT\n"
        f"NUMBER_OF_SETS 3\nBEGIN_DATA\n{rows}\nEND_DATA\n")
    assert chart.read_chart(ti1).device == pytest.approx(
        chart.read_chart(txt).device, abs=1e-6)


def test_a_chart_that_cannot_say_which_scale_it_uses_admits_it(tmp_path):
    """A chart with no bright patch could be counting to either. Assuming one
    silently is how a picture comes out smooth, plausible and wrong."""
    where = tmp_path / "dim.txt"
    where.write_text(
        "CGATS.5\nNUMBER_OF_FIELDS 4\nBEGIN_DATA_FORMAT\n"
        "SampleID RGB_R RGB_G RGB_B\nEND_DATA_FORMAT\nBEGIN_DATA\n"
        "1 10.0 12.0 9.0\n2 20.0 22.0 19.0\nEND_DATA\n")
    got = chart.read_chart(where)
    assert not got.scale_certain
    assert got.scale == 100.0


def test_sheet_positions_come_across_from_a_ti2(tmp_path):
    where = tmp_path / "c.ti2"
    where.write_text(A_REAL_TI2)
    got = chart.read_chart(where)
    assert got.locations == ("E11", "A1")


def test_repeated_patches_are_counted_not_hidden(tmp_path):
    where = tmp_path / "c.ti1"
    where.write_text(A_REAL_TI1.replace(
        "3 50.00000 50.00000 50.00000 21.14266 22.19007 24.08306",
        "3 100.0000 100.0000 100.0000 95.10649 100.0000 108.8440"))
    got = chart.read_chart(where)
    assert got.n_patches == 3 and got.duplicates == 1
    assert got.unique().n_patches == 2


def test_ink_amounts_out_of_range_are_pulled_back_and_reported(tmp_path):
    where = tmp_path / "c.txt"
    where.write_text(
        "CGATS.5\nNUMBER_OF_FIELDS 4\nBEGIN_DATA_FORMAT\n"
        "SampleID RGB_R RGB_G RGB_B\nEND_DATA_FORMAT\nBEGIN_DATA\n"
        "1 300.0 255.0 255.0\n2 -5.0 0.0 0.0\n3 255.0 255.0 255.0\n"
        "END_DATA\n")
    got = chart.read_chart(where)
    assert got.clamped == 2
    assert got.device.min() >= 0.0 and got.device.max() <= 1.0


def test_a_ti1s_xyz_is_kept_as_a_prediction_and_never_as_a_measurement(tmp_path):
    """targen writes XYZ into a .ti1 from its own device model — with no
    profile to predict with, the black patch comes out as XYZ 1,1,1. Treating
    those as readings gives a plausible, symmetrical, entirely fictional
    gamut."""
    where = tmp_path / "c.ti1"
    where.write_text(A_REAL_TI1)
    got = chart.read_chart(where)
    assert got.expected is not None
    assert not got.expected_accurate       # no ACCURATE_EXPECTED_VALUES here
    # And the reader that draws measured gamuts refuses it outright.
    from ti3gamut import read_ti3
    with pytest.raises(ValueError, match="chart waiting to be printed"):
        read_ti3(where)


def test_a_chart_predicted_through_a_real_profile_says_so(tmp_path):
    where = tmp_path / "c.ti1"
    where.write_text(A_REAL_TI1.replace(
        'COLOR_REP "iRGB"', 'COLOR_REP "iRGB"\nACCURATE_EXPECTED_VALUES "true"'))
    assert chart.read_chart(where).expected_accurate


def test_a_cmyk_chart_is_read_as_cmyk(tmp_path):
    where = tmp_path / "c.ti1"
    where.write_text(
        "CTI1\nCOLOR_REP \"CMYK\"\nNUMBER_OF_FIELDS 5\nBEGIN_DATA_FORMAT\n"
        "SAMPLE_ID CMYK_C CMYK_M CMYK_Y CMYK_K\nEND_DATA_FORMAT\n"
        "BEGIN_DATA\n1 0 0 0 0\n2 100 100 100 100\nEND_DATA\n")
    got = chart.read_chart(where)
    assert got.channels == ("C", "M", "Y", "K") and not got.is_rgb


def test_a_measurement_offered_as_a_chart_is_refused_by_name(tmp_path):
    where = tmp_path / "measured.ti3"
    where.write_text(
        "CTI3\nNUMBER_OF_FIELDS 7\nBEGIN_DATA_FORMAT\n"
        "SAMPLE_ID RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z\nEND_DATA_FORMAT\n"
        "BEGIN_DATA\n1 100 100 100 95 100 108\nEND_DATA\n")
    with pytest.raises(chart.ChartProblem, match="measurement"):
        chart.read_chart(where)
    assert not chart.looks_like_chart(where)


def test_a_file_with_no_ink_amounts_at_all_says_what_is_missing(tmp_path):
    where = tmp_path / "odd.txt"
    where.write_text("CGATS.5\nNUMBER_OF_FIELDS 2\nBEGIN_DATA_FORMAT\n"
                     "SampleID NOTE\nEND_DATA_FORMAT\nBEGIN_DATA\n"
                     "1 hello\nEND_DATA\n")
    with pytest.raises(chart.ChartProblem, match="RGB_R"):
        chart.read_chart(where)


def test_looks_like_chart_never_raises_on_rubbish(tmp_path):
    """It only chooses which reader gets the file; the reader gives the good
    error message, so a guess must never itself be the error."""
    bad = tmp_path / "x.ti1"
    bad.write_bytes(b"\x00\x01\x02not a file at all")
    assert chart.looks_like_chart(bad) is False
    assert chart.looks_like_chart(tmp_path / "nothing-here.ti1") is False


def test_an_i1profiler_pxf_target_is_read_without_argyllcms(tmp_path):
    """ArgyllCMS's txt2ti3 refuses these outright — it converts measurements,
    and a chart has none — so reading it here is the only route, and it also
    works on a machine with no ArgyllCMS at all."""
    where = tmp_path / "t.pxf"
    where.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<cc:CxF xmlns:cc="http://colorexchangeformat.com/CxF3-core">'
        "<cc:Resources><cc:ObjectCollection>"
        '<cc:Object ObjectType="Target" Name="T1"><cc:DeviceColorValues>'
        '<cc:ColorRGB><cc:R>255</cc:R><cc:G>255</cc:G><cc:B>255</cc:B>'
        "</cc:ColorRGB></cc:DeviceColorValues></cc:Object>"
        '<cc:Object ObjectType="Target" Name="T2"><cc:DeviceColorValues>'
        '<cc:ColorRGB><cc:R>0</cc:R><cc:G>0</cc:G><cc:B>0</cc:B>'
        "</cc:ColorRGB></cc:DeviceColorValues></cc:Object>"
        "</cc:ObjectCollection></cc:Resources></cc:CxF>")
    got = chart.read_chart(where)
    assert got.n_patches == 2 and got.kind == "CxF3"
    assert got.device.tolist() == [[1, 1, 1], [0, 0, 0]]
    assert chart.looks_like_chart(where)


# --------------------------------------------------------------------------
# Placing
# --------------------------------------------------------------------------

def _grid_chart(steps=5):
    axis = np.linspace(0, 1, steps)
    device = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"),
                      axis=-1).reshape(-1, 3)
    return chart.Chart(name="grid", device=device, channels=("R", "G", "B"),
                       kind="CTI1", scale=100.0, scale_certain=True,
                       n_rows=len(device), duplicates=0, clamped=0)


def test_a_chart_placed_through_a_profile_lands_inside_that_profile(profile):
    """The check that would catch almost anything going wrong in the placing:
    the same profile put these patches where they are."""
    from icc_read import profile_gamut

    placed = chart.through_profile(_grid_chart(), profile)
    report = chart.outside_report(placed.lab, profile_gamut(profile, steps=17))
    assert report.n_beyond == 0, (report.n_beyond, report.worst)


def test_white_goes_to_white_and_black_goes_to_black(profile):
    placed = chart.through_profile(_grid_chart(2), profile)
    lightest = placed.lab[np.argmax(placed.lab[:, 0])]
    darkest = placed.lab[np.argmin(placed.lab[:, 0])]
    assert lightest[0] == pytest.approx(100.0, abs=0.5)
    assert abs(lightest[1]) < 1.0 and abs(lightest[2]) < 1.0
    assert darkest[0] == pytest.approx(0.0, abs=0.5)


def test_the_intent_actually_used_is_reported(profile):
    placed = chart.through_profile(_grid_chart(3), profile)
    assert placed.tag == "matrix"
    assert "primaries" in placed.intent
    assert placed.profile == "test-space"


def test_a_cmyk_chart_through_an_rgb_profile_says_why_not(profile):
    four = chart.Chart(name="c", device=np.zeros((4, 4)),
                       channels=("C", "M", "Y", "K"), kind="CTI1",
                       scale=100.0, scale_certain=True, n_rows=4,
                       duplicates=0, clamped=0)
    with pytest.raises(chart.ChartProblem, match="CMYK chart"):
        chart.through_profile(four, profile)


def test_a_chart_moves_with_the_white_point_it_is_read_against(profile):
    """Everything else in the window moves when the white point changes; a
    chart left behind in the profile's own D50 would be drawn a few ΔE from
    where the shapes around it went, which is the worst size of wrong for
    something being counted in ΔE."""
    placed = chart.through_profile(_grid_chart(3), profile)
    assert placed.under("D50") == pytest.approx(placed.lab, abs=1e-6)
    assert not np.allclose(placed.under("D65"), placed.lab, atol=0.5)


# --------------------------------------------------------------------------
# Counting what falls outside
# --------------------------------------------------------------------------

def test_the_closest_point_on_a_triangle_is_really_on_it():
    """Sampled four thousand times over each triangle: the solver may never be
    further away than a point somebody found by guessing."""
    rng = np.random.default_rng(11)
    triangles = rng.normal(size=(30, 3, 3)) * 10
    points = rng.normal(size=(20, 3)) * 15
    got = chart._closest_on_triangles(points[:, None, :],
                                      triangles[None, :, :, :])
    u = rng.random((4000, 2))
    u = np.where(u.sum(1, keepdims=True) > 1, 1 - u, u)
    bary = np.column_stack([1 - u.sum(1), u[:, 0], u[:, 1]])
    for k, triangle in enumerate(triangles):
        on_it = bary @ triangle
        sampled = np.linalg.norm(on_it[None] - points[:, None], axis=2).min(1)
        mine = np.linalg.norm(got[:, k, :] - points, axis=1)
        assert (mine <= sampled + 1e-9).all()


def test_distance_outside_is_to_the_surface_not_to_the_nearest_corner():
    """On a real gamut the corners are tens of ΔE apart, so "distance to the
    nearest corner" turns a patch barely outside into an alarming number."""
    from scipy.spatial import ConvexHull

    corners = np.array([[0., 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100]])
    middle_of_a_face = np.array([[33.4, 33.4, 33.4]])
    on_surface = chart.nearest_on_hull(middle_of_a_face, corners)
    to_surface = np.linalg.norm(on_surface - middle_of_a_face)
    to_corner = np.linalg.norm(corners - middle_of_a_face, axis=1).min()
    assert to_surface < 1.0
    assert to_corner > 50.0
    assert len(ConvexHull(corners).simplices) == 4


def test_a_point_inside_a_dented_shape_is_not_found_by_its_own_corners():
    """The trap that made the first version wrong by 18 units: a measured
    surface is dented, so many of its points lie INSIDE its own hull and touch
    none of its triangles. A shortlist built from them found an interior point
    and called it the surface."""
    rng = np.random.default_rng(3)
    shell = rng.normal(size=(200, 3))
    shell /= np.linalg.norm(shell, axis=1, keepdims=True)
    dented = np.vstack([shell * 50, rng.normal(size=(200, 3)) * 5])
    far_out = np.array([[120.0, 0.0, 0.0]])
    got = chart.nearest_on_hull(far_out, dented)
    assert np.linalg.norm(got - far_out) == pytest.approx(70.0, abs=3.0)


def test_patches_barely_outside_are_called_on_the_edge_not_outside():
    """Measured: pushing a 5960-patch chart through the very profile that
    placed it left a couple of hundred patches a whisker outside, and the
    distance fell towards nothing as the surface was sampled more finely. The
    count is an artefact of the sampling; the distance is the real answer."""
    corners = np.array([[0., 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100],
                        [60, 60, 60]])
    just_out = np.array([[0.0, 0.0, -0.2]])
    report = chart.outside_report(just_out, corners)
    assert report.n_outside == 1
    assert report.n_beyond == 0
    assert report.all_inside            # nothing worth acting on
    assert report.n_edge == 1


def test_a_patch_well_outside_is_counted_and_measured():
    corners = np.array([[0., 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100]])
    report = chart.outside_report(np.array([[50.0, 90.0, 90.0]]), corners)
    assert report.n_beyond == 1
    assert report.worst > 5.0
    assert report.average == report.worst          # only one is outside


def test_the_average_is_over_the_ones_outside_not_over_the_whole_chart():
    """Averaged over everything it would fall as the chart grew, which is the
    opposite of what somebody reads it as."""
    corners = np.array([[0., 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100]])
    one_out = np.array([[50.0, 90.0, 90.0]])
    many_in = np.array([[10.0, 5.0, 5.0]] * 50)
    small = chart.outside_report(one_out, corners)
    large = chart.outside_report(np.vstack([one_out, many_in]), corners)
    assert large.average == pytest.approx(small.average)
    assert large.n_patches == 51 and large.n_beyond == 1


def test_a_chart_of_nothing_usable_reports_nothing_rather_than_crashing():
    corners = np.array([[0., 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100]])
    report = chart.outside_report(np.full((3, 3), np.nan), corners)
    assert report.n_patches == 0 and report.n_outside == 0


# --------------------------------------------------------------------------
# How the patches are spread
# --------------------------------------------------------------------------

def test_repeats_are_set_aside_before_measuring_the_spacing():
    """Charts repeat white and black on purpose, and those land on exactly the
    same colour — so "the closest pair are 0.0 apart" comes out of every real
    chart, says nothing, and hides the answer somebody wanted."""
    points = np.array([[0., 0, 0], [0, 0, 0], [10, 0, 0], [30, 0, 0],
                       [60, 0, 0]])
    got = chart.spread(points)
    assert got.repeats == 1
    assert got.closest == pytest.approx(10.0)
    assert got.largest_gap == pytest.approx(30.0)
    assert got.n_patches == 4


def test_a_regular_grid_has_one_spacing_throughout():
    axis = np.linspace(0, 100, 6)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"),
                    axis=-1).reshape(-1, 3)
    got = chart.spread(grid)
    assert got.closest == pytest.approx(got.largest_gap)
    assert got.median_gap == pytest.approx(20.0)


def test_a_gap_in_the_chart_shows_up_as_the_largest_gap():
    points = np.vstack([np.column_stack([np.linspace(0, 20, 10),
                                         np.zeros(10), np.zeros(10)]),
                        [[90.0, 0.0, 0.0]]])
    got = chart.spread(points)
    assert got.largest_gap == pytest.approx(70.0)
    assert got.closest < 3.0


def test_a_chart_too_small_to_say_anything_says_nothing():
    assert chart.spread(np.zeros((2, 3))) is None


def _a_cmyk_profile():
    """Whatever four-ink profile this machine happens to carry."""
    import glob
    for pattern in ("/System/Library/ColorSync/Profiles/*.icc",
                    "/Library/ColorSync/Profiles/*.icc",
                    "/usr/share/color/icc/**/*.icc"):
        for path in glob.glob(pattern, recursive=True):
            try:
                from icc_read import describe
                if describe(path)["space"] == "CMYK":
                    return path
            except Exception:                      # noqa: BLE001
                continue
    return None


def test_a_four_ink_chart_goes_through_a_four_ink_profile(tmp_path):
    """The CMYK path all the way through, on a real profile. Four inks are not
    a cube — the same colour can be mixed several ways — so this exercises a
    different route through the placing than any RGB chart does."""
    profile = _a_cmyk_profile()
    if profile is None:
        pytest.skip("this machine carries no CMYK profile")
    from icc_read import profile_gamut

    axis = np.linspace(0, 100, 4)
    device = np.stack(np.meshgrid(*[axis] * 4, indexing="ij"),
                      axis=-1).reshape(-1, 4)
    rows = "\n".join(f"{i + 1} " + " ".join(f"{v:.4f}" for v in quad)
                     for i, quad in enumerate(device))
    where = tmp_path / "four-ink.ti1"
    where.write_text(
        'CTI1\nCOLOR_REP "CMYK"\nNUMBER_OF_FIELDS 5\nBEGIN_DATA_FORMAT\n'
        "SAMPLE_ID CMYK_C CMYK_M CMYK_Y CMYK_K\nEND_DATA_FORMAT\n"
        f"NUMBER_OF_SETS {len(device)}\nBEGIN_DATA\n{rows}\nEND_DATA\n")

    read = chart.read_chart(where)
    assert read.channels == ("C", "M", "Y", "K")
    placed = chart.through_profile(read, profile)
    assert placed.tag in ("A2B1", "A2B0")
    assert np.isfinite(placed.lab).all()
    report = chart.outside_report(placed.lab, profile_gamut(profile, steps=9))
    assert report.n_beyond == 0, (report.n_beyond, report.worst)


# --------------------------------------------------------------------------
# Ink amounts — a chart drawn on its own, with no profile at all
# --------------------------------------------------------------------------

def test_ink_amounts_are_the_files_own_numbers_and_need_no_profile():
    """The whole point of the view: nothing here is predicted or assumed.

    A chart file holds the amounts about to be asked of the printer. Those are
    true of the chart alone — they do not change with the printer, the paper
    or the profile — so they can be drawn straight away, and the numbers on
    the axes are the numbers in the file.
    """
    c = _grid_chart(3)
    positions = chart.device_positions(c)
    assert positions.shape == (27, 3)
    assert positions.min() == 0.0 and positions.max() == 100.0
    # Exactly the file's own values, scaled to the 0..100 the axes are marked
    # in and nothing else. Any profile lookup would break this equality.
    assert np.allclose(positions, c.device * 100.0)


def test_a_real_argyll_chart_can_be_drawn_in_ink_with_no_profile(tmp_path):
    p = tmp_path / "real.ti1"
    p.write_text(A_REAL_TI1)
    c = chart.read_chart(p)
    ok, why = chart.can_draw_in_ink(c)
    assert ok and why == ""
    positions = chart.device_positions(c)
    assert len(positions) == c.n_patches
    assert 0.0 <= positions.min() and positions.max() <= 100.0


def test_a_cmyk_chart_cannot_go_on_three_ink_axes_and_says_so():
    """Four inks do not fit three axes, and there is no honest flattening.

    Dropping black or folding it into the other three would draw a chart that
    was never in the file. The message has to send somebody somewhere useful,
    so it names the control that does work for them.
    """
    four = chart.Chart(name="c", device=np.zeros((4, 4)),
                       channels=("C", "M", "Y", "K"), kind="CTI1",
                       scale=100.0, scale_certain=True, n_rows=4,
                       duplicates=0, clamped=0)
    ok, why = chart.can_draw_in_ink(four)
    assert not ok
    assert "C, M, Y, K" in why
    assert "CIELAB" in why and "Placed through" in why
    with pytest.raises(chart.ChartProblem, match="three axes"):
        chart.device_positions(four)


def test_the_scale_a_file_counted_in_never_reaches_the_axes():
    """A 0-255 file and a 0-100 file describing the same patch draw the same.

    ``read_chart`` already brings both to a shared 0..1, and this is the test
    that keeps it that way: the ink-amount view has one number on its axes,
    and a file that happened to count to 255 must not stretch the picture two
    and a half times.
    """
    hundred = chart.Chart(name="a", device=np.array([[0.5, 0.25, 1.0]]),
                          channels=("R", "G", "B"), kind="CTI1", scale=100.0,
                          scale_certain=True, n_rows=1, duplicates=0,
                          clamped=0)
    of_255 = chart.Chart(name="b", device=np.array([[0.5, 0.25, 1.0]]),
                         channels=("R", "G", "B"), kind="CGATS.5", scale=255.0,
                         scale_certain=True, n_rows=1, duplicates=0, clamped=0)
    assert np.allclose(chart.device_positions(hundred),
                       chart.device_positions(of_255))
    assert np.allclose(chart.device_positions(hundred), [[50.0, 25.0, 100.0]])


def test_spacing_in_ink_amounts_is_measured_in_ink_amounts():
    """A regular grid has a known answer, which is what makes this a check.

    5 steps from 0 to 100 puts every neighbour exactly 25 apart, so the
    closest pair, the widest hole and the middle are all 25. If the figure
    were being taken in Lab — or the positions were being run through a
    profile on the way — none of the three would come out round.
    """
    positions = chart.device_positions(_grid_chart(5))
    s = chart.spread(positions)
    assert s.n_patches == 125 and s.repeats == 0
    assert s.closest == pytest.approx(25.0)
    assert s.largest_gap == pytest.approx(25.0)
    assert s.median_gap == pytest.approx(25.0)


# --------------------------------------------------------------------------
# A skin over the patches — what it is, and what it must never become
# --------------------------------------------------------------------------

def test_a_skin_is_bare_arrays_and_never_a_gamut():
    """The type is the safeguard.

    A Gamut carries a volume, feeds the coverage figures and joins the
    comparison. A chart's skin must do none of those, because a chart samples
    only where its author put patches. Returning bare arrays is what makes
    that impossible rather than merely discouraged.
    """
    import gamutview
    verts, faces = chart.skin(_grid_chart(4).device * 100.0)
    assert isinstance(verts, np.ndarray) and isinstance(faces, np.ndarray)
    assert not isinstance(verts, gamutview.Gamut)
    assert faces.shape[1] == 3 and len(faces) > 0


def test_a_skin_over_a_cube_of_patches_encloses_that_cube():
    from scipy.spatial import ConvexHull
    verts, _faces = chart.skin(_grid_chart(5).device * 100.0)
    # 5 steps from 0 to 100: the hull is the unit cube scaled up.
    assert ConvexHull(verts).volume == pytest.approx(100.0 ** 3, rel=1e-9)


def test_a_flat_chart_gets_no_skin_rather_than_a_broken_one():
    """A grey ramp is a line; a single hue sweep is a plane. Neither encloses
    a solid, and Qhull raises rather than guessing."""
    ramp = np.repeat(np.linspace(0, 100, 12)[:, None], 3, axis=1)
    assert chart.skin(ramp) == (None, None)
    plane = np.column_stack([np.linspace(0, 100, 20),
                             np.linspace(0, 100, 20), np.zeros(20)])
    assert chart.skin(plane) == (None, None)
    assert chart.skin(np.zeros((3, 3))) == (None, None)


def test_the_lost_patches_wrap_around_the_rest_so_they_get_no_skin():
    """The measurement behind refusing an out-of-reach skin.

    The patches a paper cannot reach are the ones furthest out, so a shape
    drawn round them swallows the ones that fit as well. Here it comes to more
    than three quarters of a shape round the whole chart — on a chart where
    only a third is lost. Drawing it would read as "almost all of this is
    gone".
    """
    from scipy.spatial import ConvexHull
    device = _grid_chart(6).device * 100.0
    centre = np.array([50.0, 50.0, 50.0])
    far = np.linalg.norm(device - centre, axis=1)
    lost = far > np.quantile(far, 0.67)          # the outer third
    whole = ConvexHull(np.unique(device.round(9), axis=0)).volume
    around_lost = ConvexHull(np.unique(device[lost].round(9), axis=0)).volume
    # A regular grid puts many patches at exactly the same distance, so the
    # cut lands at 26% rather than the 33% asked for. Asserted as measured —
    # the share is not the point, the ratio below it is.
    assert 0.2 < lost.mean() < 0.35
    assert around_lost / whole > 0.75
