"""Native irreversible discard, busy guards, aliases and stale handle safety."""

import struct
import unittest

from lab.flex_discard import discard
from lab.flex_native import persist_project_pool, resource_lookup
from lab.flex_resources import dispatch, entry
from lab.flex_retirement import abort_source, pin_source, unpin_source

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None

CODE, STOP, STACK = 0x100000, 0x10F000, 0x20F000
STATE, NODE, KIT, POOL, SOURCE = 0x300000, 0x300100, 0x306000, 0x320000, 0x380000
LOADED = 0x405B1368


@unittest.skipIf(u is None, "Configured native runtime required")
class DiscardTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for base, size in (
            (CODE, 0x10000),
            (0x200000, 0x10000),
            (0x300000, 0x100000),
            (0x40000000, 0x200000),
            (0x405B0000, 0x10000),
            (0x80004000, 0x1000),
        ):
            self.cpu.mem_map(base, size)
        self.ref = struct.pack(">4I", 0x7FFE0001, 7, 1080, 55)
        self.cpu.mem_write(NODE + 4, self.ref)
        self.write(NODE + 20, SOURCE)
        self.write(NODE + 24, 9)
        self.write(STATE, NODE)
        self.write(STATE + 4, 1)
        self.write(0x80004704, KIT)
        self.cpu.mem_write(POOL, b"\xff" * 0x4000)
        self.cpu.mem_write(LOADED, b"\xff" * 0x4000)
        for slot in (9, 19):
            self.cpu.mem_write(POOL + slot * 16, self.ref)
            self.cpu.mem_write(LOADED + slot * 16, self.ref)
        for track, slot in ((8, 9), (2, 19), (4, 50)):
            self.cpu.mem_write(KIT + track * 0x450 + 0x80, struct.pack(">H", slot))
        self.other = struct.pack(">4I", 12, 34, 1080, 99)
        self.cpu.mem_write(POOL + 50 * 16, self.other)
        self.cpu.mem_write(LOADED + 50 * 16, self.other)
        self.cpu.mem_write(
            CODE, discard(CODE, CODE + 0x1000, CODE + 0x2000, CODE + 0x3000, STATE)
        )
        self.cpu.mem_write(CODE + 0x2000, resource_lookup(CODE + 0x2000, STATE))
        self.cpu.mem_write(CODE + 0x3000, abort_source(CODE + 0x3000))
        self.cpu.mem_write(CODE + 0x4000, pin_source(CODE + 0x4000))
        self.cpu.mem_write(
            CODE + 0x5000, unpin_source(CODE + 0x5000, abort=CODE + 0x3000)
        )
        self.cpu.mem_write(
            CODE + 0x6000,
            dispatch(
                CODE + 0x6000,
                CODE + 0x2000,
                CODE + 0x9000,
                durable_reader=CODE + 0xA300,
                source_pin=CODE + 0x4000,
                source_unpin=CODE + 0x5000,
            ),
        )
        for index, op in enumerate(("read", "open")):
            pc = CODE + 0x7000 + index * 0x100
            self.cpu.mem_write(pc, entry(pc, op, CODE + 0x6000))
        self.cpu.mem_write(
            CODE + 0x8000,
            persist_project_pool(
                CODE + 0x8000,
                CODE + 0x2000,
                CODE + 0xA000,
                CODE + 0xA100,
                CODE + 0xA200,
                discarded=True,
            ),
        )
        self.current_pool, self.calls = POOL, []

        def service(cpu, pc, *_):
            sp = cpu.reg_read(r.UC_M68K_REG_A7)
            result = 0
            if pc == CODE + 0x1000:
                result = self.current_pool
            elif pc == 0x40153BEA:
                slot = self.read(sp + 4)
                self.calls.append(("unload", slot))
                cpu.mem_write(
                    LOADED + slot * 16, struct.pack(">4I", 0xFFFFFFFF, 0, 0, 0)
                )
            elif pc == 0x4011E8FC:
                self.assertEqual(self.read(NODE + 20), 0)
                self.calls.append(("free", self.read(sp + 4)))
            elif pc == 0x4002D438:
                self.calls.append(("refresh", self.read(sp + 8)))
            elif pc == CODE + 0xA000:
                self.fail("Discarded take reached file writer")
            cpu.reg_write(r.UC_M68K_REG_D0, result)
            cpu.reg_write(r.UC_M68K_REG_PC, self.read(sp))
            cpu.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for pc in (
            CODE + 0x1000,
            CODE + 0xA000,
            0x40153BEA,
            0x401540C6,
            0x4011E8FC,
            0x4002D438,
        ):
            self.cpu.hook_add(u.UC_HOOK_CODE, service, begin=pc, end=pc)

    def write(self, address, value):
        self.cpu.mem_write(address, struct.pack(">I", value))

    def read(self, address):
        return int.from_bytes(self.cpu.mem_read(address, 4), "big")

    def call(self, pc, *args):
        self.cpu.mem_write(STACK, struct.pack(">" + "I" * (len(args) + 1), STOP, *args))
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2500)
        self.cpu.reg_write(r.UC_M68K_REG_A7, STACK)
        regs = [
            getattr(r, f"UC_M68K_REG_{kind}{i}")
            for kind, first, end in (("D", 2, 8), ("A", 2, 7))
            for i in range(first, end)
        ]
        for reg in regs:
            self.cpu.reg_write(reg, 0xBAD000 + reg)
        self.cpu.emu_start(pc, STOP, count=200000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), STOP)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), STACK + 4)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_SR) & 0xFF00, 0x2500)
        for reg in regs:
            self.assertEqual(self.cpu.reg_read(reg), 0xBAD000 + reg)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def test_discards_all_exact_aliases_and_releases_source_once(self):
        before = bytes(self.cpu.mem_read(KIT, 16 * 0x450))
        self.assertEqual(self.call(CODE, NODE, POOL), 0)
        self.assertEqual(
            self.calls,
            [
                ("refresh", 8),
                ("unload", 9),
                ("refresh", 2),
                ("unload", 19),
                ("free", SOURCE),
            ],
        )
        for slot in (9, 19):
            self.assertEqual(self.read(POOL + slot * 16), 0xFFFFFFFF)
            self.assertEqual(self.read(LOADED + slot * 16), 0xFFFFFFFF)
        after = bytearray(before)
        for track in (8, 2):
            after[track * 0x450 + 0x80 : track * 0x450 + 0x82] = bytes(2)
        self.assertEqual(bytes(self.cpu.mem_read(KIT, len(after))), after)
        self.assertEqual(bytes(self.cpu.mem_read(POOL + 50 * 16, 16)), self.other)
        self.assertEqual((self.read(NODE + 20), self.read(NODE + 56)), (0, 1))
        self.assertEqual(self.read(STATE + 4), 1)
        self.assertEqual(self.call(CODE, NODE, POOL), 0xFFFFFFFF)
        self.assertEqual(self.calls.count(("free", SOURCE)), 1)

    def test_busy_saved_stale_and_changed_project_leave_everything_intact(self):
        for address in (NODE + 28, NODE + 48, NODE + 52, NODE + 56, STATE + 12):
            self.write(address, 1)
            before = bytes(self.cpu.mem_read(STATE, 0x50000))
            self.assertEqual(self.call(CODE, NODE, POOL), 0xFFFFFFFF)
            self.assertEqual(bytes(self.cpu.mem_read(STATE, len(before))), before)
            self.assertEqual(self.calls, [])
            self.write(address, 0)
        self.current_pool = POOL + 0x4000
        self.assertEqual(self.call(CODE, NODE, POOL), 0xFFFFFFFF)
        self.assertEqual(self.calls, [])

    def test_stale_handles_reject_reused_source_memory(self):
        handle, ref, output = 0x350000, 0x350100, 0x350200
        self.cpu.mem_write(ref, self.ref)
        self.assertEqual(self.call(CODE + 0x7100, ref, handle), 0)
        self.assertEqual(self.call(CODE, NODE, POOL), 0)
        self.cpu.mem_write(SOURCE, b"NEW TAKE" * 100)
        self.cpu.mem_write(output, b"KEEP" * 8)
        self.assertEqual(self.call(CODE + 0x7000, output, 32, handle), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(output, 32)), b"KEEP" * 8)
        self.assertEqual(self.call(CODE + 0x7100, ref, handle), 0xFFFFFFFF)

    def test_project_save_scrubs_restored_tombstone_without_writing_audio(self):
        self.assertEqual(self.call(CODE, NODE, POOL), 0)
        self.cpu.mem_write(POOL + 99 * 16, self.ref)
        self.assertEqual(self.call(CODE + 0x8000, POOL), 0)
        self.assertEqual(self.read(POOL + 99 * 16), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(POOL + 50 * 16, 16)), self.other)

    def test_null_or_unregistered_capture_never_mutates_project(self):
        for node, pool in ((0, POOL), (NODE, 0), (NODE + 0x100, POOL)):
            self.assertEqual(self.call(CODE, node, pool), 0xFFFFFFFF)
            self.assertEqual(self.calls, [])
            self.assertEqual(self.read(NODE + 20), SOURCE)
