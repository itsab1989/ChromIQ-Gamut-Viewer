"""The colours in a picture. Every file is made and removed by pytest."""
import numpy as np
import pytest

import imagegamut


def _write(path, pixels, **kw):
    from PIL import Image
    Image.fromarray(np.asarray(pixels, dtype=np.uint8)).save(path, **kw)
    return path


def _cube(steps=24):
    axis = np.linspace(0, 255, steps)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), -1).reshape(-1, 3)
    side = int(np.ceil(np.sqrt(len(grid))))
    canvas = np.zeros((side * side, 3), np.uint8)
    canvas[:len(grid)] = grid
    return canvas.reshape(side, side, 3)


def test_a_picture_of_every_srgb_colour_measures_like_srgb(tmp_path):
    """Checked against the sRGB shape this application already builds, not
    against itself. They differ by the hull-versus-boundary gap and nothing
    else, so anything far outside that is a real fault."""
    from references import reference_gamut
    got, facts = imagegamut.image_gamut(_write(tmp_path / "cube.png", _cube()))
    srgb = reference_gamut("sRGB", white_point="D50")
    ratio = got.volume / srgb.volume
    assert 1.0 < ratio < 1.15, f"{got.volume:,.0f} against {srgb.volume:,.0f}"
    assert facts["colours"] > 10000
    assert facts["profile"] is False


def test_an_untagged_picture_says_that_srgb_was_assumed(tmp_path):
    """THE honest bit. Assuming is right far more often than not, and doing it
    silently would be exactly the unstated guess this application avoids."""
    _got, facts = imagegamut.image_gamut(_write(tmp_path / "x.png", _cube(8)))
    assert facts["profile"] is False
    assert "assumed" in facts["note"] and "sRGB" in facts["note"]
    assert "smaller than the truth" in facts["note"]      # says which way it errs


def test_a_tagged_picture_uses_its_own_profile(tmp_path):
    """A wide-gamut profile has to produce a wider shape than the same
    numbers read as sRGB -- otherwise the profile is being ignored."""
    import glob
    import pathlib
    wide = None
    for where in glob.glob("/System/Library/ColorSync/Profiles/*.icc"):
        if "AdobeRGB" in where or "ProPhoto" in where or "ROMM" in where:
            wide = pathlib.Path(where)
            break
    if wide is None:
        pytest.skip("no wide-gamut profile on this machine")
    pixels = _cube(12)
    plain = _write(tmp_path / "plain.png", pixels)
    tagged = _write(tmp_path / "tagged.png", pixels, icc_profile=wide.read_bytes())
    small, small_facts = imagegamut.image_gamut(plain)
    big, big_facts = imagegamut.image_gamut(tagged)
    assert small_facts["profile"] is False
    assert big_facts["profile"] is True
    assert "own colour profile" in big_facts["note"]
    assert big.volume > small.volume * 1.05, (big.volume, small.volume)


def test_see_through_pixels_do_not_push_the_shape_outwards(tmp_path):
    """A pixel nobody can see is not a colour the picture shows."""
    from PIL import Image
    varied = _cube(10)                      # a real spread of colours
    side = varied.shape[0]
    solid = np.zeros((side, side, 4), np.uint8)
    solid[..., :3] = varied
    solid[..., 3] = 255
    hidden = solid.copy()
    hidden[0, 0] = (255, 0, 255, 0)          # a vivid colour, fully clear
    a = tmp_path / "a.png"; b = tmp_path / "b.png"
    Image.fromarray(solid).save(a); Image.fromarray(hidden).save(b)
    first, _f = imagegamut.image_gamut(a)
    second, _g = imagegamut.image_gamut(b)
    assert second.volume == pytest.approx(first.volume, rel=1e-9)


def test_a_picture_of_one_flat_colour_is_refused_with_a_reason(tmp_path):
    flat = np.full((32, 32, 3), 128, np.uint8)
    with pytest.raises(imagegamut.UnreadableImage) as why:
        imagegamut.image_gamut(_write(tmp_path / "flat.png", flat))
    assert "enough different colours" in str(why.value)


def test_a_file_that_is_not_a_picture_says_so(tmp_path):
    bad = tmp_path / "not-a-picture.png"
    bad.write_bytes(b"this is not a picture at all")
    with pytest.raises(imagegamut.UnreadableImage) as why:
        imagegamut.image_gamut(bad)
    assert "could not be opened" in str(why.value)


def test_the_same_picture_twice_gives_the_same_answer(tmp_path):
    """A picture is sampled when it holds more colours than can be used, and
    a sample that wandered would make the volume wander with it."""
    path = _write(tmp_path / "big.png", _cube(40))
    a, _fa = imagegamut.image_gamut(path, most=5000)
    b, _fb = imagegamut.image_gamut(path, most=5000)
    assert a.volume == b.volume


def test_only_formats_this_machine_can_really_open_are_offered():
    got = imagegamut.readable_extensions()
    assert ".png" in got and ".jpg" in got and ".tif" in got
    assert len(got) > 20
    assert all(e.startswith(".") == True for e in got)


def test_how_much_of_a_picture_is_out_of_reach_is_weighted_by_the_picture():
    """THE NUMBER THAT WAS WRONG IN THE README, and by a factor of five.

    Coverage is a share of the SPACE a picture's colours enclose. Most of that
    space is unsaturated middle colour any paper reaches easily, while a
    photograph's pixels crowd towards the edges — so the two come apart badly.
    Measured on a real Display P3 photograph against a real glossy paper: 7.3%
    of the space it occupies is out of reach, and 39.8% of the actual picture
    is.

    Here that is made unmistakable: one colour well outside covers most of the
    frame, and a thousand colours inside cover a handful of pixels each.
    """
    import numpy as np

    from imagegamut import out_of_reach

    corners = np.array([[0.0, 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100]])
    inside = np.column_stack([np.linspace(5, 20, 999),
                              np.full(999, 3.0), np.full(999, 3.0)])
    outside = np.array([[50.0, 90.0, 90.0]])
    facts = {"lab": np.vstack([inside, outside]),
             "weights": np.concatenate([np.ones(999), [9000.0]])}
    lost = out_of_reach(facts, corners)

    assert lost["n_colours"] == 1
    # One colour in a thousand, and nine tenths of the picture.
    assert lost["of_its_colours"] == pytest.approx(1 / 1000, abs=1e-6)
    assert lost["of_the_picture"] == pytest.approx(0.9, abs=0.01)
    assert lost["worst"] > 5.0


def test_a_picture_entirely_within_reach_says_nothing_is_lost():
    import numpy as np

    from imagegamut import out_of_reach

    corners = np.array([[0.0, 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100]])
    facts = {"lab": np.column_stack([np.linspace(5, 20, 40),
                                     np.full(40, 3.0), np.full(40, 3.0)]),
             "weights": np.ones(40)}
    lost = out_of_reach(facts, corners)
    assert lost["of_the_picture"] == 0.0 and lost["n_colours"] == 0


def test_facts_without_the_colours_answer_nothing_rather_than_guess():
    """A saved state from a version that did not keep them must not invent a
    figure out of the shape alone — that is the very substitution this exists
    to stop."""
    from imagegamut import out_of_reach
    import numpy as np
    corners = np.array([[0.0, 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100]])
    assert out_of_reach({}, corners) is None
    assert out_of_reach({"lab": np.empty((0, 3)), "weights": np.empty(0)},
                        corners) is None


def test_the_counts_add_up_to_every_pixel_that_was_looked_at(tmp_path):
    """The weights ARE the picture: if they did not sum to the pixels, every
    share computed from them would be quietly wrong."""
    import numpy as np
    from PIL import Image

    from imagegamut import read_colours

    rng = np.random.default_rng(5)
    data = rng.integers(0, 255, size=(60, 80, 3), dtype=np.uint8)
    where = tmp_path / "p.png"
    Image.fromarray(data, "RGB").save(where)
    _values, _profile, looked_at, _space, weights = read_colours(where)
    assert looked_at == 60 * 80
    assert weights.sum() == looked_at


def test_a_picture_is_read_against_the_white_the_shape_was_built_under():
    """⚠ "82% OF YOUR PHOTOGRAPH CANNOT BE PRINTED" BECAME "3%" ON ONE NUDGE
    OF THE WHITE POINT, AND THE WORST DISTANCE WENT UP WHILE IT COLLAPSED.

    `colours_to_lab` says it in its own first line — "Turn a picture's colours
    into Lab **under D50**" — and it has no white-point parameter to be given
    another. The paper it is held against IS built under the chosen white. So
    a fixed D50 cloud was measured against a moving surface. Driven, one paper
    and one photograph open, nothing touched but White point:

        D50   82% out of reach, worst 6.8 ΔE   paper volume 702,327.4
        D65    3% out of reach, worst 9.2 ΔE   paper volume 643,384.8

    while the picture's 68,337 colours were byte-identical in both readings
    (L* mean 50.0335, a* 7.2314, b* 20.2943). A SMALLER paper covering far
    more of a fixed cloud is the signature of the two sides standing in
    different places.

    ⚠ THE WINDOW ALREADY HAD THE RULE, on its other cloud of fixed Lab
    colours. `_chart_lab` returns `self._chart_placed.under(...)` and says
    why: "Everything else in the window moves when the white point changes,
    and a chart left in the profile's own D50 would be drawn a few ΔE away
    from where the shapes around it moved to — the exact size of error that
    looks like a result." The picture's cloud was the one thing not moving.

    After: 82% under D50, D65 and back to D50, with the paper's volume moving
    702,327.4 -> 643,384.8 -> 702,327.4 beneath it. The worst distance still
    shifts a little (6.8 -> 5.8) — that is the rule working, not a leftover:
    ΔE is measured in whatever reference white the reader chose, and now both
    sides are in it.
    """
    import numpy as np

    from gamutview import lab_to_xyz
    from imagegamut import out_of_reach

    corners = np.array([[0.0, 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100]])
    inside = np.column_stack([np.linspace(5, 20, 99),
                              np.full(99, 3.0), np.full(99, 3.0)])
    outside = np.array([[50.0, 90.0, 90.0]])
    lab = np.vstack([inside, outside])
    weights = np.concatenate([np.ones(99), [900.0]])

    # Facts as they are written now: the same colours, kept as XYZ so they
    # can be read against any white.
    facts = {"lab": lab, "xyz": lab_to_xyz(lab, "D50"), "weights": weights}

    d50 = out_of_reach(facts, corners, white_point="D50")
    d65 = out_of_reach(facts, corners, white_point="D65")
    assert d50 is not None and d65 is not None

    # ⚠ THE COLOURS MOVE. If they did not, this test would pass over a
    # `white_point` argument that is accepted and ignored — which is the
    # shape of half the blind instruments in this project.
    assert d50["worst"] != d65["worst"], (
        "the white point reached nothing: `out_of_reach` is taking the "
        "argument and reading the D50 colours anyway")

    # AND OLDER FACTS, WITH NO XYZ, KEEP THE BEHAVIOUR THEY HAD rather than
    # being refused — the cache can hold a dict written before this.
    old = {"lab": lab, "weights": weights}
    assert out_of_reach(old, corners, white_point="D65")["worst"] == \
        out_of_reach(old, corners, white_point="D50")["worst"], (
        "facts with no XYZ started answering differently, so a cache entry "
        "from before this change now reads as a different picture")


def test_the_facts_keep_the_colours_as_xyz():
    """The half of the fix that lives in `image_gamut`: without this the
    re-reading above has nothing to re-read."""
    import pathlib
    import numpy as np

    from imagegamut import image_gamut

    root = pathlib.Path(__file__).resolve().parent.parent
    picture = next(iter(sorted((root / "docs").rglob("*.png"))), None)
    assert picture is not None, "no picture — this test is watching nothing"

    _gamut, facts = image_gamut(picture)
    assert "xyz" in facts, (
        "the picture's colours are kept only as Lab under D50, so they "
        "cannot be read against the white the reader chose")
    xyz = np.asarray(facts["xyz"])
    assert xyz.ndim == 2 and xyz.shape[1] == 3, xyz.shape
    assert xyz.shape[0] == np.asarray(facts["weights"]).shape[0], (
        "one weight per colour, or the picture-loss share is weighted by "
        "the wrong thing")
    assert np.isfinite(xyz).all()

    # ⚠ AND ONLY ONE COPY OF THE COLOURS IS KEPT. `facts` used to carry `lab`
    # as well, under D50, and it was overwritten one line after it was read
    # for every picture built — a third float64 (N, 3) array per photograph
    # with no reader. Four showcase pictures held at once went from 2.26 MB
    # to 3.96 MB, +75%, for nothing.
    assert "lab" not in facts, (
        "the picture's colours are kept twice again: `lab` is read and then "
        "replaced by the re-referenced `xyz` before it is used")


def test_a_picture_is_read_against_the_white_the_other_side_stands_in():
    """⚠ TWO SIDES, TWO REFERENCES, AND ONLY ONE OF THEM MOVES.

    Making the picture's colours follow the White point fixed the case where
    the other side is a MEASUREMENT and broke the case where it is a PROFILE:
    `icc_gamut`/`gam_gamut` return the file's own Lab untouched when the space
    is CIELAB, so a profile is fixed at D50 whatever is asked for. Driven on
    one picture against `Glossy-paper.icc`, D50 -> D65:

        before   68% / 3.4 ΔE  ->  94% / 5.2 ΔE
        after    68% / 3.4 ΔE  ->  68% / 3.4 ΔE

    Swept over 90 picture/profile pairs the largest movement introduced was
    25.7 percentage points, and not one pair moved before while standing
    still after.

    So the white handed to `out_of_reach` is the one the OTHER SIDE actually
    stands in — a fact that can be looked up, rather than a preference
    between two wrong answers.
    """
    import pathlib
    from types import SimpleNamespace as NS
    import gamut_app

    win = NS(_white=NS(currentData=lambda: "D65"))
    ask = gamut_app.GamutApp._white_a_shape_stands_in.__get__(
        win, gamut_app.GamutApp)
    in_lab = NS(space="lab")

    assert ask(in_lab, pathlib.Path("/x/p.icc")) == "D50", (
        "a profile's CIELAB is the file's own D50-referred Lab; reading the "
        "picture against D65 compares two different references")
    assert ask(in_lab, pathlib.Path("/x/p.gam")) == "D50"
    assert ask(in_lab, pathlib.Path("/x/p.ti3")) == "D65", (
        "a measurement IS re-referenced by `read_ti3`, so the picture must "
        "follow the control to stand beside it")
    # ⚠ A PICTURE IS D50 TOO, AND THIS LINE SAID D65 WITH NO REASON BESIDE
    # IT — the one assertion in the list that was never justified, and the one
    # that was wrong. `image_gamut` is handed `white_point`, which makes it
    # LOOK as though the shape follows the control; it passes Lab in, and
    # `build_gamut(input_space="lab")` takes those numbers as given. Built
    # under both whites: bit-identical, 0 of 406 vertices moved, against a
    # measurement's 675 of 675 at up to 17.046 ΔE.
    assert ask(in_lab, pathlib.Path("/x/p.png")) == "D50", (
        "a picture is read against the control's white while its own shape "
        "is fixed at D50 — two photographs then disagree about whether every "
        "colour fits, on a nudge of a control that says nothing about them")

    # A shape with no file — a colour space, the visible solid — and a shape
    # built in another space both follow the control.
    assert ask(in_lab, None) == "D65"
    assert ask(NS(space="luv"), pathlib.Path("/x/p.icc")) == "D65", (
        "outside CIELAB a profile IS converted under the chosen white, so "
        "pinning D50 there would reintroduce the mismatch the other way")


@pytest.mark.slow
def test_which_kinds_really_move_with_the_white_point(tmp_path):
    """⚠ THE TABLE IN `_white_a_shape_stands_in` IS A CLAIM ABOUT FIVE
    BUILDERS, AND ONE ROW OF IT WAS WRONG.

    It said a picture "moves" with the white point, because `image_gamut` is
    HANDED `white_point` — which makes it look as though it follows the
    control. It passes Lab in, and `build_gamut(input_space="lab")` takes
    those numbers as given, so the shape is the same under any white.

    With the row wrong, two photographs held against each other read

        D50   'Every colour in A is one B holds.'
        D65   '1% of A itself is out of reach of B … worst 2.7 ΔE'

    while the coverage line an inch above did not move — the same
    two-sentences-an-inch-apart fault the helper exists to prevent.

    So the table is measured here rather than believed. Built under D50 and
    D65 and compared vertex by vertex:

        measurement  worst 17.046 ΔE, 675 of 675 moved
        picture      BIT-IDENTICAL, 0 of 406 moved
        profile      BIT-IDENTICAL
    """
    import pathlib
    import numpy as np
    from imagegamut import image_gamut
    from references import icc_gamut
    from ti3gamut import read_measurement
    from gamutview import build_gamut

    root = pathlib.Path(__file__).resolve().parent.parent

    def verts(g):
        return np.asarray(g.vertices, float)

    def same(a, b):
        return verts(a).shape == verts(b).shape and np.array_equal(verts(a),
                                                                   verts(b))

    picture = next(iter(sorted((root / "docs").rglob("*.png"))), None)
    assert picture is not None
    a, _f = image_gamut(picture, white_point="D50", space="lab")
    b, _f = image_gamut(picture, white_point="D65", space="lab")
    assert same(a, b), (
        "a picture's CIELAB now moves with the white point — if that is "
        "deliberate, its row in `_white_a_shape_stands_in` must move to the "
        "`-> moves` group with it, or the picture-loss sentence will swing "
        "on a nudge of a control that says nothing about photographs")

    prof = root / "demo" / "Glossy-paper.icc"
    assert same(icc_gamut(prof, white_point="D50", space="lab"),
                icc_gamut(prof, white_point="D65", space="lab")), (
        "a profile's CIELAB now moves — its row must move too")

    # AND THE CONTROL: one kind really does move, or this test would pass on
    # a build_gamut that had stopped honouring the white point at all.
    chart = root / "demo" / "Glossy-paper.ti3"
    ma = read_measurement(chart, "D50", False)
    mb = read_measurement(chart, "D65", False)
    ga = build_gamut(ma.lab, ma.device, input_space="lab", space="lab",
                     white_point="D50")
    gb = build_gamut(mb.lab, mb.device, input_space="lab", space="lab",
                     white_point="D65")
    assert not same(ga, gb), (
        "a measurement's CIELAB no longer moves with the white point either, "
        "so this test is comparing a builder that ignores its argument")
