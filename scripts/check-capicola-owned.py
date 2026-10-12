#!/usr/bin/env python3
"""Native CPU sample allocator boundary checks for the Capicola carve-out."""

# ruff: noqa: E402
import argparse
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, source_hashes

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc
from unicorn import m68k_const as r

from lab.capicola_memory import (
    BANK_BASE,
    BANK_END,
    BASE,
    SAMPLE_BYTES,
    SITES,
    STOCK_BYTES,
    patch_cpu,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--managed-baseline", type=Path)
    parser.add_argument("--expected-main", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
    out.mkdir(parents=True, exist_ok=False)
    doctor()
    sources = source_hashes()
    report = {
        "status": "running",
        "scope": "Native inspected allocator paths; fresh state only; no hardware claim",
    }
    try:
        original = (
            args.managed_baseline
            or (ROOT / "out/runs/flex-20sec-menu-package-02/PLAITS_R3_FLEX_MAIN_OS.bin")
        ).read_bytes()
        modified, metadata = patch_cpu(
            original, managed_flex=bool(args.managed_baseline)
        )
        if args.expected_main:
            require(modified == args.expected_main.read_bytes(), "Package MAIN differs")
        (out / "CAPICOLA_RESERVED_MAIN_OS.bin").write_bytes(modified)
        report["overlay"] = metadata
        allowed = {a - BASE + i for a, *_ in SITES for i in range(2, 6)}
        assert all(
            x == y or i in allowed
            for i, (x, y) in enumerate(zip(original, modified, strict=True))
        )
        for address in (0x40153F20, 0x40153F4C):
            assert modified[address - BASE : address - BASE + 4] == struct.pack(
                ">I", STOCK_BYTES + 0x400
            )
        assert modified[0x40153F32 - BASE : 0x40153F36 - BASE] == struct.pack(
            ">I", 0x19100400
        )
        assert BANK_BASE + 576004 * 12 <= BANK_END
        for bad in (modified, bytes(len(original))):
            try:
                patch_cpu(bad, managed_flex=bool(args.managed_baseline))
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError("Unknown image accepted")
        cpu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        cpu.mem_map(0x40000000, 0x700000)
        cpu.mem_map(0x81000000, 0x10000)
        stack = 0x81008000
        stop = 0x81000000
        records = 0x40600000
        dest = 0x81000100

        def write(address, *values):
            cpu.mem_write(address, struct.pack(">" + str(len(values)) + "I", *values))

        stub_calls = []

        def stub(uc, address, size, data):
            stub_calls.append(address)
            sp = uc.reg_read(r.UC_M68K_REG_A7)
            uc.reg_write(r.UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
            uc.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for address in (0x401360AC, 0x401E26FC, 0x401E1F50):
            cpu.hook_add(UC_HOOK_CODE, stub, begin=address, end=address)

        def call(pc, *args):
            write(stack, stop, *args)
            cpu.reg_write(r.UC_M68K_REG_A7, stack)
            saved = {
                reg: 0x17100000 + i * 16
                for i, reg in enumerate(
                    (
                        r.UC_M68K_REG_D2,
                        r.UC_M68K_REG_D3,
                        r.UC_M68K_REG_A2,
                        r.UC_M68K_REG_A3,
                        r.UC_M68K_REG_A6,
                    )
                )
            }
            for reg, val in saved.items():
                cpu.reg_write(reg, val)
            cpu.emu_start(pc, stop, count=10000)
            assert cpu.reg_read(r.UC_M68K_REG_PC) == stop
            assert all(cpu.reg_read(reg) == val for reg, val in saved.items())
            return cpu.reg_read(r.UC_M68K_REG_D0)

        cases = []
        for name, image, limit in [
            ("stock", original, STOCK_BYTES),
            ("reserved", modified, SAMPLE_BYTES),
        ]:
            cpu.mem_write(BASE, image)
            for existing in (0, 8192, SAMPLE_BYTES - 8192):
                write(0x405A0F64, records, records + (52 if existing else 0))
                cpu.mem_write(records, bytes(52))
                if existing:
                    write(records + 16, 0x400, existing, 0)
                assert call(0x4015381E) == limit
                assert call(0x401537E0) == limit - existing
                for size in (
                    0,
                    1,
                    8192 - 16,
                    8192 - 15,
                    SAMPLE_BYTES - 16,
                    SAMPLE_BYTES - 15,
                    STOCK_BYTES - 16,
                ):
                    rounded = (size + 0x200F) & ~0x1FFF
                    write(dest, 0xDEADBEEF)
                    result = call(0x401543A6, 0, 0, size, 0, dest) & 255
                    expected = int(existing + rounded <= limit)
                    assert result == expected, (name, existing, size, result, expected)
                    pointer = struct.unpack(">I", cpu.mem_read(dest, 4))[0]
                    assert pointer == (0x400 + existing if expected else 0xDEADBEEF)
                    cases.append(
                        dict(
                            image=name,
                            existing=existing,
                            size=size,
                            accepted=bool(result),
                        )
                    )
            # Original empty-pool branch instructions; stop before their continuations.
            for pc, accept, reject, countreg, zeroreg in [
                (
                    0x40154482,
                    0x4015448E,
                    0x40154494,
                    r.UC_M68K_REG_D2,
                    r.UC_M68K_REG_D0,
                ),
                (
                    0x40154808,
                    0x40154816,
                    0x401547CA,
                    r.UC_M68K_REG_D6,
                    r.UC_M68K_REG_D7,
                ),
            ]:
                for size in (
                    SAMPLE_BYTES,
                    SAMPLE_BYTES + 8192,
                    STOCK_BYTES,
                    STOCK_BYTES + 8192,
                ):
                    reached = []

                    def end(uc, address, _size, _data, reached=reached):
                        reached.append(address)
                        uc.emu_stop()

                    hooks = [
                        cpu.hook_add(UC_HOOK_CODE, end, begin=a, end=a)
                        for a in (accept, reject)
                    ]
                    cpu.reg_write(countreg, size)
                    cpu.reg_write(zeroreg, 0)
                    cpu.emu_start(pc, stop, count=20)
                    for hook in hooks:
                        cpu.hook_del(hook)
                    assert reached == [accept if size <= limit else reject]
        report.update(
            status="passed",
            tail_cases=cases,
            empty_branch_cases=16,
            source_hashes=sources,
            reference_helpers_stubbed=sorted(set(stub_calls)),
        )
        require(source_hashes() == sources, "Source drift")
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k not in ("source_hashes", "tail_cases")
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
