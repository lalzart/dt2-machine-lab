"""Native save-screen state, track isolation and recorder-start guards."""

import struct
import unittest

from lab import flex_save_screen as screen
from lab.flex_native import assign_recording, resource_lookup
from lab.flex_native_save import target

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None

CODE, STACK, STOP = 0x100000, 0x20F000, 0x10F000
HEAD, VIEW, CONTROLLER, KIT, POOL = 0x300000, 0x303000, 0x304000, 0x306000, 0x310000


@unittest.skipIf(u is None, "Configured native runtime required")
class FlexSaveScreenTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for address, size in (
            (CODE, 0x10000),
            (0x200000, 0x10000),
            (0x300000, 0x20000),
            (0x40015000, 0x1000),
            (0x4004A000, 0x1000),
            (0x4011A000, 0x1000),
            (0x405B1000, 0x5000),
            (0x405BA000, 0x1000),
            (0x80004000, 0x1000),
        ):
            self.cpu.mem_map(address, size)
        self.cpu.mem_write(
            CODE, target(CODE, CODE + 0x6000, CODE + 0x5000, sample_machines=True)
        )
        self.cpu.mem_write(CODE + 0x1000, screen.pending(CODE + 0x1000, CODE))
        self.cpu.mem_write(
            CODE + 0xE000, screen.context(CODE + 0xE000, CODE + 0x1000, 0x305100)
        )
        self.cpu.mem_write(
            CODE + 0x2000,
            screen.keys(
                CODE + 0x2000,
                CODE + 0xE000,
                CODE + 0x7000,
                CODE + 0x8000,
                state=0x305100,
                discard_at=CODE + 0xF200,
                message=CODE + 0xF300,
                success=1,
                failure=2,
            ),
        )
        self.cpu.mem_write(
            CODE + 0x3000,
            target(
                CODE + 0x3000,
                CODE + 0x6000,
                CODE + 0x5000,
                sample_machines=True,
                settings_offset=0x10,
            ),
        )
        self.cpu.mem_write(CODE + 0x4000, screen.pending(CODE + 0x4000, CODE + 0x3000))
        self.cpu.mem_write(CODE + 0x5000, resource_lookup(CODE + 0x5000, HEAD))
        self.cpu.mem_write(CODE + 0x8000, bytes.fromhex("70074e75"))
        self.cpu.mem_write(
            CODE + 0x9000,
            screen.start_guard(CODE + 0x9000, CODE + 0x4000, screen.MANUAL, 2),
        )
        self.cpu.mem_write(
            CODE + 0xA000,
            screen.start_guard(CODE + 0xA000, CODE + 0x4000, screen.ARM, 1),
        )
        self.cpu.mem_write(
            CODE + 0xB000,
            assign_recording(
                CODE + 0xB000, sample_machines=True, pending_track=CODE + 0xD000
            ),
        )
        self.cpu.mem_write(
            CODE + 0xC000,
            target(
                CODE + 0xC000,
                CODE + 0x6000,
                CODE + 0x5000,
                sample_machines=True,
                direct_track=True,
            ),
        )
        self.cpu.mem_write(CODE + 0xD000, screen.pending(CODE + 0xD000, CODE + 0xC000))
        self.cpu.mem_write(0x80004704, struct.pack(">I", KIT))
        self.nodes = [0x300100 + i * 64 for i in range(16)]
        self.cpu.mem_write(HEAD, struct.pack(">I", self.nodes[0]))
        for i, node in enumerate(self.nodes):
            ref = struct.pack(">4I", 0x7FFE0001 + i, 100 + i, 1080, 0)
            self.cpu.mem_write(
                node, struct.pack(">I", self.nodes[i + 1] if i < 15 else 0) + ref
            )
            self.cpu.mem_write(KIT + i * 0x450 + 0x80, struct.pack(">H", i + 1))
            self.cpu.mem_write(0x405B1368 + (i + 1) * 16, ref)
        self.selected, self.calls = 0, []

        def service(cpu, pc, *_):
            sp = cpu.reg_read(r.UC_M68K_REG_A7)
            result = 0
            if pc == 0x4004ABE8:
                result = self.selected
            elif pc == CODE + 0x6000:
                result = POOL
            elif pc == CODE + 0x7000:
                self.calls.append(
                    ("name", *struct.unpack(">2I", cpu.mem_read(sp + 4, 8)))
                )
            elif pc == CODE + 0xF200:
                self.calls.append(
                    ("discard", *struct.unpack(">2I", cpu.mem_read(sp + 4, 8)))
                )
            elif pc == CODE + 0xF300:
                self.calls.append(
                    ("message", int.from_bytes(cpu.mem_read(sp + 4, 4), "big"))
                )
            elif pc == 0x4011AEEA:
                self.calls.append(
                    ("back", int.from_bytes(cpu.mem_read(sp + 4, 4), "big"))
                )
            elif pc in (screen.MANUAL + 8, screen.ARM + 8):
                mode, ret = struct.unpack(">2I", cpu.mem_read(sp, 8))
                self.calls.append(("start", mode, cpu.reg_read(r.UC_M68K_REG_A0)))
                cpu.reg_write(r.UC_M68K_REG_A7, sp + 8)
                cpu.reg_write(r.UC_M68K_REG_PC, ret)
                return
            cpu.reg_write(r.UC_M68K_REG_D0, result)
            cpu.reg_write(r.UC_M68K_REG_PC, int.from_bytes(cpu.mem_read(sp, 4), "big"))
            cpu.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for pc in (
            0x4004ABE8,
            CODE + 0x6000,
            CODE + 0x7000,
            CODE + 0xF200,
            CODE + 0xF300,
            0x4011AEEA,
            screen.MANUAL + 8,
            screen.ARM + 8,
        ):
            self.cpu.hook_add(u.UC_HOOK_CODE, service, begin=pc, end=pc)

    def call(self, pc, *args):
        self.cpu.mem_write(STACK, struct.pack(">" + "I" * (len(args) + 1), STOP, *args))
        self.cpu.reg_write(r.UC_M68K_REG_A7, STACK)
        self.cpu.emu_start(pc, STOP, count=10000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), STOP)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), STACK + 4)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def saved(self, index):
        self.cpu.mem_write(self.nodes[index] + 28, struct.pack(">I", 1))

    def event(self, key, flags=16):
        event = 0x305000
        self.cpu.mem_write(event + 12, struct.pack(">II", key, flags))
        return self.call(CODE + 0x2000, VIEW, event)

    def test_all_sample_machines_keep_pending_take_on_every_track(self):
        for machine in (0, 1, 2, 3, 4, 6):
            for track in range(16):
                self.selected = track
                self.cpu.mem_write(KIT + track * 0x450 + 0xD6, bytes([machine]))
                self.assertEqual(self.call(CODE + 0x1000, VIEW), self.nodes[track])
                self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_D1), POOL)

    def test_saved_and_shared_aliases_unlock_without_affecting_other_tracks(self):
        self.cpu.mem_write(KIT + 0x450 + 0x80, struct.pack(">H", 1))
        self.saved(0)
        for track in (0, 1, 15, 7, 0, 1):
            self.selected = track
            expected = 0 if track < 2 else self.nodes[track]
            self.assertEqual(self.call(CODE + 0x1000, VIEW), expected)

    def test_midi_synthesis_unknown_and_missing_assignment_use_stock(self):
        for machine in (5, 7, 8, 255):
            self.cpu.mem_write(KIT + 0xD6, bytes([machine]))
            self.assertEqual(self.call(CODE + 0x1000, VIEW), 0)
        self.cpu.mem_write(KIT + 0xD6, b"\0")
        self.cpu.mem_write(KIT + 0x80, struct.pack(">H", 1024))
        self.assertEqual(self.call(CODE + 0x1000, VIEW), 0)

    def test_visible_save_and_back_capture_exact_take_without_mutation(self):
        self.cpu.mem_write(KIT + 0xD6, b"\x02")
        regions = ((HEAD, 0x1000), (KIT, 16 * 0x450), (POOL, 0x4000))
        before = [bytes(self.cpu.mem_read(a, n)) for a, n in regions]
        self.assertEqual(self.event(10), 1)
        self.assertEqual(self.calls, [("name", self.nodes[0], POOL)])
        self.calls.clear()
        self.assertEqual(self.event(12), 1)
        self.assertEqual(self.calls, [("back", VIEW)])
        self.assertEqual([bytes(self.cpu.mem_read(a, n)) for a, n in regions], before)

    def test_releases_repeats_modifiers_and_record_do_not_save_or_start(self):
        for key, flags in (
            (10, 1),
            (10, 0),
            (10, 9),
            (10, 18),
            (12, 1),
            (19, 1),
            (43, 1),
        ):
            self.assertEqual(self.event(key, flags), 1)
            self.assertEqual(self.calls, [])
        for key in (1, 2, 3, 4, 5, 6, 16, 20, 21, 25, 40):
            self.assertEqual(self.event(key), 7)
        self.saved(0)
        self.assertEqual(self.event(10), 7)

    def test_manual_and_armed_starts_block_only_selected_unsaved_track(self):
        self.cpu.mem_write(KIT + 0xD6, b"\x04")
        for pc, mode in ((CODE + 0x9000, 2), (CODE + 0xA000, 1)):
            self.assertEqual(self.call(pc, CONTROLLER), 0)
            self.assertEqual(self.calls, [])
            self.saved(1)
            self.selected = 1
            self.call(pc, CONTROLLER)
            self.assertEqual(self.calls, [("start", mode, CONTROLLER)])
            self.calls.clear()
            self.selected = 0

    def test_captured_destination_guard_is_independent_of_later_track_selection(self):
        self.selected = 15
        self.assertEqual(self.call(CODE + 0xD000, 0), self.nodes[0])
        self.saved(0)
        self.assertEqual(self.call(CODE + 0xD000, 0), 0)
        self.assertEqual(self.call(CODE + 0xD000, 15), self.nodes[15])

    def test_assignment_cannot_replace_an_unsaved_destination(self):
        self.cpu.mem_write(0x405BA768 + 300 * 4, struct.pack(">I", 0xDEAD0000))
        self.cpu.mem_write(KIT + 0xD6, b"\x02")
        before = bytes(self.cpu.mem_read(KIT, 16 * 0x450))
        self.assertEqual(self.call(CODE + 0xB000, 300, 0, KIT), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(KIT, len(before))), before)

    def test_discard_acts_on_first_yes_release_after_selection(self):
        self.assertEqual(self.event(14), 1)
        self.event(10, 1)
        self.assertEqual(self.calls, [])
        self.event(10)
        self.assertEqual(self.calls, [("discard", self.nodes[0], POOL), ("message", 1)])

    def test_leaving_menu_and_changing_take_reset_selection(self):
        self.event(14)
        self.event(12)
        self.assertEqual(self.calls, [("back", VIEW)])
        self.calls.clear()
        self.event(10)
        self.assertEqual(self.calls, [("name", self.nodes[0], POOL)])
        self.calls.clear()
        self.event(14)
        self.selected = 8
        self.event(10)
        self.assertEqual(self.calls, [("name", self.nodes[8], POOL)])
        self.cpu.mem_write(self.nodes[8] + 56, struct.pack(">I", 1))
        self.assertEqual(self.call(CODE + 0x1000, VIEW), 0)
