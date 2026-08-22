"""Shapes built to break the lid, written as measurements the window can open.

    python scripts/make_awkward_shapes.py [folder]     # default: scratch/awkward

WHY THESE EXIST. The lid over a cut ("Close where it is cut") is easy to make
look right on two ordinary papers, which overlap in one fat region and leave a
single tidy hole. None of the ways it can go wrong appear there. Each shape
here is awkward in a NAMED way, so that a failure has a cause rather than a
mystery:

    ball                 an ordinary closed shape, the control
    ball-just-poking     a small shape off to one side, so the middle is
                         OUTSIDE it -- the lid is built by sliding corners
                         down their rays onto the other shape, which means
                         nothing if that shape does not wrap the middle
    ball-well-inside     wholly inside the other: nothing is cut, so there is
                         no hole and there must be no lid
    two-lobes            a peanut, so a ball through its waist cuts TWO
                         separate holes -- one lid per hole, or a lid that
                         wrongly bridges them
    ball-with-a-dent     a dent deep enough that the rim of the cut is not
                         convex, which a lid made of a flat disc would show
    pancake / column     flat against tall: they cross in a ring, so the
                         opening is an annulus rather than a cap

They are written with LAB_L/A/B rather than spectra, which the reader accepts
(see ti3gamut._LAB), so each file is small and every number in it is chosen
here rather than measured from anything.

DETERMINISTIC. Fixed seeds, so the same shapes come back every time and a
difference in a result is a difference in the code.
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
MIDDLE = np.array([50.0, 0.0, 0.0])


def _ball(n: int = 1600, seed: int = 1) -> np.ndarray:
    """Directions spread evenly over a sphere, the same ones every time."""
    rng = np.random.default_rng(seed)
    u = rng.normal(size=(n, 3))
    return u / np.linalg.norm(u, axis=1)[:, None]


def write(folder: pathlib.Path, name: str, lab) -> int:
    """One measurement file, in the smallest form the reader accepts."""
    lab = np.asarray(lab, float)
    rows = []
    for i, (light, a, b) in enumerate(lab, 1):
        red = 100 * (0.5 + 0.5 * np.sin(i))
        green = 100 * (0.5 + 0.5 * np.cos(i * 1.7))
        blue = 100 * (0.5 + 0.5 * np.sin(i * 2.3))
        rows.append(f"{i} {red:.4f} {green:.4f} {blue:.4f} "
                    f"{light:.4f} {a:.4f} {b:.4f}")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.ti3").write_text(
        "CTI3\n\n"
        f'DESCRIPTOR "{name} — an awkward shape for the lid"\n'
        'ORIGINATOR "make_awkward_shapes.py"\n'
        'CREATED "synthetic"\n'
        'DEVICE_CLASS "OUTPUT"\n'
        'COLOR_REP "RGB_LAB"\n\n'
        "NUMBER_OF_FIELDS 7\n"
        "BEGIN_DATA_FORMAT\n"
        "SAMPLE_ID RGB_R RGB_G RGB_B LAB_L LAB_A LAB_B\n"
        "END_DATA_FORMAT\n\n"
        f"NUMBER_OF_SETS {len(rows)}\n"
        "BEGIN_DATA\n" + "\n".join(rows) + "\nEND_DATA\n")
    return len(rows)


def make(folder) -> dict:
    """Every awkward shape, by name, with how many patches each holds."""
    folder = pathlib.Path(folder)
    u = _ball()
    made = {}
    made["ball"] = write(folder, "ball", MIDDLE + u * np.array([40, 45, 45]))
    made["ball-just-poking"] = write(
        folder, "ball-just-poking",
        MIDDLE + np.array([0, 44, 0]) + u * np.array([40, 45, 45]) * 0.30)
    made["ball-well-inside"] = write(
        folder, "ball-well-inside", MIDDLE + u * np.array([18, 20, 20]))
    lobes = np.vstack([
        MIDDLE + np.array([0, -34, 0]) + _ball(900, 2) * np.array([26, 20, 20]),
        MIDDLE + np.array([0, 34, 0]) + _ball(900, 3) * np.array([26, 20, 20])])
    made["two-lobes"] = write(folder, "two-lobes", lobes)
    dent = 1.0 - 0.42 * np.exp(
        -((u - np.array([0.2, 0.95, 0.1])) ** 2).sum(1) * 6.0)
    made["ball-with-a-dent"] = write(
        folder, "ball-with-a-dent",
        MIDDLE + u * dent[:, None] * np.array([40, 45, 45]))
    made["pancake"] = write(folder, "pancake", MIDDLE + u * np.array([10, 46, 46]))
    made["column"] = write(folder, "column", MIDDLE + u * np.array([46, 12, 12]))
    return made


def main() -> int:
    where = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else (
        HERE.parent.parent / "scratch" / "awkward")
    for name, count in make(where).items():
        print(f"  {name:20s} {count:5d} patches")
    print(f"\n  written to {where}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
