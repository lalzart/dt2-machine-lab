"""Musical scheduling and epoch failures without pretending to bind a key."""

import unittest

from lab.flex_quick_record import QuickRecord


class QuickRecordTests(unittest.TestCase):
    def test_arm_latches_source_waits_bar_and_only_commits_complete_audio(self):
        q = QuickRecord()
        self.assertEqual(
            q.gesture(destination=2, playing=True, source=9, channel=1, bars=2), "armed"
        )
        ticket = q.plan
        self.assertEqual(q.state, "armed")
        self.assertIsNone(q.bar(100, epoch=0))
        self.assertEqual(q.bar(12, epoch=1), ("start", ticket))
        self.assertIsNone(q.bar(13, epoch=1))
        self.assertEqual(q.gesture(destination=4, playing=True), "busy")
        self.assertEqual((q.plan.source, q.plan.destination), (9, 2))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            q.published(ticket, complete=True)
        self.assertEqual(q.bar(14, epoch=1), ("stop", ticket))
        q.captured(ticket)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            q.published(ticket, complete=False)
        self.assertEqual(q.state, "publishing")
        self.assertEqual(q.published(ticket, complete=True), ticket)
        self.assertEqual(q.state, "idle")

    def test_rearm_stop_and_project_change_cannot_publish_stale_tickets(self):
        q = QuickRecord()
        self.assertEqual(q.gesture(destination=1, playing=False), "stopped")
        self.assertEqual(q.gesture(destination=1, playing=True), "armed")
        old = q.plan
        self.assertEqual(q.gesture(destination=1, playing=True), "canceled")
        self.assertIsNone(q.bar(1, epoch=1))
        q.gesture(destination=1, playing=True)
        self.assertNotEqual(q.plan, old)
        q.bar(2, epoch=1)
        q.cancel()  # STOP discards unfinished capture.
        with self.assertRaises(ValueError):
            q.captured(old)
        q.gesture(destination=1, playing=True)
        ticket = q.plan
        q.bar(3, epoch=1)
        q.bar(4, epoch=1)
        q.captured(ticket)
        q.project_change()
        with self.assertRaises(ValueError):
            q.published(ticket, complete=True)
        self.assertIsNone(q.bar(5, epoch=1))

    def test_normal_delegates_without_changing_pending_buffer(self):
        q = QuickRecord()
        q.gesture(destination=1, playing=True)
        ticket = q.plan
        self.assertEqual(q.gesture(destination=0, playing=True), "stock")
        self.assertEqual(q.plan, ticket)
        self.assertEqual(q.state, "armed")


if __name__ == "__main__":
    unittest.main()
