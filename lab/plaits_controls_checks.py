"""Focused state and PCM checks for the new compiled control adapter."""

import hashlib
import math
import re
import struct

from lab.dsp import Dsp
from lab.plaits import build_blob
from lab.project import ROOT, require, sha256
from lab.runtime import STOCK_MAIN


def adapter_checks(blob, output):
    import sharc_trace as st

    def entry(folder):
        return int(
            re.search(
                r"(?m)^machine\.:\n\s+([0-9a-f]+)", (folder / "listing.txt").read_text()
            )[1],
            16,
        )

    pc = entry(output / "firmware")
    old = build_blob(True, family="bank", output=output / "bank-reference")
    oldpc = entry(output / "bank-reference")

    def peek(c, addr, size=352):
        return struct.pack(
            f"<{size // 4}I", *(c.peek(addr + i) for i in range(0, size, 4))
        )

    def invoke(e, model, trigger=0, macros=(0, 0, 0), lane=0, typ=7, previous=False):
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
        scale = (768, 1023, 16384) if previous else (32512,) * 3
        vals = {
            0x255970: typ,
            0x24F0CC: trigger << (lane * 8),
            0x2558DE: 103 * 256,
            0x2559B6: 0,
            0x2559B8: round(macros[0] * scale[0]),
            0x2559BA: model * 256,
            0x2559BC: round(macros[1] * scale[1]),
            0x2559C2: round(macros[2] * scale[2]),
            0x2559C4: 32768,
            0x2559C8: 16384,
        }
        for addr, v in vals.items():
            c.poke(addr, struct.pack("<I", v), 1)
        e.call(oldpc if previous else pc, 500000)
        return peek(c, (0x2412CC, 0x2414A4)[lane] + 4, 256)

    results = []
    for model in range(6):
        a, b = Dsp(blob), Dsp(old)
        for i in range(20):
            require(
                invoke(a, model, i == 0) == invoke(b, model, i == 0, previous=True),
                "Old bank endpoint PCM changed",
            )
        outputs = []
        for _repeat in range(2):
            a = Dsp(blob)
            pcm = b""
            for i in range(120):
                pcm += invoke(
                    a,
                    model,
                    i == 0,
                    (0.75, 0.25, 0.5) if 40 <= i < 80 else (0.25, 0.5, 0.75),
                )
                require(
                    a.core.peek(0x200E1000 + 328) == (i + 1) * 64,
                    "Macro change reset note age",
                )
            floats = struct.unpack(f"<{len(pcm) // 4}f", pcm)
            require(
                all(map(math.isfinite, floats)) and 1e-4 < max(map(abs, floats)) < 4,
                "Invalid adapter output",
            )
            outputs.append(pcm)
        require(outputs[0] == outputs[1], "Adapter exact repeat failed")
        reset = b"".join(
            invoke(
                a,
                model,
                i == 0,
                (0.75, 0.25, 0.5) if 40 <= i < 80 else (0.25, 0.5, 0.75),
            )
            for i in range(120)
        )
        require(reset == pcm, "Retrigger differs from fresh state")
        results.append(
            {
                "model": model,
                "repeat_exact": True,
                "retrigger_exact": True,
                "constant_endpoint_old_bank_exact": True,
                "sha256": hashlib.sha256(pcm).hexdigest(),
                "peak": max(map(abs, floats)),
            }
        )
        print("Adapter model", model, "passed", flush=True)
    a, b = Dsp(blob), Dsp(blob)
    changed = frozen = b""
    for i in range(120):
        changed += invoke(
            a, 3, i == 0, (0.75, 0.25, 0.5) if 40 <= i < 80 else (0.25, 0.5, 0.75)
        )
        frozen += invoke(b, 3, i == 0, (0.25, 0.5, 0.75))
    require(changed != frozen, "Frozen macro negative not detected")
    invoke(a, 3, 1)
    invoke(b, 3, 1)
    for _ in range(5):
        require(invoke(a, 5) == invoke(b, 3), "MODEL changed sound without trigger")
        require(
            peek(a.core, 0x200E1000) == peek(b.core, 0x200E1000),
            "MODEL changed state without trigger",
        )
    invoke(a, 5, 1, lane=1)
    untouched = peek(a.core, 0x200E1160)
    invoke(a, 4, 1, macros=(0.1, 0.2, 0.3))
    require(peek(a.core, 0x200E1160) == untouched, "Cross-lane state changed")
    invoke(a, 0, typ=6)
    require(
        a.core.peek(0x200E1000 + 336) == 0 and invoke(a, 0) == bytes(256),
        "Switch-away/silent return failed",
    )
    import json

    prior = json.loads((ROOT / "out/runs/bank-final-01/report.json").read_text())
    require(
        sha256(output / "bank-reference/PLAITS_BLOB.bin")
        == prior["outputs"]["firmware/PLAITS_BLOB.bin"],
        "Old bank image drift",
    )
    return {
        "models": results,
        "macro_age_continuous": True,
        "frozen_macro_negative": True,
        "model_trigger_latched": True,
        "lane_isolation": True,
        "switch_silent_return": True,
        "old_bank_image_exact": True,
        "scope": "Direct compiled SHARC adapter calls; synthetic control vectors",
    }


def cpu_checks(p, *, integration=False):
    import json
    import struct

    from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc
    from unicorn import m68k_const as k

    from lab.plaits_controls import BASE, COUNT, ROWS, TABLE

    new = (p / "PLAITS_MAIN_OS.bin").read_bytes()
    old = STOCK_MAIN.read_bytes()
    m = json.loads((p / "macro-cpu-patches.json").read_text())
    limit = 279 if integration else 278
    if integration:
        extra = json.loads((p / "integration-cpu-patches.json").read_text())
        m["helpers"][0]["address"] = extra["first_helper"]
    regs = {
        f"{pre}{i}": getattr(k, f"UC_M68K_REG_{pre.upper()}{i}")
        for pre in ("d", "a")
        for i in range(8)
    }
    u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    u.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
    u.mem_map(0x40000000, 4194304)
    u.mem_write(BASE, new)
    u.mem_map(0x81000000, 65536)
    # Execute the real restore span, including its bound load and the next
    # field's validation. Compare all 256 serialized machine byte values;
    # only type 7 may change. The 0xff sentinel keeps its stock behavior.
    restore_results = []
    for image in (old, new):
        u.mem_write(BASE, image)
        u.ctl_remove_cache(BASE, BASE + len(image))
        results = []
        for typ in range(256):
            for adjacent in (0, 6, 7, 255):
                u.reg_write(k.UC_M68K_REG_SR, 0x2000)
                for r in regs.values():
                    u.reg_write(r, 0)
                u.reg_write(k.UC_M68K_REG_A0, 0x40213754)
                u.reg_write(k.UC_M68K_REG_A2, 0x81001000)
                u.reg_write(k.UC_M68K_REG_A3, 0x81002000)
                u.mem_write(0x81001000, bytes([0x5A]) * 256)
                u.mem_write(0x81002000, bytes(256))
                u.mem_write(0x810020D2, bytes((typ, adjacent)))
                u.emu_start(0x400DB2EA, 0x400DB342, count=100)
                require(
                    u.reg_read(k.UC_M68K_REG_PC) == 0x400DB342,
                    "Restore span did not complete",
                )
                results.append(bytes(u.mem_read(0x81001000, 256)))
        restore_results.append(results)
    for n, (stock_result, result) in enumerate(zip(*restore_results, strict=True)):
        expected = bytearray(stock_result)
        if n // 4 == 7:
            require(expected[0xA2] == 0, "Stock restore negative changed")
            expected[0xA2] = 7
        require(result == expected, "Track restore changed another field or type")
    u.mem_write(BASE, new)
    u.ctl_remove_cache(BASE, BASE + len(new))
    n = 0
    for helper in m["helpers"]:
        (src, scale, dst, op, field) = helper["key"]
        addr = helper["address"]
        for idx in list(range(limit)) + [limit, limit + 1, 1000]:
            initial = {x: 0x12340000 + i for (i, x) in enumerate(regs)}
            initial["a7"] = 0x81008000
            initial[src] = idx * scale
            u.reg_write(k.UC_M68K_REG_SR, 8197)
            for x, r in regs.items():
                u.reg_write(r, initial[x])
            u.mem_write(initial["a7"], struct.pack(">I", 0x40001000))
            u.emu_start(addr, 0x40001000, count=100)
            expected = dict(initial)
            expected["a7"] += 4
            base = (ROWS - COUNT * 60 if 275 <= idx < limit else TABLE) + field
            expected[dst] = base + (initial[dst] if op != "lea" else 0) & 0xFFFFFFFF
            for x, r in regs.items():
                require(
                    u.reg_read(r) == expected[x],
                    (helper, idx, x, hex(u.reg_read(r)), hex(expected[x])),
                )
            require(
                u.reg_read(k.UC_M68K_REG_SR) & 31 == (0 if op == "addi" else 5),
                (helper, idx, "ccr", hex(u.reg_read(k.UC_M68K_REG_SR))),
            )
            n += 1
    print("PASS", n, "sparse resolver/register cases")
    for start, offset, signed in [
        (0x400D9ED8, 4, False),
        (0x400D9EFC, 0, False),
        (0x400DA48E, 20, False),
        (0x400DA4B8, 24, True),
        (0x400DA4DC, 26, True),
        (0x400DA500, 28, False),
        (0x400DA524, 36, False),
        (0x400DA330, 32, False),
    ]:
        for idx in list(range(limit)) + [limit, limit + 1, 0xFFFFFFFF]:
            u.reg_write(k.UC_M68K_REG_SR, 8192)
            u.reg_write(k.UC_M68K_REG_A7, 0x81008000)
            u.mem_write(0x81008000, struct.pack(">II", 0x40001000, idx))
            u.emu_start(start, 0x40001000, count=200)
            row = (
                ROWS + (idx - 275) * 60
                if 275 <= idx < limit
                else TABLE + (idx if idx < 275 else 0) * 60
            )
            size = 2 if signed else 4
            v = (
                int.from_bytes(u.mem_read(row + offset, size), "big", signed=signed)
                & 0xFFFFFFFF
            )
            require(
                u.reg_read(k.UC_M68K_REG_D0) == v,
                (hex(start), idx, hex(u.reg_read(k.UC_M68K_REG_D0)), hex(v)),
            )
    print("PASS complete parameter accessors old/new/fallback")
    for idx in list(range(limit)) + [limit, limit + 1, 0xFFFFFFFF]:
        u.reg_write(k.UC_M68K_REG_SR, 8192)
        u.reg_write(k.UC_M68K_REG_A7, 0x81008000)
        u.mem_write(0x81008000, struct.pack(">II", 0x40001000, idx))
        u.emu_start(0x400C87CA, 0x40001000, count=200)
        expected = 0x4293C040 + 68 * (
            250 if 275 <= idx < limit else idx if idx < 275 else 0
        )
        require(
            u.reg_read(k.UC_M68K_REG_D0) == expected,
            (idx, hex(u.reg_read(k.UC_M68K_REG_D0)), hex(expected)),
        )
    for idx in range(limit):
        row = ROWS + (idx - 275) * 60 if idx >= 275 else TABLE + idx * 60
        (lo, hi) = struct.unpack(">ii", u.mem_read(row + 8, 8))
        for value in (lo - 1, lo, hi, hi + 1):
            u.reg_write(k.UC_M68K_REG_SR, 8192)
            u.reg_write(k.UC_M68K_REG_A7, 0x81008000)
            u.mem_write(
                0x81008000, struct.pack(">IIII", 0x40001000, 0, idx, value & 0xFFFFFFFF)
            )
            u.emu_start(0x4003ADB4, 0x40001000, count=500)
            require(
                bool(u.reg_read(k.UC_M68K_REG_D0) & 255) == (lo <= value <= hi),
                (idx, value, lo, hi),
            )
    for idx in range(275):
        if idx == 250:
            continue
        off = TABLE - BASE + idx * 60
        require(new[off : off + 60] == old[off : off + 60], idx)
    print(
        "PASS complete UI behavior and range validator; stock rows unchanged except MODEL"
    )
    u.mem_map(0x80003000, 16384)
    for typ in range(8):
        for value in (0, 1, 519, 5639, 16384, 32512):
            initial = {x: 0x12340000 + i for (i, x) in enumerate(regs)}
            initial["a7"] = 0x81008000
            u.reg_write(k.UC_M68K_REG_SR, 8197)
            for x, r in regs.items():
                u.reg_write(r, initial[x])
            u.mem_write(0x80003CD0, bytes([typ]))
            u.mem_write(0x80003396, struct.pack(">HHH", value, 768, value))
            u.mem_write(0x800033A0, struct.pack(">HH", value, 2304))
            baseline = bytes([90]) * 4096
            u.mem_write(0x80005B50, baseline)
            u.emu_start(0x40311D04, 0x400D934C, count=100)
            expected = bytearray(baseline)
            if typ == 7:
                expected[0x56:0x5A] = struct.pack(">HH", value, 768)
                expected[96:98] = struct.pack(">H", value)
                if integration:
                    expected[0x5A:0x5C] = struct.pack(">H", value)
                    expected[98:100] = struct.pack(">H", 2304)
            require(
                bytes(u.mem_read(0x80005B50, 4096)) == expected,
                (typ, value, "shim memory"),
            )
            for x, r in regs.items():
                require(
                    u.reg_read(r) == (0x80005B50 if x == "d0" else initial[x]),
                    (typ, value, x),
                )
    print(
        "PASS 48 transport shim type/value cases; stock types and other memory/registers unchanged"
    )
    for typ in () if integration else range(8):
        for value in (0, 1, 519, 1023, 1024, 1025, 5639, 16384, 32512, 65535):
            for flags in (0, 5, 16, 31):
                initial = {x: 0x12340000 + i for i, x in enumerate(regs)}
                initial["a7"] = 0x81008000
                u.reg_write(k.UC_M68K_REG_SR, 0x2000 | flags)
                for x, r in regs.items():
                    u.reg_write(r, initial[x])
                u.mem_write(0x81008000, struct.pack(">I", 0x40001000))
                u.mem_write(0x80003CD0, bytes([typ]))
                u.mem_write(0x8000339A, struct.pack(">H", value))
                baseline = bytes([0x5A]) * 0x1000
                u.mem_write(0x80005B50, baseline)
                u.emu_start(m["sample_shim"], 0x40001000, count=100)
                expected = bytearray(baseline)
                if typ == 7:
                    expected[0x5A:0x5C] = struct.pack(">H", value)
                require(
                    bytes(u.mem_read(0x80005B50, 0x1000)) == expected,
                    "Final TIMB transport changed wrong track/memory",
                )
                initial["a7"] += 4
                initial["a5"] = 0x8000483C
                require(
                    all(u.reg_read(r) == initial[x] for x, r in regs.items()),
                    "Final TIMB transport clobbered registers",
                )
                require(
                    u.reg_read(k.UC_M68K_REG_SR) & 31 == flags,
                    "Final TIMB transport changed CCR",
                )
    controls = json.loads((ROOT / "machines/plaits-controls/controls.json").read_text())
    for name, mirror in (("harmonics", 26), ("timbre", 28), ("morph", 31)):
        row = ROWS + (controls[name]["param_code"] - 275) * 60
        require(
            struct.unpack(">6I", u.mem_read(row, 24))
            == (6, mirror, 0, 32512, 16384, 0),
            "Macro metadata/default differs",
        )
    print(
        "PASS dedicated macro metadata"
        if integration
        else "PASS 320 final sample-slot transport cases and dedicated macro metadata"
    )
    return {
        "resolver_register_cases": n,
        "stock_ids": 275,
        "new_ids": limit - 275,
        "ui_and_range_checks": True,
        "transport_cases": 48 if integration else 368,
        "track_restore_cases": 1024,
        "stock_rows_preserved_except_existing_model": True,
    }
