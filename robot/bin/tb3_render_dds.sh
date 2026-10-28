#!/bin/bash
# 機体の Fast DDS のプロファイル /etc/tb3/fastdds.xml を、今のネットワークの状態から作る。
# tb3-bringup / tb3-deadman の起動前（ExecStartPre）に動く。DHCP でも固定 IP でも、その時点の IP を使う。
#
# /etc/tb3/tb3.env の DDS_IFACE:
#   wlan0 / eth0 など = そのインタフェースの IPv4 アドレスだけで通信する（共有メモリは使わない）。
#                       IP が付くまで最大 TB3_NET_WAIT 秒（既定 90）待つ。付かなければ失敗（サービスは再試行する）
#   any               = 制限しない（Fast DDS の既定。有線を抜き差ししない使い方向け）
set -u
ENV="${TB3_ENV:-/etc/tb3/tb3.env}"
[ -r "$ENV" ] && . "$ENV"
IFACE="${DDS_IFACE:-wlan0}"
OUT="${TB3_DDS_OUT:-/etc/tb3/fastdds.xml}"
mkdir -p "$(dirname "$OUT")"

if [ "$IFACE" = "any" ]; then
  cat > "$OUT" <<'XML'
<?xml version="1.0" encoding="UTF-8" ?>
<!-- tb3_render_dds.sh が作った。DDS_IFACE=any: Fast DDS の既定のまま -->
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <participant profile_name="default_participant" is_default_profile="true">
    <rtps></rtps>
  </participant>
</profiles>
XML
  echo "tb3_render_dds: no interface restriction"
  exit 0
fi

IP=""
for _ in $(seq "${TB3_NET_WAIT:-90}"); do
  IP=$(ip -4 -o addr show dev "$IFACE" scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)
  [ -n "$IP" ] && break
  sleep 1
done
if [ -z "$IP" ]; then
  echo "tb3_render_dds: $IFACE has no IPv4 address after ${TB3_NET_WAIT:-90}s" >&2
  exit 1
fi

cat > "$OUT" <<XML
<?xml version="1.0" encoding="UTF-8" ?>
<!-- tb3_render_dds.sh が $(date -Is) に作った（起動のたびに作り直す）。
     機体の ROS 2 は $IFACE の IPv4 アドレス $IP だけを使う。有線の抜き差しで通信が壊れないようにするため。
     共有メモリは使わず、機体の中のノード同士も UDP でこの IP を通して話す -->
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor>
      <transport_id>tb3_iface_only</transport_id>
      <type>UDPv4</type>
      <interfaceWhiteList>
        <address>$IP</address>
      </interfaceWhiteList>
    </transport_descriptor>
  </transport_descriptors>
  <participant profile_name="default_participant" is_default_profile="true">
    <rtps>
      <useBuiltinTransports>false</useBuiltinTransports>
      <userTransports>
        <transport_id>tb3_iface_only</transport_id>
      </userTransports>
    </rtps>
  </participant>
</profiles>
XML
echo "tb3_render_dds: $IFACE $IP"
