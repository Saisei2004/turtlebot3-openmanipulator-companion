#!/usr/bin/env python3
# OpenCR の制御テーブルを読むのにかかる時間を測る（tb3-bringup を止めてから使う）
import time
from dynamixel_sdk import PortHandler, PacketHandler
p = PortHandler("/dev/ttyACM0"); p.openPort(); p.setBaudRate(1000000); time.sleep(1.5)
h = PacketHandler(2.0)
def t(addr, n, reps=20):
    ok, ts = 0, []
    for _ in range(reps):
        a = time.perf_counter(); b, r, e = h.readTxRx(p, 200, addr, n); ts.append(time.perf_counter() - a); ok += (r == 0)
    ts.sort(); print(f"read addr {addr:3d} len {n:3d}: ok {ok}/{reps}  median {ts[len(ts)//2]*1000:6.1f} ms  max {ts[-1]*1000:6.1f} ms")
for addr, n in [(0, 4), (128, 16), (136, 8), (240, 32), (0, 128), (0, 256), (0, 340)]:
    t(addr, n)
# 書き込み（モーター電源 ON 状態のまま、トルクレジスタを同じ値で書き直すだけ）
p.closePort()
