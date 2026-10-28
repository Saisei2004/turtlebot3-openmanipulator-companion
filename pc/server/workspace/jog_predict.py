"""READY から手先を後ろへ（r を減らす）動かしたとき、どこで IK 限界・衝突になるかを MuJoCo で予測する"""
import numpy as np, sim_common as sc, omx_model as om
s = sc.Sim(); idx = [om.GROUPS.index(g) for g in om.VARIANTS["photo_solid"]]
lim = np.array([[-2.8274, 2.8274], [-1.7907, 1.5708], [-0.9425, 1.3823], [-1.7907, 2.0420]])
import sys
z, pitch = float(sys.argv[1]), float(sys.argv[2])
for r100 in np.arange(27.4, 5.0, -0.5):
    r = r100 / 100
    a = sc.ik_a(r, z, pitch, -1)
    if np.isnan(a).any(): print(f"r={r100:.1f} cm: IK unreachable"); break
    out = [k + 1 for k in range(4) if a[k] < lim[k][0] or a[k] > lim[k][1]]
    d = s.depths(a); w = max(d[i] for i in idx); hit = [om.GROUPS[i] for i in idx if d[i] > 0.002]
    if out or hit:
        print(f"r={r100:.1f} cm z=12.8 pitch 0: z=%.1f first problem -> limit joints {out}, hits {hit}, depth {w*1000:.1f} mm" % (z*100)); break
else:
    print("no problem down to r=5")
