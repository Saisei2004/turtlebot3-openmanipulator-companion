#!/bin/bash
# LDS-01 / LDS-02 のどちらで /scan が出るかを短時間ずつ試す
source /opt/ros/humble/setup.bash; source ~/turtlebot3_ws/install/setup.bash
export ROS_DOMAIN_ID=77
try() {
  echo "== $1"; "${@:2}" > /tmp/lds_$1.log 2>&1 & P=$!
  sleep 8
  timeout 6 ros2 topic echo --once /scan --field ranges 2>/dev/null | tr ',' '\n' | grep -cE '^ ?[0-9]+\.[0-9]*[1-9]' 
  kill -INT $P; sleep 2; kill -9 $P 2>/dev/null; pkill -9 -x hlds_laser_publ; pkill -9 -x ld08_driver; sleep 1
  tail -3 /tmp/lds_$1.log
}
try LDS-01 ros2 run hls_lfcd_lds_driver hlds_laser_publisher --ros-args -p port:=/dev/ttyUSB0 -p frame_id:=base_scan
try LDS-02 ros2 run ld08_driver ld08_driver --ros-args -p frame_id:=base_scan
