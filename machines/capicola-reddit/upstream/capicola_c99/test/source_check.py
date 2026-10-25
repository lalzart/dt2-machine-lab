"""Checks source.c's outputs: kick onsets (timing follows stretch), the chord's
spectrum (pitch follows pitch), unity vs the input, retrigger and loop seams."""
import numpy as np

ld = lambda n: np.fromfile(f"src_{n}.raw", dtype="<f4")
x = ld("input")
FS = 48000


def onsets(y):
    env = np.convolve(np.abs(y), np.ones(96) / 96, mode="same")
    th = 0.5 * env.max()
    idx = np.flatnonzero((env[1:] >= th) & (env[:-1] < th))
    keep = [i for k, i in enumerate(idx) if k == 0 or i - idx[k - 1] > FS // 20]
    return np.array(keep) / FS


def peaks(y, lo=150, hi=600, n=3):
    seg = y[int(0.30 * FS):int(0.48 * FS)] if len(y) > FS // 2 else y
    w = np.hanning(len(seg))
    sp = np.abs(np.fft.rfft(seg * w, 1 << 17))
    f = np.fft.rfftfreq(1 << 17, 1 / FS)
    band = (f > lo) & (f < hi)
    fb, sb = f[band], sp[band]
    out = []
    for _ in range(n):
        k = np.argmax(sb); out.append(fb[k]); sb[max(0, k - 60):k + 60] = 0
    return sorted(round(v, 1) for v in out)


print("input onsets (s):", np.round(onsets(x), 3), " chord peaks (Hz):", peaks(x))
for name, s in (("unity", 1), ("slow", 0.5), ("fast", 2)):
    y = ld(name)
    print(f"{name:6s} onsets:", np.round(onsets(y), 3), f" expected spacing {0.5 / s:.3f} s")
for name, p in (("unity", 1), ("pitch", 1.5), ("pdown", 0.75)):
    y = ld(name)
    print(f"{name:6s} chord peaks:", peaks(y, 150 * p, 600 * p), f" expected {[round(v * p, 1) for v in (220, 277, 330)]}")
y = ld("unity")[:len(x)]
best = max(range(0, 8), key=lambda d: np.dot(x[:len(x) - 8], y[d:len(x) - 8 + d]))
e = y[best:best + len(x) - 8] - x[:len(x) - 8]
print(f"unity vs input: delay {best} samples, SNR {10 * np.log10(np.sum(x[:len(x) - 8] ** 2) / np.sum(e ** 2)):.1f} dB")
r = ld("retrig")
print("retrig onsets (s):", np.round(onsets(r), 3), " (a note every 0.25 s from the sample's start)")
lp = ld("loop")
print("loop onsets (s):", np.round(onsets(lp), 3), " (0.5 s loop)")

for L in (32, 16, 8):
    print(f"leash {L:3d}: slow onsets", np.round(onsets(ld(f"slow_l{L}")), 3), " fast onsets", np.round(onsets(ld(f"fast_l{L}")), 3))
