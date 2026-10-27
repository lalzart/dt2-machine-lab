"""Post-recording popup instructions, with named native UI/parameter seams."""

import json
import os
import struct
import unittest

import test_sketch_controls as controls
import test_sketch_copy as copying

from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as jobs
from lab import recorder_worker_code as w
from lab import sketch as s
from lab import sketch_assign as a
from lab import sketch_managed as m
from lab import sketchbook_ui as book
from lab.emit import Code
from lab.project import ROOT
from lab.runtime import STOCK_MAIN


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "Explicit Rust ColdFire bridge required"
)
class AssignmentPopup(unittest.TestCase):
    def setUp(self):
        self.f = f = controls.PerformanceControls().view()
        f.cpu.mem_map(a.BASE, a.SIZE)
        f.cpu.mem_map(m.BASE, m.SIZE)
        f.cpu.mem_map(book.STATE & ~4095, 4096)
        f.cpu.mem_map(0x210000, 0x10000)
        f.cpu.mem_map(nb.TICK & ~4095, 4096)
        f.cpu.mem_map(w.ASSIGN & ~4095, 4096)
        f.cpu.mem_map(a.preview.CANCEL_KEY & ~4095, 4096)
        for parts in a.payload(STOCK_MAIN.read_bytes()):
            for at, raw in parts.items():
                f.cpu.mem_write(at, raw)
        f.put(n.STATE, 11)
        f.put(w.STATE + 68, 0x210000)
        f.put(w.STATE + 96, 1020, 1021, 1022, 1023)
        for buf in range(1, 5):
            slot = 1019 + buf
            f.put(0x405B1368 + slot * 16, 0x7FFB0000 + buf, 0x1000, 4000, 1)
            f.put(0x210000 + slot * 16, 0x7FFB0000 + buf, 11, 4000, 1)
        f.put(nb.STATE + nb.DEST, 2)
        # Native View push/heap is tested by the coupled cold-boot probe.
        c = Code()
        a.value(c, a.VIEW, 0x200500)
        a.value(c, a.PENDING, 0)
        a.inc(c, a.SHOWN)
        c.emit("4e75")
        f.cpu.mem_write(a.OPEN, c.finish(a.OPEN))
        f.native_value(a.TOP, 0x200100)
        f.call(a.QUEUE)

    def get(self, field):
        return int.from_bytes(self.f.cpu.mem_read(a.STATE + field, 4), "big")

    def event(self, key, flags):
        self.f.put(0x20E000, 0, 0, 0, key, flags)
        return self.f.call(a.KEY, 0x200500, 0x20E000)

    def setter(self, track):
        copying.CopyShortcuts().setter(self.f, track)

    def test_success_opens_once_and_selection_changes_do_not_relabel_recording(self):
        f = self.f
        f.put(s.STATE + s.BUF, 4)
        f.call(a.SERVICE)
        f.call(a.SERVICE)
        self.assertEqual(
            (self.get(a.BUF), self.get(a.SLOT), self.get(a.SHOWN)), (2, 1021, 1)
        )
        self.setter(15)
        self.assertEqual(self.event(40, 1), 1)
        self.assertEqual(self.get(a.ASSIGNED), 0)
        self.assertEqual(self.event(40, 16), 1)
        self.assertEqual(
            (self.get(a.RESULT), self.get(a.TARGET), self.get(a.ASSIGNED)),
            (a.OK, 16, 1),
        )
        self.assertEqual(
            f.cpu.mem_read(0x204000 + 15 * 0x450 + 0x80, 2), struct.pack(">H", 1021)
        )
        self.event(40, 16)
        self.assertEqual(self.get(a.ASSIGNED), 1)
        self.assertEqual(f.get(0x200900 - s.STATE), 1)  # deferred close requested once

    def test_no_preserves_entire_kit_and_all_buffer_associations(self):
        f = self.f
        f.call(a.SERVICE)
        kit, pool = (
            f.cpu.mem_read(0x204000, 16 * 0x450),
            f.cpu.mem_read(0x210000, 16384),
        )
        f.cpu.mem_write(a.ASSIGN, bytes.fromhex("4afc"))
        self.event(12, 1)
        self.assertEqual(self.get(a.CLOSING), 0)
        self.event(12, 16)
        self.assertEqual((self.get(a.RESULT), self.get(a.SKIPPED)), (a.NO, 1))
        self.assertEqual(f.cpu.mem_read(0x204000, 16 * 0x450), kit)
        self.assertEqual(f.cpu.mem_read(0x210000, 16384), pool)

    def test_unmatched_release_hold_repeat_and_other_keys_do_nothing(self):
        self.f.call(a.SERVICE)
        self.f.cpu.mem_write(a.ASSIGN, bytes.fromhex("4afc"))
        for key, flags in (
            (25, 16),
            (12, 16),
            (25, 9),
            (25, 0x29),
            (25, 16),
            (10, 1),
            (10, 16),
        ):
            self.assertEqual(self.event(key, flags), 1)
        self.assertEqual(
            (self.get(a.ASSIGNED), self.get(a.CLOSING), self.get(a.PRESSED)), (0, 0, 0)
        )
        self.event(12, 1)
        self.event(25, 16)
        self.assertEqual(self.get(a.CLOSING), 0)
        self.event(12, 16)
        self.assertEqual(self.get(a.RESULT), a.NO)

    def test_native_fast_second_press_is_a_fresh_owned_choice(self):
        self.f.call(a.SERVICE)
        self.setter(0)
        self.event(25, 5)
        self.assertEqual(self.get(a.ASSIGNED), 0)
        self.event(25, 16)
        self.assertEqual((self.get(a.RESULT), self.get(a.ASSIGNED)), (a.OK, 1))

    def test_supported_machines_and_track_bounds_with_stock_setter(self):
        f = self.f
        for track, machine in ((0, 0), (3, 1), (5, 2), (7, 3), (9, 4), (15, 6)):
            with self.subTest(track=track, machine=machine):
                self.setter(track)
                f.cpu.mem_write(0x204000 + track * 0x450 + 0xD6, bytes([machine]))
                before = bytearray(f.cpu.mem_read(0x204000, 16 * 0x450))
                self.assertEqual(f.call(a.ASSIGN, track), a.OK)
                before[track * 0x450 + 0x80 : track * 0x450 + 0x82] = struct.pack(
                    ">H", 1021
                )
                self.assertEqual(f.cpu.mem_read(0x204000, 16 * 0x450), before)
        for track in (16, 0xFFFFFFFF):
            self.assertEqual(f.call(a.ASSIGN, track), a.FAILED)

    def test_midi_keeps_prompt_open_then_accepts_an_audio_track(self):
        f = self.f
        f.call(a.SERVICE)
        f.cpu.mem_write(0x204000 + 0xD6, bytes([5]))
        self.event(25, 1)
        self.event(25, 16)
        self.assertEqual((self.get(a.RESULT), self.get(a.CLOSING)), (a.MIDI, 0))
        self.setter(15)
        self.event(40, 1)
        self.event(40, 16)
        self.assertEqual((self.get(a.RESULT), self.get(a.CLOSING)), (a.OK, 1))

    def test_stale_contexts_or_replaced_take_cannot_assign_or_reopen(self):
        for at in (
            n.STATE,
            0x80004704,
            0x44F370A0,
            w.STATE + 68,
            0x405B1368 + 1021 * 16,
            0x210000 + 1021 * 16,
        ):
            with self.subTest(at=hex(at)):
                self.setUp()
                f = self.f
                f.put(at, 0)
                f.cpu.mem_write(0x40045582, bytes.fromhex("4afc"))
                self.assertEqual(f.call(a.ASSIGN, 0), a.STALE)
                f.call(a.SERVICE)
                self.assertEqual(
                    (self.get(a.PENDING), self.get(a.SHOWN), self.get(a.RESULT)),
                    (0, 0, a.STALE),
                )

    def test_busy_defers_and_new_capture_discards_pending_request(self):
        f = self.f
        for at in (jobs.STOCK_BUSY, jobs.STATE + 56, w.STATE + 12):
            f.put(at, 1)
            self.assertEqual(f.call(a.ASSIGN, 0), a.BUSY)
            f.call(a.SERVICE)
            self.assertEqual((self.get(a.PENDING), self.get(a.SHOWN)), (1, 0))
            f.put(at, 0)
        f.put(nb.STATE + nb.PHASE, 2)
        f.call(a.SERVICE)
        self.assertEqual((self.get(a.PENDING), self.get(a.RESULT)), (0, a.STALE))

    def test_foreign_dialog_and_owned_capture_release_defer_popup(self):
        f = self.f
        f.native_value(a.TOP, 0x200600)
        f.put(0x200600, 0x200700)
        f.put(0x200708, 0x123456)
        f.call(a.SERVICE)
        self.assertEqual(self.get(a.SHOWN), 0)
        f.put(0x200708, s.MAIN_SITE)
        for at in (s.STATE + s.OWN, s.STATE + s.FUNC_OWN, m.STATE + m.BORROWED):
            f.put(at, 1)
            f.call(a.SERVICE)
            self.assertEqual(self.get(a.SHOWN), 0)
            f.put(at, 0)
        f.call(a.SERVICE)
        self.assertEqual(self.get(a.SHOWN), 1)

    def test_top_route_absorbs_press_and_release_before_stock_track_listener(self):
        f = self.f
        f.call(a.SERVICE)
        f.put(0x200800 + 0x18, 0x200900)
        f.put(0x200900 + 8, 0x200500)
        f.cpu.mem_write(a.preview.CANCEL_KEY, bytes.fromhex("4afc"))
        for flags in (1, 16):
            f.put(0x20E000, 0, 0, 0, 12, flags)
            self.assertEqual(f.call(a.ROUTE, 0x200800, 0x20E000), 1)
        self.assertEqual(self.get(a.RESULT), a.NO)

    def test_publication_notifier_only_runs_on_success(self):
        f = self.f
        f.cpu.mem_write(
            nb.DONE, nb.done(release_recorder=True, publication_notify=a.QUEUE)
        )
        f.native_value(nb.CHECK, 0)
        f.native_value(w.ASSIGN, 0)
        f.native_value(nb.DISCARD, 0)
        for status, lease, expected in ((-1, 1, 0), (0, 0, 0), (0, 1, 1)):
            f.put(a.STATE + a.PENDING, 0)
            f.put(w.STATE + 12, lease)
            for at, val in (
                (nb.STATE + nb.KIT, 0x204000),
                (w.STATE + 44, 0x204000),
                (nb.STATE + nb.EPOCH, 11),
                (w.STATE + 60, 11),
                (w.STATE + 56, 2),
            ):
                f.put(at, val)
            f.call(nb.DONE, 0, status & 0xFFFFFFFF)
            self.assertEqual(self.get(a.PENDING), expected)

    def test_held_buttons_finish_their_release_before_prompt_can_open(self):
        f = self.f
        for held in (1, 17, 25, 40, 50):
            c = Code()
            c.emit("202f0004")
            c.imm("0c80", held)
            c.emit("57c0 4e75")
            f.cpu.mem_write(0x4011DE70, c.finish(0x4011DE70))
            f.call(a.SERVICE)
            self.assertEqual((self.get(a.SHOWN), self.get(a.PENDING)), (0, 1))
        f.native_value(0x4011DE70, 0)
        f.call(a.SERVICE)
        self.assertEqual(self.get(a.SHOWN), 1)

    def test_view_walk_skips_only_stock_main_layers_and_respects_other_modal(self):
        f = self.f
        f.put(0x200818, 0x200900)
        f.put(0x200904, 0x200920, 0x200600)
        f.put(0x200924, 0x200814, 0x200500)
        for table in a.RESIDENT_VTABLES:
            f.put(0x200600, table)
            self.assertEqual(f.call(a.TOP_FROM, 0x200800), 0x200500)
        f.put(0x200600, 0x40123456)
        self.assertEqual(f.call(a.TOP_FROM, 0x200800), 0x200600)
        f.put(a.STATE + a.VIEW, 0x200500)
        f.native_value(a.preview.CANCEL_KEY, 55)
        f.put(0x20E000, 0, 0, 0, 12, 1)
        self.assertEqual(f.call(a.ROUTE, 0x200800, 0x20E000), 55)
        self.assertEqual(self.get(a.PRESSED), 0)
        f.put(0x200818, 0x200814)
        self.assertEqual(f.call(a.TOP_FROM, 0x200800), 0)

    def test_each_buffer_queues_its_own_slot_and_invalid_destination_is_ignored(self):
        f = self.f
        for buf in range(1, 5):
            f.put(nb.STATE + nb.DEST, buf)
            f.call(a.QUEUE)
            self.assertEqual((self.get(a.BUF), self.get(a.SLOT)), (buf, 1019 + buf))
            self.assertEqual(f.call(a.CHECK), 1)
        for buf in (0, 5, 0xFFFFFFFF):
            f.put(nb.STATE + nb.DEST, buf)
            f.call(a.QUEUE)
            self.assertEqual(self.get(a.PENDING), 0)


class PopupPlacement(unittest.TestCase):
    def test_off_preserves_previous_managed_image_and_on_is_guarded(self):
        from lab.sketch_device import ASSIGN_END, MANAGED_END, build
        from lab.sketch_device_validation import read_segments

        flags = {
            name.replace("-", "_"): True
            for name in json.loads((ROOT / "profiles/sketch-managed.json").read_text())[
                "build_flags"
            ]
        }
        _, off = build(STOCK_MAIN.read_bytes(), **flags)
        self.assertEqual(
            off["sha256"],
            "4c7f99100063de90164bf47197761a2fb0d19e45a4763219e5a40b44ebcb58bf",
        )
        image, on = build(STOCK_MAIN.read_bytes(), **flags, assign_popup=True)
        self.assertEqual(on["reservation"][1], ASSIGN_END)
        self.assertEqual(off["reservation"][1], MANAGED_END)
        self.assertEqual(len(read_segments(image, on)), len(on["segments"]))
        self.assertEqual(
            (image, on), build(STOCK_MAIN.read_bytes(), **flags, assign_popup=True)
        )
        with self.assertRaisesRegex(ValueError, "requires managed"):
            build(STOCK_MAIN.read_bytes(), assign_popup=True)
