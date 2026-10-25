"""Device-reported backing-row jump and native track-selection regression."""

import os
import struct
import unittest

import test_buf_selector as old_selector
import test_sketch_controls as old_controls

from lab import buf_selector as s
from lab import recorder_freeze_code as n
from lab import sketch as sk
from lab.runtime import STOCK_MAIN
from lab.sketch_device import build


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "Rust ColdFire bridge required"
)
class NavigationTests(unittest.TestCase):
    def selector(self, fixed=True):
        f = old_selector.SelectorTests()
        f.setUp()
        f.menu_boundaries()
        f.cpu.mem_map(0x4001E000, 4096)
        f.cpu.mem_write(0x4001E17A, bytes.fromhex("2039002006044e75"))
        f.cpu.mem_write(0x4001E5D0, bytes.fromhex("4e75"))
        f.put(0x200724, 0x200820)
        f.cpu.mem_write(0x200820, bytes.fromhex("2039002008104e75"))
        f.cpu.mem_write(0x200540, bytes.fromhex("202f000823c0002006004e75"))
        f.put(0x2000C4, 0x200540)
        f.put(n.STATE + 32, 145, 19, 300, 901)
        for at, raw in s.payload(
            STOCK_MAIN.read_bytes(), navigation_fixes=fixed
        ).items():
            f.cpu.mem_write(at, raw)
        f.menu_boundaries()
        return f

    def bank(self, f):
        return int.from_bytes(f.cpu.mem_read(0x2000A2, 2), "big")

    def rank(self, f):
        return int.from_bytes(f.cpu.mem_read(0x200810, 4), "big")

    def test_R2_reproduces_B17_jump_but_fixed_cursor_retains_all_ordinary_rows(self):
        f = self.selector(False)
        f.cpu.mem_write(0x2000A2, struct.pack(">H", 144))
        f.call(s.CURSOR, 0x200000, 145)
        self.assertEqual((self.bank(f), self.rank(f)), (0, 3))
        f = self.selector()
        roots = bytes(f.cpu.mem_read(n.STATE, 256))
        for slot in range(1024):
            f.call(s.CURSOR, 0x200000, slot)
            self.assertEqual(self.bank(f), slot)
            self.assertEqual(self.rank(f), (slot & 127) + (4 if slot < 128 else 0))
        self.assertEqual(bytes(f.cpu.mem_read(n.STATE, 256)), roots)
        self.assertEqual(bytes(f.cpu.mem_read(0x2000A0, 2)), b"\x00\x37")

    def test_alias_and_ordinary_A_backing_rows_have_distinct_cursor_ranks(self):
        from lab.emit import Code

        for mapping in ((145, 19, 300, 901), (1, 2, 3, 4)):
            f = self.selector()
            f.put(n.STATE + 32, *mapping)
            # Native listeners can synchronize the cursor while the absolute
            # setter runs. NAVIGATE must still finish at its intended rank.
            c = Code()
            c.emit("202f0008")
            c.imm("23c0", 0x200600)
            c.emit("2f00")
            c.imm("4879", 0x200000)
            n.call(c, s.CURSOR, 8)
            c.emit("4e75")
            f.cpu.mem_write(0x200540, c.finish(0x200540))
            for delta in (1, -1):
                ranks = range(132) if delta == 1 else range(131, -1, -1)
                for rank in ranks:
                    actual = f.call(s.FORWARD, 0, rank)
                    f.put(0x200604, actual)
                    f.put(0x200810, rank)
                    f.cpu.mem_write(
                        0x2000A2, struct.pack(">H", 0 if rank < 4 else actual)
                    )
                    self.assertEqual(
                        f.call(s.NAVIGATE, 0x200000, delta & 0xFFFFFFFF), 1
                    )
                    expected = max(0, min(131, rank + delta))
                    self.assertEqual(self.rank(f), expected)
                    target = f.call(s.FORWARD, 0, expected)
                    self.assertEqual(
                        int.from_bytes(f.cpu.mem_read(0x200600, 4), "big"), target
                    )

    def test_backing_rows_in_B_through_H_leave_arrows_and_bank_keys_to_stock(self):
        f = self.selector()
        for slot in (145, 300, 901):
            f.cpu.mem_write(0x2000A2, struct.pack(">H", slot))
            f.put(0x200604, slot)
            for fn, arg in (
                (s.NAVIGATE, 1),
                (s.NAVIGATE, 0xFFFFFFFF),
                (s.BANK, 13),
                (s.BANK, 15),
            ):
                f.put(0x200600, 0xCAFEBABE)
                self.assertEqual(f.call(fn, 0x200000, arg), 0)
                self.assertEqual(
                    int.from_bytes(f.cpu.mem_read(0x200600, 4), "big"), 0xCAFEBABE
                )

    def test_reopening_assigned_BUF_canonicalizes_only_at_construction(self):
        f = self.selector()
        f.cpu.mem_map(0x40111000, 4096)
        for at in (s.nb.INIT_BODY, 0x40111888):
            f.cpu.mem_write(at, bytes.fromhex("4e75"))
        f.cpu.mem_write(0x2000A0, struct.pack(">HH", 145, 145))
        f.call(s.BUILD, 0x200000)
        self.assertEqual((self.bank(f), self.rank(f)), (145, 17))
        f.cpu.reg_write(old_selector.r.UC_M68K_REG_A2, 0x200000)
        self.assertEqual(f.call(s.INITIAL), 3)
        self.assertEqual(self.bank(f), 0)
        self.assertEqual(bytes(f.cpu.mem_read(0x2000A0, 2)), struct.pack(">H", 145))

    def test_native_rebuild_and_subscription_keep_an_open_BUF_alias(self):
        from lab.emit import Code

        f = self.selector()
        f.cpu.mem_write(0x2000A0, struct.pack(">HH", 145, 145))
        f.cpu.reg_write(old_selector.r.UC_M68K_REG_A2, 0x200000)
        c = Code()
        c.imm("4879", 145)
        c.imm("4879", 0x200000)
        n.call(c, s.CURSOR, 8)
        c.emit("4e75")
        f.cpu.mem_write(s.BUILD_STOCK, c.finish(s.BUILD_STOCK))
        self.assertEqual(f.call(s.INITIAL), 3)
        self.assertEqual((self.bank(f), self.rank(f)), (0, 3))
        f.call(s.CURSOR, 0x200000, 145)
        self.assertEqual((self.bank(f), self.rank(f)), (0, 3))
        # The identical slot in an ordinary B row is a different presentation.
        f.cpu.mem_write(0x2000A2, struct.pack(">H", 145))
        f.call(s.CURSOR, 0x200000, 145)
        self.assertEqual((self.bank(f), self.rank(f)), (145, 17))

    def test_track_selection_closes_only_owned_view_on_press(self):
        f = old_controls.PerformanceControls().view()
        code, _ = sk.route(bytes.fromhex("4fefffa048d77cfc"), navigation_fixes=True)
        f.cpu.mem_write(sk.ROUTE, code)
        f.native_value(sk.ROUTE_STOCK, 47)
        controller, node = 0x200A00, 0x200B00
        f.put(controller + 0x18, node)
        f.put(node + 8, 0x200100)
        # TRK press leaves before its native overlay/listener owns later pads.
        for flags in (1, 9, 0x29, 0x10):
            f.put(0x208400, 0, 0, 0, 16, flags)
            self.assertEqual(f.call(sk.ROUTE, controller, 0x208400), 47)
        self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200900, 4), "big"), 1)
        for key in range(25, 41):
            f.put(0x208400, 0, 0, 0, key, 1)
            self.assertEqual(f.call(sk.ROUTE, controller, 0x208400), 47)
        self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200900, 4), "big"), 1)
        # A foreign modal, an empty stack or an owned SONG gesture retain
        # precedence. The original event and return code stay untouched.
        for owner, top in ((0, 0x200200), (1, 0x200100)):
            f.put(node + 8, top)
            f.put(sk.STATE + sk.OWN, owner)
            f.put(0x208400, 0, 0, 0, 16, 1)
            self.assertEqual(f.call(sk.ROUTE, controller, 0x208400), 47)
            self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200900, 4), "big"), 1)
        f.put(sk.STATE + sk.OWN, 0)
        f.put(controller + 0x18, controller + 0x14)
        self.assertEqual(f.call(sk.ROUTE, controller, 0x208400), 47)
        self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200900, 4), "big"), 1)

    def test_all_sixteen_trigs_exit_only_top_sketch_and_forward_original_event(self):
        code = sk.payload(
            STOCK_MAIN.read_bytes(), arm_enabled=True, freeze_enabled=True,
            performance_controls=True, navigation_fixes=True,
            startup_capture=True, copy_shortcuts=True, stopped_recording=True,
        )[sk.ROUTE]
        for key in range(25, 41):
            with self.subTest(key=key):
                f = old_controls.PerformanceControls().view()
                f.cpu.mem_write(sk.ROUTE, code)
                f.native_value(sk.ROUTE_STOCK, 47)
                controller, node = 0x200A00, 0x200B00
                f.put(controller + 0x18, node)
                f.put(node + 8, 0x200100)
                for owner, top, flags, closes in (
                    (0, 0x200100, 0x10, 0),
                    (0, 0x200100, 9, 0),
                    (1, 0x200100, 1, 0),
                    (0, 0x200200, 1, 0),
                    (0, 0x200100, 1, 1),
                ):
                    f.put(sk.STATE + sk.OWN, owner)
                    f.put(node + 8, top)
                    f.put(0x208400, 0, 0, 0, key, flags)
                    before = bytes(f.cpu.mem_read(0x208400, 20))
                    self.assertEqual(f.call(sk.ROUTE, controller, 0x208400), 47)
                    self.assertEqual(bytes(f.cpu.mem_read(0x208400, 20)), before)
                    self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200900, 4), 'big'), closes)

    def test_reserved_backing_slot_still_rejects_an_ordinary_sample_load(self):
        from lab import recorder_worker_code as w

        f = self.selector()
        f.cpu.mem_map(0x10300000, 4096)
        f.cpu.mem_map(w.SLOT_GUARDS, 4096)
        f.put(n.RESERVED, 145, 146, 147, 148, 0xFFFFFFFF)
        f.cpu.mem_write(0x200A00, bytes.fromhex("702a4e75"))
        f.cpu.mem_write(w.SLOT_GUARDS, w.slot_guard(w.SLOT_GUARDS, 0x200A00, load=True))
        self.assertEqual(f.call(w.SLOT_GUARDS, 0, 145), 0xFFFFFFFF)
        self.assertEqual(f.call(w.SLOT_GUARDS, 0, 149), 42)

    def test_profile_disabled_reproduces_R2_and_changes_no_storage_hooks(self):
        from hashlib import sha256

        flags = dict(
            arm_diagnostics=True,
            clock_fix=True,
            buf_selector=True,
            performance_controls=True,
        )
        before, baseline = build(STOCK_MAIN.read_bytes(), **flags)
        self.assertEqual(
            sha256(before).hexdigest(),
            "7b3c783fcedd97fa459fb5005c73d3cc0978107acdf98cd37ce7ad209fc22d66",
        )
        after, changed = build(STOCK_MAIN.read_bytes(), **flags, navigation_fixes=True)
        self.assertNotEqual(before, after)
        self.assertEqual(baseline["reservation"], changed["reservation"])
        self.assertEqual(baseline["hooks"], changed["hooks"])
        self.assertTrue(changed["navigation_fixes"])
