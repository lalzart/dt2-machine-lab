"""Opt-in native BUF worker adapter. Python models peripherals and observes.

No host capture commit, loader invocation, allocation, assignment, naming or
registration. Native FREEZE remains the prior paused diagnostic command.
"""

import struct

# isort: off
from lab import recorder_worker_code as w, recorder_freeze_code as n
from lab.flex_native_input import NativeFlexInput
from lab.recorder_freeze_native import NativeFreezeUI
from lab.project import require
from lab.flex_heap import inspect_heap, block_bytes
from lab.flex_buffer_ui import STATE as DEST, NAMES
from unicorn import UC_HOOK_CODE, m68k_const as k
# isort: on


class NativeWorkerUI(NativeFreezeUI):
    def __init__(self, gui, *args, **kwargs):
        super().__init__(gui, *args, **kwargs)
        spin = gui.spin

        def observe_spin(*a, **kw):
            result = spin(*a, **kw)
            if self.fw is not None:
                self.sync_observation()
            return result

        gui.spin = observe_spin

    def install(self, main):
        super().install(main)
        require(w.DEST == DEST and w.NAMES == NAMES, "Worker UI ABI drift")
        fw = self.fw
        for page in range(w.BASE, w.END, 4096):
            fw.m.ensure(page)
            fw.write(page, bytes(4096))
        parts = w.payload()
        strings = {
            name: text.replace("FLEX:", "BUF:") for name, text in w.f.USE_ERRORS.items()
        }
        strings["limit"] = "BUF: SESSION LIMIT"
        for index, name in enumerate(strings):
            at = w.ERROR_NAMES + index * 64
            fw.write(at, strings[name].encode().ljust(64, b"\0"))
            fw.write(w.ERROR_TABLE + index * 4, struct.pack(">I", at))
        require(
            fw.read(0x40021986, 6) == bytes.fromhex("487940229675"),
            "Stock error PEA drift",
        )
        fw.write(0x40021986, b"\x4e\xf9" + struct.pack(">I", w.ERROR_ENTRY))
        fw.uc.ctl_remove_cache(0x40021986, 0x4002198C)
        require(
            fw.read(0x400CD638, 8) == bytes.fromhex("4feffff448d70c04"),
            "Stock page publisher drift",
        )
        fw.write(
            0x400CD638, b"\x4e\xf9" + struct.pack(">I", w.PAGE_FILTER) + b"\x4e\x71"
        )
        fw.uc.ctl_remove_cache(0x400CD638, 0x400CD640)
        fw.write(
            n.FREEZE, b"\x4e\xf9" + struct.pack(">I", w.FREEZE_GUARD) + b"\x4e\x71"
        )
        fw.uc.ctl_remove_cache(n.FREEZE, n.FREEZE + 8)
        self.hooks.append(
            fw.uc.hook_add(
                UC_HOOK_CODE, self.published_page, begin=w.TRAMP + 96, end=w.TRAMP + 96
            )
        )
        for pc, block in parts.items():
            fw.write(pc, block)
        self.worker_contexts, self.completed, self.chunks = [], [], []
        self.retirements, self.retiring = [], None
        self.retire_done = w.RETIRE + len(parts[w.RETIRE]) - 8
        self.native_mode = True  # All source HLEs disabled, including worker mode.
        for pc, (before, target) in w.HOOKS.items():
            expected = bytes.fromhex(before)
            require(fw.read(pc, 8) == expected, f"Worker hook drift {pc:#x}")
            fw.write(pc, b"\x4e\xf9" + struct.pack(">I", target) + b"\x4e\x71")
            fw.uc.ctl_remove_cache(pc, pc + 8)
        for i, (_op, (pc, _)) in enumerate(n.RESOURCE_SITES.items()):
            fw.write(pc, b"\x4e\xf9" + struct.pack(">I", w.DISPATCH + i * 256))
            fw.uc.ctl_remove_cache(pc, pc + 16)
        for i, pc in enumerate((0x40154540, n.UNLOAD, n.CLEAR)):
            fw.write(pc, b"\x4e\xf9" + struct.pack(">I", w.SLOT_GUARDS + i * 256))
            fw.uc.ctl_remove_cache(pc, pc + 8)
        # Original error callback's PEA operand, only reached after our failure.
        # Ordinary NORMAL failures retain the original stock error text.
        fw.uc.ctl_remove_cache(w.BASE, w.END)
        for pc in (w.WORKER, w.FINISH, w.RETIRE, w.COPY, n.REGISTER, self.retire_done):
            self.hooks.append(
                fw.uc.hook_add(UC_HOOK_CODE, self.worker_observe, begin=pc, end=pc)
            )
        self.payload_ranges = [(pc, len(block)) for pc, block in sorted(parts.items())]

    def hook(self, uc, pc, size, data):
        # Only external recorder-peer behavior. In particular trim YES is not
        # skipped, and no "pending accept" host transaction can be scheduled.
        if pc != 0x400CD638:
            NativeFlexInput.observe(self, uc, pc, size, data)

    def published_page(self, uc, _pc, size, data):
        # Observe only the path actually forwarded by native page_filter().
        NativeFlexInput.observe(self, uc, 0x400CD638, size, data)

    def extra_hook(self, uc, pc, *_):
        if pc == 0x40021DE0:
            self.view = self.fw.u32(uc.reg_read(k.UC_M68K_REG_A7) + 4)
            # Label is experimental presentation only, not a backend action.
            self.fw.write(
                0x402296FB, b"Y:SAVE\0" if self.destination == 0 else b"Y:USE \0"
            )
        # No inherited host setup/slot guards/selector names/project operations.

    def process(self):
        raise AssertionError("Native worker attempted a host BUF transaction")

    def worker_observe(self, uc, pc, *_):
        fw = self.fw
        if pc == w.WORKER and fw.u32(w.STATE + 12):
            self.worker_contexts.append(
                dict(
                    sr=uc.reg_read(k.UC_M68K_REG_SR),
                    direct=fw.direct,
                    sp=uc.reg_read(k.UC_M68K_REG_A7),
                    tick=self.tick(),
                )
            )
        elif pc == w.FINISH and fw.u32(w.STATE + 12):
            self.record_event(
                "native-worker-finish", status=fw.u32(uc.reg_read(k.UC_M68K_REG_A7) + 8)
            )
        elif pc == w.RETIRE:
            self.record_event("native-source-retirement")
            node = fw.u32(uc.reg_read(k.UC_M68K_REG_A7) + 4)
            self.retiring = dict(
                node=node,
                pointer=fw.u32(node + 20),
                size=fw.u32(node + 12),
                free_before=inspect_heap(fw.read).free_bytes,
            )
        elif pc == self.retire_done:
            item = self.retiring
            item["free_after"] = inspect_heap(fw.read).free_bytes
            require(
                fw.u32(item["node"] + 20) == 0
                and item["free_after"] - item["free_before"]
                == block_bytes(item["size"]),
                "Native retirement freed wrong CPU block",
            )
            self.retirements.append(item)
            self.retiring = None
        elif pc == w.COPY:
            self.record_event("native-recorder-copy")
        elif pc == n.REGISTER:
            self.record_event("native-worker-register")
        self.sync_observation()

    def sync_observation(self):
        fw = self.fw
        if fw.u32(w.STATE + 64):
            self.buffer_slots = [fw.u32(w.STATE + 96 + i * 4) for i in range(4)]
            self.private_slots = [fw.u32(w.STATE + 112 + i * 4) for i in range(8)]
            self.setup_done = True
        count = fw.u32(w.STATE + 80)
        if count > len(self.completed):
            # Observation only: no guest state is modified here.
            slot = fw.u32(w.STATE + 36)
            self.target = fw.u32(w.STATE + 16)
            self.current = dict(
                slot=slot,
                track=self.target,
                frames=fw.u32(w.STATE + 28),
                stereo=bool(fw.u32(w.STATE + 32)),
                generation=fw.u32(w.STATE + 4),
                allocation=fw.slot(slot),
            )
            self.completed.append(dict(self.current))
            self.phase, self.error = "assigned", None

    def freeze(self, *args, **kwargs):
        try:
            return super().freeze(*args, **kwargs)
        finally:
            self.native_mode = True
