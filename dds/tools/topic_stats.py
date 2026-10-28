#!/usr/bin/env python3
"""既存のトピックが、どれだけ届くか・どれだけ途切れるかを測る（record_stream2.py の心拍まわりを一般化したもの）。

測るもの: 受信件数と頻度、メッセージの間隔の分布（中央値・p95・p99・最大）、最長の途切れとその位置、閾値を超えた間隔の数、
最初のメッセージが届くまでの時間（= この測定プロセスの発見の遅さ）。

例（機体の /scan と心拍を 30 秒）:
  python3 topic_stats.py --topic /scan --topic /tb3_pc_alive --duration 30 --gap-threshold 0.15
  python3 topic_stats.py --topic /joint_states --expected-hz 78 --csv stats.csv --label wifi_whitelist
QoS は既定で best_effort（reliable の発行にも best_effort の購読はつながる。逆はつながらない）。型は自動で調べる（--type で指定すると待たない）。
"""
import argparse
import json
import sys
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rosidl_runtime_py.utilities import get_message

import common


class Stats(Node):
    def __init__(self):
        super().__init__("tb3_dds_topic_stats")
        self.t = {}       # topic -> [perf_counter 秒]

    def watch(self, topic, msg_type, qos_kind, depth):
        self.t[topic] = []
        self.create_subscription(msg_type, topic, lambda m, k=topic: self.t[k].append(time.perf_counter()), common.qos(qos_kind, depth))


def resolve_type(node, topic, wait):
    t_end = time.perf_counter() + wait
    while time.perf_counter() < t_end:
        for name, types in node.get_topic_names_and_types():
            if name == topic and types:
                return types[0]
        rclpy.spin_once(node, timeout_sec=0.1)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topic", action="append", required=True, help="測るトピック（複数指定できる）")
    ap.add_argument("--type", action="append", help="トピックの型（例 sensor_msgs/msg/LaserScan）。--topic と同じ順に指定。省略すると自動")
    ap.add_argument("--duration", type=float, default=30, help="測る秒数（購読を始めてから）")
    ap.add_argument("--qos", choices=["reliable", "best_effort"], default="best_effort")
    ap.add_argument("--depth", type=int, default=50)
    ap.add_argument("--gap-threshold", type=float, default=0.15, help="これを超えた間隔を「途切れ」として数える [s]")
    ap.add_argument("--expected-hz", type=float, help="本来の頻度。あれば取りこぼしの目安（件数の不足）を出す")
    ap.add_argument("--wait-type", type=float, default=20, help="型の自動判定を待つ秒数")
    ap.add_argument("--csv", help="トピックごとの要約を 1 行ずつ足す CSV")
    ap.add_argument("--label", default="")
    a = ap.parse_args()

    rclpy.init()
    node = Stats()
    types = a.type or []
    t_sub = {}
    for i, topic in enumerate(a.topic):
        ty = types[i] if i < len(types) else resolve_type(node, topic, a.wait_type)
        if ty is None:
            print(f"{topic}: 型を判定できません（{a.wait_type:.0f} 秒待った。発行側が見えていない）。--type を指定するか、発見の問題を疑う", file=sys.stderr)
            continue
        node.watch(topic, get_message(ty), a.qos, a.depth)
        t_sub[topic] = (time.perf_counter(), ty)
    if not node.t:
        return 3
    t0 = time.perf_counter()
    while rclpy.ok() and time.perf_counter() - t0 < a.duration:
        rclpy.spin_once(node, timeout_sec=0.05)

    tag = common.env_tag()
    rows = []
    print(f"topic_stats  {a.duration:g} s  qos={a.qos}  rmw={tag['rmw']}  profile={tag['profile']}  domain={tag['ros_domain_id']}")
    for topic, ts in node.t.items():
        ts = np.array(ts)
        t_s, ty = t_sub[topic]
        row = dict(label=a.label, **tag, topic=topic, type=ty, duration_s=a.duration, count=int(ts.size))
        if ts.size == 0:
            print(f"  {topic}: 1 件も届かない（発見できていない / QoS が合わない / ファイアウォール）")
            row.update(rate_hz=0.0, first_msg_s=float("nan"))
            rows.append(row)
            continue
        gaps = np.diff(ts)
        s = common.summarize(gaps * 1000)
        first = float(ts[0] - t_s)
        win = float(ts[-1] - ts[0]) if ts.size > 1 else float("nan")
        rate = (ts.size - 1) / win if ts.size > 1 and win > 0 else float("nan")
        worst = int(np.argmax(gaps)) if gaps.size else 0
        over = int((gaps > a.gap_threshold).sum()) if gaps.size else 0
        row.update(first_msg_s=round(first, 2), rate_hz=round(rate, 2), gap_median_ms=round(s["median"], 1), gap_p95_ms=round(s["p95"], 1),
                   gap_p99_ms=round(s["p99"], 1), gap_max_ms=round(s["max"], 1), gap_max_at_s=round(float(ts[worst] - t_s), 1) if gaps.size else float("nan"),
                   gaps_over_threshold=over, gap_threshold_s=a.gap_threshold, intervals=int(gaps.size))
        line = (f"  {topic}  {ts.size} 件  {rate:.1f} Hz  最初の 1 件まで {first:.2f} s  間隔[ms] 中央値 {s['median']:.1f} / p95 {s['p95']:.1f} / p99 {s['p99']:.1f} / 最大 {s['max']:.1f}"
                f"（購読開始から {row['gap_max_at_s']} s の位置）  {a.gap_threshold * 1000:.0f} ms 超 {over} / {gaps.size}")
        if a.expected_hz:
            exp = a.expected_hz * (ts[-1] - ts[0])
            row["expected_count"] = round(exp)
            row["shortfall_pct"] = round(100 * (exp - (ts.size - 1)) / exp, 1) if exp > 0 else float("nan")
            line += f"  期待 {exp:.0f} 件に対し不足 {row['shortfall_pct']} %"
        print(line)
        rows.append(row)
    for r in rows:
        print("RESULT " + json.dumps(r, ensure_ascii=False))
        if a.csv:
            common.append_csv(a.csv, r)
    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
