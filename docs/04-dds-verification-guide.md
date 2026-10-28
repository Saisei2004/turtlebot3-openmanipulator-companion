# 04. DDS 検証ガイド

この機体を使って DDS（ROS 2）の検証を進めるための、実験の一覧と進め方。道具は [`dds/README.md`](../dds/README.md)、これまでに分かったことと設定の知識は [03-network-and-dds.md](03-network-and-dds.md)。
**この章の「目安」は、測るときの目当てとして私が置いたもの（規格や公式の値ではない）。結果を見て、検証する人が決め直してよい。**

## 1. 目的

1. 機体（Wi-Fi）と PC の間で、ROS 2 の通信が、どれだけ速く見つかり（発見）、どれだけ遅れ、どれだけ途切れるかを、設定ごとに数字で比べる。
2. 有線・Wi-Fi の抜き差しや、AP（ルーター）の切り替えで、通信が壊れにくい設定を決める。
3. 機体の安全の仕組み（PC が 0.3 秒黙ると腕と車輪を止める見張り）が、通信の揺れで誤って止めないか、止めるべきときに止まるかを確かめる。
4. Fast DDS と CycloneDDS、マルチキャスト・ユニキャスト・Discovery Server を比べる。

## 2. 準備

### 2.1 構成

```
 PC ── tb3ctl server ──┬─ 操作画面 :8080 / rosbridge :9090
 （有線）               └─ circle_driver ── 心拍 /tb3_pc_alive 20 Hz（Orbit・Dance・グリッパー動作中だけ出る）
        │  ROS 2 / DDS（UDP 7400〜7700）
 ルーター ── Wi-Fi ──  機体: tb3-bringup（ros2_control_node, ld08_driver, …）/ tb3-deadman（心拍が 0.3 秒途切れたら停止）
```
機体の通信の相手は PC だけ。検証用に新しいトピック（`/tb3_dds/ping` `/tb3_dds/pong`）を足すが、機体の既存のトピックには触らない。

### 2.2 必要な設定

- PC: WSL2（mirrored）+ Ubuntu 22.04 + ROS 2 Humble、または Ubuntu 22.04 の PC。セットアップは [01-quickstart-new-pc.md](01-quickstart-new-pc.md)。Windows の場合のファイアウォール規則（UDP 7400〜7700、TCP 8080・9090）は管理者で `pc/scripts/windows/allow_wsl_ros2_firewall.ps1`。
- 機体: [02-robot-provisioning.md](02-robot-provisioning.md) の構成（Wi-Fi の固定 IP、`DDS_IFACE=wlan0`、サービス 3 つ）。
- `tb3ctl init` で `config/tb3.env` を作る（`ROBOT_HOST`・`ROS_DOMAIN_ID`・`DDS_MODE`）。
- 確認: `tb3ctl status`（機体の IP・サービス・Wi-Fi の信号が出る）。
- 道具の自己点検（機体なし）: `bash dds/tools/selftest_local.sh`。

### 2.3 安全

- **ネットワークを乱す実験（D・E・I・J）の間は、Orbit（円走行）と Dance を動かさない**。機体は、通信が切れると停止する作りだが、停止の前後で腕と車輪が動くので、機体を床のあいた場所に置き、腕の周りに物を置かない。
- 心拍（`/tb3_pc_alive`）は、Orbit・Dance・グリッパー動作の最中だけ出る。心拍だけを測りたいときは、**グリッパーだけの動作**を使う: `curl -s -X POST -H "Content-Type: application/json" -d '{"arm":false,"gripper":true,"grip_period":4}' http://localhost:8080/api/dance`（心拍の値が 4。見張りは、腕と車輪の動作中（値 2 と 1）にしか止めない）。止めるのは `{"action":"stop"}` を `/api/circle` へ。
- 機体に指令を送らずに PC 側だけを試すなら `tb3ctl server --dry`（心拍は `/tb3_pc_alive_dryrun` に出る）。
- `--robot-ssh` を付けた `run_matrix.sh` が機体に触るのは、`echo_node.py` を `/tmp` に置いて動かし、止めて消すことだけ。サービスは止めない。

### 2.4 結果の残し方

各実験の結果は、`env_report.sh`（PC と機体の両方）と一緒に保存する。`bash dds/tools/env_report.sh > dds/results/<日付>_env_pc.txt`、`ssh ubuntu@<機体> 'bash -s' < dds/tools/env_report.sh > dds/results/<日付>_env_robot.txt`。ルーターの機種・周波数帯・測った場所（機体と AP の距離、壁）は、手で書き足す。

## 3. 実験

共通: ROS_DOMAIN_ID は機体と PC で同じ（既定 0）。測定は同じ条件で最低 3 回繰り返し、中央値と最大を書く。`tb3ctl ros <コマンド>` は、設定どおりの環境（ドメイン ID・PC 側のプロファイル）で動かす。

### 実験 A: 有線と無線の発見時間

- **確かめること**: 新しい PC のプロセスが、機体の `/scan` を見つけ、最初の 1 件を受け取るまでの時間。有線と Wi-Fi でどれだけ違うか。
- **仮説**: Wi-Fi のマルチキャスト発見が遅く（約 10 秒の観測あり）、有線では 1 秒未満。
- **手順**: (1) 機体を Wi-Fi だけにする（有線を抜く、または `DDS_IFACE=wlan0` で有線を切る）。`tb3ctl ros python3 dds/tools/discovery_time.py --topic /scan --runs 10 --csv dds/results/A_wifi.csv --label wifi_default`。(2) 機体を有線だけにする（`DDS_IFACE=eth0` にして `tb3ctl robot-apply`、Wi-Fi を切る）。同じ測定で `--label wired_default`。
- **道具**: `discovery_time.py`。条件の記録に `env_report.sh`。
- **読み方**: `first_msg_s` の中央値と最大。`match_s`（発行者が見えるまで）と `first_msg_s` の差が大きければ、発見は終わっているのにデータの経路がまだ、ということ。届かなかった回（`timeouts`）も数える。
- **目安**: Wi-Fi で、最初の 1 件の中央値が 3 秒以内、最大が 10 秒以内。
- **分かっていること**: Wi-Fi・PC 既定で約 10 秒（03 の 4.1）。有線での値は未測定。

### 実験 B: multicast / unicast peers / Discovery Server

- **確かめること**: 発見の方式を変えると、発見の時間が縮まるか。
- **仮説**: unicast peers（PC → 機体の IP）で縮む。参加者 ID の範囲を明示すると、ros2_control 側の約 3 秒の遅れも消える（推測）。Discovery Server は最も安定するが、サーバーが 1 点の弱点になる。
- **手順**: `bash dds/tools/run_matrix.sh --robot-ip <機体の IP> --pc-ip <PC の LAN の IP> --robot-ssh ubuntu@<機体の IP> --profiles "default multicast_only multicast_fast_announce unicast_peers" --measures "discovery stats" --runs 10 --duration 30`。`unicast_peers` は `--peer-pids`（参加者 ID の数）を変えて数通り（4・12・24）。Discovery Server は別途: 機体で `fastdds discovery -i 0 -l <機体の IP> -p 11811`（別の窓で動かしたままにする）、PC と機体のサービスのクライアントを `discovery_server` プロファイル（`render_profile.py discovery_server --server-ip <機体の IP>`）にして測る。CLI で全体を見るときは `discovery_super_client`。
- **道具**: `render_profile.py`・`run_matrix.sh`・`discovery_time.py`・`topic_stats.py`。
- **読み方**: プロファイルごとの `first_msg_s`。特に `/scan`（ld08_driver）と `/joint_states`（ros2_control_node）の差（03 の 4.1 の 5）。
- **目安**: どのトピックも、最初の 1 件が 3 秒以内。差が 1 秒以内。
- **分かっていること**: unicast peers（ポート指定なし）で `/scan` はすぐ、ros2_control 側は約 3 秒。それ以外は未検証。

### 実験 C: 共有メモリのあり・なし

- **確かめること**: 共有メモリを使わない（UDP だけ）設定が、同じ機体の中のノード同士の遅延と CPU の負荷を、どれだけ悪くするか。
- **仮説**: 遅延は増えるが、機体内の用途（ros2_control と rosbridge は別ホスト）には影響が小さい。大きいメッセージ（`/scan`）では CPU が目に見えて増える。
- **手順**: **機体の中だけで**測る。機体に `echo_node.py` `pingpong.py` `common.py` を `/tmp` に置き、機体の ROS 環境で、プロファイル `default`（共有メモリあり）→ `udp_only`（なし）→ `interface_whitelist` の順に、`echo_node` と `pingpong` を機体内で動かす（`--size 64` と `--size 65536`）。同時に `top -b -n 20 -d 1 | head`（CPU）と `/dev/shm` の使用量。
- **道具**: `pingpong.py` `echo_node.py` `render_profile.py`（機体で）。
- **読み方**: 往復時間の中央値と p99、機体の CPU 使用率。
- **目安**: 64 B の往復の p99 が、`udp_only` でも 5 ms 以内（PC 1 台のループバックでは約 2 ms だった。機体の Raspberry Pi 4 での値は未測定）。
- **分かっていること**: 未測定（機体で）。

### 実験 D: インタフェースの抜き差し

- **確かめること**: 走行・動作を止めたまま、ネットワークを変えたときの、通信の途切れの長さと、自動で戻るか。
- **仮説**: whitelist（Wi-Fi の IP だけ）にすると、有線の抜き差しで壊れない。既定では有線を切ると ros2_control 系だけが戻らない（03 の 4.1）。
- **手順**: PC で `tb3ctl ros python3 dds/tools/topic_stats.py --topic /scan --topic /joint_states --topic /odom --duration 180 --gap-threshold 0.5 --csv dds/results/D.csv --label <条件>` を動かしながら、時刻を決めて次を行う（ssh は影響を受けない側で）: (a) 60 秒目に有線を切る（`sudo ip link set eth0 down`。ssh は Wi-Fi で）、(b) 120 秒目に戻す（`ip link set eth0 up`）。次に (c) Wi-Fi を切る（`sudo ip link set wlan0 down`。ssh は有線で）と戻す。(d) AP を替える（別の SSID の Wi-Fi に `tb3ctl robot-wifi`）。それぞれ、機体のプロファイルを `DDS_IFACE=any`（既定）と `wlan0`（whitelist）で比べる。**安全のために、切る側と別の経路を使って ssh し、必ず元に戻す手順を書き出してから始める。**
- **道具**: `topic_stats.py`（`gap_max_ms` と `gap_max_at_s`）、`env_report.sh`。
- **読み方**: 操作した時刻のあとの最大の途切れと、頻度が元に戻るまでの秒。**新しく起動したプロセスで測り直す**と、既存の購読が途切れたのか、新しい発見が遅いのかを分けられる（長く動かしたプロセスの結果と、新しいプロセスの結果を両方取る）。
- **目安**: 有線を切っても、Wi-Fi 側の通信は 1 秒以内に戻る。Wi-Fi を切ったら、戻してから 10 秒以内に全トピックが戻る。
- **分かっていること**: 03 の 4.1。「走行中に切っても壊れない」ことは、まだ確認できていない。

### 実験 E: 心拍の揺れと deadman（見張りの待ち時間 0.3 秒は妥当か）

- **確かめること**: 心拍（20 Hz）の間隔の分布と、0.3 秒を超える途切れの頻度。0.3 秒が短すぎ（誤って止める）・長すぎ（止めるのが遅い）でないか。
- **仮説**: 近距離・空いた AP では 0.3 秒を超えない（16 秒間で最大 74 ms）。距離・障害物・他の通信（ビデオ会議など）・`/scan` の揺れ（0.3〜0.4 秒の途切れが出ていた）があると、超える回が出る。
- **手順**: PC でグリッパーだけの動作を始める（2.3 の `curl`）。機体で `topic_stats.py --topic /tb3_pc_alive --type std_msgs/msg/Int8 --duration 3600 --gap-threshold 0.15 --csv E.csv`（`scp dds/tools/topic_stats.py dds/tools/common.py ubuntu@<機体>:/tmp/` してから、機体の ROS 環境で）。条件を変えて繰り返す: AP との距離（1 m・5 m・壁越し）、同時に別の端末で大きい通信（動画）、`/scan` を PC でも購読。別に、**止まる速さ**: `python3 tools/record_stream2.py 34`（機体）で、PC の `tb3_server.py` を強制終了したあと腕の指令が止まるまでを測る（以前は約 0.58 秒）。
- **道具**: `topic_stats.py`（機体）、`tools/record_stream2.py`、`robot/bin/tb3_deadman.py`（`TIMEOUT_S`）。
- **読み方**: `gaps_over_threshold`（0.15 秒超）と `gap_max_ms`。**0.3 秒を超えた回数が、誤停止の回数の見込み**。
- **目安**: 1 時間で 0.3 秒超が 0 回。あれば、`TIMEOUT_S` を延ばす（止まる速さとの引き換え）か、心拍の QoS（現状は既定）を見直す（実験 G）。
- **分かっていること**: Wi-Fi・近距離・約 16 秒で、中央値 50 ms、p99 65 ms、最大 74 ms、150 ms 超 0/324。長時間・遠距離は未測定。

### 実験 F: 大きいメッセージの帯域と取りこぼし

- **確かめること**: メッセージの大きさと頻度を上げたとき、どこから取りこぼし・遅延の悪化が始まるか（Wi-Fi の実効の帯域）。
- **仮説**: 64 KB × 20 Hz（約 10 Mbit/s）は通るが、reliable で 100 Hz 以上は再送で遅延が膨らむ。
- **手順**: 機体で `echo_node.py`、PC で `pingpong.py --size {64,1024,16384,65536} --hz {10,50,100,200} --qos {reliable,best_effort} --duration 30 --csv F.csv`（組み合わせは `run_matrix.sh --size/--hz` でも、シェルのループでもよい）。同じ日に `ros2 topic bw /scan`。
- **道具**: `pingpong.py`。
- **読み方**: `loss_pct`、`rtt_p99_ms`、`reply_gap_max_ms`。往復なので、実効の帯域は上り + 下りの 2 倍。
- **目安**: 想定の用途（`/scan` 約 3 KB × 10 Hz、`/joint_states`、カメラを足すなら 100 KB 級 × 10〜30 Hz）で、取りこぼし 1% 未満。
- **分かっていること**: PC 1 台のループバックでは、64 KB × 20 Hz で 0 件の取りこぼし、往復の中央値 1.07 ms（機体なしで確認したこと）。Wi-Fi では未測定。

### 実験 G: QoS（reliable と best_effort）

- **確かめること**: reliable は、取りこぼしを再送で補う代わりに、遅延の尾（p99・最大）が長くなるか。心拍・`/cmd_vel` のような「古い値に意味がない」ものは best_effort が向くか。
- **仮説**: Wi-Fi の取りこぼしがあると、reliable の p99・最大が数倍になる。best_effort は取りこぼすが遅れない。
- **手順**: 実験 F の測定を `--qos reliable` と `--qos best_effort` で（機体の `echo_node.py` も同じ QoS で起動し直す）。Wi-Fi を弱くした条件（AP から遠ざける）でも。
- **道具**: `pingpong.py`。
- **読み方**: `rtt_p99_ms` と `rtt_max_ms` の違い、`loss_pct`、`longest_loss_run`（連続して欠けた件数 = 途切れの目安）。
- **目安**: （判断材料）心拍は、best_effort にして最大の遅れが小さくなるなら、そちらを検討する。**現状の `circle_driver` と `tb3_deadman` は既定の QoS（reliable・深さ 10）**。
- **注意**: QoS が合わないと**つながらない**（reliable の購読は best_effort の発行とつながらない）。`pingpong` は「echo_node が見つかりません」で終了コード 3 になる（機体なしで確認）。

### 実験 H: Fast DDS と CycloneDDS

- **確かめること**: 同じ測定（A・D・E・F）で、CycloneDDS のほうが、発見が速い・途切れにくいか。
- **仮説**: Cyclone のほうが発見が速く、複数インタフェースに強い（一般に言われること。この機体では未検証）。
- **手順**: 機体と PC の両方に `sudo apt install ros-humble-rmw-cyclonedds-cpp`。`render_profile.py cyclonedds/cyclone_iface_peer --iface-ip <PC の IP> --robot-ip <機体の IP> -o ... --shell` の `export`（`RMW_IMPLEMENTATION` と `CYCLONEDDS_URI`）を PC で。機体のサービスにも同じ環境変数を足して再起動（`/etc/tb3/tb3.env` に書く。足し方は 02 章。**この機体では動かしていない**）。**Fast DDS と Cyclone は互いに通信できないので、機体と PC は同じ RMW にそろえる**。`run_matrix.sh --profiles "cyclonedds/cyclone_iface_peer cyclonedds/cyclone_iface_multicast ..."`（`rmw_cyclonedds_cpp` が無いと、この行は飛ばされる）。
- **道具**: `render_profile.py`・`run_matrix.sh`。
- **読み方**: 実験 A・F と同じ表に、RMW の列を足して比べる。
- **目安**: 発見の時間の最大が Fast DDS より短い。ros2_control の制御（`/joint_states` 78 Hz）に支障がない。
- **注意**: Cyclone の `MaxAutoParticipantIndex` が小さいと、ノードの多い機体で参加者が作れない（`cyclone_iface_peer` では 100 にしてある。未検証）。

### 実験 I: ドメイン ID を分けた複数台・複数 PC

- **確かめること**: 別のドメイン ID の機体・PC が互いに見えないこと。同じドメインの PC が 2 台あるときの干渉。
- **仮説**: ドメインを分ければ混ざらない。**同じドメインに PC が 2 台いて、両方が `tb3ctl server` を動かすと、どちらも `/cmd_vel` や腕の軌道を出せてしまう**（危険）。
- **手順**: (1) 機体 A（`ROS_DOMAIN_ID=0`）と PC を、機体 B（`ROS_DOMAIN_ID=1`、`tb3ctl robot-apply`）で: `ROS_DOMAIN_ID=1 ros2 topic list --no-daemon` が機体 B だけを返す。(2) 同じドメインで PC を 2 台動かし、片方が Orbit を始めたとき、もう片方の `topic_stats.py --topic /cmd_vel` で見える（**機体を動かさない `tb3ctl server --dry` で**）。
- **道具**: `topic_stats.py`・`tb3ctl ros ros2 topic list --no-daemon`。
- **読み方**: 見えるトピックの一覧。ドメインごとのポート（7400 + 250 × ドメイン ID）。ドメイン ID が大きいと、Linux の一時ポートの範囲と重なる（101 までにするのが無難。ROS 2 の資料に基づく一般知識）。
- **目安**: ドメインを分けたとき、互いのトピックが 1 件も見えない。
- **分かっていること**: 未測定。

### 実験 J: 長時間（1 時間以上）の安定性

- **確かめること**: 1〜数時間、通信の頻度・途切れ・CPU・メモリが安定しているか。
- **仮説**: Wi-Fi の揺れ以外は安定。共有メモリを使わないので `/dev/shm` は増えない。
- **手順**: 心拍用に、グリッパーだけの動作を始める。PC で `topic_stats.py --topic /scan --topic /joint_states --topic /tb3_pc_alive --duration 7200 --gap-threshold 0.5 --csv J.csv`、機体で 10 秒ごとに `iw dev wlan0 link`（信号）・`top`（CPU）・`free -m`・`vcgencmd get_throttled`（電圧低下）を記録（`while true; do date -Is; iw dev wlan0 link | grep -E 'signal|bitrate'; vcgencmd get_throttled; sleep 10; done > /tmp/J_robot.log`）。終了後 `journalctl -u tb3-bringup -u tb3-deadman --since "-2 hours" | grep -iE "error|lost|died|warn"`。
- **道具**: `topic_stats.py`・`env_report.sh`。
- **読み方**: `gap_max_at_s` が信号の悪化の時刻と合うか。途切れの数が時間とともに増えないか。
- **目安**: 2 時間で、0.5 秒超の途切れが 0〜数回、サービスの再起動 0 回。
- **分かっていること**: 未測定。

### 進める順番（おすすめ）

自己点検 → `tb3ctl status` → A → B → D → E → F・G → C → H → I → J。**D と E は安全に関わる**ので、先に済ませる。

## 4. 分かっていること（数値つき）

[03-network-and-dds.md](03-network-and-dds.md) の 4.1〜4.4 に全部ある。要点:
- Wi-Fi・PC 既定で、新しい参加者が機体を見つけるのに約 10 秒（12 秒の窓の最後の約 2.5 秒ぶんしか届かなかった）。PC 側 unicast peers（ポート指定なし）で `/scan` はすぐ、ros2_control 側は約 3 秒（最大の間隔 約 2.86 s）。
- 走行中に有線を切ると、既定のプロファイルでは ros2_control_node のトピックが PC に届かなくなった（機体の中では 73.6 Hz で出ていた）。起動し直しで `controller_state` が 74.7 Hz で届いた。whitelist 後も、切った直後は届かなかった。
- 心拍 20 Hz（Wi-Fi）: 中央値 50 ms、p99 65 ms、最大 74 ms、150 ms 超 0/324。`/scan` は最大 260〜410 ms の揺れ。
- PC → 機体 ping（Wi-Fi）: 平均 3 ms（最大 17）〜 6 ms（最大 30）。機体 → PC の ping は 100% 失敗（DDS とは無関係）。
- 腕の指令の追従: 遅れ 0.16〜0.30 s、位置のずれ 平均 0.003〜0.018 rad。PC の強制終了から腕の指令が止まるまで約 0.58 秒（見張り 0.3 秒 + 保持 0.25 秒）。
- この PC（WSL mirrored + Tailscale）で、既定のままだと同じ PC の中の参加者同士が見つからない。LAN の IP か Tailscale の IP を 1 つに絞ると見つかる。

## 5. まだ分かっていないこと

03 の 9 に同じ。特に: 有線を切ったときの ros2_control 系の不達の原因／whitelist で防げているか／Wi-Fi の発見が遅い原因／省電力 off の効果／長時間・遠距離の心拍の揺れ／Cyclone・Discovery Server／機体側の Fast DDS のバージョン。

## 6. よくある落とし穴

1. **`ros2 topic list` は、起動の直後や `ros2 daemon` の経由では不完全**（実例あり）。`--no-daemon` をつけ、数秒待つ。測定は本キットの道具（rclpy で直接発見する）で。
2. **機体 → PC の `ping` が通らないことは、DDS の失敗ではない**（Windows のファイアウォール）。判定は `topic_stats.py`。
3. **QoS が合わないと、エラーなしでつながらない**。`pingpong` と `echo_node` は同じ `--qos` で。
4. **新しいプロセスの結果と、長く動かしたプロセスの結果は別物**（発見の時間は、起動の直後だけの話）。
5. **WSL に古い `rosbridge` が残ると 9090 が取り合いになる**。`tb3ctl stop`（`pc/scripts/kill_server.sh`）で全部止めてから。
6. **複数のインタフェースがある PC（Tailscale・VPN・Docker）は、既定のままだと同じ PC の中ですら発見に失敗することがある**（03 の 4.3）。PC 側も IP を 1 つに絞る。
7. `/joint_states` の頻度が高く見えても、値が新しくなるのは約 10 Hz（OpenCR の読み取りが 100 ms ごと）。遅延の測定には、`pingpong` のような専用のメッセージを使う。
8. 測定の「頻度」は、購読側が受け取った件数。reliable ではキューに溜まって遅れて届き、頻度だけ正常に見えることがある。**遅れ（往復時間）と間隔の最大も見る**。
9. サービス（`tb3-bringup` など）の起動中に、同じ機体で別の ROS 2 のノード（検証用の `echo_node` など）を動かすと、CPU を食って制御周期に影響する。測定の前後の `top` を残す。
10. `start_server.sh` などが動いている最中に、そのファイルを書き換えない（bash が壊れた行を読む）。

## 7. 機体なしで確認したこと（2026-10-28、この PC の WSL Go2-ROS、ROS 2 Humble、Fast DDS 2.6.11）

**機体の電源は入っておらず、機体にはつないでいない。** 同じ PC の中だけ（ドメイン ID 91）で、`dds/tools/selftest_local.sh` が **OK 44 / NG 0**。主な出力:

```
[2a] 各プロファイルが Fast DDS に読み込まれる（XMLPARSER のエラーなし）: default multicast_only multicast_fast_announce unicast_peers interface_whitelist udp_only discovery_server discovery_super_client → すべて OK
     （最初の版の multicast_only は <initialPeersList/> が空で XMLPARSER Error になり、直した）
[2b] 既定の設定（全インタフェース）→ 同じ PC の中の参加者同士が見つからなかった（interface_whitelist で 192.168.11.9 を指定すると見つかる）
pingpong  64 B @ 50 Hz  qos=reliable  profile=wl.xml  domain=91
  つながるまで 0.05 s / 送信 250 / 受信 250 / 取りこぼし 0.0 %
  往復時間 [ms]  最小 0.47  中央値 0.88  p95 1.41  p99 1.70  最大 2.30  標準偏差 0.27
pingpong  65536 B @ 20 Hz
  送信 100 / 受信 100 / 取りこぼし 0.0 %   往復時間 [ms]  中央値 1.07  p95 1.74  p99 2.10  最大 2.97
QoS 不一致（reliable の echo に best_effort の pingpong）→ 「echo_node が見つかりません」、終了コード 3（ログに RELIABILITY の非互換の警告）
discovery_time（ダミーの発行者、3 回）: 最初の 1 件までの秒 最小 0.21 / 中央値 0.22 / 最大 0.26、届かなかった回 0 / 3
topic_stats（ダミー 20 Hz、10 秒）: 200 件、20.0 Hz、間隔 中央値 50.0 ms / p99 51.4 ms / 最大 51.9 ms、150 ms 超 0 / 199
```
`run_matrix.sh --local`（既定と interface_whitelist）も動いた（既定は同じ PC の中で見つからず、`discovery.csv` に届かなかった回、`stats.csv` に 0 件、`pingpong.csv` に「つながらなかった」行が残る。interface_whitelist は全部届いた）。`run_matrix.sh --dry-run` は実行するコマンドだけを表示した。

**確認できていないもの（機体が必要、または別の準備が必要）**: 機体との往復・発見・心拍（実験 A〜G・I・J のすべての実測）、`run_matrix.sh --robot-ssh`（機体への `scp`/`ssh`）、`env_report.sh` の機体側（Wi-Fi の信号・`vcgencmd`）、`unicast_peers` の参加者 ID を明示した形の効果、Discovery Server、CycloneDDS（`rmw_cyclonedds_cpp` が WSL に入っていない。プロファイルを描いて XML として読めることだけを確認）。

## 8. 結果の書き方のひな形

実験ごとに、条件を先に書き、表で数字を並べる。1 行 = 1 条件。`env_report.sh` のファイル名を書く。

```
### 実験 A（2026-MM-DD）  機体 <名前> / PC <名前> / ルーター <機種・2.4 or 5 GHz・チャンネル> / 距離 <m>
条件の記録: dds/results/2026MMDD_env_pc.txt, 2026MMDD_env_robot.txt
| 条件（label） | RMW | プロファイル（機体 / PC） | runs | match 中央値 [s] | first_msg 中央値 [s] | 最大 [s] | 届かなかった回 |
|---|---|---|---|---|---|---|---|
| wifi_default | fastrtps | whitelist / default | 10 | | | | |
| wifi_unicast | fastrtps | whitelist / unicast_peers | 10 | | | | |

### 実験 F・G（往復）
| label | size [B] | Hz | QoS | 取りこぼし [%] | 往復 中央値 [ms] | p99 [ms] | 最大 [ms] | 返事の間隔の最大 [ms] |
|---|---|---|---|---|---|---|---|---|

### 実験 D・E・J（届き方）
| label | トピック | 頻度 [Hz] | 間隔 p99 [ms] | 間隔の最大 [ms]（購読開始からの位置 [s]） | 閾値超えの数 / 間隔の数 |
|---|---|---|---|---|---|

読み取り: <何が分かったか。推測は推測と書く>
次にやること: <>
```
