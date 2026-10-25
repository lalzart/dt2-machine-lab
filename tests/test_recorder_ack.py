"""Execute diagnostic CF request/matching instructions; no host status commits."""

import struct
import unittest

from lab import recorder_ack as a
from lab import recorder_retirement as r
from lab.coldfire import audit_code

try:
    import unicorn as u
    from unicorn import m68k_const as k
except ImportError:
    u = None


@unittest.skipIf(u is None, "Requires configured ColdFire runtime")
class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
        self.cfg = a.constants()
        for at, size in (
            (r.CF_BASE, 8192),
            (self.cfg["CF_BASE"], 16384),
            (0x200000, 65536),
            (0x400CD000, 4096),
            (0x80004000, 8192),
        ):
            self.cpu.mem_map(at, size)
        self.cpu.mem_write(r.CF_ENTRY, r.sender())
        for at, code in a.cpu().items():
            audit_code(code, at)
            self.cpu.mem_write(at, code)
        self.pages = []

        def publisher(cpu, *_):
            sp = cpu.reg_read(k.UC_M68K_REG_A7)
            ret, tag, packet, order = struct.unpack(">4I", cpu.mem_read(sp, 16))
            self.pages.append((tag, bytes(cpu.mem_read(packet, 4096)), order))
            cpu.reg_write(k.UC_M68K_REG_D0, 0)
            cpu.reg_write(k.UC_M68K_REG_A7, sp + 4)
            cpu.reg_write(k.UC_M68K_REG_PC, ret)

        self.cpu.hook_add(u.UC_HOOK_CODE, publisher, begin=0x400CD638, end=0x400CD638)

    def call(self, fn, args=()):
        stack, stop = 0x20F000, 0x20FF00
        self.cpu.mem_write(stack, struct.pack(">" + "I" * (len(args) + 1), stop, *args))
        self.cpu.reg_write(k.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(k.UC_M68K_REG_A7, stack)
        regs = (k.UC_M68K_REG_D2, k.UC_M68K_REG_D3, k.UC_M68K_REG_A2, k.UC_M68K_REG_A3)
        for i, reg in enumerate(regs):
            self.cpu.reg_write(reg, 0x123400 + i)
        self.cpu.emu_start(fn, stop, count=50000)
        self.assertEqual(self.cpu.reg_read(k.UC_M68K_REG_PC), stop)
        self.assertEqual(self.cpu.reg_read(k.UC_M68K_REG_A7), stack + 4)
        for i, reg in enumerate(regs):
            self.assertEqual(self.cpu.reg_read(reg), 0x123400 + i)
        return self.cpu.reg_read(k.UC_M68K_REG_D0)

    def state(self):
        return struct.unpack(">12I", self.cpu.mem_read(self.cfg["CF_STATE"], 48))

    def begin(
        self, epoch=1, generation=0x7FFE0001, sequence=1, start=0x2400, size=16384
    ):
        args = (epoch, generation, sequence, start, size)
        self.assertEqual(self.call(a.CF_REQUEST, args), 0)
        return a.fragments(*args[:3])

    def feed(self, byte):
        self.cpu.mem_write(0x8000488C + self.cfg["CF_REPLY_BYTE"], bytes([byte]))
        return self.call(a.CF_CONSUME)

    def test_all_tuple_bits_match_and_receipt_is_idempotent(self):
        for epoch, generation, sequence in (
            (1, 0x7FFE0001, 1),
            (0xA5F0CC33, 0x7FFE0008, 0x69AA55FF),
            (0xFFFFFFFF, 0x7FFE0008, 0xFFFFFFFF),
        ):
            encoded = self.begin(epoch, generation, sequence)
            self.assertEqual(self.state()[1:4], (epoch, generation, sequence))
            for i, byte in enumerate(encoded):
                self.assertEqual(self.feed(byte), int(i == 47))
            self.assertEqual(self.state()[6:9], (2, 48, 48))
            before = self.state()
            self.assertEqual(self.feed(encoded[-1]), 1)
            self.assertEqual(self.state(), before)
        self.assertEqual(len(self.pages), 3)

    def test_stale_conflict_and_invalid_request_preserve_state(self):
        self.begin(2, 0x7FFE0001, 10)
        before = self.state()
        for args in (
            (0, 0x7FFE0001, 11, 0x2400, 16384),
            (1, 0x7FFE0001, 100, 0x2400, 16384),
            (2, 0x7FFE0001, 9, 0x2400, 16384),
            (2, 0x7FFE0002, 10, 0x2400, 16384),
            (2, 0x7FFE0001, 10, 0x6400, 16384),
            (2, 0x7FFE0001, 11, 0x2401, 16384),
            (2, 0x7FFE0009, 11, 0x2400, 16384),
        ):
            self.assertEqual(self.call(a.CF_REQUEST, args), 0xFFFFFFFF)
            self.assertEqual(self.state(), before)
        self.begin(2, 0x7FFE0001, 10)
        self.assertEqual(self.state(), before)
        self.assertEqual(len(self.pages), 1)
        self.begin(3, 0x7FFE0002, 1)
        self.assertEqual(len(self.pages), 2)

    def test_corrupt_reordered_duplicate_and_stale_cannot_confirm(self):
        old = self.begin()
        new = self.begin(sequence=2)
        for byte in old:
            self.assertEqual(self.feed(byte), 0)
        for byte in (255, new[0], new[0], new[2], new[1], new[4] ^ 1):
            self.assertEqual(self.feed(byte), 0)
        for i, byte in enumerate(new):
            self.assertEqual(self.feed(byte), int(i == 47))
        self.assertEqual(self.state()[9], 1)

    def test_stock_zero_times_out_and_keeps_expected_tuple(self):
        self.begin()
        expected = self.state()[1:6]
        for _ in range(self.cfg["TIMEOUT"] - 1):
            self.assertEqual(self.feed(0), 0)
        self.assertEqual(self.feed(0), 0xFFFFFFFF)
        self.assertEqual(self.state()[6], 3)
        self.assertEqual(self.state()[1:6], expected)
        before = self.state()
        for _ in range(3):
            self.assertEqual(self.feed(255), 0xFFFFFFFF)
            self.assertEqual(self.state(), before)
        self.assertEqual(self.state()[11], 1)
