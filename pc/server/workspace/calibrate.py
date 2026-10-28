"""モデルの検証: (1) MuJoCo の手先位置 = 解析 FK（arm_kin.js と同じ式）か、(2) 実機で確認済みの姿勢が衝突なしと出るか"""
import numpy as np
import sim_common as sc

S = sc.Sim()
import omx_model as om
rng = np.random.default_rng(0)

# (1) FK の一致
err = []
for _ in range(500):
    a = np.concatenate([[rng.uniform(-3, 3)], rng.uniform(-1.5, 1.5, 3)])
    r, z, _y = S.tip_rz(a)
    xe, ze, pe = sc.fk_a(a)
    err.append(max(abs(r - xe), abs(z - ze)))
print(f"[FK] MuJoCo と解析式の手先位置の差: 最大 {max(err) * 1000:.4f} mm（500 姿勢）")

a = sc.ik_a(np.array([0.2, 0.15]), np.array([0.05, -0.1]), np.array([0.4, 1.2]), -1)
print("[IK] 往復の差:", np.abs(np.array(sc.fk_a(a)) - np.array([[0.2, 0.15], [0.05, -0.1], [0.4, 1.2]])).max())

# (2) 実機で取れた姿勢（q は /joint_states 側）
known = {
    "全関節0 (カメラで撮影・上腕が前へ倒れた形)": [0, 0, 0, 0],
    "READY q=[0,-0.93,-0.07,1.65] (L字)": [0, -0.93, -0.07, 1.65],
    "写真の姿勢 q=[-0.02,-0.561,0.865,1.092]": [-0.02, -0.561, 0.865, 1.092],
    "旧構成 home q=[-0.0199,-0.813,1.5142,0.0337]（今の OFFSET 込みでは実在しない姿勢）": [-0.0199, -0.813, 1.5142, 0.0337],
}
# 参考: OMX 標準の折りたたみ姿勢を URDF 側の角 a としてそのまま与える（OMX の標準ホーム姿勢）
known_a = {"OMX 標準 init a=[0,-1.05,1.05,0]": [0, -1.05, 1.05, 0],
           "旧 home を a として読む a=[-0.0199,-0.813,1.5142,0.0337]": [-0.0199, -0.813, 1.5142, 0.0337]}
S.m.geom_margin[:] = 0.006       # 近接も拾う（6 mm）
for g in (0.019, -0.010):
    S.set_grip(g)
    print(f"\n--- グリッパー {g * 1000:+.0f} mm ---")
    for name, q in known.items():
        a = np.array(q) + sc.OFFSET
        r, z, _ = S.tip_rz(a)
        pitch = np.degrees(a[1] + a[2] + a[3])
        dep = S.depths(a) * 1000
        worst = {om.GROUPS[i]: round(v, 1) for i, v in enumerate(dep) if v > 0}
        print(f"{name}\n   手先 r={r * 100:.1f} cm z={z * 100:.1f} cm pitch={pitch:.0f}°  a={np.round(a, 3)}  めり込み(mm) {worst or 'なし'}")

print("\n--- 折りたたみ姿勢（a を直接指定）---")
S.set_grip(0.019)
for name, a in known_a.items():
    a = np.array(a)
    r, z, _ = S.tip_rz(a)
    dep = S.depths(a) * 1000
    print(f"{name}: 手先 r={r * 100:.1f} z={z * 100:.1f} めり込み(mm)", {om.GROUPS[i]: round(v, 1) for i, v in enumerate(dep) if v > 0} or "なし")
