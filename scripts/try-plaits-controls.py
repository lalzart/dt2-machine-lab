# ruff: noqa: E402
"""Build, capture, check and audition dedicated Plaits macros on the prepared emulator."""

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
p.add_argument("output", type=Path)
p.add_argument(
    "--capture",
    type=Path,
    help="Use an existing passing controls capture instead of recording a fresh one",
)
p.add_argument(
    "--checks-only",
    action="store_true",
    help="CPU and compiled adapter checks, without CPU capture or firmware replay",
)
p.add_argument(
    "--play",
    action="store_true",
    help="Play the completed WAV through the Mac after verification",
)
p.add_argument(
    "--regenerate-header",
    action="store_true",
    help="Regenerate adapter constants from the locked control map before checking",
)
args = p.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use a fresh out/runs directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
from lab.dsp import Dsp
from lab.formats import read_frames
from lab.plaits import build_blob, build_cpu
from lab.plaits_controls import control_header, validate_sources
from lab.plaits_controls_checks import adapter_checks, cpu_checks

if args.regenerate_header:
    machine = ROOT / "machines/plaits-controls"
    control = json.loads((machine / "controls.json").read_text())
    (machine / "controls.h").write_text(control_header(control))
lock = validate_sources()
doctor()
fingerprint = source_hashes()
report = {
    "source_sha256": fingerprint,
    "source_lock": lock,
    "cpu_load_percent": None,
    "dsp_load_percent": None,
    "boundary": "Prepared CPU checkpoint and executed SHARC voice buffers; buffered audition, no final mixer, hardware timing or clean startup proof.",
}
started = time.monotonic()


def pcm(values):
    require(bool(values) and all(map(math.isfinite, values)), "Invalid PCM")
    return array.array("f", values).tobytes()


def wav(name, values):
    raw = pcm(values)
    (out / (name + ".f32")).write_bytes(raw)
    require(max(map(abs, values)) < 1, "Audio exceeds unity; refuse clipping")
    with wave.open(str(out / (name + ".wav")), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(48000)
        f.writeframes(array.array("h", (round(v * 32767) for v in values)).tobytes())
    return hashlib.sha256(raw).hexdigest()


def isolate(frame):
    f = bytearray(frame)
    for off in (0x22, 0x24, 0x26, 0x28):
        f[off : off + 2] = (int.from_bytes(f[off : off + 2], "big") & 1).to_bytes(
            2, "big"
        )
    return bytes(f)


def replay(blob, frames):
    e = Dsp(blob)
    audio = []
    events = []
    previous = 0
    for i, f in enumerate(frames):
        audio.extend(e.frame(f))
        age = e.core.peek(0x200E1000 + 328)
        if age and (not previous or age < previous):
            events.append(i)
        previous = age
    return audio, events


def render_capture(blob, capture):
    meta = json.loads((capture / "capture.json").read_text())
    require(meta["status"] == "passed", "Capture did not pass")
    require(
        meta["cpu_candidate"]["sha256"] == report["cpu_candidate"]["sha256"],
        "Capture CPU differs",
    )
    require(sha256(capture / "macros.dtfr") == meta["capture_sha256"], "Capture drift")
    raw = read_frames(capture / "macros.dtfr")
    start, end = meta["preview_start"], meta["preview_end"]
    frames = [
        isolate(f)
        for f in [raw[start - 1]] * 150 + raw[start:end] + [raw[end - 1]] * 350
    ]
    require(
        all(
            f[o : o + 2] == b"\0\0"
            for f in (frames[0], frames[-1])
            for o in (0x22, 0x24, 0x26, 0x28)
        ),
        "Padding has events",
    )
    print("Replaying genuine macro locks", len(frames), "frames", flush=True)
    audio, events = replay(blob, frames)
    require(len(events) == 5, "Expected five audible lock/base events")
    repeat, _ = replay(blob, frames)
    require(pcm(audio) == pcm(repeat), "Firmware repeat differs")
    spans = []
    for first, second in ((0, 3), (2, 4)):
        # With live macros, releasing a held trig changes the input before
        # the next note. Compare only the matching complete-control prefix.
        limit = min(
            events[first + 1] - events[first],
            (events[second + 1] if second + 1 < len(events) else len(frames))
            - events[second],
        )
        count = 0
        for n in range(limit):
            a, b = frames[events[first] + n], frames[events[second] + n]
            if any(
                a[o : o + 2] != b[o : o + 2]
                for o in (
                    0x02,
                    0x22,
                    0x24,
                    0x26,
                    0x28,
                    0x94,
                    0xDA,
                    0xDC,
                    0xDE,
                    0xE0,
                    0xE6,
                    0xE8,
                    0xEC,
                )
            ):
                break
            count += 1
        require(count >= 4, "No useful matching-input recall interval")
        span = count * 64
        aa = audio[events[first] * 64 : events[first] * 64 + span]
        bb = audio[events[second] * 64 : events[second] * 64 + span]
        require(pcm(aa) == pcm(bb), "Lock/base audio recall differs")
        spans.append(span)
    import sharcldr

    disabled = bytearray(blob)
    offset = sharcldr.offset_for_address(sharcldr.parse_blocks(blob), 0x1C4F15)
    disabled[offset : offset + 6] = bytes.fromhex("5499a801408c")
    short = frames[: events[0] + 40]
    stock = [bytearray(f) for f in short]
    for f in stock:
        f[0x94:0x96] = b"\0\6"
    aa, _ = replay(blob, stock)
    bb, _ = replay(bytes(disabled), stock)
    require(pcm(aa) == pcm(bb), "Stock hook parity failed")
    negative, _ = replay(bytes(disabled), short)
    require(
        pcm(negative) != pcm(audio[: len(negative)]), "Disabled hook negative failed"
    )
    # Audition separately held genuine captured trigger/tail frames; no macro
    # substitution. Each note is allowed to finish before the next preview.
    listen = []
    for event in meta["previews"][:3]:
        i = event["frame"]
        before = isolate(raw[i - 1])
        trigger = isolate(raw[i])
        tail = isolate(raw[i + 1])
        require(
            all(tail[o : o + 2] == b"\0\0" for o in (0x22, 0x24, 0x26, 0x28)),
            "Audition tail has an event",
        )
        segment = [before] * 150 + [trigger] + [tail] * 400
        sound, detected = replay(blob, segment)
        require(
            len(detected) == 1 and max(map(abs, sound)) > 1e-4, "Audition event missing"
        )
        listen.extend(sound)
    i, j = meta["sustain_start"], meta["sustain_end"]
    segment = (
        [isolate(raw[i - 1])] * 150
        + [isolate(f) for f in raw[i:j]]
        + [isolate(raw[j - 1])] * 350
    )
    sustained, sevents = replay(blob, segment)
    require(len(sevents) == 1, "Sustained macro replay retriggered")
    frozen = [bytearray(f) for f in segment]
    macro = raw[i][0xDC:0xDE]
    for f in frozen[150:]:
        f[0xDC:0xDE] = macro
    constant, _ = replay(blob, frozen)
    require(pcm(sustained) != pcm(constant), "Captured sustained edit negative failed")
    listen.extend(sustained)
    report["capture"] = {
        "path": str(capture),
        "sha256": meta["capture_sha256"],
        "adaptation": "Lock replay: 150 preroll/350 held-tail frames; other-track event bits masked. Audition: A/B/base each uses genuine adjacent trigger and held tail for 400 frames; sustained edit retains the captured timeline. Parameter bytes unchanged except explicitly labeled frozen negative.",
    }
    report["firmware"] = {
        "frames": len(frames),
        "event_frames": events,
        "repeat_exact": True,
        "recall_equal_samples": spans,
        "stock_hook_exact": True,
        "disabled_hook_negative": True,
        "sustained_macro_negative": True,
        "raw_sequence_pcm_sha256": wav("macro-lock-sequence", audio),
        "audition_pcm_sha256": wav("plaits-controls", listen),
        "peak": max(map(abs, listen)),
    }


try:
    report["cpu_candidate"] = build_cpu(family="controls")
    report["cpu_checks"] = cpu_checks(out)
    blob = build_blob(True, family="controls", output=out / "firmware")
    report["adapter"] = adapter_checks(blob, out)
    if not args.checks_only:
        capture = args.capture.resolve() if args.capture else out / "capture"
        if not args.capture:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/capture-plaits-controls.py"),
                    str(capture),
                ],
                check=True,
                timeout=660,
            )
        render_capture(blob, capture)
    require(source_hashes() == fingerprint, "Source changed during run")
    report["status"] = "passed"
except BaseException as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    report["host_seconds"] = time.monotonic() - started
    report["outputs"] = {
        str(f.relative_to(out)): sha256(f)
        for f in out.rglob("*")
        if f.is_file() and f.suffix in (".wav", ".f32", ".bin")
    }
    write_json(out / "report.json", report)
if args.play and not args.checks_only:
    subprocess.run(["afplay", str(out / "plaits-controls.wav")], check=True)
print(
    json.dumps(
        {
            k: v
            for k, v in report.items()
            if k not in ("source_sha256", "source_lock", "outputs")
        },
        indent=2,
    )
)
