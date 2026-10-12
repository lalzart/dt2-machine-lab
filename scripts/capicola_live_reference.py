"""Independent composition oracle for the frozen R3 live-control policy."""

import copy
import math

from capicola_stretch_reference import Reader, f32


class LiveReader:
    def __init__(self, reader):
        self.current = reader
        self.outgoing = None
        self.fade_left = 0
        self.pending = None

    def transition(self):
        start, end, reverse, loop, pitch, advance = self.pending
        old = self.current
        x = old.ideal % (old.end - old.start) if old.loop else old.ideal
        absolute = min(end - 1, max(start, old.mapped(x)))
        new = Reader(
            old.values,
            old.times,
            old.frames,
            start,
            end,
            reverse,
            loop,
            pitch,
            advance,
            old.leash,
        )
        relative = end - 1 - absolute if reverse else absolute - start
        new.ideal = new.actual = new.incoming = relative
        new.position = 48
        if not loop:
            new.duration = 48 + math.ceil((end - start - relative) / new.rate)
        self.outgoing = copy.copy(old)
        self.current = new
        self.pending = None
        self.fade_left = 64

    def update(self, start, end, reverse, loop, pitch, advance):
        c = self.current
        if not c.active and not self.fade_left:
            self.pending = None
            return
        c.update(pitch, advance)
        if self.fade_left:
            self.outgoing.update(pitch, advance)
        requested = (start, end, reverse, loop, pitch, advance)
        self.pending = (
            requested if requested[:4] != (c.start, c.end, c.reverse, c.loop) else None
        )
        if self.pending and not self.fade_left and c.active:
            self.transition()

    def process(self, frames):
        out = []
        for _ in range(frames):
            if self.pending and not self.fade_left and self.current.active:
                self.transition()
            y = self.current.tick()
            if self.fade_left:
                t = f32((64 - self.fade_left) * f32(1 / 63))
                weight = f32(f32(t * t) * f32(3 - f32(2 * t)))
                y = self.outgoing.tick() * (1 - weight) + y * weight
                self.fade_left -= 1
            out.append(y)
        return out
