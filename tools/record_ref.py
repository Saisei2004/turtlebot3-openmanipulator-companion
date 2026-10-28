#!/usr/bin/env python3
# コントローラが出している指令位置（reference）を記録して、動いている区間の速度のなめらかさを見る
import time, sys, rclpy, numpy as np
from rclpy.node import Node
from control_msgs.msg import JointTrajectoryControllerState
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
rclpy.init(); n = Node("record_ref"); rows = []
n.create_subscription(JointTrajectoryControllerState, "/arm_controller/controller_state",
    lambda m: rows.append((m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, list(m.reference.positions), list(m.reference.velocities))), 100)
t0 = time.time()
while time.time() - t0 < dur: rclpy.spin_once(n, timeout_sec=0.005)
t = np.array([r[0] for r in rows]); q = np.array([r[1] for r in rows]); rv = np.array([r[2] for r in rows])
dq = np.abs(np.diff(q, axis=0)).max(axis=1)
idx = np.where(dq > 2e-5)[0]
print(f"samples {len(rows)} in {dur:.0f} s ({len(rows)/dur:.0f}/s); samples with motion {len(idx)}")
if len(idx) < 4: print("no motion"); sys.exit()
# 0.3 秒以上あいたら別の動きとして分け、いちばん長い動きを見る
clusters, cur = [], [idx[0]]
for i in idx[1:]:
    if t[i] - t[cur[-1]] > 0.3: clusters.append(cur); cur = [i]
    else: cur.append(i)
clusters.append(cur)
for c in sorted(clusters, key=len, reverse=True)[:2]:
    a, b = c[0], c[-1] + 1
    tt, qq = t[a:b+1], q[a:b+1]; j = np.argmax(np.abs(qq[-1] - qq[0]))
    step = np.diff(qq[:, j]); dts = np.diff(tt); v = step / dts
    sm = np.convolve(v, np.ones(3)/3, mode="valid")
    print(f"- motion on joint {j+1}: {abs(qq[-1,j]-qq[0,j]):.3f} rad in {tt[-1]-tt[0]:.2f} s, {len(step)} samples, "
          f"sample gap median {np.median(dts)*1000:.0f} ms max {dts.max()*1000:.0f} ms")
    print('  reference velocity (rad/s) along the motion:', ' '.join(f'{x:+.2f}' for x in rv[a:b+1, j][::max(1, (b-a)//24)]))
    mid = v[len(v)//4: 3*len(v)//4]
    print(f"  velocity mid-phase mean {mid.mean():+.3f} rad/s, std {mid.std():.3f} ({abs(mid.std()/mid.mean())*100:.0f}% of mean); "
          f"max |step-to-step change| {np.abs(np.diff(sm)).max():.3f} rad/s")
