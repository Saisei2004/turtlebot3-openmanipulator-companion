#!/bin/bash
# tb3-bringup がモーターと通信できなくなったら（電池切れ・電圧低下など）起動し直す。起動し直しは 60 秒に 1 回まで
while true; do
  journalctl -u tb3-bringup -f -n 0 -o cat | grep -m1 -E "Can't control (joints|wheels)" >/dev/null
  echo "motor link lost; restarting tb3-bringup"
  systemctl restart tb3-bringup.service
  sleep 60
done
