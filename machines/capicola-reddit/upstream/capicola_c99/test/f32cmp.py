"""Compare render outputs: double (reference) vs CC_F32. Usage: f32cmp.py REF.raw TEST.raw"""
import math, struct, sys
a = open(sys.argv[1], "rb").read(); b = open(sys.argv[2], "rb").read()
x = struct.unpack(f"<{len(a)//4}f", a); y = struct.unpack(f"<{len(b)//4}f", b)
nA = (48000 * 8 // 64) * 64
for name, lo, hi in (("A live", 0, nA), ("B play", nA, len(x))):
    sp = sum(v * v for v in x[lo:hi]); ep = sum((p - q) ** 2 for p, q in zip(x[lo:hi], y[lo:hi]))
    md = max(abs(p - q) for p, q in zip(x[lo:hi], y[lo:hi]))
    snr = 10 * math.log10(sp / ep) if ep else float("inf")
    worst = min((10 * math.log10(max(sum(v*v for v in x[s:s+48000]), 1e-30) / e) if (e := sum((p-q)**2 for p, q in zip(x[s:s+48000], y[s:s+48000]))) else 999, s // 48000) for s in range(lo, hi, 48000))
    print(f"{name}: {hi-lo} samples, max |diff| {md:.3g}, SNR {snr:.1f} dB, worst second {worst[0]:.1f} dB (second {worst[1]-lo//48000})")
