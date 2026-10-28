"""ドライバを「試験用」にして（機体には何も送らず、別名のトピックに出す）、円走行・アームの軌道・グリッパー・心拍の指令を記録して確かめる"""
import json
import time

import numpy as np

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pc", "server"))
import circle_driver as cd

node = cd.get_driver(dry=True)
time.sleep(2.0)
q0 = node.joint_q()
print("link:", json.dumps({k: v for k, v in node.status().items() if k in ("link_ok", "scan_age_s")}), "q0", [round(v, 3) for v in q0])

chunks, hb, grip_goals = [], [], []
orig_pts = node._publish_points
node._publish_points = lambda pts: (chunks.append((time.time(), pts)), orig_pts(pts))
orig_alive = node.alive_pub.publish
node.alive_pub.publish = lambda m: (hb.append((time.time(), m.data)), orig_alive(m))
t0 = time.time()
node._send_grip = lambda pos: grip_goals.append((round(time.time() - t0, 1), pos))

node.start(0.30, 0.10, True)
node.start_dance(0.9, q0, True, True, 4.0)
n0 = node.sent
time.sleep(30.0)
s = node.status()
print(f"orbit: sent {node.sent - n0} in 30 s ({(node.sent - n0) / 30:.1f} Hz), cmd_omega {s['cmd_omega']}, blocked {s['blocked']}")
print(f"arm:   {s['arm']['chunks']} trajectory chunks ({s['arm']['chunks'] / 30:.1f} per s), {s['arm']['sent']} points total")
t_stop = time.time()
node.stop("test done", "all")
time.sleep(0.6)
st = node.status()
print("after stop -> orbit running", st["running"], "arm running", st["arm"]["running"], "gripper running", st["gripper"]["running"])

body = [c for c in chunks if c[0] < t_stop - 0.01]
hold = [c for c in chunks if c[0] >= t_stop - 0.01]
gaps = np.diff([c[0] for c in body])
print(f"chunks: {len(body)}, median gap {np.median(gaps) * 1000:.0f} ms (max {gaps.max() * 1000:.0f}), points per chunk {len(body[0][1])}, horizon {body[0][1][-1][2]:.1f} s, first point at +{body[0][1][0][2]:.1f} s")
allq = np.array([p[0] for c in body for p in c[1]]); alldq = np.array([p[1] for c in body for p in c[1]])
lim = np.array([[-2.8274, 2.8274], [-2.7207, 0.6408], [-1.0125, 1.3123], [-0.1407, 3.1416]])
print("max |velocity| per joint (rad/s):", np.round(np.abs(alldq).max(0), 2).tolist())
print("within joint limits:", bool(((allq > lim[:, 0]).all() and (allq < lim[:, 1]).all())))
# 連続する塊の重なり: 後の塊の点が、前の塊の同じ時刻の点とどれだけずれるか
mism = 0.0
for (ta, pa), (tb, pb) in zip(body[:-1], body[1:]):
    off = tb - ta
    for q, dq, h in pb:
        ha = h + off
        for qa, dqa, hh in pa:
            if abs(hh - ha) < 0.011:
                mism = max(mism, float(np.abs(np.array(q) - np.array(qa)).max()))
print(f"max position mismatch between overlapping chunks: {mism:.4f} rad (0.02 s の時刻ずれ分を含む)")
print("hold command at stop: zero velocity", hold[-1][1][0][1], "over", hold[-1][1][0][2], "s") if hold else print("no hold command")
masks = sorted(set(m for _, m in hb))
rate = len([h for h in hb if h[0] < t_stop]) / 30
print(f"heartbeat: {rate:.1f} Hz while running, mask values {masks} (7 = 車輪 + アーム + グリッパー, 0 = 自分で止めた), last = {hb[-1][1]}")
print(f"gripper: {len(grip_goals)} goals:", grip_goals[:6])
