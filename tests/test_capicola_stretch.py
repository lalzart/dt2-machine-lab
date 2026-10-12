"""Transport bounds and live-state continuity, independent of firmware fixtures."""

import ctypes as ct
import importlib.util
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "stretch_check", ROOT / "scripts/check-capicola-stretch.py"
)
stretch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stretch)


class StretchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.lib = stretch.build(Path(cls.temp.name))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def sample(self):
        return stretch.capacity.Sample(
            self.lib, [0.8 * math.sin(i * 0.1) for i in range(1024)]
        )

    def test_duration_counts_output_without_expanding_source_memory(self):
        sample = self.sample()
        for rate in (0.0002, 0.03125, 0.7, 64):
            state = stretch.start(self.lib, sample, (0, 1024), 0, 0, 32, rate)
            q = int(ct.c_float(rate).value * 2**24)
            self.assertEqual(state.core.duration, (1024 * 2**24 + q - 1) // q)
        state = stretch.Stretch()
        self.assertNotEqual(
            self.lib.cap_stretch_start(
                ct.byref(state), ct.byref(sample.bank), 0, 1024, 0, 0, 1, 1 / 65536, 128
            ),
            0,
        )
        self.assertFalse(state.core.active)
        self.assertEqual(sample.bank.frames, 1024)

    def test_loop_wrap_and_negative_cursor_match_independent_model(self):
        sample = self.sample()
        for reverse in (0, 1):
            state = stretch.start(self.lib, sample, (100, 149), reverse, 1, 0.03125, 64)
            reference = stretch.model(sample, (100, 149), reverse, 1, 0.03125, 64)
            for _ in range(8):
                stretch.compare(
                    stretch.process(self.lib, state, 1024), reference.process(1024)
                )
                self.assertLess(state.core.ideal_w, 49)
                self.assertLess(state.core.actual_w, 0)
                self.assertEqual(state.core.position, 48)
            sample.guards()

    def test_live_update_preserves_splice_and_positions(self):
        sample = self.sample()
        state = stretch.start(self.lib, sample, (0, 1024), 0, 1, 32, 0.03125)
        stretch.process(self.lib, state, 1024)
        before = (
            state.core.actual_w,
            state.core.actual_f,
            state.core.ideal_w,
            state.core.ideal_f,
            state.core.phase,
            state.core.splicing,
        )
        self.assertEqual(self.lib.cap_stretch_update(ct.byref(state), 0.5, 2), 0)
        after = (
            state.core.actual_w,
            state.core.actual_f,
            state.core.ideal_w,
            state.core.ideal_f,
            state.core.phase,
            state.core.splicing,
        )
        self.assertEqual(before, after)
        self.assertEqual(state.core.pitch_q, 2**23)
        self.assertEqual(state.core.advance_q, 2**25)

    def test_unused_incoming_cursor_cannot_accumulate_loop_periods(self):
        sample = self.sample()
        state = stretch.start(self.lib, sample, (100, 149), 0, 1, 32, 32)
        stretch.process(self.lib, state, 16384)
        self.assertFalse(state.core.splicing)
        self.assertEqual(state.core.incoming_w, state.core.actual_w)
        self.assertLess(state.core.incoming_w, 49)

    def test_generation_invalidates_before_null_storage_is_read(self):
        sample = self.sample()
        state = stretch.start(self.lib, sample, (0, 1024), 1, 1, 1, 1)
        sample.bank.generation += 1
        sample.bank.value = ct.POINTER(ct.c_float)()
        self.assertEqual(stretch.process(self.lib, state, 128), [0.0] * 128)
        self.assertFalse(state.core.active)
