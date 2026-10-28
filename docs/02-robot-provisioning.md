# 02. 機体を作る（まっさらな SD カードから）と、この機体の今の状態

> **未検証**: `robot/install_robot.sh` を、まっさらな SD カードから最後まで通したことはない。同じコマンドを 2026-10-25〜26 に 1 つずつ実機で動かして確かめ、それをまとめたのがこのスクリプト。`tb3ctl robot-install` / `robot-apply` も実機では動かしていない（`--dry-run` で、組み立てるコマンドを見ただけ）。初めて通すときは、フェーズごとに分けて動かし、各フェーズの終わりに確認すること。

## ハードウェア（この機体）

| 部品 | 内容（会話で確認したことだけ） |
|---|---|
| 計算機 | Raspberry Pi 4 Model B Rev 1.5、メモリ 4 GB（`free` で 3.7 GiB） |
| 制御基板 | OpenCR（USB `0483:5740`、`/dev/ttyACM0`。書き込みツールの表示は `Board Name: OpenCR R1.0`）。ファームウェアは `turtlebot3_manipulation` V230127R1 を書き込み済み |
| LiDAR | LDS-02（USB-シリアル変換 CP210x `10c4:ea60`、`/dev/ttyUSB0`）。ドライバは `ld08_driver`。LDS-01 用のドライバ（`hlds_laser_publisher`）では距離が出なかった |
| アーム | OpenManipulator-X（関節 4 つ + グリッパー） |
| 車輪 | Dynamixel の車輪 2 つ（型番は確認していない） |
| 車体 | Burger を 3D プリントで Waffle サイズの 2 段に作り変えたもの。写真では、前が灰色の板（LiDAR が載る）、後ろが白い板（アームの土台が載る） |
| 電池 | 電池切れで止まった直後に OpenCR から読んだ電圧が 11.06 V（約 32%）。電池の型番・セル数は確認していない |

## 新しい SD カードから作る手順

### 1. OS を書き込む

- OS: Ubuntu Server 22.04.5 LTS (64-bit)、Raspberry Pi 用。ファイル名 `ubuntu-22.04.5-preinstalled-server-arm64+raspi.img.xz`（1,038,926,560 バイト）、入手先 `https://cdimage.ubuntu.com/ubuntu/releases/jammy/release/`、SHA256 `fd7687c5c9422a6c7ba4717c227bf6473fe4e0c954d5a9f664201dcecc63e822`（2026-10-25 に確認）。
- Raspberry Pi Imager で書くとき、設定（歯車）に次を入れる。この機体の旧 SD も Imager で作られていた（`user-data` に `rpi-imager` の印）。

| 設定 | この機体の値（例。変えてよい） |
|---|---|
| ホスト名 | `turtle-destroyer`（mDNS で `turtle-destroyer.local`。cloud-init が `avahi-daemon` を入れる） |
| ユーザー | `ubuntu` |
| ssh | 有効、**公開鍵のみ**（パスワードログインは無効にした）。公開鍵は引き継ぐ人のものを入れる |
| Wi-Fi | SSID とパスフレーズ、国 `JP` |
| タイムゾーン・キーボード | `Asia/Tokyo`、`jp` |

- `tb3ctl robot-install` は機体で `sudo` を何度も使う。この機体は `sudo` をパスワードなしにしてある（`NOPASSWD:ALL`）。Imager で作ったユーザーはパスワードが要るので、`ssh -t` でつないだ画面でパスワードを聞かれたら入れる。

### 2. 初回起動と ssh

- SD を挿して電源を入れる。cloud-init の初期設定が終わるまで数分かかる（Wi-Fi が付くのはそのあと）。
- IP は、ルーターの一覧、または `ping turtle-destroyer.local`（PC が `.local` を引ければ）で調べる。

```bash
ssh ubuntu@<機体の IP>
```

### 3. 設定ファイルを作って、機体に入れる

```bash
python3 tb3ctl.py init
```

```bash
python3 tb3ctl.py robot-install
```

`robot-install` は、`robot/` を機体の `~/tb3-companion/robot/` に転送し、設定を `robot.env` に書いて、`install_robot.sh` を `ssh -t` で動かす。フェーズ（個別に `tb3ctl robot-install ros` のように指定できる。何も指定しないと `all` = `base ros ws files`）:

| フェーズ | 内容 | 前回の実測（同等の作業。**およその時間**） |
|---|---|---|
| `base` | 自動更新・スリープを止める、`iw` などを入れる | 数分 |
| `ros` | ROS 2 Humble（ros-base）、TurtleBot3 + OpenManipulator-X の apt パッケージ（`ros-humble-turtlebot3-manipulation`、`turtlebot3`、cartographer、navigation2 など） | ROS の導入が約 40 分（ワークスペースのビルドを含む）、manipulation の apt が約 20 分 |
| `ws` | `ld08_driver` を clone、公式 `turtlebot3_manipulation_hardware` に通信を減らすパッチを当て、`~/turtlebot3_ws` で `colcon build`（[hardware_patch/apply.sh](../robot/hardware_patch/apply.sh)） | パッチ入りのプラグインのビルドは約 25 秒（機体で） |
| `files` | `/etc/tb3/tb3.env`、`/usr/local/bin/` のスクリプト、サービス 4 つ、udev、`~/.bashrc`。サービスを起動する | 数十秒 |
| `opencr` | OpenCR のファームウェアを書き込む（`all` には含まれない） | 書き込みは 2〜3 秒 |

途中で ssh が切れたら、同じコマンドを（必要なフェーズだけ）もう一度動かす。

### 4. OpenCR のファームウェア

OpenCR に、アーム付き用（`turtlebot3_manipulation`）のファームウェアが入っていないと、ROS 側の制御は起動しても値が読めない。2026-10-25 の症状: OpenCR に問い合わせて返事はあるが、読み出した値が食い違い、全関節の角度がすべて -π のまま、制御テーブルを 12 バイト読んでも 2 バイトしか返らなかった。書き込んだら直った。

```bash
python3 tb3ctl.py robot-install opencr
```

中身は `robot/bin/tb3_flash_opencr.sh`: `tb3-bringup` を止め、`libc6:armhf`（書き込みツールが 32 ビット ARM のため）を入れ、`opencr_update.tar.bz2`（約 360 KB、ROBOTIS の `OpenCR-Binaries`）を取って、`./update.sh /dev/ttyACM0 turtlebot3_manipulation.opencr`、最後に起動し直す。書き込み中は OpenCR がリセットされ、モーターの電源が一瞬切れる。2026-10-25 の実機での出力は `V230127R1`、CRC 一致、`jump_to_fw`。

### 5. 確認

```bash
python3 tb3ctl.py status
```

`tb3-bringup` / `tb3-deadman` / `tb3-watchdog` / `wifi-powersave-off` がすべて `active`。そのあと `tb3ctl server` で操作画面を開き、ランプが `ONLINE` になり、LiDAR が出ることを確かめる。腕や車輪を動かす前に [06-safety.md](06-safety.md)。

## この機体の今の状態（2026-10-28 時点。電源は切ってある。最後に電源を入れたのは 2026-10-26）

| 項目 | 内容 |
|---|---|
| OS | Ubuntu 22.04.5（Raspberry Pi 用、kernel `5.15.0-1061-raspi`）。2026-10-25 に、新しい SD として書き直した（旧 SD の内容は下のバックアップ） |
| ホスト名・ユーザー | `turtle-destroyer` / `ubuntu`。パスワードログインは無効。ssh できる鍵は、前の担当者の PC の `~/.ssh/id_ed25519_turtlebot` の公開鍵だけ（[10](10-handoff-checklist.md)） |
| ネットワーク | Wi-Fi `Buffalo-G-B7A0` に**だけ**登録。固定 IP `192.168.11.100/24`（ゲートウェイ・DNS `192.168.11.1`）。有線 `eth0` は DHCP（`192.168.11.64` をもらっていた）。`/etc/netplan/50-cloud-init.yaml` を書き換え済みで、cloud-init のネットワーク設定は無効（`/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg`）。書き換え前の控えは `/root/50-cloud-init.yaml.bak-20261026` |
| ROS | ROS 2 Humble。`~/turtlebot3_ws` には `turtlebot3` / `ld08_driver` / `coin_d4_driver` のソースビルドと、パッチ入りの `turtlebot3_manipulation_hardware`（overlay）。`robot/install_robot.sh` が作るのは `ld08_driver` とパッチ入りプラグインだけで、今の機体より小さい（差は**未検証**） |
| OpenCR | `turtlebot3_manipulation` V230127R1 を書き込み済み。`~/opencr_update/` に書き込みツール |
| サービス | `tb3-bringup`、`tb3-deadman`、`tb3-watchdog`、`wifi-powersave-off` がすべて有効（電源を入れると自動で起動する。再起動で確認済み） |
| サービス定義の版 | **機体に入っているのは、このリポジトリの `robot/systemd/` より 1 つ前の版**: Wi-Fi の固定 IP `192.168.11.100` 決め打ちで待つ、Fast DDS のプロファイルは `/etc/tb3/fastdds_wifi.xml`（IP 固定）、`ExecStart` は `/home/ubuntu/tb3_bringup.sh`、環境は `tb3.env` ではなくサービスに直接書いてある。**`tb3ctl robot-apply` で、このリポジトリの版（起動のたびに IP から DDS 設定を作る）に置き換わる。実機では未検証** |
| 腕のサーボ | プロファイルの加速 25、速度 300（既定は 100 / 500） |
| 設定 | `ROS_DOMAIN_ID=0`、`TURTLEBOT3_MODEL=waffle_pi`、`LDS_MODEL=LDS-02`（サービスのスクリプトと `~/.bashrc` に書いてある） |
| ほかに機体の上にあるもの | `~/tb3_setup.sh` `~/tb3_manip.sh`（導入のときに動かした元のスクリプト）、旧 SD から戻した `~/tb3_arm/` `~/tb3_home.sh` `~/tb3_start_with_home.sh` `~/.tb3_home.json`（旧構成のアームのスクリプトと旧 home。**旧 home は今の関節の 0 位置では自己衝突する**。使わない。[05](05-arm-kinematics-and-mujoco.md)）、`~/record_*.py` などの測定スクリプト、`~/old-home-ubuntu-20261025.tar.gz` |

## バックアップ（旧 SD の保存。リポジトリの外）

| もの | 場所 | 内容 |
|---|---|---|
| 旧 SD カードの全体イメージ | `D:\claude-chat\turtlebot3-backup\turtle-destroyer-sd-20261025.img.gz`（3,041,712,540 バイト）。同じものが MacBook の `~/` にもあった | SD 16 GB（15,962,472,448 バイト）を丸ごと `dd` して gzip したもの。SHA256 `7d403e0bdb75e00950405531b835ab2cacc4cf3ef1acf65f836374b84adf053f`（Mac と D: の両方で一致を確認） |
| 同じ、展開したもの | `D:\claude-chat\turtlebot3-backup\turtle-destroyer-sd-20261025.img`（約 16 GB） | WSL で `losetup` + `mount -o ro,noload` して中身を読める |
| 旧ホームの tar | `D:\claude-chat\turtlebot3-backup\old-home-ubuntu-20261025.tar.gz`（約 14 MB） | `/home/ubuntu`（`.cursor-server` と `.cache` を除く）。`tb3_arm/`、`opencr_update/`、`.tb3_home.json` など |

旧 SD の構成: Ubuntu 22.04（2026-04 に Imager で作成）、ROS 2 Humble（desktop）、`ros-humble-turtlebot3-manipulation` 一式、`ROS_DOMAIN_ID` 未設定（= 0）、`TURTLEBOT3_MODEL=waffle_pi`。旧 SD のネットワーク設定の Wi-Fi は `Buffalo-G-B7A0`。旧 SD の `user-data` にはパスワードのハッシュと `ssh_pwauth: true` があった（今の SD は無効）。バックアップの中の Wi-Fi 設定・パスワードのハッシュは、リポジトリには入れていない。

## cloud-init で、後から ssh の鍵を足す（SD を抜いて）

機体に入れる鍵が無いとき（[10](10-handoff-checklist.md) の (c)）。2026-10-25 に、この方法で鍵を入れた。

1. 機体の電源を切り、SD を抜いて、PC か Mac に挿す。FAT の起動領域（ラベル `system-boot`）が見える。
2. `user-data` の `users:` の `ubuntu` に、`ssh_authorized_keys:` の行を足す（鍵が既にあれば、その下に 1 行足す）。

   ```yaml
   users:
   - name: ubuntu
     ssh_authorized_keys:
     - ssh-ed25519 AAAA...（引き継ぐ人の公開鍵）
   ```

3. cloud-init に「新しい機体だ」と思わせて、もう一度読ませる。`meta-data` の `instance-id` と、`cmdline.txt` の最後の `ds=nocloud;i=<ID>` の `<ID>` を、**同じ新しい値**に替える（例 `i=tb3-key2`）。値が前と同じだと読み直されない。
4. SD を機体に戻して電源を入れる。数分後に鍵で入れる。

メモ（2026-10-25）:
- **Mac では、SD の起動領域は、ssh 越しだと `Operation not permitted` で読めなかった**（macOS のリムーバブルボリュームの保護）。Mac のターミナルアプリで、本人が動かす必要があった。
- Windows の内蔵・USB のカードリーダーでは、この PC は SD を認識しなかった（Mac の外付けリーダーでは認識）。
- 最初に入れた `id_ed25519` の鍵は、パスフレーズが分からず（ssh-agent もこの環境に無く）使えなかった。そのため、パスフレーズなしの専用鍵（`id_ed25519_turtlebot`）を作って入れ直した。
