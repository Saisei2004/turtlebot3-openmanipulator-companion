# 03. ネットワークと DDS の設定の知識

この機体で、PC と ROS 2（DDS）がつながるための、ネットワークと Fast DDS の設定の知識。**数値は 2026-10-25〜28 に、この機体と、この PC（Windows 11 + WSL2）で測ったもの**。推測は「推測」、測っていないものは「未検証」と書く。
最初に無線化したときの記録は [NETWORK-first-setup.md](NETWORK-first-setup.md)。検証の進め方は [04-dds-verification-guide.md](04-dds-verification-guide.md)、道具は [`dds/README.md`](../dds/README.md)。

## 1. 構成

```
 PC（有線）                        ルーター                         機体 Raspberry Pi 4
 Windows 11 + WSL2 (mirrored)      Buffalo                          Ubuntu 22.04 / ROS 2 Humble
   eth1 192.168.11.9  ────────────  LAN ─────  Wi-Fi 2.4 GHz ch4 ───  wlan0 192.168.11.100（固定）
   eth0 100.x (Tailscale)           DHCP 範囲 .2〜.65                  eth0 192.168.11.64（DHCP。ケーブルをつなげば）
 rosbridge :9090 / 操作画面 :8080                                       tb3-bringup / tb3-deadman / tb3-watchdog
 circle_driver（心拍 20 Hz）
```
- ROS_DOMAIN_ID は 0。RMW は Fast DDS（`rmw_fastrtps_cpp`）。PC 側の Fast DDS は `ros-humble-fastrtps 2.6.11`（機体側は確認していない。同じ apt のリポジトリなので同じはず）。
- 機体 → PC の ICMP（ping）は届かない。PC → 機体は届く。DDS の UDP は双方向に通る（4 参照）。

## 2. 無線化の手順の要点

詳細は [02-robot-provisioning.md](02-robot-provisioning.md) と、リポジトリの `robot/`。コマンドは `tb3ctl` にまとめてある。

| やること | 何のため | 手段 |
|---|---|---|
| Wi-Fi を固定 IP にする | DDS の設定が IP を指すので、IP が変わらないようにする | `tb3ctl robot-wifi --ssid <SSID> --psk <パスワード> --static <IP>/24 --gateway <ゲートウェイ>`（手で書くなら netplan。`robot/netplan/`） |
| Wi-Fi の省電力を切る | 応答の遅れを減らす（**効果は測れていない**。7 参照） | `wifi-powersave-off.service`（`tb3ctl robot-apply` で入る） |
| ROS 2 が使うインタフェースを Wi-Fi だけにする | 有線の抜き差しで通信が壊れないように | `config/tb3.env` の `DDS_IFACE=wlan0` → `tb3ctl robot-apply`。起動のたびに `robot/bin/tb3_render_dds.sh` が、その時点の wlan0 の IP から `interface_whitelist` 相当のプロファイルを作る |
| PC から機体へ発見を直接呼びかける | Wi-Fi 越しのマルチキャスト発見が遅いため | `config/tb3.env` の `DDS_MODE=unicast`。`tb3ctl server` / `tb3ctl ros` が PC 側のプロファイルを作る |
| ssh の接続先を Wi-Fi にする | ケーブルなしで入る | `ROBOT_HOST` を Wi-Fi の IP（または mDNS 名）にする |

起動の順番: サービスは Wi-Fi が IP を取るまで最大 90 秒待ってから立ち上がる。**IP が付かないと Fast DDS の参加者が作れない（whitelist の IP が無い）ので、サービスは起動に失敗して再試行する**。

## 3. 固定 IP と DHCP の選び方

| | 固定 IP | DHCP（IP が変わる） |
|---|---|---|
| 良い点 | PC 側の設定（unicast の相手）と ssh が変わらない | ルーターの設定を触らなくてよい。別のネットワークに持ち込みやすい |
| 悪い点 | ルーターの DHCP 範囲と重ならない IP を選ぶ必要がある。別のネットワークでは、つなぎ直しのたびに設定し直し | 機体の IP が変わると、PC 側が古い IP を呼び続ける。固定の whitelist プロファイルは無効になる |
| この機体 | 192.168.11.100（Buffalo の既定の DHCP 範囲 .2〜.65 の外。範囲は推測。機体が .64・.65 を取っていた事実による） | `tb3_render_dds.sh` が起動のたびに現在の IP でプロファイルを作るので、機体側は DHCP でも動くはず（**未検証**）。PC 側は `ROBOT_HOST` に mDNS 名を使う（`avahi-daemon` は入っている。PC から `.local` が引けるかは、Windows では引けた。WSL では未確認） |

選ぶ目安: 1 台を決まった場所で使うなら固定。持ち運ぶ・複数の人が別のネットワークで使うなら、DHCP + mDNS 名（`ROBOT_HOST=<名前>.local`）を先に試す。どちらでも、`tb3ctl status` で機体の IP が見える。

## 4. この機体と PC で分かったこと（事象と数値）

### 4.1 有線を切ると、機体の ros2_control_node のトピックが PC に届かなくなった（2026-10-26）

| # | 条件 | 結果 | 出どころ |
|---|---|---|---|
| 1 | 機体は既定のプロファイル（全インタフェース + 共有メモリ）、Wi-Fi は DHCP。走行中に機体で `ip link set eth0 down` | PC（WSL）で `/scan` は届いた（9.75 Hz、間隔 94〜114 ms）。`/joint_states` `/odom` `/arm_controller/controller_state` は **8〜15 秒の窓で 0 件**（2 回の測定）。機体の中では `/joint_states` が **73.6 Hz** で出ていた（ノードは生きていた） | 会話の測定（`ros2 topic hz`） |
| 2 | 同じ状態で `tb3-bringup` を再起動（eth0 は down のまま） | その測定で `/arm_controller/controller_state` が **74.7 Hz**（最大の間隔 74 ms）で届いた。`/joint_states` と `/odom` は同じ測定では出力なし（発見の遅れかもしれない）。再起動で届くようにはなったが、**3 つとも直ったことは、この測定では示せていない** | 同上 |
| 3 | 機体を interface_whitelist（Wi-Fi の IP だけ）にしたあと、また走行中に eth0 を down。PC は既定 | 切った 4 秒後からの 12 秒: `/scan` 47 件（最大の間隔 410 ms）、ros2_control の 3 トピックは **0 件**。PC の常駐ドライバは `link_ok=False` になった | 同上 |
| 4 | 3 の 1〜2 分後（eth0 は down のまま）、新しいプロセスで 12 秒 | `/scan` 109 件（最大 285 ms）、`/joint_states` 192 件（最大の間隔 **2792 ms**）、`/odom` 99 件、controller_state 170 件 | 同上 |
| 5 | PC 側に `initialPeersList`（機体の IP、ポート指定なし）を入れて、新しいプロセスで 12 秒 | `/scan` 116 件（最大 264 ms）、`/joint_states` 52 件（最大の間隔 **2860 ms**）、`/odom` 25 件、controller_state 45 件 | 同上 |
| 6（基準） | 有線あり、機体は whitelist、PC は既定。12 秒 | `/scan` 115 件（間隔の中央値 101 ms、最大 121 ms）、`/joint_states` 931 件（10 ms、最大 61 ms）、`/odom` 493 件、controller_state 835 件（11 ms、最大 61 ms） | 同上 |

読み取れること（推測を含む）:
- 1: ノードが生きているのに PC に届かないので、発見かデータ経路の問題。**原因は特定していない**。推測: 起動時に有線の IP を含めて作られた送信先・ソケットが、インタフェースの消失後に使えなくなった。
- 3→4: 有線を切った直後は ros2_control 系が届かず、約 1 分後には届いた。**新しい参加者が機体を見つけるのに約 10 秒**かかった（4 で 12 秒の窓のうち、データは最後の約 2.5 秒ぶんだけ）。マルチキャストの発見が Wi-Fi で遅いことと一致するが、**切り分けていない**（AP のマルチキャスト処理、DTIM、パケットの取りこぼしなど）。
- 5: `/scan`（ld08_driver）は最初から届き、ros2_control 側は約 3 秒遅れた。推測: ポートを書かない locator は参加者 ID の小さい参加者だけを試すので、機体で後から作られる（ID の大きい）参加者の発見が遅れた。**未確認**。`dds/profiles/unicast_peers.xml.in` は参加者 ID 0〜11 のポートを明示して並べるが、効果は未検証。
- 3 で「走行中に有線を切っても壊れない」ことは**確認できていない**（既存の購読が途切れたのかを、長く見ていない）。whitelist にした目的は達していない可能性がある。実験 D で測り直す。

### 4.2 Wi-Fi だけで動かしたときの数値（有線を切った機体 + 有線の PC。2026-10-26）

| 項目 | 数値 | 出どころ |
|---|---|---|
| PC → 機体 ping（省電力 on、DHCP、Wi-Fi） | 40/40 返答、平均 3 ms、最大 17 ms | 会話の測定（Windows の `ping -n 40`） |
| PC → 機体 ping（省電力 off、固定 IP） | 60/60 返答、平均 6 ms、最大 30 ms | 同上（`ping -n 60`） |
| 機体 → PC ping | 60/60 失敗（100% loss） | 機体で `ping -c 60 -i 0.2` |
| 心拍 `/tb3_pc_alive`（PC → 機体、20 Hz、約 16 秒） | 間隔の中央値 50 ms、p99 65 ms、最大 74 ms、150 ms 超 0 / 324 | `record_stream2.py`（機体で受信） |
| 腕の軌道の渡し（0.5 秒ごと） | 間隔の中央値 517 ms、最大 580 ms | 同上 |
| 腕が指令に付いてくる遅れ・ずれ | 遅れ 0.16〜0.30 s、位置のずれ 平均 0.003〜0.018 rad、最大 0.056 rad | 同上 |
| `/scan`（LDS-02、約 10 Hz） | 間隔の最大が 260〜410 ms の揺れが時々ある | `ros2 topic hz`（複数回） |
| Wi-Fi の状態 | 2.4 GHz、チャンネル 4、-60 dBm、rx 58.5 / tx 72.2 Mbit/s、DTIM 1 | `iw dev wlan0 link` |

- **省電力 off が効いたかは分からない**。ping は on のほうが平均が小さかった（3 ms と 6 ms）が、サンプル数も時刻も違う。切ったのは一般的な知識（省電力で応答が遅れてばらつく）による。実験で測り直す。
- **deadman（心拍が 0.3 秒途切れたら止める）との関係**: 心拍の最大 74 ms には 4 倍の余裕があるが、`/scan` では 0.3〜0.4 秒の途切れが出ている。同じ程度の途切れが心拍に起きると、見張りが誤って止める。実験 E で、長く測って決める。

### 4.3 この PC（WSL）で再現した事象（2026-10-28）

機体の電源を入れずに、**同じ PC の中だけ**で測った。`dds/tools/selftest_local.sh` の `[2b]` で再現できる。

- WSL のインタフェース: `lo`（**MULTICAST フラグなし**）、`eth0` 100.x/32（Tailscale）、`eth1` 192.168.11.9/24（LAN）、`loopback0`。
- 既定のプロファイルのままだと、**同じ PC の 2 つのプロセスが互いを見つけられない**（`ros2 topic list --no-daemon` に相手のトピックが出ない）。`udp_only`（共有メモリなし）でも同じ。
- `ROS_LOCALHOST_ONLY=1` も、`interface_whitelist` に 127.0.0.1 を入れても見つからない（推測: `lo` にマルチキャストが無いため）。
- `interface_whitelist` に `192.168.11.9`（LAN）、または `100.111.108.121`（Tailscale）を 1 つ入れると、**見つかる**。
- 原因は特定していない。推測: 複数のインタフェースにマルチキャストを出したとき、受け側が join しているインタフェースと食い違う。
- 意味: PC が複数のインタフェースを持つとき（Tailscale、VPN、Hyper-V、Docker）、PC 側も IP を 1 つに絞ったほうが安定する可能性がある。機体との通信（4.1）の不安定さにも、PC 側の要因があるかもしれない（**未確認**）。

### 4.4 ネットワークの外の、制御周期に効く制約（DDS の話ではない）

OpenCR は DYNAMIXEL 通信を、**1 秒に 43〜44 回しか処理しない**（生のシリアルで測った。続けて送ると 1 回 23 ms、10 ms 空けると 12.9 ms、20 ms 空けると 2.9 ms で返るが、どれも 1 秒あたりの回数は同じ）。純正の `turtlebot3_manipulation_hardware` は 1 周期に 7 回通信して約 5 Hz で動いていた。通信を減らした版（`robot/hardware_patch/`）で、腕の指令は約 20〜30 Hz になった。**DDS の遅延を測るときは、`/joint_states` のトピックは約 78 Hz で出るが、値が新しくなるのは約 10 Hz（読み取りが 100 ms ごと）であることを忘れない**（頻度だけ見ると、DDS が速いように見える）。詳しくは [07-findings-and-gotchas.md](07-findings-and-gotchas.md)。

## 5. 発見のしくみの要点（一般知識。この機体では未検証の部分あり）

- Fast DDS の発見（SPDP）は、既定ではマルチキャスト（239.255.0.1）。ポートは RTPS の既定の式（PB=7400、DG=250、PG=2）で、ドメイン `d`・参加者 ID `p` のとき: マルチキャストのメタトラフィック 7400+250d、ユニキャストのメタトラフィック 7410+250d+2p、ユーザーデータ（ユニキャスト）7411+250d+2p。**ドメイン 0 の参加者 ID 0〜11 は 7410, 7412, … 7432**。ファイアウォールは UDP 7400〜7700 を許可している（`pc/scripts/windows/allow_wsl_ros2_firewall.ps1`）。
- 機体には参加者が多い（`ros2_control_node`、`ld08_driver`、`robot_state_publisher`、各 spawner、`tb3_deadman` など。**数は数えていない**）。参加者 ID は、同じ機体の中で 0 から順に使われる。
- `initialPeersList` に IP だけを書くと、既定のポートの、最初のいくつかの参加者 ID を試す（個数は Fast DDS のバージョンに依存。**この機体では確認していない**）。
- 共有メモリ（SHM）は、同じホストの参加者同士のデータ経路。発見の通信は UDP。`useBuiltinTransports=false` + UDP の transport だけにすると、SHM は使われない。
- Wi-Fi のマルチキャスト: AP は省電力中の端末のために、マルチキャストを DTIM のタイミングまで溜めて、低い速度（基本レート）で送ることがある（**一般知識。このルーターでは確認していない**。DTIM は 1 だった）。ルーターの「マルチキャスト → ユニキャスト変換」の設定で変わる。
- Discovery Server は、マルチキャストを使わない発見。サーバーが 1 点の弱点になる。`dds/profiles/discovery_server.xml.in`。**この機体では未検証**。

## 6. `interfaceWhiteList` の使いどころと落とし穴

使いどころ: 有線と無線が同時にあるときに、ROS 2 の通信を 1 本に決めたい。持ち運ぶ機体で、インタフェースが増減する。
落とし穴:
1. **IP が変わると参加者が作れない／つながらない**。起動時に作り直す（`tb3_render_dds.sh`）か、固定 IP にする。
2. whitelist した IP が無い状態（Wi-Fi が未接続）で起動すると、ノードが起動に失敗する。サービスに待ちと再試行がある（90 秒）。
3. `useBuiltinTransports=false` なので共有メモリを使わない。同じ機体の中のノード同士も UDP になる。CPU 負荷の増加は**測っていない**。
4. 有線だけで使う（Wi-Fi なし）とき、`DDS_IFACE=eth0` にしないと通信できない。`any` なら制限しない。
5. 動いている最中にインタフェースが消える場合の振る舞いは、4.1 のとおり**まだ分かっていない**。

## 7. ルーター・Wi-Fi

- ルーターは Buffalo。2.4 GHz の `Buffalo-G-B7A0`（チャンネル 4。隣に `Buffalo-G-65E0` がチャンネル 10）と、5 GHz の `Buffalo-A-B7A0`（チャンネル 44・100）が見えている。**機体の設定は 2.4 GHz だけ**。Raspberry Pi 4 は 5 GHz に対応するが、パスワードを持っていないので試していない。5 GHz に替えると混み合いが減るはず（**未検証**）。
- DHCP の割り当て範囲は、Buffalo の既定が .2〜.65 と思われる（推測）。ルーターの画面で確認する。
- 省電力: `iw dev wlan0 get power_save`。切る手段は `wifi-powersave-off.service`（`iw dev wlan0 set power_save off`）。**切った効果は測れていない**（4.2）。
- 別のネットワークに持ち込むとき: `tb3ctl robot-wifi`（失敗したら自動で元に戻す）。ssh できる状態（有線）で行う。

## 8. Windows / WSL 側の注意

- **WSL は mirrored ネットワーク**（`C:\Users\<名前>\.wslconfig` に `[wsl2]` / `networkingMode=mirrored`。反映には `wsl --shutdown`。**全ディストリビューションに効く**）。NAT のままだと、LAN の機体と DDS（マルチキャスト）が通らない。
- **Hyper-V ファイアウォール**: WSL の既定は外からの受信を拒否。UDP 7400〜7700 と TCP 8080・9090 を、ローカルサブネットからだけ許可する規則を作る（`pc/scripts/windows/allow_wsl_ros2_firewall.ps1`、**管理者**）。**管理者でないと `New-NetFirewallHyperVRule` が「アクセスが拒否されました」で失敗する**（最初のスクリプトは失敗しても「OK」と出していた。直してある）。ホスト側にも同じ規則（`New-NetFirewallRule`）を作る。
- 機体 → PC の ping が 100% 失敗するのは、Windows のファイアウォールが受信の ICMP echo を許可していないため（**推測。規則は確認していない**）。DDS の UDP とは別なので、**機体から PC へ ping できるかを、DDS の疎通の判定に使わない**。判定は `topic_stats.py` / `tb3ctl status`。
- WSL の mirrored では、PC の全インタフェース（Tailscale・VPN など）が見える。4.3 のとおり、複数あると同じ PC の中の発見すら失敗した。PC 側も `interface_whitelist` で LAN の IP を 1 つに絞る手がある。
- WSL を落としても、`rosbridge` が残り、9090 が取り合いになる（`Address already in use`）。`pc/scripts/kill_server.sh` で全部止めてから起動する。**`start_server.sh` が動いている最中にそのファイルを書き換えると、bash が壊れた行を読む**（実際に `XIT: command not found` が出た）。
- `ros2 daemon` は古い・不完全な発見の結果を返す（実例: サービス起動の直後に `ros2 topic list` が `/parameter_events` と `/rosout` だけを返し、`--no-daemon` で待つと全部出た）。測定では `--no-daemon`、または `ros2 daemon stop`、または本キットの道具（rclpy で直接発見する）を使う。
- mDNS（`<ホスト名>.local`）: Windows からは機体の名前が引けた。WSL からは未確認。

## 9. まだ分かっていないこと

- 4.1 の原因（有線を切ると ros2_control 系だけが届かなくなる理由）と、whitelist で防げているか。
- 新しい参加者の発見が Wi-Fi で約 10 秒かかる原因（AP のマルチキャスト処理か、参加者 ID の範囲か、取りこぼしか）。
- 省電力 off の効果。2.4 GHz と 5 GHz の違い。
- 心拍・`/scan` の途切れ（0.3〜0.4 秒）の原因と、長時間での頻度。
- CycloneDDS・Discovery Server での挙動（どちらも未実施）。
- 機体側の Fast DDS のバージョン、参加者の数。
