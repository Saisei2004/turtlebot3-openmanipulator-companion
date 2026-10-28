#!/bin/bash
# PC のターミナルのキーボードで機体を走らせる（i/j/k/l など。q/z で速度変更）。ブラウザの操作画面が使えないときの代わり
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/dds_env.sh" || exit 1
exec ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -p speed:=0.10 -p turn:=0.6
