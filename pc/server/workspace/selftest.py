"""MuJoCo のモデルが読めて、既知の姿勢で期待どおりの衝突判定になるか（機体なし）。pc/server/workspace で動かす"""
import sys
import numpy as np
import omx_model as om
import sim_common as sc

s = sc.Sim()
idx = [om.GROUPS.index(g) for g in om.VARIANTS["photo_solid"]]
worst = lambda q: max(float(s.depths(np.array(q) + sc.OFFSET)[i]) for i in idx) * 1000     # [mm]
cases = [("READY（衝突なし）", [0, -0.93, -0.07, 1.65], False), ("折りたたみ HOME（衝突なし）", [0, -1.98, 0.98, 1.65], False),
         ("旧 home（自己衝突 23.5 mm）", [-0.0199, -0.813, 1.5142, 0.0337], True), ("LiDAR・板に当たる姿勢", [0, -0.93, 1.0, 1.65], True)]
ng = 0
for name, q, expect_hit in cases:
    w = worst(q)
    ok = (w > 2.0) == expect_hit
    ng += not ok
    print(("OK   " if ok else "NG   ") + f"{name}: 最大めり込み {w:.1f} mm")
sys.exit(1 if ng else 0)
