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
