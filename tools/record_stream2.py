#!/usr/bin/env python3
"""機体側で、PC から来た指令（位置・速度）・コントローラの指令位置・実際の関節の位置を同時に記録し、追従のよさとなめらかさを測る"""
import sys
import time

import numpy as np
import rclpy
from control_msgs.msg import JointTrajectoryControllerState
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Int8
from trajectory_msgs.msg import JointTrajectory

J = ["joint1", "joint2", "joint3", "joint4"]
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
rclpy.init()
n = Node("record_stream2")
cmd, ref, act, hb = [], [], [], []


def on_cmd(m):
    p = m.points[0]
    cmd.append((time.time(), list(p.positions), list(p.velocities), p.time_from_start.sec + p.time_from_start.nanosec * 1e-9))


n.create_subscription(JointTrajectory, "/arm_controller/joint_trajectory", on_cmd, 50)
n.create_subscription(JointTrajectoryControllerState, "/arm_controller/controller_state",
                      lambda m: ref.append((m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, list(m.reference.positions), list(m.reference.velocities))), 100)
n.create_subscription(JointState, "/joint_states", lambda m: act.append((time.time(), [dict(zip(m.name, m.position)).get(j, np.nan) for j in J])), 50)
n.create_subscription(Int8, "/tb3_pc_alive", lambda m: hb.append((time.time(), m.data)), 50)
t0 = time.time()
while time.time() - t0 < dur:
    rclpy.spin_once(n, timeout_sec=0.005)
if len(cmd) < 20:
    print("no stream"); sys.exit()
ct = np.array([c[0] for c in cmd]); cq = np.array([c[1] for c in cmd]); cdq = np.array([c[2] for c in cmd])
print(f"commands from the PC: {len(cmd)} messages, horizon {cmd[5][3]:.2f} s, median gap {np.median(np.diff(ct)) * 1000:.0f} ms, max gap {np.diff(ct).max() * 1000:.0f} ms")
print("commanded |velocity| max per joint:", np.round(np.abs(cdq).max(0), 2).tolist(), " (計画は 0.5 rad/s 以下)")
# 指令位置 q(t+h) を時刻 t に直して、コントローラの reference と比べる
rt = np.array([r[0] for r in ref]); rq = np.array([r[1] for r in ref]); rdq = np.array([r[2] for r in ref])
# stamp は ROS 時刻（= time.time()）
k0 = min(8, len(ct) - 2)
mid = (rt > ct[k0]) & (rt < ct[-1])
g = np.arange(rt[mid][0], rt[mid][-1], 0.01)
rqi = np.stack([np.interp(g, rt[mid], rq[mid][:, j]) for j in range(4)], 1)
v = np.gradient(rqi, 0.01, axis=0); a = np.gradient(v, 0.01, axis=0)
print("controller reference, finite-difference |velocity| max:", np.round(np.abs(v).max(0), 2).tolist(), " |accel| max:", np.round(np.abs(a).max(0), 1).tolist())
print("controller-reported |velocity| max (p95):", np.round(np.percentile(np.abs(rdq[mid]), 95, axis=0), 2).tolist(), "max", np.round(np.abs(rdq[mid]).max(0), 2).tolist())
# 実際の位置が、指令位置にどれだけ遅れて付いてくるか
at = np.array([x[0] for x in act]); aq = np.array([x[1] for x in act])
m2 = (at > ct[k0]) & (at < ct[-1])
lags = []
for j in range(4):
    best = None
    for lag in np.arange(0.0, 0.6, 0.02):
        e = np.abs(aq[m2][:, j] - np.interp(at[m2] - lag, g, rqi[:, j], left=np.nan, right=np.nan))
        e = e[~np.isnan(e)]
        if len(e) > 10 and (best is None or e.mean() < best[1]):
            best = (lag, e.mean(), e.max())
    lags.append(best)
print("actual position vs reference: best lag [s], mean error [rad], max error [rad] per joint:", [(round(b[0], 2), round(b[1], 3), round(b[2], 3)) for b in lags])

# ---- PC が止まったとき（心拍が途切れたとき）に、腕が何秒で止まったか ----
if hb:
    last_hb = hb[-1][0]
    run = [h[0] for h in hb if h[1] != 0]
    gaps_hb = np.diff(run) if len(run) > 3 else np.array([0.05])
    print(f"heartbeat gaps at the robot (Wi-Fi): median {np.median(gaps_hb) * 1000:.0f} ms, p99 {np.percentile(gaps_hb, 99) * 1000:.0f} ms, max {gaps_hb.max() * 1000:.0f} ms, gaps over 150 ms: {(gaps_hb > 0.15).sum()} of {len(gaps_hb)}")
    ts = np.array([r[0] for r in ref]); qs = np.array([r[1] for r in ref])
    # 指令位置の動き（有限差分の速度）が 0.02 rad/s 未満になった時刻
    sp = np.abs(np.gradient(qs, ts, axis=0)).max(1)
    after_i = np.where(ts > last_hb)[0]
    quiet = [i for i in after_i if sp[i] < 0.02]
    print(f"last heartbeat at +{last_hb - t0:.1f} s (value {hb[-1][1]}); heartbeats {len(hb)} total")
    print("commanded position speed (finite diff) just before the last heartbeat: %.2f rad/s" % sp[(ts > last_hb - 0.3) & (ts <= last_hb)].max())
    print("commanded position stopped moving %.2f s after the last heartbeat" % (ts[quiet[0]] - last_hb) if quiet else "commanded position did not stop")
    sp2 = [(a, max(abs(x) for x in d) if len(d) else 0) for a, d in zip(at, [np.abs(r) for r in aq])]
    meas = np.abs(np.gradient(aq, at, axis=0)).max(1)
    mi = [i for i in np.where(at > last_hb)[0] if meas[i] < 0.05]
    print("measured joint position stopped (finite diff < 0.05 rad/s) %.2f s after the last heartbeat" % (at[mi[0]] - last_hb) if mi else "measured joints still moving")
