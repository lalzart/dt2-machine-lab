"""Opt-in emulator FREEZE alias experiment. No gesture or target build hook.

The stock CPU cache supplies an existing allocation; only a new slot header
crosses LP0. Metadata resolution and conservative lifetime pins are host-side.
"""

import struct
from dataclasses import asdict, dataclass

from lab.flex_buffer_ui import BufferUI
from lab.project import require


class MetadataOnly(dict):
    """A retired source can identify a cache hit, but cannot provide PCM."""

    def __getitem__(self, key):
        require(key != "data", "Retired PCM unavailable: native readback required")
        return super().__getitem__(key)


@dataclass(frozen=True)
class Frozen:
    epoch: int
    identity: int
    name: str
    slot: int
    buffer: int
    generation: int
    frames: int
    stereo: bool
    start: int
    size: int


class FreezeUI(BufferUI):
    def __init__(self, *args, **kwargs):
        self.snapshots = []
        self.metadata = {}
        self.freeze_limit = 8
        self.freeze_fault = None
        self.aliases = []
        super().__init__(*args, **kwargs)

    def install(self, main):
        super().install(main)
        self.original_source = self.fw.get_source

        def get_source(identity):
            if identity in self.metadata:
                return self.metadata[identity]
            return self.original_source(identity)

        self.fw.get_source = get_source

    def _names(self):
        super()._names()
        for snapshot in self.snapshots:
            address = 0x405B6368 + snapshot.slot * 16
            self.fw.write(address, snapshot.name.encode().ljust(16, b"\0"))
            self.fw.write(0x405BC768 + snapshot.slot * 4, struct.pack(">I", address))

    def extra_hook(self, uc, pc, *args):
        from unicorn import m68k_const as k

        fw = self.fw
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        # Frozen references are just as volatile as live buffers. This includes
        # snapshots whose source buffer has since been cleared or invalidated.
        if pc == 0x40043A30 and self.snapshots:
            self.error = "VOLATILE SNAPSHOTS: PROJECT NOT SAVED"
            self.record_event("snapshot-project-save-blocked")
            self.returned(0)
            return
        if pc in (0x40154540, 0x401540C6, 0x40153BEA) and not fw.direct:
            slot = fw.u32(sp + (8 if pc == 0x40154540 else 4))
            if slot in {s.slot for s in self.snapshots}:
                self.record_event("frozen-slot-guard", pc=hex(pc), slot=slot)
                self.returned(-1 if pc == 0x40154540 else 0)
                return
        if pc == 0x401537A8:
            slot = fw.u32(sp + 4)
            if slot in {s.slot for s in self.snapshots}:
                self.returned(0x405B6368 + slot * 16)
                return
        if pc == 0x401137A4:
            pointer = fw.u32(sp + 28)
            if 0x40000000 <= pointer < 0x50000000:
                value = fw.read(pointer, 32).split(b"\0")[0]
                if any(s.name.encode() in value for s in self.snapshots):
                    self.selector_names.append(
                        dict(text=value.decode("ascii"), kind="frozen-selector-row")
                    )
        super().extra_hook(uc, pc, *args)

    def freeze(self, destination, *, expected_epoch=None):
        """Called at a paused worker boundary, not through a claimed native key.

        A pending candidate is irrelevant: freeze the last committed version.
        All old allocations remain pinned. There is no reclaimer in this probe.
        """
        import plusdrive_check as check

        fw = self.fw
        require(self.setup_done and 1 <= destination <= 4, "Invalid buffer")
        require(not self.project_transition_blocked, "Project changed: restart session")
        require(
            expected_epoch in (None, self.buffers.epoch), "Stale FREEZE project handle"
        )
        generation = self.buffers.current[destination - 1]
        require(generation is not None, "Cannot FREEZE an empty buffer")
        require(
            len(self.snapshots) < self.freeze_limit, "Snapshot limit; audio retained"
        )
        ref = self.generation_refs[generation.number]
        identity = int.from_bytes(ref[:4], "big")
        require(identity not in fw.sources, "FREEZE requires retired source PCM")
        info = next(g for g in self.retained if g["generation"] == generation.number)
        with fw.transaction():
            pool = self.project_pool()
            # The stock empty-reference sentinel is the identity word; the
            # unused tail is not necessarily erased. Check both owners.
            slots = [
                slot
                for slot in range(1, 1024)
                if slot % 128
                and slot not in self.buffer_slots + self.private_slots
                and fw.slot(slot)["empty"]
                and fw.read(pool + slot * 16, 4) == b"\xff" * 4
            ]
            require(slots, "No empty Project RAM slot; audio retained")
            slot = slots[0]
            require(
                self.freeze_fault != "allocation",
                "Injected snapshot allocation failure",
            )
            before = fw.slot(generation.slot)
            if self.freeze_fault != "missing-metadata":
                self.metadata[identity] = MetadataOnly(ref=ref, name="RAM-ALIAS")
            events_before = len(fw.source_events)
            alias = check.check_load(fw, ref, slot)
            packets = list(fw.pages)
            after = fw.slot(slot)
            require(alias["load_d0"] == 0, "Stock alias load failed")
            require(alias["data_pages"] == 0, "FREEZE copied PCM pages")
            require(
                all(tag == 0xFFFFFFFF for tag, _, _ in packets),
                "FREEZE emitted sample data",
            )
            require(
                not fw.handles
                and not any(
                    e[0] in ("open", "read") for e in fw.source_events[events_before:]
                ),
                "FREEZE reopened retired PCM",
            )
            require(
                all(after[k] == before[k] for k in ("block_index", "start", "size")),
                "FREEZE created a different allocation",
            )
            serial = len(self.snapshots) + 1
            snapshot = Frozen(
                self.buffers.epoch,
                0x7FFC0000 + serial,
                f"B{destination}-{serial:03d}",
                slot,
                destination,
                generation.number,
                generation.frames,
                info["stereo"],
                after["start"],
                after["size"],
            )
            # New project identity, original loader key. Native persistence is
            # blocked; this is not a durable or reopenable sample reference.
            fw.write(
                pool + slot * 16,
                struct.pack(
                    ">4I", snapshot.identity, snapshot.epoch, generation.number, 0
                ),
            )
            self.snapshots.append(snapshot)
            self.aliases.append(
                dict(
                    slot=slot,
                    loader={
                        key: alias[key]
                        for key in (
                            "load_d0",
                            "data_pages",
                            "slot_headers",
                            "len",
                            "rate",
                            "stereo",
                        )
                    },
                    loader_key=alias["key"].hex(),
                    source_events=fw.source_events[events_before:],
                )
            )
            self.pages.extend(packets)
            self._names()
            self.record_event("freeze", **asdict(snapshot), pcm_pages=0)
            return snapshot
