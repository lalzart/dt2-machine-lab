# ruff: noqa: E402
"""Replay CPU controls with track-1 event isolation; write audio and observations."""

import argparse
import array
import hashlib
import importlib
import json
import math
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, settings, source_hashes

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(
        str(config["python"]),
        [str(config["python"]), str(Path(__file__).resolve()), *sys.argv[1:]],
    )
doctor()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "capture", type=Path, help="Directory containing capture.json and controls.dtfr"
)
parser.add_argument("output", type=Path)
args = parser.parse_args()
capture = args.capture.resolve()
out = args.output.resolve()
if not out.is_relative_to(ROOT / "out/runs"):
    raise ValueError("Output must be below out/runs")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
importlib.import_module("lab.runtime")
from live_gui_check import write_wav

from lab.dsp import Dsp, build_route_blob
from lab.formats import read_frames

all_frames = read_frames(capture / "controls.dtfr")
meta = json.loads((capture / "capture.json").read_text())
a, b = meta["play_start"], meta["play_end"]
if not (0 < a < b <= len(all_frames)):
    raise ValueError("Missing or invalid completed capture range")
frames = [all_frames[a - 1]] * 150 + all_frames[a:b] + [all_frames[b - 1]] * 500
# Isolate track 1: other stock tracks reach unsupported native DSP code.
frames = [bytearray(f) for f in frames]
for f in frames:
    for off in (0x22, 0x24, 0x26, 0x28):
        f[off : off + 2] = (int.from_bytes(f[off : off + 2], "big") & 1).to_bytes(
            2, "big"
        )
if any(
    frames[0][off : off + 2] != b"\0\0" or frames[-1][off : off + 2] != b"\0\0"
    for off in (0x22, 0x24, 0x26, 0x28)
):
    raise ValueError("Padding frames contain one-shot events")
engine = Dsp(build_route_blob(sine=True, controls=True))
audio = array.array("f")
source = array.array("f")
events = []
previous_age = 0
for i, frame in enumerate(frames):
    audio.extend(engine.frame(frame))
    source.extend(engine.source)
    state = [engine.core.peek(0x200F0100 + 4 * j) for j in range(7)]
    if state[1] and state[1] < previous_age or (state[1] and previous_age == 0):
        events.append(
            {
                "render_frame": i,
                "capture_frame": a + i - 150,
                "state": state,
                "frequency_from_increment": state[4] * 96000 / 2**32,
                "duration_ms": state[5] / 96,
                "gain": struct.unpack("<f", struct.pack("<I", state[6]))[0],
                "wire": {
                    name: int.from_bytes(frame[off : off + 2], "big")
                    for name, off in {
                        "tune": 0xDA,
                        "length": 0xE8,
                        "level": 0xEC,
                        "note": 2,
                    }.items()
                },
            }
        )
    previous_age = state[1]
    if i % 250 == 0:
        print("render frame", i, flush=True)
write_wav(str(out / "controls.wav"), audio)
(out / "controls-source.f32").write_bytes(source.tobytes())
(out / "controls.f32").write_bytes(audio.tobytes())
for n, event in enumerate(events):
    start = event["render_frame"] * 64
    end = min(
        events[n + 1]["render_frame"] * 64 if n + 1 < len(events) else len(source),
        start + event["state"][5],
    )
    chunk = source[start:end]
    event["peak"] = max(map(abs, chunk), default=0)
    crossings = []
    for k in range(480, len(chunk) - 480):
        if chunk[k] <= 0 < chunk[k + 1]:
            crossings.append(k - chunk[k] / (chunk[k + 1] - chunk[k]))
    event["measured_frequency_hz"] = (
        96000 * (len(crossings) - 1) / (crossings[-1] - crossings[0])
        if len(crossings) > 1
        else None
    )
    event["observed_nonzero_samples"] = sum(v != 0 for v in chunk)
report = {
    "events": events,
    "capture_mode": meta.get("capture_mode", "unspecified"),
    "frames": len(frames),
    "finite": all(map(math.isfinite, source)),
    "peak": max(map(abs, source)),
    "capture": str(capture),
    "capture_sha256": hashlib.sha256(
        (capture / "controls.dtfr").read_bytes()
    ).hexdigest(),
    "source_sha256": source_hashes(),
    "input_event_mask": 1,
    "blob_sha256": hashlib.sha256((out / "SINE_BLOB.bin").read_bytes()).hexdigest(),
    "pcm_sha256": hashlib.sha256(audio.tobytes()).hexdigest(),
    "boundary": "CPU capture frames with other-track event bits masked; track-1 control words unchanged. 150-frame preroll and 500-frame stable tail. One transaction per DSP block; emulated timing. Track-1 voice buffer, not final mix.",
}
(out / "render.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2), flush=True)
