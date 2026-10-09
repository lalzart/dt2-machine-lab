"""Execute read-only Flex accounting; no loader or heap services substituted."""

import struct
import unittest

from lab.flex_memory import snapshot

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None


@unittest.skipIf(u is None, "Native execution requires configured Unicorn runtime")
class FlexMemoryTests(unittest.TestCase):
    def run_snapshot(self, takes, *, busy=False, cycle=False):
        cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        code, state, output, stack, stop = (
            0x100000,
            0x200000,
            0x210000,
            0x21F000,
            0x10F000,
        )
        cpu.mem_map(code, 0x10000)
        cpu.mem_map(state, 0x20000)
        cpu.mem_write(code, snapshot(code))
        cpu.mem_write(stop, bytes.fromhex("4e71"))
        nodes = [state + 0x100 + i * 64 for i in range(len(takes))]
        cpu.mem_write(
            state,
            struct.pack(">4I", nodes[0] if nodes else 0, len(nodes), 0, int(busy)),
        )
        for i, (length, saved) in enumerate(takes):
            following = nodes[i + 1] if i + 1 < len(nodes) else nodes[0] if cycle else 0
            words = [following, 0, 0, length, 0, 0, 0, int(saved)] + [0] * 8
            cpu.mem_write(nodes[i], struct.pack(">16I", *words))
        cpu.mem_write(output, b"\xa5" * 16)
        cpu.mem_write(stack, struct.pack(">3I", stop, state, output))
        cpu.reg_write(r.UC_M68K_REG_A7, stack)
        saved_regs = [
            r.UC_M68K_REG_D2,
            r.UC_M68K_REG_D3,
            r.UC_M68K_REG_D4,
            r.UC_M68K_REG_D5,
            r.UC_M68K_REG_A2,
            r.UC_M68K_REG_A3,
        ]
        for reg in saved_regs:
            cpu.reg_write(reg, 0x12345678)
        before = bytes(cpu.mem_read(state, 0x10000))
        cpu.emu_start(code, stop, count=10000)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_PC), stop)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_A7), stack + 4)
        for reg in saved_regs:
            self.assertEqual(cpu.reg_read(reg), 0x12345678)
        self.assertEqual(bytes(cpu.mem_read(state, 0x10000)), before)
        return cpu.reg_read(r.UC_M68K_REG_D0), struct.unpack(
            ">4I", cpu.mem_read(output, 16)
        )

    def test_empty(self):
        self.assertEqual(self.run_snapshot([]), (0, (0, 0, 0, 0)))

    def test_mixed_sources_saved_source_stays_counted(self):
        self.assertEqual(
            self.run_snapshot([(362, False), (1920080, True), (3840080, False)]),
            (0, (3, 1, 5760282, 5760714)),
        )

    def test_full_stereo_capacity(self):
        self.assertEqual(
            self.run_snapshot([(3840080, True)] * 32),
            (0, (32, 32, 122880000, 122884608)),
        )

    def test_busy_corrupt_or_unbounded_does_not_publish(self):
        for args, options in [
            ([(362, False)], {"busy": True}),
            ([(362, False)], {"cycle": True}),
            ([(361, False)], {}),
            ([(3840081, True)], {}),
            ([(362, False)] * 33, {}),
        ]:
            with self.subTest(args=args[:1], options=options):
                self.assertEqual(
                    self.run_snapshot(args, **options), (0xFFFFFFFF, (0xA5A5A5A5,) * 4)
                )


if __name__ == "__main__":
    unittest.main()
