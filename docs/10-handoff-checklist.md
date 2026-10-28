# 10. 引き継ぎのチェックリスト（最初に読む）

前の担当者は 2026-10-28 に、この機体から手を離す。**機体の電源は、最後に 2026-10-26 に入れて、今は切ってある。**

## A. 今すぐ必要なこと: 機体に入れるようにする

機体の `ubuntu` ユーザーは、**パスワードでのログインを無効にしてある**。ssh できる鍵は、前の担当者の PC の `~/.ssh/id_ed25519_turtlebot`（パスフレーズなし）の公開鍵**だけ**。**公開鍵**は `robot/keys/id_ed25519_turtlebot.pub` としてこのリポジトリに入れてある（公開してよいもの。持ち主の了承済み）。**秘密鍵**は、このリポジトリに入っていない（入れてはいけない）。

| 方法 | 手順 |
|---|---|
| (a) 秘密鍵を受け取る | 前の担当者から、安全な方法（暗号化した USB、パスワード付き圧縮など。メール・チャットに貼らない）で `id_ed25519_turtlebot` を受け取り、`config/tb3.env` の `ROBOT_SSH_KEY` にそのパスを書く。受け取ったあと、自分の鍵を足して（(b)）、この鍵は機体から消すとよい |
| (b) 前の担当者が公開鍵を足す | 機体の電源を入れ、前の担当者の PC から入って、引き継ぐ人の公開鍵を足す |
| (c) SD カードを抜いて足す | [02](02-robot-provisioning.md) の「cloud-init で、後から ssh の鍵を足す」。前の担当者に頼らずにできる。機体の電源を切って、SD を抜く。Mac は、ターミナルアプリから |

(b) の足し方（前の担当者の PC で。次の人の PC で自分の鍵が入ったあとは、`python3 tb3ctl.py add-key 公開鍵.pub` でも足せる）:

```bash
ssh -i ~/.ssh/id_ed25519_turtlebot ubuntu@192.168.11.100 'echo "<引き継ぐ人の公開鍵 1 行>" >> ~/.ssh/authorized_keys'
```

## B. 今の機体のネットワーク（別の場所では、そのままでは使えない）

| 項目 | 値（この機体の今の値） |
|---|---|
| Wi-Fi | `Buffalo-G-B7A0`（2.4 GHz）**にだけ**登録。固定 IP `192.168.11.100/24`、ゲートウェイ・DNS `192.168.11.1`。パスフレーズは、ルーター（Buffalo）のもの。**リポジトリにも機体の外にも書いていない**（機体の `/etc/netplan/50-cloud-init.yaml` に、ハッシュで入っている） |
| 有線 | `eth0` は DHCP（`192.168.11.64` をもらっていた） |
| ホスト名 | `turtle-destroyer`（avahi が入っているので `turtle-destroyer.local`。PC が `.local` を引ければ） |
| 別の場所で使う | 有線でつないで ssh できる状態から、`tb3ctl robot-wifi`（[01](01-quickstart-new-pc.md)）。または、SD を抜いて `network-config` を直す。**`robot-wifi` は実機では未検証**。ルーターの DHCP の割り当て範囲の外から固定 IP を選ぶ |

## C. 保管物

| もの | どこに | 注意 |
|---|---|---|
| 機体（TB-3）、電池、充電器 | 前の担当者のところ（場所は引き継ぎのときに確認） | 電池は、最後に停止したとき 11.06 V（約 32%）。長く置くなら充電してから（電池の取り扱いは電池の説明書に従う） |
| 旧 SD カードの全体イメージ（3.0 GB の `.img.gz`、展開した約 16 GB の `.img`）と、旧ホームの tar（14 MB） | `D:\claude-chat\turtlebot3-backup\`（前の担当者の PC）。同じ `.img.gz` が MacBook の `~/` にもあった | リポジトリには入れていない。SHA256 は [02](02-robot-provisioning.md)。旧 SD の `user-data` に、パスワードのハッシュと Wi-Fi の設定が入っている。人に渡すときは扱いに注意 |
| 旧 SD カード（物理） | 前の担当者のところ（確認） | 機体に入っているのは、2026-10-25 に作り直した新しい SD |
| ウェブカメラ（eMeet C960） | 前の担当者の PC につないでいたもの | この機体の部品ではない。腕の姿勢の実測に使っただけ。リポジトリに道具は入れていない |

## D. 引き継いだら、まずやること

1. [README](../README.md) と [06-safety.md](06-safety.md) を読む。
2. 機体に入れることを確かめる。

   ```bash
   python3 tb3ctl.py init
   ```

   ```bash
   python3 tb3ctl.py robot-ssh hostname
   ```

3. 機体の今のサービス定義を、控えておく（機体のサービスは、このリポジトリの `robot/systemd/` より **1 つ前の版**で動いている。[02](02-robot-provisioning.md) の「サービス定義の版」）。

   ```bash
   python3 tb3ctl.py robot-ssh sudo tar -czf /root/tb3-services-before-robot-apply.tar.gz /etc/systemd/system/tb3-bringup.service /etc/systemd/system/tb3-deadman.service /etc/systemd/system/tb3-watchdog.service /etc/systemd/system/wifi-powersave-off.service /etc/tb3 /home/ubuntu/tb3_bringup.sh /usr/local/bin/tb3_deadman.py /usr/local/bin/tb3_watchdog.sh
   ```

4. このリポジトリの版に置き換えて、動き続けることを確かめる（**未検証**。失敗しても、手順 3 の控えから戻せる）。

   ```bash
   python3 tb3ctl.py robot-apply
   ```

5. `python3 tb3ctl.py status`、`bash tests/run_tests.sh`（PC 側）。
6. [06](06-safety.md) の「初めて動かす手順」に従って、試験用 → SLOW → アーム → Dance → Orbit。

## E. 未完了・次にやること

| 項目 | 状態 | 参照 |
|---|---|---|
| 実機での Orbit（円走行）の試験 | **未実施**（計算と通信切れの停止は、機体に送らない試験用で確認） | [06](06-safety.md) |
| 新しい HOME（折りたたみ姿勢）の実機確認 | 前の担当者が 1 回押して「まあよさげ」と確認（目視。数値の記録なし）。見直すとよい | [05](05-arm-kinematics-and-mujoco.md) |
| Dance を大きさ 0.9（既定）で実機 | 未実施（実機は 0.6 だけ） | [06](06-safety.md) |
| Wi-Fi 越しで、PC を強制終了して腕が止まるまでの時間 | 未測定（有線では 0.58 秒） | [06](06-safety.md) |
| ケーブルを物理的に抜いて、電源を入れ直す | 未実施（ケーブルをつけたままの再起動と、`ip link set eth0 down` は確認済み） | [03](03-network-and-dds.md) |
| `robot/install_robot.sh` を、まっさらな SD から通す | **未検証** | [02](02-robot-provisioning.md) |
| `tb3ctl robot-install` / `robot-apply` / `robot-wifi` | **未検証**（`--dry-run` のみ） | [01](01-quickstart-new-pc.md) |
| 車体の板の寸法の実測（前端 ±2 cm、厚み、上面の高さ、中身）、LDS-02 の寸法 | 未実施。MuJoCo の判定の精度に直結 | [05](05-arm-kinematics-and-mujoco.md) |
| 5 GHz（`Buffalo-A-B7A0`）への切り替え | 未実施（パスフレーズが要る） | [01](01-quickstart-new-pc.md) |
| ゲームパッド | 未検証（ゲームパッドが無かった） | |
| Docker（`pc/docker/`） | 未ビルド | [01](01-quickstart-new-pc.md) |
| **DDS の検証** | **次の本題**。検証キットは `dds/`、手順は [04](04-dds-verification-guide.md)、設定の知識は [03](03-network-and-dds.md) | |
| 電池が減ったときの Orbit・Dance の振る舞い | 未確認 | |
| このリポジトリのライセンス | **未設定**。持ち主が決める。公開前に [NOTICE.md](../NOTICE.md) の「要確認」を確かめる | |
| 画面の `Peace Industries` の文字・社章（別プロジェクト TRUST ME から流用）を、公開してよいか | 持ち主に確認 | [NOTICE.md](../NOTICE.md) |
| git の置き場所（リモート） | ________ | |

## F. 連絡先（空欄。引き継ぎのときに埋める）

| 役割 | 名前 | 連絡の方法 |
|---|---|---|
| 前の担当者（機体・この環境の経緯） | | |
| 機体・電池・充電器の保管場所の担当 | | |
| ルーター（Buffalo）の管理者（DHCP の範囲、Wi-Fi のパスフレーズ） | | |
| リポジトリの持ち主 | | |
