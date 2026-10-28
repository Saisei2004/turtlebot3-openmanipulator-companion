#!/bin/bash
# PC 側のサーバー（操作画面・rosbridge・ドライバ）をすべて止める。
# 古い rosbridge が残ると、新しい rosbridge が 9090 を取れず「Address already in use」を出し続けるので、起動前にも呼ぶ。
# 呼び出し元（start_server.sh）と自分自身は殺さない。
for p in $(pgrep -f "start_server.sh"); do
  [ "$p" = "$$" ] || [ "$p" = "$PPID" ] || kill "$p" 2>/dev/null
done
pkill -9 -f tb3_server.py 2>/dev/null
pkill -f rosbridge_websocket 2>/dev/null
pkill -f rosapi_node 2>/dev/null
pkill -f "ros2 launch rosbridge_server" 2>/dev/null
sleep 1
left=$(pgrep -af "tb3_server|rosbridge|rosapi" | grep -v pgrep | wc -l)
echo "tb3-companion server processes left: $left"
exit 0
