"""Bounded replay construction with explicit event and input provenance."""

import struct
from pathlib import Path

from lab.project import require

EVENTS = (0x22, 0x24, 0x26, 0x28)


def write_frames(path, frames):
    require(1 <= len(frames) <= 32768, "Replay count outside bounds")
    require(all(0x96 <= len(f) <= 4096 for f in frames), "Invalid wire extent")
    raw = b"DTFR\x01\0\0\0" + struct.pack("<I", len(frames))
    raw += b"".join(struct.pack("<I", len(f)) + f for f in frames)
    Path(path).write_bytes(raw)


def trigger_mask(frames):
    mask = 0
    for frame in frames:
        mask |= int.from_bytes(frame[0x22:0x24], "big")
    return mask


def fixed_replay(frames, count):
    require(128 <= count <= 512, "Replay must contain 128..512 blocks")
    require(bool(frames), "Empty source capture")
    require(
        all(frames[-1][o : o + 2] == b"\0\0" for o in EVENTS),
        "Tail has a one-shot event",
    )
    replay = list(frames[:count])
    require(
        trigger_mask(replay) == trigger_mask(frames),
        "Replay truncates a requested track trigger",
    )
    # Never truncate a note-off/other one-shot event either.
    require(
        not any(any(f[o : o + 2] != b"\0\0" for o in EVENTS) for f in frames[count:]),
        "Replay truncates an event",
    )
    replay += [frames[-1]] * (count - len(replay))
    return replay


def track_one_clip(frames, start, count, *, preroll=32):
    """Explicit derived input: isolate event masks, retain every parameter byte."""
    require(128 <= count <= 512, "Replay must contain 128..512 blocks")
    require(
        start > 0 and start + count - preroll <= len(frames), "Clip outside capture"
    )
    require(0 < preroll < count, "Invalid preroll")

    def isolate(frame):
        result = bytearray(frame)
        for offset in EVENTS:
            result[offset : offset + 2] = (
                int.from_bytes(frame[offset : offset + 2], "big") & 1
            ).to_bytes(2, "big")
        return bytes(result)

    before = isolate(frames[start - 1])
    require(
        all(before[o : o + 2] == b"\0\0" for o in EVENTS), "Preroll contains an event"
    )
    result = [before] * preroll + [
        isolate(f) for f in frames[start : start + count - preroll]
    ]
    require(trigger_mask(result) == 1, "Missing track-one trigger")
    return result
