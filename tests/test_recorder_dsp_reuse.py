"""Guest-instruction refusal tests; stock allocator success is an integration test."""

import struct
import unittest

from lab import recorder_dsp_reuse as e
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None


@unittest.skipIf(u is None, "Requires configured ColdFire runtime")
class ReclaimRefusalTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for at, size in (
            (e.BASE, e.END - e.BASE),
            (n.BASE, 0x8000),
            (w.BASE, 0x1000),
            (q.BASE, 0x1000),
            (0x405A0000, 0x30000),
            (0x80004000, 0x1000),
            (0x200000, 0x10000),
        ):
            self.cpu.mem_map(at, size)
        self.cpu.mem_write(e.ENTRY, e.command())
        self.put(n.STATE, 1)
        self.put(0x80004704, 0x204000)
        self.put(n.GEN, 1, n.FIRST_ID, 1, 0)
        self.put(n.GEN + 36, 304)
        self.proof = [
            e.CERTIFICATE,
            n.FIRST_ID,
            1,
            7,
            9216,
            16384,
            0,
            0,
            0,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            2,
            2,
            50,
            49,
        ]
        self.put(e.PROOF, *self.proof)

    def put(self, at, *words):
        self.cpu.mem_write(at, struct.pack(">" + "I" * len(words), *words))

    def call(self, *, epoch=1, kit=0x204000, sequence=7, sr=0x2700):
        stack, stop = 0x20F000, 0x20FF00
        self.put(stack, stop, n.FIRST_ID, epoch, kit, sequence)
        before = bytes(self.cpu.mem_read(n.GEN, 512))
        proof = bytes(self.cpu.mem_read(e.PROOF, 84))
        self.cpu.reg_write(r.UC_M68K_REG_SR, sr)
        self.cpu.reg_write(r.UC_M68K_REG_A7, stack)
        preserved = [
            getattr(r, f"UC_M68K_REG_{x}")
            for x in ("D2", "D3", "D4", "D5", "D6", "D7", "A2", "A3", "A4", "A5", "A6")
        ]
        for i, reg in enumerate(preserved):
            self.cpu.reg_write(reg, 0x123000 + i * 4)
        self.cpu.emu_start(e.ENTRY, stop, count=20000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), stop)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), stack + 4)
        for i, reg in enumerate(preserved):
            self.assertEqual(self.cpu.reg_read(reg), 0x123000 + i * 4)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN, 512)), before)
        self.assertEqual(bytes(self.cpu.mem_read(e.PROOF, 84)), proof)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def test_missing_exclusive_lease_or_busy_operation_never_mutates(self):
        self.put(e.PROOF, 0)
        self.assertEqual(self.call(), 0xFFFFFFFF)
        self.put(e.PROOF, e.CERTIFICATE)
        for at in (w.STATE + 12, n.STATE + 24, q.STATE + 56, q.STOCK_BUSY):
            self.put(at, 1)
            self.assertEqual(self.call(), 0xFFFFFFFF)
            self.put(at, 0)
        self.assertEqual(self.call(sr=0x2000), 0xFFFFFFFF)

    def test_epoch_kit_sequence_and_tombstone_mismatch_refuse(self):
        for values in ({"epoch": 2}, {"kit": 0x204004}, {"sequence": 8}):
            self.assertEqual(self.call(**values), 0xFFFFFFFE)
        self.put(n.GEN, 3)
        self.assertEqual(self.call(), 0xFFFFFFFE)

    def test_each_observed_reader_or_nonprivate_root_refuses(self):
        for index in (6, 7, 8, 10, 11, 12, 13, 14, 15, 16):
            self.put(e.PROOF + index * 4, 1)
            self.assertEqual(self.call(), 0xFFFFFFFC)
            self.put(e.PROOF + index * 4, 0)

    def test_frozen_snapshot_canonical_key_refuses_even_if_cpu_slot_is_obsolete(self):
        self.put(n.SNAP, 1, n.SNAP_FIRST, 1, 0, n.FIRST_ID)
        self.assertEqual(self.call(), 0xFFFFFFFD)

    def test_stale_completion_or_nonadvanced_control_fence_refuses(self):
        for index, value in ((17, 1), (18, 0), (19, 49), (19, 48)):
            self.put(e.PROOF, *self.proof)
            self.put(e.PROOF + index * 4, value)
            self.assertEqual(self.call(), 0xFFFFFFFE)
