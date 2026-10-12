# ruff: noqa: E402, I001
"""Repeat a bounded OS 1.16 DSP application-entry diagnostic from loader bytes.

No prepared DSP snapshot, instruction skipping, CPU peer or hardware access.
This is a startup diagnostic, not a firmware release gate or full chip model.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run", type=Path)
parser.add_argument("--candidate-blob", required=True, type=Path)
parser.add_argument("--steps", type=int, default=500_000_000)
parser.add_argument("--peripheral-smoke", action="store_true")
args = parser.parse_args()
require(1 <= args.steps <= 500_000_000, "Instruction bound must be 1..500000000")
doctor()
run = args.run.resolve()
require(run.is_relative_to(ROOT / "out/runs"), "Expected ignored lab run directory")
require(not run.exists(), "Refusing to overwrite evidence")
require(
    sha256(args.candidate_blob)
    == "98db0c43d987eadbbc9f528660196b97c58d24a9785206a7bdb8f6882c3822b6",
    "Unknown candidate DSP image",
)
run.mkdir(parents=True)
os.environ["DT2_LAB_RUN_DIR"] = str(run.relative_to(ROOT / "out/runs"))
from lab.runtime import LIB, STOCK_BLOB
from lab.formats import read_frames
import sharc_harness as harness
import sharc_transpile_run as native
import sharcldr
from sharc_core.memory import UnmodeledMMR, _dm_read
from sharc_core.values import Const

# ADI ADSP-2156x HWR rev 1.1: figures 6-7, 6-13, 6-28, 32-7;
# appendix table A-73 (all twelve PCG register resets). See reproduction notes.
# PORT FER/DIR/INEN/MUX/POL resets: HWR appendix A-80..A-82.
# PINT_ASSIGN reset: HWR appendix A-74..A-76.
# DAI0/1 global SPORT enable and interrupt resets: HWR appendix A-15/A-16.
# Only initial values: existing peripheral semantics remain incomplete.
RESETS = {0x31089400: 0, 0x31089404: 0, 0x3108B840: 0, 0x310CA2EC: 0, 0x310CA2E8: 0}
RESETS.update(
    {
        base + offset: 0
        for base in (0x31004000, 0x31004080, 0x31004100)
        for offset in (0, 0x18, 0x24, 0x30, 0x38)
    }
)
RESETS.update({0x310C92EC: 0, 0x310C92E8: 0})
RESETS.update({base + 0x0C: 0x101 for base in (0x31005000, 0x31005100, 0x31005200)})
RESETS.update({0x31089800 + 8 * sid: 0 for sid in range(256)})
RESETS.update(
    {
        base + offset: 0
        for base in (0x310C9300, 0x310CA300)
        for offset in range(0, 24, 4)
    }
)
require(
    sha256(STOCK_BLOB)
    == "0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2",
    "Unknown stock DSP image",
)
report = {
    "hardware_ready": False,
    "script_sha256": sha256(Path(__file__)),
    "native_library_sha256": sha256(LIB),
    "scope": "Loaded application entry; reset-value diagnostic, no CPU peer",
    "stack_model": True,
    "bank_model": True,
    "instruction_limit": args.steps,
    "reset_values": {hex(k): v for k, v in RESETS.items()},
    "arms": {},
}
frames = []
if args.peripheral_smoke:
    capture = config["fixture"] / "captures/type-6.dtfr"
    require(
        sha256(capture)
        == "2e59fb92f95ef27b571a1335f125d893ce5e402578c4f5cd21d701d8c4eb13c7",
        "Unknown stock control capture",
    )
    frames = read_frames(capture)[:16]
    report["capture_sha256"] = sha256(capture)
    report["peripheral_scope"] = (
        "Captured stock frames and silent input via native SPI2/SPORT4 DMA; not coupled CPU boot"
    )
for label, path in (("stock", STOCK_BLOB), ("plaits", args.candidate_blob)):
    fingerprints = []
    event_repeats = []
    for repeat in range(2):
        raw = path.read_bytes()
        memory = sharcldr.LoadedMemory.from_stream(raw)
        entries = sharcldr.entry_points(sharcldr.parse_blocks(raw))
        require(entries == [0x120230, 0x1C1338], "Unexpected loader entry points")
        runner = harness._make_runner(memory, "dt2-1.16", entries[-1], {})
        # Required by native interrupt entry and firmware context switches.
        runner.state.stack_model = True
        runner.state.bank_model = True
        # A negative control proves we do not zero all missing MMR reads.
        runner.state.mmrs.update({k: Const(v) for k, v in RESETS.items()})
        try:
            _dm_read(runner.state, 0x31089424, 4)
        except UnmodeledMMR:
            pass
        else:
            raise RuntimeError("Unknown-MMR guard was lost")
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
        steps = core.run(args.steps)
        state = core.export_state()
        fingerprint = hashlib.sha256(
            json.dumps(state, sort_keys=True).encode()
        ).hexdigest()
        fingerprints.append(fingerprint)
        detail = None
        if core.halt_reason:
            diagnostic = native._runner_for(
                native.to_python(core, runner.state), memory
            )
            try:
                diagnostic.step()
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}"
        result = {
            "blob_sha256": sha256(path),
            "instructions": steps,
            "pc": hex(core.pc()),
            "halt": core.halt_reason,
            "python_diagnostic": detail,
            "state_sha256": fingerprint,
            "status": "stopped" if core.halt_reason else "instruction-bound",
        }
        if frames and not core.halt_reason:
            events = []
            for frame in frames:
                event = {}
                events.append(event)
                try:
                    reply = core.spi2_exchange(frame)
                    event["reply_bytes"] = len(reply)
                    event["reply_sha256"] = hashlib.sha256(reply).hexdigest()
                    event["control_instructions"] = core.run(2_000_000)
                    require(not core.halt_reason, core.halt_reason)
                    pcm = core.sport_block()
                    event["sport_bytes"] = None if pcm is None else len(pcm)
                    event["sport_sha256"] = (
                        None if pcm is None else hashlib.sha256(pcm).hexdigest()
                    )
                    event["audio_instructions"] = core.run(2_000_000)
                    require(not core.halt_reason, core.halt_reason)
                except Exception as exc:
                    event["error"] = f"{type(exc).__name__}: {exc}"
                    event["pc"] = hex(core.pc())
                    break
            result["peripheral_events"] = events
            event_repeats.append(events)
        name = f"{label}-{repeat + 1}"
        write_json(run / f"{name}-state.json", state)
        report["arms"][name] = result
        write_json(run / "report.json", report)
        print(name, json.dumps(result), flush=True)
        del core
    require(fingerprints[0] == fingerprints[1], f"{label} startup was not repeatable")
    if event_repeats:
        require(
            len(event_repeats) == 2 and event_repeats[0] == event_repeats[1],
            f"{label} peripheral diagnostic was not repeatable",
        )
report["exact_repeat"] = True
write_json(run / "report.json", report)
