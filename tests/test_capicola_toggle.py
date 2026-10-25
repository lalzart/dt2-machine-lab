"""The optional routing layer has a closed control/protocol domain."""

import unittest

from lab.capicola_toggle import TITLES, decode_reply, patch_cpu, requested


class ToggleTests(unittest.TestCase):
    def test_disabled_layer_is_identity(self):
        image = b"unmodified arbitrary input"
        result, report = patch_cpu(image, enabled=False)
        self.assertIs(result, image)
        self.assertFalse(report["enabled"])
        self.assertEqual(report["writes"], [])
        with self.assertRaises(ValueError):
            patch_cpu(image)

    def test_full_wire_domain(self):
        for raw in range(65536):
            self.assertEqual(requested(raw), 128 <= raw <= 256)
            want = (
                ((raw >> 8) & 15, raw & 255)
                if raw >> 12 == 13 and raw & 255 <= 6
                else None
            )
            self.assertEqual(decode_reply(raw), want)
        self.assertFalse(requested(-1))
        self.assertFalse(requested(0xFFFFFFFF))

    def test_feedback_titles_are_fixed_and_distinct(self):
        self.assertEqual(len(TITLES), 8)
        self.assertTrue(all(len(t) == 18 and t.isascii() for t in TITLES))
        self.assertEqual(len(set(TITLES)), 8)
