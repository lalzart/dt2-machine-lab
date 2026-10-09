#!/usr/bin/env python3
"""Capture bounded pad workloads from verified stock OS 1.16; replay DSP variants."""

# ruff: noqa: E402
import argparse
import array
import hashlib
import json
import math
import os
import sys
import time
import zlib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, write_json
from lab.resource_workloads import (
    fixed_replay,
    track_one_clip,
    trigger_mask,
    write_frames,
)

config = settings()
if Path(sys.executable).absolute() != config["python"].absolute():
    os.execv(
        str(config["python"]), [str(config["python"]), "-B", __file__, *sys.argv[1:]]
    )
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--capture-only", action="store_true")
parser.add_argument(
    "--extended-stock",
    action="store_true",
    help="also select ONESHOT on track 3 and GRID on track 1",
)
parser.add_argument(
    "--custom-engines",
    action="store_true",
    help="include installed Plaits and captured SINE/Plaits FM workloads",
)
parser.add_argument("--frames", type=int, default=192)
args = parser.parse_args()
require(128 <= args.frames <= 512, "Replay must contain 128..512 blocks")
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()
# isort: off
from lab.runtime import FIXTURE, PROFILE, REPO, STOCK_BLOB, STOCK_MAIN
from emu import gui, panel
from emu.harness import PAGE
from emu.snapshot import _load_blob
# isort: on

from lab.flex_heap import inspect_heap
from lab.pattern_clock import Recorder, install

original = ROOT.parent / "Digitect firmware research project"
base = original / "work/digikit"
snapshot = base / "snapshots/dt2-1.16-auto/be080a1acd14/ready.snap"
card = base / "out/plusdrive/auto/be080a1acd14/dt2.img"
syx = (
    original
    / "outputs/elektron-firmware-research/firmware/originals/Digitakt_II_OS1.16.syx"
)
require(
    sha256(snapshot)
    == "3852f53c7e45c358702ed9cefb8bb3ef2af194f4f501e70b6cfbcba333494867",
    "Unknown stock ready checkpoint",
)
require(sha256(syx) == PROFILE["stock_syx_sha256"], "Unknown firmware package")
saved = _load_blob(snapshot)
require(
    saved["manifest"]["main_sha256"] == PROFILE["stock_main_sha256"],
    "Checkpoint was not built from stock MAIN",
)
# Static MAIN prefix must match; later initialized data legitimately changes at boot.
start, end = 0x40000400, 0x4029E9C0
pages = {
    a: zlib.decompress(v)
    for a, v in saved["pages"].items()
    if 0x40000000 <= a < 0x40300000
}
memory = b"".join(
    pages.get(a, bytes(PAGE)) for a in range(0x40000000, 0x40300000, PAGE)
)
require(
    memory[start - 0x40000000 : end - 0x40000000]
    == STOCK_MAIN.read_bytes()[: end - start],
    "Stock checkpoint static MAIN differs",
)
del saved, pages, memory
card_hash = gui.check_card_image_sidecar(str(snapshot), str(card))
require(card_hash, "Missing stock card provenance")
os.chdir(REPO)
os.environ.update(
    DT2_SYX=str(syx),
    DT2_SECTIONS=str(FIXTURE / "sections"),
    DT2_MAIN_IMG=str(STOCK_MAIN),
)
recorder = Recorder()
runtime = install(gui, recorder)
emu = gui.Emulator(
    str(snapshot),
    syx=str(syx),
    card_image=str(card),
    live=recorder,
    fast=False,
    realtime=False,
    panel_dwell=4,
)
runtime["worker"] = emu
emu.pause.set()
emu.start()
deadline = time.monotonic() + 600
report = {
    "status": "running",
    "firmware": PROFILE["firmware"],
    "main_sha256": PROFILE["stock_main_sha256"],
    "stock_blob_sha256": PROFILE["stock_blob_sha256"],
    "cpu_snapshot": str(snapshot),
    "cpu_snapshot_sha256": sha256(snapshot),
    "card_sha256": card_hash,
    "scope": "Stock MAIN checkpoint, original stock DSP for baseline; modeled SSI 96000 Hz and zero DSP replies; bounded pad auditions, not physical CPU/DSP load",
    "gestures": [],
    "cpu_stages": [],
    "workloads": [],
}
manifest = {
    **provenance,
    "status": "running",
    "started_utc": datetime.now(UTC).isoformat(),
    "command": {"command": "resource-baseline", "frames": args.frames},
    "run": out.name,
}
write_json(out / "manifest.json", manifest)
source_paths = [
    Path(__file__),
    ROOT / "lab/resource_workloads.py",
    ROOT / "lab/dsp.py",
    ROOT / "lab/pattern_clock.py",
    ROOT / "lab/flex_heap.py",
    ROOT / "lab/metrics.py",
    ROOT / "lab/plaits.py",
    ROOT / "lab/pattern_dsp.py",
    ROOT / "lab/pattern_native.py",
    ROOT / "lab/plaits_controls.py",
    ROOT / "lab/plaits_integration.py",
    ROOT / "lab/capicola_layout.py",
]
frozen_sources = {str(p): sha256(p) for p in source_paths}
for folder in [ROOT / "machines/sine"] + [
    ROOT / ("machines/plaits-" + family)
    for family in ("va", "trio", "bank", "controls", "integration")
]:
    for source in folder.rglob("*"):
        if source.is_file():
            frozen_sources[str(source)] = sha256(source)
report["source_sha256"] = frozen_sources


def advance(n):
    target = emu.stats["instrs"] + n + gui.BUDGET
    runtime["pause_after"] = target
    emu.pause.clear()
    while emu.stats["status"] != "paused" or emu.stats["instrs"] < target:
        require(
            not emu.error and emu.is_alive() and not emu.stats["terminal"],
            f"CPU stopped: {emu.error}",
        )
        require(time.monotonic() < deadline, "600-second capture bound exceeded")
        time.sleep(0.005)
    require(not emu._faulted_pages, "CPU touched a fault page")


def buttons(names, kind):
    for name in names:
        hits = [k for k, value in emu.button_names.items() if value.upper() == name]
        require(len(hits) == 1, f"Unknown panel control {name}")
        emu.inbox.append((kind, hits[0], None))
    report["gestures"].append([emu.stats["instrs"], kind, names])
    advance(2_000_000)


def tap(name):
    buttons([name], "press")
    buttons([name], "release")


def chord(modifier, name):
    buttons([modifier], "press")
    tap(name)
    buttons([modifier], "release")


def select_machine(track, index):
    chord("TRK", f"TRIG {track}")
    chord("FUNC", "SRC")
    for _ in range(8):
        tap("UP")
    for _ in range(index):
        tap("DOWN")
    tap("YES")
    tap("YES")


def workload(name, tracks):
    start = len(recorder.frames)
    before = emu.stats["instrs"]
    if tracks:
        names = [f"TRIG {n}" for n in tracks]
        buttons(names, "press")
        buttons(names, "release")
    advance(10_000_000)
    raw = recorder.frames[start:]
    ticks = recorder.ticks[start:]
    require(
        raw
        and all(
            (b - a) & 0xFFFFFFFF == 32
            for a, b in zip(ticks[:-1], ticks[1:], strict=True)
        ),
        "Capture ticks discontinuous",
    )
    mask = 0
    for f in raw:
        mask |= int.from_bytes(f[0x22:0x24], "big")
    expected = sum(1 << (n - 1) for n in tracks)
    require(mask == expected, f"Pad trigger mask {mask:#x} != {expected:#x}")
    require(
        all(raw[-1][o : o + 2] == b"\0\0" for o in (0x22, 0x24, 0x26, 0x28)),
        "Tail has one-shot event",
    )
    path = out / (name + ".dtfr")
    write_frames(path, raw)
    heap = inspect_heap(lambda a, n: bytes(emu._uc.mem_read(a, n))).report()
    row = {
        "name": name,
        "tracks": tracks,
        "capture": str(path),
        "capture_sha256": sha256(path),
        "frames": len(raw),
        "ticks": ticks,
        "trigger_mask": mask,
        "machine_types": [
            int.from_bytes(raw[-1][0x94 + 2 * t : 0x96 + 2 * t], "big")
            for t in range(16)
        ],
        "cpu_instructions_in_fixed_window": emu.stats["instrs"] - before,
        "heap": heap,
    }
    report["cpu_stages"].append(row)
    if emu._panel_latch:
        panel.write_png(emu._panel_latch, str(out / (name + ".png")))
    print(
        name,
        "captured",
        len(raw),
        "frames, triggers",
        hex(mask),
        "free heap",
        heap["free_bytes"],
        flush=True,
    )
    return raw, row


try:
    require(
        emu.ready.wait(60) and not emu.error, f"Stock CPU startup failed: {emu.error}"
    )
    while len(recorder.frames) < 32 and emu.stats["instrs"] < 220_000_000:
        advance(10_000_000)
    require(len(recorder.frames) >= 32, "Control-link warmup stalled")
    for _ in range(2):
        buttons(["STOP"], "press")
        buttons(["STOP"], "release")
    captures = []
    for name, tracks in [
        ("idle", []),
        ("one-pad", [1]),
        ("two-pads", [1, 2]),
        ("four-pads", [1, 2, 3, 4]),
    ]:
        captures.append((name, *workload(name, tracks)))
    if args.extended_stock:
        select_machine(3, 0)
        raw, row = workload("four-pads-oneshot", [1, 2, 3, 4])
        require(
            row["machine_types"][:4] == [0, 0, 0, 0],
            "Four ONESHOT selections not confirmed",
        )
        captures.append(("four-pads-oneshot", raw, row))
        select_machine(1, 5)
        raw, row = workload("one-pad-grid", [1])
        require(row["machine_types"][0] == 4, "GRID type 4 not confirmed")
        captures.append(("one-pad-grid", raw, row))
    report["faulted_pages"] = sorted(emu._faulted_pages)
    report["worker_error"] = emu.error
    report["cpu_instructions"] = emu.stats["instrs"]
except BaseException as exc:
    report.update(status="failed", error=str(exc))
    manifest.update(status="failed", error=str(exc))
    raise
finally:
    emu.stop_flag.set()
    emu.pause.clear()
    emu.join(timeout=30)
    report["worker_stopped"] = not emu.is_alive()
    write_json(out / "stock-capture.json", report)
    write_json(out / "manifest.json", manifest)

try:
    if not args.capture_only:
        from lab.dsp import build_route_blob
        from lab.formats import read_frames
        from lab.metrics import distribution
        from lab.pattern_dsp import PatternDsp, check_fext
        from lab.plaits import build_blob

        check_fext()
        sine = build_route_blob(sine=True)
        variants = [("stock", STOCK_BLOB.read_bytes()), ("sine-installed", sine)]
        if args.custom_engines:
            plaits = build_blob(True, family="integration", output=out / "plaits-build")
            variants.append(("plaits-installed", plaits))

        def render_case(
            name,
            replay,
            row,
            variant,
            blob,
            *,
            cpu_stock=True,
            origin=None,
            preroll=None,
        ):
            path = out / (name + "-replay.dtfr")
            write_frames(path, replay)
            label = name + "-" + variant
            try:
                engine = PatternDsp(blob)
                audio = array.array("f")
                active_counts = []
                for f in replay:
                    audio.extend(engine.frame(f))
                    active_counts.append(
                        sum(
                            bool(
                                engine.core.peek(
                                    engine.profile.voice_records
                                    + i * engine.h.VOICE_RECORD_STRIDE
                                    + engine.h.FIELD_ACTIVE,
                                    1,
                                )
                            )
                            for i in range(engine.h.VOICE_RECORD_COUNT)
                        )
                    )
                require(all(map(math.isfinite, audio)), "Nonfinite DSP output")
                if row["tracks"]:
                    require(
                        max(map(abs, audio)) > 1e-7,
                        "Triggered workload is silent in the voice tap",
                    )
                scope = {
                    "boundary": "Whole emulated DSP block handler; excludes DMA callback and Python output tap",
                    "instruction_unit": "emulated retired instructions, not physical clock cycles",
                    "instructions_per_block": distribution(engine.block_instructions),
                    "host_us_per_block": distribution(engine.block_host_us),
                    "target_cpu_load_percent": None,
                    "target_dsp_load_percent": None,
                }
                record = {
                    "frames": len(replay),
                    "capture": str(path),
                    "capture_sha256": sha256(path),
                    "preroll_trigger_frame": None,
                    "sample_rates": {"source": 96000, "captured_stereo": 48000},
                    "dsp_blob_sha256": hashlib.sha256(blob).hexdigest(),
                    "profile": scope,
                    "pcm_sha256": hashlib.sha256(audio.tobytes()).hexdigest(),
                    "peak": max(map(abs, audio)),
                    "cpu_stock": cpu_stock,
                    "workload": row["name"],
                    "installed_variant": variant,
                    "origin": origin or row["capture"],
                    "max_active_voice_lanes": max(active_counts),
                    "native_library_sha256": sha256(engine.library),
                    "fext_fallbacks": dict(engine.fallbacks),
                }
                record["preroll_trigger_frame"] = preroll
                write_json(out / (label + ".json"), record)
                write_json(
                    out / (label + "-profile.json"),
                    {
                        "scope": scope,
                        "instructions": engine.block_instructions,
                        "host_us": engine.block_host_us,
                    },
                )
                (out / (label + ".f32")).write_bytes(audio.tobytes())
                report["workloads"].append(
                    {
                        "name": name,
                        "variant": variant,
                        "profile": str(out / (label + "-profile.json")),
                        "mean_instructions": scope["instructions_per_block"]["mean"],
                        "peak_instructions": scope["instructions_per_block"][
                            "max_observed"
                        ],
                    }
                )
                print(label, scope["instructions_per_block"], flush=True)
            except BaseException as exc:
                report.update(status="failed", error=str(exc), failed_case=label)
                manifest.update(status="failed", error=str(exc), failed_case=label)
                write_json(out / "stock-capture.json", report)
                write_json(out / "manifest.json", manifest)
                raise

        for name, raw, row in captures:
            replay = fixed_replay(raw, args.frames)
            for variant, blob in variants:
                render_case(name, replay, row, variant, blob)
            require(
                (out / (name + "-stock.f32")).read_bytes()
                == (out / (name + "-sine-installed.f32")).read_bytes(),
                "Installed SINE changed stock voice PCM",
            )
            if args.custom_engines:
                require(
                    (out / (name + "-stock.f32")).read_bytes()
                    == (out / (name + "-plaits-installed.f32")).read_bytes(),
                    "Installed Plaits changed stock voice PCM",
                )
        if args.custom_engines:
            sine_capture = FIXTURE / "captures/sine-type-7.dtfr"
            raw = read_frames(sine_capture)
            first = next(i for i, f in enumerate(raw) if trigger_mask([f]) & 1)
            replay = track_one_clip(raw + [raw[-1]] * args.frames, first, args.frames)
            render_case(
                "sine-active",
                replay,
                {"tracks": [1], "name": "sine-active"},
                "sine",
                sine,
                cpu_stock=False,
                origin=str(sine_capture),
                preroll=32,
            )
            capture = ROOT / "out/runs/integration-r3-pattern-final-02"
            meta = json.loads((capture / "capture.json").read_text())
            require(
                meta["status"] == "passed"
                and sha256(capture / "pattern.dtfr") == meta["capture_sha256"],
                "Unknown R3 capture",
            )
            raw = read_frames(capture / "pattern.dtfr", max_frames=32768)
            first = meta["passes"][0]["render_start"]
            replay = track_one_clip(raw, first, args.frames)
            require(
                all(int.from_bytes(f[0xDE:0xE0], "big") == 256 for f in replay),
                "R3 clip is not FM model",
            )
            render_case(
                "plaits-fm-active",
                replay,
                {"tracks": [1], "name": "plaits-fm-active"},
                "plaits",
                plaits,
                cpu_stock=False,
                origin=str(capture / "pattern.dtfr"),
                preroll=32,
            )
            report["custom_input_scope"] = (
                "Active custom cases use historical custom-CPU captures, with 32-frame preroll and explicit track-one event isolation; they are not stock-CPU captures or matched stock-engine comparisons"
            )
    require(
        {p: sha256(p) for p in frozen_sources} == frozen_sources,
        "Baseline source changed during run",
    )
    report["status"] = "passed"
    write_json(out / "stock-capture.json", report)
    manifest.update(
        status="passed",
        finished_utc=datetime.now(UTC).isoformat(),
        result={"ok": True, "scope": report["scope"]},
    )
    write_json(out / "manifest.json", manifest)
    print("PASS:", out, flush=True)
except BaseException as exc:
    report.update(status="failed", error=str(exc))
    manifest.update(
        status="failed", error=str(exc), finished_utc=datetime.now(UTC).isoformat()
    )
    write_json(out / "stock-capture.json", report)
    write_json(out / "manifest.json", manifest)
    raise
