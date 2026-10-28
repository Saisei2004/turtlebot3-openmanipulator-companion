#!/bin/bash
# 機体（Raspberry Pi 4 + Ubuntu 22.04 + OpenCR）に、このリポジトリの機体側をすべて入れる。
# 普通は PC から `tb3ctl robot-install`（全部）か `tb3ctl robot-apply`（設定とサービスだけ）で動かす。
#
# 使い方（機体の上で）:  bash install_robot.sh [フェーズ ...]
#   base    自動更新とスリープを止める、Wi-Fi の省電力ツール
#   ros     ROS 2 Humble（ros-base）と TurtleBot3 + OpenManipulator-X のパッケージ（apt）
#   ws      ld08_driver（LiDAR LDS-02）と、通信を減らした turtlebot3_manipulation_hardware をビルドして ~/turtlebot3_ws に置く
#   files   /etc/tb3/tb3.env、サービス（bringup / deadman / watchdog / Wi-Fi 省電力オフ）、udev、~/.bashrc を入れて起動
#   opencr  OpenCR のファームウェアをアーム付き用に書き込む（tb3_flash_opencr.sh）。基板を書き換えるので、all には含めない
#   all     base ros ws files（既定。opencr は含まない）
#
# 設定は robot.env（tb3ctl が config/tb3.env から作って、このスクリプトと同じ場所に置く）か、環境変数で渡す:
#   ROS_DOMAIN_ID TURTLEBOT3_MODEL LDS_MODEL DDS_IFACE TB3_JOINTS_PROFILE_ACCELERATION TB3_JOINTS_PROFILE_VELOCITY
#
# 状態: 2026-10-25〜26 に、同じコマンドを 1 つずつ実機で動かして確かめた。一続きのこのスクリプトとして、
# まっさらな SD カードから最後まで通したことはまだない（docs/02-robot-provisioning.md の「未検証」を参照）。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DEBIAN_FRONTEND=noninteractive
TB3_USER="${TB3_USER:-$(id -un)}"
TB3_HOME="$(getent passwd "$TB3_USER" | cut -d: -f6)"
[ -r "$HERE/robot.env" ] && { set -a; . "$HERE/robot.env"; set +a; }
ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
TURTLEBOT3_MODEL="${TURTLEBOT3_MODEL:-waffle_pi}"
LDS_MODEL="${LDS_MODEL:-LDS-02}"
DDS_IFACE="${DDS_IFACE:-wlan0}"
TB3_JOINTS_PROFILE_ACCELERATION="${TB3_JOINTS_PROFILE_ACCELERATION:-25}"
TB3_JOINTS_PROFILE_VELOCITY="${TB3_JOINTS_PROFILE_VELOCITY:-300}"
UPSTREAM_MANIP_REV=814f140      # ROBOTIS-GIT/turtlebot3_manipulation の humble ブランチ（パッチを当てる元。v2.2.1）

log() { printf '\n== %s ==\n' "$*"; }
need_root() { [ "$(id -u)" -eq 0 ] && SUDO="" || SUDO="sudo"; }
need_root

phase_base() {
  log "base: 自動更新・スリープを止める"
  $SUDO tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null <<'EOF'
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
EOF
  $SUDO systemctl stop unattended-upgrades 2>/dev/null || true
  # 待ち合わせで起動が遅くならないように。ネットワークの待ちは tb3-bringup が自分でやる
  $SUDO systemctl mask systemd-networkd-wait-online.service sleep.target suspend.target hibernate.target hybrid-sleep.target
  while $SUDO fuser /var/lib/dpkg/lock-frontend /var/lib/apt/lists/lock >/dev/null 2>&1; do sleep 5; done
  $SUDO apt-get update
  $SUDO apt-get install -y -qq iw wireless-tools curl git software-properties-common locales
}

phase_ros() {
  log "ros: ROS 2 Humble と TurtleBot3 + OpenManipulator-X"
  $SUDO locale-gen en_US en_US.UTF-8 && $SUDO update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
  $SUDO add-apt-repository -y universe
  if [ ! -e /etc/apt/sources.list.d/ros2.sources ] && ! ls /etc/apt/sources.list.d | grep -q ros2; then
    V=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F '"tag_name"' | awk -F'"' '{print $4}')
    curl -fL -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${V}/ros2-apt-source_${V}.jammy_all.deb"
    $SUDO dpkg -i /tmp/ros2-apt-source.deb
  fi
  $SUDO apt-get update
  $SUDO apt-get -y upgrade
  $SUDO apt-get install -y ros-humble-ros-base ros-dev-tools \
    python3-argcomplete python3-colcon-common-extensions libboost-system-dev build-essential libudev-dev git \
    ros-humble-hls-lfcd-lds-driver ros-humble-turtlebot3-msgs ros-humble-dynamixel-sdk ros-humble-xacro \
    ros-humble-turtlebot3-manipulation ros-humble-turtlebot3 \
    ros-humble-cartographer ros-humble-cartographer-ros ros-humble-navigation2 ros-humble-nav2-bringup \
    python3-yaml python3-numpy python3-serial
}

phase_ws() {
  log "ws: LiDAR ドライバと、通信を減らした制御プラグインをビルド"
  local ws="$TB3_HOME/turtlebot3_ws"
  sudo -u "$TB3_USER" mkdir -p "$ws/src"
  [ -d "$ws/src/ld08_driver" ] || sudo -u "$TB3_USER" git clone -b humble https://github.com/ROBOTIS-GIT/ld08_driver.git "$ws/src/ld08_driver"
  sudo -u "$TB3_USER" env UPSTREAM_MANIP_REV="$UPSTREAM_MANIP_REV" bash "$HERE/hardware_patch/apply.sh" "$ws"
  sudo -u "$TB3_USER" bash -c "source /opt/ros/humble/setup.bash && cd '$ws' && colcon build --symlink-install --parallel-workers 2 --cmake-args -DCMAKE_BUILD_TYPE=Release"
}

phase_files() {
  log "files: 設定・サービス・udev・~/.bashrc"
  $SUDO mkdir -p /etc/tb3
  $SUDO tee /etc/tb3/tb3.env >/dev/null <<EOF
# tb3ctl robot-apply が書く（手で直してもよいが、次の robot-apply で上書きされる）
ROS_DOMAIN_ID=$ROS_DOMAIN_ID
TURTLEBOT3_MODEL=$TURTLEBOT3_MODEL
LDS_MODEL=$LDS_MODEL
DDS_IFACE=$DDS_IFACE
TB3_JOINTS_PROFILE_ACCELERATION=$TB3_JOINTS_PROFILE_ACCELERATION
TB3_JOINTS_PROFILE_VELOCITY=$TB3_JOINTS_PROFILE_VELOCITY
EOF
  for f in tb3_bringup.sh tb3_deadman.py tb3_watchdog.sh tb3_render_dds.sh tb3_flash_opencr.sh tb3_set_wifi.py; do
    [ -e "$HERE/bin/$f" ] && $SUDO install -m 755 "$HERE/bin/$f" /usr/local/bin/
  done
  $SUDO install -m 644 "$HERE/bin/tb3_env.sh" /etc/tb3/env.sh
  for u in tb3-bringup tb3-deadman tb3-watchdog wifi-powersave-off; do
    sed "s/__USER__/$TB3_USER/g" "$HERE/systemd/$u.service" | $SUDO tee "/etc/systemd/system/$u.service" >/dev/null
  done
  $SUDO install -m 644 "$HERE"/udev/*.rules /etc/udev/rules.d/
  $SUDO udevadm control --reload-rules && $SUDO udevadm trigger
  # ~/.bashrc: 古い設定を消して、ブロックを 1 つ置く
  local rc="$TB3_HOME/.bashrc"
  sudo -u "$TB3_USER" sed -i '/#TURTLEBOT3$/d; /# >>> tb3-companion >>>/,/# <<< tb3-companion <<</d' "$rc"
  printf '# >>> tb3-companion >>>\n[ -r /etc/tb3/env.sh ] && . /etc/tb3/env.sh\n# <<< tb3-companion <<<\n' | sudo -u "$TB3_USER" tee -a "$rc" >/dev/null
  # 有線（eth0）: DHCP に加えて、リンクローカル（169.254.x.x）も持たせる。PC とケーブル 1 本で直結したとき（DHCP サーバーが無いとき）も、
  # PC（Windows は自動で 169.254.x.x を取る）と話せて、名前（ホスト名.local、avahi）で ssh できる。反映は次の再起動のとき（今の接続を切らないため）
  printf 'network:\n  version: 2\n  ethernets:\n    eth0:\n      dhcp4: true\n      dhcp6: true\n      optional: true\n      link-local: [ ipv4, ipv6 ]\n' | $SUDO tee /etc/netplan/60-tb3-eth0.yaml >/dev/null
  $SUDO chmod 600 /etc/netplan/60-tb3-eth0.yaml
  $SUDO netplan generate 2>/dev/null || { echo "netplan が eth0 の link-local を受け付けないので、60-tb3-eth0.yaml を外す" >&2; $SUDO rm -f /etc/netplan/60-tb3-eth0.yaml; }
  $SUDO apt-get install -y -qq avahi-daemon >/dev/null 2>&1 || true
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable wifi-powersave-off tb3-bringup tb3-deadman tb3-watchdog
  $SUDO systemctl restart wifi-powersave-off || true
  $SUDO systemctl restart tb3-bringup tb3-deadman tb3-watchdog
  sleep 5
  systemctl --no-pager --full status tb3-bringup tb3-deadman tb3-watchdog 2>/dev/null | grep -E "^●|Active:" || true
}

phase_opencr() {
  log "opencr: OpenCR にアーム付き用ファームウェアを書き込む"
  bash "$HERE/bin/tb3_flash_opencr.sh"
}

PHASES=("$@")
[ ${#PHASES[@]} -eq 0 ] && PHASES=(all)
for ph in "${PHASES[@]}"; do
  case "$ph" in
    base|ros|ws|files|opencr) "phase_$ph" ;;
    all) phase_base; phase_ros; phase_ws; phase_files ;;
    *) echo "unknown phase: $ph" >&2; exit 2 ;;
  esac
done
log "done: ${PHASES[*]}"
