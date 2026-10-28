#!/usr/bin/env python3
# OpenCR (ID 200) とアーム関節 (ID 11-15) に問い合わせる。読むだけで動かさない
import time
from dynamixel_sdk import PortHandler, PacketHandler
p = PortHandler("/dev/ttyACM0"); p.openPort(); p.setBaudRate(1000000); time.sleep(2)
h = PacketHandler(2.0)
b, r, e = h.readTxRx(p, 200, 0, 12); print("ctrl0-11", list(b), h.getTxRxResult(r))
for i in range(11, 16):
    m, r, e = h.ping(p, i); print("ID", i, m, h.getTxRxResult(r))
p.closePort()
