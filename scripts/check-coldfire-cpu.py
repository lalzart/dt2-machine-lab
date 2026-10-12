"""Build/audit corrected CPU and check rank-shim ABI plus existing controls.

Local CPU execution only. No MIDI, no device operations, no upload package.
"""

# ruff: noqa: E402
import argparse
import json
import os
import random
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

from lab.coldfire import BASE, INSERT, RANK, TABLE, audit_code
from lab.plaits import build_cpu
from lab.plaits_controls_checks import cpu_checks

report = {"status": "running", "sources": sources}
try:
    report["cpu"] = build_cpu(family="controls")
    data = (out / "PLAITS_MAIN_OS.bin").read_bytes()
    u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    u.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
    u.mem_map(0x40000000, 0x400000)
    u.mem_map(0x81000000, 0x10000)
    u.mem_write(BASE, data)
    regs = [getattr(k, f"UC_M68K_REG_{pre}{i}") for pre in ("D", "A") for i in range(8)]
    rng = random.Random(0x40311A64)
    for case in range(256):
        sp = 0x81008000 + (case % 4) * 4
        initial = [rng.getrandbits(32) for _ in regs]
        initial[-1] = sp
        sr = 0x2000 | (case % 32)
        u.reg_write(k.UC_M68K_REG_SR, sr)
        for reg, value in zip(regs, initial, strict=True):
            u.reg_write(reg, value)
        before = bytes(rng.getrandbits(8) for _ in range(128))
        u.mem_write(sp - 32, before)
        u.emu_start(RANK, INSERT, count=32)
        require(u.reg_read(k.UC_M68K_REG_PC) == INSERT, "Rank target mismatch")
        require([u.reg_read(r) for r in regs] == initial, "Rank register/SP corruption")
        expected = bytearray(before)
        expected[28:32] = struct.pack(">I", initial[8])  # below-SP saved A0
        expected[40:48] = struct.pack(">II", TABLE, TABLE + 64)
        require(
            bytes(u.mem_read(sp - 32, 128)) == expected,
            "Rank stack/argument corruption",
        )
        require(
            u.reg_read(k.UC_M68K_REG_SR) == sr & ~15,
            "Rank flags differ from original MOVEs",
        )
    report["rank_abi_cases"] = 256
    report["rank_preserves"] = [
        "all D/A registers",
        "SP",
        "return address",
        "map argument",
        "neighboring stack",
        "original final CCR",
    ]
    failed = bytes.fromhex("2f7c40311a840008")
    try:
        audit_code(failed, RANK)
    except ValueError as exc:
        report["illegal_original_rejected"] = str(exc)
    else:
        raise ValueError("Illegal original accepted")
    # Document the emulator blind spot: it still accepts the exact bad opcode.
    u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    u.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
    u.mem_map(0x40000000, 0x400000)
    u.mem_map(0x81000000, 0x10000)
    u.reg_write(k.UC_M68K_REG_SR, 0x2000)
    u.mem_write(RANK, failed)
    u.reg_write(k.UC_M68K_REG_A7, 0x81008000)
    u.emu_start(RANK, RANK + 8, count=1)
    report["emulator_accepts_illegal_original"] = (
        u.reg_read(k.UC_M68K_REG_PC) == RANK + 8
    )
    require(
        report["emulator_accepts_illegal_original"],
        "Emulator behavior changed; revisit regression",
    )
    report["controls"] = cpu_checks(out)
    require(source_hashes() == sources, "Source changed during check")
    report.update(status="passed", hardware_verified=False)
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
