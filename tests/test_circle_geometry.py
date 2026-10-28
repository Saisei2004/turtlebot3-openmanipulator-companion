"""円の走行路の障害物判定を、既知の配置で確かめる（機体は動かさない）"""
import math
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pc", "server"))
import circle_driver as cd

R = 0.30


def ring(cx, cy, r, a0, a1, n=12):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / (n - 1)), cy + r * math.sin(a0 + (a1 - a0) * i / (n - 1))) for i in range(n)]


def check(name, pts, left, expect_block):
    n, near = cd.danger_points(pts, R, left)
    ok = (n >= cd.MIN_POINTS) == expect_block
    print(f"{'OK ' if ok else 'NG '} {name:44s} points in path {n:2d}  nearest arc {None if near is None else round(near, 2)} m")
    return ok


allok = True
# 左回り: 円の中心は (0, +0.30)。機体は円の一番手前（中心から見て真下）にいて、反時計回りに進む。
# 進行方向 = 機体の前（+x）。前に 0.4 m の壁（x=0.4、y が -0.15..0.15）
wall_front = [(0.40, y / 100) for y in range(-15, 16, 3)]
allok &= check("左回り: 真正面 0.40 m の壁", wall_front, True, True)
allok &= check("左回り: 真後ろ 0.40 m の壁", [(-0.40, y / 100) for y in range(-15, 16, 3)], True, False)
allok &= check("左回り: 円の中心（穴の中）の物", [(0.0, 0.30 + dy / 100) for dy in range(-6, 7, 3)] + [(dx / 100, 0.30) for dx in range(-6, 7, 3)], True, False)
allok &= check("左回り: 進路の外側 0.7 m の壁", [(0.0 + x / 100, -0.45) for x in range(-20, 21, 4)], True, False)
allok &= check("左回り: 円の上（反対側）0.6 m 先の物", [(x / 100, 0.60) for x in range(-5, 6, 2)], True, False)
# 左回りの前方斜め: 円弧上で 40° 先
a = -math.pi / 2 + math.radians(40)
allok &= check("左回り: 円弧の 40° 先の物", ring(R * math.cos(a), R + R * math.sin(a), 0.04, 0, 2 * math.pi), True, True)
a = -math.pi / 2 + math.radians(110)
allok &= check("左回り: 円弧の 110° 先（まだ遠い）の物", ring(R * math.cos(a), R + R * math.sin(a), 0.04, 0, 2 * math.pi), True, False)
# 機体自身（0.23 m 以内）は無視
allok &= check("機体の柱・電池（0.15 m 以内）", [(0.12, 0.05), (0.10, -0.05), (0.15, 0.0), (-0.1, 0.1)], True, False)
# 右回りは鏡像
allok &= check("右回り: 真正面 0.40 m の壁", wall_front, False, True)
allok &= check("右回り: 左側の物（反対側の円の中）", [(0.20, 0.30 + y / 100) for y in range(-5, 6, 2)], False, False)
# 2 点だけ（ノイズ）では止まらない
allok &= check("ノイズ 2 点", wall_front[:2], True, False)
print("ALL OK" if allok else "SOME FAILED")
raise SystemExit(0 if allok else 1)
