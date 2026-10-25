"""Install next-bar native code; peripheral models and read-only evidence only."""

import struct

# isort: off
from lab import buf_next_bar as b
from lab import buf_performance as p
from lab import buf_auto_retirement as auto
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab import recorder_seat_reuse as seats
from lab.buf_performance_ui import PerformanceUI
from lab.project import require
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE, m68k_const as k
# isort: on


class NextBarUI(PerformanceUI):
    def __init__(self, *args, clock_enabled=True, **kwargs):
        self.clock_enabled = clock_enabled
        self.next_bar_trace = []
        super().__init__(*args, **kwargs)

    def install(self, main):
        super().install(main)
        fw = self.fw
        self.recorder_settings = None
        parts = b.payload()
        for at, expected in (
            (b.ARM_SITE, b.ARM_BYTES),
            (b.CLOCK_SITE, b.CLOCK_BYTES),
            (p.KEY, p.payload()[p.KEY]),
            (q.GUI, b"\x4e\xf9" + struct.pack(">I", auto.POLL)),
        ):
            require(fw.read(at, len(expected)) == expected, "Next-bar patch site drift")
        for at in (
            b.START,
            b.STOP,
            b.DISCARD,
            b.READY,
            b.COUNT,
            b.CHANNEL,
            b.CLOCK_MODE,
        ):
            require(
                fw.read(at, 16) == main[at - 0x40000400 : at - 0x40000400 + 16],
                "Next-bar stock function drift",
            )
        for at in range(b.BASE, b.END, 4096):
            fw.m.ensure(at)
            fw.write(at, bytes(4096))
        fw.write(b.STATE + b.ENABLED, struct.pack(">I", int(self.clock_enabled)))
        fw.write(b.LABEL, b"BUF AUTO USE\0")
        for at, code in parts.items():
            fw.write(at, code)
            fw.uc.ctl_remove_cache(at, at + len(code))
        for at, target, size in (
            (b.ARM_SITE, b.ARM, 8),
            (b.CLOCK_SITE, b.IRQ, 8),
            (q.GUI, b.POLL, 6),
        ):
            fw.write(
                at,
                b"\x4e\xf9"
                + struct.pack(">I", target)
                + b"\x4e\x71" * ((size - 6) // 2),
            )
            fw.uc.ctl_remove_cache(at, at + size)
        fw.write(p.KEY, b.key_bridge())
        fw.uc.ctl_remove_cache(p.KEY, p.KEY + len(b.key_bridge()))
        # Current BUF commits publish only. NORMAL still takes its original
        # trampolines. Keep seat selection/token issuance in the native worker.
        for at, code in (
            (w.WORKER, seats.worker(require_track=False)),
            (w.ASSIGN, w.assign(assign_track=False)),
            (p.ELIGIBLE, p.eligible(all_oneshot=False)),
        ):
            fw.write(at, code)
            fw.uc.ctl_remove_cache(at, at + len(code))
        def settings_observe(uc, _pc, *_):
            self.recorder_settings = uc.reg_read(k.UC_M68K_REG_A0)

        self.hooks.append(
            fw.uc.hook_add(
                UC_HOOK_CODE, settings_observe, begin=0x4004CCC6, end=0x4004CCC6
            )
        )

        def observe(uc, pc, *_):
            if pc in (b.START, b.STOP, b.DISCARD) and not fw.u32(b.STATE + b.OWN):
                return  # The manual seed take is recorded by the existing peer.
            require(not fw.direct, "Host direct next-bar execution")
            sp = uc.reg_read(k.UC_M68K_REG_A7)
            self.next_bar_trace.append(
                dict(
                    pc=pc,
                    caller=fw.u32(sp),
                    frame=self.peer.calls,
                    tick=self.tick(),
                    sr=uc.reg_read(k.UC_M68K_REG_SR),
                    phase=fw.u32(b.STATE + b.PHASE),
                    serial=fw.u32(b.STATE + b.SERIAL),
                    epoch=fw.u32(b.STATE + b.CEPOCH),
                    recorder_state=fw.u32(fw.u32(fw.u32(b.STATE + b.CTRL) + 16) + 0xA4)
                    if fw.u32(b.STATE + b.CTRL)
                    else None,
                    count=fw.u32(w.STATE + 80),
                )
            )
            if pc in (b.START, b.STOP) and fw.u32(b.STATE + b.OWN):
                require(
                    b.STEP <= fw.u32(sp) < b.STEP + len(parts[b.STEP]),
                    "Capture bypassed native GUI service",
                )

        for at in (
            b.ARM,
            b.START,
            b.STOP,
            b.DISCARD,
            b.QUEUE,
            b.WORKER,
            b.DONE,
            b.CANCEL_FN,
            0x400161FE,  # Original capture completion / modeled input boundary.
        ):
            self.hooks.append(fw.uc.hook_add(UC_HOOK_CODE, observe, begin=at, end=at))

        def receipt(uc, _access, at, size, value, *_):
            if at == b.STATE + b.PUBLISH_TICK:
                self.next_bar_trace.append(
                    dict(
                        event="publish",
                        pc=uc.reg_read(k.UC_M68K_REG_PC),
                        tick=value,
                        frame=self.peer.calls,
                    )
                )
            elif at == b.STATE + b.SERIAL:
                pc = uc.reg_read(k.UC_M68K_REG_PC)
                require(
                    size == 4 and b.IRQ <= pc < b.IRQ + len(parts[b.IRQ]),
                    "Non-native bar receipt",
                )
                self.next_bar_trace.append(
                    dict(
                        pc=pc,
                        event="bar",
                        step=int.from_bytes(fw.read(0x43164F98, 2), "big"),
                        pulse=fw.read(0x43164F9A, 1)[0],
                        serial=value,
                        tick=self.tick(),
                        frame=self.peer.calls,
                    )
                )

        self.hooks.append(
            fw.uc.hook_add(
                UC_HOOK_MEM_WRITE,
                receipt,
                begin=b.STATE + b.SERIAL,
                end=b.STATE + b.SERIAL + 3,
            )
        )
        self.hooks.append(
            fw.uc.hook_add(
                UC_HOOK_MEM_WRITE,
                receipt,
                begin=b.STATE + b.PUBLISH_TICK,
                end=b.STATE + b.PUBLISH_TICK + 3,
            )
        )

    def hook(self, uc, pc, size, data):
        if pc == b.START:
            # This changes modeled input cadence only. Native bar receipts and
            # controller start/stop still choose the transaction boundaries.
            self.input.ticks_per_frame = 1 if self.fw.u32(b.STATE + b.OWN) else 2
        return super().hook(uc, pc, size, data)
