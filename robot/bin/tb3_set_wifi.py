#!/usr/bin/env python3
"""機体の Wi-Fi（wlan0）を、別のネットワークにつなぐ／固定 IP にする／DHCP に戻す。root で動かす。
PC からは `tb3ctl robot-wifi` が、戻す保険（自動で元に戻すタイマー）つきで呼ぶ。パスワードは表示しない。

usage:
  tb3_set_wifi.py --ssid NAME --psk PASSPHRASE [--static 192.168.0.50/24 --gateway 192.168.0.1 [--dns 192.168.0.1]]
  tb3_set_wifi.py --restore            # 元の設定（/root/50-cloud-init.yaml.tb3-backup）に戻す
SSID だけでパスフレーズが無い（--open）ときは、パスワードなしのネットワーク。--dhcp で固定 IP をやめる。

netplan の psk には、パスフレーズから計算した 64 桁の 16 進（PBKDF2-HMAC-SHA1, 4096 回, SSID を塩）を書く。平文は残さない。
"""
import argparse
import hashlib
import os
import shutil
import sys

import yaml

PATH = "/etc/netplan/50-cloud-init.yaml"
BACKUP = "/root/50-cloud-init.yaml.tb3-backup"
DISABLE_CLOUD_NET = "/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg"


def psk_hex(ssid, passphrase):
    return hashlib.pbkdf2_hmac("sha1", passphrase.encode(), ssid.encode(), 4096, 32).hex()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssid")
    ap.add_argument("--psk", help="パスフレーズ（8〜63 文字）")
    ap.add_argument("--open", action="store_true", help="パスワードなしのネットワーク")
    ap.add_argument("--static", help="固定 IP（例 192.168.0.50/24）")
    ap.add_argument("--gateway")
    ap.add_argument("--dns", help="DNS（既定はゲートウェイ）")
    ap.add_argument("--dhcp", action="store_true")
    ap.add_argument("--iface", default="wlan0")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("root で動かしてください")
    if a.restore:
        shutil.copy(BACKUP, PATH)
        print("restored", PATH)
        return
    if not a.ssid or not (a.psk or a.open):
        sys.exit("--ssid と、--psk か --open が要ります")
    if a.psk and not 8 <= len(a.psk) <= 63:
        sys.exit("パスフレーズは 8〜63 文字")
    if a.static and not a.gateway:
        sys.exit("--static には --gateway も要ります")
    if not os.path.exists(BACKUP):
        shutil.copy(PATH, BACKUP)

    d = yaml.safe_load(open(PATH))
    w = d["network"].setdefault("wifis", {}).setdefault(a.iface, {})
    ap_cfg = {} if a.open else {"password": psk_hex(a.ssid, a.psk)}
    w["access-points"] = {a.ssid: ap_cfg}          # 古い接続先は消す（1 つだけ。複数にしたいときは YAML を手で直す）
    w["optional"] = True
    w.setdefault("regulatory-domain", "JP")
    if a.static and not a.dhcp:
        w["dhcp4"] = False
        w["dhcp6"] = True
        w["addresses"] = [a.static]
        w["routes"] = [{"to": "default", "via": a.gateway, "metric": 600}]
        w["nameservers"] = {"addresses": [a.dns or a.gateway]}
    else:
        w["dhcp4"] = True
        for k in ("addresses", "routes", "nameservers"):
            w.pop(k, None)
    yaml.safe_dump(d, open(PATH, "w"), default_flow_style=False, sort_keys=True)
    os.chmod(PATH, 0o600)
    os.makedirs(os.path.dirname(DISABLE_CLOUD_NET), exist_ok=True)
    with open(DISABLE_CLOUD_NET, "w") as f:      # 再起動で cloud-init が netplan を作り直さないように
        f.write("network: {config: disabled}\n")
    print("wifi ->", {"ssid": a.ssid, "static": a.static if not a.dhcp else None, "gateway": a.gateway, "iface": a.iface})


if __name__ == "__main__":
    main()
