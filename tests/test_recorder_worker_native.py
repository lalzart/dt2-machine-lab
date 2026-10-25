"""Native worker admission/ownership ABI. Full firmware tests live in scripts/."""

import struct
import unittest

from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab.coldfire import audit_code

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None


@unittest.skipIf(u is None, "Requires configured ColdFire runtime")
class NativeWorkerTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for at, size in (
            (w.BASE, w.END - w.BASE),
            (n.BASE, 0x8000),
            (0x200000, 0x10000),
            (0x80004000, 0x1000),
        ):
            self.cpu.mem_map(at, size)
        self.stop, self.stack = 0x20FF00, 0x20F000
        for at, data in w.payload().items():
            self.cpu.mem_write(at, data)
        self.cpu.mem_write(w.TRAMP + 32, bytes.fromhex("702a4e75"))

    def put(self, at, *values):
        self.cpu.mem_write(at, struct.pack(">" + "I" * len(values), *values))

    def call(self, at, *args, d0=0):
        self.put(self.stack, self.stop, *args)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(r.UC_M68K_REG_A7, self.stack)
        self.cpu.reg_write(r.UC_M68K_REG_D0, d0)
        regs = (
            r.UC_M68K_REG_D2,
            r.UC_M68K_REG_D3,
            r.UC_M68K_REG_D4,
            r.UC_M68K_REG_D5,
            r.UC_M68K_REG_D6,
            r.UC_M68K_REG_D7,
            r.UC_M68K_REG_A2,
            r.UC_M68K_REG_A3,
            r.UC_M68K_REG_A4,
            r.UC_M68K_REG_A5,
            r.UC_M68K_REG_A6,
        )
        for i, reg in enumerate(regs):
            self.cpu.reg_write(reg, 0x123000 + i * 4)
        self.cpu.emu_start(at, self.stop, count=50000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), self.stop)
        for i, reg in enumerate(regs):
            self.assertEqual(self.cpu.reg_read(reg), 0x123000 + i * 4)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), self.stack + 4)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def test_idle_worker_forwards_stock_and_stale_epoch_refuses_before_loader(self):
        self.assertEqual(self.call(w.WORKER), 42)
        self.put(w.STATE + 12, 1)
        self.put(w.STATE + 60, 1)
        self.put(n.STATE, 2)
        before = bytes(self.cpu.mem_read(w.STATE, 192))
        self.assertEqual(self.call(w.WORKER), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(w.STATE, 192)), before)

    def test_reused_kit_address_still_checks_epoch_and_kit_change_refuses(self):
        self.put(w.STATE + 12, 1)
        self.put(w.STATE + 60, 1)
        self.put(n.STATE, 1)
        self.put(w.STATE + 44, 0x1234)
        self.put(0x80004704, 0x5678)
        self.assertEqual(self.call(w.WORKER), 0xFFFFFFFF)

    def test_tombstone_sources_never_reopen_even_during_another_worker(self):
        node = 0x204000
        self.put(w.STATE, node)
        self.put(node, 0, n.FIRST_ID)
        self.put(node + 20, 0)
        self.assertEqual(self.call(w.LOOKUP, d0=n.FIRST_ID), n.FIRST_ID)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A0), 0)
        self.put(node + 20, 0x205000)
        self.call(w.LOOKUP, d0=n.FIRST_ID)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A0), node)
        self.call(w.LOOKUP, d0=n.FIRST_ID + 1)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A0), 0)

    def test_payload_regions_are_bounded_and_copy_accept_are_audited(self):
        parts = sorted(w.payload().items())
        self.assertTrue(
            all(w.BASE <= pc < pc + len(data) <= w.END for pc, data in parts)
        )
        self.assertTrue(
            all(
                pc + len(data) <= later
                for (pc, data), (later, _) in zip(parts, parts[1:], strict=False)
            )
        )
        for at in (w.COPY, w.ACCEPT, w.WORKER, w.ASSIGN, w.RETIRE, w.SETUP):
            audit_code(dict(parts)[at], at)

    def test_logical_header_is_held_and_incomplete_header_is_never_published(self):
        self.cpu.mem_write(w.TRAMP + 96, bytes.fromhex("702a4e75"))
        self.put(w.STATE + 12, 1)
        self.put(w.STATE + 36, 300)
        header = struct.pack(">5I", 300, 1, 2, 48000, 3120).ljust(4096, b"\0")
        self.cpu.mem_write(0x204000, header)
        self.assertEqual(self.call(w.PAGE_FILTER, 0xFFFFFFFF, 0x204000, 1), 0)
        self.assertEqual(bytes(self.cpu.mem_read(w.HEADER, 4096)), header)
        self.assertEqual(
            bytes(self.cpu.mem_read(w.STATE + 160, 4)), struct.pack(">I", 1)
        )
        self.put(w.STATE + 160, 0)
        self.put(w.STATE + 76, 5)
        self.assertEqual(self.call(w.PAGE_FILTER, 0xFFFFFFFF, 0x204000, 1), 0)
        self.assertEqual(bytes(self.cpu.mem_read(w.STATE + 160, 4)), bytes(4))
        self.put(0x204000, 304)
        self.assertEqual(self.call(w.PAGE_FILTER, 0xFFFFFFFF, 0x204000, 1), 42)

    def test_native_freeze_refuses_a_pending_recorder_worker(self):
        self.put(w.STATE + 12, 1)
        self.assertEqual(self.call(w.FREEZE_GUARD, 1, 1, 0), 0xFFFFFFFF)
