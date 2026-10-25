"""Host-model checks (gen_host builds): uv run --with numpy python test/hostq.py <cmd> ...
  impurity BIN...        tonal impurity (dB, lower is cleaner) of the 5-partial tone, PLAY 0/1, several TUNE x stretch
  same BIN_A BIN_B       max |diff| of stereo output between two host builds over several configs
Record: test/rec_st.txt (voice L record, its params, voice R record, its params: the runner's build/gen_rec.txt
from a MACHINE=2 STEREO=1 run, its START 0 and END 48000). Tone: test/tone.i16 (110, 220, 277.18, 330, 440 Hz)."""
import numpy as np, subprocess, os, sys
Q = os.path.dirname(os.path.abspath(__file__))
fs = 48000; P0 = (110, 220, 277.18, 330, 440)
def run(binary, env, blocks=4600, stereo=False):
    e = dict(os.environ, **{k: str(v) for k, v in env.items()})
    if stereo: e['STEREO'] = '1'
    out = subprocess.run([binary, str(blocks), f'{Q}/rec_st.txt', f'{Q}/tone.i16'], capture_output=True, text=True, env=e).stdout
    rows = [l.split() for l in out.split('\n') if l.split()]
    return np.array([[np.frombuffer(bytes.fromhex(w)[::-1], '<f4')[0] for w in r] for r in rows], dtype=np.float64)
def impurity(y, pitch):
    seg = y[fs // 2: fs // 2 + 2 * fs]
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / fs)
    band = (f > 60) & (f < 6000); near = np.zeros_like(band)
    for p in P0: near |= np.abs(f - p * pitch) < 4
    return 10 * np.log10(sp[band & ~near].sum() / sp[band].sum())
cmd, bins = sys.argv[1], sys.argv[2:]
if cmd == 'impurity':
    cases = [(0, 0.5), (4, 1.0), (12, 0.5), (-5, 1.0), (7, 2.0), (0, 0.7)]
    for play in (0, 1):
        print(f"PLAY {play}   " + " ".join(f"{os.path.basename(b):>10}" for b in bins))
        for tune, st in cases:
            vals = [impurity(run(b, dict(HTUNE=tune, HSTRETCH=st, HEND=470000, HPLAY=play)).ravel(), 2 ** (tune / 12)) for b in bins]
            print(f"{tune:>4} x{st:<4}   " + " ".join(f"{v:10.1f}" for v in vals))
elif cmd == 'same':
    for env in ({}, {'RETRIG': '10,50,51,200'}, {'HTUNE': 7, 'RETRIG': '30,90'}, {'HTUNE': -5, 'HPLAY': 1},
                {'HTUNE': 4, 'HPLAY': 3, 'HEND': 20000}, {'HTUNE': 24, 'HSTRETCH': 0.6}, {'HTUNE': -7, 'HSTRETCH': 1.7, 'RETRIG': '40,41,300'}):
        a, b = run(bins[0], env, 600, True), run(bins[1], env, 600, True)
        print(env, 'max|diff| %.2e' % np.abs(a - b).max() if a.shape == b.shape else f'shapes {a.shape} {b.shape}', 'rms %.3f' % np.sqrt((b ** 2).mean()))
