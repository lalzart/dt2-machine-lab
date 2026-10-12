"""Live edits must preserve steady playback and stop safely across bank retirement."""

import ctypes as ct
import importlib.util
import itertools
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "live_check", ROOT / "scripts/check-capicola-stretch-live.py"
)
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / "live").mkdir()
        (root / "old").mkdir()
        cls.lib = live.build(root / "live")
        cls.old = live.base.build(root / "old")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def sample(self):
        return live.base.capacity.Sample(
            self.lib, [0.8 * math.sin(i * 0.1) for i in range(1024)]
        )

    def test_unchanged_controls_preserve_previous_c_reader_exactly(self):
        sample = self.sample()
        for reverse, loop in itertools.product((0, 1), repeat=2):
            current = live.start(self.lib, sample, reverse, loop, 2, 0.5)
            old = live.base.start(self.old, sample, (0, 1024), reverse, loop, 2, 0.5)
            for _ in range(8):
                self.assertEqual(
                    live.update(self.lib, current, (0, 1024), reverse, loop, 2, 0.5),
                    0,
                )
                self.assertEqual(
                    live.process(self.lib, current, 128),
                    live.base.process(self.old, old, 128),
                )

    def test_trim_clamps_absolute_position_before_reversing(self):
        sample = self.sample()
        state = live.start(self.lib, sample, 0, 1, 1, 0.5)
        live.process(self.lib, state, 128)  # Absolute ideal position is 64.
        self.assertEqual(live.update(self.lib, state, (200, 600), 1, 1, 1, 0.5), 0)
        # Clamped absolute 200 becomes reverse-relative 599 - 200 = 399.
        self.assertEqual(
            (state.current.core.ideal_w, state.current.core.ideal_f), (399, 0)
        )
        self.assertEqual(state.outgoing.core.ideal_w, 64)
        self.assertEqual(state.fade_left, 64)
        live.process(self.lib, state, 64)
        self.assertEqual(state.fade_left, 0)
        self.assertFalse(state.outgoing.core.active)

    def test_latest_queue_can_be_cancelled_and_trigger_discards_it(self):
        sample = self.sample()
        state = live.start(self.lib, sample)
        live.process(self.lib, state, 128)
        live.update(self.lib, state, (200, 600), 1, 1, 1, 1)
        live.process(self.lib, state, 7)
        live.update(self.lib, state, (400, 900), 0, 1, 2, 0.5)
        self.assertTrue(state.pending)
        live.update(self.lib, state, (200, 600), 1, 1, 2, 0.5)
        self.assertFalse(state.pending)
        live.process(self.lib, state, 128)
        self.assertEqual((state.current.start, state.current.end), (200, 600))
        live.update(self.lib, state, (400, 900), 0, 1, 2, 0.5)
        live.update(self.lib, state, (100, 500), 1, 1, 2, 0.5)
        self.assertTrue(state.pending)
        self.assertEqual(
            self.lib.cap_live_start(
                ct.byref(state), ct.byref(sample.bank), 0, 1024, 0, 1, 1, 1, 128
            ),
            0,
        )
        fresh = live.start(self.lib, sample)
        self.assertEqual(
            live.process(self.lib, state, 256), live.process(self.lib, fresh, 256)
        )

    def test_retired_bank_stops_both_readers_before_null_storage_access(self):
        sample = self.sample()
        state = live.start(self.lib, sample)
        live.process(self.lib, state, 128)
        live.update(self.lib, state, (200, 600), 1, 1, 1, 1)
        sample.bank.generation += 1
        sample.bank.value = ct.POINTER(ct.c_float)()
        self.assertEqual(live.process(self.lib, state, 128), [0.0] * 128)
        self.assertFalse(state.current.core.active)
        self.assertFalse(state.outgoing.core.active)
        self.assertEqual(state.fade_left, 0)

    def test_completed_finite_note_stays_silent_after_valid_edit(self):
        sample = self.sample()
        state = live.start(self.lib, sample, 0, 0, 1, 32)
        live.process(self.lib, state, 128)
        self.assertFalse(state.current.core.active)
        self.assertEqual(live.update(self.lib, state, (100, 900), 1, 1, 1, 1), 0)
        self.assertEqual(live.process(self.lib, state, 128), [0.0] * 128)
