"""Dry-input ordering and failures; effects cannot invoke an audio backend."""

import unittest
from dataclasses import replace

from lab.recorder_gestures import Context, Gestures

BUF = Context(destination=1, kit=123, owner=456, performance=True)
RELEASE = bytes(range(24))


class GestureTests(unittest.TestCase):
    def first(self, g, *, context=BUF, up=7):
        self.assertFalse(g.sampling(0, 1, context).consume)
        self.assertTrue(g.sampling(up, 16, context, RELEASE).consume)

    def test_single_waits_from_first_press_not_from_release(self):
        g = Gestures()
        self.first(g)
        self.assertEqual(g.poll(31, BUF), ())
        (effect,) = g.poll(32, BUF)
        self.assertEqual(
            (effect.kind, effect.payload, effect.released_at), ("single", RELEASE, 7)
        )
        self.assertEqual(g.poll(100, BUF), ())

    def test_double_wins_and_consumes_releases_and_second_hold(self):
        g = Gestures()
        self.first(g)
        result = g.sampling(14, 5, BUF)
        self.assertTrue(result.consume)
        self.assertEqual([e.kind for e in result.effects], ["would-arm"])
        self.assertEqual(g.poll(100, BUF), ())
        self.assertTrue(g.sampling(110, 0x2D, BUF).consume)
        self.assertTrue(g.sampling(111, 16, BUF).consume)
        self.assertEqual(g.poll(120, BUF), ())

    def test_fast_and_exact_window_boundary(self):
        g = Gestures()
        self.first(g)
        self.assertEqual(g.sampling(31, 1, BUF).effects[0].kind, "would-arm")
        g = Gestures()
        self.first(g)
        result = g.sampling(32, 5, BUF)
        self.assertFalse(result.consume)
        self.assertEqual([e.kind for e in result.effects], ["single"])

    def test_longer_short_press_is_immediate_and_hold_fires_once(self):
        g = Gestures()
        g.sampling(0, 1, BUF)
        self.assertFalse(g.sampling(40, 16, BUF).consume)
        self.assertIsNone(g.pending)
        g.sampling(50, 1, BUF)
        self.assertEqual(g.poll(113, BUF), ())
        (effect,) = g.poll(114, BUF)
        self.assertEqual(effect.kind, "would-freeze")
        self.assertEqual(g.poll(300, BUF), ())
        self.assertTrue(g.sampling(301, 0x49, BUF).consume)
        self.assertTrue(g.sampling(302, 16, BUF).consume)

    def test_repeat_or_duplicate_down_is_not_a_second_press(self):
        g = Gestures()
        g.sampling(0, 1, BUF)
        self.assertEqual(g.sampling(1, 1, BUF).effects, ())
        self.assertEqual(g.sampling(24, 9, BUF).effects, ())
        self.assertEqual(g.sampling(32, 9, BUF).effects, ())
        self.assertEqual(g.sampling(64, 41, BUF).effects[0].kind, "would-freeze")

    def test_triple_tap_does_not_open_recorder_after_double(self):
        g = Gestures()
        self.first(g)
        g.sampling(14, 5, BUF)
        g.sampling(21, 16, BUF)
        self.assertTrue(g.sampling(28, 5, BUF).consume)
        self.assertTrue(g.sampling(35, 16, BUF).consume)
        self.assertEqual(g.poll(90, BUF), ())

    def test_encoder_during_hold_keeps_performance_but_after_tap_flushes(self):
        g = Gestures()
        g.sampling(0, 1, BUF)
        self.assertEqual(g.encoder(20, BUF), ())
        self.assertEqual(g.poll(64, BUF)[0].kind, "would-freeze")
        g = Gestures()
        self.first(g)
        (effect,) = g.encoder(10, BUF)
        self.assertEqual(
            (effect.kind, effect.tick, effect.released_at), ("single", 10, 7)
        )
        self.assertEqual(g.poll(100, BUF), ())

    def test_chord_or_stop_cancels_intent_and_swallows_owned_release(self):
        g = Gestures()
        g.sampling(0, 1, BUF)
        g.cancel(10)
        self.assertEqual(g.poll(64, BUF), ())
        self.assertTrue(g.sampling(70, 16, BUF).consume)
        g = Gestures()
        self.first(g)
        g.cancel(10)
        self.assertEqual(g.poll(100, BUF), ())

    def test_normal_modifiers_modal_busy_and_recorder_states_passthrough(self):
        for ctx in (
            replace(BUF, destination=0),
            replace(BUF, destination=5),
            replace(BUF, performance=False),
            replace(BUF, owner=0),
            replace(BUF, busy=True),
            *(replace(BUF, recorder_state=n) for n in (1, 2, 3, 4)),
        ):
            with self.subTest(context=ctx):
                g = Gestures()
                self.assertFalse(g.sampling(0, 1, ctx).consume)
                self.assertEqual(g.poll(64, ctx), ())
                self.assertFalse(g.sampling(70, 16, ctx).consume)
        g = Gestures()
        self.assertFalse(g.sampling(0, 3, BUF).consume)
        self.assertFalse(g.sampling(7, 18, BUF).consume)

    def test_epoch_destination_owner_and_busy_changes_cancel_deferred_work(self):
        for ctx in (
            replace(BUF, epoch=2),
            replace(BUF, kit=124),
            replace(BUF, owner=457),
            replace(BUF, destination=2),
            replace(BUF, recorder_state=2),
            replace(BUF, busy=True),
        ):
            with self.subTest(context=ctx):
                g = Gestures()
                self.first(g)
                self.assertEqual(g.poll(32, ctx), ())
                self.assertIsNone(g.pending)
                g = Gestures()
                g.sampling(0, 1, BUF)
                self.assertEqual(g.poll(64, ctx), ())
                self.assertTrue(g.sampling(70, 16, ctx).consume)

    def test_consumed_stock_release_never_becomes_navigation(self):
        g = Gestures()
        g.sampling(0, 1, BUF)
        self.assertTrue(g.sampling(7, 0, BUF).consume)
        self.assertEqual(g.poll(100, BUF), ())

    def test_modified_chord_release_remains_stock_after_cancellation(self):
        g = Gestures()
        g.sampling(0, 1, BUF)
        g.cancel(10)
        self.assertFalse(g.sampling(20, 18, BUF).consume)
        self.assertEqual(g.poll(100, BUF), ())

    def test_context_change_clears_triple_tap_cooldown(self):
        g = Gestures()
        self.first(g)
        g.sampling(14, 5, BUF)
        g.sampling(21, 16, BUF)
        other = replace(BUF, destination=2)
        self.assertFalse(g.sampling(25, 1, other).consume)
        self.assertEqual(g.mode, "first")

    def test_monotonic_clock_and_threshold_validation(self):
        with self.assertRaises(ValueError):
            Gestures(double_ticks=64, hold_ticks=32)
        g = Gestures()
        g.poll(100, BUF)
        with self.assertRaisesRegex(ValueError, "Unwrap"):
            g.poll(1, BUF)


if __name__ == "__main__":
    unittest.main()
