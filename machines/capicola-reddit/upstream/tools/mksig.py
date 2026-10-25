"""Write test/render.c's realistic test signal (1 s, float32 LE) to build/sig.f32
(test/dt2trace_gen.py's input)."""
import os
import math, struct
rng = 12345
def noise():
    global rng
    rng ^= (rng << 13) & 0xFFFFFFFF; rng ^= rng >> 17; rng ^= (rng << 5) & 0xFFFFFFFF
    return struct.unpack("<f", struct.pack("<f", rng / 4294967296.0))[0] * 2 - 1
x = []
for i in range(48000):
    t = i / 48000; tb = math.fmod(t, 0.5); th = math.fmod(t, 0.125)
    x.append(0.5 * math.exp(-tb * 20) * math.sin(2 * math.pi * (50 + 200 * math.exp(-tb * 40)) * tb)
             + 0.1 * math.exp(-th * 80) * noise()
             + 0.1 * (math.sin(2 * math.pi * 220 * t) + math.sin(2 * math.pi * 277 * t) + math.sin(2 * math.pi * 330 * t)))
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build", "sig.f32"), "wb").write(struct.pack("<48000f", *x))
