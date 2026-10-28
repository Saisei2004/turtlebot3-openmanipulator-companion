"""「全部の関節がずっと動き続ける」動き（周期 24 秒の合成波）の中心と大きさを、MuJoCo の衝突判定で探す"""
import math
import numpy as np
import sim_common as sc
import omx_model as om

s = sc.Sim()
IDX = [om.GROUPS.index(g) for g in om.VARIANTS["photo_solid"]]
OFFSET = sc.OFFSET
T = 24.0
K = np.array([2, 3, 5, 4])                    # 24 秒の間に何周するか（関節ごとに違う周期）
PHI = np.array([0.0, 0.7, 1.9, 3.1])
AMP = np.array([0.55, 0.40, 0.35, 0.50])
QLIM = np.array([[-2.8274, 2.8274], [-2.7207, 0.6408], [-1.0125, 1.3123], [-0.1407, 3.1416]])
MARGIN = 0.03


def pattern(center, scale, t):
    return center + scale * AMP * np.sin(2 * math.pi * K * t / T + PHI)


def worst(center, scale, n=480):
    w, lim = 0.0, False
    for t in np.arange(0, T, T / n):
        q = pattern(center, scale, t)
        if (q < QLIM[:, 0] + MARGIN).any() or (q > QLIM[:, 1] - MARGIN).any():
            lim = True
        d = s.depths(q + OFFSET)
        w = max(w, max(d[i] for i in IDX))
    return w, lim


def ok(center, scale):
    for k in (1.0, 1.15):                     # 1.15 倍の大きさでも当たらない = 余裕
        w, lim = worst(center, scale * k)
        if w > 0.002 or lim:
            return False
    return True


def max_scale(center):
    for sc_ in np.arange(1.0, 0.19, -0.05):
        if ok(center, sc_):
            return round(float(sc_), 2)
    return 0.0


if __name__ == "__main__":
    cands = {
        "READY (a=0)": np.array([0, -0.93, -0.07, 1.65]),
        "forward-up": np.array([0, -0.45, 0.35, 0.85]) ,
        "mid": np.array([0, -0.70, 0.30, 1.20]),
        "high": np.array([0, -0.85, 0.15, 1.45]),
        "folded-ish": np.array([0, -1.30, 0.55, 1.40]),
        "forward": np.array([0, -0.55, 0.45, 0.60]),
    }
    for name, c in cands.items():
        a = c + OFFSET
        print(f"{name:14s} q={np.round(c, 2).tolist()}  max safe scale (with 1.15x margin): {max_scale(c)}")
