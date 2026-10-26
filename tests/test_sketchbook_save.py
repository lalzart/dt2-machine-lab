"""Execute the emitted receiver against independently encoded wire packets."""

import os
import struct
import unittest

from selector_core_support import Core
from unicorn import m68k_const as r

from lab import sketchbook_save as s
from lab.coldfire import audit_code
from lab.emit import Code


@unittest.skipUnless(
    os.environ.get("DT2_BUF_SELECTOR_CORE"), "Requires explicit Rust ColdFire bridge"
)
class SketchbookSaveTests(unittest.TestCase):
    def test_declared_entries_are_not_silently_replaced(self):
        self.assertEqual(s.payload()[s.CLOSE], s.close())

    def setUp(self):
        self.cpu = Core()
        for at, size in (
            (s.t.BASE, 0x10000),
            (s.n.BASE, 0x8000),
            (s.w.BASE, 0xB000),
            (0x200000, 0x20000),
            (0x405A0000, 0x20000),
            (0x4011E000, 0x1000),
        ):
            self.cpu.mem_map(at, size)
        for at, size in (
            (s.q.BASE, 0x4000),
            (s.nb.BASE, 0x8000),
            (0x40199000, 0x1000),
            (0x40015000, 0x1000),
            (0x80004000, 0x1000),
            (0x44F37000, 0x1000),
            (0x47DB3000, 0x1000),
        ):
            self.cpu.mem_map(at, size)
        for at, raw in s.payload().items():
            audit_code(raw, at)
            self.cpu.mem_write(at, raw)
        self.dest = 0x201000
        self.put(s.STATE, 1, 5, 0x7FFB0003, 2, 17, 500, 0, self.dest, 0, 0)
        self.cpu.mem_write(self.dest, b"\xa5" * 4096)

    def put(self, at, *words):
        self.cpu.mem_write(
            at,
            struct.pack(">" + str(len(words)) + "I", *(v & 0xFFFFFFFF for v in words)),
        )

    def word(self, at):
        return struct.unpack(">I", self.cpu.mem_read(at, 4))[0]

    def call(self, at, *args, return_pc=0x21FF00):
        sp, ret = 0x21F000, return_pc
        self.put(sp, ret, *args)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(r.UC_M68K_REG_A7, sp)
        regs = [
            getattr(r, "UC_M68K_REG_" + name)
            for name in [
                "D2",
                "D3",
                "D4",
                "D5",
                "D6",
                "D7",
                "A2",
                "A3",
                "A4",
                "A5",
                "A6",
            ]
        ]
        for i, reg in enumerate(regs):
            self.cpu.reg_write(reg, 0x123000 + i * 4)
        self.cpu.emu_start(at, ret, count=200000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), sp + 4)
        for i, reg in enumerate(regs):
            self.assertEqual(self.cpu.reg_read(reg), 0x123000 + i * 4)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def receive(self, data, **overrides):
        args = dict(
            serial=5,
            epoch=2,
            token=0x7FFB0003,
            position=17,
            offset=self.word(s.STATE + s.RECEIVED),
            data=data,
        )
        args.update(overrides)
        raw = s.packet(**args)
        self.cpu.mem_write(s.RX + 0xABC, raw + bytes(260 - len(raw)))
        self.call(s.CONSUME)

    def test_ordered_packets_exact_and_duplicate_does_not_advance(self):
        data = bytes((i * 73 + 21) & 255 for i in range(500))
        self.receive(data[:224])
        self.assertEqual(self.word(s.STATE + s.RECEIVED), 224)
        self.receive(data[:224], offset=0)
        self.assertEqual(self.word(s.STATE + s.RECEIVED), 224)
        self.receive(data[224:448])
        self.receive(data[448:])
        self.assertEqual(self.word(s.STATE + s.PHASE), 2)
        self.assertEqual(self.cpu.mem_read(self.dest, 500), data)
        self.assertEqual(self.cpu.mem_read(self.dest + 500, 64), b"\xa5" * 64)

    def test_stale_envelope_and_zero_reply_cannot_write_or_complete(self):
        for field in ["serial", "epoch", "token", "position"]:
            with self.subTest(field=field):
                self.receive(b"\x55" * 224, **{field: 7})
                self.assertEqual(self.word(s.STATE + s.PHASE), 1)
                self.assertEqual(self.word(s.STATE + s.RECEIVED), 0)
        self.cpu.mem_write(s.RX + 0xABC, bytes(260))
        for _ in range(512):
            self.call(s.CONSUME)
        self.assertEqual(self.word(s.STATE + s.PHASE), 3)
        self.assertEqual(self.cpu.mem_read(self.dest, 500), b"\xa5" * 500)

    def test_close_ack_is_sequenced_and_required_before_lease_release(self):
        self.put(s.STATE + s.PHASE, 4)
        self.put(s.STATE + s.CANCEL, 1)
        self.receive(b"", status=2, serial=4)
        self.assertEqual(self.word(s.STATE + s.PHASE), 4)
        self.receive(b"", status=2)
        self.assertEqual(self.word(s.STATE + s.PHASE), 5)
        self.put(s.w.STATE + 12, 4)
        self.call(s.DONE, 0, 0)
        self.assertEqual(self.word(s.w.STATE + 12), 4)
        self.put(s.STATE + s.CLOSED, 1)
        self.call(s.DONE, 0, 0)
        self.assertEqual(self.word(s.w.STATE + 12), 0)

    def test_corrupt_reordered_status_and_oversize_refuse_before_copy(self):
        cases = ["corrupt", "reorder", "status", "oversize", "empty", "overrun"]
        for case in cases:
            with self.subTest(case=case):
                self.put(s.STATE + s.PHASE, 1)
                data = b"\x5a" * 224
                kw = {}
                if case == "reorder":
                    kw["offset"] = 224
                if case == "status":
                    kw["status"] = 1
                    data = b""
                if case == "oversize":
                    data = b"\x5a" * 225
                if case == "empty":
                    data = b""
                if case == "overrun":
                    self.put(s.STATE + s.COUNT, 100)
                raw = bytearray(
                    s.packet(
                        5,
                        2,
                        0x7FFB0003,
                        17,
                        kw.get("offset", 0),
                        data,
                        kw.get("status", 0),
                    )
                )
                if case == "corrupt":
                    raw[-1] ^= 1
                self.cpu.mem_write(s.RX + 0xABC, raw)
                self.call(s.CONSUME)
                self.assertEqual(self.word(s.STATE + s.PHASE), 3)
                self.assertEqual(self.word(s.STATE + s.RECEIVED), 0)
                self.assertEqual(self.cpu.mem_read(self.dest, 500), b"\xa5" * 500)

    def test_capture_keeps_only_metadata_and_original_retirement_runs(self):
        node, source = 0x203000, 0x204000
        token = 0x7FFB0003
        native = bytes((i * 31 + 7) & 255 for i in range(880))
        self.cpu.mem_write(source, native)
        self.put(node, 0, token, 0x98765433, 880, 9, source)
        self.put(s.n.STATE, 2)
        self.put(s.n.GEN, 1, token, 2)
        self.put(s.n.GEN + 36, 1021)
        self.put(0x405B5368 + 1021 * 4, 1)
        self.put(0x405A0F64, 0x205000)
        self.put(0x205000 + 52 + 16, 0x2400, 0x4000)
        self.cpu.mem_write(
            s.n.LOOKUP,
            bytes.fromhex("203c") + struct.pack(">I", s.n.GEN) + bytes.fromhex("4e75"),
        )
        self.cpu.mem_write(0x4011E8FC, bytes.fromhex("70004e75"))
        self.call(s.CAPTURE, node)
        self.assertEqual(self.word(node + 20), 0)
        self.assertEqual(self.word(s.META), 1)
        self.assertEqual(self.word(s.META + 4), token)
        self.assertEqual(self.word(s.META + 24), 1021)
        self.assertEqual(self.cpu.mem_read(s.META + 32, 64), native[:64])
        self.assertEqual(self.cpu.mem_read(s.META + 96, 16), native[-16:])
        self.assertEqual(self.word(s.META + 112), 0x2400)
        self.assertEqual(self.word(s.META + 116), 0x4000)

    def ready(self):
        token = 0x7FFB0003
        key = (token, 0x98765433, 880, 9)
        self.put(s.n.STATE, 2)
        self.put(s.n.GEN, 1, token, 2, 0, *key)
        self.put(s.n.GEN + 36, 300)
        self.put(s.META, 1, token, key[1], 880, 2, 0, 300)
        self.put(s.META + 120, 9)
        self.put(0x405B1368 + 1019 * 16, *key)
        for at, v in (
            (0x80004704, 0x11),
            (0x44F370A0, 0x12),
            (s.w.STATE + 68, 0x13),
            (s.q.CURRENT_TCB, 0x14),
        ):
            self.put(at, v)
        self.cpu.mem_write(
            s.n.LOOKUP,
            bytes.fromhex("203c") + struct.pack(">I", s.n.GEN) + bytes.fromhex("4e75"),
        )
        self.cpu.mem_write(0x4019988A, bytes.fromhex("70014e75"))
        self.cpu.mem_write(0x40015F6C, bytes.fromhex("70004e75"))

    def test_admission_pins_metadata_and_refusal_preserves_pending_save(self):
        self.ready()
        name = 0x206000
        self.cpu.mem_write(name, b"Frozen A\0")
        self.assertEqual(self.call(s.ADMIT, 1019, name), 0)
        self.assertEqual(self.word(s.w.STATE + 12), 4)
        self.assertEqual(self.word(s.STATE + s.CONTEXT), s.META)
        self.assertEqual(self.cpu.mem_read(s.PATH, 21), b"/Sketchbook/Frozen A\0")
        old = self.cpu.mem_read(s.STATE, 0x180)
        self.cpu.mem_write(name, b"Redirected\0")
        self.assertEqual(self.call(s.ADMIT, 1019, name), 0xFFFFFFFF)
        self.assertEqual(self.cpu.mem_read(s.STATE, 0x180), old)

    def test_invalid_names_or_stale_generation_cannot_claim_save(self):
        self.ready()
        name = 0x206000
        for data in (
            b"\0",
            b".hidden\0",
            b" space\0",
            b"bad/name\0",
            b"bad\\name\0",
            b"x" * 61 + b"\0",
            b"non\xff\0",
        ):
            self.cpu.mem_write(name, data)
            self.assertEqual(self.call(s.ADMIT, 1019, name), 0xFFFFFFFF)
            self.assertEqual(self.word(s.w.STATE + 12), 0)
        self.cpu.mem_write(name, b"Valid\0")
        self.put(s.META + 120, 10)
        self.assertEqual(self.call(s.ADMIT, 1019, name), 0xFFFFFFFF)
        self.assertEqual(self.word(s.w.STATE + 12), 0)

    def test_reader_exact_header_trailer_and_invalid_range(self):
        self.ready()
        name = 0x206000
        self.cpu.mem_write(name, b"Take\0")
        self.assertEqual(self.call(s.ADMIT, 1019, name), 0)
        self.put(s.STATE + s.JOB, 2, 0, 0x14)
        header = bytes(range(64))
        footer = bytes(range(240, 256))
        self.cpu.mem_write(s.META + 32, header)
        self.cpu.mem_write(s.META + 96, footer)
        for pos, count, expected in (
            (0, 64, header),
            (3, 23, header[3:26]),
            (864, 16, footer),
            (867, 10, footer[3:13]),
        ):
            self.assertEqual(self.call(s.READ, s.META, self.dest, count, pos), count)
            self.assertEqual(self.cpu.mem_read(self.dest, count), expected)
        for count, pos in (
            (4097, 0),
            (1, 880),
            (20, 870),
            (0xFFFFFFFF, 0),
            (10, 0xFFFFFFF0),
        ):
            self.assertEqual(
                self.call(s.READ, s.META, self.dest, count, pos), 0xFFFFFFFF
            )
        self.put(s.n.STATE, 3)
        self.assertEqual(self.call(s.READ, s.META, self.dest, 16, 0), 0xFFFFFFFF)

    def test_sender_exact_request_and_nonwrapping_serial(self):
        self.cpu.mem_map(0x400CD000, 0x1000)
        self.cpu.mem_write(0x400CD638, bytes.fromhex("70004e75"))
        self.put(s.STATE + s.CONTEXT, s.META)
        self.put(s.META + 24, 300)
        self.put(s.META + 36, 800, 48000)
        self.cpu.mem_write(s.META + 33, b"\x01")
        self.put(s.META + 112, 0x2400, 0x4000)
        self.assertEqual(self.call(s.SEND), 0)
        q = struct.unpack(">16I", self.cpu.mem_read(s.PACKET, 64))
        self.assertEqual(
            q,
            (
                0x534B5231,
                1,
                2,
                0x7FFB0003,
                6,
                300,
                0x2400,
                0x4000,
                400,
                48000,
                1,
                17,
                500,
                0xFFFFFFF9,
                0,
                0x534B4342,
            ),
        )
        self.assertEqual(self.cpu.mem_read(s.PACKET + 64, 4032), bytes(4032))
        self.put(s.STATE + s.SERIAL, 0xFFFFFFFF)
        self.assertEqual(self.call(s.SEND), 0xFFFFFFFF)
        self.assertEqual(self.word(s.STATE + s.SERIAL), 0xFFFFFFFF)

    def test_driver_uses_extended_destination_and_preserves_stock_prefix(self):
        self.cpu.mem_map(0x80000000, 0x4000)
        self.cpu.mem_map(0x80005000, 0x2000)
        self.cpu.mem_map(0x40136000, 0x1000)
        self.cpu.mem_map(0x42948000, 0x1000)
        c = Code()
        for i in range(4):
            c.emit(f"202f{4 + i * 4:04x}")
            c.imm("23c0", s.STATE + 0x380 + i * 4)
        c.emit("702a4e75")
        self.cpu.mem_write(s.OLD_DRIVER, c.finish(s.OLD_DRIVER))
        c = Code()
        c.emit("206f0004 226f0008 202f000c")
        c.label("copy")
        c.emit("10d9")
        c.imm("0680", -1)
        c.branch(6, "copy")
        c.emit("4e75")
        self.cpu.mem_write(0x401360AC, c.finish(0x401360AC))
        self.put(s.STATE + s.PHASE, 0)
        data = bytes((i * 71 + 19) & 255 for i in range(3008))
        self.cpu.mem_write(s.RX, data)
        self.cpu.mem_write(0x8000488C, b"\xa5" * 0xABC + b"canary")
        self.assertEqual(self.call(s.DRIVER, 0x802, 0x80005348, 0xABC, 0x8000488C), 42)
        self.assertEqual(
            struct.unpack(">4I", self.cpu.mem_read(s.STATE + 0x380, 16)),
            (0x802, 0x80005348, 3008, s.RX),
        )
        self.assertEqual(
            self.cpu.mem_read(0x8000488C, 0xABC + 6), data[:0xABC] + b"canary"
        )
        self.assertEqual(self.word(0x42948B08), 3008)

    def test_placed_capture_and_admission_use_relocated_generation_base(self):
        from lab.sketch_device import ARENAS, relocate, relocate_code

        lo = (ARENAS[0].destination - 0x100) & ~4095
        hi = (ARENAS[-1].destination + ARENAS[-1].size + 0x200 + 4095) & ~4095
        self.cpu.mem_map(lo, hi - lo)
        for at, raw in s.payload().items():
            self.cpu.mem_write(relocate(at), relocate_code(raw, at)[0])
        self.cpu.mem_write(
            relocate(s.n.LOOKUP),
            bytes.fromhex("203c")
            + struct.pack(">I", relocate(s.n.GEN))
            + bytes.fromhex("4e75"),
        )
        node, source = 0x203000, 0x204000
        token = 0x7FFB0003
        key = (token, 0x98765433, 880, 9)
        native = bytes((i * 31 + 7) & 255 for i in range(880))
        self.cpu.mem_write(source, native)
        self.put(node, 0, *key, source)
        self.put(relocate(s.n.STATE), 2)
        self.put(relocate(s.n.GEN), 1, token, 2, 0, *key)
        self.put(relocate(s.n.GEN) + 36, 300)
        self.put(0x405B5368 + 300 * 4, 1)
        self.put(0x405A0F64, 0x205000)
        self.put(0x205000 + 52 + 16, 0x2400, 0x4000)
        self.cpu.mem_write(0x4011E8FC, bytes.fromhex("70004e75"))
        self.call(relocate(s.CAPTURE), node)
        self.assertEqual(self.word(relocate(s.META)), 1)
        self.assertEqual(self.cpu.mem_read(relocate(s.META) + 32, 64), native[:64])
        self.assertEqual(self.word(node + 20), 0)
        self.put(0x405B1368 + 1019 * 16, *key)
        for at, v in (
            (0x80004704, 0x11),
            (0x44F370A0, 0x12),
            (relocate(s.w.STATE) + 68, 0x13),
        ):
            self.put(at, v)
        self.cpu.mem_write(0x4019988A, bytes.fromhex("70014e75"))
        self.cpu.mem_write(0x40015F6C, bytes.fromhex("70004e75"))
        name = 0x206000
        self.cpu.mem_write(name, b"Placed\0")
        self.assertEqual(self.call(relocate(s.ADMIT), 1019, name), 0)
        self.assertEqual(self.word(relocate(s.STATE) + s.CONTEXT), relocate(s.META))

    def ui(self):
        from lab import sketchbook_preview as p
        from lab import sketchbook_ui as u

        for at, raw in (p.payload() | u.payload()[0]).items():
            audit_code(raw, at)
            self.cpu.mem_write(at, raw)
        return p, u

    def test_sketchbook_rows_skip_quarantined_freezes_and_resolve_original_take(self):
        from lab import recorder_seat_reuse as seats

        self.ready()
        _p, u = self.ui()
        self.cpu.mem_write(s.n.LOOKUP, seats.lookup())
        self.assertEqual(self.call(u.COUNT), 4)
        self.put(s.n.SNAP, 3, 0x7FFC0001, 2)
        self.put(s.n.SNAP + 64, 1, 0x7FFC0002, 2)
        self.put(s.n.SNAP + 64 + 36, 1019)
        self.assertEqual(self.call(u.COUNT), 5)
        self.assertEqual(self.call(u.TARGET, 4), s.META)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_D1), 1019)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A0), 0x7FFB0003)
        self.assertEqual(self.call(u.TARGET, 0), 0)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_D1), 1020)
        self.assertEqual(self.call(u.TARGET, 5), 0)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_D1), 0xFFFFFFFF)

    def test_song_list_navigation_and_back_release_keep_parent_view(self):
        from lab import sketch as sketch

        _p, u = self.ui()
        self.cpu.mem_map(sketch.BASE, 0x8000)
        self.cpu.mem_map(0x40139000, 0x1000)
        self.cpu.mem_write(0x40139AE6, bytes.fromhex("4e75"))
        view, event = 0x207000, 0x207800
        self.put(sketch.STATE + sketch.VIEW, view)

        def key(number, flags=1, owner=view):
            self.put(event + 12, number, flags)
            return self.call(u.KEY, owner, event)

        self.assertEqual(key(14, owner=view + 4), 0)
        self.assertEqual(self.word(u.STATE + u.MODE), 0)
        self.assertEqual(key(13), 0)  # Physical LEFT must not open Sketchbook.
        self.assertEqual(key(14), 1)  # Physical DOWN, from the stock name table.
        self.assertEqual(self.word(u.STATE + u.MODE), 1)
        self.assertEqual(key(13), 1)
        self.assertEqual(self.word(u.STATE + u.MODE), 0)
        self.assertEqual(key(13, flags=0x10), 1)
        self.assertEqual(key(14), 1)
        self.assertEqual(key(12, flags=0), 1)  # Foreign naming-dialog release.
        self.assertEqual(self.word(u.STATE + u.MODE), 1)
        self.assertEqual(key(11), 1)
        self.assertEqual(self.word(u.STATE + u.ROW), 0)
        for _ in range(12):
            self.assertEqual(key(14), 1)
        self.assertEqual(self.word(u.STATE + u.ROW), 3)
        self.assertEqual(key(12), 1)
        self.assertEqual(self.word(u.STATE + u.MODE), 0)
        self.assertEqual(key(12, flags=0), 1)
        self.assertEqual(self.word(sketch.STATE + sketch.VIEW), view)
        self.assertEqual(key(12), 0)  # A new NO belongs to the parent Sketch.
        self.assertEqual(key(24), 0)  # SONG retains its original gesture owner.

    def test_physical_navigation_names_are_guarded_by_original_firmware(self):
        from lab.dt2_116 import BASE, PANEL_BUTTON_NAMES, verify_navigation_names
        from lab.runtime import STOCK_MAIN

        stock = bytearray(STOCK_MAIN.read_bytes())
        verify_navigation_names(stock)
        at = PANEL_BUTTON_NAMES - BASE + 13 * 4
        stock[at:at + 8] = stock[at + 4:at + 8] + stock[at:at + 4]
        with self.assertRaisesRegex(ValueError, "physical button map drift"):
            verify_navigation_names(stock)

    def test_song_list_data_encoder_is_scoped_and_cannot_edit_recorder_knobs(self):
        _p, u = self.ui()
        self.cpu.mem_map(0x4011A000, 0x1000)
        self.cpu.mem_write(0x4011AE46, bytes.fromhex("4e75"))
        event = 0x207800
        self.put(event + 12, 9, 1)
        self.assertEqual(self.call(u.ROTATE, 0x207000, event), 0)
        self.put(u.STATE + u.MODE, 1)
        for _ in range(12):
            self.assertEqual(self.call(u.ROTATE, 0x207000, event), 1)
        self.assertEqual(self.word(u.STATE + u.ROW), 3)
        self.put(event + 16, 0xFFFFFFFF)
        self.call(u.ROTATE, 0x207000, event)
        self.assertEqual(self.word(u.STATE + u.ROW), 2)
        self.put(event + 12, 1, 1)  # Encoder A must not change the recorder BUF.
        self.assertEqual(self.call(u.ROTATE, 0x207000, event), 1)
        self.assertEqual(self.word(u.STATE + u.ROW), 2)

    def test_song_save_opens_name_once_on_paired_yes_release(self):
        from lab import sketch as sketch

        self.ready()
        _p, u = self.ui()
        self.cpu.mem_map(sketch.BASE, 0x8000)
        view, event = 0x207000, 0x207800
        self.put(sketch.STATE + sketch.VIEW, view)
        self.put(u.STATE + u.MODE, 1, 4)
        self.put(s.n.SNAP, 1, 0x7FFC0001, 2)
        self.put(s.n.SNAP + 36, 1019)
        c = Code()
        for off, arg in ((0x30, 4), (0x34, 8)):
            c.emit(f"202f{arg:04x}")
            c.imm("23c0", u.STATE + off)
        c.emit("70004e75")
        self.cpu.mem_write(u.OPEN_NAME, c.finish(u.OPEN_NAME))
        self.put(event + 12, 10, 0)
        self.assertEqual(self.call(u.KEY, view, event), 0)
        self.assertEqual(self.word(u.STATE + 0x30), 0)
        self.put(event + 16, 1)
        self.assertEqual(self.call(u.KEY, view, event), 1)
        self.assertEqual(self.word(u.STATE + 0x30), 0)
        self.put(event + 16, 0)
        self.assertEqual(self.call(u.KEY, view, event), 2)
        self.assertEqual(self.word(u.STATE + 0x30), s.META)
        self.assertEqual(self.word(u.STATE + 0x34), 0x7FFB0003)
        self.assertEqual(self.call(u.KEY, view, event), 0)

    def test_preview_resource_has_exact_bytes_and_frees_only_at_stock_close(self):
        p, _u = self.ui()
        token = 0x7FFB0003
        native = bytes((i * 31 + 7) & 255 for i in range(880))
        source, handle = 0x204000, 0x206000
        self.cpu.mem_write(source, native)
        self.put(p.NODE, 0, token, 0x98765433, 880, 9, source)
        self.put(p.STATE, source, 0)
        c = Code()
        c.emit("202f0004")
        c.imm("23c0", s.STATE + 0x3F0)
        c.emit("70004e75")
        self.cpu.mem_write(0x4011E8FC, c.finish(0x4011E8FC))
        self.assertEqual(self.call(p.OPEN, p.NODE + 4, handle, return_pc=0x40153E8A), 0)
        self.assertEqual(self.call(p.SIZE, token), 880)
        self.assertEqual(
            self.call(p.READ, self.dest, 500, handle, return_pc=0x40153ED4), 500
        )
        self.assertEqual(self.cpu.mem_read(self.dest, 500), native[:500])
        self.assertEqual(self.word(p.STATE), source)
        self.assertEqual(
            self.call(p.READ, self.dest, 500, handle, return_pc=0x40153D7E), 380
        )
        self.assertEqual(self.cpu.mem_read(self.dest, 380), native[500:])
        self.assertEqual(self.call(p.CLOSE, handle), 0)
        self.assertEqual(self.word(s.STATE + 0x3F0), source)
        self.assertEqual(self.word(p.STATE), 0)
        self.assertEqual(self.word(handle), 0xFFFFFFFF)

    def test_preview_snapshot_chunks_use_bounded_reader_and_own_the_result(self):
        # Explicit service fixtures for heap/read/close; the coupled probe
        # supplies the real DSP bytes and stock preview/filesystem services.
        self.ready()
        p, _u = self.ui()
        size = 9000
        key = (0x7FFB0003, 0x98765433, size, 9)
        self.put(s.META + 12, size)
        self.put(s.n.GEN + 24, size)
        self.put(0x405B1368 + 1019 * 16, *key)
        name = 0x206000
        self.cpu.mem_write(name, b"PREVIEW\0")
        self.assertEqual(self.call(s.ADMIT, 1019, name), 0)
        source, destination = 0x204000, 0x208000
        native = bytes((i * 73 + 19) & 255 for i in range(size))
        self.cpu.mem_write(source, native)
        self.cpu.mem_write(destination, b"\xa5" * (size + 64))
        self.cpu.mem_write(
            0x4011E8F0,
            bytes.fromhex("203c")
            + struct.pack(">I", destination)
            + bytes.fromhex("4e75"),
        )
        c = Code()
        c.imm("41f9", source)
        c.emit("202f0010 d1c0 226f0008 202f000c")
        c.label("copy")
        c.emit("12d8")
        c.imm("0680", -1)
        c.branch(6, "copy")
        c.emit("202f000c 4e75")
        self.cpu.mem_write(s.READ, c.finish(s.READ))
        c = Code()
        c.emit("7001")
        s.store(c, s.CLOSED)
        c.emit("70004e75")
        self.cpu.mem_write(s.CLOSE, c.finish(s.CLOSE))
        self.assertEqual(self.call(p.WORKER), 0)
        self.assertEqual(self.cpu.mem_read(destination, size), native)
        self.assertEqual(self.cpu.mem_read(destination + size, 64), b"\xa5" * 64)
        self.assertEqual(self.word(p.STATE), destination)
        self.assertEqual(self.word(p.NODE + 20), destination)
        self.assertEqual(self.cpu.mem_read(p.NODE + 4, 16), struct.pack(">4I", *key))

    def test_preview_null_and_unrelated_handles_forward_to_original_dispatch(self):
        p, _u = self.ui()
        self.put(p.STATE, 0x204000, 1)
        self.put(p.NODE + 4, 0x7FFB0003)
        for op, pc, args in [
            ("open", p.OPEN, (0, 0x206000)),
            ("read", p.READ, (self.dest, 16, 0)),
            ("size", p.SIZE, (10,)),
            ("close", p.CLOSE, (0,)),
        ]:
            at = s.w.DISPATCH + list(s.n.RESOURCE_SITES).index(op) * 256
            self.cpu.mem_write(at, bytes.fromhex("702a4e75"))
            self.assertEqual(self.call(pc, *args), 42)

    def test_filename_callback_refuses_a_reused_metadata_seat(self):
        self.ready()
        _p, u = self.ui()
        closure, string, name = 0x205000, 0x205100, 0x205200
        self.put(closure, s.META, 0x7FFB0003)
        self.put(string, name)
        self.cpu.mem_write(name, b"Take\0")
        self.put(s.META + 4, 0x7FFB0004)
        self.cpu.mem_write(u.MESSAGE, bytes.fromhex("70014e75"))
        self.assertEqual(self.call(u.CALLBACK, closure, string), 1)
        self.assertEqual(self.word(s.w.STATE + 12), 0)

    def test_global_stop_cancels_preview_and_keeps_stock_event_delivery(self):
        p, _u = self.ui()
        event = 0x206000
        self.cpu.mem_write(p.OLD_ROUTE, bytes.fromhex("702a4e75"))
        self.put(event, 0, 0, 0, 21, 1)
        self.put(s.STATE + s.KIND, 1)
        self.put(s.STATE + s.JOB, 2)
        self.assertEqual(self.call(p.CANCEL_KEY, 0x1234, event), 42)
        self.assertEqual(self.word(s.STATE + s.CANCEL), 0)
        self.put(s.STATE + s.KIND, 2)
        self.assertEqual(self.call(p.CANCEL_KEY, 0x1234, event), 42)
        self.assertEqual(self.word(s.STATE + s.CANCEL), 1)
        self.put(s.STATE + s.CLOSED, 1)
        self.put(s.w.STATE + 12, 4)
        self.call(p.DONE, 0, 0)
        self.assertEqual(self.word(s.STATE + s.RESULT), 0xFFFFFFFF)
        self.assertEqual(self.word(s.w.STATE + 12), 0)


if __name__ == "__main__":
    unittest.main()
