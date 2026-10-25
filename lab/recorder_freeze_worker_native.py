"""Native FREEZE queue adapter; observes jobs, never executes a host commit."""

import struct

from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k

from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab.project import require
from lab.recorder_worker_native import NativeWorkerUI


class QueuedFreezeUI(NativeWorkerUI):
    def install(self, main):
        super().install(main)
        fw = self.fw
        require(
            main[0x18:0x1E] == bytes.fromhex("207947db3f64"),
            "OS 1.16 scheduler current-task operand drift",
        )
        require(fw.read(q.GUI, 6) == q.GUI_BYTES, "GUI loop boundary drift")
        for at in range(q.BASE, q.END, 4096):
            fw.m.ensure(at)
            fw.write(at, bytes(4096))
        for at, block in q.payload().items():
            fw.write(at, block)
        fw.write(q.LABEL, b"FREEZE\0")
        fw.write(q.GUI, b"\x4e\xf9" + struct.pack(">I", q.POLL))
        fw.uc.ctl_remove_cache(q.GUI, q.GUI + 6)
        for i, pc in enumerate((0x40154540, n.UNLOAD, n.CLEAR)):
            expected = b"\x4e\xf9" + struct.pack(">I", w.SLOT_GUARDS + i * 256)
            require(fw.read(pc, 6) == expected, "Worker slot guard drift")
            fw.write(pc, b"\x4e\xf9" + struct.pack(">I", q.GUARDS + i * 256))
            fw.uc.ctl_remove_cache(pc, pc + 8)
        fw.uc.ctl_remove_cache(q.BASE, q.END)
        self.freeze_contexts = []
        for at in (q.SUBMIT, q.WORKER, q.BODY, q.DONE, w.WORKER):
            self.hooks.append(
                fw.uc.hook_add(UC_HOOK_CODE, self.freeze_observe, begin=at, end=at)
            )

    def freeze_observe(self, uc, pc, *_):
        self.freeze_contexts.append(
            dict(
                pc=pc,
                sr=uc.reg_read(k.UC_M68K_REG_SR),
                task=self.fw.u32(q.CURRENT_TCB),
                direct=self.fw.direct,
                phase=self.fw.u32(q.STATE + 8),
                tick=self.tick(),
            )
        )

    def freeze(self, *_a, **_kw):
        raise AssertionError("Queued FREEZE forbids the paused host command")
