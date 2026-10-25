"""Execute seat/token lifecycle instructions, including ABA negative controls."""

import struct
import unittest

from lab import recorder_freeze_code as n
from lab import recorder_seat_reuse as s
from lab import recorder_worker_code as w

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None


@unittest.skipIf(u is None, "Requires configured ColdFire runtime")
class SeatTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for at, size in (
            (n.BASE, 0x8000),
            (w.BASE, 0xB000),
            (s.BASE, s.END - s.BASE),
            (0x200000, 0x10000),
            (0x4011E000, 0x1000),
            (0x405B0000, 0x10000),
            (0x80004000, 0x1000),
        ):
            self.cpu.mem_map(at, size)
        self.put(n.STATE, 1)
        self.cpu.mem_write(n.LOOKUP, s.lookup())
        self.cpu.mem_write(s.SELECT, s.select())
        self.cpu.mem_write(s.CLEAN, s.clean())
        self.cpu.mem_write(n.REGISTER, s.register())
        self.cpu.mem_write(0x4011E8FC, bytes.fromhex("70004e75"))

    def put(self, at, *words):
        self.cpu.mem_write(at, struct.pack(">" + "I" * len(words), *words))

    def call(self, at, *args):
        stack, stop = 0x20F000, 0x20FF00
        self.put(stack, stop, *args)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2700)
        self.cpu.reg_write(r.UC_M68K_REG_A7, stack)
        self.cpu.emu_start(at, stop, count=20000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), stop)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), stack + 4)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def test_full_seats_refuse_without_resetting_issued_tokens(self):
        self.put(w.STATE + 4, 100)
        for i in range(8):
            self.put(n.GEN + i * 64, 1, s.FIRST_ID + i, 1)
        before = bytes(self.cpu.mem_read(n.GEN, 512))
        self.assertEqual(self.call(s.SELECT), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN, 512)), before)
        self.assertEqual(
            bytes(self.cpu.mem_read(w.STATE + 4, 4)), struct.pack(">I", 100)
        )
        self.put(n.GEN + 5 * 64, 0)
        self.assertEqual(self.call(s.SELECT), 5)

    def test_stale_token_never_follows_reused_seat(self):
        for serial in range(100):
            token = s.FIRST_ID + serial
            self.put(n.GEN, 1, token, 1)
            self.assertEqual(self.call(n.LOOKUP, token), n.GEN)
            if serial:
                self.assertEqual(self.call(n.LOOKUP, token - 1), 0)
        for status in (0, 3):
            self.put(n.GEN, status)
            self.assertEqual(self.call(n.LOOKUP, token), 0)

    def test_exact_epoch_status_and_snapshot_identity(self):
        self.put(n.GEN + 7 * 64, 1, s.LAST_ID, 1)
        self.assertEqual(self.call(n.LOOKUP, s.LAST_ID), n.GEN + 7 * 64)
        self.put(n.STATE, 2)
        self.assertEqual(self.call(n.LOOKUP, s.LAST_ID), 0)
        self.put(n.SNAP, 1, n.SNAP_FIRST, 2)
        self.assertEqual(self.call(n.LOOKUP, n.SNAP_FIRST), n.SNAP)
        for token in (s.FIRST_ID - 1, s.LAST_ID + 1, n.FIRST_ID, 0xFFFFFFFF):
            self.assertEqual(self.call(n.LOOKUP, token), 0)

    def test_registration_uses_vacant_physical_seat_and_exact_token(self):
        token = s.FIRST_ID + 99
        self.put(s.STATE, 6)
        seat = n.GEN + 6 * 64
        self.put(seat, 3, token, 1)
        self.put(0x405B1368 + 300 * 16, token, 12345, 12560, 100)
        self.assertEqual(self.call(n.REGISTER, 1, 300, 310, 1), 0)
        self.assertEqual(self.call(n.LOOKUP, token), seat)
        self.assertEqual(
            bytes(self.cpu.mem_read(seat + 48, 16)),
            struct.pack(">4I", token, 12345, 12560, 100),
        )
        before = bytes(self.cpu.mem_read(n.GEN, 512))
        self.assertEqual(self.call(n.REGISTER, 1, 300, 310, 1), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN, 512)), before)

    def test_unlink_dead_middle_node_preserves_frozen_and_current_nodes(self):
        self.put(n.GEN, 3, s.FIRST_ID + 1, 1)
        self.put(w.STATE, 0x204000)
        self.put(0x204000, 0x204100, s.FIRST_ID + 2)
        self.put(0x204100, 0x204200, s.FIRST_ID + 1)
        self.put(0x204200, 0, s.FIRST_ID)
        freed = []

        def observe(cpu, _at, *_):
            sp = cpu.reg_read(r.UC_M68K_REG_A7)
            freed.append(struct.unpack(">I", cpu.mem_read(sp + 4, 4))[0])

        self.cpu.hook_add(u.UC_HOOK_CODE, observe, begin=0x4011E8FC, end=0x4011E8FC)
        self.assertEqual(self.call(s.CLEAN, n.GEN), 0)
        self.assertEqual(freed, [0x204100])
        self.assertEqual(
            bytes(self.cpu.mem_read(0x204000, 4)), struct.pack(">I", 0x204200)
        )
        self.assertEqual(
            bytes(self.cpu.mem_read(w.STATE, 4)), struct.pack(">I", 0x204000)
        )

    def test_token_exhaustion_and_stale_epoch_refuse_before_setup(self):
        self.cpu.mem_write(w.WORKER, s.worker())
        self.put(w.STATE + 12, 1)
        self.put(w.STATE + 60, 1)
        self.put(w.STATE + 44, 0x204000)
        self.put(0x80004704, 0x204000)
        self.put(w.STATE + 4, 65535)
        self.assertEqual(self.call(w.WORKER), 0xFFFFFFFF)
        self.put(w.STATE + 4, 0)
        self.put(w.STATE + 60, 2)
        self.assertEqual(self.call(w.WORKER), 0xFFFFFFFF)

    def test_failed_accept_releases_only_unexposed_reservation(self):
        self.cpu.mem_write(s.ACCEPT, s.accept())
        self.cpu.mem_write(w.ACCEPT, bytes.fromhex("70ff4e75"))
        self.put(s.STATE, 2)
        self.put(w.STATE + 4, 100)
        seat = n.GEN + 2 * 64
        self.put(seat, 3, s.FIRST_ID + 100, 1)
        self.assertEqual(self.call(s.ACCEPT, w.STATE, 0, 3120, 1, 306), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(seat, 4)), bytes(4))
        # Publication consumed this token: keep the failed seat quarantined.
        self.put(seat, 3, s.FIRST_ID + 99, 1)
        self.assertEqual(self.call(s.ACCEPT, w.STATE, 0, 3120, 1, 306), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(seat, 4)), struct.pack(">I", 3))
