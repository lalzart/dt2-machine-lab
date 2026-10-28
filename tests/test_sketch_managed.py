"""Managed Sketch contract exercised by explicit native ColdFire instructions."""

import os
import unittest

import test_sketch_controls as controls

from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab import sketch as s
from lab import sketch_managed as m
from lab.emit import Code


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "Explicit Rust ColdFire bridge required"
)
class ManagedBuffers(unittest.TestCase):
    def setUp(self):
        self.ui = controls.CompactPanelControls()
        self.ui.setUp()
        self.f = f = self.ui.f
        f.cpu.mem_map(m.BASE, m.SIZE)
        for at, raw in m.payload().items():
            f.cpu.mem_write(at, raw)
        f.cpu.mem_write(
            s.ROTATE,
            s.rotation(
                performance_controls=True, sketchbook_save=True, managed_buffers=True
            ),
        )
        f.put(0x204800, 18, 1, 4, 0)

    def word(self, at):
        return int.from_bytes(self.f.cpu.mem_read(at, 4), "big")

    def rotate(self, encoder, delta=96):
        f = self.f
        f.cpu.mem_write(self.ui.accumulator, bytes(0x100))
        f.put(self.ui.event, 0, 0, 0, encoder + 1, delta & 0xFFFFFFFF, 0)
        f.call(s.ROTATE, 0x200100, self.ui.event)

    def test_preferences_are_independent_and_normal_sampler_is_unchanged(self):
        f = self.f
        normal = f.cpu.mem_read(0x204800, 16)
        for buf in range(1, 5):
            f.put(s.STATE + s.BUF, buf)
            self.assertEqual(f.call(m.GETTERS[0], 0), 18)
            f.call(m.SETTERS[0], 0, buf)
            f.call(m.SETTERS[4], 0, buf % 2)
        for buf in range(1, 5):
            f.put(s.STATE + s.BUF, buf)
            self.assertEqual(f.call(m.GETTERS[0], 0), buf)
            self.assertEqual(f.call(m.GETTERS[4], 0), buf % 2)
        self.assertEqual(f.cpu.mem_read(0x204800, 16), normal)

    def test_real_encoder_controls_use_selected_preferences_and_supported_lengths(self):
        f = self.f
        self.rotate(1, -96)
        self.assertEqual(f.call(m.GETTERS[0]), 17)
        self.rotate(5)
        self.assertEqual(f.call(m.GETTERS[4]), 1)
        self.rotate(0)
        self.assertEqual(f.get(s.BUF), 2)
        self.assertEqual(f.call(m.GETTERS[0]), 18)
        self.assertEqual(f.call(m.GETTERS[4]), 0)
        self.rotate(3, -96)
        self.assertEqual(f.call(m.GETTERS[2]), 4)
        for _ in range(4):
            self.rotate(3)
        self.assertEqual(f.call(m.GETTERS[2]), 6)
        self.assertEqual(self.word(0x204800), 18)
        self.assertEqual(self.word(0x204808), 4)

    def admitted_stub(self):
        c = Code()
        c.emit("7000")
        c.imm("23c0", s.STATE + s.ARM_RESULT)
        c.emit("7001")
        c.imm("23c0", nb.STATE + nb.PHASE)
        c.emit("4e75")
        self.f.cpu.mem_write(m.OLD_ARM, c.finish(m.OLD_ARM))

    def test_capture_latches_buffer_then_restores_normal_settings_after_publication(
        self,
    ):
        f = self.f
        f.call(m.ENSURE)
        f.put(m.SETTINGS + m.STRIDE, 7, 2, 5, 1, 1)
        f.put(s.STATE + s.BUF, 4)
        f.put(s.STATE + s.LATCH, 2)
        self.admitted_stub()
        f.call(m.ARM)
        self.assertEqual(
            f.cpu.mem_read(0x204800, 16), f.cpu.mem_read(m.SETTINGS + m.STRIDE, 16)
        )
        self.assertEqual(self.word(m.STATE + m.CAPTURE_BUF), 2)
        f.call(m.RESTORE)
        self.assertEqual(self.word(m.STATE + m.BORROWED), 1)
        f.put(nb.STATE + nb.PHASE, 0)
        f.put(w.STATE + 12, 1)
        f.call(m.RESTORE)
        self.assertEqual(self.word(m.STATE + m.BORROWED), 1)
        f.put(w.STATE + 12, 0)
        f.call(m.RESTORE)
        self.assertEqual(self.word(m.STATE + m.BORROWED), 0)
        self.assertEqual([self.word(0x204800 + i * 4) for i in range(4)], [18, 1, 4, 0])
        self.assertEqual(f.get(s.START_MODE), 0)

    def test_full_and_busy_refuse_before_touching_normal_settings_or_capture(self):
        f = self.f
        f.put(s.STATE + s.LATCH, 1)
        f.cpu.mem_write(m.OLD_ARM, bytes.fromhex("4afc"))
        before = f.cpu.mem_read(0x204800, 16)
        for i in range(8):
            f.put(n.GEN + i * 64, i % 3 + 1)
        self.assertEqual(f.call(m.CAPACITY), 0)
        f.call(m.ARM)
        self.assertEqual(f.get(s.ARM_RESULT), nb.CAPACITY_RESULT & 0xFFFFFFFF)
        self.assertEqual(f.call(m.STATUS), m.FULL)
        f.put(w.STATE + 12, 4)
        f.call(m.ARM)
        self.assertEqual(f.get(s.ARM_RESULT), nb.ARM_BUSY & 0xFFFFFFFF)
        self.assertEqual(f.cpu.mem_read(0x204800, 16), before)
        self.assertEqual(self.word(m.STATE + m.BORROWED), 0)

    def test_failure_restores_and_stale_project_never_writes_old_pointer(self):
        f = self.f
        f.put(s.STATE + s.LATCH, 1)
        c = Code()
        c.emit("70ff")
        c.imm("23c0", s.STATE + s.ARM_RESULT)
        c.emit("4e75")
        f.cpu.mem_write(m.OLD_ARM, c.finish(m.OLD_ARM))
        f.call(m.ARM)
        self.assertEqual(self.word(m.STATE + m.BORROWED), 0)
        self.assertEqual(self.word(m.STATE + m.FAILURE), 1)
        self.admitted_stub()
        f.call(m.ARM)
        f.put(nb.STATE + nb.PHASE, 0)
        f.native_value(0x401988A2, 0x203004)
        f.put(0x204800, 3)
        f.call(m.RESTORE)
        self.assertEqual(self.word(0x204800), 3)
        self.assertEqual(self.word(m.STATE + m.BORROWED), 1)

    def test_stale_project_or_wrapper_refuses_before_borrowing(self):
        f = self.f
        f.call(m.ENSURE)
        f.put(s.STATE + s.LATCH, 1)
        f.cpu.mem_write(m.OLD_ARM, bytes.fromhex("4afc"))
        before = f.cpu.mem_read(0x204800, 16)
        project = self.word(m.STATE + m.PROJECT)
        pointer = self.word(m.STATE + m.POINTER)
        for function, original in ((0x401988A2, project), (0x40041D18, pointer)):
            with self.subTest(function=hex(function)):
                f.native_value(function, original + 4)
                f.call(m.ARM)
                self.assertEqual(f.get(s.ARM_RESULT), nb.ARM_REFUSED & 0xFFFFFFFF)
                self.assertEqual(self.word(m.STATE + m.BORROWED), 0)
                self.assertEqual(f.call(m.STATUS), m.ERROR)
                self.assertEqual(f.cpu.mem_read(0x204800, 16), before)
                f.native_value(function, original)

    def test_manual_finish_reaches_existing_capture_owner_without_borrowing_twice(self):
        f = self.f
        f.put(m.STATE + m.BORROWED, 1)
        f.put(nb.STATE + nb.PHASE, 2)
        c = Code()
        c.emit("7003")
        c.imm("23c0", nb.STATE + nb.PHASE)
        c.emit("4e75")
        f.cpu.mem_write(m.OLD_ARM, c.finish(m.OLD_ARM))
        before = f.cpu.mem_read(0x204800, 16)
        f.call(m.ARM)
        self.assertEqual(self.word(nb.STATE + nb.PHASE), 3)
        self.assertEqual(self.word(m.STATE + m.BORROWED), 1)
        self.assertEqual(f.cpu.mem_read(0x204800, 16), before)

    def test_failed_publication_reports_on_its_buffer_and_restores_normal_settings(
        self,
    ):
        f = self.f
        self.admitted_stub()
        f.put(s.STATE + s.LATCH, 1)
        f.call(m.ARM)
        f.put(nb.STATE + nb.PHASE, 0)
        f.put(nb.STATE + nb.RESULT, 0xFFFFFFFF)
        f.call(m.RESTORE)
        self.assertEqual(f.call(m.STATUS), m.ERROR)
        f.put(s.STATE + s.BUF, 2)
        self.assertEqual(f.call(m.STATUS), m.EMPTY)
        f.call(m.SETTERS[0], 0, 2)
        f.put(s.STATE + s.BUF, 1)
        self.assertEqual(f.call(m.STATUS), m.ERROR)
        f.call(m.SETTERS[0], 0, 2)
        self.assertEqual(f.call(m.STATUS), m.EMPTY)
        self.assertEqual(self.word(m.STATE + m.BORROWED), 0)

    def test_status_follows_capture_owner_and_does_not_claim_free_quarantined_storage(
        self,
    ):
        f = self.f
        self.assertEqual(f.call(m.CAPACITY), 8)
        for i, state in enumerate((1, 2, 3, 1)):
            f.put(n.GEN + i * 64, state)
        self.assertEqual(f.call(m.CAPACITY), 4)
        for phase, expected in (
            (1, m.WAIT),
            (2, m.RECORDING),
            (3, m.BUSY),
            (6, m.WAIT),
        ):
            f.put(nb.STATE + nb.PHASE, phase)
            f.put(nb.STATE + nb.DEST, 1)
            self.assertEqual(f.call(m.STATUS), expected)
        f.put(s.STATE + s.BUF, 2)
        self.assertEqual(f.call(m.STATUS), m.EMPTY)
