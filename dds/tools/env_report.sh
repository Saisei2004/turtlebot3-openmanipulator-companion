#!/usr/bin/env bash
# 検証の条件を記録する。測定結果と必ず一緒に残すこと（同じ測定でも、条件が違えば別の結果になる）。
# 使い方:  bash env_report.sh > results/xxxx/env_pc.txt
#          ssh ubuntu@<機体> 'bash -s' < env_report.sh > results/xxxx/env_robot.txt      # 機体側（読み取りだけ）
# 読み取りだけで、何も変更しない。無いコマンドは飛ばす。
sec() { printf '\n===== %s =====\n' "$1"; }
has() { command -v "$1" >/dev/null 2>&1; }

sec "時刻・ホスト"
date -Is; hostname; uname -a
[ -r /etc/os-release ] && . /etc/os-release && echo "OS: ${PRETTY_NAME:-?}"
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "WSL: yes"; has wslinfo && wslinfo --networking-mode 2>/dev/null | sed 's/^/WSL networking mode: /'
fi
has uptime && uptime

sec "ROS 2 / RMW / DDS のバージョン"
echo "ROS_DISTRO=${ROS_DISTRO:-(未設定: source /opt/ros/humble/setup.bash が必要)}"
if has dpkg; then
  dpkg -l 2>/dev/null | awk '/^ii/ && ($2 ~ /^ros-[a-z]+-(fastrtps|fastcdr|rmw-fastrtps|rmw-cyclonedds|cyclonedds|rmw-implementation|rclpy|rclcpp)$/ || $2 ~ /^ros-[a-z]+-(rmw-fastrtps-cpp|rmw-fastrtps-shared-cpp|fastrtps)$/) {printf "%-44s %s\n", $2, $3}'
fi
has ros2 && has timeout && timeout 20 ros2 doctor --report 2>/dev/null | grep -iE "middleware|rmw|RMW_IMPLEMENTATION|distribution name" | head -6   # 遅いので 20 秒で打ち切る

sec "環境変数（ROS / RMW / FASTRTPS / FASTDDS / CYCLONEDDS / TB3）"
env | grep -E '^(ROS_|RMW_|FASTRTPS_|FASTDDS_|CYCLONEDDS_|TB3_|LDS_|TURTLEBOT3_)' | sort || true

sec "使っているプロファイルの中身"
shown=0
for f in "${FASTRTPS_DEFAULT_PROFILES_FILE:-}" "${FASTDDS_DEFAULT_PROFILES_FILE:-}" "${CYCLONEDDS_URI#file://}"; do
  if [ -n "$f" ] && [ -r "$f" ]; then echo "--- $f"; cat "$f"; shown=1; fi
done
[ "$shown" = 0 ] && echo "(プロファイルの指定なし = 既定の設定。CYCLONEDDS_URI が file:// 以外なら上の環境変数を見る)"

sec "ネットワーク: インタフェースと IP"
if has ip; then ip -br addr; echo; ip -4 route; echo; ip -6 route 2>/dev/null | head -5; else echo "ip コマンドなし"; fi

sec "ネットワーク: マルチキャスト（発見に使う 239.255.0.1 に参加しているか）"
has ip && ip maddr 2>/dev/null | head -30
[ -r /proc/net/igmp ] && head -20 /proc/net/igmp

sec "ネットワーク: Wi-Fi（あれば）"
wl=$(ls /sys/class/net 2>/dev/null | grep -E '^(wl|wlan)' | head -3)
if [ -z "$wl" ]; then echo "Wi-Fi インタフェースなし"; fi
for i in $wl; do
  echo "--- $i ($(cat /sys/class/net/$i/operstate 2>/dev/null))"
  if has iw; then iw dev "$i" link 2>&1 | head -12; iw dev "$i" get power_save 2>&1; else echo "iw なし（sudo apt install iw で、信号・速度・省電力が見える）"; fi
  has iwconfig && iwconfig "$i" 2>&1 | grep -E "Signal|Bit Rate|Tx-Power"
done

sec "ファイアウォール・待ち受け（読み取りのみ）"
has ss && ss -uln 2>/dev/null | awk 'NR==1 || /:7[0-9][0-9][0-9]\b|:11811\b/' | head -20
has ufw && (ufw status 2>/dev/null | head -5)

sec "CPU・負荷（機体のとき: Raspberry Pi の温度とスロットリング）"
nproc; cat /proc/loadavg
has vcgencmd && { vcgencmd measure_temp; vcgencmd get_throttled; }
echo
echo "(ここまで。結果の横に、ROS_DOMAIN_ID・機体と PC のプロファイル・ルーターの機種と周波数帯・測った場所も手で書き足すこと)"
