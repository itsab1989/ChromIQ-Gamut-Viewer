"""The colours in a picture, as a shape — so you can see whether they print.

THE QUESTION THIS ANSWERS
-------------------------
"Will this photograph survive on that paper?" Open the image and open the
measurement, and the answer is the coverage figure already on screen: how much
of the picture's colour fits inside what the paper can print, and — drawn on
the shape — exactly which colours do not.

WHAT AN IMAGE'S GAMUT IS, AND IS NOT
------------------------------------
It is **the colours that are actually in this picture**. Nothing more.

* It is NOT what the camera could capture, nor what the file format could
  hold. A photograph of a grey morning has a small gamut because the morning
  was grey, not because anything failed.
* It has no device axes. A chart knows which ink values made each patch, so
  its boundary can follow the real dents; an image knows only its colours, so
  the honest shape is the skin around them.
* A big gamut is not a good picture and a small one is not a bad one. This
  says what is there, not whether it is any good.

COLOUR SCIENCE, STATED PLAINLY
------------------------------
An image's numbers mean nothing on their own -- "255, 0, 0" is only a red once
you know which red. So:

* **If the file carries an ICC profile, that profile is used**, evaluated the
  same way any other profile is here.
* **If it does not, sRGB is assumed, and the application says so.** That is
  the convention every browser follows and it is right far more often than it
  is wrong -- but it is an assumption, it changes the answer, and quietly
  making it would be exactly the kind of unstated guess this application
  exists to avoid.
* Everything ends up as Lab under D50, like every other shape here, so the
  comparison is like for like.

ONE NUMBER THAT LOOKS WRONG AND IS NOT
--------------------------------------
A picture containing every colour of the sRGB cube measures about 9% larger
than the sRGB shape itself -- 906 000 against 832 000, measured. Neither is
mistaken. sRGB is a device space, so its shape is built from the six faces of
its cube and follows their curve; a picture has no device values, so its shape
is a skin stretched over the colours, and a skin bridges straight across every
place the true surface curves inwards.

It matters when reading coverage: a picture's shape is the smallest one that
holds all of its colours, and never smaller than the colours themselves.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

#: How many distinct colours are kept at most. A photograph can hold millions;
#: the shape they enclose is decided by the outermost few thousand, and the
#: hull of 300 000 points is computed in well under a second. Sampled with a
#: fixed seed, so opening the same picture twice gives the same answer.
MOST_COLOURS = 300_000
_SEED = 12345


class UnreadableImage(Exception):
    """This file cannot be turned into colours, with a reason worth reading."""


def _register_extra_formats() -> None:
    """Teach Pillow the formats it does not know on its own.

    HEIC is what every iPhone photograph is, and JPEG XL is what a good deal
    of archive material is becoming. Both arrive as plug-ins; if one is
    missing the rest still work, and the file dialog simply will not offer it.
    """
    for module, hook in (("pillow_heif", "register_heif_opener"),
                         ("pillow_avif", None),
                         ("pillow_jxl", None)):
        try:
            loaded = __import__(module)
            if hook and hasattr(loaded, hook):
                getattr(loaded, hook)()
        except Exception:                      # noqa: BLE001 — never fatal
            continue


def readable_extensions() -> list:
    """Every extension that can actually be opened on THIS machine.

    Asked of the library rather than listed by hand, so the file dialog can
    never offer something that will fail, and never hide something that works.
    """
    from PIL import Image

    _register_extra_formats()
    Image.init()
    return sorted({ext.lower() for ext, name in Image.EXTENSION.items()
                   if name in Image.OPEN})


def describe_colour_handling(profile: "bytes | None") -> str:
    """What was assumed, in words, for showing beside the picture."""
    if profile:
        return ("Its own colour profile was used, so these are the colours "
                "the picture really holds.")
    return ("No colour profile in the file, so sRGB was assumed — the usual "
            "convention, and right far more often than not. If it was really "
            "made in a wider space such as Adobe RGB, the shape shown here is "
            "smaller than the truth.")


def read_colours(path, most: int = MOST_COLOURS):
    """The distinct colours in a picture, and the profile it carried.

    Returns (values 0..1 of shape (N, channels), profile bytes or None, how
    many pixels were looked at, the colour space name, and how many pixels
    hold each of those colours).

    THE COUNTS MATTER AS MUCH AS THE COLOURS. A photograph's rarest colour and
    its commonest count the same towards the shape it encloses, and nothing
    like the same towards "how much of this picture will print".
    """
    from PIL import Image

    _register_extra_formats()
    path = Path(path)
    try:
        with Image.open(path) as opened:
            opened.load()
            profile = opened.info.get("icc_profile")
            mode = opened.mode
            if mode in ("RGBA", "LA", "PA", "P"):
                # Transparency is not a colour. A pixel nobody can see must
                # not push the shape outwards, so anything fully clear is
                # dropped and the rest is used as it stands.
                opened = opened.convert("RGBA")
                data = np.asarray(opened, dtype=np.uint8)
                flat = data.reshape(-1, 4)
                flat = flat[flat[:, 3] > 0][:, :3]
                depth, channels, space = 255.0, 3, "RGB"
            elif mode == "CMYK":
                data = np.asarray(opened, dtype=np.uint8)
                flat = data.reshape(-1, 4)
                depth, channels, space = 255.0, 4, "CMYK"
            elif mode in ("I;16", "I;16B", "I;16L", "I"):
                data = np.asarray(opened, dtype=np.uint32)
                flat = np.repeat(data.reshape(-1, 1), 3, axis=1)
                depth, channels, space = 65535.0, 3, "GREY"
            elif mode == "L":
                data = np.asarray(opened.convert("RGB"), dtype=np.uint8)
                flat = data.reshape(-1, 3)
                depth, channels, space = 255.0, 3, "GREY"
            else:
                opened = opened.convert("RGB")
                data = np.asarray(opened, dtype=np.uint8)
                flat = data.reshape(-1, 3)
                depth, channels, space = 255.0, 3, "RGB"
    except UnreadableImage:
        raise
    except Exception as exc:                   # noqa: BLE001 — say what, not how
        raise UnreadableImage(
            f"{path.name} could not be opened as a picture: {exc}") from exc

    looked_at = int(flat.shape[0])
    if looked_at == 0:
        raise UnreadableImage(
            f"{path.name} has no visible pixels — every one of them is "
            "completely see-through, so there are no colours to show.")

    # The distinct colours, exactly: a photograph repeats most of its pixels
    # many times over and only the different ones can change the shape. How
    # often each one occurs is kept alongside, because that is what turns
    # "which colours are out of reach" into "how much of the picture is".
    unique, counts = np.unique(flat, axis=0, return_counts=True)
    if len(unique) > most:
        picked = np.sort(np.random.default_rng(_SEED).choice(
            len(unique), most, replace=False))
        unique, counts = unique[picked], counts[picked]
    return (unique.astype(float) / depth, profile, looked_at, space,
            counts.astype(float))


def colours_to_lab(values: np.ndarray, profile: "bytes | None",
                   space: str = "RGB") -> np.ndarray:
    """Turn a picture's colours into Lab under D50.

    Through the file's own profile when it has one -- read by the same code
    that reads any other profile here -- and through sRGB when it does not.
    """
    from gamutview import xyz_to_lab

    if profile:
        try:
            return _through_profile(values, profile)
        except Exception:                      # noqa: BLE001
            pass                               # fall back rather than refuse
    if space == "CMYK":
        raise UnreadableImage(
            "This picture is in CMYK and carries no colour profile, so there "
            "is no way to know which inks were meant. Open one that has its "
            "profile embedded, or convert it to RGB first.")
    return xyz_to_lab(_srgb_to_xyz(values), "D50")


def _through_profile(values: np.ndarray, profile: bytes) -> np.ndarray:
    """The picture's own profile, evaluated the way every profile is here."""
    import tempfile

    import icc_read
    from gamutview import xyz_to_lab

    with tempfile.NamedTemporaryFile(suffix=".icc", delete=False) as handle:
        handle.write(profile)
        where = Path(handle.name)
    try:
        tags = icc_read.read_tags(where)
        head = icc_read.describe(where)
        table = tags.get("A2B1") or tags.get("A2B0")
        if table is not None:
            xyz = icc_read._lut_to_pcs(table, values, head["pcs"])
        else:
            xyz = icc_read._matrix_to_pcs(tags, values)
    finally:
        where.unlink(missing_ok=True)
    return xyz_to_lab(xyz, icc_read.PCS_WHITE)


def _srgb_to_xyz(values: np.ndarray) -> np.ndarray:
    """sRGB, assumed, adapted to D50 the honest way rather than by pretending.

    Built from the same primaries the sRGB comparison uses, so a picture and
    the sRGB shape it is measured against cannot disagree about what sRGB is.
    """
    from gamutview import _as_white_point, _bradford_adapt
    from references import REFERENCE_SPACES, _rgb_to_xyz_matrix

    spec = REFERENCE_SPACES["sRGB"]
    values = np.clip(np.asarray(values, dtype=float), 0.0, 1.0)
    linear = np.where(values <= 0.04045, values / 12.92,
                      ((values + 0.055) / 1.055) ** 2.4)
    xyz = linear @ _rgb_to_xyz_matrix(spec["primaries"], spec["white"]).T
    return xyz @ _bradford_adapt(_as_white_point("D65"),
                                 _as_white_point("D50")).T


def image_gamut(path, *, white_point: str = "D50", space: str = "lab",
                most: int = MOST_COLOURS, **_ignored):
    """The shape the colours of a picture enclose, and what it was read as.

    Returns (gamut, facts). The facts come back beside it rather than attached
    to it because a Gamut is frozen -- and they are worth having: how many
    pixels were looked at, how many different colours were found, and whether
    the picture said which colours those were or it had to be assumed.

    A skin around them, never a dented boundary: an image carries no device
    values, so there is nothing to say which of its colours sit on an edge and
    which are simply absent. Claiming a dent that was never measured would be
    inventing detail.
    """
    from gamutview import build_gamut

    values, profile, looked_at, kind, weights = read_colours(path, most)
    lab = colours_to_lab(values, profile, kind)
    good = np.isfinite(lab).all(axis=1)
    if good.sum() < 4:
        raise UnreadableImage(
            f"{Path(path).name} does not hold enough different colours to "
            "make a shape — at least four are needed, and a picture of one "
            "flat colour encloses nothing at all.")
    gamut = build_gamut(lab[good], input_space="lab", white_point=white_point,
                        space=space)
    facts = {"pixels": looked_at, "colours": int(good.sum()),
             "profile": bool(profile), "space": kind,
             "note": describe_colour_handling(profile),
             # THE COLOURS THEMSELVES, AND HOW MUCH OF THE PICTURE EACH IS.
             # Kept because the shape alone cannot answer the question people
             # actually ask. Coverage is a fraction of the SPACE a picture's
             # colours enclose, and most of that space is unsaturated middle
             # colour that any paper reaches easily, while a photograph's
             # pixels crowd towards the edge. Measured on one real photograph
             # against one real paper: 7.3% of the space it occupies is out of
             # reach, and 39.8% of the actual picture is. Reporting only the
             # first is comforting and wrong.
             "lab": lab[good], "weights": weights[good]}
    return gamut, facts


def out_of_reach(facts: dict, gamut, *, tolerance: float = 1.0) -> "dict | None":
    """How much of a picture a shape cannot print — by pixel, not by volume.

    ⚠ RAISES `chart.NotInCIELAB` when *gamut* was not built in CIELAB. This
    used to be impossible to notice: the arithmetic reads vertices raw, so a
    shape in CIELUV or CIE XYZ produced a confident figure answering a
    different question — a photograph read 0%, 1% and 100% out of reach with
    nothing but the drawing changed. `chart.outside_report` refuses it now,
    and this inherits the refusal. `None` is still returned for a picture
    with nothing measurable in it.

    Returns the share of the picture (weighted by how many pixels hold each
    colour), the share of its distinct colours, and the worst distance outside
    in ΔE2000. None when the facts came from a version that did not keep the
    colours.

    *tolerance* is the same edge band the chart check uses: a colour a fraction
    of a ΔE outside the surface is on it, and the surface is only known as
    finely as it was sampled.
    """
    import chart

    lab = facts.get("lab")
    weights = facts.get("weights")
    if lab is None or weights is None or not len(lab):
        return None
    report = chart.outside_report(lab, gamut, tolerance=tolerance)
    total = float(weights.sum()) or 1.0
    return {"of_the_picture": float(weights[report.beyond].sum()) / total,
            "of_its_colours": float(report.beyond.mean()),
            "worst": report.worst,
            "n_colours": int(report.n_beyond)}
