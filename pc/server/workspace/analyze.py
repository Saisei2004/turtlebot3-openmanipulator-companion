"""sweep.py の結果から workspace.json / joint_space.json / 図 / 現在の画面とのずれ を作る。"""
import json
from pathlib import Path
import numpy as np
import omx_model as om
import sim_common as sc
import sweep as sw

OUT = Path("out")
TOL = sw.TOL_U8
NR, NZ, NP = len(sw.R_GRID), len(sw.Z_GRID), len(sw.P_DEG)
LIMS = ["urdf_on_a", "mech_pi_on_q"]
ENVS = list(om.VARIANTS)
PAY = sw.PAYLOADS


def load_ik():
    z = np.load(OUT / "ik_grid.npz")
    dep, tau, idx, a, a_raw = z["dep"], z["tau"], z["idx"], z["a"], z["a_raw"]
    y = np.load(OUT / "yaw_mask.npz")
    N = len(dep)
    ymask = np.zeros((N, len(ENVS)), np.uint32)
    ymask[y["fi"]] = y["mask"]
    return dict(dep=dep, tau=tau, idx=idx, a=a, a_raw=a_raw, ymask=ymask, yaws=y["yaws"])


def env_ok0(dep, v):
    return (dep[:, [om.GROUPS.index(g) for g in om.VARIANTS[v]]] <= TOL).all(1)


def lim_ok(a, lim):
    """a は URDF 側の関節角（サーボ範囲に畳み済み）"""
    if lim == "mech_pi_on_q":
        return np.ones(len(a), bool)
    return ((a[:, 1:4] >= sc.URDF_LIM[1:4, 0]) & (a[:, 1:4] <= sc.URDF_LIM[1:4, 1])).all(1)


def yaw_bits_ok(lim, yaws):
    """joint1 の使える yaw のビット（URDF は ±162°、サーボは ±π）"""
    lo = -np.degrees(2.827433388) if lim == "urdf_on_a" else -181
    hi = np.degrees(2.827433388) if lim == "urdf_on_a" else 181
    m = 0
    for i, y in enumerate(yaws):
        if lo <= y <= hi:
            m |= (1 << i)
    return np.uint32(m)


def cells_from(poses_ok, d, extra=None):
    """poses_ok: (N,) bool。セルごとの集計を (NR,NZ) 配列で返す"""
    idx = d["idx"]
    ir, iz, ip = idx[:, 0], idx[:, 1], idx[:, 2]
    ok = poses_ok
    cnt = np.zeros((NR, NZ, NP), bool)
    cnt[ir[ok], iz[ok], ip[ok]] = True                      # 肘の 2 解のどちらか
    n = cnt.sum(2)
    return cnt, n


def runs_of(row):
    """pitch の ok 配列（円周上）から、連続区間 [開始°, 終了°] の一覧"""
    if row.all():
        return [[int(sw.P_DEG[0]), int(sw.P_DEG[-1])]]
    if not row.any():
        return []
    ang = sw.P_DEG
    start = None; out = []
    for i in range(NP):
        if row[i] and start is None:
            start = i
        if (not row[i] or i == NP - 1) and start is not None:
            end = i if row[i] and i == NP - 1 else i - 1
            out.append([int(ang[start]), int(ang[end])]); start = None
    if len(out) > 1 and out[0][0] == ang[0] and out[-1][1] == ang[-1]:      # 円周でつながる
        out[0][0] = out[-1][0] - 360; out.pop()
    return out


def analyze_combo(d, lim, env):
    dep, tau, a = d["dep"], d["tau"], d["a"]
    ok = lim_ok(a, lim) & env_ok0(dep, env)
    cnt, n = cells_from(ok, d)
    res = dict(ok=ok, cnt=cnt, n=n)
    idx = d["idx"]
    # トルク余裕（ペイロードごと）
    marg = {}
    for j, p in enumerate(PAY):
        m = 1.0 - tau[:, j] / sc.TAU_STALL                  # tau は joint2..4 の最大 |保持トルク|
        okt = ok & np.isfinite(m)
        best = np.full((NR, NZ), -np.inf); worst = np.full((NR, NZ), np.inf)
        np.maximum.at(best, (idx[okt, 0], idx[okt, 1]), m[okt])
        np.minimum.at(worst, (idx[okt, 0], idx[okt, 1]), m[okt])
        best[~np.isfinite(best)] = np.nan; worst[~np.isfinite(worst)] = np.nan
        tok = okt & (m >= 0)
        cntt, nt = cells_from(tok, d)
        marg[p] = dict(best=best, worst=worst, n_ok=nt, cnt=cntt, pose_ok=tok)
    res["torque"] = marg
    # yaw ごとに届くか（セル単位。URDF 限界の yaw 範囲を掛ける）
    yb = yaw_bits_ok(lim, d["yaws"])
    ev = ENVS.index(env)
    ym = d["ymask"][:, ev] & yb
    ym = np.where(ok, ym, 0).astype(np.uint32)
    cellmask = np.zeros((NR, NZ), np.uint32)
    for ir_, iz_, m_ in zip(idx[ok, 0], idx[ok, 1], ym[ok]):
        cellmask[ir_, iz_] |= m_
    res["yaw_mask"] = cellmask
    return res


def cell_arrays(res):
    cnt, n = res["cnt"], res["n"]
    pmin = np.full((NR, NZ), np.nan); pmax = np.full((NR, NZ), np.nan)
    for ir in range(NR):
        for iz in range(NZ):
            if n[ir, iz]:
                w = np.where(cnt[ir, iz])[0]
                pmin[ir, iz] = sw.P_DEG[w[0]]; pmax[ir, iz] = sw.P_DEG[w[-1]]
    return pmin, pmax


def flat(a, ndigits=None):
    x = np.asarray(a).reshape(-1)
    out = []
    for v in x:
        if isinstance(v, (np.floating, float)):
            out.append(None if not np.isfinite(v) else (round(float(v), ndigits) if ndigits else float(v)))
        else:
            out.append(int(v))
    return out


def web_compare(d, sim_ok_urdf, sim_ok_mech):
    """画面（arm_kin.js: 肘=-1 の 1 解だけ、LIMITS を q に適用、r≥0.06、z≥床ガード）が出す答えと、シミュレーションの答えを姿勢単位で比べる"""
    idx = d["idx"]; a_raw = d["a_raw"]
    elbow = idx[:, 3]
    r = sw.R_GRID[idx[:, 0]]; z = sw.Z_GRID[idx[:, 1]]
    q_web = a_raw - sc.OFFSET                                   # 畳まずにそのまま（arm_kin.js と同じ）
    in_lim = ((q_web[:, 1:4] >= sc.WEB_LIM[1:4, 0]) & (q_web[:, 1:4] <= sc.WEB_LIM[1:4, 1])).all(1)
    base = (elbow == 0) & in_lim & (r >= 0.06)                  # elbow index 0 は ik_a の elbow=-1
    out = {}
    for guard in (-0.08, -0.20):
        web = base & (z >= guard - 1e-9)
        for name, sim in (("sim_urdf_photo_solid", sim_ok_urdf), ("sim_mech_photo_solid", sim_ok_mech)):
            sim1 = sim & (elbow == 0)
            both = (web & sim1).sum(); wo = (web & ~sim1).sum(); so = (~web & sim1 & (r >= 0.06) & (z >= guard - 1e-9)).sum()
            out[f"guard{int(guard * 100)}|{name}"] = dict(web_ok=int(web.sum()), sim_ok_same_elbow_same_region=int((sim1 & (r >= 0.06) & (z >= guard - 1e-9)).sum()),
                                                          both=int(both), web_only=int(wo), sim_only=int(so))
    return out, base



def reasons(d, mask, lim="urdf_on_a", env="photo_solid"):
    """mask の姿勢がシミュレーションで不可になる理由（優先順位: 関節限界 → 自己衝突 → 床 → 車体）の内訳"""
    dep, a = d["dep"][mask], d["a"][mask]
    lo = ~lim_ok(a, lim)
    selfc = dep[:, 0] > TOL
    floor = dep[:, 1] > TOL
    body = ~env_ok0(dep, env)
    out = dict(joint_limit=int(lo.sum()))
    rest = ~lo
    out["self_collision"] = int((rest & selfc).sum()); rest &= ~selfc
    out["floor"] = int((rest & floor).sum()); rest &= ~floor
    out["body_wheel_lidar_plate"] = int((rest & body).sum()); rest &= ~body
    out["none(=sim ok)"] = int(rest.sum())
    return out


def web_vs_sim(d, combos):
    idx = d["idx"]; a_raw = d["a_raw"]
    elbow = idx[:, 3]
    r = sw.R_GRID[idx[:, 0]]; z = sw.Z_GRID[idx[:, 1]]
    q_web = a_raw - sc.OFFSET                                  # 畳まずにそのまま（arm_kin.js と同じ）
    in_lim = ((q_web[:, 1:4] >= sc.WEB_LIM[1:4, 0]) & (q_web[:, 1:4] <= sc.WEB_LIM[1:4, 1])).all(1)
    web_core = (elbow == 0) & in_lim & (r >= 0.06)             # elbow index 0 = arm_kin.js と同じ -acos の解
    res = {}
    for guard in (-0.08, -0.20):
        zg = z >= guard - 1e-9
        web = web_core & zg
        for lim, env in (("urdf_on_a", "photo_solid"), ("mech_pi_on_q", "photo_solid"), ("urdf_on_a", "self_floor")):
            sim = combos[(lim, env)]["ok"]
            region = (elbow == 0) & (r >= 0.06) & zg           # 画面が答える土俵（肘 1 解・r≥6cm・床ガード以上）
            e = dict(web_accepts=int(web.sum()), sim_ok_in_same_region=int((sim & region).sum()),
                     both=int((web & sim).sum()), web_only=int((web & ~sim).sum()), sim_only=int((~web & sim & region).sum()))
            e["web_only_reasons"] = reasons(d, web & ~sim, lim, env)
            # sim_only の理由: 画面側が止める理由
            so = ~web & sim & region
            e["sim_only_reasons"] = dict(web_joint_limit_on_q=int((so & ~in_lim).sum()), other=int((so & in_lim).sum()))
            res[f"floor_guard_{int(guard * 100)}cm|{lim}|{env}"] = e
    # セル単位（yaw=0）: 画面が 1 つでも pitch を受け付けるセルとシミュレーションの比較
    for lim, env in (("urdf_on_a", "photo_solid"), ("mech_pi_on_q", "photo_solid")):
        wcnt = np.zeros((NR, NZ), bool); wcnt[idx[web_core & (z >= -0.08 - 1e-9), 0], idx[web_core & (z >= -0.08 - 1e-9), 1]] = True
        scnt = combos[(lim, env)]["n"] > 0
        sreg = np.zeros((NR, NZ), bool); sreg[:, :] = (sw.Z_GRID[None, :] >= -0.08 - 1e-9) & (sw.R_GRID[:, None] >= 0.06)
        res[f"cells|guard-8cm|{lim}|{env}"] = dict(web_cells=int(wcnt.sum()), sim_cells_same_region=int((scnt & sreg).sum()),
                                                   both=int((wcnt & scnt).sum()), web_only=int((wcnt & ~scnt).sum()), sim_only=int((~wcnt & scnt & sreg).sum()),
                                                   sim_cells_all=int(scnt.sum()))
    return res, web_core


def known_poses():
    S = sc.Sim()
    rows = []
    for name, q in (("全関節0（カメラで実物確認・上腕が前へ倒れた形）", [0, 0, 0, 0]), ("READY（L字・実物確認）", [0, -0.93, -0.07, 1.65]),
                    ("写真の姿勢（実物）", [-0.02, -0.561, 0.865, 1.092]), ("旧 home を q として読んだ姿勢（現行 OFFSET では実在しない）", [-0.0199, -0.813, 1.5142, 0.0337])):
        a = np.array(q, float) + sc.OFFSET
        r, z, _ = S.tip_rz(a)
        dep = S.depths(a) * 1000
        rows.append(dict(name=name, q=q, a=[round(float(x), 4) for x in a], r_cm=round(float(r) * 100, 1), z_cm=round(float(z) * 100, 1),
                         pitch_deg=round(float(np.degrees(a[1] + a[2] + a[3])), 1),
                         in_urdf_limits=bool(((a[1:4] >= sc.URDF_LIM[1:4, 0]) & (a[1:4] <= sc.URDF_LIM[1:4, 1])).all()),
                         depth_mm={g: round(float(v), 1) for g, v in zip(om.GROUPS, dep) if v > 0.01}))
    return rows


def joint_space():
    z = np.load(OUT / "joint_grid.npz"); dep = z["dep"]; q = np.degrees(z["q"])
    A = np.deg2rad(q)[:, None, None] * 0
    qr = z["q"]
    a2 = qr + sc.OFFSET[1]; a3 = qr + sc.OFFSET[2]; a4 = qr + sc.OFFSET[3]
    inl = ((a2[:, None, None] >= sc.URDF_LIM[1, 0]) & (a2[:, None, None] <= sc.URDF_LIM[1, 1]) &
           (a3[None, :, None] >= sc.URDF_LIM[2, 0]) & (a3[None, :, None] <= sc.URDF_LIM[2, 1]) &
           (a4[None, None, :] >= sc.URDF_LIM[3, 0]) & (a4[None, None, :] <= sc.URDF_LIM[3, 1]))
    out = {"grid_deg": [float(q[0]), float(q[-1]), float(q[1] - q[0])], "note": "joint1=0 (真正面)。q は /joint_states と同じ値。q2,q3,q4 を ±180° の 2° 刻みで全探索"}
    for lim in LIMS:
        for env in ("photo_solid", "self_floor", "stock_solid"):
            idxs = [om.GROUPS.index(g) for g in om.VARIANTS[env]]
            free = (dep[..., idxs] <= TOL).all(-1)
            if lim == "urdf_on_a":
                free &= inl
            tot = inl.sum() if lim == "urdf_on_a" else free.size
            e = dict(free_poses=int(free.sum()), total_poses_in_limits=int(tot), free_fraction=round(float(free.sum() / tot), 4))
            e["q_range_deg"] = {}
            for j, nm in enumerate(("joint2", "joint3", "joint4")):
                ax = tuple(k for k in range(3) if k != j)
                m = free.any(axis=ax)
                e["q_range_deg"][nm] = [float(q[m].min()), float(q[m].max())] if m.any() else None
                e.setdefault("marginal_free_fraction", {})[nm] = [round(float(x), 3) for x in free.mean(axis=ax)]
            # (q2,q3) の組ごとに q4 の自由な区間
            runs = {}
            for i2 in range(len(q)):
                for i3 in range(len(q)):
                    row = free[i2, i3]
                    if not row.any():
                        continue
                    rr = []; st = None
                    for i4 in range(len(q)):
                        if row[i4] and st is None:
                            st = i4
                        if st is not None and (not row[i4] or i4 == len(q) - 1):
                            en = i4 if row[i4] else i4 - 1
                            rr.append([float(q[st]), float(q[en])]); st = None
                    runs[f"{q[i2]:.0f},{q[i3]:.0f}"] = rr
            e["q4_free_runs_by_q2_q3_deg"] = runs
            out[f"{lim}|{env}"] = e
    return out, dep, inl


def main():
    d = load_ik()
    dep, tau, a, idx = d["dep"], d["tau"], d["a"], d["idx"]
    combos = {(lim, env): analyze_combo(d, lim, env) for lim in LIMS for env in ENVS}
    print("\n=== セル数（1 cm² = 1 セル, yaw=0）===")
    for (lim, env), r in combos.items():
        print(f"{lim:14s} {env:18s} セル {int((r['n'] > 0).sum()):5d}  可能姿勢 {int(r['ok'].sum()):6d}  500g でトルク不足のセル {int(((r['n'] > 0) & (r['torque'][0.5]['n_ok'] == 0)).sum())}")
    cmp_, web_core = web_vs_sim(d, combos)
    print("\n=== 画面 (arm_kin.js) とシミュレーションのずれ ===")
    for k, v in cmp_.items():
        print(k, json.dumps(v, ensure_ascii=False))
    kp = known_poses()
    for r in kp:
        print(r)
    js, jdep, inl = joint_space()
    for k, v in js.items():
        if isinstance(v, dict):
            print(k, v["free_poses"], "/", v["total_poses_in_limits"], v["free_fraction"], v["q_range_deg"])
    return d, combos, cmp_, kp, js


if __name__ == "__main__":
    main()
