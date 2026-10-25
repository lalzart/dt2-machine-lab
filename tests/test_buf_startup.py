"""ColdFire ownership checks with explicit prepared service boundaries."""

import os
import unittest

import test_sketch_controls as controls

from lab import buf_next_bar as b
from lab import buf_startup as p
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab.emit import Code


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "Rust ColdFire bridge required"
)
class PendingCapture(unittest.TestCase):
    def fixture(self):
        f = controls.PerformanceControls().recorder()
        f.cpu.mem_map(p.CODE, 0x4000)
        f.cpu.mem_map(0x44F37000, 4096)
        for at, raw in p.payload().items():
            f.cpu.mem_write(at, raw)
        f.native_value(p.POOL_GET, 0x209000)
        f.put(0x44F370A0, 27)
        for at, raw in {
            b.ARM_ONLY: bytes.fromhex("4ef9") + p.ARM_BODY.to_bytes(4, "big"),
            b.CHECK: b.check(clock_fix=True, startup_capture=True),
            b.STEP: b.step(performance_controls=True, startup_capture=True),
            b.CANCEL_FN: b.cancel(startup_capture=True),
            b.WORKER: b.worker(startup_capture=True),
            b.USE_GATE: b.use_gate(startup_capture=True),
        }.items():
            f.cpu.mem_write(at, raw)
        c = Code()
        c.imm("2039", 0x207680)
        c.emit("5280")
        c.imm("23c0", 0x207680)
        c.emit("7001")
        c.imm("23c0", w.STATE + 64)
        c.imm("203c", 0x209000)
        c.imm("23c0", w.STATE + 68)
        c.emit("7000 4e75")
        f.cpu.mem_write(p.INIT_STOCK, c.finish(p.INIT_STOCK))
        for off in (64, 68, 80):
            f.put(w.STATE + off, 0)
        f.put(b.STATE + p.BATCH_SERIAL, 1)
        f.put(b.STATE + p.BATCH_ACTIVE, 1)
        f.put(q.STATE + 56, 259)
        f.put(q.STOCK_BUSY, 1)
        return f

    def stop_early(self, f):
        self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), 0)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.STARTS), 1)
        f.put(0x207038, 96000)
        f.put(0x2071A4, 4)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.PHASE), p.WAIT_LOAD)

    def finish_batch(self, f):
        f.put(b.STATE + p.BATCH_ACTIVE, 0)
        f.put(b.STATE + p.BATCH_DONE, 1)
        f.put(q.STATE + 56, 0)
        f.put(q.STOCK_BUSY, 0)

    def test_capture_before_setup_and_inter_load_gap_then_publish_once(self):
        f = self.fixture()
        self.stop_early(f)
        self.assertEqual(f.get(w.STATE + 64), 0)
        self.assertEqual(f.get(w.STATE + 12), 0)
        f.put(q.STATE + 56, 0)
        f.put(q.STOCK_BUSY, 0)
        for _ in range(3):
            f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.PHASE), p.WAIT_LOAD)
        self.assertEqual(f.get(0x207680), 0)
        self.finish_batch(f)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.PHASE), 4)
        self.assertEqual(f.get(0x207680), 1)
        self.assertEqual(f.get(w.STATE + 12), 1)
        self.assertEqual(f.call(b.WORKER), 0)
        f.call(b.DONE, 0x207700, 0)
        self.assertEqual(f.get(b.STATE + b.USES), 1)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.USES), 1)
        self.assertEqual(f.get(w.DEST), 0)

    def test_second_capture_start_freeze_use_cannot_replace_pending_take(self):
        f = self.fixture()
        self.stop_early(f)
        before = bytes(f.cpu.mem_read(b.STATE, 132))
        self.assertEqual(f.call(b.ARM_NOW, 0x207000, 2), b.ARM_BUSY & 0xFFFFFFFF)
        self.assertEqual(bytes(f.cpu.mem_read(b.STATE, 132)), before)
        self.assertEqual(f.call(p.START_GATE, 0x207000), 0xFFFFFFFF)
        self.assertEqual(f.call(p.ARM_GATE, 0x207000), b.ARM_BUSY & 0xFFFFFFFF)
        self.assertEqual(f.call(p.FREEZE_GATE, 1), b.ARM_BUSY & 0xFFFFFFFF)
        f.cpu.mem_write(0x400232D2, bytes.fromhex("70014e75"))
        self.assertEqual(f.call(b.USE_GATE), 1)
        self.assertEqual(f.get(b.STATE + b.DEST), 1)

    def test_cancel_wait_discards_and_cannot_publish_later(self):
        f = self.fixture()
        self.stop_early(f)
        f.call(b.CANCEL_FN)
        self.assertEqual(f.get(b.STATE + b.CANCELS), 1)
        self.assertEqual(f.get(b.STATE + b.PHASE), 0)
        self.assertEqual(f.get(0x207038), 0)
        self.finish_batch(f)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.USES), 0)
        self.assertEqual(f.get(0x207680), 0)

    def test_cancel_normalizing_keeps_ownership_until_native_completion(self):
        f = self.fixture()
        self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), 0)
        f.call(b.STEP)
        f.put(0x207038, 96000)
        f.put(0x2071A4, 3)
        f.call(b.STEP)
        f.call(b.CANCEL_FN)
        self.assertEqual(f.get(b.STATE + b.PHASE), 5)
        self.assertEqual(f.call(b.ARM_NOW, 0x207000, 2), b.ARM_BUSY & 0xFFFFFFFF)
        f.put(0x2071A4, 4)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.PHASE), 0)
        self.assertEqual(f.get(b.STATE + b.CANCELS), 1)
        self.assertEqual(f.get(b.STATE + b.USES), 0)

    def test_project_kit_epoch_and_new_batch_invalidate(self):
        for at, val in (
            (0x44F370A0, 28),
            (0x80004704, 0x204100),
            (n.STATE, 2),
            (b.STATE + p.BATCH_SERIAL, 2),
        ):
            with self.subTest(address=hex(at)):
                f = self.fixture()
                self.stop_early(f)
                f.put(at, val)
                f.call(b.STEP)
                self.finish_batch(f)
                f.call(b.STEP)
                self.assertEqual(f.get(b.STATE + b.PHASE), 0)
                self.assertEqual(f.get(b.STATE + b.USES), 0)
                self.assertEqual(f.get(0x207680), 0)

    def test_foreign_worker_lease_survives_wait_and_cancel(self):
        f = self.fixture()
        self.stop_early(f)
        self.finish_batch(f)
        f.put(w.STATE + 12, 2)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.PHASE), p.WAIT_LOAD)
        f.call(b.CANCEL_FN)
        self.assertEqual(f.get(w.STATE + 12), 2)

    def test_unknown_or_poisoned_batch_refuses(self):
        for field, value in ((p.BATCH_SERIAL, 0), (p.POISON, 1)):
            f = self.fixture()
            f.put(b.STATE + field, value)
            self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), b.ARM_BUSY & 0xFFFFFFFF)
            self.assertEqual(f.get(b.STATE + b.OWN), 0)

    def test_worker_and_completion_reject_a_new_batch(self):
        f = self.fixture()
        self.stop_early(f)
        self.finish_batch(f)
        f.call(b.STEP)
        f.put(b.STATE + p.BATCH_SERIAL, 2)
        self.assertEqual(f.call(b.WORKER), 0xFFFFFFFF)
        f.call(b.DONE, 0x207700, 0)
        self.assertEqual(f.get(b.STATE + b.USES), 0)
        self.assertEqual(f.get(0x207614), 1)

    def test_disabled_profile_is_exact_R4(self):
        from lab.runtime import STOCK_MAIN
        from lab.sketch_device import build

        _, meta = build(
            STOCK_MAIN.read_bytes(),
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
            navigation_fixes=True,
            fixed_buf_slots=True,
        )
        self.assertEqual(
            meta["sha256"],
            "7c5e0bdea8b5c7c8feb5cfc8c695d0f27dbd4a070624994215b2f288d0012de1",
        )
        self.assertEqual(meta["buf_public_slots"], [1020, 1021, 1022, 1023])

    def test_bar_default_records_during_loading_and_retains_until_publication(self):
        f = self.fixture()
        self.assertEqual(f.call(b.ARM_ONLY, 0x207000, 1), 0)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.STARTS), 0)
        f.edge()
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.STARTS), 1)
        f.edge()
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.STOPS), 1)
        f.put(0x2071A4, 4)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.PHASE), p.WAIT_LOAD)
        self.assertEqual(f.get(w.STATE + 64), 0)
        self.finish_batch(f)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.PHASE), 4)

    def test_project_request_invalidates_even_before_project_identity_changes(self):
        f = self.fixture()
        self.stop_early(f)
        f.cpu.mem_write(p.PROJECT_STOCK, n.project_guard(p.PROJECT_STOCK, 0x20FF00))
        f.put(n.STATE + 16, 1)  # Existing reservation still refuses project load.
        self.assertEqual(f.call(p.PROJECT_GATE), 0)
        self.assertEqual(f.get(b.STATE + b.CANCEL), 1)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.PHASE), 0)
        self.assertEqual(f.get(b.STATE + b.USES), 0)

    def test_native_batch_return_only_accepts_the_loading_task(self):
        from unicorn import m68k_const as r

        for task, done in ((0x203000, 1), (0x204000, 0)):
            f = self.fixture()
            f.cpu.mem_map(0x4004E000, 4096)
            f.cpu.mem_write(p.BATCH_RETURN + 8, bytes.fromhex("4e75"))
            f.put(b.STATE + p.BATCH_TASK, 0x203000)
            f.put(q.CURRENT_TCB, task)
            stack, stop = 0x20E000, 0x20FF00
            f.put(stack + 0x58, stop)
            f.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
            f.cpu.reg_write(r.UC_M68K_REG_A7, stack)
            f.cpu.reg_write(r.UC_M68K_REG_D0, 123)
            f.cpu.reg_write(r.UC_M68K_REG_D1, 456)
            f.cpu.emu_start(p.BATCH_LEAVE, stop, count=10000)
            self.assertEqual(f.get(b.STATE + p.BATCH_DONE), done)
            self.assertEqual(f.get(b.STATE + p.BATCH_ACTIVE), 1 - done)
            self.assertEqual(f.cpu.reg_read(r.UC_M68K_REG_A7), stack + 0x5C)
            self.assertEqual(f.cpu.reg_read(r.UC_M68K_REG_D0), 123)
            self.assertEqual(f.cpu.reg_read(r.UC_M68K_REG_D1), 456)

    def test_feedback_tracks_pending_take_before_playback_pool_setup(self):
        from lab import sketch as s

        f = controls.PerformanceControls().view()
        f.cpu.mem_map(p.CODE, 0x4000)
        f.native_value(p.POOL_GET, 0x209000)
        f.cpu.mem_write(s.ARM_FEEDBACK, s.arm_feedback(startup_capture=True))
        for live, latch in (
            (b.STATE + b.ARMS, s.ARM_COUNT),
            (n.STATE, s.ARM_EPOCH),
            (0x80004704, s.ARM_KIT),
            (0x44F370A0, s.ARM_PROJECT),
            (b.STATE + b.DEST, s.ARM_BUF),
        ):
            f.put(s.STATE + latch, int.from_bytes(f.cpu.mem_read(live, 4), "big"))
        f.put(s.STATE + s.ARM_POOL, 0x209000)
        f.put(w.STATE + 68, 0)
        f.put(b.STATE + b.PHASE, p.WAIT_LOAD)
        f.put(s.STATE + s.ACTION, s.ARM_PROCESSING)
        f.call(s.ARM_FEEDBACK)
        self.assertEqual(f.get(s.ACTION), s.ARM_LOADING)

    def test_NO_requests_cancellation_before_Sketch_closes_without_consuming_foreign_input(
        self,
    ):
        from lab import sketch as s
        from lab.runtime import STOCK_MAIN

        for phase in (1, 2, 3, p.WAIT_LOAD):
            f = controls.PerformanceControls().view()
            parts = s.payload(
                STOCK_MAIN.read_bytes(),
                arm_enabled=True,
                freeze_enabled=True,
                performance_controls=True,
                startup_capture=True,
            )
            f.cpu.mem_write(s.INPUT, parts[s.INPUT])
            f.put(b.STATE + b.PHASE, phase)
            self.assertEqual(f.event(12, 1), 0)
            self.assertEqual(
                int.from_bytes(f.cpu.mem_read(b.STATE + b.CANCEL, 4), "big"), 1
            )

    def test_sample_selection_cannot_initialize_slots_in_a_gap_or_pending_take(self):
        f = self.fixture()
        f.cpu.mem_write(
            b.INIT_BODY, bytes.fromhex("4ef9") + p.INIT_GATE.to_bytes(4, "big")
        )
        f.put(q.STATE + 56, 0)
        f.put(q.STOCK_BUSY, 0)
        f.call(b.INIT_BODY)
        self.assertEqual(f.get(0x207680), 0)
        self.stop_early(f)
        self.finish_batch(f)
        f.call(b.INIT_BODY)
        self.assertEqual(f.get(0x207680), 0)
        f.call(b.STEP)
        self.assertEqual(f.get(0x207680), 1)
        self.assertEqual(f.get(b.STATE + b.PHASE), 4)

    def setup_fixture(self, *, capacity=False):
        from test_buf_fixed_slots import Fixture

        from lab import buf_fixed_slots as fixed

        f = Fixture()
        f.cpu.mem_map(q.BASE, 0x4000)
        f.cpu.mem_map(p.CODE, 0x4000)
        f.cpu.mem_map(0x40966000, 4096)
        for at, raw in p.payload().items():
            f.cpu.mem_write(at, raw)
        f.cpu.mem_write(b.INIT, b.initialize())
        f.cpu.mem_write(
            b.INIT_BODY, bytes.fromhex("4ef9") + p.INIT_GATE.to_bytes(4, "big")
        )
        # Count actual SETUP executions; its original emitted body still runs.
        f.cpu.mem_write(0x20A000, f.cpu.mem_read(w.SETUP, len(fixed.setup())))
        c = Code()
        c.imm("2039", 0x200740)
        c.emit("5280")
        c.imm("23c0", 0x200740)
        c.imm("4ef9", 0x20A000)
        f.cpu.mem_write(w.SETUP, c.finish(w.SETUP))
        if not capacity:
            for slot in range(1, 1020):
                f.occupied(slot)
        f.put(w.DEST, 1)
        f.put(b.STATE + p.BATCH_DONE, 1)
        return f

    def test_failed_setup_is_throttled_and_recovers_after_slots_are_freed(self):
        from test_buf_fixed_slots import POOL

        f = self.setup_fixture()
        f.put(b.TICK, 1000)
        f.call(b.INIT)
        self.assertEqual(f.get(0x200740), (1,))
        self.assertEqual(f.get(b.STATE + p.SETUP_RETRY), (1,))
        before = f.protected()
        for tick in (1000, 1001, 1000 + p.SETUP_RETRY_FRAMES - 1):
            f.put(b.TICK, tick)
            f.call(b.INIT)
            self.assertEqual(f.get(0x200740), (1,))
            self.assertEqual(f.protected(), before)
        for slot in range(1, 9):
            f.put(POOL + slot * 16, 0xFFFFFFFF, 0, 0, 0)
        f.put(b.TICK, 1000 + p.SETUP_RETRY_FRAMES)
        f.call(b.INIT)
        self.assertEqual(f.get(0x200740), (2,))
        self.assertEqual(f.get(w.STATE + 64), (1,))
        self.assertEqual(f.get(w.STATE + 12), (0,))
        self.assertEqual(f.get(b.STATE + p.SETUP_RETRY), (0,))
        for _ in range(3):
            f.call(b.INIT)
        self.assertEqual(f.get(0x200740), (2,))

    def test_setup_retry_wrap_and_busy_guards_preserve_foreign_ownership(self):
        f = self.setup_fixture()
        start = 0xFFFFF000
        f.put(b.TICK, start)
        f.call(b.INIT)
        for elapsed, attempts in (
            (p.SETUP_RETRY_FRAMES - 1, 1),
            (p.SETUP_RETRY_FRAMES, 2),
        ):
            f.put(b.TICK, (start + elapsed) & 0xFFFFFFFF)
            f.call(b.INIT)
            self.assertEqual(f.get(0x200740), (attempts,))
        for at in (w.STATE + 12, n.STATE + 24, q.STATE + 56, q.STOCK_BUSY):
            with self.subTest(guard=hex(at)):
                f = self.setup_fixture(capacity=True)
                f.put(at, 2)
                f.call(b.INIT)
                self.assertEqual(f.get(0x200740), (0,))
                self.assertEqual(f.get(at), (2,))
                self.assertEqual(f.get(b.STATE + p.SETUP_RETRY), (0,))

    def test_admitted_arm_and_new_batch_clear_setup_retry(self):
        f = self.fixture()
        f.put(b.STATE + p.SETUP_RETRY, 1)
        self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), 0)
        self.assertEqual(f.get(b.STATE + p.SETUP_RETRY), 0)
        f.put(b.STATE + p.SETUP_RETRY, 1)
        self.assertEqual(f.call(b.ARM_NOW, 0x207000, 2), b.ARM_BUSY & 0xFFFFFFFF)
        self.assertEqual(f.get(b.STATE + p.SETUP_RETRY), 1)
        f = self.fixture()
        f.cpu.mem_map(0x4004E000, 4096)
        f.cpu.mem_write(p.BATCH_SITE + 8, bytes.fromhex("4e75"))
        f.put(b.STATE + p.BATCH_ACTIVE, 0)
        f.put(b.STATE + p.SETUP_RETRY, 1)
        f.call(p.BATCH_ENTER)
        self.assertEqual(f.get(b.STATE + p.SETUP_RETRY), 0)
        self.assertEqual(f.get(b.STATE + p.BATCH_SERIAL), 2)

    def test_wait_load_draw_status_and_latched_action_target(self):
        from lab import sketch as s
        from lab.runtime import STOCK_MAIN

        f = controls.PerformanceControls().view()
        for at, raw in s.payload(
            STOCK_MAIN.read_bytes(),
            arm_enabled=True,
            freeze_enabled=True,
            arm_diagnostics=True,
            clock_fix=True,
            performance_controls=True,
            fixed_buf_slots=True,
            startup_capture=True,
        ).items():
            f.cpu.mem_write(at, raw)
        # Isolate drawing from the separately tested feedback and raster services.
        for at, value in (
            (s.CLEAR, 1),
            (s.TEXT, 0),
            (s.ARM_FEEDBACK, 0),
            (s.GETTERS[0], 0),
            (s.GETTERS[1], 0),
            (s.GETTERS[3], 0),
        ):
            f.native_value(at, value)
        f.cpu.mem_write(0x200800, b"IN\0")
        for at in (0x4001FD88, 0x4001FDBE, 0x4001FDF4):
            f.native_value(at, 0x200800)
        c = Code()
        c.emit("206f0008 2010")
        c.imm("0c80", 0x5245433A)  # REC: format's two actual string arguments.
        c.branch(6, "action")
        for offset, target in ((12, 0x200700), (16, 0x200704)):
            c.emit(f"202f{offset:04x}")
            c.imm("23c0", target)
        c.label("action")
        c.emit("2010")
        c.imm("0c80", 0x42554620)  # BUF action format and its latched target.
        c.branch(6, "return")
        for offset, target in ((8, 0x200708), (12, 0x20070C)):
            c.emit(f"202f{offset:04x}")
            c.imm("23c0", target)
        c.label("return")
        c.emit("7000 4e75")
        f.cpu.mem_write(s.PRINT, c.finish(s.PRINT))
        f.put(s.STATE + s.ACTION, s.ARM_LOADING)
        f.put(s.STATE + s.ARM_BUF, 3)

        def recorded_string(at):
            ptr = int.from_bytes(f.cpu.mem_read(at, 4), "big")
            return bytes(f.cpu.mem_read(ptr, 80)).split(b"\0")[0]

        for phase, expected in enumerate(
            (b"IDLE", b"ARMED", b"RECORD", b"PROC", b"COMMIT", b"REFUSED", b"WAIT")
        ):
            f.put(b.STATE + b.PHASE, phase)
            f.call(s.DRAW, 0x200100, 0x200500)
            self.assertEqual(recorded_string(0x200704), expected)
        self.assertEqual(recorded_string(0x200708), b"BUF %u: WAIT LOAD")
        self.assertEqual(int.from_bytes(f.cpu.mem_read(0x20070C, 4), "big"), 3)
