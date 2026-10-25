import unittest

from lab.recorder_overlay import sector_overlay


class RecorderOverlayTests(unittest.TestCase):
    def test_boundary_bytes_preserve_rest_of_each_original_sector(self):
        calls = []

        def read(sector, size):
            calls.append((sector, size))
            return bytes([sector + 10]) * size

        result = sector_overlay({511: 42, 512: 43, 514: 44}, read)
        self.assertEqual(calls, [(0, 512), (1, 512)])
        self.assertEqual(result[0], bytes([10]) * 511 + b"*")
        self.assertEqual(result[1], b"+\x0b," + bytes([11]) * 509)

    def test_sector_maps_and_out_of_bounds_inputs_are_rejected(self):
        for overlay in ({1: bytes(512)}, {-1: 0}, {0: 256}, {1024: 1}):
            with self.assertRaises(ValueError):
                sector_overlay(overlay, lambda s, n: bytes(n), sectors=2)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            sector_overlay({0: 1}, lambda s, n: bytes(511))
