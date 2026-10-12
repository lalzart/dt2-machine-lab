#!/usr/bin/env python3
"""Verify the existing OS1.16 STRETCH interface for a DSP replacement.

This intentionally omits the experimental type-8 selector and its CPU patches.
It executes the native descriptor, name, permission and restore functions and
compares the retained type-2 interface with the original firmware.
"""

# ruff: noqa: E402, I001
import argparse
import hashlib
import json
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
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
doctor()
from lab.runtime import STOCK_MAIN
from lab.plaits import build_cpu
from lab.flex_native_build import patch_cpu as flex
from lab.plaits_menu import patch_cpu as menu
from lab.capicola_memory import patch_cpu as reserve
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn import m68k_const as k

BASE = 0x40000400
TABLE = 0x4020F18C
EXPECTED_SHA = "7f19553cc4bbdf170378ba67c85bedcf4a57a1d10a4a9751080e249547bd8ff3"
EXPECTED_FIELDS = (221, 222, 0, 223, 224, 225, 226, 227, 10)
report = dict(status="running", firmware="Digitakt II OS1.16")
try:
    sources = source_hashes()
    build_cpu(family="integration")
    image, reservation = reserve(
        menu(flex((out / "PLAITS_MAIN_OS.bin").read_bytes())[0])[0]
    )
    require(hashlib.sha256(image).hexdigest() == EXPECTED_SHA, "CPU baseline drift")
    (out / "STRETCH_MAIN_OS.bin").write_bytes(image)
    write_json(out / "reservation.json", reservation)
    u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    u.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
    u.mem_map(0x40000000, 0x400000)
    u.mem_map(0x81000000, 0x10000)
    u.mem_map(0x80003000, 0x5000)
    u.mem_map(0x4293B000, 0x1000)
    sp, end, dest = 0x81008000, 0x81000000, 0x81001000

    def load(binary):
        u.mem_write(BASE, binary)
        u.ctl_remove_cache(BASE, BASE + len(binary))

    def reset():
        u.reg_write(k.UC_M68K_REG_SR, 0x2000)
        for prefix in ("A", "D"):
            for i in range(8):
                u.reg_write(getattr(k, f"UC_M68K_REG_{prefix}{i}"), 0)
        u.reg_write(k.UC_M68K_REG_A7, sp)

    def call(pc, *values):
        reset()
        u.mem_write(sp, struct.pack(">" + "I" * (len(values) + 1), end, *values))
        u.emu_start(pc, end, count=20000)
        require(u.reg_read(k.UC_M68K_REG_PC) == end, f"Incomplete native call {pc:#x}")
        return u.reg_read(k.UC_M68K_REG_D0)

    def string(ptr):
        if not ptr:
            return ""
        return bytes(u.mem_read(ptr, 64)).split(b"\0")[0].decode()

    snapshots = []
    for binary in (STOCK_MAIN.read_bytes(), image):
        load(binary)
        # The descriptor is BSS. Execute its original straight-line field
        # initializer, stopping before the next machine's string helper.
        # No descriptor fields are supplied by the test harness.
        init_start, init_end = 0x401C4938, 0x401C49A0
        require(
            binary[init_start - BASE : init_end - BASE]
            == STOCK_MAIN.read_bytes()[init_start - BASE : init_end - BASE],
            "STRETCH initializer changed",
        )
        u.mem_write(0x4293B9B8, bytes(44))
        reset()
        u.emu_start(init_start, init_end, count=100)
        require(u.reg_read(k.UC_M68K_REG_PC) == init_end, "Initializer incomplete")
        descriptor = call(0x400C8840, 2)
        fields = struct.unpack(">9I", u.mem_read(descriptor + 8, 36))
        require(fields == EXPECTED_FIELDS, "STRETCH descriptor changed")
        names = [string(call(pc, 2)) for pc in (0x400DA548, 0x400DA56E, 0x400DA594)]
        rows = []
        for slot, field in enumerate(fields):
            if not field:
                rows.append(dict(slot=slot, field=0, exposed=False))
                continue
            row = TABLE + field * 60
            raw = bytes(u.mem_read(row, 60))
            words = struct.unpack(">15I", raw)
            mirror = call(0x400D9ED8, field)
            if mirror & 0x80000000:
                mirror -= 1 << 32
            require(
                mirror == struct.unpack(">i", raw[4:8])[0], "Native mirror mismatch"
            )
            rows.append(
                dict(
                    slot=slot,
                    field=field,
                    exposed=True,
                    raw=raw.hex(),
                    mirror=mirror,
                    minimum=words[2],
                    maximum=words[3],
                    default=words[4],
                    long_name=string(words[10]),
                    owner_name=string(words[11]),
                    short_name=string(words[12]),
                    formatter=hex(words[13]),
                    wire_offset=hex(0xA8 + 2 * mirror) if mirror >= 0 else None,
                    track1_dsp_cache=hex(0x255984 + 2 * mirror)
                    if mirror >= 0
                    else None,
                )
            )
        permissions = [call(0x400DA3B0, 2, track) for track in range(16)]
        restored = []
        for typ in range(256):
            for adjacent in (0, 6, 7, 255):
                reset()
                u.reg_write(k.UC_M68K_REG_A0, 0x40213754)
                u.reg_write(k.UC_M68K_REG_A2, dest)
                u.reg_write(k.UC_M68K_REG_A3, dest + 0x1000)
                u.mem_write(dest, b"Z" * 256)
                u.mem_write(dest + 0x1000, bytes(256))
                u.mem_write(dest + 0x10D2, bytes((typ, adjacent)))
                u.emu_start(0x400DB2EA, 0x400DB342, count=100)
                require(
                    u.reg_read(k.UC_M68K_REG_PC) == 0x400DB342, "Restore incomplete"
                )
                restored.append(bytes(u.mem_read(dest, 256)))
        snapshots.append(
            dict(names=names, rows=rows, permissions=permissions, restored=restored)
        )
    old, new = snapshots
    for field in ("names", "rows", "permissions"):
        require(new[field] == old[field], "CPU STRETCH interface changed: " + field)
    for index, (before, after) in enumerate(
        zip(old["restored"], new["restored"], strict=True)
    ):
        expected = bytearray(before)
        # The preserved Plaits integration already restores type 7. STRETCH
        # and every other serialized value must retain the stock result.
        if index // 4 == 7:
            expected[0xA2] = 7
        require(after == expected, f"Restore changed serialized type {index // 4}")
    require(all(new["permissions"]), "Existing STRETCH is not allowed on all 16 tracks")
    require(
        new["names"][:2] == ["Stretch", "STRE"], "Existing machine identity changed"
    )
    require(source_hashes() == sources, "Source drift")
    report.update(
        status="passed",
        sha256=EXPECTED_SHA,
        machine_id=2,
        names=new["names"],
        fields=list(EXPECTED_FIELDS),
        controls=new["rows"],
        permitted_tracks=list(range(1, 17)),
        restore_cases=len(new["restored"]),
        exposed_gap=False,
        sources=sources,
        scope="Native CPU interface parity only; DSP replacement, panel capture, audio, physical timing and hardware remain unverified",
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "sources"}, indent=2
        )
    )
