"""Focused stopped-capture state transitions; native services are fixture seams."""

import os
import unittest

import test_buf_startup as startup

from lab import buf_next_bar as b
from lab import buf_stopped as free
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "ColdFire bridge required"
)
class StoppedCapture(unittest.TestCase):
    def fixture(self, loading=False):
        f = startup.PendingCapture().fixture()
        for at, raw in free.payload().items():
            f.cpu.mem_write(at, raw)
        f.cpu.mem_write(
            b.CHECK,
            b.check(clock_fix=True, startup_capture=True, stopped_recording=True),
        )
        f.cpu.mem_write(
            b.STEP,
            b.step(
                performance_controls=True, startup_capture=True, stopped_recording=True
            ),
        )
        for at in (0x43164F94, 0x43165010, b.STATE + b.VALID):
            f.put(at, 0)
        if not loading:
            startup.PendingCapture().finish_batch(f)
        return f

    def start(self, f, buf=2, menu=0):
        self.assertEqual(f.call(free.DISPATCH, 0x207000, buf, menu), 0)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.START_MODE), free.MODE)
        self.assertEqual(f.get(b.STATE + b.PHASE), 2)

    def finish(self, f):
        # A later track/BUF/menu selection must not redirect the admitted take.
        self.assertEqual(f.call(free.DISPATCH, 0x207000, 4, 1), 0)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.PHASE), 3)
        f.put(0x2071A4, 4)
        f.call(b.STEP)

    def publish(self, f):
        self.assertEqual(f.get(b.STATE + b.PHASE), 4)
        self.assertEqual(f.call(b.WORKER), 0)
        f.call(b.DONE, 0x207700, 0)

    def test_stopped_start_early_finish_publish_once_without_bar_clock(self):
        f = self.fixture()
        self.start(f)
        f.put(b.TICK, 3000)
        f.put(0x207038, 2000)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.STOPS), 0)
        self.finish(f)
        self.publish(f)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.USES), 1)
        self.assertEqual(f.get(b.STATE + b.DEST), 2)
        self.assertEqual(f.get(w.DEST), 0)

    def test_stopped_mode_stays_latched_across_transport_and_clock_changes(self):
        f = self.fixture()
        self.start(f, menu=1)
        for at, value in ((0x43164F94, 1), (b.STATE + b.CEPOCH, 200)):
            f.put(at, value)
        f.native_value(b.CLOCK_MODE, 99)
        f.call(b.STEP)
        self.finish(f)
        self.publish(f)
        self.assertEqual(f.get(b.STATE + b.CANCELS), 0)

    def test_LEN_automatic_finish_and_native_completed_take_publish(self):
        for native in (False, True):
            f = self.fixture()
            self.start(f)
            if native:
                f.put(0x207038, 96000)
                f.put(0x2071A4, 4)
                f.cpu.mem_write(b.STOP, bytes.fromhex("4afc"))
            else:
                for elapsed in range(6000, 96001, 6000):
                    f.put(b.TICK, 1000 + elapsed)
                    f.call(b.STEP)
                f.put(0x207038, 96000)
                f.put(0x2071A4, 4)
            f.call(b.STEP)
            if f.get(b.STATE + b.PHASE) == 3:
                f.call(b.STEP)
            self.publish(f)
            self.assertEqual(f.get(b.STATE + b.STOPS), 1)
            self.assertEqual(f.get(b.STATE + b.USES), 1)

    def test_successful_take_releases_DSP_command_before_next_start(self):
        f = self.fixture()
        self.start(f, buf=1)
        self.assertEqual(f.get(0x402A1490), 0)
        # Model the native finite-LEN completion, without invoking STOP's
        # command-2 wrapper. This is the path the prior native flow missed.
        f.put(b.TICK, 97000)
        f.put(0x207038, 96000)
        f.put(0x2071A4, 4)
        f.call(b.STEP)
        if f.get(b.STATE + b.PHASE) == 3:
            f.call(b.STEP)
        self.publish(f)
        self.assertEqual(f.get(0x402A1490), 2,
                         "published take must release native recorder command")
        self.assertEqual(f.get(0x2071A4), 0)
        self.assertEqual(f.get(0x207038), 0)
        self.assertEqual(f.get(b.STATE + b.USES), 1)
        self.assertEqual(f.get(w.DEST), 0)
        self.start(f, buf=1)
        self.assertEqual(f.get(0x402A1490), 0)
        self.assertEqual(f.get(b.STATE + b.STARTS), 2)

    def test_loading_retains_finished_free_take_until_native_batch_returns(self):
        f = self.fixture(loading=True)
        self.start(f)
        self.finish(f)
        self.assertEqual(f.get(b.STATE + b.PHASE), startup.p.WAIT_LOAD)
        self.assertEqual(f.call(free.DISPATCH, 0x207000, 3, 0), b.ARM_BUSY & 0xFFFFFFFF)
        startup.PendingCapture().finish_batch(f)
        f.call(b.STEP)
        self.publish(f)
        self.assertEqual(f.get(b.STATE + b.USES), 1)

    def test_guards_preserve_pending_normal_take_and_foreign_operations(self):
        for at, value in (
            (0x2071A4, 4),
            (w.STATE + 12, 2),
            (q.STATE + 56, 1),
            (q.STOCK_BUSY, 1),
        ):
            with self.subTest(address=hex(at)):
                f = self.fixture()
                f.put(at, value)
                before = bytes(f.cpu.mem_read(0x207000, 0x200))
                self.assertEqual(
                    f.call(free.DISPATCH, 0x207000, 1, 0), b.ARM_BUSY & 0xFFFFFFFF
                )
                self.assertEqual(bytes(f.cpu.mem_read(0x207000, 0x200)), before)
                self.assertEqual(f.get(b.STATE + b.OWN), 0)

    def test_context_changes_and_explicit_cancel_never_publish(self):
        for at, value in (
            (0x44F370A0, 28),
            (0x80004704, 0x204100),
            (n.STATE, 2),
            (w.DEST, 3),
            (0x209000 - 36, 9),
            (b.STATE + b.CANCEL, 1),
        ):
            with self.subTest(address=hex(at)):
                f = self.fixture()
                self.start(f)
                f.put(at, value)
                f.call(b.STEP)
                self.assertEqual(f.get(b.STATE + b.CANCEL), 1)
                self.assertIn(f.get(b.STATE + b.PHASE), (0, 5))
                self.assertEqual(f.get(b.STATE + b.USES), 0)

    def test_short_take_and_unexpected_native_completion_are_rejected(self):
        for state, count in ((2, 140), (3, 48000), (4, 48000)):
            f = self.fixture()
            self.start(f)
            f.put(0x207038, count)
            if state == 2:
                self.finish(f)
            else:
                f.put(0x2071A4, state)
                f.call(b.STEP)
            self.assertEqual(f.get(b.STATE + b.USES), 0)

    def test_sample_clock_wrap_hard_limit_tempo_and_LEN_guards(self):
        f = self.fixture()
        start = 0xFFFFF000
        f.put(b.TICK, start)
        self.start(f)
        for elapsed in range(6000, 96001, 6000):
            f.put(b.TICK, (start + elapsed) & 0xFFFFFFFF)
            f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.STOPS), 1)
        for change in ("capacity", "tempo", "cadence"):
            f = self.fixture()
            self.start(f)
            if change == "capacity":
                f.put(b.TICK, 1000 + b.MAX_CAPTURE_FRAMES + 1)
            elif change == "tempo":
                f.put(0x402B62BC, 14520)
            else:
                f.put(b.TICK, 1000 + b.LATENCY + 1)
            f.call(b.STEP)
            self.assertEqual(f.get(b.STATE + b.USES), 0)
            self.assertEqual(f.get(b.STATE + b.CANCELS), 1)
        for raw in (0, 7, 8):
            f = self.fixture()
            f.put(0x209000 - 24, raw)
            self.assertEqual(
                f.call(free.DISPATCH, 0x207000, 1, 0), b.ARM_LENGTH & 0xFFFFFFFF
            )
            self.assertEqual(f.get(b.STATE + b.OWN), 0)

    def test_running_BAR_and_NOW_keep_clock_and_busy_behavior(self):
        for menu in (0, 1):
            f = self.fixture()
            f.put(0x43164F94, 1)
            f.put(b.STATE + b.VALID, 1)
            self.assertEqual(f.call(free.DISPATCH, 0x207000, 1, menu), 0)
            self.assertEqual(f.get(b.STATE + b.START_MODE), menu)
            before = bytes(f.cpu.mem_read(b.STATE, 132))
            self.assertEqual(
                f.call(free.DISPATCH, 0x207000, 2, menu), b.ARM_BUSY & 0xFFFFFFFF
            )
            self.assertEqual(bytes(f.cpu.mem_read(b.STATE, 132)), before)
            f.put(0x43164F94, 0)
            self.assertEqual(f.call(b.CHECK), 0xFFFFFFFF)
