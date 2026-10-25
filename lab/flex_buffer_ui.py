"""Opt-in stock-panel Flex buffer prototype; resource orchestration is host-side.

Emitted ColdFire gives the unused ready-page C rotation a DEST cell/setter in
guest RAM. MON stays on its original E path. The source adapter, publication
transaction, selector names and save/epoch guards are emulator callbacks.
"""

import struct

from lab.flex_buffer_core import Buffers, Generation
from lab.flex_recorder import MAX_FRAMES
from lab.flex_ui import RESPONSE, FlexUI
from lab.project import require
from lab.recorder_destination import (
    ARENA,
    DRAW,
    LABEL,
    NAMES,
    ROTATE,
    SET,
    STATE,
    TABLE,
    cell,
    rotation,
    setter,
)


class BufferUI(FlexUI):
    def __init__(self, *args, **kwargs):
        self.buffers = Buffers()
        self.buffer_slots = []
        self.private_slots = []
        self.issued = 0
        self.latched = None
        self.generation_refs = {}
        self.selector_names = []
        self.setup_done = False
        self.inject_failure = None
        self.project_transition_blocked = False
        super().__init__(*args, **kwargs)

    @property
    def destination(self):
        return self.fw.u32(STATE) if self.fw else 0

    def install(self, main):
        super().install(main)
        from unicorn import UC_HOOK_CODE

        fw = self.fw
        for page in range(ARENA, ARENA + 0x1000, 4096):
            fw.m.ensure(page)
        fw.write(ARENA, bytes(4096))
        fw.write(LABEL, b"DEST\0")
        cursor = ARENA + 0x110
        for index, name in enumerate(("TAKE", "BUF 1", "BUF 2", "BUF 3", "BUF 4")):
            fw.write(TABLE + index * 4, struct.pack(">I", cursor))
            fw.write(cursor, name.encode() + b"\0")
            cursor += 8
        fw.write(DRAW, cell())
        fw.write(SET, setter())
        fw.write(ROTATE, rotation())
        require(
            fw.read(0x400209AE, 6) == bytes.fromhex("487800052f02"),
            "Ready rotation drift",
        )
        require(
            fw.read(0x400221A0, 8) == bytes.fromhex("487800014878002f"),
            "Ready C graphic drift",
        )
        fw.write(0x400209AE, bytes.fromhex("4ef9") + struct.pack(">I", ROTATE))
        fw.write(
            0x400221A0, bytes.fromhex("4ef9") + struct.pack(">I", DRAW) + b"\x4e\x71"
        )
        fw.uc.ctl_remove_cache(0x40020000, 0x40024000)
        fw.uc.ctl_remove_cache(ARENA, ARENA + 0x1000)
        for pc in (
            0x40021DE0,
            0x401537A8,
            0x401537B8,
            0x40043A30,
            0x400F5050,
            0x40154540,
            0x401540C6,
            0x40153BEA,
            SET,
            0x4004D0D2,
            0x40113AE8,
            0x401137A4,
        ):
            self.hooks.append(
                fw.uc.hook_add(UC_HOOK_CODE, self.extra_hook, begin=pc, end=pc)
            )

    def _names(self):
        for index, _slot in enumerate(self.buffer_slots):
            state = (
                "RECORDING"
                if self.buffers.recording
                and self.buffers.recording.destination == index + 1
                and self.input.active
                else "READY"
                if self.buffers.current[index]
                else "EMPTY"
            )
            name = f"BUF {index + 1} {state}"
            self.fw.write(NAMES + index * 32, name.encode().ljust(32, b"\0"))
            self.fw.write(0x405B6368 + _slot * 16, name.encode().ljust(16, b"\0"))
            self.fw.write(0x405BC768 + _slot * 4, struct.pack(">I", NAMES + index * 32))
        for slot in self.private_slots:
            self.fw.write(0x405BC768 + slot * 4, struct.pack(">I", 0x4023F364))

    def extra_hook(self, uc, pc, *_):
        from unicorn import m68k_const as k

        fw = self.fw
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        if pc in (SET, 0x4004D0D2):
            self.record_event(
                "control-observe",
                pc=hex(pc),
                arg=fw.u32(sp + 8),
                destination=self.destination,
            )
        elif pc == 0x40113AE8:
            text = fw.u32(sp + 24)
            if ARENA <= text < ARENA + 4096:
                value = fw.read(text, 16).split(b"\0")[0].decode("ascii", "replace")
                self.selector_names.append(
                    dict(text=value, destination=self.destination)
                )
        elif pc == 0x401137A4:
            pointer = fw.u32(sp + 28)
            if 0x40000000 <= pointer < 0x50000000:
                value = fw.read(pointer, 32).split(b"\0")[0]
                if b" BUF " in value and len(self.selector_names) < 1024:
                    self.selector_names.append(
                        dict(text=value.decode("ascii"), kind="stock-selector-row")
                    )
        elif pc == 0x40021DE0:
            self.view = fw.u32(sp + 4)
            if not self.setup_done and self.pending is None:
                self.pending = ("setup",)
        elif pc == 0x401537A8 and self.setup_done:
            slot = fw.u32(sp + 4)
            if slot in self.buffer_slots:
                self.returned(NAMES + self.buffer_slots.index(slot) * 32)
            elif slot in self.private_slots:
                self.returned(0x4023F364)  # Existing non-NULL empty string.
        elif pc == 0x401537B8 and self.setup_done:
            if fw.u32(sp + 4) in self.private_slots:
                self.returned(0)
        elif (
            pc in (0x40154540, 0x401540C6, 0x40153BEA)
            and self.setup_done
            and not fw.direct
        ):
            slot = fw.u32(sp + (8 if pc == 0x40154540 else 4))
            if slot in self.buffer_slots + self.private_slots:
                self.record_event("reserved-slot-guard", pc=hex(pc), slot=slot)
                self.returned(-1 if pc == 0x40154540 else 0)
        elif pc == 0x40043A30 and self.setup_done:
            live = fw.u32(0x80004704)
            references = [
                int.from_bytes(fw.read(live + t * 0x450 + 0x80, 2), "big")
                for t in range(16)
            ]
            # Conservatively block even inactive pattern/lock roots while any
            # committed volatile resource exists, until complete roots are known.
            if any(self.buffers.current) or set(references) & set(self.buffer_slots):
                self.error = "VOLATILE BUFFERS: PROJECT NOT SAVED"
                self.record_event("project-save-blocked")
                self.returned(0)
        elif pc == 0x400F5050 and self.setup_done and self.buffers.generations:
            # Existing public storage load API returns a byte bool. Refuse
            # before decoding/reset can free a private allocation behind readers.
            self.error = "BUFFER SESSION: RESTART TO LOAD PROJECT"
            self.record_event("project-load-blocked")
            self.returned(0)

    def setup(self):
        if self.setup_done:
            return
        fw = self.fw
        pool = self.project_pool()
        free = [
            slot
            for slot in range(1, 1024)
            if slot % 128
            and fw.slot(slot)["empty"]
            and fw.read(pool + slot * 16, 16)[:4] == b"\xff" * 4
        ]
        require(len(free) >= 44, "Insufficient unused fixture slots")
        self.buffer_slots = free[:4]
        self.private_slots = list(reversed(free[-8:]))
        self.setup_done = True
        self._names()
        self.record_event(
            "buffers-initialized", slots=self.buffer_slots, private=self.private_slots
        )

    def project_pool(self):
        fw = self.fw
        project = fw.call(0x401988A2, [])
        settings = fw.call(0x40041D18, [project])
        return fw.call(fw.u32(fw.u32(settings) + 0x28), [settings]) + 0x1D2

    def hook(self, uc, pc, size, data):
        if pc == 0x40015FDA:
            self.target = None
            if self.destination:
                self.latched = self.buffers.begin(
                    self.destination, 0, self.fw.u32(0x80004704)
                )
        if pc == 0x40015FF8:
            self.buffers.cancel()
            self.latched = None
            if self.setup_done:
                self._names()
        super().hook(uc, pc, size, data)
        if pc == 0x400161FE and self.setup_done:
            self._names()

    def process(self):
        self.setup_in_transaction()
        if self.pending[0] == "setup":
            self.pending = None
            return
        if self.pending[0] == "project-change":
            self.pending = None
            self.change_project()
            return
        if self.pending[0] == "target":
            super().process()
            if self.latched:
                from dataclasses import replace

                self.latched = replace(self.latched, track=self.target)
                self.buffers.recording = self.latched
                self._names()
            return
        if self.latched is None:
            # Keep private/stable slots away from the legacy free-slot chooser.
            original = self.fw.free_slot
            original_source = self.fw.source

            def take_source(pcm, stereo, generation=1, **options):
                require(self.issued < 32, "32 issued identity limit")
                self.issued += 1
                return original_source(pcm, stereo, self.issued, **options)

            self.fw.free_slot = self.free_take_slot
            self.fw.source = take_source
            try:
                super().process()
            finally:
                self.fw.free_slot = original
                self.fw.source = original_source
            return
        pending, self.pending = self.pending, None
        fw, candidate = self.fw, self.latched
        generation_slot = identity = None
        committed = False
        try:
            with fw.transaction():
                require(
                    not self.project_transition_blocked,
                    "Project changed: restart buffer prototype session",
                )
                require(
                    candidate.epoch == self.buffers.epoch
                    and candidate.kit == fw.u32(0x80004704),
                    "Project changed",
                )
                take = self.input.candidate(*pending[1:])
                require(take.frames <= 96000, "BUF prototype limit: 2 seconds")
                size = (len(take.pcm) + 80 + 0x200F) & ~0x1FFF
                self.buffers.admit(candidate, size)
                require(self.issued < 32, "32 issued identity limit")
                live = fw.u32(0x80004704) + self.target * 0x450
                settings = fw.u32(self.view + 0xA0)
                require(
                    fw.call(0x4004ABE8, [settings]) == candidate.track,
                    "Selected track changed",
                )
                require(
                    fw.read(live + 0xD6, 1) == b"\0", "BUF prototype requires ONESHOT"
                )
                generation_slot = self.private_slots[len(self.buffers.generations)]
                require(fw.slot(generation_slot)["empty"], "Generation slot is owned")
                if self.inject_failure == "allocation":
                    raise ValueError("Injected allocation failure")
                for first in range(pending[1], pending[2], 0x800 // take.width):
                    count = min(0x800 // take.width, pending[2] - first)
                    fw.call(0x40012542, [])
                    try:
                        pointer = fw.call(
                            0x4001282E, [first, count, int(not take.stereo)]
                        )
                        offset = (first - pending[1]) * take.width
                        require(
                            pointer == RESPONSE
                            and fw.read(pointer, count * take.width)
                            == take.pcm[offset : offset + count * take.width],
                            "Recorder chunk differs",
                        )
                    finally:
                        fw.call(0x40012552, [])
                self.issued += 1
                ref = fw.source(
                    take.pcm, take.stereo, self.issued, max_frames=MAX_FRAMES
                )
                identity = int.from_bytes(ref[:4], "big")
                loaded, pages = fw.load(ref, generation_slot)
                require(
                    not fw.handles and loaded["allocation"]["size"] == size,
                    "Loader completeness",
                )
                require(
                    loaded["allocation"]["start"] + size <= 0x18800400,
                    "Allocation enters Capicola reservation",
                )
                if self.inject_failure == "publication":
                    # Allocation is quarantined, identity remains issued. No
                    # logical alias is changed and no partial pages are played.
                    raise ValueError("Injected incomplete publication")
                visible = self.buffer_slots[candidate.destination - 1]
                import plusdrive_check as check

                from lab.flex_lite import CLEAR_SLOT, UNLOAD

                if not fw.slot(visible)["empty"]:
                    fw.pages.clear()
                    fw.call(UNLOAD, [visible])
                    fw.call(CLEAR_SLOT, [visible])
                    pages.extend(fw.pages)
                alias = check.check_load(fw, ref, visible)
                require(
                    alias["load_d0"] == 0 and alias["data_pages"] == 0,
                    "Alias commit must use complete allocation",
                )
                pages.extend(fw.pages)
                fw.assign(self.target, visible)
                # Logical project references are volatile and serialization is
                # guarded above; source bytes cannot be reopened after removal.
                fw.write(
                    self.project_pool() + visible * 16,
                    struct.pack(
                        ">4I",
                        0x7FFD0000 + candidate.destination,
                        self.buffers.epoch,
                        0,
                        0,
                    ),
                )
                generation = Generation(
                    self.buffers.epoch, self.issued, generation_slot, size, take.frames
                )
                self.buffers.commit(candidate, generation, complete=True)
                committed = True
                self.generation_refs[self.issued] = ref
                self.pages.extend(pages)
                del fw.sources[identity]
                self.current = dict(
                    slot=visible,
                    name=f"BUF {candidate.destination}",
                    track=self.target,
                    frames=take.frames,
                    stereo=take.stereo,
                    generation=self.issued,
                    allocation=loaded["allocation"],
                )
                self.retained.append(dict(self.current))
                self.latched = None
                self._names()
                fw.call(0x40016020, [self.controller])
                self.phase, self.error = "assigned", None
                self.record_event(
                    "buffer-use", **self.current, dsp_bytes=self.buffers.occupied
                )
                worker = self.clock_state["worker"]
                names = {v: k for k, v in worker.button_names.items()}
                worker.inbox.extend(
                    [("press", names["SRC"], None), ("release", names["SRC"], None)]
                )
        except Exception as exc:
            if generation_slot is not None and not committed:
                with fw.transaction():
                    allocation = fw.slot(generation_slot)
                    if not allocation["empty"]:
                        self.buffers.generations.append(
                            Generation(
                                self.buffers.epoch,
                                self.issued,
                                generation_slot,
                                allocation["size"],
                                take.frames,
                            )
                        )
                    if identity in fw.sources and not fw.handles:
                        del fw.sources[identity]
            self.error, self.phase = str(exc), "trim"
            self.record_event("buffer-use-failed", error=self.error)

    def setup_in_transaction(self):
        if not self.setup_done:
            with self.fw.transaction():
                self.setup()

    def free_take_slot(self):
        for slot in range(1, 1024):
            if (
                slot % 128
                and slot not in self.buffer_slots + self.private_slots
                and self.fw.slot(slot)["empty"]
            ):
                return slot
        raise ValueError("No TAKE slot")

    def change_project(self):
        from lab.flex_lite import CLEAR_SLOT, UNLOAD

        with self.fw.transaction():
            for slot in self.buffer_slots:
                if not self.fw.slot(slot)["empty"]:
                    self.fw.pages.clear()
                    self.fw.call(UNLOAD, [slot])
                    self.fw.call(CLEAR_SLOT, [slot])
                    self.pages.extend(self.fw.pages)
            self.buffers.project_change()
            self.project_transition_blocked = True
            pool = self.project_pool()
            live = self.fw.u32(0x80004704)
            for slot in self.buffer_slots:
                self.fw.write(pool + slot * 16, b"\xff" * 16)
            for track in range(16):
                address = live + track * 0x450
                if (
                    int.from_bytes(self.fw.read(address + 0x80, 2), "big")
                    in self.buffer_slots
                ):
                    self.fw.write(address + 0x80, bytes(2))
                    self.fw.call(0x4002D438, [address + 0x34, track])
            self.fw.write(STATE, bytes(8))
            self.latched = self.current = None
            self._names()
            self.record_event("project-epoch", epoch=self.buffers.epoch)
