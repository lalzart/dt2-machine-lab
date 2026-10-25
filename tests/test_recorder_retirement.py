"""Native diagnostic sender ABI and pool/identity bounds, without host commits."""

import struct
import unittest

from lab import recorder_retirement as r

try:
    import unicorn as u
    from unicorn import m68k_const as k
except ImportError:
    u = None


@unittest.skipIf(u is None, "Requires configured ColdFire runtime")
class RetirementSenderTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
        for at, size in ((r.CF_BASE, 8192), (0x200000, 0x10000), (0x400CD000, 4096)):
            self.cpu.mem_map(at, size)
        self.cpu.mem_write(r.CF_ENTRY, r.sender())
        self.pages = []

        def publisher(cpu, *_):
            sp = cpu.reg_read(k.UC_M68K_REG_A7)
            values = struct.unpack(">4I", cpu.mem_read(sp, 16))
            self.pages.append(
                (values[1], bytes(cpu.mem_read(values[2], 4096)), values[3])
            )
            cpu.reg_write(k.UC_M68K_REG_D0, 0)
            cpu.reg_write(k.UC_M68K_REG_A7, sp + 4)
            cpu.reg_write(k.UC_M68K_REG_PC, values[0])

        self.cpu.hook_add(u.UC_HOOK_CODE, publisher, begin=0x400CD638, end=0x400CD638)

    def call(self, *args):
        stack, stop = 0x20F000, 0x20FF00
        self.cpu.mem_write(stack, struct.pack(">6I", stop, *args))
        self.cpu.reg_write(k.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(k.UC_M68K_REG_A7, stack)
        regs = (k.UC_M68K_REG_D2, k.UC_M68K_REG_D3, k.UC_M68K_REG_A2, k.UC_M68K_REG_A3)
        for i, reg in enumerate(regs):
            self.cpu.reg_write(reg, 0x123400 + i)
        self.cpu.emu_start(r.CF_ENTRY, stop, count=20000)
        self.assertEqual(self.cpu.reg_read(k.UC_M68K_REG_PC), stop)
        self.assertEqual(self.cpu.reg_read(k.UC_M68K_REG_A7), stack + 4)
        for i, reg in enumerate(regs):
            self.assertEqual(self.cpu.reg_read(reg), 0x123400 + i)
        return self.cpu.reg_read(k.UC_M68K_REG_D0)

    def test_native_packet_boundary_and_padding(self):
        c = r.constants()
        args = (1, c["FIRST_ID"], 1, 0x2400, 16384)
        self.cpu.mem_write(r.CF_PACKET, bytes([0xA5]) * 4096)
        self.assertEqual(self.call(*args), 0)
        self.assertEqual(self.pages, [(c["TAG"], r.packet(*args), 1)])
        self.assertEqual(self.pages[0][1][64:], bytes(4032))

    def test_last_normal_pool_allocation_excludes_capicola(self):
        c = r.constants()
        args = (0xFFFFFFFF, c["LAST_ID"], 0xFFFFFFFF, c["POOL_END"] - 8192, 8192)
        self.assertEqual(self.call(*args), 0)
        self.assertEqual(self.pages[0][1], r.packet(*args))
        self.assertEqual(self.pages[0][1][28:32], bytes(4))

    def test_bad_extent_or_id_never_publishes_or_changes_packet(self):
        c = r.constants()
        cases = [
            (0, c["FIRST_ID"], 1, 0x2400, 8192),
            (1, c["FIRST_ID"] - 1, 1, 0x2400, 8192),
            (1, c["LAST_ID"] + 1, 1, 0x2400, 8192),
            (1, c["FIRST_ID"], 0, 0x2400, 8192),
            (1, c["FIRST_ID"], 1, 0, 8192),
            (1, c["FIRST_ID"], 1, 0x2401, 8192),
            (1, c["FIRST_ID"], 1, 0x2400, 8193),
            (1, c["FIRST_ID"], 1, c["POOL_END"], 8192),
            (1, c["FIRST_ID"], 1, c["POOL_END"] - 8192, 16384),
            (1, c["FIRST_ID"], 1, 0x2400, 0xFFFFE000),
        ]
        self.cpu.mem_write(r.CF_PACKET, bytes([0xA5]) * 4096)
        for args in cases:
            self.assertEqual(self.call(*args), 0xFFFFFFFF)
            self.assertFalse(self.pages)
            self.assertEqual(
                bytes(self.cpu.mem_read(r.CF_PACKET, 4096)), bytes([0xA5]) * 4096
            )
