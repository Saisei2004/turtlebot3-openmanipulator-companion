# dds/ — DDS（ROS 2）の検証キット

この機体（TurtleBot3 + OpenManipulator-X、Raspberry Pi 4、Ubuntu 22.04、ROS 2 Humble、Fast DDS 2.6）で、PC との通信を測り、設定を比べるための道具と設定のひな形。
検証の進め方は [`docs/04-dds-verification-guide.md`](../docs/04-dds-verification-guide.md)、これまでに分かったことは [`docs/03-network-and-dds.md`](../docs/03-network-and-dds.md)。

## 道具（`dds/tools/`）

| 道具 | 動かす場所 | 何をするか |
|---|---|---|
| `echo_node.py` | 機体（相手側） | `/tb3_dds/ping` をそのまま `/tb3_dds/pong` に返す |
| `pingpong.py` | PC | ping を送り、往復時間（中央値・p95・p99・最大）・取りこぼし・途切れ・順番の入れ替わりを測る。大きさ 64 B〜64 KB、QoS、頻度を変えられる |
| `topic_stats.py` | PC（機体でも） | 既存トピック（`/scan` `/joint_states` `/tb3_pc_alive` など）の頻度・間隔の分布・最長の途切れ・閾値超えの数 |
| `discovery_time.py` | PC | 新しいプロセス（= 新しい DDS 参加者）が起動してから、相手が見え、最初の 1 件が届くまでの秒を N 回測る。`ros2 daemon` は使わない |
| `env_report.sh` | PC・機体 | 検証の条件（OS・バージョン・インタフェース・Wi-Fi・環境変数・プロファイルの中身）を記録する。読み取りだけ |
| `run_matrix.sh` | PC | プロファイル × 測定を順に回し、`dds/results/<日時>/` に CSV と環境の記録を残す |
| `selftest_local.sh` | PC | 機体なし・PC 1 台で、上の道具が動くことの自己点検（約 2 分、約 40 項目） |

| 設定 | 場所 | 何をするか |
|---|---|---|
| `render_profile.py` | `dds/` | プロファイルのひな形（`profiles/*.xml.in`）に IP などを入れて XML を書き出す。`--list` で一覧、`--shell` で必要な `export` を出す |
| `profiles/*.xml.in` | `dds/profiles/` | Fast DDS: `default` `multicast_only` `multicast_fast_announce` `unicast_peers` `interface_whitelist` `udp_only` `discovery_server` `discovery_super_client`。各ファイルの先頭に目的と注意 |
| `profiles/cyclonedds/` | | CycloneDDS: `cyclone_iface_peer` `cyclone_iface_multicast`（`CYCLONEDDS_URI` に指定する） |

すべて Python 3 + rclpy（numpy は使う）。使う前に ROS 2 Humble を読み込む（`source /opt/ros/humble/setup.bash`）。
設定済みの環境（ドメイン ID・プロファイル）で動かすなら `tb3ctl ros python3 dds/tools/pingpong.py ...`。

## まず動かす（機体なし・約 2 分）

```bash
source /opt/ros/humble/setup.bash
bash dds/tools/selftest_local.sh                 # 既定は auto: 既定ルートの IP だけを使うプロファイルで測る
```
同じ PC の中で `echo_node` と `pingpong`、ダミーの発行者と `discovery_time` / `topic_stats` が動く。最後の行が `結果: OK … / NG 0` なら道具は使える。
**インタフェースが複数ある PC（WSL の mirrored + Tailscale など）では、既定の設定だと同じ PC の中ですら参加者同士が見つからないことがある**（`[2b]` で分かる。詳しくは docs/03 の「この PC で再現した事象」）。

## 機体と測る（機体の電源を入れてから）

```bash
# 1. PC 側の確認（機体が見えるか）
tb3ctl status
tb3ctl ros python3 dds/tools/topic_stats.py --topic /scan --topic /tb3_pc_alive --duration 30 --gap-threshold 0.15

# 2. 往復時間（機体で echo_node を動かす。--robot-ssh を付けると /tmp に置いて動かし、終わったら消す）
bash dds/tools/run_matrix.sh --robot-ip <機体の IP> --pc-ip <PC の LAN の IP> --robot-ssh ubuntu@<機体の IP> \
     --profiles "default multicast_only unicast_peers udp_only" --measures "discovery pingpong stats"

# 3. 条件の記録（結果と一緒に残す）
bash dds/tools/env_report.sh > dds/results/env_pc.txt
ssh ubuntu@<機体の IP> 'bash -s' < dds/tools/env_report.sh > dds/results/env_robot.txt
```
機体側のサービスの停止・再起動は、これらの道具はしない。`--robot-ssh` で機体に触るのは、`echo_node.py` を `/tmp` に置いて動かし、止めて消すことだけ。

## プロファイルを使う

```bash
python3 dds/render_profile.py --list
eval "$(python3 dds/render_profile.py unicast_peers --robot-ip 192.168.11.100 -o /tmp/pc.xml --shell)"   # FASTRTPS_DEFAULT_PROFILES_FILE などを export
python3 dds/render_profile.py interface_whitelist --iface-ip 192.168.11.100 -o /tmp/wifi.xml           # 機体用（Wi-Fi の IP だけを使う）
```
CycloneDDS は `--shell` が `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` と `CYCLONEDDS_URI` を出す。`ros-humble-rmw-cyclonedds-cpp` が要る（`sudo apt install ros-humble-rmw-cyclonedds-cpp`。この PC では入れていないので、Cyclone は動かしていない）。

## 結果の置き場

`dds/results/` は git に入れない（`.gitignore`）。残したい結果は、env_report と一緒に `docs/` に表で書く（04 の末尾にひな形）。
