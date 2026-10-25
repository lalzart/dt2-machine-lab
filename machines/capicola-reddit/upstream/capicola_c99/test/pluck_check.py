"""pluck_check.c's outputs against the ideal: the input resampled at the same rate
(band-limited, numpy FFT interpolation over the region played), best-delay
aligned; SNR overall and above 4 kHz."""
import numpy as np
FS = 48000
x = np.fromfile("pk_input.raw", "<f4").astype(np.float64)


def ideal(rate, n):
    # output sample k reads input position k * rate: band-limited interpolation
    m = int(n * rate) + 64
    seg = x[:m]
    spec = np.fft.rfft(seg)
    pos = np.arange(n) * rate
    # evaluate the band-limited signal at fractional positions via a windowed-sinc
    out = np.zeros(n)
    taps = np.arange(-32, 33)
    for k in range(n):
        p = pos[k]; i0 = int(np.floor(p)); fr = p - i0
        idx = i0 + taps
        ok = (idx >= 0) & (idx < len(seg))
        w = np.sinc(taps - fr) * np.hanning(67)[1:-1][: len(taps)] * (min(1.0, 1 / rate) if rate > 1 else 1.0)
        if rate > 1:
            w = np.sinc((taps - fr) / rate) / rate * np.hanning(67)[1:-1][: len(taps)]
        out[k] = np.dot(w[ok], seg[idx[ok]])
    return out


def hp(y, fc=4000):
    s = np.fft.rfft(y); f = np.fft.rfftfreq(len(y), 1 / FS); s[f < fc] = 0
    return np.fft.irfft(s, len(y))


for r in (80, 100, 125):
    y = np.fromfile(f"pk_{r}.raw", "<f4").astype(np.float64)
    n = 48000
    ref = ideal(r / 100, n + 16)
    best = max(range(0, 12), key=lambda d: np.dot(ref[:n], y[d:n + d]))
    yy = y[best:n + best]; rr = ref[:n]
    a = slice(4800, n)
    e = yy[a] - rr[a]
    snr = 10 * np.log10(np.sum(rr[a] ** 2) / np.sum(e ** 2))
    eh = hp(yy) - hp(rr)
    snr_h = 10 * np.log10(np.sum(hp(rr)[a] ** 2) / np.sum(eh[a] ** 2))
    print(f"rate {r / 100:.2f}: delay {best}, SNR {snr:5.1f} dB, above 4 kHz {snr_h:5.1f} dB")
