"""Offline R3 CPU integration checks; never opens MIDI or transmits firmware."""

# ruff: noqa: E402
import argparse
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
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
doctor()
sources = source_hashes()
from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc
from unicorn import m68k_const as k

from lab.plaits import build_cpu
from lab.plaits_controls_checks import cpu_checks
from lab.plaits_integration import BASE, MODEL_NAMES

report = {"status": "running", "sources": sources}
try:
    report["cpu"] = build_cpu(family="integration")
    report["existing_checks"] = cpu_checks(out, integration=True)
    image = (out / "PLAITS_MAIN_OS.bin").read_bytes()
    r2 = (out / "PLAITS_R2_MAIN_OS.bin").read_bytes()
    meta = json.loads((out / "integration-cpu-patches.json").read_text())
    u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    u.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
    u.mem_map(0x40000000, 0x400000)
    u.mem_map(0x81000000, 0x10000)
    u.mem_write(BASE, image)
    sp, end, dest = 0x81008000, 0x40001000, 0x81004000

    def call(pc, *args, stop=end):
        u.reg_write(k.UC_M68K_REG_SR, 0x2000)
        u.reg_write(k.UC_M68K_REG_A7, sp)
        u.mem_write(sp, struct.pack(">" + "I" * (len(args) + 1), end, *args))
        try:
            u.emu_start(pc, stop, count=20000)
        except Exception:
            print(
                "FAILED CALL",
                hex(pc),
                args,
                hex(u.reg_read(k.UC_M68K_REG_PC)),
                flush=True,
            )
            raise
        require(u.reg_read(k.UC_M68K_REG_PC) == stop, "Incomplete CPU call")
        return u.reg_read(k.UC_M68K_REG_D0)

    # Execute real stock sprintf, including destination memory safety.
    for raw, name in [(i * 256, n) for i, n in enumerate(MODEL_NAMES)] + [
        (0xFFFFFFFF, MODEL_NAMES[0]),
        (1536, MODEL_NAMES[0]),
    ]:
        u.mem_write(dest - 16, b"Z" * 160)
        call(meta["model_formatter"], raw, dest)
        result = bytes(u.mem_read(dest, 64)).split(b"\0")[0].decode()
        require(result == name, ("model formatter", raw, result, name))
        require(bytes(u.mem_read(dest - 16, 16)) == b"Z" * 16, "Formatter underrun")
        require(bytes(u.mem_read(dest + 64, 64)) == b"Z" * 64, "Formatter overrun")
    for raw, expected in ((0, "100 ms"), (2304, "1000 ms"), (32512, "12800 ms")):
        call(meta["duration_formatter"], raw, dest)
        require(
            bytes(u.mem_read(dest, 64)).split(b"\0")[0].decode() == expected,
            "Duration units",
        )
    report["formatters"] = (
        "actual stock sprintf; all six models, invalid fallback, duration bounds"
    )
    # Compare complete permission routine to original for every stock type/track.
    permissions = []
    for binary in (r2, image):
        u.mem_write(BASE, binary)
        u.ctl_remove_cache(BASE, BASE + len(binary))
        permissions.append(
            [call(0x400DA3B0, typ, track) for typ in range(9) for track in range(17)]
        )
    for typ in range(9):
        for track in range(17):
            got = permissions[1][typ * 17 + track]
            expected = int(track == 0) if typ == 7 else permissions[0][typ * 17 + track]
            require(got == expected, ("permission", typ, track, got, expected))
    u.mem_map(0x80003000, 0x5000)
    repack_cases = 0
    for track in range(16):
        for typ in range(8):
            for value in (0, 519, 1024, 5639, 32512):
                results = []
                for binary in (r2, image):
                    u.mem_write(BASE, binary)
                    u.ctl_remove_cache(BASE, BASE + len(binary))
                    u.mem_write(0x80003CD0, bytes([typ]))
                    buffer = 0x80005B50 + track * 142
                    u.mem_write(buffer, bytes([0x5A]) * 142)
                    u.mem_write(buffer + 0x5A, struct.pack(">HHH", value, 512, 768))
                    u.reg_write(k.UC_M68K_REG_D6, track)
                    u.reg_write(k.UC_M68K_REG_A4, buffer)
                    call(0x4002E978, stop=0x4002E994)
                    results.append(bytes(u.mem_read(buffer, 142)))
                expected = bytearray(results[0])
                if track == 0 and typ == 7:
                    expected[0x5A:0x5C] = struct.pack(">H", value)
                require(
                    results[1] == expected,
                    (
                        "LFO repack preservation",
                        track,
                        typ,
                        value,
                        results[0][90:96].hex(),
                        results[1][90:96].hex(),
                        expected[90:96].hex(),
                    ),
                )
                repack_cases += 1
    report["repack_cases"] = repack_cases
    u.mem_map(0x4316E000, 0x2000)
    # Seed stock reverse caches with distinct values; the extension must not
    # change any stock lookup, regardless of the live cache contents.
    u.mem_write(0x4316E000, b"".join(struct.pack(">I", i + 1000) for i in range(2048)))
    reverse_results = []
    for binary in (r2, image):
        u.mem_write(BASE, binary)
        u.ctl_remove_cache(BASE, BASE + len(binary))
        reverse_results.append(
            [
                call(0x400DA23E, mirror, typ, flt)
                for mirror in range(72)
                for typ in range(9)
                for flt in range(7)
            ]
        )
    mapping = {26: 275, 28: 276, 31: 277, 32: 278}
    index = 0
    for mirror in range(72):
        for typ in range(9):
            for flt in range(7):
                expected = (
                    mapping.get(mirror, 0)
                    if typ == 7 and 25 <= mirror <= 34
                    else reverse_results[0][index]
                )
                require(
                    reverse_results[1][index] == expected,
                    ("reverse lookup", mirror, typ, flt),
                )
                index += 1
    report["reverse_lookup_cases"] = index
    report["permission_cases"] = 153
    require(source_hashes() == sources, "Sources changed during CPU checks")
    report["status"] = "passed"
finally:
    write_json(out / "report.json", report)
print(json.dumps(report, indent=2))
