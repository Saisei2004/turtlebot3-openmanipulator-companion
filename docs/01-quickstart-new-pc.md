# 01. 別の PC・別のネットワークで動かす

前提: 機体は動く状態（機体側の導入済み。新品の SD から作るときは [02](02-robot-provisioning.md)）。機体の ssh に入れること（[10](10-handoff-checklist.md) の最初の項目）。

## 1. 構成を選ぶ

| 構成 | 状態 |
|---|---|
| Windows 11 + WSL2（Ubuntu 22.04）+ mirrored ネットワーク | この構成で、すべて確認した（PC 側の `tb3ctl server` `stop` `status` `ros`、機体との通信） |
| Ubuntu 22.04 を直接入れた PC | 手順は `setup_pc.sh` と同じ。**この構成そのものは試していない**（WSL2 の Ubuntu 22.04 で `setup_pc.sh` 相当を使った） |
| Docker（`pc/docker/`、Linux のホストだけ） | **未ビルド**。Windows / macOS の Docker Desktop では DDS が機体に届かない（推測。確かめていない） |
| macOS | 対象外（ROS 2 Humble を入れる手順を用意していない） |

`tb3ctl` 自体は Python 3 と `ssh` / `scp` / `tar` があれば動く。Windows では PowerShell / cmd から `python tb3ctl.py ...`（または `tb3ctl.cmd ...`）と動かすと、PC 側のスクリプトは `wsl.exe` 経由で WSL の中で動く（**この環境で確かめたのはこのやり方**。ssh の鍵は Windows 側のもの）。WSL の中から `python3 tb3ctl.py ...` と動かしてもよいが、そちらは試していない。以降の `python3 tb3ctl.py` は、Windows では `python tb3ctl.py` に読み替える。

## 2. Windows の準備（WSL2）

1. WSL2 と Ubuntu 22.04 を入れる

   ```powershell
   wsl --install -d Ubuntu-22.04
   ```

2. WSL を LAN に直接つなぐ（mirrored）。`%UserProfile%\.wslconfig` に次を書く

   ```ini
   [wsl2]
   networkingMode=mirrored
   ```

3. WSL を落として、反映する

   ```powershell
   wsl --shutdown
   ```

4. 管理者の PowerShell で、LAN からの ROS 2（DDS）と操作画面への受信を通す。**これが無いと機体が PC に届かない**（Hyper-V ファイアウォールが WSL への外からの受信を既定で全部止める）。許すのは「ローカルサブネットから」だけ

   ```powershell
   .\pc\scripts\windows\allow_wsl_ros2_firewall.ps1
   ```

   `ROS_DOMAIN_ID` を 0 以外にしたときは `-DomainId <ID>`、規則を消すときは `-Remove`。

5. 以降の `setup_pc.sh` は WSL の中で動かす。リポジトリは Windows 側（例 `D:\...\tb3-companion`）に置いたまま、WSL からは `/mnt/d/...` で見える（`tb3ctl` が `wsl.exe --cd` で正しく開く）。

## 3. PC に必要なものを入れる（Ubuntu 22.04 / WSL の中）

```bash
bash pc/scripts/setup_pc.sh
```

ROS 2 Humble（ros-base）、rosbridge、teleop、control_msgs、`rmw_cyclonedds_cpp`、numpy、MuJoCo を入れる。Ubuntu 22.04 以外では止まる。何度動かしてもよい。

## 4. 設定ファイルを作る

```bash
python3 tb3ctl.py init
```

質問に答える（機体の IP か名前、ユーザー名、ssh 鍵、`ROS_DOMAIN_ID`、`DDS_MODE`、`DDS_IFACE`、Windows なら `WSL_DISTRO`）。`config/tb3.env` ができる（git に入らない）。Windows で WSL のディストリビューション名は `wsl -l -q` で分かる。質問なしで作るときは `tb3ctl init --yes --robot-host <IP> --wsl-distro <名前>`。

| キー | 迷ったとき |
|---|---|
| `ROS_DOMAIN_ID` | 機体と PC で必ず同じ。同じネットワークで複数台・複数人が動かすときは分ける（0〜101）。**機体側は `tb3ctl robot-apply` で変える** |
| `DDS_MODE` | Wi-Fi 越しは `unicast`（PC が機体の IP へ直接も発見を呼びかける。マルチキャストだけだと、新しく起動したプロセスが機体を見つけるまで約 10 秒かかった）。有線で同じスイッチ上なら `multicast` でもよい |
| `DDS_IFACE` | 機体の ROS 2 が使うインタフェース。`wlan0`（有線の抜き差しで壊れない）/ `eth0` / `any`（制限しない）。詳細は [03](03-network-and-dds.md) |

## 5. サーバーを起動する

```bash
python3 tb3ctl.py server
```

ブラウザで `http://localhost:8080/`。止めるときは Ctrl-C か、別の窓で次を動かす。

```bash
python3 tb3ctl.py stop
```

機体に指令を送らない試験用の起動は `tb3ctl server --dry`（円走行・アームの指令を、別名のトピックに出す。[00](00-overview.md)）。

## 6. 機体を別のネットワーク（別の Wi-Fi）につなぐ

機体の ssh に入れる状態（有線でつなぐか、今の Wi-Fi 上で）から、PC で次を動かす。`--static` を付けると固定 IP、付けないと DHCP。

```bash
python3 tb3ctl.py robot-wifi --ssid <SSID> --psk <パスフレーズ> --static 192.168.0.50/24 --gateway 192.168.0.1
```

動き（コードのとおり。**実機では動かしていない**）:

1. 機体の `/etc/netplan/50-cloud-init.yaml` を書き換える（元を `/root/50-cloud-init.yaml.tb3-backup` に控える。パスフレーズは 64 桁の 16 進に変換して書き、平文は残さない）。
2. 240 秒後に、確定の印（`/tmp/tb3_wifi_ok`）がなければ、元の設定に戻すタイマーを先に仕掛ける。
3. `netplan apply`。機体への ssh は一度切れる。
4. PC を新しいネットワークにつなぎ、機体が見えたら、表示されるコマンドで確定する。

   ```bash
   ssh ubuntu@<新しい IP> 'touch /tmp/tb3_wifi_ok'
   ```

5. `config/tb3.env` の `ROBOT_HOST` を新しい IP にして、機体の DDS 設定を作り直す。

   ```bash
   python3 tb3ctl.py robot-apply
   ```

固定 IP と DHCP:

| | 固定 IP | DHCP |
|---|---|---|
| 向き | PC 側の設定（`ROBOT_HOST`）を変えなくてよい | 設定が楽 |
| 注意 | ルーターの DHCP の割り当て範囲の**外**から選ぶ。この機体の例: Buffalo のルーターは .2〜.65 を配っていて、機体が .64 / .65 をもらったので、範囲の外の .100 を選び、PC から ping（返事なし）と `arp -a`（載っていない）で使われていないことを確かめた | 機体の IP が変わると `ROBOT_HOST` が合わなくなる。名前（mDNS: `<ホスト名>.local`）で引けるかは、**WSL からは未確認** |
| 機体の DDS | どちらも、起動のたびに `tb3_render_dds.sh` が、そのときの IP で `/etc/tb3/fastdds.xml` を作る。IP が付くまで最大 90 秒待つ | 同じ |

ルーターの割り当て範囲は、ルーターの設定画面で確かめる。

5 GHz: この場所では 5 GHz の `Buffalo-A-B7A0` も見えている（今の 2.4 GHz より混み合いにくい）。つなぐには、その SSID のパスフレーズを `robot-wifi` で渡す。**試していない**。

## 7. つながったかを確かめる

```bash
python3 tb3ctl.py status
```

PC のサーバー（`link_ok`）と、機体（サービス 4 つの `active`、Wi-Fi の電波、`/etc/tb3/tb3.env`）が出る。機体が電源オフ・圏外だと「ssh できない」。

| 確かめること | どう見えれば OK |
|---|---|
| 操作画面の左上のランプ | `ONLINE`（`Offline` / `Link Lost` は rosbridge につながっていない） |
| `tb3ctl status` の PC サーバーの行 | `link_ok=True`（機体からの `/scan` と `/joint_states` が来ている） |
| ROS 2 のトピック | 次で `/scan` `/joint_states` `/odom` などが見える |

```bash
python3 tb3ctl.py ros ros2 topic list
```

`tb3ctl ros` は、設定のドメイン ID と DDS のプロファイルをそろえて、そのコマンドを動かす（WSL の中で `--exec` 経由）。

見えないとき・遅いときは [08](08-troubleshooting.md)、DDS のしくみは [03](03-network-and-dds.md)。

## 8. 初めて機体を動かす前に

[06-safety.md](06-safety.md) の「初めて動かす手順」を、**必ず**読む。周りの空き、充電ケーブル、STOP の位置、SLOW から。
