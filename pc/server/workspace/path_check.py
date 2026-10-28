"""関節空間の直線補間（コントローラの動き方）に沿って衝突・限界を調べる"""
import numpy as np, sim_common as sc
s = sc.Sim()
def path(q0, q1, n=60):
    worst, hit = 0.0, set()
    for t in np.linspace(0, 1, n):
        a = np.array(q0) * (1 - t) + np.array(q1) * t + sc.OFFSET
        d = s.depths(a)
        import omx_model as om
        idx = [om.GROUPS.index(g) for g in om.VARIANTS["photo_solid"]]
        w = max(d[i] for i in idx)
        if w > 0.002: hit |= {om.GROUPS[i] for i in idx if d[i] > 0.002}
        worst = max(worst, w)
    lim = [k + 1 for k in range(4) if min(np.array(q0)[k], np.array(q1)[k]) + sc.OFFSET[k] < sc.URDF_LIM[k][0] or max(np.array(q0)[k], np.array(q1)[k]) + sc.OFFSET[k] > sc.URDF_LIM[k][1]]
    return round(worst * 1000, 1), sorted(hit), lim
READY = [0, -0.93, -0.07, 1.65]
STOW = list(np.array([0, -1.05, 1.05, 0]) - sc.OFFSET)
CUR = [-0.005, -1.26, 1.05, 0.43]
OLD = [-0.0199, -0.813, 1.5142, 0.0337]
print("STOW q =", np.round(STOW, 3).tolist())
for name, a, b in [("CUR->READY", CUR, READY), ("READY->STOW", READY, STOW), ("STOW->READY", STOW, READY), ("CUR->STOW", CUR, STOW), ("READY->OLDHOME", READY, OLD), ("STOW->OLDHOME", STOW, OLD)]:
    print(f"{name:16s} worst depth mm / hit / limit-violating joints:", path(a, b))
for nm, q in [("STOW", STOW), ("READY", READY), ("CUR", CUR), ("OLD home", OLD)]:
    a = np.array(q) + sc.OFFSET; tau = np.abs(sc.Sim(0.2).hold_torque(a)).max() / sc.TAU_STALL
    print(f"{nm:9s} tip(r,z,pitch deg)", np.round(np.array(sc.fk_a(a))*[100,100,180/np.pi],1).tolist(), " torque %% of stall (200g): %.0f" % (tau*100))
