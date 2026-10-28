#!/bin/bash
# PC 側（Ubuntu 22.04 または WSL2 の Ubuntu 22.04）に必要なものを入れる: ROS 2 Humble、rosbridge、MuJoCo など。
# Windows の人は、先に WSL2 と Ubuntu 22.04 を入れて、docs/01-quickstart-new-pc.md の「Windows」の手順（mirrored ネットワーク）を済ませる。
# 何度動かしてもよい。sudo が使えること。
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
. /etc/os-release
[ "${VERSION_ID:-}" = "22.04" ] || { echo "Ubuntu 22.04 が前提です（今: ${PRETTY_NAME:-?}）。他の OS は pc/docker/ を使ってください" >&2; exit 1; }

sudo apt-get update -qq
sudo apt-get install -y -qq locales software-properties-common curl git python3-pip
sudo locale-gen en_US en_US.UTF-8 >/dev/null && sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
sudo add-apt-repository -y universe >/dev/null
if ! ls /etc/apt/sources.list.d | grep -q ros2; then
  V=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F '"tag_name"' | awk -F'"' '{print $4}')
  curl -fL -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${V}/ros2-apt-source_${V}.jammy_all.deb"
  sudo dpkg -i /tmp/ros2-apt-source.deb
  sudo apt-get update -qq
fi
sudo apt-get install -y ros-humble-ros-base ros-humble-rosbridge-server ros-humble-teleop-twist-keyboard \
  ros-humble-control-msgs ros-humble-trajectory-msgs ros-humble-rmw-cyclonedds-cpp python3-numpy python3-yaml
# MuJoCo（衝突判定とワークスペース解析）。3.x なら動く（3.11.0 で確認）
python3 -m pip install --quiet --user mujoco
python3 -c "import mujoco, numpy; print('mujoco', mujoco.__version__, 'numpy', numpy.__version__)"
echo "OK: 次は tb3ctl init → tb3ctl server"
