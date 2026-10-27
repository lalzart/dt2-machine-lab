"""Execute startup placeholders and guarded early reservation on ColdFire."""

import json
import os
import unittest

import test_buf_navigation as navigation
import test_buf_startup as startup_tests
from unicorn import m68k_const as r

from lab import buf_fixed_slots as fixed
from lab import buf_loading as loading
from lab import buf_next_bar as b
from lab import buf_selector as selector
from lab import buf_startup as startup
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as jobs
from lab import recorder_worker_code as w
from lab import sketch_managed as managed
from lab.runtime import STOCK_MAIN


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "Rust ColdFire bridge required"
)
class Loading(unittest.TestCase):
    def selector(self):
        f = navigation.NavigationTests().selector()
        f.cpu.mem_map(managed.BASE, managed.SIZE)
        for parts in loading.payload():
            for at, raw in parts.items():
                f.cpu.mem_write(at, raw)
        for at, raw in selector.payload(
            STOCK_MAIN.read_bytes(), navigation_fixes=True, buf_loading=True
        ).items():
            f.cpu.mem_write(at, raw)
        f.menu_boundaries()
        f.put(w.STATE + 64, 0)
        f.put(n.STATE + 32, 0, 0, 0, 0)
        f.put(b.STATE + startup.BATCH_ACTIVE, 1)
        f.cpu.mem_write(0x2000A2, bytes(2))
        return f

    def ready(self, f):
        f.put(w.STATE + 64, 1)
        f.put(n.STATE + 32, *fixed.PUBLIC)

    def test_pending_rows_keep_ordinary_slot_mapping_and_cancel_identity(self):
        f = self.selector()
        before = bytes(f.cpu.mem_read(n.STATE, 256))
        for slot in range(1024):
            rank = f.call(selector.INVERSE, 0x200000, slot)
            self.assertEqual(rank, (slot & 127) + (4 if slot < 128 else 0))
            self.assertEqual(f.call(selector.FORWARD, slot, rank), slot)
        self.assertEqual(bytes(f.cpu.mem_read(n.STATE, 256)), before)
        self.assertEqual(bytes(f.cpu.mem_read(0x2000A0, 2)), b"\x00\x37")
        for rank in range(4):
            self.assertEqual(f.call(selector.FORWARD, 0, rank), 0)

    def test_loading_rows_cannot_assign_unowned_backing_slots_then_unlock_in_place(
        self,
    ):
        f = self.selector()
        f.put(0x200604, 0)
        f.put(0x200810, 4)
        f.put(0x200600, 0xDEADBEEF)
        self.assertEqual(f.call(selector.NAVIGATE, 0x200000, 0xFFFFFFFF), 1)
        self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200810, 4), "big"), 3)
        self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200600, 4), "big"), 0xDEADBEEF)
        self.ready(f)
        self.assertEqual(f.call(selector.NAVIGATE, 0x200000, 0), 1)
        self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200810, 4), "big"), 3)
        self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200600, 4), "big"), 1020)

    def test_pending_confirm_does_not_assign_and_ready_confirm_uses_current_row(self):
        f = self.selector()
        f.cpu.mem_write(selector.KEY_STOCK, bytes.fromhex("702a4e75"))
        for slot in (0, 7, 127):
            f.cpu.mem_write(0x2000A2, slot.to_bytes(2, "big"))
            f.put(0x200604, slot)
            f.put(0x200810, 3)
            for flags in (1, 0x10):
                f.put(0x200900, 0, 0, 0, 10, flags)
                f.put(0x200600, 0xDEADBEEF)
                self.assertEqual(f.call(selector.KEY, 0x200000, 0x200900), 1)
                self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200600, 4), "big"), 0xDEADBEEF)
        self.ready(f)
        f.put(0x200900, 0, 0, 0, 10, 1)
        self.assertEqual(f.call(selector.KEY, 0x200000, 0x200900), 42)
        self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200600, 4), "big"), 1020)
        self.assertEqual(int.from_bytes(f.cpu.mem_read(0x200810, 4), "big"), 3)

    def test_defensive_resolver_retains_current_sample_on_disabled_row(self):
        f = self.selector()
        for slot in (0, 1, 127):
            for rank in range(4):
                f.cpu.reg_write(r.UC_M68K_REG_D0, rank)
                f.cpu.reg_write(r.UC_M68K_REG_D2, 0xDEAD0000 | slot)
                f.cpu.reg_write(r.UC_M68K_REG_A7, 0x20F000)
                f.cpu.emu_start(selector.RESOLVE, 0x4001E1E6, count=10000)
                self.assertEqual(f.cpu.reg_read(r.UC_M68K_REG_D2), slot)

    def test_native_list_rebuild_keeps_loading_rows_and_original_sample(self):
        f = self.selector()
        f.cpu.mem_map(0x40111000, 4096)
        for at in (b.INIT_BODY, 0x40111888):
            f.cpu.mem_write(at, bytes.fromhex("4e75"))
        for actual in (0, 7, 127, 128, 1020):
            f.cpu.mem_write(0x2000A2, actual.to_bytes(2, "big"))
            f.call(selector.BUILD, 0x200000)
            self.assertEqual(
                int.from_bytes(f.cpu.mem_read(selector.VIEW_ENABLED, 4), "big"), 1
            )
            self.assertEqual(
                int.from_bytes(f.cpu.mem_read(0x200810, 4), "big"),
                (actual & 127) + (4 if actual < 128 else 0),
            )
        self.assertEqual(bytes(f.cpu.mem_read(0x2000A0, 2)), b"\x00\x37")

    def test_sketch_loading_status_preserves_active_recording_feedback(self):
        f = self.selector()
        f.cpu.mem_write(managed.STATUS_TEXT, managed.status_text(buf_loading=True))
        f.cpu.mem_write(managed.STATUS, bytes.fromhex("70034e75"))
        self.assertEqual(f.call(managed.STATUS_TEXT), loading.TEXTS)
        f.put(b.STATE + startup.POISON, 1)
        self.assertEqual(f.call(managed.STATUS_TEXT), loading.TEXTS + 16)
        f.put(b.STATE + b.PHASE, 2)
        self.assertEqual(
            f.call(managed.STATUS_TEXT), managed.TEXTS + managed.RECORDING * 16
        )
        f.put(b.STATE + b.PHASE, 6)
        self.assertEqual(f.call(managed.STATUS_TEXT), loading.TEXTS)

    def test_formatter_loading_unavailable_empty_ready_without_reopening(self):
        f = self.selector()
        for at, size in ((0x40115000, 4096), (0x401E7000, 4096), (0x405B0000, 0x10000)):
            f.cpu.mem_map(at, size)
        f.cpu.mem_write(0x401154E0, bytes.fromhex("202f00044e75"))
        f.cpu.mem_write(0x401E7A64, bytes.fromhex("206f000420af00084e75"))
        f.put(0x200200, 0x200210)
        f.put(0x200210, 0x200000)
        for expected in ("LOADING", "UNAVAIL", "EMPTY", "READY"):
            if expected == "UNAVAIL":
                f.put(b.STATE + startup.BATCH_DONE, 1)
                f.put(fixed.STATE + fixed.STATUS, fixed.CONFLICT)
            if expected in ("EMPTY", "READY"):
                self.ready(f)
            for rank, slot in enumerate(reversed(fixed.PUBLIC)):
                f.put(0x405B1368 + slot * 16 + 8, 100 if expected == "READY" else 0)
                f.cpu.reg_write(r.UC_M68K_REG_A0, 0x200400)
                f.call(selector.FORMAT, 0x200200, rank)
                ptr = int.from_bytes(f.cpu.mem_read(0x200400, 4), "big")
                self.assertEqual(
                    f.cpu.mem_read(ptr, 16).split(b"\0")[0].decode(),
                    f"BUF {4 - rank} {expected}",
                )

    def early(self):
        f = startup_tests.PendingCapture().setup_fixture(capacity=True)
        f.cpu.mem_map(managed.BASE, managed.SIZE)
        for parts in loading.payload(early_setup=True):
            for at, raw in parts.items():
                f.cpu.mem_write(at, raw)
        f.cpu.reg_write(r.UC_M68K_REG_A2, 0x200100)
        f.put(b.STATE + startup.BATCH_ACTIVE, 1)
        f.put(b.STATE + startup.BATCH_DONE, 0)
        return f

    def test_early_setup_reserves_metadata_before_loads_without_changing_pool(self):
        from test_buf_fixed_slots import POOL

        f = self.early()
        pool = f.cpu.mem_read(POOL, 16384)
        f.call(loading.EARLY)
        self.assertEqual(f.get(w.STATE + 64), (1,))
        self.assertEqual(f.get(n.STATE + 32, 4), fixed.PUBLIC)
        self.assertEqual(f.get(loading.ATTEMPTS), (1,))
        self.assertEqual(f.get(loading.RESULT), (1,))
        self.assertEqual(f.cpu.mem_read(POOL, 16384), pool)
        self.assertEqual(f.get(w.STATE + 12), (0,))
        self.assertEqual(f.get(b.STATE + startup.BATCH_ACTIVE), (1,))
        f.call(loading.EARLY)
        self.assertEqual(f.get(loading.ATTEMPTS), (1,))

    def test_early_setup_retains_busy_capture_and_project_guards(self):
        for at in (
            w.STATE + 12,
            n.STATE + 24,
            jobs.STATE + 56,
            jobs.STOCK_BUSY,
            b.STATE + b.PHASE,
            b.STATE + startup.POISON,
        ):
            with self.subTest(guard=hex(at)):
                f = self.early()
                f.put(at, 1)
                protected = f.protected()
                f.call(loading.EARLY)
                self.assertEqual(f.protected(), protected)
                self.assertEqual(f.get(at), (1,))
                self.assertEqual(f.get(w.STATE + 64), (0,))
        f = self.early()
        f.cpu.reg_write(r.UC_M68K_REG_A2, 0x200300)
        f.call(loading.EARLY)
        self.assertEqual(f.get(loading.ATTEMPTS), (0,))

    def test_conflicting_sample_is_preserved_and_later_setup_can_recover(self):
        from test_buf_fixed_slots import POOL

        f = self.early()
        f.occupied(1020)
        protected = f.protected()
        f.call(loading.EARLY)
        self.assertEqual(f.protected(), protected)
        self.assertEqual(f.get(w.STATE + 64), (0,))
        self.assertEqual(f.get(fixed.STATE + fixed.STATUS), (fixed.CONFLICT,))
        f.put(b.STATE + startup.BATCH_ACTIVE, 0)
        f.put(b.STATE + startup.BATCH_DONE, 1)
        self.assertEqual(f.call(loading.AVAILABILITY), 2)
        f.put(POOL + 1020 * 16, 0xFFFFFFFF, 0, 0, 0)
        f.put(b.TICK, startup.SETUP_RETRY_FRAMES)
        f.call(b.INIT_BODY)
        self.assertEqual(f.get(w.STATE + 64), (1,))


class Placement(unittest.TestCase):
    def test_optional_flags_preserve_previous_image_and_arenas(self):
        from lab.project import ROOT
        from lab.sketch_device import build

        flags = {
            k.replace("-", "_"): True
            for k in json.loads((ROOT / "profiles/sketch-managed.json").read_text())[
                "build_flags"
            ]
        }
        _, old = build(STOCK_MAIN.read_bytes(), **flags, assign_popup=True)
        self.assertEqual(
            old["sha256"],
            "b62584d425f31c22f1e8013234e23f03c36177d8ab6a0312767e7568d91d4431",
        )
        _, new = build(
            STOCK_MAIN.read_bytes(),
            **flags,
            assign_popup=True,
            buf_loading=True,
            early_buf_setup=True,
        )
        self.assertEqual(new["arenas"], old["arenas"])
        self.assertEqual(new["reservation"], old["reservation"])
        with self.assertRaisesRegex(ValueError, "requires managed"):
            build(STOCK_MAIN.read_bytes(), buf_loading=True)
        with self.assertRaisesRegex(ValueError, "requires loading"):
            build(STOCK_MAIN.read_bytes(), **flags, early_buf_setup=True)
