"""Focused native instruction checks for the opt-in performance controls."""

import os
import unittest
from unittest.mock import patch

import test_buf_next_bar as previous_bar
import test_sketch as previous_sketch
from selector_core_support import Core

from lab import buf_next_bar as b
from lab import recorder_worker_code as w
from lab import sketch as s
from lab.emit import Code
from lab.runtime import STOCK_MAIN


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "Explicit Rust ColdFire bridge required"
)
class PerformanceControls(unittest.TestCase):
    def recorder(self, raw_length=4):
        f = previous_bar.NextBarTests()
        f.clock_profile = True
        with patch.object(previous_bar.u, "Uc", Core):
            f.setUp()
        for at, code in b.payload(
            arm_diagnostics=True, clock_fix=True, performance_controls=True
        ).items():
            f.cpu.mem_write(at, code)
        f.cpu.mem_map(0x402B6000, 4096)
        f.cpu.mem_write(b.TEMPO_GET, bytes.fromhex("2039402b62bc4e75"))
        f.put(0x402B62BC, 14400)  # Authenticated getter: 120 BPM * 120.
        f.put(0x209000 - 24, raw_length)
        f.put(w.DEST, 0)
        f.put(b.TICK, 1000)
        return f

    def view(self):
        f = previous_sketch.SketchTests()
        with patch.object(previous_sketch.u, "Uc", Core):
            f.setUp()
        for at, code in s.payload(
            STOCK_MAIN.read_bytes(),
            arm_enabled=True,
            freeze_enabled=True,
            performance_controls=True,
        ).items():
            f.cpu.mem_write(at, code)
        # Count close requests. Actual deferred destruction is covered natively.
        c = Code()
        c.imm("2039", 0x200900)
        c.emit("5280")
        c.imm("23c0", 0x200900)
        c.emit("7000 4e75")
        f.cpu.mem_write(0x4011AEEA, c.finish(0x4011AEEA))
        f.native_value(s.OPEN, 0)
        return f

    def test_now_starts_without_bar_and_captures_full_16_32_64_steps(self):
        for raw_length, frames in ((4, 96000), (5, 192000), (6, 384000)):
            with self.subTest(raw_length=raw_length):
                f = self.recorder(raw_length)
                serial = f.get(b.STATE + b.SERIAL)
                self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), 0)
                self.assertEqual(f.get(b.STATE + b.STARTS), 0)
                f.call(b.STEP)
                self.assertEqual(f.get(b.STATE + b.STARTS), 1)
                self.assertEqual(f.get(b.STATE + b.PHASE), 2)
                for elapsed in range(6000, frames, 6000):
                    f.put(b.TICK, 1000 + elapsed)
                    f.call(b.STEP)
                    self.assertEqual(f.get(b.STATE + b.STOPS), 0)
                f.put(b.TICK, 1000 + frames)
                f.call(b.STEP)
                self.assertEqual(f.get(b.STATE + b.STOPS), 1)
                self.assertEqual(f.get(b.STATE + b.PHASE), 3)
                self.assertEqual(
                    f.get(b.STATE + b.STOP_TICK) - f.get(b.STATE + b.START_TICK), frames
                )
                self.assertEqual(f.get(b.STATE + b.SERIAL), serial)
                self.assertEqual(f.get(w.DEST), 0)

    def test_bar_stays_default_and_busy_now_cannot_relabel_it(self):
        f = self.recorder()
        self.assertEqual(f.call(b.ARM_ONLY, 0x207000, 1), 0)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.STARTS), 0)
        before = bytes(f.cpu.mem_read(b.STATE, 132))
        self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), b.ARM_BUSY & 0xFFFFFFFF)
        self.assertEqual(bytes(f.cpu.mem_read(b.STATE, 132)), before)
        f.edge()
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.STARTS), 1)
        self.assertEqual(f.get(b.STATE + b.START_MODE), 0)

    def test_now_tempo_change_and_lost_poll_cancel_without_publication(self):
        for change in ("tempo", "cadence"):
            with self.subTest(change=change):
                f = self.recorder()
                self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), 0)
                f.call(b.STEP)
                if change == "tempo":
                    f.put(0x402B62BC, 14520)
                    f.put(b.TICK, 2000)
                else:
                    f.put(b.TICK, 1000 + b.LATENCY + 1)
                f.call(b.STEP)
                self.assertEqual(f.get(b.STATE + b.CANCELS), 1)
                self.assertEqual(f.get(b.STATE + b.USES), 0)
                self.assertEqual(f.get(w.DEST), 0)

    def test_now_sample_clock_wrap_and_ten_second_cap(self):
        f = self.recorder()
        start = 0xFFFFF000
        f.put(b.TICK, start)
        self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), 0)
        f.call(b.STEP)
        for elapsed in range(6000, 96001, 6000):
            f.put(b.TICK, (start + elapsed) & 0xFFFFFFFF)
            f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.PHASE), 3)
        self.assertEqual(f.get(b.STATE + b.STOPS), 1)
        f = self.recorder(6)
        f.put(0x402B62BC, 3600)
        self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), 0)
        f.call(b.STEP)
        for elapsed in range(6000, b.MAX_CAPTURE_FRAMES + 1, 6000):
            f.put(b.TICK, 1000 + elapsed)
            f.call(b.STEP)
        f.put(b.TICK, 1000 + b.MAX_CAPTURE_FRAMES + 1)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.RESULT), b.CAPACITY_RESULT & 0xFFFFFFFF)
        self.assertEqual(f.get(b.STATE + b.USES), 0)

    def test_native_now_completion_normalizes_and_publishes_without_second_stop(self):
        for native_state in (3, 4):
            with self.subTest(native_state=native_state):
                f = self.recorder()
                f.put(0x402B62BC, 12240)
                f.put(b.TICK, 890048)
                self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), 0)
                f.call(b.STEP)
                f.put(0x207038, 113408)  # Actual failing native trace.
                f.put(0x2071A4, native_state)
                # A valid native-completed count is authoritative, even when
                # the GUI observes it after the final timer interval.
                f.put(b.TICK, 1003456)
                f.cpu.mem_write(b.STOP, bytes.fromhex("4afc"))
                f.call(b.STEP)
                self.assertEqual(f.get(b.STATE + b.STOPS), 1)
                if native_state == 3:
                    self.assertEqual(f.get(b.STATE + b.PHASE), 3)
                    f.put(0x2071A4, 4)
                    f.call(b.STEP)
                self.assertEqual(f.get(b.STATE + b.PHASE), 4)
                self.assertEqual(f.call(b.WORKER), 0)
                f.call(b.DONE, 0x207700, 0)
                self.assertEqual(f.get(b.STATE + b.USES), 1)
                self.assertEqual(f.get(b.STATE + b.CANCELS), 0)
                self.assertEqual(f.get(w.DEST), 0)

    def test_explicit_cancel_wins_over_a_full_native_completed_take(self):
        f = self.recorder()
        self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), 0)
        f.call(b.STEP)
        f.put(0x207038, 96000)
        f.put(0x2071A4, 4)
        f.put(b.STATE + b.CANCEL, 1)
        f.call(b.STEP)
        self.assertEqual(f.get(b.STATE + b.CANCELS), 1)
        self.assertEqual(f.get(b.STATE + b.USES), 0)

    def test_native_completion_rejects_short_overlong_and_changed_tempo_takes(self):
        for length, count, tempo, accepted in (
            (4, 96000, 14400, True),
            (5, 192000, 14400, True),
            (6, 384000, 14400, True),
            (4, 96000 - b.COUNT_MARGIN, 14400, True),
            (4, 96000 - b.COUNT_MARGIN - 1, 14400, False),
            (4, 96000 + b.LATENCY, 14400, True),
            (4, 96000 + b.LATENCY + 1, 14400, False),
            (4, 1000, 14400, False),
            (4, 96000, 14520, False),
            (4, b.MAX_CAPTURE_FRAMES + 1, 14400, False),
        ):
            with self.subTest(length=length, count=count, tempo=tempo):
                f = self.recorder(length)
                self.assertEqual(f.call(b.ARM_NOW, 0x207000, 1), 0)
                f.call(b.STEP)
                f.put(0x207038, count)
                f.put(0x402B62BC, tempo)
                result = f.call(b.NOW_COMPLETED)
                self.assertEqual(result, 0 if accepted else 0xFFFFFFFF)

    def test_page_buttons_close_only_the_actual_sketch_owner_and_propagate(self):
        for key in range(1, 7):
            with self.subTest(key=key):
                f = self.view()
                self.assertEqual(f.event(key, 1), 0)
                self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200900, 4), "big"), 1)
                self.assertEqual(f.event(key, 0x10), 0)
                self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200900, 4), "big"), 1)
                f.put(0x208400, 0, 0, 0, key, 1)
                self.assertEqual(f.call(s.INPUT, 0x200200, 0x208400), 0)
                self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200900, 4), "big"), 1)

    def test_F_uses_one_volatile_selection_and_locks_during_admitted_capture(self):
        f = self.view()
        c = Code()
        c.emit("202f0008")
        c.imm("0c80", 5)
        c.branch(7, "match")
        c.emit("7000 4e75")
        c.label("match")
        c.emit("7001 4e75")
        f.cpu.mem_write(0x40111732, c.finish(0x40111732))
        f.native_value(0x40111B62, 256)
        self.assertEqual(f.get(s.START_MODE), 0)
        f.call(s.ROTATE, 0x200100, 0x208400)
        self.assertEqual(f.get(s.START_MODE), 1)
        f.put(b.STATE + b.PHASE, 1)
        f.native_value(0x40111B62, 0xFFFFFF00)
        f.call(s.ROTATE, 0x200100, 0x208400)
        self.assertEqual(f.get(s.START_MODE), 1)
        self.assertEqual(int.from_bytes(f.cpu.mem_read(w.DEST, 4), "big"), 0)
        self.assertEqual(f.get(s.BUF), 1)

    def test_stopped_title_displays_the_remembered_BAR_NOW_selection(self):
        from lab import buf_stopped as free
        f = self.view()
        for at, raw in s.payload(
            STOCK_MAIN.read_bytes(), arm_enabled=True, freeze_enabled=True,
            performance_controls=True, stopped_recording=True,
        ).items():
            f.cpu.mem_write(at, raw)
        f.cpu.mem_map(free.IS_STOPPED & ~4095, 4096)
        for at in (s.CLEAR, s.TEXT, s.PRINT, s.ARM_FEEDBACK,
                   s.FREEZE_FEEDBACK, s.READY, *s.GETTERS,
                   0x4001FD88, 0x4001FDBE, 0x4001FDF4):
            f.native_value(at, int(at == s.CLEAR))
        f.native_value(free.IS_STOPPED, 1)
        # Observe PRINT's first (title) call via a native instruction seam.
        # Its second formatting argument is the visible START mode text.
        c = Code()
        c.imm('2039', 0x200940)
        c.emit('4a80')
        c.branch(6, 'done')
        c.emit('202f0010')
        c.imm('23c0', 0x200944)
        c.emit('7001')
        c.imm('23c0', 0x200940)
        c.label('done')
        c.emit('7000 4e75')
        f.cpu.mem_write(s.PRINT, c.finish(s.PRINT))
        for mode, text in ((0, b'BAR'), (1, b'NOW'), (0, b'BAR')):
            f.put(0x200940, 0, 0)
            f.put(s.STATE + s.START_MODE, mode)
            f.call(s.DRAW, 0x200100, 0x200500)
            pointer = int.from_bytes(f.cpu.mem_read(0x200944, 4), 'big')
            self.assertEqual(bytes(f.cpu.mem_read(pointer, 8)).split(b'\0')[0], text)
            self.assertEqual(f.get(s.START_MODE), mode)
            self.assertEqual(f.get(s.BUF), 1)
            self.assertEqual(int.from_bytes(f.cpu.mem_read(w.DEST, 4), 'big'), 0)

    def test_opt_in_off_reproduces_user_tested_selector_image(self):
        from lab.sketch_device import build

        main, metadata = build(
            STOCK_MAIN.read_bytes(),
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
        )
        self.assertEqual(
            metadata["sha256"],
            "701a29543c5da385cd607bc5f8f2586742e3089e98165fd8854d6586dcdd9795",
        )
        changed, enabled = build(
            STOCK_MAIN.read_bytes(),
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
        )
        self.assertNotEqual(main, changed)
        self.assertEqual(metadata["reservation"], enabled["reservation"])
        self.assertTrue(enabled["performance_controls"])


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "Explicit Rust ColdFire bridge required"
)
class CompactPanelControls(unittest.TestCase):
    """Real stock encoder instructions, with explicit recorder service seams."""

    def setUp(self):
        from lab import sketchbook_ui as book

        self.f = f = previous_sketch.SketchTests()
        with patch.object(previous_sketch.u, "Uc", Core):
            f.setUp()
        f.cpu.mem_map(0x40300000, 0x70000)
        f.cpu.mem_write(0x40000400, STOCK_MAIN.read_bytes())
        f.cpu.mem_map(0x44D2E000, 4096)
        # Stock ready-state enum resource. The cold-boot visual probe separately
        # checks its divisor and step against initialized firmware RAM.
        f.cpu.mem_write(
            0x44D2E600,
            bytes.fromhex("00000000000000000000000600000001000000000000000600000004"),
        )
        f.cpu.mem_map(book.ROTATE & ~4095, 4096)
        f.native_value(book.ROTATE, 0)  # Main panel, no Sketchbook list owner.
        f.native_value(0x4005AA8E, 300)  # Stock scaler timestamp seam.
        f.native_value(0x4019988A, 0x205000)
        f.native_value(0x40015F6C, 0)
        for i, (getter, setter) in enumerate(zip(s.GETTERS, s.SETTERS, strict=True)):
            at = 0x204800 + i * 4
            c = Code()
            c.imm("2039", at)
            c.emit("4e75")
            f.cpu.mem_write(getter, c.finish(getter))
            c = Code()
            c.emit("202f0008")
            c.imm("23c0", at)
            c.emit("4e75")
            f.cpu.mem_write(setter, c.finish(setter))
        c = Code()
        c.imm("2039", 0x200900)
        c.emit("5280")
        c.imm("23c0", 0x200900)
        c.emit("4e75")
        f.cpu.mem_write(0x4011AE46, c.finish(0x4011AE46))
        f.cpu.mem_write(
            s.ROTATE, s.rotation(performance_controls=True, sketchbook_save=True)
        )
        self.event, self.oracle = 0x208400, 0x208800
        self.accumulator = 0x200100 + s.SCALER

    def test_small_motion_fast_turns_and_reversals_follow_stock_filter_one_choice(self):
        f = self.f
        cases = (
            (0, s.STATE + s.BUF, 2, 1, 4),
            (1, 0x204800, 9, 0, 18),
            (2, 0x204804, 1, 0, 3),
            (3, 0x204808, 4, 0, 8),
            (4, 0x20480C, 0, 0, 1),
            (5, s.STATE + s.START_MODE, 0, 0, 1),
        )
        for encoder, at, initial, low, high in cases:
            with self.subTest(encoder=encoder):
                f.cpu.mem_write(self.accumulator, bytes(0x100))
                f.cpu.mem_write(self.oracle, bytes(0x100))
                f.put(0x204800, 18)  # MON's original external-source edit gate.
                f.put(at, initial)
                expected = initial
                for delta in [1] * 7 + [-1] * 7 + [96, 96, -96, -96, 0] + [6] * 8:
                    f.put(self.event, 0, 0, 0, encoder + 1, delta & 0xFFFFFFFF, 0)
                    scaled = f.call(0x40111B62, self.oracle, self.event, 0x44D2E600)
                    if scaled >= 2**31:
                        scaled -= 2**32
                    previous = expected
                    expected = max(low, min(high, expected + max(-1, min(1, scaled))))
                    f.put(s.STATE + s.ACTION, 123)
                    f.put(0x200900, 0)
                    self.assertEqual(f.call(s.ROTATE, 0x200100, self.event), 1)
                    self.assertEqual(int.from_bytes(f.cpu.mem_read(at, 4), "big"), expected)
                    self.assertLessEqual(abs(expected - previous), 1)
                    self.assertEqual(f.get(s.ACTION), 0 if expected != previous else 123)
                    self.assertEqual(
                        int.from_bytes(f.cpu.mem_read(0x200900, 4), "big"),
                        int(expected != previous),
                    )
                    self.assertEqual(
                        f.cpu.mem_read(self.accumulator, 0x100),
                        f.cpu.mem_read(self.oracle, 0x100),
                    )
                    for acc in (self.accumulator, self.oracle):
                        f.call(0x40111940, acc, 0)  # Native timer decay.

    def test_buf_tiny_motion_is_filtered_and_fast_turn_cannot_skip_to_four(self):
        f = self.f
        f.put(s.STATE + s.BUF, 1)
        for _ in range(5):
            f.put(self.event, 0, 0, 0, 1, 1, 0)
            f.call(s.ROTATE, 0x200100, self.event)
            self.assertEqual(f.get(s.BUF), 1)
        f.put(self.event, 0, 0, 0, 1, 96, 0)
        f.call(s.ROTATE, 0x200100, self.event)
        self.assertEqual(f.get(s.BUF), 2)

    def test_busy_capture_keeps_recorder_settings_and_start_preference(self):
        f = self.f
        f.native_value(0x40015F6C, 2)
        for encoder, at in ((1, 0x204800), (2, 0x204804), (3, 0x204808),
                            (4, 0x20480C), (5, s.STATE + s.START_MODE)):
            with self.subTest(encoder=encoder):
                f.cpu.mem_write(self.accumulator, bytes(0x100))
                f.put(at, 0)
                f.put(self.event, 0, 0, 0, encoder + 1, 96, 0)
                f.call(s.ROTATE, 0x200100, self.event)
                self.assertEqual(int.from_bytes(f.cpu.mem_read(at, 4), "big"), 0)
