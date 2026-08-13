"""Draw a gamut both ways, so the difference between the two modes is visible.

    python demo.py            # writes gamut-demo.html, opens it
    python demo.py --show     # matplotlib window instead

Needs plotly (or matplotlib for --show) on top of numpy + scipy.
"""
from __future__ import annotations

import sys

import numpy as np

from gamutview import build_gamut


def srgb_cube(n: int = 8):
    """An n x n x n grid of sRGB values and their XYZ under D65 — stand-in for a
    measured chart: drive values on one side, measurements on the other."""
    g = np.linspace(0.0, 1.0, n)
    r, gg, b = np.meshgrid(g, g, g, indexing="ij")
    rgb = np.stack([r.ravel(), gg.ravel(), b.ravel()], axis=-1)
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m = np.linalg.inv(np.array([[3.2404542, -1.5371385, -0.4985314],
                                [-0.9692660, 1.8760108, 0.0415560],
                                [0.0556434, -0.2040259, 1.0572252]]))
    return rgb, lin @ m.T


def main() -> int:
    rgb, xyz = srgb_cube(8)
    hull = build_gamut(xyz, white_point="D65")
    cube = build_gamut(xyz, rgb, white_point="D65")
    for g in (hull, cube):
        print(f"  {g.mode:<12} {len(g.vertices):>5} vertices  "
              f"{len(g.faces):>5} triangles  volume {g.volume:,.0f}")

    if "--show" in sys.argv:
        import matplotlib.pyplot as plt
        fig = plt.figure(figsize=(11, 5))
        for i, g in enumerate((hull, cube), 1):
            ax = fig.add_subplot(1, 2, i, projection="3d")
            v = g.cylindrical()
            ax.plot_trisurf(v[:, 0], v[:, 1], g.faces, v[:, 2],
                            shade=False, linewidth=0, antialiased=False)
            ax.set_title(g.mode)
            ax.set_xlabel("a*-ish"); ax.set_ylabel("b*-ish"); ax.set_zlabel("L*")
        plt.tight_layout(); plt.show()
        return 0

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "mesh3d"}] * 2],
                        subplot_titles=[g.mode for g in (hull, cube)])
    for col, g in enumerate((hull, cube), 1):
        v = g.cylindrical()
        # Per-vertex colour: each point painted the colour it represents.
        colours = [f"rgb({int(r*255)},{int(gg*255)},{int(b*255)})"
                   for r, gg, b in g.colors]
        fig.add_trace(go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2],
                                i=g.faces[:, 0], j=g.faces[:, 1], k=g.faces[:, 2],
                                vertexcolor=colours, opacity=1.0, flatshading=False),
                      row=1, col=col)
    fig.update_layout(title="sRGB gamut in Lab — convex hull vs device cube",
                      showlegend=False)
    fig.write_html("gamut-demo.html", include_plotlyjs="cdn")
    print("\n  wrote gamut-demo.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
