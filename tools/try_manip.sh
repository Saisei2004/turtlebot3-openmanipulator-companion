#!/bin/bash
# manipulation を指令なしで起動し、コントローラと関節状態を確認して止める
source /opt/ros/humble/setup.bash; source ~/turtlebot3_ws/install/setup.bash
export TURTLEBOT3_MODEL=waffle_pi LDS_MODEL=LDS-01 ROS_DOMAIN_ID=77
ros2 launch turtlebot3_manipulation_bringup base.launch.py use_sim:=false use_fake_hardware:=false > /tmp/manip_try.log 2>&1 &
L=$!
sleep 25
ros2 control list_controllers
timeout 5 ros2 topic echo --once /joint_states --field position
timeout 5 ros2 topic echo --once /battery_state --field voltage
kill -INT $L; sleep 5
pkill -INT -x ros2_control_no; pkill -x robot_state_pub; sleep 2; pkill -9 -x ros2_control_no
pgrep -l -x "ros2_control_no|robot_state_pub|spawner" || echo "all stopped"
echo "errors: $(grep -c 'no status packet' /tmp/manip_try.log)"
grep -E "Connected|ERROR|WARN" /tmp/manip_try.log | grep -v FIFO | sort | uniq -c | head
