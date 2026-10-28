"""analyze.py の集計を workspace.json / joint_space.json / 図 に書き出す。"""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import analyze as an
import omx_model as om
import sim_common as sc
import sweep as sw

for f in ("Yu Gothic", "Meiryo", "MS Gothic", "Noto Sans CJK JP"):
    if any(f in x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams["axes.unicode_minus"] = False

W = Path(".")
R, Z, P = sw.R_GRID, sw.Z_GRID, sw.P_DEG
NR, NZ, NP = len(R), len(Z), len(P)
PRIMARY = ("urdf_on_a", "photo_solid")
FLOOR_REL = om.FLOOR_Z - om.J2_IN_BASE[2]                 # 床の高さ（joint2 軸原点）= -0.1775
PLATE_TOP_REL = om.PLATE_Z[1] - om.J2_IN_BASE[2]          # 板の上面
Q_LIMITS_FROM_URDF = {                                    # URDF の限界（a）を、画面が使う読み値 q に直したもの
    "joint2": [round(float(sc.URDF_LIM[1, 0] - sc.OFFSET[1]), 4), round(float(sc.URDF_LIM[1, 1] - sc.OFFSET[1]), 4)],
    "joint3": [round(float(sc.URDF_LIM[2, 0] - sc.OFFSET[2]), 4), round(float(sc.URDF_LIM[2, 1] - sc.OFFSET[2]), 4)],
    "joint4": [round(float(sc.URDF_LIM[3, 0] - sc.OFFSET[3]), 4), round(min(float(sc.URDF_LIM[3, 1] - sc.OFFSET[3]), np.pi), 4)],
}


def fl(a, nd=3):
    x = np.asarray(a, float).reshape(-1)
    return [None if not np.isfinite(v) else round(float(v), nd) for v in x]


def build_combo_json(d, lim, env, res, full):
    n = res["n"]
    pmin, pmax = an.cell_arrays(res)
    e = dict(area_cm2=int((n > 0).sum()), n_poses_yaw0=int(res["ok"].sum()),
             n_pitch=[int(v) for v in n.reshape(-1)],
             pitch_min_deg=fl(pmin, 0), pitch_max_deg=fl(pmax, 0),
             yaw_mask=[int(v) for v in res["yaw_mask"].reshape(-1)])
    tq = {}
    for p in sw.PAYLOADS:
        t = res["torque"][p]
        tq[f"{int(p * 1000)}g"] = dict(n_pitch_torque_ok=[int(v) for v in t["n_ok"].reshape(-1)],
                                       margin_best=fl(t["best"], 3), margin_worst=fl(t["worst"], 3),
                                       area_cm2_torque_ok=int((t["n_ok"] > 0).sum()))
    e["torque"] = tq
    if full:
        runs = {}
        for ir in range(NR):
            for iz in range(NZ):
                if n[ir, iz]:
                    runs[f"{ir},{iz}"] = an.runs_of(res["cnt"][ir, iz])
        e["pitch_runs_deg"] = runs
    return e


def main():
    d = an.load_ik()
    combos = {(lim, env): an.analyze_combo(d, lim, env) for lim in an.LIMS for env in an.ENVS}
    cmp_, web_core = an.web_vs_sim(d, combos)
    kp = an.known_poses()
    js, jdep, inl = an.joint_space()
    meta = dict(
        generated="2026-10-26", mujoco_version=__import__("mujoco").__version__,
        coordinate="原点=joint2 の軸（base_link で x=-0.080, z=0.1675）。r=前方、z=上、pitch=手先の下向き角=a2+a3+a4（度）。セルは (r,z) 1 cm、pitch は 3° 刻み。配列は ir*nz+iz の順（r が遅い）。yaw=0（真正面）の結果で、yaw_mask は 15° ごとの到達可否のビット（下記 yaw_deg の順）",
        joint_convention="q = /joint_states の値（指令に使う値）、a = URDF 側の関節角 = q + OFFSET。OFFSET=[0,0.93,0.07,-1.65]（カメラで実測）",
        limit_variants={"urdf_on_a": "URDF の関節限界を a に適用（かつサーボの出力軸 q が ±π）。設計上の可動範囲",
                        "mech_pi_on_q": "サーボの出力軸 q が ±π にあることだけを条件にし、あとは衝突だけで制限（機械的な上限）"},
        q_limits_equivalent_of_urdf_on_q=Q_LIMITS_FROM_URDF,
        env_variants={"photo_solid": "写真から測った車体（板 x=-0.215〜+0.050）。板と板のあいだは詰まっているとみなす（保守的）。基準",
                      "photo_solid_f030": "同上で板の前端を +0.030", "photo_solid_f070": "同上で板の前端を +0.070",
                      "photo_plate_only": "上段の板・車輪・LiDAR だけ（あいだは空洞とみなす）",
                      "stock_solid": "標準 Waffle Pi の板（x=-0.133〜+0.141）。実物とは違う参考値",
                      "self_floor": "車体なし（自己衝突と床だけ）"},
        assumptions=dict(
            arm_model="寸法・質量・慣性・メッシュは機体の robot_description と turtlebot3_manipulation_description のメッシュ。リンクのメッシュは長手方向のスラブに切って凸包にした（MuJoCo のメッシュ衝突は凸包のため）",
            tolerance_mm=2.0, gripper="開き幅 +19 mm（最大）で評価。-10 mm（閉）でも写真の姿勢などの結果は同じ",
            plate_z_m=list(om.PLATE_Z), body_z_m=list(om.BODY_Z), plate_x_rear_m=om.PLATE_X_REAR, plate_front_options_m=om.FRONTS,
            plate_y_m=list(om.PLATE_Y), stock_plate_x_m=list(om.STOCK_X), lidar="ladar.stl（LDS-01 のメッシュ）を URDF の位置 (-0.024,0,0.122) に置いた。実機は LDS-02",
            wheels=om.WHEEL, caster=om.CASTER, floor_z_in_base_link_m=om.FLOOR_Z, floor_z_in_joint2_frame_m=round(FLOOR_REL, 4),
            plate_top_z_in_joint2_frame_m=round(PLATE_TOP_REL, 4),
            not_modelled="電池・ラズパイ・OpenCR・配線・カメラ・柱・ケーブルの張力。ケーブルが当たる姿勢は含まない",
            torque="MuJoCo の qfrc_bias から静止保持トルク（重力のみ）。joint2〜4 の最大値を失速トルク 4.1 N·m（XM430-W350, 12 V, 2.3 A, ROBOTIS e-Manual）で割って余裕とした。電池 3S が 11 V 台なら失速トルクは約 0.9 倍。動的な加速のトルクは含まない",
            payload="手先（end_effector_link）の点質量 0/100/200/500 g。OpenMANIPULATOR-X の定格ペイロード 500 g（ROBOTIS e-Manual）",
        ),
        yaw_deg=[int(v) for v in d["yaws"]],
    )
    grid = dict(r0=float(R[0]), dr=0.01, nr=NR, z0=float(Z[0]), dz=0.01, nz=NZ, pitch0_deg=int(P[0]), dpitch_deg=3, np=NP)
    combos_json = {}
    for (lim, env), res in combos.items():
        full = (lim, env) in (PRIMARY, ("mech_pi_on_q", "photo_solid"), ("urdf_on_a", "self_floor"))
        combos_json[f"{lim}|{env}"] = build_combo_json(d, lim, env, res, full)
    out = dict(meta=meta, grid=grid, combos=combos_json, web_vs_sim=cmp_, validation=kp)
    (W / "workspace.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (W / "joint_space.json").write_text(json.dumps(js, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("workspace.json", (W / "workspace.json").stat().st_size // 1024, "KB; joint_space.json", (W / "joint_space.json").stat().st_size // 1024, "KB")
    plots(d, combos, js, jdep, inl, web_core)
    return d, combos, js


# ------------------------------------------------------------------ 図
def decorate(ax, plate=True):
    ax.axhline(FLOOR_REL * 100, color="#555", lw=1.2); ax.text(-11, FLOOR_REL * 100 - 1.2, "床", color="#555", fontsize=8, va="top")
    if plate:
        x0, x1 = om.PLATE_X_REAR - om.J2_IN_BASE[0], om.FRONTS["f050"] - om.J2_IN_BASE[0]
        ax.add_patch(plt.Rectangle((x0 * 100, (om.BODY_Z[0] - om.J2_IN_BASE[2]) * 100), (x1 - x0) * 100, (om.PLATE_Z[1] - om.BODY_Z[0]) * 100,
                                   fc="#c9a05a", ec="#8a6a2a", alpha=.55, lw=1))
        ax.add_patch(plt.Rectangle(((-0.024 - 0.033 - om.J2_IN_BASE[0]) * 100, (om.LIDAR_POS[2] - 0.0302 - om.J2_IN_BASE[2]) * 100), 9.4, 3.9, fc="#444", alpha=.7))
    ax.plot([0], [0], "r+", ms=10); ax.text(0.5, 1.5, "joint2 軸", color="r", fontsize=8)
    ax.set_aspect("equal"); ax.set_xlabel("r 前方 [cm]（joint2 軸から）"); ax.set_ylabel("z 高さ [cm]（joint2 軸から）")
    ax.set_xlim(-14, 42); ax.set_ylim(-20, 40); ax.grid(alpha=.25)


def rz_image(ax, arr, cmap, vmin=None, vmax=None, mask=None):
    a = np.where(mask, arr, np.nan) if mask is not None else arr
    im = ax.imshow(a.T, origin="lower", extent=[(R[0] - .005) * 100, (R[-1] + .005) * 100, (Z[0] - .005) * 100, (Z[-1] + .005) * 100],
                   cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    return im


def plots(d, combos, js, jdep, inl, web_core):
    idx = d["idx"]
    # 1. r-z 到達領域（可能な pitch の本数）
    fig, axs = plt.subplots(1, 3, figsize=(17, 6.4))
    for ax, (lim, env), ttl in zip(axs, [PRIMARY, ("mech_pi_on_q", "photo_solid"), ("urdf_on_a", "self_floor")],
                                   ["設計範囲（URDF 限界）＋写真の車体 ［基準］", "サーボ ±π のみ＋写真の車体", "URDF 限界・車体なし（自己衝突と床のみ）"]):
        n = combos[(lim, env)]["n"]
        im = rz_image(ax, n * 3.0, "viridis", 0, 360, mask=n > 0)
        decorate(ax, plate=env != "self_floor"); ax.set_title(f"{ttl}\n{int((n > 0).sum())} cm²", fontsize=10)
        plt.colorbar(im, ax=ax, fraction=.046, label="取れる手先の傾きの合計 [°]（3° 刻みの本数×3°）")
    fig.suptitle("手先が届く領域（yaw=0・真正面）。色は、その点で取れる手先 pitch の範囲の広さ", fontsize=12)
    fig.tight_layout(); fig.savefig(W / "workspace_rz.png", dpi=110); plt.close(fig)
    # 2. pitch ごとの到達領域
    pitches = [-90, -60, -30, 0, 30, 60, 90, 120]
    fig, axs = plt.subplots(2, 4, figsize=(18, 9.4))
    res = combos[PRIMARY]
    for ax, pv in zip(axs.reshape(-1), pitches):
        ip = int(np.argmin(np.abs(P - pv)))
        m = res["cnt"][:, :, ip]
        rz_image(ax, np.ones_like(m, float), "Greens", 0, 1.6, mask=m)
        decorate(ax); ax.set_title(f"手先 pitch ≈ {P[ip]:+d}°（{'水平' if abs(pv) < 5 else ('下向き' if pv > 0 else '上向き')}）  {int(m.sum())} cm²", fontsize=10)
    fig.suptitle("手先の傾きごとの到達領域（基準: URDF 限界＋写真の車体、yaw=0）。pitch=+90° は真下、-90° は真上", fontsize=12)
    fig.tight_layout(); fig.savefig(W / "workspace_pitch.png", dpi=105); plt.close(fig)
    # 3. トルク余裕
    fig, axs = plt.subplots(2, 4, figsize=(18, 9.4))
    res = combos[PRIMARY]
    for j, p in enumerate(sw.PAYLOADS):
        t = res["torque"][p]
        for row, key, ttl in ((0, "best", "最良（その点で一番楽な姿勢）"), (1, "worst", "最悪（その点で一番きつい姿勢）")):
            ax = axs[row, j]
            im = rz_image(ax, t[key], "RdYlGn", 0, 1, mask=res["n"] > 0)
            decorate(ax); ax.set_title(f"ペイロード {int(p * 1000)} g — トルク余裕 {ttl}", fontsize=9)
            plt.colorbar(im, ax=ax, fraction=.046, label="1 − 保持トルク/4.1 N·m")
    fig.suptitle("静止保持トルクの余裕（joint2〜4 の最大値、XM430-W350 の失速 4.1 N·m に対して）。0 以下ならそのサーボでは保持できない", fontsize=11)
    fig.tight_layout(); fig.savefig(W / "workspace_torque.png", dpi=105); plt.close(fig)
    # 4. 衝突で除外された領域
    dep, a = d["dep"], d["a"]
    inlim = an.lim_ok(a, "urdf_on_a")
    selfc = dep[:, 0] > an.TOL; floor = dep[:, 1] > an.TOL
    body = ~an.env_ok0(dep, "photo_solid") & ~selfc & ~floor
    okp = res["ok"]
    cat = np.zeros((NR, NZ), int)                   # 0 届かない / 1 届く(OK) / 2 関節限界だけが理由 / 3 自己衝突 / 4 床 / 5 車体
    kin = np.zeros((NR, NZ), bool)
    ir, iz = idx[:, 0], idx[:, 1]
    kin[ir, iz] = True
    arr = {k: np.zeros((NR, NZ), bool) for k in ("ok", "limit_only", "self", "floor", "body")}
    arr["ok"][ir[okp], iz[okp]] = True
    for nm, m in (("limit_only", ~inlim & ~selfc & ~floor & ~body), ("self", inlim & selfc), ("floor", inlim & ~selfc & floor), ("body", inlim & ~selfc & ~floor & ~env_dummy(dep))):
        arr[nm][ir[m], iz[m]] = True
    cat[kin] = 2
    for code, nm in ((2, "limit_only"), (5, "body"), (4, "floor"), (3, "self")):
        cat[arr[nm] & ~arr["ok"]] = code
    cat[arr["ok"]] = 1
    from matplotlib.colors import ListedColormap
    cm = ListedColormap(["#ffffff", "#7fc97f", "#cccccc", "#d95f02", "#7570b3", "#e7298a"])
    fig, ax = plt.subplots(figsize=(8.5, 8))
    im = ax.imshow(cat.T, origin="lower", extent=[(R[0] - .005) * 100, (R[-1] + .005) * 100, (Z[0] - .005) * 100, (Z[-1] + .005) * 100], cmap=cm, vmin=0, vmax=5, interpolation="nearest")
    decorate(ax)
    import matplotlib.patches as mp
    ax.legend(handles=[mp.Patch(color=c, label=l) for c, l in zip(["#7fc97f", "#cccccc", "#d95f02", "#7570b3", "#e7298a"],
              ["届く（衝突なし・限界内の姿勢がある）", "運動学的には届くが URDF 関節限界で全滅", "自己衝突で全滅", "床との衝突で全滅", "車体（板・車輪・LiDAR）との衝突で全滅"])], loc="upper right", fontsize=8)
    ax.set_title("各セル（yaw=0）で姿勢が全滅する理由（基準: URDF 限界＋写真の車体）")
    fig.tight_layout(); fig.savefig(W / "workspace_excluded.png", dpi=110); plt.close(fig)
    # 5. yaw ごとの到達（真上から見た図）
    fig, axs = plt.subplots(1, 3, figsize=(17, 6))
    for ax, zq in zip(axs, (-0.15, -0.08, 0.05)):
        iz0 = int(round((zq - Z[0]) / 0.01))
        for lim, env, col, lab in (("urdf_on_a", "photo_solid", "#1b9e77", "写真の車体"), ("urdf_on_a", "self_floor", "#cccccc", "車体なし")):
            cm_ = combos[(lim, env)]["yaw_mask"]
            xs, ys = [], []
            for ir_ in range(NR):
                m_ = int(cm_[ir_, iz0])
                for iy, yd in enumerate(d["yaws"]):
                    if m_ >> iy & 1:
                        xs.append(R[ir_] * np.cos(np.radians(yd))); ys.append(R[ir_] * np.sin(np.radians(yd)))
            ax.scatter(np.array(xs) * 100, np.array(ys) * 100, s=6, c=col, label=lab, zorder=2 if env == "photo_solid" else 1)
        x0, x1 = (om.PLATE_X_REAR - om.J2_IN_BASE[0]) * 100, (om.FRONTS["f050"] - om.J2_IN_BASE[0]) * 100
        ax.add_patch(plt.Rectangle((x0, om.PLATE_Y[0] * 100), x1 - x0, (om.PLATE_Y[1] - om.PLATE_Y[0]) * 100, fc="none", ec="#8a6a2a", lw=1.5))
        ax.plot([0], [0], "r+", ms=10); ax.set_aspect("equal"); ax.grid(alpha=.25)
        ax.set_xlim(-40, 42); ax.set_ylim(-42, 42); ax.set_title(f"高さ z={zq * 100:+.0f} cm（床から {(zq - FLOOR_REL) * 100:.1f} cm）で届く位置（上から）", fontsize=10)
        ax.set_xlabel("前方 [cm]"); ax.set_ylabel("左 [cm]"); ax.legend(fontsize=8, loc="upper left")
    fig.suptitle("joint1（yaw）を 15° ごとに回したときの到達位置。茶色の枠が上段の板（写真から）", fontsize=12)
    fig.tight_layout(); fig.savefig(W / "workspace_yaw.png", dpi=105); plt.close(fig)
    # 6. 関節空間: (q2,q3) ごとの joint4 の自由な割合
    z = np.load(an.OUT / "joint_grid.npz"); q = np.degrees(z["q"])
    idxs = [om.GROUPS.index(g) for g in om.VARIANTS["photo_solid"]]
    free = (jdep[..., idxs] <= an.TOL).all(-1)
    fig, axs = plt.subplots(1, 2, figsize=(14, 6.2))
    for ax, ttl, f in ((axs[0], "サーボ ±π のみ＋写真の車体", free), (axs[1], "URDF 限界＋写真の車体", free & inl)):
        im = ax.imshow(f.mean(2).T, origin="lower", extent=[q[0] - 1, q[-1] + 1, q[0] - 1, q[-1] + 1], cmap="viridis", vmin=0, vmax=1)
        ax.set_xlabel("joint2 の読み値 q2 [°]"); ax.set_ylabel("joint3 の読み値 q3 [°]"); ax.set_title(f"{ttl}\n(q2,q3) ごとに joint4 が衝突しない割合"); ax.grid(alpha=.25)
        plt.colorbar(im, ax=ax, fraction=.046)
    fig.tight_layout(); fig.savefig(W / "joint_space.png", dpi=105); plt.close(fig)


def env_dummy(dep):
    """photo_solid に含まれる車体グループ（self/floor 以外）だけが当たっている姿勢でなければ True（= 車体に当たっていない）"""
    return an.env_ok0(dep, "photo_solid")


if __name__ == "__main__":
    main()
