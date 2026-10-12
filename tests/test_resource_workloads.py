"""Ensure bounded baseline replay construction preserves and isolates events."""

import tempfile
import unittest
from pathlib import Path

from lab.formats import read_frames
from lab.resource_workloads import EVENTS, fixed_replay, track_one_clip, write_frames


def frame(offset=None, mask=1):
    value = bytearray(512)
    value[0xDE:0xE0] = b"\x01\x00"
    if offset is not None:
        value[offset : offset + 2] = mask.to_bytes(2, "big")
    return bytes(value)


class ResourceWorkloadTests(unittest.TestCase):
    def test_tail_events_cannot_be_repeated(self):
        for offset in EVENTS:
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                fixed_replay([frame(), frame(offset)], 128)

    def test_truncation_cannot_drop_any_event(self):
        for offset in EVENTS:
            raw = [frame()] * 130
            raw[128] = frame(offset)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                fixed_replay(raw, 128)

    def test_padding_preserves_parameters_and_round_trips(self):
        raw = [frame(), frame(0x22), frame()]
        replay = fixed_replay(raw, 128)
        self.assertEqual(replay[:3], raw)
        self.assertEqual(replay[3:], [raw[-1]] * 125)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "frames.dtfr"
            write_frames(path, replay)
            self.assertEqual(read_frames(path), replay)

    def test_isolation_changes_only_event_masks_and_not_source(self):
        raw = [frame()] + [frame(0x22, 7)] + [frame()] * 120
        original = list(raw)
        result = track_one_clip(raw, 1, 128, preroll=32)
        self.assertEqual(raw, original)
        self.assertEqual(result[:32], [raw[0]] * 32)
        self.assertEqual(result[32][0x22:0x24], b"\0\1")
        for offset in range(len(raw[1])):
            if not any(e <= offset < e + 2 for e in EVENTS):
                self.assertEqual(result[32][offset], raw[1][offset])

    def test_missing_trigger_event_preroll_and_bad_bounds_refused(self):
        for raw, start, count, preroll in (
            ([frame()] * 140, 1, 128, 32),
            ([frame(0x24)] + [frame(0x22)] * 140, 1, 128, 32),
            ([frame()] * 140, 0, 128, 32),
            ([frame()] * 140, 20, 128, 1),
            ([frame()] * 140, 1, 128, 128),
        ):
            with (
                self.subTest(start=start, preroll=preroll),
                self.assertRaises(ValueError),
            ):
                track_one_clip(raw, start, count, preroll=preroll)
        for count in (127, 513):
            with self.assertRaises(ValueError):
                fixed_replay([frame()], count)
            with self.assertRaises(ValueError):
                track_one_clip([frame()] + [frame(0x22)] * 600, 1, count)


if __name__ == "__main__":
    unittest.main()
