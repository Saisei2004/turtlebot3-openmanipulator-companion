#!/usr/bin/env python3
# OpenCR からバッテリー電圧と状態を読む（tb3-bringup を止めているときだけ使える）
import time
from dynamixel_sdk import PortHandler, PacketHandler
p = PortHandler("/dev/ttyACM0"); p.openPort(); p.setBaudRate(1000000); time.sleep(1.5)
h = PacketHandler(2.0)
v, r, _ = h.read4ByteTxRx(p, 200, 42); pct, r2, _ = h.read4ByteTxRx(p, 200, 46)
st, r3, _ = h.read1ByteTxRx(p, 200, 18)
print(f"battery {v / 100:.2f} V ({h.getTxRxResult(r)}), {pct / 100:.0f} %, device_status {st}")
p.closePort()
