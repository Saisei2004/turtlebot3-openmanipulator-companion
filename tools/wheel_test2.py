#!/usr/bin/env python3
# 0.05 m/s で約 2 秒だけ前進指令を出し、車輪の角度が変わるか見る（機体の中で動かす）
import time, rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import JointState
from nav_msgs.msg import Odometry
rclpy.init(); n = Node("wheel_test2")
pos = {}; odom = [None]
n.create_subscription(JointState, "/joint_states", lambda m: pos.update(zip(m.name, m.position)), 10)
n.create_subscription(Odometry, "/odom", lambda m: odom.__setitem__(0, (m.pose.pose.position.x, m.twist.twist.linear.x)), 10)
pub = n.create_publisher(Twist, "/cmd_vel", 10)
t0 = time.time()
while (len(pos) < 6 or pub.get_subscription_count() == 0) and time.time() - t0 < 8: rclpy.spin_once(n, timeout_sec=0.1)
time.sleep(0.5); [rclpy.spin_once(n, timeout_sec=0.05) for _ in range(10)]
w0 = (pos["wheel_left_joint"], pos["wheel_right_joint"])
print("subscribers on /cmd_vel:", pub.get_subscription_count(), "start wheels", [round(v, 3) for v in w0])
t1 = time.time(); m = Twist(); m.linear.x = 0.05
vmax = 0
while time.time() - t1 < 2.0:
    pub.publish(m); rclpy.spin_once(n, timeout_sec=0.05)
    if odom[0]: vmax = max(vmax, abs(odom[0][1]))
pub.publish(Twist())
t2 = time.time()
while time.time() - t2 < 1.0: rclpy.spin_once(n, timeout_sec=0.05)
w1 = (pos["wheel_left_joint"], pos["wheel_right_joint"])
print("end wheels", [round(v, 3) for v in w1], "delta", [round(b - a, 3) for a, b in zip(w0, w1)], "max odom speed", round(vmax, 3))
