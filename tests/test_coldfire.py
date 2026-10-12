"""Regression for the hardware-observed illegal MOVE and conservative decoder."""

import unittest

from lab.coldfire import RANK, audit_code, fix_rank, rank_shim


class ColdFireTests(unittest.TestCase):
    def test_hardware_fault_and_second_illegal_move_rejected(self):
        for code in ("2f7c40311a840008", "2f7c40311ac4000c"):
            with self.assertRaisesRegex(ValueError, "MOVE source/destination"):
                audit_code(bytes.fromhex(code), RANK)

    def test_move_restrictions_other_addresses_and_sizes(self):
        for code in (
            "23fc0000000140001000",
            "33fc000140001000",
            "2f79004010000008",
            "23ef000840001000",
        ):
            with self.assertRaisesRegex(ValueError, "MOVE source/destination"):
                audit_code(bytes.fromhex(code), 0x40001000)

    def test_supported_move_alternatives(self):
        for code in ("203c40311a84", "2f400008", "2f08", "205f", "2f48000c"):
            self.assertEqual(len(audit_code(bytes.fromhex(code), RANK)), 1)
        self.assertEqual(len(rank_shim()), 28)
        self.assertEqual(len(audit_code(rank_shim(), RANK)), 7)

    def test_unreviewed_and_truncated_forms_fail_closed(self):
        for code in ("4afc", "4e", "203c", "4e754e", "41f0", "6102", "600000"):
            with self.assertRaises(ValueError):
                audit_code(bytes.fromhex(code), RANK)

    def test_stock_absolute_short_pea_allocation_literal(self):
        self.assertEqual(
            audit_code(bytes.fromhex("48780024"), RANK)[0]["kind"], "PEA absolute-short"
        )
        with self.assertRaises(ValueError):
            audit_code(bytes.fromhex("487800"), RANK)

    def test_native_virtual_call_address_registers(self):
        for register in range(8):
            code = (0x4E90 + register).to_bytes(2, "big")
            self.assertEqual(audit_code(code, RANK)[0]["kind"], "JSR (An)")
        for code in ("4e98", "4ea0", "4eb0"):
            with self.assertRaises(ValueError):
                audit_code(bytes.fromhex(code), RANK)

    def test_source_ownership_integer_forms(self):
        for code in ("5380", "5382", "4a80", "4a82", "4a83"):
            self.assertEqual(len(audit_code(bytes.fromhex(code), RANK)), 1)
        with self.assertRaises(ValueError):
            audit_code(bytes.fromhex("4a88"), RANK)

    def test_fix_refuses_unknown_input(self):
        with self.assertRaisesRegex(ValueError, "byte guard"):
            fix_rank(bytes(0x320000))

    def test_feedback_forms_reject_truncation_and_other_registers(self):
        for code in ("02800000007f", "02810000fc00", "ee89", "e889", "9283"):
            self.assertEqual(len(audit_code(bytes.fromhex(code), RANK)), 1)
        for code in ("02800000", "02820000007f", "ee8a", "e88a"):
            with self.assertRaises(ValueError):
                audit_code(bytes.fromhex(code), RANK)


if __name__ == "__main__":
    unittest.main()
