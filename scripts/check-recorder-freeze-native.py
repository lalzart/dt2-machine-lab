#!/usr/bin/env python3
# ruff: noqa: E402
"""Executed ColdFire metadata/alias/rollback proof after Gate-A NORMAL parity.

BUF capture/commit remains host-assisted; FREEZE uses a native diagnostic
command with no resource HLE. No hardware image, readback or key binding.
"""

import argparse
import os
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
args = p.parse_args()
provenance = doctor()
gate = ROOT / "out/runs/recorder-native-audit-20261020-01/gate-a.json"
import json

require(json.loads(gate.read_text())["status"] == "passed", "Gate A has not passed")
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

# isort: off
from lab.recorder_freeze_native import NativeFreezeUI
from lab import recorder_freeze_code as n
from lab.flex_freeze_probe import audio_oracle, dump_pages
from lab.flex_heap import inspect_heap
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.formats import read_frames
# isort: on

sources = source_hashes()
write_json(out / "sources.json", sources)
for name in sources:
    target = out / "frozen-sources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
report = dict(
    status="running",
    provenance=provenance,
    gate_a_sha256=sha256(gate),
    checks={},
    memory=[],
    host_capture=True,
    native_freeze=True,
    native_readback=False,
    gesture_bound=False,
)
session = None


def pcm(number):
    return Take(
        b"".join(
            struct.pack(
                ">hh",
                (i * (37 + number * 16)) % 20001 - 10000,
                (i * (67 + number * 22)) % 16001 - 8000,
            )
            for i in range(12000)
        ),
        True,
    )


def stage(name):
    session.advance()
    session.screenshot(name)


def slot(track):
    return int.from_bytes(fw.read(fw.u32(0x80004704) + track * 0x450 + 0x80, 2), "big")


def record(number):
    session.flex.input.source = pcm(number)
    session.record()
    session.accept()


def failure(name, operation, code):
    before = fw.read(fw.u32(0x80004704), 16 * 0x450)
    try:
        operation()
    except ValueError as exc:
        require(f"({code})" in str(exc), f"Wrong native failure {name}: {exc}")
        report["checks"][name] = str(exc)
    else:
        raise ValueError("Negative did not fail: " + name)
    require(
        fw.read(fw.u32(0x80004704), len(before)) == before,
        "Native failure changed track data",
    )


def freeze():
    before = inspect_heap(fw.read)
    source_before = session.flex.resource_hle_calls
    snapshot = session.flex.freeze(1)
    after = inspect_heap(fw.read)
    require(
        source_before == session.flex.resource_hle_calls
        and not fw.sources
        and not fw.handles,
        "Native freeze used/retained host PCM",
    )
    report["memory"].append(
        dict(
            snapshot=snapshot,
            heap_delta=before.free_bytes - after.free_bytes,
            dsp_bytes=session.flex.buffers.occupied,
            header_pages=len(session.flex.last_freeze_pages),
            pcm_pages=sum(
                tag != 0xFFFFFFFF for tag, _, _ in session.flex.last_freeze_pages
            ),
        )
    )
    return snapshot


def select(track, target):
    session.chord("TRK", f"TRIG {track + 1}")
    live = fw.u32(0x80004704) + track * 0x450
    if fw.read(live + 0xD6, 1) != b"\0":
        session.chord("FUNC", "SRC")
        for _ in range(8):
            session.tap("UP")
        session.tap("YES")
        session.tap("YES")
    session.tap("SRC")
    session.tap("ENCODER D")
    current = slot(track)
    for _ in range((target // 128 - current // 128) % 8):
        session.tap("RIGHT")
    for _ in range(abs(target % 128 - current % 128)):
        session.tap("DOWN" if target % 128 > current % 128 else "UP")
    stage(f"selector-t{track + 1}")
    session.tap("YES")
    require(slot(track) == target, "Original selector failed")


try:
    session = Session(pcm(1), out, adapter_factory=NativeFreezeUI)
    fw = session.flex.fw
    write_json(out / "native-patches.json", session.flex.native_patches)
    write_json(out / "code-ranges.json", session.flex.code_ranges)
    session.tap("SAMPLING")
    for _ in range(14):
        if session.flex.destination == 1:
            break
        session.turn("C", 5)
    require(session.flex.destination == 1, "C failed to choose BUF 1")
    session.tap("SRC")
    failure("empty", lambda: session.flex.freeze(1), -2)
    record(1)
    a = dict(session.flex.current)
    history_a = list(session.flex.pages)
    require(fw.u32(n.GEN) == 1, "Native generation registration missing")
    failure("stale-epoch", lambda: session.flex.freeze(1, expected_epoch=0), -3)
    # Same address but different epoch: native check cannot rely on kit pointer.
    fw.write(n.STATE, struct.pack(">I", 2))
    failure("reused-kit-address", lambda: session.flex.freeze(1, expected_epoch=1), -3)
    fw.write(n.STATE, struct.pack(">I", 1))
    # Identity collision and admission refusal must precede alias publication.
    fw.write(n.SNAP, struct.pack(">I", 3))
    failure("identity-collision", lambda: session.flex.freeze(1), -5)
    fw.write(n.SNAP, bytes(64))
    fw.write(n.STATE + 12, struct.pack(">I", 1))
    failure("capacity-seam", lambda: session.flex.freeze(1), -5)
    fw.write(n.STATE + 12, bytes(4))
    frozen = freeze()
    require(frozen["name"] == "B1-001", "Native stock basename differs")
    require(
        frozen["identity"] != fw.u32(0x405B1368 + frozen["slot"] * 16),
        "Logical snapshot and loader key were conflated",
    )
    require(
        frozen["allocation"]["start"] == a["allocation"]["start"],
        "FREEZE copied allocation",
    )
    history_af = list(session.flex.pages)
    stage("01-native-frozen-performance-context")
    select(4, a["slot"])
    select(5, frozen["slot"])
    capture = session.capture_pad("a-pad")
    wire = read_frames(capture["path"])[capture["trigger"]]
    require(
        int.from_bytes(wire[0xE0 + 5 * 0x60 : 0xE2 + 5 * 0x60], "big")
        == frozen["slot"],
        "Snapshot did not reach native control packet",
    )
    session.chord("TRK", "TRIG 1")
    record(2)
    b = dict(session.flex.current)
    history_b = list(session.flex.pages)
    require(
        slot(0) == slot(4) == a["slot"] and slot(5) == frozen["slot"],
        "Native freeze changed assignment",
    )
    stage("02-new-buffer-and-native-frozen-a")
    # Native rollback after stock aliasing but before project publication.
    fw.write(n.STATE + 12, struct.pack(">I", 2))
    failure("post-alias-rollback", lambda: session.flex.freeze(1), -4)
    fw.write(n.STATE + 12, bytes(4))
    require(
        fw.u32(n.SNAP + 64) == 3 and fw.u32(n.STATE + 4) == 2,
        "Failed snapshot identity was recycled",
    )
    rejected_slot = fw.u32(n.SNAP + 64 + 36)
    require(fw.slot(rejected_slot)["empty"], "Rollback left broken selectable sample")
    for fault, label in ((3, "stock-loader-cache-miss"), (4, "incomplete-header")):
        fw.write(n.STATE + 12, struct.pack(">I", fault))
        failure(label, lambda: session.flex.freeze(1), -4)
        fw.write(n.STATE + 12, bytes(4))
        failed = n.SNAP + (fw.u32(n.STATE + 4) - 1) * 64
        failed_slot = fw.u32(failed + 36)
        require(
            fw.u32(failed) == 3 and fw.slot(failed_slot)["empty"],
            "Failed native alias became selectable",
        )
    with session.flex.native():
        pool = session.flex.project_pool()
        require(
            fw.read(pool + rejected_slot * 16, 4) == b"\xff" * 4,
            "Rollback published project reference",
        )
        # Native frozen-slot and persistence guards, with old host guards bypassed.
        before = fw.slot(frozen["slot"])
        fw.call(n.UNLOAD, [frozen["slot"]])
        fw.call(n.CLEAR, [frozen["slot"]])
        require(
            fw.slot(frozen["slot"]) == before,
            "Native guard allowed premature frozen-slot reuse",
        )
        writes = len(fw.card.writes)
        require(
            fw.call(n.SAVE, [0, 0, 0]) == 0
            and fw.call(n.LOAD_PROJECT, [0, 0, 0, 0]) == 0
            and len(fw.card.writes) == writes,
            "Native project guard failed",
        )
        require(
            fw.call(0x4015BA22, [frozen["identity"]]) == 0xFFFFFFFF,
            "Retired snapshot exposed a full CPU source",
        )
    freeze()  # B1-005; 002..004 remain tombstones.
    for number in range(3, 9):
        record(number)
        if fw.u32(n.STATE + 4) < 8:
            freeze()
    failure("snapshot-limit", lambda: session.flex.freeze(1), -5)
    histories = dict(
        a=history_a, af=history_af, b=history_b, all=list(session.flex.pages)
    )
    for name, packets in histories.items():
        dump_pages(out / f"pages-{name}.bin", packets)
    require(
        not fw.sources and not fw.card.writes,
        "Native buffer workflow wrote a file/kept source PCM",
    )
    report["snapshots"] = session.flex.snapshots
    report["checks"].update(
        native_resource_calls=session.flex.native_resource_calls,
        issued_snapshots=fw.u32(n.STATE + 4),
        ready_snapshots=len(session.flex.snapshots),
        quarantined_slot=rejected_slot,
        no_file_writes=True,
        native_project_guards=True,
    )
    report["events"] = session.flex.events
    report["inputs"] = dict(session.inputs)
    inputs = dict(session.inputs)
    session.close()
    session = None
    report["audio"] = audio_oracle(
        out, inputs, wire, a["slot"], frozen["slot"], histories
    )
    require(source_hashes() == sources, "Source drift during native proof")
    report["status"] = "passed"
    print(f"PASS: {out / 'report.json'}", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if session:
        report["events"] = session.flex.events
        report["native_resource_calls"] = session.flex.native_resource_calls
        session.screenshot("failure")
    raise
finally:
    if session:
        session.close()
    write_json(out / "report.json", report)
