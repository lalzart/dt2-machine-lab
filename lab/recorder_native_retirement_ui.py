"""Observe native retirement jobs; no host retirement or completion writes."""

import struct

from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k

from lab import recorder_ack as ack
from lab import recorder_ack_loop as loop
from lab import recorder_dsp_reuse as paused
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_native_retirement as t
from lab import recorder_retirement as obs
from lab import recorder_seat_reuse as seats
from lab import recorder_worker_code as w
from lab.project import require
from lab.recorder_seat_native import SeatReuseUI


class NativeRetirementUI(SeatReuseUI):
    def __init__(self, *args, peer, **kwargs):
        self.peer = peer
        self.transaction_trace = []
        super().__init__(*args, **kwargs)

    def install(self, main):
        super().install(main)
        fw = self.fw
        loop.install_cpu(fw)
        fw.write(w.FLUSH, w.flush())  # transaction sends the obsolete generation.
        fw.uc.ctl_remove_cache(w.FLUSH, w.FLUSH + len(w.flush()))
        for at in range(t.BASE, t.END, 4096):
            fw.m.ensure(at)
            fw.write(at, bytes(4096))
        for at, data in (t.payload() | t.receipt_cpu()).items():
            fw.write(at, data)
            fw.uc.ctl_remove_cache(at, at + len(data))
        sender = obs.sender()
        for old, new in ((n.FIRST_ID, seats.FIRST_ID), (n.FIRST_ID + 7, seats.LAST_ID)):
            require(sender.count(struct.pack(">I", old)) == 1, "Sender bound drift")
            sender = sender.replace(struct.pack(">I", old), struct.pack(">I", new))
        fw.write(obs.CF_ENTRY, sender)
        fw.uc.ctl_remove_cache(obs.CF_ENTRY, obs.CF_ENTRY + len(sender))

        def jump(at, expected, target):
            require(
                fw.read(at, len(expected)) == expected,
                f"Transaction hook drift {at:#x}",
            )
            fw.write(
                at,
                b"\x4e\xf9"
                + struct.pack(">I", target)
                + b"\x4e\x71" * ((len(expected) - 6) // 2),
            )
            fw.uc.ctl_remove_cache(at, at + len(expected))

        jump(q.GUI, b"\x4e\xf9" + struct.pack(">I", q.POLL), t.POLL)
        jump(t.DRIVER_SITE, t.DRIVER_BYTES, t.DRIVER)
        jump(n.LOOKUP, seats.lookup()[:10], t.LOOKUP_GUARD)
        for i, at in enumerate((0x40154540, n.UNLOAD, n.CLEAR)):
            jump(
                at,
                b"\x4e\xf9" + struct.pack(">I", q.GUARDS + i * 256),
                t.GUARDS + i * 256,
            )
        fw.write(t.LABEL, b"RETIRE\0")
        fw.write(paused.ENTRY, bytes.fromhex("70ff4e75"))
        fw.uc.ctl_remove_cache(paused.ENTRY, paused.ENTRY + 4)
        link = self.clock_state["events"]["dspi2"]
        self.peer.inner, link.peer = link.peer, self.peer
        for at in (
            t.WORKER,
            t.BEGIN,
            t.COMMIT,
            t.DONE,
            ack.CF_REQUEST,
            ack.CF_CONSUME,
            ack.CF_PUMP,
            n.UNLOAD,
        ):
            self.hooks.append(
                fw.uc.hook_add(UC_HOOK_CODE, self.observe_transaction, begin=at, end=at)
            )

    def observe_transaction(self, uc, pc, *_):
        fw = self.fw
        require(not fw.direct, "Host direct retirement/pump used")
        require(pc != ack.CF_PUMP, "Diagnostic pump used")
        if pc == ack.CF_CONSUME:
            ret = fw.u32(uc.reg_read(k.UC_M68K_REG_A7))
            require(loop.RECEIVE <= ret < loop.SUBMIT, "Matcher bypassed native ISR")
            return
        self.transaction_trace.append(
            dict(
                pc=pc,
                phase=fw.u32(t.STATE + t.PHASE),
                task=fw.u32(q.CURRENT_TCB),
                sr=uc.reg_read(k.UC_M68K_REG_SR),
                frame=self.peer.calls,
                active_unload=fw.u32(t.STATE + t.ACTIVE_UNLOAD),
            )
        )
        if pc == n.UNLOAD and fw.u32(t.STATE + t.PHASE) == 3:
            require(
                fw.u32(t.STATE + t.ACTIVE_UNLOAD) == 1,
                "Shared worker borrowed inactive unload authority",
            )
        if pc == t.DONE:
            require(
                fw.u32(t.STATE + t.ACTIVE_UNLOAD) == 0,
                "Native unload authority escaped its call",
            )
        if pc == ack.CF_REQUEST:
            self.peer.request()

    def published_page(self, *args):
        before = len(self.pages)
        super().published_page(*args)
        self.peer.publish(self.pages[before:])
