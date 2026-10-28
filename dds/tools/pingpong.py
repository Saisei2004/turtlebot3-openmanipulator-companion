#!/usr/bin/env python3
"""PC 側の往復時間の測定。/<ns>/ping に送った小さなメッセージが、echo_node.py（機体側）から /<ns>/pong で返るまでの時間を測る。

測るもの: 往復時間（RTT）の分布（中央値・p95・p99・最大）、取りこぼし、順番の入れ替わり、返事の間隔の最大（= 途切れ）。
時計は送った側（この PC）の単調時計だけを使うので、機体と PC の時計合わせは要らない。往復の半分が片道とは限らない（上りと下りは別の道）。

例:
  python3 pingpong.py --size 64 --hz 20 --duration 30
  python3 pingpong.py --size 65536 --hz 10 --qos best_effort --csv result.csv --label wifi_unicast
機体が無くても、同じ PC で echo_node.py を動かせば動作を確かめられる。
"""
import argparse
import array
import json
import struct
import sys
import time

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import UInt8MultiArray

import common

HEADER = struct.Struct("<QqI")      # 連番, 送信時刻 [ns, perf_counter], ペイロードの大きさ


class Pinger(Node):
    def __init__(self, ns, qos_kind, depth):
        super().__init__("tb3_dds_pingpong")
        q = common.qos(qos_kind, depth)
        self.pub = self.create_publisher(UInt8MultiArray, f"{ns}/ping", q)
        self.sub = self.create_subscription(UInt8MultiArray, f"{ns}/pong", self.on_pong, q)
        self.rtt = {}          # seq -> RTT [ms]（最初の返事だけ）
        self.recv_t = []       # 返事が届いた時刻 [s]
        self.dups = 0
        self.ooo = 0
        self.max_seq = -1

    def on_pong(self, m):
        t = time.perf_counter_ns()
        b = bytes(m.data[:HEADER.size])
        if len(b) < HEADER.size:
            return
        seq, t_send, _ = HEADER.unpack(b)
        if seq in self.rtt:
            self.dups += 1
            return
        if seq < self.max_seq:
            self.ooo += 1
        self.max_seq = max(self.max_seq, seq)
        self.rtt[seq] = (t - t_send) / 1e6
        self.recv_t.append(t / 1e9)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ns", default="/tb3_dds")
    ap.add_argument("--size", type=int, default=64, help="ペイロードの大きさ [B]（20 以上。64 B〜64 KB で試す）")
    ap.add_argument("--hz", type=float, default=20, help="送る頻度 [Hz]")
    ap.add_argument("--duration", type=float, default=30, help="送り続ける秒数")
    ap.add_argument("--qos", choices=["reliable", "best_effort"], default="reliable")
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--wait-match", type=float, default=20, help="echo_node が見つかるまで待つ秒数（超えたら終了コード 3）")
    ap.add_argument("--drain", type=float, default=2, help="送り終わったあと、遅れて届く返事を待つ秒数")
    ap.add_argument("--csv", help="要約を 1 行足す CSV")
    ap.add_argument("--samples-csv", help="1 往復ごとの記録（seq, rtt_ms）の CSV（上書き）")
    ap.add_argument("--label", default="", help="結果に付ける名前（プロファイル名など）")
    a = ap.parse_args()
    if a.size < HEADER.size:
        sys.exit(f"--size は {HEADER.size} 以上")

    rclpy.init()
    node = Pinger(a.ns, a.qos, a.depth)
    t_start = time.perf_counter()
    while rclpy.ok() and time.perf_counter() - t_start < a.wait_match:
        rclpy.spin_once(node, timeout_sec=0.05)
        if node.pub.get_subscription_count() > 0 and node.count_publishers(f"{a.ns}/pong") > 0:
            break
    else:
        print(f"echo_node が見つかりません（{a.wait_match:.0f} 秒待った）。相手側で echo_node.py を、同じ ROS_DOMAIN_ID・同じ --qos で動かしてください", file=sys.stderr)
        if a.csv:       # つながらなかったことも、結果の表に残す
            common.append_csv(a.csv, dict(label=a.label, **common.env_tag(), size=a.size, hz=a.hz, qos=a.qos, duration_s=a.duration, no_match_after_s=a.wait_match, sent=0, received=0))
        return 3
    match_s = time.perf_counter() - t_start
    time.sleep(0.3)            # つながった直後の取りこぼしを数えないための短い待ち

    pad = bytes(a.size - HEADER.size)
    period = 1.0 / a.hz
    t0 = time.perf_counter()
    next_send, seq, sent_at = t0, 0, {}
    while rclpy.ok() and time.perf_counter() - t0 < a.duration:
        now = time.perf_counter()
        if now >= next_send:
            msg = UInt8MultiArray()
            msg.data = array.array("B", HEADER.pack(seq, time.perf_counter_ns(), a.size) + pad)
            node.pub.publish(msg)
            sent_at[seq] = now
            seq += 1
            next_send += period
            if now - next_send > 5 * period:       # 遅れすぎたら詰め直す（バースト送信を避ける）
                next_send = now + period
        rclpy.spin_once(node, timeout_sec=max(0.0, min(0.002, next_send - time.perf_counter())))
    t_end = time.perf_counter()
    d_end = t_end + a.drain
    while rclpy.ok() and time.perf_counter() < d_end:
        rclpy.spin_once(node, timeout_sec=0.01)

    sent, got = seq, len(node.rtt)
    rtts = np.array([node.rtt[k] for k in sorted(node.rtt)])
    rs = common.summarize(rtts)
    gaps = np.diff(np.array(sorted(node.recv_t))) if len(node.recv_t) > 1 else np.array([float("nan")])
    # 欠けた連番が続いた最長の長さ（= 途切れの目安）
    missing = [k for k in range(sent) if k not in node.rtt]
    longest, run = 0, 0
    prev = None
    for k in missing:
        run = run + 1 if prev is not None and k == prev + 1 else 1
        longest, prev = max(longest, run), k
    tag = common.env_tag()
    row = dict(label=a.label, **tag, size=a.size, hz=a.hz, qos=a.qos, duration_s=a.duration, match_s=round(match_s, 2),
               sent=sent, received=got, loss_pct=round(100 * (sent - got) / max(sent, 1), 2), longest_loss_run=longest,
               rtt_min_ms=round(rs["min"], 2), rtt_median_ms=round(rs["median"], 2), rtt_p95_ms=round(rs["p95"], 2),
               rtt_p99_ms=round(rs["p99"], 2), rtt_max_ms=round(rs["max"], 2), rtt_std_ms=round(rs["std"], 2),
               reply_gap_max_ms=round(float(np.nanmax(gaps)) * 1000, 1), out_of_order=node.ooo, duplicates=node.dups)
    print(f"pingpong  {a.size} B @ {a.hz:g} Hz  qos={a.qos}  rmw={tag['rmw']}  profile={tag['profile']}  domain={tag['ros_domain_id']}")
    print(f"  つながるまで {match_s:.2f} s / 送信 {sent} / 受信 {got} / 取りこぼし {row['loss_pct']} %（欠けが続いた最長 {longest} 件）")
    print(f"  往復時間 [ms]  最小 {common.fmt(rs['min'], 2)}  中央値 {common.fmt(rs['median'], 2)}  p95 {common.fmt(rs['p95'], 2)}  p99 {common.fmt(rs['p99'], 2)}  最大 {common.fmt(rs['max'], 2)}  標準偏差 {common.fmt(rs['std'], 2)}")
    print(f"  返事の間隔の最大 {row['reply_gap_max_ms']} ms / 順番の入れ替わり {node.ooo} / 重複 {node.dups}")
    print("RESULT " + json.dumps(row, ensure_ascii=False))
    if a.csv:
        common.append_csv(a.csv, row)
    if a.samples_csv:
        with open(a.samples_csv, "w", encoding="utf-8") as f:
            f.write("seq,rtt_ms\n")
            for k in sorted(node.rtt):
                f.write(f"{k},{node.rtt[k]:.3f}\n")
    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
