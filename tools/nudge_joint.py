#!/usr/bin/env python3
"""アームの関節を 1 つだけ少し動かす（調整用）。usage: nudge_joint.py <joint1..4> <delta_rad> [sec]
今の関節角を /joint_states から読み、指定の関節だけ delta 足した姿勢へ sec 秒で動かす。"""
import sys
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Duration

JOINTS = ["joint1", "joint2", "joint3", "joint4"]


def main():
    name, delta = sys.argv[1], float(sys.argv[2])
    sec = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
    if name not in JOINTS or abs(delta) > 0.6:
        sys.exit("joint は joint1..4、delta は ±0.6 rad まで")
    rclpy.init()
    node = Node("nudge_joint")
    cur = {}
    node.create_subscription(JointState, "/joint_states", lambda m: cur.update(zip(m.name, m.position)), 10)
    pub = node.create_publisher(JointTrajectory, "/arm_controller/joint_trajectory", 10)
    t0 = time.time()
    while not all(j in cur for j in JOINTS) or pub.get_subscription_count() == 0:
        rclpy.spin_once(node, timeout_sec=0.1)
        if time.time() - t0 > 10:
            sys.exit("joint_states かコントローラが見つかりません")
    q = [cur[j] for j in JOINTS]
    q[JOINTS.index(name)] += delta
    msg = JointTrajectory(joint_names=JOINTS)
    msg.points = [JointTrajectoryPoint(positions=q, time_from_start=Duration(sec=int(sec), nanosec=int((sec % 1) * 1e9)))]
    pub.publish(msg)
    print("before", [round(cur[j], 3) for j in JOINTS], "target", [round(v, 3) for v in q], flush=True)
    end = time.time() + sec + 0.8
    while time.time() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    print("after ", [round(cur[j], 3) for j in JOINTS], flush=True)
    rclpy.shutdown()


if __name__ == "__main__":
    main()
