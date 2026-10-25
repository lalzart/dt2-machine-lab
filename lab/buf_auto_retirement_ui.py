"""Install the native BUF scheduler; host only models peripherals/observes."""

import struct

# isort: off
# Load the pinned runtime through the existing adapter before importing Unicorn.
from lab import buf_auto_retirement as auto
from lab import recorder_freeze_worker_code as q
from lab import recorder_native_retirement as t
from lab.project import require
from lab.recorder_native_retirement_ui import NativeRetirementUI
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k
# isort: on


class AutoRetirementUI(NativeRetirementUI):
    def install(self, main):
        super().install(main)
        fw = self.fw
        for at, expected in auto.STOCK_GUARDS.items():
            require(fw.read(at, len(expected)) == expected, "BUF stock getter drift")
        for at in range(auto.BASE, auto.END, 4096):
            fw.m.ensure(at)
            fw.write(at, bytes(4096))
        require(fw.read(t.POLL, len(t.poll())) == t.poll(), "BUF transaction drift")
        for at, data in auto.payload().items():
            fw.write(at, data)
            fw.uc.ctl_remove_cache(at, at + len(data))
        require(
            fw.read(q.GUI, 6) == b"\x4e\xf9" + struct.pack(">I", t.POLL),
            "BUF GUI hook drift",
        )
        fw.write(q.GUI, b"\x4e\xf9" + struct.pack(">I", auto.POLL))
        fw.uc.ctl_remove_cache(q.GUI, q.GUI + 6)
        self.automatic_submissions = []

        def observe_queue(uc, _pc, *_):
            if uc.reg_read(k.UC_M68K_REG_D0) != 1:
                return  # Commit submission belongs to the existing transaction.
            caller = fw.u32(uc.reg_read(k.UC_M68K_REG_A7))
            require(
                auto.STEP <= caller < auto.STEP + len(auto.step()),
                "BUF prepare was not selected by native policy",
            )
            require(
                not fw.direct and fw.u32(t.STATE) == fw.u32(t.STATE + 4) == 0,
                "Host/manual BUF retirement command used",
            )
            self.automatic_submissions.append(
                dict(token=fw.u32(t.STATE + 16), frame=self.peer.calls, caller=caller)
            )

        self.hooks.append(
            fw.uc.hook_add(UC_HOOK_CODE, observe_queue, begin=t.QUEUE, end=t.QUEUE)
        )
