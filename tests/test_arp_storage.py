"""Incremental overlay parity against the byte overlay's read-only base."""
import random
import unittest
from types import SimpleNamespace

from lab.arp_storage import DirtyOverlay, OverlaySync, AttachedCard, UI_STACK, protected_stack_spans


class Card:
    def __init__(self):
        self.base = bytes((i * 37) & 255 for i in range(16 * 512))
        self.overlay = {}

    def read(self, sector, length):
        return self.overlay.get(sector, self.base[sector * 512:(sector + 1) * 512])[:length]


class OverlayTests(unittest.TestCase):
    def test_alternating_guest_native_writes_removals_and_restore(self):
        card = Card(); model = SimpleNamespace(overlay={})
        sync = OverlaySync(model, card); rng = random.Random(42)
        for iteration in range(100):
            if iteration % 13 == 0:
                model.overlay = {rng.randrange(8192): rng.randrange(256) for _ in range(20)}
            else:
                for _ in range(20): model.overlay[rng.randrange(8192)] = rng.randrange(256)
                for key in list(model.overlay)[:7]: model.overlay.pop(key)
            previous = sync.before()
            for sector in range(16):
                expected = bytes(model.overlay.get(sector * 512 + i, card.base[sector * 512 + i]) for i in range(512))
                self.assertEqual(card.read(sector, 512), expected)
            sector = rng.randrange(16); data = bytes([iteration]) * 512
            card.overlay[sector] = data
            sync.after(previous)
            self.assertEqual(bytes(model.overlay[sector * 512 + i] for i in range(512)), data)
            counts = sync.imported, sync.published
            sync.after(sync.before())
            self.assertEqual((sync.imported, sync.published), counts)

    def test_dirty_dict_mutations_and_clear_restore_base(self):
        card = Card(); model = SimpleNamespace(overlay={1: 0, 700: 255})
        sync = OverlaySync(model, card)
        sync.after(sync.before()); model.overlay.clear()
        sync.after(sync.before())
        self.assertEqual(card.overlay, {})
        self.assertEqual(model.overlay, {})
        d = DirtyOverlay(); d.setdefault(1, 3); d |= {700: 9}; d.popitem()
        self.assertEqual(d.dirty, {0, 1})
        del d[1]
        self.assertEqual(d, {})

    def test_one_transfer_publishes_only_its_changed_sectors(self):
        card=Card();model=SimpleNamespace(overlay={0:1,512:2})
        sync=OverlaySync(model,card);sync.after(sync.before())
        old=dict(model.overlay)
        previous={1:card.overlay[1]}
        card.overlay[1]=bytes([33])*512
        sync.after(previous,[1])
        self.assertEqual(model.overlay[0],old[0])
        self.assertEqual(bytes(model.overlay[512+i] for i in range(512)),bytes([33])*512)
        self.assertEqual(sync.published,1)


class StackProtectionTests(unittest.TestCase):
    def test_adjacent_queue_is_writable_but_live_stack_is_protected(self):
        from unicorn import m68k_const as r
        class Cpu:
            def __init__(self):
                self.data=bytearray(4096);self.regs={r.UC_M68K_REG_A7:0x4098F62C,r.UC_M68K_REG_SR:0x2004}
            def mem_read(self,a,n):return bytes(self.data[a-0x4098F000:a-0x4098F000+n])
            def mem_write(self,a,b):self.data[a-0x4098F000:a-0x4098F000+len(b)]=b
            def mem_regions(self):return [(0x4098F000,0x4098FFFF,3)]
            def reg_read(self,n):return self.regs[n]
            def reg_write(self,n,v):self.regs[n]=v
            def context_save(self):return dict(self.regs)
            def context_restore(self,v):self.regs=dict(v)
        card=object.__new__(AttachedCard);card.uc=Cpu();card.direct=False;card.stack_checks=0;card._scratch_start=0x62000000
        card.sync=SimpleNamespace(before=lambda:{},after=lambda previous:None)
        # Stock queue storage shares the final page, starting at stack end.
        with card.transaction():card.write(UI_STACK[1]+0x10c,b'QUEUE')
        self.assertEqual(card.stack_checks,1)
        with self.assertRaisesRegex(ValueError,'live guest stack bytes'):
            with card.transaction():card.write(0x4098F62C,b'BAD!')
        self.assertFalse(card.direct)
        # Unknown task stacks retain the complete-page guard.
        self.assertEqual(protected_stack_spans(0x4294896c)[0],(0x42948000,0x42949000))
