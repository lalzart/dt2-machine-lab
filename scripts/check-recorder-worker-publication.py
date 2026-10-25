#!/usr/bin/env python3
# ruff: noqa: E402
"""Interleave original SHARC triggers between captured native BUF headers.

A successful diagnostic may expose a publication gap; it does not certify an
atomic native commit. Host delivery controls packet order, not sample contents.
"""

import argparse
import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, sha256, source_hashes, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("workflow", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--require-atomic", action="store_true")
a = p.parse_args()
doctor()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored output")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.flex_audio import baseline_pages
from lab.flex_lite import FlexDsp
from lab.flex_session import stock_inputs

sources = source_hashes()
write_json(out / "sources.json", sources)
workflow = a.workflow.resolve()
proof = json.loads((workflow / "report.json").read_text())
require(proof["status"] == "passed", "Workflow must pass")
report = dict(status="running", workflow_sha256=sha256(workflow / "report.json"))


def pages(name):
    raw = (workflow / f"pages-{name}.bin").read_bytes()
    require(len(raw) % 4104 == 0, "Partial packet")
    return [
        (
            struct.unpack_from(">I", raw, i)[0],
            raw[i + 8 : i + 4104],
            struct.unpack_from(">I", raw, i + 4)[0],
        )
        for i in range(0, len(raw), 4104)
    ]


def voice_peak(engine):
    peak = 0.0
    for lane in (0, 1):
        base = 0x2412CC + lane * 0x1D8
        if engine.core.peek(base + 0x1B8, 1):
            words = [
                engine.core.peek(base + engine.h.FIELD_WORK_BUFFER + i * 4)
                for i in range(64)
            ]
            peak = max(
                peak, *map(abs, struct.unpack("<64f", struct.pack("<64I", *words)))
            )
    return peak


try:
    before, after = pages("af"), pages("b")
    require(after[: len(before)] == before, "History prefix changed")
    stable = proof["checks"]["first"]["slot"]
    wire = bytearray.fromhex(proof["audio_inputs"]["wire"])
    struct.pack_into(">H", wire, 0xE0, stable)
    for offset in (0x22, 0x24, 0x26, 0x28, 0x2A):
        struct.pack_into(">H", wire, offset, int(offset in (0x22, 0x26)))
    baseline = baseline_pages(stock_inputs()["lp0"])
    old, incoming = FlexDsp(), FlexDsp()
    for engine in (old, incoming):
        engine.publish(baseline)
        engine.publish(before)
    reference_peak = 0.0
    for index in range(12):
        packet = bytearray(wire)
        if index:
            for offset in (0x22, 0x26):
                struct.pack_into(">H", packet, offset, 0)
        old.frame(bytes(packet))
        reference_peak = max(reference_peak, voice_peak(old))
    require(reference_peak > 0, "Silent old-generation oracle")
    pointers = [old.core.peek(0x2412CC + lane * 0x1D8) for lane in (0, 1)]
    zero_headers = []
    old_descriptor = incoming.slot_record(stable)
    complete_headers = []
    for index, page in enumerate(after[len(before) :]):
        if (
            page[0] == 0xFFFFFFFF
            and struct.unpack_from(">I", page[1])[0] == stable
            and struct.unpack_from(">I", page[1], 16)[0]
        ):
            if a.require_atomic:
                require(
                    incoming.slot_record(stable) == old_descriptor,
                    "Old descriptor changed before final header",
                )
            complete_headers.append(index)
        old.publish([page])
        incoming.publish([page])
        tag, block, _ = page
        if (
            tag == 0xFFFFFFFF
            and struct.unpack_from(">I", block)[0] == stable
            and struct.unpack_from(">I", block, 16)[0] == 0
        ):
            zero_headers.append(
                dict(index=index, descriptor=incoming.slot_record(stable))
            )
            require(
                pointers == [old.core.peek(0x2412CC + lane * 0x1D8) for lane in (0, 1)],
                "Old active pointer invalidated",
            )
            if len(zero_headers) == 1:
                incoming.frame(bytes(wire))
                report["new_trigger_gap_peak"] = voice_peak(incoming)
                report["new_trigger_gap_active"] = [
                    incoming.core.peek(0x2412CC + lane * 0x1D8 + 0x1B8, 1)
                    for lane in (0, 1)
                ]
    if a.require_atomic:
        require(
            not zero_headers and len(complete_headers) == 1,
            "Logical publication was not one final header",
        )
        later = pages("all")[len(after) :]
        require(
            not any(
                tag == 0xFFFFFFFF and struct.unpack_from(">I", block)[0] == stable
                for tag, block, _ in later
            ),
            "Failed commits emitted logical headers",
        )
    else:
        require(
            zero_headers, "Expected stock clear/header negative control disappeared"
        )
    report.update(
        status="passed",
        atomic_commit=a.require_atomic,
        zero_headers=zero_headers,
        old_active_pointers_preserved=True,
        complete_descriptor=incoming.slot_record(stable),
        original_a_peak=reference_peak,
        layer="Original SHARC page callback and ONESHOT; explicitly interleaved host packet delivery; hardware interleaving not measured",
    )
    require(source_hashes() == sources, "Source drift")
    print(
        "PASS: atomic header publication"
        if a.require_atomic
        else "PASS: diagnostic exposed stock logical-slot clear window",
        flush=True,
    )
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
