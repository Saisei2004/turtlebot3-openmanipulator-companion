// OpenManipulator-X（TB3 搭載）の順運動学・逆運動学。寸法は機体の robot_description から取った値。
// 座標は joint2 の軸を原点にした腕の平面: r = 前方 [m]、z = 上 [m]、pitch = 手先の下向き角 [rad]
(function (root) {
  const A = [0.024, 0.128];          // joint2 → joint3
  const L1 = Math.hypot(A[0], A[1]);
  const TH0 = Math.atan2(A[1], A[0]);
  const L2 = 0.124;                  // joint3 → joint4
  const L3 = 0.126;                  // joint4 → 手先 (end_effector_link)
  // robot_description（URDF）の限界は実角 a に対するもの。読み値 q の限界は a の限界から OFFSET を引いて直す
  // （2026-10-26、MuJoCo の全探索 workspace/ で確認。joint4 の上限はサーボの出力軸の範囲 π で頭打ち）
  const URDF_A = [[-2.8274, 2.8274], [-1.7907, 1.5708], [-0.9425, 1.3823], [-1.7907, 2.0420]];
  const GRIP = [-0.010, 0.019];
  // この機体のアームは関節の 0 位置が robot_description とずれている（2026-10-25 にカメラで実測）。
  // 実際の角度 = /joint_states の値 + OFFSET。指令 [0, -0.93, -0.07, 1.65] で上腕が真上・前腕と手先が水平になるのを確認済み
  const OFFSET = [0, 0.93, 0.07, -1.65];
  const LIMITS = URDF_A.map((l, i) => [l[0] - OFFSET[i], Math.min(Math.PI, l[1] - OFFSET[i])]);
  const J2_FROM_BASE = [-0.080, 0.1675]; // base_link から見た joint2 の位置（標準の TB3 Waffle 搭載時）

  // y 軸回りに q 回したときの (x, z)
  const rot = (q, x, z) => [x * Math.cos(q) + z * Math.sin(q), -x * Math.sin(q) + z * Math.cos(q)];

  // q は /joint_states と同じ値（指令に使う値）。LIMITS もこの値で判定する
  function fk(qRaw) {
    const q = qRaw.map((v, i) => v + OFFSET[i]);
    const a2 = q[1], a3 = q[1] + q[2], a4 = q[1] + q[2] + q[3];
    const p3 = rot(a2, A[0], A[1]);
    const d4 = rot(a3, L2, 0), p4 = [p3[0] + d4[0], p3[1] + d4[1]];
    const de = rot(a4, L3, 0), pe = [p4[0] + de[0], p4[1] + de[1]];
    return { yaw: q[0], r: pe[0], z: pe[1], pitch: a4, pts: [[0, 0], p3, p4, pe] };
  }

  // 肘を上にした解だけを返す。届かない・可動範囲外なら null
  function ik(t) {
    const wx = t.r - L3 * Math.cos(t.pitch), wz = t.z + L3 * Math.sin(t.pitch);
    const D = (wx * wx + wz * wz - L1 * L1 - L2 * L2) / (2 * L1 * L2);
    if (D < -1 || D > 1) return null;
    const psi = -Math.acos(D);
    const bA = Math.atan2(wz, wx) - Math.atan2(L2 * Math.sin(psi), L1 + L2 * Math.cos(psi));
    const a2 = TH0 - bA, a3 = -(bA + psi);
    const q = [t.yaw, a2, a3 - a2, t.pitch - a3].map((v, i) => v - OFFSET[i]);
    for (let i = 0; i < 4; i++) if (q[i] < LIMITS[i][0] || q[i] > LIMITS[i][1]) return null;
    return q;
  }

  root.ArmKin = { fk, ik, LIMITS, GRIP, OFFSET, J2_FROM_BASE, L: { L1, L2, L3 } };
})(typeof window !== "undefined" ? window : globalThis);
