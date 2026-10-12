"""Native source handover interleavings; filesystem validation/free are models."""

import struct
import unittest

from lab.flex_retirement import abort_source, pin_source, retire_source, unpin_source

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None


@unittest.skipIf(u is None, "Native execution requires configured Unicorn runtime")
class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for base, size in (
            (0x100000, 0x10000),
            (0x200000, 0x10000),
            (0x40000000, 0x200000),
        ):
            self.cpu.mem_map(base, size)
        self.node, self.source, self.stack, self.stop = (
            0x200100,
            0x204000,
            0x20F000,
            0x10F000,
        )
        self.entries = {}
        for i, fn in enumerate((pin_source, unpin_source, retire_source, abort_source)):
            pc = 0x100000 + i * 0x1000
            self.entries[fn.__name__] = pc
            self.cpu.mem_write(
                pc, fn(pc, abort=0x103000) if fn == unpin_source else fn(pc)
            )
        self.cpu.mem_write(self.stop, bytes.fromhex("4e71"))
        self.write(20, self.source)
        self.write(28, 1)
        self.cpu.mem_write(self.node + 32, struct.pack(">4I", 123, 456, 362, 1))
        self.frees = []
        self.valid = True
        self.interleave = lambda: None
        self.sr = 0x2500

        def service(uc, pc, size, data):
            sp = uc.reg_read(r.UC_M68K_REG_A7)
            self.assertEqual(uc.reg_read(r.UC_M68K_REG_SR) & 0xFF00, self.sr)
            if pc == 0x4015B178:
                self.assertEqual(self.read(52), 1)
                ref = int.from_bytes(uc.mem_read(sp + 4, 4), "big")
                self.assertEqual(
                    bytes(uc.mem_read(ref, 16)), bytes(uc.mem_read(self.node + 32, 16))
                )
                self.interleave()
                result = int(self.valid)
            else:
                self.assertEqual(self.read(20), 0)
                self.assertEqual(self.read(48), 0)
                self.frees.append(int.from_bytes(uc.mem_read(sp + 4, 4), "big"))
                result = 0
            ret = int.from_bytes(uc.mem_read(sp, 4), "big")
            uc.reg_write(r.UC_M68K_REG_D0, result & 0xFFFFFFFF)
            uc.reg_write(r.UC_M68K_REG_A7, sp + 4)
            uc.reg_write(r.UC_M68K_REG_PC, ret)

        for pc in (0x4015B178, 0x4011E8FC):
            self.cpu.hook_add(u.UC_HOOK_CODE, service, begin=pc, end=pc)

    def read(self, offset):
        return int.from_bytes(self.cpu.mem_read(self.node + offset, 4), "big")

    def write(self, offset, value):
        self.cpu.mem_write(self.node + offset, struct.pack(">I", value))

    def call(self, name):
        self.cpu.reg_write(r.UC_M68K_REG_SR, self.sr)
        self.cpu.reg_write(r.UC_M68K_REG_A7, self.stack)
        self.cpu.reg_write(r.UC_M68K_REG_D2, 0xDEAD1234)
        self.cpu.reg_write(r.UC_M68K_REG_A2, 0xBEAD1234)
        self.cpu.mem_write(self.stack, struct.pack(">2I", self.stop, self.node))
        self.cpu.emu_start(self.entries[name], self.stop, count=10000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), self.stop)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), self.stack + 4)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_SR) & 0xFF00, self.sr)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_D2), 0xDEAD1234)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A2), 0xBEAD1234)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def test_active_copy_blocks_retirement_until_unpinned(self):
        self.assertEqual(self.call("pin_source"), self.source)
        self.assertEqual(self.read(48), 1)
        self.assertEqual(self.call("retire_source"), 1)
        self.assertFalse(self.frees)
        self.assertEqual(self.call("unpin_source"), 0)
        self.assertEqual(self.call("retire_source"), 0)
        self.assertEqual(self.frees, [self.source])
        self.assertEqual(self.call("pin_source"), 0)
        self.assertEqual(self.call("retire_source"), 1)
        self.assertEqual(self.frees, [self.source])

    def test_missing_or_invalid_backing_retains_source(self):
        self.valid = False
        self.assertEqual(self.call("retire_source"), 1)
        self.assertEqual((self.read(20), self.read(52)), (self.source, 0))
        self.assertFalse(self.frees)
        self.write(28, 0)
        self.assertEqual(self.call("retire_source"), 1)
        self.assertFalse(self.frees)

    def test_recovery_matches_never_release_only_source(self):
        for status in (2, 3, 4, -1):
            self.valid = status
            self.assertEqual(self.call("retire_source"), 1)
            self.assertEqual((self.read(20), self.read(52)), (self.source, 0))
            self.assertFalse(self.frees)

    def test_reader_arrives_while_backing_is_validated(self):
        self.interleave = lambda: self.write(48, 1)
        self.assertEqual(self.call("retire_source"), 1)
        self.assertEqual((self.read(20), self.read(52)), (self.source, 0))
        self.assertFalse(self.frees)

    def test_changed_backing_or_other_retirement_owner_retains_source(self):
        self.interleave = lambda: self.write(36, 999)
        self.assertEqual(self.call("retire_source"), 1)
        self.assertFalse(self.frees)
        self.write(52, 1)
        self.assertEqual(self.call("retire_source"), 1)
        self.assertEqual(self.read(52), 1)

    def test_pin_bounds_and_interrupt_masks(self):
        for sr in (0x2000, 0x2500, 0x2700, 0x3000):
            self.sr = sr
            self.write(48, 0xFFFFFFFF)
            self.assertEqual(self.call("pin_source"), 0xFFFFFFFF)
            self.assertEqual(self.read(48), 0xFFFFFFFF)
            self.write(48, 0)
            self.assertEqual(self.call("unpin_source"), 0xFFFFFFFF)
            self.assertEqual(self.read(48), 0)

    def test_aborted_candidate_drains_existing_copy_and_rejects_new_pins(self):
        self.assertEqual(self.call("pin_source"), self.source)
        self.assertEqual(self.call("abort_source"), 1)
        self.assertEqual((self.read(20), self.read(56)), (self.source, 1))
        self.assertEqual(self.call("pin_source"), 0xFFFFFFFF)
        self.assertEqual(self.read(48), 1)
        self.assertFalse(self.frees)
        self.assertEqual(self.call("unpin_source"), 0)
        self.assertEqual(self.frees, [self.source])
        self.assertEqual(self.call("abort_source"), 0)
        self.assertEqual(self.frees, [self.source])
