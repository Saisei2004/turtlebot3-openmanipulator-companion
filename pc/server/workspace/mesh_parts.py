"""MuJoCo のメッシュ衝突は凸包になる。細長い非凸のリンクは凸包だと大きすぎて、実機で取れた姿勢まで
「衝突」と判定してしまうので、リンクのメッシュを長手方向のスラブに切り、スラブごとに凸包にする（凸分解の簡易版）。"""
import re
import struct
from pathlib import Path
import numpy as np

SRC = Path("meshes")
DST = Path("meshes/parts")


def read_stl(path):
    d = Path(path).read_bytes()
    if d[:5] == b"solid" and b"facet" in d[:400]:
        v = np.array(re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", d), dtype=float)
        return v.reshape(-1, 3, 3)
    n = struct.unpack("<I", d[80:84])[0]
    a = np.frombuffer(d[84:84 + n * 50], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    return a["v"].astype(float)


def write_stl(path, tris):
    n = len(tris)
    rec = np.zeros(n, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    rec["v"] = tris
    Path(path).write_bytes(b"\0" * 80 + struct.pack("<I", n) + rec.tobytes())


def split(name, parts, axis=None):
    """メッシュ name を主軸方向に parts 個のスラブへ切る。三角形は重心の位置で振り分ける。戻り: 部品名のリスト"""
    DST.mkdir(parents=True, exist_ok=True)
    tris = read_stl(SRC / f"{name}.stl")
    if parts <= 1:
        write_stl(DST / f"{name}_0.stl", tris)
        return [f"{name}_0"]
    pts = tris.reshape(-1, 3)
    if axis is None:
        c = pts - pts.mean(0)
        axis = np.linalg.svd(c, full_matrices=False)[2][0]
    cen = tris.mean(1) @ axis
    edges = np.quantile(cen, np.linspace(0, 1, parts + 1))
    names = []
    for k in range(parts):
        sel = (cen >= edges[k]) & ((cen <= edges[k + 1]) if k == parts - 1 else (cen < edges[k + 1]))
        if sel.sum() < 4:
            continue
        write_stl(DST / f"{name}_{k}.stl", tris[sel])
        names.append(f"{name}_{k}")
    return names


if __name__ == "__main__":
    for nm, n in (("link1", 1), ("link2", 4), ("link3", 6), ("link4", 6), ("link5", 4),
                  ("gripper_left_palm", 3), ("gripper_right_palm", 3)):
        print(nm, split(nm, n))
