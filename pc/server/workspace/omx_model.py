"""TB3 + OpenManipulator-X の MuJoCo モデル。

寸法・質量・慣性・メッシュはすべて機体の robot_description（robot.urdf）と
turtlebot3_manipulation_description のメッシュから取る。リンクのメッシュは長手方向のスラブ（凸分解）に切って使う（mesh_parts.py）。
機体の車体（板・LiDAR・車輪）だけは、実物の 3D プリント車体の寸法が分からないので、写真と標準 Waffle Pi の
メッシュから概算した箱で置き換える（下の定数が仮定。結果に効くので workspace.json の meta にも書き出す）。

座標系: ワールド = base_link。x 前、y 左、z 上（原点は車輪軸の高さ。床は z=-0.010）。
関節角は URDF 側の値 a（= /joint_states の値 q + OFFSET）。
"""
import glob
import os
import xml.etree.ElementTree as ET
import mujoco

URDF = "robot.urdf"
OFFSET = [0.0, 0.93, 0.07, -1.65]            # 実角 a = 読み値 q + OFFSET（カメラで実測済み）
FLOOR_Z = -0.010                              # base_footprint の高さ（base_joint）
J2_IN_BASE = (-0.080, 0.0, 0.1675)            # joint2 の軸（r-z 座標の原点）の base_link 位置
TIP_POS = (0.126, 0.0, 0.0)                   # end_effector_link（link5 基準）

# ---- 車体の仮定（実物を測って直すところ）----
PLATE_Z = (0.082, 0.092)                      # 上段の板の厚み。標準 Waffle Pi の base.stl で最上段は z=82〜92 mm。アーム土台(link1 の底)が z=91 mm で載る
BODY_Z = (0.0, 0.082)                         # 板と板のあいだ（電池・ラズパイ・OpenCR・柱）。ここを「中身が詰まっている」とみなす（保守的）
PLATE_Y = (-0.1394, 0.1394)
# 上段の板の前端 x。写真から +0.05〜+0.07 と読めた（標準 Waffle は +0.1413）。写真の姿勢が衝突しない +0.050 を基準にし ±2 cm も試す
PLATE_X_REAR = -0.215                         # 後端（写真から。標準は -0.1328）
FRONTS = {"f030": 0.030, "f050": 0.050, "f070": 0.070}
STOCK_X = (-0.1328, 0.1413)                   # 標準 Waffle Pi
WHEEL = dict(r=0.033, half_w=0.009, y=0.144, z=0.023)
CASTER = dict(size=(0.015, 0.0045, 0.010), pos=(-0.177, 0.064, -0.004))
LIDAR_POS = (-0.024, 0.0, 0.122)              # ladar.stl は LDS-01 のメッシュ（実機は LDS-02。形は近い）

# 衝突結果を入れる配列の添字（Sim.depths の並び）
GROUPS = ["self", "floor", "wheel", "caster", "lidar",
          "plate_f030", "body_f030", "plate_f050", "body_f050", "plate_f070", "body_f070",
          "plate_stock", "body_stock"]
# 車体の仮定ごとに「どのグループとの衝突を数えるか」
VARIANTS = {
    "photo_solid": ["self", "floor", "wheel", "caster", "lidar", "plate_f050", "body_f050"],
    "photo_solid_f030": ["self", "floor", "wheel", "caster", "lidar", "plate_f030", "body_f030"],
    "photo_solid_f070": ["self", "floor", "wheel", "caster", "lidar", "plate_f070", "body_f070"],
    "photo_plate_only": ["self", "floor", "wheel", "lidar", "plate_f050"],
    "stock_solid": ["self", "floor", "wheel", "caster", "lidar", "plate_stock", "body_stock"],
    "self_floor": ["self", "floor"],
}


def _f(s):
    return [float(x) for x in s.split()]


def _inertial(link):
    i = link.find("inertial")
    m = float(i.find("mass").get("value"))
    o = _f(i.find("origin").get("xyz"))
    t = {k: float(v) for k, v in i.find("inertia").attrib.items()}
    full = f"{t['ixx']:.9g} {t['iyy']:.9g} {t['izz']:.9g} {t['ixy']:.9g} {t['ixz']:.9g} {t['iyz']:.9g}"
    return f'<inertial pos="{o[0]:.9g} {o[1]:.9g} {o[2]:.9g}" mass="{m:.9g}" fullinertia="{full}"/>'


def make_xml(payload_kg=0.0, with_env=True):
    r = ET.parse(URDF).getroot()
    L = {l.get("name"): l for l in r.findall("link")}
    J = {j.get("name"): j for j in r.findall("joint")}

    def jorig(n):
        return _f(J[n].find("origin").get("xyz"))

    def p(v):
        return f"{v[0]:.9g} {v[1]:.9g} {v[2]:.9g}"

    def corig(link):
        c = L[link].find("collision/origin")
        return _f(c.get("xyz")) if c is not None else [0, 0, 0]

    stems = {"link1": "link1", "link2": "link2", "link3": "link3", "link4": "link4", "link5": "link5",
             "gl": "gripper_left_palm", "gr": "gripper_right_palm"}
    parts = {k: sorted(os.path.basename(f)[:-4] for f in glob.glob(f"meshes/parts/{v}_*.stl")) for k, v in stems.items()}
    asset = "".join(f'<mesh name="{pn}" file="parts/{pn}.stl" scale="0.001 0.001 0.001"/>'
                    for ps in parts.values() for pn in ps)
    asset += '<mesh name="ladar" file="ladar.stl" scale="0.001 0.001 0.001"/>'

    class _Arm:
        def format(self, m, pos):
            return "".join(f'<geom type="mesh" mesh="{pn}" pos="{pos}" contype="1" conaffinity="1" rgba="0.3 0.3 0.35 1"/>'
                           for pn in parts[m])
    arm = _Arm()

    b1 = jorig("base_fixed")
    j1, j2, j3, j4 = jorig("joint1"), jorig("joint2"), jorig("joint3"), jorig("joint4")
    gl, gr = jorig("gripper_left_joint"), jorig("gripper_right_joint")
    lo, hi = -0.010, 0.019

    arm_xml = f"""
    <body name="link1" pos="{p(b1)}">
      {_inertial(L['link1'])}
      {arm.format('link1', p(corig('link1')))}
      <body name="link2" pos="{p(j1)}">
        <joint name="joint1" type="hinge" axis="0 0 1" limited="false"/>
        {_inertial(L['link2'])}
        {arm.format('link2', p(corig('link2')))}
        <body name="link3" pos="{p(j2)}">
          <joint name="joint2" type="hinge" axis="0 1 0" limited="false"/>
          {_inertial(L['link3'])}
          {arm.format('link3', p(corig('link3')))}
          <body name="link4" pos="{p(j3)}">
            <joint name="joint3" type="hinge" axis="0 1 0" limited="false"/>
            {_inertial(L['link4'])}
            {arm.format('link4', p(corig('link4')))}
            <body name="link5" pos="{p(j4)}">
              <joint name="joint4" type="hinge" axis="0 1 0" limited="false"/>
              {_inertial(L['link5'])}
              {arm.format('link5', p(corig('link5')))}
              <site name="tip" pos="{p(TIP_POS)}" size="0.003"/>
              <body name="payload" pos="{p(TIP_POS)}">
                <inertial pos="0 0 0" mass="{max(payload_kg, 1e-6):.9g}" diaginertia="1e-9 1e-9 1e-9"/>
              </body>
              <body name="gripper_l" pos="{p(gl)}">
                <joint name="grip_l" type="slide" axis="0 1 0" limited="true" range="{lo} {hi}"/>
                {_inertial(L['gripper_left_link'])}
                {arm.format('gl', p(corig('gripper_left_link')))}
              </body>
              <body name="gripper_r" pos="{p(gr)}">
                <joint name="grip_r" type="slide" axis="0 -1 0" limited="true" range="{lo} {hi}"/>
                {_inertial(L['gripper_right_link'])}
                {arm.format('gr', p(corig('gripper_right_link')))}
              </body>
            </body>
          </body>
        </body>
      </body>
    </body>"""

    env_xml = ""
    if with_env:
        eg = 'contype="2" conaffinity="1" rgba="0.8 0.6 0.2 0.35"'

        def box(name, xr, yr, zr):
            c = ((xr[0] + xr[1]) / 2, (yr[0] + yr[1]) / 2, (zr[0] + zr[1]) / 2)
            h = ((xr[1] - xr[0]) / 2, (yr[1] - yr[0]) / 2, (zr[1] - zr[0]) / 2)
            return f'<geom name="{name}" type="box" pos="{p(c)}" size="{p(h)}" {eg}/>'

        g = []
        for key, front in FRONTS.items():
            g.append(box(f"plate_{key}", (PLATE_X_REAR, front), PLATE_Y, PLATE_Z))
            g.append(box(f"body_{key}", (PLATE_X_REAR + 0.005, front - 0.005), PLATE_Y, BODY_Z))
        g.append(box("plate_stock", STOCK_X, PLATE_Y, PLATE_Z))
        g.append(box("body_stock", (STOCK_X[0], STOCK_X[1] - 0.008), PLATE_Y, BODY_Z))
        for s, nm in ((1, "wheel_l"), (-1, "wheel_r")):
            g.append(f'<geom name="{nm}" type="cylinder" pos="0 {s * WHEEL["y"]} {WHEEL["z"]}" '
                     f'zaxis="0 1 0" size="{WHEEL["r"]} {WHEEL["half_w"]}" {eg}/>')
            c = CASTER
            g.append(f'<geom name="caster_{nm[-1]}" type="box" pos="{c["pos"][0]} {s * c["pos"][1]} {c["pos"][2]}" '
                     f'size="{p(c["size"])}" {eg}/>')
        g.append(f'<geom name="lidar" type="mesh" mesh="ladar" pos="{p(LIDAR_POS)}" {eg}/>')
        env_xml = f'<body name="env">{"".join(g)}</body>' \
                  f'<geom name="floor" type="plane" pos="0 0 {FLOOR_Z}" size="2 2 0.1" contype="2" conaffinity="1" rgba="0.4 0.4 0.4 1"/>'

    return f"""<mujoco model="tb3_omx">
  <compiler angle="radian" meshdir="meshes" balanceinertia="true" boundmass="1e-6" boundinertia="1e-9" fusestatic="false" autolimits="false"/>
  <option gravity="0 0 -9.81"/>
  <asset>{asset}</asset>
  <worldbody>
    {env_xml}
    {arm_xml}
  </worldbody>
  <contact><exclude body1="link1" body2="link2"/><exclude body1="gripper_l" body2="gripper_r"/>{'<exclude body1="env" body2="link1"/>' if with_env else ''}</contact>
</mujoco>"""


def load(payload_kg=0.0, with_env=True):
    return mujoco.MjModel.from_xml_string(make_xml(payload_kg, with_env))


if __name__ == "__main__":
    m = load()
    print("nbody", m.nbody, "ngeom", m.ngeom, "nq", m.nq, "arm mass [kg] =", m.body_mass[m.body("link2").id:].sum().round(4))
