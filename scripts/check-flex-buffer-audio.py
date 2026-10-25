#!/usr/bin/env python3
# ruff: noqa: E402
"""Replay buffer commits through stock SHARC against ordinary file loading.

Original CPU loader and original SHARC callbacks/renderers execute. Page DMA,
input/control delivery and the resource transaction remain explicit host models.
"""

import argparse
import array
import hashlib
import math
import os
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("workflow", type=Path)
p.add_argument("output", type=Path)
args = p.parse_args()
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.runtime import STOCK_MAIN  # isort: skip
import plusdrive_check as check
import tools.plusdrive as pd
from live_gui_check import write_wav

from lab.flex_audio import baseline_pages
from lab.flex_lite import FlexDsp
from lab.formats import read_frames

workflow = args.workflow.resolve()
import json

ui = json.loads((workflow / "report.json").read_text())
require(ui["status"] == "passed", "Workflow did not pass")
sources = source_hashes()
report = dict(
    status="running",
    scope=__doc__,
    source_hashes=sources,
    checks={},
    workflow_report_sha256=sha256(workflow / "report.json"),
    hardware=False,
)
fw = None


def pages(path):
    raw = path.read_bytes()
    require(len(raw) % 4104 == 0, "Partial page capture")
    return [
        (
            struct.unpack_from(">I", raw, i)[0],
            raw[i + 8 : i + 4104],
            struct.unpack_from(">I", raw, i + 4)[0],
        )
        for i in range(0, len(raw), 4104)
    ]


def payload(packets, slot):
    memory = {}
    descriptor = None
    for tag, block, _ in packets:
        if tag == 0xFFFFFFFF:
            fields = struct.unpack_from(">5I", block)
            if fields[0] == slot and fields[4]:
                descriptor = fields
        else:
            memory[tag] = block
    _, left, right, rate, length = descriptor
    require(rate == 48000, "Unexpected rate")

    def byte(offset):
        return memory[offset // 4096][offset % 4096]

    return bytes(
        v
        for frame in range(length // 2)
        for offset in (left + frame * 2, right + frame * 2)
        for v in (byte(offset), byte(offset + 1))
    )


def retarget(packets, slot):
    result = []
    for tag, block, header in packets:
        if tag == 0xFFFFFFFF:
            block = struct.pack(">I", slot) + block[4:]
        result.append((tag, block, header))
    return result


try:
    first = pages(workflow / "pages-a.bin")
    combined = pages(workflow / "pages-ab.bin")
    require(combined[: len(first)] == first, "A history changed")
    stable = ui["buffer_slots"][0]
    wave_dir = out / "ordinary-samples"
    wave_dir.mkdir()
    native = []
    for index, packets in enumerate((first, combined)):
        pcm = payload(packets, stable)
        native.append(pd.build_native_sample(pcm, True))
        with wave.open(str(wave_dir / f"{index}.wav"), "wb") as stream:
            stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            stream.writeframes(
                b"".join(pcm[j : j + 2][::-1] for j in range(0, len(pcm), 2))
            )
    card = out / "ordinary.img"
    entries = pd.build(str(wave_dir), str(card), main_os=STOCK_MAIN.read_bytes())
    snapshot = (
        ROOT.parent
        / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap"
    )
    require(
        sha256(snapshot)
        == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
        "CPU fixture drift",
    )
    fw = check.Firmware(card, snapshot, STOCK_MAIN)
    fw.call(0x40154358, [])
    check.check_mount(fw, entries[0]["ref"])
    reference = []
    for index in range(2):
        loaded = check.check_load(fw, entries[index]["ref"], stable + index)
        require(
            loaded["load_d0"] == 0
            and all(check.sent_pcm_matches(loaded, native[index])),
            "Ordinary file oracle differs",
        )
        reference.append(retarget(list(fw.pages), stable))
    from lab.flex_session import stock_inputs

    baseline = baseline_pages(stock_inputs()["lp0"])
    actual, oracle = FlexDsp(), FlexDsp()
    for engine in (actual, oracle):
        engine.publish(baseline)
    actual.publish(first)
    oracle.publish(reference[0])
    capture = ui["checks"]["workflow"]["capture_b"]
    frames = read_frames(capture["path"])
    wire = bytearray(frames[capture["trigger"]])

    def block(engine, trigger=0, selected=stable):
        packet = bytearray(wire)
        for offset in (0x22, 0x24, 0x26, 0x28, 0x2A):
            struct.pack_into(
                ">H", packet, offset, trigger if offset in (0x22, 0x26) else 0
            )
        for track in (0, 4):
            struct.pack_into(">H", packet, 0xE0 + track * 0x60, selected)
        before = [
            bool(engine.core.peek(0x2412CC + voice * 0x1D8 + 0x1B8, 1))
            for voice in (0, 1, 8, 9)
        ]
        engine.frame(bytes(packet))
        lanes = []
        for voice, was_active in zip((0, 1, 8, 9), before, strict=True):
            base = 0x2412CC + voice * 0x1D8
            if was_active or engine.core.peek(base + 0x1B8, 1):
                values = [
                    engine.core.peek(base + engine.h.FIELD_WORK_BUFFER + i * 4)
                    for i in range(64)
                ]
                floats = struct.unpack("<64f", struct.pack("<64I", *values))
                lanes.append(
                    [0.5 * (floats[i] + floats[i + 1]) for i in range(0, 64, 2)]
                )
            else:
                lanes.append([0.0] * 32)
        result = [v for sample in zip(*lanes, strict=True) for v in sample]
        require(all(map(math.isfinite, result)), "Nonfinite PCM")
        return array.array("f", result).tobytes()

    phases = {}
    for name, blocks, trigger in (
        ("a-shared", 24, 17),
        ("old-readers-after-b-publication", 16, 0),
        ("new-triggers-use-b", 32, 17),
    ):
        if name == "old-readers-after-b-publication":
            pointers = [
                actual.core.peek(0x2412CC + voice * 0x1D8) for voice in (0, 1, 8, 9)
            ]
            actual.publish(combined[len(first) :])
            require(
                pointers
                == [
                    actual.core.peek(0x2412CC + voice * 0x1D8) for voice in (0, 1, 8, 9)
                ],
                "Commit changed active voice pointers",
            )
        if name == "new-triggers-use-b":
            oracle.publish(reference[1])
        pcm_a, pcm_b = [], []
        for i in range(blocks):
            pcm_a.append(block(actual, trigger if i == 0 else 0))
            pcm_b.append(block(oracle, trigger if i == 0 else 0))
        require(pcm_a == pcm_b, "Stock output differs in " + name)
        joined = b"".join(pcm_a)
        values = struct.unpack(f"<{len(joined) // 4}f", joined)
        require(max(map(abs, values)) > 0, "Silent parity oracle")
        (out / (name + ".f32")).write_bytes(joined)
        for index, track in ((0, 1), (2, 5)):
            stereo = [
                v
                for i in range(0, len(values), 4)
                for v in values[i + index : i + index + 2]
            ]
            require(max(map(abs, stereo)) > 0, f"Track {track} silent")
            write_wav(str(out / f"{name}-t{track}.wav"), stereo, 48000)
        phases[name] = dict(
            exact=True, blocks=blocks, sha256=hashlib.sha256(joined).hexdigest()
        )
    empty = FlexDsp()
    empty.publish(baseline)
    silent = b"".join(
        block(empty, 17 if i == 0 else 0, ui["buffer_slots"][3]) for i in range(12)
    )
    require(
        not any(struct.unpack(f"<{len(silent) // 4}f", silent)), "Empty buffer audible"
    )
    report["checks"] = dict(
        phases=phases,
        empty_silent=True,
        tracks=[1, 5],
        old_generations_pinned=True,
        native_retirement=False,
    )
    require(sources == source_hashes(), "Source drift during audio replay")
    report["status"] = "passed"
    write_json(out / "report.json", report)
    print(f"PASS: {out / 'report.json'}", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    write_json(out / "report.json", report)
    raise
finally:
    if fw:
        fw.close()
