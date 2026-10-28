#!/usr/bin/env bash
# プロファイル × 測定 を順に回して、results/<日時>/ に CSV と環境の記録を残す。
#
#   測定: discovery（発見の時間）/ pingpong（往復時間。相手側に echo_node.py が要る）/ stats（既存トピックの届き方）
#
# 機体側には勝手に触らない。--robot-ssh user@host を付けたときだけ、echo_node.py の起動と停止に限って ssh/scp を使う
# （echo_node.py を機体の /tmp にコピーして動かし、終わったら止めて消す。サービスの停止・再起動はしない）。
# 付けないときは、やることを標準出力に案内して待つ（--yes で待たない）。
#
# 例（機体が Wi-Fi の 192.168.11.100、PC の LAN 側が 192.168.11.9）:
#   bash run_matrix.sh --robot-ip 192.168.11.100 --pc-ip 192.168.11.9 \
#        --profiles "default multicast_only unicast_peers udp_only" --measures "discovery pingpong stats" \
#        --robot-ssh ubuntu@192.168.11.100
# --wait N: 発見・相手待ちの最長の秒（既定 30。届かないプロファイルで長く待たないよう、短くしてもよい）
# 機体なしの動作確認（同じ PC の中だけ）:
#   bash run_matrix.sh --local --profiles "default udp_only interface_whitelist" --iface-ip <この PC の IP> --duration 8
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DDS="$(cd "$HERE/.." && pwd)"
PROFILES="default"; MEASURES="discovery pingpong stats"
ROBOT_IP=""; PC_IP=""; IFACE_IP=""; DOMAIN="${ROS_DOMAIN_ID:-0}"; ROBOT_SSH=""; DURATION=20; SIZE=64; HZ=20
TOPIC="/scan"; TYPE="sensor_msgs/msg/LaserScan"; RUNS=5; WAIT=30; OUT=""; YES=0; DRY=0; LOCAL=0; QOS="reliable"; LABEL_EXTRA=""
usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --profiles) PROFILES="$2"; shift 2;;      --measures) MEASURES="$2"; shift 2;;
    --robot-ip) ROBOT_IP="$2"; shift 2;;       --pc-ip) PC_IP="$2"; shift 2;;
    --iface-ip) IFACE_IP="$2"; shift 2;;       --domain-id) DOMAIN="$2"; shift 2;;
    --robot-ssh) ROBOT_SSH="$2"; shift 2;;     --duration) DURATION="$2"; shift 2;;
    --size) SIZE="$2"; shift 2;;               --hz) HZ="$2"; shift 2;;
    --topic) TOPIC="$2"; shift 2;;             --type) TYPE="$2"; shift 2;;
    --runs) RUNS="$2"; shift 2;;               --wait) WAIT="$2"; shift 2;;               --qos) QOS="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;                 --label) LABEL_EXTRA="$2"; shift 2;;
    --yes) YES=1; shift;;                      --dry-run) DRY=1; shift;;
    --local) LOCAL=1; shift;;                  -h|--help) usage 0;;
    *) echo "不明な引数: $1" >&2; usage 2;;
  esac
done
export ROS_DOMAIN_ID="$DOMAIN"
[ -z "${ROS_DISTRO:-}" ] && [ -r /opt/ros/humble/setup.bash ] && . /opt/ros/humble/setup.bash
TS="$(date +%Y%m%d-%H%M%S)"; OUT="${OUT:-$DDS/results/$TS}"; mkdir -p "$OUT"
[ "$LOCAL" = 1 ] && { ROBOT_IP="${ROBOT_IP:-127.0.0.1}"; IFACE_IP="${IFACE_IP:-127.0.0.1}"; }
[ -z "$IFACE_IP" ] && IFACE_IP="$PC_IP"
echo "出力先: $OUT   domain=$DOMAIN   profiles=[$PROFILES]   measures=[$MEASURES]   local=$LOCAL"
run() { if [ "$DRY" = 1 ]; then echo "  [dry-run] $*"; else "$@"; fi; }
pause() { [ "$YES" = 1 ] || [ "$DRY" = 1 ] || read -r -p "$1 （準備できたら Enter） " _; }

ECHO_PID=""; REMOTE_ECHO=0
start_echo() {                 # echo_node.py を相手側で動かす。いまの環境（プロファイル）で
  if [ "$LOCAL" = 1 ]; then
    if [ "$DRY" = 1 ]; then echo "  [dry-run] python3 echo_node.py（この PC の中）"; else
      python3 "$HERE/echo_node.py" --qos "$QOS" --report-every 0 >"$OUT/echo_local.log" 2>&1 &
      ECHO_PID=$!; sleep 2
    fi
  elif [ -n "$ROBOT_SSH" ]; then
    echo "  機体で echo_node を起動（ssh: $ROBOT_SSH。/tmp に置くだけ。サービスには触らない）"
    run scp -q "$HERE/echo_node.py" "$HERE/common.py" "$ROBOT_SSH:/tmp/" || return 1
    # 機体のサービスと同じ環境（プロファイル）で動かす。/etc/tb3/fastdds.xml（tb3_render_dds.sh が起動のたびに描く）、無ければ /run/tb3/fastdds.xml、/etc/tb3/fastdds_wifi.xml（最初の手作業の構成）の順
    run ssh "$ROBOT_SSH" "bash -lc 'source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=$DOMAIN; for f in /etc/tb3/fastdds.xml /run/tb3/fastdds.xml /etc/tb3/fastdds_wifi.xml; do [ -r \$f ] && export FASTRTPS_DEFAULT_PROFILES_FILE=\$f && break; done; cd /tmp && nohup python3 echo_node.py --qos $QOS --report-every 0 > /tmp/tb3_dds_echo.log 2>&1 & echo \$! > /tmp/tb3_dds_echo.pid'"
    REMOTE_ECHO=1; sleep 3
  else
    echo "  ★ 機体（相手側）で echo_node を動かしてください（機体の ROS 環境で。QoS は $QOS）:"
    echo "      scp dds/tools/echo_node.py dds/tools/common.py ubuntu@<機体>:/tmp/ && ssh ubuntu@<機体> 'cd /tmp && source /opt/ros/humble/setup.bash && ROS_DOMAIN_ID=$DOMAIN python3 echo_node.py --qos $QOS'"
    pause "echo_node を動かしましたか"
  fi
}
stop_echo() {
  [ -n "$ECHO_PID" ] && { kill "$ECHO_PID" 2>/dev/null; wait "$ECHO_PID" 2>/dev/null; ECHO_PID=""; }
  if [ "$REMOTE_ECHO" = 1 ]; then
    run ssh "$ROBOT_SSH" 'kill $(cat /tmp/tb3_dds_echo.pid) 2>/dev/null; rm -f /tmp/tb3_dds_echo.pid /tmp/echo_node.py /tmp/common.py /tmp/tb3_dds_echo.log'
    REMOTE_ECHO=0
  fi
}
trap 'stop_echo' EXIT

{ echo "# run_matrix $(date -Is)"; echo "args: profiles=[$PROFILES] measures=[$MEASURES] robot_ip=$ROBOT_IP pc_ip=$PC_IP iface_ip=$IFACE_IP domain=$DOMAIN duration=$DURATION size=$SIZE hz=$HZ qos=$QOS topic=$TOPIC local=$LOCAL"; } > "$OUT/matrix.txt"

for prof in $PROFILES; do
  echo; echo "=== プロファイル: $prof ==="
  X="$OUT/profile_$(echo "$prof" | tr '/' '_').xml"
  exports="$(python3 "$DDS/render_profile.py" "$prof" --robot-ip "${ROBOT_IP:-}" --pc-ip "${PC_IP:-}" --iface-ip "${IFACE_IP:-}" --server-ip "${ROBOT_IP:-}" --domain-id "$DOMAIN" -o "$X" --shell)" || {
    echo "  このプロファイルは描けませんでした（足りない引数があるかも）。飛ばします" | tee -a "$OUT/matrix.txt"; continue; }
  eval "$exports"
  case "${RMW_IMPLEMENTATION:-}" in rmw_cyclonedds_cpp) ros2 pkg prefix rmw_cyclonedds_cpp >/dev/null 2>&1 || { echo "  rmw_cyclonedds_cpp が入っていません（sudo apt install ros-humble-rmw-cyclonedds-cpp）。飛ばします" | tee -a "$OUT/matrix.txt"; continue; };; esac
  bash "$HERE/env_report.sh" > "$OUT/env_pc_$(echo "$prof" | tr '/' '_').txt" 2>&1
  for m in $MEASURES; do
    label="${prof}${LABEL_EXTRA:+_$LABEL_EXTRA}"
    case "$m" in
      discovery)
        if [ "$LOCAL" = 1 ]; then run python3 "$HERE/discovery_time.py" --dummy-publisher --runs "$RUNS" --timeout "$WAIT" --csv "$OUT/discovery.csv" --label "$label"
        else run python3 "$HERE/discovery_time.py" --topic "$TOPIC" --type "$TYPE" --runs "$RUNS" --timeout "$WAIT" --csv "$OUT/discovery.csv" --label "$label"; fi;;
      pingpong)
        start_echo || { echo "  echo_node を起動できず、pingpong を飛ばします"; continue; }
        run python3 "$HERE/pingpong.py" --size "$SIZE" --hz "$HZ" --duration "$DURATION" --qos "$QOS" --csv "$OUT/pingpong.csv" --label "$label" --wait-match "$WAIT"
        [ $? = 3 ] && echo "  → echo_node が見つかりませんでした（プロファイル $prof では相手と話せない可能性。相手側の設定と合っているか確認）" | tee -a "$OUT/matrix.txt"
        stop_echo;;
      stats)
        if [ "$LOCAL" = 1 ]; then
          python3 "$HERE/discovery_time.py" --dummy --dummy-hz 20 >/dev/null 2>&1 & DP=$!; sleep 3
          run python3 "$HERE/topic_stats.py" --topic /dds_test/dummy --type std_msgs/msg/UInt8MultiArray --duration "$DURATION" --expected-hz 20 --csv "$OUT/stats.csv" --label "$label"
          kill $DP 2>/dev/null; wait $DP 2>/dev/null
        else run python3 "$HERE/topic_stats.py" --topic "$TOPIC" --duration "$DURATION" --wait-type "$WAIT" --csv "$OUT/stats.csv" --label "$label"; fi;;
      *) echo "不明な測定: $m（discovery / pingpong / stats）";;
    esac
  done
done
echo; echo "完了。結果: $OUT"; ls -1 "$OUT" 2>/dev/null | sed 's/^/  /'
echo "条件の記録（env_pc_*.txt）と一緒に保存してください。機体側の記録は: ssh <機体> 'bash -s' < dds/tools/env_report.sh"
