#!/usr/bin/env python3
"""Packaged source-playback reader: full-start/wrap PCM and full grain handoffs.

Prepared analyzed bank and initial state are host fixtures. Native integration
checker separately executes real native trigger/start/update and routing.
"""

# ruff: noqa: E402, I001
import argparse
import ctypes as ct
import hashlib
import importlib.util
import itertools
import json
import os
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from lab.project import require, settings, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--package", type=Path, required=True)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab import runtime  # noqa: F401 - initialize pinned native imports
import sharc_trace as st
import sharcldr
from lab.dsp import Dsp, header
from lab.capicola_layout import STATE_BASE
from lab.capicola_memory import BANK_BASE

spec = importlib.util.spec_from_file_location(
    "source_host", ROOT / "scripts/check-capicola-source.py"
)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
manifest = json.loads((a.package / "manifest.json").read_text())
frozen = source_hashes()
require(
    manifest.get("capicola_source") and manifest["source_hashes"] == frozen,
    "Wrong/stale source package",
)
blob = (a.package / manifest["dsp"]["path"]).read_bytes()
require(hashlib.sha256(blob).hexdigest() == manifest["dsp"]["sha256"], "DSP drift")
listing = (a.package / "firmware/listing.txt").read_text()
pcs = {
    label: int(re.search(r"(?m)^" + name + r"\.:\n\s+([0-9a-f]+)", listing)[1], 16)
    for label, name in [("reader", "cap_stretch_process"), ("live", "cap_live_process")]
}
split = sharcldr.parse_blocks(blob)[-1]["offset"]
extra = header(BANK_BASE - 256, STATE_BASE - (BANK_BASE - 256)) + bytes(
    STATE_BASE - (BANK_BASE - 256)
)
engine = Dsp(blob[:split] + extra + blob[split:])
core = engine.core
q, h, lib, old, ref = host.build(out)
bptr = BANK_BASE + 0x20000
sptr = BANK_BASE + 0x21000
dest = BANK_BASE + 0x22004


def poke(at, data):
    require(core.poke(at, data, 1) == len(data), "Fixture write")


def raw(at, n):
    return bytes(core.peek(at + i, 1) for i in range(n))


def stretch_bytes(s):
    return (
        struct.pack("<I", bptr)
        + bytes(s.core)[8:]
        + struct.pack(
            "<9i",
            *[
                getattr(s, n)
                for n in [
                    "start",
                    "end",
                    "reverse",
                    "loop",
                    "first_key",
                    "key_count",
                    "ideal_key",
                    "actual_key",
                    "incoming_key",
                ]
            ],
        )
    )


def state_bytes(s, live=False):
    if not live:
        return stretch_bytes(s)
    return (
        stretch_bytes(s.current)
        + stretch_bytes(s.outgoing)
        + struct.pack(
            "<5i2fi",
            s.fade_left,
            s.start,
            s.end,
            s.reverse,
            s.loop,
            s.pitch,
            s.advance,
            s.pending,
        )
    )


def install(bank, arrays, s, live=False):
    poke(BANK_BASE, b"".join(bytes(v) for v in arrays))
    count = bank.count
    poke(
        bptr,
        struct.pack(
            "<3I4iI",
            BANK_BASE,
            BANK_BASE + count * 4,
            BANK_BASE + count * 8,
            bank.capacity,
            bank.count,
            bank.frames,
            bank.error,
            bank.generation,
        ),
    )
    payload = state_bytes(s, live)
    require(len(payload) == (256 if live else 112), "Target ABI")
    poke(sptr - 4, b"GUAR" + payload + b"END!")
    return len(payload)


def render(n, size, live=False):
    poke(dest - 4, b"OUT!" + bytes(n * 4) + b"LAST")
    for name, value in {
        "I7": STATE_BASE + 0x17F00,
        "I6": STATE_BASE + 0x17F00,
        "M5": 0,
        "M6": 1,
        "M7": 0xFFFFFFFF,
        "M13": 0,
        "M14": 1,
        "M15": 0xFFFFFFFF,
        "R4": sptr,
        "R8": dest,
        "R12": n,
    }.items():
        core.set_reg(st.UREG_CODES[name], st.Const(value))
    before = core.stats()["instructions"]
    engine.call(pcs["live" if live else "reader"], 600_000_000)
    used = core.stats()["instructions"] - before
    require(
        raw(dest - 4, 4) == b"OUT!" and raw(dest + n * 4, 4) == b"LAST",
        "Output overrun",
    )
    require(
        raw(sptr - 4, 4) == b"GUAR" and raw(sptr + size, 4) == b"END!", "State overrun"
    )
    return struct.unpack("<" + "f" * n, raw(dest, n * 4)), used


report = dict(
    status="running",
    scope=__doc__,
    source_hashes=frozen,
    dsp_sha256=manifest["dsp"]["sha256"],
    cases=[],
    handoffs=[],
)
try:
    for kind in ["noise", "percussion", "chord"]:
        data = host.signal(kind, 1024)
        bank, arrays = q.sample(h, lib, data)
        for reverse, loop, pitch in itertools.product([0, 1], [0, 1], [0.5, 1.0, 2.0]):
            n = 4096
            up, expected, event = [(ct.c_float * n)() for _ in range(3)]
            stats = (ct.c_float * 7)()
            require(
                ref.source_audit(
                    data,
                    len(data),
                    0,
                    len(data),
                    reverse,
                    loop,
                    pitch,
                    0.425,
                    n,
                    up,
                    expected,
                    event,
                    stats,
                )
                == 0
                and stats[2] == 0,
                "Original fixture",
            )
            s = h.base.Stretch()
            require(
                lib.cap_stretch_start(
                    ct.byref(s),
                    ct.byref(bank),
                    0,
                    len(data),
                    reverse,
                    loop,
                    pitch,
                    0.425,
                    128,
                )
                == 0,
                "Host start",
            )
            size = install(bank, arrays, s)
            actual, used = render(n, size)
            maximum, rms = q.error(up, actual)
            require(
                maximum <= 1e-4 and rms <= 1e-5,
                f"Native full-start error:{kind, reverse, loop, maximum, rms}",
            )
            install(bank, arrays, s)
            again, _ = render(n, size)
            require(actual == again, "Native repeat")
            report["cases"].append(
                dict(
                    kind=kind,
                    pitch=pitch,
                    reverse=reverse,
                    loop=loop,
                    frames=n,
                    maximum_error=maximum,
                    rms_error=rms,
                    instructions=used,
                    repeat_exact=True,
                    splices=sum(v > 0 for v in event),
                )
            )
            print(
                f"PASS native {kind} pitch{pitch} reverse{reverse} loop{loop} error{maximum:.3g}",
                flush=True,
            )
    data = host.signal("complex", 4096)
    bank, arrays = q.sample(h, lib, data)
    for change in ["reverse", "trim", "retrigger"]:
        s = h.Live()
        lib.cap_live_start(
            ct.byref(s), ct.byref(bank), 0, len(data), 0, 1, 1, 0.425, 128
        )
        pre = (ct.c_float * 512)()
        lib.cap_live_process(ct.byref(s), pre, 512)
        if change == "retrigger":
            lib.cap_live_retrigger(
                ct.byref(s), ct.byref(bank), 0, len(data), 0, 1, 2, 0.5, 128
            )
        else:
            lib.cap_live_update(
                ct.byref(s),
                512 if change == "trim" else 0,
                3072 if change == "trim" else len(data),
                int(change == "reverse"),
                1,
                2,
                0.5,
            )
        require(
            s.fade_left == 960 and s.outgoing.core.pitch == 1,
            "Source handoff initial state",
        )
        saved = h.Live.from_buffer_copy(bytes(s))
        size = install(bank, arrays, s, True)
        n = 1024
        expected = (ct.c_float * n)()
        lib.cap_live_process(ct.byref(s), expected, n)
        actual, used = render(n, size, True)
        maximum, rms = q.error(expected, actual)
        require(
            maximum <= 1e-4 and rms <= 1e-5,
            f"Native handoff error:{change, maximum, rms}",
        )
        install(bank, arrays, saved, True)
        again, _ = render(n, size, True)
        require(again == actual, "Handoff repeat")
        report["handoffs"].append(
            dict(
                change=change,
                frames=n,
                maximum_error=maximum,
                rms_error=rms,
                instructions=used,
                repeat_exact=True,
            )
        )
    require(frozen == source_hashes(), "Source drift")
    report["status"] = "passed"
    print("PASS source target full playback and grain handoffs", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
