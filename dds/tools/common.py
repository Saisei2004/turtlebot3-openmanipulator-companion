"""dds/tools 共通の小さな部品（分位数・CSV 追記・QoS・実行条件のタグ）。rclpy は QoS を作るときだけ読み込む。"""
import csv
import os
import sys
import time

import numpy as np


def qos(kind="reliable", depth=10):
    """kind: reliable | best_effort。履歴は KEEP_LAST(depth)、耐久性は VOLATILE"""
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    rel = ReliabilityPolicy.RELIABLE if kind == "reliable" else ReliabilityPolicy.BEST_EFFORT
    return QoSProfile(reliability=rel, history=HistoryPolicy.KEEP_LAST, depth=depth, durability=DurabilityPolicy.VOLATILE)


def pct(values, p):
    """p 分位（0〜100）。空なら nan"""
    return float(np.percentile(values, p)) if len(values) else float("nan")


def summarize(values):
    """中央値・p95・p99・最大・最小・標準偏差をまとめた dict（単位は呼ぶ側が決める）"""
    v = np.asarray(values, float)
    if v.size == 0:
        return dict(n=0, min=float("nan"), median=float("nan"), p95=float("nan"), p99=float("nan"), max=float("nan"), std=float("nan"))
    return dict(n=int(v.size), min=float(v.min()), median=float(np.median(v)), p95=pct(v, 95), p99=pct(v, 99), max=float(v.max()), std=float(v.std()))


def env_tag():
    """結果の横に残す、実行条件の短いタグ。詳しくは env_report.sh"""
    prof = os.environ.get("FASTRTPS_DEFAULT_PROFILES_FILE") or os.environ.get("CYCLONEDDS_URI") or ""
    return dict(
        ros_domain_id=os.environ.get("ROS_DOMAIN_ID", "0"),
        rmw=os.environ.get("RMW_IMPLEMENTATION", "(default)"),
        profile=os.path.basename(prof.replace("file://", "")) if prof else "(none)",
        discovery_server=os.environ.get("ROS_DISCOVERY_SERVER", ""),
        host=os.uname().nodename if hasattr(os, "uname") else "",
    )


def append_csv(path, row):
    """row（dict）を CSV に 1 行足す。ファイルが無ければ見出しも書く。
    行によって項目が違っても（例: 1 件も届かなかった行は項目が少ない）、列がずれないよう、見出しは項目の和集合にそろえて書き直す"""
    rows = []
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    cols = list(rows[0].keys()) if rows else []
    for k in row.keys():
        if k not in cols:
            cols.append(k)
    rows.append(row)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, restval="")
        w.writeheader()
        w.writerows(rows)


def fmt(x, nd=1):
    return "nan" if x != x else f"{x:.{nd}f}"


def eprint(*a):
    print(*a, file=sys.stderr, flush=True)


def now():
    return time.perf_counter()
