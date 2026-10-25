"""Execute native bank transactions with injected storage/loader failures.

File I/O, stock loader and refresh are boundary peers. Capture, bank search,
identity guards, filename preparation, rollback and publication run in guest.
"""

import struct
import unittest

from lab import flex_bank as bank
from lab import flex_native_save as named
from lab.flex_native import resource_lookup

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None

CODE, STOP, STACK = 0x100000, 0x10F000, 0x20F000
HEAD, NODE, KIT, POOL, FLOW, VIEW, TEXT = (
    0x300000,
    0x300100,
    0x306000,
    0x320000,
    0x350000,
    0x351000,
    0x352000,
)
VALID, FIND, COMMIT, LOOKUP, PREPARE, PROMOTE, BEGIN, CAPTURE, ACTIVE, KEYS = (
    CODE + i * 0x1000 for i in range(10)
)
GET_POOL, SAVE, RETIRE, OPEN_NAME, MESSAGE = (
    CODE + 0xB000 + i * 0x100 for i in range(5)
)


@unittest.skipIf(u is None, "Configured ColdFire runtime required")
class FlexBankTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for base, size in (
            (CODE, 0x10000),
            (0x200000, 0x10000),
            (0x300000, 0x100000),
            (0x40000000, 0x200000),
            (0x405B0000, 0x10000),
            (0x80004000, 0x1000),
        ):
            self.cpu.mem_map(base, size)
        self.original = struct.pack(">4I", 0x7FFE0001, 7, 1080, 55)
        self.durable = struct.pack(">4I", 23, 7, 1080, 78)
        self.other = struct.pack(">4I", 24, 99, 2160, 79)
        self.cpu.mem_write(NODE + 4, self.original)
        self.write(NODE + 20, 0x380000)
        self.write(HEAD, NODE)
        self.write(bank.LIVE_KIT, KIT)
        self.cpu.mem_write(POOL, b"\xff" * 0x4000)
        self.cpu.mem_write(bank.LOADED, b"\xff" * 0x4000)
        self.current_pool, self.selected, self.calls = POOL, 8, []
        self.fail_load = self.fail_save = False
        self.after_load = self.after_save = None
        self.setup_assignment()
        self.cpu.mem_write(VALID, bank.validate(VALID, GET_POOL, LOOKUP))
        self.cpu.mem_write(FIND, bank.find_slot(FIND))
        self.cpu.mem_write(
            COMMIT, bank.commit(COMMIT, VALID, FIND, PREPARE, PROMOTE, pool=GET_POOL)
        )
        self.cpu.mem_write(LOOKUP, resource_lookup(LOOKUP, HEAD))
        self.cpu.mem_write(
            PREPARE,
            named.write_named(
                PREPARE, GET_POOL, SAVE, 0, TEXT + 0x100, prepare_only=True
            ),
        )
        self.cpu.mem_write(PROMOTE, named.promote(PROMOTE, retire=RETIRE))
        self.cpu.mem_write(
            BEGIN, bank.begin(BEGIN, FLOW, VALID, OPEN_NAME, MESSAGE, 123)
        )
        self.cpu.mem_write(CAPTURE, bank.capture_name(CAPTURE, FLOW, VALID))
        self.cpu.mem_write(ACTIVE, bank.active(ACTIVE, FLOW, VALID))
        self.cpu.mem_write(
            KEYS,
            bank.keys(
                KEYS,
                FLOW,
                ACTIVE,
                COMMIT,
                MESSAGE,
                dict(bank_success=1, bank_full_message=2, bank_failure=3),
                TEXT + 0x200,
            ),
        )

        def service(cpu, pc, *_):
            sp = cpu.reg_read(r.UC_M68K_REG_A7)
            result = 0
            if pc == GET_POOL:
                result = self.current_pool
            elif pc == 0x4004ABE8:
                result = self.selected
            elif pc == 0x40154540:
                ref, slot = self.read(sp + 4), self.read(sp + 8)
                self.assertEqual(bytes(cpu.mem_read(ref, 16)), self.original)
                self.assertEqual(self.read(POOL + slot * 16), 0xFFFFFFFF)
                self.calls.append(("load", slot))
                cpu.mem_write(bank.LOADED + slot * 16, self.original)
                self.write(bank.LENGTHS + slot * 4, 1080)
                if self.after_load:
                    self.after_load(slot)
                result = 0xFFFFFFFF if self.fail_load else 0
            elif pc == SAVE:
                node, path, ref = (self.read(sp + n) for n in (4, 8, 12))
                self.assertEqual(node, NODE)
                self.calls.append(
                    ("write", bytes(cpu.mem_read(path, 72)).split(b"\0")[0])
                )
                if self.after_save:
                    self.after_save()
                if self.fail_save:
                    result = 0xFFFFFFFF
                else:
                    cpu.mem_write(ref, self.durable)
            elif pc == 0x40153BEA:
                slot = self.read(sp + 4)
                self.calls.append(("unload", slot))
                cpu.mem_write(
                    bank.LOADED + slot * 16, struct.pack(">4I", 0xFFFFFFFF, 0, 0, 0)
                )
                self.write(bank.LENGTHS + slot * 4, 0)
            elif pc == 0x4002D438:
                self.calls.append(("refresh", self.read(sp + 8)))
            elif pc == RETIRE:
                self.calls.append(("retire", self.read(sp + 4)))
                self.assertEqual(self.read(NODE + 28), 1)
                self.write(NODE + 20, 0)
            elif pc == OPEN_NAME:
                self.calls.append(("name", self.read(sp + 4), self.read(sp + 8)))
            elif pc == MESSAGE:
                self.calls.append(("message", self.read(sp + 4)))
            cpu.reg_write(r.UC_M68K_REG_D0, result)
            cpu.reg_write(r.UC_M68K_REG_PC, self.read(sp))
            cpu.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for pc in (
            GET_POOL,
            SAVE,
            RETIRE,
            OPEN_NAME,
            MESSAGE,
            0x4004ABE8,
            0x40154540,
            0x401540C6,
            0x40153BEA,
            0x4002D438,
            0x40157192,
        ):
            self.cpu.hook_add(u.UC_HOOK_CODE, service, begin=pc, end=pc)

    def setup_assignment(self, slot=9, track=8, machine=2):
        self.cpu.mem_write(KIT + track * 0x450 + 0x80, struct.pack(">H", slot))
        self.cpu.mem_write(KIT + track * 0x450 + 0xD6, bytes([machine]))
        self.cpu.mem_write(POOL + slot * 16, self.original)
        self.cpu.mem_write(bank.LOADED + slot * 16, self.original)
        self.write(bank.LENGTHS + slot * 4, 1080)
        self.cpu.mem_write(
            FLOW, struct.pack(">7I", NODE, POOL, KIT, track, slot, slot >> 7, 1)
        )
        self.cpu.mem_write(FLOW + bank.NAME, b"Organized take\0")

    def write(self, address, value):
        self.cpu.mem_write(address, struct.pack(">I", value))

    def read(self, address):
        return int.from_bytes(self.cpu.mem_read(address, 4), "big")

    def call(self, pc, *args):
        self.cpu.mem_write(STACK, struct.pack(">" + "I" * (len(args) + 1), STOP, *args))
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2500)
        self.cpu.reg_write(r.UC_M68K_REG_A7, STACK)
        regs = [
            getattr(r, f"UC_M68K_REG_{kind}{i}")
            for kind, first, end in (("D", 2, 8), ("A", 2, 7))
            for i in range(first, end)
        ]
        for reg in regs:
            self.cpu.reg_write(reg, 0xBAD000 + reg)
        self.cpu.emu_start(pc, STOP, count=200000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), STOP)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), STACK + 4)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_SR) & 0xFF00, 0x2500)
        for reg in regs:
            self.assertEqual(self.cpu.reg_read(reg), 0xBAD000 + reg)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def contents(self):
        return tuple(
            bytes(self.cpu.mem_read(a, n))
            for a, n in ((KIT, 16 * 0x450), (POOL, 0x4000), (NODE, 64))
        )

    def event(self, key, flags=16):
        self.cpu.mem_write(TEXT, bytes(12) + struct.pack(">2I", key, flags))
        return self.call(KEYS, VIEW, TEXT)

    def test_all_banks_skip_reserved_and_occupied_loader_or_project_slots(self):
        for index in range(1, 8):
            start = index * 128 + 1
            self.write(FLOW + bank.BANK, index)
            self.cpu.mem_write(POOL + start * 16, self.other)
            self.cpu.mem_write(bank.LOADED + (start + 1) * 16, self.other)
            self.write(bank.LENGTHS + (start + 2) * 4, 1080)
            self.assertEqual(self.call(FIND, FLOW), start + 3)
            self.cpu.mem_write(POOL + start * 16, b"\xff" * (127 * 16))
        self.write(FLOW + bank.BANK, 8)
        self.assertEqual(self.call(FIND, FLOW), 0xFFFFFFFF)

    def test_cross_bank_save_preserves_old_aliases_and_changes_only_captured_slot(self):
        self.write(FLOW + bank.BANK, 3)
        self.cpu.mem_write(POOL + 25 * 16, self.original)
        self.cpu.mem_write(KIT + 2 * 0x450 + 0x80, struct.pack(">H", 9))
        before = bytes(self.cpu.mem_read(KIT, 16 * 0x450))
        self.assertEqual(self.call(COMMIT, FLOW), 385)
        expected = bytearray(before)
        expected[8 * 0x450 + 0x80 : 8 * 0x450 + 0x82] = struct.pack(">H", 385)
        self.assertEqual(bytes(self.cpu.mem_read(KIT, len(before))), expected)
        for slot in (9, 25, 385):
            self.assertEqual(
                bytes(self.cpu.mem_read(POOL + slot * 16, 16)), self.durable
            )
        self.assertEqual(
            bytes(self.cpu.mem_read(bank.LOADED + 9 * 16, 16)), self.original
        )
        self.assertEqual(
            self.calls,
            [
                ("load", 385),
                ("write", b"/recorded/Organized take"),
                ("refresh", 8),
                ("retire", NODE),
            ],
        )
        self.assertEqual(self.read(FLOW + bank.PHASE), 0)

    def test_same_bank_keeps_original_slot_even_if_bank_is_full(self):
        for slot in range(1, 128):
            if slot != 9:
                self.cpu.mem_write(POOL + slot * 16, self.other)
        self.assertEqual(self.call(COMMIT, FLOW), 9)
        self.assertFalse(any(call[0] == "load" for call in self.calls))

    def test_full_target_bank_never_loads_writes_or_changes_take(self):
        self.write(FLOW + bank.BANK, 7)
        for slot in range(897, 1024):
            self.cpu.mem_write(POOL + slot * 16, self.other)
        before = self.contents()
        self.assertEqual(self.call(COMMIT, FLOW), 0xFFFFFFFE)
        self.assertEqual(self.contents(), before)
        self.assertEqual(self.calls, [])

    def test_last_slot_in_bank_h_is_usable_without_crossing_table_end(self):
        self.write(FLOW + bank.BANK, 7)
        for slot in range(897, 1023):
            self.cpu.mem_write(POOL + slot * 16, self.other)
        self.assertEqual(self.call(FIND, FLOW), 1023)
        self.assertEqual(self.call(COMMIT, FLOW), 1023)

    def test_invalid_name_rolls_back_before_any_file_or_project_write(self):
        self.write(FLOW + bank.BANK, 3)
        self.cpu.mem_write(FLOW + bank.NAME, b"invalid/name\0")
        before = self.contents()
        self.assertEqual(self.call(COMMIT, FLOW), 0xFFFFFFFF)
        self.assertEqual(self.contents(), before)
        self.assertEqual(self.calls, [("load", 385), ("unload", 385)])

    def test_loader_and_write_failures_rollback_candidate_only(self):
        for failure in ("fail_load", "fail_save"):
            with self.subTest(failure=failure):
                self.write(FLOW + bank.BANK, 2)
                setattr(self, failure, True)
                before = self.contents()
                self.assertEqual(self.call(COMMIT, FLOW), 0xFFFFFFFF)
                self.assertEqual(self.contents(), before)
                self.assertEqual(self.read(bank.LOADED + 257 * 16), 0xFFFFFFFF)
                self.assertIn(("unload", 257), self.calls)
                self.assertFalse(
                    any(call[0] in ("retire", "refresh") for call in self.calls)
                )
                setattr(self, failure, False)
                self.calls.clear()
        self.assertEqual(self.call(COMMIT, FLOW), 257)

    def test_reentrant_destination_occupation_is_preserved(self):
        self.write(FLOW + bank.BANK, 1)
        self.after_save = lambda: self.cpu.mem_write(POOL + 129 * 16, self.other)
        before = bytes(self.cpu.mem_read(KIT, 16 * 0x450))
        self.assertEqual(self.call(COMMIT, FLOW), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(POOL + 129 * 16, 16)), self.other)
        self.assertEqual(bytes(self.cpu.mem_read(KIT, len(before))), before)
        self.assertEqual(self.read(NODE + 28), 0)
        self.assertNotIn(("unload", 129), self.calls)

    def test_unready_candidate_never_replaces_a_playable_assignment(self):
        self.write(FLOW + bank.BANK, 3)
        for phase in ("load", "save"):
            with self.subTest(phase=phase):
                self.after_load = (
                    (lambda slot: self.write(bank.LENGTHS + slot * 4, 0))
                    if phase == "load"
                    else None
                )
                self.after_save = (
                    (lambda: self.write(bank.LENGTHS + 385 * 4, 0))
                    if phase == "save"
                    else None
                )
                before = self.contents()
                self.assertEqual(self.call(COMMIT, FLOW), 0xFFFFFFFF)
                self.assertEqual(self.contents(), before)
                self.assertEqual(self.read(bank.LENGTHS + 385 * 4), 0)
                self.assertNotIn(("refresh", 8), self.calls)
                self.assertNotIn(("retire", NODE), self.calls)
                if phase == "load":
                    self.assertEqual(self.calls, [("load", 385), ("unload", 385)])
                self.calls.clear()

    def test_reentrant_project_change_never_unloads_replacement_project(self):
        self.write(FLOW + bank.BANK, 1)
        self.after_load = lambda slot: setattr(self, "current_pool", POOL + 0x4000)
        before = self.contents()
        self.assertEqual(self.call(COMMIT, FLOW), 0xFFFFFFFF)
        self.assertEqual(self.contents(), before)
        self.assertEqual(self.calls, [("load", 129)])

    def test_exact_identity_machine_and_capture_guards(self):
        for address in (
            POOL + 9 * 16 + 4,
            bank.LOADED + 9 * 16 + 12,
            NODE + 28,
            NODE + 56,
            FLOW + bank.TRACK,
            FLOW + bank.KIT,
        ):
            old = self.read(address)
            self.write(address, old + 1)
            before = self.contents()
            self.assertEqual(self.call(COMMIT, FLOW), 0xFFFFFFFF)
            self.assertEqual(self.contents(), before)
            self.assertEqual(self.calls, [])
            self.write(address, old)
        self.current_pool = POOL + 16
        self.assertEqual(self.call(COMMIT, FLOW), 0xFFFFFFFF)
        self.current_pool = POOL
        for machine in (5, 7, 255):
            self.cpu.mem_write(KIT + 8 * 0x450 + 0xD6, bytes([machine]))
            self.assertEqual(self.call(COMMIT, FLOW), 0xFFFFFFFF)

    def test_begin_captures_all_tracks_and_sample_engines(self):
        for track in range(16):
            for machine in (0, 1, 2, 3, 4, 6):
                self.setup_assignment(slot=897 + track, track=track, machine=machine)
                self.selected = track
                self.assertEqual(self.call(BEGIN, NODE, POOL, VIEW), 0)
                self.assertEqual(
                    tuple(self.read(FLOW + off) for off in range(0, 28, 4)),
                    (NODE, POOL, KIT, track, 897 + track, 7, 0),
                )
                self.assertEqual(self.calls[-1], ("name", NODE, POOL))

    def test_name_callback_stages_without_writing_and_cancel_preserves_audio(self):
        self.call(BEGIN, NODE, POOL, VIEW)
        self.cpu.mem_write(TEXT, struct.pack(">2I", NODE, POOL))
        self.cpu.mem_write(TEXT + 16, struct.pack(">I", TEXT + 32))
        self.cpu.mem_write(TEXT + 32, b"A" * 60 + b"\0")
        before = self.contents()
        self.call(CAPTURE, TEXT, TEXT + 16)
        self.assertEqual(self.read(FLOW + bank.PHASE), 1)
        self.assertEqual(
            bytes(self.cpu.mem_read(FLOW + bank.NAME, 61)), b"A" * 60 + b"\0"
        )
        self.assertEqual(self.contents(), before)
        self.assertEqual(self.calls, [("name", NODE, POOL)])
        self.assertEqual(self.event(12), 1)
        self.assertEqual(self.read(FLOW + bank.PHASE), 0)
        self.assertEqual(self.contents(), before)

    def test_bank_keys_are_single_release_actions_and_wrap(self):
        for flags in (1, 9, 18):
            self.event(15, flags)
            self.assertEqual(self.read(FLOW + bank.BANK), 0)
        self.event(13)
        self.assertEqual(self.read(FLOW + bank.BANK), 7)
        self.event(15)
        self.assertEqual(self.read(FLOW + bank.BANK), 0)
        self.assertEqual(self.calls, [])

    def test_bank_page_resets_on_track_change_even_for_same_take_alias(self):
        self.cpu.mem_write(KIT + 7 * 0x450 + 0x80, struct.pack(">H", 9))
        self.selected = 7
        self.assertEqual(self.call(ACTIVE, VIEW), 0)
        self.assertEqual(self.read(FLOW + bank.PHASE), 0)
        self.assertEqual(self.calls, [])
