#!/bin/bash
# 設定（ドメイン ID・DDS のプロファイル）を揃えた状態で、ROS 2 のコマンドや Python を動かす。
# 例:  pc/scripts/run_ros.sh ros2 topic list
#      pc/scripts/run_ros.sh python3 dds/tools/topic_stats.py --topic /scan
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/dds_env.sh" || exit 1
[ $# -eq 0 ] && { echo "usage: run_ros.sh <command> [args...]" >&2; exit 2; }
exec "$@"
