"""Ownership rejection, byte compatibility, and native save ordering/ABI."""

import struct
import unittest

from lab.project_save import SavePhases, dispatcher
from lab.resources import (
    PaddingAllocator,
    Region,
    patch_conflicts,
    validate_names,
    validate_regions,
)
from lab.sharc_hooks import HOOKS, Address, Hook, validate_preemption

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None


class ResourceTests(unittest.TestCase):
    def test_allocator_alignment_reach_and_overlap_rejections(self):
        allocator = PaddingAllocator(((0x1002, 0x1010), (0x2000, 0x2010)))
        self.assertEqual(allocator.allocate("first", 8), 0x1004)
        self.assertEqual(
            allocator.allocate("second", 8, near=(0x2000,), reach=16), 0x2000
        )
        for action in (
            lambda: allocator.allocate("first", 2),
            lambda: allocator.allocate("too-big", 100),
            lambda: PaddingAllocator(((1, 10), (5, 15))),
        ):
            with self.assertRaises(ValueError):
                action()

    def test_address_domains_and_preemption_are_not_interchangeable(self):
        with self.assertRaises(ValueError):
            Address(0x1C4F15, "dsp-sw").in_space("cpu")
        with self.assertRaises(ValueError):
            validate_preemption(
                (
                    HOOKS["source"],
                    Hook(
                        "bad-event",
                        Address(1, "dsp-sw"),
                        Address(2, "dsp-sw"),
                        HOOKS["source"].scratch,
                        HOOKS["source"].stack,
                        "sample-event",
                    ),
                )
            )
        validate_preemption(tuple(HOOKS.values()))

    def test_active_event_wrapper_rejects_a_word_address_as_scratch(self):
        from lab.capicola_automatic import wrapper

        event = HOOKS["sample-page"]
        with self.assertRaises(ValueError):
            wrapper(
                "cap_page_hook",
                "cap_event",
                Address(event.scratch.value, "dsp-dm"),
                event.stack,
                "",
                "",
                event.continuation,
            )

    def test_named_ownership_and_regions_reject_collisions(self):
        with self.assertRaises(ValueError):
            validate_names((("sine", ["machine:7"]), ("plaits", ["machine:7"])))
        with self.assertRaises(ValueError):
            validate_regions(
                [Region("a", "cpu", 10, 20, "boot"), Region("b", "cpu", 15, 30, "boot")]
            )
        validate_regions(
            [Region("a", "cpu", 10, 20, "boot"), Region("b", "dsp-dm", 10, 20, "boot")]
        )
        self.assertEqual(
            patch_conflicts(
                [
                    ("a", [{"address": 16, "after": "11223344", "label": "one"}]),
                    ("b", [{"address": 18, "after": "aabb", "label": "two"}]),
                ]
            )[0]["end"],
            20,
        )

    def test_no_implicit_save_phase_alias(self):
        with self.assertRaises(ValueError):
            SavePhases(0x1000, prepare=(0x1000,))


@unittest.skipIf(u is None, "Configured Unicorn required")
class SaveDispatcherTests(unittest.TestCase):
    def execute(self, prepare_result=0, stock_result=1, commit_result=0):
        cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        cpu.mem_map(0x100000, 0x10000)
        cpu.mem_map(0x200000, 0x10000)
        targets = dict(
            arp=0x101000,
            flex=0x102000,
            stock=0x103000,
            commit=0x104000,
            cleanup=0x105000,
        )
        plan = SavePhases(
            targets["stock"],
            (targets["arp"], targets["flex"]),
            (targets["commit"],),
            (targets["cleanup"],),
        )
        cpu.mem_write(0x100000, dispatcher(0x100000, plan))
        events = []

        def callback(machine, pc, _size, _user):
            name = next(name for name, value in targets.items() if value == pc)
            sp = machine.reg_read(r.UC_M68K_REG_A7)
            count = 4 if name == "commit" else 3
            args = struct.unpack(f">{count}I", machine.mem_read(sp + 4, count * 4))
            events.append((name, args))
            result = {
                "arp": 0,
                "flex": prepare_result,
                "stock": stock_result,
                "commit": commit_result,
                "cleanup": 0x1234,
            }[name]
            machine.reg_write(r.UC_M68K_REG_D0, result & 0xFFFFFFFF)
            machine.reg_write(r.UC_M68K_REG_D1, 0xBAD)
            machine.reg_write(r.UC_M68K_REG_A0, 0xBAD)
            machine.reg_write(
                r.UC_M68K_REG_PC, int.from_bytes(machine.mem_read(sp, 4), "big")
            )
            machine.reg_write(r.UC_M68K_REG_A7, sp + 4)

        for target in targets.values():
            cpu.hook_add(u.UC_HOOK_CODE, callback, begin=target, end=target)
        registers = [
            getattr(r, f"UC_M68K_REG_{kind}{i}")
            for kind, indices in (("D", range(1, 8)), ("A", range(7)))
            for i in indices
        ]
        for i, reg in enumerate(registers):
            cpu.reg_write(reg, 0x12340000 + i)
        sp, stop = 0x20F000, 0x10FF00
        cpu.mem_write(sp, struct.pack(">4I", stop, 0xAA, 0xBB, 0xCC))
        cpu.reg_write(r.UC_M68K_REG_SR, 0x2005)
        cpu.reg_write(r.UC_M68K_REG_A7, sp)
        cpu.emu_start(0x100000, stop, count=3000)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_PC), stop)
        self.assertEqual(cpu.reg_read(r.UC_M68K_REG_A7), sp + 4)
        for i, reg in enumerate(registers):
            self.assertEqual(cpu.reg_read(reg), 0x12340000 + i)
        for name, args in events:
            self.assertEqual(
                args,
                (stock_result, 0xAA, 0xBB, 0xCC)
                if name == "commit"
                else (0xAA, 0xBB, 0xCC),
            )
        return [name for name, _ in events], cpu.reg_read(r.UC_M68K_REG_D0)

    def test_success_and_companion_failure_preserve_exact_stock_result(self):
        for companion in (0, -1):
            order, result = self.execute(
                stock_result=0xABCD0001, commit_result=companion
            )
            self.assertEqual(order, ["arp", "flex", "stock", "commit", "cleanup"])
            self.assertEqual(result, 0xABCD0001)

    def test_prepare_failure_skips_writer_and_companion(self):
        order, result = self.execute(prepare_result=-1)
        self.assertEqual(order, ["arp", "flex", "cleanup"])
        self.assertEqual(result, 0)

    def test_stock_failure_skips_companion_but_cleans_up(self):
        for raw in (0, 0xABCD0000, 2):
            order, result = self.execute(stock_result=raw)
            self.assertEqual(order, ["arp", "flex", "stock", "cleanup"])
            self.assertEqual(result, raw)
