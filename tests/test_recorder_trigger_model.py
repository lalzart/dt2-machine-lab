"""Trigger-independent request identity and explicit musical boundary controls."""

import unittest
from dataclasses import asdict

from lab.recorder_gestures import Context, Gestures
from lab.recorder_trigger_model import ArmRequests

SETTINGS = bytes(range(36))
ARGS = dict(epoch=1, kit=123, destination=2, settings=SETTINGS)


class RequestTests(unittest.TestCase):
    def model(self):
        q = ArmRequests()
        q.boundary(10, epoch=1, clock=7)
        return q

    def test_both_triggers_produce_the_identical_backend_receipt(self):
        receipts = []
        for _trigger in ("double", "chord"):
            q = self.model()
            self.assertEqual(q.request(**ARGS), "armed")
            self.assertIsNone(q.boundary(10, epoch=1, clock=7))
            receipts.append(q.boundary(11, epoch=1, clock=7))
            self.assertEqual(q.state, "would-record")
            self.assertIsNone(q.boundary(11, epoch=1, clock=7))
            self.assertIsNone(q.boundary(12, epoch=1, clock=7))
        self.assertEqual(receipts[0], receipts[1])
        self.assertNotIn("trigger", asdict(receipts[0]))

    def test_unprimed_clock_cannot_turn_a_first_observation_into_start(self):
        q = ArmRequests()
        self.assertEqual(q.request(**ARGS), "unclocked")
        self.assertIsNone(q.boundary(100, epoch=1, clock=7))
        self.assertEqual(q.state, "idle")
        self.assertEqual(q.request(**ARGS), "armed")
        self.assertIsNotNone(q.boundary(101, epoch=1, clock=7))

    def test_missed_boundary_and_clock_restart_cancel_instead_of_starting_late(self):
        for index, clock in ((12, 7), (0, 8)):
            q = self.model()
            q.request(**ARGS)
            self.assertIsNone(q.boundary(index, epoch=1, clock=clock))
            self.assertEqual(q.state, "idle")

    def test_stale_epoch_bar_cannot_cancel_or_start_the_current_request(self):
        q = self.model()
        q.request(**ARGS)
        plan = q.plan
        self.assertIsNone(q.boundary(11, epoch=0, clock=7))
        self.assertEqual(q.plan, plan)
        self.assertIs(q.boundary(11, epoch=1, clock=7), plan)

    def test_repeat_request_cancels_without_issuing_a_second_ticket(self):
        q = self.model()
        q.request(**ARGS)
        self.assertEqual(q.request(**ARGS), "canceled")
        self.assertEqual(q.serial, 1)
        self.assertIsNone(q.boundary(11, epoch=1, clock=7))
        q.request(**ARGS)
        self.assertEqual(q.serial, 2)

    def test_latched_settings_own_their_bytes(self):
        settings = bytearray(SETTINGS)
        q = self.model()
        q.request(**(ARGS | dict(settings=settings)))
        settings[0] = 255
        self.assertEqual(q.plan.settings, SETTINGS)

    def test_normal_is_stock_and_does_not_mutate_a_pending_request(self):
        q = self.model()
        q.request(**ARGS)
        plan = q.plan
        self.assertEqual(q.request(**(ARGS | dict(destination=0))), "stock")
        self.assertIs(q.plan, plan)

    def test_busy_request_and_bad_shape_are_refused(self):
        q = self.model()
        with self.assertRaises(ValueError):
            q.request(**(ARGS | dict(settings=bytes(32))))
        for values in (dict(epoch=0), dict(kit=0), dict(destination=5)):
            self.assertEqual(q.request(**(ARGS | values)), "refused")
        q.request(**ARGS)
        q.boundary(11, epoch=1, clock=7)
        self.assertEqual(q.request(**ARGS), "busy")

    def test_context_and_project_barriers(self):
        for values in (
            dict(epoch=2),
            dict(kit=124),
            dict(destination=3),
            dict(busy=True),
        ):
            q = self.model()
            q.request(**ARGS)
            self.assertFalse(
                q.validate(**(dict(epoch=1, kit=123, destination=2) | values))
            )
            self.assertIsNone(q.boundary(11, epoch=1, clock=7))
        q = self.model()
        q.request(**ARGS)
        q.project(2)
        self.assertIsNone(q.clock)
        self.assertIsNone(q.boundary(11, epoch=1, clock=7))

    def test_cancel_is_a_stop_barrier(self):
        q = self.model()
        q.request(**ARGS)
        q.cancel()
        self.assertIsNone(q.boundary(11, epoch=1, clock=7))


class ChordOnlyGestureTests(unittest.TestCase):
    def test_chord_only_releases_immediately_but_still_recognizes_freeze_hold(self):
        ctx = Context(destination=1, kit=123, owner=456, performance=True)
        g = Gestures(double_enabled=False)
        g.sampling(0, 1, ctx)
        self.assertFalse(g.sampling(6, 16, ctx).consume)
        self.assertIsNone(g.pending)
        g.sampling(12, 5, ctx)
        self.assertFalse(g.sampling(18, 16, ctx).consume)
        g.sampling(30, 1, ctx)
        self.assertEqual(g.poll(94, ctx)[0].kind, "would-freeze")

    def test_default_double_arbitration_remains_enabled(self):
        ctx = Context(destination=1, kit=123, owner=456, performance=True)
        g = Gestures()
        g.sampling(0, 1, ctx)
        self.assertTrue(g.sampling(6, 16, ctx).consume)
        self.assertEqual(g.sampling(12, 5, ctx).effects[0].kind, "would-arm")


if __name__ == "__main__":
    unittest.main()
