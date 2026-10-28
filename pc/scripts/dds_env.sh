# 設定を読み、ROS 2 Humble の環境を作り、PC 側の Fast DDS のプロファイルを作って export する（他のスクリプトから source する）
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/tb3_config.sh"
[ -r /opt/ros/humble/setup.bash ] || { echo "ROS 2 Humble が見つかりません。先に pc/scripts/setup_pc.sh を動かしてください" >&2; return 1 2>/dev/null || exit 1; }
. /opt/ros/humble/setup.bash
mkdir -p "$TB3_DATA_DIR"

# Wi-Fi 越しは、マルチキャストの発見が遅い（新しく起動したプロセスが機体を見つけるまで約 10 秒）ので、機体の IP へ直接も呼びかける
unset FASTRTPS_DEFAULT_PROFILES_FILE
if [ "$RMW_IMPLEMENTATION" = "rmw_fastrtps_cpp" ] && [ "$DDS_MODE" = "unicast" ]; then
  # tb3ctl が、Windows 側で引いた IP を ROBOT_IP で渡してくる（WSL は .local の名前を引けないことがある）
  ROBOT_IP="${ROBOT_IP:-}"
  [ -z "$ROBOT_IP" ] && [ -n "$ROBOT_HOST" ] && ROBOT_IP="$(getent ahostsv4 "$ROBOT_HOST" 2>/dev/null | awk '{print $1; exit}')"
  if [ -n "$ROBOT_IP" ]; then
    TB3_PC_PROFILE="$TB3_DATA_DIR/fastdds_pc.xml"
    cat > "$TB3_PC_PROFILE" <<XML
<?xml version="1.0" encoding="UTF-8" ?>
<!-- dds_env.sh が作った。機体 $ROBOT_HOST ($ROBOT_IP) へ、マルチキャストに加えて直接も発見を呼びかける -->
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <participant profile_name="default_participant" is_default_profile="true">
    <rtps>
      <builtin>
        <initialPeersList>
          <locator><udpv4><address>$ROBOT_IP</address></udpv4></locator>
        </initialPeersList>
      </builtin>
    </rtps>
  </participant>
</profiles>
XML
    export FASTRTPS_DEFAULT_PROFILES_FILE="$TB3_PC_PROFILE"
    TB3_DDS_NOTE="DDS: unicast peer $ROBOT_IP (+ multicast), domain $ROS_DOMAIN_ID"
  else
    TB3_DDS_NOTE="DDS: ROBOT_HOST ('${ROBOT_HOST}') の IP を引けないので、マルチキャストだけで発見します（Wi-Fi だと遅いことがあります）"
  fi
else
  TB3_DDS_NOTE="DDS: $RMW_IMPLEMENTATION / $DDS_MODE, domain $ROS_DOMAIN_ID"
fi
export TB3_DDS_NOTE
