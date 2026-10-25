"""Capicola as the Digitakt II's STRETCH, REPITCH, GRID and SLICE (OS 1.17 or 1.16, DT2_FW).

    uv run --python 3.12 --no-project python firmware/build_cap.py --release|--diag [--slice-ui] [-o OUT.syx] [--section7-out S7.bin]

--release: the image to play: stock MAIN OS and stock section 7 with only the
           changes below.
--diag:    the same plus the USB probe (build.py) and the generator's counters in
           reply word 0 (the handler's own store NOP'd), for dt2probe.py capload.

  1. the DSP code (tools/build_gen.sh: build/dt2gen_l1.dxe, or dt2gen_l1_diag.dxe
     for --diag; capicola_c99/sharc: dt2gen.c with capicola.c, render.asm,
     feed.asm, dt2entry.asm, rt.c; linked by l1l2.ldf), its L1 segment at PM sw
     0x16bab8 = DM 0x2d7570, after the stock image's last byte in L1 block 1
     (0x2d7563), zero-padded to 0x2df000; its rarely run code in L2;
  2. the per-voice dispatch's `cjump 0x1c5576 (db)` at sw 0x1c6af1 (STRETCH)
     retargeted to cc_dt2_entry, and its `cjump 0x1c4ecf (db)` at sw 0x1c6b00
     (the shared sample generator) to cc_dt2_rp_entry, which sends every machine
     but REPITCH, GRID and SLICE straight on to 0x1c4ecf: the same instructions,
     their 24-bit target fields changed and nothing else.
  3. MAIN OS: the SRC page's empty slot 2 (the knob after PLAY) on STRETCH and
     REPITCH becomes CAPI, the switch between the stock machine and Capicola's.
     Each machine's descriptor field 2 is a `clr.l` in the boot initializer; it
     becomes a `jmp` to a stub in the cave that survives a cold boot
     (machineprofile's flash_cave), which stores the param code and jumps back.
     The codes are the firmware's two dormant "Crossfade"/CFADE entries (slot 2,
     default 0): 0xcc for STRETCH, 0xfa for REPITCH, renamed "Capicola"/"CAPI"
     and given to their machine. digikit docs/findings/02-machines-and-parameters.md,
     "Exposing CFADE".
  4. --slice-ui (slice_main_os): GRID's and SLICE's slot 2 a three-way CAPI
     (OFF, REP, STR) and SLICE's slot 6 BARS, for dt2gen.c's slice machines.
Its state is in DSP DDR at 0x9e000000 + v * 0x5000 (32 voices, 640 KB) and the
stereo link's record at 0x9e0a0000, the region step 4.1 found unowned.
"""

from __future__ import annotations

import argparse
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build as probe       # noqa: E402  (puts dnfw on sys.path)
from fwver import FW, A     # noqa: E402  (DT2_FW: which OS; A(): a 1.16 MAIN OS address on it)
import sec7                 # noqa: E402  (section 7's layout)

from dnfw.cli.build import write_verified            # noqa: E402
from dnfw.cli.files import read_image                # noqa: E402
from dnfw.firmware.build import build as rebuild     # noqa: E402
from dnfw.firmware.build import replacement          # noqa: E402
from dnfw.firmware.load import load                  # noqa: E402
from dnfw.image import bootstream, sharc_object      # noqa: E402

DXE = probe.REPO / "build/dt2gen_l1.dxe"                 # tools/build_gen.sh: the release build
DIAG_DXE = probe.REPO / "build/dt2gen_l1_diag.dxe"       # built with -DGEN_DIAG
CODE_DM, CODE_SW = 0x2D7570, 0x16BAB8
SITES = [  # (call site sw, stock target, our entry symbol)
    (0x1C6AF1, 0x1C5576, "cc_dt2_entry."),
    (0x1C6B00, 0x1C4ECF, "cc_dt2_rp_entry."),
]


COLD_LO, COLD_HI = 0x200A0000, 0x200E0000   # L2 for rarely run code (l1l2.ldf): inside the
# region the memory test (dt2capicola_memtest, 2026-10-03) found untouched by the firmware


def read_dxe(path=DXE) -> tuple[bytes, dict[str, int], bytes]:
    """The L1 code, the symbols, and the boot blocks of any code linked into L2's
    cold region."""
    d = path.read_bytes()
    if d[5] != 1:
        raise SystemExit("expected a little-endian ELF from seld")
    phoff = struct.unpack_from("<I", d, 0x1C)[0]
    phentsize, phnum = struct.unpack_from("<HH", d, 0x2A)
    segs = []
    for i in range(phnum):
        typ, off, vaddr, paddr, filesz, memsz = struct.unpack_from("<IIIIII", d, phoff + i * phentsize)
        if typ == 1 and memsz:
            segs.append((vaddr, d[off:off + filesz], memsz))
    cold = b""
    l1 = [sg for sg in segs if sg[0] == CODE_SW]
    for v, b, m in segs:
        if v == CODE_SW:
            continue
        byte = 0x20000000 + 2 * (v - 0xB80000)
        if not (0xB80000 <= v < 0xC00000 and COLD_LO <= byte and byte + len(b) * 2 <= COLD_HI and len(b) == m):
            raise SystemExit(f"segment at sw {v:#x} ({len(b)} B) is neither our L1 code nor L2 cold code")
        cold += bootstream.block(byte, sharc_object.load_bytes(b))
    if len(l1) != 1 or len(l1[0][1]) != l1[0][2]:
        raise SystemExit(f"want one code segment at sw {CODE_SW:#x} and no data, got "
                         f"{[(hex(v), len(b), m) for v, b, m in segs]}")
    shoff = struct.unpack_from("<I", d, 0x20)[0]
    shentsize, shnum = struct.unpack_from("<HH", d, 0x2E)
    secs = [struct.unpack_from("<IIIIIIIIII", d, shoff + i * shentsize) for i in range(shnum)]
    st = [s for s in secs if s[1] == 2][0]
    strs = secs[st[6]]
    syms = {}
    for k in range(st[5] // 16):
        n_, val = struct.unpack_from("<II", d, st[4] + 16 * k)
        o = strs[4] + n_
        syms[d[o:d.index(b"\0", o)].decode()] = val
    return sharc_object.load_bytes(l1[0][1]), syms, cold


def diag_base(stock7: bytes) -> bytes:
    """Stock with the handler's reply-word-0 store NOP'd, so word 0 carries the
    generator's counters."""
    if bootstream.read_span(stock7, sec7.sw_to_load(sec7.STORE_SW), 2) != sec7.STORE_STOCK:
        raise SystemExit("sw 0x1c75c4 is not the stock dm (i4,m5)=r2")
    out = bytearray(stock7)
    bootstream.write_span(out, sec7.sw_to_load(sec7.STORE_SW), sec7.NOP16)
    return bytes(out)


MEMTEST_PAT_AT, MEMTEST_WORDS = 0x20080000, 8192   # capicola_c99/sharc/memtest.c's L2 pattern


def memtest_blocks(l2_dxe: pathlib.Path) -> bytes:
    """The memory test's L2 blocks: memfn.asm's cc_l2fn (linked by memtest_l2.ldf)
    and the pattern word k = 0x5A000000 ^ (k * 2654435761)."""
    d = l2_dxe.read_bytes()
    phoff = struct.unpack_from("<I", d, 0x1C)[0]
    phentsize, phnum = struct.unpack_from("<HH", d, 0x2A)
    out = b""
    for i in range(phnum):
        typ, off, vaddr, _paddr, filesz = struct.unpack_from("<IIIII", d, phoff + i * phentsize)
        if typ != 1 or not filesz:
            continue
        if not 0xB80000 <= vaddr < 0xC00000:
            raise SystemExit(f"memtest: {l2_dxe} segment at {vaddr:#x} is not L2 code")
        out += bootstream.block(0x20000000 + 2 * (vaddr - 0xB80000), sharc_object.load_bytes(d[off:off + filesz]))
    pat = b"".join(struct.pack("<I", (0x5A000000 ^ (k * 2654435761)) & 0xFFFFFFFF) for k in range(MEMTEST_WORDS))
    return out + bootstream.block(MEMTEST_PAT_AT, pat)


def section7(stock7: bytes, code: bytes, syms: dict[str, int], diag: bool = False, extra: bytes = b"",
             release: bool = False) -> bytes:
    base = diag_base(stock7) if diag else stock7   # release: no reply-word counters; only our code and the two retargets
    pad_to = sec7.PAD_TO
    lo, hi = sec7.LOAD_ALIAS + CODE_DM, sec7.LOAD_ALIAS + pad_to
    if CODE_DM <= sec7.BLOCK1_LAST_STOCK or CODE_DM + len(code) + 64 > pad_to:
        raise SystemExit(f"{len(code)} B at DM {CODE_DM:#x} does not fit before {pad_to:#x} with 64 B to spare")
    for b in bootstream.walk(base).blocks:
        if b.count and b.target < hi and lo < b.target + b.count:
            raise SystemExit(f"the code overlaps block {b.target:#x}+{b.count:#x}")
    out = bytearray(bootstream.insert_before_final(base, bootstream.block(lo, code + bytes(pad_to - CODE_DM - len(code))) + extra))
    for site, stock, sym in SITES:
        at = sec7.sw_to_load(site)
        w0, w1, w2 = struct.unpack("<HHH", bootstream.read_span(bytes(out), at, 6))
        insn = (w0 << 32) | (w1 << 16) | w2
        if (insn >> 24) & 0xFFFFFF != 0x180400 or insn & 0xFFFFFF != stock:
            raise SystemExit(f"sw {site:#x} is not the stock `cjump {stock:#x} (db)`")
        target = syms[sym]
        if not CODE_SW <= target < CODE_SW + len(code) // 2:
            raise SystemExit(f"{sym} at {target:#x} is outside the code")
        new = (insn & ~0xFFFFFF) | target
        bootstream.write_span(out, at, struct.pack("<HHH", new >> 32, (new >> 16) & 0xFFFF, new & 0xFFFF))
        print(f"  sw {site:#x}: cjump {stock:#x} -> cjump {target:#x} ({sym})")
    result = bytes(out)
    walked = bootstream.walk(result)
    if not walked.complete or walked.stopped_at != len(result):
        raise SystemExit(f"the result does not walk as a boot stream ({walked.reason})")
    print(f"  code: {len(code)} B at DM {CODE_DM:#x} (sw {CODE_SW:#x}), zero to the pad end; "
          f"{len(walked.blocks)} blocks")
    return result


MOS_BASE = A(0x40000400)
# The stubs and strings go in the tail of the probe's code cave (build.py RUN_A,
# a `dnfw cave scan` zero run whose start has run the probe on the device since
# build 1). digikit's flash_cave (0x403117c4) froze the device at the logo: that
# trailing region is not loaded or is cleared on the hardware, whatever the
# emulator does.
CAVE = A(0x402E4D50)                       # RUN_A + 0x32c; RUN_A ends 0x402e4da4
CAPI_STRINGS = (b"Capicola\0", b"CAPI\0")
PARAM_TABLE, PARAM_STRIDE = A(0x4020F18C), 0x3C
SLOTS = [  # machine, clr.l site, its descriptor field 2, param code, owner type, owner name ptr
    ("STRETCH", A(0x401C499A), A(0x4293B9C8), 0xCC, 2, A(0x402427D2)),
    ("REPITCH", A(0x401C4A14), A(0x4293B9F4), 0xFA, 3, A(0x4022731A)),
]
# The page draws a parameter's graphic through a per-parameter std::function in RAM
# (0x4293c040 + code*0x44, +0x14; looked up by 0x400c87ca, called from the value
# drawer 0x4003a768). Boot code fills each one with a copy of a shared prototype: the
# knob at 0x4293b364 (CFADE's), the OFF/ON switch at 0x4293b024 (AMP.T, FLT.T, LFO.T,
# RSET, RTRG: invoker 0x400c1de4, frame value>>8 of a two-frame sprite). These are the
# `pea.l prototype` before each CFADE entry's copy call.
GRAPHIC_SITES = {0xCC: A(0x401C267A), 0xFA: A(0x401C3284)}
KNOB_PROTO, SWITCH_PROTO = A(0x4293B364), A(0x4293B024)
# The same entry's word +0 is a flags word (read by 0x4003b548): CFADE's 0x20 makes
# the slot drawer (0x40069b8e, btst #5) show the value in place of the name while
# the value is edited; the switches have 4. `moveq #flags,d1` before each store.
FLAGS_SITES = {0xCC: (A(0x401C266A), A(0x401C2672)), 0xFA: (A(0x401C327A), A(0x401C327C))}   # moveq, its store
KNOB_FLAGS, SWITCH_FLAGS = 0x20, 0x04


def capi_main_os(mos: bytes, machines=("STRETCH", "REPITCH"), parts=("blob", "hook", "table", "look")) -> bytes:
    """parts (for bisecting the device freeze): blob = the stubs and strings in the
    probe's cave; hook = the clr.l -> jmp stub; table = the parameter entries'
    owner and name edits; neutral = stubs that only redo the clr.l."""
    out = bytearray(mos)

    def at(a, n):
        return bytes(out[a - MOS_BASE:a - MOS_BASE + n])

    def put(a, b):
        out[a - MOS_BASE:a - MOS_BASE + len(b)] = b

    # ColdFire instructions are at most 6 bytes: move.l #imm,abs.l (10 bytes, 23fc)
    # is a 68k form the ColdFire does not have -- the device took it as an illegal
    # instruction and hung at the logo, while the emulator (a 68040 core) ran it.
    # So: move.l d0,-(sp); move.l #code,d0; move.l d0,field; move.l (sp)+,d0; jmp
    # back; nop -- 24 bytes a stub.
    if "neutral" in parts:   # bisecting: the stub does what the hooked clr.l did
        stubs = b"".join(struct.pack(">HIHHHHHHHI", 0x42B9, field, 0x4E71, 0x4E71, 0x4E71, 0x4E71, 0x4E71, 0x4E71, 0x4EF9, site + 6)
                         for _, site, field, code, _, _ in SLOTS)
    else:
        stubs = b"".join(struct.pack(">HHIHIHHIH", 0x2F00, 0x203C, code, 0x23C0, field, 0x201F, 0x4EF9, site + 6, 0x4E71)
                         for _, site, field, code, _, _ in SLOTS)   # both stubs, even if one is unused
    assert len(stubs) == 24 * len(SLOTS)
    strings = CAPI_STRINGS[0] + b"\0" * (12 - len(CAPI_STRINGS[0])) + CAPI_STRINGS[1]
    blob = stubs + strings
    if CAVE < probe.CAVE or CAVE + len(blob) > probe.RUN_A + probe.RUN_LEN - 4:
        raise SystemExit("the CAPI blob leaves the probe's cave")
    if at(CAVE, len(blob)) != bytes(len(blob)):
        raise SystemExit(f"the cave at {CAVE:#x} is not zero (the probe grew into it?)")
    if "blob" in parts:
        put(CAVE, blob)
    long_ptr, short_ptr = CAVE + len(stubs), CAVE + len(stubs) + 12
    for k, (name, site, field, code, owner, owner_name) in enumerate(SLOTS):
        if name not in machines:
            print(f"  {name}: left stock")
            continue
        want = bytes.fromhex("42b9") + struct.pack(">I", field)
        if at(site, 6) != want or at(site + 6, 2) != bytes.fromhex("4e92"):
            raise SystemExit(f"{name}: {site:#x} is not the stock clr.l {field:#x} before jsr (a2)")
        if "hook" in parts:
            put(site, struct.pack(">HI", 0x4EF9, CAVE + 24 * k))
        e = PARAM_TABLE + code * PARAM_STRIDE
        f = struct.unpack(">15I", at(e, 60))
        if (f[1], f[2], f[3], f[4], f[10], f[12], f[13]) != (27, 0, 0x7F00, 0, A(0x40242AAC), A(0x40242AB6), A(0x400E1424)):
            raise SystemExit(f"param {code:#x} is not the stock dormant CFADE entry: {[hex(x) for x in f]}")
        if "table" in parts:
            # an OFF/ON switch, as stock's on/off parameters (Env Reset, Pingpong,
            # Dual Mono, Retrig): max 0x100, their OFF/ON formatter. Off (the
            # default) = the stock machine, on = Capicola (dt2entry.asm)
            put(e + 0x0C, struct.pack(">I", 0x100))
            put(e + 0x34, struct.pack(">I", A(0x400E195C)))
            put(e + 0x00, struct.pack(">I", owner))
            put(e + 0x28, struct.pack(">I", long_ptr))
            put(e + 0x2C, struct.pack(">I", owner_name))
            put(e + 0x30, struct.pack(">I", short_ptr))
        if "look" in parts:   # drawn as the OFF/ON switch, not a knob
            g = GRAPHIC_SITES[code]
            if at(g, 6) != struct.pack(">HI", 0x4879, KNOB_PROTO):
                raise SystemExit(f"{name}: {g:#x} is not the stock pea.l {KNOB_PROTO:#x}")
            put(g, struct.pack(">HI", 0x4879, SWITCH_PROTO))
            fl, fs = FLAGS_SITES[code]   # the name stays while editing, as on the switches
            if at(fl, 2) != bytes([0x72, KNOB_FLAGS]) or at(fs, 6) != struct.pack(">HI", 0x23C1, A(0x4293C040) + code * 0x44):
                raise SystemExit(f"{name}: {fl:#x} is not the stock moveq #{KNOB_FLAGS:#x},d1; move.l d1,...")
            put(fl, bytes([0x72, SWITCH_FLAGS]))
        print(f"  {name}: parts {','.join(parts)}: hook {site:#x} -> jmp {CAVE + 24 * k:#x} (via d0: #{code:#x} -> {field:#x}); "
              f"param {code:#x} owner {owner}, 'Capicola'/'CAPI'")
    return bytes(out)


# GRID and SLICE on Capicola (dt2gen.c gen_slice_speed): slot 2 a three-way CAPI
# (OFF the stock machine, REP REPITCH's way, STR STRETCH's way) on both machines,
# and SLICE's empty slot 6 STRETCH's BARS. A descriptor's owner only matters to the
# modulation-destination views (digikit findings 02, SoundParameterSet::vfunc_21),
# so one row serves two pages: the three-way is REPITCH's disabled TUNE row (0xe6,
# made a slot-2 row like CFADE), BARS is STRETCH's own row (0xe2) as it is. The
# stubs, the three-way's formatter (a copy of Filter Type's, which takes its three
# labels from a table) and its strings go in the tail of the probe's buffer run,
# past probe.S's BUF_END.
SLICE_CAVE = probe.RUN_B + 4 + 0x268                 # probe.S BUF_END
SLICE_CAVE_END = probe.RUN_B + probe.RUN_LEN - 4
SLICE_SLOTS = [  # what, clr.l site, the page's field, param code, whether jsr (a2) follows the clr.l
    ("GRID slot 2", A(0x401C4A8E), A(0x4293BA20), 0xE6, True),
    ("SLICE slot 2", A(0x401C4B08), A(0x4293BA78), 0xE6, False),
    ("SLICE slot 6", A(0x401C4B62), A(0x4293BA88), 0xE2, True),
]
MODE_CODE = 0xE6
MODE_LABELS = (b"OFF", b"REP", b"STR")
# BARS up to 32 (stock 8): STRETCH's row (SLICE's slot 6 too) and REPITCH's. The
# stock DSP takes 2^BARS unclamped (w72 and REPITCH's STEP keep halving at 4, 5),
# the formatter prints 1 << value, and the graphic's sprite lookup clamps its
# frame (16 and 32 show the 8-bar picture). WERP's BARS stays: its DSP clamps at 3.
BARS_CODES = (0xE2, 0xEB)
BARS_MAX = 5                # 1 << 5 = 32 bars
BARS_FMT = A(0x400E1742)
FMT_THREE = A(0x400E216E)      # Filter Type's formatter; lea.l table at +0x16, 0x38 bytes to its rts
MODE_GRAPHIC = A(0x401C2D4E)   # move.l #prototype,(a7) for 0xe6's graphic: TUNE's, made the routing words'
TUNE_PROTO = A(0x4293B184)
MSLICE_NAME = A(0x40242ABC)

# The page's pictures (slice_ui2). A parameter's graphic is a std::function in RAM
# (0x4293c040 + code*0x44, +0x14: functor 8 bytes, manager, invoker), copied at
# boot from a prototype; the invoker picks a frame of a sprite sheet by value and
# blits it. A sheet is {begin, end} of 28-byte frames {vtable 0x4021cb40, width,
# height, 1, data, mask, 0}: data and mask one 32-bit word a column, the top row
# in the MSB; the blitter (0x40113e88) keeps the screen where the mask is 0, and
# the frame lookup (0x40114334) clamps the index to the frames there are.
#  - CAPI (0xe6) drawn as words (OFF/REP/STR) the way SR.RT (0x101) draws its two:
#    the routing words' prototype, then the copied invoker swapped for a copy of
#    theirs (0x400c1f4c) on our sheet, and the flags those parameters use (4: the
#    name stays, the picture shows the value).
#  - BARS 16 and 32: the two BARS invokers (0x400c7d52 STRETCH's, which SLICE's
#    slot 6 shares, and 0x400c7e44 REPITCH's) read our sheet: the four stock frames
#    (1, 2, 4, 8 bars) and two more (two and four rows of 8 bars).
#  - TUNE off the page while CAPI is REP on GRID and SLICE (the DSP ignores it
#    there): the SRC page's slot list (0x40041fa8) asks 0x400c8840 for a machine's
#    nine param codes on every slot redraw, with the track's index and its kit on
#    the stack; that one call goes to list_hook instead, which hands back a copy
#    without TUNE (field 0, the slot left empty as REPITCH's) when the track's
#    slot-2 value is 1. A track's sound is kit + 0x6c + track * 0x3c0 -> vtable
#    +0x28 (0x40036266's way); its values at +0x14 + 2 * mirror index.
# The code and pictures go in 0x402f4f14: 896 zero bytes that are pixel data of a
# 128x64 bitmap (0x44f366c4, data 0x402f4e94, mask 0x402f4a94) whose mask is zero
# from column 16 on, so they never show (RUN_A is the same kind of place); no
# code reference, and the emulator saw no access during boot to the SRC page.
UI2_CAVE, UI2_CAVE_END = A(0x402F4F14), A(0x402F5294)
UI2_BMP_MASK = (A(0x402F4A94), A(0x402F4E94))     # its mask and data: 1 KB each
ROUTE_PROTO = A(0x4293AF64)                    # the routing words' prototype (BW.RT, SR.RT, OD.RT)
ROUTE_DRAW = A(0x400C1F4C)                     # its invoker; pea.l sheet at +0x1e, 0x4e bytes to its jmp
ROUTE_SHEET = A(0x44F359C8)
MODE_FLAGS, MODE_INVOKER = A(0x4293C040) + 0xE6 * 0x44, A(0x4293C040) + 0xE6 * 0x44 + 0x14 + 0xC
MODE_STUB_SITE = A(0x401C2D5C)                 # pea.l $4293ac74.l, after 0xe6's graphic is copied
FRAME_VT = A(0x4021CB40)
CAPI_MASK = A(0x402DAE90)                      # SR.RT's: 19 columns of 17 rows
BARS_SHEET = A(0x44F35F94)
BARS_SHEET_SITES = (A(0x400C7DD2), A(0x400C7E20), A(0x400C7EC4), A(0x400C7F12))   # pea.l $44f35f94.l
BARS_FRAMES = (A(0x402E3F24), A(0x402E3F68), A(0x402E3FAC), A(0x402E3FF0))        # 1, 2, 4, 8 bars (17x7)
BARS_MASK = A(0x402E3EE0)
LIST_STOCK = A(0x400C8840)     # the machine slot-list accessor: 0x4293b960 + type * 0x2c
LIST_SITES = (  # its callers on the SRC page: the site, the stock bytes, the hook entry
    (A(0x40017CF2), "47f9%08x" % A(0x400C8840), "list_hook_slot"),    # lea .,a3: the page renderer's per-slot code
    (A(0x4006217E), "49f9%08x" % A(0x400C8840), "list_hook_last"),    # lea .,a4: the knob hit-test
)
BARS_CLAMP_SITE = A(0x400C7D68)   # pea.l $d9.w in STRETCH's BARS invoker: it clamps by WERP's BARS row (max 8)
GLYPHS = {   # 5x7
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
}
UI2_S = """\
        .set    SCRATCH, {scratch:#x}
        .set    LAST, {last:#x}
        .set    CAPI_SHEET, {capi_sheet:#x}
        .set    WORDS, {words:#x}
        .set    ONOFF, {onoff:#x}
        .text
        .globl  capi_words, capi_switch, list_hook_slot, list_hook_last
| CAPI's graphic, called as every parameter graphic: (functor, value, canvas, x,
| y, compact). capi_words (SLICE's and GRID's three-way): our word picture at
| (x+1, y); capi_switch (STRETCH's and REPITCH's): the stock switch, sheet
| {switch_sheet:#x} at (x+1, y+4) as its own invoker 0x400c1de4 draws it. Compact (the
| sample view, where flags 0x24 keep the title off): the value as text where the
| title would be (the slot drawer's call at 0x40069d32: (x+9, y-7), the titles'
| font, centred in "XXXX"); the words from the formatter's table (WORDS) or ONOFF.
capi_words:
        lea     CAPI_SHEET,%a0
        lea     WORDS,%a1
        moveq   #0,%d1
        bra.s   1f
capi_switch:
        lea     {switch_sheet:#x},%a0
        lea     ONOFF,%a1
        moveq   #4,%d1
1:      move.l  8(%sp),%d0
        asr.l   #8,%d0
        tst.b   0x1b(%sp)
        bne.s   2f
        clr.l   -(%sp)
        add.l   0x18(%sp),%d1
        move.l  %d1,-(%sp)
        move.l  0x18(%sp),%d1
        addq.l  #1,%d1
        move.l  %d1,-(%sp)
        clr.l   -(%sp)
        move.l  %d0,-(%sp)
        move.l  %a0,-(%sp)
        jsr     {lookup:#x}
        lea     12(%sp),%sp
        move.l  %d0,-(%sp)
        move.l  0x1c(%sp),-(%sp)
        jsr     {blit:#x}
        lea     20(%sp),%sp
        rts
2:      move.l  (%a1,%d0.l*4),-(%sp)
        pea     {fmt_s:#x}
        pea     {xxxx:#x}
        clr.l   -(%sp)
        pea     1
        move.l  0x28(%sp),%d1
        subq.l  #7,%d1
        move.l  %d1,-(%sp)
        move.l  0x28(%sp),%d1
        addq.l  #8,%d1
        addq.l  #1,%d1
        move.l  %d1,-(%sp)
        pea     {font:#x}
        move.l  0x2c(%sp),-(%sp)
        jsr     {text:#x}
        lea     36(%sp),%sp
        rts
| The SRC page's slot lists without TUNE for GRID (4) and SLICE (6) at slot 2 = 1
| (REP), called as the accessor 0x400c8840 (the machine type at 4(sp)).
| list_hook_slot: the page renderer's (0x40017cd4) per-slot calls, which leave the
| track's sound slot object at 8(sp) (for 0x4005063e); list_hook_last: the knob
| hit-test's (0x4006216e), only the type: it goes by LAST, what the renderer found.
list_hook_slot:
        move.l  8(%sp),%d0
        move.l  %a2,-(%sp)
        move.l  %d0,%a2
        clr.l   LAST
        move.l  8(%sp),%d1
        subq.l  #4,%d1
        beq.s   3f
        subq.l  #2,%d1
        bne.s   7f
3:      tst.l   %d0
        beq.s   7f
        move.l  (%a2),%a0
        move.l  %a2,-(%sp)
        move.l  0x28(%a0),%a0
        jsr     (%a0)
        addq.l  #4,%sp
        tst.l   %d0
        beq.s   7f
        move.l  %d0,%a0
        clr.l   %d0
        move.w  0x4a(%a0),%d0
        lsr.l   #8,%d0
        subq.l  #1,%d0
        bne.s   7f
        moveq   #1,%d0
        move.l  %d0,LAST
7:      move.l  (%sp)+,%a2
list_hook_last:
        move.l  4(%sp),-(%sp)
        jsr     {stock:#x}
        addq.l  #4,%sp
        tst.l   LAST
        beq.s   9f
        move.l  4(%sp),%d1
        subq.l  #4,%d1
        beq.s   4f
        subq.l  #2,%d1
        bne.s   9f
4:      move.l  %d0,%a0
        lea     SCRATCH,%a1
        moveq   #11,%d0
5:      move.l  (%a0)+,(%a1)+
        subq.l  #1,%d0
        bne.s   5b
        lea     SCRATCH,%a0
        clr.l   8(%a0)
        move.l  %a0,%d0
9:      rts
"""


def assemble_cf(source: str, base: int) -> tuple[bytes, dict[str, int]]:
    """GNU assembly for the DT2's ColdFire (MCF5441x: -mcpu=54418, so a 68k-only
    form is an assembler error here rather than an illegal instruction on the
    device), linked at base: its bytes and symbols."""
    import shutil
    import subprocess
    import tempfile
    pre = next((p for p in ("m68k-elf-", "m68k-linux-gnu-", "m68k-none-elf-") if shutil.which(p + "as")), None)
    if pre is None:
        raise SystemExit("no m68k binutils (m68k-elf-as or m68k-linux-gnu-as): ./build.sh installs them")
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        (d / "a.s").write_text(source)
        subprocess.run([pre + "as", "-mcpu=54418", "-o", str(d / "a.o"), str(d / "a.s")], check=True)
        subprocess.run([pre + "ld", "-Ttext", hex(base), "-e", "0", "-o", str(d / "a.elf"), str(d / "a.o")], check=True)
        subprocess.run([pre + "objcopy", "-O", "binary", "-j", ".text", str(d / "a.elf"), str(d / "a.bin")], check=True)
        nm = subprocess.run([pre + "nm", str(d / "a.elf")], capture_output=True, text=True, check=True).stdout
        syms = {f[2]: int(f[0], 16) for f in (line.split() for line in nm.splitlines()) if len(f) == 3}
        return (d / "a.bin").read_bytes(), syms


def column_words(rows: list[str]) -> bytes:
    """a picture as the blitter's data: one 32-bit word a column, its h rows in the
    top h bits with the top row lowest (row r is bit 32 - h + r: SR.RT's frames read
    "PRE/FLTR" and "POST/FLTR" that way)"""
    h = len(rows)
    return b"".join(struct.pack(">I", sum(1 << (32 - h + r) for r, row in enumerate(rows) if row[c] == "#"))
                    for c in range(len(rows[0])))


def word_picture(word: str, w: int = 17, h: int = 17, left: int = 0, top: int = 5) -> list[str]:
    px = [["."] * w for _ in range(h)]
    for k, ch in enumerate(word):
        for r, line in enumerate(GLYPHS[ch]):
            for c, p in enumerate(line):
                if p == "#":
                    px[top + r][left + 6 * k + c] = "#"
    return ["".join(row) for row in px]


def bars_picture(rows_lit: set[int]) -> list[str]:
    return [".#.#.#.#.#.#.#.#." if r in rows_lit else "." * 17 for r in range(7)]


def slice_ui2(out: bytearray) -> None:
    def at(a, n):
        return bytes(out[a - MOS_BASE:a - MOS_BASE + n])

    def put(a, b):
        out[a - MOS_BASE:a - MOS_BASE + len(b)] = b

    # the cave: zero, inside its bitmap's data, where that bitmap's mask is zero
    if at(UI2_CAVE, UI2_CAVE_END - UI2_CAVE) != bytes(UI2_CAVE_END - UI2_CAVE):
        raise SystemExit(f"the cave at {UI2_CAVE:#x} is not zero")
    bm_mask, bm_data = UI2_BMP_MASK
    first_col = (UI2_CAVE - bm_data) // 8
    if not (bm_data <= UI2_CAVE and UI2_CAVE_END <= bm_data + 1024) or any(at(bm_mask + 8 * first_col, 8 * (128 - first_col))):
        raise SystemExit("the cave is not masked out of its bitmap")
    scratch = SLICE_CAVE + 152               # after slice_main_os's blob in RUN_B's tail: 0x2c bytes,
    stub_at = scratch + 0x2C                 # the graphics stub (48 bytes),
    last = stub_at + 48                      # list_hook's LAST (4)
    onoff = last + 4                         # and capi_switch's OFF, ON (8)
    words = SLICE_CAVE + 24 * len(SLICE_SLOTS) + 0x38   # slice_main_os's formatter table: OFF, REP, STR
    if at(scratch, onoff + 8 - scratch) != bytes(onoff + 8 - scratch) or onoff + 8 > SLICE_CAVE_END:
        raise SystemExit("RUN_B's tail is not free for the scratch list, stub, LAST and ONOFF")
    if at(words, 12) != struct.pack(">III", words + 12, words + 16, words + 20) or at(words + 12, 12) != b"OFF\0REP\0STR\0":
        raise SystemExit(f"{words:#x} is not slice_main_os's OFF/REP/STR table")
    if at(A(0x4023A62D), 4) != b"OFF\0" or at(A(0x4023ABC1), 3) != b"ON\0":
        raise SystemExit("the stock OFF/ON strings are not where the OFF/ON formatter has them")
    # the code first; its data after it, on 4 (two passes: the code's size sets the data's addresses)
    code_at = UI2_CAVE
    args = dict(scratch=scratch, last=last, words=words, onoff=onoff, stock=LIST_STOCK, capi_sheet=0x40000000,
                switch_sheet=A(0x44F34010), lookup=A(0x40114334), blit=A(0x40113E88), fmt_s=A(0x40240924),
                xxxx=A(0x4023DEB7), font=A(0x402A6C30), text=A(0x40113CF4))   # (a long address: the same size as the real one)
    code, syms = assemble_cf(UI2_S.format(**args), code_at)
    data_at = (code_at + len(code) + 3) & ~3
    capi_sheet = data_at
    capi_frames = capi_sheet + 8
    bars_sheet = capi_frames + 3 * 28
    bars_frames = bars_sheet + 8
    bmp = bars_frames + 6 * 28
    args["capi_sheet"] = capi_sheet
    code, syms = assemble_cf(UI2_S.format(**args), code_at)
    if syms["capi_words"] != code_at or (code_at + len(code) + 3) & ~3 != data_at:
        raise SystemExit("the graphics code moved between its two assemblies")
    capi_bmps = [column_words(word_picture(wd)) for wd in ("OFF", "REP", "STR")]   # 17x17, the word on rows 5-11
    bars_bmps = [column_words(bars_picture({1, 2, 4, 5})), column_words(bars_picture({0, 2, 4, 6}))]   # 16, 32
    capi_data = [bmp + 68 * k for k in range(3)]
    bars_data = [bmp + 3 * 68 + 68 * k for k in range(2)]
    end = bars_data[-1] + 68
    if end > UI2_CAVE_END:
        raise SystemExit(f"the pictures and code ({end - UI2_CAVE} B) leave the cave")
    blob = code + bytes(data_at - (code_at + len(code)))
    blob += struct.pack(">II", capi_frames, capi_frames + 3 * 28)
    blob += b"".join(struct.pack(">7I", FRAME_VT, 17, 17, 1, d, CAPI_MASK, 0) for d in capi_data)
    blob += struct.pack(">II", bars_frames, bars_frames + 6 * 28)
    blob += b"".join(struct.pack(">7I", FRAME_VT, 17, 7, 1, d, BARS_MASK, 0) for d in list(BARS_FRAMES) + bars_data)
    blob += b"".join(capi_bmps) + b"".join(bars_bmps)
    assert UI2_CAVE + len(blob) == end
    put(UI2_CAVE, blob)
    put(onoff, struct.pack(">II", A(0x4023A62D), A(0x4023ABC1)))
    # CAPI's graphics: 0xe6 gets the routing words' prototype (its invoker swapped below);
    # STRETCH's 0xcc keeps the switch's (capi_main_os), its invoker swapped too; REPITCH's
    # 0xfa then copies 0xcc's slot (copied after the stub has run), invoker and all.
    # Flags 0x24 on all three: the title stays on the main view, the compact view
    # leaves it off (0x40069d0e) and shows the graphic (BARS's flags).
    if at(MODE_GRAPHIC, 6) != struct.pack(">HI", 0x2EBC, KNOB_PROTO):
        raise SystemExit(f"{MODE_GRAPHIC:#x} is not slice_main_os's move.l #{KNOB_PROTO:#x},(a7)")
    put(MODE_GRAPHIC, struct.pack(">HI", 0x2EBC, ROUTE_PROTO))
    if at(MODE_STUB_SITE, 6) != bytes.fromhex("4879%08x" % A(0x4293AC74)):
        raise SystemExit(f"{MODE_STUB_SITE:#x} is not the stock pea.l $4293ac74.l")
    inv_cc = A(0x4293C040) + 0xCC * 0x44 + 0x14 + 0xC
    stub = struct.pack(">HHHIHIHIHIHIHHIHI", 0x2F00, 0x7024, 0x23C0, MODE_FLAGS, 0x203C, syms["capi_words"], 0x23C0,
                       MODE_INVOKER, 0x203C, syms["capi_switch"], 0x23C0, inv_cc, 0x201F, 0x4879, A(0x4293AC74),
                       0x4EF9, MODE_STUB_SITE + 6)
    assert len(stub) == 48
    put(stub_at, stub)
    put(MODE_STUB_SITE, struct.pack(">HI", 0x4EF9, stub_at))
    for code_ in (0xCC, 0xFA):
        fl, _fs = FLAGS_SITES[code_]
        if at(fl, 2) != bytes([0x72, SWITCH_FLAGS]):
            raise SystemExit(f"{fl:#x} is not capi_main_os's moveq #{SWITCH_FLAGS:#x},d1")
        put(fl, bytes([0x72, 0x24]))
    g = GRAPHIC_SITES[0xFA]
    if at(g, 6) != struct.pack(">HI", 0x4879, SWITCH_PROTO):
        raise SystemExit(f"{g:#x} is not capi_main_os's pea.l {SWITCH_PROTO:#x}")
    if not g > MODE_STUB_SITE > GRAPHIC_SITES[0xCC]:
        raise SystemExit("the boot order 0xcc's graphic, the stub, 0xfa's graphic does not hold")
    put(g, struct.pack(">HI", 0x4879, A(0x4293C040) + 0xCC * 0x44 + 0x14))
    # BARS: our six-frame sheet in both invokers
    for s in BARS_SHEET_SITES:
        if at(s, 6) != bytes.fromhex("4879") + struct.pack(">I", BARS_SHEET):
            raise SystemExit(f"{s:#x} is not the stock pea.l {BARS_SHEET:#x}")
        put(s + 2, struct.pack(">I", bars_sheet))
    # BARS: STRETCH's invoker clamps by its own row (0xe2, up to 32), not WERP's (0xd9, 8)
    if at(BARS_CLAMP_SITE, 4) != bytes.fromhex("487800d9"):
        raise SystemExit(f"{BARS_CLAMP_SITE:#x} is not the stock pea.l $d9.w")
    put(BARS_CLAMP_SITE, bytes.fromhex("487800e2"))
    # TUNE: the accessor's three callers on the SRC page
    for site, stock, entry in LIST_SITES:
        if at(site, 6).hex() != stock:
            raise SystemExit(f"{site:#x} is not the stock {stock}")
        put(site, bytes.fromhex(stock[:4]) + struct.pack(">I", syms[entry]))
    print(f"  pictures: CAPI words/switch {syms['capi_words']:#x}/{syms['capi_switch']:#x}, BARS 16/32, list hooks "
          f"{', '.join(f'{syms[e]:#x}' for _, _, e in LIST_SITES)}: {end - UI2_CAVE} of {UI2_CAVE_END - UI2_CAVE} B at "
          f"{UI2_CAVE:#x}; RUN_B: scratch {scratch:#x}, stub {stub_at:#x}, LAST {last:#x}, ONOFF {onoff:#x}")


def slice_main_os(mos: bytes) -> bytes:
    out = bytearray(mos)

    def at(a, n):
        return bytes(out[a - MOS_BASE:a - MOS_BASE + n])

    def put(a, b):
        out[a - MOS_BASE:a - MOS_BASE + len(b)] = b

    long_ptr = CAVE + 24 * len(SLOTS)   # capi_main_os's "Capicola" and "CAPI"
    short_ptr = long_ptr + 12
    if at(long_ptr, 9) != CAPI_STRINGS[0] or at(short_ptr, 5) != CAPI_STRINGS[1]:
        raise SystemExit("slice_main_os: the CAPI strings are not in place (capi_main_os first)")
    stubs = b"".join(struct.pack(">HHIHIHHIH", 0x2F00, 0x203C, code, 0x23C0, field, 0x201F, 0x4EF9, site + 6, 0x4E71)
                     for _, site, field, code, _ in SLICE_SLOTS)
    fmt = bytearray(at(FMT_THREE, 0x38))
    if fmt[0x16:0x1C] != bytes.fromhex("41f9%08x" % A(0x40213C5C)) or fmt[-2:] != bytes.fromhex("4e75") or fmt[:6] != bytes.fromhex("202f0004e080"):
        raise SystemExit(f"{FMT_THREE:#x} is not the stock Filter Type formatter")
    fmt_addr = SLICE_CAVE + len(stubs)
    table_addr = fmt_addr + len(fmt)
    assert table_addr % 4 == 0
    strings_addr = table_addr + 4 * len(MODE_LABELS)
    fmt[0x18:0x1C] = struct.pack(">I", table_addr)
    strings, ptrs = b"", []
    for s in MODE_LABELS:
        ptrs.append(strings_addr + len(strings))
        strings += s + b"\0"
    blob = stubs + bytes(fmt) + b"".join(struct.pack(">I", p) for p in ptrs) + strings
    if SLICE_CAVE + len(blob) > SLICE_CAVE_END:
        raise SystemExit(f"the slice blob ({len(blob)} B) leaves the probe's buffer run")
    if at(SLICE_CAVE, SLICE_CAVE_END - SLICE_CAVE) != bytes(SLICE_CAVE_END - SLICE_CAVE):
        raise SystemExit(f"the run at {SLICE_CAVE:#x} is not zero")
    put(SLICE_CAVE, blob)
    for k, (what, site, field, code, jsr_next) in enumerate(SLICE_SLOTS):
        if at(site, 6) != bytes.fromhex("42b9") + struct.pack(">I", field):
            raise SystemExit(f"{what}: {site:#x} is not the stock clr.l {field:#x}")
        if jsr_next and at(site + 6, 2) != bytes.fromhex("4e92"):
            raise SystemExit(f"{what}: no jsr (a2) after {site:#x}")
        put(site, struct.pack(">HI", 0x4EF9, SLICE_CAVE + 24 * k))
        print(f"  {what}: hook {site:#x} -> jmp {SLICE_CAVE + 24 * k:#x} (#{code:#x} -> {field:#x})")
    e = PARAM_TABLE + MODE_CODE * PARAM_STRIDE
    f = struct.unpack(">15I", at(e, 60))
    if (f[0], f[1], f[2], f[3], f[4], f[5], f[7], f[13]) != (3, 25, 0x400, 0x7C00, 0x4000, 1, 0xFFFFFFFF, A(0x400E1618)):
        raise SystemExit(f"param {MODE_CODE:#x} is not the stock disabled REPITCH TUNE: {[hex(x) for x in f]}")
    # a slot-2 row as CFADE's (0xcc): owner MSlice, mirror 27, 0..0x200 (three
    # values), default 0 (off), MIDI CC 18, kind 0x81; named Capicola/CAPI
    put(e + 0x00, struct.pack(">IIIIII", 6, 27, 0, 0x200, 0, 0))
    put(e + 0x18, struct.pack(">h", 18))
    put(e + 0x1C, struct.pack(">I", 0x81))
    put(e + 0x28, struct.pack(">IIII", long_ptr, MSLICE_NAME, short_ptr, fmt_addr))
    if at(MODE_GRAPHIC, 6) != struct.pack(">HI", 0x2EBC, TUNE_PROTO):
        raise SystemExit(f"{MODE_GRAPHIC:#x} is not the stock move.l #{TUNE_PROTO:#x},(a7)")
    put(MODE_GRAPHIC, struct.pack(">HI", 0x2EBC, KNOB_PROTO))
    for code in BARS_CODES:
        b = PARAM_TABLE + code * PARAM_STRIDE
        g = struct.unpack(">15I", at(b, 60))
        if (g[1], g[2], g[3], g[4], g[13]) != (33, 0, 0x300, 0x200, BARS_FMT):
            raise SystemExit(f"param {code:#x} is not a stock BARS row: {[hex(x) for x in g]}")
        put(b + 0x0C, struct.pack(">I", BARS_MAX << 8))
    print(f"  BARS ({', '.join(hex(c) for c in BARS_CODES)}): up to {1 << BARS_MAX} bars")
    print(f"  param {MODE_CODE:#x}: three-way CAPI ({'/'.join(s.decode() for s in MODE_LABELS)}), formatter {fmt_addr:#x}, "
          f"blob {len(blob)} of {SLICE_CAVE_END - SLICE_CAVE} B at {SLICE_CAVE:#x}")
    assert len(blob) == 152      # (slice_ui2 puts its scratch list right after it)
    slice_ui2(out)
    return bytes(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("-o", "--out", type=pathlib.Path)
    p.add_argument("--section7-out", type=pathlib.Path)
    p.add_argument("--main-os-out", type=pathlib.Path)
    p.add_argument("--no-capi", action="store_true", help="leave MAIN OS as the probe build (no CAPI knob)")
    p.add_argument("--capi-machines", default="STRETCH,REPITCH", help="which machines get the knob")
    p.add_argument("--capi-parts", default="blob,hook,table,look", help="bisecting: which parts of the knob patch (blob, hook, table, look)")
    p.add_argument("--dxe", type=pathlib.Path, help="the code to place (default: the diag or plain generator build)")
    p.add_argument("--memtest-l2", type=pathlib.Path, help="the memory test: memfn's L2 link (work/build_memtest.sh); adds it and the pattern to L2")
    p.add_argument("--diag", action="store_true", help="with the USB probe and the generator's counters in reply word 0 (dt2probe.py capload)")
    p.add_argument("--release", action="store_true", help="no monitoring: stock MAIN OS (no USB probe) and stock section 7 "
                   "(no counters) with only our code and patches; the release DSP build (dt2gen_l1.dxe)")
    p.add_argument("--slice-ui", action="store_true", help="GRID and SLICE: the three-way CAPI at slot 2, SLICE's BARS at slot 6 (slice_main_os)")
    p.add_argument("--stock-dsp", action="store_true", help="bisecting: leave section 7 (the DSP program) stock, so only the MAIN OS changes")
    args = p.parse_args()
    if args.release and args.diag:
        raise SystemExit("--release and --diag exclude each other")
    if not (args.release or args.diag):
        raise SystemExit("choose --release (the image to play) or --diag (with the USB probe, for capload)")
    out = args.out or probe.OUT_DIR / (f"dt2capdiag_DT2_{FW}.syx" if args.diag else f"dt2capicola_DT2_{FW}.syx")
    code, syms, cold = read_dxe(args.dxe or (DIAG_DXE if args.diag else DXE))
    if args.release and ("diag_frame." in syms or "cc_diag_stock." not in syms):
        raise SystemExit("--release wants the release DSP build (build/dt2gen_l1.dxe from tools/build_gen.sh, no GEN_DIAG)")
    firmware = load(read_image(probe.STOCK))
    if args.release:
        main_os = firmware.container.find(probe.MAIN_OS).unpack()   # no USB probe
    else:
        main_os = probe.compose(firmware.container.find(probe.MAIN_OS).unpack(), "dt2capdiag 1")
    if not args.no_capi:
        main_os = capi_main_os(main_os, tuple(args.capi_machines.upper().split(",")), tuple(args.capi_parts.split(",")))
    if args.slice_ui:
        main_os = slice_main_os(main_os)
    if args.main_os_out:
        args.main_os_out.write_bytes(main_os)
    s7 = section7(firmware.container.find(sec7.SECTION7).unpack(), code, syms, args.diag,
                  cold + (memtest_blocks(args.memtest_l2) if args.memtest_l2 else b""), release=args.release)
    if cold:
        print(f"  cold code: {len(cold)} B of boot blocks into L2 {COLD_LO:#x}..{COLD_HI:#x}")
    if args.section7_out:
        args.section7_out.write_bytes(s7)
    sections = {probe.MAIN_OS: replacement(firmware, probe.MAIN_OS, main_os)}
    if args.stock_dsp:
        print("  section 7: stock (--stock-dsp)")
    else:
        sections[sec7.SECTION7] = replacement(firmware, sec7.SECTION7, s7)
    output = rebuild(firmware, sections)
    return write_verified(output, out)


if __name__ == "__main__":
    raise SystemExit(main())
