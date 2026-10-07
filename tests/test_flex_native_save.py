"""Native explicit-save transaction and recorder shortcut negative controls."""

import struct
import unittest

from lab import flex_native_save as save

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None

CODE, STACK, STOP = 0x100000, 0x20F000, 0x10F000
NODE, POOL, NAME = 0x300100, 0x310000, 0x304000


@unittest.skipIf(u is None, "Use the configured Unicorn runtime")
class NativeSaveTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for address, length in (
            (CODE, 0x10000),
            (0x200000, 0x10000),
            (0x300000, 0x20000),
        ):
            self.cpu.mem_map(address, length)
        self.original = struct.pack(">4I", 0x7FFE0001, 7, 1080, 0)
        self.old_saved = struct.pack(">4I", 8, 7, 1080, 0)
        self.new_saved = struct.pack(">4I", 9, 7, 1080, 0)
        self.cpu.mem_write(NODE, bytes(4) + self.original + bytes(28))
        self.cpu.mem_write(POOL, b"\xff" * 0x4000)
        self.cpu.mem_write(POOL + 16, self.original)
        self.cpu.mem_write(POOL + 32, struct.pack(">4I", 0x7FFE0002, 8, 1080, 0))
        self.cpu.mem_write(
            CODE,
            save.write_named(
                CODE, CODE + 0x5000, CODE + 0x6000, CODE + 0x7000, NAME + 256
            ),
        )
        self.cpu.mem_write(CODE + 0x7000, save.promote(CODE + 0x7000))
        self.cpu.mem_map(0x40157000, 0x1000)
        self.current_pool, self.fail_save, self.writes = POOL, False, []

        def services(cpu, pc, *_):
            sp = cpu.reg_read(r.UC_M68K_REG_A7)
            result = 0
            if pc == CODE + 0x5000:
                result = self.current_pool
            elif pc == CODE + 0x6000:
                node, path, ref = struct.unpack(">3I", cpu.mem_read(sp + 4, 12))
                self.assertEqual(node, NODE)
                name = bytes(cpu.mem_read(path, 72)).split(b"\0")[0]
                self.writes.append(name)
                if self.fail_save:
                    result = 0xFFFFFFFF
                else:
                    cpu.mem_write(ref, self.new_saved)
            cpu.reg_write(r.UC_M68K_REG_D0, result)
            cpu.reg_write(r.UC_M68K_REG_PC, int.from_bytes(cpu.mem_read(sp, 4), "big"))
            cpu.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for pc in (CODE + 0x5000, CODE + 0x6000, 0x40157192):
            self.cpu.hook_add(u.UC_HOOK_CODE, services, begin=pc, end=pc)

    def call(self, name):
        cpu = self.cpu
        cpu.mem_write(NAME, name + b"\0")
        cpu.mem_write(STACK, struct.pack(">4I", STOP, NODE, POOL, NAME))
        cpu.reg_write(r.UC_M68K_REG_A7, STACK)
        registers = [
            getattr(r, f"UC_M68K_REG_{kind}{i}")
            for kind, first, last in (("D", 2, 8), ("A", 2, 7))
            for i in range(first, last)
        ]
        for reg in registers:
            cpu.reg_write(reg, 0xBAD000 + reg)
        cpu.emu_start(CODE, STOP, count=100000)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_PC), STOP)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_A7), STACK + 4)
        for reg in registers:
            self.assertEqual(cpu.reg_read(reg), 0xBAD000 + reg)
        return cpu.reg_read(r.UC_M68K_REG_D0)

    def test_named_save_promotes_only_selected_take_and_aliases(self):
        self.cpu.mem_write(NODE + 28, struct.pack(">I", 1) + self.old_saved)
        self.cpu.mem_write(POOL + 48, self.old_saved)
        unrelated = bytes(self.cpu.mem_read(POOL + 32, 16))
        self.assertEqual(self.call(b"My final take"), 0)
        self.assertEqual(self.writes, [b"/recorded/My final take"])
        for offset in (16, 48):
            self.assertEqual(
                bytes(self.cpu.mem_read(POOL + offset, 16)), self.new_saved
            )
        self.assertEqual(bytes(self.cpu.mem_read(POOL + 32, 16)), unrelated)
        self.assertEqual(
            bytes(self.cpu.mem_read(NODE + 28, 20)),
            struct.pack(">I", 1) + self.new_saved,
        )

    def test_sixty_character_name_is_bounded(self):
        self.assertEqual(self.call(b"A" * 60), 0)
        self.assertEqual(self.writes, [b"/recorded/" + b"A" * 60])

    def test_invalid_names_do_not_write_or_publish(self):
        before = bytes(self.cpu.mem_read(POOL, 0x4000))
        for name in (
            b"",
            b".",
            b"..",
            b" hidden",
            b"A/B",
            b"A\\B",
            b"A\nB",
            b"A\x80B",
            b"A" * 61,
        ):
            with self.subTest(name=name):
                self.assertEqual(self.call(name), 0xFFFFFFFF)
                self.assertEqual(self.writes, [])
                self.assertEqual(bytes(self.cpu.mem_read(POOL, 0x4000)), before)

    def test_changed_project_and_write_failure_preserve_references(self):
        before = bytes(self.cpu.mem_read(POOL, 0x4000))
        self.current_pool = POOL + 16
        self.assertEqual(self.call(b"Changed project"), 0xFFFFFFFF)
        self.assertEqual(self.writes, [])
        self.current_pool, self.fail_save = POOL, True
        self.assertEqual(self.call(b"Write failure"), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(POOL, 0x4000)), before)
        self.assertEqual(bytes(self.cpu.mem_read(NODE + 28, 20)), bytes(20))


@unittest.skipIf(u is None, "Use the configured Unicorn runtime")
class RecorderSaveKeyTests(unittest.TestCase):
    def execute(self, code, flags, phase=0, node=NODE):
        cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for address, length in (
            (CODE, 0x10000),
            (0x200000, 0x10000),
            (0x300000, 0x10000),
            (0x40015000, 0x1000),
            (0x40199000, 0x1000),
        ):
            cpu.mem_map(address, length)
        cpu.mem_write(
            CODE,
            save.recorder_keys(
                CODE,
                CODE + 0x1000,
                CODE + 0x2000,
                CODE + 0x3000,
                0x300100,
                0x300200,
                CODE + 0x4000,
            ),
        )
        cpu.mem_write(CODE + 0x4000, bytes.fromhex("70074e75"))
        event, view = 0x301000, 0x302000
        cpu.mem_write(event, bytes(12) + struct.pack(">II", code, flags))
        cpu.mem_write(STACK, struct.pack(">III", STOP, view, event))
        cpu.reg_write(r.UC_M68K_REG_A7, STACK)
        calls = []

        def service(uc, pc, *_):
            sp = uc.reg_read(r.UC_M68K_REG_A7)
            result = 0
            if pc == 0x40015F6C:
                result = phase
            elif pc == CODE + 0x1000:
                result = node
                uc.reg_write(r.UC_M68K_REG_D1, POOL)
            elif pc in (CODE + 0x2000, CODE + 0x3000):
                calls.append((pc, int.from_bytes(uc.mem_read(sp + 4, 4), "big")))
                if pc == CODE + 0x2000:
                    self.assertEqual(
                        bytes(uc.mem_read(sp + 4, 8)), struct.pack(">II", NODE, POOL)
                    )
            uc.reg_write(r.UC_M68K_REG_D0, result)
            uc.reg_write(r.UC_M68K_REG_PC, int.from_bytes(uc.mem_read(sp, 4), "big"))
            uc.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for pc in (0x4019988A, 0x40015F6C, CODE + 0x1000, CODE + 0x2000, CODE + 0x3000):
            cpu.hook_add(u.UC_HOOK_CODE, service, begin=pc, end=pc)
        cpu.emu_start(CODE, STOP, count=1000)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_PC), STOP)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_A7), STACK + 4)
        return cpu.reg_read(r.UC_M68K_REG_D0), calls

    def test_idle_func_record_opens_once(self):
        self.assertEqual(self.execute(0x13, 3), (1, [(CODE + 0x2000, NODE)]))
        for flags in (0x12, 0xB):
            self.assertEqual(self.execute(0x13, flags), (1, []))

    def test_other_keys_and_unmodified_record_keep_stock_dispatch(self):
        for code, flags in ((0x13, 1), (0x13, 0x10), (0xA, 3), (0xC, 3)):
            self.assertEqual(self.execute(code, flags), (7, []))

    def test_unaccepted_take_and_missing_sample_show_specific_messages(self):
        self.assertEqual(
            self.execute(0x13, 3, phase=4), (1, [(CODE + 0x3000, 0x300200)])
        )
        self.assertEqual(
            self.execute(0x13, 3, node=0), (1, [(CODE + 0x3000, 0x300100)])
        )
        self.assertEqual(self.execute(0x13, 3, phase=2), (1, []))
