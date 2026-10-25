"""Explicit BUF admission, generation latch and existing queue ownership."""

import unittest

from buf_native_support import PerformanceFixture, r, u

from lab import buf_freeze as b
from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_seat_reuse as seats
from lab import recorder_worker_code as w
from lab.emit import Code


@unittest.skipIf(u is None, "Requires configured native CPU runtime")
class BufFreezeTests(PerformanceFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        for at, size in (
            (b.BASE, b.END - b.BASE),
            (nb.BASE, 0x1000),
            (0x44F37000, 4096),
            (0x400F0000, 4096),
        ):
            self.cpu.mem_map(at, size)
        for at, raw in {**q.payload(), **b.payload()}.items():
            self.cpu.mem_write(at, raw)
        self.cpu.mem_write(n.LOOKUP, seats.lookup())
        self.native_value(0x40198A16, 0x207000)
        self.native_value(0x400F0AB8, 1)
        self.put(0x44F370A0, 0x207400)
        self.put(0x405B1368 + 301 * 16, seats.FIRST_ID, 12345, 12560, 1)
        self.put(w.DEST, 0)
        # BUF 2 is populated; selected track deliberately names another sample.
        self.slot(7, 44)
        for at, target in ((q.GATE, b.GATE), (q.DONE, b.DONE)):
            c = Code()
            c.imm("4ef9", target)
            self.cpu.mem_write(at, c.finish(at))

    def native_value(self, at, value):
        c = Code()
        c.imm("203c", value)
        c.emit("4e75")
        self.cpu.mem_write(at, c.finish(at))
        self.cpu.ctl_remove_cache(at, at + len(c.data))

    def owned(self):
        self.put(q.STATE + 8, 2)
        self.put(q.STATE + 48, 1)
        self.put(q.STATE + 28, self.get(q.CURRENT_TCB))

    def test_accepts_explicit_buf_and_pins_before_queue_with_normal_dest(self):
        self.put(0x43164F94, 0)
        self.put(0x43165010, 0)  # A committed BUF also freezes with transport stopped.
        assignments = bytes(self.cpu.mem_read(0x204000, 16 * 0x450))
        boundaries = []

        def observe(uc, pc, *_):
            boundaries.append(
                (pc, uc.reg_read(r.UC_M68K_REG_SR) & 0x2700, self.get(w.STATE + 12))
            )

        for pc in (n.LOOKUP, 0x400F0AB8):
            self.cpu.hook_add(u.UC_HOOK_CODE, observe, begin=pc, end=pc)
        self.assertEqual(self.call(b.SUBMIT, 2), 0)
        self.assertEqual(boundaries, [(n.LOOKUP, 0x2700, 0), (0x400F0AB8, 0x2000, 2)])
        self.assertEqual(self.get(w.STATE + 12), 2)
        self.assertEqual(self.get(b.STATE + b.BUFFER), 2)
        self.assertEqual(self.get(b.STATE + b.GENERATION), n.GEN)
        self.assertEqual(self.get(b.STATE + b.SLOT), 301)
        self.assertEqual(self.get(q.STATE + 16), 2)
        self.assertEqual(self.get(q.STATE + 36), 1)
        self.assertEqual(self.get(w.DEST), 0)
        self.assertEqual(bytes(self.cpu.mem_read(0x204000, 16 * 0x450)), assignments)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_SR) & 0x2700, 0x2000)
        self.owned()
        self.assertEqual(self.call(q.GATE), 0)
        self.put(w.DEST, 4)  # Preference changes after admission cannot retarget.
        self.slot(3, 99)
        self.assertEqual(self.call(q.GATE), 0)
        self.assertEqual(self.call(q.DONE, 0, 312), 0)
        self.assertEqual(self.get(b.STATE + b.ACTIVE), 0)
        self.assertEqual(self.get(w.STATE + 12), 0)
        self.assertEqual(self.get(q.STATE + 12), 312)

    def test_pending_request_survives_competing_admission_and_context(self):
        self.assertEqual(self.call(b.SUBMIT, 2), 0)
        before = bytes(self.cpu.mem_read(b.STATE, 64))
        context = bytes(self.cpu.mem_read(q.STATE + 8, 32))
        for target in (1, 2, 4):
            self.assertEqual(self.call(b.SUBMIT, target), 0xFFFFFFF9)
        self.assertEqual(bytes(self.cpu.mem_read(b.STATE, 64)), before)
        self.assertEqual(bytes(self.cpu.mem_read(q.STATE + 8, 32)), context)
        self.assertEqual(self.get(q.STATE + 36), 1)

    def test_busy_empty_invalid_and_full_refuse_without_claiming(self):
        for target in (0, 5):
            self.assertEqual(self.call(b.SUBMIT, target), 0xFFFFFFFF)
        self.assertEqual(self.call(b.SUBMIT, 1), 0xFFFFFFFE)
        for at in (
            w.STATE + 12,
            n.STATE + 24,
            q.STOCK_BUSY,
            q.STATE + 56,
            nb.STATE + nb.PHASE,
            q.STATE,
            0x2071A4,
        ):
            old = self.get(at)
            self.put(at, 1)
            self.assertEqual(self.call(b.SUBMIT, 2), 0xFFFFFFF9, hex(at))
            self.put(at, old)
        self.put(n.STATE + 4, 8)
        self.assertEqual(self.call(b.SUBMIT, 2), 0xFFFFFFFB)
        self.assertEqual(self.get(w.STATE + 12), 0)
        self.assertEqual(self.get(b.STATE + b.ACTIVE), 0)
        self.assertEqual(self.get(q.STATE + 36), 0)

    def test_complete_source_keys_status_epoch_and_length_are_required(self):
        for at, value in (
            (n.GEN, 2),
            (n.GEN + 8, 2),
            (n.GEN + 24, 0),
            (n.GEN + 28, 0),
            *(
                (0x405B1368 + slot * 16 + off, 999)
                for slot in (301, 304)
                for off in range(0, 16, 4)
            ),
        ):
            with self.subTest(at=hex(at)):
                old = self.get(at)
                self.put(at, value)
                self.assertEqual(self.call(b.SUBMIT, 2), 0xFFFFFFFE)
                self.assertEqual(self.get(w.STATE + 12), 0)
                self.put(at, old)

    def test_worker_gate_rejects_changed_project_generation_or_association(self):
        self.assertEqual(self.call(b.SUBMIT, 2), 0)
        self.owned()
        for at in (
            0x44F370A0,
            w.STATE + 68,
            n.STATE + 36,
            n.GEN + 4,
            b.STATE + b.KEY,
            b.STATE + b.PIN,
        ):
            old = self.get(at)
            self.put(at, old + 1)
            self.assertNotEqual(self.call(q.GATE), 0, hex(at))
            self.put(at, old)
        self.assertEqual(self.call(q.GATE), 0)
        self.put(0x44F370A0, 0x207500)
        self.put(q.STATE + 8, 1)
        self.put(q.STATE + 48, 0)
        self.assertEqual(self.call(q.WORKER), 0xFFFFFFFF)
        self.assertEqual(self.get(n.SNAP), 0)
        self.assertEqual(self.get(n.STATE + 4), 0)
        self.call(q.DONE, 0, 0xFFFFFFFF)
        self.assertEqual(self.get(w.STATE + 12), 0)

    def test_queue_failure_releases_claim_and_legacy_gate_still_works(self):
        self.native_value(0x400F0AB8, 0)
        self.assertEqual(self.call(b.SUBMIT, 2), 0xFFFFFFFA)
        self.assertEqual(self.get(w.STATE + 12), 0)
        self.assertEqual(self.get(b.STATE + b.ACTIVE), 0)
        self.assertEqual(self.get(q.STATE + 36), 0)
        # Existing track-derived jobs do not inherit the new source latch.
        self.put(w.STATE + 12, 2)
        self.put(q.STATE + 20, 1, 0x204000)
        self.owned()
        self.assertEqual(self.call(q.GATE), 0)
