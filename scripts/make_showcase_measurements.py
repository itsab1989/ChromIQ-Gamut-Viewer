"""Four invented papers, derived from the demo measurements, for the showcase.

    python scripts/make_showcase_measurements.py [--out demo/showcase]

WHY DERIVED RATHER THAN INVENTED FRESH. The two committed demo measurements
(`demo/Glossy-paper.ti3`, `demo/Matte-paper.ti3`) are 1168 real patch
positions with a plausible paper's shape; everything ArgyllCMS-flavoured
about them is already right. Each showcase paper below starts from one of
them and changes ONLY the part its story needs -- the same rule
`make_demo_profiles.py` follows, and for the same reason: the rest of the
file stays exactly as trustworthy as the one it came from.

NEUTRAL NAMES, ALWAYS. These are imaginary papers with imaginary names.
Nothing here describes, or is named after, any real paper, printer, maker or
person.

WHAT EACH PAPER IS FOR, and the story it must be able to tell:

  baryta gloss 315gsm          the reference: the glossy demo paper renamed.
  heavy matte cotton 310gsm    holds LESS overall but still pokes OUT of the
                               gloss in one hue region -- so "which fits
                               inside which" has two different answers, and
                               neither is 100%.
  soft-white rag 300gsm        encloses the SAME volume as the matte cotton
                               (within 2%) with a different shape: the
                               gloss's deep shadows kept, the chroma pulled
                               in until the volumes agree. The pair is what
                               a single "gamut size" number cannot tell
                               apart. Derived from the GLOSS, not the matte
                               -- measured first: the matte's shadow floor
                               is L* 12.7 and no believable bending of it
                               reaches the deep blacks this story needs,
                               while the gloss starts at L* 4.0 and only its
                               chroma has to move.
  baryta gloss 315gsm, a year on the shelf
                               the gloss with its blues and violets partly
                               gone and the paper white slightly warmed --
                               the shape of an optical brightener fading.

The spectral bands are dropped: the viewer reads device values and XYZ, and
the spectra are five sixths of the source files' size. Each file is ~150 kB.

EVERY PAPER CHECKS ITS OWN STORY before anything is written, with the
application's own arithmetic (`build_gamut`, `coverage`): a demo that has
quietly stopped demonstrating its point is worse than none. Exit 1 if any
story fails.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "python"))

import cgats                                    # noqa: E402
from gamutview import (build_gamut, coverage, lab_to_xyz,       # noqa: E402
                       outside_of, xyz_to_lab)

GLOSSY = ROOT / "demo" / "Glossy-paper.ti3"
MATTE = ROOT / "demo" / "Matte-paper.ti3"

HEADER = """CTI3

DESCRIPTOR "Invented paper for the showcase — derived from the demo measurement"
ORIGINATOR "scripts/make_showcase_measurements.py"
CREATED "Demo"
DEVICE_CLASS "OUTPUT"
COLOR_REP "iRGB_XYZ"

NUMBER_OF_FIELDS 8
BEGIN_DATA_FORMAT
SAMPLE_ID SAMPLE_LOC RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z
END_DATA_FORMAT

NUMBER_OF_SETS {n}
BEGIN_DATA
"""


def read_raw(path: pathlib.Path):
    """(ids, locations, rgb (N,3) 0..100, xyz (N,3) 0..100) from a .ti3."""
    tables = cgats.read_tables(path.read_text(errors="replace"))
    for table in tables:
        if table.has("XYZ_X", "XYZ_Y", "XYZ_Z"):
            break
    else:
        raise SystemExit(f"{path.name} has no XYZ columns")
    ids = [r[list(table.columns).index("SAMPLE_ID")] for r in table.rows]
    locs = [r[list(table.columns).index("SAMPLE_LOC")] for r in table.rows]
    rgb = np.column_stack([table.numbers(c)[:, 0]
                           for c in ("RGB_R", "RGB_G", "RGB_B")])
    xyz = np.column_stack([table.numbers(c)[:, 0]
                           for c in ("XYZ_X", "XYZ_Y", "XYZ_Z")])
    return ids, locs, rgb, xyz


def write_ti3(path: pathlib.Path, ids, locs, rgb, xyz) -> None:
    rows = []
    for i in range(len(ids)):
        loc = locs[i] if str(locs[i]).startswith('"') else f'"{locs[i]}"'
        rows.append(f"{ids[i]} {loc} "
                    f"{rgb[i, 0]:.5f} {rgb[i, 1]:.5f} {rgb[i, 2]:.5f} "
                    f"{xyz[i, 0]:.6f} {xyz[i, 1]:.6f} {xyz[i, 2]:.6f} ")
    path.write_text(HEADER.format(n=len(ids)) + "\n".join(rows)
                    + "\nEND_DATA\n", encoding="utf-8")


def hue_weight(lab: np.ndarray, centre: float, width: float) -> np.ndarray:
    """1 in the middle of a hue band, easing to 0 at its edges.

    A hard-edged band would put a crease in the gamut surface exactly where
    two neighbouring patches straddle the edge; a raised cosine keeps the
    derived surface as smooth as a paper's really is.
    """
    hue = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360.0
    away = np.abs((hue - centre + 180.0) % 360.0 - 180.0)
    w = np.zeros(len(lab))
    inside = away < width
    w[inside] = 0.5 * (1.0 + np.cos(np.pi * away[inside] / width))
    return w


def scale_chroma(lab: np.ndarray, factor) -> np.ndarray:
    out = lab.copy()
    out[:, 1] *= factor
    out[:, 2] *= factor
    return out


def matte_cotton(lab: np.ndarray) -> np.ndarray:
    """The matte with one hue region lifted a little past the gloss.

    A tenth more chroma at the band's centre, fading to nothing at its
    edges -- enough that a few percent of this paper stands outside the
    gloss, which is the whole story: neither paper holds the other.
    """
    lift = 1.0 + 0.14 * hue_weight(lab, centre=150.0, width=70.0)
    return scale_chroma(lab, lift)


def soft_rag(lab: np.ndarray, chroma: float) -> np.ndarray:
    """The gloss's shape with its chroma pulled in; volume tuned outside.

    Applied to the GLOSS's Lab. Lightness is left alone -- the deep blacks
    ARE the story -- and the chroma scale is what the bisection below moves
    until this paper encloses the same volume as the matte cotton.
    """
    return scale_chroma(lab, chroma)


def a_year_on_the_shelf(lab: np.ndarray) -> np.ndarray:
    """What a fading brightener does: blues and violets pull in, white warms."""
    keep = 1.0 - 0.22 * hue_weight(lab, centre=280.0, width=80.0)
    out = scale_chroma(lab, keep)
    near_white = np.clip((out[:, 0] - 85.0) / 15.0, 0.0, 1.0)
    out[:, 2] += 1.6 * near_white          # towards yellow
    out[:, 0] -= 0.9 * near_white          # and very slightly dimmer
    return out


failures: list[str] = []


def check(claim: str, ok: bool, detail: str = "") -> None:
    mark = "  ok  " if ok else " FAIL "
    print(f"  [{mark}] {claim}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(claim + (f" ({detail})" if detail else ""))


def main(out: pathlib.Path) -> int:
    out.mkdir(parents=True, exist_ok=True)

    ids_g, locs_g, rgb_g, xyz_g = read_raw(GLOSSY)
    ids_m, locs_m, rgb_m, xyz_m = read_raw(MATTE)
    lab_g = xyz_to_lab(xyz_g / 100.0, "D50")
    lab_m = xyz_to_lab(xyz_m / 100.0, "D50")

    def gamut(lab):
        return build_gamut(lab, rgb_g / 100.0, input_space="lab", space="lab")

    print("\nderiving the papers")
    papers: dict[str, np.ndarray] = {}
    papers["baryta gloss 315gsm"] = lab_g
    papers["heavy matte cotton 310gsm"] = matte_cotton(lab_m)
    papers["baryta gloss 315gsm, a year on the shelf"] = \
        a_year_on_the_shelf(lab_g)

    # THE RAG'S VOLUME IS TUNED, NOT HOPED FOR. Its story is "same size,
    # different shape", so its chroma scale is bisected until its volume is
    # within a percent of the matte cotton's. The first version of this
    # guessed a shadow-deepening constant instead and bisected the matte's
    # chroma -- which converged on a scale of 1.0 and a rag that was WIDER
    # than the cotton in the mid-tones, failing its own story. Deepening a
    # shadow floor adds almost no volume, so the bisection had nothing to
    # trade against.
    matte_vol = gamut(papers["heavy matte cotton 310gsm"]).volume
    lo, hi = 0.80, 1.00
    rag = None
    for _ in range(18):
        mid = (lo + hi) / 2.0
        rag = soft_rag(lab_g, mid)
        if gamut(rag).volume < matte_vol:
            lo = mid
        else:
            hi = mid
    papers["soft-white rag 300gsm"] = rag

    gamuts = {name: gamut(lab) for name, lab in papers.items()}
    for name, g in gamuts.items():
        print(f"    {name:45s} {g.volume:10,.0f} cubic Lab units")

    print("\nthe stories, checked with the viewer's own arithmetic")
    a = gamuts["baryta gloss 315gsm"]
    b = gamuts["heavy matte cotton 310gsm"]
    c = gamuts["soft-white rag 300gsm"]
    d = gamuts["baryta gloss 315gsm, a year on the shelf"]

    # S1 — the two directions must have two different answers, neither 100%.
    b_in_a = coverage(b, a)[0]
    a_in_b = coverage(a, b)[0]
    check("most of the matte cotton fits inside the gloss, not all of it",
          0.90 <= b_in_a <= 0.995, f"{100 * b_in_a:.1f}%")
    check("the other way round the answer is clearly different",
          a_in_b <= b_in_a - 0.08,
          f"{100 * a_in_b:.1f}% against {100 * b_in_a:.1f}%")

    # S8 — same volume, different shape.
    vol_gap = abs(b.volume - c.volume) / max(b.volume, c.volume)
    check("the rag and the matte cotton enclose the same volume",
          vol_gap <= 0.02, f"{100 * vol_gap:.2f}% apart")
    dark_b = float(np.min(b.vertices[:, 0]))
    dark_c = float(np.min(c.vertices[:, 0]))
    check("the rag goes deeper in the shadows",
          dark_c <= dark_b - 1.5, f"L* {dark_c:.1f} against {dark_b:.1f}")

    def widest_mid(g):
        mid = g.vertices[(g.vertices[:, 0] >= 45) & (g.vertices[:, 0] <= 65)]
        return float(np.max(np.hypot(mid[:, 1], mid[:, 2])))

    check("and the matte cotton is the wider of the two in the mid-tones",
          widest_mid(b) >= widest_mid(c) + 3.0,
          f"chroma {widest_mid(b):.1f} against {widest_mid(c):.1f}")

    # S4 — the year on the shelf loses a visible share, mostly blue-violet.
    still = coverage(a, d)[0]
    check("the shelf year costs the gloss a visible share of its colour",
          0.55 <= still <= 0.92, f"{100 * (1 - still):.1f}% no longer reached")
    gone = outside_of(a, d)
    hue = np.degrees(np.arctan2(a.vertices[gone, 2],
                                a.vertices[gone, 1])) % 360.0
    in_band = np.mean((hue >= 200.0) & (hue <= 340.0)) if gone.any() else 0.0
    check("and what is gone is mostly in the blues and violets",
          gone.any() and in_band >= 0.55,
          f"{100 * in_band:.0f}% of the lost surface is in that hue range")

    print("\nwriting")
    sources = {
        "baryta gloss 315gsm": (ids_g, locs_g, rgb_g),
        "heavy matte cotton 310gsm": (ids_m, locs_m, rgb_m),
        "soft-white rag 300gsm": (ids_g, locs_g, rgb_g),
        "baryta gloss 315gsm, a year on the shelf": (ids_g, locs_g, rgb_g),
    }
    import ti3gamut
    for name, lab in papers.items():
        ids, locs, rgb = sources[name]
        xyz = lab_to_xyz(lab, "D50") * 100.0
        path = out / f"{name}.ti3"
        write_ti3(path, ids, locs, rgb, xyz)
        # AND EACH FILE IS READ BACK THROUGH THE REAL READER, because the
        # showcase opens these through the window and a file only this
        # script can parse would demo nothing.
        again = ti3gamut.read_ti3(path)
        check(f"{path.name} reads back through the viewer's own reader",
              again.n_patches == len(ids) and again.device is not None,
              f"{again.n_patches} patches, {path.stat().st_size / 1024:.0f} kB")
        drift = float(np.max(np.abs(again.lab - lab)))
        check(f"{path.name} carries the Lab values it was built from",
              drift < 0.01, f"worst round-trip error {drift:.4f}")

    print()
    if failures:
        for f in failures:
            print(f"  - {f}")
        print(f"\n{len(failures)} story/stories not held. Nothing to ship.")
        return 1
    print(f"4 papers written to {out}, every story checked.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "demo" / "showcase"))
    raise SystemExit(main(pathlib.Path(ap.parse_args().out)))
