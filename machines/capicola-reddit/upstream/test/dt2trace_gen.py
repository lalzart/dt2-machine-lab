"""Capicola's generators (capicola_c99/sharc/dt2gen.c) inside the real DT2 frame
chain, in digikit's runner (OS 1.16 and 1.17 share the DSP image).

Run from digikit's checkout (its runner; DIGIKIT, by default
DT2_WORKSPACE/work/digikit), after tools/build_gen.sh and tools/mksig.py:
    cd $DIGIKIT && uv run --quiet python <repo>/test/dt2trace_gen.py [FRAMES]

build/dt2gen.dxe is added to section 7 as extra boot blocks and the
dispatch's STRETCH call (sw 0x1c6af1, `cjump 0x1c5576 (db)`) is retargeted to
cc_dt2_entry, as build_s3.py does for the instrument. Voice 0 plays the
realistic test signal (build/sig.f32 as int16) as a STRETCH track with the
page the instrument reported, at 120 BPM. Per call: the instructions spent in
our code and the 32 outputs; at the first call the voice and parameter records
go to build/gen_rec.txt, and build/gen_host replays them for comparison.
"""
import os
import shutil
import struct
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "tools")   # digikit's (the cwd)
sys.path.insert(0, os.path.join(REPO, "firmware"))
import build as probe  # noqa: E402  (puts dnfw on sys.path)
import sec7  # noqa: E402
import sharcldr  # noqa: E402
import sharc_harness as H  # noqa: E402
import sharc_survey as sv  # noqa: E402
import sharc_trace as st  # noqa: E402
from dnfw.image import bootstream, sharc_object  # noqa: E402

BUILD = os.path.join(REPO, "build")   # tools/build_gen.sh's outputs
OUT = os.environ.get("GEN_OUT") or BUILD   # this run's files (gen_sample, gen_rec, gen_out_*): one folder per parallel run
os.makedirs(OUT, exist_ok=True)
IMAGE = "dt2-1.16"   # digikit's name for the DSP image; 1.17's is the same
STOCK7 = os.path.join(BUILD, "stock_section7.bin")   # the stock image's section 7 (firmware: never commit)
if not os.path.exists(STOCK7):
    from dnfw.cli.files import read_image  # noqa: E402
    from dnfw.firmware.load import load  # noqa: E402
    open(STOCK7 + f".{os.getpid()}", "wb").write(load(read_image(probe.STOCK)).container.find(sec7.SECTION7).unpack())
    os.replace(STOCK7 + f".{os.getpid()}", STOCK7)   # (parallel runs: whole or absent)
FRAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 12
CALL_SW, STOCK_TARGET = 0x1C6AF1, 0x1C5576
SHARED_SW, SHARED_TARGET = 0x1C6B00, 0x1C4ECF
MACHINE = int(os.environ.get("MACHINE", "2"))
NOPATCH = bool(os.environ.get("NOPATCH"))
PARAM_RECORDS, TYPE_OFF = 0x2506EC, 0x4C
PAGES = (0x264220, 0x265220)
PAGE = ("4000 0300 0000 0053 0000 5300 0000 7800 0000 6400 0000 0000 0000 0000 0000 0000 "
        "0000 7f00 0000 4000 0000 0000 4000 0000 4000 0000 0000 7f00 0000 0000 0000 0000 "
        "7f00 4000 7f00 2000 0000 6500 0000 4000 6e00 0000 0100 0000 0000 0000 0000 0000").split()
TEMPO = int(os.environ.get("BPM", "120")) * 120
TUNE = int(os.environ.get("TUNE", "0"))
PLAYMODE = os.environ.get("PLAY")   # the SRC page's PLAY (0..3), frame word 0xdc + 0x60 * track

BUILT = os.environ.get("BUILT")   # a finished section 7 (build_cap.py --section7-out): run it as is
d = open(os.environ.get("DXE") or f"{BUILD}/{'dt2gen_l1' if BUILT else 'dt2gen'}.dxe", "rb").read()
phoff = struct.unpack_from("<I", d, 0x1C)[0]
phentsize, phnum = struct.unpack_from("<HH", d, 0x2A)
shoff = struct.unpack_from("<I", d, 0x20)[0]
shentsize, shnum = struct.unpack_from("<HH", d, 0x2E)
secs = [struct.unpack_from("<IIIIIIIIII", d, shoff + i * shentsize) for i in range(shnum)]
symtab = [s for s in secs if s[1] == 2][0]
strs = secs[symtab[6]]
syms = {}
for k in range(symtab[5] // 16):
    n_, val = struct.unpack_from("<II", d, symtab[4] + 16 * k)
    o = strs[4] + n_
    syms[d[o:d.index(b"\0", o)].decode()] = val
ENTRY = syms["cc_dt2_entry."] if MACHINE == 2 else syms["cc_dt2_rp_entry."]
OURS = (2, 3, 4, 6)   # the page's machine types our entries take: STRETCH, REPITCH, GRID, SLICE
import bisect, collections  # noqa: E401,E402
FUNCS = sorted((v, n) for n, v in syms.items() if n.endswith(".") and not n.startswith((".", "_")) and (0xBC0000 <= v < 0xC00000 or 0x16B000 <= v < 0x170000))
FSTART = [a for a, _ in FUNCS]
PROF = os.environ.get("PROF")
prof = [collections.Counter() for _ in range(FRAMES)]
blocks, code_lo, code_hi = b"", None, None
code_ranges = []   # every loadable code segment: L1, and L2's cold code (l1l2.ldf)
for i in range(phnum):
    typ, off, vaddr, paddr, filesz = struct.unpack_from("<IIIII", d, phoff + i * phentsize)
    if typ != 1 or not filesz:
        continue
    raw = d[off:off + filesz]
    code_lo, code_hi = vaddr, vaddr + filesz // 2
    code_ranges.append((code_lo, code_hi))
    if 0xB80000 <= vaddr < 0xC00000:
        blocks += bootstream.block(0x20000000 + 2 * (vaddr - 0xB80000), sharc_object.load_bytes(raw))
    else:
        blocks += bootstream.block(vaddr, raw)
s7 = bytearray(open(BUILT, "rb").read() if BUILT else bootstream.insert_before_final(open(STOCK7, "rb").read(), blocks))
for site, stock, target in ((CALL_SW, STOCK_TARGET, syms["cc_dt2_entry."]), (SHARED_SW, SHARED_TARGET, syms["cc_dt2_rp_entry."])):
    if NOPATCH or BUILT:
        break
    at = sec7.sw_to_load(site)
    w0, w1, w2 = struct.unpack("<HHH", bootstream.read_span(bytes(s7), at, 6))
    insn = (w0 << 32) | (w1 << 16) | w2
    assert (insn >> 24) & 0xFFFFFF == 0x180400 and insn & 0xFFFFFF == stock, hex(insn)
    new = (insn & ~0xFFFFFF) | target
    bootstream.write_span(s7, at, struct.pack("<HHH", new >> 32, (new >> 16) & 0xFFFF, new & 0xFFFF))


def in_code(pc):
    for lo_, hi_ in code_ranges:
        if lo_ <= pc < hi_:
            return True
    return False


print(f"machine {MACHINE}; watching entry {ENTRY:#x}; our code sw {code_lo:#x}-{code_hi:#x}; " + ("stock (no patch)" if NOPATCH else f"built image {BUILT}" if BUILT else "both call sites retargeted"))

dst = os.path.join("out", "sections", IMAGE, "section_7_BLOB.bin")
if not os.path.exists(dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(STOCK7, dst)
memory = sharcldr.LoadedMemory.from_stream(bytes(s7))
t0 = time.time()
init = H.run_init(memory, IMAGE)
print(f"run_init: ran={init.ran} ({time.time() - t0:.0f} s)")
runner = init.runner
state = runner.state
sig = struct.unpack("<48000f", open(f"{BUILD}/sig.f32", "rb").read())
if os.environ.get("SINE"):   # a steady 1 kHz sine at half scale, for level comparisons
    import math
    sig = [0.5] * 48000 if os.environ["SINE"] == "dc" else [0.5 * math.sin(2 * math.pi * float(os.environ["SINE"]) * n / 48000) for n in range(48000)]
i16 = [max(-32768, min(32767, round(v * 32767))) for v in sig]
SDDR = bool(os.environ.get("SDDR"))   # the samples in DDR at the device's sample base (COST runs)
SBASE = 0x8422B9E8 if SDDR else 0x310000
H._write_samples(state, SBASE, [v / 32768 for v in i16], "int16")
open(f"{OUT}/gen_sample.i16", "wb").write(struct.pack(f"<{len(i16)}h", *i16))
TRACK = int(os.environ.get("TRACK", "0"))   # the machine's track: voices 2t (L) and 2t+1 (R), both gated on
record = H.setup_voice(state, IMAGE, 2 * TRACK, sample_len=48000, pitch_step=1.0, sample_base=SBASE)
STEREO = bool(os.environ.get("STEREO"))   # the right voice gets its own sample: the signal from 1000 samples on
if STEREO:
    i16_r = i16[1000:] + i16[:1000]
    H._write_samples(state, SBASE + 0x20000, [v / 32768 for v in i16_r], "int16")
    blob = struct.pack(f"<{len(i16)}h", *i16) + bytes(0x20000 - 2 * len(i16)) + struct.pack(f"<{len(i16_r)}h", *i16_r)
    open(f"{OUT}/gen_sample.i16", "wb").write(blob)
record_r = H.setup_voice(state, IMAGE, 2 * TRACK + 1, sample_len=48000, pitch_step=1.0,
                         sample_base=SBASE + 0x20000 if STEREO else SBASE)
for v_ in (2 * TRACK, 2 * TRACK + 1):
    H._poke(state, PARAM_RECORDS + v_ * 0xDC + TYPE_OFF, MACHINE)
if os.environ.get("IDLE"):   # both voices inactive: the early-return path
    for rec_ in (record, record_r):
        H._poke(state, rec_ + 0x1B8, 0, width=1)
CYC = bool(os.environ.get("CYC"))     # estimated device cycles per call (cyc_step below)
CYCPROF = [int(x) for x in os.environ.get("CYCPROF", "").split(",") if x]   # frames to break down by function
CYCPC = os.environ.get("CYCPC")   # "lo,hi": print the costliest instructions in [lo, hi) over the run
cyc_pc = collections.Counter()
COST = bool(os.environ.get("COST")) or CYC   # count our code's DDR accesses per call
import re as _re
import sharcfn as _sharcfn
_cyc_cache, _cyc_texts = {}, {}


def _cyc_info(nr, pc):
    info = _cyc_cache.get(pc)
    if info is None:
        insn = nr._decode(pc)
        txt = _sharcfn.render_instruction(pc, insn, nr.data, set(), collections.Counter(), [])[0]
        _cyc_texts[pc] = txt
        iw = set(int(x) for x in _re.findall(r"\bI(\d+)\s*=(?!=)", txt))
        iu = set()
        for inner in _re.findall(r"(?:DM|PM)\(([^)]*)\)", txt):
            iu |= set(int(x) for x in _re.findall(r"\bI(\d+)", inner))
        iu |= set(int(x) for x in _re.findall(r"JUMP\s*\(\s*M\d+\s*,\s*I(\d+)", txt, _re.I))
        is_call = bool(_re.search(r"\bCALL\b", txt, _re.I))
        is_ret = bool(_re.search(r"\bRTS\b|\bRETURN\b", txt))
        if _re.search(r"\bRETURN\b", txt):
            iu.add(12)   # selcc's return: JUMP (M14, I12) (DB), I12 loaded just before
        m = _re.search(r"\bF(\d+)\s*=\s*fmul\(", txt)
        fmul = int(m.group(1)) if m else None
        fread = set(int(x) for x in _re.findall(r"(?<![=\w])\s*F(\d+)\b(?!\s*=[^=])", txt))
        info = (insn.length_bytes // 2 if insn.length_bytes else 1, iw, iu, is_call, is_ret, fmul, fread)
        _cyc_cache[pc] = info
    return info


cyc = {"step": 0, "iw_at": {}, "prev": None, "fmul": None, "acc": 0, "parts": collections.Counter()}


def cyc_step(nr, pc):
    """The device cost of the instruction at pc (ubench measurements, 2026-10-01):
    1 a cycle; +4 for an I register used to address within 1 instruction of its
    write (+3, +2, +1 at 2, 3, 4); +2 for a taken branch; +6 for a CALL and +6 for
    a return; +2 for an F register read right after a multiply wrote it. L1
    block 1 and DDR accesses are added from watchpoints per call."""
    w, iw, iu, is_call, is_ret, fmul, fread = _cyc_info(nr, pc)
    cyc["step"] += 1
    c = 1
    for i in iu:
        at = cyc["iw_at"].get(i)
        if at is not None:
            d = cyc["step"] - at
            if 1 <= d <= 4:
                c += 5 - d
                cyc["parts"]["dag"] += 5 - d
    prev = cyc["prev"]
    if prev is not None and pc != prev[0] + prev[1]:
        c += 2
        cyc["parts"]["taken"] += 2
    if is_call:
        c += 6
        cyc["parts"]["call"] += 6
    if is_ret:
        c += 6
        cyc["parts"]["ret"] += 6
    if cyc["fmul"] is not None and cyc["fmul"] in fread:
        c += 2
        cyc["parts"]["fdep"] += 2
    for i in iw:
        cyc["iw_at"][i] = cyc["step"]
    cyc["fmul"] = fmul
    cyc["prev"] = (pc, w)
    cyc["acc"] += c
    if CYCPC:
        cyc_pc[pc] += c
    if CYCPROF:
        cyc["fn"][FUNCS[bisect.bisect_right(FSTART, pc) - 1][1] if FSTART and pc >= FSTART[0] else "?"] += c
cost_rows = []
cyc_rows = []
print(f"track {TRACK}: records {record:#x} (L), {record_r:#x} (R)")
FWLOAD = os.environ.get("FWLOAD")   # load a stereo sample through the firmware: slot table + trig, no record pokes
FW_SLOT, FW_BASE, FW_L, FW_R = 0x101, 0x8422B9C8, 0x20, 0x20 + 0x20000
TRIGF = int(os.environ.get("TRIGF", "1"))
if FWLOAD:
    i16_r = i16[1000:] + i16[:1000] if FWLOAD != "neg" else [-v for v in i16]
    for base_, data_ in ((FW_BASE + FW_L, i16), (FW_BASE + FW_R, i16_r)):
        for k_ in range(0, len(data_), 2):
            H._poke(state, base_ + 2 * k_, (data_[k_] & 0xFFFF) | ((data_[k_ + 1] & 0xFFFF) << 16))
    sl_ = 0x257810 + FW_SLOT * 0x14
    for k_, w_ in enumerate((FW_L, FW_R, 2 * len(i16), 48000)):
        H._poke(state, sl_ + 4 * k_, w_)
    H._poke(state, sl_ + 16, 1, width=1)
    for rec_ in (record, record_r):   # forget the hand pokes: the firmware must write these
        H._poke(state, rec_, 0)
        H._poke(state, rec_ + 0x1B8, 0, width=1)
    print(f"FWLOAD: slot {FW_SLOT:#x} stereo, L at {FW_BASE + FW_L:#x}, R at {FW_BASE + FW_R:#x}, trig at frame {TRIGF}")
H.setup_frame(state, IMAGE, command=3)
for pg in PAGES:
    H._poke(state, pg + 0x94 + 2 * TRACK, MACHINE, width=2)
    for i, w_ in enumerate(PAGE):
        H._poke(state, pg + 0xDA + 0x60 * TRACK + 2 * i, int(w_, 16), width=2)
    H._poke(state, pg + 0xDA + 0x60 * TRACK, (0x40 + TUNE) << 8, width=2)
    if os.environ.get("STRT"):   # STRT (frame word 0xe6), raw page value
        H._poke(state, pg + 0xE6 + 0x60 * TRACK, int(os.environ["STRT"], 0), width=2)
    if PLAYMODE is not None:
        H._poke(state, pg + 0xDC + 0x60 * TRACK, int(PLAYMODE) << 8, width=2)
    if os.environ.get("CAPI"):   # the SRC page's slot 2 (0..127), as the ColdFire patch sends it
        H._poke(state, pg + 0xDE + 0x60 * TRACK, int(os.environ["CAPI"]) << 8, width=2)
    if os.environ.get("LEV"):
        H._poke(state, pg + 0xEC + 0x60 * TRACK, int(os.environ["LEV"]) << 8, width=2)
    for pw_ in (x for x in os.environ.get("POKE", "").split(",") if x):   # "off:value": a raw SRC page halfword (0xea = slot 6)
        o_, v_ = (int(x, 0) for x in pw_.split(":"))
        H._poke(state, pg + o_ + 0x60 * TRACK, v_, width=2)
    H._poke(state, pg + 0xD8, TEMPO, width=2)
    H._poke(state, pg + 0x73C, 1, width=2)
    if FWLOAD:
        H._poke(state, pg + 0xE0 + 0x60 * TRACK, FW_SLOT, width=2)


def words(s, base, n):
    out = []
    for k in range(n):
        v = st._dm_read(s, base + 4 * k, 4)
        out.append(v.value & 0xFFFFFFFF if v is not None and getattr(v, "value", None) is not None else 0)
    return out


outs, costs, dumped = [], [], False
entry_i7, stack_lo = {}, {}   # STACKMIN: per voice, the stack pointer at our entry and the lowest stack address touched
outs_r = []
outs_now = outs
RETRIG = [int(x) for x in os.environ.get("RETRIG", "").split(",") if x]
for f in range(FRAMES):
    if f in RETRIG:   # a trig: the firmware seeds PHASE at START (w66/w67), on both voices of the track
        for rec_ in (record, record_r):
            w = words(runner.state, rec_, 0x70)
            H._poke(runner.state, rec_ + 4 * 0x6C, w[0x66])
            H._poke(runner.state, rec_ + 4 * 0x6D, w[0x67])
    if FWLOAD:
        for pg in PAGES:
            H._poke(runner.state, pg + 0x22, 0x0101 if f == TRIGF else 0, width=2)
    if os.environ.get("TUNE2"):   # "frame:value": TUNE changes at that frame (both pages)
        f2_, t2_ = (int(x) for x in os.environ["TUNE2"].split(":"))
        if f == f2_:
            for pg in PAGES:
                H._poke(runner.state, pg + 0xDA + 0x60 * TRACK, (0x40 + t2_) << 8, width=2)
    if os.environ.get("SHOWTUNE"):
        f32t_ = lambda w: struct.unpack("<f", struct.pack("<I", w))[0]  # noqa: E731
        pl_ = words(runner.state, PARAM_RECORDS + 2 * TRACK * 0xDC, 1)[0]
        pr_ = words(runner.state, PARAM_RECORDS + (2 * TRACK + 1) * 0xDC, 1)[0]
        tl_ = words(runner.state, 0x9E000000 + 2 * TRACK * 0x5000, 7)[6]
        tr_ = words(runner.state, 0x9E000000 + (2 * TRACK + 1) * 0x5000, 7)[6]
        print(f"   frame {f} before: TUNE param L {f32t_(pl_):.5f} R {f32t_(pr_):.5f}; trigs L {tl_} R {tr_}")
    nr = runner.fresh_call(H.profile(IMAGE).block_handler, diagnose_unknown=True)
    calls = []
    orig = nr.step

    def step(orig=orig, nr=nr, calls=calls):
        global dumped
        pc = nr.state.pc_sw
        if (pc == ENTRY and not (calls and len(calls[-1]) == 3)) or (pc in (STOCK_TARGET, SHARED_TARGET) and (NOPATCH or MACHINE not in OURS) and not calls):
            r4 = nr.state.uregs.get(sr_codes["R4"]).value
            r8 = nr.state.uregs.get(sr_codes["R8"]).value
            if os.environ.get("FORCESE") and r4 in (record, record_r):   # "start,end": both records' START/END (whole
                s_, e_ = (int(x) for x in os.environ["FORCESE"].split(","))   # samples, Q31) at our entry: SLICE without slices
                for rec_ in (record, record_r):   # (both: the left voice's stereo pass compares them)
                    for w_, v_ in ((0x66, s_), (0x68, e_)):
                        H._poke(nr.state, rec_ + 4 * w_, (v_ & 1) << 31)
                        H._poke(nr.state, rec_ + 4 * (w_ + 1), v_ >> 1)
            calls.append([r4, r8, 0])
            entry_i7[r4] = nr.state.uregs.get(sr_codes["I7"]).value
            if os.environ.get("SHOWPAIR") and r4 in (record, record_r):   # the right record as each voice of the pair sees it
                wr_ = words(nr.state, record_r, 0x1D8 // 4)
                gv_ = words(nr.state, 0x20080000 + 0x400 * ((record_r - record) // 0x1D8 + (record - 0x2412CC) // 0x1D8), 2)
                print(f"   pair f{len(outs_now)} call {'L' if r4 == record else 'R'}: R magic {gv_[0]:#x} playing {gv_[1]}; R w0 {wr_[0]:#x} START {wr_[0x67]:#x}:{wr_[0x66]:#x} END {wr_[0x69]:#x}:{wr_[0x68]:#x} PHASE {wr_[0x6d]:#x}:{wr_[0x6c]:#x} ACTIVE {wr_[0x6e] & 0xff}")
            if os.environ.get("SHOWOUT"):
                print(f"   call r4 {r4:#x}: flag word +0x17c {words(nr.state, r4 + 0x17C, 1)[0]:08x}, w60 {words(nr.state, r4 + 0x180, 1)[0]:08x}")
            if os.environ.get("SHOWSTACK") and len(calls) == 1:
                print(f"   at our entry: I6 {nr.state.uregs.get(sr_codes['I6']).value:#x} I7 {nr.state.uregs.get(sr_codes['I7']).value:#x}")
            if COST:
                call_wl.append((r4, len(nr.watch_log)))
            if CYC:
                global cyc
                cyc = {"step": 0, "iw_at": {}, "prev": None, "fmul": None, "acc": 0, "parts": collections.Counter(), "fn": collections.Counter()}
                cyc_calls.append(cyc)
            if r4 == record and not dumped:
                with open(f"{OUT}/gen_rec.txt", "w") as fh:
                    fh.write(" ".join(f"{w:08x}" for w in words(nr.state, record, 0x1D8 // 4)) + "\n")
                    fh.write(" ".join(f"{w:08x}" for w in words(nr.state, PARAM_RECORDS + 2 * TRACK * 0xDC, 0xDC // 4)) + "\n")
                    fh.write(" ".join(f"{w:08x}" for w in words(nr.state, record_r, 0x1D8 // 4)) + "\n")
                    fh.write(" ".join(f"{w:08x}" for w in words(nr.state, PARAM_RECORDS + (2 * TRACK + 1) * 0xDC, 0xDC // 4)) + "\n")
                    pg_ = PAGES[words(nr.state, 0x261CA4, 1)[0] & 1]   # the tempo float and the track's slot 2 and 6 words (gen_host line 5)
                    fh.write(" ".join(f"{w:08x}" for w in words(nr.state, 0x252D50, 1) + words(nr.state, pg_ + 0xDC + 0x60 * TRACK, 1)
                                      + words(nr.state, pg_ + 0xE8 + 0x60 * TRACK, 1)) + "\n")
                dumped = True
        inside = in_code(pc) or (calls and len(calls[-1]) == 3 and (NOPATCH or MACHINE not in OURS or os.environ.get("STOCKWRAP"))
                                             and pc not in (0x1C6AF7 + 1, 0x1C6B07))
        if inside and calls:
            calls[-1][2] += 1
            if CYC:
                cyc_step(nr, pc)
            if PROF and calls[-1][0] == record:
                prof[len(outs_now)][FUNCS[bisect.bisect_right(FSTART, pc) - 1][1]] += 1
        elif calls and len(calls[-1]) == 3 and nr._was_inside:
            calls[-1].append(words(nr.state, calls[-1][1], 32))   # the outputs, as the dispatch gets them
        nr._was_inside = inside
        nr._last.append(pc)
        orig()

    from sharc_core.encoding import UREG_CODES as sr_codes  # noqa: E402
    nr.step = step
    call_wl = []
    cyc_calls = []
    if COST:
        import sharc_run as _sr2
        nr.attach_watchpoints([_sr2.Watchpoint(0x80000000, 0xA0000000, on_read=True, on_write=True, stop=False, label="ddr")]
                              + ([_sr2.Watchpoint(0x2C0000, 0x2F0000, on_read=True, on_write=True, stop=False, label="l1b1"),
                                  _sr2.Watchpoint(0xFFFF0000, 0xFFFFFFFC, on_read=True, on_write=True, stop=False, label="stack")] if CYC else []))
    if os.environ.get("WATCHREC"):
        import sharc_run as _sr
        lo_w, hi_w = (int(x, 0) for x in os.environ.get("WATCHRANGE", "0x1A8,0x1D8").split(","))
        nr.attach_watchpoints([_sr.Watchpoint(record + lo_w, record + hi_w, on_read=True, stop=False, label="rec")])
    nr._was_inside = False
    import collections as _c
    nr._last = _c.deque(maxlen=24)
    t0 = time.time()
    halt = sv.run_with_patches(nr, H.FRAME_PATCH_TABLE, 20_000_000)
    v0 = [c for c in calls if c[0] == record]
    if COST:
        wl = nr.watch_log
        bounds = [b for _, b in call_wl] + [len(wl)]
        for ci, (r4_, b0) in enumerate(call_wl):
            lines_ = {}
            cnt = collections.Counter()
            for ev in wl[b0:bounds[ci + 1]]:
                if not in_code(ev.pc_sw):
                    continue
                if ev.address & 3:   # the runner logs each byte of an access: count words
                    continue
                if ev.label == "stack":
                    cnt["stack", ev.access] += 1
                    if os.environ.get("STACKMIN"):
                        stack_lo[r4_] = min(stack_lo.get(r4_, 1 << 33), ev.address)
                    continue
                if ev.label == "l1b1" or ev.address < 0x80000000:
                    cnt["l1b1"] += 1
                    continue
                region = "state" if ev.address >= 0x9E000000 else "sample"
                if os.environ.get("LINES"):   # distinct 32-byte lines per call and region
                    sub_ = region if region == "sample" else ("ring" if (ev.address - 0x9E000000) % 0x5000 >= 0x400 else "rec")
                    lines_.setdefault(sub_, set()).add(ev.address >> 5)
                if region == "state":
                    if ev.address >= 0x9E0A0000:
                        cnt[("sub", "link", ev.access)] += 1
                    elif (ev.address - 0x9E000000) % 0x5000 < 0x400:
                        cnt[("sub", "rec", ev.access)] += 1
                    else:
                        cnt[("sub", "ring", ev.access)] += 1
                cnt[(region, ev.access)] += 1
                if os.environ.get("COSTDBG") and ev.pc_sw == int(os.environ["COSTDBG"], 16) and f == int(os.environ.get("COSTMAP", "-1")):
                    print(f"      dbg pc {ev.pc_sw:#x} {ev.access} addr {ev.address:#x} width {ev.width} old {ev.old_value}")
                if os.environ.get("COSTMAP"):
                    cnt[("map", ev.access, ev.address >> 12 << 12, ev.pc_sw)] += 1
            instr_ = next((c[2] for c in calls if c[0] == r4_), 0)
            cost_rows.append((f, "L" if r4_ == record else "R", instr_, cnt["state", "read"], cnt["state", "write"], cnt["sample", "read"], cnt["sample", "write"]))
            if os.environ.get("COSTMAP") and f == int(os.environ["COSTMAP"]):
                for k_, n_ in sorted(((k_, n_) for k_, n_ in cnt.items() if k_[0] == "map" and (os.environ.get("COSTALL") or k_[2] < 0x9E000000)), key=lambda kv: -kv[1])[:25]:
                    print(f"      {k_[1]:5s} page {k_[2]:#x} pc {k_[3]:#x}: {n_}")
            if CYC and ci < len(cyc_calls):
                cc_ = cyc_calls[ci]
                ddr_ = cnt["state", "read"] + cnt["state", "write"] + cnt["sample", "read"] + cnt["sample", "write"]
                est_ = cc_["acc"] + cnt["l1b1"] + round(1.2 * ddr_)
                cyc_rows.append((f, "L" if r4_ == record else "R", instr_, est_))
                print(f"   cyc {'L' if r4_ == record else 'R'}: instr {instr_:,} -> est {est_:,} cycles  (dag {cc_['parts']['dag']:,} taken {cc_['parts']['taken']:,} "
                      f"call {cc_['parts']['call']:,} ret {cc_['parts']['ret']:,} fdep {cc_['parts']['fdep']:,} l1b1 {cnt['l1b1']:,} ddr {ddr_:,} stack r/w {cnt['stack', 'read']:,}/{cnt['stack', 'write']:,})")
            if CYC and f in CYCPROF and ci < len(cyc_calls):
                print("      by function: " + ", ".join(f"{n_} {c_:,}" for n_, c_ in cyc_calls[ci]["fn"].most_common(int(os.environ.get("TOPN", "14")))))
            if os.environ.get("LINES"):
                print(f"   lines {'L' if r4_ == record else 'R'}: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(lines_.items())))
            if os.environ.get("STACKMIN") and r4_ in stack_lo and r4_ in entry_i7:
                print(f"   stack depth {cost_rows[-1][1]}: {entry_i7[r4_] - stack_lo[r4_]} bytes below the entry's I7")
            print(f"   cost {cost_rows[-1][1]}: instr {instr_:,}  DDR reads: rec {cnt['sub', 'rec', 'read']} ring {cnt['sub', 'ring', 'read']} link {cnt['sub', 'link', 'read']} other {cnt['sample', 'read']}; writes rec {cnt['sub', 'rec', 'write']} ring {cnt['sub', 'ring', 'write']} other {cnt['sample', 'write']}"
                  f"  -> model {instr_ + 10 * (cnt['state', 'read'] + cnt['sample', 'read']):,} cycles")
    others = [c for c in calls if c[0] != record]
    vr = [c for c in calls if c[0] == record_r]
    if v0 and vr and len(vr[0]) > 3 and len(v0[0]) > 3:
        f32__ = lambda w: struct.unpack("<f", struct.pack("<I", w))[0]  # noqa: E731
        dl = max(abs(f32__(a_) - f32__(b_)) for a_, b_ in zip(v0[0][3], vr[0][3]))
        print(f"   L vs R this frame: max |diff| {dl:.3g}; L[0:4] {[round(f32__(x), 4) for x in v0[0][3][:4]]} R[0:4] {[round(f32__(x), 4) for x in vr[0][3][:4]]}")
    if vr and len(vr[0]) > 3:
        f32_ = lambda w: struct.unpack("<f", struct.pack("<I", w))[0]  # noqa: E731
        print(f"   R voice {record_r:#x}: {vr[0][2]:,} instr in our code, out rms "
              f"{(sum(f32_(w) ** 2 for w in vr[0][3]) / 32) ** 0.5:.4f}")
    if v0 and len(v0[0]) < 4:
        print(f"frame {f}: halted inside our code: {halt!s:.400} at pc {nr.state.pc_sw:#x}")
        print("   last pcs:", " ".join(hex(x) for x in nr._last))
        break
    if v0 and os.environ.get("SHOWOUT"):
        f32s_ = lambda w: struct.unpack("<f", struct.pack("<I", w))[0]  # noqa: E731
        print("   out L:", " ".join(f"{f32s_(x):.4f}" for x in v0[0][3]))
    if v0:
        outs.append(v0[0][3])
        outs_r.append(vr[0][3] if vr and len(vr[0]) > 3 else [0] * 32)
        costs.append(v0[0][2])
    print(f"frame {f}: {nr.instructions:,} instr ({time.time() - t0:.0f} s), halt {halt!s:.300}; "
          f"voice 0: {v0[0][2] if v0 else -1:,} instr in our code; other STRETCH calls {len(others)} "
          f"({', '.join(str(c[2]) for c in others[:3])})", flush=True)
    if os.environ.get("WATCHREC"):
        acc = collections.defaultdict(set)
        for ev in nr.watch_log:
            if not in_code(ev.pc_sw):
                acc[(ev.access, (ev.address - 0x28000000 - record) // 4 if ev.address >= 0x28000000 else (ev.address - record) // 4)].add(ev.pc_sw)
        print("   outside our code:", "; ".join(f"{k[0]} w{k[1]:02x} by {'/'.join(hex(p) for p in sorted(v))}" for k, v in sorted(acc.items())))
    runner = nr
    if FWLOAD:
        for nm_, rec_ in (("L", record), ("R", record_r)):
            w = words(runner.state, rec_, 0x70)
            act = (w[0x6E] & 0xFF)
            if os.environ.get("SHOWPLAY"):
                b6e_ = w[0x6E]
                print(f"   {nm_} play: LOOPSTART {H._read_q31_pair(runner.state, rec_ + 0x190) / 2**31:.1f} rev {(b6e_ >> 24) & 0xFF} loop {w[0x6F] & 0xFF} seedpend {(b6e_ >> 16) & 0xFF}")
            print(f"   {nm_} rec: w0 {w[0]:#x} rate {w[0x61]} frames {w[0x62]:#x} START {H._read_q31_pair(runner.state, rec_ + 0x198) / 2**31:.1f}"
                  f" END {H._read_q31_pair(runner.state, rec_ + 0x1A0) / 2**31:.1f} PHASE {H._read_q31_pair(runner.state, rec_ + 0x1B0) / 2**31:.2f}"
                  f" STEP {H._read_q31_pair(runner.state, rec_ + 0x1A8) / 2**31:.4f} w72 {struct.unpack('<f', struct.pack('<I', words(runner.state, rec_ + 0x1C8, 1)[0]))[0]:.4f} ACTIVE {act}")

if CYCPC:
    if CYCPC.endswith("."):   # a function's name (with selcc's trailing dot): its range in FUNCS
        k_ = [i_ for i_, (_, n_) in enumerate(FUNCS) if n_ == CYCPC][0]
        lo_, hi_ = FUNCS[k_][0], (FUNCS[k_ + 1][0] if k_ + 1 < len(FUNCS) else FUNCS[k_][0] + 0x10000)
    else:
        lo_, hi_ = (int(x, 0) for x in CYCPC.split(","))
    tot_ = sum(c_ for p_, c_ in cyc_pc.items() if lo_ <= p_ < hi_)
    print(f"cycles in [{lo_:#x}, {hi_:#x}): {tot_:,}")
    for p_ in sorted(p_ for p_ in cyc_pc if lo_ <= p_ < hi_):
        print(f"   {p_:#x} {cyc_pc[p_]:8,}  {_cyc_texts.get(p_, '')}")
if CYC and os.environ.get("CYCTXT"):
    for pc_, t_ in sorted(_cyc_texts.items())[:int(os.environ["CYCTXT"])]:
        print(f"   {pc_:#x}: {t_}   {_cyc_cache[pc_][1:]}")
if CYC:
    import json as _json2
    open(f"{OUT}/cyc_{os.environ.get('COSTTAG', 'run')}.json", "w").write(_json2.dumps(cyc_rows))
if os.environ.get("DUMPL1"):   # words at an L1 address after the run (DUMPL1=addr,count)
    a_, n_ = (int(x, 0) for x in os.environ["DUMPL1"].split(","))
    print("L1", hex(a_), " ".join(str(w) for w in words(runner.state, a_, n_)))
    raise SystemExit
if COST:
    import json as _json
    open(f"{OUT}/cost_{os.environ.get('COSTTAG', 'run')}.json", "w").write(_json.dumps(cost_rows))
if FWLOAD:
    raise SystemExit
open(f"{OUT}/gen_out_m{MACHINE}{'_stock' if NOPATCH else ''}.txt", "w").write(
    "\n".join(" ".join(f"{w:08x}" for w in o) for o in outs) + "\n")
open(f"{OUT}/gen_out_m{MACHINE}_r.txt", "w").write("\n".join(" ".join(f"{w:08x}" for w in o) for o in outs_r) + "\n")
if NOPATCH or MACHINE not in OURS or (os.environ.get("STOCKWRAP") and not int(os.environ.get("CAPI") or 0)):   # (no host model of stock)
    print(f"voice 0 outputs saved ({len(outs)} blocks); rms from block 4", (sum(struct.unpack('<f', struct.pack('<I', w))[0] ** 2 for o in outs[4:] for w in o) / max(1, 32 * len(outs[4:]))) ** 0.5)
    raise SystemExit
bad = []   # runner and host not bit-identical: the exit status says so (test/run_tests.py)
host = subprocess.run([f"{BUILD}/gen_host", str(len(outs)), f"{OUT}/gen_rec.txt",
                       f"{OUT}/gen_sample.i16"], capture_output=True, text=True, check=True).stdout.split("\n")
if STEREO:   # gen_host's STEREO mode prints L and R lines alternately
    host_l, host_r = host[0::2], host[1::2]
    f32_ = lambda w: struct.unpack("<f", struct.pack("<I", w))[0]  # noqa: E731
    for name, ours, theirs in (("L", outs, host_l), ("R", outs_r, host_r)):
        worst, first = 0.0, None
        for b, out in enumerate(ours):
            d_ = max(abs(f32_(a) - f32_(int(h, 16))) for a, h in zip(out, theirs[b].split()))
            if d_ > 1e-4 and first is None:
                first = b
            worst = max(worst, d_)
        print(f"stereo {name}: runner vs host max |diff| {worst:.3g}" + (f", first block over 1e-4: {first}" if first is not None else ""))
        if [list(o) for o in ours] != [[int(h, 16) for h in theirs[b].split()] for b in range(len(ours))]:
            bad.append(name)   # (the words: a NaN never compares)
    host = host_l
f32 = lambda w: struct.unpack("<f", struct.pack("<I", w))[0]  # noqa: E731
worst = 0.0
for b, out in enumerate(outs):
    hv = [int(x, 16) for x in host[b].split()]
    worst = max(worst, max(abs(f32(a) - f32(h)) for a, h in zip(out, hv)))
rms = (sum(f32(w) ** 2 for o in outs[4:] for w in o) / max(1, 32 * len(outs[4:]))) ** 0.5   # from block 4
print(f"voice 0 vs host replay: max |diff| {worst:.3g} over {len(outs)} blocks; output rms {rms:.4f}")
if [list(o) for o in outs] != [[int(x, 16) for x in host[b].split()] for b in range(len(outs))]:
    bad.append("voice 0")
print("instructions per call:", costs)
if "_diag" in os.environ.get("DXE", ""):
    w0 = words(runner.state, 0x266220, 1)[0]
    w1 = words(runner.state, 0x267220, 1)[0]
    print(f"reply word 0: page 0 {w0:#010x}, page 1 {w1:#010x} (calls {w0 >> 16}, trigs {w0 & 0xffff})")
if PROF:
    for f in [int(x) for x in PROF.split(",")]:
        tot = sum(prof[f].values())
        print(f"frame {f} ({tot:,}):", ", ".join(f"{n} {c:,}" for n, c in prof[f].most_common(12)))
if bad:
    sys.exit(f"runner and host differ: {', '.join(bad)}")
