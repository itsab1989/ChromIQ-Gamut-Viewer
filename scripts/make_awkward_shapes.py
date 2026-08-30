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
    ball-shifted         the same ball, moved sideways: two equal spheres
                         cross in a perfect CIRCLE, so any tooth or flag on
                         that seam is the drawing's and not the data's
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


def _cube_surface(per_side: int = 26) -> np.ndarray:
    """Points all over the surface of a cube, as unit offsets in -1..1.

    ⚠ A CUBE IS THE INSTRUMENT FOR ANYTHING ABOUT THE WALLS, and that is why
    it is here. Basti asked for "a cube like shape that in turn fills most of
    the room so you can easily spot the wall when it is in a place where it
    does not belong". A ball is the worst possible shape for that question:
    it is round, so it never lines up with anything, it leaves most of the box
    empty, and a wall in the wrong place merely looks like more background.

    A cube's faces are FLAT and PARALLEL TO THE WALLS. Fill the room with one
    and the answer needs no pixel counting: a wall that belongs behind the
    shape is hidden completely, and a wall painted on the camera's own side is
    a grey panel lying across a flat sheet of colour, which anybody can see at
    a glance and in one still frame.
    """
    t = np.linspace(-1.0, 1.0, per_side)
    x, y = np.meshgrid(t, t)
    x, y = x.ravel(), y.ravel()
    one = np.ones_like(x)
    faces = [np.column_stack(f) for f in (
        (x, y, one), (x, y, -one),          # top and bottom
        (x, one, y), (x, -one, y),          # two sides
        (one, x, y), (-one, x, y))]         # two ends
    return np.unique(np.vstack(faces), axis=0)


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
    # ⚠ THE SEAM TEST, and the reason it is a pair of BALLS. Two equal
    # spheres, offset, both containing the middle: where they cross is a
    # mathematically perfect CIRCLE. Anything the picture shows on that seam
    # that is not a smooth circle -- teeth, flags, a sawtooth -- is the
    # drawing's, not the data's, and there is nothing to argue about.
    made["ball-shifted"] = write(
        folder, "ball-shifted",
        MIDDLE + np.array([0, 18, 0]) + u * np.array([40, 45, 45]))
    made["pancake"] = write(folder, "pancake", MIDDLE + u * np.array([10, 46, 46]))
    made["column"] = write(folder, "column", MIDDLE + u * np.array([46, 12, 12]))
    # ⚠ THE WALL TEST. Nearly the whole L* range and a wide, square a*/b*
    # spread, so the shape fills the room it is drawn in and its flat faces
    # sit parallel to the box's own walls. Anything grey lying ACROSS a face
    # is a wall on the wrong side of the box, and it needs no instrument to
    # see -- which is the point, because every pixel-counting instrument
    # aimed at this fault so far has measured the symptom (a wall COVERING
    # the shape) rather than the fault (a wall on the camera's own side,
    # which at a grazing angle covers nothing and is still wrong).
    made["cube-fills-the-room"] = write(
        folder, "cube-fills-the-room",
        MIDDLE + _cube_surface() * np.array([45.0, 60.0, 60.0]))
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
