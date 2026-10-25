"""Execute fixed setup, retained-marker refusals and feedback instructions."""

import os
import struct
import unittest
from pathlib import Path

from selector_core_support import Core
from unicorn import m68k_const as r

from lab import buf_fixed_slots as fixed
from lab import buf_selector as selector
from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab import sketch as sketch
from lab.emit import Code
from lab.sketch_device import build

STOCK = (
    Path(__file__).resolve().parents[1]
    / ".local/fixture/sections/section_3_MAIN_OS.bin"
)
POOL = 0x2101D2


class Fixture:
    def __init__(self):
        self.cpu = Core()
        for address, size in (
            (0x200000, 0x20000),
            (0x40000000, 0x300000),
            (0x405B0000, 0x10000),
            (w.BASE, w.END - w.BASE),
            (n.BASE, 0x8000),
            (0x10300000, 0x1000),
            (selector.nb.BASE, 0x8000),
            (sketch.BASE, 0x8000),
        ):
            self.cpu.mem_map(address, size)
        self.cpu.mem_write(w.SETUP, fixed.setup())
        self.value(0x401988A2, 0x200100)
        self.value(0x40041D18, 0x200100)
        self.value(0x200200, 0x210000)
        self.put(0x200100, 0x200180)
        self.put(0x2001A8, 0x200200)
        for slot in range(1024):
            self.put(POOL + slot * 16, 0xFFFFFFFF)
            self.put(0x405B1368 + slot * 16, 0xFFFFFFFF)
        self.put(n.RESERVED, 0xFFFFFFFF)

    def put(self, address, *values):
        self.cpu.mem_write(address, struct.pack(">" + "I" * len(values), *values))

    def get(self, address, count=1):
        return struct.unpack(">" + "I" * count, self.cpu.mem_read(address, count * 4))

    def value(self, address, value):
        c = Code()
        c.imm("203c", value)
        c.emit("4e75")
        self.cpu.mem_write(address, c.finish(address))

    def call(self, address, *args):
        self.put(0x20F000, 0x20FF00, *args)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(r.UC_M68K_REG_A7, 0x20F000)
        self.cpu.emu_start(address, 0x20FF00, count=150000)
        assert self.cpu.reg_read(r.UC_M68K_REG_PC) == 0x20FF00
        assert self.cpu.reg_read(r.UC_M68K_REG_A7) == 0x20F004
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def occupied(self, slot):
        self.put(POOL + slot * 16, 0x12345678, slot, 1, 0)

    def protected(self):
        return tuple(
            self.cpu.mem_read(at, length)
            for at, length in (
                (POOL, 16384),
                (0x405B0000, 65536),
                (n.STATE, 256),
                (n.RESERVED, 84),
                (w.STATE + 64, 96),
            )
        )


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "Rust ColdFire bridge required"
)
class FixedSlots(unittest.TestCase):
    def test_public_mapping_is_fixed_and_private_policy_stays_ascending(self):
        for prefix in (0, 144, 299):
            f = Fixture()
            for slot in range(1, prefix + 1):
                f.occupied(slot)
            pool_before = f.cpu.mem_read(POOL, 16384)
            self.assertEqual(f.call(w.SETUP), 0)
            self.assertEqual(f.get(w.STATE + 96, 4), fixed.PUBLIC)
            expected = tuple(slot for slot in range(prefix + 1, 1020) if slot % 128)[:8]
            self.assertEqual(f.get(w.STATE + 112, 8), expected)
            self.assertEqual(
                f.get(n.RESERVED, 13), fixed.PUBLIC + expected + (0xFFFFFFFF,)
            )
            self.assertEqual(f.get(w.STATE + 64), (1,))
            self.assertEqual(f.get(n.STATE + 16), (1,))
            self.assertEqual(f.get(w.DEST), (0,))
            self.assertEqual(f.cpu.mem_read(POOL, 16384), pool_before)
            for index, slot in enumerate(fixed.PUBLIC):
                self.assertEqual(
                    f.cpu.mem_read(0x405B6368 + slot * 16, 5),
                    f"BUF {index + 1}".encode(),
                )

    def test_occupied_public_slots_refuse_without_partial_ownership_or_fallback(self):
        for slot in fixed.PUBLIC:
            for kind in ("project", "cache", "length"):
                f = Fixture()
                if kind == "project":
                    f.occupied(slot)
                else:
                    f.put(
                        (0x405B1368 + slot * 16)
                        if kind == "cache"
                        else (0x405BA768 + slot * 4),
                        141,
                    )
                before = f.protected()
                self.assertEqual(f.call(w.SETUP), 0xFFFFFFFF)
                self.assertEqual(f.protected(), before)
                self.assertEqual(f.get(fixed.STATE, 2), (fixed.CONFLICT, slot))

    def test_retained_matching_markers_restore_empty_identity_without_pool_rewrites(
        self,
    ):
        f = Fixture()
        for index, slot in enumerate(fixed.PUBLIC):
            f.put(POOL + slot * 16, 0x7FFD0001 + index, 71 + index, 0, 0)
        before = f.cpu.mem_read(POOL, 16384)
        self.assertEqual(f.call(w.SETUP), 0)
        self.assertEqual(f.get(w.STATE + 96, 4), fixed.PUBLIC)
        self.assertEqual(f.get(fixed.STATE + fixed.RESTORED), (4,))
        self.assertEqual(f.cpu.mem_read(POOL, 16384), before)
        self.assertTrue(
            all(f.get(0x405BA768 + slot * 4) == (0,) for slot in fixed.PUBLIC)
        )

    def test_wrong_marker_or_nonempty_cache_is_not_adopted(self):
        for marker in (
            (0x7FFD0002, 1, 0, 0),
            (0x7FFD0001, 0, 0, 0),
            (0x7FFD0001, 1, 1, 0),
            (0x7FFD0001, 1, 0, 1),
        ):
            f = Fixture()
            f.put(POOL + 1020 * 16, *marker)
            before = f.protected()
            self.assertEqual(f.call(w.SETUP), 0xFFFFFFFF)
            self.assertEqual(f.protected(), before)
        f = Fixture()
        f.put(POOL + 1020 * 16, 0x7FFD0001, 1, 0, 0)
        f.put(0x405B1368 + 1020 * 16, 0x7FFB0001)
        self.assertEqual(f.call(w.SETUP), 0xFFFFFFFF)

    def test_old_B17_reference_is_preserved_and_never_migrated(self):
        f = Fixture()
        f.put(POOL + 145 * 16, 0x7FFD0001, 4, 0, 0)
        before = f.cpu.mem_read(POOL + 145 * 16, 16)
        self.assertEqual(f.call(w.SETUP), 0)
        self.assertEqual(f.get(w.STATE + 96, 4), fixed.PUBLIC)
        self.assertEqual(f.cpu.mem_read(POOL + 145 * 16, 16), before)
        self.assertNotIn(145, f.get(n.RESERVED, 12))

    def test_private_capacity_is_still_eight_and_failure_is_atomic(self):
        for count in (7, 8):
            f = Fixture()
            allowed = set(fixed.PUBLIC) | set(range(1, count + 1))
            for slot in range(1, 1024):
                if slot not in allowed:
                    f.occupied(slot)
            before = f.protected()
            self.assertEqual(f.call(w.SETUP), 0 if count == 8 else 0xFFFFFFFF)
            if count == 7:
                self.assertEqual(f.protected(), before)
                self.assertEqual(f.get(fixed.STATE), (fixed.CAPACITY,))

    def test_setup_is_idempotent_with_live_audio_and_checks_pool_identity(self):
        f = Fixture()
        self.assertEqual(f.call(w.SETUP), 0)
        f.put(0x405B1368 + 1020 * 16, 0x7FFB0001, 1, 48000, 1)
        f.put(0x405BA768 + 1020 * 4, 48000)
        before = f.protected()
        self.assertEqual(f.call(w.SETUP), 0)
        self.assertEqual(f.protected(), before)
        f.value(0x200200, 0x211000)
        self.assertEqual(f.call(w.SETUP), 0xFFFFFFFF)
        self.assertEqual(f.protected(), before)
        self.assertEqual(f.get(fixed.STATE), (fixed.PROJECT,))

    def test_native_aliases_keep_H_slots_and_NORMAL_OFF_defaults(self):
        f = Fixture()
        self.assertEqual(f.call(w.SETUP), 0)
        f.put(n.STATE + 32, *fixed.PUBLIC)
        f.put(selector.VIEW_ENABLED, 1)
        for at, raw in selector.payload(
            STOCK.read_bytes(), navigation_fixes=True
        ).items():
            f.cpu.mem_write(at, raw)
        for rank, slot in enumerate(reversed(fixed.PUBLIC)):
            self.assertEqual(f.call(selector.FORWARD, 0, rank), slot)
            self.assertEqual(f.call(selector.INVERSE, 0x200000, slot), rank)
        self.assertEqual(f.call(selector.FORWARD, 0, 4), 0)
        self.assertEqual(f.get(w.DEST), (0,))

    def test_fixed_feedback_formats_exact_conflict_and_capacity(self):
        f = Fixture()
        for at, raw in sketch.payload(
            STOCK.read_bytes(),
            arm_enabled=True,
            arm_diagnostics=True,
            clock_fix=True,
            performance_controls=True,
            fixed_buf_slots=True,
        ).items():
            f.cpu.mem_write(at, raw)
        for at in (
            sketch.ARM_FEEDBACK,
            sketch.READY,
            0x4001FD88,
            0x4001FDBE,
            0x4001FDF4,
            0x40015F6C,
            *sketch.GETTERS,
        ):
            f.value(at, 0)
        f.value(sketch.CLEAR, 1)
        f.value(0x4019988A, 0x205000)
        # Native print boundary captures format and first argument. Text captures
        # only y=9's source pointer; no fake fonts/pixels or rendered UI claim.
        c = Code()
        c.emit("202f0008")
        c.imm("23c0", 0x200700)
        c.emit("202f000c")
        c.imm("23c0", 0x200704)
        c.emit("7000 4e75")
        f.cpu.mem_write(sketch.PRINT, c.finish(sketch.PRINT))
        c = Code()
        c.emit("202f0010")
        c.imm("0c80", 9)
        c.branch(6, "return")
        c.emit("202f0018")
        c.imm("23c0", 0x200708)
        c.label("return")
        c.emit("7000 4e75")
        f.cpu.mem_write(sketch.TEXT, c.finish(sketch.TEXT))
        f.put(sketch.STATE + sketch.BUF, 1)
        for status, text in (
            (fixed.CONFLICT, b"BUF: H%03u IN USE"),
            (fixed.CAPACITY, b"BUF: NEED 8 FREE"),
            (fixed.PROJECT, b"BUF: POOL CHANGED"),
        ):
            f.put(fixed.STATE, status, 1020)
            f.call(sketch.DRAW, 0x200100, 0x200500)
            if status == fixed.CONFLICT:
                pointer = f.get(0x200700)[0]
                self.assertEqual(f.get(0x200704), (124,))
            else:
                pointer = f.get(0x200708)[0]
            self.assertEqual(f.cpu.mem_read(pointer, len(text)), text)

    def test_opt_in_profile_keeps_R3_exact_and_has_no_new_reservation(self):
        import hashlib

        flags = {
            "arm_diagnostics": True,
            "clock_fix": True,
            "buf_selector": True,
            "performance_controls": True,
            "navigation_fixes": True,
        }
        old, old_meta = build(STOCK.read_bytes(), **flags)
        self.assertEqual(
            hashlib.sha256(old).hexdigest(),
            "df5d524e037e2412aeaadb31e01108ebae381fb551aa002118d4d09aafdacf0c",
        )
        new, meta = build(STOCK.read_bytes(), **flags, fixed_buf_slots=True)
        self.assertNotEqual(old, new)
        self.assertEqual(meta["buf_public_slots"], list(fixed.PUBLIC))
        self.assertEqual(meta["reservation"], old_meta["reservation"])
        self.assertEqual(
            build(STOCK.read_bytes(), **flags, fixed_buf_slots=True), (new, meta)
        )
        with self.assertRaisesRegex(ValueError, "navigation"):
            build(STOCK.read_bytes(), fixed_buf_slots=True)
