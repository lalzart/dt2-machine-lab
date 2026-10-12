"""Capacity, shared-bank lifetime and integer-duration regression gates."""

import ctypes as ct
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "capacity_check", ROOT / "scripts/check-capicola-capacity.py"
)
cap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cap)


class CapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.lib, cls.oracle, cls.old = cap.build(Path(cls.temp.name))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_twelve_seconds_dense_and_exact_capacity(self):
        data = cap.fixture("noise")
        exact = cap.Sample(self.lib, data)
        self.assertEqual(exact.result, 0)
        self.assertGreater(exact.bank.count, 40960)
        self.assertEqual(exact.capacity, exact.bank.count)
        short = cap.Sample(self.lib, data, exact.capacity - 1)
        self.assertEqual(short.result, 2)
        self.assertEqual(short.bank.count, 0)
        self.assertEqual(cap.Reader(short).start(), 2)
        short.guards()

    def test_input_limits_and_invalid_measurement(self):
        sample = cap.Sample(self.lib, [0.0] * 576000)
        self.assertEqual(sample.result, 0)
        for bad in [[], [0.0] * 576001, [float("nan")], [float("inf")], [1.01]]:
            data = cap.pcm_array(bad)
            self.assertEqual(self.lib.cap_measure(data, len(data)), -1)
            self.assertEqual(
                self.lib.cap_load(ct.byref(sample.bank), data, len(data)), 1
            )
            self.assertEqual(sample.bank.count, 0)
        one = cap.Sample(self.lib, [0.5])
        reader = cap.Reader(one)
        self.assertEqual(reader.start(), 0)
        reader.render(20)
        self.assertEqual(reader.state.position, 1)

    def test_shared_bank_readers_and_reload_invalidation(self):
        data = cap.fixture("sine", 10000)
        sample = cap.Sample(self.lib, data)
        a, b = cap.Reader(sample), cap.Reader(sample)
        a.start(1.1, 0.7)
        expected = a.render(2000)
        a.start(1.1, 0.7)
        original = sample.payload()
        b.start(0.5, 2)
        b.render(1700)
        self.assertEqual(a.render(2000), expected)
        self.assertEqual(sample.payload(), original)
        # Failed replacement invalidates both voices before any stale read.
        self.assertEqual(self.lib.cap_load(ct.byref(sample.bank), None, 0), 1)
        pa, pb = a.state.position, b.state.position
        self.assertEqual(a.render(128), bytes(512))
        self.assertEqual(b.render(128), bytes(512))
        self.assertEqual((a.state.position, b.state.position), (pa, pb))
        self.assertEqual(
            self.lib.cap_load(ct.byref(sample.bank), cap.pcm_array(data), len(data)), 0
        )
        self.assertEqual(a.render(128), bytes(512))
        self.assertEqual(a.start(1.1, 0.7), 0)
        self.assertEqual(a.render(2000), expected)

    def test_control_failures_stop_and_bank_bind_fail_closed(self):
        sample = cap.Sample(self.lib, cap.fixture("drums", 1000))
        reader = cap.Reader(sample)
        for values in [
            (float("nan"), 1, 128),
            (1, float("inf"), 128),
            (0.49, 1, 128),
            (1, 1, 129),
        ]:
            self.assertEqual(reader.start(*values), 3)
            self.assertEqual(reader.render(64), bytes(256))
        reader.start()
        reader.render(123)
        self.lib.cap_stop(ct.byref(reader.state))
        self.assertEqual(reader.render(64), bytes(256))
        self.assertEqual(reader.state.position, 123)
        reader.start()
        self.assertEqual(
            self.lib.cap_bank_bind(ct.byref(sample.bank), None, None, None, 480005), 1
        )
        self.assertEqual(reader.render(64), bytes(256))
        empty = cap.State()
        self.lib.cap_init(ct.byref(empty))
        self.assertEqual(self.lib.cap_start(ct.byref(empty), 1, 1, 128), 1)

    def test_long_duration_boundaries_and_old_overflow(self):
        for frames in [1, 47999, 48000, 262144, 575999, 576000]:
            for rate in [0.5, 0.7, 1, 1.1, 2]:
                rate = ct.c_float(rate).value
                self.assertEqual(
                    self.lib.cap_test_duration(frames, int(rate * 2**24)),
                    math.ceil(frames / rate),
                )
        old_product = ((8192 * 960000) & 0xFFFFFFFF) >> 12
        self.assertNotEqual(old_product, 1920000)
