#!/usr/bin/env python3
"""Check reply ownership, unchanged builds/fields and native SPI2 transmission."""

# ruff: noqa: E402, I001
import argparse
import hashlib
import json
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
p.add_argument("--live-feedback", action="store_true")
args = p.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
doctor()
from lab.capicola_feedback import HINT, REPLY_WORD, TEXT, patch_cpu
from lab import capicola_layout as layout
from lab.dsp import Dsp
from lab.formats import read_frames
from lab.plaits import build_blob
from lab.runtime import LIB, STOCK_BLOB
import sharc_harness as harness
import sharc_transpile_run as native
import sharcldr
from sharc_core.memory import UnmodeledMMR, _dm_read
from sharc_core.values import Const

if args.live_feedback:
    from lab.capicola_live_feedback import SAMPLE_WORD, patch_cpu
FAMILY = "capicola-live-feedback" if args.live_feedback else "capicola-feedback"
report = dict(
    status="running",
    hardware_verified=False,
    scope="Native reply fields, prior DSP build parity, fresh DSP application entry and actual SPI2/SPORT DMA. SPI smoke uses an empty project slot; selected-sample progress and CPU display are separate replays.",
)
try:
    sources = source_hashes()
    candidate = build_blob(
        True,
        family=FAMILY,
        layout="reserved-state",
        output=out / "candidate",
    )
    repeat = build_blob(
        True, family=FAMILY, layout="reserved-state", output=out / "repeat"
    )
    require(candidate == repeat, "Feedback build is not exact repeat")
    previous = build_blob(
        True,
        family="capicola-selection",
        layout="reserved-state",
        output=out / "previous",
    )
    require(
        hashlib.sha256(previous).hexdigest()
        == "9fd52edc63ccd428e076653311f796b0ea7e67758d28288b44351af76f6cf879",
        "Previous selection image changed",
    )
    if args.live_feedback:
        old_feedback = build_blob(
            True,
            family="capicola-feedback",
            layout="reserved-state",
            output=out / "previous-feedback",
        )
        require(
            hashlib.sha256(old_feedback).hexdigest()
            == "459c667dee6850dc59f0582d20289ca1539cac2e6cd303032ca0003b091fc88e",
            "Previous feedback image changed",
        )
    legacy = build_blob(True, family="capicola-controls", output=out / "legacy")
    require(
        hashlib.sha256(legacy).hexdigest()
        == "ce51ec4ced24b1617ae35337c4bf7cdddf22a2d288f320d74fc3d636206f2c5f",
        "Legacy controls image changed",
    )
    main = (ROOT / "out/runs/capicola-panel-08/CAPICOLA_MAIN_OS.bin").read_bytes()
    image, metadata = patch_cpu(main)
    require(patch_cpu(main) == (image, metadata), "CPU overlay is not exact repeat")
    try:
        patch_cpu(bytes(len(main)))
    except ValueError:
        pass
    else:
        raise ValueError("Unknown CPU image accepted")
    (out / "FEEDBACK_MAIN_OS.bin").write_bytes(image)
    write_json(out / "cpu-patches.json", metadata)
    report.update(
        blob_sha256=hashlib.sha256(candidate).hexdigest(),
        cpu_sha256=metadata["sha256"],
        exact_repeat=True,
        previous_builds_unchanged=True,
    )
    # Execute the actual ColdFire getter across the complete wire-word domain.
    # Only valid ABI words may show READY or progress; other types delegate to
    # the preserved getter. These synthetic words are decoder negatives, not
    # evidence of DSP preparation or transport.
    import plusdrive_check as cf

    cpu_inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
    checkpoint = ROOT / "out/runs/capicola-panel-05/capicola-ready.snap"
    fw = cf.Firmware(cpu_inputs["card"], checkpoint, out / "FEEDBACK_MAIN_OS.bin")
    original = cf.Firmware(
        cpu_inputs["card"],
        checkpoint,
        ROOT / "out/runs/capicola-panel-08/CAPICOLA_MAIN_OS.bin",
    )
    try:
        for w in metadata["writes"]:
            fw.write(w["address"], bytes.fromhex(w["after"]))
        fw.uc.ctl_remove_cache(0x40000400, 0x40000400 + len(image))
        valid = {
            0xD480: "EMPTY",
            0xD500: "FORMAT",
            0xD600: "WAIT",
            0xD6E4: "READY",
            0xD700: "ERROR",
        }
        for percent in range(101):
            valid[0xD580 | percent] = (
                "P<25%"
                if percent < 25
                else "P<50%"
                if percent < 50
                else "P<75%"
                if percent < 75
                else "P<100%"
            )
        if args.live_feedback:
            fw.write(SAMPLE_WORD, struct.pack(">H", 7))
            valid = {0x8070 | i: text for i, text in enumerate(TEXT)}
        for word in range(65536):
            fw.write(REPLY_WORD, struct.pack(">H", word))
            pointer = fw.call(HINT, [8], limit=500)
            require(pointer in metadata["pointers"], "Invalid native caption pointer")
            require(
                TEXT[metadata["pointers"].index(pointer)] == valid.get(word, ""),
                "Malformed word produced a caption",
            )
        if args.live_feedback:
            for slot in range(1024):
                fw.write(SAMPLE_WORD, struct.pack(">H", slot))
                for index in range(16):
                    fw.write(REPLY_WORD, struct.pack(">H", 0x8000 | slot << 4 | index))
                    pointer = fw.call(HINT, [8], limit=500)
                    require(
                        pointer == metadata["pointers"][index if index < 10 else 0],
                        "Slot boundary decoder mismatch",
                    )
            fw.write(SAMPLE_WORD, struct.pack(">H", 1024))
            fw.write(REPLY_WORD, struct.pack(">H", 0x8005))
            require(
                fw.call(HINT, [8], limit=500) == metadata["pointers"][0],
                "Preview slot accepted",
            )
            report["all_slot_index_cases"] = 16384
        other_types = [*range(8), 9, 10, 65535, 0xFFFFFFFF]
        for typ in other_types:
            require(
                fw.call(HINT, [typ], limit=500)
                == original.call(HINT, [typ], limit=500),
                "Original hint changed",
            )
        report.update(
            native_caption_word_cases=65536, original_hint_comparisons=len(other_types)
        )
    finally:
        fw.card.close()
        original.card.close()
    wires = read_frames(config["fixture"] / "captures/sine-type-7.dtfr")

    def reply_memory(core):
        base = 0x266220 + (core.peek(0x261CA4) & 1) * 4096
        return b"".join(
            struct.pack("<I", core.peek(base + i)) for i in range(0, 0xABC, 4)
        )

    sentinel_cases = parity_cases = 0
    for typ, model in [(t, 0) for t in range(7)] + [(7, m) for m in range(6)]:
        a, b = Dsp(candidate), Dsp(previous)
        for wire in wires:
            w = bytearray(wire)
            w[0x94:0x96] = struct.pack(">H", typ)
            if typ == 7:
                w[0xDE:0xE0] = struct.pack(">H", model * 256)
            for base in (0x266220, 0x267220):
                b.core.poke(base + 0x1A, bytes.fromhex("3ca5"), 2)
            require(
                a.frame(bytes(w)) == b.frame(bytes(w)), "Original/Plaits voice changed"
            )
            for base in (0x266220, 0x267220):
                require(
                    b.core.peek(base + 0x1A, 2) == 0xA53C,
                    "Previous firmware owns reply word",
                )
            ra, rb = reply_memory(a.core), reply_memory(b.core)
            require(
                all(
                    x == y or i in (0, 1, 2, 3, 0x1A, 0x1B)
                    for i, (x, y) in enumerate(zip(ra, rb, strict=True))
                ),
                "Other reply fields changed",
            )
            sentinel_cases += 1
            parity_cases += 1
        del a, b
    report.update(
        reply_sentinel_frames=sentinel_cases,
        full_reply_parity_frames=parity_cases,
        parity_excluded_bytes=[0, 1, 2, 3, 0x1A, 0x1B],
    )
    print(
        f"Exact builds and {parity_cases} full reply/voice comparisons passed",
        flush=True,
    )

    # Exact documented reset-value model already used by the resident runner.
    resets = {0x31089400: 0, 0x31089404: 0, 0x3108B840: 0, 0x310CA2EC: 0, 0x310CA2E8: 0}
    resets.update(
        {
            base + offset: 0
            for base in (0x31004000, 0x31004080, 0x31004100)
            for offset in (0, 0x18, 0x24, 0x30, 0x38)
        }
    )
    resets.update({0x310C92EC: 0, 0x310C92E8: 0})
    resets.update({base + 0x0C: 0x101 for base in (0x31005000, 0x31005100, 0x31005200)})
    resets.update({0x31089800 + 8 * sid: 0 for sid in range(256)})
    resets.update(
        {
            base + offset: 0
            for base in (0x310C9300, 0x310CA300)
            for offset in range(0, 24, 4)
        }
    )
    memory = sharcldr.LoadedMemory.from_stream(candidate)
    require(
        sharcldr.entry_points(sharcldr.parse_blocks(candidate)) == [0x120230, 0x1C1338],
        "Loader entries changed",
    )
    runner = harness._make_runner(memory, "dt2-1.16", 0x1C1338, {})
    runner.state.stack_model = runner.state.bank_model = True
    runner.state.mmrs.update({k: Const(v) for k, v in resets.items()})
    try:
        _dm_read(runner.state, 0x31089424, 4)
    except UnmodeledMMR:
        pass
    else:
        raise ValueError("Unknown-MMR guard lost")
    core = native.NativeCore(native.pack_image(memory), str(LIB))
    core.set_option(native.OPT_BLOCKS, 0)
    core.set_option(native.OPT_RUNTIME_DECODE, 1)
    native.to_native(core, runner.state)
    for option in (
        native.OPT_INSTRUCTION_CLOCK,
        native.OPT_SOFTWARE_INTERRUPTS,
        native.OPT_CORE_TIMER,
        native.OPT_PERIPHERAL_MODEL,
    ):
        core.set_option(option, 1)
    boot_steps = core.run(500_000_000)
    require(not core.halt_reason, f"Fresh startup halted: {core.halt_reason}")
    report["native_startup_instructions"] = boot_steps
    held = bytearray(
        read_frames(ROOT / "out/runs/capicola-panel-08/capicola.dtfr")[-20]
    )
    held[0x22:0x24] = bytes(2)
    held[0x94:0x96] = struct.pack(">H", 8)
    held[0xE0:0xE2] = bytes(2)
    require(core.peek(0x257810 + 8) == 0, "Fresh slot0 is not empty")
    events = []
    for i in range(16):
        reply = core.spi2_exchange(bytes(held))
        require(
            reply is not None and len(reply) == 0xABC,
            "SPI2 did not transmit stock frame extent",
        )
        (out / f"spi-reply-{i:02}.bin").write_bytes(reply)
        core.run(500_000)
        require(not core.halt_reason, f"SPI2 stopped: {core.halt_reason}")
        core.sport_block()
        core.run(2_000_000)
        require(not core.halt_reason, f"SPORT stopped: {core.halt_reason}")
        state = core.peek(layout.address(0x200E4610))
        word = int.from_bytes(reply[0x1A:0x1C], "big")
        events.append(
            dict(
                frame=i,
                state=state,
                reply_word=word,
                spi_tx_start=core.peek(0x3102D204),
                spi_tx_count=core.peek(0x3102D20C),
                spi_tx_xmodify=core.peek(0x3102D210),
            )
        )
    empty_word = 0x8001 if args.live_feedback else 0xD480
    require(
        any(e["reply_word"] == empty_word for e in events),
        "Native EMPTY status never reached actual SPI2 transmission",
    )
    require(
        all(e["reply_word"] in (0, empty_word) for e in events),
        "Unexpected wire word in empty-slot smoke",
    )
    require(
        all(e["state"] == 1 for e in events[2:]),
        "SPI2 input did not select the native empty slot",
    )
    report["native_spi2_events"] = events
    require(source_hashes() == sources, "Source drift")
    report.update(
        status="passed", sources=sources, stock_blob_sha256=sha256(STOCK_BLOB)
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))
