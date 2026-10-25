"""quality_check.c's outputs: for the tonal sample, the energy outside the five
partials (+-4 Hz) against the total, 60 Hz..6 kHz, in dB (lower is cleaner; the
input itself is the floor); for the drum sample, the kick onsets' worst timing
error against k * 0.25 / stretch, in ms."""
import numpy as np
FS = 48000
import os
P = tuple(f * float(os.environ.get('QC_PITCH', '1')) for f in (110, 220, 277.18, 330, 440))


def impurity(y):
    seg = y[FS // 2: FS // 2 + 2 * FS]
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / FS)
    band = (f > 60) & (f < 6000)
    near = np.zeros_like(band)
    for p in P:
        near |= np.abs(f - p) < 4
    return 10 * np.log10(sp[band & ~near].sum() / sp[band].sum())


def onset_err(y, s):
    """Each expected kick at k * 0.25 / s (from the output's first onset): the
    nearest rise through 30% of the peak envelope within half a period."""
    env = np.convolve(np.abs(y), np.ones(96) / 96, mode="same")
    th = 0.3 * env.max()
    rises = np.flatnonzero((env[1:] >= th) & (env[:-1] < th)) / FS
    if len(rises) < 2:
        return float("nan")
    per = 0.25 / s
    t0 = rises[0]
    errs = []
    for k in range(1, int((len(y) / FS - t0) / per)):
        e = t0 + k * per
        near = rises[np.abs(rises - e) < per / 2]
        errs.append(np.min(np.abs(near - e)) if len(near) else per / 2)
    return 1000 * max(errs)


import sys
cfgs = tuple(int(x) for x in sys.argv[1:]) or (8, 32, 128, -480, -960, -1920, -2880)
st = (50, 80, 125, 160, 200, 300)
print("impurity dB (tonal)        " + "  ".join(f"s{s / 100:<4}" for s in st))
for c in cfgs:
    row = [impurity(np.fromfile(f"qc_tonal_{c}_{s}.raw", "<f4")) for s in st]
    print(f"  {'kf ' + str(c) if c > 0 else 'time ' + str(-c):12s}  " + "  ".join(f"{v:6.1f}" for v in row))
print("worst kick timing error ms (drum)")
for c in cfgs:
    row = [onset_err(np.fromfile(f"qc_drum_{c}_{s}.raw", "<f4"), s / 100) for s in st]
    print(f"  {'kf ' + str(c) if c > 0 else 'time ' + str(-c):12s}  " + "  ".join(f"{v:6.1f}" for v in row))
