"""Guard matched adapted STRETCH workloads and sample backing bounds."""

import struct
import unittest

from lab.resource_workloads import EVENTS
from lab.stretch_resources import controls, measured_frames, pcm_extent


class StretchResourceTests(unittest.TestCase):
    def setUp(self):
        self.template = bytes([37]) * 2048

    def test_controls_keep_source_and_route_only_requested_tracks(self):
        original = self.template
        for tracks in (0, 1, 4, 16):
            wire = controls(original, tracks)
            self.assertEqual(original, self.template)
            self.assertEqual(wire[:2], original[:2])
            self.assertTrue(all(wire[o : o + 2] == b"\0\0" for o in EVENTS))
            for track in range(16):
                self.assertEqual(
                    int.from_bytes(wire[0x94 + track * 2 : 0x96 + track * 2], "big"),
                    2 if track < tracks else 0,
                )
                base = 0xDA + track * 0x60
                self.assertEqual(int.from_bytes(wire[base + 6 : base + 8], "big"), 7)
                self.assertEqual(
                    wire[base + 20 : base + 96], original[0xDA + 20 : 0xDA + 96]
                )

    def test_one_shot_trigger_is_not_repeated(self):
        for tracks in (1, 4, 16):
            wire = controls(self.template, tracks)
            replay = measured_frames(wire, tracks, 128, trigger=True)
            self.assertEqual(
                int.from_bytes(replay[0][0x22:0x24], "big"), (1 << tracks) - 1
            )
            self.assertEqual(replay[1:], [wire] * 127)
        with self.assertRaises(ValueError):
            measured_frames(wire, 16, 257, trigger=True)

    def test_changed_controls_and_bounds(self):
        wire = controls(self.template, 1, fast=True)
        self.assertEqual(int.from_bytes(wire[0xDA:0xDC], "big"), 19456)
        self.assertEqual(wire[0xEA:0xEC], b"\0\0")
        wire = controls(self.template, 16, mixed=True)
        self.assertNotEqual(wire[0xDA:0xDC], wire[0xDA + 96 : 0xDC + 96])
        for source, tracks in ((self.template, 2), (bytes(100), 1)):
            with self.assertRaises(ValueError):
                controls(source, tracks)

    def test_lp0_extent_preserves_page_margin_and_rejects_bad_capture(self):
        raw = struct.pack("<I", 2) + bytes(4096)
        self.assertEqual(pcm_extent(raw), 4 * 4096 + 1024)
        for raw in (
            b"",
            bytes(4101),
            struct.pack("<I", 0x19200) + bytes(4096),
            struct.pack("<I", 5000) + bytes(4096),
        ):
            with self.assertRaises(ValueError):
                pcm_extent(raw)


if __name__ == "__main__":
    unittest.main()
