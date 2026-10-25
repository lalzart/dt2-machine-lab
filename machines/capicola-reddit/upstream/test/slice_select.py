"""slice_select.py: capi_select2.py with any encoders: TURNS_SPEC="2:1,2:1,6:1" turns
(encoder, delta) in order, a screenshot after each (encoder 2 = C, slot 2; 6 = G,
slot 6); the frame's words 0xde and 0xea (track 1's slots 2 and 6) printed at the end.

Select a machine on track 1 in digikit's ColdFire emulator the way
docs/findings/03-ui-and-panel.md found reliable: the FUNC+SRC chord early after
the boot400M snapshot (while the UI queue's backlog is small), then DOWN taps
and YES twice, with screenshots; then run on and turn encoder C.

Run from digikit's checkout (its ColdFire emulator), with a snapshot of the image
(python -m emu.extract SYX -o SECTIONS; python -m emu.checkpoint make 400000000 SNAPDIR/boot SYX):
  PYTHONPATH=.:tools DT2_SECTIONS=SECTIONS .venv/bin/python <repo>/test/slice_select.py SYX SECTIONS SNAP TYPE OUTDIR [CHORD_AT_M]
Env: POKES16=addr:val,... sets stored values (track 1's sound: CAPI at 0x42653336, BARS
0x42653342); PRESS_SRC=n presses SRC n times; CANVAS_AT=entry,exit dumps the canvas from a
graphic routine; WATCH_RANGES, COUNT_PCS, LOG_PCS for tracing.
"""
import os
import sys

sys.path.insert(0, "tools")
import machinecheck as mc  # noqa: E402

syx, sections, snap, mtype, out = sys.argv[1:6]
mtype = int(mtype)
chord_at = int(sys.argv[6]) * 1_000_000 if len(sys.argv) > 6 else 84_000_000
os.makedirs(out, exist_ok=True)
mc._lazy_imports()
os.environ["DT2_SECTIONS"] = sections
m, ev, st, pc, inq, at, pits, profile = mc.emucheck.setup(snap, syx)
import unicorn as _uc
_acc = []
_wcount = {}
for _r in (x for x in os.environ.get("WATCH_RANGES", "").split(",") if x):   # "lo:hi": any read or write of [lo, hi)
    _lo, _hi = (int(v, 0) for v in _r.split(":"))
    def _mcb(uc, access, addr, size, value, data, _lo=_lo):
        _wcount[_lo] = _wcount.get(_lo, 0) + 1
        if sum(1 for x in _acc if x[4] == _lo) < 4:
            _acc.append((access, addr, size, uc.reg_read(_uc.m68k_const.UC_M68K_REG_PC), _lo))
    m.uc.hook_add(_uc.UC_HOOK_MEM_READ | _uc.UC_HOOK_MEM_WRITE, _mcb, begin=_lo, end=_hi - 1)
n = [0]


def shot(name):
    buf = mc.panel.read(m, profile.fb_front)
    path = os.path.join(out, "%02d_%s.png" % (n[0], name))
    n[0] += 1
    if buf is not None:
        mc.panel.write_png(buf, path)
    print("png", path, flush=True)


def run(instrs):
    global pc
    pc, _d, stop = mc.spin(m, pc, instrs, pits=pits)
    if stop != "limit":
        print("STOPPED:", stop, flush=True)
        raise SystemExit(1)


done = 0
while done < 600_000_000:   # until the screen first lights up, then act at once
    run(5_000_000)
    done += 5_000_000
    buf = mc.panel.read(m, profile.fb_front)
    if buf and mc.emucheck.frame_on_fraction(buf) >= mc.emucheck.MAIN_SCREEN_ON_FRACTION:
        break
print("screen up at +%dM" % (done // 1_000_000), flush=True)
shot("screen_up")
for k in range(int(os.environ.get("DISMISS", "1"))):
    pc = mc.send(m, profile, mc.build_yes(), 2_000_000, pits, pc)
    run(4_000_000)
    shot("dismiss%d" % k)
pc = mc.send(m, profile, mc.build_func_src_chord(), 2_000_000, pits, pc)
run(6_000_000)
shot("after_chord")
for k in range(mc.derive_down_taps(mtype, 7)):   # short presses: auto-repeat starts ~1.9M after a press
    msgs = mc.build_down_taps(1)
    pc = mc.send(m, profile, msgs[:1], 500_000, pits, pc)
    pc = mc.send(m, profile, msgs[1:], 3_000_000, pits, pc)
run(6_000_000)
shot("after_down")
y = mc.build_yes()
pc = mc.send(m, profile, y[:1], 500_000, pits, pc)
pc = mc.send(m, profile, y[1:], 3_000_000, pits, pc)
run(6_000_000)
shot("yes1")
pc = mc.send(m, profile, y[:1], 500_000, pits, pc)
pc = mc.send(m, profile, y[1:], 3_000_000, pits, pc)
run(30_000_000)
shot("yes2")
print("track 1 type byte:", m.uc.mem_read(0x4265338E, 1)[0], flush=True)
run(int(os.environ.get("RUN_ON_M", "200")) * 1_000_000)
shot("later")
import unicorn as _uc
_logs = []
for _a in (int(x, 0) for x in os.environ.get("LOG_PCS", "").split(",") if x):   # log calls: return address and 6 stack args
    def _lcb(uc, addr, size, data, _a=_a):
        if sum(1 for x in _logs if x[0] == _a and x[2] == _phase[0]) < int(os.environ.get("LOG_N", "12")):
            sp = uc.reg_read(_uc.m68k_const.UC_M68K_REG_A7)
            ws = [int.from_bytes(bytes(uc.mem_read(sp + 4 * k, 4)), "big") for k in range(7)]
            _logs.append((_a, ws, _phase[0]))
    m.uc.hook_add(_uc.UC_HOOK_CODE, _lcb, begin=_a, end=_a)
_phase = ["page1"]
_canv = []
if os.environ.get("CANVAS_AT"):   # "entry,exit": at entry note the canvas (12(sp)); at exit dump it (once per phase)
    _ca, _cx = (int(x, 0) for x in os.environ["CANVAS_AT"].split(","))
    def _ce(uc, addr, size, data):
        sp = uc.reg_read(_uc.m68k_const.UC_M68K_REG_A7)
        _canv.append(["pending", int.from_bytes(bytes(uc.mem_read(sp + 12, 4)), "big"), _phase[0]])
    def _cxh(uc, addr, size, data):
        if _canv and _canv[-1][0] == "pending" and sum(1 for c in _canv if c[0] == "done" and c[2] == _phase[0]) < 1:
            cv = _canv[-1][1]
            w_, h_, wpc_, d_ = (int.from_bytes(bytes(uc.mem_read(cv + o, 4)), "big") for o in (4, 8, 12, 16))
            raw = bytes(uc.mem_read(d_, 4 * wpc_ * w_))
            _canv[-1] = ["done", cv, _phase[0], w_, h_, wpc_, raw]
    m.uc.hook_add(_uc.UC_HOOK_CODE, _ce, begin=_ca, end=_ca)
    m.uc.hook_add(_uc.UC_HOOK_CODE, _cxh, begin=_cx, end=_cx)
_hits = {}
for _a in (int(x, 0) for x in os.environ.get("COUNT_PCS", "").split(",") if x):   # count calls of these addresses
    _hits[_a] = 0
    def _cb(uc, addr, size, data, _a=_a):
        _hits[_a] += 1
    m.uc.hook_add(_uc.UC_HOOK_CODE, _cb, begin=_a, end=_a)
if _hits:
    for _w in range(int(os.environ.get("COUNT_WINDOWS", "3"))):
        before = dict(_hits)
        run(10_000_000)
        print("count window %d (10M instr): " % _w + ", ".join("%#x %d" % (a, _hits[a] - before[a]) for a in _hits), flush=True)
for k, spec in enumerate(x for x in os.environ.get("POKES16", "").split(",") if x):   # "addr:value": a halfword, then a screenshot
    a_, v_ = (int(x, 0) for x in spec.split(":"))
    print("poke %#x: was %#06x, now %#06x" % (a_, int.from_bytes(bytes(m.uc.mem_read(a_, 2)), "big"), v_), flush=True)
    m.uc.mem_write(a_, v_.to_bytes(2, "big"))
    run(20_000_000)
    shot("poke%d_%x_%x" % (k, a_, v_))
if os.environ.get("PRESS_SRC"):   # SRC again: the waveform view
    for k in range(int(os.environ["PRESS_SRC"])):
        _phase[0] = "src%d" % (k + 1)
        pc = mc.send(m, profile, [(mc.SRC_CH, 1 << mc.SRC_BIT)], 500_000, pits, pc)   # press, then release (as the DOWN taps)
        pc = mc.send(m, profile, [(mc.SRC_CH, 0)], 3_000_000, pits, pc)
        run(30_000_000)
        shot("src%d" % (k + 1))
for k, spec in enumerate(x for x in os.environ.get("TURNS_SPEC", "2:1").split(",") if x):
    enc, delta = (int(v) for v in spec.split(":"))
    pc = mc.panelin.encoder(m, profile, enc, delta)
    run(20_000_000)
    shot("turn%d_e%d" % (k, enc))
    if _hits:
        print("after turn %d: " % k + ", ".join("%#x %d" % (a, _hits[a]) for a in _hits), flush=True)
shot("turned")
for k in range(int(os.environ.get("AFTER", "0"))):
    run(7_000_000)
    shot("after%d" % k)
prof = mc.resolve_frame_profile(os.path.join(sections, [f for f in os.listdir(sections) if "MAIN_OS" in f][0]),
                                {"vector": 191, "handler": 0x4002DD0C, "driver": 0x400CD2BC, "counter": 0x402A1488, "gate": 0x409664F4})
m.uc.mem_write(prof["gate"], bytes(4))
ok, calls = mc.capture_frame(m, prof)
frame = bytes(m.uc.mem_read(0x80005348, 0x800))
open(os.path.join(out, "frame.bin"), "wb").write(frame)
print("frame captured ok=%r, driver calls=%d" % (ok, len(calls)), flush=True)
for c in _canv:
    if c[0] != "done": continue
    _, cv, ph, w_, h_, wpc_, raw = c
    for order in (0, 1):   # which of a column's words is the top
        rows = []
        for yy in range(h_):
            line = ""
            for xx in range(w_):
                k = (yy // 32) if order == 0 else (wpc_ - 1 - yy // 32)
                wd = int.from_bytes(raw[4 * (wpc_ * xx + k):4 * (wpc_ * xx + k) + 4], "big")
                line += "#" if (wd >> (yy % 32)) & 1 else "."
            rows.append(line)
        with open(os.path.join(out, "canvas_%s_order%d.txt" % (ph, order)), "w") as fh:
            fh.write("\n".join(rows) + "\n")
    print("canvas %#x (%dx%d, %d words a column) dumped at phase %s" % (cv, w_, h_, wpc_, ph), flush=True)
for _a, ws, ph in _logs:
    print("call %#x [%s]: ret %#x args %s" % (_a, ph, ws[0], " ".join("%#x" % w for w in ws[1:])), flush=True)
if os.environ.get("WATCH_RANGES"):
    print("watched accesses per range: " + ", ".join("%#x %d" % kv for kv in sorted(_wcount.items())) +
          "".join("\n   %s %#x size %d pc %#x" % ("W" if a == _uc.UC_MEM_WRITE else "R", ad, sz, pc_) for a, ad, sz, pc_, _ in _acc), flush=True)
import struct as _st
print("frame words: type %#x slot2 %#x slot6 %#x" % (_st.unpack_from(">H", frame, 0x94)[0], _st.unpack_from(">H", frame, 0xDE)[0],
                                                  _st.unpack_from(">H", frame, 0xEA)[0]), flush=True)
print("done", flush=True)
