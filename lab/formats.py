"""Bounded DTFR reader for the captured control stream."""

import struct
from pathlib import Path

from lab.project import require


def read_frames(path):
    raw = Path(path).read_bytes()
    require(len(raw) >= 12 and raw[:8] == b"DTFR\x01\0\0\0", "Not a DTFR v1 capture")
    count = struct.unpack_from("<I", raw, 8)[0]
    require(1 <= count <= 4096, "DTFR frame count outside 1..4096")
    frames, offset = [], 12
    for _ in range(count):
        require(offset + 4 <= len(raw), "Truncated DTFR frame header")
        size = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        require(0x96 <= size <= 4096, "Invalid DTFR control-frame size")
        require(offset + size <= len(raw), "Truncated DTFR frame payload")
        frames.append(raw[offset : offset + size])
        offset += size
    require(offset == len(raw), "Trailing DTFR data")
    return frames
