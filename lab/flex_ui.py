"""Opt-in OS 1.16 recorder UI, modeled WAV service and volatile sample handoff.

Uses original firmware routines at a worker boundary. Dependencies and firmware
files remain unchanged. Hooks and one label are installed only in guest RAM.
"""

import struct
from contextlib import contextmanager

from lab.flex_recorder import MAX_FRAMES, RecorderInput
from lab.project import require

# isort: off
from lab.flex_lite import RamFirmware
import plusdrive_check as check
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k
# isort: on

RESPONSE = 0x4FE79340
TICK = 0x40966500
HOOK_BYTES = {
    0x40015FDA: "48780002206f0008",  # manual start
    0x400161FE: "4fefffd448d70c04",  # stop/normalize
    0x40015FF8: "2f0a246f000842a7",  # discard/reset
    0x400CD6CE: "71f98000100473f9",  # recorded frame count
    0x400124A0: "",  # filled from authenticated MAIN below, service boundary
    0x40022FBE: "4879402297197e01",  # plain YES in completed trim view
    0x40023026: "2f0b4eb940197a4a",  # stock PLEASE WAIT view has been pushed
}
MAX_TAKES = 32


class AttachedFirmware(RamFirmware):
    """Borrow a GUI Machine; HLE accommodations apply only to bounded calls."""

    def __init__(self, machine, card):
        self.m, self.uc = machine, machine.uc
        self.card = check.Card(card)
        self.pages, self.events, self.traps = [], [], []
        self.sources, self.handles = {}, {}
        self.source_events, self.source_hooks, self.assignment_hooks = [], [], []
        self._scratch = check.SCRATCH
        self.direct = False
        self.recorder_lock_depth = 0
        self.poisoned_responses = 0
        self.hooks = []
        machine.ensure(check.SCRATCH)
        machine.ensure(check.STACK_TOP)
        for address, fn in (
            (check.EMMC_READ, self._emmc_read),
            (check.EMMC_WRITE, self._emmc_write),
            (check.MUTEX_LOCK, lambda a: 1),
            (check.MUTEX_UNLOCK, lambda a: 0),
            (check.RMUTEX_LOCK, self.lock_recorder),
            (check.RMUTEX_UNLOCK, self.unlock_recorder),
            (check.FLEXBUS_PAGE, self._flexbus_page),
            (check.LOADER_EVENT, self._loader_event),
        ):
            self._hle(address, fn)
        self.enable_ram()

    def lock_recorder(self, arg):
        if arg(0) == 0x40965B74:
            self.recorder_lock_depth += 1
        return 1

    def unlock_recorder(self, arg):
        if arg(0) == 0x40965B74:
            require(self.recorder_lock_depth > 0, "Unbalanced recorder unlock")
            self.recorder_lock_depth -= 1
            if not self.recorder_lock_depth:
                self.write(RESPONSE, b"\xa5" * 0x800)
                self.poisoned_responses += 1
        return 0

    def _hle(self, address, fn):
        def hook(uc, pc, size, data):
            if not self.direct:
                return
            sp = uc.reg_read(k.UC_M68K_REG_A7)
            ret = self.u32(sp)
            value = fn(lambda i: self.u32(sp + 4 + i * 4))
            uc.reg_write(k.UC_M68K_REG_D0, (value or 0) & 0xFFFFFFFF)
            uc.reg_write(k.UC_M68K_REG_A7, sp + 4)
            uc.reg_write(k.UC_M68K_REG_PC, ret)

        self.hooks.append(
            self.uc.hook_add(UC_HOOK_CODE, hook, begin=address, end=address)
        )

    @contextmanager
    def transaction(self):
        require(not self.direct, "Nested GUI firmware transaction")
        context = self.uc.context_save()
        self.direct = True
        self._scratch = check.SCRATCH
        self.uc.reg_write(k.UC_M68K_REG_SR, 0x2700)
        try:
            yield
        finally:
            self.uc.context_restore(context)
            self.direct = False

    def name(self, arg):
        source = self.get_source(arg(0))
        label = source.get("name", "TEMP")
        self.write(arg(2), ("/TEMP/" + label).encode().ljust(32, b"\0"))
        return arg(2)

    def assign(self, track, slot):
        require(0 <= track < 16 and not self.slot(slot)["empty"], "Invalid assignment")
        live = self.u32(0x80004704) + track * check.TRACK_STRIDE
        require(
            self.read(live + check.TRACK_MACHINE, 1) == b"\0",
            "Use an ONESHOT track for this prototype",
        )
        before = self.read(live, check.TRACK_STRIDE)
        try:
            self.write(live + check.TRACK_SLOT, struct.pack(">H", slot))
            self.call(0x4002D438, [live + 0x34, track])
            after = self.read(live, check.TRACK_STRIDE)
            require(
                before[:0x80] == after[:0x80] and before[0x82:] == after[0x82:],
                "Assignment changed other track data",
            )
        except Exception:
            self.write(live, before)
            self.call(0x4002D438, [live + 0x34, track])
            raise
        return before, after


class FlexUI:
    def __init__(self, gui, clock_state, source, card, main, *, enabled=True):
        self.input = RecorderInput(source)
        self.clock_state = clock_state
        self.target = None
        self.current = None
        self.retained = []
        self.events = []
        self.pages = []
        self.pending = None
        self.view = None
        self.controller = None
        self.error = None
        self.phase = "ready"
        self.enabled = enabled
        self.fw = None
        self.hooks = []
        original_build, original_spin = gui.build, gui.spin

        def build(*args, **kwargs):
            result = original_build(*args, **kwargs)
            self.fw = AttachedFirmware(result[0], card)
            self.install(main)
            return result

        def spin(*args, **kwargs):
            result = original_spin(*args, **kwargs)
            if self.pending is not None:
                self.process()
            return result

        gui.build, gui.spin = build, spin

    def tick(self):
        return self.fw.u32(TICK)

    def record_event(self, event, **fields):
        self.events.append({"event": event, "tick": self.tick(), **fields})

    def install(self, main):
        fw = self.fw
        for address, expected in HOOK_BYTES.items():
            expected = (
                bytes.fromhex(expected)
                if expected
                else main[address - 0x40000400 : address - 0x40000400 + 8]
            )
            require(
                fw.read(address, len(expected)) == expected,
                f"UI hook drift at {address:#x}",
            )
            self.hooks.append(
                fw.uc.hook_add(UC_HOOK_CODE, self.hook, begin=address, end=address)
            )
        require(fw.read(0x400232D2, 2) == bytes.fromhex("1003"), "UI return site drift")
        require(fw.read(0x402296FB, 7) == b"Y:SAVE\0", "Trim label drift")
        if self.enabled:
            fw.write(0x402296FB, b"Y:USE \0")

    def returned(self, value=0):
        u = self.fw.uc
        sp = u.reg_read(k.UC_M68K_REG_A7)
        ret = self.fw.u32(sp)
        u.reg_write(k.UC_M68K_REG_D0, value & 0xFFFFFFFF)
        u.reg_write(k.UC_M68K_REG_A7, sp + 4)
        u.reg_write(k.UC_M68K_REG_PC, ret)

    def hook(self, u, pc, size, data):
        fw = self.fw
        if pc == 0x400CD6CE:
            self.returned(self.input.count(self.tick()))
        elif pc == 0x40015FDA:
            self.controller = fw.u32(u.reg_read(k.UC_M68K_REG_A7) + 4)
            self.view = u.reg_read(k.UC_M68K_REG_A2)
            self.input.begin(self.tick())
            self.phase, self.error = "recording", None
            self.pending = ("target",)
            self.record_event("record")
        elif pc == 0x400161FE:
            self.input.finish(self.tick())
            self.phase = "trim"
            self.record_event("finish", frames=self.input.captured)
        elif pc == 0x40015FF8:
            self.input.discard()
            self.phase = "ready"
            self.record_event("discard")
        elif pc == 0x40022FBE and self.enabled:
            self.view = u.reg_read(k.UC_M68K_REG_A2)
            self.pending = (
                "accept",
                fw.u32(self.view + 0x9A0),
                fw.u32(self.view + 0x9A4),
            )
            u.reg_write(k.UC_M68K_REG_D3, 1)
            u.reg_write(k.UC_M68K_REG_PC, 0x400232D2)
        elif pc == 0x40023026:
            self.record_event("stock-save-progress-opened")
        elif pc == 0x400124A0:
            sp = u.reg_read(k.UC_M68K_REG_A7)
            length, pointer, response = struct.unpack(">III", fw.read(sp + 4, 12))
            require(length in (2, 4, 12), "Unknown recorder request extent")
            desc = fw.read(pointer, length)
            command = int.from_bytes(desc[:2], "big")
            payload = bytes(response)
            if command == 3:
                _, selector, start, end = struct.unpack(">HHII", desc)
                require(response == 16, "Waveform response extent")
                payload = self.input.extrema(start, end)
            elif command == 4:
                _, mono, start, count = struct.unpack(">HHII", desc)
                require(response == 0x800, "PCM response extent")
                require(
                    fw.direct and fw.recorder_lock_depth == 2,
                    "Chunk request did not retain outer lock",
                )
                payload = self.input.chunk(start, count, mono).ljust(response, b"\0")
            elif command not in (0, 1, 2, 5):
                raise ValueError(f"Unmodeled recorder command {command}")
            fw.write(RESPONSE, payload)
            self.returned()

    def process(self):
        pending, self.pending = self.pending, None
        fw = self.fw
        committed = False
        try:
            with fw.transaction():
                if pending[0] == "target":
                    settings = fw.u32(self.view + 0xA0)
                    settings_data = fw.call(fw.u32(fw.u32(settings) + 0x28), [settings])
                    # This modeled input's channel count is explicit; keep the
                    # native recorder display consistent with the chosen WAV.
                    fw.write(
                        settings_data + 0x1BE,
                        struct.pack(">I", int(not self.input.source.stereo)),
                    )
                    if self.target is None:
                        self.target = fw.call(0x4004ABE8, [settings])
                        require(0 <= self.target < 16, "Invalid target track")
                    return
                require(
                    len(fw.sources) < MAX_TAKES,
                    "Session holds 32 takes; restart before recording more",
                )
                candidate = self.input.candidate(*pending[1:])
                # Check compatibility before allocating or touching the old sound.
                live = fw.u32(0x80004704) + self.target * check.TRACK_STRIDE
                require(
                    fw.read(live + check.TRACK_MACHINE, 1) == b"\0",
                    "Destination must use ONESHOT",
                )
                slot = fw.free_slot()
                copied = bytearray()
                for first in range(pending[1], pending[2], 0x800 // candidate.width):
                    count = min(0x800 // candidate.width, pending[2] - first)
                    fw.call(0x40012542, [])
                    try:
                        pointer = fw.call(
                            0x4001282E, [first, count, int(not candidate.stereo)]
                        )
                        require(
                            pointer == RESPONSE, "Unexpected recorder response address"
                        )
                        copied.extend(fw.read(pointer, count * candidate.width))
                    finally:
                        fw.call(0x40012552, [])
                require(
                    bytes(copied) == candidate.pcm, "Original chunk wrapper PCM differs"
                )
                generation = len(fw.sources) + 1
                ref = fw.source(
                    bytes(copied), candidate.stereo, generation, max_frames=MAX_FRAMES
                )
                label = f"TEMP{generation:03d}"
                fw.sources[int.from_bytes(ref[:4], "big")]["name"] = label
                loaded, pages = fw.load(ref, slot)
                require(not fw.handles, "Loader left a temporary source open")
                require(loaded["name"] == label.encode(), "Temporary name differs")
                require(
                    check.sent_pcm_matches(
                        loaded, fw.sources[int.from_bytes(ref[:4], "big")]["data"]
                    )
                    == [True] * (2 if candidate.stereo else 1),
                    "Published PCM differs",
                )
                before, after = fw.assign(self.target, slot)
                take = {
                    "slot": slot,
                    "name": label,
                    "track": self.target,
                    "frames": candidate.frames,
                    "stereo": candidate.stereo,
                    "allocation": loaded["allocation"],
                }
                self.retained.append(take)
                self.current = take
                self.pages.extend(pages)
                committed = True
                fw.call(0x40016020, [self.controller])
                self.phase, self.error = "assigned", None
                self.record_event("use", **take, track_bytes_preserved=True)
                worker = self.clock_state["worker"]
                names = {v: k for k, v in worker.button_names.items()}
                worker.inbox.extend(
                    [
                        ("press", names["TRK"], None),
                        ("press", names[f"TRIG {self.target + 1}"], None),
                        ("release", names[f"TRIG {self.target + 1}"], None),
                        ("release", names["TRK"], None),
                        ("press", names["SRC"], None),
                        ("release", names["SRC"], None),
                    ]
                )
        except Exception as exc:
            self.error = str(exc)
            self.phase = "assigned" if committed else "trim"
            self.record_event(
                "assigned-ui-error" if committed else "use-failed", error=self.error
            )
