"""Execute metadata/ABI guards without any resource or snapshot host callback."""

import struct
import unittest

from lab import recorder_freeze_code as n

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None


@unittest.skipIf(u is None, "Requires configured ColdFire Unicorn runtime")
class NativeFreezeMetadataTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for base, size in (
            (n.BASE, 0x8000),
            (0x200000, 0x10000),
            (0x405B0000, 0x10000),
        ):
            self.cpu.mem_map(base, size)
        self.stop, self.fallback, self.stack = (
            n.BASE + 0x7FF0,
            n.BASE + 0x7E00,
            0x20F000,
        )
        self.cpu.mem_write(self.fallback, bytes.fromhex("702a4e75"))
        self.cpu.mem_write(n.LOOKUP, n.lookup())
        self.cpu.mem_write(n.REGISTER, n.register())
        self.cpu.mem_write(n.STATE, struct.pack(">I", 1))
        self.key = struct.pack(">4I", n.FIRST_ID, 0x12345679, 1024, 1)
        self.logical = struct.pack(">4I", n.SNAP_FIRST, 1, 1, 0)
        self.cpu.mem_write(n.SNAP, struct.pack(">4I", 1, n.SNAP_FIRST, 1, 0))
        self.cpu.mem_write(n.SNAP + 16, self.key)
        self.cpu.mem_write(n.SNAP + 32, struct.pack(">I", n.NAMES))
        self.cpu.mem_write(n.SNAP + 48, self.logical)
        self.cpu.mem_write(n.NAMES, b"/TEMP/B1-001\0".ljust(32, b"\0"))
        self.handlers = {}
        for index, operation in enumerate(n.RESOURCE_SITES):
            pc = n.HANDLERS + index * 512
            self.cpu.mem_write(pc, n.resource(operation, pc, self.fallback))
            self.handlers[operation] = pc

    def call(self, pc, *args):
        self.cpu.mem_write(
            self.stack, struct.pack(">" + "I" * (len(args) + 1), self.stop, *args)
        )
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2700)
        self.cpu.reg_write(r.UC_M68K_REG_A7, self.stack)
        preserved = {}
        for index, reg in enumerate(
            (
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
        ):
            preserved[reg] = 0x123000 + index * 4
            self.cpu.reg_write(reg, preserved[reg])
        self.cpu.emu_start(pc, self.stop, count=10000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), self.stop)
        for reg, value in preserved.items():
            self.assertEqual(self.cpu.reg_read(reg), value)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def test_distinct_logical_reference_resolves_exact_key_and_name_natively(self):
        self.cpu.mem_write(0x204000, self.logical)
        self.assertEqual(self.call(self.handlers["resolve"], 0x204000, 0x204100), 1)
        self.assertEqual(bytes(self.cpu.mem_read(0x204100, 4)), self.logical[:4])
        self.assertEqual(self.call(self.handlers["key"], n.SNAP_FIRST, 0x204100), 0)
        self.assertEqual(bytes(self.cpu.mem_read(0x204100, 16)), self.key)
        self.assertEqual(
            self.call(self.handlers["name"], n.SNAP_FIRST, 0, 0x204100), 0x204100
        )
        self.assertEqual(
            bytes(self.cpu.mem_read(0x204100, 32)), b"/TEMP/B1-001\0".ljust(32, b"\0")
        )

    def test_corrupt_words_epoch_and_tombstone_never_resolve(self):
        for offset in range(0, 16, 4):
            ref = bytearray(self.logical)
            # Keep the ID corruption inside our claimed snapshot namespace;
            # other namespaces intentionally fall through to original stock.
            ref[offset + 3] ^= 2 if offset == 0 else 0x40
            self.cpu.mem_write(0x204000, bytes(ref))
            self.cpu.mem_write(0x204100, b"\xa5" * 16)
            self.assertEqual(
                self.call(self.handlers["resolve"], 0x204000, 0x204100), 0xFFFFFFFF
            )
            self.assertEqual(bytes(self.cpu.mem_read(0x204100, 16)), b"\xa5" * 16)
        self.cpu.mem_write(n.STATE, struct.pack(">I", 2))
        self.assertEqual(
            self.call(self.handlers["key"], n.SNAP_FIRST, 0x204100), 0xFFFFFFFF
        )
        self.cpu.mem_write(n.STATE, struct.pack(">I", 1))
        self.cpu.mem_write(n.SNAP, struct.pack(">I", 3))
        self.assertEqual(
            self.call(self.handlers["key"], n.SNAP_FIRST, 0x204100), 0xFFFFFFFF
        )

    def test_no_pcm_handle_and_original_file_namespace_falls_through(self):
        self.cpu.mem_write(0x204000, self.logical)
        self.cpu.mem_write(0x204200, self.logical[:4] + bytes(28))
        for op, args in (
            ("size", (n.SNAP_FIRST,)),
            ("open", (0x204000, 0x204100)),
            ("read", (0x204100, 16, 0x204200)),
            ("close", (0x204200,)),
        ):
            self.assertEqual(self.call(self.handlers[op], *args), 0xFFFFFFFF)
        self.assertEqual(self.call(self.handlers["key"], 6, 0x204100), 42)

    def test_registration_preserves_cache_keys_and_refuses_identity_reuse(self):
        for slot in (300, 1023):
            self.cpu.mem_write(0x405B1368 + slot * 16, self.key)
        self.assertEqual(self.call(n.REGISTER, 1, 300, 1023, 1), 0)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN + 16, 16)), self.key)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN + 48, 16)), self.key)
        for slot in (300, 1023):
            self.assertEqual(
                bytes(self.cpu.mem_read(0x405B1368 + slot * 16, 16)), self.key
            )
        before = bytes(self.cpu.mem_read(n.GEN, 64))
        self.assertEqual(self.call(n.REGISTER, 1, 300, 1023, 1), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN, 64)), before)
