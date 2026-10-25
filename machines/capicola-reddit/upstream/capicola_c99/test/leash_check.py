"""Pitch and level of leash_check.c's outputs: the chord's three peaks (should stay
220/277/330 Hz at any stretch) and the RMS against stretch 1."""
import numpy as np
FS = 48000


def peaks(y):
    seg = y[int(0.5 * FS):int(1.9 * FS)]
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 18))
    f = np.fft.rfftfreq(1 << 18, 1 / FS)
    band = (f > 150) & (f < 450)
    fb, sb = f[band], sp[band].copy()
    out = []
    for _ in range(3):
        k = np.argmax(sb); out.append(fb[k]); sb[max(0, k - 200):k + 200] = 0
    return sorted(round(v) for v in out)


for L in (8, 16, 32, 64, 128):
    ref = np.fromfile(f"lc_{L}_100.raw", "<f4")
    rr = np.sqrt(np.mean(ref[FS // 2:] ** 2))
    row = []
    for s in (50, 75, 100, 150, 200):
        y = np.fromfile(f"lc_{L}_{s}.raw", "<f4")
        lvl = 20 * np.log10(np.sqrt(np.mean(y[FS // 2:] ** 2)) / rr)
        row.append(f"s{s / 100:.2f}: {peaks(y)} {lvl:+.1f} dB")
    print(f"leash {L:3d} | " + " | ".join(row))
