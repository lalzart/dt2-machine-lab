#!/usr/bin/env python3
# ruff: noqa: E402
"""Native DSP allocation release/reuse in an explicit paused closed world.

Capture producer, LP0 delivery and DSP-proof mailbox delivery are modeled.
No host capture/publication/registry commit or simulated allocator success.
"""

import argparse
import array
import ctypes
import hashlib
import os
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, sha256, source_hashes, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--smoke", action="store_true")
a = p.parse_args()
provenance = doctor()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored out/runs")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

import plusdrive_check as check
import tools.plusdrive as pd
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k

from lab import recorder_dsp_reuse as r
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_retirement as old
from lab import recorder_retirement_gate as gate
from lab import recorder_worker_code as w
from lab.dsp import Dsp
from lab.flex_audio import baseline_pages
from lab.flex_dsp_probe import control
from lab.flex_freeze_probe import dump_pages, payload
from lab.flex_heap import inspect_heap
from lab.flex_lite import FlexDsp
from lab.flex_recorder import Take
from lab.flex_session import Session
from lab.formats import read_frames
from lab.recorder_freeze_worker_native import QueuedFreezeUI
from lab.runtime import STOCK_MAIN

sources = source_hashes()
write_json(out / "sources.json", sources)
report = dict(
    status="running",
    provenance=provenance,
    checks={},
    cycles=[],
    releases=[],
    scope=__doc__,
    native_save=False,
    native_retirement_transport=False,
    identity_recycling=False,
    proof_delivery="modeled, actual native diagnostic",
    closed_world="both CPUs paused; stopped isolated project; no unmodeled producers",
)
session = ref_fw = None


class Observed(FlexDsp):
    def __init__(self, blob, state=None):
        Dsp.__init__(self, blob)
        if state is not None:
            buf = ctypes.create_string_buffer(state)
            require(
                self.core._lib.sharc_native_import_state(
                    self.core._handle, buf, len(state)
                )
                == 0,
                "Clone failed",
            )


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


def allocations():
    begin, end = fw.u32(0x405A0F64), fw.u32(0x405A0F68)
    require(end >= begin and (end - begin) % 52 == 0, "Allocation vector invalid")
    rows = []
    for at in range(begin, end, 52):
        start, size, gap = struct.unpack(">3I", fw.read(at + 16, 12))
        rows.append(
            dict(start=start, size=size, preceding_free=gap, aliases=fw.u32(at + 48))
        )
    return rows


def snapshot():
    return dict(
        allocations=allocations(),
        keys=fw.read(0x405B1368, 16384).hex(),
        registry=fw.read(n.GEN, 512).hex(),
        project=fw.read(fw.u32(w.STATE + 68), 16384).hex(),
        private=[fw.slot(fw.u32(w.STATE + 112 + i * 4)) for i in range(8)],
    )


def record(number):
    trace_start = len(trace)
    session.flex.input.source = pcm(number)
    session.chord("TRK", "TRIG 1")
    session.record()
    session.tap("YES")
    for _ in range(20):
        session.flex.sync_observation()
        if session.flex.phase == "assigned":
            break
        session.advance()
    require(session.flex.phase == "assigned", "Native USE failed")
    session.advance()
    session.flex.sync_observation()
    current = dict(session.flex.current)
    current["id"] = fw.u32(0x405B1368 + current["slot"] * 16)
    current["private"] = fw.u32(w.STATE + 72)
    current["epoch"] = fw.u32(n.STATE)
    current["pcm"] = payload(session.flex.pages, current["slot"])
    expected = session.flex.input.candidate(
        fw.u32(w.STATE + 24), fw.u32(w.STATE + 24) + current["frames"]
    ).pcm
    require(current["pcm"] == expected, "Native capture/transport PCM mismatch")
    require(
        not fw.sources and not fw.handles and not fw.direct, "Host transaction used"
    )
    node = fw.u32(w.STATE)
    while node:
        require(fw.u32(node + 20) == 0, "Retained CPU PCM")
        node = fw.u32(node)
    report["cycles"].append(
        dict(
            number=number,
            identity=current["id"],
            slot=current["slot"],
            private=current["private"],
            allocation=current["allocation"],
            allocations=allocations(),
            heap_free=inspect_heap(fw.read).free_bytes,
            cpu_pcm_freed=fw.u32(w.STATE + 84),
            private_slots=[fw.slot(fw.u32(w.STATE + 112 + i * 4)) for i in range(8)],
            track1=fw.read(fw.u32(0x80004704) + 0x80, 2).hex(),
            native_allocator_trace=list(trace[trace_start:]),
        )
    )
    print("record", number, current["id"], current["allocation"], flush=True)
    dump_pages(out / f"pages-{number}.bin", session.flex.pages)
    (out / f"candidate-{number}.pcm").write_bytes(current["pcm"])
    return current


def freeze():
    before = fw.u32(q.STATE + 32)
    fw.write(q.STATE, struct.pack(">I", fw.u32(q.STATE) + 1))
    session.turn("A", 0)
    for _ in range(20):
        if fw.u32(q.STATE + 32) > before:
            break
        session.advance()
    require(fw.u32(q.STATE + 32) == before + 1, "Native FREEZE did not finish")
    result = fw.u32(q.STATE + 12)
    require(result < 1024, f"FREEZE failed {result:#x}")
    return result


def observation(engine, item, seq, *, wire_slot=None, trigger=False, blocks=3):
    allocation = item["allocation"]
    engine.publish(
        [
            (
                old.constants()["TAG"],
                old.packet(
                    item["epoch"],
                    item["id"],
                    seq,
                    allocation["start"],
                    allocation["size"],
                ),
                1,
            )
        ]
    )
    for i in range(blocks):
        engine.frame(
            control(
                wire,
                stable if wire_slot is None else wire_slot,
                trigger=trigger and i == 0,
            )
        )
    base = gate.contract()["constants"]["STATE"]
    values = [engine.core.peek(base + i * 4) for i in range(97)]
    require(
        values[10] and values[27] == 0 and values[28] == 127,
        "Diagnostic permission/unknown boundary changed",
    )
    return values


def release(item, view, *, exclusive=True, expected=None):
    before = snapshot()
    dsp_before = actual.state_bytes()
    allocation = item["allocation"]
    old_pcm_hash = hashlib.sha256(
        actual.sample_bytes(allocation["start"] - 1024, allocation["size"])
    ).hexdigest()
    r.deliver(fw, view, item["allocation"], exclusive=exclusive)
    trace.clear()
    pages_before = len(session.flex.pages)
    direct_pages_before = len(fw.pages)
    with fw.transaction():
        result = fw.call(
            r.ENTRY, [item["id"], item["epoch"], fw.u32(0x80004704), view[13]]
        )
    # Paused diagnostic calls use AttachedFirmware's existing publisher HLE:
    # these are captured native unload arguments, not a synthetic clear header.
    session.flex.pages.extend(fw.pages[direct_pages_before:])
    after = snapshot()
    if expected is not None:
        require(
            result == expected & 0xFFFFFFFF,
            f"Wrong refusal {result:#x}, expected {expected}",
        )
        require(
            before == after and len(session.flex.pages) == pages_before,
            "Failed release changed playback ownership",
        )
        require(actual.state_bytes() == dsp_before, "Refused release changed DSP state")
    record = dict(
        identity=item["id"],
        result=result,
        before=before["allocations"],
        after=after["allocations"],
        native_trace=list(trace),
        diagnostic=view[:35],
        exclusive_certificate=exclusive,
        resident_extent_sha256=old_pcm_hash,
    )
    report["releases"].append(record)
    if result == 0:
        require(fw.slot(item["private"])["empty"], "Private cache owner retained")
        require(
            fw.u32(n.GEN + (item["id"] - n.FIRST_ID) * 64) == 3,
            "Old identity not tombstoned",
        )
        require(
            len(after["allocations"]) == len(before["allocations"]) - 1,
            "No allocator record was removed",
        )
        require(
            sum(x["size"] for x in before["allocations"])
            - sum(x["size"] for x in after["allocations"])
            == item["allocation"]["size"],
            "Wrong DSP extent released",
        )
        require(
            any(x["pc"] == 0x4015416C for x in trace)
            and any(x["pc"] == 0x401541FC for x in trace),
            "Stock final-owner release not executed",
        )
        for engine in (actual,):
            engine.publish(session.flex.pages[pages_before:])
        require(
            actual.slot_record(item["private"])[2] == 0, "DSP private header retained"
        )
        require(
            hashlib.sha256(
                actual.sample_bytes(allocation["start"] - 1024, allocation["size"])
            ).hexdigest()
            == old_pcm_hash,
            "Unload unexpectedly changed PCM bytes",
        )
        with fw.transaction():
            require(
                fw.call(n.LOOKUP, [item["id"]]) == 0, "Stale identity still resolves"
            )
            # Original loader attempts resolution BEFORE its cache lookup.
            # The empty nonreserved target stays empty after stale acquisition.
            target = 400
            require(fw.slot(target)["empty"], "Stale test target occupied")
            ref = n.GEN + (item["id"] - n.FIRST_ID) * 64 + 48
            require(
                fw.call(0x40154540, [ref, target]) != 0, "Stale cache alias acquired"
            )
            require(fw.slot(target)["empty"], "Stale load populated target")
    print(
        "release",
        item["id"],
        hex(result),
        "DSP",
        len(before["allocations"]),
        "->",
        len(after["allocations"]),
        flush=True,
    )
    return result


def resident(item):
    """Diagnostic host readback only; not a native SAVE path."""
    descriptor = actual.slot_record(item["slot"])
    left, right, length = descriptor[:3]
    lpcm, rpcm = actual.sample_bytes(left, length), actual.sample_bytes(right, length)
    pcm = b"".join(
        lpcm[i : i + 2][::-1] + rpcm[i : i + 2][::-1] for i in range(0, length, 2)
    )
    require(pcm == item["pcm"], "Actual resident DSP PCM differs from native candidate")
    extent = item["allocation"]
    return dict(
        descriptor=descriptor,
        pcm_sha256=hashlib.sha256(pcm).hexdigest(),
        extent_sha256=hashlib.sha256(
            actual.sample_bytes(extent["start"] - 1024, extent["size"])
        ).hexdigest(),
    )


def exact_audio(item, history, label=None):
    """Independent original CPU disk load -> stock ONESHOT oracle."""
    global ref_fw
    label = str(item["generation"]) if label is None else label
    play_slot = item["slot"]
    folder = out / f"reference-{label}"
    folder.mkdir()
    with wave.open(str(folder / "sample.wav"), "wb") as f:
        f.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        pcm_le = b"".join(
            item["pcm"][i : i + 2][::-1] for i in range(0, len(item["pcm"]), 2)
        )
        f.writeframes(pcm_le)
    card = out / f"reference-{label}.img"
    entries = pd.build(str(folder), str(card), main_os=STOCK_MAIN.read_bytes())
    snap = (
        ROOT.parent
        / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap"
    )
    require(
        sha256(snap)
        == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
        "Oracle snapshot drift",
    )
    ref_fw = check.Firmware(card, snap, STOCK_MAIN)
    try:
        ref_fw.call(0x40154358, [])
        check.check_mount(ref_fw, entries[0]["ref"])
        loaded = check.check_load(ref_fw, entries[0]["ref"], play_slot)
        require(
            loaded["load_d0"] == 0
            and all(
                check.sent_pcm_matches(
                    loaded, pd.build_native_sample(item["pcm"], True)
                )
            ),
            "Stock file oracle failed",
        )
        ref_pages = list(ref_fw.pages)
    finally:
        ref_fw.close()
        ref_fw = None
    take, reference = FlexDsp(), FlexDsp()
    for engine in (take, reference):
        engine.publish(baseline)
    take.publish(history)
    reference.publish(ref_pages)
    chunks = []
    for i in range(48):
        frame = control(wire, play_slot, trigger=i == 0)
        x = array.array("f", take.frame(frame)).tobytes()
        y = array.array("f", reference.frame(frame)).tobytes()
        require(x == y, "Reused ONESHOT differs from stock-file PCM")
        chunks.append(x)
    data = b"".join(chunks)
    require(any(struct.unpack(f"<{len(data) // 4}f", data)), "Silent oracle")
    (out / f"audio-{label}.f32").write_bytes(data)
    return dict(exact=True, blocks=48, sha256=hashlib.sha256(data).hexdigest())


try:
    fixture = ROOT / "out/runs/recorder-barrier-probe-20261022-02/dsp/GATE_BLOB.bin"
    require(
        sha256(fixture)
        == "d4e9a786dc74fb26b174f5f591a2b1de6e68af202778c870f09eb65bf555b153",
        "Existing diagnostic build drift",
    )
    blob = fixture.read_bytes()
    session = Session(pcm(1), out, adapter_factory=QueuedFreezeUI)
    fw = session.flex.fw
    code = r.install(fw)
    (out / "reclaim.bin").write_bytes(code)
    trace = []
    for pc in (
        n.UNLOAD,
        n.CLEAR,
        0x4015415E,
        0x4015416C,
        0x40154174,
        0x4015419E,
        0x401541CC,
        0x401541FC,
        0x4015366E,
        0x401535C2,
        0x4015444E,
        0x401543A6,
    ):

        def observe(uc, address, *_):
            trace.append(
                dict(
                    pc=address,
                    sr=uc.reg_read(k.UC_M68K_REG_SR),
                    a2=uc.reg_read(k.UC_M68K_REG_A2),
                )
            )

        session.flex.hooks.append(
            fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)
        )
    session.tap("SAMPLING")
    for _ in range(14):
        if session.flex.destination == 1:
            break
        session.turn("C", 5)
    require(session.flex.destination == 1, "DEST failed")
    session.tap("SRC")
    session.tap("STOP")
    session.tap("STOP")
    first = record(1)
    stable = first["slot"]
    capture = session.capture_pad("first-trigger")
    frames = read_frames(capture["path"])
    wire = next(f for f in frames if int.from_bytes(f[0x22:0x24], "big") & 1)
    baseline = baseline_pages(session.inputs["lp0"])
    actual = Observed(blob)
    actual.publish(baseline)
    actual.publish(session.flex.pages)
    report["resident_a"] = resident(first)
    initial_state = actual.state_bytes()
    actual.frame(control(wire, stable, trigger=True))
    actual.frame(control(wire, stable))
    old_pages = len(session.flex.pages)
    second = record(2)
    report["audio"] = {"b": exact_audio(second, list(session.flex.pages))}
    actual.publish(session.flex.pages[old_pages:])
    report["resident_b"] = resident(second)
    active = observation(actual, first, 1)
    require(active[15], "A active-reader case not reached")
    release(first, active, expected=-4)
    report["checks"]["active-reader-refused"] = True
    pending_engine = Observed(blob, initial_state)
    # Match the CPU's replacement: logical BUF 1 must already name B. A has
    # only its private owner, so this refusal isolates the queued selection.
    pending_engine.publish(session.flex.pages[old_pages:])
    pending = observation(
        pending_engine, first, 2, wire_slot=first["private"], trigger=True, blocks=1
    )
    require(
        pending[15] == 0
        and pending[17] == 0
        and pending[18] == 1
        and (pending[22] or pending[23] or pending[24]),
        "Zero-reader pending-trigger case not reached",
    )
    release(first, pending, expected=-4)
    pending_engine.frame(control(wire, first["private"]))
    require(
        pending_engine.reading(first["private"]),
        "Pending A did not acquire on next block",
    )
    report["checks"]["zero-reader-pending-refused"] = True
    # Retrigger current B on alternating stock lanes to remove old A pointers,
    # then stop all event production and drain both command banks.
    session.tap("STOP")
    session.tap("STOP")
    for i in range(40):
        actual.frame(control(wire, stable, trigger=i in (0, 12, 24)))
    quiet = observation(actual, first, 3)
    report["initial_quiet"] = quiet[:35]
    release(first, quiet, exclusive=False, expected=-1)
    report["checks"]["unknown-ownership-refused"] = True
    result = release(first, quiet)
    require(result == 0, f"Positive reclamation refused: {result:#x}; DSP {quiet[:35]}")
    report["checks"]["one-native-release"] = True
    old_pages = len(session.flex.pages)
    third = record(3)
    actual.publish(session.flex.pages[old_pages:])
    report["resident_c"] = resident(third)
    require(
        report["resident_c"]["extent_sha256"] != report["resident_a"]["extent_sha256"],
        "Reused extent still contains A",
    )
    require(
        third["allocation"]["start"] == first["allocation"]["start"]
        and third["allocation"]["size"] <= first["allocation"]["size"]
        and third["id"] != first["id"],
        "C did not consume A's released extent with a distinct identity",
    )
    report["checks"]["actual-dsp-reuse"] = True
    with fw.transaction():
        require(
            fw.call(n.LOOKUP, [first["id"]]) == 0, "A revived after C reused memory"
        )
        require(
            fw.call(0x40154540, [n.GEN + 48, 400]) != 0 and fw.slot(400)["empty"],
            "Stale A loader acquired C's allocation",
        )
    report["checks"]["stale-a-refused-after-reuse"] = True
    report["audio"]["c"] = exact_audio(third, list(session.flex.pages))
    if not a.smoke:
        # B is now obsolete; reject once while still read, then drain and free.
        b_live = observation(actual, second, 4)
        release(second, b_live, expected=-4)
        for i in range(40):
            actual.frame(control(wire, stable, trigger=i in (0, 12, 24)))
        b_quiet = observation(actual, second, 5)
        require(release(second, b_quiet) == 0, "B release failed")
        old_pages = len(session.flex.pages)
        frozen_slot = freeze()  # Freeze C with the existing native worker.
        actual.publish(session.flex.pages[old_pages:])
        old_pages = len(session.flex.pages)
        fourth = record(4)
        actual.publish(session.flex.pages[old_pages:])
        frozen = observation(actual, third, 6)
        release(third, frozen, expected=-3)
        report["checks"]["native-frozen-snapshot-refused"] = frozen_slot
        previous = fourth
        for number in range(5, 9):
            old_pages = len(session.flex.pages)
            current = record(number)
            actual.publish(session.flex.pages[old_pages:])
            for i in range(40):
                actual.frame(control(wire, stable, trigger=i in (0, 12, 24)))
            quiet = observation(actual, previous, number + 2)
            require(release(previous, quiet) == 0, "Repeated release failed")
            report["audio"][str(number)] = exact_audio(
                current, list(session.flex.pages)
            )
            previous = current
        report["audio"]["late-frozen-c"] = exact_audio(
            dict(third, slot=frozen_slot), list(session.flex.pages), "late-frozen-c"
        )
        require(fw.u32(w.STATE + 4) == 8, "Issued-generation cap changed")
        # Exercise the real admission guard; no ID increment or publication.
        before = snapshot()
        pages = len(session.flex.pages)
        session.flex.input.source = pcm(9)
        session.record()
        session.tap("YES")
        session.advance()
        require(
            fw.u32(w.STATE + 4) == 8
            and snapshot() == before
            and len(session.flex.pages) == pages,
            "Ninth request changed resources or bypassed admission",
        )
        report["checks"]["eight-issued-limit-preserved"] = True
    require(source_hashes() == sources, "Sources drifted during experiment")
    require(session.flex.resource_hle_calls == 0, "Resource HLE used")
    report["native_source_frees"] = session.flex.retirements
    report["status"] = "passed-restricted-emulator"
    print("PASS", out / "report.json", flush=True)
except BaseException as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    if session:
        session.close()
    if ref_fw:
        ref_fw.close()
    write_json(out / "report.json", report)
