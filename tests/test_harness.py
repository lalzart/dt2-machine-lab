import hashlib
import math
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lab.formats import read_frames
from lab.metrics import analyze_sine
from lab.project import inside, verify_files


class FixtureIntegrityTests(unittest.TestCase):
    def test_changed_fixture_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.pack"
            path.write_bytes(b"original state")
            expected = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}
            verify_files(directory, expected)
            path.write_bytes(b"different state")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_files(directory, expected)

    def test_fixture_path_cannot_escape(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "escapes"),
        ):
            inside(directory, "../outside")

    def test_checks_survive_optimized_python(self):
        result = subprocess.run(
            [
                sys.executable,
                "-O",
                "-B",
                "-c",
                "from lab.project import require; require(False, 'refused')",
            ],
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refused", result.stderr)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "control.dtfr"
        self.payload = bytes(0x100)
        self.capture = (
            b"DTFR\x01\0\0\0" + struct.pack("<II", 1, len(self.payload)) + self.payload
        )

    def test_roundtrip_real_frame_shape(self):
        self.path.write_bytes(self.capture)
        self.assertEqual(read_frames(self.path), [self.payload])

    def test_malformed_capture_is_refused(self):
        cases = [
            self.capture[:4],
            self.capture[:-1],
            self.capture + b"extra",
            b"DTFR\x01\0\0\0" + struct.pack("<I", 0),
            b"DTFR\x01\0\0\0" + struct.pack("<I", 4097),
        ]
        for data in cases:
            with self.subTest(size=len(data)):
                self.path.write_bytes(data)
                with self.assertRaises(ValueError):
                    read_frames(self.path)


class SignalTests(unittest.TestCase):
    def signal(self, frequency=440, shift=0):
        result = [0.0] * 96000
        for i in range(24000):
            result[151 * 64 + shift + i] = (
                0.125
                * max(0, min(1, i / 480, (24000 - i) / 480))
                * math.sin(2 * math.pi * frequency * i / 96000)
            )
        return result

    def test_reference_passes(self):
        self.assertTrue(analyze_sine(self.signal())["ok"])

    def test_wrong_pitch_and_timing_fail(self):
        for data in (self.signal(880), self.signal(440, -64)):
            with self.assertRaises(ValueError):
                analyze_sine(data)

    def test_nonfinite_and_missing_audio_fail(self):
        bad = self.signal()
        bad[18000] = float("nan")
        for data in (bad, [0.0] * 96000):
            with self.assertRaises(ValueError):
                analyze_sine(data)


if __name__ == "__main__":
    unittest.main()
