"""Bounded native-SHARC replay for the local DTII machine experiment."""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import struct
import subprocess
import time
from pathlib import Path

from lab.formats import read_frames
from lab.metrics import distribution
from lab.runtime import (
    ARENA,
    LIB,
    OUT,
    PACK,
    PROFILE,
    REPO,
    ROOT,
    SELACHE,
    STOCK_BLOB,
    sharc_profile,
)


def assemble(source):
    from sharc_selache import SelacheOracle

    run = SelacheOracle.open(SELACHE).assemble_text(source)
    if not run.comparison.all_extents_agree:
        raise ValueError("Assembler and DigiKit instruction widths disagree")
    return run


def header(target, count):
    # Same core/signature and data-block flags as the stock loader stream.
    result = bytearray(struct.pack("<IIII", 0xAD000001, target, count, 0))
    checksum = 0
    for byte in result:
        checksum ^= byte
    result[2] ^= checksum
    return bytes(result)


def build_route_blob(sine=False, controls=False):
    import sharcldr

    if controls and not sine:
        raise ValueError("Controls require the SINE renderer")
    raw = bytearray(STOCK_BLOB.read_bytes())
    if hashlib.sha256(raw).hexdigest() != PROFILE["stock_blob_sha256"]:
        raise ValueError("Wrong DSP firmware")
    blocks = sharcldr.parse_blocks(raw)
    memory = sharcldr.LoadedMemory.from_stream(raw, blocks)
    if any(
        a < ARENA + 0x2000 and b > ARENA
        for a, b in zip(memory._segments[0], memory._segments[1], strict=True)
    ):
        raise ValueError("Experiment arena overlaps a loader segment")
    route = assemble(".section/pm seg_pmco;\nI3 = 0x200f0000;\n")
    offset = sharcldr.offset_for_address(blocks, 0x1C2731)
    if bytes(raw[offset : offset + 6]).hex() != "130f2500c067":
        # Get the exact expected stock instruction from the same public encoder.
        expected = assemble(".section/pm seg_pmco;\nI3 = 0x2567c0;\n").boot_bytes
        if raw[offset : offset + 6] != expected:
            raise ValueError("Remap pointer instruction mismatch")
    raw[offset : offset + 6] = route.boot_bytes
    arena = bytearray(0x2000)
    arena[:32] = struct.pack("<8I", 0, 1, 2, 3, 4, 0, 5, 5)
    if sine:
        from sharc_selache import compare_listing, find_elf_section, swap_parcels

        toolchain = SELACHE / "target/release"
        machine = ROOT / "machines" / ("sine-controls" if controls else "sine")
        subprocess.run(
            [
                str(toolchain / "selas"),
                "-proc",
                "ADSP-21569",
                "-o",
                str(OUT / "sine.doj"),
                str(machine / "dsp.s"),
            ],
            check=True,
            timeout=60,
        )
        subprocess.run(
            [
                str(toolchain / "seld"),
                "-proc",
                "ADSP-21569",
                "-T",
                str(ROOT / "machines/sine/memory.ldf"),
                "-o",
                str(OUT / "sine.dxe"),
                str(OUT / "sine.doj"),
            ],
            check=True,
            timeout=60,
        )
        listing = subprocess.check_output(
            [str(toolchain / "seldump"), "-ns", "sine_code", str(OUT / "sine.dxe")],
            text=True,
            timeout=60,
        )
        if not compare_listing(listing).all_extents_agree:
            raise ValueError("Linked sine instruction widths disagree")
        code = bytearray(swap_parcels(find_elf_section(OUT / "sine.dxe", "sine_code")))
        hook_offset = sharcldr.offset_for_address(blocks, 0x1C4F15)
        displaced = bytes(raw[hook_offset : hook_offset + 6])
        if displaced.hex() != "5499a801408c":
            raise ValueError(f"Unexpected displaced instructions: {displaced.hex()}")
        if code[-12:-6] != bytes.fromhex("010001000100"):
            raise ValueError("Fallback NOP placeholder mismatch")
        code[-12:-6] = displaced
        if len(code) > 2048:
            raise ValueError("Sine code exceeded 2 KiB allowance")
        raw[hook_offset : hook_offset + 6] = assemble(
            ".section/pm seg_pmco;\nJUMP 0xbf8800;\n"
        ).boot_bytes
        arena[0x1000 : 0x1000 + len(code)] = code
        for i in range(256):
            struct.pack_into(
                "<f", arena, 0x400 + 4 * i, math.sin(2 * math.pi * i / 256)
            )
        if controls:
            # MIDI-indexed DDS increments, with one extra entry for interpolation.
            for i in range(129):
                increment = (2**32) * 440 * 2 ** ((i - 69) / 12) / 96000
                struct.pack_into("<f", arena, 0x800 + 4 * i, increment)
        (OUT / "sine-listing.txt").write_text(listing)
        (OUT / "sine-code.bin").write_bytes(code)
    final = blocks[-1]
    if final["flags"] != ["bit0", "FINAL"] or final["byte_count"] != 0:
        raise ValueError("Unexpected final loader block")
    split = final["offset"]
    result = bytes(raw[:split]) + header(ARENA, len(arena)) + arena + bytes(raw[split:])
    check = sharcldr.parse_blocks(result)
    if len(check) != len(blocks) + 1 or check[-1]["payload_offset"] != len(result):
        raise ValueError("Extended loader stream failed parsing")
    (OUT / ("SINE_BLOB.bin" if sine else "TEST_BLOB.bin")).write_bytes(result)
    (OUT / "route-listing.txt").write_text(route.listing)
    return result


class Dsp:
    def __init__(self, blob=None):
        import sharc_harness as h
        import sharc_transpile_run as native
        import sharcldr

        self.h, self.native = h, native
        self.profile = sharc_profile()
        pack = PACK.read_bytes()
        if pack[:8] != b"SHFP\x01\x00\x00\x00":
            raise ValueError("Expected SHFP v1 state pack")
        size = struct.unpack_from("<I", pack, 8)[0]
        image = pack[12 : 12 + size]
        at = 12 + size
        size = struct.unpack_from("<I", pack, at)[0]
        state = pack[at + 4 : at + 4 + size]
        at += 4 + size
        if blob is not None:
            image = native.pack_image(sharcldr.LoadedMemory.from_stream(blob))
        self.core = native.NativeCore(image, str(LIB))
        rc = self.core._lib.sharc_native_import_state(
            self.core._handle, state, len(state)
        )
        if rc != 0:
            raise RuntimeError(f"Native state import failed: {rc}")
        count = struct.unpack_from("<I", pack, at)[0]
        at += 4
        for _ in range(count):
            key, value = struct.unpack_from("<Iq", pack, at)
            at += 12
            self.core.set_option(key, value)
        self.core.set_option(native.OPT_BLOCKS, 0)
        # Decode the image actually loaded, including experiment instructions.
        self.core.set_option(native.OPT_RUNTIME_DECODE, 1)
        self.instructions = 0
        self.source = []
        self.block_instructions = []
        self.block_host_us = []

    def call(self, pc, limit):
        self.core.fresh_call(pc)
        self.core.run(limit)
        why = self.core.halt_reason or ""
        if "return without followed call" not in why:
            raise RuntimeError(f"DSP call {pc:#x}: {why}")

    def frame(self, wire):
        import sharc_trace as st

        core, p, h = self.core, self.profile, self.h
        shift = core.peek(p.command_word_shift_src) & 1
        base = p.command_word + (1 - shift) * h.RING_SIZE_BYTES
        data = h._swap16(wire[: h.RING_SIZE_BYTES])
        if core.poke(base, data, 1) != len(data):
            raise RuntimeError("DMA input write failed")
        core.set_reg(st.UREG_CODES["R8"], st.Const(h.DMA_SHIFT_CALLBACK_COMPLETE_EVENT))
        self.call(h.DMA_SHIFT_CALLBACK, 64)
        before = core.stats()["instructions"]
        started = time.perf_counter_ns()
        self.call(p.block_handler, 4_000_000)
        self.block_host_us.append((time.perf_counter_ns() - started) / 1000)
        self.block_instructions.append(core.stats()["instructions"] - before)
        channels = []
        for voice in (0, 1):
            base = p.voice_records + voice * h.VOICE_RECORD_STRIDE + h.FIELD_WORK_BUFFER
            words = [core.peek(base + i * 4) or 0 for i in range(64)]
            samples = struct.unpack("<64f", struct.pack("<64I", *words))
            if voice == 0:
                self.source = list(samples)
            channels.append(
                [0.5 * (samples[i] + samples[i + 1]) for i in range(0, 64, 2)]
            )
        return [value for pair in zip(*channels, strict=True) for value in pair]


def render(
    machine_type,
    route,
    count=450,
    as_stock=False,
    sine=False,
    preroll=0,
    capture=None,
    label=None,
):
    from live_gui_check import write_wav

    capture = Path(capture) if capture else OUT / f"type-{machine_type}.dtfr"
    frames = read_frames(capture)
    if as_stock:
        # Controlled comparator: same genuine CPU capture, only type 7 -> 6.
        converted = []
        for frame in frames:
            frame = bytearray(frame)
            if frame[0x94:0x96] == b"\0\7":
                frame[0x94:0x96] = b"\0\6"
            converted.append(bytes(frame))
        frames = converted
    if preroll:
        trig = next(i for i, frame in enumerate(frames) if frame[0x22:0x24] != b"\0\0")
        if preroll < trig:
            raise ValueError("Pre-roll cannot move trigger earlier")
        frames = [frames[0]] * (preroll - trig) + frames
    blob = build_route_blob(sine=sine) if route or sine else None
    dsp = Dsp(blob)
    # Preserve actual captured bytes. Repeat only a captured non-trigger tail.
    if any(
        frames[-1][offset : offset + 2] != b"\0\0"
        for offset in (0x22, 0x24, 0x26, 0x28)
    ):
        raise ValueError("Tail frame still contains one-shot events")
    name = f"type-{machine_type}-{'route' if route else 'stock'}"
    if as_stock:
        name += "-comparator"
    if sine:
        name += "-sine"
    if label:
        if not all(c.isalnum() or c in "-_" for c in label):
            raise ValueError("Output label must be a simple filename stem")
        name = label
    samples = array.array("f")
    source = array.array("f")
    started = time.monotonic()
    trace = []
    for i in range(count):
        wire = frames[i] if i < len(frames) else frames[-1]
        block = dsp.frame(wire)
        samples.extend(block)
        source.extend(dsp.source)
        if i < 12:
            trace.append(
                {
                    "frame": i,
                    "wire_type": int.from_bytes(wire[0x94:0x96], "big"),
                    "cached_type": dsp.core.peek(0x255970, 2),
                    "selector": dsp.core.peek(0x250738),
                    "peak": max(map(abs, block)),
                }
            )
    report = {
        "frames": count,
        "peak": max(map(abs, samples)),
        "finite": all(map(math.isfinite, samples)),
        "trace": trace,
        "seconds": time.monotonic() - started,
        "stats": dsp.core.stats(),
        "pcm_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
        "dsp_blob_sha256": hashlib.sha256(blob or STOCK_BLOB.read_bytes()).hexdigest(),
    }
    report["sine_executions"] = dsp.core.peek(ARENA + 0x130)
    report["sine_state"] = [dsp.core.peek(ARENA + 0x100 + i * 4) for i in range(12)]
    report["source_peak"] = max(map(abs, source))
    report["source_finite"] = all(map(math.isfinite, source))
    report["capture"] = str(capture)
    report["capture_sha256"] = hashlib.sha256(capture.read_bytes()).hexdigest()
    report["preroll_trigger_frame"] = preroll if preroll else None
    report["sample_rates"] = {"source": 96000, "captured_stereo": 48000}
    report["output_boundary"] = "voice work buffers decimated; not final hardware mix"
    report["profile"] = {
        "boundary": "Whole emulated DSP block handler; excludes DMA callback and Python output tap",
        "instruction_unit": "emulated retired instructions, not physical clock cycles",
        "instructions_per_block": distribution(dsp.block_instructions),
        "host_us_per_block": distribution(dsp.block_host_us),
        "target_cpu_load_percent": None,
        "target_dsp_load_percent": None,
    }
    (OUT / f"{name}-profile.json").write_text(
        json.dumps(
            {
                "instructions": dsp.block_instructions,
                "host_us": dsp.block_host_us,
                "scope": report["profile"],
            },
            indent=2,
        )
        + "\n"
    )
    if sine:
        report["assembly_sha256"] = hashlib.sha256(
            (ROOT / "machines/sine/dsp.s").read_bytes()
        ).hexdigest()
        report["code_bytes"] = (OUT / "sine-code.bin").stat().st_size
    write_wav(str(OUT / f"{name}.wav"), samples)
    (OUT / f"{name}.f32").write_bytes(samples.tobytes())
    (OUT / f"{name}-source.f32").write_bytes(source.tobytes())
    (OUT / f"{name}.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


def main():
    os.chdir(REPO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", type=int, choices=(6, 7), default=7)
    parser.add_argument("--route", action="store_true")
    parser.add_argument("--frames", type=int, default=450)
    parser.add_argument("--as-stock", action="store_true")
    parser.add_argument("--sine", action="store_true")
    parser.add_argument("--preroll", type=int, default=0)
    parser.add_argument("--capture")
    parser.add_argument("--label")
    args = parser.parse_args()
    if not 1 <= args.frames <= 2000:
        raise ValueError("Render bound is 1..2000 frames")
    render(
        args.type,
        args.route,
        args.frames,
        args.as_stock,
        args.sine,
        args.preroll,
        args.capture,
        args.label,
    )


if __name__ == "__main__":
    main()
