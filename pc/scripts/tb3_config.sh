# tb3-companion の設定を読む（他のスクリプトから `source` する）。
# 探し順: $TB3_CONFIG → <リポジトリ>/config/tb3.env → ~/.config/tb3-companion/tb3.env。無ければ既定値のまま。
_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
for _f in "${TB3_CONFIG:-}" "$_ROOT/config/tb3.env" "$HOME/.config/tb3-companion/tb3.env"; do
  if [ -n "$_f" ] && [ -r "$_f" ]; then
    set -a; . <(tr -d '\r' < "$_f"); set +a      # Windows のメモ帳などで直しても（改行が CRLF でも）読める
    TB3_CONFIG_USED="$_f"
    break
  fi
done
ROBOT_HOST="${ROBOT_HOST:-}"
ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
DDS_MODE="${DDS_MODE:-unicast}"
SERVER_PORT="${SERVER_PORT:-8080}"
ROSBRIDGE_PORT="${ROSBRIDGE_PORT:-9090}"
TB3_DATA_DIR="${TB3_DATA_DIR:-$HOME/.local/share/tb3-companion}"
export ROS_DOMAIN_ID RMW_IMPLEMENTATION TB3_DATA_DIR ROSBRIDGE_PORT SERVER_PORT
