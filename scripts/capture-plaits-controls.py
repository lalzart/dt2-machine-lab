# ruff: noqa: E402
"""Capture dedicated macro controls and locks from the prepared SINE CPU checkpoint (no device)."""

import argparse
import hashlib
import json
import os
import struct
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument(
    "--snapshot",
    type=Path,
    default=ROOT / "out/runs/controls-cpu-lock-fast/locked-ready.snap",
)
args = p.parse_args()
doctor()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.plaits import build_cpu
from lab.runtime import REPO, STOCK_MAIN

inputs = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
inputs["snapshot"] = str(args.snapshot.resolve())
meta = build_cpu(family="controls")
old = Path(inputs["main"]).read_bytes()
require(
    hashlib.sha256(old).hexdigest()
    == "344bf871f4e25f0d3c349099223ed17ef44da47eddde167fc14e5fe493f44830",
    "Expected inherited SINE image",
)
new = (out / "PLAITS_MAIN_OS.bin").read_bytes()
require(len(old) == len(new), "Image extent changed")
patches = []
i = 0
while i < len(old):
    if old[i] == new[i]:
        i += 1
        continue
    start = i
    while i < len(old) and old[i] != new[i]:
        i += 1
    patches.append((start, old[start:i], new[start:i]))
# Restore the checkpoint under its original image, then apply guarded image diffs.
os.chdir(REPO)
os.environ.update(
    DT2_SYX=inputs["syx"], DT2_SECTIONS=inputs["sections"], DT2_MAIN_IMG=inputs["main"]
)
import framelink
from emu import gui, panel
from emu.checkpoint import save_longrun
from live_gui_check import _pause_at_limit

profile = framelink.PROFILES[sha256(STOCK_MAIN)]
original = STOCK_MAIN.read_bytes()
for field in ("handler", "driver", "counter", "gate"):
    off = profile[field] - 0x40000400
    if 0 <= off < len(old):
        require(
            original[off : off + 64] == old[off : off + 64] == new[off : off + 64],
            f"Frame-link site changed: {field}",
        )
framelink.PROFILES[hashlib.sha256(old).hexdigest()] = dict(profile)


class Recorder:
    period = 200_000

    def __init__(self):
        self.frames = []

    def open(self):
        return self

    def close(self):
        pass

    def device_name(self):
        return "Plaits macro offline recorder"

    def push_frame(self, frame):
        require(len(self.frames) < 4096, "Capture frame bound exceeded")
        self.frames.append(bytes(frame))

    def frame_stats(self):
        return SimpleNamespace(
            pushed=len(self.frames),
            trig_pushed=sum(f[0x22:0x24] != b"\0\0" for f in self.frames),
            taken=0,
            repeats=0,
            max_depth=len(self.frames),
            merged=0,
        )

    def stats(self):
        return SimpleNamespace(underruns=0)

    def render_stats(self):
        return SimpleNamespace(
            frames=0, clean=0, stopped=0, nonzero_frames=0, median_us=0, p99_us=0
        )


saved = {}
original_build = gui.build


def capture_build(*a, **kw):
    result = original_build(*a, **kw)
    saved["events"] = result[1]
    return result


gui.build = capture_build
recorder = Recorder()
emu = gui.Emulator(
    inputs["snapshot"],
    syx=inputs["syx"],
    card_image=inputs["card"],
    live=recorder,
    fast=False,
    realtime=False,
    panel_dwell=4,
)
emu.pause.set()
emu.start()
fingerprint = source_hashes()
report = {
    "inputs": inputs,
    "input_sha256": {k: sha256(v) for k, v in inputs.items() if k != "sections"},
    "source_sha256": fingerprint,
    "cpu_candidate": meta,
    "stages": [],
    "lock_readbacks": [],
    "macro_lock_readbacks": [],
    "scope": "Prepared checkpoint plus guarded CPU image diff; real panel encoder locks and step previews, zero DSP replies. No clean boot, project reload or continuous PLAY claim.",
}
deadline = time.monotonic() + 600


def advance(n=2_000_000):
    target = emu.stats["instrs"] + n
    emu.pause.clear()
    while emu.inbox or emu.stats["instrs"] < target:
        require(not emu.error and emu.is_alive(), f"CPU stopped: {emu.error}")
        if time.monotonic() > deadline:
            raise TimeoutError("600-second CPU limit")
        time.sleep(0.005)
    _pause_at_limit(emu)


def code(name, encoder=False):
    names = emu.encoder_names if encoder else emu.button_names
    hits = [k for k, v in names.items() if v.upper() == name]
    require(len(hits) == 1, f"Unknown control {name}")
    return hits[0]


def button(name, action):
    emu.inbox.append((action, code(name), None))
    advance()


def tap(name):
    emu.inbox.extend([("press", code(name), None), ("release", code(name), None)])
    advance()


def turn(delta, count=1, encoder="C"):
    emu._dwell_chunks = 0
    for _ in range(count):
        emu.inbox.append(("encoder", code("ENCODER " + encoder, True), delta))
        advance(200_000)
    emu._dwell_chunks = 4
    advance(4_000_000)


def values(frame):
    return {
        k: int.from_bytes(frame[o : o + 2], "big")
        for k, o in {
            "trig": 0x22,
            "type": 0x94,
            "model": 0xDE,
            "note": 0x02,
            "tune": 0xDA,
            "harmonics": 0xDC,
            "timbre": 0xE0,
            "morph": 0xE6,
            "length": 0xE8,
            "level": 0xEC,
        }.items()
    }


def stage(name):
    ptr = int.from_bytes(emu._uc.mem_read(0x80004704, 4), "big")
    row = {
        "name": name,
        "frame": len(recorder.frames),
        "wire": values(recorder.frames[-1]),
        "base": {
            k: int.from_bytes(emu._uc.mem_read(ptr + 0x48 + 2 * index, 2), "big")
            for k, index in (
                ("harmonics", 26),
                ("timbre", 28),
                ("morph", 31),
                ("model", 27),
            )
        },
        "raw_mirrors": {
            k: int.from_bytes(emu._uc.mem_read(0x80003362 + 2 * index, 2), "big")
            for k, index in (
                ("harmonics", 26),
                ("timbre", 28),
                ("morph", 31),
                ("model", 27),
            )
        },
        "smoothed": {
            k: int.from_bytes(emu._uc.mem_read(0x80005B72 + 2 * index, 2), "big")
            for k, index in (
                ("harmonics", 26),
                ("timbre", 28),
                ("morph", 31),
                ("model", 27),
            )
        },
    }
    report["stages"].append(row)
    if emu._panel_latch:
        panel.write_png(emu._panel_latch, str(out / (name + ".png")))
    print(json.dumps(row), flush=True)


MACROS = ("harmonics", "timbre", "morph")


def base_values():
    ptr = int.from_bytes(emu._uc.mem_read(0x80004704, 4), "big")
    return {
        k: int.from_bytes(emu._uc.mem_read(ptr + 0x48 + 2 * i, 2), "big")
        for k, i in zip(MACROS, (26, 28, 31), strict=True)
    }


def preview():
    begin = len(recorder.frames)
    tap("YES")
    advance(4_000_000)
    triggers = [
        (begin + i, values(f))
        for i, f in enumerate(recorder.frames[begin:])
        if values(f)["trig"] & 1
    ]
    require(len(triggers) == 1, f"Expected one preview trigger: {triggers}")
    index, row = triggers[0]
    require(row["model"] == 768, "Expected WS")
    return {"frame": index, "values": row}


try:
    require(emu.ready.wait(60) and not emu.error, f"CPU startup failed: {emu.error}")
    for offset, before, after in patches:
        address = 0x40000400 + offset
        require(
            bytes(emu._uc.mem_read(address, len(before))) == before,
            f"Checkpoint image drift at {address:#x}",
        )
        emu._uc.mem_write(address, after)
    ptr = int.from_bytes(emu._uc.mem_read(0x80004704, 4), "big")
    require(emu._uc.mem_read(ptr + 0xD6, 1)[0] == 7, "Expected selected type 7")
    tap("SRC")
    turn(-8, 6)
    turn(3, 3)
    stage("selected-ws")
    sweep = []
    for n in range(8):
        turn(8, 3, "B")
        stage(f"harmonics-{n}")
        sweep.append(base_values()["harmonics"])
    require(len(set(sweep)) == 8, "HARM lacks eight distinct panel values")
    report["harmonics_sweep_raw"] = sweep
    turn(8, 16, "D")
    turn(8, 6, "E")
    base = base_values()
    report["base_values"] = base
    stage("base-values")
    locks = {}
    for step, delta in ((5, 8), (13, -8)):
        button(f"TRIG {step}", "press")
        for encoder in ("B", "D", "E"):
            turn(delta, 8, encoder)
        readback = preview()
        locks[step] = {k: readback["values"][k] for k in MACROS}
        require(
            all(locks[step][k] != base[k] for k in MACROS),
            "Macro lock did not differ from base",
        )
        require(base_values() == base, "Setting locks changed base parameters")
        report["macro_lock_readbacks"].append({"step": step, **readback})
        stage(f"stored-{step}")
        button(f"TRIG {step}", "release")
    require(locks[5] != locks[13], "Locks A/B are equal")
    save_longrun(
        emu._m, saved["events"], emu.live_forcer.pits, str(out / "macros-ready.snap")
    )
    report["preview_start"] = len(recorder.frames)
    report["previews"] = []
    for step in (5, 13, 9, 5, 9):
        button(f"TRIG {step}", "press")
        actual = preview()
        expected = locks.get(step, base)
        require(
            {k: actual["values"][k] for k in MACROS} == expected,
            f"Lock/base recall failed: {actual}, {expected}",
        )
        report["previews"].append({"step": step, **actual})
        stage(f"recall-{step}-{len(recorder.frames)}")
        button(f"TRIG {step}", "release")
    report["preview_end"] = len(recorder.frames)
    button("TRIG 9", "press")
    actual = preview()
    report["sustain_start"] = actual["frame"]
    button("TRIG 9", "release")
    turn(8, 8, "B")
    stage("sustained-harmonics-edit")
    report["sustain_end"] = len(recorder.frames)
    sustained = [
        values(f)
        for f in recorder.frames[report["sustain_start"] : report["sustain_end"]]
    ]
    require(
        sum(bool(f["trig"] & 1) for f in sustained) == 1, "Sustain edit retriggered"
    )
    require(
        len({f["harmonics"] for f in sustained}) > 1,
        "Sustain edit did not reach the wire",
    )
    report["default_reset"] = (
        "Metadata defaults verified separately; panel reset gesture not established"
    )
    require(source_hashes() == fingerprint, "Source changed during capture")
    report["status"] = "passed"
except BaseException as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    emu.stop_flag.set()
    emu.pause.clear()
    emu.join(timeout=30)
    frames = recorder.frames
    (out / "macros.dtfr").write_bytes(
        b"DTFR"
        + struct.pack("<II", 1, len(frames))
        + b"".join(struct.pack("<I", len(f)) + f for f in frames)
    )
    report["capture_sha256"] = sha256(out / "macros.dtfr")
    report["worker_error"] = emu.error
    report["faulted_pages"] = sorted(emu._faulted_pages)
    write_json(out / "capture.json", report)
