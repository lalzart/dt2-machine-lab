#!/usr/bin/env python3
# ruff: noqa: E402
"""Reparse the combined package and check bounded CPU/DSP startup separately.

CPU has a modeled DSP boot peer; DSP uses documented reset-value peripheral
models. This does not run a coupled system or establish physical timing.
"""

import argparse
import json
import os
import struct
import sys
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
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("package_run", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--elekloader-reference", required=True, type=Path)
args = parser.parse_args()
doctor()
out = args.output.resolve()
package_run = args.package_run.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run directory")
require(package_run.is_relative_to(ROOT / "out/runs"), "Use a local package run")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab import capicola_layout as layout
from lab.runtime import LIB, PROFILE
from lab.upload import REFERENCE_REVISION, digest, verify_candidate

reference = args.elekloader_reference.resolve()
require(git(reference, "rev-parse", "HEAD") == REFERENCE_REVISION, "Unknown codec")
require(not git(reference, "status", "--porcelain"), "Dirty codec checkout")
sys.path.insert(0, str(reference))
import sharc_harness as harness
import sharc_transpile_run as native
import sharcldr
from elekloader.syx import Syx
from emu import checkpoint, snapshot
from sharc_core.values import Const

report = dict(status="running", scope=__doc__, hardware_ready=False)
try:
    sources = source_hashes()
    manifest = json.loads((package_run / "manifest.json").read_text())
    require(manifest["status"] == "target-build-complete", "Incomplete package build")
    require(manifest["source_hashes"] == sources, "Package source drift")
    candidate = package_run / manifest["candidate"]
    require(sha256(candidate) == manifest["container"]["sha256"], "Package changed")
    parsed = Syx(candidate.read_bytes())
    inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
    require(sha256(inputs["syx"]) == PROFILE["stock_syx_sha256"], "Unknown stock SYX")
    stock = Syx(Path(inputs["syx"]).read_bytes())
    images = {3: parsed.section(3), 7: parsed.section(7)}
    for sid, name in ((3, "cpu"), (7, "dsp")):
        require(
            digest(images[sid]) == manifest[name]["sha256"], "Section image changed"
        )
        require(
            images[sid] == (package_run / manifest[name]["path"]).read_bytes(),
            "Package image mismatch",
        )
    report["container"] = verify_candidate(candidate.read_bytes(), stock, images)
    report["candidate_sha256"] = sha256(candidate)
    main = out / "PACKAGE_MAIN_OS.bin"
    main.write_bytes(images[3])
    blob = out / "PACKAGE_BLOB.bin"
    blob.write_bytes(images[7])

    saved = checkpoint.make(
        [400_000_000], prefix=str(out / "boot"), syx=str(candidate), img_path=str(main)
    )
    require(len(saved) == 1, "CPU did not reach the bounded checkpoint")
    machine, extra, _ = snapshot.restore(str(out / "boot400M.snap"))
    writes = (
        manifest["cpu"]["flex"]["writes"]
        + manifest["cpu"]["menu"]["writes"]
        + manifest["cpu"]["reservation"]["writes"]
    )
    for write in writes:
        expected = bytes.fromhex(write["after"])
        require(
            bytes(machine.uc.mem_read(write["address"], len(expected))) == expected,
            "CPU startup changed " + write["label"],
        )
    require(len(extra["tasks"]) == 9, "Unexpected CPU task count")
    report["cpu_startup"] = dict(
        nominal_instructions=400_000_000,
        tasks=len(extra["tasks"]),
        patch_writes_retained=len(writes),
        scope="ColdFire reset through bounded checkpoint, modeled DSP boot peer",
    )
    del machine
    print("CPU checkpoint reached; all combined patch bytes retained", flush=True)
    write_json(out / "report.json", report)

    # Same explicit reset-value model as the preserved reserved-state startup
    # check. No inherited DSP snapshot, instruction skipping or catch-all MMRs.
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
    memory = sharcldr.LoadedMemory.from_stream(images[7])
    require(
        sharcldr.entry_points(sharcldr.parse_blocks(images[7])) == [0x120230, 0x1C1338],
        "Unexpected DSP entry points",
    )
    fingerprints = []
    records = []
    for repetition in range(2):
        runner = harness._make_runner(memory, "dt2-1.16", 0x1C1338, {})
        runner.state.stack_model = runner.state.bank_model = True
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
        require(not core.halt_reason, f"DSP startup halted: {core.halt_reason}")

        def read(address, count, *, core=core):
            return b"".join(
                struct.pack("<I", core.peek(address + i))
                for i in range(0, (count + 3) & ~3, 4)
            )[:count]

        code_bytes = manifest["dsp"]["build"]["code_bytes"]
        data_bytes = manifest["dsp"]["build"]["data_bytes"]
        for address, count in (
            (layout.CODE_BASE, code_bytes),
            (layout.STATE_BASE, data_bytes),
            (layout.address(0x200F0000), 36),
        ):
            require(
                read(address, count) == memory.read(address, count),
                "DSP startup overwrote linked code/constants/selector",
            )
        fingerprint = dict(
            pc=core.pc(),
            code_sha256=digest(read(layout.CODE_BASE, code_bytes)),
            state_sha256=digest(read(layout.STATE_BASE, layout.STATE_BYTES)),
        )
        fingerprints.append(fingerprint)
        records.append(dict(repetition=repetition, instructions=steps, **fingerprint))
        print(
            f"DSP startup repetition {repetition + 1} retains linked code and constants",
            flush=True,
        )
        del core
    require(fingerprints[0] == fingerprints[1], "DSP startup repetition differs")
    require(source_hashes() == sources, "Sources changed during validation")
    report.update(
        status="passed",
        source_fresh=True,
        source_hashes=sources,
        dsp_startup=records,
        dsp_repeat_exact=True,
    )
except Exception as exc:
    report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    raise
finally:
    write_json(out / "report.json", report)
