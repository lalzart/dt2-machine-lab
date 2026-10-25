"""Shared native BUF fixtures; helpers only, with no discoverable test cases.

Each layer adds the same prepared service boundaries used by the original
standalone tests. Payload bytes and test assertions stay in their feature files.
"""

import struct

from lab import buf_auto_retirement as a
from lab import buf_performance as p
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_native_retirement as t
from lab import recorder_seat_reuse as seats
from lab import recorder_worker_code as w
from lab.emit import Code

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = r = None


class NativeRetirementFixture:
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for at, size in (
            (t.BASE, t.END - t.BASE),
            (n.BASE, 0x8000),
            (w.BASE, 0xB000),
            (q.BASE, 0x4000),
            (0x10900000, 0x4000),
            (0x10A00000, 0x4000),
            (0x200000, 0x10000),
            (0x405A0000, 0x40000),
            (0x47DB3000, 0x1000),
            (0x80004000, 0x1000),
            (0x40154000, 0x1000),
            (seats.BASE, 0x4000),
            (0x40001000, 0x1000),
            (0x4002D000, 0x1000),
            (0x40966000, 0x1000),
        ):
            self.cpu.mem_map(at, size)
        for at, code in t.payload().items():
            self.cpu.mem_write(at, code)
        for at, code in t.receipt_cpu().items():
            self.cpu.mem_write(at, code)
        for at, code in (
            (q.ENTER, q.operation_count(q.ENTER, 1)),
            (q.LEAVE, q.operation_count(q.LEAVE, -1)),
            (q.GATE, q.gate()),
        ):
            self.cpu.mem_write(at, code)
        self.put(n.STATE, 1)
        self.put(w.STATE + 12, 3)
        self.put(0x80004704, 0x204000)
        self.put(q.CURRENT_TCB, 0x203000)
        for field, value in (
            (t.PHASE, 1),
            (t.TOKEN, seats.FIRST_ID),
            (t.EPOCH, 1),
            (t.KIT, 0x204000),
            (t.OWNER, 0x203000),
        ):
            self.put(t.STATE + field, value)
        self.put(n.GEN, 1, seats.FIRST_ID, 1, 0, seats.FIRST_ID, 12345, 12560, 1)
        self.put(n.GEN + 36, 304)
        self.put(w.STATE + 68, 0x209000)
        self.put(0x209000 + 304 * 16, seats.FIRST_ID, 12345, 12560, 1)
        self.put(0x405B1368 + 304 * 16, seats.FIRST_ID, 12345, 12560, 1)
        self.put(0x405A0F64, 0x405DF000, 0x405DF034)
        self.put(0x405DF010, 9216, 16384)
        self.put(0x405DF030, 1)

    def put(self, at, *words):
        self.cpu.mem_write(at, struct.pack(">" + len(words) * "I", *words))

    def get(self, at):
        return struct.unpack(">I", self.cpu.mem_read(at, 4))[0]

    def call(self, at, *args):
        stack, stop = 0x20F000, 0x20FF00
        self.put(stack, stop, *args)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(r.UC_M68K_REG_A7, stack)
        self.cpu.emu_start(at, stop, count=100000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), stop)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), stack + 4)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)


class AutoRetirementFixture(NativeRetirementFixture):
    def setUp(self):
        super().setUp()
        for at, size in (
            (a.BASE, a.END - a.BASE),
            (0x40199000, 4096),
            (0x40015000, 4096),
            (0x4004D000, 4096),
        ):
            self.cpu.mem_map(at, size)
        for at, code in a.payload().items():
            self.cpu.mem_write(at, code)
        self.put(w.STATE + 12, 0)
        self.put(w.STATE + 64, 1)
        self.put(w.STATE + 80, 1)
        self.put(t.STATE + t.PHASE, 0)
        self.put(n.STATE + 32, 300, 301, 302, 303)
        self.put(a.TICK, 100)
        # Prepared singleton; original recorder state getter and its body execute.
        c = Code()
        c.imm("203c", 0x207000)
        c.emit("4e75")
        self.cpu.mem_write(a.CONTROLLER, c.finish(a.CONTROLLER))
        self.put(0x207010, 0x207100)
        for at in (a.RECORDER_STATE, 0x4004D9D6):
            self.cpu.mem_write(at, a.STOCK_GUARDS[at])
        # Queue boundary stub is native, not a host chooser or token supplier.
        c = Code()
        c.imm("2039", t.STATE + 16)
        c.imm("23c0", t.STATE + t.TOKEN)
        c.emit("7001")
        c.imm("23c0", t.STATE + t.PHASE)
        c.emit("7003")
        c.imm("23c0", w.STATE + 12)
        c.emit("7000 4e75")
        self.cpu.mem_write(t.QUEUE, c.finish(t.QUEUE))


class PerformanceFixture(AutoRetirementFixture):
    def setUp(self):
        super().setUp()
        for at, size in (
            (p.BASE, p.END - p.BASE),
            (w.DEST, 4096),
            (0x400D6000, 4096),
            (0x43164000, 8192),
            (0x4011D000, 4096),
            (0x40198000, 4096),
            (0x40041000, 4096),
            (0x4004A000, 4096),
        ):
            self.cpu.mem_map(at, size)
        for at, code in p.payload().items():
            self.cpu.mem_write(at, code)
        self.cpu.mem_write(p.PLAY_GET, p.PLAY_BYTES)
        self.put(0x43164F94, 1)
        self.put(0x43165010, 1)
        for at in (0x401988A2, 0x40041D18):
            c = Code()
            c.imm("203c", 0x207400)
            c.emit("4e75")
            self.cpu.mem_write(at, c.finish(at))
        c = Code()
        c.imm("2039", 0x207600)
        c.emit("4e75")
        self.cpu.mem_write(0x4004ABE8, c.finish(0x4004ABE8))
        c = Code()
        c.emit("202f0004")
        c.imm("41f9", 0x208000)
        c.emit("d1c0 7000 1010 4e75")
        self.cpu.mem_write(p.HELD, c.finish(p.HELD))
        self.cpu.mem_write(0x208000 + 50, b"\x01")
        for i in range(4):
            self.put(0x405B1368 + (300 + i) * 16, seats.FIRST_ID + i)
        self.slot(0, 300)

    def slot(self, track, slot):
        self.put(0x207600, track)
        self.cpu.mem_write(0x204000 + track * 0x450 + 0x80, struct.pack(">H", slot))
