#!/usr/bin/env python3
"""Native CPU checks for the guarded Capicola menu and parameter overlay."""

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
from lab.project import settings, doctor, require, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
args = p.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = out.name
doctor()
from lab.plaits import build_cpu
from lab.flex_native_build import patch_cpu as flex
from lab.plaits_menu import patch_cpu as menu
from lab.capicola_memory import patch_cpu as reserve
from lab.capicola_controls import patch_cpu, BASE, ORDER, FIELDS, TABLE
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn import m68k_const as k

report = dict(status="running")
try:
    sources = source_hashes()
    build_cpu(family="integration")
    before = reserve(menu(flex((out / "PLAITS_MAIN_OS.bin").read_bytes())[0])[0])[0]
    image, meta = patch_cpu(before)
    require(image == patch_cpu(before)[0], "Repeated CPU overlay differs")
    (out / "CAPICOLA_MAIN_OS.bin").write_bytes(image)
    write_json(out / "cpu-patches.json", meta)
    for bad in (image, bytes(len(image))):
        try:
            patch_cpu(bad)
        except (ValueError, RuntimeError):
            pass
        else:
            raise ValueError("Unknown image accepted")
    u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    u.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
    u.mem_map(0x40000000, 0x400000)
    u.mem_map(0x81000000, 0x10000)
    u.mem_map(0x80003000, 0x5000)
    sp, end, dest = 0x81008000, 0x81000000, 0x81001000

    def load(b):
        u.mem_write(BASE, b)
        u.ctl_remove_cache(BASE, BASE + len(b))

    def call(pc, *args, stop=end):
        u.reg_write(k.UC_M68K_REG_SR, 0x2000)
        u.reg_write(k.UC_M68K_REG_A7, sp)
        u.mem_write(sp, struct.pack(">" + "I" * (len(args) + 1), end, *args))
        u.emu_start(pc, stop, count=20000)
        require(u.reg_read(k.UC_M68K_REG_PC) == stop, f"Incomplete call {pc:#x}")
        return u.reg_read(k.UC_M68K_REG_D0)

    def string(ptr):
        return bytes(u.mem_read(ptr, 64)).split(b"\0")[0].decode()

    outputs = []
    types = list(range(11)) + [0xFFFFFFFF, 0x7FFFFFFF]
    for binary in (before, image):
        load(binary)
        outputs.append([call(0x400C8840, t) for t in types])
    for t, old, new in zip(types, *outputs, strict=True):
        require(
            new == (meta["descriptor"] if t == 8 else old),
            "Descriptor dispatch changed another type",
        )
    require(
        tuple(struct.unpack(">9I", u.mem_read(meta["descriptor"] + 8, 36))) == FIELDS,
        "Descriptor fields",
    )
    names = []
    for t in ORDER:
        names.append(string(call(0x400DA548, t)))
    require(
        names
        == [
            "Oneshot",
            "Werp",
            "Stretch",
            "Repitch",
            "Slice",
            "Grid",
            "PLAITS",
            "CAPICOLA",
            "MIDI",
        ],
        "Menu names",
    )
    require(string(call(0x400DA56E, 8)) == "CAP", "Short name")
    for typ in list(range(8)) + [9, 255, 0xFFFFFFFF]:
        for function in (0x400DA548, 0x400DA56E, 0x400DA594, 0x4005E204):
            result = []
            for binary in (before, image):
                load(binary)
                result.append(call(function, typ))
            require(result[0] == result[1], "Name/group stock parity")
    perms = []
    for binary in (before, image):
        load(binary)
        perms.append(
            [call(0x400DA3B0, t, track) for t in range(10) for track in range(17)]
        )
    for i, (old, new) in enumerate(zip(*perms, strict=True)):
        typ, track = divmod(i, 17)
        require(new == (int(track == 0) if typ == 8 else old), "Permission changed")
    load(image)
    u.reg_write(k.UC_M68K_REG_A0, 0x12345678)
    call(0x40311A64, 0, 0, 0, stop=0x401AAB60)
    require(
        u.reg_read(k.UC_M68K_REG_A0) == 0x12345678
        and u.reg_read(k.UC_M68K_REG_A7) == sp,
        "Rank ABI",
    )
    lo, hi = struct.unpack(">2I", u.mem_read(sp + 8, 8))
    require((lo, hi) == (meta["ranks"], meta["ranks"] + 72), "Rank span")
    require(
        tuple(t for t, r in struct.iter_unpack(">II", u.mem_read(lo, hi - lo)))
        == ORDER,
        "Rank order",
    )
    # Original restore instructions, all serialized byte values and neighbor.
    restored = []
    for binary in (before, image):
        load(binary)
        cases = []
        for typ in range(256):
            for adjacent in (0, 6, 7, 255):
                u.reg_write(k.UC_M68K_REG_SR, 0x2000)
                for pre in ("A", "D"):
                    for i in range(8):
                        u.reg_write(getattr(k, f"UC_M68K_REG_{pre}{i}"), 0)
                u.reg_write(k.UC_M68K_REG_A0, 0x40213754)
                u.reg_write(k.UC_M68K_REG_A2, dest)
                u.reg_write(k.UC_M68K_REG_A3, dest + 0x1000)
                u.mem_write(dest, b"Z" * 256)
                u.mem_write(dest + 0x1000, bytes(256))
                u.mem_write(dest + 0x10D2, bytes((typ, adjacent)))
                u.emu_start(0x400DB2EA, 0x400DB342, count=100)
                require(u.reg_read(k.UC_M68K_REG_PC) == 0x400DB342, "Restore span")
                cases.append(bytes(u.mem_read(dest, 256)))
        restored.append(cases)
    for i, (old, new) in enumerate(zip(*restored, strict=True)):
        expected = bytearray(old)
        if i // 4 == 8:
            expected[0xA2] = 8
        require(new == expected, "Restore changed other type/field")
    load(image)
    row = TABLE + 204 * 60
    require(call(0x400D9ED8, 204) == 27, "RATE mirror")
    for raw in (0, 16384, 32512):
        call(0x400E1424, raw, dest)
        require(string(dest) == str(raw // 256), "Rate formatter")
    for raw, want in (
        (0xFFFFFFFF, False),
        (0, True),
        (16384, True),
        (32512, True),
        (32513, False),
    ):
        require(
            bool(call(0x4003ADB4, 0, 204, raw) & 255) == want, "Rate range validation"
        )
    # Early model filter is only customized for type7; prove Capicola takes
    # exactly the baseline sampler path instead of Plaits' MODEL override.
    for raw in (0, 1, 16384, 32512):
        results = []
        for binary in (before, image):
            load(binary)
            u.mem_write(0x80003CD0, b"\x08")
            u.mem_write(0x80003398, struct.pack(">H", raw))
            u.mem_write(0x80005B50, bytes([0x5A]) * 142)
            call(0x40311D04, stop=0x400D934C)
            results.append(bytes(u.mem_read(0x80005B50, 142)))
        require(results[0] == results[1], "Capicola entered Plaits filter override")
    require(source_hashes() == sources, "Source drift")
    report.update(
        status="passed",
        names=names,
        dispatch_cases=len(types),
        permission_cases=170,
        restore_cases=1024,
        rate_metadata="native mirror, range and formatter passed",
        sha256=hashlib.sha256(image).hexdigest(),
        sources=sources,
        scope="Native CPU functions and guarded tables; panel, boot, full transport and hardware unverified",
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))
