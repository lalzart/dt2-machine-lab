"""Execute rank conversion instructions against varied project mappings."""

import os
import struct
import unittest

import unicorn as u
from unicorn import m68k_const as r

from lab import buf_selector as s
from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab.runtime import STOCK_MAIN


class SelectorTests(unittest.TestCase):
    def setUp(self):
        if os.environ.get("DT2_BUF_SELECTOR_CORE"):
            from selector_core_support import Core

            self.cpu = Core()
        else:
            self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
            self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for at, size in (
            (s.nb.BASE, 0x8000),
            (w.BASE, 4096),
            (n.BASE, 4096),
            (0x200000, 0x10000),
        ):
            self.cpu.mem_map(at, size)
        for at, code in s.payload(STOCK_MAIN.read_bytes()).items():
            self.cpu.mem_write(at, code)
        self.put(w.STATE + 64, 1)
        self.put(s.VIEW_ENABLED, 1)
        self.put(n.STATE + 32, 901, 19, 555, 300)
        self.cpu.mem_write(0x2000A0, bytes.fromhex("0037ffff"))

    def put(self, at, *values):
        self.cpu.mem_write(at, struct.pack(">" + "I" * len(values), *values))

    def call(self, address, *args):
        self.put(0x20F000, 0x20FF00, *args)
        self.cpu.reg_write(r.UC_M68K_REG_A7, 0x20F000)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.emu_start(address, 0x20FF00, count=10000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), 0x20FF00)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), 0x20F004)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def test_inverse_preserves_cancel_slot_and_recognizes_all_buffers(self):
        for slot, rank in (
            (901, 3),
            (19, 2),
            (555, 1),
            (300, 0),
            (0, 4),
            (1, 5),
            (127, 131),
            (128, 0),
            (1023, 127),
        ):
            with self.subTest(slot=slot):
                self.assertEqual(self.call(s.INVERSE, 0x200000, slot), rank)
                self.assertEqual(bytes(self.cpu.mem_read(0x2000A0, 2)), b"\x00\x37")
                bank = int.from_bytes(self.cpu.mem_read(0x2000A2, 2), "big")
                self.assertEqual(bank, 0 if slot in (901, 19, 555, 300) else slot)

    def test_forward_boundary_and_all_ordinary_slots(self):
        roots = bytes(self.cpu.mem_read(n.STATE, 256))
        for rank, slot in (
            (0, 300),
            (1, 555),
            (2, 19),
            (3, 901),
            (4, 0),
            (5, 1),
            (131, 127),
        ):
            self.assertEqual(self.call(s.FORWARD, 0, rank), slot)
        for bank in range(1, 8):
            for rank in (0, 1, 44, 127):
                self.assertEqual(
                    self.call(s.FORWARD, bank * 128, rank), bank * 128 + rank
                )
        for bad in (132, 1024, 0xFFFFFFFF):
            self.assertEqual(self.call(s.FORWARD, 0, bad), 0)
        self.assertEqual(bytes(self.cpu.mem_read(n.STATE, 256)), roots)

    def test_missing_setup_or_invalid_mapping_keeps_stock_ranks(self):
        for ready, invalid in ((0, None), (1, 0), (1, 1024), (1, 0xFFFFFFFF)):
            self.setUp()
            self.put(w.STATE + 64, ready)
            if invalid is not None:
                self.put(n.STATE + 40, invalid)
            self.assertEqual(self.call(s.FORWARD, 0, 4), 4)
            self.assertEqual(self.call(s.INVERSE, 0x200000, 7), 7)

    def test_wrong_firmware_is_rejected(self):
        image = bytearray(STOCK_MAIN.read_bytes())
        image[0x1E1BE - 0x400] ^= 1
        with self.assertRaisesRegex(ValueError, "OS1.16"):
            s.payload(image)

    def test_formatter_uses_native_function_context_and_empty_ready_labels(self):
        for at, size in ((0x40115000, 4096), (0x401E7000, 4096), (0x405B0000, 0x10000)):
            self.cpu.mem_map(at, size)
        # Explicit C++ boundaries only: return a supplied menu ID, then record
        # the constructor's source string pointer in its output object.
        self.cpu.mem_write(0x401154E0, bytes.fromhex("202f00044e75"))
        self.cpu.mem_write(0x401E7A64, bytes.fromhex("206f000420af00084e75"))
        self.put(0x200200, 0x200210)
        self.put(0x200210, 0x200000)
        self.cpu.mem_write(0x2000A2, bytes(2))
        for rank, slot in ((0, 300), (1, 555), (2, 19), (3, 901)):
            for ready in (False, True):
                self.put(0x405B1368 + slot * 16 + 8, 141 if ready else 0)
                self.cpu.reg_write(r.UC_M68K_REG_A0, 0x200400)
                self.assertEqual(self.call(s.FORMAT, 0x200200, rank), 0x200400)
                ptr = int.from_bytes(self.cpu.mem_read(0x200400, 4), "big")
                label = self.cpu.mem_read(ptr, 16).split(b"\0")[0].decode()
                self.assertEqual(
                    label, f"BUF {4 - rank} " + ("READY" if ready else "EMPTY")
                )

    def test_resolve_clears_the_stock_word_register_upper_half(self):
        self.cpu.reg_write(r.UC_M68K_REG_D0, 3)
        self.cpu.reg_write(r.UC_M68K_REG_D2, 0xDEAD0000)
        self.cpu.reg_write(r.UC_M68K_REG_A7, 0x20F000)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.emu_start(s.RESOLVE, 0x4001E1E6, count=10000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_D2), 901)

    def test_navigation_calls_native_callback_with_backing_slot(self):
        self.cpu.mem_map(0x4001E000, 4096)
        # Native selected-slot boundary returns the supplied actual slot. The
        # callback records its right-aligned native short argument.
        self.cpu.mem_write(0x4001E17A, bytes.fromhex("2039002006044e75"))
        self.put(0x2000C4, 0x200540)
        self.menu_boundaries()
        self.cpu.mem_write(0x200540, bytes.fromhex("202f000823c0002006004e75"))
        for original, delta, expected in (
            (0, -1, 901),
            (901, -1, 19),
            (300, -1, 300),
            (901, 1, 0),
            (0, 1, 1),
            (127, 99, 127),
            (127, 1, 127),
            (127, 999999, 127),
        ):
            self.put(0x200604, original)
            self.assertEqual(self.call(s.NAVIGATE, 0x200000, delta & 0xFFFFFFFF), 1)
            self.assertEqual(
                int.from_bytes(self.cpu.mem_read(0x200600, 4), "big"), expected
            )
        self.put(0x200600, 0xCAFEBABE)
        self.put(0x200604, 128)
        self.assertEqual(self.call(s.NAVIGATE, 0x200000, 0xFFFFFFFF), 0)
        self.assertEqual(
            int.from_bytes(self.cpu.mem_read(0x200600, 4), "big"), 0xCAFEBABE
        )

    def menu_boundaries(self):
        self.cpu.mem_write(
            s.BUILD_STOCK, bytes.fromhex("203900200920528023c0002009204e75")
        )
        self.cpu.mem_map(0x4011A000, 4096)
        self.cpu.mem_write(0x4011AE46, bytes.fromhex("4e75"))
        self.put(0x20004C, 0x200700)
        self.put(0x200720, 0x200800)
        self.cpu.mem_write(0x200800, bytes.fromhex("202f000823c0002008104e75"))

    def test_cursor_resynchronizes_native_menu_after_absolute_assignment(self):
        self.menu_boundaries()
        for slot, rank in (
            (901, 3),
            (19, 2),
            (555, 1),
            (300, 0),
            (0, 4),
            (1, 5),
            (128, 0),
        ):
            self.call(s.CURSOR, 0x200000, slot)
            self.assertEqual(
                int.from_bytes(self.cpu.mem_read(0x200810, 4), "big"), rank
            )
            self.assertEqual(bytes(self.cpu.mem_read(0x2000A0, 2)), b"\x00\x37")

    def test_opening_menu_preserves_current_sample_and_off_default(self):
        self.menu_boundaries()
        self.cpu.mem_map(0x4001E000, 4096)
        self.cpu.mem_map(0x40111000, 4096)
        # Native boundaries: backend setup and scaler are already covered
        # separately. Capture cursor rank/notify; detect any sample assignment.
        for at in (s.nb.INIT_BODY, s.BUILD_STOCK, 0x40111888, 0x4001E5D0):
            self.cpu.mem_write(at, bytes.fromhex("4e75"))
        self.put(0x200720, 0x200A00)
        self.cpu.mem_write(
            0x200A00,
            bytes.fromhex("202f000823c000200810202f000c23c0002008144e75"),
        )
        self.put(0x2000C4, 0x200540)
        self.cpu.mem_write(0x200540, bytes.fromhex("202f000823c0002006004e75"))
        roots = bytes(self.cpu.mem_read(n.STATE, 256))
        for slot, rank in ((0, 4), (7, 11), (128, 0), (901, 3)):
            with self.subTest(slot=slot):
                self.cpu.mem_write(0x2000A0, struct.pack(">HH", slot, slot))
                self.put(0x200600, 0xCAFEBABE)
                self.call(s.BUILD, 0x200000)
                self.assertEqual(
                    bytes(self.cpu.mem_read(0x200810, 8)), struct.pack(">II", rank, 0)
                )
                self.cpu.reg_write(r.UC_M68K_REG_A2, 0x200000)
                self.assertEqual(self.call(s.INITIAL), rank)
                self.assertEqual(
                    bytes(self.cpu.mem_read(0x2000A0, 2)), struct.pack(">H", slot)
                )
                self.assertEqual(
                    bytes(self.cpu.mem_read(0x200600, 4)), b"\xca\xfe\xba\xbe"
                )
                self.assertEqual(bytes(self.cpu.mem_read(n.STATE, 256)), roots)

    def test_late_backend_initialization_does_not_reinterpret_existing_rows(self):
        self.put(s.VIEW_ENABLED, 0)
        self.assertEqual(self.call(s.FORWARD, 0, 4), 4)
        self.assertEqual(self.call(s.INVERSE, 0x200000, 7), 7)
        self.put(s.VIEW_ENABLED, 1)
        self.assertEqual(self.call(s.FORWARD, 0, 4), 0)
        self.assertEqual(self.call(s.INVERSE, 0x200000, 7), 11)


    def test_disabled_view_does_not_consume_encoder_input(self):
        self.put(0x200000, 0x401EE4B8)
        self.put(s.VIEW_ENABLED, 0)
        self.assertEqual(self.call(s.ROTATE, 0x200004, 0x200900), 0)
        self.put(s.VIEW_ENABLED, 1)
        for slot in (1, 7, 127, 128, 255, 256, 511, 768, 1023):
            self.cpu.mem_write(0x2000A2, struct.pack(">H", slot))
            self.assertEqual(self.call(s.ROTATE, 0x200004, 0x200900), 0)

    def test_menu_rebuild_constructs_the_native_scaler_once(self):
        self.menu_boundaries()
        self.cpu.mem_map(0x40111000, 4096)
        self.cpu.mem_write(s.nb.INIT_BODY, bytes.fromhex("4e75"))
        self.cpu.mem_write(s.BUILD_STOCK, bytes.fromhex("4e75"))
        self.cpu.mem_write(
            0x40111888, bytes.fromhex("203900200900528023c0002009004e75")
        )
        self.cpu.mem_write(0x2000A2, bytes(2))
        for _ in range(4):
            self.call(s.BUILD, 0x200000)
        self.assertEqual(int.from_bytes(self.cpu.mem_read(0x200900, 4), "big"), 1)
        self.assertEqual(int.from_bytes(self.cpu.mem_read(s.SCALER_INIT, 4), "big"), 1)

    def test_cursor_rebuilds_rows_across_the_A_bank_boundary(self):
        self.menu_boundaries()
        self.cpu.mem_write(0x2000A2, struct.pack(">H", 127))
        self.call(s.CURSOR, 0x200000, 128)
        self.assertEqual(int.from_bytes(self.cpu.mem_read(0x200810, 4), "big"), 0)
        self.call(s.CURSOR, 0x200000, 127)
        self.assertEqual(int.from_bytes(self.cpu.mem_read(0x200810, 4), "big"), 131)
        self.assertEqual(int.from_bytes(self.cpu.mem_read(0x200920, 4), "big"), 2)
