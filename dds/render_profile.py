#!/usr/bin/env python3
"""DDS プロファイルのひな形（profiles/*.xml.in）に IP などを入れて XML を書き出す。

使い方:
  python3 render_profile.py --list
  python3 render_profile.py interface_whitelist --iface-ip 192.168.11.100 -o /tmp/fastdds_wifi.xml
  python3 render_profile.py unicast_peers --robot-ip 192.168.11.100 --domain-id 0 --peer-pids 12 -o /tmp/fastdds_pc.xml
  python3 render_profile.py discovery_server --server-ip 192.168.11.100 -o /tmp/ds.xml
  python3 render_profile.py cyclonedds/cyclone_iface_peer --iface-ip 192.168.11.9 --robot-ip 192.168.11.100 -o /tmp/cyclone.xml

  # 使うのに必要な export をシェルへ（eval で取り込める）
  eval "$(python3 render_profile.py interface_whitelist --iface-ip 192.168.11.100 -o /tmp/p.xml --shell)"

プレースホルダー:
  @ROBOT_IP@ 相手（機体）の IP / @PC_IP@ PC の IP / @IFACE_IP@ 使うインタフェースの IP
  @SERVER_IP@ @SERVER_PORT@ @SERVER_ID@ @SERVER_PREFIX@ Discovery Server / @PEER_LOCATORS@ 参加者 ID ごとのユニキャスト locator（自動生成）
ひな形の先頭コメントにある `tb3-meta:` の行（rmw / requires / env / env_uri）を読んで、必要な引数の確認と export の出力をする。
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILES = HERE / "profiles"


def names():
    return sorted(str(p.relative_to(PROFILES))[: -len(".xml.in")].replace("\\", "/") for p in PROFILES.rglob("*.xml.in"))


def meta(text):
    m = {}
    for line in re.findall(r"tb3-meta:\s*(.*)", text):
        k, _, v = line.partition("=")
        m[k.strip()] = v.strip()
    return m


def first_comment_title(text):
    m = re.search(r"<!--\s*\n\s*(.*?)\n", text)
    return m.group(1).strip() if m else ""


def peer_locators(ip, domain, pids, indent="          "):
    """既定のメタトラフィック・ユニキャストのポート: 7400 + 250 * domain + 10 + 2 * 参加者ID"""
    out = []
    for pid in range(pids):
        port = 7400 + 250 * domain + 10 + 2 * pid
        out.append(f"{indent}<locator><udpv4><address>{ip}</address><port>{port}</port></udpv4></locator>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?", help="プロファイル名（--list で一覧）。cyclonedds/ 以下は cyclonedds/名前")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--robot-ip")
    ap.add_argument("--pc-ip")
    ap.add_argument("--iface-ip")
    ap.add_argument("--domain-id", type=int, default=0, help="ROS_DOMAIN_ID（ポートの計算に使う）")
    ap.add_argument("--peer-pids", type=int, default=12, help="unicast_peers で、ポートを明示する参加者 ID の数")
    ap.add_argument("--server-ip")
    ap.add_argument("--server-port", type=int, default=11811)
    ap.add_argument("--server-id", type=int, default=0)
    ap.add_argument("-o", "--out", help="書き出す先（省略すると標準出力）")
    ap.add_argument("--shell", action="store_true", help="使うのに必要な export 行を標準出力に出す（XML は -o へ）")
    a = ap.parse_args()

    if a.list:
        for n in names():
            t = (PROFILES / (n + ".xml.in")).read_text(encoding="utf-8")
            print(f"{n:34s} {first_comment_title(t)}")
        return 0
    if not a.name or a.name not in names():
        print("プロファイル名を指定してください（--list で一覧）", file=sys.stderr)
        return 2
    text = (PROFILES / (a.name + ".xml.in")).read_text(encoding="utf-8")
    md = meta(text)

    server_ip = a.server_ip or a.robot_ip
    values = {
        "ROBOT_IP": a.robot_ip, "PC_IP": a.pc_ip, "IFACE_IP": a.iface_ip, "SERVER_IP": server_ip,
        "SERVER_PORT": str(a.server_port), "SERVER_ID": str(a.server_id),
        "SERVER_PREFIX": "44.53.%02x.5f.45.50.52.4f.53.49.4d.41" % a.server_id,
    }
    need = [x for x in md.get("requires", "").split(",") if x]
    miss = [x for x in need if not values.get(x)]
    if miss:
        flags = {"ROBOT_IP": "--robot-ip", "PC_IP": "--pc-ip", "IFACE_IP": "--iface-ip", "SERVER_IP": "--server-ip（または --robot-ip）"}
        print("次の指定が足りません: " + ", ".join(flags.get(x, x) for x in miss), file=sys.stderr)
        return 2
    if "@PEER_LOCATORS@" in text:
        text = text.replace("@PEER_LOCATORS@", peer_locators(a.robot_ip, a.domain_id, a.peer_pids))
    for k, v in values.items():
        if v is not None:
            text = text.replace(f"@{k}@", v)
    left = sorted(set(re.findall(r"@[A-Z_]+@", re.sub(r"<!--.*?-->", "", text, flags=re.S))))
    if left:
        print("置き換えられていないプレースホルダーがあります（コメント以外）: " + ", ".join(left), file=sys.stderr)
        return 2

    if a.out:
        Path(a.out).write_text(text, encoding="utf-8", newline="\n")
    elif not a.shell:
        sys.stdout.write(text)
    if a.shell:
        if not a.out:
            print("--shell には -o（XML の書き出し先）が要ります", file=sys.stderr)
            return 2
        out = Path(a.out).resolve()
        rmw = md.get("rmw", "rmw_fastrtps_cpp")
        print(f"export RMW_IMPLEMENTATION={rmw}")
        if rmw == "rmw_cyclonedds_cpp":
            print(f"export CYCLONEDDS_URI=file://{out}")
            print("unset FASTRTPS_DEFAULT_PROFILES_FILE")
        else:
            if a.name == "default":
                print("unset FASTRTPS_DEFAULT_PROFILES_FILE")
            else:
                print(f"export FASTRTPS_DEFAULT_PROFILES_FILE={out}")
            print("unset CYCLONEDDS_URI")
        env = md.get("env")
        if env:
            for k, v in values.items():
                env = env.replace(f"@{k}@", v or "")
            print(f"export {env}")
        else:
            print("unset ROS_DISCOVERY_SERVER")
    return 0


if __name__ == "__main__":
    sys.exit(main())
