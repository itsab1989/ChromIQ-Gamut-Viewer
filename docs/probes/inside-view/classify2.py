"""Which pixels see the sheet from OUTSIDE the shape, and which from INSIDE.

Winding-free version. The page mesh is re-cut along the agreement boundary
(duplicated rim corners, T-junctions), so per-face winding is not a reliable
orientation oracle -- calibrating screen-space winding on the closed shell
gave a different answer per camera. What IS reliable is the volume: at a
covered pixel, count how many times the closed as-saved shell is crossed
strictly BEFORE the drawn mesh's first hit. Even -> the eye-side of the
winning sheet is outside the shape (an ordinary outer view); odd -> the ray
already entered the shape, so the sheet is being seen from within: the inner
side of the shell.

Calibration is exact by construction: on the closed shell itself every
covered pixel must come out even (0), because a closed surface's first hit
is always its outside.

Usage: classify2.py <harvest-dir> <closed-dir> [--mutate]
  --mutate flips the parity everywhere, to prove the numbers answer to it.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
from classify import load_mesh, pieces_of, screenshot_lit, mat


def project(v, cam):
    T = mat(cam["projection"]) @ mat(cam["view"]) @ mat(cam["model"])
    vs = v * np.asarray(cam["dataScale"], float)[None, :]
    clip = (T @ np.hstack([vs, np.ones((len(vs), 1))]).T).T
    ndc = clip[:, :3] / clip[:, 3:4]
    return ndc


def screen(ndc, W, H):
    sx = (ndc[:, 0] + 1) / 2 * W
    sy = (1 - (ndc[:, 1] + 1) / 2) * H
    return sx, sy, ndc[:, 2]


def rasterize(faces, sx, sy, sz, W, H, mode, z0=None, eps=1e-6):
    """mode 'nearest' -> (winner, depth); mode 'count<z0' -> crossing count."""
    if mode == "nearest":
        win = np.full((H, W), -1, int); depth = np.full((H, W), np.inf)
    else:
        count = np.zeros((H, W), int)
    for at, (a, b, c) in enumerate(faces):
        xs = np.array([sx[a], sx[b], sx[c]]); ys = np.array([sy[a], sy[b], sy[c]])
        zs = np.array([sz[a], sz[b], sz[c]])
        x0 = max(0, int(np.floor(xs.min()))); x1 = min(W - 1, int(np.ceil(xs.max())))
        y0 = max(0, int(np.floor(ys.min()))); y1 = min(H - 1, int(np.ceil(ys.max())))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5,
                             np.arange(y0, y1 + 1) + 0.5)
        d = ((xs[1] - xs[0]) * (ys[2] - ys[0])
             - (xs[2] - xs[0]) * (ys[1] - ys[0]))
        if abs(d) < 1e-12:
            continue
        l1 = ((gx - xs[0]) * (ys[2] - ys[0]) - (gy - ys[0]) * (xs[2] - xs[0])) / d
        l2 = -((gx - xs[0]) * (ys[1] - ys[0]) - (gy - ys[0]) * (xs[1] - xs[0])) / d
        l0 = 1 - l1 - l2
        inside = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9)
        if not inside.any():
            continue
        z = l0 * zs[0] + l1 * zs[1] + l2 * zs[2]
        if mode == "nearest":
            sub = depth[y0:y1 + 1, x0:x1 + 1]
            better = inside & (z < sub)
            sub[better] = z[better]
            win[y0:y1 + 1, x0:x1 + 1][better] = at
        else:
            sub = z0[y0:y1 + 1, x0:x1 + 1]
            count[y0:y1 + 1, x0:x1 + 1] += (inside & (z < sub - eps))
    return (win, depth) if mode == "nearest" else count


def erode(mask, n=2):
    m = mask.copy()
    for _ in range(n):
        m = (m & np.roll(m, 1, 0) & np.roll(m, -1, 0)
               & np.roll(m, 1, 1) & np.roll(m, -1, 1))
    return m


def main() -> int:
    folder = pathlib.Path(sys.argv[1])
    closed = pathlib.Path(sys.argv[2])
    mutate = "--mutate" in sys.argv

    m, v, f, colour = load_mesh(folder)
    cm, cv, cf, _ = load_mesh(closed)
    same = len(cv) == len(v) and np.allclose(cv, v)
    print(f"drawn mesh {len(f)} faces; closed shell {len(cf)} faces; "
          f"same vertex array: {same}")
    label, npieces = pieces_of(f, len(v))
    for p in range(npieces):
        verts = np.unique(f[label == p].ravel())
        hue = colour[verts].mean(axis=0)
        print(f"  piece {p}: {(label == p).sum()} faces, mean colour "
              f"rgb({hue[0]:.0f},{hue[1]:.0f},{hue[2]:.0f})")

    # exact calibration: the closed shell must classify 100% outside
    cam = json.loads(sorted(closed.glob("cam*.json"))[0].read_text())
    W = max(2, int(round(cam["rect"][2] * 0.5)))
    H = max(2, int(round(cam["rect"][3] * 0.5)))
    ndc = project(cv, cam); sx, sy, sz = screen(ndc, W, H)
    win, depth = rasterize(cf, sx, sy, sz, W, H, "nearest")
    crossings = rasterize(cf, sx, sy, sz, W, H, "count", z0=depth,
                          eps=1e-4 * (sz.max() - sz.min()))
    covered = win >= 0
    odd = (crossings[covered] % 2 == 1).sum()
    print(f"calibration: closed shell, {covered.sum()} covered px, "
          f"{odd} classify inside ({odd / max(1, covered.sum()):.4%})")

    print(f"\n{'camera':22s} {'cover':>6} {'prec':>5}  "
          + "  ".join(f"p{p}:out/in" for p in range(npieces))
          + "   inLum outLum")
    rows = []
    for cj in sorted(folder.glob("*.json")):
        name = cj.stem
        if name.startswith(("mesh", "classified")):
            continue
        cam = json.loads(cj.read_text())
        W = max(2, int(round(cam["rect"][2] * 0.5)))
        H = max(2, int(round(cam["rect"][3] * 0.5)))
        ndc = project(v, cam); sx, sy, sz = screen(ndc, W, H)
        win, depth = rasterize(f, sx, sy, sz, W, H, "nearest")
        cndc = project(cv, cam); csx, csy, csz = screen(cndc, W, H)
        eps = 1e-4 * (csz.max() - csz.min())
        crossings = rasterize(cf, csx, csy, csz, W, H, "count",
                              z0=depth, eps=eps)
        covered = win >= 0
        inner = (crossings % 2 == 1) & covered
        if mutate:
            inner = (crossings % 2 == 0) & covered
        px, lit = screenshot_lit(folder, name, cam, scale=0.5)
        precision = (covered & lit).sum() / max(1, covered.sum())
        lum = px.mean(axis=2)
        cells = []; row = {}
        inlum = outlum = float("nan")
        for p in range(npieces):
            mine = covered & np.isin(win, np.where(label == p)[0])
            n_in = (mine & inner).sum(); n_out = (mine & ~inner).sum()
            cells.append(f"{n_out:6d}/{n_in:5d}")
            row[str(p)] = [int(n_out), int(n_in)]
            core_in = erode(mine & inner, 2); core_out = erode(mine & ~inner, 2)
            if core_in.sum() > 30:
                inlum = lum[core_in].mean()
                if core_out.sum() > 30:
                    outlum = lum[core_out].mean()
        print(f"{name:22s} {covered.sum():6d} {precision:5.2f}  "
              + "  ".join(cells) + f"   {inlum:5.1f} {outlum:6.1f}")
        rows.append(dict(name=name, eye=cam["eye"], precision=precision,
                         cover=int(covered.sum()), pieces=row))
    out = folder / ("classified2-mutated.json" if mutate else "classified2.json")
    out.write_text(json.dumps(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
