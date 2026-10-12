#!/usr/bin/env python3
"""Actual native Flex allocation failure, saved-source recovery and old-handle PCM."""

# ruff: noqa: E402
import argparse
import json
import os
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument(
    "--snapshot",
    type=Path,
    default=ROOT.parent
    / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap",
)
args = p.parse_args()
doctor()
require(
    sha256(args.snapshot)
    == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
    "Unknown snapshot",
)
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.runtime import STOCK_MAIN  # isort: skip
import plusdrive_check as check
import tools.plusdrive as pd
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k

from lab.flex_heap import HeapTrace, inspect_heap
from lab.flex_native import MAX_FRAMES, RESOURCE_SITES, USE_ERRORS
from lab.flex_native_build import BASE, patch_cpu

samples = out / "samples"
samples.mkdir()
with wave.open(str(samples / "mount.wav"), "wb") as w:
    w.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
    w.writeframes(bytes(1024))
card = out / "card.img"
entries = pd.build(str(samples), str(card), main_os=STOCK_MAIN.read_bytes())
fw = check.Firmware(card, args.snapshot, STOCK_MAIN)
report = dict(
    status="running",
    scope=__doc__,
    snapshot=sha256(args.snapshot),
    sources={
        p: sha256(ROOT / p)
        for p in (
            "lab/flex_heap.py",
            "lab/flex_native.py",
            "lab/flex_native_build.py",
            "lab/flex_retirement.py",
            "scripts/check-flex-pressure.py",
        )
    },
)
trace = None
variant = 0


def recorder(arg):
    command, mono, first, count = struct.unpack(">HHII", fw.read(arg(1), 12))
    require(command == 4 and mono == 0, "Recorder command")
    data = b"".join(
        struct.pack(
            ">HH", (i * 17 + variant) & 65535, (30000 - i * 29 - variant) & 65535
        )
        for i in range(first, first + count)
    )
    fw.write(0x4FE79340, data.ljust(2048, b"\0"))
    return 0


try:
    fw.call(0x40154358, [])
    check.check_mount(fw, entries[0]["ref"])
    image, meta = patch_cpu(STOCK_MAIN.read_bytes(), managed_sources=True)
    for w in meta["writes"]:
        require(
            fw.read(w["address"], len(bytes.fromhex(w["before"])))
            == bytes.fromhex(w["before"]),
            "Patch guard",
        )
        fw.write(w["address"], bytes.fromhex(w["after"]))
    fw.uc.ctl_remove_cache(BASE, BASE + len(image))
    loc = meta["locations"]
    write_json(out / "native-patches.json", meta)
    report["main_sha256"] = meta["sha256"]
    fw._hle(0x400124A0, recorder)
    trace = HeapTrace(fw)
    trace.phase = "fill-unsaved"
    nodes = []
    while True:
        variant = len(nodes)
        before = inspect_heap(fw.read)
        head = fw.read(loc["state"], 8)
        node = fw.call(
            loc["accept"],
            [loc["state"], 0, MAX_FRAMES, 1, 300 + len(nodes)],
            limit=800000000,
        )
        if node == 0xFFFFFFFF:
            after = inspect_heap(fw.read)
            require(
                fw.read(loc["state"], 8) == head and after.blocks == before.blocks,
                "Failed accept leaked source/descriptor or changed identities",
            )
            require(
                fw.u32(loc["state"] + 48) == list(USE_ERRORS).index("memory"),
                "Pressure did not fail at memory stage",
            )
            break
        nodes.append(node)
        require(len(nodes) < 32, "No allocation-pressure boundary")
    report["unsaved_maximum_in_fixture"] = len(nodes)
    require(nodes, "No pressure takes")
    first = nodes[0]
    source = fw.u32(first + 20)
    old_ref = fw.read(first + 4, 16)
    original_file = fw.read(source, fw.u32(first + 12))
    original = original_file[:256]
    handle = fw.alloc(16)
    dest = fw.alloc(256)
    require(
        fw.call(RESOURCE_SITES["open"][0], [first + 4, handle]) == 0, "Old handle open"
    )
    require(
        fw.call(RESOURCE_SITES["read"][0], [dest, 256, handle]) == 256
        and fw.read(dest, 256) == original,
        "Pressure corrupted oldest take",
    )
    # Persist just the oldest take, retaining the handle while its allocation
    # becomes available to the next take. No hidden write occurs during USE.
    trace.phase = "save-and-recover"
    pool = fw.alloc(b"\xff" * (1024 * 16))
    fw.write(pool + 16, old_ref)
    require(
        fw.call(loc["persist"], [pool], limit=800000000) == 0
        and fw.u32(first + 20) == 0,
        "Pressure save did not reclaim source",
    )
    variant = 99
    retry = fw.call(
        loc["accept"], [loc["state"], 0, MAX_FRAMES, 1, 400], limit=800000000
    )
    require(retry != 0xFFFFFFFF, "Save did not recover actual admission capacity")
    require(
        fw.read(first + 4, 16) == old_ref and fw.read(retry + 4, 16) != old_ref,
        "Recovered allocation reused identity",
    )
    fw.write(handle + 4, bytes(4))
    require(
        fw.call(RESOURCE_SITES["read"][0], [dest, 256, handle]) == 256
        and fw.read(dest, 256) == original,
        "Old handle resolved new PCM after capacity recovery",
    )
    # There is no second source-sized block now. Streaming needs 32 KiB.
    pressure = inspect_heap(fw.read)
    require(
        pressure.largest_block < 4 << 20, "Pressure fixture still has a 4 MiB block"
    )
    path = fw.alloc(b"/recorded/PRESSURE-SAVE-AS\0")
    saved = fw.alloc(b"\xcc" * 16)
    trace.phase = "streaming-save-as"
    cached = fw.read(first + 32, 16)
    before = inspect_heap(fw.read)
    faults = []

    def fail_second_chunk(uc, pc, size, data):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if fw.u32(sp + 16) >= 0x8000:
            faults.append(fw.u32(sp + 16))
            uc.reg_write(k.UC_M68K_REG_D0, 0xFFFFFFFF)
            uc.reg_write(k.UC_M68K_REG_A7, sp + 4)
            uc.reg_write(k.UC_M68K_REG_PC, fw.u32(sp))

    def erase(arg):
        sector, count = arg(0), arg(1)
        require(
            sector >= 0x5EE180
            and 0 < count <= ((MAX_FRAMES * 4 + 80 + 32767) // 32768) * 64
            and count % 64 == 0,
            f"Unexpected discard sector={sector:#x} count={count}",
        )
        fw.card.write(sector, bytes(count * 512))
        return 0

    fw._hle(0x4012DDF2, erase)
    fault = fw.uc.hook_add(
        UC_HOOK_CODE,
        fail_second_chunk,
        begin=loc["read_backing"],
        end=loc["read_backing"],
    )
    try:
        require(
            fw.call(loc["save"], [first, path, saved], limit=800000000) == 0xFFFFFFFF,
            "Partial backing read accepted",
        )
    finally:
        fw.uc.hook_del(fault)
    require(
        faults == [0x8000]
        and fw.read(saved, 16) == b"\xcc" * 16
        and fw.read(first + 32, 16) == cached
        and fw.u32(first + 20) == 0,
        "Partial read changed reference or source ownership",
    )
    # Same path succeeding proves the partial destination was removed.
    require(
        fw.call(loc["save"], [first, path, saved], limit=800000000) == 0,
        "Streaming Save As failed under heap pressure or left a partial file",
    )
    require(fw.read(first + 32, 16) == cached, "Save As primitive published early")
    trace.phase = "stock-reload"
    fw.call(0x401540C6, [300])
    fw.call(0x40153BEA, [300])
    loaded = check.check_load(fw, fw.read(saved, 16), 500)
    require(
        loaded["load_d0"] == 0 and all(check.sent_pcm_matches(loaded, original_file)),
        "Streaming Save As did not preserve full PCM",
    )
    scratch = [
        e
        for e in trace.events
        if e["phase"] == "streaming-save-as" and e.get("requested") == 32768
    ]
    require(
        len(scratch) == 2 and all(e["occupied"] == 32768 for e in scratch),
        "Streaming scratch block differs",
    )
    require(
        not any(
            e.get("occupied", 0) >= 4 << 20
            for e in trace.events
            if e["phase"] == "streaming-save-as"
        ),
        "Save As allocated a complete take",
    )
    report.update(
        streaming_save_as_under_pressure=True,
        streaming_scratch_bytes=32768,
        partial_read_cleanup_and_retry=True,
        full_saved_pcm_matches=True,
        largest_block_before_save_as=pressure.largest_block,
    )
    fw.call(RESOURCE_SITES["close"][0], [handle])
    report.update(
        actual_malloc_failure_preserves_takes=True,
        failed_candidate_heap_restored=True,
        save_recovers_capacity=True,
        old_handle_keeps_exact_pcm=True,
        source_address_reused=fw.u32(retry + 20) == source,
        issued_identities=fw.u32(loc["state"] + 4),
        status="PASS",
    )
except Exception as exc:
    report.update(status="FAIL", error=str(exc))
    raise
finally:
    if trace:
        report["heap_trace"] = trace.report()
    write_json(out / "report.json", report)
    fw.close()
print(json.dumps({k: v for k, v in report.items() if k != "heap_trace"}, indent=2))
