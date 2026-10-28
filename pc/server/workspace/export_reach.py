"""workspace.json の基準組み合わせから、画面用の小さな到達領域データ webui/reach.json を作る。
セル（r, z を 1 cm）ごとに、届く手先の傾き（pitch、3° 刻み 120 本）のビットを詰めて base64 にする。"""
import json, base64, numpy as np
w = json.load(open("workspace.json", encoding="utf-8"))
g = w["grid"]; nr, nz, npch = g["nr"], g["nz"], g["np"]
combo = w["combos"]["urdf_on_a|photo_solid"]
runs = combo["pitch_runs_deg"]
bits = np.zeros((nr, nz, npch), bool)
for key, rs in runs.items():
    ir, iz = map(int, key.split(","))
    for lo, hi in rs:
        for k in range(npch):
            p = g["pitch0_deg"] + k * g["dpitch_deg"]
            if lo - 1e-6 <= p <= hi + 1e-6: bits[ir, iz, k] = True
packed = np.packbits(bits.reshape(-1))
out = dict(r0=g["r0"], dr=g["dr"], nr=nr, z0=g["z0"], dz=g["dz"], nz=nz, pitch0=g["pitch0_deg"], dpitch=g["dpitch_deg"], np=npch,
           note="bit index = (ir*nz + iz)*np + k; ir=round((r-r0)/dr), iz=round((z-z0)/dz), k=round((pitch_deg-pitch0)/dpitch). 条件: URDF 限界を a に適用・写真から測った車体・床との衝突なし・めり込み 2mm まで許容",
           bits=base64.b64encode(packed.tobytes()).decode("ascii"))
json.dump(out, open("../webui/reach.json", "w"), separators=(",", ":"))
n = int(bits.any(-1).sum()); print("cells reachable", n, "area_cm2", combo["area_cm2"], "poses", int(bits.sum()), "bytes", len(out["bits"]))
# 検算: n_pitch と一致するか
npc = np.array(combo["n_pitch"]).reshape(nr, nz)
print("n_pitch consistent:", int((bits.sum(-1) == npc).all()), "max diff", int(np.abs(bits.sum(-1) - npc).max()))
