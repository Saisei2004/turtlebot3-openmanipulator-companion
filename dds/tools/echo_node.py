#!/usr/bin/env python3
"""機体側（または相手側）で動かす折り返しノード。pingpong.py が送る /<ns>/ping をそのまま /<ns>/pong に返す。

機体で動かすときは、機体の ROS 2 環境（ROS_DOMAIN_ID と Fast DDS のプロファイル）を、サービスと同じにして動かすこと。
  source /opt/ros/humble/setup.bash
  export ROS_DOMAIN_ID=0
  export FASTRTPS_DEFAULT_PROFILES_FILE=...   # 機体のサービスと同じもの（run_matrix.sh の --robot-ssh は自動で探す）
  python3 echo_node.py --qos reliable

QoS は pingpong.py と同じにする（reliable の購読は best_effort の発行とつながらない）。
"""
import argparse
import array
import struct
import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import UInt8MultiArray

import common


class Echo(Node):
    def __init__(self, ns, qos_kind, depth):
        super().__init__("tb3_dds_echo")
        q = common.qos(qos_kind, depth)
        self.pub = self.create_publisher(UInt8MultiArray, f"{ns}/pong", q)
        self.create_subscription(UInt8MultiArray, f"{ns}/ping", self.on_ping, q)
        self.n = 0
        self.last_seq = None
        self.gaps = 0
        self.t_first = None

    def on_ping(self, m):
        out = UInt8MultiArray()
        out.data = array.array("B", bytes(m.data))
        self.pub.publish(out)
        self.n += 1
        if self.t_first is None:
            self.t_first = time.time()
        if len(m.data) >= 8:
            seq = struct.unpack_from("<Q", bytes(m.data[:8]))[0]
            if self.last_seq is not None and seq != self.last_seq + 1:
                self.gaps += 1
            self.last_seq = seq


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ns", default="/tb3_dds", help="トピックの接頭辞（既定 /tb3_dds）")
    ap.add_argument("--qos", choices=["reliable", "best_effort"], default="reliable")
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--duration", type=float, default=0, help="動かす秒数（0 = Ctrl-C まで）")
    ap.add_argument("--report-every", type=float, default=10, help="何秒ごとに件数を表示するか（0 で表示しない）")
    a = ap.parse_args()
    rclpy.init()
    node = Echo(a.ns, a.qos, a.depth)
    print(f"echo_node: {a.ns}/ping -> {a.ns}/pong  qos={a.qos}  domain={common.env_tag()['ros_domain_id']}  rmw={common.env_tag()['rmw']}", flush=True)
    t0 = last = time.time()
    try:
        while rclpy.ok() and (a.duration <= 0 or time.time() - t0 < a.duration):
            rclpy.spin_once(node, timeout_sec=0.05)
            if a.report_every and time.time() - last >= a.report_every:
                last = time.time()
                print(f"echo_node: 受信 {node.n} 件（連番の飛び {node.gaps} 回）", flush=True)
    except KeyboardInterrupt:
        pass
    print(f"echo_node: 終了。受信 {node.n} 件、連番の飛び {node.gaps} 回", flush=True)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
