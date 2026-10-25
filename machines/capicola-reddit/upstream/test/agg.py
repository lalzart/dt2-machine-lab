# per-function cycle estimates per call from dt2trace_gen.py CYC=1 CYCPROF=... output
import sys, re, collections
tot = {'L': collections.Counter(), 'R': collections.Counter()}; side = None; n = collections.Counter()
for l in open(sys.argv[1]):
    m = re.match(r'\s+cyc (L|R):', l)
    if m: side = m.group(1); n[side] += 1; continue
    if 'by function:' in l and side:
        for k, v in re.findall(r'(\S+) (\d[\d,]*)(?=, |$)', l.split('by function:')[1].strip()):
            tot[side][k] += int(v.replace(',', ''))
for s in 'LR':
    if n[s]: print(s, n[s], 'calls, total %.0f; per call:' % (sum(tot[s].values()) / n[s]), ', '.join(f'{k} {v/n[s]:,.0f}' for k, v in tot[s].most_common(12)))
