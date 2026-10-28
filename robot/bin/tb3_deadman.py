#!/usr/bin/env python3
"""機体側の見張り。PC の円走行・アーム・グリッパーのドライバが出す心拍（/tb3_pc_alive）が 0.3 秒途切れたら、
アームをその場で止め、車輪を止める。PC が落ちた・ネットワークが切れた・PC が固まったときに、動き続けないための仕組み。

心拍の値は「今 PC が動かしているもの」のビット: 1 = 車輪, 2 = アーム, 4 = グリッパー。0 は「PC が自分で止めた（見張り不要）」。
"""
import time

import rclpy
from builtin_interfaces.msg import Duration
from control_msgs.msg import JointTrajectoryControllerState
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Int8
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

TIMEOUT_S = 0.3
JOINTS = ["joint1", "joint2", "joint3", "joint4"]


class Deadman(Node):
    def __init__(self):
        super().__init__("tb3_deadman")
        self.mask = 0
        self.t_hb = 0.0
        self.ref = None
        self.create_subscription(Int8, "/tb3_pc_alive", self._on_hb, 10)
        self.create_subscription(JointTrajectoryControllerState, "/arm_controller/controller_state", self._on_state, 10)
        self.arm_pub = self.create_publisher(JointTrajectory, "/arm_controller/joint_trajectory", 10)
        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_timer(0.05, self._tick)
        self.get_logger().info("deadman ready (timeout %.1f s)" % TIMEOUT_S)

    def _on_hb(self, m):
        if m.data != 0 and self.mask == 0:
            self.get_logger().info("armed (mask %d)" % m.data)
        self.mask, self.t_hb = int(m.data), time.time()

    def _on_state(self, m):
        if all(j in m.joint_names for j in JOINTS):
            self.ref = [m.reference.positions[m.joint_names.index(j)] for j in JOINTS]

    def _tick(self):
        if self.mask == 0 or time.time() - self.t_hb <= TIMEOUT_S:
            return
        mask, self.mask = self.mask, 0
        self.get_logger().warn("PC heartbeat lost (mask %d) -> stopping" % mask)
        if mask & 1:
            for _ in range(3):
                self.cmd_pub.publish(Twist())
        if mask & 2 and self.ref is not None:
            pt = JointTrajectoryPoint(positions=[float(v) for v in self.ref], velocities=[0.0] * 4)
            pt.time_from_start = Duration(sec=0, nanosec=250_000_000)
            self.arm_pub.publish(JointTrajectory(joint_names=JOINTS, points=[pt]))


def main():
    rclpy.init()
    rclpy.spin(Deadman())


if __name__ == "__main__":
    main()
