# 00. システムの全体像

## 何がどこで動くか

| 場所 | 部品 | 役割 |
|---|---|---|
| 機体 | `tb3-bringup`（サービス） | `turtlebot3_manipulation_bringup base.launch.py`（ros2_control: 車輪・アーム 4 関節・グリッパー・IMU）と LiDAR ドライバ `ld08_driver`（LDS-02） |
| 機体 | `tb3-deadman` | PC の心拍 `/tb3_pc_alive` が 0.3 秒途切れたら、腕をその場で止め、車輪を止める |
| 機体 | `tb3-watchdog` | ログに `Can't control (joints\|wheels)` が出たら（モーターの電源が落ちたとき）`tb3-bringup` を起動し直す（60 秒に 1 回まで） |
| 機体 | `wifi-powersave-off` | Wi-Fi の省電力を切る |
| 機体 | OpenCR（USB `/dev/ttyACM0`） | Dynamixel（車輪 2、アーム 4 関節、グリッパー）と IMU をつなぐ基板 |
| PC | `pc/server/tb3_server.py`（:8080） | 操作画面の配信、`/api/*`、MuJoCo の衝突判定 |
| PC | `pc/server/circle_driver.py`（`tb3_server.py` の中の ROS 2 ノード） | Orbit・Dance・グリッパーの開閉。心拍を出す |
| PC | `rosbridge_server`（:9090） | ブラウザ（WebSocket）⇔ ROS 2 |
| ブラウザ | `pc/server/webui/index.html` | 操作画面 |

## 通信の流れ

```
 ブラウザ ──ws:9090──► rosbridge ──DDS──► 機体: /cmd_vel, /arm_controller/joint_trajectory, /gripper_controller/gripper_cmd
 ブラウザ ◄─ws:9090── rosbridge ◄─DDS── 機体: /joint_states, /scan, /odom, /arm_controller/controller_state
 ブラウザ ──http:8080─► tb3_server.py    /api/check（衝突判定）, /api/library（姿勢の保存）, /api/circle, /api/dance
 circle_driver ──DDS──► 機体: /cmd_vel（20 Hz）, /arm_controller/joint_trajectory（0.5 秒ごと）, /gripper_controller/gripper_cmd, /tb3_pc_alive（20 Hz）
```

## ROS 2 のトピック

| トピック | 型 | 向き | 内容 |
|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | PC → 機体 | 車輪。画面のジョイスティック・キーは約 10 Hz、Orbit は 20 Hz。機体の `diff_drive_controller` は 0.5 秒（`cmd_vel_timeout`）来ないと止まる |
| `/arm_controller/joint_trajectory` | `trajectory_msgs/JointTrajectory` | PC → 機体 | アームの 4 関節（`joint1`〜`joint4`）。手先操作は先 0.2・0.4 秒の 2 点を 20 Hz、Dance は先 1.5 秒（0.1 秒ごと 15 点）を 0.5 秒ごと、READY・HOME などは 1 点（1.2〜4 秒） |
| `/gripper_controller/gripper_cmd` | `control_msgs/action/GripperCommand` | PC → 機体 | グリッパー。位置 -0.010（閉）〜 0.019（開）[m]、`max_effort: -1.0` |
| `/tb3_pc_alive` | `std_msgs/Int8` | PC → 機体 | 心拍（20 Hz）。値のビット: 1 = 車輪、2 = アーム、4 = グリッパーを PC が動かしている。0 = PC が自分で止めた（見張りを外す） |
| `/joint_states` | `sensor_msgs/JointState` | 機体 → PC | 車輪とアームの角度。OpenCR からの読み取りは 0.1 秒ごと（約 10 回/秒）。トピックは約 75 回/秒出るが、新しい値は 10 回/秒 |
| `/arm_controller/controller_state` | `control_msgs/JointTrajectoryControllerState` | 機体 → PC | コントローラが出している指令位置（`reference`）。画面の側面図はこれで描く |
| `/scan` | `sensor_msgs/LaserScan` | 機体 → PC | LiDAR（約 10 Hz） |
| `/odom` | `nav_msgs/Odometry` | 機体 → PC | 走行の速度（`open_loop: true`。指令を積分した値で、車輪の実測ではない） |
| `/imu_broadcaster/imu` | `sensor_msgs/Imu` | 機体 → PC | IMU |

`/battery_state` は**出ていない**（電圧は OpenCR の制御テーブルにあるが、ROS のトピックにしていない。`tools/read_battery.py` で読める。`tb3-bringup` を止めて使う）。

試験用（`TB3_DRYRUN=1` / `tb3ctl server --dry`）のとき、ドライバは機体に送らず、`/cmd_vel_dryrun`、`/arm_dryrun`、`/tb3_pc_alive_dryrun` に出す。グリッパーは何も送らない。

## PC の HTTP API（`tb3_server.py`、既定 :8080）

| API | 内容 |
|---|---|
| `GET /api/library` / `PUT /api/library` | 姿勢と動作列の読み出し・保存。保存先は `TB3_DATA_DIR/poses.json`（既定 `~/.local/share/tb3-companion/`）。初回は `home`（折りたたみ姿勢）だけ |
| `POST /api/check` | `{"poses": [[q1,q2,q3,q4], ...]}`（最大 400 件、`/joint_states` と同じ値）→ 各姿勢の `ok / hit / limit / depth_mm / torque_pct_200g`。MuJoCo で判定 |
| `GET /api/circle` | Orbit・Dance・グリッパーの状態（`running`、`link_ok`、`dry`、`arm.*`、`gripper.*`、`stop_reason` など） |
| `POST /api/circle` | `{"action":"start","radius":0.3,"speed":0.1,"dir":"left"}` または `{"action":"stop","what":"all\|orbit\|dance"}` |
| `POST /api/dance` | `{"arm":true,"gripper":true,"scale":0.9,"grip_period":4}`。始める前に MuJoCo で調べ、当たらない大きさに縮める。縮められなければ 409 |

## ポート

| ポート | 何 |
|---|---|
| TCP 8080 | 操作画面と `/api/*`（`SERVER_PORT`） |
| TCP 9090 | rosbridge（`ROSBRIDGE_PORT`）。**画面は `ws://<ホスト>:9090` に決め打ちで接続する**（`index.html`）。変えたら画面も直す |
| UDP 7400 + 250 × ROS_DOMAIN_ID から 250 個 | DDS（ドメイン 0 なら 7400〜7649）。Windows のファイアウォールで通す対象 |
| TCP 22 | 機体の ssh |

## ファイルの場所

| 場所 | 内容 |
|---|---|
| 機体 `/etc/tb3/tb3.env` | 機体の設定（`ROS_DOMAIN_ID`、`TURTLEBOT3_MODEL`、`LDS_MODEL`、`DDS_IFACE`、`TB3_JOINTS_PROFILE_ACCELERATION` / `_VELOCITY`）。`tb3ctl robot-apply` が書く |
| 機体 `/etc/tb3/fastdds.xml` | Fast DDS のプロファイル。**サービスの起動のたびに** `tb3_render_dds.sh` が、`DDS_IFACE` のその時点の IP で作り直す |
| 機体 `/etc/tb3/env.sh` | ログインしたときの ROS 2 の環境（`~/.bashrc` が読む） |
| 機体 `/usr/local/bin/` | `tb3_bringup.sh` `tb3_deadman.py` `tb3_watchdog.sh` `tb3_render_dds.sh` `tb3_flash_opencr.sh` `tb3_set_wifi.py` |
| 機体 `/etc/systemd/system/` | `tb3-bringup.service` `tb3-deadman.service` `tb3-watchdog.service` `wifi-powersave-off.service` |
| 機体 `/etc/udev/rules.d/` | `99-turtlebot3-cdc.rules`（OpenCR を ModemManager に掴ませない）、`98-tb3-opencr-restart.rules`（OpenCR がつなぎ直されたら `tb3-bringup` を起動し直す） |
| 機体 `~/turtlebot3_ws` | `ld08_driver` と、パッチを当てた `turtlebot3_manipulation_hardware`（apt 版を上書きする overlay） |
| 機体 `~/tb3-companion/robot/` | `tb3ctl` が転送したこのリポジトリの `robot/`（`robot.env` を含む） |
| PC `config/tb3.env` | PC 側の設定（`config/tb3.env.example` が見本） |
| PC `TB3_DATA_DIR`（既定 `~/.local/share/tb3-companion/`。WSL なら WSL の中） | `poses.json`、`fastdds_pc.xml`（起動のたびに作る PC 側の DDS 設定） |

## 座標と角度の約束（要約。詳細は [05](05-arm-kinematics-and-mujoco.md)）

| 記号 | 意味 |
|---|---|
| `q` | `/joint_states` の値であり、`/arm_controller/joint_trajectory` に出す値（画面のスライダー・API の `poses` もこれ） |
| `a` | URDF 側の関節角。`a = q + OFFSET`、`OFFSET = [0, 0.93, 0.07, -1.65]` [rad]。この機体のアームは関節の 0 位置が URDF とずれているため（カメラで実測） |
| `r, z, pitch` | 側面図の座標。原点は joint2 の軸、`r` は前方、`z` は上、`pitch` は手先の下向き角（+90° で真下） |
| 関節限界 | URDF の限界は `a` に対するもの。`q` では joint2 [-2.7207, 0.6408]、joint3 [-1.0125, 1.3123]、joint4 [-0.1407, 3.1416] rad |

## 設定のキー（`config/tb3.env`）

`ROBOT_HOST` `ROBOT_USER` `ROBOT_SSH_KEY` `ROS_DOMAIN_ID` `RMW_IMPLEMENTATION` `DDS_MODE`（`unicast` / `multicast`）`TURTLEBOT3_MODEL` `LDS_MODEL` `DDS_IFACE`（`wlan0` / `eth0` / `any`）`JOINTS_PROFILE_ACCELERATION` `JOINTS_PROFILE_VELOCITY` `SERVER_PORT` `ROSBRIDGE_PORT` `WSL_DISTRO`。意味は `config/tb3.env.example` のコメント。
