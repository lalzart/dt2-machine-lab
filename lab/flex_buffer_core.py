"""Bounded host oracle for project-scoped logical recording buffers.

No DSP pointers, native identity recycling, save implementation or memory
reclamation is implied. Retired generations deliberately remain quarantined.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    epoch: int
    destination: int
    track: int
    kit: int
    ticket: int


@dataclass(frozen=True)
class Generation:
    epoch: int
    number: int
    slot: int
    size: int
    frames: int


class Buffers:
    def __init__(self, *, max_generations=8, max_bytes=4 * 1024 * 1024):
        self.epoch = 1
        self.max_generations, self.max_bytes = max_generations, max_bytes
        self.generations = []
        self.current = [None] * 4
        self.recording = None
        self.tickets = 0

    @property
    def occupied(self):
        return sum(g.size for g in self.generations)

    def begin(self, destination, track, kit):
        if not 1 <= destination <= 4 or not 0 <= track < 16:
            raise ValueError("Invalid recording destination")
        if self.recording is not None:
            raise ValueError("Candidate already recording")
        self.tickets += 1
        self.recording = Candidate(self.epoch, destination, track, kit, self.tickets)
        return self.recording

    def cancel(self):
        self.recording = None

    def admit(self, candidate, size):
        if candidate != self.recording or candidate.epoch != self.epoch:
            raise ValueError("Recording belongs to an earlier project")
        if size <= 0 or self.occupied + size > self.max_bytes:
            raise ValueError("Buffer memory full; previous audio retained")
        if len(self.generations) >= self.max_generations:
            raise ValueError("Generation limit; previous audio retained")

    def commit(self, candidate, generation, *, complete):
        self.admit(candidate, generation.size)
        if not complete or generation.epoch != self.epoch:
            raise ValueError("Incomplete recording publication")
        if generation.number in {g.number for g in self.generations}:
            raise ValueError("Generation identity already issued")
        old = self.current[candidate.destination - 1]
        self.generations.append(generation)
        self.current[candidate.destination - 1] = generation
        self.recording = None
        return old

    def project_change(self):
        self.epoch += 1
        self.current = [None] * 4
        self.recording = None

    def status(self, destination):
        if self.recording and self.recording.destination == destination:
            return "RECORDING"
        return "READY" if self.current[destination - 1] else "EMPTY"

    def save_allowed(self, referenced_slots, buffer_slots):
        if set(referenced_slots) & set(buffer_slots):
            raise ValueError("VOLATILE BUFFERS: PROJECT NOT SAVED")
        return True
