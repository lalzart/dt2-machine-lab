"""Bounded frontend instructions with explicit worker/parameter service seams."""

import os
import struct
import unittest
from unittest.mock import patch

import test_sketch as previous
from selector_core_support import Core

from lab import buf_freeze as bf
from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab import sketch as s
from lab import sketch_copy as clip
from lab.emit import Code
from lab.runtime import STOCK_MAIN


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "Explicit native core required"
)
class CopyShortcuts(unittest.TestCase):
    def fixture(self, *, enabled=True):
        f = previous.SketchTests()
        with patch.object(previous.u, "Uc", Core):
            f.setUp()
        for at, raw in s.payload(
            STOCK_MAIN.read_bytes(),
            arm_enabled=True,
            freeze_enabled=True,
            startup_capture=True,
            copy_shortcuts=enabled,
        ).items():
            f.cpu.mem_write(at, raw)
        f.native_value(0x4011DE70, 1)

        # Keep panel events outside the 16-track kit region checked below.
        def event(key, flags):
            f.put(0x20E000, 0, 0, 0, key, flags)
            return f.call(s.INPUT, 0x200100, 0x20E000)

        f.event = event
        f.put(w.STATE + 68, 0x201000)
        f.put(n.STATE, 11)
        # Explicit SUBMIT boundary counts accepted requests and supplies the
        # existing backend's latched context. Snapshot work is not modeled here.
        c = Code()
        for src, dst in (
            (n.STATE, bf.STATE + bf.EPOCH),
            (0x80004704, bf.STATE + bf.KIT),
            (0x44F370A0, bf.STATE + bf.PROJECT),
            (w.STATE + 68, bf.STATE + bf.POOL),
        ):
            c.imm("2039", src)
            c.imm("23c0", dst)
        c.imm("2039", 0x200900)
        c.emit("5280")
        c.imm("23c0", 0x200900)
        c.emit("202f0004")
        c.imm("23c0", 0x200904)
        c.emit("7000 4e75")
        f.cpu.mem_write(bf.SUBMIT, c.finish(bf.SUBMIT))
        return f

    def read(self, f, field):
        return f.get(clip.STATE + field - s.STATE)

    def complete(self, f, slot=77, index=0):
        descriptor = n.SNAP + index * 64
        cache = (n.SNAP_FIRST + index, 12345, 12560, 1)
        public = (n.SNAP_FIRST + index, 11, 12560, 1)
        f.put(descriptor, 1, public[0], 11, 0, *cache)
        f.put(descriptor + 0x24, slot)
        f.put(descriptor + 0x30, *public)
        f.put(0x405B1368 + slot * 16, *cache)
        f.put(0x201000 + slot * 16, *public)
        f.put(q.STATE + 12, slot)
        f.put(q.STATE + 32, self.read(f, clip.COMPLETION))
        f.call(clip.FEEDBACK)

    def setter(self, f, track=0):
        # Execute the authenticated stock sample setter. Its abstract parameter
        # object, range helper and notifications are explicitly prepared.
        raw = STOCK_MAIN.read_bytes()
        start, end = 0x4003B570, 0x4003B614
        f.cpu.mem_write(start, raw[start - 0x40000400 : end - 0x40000400])
        f.native_value(0x4004ABE8, track)
        f.native_value(0x40045582, 0x200A00)
        f.put(0x200A00, 0x200B00)
        f.put(0x200B24, 0x200C00)
        f.put(0x200B28, 0x200C20)
        f.put(0x200B64, 0x200C40)
        f.put(0x200B7C, 0x200C60)
        f.native_value(0x200C00, 1)
        f.native_value(0x200C40, 0)
        c = Code()
        c.imm("2039", 0x200D00)
        c.emit("4e75")
        f.cpu.mem_write(0x200C20, c.finish(0x200C20))
        c = Code()
        c.emit("202f000c")
        c.imm("23c0", 0x200D00)
        c.emit("2040")
        c.imm("203c", 0x204000 + track * 0x450)
        c.emit("2240 2008 33400080")
        c.imm("2039", 0x200D04)
        c.emit("5280")
        c.imm("23c0", 0x200D04)
        c.emit("4e75")
        f.cpu.mem_write(0x200C60, c.finish(0x200C60))
        c = Code()
        c.emit("7000 2080")
        c.imm("203c", 1023)
        c.emit("21400004 4e75")
        f.cpu.mem_write(0x400DA204, c.finish(0x400DA204))

    def test_copy_owns_one_press_cycle_and_preserves_selected_buf(self):
        f = self.fixture()
        f.put(s.STATE + s.BUF, 4)
        self.assertEqual(f.event(19, 3), 1)
        self.assertEqual(
            (f.get(s.ACTION), self.read(f, clip.PENDING)), (clip.QUEUED, 1)
        )
        for flags in (9, 0x29, 5):
            self.assertEqual(f.event(19, flags), 1)
        f.native_value(0x4011DE70, 0)  # FUNC may be released before RECORD.
        self.assertEqual(f.event(19, 16), 1)
        self.assertEqual((f.get(0x200900 - s.STATE), f.get(0x200904 - s.STATE)), (1, 4))
        self.assertEqual(
            (self.read(f, clip.OWN), f.get(s.OWN), f.get(s.FREEZES)), (0, 0, 0)
        )
        self.assertEqual(bytes(f.cpu.mem_read(w.DEST, 4)), bytes(4))

    def test_func_stop_does_not_cancel_but_bare_stop_and_no_do(self):
        f = self.fixture()
        f.put(nb.STATE + nb.PHASE, 2)
        self.assertEqual(f.event(21, 3), 1)
        self.assertEqual(bytes(f.cpu.mem_read(nb.STATE + nb.CANCEL, 4)), bytes(4))
        self.assertEqual(f.event(21, 0), 1)
        f.native_value(0x4011DE70, 0)
        for key in (21, 12):
            f.put(nb.STATE + nb.CANCEL, 0)
            self.assertEqual(f.event(key, 1), 0)
            self.assertEqual(
                bytes(f.cpu.mem_read(nb.STATE + nb.CANCEL, 4)), struct.pack(">I", 1)
            )

    def test_ready_snapshot_survives_buf_replacement_and_selection_change(self):
        f = self.fixture()
        f.event(19, 1)
        f.event(19, 0)
        self.complete(f)
        self.assertEqual((self.read(f, clip.VALID), f.get(s.ACTION)), (1, clip.COPIED))
        f.put(s.STATE + s.BUF, 3)
        f.put(n.GEN, 999, 998, 997, 996)  # Live generation may change independently.
        self.assertEqual(f.call(clip.CHECK), 1)
        self.assertEqual(self.read(f, clip.SLOT), 77)

    def test_paste_reuses_one_take_on_two_tracks_through_stock_setter(self):
        f = self.fixture()
        f.event(19, 1)
        f.event(19, 0)
        self.complete(f)
        for track in (0, 4, 4):
            self.setter(f, track)
            before = bytes(f.cpu.mem_read(0x204000, 16 * 0x450))
            f.event(21, 1)
            f.event(21, 16)
            after = bytes(f.cpu.mem_read(0x204000, 16 * 0x450))
            expected = bytearray(before)
            struct.pack_into(">H", expected, track * 0x450 + 0x80, 77)
            self.assertEqual(after, bytes(expected))
            self.assertEqual(
                (f.get(s.ACTION), self.read(f, clip.TARGET)), (clip.PASTED, track + 1)
            )
        self.assertEqual(f.get(0x200900 - s.STATE), 1)
        self.assertEqual(self.read(f, clip.SLOT), 77)

    def test_empty_busy_and_unsupported_paste_do_not_mutate_track_or_cancel(self):
        f = self.fixture()
        f.call(clip.PASTE)
        self.assertEqual(f.get(s.ACTION), clip.NO_COPY)
        f.event(19, 1)
        f.event(19, 0)
        f.call(clip.PASTE)
        self.assertEqual(f.get(s.ACTION), clip.PASTE_BUSY)
        self.complete(f)
        self.setter(f)
        for at in (q.STOCK_BUSY, q.STATE + 56, w.STATE + 12, nb.STATE + nb.PHASE):
            f.put(at, 1)
            f.call(clip.PASTE)
            self.assertEqual(f.get(s.ACTION), clip.PASTE_BUSY)
            f.put(at, 0)
        f.cpu.mem_write(0x2040D6, bytes([5]))
        f.call(clip.PASTE)
        self.assertEqual(f.get(s.ACTION), clip.MACHINE)
        self.assertEqual(f.get(0x200D04 - s.STATE), 0)

    def test_full_failed_copy_preserves_previous_take_and_pending_does_not_resubmit(
        self,
    ):
        f = self.fixture()
        f.call(clip.COPY)
        f.call(clip.COPY)
        self.assertEqual(f.get(0x200900 - s.STATE), 1)
        self.complete(f)
        for result, message in (
            (-7, clip.BUSY),
            (-2, clip.EMPTY),
            (-5, clip.FULL),
            (-6, clip.FAILED),
        ):
            f.native_value(bf.SUBMIT, result)
            f.call(clip.COPY)
            self.assertEqual(f.get(s.ACTION), message)
            self.assertEqual(
                (self.read(f, clip.VALID), self.read(f, clip.SLOT)), (1, 77)
            )

    def test_stale_context_cache_pool_and_snapshot_fail_closed(self):
        f = self.fixture()
        f.call(clip.COPY)
        self.complete(f)
        for at in (
            n.STATE,
            0x80004704,
            0x44F370A0,
            w.STATE + 68,
            n.SNAP,
            n.SNAP + 8,
            0x405B1368 + 77 * 16 + 4,
            0x201000 + 77 * 16 + 4,
        ):
            old = bytes(f.cpu.mem_read(at, 4))
            f.put(at, 0)
            self.assertEqual(f.call(clip.CHECK), 0, hex(at))
            f.call(clip.PASTE)
            self.assertEqual(f.get(s.ACTION), clip.PASTE_STALE)
            f.cpu.mem_write(at, old)
        self.assertEqual(f.call(clip.CHECK), 1)

    def test_completion_failure_wrap_and_later_job_cannot_supply_wrong_take(self):
        for initial, completed, result, expected in (
            (0, 1, -3, clip.FAILED),
            (0, 2, 77, clip.STALE),
            (0xFFFFFFFF, 0, 77, clip.COPIED),
        ):
            f = self.fixture()
            f.put(q.STATE + 32, initial)
            f.call(clip.COPY)
            f.call(clip.FEEDBACK)
            self.assertEqual(self.read(f, clip.PENDING), 1)
            if expected == clip.COPIED:
                self.complete(f)
            else:
                f.put(q.STATE + 12, result & 0xFFFFFFFF)
                f.put(q.STATE + 32, completed)
                f.call(clip.FEEDBACK)
            self.assertEqual(f.get(s.ACTION), expected)
            self.assertEqual(self.read(f, clip.PENDING), 0)

    def test_other_views_unmodified_controls_song_and_modal_keep_ownership(self):
        f = self.fixture()
        for kind in ("other_view", "song", "no_func", "play"):
            f.put(s.STATE + s.VIEW, 0x200200 if kind == "other_view" else 0x200100)
            f.put(s.STATE + s.OWN, 2 if kind == "song" else 0)
            f.native_value(0x4011DE70, 0 if kind == "no_func" else 1)
            self.assertEqual(f.event(20 if kind == "play" else 19, 1), 0)
            self.assertEqual(f.get(0x200900 - s.STATE), 0)
        f.put(s.STATE + s.OWN, 0)
        f.event(19, 1)
        f.native_value(s.ROUTE_STOCK, 1)
        f.put(0x208400, 0, 0, 0, 19, 0)
        self.assertEqual(f.call(s.ROUTE, 0x200100, 0x208400), 1)
        self.assertEqual(self.read(f, clip.OWN), 0)

    def test_flag_required_and_original_payload_stays_exact(self):
        with self.assertRaisesRegex(ValueError, "FREEZE"):
            s.payload(STOCK_MAIN.read_bytes(), copy_shortcuts=True)
        f = self.fixture(enabled=False)
        self.assertEqual(f.event(19, 1), 0)
        f.put(nb.STATE + nb.PHASE, 2)
        self.assertEqual(f.event(21, 1), 0)
        self.assertEqual(
            bytes(f.cpu.mem_read(nb.STATE + nb.CANCEL, 4)), struct.pack(">I", 1)
        )
