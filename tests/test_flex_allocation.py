"""Native split-allocation transactions; heap/copy/loader callees are models.

These establish pre-publication cleanup, not scheduler or late-reader safety.
"""

import struct
import unittest

from lab.flex_native import USE_ERRORS, accept_recording

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None


@unittest.skipIf(u is None, "Native execution requires configured Unicorn runtime")
class SplitAllocationTests(unittest.TestCase):
    def run_case(self, failure=None, repetitions=1):
        cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        code, copier, stop, state, stack = (
            0x100000,
            0x108000,
            0x10F000,
            0x200000,
            0x20F000,
        )
        for base, size in (
            (code, 0x10000),
            (state, 0x10000),
            (0x300000, 0x100000),
            (0x40000000, 0x1000000),
        ):
            cpu.mem_map(base, size)
        errors = {name: i for i, name in enumerate(USE_ERRORS)}
        cpu.mem_write(
            code, accept_recording(code, copier, errors, separate_source=True)
        )
        cpu.mem_write(stop, bytes.fromhex("4e71"))
        cpu.mem_write(0x405B1378, bytes.fromhex("ffffffff"))
        live, freed, calls = {}, [], []
        next_pointer = 0x300000
        allocations = 0

        def word(address):
            return int.from_bytes(cpu.mem_read(address, 4), "big")

        def service(uc, pc, size, data):
            nonlocal next_pointer, allocations
            sp = cpu.reg_read(r.UC_M68K_REG_A7)
            args = [word(sp + 4 + i * 4) for i in range(5)]
            calls.append(pc)
            result = 0
            if pc == 0x4011E8F0:
                allocations += 1
                if (failure, allocations % 2) not in (("descriptor", 1), ("source", 0)):
                    result = next_pointer
                    live[result] = args[0]
                    next_pointer += (args[0] + 15) & ~15
            elif pc == 0x4011E8FC:
                self.assertIn(args[0], live)
                freed.append(args[0])
                del live[args[0]]
            elif pc == copier:
                self.assertEqual(live[args[0]], 362)
                result = 0xFFFFFFFF if failure == "copy" else 362
            elif pc == 0x4015A6DC:
                result = 0x12345679
            elif pc == 0x40154540:
                result = 1 if failure == "loader" else 0
            cpu.reg_write(r.UC_M68K_REG_D0, result)
            cpu.reg_write(r.UC_M68K_REG_A7, sp + 4)
            cpu.reg_write(r.UC_M68K_REG_PC, word(sp))

        services = (
            0x4011E8F0,
            0x4011E8FC,
            copier,
            0x400015A0,
            0x4015AA20,
            0x4015A6DC,
            0x400016D2,
            0x40154540,
            0x401540C6,
            0x40153BEA,
        )
        for pc in services:
            cpu.hook_add(u.UC_HOOK_CODE, service, begin=pc, end=pc)
        for _ in range(repetitions):
            cpu.mem_write(stack, struct.pack(">6I", stop, state, 0, 141, 0, 1))
            cpu.reg_write(r.UC_M68K_REG_A7, stack)
            cpu.emu_start(code, stop, count=100000)
            self.assertEqual(cpu.reg_read(r.UC_M68K_REG_PC), stop)
            self.assertEqual(cpu.reg_read(r.UC_M68K_REG_A7), stack + 4)
            if failure:
                self.assertEqual(cpu.reg_read(r.UC_M68K_REG_D0), 0xFFFFFFFF)
                self.assertEqual((word(state), word(state + 4)), (0, 0))
                self.assertFalse(live)
        return live, freed, calls, word(state), word(state + 4)

    def test_descriptor_failure_has_no_cleanup_or_publication(self):
        live, freed, calls, _, _ = self.run_case("descriptor")
        self.assertFalse(live or freed)
        self.assertNotIn(0x40154540, calls)

    def test_source_failure_frees_only_descriptor(self):
        live, freed, calls, _, _ = self.run_case("source")
        self.assertFalse(live)
        self.assertEqual(len(freed), 1)
        self.assertNotIn(0x40154540, calls)

    def test_copy_failure_frees_both_before_loader(self):
        live, freed, calls, _, _ = self.run_case("copy", 1000)
        self.assertFalse(live)
        self.assertEqual(len(freed), 2000)
        self.assertNotIn(0x40154540, calls)

    def test_loader_failure_preserves_existing_cleanup_contract(self):
        live, freed, calls, _, _ = self.run_case("loader")
        self.assertFalse(live)
        self.assertEqual(len(freed), 2)
        self.assertIn(0x401540C6, calls)
        self.assertIn(0x40153BEA, calls)

    def test_success_keeps_descriptor_and_immutable_source(self):
        live, freed, _, head, count = self.run_case()
        self.assertEqual(sorted(live.values()), [64, 362])
        self.assertEqual(live[head], 64)
        self.assertEqual(count, 1)
        self.assertFalse(freed)
