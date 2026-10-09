#!/usr/bin/env python3
"""Validate reserved working-memory builds, stock parity and fresh DSP startup."""

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
from lab.project import doctor, require, settings, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--selection", action="store_true")
args = p.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs/<unique>")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
doctor()
from lab import capicola_layout as layout
from lab.dsp import Dsp, header
from lab.formats import read_frames
from lab.plaits import build_blob
from lab.runtime import LIB
import sharc_harness as harness
import sharc_transpile_run as native
import sharcldr
from sharc_core.values import Const

report = dict(
    status="running",
    scope="Owned working-data layout and bounded native startup; L2 code ownership and hardware timing remain unverified",
)
try:
    sources = source_hashes()
    family = "capicola-selection" if args.selection else "capicola-controls"
    candidate = build_blob(
        True,
        family=family,
        layout="reserved-state",
        output=out / "candidate",
    )
    repeat = build_blob(
        True, family=family, layout="reserved-state", output=out / "repeat"
    )
    require(candidate == repeat, "Relocated build is not exact repeat")
    old = build_blob(True, family="capicola-controls", output=out / "legacy")
    require(
        hashlib.sha256(old).hexdigest()
        == "ce51ec4ced24b1617ae35337c4bf7cdddf22a2d288f320d74fc3d636206f2c5f",
        "Legacy controls build changed",
    )
    if args.selection:
        previous = build_blob(
            True,
            family="capicola-controls",
            layout="reserved-state",
            output=out / "previous-reserved",
        )
        require(
            hashlib.sha256(previous).hexdigest()
            == "dcf9c499f09abecf0cad088d9bdd1e3073ef931fe90a3bd86b7df8649344643f",
            "Previous reserved-state image changed",
        )
        report["previous_reserved_exact"] = True
    plan = json.loads((out / "candidate/memory-layout.json").read_text())
    report.update(
        blob_sha256=hashlib.sha256(candidate).hexdigest(),
        exact_repeat=True,
        legacy_exact=True,
        layout=plan,
    )
    poison = bytes([0xA5]) * layout.STATE_BYTES
    split = sharcldr.parse_blocks(candidate)[-1]["offset"]
    poisoned = (
        candidate[:split]
        + header(layout.OLD_BASE, len(poison))
        + poison
        + candidate[split:]
    )

    def peek(core, address, count):
        return b"".join(
            struct.pack("<I", core.peek(address + i)) for i in range(0, count, 4)
        )

    wires = read_frames(config["fixture"] / "captures/sine-type-7.dtfr")
    cases = 0
    for typ, model in [(0, 0), (6, 0)] + [(7, m) for m in range(6)]:
        a, b = Dsp(poisoned), Dsp(old)
        for wire in wires:
            w = bytearray(wire)
            w[0x94:0x96] = struct.pack(">H", typ)
            if typ == 7:
                w[0xDE:0xE0] = struct.pack(">H", model * 256)
            require(
                a.frame(bytes(w)) == b.frame(bytes(w)),
                "Stock/Plaits output changed after relocation",
            )
            cases += 1
        require(
            peek(a.core, layout.OLD_BASE, len(poison)) == poison,
            "Stock/Plaits touched former working memory",
        )
        del a, b
    report["stock_plaits_frame_comparisons"] = cases
    print(f"Exact builds and {cases} stock/Plaits comparisons passed", flush=True)

    # Same documented reset-value model as probe-dsp-startup.py. It does not
    # replace missing MMR reads generally, skip instructions or import a snapshot.
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
    reports = []
    fingerprints = []
    for repetition in range(2):
        memory = sharcldr.LoadedMemory.from_stream(poisoned)
        require(
            sharcldr.entry_points(sharcldr.parse_blocks(poisoned))
            == [0x120230, 0x1C1338],
            "Unexpected loader entries",
        )
        runner = harness._make_runner(memory, "dt2-1.16", 0x1C1338, {})
        runner.state.stack_model = True
        runner.state.bank_model = True
        runner.state.mmrs.update({k: Const(v) for k, v in resets.items()})
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
        steps = core.run(500_000_000)
        require(not core.halt_reason, f"Fresh startup halted: {core.halt_reason}")
        require(
            peek(core, layout.OLD_BASE, len(poison)) == poison,
            "Startup wrote the former working region",
        )
        expected_code = memory.read(layout.CODE_BASE, plan["instruction_code"]["bytes"])
        padded = (len(expected_code) + 3) & ~3
        require(
            peek(core, layout.CODE_BASE, padded)[: len(expected_code)] == expected_code,
            "Startup overwrote custom instruction code",
        )
        build = json.loads((out / "candidate/build.json").read_text())
        require(
            peek(core, layout.STATE_BASE, build["data_bytes"])
            == memory.read(layout.STATE_BASE, build["data_bytes"]),
            "Startup overwrote constants",
        )
        selector = layout.address(0x200F0000)
        require(
            peek(core, selector, 36) == memory.read(selector, 36),
            "Startup overwrote selector",
        )
        # Actual RTOS heap block headers after application startup. The stock
        # task-creation allocator uses this L1 region, not the L2 code interval.
        heap_start, heap_end = 0x2CA598, 0x2D6D90
        require(core.peek(0x2D6DA4) == heap_end, "Unexpected native RTOS heap endpoint")
        cursor = heap_start
        blocks = []
        while cursor < heap_end and len(blocks) < 1024:
            size = core.peek(cursor + 4)
            n = size & 0x7FFFFFFF
            require(
                n >= 8 and n % 8 == 0 and cursor + n <= heap_end,
                "Invalid RTOS heap extent",
            )
            blocks.append(
                dict(address=cursor, bytes=n, allocated=bool(size & 0x80000000))
            )
            cursor += n
        require(cursor == heap_end, "RTOS blocks do not cover the declared heap")
        state = core.export_state()
        digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
        fingerprints.append(digest)
        result = dict(
            instructions=steps,
            pc=hex(core.pc()),
            state_sha256=digest,
            heap_start=heap_start,
            heap_end=heap_end,
            heap_blocks=blocks,
            retired_l2_bytes_unchanged=len(poison),
            code_unchanged=True,
            constants_unchanged=True,
            selector_unchanged=True,
        )
        reports.append(result)
        write_json(out / f"startup-{repetition + 1}.json", result)
        print(
            f"Fresh startup {repetition + 1} passed, {len(blocks)} RTOS heap blocks in L1",
            flush=True,
        )
        del core
    require(fingerprints[0] == fingerprints[1], "Fresh startup state did not repeat")
    require(source_hashes() == sources, "Sources changed during validation")
    report.update(
        status="passed", startup=reports, startup_exact_repeat=True, sources=sources
    )
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "report.json", report)
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("sources", "layout", "startup")
            },
            indent=2,
        )
    )
