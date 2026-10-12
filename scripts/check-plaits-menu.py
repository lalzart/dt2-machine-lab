"""Focused menu table and native rank-shim check on two local MAIN images."""

import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc
from unicorn import m68k_const as r

from lab.coldfire import INSERT
from lab.coldfire import RANK as SHIM
from lab.plaits_menu import BASE, LIST, ORDER, RANK, patch_cpu

before, after = (Path(p).read_bytes() for p in sys.argv[1:3])
expected, _ = patch_cpu(before)
assert after == expected
allowed = set(range(LIST - BASE, LIST - BASE + 32)) | set(
    range(RANK - BASE, RANK - BASE + 64)
)
changed = [
    i for i, pair in enumerate(zip(before, after, strict=True)) if pair[0] != pair[1]
]
assert len(before) == len(after) and set(changed) <= allowed
try:
    patch_cpu(after)
except (ValueError, RuntimeError):
    pass
else:
    raise AssertionError("Reapplying overlay must fail the baseline guard")
u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
u.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
u.mem_map(0x40000000, 0x400000)
u.mem_map(0x81000000, 0x10000)
u.mem_write(BASE, after)
sp = 0x81008000
u.reg_write(r.UC_M68K_REG_A7, sp)
u.reg_write(r.UC_M68K_REG_A0, 0x12345678)
u.mem_write(sp, struct.pack(">4I", 0, 0, 0, 0))
u.emu_start(SHIM, INSERT, count=100)
assert u.reg_read(r.UC_M68K_REG_PC) == INSERT
assert u.reg_read(r.UC_M68K_REG_A7) == sp
assert u.reg_read(r.UC_M68K_REG_A0) == 0x12345678
lo, hi = struct.unpack(">2I", u.mem_read(sp + 8, 8))
assert (lo, hi) == (RANK, RANK + 64)
pairs = list(struct.iter_unpack(">II", bytes(u.mem_read(lo, hi - lo))))
assert tuple(typ for typ, rank in sorted(pairs, key=lambda p: p[1])) == ORDER
names = []
for typ in ORDER:
    ptr = struct.unpack_from(">I", after, 0x403119C4 - BASE + typ * 12)[0]
    names.append(after[ptr - BASE : ptr - BASE + 32].split(b"\0")[0].decode())
assert names == [
    "Oneshot",
    "Werp",
    "Stretch",
    "Repitch",
    "Slice",
    "Grid",
    "PLAITS",
    "MIDI",
]
assert struct.unpack_from(">8I", after, LIST - BASE) == ORDER
print(
    json.dumps(
        dict(
            status="PASS",
            names=names,
            changed_bytes=len(changed),
            scope="Native rank-shim ABI and display tables; all other MAIN bytes identical, including descriptors, IDs, Flex and DSP transport. No panel or hardware test.",
            sha256=hashlib.sha256(after).hexdigest(),
        ),
        indent=2,
    )
)
