"""感度・検算: 許容めり込み、グリッパー開閉、肘の解の別、トルクの検算（解析式 vs MuJoCo）、画面の限界を直した場合"""
import json
import numpy as np
import analyze as an
import omx_model as om
import sim_common as sc
import sweep as sw

out = {}
d = an.load_ik()
dep, a, idx = d["dep"], d["a"], d["idx"]
NR, NZ = an.NR, an.NZ


def area(ok):
    c = np.zeros((NR, NZ), bool); c[idx[ok, 0], idx[ok, 1]] = True
    return int(c.sum())


inl = an.lim_ok(a, "urdf_on_a")
gi = [om.GROUPS.index(g) for g in om.VARIANTS["photo_solid"]]
# 1. めり込みの許容を変えたとき（基準 = 2 mm）
out["tolerance_mm"] = {}
for t in (0.0, 1.0, 2.0, 4.0, 6.0):
    u = int(round(t * sc.QUANT))
    ok = inl & (dep[:, gi] <= u).all(1)
    out["tolerance_mm"][str(t)] = dict(area_cm2=area(ok), poses=int(ok.sum()))
# 2. グリッパーを閉じた(-10 mm)とき
z = np.load(an.OUT / "ik_grid_gripclosed.npz")
okc = inl & (z["dep"][:, gi] <= an.TOL).all(1)
oko = inl & (dep[:, gi] <= an.TOL).all(1)
out["gripper"] = dict(open_19mm=dict(area_cm2=area(oko), poses=int(oko.sum())), closed_minus10mm=dict(area_cm2=area(okc), poses=int(okc.sum())))
# 3. 肘の解（URDF 限界・基準）。画面の arm_kin.js は elbow index 0 の解しか使わない
for e in (0, 1):
    m = oko & (idx[:, 3] == e)
    out.setdefault("elbow_poses", {})[f"elbow_{'minus' if e == 0 else 'plus'}1"] = dict(poses=int(m.sum()), area_cm2=area(m))
only1 = oko & (idx[:, 3] == 1)
c0 = np.zeros((NR, NZ), bool); c0[idx[oko & (idx[:, 3] == 0), 0], idx[oko & (idx[:, 3] == 0), 1]] = True
c1 = np.zeros((NR, NZ), bool); c1[idx[only1, 0], idx[only1, 1]] = True
out["elbow_poses"]["cells_only_reachable_with_elbow_plus1"] = int((c1 & ~c0).sum())
# 4. 画面の関節限界を「URDF 限界を q に直したもの」にした場合の一致
q_web = d["a_raw"] - sc.OFFSET
newlim = np.array([[-9, 9], [sc.URDF_LIM[1, 0] - sc.OFFSET[1], sc.URDF_LIM[1, 1] - sc.OFFSET[1]],
                   [sc.URDF_LIM[2, 0] - sc.OFFSET[2], sc.URDF_LIM[2, 1] - sc.OFFSET[2]],
                   [sc.URDF_LIM[3, 0] - sc.OFFSET[3], min(sc.URDF_LIM[3, 1] - sc.OFFSET[3], np.pi)]])
ok_new = ((q_web[:, 1:4] >= newlim[1:4, 0]) & (q_web[:, 1:4] <= newlim[1:4, 1])).all(1)
r = sw.R_GRID[idx[:, 0]]; zz = sw.Z_GRID[idx[:, 1]]
reg = (idx[:, 3] == 0) & (r >= 0.06)
for guard in (-0.08, -0.17):
    web_new = ok_new & reg & (zz >= guard - 1e-9)
    sim = oko & reg & (zz >= guard - 1e-9)
    out.setdefault("web_with_limits_converted_to_q", {})[f"guard_{int(guard * 100)}cm"] = dict(
        both=int((web_new & sim).sum()), web_only=int((web_new & ~sim).sum()), sim_only=int((~web_new & sim).sum()),
        web_only_reasons=an.reasons(d, web_new & ~sim))
out["q_limits_urdf_converted"] = {k: [round(float(x), 4) for x in newlim[i]] for i, k in ((1, "joint2"), (2, "joint3"), (3, "joint4"))}
# 5. トルクの検算: 平面 3 リンクの静力学（URDF の質量・重心から）と MuJoCo の保持トルクを比べる
import xml.etree.ElementTree as ET
r_ = ET.parse("robot.urdf").getroot()
L = {l.get("name"): l for l in r_.findall("link")}
J = {j.get("name"): j for j in r_.findall("joint")}
def mc(link):
    i = L[link].find("inertial"); return float(i.find("mass").get("value")), np.array([float(x) for x in i.find("origin").get("xyz").split()])
def org(j): return np.array([float(x) for x in J[j].find("origin").get("xyz").split()])
M = {k: mc(k) for k in ("link3", "link4", "link5", "gripper_left_link", "gripper_right_link", "link2")}
def tau_analytic(a, payload):
    """joint2,3,4 の保持トルク（y 軸まわり）。a=[a1,a2,a3,a4]。重力は -z。平面（x-z）で計算"""
    a2, a3, a4 = a[1], a[1] + a[2], a[1] + a[2] + a[3]
    def R(t): return np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])      # arm_kin.js の rot と同じ（y 軸まわり）
    def xz(v): return np.array([v[0], v[2]])
    p2 = np.zeros(2)                       # joint2 軸（link3 の原点）
    p3 = p2 + R(a2) @ xz(org("joint3"))
    p4 = p3 + R(a3) @ xz(org("joint4"))
    com = {"link3": p2 + R(a2) @ xz(M["link3"][1]), "link4": p3 + R(a3) @ xz(M["link4"][1]), "link5": p4 + R(a4) @ xz(M["link5"][1])}
    tip = p4 + R(a4) @ xz(np.array(om.TIP_POS))
    masses = [("link3", M["link3"][0]), ("link4", M["link4"][0]), ("link5", M["link5"][0]), ("gl", 0.001), ("gr", 0.001), ("pay", payload)]
    comp = dict(com); comp["gl"] = p4 + R(a4) @ np.array([0.0817, 0]); comp["gr"] = comp["gl"]; comp["pay"] = tip
    out_t = []
    for pj, own in ((p2, ("link3", "link4", "link5", "gl", "gr", "pay")), (p3, ("link4", "link5", "gl", "gr", "pay")), (p4, ("link5", "gl", "gr", "pay"))):
        t = 0.0
        for nm, m in masses:
            if nm in own:
                rx = comp[nm][0] - pj[0]
                t += m * 9.81 * rx                      # 重力による y 軸まわりのモーメント（前方の重りが関節を前に倒そうとする）
        out_t.append(t)
    return np.array(out_t)
rng = np.random.default_rng(3)
errs = []
S0 = sc.Sim(payload_kg=0.3, with_env=False)
for _ in range(1500):
    aa = np.array([0, rng.uniform(-1.7, 1.5), rng.uniform(-0.9, 1.3), rng.uniform(-1.7, 2.0)])
    t_mj = S0.hold_torque(aa)[1:4]
    t_an = tau_analytic(aa, 0.3)
    errs.append(np.abs(np.abs(t_mj) - np.abs(t_an)).max())
out["torque_cross_check"] = dict(samples=1500, payload_kg=0.3, max_abs_diff_Nm=round(float(max(errs)), 4), median_abs_diff_Nm=round(float(np.median(errs)), 5))
tau = d["tau"]
out["torque_summary"] = {f"{int(p * 1000)}g": dict(max_Nm=round(float(np.nanmax(tau[:, j])), 3), margin_min=round(float(1 - np.nanmax(tau[:, j]) / sc.TAU_STALL), 3),
                                                      frac_of_stall_max=round(float(np.nanmax(tau[:, j]) / sc.TAU_STALL), 3),
                                                      frac_of_stall_at_11v=round(float(np.nanmax(tau[:, j]) / (sc.TAU_STALL * 11.1 / 12)), 3)) for j, p in enumerate(sw.PAYLOADS)}
# 基準セル内に限ったトルク最大
prim = an.analyze_combo(d, "urdf_on_a", "photo_solid")
out["torque_summary_in_primary_workspace"] = {f"{int(p * 1000)}g": round(float(np.nanmax(np.where(prim["ok"], tau[:, j], np.nan))), 3) for j, p in enumerate(sw.PAYLOADS)}
json.dump(out, open("sensitivity.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
