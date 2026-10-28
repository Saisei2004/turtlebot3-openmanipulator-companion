# 第三者のもの（NOTICE）

このリポジトリには、第三者の著作物の一部（またはそれから作ったもの）が入っている。ライセンス名は、この作業で確かめられたものだけを書く。確かめていないものは「要確認」。公開する前に、持ち主が原典で確認すること。

| 何 | どこにあるか | ライセンス | 確かめた方法 |
|---|---|---|---|
| ROBOTIS `turtlebot3_manipulation_hardware`（ros2_control のハードウェアプラグイン）の改変（通信を減らすパッチ） | `robot/hardware_patch/*.patch`。`apply.sh` が、公式 `ROBOTIS-GIT/turtlebot3_manipulation`（humble）の `814f140`（v2.2.1）から取ってきて当てる。公式のソースそのものはリポジトリに入れていない | Apache-2.0（Copyright 2022 ROBOTIS CO., LTD.） | 公式のソース `turtlebot3_manipulation_system.cpp` のヘッダ（2026-10-25 に読んだ） |
| OpenManipulator-X / TurtleBot3 のメッシュ（STL）と、そこから作った凸分解の部品 | `pc/server/workspace/meshes/`（`parts/` は `mesh_parts.py` が作った派生物）。機体の `/opt/ros/humble/share/turtlebot3_manipulation_description/` などから読み取りでコピーした | **要確認**（ROBOTIS のパッケージ。Apache-2.0 と推測するが、メッシュ個別のライセンスは確かめていない） | 未確認 |
| 機体の `robot_description`（xacro から生成した URDF） | `pc/server/workspace/robot.urdf` | **要確認**（上と同じ。ファイルの先頭は「xacro が自動生成した」とだけある） | ファイルの先頭 |
| OpenCR のファームウェア `turtlebot3_manipulation.opencr`（V230127R1） | **リポジトリには入れていない**。`robot/bin/tb3_flash_opencr.sh` が `https://github.com/ROBOTIS-GIT/OpenCR-Binaries/raw/master/turtlebot3/ROS2/latest/opencr_update.tar.bz2` から取ってくる（約 360 KB。2026-10-28 に HTTP 200 を確認） | **要確認**（ROBOTIS） | 未確認 |
| MuJoCo | `pip install mujoco`（`pc/scripts/setup_pc.sh`）。3.11.0 で確認 | **要確認**（pip のメタデータの License 欄は空だった。公式の表記を確かめる） | `pip show mujoco` |
| roslib 1.4.1（ブラウザから rosbridge を使う JavaScript） | 画面が CDN（`cdn.jsdelivr.net/npm/roslib@1.4.1`）から読む。リポジトリには入れていない | BSD-2-Clause | npm の `package.json` の `license` |
| rosbridge_suite（`rosbridge_server`） | apt（`ros-humble-rosbridge-server`） | BSD | `/opt/ros/humble/share/rosbridge_server/package.xml` |
| teleop_twist_keyboard | apt | BSD License 2.0 | 同上の `package.xml` |
| control_msgs | apt | BSD-3-Clause | 同上の `package.xml` |
| ROS 2 Humble（rclpy など） | apt | Apache-2.0 など、パッケージごと（rclpy は Apache License 2.0） | `package.xml` |
| ROBOTIS `ld08_driver`（LDS-02 の LiDAR ドライバ） | リポジトリには入れていない。`install_robot.sh` が `ROBOTIS-GIT/ld08_driver`（humble）を git clone してビルドする | **要確認** | 未確認 |
| Fast DDS / CycloneDDS | ROS 2 の apt パッケージ | **要確認** | 未確認 |

## 参考にしたもの（コードは取り込んでいない）

- ROBOTIS e-Manual（TurtleBot3 の SBC Setup、Humble）。Dynamixel XM430-W350 の失速トルク 4.1 N·m（12 V）もここの値。
