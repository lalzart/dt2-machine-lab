#!/usr/bin/env python3
"""Matched stock/Capicola STRETCH instruction profiles; no CPU/hardware timing."""

# ruff: noqa: E402, I001
import argparse
import array
import hashlib
import math
import os
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, write_json

config = settings()
if Path(sys.executable).absolute() != config["python"].absolute():
    os.execv(
        str(config["python"]), [str(config["python"]), "-B", __file__, *sys.argv[1:]]
    )
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--blocks", type=int, default=128)
CASES = {
    "idle": (0, 0, False, False, False),
    "preparation": (1, 0, False, False, False),
    "pending-trigger": (1, 3, True, False, False),
    "one-loop": (1, 192, True, False, False),
    "one-fast": (1, 192, True, True, False),
    "four-loop": (4, 192, True, False, False),
    "sixteen-loop": (16, 192, True, False, False),
    "sixteen-mixed": (16, 192, True, False, True),
}
parser.add_argument("--case", choices=CASES, action="append")
args = parser.parse_args()
require(8 <= args.blocks <= 256, "Use 8..256 measured blocks")
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
manifest = {
    **doctor(),
    "status": "running",
    "started_utc": datetime.now(UTC).isoformat(),
    "run": out.name,
    "command": {
        "command": "capicola-stretch-profile",
        "blocks": args.blocks,
        "cases": args.case or list(CASES),
    },
}
write_json(out / "manifest.json", manifest)
# Runtime configures the pinned dependency's module path before these imports.
from lab.runtime import PROFILE, STOCK_BLOB

import sharc_trace as st
import sharcldr
from sharc_transpile_run import OPT_STOP_PC

from lab.capicola_layout import STATE_BASE, address
from lab.capicola_memory import RESERVE_BYTES, RESERVED_BASE
from lab.dsp import header
from lab.formats import read_frames
from lab.metrics import distribution
from lab.pattern_dsp import PatternDsp, check_fext
from lab.plaits import build_blob
from lab.resource_workloads import write_frames
from lab.stretch_resources import controls, measured_frames, pcm_extent

POOL = 0x8422B9C8
HANDOFF, BANK, LANES = [address(a) for a in (0x200E4000, 0x200E4100, 0x200E4800)]
CAPTURE = ROOT / "out/runs/capicola-panel-08/capicola.dtfr"
LOAD = ROOT / "out/runs/capicola-panel-05/flexbus.raw"
EXPECTED = {
    CAPTURE: "3e6a3f0f319ca2c27087a77fb09d73f0b88922c2eabec0bb42651de8a1596290",
    LOAD: "85f122f352abf80e5ae7fd11e9d5f05e5cc8b3e0526cd694d4fe420b6707e844",
}
# Freeze DSP/compiler/capture inputs; unrelated CPU/UI work can continue.
prefixes = ("machines/", "profiles/")
modules = (
    "dsp",
    "plaits",
    "plaits_controls",
    "plaits_integration",
    "capicola_layout",
    "capicola_automatic",
    "capicola_controls",
    "capicola_stretch",
    "capicola_memory",
    "pattern_dsp",
    "pattern_native",
    "runtime",
    "project",
    "metrics",
    "formats",
    "resource_workloads",
    "stretch_resources",
)
source_names = {f"lab/{name}.py" for name in modules} | {
    "scripts/profile-capicola-stretch.py"
}
frozen = {
    p: h
    for p, h in manifest["source_hashes"].items()
    if p.startswith(prefixes) or p in source_names
}
report = {
    "status": "running",
    "firmware": PROFILE["firmware"],
    "scope": "Matched adapted wire and captured LP0 loading in prepared native DSP replay; whole block work including Capicola preparation and diagnostic copy; hardware CPU/DSP percentages unmeasured",
    "cases": [],
    "inputs": {str(p): h for p, h in EXPECTED.items()},
    "sources": frozen,
}


def load_pcm(engine, raw):
    core = engine.core
    regs = [f"{k}{i}" for k in ("R", "I", "M", "L") for i in range(16)]
    saved = {r: core.get_reg(st.UREG_CODES[r]) for r in regs}
    core.set_option(OPT_STOP_PC, 0x1C834A)
    for pos in range(0, len(raw), 4100):
        core.poke(0x268240, raw[pos : pos + 4100], 1)
        values = dict(
            M5=0,
            M6=1,
            M7=-1,
            M14=1,
            I6=0x200D7F00,
            I7=0x200D7EF8,
            R4=0,
            R8=4,
            R12=0x268220,
        )
        values.update({f"L{i}": 0 for i in range(16)})
        for reg, value in values.items():
            core.set_reg(st.UREG_CODES[reg], st.Const(value))
        core.poke(0x200D7EFC, bytes(32), 1)
        core.fresh_call(0x1C7E1F)
        core.run(50000)
        require(core.pc() == 0x1C834A, "LP0 callback failed")
    core.set_option(OPT_STOP_PC, 0)
    for reg, value in saved.items():
        core.set_reg(st.UREG_CODES[reg], value)


def arena(blob, extent, bank):
    split = sharcldr.parse_blocks(blob)[-1]["offset"]
    extra = header(POOL - 1024, extent) + bytes(extent)
    if bank:
        extra += header(RESERVED_BASE, STATE_BASE - RESERVED_BASE) + bytes(
            STATE_BASE - RESERVED_BASE
        )
    return blob[:split] + extra + blob[split:]


def floats(engine, pointer):
    require(
        0x80000000 <= pointer <= 0xA0000000 - 128 and pointer % 4 == 0,
        "Destination bounds",
    )
    return struct.unpack(
        "<32f",
        struct.pack("<32I", *[engine.core.peek(pointer + i * 4) for i in range(32)]),
    )


try:
    for path, digest in EXPECTED.items():
        require(sha256(path) == digest, "Changed input: " + str(path))
    raw = LOAD.read_bytes()
    extent = pcm_extent(raw)
    check_fext()
    candidate = build_blob(
        True,
        family="capicola-stretch",
        layout="reserved-state",
        output=out / "candidate",
    )
    require(
        hashlib.sha256(candidate).hexdigest()
        == "2e40f16aca0243cf44732703be0e18817669ddb2ae5653c945de352ca4b3334a",
        "STRETCH R1 image drift",
    )
    template = next(
        w
        for w in read_frames(CAPTURE)
        if int.from_bytes(w[0x94:0x96], "big") == 8
        and int.from_bytes(w[0x22:0x24], "big") & 1
    )
    for name in args.case or CASES:
        tracks, warmup, trigger, fast, mixed = CASES[name]
        wire = controls(template, tracks, fast=fast, mixed=mixed)
        count = 192 if name in ("preparation", "pending-trigger") else args.blocks
        replay = measured_frames(wire, tracks, count, trigger=trigger)
        capture = out / (name + "-replay.dtfr")
        write_frames(capture, replay)
        setup = {
            "sample_load_sha256": sha256(LOAD),
            "allocation_extent_bytes": extent,
            "warmup_blocks": warmup,
            "warmup_wire_sha256": hashlib.sha256(wire).hexdigest(),
            "method": "stock SHFP state; captured LP0 callback replay; zero-backed sample extent; candidate bank backing without zeroing linked constants",
        }
        results = {}
        for variant, blob in (
            ("stock", STOCK_BLOB.read_bytes()),
            ("capicola-stretch-r1", candidate),
        ):
            actual_blob = arena(blob, extent, variant != "stock")
            engine = PatternDsp(actual_blob)
            load_pcm(engine, raw)
            for _ in range(warmup):
                engine.frame(wire)
            if variant != "stock" and warmup == 192:
                require(
                    engine.core.peek(HANDOFF + 8) == 1, "Bank not ready before playback"
                )
            engine.block_instructions.clear()
            engine.block_host_us.clear()
            destination_audio = array.array("f")
            post_block_audio = array.array("f")
            backends = []
            ready = []
            active = []
            for frame in replay:
                engine.frame(frame)
                if variant != "stock":
                    ready.append(engine.core.peek(HANDOFF + 8))
                    backends.append(
                        sum(
                            engine.core.peek(LANES + i * 132 + 120) == 1
                            for i in range(32)
                        )
                    )
                active.append(
                    sum(
                        bool(engine.core.peek(0x2412CC + i * 0x1D8 + 0x1B8, 1))
                        for i in range(32)
                    )
                )
                for lane in range(tracks * 2):
                    pointer = engine.core.peek(0x24EF2C + lane * 4)
                    post_block_audio.extend(floats(engine, pointer))
                    if (
                        variant != "stock"
                        and engine.core.peek(LANES + lane * 132 + 120) == 1
                    ):
                        require(
                            engine.core.peek(LANES + lane * 132 + 128) == pointer,
                            "Custom destination pointer mismatch",
                        )
                        destination_audio.extend(
                            floats(engine, address(0x200E6000) + lane * 128)
                        )
            require(
                all(map(math.isfinite, post_block_audio))
                and all(map(math.isfinite, destination_audio)),
                "Nonfinite DSP destination",
            )
            if variant != "stock" and warmup == 192:
                require(
                    min(backends[1:]) == tracks * 2,
                    "Playback fell back or lost readers",
                )
                require(
                    destination_audio and max(map(abs, destination_audio)) > 1e-7,
                    "Silent custom renderer",
                )
            if name == "pending-trigger" and variant != "stock":
                require(max(backends) == 0, "Unready note taken over mid-play")
            scope = {
                "boundary": "Whole emulated DSP block handler; excludes DMA callback and Python output tap",
                "instruction_unit": "emulated retired instructions, not physical clock cycles",
                "instructions_per_block": distribution(engine.block_instructions),
                "host_us_per_block": distribution(engine.block_host_us),
                "target_cpu_load_percent": None,
                "target_dsp_load_percent": None,
            }
            label = name + "-" + variant
            record = {
                "frames": count,
                "capture_sha256": sha256(capture),
                "capture": str(capture),
                "preroll_trigger_frame": None,
                "sample_rates": {"source": 96000, "captured_stereo": 48000},
                "dsp_blob_sha256": hashlib.sha256(blob).hexdigest(),
                "replay_blob_sha256": hashlib.sha256(actual_blob).hexdigest(),
                "replay_setup": setup,
                "profile": scope,
                "native_library_sha256": sha256(engine.library),
                "cpu_stock": False,
                "workload": "stretch-" + name,
                "installed_variant": variant,
                "origin": str(CAPTURE),
                "max_active_voice_lanes": max(active),
                "fext_fallbacks": dict(engine.fallbacks),
                "ready_after_measured_block": next(
                    (i + 1 for i, v in enumerate(ready) if v == 1), None
                ),
                "minimum_custom_backends": min(backends) if backends else None,
                "maximum_custom_backends": max(backends) if backends else None,
                "direct_custom_destination_samples": len(destination_audio),
                "direct_custom_destination_peak": max(
                    map(abs, destination_audio), default=None
                ),
                "memory_bank": {
                    "keys": engine.core.peek(BANK + 16),
                    "capacity": engine.core.peek(BANK + 12),
                    "frames": engine.core.peek(BANK + 20),
                    "allocated_array_bytes": engine.core.peek(BANK + 12) * 12,
                    "shared_readers_bytes": 32 * 132,
                    "total_reserved_bytes": RESERVE_BYTES,
                }
                if variant != "stock" and ready[-1] == 1
                else None,
                "output_scope": "Custom PCM copied at actual STRETCH destination before downstream reuse; stock post-block buffer used only for fallback parity, not renderer-quality comparison",
            }
            write_json(out / (label + ".json"), record)
            write_json(
                out / (label + "-profile.json"),
                {
                    "scope": scope,
                    "instructions": engine.block_instructions,
                    "host_us": engine.block_host_us,
                },
            )
            if destination_audio:
                (out / (label + "-destinations.f32")).write_bytes(
                    destination_audio.tobytes()
                )
            results[variant] = {
                "record": record,
                "instructions": engine.block_instructions,
                "post_audio": post_block_audio.tobytes(),
            }
            print(label, scope["instructions_per_block"], flush=True)
        stock = results["stock"]
        cap = results["capicola-stretch-r1"]
        if name == "pending-trigger":
            require(
                stock["post_audio"] == cap["post_audio"],
                "Stock fallback post-block destination drift",
            )
        base = stock["record"]["profile"]["instructions_per_block"]
        cost = cap["record"]["profile"]["instructions_per_block"]
        row = {
            "name": name,
            "tracks": tracks,
            "blocks": count,
            "stock": base,
            "capicola": cost,
            "mean_change_percent": 100 * (cost["mean"] / base["mean"] - 1),
            "memory_bank": cap["record"]["memory_bank"],
            "ready_after_measured_block": cap["record"]["ready_after_measured_block"],
        }
        if name == "preparation":
            end = cap["record"]["ready_after_measured_block"]
            require(end is not None, "Preparation never ready")
            row["preparation_window"] = {
                "blocks_to_ready": end,
                "modeled_audio_seconds": end * 32 / 48000,
                "additional_instructions_to_ready": sum(cap["instructions"][:end])
                - sum(stock["instructions"][:end]),
                "stock": distribution(stock["instructions"][:end]),
                "capicola": distribution(cap["instructions"][:end]),
            }
        report["cases"].append(row)
        write_json(out / "report.json", report)
    require(
        all(sha256(ROOT / p) == h for p, h in frozen.items()),
        "DSP profiling source drift",
    )
    report["status"] = "passed"
    manifest.update(
        status="passed",
        finished_utc=datetime.now(UTC).isoformat(),
        result={"ok": True, "scope": report["scope"]},
    )
except BaseException as exc:
    report.update(status="failed", error=str(exc))
    manifest.update(
        status="failed", error=str(exc), finished_utc=datetime.now(UTC).isoformat()
    )
    raise
finally:
    write_json(out / "report.json", report)
    write_json(out / "manifest.json", manifest)
print("PASS:", out, flush=True)
