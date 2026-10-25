"""Check panel stimulus routing without substituting any recorder operation."""

import types
import unittest

from lab.type7a_matrix import recording_session


class StimulusTests(unittest.TestCase):
    def test_buf_selects_target_through_original_panel_and_normal_stays_stock(self):
        class Original:
            def __init__(self, destination):
                self.flex = types.SimpleNamespace(destination=destination)
                self.calls = []

            def chord(self, modifier, name):
                self.calls.append((modifier, name))

            def tap(self, name):
                self.calls.append((name,))

        for destination in range(5):
            events = []
            session = recording_session(Original, events)(destination)
            session.tap("YES")
            self.assertEqual(session.calls, [("YES",)])
            session.tap("SAMPLING")
            expected = [("YES",)]
            if destination:
                expected.append(("TRK", "TRIG 1"))
            expected.append(("SAMPLING",))
            self.assertEqual(session.calls, expected)
            self.assertEqual(events, [dict(destination=destination,
                                          selected_t1=bool(destination))])
