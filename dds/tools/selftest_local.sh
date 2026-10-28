#!/usr/bin/env bash
# 機体なし・この PC 1 台だけで、道具が動くことを確かめる自己点検（約 2 分）。ほかの機器・機体には何も送らない。
# 使い方:  source /opt/ros/humble/setup.bash && bash dds/tools/selftest_local.sh [--iface-ip auto|<この PC の LAN の IP>|none]
#   既定は auto（既定ルートの送信元 IP を 1 つ選び、interface_whitelist でその IP だけを使って測る）。
#   none にすると Fast DDS の既定のまま（全インタフェース）で測る。
#   WSL（mirrored）+ Tailscale のように、インタフェースが複数ある PC では、既定のままだと同じ PC の中ですら見つからないことがある
#   （この道具を作った PC で再現: [2b]）。そのときは auto のまま使う。
# ROS_DOMAIN_ID は、ほかの通信と混ざらないよう 91 にする（SELFTEST_DOMAIN で変えられる）。
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DDS="$(cd "$HERE/.." && pwd)"
export ROS_DOMAIN_ID="${SELFTEST_DOMAIN:-91}"
IFACE="auto"; [ "${1:-}" = "--iface-ip" ] && IFACE="${2:-auto}"
if [ "$IFACE" = auto ]; then
  IFACE="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -1)"
  [ -z "$IFACE" ] && IFACE=none
fi
pass=0; fail=0
ok()  { echo "  OK   $1"; pass=$((pass+1)); }
ng()  { echo "  NG   $1"; fail=$((fail+1)); }
chk() { local msg="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$msg"; else ng "$msg"; fi; }
tmp="$(mktemp -d)"
cleanup() { kill $EP $DP 2>/dev/null; rm -rf "$tmp"; }
EP=""; DP=""; trap cleanup EXIT

echo "[1] 構文"
for f in "$HERE"/*.py "$DDS/render_profile.py"; do chk "py_compile $(basename "$f")" python3 -m py_compile "$f"; done
for f in "$HERE"/*.sh; do chk "bash -n $(basename "$f")" bash -n "$f"; done

echo "[2] プロファイルを描いて、XML として読めるか"
for n in $(python3 "$DDS/render_profile.py" --list | awk '{print $1}'); do
  chk "render $n" python3 "$DDS/render_profile.py" "$n" --robot-ip 192.0.2.10 --pc-ip 192.0.2.20 --iface-ip 192.0.2.20 --server-ip 192.0.2.10 -o "$tmp/$(echo "$n" | tr / _).xml"
  chk "xml   $n" python3 -c "import sys,xml.etree.ElementTree as E; E.parse(sys.argv[1])" "$tmp/$(echo "$n" | tr / _).xml"
done

echo "[2a] Fast DDS が各プロファイルを読めるか（XMLPARSER のエラーが出ないか。各 2 秒）"
for n in default multicast_only multicast_fast_announce unicast_peers interface_whitelist udp_only discovery_server discovery_super_client; do
  python3 "$DDS/render_profile.py" "$n" --robot-ip 192.0.2.10 --iface-ip "${IFACE:-192.0.2.20}" --server-ip 192.0.2.10 -o "$tmp/load_$n.xml" >/dev/null 2>&1
  err="$(FASTRTPS_DEFAULT_PROFILES_FILE="$tmp/load_$n.xml" timeout 20 python3 -c "import rclpy; rclpy.init(); n=rclpy.create_node('x'); rclpy.spin_once(n, timeout_sec=1.5); print('created')" 2>&1)"
  if echo "$err" | grep -q "XMLPARSER"; then ng "load $n"; echo "$err" | grep XMLPARSER | head -2 | sed 's/^/    /'; elif echo "$err" | grep -q created; then ok "load $n"; else ng "load $n（起動できず）"; fi
done

echo "[2b] 既定の設定（全インタフェース）で、同じ PC の中の参加者同士が見つかるか（参考。見つからなくても NG にしない）"
out="$(python3 "$HERE/discovery_time.py" --dummy-publisher --runs 1 --timeout 12 2>&1)"
if echo "$out" | grep -q "届かなかった回 0 / 1"; then echo "  既定のままで見つかった"; else echo "  既定のままでは見つからなかった → この PC では、IP を 1 つに絞る（interface_whitelist）必要がある"; fi
ip -o link show 2>/dev/null | awk '{printf "    %s %s\n", $2, $3}' | head -8

if [ "$IFACE" != none ]; then
  echo "[3] 以降は interface_whitelist（$IFACE だけを使う）で測る"
  eval "$(python3 "$DDS/render_profile.py" interface_whitelist --iface-ip "$IFACE" -o "$tmp/wl.xml" --shell)"
else
  echo "[3] 以降は既定の設定で測る"
fi

echo "[3] 往復時間（echo_node と pingpong を同じ PC で、domain $ROS_DOMAIN_ID）"
python3 "$HERE/echo_node.py" --qos reliable --report-every 0 >"$tmp/echo.log" 2>&1 & EP=$!
sleep 3
out="$(python3 "$HERE/pingpong.py" --size 64 --hz 50 --duration 5 --label selftest --csv "$tmp/pp.csv" 2>&1)"; echo "$out" | sed 's/^/    /' | grep -v RESULT
echo "$out" | grep -q "取りこぼし 0.0 %" && ok "pingpong 64 B: 取りこぼしなし" || ng "pingpong 64 B"
out="$(python3 "$HERE/pingpong.py" --size 65536 --hz 20 --duration 5 --label selftest --csv "$tmp/pp.csv" 2>&1)"; echo "$out" | sed 's/^/    /' | grep -v RESULT
echo "$out" | grep -q "送信" && ! echo "$out" | grep -q "取りこぼし 100" && ok "pingpong 64 KB" || ng "pingpong 64 KB"
out="$(python3 "$HERE/pingpong.py" --size 64 --hz 50 --duration 4 --qos best_effort --wait-match 6 2>&1)"; echo "$out" | sed 's/^/    /' | grep -v RESULT | head -3
echo "$out" | grep -q "echo_node が見つかりません" && ok "QoS が合わないとき（reliable の echo に best_effort の pingpong）は、つながらず終了コード 3 で知らせる" || echo "  (参考) best_effort の pingpong も reliable の echo とつながった"
kill $EP 2>/dev/null; wait $EP 2>/dev/null; EP=""
chk "CSV に行が書かれた" test "$(wc -l < "$tmp/pp.csv")" -ge 3

echo "[4] 発見の時間（ダミーの発行者に対して 3 回）"
out="$(python3 "$HERE/discovery_time.py" --dummy-publisher --runs 3 --interval 1 --csv "$tmp/dt.csv" --label selftest 2>&1)"; echo "$out" | sed 's/^/    /' | grep -v RESULT
echo "$out" | grep -q "届かなかった回 0 / 3" && ok "discovery_time" || ng "discovery_time"

echo "[5] 既存トピックの届き方（ダミーの発行者を 10 秒）"
python3 "$HERE/discovery_time.py" --dummy --dummy-hz 20 >/dev/null 2>&1 & DP=$!
sleep 3
out="$(python3 "$HERE/topic_stats.py" --topic /dds_test/dummy --duration 10 --expected-hz 20 --csv "$tmp/ts.csv" --label selftest 2>&1)"; echo "$out" | sed 's/^/    /' | grep -v RESULT
kill $DP 2>/dev/null; wait $DP 2>/dev/null; DP=""
echo "$out" | grep -q "件" && ! echo "$out" | grep -q "1 件も届かない" && ok "topic_stats" || ng "topic_stats"

echo "[6] 条件の記録"
chk "env_report.sh" bash "$HERE/env_report.sh"

echo; echo "結果: OK $pass / NG $fail"
[ "$fail" = 0 ]
