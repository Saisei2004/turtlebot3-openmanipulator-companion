#!/usr/bin/env python3
"""TB3 操作画面の配信と、アーム姿勢・動作列の保存 API。

GET  /api/library  -> {"poses": {...}, "sequences": {...}}
PUT  /api/library  <- 同じ形の JSON を丸ごと保存（poses.json に書く）
POST /api/check    <- {"poses": [[q1,q2,q3,q4], ...]}（/joint_states と同じ値）
                   -> 各姿勢の衝突・関節限界・重力トルクを MuJoCo で判定（workspace/ のモデル）
GET  /api/circle   -> 円走行（Orbit）の状態
POST /api/circle   <- {"action":"start","radius":0.3,"speed":0.1,"dir":"left"} / {"action":"stop","what":"all|orbit|dance"}
                   PC の ROS ノード（circle_driver.py）が /cmd_vel を 20 Hz で出し続ける。LiDAR で進路を見て、障害物があれば止まる
POST /api/dance    <- {"arm":true,"gripper":true,"scale":0.9,"grip_period":4}  アーム全関節とグリッパーを動かし続ける。
                   始める前に、今の姿勢からの経路と合成波全体を MuJoCo で調べ、当たらない大きさに自動で縮める
それ以外は webui/ の静的ファイルを返す。
"""
import json
import os
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB = HERE / "webui"
# 姿勢と動作列の保存先。リポジトリの外（TB3_DATA_DIR、既定 ~/.local/share/tb3-companion）に置き、git を汚さない
DATA_DIR = Path(os.environ.get("TB3_DATA_DIR") or Path.home() / ".local" / "share" / "tb3-companion")
STORE = DATA_DIR / "poses.json"
MAX_BYTES = 256 * 1024
TOL_M = 0.002                     # めり込み 2 mm までは接触なし（workspace/sweep.py と同じ）
TAU_STALL = 4.1                   # XM430-W350 の失速トルク [N·m]
ENV = "photo_solid"               # 車体の仮定: workspace/omx_model.py の VARIANTS
_sim = {}
_sim_lock = threading.Lock()
_circle = {}


def dance_plan(q0, requested):
    """合成波の全体（始めのなめらかなつなぎ込み + 24 秒の 1 周期）を MuJoCo で調べ、当たらない最大の大きさを返す。1.15 倍でも当たらないことを条件にして余裕を持たせる。無ければ None"""
    sim_check([])                               # モデルを読み込む
    with _sim_lock:
        if "s0" not in _sim:
            return None
        np, sc = _sim["np"], _sim["sc"]
        import circle_driver as cd
        lim = np.array(sc.URDF_LIM) - sc.OFFSET[:, None]
        lim[3, 1] = min(np.pi, lim[3, 1])

        def free(scale):
            for t in np.arange(0.0, cd.DANCE_RAMP_S + cd.DANCE_T + 0.5, 0.05):
                q = np.array(cd.dance_pose(q0, scale, t)[0])
                if (q < lim[:, 0] + 0.02).any() or (q > lim[:, 1] - 0.02).any():
                    return False
                dep = _sim["s0"].depths(q + sc.OFFSET)
                if max(float(dep[i]) for _, i in _sim["idx"]) > TOL_M:
                    return False
            return True

        s = requested
        while s >= 0.3 - 1e-9:
            if free(s) and free(s * 1.15):
                return round(s, 2)
            s -= 0.05
        return None


def circle():
    """円走行ドライバ（ROS 2 ノード）。ROS が使えない環境では None"""
    if "drv" not in _circle:
        try:
            sys.path.insert(0, str(HERE))
            import atexit
            import circle_driver
            drv = circle_driver.get_driver(dry=os.environ.get("TB3_DRYRUN") == "1")
            atexit.register(lambda: drv.stop("server exit"))
            _circle["drv"] = drv
        except Exception as e:  # noqa: BLE001
            _circle["drv"] = None
            _circle["err"] = repr(e)
            print("circle unavailable:", e, flush=True)
    return _circle["drv"]


def sim_check(poses):
    """poses: q（/joint_states と同じ値）のリスト。MuJoCo が無い・読めないときは None"""
    with _sim_lock:
        if "err" in _sim:
            return None
        if "s0" not in _sim:
            cwd = os.getcwd()
            try:
                sys.path.insert(0, str(HERE / "workspace"))
                os.chdir(HERE / "workspace")          # モデルのメッシュを相対パス（meshes/）で読むため
                import numpy as np
                import omx_model as om
                import sim_common as sc
                _sim.update(np=np, om=om, sc=sc, s0=sc.Sim(), s2=sc.Sim(payload_kg=0.2),
                            idx=[(g, om.GROUPS.index(g)) for g in om.VARIANTS[ENV]])
                print("sim ready", flush=True)
            except Exception as e:  # noqa: BLE001
                _sim["err"] = repr(e)
                print("sim unavailable:", e, flush=True)
                return None
            finally:
                os.chdir(cwd)
        np, sc = _sim["np"], _sim["sc"]
        out = []
        for q in poses:
            a = np.array(q, float) + sc.OFFSET
            dep = _sim["s0"].depths(a)
            hits = [g for g, i in _sim["idx"] if dep[i] > TOL_M]
            worst = max(float(dep[i]) for _, i in _sim["idx"])
            lim = [k + 1 for k in range(4) if a[k] < sc.URDF_LIM[k][0] - 1e-9 or a[k] > sc.URDF_LIM[k][1] + 1e-9]
            tau = float(np.abs(_sim["s2"].hold_torque(a)).max())
            out.append({"ok": not hits and not lim, "hit": hits, "limit": lim,
                        "depth_mm": round(worst * 1000, 1), "torque_pct_200g": round(tau / TAU_STALL * 100)})
        return out

# 旧構成の ~/.tb3_home.json の home を最初の 1 件にする
SEED = {
    "poses": {
        # OpenManipulator-X 標準の折りたたみ姿勢 a=[0,-1.05,1.05,0] を q に直したもの（MuJoCo で衝突なしを確認）。旧構成の home は今の関節 0 位置では自己衝突する
        "home": {"joints": [0.0, -1.98, 0.98, 1.65], "gripper": 0.0038},
    },
    "sequences": {},
}


def load():
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return json.loads(json.dumps(SEED))


def valid(lib):
    if not isinstance(lib, dict) or not isinstance(lib.get("poses"), dict) or not isinstance(lib.get("sequences"), dict):
        return False
    for p in lib["poses"].values():
        j = p.get("joints") if isinstance(p, dict) else None
        if not (isinstance(j, list) and len(j) == 4 and all(isinstance(v, (int, float)) for v in j)):
            return False
        if not isinstance(p.get("gripper"), (int, float)):
            return False
    for s in lib["sequences"].values():
        if not isinstance(s, list) or not all(isinstance(st, dict) and isinstance(st.get("pose"), str) for st in s):
            return False
    return True


def save(lib):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=".poses-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STORE)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/config.js":        # 画面が使うポート（tb3ctl の設定 ROSBRIDGE_PORT）を渡す
            port = int(os.environ.get("ROSBRIDGE_PORT") or 9090)
            body = ("window.TB3_ROSBRIDGE_PORT = %d;\n" % port).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/library":
            return self._json(200, load())
        if self.path == "/api/circle":
            drv = circle()
            return self._json(200, drv.status()) if drv else self._json(503, {"error": "no ros", "detail": _circle.get("err", "")})
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/circle":
            return self._post_circle()
        if self.path == "/api/dance":
            return self._post_dance()
        if self.path != "/api/check":
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BYTES:
            return self._json(413, {"error": "too large"})
        try:
            poses = json.loads(self.rfile.read(n))["poses"]
            assert isinstance(poses, list) and len(poses) <= 400
            assert all(isinstance(q, list) and len(q) == 4 and all(isinstance(v, (int, float)) for v in q) for q in poses)
        except (ValueError, KeyError, AssertionError):
            return self._json(400, {"error": "bad shape"})
        res = sim_check(poses)
        if res is None:
            return self._json(503, {"error": "no sim", "detail": _sim.get("err", "")})
        return self._json(200, {"results": res})

    def _post_dance(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 4096:
            return self._json(413, {"error": "too large"})
        try:
            req = json.loads(self.rfile.read(n))
            arm, grip = bool(req.get("arm", True)), bool(req.get("gripper", True))
            scale, period = float(req.get("scale", 0.9)), float(req.get("grip_period", 4.0))
            assert 0.3 <= scale <= 1.0 and 2.0 <= period <= 8.0 and (arm or grip)
        except (ValueError, TypeError, AssertionError):
            return self._json(400, {"error": "bad shape"})
        drv = circle()
        if drv is None:
            return self._json(503, {"error": "no ros", "detail": _circle.get("err", "")})
        q0 = drv.joint_q()
        if q0 is None:
            return self._json(409, {"error": "機体の関節の値が来ていません"})
        used = scale
        if arm:
            used = dance_plan(q0, scale)
            if used is None:
                return self._json(409, {"error": "今の姿勢からは、当たらない大きさの動きを作れません。READY か HOME にしてからやり直してください"})
        try:
            drv.start_dance(used, q0, arm, grip, period)
        except RuntimeError as e:
            return self._json(409, {"error": str(e)})
        res = drv.status()
        res["scale_used"] = used if arm else None
        return self._json(200, res)

    def _post_circle(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 4096:
            return self._json(413, {"error": "too large"})
        try:
            req = json.loads(self.rfile.read(n))
            assert req["action"] in ("start", "stop")
        except (ValueError, KeyError, AssertionError):
            return self._json(400, {"error": "bad shape"})
        drv = circle()
        if drv is None:
            return self._json(503, {"error": "no ros", "detail": _circle.get("err", "")})
        if req["action"] == "stop":
            what = req.get("what", "all")
            drv.stop("stopped by operator", what if what in ("all", "orbit", "dance") else "all")
            return self._json(200, drv.status())
        try:
            drv.start(req.get("radius", 0.30), req.get("speed", 0.10), req.get("dir", "left") != "right", req.get("max_s"))
        except (ValueError, TypeError) as e:
            return self._json(400, {"error": str(e)})
        except RuntimeError as e:
            return self._json(409, {"error": str(e)})
        return self._json(200, drv.status())

    def do_PUT(self):
        if self.path != "/api/library":
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BYTES:
            return self._json(413, {"error": "too large"})
        try:
            lib = json.loads(self.rfile.read(n))
        except ValueError:
            return self._json(400, {"error": "bad json"})
        if not valid(lib):
            return self._json(400, {"error": "bad shape"})
        save(lib)
        return self._json(200, {"ok": True})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"TB3 web on 0.0.0.0:{port}  (library: {STORE}, dry-run: {os.environ.get('TB3_DRYRUN') == '1'})", flush=True)
    threading.Thread(target=circle, daemon=True).start()          # 通信の発見に数秒かかるので、起動と同時に ROS ノードを立てておく
    threading.Thread(target=lambda: sim_check([]), daemon=True).start()   # MuJoCo のモデルも読んでおく
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
