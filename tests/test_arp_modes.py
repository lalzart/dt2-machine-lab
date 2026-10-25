"""Frozen mode vectors, release/order ownership and four-mode ABI checks."""
import struct
import unittest

from lab import arp_modes as native
from lab.arp_emulation import STATE
from lab.arp_modes_emulation import ModesCore
from lab.coldfire import audit_code


def phrase(mode, notes=(67, 64, 60)):
    c = ModesCore(enabled=mode)
    for note in notes:
        c.call("press", note, 100)
    c.call("clock", 0, 1)
    events = []
    for tick in range(32, 60_001, 32):
        events.extend(c.call("clock", tick, 1)[1])
    return c, events


class ArpModesTests(unittest.TestCase):
    def test_frozen_mode_vectors_and_exact_repeat(self):
        for mode, expected in ((1, [60,64,67,60,64,67,60,64]),
                               (2, [67,64,60,67,64,60,67,64]),
                               (3, [64,64,60,60,60,64,67,60])):
            a, events = phrase(mode)
            b, repeated = phrase(mode)
            self.assertEqual([e[1] for e in events if e[0] == "on"], expected)
            self.assertEqual(events, repeated)
            self.assertEqual(a.raw(), b.raw())

    def test_order_duplicates_release_and_repress(self):
        c = ModesCore(enabled=2)
        for n in (67,64,60,67): c.call("press", n, 90)
        self.assertEqual(c.call("select")[0], 67)
        c.call("release", 67)
        self.assertEqual(c.call("select")[0], 64)
        c.call("release", 67); c.call("press", 67, 100)
        self.assertEqual([c.call("select")[0] for _ in range(4)], [60,67,64,60])

    def test_random_uses_unique_pitches_and_restart_seed(self):
        for notes in ((67,64,60), (67,64,60,67,64,60)):
            c, events = phrase(3, notes)
            self.assertEqual([e[1] for e in events if e[0] == "on"], [64,64,60,60,60,64,67,60])
            c.call("panic")
            self.assertEqual(c.field("rng"), native.SEED)

    def test_mode_change_closes_gate_keeps_release_owners(self):
        for mode in (0,2,3):
            c = ModesCore(); c.call("press",60,100)
            c.call("clock",0,1); c.call("clock",7060,1)
            self.assertEqual(c.call("mode",mode)[1], [("off",60,0)])
            self.assertEqual(c.field("held"),0)
            self.assertEqual(c.field("owned"),1)
            self.assertEqual(c.call("release",60)[1],[])
            self.assertEqual(c.field("owned"),0)

    def test_same_mode_does_not_reset_rng_or_order(self):
        for mode in (2,3):
            c,_ = phrase(mode)
            c.call("clock",60032,1)
            before = c.raw()
            c.call("mode",mode)
            # The result flags describe this operation; musical state is inert.
            self.assertEqual(c.raw()[:52]+c.raw()[56:],before[:52]+before[56:])

    def test_invalid_enum_and_serial_overflow_are_unchanged(self):
        c = ModesCore(enabled=2)
        c.cpu.mem_write(STATE + native.FIELDS["serial"], struct.pack(">I",0xffffffff))
        for name,args in (("press",(60,100)),("mode",(4,)),("init",(0,4)),("press",(-1,100))):
            before=c.raw()
            self.assertEqual(c.call(name,*args)[0],0xffffffff)
            self.assertEqual(c.raw(),before)

    def test_all_emitted_code_is_audited(self):
        for address,code in native.build().values():
            self.assertLessEqual(len(code),1024)
            self.assertTrue(audit_code(code,address))

    def test_old_suppressed_duplicate_release_preserves_new_gate(self):
        c=ModesCore();c.call("press",60,100)
        c.call("clock",0,1);c.call("clock",7060,1)
        c.call("mode",3);c.call("press",60,90)
        c.call("clock",7100,1);c.call("clock",14200,1)
        self.assertEqual(c.call("release",60)[1],[])
        self.assertEqual(c.field("held"),1)
        self.assertEqual(c.call("release",60)[1],[("off",60,0)])
