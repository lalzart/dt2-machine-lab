"""Native selected-buffer/transport/input tests; no fabricated bar events."""

import unittest

from buf_native_support import PerformanceFixture, r, u

from lab import buf_auto_retirement as auto
from lab import buf_performance as p
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_seat_reuse as seats
from lab import recorder_worker_code as w


@unittest.skipIf(u is None, "Requires configured native CPU runtime")
class PerformanceTests(PerformanceFixture, unittest.TestCase):
    def event(self, key, flags):
        self.put(0x208400, 0, 0, 0, key, flags, 0)
        return self.call(p.INPUT, 0x200100, 0x208400, 1)

    def test_resolves_selected_track_buf_independently_of_recorder_destination(self):
        self.put(w.DEST, 4)
        for i in range(4):
            self.slot(7, 300 + i)
            self.assertEqual(self.call(p.ELIGIBLE), i + 1)
        self.assertEqual(self.get(w.DEST), 4)

    def test_stopped_unrelated_or_uncommitted_slots_are_stock(self):
        self.put(0x43164F94, 0)
        self.put(0x43165010, 0)
        self.assertEqual(self.event(43, 1), 0)
        self.assertEqual(self.get(q.STATE), 0)
        self.put(0x43164F94, 1)
        self.slot(0, 44)
        self.assertEqual(self.call(p.ELIGIBLE), 0xFFFFFFFF)
        self.slot(0, 300)
        self.put(0x405B1368 + 300 * 16, 123)
        self.assertEqual(self.call(p.ELIGIBLE), 0xFFFFFFFF)

    def test_chord_requests_once_and_owns_both_release_orders(self):
        for releases in ((43, 50), (50, 43)):
            with self.subTest(releases=releases):
                self.setUp()
                self.assertEqual(self.event(43, 1), 1)
                self.assertEqual(self.event(43, 9), 1)
                self.assertEqual(self.event(43, 1), 1)
                self.assertEqual(self.get(q.STATE), 1)
                self.assertEqual(self.get(p.STATE + p.REQUESTS), 1)
                for key in releases:
                    self.assertEqual(self.event(key, 32), 1)
                self.assertEqual(self.get(p.STATE + p.SAMPLING_OWNED), 0)
                self.assertEqual(self.get(p.STATE + p.C_OWNED), 0)

    def test_plain_sampling_and_other_keys_are_exactly_passed_through(self):
        initial = bytes(self.cpu.mem_read(p.STATE, 128))
        for key in (50, 10, 12, 17, 20, 21, 25, 40):
            for flags in (1, 9, 16, 32):
                with self.subTest(key=key, flags=flags):
                    self.assertEqual(self.event(key, flags), 0)
        self.assertEqual(bytes(self.cpu.mem_read(p.STATE, 128)), initial)

    def test_c_without_sampling_or_with_modifiers_stays_stock(self):
        self.cpu.mem_write(0x208000 + 50, b"\0")
        self.assertEqual(self.event(43, 1), 0)
        self.cpu.mem_write(0x208000 + 50, b"\x01")
        for key in (17, 10, 12, 20, 21):
            self.cpu.mem_write(0x208000 + key, b"\x01")
            self.assertEqual(self.event(43, 1), 0)
            self.cpu.mem_write(0x208000 + key, b"\0")
        for flags in (3, 9, 16, 32):
            self.assertEqual(self.event(43, flags), 0)
        self.assertEqual(self.get(p.STATE + p.REQUESTS), 0)

    def test_native_busy_recording_and_serial_exhaustion_refuse(self):
        for at, value in (
            (w.STATE + 12, 1),
            (w.STATE + 12, 2),
            (w.STATE + 12, 3),
            (w.STATE + 80, 0),
            (n.STATE + 24, 1),
            (q.STOCK_BUSY, 1),
            (q.STATE + 56, 1),
            (q.STATE, 1),
            (0x2071A4, 1),
            (0x2071A4, 2),
            (0x2071A4, 3),
            (0x2071A4, 4),
        ):
            old = self.get(at)
            self.put(at, value)
            self.assertEqual(self.call(p.ELIGIBLE), 0xFFFFFFFF, (hex(at), value))
            self.put(at, old)
        self.put(q.STATE, 0xFFFFFFFF, 0xFFFFFFFF)
        self.assertEqual(self.call(p.ELIGIBLE), 0xFFFFFFFF)
        self.put(q.STATE, 0, 0)
        self.cpu.mem_write(0x204000 + 15 * 0x450 + 0xD6, b"\x02")
        self.assertEqual(self.call(p.ELIGIBLE), 0xFFFFFFFF)

    def test_automatic_lease_can_yield_to_explicit_chord(self):
        self.put(w.STATE + 12, 3)
        self.put(auto.STATE + auto.ACTIVE, seats.FIRST_ID + 1)
        self.assertEqual(self.event(43, 1), 1)
        self.assertEqual(self.get(q.STATE), 1)

    def test_stale_latched_epoch_and_kit_refuse_before_native_submission(self):
        for at in (p.STATE + p.EPOCH, p.STATE + p.KIT):
            self.setUp()
            self.assertEqual(self.event(43, 1), 1)
            old = self.get(at)
            self.put(at, old + 1)
            self.assertEqual(self.call(p.SUBMIT), 0xFFFFFFF8)
            self.assertEqual(self.get(w.STATE + 12), 0)
            self.assertEqual(self.get(q.STATE + 8), 0)

    def test_input_preserves_registers_and_repeats_native_state_exactly(self):
        regs = [
            getattr(r, "UC_M68K_REG_" + name)
            for name in (
                "D2",
                "D3",
                "D4",
                "D5",
                "D6",
                "D7",
                "A2",
                "A3",
                "A4",
                "A5",
                "A6",
            )
        ]
        for i, reg in enumerate(regs):
            self.cpu.reg_write(reg, 0x210000 + i * 16)
        before = [self.cpu.reg_read(reg) for reg in regs]
        self.assertEqual(self.event(43, 1), 1)
        self.assertEqual([self.cpu.reg_read(reg) for reg in regs], before)
        state = bytes(self.cpu.mem_read(p.STATE, 128))
        self.setUp()
        self.assertEqual(self.event(43, 1), 1)
        self.assertEqual(bytes(self.cpu.mem_read(p.STATE, 128)), state)
