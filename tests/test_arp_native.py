"""Native state/lifecycle tests against frozen musical expectations."""
import math
import unittest

from lab import arp_native as native
from lab.arp_emulation import NativeCore


class ArpNativeTests(unittest.TestCase):
    def test_up_sorts_reverse_input_and_preserves_rational_phase(self):
        c = NativeCore()
        for note in (67, 64, 60):
            self.assertEqual(c.call("press", note, 100), (0, []))
        c.call("clock", 0, 1)
        events = []
        for tick in range(32, 80_001, 32):
            events += [(tick, *e) for e in c.call("clock", tick, 1)[1]]
        on = [e for e in events if e[1] == "on"]
        self.assertEqual([e[2] for e in on], [60, 64, 67] * 3 + [60, 64])
        for index, event in enumerate(on, 1):
            deadline = math.ceil(index * native.STEP / native.UNITS_PER_SAMPLE)
            self.assertTrue(0 <= event[0] - deadline <= 31)
        self.assertEqual(c.field("phase"), (80_000 * 408) % native.STEP)
        # The eleventh gate ends after this capture, at >81k samples.
        self.assertEqual([e[1] for e in events], ["on", "off"] * 10 + ["on"])

    def test_duplicate_pitch_needs_both_releases(self):
        c = NativeCore()
        c.call("press", 60, 70); c.call("press", 60, 100)
        c.call("clock", 0, 1)
        self.assertEqual(c.call("clock", 7060, 1)[1], [("on", 60, 100)])
        self.assertEqual(c.call("release", 60)[1], [])
        self.assertEqual(c.field("held"), 1)
        self.assertEqual(c.call("release", 60)[1], [("off", 60, 0)])
        self.assertEqual(c.field("owned"), 0)
        self.assertEqual(c.call("clock", 14120, 1)[1], [])

    def test_removed_active_note_releases_and_next_selection_advances(self):
        c = NativeCore()
        for n in (60, 64, 67): c.call("press", n, 90)
        c.call("clock", 0, 1); c.call("clock", 7060, 1)
        self.assertEqual(c.call("release", 60)[1], [("off", 60, 0)])
        self.assertEqual(c.call("clock", 14120, 1)[1], [("on", 64, 90)])

    def test_stop_clears_arp_but_consumes_later_physical_release(self):
        c = NativeCore(); c.call("press", 60, 100)
        c.call("clock", 0, 1); c.call("clock", 7060, 1)
        self.assertEqual(c.call("clock", 7100, 0)[1], [("off", 60, 0)])
        self.assertEqual(c.field("held"), 0)
        self.assertEqual(c.field("owned"), 1)
        c.call("clock", 8000, 1)
        self.assertEqual(c.call("clock", 16000, 1)[1], [])
        self.assertEqual(c.call("release", 60)[1], [])
        self.assertEqual(c.field("owned"), 0)

    def test_disable_is_silent_and_old_release_does_not_start_stock_note(self):
        c = NativeCore(); c.call("press", 60, 100)
        c.call("clock", 0, 1); c.call("clock", 7060, 1)
        self.assertEqual(c.call("mode", 0)[1], [("off", 60, 0)])
        self.assertEqual(c.call("clock", 15000, 1)[1], [])
        self.assertEqual(c.call("release", 60)[1], [])
        self.assertEqual(c.field("owned"), 0)
        c.call("press", 64, 90)
        self.assertEqual(c.field("held"), 0)

    def test_capacity_and_invalid_arguments_leave_bytes_unchanged(self):
        c = NativeCore()
        for _ in range(16): c.call("press", 60, 100)
        for name, args in [("press", (64, 100)), ("press", (128, 100)),
                           ("press", (60, 0)), ("release", (128,)),
                           ("mode", (2,)), ("clock", (10, 2))]:
            before = c.raw()
            self.assertEqual(c.call(name, *args)[0], 0xFFFFFFFF)
            self.assertEqual(c.raw(), before)

    def test_tick_wrap_and_range_endpoints(self):
        start = 0xFFFFF000
        c = NativeCore(start)
        c.call("press", 127, 127); c.call("press", 0, 1)
        c.call("clock", start, 1)
        self.assertEqual(c.call("clock", (start + 7060) & 0xFFFFFFFF, 1)[1],
                         [("on", 0, 1)])
        self.assertEqual(c.call("clock", (start + 14120) & 0xFFFFFFFF, 1)[1],
                         [("off", 0, 0), ("on", 127, 127)])

    def test_overdue_clock_panics_without_catchup_burst(self):
        c = NativeCore(); c.call("press", 60, 100)
        c.call("clock", 0, 1); c.call("clock", 7060, 1)
        self.assertEqual(c.call("clock", 60000, 1)[1], [("off", 60, 0)])
        self.assertEqual(c.field("held"), 0)
        self.assertEqual(c.field("owned"), 1)

    def test_short_late_service_drops_excess_deadlines(self):
        c = NativeCore(); c.call("press", 60, 100)
        c.call("clock", 0, 1)
        self.assertEqual(c.call("clock", 40000, 1)[1], [("on", 60, 100)])
        self.assertLess(c.field("phase"), native.STEP)
        self.assertEqual(c.call("clock", 40001, 1)[1], [])

    def test_reset_and_repeated_sequence_are_byte_exact(self):
        def sequence(c):
            c.call("press", 67, 100); c.call("press", 60, 90)
            c.call("clock", 0, 1)
            rows = [c.call("clock", t, 1)[1] for t in range(32, 32001, 32)]
            return rows, c.raw()
        c = NativeCore()
        first = sequence(c)
        c.call("init", 0, 1)
        self.assertEqual(sequence(c), first)
        c.call("init", 0, 1)
        self.assertEqual(c.raw(), NativeCore().raw())


if __name__ == "__main__":
    unittest.main()
