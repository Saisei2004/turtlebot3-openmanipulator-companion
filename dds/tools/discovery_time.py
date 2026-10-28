#!/usr/bin/env python3
"""新しい参加者が起動してから、相手の発行者が見つかり、最初のメッセージが届くまでの時間を、別プロセスで N 回繰り返して測る。

`ros2 daemon` は使わない（rclpy は直接発見するので、デーモンの古い発見結果の影響を受けない）。
各回は新しいプロセス（= 新しい DDS 参加者）。測るのは次の 3 つ（rclpy を読み込んだあと、ノードを作る直前からの秒）:
  node_ready_s   ノードができるまで
  match_s        トピックの発行者が 1 つ見えるまで（発見の遅さ。Wi-Fi のマルチキャスト発見で効く）
  first_msg_s    最初のメッセージが届くまで（発見 + データの経路がつながるまで）

例（機体の /scan に対して 5 回）:
  python3 discovery_time.py --topic /scan --type sensor_msgs/msg/LaserScan --runs 5 --csv discovery.csv --label wifi_default
機体が無いとき（同じ PC のダミー発行者に対して）:
  python3 discovery_time.py --dummy-publisher --runs 3
"""
import argparse
import array
import json
import os
import subprocess
import sys
import time

import numpy as np

import common

DUMMY_TOPIC = "/dds_test/dummy"
DUMMY_TYPE = "std_msgs/msg/UInt8MultiArray"


def dummy_main(hz):
    import rclpy
    from std_msgs.msg import UInt8MultiArray
    rclpy.init()
    n = rclpy.create_node("tb3_dds_dummy_pub")
    pub = n.create_publisher(UInt8MultiArray, DUMMY_TOPIC, common.qos("best_effort", 10))
    msg = UInt8MultiArray()
    msg.data = array.array("B", bytes(64))
    n.create_timer(1.0 / hz, lambda: pub.publish(msg))
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass


def child_main(topic, type_name, timeout, qos_kind):
    import rclpy
    from rosidl_runtime_py.utilities import get_message
    msg_type = get_message(type_name)
    t0 = time.perf_counter()
    rclpy.init()
    node = rclpy.create_node("tb3_dds_discovery_probe")
    t_node = time.perf_counter() - t0
    got = []
    node.create_subscription(msg_type, topic, lambda m: got.append(time.perf_counter() - t0), common.qos(qos_kind, 10))
    t_match = None
    while rclpy.ok() and time.perf_counter() - t0 < timeout and not got:
        rclpy.spin_once(node, timeout_sec=0.01)
        if t_match is None and node.count_publishers(topic) > 0:
            t_match = time.perf_counter() - t0
    out = dict(node_ready_s=round(t_node, 3), match_s=None if t_match is None else round(t_match, 3), first_msg_s=round(got[0], 3) if got else None)
    print("CHILD " + json.dumps(out), flush=True)
    node.destroy_node()
    rclpy.shutdown()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topic", default="/scan")
    ap.add_argument("--type", default="sensor_msgs/msg/LaserScan")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=40, help="1 回あたりの最長の待ち [s]")
    ap.add_argument("--interval", type=float, default=2, help="次の回までの待ち [s]（前の参加者の消えるのを待つ）")
    ap.add_argument("--qos", choices=["reliable", "best_effort"], default="best_effort")
    ap.add_argument("--dummy-publisher", action="store_true", help="同じ PC にダミーの発行者（%s）を起こし、それに対して測る" % DUMMY_TOPIC)
    ap.add_argument("--dummy-hz", type=float, default=20)
    ap.add_argument("--csv")
    ap.add_argument("--label", default="")
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--dummy", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a.dummy:
        return dummy_main(a.dummy_hz)
    if a.child:
        return child_main(a.topic, a.type, a.timeout, a.qos)

    topic, ty = a.topic, a.type
    dummy = None
    if a.dummy_publisher:
        topic, ty = DUMMY_TOPIC, DUMMY_TYPE
        dummy = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--dummy", "--dummy-hz", str(a.dummy_hz)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
    tag = common.env_tag()
    print(f"discovery_time  topic={topic}  runs={a.runs}  qos={a.qos}  rmw={tag['rmw']}  profile={tag['profile']}  domain={tag['ros_domain_id']}")
    results = []
    try:
        for i in range(a.runs):
            t = time.perf_counter()
            p = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", "--topic", topic, "--type", ty, "--timeout", str(a.timeout), "--qos", a.qos],
                               capture_output=True, text=True, timeout=a.timeout + 30)
            line = [l for l in p.stdout.splitlines() if l.startswith("CHILD ")]
            r = json.loads(line[-1][6:]) if line else dict(node_ready_s=None, match_s=None, first_msg_s=None)
            r["run"] = i + 1
            results.append(r)
            fm = r["first_msg_s"]
            print(f"  {i + 1}/{a.runs}: ノード {r['node_ready_s']} s / 発行者が見える {r['match_s']} s / 最初の 1 件 {fm if fm is not None else '届かず（%g 秒）' % a.timeout}  （この回 {time.perf_counter() - t:.1f} s）", flush=True)
            if i + 1 < a.runs:
                time.sleep(a.interval)
    finally:
        if dummy:
            dummy.terminate()
    fm = [r["first_msg_s"] for r in results if r["first_msg_s"] is not None]
    mm = [r["match_s"] for r in results if r["match_s"] is not None]
    s, m = common.summarize(fm), common.summarize(mm)
    summary = dict(label=a.label, **tag, topic=topic, runs=a.runs, timeouts=a.runs - len(fm),
                   match_median_s=round(m["median"], 2), match_max_s=round(m["max"], 2),
                   first_msg_min_s=round(s["min"], 2), first_msg_median_s=round(s["median"], 2), first_msg_max_s=round(s["max"], 2))
    print(f"  最初の 1 件までの秒: 最小 {common.fmt(s['min'], 2)} / 中央値 {common.fmt(s['median'], 2)} / 最大 {common.fmt(s['max'], 2)}   届かなかった回 {summary['timeouts']} / {a.runs}")
    print("RESULT " + json.dumps(summary, ensure_ascii=False))
    if a.csv:
        for r in results:
            common.append_csv(a.csv, dict(label=a.label, **tag, topic=topic, **r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
