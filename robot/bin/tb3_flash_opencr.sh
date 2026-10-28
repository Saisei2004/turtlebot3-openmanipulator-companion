#!/bin/bash
# OpenCR（機体の制御基板）に、OpenManipulator-X 付き用のファームウェア（turtlebot3_manipulation, V230127R1）を書き込む。
# ファームウェアが合っていないと、アームの関節やモーターの値が正しく読めない
# （2026-10-25: 合っていないとき、全関節が -π のままで OpenCR が読み取りに答えなかった）。
# 書き込みは 2 秒ほど。失敗しても OpenCR のブートローダから書き直せる。書き込み中は OpenCR がリセットされ、モーターの電源が一瞬切れる。
#
# usage: tb3_flash_opencr.sh [ポート（既定 /dev/ttyACM0）]   ※ tb3-bringup が動いていると通信が取り合いになるので、止めてから動かす
set -euo pipefail
PORT="${1:-/dev/ttyACM0}"
DIR="${TB3_OPENCR_DIR:-$HOME/opencr_update}"
URL="https://github.com/ROBOTIS-GIT/OpenCR-Binaries/raw/master/turtlebot3/ROS2/latest/opencr_update.tar.bz2"
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

echo "tb3-bringup を止める"; $SUDO systemctl stop tb3-watchdog tb3-bringup 2>/dev/null || true
# 書き込みツールは 32 ビット ARM の実行ファイル。64 ビットの Ubuntu では 32 ビットのライブラリが要る
$SUDO dpkg --add-architecture armhf && $SUDO apt-get update -qq && $SUDO apt-get install -y -qq libc6:armhf
if [ ! -x "$DIR/update.sh" ]; then
  mkdir -p "$DIR/.." && cd "$(dirname "$DIR")"
  curl -fL -o opencr_update.tar.bz2 "$URL"      # 約 360 KB。ファイルの入手先を変えたいときは URL を替える
  tar -xjf opencr_update.tar.bz2                # ./opencr_update/ ができる
fi
cd "$DIR"
./update.sh "$PORT" turtlebot3_manipulation.opencr
echo "tb3-bringup を起動し直す"; $SUDO systemctl start tb3-bringup tb3-watchdog 2>/dev/null || true
