# ruff: noqa: E402
"""Render a verified pattern's two PLAY loops through the actual SHARC firmware."""

import argparse
import array
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("capture", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--play", action="store_true")
args = p.parse_args()
doctor()
capture = args.capture.resolve()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.formats import read_frames
from lab.pattern_dsp import PatternDsp, check_fext
from lab.runtime import STOCK_BLOB

meta = json.loads((capture / "capture.json").read_text())
interactive = meta.get("mode") == "interactive"
require(
    meta["status"] == ("captured" if interactive else "passed"), "Capture did not pass"
)
require(
    sha256(capture / "pattern.dtfr") == meta["capture_sha256"], "Capture hash changed"
)
raw = read_frames(capture / "pattern.dtfr", max_frames=32768)
phase = meta["passes"][0]
start, end = phase["render_start"], phase["render_end"]
require(0 < start < end <= len(raw), "Invalid render range")
require(len(meta["ticks"]) == len(raw), "Frame/tick count mismatch")
require(
    all(
        (b - a) & 0xFFFFFFFF == 32
        for a, b in zip(
            meta["ticks"][start : end - 1], meta["ticks"][start + 1 : end], strict=True
        )
    ),
    "Capture clock discontinuity",
)


def isolate(frame):
    f = bytearray(frame)
    for off in (0x22, 0x24, 0x26, 0x28):
        f[off : off + 2] = (int.from_bytes(f[off : off + 2], "big") & 1).to_bytes(
            2, "big"
        )
    return bytes(f)


preroll = isolate(raw[start - 1])
require(
    all(preroll[o : o + 2] == b"\0\0" for o in (0x22, 0x24, 0x26, 0x28)),
    "Preroll contains an event",
)
frames = [preroll] * 150 + [isolate(f) for f in raw[start:end]]
trigger_indices = [
    i for i, f in enumerate(frames) if int.from_bytes(f[0x22:0x24], "big") & 1
]
require(
    bool(trigger_indices) if interactive else len(trigger_indices) == 8,
    "Expected audible note events",
)
if meta["machine"] == "plaits":
    from lab.plaits import build_blob

    blob = build_blob(True, family="controls", output=out / "firmware")
else:
    blob = STOCK_BLOB.read_bytes()
fingerprint = source_hashes()
fext_cases = check_fext()
report = {
    "capture": str(capture),
    "capture_sha256": meta["capture_sha256"],
    "source_sha256": fingerprint,
    "blob_sha256": hashlib.sha256(blob).hexdigest(),
    "frames": len(frames),
    "preroll_frames": 150,
    "fext_state_cases": fext_cases,
    "events": trigger_indices,
    "boundary": "Actual SHARC voice buffers, track-1 event isolation; completed WAV, no final mix, real-time or hardware claim.",
}
started = time.monotonic()


def render(label):
    dsp = PatternDsp(blob)
    audio = array.array("f")
    for i, f in enumerate(frames):
        audio.extend(dsp.frame(f))
        if i % 1000 == 0:
            print(label, i, "/", len(frames), flush=True)
    require(all(map(math.isfinite, audio)), "Nonfinite audio")
    require(0 < max(map(abs, audio)) < 1, "Silent or clipping audio")
    return audio, dsp


try:
    audio, dsp = render("render")
    repeat, _ = render("repeat")
    require(audio.tobytes() == repeat.tobytes(), "Exact replay mismatch")
    peaks = []
    for j, a in enumerate(trigger_indices):
        b = trigger_indices[j + 1] if j + 1 < len(trigger_indices) else len(frames)
        peak = max(map(abs, audio[a * 64 : b * 64]))
        require(peak > 1e-7, "Silent note interval")
        peaks.append(peak)
    (out / "pattern.f32").write_bytes(audio.tobytes())
    pcm = array.array("h", (round(x * 32767) for x in audio))
    if sys.byteorder != "little":
        pcm.byteswap()
    with wave.open(str(out / "pattern.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(pcm.tobytes())
    require(source_hashes() == fingerprint, "Source changed during render")
    report.update(
        status="passed",
        exact_repeat=True,
        fext_fallbacks=dict(dsp.fallbacks),
        native_library_sha256=sha256(dsp.library),
        note_interval_peaks=peaks,
        peak=max(map(abs, audio)),
        pcm_sha256=sha256(out / "pattern.f32"),
        wav_sha256=sha256(out / "pattern.wav"),
        audio_seconds=len(audio) / 96000,
        wall_seconds=time.monotonic() - started,
    )
except BaseException as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    write_json(out / "render.json", report)
if args.play:
    subprocess.run(["afplay", str(out / "pattern.wav")], check=True, timeout=30)
