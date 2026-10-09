"""Memory placement must reject overlap and unreviewed generated addresses."""

import unittest

from lab import capicola_layout as layout
from lab.capicola_memory import BANK_BASE, BANK_END


class LayoutTests(unittest.TestCase):
    def test_live_readers_fit_and_reject_old_lane_aliases(self):
        plan = layout.manifest(100000, 12496, family="capicola-stretch-live")
        regions = {r["name"]: r for r in plan["regions"]}
        cache, lanes, trace = [
            regions[n]
            for n in ("stretch_cache", "live_lanes", "live_destination_trace")
        ]
        self.assertLessEqual(cache["end"], lanes["start"])
        self.assertGreaterEqual(lanes["end"] - lanes["start"], 32 * 276)
        self.assertEqual(lanes["end"], trace["start"])
        self.assertLessEqual(trace["end"], regions["selector"]["start"])
        source = "\n".join(f"R0={a:#x};" for a in sorted(layout.LIVE_KERNEL_ADDRESSES))
        layout.relocate_assembly(source, "kernel", family="capicola-stretch-live")
        for bad in (source + "\nR0=0x200e4800;", source.replace("0x200eb000", "0")):
            with self.assertRaises(ValueError):
                layout.relocate_assembly(bad, "kernel", family="capicola-stretch-live")

    def test_maximum_bank_and_state_fit_existing_reservation(self):
        plan = layout.manifest(64588, 12496)
        self.assertLess(BANK_BASE + 576004 * 12, plan["state_base"])
        self.assertLessEqual(plan["state_base"] + plan["state_bytes"], BANK_END)
        self.assertFalse(plan["instruction_code"]["runtime_ownership_verified"])
        for code, data in ((0x40001, 1), (1, 0x10001), (0, 1), (1, 0)):
            with self.assertRaises(ValueError):
                layout.manifest(code, data)

    def test_loader_overlap_and_adjacent_boundaries(self):
        layout.check_stock_disjoint(
            [
                (layout.CODE_BASE - 4, layout.CODE_BASE),
                (layout.STATE_BASE + layout.STATE_BYTES, BANK_END),
            ]
        )
        for a, b in (
            (layout.CODE_BASE - 1, layout.CODE_BASE + 1),
            (layout.STATE_BASE - 1, layout.STATE_BASE + 1),
            (layout.STATE_BASE + 1, layout.STATE_BASE + 2),
        ):
            with self.assertRaises(ValueError):
                layout.check_stock_disjoint([(a, b)])

    def test_unknown_layout_family_and_address_refused(self):
        layout.validate_layout("legacy", False, "va")
        layout.validate_layout("reserved-state", True, "capicola-controls")
        layout.validate_layout("reserved-state", True, "capicola-selection")
        layout.validate_layout("reserved-state", True, "capicola-feedback")
        layout.validate_layout("reserved-state", True, "capicola-live-feedback")
        layout.validate_layout("reserved-state", True, "capicola-stretch")
        for args in (
            ("other", True, "capicola-controls"),
            ("reserved-state", False, "capicola-controls"),
            ("reserved-state", True, "integration"),
        ):
            with self.assertRaises(ValueError):
                layout.validate_layout(*args)
        for address in (layout.OLD_BASE - 1, layout.OLD_END):
            with self.assertRaises(ValueError):
                layout.address(address)
        source = "\n".join(f"R0={a:#x};" for a in sorted(layout.KERNEL_ADDRESSES))
        mapped = layout.relocate_assembly(source, "kernel")
        self.assertIn(hex(layout.address(0x200E4000)), mapped)
        for bad in (source + "\nR1=0x200eff00;", source.replace("0x200e4000", "0")):
            with self.assertRaises(ValueError):
                layout.relocate_assembly(bad, "kernel")
        selection = source + "\nR0=0x200e4600;"
        self.assertIn(
            hex(layout.address(0x200E4600)),
            layout.relocate_assembly(selection, "kernel", family="capicola-selection"),
        )
        with self.assertRaises(ValueError):
            layout.relocate_assembly(selection, "kernel")
        with self.assertRaises(ValueError):
            layout.relocate_assembly(source, "kernel", family="capicola-selection")
        with self.assertRaises(ValueError):
            layout.relocate_assembly(source, "unknown")
        feedback = selection + "\nR1=0x200e4610;R2=0x200e4618;R3=0x200e461c;"
        layout.relocate_assembly(feedback, "kernel", family="capicola-feedback")
        live = feedback + "\nR4=0x200e460c;"
        layout.relocate_assembly(live, "kernel", family="capicola-live-feedback")
        with self.assertRaises(ValueError):
            layout.relocate_assembly(live, "kernel", family="capicola-feedback")
        with self.assertRaises(ValueError):
            layout.relocate_assembly(feedback, "kernel", family="capicola-selection")

    def test_stretch_state_and_trace_are_disjoint_and_strict(self):
        plan = layout.manifest(77000, 12496, family="capicola-stretch")
        regions = {r["name"]: r for r in plan["regions"]}
        self.assertEqual(
            regions["stretch_destination_trace"]["end"]
            - regions["stretch_destination_trace"]["start"],
            32 * 128,
        )
        self.assertLessEqual(
            regions["stretch_lanes"]["end"],
            regions["stretch_destination_trace"]["start"],
        )
        self.assertLessEqual(
            regions["stretch_destination_trace"]["end"], regions["selector"]["start"]
        )
        source = "\n".join(
            f"R0={a:#x};" for a in sorted(layout.STRETCH_KERNEL_ADDRESSES)
        )
        layout.relocate_assembly(source, "kernel", family="capicola-stretch")
        for bad in (source + "\nR0=0x200e5800;", source.replace("0x200e6000", "0")):
            with self.assertRaises(ValueError):
                layout.relocate_assembly(bad, "kernel", family="capicola-stretch")

    def test_multi_cache_is_disjoint_and_cannot_use_single_bank_aliases(self):
        plan = layout.manifest(85000, 12496, family="capicola-stretch-multi")
        regions = {r["name"]: r for r in plan["regions"]}
        cache = regions["stretch_cache"]
        self.assertEqual(cache["end"] - cache["start"], 2048)
        self.assertLessEqual(
            regions["stretch_destination_trace"]["end"], cache["start"]
        )
        self.assertLessEqual(cache["end"], regions["selector"]["start"])
        source = "\n".join(f"R0={a:#x};" for a in sorted(layout.MULTI_KERNEL_ADDRESSES))
        layout.relocate_assembly(source, "kernel", family="capicola-stretch-multi")
        for bad in (source + "\nR0=0x200e4100;", source.replace("0x200e701c", "0")):
            with self.assertRaises(ValueError):
                layout.relocate_assembly(bad, "kernel", family="capicola-stretch-multi")
