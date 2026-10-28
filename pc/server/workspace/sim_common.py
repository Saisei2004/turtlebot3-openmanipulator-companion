"""MuJoCo 上の姿勢評価（衝突・手先位置・重力保持トルク）と、arm_kin.js と同じ解析 FK/IK。"""
import numpy as np
import mujoco
import omx_model as om

OFFSET = np.array(om.OFFSET)
A = (0.024, 0.128)
L1 = float(np.hypot(*A))
TH0 = float(np.arctan2(A[1], A[0]))
L2, L3 = 0.124, 0.126
# URDF の関節限界（a に適用）
URDF_LIM = np.array([[-2.827433388, 2.827433388], [-1.790707813, 1.570796327],
                     [-0.942477796, 1.382300768], [-1.790707813, 2.042035225]])
WEB_LIM = np.array([[-2.8274, 2.8274], [-1.7907, 1.5708], [-0.9425, 1.60], [-1.7907, 2.0420]])   # arm_kin.js の LIMITS（q に適用している）
TAU_STALL = 4.1                           # XM430-W350 失速トルク [N·m] @12V, 2.3A（ROBOTIS e-Manual XM430-W350）
GI = {g: i for i, g in enumerate(om.GROUPS)}
QUANT = 4.0                               # 深さは 0.25 mm 刻みの uint8 で持つ


def fk_a(a):
    """解析 FK（arm_kin.js と同じ）。a: (...,4) URDF 側の関節角。戻り: r, z, pitch（joint2 軸原点）"""
    a = np.asarray(a, float)
    a2 = a[..., 1]; a3 = a2 + a[..., 2]; a4 = a3 + a[..., 3]
    c, s = np.cos, np.sin
    x3 = A[0] * c(a2) + A[1] * s(a2); z3 = -A[0] * s(a2) + A[1] * c(a2)
    x4 = x3 + L2 * c(a3); z4 = z3 - L2 * s(a3)
    xe = x4 + L3 * c(a4); ze = z4 - L3 * s(a4)
    return xe, ze, a4


def ik_a(r, z, pitch, elbow):
    """解析 IK。elbow=-1 は arm_kin.js と同じ解、+1 はもう一方。届かないと nan。戻り: a (...,4)（yaw=0）"""
    r = np.asarray(r, float); z = np.asarray(z, float); pitch = np.asarray(pitch, float)
    wx = r - L3 * np.cos(pitch); wz = z + L3 * np.sin(pitch)
    D = (wx * wx + wz * wz - L1 * L1 - L2 * L2) / (2 * L1 * L2)
    ok = np.abs(D) <= 1
    psi = elbow * np.arccos(np.clip(D, -1, 1))
    bA = np.arctan2(wz, wx) - np.arctan2(L2 * np.sin(psi), L1 + L2 * np.cos(psi))
    a2 = TH0 - bA; a3t = -(bA + psi)
    out = np.stack([np.zeros_like(a2), a2, a3t - a2, pitch - a3t], -1)
    out[~ok] = np.nan
    return out


def wrap_q(q):
    """サーボの出力軸は [-π, π) なので、角度をその範囲に畳む"""
    return (np.asarray(q, float) + np.pi) % (2 * np.pi) - np.pi


class Sim:
    def __init__(self, payload_kg=0.0, with_env=True, gripper=0.019):
        self.m = om.load(payload_kg, with_env)
        self.d = mujoco.MjData(self.m)
        m = self.m
        self.qadr = [m.joint(n).qposadr[0] for n in ("joint1", "joint2", "joint3", "joint4")]
        self.gadr = [m.joint("grip_l").qposadr[0], m.joint("grip_r").qposadr[0]]
        self.dadr = [m.joint(n).dofadr[0] for n in ("joint1", "joint2", "joint3", "joint4")]
        self.tip = m.site("tip").id
        # 各 geom がどのグループか（-1 = アーム）
        grp = np.full(m.ngeom, -1, int)
        for g in range(m.ngeom):
            nm = m.geom(g).name
            if nm in ("wheel_l", "wheel_r"):
                grp[g] = GI["wheel"]
            elif nm in ("caster_l", "caster_r"):
                grp[g] = GI["caster"]
            elif nm in GI:
                grp[g] = GI[nm]
        self.grp = grp
        self.gname = [m.geom(g).name or m.body(m.geom_bodyid[g]).name for g in range(m.ngeom)]
        self.set_grip(gripper)
        self.j2 = np.array(om.J2_IN_BASE)

    def set_grip(self, g):
        self.d.qpos[self.gadr[0]] = g
        self.d.qpos[self.gadr[1]] = g

    def pose(self, a, yaw=None):
        q = np.array(a, float).copy()
        if yaw is not None:
            q[0] = yaw
        self.d.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.m, self.d)

    def tip_rz(self, a):
        """MuJoCo の手先位置を joint2 軸原点・joint1 の向きに揃えた (r, z, 横ずれ) にして返す"""
        self.pose(a)
        p = self.d.site_xpos[self.tip] - self.j2
        c, s = np.cos(a[0]), np.sin(a[0])
        return p[0] * c + p[1] * s, p[2], p[1] * c - p[0] * s

    def depths(self, a, yaw=None):
        """グループごとの最大めり込み量 [m]（長さ len(GROUPS)）。アーム同士は 'self'、床は 'floor'"""
        self.pose(a, yaw)
        mujoco.mj_collision(self.m, self.d)
        d = self.d
        out = np.zeros(len(om.GROUPS))
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = self.grp[c.geom1], self.grp[c.geom2]
            k = max(g1, g2) if max(g1, g2) >= 0 else 0
            pen = -c.dist
            if pen > out[k]:
                out[k] = pen
        return out

    def depths_u8(self, a, yaw=None):
        return np.minimum(255, np.round(self.depths(a, yaw) * 1000 * QUANT)).astype(np.uint8)

    def contacts(self, a, yaw=None):
        """接触ペアの一覧（検証用）"""
        self.pose(a, yaw)
        mujoco.mj_collision(self.m, self.d)
        return [(self.gname[c.geom1], self.gname[c.geom2], round(-c.dist * 1000, 2)) for c in self.d.contact[:self.d.ncon]]

    def hold_torque(self, a):
        """静止保持に必要な関節トルク（joint1..4）[N·m]。MuJoCo の qfrc_bias（重力項）を符号反転して返す"""
        self.d.qpos[self.qadr] = a
        self.d.qvel[:] = 0
        mujoco.mj_forward(self.m, self.d)
        return -self.d.qfrc_bias[self.dadr]
