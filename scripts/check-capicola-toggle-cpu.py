#!/usr/bin/env python3
"""Execute the optional CAPI control and feedback helpers on native ColdFire."""

# ruff: noqa: E402
import argparse
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import require, settings, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--package", type=Path, required=True)
args = parser.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc
from unicorn import m68k_const as k

from lab.capicola_toggle import BASE, RX_DRIVER, RX_WORD, TITLES, patch_cpu, requested

report = dict(status="running", firmware="OS1.16", hardware_verified=False)
sources = source_hashes()
try:
    package = args.package.resolve()
    manifest = json.loads((package / "manifest.json").read_text())
    combined = manifest['cpu'].get('native')
    if combined:
        from lab.cpu_fixture import load_package

        image, combined, _manifest = load_package(package)
        meta = manifest['cpu']['capi_toggle']
        baseline = (package / 'cpu-base/RESERVED_NO_TOGGLE_MAIN.bin').read_bytes()
        legacy = patch_cpu(baseline)[0]
        require(__import__('hashlib').sha256(legacy).hexdigest() ==
                '7f911a1e68158f991f9327d8cfae10a143824959f319b930eb4f3e40a9cba989',
                'Legacy CAPI oracle changed')
        for w in meta['writes']:
            off = w['address'] - BASE
            require(image[off:off + len(bytes.fromhex(w['after']))] == bytes.fromhex(w['after']),
                    'Combined image changed CAPI ' + w['label'])
    else:
        image = (package / "PLAITS_R3_FLEX_CAPICOLA_MAIN_OS.bin").read_bytes()
        meta = manifest["cpu"]["capi_toggle"]
        baseline = bytearray(image[:0x31FB60])
        for w in meta["writes"]:
            if w["address"] < 0x40320000:
                start = w["address"] - BASE
                baseline[start:start + len(bytes.fromhex(w["before"]))] = bytes.fromhex(w["before"])
        require(patch_cpu(bytes(baseline))[0] == image, "Package differs from current patch")
    require(patch_cpu(bytes(baseline), enabled=False)[0] == baseline,
            "Disabled patch changed bytes")
    u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    u.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
    for address, size in (
        (0x40000000, 0x400000),
        (0x81000000, 0x10000),
        (0x80000000, 0x10000),
        (0x4293B000, 0x1000),
        (0x4316E000, 0x2000),
    ):
        u.mem_map(address, size)
    if combined:
        from lab.cpu_extension import START, LIMIT
        u.mem_map(START, LIMIT - START)
    sp, end, dest = 0x81008000, 0x81000000, 0x81001000
    regs = [getattr(k, f"UC_M68K_REG_{p}{i}") for p in ("D", "A") for i in range(8)]

    def load(binary):
        u.mem_write(BASE, bytes(binary))
        u.ctl_remove_cache(BASE, BASE + len(image))
        if combined and bytes(binary) == image:
            from lab.cpu_fixture import segments
            for segment in segments(image, combined):
                u.mem_write(segment.destination, segment.data + bytes(segment.bss))
        u.reg_write(k.UC_M68K_REG_SR, 0x2000)
        u.reg_write(k.UC_M68K_REG_A7, sp)
        u.mem_write(sp, struct.pack(">I", end))
        # Run the real extended initializer; helpers must execute from SRAM,
        # not from their external source which native reset will erase.
        u.emu_start(0x4000045C, end, count=500000)
        require(u.reg_read(k.UC_M68K_REG_PC) == end, "Native SRAM copy incomplete")
        u.emu_start(0x401C4938, 0x401C49A0, count=100)

    def call(pc, *values, stop=end, initial=None):
        u.reg_write(k.UC_M68K_REG_SR, 0x2000)
        for i, r in enumerate(regs):
            u.reg_write(r, (initial or [0] * 16)[i])
        u.reg_write(k.UC_M68K_REG_A7, sp)
        u.mem_write(sp, struct.pack(">" + "I" * (len(values) + 1), end, *values))
        u.emu_start(pc, stop, count=20000)
        require(u.reg_read(k.UC_M68K_REG_PC) == stop, f"Incomplete call {pc:#x}")
        return u.reg_read(k.UC_M68K_REG_D0)

    load(image)
    if combined:
        from lab.plaits_integration import MODEL_NAMES
        integration = combined['base']['plaits_integration']
        for raw, name in [(i * 256, n) for i, n in enumerate(MODEL_NAMES)] + [(0xffffffff, MODEL_NAMES[0])]:
            call(integration['model_formatter'], raw, dest)
            require(bytes(u.mem_read(dest, 32)).split(b'\0')[0].decode() == name,
                    'Combined Plaits formatter')
        for raw, name in ((0, '100 ms'), (2304, '1000 ms'), (32512, '12800 ms')):
            call(integration['duration_formatter'], raw, dest)
            require(bytes(u.mem_read(dest, 32)).split(b'\0')[0].decode() == name,
                    'Combined Plaits duration')
        report['plaits_models'] = list(MODEL_NAMES)
        report['plaits_duration_bounds'] = True
        require(call(0x400C8840, 7) == 0x403118C4, 'Combined Plaits descriptor')
    ptr = call(0x400C8840, 2)
    require(ptr == meta["descriptor"], "Native descriptor dispatch failed")
    require(
        struct.unpack(">9I", u.mem_read(ptr + 8, 36)) == tuple(meta["fields"]),
        "Wrong SRC fields",
    )
    require(call(0x400D9ED8, 204) == 27, "Wrong native mirror")
    for raw in range(65536):
        u.mem_write(dest - 4, b"Z" * 12)
        size = call(meta["formatter"], raw, dest)
        expected = b"ON\0\0" if requested(raw) else b"OFF\0"
        require(
            bytes(u.mem_read(dest, 4)) == expected
            and size == (2 if requested(raw) else 3),
            "Formatter threshold",
        )
        require(
            bytes(u.mem_read(dest - 4, 4)) == b"Z" * 4
            and bytes(u.mem_read(dest + 4, 4)) == b"Z" * 4,
            "Formatter bounds",
        )
    report["formatter_cases"] = 65536
    # Native table validator: no hand-written substitute for range checks.
    for raw in (0, 1, 127, 128, 255, 256, 257, 32512, 65535, 0xFFFFFFFF):
        result = call(0x4003ADB4, 0, 204, raw)
        require(bool(result & 255) == (raw <= 256), "Native range validator")
        report.setdefault("range_results", []).append([raw, result])
    # Complete native permissions, reverse lookup, late repack and restore
    # comparisons. Distinct reverse-cache sentinels make accidental changes visible.
    u.mem_write(0x4316E000, b"".join(struct.pack(">I", i + 1000) for i in range(2048)))
    snapshots = []
    for binary in (baseline, image):
        load(binary)
        permissions = [
            call(0x400DA3B0, typ, track) for typ in range(9) for track in range(17)
        ]
        reverse = [
            call(0x400DA23E, mirror, typ, flt)
            for mirror in range(72)
            for typ in range(9)
            for flt in range(7)
        ]
        repack = []
        for track in range(16):
            for typ in range(8):
                u.mem_write(0x80003CD0 + track * 0x9A, bytes([typ]))
                buf = 0x80005B50 + track * 142
                u.mem_write(buf, b"Z" * 142)
                initial = [0] * 16
                initial[6], initial[12] = track, buf
                call(0x4002E978, stop=0x4002E994, initial=initial)
                repack.append(bytes(u.mem_read(buf, 142)))
        snapshots.append(dict(permissions=permissions, reverse=reverse, repack=repack))
    if combined and combined.get('any_tracks'):
        # Only the explicitly unlocked Plaits permission/repack behavior differs.
        for track in range(16):
            snapshots[0]['permissions'][7*17+track] = 1
            snapshots[0]['repack'][track*8+7] = b'Z'*142
    require(
        snapshots[0] == snapshots[1],
        "Unchanged native mapping/permissions/repack drift",
    )
    report.update(permission_cases=153, reverse_cases=4536, repack_cases=128)
    load(image)
    cache = meta["cache"]
    for track in range(16):
        for state in range(7):
            u.mem_write(RX_WORD, struct.pack(">H", 0xD000 | track << 8 | state))
            call(meta["observer"])
            require(
                u.mem_read(cache + track, 1)[0] == state
                and u.mem_read(cache + 16 + track, 1)[0] == 32,
                "Observer track/state",
            )
    for word in (0, 0xFFFF, 0xD007, 0xC003):
        u.mem_write(RX_WORD, struct.pack(">H", word))
        call(meta["observer"])
        require(bytes(u.mem_read(cache, 32)) == bytes(32), "Invalid reply not cleared")
    u.mem_write(cache + 16, bytes([32]) * 16)
    u.mem_write(RX_WORD, struct.pack(">H", 0xDF02))
    for _ in range(32):
        call(meta["observer"])
    require(
        bytes(u.mem_read(cache + 16, 15)) == bytes(15), "Stale reply did not expire"
    )
    # Model only the existing peripheral driver boundary; execute wrapper/observer.
    seen = []

    def driver(uc, pc, size, context):
        if pc != RX_DRIVER:
            return
        stack = uc.reg_read(k.UC_M68K_REG_A7)
        seen.append(struct.unpack(">4I", uc.mem_read(stack + 4, 16)))
        for reg, value in (
            (k.UC_M68K_REG_D0, 0x10203040),
            (k.UC_M68K_REG_D1, 0x50607080),
            (k.UC_M68K_REG_A0, 0x12345678),
            (k.UC_M68K_REG_A1, 0x98765432),
        ):
            uc.reg_write(reg, value)
        uc.reg_write(k.UC_M68K_REG_SR, 0x2015)
        uc.reg_write(k.UC_M68K_REG_PC, int.from_bytes(uc.mem_read(stack, 4), "big"))
        uc.reg_write(k.UC_M68K_REG_A7, stack + 4)

    hook = u.hook_add(UC_HOOK_CODE, driver)
    initial = [0xABC00000 + i for i in range(16)]
    call(meta["receiver"], 0x802, 0x80005348, 0xABC, 0x8000488C, initial=initial)
    require(seen == [(0x802, 0x80005348, 0xABC, 0x8000488C)], "RX argument forwarding")
    expected = initial[:]
    expected[0:2] = [0x10203040, 0x50607080]
    expected[8:10] = [0x12345678, 0x98765432]
    expected[15] = sp + 4
    require([u.reg_read(r) for r in regs] == expected, "RX result/register corruption")
    require(u.reg_read(k.UC_M68K_REG_SR) == 0x2015, "RX CCR corruption")
    u.hook_del(hook)
    # Page wrapper with three existing UI calls modeled as boundaries.
    view, widget, context = dest + 0x100, dest + 0x300, dest + 0x500
    updates, current_track = [], [0]

    def ui_boundary(uc, pc, size, data):
        if pc not in (0x4004ABE8, 0x4005B1E0, 0x4005B076):
            return
        stack = uc.reg_read(k.UC_M68K_REG_A7)
        if pc == 0x4004ABE8:
            require(
                int.from_bytes(uc.mem_read(stack + 4, 4), "big") == context,
                "Wrong view context",
            )
            uc.reg_write(k.UC_M68K_REG_D0, current_track[0])
        elif pc == 0x4005B1E0:
            owner, title = struct.unpack(">II", uc.mem_read(stack + 4, 8))
            require(owner == widget, "Wrong caption widget")
            title = int.from_bytes(uc.mem_read(title, 4), "big")
            updates.append(bytes(uc.mem_read(title, 18)).decode())
            uc.mem_write(widget + 0x48, struct.pack(">I", title))
        else:
            uc.reg_write(k.UC_M68K_REG_D0, 0x12344321)
        uc.reg_write(k.UC_M68K_REG_PC, int.from_bytes(uc.mem_read(stack, 4), "big"))
        uc.reg_write(k.UC_M68K_REG_A7, stack + 4)

    hook = u.hook_add(UC_HOOK_CODE, ui_boundary)
    u.mem_write(view, struct.pack(">I", 0x401ED888))
    u.mem_write(view + 0x64, struct.pack(">I", 2))
    u.mem_write(view + 0x6C, struct.pack(">II", widget, 0))
    u.mem_write(view + 0x74, struct.pack(">I", context))
    initial = [0xB0000000 + i for i in range(16)]
    initial[10] = view
    cases = 0
    for track in range(16):
        current_track[0] = track
        u.mem_write(0x80003CD0 + track * 0x9A, b"\2")
        for raw in (0, 127, 128, 256, 257):
            u.mem_write(0x80003398 + track * 0x8E, struct.pack(">H", raw))
            for state in range(7):
                u.mem_write(cache + track, bytes([state]))
                u.mem_write(cache + 16 + track, b"\x20")
                u.mem_write(widget + 0x48, struct.pack(">I", meta["title_pointers"][0]))
                want = 7 if state in (0, 1, 2, 6) and not requested(raw) else state
                before = len(updates)
                result = call(meta["refresh"], widget, initial=initial)
                actual = bytes(
                    u.mem_read(int.from_bytes(u.mem_read(widget + 0x48, 4), "big"), 18)
                ).decode()
                require(
                    actual == TITLES[want] and result == 0x12344321,
                    "SRC title/result mismatch",
                )
                saved = [u.reg_read(r) for r in regs]
                require(
                    saved[1:15] == initial[1:15] and saved[15] == sp + 4,
                    "SRC callee register corruption",
                )
                stable = len(updates)
                call(meta["refresh"], widget, initial=initial)
                require(len(updates) == stable, "Stable caption rewritten")
                require(stable - before <= 1, "Multiple caption writes")
                cases += 1
    for page, typ, track in ((1, 2, 0), (2, 1, 0), (2, 2, 16)):
        u.mem_write(view + 0x64, struct.pack(">I", page))
        u.mem_write(0x80003CD0, bytes([typ]))
        current_track[0] = track
        before = len(updates)
        call(meta["refresh"], widget, initial=initial)
        require(len(updates) == before, "Other page/type/track changed")
    u.hook_del(hook)
    require(source_hashes() == sources, "Source drift")
    report.update(
        status="passed",
        sources=sources,
        title_cases=cases,
        receiver_abi=True,
        status_aging=True,
        scope="Native CPU helpers and comparisons; UI peripheral calls modeled only for ABI checks",
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
