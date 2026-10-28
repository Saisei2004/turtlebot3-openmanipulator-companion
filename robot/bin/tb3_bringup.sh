#!/bin/bash
# 機体の常駐起動: アーム付き TurtleBot3（ros2_control）と LiDAR（LDS-02）を立ち上げる。
# 環境変数（ROS_DOMAIN_ID, TURTLEBOT3_MODEL, LDS_MODEL, FASTRTPS_DEFAULT_PROFILES_FILE ...）は
# systemd の EnvironmentFile=/etc/tb3/tb3.env と tb3-bringup.service が渡す。
set -e
source /opt/ros/humble/setup.bash
[ -r "$HOME/turtlebot3_ws/install/setup.bash" ] && source "$HOME/turtlebot3_ws/install/setup.bash"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}" TURTLEBOT3_MODEL="${TURTLEBOT3_MODEL:-waffle_pi}" LDS_MODEL="${LDS_MODEL:-LDS-02}"
ros2 run ld08_driver ld08_driver --ros-args -p frame_id:=base_scan &
exec ros2 launch turtlebot3_manipulation_bringup base.launch.py use_sim:=false use_fake_hardware:=false
