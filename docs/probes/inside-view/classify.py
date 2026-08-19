"""Which triangles win each pixel, and which SIDE of them the camera sees.

Reads a harvest directory (mesh.json + camNNN.json + camNNN.png) and, per
camera, rasterises the drawn triangle list with the very matrices the GL
scene used -- a z-buffer, nearest wins, exactly what the opaque path does.
Each covered pixel is classified by the winning triangle's screen-space
winding: with the shell wound one way consistently, every triangle seen from
OUTSIDE has one sign and every triangle seen from INSIDE (a back face) has
the other. The sign meaning "outside" is calibrated on the closed as-saved
mesh, where the inside cannot be seen at all.

Per camera and per connected piece it reports front pixels, back pixels, and
-- against the screenshot -- the mean brightness of each region, which is
what settles whether a back face is drawn lit like a front one.

The probe proves it landed: raster coverage is compared with the
screenshot's own lit pixels (IoU), and --mutate flips the winding to show
the classification answers to it.

Usage: classify.py <harvest-dir> [--mutate] [--calibrate <closed-dir>]
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
from PIL import Image


def mat(flat):
    return np.asarray(flat, float).reshape(4, 4, order="F")


def load_mesh(folder):
    m = json.loads((folder / "mesh.json").read_text())
    v = np.stack([m["x"], m["y"], m["z"]], axis=1).astype(float)
    f = np.stack([m["i"], m["j"], m["k"]], axis=1).astype(int)
    colour = np.zeros((len(v), 3))
    for at, c in enumerate(m["vertexcolor"]):
        inside = c[c.index("(") + 1:c.index(")")].split(",")
        colour[at] = [float(inside[0]), float(inside[1]), float(inside[2])]
    return m, v, f, colour


def pieces_of(faces, n):
    """Connected components over shared vertices; label per face."""
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a

    for a, b, c in faces:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra; parent[rc] = find(b)
    roots = [find(f[0]) for f in faces]
    names = sorted(set(roots))
    return np.asarray([names.index(r) for r in roots]), len(names)


def raster(v, faces, cam, scale=1.0):
    """(winner index per pixel or -1, depth, screen coords of vertices)."""
    M = mat(cam["model"]); V = mat(cam["view"]); P = mat(cam["projection"])
    T = P @ V @ M
    # plotly gl3d hands the GL scene its vertices already multiplied by the
    # scene's dataScale; cameraParams.model does not contain it.
    v = v * np.asarray(cam["dataScale"], float)[None, :]
    W = max(2, int(round(cam["rect"][2] * scale)))
    H = max(2, int(round(cam["rect"][3] * scale)))
    ones = np.ones((len(v), 1))
    clip = (T @ np.hstack([v, ones]).T).T
    w = clip[:, 3:4]
    ndc = clip[:, :3] / w
    sx = (ndc[:, 0] + 1) / 2 * W
    sy = (1 - (ndc[:, 1] + 1) / 2) * H
    sz = ndc[:, 2]
    win = np.full((H, W), -1, int)
    depth = np.full((H, W), np.inf)
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
        sub = depth[y0:y1 + 1, x0:x1 + 1]
        better = inside & (z < sub)
        sub[better] = z[better]
        win[y0:y1 + 1, x0:x1 + 1][better] = at
    return win, depth, sx, sy


def face_signs(faces, sx, sy):
    a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
    return np.sign((sx[b] - sx[a]) * (sy[c] - sy[a])
                   - (sx[c] - sx[a]) * (sy[b] - sy[a]))


def screenshot_lit(folder, name, cam, scale=1.0):
    im = Image.open(folder / f"{name}.png").convert("RGB")
    r = cam["ratio"]
    left, top, wide, tall = [x * r for x in cam["rect"]]
    box = im.crop((int(left), int(top), int(left + wide), int(top + tall)))
    W = max(2, int(round(cam["rect"][2] * scale)))
    H = max(2, int(round(cam["rect"][3] * scale)))
    box = box.resize((W, H))
    px = np.asarray(box, float)
    corners = np.concatenate([px[:4, :4].reshape(-1, 3),
                              px[:4, -4:].reshape(-1, 3)])
    bg = corners.mean(axis=0)
    lit = (np.abs(px - bg).sum(axis=2) > 40)
    return px, lit


def main() -> int:
    folder = pathlib.Path(sys.argv[1])
    mutate = "--mutate" in sys.argv
    calib = None
    if "--calibrate" in sys.argv:
        calib = pathlib.Path(sys.argv[sys.argv.index("--calibrate") + 1])

    m, v, f, colour = load_mesh(folder)
    if mutate:
        f = f[:, [0, 2, 1]]
        print("MUTATION: winding flipped on all", len(f), "faces")
    label, npieces = pieces_of(f, len(v))
    piece_hue = []
    for p in range(npieces):
        verts = np.unique(f[label == p].ravel())
        piece_hue.append(colour[verts].mean(axis=0))
    print(f"mesh: {len(v)} vertices, {len(f)} faces, {npieces} pieces")
    for p, hue in enumerate(piece_hue):
        n = (label == p).sum()
        print(f"  piece {p}: {n} faces, mean colour rgb"
              f"({hue[0]:.0f},{hue[1]:.0f},{hue[2]:.0f})")

    # -- the OUTSIDE sign, calibrated on the closed shell -------------------
    outside_sign = None
    if calib is not None:
        cm, cv, cf, _ = load_mesh(calib)
        cams = sorted(calib.glob("cam*.json"))
        cam = json.loads(cams[0].read_text())
        cwin, _, csx, csy = raster(cv, cf, cam, scale=0.5)
        signs = face_signs(cf, csx, csy)
        seen = signs[np.unique(cwin[cwin >= 0])]
        pos = (seen > 0).sum(); neg = (seen < 0).sum()
        outside_sign = 1.0 if pos >= neg else -1.0
        print(f"calibration on closed shell ({len(cf)} faces): visible "
              f"winners {pos} positive / {neg} negative -> outside sign "
              f"{outside_sign:+.0f}"
              + ("  [NOT unanimous!]" if pos and neg else ""))
    else:
        outside_sign = 1.0
        print("no calibration dir given; assuming outside sign +1")

    print(f"\n{'camera':22s} {'cover':>7} {'IoU':>5} {'prec':>5} {'hue':>5}  "
          + "  ".join(f"p{p}:front/back" for p in range(npieces))
          + "   backLum frontLum")
    rows = []
    for cj in sorted(folder.glob("cam*.json")):
        name = cj.stem
        cam = json.loads(cj.read_text())
        win, _, sx, sy = raster(v, f, cam, scale=0.5)
        signs = face_signs(f, sx, sy)
        covered = win >= 0
        px, lit = screenshot_lit(folder, name, cam, scale=0.5)
        both = (covered & lit).sum(); either = (covered | lit).sum()
        iou = both / max(1, either)
        # PRECISION: of the pixels the raster says the mesh covers, how many
        # are really lit on the screenshot. The grid and lettering light
        # pixels the mesh does not cover, so IoU alone under-reads a probe
        # that landed perfectly.
        precision = both / max(1, covered.sum())
        # AND THE COLOURS AGREE, not merely the footprint: the screenshot
        # hue at covered pixels against the winning triangle's own vertex
        # colour (hue only -- lighting scales brightness).
        if covered.sum():
            want = colour[f[win[covered], 0]]
            got_px = px[covered]
            wn = want / np.maximum(1e-6, np.linalg.norm(want, axis=1))[:, None]
            gn = got_px / np.maximum(1e-6,
                                     np.linalg.norm(got_px, axis=1))[:, None]
            hue_ok = float((np.einsum("ij,ij->i", wn, gn) > 0.9).mean())
        else:
            hue_ok = float("nan")
        cells = []
        backlum = frontlum = float("nan")
        backs = {}
        for p in range(npieces):
            mine = covered & np.isin(win, np.where(label == p)[0])
            s = np.zeros_like(win, float)
            s[covered] = signs[win[covered]] * outside_sign
            front = (mine & (s > 0)).sum()
            back = (mine & (s < 0)).sum()
            backs[p] = back
            cells.append(f"{front:6d}/{back:5d}")
            if back > 30:
                lum = px.mean(axis=2)
                backlum = lum[mine & (s < 0)].mean()
                if front > 30:
                    frontlum = lum[mine & (s > 0)].mean()
        print(f"{name:22s} {covered.sum():7d} {iou:5.2f} {precision:5.2f} "
              f"{hue_ok:5.2f}  " + "  ".join(cells)
              + f"   {backlum:7.1f} {frontlum:8.1f}")
        rows.append(dict(name=name, eye=cam["eye"], iou=iou,
                         precision=precision, hue=hue_ok,
                         cover=int(covered.sum()),
                         backs={str(k): int(vv) for k, vv in backs.items()}))
    (folder / ("classified-mutated.json" if mutate else "classified.json")
     ).write_text(json.dumps(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
