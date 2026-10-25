"""Missing Flex references must not prevent saving other project contents."""

import struct
import unittest

from lab.flex_native import FIRST_ID, persist_project_pool, resource_lookup
from lab.project_save import SavePhases, dispatcher

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None

CODE, STACK, STOP = 0x100000, 0x20F000, 0x10F000
HEAD, NODE, POOL = 0x300000, 0x300100, 0x310000


@unittest.skipIf(u is None, "Configured native runtime required")
class MissingProjectReferencesTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for address, size in (
            (CODE, 0x10000), (0x200000, 0x10000),
            (0x300000, 0x20000), (0x40000000, 0x200000),
        ):
            self.cpu.mem_map(address, size)
        self.cpu.mem_write(POOL, struct.pack(">4I", 0xFFFFFFFF, 0, 0, 0) * 1024)
        self.cpu.mem_write(CODE + 0x4000, resource_lookup(CODE + 0x4000, HEAD))
        self.cpu.mem_write(CODE + 0x3000, bytes.fromhex("70014e75"))
        self.cpu.mem_write(CODE + 0x2000, dispatcher(
            CODE + 0x2000, SavePhases(CODE + 0x3000, (CODE,))
        ))
        self.original = struct.pack(">4I", FIRST_ID, 7, 1080, 55)
        self.durable = struct.pack(">4I", 8, 7, 1080, 99)
        self.orphan = struct.pack(">4I", FIRST_ID + 15, 9, 1080, 20)
        self.writes, self.stock = [], []
        self.fail_write = False

        def endpoint(cpu, pc, *_):
            if pc == CODE + 0x3000:
                self.stock.append(True)
                return
            sp = cpu.reg_read(r.UC_M68K_REG_A7)
            result = 0
            if pc == CODE + 0x5000:
                self.writes.append(self.word(sp + 4))
                result = 0xFFFFFFFF if self.fail_write else 0
                if not self.fail_write:
                    cpu.mem_write(self.word(sp + 12), self.durable)
            cpu.reg_write(r.UC_M68K_REG_D0, result)
            cpu.reg_write(r.UC_M68K_REG_PC, self.word(sp))
            cpu.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for pc in (CODE + 0x3000, CODE + 0x5000, 0x40157192, 0x40000E82):
            self.cpu.hook_add(u.UC_HOOK_CODE, endpoint, begin=pc, end=pc)

    def word(self, address):
        return int.from_bytes(self.cpu.mem_read(address, 4), "big")

    def put(self, address, value):
        self.cpu.mem_write(address, struct.pack(">I", value))

    def save(self, preserve_missing=True):
        self.cpu.mem_write(CODE, persist_project_pool(
            CODE, CODE + 0x4000, CODE + 0x5000, CODE + 0x6000,
            CODE + 0x6100, discarded=True, preserve_missing=preserve_missing,
        ))
        self.cpu.mem_write(STACK, struct.pack(">4I", STOP, POOL, 128, 0))
        self.cpu.reg_write(r.UC_M68K_REG_A7, STACK)
        self.cpu.emu_start(CODE + 0x2000, STOP, count=2_000_000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), STOP)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), STACK + 4)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def live(self):
        self.put(HEAD, NODE)
        self.cpu.mem_write(NODE + 4, self.original)
        self.put(NODE + 20, 0x301000)
        self.cpu.mem_write(POOL + 16, self.original)

    def test_reboot_missing_reference_preserves_all_project_bytes(self):
        self.cpu.mem_write(POOL + 500 * 16, self.orphan)
        before = bytes(self.cpu.mem_read(POOL, 0x4000))
        self.assertEqual(self.save(), 1)
        self.assertEqual(bytes(self.cpu.mem_read(POOL, 0x4000)), before)
        self.assertEqual(self.stock, [True])
        self.assertEqual(self.writes, [])

    def test_missing_reference_does_not_hide_live_take_write_failure(self):
        self.live()
        self.cpu.mem_write(POOL + 500 * 16, self.orphan)
        before = bytes(self.cpu.mem_read(POOL, 0x4000))
        self.fail_write = True
        self.assertEqual(self.save(), 0)
        self.assertEqual(bytes(self.cpu.mem_read(POOL, 0x4000)), before)
        self.assertEqual(self.stock, [])
        self.fail_write = False
        self.assertEqual(self.save(), 1)
        self.assertEqual(bytes(self.cpu.mem_read(POOL + 16, 16)), self.durable)
        self.assertEqual(bytes(self.cpu.mem_read(POOL + 500 * 16, 16)), self.orphan)

    def test_same_id_different_take_is_not_rebound_or_discarded(self):
        self.live()
        older = struct.pack(">4I", FIRST_ID, 123, 1080, 44)
        self.cpu.mem_write(POOL + 500 * 16, older)
        self.assertEqual(self.save(), 1)
        self.assertEqual(bytes(self.cpu.mem_read(POOL + 500 * 16, 16)), older)
        self.assertEqual(self.writes, [NODE])
        # A current-boot tombstone must not erase a different boot's reference.
        self.put(NODE + 56, 1)
        self.cpu.mem_write(POOL + 16, self.original)
        self.assertEqual(self.save(), 1)
        self.assertEqual(self.word(POOL + 16), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(POOL + 500 * 16, 16)), older)

    def test_legacy_strict_mode_still_rejects_missing_reference(self):
        self.cpu.mem_write(POOL + 500 * 16, self.orphan)
        self.assertEqual(self.save(preserve_missing=False), 0)
        self.assertEqual(self.stock, [])
