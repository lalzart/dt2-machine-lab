"""Bounds and lifecycle tests for the isolated AGPL Capicola source experiment."""

import array
import ctypes as ct
import importlib.util
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "capicola_check", ROOT / "scripts/check-capicola.py"
)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


@unittest.skipUnless(shutil.which("clang"), "Host core checks require clang")
class CapicolaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / "core.dylib"
        subprocess.run(
            [
                "clang",
                "-std=c99",
                "-O2",
                "-ffp-contract=off",
                "-shared",
                str(ROOT / "machines/capicola/core.c"),
                "-o",
                str(lib),
            ],
            check=True,
        )
        cls.lib = ct.CDLL(str(lib))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.engine = check.Engine(self.lib, "cap")

    def test_output_bounds_and_terminal_silence(self):
        e = self.engine
        self.assertEqual(e.load(array.array("f", [0.25] * 100)), 0)
        self.assertEqual(e.call("start", 1, 0.7, 128), 0)
        # Float32 control semantics, not Python decimal arithmetic.
        duration = math.ceil(100 / ct.c_float(0.7).value)
        out = (ct.c_float * (duration + 20))(*([123.0] * (duration + 20)))
        target = ct.cast(ct.byref(out, 4), ct.POINTER(ct.c_float))
        e.call("process", target, duration + 10)
        self.assertEqual(out[0], 123.0)
        self.assertEqual(out[duration + 11], 123.0)
        self.assertTrue(all(v == 0 for v in out[duration + 1 : duration + 11]))
        self.assertEqual(e.call("position"), duration)
        self.assertTrue(all(abs(v) <= 0.25 for v in out[1 : duration + 1]))

    def test_invalid_load_clears_prior_sample(self):
        e = self.engine
        for x in [[], [float("nan")], [float("inf")], [-1.01], [0.0] * 48001]:
            self.assertEqual(e.load([0.5] * 100), 0)
            self.assertEqual(e.call("start", 1, 1, 128), 0)
            self.assertEqual(e.load(x), 1)
            self.assertEqual(e.call("count"), 0)
            self.assertNotEqual(e.call("start", 1, 1, 128), 0)
            self.assertEqual(e.render(32), bytes(128))

    def test_dense_input_overflow_is_atomic_and_recoverable(self):
        e = self.engine
        self.assertEqual(e.load(check.generate("noise", 48000, 1)), 2)
        self.assertEqual(e.call("count"), 0)
        self.assertEqual(e.render(100), bytes(400))
        self.assertEqual(e.load(check.generate("sine", 1000, 1)), 0)
        self.assertEqual(e.call("start", 1, 1, 128), 0)
        self.assertNotEqual(e.render(1000), bytes(4000))

    def test_decimal_rates_reset_and_partition(self):
        e = self.engine
        self.assertEqual(e.load(check.generate("sine", 4800, 1)), 0)
        self.assertEqual(e.call("start", 1.1, 0.7, 64), 0)
        expected = e.render(7000, 64)
        self.assertEqual(e.call("start", 1.1, 0.7, 64), 0)
        self.assertEqual(e.render(7000, 1), expected)

    def test_stop_does_not_advance_or_leak(self):
        e = self.engine
        e.load(check.generate("sine", 4800, 1))
        e.call("start", 1, 1, 128)
        e.render(200)
        e.call("stop")
        self.assertEqual(e.render(100), bytes(400))
        self.assertEqual(e.call("position"), 200)

    def test_invalid_control_is_silent_and_valid_start_recovers(self):
        e = self.engine
        e.load(check.generate("sine", 4800, 1))
        for controls in [
            (float("nan"), 1, 128),
            (1, float("inf"), 128),
            (0.1, 1, 128),
            (1, 1, 129),
        ]:
            self.assertEqual(e.call("start", *controls), 3)
            self.assertEqual(e.render(100), bytes(400))
        self.assertEqual(e.call("start", 1, 1, 128), 0)
        self.assertNotEqual(e.render(1000), bytes(4000))
