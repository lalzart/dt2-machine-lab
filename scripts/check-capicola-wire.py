#!/usr/bin/env python3
"""Replay captured OS1.16 sample transfers and panel commands into native DSP."""

# ruff: noqa: E402, I001
import argparse
import array
import importlib.util
import json
import math
import os
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
p.add_argument("--capture", required=True, type=Path)
p.add_argument("--reserved-state", action="store_true")
p.add_argument(
    "--feedback", action="store_true", help="Validate the tagged native reply"
)
p.add_argument(
    "--selection", action="store_true", help="Prepare before the first trigger"
)
p.add_argument(
    "--sample-load",
    required=True,
    type=Path,
    help="Boot run containing flexbus.raw and CAPICOLA_MAIN_OS.bin",
)
p.add_argument(
    "--live-feedback",
    action="store_true",
    help="Validate slot-correlated quarter status",
)
args = p.parse_args()
if args.live_feedback:
    args.feedback = True
if args.feedback:
    require(
        args.selection and args.reserved_state, "Feedback requires reserved selection"
    )
out, capture, boot = (
    v.resolve() for v in (args.output, args.capture, args.sample_load)
)
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
doctor()
from lab import capicola_layout
from lab.capicola_controls import patch_cpu as controls
from lab.capicola_memory import BANK_BASE, patch_cpu as reserve
from lab.dsp import Dsp, header
from lab.flex_native_build import patch_cpu as flex
from lab.formats import read_frames
from lab.plaits import build_blob, build_cpu
from lab.plaits_menu import patch_cpu as menu
import sharcldr
import sharc_trace as st
from sharc_transpile_run import OPT_STOP_PC

POOL = 0x8422B9C8
LAYOUT = "reserved-state" if args.reserved_state else "legacy"
HANDOFF = capicola_layout.address(0x200E4000) if args.reserved_state else 0x200E4000
TEST_STACK = capicola_layout.address(0x200D7F00) if args.reserved_state else 0x200D7F00
report = dict(
    status="running",
    scope="Captured CPU sample transfer and panel wire into native SHARC voice buffers; no final-mix or physical timing proof",
)
try:
    sources = source_hashes()
    capture_report = json.loads((capture / "capture.json").read_text())
    require(capture_report["status"] == "passed", "Panel capture did not pass")
    build_cpu(family="integration")
    main, _ = controls(
        reserve(menu(flex((out / "PLAITS_MAIN_OS.bin").read_bytes())[0])[0])[0]
    )
    require(
        main
        == (capture / "CAPICOLA_MAIN_OS.bin").read_bytes()
        == (boot / "CAPICOLA_MAIN_OS.bin").read_bytes(),
        "CPU images differ",
    )
    blob = build_blob(
        True,
        family="capicola-live-feedback"
        if args.live_feedback
        else "capicola-feedback"
        if args.feedback
        else "capicola-selection"
        if args.selection
        else "capicola-controls",
        output=out / "candidate",
        layout=LAYOUT,
    )
    report["inputs"] = {
        str(f): sha256(f)
        for f in (
            capture / "capicola.dtfr",
            boot / "flexbus.raw",
            capture / "CAPICOLA_MAIN_OS.bin",
            out / "candidate/PLAITS_BLOB.bin",
        )
    }
    raw = (boot / "flexbus.raw").read_bytes()
    require(len(raw) % 4100 == 0, "Incomplete LP0 transfer")
    tags = [struct.unpack_from("<I", raw, i)[0] for i in range(0, len(raw), 4100)]
    pages = [t for t in tags if t < 0x19200]
    require(pages and max(pages) < 0x1000, "Bound this LP0 test to 16 MiB")
    extent = (max(pages) + 2) * 4096 + 1024
    split = sharcldr.parse_blocks(blob)[-1]["offset"]
    # Mapped zero RAM models the external pool and reserved bank; sample content
    # comes exclusively from the captured transfers through stock callbacks.
    blob = (
        blob[:split]
        + header(POOL - 1024, extent)
        + bytes(extent)
        + header(BANK_BASE - 256, 0x697A00)
        + bytes(0x697A00)
        + blob[split:]
    )
    poison = bytes([0xA5]) * capicola_layout.STATE_BYTES
    if args.reserved_state:
        split = sharcldr.parse_blocks(blob)[-1]["offset"]
        blob = (
            blob[:split]
            + header(capicola_layout.OLD_BASE, len(poison))
            + poison
            + blob[split:]
        )
    engine = Dsp(blob)
    core = engine.core

    def peek(address, count):
        return b"".join(
            struct.pack("<I", core.peek(address + i)) for i in range(0, count, 4)
        )

    guards = {}
    if args.reserved_state:
        for region in capicola_layout.REGIONS:
            name, low, high = region
            if name.endswith("stack"):
                addr = capicola_layout.STATE_BASE + low
                guards[addr] = bytes([0xC3]) * 64
                core.poke(addr, guards[addr], 1)

    registers = [f"{prefix}{i}" for prefix in ("R", "I", "M", "L") for i in range(16)]

    def deliver_samples(transfers=raw):
        saved = {r: core.get_reg(st.UREG_CODES[r]) for r in registers}
        # Stand in for LP0 DMA completion/resubmission, executing the stock firmware
        # callback and all page/header/guard-copy routines, including our hooks.
        core.set_option(OPT_STOP_PC, 0x1C834A)
        counts = []
        for pos in range(0, len(transfers), 4100):
            core.poke(0x268240, transfers[pos : pos + 4100], 1)
            values = dict(
                M5=0,
                M6=1,
                M7=-1,
                M14=1,
                I6=TEST_STACK,
                I7=TEST_STACK - 8,
                R4=0,
                R8=4,
                R12=0x268220,
            )
            values.update({f"L{i}": 0 for i in range(16)})
            for r, value in values.items():
                core.set_reg(st.UREG_CODES[r], st.Const(value))
            core.poke(TEST_STACK - 4, bytes(32), 1)
            before = core.stats()["instructions"]
            core.fresh_call(0x1C7E1F)
            core.run(50000)
            require(
                core.pc() == 0x1C834A,
                f"LP0 did not resubmit: {core.halt_reason} at {core.pc():x}",
            )
            counts.append(core.stats()["instructions"] - before)
        core.set_option(OPT_STOP_PC, 0)
        for r, value in saved.items():
            core.set_reg(st.UREG_CODES[r], value)
        return counts

    counts = deliver_samples()
    report.update(lp0_transfers=len(counts), max_lp0_instructions=max(counts))
    print("Captured sample transfers passed native LP0 callbacks", flush=True)

    wires = read_frames(capture / "capicola.dtfr")
    events = [
        i
        for i, w in enumerate(wires)
        if int.from_bytes(w[0x94:0x96], "big") == 8
        and int.from_bytes(w[0x22:0x24], "big") & 1
    ]
    require(events and events[-1] + 2 < len(wires), "Missing complete Capicola trigger")
    event = events[-1]
    # Stock scheduling loads/arms the voice on the block after the wire trigger.
    # Do not seed voice pointers, sample metadata, bank contents or trigger flags.
    held = bytearray(wires[event])
    held[0x22:0x24] = bytes(2)
    voices_before = (core.peek(0x2412CC), core.peek(0x2414A4))
    if args.selection:
        for _ in range(5):
            require(
                max(map(abs, engine.frame(bytes(held)))) == 0,
                "Selection triggered audio",
            )
    else:
        for wire in wires[max(0, event - 4) : event + 3]:
            engine.frame(wire)
    source, n = core.peek(0x2412CC), core.peek(0x241454)
    slot = int.from_bytes(wires[event][0xE0:0xE2], "big")
    require(slot < 0x400, "Expected project sample")
    left, right, size, rate, stereo = struct.unpack(
        "<5I", peek(0x257810 + slot * 20, 20)
    )
    if args.selection:
        source, n = POOL + left, size // 2
        require(
            source not in voices_before, "Fixture already assigned the selected sample"
        )
    require(
        source == POOL + left
        and n * 2 == size
        and left == right
        and rate == 48000
        and not (stereo & 255),
        "Stock assignment differs from loaded mono slot",
    )
    require(
        source >= POOL and source + n * 2 <= POOL - 1024 + extent and 0 < n <= 16384,
        "Use a short bounded fixture for full-wire replay",
    )
    if not args.selection:
        require(core.peek(0x2414A4) == source, "Mono lanes differ")
    data = array.array(
        "f",
        [
            v[0] / 32768
            for v in struct.iter_unpack("<h", peek(source, (n * 2 + 3) & ~3)[: n * 2])
        ],
    )
    spec = importlib.util.spec_from_file_location(
        "cap", ROOT / "scripts/check-capicola-capacity.py"
    )
    cap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cap)
    lib, _, _ = cap.build(out)
    bank = cap.Sample(lib, data)
    require(bank.result == 0, "Host bank construction failed")
    held = bytearray(wires[event])
    held[0x22:0x24] = bytes(2)
    status_address = (
        capicola_layout.address(0x200E4600) if args.reserved_state else 0x200E4600
    )
    status_names = (
        "sequence",
        "magic",
        "version",
        "slot",
        "state",
        "reason",
        "done",
        "total",
        "epoch",
        "source",
        "frames",
    )

    def preparation_status():
        values = dict(
            zip(
                status_names,
                struct.unpack("<11I", peek(status_address, 44)),
                strict=True,
            )
        )
        require(
            values["sequence"] % 2 == 0
            and values["magic"] == 0x43505331
            and values["version"] == 1,
            "Invalid native status record",
        )
        require(
            values["sequence"] == core.peek(status_address), "Torn native status read"
        )
        require(values["done"] <= values["total"], "Preparation progress overflow")
        if args.feedback:
            state = values["state"]
            percent = (
                100 * values["done"] // values["total"]
                if state == 3 and values["total"]
                else 100
                if state == 5
                else 0
            )
            expected_word = 0xD400 | state << 7 | percent if state else 0
            if args.live_feedback:
                index = state
                if state == 3 and values["total"]:
                    q = min(3, 4 * values["done"] // values["total"])
                    index = (3, 7, 8, 9)[q]
                expected_word = (
                    0x8000 | values["slot"] << 4 | index
                    if state and values["slot"] < 1024
                    else 0
                )
            base = 0x266220 + (core.peek(0x261CA4) & 1) * 4096
            require(
                core.peek(base + 0x1A, 2) == expected_word,
                "Native reply does not match progress",
            )
            raw_reply = peek(base, 0xABC)
            wire_reply = bytes(
                v
                for pair in zip(raw_reply[1::2], raw_reply[::2], strict=True)
                for v in pair
            )
            require(
                int.from_bytes(wire_reply[0x1A:0x1C], "big") == expected_word,
                "Reply parcel order",
            )
            # These are native block-handler reply buffers, before the SPI2 DMA
            # transport. Preserve them for a separately scoped CPU display replay.
            replies.append(wire_reply)
            values["reply_word"] = expected_word
            reply_statuses.append(dict(values))
        return values

    replies = []
    reply_statuses = []
    progress = []
    require(not core.peek(HANDOFF + 8), "Short fixture unexpectedly already prepared")
    for i in range(2 * ((n + 35) // 32) + 8):  # noqa: B007 - recorded after loop
        if core.peek(HANDOFF + 8) == 1:
            break
        pcm = engine.frame(bytes(held))
        require(max(map(abs, pcm)) == 0, "Unprepared sample rendered")
        if args.selection:
            progress.append(preparation_status())
    else:
        raise ValueError("Native frame preparation did not complete")
    require(
        peek(BANK_BASE, len(bank.payload())) == bank.payload(),
        "Native keys differ from host",
    )
    report.update(
        sample_slot=slot,
        sample_source=hex(source),
        sample_frames=n,
        frames_until_ready=i,
        bank_bytes=len(bank.payload()),
    )
    print("Stock-assigned sample prepared through normal audio blocks", flush=True)

    if args.selection:
        require(
            (core.peek(0x2412CC), core.peek(0x2414A4)) == voices_before,
            "Preparation needed a voice assignment",
        )
        require(
            all(
                a["epoch"] == b["epoch"] and a["done"] <= b["done"]
                for a, b in zip(progress[:-1], progress[1:], strict=True)
            ),
            "Progress regressed within preparation",
        )
        require(
            progress[-1]["state"] == 5
            and progress[-1]["done"] == 2 * (n + 4)
            and progress[-1]["slot"] == slot,
            "READY status does not match selected sample",
        )
        write_json(out / "preparation-progress.json", progress)
        if args.feedback:
            (out / "native-preparation-replies.bin").write_bytes(b"".join(replies))
        report.update(
            prepared_before_first_trigger=True,
            unchanged_previous_voice_pointers=[hex(v) for v in voices_before],
            ready_status=progress[-1],
        )

    pitch, advance, gain = struct.unpack("<3f", peek(HANDOFF + 16, 12))
    reference = cap.Reader(bank)
    require(reference.start(pitch, advance) == 0, "Oracle controls failed")
    blocks = math.ceil(reference.state.duration / 32) + 2
    expected = array.array("f")
    expected.frombytes(reference.render(blocks * 32))
    expected = array.array("f", [v * gain for v in expected])
    # One fixed block of command latency, not a fitted alignment. Assert silence
    # on that block, then compare the whole sample and its completed silent tail.
    onset = engine.frame(wires[event])
    require(
        max(map(abs, onset)) == 0, "Trigger no longer has the stock one-block latency"
    )
    audio = []
    for _ in range(blocks):
        audio.extend(engine.frame(bytes(held)))
    actual = array.array("f", audio[::2])
    require(
        actual.tobytes() == array.array("f", audio[1::2]).tobytes(),
        "Mono lane output differs",
    )
    require(max(map(abs, actual)) > 1e-5, "CPU-triggered voice is silent")
    mx, rms = cap.previous.error(expected.tobytes(), actual.tobytes())
    require(mx <= 1e-4 and rms <= 1e-5, "CPU-to-DSP voice mismatch")
    require(max(map(abs, actual[-32:])) == 0, "Completed voice did not stop")
    # The unfixed comparison must actually fail, preventing a vacuous silent pass.
    wrong = array.array("f", [0.0] * 32 + list(actual[:-32]))
    bad_max, bad_rms = cap.previous.error(expected.tobytes(), wrong.tobytes())
    require(bad_max > 1e-4 and bad_rms > 1e-5, "Latency negative control did not fail")
    cap.ref.save_wav(out / "capicola-cpu-to-dsp.wav", actual.tobytes())
    # Reload at the same PCM address only after the first bank has been ready.
    # This exercises relocated event/epoch state and its private interrupt stack.
    generation = core.peek(HANDOFF + 32)
    if args.selection:
        page_position = next(
            pos
            for pos in range(0, len(raw), 4100)
            if struct.unpack_from("<I", raw, pos)[0] == left // 4096
        )
        deliver_samples(raw[page_position : page_position + 4100])
        require(core.peek(HANDOFF + 8) == 0, "Page write left old bank published")
        require(
            max(map(abs, engine.frame(bytes(held)))) == 0,
            "Page invalidation leaked audio",
        )
        require(preparation_status()["state"] == 4, "Missing waiting-for-load status")
        report["page_write_waits_for_header"] = True
    reload_counts = deliver_samples()
    require(core.peek(HANDOFF + 8) == 0, "Reload kept the old bank published")
    for reload_frames in range(2 * ((n + 35) // 32) + 8):  # noqa: B007
        if core.peek(HANDOFF + 8) == 1:
            break
        require(
            max(map(abs, engine.frame(bytes(held)))) == 0,
            "Reload preparation rendered stale audio",
        )
    else:
        raise ValueError("Reload did not prepare a new bank")
    require(core.peek(HANDOFF + 32) != generation, "Reload reused the old generation")
    require(
        peek(BANK_BASE, len(bank.payload())) == bank.payload(), "Reload changed keys"
    )
    require(
        max(map(abs, engine.frame(wires[event]))) == 0, "Reload trigger latency changed"
    )
    reloaded = []
    for _ in range(blocks):
        reloaded.extend(engine.frame(bytes(held)))
    require(
        array.array("f", reloaded).tobytes() == array.array("f", audio).tobytes(),
        "Reload playback is not identical",
    )
    report.update(
        reload_transfers=len(reload_counts),
        reload_frames_until_ready=reload_frames,
        max_reload_lp0_instructions=max(reload_counts),
        reload_audio_identical=True,
    )
    if args.selection:
        # Explicit synthetic table entries are negative controls only. Positive
        # preparation above used solely captured LP0 data and CPU commands.
        saved_entry = peek(0x257810 + slot * 20, 20)
        negative_cases = []
        cases = [
            ("empty", slot, (left, right, 0, rate, 0), 1, 1),
            ("preview", 1024, None, 2, 2),
            ("signed-slot", 65535, None, 2, 2),
            ("different-channels", slot, (left, left + 2, size, rate, 0), 2, 3),
            ("stereo-flag", slot, (left, right, size, rate, 1), 2, 3),
            ("sample-rate", slot, (left, right, size, 44100, 0), 2, 4),
            ("too-long", slot, (left, right, 1152002, rate, 0), 2, 5),
            ("too-short", slot, (left, right, 280, rate, 0), 2, 6),
            ("odd-length", slot, (left, right, size + 1, rate, 0), 2, 7),
            ("odd-offset", slot, (left + 1, right + 1, size, rate, 0), 2, 7),
            ("outside-pool", slot, (0x18800000, 0x18800000, size, rate, 0), 2, 7),
            ("cross-pool-end", slot, (0x187FFFFE, 0x187FFFFE, size, rate, 0), 2, 7),
        ]
        for name, selected, entry, state, reason in cases:
            core.poke(
                0x257810 + slot * 20,
                struct.pack("<5I", *entry) if entry else saved_entry,
                1,
            )
            wire = bytearray(held)
            wire[0xE0:0xE2] = struct.pack(">H", selected)
            for _ in range(3):
                engine.frame(bytes(wire))
            status = preparation_status()
            require(
                not core.peek(HANDOFF + 8)
                and status["state"] == state
                and status["reason"] == reason
                and status["source"] == 0,
                f"Unsupported selection accepted: {name}: {status}",
            )
            require(
                max(map(abs, engine.frame(bytes(wire)))) == 0,
                f"Invalid sample rendered: {name}",
            )
            negative_cases.append(dict(case=name, status=status))
        core.poke(0x257810 + slot * 20, saved_entry, 1)
        # Start one valid source, abandon it mid-count, then select it again.
        for _ in range(8):
            engine.frame(bytes(held))
        before = preparation_status()
        require(
            before["state"] == 3 and 0 < before["done"] < before["total"],
            "Missing partial preparation",
        )
        empty = bytearray(held)
        empty_slot = next(
            (
                v
                for v in range(1024)
                if v != slot and core.peek(0x257810 + v * 20 + 8) == 0
            ),
            None,
        )
        require(empty_slot is not None, "No empty slot in captured table")
        empty[0xE0:0xE2] = struct.pack(">H", empty_slot)
        for _ in range(3):
            engine.frame(bytes(empty))
        require(
            preparation_status()["state"] == 1 and not core.peek(HANDOFF + 8),
            "Selection did not cancel",
        )
        for _ in range(3):
            engine.frame(bytes(held))
        restarted = preparation_status()
        require(
            restarted["epoch"] != before["epoch"]
            and restarted["done"] < before["done"],
            "Selection resumed stale work",
        )
        for _ in range(2 * ((n + 35) // 32) + 8):
            if core.peek(HANDOFF + 8):
                break
            require(
                max(map(abs, engine.frame(bytes(held)))) == 0, "Restart leaked audio"
            )
        require(
            core.peek(HANDOFF + 8) == 1
            and peek(BANK_BASE, len(bank.payload())) == bank.payload(),
            "Restart did not restore exact bank",
        )
        engine.frame(wires[event])
        require(
            max(map(abs, engine.frame(bytes(held)))) > 1e-5,
            "Active cancellation comparator is silent",
        )
        engine.frame(bytes(empty))  # Stock command pipeline: one block.
        require(
            max(map(abs, engine.frame(bytes(empty)))) == 0,
            "Playing voice survived selection of an empty slot",
        )
        require(
            not core.peek(HANDOFF + 8) and preparation_status()["state"] == 1,
            "Empty selection kept READY",
        )
        off = bytearray(held)
        off[0x94:0x96] = struct.pack(">H", 0)
        for _ in range(3):
            engine.frame(bytes(off))
        require(
            preparation_status()["state"] == 0 and not core.peek(HANDOFF + 8),
            "Machine exit kept preparation active",
        )
        report.update(
            selection_negatives=negative_cases,
            mid_prepare_cancellation=True,
            playing_selection_cancelled=True,
            machine_exit_cancels=True,
            progress_restarted={"before": before, "after": restarted},
        )
    if args.reserved_state:
        require(
            peek(capicola_layout.OLD_BASE, len(poison)) == poison,
            "Candidate wrote the retired L2 working region",
        )
        for addr, guard in guards.items():
            require(
                peek(addr, len(guard)) == guard, "Private stack boundary overwritten"
            )
        report.update(retired_l2_bytes_unchanged=len(poison), stack_guards=len(guards))
    require(source_hashes() == sources, "Source drift")
    if args.feedback:
        (out / "native-preparation-replies.bin").write_bytes(b"".join(replies))
        write_json(out / "native-reply-statuses.json", reply_statuses)
        report["native_reply_snapshots"] = len(replies)
    report.update(
        status="passed",
        wire_trigger_frame=event,
        trigger_latency_samples=32,
        output_frames=len(actual),
        max_error=mx,
        rms_error=rms,
        latency_negative_max_error=bad_max,
        latency_negative_rms_error=bad_rms,
        pitch=pitch,
        advance=advance,
        gain=gain,
        max_frame_instructions=max(engine.block_instructions),
        sources=sources,
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))
