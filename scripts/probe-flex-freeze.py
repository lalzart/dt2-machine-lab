#!/usr/bin/env python3
# ruff: noqa: E402
"""Bounded BUF -> FREEZE -> re-record proof. Emulator only, no key binding."""

import argparse
import os
import shutil
import struct
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import (
    doctor,
    git,
    require,
    settings,
    sha256,
    source_hashes,
    write_json,
)

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
args = p.parse_args()
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.flex_freeze import FreezeUI
from lab.flex_freeze_probe import audio_oracle, dump_pages, payload
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.formats import read_frames

sources = source_hashes()
for name in sources:
    target = out / "frozen-sources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
write_json(out / "sources.json", sources)
test_sources = {
    str(f.relative_to(ROOT)): sha256(f) for f in (ROOT / "tests").glob("test_flex*.py")
}
write_json(out / "test-sources.json", test_sources)
report = dict(
    status="running",
    head=git(ROOT, "rev-parse", "HEAD"),
    branch=git(ROOT, "branch", "--show-current"),
    initial_status=git(ROOT, "status", "--porcelain=v1"),
    checks={},
    memory=[],
    native_freeze=False,
    native_readback=False,
    gesture_bound=False,
)
session = None


def demo(number):
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


def expect_failure(name, action, text):
    try:
        action()
    except ValueError as exc:
        require(text in str(exc), f"Wrong negative control {name}: {exc}")
        report["checks"][name] = str(exc)
    else:
        raise ValueError("Negative control did not fail: " + name)


def slot(track):
    return int.from_bytes(fw.read(fw.u32(0x80004704) + track * 0x450 + 0x80, 2), "big")


def select(track, target):
    session.chord("TRK", f"TRIG {track + 1}")
    live = fw.u32(0x80004704) + track * 0x450
    if fw.read(live + 0xD6, 1) != b"\0":
        session.chord("FUNC", "SRC")
        for _ in range(8):
            session.tap("UP")
        session.tap("YES")
        session.tap("YES")
    require(fw.read(live + 0xD6, 1) == b"\0", "ONESHOT preparation failed")
    session.tap("SRC")
    session.tap("ENCODER D")
    current = slot(track)
    for _ in range((target // 128 - current // 128) % 8):
        session.tap("RIGHT")
    for _ in range(abs(target % 128 - current % 128)):
        session.tap("DOWN" if target % 128 > current % 128 else "UP")
    stage(f"selector-t{track + 1}")
    session.tap("YES")
    require(slot(track) == target, "Stock selector chose wrong sample")


def capture(number, trim=False):
    session.flex.input.source = demo(number)
    session.record()
    if trim:
        before = [fw.u32(session.flex.view + off) for off in (0x9A0, 0x9A4)]
        for _ in range(12):
            session.turn("E", 5)
            if fw.u32(session.flex.view + 0x9A0) > before[0]:
                break
        for _ in range(12):
            session.turn("H", -5)
            if fw.u32(session.flex.view + 0x9A4) < before[1]:
                break
        after = [fw.u32(session.flex.view + off) for off in (0x9A0, 0x9A4)]
        report["checks"]["trim"] = dict(before=before, after=after)
        require(
            before[0] < after[0] < after[1] < before[1], "Original trim did not move"
        )


def freeze(destination):
    from lab.flex_heap import inspect_heap

    before = session.flex.buffers.occupied
    heap_before = inspect_heap(fw.read)
    vector_before = fw.u32(0x405A0F68) - fw.u32(0x405A0F64)
    started = time.perf_counter_ns()
    snapshot = session.flex.freeze(destination)
    heap_after = inspect_heap(fw.read)
    require(
        vector_before == fw.u32(0x405A0F68) - fw.u32(0x405A0F64),
        "FREEZE grew the stock allocation vector",
    )
    require(
        session.flex.buffers.occupied == before and not fw.sources,
        "FREEZE retained PCM or grew allocation budget",
    )
    report["memory"].append(
        dict(
            generations=len(session.flex.buffers.generations),
            snapshots=len(session.flex.snapshots),
            dsp_bytes=before,
            issued=session.flex.issued,
            host_source_pcm_bytes=0,
            heap_free_before=heap_before.free_bytes,
            heap_free_after=heap_after.free_bytes,
            heap_largest_after=heap_after.largest_block,
            freeze_host_us=(time.perf_counter_ns() - started) / 1000,
        )
    )
    return snapshot


try:
    session = Session(demo(1), out, adapter_factory=FreezeUI)
    fw = session.flex.fw
    session.tap("SAMPLING")
    for _ in range(14):
        if session.flex.destination == 1:
            break
        session.turn("C", 5)
    require(session.flex.destination == 1, "C did not select BUF 1")
    stage("01-dest-buf1")
    expect_failure("empty", lambda: session.flex.freeze(4), "empty")
    session.tap("SRC")
    capture(1, trim=True)
    stage("02-trim-a")
    session.accept()
    first = dict(session.flex.current)
    history_a = list(session.flex.pages)
    expect_failure(
        "stale-epoch", lambda: session.flex.freeze(1, expected_epoch=0), "Stale"
    )
    session.flex.freeze_fault = "missing-metadata"
    with fw.transaction():
        failed_slot = session.flex.free_take_slot()
    expect_failure(
        "cache-alias-needs-metadata",
        lambda: session.flex.freeze(1),
        "Unknown temporary identity",
    )
    with fw.transaction():
        require(
            fw.slot(failed_slot)["empty"],
            "Failed FREEZE published a slot",
        )
    session.flex.freeze_fault = "allocation"
    expect_failure("freeze-allocation", lambda: session.flex.freeze(1), "Injected")
    session.flex.freeze_fault = None
    frozen = freeze(1)
    history_af = list(session.flex.pages)
    require(
        len(history_af) > len(history_a)
        and payload(history_af, frozen.slot) == payload(history_a, first["slot"]),
        "FREEZE changed PCM identity",
    )
    stage("03-freeze-from-performance-context")
    select(4, first["slot"])
    select(5, frozen.slot)
    require(
        any(
            x.get("kind") == "frozen-selector-row" and frozen.name in x["text"]
            for x in session.flex.selector_names
        ),
        "Stock selector did not draw frozen name",
    )
    stage("04-frozen-snapshot-on-t6")
    capture_info = session.capture_pad("a-pad")
    frames = read_frames(capture_info["path"])
    wire = frames[capture_info["trigger"]]
    require(
        int.from_bytes(wire[0xE0 + 5 * 0x60 : 0xE2 + 5 * 0x60], "big") == frozen.slot,
        "Snapshot did not reach actual CPU control frame",
    )
    # Return to a buffer track: USE must not silently replace frozen T6.
    session.chord("TRK", "TRIG 1")
    capture(2)
    session.accept()
    second = dict(session.flex.current)
    history_b = list(session.flex.pages)
    require(
        slot(0) == slot(4) == first["slot"] and slot(5) == frozen.slot,
        "Replacement changed shared or frozen references",
    )
    require(
        first["allocation"]["start"] != second["allocation"]["start"],
        "Replacement overwrote A",
    )
    stage("05-buf1-rerecorded-t6-still-frozen")
    freeze(1)
    # Discard and incomplete publication retain the current committed B.
    capture(3)
    previous = session.flex.buffers.current[0]
    session.flex.inject_failure = "allocation"
    session.tap("YES")
    session.advance()
    require(
        session.flex.buffers.current[0] is previous and session.flex.phase == "trim",
        "Failed candidate replaced B",
    )
    report["checks"]["candidate-allocation"] = session.flex.error
    session.flex.inject_failure = None
    session.chord("FUNC", "NO")
    require(
        session.flex.buffers.current[0] is previous, "Discard changed committed audio"
    )
    session.tap("SRC")
    # Eight distinct recordings/snapshots, no reuse or identity recycling.
    for number in range(3, 9):
        capture(number)
        session.accept()
        freeze(1)
    expect_failure(
        "snapshot-exhaustion", lambda: session.flex.freeze(1), "Snapshot limit"
    )
    previous = session.flex.buffers.current[0]
    capture(9)
    session.tap("YES")
    session.advance()
    require(
        session.flex.phase == "trim" and session.flex.buffers.current[0] is previous,
        "Generation exhaustion lost current sample",
    )
    report["checks"]["generation-exhaustion"] = session.flex.error
    session.chord("FUNC", "NO")
    session.tap("SRC")
    histories = dict(
        a=history_a, af=history_af, b=history_b, all=list(session.flex.pages)
    )
    for name, packets in histories.items():
        dump_pages(out / f"pages-{name}.bin", packets)
    with fw.transaction():
        for snapshot in session.flex.snapshots:
            allocation = fw.slot(snapshot.slot)
            require(
                (allocation["start"], allocation["size"])
                == (snapshot.start, snapshot.size),
                "Frozen allocation changed",
            )
        require(
            fw.call(0x40043A30, [0, 0, 0]) == 0, "Project save escaped volatile guard"
        )
        require(
            fw.call(0x400F5050, [0, 0, 0, 0]) == 0, "Project load escaped reader guard"
        )
        for identity in session.flex.metadata:
            expect_failure(
                f"no-readback-{identity:x}",
                lambda identity=identity: fw.call(0x4015BA22, [identity]),
                "readback required",
            )
    require(
        not fw.sources and not fw.handles and not fw.card.writes,
        "Retained source or file write",
    )
    report["snapshots"] = [asdict(s) for s in session.flex.snapshots]
    report["aliases"] = session.flex.aliases
    report["checks"]["shared_tracks_and_frozen_track"] = [slot(t) for t in (0, 4, 5)]
    report["checks"]["no_file_writes"] = True
    report["checks"]["cpu_pcm_policy"] = (
        "No guest heap PCM allocation in this host-backed BUF adapter; host source PCM entries removed. Not a whole-heap measurement. Native free proved separately."
    )
    inputs = dict(session.inputs)
    report["inputs"] = {k: sha256(v) for k, v in inputs.items() if k != "sections"}
    report["selector_rows"] = session.flex.selector_names
    session.flex.change_project()
    expect_failure(
        "epoch-invalidates-freeze", lambda: session.flex.freeze(1), "Project changed"
    )
    with fw.transaction():
        require(
            fw.call(0x40043A30, [0, 0, 0]) == 0,
            "Snapshots escaped save guard after epoch invalidation",
        )
    report["checks"]["project_transition"] = (
        "Host epoch invalidates buffers; frozen allocations quarantined and save/load blocked, restart required. Not a real project load."
    )
    report["events"] = session.flex.events
    session.close()
    session = None
    print("UI/lifetime checks passed; comparing stock DSP audio", flush=True)
    report["audio"] = audio_oracle(
        out, inputs, wire, first["slot"], frozen.slot, histories
    )
    require(sources == source_hashes(), "Source drift during FREEZE probe")
    require(
        test_sources
        == {
            str(f.relative_to(ROOT)): sha256(f)
            for f in (ROOT / "tests").glob("test_flex*.py")
        },
        "Test source drift",
    )
    report["status"] = "passed"
    write_json(out / "report.json", report)
    print(f"PASS: {out / 'report.json'}", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if session:
        report["events"] = session.flex.events
        session.screenshot("failure")
    write_json(out / "report.json", report)
    raise
finally:
    if session:
        session.close()
