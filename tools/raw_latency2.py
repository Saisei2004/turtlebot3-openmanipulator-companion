#!/usr/bin/env python3
# OpenCR への ping / read / 書き込み(同じ値)それぞれの往復時間を生の通信で測る（tb3-bringup を止めてから使う）
import time, serial, struct
s = serial.Serial("/dev/ttyACM0", 1000000, timeout=0); time.sleep(1.5)
T = []
for i in range(256):
    c = i << 8
    for _ in range(8): c = ((c << 1) ^ 0x8005) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    T.append(c)
def crc(d):
    a = 0
    for b in d: a = ((a << 8) ^ T[((a >> 8) ^ b) & 0xFF]) & 0xFFFF
    return a
def pkt(inst, params):
    body = bytes([0xFF, 0xFF, 0xFD, 0x00, 200]) + struct.pack("<H", len(params) + 3) + bytes([inst]) + params
    return body + struct.pack("<H", crc(body))
def rt(p, reps=25):
    ts = []
    for _ in range(reps):
        s.reset_input_buffer(); t0 = time.perf_counter(); s.write(p); got = b""
        while time.perf_counter() - t0 < 0.3:
            got += s.read(512)
            if len(got) >= 11 and len(got) >= 7 + struct.unpack("<H", got[5:7])[0]: break
        ts.append((time.perf_counter() - t0, len(got))); time.sleep(0.01)
    ts.sort(); return f"median {ts[len(ts)//2][0]*1000:5.1f} ms  max {ts[-1][0]*1000:5.1f} ms  reply {ts[len(ts)//2][1]}B"
print("ping            ", rt(pkt(1, b"")))
print("read 0..4       ", rt(pkt(2, struct.pack("<HH", 0, 4))))
print("read 0..344     ", rt(pkt(2, struct.pack("<HH", 0, 344))))
print("write heartbeat ", rt(pkt(3, struct.pack("<H", 19) + b"\x01")))
print("write led       ", rt(pkt(3, struct.pack("<H", 20) + b"\x00")))

# ---- 続けて送ったときの 1 回あたりの時間（間隔を変えて）----
def burst(gap, n=40):
    p = pkt(2, struct.pack("<HH", 0, 4)); t_start = time.perf_counter(); per = []
    for _ in range(n):
        s.reset_input_buffer(); t0 = time.perf_counter(); s.write(p); got = b""
        while time.perf_counter() - t0 < 0.3:
            got += s.read(512)
            if len(got) >= 15: break
        per.append(time.perf_counter() - t0)
        if gap: time.sleep(gap)
    total = time.perf_counter() - t_start; per.sort()
    print(f"gap {gap*1000:4.0f} ms: round trip median {per[len(per)//2]*1000:5.1f} ms, min {per[0]*1000:5.1f}, max {per[-1]*1000:5.1f} | throughput {n/total:5.1f} /s")
for g in (0, 0.002, 0.005, 0.01, 0.02):
    burst(g)
