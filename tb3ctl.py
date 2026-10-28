#!/usr/bin/env python3
"""tb3ctl: tb3-companion の操作コマンド。PC（Windows / Linux / macOS の ssh が使える環境）から、機体と PC 側サーバーを操作する。

  tb3ctl init                  設定ファイル config/tb3.env を対話で作る（機体の IP・ドメイン ID など）
  tb3ctl robot-install [フェーズ]   機体に全部入れる（まっさらな Ubuntu 22.04 から。1〜2 時間）。フェーズ: base ros ws files opencr
  tb3ctl robot-apply           機体の設定とサービスだけ入れ直して再起動する（数十秒）
  tb3ctl install-key 秘密鍵    前の担当者から受け取った秘密鍵を ~/.ssh に置き、config に書く（機体に ssh で入れるのは、この鍵だけ）
  tb3ctl robot-wifi --ssid S --psk P [--set-host] [--static IP/24 --gateway GW]
                               機体を別の Wi-Fi につなぐ。有線で ssh できる状態で動かす。PC から届くことを確かめてから確定し、
                               確定できなければ自動で元の Wi-Fi に戻る。そのあと有線を外してよい
  tb3ctl add-key 公開鍵.pub    機体に入れる ssh の公開鍵を足す（もう入れる鍵がある状態で）
  tb3ctl robot-ssh [コマンド]  機体に ssh する
  tb3ctl server [--dry]        PC 側のサーバー（操作画面 + rosbridge + ドライバ）を起動する。--dry は機体に指令を送らない試験用
  tb3ctl stop                  PC 側のサーバーを止める
  tb3ctl status                PC・機体・通信の状態をまとめて見る
  tb3ctl ros <コマンド...>     設定どおりのドメイン ID・DDS プロファイルで ROS 2 のコマンドを動かす（例: tb3ctl ros ros2 topic list）

--dry-run を付けると、実行するコマンドを表示するだけで何もしない。
"""
import argparse
import os
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.request
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIN = sys.platform == "win32"
DEFAULTS = dict(ROBOT_HOST="", ROBOT_USER="ubuntu", ROBOT_SSH_KEY="", ROS_DOMAIN_ID="0", RMW_IMPLEMENTATION="rmw_fastrtps_cpp",
                DDS_MODE="unicast", TURTLEBOT3_MODEL="waffle_pi", LDS_MODEL="LDS-02", DDS_IFACE="wlan0",
                JOINTS_PROFILE_ACCELERATION="25", JOINTS_PROFILE_VELOCITY="300", SERVER_PORT="8080", ROSBRIDGE_PORT="9090",
                WSL_DISTRO="Ubuntu-22.04")
DRY = False


# ---------------------------------------------------------------- 設定
def config_path(explicit=None):
    for p in (explicit, os.environ.get("TB3_CONFIG"), ROOT / "config" / "tb3.env", Path.home() / ".config" / "tb3-companion" / "tb3.env"):
        if p and Path(p).is_file():
            return Path(p)
    return None


def parse_env(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #")[0].strip().strip('"').strip("'")
        out[k.strip()] = v
    return out


def load_config():
    cfg = dict(DEFAULTS)
    p = config_path()
    if p:
        cfg.update({k: v for k, v in parse_env(p.read_text(encoding="utf-8")).items() if v != "" or k in ("ROBOT_SSH_KEY",)})
    cfg["_path"] = str(p) if p else None
    return cfg


def need_host(cfg):
    if not cfg["ROBOT_HOST"]:
        sys.exit("ROBOT_HOST が未設定です。`tb3ctl init` を先に動かしてください")


# ---------------------------------------------------------------- 実行
def show(cmd):
    return " ".join(shlex.quote(str(c)) for c in cmd)


def run(cmd, check=True, input_bytes=None, capture=False, quiet=False):
    if DRY:
        print("DRY>", show(cmd))
        return subprocess.CompletedProcess(cmd, 0, b"", b"")
    if not quiet:
        print("+", show(cmd), flush=True)
    r = subprocess.run(cmd, input=input_bytes, capture_output=capture)
    if check and r.returncode != 0:
        sys.exit(f"失敗（終了コード {r.returncode}）: {show(cmd)}")
    return r


def ssh_cmd(cfg, remote=None, tty=False):
    cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=30", "-o", "ConnectTimeout=10"]
    if tty:
        cmd.append("-t")
    if cfg["ROBOT_SSH_KEY"]:
        cmd += ["-i", os.path.expanduser(cfg["ROBOT_SSH_KEY"]), "-o", "IdentitiesOnly=yes"]
    cmd.append(f'{cfg["ROBOT_USER"]}@{cfg["ROBOT_HOST"]}')
    if remote:
        cmd.append(remote)
    return cmd


def pc_bash(cfg, script_rel, args=(), env=None):
    """PC 側のスクリプトを動かすコマンド。Windows では WSL（config の WSL_DISTRO）の中で動かす"""
    envs = [f"{k}={v}" for k, v in (env or {}).items()]
    inner = ["env", *envs, "bash", script_rel, *args] if envs else ["bash", script_rel, *args]
    if WIN:
        # --exec: シェルを通さず、引数をそのまま渡す（通すと $VAR や ; が Windows 側の解釈で壊れる）
        return ["wsl.exe", "-d", cfg["WSL_DISTRO"], "--cd", str(ROOT), "--exec", *inner]
    return inner


# ---------------------------------------------------------------- 機体へ送る
def robot_env_text(cfg):
    return "\n".join([
        "# tb3ctl が config/tb3.env から作った（機体の install_robot.sh が読む）",
        f'ROS_DOMAIN_ID={cfg["ROS_DOMAIN_ID"]}', f'TURTLEBOT3_MODEL={cfg["TURTLEBOT3_MODEL"]}', f'LDS_MODEL={cfg["LDS_MODEL"]}',
        f'DDS_IFACE={cfg["DDS_IFACE"]}', f'TB3_JOINTS_PROFILE_ACCELERATION={cfg["JOINTS_PROFILE_ACCELERATION"]}',
        f'TB3_JOINTS_PROFILE_VELOCITY={cfg["JOINTS_PROFILE_VELOCITY"]}', ""])


def push_robot(cfg):
    need_host(cfg)
    run(ssh_cmd(cfg, "mkdir -p ~/tb3-companion"))
    if DRY:
        print("DRY> tar -C", ROOT, "-cf - robot | ssh ... 'tar -C ~/tb3-companion -xf -'")
    else:
        tar = subprocess.Popen(["tar", "-C", str(ROOT), "--exclude=__pycache__", "-cf", "-", "robot"], stdout=subprocess.PIPE)
        rx = subprocess.run(ssh_cmd(cfg, "tar -C ~/tb3-companion -xf -"), stdin=tar.stdout)
        tar.stdout.close()
        if tar.wait() != 0 or rx.returncode != 0:
            sys.exit("機体へのファイルの転送に失敗しました（ssh でつながるか確認: tb3ctl robot-ssh）")
    run(ssh_cmd(cfg, "cat > ~/tb3-companion/robot/robot.env"), input_bytes=robot_env_text(cfg).encode())
    run(ssh_cmd(cfg, "chmod +x ~/tb3-companion/robot/install_robot.sh ~/tb3-companion/robot/bin/*.sh ~/tb3-companion/robot/hardware_patch/apply.sh"))


def cmd_robot_install(a, cfg):
    push_robot(cfg)
    phases = a.phases or ["all"]
    print("機体での導入を始めます（ws のビルドを含めて 1〜2 時間。途中で ssh が切れたら、もう一度同じコマンドで続きから動かせます）")
    run(ssh_cmd(cfg, f"bash ~/tb3-companion/robot/install_robot.sh {' '.join(phases)}", tty=True))


def cmd_robot_apply(a, cfg):
    push_robot(cfg)
    run(ssh_cmd(cfg, "bash ~/tb3-companion/robot/install_robot.sh files", tty=True))


def cmd_add_key(a, cfg):
    """機体の ~/.ssh/authorized_keys に公開鍵を足す（もう入れる鍵がある状態で）。同じ鍵は重ねて足さない"""
    need_host(cfg)
    for f in a.pubkeys:
        key = Path(f).expanduser().read_text(encoding="utf-8").strip().splitlines()[0]
        if not key.startswith(("ssh-", "ecdsa-", "sk-")):
            sys.exit(f"{f} は ssh の公開鍵に見えません（秘密鍵ではなく .pub を渡してください）")
        remote = ("mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && "
                  f"grep -qxF {shlex.quote(key)} ~/.ssh/authorized_keys || echo {shlex.quote(key)} >> ~/.ssh/authorized_keys; echo 'authorized_keys:'; wc -l < ~/.ssh/authorized_keys")
        run(ssh_cmd(cfg, remote))


def cmd_robot_ssh(a, cfg):
    need_host(cfg)
    r = run(ssh_cmd(cfg, " ".join(shlex.quote(c) for c in a.command) if a.command else None, tty=not a.command), check=False)
    sys.exit(r.returncode)


def tcp_open(host, port, timeout=3.0):
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def resolve_ip(host):
    """機体の名前（turtle-destroyer.local など）から IPv4 を引く。Windows 側の名前解決（mDNS が使える）で引いて、WSL へ渡す"""
    import socket
    try:
        return socket.getaddrinfo(host, 22, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    except OSError:
        return ""


def cmd_robot_wifi(a, cfg):
    """機体を別の Wi-Fi につなぐ。有線（直結でも、ルーター経由でもよい）で ssh できる状態で動かす。
    Wi-Fi に切り替えたあと、機体が Wi-Fi の IP を取り、PC から届くことを確かめてから確定する。
    確定できなければ、--restore-after 秒（既定 240）で、元の Wi-Fi の設定に自動で戻る。有線の ssh はそのあいだ切れない。"""
    need_host(cfg)
    if a.static and not a.gateway:
        sys.exit("--static には --gateway も要ります")
    if not a.psk and not a.open:
        sys.exit("--psk（パスフレーズ）か --open（パスワードなし）が要ります")
    run(ssh_cmd(cfg, "mkdir -p ~/tb3-companion/robot/bin"))
    scp = ["scp", "-o", "StrictHostKeyChecking=accept-new"] + (["-i", os.path.expanduser(cfg["ROBOT_SSH_KEY"]), "-o", "IdentitiesOnly=yes"] if cfg["ROBOT_SSH_KEY"] else [])
    run(scp + [str(ROOT / "robot" / "bin" / "tb3_set_wifi.py"), f'{cfg["ROBOT_USER"]}@{cfg["ROBOT_HOST"]}:tb3-companion/robot/bin/'])
    args = ["--ssid", a.ssid] + (["--psk", a.psk] if a.psk else ["--open"]) + (["--static", a.static, "--gateway", a.gateway] if a.static else ["--dhcp"])
    if a.dns:
        args += ["--dns", a.dns]
    user, restore_s = cfg["ROBOT_USER"], a.restore_after
    remote = (f"sudo rm -f /tmp/tb3_wifi_ok; "
              f"sudo python3 ~/tb3-companion/robot/bin/tb3_set_wifi.py {' '.join(shlex.quote(x) for x in args)} || exit 3; "
              f"sudo bash -c \"(sleep {restore_s}; [ -e /tmp/tb3_wifi_ok ] || {{ python3 /home/{user}/tb3-companion/robot/bin/tb3_set_wifi.py --restore; netplan apply; }}) >/dev/null 2>&1 &\"; "
              f"sudo netplan apply >/dev/null 2>&1; "
              f"for i in $(seq 60); do ip -4 -o addr show dev wlan0 scope global | grep -q . && break; sleep 1; done; "
              f"echo WIFI_IP=$(ip -4 -o addr show dev wlan0 scope global | awk '{{print $4}}' | cut -d/ -f1 | head -1); "
              f"echo ROBOT_NAME=$(hostname); iw dev wlan0 link 2>/dev/null | grep -E 'SSID|signal'")
    print(f"Wi-Fi を『{a.ssid}』に切り替えます（最大 1 分ほど）。有線の ssh は切れません。")
    r = run(ssh_cmd(cfg, remote), check=False, capture=True, quiet=True)
    if DRY:
        return
    out = r.stdout.decode(errors="replace")
    print(out.rstrip())
    info = dict(ln.split("=", 1) for ln in out.splitlines() if ln.startswith(("WIFI_IP=", "ROBOT_NAME=")))
    wifi_ip, name = info.get("WIFI_IP", ""), info.get("ROBOT_NAME", "")
    if r.returncode != 0 or not wifi_ip:
        sys.exit(f"機体が Wi-Fi の IP を取れませんでした（SSID・パスフレーズ・電波を確認）。{restore_s} 秒以内に元の Wi-Fi の設定へ自動で戻ります。")
    print(f"機体の Wi-Fi の IP: {wifi_ip}。PC から届くか確かめます…")
    ok = False
    for _ in range(10):
        if tcp_open(wifi_ip, 22):
            ok = True
            break
        time.sleep(2)
    if not ok:
        sys.exit(f"PC から {wifi_ip}:22 に届きません（PC が同じ Wi-Fi・同じネットワークにつながっているか確認）。\n"
                 f"確定していないので、{restore_s} 秒以内に元の Wi-Fi の設定へ自動で戻ります。")
    # 確定（自動で戻すのを止める）してから、ROS 2 のサービスを、新しい IP で起動し直す（DDS のプロファイルは起動のたびに作り直される）
    run(ssh_cmd(cfg, "touch /tmp/tb3_wifi_ok; sudo systemctl restart tb3-bringup tb3-deadman 2>/dev/null; echo restarted"), check=False)
    host = (a.static.split("/")[0] if a.static else (f"{name}.local" if name else wifi_ip))
    print(f"\n確定しました。機体の Wi-Fi の IP は {wifi_ip}。")
    if a.set_host:
        path = Path(cfg["_path"] or ROOT / "config" / "tb3.env")
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            lines = [f"ROBOT_HOST={host}" if ln.startswith("ROBOT_HOST=") else ln for ln in lines]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            print(f"{path} の ROBOT_HOST を {host} にしました。")
    else:
        print(f"config/tb3.env の ROBOT_HOST を {host} に書き換えてください（--set-host を付けると自動で書き換えます）。")
    print("有線のケーブルを外して、`tb3ctl status` で、Wi-Fi 越しにつながることを確かめてください。")


def cmd_install_key(a, cfg):
    """機体に入れる秘密鍵を、この PC の ~/.ssh に置いて、config の ROBOT_SSH_KEY に書く。
    リポジトリに入っている公開鍵（robot/keys/）と、組になっているか確かめる"""
    src = Path(a.private_key).expanduser()
    if not src.is_file():
        sys.exit(f"{src} がありません")
    head = src.read_text(errors="replace")[:80]
    if "PRIVATE KEY" not in head:
        sys.exit(f"{src} は秘密鍵に見えません（-----BEGIN ... PRIVATE KEY----- で始まるファイルを渡してください。.pub ではありません）")
    pub_repo = (ROOT / "robot" / "keys" / "id_ed25519_turtlebot.pub").read_text().split()[:2]
    r = subprocess.run(["ssh-keygen", "-y", "-f", str(src)], capture_output=True)
    if r.returncode != 0:
        sys.exit("秘密鍵を読めませんでした（パスフレーズ付きなら、先に ssh-keygen -p で外すか、ssh-agent を使ってください）")
    if r.stdout.decode().split()[:2] != pub_repo and not a.force:
        sys.exit("この秘密鍵は、リポジトリの公開鍵（robot/keys/id_ed25519_turtlebot.pub）と組になっていません。別の鍵を使うなら --force")
    dest = Path.home() / ".ssh" / "id_ed25519_turtlebot"
    dest.parent.mkdir(mode=0o700, exist_ok=True)
    if DRY:
        print("DRY> copy", src, "->", dest)
        return
    if src.resolve() != dest.resolve():            # すでにそこにある鍵なら、コピーしない
        dest.write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
    if WIN:
        subprocess.run(["icacls", str(dest), "/inheritance:r", "/grant:r", f"{os.environ.get('USERNAME', '')}:F"], capture_output=True)
    else:
        dest.chmod(0o600)
    cfgp = ROOT / "config" / "tb3.env"
    if cfgp.exists():
        lines = [f"ROBOT_SSH_KEY={dest}" if ln.startswith("ROBOT_SSH_KEY=") else ln for ln in cfgp.read_text(encoding="utf-8").splitlines()]
        cfgp.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"置きました: {dest}（config/tb3.env の ROBOT_SSH_KEY に書きました）")
    else:
        print(f"置きました: {dest}。tb3ctl init のとき、ssh の秘密鍵のパスに、これを答えてください")


# ---------------------------------------------------------------- PC 側
def cmd_server(a, cfg):
    env = {"TB3_DRYRUN": "1"} if a.dry else {}
    ip = resolve_ip(cfg["ROBOT_HOST"]) if cfg["ROBOT_HOST"] else ""
    if ip:
        env["ROBOT_IP"] = ip                       # WSL は mDNS（.local）を引けないことがあるので、Windows 側で引いた IP を渡す
    cmd = pc_bash(cfg, "pc/scripts/start_server.sh", env=env)
    print("PC 側のサーバーを起動します（止めるには Ctrl-C、または別の窓で tb3ctl stop）。%s" % ("試験用: 機体には指令を送りません" if a.dry else ""))
    if a.open and not DRY:
        import threading, webbrowser
        threading.Timer(8.0, lambda: webbrowser.open(f'http://localhost:{cfg["SERVER_PORT"]}/')).start()
    run(cmd, check=False)


def cmd_stop(a, cfg):
    run(pc_bash(cfg, "pc/scripts/kill_server.sh"), check=False)


def cmd_ros(a, cfg):
    if not a.command:
        sys.exit("usage: tb3ctl ros <コマンド...>")
    ip = resolve_ip(cfg["ROBOT_HOST"]) if cfg["ROBOT_HOST"] else ""
    r = run(pc_bash(cfg, "pc/scripts/run_ros.sh", args=a.command, env={"ROBOT_IP": ip} if ip else None), check=False)
    sys.exit(r.returncode)


def http_json(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def cmd_status(a, cfg):
    print(f"設定: {cfg['_path'] or '（なし。tb3ctl init を）'}   機体: {cfg['ROBOT_USER']}@{cfg['ROBOT_HOST'] or '?'}   ROS_DOMAIN_ID={cfg['ROS_DOMAIN_ID']}  RMW={cfg['RMW_IMPLEMENTATION']}  DDS_MODE={cfg['DDS_MODE']}")
    # PC のサーバー
    try:
        s = http_json(f'http://localhost:{cfg["SERVER_PORT"]}/api/circle')
        print(f"PC サーバー: 動いている（http://localhost:{cfg['SERVER_PORT']}/）  機体との通信 link_ok={s['link_ok']}  試験用={s['dry']}  "
              f"Orbit={s['running']} Dance={s['arm']['running']}")
    except Exception as e:  # noqa: BLE001
        print(f"PC サーバー: 動いていない（tb3ctl server で起動）  [{type(e).__name__}]")
    if not cfg["ROBOT_HOST"]:
        return
    # 機体
    ip = resolve_ip(cfg["ROBOT_HOST"])
    print(f"機体の宛先: {cfg['ROBOT_HOST']} -> {ip or '（名前を引けない。IP か、同じネットワークかを確認）'}   ssh(22) に{'届く' if ip and tcp_open(ip, 22) else '届かない'}")
    r = run(ssh_cmd(cfg, "echo up; uptime -p; hostname; ip -br -4 addr show wlan0 eth0 | cut -c1-60; "
                         "for s in tb3-bringup tb3-deadman tb3-watchdog wifi-powersave-off; do printf '%s: ' $s; systemctl is-active $s; done; "
                         "iw dev wlan0 link 2>/dev/null | grep -E 'SSID|signal|tx bitrate'; iw dev wlan0 get power_save 2>/dev/null; cat /etc/tb3/tb3.env 2>/dev/null | grep -v '^#'"),
            check=False, capture=True, quiet=True)
    if DRY:
        return
    if r.returncode != 0:
        print(f"機体: ssh できない（電源・Wi-Fi・ROBOT_HOST を確認）\n  {r.stderr.decode(errors='replace').strip()[:200]}")
    else:
        print("機体:\n" + "\n".join("  " + ln for ln in r.stdout.decode(errors="replace").splitlines()))


def cmd_init(a, cfg):
    target = ROOT / "config" / "tb3.env"
    if target.exists() and not a.force:
        sys.exit(f"{target} がもうあります。作り直すなら --force")
    template = (ROOT / "config" / "tb3.env.example").read_text(encoding="utf-8")
    vals = {}

    def ask(key, prompt, default):
        v = getattr(a, key.lower(), None)
        if v is None and not a.yes:
            v = input(f"{prompt} [{default}]: ").strip()
        vals[key] = v or default

    ask("ROBOT_HOST", "機体の IP か名前（例 192.168.0.50, turtlebot.local）", cfg["ROBOT_HOST"] or "192.168.11.100")
    ask("ROBOT_USER", "機体のユーザー名", cfg["ROBOT_USER"])
    ask("ROBOT_SSH_KEY", "ssh の秘密鍵のパス（無ければ空）", cfg["ROBOT_SSH_KEY"])
    ask("ROS_DOMAIN_ID", "ROS_DOMAIN_ID（機体と PC で同じ。0〜101）", cfg["ROS_DOMAIN_ID"])
    ask("DDS_MODE", "DDS の発見: unicast（Wi-Fi 向け）か multicast", cfg["DDS_MODE"])
    ask("DDS_IFACE", "機体の ROS 2 が使うインタフェース（wlan0 / eth0 / any）", cfg["DDS_IFACE"])
    if WIN:
        ask("WSL_DISTRO", "ROS 2 Humble が入った WSL のディストリビューション名", cfg["WSL_DISTRO"])
    lines = []
    for line in template.splitlines():
        k = line.split("=", 1)[0].strip()
        lines.append(f"{k}={vals[k]}" if k in vals and "=" in line and not line.lstrip().startswith("#") else line)
    if DRY:
        print("DRY> write", target)
        print("\n".join(l for l in lines if l.split("=")[0] in vals))
        return
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")   # Windows でも LF（bash の source が読めるように）
    print(f"書きました: {target}\n次: tb3ctl status  /  tb3ctl robot-install（機体が新品のとき）  /  tb3ctl server")


# ---------------------------------------------------------------- 本体
def main():
    global DRY
    ap = argparse.ArgumentParser(prog="tb3ctl", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="実行するコマンドを表示するだけ")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--force", action="store_true"); p.add_argument("--yes", action="store_true", help="質問せず、引数と既定値で作る")
    for k in ("robot_host", "robot_user", "robot_ssh_key", "ros_domain_id", "dds_mode", "dds_iface", "wsl_distro"):
        p.add_argument("--" + k.replace("_", "-"), dest=k)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("robot-install"); p.add_argument("phases", nargs="*", help="base ros ws files opencr all"); p.set_defaults(fn=cmd_robot_install)
    sub.add_parser("robot-apply").set_defaults(fn=cmd_robot_apply)
    p = sub.add_parser("robot-wifi"); p.add_argument("--ssid", required=True); p.add_argument("--psk"); p.add_argument("--static"); p.add_argument("--gateway")
    p.add_argument("--dns"); p.add_argument("--open", action="store_true", help="パスワードなしのネットワーク")
    p.add_argument("--set-host", action="store_true", help="確定したら config の ROBOT_HOST を新しい宛先に書き換える")
    p.add_argument("--restore-after", type=int, default=240, help="確定しなければ元に戻すまでの秒数"); p.set_defaults(fn=cmd_robot_wifi)
    p = sub.add_parser("install-key"); p.add_argument("private_key", help="前の担当者から受け取った秘密鍵のファイル"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_install_key)
    p = sub.add_parser("add-key"); p.add_argument("pubkeys", nargs="+", help="足す公開鍵のファイル（.pub）"); p.set_defaults(fn=cmd_add_key)
    p = sub.add_parser("robot-ssh"); p.add_argument("command", nargs=argparse.REMAINDER); p.set_defaults(fn=cmd_robot_ssh)
    p = sub.add_parser("server"); p.add_argument("--dry", action="store_true"); p.add_argument("--open", action="store_true", help="ブラウザで操作画面を開く"); p.set_defaults(fn=cmd_server)
    sub.add_parser("stop").set_defaults(fn=cmd_stop)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("ros"); p.add_argument("command", nargs=argparse.REMAINDER); p.set_defaults(fn=cmd_ros)
    for st in (sys.stdout, sys.stderr):          # cp932 などのコンソールで、表示できない文字があっても落ちないように
        try:
            st.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001
            pass
    a = ap.parse_args()
    DRY = a.dry_run
    cfg = load_config()
    a.fn(a, cfg)


if __name__ == "__main__":
    main()
