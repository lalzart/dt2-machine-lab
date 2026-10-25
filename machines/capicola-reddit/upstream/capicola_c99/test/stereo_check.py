"""stereo_check.c's outputs: L/R correlation, and the mid (L+R)/2 and side (L-R)/2
levels against the input's, from 0.5 s on."""
import numpy as np
FS = 48000


def stats(name):
    x = np.fromfile(name, "<f4").reshape(-1, 2)[FS // 2:]
    l, r = x[:, 0], x[:, 1]
    mid, side = (l + r) / 2, (l - r) / 2
    return np.corrcoef(l, r)[0, 1], np.sqrt(np.mean(mid ** 2)), np.sqrt(np.mean(side ** 2)), np.sqrt(np.mean(l ** 2))


ci, mi, si, li = stats("st_input.raw")
print(f"input        corr {ci:.3f}  mid {20 * np.log10(mi):6.1f} dBFS  side {20 * np.log10(si):6.1f}  L {20 * np.log10(li):6.1f}")
for s in (75, 100, 125, 160, 200):
    for tag in ("nolink", "link"):
        c, m, sd, l = stats(f"st_{tag}_{s}.raw")
        print(f"s{s / 100:<4} {tag:6s} corr {c:.3f}  mid {20 * np.log10(m / mi):+5.1f} dB  side {20 * np.log10(sd / si):+5.1f} dB  L {20 * np.log10(l / li):+5.1f} dB")

import os
if os.environ.get("SWEEPWIN"):   # correlation in 100 ms windows (the sweep runs)
    for s in (75, 100, 160):
        x = np.fromfile(f"st_link_{s}.raw", "<f4").reshape(-1, 2)
        w = FS // 10
        cs = [np.corrcoef(x[i:i + w, 0], x[i:i + w, 1])[0, 1] for i in range(0, len(x) - w, w)]
        print(f"s{s / 100:<4} link, 100 ms windows: min corr {min(cs):.3f}  windows below 0.9: {sum(c < 0.9 for c in cs)}/{len(cs)}")
