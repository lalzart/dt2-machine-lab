"""Bounded WAV input model for the emulator's completed-recording service.

No microphone, filesystem writes, GUI or firmware imports. PCM is big-endian
interleaved int16, as requested by the original OS 1.16 chunk wrapper.
"""

import array
import struct
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

RATE = 48000
MAX_FRAMES = RATE * 10
MIN_FRAMES = 141


@dataclass(frozen=True)
class Take:
    pcm: bytes
    stereo: bool

    def __post_init__(self):
        if len(self.pcm) % self.width or not MIN_FRAMES <= self.frames <= MAX_FRAMES:
            raise ValueError("Choose 141..480000 complete audio frames")

    @property
    def width(self):
        return 4 if self.stereo else 2

    @property
    def frames(self):
        return len(self.pcm) // self.width

    def trim(self, start, end):
        if not 0 <= start < end <= self.frames:
            raise ValueError("Trim outside recorded audio")
        return Take(self.pcm[start * self.width : end * self.width], self.stereo)

    @classmethod
    def from_wav(cls, path):
        with wave.open(str(Path(path)), "rb") as wav:
            if (wav.getframerate(), wav.getsampwidth(), wav.getcomptype()) != (
                RATE,
                2,
                "NONE",
            ) or wav.getnchannels() not in (1, 2):
                raise ValueError("Input must be 48 kHz PCM16 mono or stereo WAV")
            if not MIN_FRAMES <= wav.getnframes() <= MAX_FRAMES:
                raise ValueError("Input must be at most 10 seconds")
            words = array.array("h", wav.readframes(wav.getnframes()))
            if sys.byteorder == "little":
                words.byteswap()
            return cls(words.tobytes(), wav.getnchannels() == 2)


class RecorderInput:
    def __init__(self, source):
        self.source = source
        self.completed = None
        self.active = False
        self.started = 0
        self.captured = 0
        self.requests = []

    def begin(self, clock):
        if self.active:
            raise ValueError("Already recording")
        self.completed = None
        self.captured = 0
        self.started = clock
        self.active = True

    def count(self, clock):
        if self.active:
            self.captured = min(
                self.source.frames, max(1, ((clock - self.started) & 0xFFFFFFFF) // 2)
            )
        return self.captured

    def finish(self, clock):
        self.count(clock)
        self.active = False
        # Empty/short recordings stay cancellable, but cannot be accepted.
        self.completed = self.source.pcm[: self.captured * self.source.width]

    def discard(self):
        self.active = False
        self.completed = None
        self.captured = 0

    def candidate(self, start, end):
        if self.active or self.completed is None:
            raise ValueError("Finish recording before USE")
        if not 0 <= start < end <= self.captured:
            raise ValueError("Trim outside completed recording")
        return Take(
            self.completed[start * self.source.width : end * self.source.width],
            self.source.stereo,
        )

    def chunk(self, start, count, mono):
        if self.active or self.completed is None:
            raise ValueError("PCM requested before recording finished")
        if bool(mono) != (not self.source.stereo):
            raise ValueError("Recorder channel mode differs from input")
        if (
            not 0 <= start <= start + count <= self.captured
            or count * self.source.width > 0x800
        ):
            raise ValueError(
                "Recorder request outside completed PCM or response capacity"
            )
        self.requests.append((start, count, mono))
        return self.completed[
            start * self.source.width : (start + count) * self.source.width
        ]

    def extrema(self, start, end):
        limit = self.captured if self.completed is not None else self.source.frames
        start, end = max(0, start), min(end, limit)
        if start >= end:
            return bytes(16)
        data = self.completed if self.completed is not None else self.source.pcm
        words = struct.unpack(
            f">{(end - start) * self.source.width // 2}h",
            data[start * self.source.width : end * self.source.width],
        )
        lanes = (words[::2], words[1::2]) if self.source.stereo else (words, words)
        # The native draw consumer compares signed longs and scales by the
        # largest absolute peak (0x40022b8a / 0x4001ff36), not IEEE floats.
        return struct.pack(
            ">4i", *(v for lane in lanes for v in (min(lane), max(lane)))
        )
