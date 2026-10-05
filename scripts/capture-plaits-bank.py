# ruff: noqa: E402
"""Capture real six-model MODEL locks from the prepared SINE CPU checkpoint (no device)."""

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
meta = build_cpu(family="bank")
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
        return "Plaits MODEL offline recorder"

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


def turn(delta, count=1):
    emu._dwell_chunks = 0
    for _ in range(count):
        emu.inbox.append(("encoder", code("ENCODER C", True), delta))
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
        "base_model_raw": int.from_bytes(emu._uc.mem_read(ptr + 0x48 + 54, 2), "big"),
        "mirror_model_raw": int.from_bytes(emu._uc.mem_read(0x80003398, 2), "big"),
    }
    report["stages"].append(row)
    if emu._panel_latch:
        panel.write_png(emu._panel_latch, str(out / (name + ".png")))
    print(json.dumps(row), flush=True)


def verify_locked_model(step, model):
    """Read real trigger words while held; bounded panel-only correction."""
    delta = 3
    previous_error = None
    for attempt in range(8):
        start = len(recorder.frames)
        tap("YES")
        advance(4_000_000)
        events = [values(f) for f in recorder.frames[start:] if values(f)["trig"] & 1]
        require(len(events) == 1, f"Expected one lock readback trigger: {events}")
        actual = events[0]["model"]
        row = {
            "step": step,
            "target": model * 256,
            "actual": actual,
            "attempt": attempt,
        }
        report["lock_readbacks"].append(row)
        print(json.dumps(row), flush=True)
        error = model * 256 - actual
        if not error:
            return
        if previous_error is not None and error * previous_error < 0:
            delta = max(1, delta - 1)
        elif error == previous_error:
            delta = min(4, delta + 1)
        turn(delta if error > 0 else -delta)
        previous_error = error
    raise ValueError(f"Could not set step {step} to model {model} through the panel")


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
    stage("base-va")
    # Store WS/ADD/GRAIN on 5/13/1; step 9 retains the base VA model.
    for step, turns in ((5, 3), (13, 4), (1, 5)):
        button(f"TRIG {step}", "press")
        turn(-8, 6)
        # Six-model range changes inherited encoder scaling. Check actual
        # trigger words rather than assuming a detent-to-model relationship.
        turn(3, turns)
        verify_locked_model(step, turns)
        stage(f"held-{step}")
        button(f"TRIG {step}", "release")
    tap("TRIG 9")
    save_longrun(
        emu._m, saved["events"], emu.live_forcer.pits, str(out / "models-ready.snap")
    )
    report["preview_start"] = len(recorder.frames)
    for step in (9, 5, 13, 1, 5, 9):
        button(f"TRIG {step}", "press")
        tap("YES")
        advance(20_000_000)
        stage(f"preview-{step}-{len(recorder.frames)}")
        button(f"TRIG {step}", "release")
    report["preview_end"] = len(recorder.frames)
    selected = [
        values(f)["model"]
        for f in recorder.frames[report["preview_start"] : report["preview_end"]]
        if values(f)["trig"] & 1
    ]
    report["preview_models_raw"] = selected
    require(
        selected == [0, 768, 1024, 1280, 768, 0],
        f"Unexpected model lock recall: {selected}",
    )
    require(source_hashes() == fingerprint, "Source changed during capture")
    report["status"] = "passed"
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    emu.stop_flag.set()
    emu.pause.clear()
    emu.join(timeout=30)
    frames = recorder.frames
    (out / "models.dtfr").write_bytes(
        b"DTFR"
        + struct.pack("<II", 1, len(frames))
        + b"".join(struct.pack("<I", len(f)) + f for f in frames)
    )
    report["capture_sha256"] = sha256(out / "models.dtfr")
    report["worker_error"] = emu.error
    report["faulted_pages"] = sorted(emu._faulted_pages)
    write_json(out / "capture.json", report)
