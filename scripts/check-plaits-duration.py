"""Check compiled R3 duration, baseline PCM and retrigger behavior offline."""

# ruff: noqa: E402
import argparse
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
args = p.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
doctor()
sources = source_hashes()
import math
import re

# isort: off
from lab.dsp import Dsp
from lab.plaits import build_blob
import sharc_trace as st
# isort: on

new = build_blob(True, family="integration", output=out / "firmware")
old = build_blob(True, family="controls", output=out / "baseline")


def entry(folder):
    return int(
        re.search(
            r"(?m)^machine\.:\n\s+([0-9a-f]+)", (folder / "listing.txt").read_text()
        )[1],
        16,
    )


pc = entry(out / "firmware")
oldpc = entry(out / "baseline")


def invoke(e, model=0, raw=2304, trig=0, lane=0, previous=False, typ=7):
    c = e.core
    regs = {
        "M5": 0,
        "M6": 1,
        "M7": -1,
        "M14": 1,
        "I6": 0x200DFF00,
        "I7": 0x200DFEF8,
        "R4": (0x2412CC, 0x2414A4)[lane],
    }
    regs.update({f"L{i}": 0 for i in range(16)})
    for k, v in regs.items():
        c.set_reg(st.UREG_CODES[k], st.Const(v))
    c.poke(0x200DFEFC, struct.pack("<II", 0, 0), 1)
    for a, v in {
        0x255970: typ,
        0x24F0CC: trig << (lane * 8),
        0x2558DE: 103 * 256,
        0x2559B6: 0,
        0x2559B8: 8192,
        0x2559BA: model * 256,
        0x2559BC: 16384,
        0x2559C2: 24576,
        0x2559C4: raw,
        0x2559C8: 16384,
    }.items():
        c.poke(a, struct.pack("<I", v), 1)
    e.call(oldpc if previous else pc, 500000)
    buf = (0x2412CC, 0x2414A4)[lane] + 4
    data = struct.pack("<64I", *(c.peek(buf + i) for i in range(0, 256, 4)))
    require(
        all(map(math.isfinite, struct.unpack("<64f", data))),
        "Compiled adapter check failed",
    )
    return data


for model in range(6):
    a, b = Dsp(new), Dsp(old)
    for i in range(30):
        require(
            invoke(a, model, trig=i == 0)
            == invoke(b, model, raw=32768, trig=i == 0, previous=True),
            ("baseline overlap", model, i),
        )
    print("baseline model", model, "passed", flush=True)
for raw in (0, 2304, 32512, 65535):
    a = Dsp(new)
    invoke(a, raw=raw, trig=1)
    length = min((raw // 256 + 1) * 9600, 1228800)
    require(
        a.core.peek(537792512 + 332) == length,
        (raw, length, a.core.peek(537792512 + 332)),
    )
    # Execute the actual terminal fade and expiry at each duration endpoint.
    for lane in (0, 1):
        invoke(a, raw=raw, trig=1, lane=lane)
        base = 0x200E1000 + lane * 352
        a.core.poke(base + 328, struct.pack("<I", length - 512), 1)
        for _ in range(9):
            last = invoke(a, raw=raw, lane=lane)
        require(
            last == bytes(256) and a.core.peek(base + 336) == 0,
            "Compiled adapter check failed",
        )
        invoke(a, raw=raw, trig=1, lane=lane)
        require(a.core.peek(base + 328) == 64, "Compiled adapter check failed")
    print("duration", raw, length, "passed", flush=True)
# Contiguous minimum-length render: expiry and exact retrigger repeat.
a = Dsp(new)
x = b"".join(invoke(a, raw=0, trig=i == 0) for i in range(152))
y = b"".join(invoke(a, raw=0, trig=i == 0) for i in range(152))
require(x == y and x[-256:] == bytes(256), "Compiled adapter check failed")
report = {
    "status": "passed",
    "sources": sources,
    "blob_sha256": __import__("hashlib").sha256(new).hexdigest(),
    "baseline_pcm_models": 6,
    "duration_bounds": [0, 2304, 32512, 65535],
    "two_lanes": True,
    "actual_expiry": True,
    "minimum_duration_exact_retrigger": True,
    "scope": "Compiled SHARC adapter buffers; boundary state jump for long durations, no real-time or hardware claim",
}
require(source_hashes() == sources, "Sources changed during DSP checks")
write_json(out / "report.json", report)
print(report)
