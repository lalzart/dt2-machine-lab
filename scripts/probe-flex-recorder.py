#!/usr/bin/env python3
"""Inspect OS 1.16 and exercise its original save consumer with synthetic peers.

No firmware patch, real filesystem service, panel recording or SHARC execution.
The full pinned MAIN is loaded unchanged. Only named external callees are
intercepted; the save loop, PCM wrapper and lock helpers execute original bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".deps/digikit"))

from dt2.coldfire import disasm  # noqa: E402
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn import m68k_const as k  # noqa: E402

BASE = 0x40000400
MAIN_HASH = "57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d"
RESPONSE = 0x4FE79340
STAGING = 0x405A50B0
MUTEX = 0x40965B74
SENTINEL = 0x81000100

RANGES = {
    "service_and_locks": (0x400124A0, 0x40012562),
    "pcm_command4": (0x4001282E, 0x4001288A),
    "normalize_command5": (0x4001288A, 0x400128CA),
    "recorder_transitions": (0x40015FDA, 0x40016060),
    "save_worker": (0x4001F8B0, 0x4001F8D0),
    "post_normalize": (0x40020EDE, 0x40020F28),
    "save_trim_capture": (0x4002302E, 0x40023052),
    "response_getter_and_dma": (0x400CD482, 0x400CD638),
    "recorded_frame_count": (0x400CD6CE, 0x400CD6E2),
    "save_writer": (0x40153994, 0x40153B1E),
    "stereo_slot_header": (0x40153B28, 0x40153B90),
    "mono_slot_header": (0x40153B90, 0x40153BEA),
}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def occurrences(data, needle):
    result = []
    offset = data.find(needle)
    while offset >= 0:
        result.append(BASE + offset)
        offset = data.find(needle, offset + 1)
    return result


def source_bytes(start, count, stereo):
    words = []
    for frame in range(start, start + count):
        words.append((0x1000 + frame * 17) & 0xFFFF)
        if stereo:
            words.append((0x7000 - frame * 29) & 0xFFFF)
    return struct.pack(f">{len(words)}H", *words)


def run_writer(main, *, start, frames, stereo, fail_open=False):
    u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    u.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
    for addr, size in [
        (0x40000000, 0x400000),
        (0x405A5000, 0x9000),
        (0x4FE79000, 0x3000),
        (0x81000000, 0x10000),
    ]:
        u.mem_map(addr, size)
    u.mem_write(BASE, main)
    u.mem_write(0x81001000, b"/recorded/SYNTHETIC\0")
    u.mem_write(STAGING - 16, bytes(range(16)))
    sink = bytearray()
    events = []
    requests = []
    lock_depth = 0
    instructions = 0
    last_chunk = None
    ff1_emulations = 0

    def argument(n):
        sp = u.reg_read(k.UC_M68K_REG_A7)
        return struct.unpack(">I", u.mem_read(sp + 4 * n, 4))[0]

    def return_from_stub(value=0):
        sp = u.reg_read(k.UC_M68K_REG_A7)
        pc = struct.unpack(">I", u.mem_read(sp, 4))[0]
        u.reg_write(k.UC_M68K_REG_D0, value)
        u.reg_write(k.UC_M68K_REG_A7, sp + 4)
        u.reg_write(k.UC_M68K_REG_PC, pc)

    def observe(_uc, pc, _size, _user):
        nonlocal lock_depth, instructions, last_chunk, ff1_emulations
        instructions += 1
        if pc == 0x401539E2:
            # Same missing-opcode accommodation as DigiKit emu/harness.py.
            require(bytes(u.mem_read(pc, 2)) == bytes.fromhex("04c6"), "FF1 site drift")
            value = u.reg_read(k.UC_M68K_REG_D6) & 0xFFFFFFFF
            u.reg_write(k.UC_M68K_REG_D6, 32 - value.bit_length())
            u.reg_write(k.UC_M68K_REG_PC, pc + 2)
            ff1_emulations += 1
        elif pc == 0x40001608:
            require(argument(1) == MUTEX, "Unexpected lock object")
            lock_depth += 1
            events.append(["lock", lock_depth])
            return_from_stub()
        elif pc == 0x4000172A:
            require(argument(1) == MUTEX and lock_depth > 0, "Invalid unlock")
            lock_depth -= 1
            events.append(["unlock", lock_depth])
            if not lock_depth:
                # Model the shared response being reused immediately after unlock.
                u.mem_write(RESPONSE, bytes([0xA5]) * 0x800)
            return_from_stub()
        elif pc == 0x400124A0:
            size, desc, response_size = argument(1), argument(2), argument(3)
            require(size == 12 and response_size == 0x800, "Wrong service extent")
            command, channel, first, count = struct.unpack(
                ">HHII", u.mem_read(desc, 12)
            )
            require(command == 4 and channel == int(not stereo), "Wrong request")
            require(lock_depth == 2, "Save consumer did not retain outer lock")
            payload = source_bytes(first, count, stereo)
            require(len(payload) <= 0x800, "Response capacity exceeded")
            u.mem_write(RESPONSE, payload + bytes([0xE7]) * (0x800 - len(payload)))
            last_chunk = payload
            requests.append({"start": first, "frames": count, "channel": channel})
            events.append(["service", first, count])
            return_from_stub()
        elif pc in (0x40157192, 0x40156D9C):
            events.append(["mkdir" if pc == 0x40157192 else "reset_path"])
            return_from_stub()
        elif pc == 0x40158626:
            events.append(["open"])
            return_from_stub(1 if fail_open else 0)
        elif pc == 0x40158534:
            events.append(["reserve", argument(3)])
            return_from_stub()
        elif pc == 0x40135AD8:
            dest, length = argument(1), argument(2)
            require(length == 0x40, "Unexpected header clear")
            u.mem_write(dest, bytes(length))
            return_from_stub()
        elif pc == 0x401360AC:
            dest, src, length = argument(1), argument(2), argument(3)
            require(src == RESPONSE and lock_depth == 1, "Invalid copy lifetime")
            require(last_chunk is not None and length == len(last_chunk), "Copy extent")
            require(
                dest >= STAGING and dest + length <= STAGING + 0x8000, "Staging bounds"
            )
            u.mem_write(dest, bytes(u.mem_read(src, length)))
            events.append(["copy", length])
            return_from_stub(dest)
        elif pc == 0x4015838E:
            src, length = argument(1), argument(2)
            require(lock_depth == 0, "File write holds recorder lock")
            sink.extend(u.mem_read(src, length))
            events.append(["write", length])
            return_from_stub(length)
        elif pc in (0x4015B0CE, 0x401585E4):
            events.append(["finalize" if pc == 0x4015B0CE else "close"])
            return_from_stub()

    u.hook_add(UC_HOOK_CODE, observe)
    u.reg_write(k.UC_M68K_REG_SR, 0x2000)
    u.reg_write(k.UC_M68K_REG_A7, 0x81008000)
    u.mem_write(
        0x81008000,
        struct.pack(">IIIII", SENTINEL, 0x81001000, start, frames, int(stereo)),
    )
    try:
        u.emu_start(0x40153994, SENTINEL, timeout=5_000_000, count=200_000)
    except Exception as error:
        raise RuntimeError(
            f"Original writer stopped at PC={u.reg_read(k.UC_M68K_REG_PC):#x}; "
            f"last events={events[-6:]}: {error}"
        ) from error
    require(
        u.reg_read(k.UC_M68K_REG_PC) == SENTINEL, "Writer did not return within budget"
    )
    require(lock_depth == 0, "Unbalanced lock")
    require(bytes(u.mem_read(BASE, len(main))) == main, "Original code changed")
    if fail_open:
        require(not requests and not sink, "Open failure still read or wrote PCM")
    else:
        expected = source_bytes(start, frames, stereo)
        require(len(sink) == len(expected) + 0x50, "Unexpected saved extent")
        require(
            sink[0x40:-16] == expected,
            "Payload differs or shared-response poison escaped",
        )
        require(sink[-16:] == bytes(range(16)), "Trailer differs")
        require(sink[1] == int(stereo), "Header channel flag")
        require(
            struct.unpack(">II", sink[4:12]) == (len(expected), 48000),
            "Header length/rate",
        )
        require(
            sum(r["frames"] for r in requests) == frames, "Requested extent mismatch"
        )
        cursor = start
        for request in requests:
            require(request["start"] == cursor, "Noncontiguous source requests")
            cursor += request["frames"]
    return {
        "start": start,
        "frames": frames,
        "stereo": stereo,
        "fail_open": fail_open,
        "instructions_with_stubs": instructions,
        "requests": requests,
        "events": events,
        "file_bytes": len(sink),
        "file_sha256": sha(sink),
        "shared_response_poison_after_outer_unlock": True,
        "ff1_emulations": ff1_emulations,
        "code_unchanged": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output", type=Path, help="New directory below the lab's ignored out/"
    )
    parser.add_argument(
        "--main",
        type=Path,
        default=ROOT / ".local/fixture/sections/section_3_MAIN_OS.bin",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / "out"), "Output must stay in ignored out/")
    require(not output.exists(), "Use a fresh output directory")
    image = args.main.resolve().read_bytes()
    require(
        sha(image) == MAIN_HASH,
        "Unknown MAIN firmware; only authenticated OS 1.16 is accepted",
    )
    output.mkdir(parents=True)
    report = {
        "status": "running",
        "firmware": "Digitakt II OS 1.16",
        "main_sha256": sha(image),
        "started_utc": datetime.now(UTC).isoformat(),
        "script_sha256": sha(Path(__file__).read_bytes()),
        "scope": "Static byte inspection and isolated original CPU save consumer with synthetic service/file/mutex/memory helpers. No capture, storage, SHARC audio or hardware validation.",
    }
    try:
        raw_refs = {}
        for name, value in [
            ("pcm_wrapper", 0x4001282E),
            ("save_writer", 0x40153994),
            ("response", RESPONSE),
        ]:
            raw_refs[name] = [
                hex(a) for a in occurrences(image, struct.pack(">I", value))
            ]
        report["raw_absolute_occurrences_not_complete_callgraph"] = raw_refs
        report["slices"] = {}
        for name, (start, end) in RANGES.items():
            content = image[start - BASE : end - BASE]
            rows = list(disasm(image, BASE, start, min(end + 16, BASE + len(image))))
            text = (
                "\n".join(
                    f"{a:08x} {hx:24s} {mn:10s} {ops}"
                    for a, hx, mn, ops in rows
                    if a < end
                )
                + "\n"
            )
            (output / f"{name}.s").write_text(text)
            report["slices"][name] = {
                "start": hex(start),
                "end": hex(end),
                "sha256": sha(content),
            }
        report["cases"] = []
        for stereo in (False, True):
            for frames in (0, 1, 511, 512, 513, 1024, 1025, 20000):
                kwargs = {"start": 7, "frames": frames, "stereo": stereo}
                a, b = run_writer(image, **kwargs), run_writer(image, **kwargs)
                require(a == b, "Exact repeat differs")
                a["exact_repeat"] = True
                report["cases"].append(a)
        report["open_failure"] = run_writer(
            image, start=7, frames=20000, stereo=True, fail_open=True
        )
        require(
            sha(args.main.resolve().read_bytes()) == MAIN_HASH,
            "Input changed during run",
        )
        require(
            sha(Path(__file__).read_bytes()) == report["script_sha256"],
            "Probe changed during run",
        )
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"PASS: {len(report['cases'])} exact-repeat save-consumer vectors and open-failure control; {output / 'report.json'}"
    )


if __name__ == "__main__":
    main()
