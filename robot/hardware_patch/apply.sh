#!/bin/bash
# 公式の turtlebot3_manipulation_hardware（ROBOTIS-GIT/turtlebot3_manipulation, humble）を取ってきて、
# 通信を減らすパッチを当て、<ワークスペース>/src に置く。ビルドは呼び出し側（colcon build）。
#
# usage: apply.sh [ワークスペース（既定 ~/turtlebot3_ws）]
# 環境変数 UPSTREAM_MANIP_REV で、パッチを作った元の版を替えられる（既定 814f140 = v2.2.1）。パッチはこの版にだけ確かめてある。
#
# なぜ要るか: OpenCR は 1 回の通信に約 23 ms かかり、1 秒に 43 回しか応答できない。公式の実装は 1 周期に 7 回通信して
# 約 5 Hz でしか動かず、腕の動きがカクカクする。腕の目標を 22 バイト 1 回の書き込みにまとめ、定期の通信を間引いて約 20 Hz にする。
# 詳しくは docs/07-findings-and-gotchas.md。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="${1:-$HOME/turtlebot3_ws}"
REV="${UPSTREAM_MANIP_REV:-814f140}"
PATCH="$HERE/tb3_manipulation_hardware_fewer_transactions.patch"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

git clone -q --filter=blob:none --sparse https://github.com/ROBOTIS-GIT/turtlebot3_manipulation.git "$tmp/up"
cd "$tmp/up"
git sparse-checkout set turtlebot3_manipulation_hardware
git checkout -q "$REV"
git config core.autocrlf false
git apply --ignore-whitespace -p1 "$PATCH"
mkdir -p "$WS/src"
rm -rf "$WS/src/turtlebot3_manipulation_hardware"
cp -r turtlebot3_manipulation_hardware "$WS/src/"
echo "patched turtlebot3_manipulation_hardware ($REV) -> $WS/src"
