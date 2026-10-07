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

    def test_native_virtual_call_address_registers(self):
        for register in range(8):
            code = (0x4E90 + register).to_bytes(2, "big")
            self.assertEqual(audit_code(code, RANK)[0]["kind"], "JSR (An)")
        for code in ("4e98", "4ea0", "4eb0"):
            with self.assertRaises(ValueError):
                audit_code(bytes.fromhex(code), RANK)

    def test_fix_refuses_unknown_input(self):
        with self.assertRaisesRegex(ValueError, "byte guard"):
            fix_rank(bytes(0x320000))


if __name__ == "__main__":
    unittest.main()
