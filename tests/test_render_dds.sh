#!/bin/bash
# robot/bin/tb3_render_dds.sh が、DDS_IFACE=any / 実在するインタフェース / 存在しないインタフェース で正しく動くか（機体なしで確かめる）
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export TB3_DDS_OUT="$(mktemp)" TB3_ENV=/nonexistent
fail=0
ok() { echo "OK   $*"; }
ng() { echo "NG   $*"; fail=1; }

DDS_IFACE=any bash "$ROOT/robot/bin/tb3_render_dds.sh" >/dev/null
grep -q interfaceWhiteList "$TB3_DDS_OUT" && ng "any: ホワイトリストが入っている" || ok "any: 制限なしのプロファイル"
python3 -c "import xml.dom.minidom,sys; xml.dom.minidom.parse('$TB3_DDS_OUT')" && ok "any: XML として正しい" || ng "any: XML が壊れている"

IF=$(ip -4 -o addr show scope global | awk '{print $2}' | head -1)
if [ -n "$IF" ]; then
  IP=$(ip -4 -o addr show dev "$IF" scope global | awk '{print $4}' | cut -d/ -f1 | head -1)
  DDS_IFACE="$IF" bash "$ROOT/robot/bin/tb3_render_dds.sh" >/dev/null
  grep -q "<address>$IP</address>" "$TB3_DDS_OUT" && ok "$IF: その IP ($IP) だけを通す" || ng "$IF: IP がプロファイルに入っていない"
  grep -q "<useBuiltinTransports>false" "$TB3_DDS_OUT" && ok "$IF: 共有メモリなし" || ng "$IF: 組み込みの通信手段が残っている"
  python3 -c "import xml.dom.minidom; xml.dom.minidom.parse('$TB3_DDS_OUT')" && ok "$IF: XML として正しい" || ng "$IF: XML が壊れている"
else
  echo "SKIP 実在するインタフェースが無い"
fi

if DDS_IFACE=nope0 TB3_NET_WAIT=2 bash "$ROOT/robot/bin/tb3_render_dds.sh" >/dev/null 2>&1; then ng "存在しないインタフェースで成功してしまう"; else ok "存在しないインタフェースは失敗する（サービスは再試行する）"; fi
rm -f "$TB3_DDS_OUT"
exit $fail
