# ruff: noqa: E402
"""Small panel-input experiment: SINE controls and sequencer parameter locks.

Run with the configured patched Python; requires .local/cpu-inputs.json.
The original card is mapped read-only by DigiKit; writes stay in its RAM overlay.
"""

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
from lab.project import doctor, settings, sha256, source_hashes

CONFIG = settings()
if Path(sys.executable).resolve() != CONFIG["python"].resolve():
    os.execv(
        str(CONFIG["python"]),
        [str(CONFIG["python"]), str(Path(__file__).resolve()), *sys.argv[1:]],
    )
doctor()
REPO = CONFIG["digikit"]
sys.path[:0] = [str(REPO), str(REPO / "tools")]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument(
    "--locked-snapshot",
    type=Path,
    help="Resume a SINE grid snapshot with locked step 1 and unlocked step 5",
)
parser.add_argument(
    "--play",
    action="store_true",
    help="Capture bounded PLAY startup instead of three step previews",
)
args = parser.parse_args()
INPUTS = json.loads((ROOT / ".local/cpu-inputs.json").read_text())
if args.locked_snapshot:
    INPUTS["snapshot"] = str(args.locked_snapshot.resolve())
OUT = args.output.resolve()
if not OUT.is_relative_to(ROOT / "out/runs"):
    raise ValueError("Output must be a fresh directory below out/runs")
OUT.mkdir(parents=True, exist_ok=False)
os.chdir(REPO)  # DigiKit resolves the device descriptions relative to its root.
os.environ.update(
    DT2_SYX=INPUTS["syx"], DT2_SECTIONS=INPUTS["sections"], DT2_MAIN_IMG=INPUTS["main"]
)

import framelink
from emu import gui, panel
from live_gui_check import _pause_at_limit
from machinecheck import derive_down_taps


class Recorder:
    period = 200_000

    def __init__(self):
        self.frames = []

    def open(self):
        return self

    def close(self):
        pass

    def device_name(self):
        return "SINE controls offline recorder"

    def push_frame(self, frame):
        if len(self.frames) >= 4096:
            raise RuntimeError("4096-frame capture bound")
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


original = (CONFIG["fixture"] / "sections/section_3_MAIN_OS.bin").read_bytes()
candidate = Path(INPUTS["main"]).read_bytes()
original_sha = hashlib.sha256(original).hexdigest()
candidate_sha = hashlib.sha256(candidate).hexdigest()
if candidate_sha != "344bf871f4e25f0d3c349099223ed17ef44da47eddde167fc14e5fe493f44830":
    raise ValueError("Expected existing SINE CPU image")
profile = framelink.PROFILES[original_sha]
for field in ("handler", "driver", "counter", "gate"):
    offset = profile[field] - 0x40000400
    if (
        0 <= offset < len(original)
        and original[offset : offset + 64] != candidate[offset : offset + 64]
    ):
        raise ValueError(f"Frame-link site changed: {field}")
framelink.PROFILES[candidate_sha] = dict(profile)

saved_build = {}
original_build = gui.build


def capture_build(*args, **kwargs):
    result = original_build(*args, **kwargs)
    saved_build["events"] = result[1]
    return result


gui.build = capture_build
recorder = Recorder()
emu = gui.Emulator(
    INPUTS["snapshot"],
    syx=INPUTS["syx"],
    card_image=INPUTS["card"],
    live=recorder,
    fast=False,
    realtime=False,
    panel_dwell=4,
)
emu.pause.set()
emu.start()
deadline = time.monotonic() + 600
report = {
    "inputs": INPUTS,
    "main_sha256": candidate_sha,
    "stages": [],
    "input_sha256": {k: sha256(v) for k, v in INPUTS.items() if k != "sections"},
    "source_sha256": source_hashes(),
    "scope": "Real panel inputs and CPU DSPI2 transmissions; zero DSP replies, no hardware",
}


def advance(instructions=2_000_000):
    target = emu.stats["instrs"] + instructions
    emu.pause.clear()
    while emu.inbox or emu.stats["instrs"] < target:
        if emu.error or not emu.is_alive():
            raise RuntimeError(f"CPU stopped: {emu.error}")
        if time.monotonic() > deadline:
            raise TimeoutError("600-second CPU bound")
        time.sleep(0.005)
    _pause_at_limit(emu)


def code(name, encoder=False):
    names = emu.encoder_names if encoder else emu.button_names
    matches = [k for k, v in names.items() if v.upper() == name]
    if len(matches) != 1:
        raise ValueError(f"Unknown control {name}: {names}")
    return matches[0]


def button(name, kind):
    emu.inbox.append((kind, code(name), None))
    advance()


def tap(name):
    emu.inbox.extend([("press", code(name), None), ("release", code(name), None)])
    advance()


def turn(name, delta):
    emu.inbox.append(("encoder", code(f"ENCODER {name}", True), delta))
    advance()


def values(frame):
    return {
        name: int.from_bytes(frame[off : off + 2], "big")
        for name, off in {
            "note": 2,
            "trig": 0x22,
            "velocity": 0x34,
            "type": 0x94,
            "tune": 0xDA,
            "length": 0xE8,
            "level": 0xEC,
        }.items()
    }


def stage(name):
    entry = {
        "name": name,
        "frame": len(recorder.frames),
        "instructions": emu.stats["instrs"],
        "wire": values(recorder.frames[-1]),
    }
    ptr = int.from_bytes(emu._uc.mem_read(0x80004704, 4), "big")
    entry["base_sound"] = [
        int.from_bytes(emu._uc.mem_read(ptr + 0x34 + 0x14 + 2 * i, 2), "big")
        for i in (25, 32, 34)
    ]
    report["stages"].append(entry)
    if emu._panel_latch:
        panel.write_png(emu._panel_latch, str(OUT / f"{name}.png"))
    print(json.dumps(entry), flush=True)


try:
    if not emu.ready.wait(60) or emu.error:
        raise RuntimeError(f"CPU startup failed: {emu.error}")
    print(f"Buttons: {emu.button_names}; encoders: {emu.encoder_names}", flush=True)
    if args.locked_snapshot:
        advance(3_000_000)
        stage("restored-locks")
        ptr = int.from_bytes(emu._uc.mem_read(0x80004704, 4), "big")
        if emu._uc.mem_read(ptr + 0xD6, 1)[0] != 7:
            raise ValueError("Snapshot is not using the SINE machine on track 1")
    else:
        button("FUNC", "press")
        tap("SRC")
        button("FUNC", "release")
        for _ in range(derive_down_taps(7, 7)):
            tap("DOWN")
        tap("YES")
        tap("YES")
        advance(3_000_000)
        stage("selected")
        from emu.checkpoint import save_longrun

        save_longrun(
            emu._m,
            saved_build["events"],
            emu.live_forcer.pits,
            str(OUT / "selected-ready.snap"),
        )
        tap("TRIG 1")
        advance(8_000_000)
        stage("base-trigger")
        tap("RECORD")
        button("FUNC", "press")
        tap("PLAY")
        button("FUNC", "release")
        advance(4_000_000)
        stage("cleared-track")
        tap("TRIG 1")
        tap("TRIG 5")
        button("TRIG 1", "press")
        for name, delta in (("A", -8), ("F", -8), ("H", -8)):
            # The GUI's dwell gate also throttles encoder messages. Keep button
            # pacing, but deliver rotation bursts at separate chunk boundaries.
            emu._dwell_chunks = 0
            for _ in range(12):
                emu.inbox.append(("encoder", code(f"ENCODER {name}", True), delta))
                advance(200_000)
            emu._dwell_chunks = 4
            advance(4_000_000)
        advance(8_000_000)
        stage("held-locked-1")
        button("TRIG 1", "release")
        advance(8_000_000)
        stage("lock-stored")
        save_longrun(
            emu._m,
            saved_build["events"],
            emu.live_forcer.pits,
            str(OUT / "locked-ready.snap"),
        )
    report["capture_mode"] = "play" if args.play else "step-preview"
    report["play_start"] = len(recorder.frames)
    if args.play:
        tap("TRIG 2")
        tap("PLAY")
        advance(220_000_000)
        report["play_end"] = len(recorder.frames)
        stage("playing")
        tap("STOP")
    else:
        for step in (1, 5, 1):
            button(f"TRIG {step}", "press")
            tap("YES")
            advance(20_000_000)
            stage(f"preview-{step}-{len(recorder.frames)}")
            button(f"TRIG {step}", "release")
        report["play_end"] = len(recorder.frames)
        stage("previews-complete")

finally:
    emu.stop_flag.set()
    emu.pause.clear()
    emu.join(timeout=30)
    frames = recorder.frames
    blob = b"DTFR" + struct.pack("<II", 1, len(frames))
    blob += b"".join(struct.pack("<I", len(f)) + f for f in frames)
    (OUT / "controls.dtfr").write_bytes(blob)
    report["trigger_frames"] = [
        {"frame": i, **values(f)}
        for i, f in enumerate(frames)
        if int.from_bytes(f[0x22:0x24], "big") & 1
    ]
    report["faulted_pages"] = sorted(emu._faulted_pages)
    report["worker_error"] = emu.error
    report["completed_capture"] = "play_end" in report
    (OUT / "capture.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["trigger_frames"]), flush=True)
