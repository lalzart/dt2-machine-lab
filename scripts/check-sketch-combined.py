#!/usr/bin/env python3
"""Execute combined CPU boundaries and the actual MAIN DSP depacker.

These are bounded instruction fixtures. Stock UI/heap endpoints in the ARP
case are stubbed; coupled boot and panel recording have a separate native test.
"""

# ruff: noqa: E402
import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import require, settings, sha256, source_hashes, write_json

cfg = settings()
if Path(sys.executable).resolve() != cfg["python"].resolve():
    os.execv(str(cfg["python"]), [str(cfg["python"]), "-B", __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--package", type=Path, required=True)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored output")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc
from unicorn import m68k_const as r

from lab import arp_firmware as arp
from lab import arp_tempo as tempo
from lab import recorder_freeze_worker_code as jobs
from lab import sketch_device as sketch
from lab.capicola_toggle import requested
from lab.cpu_extension import Segment, segment_chain
from lab.dt2_116 import BASE
from lab.runtime import STOCK_MAIN

frozen = source_hashes()
manifest = json.loads((a.package / "manifest.json").read_text())
require(
    manifest.get("combined") and manifest["source_hashes"] == frozen,
    "Stale combined package",
)
require(
    sha256(a.package / manifest["candidate"]) == manifest["container"]["sha256"],
    "Container drift",
)
image = (a.package / "SKETCH_MAIN.bin").read_bytes()
meta = json.loads((a.package / "native-patches.json").read_text())
require(hashlib.sha256(image).hexdigest() == meta["sha256"], "CPU drift")
report = dict(
    status="running",
    scope=__doc__,
    source_hashes=frozen,
    cpu_sha256=meta["sha256"],
    hardware=False,
)
try:
    u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    u.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
    for at, size in (
        (0x40000000, 0x8000000),
        (0x80000000, 0x10000),
        (0x81000000, 0x10000),
    ):
        u.mem_map(at, size)
    u.mem_write(BASE, image)
    cursor = meta["chain_address"] - BASE
    segments = []
    for info in meta["segments"]:
        n, dest, bss = struct.unpack_from(">III", image, cursor)
        require(
            (n, dest, bss) == (info["data_bytes"], info["destination"], info["bss"]),
            "Segment extent",
        )
        data = image[cursor + 12 : cursor + 12 + n]
        require(hashlib.sha256(data).hexdigest() == info["sha256"], "Segment digest")
        segments.append(Segment(dest, data, bss))
        u.mem_write(dest, data + bytes(bss))
        cursor += 12 + n
    require(
        image[meta["chain_address"] - BASE :]
        == segment_chain(segments, reservation=tuple(meta["reservation"])),
        "Segment chain",
    )
    sp, end, state, dest = 0x8100F000, 0x81000000, 0x81002000, 0x81001000

    def put(at, *values):
        u.mem_write(
            at, struct.pack(">" + "I" * len(values), *[v & 0xFFFFFFFF for v in values])
        )

    def get(at):
        return int.from_bytes(u.mem_read(at, 4), "big")

    def call(pc, *values, limit=100000):
        u.reg_write(r.UC_M68K_REG_SR, 0x2700)
        u.reg_write(r.UC_M68K_REG_A7, sp)
        put(sp, end, *values)
        u.emu_start(pc, end, count=limit)
        require(u.reg_read(r.UC_M68K_REG_PC) == end, f"Incomplete CPU call {pc:#x}")
        return u.reg_read(r.UC_M68K_REG_D0)

    call(0x4000045C, limit=500000)
    cap = meta["capicola"]
    for machine in range(7):
        actual = call(0x400C8840, machine)
        if machine == 2:
            require(actual == cap["descriptor"], "CAPI descriptor")
            require(
                struct.unpack(">9I", u.mem_read(actual + 8, 36))
                == tuple(cap["fields"]),
                "CAPI fields",
            )
        else:
            hook = bytes(u.mem_read(0x400C8840, 8))
            u.mem_write(
                0x400C8840,
                STOCK_MAIN.read_bytes()[0x400C8840 - BASE : 0x400C8848 - BASE],
            )
            u.ctl_remove_cache(0x400C8840, 0x400C8850)
            expected = call(0x400C8840, machine)
            u.mem_write(0x400C8840, hook)
            u.ctl_remove_cache(0x400C8840, 0x400C8850)
            require(actual == expected, "Stock machine descriptor changed")
    for value in (0, 1, 127, 128, 255, 256, 257, 32512, 65535):
        call(cap["formatter"], value, dest)
        require(
            bytes(u.mem_read(dest, 4)) == (b"ON\0\0" if requested(value) else b"OFF\0"),
            "CAPI formatter",
        )
        require(
            bool(call(0x4003ADB4, 0, 204, value) & 255) == (value <= 256),
            "CAPI native bounds",
        )
    report["capi_cpu"] = dict(
        stock_descriptors=6, capi_descriptor=True, formatter_and_bounds=True
    )

    locations = meta["arp"]["locations"]
    notes = []

    def endpoint(cpu, pc, size, user):
        stack = cpu.reg_read(r.UC_M68K_REG_A7)
        if pc in (arp.ON, arp.OFF):
            notes.append(
                (
                    get(arp.TICK),
                    "on" if pc == arp.ON else "off",
                    get(stack + 4),
                    get(stack + 8),
                )
            )
        if pc == arp.MAINLOOP + 6:
            stack += 4
        cpu.reg_write(r.UC_M68K_REG_PC, get(stack))
        cpu.reg_write(r.UC_M68K_REG_A7, stack + 4)

    for pc in (
        locations["ensure"],
        locations["sync"],
        arp.ON,
        arp.OFF,
        arp.MAINLOOP + 6,
    ):
        u.hook_add(UC_HOOK_CODE, endpoint, begin=pc, end=pc)
    put(locations["pointer"], state)
    sequences = []
    for track, mode, expected in ((15, 1, [60, 64, 67, 60]), (7, 2, [67, 64, 60, 67])):
        notes.clear()
        call(locations["init"], state, 0, mode)
        put(state + tempo.RATE, -1)
        call(locations["rate"], state, 2)
        put(state + arp.KEYBOARD, 1)
        put(state + arp.TRACK, track)
        put(0x402B62BC, 15300)
        for note in (67, 64, 60):
            call(locations["press"], state, note, 100)
        step = tempo.STEPS[2]
        ticks = [0] + sorted(
            {
                (n * step + 15299) // 15300 + delta
                for n in range(1, 5)
                for delta in (0, (step // 2 + 15299) // 15300)
            }
        )
        for tick in ticks:
            put(arp.TICK, tick)
            # Actual Sketch GUI continuation enters the newly chained ARP.
            call(sketch.relocate(jobs.TRAMP))
        on = [n[3] for n in notes if n[1] == "on"]
        require(
            on == expected and all(n[2] == track for n in notes),
            "Composed stopped ARP sequence",
        )
        require(get(state + arp.PLAY) == 0, "ARP changed transport")
        sequences.append(dict(track=track + 1, mode=mode, bpm=127.5, notes=list(notes)))
    report["arp_stopped"] = sequences
    for at, size in meta["guards"]:
        from lab.cpu_extension import GUARD

        require(bytes(u.mem_read(at, size)) == GUARD[:size], "CPU arena guard")

    # The real MAIN routine must fit its one-megabyte output allocation,
    # including command byte 3; inspect both canaries and output identity.
    sys.path.insert(0, str(ROOT / "out/references/elekloader-upload-audit"))
    from elekloader.syx import Syx

    parsed = Syx((a.package / manifest["candidate"]).read_bytes())
    compressed, expected = parsed.stored[7], parsed.section(7)
    u.mem_map(0x50000000, 0x200000)
    u.mem_map(0x60000000, 0x200000)
    u.mem_write(0x50000000, compressed)
    u.mem_write(0x60000000, b"\x03" + b"Z" * (0x100000 - 1))
    canary = b"combined-boundary" * 4
    u.mem_write(0x60100000, canary)
    n = call(0x4013815C, 0x50000000, 0x60000001, limit=250000000)
    require(
        n == len(expected) and bytes(u.mem_read(0x60000001, n)) == expected,
        "MAIN DSP decode mismatch",
    )
    require(
        n + 1 <= 0x100000
        and bytes(u.mem_read(0x60000000, 1)) == b"\x03"
        and bytes(u.mem_read(0x60100000, len(canary))) == canary,
        "DSP staging overflow",
    )
    report["main_depacker"] = dict(
        bytes=n, headroom=0x100000 - n - 1, exact=True, canary_intact=True
    )
    require(source_hashes() == frozen, "Source drift")
    report["status"] = "passed"
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
