#!/bin/bash
# 機体なしで動かせる確認をまとめて動かす。ROS 2 Humble 入りの Ubuntu / WSL で:  bash tests/run_tests.sh
# 各行は OK / NG。NG があれば終了コード 1。
[ -r /opt/ros/humble/setup.bash ] && . /opt/ros/humble/setup.bash   # rclpy を使うテストのため（set -u の前に読む）
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0
step() { printf '\n--- %s\n' "$*"; }
run() { if "$@"; then echo "OK   $*"; else echo "NG   $*"; fail=1; fi; }

step "シェルスクリプトの構文"
for f in "$ROOT"/robot/install_robot.sh "$ROOT"/robot/bin/*.sh "$ROOT"/robot/hardware_patch/apply.sh "$ROOT"/pc/scripts/*.sh "$ROOT"/tests/*.sh "$ROOT"/dds/*.sh "$ROOT"/dds/tools/*.sh; do
  [ -e "$f" ] && run bash -n "$f"
done
step "Python の構文"
for f in $(find "$ROOT" -name "*.py" -not -path "*/.venv/*" -not -path "*/workspace/out/*"); do run python3 -m py_compile "$f"; done
step "機体の起動時に DDS の設定を作る処理"
run bash "$ROOT/tests/test_render_dds.sh"
step "円走行の障害物判定（ROS 2 の Python が要る）"
if python3 -c "import rclpy" 2>/dev/null; then run python3 "$ROOT/tests/test_circle_geometry.py"; else echo "SKIP rclpy が無い"; fi
step "MuJoCo のモデルと衝突判定（mujoco が要る）"
if python3 -c "import mujoco" 2>/dev/null; then (cd "$ROOT/pc/server/workspace" && run python3 selftest.py); else echo "SKIP mujoco が無い"; fi
step "ハードウェアのパッチが公式に当たるか（インターネットが要る）"
if [ "${TB3_TEST_NET:-1}" = "1" ] && command -v git >/dev/null; then
  tmp="$(mktemp -d)"
  ( git clone -q --filter=blob:none --sparse https://github.com/ROBOTIS-GIT/turtlebot3_manipulation.git "$tmp/up" \
    && cd "$tmp/up" && git sparse-checkout set turtlebot3_manipulation_hardware && git checkout -q 814f140 \
    && git config core.autocrlf false && git apply --check --ignore-whitespace -p1 "$ROOT/robot/hardware_patch/tb3_manipulation_hardware_fewer_transactions.patch" ) \
    && echo "OK   パッチは公式 814f140 にきれいに当たる" || { echo "NG   パッチが当たらない"; fail=1; }
  rm -rf "$tmp"
else echo "SKIP"; fi
echo; [ $fail -eq 0 ] && echo "ALL OK" || echo "SOME FAILED"
exit $fail
