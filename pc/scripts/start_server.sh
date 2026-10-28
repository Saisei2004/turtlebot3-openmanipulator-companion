#!/bin/bash
# PC 側のサーバーを起動する: 操作画面（:SERVER_PORT）+ rosbridge（:ROSBRIDGE_PORT）+ 円走行・Dance のドライバ + MuJoCo の衝突判定。
# ROS 2 Humble が入った Ubuntu 22.04（または WSL2 の Ubuntu）で動かす。Windows からは `tb3ctl server` が WSL 経由で呼ぶ。
#
# 環境変数 TB3_DRYRUN=1 で「試験用」: 円走行・アームの指令を機体に送らず、別名のトピック（/cmd_vel_dryrun など）に出す。
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
. "$HERE/dds_env.sh"
bash "$HERE/kill_server.sh" >/dev/null || true     # 古い rosbridge が残っていると 9090 を取り合う
echo "$TB3_DDS_NOTE"
cd "$ROOT/pc/server"
python3 tb3_server.py "$SERVER_PORT" &
WEB=$!
trap 'kill $WEB 2>/dev/null' EXIT
echo "操作画面: http://localhost:$SERVER_PORT/   rosbridge: ws://localhost:$ROSBRIDGE_PORT"
ros2 launch rosbridge_server rosbridge_websocket_launch.xml port:="$ROSBRIDGE_PORT" address:=0.0.0.0 \
  send_action_goals_in_new_thread:=true call_services_in_new_thread:=true default_call_service_timeout:=5.0
