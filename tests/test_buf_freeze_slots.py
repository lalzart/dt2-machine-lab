"""Fixed FREEZE rows, conservative collision refusal and native publication."""

import os
import unittest
from unittest.mock import patch

import test_buf_fixed_slots as fixed_tests
import test_buf_freeze as prior
import test_sketch_copy as copy_tests
from selector_core_support import Core

from lab import buf_fixed_slots as fixed
from lab import buf_freeze as bf
from lab import buf_freeze_slots as slots
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab import sketch as s
from lab import sketch_copy as clip
from lab.emit import Code


@unittest.skipUnless(os.environ.get("DT2_BUF_SELECTOR_CORE"), "Rust ColdFire required")
class FreezeSlots(unittest.TestCase):
    def fixture(self):
        f = prior.BufFreezeTests()
        with patch.object(prior.u, "Uc", Core):
            f.setUp()
        for at, raw in bf.payload(slot_picker=slots.PICK).items():
            f.cpu.mem_write(at, raw)
        f.cpu.mem_write(slots.PICK, slots.picker())
        f.cpu.mem_write(q.BODY, n.freeze(address=q.BODY, worker_gate=q.GATE, slot_picker=slots.PICK))
        f.put(n.RESERVED, 0xFFFFFFFF)
        for slot in slots.SLOTS:
            f.put(0x209000 + slot * 16, 0xFFFFFFFF)
            f.put(0x405B1368 + slot * 16, 0xFFFFFFFF)
        return f

    def roots(self, f):
        return tuple(bytes(f.cpu.mem_read(at, size)) for at, size in (
            (0x209000, 16384), (0x405B0000, 0x10000),
            (n.SNAP, 512), (n.GEN, 512), (n.RESERVED, 84),
            (n.STATE, 64), (0x204000, 16 * 0x450),
        ))

    def test_eight_fixed_targets_and_full_refusal_do_not_mutate_roots(self):
        f = self.fixture()
        for index, target in enumerate(slots.SLOTS):
            f.put(n.STATE + 4, index)
            before = self.roots(f)
            self.assertEqual(f.call(slots.PICK), target)
            self.assertEqual(self.roots(f), before)
            self.assertEqual(f.get(slots.TARGET), target)
        f.put(n.STATE + 4, 8)
        before = self.roots(f)
        self.assertEqual(f.call(slots.PICK), 0xFFFFFFFB)
        self.assertEqual(self.roots(f), before)

    def test_each_occupied_target_refuses_without_overwrite_issue_or_lease(self):
        for index, target in enumerate(slots.SLOTS):
            for kind in ("project", "cache", "length", "reserved"):
                with self.subTest(index=index, kind=kind):
                    f = self.fixture()
                    f.put(n.STATE + 4, index)
                    at = {"project": 0x209000 + target * 16,
                          "cache": 0x405B1368 + target * 16,
                          "length": 0x405BA768 + target * 4,
                          "reserved": n.RESERVED}[kind]
                    f.put(at, target if kind == "reserved" else 0x12345678)
                    if kind == "reserved":
                        f.put(at + 4, 0xFFFFFFFF)
                    before = self.roots(f)
                    self.assertEqual(f.call(bf.SUBMIT, 2), 0xFFFFFFF8)
                    self.assertEqual(self.roots(f), before)
                    self.assertEqual(f.get(w.STATE + 12), 0)
                    self.assertEqual(f.get(bf.STATE + bf.ACTIVE), 0)
                    self.assertEqual(f.get(q.STATE + 36), 0)
                    self.assertEqual(f.get(slots.TARGET), target)
                    self.assertEqual(f.cpu.reg_read(prior.r.UC_M68K_REG_SR) & 0x2700, 0x2000)

    def test_worker_rechecks_target_before_any_snapshot_mutation(self):
        f = self.fixture()
        self.assertEqual(f.call(bf.SUBMIT, 2), 0)
        target = slots.SLOTS[0]
        f.put(0x209000 + target * 16, 0xABCDEF01, 9, 10, 11)
        before = self.roots(f)
        self.assertEqual(f.call(q.WORKER), 0xFFFFFFF8)
        self.assertEqual(self.roots(f), before)
        self.assertEqual(f.get(n.STATE + 4), 0)
        f.call(q.DONE, 0, 0xFFFFFFF8)
        self.assertEqual(f.get(w.STATE + 12), 0)
        self.assertEqual(f.get(bf.STATE + bf.ACTIVE), 0)

    def prepare_loader_seam(self, f):
        # The backend's current-project wrapper executes with an explicit
        # abstract object. The cache-hit service copies its existing key only;
        # real stock loader/DSP behavior is covered by the coupled probe.
        f.put(0x207400, 0x207500)
        f.put(0x207528, 0x207800)
        f.native_value(0x207800, 0x209000 - 0x1D2)
        for buf in range(4):
            for index in range(8):
                f.cpu.mem_write(n.NAMES + (buf * 8 + index) * 32,
                                f"/TEMP/B{buf + 1}-{index + 1:03d}".encode().ljust(32, b"\0"))
        c = Code()
        c.emit("202f0008 d080 d080 d080 d080")
        c.imm("41f9", 0x405B1368)
        c.emit("d1c0")
        c.imm("43f9", n.GEN + 16)
        c.emit("20d9 20d9 20d9 20d9 7000 4e75")
        f.cpu.mem_write(0x40154540, c.finish(0x40154540))

    def test_native_body_publishes_all_eight_distinct_snapshots_and_keeps_source(self):
        f = self.fixture()
        self.prepare_loader_seam(f)
        assignments = bytes(f.cpu.mem_read(0x204000, 16 * 0x450))
        source = bytes(f.cpu.mem_read(n.GEN, 64))
        for index, target in enumerate(slots.SLOTS):
            self.assertEqual(f.call(bf.SUBMIT, 2), 0)
            self.assertEqual(f.call(q.WORKER), target)
            f.call(q.DONE, 0, target)
            self.assertEqual(f.get(n.STATE + 4), index + 1)
            desc = n.SNAP + index * 64
            self.assertEqual(f.get(desc), 1)
            self.assertEqual(f.get(desc + 36), target)
            self.assertEqual(f.get(0x209000 + target * 16), n.SNAP_FIRST + index)
            self.assertEqual(bytes(f.cpu.mem_read(n.GEN, 64)), source)
            self.assertEqual(bytes(f.cpu.mem_read(0x204000, 16 * 0x450)), assignments)
            for previous in range(index):
                self.assertEqual(f.get(n.SNAP + previous * 64), 1)
                self.assertEqual(f.get(n.SNAP + previous * 64 + 36), slots.SLOTS[previous])
        before = self.roots(f)
        self.assertEqual(f.call(bf.SUBMIT, 2), 0xFFFFFFFB)
        self.assertEqual(self.roots(f), before)

    def test_private_generation_setup_excludes_freeze_rows_without_claiming_them(self):
        f = fixed_tests.Fixture()
        f.cpu.mem_write(w.SETUP, fixed.setup(freeze_h_slots=True))
        for slot in range(1, 1004):
            f.occupied(slot)
        # A pre-existing ordinary H123 sample is unrelated to BUF setup.
        f.occupied(1019)
        before = bytes(f.cpu.mem_read(fixed_tests.POOL, 16384))
        self.assertEqual(f.call(w.SETUP), 0)
        self.assertEqual(f.get(w.STATE + 112, 8), tuple(range(1004, 1012)))
        self.assertEqual(bytes(f.cpu.mem_read(fixed_tests.POOL, 16384)), before)
        self.assertTrue(set(f.get(n.RESERVED, 12)).isdisjoint(slots.SLOTS))
        f = fixed_tests.Fixture()
        f.cpu.mem_write(w.SETUP, fixed.setup(freeze_h_slots=True))
        for slot in range(1, 1012):
            f.occupied(slot)
        before = f.protected()
        self.assertEqual(f.call(w.SETUP), 0xFFFFFFFF)
        self.assertEqual(f.protected(), before)

    def test_collision_feedback_preserves_existing_copy_and_uses_same_warning(self):
        f = copy_tests.CopyShortcuts().fixture()
        for at, raw in clip.payload(freeze_h_slots=True).items():
            f.cpu.mem_write(at, raw)
        f.cpu.mem_write(s.FREEZE_SUBMIT, s.submit_freeze(freeze_h_slots=True))
        f.cpu.mem_write(s.FREEZE_FEEDBACK, s.freeze_feedback(freeze_h_slots=True))
        f.native_value(bf.SUBMIT, 0xFFFFFFF8)
        f.put(clip.STATE + clip.VALID, 1)
        before = bytes(f.cpu.mem_read(clip.STATE, 48))
        f.call(clip.COPY)
        self.assertEqual(f.get(s.ACTION), slots.ACTION)
        self.assertEqual(bytes(f.cpu.mem_read(clip.STATE, 48)), before)
        f.call(s.FREEZE_SUBMIT)
        self.assertEqual(f.get(s.ACTION), slots.ACTION)
        f.put(s.STATE + s.ACTION, 12)
        f.put(s.STATE + s.FREEZE_DONE, 1)
        f.put(q.STATE + 32, 2)
        f.put(q.STATE + 12, 0xFFFFFFF8)
        f.call(s.FREEZE_FEEDBACK)
        self.assertEqual(f.get(s.ACTION), slots.ACTION)
