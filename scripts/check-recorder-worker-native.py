#!/usr/bin/env python3
# ruff: noqa: E402
"""Native queued BUF transaction from original recorder buttons; no host commit."""

import argparse
import os
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, source_hashes, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--smoke", action="store_true")
p.add_argument("--queued-freeze", action="store_true")
a = p.parse_args()
provenance = doctor()
out = a.output.resolve()
assert out.is_relative_to(ROOT / "out/runs")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab.flex_freeze_probe import audio_oracle, dump_pages, payload
from lab.flex_heap import inspect_heap
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.formats import read_frames
from lab.project import require
from lab.recorder_freeze_worker_native import QueuedFreezeUI
from lab.recorder_worker_native import NativeWorkerUI

sources = source_hashes()
write_json(out / "sources.json", sources)
for name in sources:
    target = out / "frozen-sources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
report = dict(
    status="running",
    provenance=provenance,
    checks={},
    memory=[],
    host_commit=False,
    native_worker=True,
    modeled_recorder_peer=True,
    native_readback=False,
    queued_freeze=a.queued_freeze,
)
session = None


def freeze_result():
    before = fw.u32(q.STATE + 32)
    # Test command input only. Native GUI latches DEST, epoch and kit and
    # submits the job; no host call into the worker or resource registry.
    fw.write(q.STATE, struct.pack(">I", fw.u32(q.STATE) + 1))
    session.turn("A", 0)  # Wake the stock blocked GUI without navigation.
    if fw.u32(q.STATE + 52) & 0x80000000:
        return fw.u32(q.STATE + 52)
    for _ in range(20):
        if fw.u32(q.STATE + 32) > before:
            break
        session.advance()
    require(fw.u32(q.STATE + 32) == before + 1, "FREEZE job did not complete")
    result = fw.u32(q.STATE + 12)
    require(fw.u32(w.STATE + 12) == 0, "FREEZE kept common ownership")
    require(fw.u32(q.STATE + 56) == 0, "Unbalanced native sample-operation count")
    report["freeze_contexts"] = session.flex.freeze_contexts
    require(
        all(
            not row["direct"] and row["sr"] & 0x700 != 0x700
            for row in report["freeze_contexts"]
        ),
        "FREEZE used a masked host diagnostic",
    )
    return result


def freeze():
    if not a.queued_freeze:
        return session.flex.freeze(1)
    result = freeze_result()
    require(result < 1024, f"Queued FREEZE failed {result:#x}")
    return next(item for item in session.flex.snapshots if item["slot"] == result)


def freeze_matrix():
    checks = {}
    before = fw.read(0x405B1368 + first["slot"] * 16, 16)
    # The final normal scenario selected BUF 4. Its live generation is valid;
    # commands use that native destination, never a host-selected sample ref.
    for fault in (3, 4):
        fw.write(q.STATE + 40, struct.pack(">I", fault))
        issued = fw.u32(n.STATE + 4)
        require(freeze_result() == 0xFFFFFFFD, "Stale FREEZE context accepted")
        require(fw.u32(n.STATE + 4) == issued, "Stale request consumed identity")
        checks[f"stale-{fault}"] = True
    fw.write(q.STATE + 40, bytes(4))
    for fault in (1, 2, 3):
        fw.write(n.STATE + 12, struct.pack(">I", fault))
        result = freeze_result()
        require(
            result == (0xFFFFFFFB if fault == 1 else 0xFFFFFFFC),
            f"FREEZE fault {fault} did not refuse {result:#x}",
        )
        checks[f"native-fault-{fault}"] = True
    fw.write(n.STATE + 12, bytes(4))
    while fw.u32(n.STATE + 4) < 8:
        freeze()
    issued = fw.u32(w.STATE + 4), fw.u32(n.STATE + 4)
    lengths = fw.read(0x405BA768, 4096)
    keys = fw.read(0x405B1368, 16384)
    native_sources = fw.read(w.STATE, 192)
    pages = len(session.flex.pages)
    heap_free = []
    for _ in range(256):
        require(freeze_result() == 0xFFFFFFFB, "Full FREEZE registry accepted")
        heap_free.append(inspect_heap(fw.read).free_bytes)
    require(
        (fw.u32(w.STATE + 4), fw.u32(n.STATE + 4)) == issued,
        "Refusal recycled or consumed identities",
    )
    require(
        fw.read(0x405BA768, 4096) == lengths
        and fw.read(0x405B1368, 16384) == keys
        and fw.read(w.STATE, 192) == native_sources
        and len(session.flex.pages) == pages,
        "Refusal mutated sample resources",
    )
    require(
        fw.read(0x405B1368 + first["slot"] * 16, 16) == before,
        "FREEZE matrix changed BUF 1",
    )
    completions = fw.u32(q.STATE + 32)
    session.turn("A", 0)  # Same request serial must not queue another job.
    require(fw.u32(q.STATE + 32) == completions, "Duplicate request was replayed")
    checks["full-refusals"] = dict(
        count=256, heap_free=heap_free, pcm_pages=0, identities=issued
    )
    require(
        max(heap_free) - min(heap_free) <= 64,
        "Repeated refused FREEZE jobs accumulate CPU memory",
    )
    checks["full-refusals"]["heap_span"] = max(heap_free) - min(heap_free)
    checks["duplicate-serial"] = True
    checks["source-hle"] = session.flex.resource_hle_calls
    report["freeze_matrix"] = checks
    report["freeze_contexts"] = session.flex.freeze_contexts


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


def record(number):
    session.flex.input.source = pcm(number)
    session.record()
    session.tap("YES")
    for _ in range(20):
        session.flex.sync_observation()
        if session.flex.phase == "assigned":
            break
        session.advance()
    require(
        session.flex.phase == "assigned",
        f"Native USE failed {fw.read(w.STATE, 96).hex()}",
    )
    session.advance()
    session.flex.sync_observation()
    require(
        not fw.sources and not fw.handles and not fw.direct,
        "Host source/transaction used",
    )
    nodes = []
    node = fw.u32(w.STATE)
    while node:
        nodes.append(
            dict(
                pointer=node, source=fw.u32(node + 20), ref=fw.read(node + 4, 16).hex()
            )
        )
        node = fw.u32(node)
    require(all(row["source"] == 0 for row in nodes), "Retained CPU PCM")
    report["memory"].append(
        dict(
            number=number,
            heap_free=inspect_heap(fw.read).free_bytes,
            nodes=nodes,
            retired_bytes=fw.u32(w.STATE + 84),
        )
    )
    return dict(session.flex.current)


try:
    session = Session(
        pcm(1),
        out,
        adapter_factory=QueuedFreezeUI if a.queued_freeze else NativeWorkerUI,
    )
    fw = session.flex.fw
    if a.queued_freeze:
        require(freeze_result() == 0xFFFFFFFF, "NORMAL admitted FREEZE")
    session.tap("SAMPLING")
    for _ in range(14):
        if session.flex.destination == 1:
            break
        session.turn("C", 5)
    require(session.flex.destination == 1, "C DEST failed")
    if a.queued_freeze:
        require(freeze_result() == 0xFFFFFFFE, "Empty BUF admitted FREEZE")
    session.tap("SRC")
    first = record(1)
    require(
        payload(session.flex.pages, first["slot"])
        == session.flex.input.candidate(
            fw.u32(w.STATE + 24), fw.u32(w.STATE + 24) + first["frames"]
        ).pcm,
        "Native PCM differs",
    )
    report["checks"]["first"] = first
    session.screenshot("01-native-buffer-ready")
    if a.smoke and a.queued_freeze:
        report["snapshots"] = [freeze()]

    def slot(track):
        return int.from_bytes(
            fw.read(fw.u32(0x80004704) + track * 0x450 + 0x80, 2), "big"
        )

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
        session.tap("YES")
        require(slot(track) == target, "Stock selector assignment failed")

    def refusal(fault, name):
        previous = fw.read(0x405B1368 + first["slot"] * 16, 16)
        before_id = fw.u32(w.STATE + 4)
        fw.write(w.STATE + 76, struct.pack(">I", fault))
        session.record()
        session.tap("YES")
        session.advance()
        require(fw.u32(w.STATE + 12) == 0, "Worker stuck busy")
        require(
            fw.read(0x405B1368 + first["slot"] * 16, 16) == previous,
            "Failure replaced committed buffer",
        )
        node = fw.u32(w.STATE)
        while node:
            require(fw.u32(node + 20) == 0, "Failed candidate retained CPU PCM")
            node = fw.u32(node)
        report["checks"][name] = dict(
            before_id=before_id,
            after_id=fw.u32(w.STATE + 4),
            restore_status=fw.u32(w.STATE + 92),
        )
        fw.write(w.STATE + 76, bytes(4))
        session.tap("NO")
        session.chord("FUNC", "NO")
        session.tap("SRC")

    if not a.smoke:
        frozen = freeze()
        history_a = list(session.flex.pages)
        history_af = list(session.flex.pages)
        select(4, first["slot"])
        select(5, frozen["slot"])
        capture = session.capture_pad("a-pad")
        wire = read_frames(capture["path"])[capture["trigger"]]
        session.chord("TRK", "TRIG 1")
        # Native grid editing and normal PLAY, without host-scheduled notes.
        session.tap("RECORD")
        session.chord("FUNC", "PLAY")
        session.chord("FUNC", "PAGE")
        session.tap("PAGE")
        session.tap("NO")
        for step in (1, 5, 9, 13):
            session.tap(f"TRIG {step}")
        session.tap("SRC")
        session.tap("RECORD")
        session.recorder.frames.clear()
        session.recorder.ticks.clear()
        session.recorder.recording = True
        clock_trace = []
        from unicorn import UC_HOOK_CODE

        def clock_observe(*_):
            if len(clock_trace) < 4096:
                clock_trace.append(
                    dict(
                        tick=fw.u32(0x40966500),
                        step=int.from_bytes(fw.read(0x43164F98, 2), "big"),
                        pattern=fw.u32(0x4316501C),
                    )
                )

        clock_hook = fw.uc.hook_add(
            UC_HOOK_CODE, clock_observe, begin=0x400D5AEC, end=0x400D5AEC
        )
        session.tap("PLAY")
        second = record(2)

        def events():
            return [
                dict(
                    index=i,
                    tick=session.recorder.ticks[i],
                    slot=int.from_bytes(frame[0xE0:0xE2], "big"),
                )
                for i, frame in enumerate(session.recorder.frames)
                if int.from_bytes(frame[0x22:0x24], "big") & 1
            ]

        for _ in range(60):
            if len(events()) >= 5:
                break
            session.advance(10_000_000)
        require(
            len(events()) >= 5 and all(e["slot"] == first["slot"] for e in events()),
            "Native PLAY failed to sequence stable BUF",
        )
        report["checks"]["native-sequencer"] = events()
        report["clock_trace"] = clock_trace
        fw.uc.hook_del(clock_hook)
        session.tap("STOP")
        session.tap("STOP")
        session.recorder.recording = False
        require(second["slot"] == first["slot"], "Logical slot changed")
        require(
            payload(session.flex.pages, second["slot"])
            == session.flex.input.candidate(
                fw.u32(w.STATE + 24), fw.u32(w.STATE + 24) + second["frames"]
            ).pcm,
            "Replacement PCM differs",
        )
        require(
            frozen["allocation"]["start"] == first["allocation"]["start"],
            "Snapshot backing changed",
        )
        report["checks"]["second"], report["checks"]["frozen"] = second, frozen
        history_b = list(session.flex.pages)
        require(
            slot(0) == slot(4) == first["slot"] and slot(5) == frozen["slot"],
            "Shared/frozen track identity changed",
        )
        require(
            fw.read(0x405B6368 + first["slot"] * 16, 5) == b"BUF 1",
            "Native logical name lost",
        )
        ids = fw.u32(w.STATE + 4)
        session.record()
        session.chord("FUNC", "NO")
        session.tap("SRC")
        require(fw.u32(w.STATE + 4) == ids, "Cancel consumed identity")
        report["checks"]["cancel"] = True
        for fault, name in (
            (1, "admission-refused"),
            (4, "native-heap-refused"),
            (5, "incomplete-final-header"),
            (3, "post-alias-rollback"),
            (6, "stale-completion"),
        ):
            refusal(fault, name)
        for destination in (2, 3, 4):
            session.tap("SAMPLING")
            for _ in range(12):
                if session.flex.destination == destination:
                    break
                session.turn("C", 5)
            session.tap("SRC")
            record(destination + 5)
        require(fw.u32(w.STATE + 4) == 8, "Expected eight issued generations")
        # Return to BUF 1: native ninth admission fails, existing slots remain.
        session.tap("SAMPLING")
        for _ in range(16):
            if session.flex.destination == 1:
                break
            session.turn("C", -5)
        session.tap("SRC")
        refusal(0, "generation-capacity")
        with session.flex.native():
            frozen_before = fw.slot(frozen["slot"])
            fw.call(n.UNLOAD, [frozen["slot"]])
            fw.call(n.CLEAR, [frozen["slot"]])
            require(fw.slot(frozen["slot"]) == frozen_before, "Premature frozen reuse")
            require(
                fw.call(n.SAVE, [0, 0, 0]) == 0
                and fw.call(n.LOAD_PROJECT, [0, 0, 0, 0]) == 0,
                "Volatile project guard failed",
            )
            # Native metadata rejects a stale epoch and a forged full ref.
            require(
                fw.call(n.FREEZE, [1, 0, fw.u32(0x80004704)]) == 0xFFFFFFFD,
                "Stale snapshot epoch accepted",
            )
        session.flex.native_mode = True
        report["checks"]["native-project-and-reader-guards"] = True
        histories = dict(
            a=history_a, af=history_af, b=history_b, all=list(session.flex.pages)
        )
        inputs = dict(session.inputs)
        report["audio_inputs"] = dict(
            wire=wire.hex(), stable=first["slot"], frozen=frozen["slot"]
        )
        for name, pages in histories.items():
            dump_pages(out / f"pages-{name}.bin", pages)
        report["snapshots"] = session.flex.snapshots
        session.screenshot("02-native-four-buffers-and-frozen-a")
        if a.queued_freeze:
            freeze_matrix()
    report["contexts"] = session.flex.worker_contexts
    require(
        report["contexts"]
        and all(
            not row["direct"] and row["sr"] & 0x700 != 0x700
            for row in report["contexts"]
        ),
        "Worker ran as masked host diagnostic",
    )
    require(session.flex.resource_hle_calls == 0, "Host source HLE called")
    report["checks"]["source_hle_calls"] = session.flex.resource_hle_calls
    report["events"] = session.flex.events
    report["native_resources"] = session.flex.native_resource_calls
    report["retirements"] = session.flex.retirements
    require(not fw.card.writes, "BUF wrote a file")
    report["payload_ranges"] = session.flex.payload_ranges
    dump_pages(out / "native-pages.bin", session.flex.pages)
    if not a.smoke:
        session.close()
        session = None
        report["audio"] = audio_oracle(
            out, inputs, wire, first["slot"], frozen["slot"], histories
        )
    require(source_hashes() == sources, "Source changed during run")
    report["status"] = "passed"
    print("PASS", out / "report.json", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    if session:
        report["state"] = fw.read(w.STATE, 192).hex()
        report["events"] = session.flex.events
        report["contexts"] = session.flex.worker_contexts
        report["native_resources"] = session.flex.native_resource_calls
        session.screenshot("failure")
    raise
finally:
    if session:
        session.close()
    write_json(out / "report.json", report)
