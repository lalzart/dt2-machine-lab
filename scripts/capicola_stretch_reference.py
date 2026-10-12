"""Independent floating-position model of the frozen STRETCH R1 equations.

Reads immutable key arrays, never calls the C reader. Positions use binary64;
only the crossfade accumulator uses binary32, as the source algorithm does.
"""

import bisect
import math
import struct

Q = 2**24


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


class Reader:
    def __init__(
        self,
        values,
        times,
        frames,
        start,
        end,
        reverse,
        loop,
        pitch,
        advance,
        leash=128,
    ):
        self.values, self.times, self.frames = values, times, frames
        self.start, self.end = start, end
        self.reverse, self.loop, self.leash = reverse, loop, leash
        self.ideal = self.actual = self.incoming = self.phase = 0.0
        self.increment = 0.0
        self.splicing = False
        self.position = 0
        self.active = True
        self.first = bisect.bisect_left(times, start)
        self.last = bisect.bisect_left(times, end)
        self.keys = times[self.first : self.last]
        self.duration = 0
        self.update(pitch, advance)

    def update(self, pitch, advance):
        self.pitch = f32(pitch)
        self.rate = math.floor(f32(advance) * Q) / Q
        self.pitch_rate = math.floor(self.pitch * Q) / Q
        if not self.loop:
            self.duration = self.position + math.ceil(
                (self.end - self.start - self.ideal) / self.rate
            )

    def mapped(self, x):
        return self.end - 1 - x if self.reverse else self.start + x

    def window(self, x):
        return min(len(self.times) - 1, max(1, bisect.bisect_left(self.times, x)))

    def rank(self, x):
        if not self.loop:
            k = self.window(self.mapped(x))
            return len(self.times) - 1 - k if self.reverse else k
        cycle, x = divmod(x, self.end - self.start)
        if not self.keys:
            return int(cycle)
        # Search ascending event times in the direction of playback.
        if self.reverse:
            ordinal = len(self.keys) - bisect.bisect_right(self.keys, self.mapped(x))
        else:
            ordinal = bisect.bisect_left(self.keys, self.mapped(x))
        return int(cycle) * len(self.keys) + ordinal

    def key(self, rank):
        if self.loop:
            if not self.keys:
                return rank * (self.end - self.start)
            cycle, ordinal = divmod(rank, len(self.keys))
            time = self.keys[-1 - ordinal] if self.reverse else self.keys[ordinal]
        else:
            cycle = 0
            index = len(self.times) - 1 - rank if self.reverse else rank
            time = self.times[min(len(self.times) - 1, max(0, index))]
        return (self.end - 1 - time if self.reverse else time - self.start) + cycle * (
            self.end - self.start
        )

    def sample(self, x):
        if self.loop:
            x %= self.end - self.start
        elif not 0 <= x < self.end - self.start:
            return 0.0
        physical = self.mapped(x)
        if not 0 <= physical < self.frames:
            return 0.0
        index = self.window(physical)
        duration = self.times[index] - self.times[index - 1]
        t = (
            max(0.0, min(1.0, (self.times[index] - physical) / duration))
            if duration > 1e-5
            else 0.0
        )
        result = ((2 * t - 3) * t * t + 1) * self.values[index] + (
            (-2 * t + 3) * t * t
        ) * self.values[index - 1]
        if self.loop:
            result *= max(0.0, min(1.0, x / 48, (self.end - self.start - 1 - x) / 48))
        return result

    def tick(self):
        if not self.active:
            return 0.0
        grid, actual = self.rank(self.ideal), self.rank(self.actual)
        if not self.splicing and abs(actual - grid) > self.leash:
            self.incoming = self.ideal
            if self.actual < self.ideal:
                duration = self.key(grid - 1) - self.key(grid - self.leash)
            else:
                duration = self.key(grid + self.leash - 1) - self.key(grid - 1)
            self.increment = f32(1 / max(48.0, min(960.0, duration)))
            self.phase, self.splicing = 0.0, True
        self.ideal += self.rate
        if self.splicing and self.phase <= 1:
            weight = self.phase * self.phase * (3 - 2 * self.phase)
            result = self.sample(self.incoming) * weight + self.sample(self.actual) * (
                1 - weight
            )
            self.actual += self.pitch_rate
            self.incoming += self.pitch_rate
            self.phase = f32(self.phase + f32(self.increment * self.pitch))
        else:
            if self.splicing:
                self.actual = self.incoming
                self.phase, self.splicing = 0.0, False
            result = self.sample(self.actual)
            self.actual += self.pitch_rate
        if self.loop:
            if not self.splicing:
                self.incoming = self.actual
            shift = math.floor(self.ideal / (self.end - self.start)) * (
                self.end - self.start
            )
            self.ideal -= shift
            self.actual -= shift
            self.incoming -= shift
        edge = min(1.0, self.position / 48)
        if self.loop:
            self.position = min(48, self.position + 1)
        else:
            edge = max(0.0, min(edge, (self.duration - 1 - self.position) / 48))
            self.position += 1
            self.active = self.position < self.duration
        return result * edge

    def process(self, frames):
        return [self.tick() for _ in range(frames)]
