# 機体を無線（Wi-Fi）で使う設定（2026-10-26）

LAN ケーブルなしで、PC と機体が Wi-Fi 越しにつながる。PC は有線のまま。

## 構成
| 項目 | 内容 |
|---|---|
| 機体の Wi-Fi | `Buffalo-G-B7A0`（2.4 GHz、チャンネル 4、-60 dBm、約 70 Mbps）。固定 IP **192.168.11.100**（ルーターの DHCP 割り当て範囲 .2〜.65 の外） |
| 機体の有線 | これまでどおり DHCP（192.168.11.64）。つなげば ssh できるが、ROS 2 の通信には使わない |
| ssh | `ssh tb3`（= 192.168.11.100）。有線は `ssh tb3-wired` |
| 機体の ROS 2 (Fast DDS) | `/etc/tb3/fastdds_wifi.xml` で Wi-Fi の固定 IP だけを使う（有線の抜き差しで通信が壊れないように）。tb3-bringup / tb3-deadman のサービスと機体の `.bashrc` に設定済み |
| PC (WSL) の Fast DDS | `fastdds_pc_unicast.xml`。Wi-Fi 越しはマルチキャストの発見が遅い（新しいプロセスが機体を見つけるまで約 10 秒）ので、機体の固定 IP へ直接も呼びかける。`start_tb3_server.sh` と `wsl_run_ros.sh` が使う |
| Wi-Fi の省電力 | `wifi-powersave-off.service` で切る（入れたままだと応答が遅れてばらつく） |
| 起動順 | tb3-bringup / tb3-deadman は、Wi-Fi が固定 IP を取るまで最大 90 秒待つ |

## 測った数値（機体は有線を外した状態、PC は有線）
- PC → 機体 ping：60/60 返答、平均 6 ms、最大 30 ms（省電力オフ・固定 IP のあと）
- 心拍（PC → 機体、20 Hz）：間隔の中央値 50 ms、99% が 65 ms 以下、最大 74 ms、150 ms を超えたもの 0 / 324
- 腕の追従は有線のときと同じ（遅れ約 0.2 s、位置のずれ 平均 0.003〜0.018 rad）
- /scan は約 10 Hz（間隔の最大 260〜410 ms の揺れが時々ある）

## 元に戻すには（機体で）
```bash
sudo cp /root/50-cloud-init.yaml.bak-20261026 /etc/netplan/50-cloud-init.yaml && sudo netplan apply   # Wi-Fi を DHCP に戻す
sudo systemctl disable --now wifi-powersave-off
sudo sed -i '/FASTRTPS_DEFAULT_PROFILES_FILE/d; /ExecStartPre=.*wlan0/d' /etc/systemd/system/tb3-bringup.service /etc/systemd/system/tb3-deadman.service
sudo systemctl daemon-reload && sudo systemctl restart tb3-bringup tb3-deadman
```

## 注意
- Wi-Fi の IP を変えるときは、`/etc/tb3/fastdds_wifi.xml` と PC の `fastdds_pc_unicast.xml`、`~/.ssh/config` の IP も合わせる。
- 5 GHz の `Buffalo-A-B7A0` も見えている（今より混み合いにくい）。つなぐには、そのパスワードを `/etc/netplan/50-cloud-init.yaml` に足す必要がある（今の設定にあるのは 2.4 GHz 側のものだけ）。
