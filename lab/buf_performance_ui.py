"""Install native BUF performance input; observe events and native state only."""

import struct

# isort: off
from lab import buf_performance as p
from lab import recorder_freeze_worker_code as q
from lab.buf_auto_retirement_ui import AutoRetirementUI
from lab.project import require
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import m68k_const as k
# isort: on


class PerformanceUI(AutoRetirementUI):
    def install(self, main):
        super().install(main)
        fw = self.fw
        for at, expected in (
            (p.KEY_SITE, p.KEY_BYTES),
            (p.PLAY_GET, p.PLAY_BYTES),
            (q.SUBMIT, q.submit()),
        ):
            require(fw.read(at, len(expected)) == expected, "Performance site drift")
        for at in range(p.BASE, p.END, 4096):
            fw.m.ensure(at)
            fw.write(at, bytes(4096))
        for at, data in p.payload().items():
            fw.write(at, data)
            fw.uc.ctl_remove_cache(at, at + len(data))
        for at, target, size in ((p.KEY_SITE, p.KEY, 8), (q.SUBMIT, p.SUBMIT, 6)):
            data = (
                b"\x4e\xf9"
                + struct.pack(">I", target)
                + b"\x4e\x71" * ((size - 6) // 2)
            )
            fw.write(at, data)
            fw.uc.ctl_remove_cache(at, at + size)
        self.performance_keys, self.native_freeze_requests, self.sequence_trace = (
            [],
            [],
            [],
        )

        def key(uc, _pc, *_):
            event = fw.u32(uc.reg_read(k.UC_M68K_REG_A7) + 8)
            code, flags = fw.u32(event + 12), fw.u32(event + 16)
            if code in (43, 50):
                self.performance_keys.append(
                    dict(key=code, flags=flags, frame=self.peer.calls)
                )

        def request(uc, _access, address, size, value, *_):
            if address != q.STATE:
                return
            pc = uc.reg_read(k.UC_M68K_REG_PC)
            require(
                p.INPUT <= pc < p.INPUT + len(p.input_event()),
                "FREEZE request did not originate in native input",
            )
            require(size == 4 and not fw.direct, "Invalid FREEZE request writer")
            self.native_freeze_requests.append(
                dict(
                    serial=value,
                    buffer=fw.u32(p.STATE + p.DEST),
                    pc=pc,
                    frame=self.peer.calls,
                )
            )

        self.hooks.append(fw.uc.hook_add(UC_HOOK_CODE, key, begin=p.INPUT, end=p.INPUT))
        self.hooks.append(
            fw.uc.hook_add(UC_HOOK_MEM_WRITE, request, begin=q.STATE, end=q.STATE + 3)
        )

        def sequence(_uc, _pc, *_):
            require(len(self.sequence_trace) < 8192, "Performance trace bound exceeded")
            self.sequence_trace.append(
                dict(
                    frame=self.peer.calls,
                    tick=self.tick(),
                    active=fw.u32(0x43164F94),
                    mode=fw.u32(0x43165010),
                    step=int.from_bytes(fw.read(0x43164F98, 2), "big"),
                    pulse=fw.read(0x43164F9A, 1)[0],
                    pattern=fw.u32(0x4316501C),
                )
            )

        pc = 0x400D8C6E  # Original source-57 exit, after normal native progression.
        require(
            fw.read(pc, 8) == bytes.fromhex("4cd77fff4fef0094"), "Sequencer exit drift"
        )
        self.hooks.append(fw.uc.hook_add(UC_HOOK_CODE, sequence, begin=pc, end=pc))
