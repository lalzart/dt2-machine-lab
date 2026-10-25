"""Host-only lifecycle controls for the isolated DSP-memory investigation.

These guards are an experiment oracle, not firmware synchronization. Tokens
are never sample IDs. A new token cannot make an old reader disappear.
"""

from dataclasses import dataclass, field


@dataclass
class Buffer:
    capacity: int
    generation: int = 0
    epoch: int = 0
    state: str = "free"
    expected: int = 0
    pages: set = field(default_factory=set)
    readers: int = 0
    roots: int = 0


class DoubleBuffer:
    def __init__(self, capacities):
        self.buffers = [Buffer(n) for n in capacities]
        self.epoch = 1
        self.selected = None

    def _get(self, token, *, current=True):
        epoch, index, generation = token
        item = self.buffers[index]
        if (item.epoch, item.generation) != (epoch, generation):
            raise ValueError("Stale generation")
        if current and epoch != self.epoch:
            raise ValueError("Stale project")
        return item

    def begin(self, index, pages):
        item = self.buffers[index]
        if item.state != "free" or item.readers or item.roots:
            raise ValueError("Buffer still owned")
        if not 0 < pages * 4096 <= item.capacity:
            raise ValueError("Workspace exhausted")
        item.generation += 1
        item.epoch = self.epoch
        item.state, item.expected = "writing", pages
        item.pages.clear()
        return self.epoch, index, item.generation

    def page(self, token, index):
        item = self._get(token)
        if item.state != "writing" or not 0 <= index < item.expected:
            raise ValueError("Unexpected page")
        item.pages.add(index)

    def commit(self, token):
        item = self._get(token)
        if item.state != "writing" or len(item.pages) != item.expected:
            raise ValueError("Incomplete publication")
        item.state = "ready"

    def select(self, token):
        item = self._get(token)
        if item.state != "ready":
            raise ValueError("Unpublished selection")
        if self.selected == token:
            return
        if self.selected is not None:
            self._get(self.selected).roots -= 1
        item.roots += 1
        self.selected = token

    def pin(self, token):
        item = self._get(token)
        if item.state != "ready":
            raise ValueError("Unpublished reader")
        item.readers += 1

    def unpin(self, token):
        item = self._get(token, current=False)
        if item.readers == 0:
            raise ValueError("Unbalanced reader")
        item.readers -= 1

    def retire(self, token):
        item = self._get(token, current=False)
        if item.readers or item.roots:
            raise ValueError("Buffer still owned")
        item.state = "free"

    def project_change(self):
        # Models explicit release of this experiment's single project root.
        # It does not claim all real pattern/undo/clipboard roots are known.
        if self.selected is not None:
            self._get(self.selected).roots -= 1
        self.selected = None
        self.epoch += 1


def control(wire, slot, *, trigger=False):
    """Same controlled ONESHOT fields as probe-flex-lite, track 1 only."""
    import struct

    result = bytearray(wire)
    for offset, value in {
        0: 3,
        2: 0x3C00,
        0x22: int(trigger),
        0x24: 0,
        0x26: 0,
        0x28: 0,
        0x2A: 0,
        0x94: 0,
        0xDA: 0x4000,
        0xDC: 0x300,
        0xDE: 0,
        0xE0: slot,
        0xE6: 0,
        0xE8: 0x7800,
        0xEA: 0,
        0xEC: 0x6400,
    }.items():
        struct.pack_into(">H", result, offset, value)
    return bytes(result)
