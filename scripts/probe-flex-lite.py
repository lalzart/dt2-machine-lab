#!/usr/bin/env python3
# ruff: noqa: E402
"""Bounded RAM-backed sample publication and stock-playback experiment."""

import argparse
import array
import hashlib
import math
import os
import shutil
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--snapshot", type=Path, required=True)
parser.add_argument(
    "--cpu-only",
    action="store_true",
    help="Stop at CPU publication; not a complete acceptance run",
)
args = parser.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh ignored run directory")
preflight = doctor()
require(
    sha256(args.snapshot)
    == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
    "Unknown CPU snapshot",
)
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
# lab.runtime installs the pinned tool import paths.
# isort: off
from lab.flex_lite import FlexDsp, RamFirmware
from lab.runtime import STOCK_MAIN
import plusdrive_check as check
import tools.plusdrive as pd
# isort: on

SOURCES = [
    ROOT / p
    for p in (
        "lab/flex_lite.py",
        "scripts/probe-flex-lite.py",
        "lab/dsp.py",
        "lab/runtime.py",
        "docs/FLEX-LITE-PROTOTYPE.md",
    )
]
FINGERPRINT = {str(p.relative_to(ROOT)): sha256(p) for p in SOURCES}
for source in SOURCES:
    archived = out / "frozen-sources" / source.relative_to(ROOT)
    archived.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, archived)
VARIANTS = {
    "base": {},
    "octave": {0xDA: 0x4C00},
    "trim": {0xE6: 0x1E00, 0xE8: 0x1800},
    "loop": {0xDC: 0x0200, 0xE8: 0x1E00},
    "reverse": {0xDC: 0},
    "reverse-loop": {0xDC: 0x0100, 0xE8: 0x1E00},
}


def pcm_words(stereo, generation=1, count=12000):
    words = []
    for i in range(count):
        words.append(
            round(
                9000
                * math.sin(2 * math.pi * (440 if generation == 1 else 659) * i / 48000)
            )
        )
        if stereo:
            words.append(
                round(
                    6000
                    * math.sin(
                        2 * math.pi * (733 if generation == 1 else 1097) * i / 48000
                    )
                )
            )
    return words


def write_wav(path, words, stereo):
    with wave.open(str(path), "wb") as wav:
        wav.setparams((2 if stereo else 1, 2, 48000, 0, "NONE", "not compressed"))
        wav.writeframes(struct.pack(f"<{len(words)}h", *words))


def store_pages(folder, name, pages):
    raw = b"".join(struct.pack(">II", tag, hdr) + block for tag, block, hdr in pages)
    (folder / f"{name}-pages.bin").write_bytes(raw)


def control(wire, slot, variant="base", trigger=False):
    f = bytearray(wire)
    changes = {
        0: 3,
        2: 0x3C00,
        0x22: int(trigger),
        0x24: 0,
        0x26: 0,
        0x28: 0,
        0x94: 0,
        0xDA: 0x4000,
        0xDC: 0x300,
        0xDE: 0,
        0xE0: slot,
        0xE6: 0,
        0xE8: 0x7800,
        0xEA: 0,
        0xEC: 0x6400,
    }
    changes.update(VARIANTS[variant])
    for offset, value in changes.items():
        struct.pack_into(">H", f, offset, value)
    return bytes(f)


def render(seed, pages, wire, slot, variant, folder, name, frames=256):
    from live_gui_check import write_wav as write_float_wav

    dsp = FlexDsp(seed)
    dsp.publish(pages)
    samples = array.array("f")
    latched = None
    for i in range(frames):
        samples.extend(dsp.frame(control(wire, slot, variant, i == 10)))
        if i == 15:
            latched = dsp.voice()
    require(all(map(math.isfinite, samples)), "Nonfinite voice PCM")
    (folder / f"{name}.f32").write_bytes(samples.tobytes())
    write_float_wav(str(folder / f"{name}.wav"), samples, 48000)
    result = {
        "sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
        "peak": max(map(abs, samples)),
        "latched": latched,
        "last": dsp.voice(),
        "frames": frames,
    }
    return samples.tobytes(), result, dsp


report = {
    "status": "running",
    "preflight": preflight,
    "source_sha256": FINGERPRINT,
    "proposal_sha256": sha256(ROOT / "docs/FLEX-LITE-FEASIBILITY.md"),
    "snapshot": str(args.snapshot.resolve()),
    "snapshot_sha256": sha256(args.snapshot),
    "scope": "Prepared CPU loader, RAM-input shim, controlled live-track assignment and frame construction, modeled LP0 delivery, stock offline SHARC voice buffers. No panel recording, project save/reload, real time, final mixer or hardware.",
    "control_edits": {
        "base": {
            hex(o): v
            for o, v in {
                0: 3,
                2: 0x3C00,
                0x94: 0,
                0xDA: 0x4000,
                0xDC: 0x300,
                0xDE: 0,
                0xE6: 0,
                0xE8: 0x7800,
                0xEA: 0,
                0xEC: 0x6400,
            }.items()
        },
        "variants": {
            name: {hex(o): v for o, v in changes.items()}
            for name, changes in VARIANTS.items()
        },
        "trigger": "track 1 at frame 10; release/aux event words zero",
        "slot": "actual CPU-allocated slot",
    },
    "cases": [],
}
try:
    for stereo in (False, True):
        folder = out / ("stereo" if stereo else "mono")
        folder.mkdir()
        stock_dir, ram_dir = folder / "stored-fixtures", folder / "ram-drive-fixtures"
        stock_dir.mkdir()
        ram_dir.mkdir()
        write_wav(stock_dir / "00-background.wav", pcm_words(False, 2, 2400), False)
        shutil.copyfile(stock_dir / "00-background.wav", ram_dir / "00-background.wav")
        words = pcm_words(stereo)
        pcm = struct.pack(f">{len(words)}h", *words)
        write_wav(stock_dir / "10-a.wav", words, stereo)
        write_wav(stock_dir / "20-b.wav", pcm_words(stereo, 2), stereo)
        stock_card, ram_card = folder / "reference.img", folder / "ram-drive.img"
        stored_entries = pd.build(
            str(stock_dir), str(stock_card), main_os=STOCK_MAIN.read_bytes()
        )
        ram_entries = pd.build(
            str(ram_dir), str(ram_card), main_os=STOCK_MAIN.read_bytes()
        )
        require(
            len(stored_entries) == 3 and len(ram_entries) == 1,
            "Image fixture contents differ",
        )
        stock, temp = (
            RamFirmware(stock_card, args.snapshot),
            RamFirmware(ram_card, args.snapshot),
        )
        row = {"stereo": stereo, "renders": {}}
        report["cases"].append(row)
        try:
            stock.call(0x40154358, [])
            temp.call(0x40154358, [])
            resets = list(temp.pages)
            check.check_mount(stock, stored_entries[0]["ref"])
            check.check_mount(temp, ram_entries[0]["ref"])
            background, bg_pages = temp.load(ram_entries[0]["ref"], 1)
            stock_background, _ = stock.load(stored_entries[0]["ref"], 1)
            require(
                background["allocation"]["start"]
                == stock_background["allocation"]["start"],
                "Background placement differs",
            )
            temp.card.reads.clear()
            temp.card.writes.clear()
            slot = temp.free_slot()
            require(stock.slot(slot)["empty"], "Comparator slot occupied")
            stored, stored_pages = stock.load(stored_entries[1]["ref"], slot)
            temp.enable_ram()
            ref = temp.source(pcm, stereo)
            ram, ram_pages = temp.load(ref, slot)
            require(
                check.sent_pcm_matches(ram, pd.build_native_sample(pcm, stereo))
                == [True] * (2 if stereo else 1),
                "RAM publication PCM differs",
            )
            require(
                stored["slot_headers"] == ram["slot_headers"], "Slot headers differ"
            )
            require(len(stored_pages) == len(ram_pages), "Transfer count differs")
            require(
                not temp.card.reads and not temp.card.writes,
                "RAM loader touched storage",
            )
            wire = temp.capture_assignment(slot)
            stored_wire = stock.capture_assignment(slot)
            require(wire == stored_wire, "CPU assignment frames differ")
            (folder / "cpu-assignment-wire.bin").write_bytes(wire)
            for name, pages in (
                ("stock", stored_pages),
                ("ram", ram_pages),
                ("background", bg_pages),
                ("reset", resets),
            ):
                store_pages(folder, name, pages)
            bg_before = temp.slot(1)
            require(
                ram["allocation"]["start"] >= bg_before["start"] + bg_before["size"],
                "Temporary allocation overlaps background",
            )
            row.update(
                slot=slot,
                allocation=ram["allocation"],
                background=bg_before,
                headers=ram["slot_headers"],
                transfers=len(ram_pages),
                source_hooks=temp.source_hooks,
                cpu_assignment="live track RAM write; original row refresh and all-track packing; settled-smoother calibration; direct bounded ISR entry",
            )
            if args.cpu_only:
                continue
            seed_dsp = FlexDsp()
            seed_dsp.publish(resets)
            seed_dsp.publish(bg_pages)
            seed = seed_dsp.state_bytes()
            (folder / "dsp-seed.bin").write_bytes(seed)
            row["seed_sha256"] = hashlib.sha256(seed).hexdigest()
            bg_record = seed_dsp.slot_record(1)
            bg_pcm = seed_dsp.sample_bytes(bg_record[0], bg_record[2])
            negative_pages = [p for p in ram_pages if not p[2]]
            _, negative, _ = render(
                seed,
                negative_pages,
                wire,
                slot,
                "base",
                folder,
                "unpublished",
                frames=32,
            )
            require(negative["peak"] == 0, "Unpublished slot produced audio")
            row["unpublished"] = negative
            for variant in VARIANTS:
                expected, reference, _ = render(
                    seed, stored_pages, wire, slot, variant, folder, f"{variant}-stock"
                )
                actual, rendered, dsp = render(
                    seed, ram_pages, wire, slot, variant, folder, f"{variant}-ram"
                )
                repeated, repeat, _ = render(
                    seed, ram_pages, wire, slot, variant, folder, f"{variant}-repeat"
                )
                require(
                    actual == expected == repeated,
                    f"{variant} PCM parity or exact repeat failed",
                )
                require(rendered["peak"] > 0, f"{variant} is silent")
                require(
                    dsp.slot_record(1) == bg_record
                    and dsp.sample_bytes(bg_record[0], bg_record[2]) == bg_pcm,
                    "Background sample changed",
                )
                state = rendered["latched"]
                row["renders"][variant] = {
                    **rendered,
                    "stock_exact": True,
                    "repeat_exact": True,
                    "semantic_checks": "pending",
                }
                expected_step = (
                    -0.5
                    if variant.startswith("reverse")
                    else 1.0
                    if variant == "octave"
                    else 0.5
                )
                # The stock exponent approximation gives 0.9999999403953552
                # at +12 semitones. PCM equality above remains byte-exact.
                require(
                    abs(state["step"] - expected_step) <= 1e-7,
                    "Pitch/direction mismatch",
                )
                require(
                    state["reverse"] == int(variant.startswith("reverse")),
                    "Reverse flag mismatch",
                )
                require(state["loop"] == int("loop" in variant), "Loop flag mismatch")
                if variant == "trim":
                    require(
                        state["start"] == 3000 and state["end"] == 5400,
                        "Trim bounds mismatch",
                    )
                if "loop" in variant:
                    require(
                        state["end"] == 3000 and rendered["last"]["active"] == 1,
                        "Loop did not outlive sample region",
                    )
                if variant != "base":
                    require(
                        actual != (folder / "base-ram.f32").read_bytes(),
                        "Control did not change output",
                    )
                if variant == "base":
                    left, right, length, _, _ = dsp.slot_record(slot)
                    channels = 2 if stereo else 1
                    for lane, start in enumerate((left, right)[:channels]):
                        channel = struct.pack(
                            f"<{len(words) // channels}h", *words[lane::channels]
                        )
                        require(
                            dsp.sample_bytes(start, length) == channel,
                            "DSP sample bytes differ",
                        )
                        require(
                            dsp.sample_bytes(start + length, 10) == channel[:10],
                            "Interpolation guard differs",
                        )
                        require(
                            start + length + 10
                            <= ram["allocation"]["start"]
                            - 0x400
                            + ram["allocation"]["size"],
                            "Guard exceeds owned allocation",
                        )
                    row["dsp_pcm_and_guards_exact"] = True
                row["renders"][variant]["semantic_checks"] = "passed"
                print(
                    f"PASS {'stereo' if stereo else 'mono'} {variant}: exact stock/repeat PCM",
                    flush=True,
                )
                write_json(out / "report.json", report)
            require(dsp.reading(slot), "Lifecycle sample is not active")
            refused = False
            try:
                temp.unload(slot, dsp)
            except ValueError as exc:
                refused = "still read" in str(exc)
            require(refused, "Active unload was not refused")
            occupied_refused = False
            try:
                temp.load(ref, slot)
            except ValueError as exc:
                occupied_refused = "occupied slot" in str(exc)
            require(occupied_refused, "Occupied-slot replacement was not refused")
            detached_wire = temp.capture_assignment(0)
            for i in range(4):
                dsp.frame(control(detached_wire, 0, "base", i == 0))
            require(not dsp.reading(slot), "Empty-slot trigger did not detach")
            temp.unload(slot, dsp)
            require(temp.slot(1) == bg_before, "Unload disturbed background allocation")
            next_words = pcm_words(stereo, 2)
            ref_b = temp.source(
                struct.pack(f">{len(next_words)}h", *next_words), stereo, 2
            )
            new_ram, new_pages = temp.load(ref_b, slot)
            replacement_wire = temp.capture_assignment(slot)
            dsp.publish(new_pages)
            new_audio = []
            for i in range(32):
                new_audio.extend(
                    dsp.frame(control(replacement_wire, slot, "base", i == 10))
                )
            require(
                max(map(abs, new_audio)) > 0 and dsp.reading(slot),
                "Replacement did not play",
            )
            require(
                check.sent_pcm_matches(
                    new_ram,
                    pd.build_native_sample(
                        struct.pack(f">{len(next_words)}h", *next_words), stereo
                    ),
                )
                == [True] * (2 if stereo else 1),
                "Replacement PCM differs",
            )
            require(new_pages != ram_pages, "Replacement did not change PCM")
            new_pcm = array.array("f", new_audio).tobytes()
            require(
                all(map(math.isfinite, new_audio))
                and new_pcm != (folder / "base-ram.f32").read_bytes()[: len(new_pcm)],
                "Replacement voice output did not change or is nonfinite",
            )
            (folder / "replacement.f32").write_bytes(new_pcm)
            store_pages(folder, "replacement", new_pages)
            require(
                dsp.slot_record(1) == bg_record
                and dsp.sample_bytes(bg_record[0], bg_record[2]) == bg_pcm,
                "Replacement changed background PCM",
            )
            row["lifecycle"] = {
                "active_unload_refused": True,
                "occupied_replacement_refused": True,
                "detach_unload_reload_play": True,
                "replacement": new_ram["allocation"],
                "replacement_audio_sha256": hashlib.sha256(new_pcm).hexdigest(),
                "replacement_audio_changed": True,
                "background_preserved": True,
            }
        finally:
            row.update(
                ram_storage_reads=len(temp.card.reads),
                ram_storage_writes=len(temp.card.writes),
                ram_source_events=temp.source_events,
                ram_card_files=[e["name"] for e in pd.ls(ram_card)],
                cpu_fault_pages=sorted(hex(a) for a in temp.m.fault_pages),
            )
            require(
                not temp.card.reads and not temp.card.writes,
                "Temporary operations touched storage",
            )
            require(not temp.m.fault_pages, "Unexpected CPU fault pages")
            stock.close()
            temp.close()
    require(
        {str(p.relative_to(ROOT)): sha256(p) for p in SOURCES} == FINGERPRINT,
        "Source changed during run",
    )
    report["status"] = "cpu-publication-passed" if args.cpu_only else "passed"
except Exception as error:
    report["status"] = "failed"
    report["error"] = str(error)
    raise
finally:
    write_json(out / "report.json", report)
print(f"PASS: {report['status']}; {out / 'report.json'}", flush=True)
