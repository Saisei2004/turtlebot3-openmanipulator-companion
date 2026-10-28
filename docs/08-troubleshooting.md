# 08. 困ったとき（症状から引く）

まず状態をまとめて見る。

```bash
python3 tb3ctl.py status
```

出るもの: PC のサーバーが動いているか（`link_ok`）、機体に ssh できるか、サービス 4 つの `active`、Wi-Fi の電波・省電力、`/etc/tb3/tb3.env`。Windows では `python tb3ctl.py ...`。機体のログは次で見る（引数は、そのまま機体で動く）。

```bash
python3 tb3ctl.py robot-ssh journalctl -u tb3-bringup -n 60 --no-pager
```

| 症状 | 確認 | 原因の候補と対処 |
|---|---|---|
| 操作画面が `Offline` / `Link Lost`（rosbridge につながらない） | PC のサーバーの端末の出力。`tb3ctl status` の PC の行 | サーバーが動いていない → `tb3ctl server`。別のプロセスが 8080 / 9090 を持っている → `tb3ctl stop` してから起動。別の PC のブラウザで開いているなら、`http://<サーバーの PC の IP>:8080/`（画面は開いたホストの 9090 に接続する。Windows ではファイアウォールの規則 [01](01-quickstart-new-pc.md)） |
| 画面は `ONLINE`、Orbit / Dance の状態欄が `Orbit サーバーに届きません` | `tb3ctl status` | `tb3_server.py` が落ちている（`http://localhost:8080/api/circle` が返らない）→ `tb3ctl stop` → `tb3ctl server` |
| サーバーの端末に `Unable to start server: [Errno 98] Address already in use` が続く | `pgrep -af rosbridge`（WSL / Linux） | 古い `rosbridge` が残っている → `tb3ctl stop`（`pc/scripts/kill_server.sh`） |
| `tb3ctl status` で「機体: ssh できない」 | 機体の電源・Wi-Fi のランプ。PC から `ping <ROBOT_HOST>`。ルーターの接続機器の一覧 | 電源が入っていない・電池切れ。Wi-Fi の設定が今のネットワークと違う（**この機体の Wi-Fi は `Buffalo-G-B7A0` にしか登録していない**）→ 有線でつなぐか、SD の cloud-init で替える（[02](02-robot-provisioning.md)）。IP が変わった（DHCP のとき）→ `config/tb3.env` の `ROBOT_HOST`。鍵が違う → `ROBOT_SSH_KEY`（[10](10-handoff-checklist.md)） |
| `ssh` が `Permission denied (publickey)` | `tb3ctl robot-ssh true` | この機体は鍵のログインだけ（パスワードは無効）。登録されている公開鍵は、前の担当者の鍵だけ → [10](10-handoff-checklist.md) の (a)(b)(c) |
| 画面は `ONLINE` だが、LiDAR も関節も来ない（`link_ok=False`） | `tb3ctl ros ros2 topic list`（`/scan` `/joint_states` が見えるか）。機体で `systemctl is-active tb3-bringup` | 機体の `tb3-bringup` が動いていない → `tb3ctl robot-ssh sudo systemctl restart tb3-bringup`。動いているのにトピックが見えない → `ROS_DOMAIN_ID` が機体と PC で違う（`config/tb3.env` と `/etc/tb3/tb3.env`）。Windows のファイアウォールが UDP を止めている（[01](01-quickstart-new-pc.md)）。マルチキャストが届かない → `DDS_MODE=unicast`。DDS の詳しい調べ方は [03](03-network-and-dds.md)・[04](04-dds-verification-guide.md) |
| トピックは見えるが、起動してから 10 秒近く待たされる / 一部のトピックだけ遅れて届く | `tb3ctl ros ros2 topic hz /joint_states` を 20 秒ほど | Wi-Fi 越しはマルチキャストの発見が遅い（約 10 秒）。`DDS_MODE=unicast` にして `tb3ctl server`（PC が機体の IP へ直接も呼びかける）。それでも ros2_control 側が約 3 秒遅れることがあった（[03](03-network-and-dds.md)） |
| 走行・アームが全く動かない（画面は `ONLINE`、LiDAR は出る） | `tb3ctl robot-ssh journalctl -u tb3-bringup -n 60 --no-pager` | `Can't control joints` / `Can't control wheels` が出ている → モーターの電源が落ちている。**電池切れ**（停止時 11.06 V、約 32% だった）→ 充電して `tb3ctl robot-ssh sudo systemctl restart tb3-bringup`（`tb3-watchdog` も自動で試す）。`There is no status packet!` が出続ける → OpenCR とつながっていない。USB・`/dev/ttyACM0`・電池と電源 |
| アームの関節の値がすべて -3.14（-π）のまま。ログに `Failed to read all control table` | `tb3ctl robot-ssh ls -l /dev/ttyACM0`、`tools/probe_opencr.py` | OpenCR のファームウェアが、アーム付き用（`turtlebot3_manipulation`）ではない → `tb3ctl robot-install opencr`（[02](02-robot-provisioning.md)） |
| 腕が動かない（画面に「動かしません: 経路の ○% 地点で …」） | 画面の下のログ | MuJoCo の判定が「当たる」「関節が限界の外」と言っている。READY か HOME から動かす。判定の仮定（板の前端など）が実物と違うなら [05](05-arm-kinematics-and-mujoco.md) |
| Dance が始まらない（`409`、「当たらない大きさの動きを作れません」） | サーバーの端末に `sim unavailable:` が出ていないか | 今の姿勢から、当たらない大きさ（0.3 まで）が作れない → READY / HOME にしてから。または、サーバーの MuJoCo が読めていない（`python3 -c "import mujoco"`。メッセージは同じになる） |
| Orbit が始まらない（`409`） | `tb3ctl status` の `link_ok` | 機体からの `/scan` か `/joint_states` が来ていない（起動してすぐ、または通信が切れている）。数秒待って、もう一度 |
| Orbit が動き出して止まる（`PAUSED · 前方 ○ m の円弧上に障害物`） | 画面のレーダー（円の予定路が出る） | 帯に 3 点以上の障害物。物をどけると 1.5 秒後に再開する。LiDAR の面にある物は何でも対象（人の足・箱） |
| 動いていたものが全部止まった（`STOPPED · link lost`） | 機体との通信が 1.5 秒以上途切れた | Wi-Fi・電源・電池を確認。**自動では再開しない**ので、直したら始め直す |
| 動きが遅れる・途切れる（Wi-Fi） | `tb3ctl status` の信号（dBm）と `tx bitrate`。機体で `iw dev wlan0 get power_save` | 省電力が入っていたら切る（`wifi-powersave-off` が active か）。電波が弱い（-60 dBm、2.4 GHz で約 70 Mbps だった）→ ルーターに近づける。5 GHz（`Buffalo-A-B7A0` が見えている）。心拍の間隔が 0.3 秒を超えると見張りが腕・車輪を止める（[06](06-safety.md)）。測り方は [04](04-dds-verification-guide.md) |
| サービスが起動しない | `tb3ctl robot-ssh systemctl status tb3-bringup --no-pager`、`journalctl -u tb3-bringup -n 60` | `ExecStartPre` の `tb3_render_dds.sh` が失敗している（`DDS_IFACE` のインタフェースに IPv4 が付かない。**90 秒待ってから失敗**し、5 秒後に再試行する）→ `ip -br addr`。Wi-Fi の設定。`DDS_IFACE=any` にすれば IP 待ちをしない（有線の抜き差しで壊れる可能性は [03](03-network-and-dds.md)） |
| `tb3ctl robot-wifi` のあと、機体が見つからない | 新しいネットワークの機器の一覧。`ssh ubuntu@<新しい IP>` | **確定（`touch /tmp/tb3_wifi_ok`）しなければ、240 秒後に元の設定に自動で戻る**。待てば元のネットワークに戻る。戻らないとき: 有線でつないで、機体で `sudo python3 ~/tb3-companion/robot/bin/tb3_set_wifi.py --restore && sudo netplan apply`。この機体では、最初に手で書き換える前の控えが `/root/50-cloud-init.yaml.bak-20261026` にある。**`robot-wifi` は実機では未検証** |
| `tb3ctl robot-install` の途中で ssh が切れた | 機体で `ps aux \| grep install_robot` | もう一度、同じコマンド（必要なフェーズだけ）。`install_robot.sh` は何度動かしてもよいように書いてある（**通しでは未検証**） |
| `tests/run_tests.sh` が `NG` | その行 | 構文なら該当ファイル。`ハードウェアのパッチが公式に当たるか` が NG ならネットワーク（`TB3_TEST_NET=0` で飛ばせる）か、公式の `814f140` が取れない |
| Windows で `wsl.exe` のエラー、`tb3ctl server` が何も出さない | `wsl -l -v` | `config/tb3.env` の `WSL_DISTRO` が、ROS 2 Humble 入りの Ubuntu 22.04 の名前（`wsl -l -q` に出るもの）と違う。`START-TB3-SERVER.cmd` の既定は `Ubuntu-22.04` |
| この環境に特有: 画面の測定値がずれる | 側面図の腕が実物と違う形 | `OFFSET`（関節の 0 位置）が、この機体のものと違う（別のアームを付けた、サーボを付け直した）→ [05](05-arm-kinematics-and-mujoco.md) の手順で測り直す |

## ログの見方（機体）

| 見たいもの | コマンド（機体で） |
|---|---|
| 制御の起動と、モーターとの通信のエラー | `journalctl -u tb3-bringup -n 100 --no-pager` |
| 見張りが動いたか | `journalctl -u tb3-deadman -n 50 --no-pager`（`armed (mask N)`、`PC heartbeat lost (mask N) -> stopping`） |
| 見張りの再起動 | `journalctl -u tb3-watchdog -n 50 --no-pager` |
| DDS のプロファイル | `cat /etc/tb3/fastdds.xml`（起動のたびに作り直される） |
| ネットワーク | `ip -br addr`、`iw dev wlan0 link`、`cat /etc/netplan/*.yaml`（パスワードのハッシュが入っているので、人に見せない） |
| OpenCR の USB | `sudo dmesg \| grep -i acm` |
