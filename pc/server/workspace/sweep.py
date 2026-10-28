"""全探索: (1) 関節空間グリッド、(2) 手先位置 (r,z,pitch) の IK グリッド、(3) joint1 の向き（yaw）ごとの車体衝突、
(4) 重力保持トルク。結果は out/*.npz に保存する（解析は analyze.py）。使い方: python sweep.py [joint|ik|yaw|all]"""
import os
import sys
import time
from multiprocessing import get_context
from pathlib import Path
import numpy as np
import omx_model as om
import sim_common as sc

OUT = Path("out"); OUT.mkdir(exist_ok=True)
TOL_U8 = int(round(0.002 * 1000 * sc.QUANT))      # めり込み 2 mm までは「接触していない」扱い（メッシュの当たり誤差・凸包の余り）
PAYLOADS = [0.0, 0.1, 0.2, 0.5]
YAWS_DEG = np.arange(-165, 181, 15)               # -165..180（24 点）。joint1 の機械範囲は ±π
Q_GRID = np.deg2rad(np.arange(-180, 181, 2))      # 関節空間グリッド（サーボ出力軸 ±π を 2° 刻み）
R_GRID = np.round(np.arange(-0.12, 0.4601, 0.01), 3)
Z_GRID = np.round(np.arange(-0.20, 0.4001, 0.01), 3)
P_DEG = np.arange(-180, 180, 3)
VAR_NAMES = list(om.VARIANTS)
VAR_IDX = [[om.GROUPS.index(g) for g in om.VARIANTS[v]] for v in VAR_NAMES]

_S = None
_SP = None


def _init():
    global _S, _SP
    import os
    _S = sc.Sim(gripper=float(os.environ.get("TB3_GRIP", "0.019")))
    _SP = [sc.Sim(payload_kg=p, with_env=False) for p in PAYLOADS]


def _task_joint(i2):
    a = np.zeros((len(Q_GRID), len(Q_GRID), 4))
    a[..., 1] = Q_GRID[i2] + sc.OFFSET[1]
    a[..., 2] = Q_GRID[:, None] + sc.OFFSET[2]
    a[..., 3] = Q_GRID[None, :] + sc.OFFSET[3]
    out = np.zeros((len(Q_GRID), len(Q_GRID), len(om.GROUPS)), np.uint8)
    for i3 in range(len(Q_GRID)):
        for i4 in range(len(Q_GRID)):
            out[i3, i4] = _S.depths_u8(a[i3, i4], 0.0)
    return i2, out


def _task_ik(poses):
    n = len(poses)
    dep = np.zeros((n, len(om.GROUPS)), np.uint8)
    tau = np.full((n, len(PAYLOADS)), np.nan, np.float32)
    for k, a in enumerate(poses):
        dep[k] = _S.depths_u8(a, 0.0)
        if dep[k, 0] <= TOL_U8 and dep[k, 1] <= TOL_U8:       # 自己衝突も床衝突もない姿勢だけトルクを計算
            for j, sp in enumerate(_SP):
                t = sp.hold_torque(a)
                tau[k, j] = np.max(np.abs(t[1:4]))
    return dep, tau


def _task_yaw(poses):
    n = len(poses)
    mask = np.zeros((n, len(VAR_NAMES)), np.uint32)
    for k, a in enumerate(poses):
        for iy, yd in enumerate(YAWS_DEG):
            d = _S.depths_u8(a, np.deg2rad(yd))
            for v, idx in enumerate(VAR_IDX):
                if (d[idx] <= TOL_U8).all():
                    mask[k, v] |= np.uint32(1 << iy)
    return mask


def run_pool(fn, items, label):
    t0 = time.time()
    ctx = get_context("spawn")
    res = []
    with ctx.Pool(22, initializer=_init) as pool:
        for i, r in enumerate(pool.imap(fn, items, chunksize=1)):
            res.append(r)
            if (i + 1) % max(1, len(items) // 10) == 0:
                print(f"  {label}: {i + 1}/{len(items)}  {time.time() - t0:.0f}s", flush=True)
    print(f"{label} 完了 {time.time() - t0:.0f}s", flush=True)
    return res


def ik_poses():
    Rg, Zg, Pg = np.meshgrid(R_GRID, Z_GRID, np.deg2rad(P_DEG), indexing="ij")
    a = np.stack([sc.ik_a(Rg, Zg, Pg, e) for e in (-1, 1)], 3)            # (R,Z,P,2,4)
    a_raw = a.copy()
    valid = np.isfinite(a[..., 1])
    q = sc.wrap_q(a - sc.OFFSET)                                            # サーボの出力軸の範囲に畳む
    a = q + sc.OFFSET
    a[..., 0] = 0.0
    return a_raw, a, valid


def main(what):
    if what in ("joint", "all"):
        print("== 関節空間グリッド", len(Q_GRID) ** 3, "姿勢")
        res = run_pool(_task_joint, list(range(len(Q_GRID))), "joint")
        dep = np.zeros((len(Q_GRID),) * 3 + (len(om.GROUPS),), np.uint8)
        for i2, o in res:
            dep[i2] = o
        np.savez_compressed(OUT / "joint_grid.npz", dep=dep, q=Q_GRID)
    if what in ("ik", "yaw", "all"):
        a_raw, a, valid = ik_poses()
        idx = np.argwhere(valid)
        poses = a[valid]
        print("== IK グリッド", poses.shape[0], "姿勢（r×z×pitch×肘）")
        if what in ("ik", "all"):
            chunks = [poses[i:i + 4000] for i in range(0, len(poses), 4000)]
            res = run_pool(_task_ik, chunks, "ik")
            dep = np.concatenate([r[0] for r in res]); tau = np.concatenate([r[1] for r in res])
            np.savez_compressed(OUT / os.environ.get("TB3_IK_OUT", "ik_grid.npz"), dep=dep, tau=tau, idx=idx, a=poses, a_raw=a_raw[valid])
        if what in ("yaw", "all"):
            z = np.load(OUT / "ik_grid.npz")
            dep = z["dep"]
            feas = (dep[:, 0] <= TOL_U8) & (dep[:, 1] <= TOL_U8)               # 自己衝突・床衝突なし（yaw に依らない）
            fi = np.where(feas)[0]
            print("== yaw 掃引:", len(fi), "姿勢 ×", len(YAWS_DEG), "yaw")
            chunks = [poses[fi[i:i + 1500]] for i in range(0, len(fi), 1500)]
            res = run_pool(_task_yaw, chunks, "yaw")
            mask = np.concatenate(res)
            np.savez_compressed(OUT / "yaw_mask.npz", fi=fi, mask=mask, yaws=YAWS_DEG, variants=np.array(VAR_NAMES))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
