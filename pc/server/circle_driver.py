"""PC 側で動かす「ずっと動き続ける」ドライバ（ROS 2 ノード）。車輪（Orbit）・アーム全関節（Dance）・グリッパーを、PC から数値を出し続けて動かす。

安全の考え方（PC と機体の接続が切れたら動きが止まる）:
- 心拍 /tb3_pc_alive を 20 Hz で出し続ける。機体側の見張り（tb3_deadman.py）は、これが 0.5 秒途切れたら、アームをその場で止め、車輪を止める。
- 車輪: /cmd_vel を 20 Hz で出し続ける。止まると機体の diff_drive が 0.5 秒で止まる（機体側の設定 cmd_vel_timeout）。
- アーム: 決まった動きなので、先 1.5 秒ぶんの軌道（0.1 秒ごとの位置と速度）をまとめて 0.5 秒ごとに渡す（20 Hz で渡し直すより、なめらか）。
  PC が止まっても、見張りが 0.3 秒で止めるので、動き続けるのは最大でも約 0.6 秒。
- グリッパー: 目標を一定間隔で出す。止まると、最後の目標の位置に留まる。
- PC 側でも、機体からの /joint_states か /scan が 1.5 秒来なければ、すべて止める。LiDAR で円の進路に障害物があれば車輪だけ止める。
"""
import math
import threading
import time

import rclpy
from builtin_interfaces.msg import Duration
from control_msgs.action import GripperCommand
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, JointState, LaserScan
from std_msgs.msg import Int8
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

JOINTS = ["joint1", "joint2", "joint3", "joint4"]
LIDAR_X = -0.024      # base_scan は base_link の 2.4 cm 後ろ（robot_description）
OWN_RADIUS = 0.23     # この内側の点は機体自身（柱・電池・ケーブル）とみなして無視する
INNER_MARGIN = 0.19   # 機体が円を描くとき、内側にはみ出す幅（半幅 + 余裕）
OUTER_MARGIN = 0.27   # 外側にはみ出す幅（外接円の半径 + 余裕）
AHEAD_DEG = 70.0      # これから通る円弧の長さ（角度）。0.1 m/s・半径 0.3 m で約 3.7 秒ぶん
BEHIND_DEG = 6.0
MIN_POINTS = 3        # ノイズ 1〜2 点では止まらない
RESUME_CLEAR_S = 1.5
STALE_S = 1.5
SPEED_RANGE = (0.03, 0.15)
RADIUS_RANGE = (0.20, 0.60)
MAX_OMEGA = 0.6

# ---- Dance: 全関節がずっと動く、周期 24 秒の合成波（workspace/dance_search.py で衝突しないことを確認）----
DANCE_T = 24.0
DANCE_K = (2, 3, 5, 4)                 # 24 秒の間に何周するか（関節ごとに違う周期 = 常にどれかが動く）
DANCE_PHI = (0.0, 0.7, 1.9, 3.1)
DANCE_AMP = (0.55, 0.40, 0.35, 0.50)   # [rad] × scale
DANCE_CENTER = (0.0, -0.93, -0.07, 1.65)   # READY（上腕が真上、前腕と手先が水平）
DANCE_RAMP_S = 3.0                     # 今の姿勢から合成波へなめらかにつなぐ時間
CHUNK_EVERY_S = 0.5                    # 先の軌道を渡し直す間隔
CHUNK_STEP_S = 0.1                     # 軌道の点の間隔
CHUNK_N = 15                           # 先 0.1〜1.5 秒ぶん
GRIP_OPEN, GRIP_CLOSE = 0.019, -0.010


def smoothstep(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u), 6 * u * (1 - u)       # 値と du/du（正規化した傾き）


def dance_pose(q0, scale, t):
    """時刻 t [s]（開始から）の目標位置と速度。最初の DANCE_RAMP_S 秒は q0 から合成波へなめらかに移る"""
    w = 2 * math.pi / DANCE_T
    pat = [c + scale * a * math.sin(w * k * t + p) for c, a, k, p in zip(DANCE_CENTER, DANCE_AMP, DANCE_K, DANCE_PHI)]
    dpat = [scale * a * w * k * math.cos(w * k * t + p) for a, k, p in zip(DANCE_AMP, DANCE_K, DANCE_PHI)]
    u, du = smoothstep(t / DANCE_RAMP_S)
    du = du / DANCE_RAMP_S if t < DANCE_RAMP_S else 0.0
    q = [b * (1 - u) + c * u for b, c in zip(q0, pat)]
    dq = [(c - b) * du + u * d for b, c, d in zip(q0, pat, dpat)]
    return q, dq


def danger_points(points, radius, left):
    """points: ロボット座標（x 前・y 左、base_link 原点）の (x, y) のリスト。
    円の中心は左回りなら (0, +R)、右回りなら (0, -R)。これから通る帯の中にある点の数と、そこまでの円弧の長さ [m] の最小値を返す"""
    cy = radius if left else -radius
    inner, outer = max(0.0, radius - INNER_MARGIN), radius + OUTER_MARGIN
    th_robot = -math.pi / 2 if left else math.pi / 2
    n, nearest = 0, None
    for x, y in points:
        if math.hypot(x, y) < OWN_RADIUS:
            continue
        d = math.hypot(x, y - cy)
        if d < inner or d > outer:
            continue
        th = math.atan2(y - cy, x)
        phi = (th - th_robot) if left else (th_robot - th)
        phi = (phi + math.pi) % (2 * math.pi) - math.pi
        if -math.radians(BEHIND_DEG) <= phi <= math.radians(AHEAD_DEG):
            n += 1
            arc = max(0.0, phi) * radius
            nearest = arc if nearest is None else min(nearest, arc)
    return n, nearest


def scan_to_points(msg):
    pts = []
    a = msg.angle_min
    for r in msg.ranges:
        if msg.range_min < r < msg.range_max and math.isfinite(r):
            pts.append((r * math.cos(a) + LIDAR_X, r * math.sin(a)))
        a += msg.angle_increment
    return pts


class CircleDriver(Node):
    def __init__(self, dry=False):
        super().__init__("tb3_circle_driver")
        self.dry = dry                                  # True: 機体には何も送らず、別名のトピックに出す（試験用）
        self.lock = threading.Lock()
        self.pub = self.create_publisher(Twist, "/cmd_vel_dryrun" if dry else "/cmd_vel", 10)
        self.arm_pub = self.create_publisher(JointTrajectory, "/arm_dryrun" if dry else "/arm_controller/joint_trajectory", 10)
        self.alive_pub = self.create_publisher(Int8, "/tb3_pc_alive_dryrun" if dry else "/tb3_pc_alive", 10)
        self.grip_client = ActionClient(self, GripperCommand, "/gripper_controller/gripper_cmd")
        self.create_subscription(LaserScan, "/scan", self._on_scan, qos_profile_sensor_data)
        self.create_subscription(JointState, "/joint_states", self._on_joints, 10)
        self.create_subscription(Odometry, "/odom", self._on_odom, 10)
        self.create_subscription(Imu, "/imu_broadcaster/imu", self._on_imu, qos_profile_sensor_data)
        self.cfg = dict(running=False, radius=0.30, speed=0.10, left=True, max_s=None)
        self.t_start = 0.0
        self.t_scan = self.t_joints = self.t_imu = 0.0
        self.points = []
        self.q_now = None
        self.yaw_last = None
        self.yaw_sum = 0.0
        self.gyro_z = 0.0
        self.blocked = False
        self.blocked_info = ""
        self.clear_since = None
        self.stop_reason = ""
        self.sent = 0
        # アーム
        self.arm = dict(running=False, scale=0.9, q0=None, t0=0.0, next_chunk=0.0, sent=0, chunks=0)
        self.arm_reason = ""
        # グリッパー
        self.grip = dict(running=False, period=4.0, t0=0.0, open=None, count=0, last_toggle=0.0)
        self.grip_reason = ""
        self.create_timer(0.05, self._tick)

    # ---- 受信 ----
    def _on_scan(self, m):
        pts = scan_to_points(m)
        with self.lock:
            self.points, self.t_scan = pts, time.time()

    def _on_joints(self, m):
        d = dict(zip(m.name, m.position))
        with self.lock:
            self.t_joints = time.time()
            if all(j in d for j in JOINTS):
                self.q_now = [d[j] for j in JOINTS]

    def _on_imu(self, m):
        self.gyro_z, self.t_imu = m.angular_velocity.z, time.time()

    def _on_odom(self, m):
        q = m.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        with self.lock:
            if self.yaw_last is not None and self.cfg["running"]:
                self.yaw_sum += (yaw - self.yaw_last + math.pi) % (2 * math.pi) - math.pi
            self.yaw_last = yaw

    def joint_q(self):
        with self.lock:
            return list(self.q_now) if self.q_now else None

    def _link_ok(self, now):
        return now - self.t_joints < STALE_S and now - self.t_scan < STALE_S

    # ---- 円走行（車輪）----
    def start(self, radius, speed, left, max_s=None):
        radius, speed = float(radius), float(speed)
        if not (RADIUS_RANGE[0] <= radius <= RADIUS_RANGE[1] and SPEED_RANGE[0] <= speed <= SPEED_RANGE[1]):
            raise ValueError("radius 0.20-0.60 m, speed 0.03-0.15 m/s")
        if speed / radius > MAX_OMEGA:
            raise ValueError("旋回が速すぎます（speed / radius ≤ 0.6 rad/s）")
        now = time.time()
        if not self._link_ok(now):
            raise RuntimeError("機体からの /scan か /joint_states が来ていません")
        with self.lock:
            self.cfg = dict(running=True, radius=radius, speed=speed, left=bool(left), max_s=max_s)
            self.t_start, self.yaw_sum, self.stop_reason = now, 0.0, ""
            self.blocked, self.blocked_info, self.clear_since, self.sent = False, "", None, 0

    # ---- アームとグリッパー ----
    def start_dance(self, scale, q0, arm=True, gripper=True, grip_period=4.0):
        if not self._link_ok(time.time()):
            raise RuntimeError("機体からの /scan か /joint_states が来ていません")
        with self.lock:
            if arm:
                self.arm = dict(running=True, scale=float(scale), q0=list(q0), t0=time.time(), next_chunk=0.0, sent=0, chunks=0)
                self.arm_reason = ""
            if gripper:
                self.grip = dict(running=True, period=float(grip_period), t0=time.time(), open=None, count=0, last_toggle=0.0)
                self.grip_reason = ""

    def stop(self, reason="stopped", what="all"):
        hold = None
        with self.lock:
            if what in ("all", "orbit") and self.cfg["running"]:
                self.cfg["running"], self.stop_reason = False, reason
            if what in ("all", "dance"):
                if self.arm["running"]:
                    self.arm["running"], self.arm_reason = False, reason
                    hold = dance_pose(self.arm["q0"], self.arm["scale"], time.time() - self.arm["t0"])[0]
                if self.grip["running"]:
                    self.grip["running"], self.grip_reason = False, reason
        if what in ("all", "orbit"):
            for _ in range(3):
                self.pub.publish(Twist())
        if hold is not None:
            self._publish_arm(hold, [0.0] * 4, 0.4)
        with self.lock:
            still = self._mask()
        if still == 0:
            self.alive_pub.publish(Int8(data=0))        # PC が自分で止めた。見張りは外れる

    def _mask(self):
        """今 PC が動かしているもの: 1 = 車輪, 2 = アーム, 4 = グリッパー"""
        return (1 if self.cfg["running"] else 0) | (2 if self.arm["running"] else 0) | (4 if self.grip["running"] else 0)

    def status(self):
        now = time.time()
        with self.lock:
            c, a, g = dict(self.cfg), dict(self.arm), dict(self.grip)
            run = c["running"]
            return {
                "running": run, "radius": c["radius"], "speed": c["speed"], "dir": "left" if c["left"] else "right",
                "elapsed_s": round(now - self.t_start, 1) if run else 0, "laps": round(abs(self.yaw_sum) / (2 * math.pi), 2),
                "blocked": self.blocked, "blocked_info": self.blocked_info, "stop_reason": self.stop_reason,
                "scan_age_s": round(now - self.t_scan, 2) if self.t_scan else None,
                "link_ok": self._link_ok(now),
                "gyro_z": round(self.gyro_z, 3) if now - self.t_imu < 1 else None,
                "cmd_omega": round((c["speed"] / c["radius"]) * (1 if c["left"] else -1), 3) if run and not self.blocked else 0.0,
                "dry": self.dry,
                "arm": {"running": a["running"], "scale": a["scale"], "elapsed_s": round(now - a["t0"], 1) if a["running"] else 0,
                        "sent": a["sent"], "chunks": a["chunks"], "stop_reason": self.arm_reason},
                "gripper": {"running": g["running"], "period_s": g["period"], "open": g["open"], "count": g["count"], "stop_reason": self.grip_reason},
            }

    # ---- 出力 ----
    def _publish_arm(self, q, dq, h):
        self._publish_points([(q, dq, h)])

    def _publish_points(self, pts):
        msg = JointTrajectory(joint_names=JOINTS)
        for q, dq, h in pts:
            pt = JointTrajectoryPoint(positions=[float(v) for v in q], velocities=[float(v) for v in dq])
            pt.time_from_start = Duration(sec=int(h), nanosec=int(round((h % 1) * 1e9)))
            msg.points.append(pt)
        self.arm_pub.publish(msg)

    def _send_grip(self, pos):
        if self.dry:
            return
        if not self.grip_client.server_is_ready():
            return
        goal = GripperCommand.Goal()
        goal.command.position = float(pos)
        goal.command.max_effort = -1.0
        self.grip_client.send_goal_async(goal)

    # ---- 制御（20 Hz）----
    def _tick(self):
        now = time.time()
        stop_all = None
        with self.lock:
            run_any = self.cfg["running"] or self.arm["running"] or self.grip["running"]
            if not run_any:
                return
            if not self._link_ok(now):
                stop_all = "link lost（機体との通信が途切れた）"
            elif self.cfg["running"] and self.cfg["max_s"] and now - self.t_start > self.cfg["max_s"]:
                stop_all = "time up"
        if stop_all:
            self.stop(stop_all, "all")
            return
        with self.lock:
            mask = self._mask()
        self.alive_pub.publish(Int8(data=mask))         # 心拍。止まると機体側の見張りが 0.3 秒で腕と車輪を止める
        self._tick_orbit(now)
        self._tick_arm(now)
        self._tick_gripper(now)

    def _tick_orbit(self, now):
        with self.lock:
            c = dict(self.cfg)
            if not c["running"]:
                return
            n, nearest = danger_points(self.points, c["radius"], c["left"])
            if n >= MIN_POINTS:
                self.blocked, self.clear_since = True, None
                self.blocked_info = f"前方 {nearest:.2f} m の円弧上に障害物 ({n} 点)"
            elif self.blocked:
                self.clear_since = self.clear_since or now
                if now - self.clear_since >= RESUME_CLEAR_S:
                    self.blocked, self.blocked_info, self.clear_since = False, "", None
            blocked = self.blocked
        m = Twist()
        if not blocked:
            m.linear.x = c["speed"]
            m.angular.z = (c["speed"] / c["radius"]) * (1 if c["left"] else -1)
        self.pub.publish(m)
        self.sent += 1

    def _tick_arm(self, now):
        with self.lock:
            a = self.arm
            if not a["running"] or now < a["next_chunk"]:
                return
            a["next_chunk"] = now + CHUNK_EVERY_S
            t0 = now - a["t0"]
            pts = []
            for k in range(1, CHUNK_N + 1):
                h = k * CHUNK_STEP_S
                q, dq = dance_pose(a["q0"], a["scale"], t0 + h)
                pts.append((q, dq, h))
            a["sent"] += len(pts)
            a["chunks"] += 1
        self._publish_points(pts)

    def _tick_gripper(self, now):
        with self.lock:
            g = self.grip
            if not g["running"]:
                return
            half = g["period"] / 2
            want_open = int((now - g["t0"]) / half) % 2 == 0
            if g["open"] is None or want_open != g["open"]:
                g["open"], g["count"], g["last_toggle"] = want_open, g["count"] + 1, now
                send = GRIP_OPEN if want_open else GRIP_CLOSE
            else:
                send = None
        if send is not None:
            self._send_grip(send)


_node = None
_node_lock = threading.Lock()


def get_driver(dry=False):
    """最初に呼んだとき ROS を初期化してノードを別スレッドで回す"""
    global _node
    with _node_lock:
        if _node is None:
            rclpy.init()
            _node = CircleDriver(dry)
            threading.Thread(target=rclpy.spin, args=(_node,), daemon=True).start()
        return _node
