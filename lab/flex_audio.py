"""Buffered stock-SHARC audition of an accepted take and actual pad capture."""

import array
import hashlib
import math
import struct
from pathlib import Path

from lab.flex_lite import FlexDsp
from lab.formats import read_frames
from lab.project import require


def baseline_pages(path):
    raw = Path(path).read_bytes()
    require(len(raw) % 4100 == 0, "Incomplete baseline LP0 packet")
    result = []
    for i in range(0, len(raw), 4100):
        tag = struct.unpack_from("<I", raw, i)[0]
        header = tag == 0xFFFFFFFF
        width = 4 if header else 2
        data = raw[i + 4 : i + 4100]
        result.append(
            (
                tag,
                b"".join(data[j : j + width][::-1] for j in range(0, 4096, width)),
                int(header),
            )
        )
    return result


def render_pad(capture, lp0, pages, output):
    from live_gui_check import write_wav

    output = Path(output)
    output.mkdir(exist_ok=False)
    frames = read_frames(capture["path"])
    track = capture["track"]
    pcm_runs = []
    baseline = baseline_pages(lp0)
    for repeat in range(2):
        dsp = FlexDsp()
        dsp.publish(baseline)
        dsp.publish(pages)
        pcm = array.array("f")
        for f in frames:
            bases = [0x2412CC + v * 0x1D8 for v in (track * 2, track * 2 + 1)]
            active_before = [
                bool(dsp.core.peek(base) and dsp.core.peek(base + 0x1B8, 1))
                for base in bases
            ]
            dsp.frame(f)
            lanes = []
            for base, was_active in zip(bases, active_before, strict=True):
                active_now = bool(
                    dsp.core.peek(base) and dsp.core.peek(base + 0x1B8, 1)
                )
                if was_active or active_now:
                    words = [
                        dsp.core.peek(base + dsp.h.FIELD_WORK_BUFFER + j * 4)
                        for j in range(64)
                    ]
                    samples = struct.unpack("<64f", struct.pack("<64I", *words))
                    lanes.append(
                        [0.5 * (samples[j] + samples[j + 1]) for j in range(0, 64, 2)]
                    )
                else:
                    lanes.append([0.0] * 32)
            pcm.extend(v for pair in zip(*lanes, strict=True) for v in pair)
        require(all(map(math.isfinite, pcm)), "Nonfinite voice audio")
        require(max(map(abs, pcm)) > 0, "Accepted pad is silent")
        pcm_runs.append(pcm.tobytes())
        (output / f"voice-{repeat}.f32").write_bytes(pcm.tobytes())
    require(pcm_runs[0] == pcm_runs[1], "Pad exact repeat differs")
    write_wav(str(output / "voice.wav"), pcm, 48000)
    return {
        "path": str(output / "voice.wav"),
        "sha256": hashlib.sha256(pcm_runs[0]).hexdigest(),
        "exact_repeat": True,
        "peak": max(map(abs, pcm)),
        "frames": len(frames),
        "scope": "Actual panel-trigger control frames, original stock DSP, selected-track voice-buffer tap; not final mix or real time",
    }
