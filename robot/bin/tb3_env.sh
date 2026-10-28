# 機体にログインしたときの ROS 2 の環境（~/.bashrc から source される）。サービスと同じ設定を使う
[ -r /etc/tb3/tb3.env ] && { set -a; . /etc/tb3/tb3.env; set +a; }
[ -r /opt/ros/humble/setup.bash ] && . /opt/ros/humble/setup.bash
[ -r "$HOME/turtlebot3_ws/install/setup.bash" ] && . "$HOME/turtlebot3_ws/install/setup.bash"
[ -r /etc/tb3/fastdds.xml ] && export FASTRTPS_DEFAULT_PROFILES_FILE=/etc/tb3/fastdds.xml
