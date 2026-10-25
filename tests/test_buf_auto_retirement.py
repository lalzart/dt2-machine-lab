"""Execute the BUF selector/cooldown/priority policy as ColdFire instructions."""

import unittest

from buf_native_support import AutoRetirementFixture, r, u

from lab import buf_auto_retirement as a
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_native_retirement as t
from lab import recorder_seat_reuse as seats
from lab import recorder_worker_code as w


@unittest.skipIf(u is None, "Requires configured native CPU runtime")
class AutoRetirementTests(AutoRetirementFixture, unittest.TestCase):
    def generation(self, index, *, status=1, epoch=1, token=None):
        token = seats.FIRST_ID + index if token is None else token
        self.put(n.GEN + index * 64, status, token, epoch)
        return token

    def finish(self, *, success=False):
        self.put(t.STATE + t.PHASE, 4 if success else 5)
        self.put(t.STATE + 12, 0 if success else 0xFFFFFFFA)
        self.put(w.STATE + 12, 0)

    def test_skips_current_frozen_stale_quarantine_and_preserves_registry(self):
        current = self.generation(0)
        frozen = self.generation(1)
        self.generation(2, status=3)
        self.generation(3, epoch=2)
        eligible = self.generation(4)
        self.put(0x405B1368 + 300 * 16, current)
        self.put(n.SNAP, 1, n.SNAP_FIRST, 1, 0, frozen)
        before = bytes(self.cpu.mem_read(n.GEN, 1024))
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ACTIVE), eligible)
        self.assertEqual(self.get(a.STATE + a.CURSOR), 5)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN, 1024)), before)
        self.assertEqual(self.get(t.STATE), 0)  # No synthetic command serial.

    def test_all_eight_frozen_is_a_bounded_noop(self):
        for i in range(8):
            token = self.generation(i)
            self.put(n.SNAP + i * 64, 1, n.SNAP_FIRST + i, 1, 0, token)
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ATTEMPTS), 0)
        self.assertEqual(self.get(w.STATE + 12), 0)

    def test_busy_and_unready_contexts_do_not_admit(self):
        for at, value in (
            (w.STATE + 12, 1),
            (n.STATE + 24, 1),
            (q.STOCK_BUSY, 1),
            (q.STATE + 56, 1),
            (q.STATE, 1),
            (t.STATE, 1),
            (w.STATE + 64, 0),
            (w.STATE + 68, 0),
            (w.STATE + 80, 0),
            (t.STATE + t.PHASE, 2),
            (t.STATE + t.PHASE, 99),
            (0x80004704, 0),
            (0x2071A4, 1),
            (0x2071A4, 2),
            (0x2071A4, 3),
            (0x2071A4, 4),
        ):
            with self.subTest(address=hex(at), value=value):
                old = self.get(at)
                self.put(at, value)
                self.call(a.STEP)
                self.assertEqual(self.get(a.STATE + a.ATTEMPTS), 0)
                self.put(at, old)
        self.cpu.mem_write(0x204000 + 15 * 0x450 + 0xD6, b"\x02")
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ATTEMPTS), 0)

    def test_out_of_namespace_tokens_are_never_queued(self):
        self.generation(0, token=seats.FIRST_ID - 1)
        self.generation(1, token=seats.LAST_ID + 1)
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ATTEMPTS), 0)

    def test_refusal_backs_off_and_rotates_to_other_obsolete_version(self):
        first, second = self.generation(0), self.generation(1)
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ACTIVE), first)
        self.put(a.TICK, 90000)
        self.finish()
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ACTIVE), second)
        self.assertEqual(self.get(a.COOLDOWNS + 4), 90000)
        self.assertEqual(self.get(a.STATE + a.REFUSALS), 1)
        self.assertEqual(self.get(a.STATE + a.LAST_TOKEN), first)
        self.finish()
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ACTIVE), 0)
        self.assertEqual(self.get(a.STATE + a.ATTEMPTS), 2)

    def test_cooldown_tick_wrap_and_exact_boundary(self):
        token = self.generation(0)
        self.put(a.COOLDOWNS, token, 0xFFFFFFF0)
        self.put(a.TICK, 0x10)
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ATTEMPTS), 0)
        self.put(a.TICK, (0xFFFFFFF0 + a.BACKOFF) & 0xFFFFFFFF)
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ACTIVE), token)

    def test_new_token_in_same_seat_bypasses_old_cooldown(self):
        token = self.generation(0, token=seats.FIRST_ID + 100)
        self.put(a.COOLDOWNS, seats.FIRST_ID, 100)
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ACTIVE), token)

    def test_queue_refusal_retains_ownership_and_is_throttled(self):
        self.cpu.mem_write(t.QUEUE, bytes.fromhex("70ff4e75"))
        before = bytes(self.cpu.mem_read(n.GEN, 512))
        self.call(a.STEP)
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ATTEMPTS), 1)
        self.assertEqual(self.get(a.STATE + a.QUEUE_DENIALS), 1)
        self.assertEqual(self.get(a.STATE + a.ACTIVE), 0)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN, 512)), before)

    def test_wait_does_not_duplicate_and_capture_or_freeze_cancels_once(self):
        self.call(a.STEP)
        self.put(t.STATE + t.PHASE, 2)
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.ATTEMPTS), 1)
        for at in (0x2071A4, q.STATE):
            with self.subTest(address=hex(at)):
                self.put(t.STATE + t.CANCEL, 0)
                old = self.get(at)
                self.put(at, 1)
                count = self.get(a.STATE + a.CANCELLATIONS)
                self.call(a.STEP)
                self.call(a.STEP)
                self.assertEqual(self.get(t.STATE + t.CANCEL), 1)
                self.assertEqual(self.get(a.STATE + a.CANCELLATIONS), count + 1)
                self.put(at, old)

    def test_success_is_observed_once_and_empty_seat_is_not_resubmitted(self):
        self.call(a.STEP)
        self.finish(success=True)
        self.put(n.GEN, 0)
        self.call(a.STEP)
        self.call(a.STEP)
        self.assertEqual(self.get(a.STATE + a.SUCCESSES), 1)
        self.assertEqual(self.get(a.STATE + a.ACTIVE), 0)
        self.assertEqual(self.get(a.STATE + a.ATTEMPTS), 1)

    def test_freeze_serial_is_deferred_without_consumption_during_auto_lease(self):
        self.cpu.mem_write(q.TRAMP, bytes.fromhex("70014e75"))
        self.cpu.mem_write(q.POLL, bytes.fromhex("70024e75"))
        self.put(q.STATE, 1)
        self.put(a.STATE + a.ACTIVE, seats.FIRST_ID)
        self.put(w.STATE + 12, 3)
        self.assertEqual(self.call(a.FREEZE_POLL), 1)
        self.assertEqual(self.get(q.STATE + 4), 0)
        self.put(w.STATE + 12, 0)
        self.assertEqual(self.call(a.FREEZE_POLL), 2)

    def test_register_stack_and_repeat_determinism(self):
        registers = [
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
        for index, reg in enumerate(registers):
            self.cpu.reg_write(reg, 0x210000 + index * 16)
        before = [self.cpu.reg_read(reg) for reg in registers]
        self.call(a.STEP)
        snapshot = bytes(self.cpu.mem_read(a.STATE, 512))
        self.assertEqual([self.cpu.reg_read(reg) for reg in registers], before)
        self.setUp()
        self.call(a.STEP)
        self.assertEqual(bytes(self.cpu.mem_read(a.STATE, 512)), snapshot)
